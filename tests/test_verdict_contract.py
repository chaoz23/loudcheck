from loudcheck import Measurement, check


def sample_measurement(**overrides):
    values = {
        "integrated": -23.0,
        "lra": 4.0,
        "true_peak": -2.0,
        "threshold": -33.0,
        "sample_rate": 48000,
        "channels": 2,
        "duration_seconds": 30.0,
        "ffmpeg_version": "unit-test",
    }
    values.update(overrides)
    return Measurement(**values)


def test_r128_verdict_passes_without_ffmpeg_fixture_generation():
    verdict = check(sample_measurement(), "EBU_R128")

    assert verdict["verdict"] == "pass"
    assert verdict["metrics"]["integrated"]["pass"]
    assert verdict["metrics"]["true_peak"]["pass"]


def test_bs1770_is_measurement_only_without_ffmpeg_fixture_generation():
    verdict = check(sample_measurement(integrated=-99.0, true_peak=3.0), "BS_1770")

    assert verdict["verdict"] == "measured"
    assert verdict["failures"] == []
    assert verdict["remediation"] == []

