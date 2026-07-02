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
    if "Invalid data found" in err:
        raise AnalysisError(f"Error: unreadable or unsupported file: {path}")
    info: dict = {"has_audio": "Stream" in err and "Audio:" in err}
    m = re.search(r"Audio:.*?(\d+) Hz.*?(mono|stereo|(\d+)(?:\.\d+)? channels)", err)
    if m:
        info["sample_rate"] = int(m.group(1))
        ch = m.group(2)
        info["channels"] = 1 if ch == "mono" else 2 if ch == "stereo" \
            else int(m.group(3) or 0)
    d = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
    if d:
        h, mi, s = int(d.group(1)), int(d.group(2)), float(d.group(3))
        info["duration"] = h * 3600 + mi * 60 + s
    return info


def measure(path: str) -> Measurement:
    """Measure integrated loudness, LRA, and true peak of a file's audio."""
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

    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", path,
         "-map", "0:a:0",
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

    return Measurement(
        integrated=f("input_i"),
        lra=f("input_lra"),
        true_peak=f("input_tp"),
        threshold=f("input_thresh"),
        sample_rate=info.get("sample_rate"),
        channels=info.get("channels"),
        duration_seconds=info.get("duration"),
        ffmpeg_version=version,
    )
