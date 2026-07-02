"""
Verdict engine — evaluate a Measurement against a named standard.

Output contract (P0.3, P0.4): a JSON-serializable dict with a top-level
pass/fail, per-metric measured/target/tolerance/delta/pass, and — on any
fail — concrete remediation text with the exact correction (e.g. "apply
-2.3 LU gain"). Gain remediation maps directly onto ffmpeg's loudnorm/volume
filters; this tool never applies it (measurement and verdict only).
"""

from __future__ import annotations

from typing import Any

from .analyze import Measurement
from .standards import STANDARDS


def check(measurement: Measurement, standard: str) -> dict[str, Any]:
    if standard not in STANDARDS:
        raise ValueError(
            f"Error: unknown standard '{standard}' "
            f"(available: {', '.join(sorted(STANDARDS))})")
    spec = STANDARDS[standard]
    unit = spec["unit"]
    metrics: dict[str, Any] = {}
    failures: list[str] = []
    remediation: list[str] = []

    # --- integrated loudness (gated: target ± tolerance) -------------------
    integ = spec["metrics"]["integrated"]
    delta = round(measurement.integrated - integ["target"], 2)
    integ_pass = abs(delta) <= integ["tolerance"]
    metrics["integrated"] = {
        "measured": round(measurement.integrated, 2),
        "target": integ["target"],
        "tolerance": integ["tolerance"],
        "delta": delta,
        "unit": unit,
        "pass": integ_pass,
        "citation": integ["citation"],
    }
    if not integ_pass:
        direction = "over" if delta > 0 else "under"
        failures.append(
            f"integrated loudness {measurement.integrated:.1f} {unit} is "
            f"{abs(delta):.1f} LU {direction} target {integ['target']:.1f}")
        remediation.append(
            f"apply {-delta:+.1f} LU gain to reach {integ['target']:.1f} "
            f"{unit} (e.g. ffmpeg -af volume={-delta:.1f}dB, or loudnorm "
            f"I={integ['target']:.0f})")

    # --- true peak (gated: hard maximum) ------------------------------------
    tp = spec["metrics"]["true_peak"]
    overage = round(measurement.true_peak - tp["max"], 2)
    tp_pass = measurement.true_peak <= tp["max"]
    metrics["true_peak"] = {
        "measured": round(measurement.true_peak, 2),
        "max": tp["max"],
        "delta": overage,
        "unit": "dBTP",
        "pass": tp_pass,
        "citation": tp["citation"],
    }
    if not tp_pass:
        failures.append(
            f"true peak {measurement.true_peak:.1f} dBTP exceeds the "
            f"{tp['max']:.1f} dBTP limit by {overage:.1f} dB")
        remediation.append(
            f"reduce peaks by at least {overage:.1f} dB (a "
            f"{-overage:.1f} dB gain reduction, or a true-peak limiter at "
            f"{tp['max']:.1f} dBTP)")

    # --- loudness range (informational unless the standard gates it) --------
    lra = spec["metrics"]["lra"]
    metrics["lra"] = {
        "measured": round(measurement.lra, 2),
        "unit": "LU",
        "pass": True,          # never gates unless a standard defines a limit
        "informational": not lra["gated"],
        "citation": lra["citation"],
    }

    ok = not failures
    return {
        "verdict": "pass" if ok else "fail",
        "standard": standard,
        "standard_name": spec["name"],
        "citation": spec["citation"],
        "metrics": metrics,
        "failures": failures,
        "remediation": remediation,
        "measurement_context": {
            "ffmpeg_version": measurement.ffmpeg_version,
            "sample_rate": measurement.sample_rate,
            "channels": measurement.channels,
            "duration_seconds": measurement.duration_seconds,
            "gating_threshold": measurement.threshold,
        },
    }
