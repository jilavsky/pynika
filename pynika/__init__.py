"""
pynika — calibration of SAXS/WAXS pinhole instruments.

Top-level public API:
    Calibrator   — runs the optimisation workflow
    CalibrationResult — dataclass holding optimised parameters
"""

from pynika._version import __version__
from pynika.calibrator import Calibrator, CalibrationResult

__all__ = ["Calibrator", "CalibrationResult", "__version__"]
