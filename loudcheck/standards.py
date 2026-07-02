"""
Standards catalog — PURE DATA, no logic.

Every entry cites the published spec text it encodes. Only formal, stable
standards belong here; per-platform delivery templates (Netflix/DPP/...)
are explicitly out of scope — see the scope guardrail in the README. A
standard is: targets + tolerances + citations. Nothing else.

Verified against published text on 2026-07-02:
- EBU R 128 (v4, 2020): "the Programme Loudness Level shall be normalised
  to a Target Level of -23.0 LUFS. The deviation from the Target Level
  shall not exceed +/-0.5 LU" ... "The Maximum Permitted True Peak Level
  of a programme during production shall be -1 dBTP." R 128 sets NO hard
  limit on Loudness Range; LRA is reported as informational.
  https://tech.ebu.ch/docs/r/r128.pdf
- ATSC A/85:2013 (§5.4, §5.5): "the Target Loudness value should be
  -24 LKFS. Minor measurement variations of up to approximately +/-2 dB
  about this value are anticipated, due to measurement uncertainty, and
  are acceptable" ... "The true-peak level should be kept below -2 dB TP
  in order to provide headroom to avoid potential clipping due to
  downstream processing."
  https://www.atsc.org/atsc-documents/a85-techniques-for-establishing-and-maintaining-audio-loudness-for-digital-television/
"""

STANDARDS = {
    "EBU_R128": {
        "name": "EBU R 128",
        "citation": "EBU R 128 (https://tech.ebu.ch/docs/r/r128.pdf)",
        "unit": "LUFS",
        "metrics": {
            "integrated": {
                "target": -23.0,
                "tolerance": 0.5,   # LU; R128 permits ±1.0 for live programmes
                "gated": True,
                "citation": "R 128: Target Level -23.0 LUFS, deviation shall not exceed ±0.5 LU",
            },
            "true_peak": {
                "max": -1.0,        # dBTP
                "gated": True,
                "citation": "R 128: Maximum Permitted True Peak Level -1 dBTP",
            },
            "lra": {
                "gated": False,     # R128 core sets no LRA limit — informational
                "citation": "R 128 defines LRA measurement (EBU Tech 3342) but sets no limit",
            },
        },
    },
    "ATSC_A85": {
        "name": "ATSC A/85:2013",
        "citation": "ATSC A/85:2013 (https://www.atsc.org/atsc-documents/a85-techniques-for-establishing-and-maintaining-audio-loudness-for-digital-television/)",
        "unit": "LKFS",
        "metrics": {
            "integrated": {
                "target": -24.0,
                "tolerance": 2.0,   # dB; A/85 §5.4 "variations of up to approximately ±2 dB ... are acceptable"
                "gated": True,
                "citation": "A/85: Target Loudness -24 LKFS, ±2 dB measurement variation acceptable",
            },
            "true_peak": {
                "max": -2.0,        # dBTP
                "gated": True,
                "citation": "A/85: true-peak level should be kept below -2 dBTP",
            },
            "lra": {
                "gated": False,
                "citation": "A/85 sets no loudness-range limit — informational",
            },
        },
    },
}
