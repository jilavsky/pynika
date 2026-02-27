"""
Top-level calibration workflow.

Public API
----------
    cal = Calibrator(instrument="SAXS")
    result = cal.calibrate("SAXS.hdf")        # runs the optimisation
    cal.save_to_hdf5("SAXS.hdf", result)      # writes back to file
    cal.save_to_pvs(result)                   # pushes to EPICS PVs
"""

from __future__ import annotations
import datetime
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    """Holds the optimised detector geometry parameters."""

    sdd_mm: float
    bcx: float
    bcy: float
    tilt_x: float
    tilt_y: float
    chi_square: float = float("nan")
    n_peaks: int = 0
    success: bool = False
    message: str = ""
    instrument: str = ""
    hdf5_path: str = ""

    def __str__(self) -> str:
        status = "OK" if self.success else "FAILED"
        return (
            f"CalibrationResult [{status}]  {self.instrument}  {os.path.basename(self.hdf5_path)}\n"
            f"  SDD    = {self.sdd_mm:.3f} mm\n"
            f"  BCx    = {self.bcx:.3f} px\n"
            f"  BCy    = {self.bcy:.3f} px\n"
            f"  TiltX  = {self.tilt_x:.4f} deg\n"
            f"  TiltY  = {self.tilt_y:.4f} deg\n"
            f"  chi2   = {self.chi_square:.4g}   peaks used = {self.n_peaks}\n"
            f"  msg    = {self.message}"
        )


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------

class Calibrator:
    """
    Orchestrates the SAXS/WAXS calibration workflow.

    Parameters
    ----------
    instrument : "SAXS", "WAXS", or "Custom"
    config_file : path to a JSON config file (required for Custom)
    fit_config  : pynika.fitting.optimizer.FitConfig — override fitting defaults
    """

    INSTRUMENTS = ("SAXS", "WAXS", "Custom")

    def __init__(
        self,
        instrument: str = "SAXS",
        config_file: Optional[str] = None,
        fit_config=None,
    ) -> None:
        if instrument not in self.INSTRUMENTS:
            raise ValueError(f"instrument must be one of {self.INSTRUMENTS}")
        self.instrument = instrument
        self.config_file = config_file
        self._inst_config: dict = self._load_instrument_config()
        self.fit_config = fit_config   # None → use FitConfig defaults

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def calibrate(self, hdf5_path: str) -> CalibrationResult:
        """
        Load image from *hdf5_path*, run geometry optimisation, return result.

        Does not write anything to disk or PVs — call save_to_hdf5() /
        save_to_pvs() separately.
        """
        from pynika.io.hdf5_io import load_image_and_params
        from pynika.calibrants import get_calibrant
        from pynika.fitting.optimizer import optimise_geometry, FitConfig

        log.info("Calibrating %s with %s", self.instrument, hdf5_path)

        # 1. Load data
        data = load_image_and_params(hdf5_path)
        image    = data["image"]
        mask     = data["mask"]
        sdd0     = data["sdd"]
        pix      = data["pixel_size"]
        wl       = data["wavelength"]
        bcx0     = data["bcx"]
        bcy0     = data["bcy"]
        tilt_x0  = data["tilt_x"]
        tilt_y0  = data["tilt_y"]

        # 2. Get calibrant
        calibrant_name = self._inst_config.get("calibrant", "AgBehenate")
        calibrant = get_calibrant(calibrant_name)

        # 3. Run optimisation
        config = self.fit_config if self.fit_config is not None else FitConfig()
        opt = optimise_geometry(
            image, mask, calibrant, wl, pix,
            sdd_init=sdd0, bcx_init=bcx0, bcy_init=bcy0,
            tilt_x_init=tilt_x0, tilt_y_init=tilt_y0,
            config=config,
        )

        result = CalibrationResult(
            sdd_mm=opt.sdd,
            bcx=opt.bcx,
            bcy=opt.bcy,
            tilt_x=opt.tilt_x,
            tilt_y=opt.tilt_y,
            chi_square=opt.chi_square,
            n_peaks=opt.n_peaks_used,
            success=opt.success,
            message=opt.message,
            instrument=self.instrument,
            hdf5_path=hdf5_path,
        )
        log.info("%s", result)

        # Sanity check: very high chi2 usually means the file is not calibrant data
        if opt.n_peaks_used > 0 and not opt.success:
            log.warning(
                "Calibration FAILED (chi2/dof=%.2g, %d peaks). "
                "Possible causes: (1) the HDF5 file contains sample data rather "
                "than a calibrant measurement; (2) initial geometry parameters are "
                "far from the true values; (3) the wrong calibrant was selected.",
                opt.chi_square, opt.n_peaks_used,
            )
        elif opt.n_peaks_used > 0 and opt.chi_square > 10.0:
            log.warning(
                "chi2/dof=%.2g is elevated (expected < 10 for a good calibrant). "
                "Verify that the input file is a calibrant measurement and that "
                "initial geometry parameters are reasonable.",
                opt.chi_square,
            )

        return result

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def save_to_hdf5(self, hdf5_path: str, result: CalibrationResult) -> None:
        """Write optimised parameters back into the HDF5 file."""
        if not result.success:
            log.warning("Calibration was not successful — not saving to HDF5")
            return
        from pynika.io.hdf5_io import save_params_to_hdf5
        save_params_to_hdf5(
            hdf5_path, self.instrument,
            result.sdd_mm, result.bcx, result.bcy,
            result.tilt_x, result.tilt_y,
        )

    def save_to_pvs(
        self,
        result: Optional[CalibrationResult] = None,
        failure_reason: str = "",
    ) -> None:
        """
        Push optimised parameters to EPICS PVs.

        If PVs are unreachable the values are printed to the console instead
        of raising an exception.  Writes a failure message if result is None
        or result.success is False.
        """
        from pynika.io.pv_io import write_calibration_to_pvs, write_failure_report
        pv_map = self._inst_config.get("epics", {})
        if not pv_map:
            log.warning("No EPICS PV map configured for instrument '%s'", self.instrument)
            return

        if result is None or not result.success:
            reason = failure_reason or (result.message if result else "unknown")
            write_failure_report(pv_map, reason)
            return

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = (
            f"pyNika OK: {self.instrument} calibrated {ts}  "
            f"file: {os.path.basename(result.hdf5_path)}  "
            f"SDD={result.sdd_mm:.2f} mm  BCx={result.bcx:.2f}  BCy={result.bcy:.2f}  "
            f"TiltX={result.tilt_x:.3f}  TiltY={result.tilt_y:.3f}  "
            f"chi2={result.chi_square:.3g}"
        )
        write_calibration_to_pvs(
            pv_map,
            sdd=result.sdd_mm,
            bcx=result.bcx,
            bcy=result.bcy,
            tilt_x=result.tilt_x,
            tilt_y=result.tilt_y,
            report_message=report,
        )

    def export_config(self, json_path: str) -> None:
        """Export the current instrument configuration to a JSON file."""
        with open(json_path, "w") as fh:
            json.dump(self._inst_config, fh, indent=2)
        log.info("Exported configuration to %s", json_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_instrument_config(self) -> dict:
        if self.instrument == "Custom":
            if self.config_file is None:
                raise ValueError("config_file must be provided for Custom instrument")
            with open(self.config_file) as fh:
                return json.load(fh)
        from pynika._instrument_configs import INSTRUMENT_CONFIGS
        return INSTRUMENT_CONFIGS[self.instrument]
