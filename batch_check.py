"""
batch_check.py — Run pynika auto-fit on every HDF5 file in the current folder.

Usage
-----
    python batch_check.py                  # all *.hdf / *.h5 / *.hdf5 in cwd
    python batch_check.py /path/to/folder  # explicit folder
    python batch_check.py *.hdf            # explicit glob (shell-expanded)

Output
------
Prints one line per file, then a summary table of failures.
No data is written to disk.
"""

from __future__ import annotations
import sys
import os
import glob


def find_hdf_files(folder: str) -> list[str]:
    paths: list[str] = []
    for ext in ("*.hdf", "*.h5", "*.hdf5", "*.HDF", "*.H5", "*.HDF5"):
        paths.extend(glob.glob(os.path.join(folder, ext)))
    return sorted(set(paths))


def main() -> None:
    # Resolve target folder / explicit file list from argv
    if len(sys.argv) == 1:
        files = find_hdf_files(".")
    elif len(sys.argv) == 2 and os.path.isdir(sys.argv[1]):
        files = find_hdf_files(sys.argv[1])
    else:
        # Treat all arguments as explicit file paths / shell-expanded globs
        files = sorted(set(sys.argv[1:]))

    if not files:
        print("No HDF5 files found.")
        return

    print(f"Found {len(files)} HDF5 file(s). Running auto-fit …\n")

    from pynika import Calibrator

    results_ok:   list[tuple[str, str, float, int]] = []   # (file, instrument, chi2, n_peaks)
    results_fail: list[tuple[str, str, str]]         = []  # (file, instrument, reason)

    col = 60   # width for the filename column

    for path in files:
        fname = os.path.basename(path)
        print(f"  {fname:<{col}}", end="", flush=True)
        try:
            cal    = Calibrator()                    # auto-detects instrument
            result = cal.auto_calibrate(path)
        except Exception as exc:
            print(f"ERROR   {exc}")
            results_fail.append((fname, "?", str(exc)))
            continue

        inst = result.instrument or "?"
        if result.success:
            print(f"OK      {inst:<6}  chi²={result.chi_square:.4f}  peaks={result.n_peaks}")
            results_ok.append((fname, inst, result.chi_square, result.n_peaks))
        else:
            chi_str = f"{result.chi_square:.4f}" if result.chi_square == result.chi_square else "—"
            print(f"FAILED  {inst:<6}  chi²={chi_str}  {result.message}")
            results_fail.append((fname, inst, result.message))

    # ── Summary ──────────────────────────────────────────────────────────────
    n_total = len(files)
    n_ok    = len(results_ok)
    n_fail  = len(results_fail)

    print(f"\n{'─'*80}")
    print(f"Summary: {n_ok}/{n_total} succeeded, {n_fail} failed\n")

    if results_ok:
        print(f"  {'FILE':<{col}}  {'INST':<6}  CHI²      PEAKS")
        for fname, inst, chi2, npk in results_ok:
            print(f"  {fname:<{col}}  {inst:<6}  {chi2:<10.4f}  {npk}")

    if results_fail:
        print(f"\n  FAILED FILES")
        print(f"  {'FILE':<{col}}  {'INST':<6}  REASON")
        for fname, inst, reason in results_fail:
            print(f"  {fname:<{col}}  {inst:<6}  {reason}")

    # Exit code: 0 if all succeeded, 1 if any failed
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    import logging
    # Only show WARNING and above so the per-file optimiser noise is suppressed
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    main()
