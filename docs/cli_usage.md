# Command-Line Usage

## Synopsis

```bash
pynika --file DATA.hdf [--auto-fit] [--instrument SAXS|WAXS|Custom] [--save-to-pvs] [--verbose]
pynika --gui
```

---

## Full option reference

| Flag | Default | Description |
|------|---------|-------------|
| `--file FILE` / `-f` | — | Path to HDF5 data file (required in non-GUI mode) |
| `--instrument` / `-i` | *auto* | `SAXS`, `WAXS`, or `Custom`. When omitted, the instrument is auto-detected from the HDF5 file metadata. |
| `--config FILE` / `-c` | — | JSON config file (required for `Custom` instrument) |
| `--auto-fit` | off | Multi-stage automatic fit (recommended): Stage 1 fits SDD+BCx+BCy with first 2 rings; Stages 2–3 fit all parameters with all rings; χ²/dof < 3 = success |
| `--save-to-pvs` | off | Push results to EPICS PVs (requires pyepics and network access) |
| `--gui` | off | Launch the interactive Qt6 GUI |
| `--verbose` / `-v` | off | Enable DEBUG logging |

---

## Examples

```bash
# Auto-detect instrument and run multi-stage auto-fit (recommended)
pynika --file /data/SAXS_calib.hdf --auto-fit

# Same, then push to EPICS PVs
pynika --file /data/SAXS_calib.hdf --auto-fit --save-to-pvs

# Explicit WAXS, single-pass fit
pynika --file /data/WAXS_calib.hdf --instrument WAXS

# Custom instrument from a JSON config
pynika --file /data/custom.hdf --instrument Custom --config my_instrument.json

# Verbose (DEBUG) logging
pynika --file /data/SAXS_calib.hdf --auto-fit --verbose
```

---

## Auto-fit stages

When `--auto-fit` is used, the calibration runs three sequential stages:

| Stage | Rings used | Parameters fitted | Continue if … |
|-------|-----------|-------------------|---------------|
| 1 | First 2 enabled | SDD, BCx, BCy only | χ²/dof < 5 |
| 2 | All enabled | All free parameters | χ²/dof < 0.2 → done immediately |
| 3 | All enabled | All free parameters | χ²/dof < 3 → success |

---

## Console output

```
INFO pynika.calibrator: Auto-calibrating WAXS with LaB6_0001.hdf
...
CalibrationResult [OK]  WAXS  LaB6_0001.hdf
  SDD    = 414.832 mm
  BCx    = 264.931 px
  BCy    = 2742.614 px
  TiltX  = -0.4251 deg
  TiltY  = -0.1598 deg
  chi2   = 0.6112   peaks used = 1860
  msg    = Auto Fit Stage 3: chi²/dof=0.6112 [OK]
```

---

## EPICS PV output

When `--save-to-pvs` is used, every PV write attempt is printed to the console:

```
pyNika: writing calibration parameters to EPICS PVs …
  [PV OK]          usxLAX:SAXS:SDD                          = 1523.456
  [PV OK]          usxLAX:SAXS:BCx                          = 512.300
  [PV UNREACHABLE] usxLAX:SAXS:BCy                          = 480.100
  [PV SIMULATED]   usxLAX:SAXS:TiltX                        = 0.12    (pyepics not installed)
pyNika: PV write complete — 2/4 written
```

Status tags: `[PV OK]` written, `[PV UNREACHABLE]` PV not responding,
`[PV SIMULATED]` pyepics not installed, `[PV ERROR]` exception during write.

---

## Batch processing with batch_check.py

For processing multiple files in a folder, use the `scripts/batch_check.py` helper script.
Copy `batch_check.py` to your data folder (or run with a path argument):

```bash
# Process all HDF5 files in the current folder
python batch_check.py

# Process all HDF5 files in a specific folder
python batch_check.py /data/calibrant_scans/

# Process explicit files
python batch_check.py file1.hdf file2.hdf
```

### Sample output

```
Found 4 HDF5 file(s). Running auto-fit …

  SAXS_calib_0001.hdf                         OK      SAXS    chi²=0.4231  peaks=847
  SAXS_calib_0002.hdf                         OK      SAXS    chi²=0.3918  peaks=831
  WAXS_calib_0001.hdf                         OK      WAXS    chi²=0.6112  peaks=1860
  bad_sample_data.hdf                         FAILED  SAXS    chi²=1e+09   Auto Fit Stage 1 failed

────────────────────────────────────────────────────────────────────────────────
Summary: 3/4 succeeded, 1 failed

  FAILED FILES
  FILE                                        INST    REASON
  bad_sample_data.hdf                         SAXS    Auto Fit Stage 1 failed (no peaks)
```

- Exit code 0 if all files succeed, 1 if any fail — suitable for scripting.
- INFO/DEBUG log noise is suppressed; only WARNING and above is shown.
- No data is written to disk.
