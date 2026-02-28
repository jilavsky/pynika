"""
Command-line interface for pyNika.

Usage
-----
    pynika --file DATA.hdf --instrument SAXS [--save-to-pvs]
    pynika --file DATA.hdf --instrument Custom --config my.json [--save-to-pvs]
    pynika --gui

Run ``pynika --help`` for full option list.
"""

from __future__ import annotations
import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pynika",
        description="Calibrate SAXS/WAXS detector geometry from diffraction standards.",
    )
    p.add_argument(
        "--file", "-f",
        metavar="HDF5_FILE",
        help="Path to the HDF5 data file to calibrate.",
    )
    p.add_argument(
        "--instrument", "-i",
        choices=["SAXS", "WAXS", "Custom"],
        default=None,
        help=(
            "Instrument configuration to use: SAXS, WAXS, or Custom. "
            "When omitted the instrument is auto-detected from the HDF5 file metadata "
            "(falls back to SAXS if detection fails)."
        ),
    )
    p.add_argument(
        "--config", "-c",
        metavar="JSON_FILE",
        help="Path to a JSON configuration file (required for Custom instrument).",
    )
    p.add_argument(
        "--auto-fit",
        action="store_true",
        default=False,
        help=(
            "Use the automatic multi-stage fitting procedure: "
            "Stage 1 fits SDD+BCx+BCy with the first 2 d-spacings; "
            "Stage 2–3 fits all parameters with all d-spacings. "
            "chi²/dof < 1 = success."
        ),
    )
    p.add_argument(
        "--save-to-pvs",
        action="store_true",
        default=False,
        help="Write optimised parameters to EPICS PVs (requires pyepics and network access).",
    )
    p.add_argument(
        "--gui",
        action="store_true",
        default=False,
        help="Launch the interactive Qt6 GUI.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.gui:
        _run_gui()
        return 0

    if not args.file:
        print("Error: --file is required when not running in --gui mode.", file=sys.stderr)
        return 1

    from pynika import Calibrator

    # Auto-detect instrument from the HDF5 file when --instrument is not given
    instrument = args.instrument
    if instrument is None and args.config is None:
        try:
            from pynika.io.hdf5_io import load_image_and_params
            _meta = load_image_and_params(args.file)
            instrument = _meta.get("instrument", "SAXS")
            logging.info("Auto-detected instrument: %s", instrument)
        except Exception as _exc:
            instrument = "SAXS"
            logging.warning("Instrument auto-detection failed (%s) — defaulting to SAXS", _exc)
    elif instrument is None:
        instrument = "SAXS"  # Custom requires explicit --instrument Custom

    try:
        cal = Calibrator(instrument=instrument, config_file=args.config)
        if args.auto_fit:
            result = cal.auto_calibrate(args.file)
        else:
            result = cal.calibrate(args.file)
    except Exception as exc:
        logging.error("Calibration failed: %s", exc)
        # Still attempt to write a failure report to PVs
        if args.save_to_pvs:
            try:
                cal.save_to_pvs(result=None, failure_reason=str(exc))
            except Exception:
                pass
        return 2

    print(result)

    cal.save_to_hdf5(args.file, result)

    if args.save_to_pvs:
        cal.save_to_pvs(result)

    return 0


def _run_gui() -> None:
    """Launch the Qt6 GUI (entry point shared by --gui flag and pynika-gui script)."""
    from pynika.gui.main_window import launch_gui
    launch_gui()


def main_gui(argv: list[str] | None = None) -> None:
    """Entry point for the pynika-gui console script."""
    from pynika.gui.main_window import launch_gui
    launch_gui()


if __name__ == "__main__":
    sys.exit(main())
