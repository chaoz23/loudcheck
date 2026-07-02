"""
loudcheck CLI — one engine, two surfaces (this and mcp_server.py).

Exit codes (agent contract): 0 = pass, 1 = fail (non-compliant),
2 = error (missing file, no audio, no ffmpeg, unknown standard).
"""

from __future__ import annotations

import argparse
import json
import sys

from .analyze import AnalysisError, measure
from .standards import STANDARDS
from .verdict import check


def human(result: dict) -> str:
    lines = [
        f"{result['verdict'].upper()} — {result['standard_name']}",
    ]
    m = result["metrics"]
    integ = m["integrated"]
    mark = "✓" if integ["pass"] else "✗"
    lines.append(
        f"  {mark} integrated {integ['measured']:.1f} {integ['unit']} "
        f"(target {integ['target']:.1f} ±{integ['tolerance']}, "
        f"delta {integ['delta']:+.1f})")
    tp = m["true_peak"]
    mark = "✓" if tp["pass"] else "✗"
    lines.append(
        f"  {mark} true peak {tp['measured']:.1f} dBTP "
        f"(max {tp['max']:.1f})")
    lra = m["lra"]
    lines.append(f"  · LRA {lra['measured']:.1f} LU (informational)")
    for r in result["remediation"]:
        lines.append(f"  → {r}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="loudcheck",
        description="Loudness compliance verdict against formal published "
                    "standards (EBU R128, ATSC A/85).")
    p.add_argument("file", help="media file to check")
    p.add_argument("--standard", default="EBU_R128",
                   choices=sorted(STANDARDS),
                   help="standard to verdict against (default: EBU_R128)")
    p.add_argument("--json", action="store_true",
                   help="emit the full verdict JSON")
    args = p.parse_args(argv)

    try:
        result = check(measure(args.file), args.standard)
    except (AnalysisError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(human(result))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
