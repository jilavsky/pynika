# pyNika — Implementation Plan

**Document type:** Feature implementation plan, ordered by priority and dependency.
**Date:** 2025

This document converts the requirements in [requirements_specification.md](requirements_specification.md) into a concrete, phased development plan.  Each phase produces a testable increment.

---

## Phase 0 — Repository Scaffold  ✅ (done)

| Task | Status | Files |
|------|--------|-------|
| Directory structure (package, tests, doc, examples) | Done | `pynika/`, `tests/`, `doc/` |
| `pyproject.toml` + `environment.yml` (Conda) | Done | root |
| `README.md`, `LICENSE`, `CHANGELOG.md`, `.gitignore` | Done | root |
| Package stub modules with docstrings | Done | `pynika/` subtree |
| Unit tests for calibrant data (verify d-spacings match Nika) | Done | `tests/test_calibrants.py` |

---

## Phase 1 — HDF5 I/O and Data Loading

**Goal:** Be able to read a SAXS or WAXS HDF5 file and extract the 2D image plus all geometry parameters into a Python dict.  Write calibration results back to the file.

### Features

| # | Feature | Module | Notes |
|---|---------|--------|-------|
| 1.1 | `load_image_and_params(hdf5_path)` | `pynika/io/hdf5_io.py` | Auto-detect SAXS vs WAXS from presence of `pin_ccd_tilt_x` vs `waxs_ccd_tilt_x` in `/entry/Metadata` |
| 1.2 | `save_params_to_hdf5(hdf5_path, ...)` | `pynika/io/hdf5_io.py` | Update instrument/detector dataset + metadata scalars |
| 1.3 | SAXS pixel mask generation | `pynika/io/hdf5_io.py` | Mask pixels < 0 + dead columns 0–3, 242–244 |
| 1.4 | WAXS pixel mask generation | `pynika/io/hdf5_io.py` | Mask pixels > 1e7 + dead columns 511–515, 1026–1040, 1551–1555 |
| 1.5 | Custom mask (user-defined rules from JSON) | `pynika/io/hdf5_io.py` | |
| 1.6 | Unit tests | `tests/test_hdf5_io.py` | Use example files from `examples/` |

### Implementation Notes

- Pixel mask is a `np.ndarray` of dtype `bool`, same shape as the image, where `True` = masked (excluded from fitting).
- Keep mask generation separate from image loading so the GUI can display the unmasked image.
- The masking conditions (threshold value, sign, column ranges) should come from the instrument configuration dict (`_instrument_configs.py`) so they are easy to override for Custom instruments.

---

## Phase 2 — Geometry Model

**Goal:** Implement the Nika pixel↔angle geometry model so the expected ring radius can be computed for any (d, BCx, BCy, SDD, TiltX, TiltY) combination.

### Features

| # | Feature | Module | Notes |
|---|---------|--------|-------|
| 2.1 | `d_to_pixel_radius(d, λ, SDD, pix_size)` | `pynika/geometry.py` | Stub already present; verify against Nika values |
| 2.2 | `pixel_to_d(r, λ, SDD, pix_size)` | `pynika/geometry.py` | Inverse — for diagnostics |
| 2.3 | Tilt-corrected radius at a given azimuthal angle | `pynika/geometry.py` | Port `NI1BC_FindTiltedPxPyValues` from `NI1_BeamCenterUtils.ipf` |
| 2.4 | Ellipse model: compute (x, y) on the ring for (angle, params) | `pynika/geometry.py` | Required for the optimisation residual |
| 2.5 | `ring_xy(bcx, bcy, radius_px, n_points)` — no-tilt display | `pynika/geometry.py` | Already present; extend for tilted case |
| 2.6 | Unit tests against Nika reference values | `tests/test_geometry.py` | Use known (BCx, BCy, SDD, tilt) → radius round-trip |

### Implementation Notes

- The Nika tilt model (`NI1BC_FindTiltedPxPyValues`, line 766 in `NI1_BeamCenterUtils.ipf`) computes the elliptical distortion of rings for a tilted flat detector.  Port this function faithfully; do not substitute with pyFAI's `rot1/rot2/rot3` parameterisation (different conventions).
- The untilted case (`r = SDD · tan(2θ) / pix_size`) is a special case and useful for testing.
- Provide a helper that, given a full set of geometry parameters and a list of (d, azimuth) pairs, returns a vector of expected pixel radii.  This vector is the model function for the optimiser.

