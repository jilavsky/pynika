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
    instrument : "SAXS", "WAXS", "Custom", or "auto" (default)
        When "auto", the instrument is detected from the HDF5 file
        metadata each time calibrate() / auto_calibrate() is called.
    config_file : path to a JSON config file (required for Custom)
    fit_config  : pynika.fitting.optimizer.FitConfig — override fitting defaults
    """

    INSTRUMENTS = ("SAXS", "WAXS", "Custom", "auto")

    def __init__(
        self,
        instrument: str = "auto",
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

        # 1. Load data
        data = load_image_and_params(hdf5_path)
        resolved_instrument, inst_config = self._resolve_instrument_and_config(data)
        log.info("Calibrating %s with %s", resolved_instrument, hdf5_path)

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
        calibrant_name = inst_config.get("calibrant", "AgBehenate")
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
            instrument=resolved_instrument,
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

    def auto_calibrate(self, hdf5_path: str) -> CalibrationResult:
        """
        Run the automatic multi-stage calibration procedure.

        Stage 1: first 2 enabled d-spacings only, fitting SDD+BCx+BCy only.
                 Aborts if chi²/dof >= 5.0 or no peaks are found.
        Stage 2: all enabled d-spacings, all free parameters.
                 Returns immediately on success if chi²/dof < 0.2.
        Stage 3: repeated full fit from Stage 2 result.
                 chi²/dof < 1.0 → success; >= 1.0 → failure.

        Does not write anything to disk or PVs — call save_to_hdf5() /
        save_to_pvs() separately.
        """
        import copy
        import numpy as np
        from pynika.io.hdf5_io import load_image_and_params
        from pynika.calibrants import get_calibrant
        from pynika.fitting.optimizer import optimise_geometry, FitConfig

        data = load_image_and_params(hdf5_path)
        resolved_instrument, inst_config = self._resolve_instrument_and_config(data)
        log.info("Auto-calibrating %s with %s", resolved_instrument, hdf5_path)

        image    = data["image"];  mask     = data["mask"]
        sdd0     = data["sdd"];    pix      = data["pixel_size"]
        wl       = data["wavelength"]
        bcx0     = data["bcx"];    bcy0     = data["bcy"]
        tilt_x0  = data["tilt_x"]; tilt_y0  = data["tilt_y"]

        calibrant_name = inst_config.get("calibrant", "AgBehenate")
        calibrant = get_calibrant(calibrant_name)
        config    = self.fit_config if self.fit_config is not None else FitConfig()

        # ── Stage 1: first 2 enabled d-spacings, SDD+BCx+BCy only ──────────
        cal_1 = copy.deepcopy(calibrant)
        enabled = [i for i, f in enumerate(cal_1.use_flags) if f]
        for i in range(len(cal_1.use_flags)):
            cal_1.use_flags[i] = i in enabled[:2]

        cfg_1 = FitConfig()
        cfg_1.step_deg          = config.step_deg
        cfg_1.transverse_px     = config.transverse_px
        cfg_1.fit_sdd           = True
        cfg_1.fit_bcx           = True
        cfg_1.fit_bcy           = True
        cfg_1.fit_tilt_x        = False
        cfg_1.fit_tilt_y        = False
        cfg_1.sdd_limits        = config.sdd_limits
        cfg_1.bcx_limits        = config.bcx_limits
        cfg_1.bcy_limits        = config.bcy_limits
        cfg_1.min_peaks_per_ring = config.min_peaks_per_ring

        log.info("Auto Fit Stage 1: first 2 d-spacings, SDD+BCx+BCy")
        r1 = optimise_geometry(
            image, mask, cal_1, wl, pix,
            sdd_init=sdd0, bcx_init=bcx0, bcy_init=bcy0,
            tilt_x_init=tilt_x0, tilt_y_init=tilt_y0,
            config=cfg_1,
        )
        chi1 = r1.chi_square if np.isfinite(r1.chi_square) else 1e9
        if r1.n_peaks_used == 0 or chi1 >= 5.0:
            log.warning(
                "Auto Fit Stage 1 failed: chi²/dof=%.4g, %d peaks", chi1, r1.n_peaks_used
            )
            return CalibrationResult(
                sdd_mm=r1.sdd, bcx=r1.bcx, bcy=r1.bcy,
                tilt_x=r1.tilt_x, tilt_y=r1.tilt_y,
                chi_square=chi1, n_peaks=r1.n_peaks_used,
                success=False,
                message=f"Auto Fit Stage 1 failed (chi²/dof={chi1:.4g}, need <5.0)",
                instrument=resolved_instrument, hdf5_path=hdf5_path,
            )

        # ── Stage 2: all d-spacings, all free parameters ────────────────────
        log.info(
            "Auto Fit Stage 2: all d-spacings, all parameters (Stage 1 chi²=%.4g)", chi1
        )
        r2 = optimise_geometry(
            image, mask, calibrant, wl, pix,
            sdd_init=r1.sdd, bcx_init=r1.bcx, bcy_init=r1.bcy,
            tilt_x_init=r1.tilt_x, tilt_y_init=r1.tilt_y,
            config=config,
        )
        chi2 = r2.chi_square if np.isfinite(r2.chi_square) else 1e9
        if chi2 < 0.2:
            log.info("Auto Fit Stage 2 converged: chi²/dof=%.4f", chi2)
            return CalibrationResult(
                sdd_mm=r2.sdd, bcx=r2.bcx, bcy=r2.bcy,
                tilt_x=r2.tilt_x, tilt_y=r2.tilt_y,
                chi_square=chi2, n_peaks=r2.n_peaks_used,
                success=True,
                message=f"Auto Fit converged at Stage 2 (chi²/dof={chi2:.4f})",
                instrument=resolved_instrument, hdf5_path=hdf5_path,
            )

        # ── Stage 3: refine from Stage 2 result ─────────────────────────────
        log.info(
            "Auto Fit Stage 3: refinement pass (Stage 2 chi²=%.4g)", chi2
        )
        r3 = optimise_geometry(
            image, mask, calibrant, wl, pix,
            sdd_init=r2.sdd, bcx_init=r2.bcx, bcy_init=r2.bcy,
            tilt_x_init=r2.tilt_x, tilt_y_init=r2.tilt_y,
            config=config,
        )
        chi3 = r3.chi_square if np.isfinite(r3.chi_square) else 1e9
        success = chi3 < 1.0
        log.info(
            "Auto Fit Stage 3 complete: chi²/dof=%.4f [%s]",
            chi3, "OK" if success else "FAILED",
        )
        return CalibrationResult(
            sdd_mm=r3.sdd, bcx=r3.bcx, bcy=r3.bcy,
            tilt_x=r3.tilt_x, tilt_y=r3.tilt_y,
            chi_square=chi3, n_peaks=r3.n_peaks_used,
            success=success,
            message=(
                f"Auto Fit Stage 3: chi²/dof={chi3:.4f} "
                f"[{'OK' if success else 'FAILED — chi²≥1'}]"
            ),
            instrument=resolved_instrument, hdf5_path=hdf5_path,
        )

    def save_to_hdf5(self, hdf5_path: str, result: CalibrationResult) -> None:
        """Write optimised parameters back into the HDF5 file."""
        if not result.success:
            log.warning("Calibration was not successful — not saving to HDF5")
            return
        from pynika.io.hdf5_io import save_params_to_hdf5
        save_params_to_hdf5(
            hdf5_path, result.instrument,
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
        # When instrument was auto-detected, look up PVs from the resolved name
        if not pv_map and result is not None and result.instrument:
            from pynika._instrument_configs import INSTRUMENT_CONFIGS
            pv_map = INSTRUMENT_CONFIGS.get(result.instrument, {}).get("epics", {})
        if not pv_map:
            log.warning("No EPICS PV map configured for instrument '%s'", self.instrument)
            return

        if result is None or not result.success:
            reason = failure_reason or (result.message if result else "unknown")
            write_failure_report(pv_map, reason)
            return

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst_label = result.instrument if result.instrument else self.instrument
        report = (
            f"pyNika OK: {inst_label} calibrated {ts}  "
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
        if self.instrument == "auto":
            return {}  # resolved per-file in _resolve_instrument_and_config()
        if self.instrument == "Custom":
            if self.config_file is None:
                raise ValueError("config_file must be provided for Custom instrument")
            with open(self.config_file) as fh:
                return json.load(fh)
        from pynika._instrument_configs import INSTRUMENT_CONFIGS
        return INSTRUMENT_CONFIGS[self.instrument]

    def _resolve_instrument_and_config(self, data: dict) -> tuple[str, dict]:
        """Return (instrument_name, inst_config) from already-loaded file data.

        When self.instrument is "auto", reads the instrument tag written by
        the data-collection system and looks up the matching configuration.
        For explicit instruments the stored config is returned unchanged.
        """
        if self.instrument != "auto":
            return self.instrument, self._inst_config
        from pynika._instrument_configs import INSTRUMENT_CONFIGS
        detected = data.get("instrument", "SAXS")
        log.info("Auto-detected instrument from file: %s", detected)
        inst_config = INSTRUMENT_CONFIGS.get(detected, INSTRUMENT_CONFIGS["SAXS"])
        return detected, inst_config
