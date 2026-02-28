# Installation

## Requirements

- Python ≥ 3.10
- numpy ≥ 1.24, scipy ≥ 1.10, h5py ≥ 3.8 (installed automatically)
- Optional: PyQt6 + pyqtgraph (GUI), pyepics (EPICS PV writing)

---

## Option A — Install directly from GitHub (beamline / end-user)

No local clone needed. This always installs the latest release from the `main` branch.

```bash
# Core only (no GUI, no EPICS) — suitable for headless / script use
pip install "git+https://github.com/jilavsky/pynika.git"

# With GUI (PyQt6 + pyqtgraph)
pip install "git+https://github.com/jilavsky/pynika.git[gui]"

# With GUI + EPICS PV writing
pip install "git+https://github.com/jilavsky/pynika.git[gui,epics]"
```

### Beamline checklist

1. Confirm Python ≥ 3.10 is active:
   ```bash
   python --version
   ```
2. Install:
   ```bash
   pip install "git+https://github.com/jilavsky/pynika.git[gui,epics]"
   ```
3. Verify:
   ```bash
   python -c "import pynika; print(pynika.__version__)"
   ```
4. Launch the GUI:
   ```bash
   pynika-gui
   ```

### Upgrading to the latest commit

```bash
pip install --upgrade "git+https://github.com/jilavsky/pynika.git[gui,epics]"
```

---

## Option B — Conda environment (development / off-beamline)

```bash
git clone https://github.com/jilavsky/pynika.git
cd pynika
conda env create -f environment.yml
conda activate pynika
```

The `environment.yml` installs PyQt6, pyqtgraph, h5py, scipy, pyepics, pytest, ruff,
and pynika itself as an editable (`pip install -e .`) install.

To update after changes to `environment.yml`:
```bash
conda env update -f environment.yml --prune
```

---

## Optional dependency extras

| Extra   | Installs                                      |
|---------|-----------------------------------------------|
| `gui`   | PyQt6, pyqtgraph — required for the GUI       |
| `epics` | pyepics — required to write EPICS PVs         |
| `dev`   | pytest, pytest-cov, ruff, mypy                |
| `all`   | All of the above                              |

---

## Importing pynika in another Python package

Add pynika as a dependency in your `pyproject.toml` or `requirements.txt`:

**pyproject.toml** (recommended):
```toml
[project]
dependencies = [
    "pynika @ git+https://github.com/jilavsky/pynika.git",
]
```

**requirements.txt**:
```
git+https://github.com/jilavsky/pynika.git
```

Then install your package normally with `pip install -e .` or `pip install .`.
See [python_api.md](python_api.md) for usage examples.