---

## Phase 3 — Gaussian Ring Fitting

**Goal:** Locate diffraction ring positions in the 2D image by fitting Gaussians along radial strips.

### Features

| # | Feature | Module | Notes |
|---|---------|--------|-------|
| 3.1 | `radial_profile_at_angle(image, mask, bcx, bcy, angle, r_center, r_width, transverse_width)` | `pynika/geometry.py` | Stub present; implement averaging loop |
| 3.2 | `fit_gaussian_linear(x, y)` | `pynika/fitting/optimizer.py` | `scipy.optimize.curve_fit`; return None on failure |
| 3.3 | `find_ring_peaks(image, mask, bcx, bcy, d, λ, SDD, pix, search_width, config)` | `pynika/fitting/optimizer.py` | Loops over azimuthal angles; skips outside-detector and masked strips |
| 3.4 | Outside-detector check | within 3.3 | If any sample point in the radial strip falls outside image bounds → skip |
| 3.5 | Masked-pixel check | within 3.3 | If fraction of masked pixels in strip > threshold (e.g. 50%) → skip |
| 3.6 | Peak validity check | within 3.3 | Peak amplitude > noise floor; peak center inside search window |
| 3.7 | Unit tests | `tests/test_fitting.py` | Synthetic image with known ring positions |

### Implementation Notes

- **Fitting function:**
  `f(r) = A · exp(-½ · ((r − μ)/σ)²) + m · r + b`
  Parameters: amplitude A, center μ, width σ, slope m, intercept b.
  Use `scipy.optimize.curve_fit` with reasonable initial guesses (A = max − min, μ = position of max, σ = search_width / 4).

- **Initial guess for μ:** use the theoretical ring radius, not the position of the maximum, to avoid locking onto noise spikes.

- **Outlier rejection:** After collecting all peak positions for a given d-spacing, compute the median and reject peaks farther than 2×median-absolute-deviation from the median.  This guards against occasional false peaks.

- **Progress reporting:** The fitting loop over all rings and all angles can be slow.  Provide a callback (or tqdm progress bar) for the CLI.  The GUI will use a worker thread (see Phase 6).

---

## Phase 4 — Geometry Optimisation

**Goal:** Implement the least-squares optimiser that uses the collected ring peaks to refine (BCx, BCy, SDD, TiltX, TiltY).

### Features

| # | Feature | Module | Notes |
|---|---------|--------|-------|
| 4.1 | `optimise_geometry(image, mask, calibrant, λ, pix, sdd0, bcx0, bcy0, tx0, ty0, config)` | `pynika/fitting/optimizer.py` | Full orchestration |
| 4.2 | Residual function for `least_squares` | within 4.1 | Vector of (fitted_radius − model_radius) for each peak |
| 4.3 | Parameter vector encoding/decoding | within 4.1 | Only free parameters enter the solver; fixed ones are held constant |
| 4.4 | Bounds enforcement | within 4.1 | Pass bounds to `scipy.optimize.least_squares` |
| 4.5 | `OptimisationResult` dataclass | `pynika/fitting/optimizer.py` | Already defined; fill in |
| 4.6 | Fit success/failure classification | within 4.1 | See criteria in requirements §10 |
| 4.7 | Unit tests with synthetic data | `tests/test_optimizer.py` | Known geometry → perturb → recover |

### Implementation Notes

- Use `scipy.optimize.least_squares` with `method='trf'` (Trust Region Reflective) which natively supports bounds.
- The residual vector length is `n_rings × n_angles_with_found_peaks`.  A typical run has 10 rings × ~300 angles = ~3 000 residuals for 5 free parameters — well-conditioned.
- **Convergence check:**
  - `result.success` from `least_squares` must be True.
  - χ² / n_dof < configurable threshold (start with 10; tune empirically on real data).
  - Fraction of successful Gaussian fits > 50% of expected (n_rings × n_angles).
- **False convergence detection:** After optimisation, compute per-ring residuals.  If any ring's mean residual exceeds its search width, flag it.

---

## Phase 5 — CLI and EPICS I/O

**Goal:** Provide a working command-line tool and EPICS PV write capability.

