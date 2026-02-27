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
        default="SAXS",
        help="Instrument configuration to use (default: SAXS).",
    )
    p.add_argument(
        "--config", "-c",
        metavar="JSON_FILE",
        help="Path to a JSON configuration file (required for Custom instrument).",
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

    try:
        cal = Calibrator(instrument=args.instrument, config_file=args.config)
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
