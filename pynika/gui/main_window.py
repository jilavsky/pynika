"""
Main Qt6 window for pyNika.

Layout mirrors the Nika Igor Pro GUI (see examples/Calibrantpage.jpg and
examples/Refinementpage.jpg for reference screenshots):

    ┌──────────────────────────────────────────────────────────┐
    │  Left panel (QScrollArea)    │  Right panel (image)       │
    │  ─────────────────────────  │  ──────────────────────── │
    │  Data File selector          │  2D detector image         │
    │  □ Log intensity scale       │  (pyqtgraph PlotItem)      │
    │                              │                            │
    │  Calibrant ▾ AgBehenate      │  Overlays:                 │
    │                              │  • red cross = beam center │
    │  d-Spacings                  │  • red curves  = theory    │
    │  Set ±W all: [15] [Apply]    │  • yellow dash = ±search   │
    │  Use  d (Å)   ±W  Show       │                            │
    │  □   58.380  [15] □          │                            │
    │  ...                         │                            │
    │                              │                            │
    │  Instrument Parameters       │                            │
    │  Wavelength (Å):  [editable] │                            │
    │  Pixel size (mm): [editable] │                            │
    │                              │                            │
    │  Fit Parameters              │                            │
    │  Param  Value  Fit  Low  Hi  │                            │
    │  SDD    [500]  □   [1] [∞]  │                            │
    │  BCx    [512]  □   ...       │                            │
    │  □ No limits                 │                            │
    └──────────────────────────────────────────────────────────┘

Phase 6 items implemented here:
  6.1  QMainWindow + horizontal QSplitter
  6.2  Left QScrollArea
  6.3  Data-file selector (QPushButton + QFileDialog + path label)
  6.4  Log-intensity checkbox
  6.5  pyqtgraph GraphicsLayoutWidget / PlotItem for 2D image
  6.6  Calibrant combo (AgBehenate / LaB6)
  6.7  d-spacing table (Use □, d, ±W spinbox, Show □)
  6.8  Instrument parameters (wavelength, pixel size) — editable override
  6.9  Fit-parameters table (value spinbox, Fit □, Low/High edits)
  6.10 "No limits" checkbox — hides Low/High columns
  6.11 Beam-center overlay (red crosshair ScatterPlotItem)
  6.12 Ring overlays: red = tilted-model theory, yellow dashed = ±search band
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter definitions (order: SDD, BCx, BCy, TiltX, TiltY)
# ---------------------------------------------------------------------------
_PARAM_KEYS    = ["sdd",     "bcx",     "bcy",     "tilt_x",  "tilt_y"]
_PARAM_LABELS  = ["SDD (mm)", "BCx (px)", "BCy (px)", "TiltX (°)", "TiltY (°)"]
_PARAM_DFLTS   = [500.0,      512.0,      512.0,      0.0,         0.0]
_PARAM_STEPS   = [1.0,        0.5,        0.5,        0.01,        0.01]
_PARAM_DECS    = [2,          3,          3,          4,           4]
_PARAM_FIT     = [True,       True,       True,       True,        True]
_PARAM_LOW     = [1.0,       -1e5,       -1e5,       -45.0,       -45.0]
_PARAM_HIGH    = [5e4,        1e5,        1e5,        45.0,        45.0]


# ---------------------------------------------------------------------------
# launch_gui  — public entry point
# ---------------------------------------------------------------------------

def launch_gui() -> None:
    """Launch the pyNika Qt6 GUI (entry point for --gui flag and pynika-gui script)."""
    try:
        import sys
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QSplitter, QWidget, QScrollArea,
            QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
            QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
            QDoubleSpinBox, QFormLayout, QLineEdit, QFileDialog,
            QSizePolicy, QHeaderView, QProgressBar,
            QDialog, QDialogButtonBox, QMessageBox,
        )
        from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
        import pyqtgraph as pg
    except ImportError as exc:
        raise ImportError(
            "PyQt6 and pyqtgraph are required for the GUI.\n"
            "Install with:  conda install pyqt pyqtgraph\n"
            "          or:  pip install 'pynika[gui]'"
        ) from exc

    # -----------------------------------------------------------------------
    # FitWorker — runs optimise_geometry in a QThread (task 6.13)
    # -----------------------------------------------------------------------

    class FitWorker(QObject):
        """Runs the geometry optimisation on a background thread."""
        progress = pyqtSignal(int, int)   # (ring_index, n_rings_total)
        finished = pyqtSignal(object)     # OptimisationResult

        def __init__(
            self, image, mask, calibrant, wavelength, pixel_size,
            sdd, bcx, bcy, tilt_x, tilt_y, config,
        ) -> None:
            super().__init__()
            self._image = image
            self._mask = mask
            self._calibrant = calibrant
            self._wavelength = wavelength
            self._pixel_size = pixel_size
            self._sdd = sdd
            self._bcx = bcx
            self._bcy = bcy
            self._tilt_x = tilt_x
            self._tilt_y = tilt_y
            self._config = config

        def run(self) -> None:
            from pynika.fitting.optimizer import optimise_geometry
            result = optimise_geometry(
                self._image, self._mask, self._calibrant,
                self._wavelength, self._pixel_size,
                self._sdd, self._bcx, self._bcy,
                self._tilt_x, self._tilt_y,
                config=self._config,
                progress_fn=lambda i, n: self.progress.emit(i, n),
            )
            self.finished.emit(result)

    # -----------------------------------------------------------------------
    # AutoFitWorker — runs the multi-stage Auto Fit on a background thread
    # -----------------------------------------------------------------------

    class AutoFitWorker(QObject):
        """Runs the 3-stage auto-fit procedure on a background QThread."""
        stage_update = pyqtSignal(str, int)   # (message, stage 1/2/3)
        finished     = pyqtSignal(object, str) # (OptimisationResult, final_message)

        def __init__(
            self, image, mask, calibrant, wavelength, pixel_size,
            sdd, bcx, bcy, tilt_x, tilt_y, config,
        ) -> None:
            super().__init__()
            self._image = image;  self._mask = mask
            self._calibrant = calibrant
            self._wavelength = wavelength;  self._pixel_size = pixel_size
            self._sdd = sdd;  self._bcx = bcx;  self._bcy = bcy
            self._tilt_x = tilt_x;  self._tilt_y = tilt_y
            self._config = config

        def run(self) -> None:
            import copy
            import math
            from pynika.fitting.optimizer import optimise_geometry, FitConfig

            # Stage 1: first 2 enabled d-spacings, SDD+BCx+BCy only
            cal_1 = copy.deepcopy(self._calibrant)
            enabled = [i for i, f in enumerate(cal_1.use_flags) if f]
            for i in range(len(cal_1.use_flags)):
                cal_1.use_flags[i] = i in enabled[:2]

            cfg_1 = FitConfig()
            cfg_1.step_deg           = self._config.step_deg
            cfg_1.transverse_px      = self._config.transverse_px
            cfg_1.fit_sdd            = True
            cfg_1.fit_bcx            = True
            cfg_1.fit_bcy            = True
            cfg_1.fit_tilt_x         = False
            cfg_1.fit_tilt_y         = False
            cfg_1.sdd_limits         = self._config.sdd_limits
            cfg_1.bcx_limits         = self._config.bcx_limits
            cfg_1.bcy_limits         = self._config.bcy_limits
            cfg_1.min_peaks_per_ring = self._config.min_peaks_per_ring

            self.stage_update.emit("Stage 1/3: first 2 rings — SDD, BCx, BCy…", 1)
            r1 = optimise_geometry(
                self._image, self._mask, cal_1,
                self._wavelength, self._pixel_size,
                self._sdd, self._bcx, self._bcy,
                self._tilt_x, self._tilt_y,
                config=cfg_1,
            )
            chi1 = r1.chi_square if math.isfinite(r1.chi_square) else 1e9
            if r1.n_peaks_used == 0 or chi1 >= 5.0:
                self.finished.emit(
                    r1,
                    f"Aborted at Stage 1 — chi²/dof={chi1:.3g} (need <5) or no peaks",
                )
                return

            # Stage 2: all enabled peaks, all free parameters
            self.stage_update.emit("Stage 2/3: all rings — all parameters…", 2)
            r2 = optimise_geometry(
                self._image, self._mask, self._calibrant,
                self._wavelength, self._pixel_size,
                r1.sdd, r1.bcx, r1.bcy,
                r1.tilt_x, r1.tilt_y,
                config=self._config,
            )
            chi2 = r2.chi_square if math.isfinite(r2.chi_square) else 1e9
            if chi2 < 0.2:
                self.finished.emit(r2, f"Converged at Stage 2 — chi²/dof={chi2:.4f}")
                return

            # Stage 3: refinement pass
            self.stage_update.emit("Stage 3/3: refinement pass…", 3)
            r3 = optimise_geometry(
                self._image, self._mask, self._calibrant,
                self._wavelength, self._pixel_size,
                r2.sdd, r2.bcx, r2.bcy,
                r2.tilt_x, r2.tilt_y,
                config=self._config,
            )
            chi3 = r3.chi_square if math.isfinite(r3.chi_square) else 1e9
            status_tag = "OK" if chi3 < 3.0 else "FAILED (chi²≥3)"
            self.finished.emit(r3, f"Stage 3 complete — chi²/dof={chi3:.4f} [{status_tag}]")

    # -----------------------------------------------------------------------
    # MainWindow class (defined inside launch_gui to avoid top-level Qt imports)
    # -----------------------------------------------------------------------

    class MainWindow(QMainWindow):
        """
        Two-pane calibration window.
        Left  — controls (file, calibrant, d-spacings, parameters)
        Right — 2D detector image with beam-center and ring overlays
        """

        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("pyNika — SAXS/WAXS Geometry Calibration")
            self.resize(1300, 820)

            # Application state
            self._image: Optional[np.ndarray] = None
            self._params: Optional[dict] = None
            self._calibrant = None

            # d-table widget references (populated in _populate_d_table)
            self._d_rows: list[tuple] = []        # (use_cb, w_spin)
            self._d_value_spins: list = []         # QDoubleSpinBox list, only for Custom calibrant

            # Overlay items in the plot (cleared on each update)
            self._ring_items: list = []
            self._band_items: list = []

            self._build_ui()

        # -------------------------------------------------------------------
        # UI construction — tasks 6.1 – 6.12
        # -------------------------------------------------------------------

        def _build_ui(self) -> None:
            # 6.1 — horizontal splitter
            splitter = QSplitter(Qt.Orientation.Horizontal, self)
            self.setCentralWidget(splitter)

            # 6.2 — left scroll panel
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(400)
            scroll.setMaximumWidth(600)
            left_widget = QWidget()
            left_layout = QVBoxLayout(left_widget)
            left_layout.setSpacing(6)
            left_layout.setContentsMargins(4, 4, 4, 4)

            # 6.3 — data file selector
            self._build_file_group(left_layout)

            # 6.4 — log intensity checkbox (default ON)
            self._log_cb = QCheckBox("Log intensity scale")
            self._log_cb.setChecked(True)
            left_layout.addWidget(self._log_cb)
            self._log_cb.toggled.connect(lambda _: self._update_image_display(reset_view=False))

            # 6.6 — calibrant selector (signal connected AFTER table is built)
            self._build_calibrant_group(left_layout)

            # 6.7 — d-spacing table
            self._build_dspacing_group(left_layout)

            # 6.8 — instrument parameters
            self._build_instrument_group(left_layout)

            # 6.9 + 6.10 — fit parameters + no-limits checkbox
            self._build_fit_params_group(left_layout)

            # 6.13 + 6.14 — run fit button, progress, chi² display
            self._build_run_section(left_layout)

            # 6.15–6.18 — save, export, and device config
            self._build_save_section(left_layout)

            left_layout.addStretch()
            scroll.setWidget(left_widget)
            splitter.addWidget(scroll)

            # 6.5 — image panel (right side)
            self._build_image_panel(splitter)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
            splitter.setSizes([440, 860])

            # Connect calibrant combo signal AFTER d-table exists, then populate
            self._cal_combo.currentTextChanged.connect(self._on_calibrant_changed)
            self._on_calibrant_changed(self._cal_combo.currentText())

            self.statusBar().showMessage(
                "Ready — select a calibrant HDF5 file to begin."
            )

        # ..........................................
        # 6.3 — File group
        # ..........................................

        def _build_file_group(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Data File")
            v = QVBoxLayout(grp)

            row = QHBoxLayout()
            btn = QPushButton("Select File…")
            btn.clicked.connect(self._on_select_file)
            row.addWidget(btn)
            row.addStretch()
            v.addLayout(row)

            self._file_label = QLabel("No file loaded.")
            self._file_label.setWordWrap(True)
            self._file_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            v.addWidget(self._file_label)
            layout.addWidget(grp)

        # ..........................................
        # 6.6 — Calibrant selector
        # ..........................................

        def _build_calibrant_group(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Calibrant")
            h = QHBoxLayout(grp)
            h.addWidget(QLabel("Calibrant:"))
            self._cal_combo = QComboBox()
            self._cal_combo.addItems(["AgBehenate", "LaB6", "Custom"])
            self._cal_combo.setToolTip(
                "AgBehenate — SAXS standard\n"
                "LaB6 — WAXS standard\n"
                "Custom — enter your own d-spacings directly in the table below"
            )
            h.addWidget(self._cal_combo)
            h.addStretch()
            layout.addWidget(grp)

        # ..........................................
        # 6.7 — d-spacing table
        # ..........................................

        def _build_dspacing_group(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("d-Spacings")
            v = QVBoxLayout(grp)

            # "Set ±W all" convenience row
            row = QHBoxLayout()
            row.addWidget(QLabel("Set ±W all (px):"))
            self._width_all_spin = QDoubleSpinBox()
            self._width_all_spin.setRange(1, 500)
            self._width_all_spin.setValue(15.0)
            self._width_all_spin.setSingleStep(5.0)
            self._width_all_spin.setDecimals(0)
            row.addWidget(self._width_all_spin)
            apply_btn = QPushButton("Apply")
            apply_btn.clicked.connect(self._on_set_all_widths)
            row.addWidget(apply_btn)
            row.addStretch()
            v.addLayout(row)

            self._d_table = QTableWidget(0, 3)
            self._d_table.setHorizontalHeaderLabels(["Use", "d (Å)", "±W (px)"])
            hh = self._d_table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            self._d_table.setColumnWidth(0, 42)
            self._d_table.setColumnWidth(2, 70)
            self._d_table.verticalHeader().setVisible(False)
            self._d_table.setFixedHeight(230)
            v.addWidget(self._d_table)
            layout.addWidget(grp)

        # ..........................................
        # 6.8 — Instrument parameters
        # ..........................................

        def _build_instrument_group(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Instrument Parameters")
            form = QFormLayout(grp)

            self._wl_edit = QLineEdit("—")
            self._wl_edit.setToolTip(
                "X-ray wavelength (Å) — loaded from HDF5 file.\n"
                "You can edit this value to override the stored wavelength."
            )
            form.addRow("Wavelength (Å):", self._wl_edit)

            self._pix_edit = QLineEdit("—")
            self._pix_edit.setToolTip(
                "Pixel size (mm) — loaded from HDF5 file.\n"
                "Edit to override if the file value is incorrect."
            )
            form.addRow("Pixel size (mm):", self._pix_edit)

            self._inst_label = QLabel("—")
            form.addRow("Detected instrument:", self._inst_label)

            layout.addWidget(grp)

        # ..........................................
        # 6.9 + 6.10 — Fit parameters table
        # ..........................................

        def _build_fit_params_group(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Fit Parameters")
            v = QVBoxLayout(grp)

            self._fit_table = QTableWidget(5, 5)
            self._fit_table.setHorizontalHeaderLabels(
                ["Parameter", "Value", "Fit?", "Low", "High"]
            )
            self._fit_table.verticalHeader().setVisible(False)
            hh = self._fit_table.horizontalHeader()
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            self._fit_table.setColumnWidth(0, 90)
            self._fit_table.setColumnWidth(2, 46)
            self._fit_table.setColumnWidth(3, 62)
            self._fit_table.setColumnWidth(4, 62)

            self._fit_value_spins: list[QDoubleSpinBox] = []
            self._fit_checkboxes:  list[QCheckBox]      = []
            self._fit_low_edits:   list[QLineEdit]      = []
            self._fit_high_edits:  list[QLineEdit]      = []

            for row_idx, (label, dflt, step, decs, fit, lo, hi) in enumerate(zip(
                _PARAM_LABELS, _PARAM_DFLTS, _PARAM_STEPS,
                _PARAM_DECS,   _PARAM_FIT,   _PARAM_LOW, _PARAM_HIGH,
            )):
                # Col 0 — parameter label (read-only)
                item = QTableWidgetItem(label)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._fit_table.setItem(row_idx, 0, item)

                # Col 1 — value spinbox
                spin = QDoubleSpinBox()
                spin.setDecimals(decs)
                spin.setSingleStep(step)
                spin.setRange(-1e7, 1e7)
                spin.setValue(dflt)
                spin.valueChanged.connect(self._on_params_changed)
                self._fit_table.setCellWidget(row_idx, 1, spin)
                self._fit_value_spins.append(spin)

                # Col 2 — fit checkbox (centred)
                cb = QCheckBox()
                cb.setChecked(fit)
                container = QWidget()
                hbox = QHBoxLayout(container)
                hbox.addWidget(cb)
                hbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hbox.setContentsMargins(0, 0, 0, 0)
                self._fit_table.setCellWidget(row_idx, 2, container)
                self._fit_checkboxes.append(cb)

                # Col 3 — lower bound
                lo_edit = QLineEdit(str(lo))
                self._fit_table.setCellWidget(row_idx, 3, lo_edit)
                self._fit_low_edits.append(lo_edit)

                # Col 4 — upper bound
                hi_edit = QLineEdit(str(hi))
                self._fit_table.setCellWidget(row_idx, 4, hi_edit)
                self._fit_high_edits.append(hi_edit)

            self._fit_table.resizeRowsToContents()
            # Constrain table height so there is no empty space below the rows
            _row_h = self._fit_table.rowHeight(0) if self._fit_table.rowCount() else 28
            _hdr_h = self._fit_table.horizontalHeader().height()
            self._fit_table.setMaximumHeight(_hdr_h + _row_h * 5 + 4)
            v.addWidget(self._fit_table)

            # 6.10 — No limits checkbox
            self._no_limits_cb = QCheckBox("No limits (hide bound columns)")
            self._no_limits_cb.toggled.connect(self._on_no_limits_changed)
            v.addWidget(self._no_limits_cb)

            grp.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            layout.addWidget(grp)

        # ..........................................
        # 6.15–6.18 — Save & Export section
        # ..........................................

        def _build_save_section(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Save & Export")
            v = QVBoxLayout(grp)

            # 6.15 Save to File + 6.16 Save to PVs (one row)
            save_row = QHBoxLayout()
            save_file_btn = QPushButton("Save to File")
            save_file_btn.setToolTip(
                "Write current calibration parameters back into the loaded HDF5 file."
            )
            save_file_btn.clicked.connect(self._on_save_to_file)
            save_row.addWidget(save_file_btn)

            save_pv_btn = QPushButton("Save to PVs")
            save_pv_btn.setToolTip(
                "Write current calibration parameters to EPICS process variables."
            )
            save_pv_btn.clicked.connect(self._on_save_to_pvs)
            save_row.addWidget(save_pv_btn)
            v.addLayout(save_row)

            # 6.17 Export / Import JSON (one row)
            json_row = QHBoxLayout()
            export_btn = QPushButton("Export JSON…")
            export_btn.setToolTip("Save current parameters to a JSON file.")
            export_btn.clicked.connect(self._on_export_json)
            json_row.addWidget(export_btn)

            import_btn = QPushButton("Import JSON…")
            import_btn.setToolTip("Load parameters from a JSON file.")
            import_btn.clicked.connect(self._on_import_json)
            json_row.addWidget(import_btn)
            v.addLayout(json_row)

            # 6.18 Custom device config
            cfg_btn = QPushButton("Custom Device Config…")
            cfg_btn.setToolTip(
                "Edit EPICS PV names for a custom instrument configuration."
            )
            cfg_btn.clicked.connect(self._on_custom_config)
            v.addWidget(cfg_btn)

            layout.addWidget(grp)

        # 6.15 — Save to File
        def _on_save_to_file(self) -> None:
            if self._params is None:
                self.statusBar().showMessage("Load a file first.")
                return
            path = self._params.get("hdf5_path", "")
            if not path:
                self.statusBar().showMessage("No file path available.")
                return
            p = self._get_params()
            inst = self._params.get("instrument", "SAXS")
            try:
                import datetime
                from pynika.io.hdf5_io import save_params_to_hdf5
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                chi2_text = self._chi2_label.text()  # e.g. "χ²/dof: 2.31"
                report_msg = (
                    f"pyNika OK: {inst} calibrated {ts}\n"
                    f"  file: {path}\n"
                    #f"  SDD={p['sdd']:.3f} mm, BCx={p['bcx']:.3f}, "
                    #f"BCy={p['bcy']:.3f}, TiltX={p['tilt_x']:.4f}, "
                   # f"TiltY={p['tilt_y']:.4f}\n"
                    f"  {chi2_text}"
                )
                save_params_to_hdf5(
                    path, inst,
                    p["sdd"], p["bcx"], p["bcy"], p["tilt_x"], p["tilt_y"],
                    calibration_report=report_msg,
                )
                self.statusBar().showMessage(
                    f"Saved parameters to {os.path.basename(path)}"
                )
                QMessageBox.information(
                    self, "Saved",
                    f"Calibration parameters written to:\n{path}",
                )
            except Exception as exc:
                self.statusBar().showMessage(f"Save failed: {exc}")
                QMessageBox.warning(self, "Save Failed", str(exc))

        # 6.16 — Save to PVs
        def _on_save_to_pvs(self) -> None:
            if self._params is None:
                self.statusBar().showMessage("Load a file first.")
                return
            inst = self._params.get("instrument", "unknown")
            from pynika._instrument_configs import INSTRUMENT_CONFIGS
            pv_map: Optional[dict] = None
            if hasattr(self, "_custom_pv_map") and self._custom_pv_map:
                pv_map = self._custom_pv_map
            elif inst in INSTRUMENT_CONFIGS:
                pv_map = INSTRUMENT_CONFIGS[inst]["epics"]
            if pv_map is None:
                QMessageBox.warning(
                    self, "No PV Map",
                    f"No EPICS PV configuration for instrument '{inst}'.\n"
                    "Use 'Custom Device Config…' to define PV names.",
                )
                return
            p = self._get_params()
            try:
                import datetime
                from pynika.io.pv_io import write_calibration_to_pvs
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                filename = os.path.basename(
                    self._params.get("hdf5_path", "unknown")
                )
                report_msg = f"pyNika OK using {filename} at {ts}"
                results = write_calibration_to_pvs(
                    pv_map,
                    p["sdd"], p["bcx"], p["bcy"], p["tilt_x"], p["tilt_y"],
                    report_message=report_msg,
                )
                n_ok = sum(results.values())
                n_total = len(results)
                self.statusBar().showMessage(
                    f"PV write: {n_ok}/{n_total} successful"
                )
                QMessageBox.information(
                    self, "PV Write",
                    f"{n_ok}/{n_total} PVs written successfully.",
                )
            except Exception as exc:
                self.statusBar().showMessage(f"PV write failed: {exc}")
                QMessageBox.warning(self, "PV Write Failed", str(exc))

        # 6.17 — Export JSON
        def _on_export_json(self) -> None:
            import json
            # Default filename derived from detected instrument
            inst_raw = (self._params or {}).get("instrument", "custom").lower()
            inst_tag = inst_raw if inst_raw in ("saxs", "waxs") else "custom"
            default_name = f"{inst_tag}_pynika_parameters.json"
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Parameters", default_name,
                "JSON files (*.json);;All files (*.*)",
            )
            if not path:
                return
            p = self._get_params()
            data: dict = dict(p)
            try:
                data["wavelength"] = float(self._wl_edit.text())
                data["pixel_size"] = float(self._pix_edit.text())
            except ValueError:
                pass
            if self._params:
                data["instrument"] = self._params.get("instrument", "unknown")
            data["calibrant"] = (
                self._cal_combo.currentText() if self._calibrant else "AgBehenate"
            )
            if self._calibrant and self._d_rows:
                data["use_flags"] = [
                    use_cb.isChecked() for use_cb, _ in self._d_rows
                ]
                data["search_widths"] = [
                    float(w_spin.value()) for _, w_spin in self._d_rows
                ]
                # For Custom calibrant also export the d-spacings themselves
                if self._d_value_spins:
                    data["d_spacings"] = [
                        float(s.value()) for s in self._d_value_spins
                    ]
            try:
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                self.statusBar().showMessage(
                    f"Parameters exported to {os.path.basename(path)}"
                )
            except Exception as exc:
                QMessageBox.warning(self, "Export Failed", str(exc))

        # 6.17 — Import JSON
        def _on_import_json(self) -> None:
            import json
            path, _ = QFileDialog.getOpenFileName(
                self, "Import Parameters", "",
                "JSON files (*.json);;All files (*.*)",
            )
            if not path:
                return
            try:
                with open(path) as f:
                    data = json.load(f)
            except Exception as exc:
                QMessageBox.warning(self, "Import Failed", str(exc))
                return

            # Warn on wavelength mismatch if a file is already loaded
            if self._params:
                try:
                    wl_file = float(self._wl_edit.text())
                    wl_json = float(data.get("wavelength", wl_file))
                    if abs(wl_file - wl_json) > 1e-5:
                        reply = QMessageBox.question(
                            self, "Wavelength Mismatch",
                            f"Loaded file wavelength : {wl_file:.5f} Å\n"
                            f"JSON wavelength        : {wl_json:.5f} Å\n\n"
                            "Import geometry parameters anyway?",
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                        )
                        if reply != QMessageBox.StandardButton.Yes:
                            return
                except ValueError:
                    pass

            # Apply geometry parameters
            for i, key in enumerate(_PARAM_KEYS):
                if key in data:
                    spin = self._fit_value_spins[i]
                    spin.blockSignals(True)
                    spin.setValue(float(data[key]))
                    spin.blockSignals(False)

            # Apply calibrant (this repopulates _d_rows)
            if "calibrant" in data:
                self._cal_combo.setCurrentText(data["calibrant"])

            # Apply per-ring use/width (after _d_rows is repopulated)
            if "use_flags" in data:
                for i, (use_cb, _) in enumerate(self._d_rows):
                    if i < len(data["use_flags"]):
                        use_cb.setChecked(bool(data["use_flags"][i]))
            if "search_widths" in data:
                for i, (_, w_spin) in enumerate(self._d_rows):
                    if i < len(data["search_widths"]):
                        w_spin.setValue(float(data["search_widths"][i]))
            # For Custom calibrant restore the d-spacings (populated after setCurrentText above)
            if "d_spacings" in data and self._d_value_spins:
                for i, d_spin in enumerate(self._d_value_spins):
                    if i < len(data["d_spacings"]):
                        d_spin.setValue(float(data["d_spacings"][i]))

            self._update_overlays()
            self.statusBar().showMessage(
                f"Parameters imported from {os.path.basename(path)}"
            )

        # 6.18 — Custom device configuration dialog
        def _on_custom_config(self) -> None:
            inst = (self._params or {}).get("instrument", "SAXS")
            from pynika._instrument_configs import INSTRUMENT_CONFIGS

            # Start from existing custom map, then instrument default, then empty
            if hasattr(self, "_custom_pv_map") and self._custom_pv_map:
                current_pv = dict(self._custom_pv_map)
            elif inst in INSTRUMENT_CONFIGS:
                current_pv = dict(INSTRUMENT_CONFIGS[inst]["epics"])
            else:
                current_pv = {
                    "bcx": "", "bcy": "",
                    "tilt_x": "", "tilt_y": "",
                    "sdd": "", "report": "",
                }

            dlg = QDialog(self)
            dlg.setWindowTitle("Custom Device Configuration")
            dlg.setMinimumWidth(720)
            v = QVBoxLayout(dlg)

            # EPICS PV fields
            pv_group = QGroupBox("EPICS PV Names")
            form = QFormLayout(pv_group)
            pv_labels = {
                "bcx":    "Beam center X",
                "bcy":    "Beam center Y",
                "tilt_x": "Tilt X (°)",
                "tilt_y": "Tilt Y (°)",
                "sdd":    "SDD (mm)",
                "report": "Calibration report string",
            }
            pv_fields: dict[str, QLineEdit] = {}
            for key, label in pv_labels.items():
                edit = QLineEdit(current_pv.get(key, ""))
                edit.setMinimumWidth(500)
                form.addRow(f"{label}:", edit)
                pv_fields[key] = edit
            v.addWidget(pv_group)

            # Reset-to-defaults button
            def _reset_to_defaults() -> None:
                if inst in INSTRUMENT_CONFIGS:
                    dflt = INSTRUMENT_CONFIGS[inst]["epics"]
                    for k, edit in pv_fields.items():
                        edit.setText(dflt.get(k, ""))

            reset_btn = QPushButton(f"Reset to {inst} defaults")
            reset_btn.clicked.connect(_reset_to_defaults)
            v.addWidget(reset_btn)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            v.addWidget(buttons)

            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._custom_pv_map = {
                    key: edit.text().strip()
                    for key, edit in pv_fields.items()
                }
                self.statusBar().showMessage(
                    "Custom PV configuration saved — will be used by 'Save to PVs'."
                )

        # ..........................................
        # 6.5 — Image panel (right side)
        # ..........................................

        def _build_image_panel(self, splitter: QSplitter) -> None:
            right_widget = QWidget()
            v = QVBoxLayout(right_widget)
            v.setContentsMargins(0, 0, 0, 0)

            self._gview = pg.GraphicsLayoutWidget()
            # Light (white) background instead of the default black
            self._gview.setBackground("w")

            self._plot = self._gview.addPlot(row=0, col=0)
            self._plot.setAspectLocked(True)   # 1:1 pixel ratio
            self._plot.invertY(True)   # row 0 at top (standard image convention)
            self._plot.setLabel("bottom", "Column (px)")
            self._plot.setLabel("left", "Row (px)")

            # 2-D image item
            self._img_item = pg.ImageItem()
            self._plot.addItem(self._img_item)

            # HistogramLUT — provides intensity range slider + gradient colour-table editor
            self._lut = pg.HistogramLUTItem()
            self._lut.setImageItem(self._img_item)
            self._gview.addItem(self._lut, row=0, col=1)
            # Start with terrain-like colour map if available, fallback to viridis
            for _cmap_name in ("CET-L17", "terrain", "viridis", "grey"):
                try:
                    _cmap = pg.colormap.get(_cmap_name)
                    self._lut.gradient.setColorMap(_cmap)
                    break
                except Exception:
                    continue

            # 6.11 — beam-center crosshair (red "+" scatter symbol)
            self._bc_dot = pg.ScatterPlotItem(
                size=14,
                pen=pg.mkPen("r", width=2),
                brush=pg.mkBrush(None),
                symbol="+",
            )
            self._plot.addItem(self._bc_dot)

            # Right-click context menu additions (colour table + save JPG)
            self._plot.getViewBox().menu.addSeparator()
            _save_jpg_action = self._plot.getViewBox().menu.addAction("Save image as JPG…")
            _save_jpg_action.triggered.connect(self._on_save_image_jpg)
            _cmap_menu = self._plot.getViewBox().menu.addMenu("Color table")
            for _name in ("viridis", "plasma", "inferno", "magma", "hot",
                          "grey", "CET-L17", "CET-L16", "CET-R4",
                          "terrain", "bwr", "hsv"):
                def _make_cmap_setter(n):
                    def _set():
                        try:
                            _c = pg.colormap.get(n)
                            self._lut.gradient.setColorMap(_c)
                        except Exception as _e:
                            self.statusBar().showMessage(f"Color map '{n}' not available: {_e}")
                    return _set
                _act = _cmap_menu.addAction(_name)
                _act.triggered.connect(_make_cmap_setter(_name))

            v.addWidget(self._gview)
            splitter.addWidget(right_widget)

        def _on_save_image_jpg(self) -> None:
            """Save the current image (with overlays) as a JPG file."""
            from PyQt6.QtWidgets import QFileDialog
            import datetime
            default_name = (
                "pynika_image_"
                + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".jpg"
            )
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Image as JPG", default_name,
                "JPEG files (*.jpg *.jpeg);;All files (*.*)",
            )
            if not path:
                return
            try:
                pixmap = self._gview.grab()
                ok = pixmap.save(path, "JPEG", quality=95)
                if ok:
                    self.statusBar().showMessage(f"Image saved to {path}")
                else:
                    self.statusBar().showMessage("JPG save failed.")
            except Exception as exc:
                self.statusBar().showMessage(f"JPG save error: {exc}")

        # -------------------------------------------------------------------
        # Slots / event handlers
        # -------------------------------------------------------------------

        def _on_select_file(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open HDF5 Calibrant File",
                "",
                "HDF5 files (*.hdf *.h5 *.hdf5);;All files (*.*)",
            )
            if path:
                self._load_file(path)

        def _load_file(self, path: str) -> None:
            from pynika.io.hdf5_io import load_image_and_params
            try:
                self._params = load_image_and_params(path)
            except Exception as exc:
                log.error("Failed to load %s: %s", path, exc)
                self.statusBar().showMessage(f"Error loading file: {exc}")
                self._file_label.setText(f"Error: {exc}")
                return

            self._image = self._params["image"]

            # Compact path display (last 3 components)
            parts = path.replace("\\", "/").split("/")
            short = "/".join(parts[-3:]) if len(parts) > 3 else path
            self._file_label.setText(short)

            # Instrument parameters
            self._wl_edit.setText(f"{self._params['wavelength']:.5f}")
            self._pix_edit.setText(f"{self._params['pixel_size']:.4f}")
            inst = self._params.get("instrument", "unknown")
            self._inst_label.setText(inst)

            # Populate fit-parameter spinboxes with values from the file
            file_vals = [
                self._params["sdd"],
                self._params["bcx"],
                self._params["bcy"],
                self._params["tilt_x"],
                self._params["tilt_y"],
            ]
            for spin, val in zip(self._fit_value_spins, file_vals):
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)

            # Auto-select calibrant based on detected instrument
            if inst == "WAXS":
                self._cal_combo.setCurrentText("LaB6")
            else:
                self._cal_combo.setCurrentText("AgBehenate")

            self._update_image_display(reset_view=True)
            self._update_overlays()
            self.statusBar().showMessage(f"Loaded {inst}: {short}")

        # ..........................................
        # Image display (6.4 + 6.5)
        # ..........................................

        def _update_image_display(self, reset_view: bool = False) -> None:
            if self._image is None:
                return
            img = self._image.copy()
            # Clamp out-of-range pixels before display so they don't distort the scale
            img = np.where((img < 0) | (img > 1e8), 0.0, img)
            if self._log_cb.isChecked():
                img = np.log10(np.where(img > 0, img, 1.0))
            # pyqtgraph ImageItem first axis = x (columns), second = y (rows)
            # our image is (ny, nx) → transpose to (nx, ny)
            self._img_item.setImage(img.T, autoLevels=reset_view)
            if reset_view:
                # Zoom to show the image with a 20-pixel border on all sides.
                # Using the larger dimension for both axes keeps pixels square and
                # centres the shorter axis inside the grey-padded background.
                ny, nx = self._image.shape
                pad = 20
                L = max(ny, nx)
                self._plot.getViewBox().setRange(
                    xRange=[-pad, L + pad],
                    yRange=[-pad, L + pad],
                    padding=0,
                )

        # ..........................................
        # Calibrant and d-spacing table (6.6 + 6.7)
        # ..........................................

        def _on_calibrant_changed(self, name: str) -> None:
            from pynika.calibrants import get_calibrant
            if name == "Custom":
                # Seed custom calibrant from LaB6 d-spacings as a sensible default
                base = get_calibrant("LaB6")
                base.name = "Custom"
                self._calibrant = base
            else:
                try:
                    self._calibrant = get_calibrant(name)
                except KeyError:
                    return
            self._populate_d_table()
            self._update_overlays()

        def _populate_d_table(self) -> None:
            if self._calibrant is None:
                return
            cal = self._calibrant
            is_custom = (cal.name == "Custom")
            n = len(cal.d_spacings)
            # Reset to 0 first so existing cell widgets are properly removed
            self._d_table.setRowCount(0)
            self._d_table.setRowCount(n)
            self._d_rows.clear()
            self._d_value_spins = []

            for i, (d, use, w) in enumerate(
                zip(cal.d_spacings, cal.use_flags, cal.search_widths)
            ):
                # Col 0 — Use checkbox (centred)
                use_cb = QCheckBox()
                use_cb.setChecked(use)
                c0 = QWidget()
                h0 = QHBoxLayout(c0)
                h0.addWidget(use_cb)
                h0.setAlignment(Qt.AlignmentFlag.AlignCenter)
                h0.setContentsMargins(0, 0, 0, 0)
                use_cb.toggled.connect(self._update_overlays)
                self._d_table.setCellWidget(i, 0, c0)

                # Col 1 — d value: editable spinbox for Custom, read-only text otherwise
                if is_custom:
                    d_spin = QDoubleSpinBox()
                    d_spin.setRange(0.001, 10000.0)
                    d_spin.setDecimals(5)
                    d_spin.setValue(d)
                    d_spin.setSingleStep(0.01)
                    d_spin.setToolTip("Enter d-spacing in Ångströms")
                    d_spin.valueChanged.connect(self._update_overlays)
                    self._d_table.setCellWidget(i, 1, d_spin)
                    self._d_value_spins.append(d_spin)
                else:
                    d_item = QTableWidgetItem(f"{d:.5f}")
                    d_item.setFlags(d_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self._d_table.setItem(i, 1, d_item)

                # Col 2 — search width spinbox
                w_spin = QDoubleSpinBox()
                w_spin.setRange(1, 500)
                w_spin.setValue(w)
                w_spin.setSingleStep(5.0)
                w_spin.setDecimals(0)
                w_spin.valueChanged.connect(self._update_overlays)
                self._d_table.setCellWidget(i, 2, w_spin)

                self._d_rows.append((use_cb, w_spin))

        def _on_set_all_widths(self) -> None:
            w = self._width_all_spin.value()
            for _, w_spin in self._d_rows:
                w_spin.blockSignals(True)
                w_spin.setValue(w)
                w_spin.blockSignals(False)
            self._update_overlays()

        # ..........................................
        # Parameter changes (6.9)
        # ..........................................

        def _on_params_changed(self) -> None:
            self._update_overlays()

        def _on_no_limits_changed(self, checked: bool) -> None:
            """6.10 — hide or show the Low/High columns in the fit table."""
            self._fit_table.setColumnHidden(3, checked)
            self._fit_table.setColumnHidden(4, checked)

        def _get_params(self) -> dict:
            """Read current geometry parameter values from the fit-table spinboxes."""
            return {k: self._fit_value_spins[i].value()
                    for i, k in enumerate(_PARAM_KEYS)}

        # ..........................................
        # Overlays (6.11 + 6.12)
        # ..........................................

        def _update_overlays(self) -> None:
            """Redraw beam-center dot and ring/band overlays from current parameters."""
            # Always remove stale overlay items first
            for item in self._ring_items + self._band_items:
                self._plot.removeItem(item)
            self._ring_items.clear()
            self._band_items.clear()

            if self._image is None or self._params is None:
                return

            p = self._get_params()

            # 6.11 — beam-center crosshair
            self._bc_dot.setData([p["bcx"]], [p["bcy"]])

            if self._calibrant is None:
                return

            wl  = self._params["wavelength"]
            pix = self._params["pixel_size"]

            from pynika.geometry import ring_xy_tilted

            for i, (use_cb, w_spin) in enumerate(self._d_rows):
                if not use_cb.isChecked():
                    continue

                # For Custom calibrant read d from the editable spinboxes
                if self._d_value_spins and i < len(self._d_value_spins):
                    d = float(self._d_value_spins[i].value())
                else:
                    d = self._calibrant.d_spacings[i]
                w = w_spin.value()

                # 6.12a — red curve: full tilted-model ring
                x_ring, y_ring = ring_xy_tilted(
                    d, wl,
                    p["bcx"], p["bcy"],
                    p["sdd"], pix,
                    p["tilt_x"], p["tilt_y"],
                )
                if len(x_ring) >= 3:
                    ring_item = pg.PlotDataItem(
                        x_ring, y_ring,
                        pen=pg.mkPen("r", width=1.5),
                        connect="finite",
                    )
                    self._plot.addItem(ring_item)
                    self._ring_items.append(ring_item)

                # 6.12b — yellow dashed bands: ±search width following the tilted ring
                # Use the tilted-model ring to get the correct radial distance at each
                # azimuthal angle, then offset ±W pixels along that radial direction.
                if len(x_ring) >= 3:
                    angles = np.linspace(0.0, 2.0 * np.pi, len(x_ring), endpoint=False)
                    cos_a = np.cos(angles)
                    sin_a = np.sin(angles)
                    dx = x_ring - p["bcx"]
                    dy = y_ring - p["bcy"]
                    r_tilted = np.where(
                        np.isfinite(dx) & np.isfinite(dy),
                        np.sqrt(dx**2 + dy**2),
                        np.nan,
                    )
                    for sign in (-1.0, +1.0):
                        r_band = r_tilted + sign * w
                        xb = np.where(r_band > 0, p["bcx"] + r_band * cos_a, np.nan)
                        yb = np.where(r_band > 0, p["bcy"] + r_band * sin_a, np.nan)
                        band_item = pg.PlotDataItem(
                            xb, yb,
                            pen=pg.mkPen(
                                "y", width=1.0,
                                style=Qt.PenStyle.DashLine,
                            ),
                            connect="finite",
                        )
                        self._plot.addItem(band_item)
                        self._band_items.append(band_item)

        # ..........................................
        # 6.13 + 6.14 — Run Fit section
        # ..........................................

        def _build_run_section(self, layout: QVBoxLayout) -> None:
            grp = QGroupBox("Optimisation")
            v = QVBoxLayout(grp)

            # Row 1 — azimuthal step + strip half-width on same line
            row_controls = QHBoxLayout()
            row_controls.addWidget(QLabel("Az. step (°):"))
            self._step_spin = QDoubleSpinBox()
            self._step_spin.setRange(0.1, 90.0)
            self._step_spin.setValue(1.0)
            self._step_spin.setSingleStep(0.5)
            self._step_spin.setDecimals(1)
            self._step_spin.setMaximumWidth(60)
            self._step_spin.setToolTip(
                "Angular step between radial line profiles.\n"
                "Smaller = more peaks found but slower.\n"
                "1° gives 360 directions per ring."
            )
            row_controls.addWidget(self._step_spin)
            row_controls.addSpacing(8)
            row_controls.addWidget(QLabel("Strip ½-W (px):"))
            self._transverse_spin = QDoubleSpinBox()
            self._transverse_spin.setRange(1.0, 50.0)
            self._transverse_spin.setValue(5.0)
            self._transverse_spin.setSingleStep(0.5)
            self._transverse_spin.setDecimals(1)
            self._transverse_spin.setMaximumWidth(60)
            self._transverse_spin.setToolTip(
                "Half-width of the averaging strip perpendicular\n"
                "to the radial direction for each peak profile.\n"
                "Wider = smoother profile but less spatial resolution."
            )
            row_controls.addWidget(self._transverse_spin)
            row_controls.addStretch()
            v.addLayout(row_controls)

            # Row 2 — Auto Fit / Run Fit / Revert buttons
            btn_row = QHBoxLayout()
            self._auto_fit_btn = QPushButton("Auto Fit")
            self._auto_fit_btn.setToolTip(
                "Multi-stage automatic fit:\n"
                "Stage 1 — first 2 rings, SDD+BCx+BCy only (abort if chi²≥5)\n"
                "Stage 2 — all rings, all parameters (done if chi²<0.2)\n"
                "Stage 3 — refinement pass (chi²<1 = success)"
            )
            self._auto_fit_btn.clicked.connect(self._on_auto_fit)
            btn_row.addWidget(self._auto_fit_btn)
            self._run_btn = QPushButton("Run Fit")
            self._run_btn.clicked.connect(self._on_run_fit)
            btn_row.addWidget(self._run_btn)
            self._revert_btn = QPushButton("Revert")
            self._revert_btn.setEnabled(False)
            self._revert_btn.setToolTip("Restore parameters to values before last fit")
            self._revert_btn.clicked.connect(self._on_revert)
            btn_row.addWidget(self._revert_btn)
            v.addLayout(btn_row)

            self._progress_bar = QProgressBar()
            self._progress_bar.setRange(0, 1)
            self._progress_bar.setValue(0)
            v.addWidget(self._progress_bar)

            # Row 3 — chi² and status on the same line (6.14)
            row_result = QHBoxLayout()
            self._chi2_label = QLabel("χ²/dof: —")
            row_result.addWidget(self._chi2_label)
            row_result.addSpacing(8)
            self._fit_status_label = QLabel("Status: idle")
            self._fit_status_label.setWordWrap(False)
            row_result.addWidget(self._fit_status_label, stretch=1)
            v.addLayout(row_result)

            layout.addWidget(grp)

        def _get_calibrant_from_ui(self):
            """Return a calibrant with Use/Width (and for Custom, d) values from the table."""
            from pynika.calibrants import get_calibrant, Calibrant
            # Custom calibrant: build entirely from the editable table values
            if (self._calibrant is not None and self._calibrant.name == "Custom"
                    and self._d_value_spins):
                d_spacings    = [float(s.value()) for s in self._d_value_spins]
                use_flags     = [use_cb.isChecked() for use_cb, _ in self._d_rows]
                search_widths = [float(w_spin.value()) for _, w_spin in self._d_rows]
                return Calibrant(
                    name="Custom",
                    d_spacings=d_spacings,
                    use_flags=use_flags,
                    search_widths=search_widths,
                )
            cal = get_calibrant(self._calibrant.name)
            for i, (use_cb, w_spin) in enumerate(self._d_rows):
                cal.use_flags[i] = use_cb.isChecked()
                cal.search_widths[i] = float(w_spin.value())
            return cal

        def _get_fit_config(self):
            """Build a FitConfig from the current UI state."""
            from pynika.fitting.optimizer import FitConfig
            cfg = FitConfig()
            cfg.step_deg = float(self._step_spin.value())
            cfg.transverse_px = float(self._transverse_spin.value())
            for i, key in enumerate(_PARAM_KEYS):
                flag = self._fit_checkboxes[i].isChecked()
                if key == "sdd":    cfg.fit_sdd    = flag
                elif key == "bcx":  cfg.fit_bcx    = flag
                elif key == "bcy":  cfg.fit_bcy    = flag
                elif key == "tilt_x": cfg.fit_tilt_x = flag
                elif key == "tilt_y": cfg.fit_tilt_y = flag

            if not self._no_limits_cb.isChecked():
                def _parse(edit, fallback):
                    try: return float(edit.text())
                    except ValueError: return fallback

                lo = [_parse(e, -1e10) for e in self._fit_low_edits]
                hi = [_parse(e,  1e10) for e in self._fit_high_edits]
                cfg.sdd_limits    = (lo[0], hi[0])
                cfg.bcx_limits    = (lo[1], hi[1])
                cfg.bcy_limits    = (lo[2], hi[2])
                cfg.tilt_x_limits = (lo[3], hi[3])
                cfg.tilt_y_limits = (lo[4], hi[4])
            return cfg

        def _on_run_fit(self) -> None:
            if self._image is None:
                self.statusBar().showMessage("Load a file first.")
                return
            if self._calibrant is None:
                self.statusBar().showMessage("Select a calibrant first.")
                return

            cal = self._get_calibrant_from_ui()
            if not any(cal.use_flags):
                self.statusBar().showMessage("Enable at least one d-spacing ring.")
                return

            p = self._get_params()
            cfg = self._get_fit_config()

            from pynika.io.hdf5_io import make_mask
            inst = self._params.get("instrument", "SAXS")
            mask = make_mask(self._image, inst)

            try:
                wl  = float(self._wl_edit.text())
                pix = float(self._pix_edit.text())
            except ValueError:
                self.statusBar().showMessage("Invalid wavelength or pixel size.")
                return

            # Save current params so user can revert if fit diverges
            self._pre_fit_params = self._get_params()
            self._revert_btn.setEnabled(False)

            n_rings = sum(cal.use_flags)
            self._progress_bar.setRange(0, max(1, n_rings))
            self._progress_bar.setValue(0)
            self._fit_status_label.setText("Scanning rings…")
            self._chi2_label.setText("χ²/dof: —")
            self._run_btn.setEnabled(False)
            self._auto_fit_btn.setEnabled(False)

            self._fit_worker = FitWorker(
                self._image, mask, cal, wl, pix,
                p["sdd"], p["bcx"], p["bcy"], p["tilt_x"], p["tilt_y"],
                cfg,
            )
            self._fit_thread = QThread()
            self._fit_worker.moveToThread(self._fit_thread)

            self._fit_thread.started.connect(self._fit_worker.run)
            self._fit_worker.progress.connect(self._on_fit_progress)
            self._fit_worker.finished.connect(self._on_fit_finished)
            self._fit_worker.finished.connect(self._fit_thread.quit)
            self._fit_thread.finished.connect(
                lambda: (self._run_btn.setEnabled(True), self._auto_fit_btn.setEnabled(True))
            )

            self._fit_thread.start()

        def _on_revert(self) -> None:
            """Restore the parameter spinboxes to their pre-fit values."""
            if not hasattr(self, "_pre_fit_params"):
                return
            for i, k in enumerate(_PARAM_KEYS):
                spin = self._fit_value_spins[i]
                spin.blockSignals(True)
                spin.setValue(self._pre_fit_params[k])
                spin.blockSignals(False)
            self._update_overlays()
            self.statusBar().showMessage("Reverted to pre-fit parameters.")

        def _on_auto_fit(self) -> None:
            """Launch the multi-stage Auto Fit procedure in a background thread."""
            if self._image is None:
                self.statusBar().showMessage("Load a file first.")
                return
            if self._calibrant is None:
                self.statusBar().showMessage("Select a calibrant first.")
                return

            cal = self._get_calibrant_from_ui()
            if not any(cal.use_flags):
                self.statusBar().showMessage("Enable at least one d-spacing ring.")
                return

            cfg = self._get_fit_config()

            from pynika.io.hdf5_io import make_mask
            inst = self._params.get("instrument", "SAXS")
            mask = make_mask(self._image, inst)

            try:
                wl  = float(self._wl_edit.text())
                pix = float(self._pix_edit.text())
            except ValueError:
                self.statusBar().showMessage("Invalid wavelength or pixel size.")
                return

            # Save current params so user can revert to pre-Auto-Fit state
            self._pre_fit_params = self._get_params()
            self._revert_btn.setEnabled(False)

            p = self._get_params()

            self._progress_bar.setRange(0, 3)
            self._progress_bar.setValue(0)
            self._fit_status_label.setText("Auto Fit Stage 1…")
            self._chi2_label.setText("χ²/dof: —")
            self._run_btn.setEnabled(False)
            self._auto_fit_btn.setEnabled(False)

            self._auto_fit_worker = AutoFitWorker(
                self._image, mask, cal, wl, pix,
                p["sdd"], p["bcx"], p["bcy"], p["tilt_x"], p["tilt_y"],
                cfg,
            )
            self._auto_fit_thread = QThread()
            self._auto_fit_worker.moveToThread(self._auto_fit_thread)

            self._auto_fit_thread.started.connect(self._auto_fit_worker.run)
            self._auto_fit_worker.stage_update.connect(self._on_auto_fit_progress)
            self._auto_fit_worker.finished.connect(self._on_auto_fit_finished)
            self._auto_fit_worker.finished.connect(self._auto_fit_thread.quit)
            self._auto_fit_thread.finished.connect(self._on_auto_fit_thread_done)

            self._auto_fit_thread.start()

        def _on_auto_fit_thread_done(self) -> None:
            self._run_btn.setEnabled(True)
            self._auto_fit_btn.setEnabled(True)

        def _on_auto_fit_progress(self, message: str, stage: int) -> None:
            self._progress_bar.setValue(stage - 1)
            self._fit_status_label.setText(message)

        def _on_auto_fit_finished(self, result, message: str) -> None:
            self._progress_bar.setValue(3)
            self._revert_btn.setEnabled(True)

            if result is None or result.n_peaks_used == 0:
                self._chi2_label.setText("χ²/dof: —")
                self._fit_status_label.setText(f"Auto Fit FAILED: {message}")
                self.statusBar().showMessage(f"Auto Fit failed: {message}")
                return

            chi2_val = result.chi_square
            chi2_str = f"{chi2_val:.4f}" if np.isfinite(chi2_val) else "—"
            self._chi2_label.setText(f"χ²/dof: {chi2_str}")

            # Update spinboxes with result values regardless of success
            fit_vals = [result.sdd, result.bcx, result.bcy, result.tilt_x, result.tilt_y]
            for spin, val in zip(self._fit_value_spins, fit_vals):
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)
            self._update_overlays()

            if result.success:
                self._fit_status_label.setText(
                    f"Auto Fit OK — {result.n_peaks_used} peaks | {message}"
                )
                self.statusBar().showMessage(
                    f"Auto Fit converged: χ²/dof={chi2_str}, {result.n_peaks_used} peaks"
                )
            else:
                self._fit_status_label.setText(f"Auto Fit FAILED — {message}")
                self.statusBar().showMessage(f"Auto Fit failed: {message}")

        def _on_fit_progress(self, ring_i: int, n_rings: int) -> None:
            self._progress_bar.setValue(ring_i + 1)
            self._fit_status_label.setText(
                f"Scanning ring {ring_i + 1}/{n_rings}…"
            )

        def _on_fit_finished(self, result) -> None:
            self._progress_bar.setValue(self._progress_bar.maximum())
            self._revert_btn.setEnabled(True)

            if result.success:
                self._chi2_label.setText(f"χ²/dof: {result.chi_square:.4f}")
                self._fit_status_label.setText(
                    f"Converged — {result.n_peaks_used} peaks used"
                )
                # Update parameter spinboxes with optimised values
                fit_vals = [
                    result.sdd, result.bcx, result.bcy,
                    result.tilt_x, result.tilt_y,
                ]
                for spin, val in zip(self._fit_value_spins, fit_vals):
                    spin.blockSignals(True)
                    spin.setValue(val)
                    spin.blockSignals(False)
                self._update_overlays()
                self.statusBar().showMessage(
                    f"Fit converged: χ²/dof={result.chi_square:.4f}, "
                    f"{result.n_peaks_used} peaks"
                )
            else:
                self._chi2_label.setText("χ²/dof: —")
                self._fit_status_label.setText(f"FAILED — {result.message}")
                self.statusBar().showMessage(f"Fit failed: {result.message}")

    # -----------------------------------------------------------------------
    # Application entry
    # -----------------------------------------------------------------------
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
