"""
Main Qt6 window for pyNika (stub).

Layout (see doc/requirements_specification.md and CalibrantPage.jpg /
Refinementpage.jpg for the reference Nika GUI):

    ┌──────────────────────────────────────────────────────────┐
    │  Left panel (controls)      │  Right panel (image)       │
    │  ─────────────────────────  │  ──────────────────────── │
    │  Data selector              │  2D detector image         │
    │  □ Log intensity scale      │  (pyqtgraph ImageView)     │
    │                             │                            │
    │  Calibrant selection        │  Overlays:                 │
    │    ○ AgBehenate             │  • red dot = beam center   │
    │    ○ LaB6                   │  • red rings = theory      │
    │    ○ Custom                 │  • yellow = search band    │
    │                             │                            │
    │  d-spacing table            │                            │
    │  (use □, value, ± width)    │                            │
    │                             │                            │
    │  Instrument parameters      │                            │
    │  (wavelength, pixel size)   │                            │
    │                             │                            │
    │  Fit parameters             │                            │
    │  SDD □ fit [low] [high]     │                            │
    │  BCx □ fit [low] [high]     │                            │
    │  BCy □ fit [low] [high]     │                            │
    │  TiltX □ fit [low] [high]   │                            │
    │  TiltY □ fit [low] [high]   │                            │
    │  □ No limits                │                            │
    │                             │                            │
    │  χ²: ___  Status: ___       │                            │
    │                             │                            │
    │  [Run Fit]  [Save to File]  │                            │
    │  [Save to PVs]              │                            │
    │  [Export JSON] [Import JSON]│                            │
    └──────────────────────────────────────────────────────────┘

This module is a stub — implementation to follow.
"""

from __future__ import annotations


def launch_gui() -> None:
    """Launch the pyNika Qt6 GUI."""
    try:
        from PyQt6.QtWidgets import QApplication
        import sys
    except ImportError as exc:
        raise ImportError(
            "PyQt6 is required for the GUI. "
            "Install it with:  pip install 'pynika[gui]'  or  conda install pyqt"
        ) from exc

    app = QApplication.instance() or QApplication(sys.argv)
    # TODO: instantiate and show MainWindow
    raise NotImplementedError("GUI not yet implemented — see implementation_plan.md")
