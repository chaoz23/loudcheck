"""
Verdict engine — evaluate a Measurement against a named standard.

Output contract (P0.3, P0.4): a JSON-serializable dict with a top-level
verdict, per-metric measured/target/tolerance/delta/pass, and — on any
fail — concrete remediation text with the exact correction (e.g. "apply
-2.3 LU gain"). Gain remediation maps directly onto ffmpeg's loudnorm/volume
filters; this tool never applies it (measurement and verdict only).

Gating is data-driven from the standards catalog: a metric only gates the
verdict if its catalog entry says `gated: True`. A standard with no gated
metrics (BS_1770) yields verdict "measured" — measurement without judgment,
because the spec defines no target to judge against.
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
    any_gate = False

    # --- integrated loudness (gate: target ± tolerance) ---------------------
    integ = spec["metrics"]["integrated"]
    entry: dict[str, Any] = {
        "measured": round(measurement.integrated, 2),
        "unit": unit,
        "citation": integ["citation"],
    }
    if integ["gated"]:
        any_gate = True
        delta = round(measurement.integrated - integ["target"], 2)
        integ_pass = abs(delta) <= integ["tolerance"]
        entry.update(target=integ["target"], tolerance=integ["tolerance"],
                     delta=delta)
        entry["pass"] = integ_pass
        if not integ_pass:
            direction = "over" if delta > 0 else "under"
            failures.append(
                f"integrated loudness {measurement.integrated:.1f} {unit} is "
                f"{abs(delta):.1f} LU {direction} target {integ['target']:.1f}")
            remediation.append(
                f"apply {-delta:+.1f} LU gain to reach {integ['target']:.1f} "
                f"{unit} (e.g. ffmpeg -af volume={-delta:.1f}dB, or loudnorm "
                f"I={integ['target']:.0f})")
    else:
        entry["pass"] = True
        entry["informational"] = True
    metrics["integrated"] = entry

    # --- true peak (gate: hard maximum) --------------------------------------
    tp = spec["metrics"]["true_peak"]
    entry = {
        "measured": round(measurement.true_peak, 2),
        "unit": "dBTP",
        "citation": tp["citation"],
    }
    if tp["gated"]:
        any_gate = True
        overage = round(measurement.true_peak - tp["max"], 2)
        tp_pass = measurement.true_peak <= tp["max"]
        entry.update(max=tp["max"], delta=overage)
        entry["pass"] = tp_pass
        if not tp_pass:
            failures.append(
                f"true peak {measurement.true_peak:.1f} dBTP exceeds the "
                f"{tp['max']:.1f} dBTP limit by {overage:.1f} dB")
            remediation.append(
                f"reduce peaks by at least {overage:.1f} dB (a "
                f"{-overage:.1f} dB gain reduction, or a true-peak limiter at "
                f"{tp['max']:.1f} dBTP)")
    else:
        entry["pass"] = True
        entry["informational"] = True
    metrics["true_peak"] = entry

    # --- loudness range (informational unless a standard gates it) -----------
    lra = spec["metrics"]["lra"]
    metrics["lra"] = {
        "measured": round(measurement.lra, 2),
        "unit": "LU",
        "pass": True,
        "informational": not lra["gated"],
        "citation": lra["citation"],
    }

    # --- optional detailed metrics (P1.3) -------------------------------------
    if measurement.max_momentary is not None:
        metrics["max_momentary"] = {
            "measured": round(measurement.max_momentary, 2),
            "unit": unit, "pass": True, "informational": True,
            "citation": "max momentary loudness (400 ms window), diagnostic",
        }
    if measurement.max_short_term is not None:
        metrics["max_short_term"] = {
            "measured": round(measurement.max_short_term, 2),
            "unit": unit, "pass": True, "informational": True,
            "citation": "max short-term loudness (3 s window), diagnostic",
        }

    if not any_gate:
        verdict = "measured"
    else:
        verdict = "pass" if not failures else "fail"
    return {
        "verdict": verdict,
        "standard": standard,
        "standard_name": spec["name"],
        "citation": spec["citation"],
        "metrics": metrics,
        "failures": failures,
        "remediation": remediation,
        "measurement_context": {
            "ffmpeg_version": measurement.ffmpeg_version,
            "audio_stream": measurement.stream_index,
            "sample_rate": measurement.sample_rate,
            "channels": measurement.channels,
            "duration_seconds": measurement.duration_seconds,
            "gating_threshold": measurement.threshold,
        },
    }
