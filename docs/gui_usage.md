# GUI Usage

## Launching

```bash
pynika-gui          # console-script shortcut installed by pip
# or
pynika --gui
```

---

## Window layout

```
┌──────────────────────────────┬────────────────────────────────────────┐
│  Left panel (scroll)         │  Right panel (detector image)          │
│  ─────────────────────────   │  ──────────────────────────────────   │
│  Data File selector          │  Pyqtgraph image + HistogramLUT strip  │
│  □ Log intensity scale       │  • red cross  = beam centre            │
│  Calibrant ▾                 │  • red curves = theoretical rings      │
│  d-Spacings table            │  • yellow dashed = ±search band        │
│  Instrument Parameters       │                                        │
│  Fit Parameters table        │                                        │
│  Optimisation controls       │                                        │
│  Save & Export               │                                        │
└──────────────────────────────┴────────────────────────────────────────┘
```

---

## Typical workflow

1. Click **Select File…** and open an HDF5 calibrant file.
2. The instrument (SAXS / WAXS) is auto-detected from the file metadata.
3. Verify the calibrant (AgBehenate for SAXS, LaB6 for WAXS) and check that the
   red ring overlays roughly align with the diffraction rings.
4. Adjust **SDD / BCx / BCy** spinboxes if the rings are far off.
5. Click **Auto Fit** — the three-stage optimiser runs in the background:
   - Stage 1: first 2 d-spacings only, SDD+BCx+BCy only.
   - Stage 2: all d-spacings, all parameters.
   - Stage 3: refinement pass (χ²/dof < 3 = success).
6. Review χ²/dof and converged parameters.  Use **Revert** to undo if needed.
7. Click **Save to File** to write results back to the HDF5 file.
8. Click **Save to PVs** to push results to EPICS (beamline only).

---

## Calibrant selection

| Calibrant  | Default for | Notes |
|------------|-------------|-------|
| AgBehenate | SAXS        | d₁ = 58.380 Å |
| LaB6       | WAXS        | 10 reflections |
| Custom     | —           | Enter your own d-spacings in the table (defaults to LaB6 values) |

### Custom calibrant

When **Custom** is selected:
- The d-spacing column in the table becomes editable spinboxes.
- Edit each d-value (Å) directly in the table.
- Use the ±W column to set the search half-width per ring.
- Changes take effect immediately (ring overlays update live).
- Use **Export JSON** to save your custom d-spacings for future sessions.

### d-spacing table columns

| Column | Description |
|--------|-------------|
| Use    | Checkbox — include this ring in the fit |
| d (Å)  | D-spacing (editable for Custom calibrant) |
| ±W (px)| Search half-width around the expected ring radius (step = 5 px) |

**Set ±W all** sets the search width for all rings at once.

---

## Instrument Parameters

- **Wavelength (Å)** and **Pixel size (mm)** are loaded from the HDF5 file.
- Both fields are editable — type a new value to override the stored value.
  The overridden value is used immediately for overlay rendering and fitting.

---

## Fit Parameters table

| Column | Description |
|--------|-------------|
| Parameter | SDD (mm), BCx (px), BCy (px), TiltX (°), TiltY (°) |
| Value  | Current value (editable spinbox) |
| Fit?   | Checkbox — free this parameter in the optimisation |
| Low / High | Bounds (hidden when "No limits" is checked) |

---

## Optimisation controls

| Control | Description |
|---------|-------------|
| Az. step (°) | Angular step between radial profiles. 1° gives 360 directions per ring. |
| Strip ½-W (px) | Half-width of the averaging strip perpendicular to the radial direction |
| **Auto Fit** | Three-stage automatic procedure (recommended) |
| **Run Fit** | Single-pass fit using the current Fit? checkboxes |
| **Revert** | Restore parameter values to before the last fit (or Auto Fit) |
| χ²/dof | Reduced chi-squared of the final fit (< 3 = good) |

---

## Image controls

- **Log intensity scale** checkbox (default ON) — toggles log₁₀ display without resetting the zoom.
- **Intensity range slider** — the HistogramLUT strip on the right edge of the image.
  Drag the yellow handles to adjust the display range. Right-click the gradient bar for
  colour table options.
- **Right-click the image** for:
  - **Color table** submenu — choose from viridis, plasma, terrain, grey, and more.
  - **Save image as JPG…** — saves the current view (with overlays) as a JPEG file.

---

## Save & Export

| Button | Action |
|--------|--------|
| Save to File | Write SDD, BCx, BCy, TiltX, TiltY, and a CalibrationReport string back into the HDF5 source file |
| Save to PVs | Push parameters to EPICS process variables (beamline only; echoes to console if PVs are unreachable) |
| Export JSON… | Save all current parameters to a JSON file (see below) |
| Import JSON… | Load parameters from a previously exported JSON file |
| Custom Device Config… | Edit EPICS PV names for non-standard instruments |

### What Export JSON saves

The JSON file contains all of the following:

| Key | Description |
|-----|-------------|
| `sdd`, `bcx`, `bcy`, `tilt_x`, `tilt_y` | Geometry parameters (current spinbox values) |
| `wavelength`, `pixel_size` | Instrument parameters (current field values) |
| `instrument` | Detected instrument tag (`SAXS` or `WAXS`) |
| `calibrant` | Selected calibrant name (`AgBehenate`, `LaB6`, or `Custom`) |
| `use_flags` | List of booleans — which rings are enabled |
| `search_widths` | List of ±W values per ring (px) |
| `d_spacings` | *(Custom calibrant only)* List of d-spacing values (Å) |

All of the above are restored on **Import JSON**. A wavelength mismatch warning
is shown if the JSON wavelength differs from the currently loaded file.
