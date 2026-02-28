# Changelog

All notable changes to pyNika will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0] — 2026-02-28

### Phase 7 — Validation and release

- **Validated** against Igor Pro Nika code on real calibrant measurements (SAXS
  AgBehenate and WAXS LaB6 files). Calibrated parameters (SDD, BCx, BCy, TiltX,
  TiltY) match Nika output to within sub-pixel / sub-micron accuracy.
- **CLI** (`pynika --file … --auto-fit`) confirmed working end-to-end on
  beamline HDF5 files.
- **Python API** (`Calibrator`, `auto_calibrate()`) confirmed working via
  `scripts/batch_check.py` batch-processing script.

### Changed

- χ²/dof success threshold changed from 1.0 → **3.0** throughout
  (`optimizer.py`, `calibrator.py`, `main_window.py`) based on empirical
  testing; chi²<3 reliably indicates a good calibration.
- `log.warning` for rings outside the detector ("0 peaks") demoted to
  `log.debug`; these are expected when some d-spacing rings fall outside the
  active detector area.
- Version set to **1.0.0**; Development Status classifier changed to
  `Production/Stable`.

### Added (GUI)

- **Custom calibrant** table now fully resets (d-spacings and editability) when
  switching from Custom back to AgBehenate or LaB6.
- **Export / Import JSON** now round-trips d-spacing values for Custom
  calibrant in addition to `use_flags` and `search_widths`.
- **Instrument Parameters** group label updated; wavelength and pixel-size
  fields now have tooltips indicating they are editable to override
  file-derived values.

### Added (documentation)

- `docs/installation.md` — pip-from-GitHub, conda, optional extras, beamline
  checklist, how to add pynika as a dependency in another package.
- `docs/gui_usage.md` — full GUI reference: layout, calibrant table,
  d-spacing table, fit-parameters table, image controls, Export/Import JSON
  content description.
- `docs/cli_usage.md` — CLI option reference, auto-fit stage table, batch
  processing with `scripts/batch_check.py`.
- `docs/python_api.md` — `Calibrator`, `CalibrationResult`, `FitConfig`,
  low-level API, importability from GitHub in other packages.
- `scripts/batch_check.py` — moved from repository root to `scripts/`; serves
  as working example for batch Python-API use.

---

## [0.1.0-dev] — Phase 1–6 complete (2026-02)

### Phase 1 — HDF5 I/O
- `pynika/io/hdf5_io.py`: `load_image_and_params()` auto-detects SAXS vs WAXS
  from Metadata PV key prefix (`pin_ccd_*` vs `waxs_ccd_*`).
- `make_mask()`: dead-pixel/dead-band masking for Eiger (SAXS) and Pilatus (WAXS).
- `save_params_to_hdf5()`: write calibration results back to the source file.
- Image is transposed on load from HDF5 (nx, ny) → numpy (ny, nx) convention.

### Phase 2 — Geometry model
- `pynika/geometry.py`: `build_rotation_matrix()` — Rodrigues rotation port from
  Nika's `NI2T_DetectorUpdateCalc`.
- `expected_pixel_position()`: tilt-aware (BCx, BCy, SDD, TiltX, TiltY) → (x, y)
  in pixel coordinates for a given d-spacing and azimuthal angle.
- `d_to_pixel_radius()` / `pixel_to_d()`: untilted convenience conversions.
- `ring_xy_tilted()`: vectorised full-ring point cloud for overlay rendering.
- `radial_profile_at_angle()`: vectorised pixel averaging along a radial strip
  (explicit sum/count, no `nanmean`, no Python inner loops).

### Phase 3 — Gaussian ring fitting
- `pynika/fitting/optimizer.py`: `fit_gaussian_linear()` — Gaussian + linear
  background via `scipy.optimize.curve_fit`; initial µ₀ = strip midpoint
  (robust against noise spikes).
- `find_ring_peaks()`: azimuthal sweep over all enabled d-spacings; 4-corner
  bounds check skips strips that fall outside the detector; outlier rejection
  using 3 × MAD.

### Phase 4 — Geometry optimisation
- `optimise_geometry()`: `scipy.optimize.least_squares` (TRF) over free
  parameters (SDD, BCx, BCy, TiltX, TiltY).
- Residual vector: 2 components (Δx, Δy) per peak in absolute pixel coordinates —
  fixes divergence when BCx/BCy are simultaneously free.
- Tolerances `ftol=xtol=gtol=1e-4` (adequate for sub-pixel calibration accuracy).
- `OptimisationResult` dataclass: fitted params, χ²/dof, peak list, success flag.

### Phase 5 — CLI and EPICS I/O
- `pynika/calibrator.py`: `Calibrator.calibrate()` orchestrates Phases 1–4.
- `pynika/io/pv_io.py`: `write_calibration_to_pvs()` with graceful degradation
  when pyepics is absent or PVs are unreachable (prints to console, no exception).
- `pynika/cli.py`: argparse entry point (`pynika` command).

### Phase 6 — Qt6 GUI (`pynika/gui/main_window.py`)
- Two-pane `QMainWindow` (left scroll panel + right pyqtgraph image view).
- File selector (`QFileDialog`), log-intensity toggle (default ON, retains view
  on toggle), viridis colour map, 1:1 aspect lock with grey padding.
- Calibrant combo (AgBehenate / LaB6) with live d-spacing table (Use ☐, d, ±W).
- Fit-parameters table (SDD, BCx, BCy, TiltX, TiltY): value spinbox, Fit ☐,
  Low/High bounds; "No limits" checkbox hides bound columns.
- Ring overlays: red tilted-model curve + yellow dashed ±search band, redrawn
  on every parameter change.
- Beam-center crosshair overlay (red + scatter item).
- Background QThread worker (`FitWorker`) keeps the GUI responsive during fitting;
  progress bar updated per ring.
- χ²/dof and status labels; Revert button restores pre-fit parameters.
- Azimuthal step (°) and strip half-width (px) spinboxes in Optimisation group.
- Save to File: writes params back to the loaded HDF5 via `save_params_to_hdf5`.
- Save to PVs: writes to EPICS PVs with report message
  "pyNika OK using <filename> at <datetime>".
- Export JSON / Import JSON: round-trip of all geometry params, calibrant,
  use_flags, search_widths; warns on wavelength mismatch at import.
- Custom Device Config dialog: editable EPICS PV names (720 px wide), reset-to-
  defaults button; stored values override built-in instrument config for PV writes.
- `launch_gui()` entry point; `pynika-gui` console script in `pyproject.toml`.

### Known limitations / open items (Phase 7–8 pending)
- Validation against known Nika output on real calibrant files not yet done
  (examples/SAXS.hdf and WAXS.hdf are sample data, not calibrant measurements).
- χ²/dof success threshold (currently 10) needs empirical tuning.
- Wavelength is held fixed; adding it as a free parameter is a future option.
- PyPI packaging (Phase 8) and CI/CD (Phase 7) not yet set up.
