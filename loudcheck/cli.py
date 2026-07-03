"""
loudcheck CLI — one engine, two surfaces (this and mcp_server.py).

Exit codes (agent contract): 0 = pass (or "measured" for gate-free
standards like BS_1770), 1 = fail — in batch mode, any fail,
2 = error (missing file, no audio, no ffmpeg, unknown standard).
"""

from __future__ import annotations

import argparse
import importlib.resources
import json
import sys
from pathlib import Path

from .analyze import AnalysisError, audio_stream_count, measure
from .standards import STANDARDS
from .verdict import check

MEDIA_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
              ".mp4", ".mov", ".mkv", ".mka", ".webm", ".mxf", ".ts", ".aiff"}


def tool_schema() -> str:
    """The machine-readable tool definition, shipped inside the package
    (the repo-root tool.json is a synced copy for agents browsing GitHub)."""
    return importlib.resources.files("loudcheck").joinpath(
        "tool.json").read_text(encoding="utf-8")


def human(result: dict) -> str:
    lines = [f"{result['verdict'].upper()} — {result['standard_name']}"]
    m = result["metrics"]

    integ = m["integrated"]
    if integ.get("informational"):
        lines.append(f"  · integrated {integ['measured']:.1f} {integ['unit']}")
    else:
        mark = "✓" if integ["pass"] else "✗"
        lines.append(
            f"  {mark} integrated {integ['measured']:.1f} {integ['unit']} "
            f"(target {integ['target']:.1f} ±{integ['tolerance']}, "
            f"delta {integ['delta']:+.1f})")

    tp = m["true_peak"]
    if tp.get("informational"):
        lines.append(f"  · true peak {tp['measured']:.1f} dBTP")
    else:
        mark = "✓" if tp["pass"] else "✗"
        lines.append(
            f"  {mark} true peak {tp['measured']:.1f} dBTP (max {tp['max']:.1f})")

    lines.append(f"  · LRA {m['lra']['measured']:.1f} LU (informational)")
    for key, label in (("max_momentary", "max momentary"),
                       ("max_short_term", "max short-term")):
        if key in m:
            lines.append(
                f"  · {label} {m[key]['measured']:.1f} {m[key]['unit']}")
    for r in result["remediation"]:
        lines.append(f"  → {r}")
    return "\n".join(lines)


def expand_targets(paths: list[str]) -> list[str]:
    """Files stay files; a directory expands to its media files (sorted)."""
    out: list[str] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            out.extend(sorted(
                str(f) for f in pp.iterdir()
                if f.suffix.lower() in MEDIA_EXTS and f.is_file()))
        else:
            out.append(p)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="loudcheck",
        description="Loudness compliance verdict against formal published "
                    "standards (EBU R128, ATSC A/85, BS.1770 measure-only).")
    p.add_argument("files", nargs="*",
                   help="media file(s) or a directory (batch mode)")
    p.add_argument("--schema", action="store_true",
                   help="print the machine-readable tool definition "
                        "(tool.json) and exit")
    p.add_argument("--mcp", action="store_true",
                   help="run as an MCP stdio server "
                        "(requires the [mcp] extra)")
    p.add_argument("--standard", default="EBU_R128",
                   choices=sorted(STANDARDS),
                   help="standard to verdict against (default: EBU_R128)")
    p.add_argument("--stream", type=int, default=0,
                   help="audio stream index to check (default: 0)")
    p.add_argument("--all-streams", action="store_true",
                   help="verdict every audio stream in the file")
    p.add_argument("--detailed", action="store_true",
                   help="add max momentary / max short-term (extra ffmpeg pass)")
    p.add_argument("--json", action="store_true",
                   help="emit the full verdict JSON")
    args = p.parse_args(argv)

    if args.schema:
        print(tool_schema())
        return 0
    if args.mcp:
        from .mcp_server import main as mcp_main  # exits 2 if extra missing
        mcp_main()
        return 0
    if not args.files:
        p.error("files required (or --schema)")

    targets = expand_targets(args.files)
    if not targets:
        print("Error: no media files found", file=sys.stderr)
        return 2

    results = []
    try:
        for path in targets:
            if args.all_streams:
                n = audio_stream_count(path)
                if n == 0:
                    raise AnalysisError("Error: no audio stream found")
                for s in range(n):
                    r = check(measure(path, stream=s, detailed=args.detailed),
                              args.standard)
                    r["file"] = path
                    results.append(r)
            else:
                r = check(measure(path, stream=args.stream,
                                  detailed=args.detailed), args.standard)
                r["file"] = path
                results.append(r)
    except (AnalysisError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2

    batch = len(results) > 1
    if args.json:
        print(json.dumps(results if batch else results[0], indent=2))
    elif batch:
        # table: one line per file/stream
        for r in results:
            m = r["metrics"]
            stream = r["measurement_context"]["audio_stream"]
            tag = f"{r['file']}" + (f" [a:{stream}]" if args.all_streams else "")
            lines = [f"{r['verdict'].upper():8} {tag}  "
                     f"I {m['integrated']['measured']:.1f} "
                     f"TP {m['true_peak']['measured']:.1f}"]
            for rem in r["remediation"]:
                lines.append(f"         → {rem}")
            print("\n".join(lines))
        n_fail = sum(1 for r in results if r["verdict"] == "fail")
        print(f"-- {len(results)} checked, "
              f"{len(results) - n_fail} pass, {n_fail} fail")
    else:
        print(human(results[0]))

    return 1 if any(r["verdict"] == "fail" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
