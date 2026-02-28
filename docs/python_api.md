# Python API

## Installation / import from another package

pynika is installable directly from GitHub and can be used as a dependency in
other packages without any PyPI registration.

**In `pyproject.toml`:**
```toml
[project]
dependencies = [
    "pynika @ git+https://github.com/jilavsky/pynika.git",
    # or pin to a specific commit:
    # "pynika @ git+https://github.com/jilavsky/pynika.git@<commit-sha>",
]
```

**In `requirements.txt`:**
```
git+https://github.com/jilavsky/pynika.git
```

Then install:
```bash
pip install -e .   # editable, for development
# or
pip install .
```

After installation, import normally:
```python
import pynika
from pynika import Calibrator, CalibrationResult
print(pynika.__version__)   # → "1.0.0"
```

---

## High-level API: `Calibrator`

### Constructor

```python
from pynika import Calibrator

cal = Calibrator(
    instrument="auto",          # "auto" (default), "SAXS", "WAXS", or "Custom"
    config_file=None,           # path to JSON config (required for "Custom")
    fit_config=None,            # FitConfig instance, or None for defaults
)
```

When `instrument="auto"` (the default), the instrument is detected from the
HDF5 file metadata each time `calibrate()` or `auto_calibrate()` is called.

---

### `auto_calibrate()` — recommended

```python
result = cal.auto_calibrate("/data/LaB6_0001.hdf")
```

Runs the automatic three-stage procedure:

| Stage | Rings used | Parameters fitted | Continue if … |
|-------|-----------|-------------------|---------------|
| 1 | First 2 enabled | SDD, BCx, BCy only | χ²/dof < 5 |
| 2 | All enabled | All free parameters | χ²/dof < 0.2 → done immediately |
| 3 | All enabled | All free parameters | χ²/dof < 3 → success |

---

### `calibrate()` — single-pass

```python
result = cal.calibrate("/data/SAXS.hdf")
```

Runs one least-squares optimisation pass with all enabled d-spacings and all
free parameters as configured in `fit_config`.

---

### `CalibrationResult`

```python
print(result)
# CalibrationResult [OK]  WAXS  LaB6_0001.hdf
#   SDD    = 414.832 mm
#   BCx    = 264.931 px
#   BCy    = 2742.614 px
#   TiltX  = -0.4251 deg
#   TiltY  = -0.1598 deg
#   chi2   = 0.6112   peaks used = 1860
#   msg    = Auto Fit Stage 3: chi²/dof=0.6112 [OK]

result.success        # True / False
result.sdd_mm         # float — sample-to-detector distance in mm
result.bcx            # float — beam centre X in pixels
result.bcy            # float — beam centre Y in pixels
result.tilt_x         # float — tilt X in degrees
result.tilt_y         # float — tilt Y in degrees
result.chi_square     # float — χ²/dof of the final fit
result.n_peaks        # int   — number of diffraction peaks used
result.message        # str   — human-readable status
result.instrument     # str   — resolved instrument name ("SAXS" or "WAXS")
result.hdf5_path      # str   — path of the input file
```

---

### Saving results

```python
# Write parameters back into the HDF5 source file (only if result.success)
cal.save_to_hdf5("/data/LaB6_0001.hdf", result)

# Push to EPICS PVs (prints to console if PVs are unreachable)
cal.save_to_pvs(result)
```

---

## Customising the fit: `FitConfig`

```python
from pynika.fitting.optimizer import FitConfig

cfg = FitConfig()
cfg.step_deg           = 2.0    # azimuthal step (degrees); default 1.0
cfg.transverse_px      = 3.0    # strip half-width (px); default 5.0
cfg.fit_tilt_x         = False  # hold TiltX fixed
cfg.fit_tilt_y         = False  # hold TiltY fixed
cfg.min_peaks_per_ring = 5      # minimum peaks to accept a ring; default 3

cal = Calibrator(instrument="SAXS", fit_config=cfg)
result = cal.auto_calibrate("/data/SAXS.hdf")
```

---

## Low-level API

```python
from pynika.io.hdf5_io import load_image_and_params, save_params_to_hdf5
from pynika.calibrants import get_calibrant
from pynika.fitting.optimizer import optimise_geometry, FitConfig

data = load_image_and_params("/data/SAXS.hdf")
cal  = get_calibrant("AgBehenate")   # returns a deep copy; safe to mutate
res  = optimise_geometry(
    data["image"], data["mask"], cal,
    data["wavelength"], data["pixel_size"],
    sdd_init=data["sdd"], bcx_init=data["bcx"], bcy_init=data["bcy"],
    tilt_x_init=data["tilt_x"], tilt_y_init=data["tilt_y"],
)
print(f"SDD = {res.sdd:.3f} mm,  BCx = {res.bcx:.3f},  chi2 = {res.chi_square:.4g}")
```

---

## Example: batch processing script

`scripts/batch_check.py` (included in the repository) is a working example of
using the Python API to process many files in a loop and report failures.  It
demonstrates:

- Auto-detecting instrument from each file (`Calibrator()` with no arguments)
- Running `auto_calibrate()` on each file
- Collecting and summarising results
- Using exit code 0/1 for scripting / CI integration

```python
from pynika import Calibrator

cal    = Calibrator()                         # auto-detects SAXS or WAXS per file
result = cal.auto_calibrate("LaB6_0001.hdf")

if result.success:
    print(f"OK  chi²={result.chi_square:.4f}  SDD={result.sdd_mm:.3f} mm")
else:
    print(f"FAILED: {result.message}")
```

See [cli_usage.md](cli_usage.md) for how to run `batch_check.py` from the command line.
