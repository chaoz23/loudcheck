"""
Measurement engine — run ffmpeg's loudnorm analysis pass and parse metrics.

Design decisions:
- Single ffmpeg invocation using `loudnorm=print_format=json` in analysis
  mode. The input_* measurement fields are independent of the normalization
  parameters, so one pass yields integrated loudness, LRA, true peak, and
  threshold. (The alternative `ebur128` filter is used in the test suite as
  a cross-check so the two ffmpeg implementations must agree for CI to pass.)
- ffmpeg version is part of the contract: it is captured and returned with
  every measurement, because filter behavior across ffmpeg releases is the
  one realistic maintenance surface this tool has. Minimum supported: 5.0.
- Errors are specific, `Error:`-prefixed, and never a raw trace (P0.5).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

MIN_FFMPEG_MAJOR = 5


class AnalysisError(Exception):
    """Raised with a clean, user-facing message (no traceback semantics)."""


@dataclass
class Measurement:
    integrated: float      # LUFS/LKFS (identical scales; name differs by spec)
    lra: float             # LU
    true_peak: float       # dBTP
    threshold: float       # LUFS, gating threshold used
    sample_rate: Optional[int]
    channels: Optional[int]
    duration_seconds: Optional[float]
    ffmpeg_version: str
    stream_index: int = 0
    max_momentary: Optional[float] = None    # LUFS, 400 ms window (--detailed)
    max_short_term: Optional[float] = None   # LUFS, 3 s window (--detailed)


def _ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AnalysisError(
            "Error: ffmpeg not found on PATH (loudcheck requires ffmpeg >= "
            f"{MIN_FFMPEG_MAJOR}.0)")
    return path


def ffmpeg_version(path: Optional[str] = None) -> str:
    out = subprocess.run(
        [path or _ffmpeg_path(), "-version"],
        capture_output=True, text=True).stdout
    m = re.match(r"ffmpeg version (\S+)", out)
    return m.group(1) if m else "unknown"


def _probe(path: str, ffmpeg: str) -> dict:
    """Light probe via ffmpeg itself (no ffprobe dependency): stream info
    from the -i banner on stderr."""
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        capture_output=True, text=True)
    err = r.stderr
    if "No such file or directory" in err:
        raise AnalysisError(f"Error: file not found: {path}")
    if "File name too long" in err:
        raise AnalysisError(f"Error: file name too long: {path[:120]}…")
    if "Invalid data found" in err:
        raise AnalysisError(f"Error: unreadable or unsupported file: {path}")
    audio_lines = [
        line for line in err.splitlines()
        if re.search(r"Stream #\d+:\d+.*?: Audio:", line)
    ]
    stream_info = []
    for line in audio_lines:
        sample_rate = re.search(r"Audio:.*?(\d+) Hz", line)
        channel_layout = re.search(r"\d+ Hz,\s*([^,]+)", line)
        channels = None
        if channel_layout:
            layout = channel_layout.group(1).strip()
            if layout == "mono":
                channels = 1
            elif layout == "stereo":
                channels = 2
            else:
                count = re.match(r"(\d+) channels?", layout)
                surround = re.match(r"(\d+)\.(\d+)(?:\([^)]*\))?$", layout)
                if count:
                    channels = int(count.group(1))
                elif surround:
                    channels = int(surround.group(1)) + int(surround.group(2))
        stream_info.append({
            "sample_rate": int(sample_rate.group(1)) if sample_rate else None,
            "channels": channels,
        })

    info: dict = {
        "has_audio": bool(audio_lines),
        "audio_streams": len(audio_lines),
        "audio_stream_info": stream_info,
    }
    d = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
    if d:
        h, mi, s = int(d.group(1)), int(d.group(2)), float(d.group(3))
        info["duration"] = h * 3600 + mi * 60 + s
    return info


def audio_stream_count(path: str) -> int:
    """Number of audio streams in the file (0 if none)."""
    return _probe(path, _ffmpeg_path()).get("audio_streams", 0)


def _detailed_pass(ffmpeg: str, path: str, stream: int) -> tuple[float, float]:
    """Second pass with ebur128 to extract max momentary / max short-term.
    The filter logs M/S every 100 ms; we take the maxima."""
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", path,
         "-map", f"0:a:{stream}",
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True)
    momentary = [float(m) for m in re.findall(r"M:\s*(-?[\d.]+)", r.stderr)]
    short_term = [float(s) for s in re.findall(r"S:\s*(-?[\d.]+)", r.stderr)]
    if not momentary or not short_term:
        raise AnalysisError(
            "Error: ebur128 produced no momentary/short-term readings")
    return max(momentary), max(short_term)


def measure(path: str, stream: int = 0, detailed: bool = False) -> Measurement:
    """Measure integrated loudness, LRA, and true peak of one audio stream.

    stream: zero-based audio stream index (0:a:N).
    detailed: also run an ebur128 pass for max momentary / max short-term.
    """
    if stream < 0:
        raise AnalysisError(
            f"Error: audio stream index must be non-negative (got {stream})")

    ffmpeg = _ffmpeg_path()

    version = ffmpeg_version(ffmpeg)
    major = re.match(r"(\d+)", version)
    if major and int(major.group(1)) < MIN_FFMPEG_MAJOR:
        raise AnalysisError(
            f"Error: ffmpeg {version} is below the supported minimum "
            f"({MIN_FFMPEG_MAJOR}.0); loudnorm measurement behavior is "
            "not verified on older releases")

    info = _probe(path, ffmpeg)
    if not info.get("has_audio"):
        raise AnalysisError("Error: no audio stream found")
    n_streams = info.get("audio_streams", 1)
    if stream >= n_streams:
        raise AnalysisError(
            f"Error: audio stream {stream} not found "
            f"(file has {n_streams} audio stream(s))")

    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", path,
         "-map", f"0:a:{stream}",
         "-af", "loudnorm=print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True)
    # loudnorm prints its JSON block to stderr after processing.
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise AnalysisError(
            "Error: ffmpeg loudnorm produced no measurement "
            f"(ffmpeg exit {r.returncode})")
    data = json.loads(m.group(0))

    def f(key: str) -> float:
        v = data.get(key)
        if v in (None, "-inf", "inf"):
            raise AnalysisError(
                f"Error: measurement '{key}' unavailable (silent or "
                "too-short audio?)")
        return float(v)

    max_m = max_s = None
    if detailed:
        max_m, max_s = _detailed_pass(ffmpeg, path, stream)

    selected_info = info["audio_stream_info"][stream]
    return Measurement(
        integrated=f("input_i"),
        lra=f("input_lra"),
        true_peak=f("input_tp"),
        threshold=f("input_thresh"),
        sample_rate=selected_info.get("sample_rate"),
        channels=selected_info.get("channels"),
        duration_seconds=info.get("duration"),
        ffmpeg_version=version,
        stream_index=stream,
        max_momentary=max_m,
        max_short_term=max_s,
    )
