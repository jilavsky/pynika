# Changelog

All notable changes to pyNika will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Initial repository scaffold (directories, packaging, documentation).
- Requirements specification and implementation plan in `doc/`.
- Package stub files for `pynika` core modules.

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
