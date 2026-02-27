# pyNika — Requirements Specification

**Document type:** Summary of project requirements derived from the initial design description.
**Date:** 2025
**Author:** Ivan Ilavsky

---

## 1. Purpose and Scope

pyNika is a Python package for calibrating small-angle and wide-angle pinhole X-ray scattering (SAXS/WAXS) instruments using scattering from distance standards (calibrants).

The primary calibration parameters are:

| Symbol | Meaning | Units |
|--------|---------|-------|
| BCx, BCy | Beam-center position on detector | pixels |
| SDD | Sample-to-detector distance | mm |
| TiltX, TiltY | Detector tilt angles (Nika convention) | degrees |

Calibration parameters must remain fully compatible with the **Nika** Igor Pro package (I. Ilavsky, *J. Appl. Cryst.* **45**, 324–328, 2012).  The downstream data-reduction pipeline reads and writes these values using Nika's geometry model, so the definitions, sign conventions, and calculation formulae must be preserved exactly.

---

## 2. Source Material

| File | Role |
|------|------|
| `examples/convertSWAXS.py` | Reference HDF5 reader (`importADData`) and data-reduction pipeline |
| `examples/NI1_BeamCenterUtils.ipf` | Nika calibration GUI: calibrant d-spacings, ring-fitting logic, EPICS PV names |
| `examples/NI1_ConvProc.ipf` | Nika geometry conversion (tilt model, pixel↔angle formulae) |
| `examples/SAXS.hdf` | Example SAXS data file |
| `examples/WAXS.hdf` | Example WAXS data file |
| `examples/CalibrantPage.jpg` | Screenshot of Nika calibrant-selection GUI |
| `examples/Refinementpage.jpg` | Screenshot of Nika refinement/fitting GUI |

---

## 3. Instrument Configurations

Three named instrument configurations are required:

### 3.1 SAXS

| Parameter | HDF5 path / metadata key |
|-----------|--------------------------|
| 2D image | `/entry/data/data` |
| SDD | `/entry/instrument/detector/distance` (mm) |
| Pixel size | `/entry/instrument/detector/x_pixel_size` (mm) |
| Wavelength | `/entry/instrument/monochromator/wavelength` (Å) |
| BCx | `/entry/Metadata/pin_ccd_center_x_pixel` |
| BCy | `/entry/Metadata/pin_ccd_center_y_pixel` |
| TiltX | `/entry/Metadata/pin_ccd_tilt_x` |
| TiltY | `/entry/Metadata/pin_ccd_tilt_y` |

Default calibrant: **AgBehenate**

EPICS PVs (APS/USAXS beamline):

| Parameter | PV name |
|-----------|---------|
| BCx | `usxLAX:SAXS:BeamCenterX` |
| BCy | `usxLAX:SAXS:BeamCenterY` |
| TiltX | `usxLAX:SAXS:DetectorTiltX` |
| TiltY | `usxLAX:SAXS:DetectorTiltY` |
| SDD | `usxLAX:SAXS:Distance` |
| Report | `usxLAX:SAXS:CalibrationReport` |

### 3.2 WAXS

| Parameter | HDF5 path / metadata key |
|-----------|--------------------------|
| BCx | `/entry/Metadata/waxs_ccd_center_x_pixel` |
| BCy | `/entry/Metadata/waxs_ccd_center_y_pixel` |
| TiltX | `/entry/Metadata/waxs_ccd_tilt_x` |
| TiltY | `/entry/Metadata/waxs_ccd_tilt_y` |

(SDD, pixel size, wavelength: same paths as SAXS)

Default calibrant: **LaB6**

EPICS PVs: same structure with `usxLAX:WAXS:` prefix.

### 3.3 Custom

All HDF5 paths, metadata key names, EPICS PV names, and calibrant selection are user-configurable.  Configuration is saved to and loaded from a **JSON file**.  A dedicated configuration GUI panel is required.

---

## 4. Calibrant Standards

Calibrants have up to **10 d-spacings** each.

### 4.1 AgBehenate (SAXS default)

Reference: T. C. Huang et al., *J. Appl. Cryst.* **26**, 180–184 (1993).