### Features

| # | Feature | Module | Notes |
|---|---------|--------|-------|
| 5.1 | Complete `Calibrator.calibrate()` | `pynika/calibrator.py` | Calls Phases 1–4 |
| 5.2 | Complete `Calibrator.save_to_hdf5()` | `pynika/calibrator.py` | Calls Phase 1.2 |
| 5.3 | Complete `Calibrator.save_to_pvs()` | `pynika/calibrator.py` | Calls `pv_io.py` |
| 5.4 | `write_calibration_to_pvs()` | `pynika/io/pv_io.py` | Stub present; implement |
| 5.5 | `write_failure_report()` | `pynika/io/pv_io.py` | Write to CalibrationReport PV on failure |
| 5.6 | Graceful degradation when pyepics absent / PV unreachable | `pynika/io/pv_io.py` | Print to console; no exception |
| 5.7 | CLI argument parsing | `pynika/cli.py` | Stub present; wire to Calibrator |
| 5.8 | JSON export / import of instrument configuration | `pynika/calibrator.py` | Custom device save/load |
| 5.9 | Integration test: CLI round-trip on example files | `tests/test_cli.py` | |

### CalibrationReport PV message format

```
pyNika OK: SAXS calibrated 2025-03-01 14:23:05
  file: /data/SAXS.hdf
  SDD=1523.4 mm, BCx=512.3, BCy=480.1, TiltX=0.12, TiltY=-0.05
  chi2/dof=2.1
```

On failure:
```
pyNika FAILED: SAXS calibration 2025-03-01 14:23:05
  file: /data/SAXS.hdf
  reason: No peaks found for d=58.380 Å (ring outside detector)
```

---

## Phase 6 — Qt6 Graphical User Interface  ✅ (done)

**Goal:** Implement the full interactive GUI described in requirements §9.

### Sub-tasks

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 6.1 | Application skeleton: `QMainWindow` with two-pane `QSplitter` | ✅ | |
| 6.2 | Left panel scaffolding with `QScrollArea` | ✅ | min 400 px, max 600 px |
| 6.3 | **Data selector:** `QPushButton` + `QFileDialog` + path label | ✅ | Last 3 path components shown |
| 6.4 | **Log intensity checkbox** | ✅ | Default ON; view retained on toggle |
| 6.5 | **pyqtgraph `ImageView`** for 2D detector image | ✅ | viridis cmap; aspect locked 1:1 |
| 6.6 | **Calibrant selector** (combo/radio) | ✅ | Auto-selects SAXS→AgBehenate, WAXS→LaB6 |
| 6.7 | **d-spacing table** (`QTableWidget`) | ✅ | 3 cols: Use ☐, d (Å), ±W (px) — Use also controls overlay display |
| 6.8 | Instrument parameters display (wavelength, pixel size) | ✅ | Editable QLineEdit fields |
| 6.9 | **Fit parameters table** | ✅ | SDD, BCx, BCy, TiltX, TiltY |
| 6.10 | **No limits checkbox** — hides bound columns | ✅ | |
| 6.11 | **Beam-center overlay** | ✅ | Red "+" `ScatterPlotItem` |
| 6.12 | **Ring overlays** (red = theory, yellow dashed = ±search band) | ✅ | Redrawn on every param change |
| 6.13 | **Run Fit button** — background `QThread` worker | ✅ | Progress bar per ring; Revert button |
| 6.14 | χ²/dof and status labels | ✅ | |
| 6.15 | **Save to File** button | ✅ | `save_params_to_hdf5`; confirm dialog |
| 6.16 | **Save to PVs** button | ✅ | Report msg: "pyNika OK using <file> at <ts>" |
| 6.17 | **Export JSON / Import JSON** buttons | ✅ | Default name: `{saxs\|waxs\|custom}_pynika_parameters.json`; warns on λ mismatch |
| 6.18 | **Custom device configuration dialog** | ✅ | Modal QDialog 720 px; EPICS PV name fields; reset-to-defaults |
| 6.19 | `launch_gui()` entry point + CLI `--gui` flag | ✅ | `pynika-gui` console script |

### GUI Architecture Notes (as implemented)

