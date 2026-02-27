# pyNika

**pyNika** is a Python package for calibrating small-angle and wide-angle pinhole X-ray scattering (SAXS/WAXS) instruments using diffraction from distance standards (calibrants). It reproduces the geometry conventions and calibration logic of the [Nika](https://usaxs.xray.aps.anl.gov/software/sas-igor) Igor Pro package so that calibration parameters remain compatible with the Nika-based data-reduction pipeline.

---

## Features

- Reads 2D detector images and instrument parameters from HDF5 files produced by the APS/USAXS data collection system.
- Optimises beam-center position (X, Y), sample-to-detector distance (SDD), and detector tilt angles (TiltX, TiltY) using least-squares fitting of diffraction rings from known calibrants.
- Supports **AgBehenate** (SAXS), **LaB6** (WAXS), and user-defined **Custom** calibrants.
- Three instrument configurations: **SAXS**, **WAXS**, and **Custom** (saved/loaded as JSON).
- Writes optimised parameters back into the HDF5 file.
- Optionally pushes parameters to EPICS process variables (PVs) via `pyepics`; gracefully degrades when PVs are unreachable.
- **CLI** for headless/pipeline use.
- **Qt6 GUI** (PyQtGraph image display) for interactive inspection and manual refinement.

---

## Installation

### Prerequisites

pyNika is tested with **Python 3.10 – 3.12**. A Conda environment is strongly recommended.

### 1. Create and activate a Conda environment

```bash
conda env create -f environment.yml
conda activate pynika
```

### 2. Install pyNika

For regular use:

```bash
pip install pynika
```

For development (editable install with all extras):

```bash
git clone https://github.com/ilavsky/pynika.git
cd pynika
pip install -e ".[all]"
```

### 3. Optional extras

| Extra | What it installs |
|-------|-----------------|
| `gui` | PyQt6, pyqtgraph — required for the interactive GUI |
| `epics` | pyepics — required to write calibration results to EPICS PVs |
| `dev` | pytest, ruff, mypy — for development and testing |
| `all` | All of the above |

```bash
pip install "pynika[gui,epics]"
```

---

## Quick Start

### CLI

```bash
# Calibrate SAXS detector, save results to HDF5 only
pynika --file /data/SAXS.hdf --instrument SAXS

# Calibrate WAXS detector and push results to EPICS PVs
pynika --file /data/WAXS.hdf --instrument WAXS --save-to-pvs

# Calibrate with a custom instrument configuration
pynika --file /data/custom.hdf --instrument Custom --config my_config.json
```

### Python API

```python
from pynika import Calibrator

cal = Calibrator(instrument="SAXS")
result = cal.calibrate("/data/SAXS.hdf")
print(result)
# CalibrationResult(sdd_mm=1523.4, bcx=512.3, bcy=480.1, tilt_x=0.12, tilt_y=-0.05)

cal.save_to_hdf5("/data/SAXS.hdf", result)
cal.save_to_pvs(result)   # no-op + warning if PVs unreachable
```

### GUI

```bash
pynika --gui
# or just
pynika-gui          # alias installed by pip
```

---

## Instrument Configurations

| Config | Calibrant | HDF5 metadata keys | EPICS PV prefix |
|--------|-----------|-------------------|-----------------|
| SAXS | AgBehenate | `pin_ccd_center_x_pixel`, `pin_ccd_center_y_pixel`, `pin_ccd_tilt_x`, `pin_ccd_tilt_y` | `usxLAX:SAXS:` |
| WAXS | LaB6 | `waxs_ccd_center_x_pixel`, `waxs_ccd_center_y_pixel`, `waxs_ccd_tilt_x`, `waxs_ccd_tilt_y` | `usxLAX:WAXS:` |
| Custom | User-defined | User-defined (JSON) | User-defined |

Common parameters read from HDF5 for all configurations:

```
/entry/instrument/detector/distance          → SDD (mm)
/entry/instrument/detector/x_pixel_size      → pixel size (mm)
/entry/instrument/monochromator/wavelength   → wavelength (Å)
/entry/data/data                             → 2D detector image
```

---

## Data Format

Input files are HDF5 files following the layout produced by the APS/USAXS area-detector data collection. Example files are provided in [examples/](examples/).

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check pynika/
```

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Calibration geometry follows the conventions of [Nika](https://usaxs.xray.aps.anl.gov/software/sas-igor) (I. Ilavsky, *J. Appl. Cryst.* **45**, 324–328, 2012). AgBehenate d-spacings from T. C. Huang et al., *J. Appl. Cryst.* **26**, 180–184, 1993.