| # | d-spacing (Å) |
|---|---------------|
| 1 | 58.380 |
| 2 | 29.185 |
| 3 | 19.46 |
| 4 | 14.595 |
| 5 | 11.676 |
| 6 | 9.73 |
| 7 | 8.34 |
| 8 | 7.2975 |
| 9 | 6.48667 |
| 10 | 5.838 |

### 4.2 LaB6 (WAXS default)

Source: P. Lee (APS/XSD), as used in Nika.

| # | d-spacing (Å) | hkl |
|---|---------------|-----|
| 1 | 4.15690 | 100 |
| 2 | 2.93937 | 110 |
| 3 | 2.39999 | 111 |
| 4 | 2.07845 | 200 |
| 5 | 1.85902 | 210 |
| 6 | 1.69705 | 211 |
| 7 | 1.46969 | 220 |
| 8 | 1.38564 | 300/221 |
| 9 | 1.31453 | 310 |
| 10 | 1.25336 | 311 |

### 4.3 Custom

Up to 10 user-specified d-spacings, each independently editable.

---

## 5. Fitting Algorithm

The fitting algorithm mirrors the Nika implementation (`NI1_BeamCenterUtils.ipf`):

1. **Theoretical ring position**: For each enabled d-spacing and the current parameter estimate, compute the expected ring radius in pixels:

   ```
   θ   = arcsin(λ / (2d))
   r   = SDD · tan(2θ) / pixel_size
   ```

2. **Radial profile extraction**: For each azimuthal direction (default: 1° steps over 360°), extract a 1D intensity profile in the radial direction, averaging ±N pixels transversely (default N = 5–10 px) to improve statistics.

3. **Gaussian peak fitting**: Fit a Gaussian plus linear background
   `f(r) = A·exp(-½((r-μ)/σ)²) + m·r + b`
   within a search window ±W pixels around the theoretical ring radius.  The search width W is per-ring, user-configurable.

4. **Peak collection**: Accept fits that converge to a peak within the search window.  Skip directions where the strip extends outside the active detector area or into masked pixels.

5. **Global optimisation**: Use `scipy.optimize.least_squares` to minimise the sum of squared residuals between all collected peak positions and the model prediction.  The model maps (BCx, BCy, SDD, TiltX, TiltY) → expected pixel position at each (d, azimuth) combination, using the Nika tilt-correction formula.

6. **Free parameters and bounds**: Each of BCx, BCy, SDD, TiltX, TiltY may be individually held fixed or allowed to float, with optional lower/upper bounds.

---

## 6. Data Masking

Two masking rules handle different detector types:

| Detector type | Mask condition |
|---------------|----------------|
| SAXS (Eiger) | Pixels with intensity < 0 are dead/invalid |
| WAXS (Pilatus) | Pixels with intensity > 1×10⁷ are in inter-module gaps |

Additionally, known dead columns are masked per-instrument:
- SAXS: columns 0–3 and 242–244
- WAXS: columns 511–515, 1026–1040, 1551–1555

Custom instruments must allow user-defined masking rules.

---

## 7. Output

### 7.1 HDF5

On success, the optimised parameters are written back to the same HDF5 file at the same paths and metadata keys from which they were read.

### 7.2 EPICS PVs (optional)

When `--save-to-pvs` is requested:

- All five geometry PVs (BCx, BCy, TiltX, TiltY, SDD) are written via `pyepics`.
- The `CalibrationReport` string PV receives a short message: success/failure, timestamp, and filenames used.
- If `pyepics` is not installed **or** the PVs are unreachable (e.g. on an off-beamline workstation), the values that would have been written are printed to the console.  **No exception is raised.**

### 7.3 JSON Export/Import

The current fit configuration (all parameters and settings, packaged as "Custom" device) can be exported to JSON and imported back via GUI buttons or CLI flags.

---

## 8. Operating Modes

### 8.1 CLI

```
pynika --file DATA.hdf --instrument SAXS [--save-to-pvs] [--verbose]
pynika --file DATA.hdf --instrument Custom --config cfg.json [--save-to-pvs]
pynika --gui
```

The CLI: loads data, runs optimisation, saves results to HDF5, optionally writes PVs, then exits.  Does **not** save if optimisation fails; only writes a failure note to the CalibrationReport PV.

### 8.2 Python API

```python
from pynika import Calibrator
cal = Calibrator(instrument="SAXS")
result = cal.calibrate("SAXS.hdf")
cal.save_to_hdf5("SAXS.hdf", result)
cal.save_to_pvs(result)
```

