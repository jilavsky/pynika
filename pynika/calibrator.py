"""
Top-level calibration workflow.

This module is a stub.  The full optimisation loop will be implemented
as described in doc/implementation_plan.md.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class CalibrationResult:
    """Holds the optimised detector geometry parameters."""

    sdd_mm: float
    bcx: float
    bcy: float
    tilt_x: float
    tilt_y: float
    chi_square: float = float("nan")
    success: bool = False
    message: str = ""

    def __str__(self) -> str:
        return (
            f"CalibrationResult("
            f"sdd={self.sdd_mm:.2f} mm, "
            f"bcx={self.bcx:.2f} px, bcy={self.bcy:.2f} px, "
            f"tilt_x={self.tilt_x:.4f}°, tilt_y={self.tilt_y:.4f}°, "
            f"chi²={self.chi_square:.4g}, "
            f"{'OK' if self.success else 'FAILED'})"
        )


class Calibrator:
    """
    Orchestrates the SAXS/WAXS calibration workflow.

    Parameters
    ----------
    instrument : str
        One of "SAXS", "WAXS", or "Custom".
    config_file : str, optional
        Path to a JSON configuration file (required when instrument="Custom").

    Notes
    -----
    This class is a stub.  See doc/implementation_plan.md for the full
    description of the algorithm to be implemented.
    """

    INSTRUMENTS = ("SAXS", "WAXS", "Custom")

    def __init__(self, instrument: str = "SAXS", config_file: Optional[str] = None) -> None:
        if instrument not in self.INSTRUMENTS:
            raise ValueError(f"instrument must be one of {self.INSTRUMENTS}")
        self.instrument = instrument
        self.config_file = config_file
        self._config: dict = self._load_config()

    # ------------------------------------------------------------------
    # Public API (stubs — to be implemented)
    # ------------------------------------------------------------------

    def calibrate(self, hdf5_path: str) -> CalibrationResult:
        """
        Load image and parameters from *hdf5_path* and run the optimisation.

        Returns
        -------
        CalibrationResult
        """
        raise NotImplementedError("calibrate() not yet implemented — see implementation_plan.md")

    def save_to_hdf5(self, hdf5_path: str, result: CalibrationResult) -> None:
        """Write optimised parameters back into the HDF5 file."""
        raise NotImplementedError

    def save_to_pvs(self, result: CalibrationResult) -> None:
        """
        Push optimised parameters to EPICS PVs.

        If PVs are unreachable the values are printed to stdout instead of
        raising an exception.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        """Load instrument configuration from JSON (Custom mode) or built-ins."""
        import json, os

        if self.instrument == "Custom":
            if self.config_file is None:
                raise ValueError("config_file must be provided for Custom instrument")
            with open(self.config_file) as fh:
                return json.load(fh)

        # Built-in SAXS / WAXS configurations
        from pynika._instrument_configs import INSTRUMENT_CONFIGS
        return INSTRUMENT_CONFIGS[self.instrument]
