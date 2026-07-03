"""loudcheck — standards-based loudness compliance verdicts (EBU R128, ATSC A/85)."""

from .analyze import AnalysisError, Measurement, measure  # noqa: F401
from .standards import STANDARDS  # noqa: F401
from .verdict import check  # noqa: F401

__version__ = "0.3.1"