### 8.3 Qt6 GUI

See Section 9 for the full GUI specification.

---

## 9. Graphical User Interface

### 9.1 Technology

- **Framework:** Qt6 (PyQt6 or PySide6)
- **Image display:** pyqtgraph `ImageView`
- Matplotlib may be used only if a required feature is unavailable in pyqtgraph.

### 9.2 Layout

Two-pane layout: **left control panel** and **right image display**.

#### Left panel — Data

- **File selector button** — opens a file-browser dialog filtering for `.hdf`, `.h5`, `.hdf5`; default starting directory is CWD.
- **Current file label** — shows the path shortened to the last two path components: `…/dataFolder/subFolder/filename.hdf`.
- **Log intensity checkbox** — converts display to `log10(intensity)`. Default: **on**.

#### Left panel — Calibrant

- Radio/combo to select: **AgBehenate**, **LaB6**, **Custom**.
- **d-spacing table** (up to 10 rows):
  - Checkbox: use this line in fit?
  - d-spacing value (editable for Custom).
  - Search width ±W (pixels) — editable per row.
  - Checkbox: display ring in image?
- **Azimuthal step** input field (degrees; default 1°).
- **Transverse strip width** input (pixels; default 5–10 px).
- Wavelength and pixel size display fields (editable as override).

#### Left panel — Fit Parameters

For each of SDD, BCx, BCy, TiltX, TiltY:

- Current value display/edit field.
- **Fit** checkbox (include in optimisation).
- **Low / High** bound fields (hidden when "No limits" is checked).
- **No limits** checkbox — hides bound fields and disables bounds in the solver.

Below the parameter table:

- χ² result label.
- Status message label (success / failure / not run).

#### Left panel — Action Buttons

| Button | Action |
|--------|--------|
| Run Fit | Execute the optimisation with current settings |
| Save to File | Write parameters to HDF5 |
| Save to PVs | Write parameters to EPICS PVs |
| Export Parameters | Save settings to JSON (default: CWD) |
| Import Parameters | Load settings from JSON (with overwrite warning) |

#### Right panel — Image Display

- Scales to fill available space; long axis oriented horizontally when possible.
- **Beam-center overlay**: red dot + circle at (BCx, BCy).  May be outside the visible image area.
- **Ring overlays** (for each row with "display" checked):
  - Red circle at theoretical ring radius.
  - Yellow circles at ±W pixels (the search band edges), showing the Gaussian fitting range.
- All overlays update live when parameter values change.

### 9.3 Custom Device Configuration Dialog

A separate modal dialog for configuring the Custom instrument:

- All HDF5 path fields (data, SDD, pixel size, wavelength, BCx/BCy/TiltX/TiltY metadata keys).
- EPICS PV name fields (BCx, BCy, TiltX, TiltY, SDD, Report).
- Mask type (SAXS-like / WAXS-like / None) and dead-column ranges.
- **Save** button — writes configuration to JSON.
- **Load** button — reads JSON back.

---

## 10. Fit Success / Failure Criteria

Fit success is not fully defined yet and must be determined through testing.  Minimum criteria to implement:

1. `scipy.optimize.least_squares` reports successful convergence.
2. Each Gaussian fit found a peak (amplitude > noise threshold, peak within search window).
3. χ² / n_dof is below a configurable threshold.

Failure cases to detect:
- Ring outside search window → convergence to a spurious local minimum.
- No peaks found for one or more d-spacings (ring outside detector, all masked).
- Fit diverges or hits parameter bounds.

---

## 11. Dependencies

| Package | Purpose | Required? |
|---------|---------|-----------|
| numpy | Array maths | Yes |
| scipy | Gaussian fitting, least_squares | Yes |
| h5py | HDF5 I/O | Yes |
| PyQt6 | GUI framework | Optional (gui extra) |
| pyqtgraph | Image display and plotting | Optional (gui extra) |
| pyepics | EPICS PV communication | Optional (epics extra) |

---

## 12. Non-Requirements

The following are explicitly out of scope for the initial release:

- 2D integration / data reduction (handled by the existing pipeline using pyFAI).
- Instrument control / scan execution.
- Detector flat-field or spatial-distortion corrections.
- Wavelength as a free fit parameter.
