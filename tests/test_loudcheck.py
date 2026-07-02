"""
Verification corpus (P0.7) — files generated at known loudness with ffmpeg's
lavfi, so no binaries are committed and the suite is self-contained.

Physics of the fixtures: per BS.1770's calibration statement, a MONO 997 Hz
sine at 0 dBFS reads -3.01 LKFS — i.e. a sine measures 3.01 LU below its
peak dBFS. ffmpeg's `sine` source generates at amplitude 1/8 (-18.06 dBFS),
so to hit a target LUFS we apply volume = (target_lufs + 3.01 + 18.06) dB.
Fixtures (known expectations):

  tone at -23 LUFS : passes EBU_R128 (-23 ±0.5)
  tone at -24 LUFS : passes ATSC_A85 (-24 ±2), FAILS EBU_R128 (delta -1.0)
  tone at -18 LUFS : fails both (too loud; remediation must say so exactly)
  tone at TP -0.5  : true-peak fail (limits -1 / -2 dBTP)
  video-only file  : "Error: no audio stream found"

The suite also cross-checks loudnorm's integrated reading against ffmpeg's
independent ebur128 implementation (must agree within 1.0 LU) — if an ffmpeg
release changes filter behavior, this is the test that catches it.
"""

import json
import re
import subprocess
import sys

import pytest

from loudcheck import STANDARDS, check, measure
from loudcheck.analyze import AnalysisError
from loudcheck.cli import main as cli_main

TOL = 1.0  # LU agreement demanded between generated level and measurement


# BS.1770's calibration statement: "If a 0 dB FS 997 Hz sine wave is applied
# to the left, center, or right channel input, the indicated loudness will
# equal -3.01 LKFS." (The -0.691 constant cancels the K-weighting gain at
# 997 Hz.) Verified empirically against ffmpeg loudnorm during development.
SINE_LUFS_BELOW_PEAK = 3.01
SINE_SOURCE_DBFS = -18.06     # ffmpeg sine source amplitude is 1/8


def gen_tone(path, target_lufs=None, target_tp=None, seconds=8, freq=997):
    """Mono 997 Hz sine calibrated to a target integrated LUFS (or peak dBTP)."""
    if target_tp is not None:
        peak_dbfs = target_tp
    else:
        peak_dbfs = target_lufs + SINE_LUFS_BELOW_PEAK
    vol_db = peak_dbfs - SINE_SOURCE_DBFS
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={seconds}:sample_rate=48000",
         "-af", f"volume={vol_db:.3f}dB",
         "-c:a", "pcm_s16le", str(path)],
        check=True)
    return str(path)


@pytest.fixture(scope="session")
def corpus(tmp_path_factory):
    d = tmp_path_factory.mktemp("corpus")
    files = {
        "r128_ok": gen_tone(d / "r128_ok.wav", target_lufs=-23.0),
        "a85_ok": gen_tone(d / "a85_ok.wav", target_lufs=-24.0),
        "loud": gen_tone(d / "loud.wav", target_lufs=-18.0),
        "hot_peak": gen_tone(d / "hot_peak.wav", target_tp=-0.5),
    }
    # video-only file (no audio stream)
    video = d / "video_only.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True)
    files["video_only"] = str(video)
    return files


# ---------------------------------------------------------------------------
# Measurement accuracy
# ---------------------------------------------------------------------------

def test_measurement_matches_generated_level(corpus):
    m = measure(corpus["r128_ok"])
    assert abs(m.integrated - (-23.0)) < TOL, m
    m18 = measure(corpus["loud"])
    assert abs(m18.integrated - (-18.0)) < TOL, m18


def test_loudnorm_agrees_with_ebur128(corpus):
    """Cross-check ffmpeg's two independent R128 implementations."""
    m = measure(corpus["r128_ok"])
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", corpus["r128_ok"],
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True)
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    integ = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1))
    assert abs(m.integrated - integ) < 1.0, (m.integrated, integ)


# ---------------------------------------------------------------------------
# Verdicts (P0.1, P0.3): every corpus file matches its known expectation
# ---------------------------------------------------------------------------

def test_r128_pass(corpus):
    v = check(measure(corpus["r128_ok"]), "EBU_R128")
    assert v["verdict"] == "pass"
    assert v["metrics"]["integrated"]["pass"]
    assert v["metrics"]["true_peak"]["pass"]
    assert not v["remediation"]


def test_a85_pass_and_crossfail(corpus):
    # -24 dBFS tone: passes A/85 (within ±2), fails R128 (outside ±0.5)
    m = measure(corpus["a85_ok"])
    assert check(m, "ATSC_A85")["verdict"] == "pass"
    v = check(m, "EBU_R128")
    assert v["verdict"] == "fail"
    assert not v["metrics"]["integrated"]["pass"]


def test_loud_fails_both_with_remediation(corpus):
    m = measure(corpus["loud"])
    for std, target in (("EBU_R128", -23.0), ("ATSC_A85", -24.0)):
        v = check(m, std)
        assert v["verdict"] == "fail"
        delta = v["metrics"]["integrated"]["delta"]
        assert delta > 0
        # P0.4: remediation states the exact negative gain correction
        assert any(f"{-delta:+.1f} LU gain" in r for r in v["remediation"]), \
            v["remediation"]


def test_true_peak_fail(corpus):
    v = check(measure(corpus["hot_peak"]), "EBU_R128")
    assert not v["metrics"]["true_peak"]["pass"]
    assert v["verdict"] == "fail"
    assert any("limiter" in r or "reduce peaks" in r for r in v["remediation"])


# ---------------------------------------------------------------------------
# Errors (P0.5)
# ---------------------------------------------------------------------------

def test_no_audio_stream(corpus):
    with pytest.raises(AnalysisError, match=r"^Error: no audio stream found"):
        measure(corpus["video_only"])


def test_missing_file():
    with pytest.raises(AnalysisError, match=r"^Error: file not found"):
        measure("/nonexistent/file.wav")


def test_unknown_standard(corpus):
    with pytest.raises(ValueError, match="unknown standard"):
        check(measure(corpus["r128_ok"]), "NETFLIX")


# ---------------------------------------------------------------------------
# CLI exit codes + CLI/MCP parity (P0.6)
# ---------------------------------------------------------------------------

def test_cli_exit_codes(corpus, capsys):
    assert cli_main([corpus["r128_ok"], "--standard", "EBU_R128"]) == 0
    assert cli_main([corpus["loud"], "--standard", "EBU_R128"]) == 1
    assert cli_main(["/nonexistent.wav"]) == 2
    capsys.readouterr()


def test_cli_json_and_mcp_identical(corpus, capsys):
    cli_main([corpus["loud"], "--standard", "EBU_R128", "--json"])
    cli_json = json.loads(capsys.readouterr().out)

    from loudcheck.mcp_server import check_loudness
    mcp_json = check_loudness(corpus["loud"], "EBU_R128")
    assert cli_json == mcp_json  # one engine, byte-identical verdicts


def test_standards_catalog_is_pure_data():
    """Guardrail: the catalog stays data-only, every gated metric cited."""
    for std in STANDARDS.values():
        for metric in std["metrics"].values():
            assert "citation" in metric
            assert not callable(metric.get("target"))