- All Qt imports are **deferred inside `launch_gui()`** — both `FitWorker` and `MainWindow` are defined there as closures so they capture the lazily imported Qt classes.
- `_d_rows: list[tuple[QCheckBox, QDoubleSpinBox]]` — single "Use" checkbox controls both fitting and ring overlay display.
- `_update_image_display(reset_view=False)` — `autoRange` called only when `reset_view=True` (i.e., on file load), preserving zoom when the log checkbox is toggled.
- Residual in `optimise_geometry` uses **absolute pixel coordinates** (2 residuals Δx, Δy per peak) — required to avoid divergence when BCx/BCy are free parameters simultaneously.
- Azimuthal step (°) and strip half-width (px) are both user-exposed spinboxes in the Optimisation group.
- `_custom_pv_map` stored on the `MainWindow` instance; overrides built-in instrument EPICS config.

---

## Phase 7 — Testing, Validation, and Documentation

| # | Task | Status | Notes |
|---|------|--------|-------|
| 7.1 | Validate SAXS calibration against known Nika output for `examples/SAXS.hdf` | ✅ Done | Validated manually; results match Igor/Nika output sufficiently |
| 7.2 | Validate WAXS calibration against known Nika output for `examples/WAXS.hdf` | ✅ Done | Validated manually; results match Igor/Nika output sufficiently |
| 7.3 | Define and tune χ²/n_dof success threshold empirically | Pending | Document chosen value in code and spec |
| 7.4 | Test graceful failure: ring outside detector | Pending | Synthetic image with narrow beam-stop |
| 7.5 | Test graceful EPICS degradation on off-beamline workstation | Pending | Mock pyepics or temporarily remove it |
| 7.6 | API reference documentation | Pending | Write docstrings for all public functions; generate with Sphinx or pdoc |
| 7.7 | User guide | Pending | Step-by-step walkthrough for beamline use |
| 7.8 | Continuous Integration (GitHub Actions) | Pending | Run `pytest` on push; test Python 3.10–3.12 |

---

## Phase 8 — PyPI Packaging and Release

| # | Task | Notes |
|---|------|-------|
| 8.1 | Verify `pyproject.toml` classifiers, version, metadata | |
| 8.2 | Build and check `sdist` + `wheel` | `python -m build; twine check dist/*` |
| 8.3 | Upload to TestPyPI and install in a clean Conda env | Smoke test CLI |
| 8.4 | Tag v0.1.0 and upload to PyPI | |
| 8.5 | Update `environment.yml` to install from PyPI | Replace `-e .[dev]` with `pynika[gui,epics]` |

---

## Dependency and Ordering

```
Phase 0 (scaffold)
    ↓
Phase 1 (HDF5 I/O)   Phase 2 (geometry)
    ↓                     ↓
Phase 3 (Gaussian fitting)
    ↓
Phase 4 (optimisation)
    ↓
Phase 5 (CLI + EPICS)     Phase 6 (GUI)
    ↓                         ↓
Phase 7 (testing & docs)
    ↓
Phase 8 (release)
```

Phases 5 and 6 can be developed in parallel after Phase 4 is complete.  Phase 6 (GUI) can begin its skeleton (6.1–6.5) in parallel with Phase 1, using synthetic data for testing.

---

## Open Questions

1. **Tilt sign convention:** Confirm that TiltX and TiltY signs and axes match exactly between pyNika and Nika before Phase 2 can be closed.  Run a known-tilt test image (e.g. the LaB6 45° example referenced in `convertSWAXS.py` line 581) through both and compare ring centroids.

2. **Fit success threshold:** The χ²/n_dof cutoff (Phase 4) and minimum peak-fraction criterion need empirical tuning on real calibration data.  Leave both as configurable parameters with conservative defaults.

3. **Wavelength as free parameter:** Currently wavelength is held fixed.  If users request it, add as an optional free parameter in Phase 4 (it is strongly correlated with SDD and must be fitted carefully).

4. **WAXS beam center convention:** The WAXS HDF5 files store `waxs_ccd_center_x` (physical mm) and `waxs_ccd_center_x_pixel` separately.  Verify which one enters the Nika geometry calculation and ensure `hdf5_io.py` reads the correct field.

5. **PyPI name conflict:** Check that `pynika` is not already taken on PyPI before Phase 8.  Alternative names: `pynika-calibrate`, `sas-calibrate`.
