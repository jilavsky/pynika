# pyNika

**pyNika** is a Python package for calibrating small-angle and wide-angle pinhole X-ray scattering (SAXS/WAXS) instruments using diffraction rings from distance standards (calibrants). It reproduces the geometry conventions and calibration logic of the [Nika](https://usaxs.xray.aps.anl.gov/software/sas-igor) Igor Pro package so that calibration parameters remain fully compatible with the Nika-based data-reduction pipeline.

---

## Features

- Reads 2D detector images and instrument parameters from HDF5 files produced by the APS/USAXS data-collection system.
- Optimises beam-center (X, Y), sample-to-detector distance (SDD), and detector tilt angles (TiltX, TiltY) using least-squares fitting of diffraction rings from known calibrants.
- Supports **AgBehenate** (SAXS), **LaB6** (WAXS), and user-defined **Custom** calibrants.
- Three built-in instrument configurations: **SAXS**, **WAXS**, and **Custom** (saved/loaded as JSON).
- Writes optimised parameters back into the HDF5 file, including a text `CalibrationReport` dataset.
- Optionally pushes parameters to EPICS process variables (PVs) via `pyepics`; always echoes the values to the console and degrades gracefully when PVs are unreachable.
- **Qt6 GUI** (pyqtgraph image display, histogram LUT, colour-table selection, JPG export) for interactive inspection and manual refinement.
- **CLI** for headless / pipeline use.

---

## Installation

### Option A — Install directly from GitHub (recommended for beamline use)

No local clone required. This always installs the latest version from the `main` branch:

```bash
# Core only (no GUI, no EPICS)
pip install "git+https://github.com/jilavsky/pynika.git"

# With GUI (PyQt6 + pyqtgraph)
pip install "git+https://github.com/jilavsky/pynika.git[gui]"

# With GUI + EPICS PV writing
pip install "git+https://github.com/jilavsky/pynika.git[gui,epics]"
```

To upgrade to the latest commit later:

```bash
pip install --upgrade "git+https://github.com/jilavsky/pynika.git[gui,epics]"
```

> **Beamline computer checklist**
> 1. Ensure Python ≥ 3.10 is active (`python --version`).
> 2. Run `pip install "git+https://github.com/jilavsky/pynika.git[gui,epics]"`.
> 3. Verify: `python -c "import pynika; print(pynika.__version__)"`.
> 4. Launch the GUI: `pynika-gui` (or `pynika --gui`).


### Option B — Conda environment (development / off-beamline)

```bash
git clone https://github.com/jilavsky/pynika.git
cd pynika
conda env create -f environment.yml
conda activate pynika
```

The `environment.yml` sets up a complete environment including PyQt6, pyqtgraph, h5py, scipy, pyepics, and the pynika package itself as an editable install.

### Optional extras

| Extra | Installs |
|-------|---------|
| `gui` | PyQt6, pyqtgraph — needed for the interactive GUI |
| `epics` | pyepics — needed to write parameters to EPICS PVs |
| `dev` | pytest, ruff, mypy — for development |
| `all` | All of the above |

```bash
pip install "git+https://github.com/jilavsky/pynika.git[gui,epics]"
```

---

## Quick Start

### Interactive GUI

```bash
pynika-gui          # console-script shortcut installed by pip
# or
pynika --gui
```

The GUI opens a two-pane window:

- **Left panel** — file selector, calibrant selection, d-spacing table, instrument parameters, fit-parameter table with bounds, optimisation controls, save/export buttons.
- **Right panel** — 2D detector image with histogram/LUT strip (drag handles to adjust intensity range; right-click gradient for colour tables). Right-click the image for colour-table selection and "Save image as JPG…".

**Typical workflow:**
1. Click **Select File…** and open an HDF5 calibrant file.
2. Verify the detected instrument (SAXS / WAXS) and calibrant (AgBehenate / LaB6).
3. Check that the red ring overlays line up with the diffraction rings; adjust SDD / BCx / BCy if they are far off.
4. Click **Run Fit** — the optimiser runs in a background thread.
5. Review χ²/dof and the converged parameters.
6. Click **Save to File** to write the results back to the HDF5 file.
7. Click **Save to PVs** to push the results to EPICS (beamline only).

### CLI

```bash
# Calibrate a SAXS file, save results to HDF5
pynika --file /data/SAXS.hdf

# Use automatic multi-stage fitting (recommended starting point)
pynika --file /data/SAXS.hdf --auto-fit

# Calibrate and also push to EPICS PVs
pynika --file /data/SAXS.hdf --save-to-pvs

# Calibrate a WAXS file
pynika --file /data/WAXS.hdf --instrument WAXS --save-to-pvs

# Custom instrument using a JSON config file
pynika --file /data/custom.hdf --instrument Custom --config my_config.json

# Verbose logging
pynika --file /data/SAXS.hdf --verbose

# Full option list
pynika --help
```

**CLI options**

| Flag | Default | Description |
|------|---------|-------------|
| `--file FILE` | — | Path to HDF5 data file (required in non-GUI mode) |
| `--instrument` | `SAXS` | `SAXS`, `WAXS`, or `Custom` |
| `--config FILE` | — | JSON config file (required for `Custom`) |
| `--auto-fit` | off | Multi-stage automatic fit (recommended): Stage 1 fits SDD+BCx+BCy with first 2 rings; Stages 2–3 fit all parameters with all rings; chi²<1 = success |
| `--save-to-pvs` | off | Push results to EPICS PVs |
| `--gui` | off | Launch the Qt6 GUI |
| `--verbose` / `-v` | off | Enable DEBUG logging |

### Python API

```python
from pynika import Calibrator, CalibrationResult

# ── Automatic multi-stage calibration (recommended) ────────────
cal = Calibrator(instrument="SAXS")
result = cal.auto_calibrate("/data/SAXS.hdf")
# Stage 1: first 2 d-spacings, SDD+BCx+BCy only (abort if chi²≥5)
# Stage 2: all d-spacings, all parameters      (done if chi²<0.2)
# Stage 3: refinement pass                     (success if chi²<1)

# ── Basic single-pass calibration ─────────────────────────────
cal = Calibrator(instrument="SAXS")          # or "WAXS"
result = cal.calibrate("/data/SAXS.hdf")     # runs the full optimisation

print(result)
# CalibrationResult [OK]  SAXS  SAXS.hdf
#   SDD    = 1523.456 mm
#   BCx    = 512.300 px
#   BCy    = 480.100 px
#   TiltX  = 0.1200 deg
#   TiltY  = -0.0500 deg
#   chi2   = 2.31    peaks used = 847
#   msg    = Converged

# ── Save results ───────────────────────────────────────────────
cal.save_to_hdf5("/data/SAXS.hdf", result)  # writes back into HDF5 file
cal.save_to_pvs(result)                      # pushes to EPICS PVs (or echos to console)

# ── Custom fitting config ──────────────────────────────────────
from pynika.fitting.optimizer import FitConfig

cfg = FitConfig()
cfg.step_deg       = 2.0   # azimuthal step in degrees (default 1.0)
cfg.transverse_px  = 3.0   # strip half-width in pixels (default 5.0)
cfg.fit_tilt_x     = False # hold TiltX fixed
cfg.fit_tilt_y     = False # hold TiltY fixed

cal = Calibrator(instrument="SAXS", fit_config=cfg)
result = cal.calibrate("/data/SAXS.hdf")

# ── Low-level access ───────────────────────────────────────────
from pynika.io.hdf5_io import load_image_and_params, save_params_to_hdf5
from pynika.calibrants import get_calibrant
from pynika.fitting.optimizer import optimise_geometry

data = load_image_and_params("/data/SAXS.hdf")
cal  = get_calibrant("AgBehenate")
res  = optimise_geometry(
    data["image"], data["mask"], cal,
    data["wavelength"], data["pixel_size"],
    sdd_init=data["sdd"], bcx_init=data["bcx"], bcy_init=data["bcy"],
    tilt_x_init=data["tilt_x"], tilt_y_init=data["tilt_y"],
)
print(f"SDD = {res.sdd:.3f} mm,  BCx = {res.bcx:.3f},  chi2 = {res.chi_square:.4g}")
```

---

## Instrument Configurations

| Config | Default calibrant | HDF5 Metadata keys |
|--------|------------------|--------------------|
| SAXS | AgBehenate | `pin_ccd_center_x_pixel`, `pin_ccd_center_y_pixel`, `pin_ccd_tilt_x`, `pin_ccd_tilt_y` |
| WAXS | LaB6 | `waxs_ccd_center_x_pixel`, `waxs_ccd_center_y_pixel`, `waxs_ccd_tilt_x`, `waxs_ccd_tilt_y` |
| Custom | User-defined | User-defined (JSON) |

HDF5 paths read for all instruments:

```
/entry/data/data                                → 2D detector image  (transposed: (nx,ny)→(ny,nx))
/entry/instrument/detector/distance             → SDD (mm)
/entry/instrument/detector/x_pixel_size         → pixel size (mm)
/entry/instrument/monochromator/wavelength       → wavelength (Å)
/entry/Metadata/<instrument>_ccd_center_x_pixel → BCx (px)
/entry/Metadata/<instrument>_ccd_center_y_pixel → BCy (px)
/entry/Metadata/<instrument>_ccd_tilt_x         → TiltX (°)
/entry/Metadata/<instrument>_ccd_tilt_y         → TiltY (°)
```

On **Save to File**, the following are updated:

```
/entry/instrument/detector/distance             ← SDD
/entry/instrument/detector/beam_center_x        ← BCx
/entry/instrument/detector/beam_center_y        ← BCy
/entry/instrument/detector/CalibrationReport    ← text report (created if absent)
/entry/Metadata/<instrument>_ccd_*             ← individual metadata scalars
```

---

## EPICS PV Console Output

When **Save to PVs** is used (GUI button or `--save-to-pvs` CLI flag), every PV write attempt is printed to the console:

```
pyNika: writing calibration parameters to EPICS PVs …
  [PV OK]          usxLAX:SAXS:SDD                          = 1523.456        (SDD (mm))
  [PV OK]          usxLAX:SAXS:BCx                          = 512.300         (beam center X (px))
  [PV OK]          usxLAX:SAXS:BCy                          = 480.100         (beam center Y (px))
  [PV OK]          usxLAX:SAXS:TiltX                        = 0.12            (TiltX (deg))
  [PV OK]          usxLAX:SAXS:TiltY                        = -0.05           (TiltY (deg))
  [PV OK]          usxLAX:SAXS:CalibrationReport            = 'pyNika OK: …'  (CalibrationReport)
pyNika: PV write complete — ALL OK
```

When off-beamline (pyepics not installed) or PV unreachable, the line reads `[PV SIMULATED]` or `[PV UNREACHABLE]` respectively — no exception is raised.

---

## Pixel Masking

| Instrument | Masked conditions |
|-----------|------------------|
| SAXS (Eiger) | intensity < 0, intensity > 1×10⁸, dead rows 0–3 and 242–244 |
| WAXS (Pilatus) | intensity < 0, intensity > 1×10⁷, module-gap rows 511–515, 1026–1040, 1551–1555 |

---

## Data Format

Input files are HDF5 files produced by the APS/USAXS area-detector data-collection system. Example files are in [examples/](examples/).

---

## Development

```bash
git clone https://github.com/jilavsky/pynika.git
cd pynika
pip install -e ".[dev]"
pytest
ruff check pynika/
```

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Calibration geometry faithfully follows the conventions of [Nika](https://usaxs.xray.aps.anl.gov/software/sas-igor) (I. Ilavsky, *J. Appl. Cryst.* **45**, 324–328, 2012). AgBehenate d-spacings from T. C. Huang et al., *J. Appl. Cryst.* **26**, 180–184, 1993.
