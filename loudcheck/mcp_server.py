"""
MCP surface — thin wrapper over the same engine the CLI uses (P0.6).

Register as a stdio MCP server:
    python -m loudcheck.mcp_server
Import path verified against mcp==1.28.1.
"""

from mcp.server.fastmcp import FastMCP

from .analyze import AnalysisError, measure
from .standards import STANDARDS
from .verdict import check

mcp = FastMCP("loudcheck")


@mcp.tool()
def check_loudness(path: str, standard: str = "EBU_R128",
                   stream: int = 0, detailed: bool = False) -> dict:
    """
    Loudness compliance verdict for a media file against a formal published
    standard. Measures integrated loudness, loudness range, and true peak
    (via ffmpeg), then evaluates them against the named standard's targets
    and tolerances.

    Args:
        path: media file to check (any format ffmpeg can read).
        standard: EBU_R128 (broadcast, -23 LUFS), ATSC_A85 (US TV, -24 LKFS),
            or BS_1770 (measurement only — verdict "measured", no gates).
        stream: zero-based audio stream index for multi-track files.
        detailed: also report max momentary / max short-term loudness
            (one extra ffmpeg pass).

    Returns:
        dict with: verdict (pass|fail|measured), per-metric
        measured/target/delta and pass booleans, failures (plain-English
        causes), remediation (exact corrections, e.g. "apply -2.3 LU gain"),
        and measurement_context (ffmpeg version, stream info).
    """
    try:
        result = check(measure(path, stream=stream, detailed=detailed), standard)
        result["file"] = path  # echoed for batch-calling agents; matches CLI JSON
        return result
    except (AnalysisError, ValueError) as e:
        return {"verdict": "error", "error": str(e), "file": path}


@mcp.tool()
def list_standards() -> dict:
    """List the standards this tool can verdict against, with their targets,
    tolerances, and spec citations."""
    return {"standards": STANDARDS}


if __name__ == "__main__":
    mcp.run()
