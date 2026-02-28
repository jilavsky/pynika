"""
EPICS PV read/write for pyNika.

Wraps pyepics with graceful degradation: if pyepics is not installed or the
PVs are unreachable (e.g. on an off-site workstation), the values that *would*
have been written are printed to the console instead of raising an exception.

Console echo format
-------------------
Every PV write attempt is printed to the console so the operator can verify
the values even without an EPICS client:

    [PV OK]          usxLAX:SAXS:SDD    = 1523.456   (SAXS SDD)
    [PV UNREACHABLE] usxLAX:SAXS:BCx    = 512.300    (SAXS beam center X)
    [PV SIMULATED]   usxLAX:SAXS:BCy    = 480.100    (SAXS beam center Y, pyepics not installed)

A summary line is printed after all PV writes are attempted.
"""

from __future__ import annotations
import datetime
import logging
from typing import Optional

log = logging.getLogger(__name__)

try:
    import epics as _epics
    _EPICS_AVAILABLE = True
except ImportError:
    _epics = None  # type: ignore[assignment]
    _EPICS_AVAILABLE = False


def _put(pv_name: str, value: float | str, label: str = "", timeout: float = 5.0) -> bool:
    """
    Attempt to write *value* to *pv_name*.

    Always prints a one-line status to the console showing the PV name,
    value, and outcome (OK / UNREACHABLE / SIMULATED).

    Parameters
    ----------
    pv_name : EPICS PV name string
    value   : value to write (float or string)
    label   : human-readable description for the console line (optional)
    timeout : connection/put timeout in seconds

    Returns
    -------
    True if the PV was successfully written, False otherwise.
    """
    if not pv_name:
        # PV name not configured — skip silently
        return False

    tag = f"  ({label})" if label else ""

    if not _EPICS_AVAILABLE:
        print(f"  [PV SIMULATED]   {pv_name:<40s} = {value!r:<16}{tag}  (pyepics not installed)")
        log.warning("pyepics not installed — PV '%s' not written", pv_name)
        return False

    try:
        pv = _epics.PV(pv_name, connection_timeout=timeout)
        if not pv.connected:
            print(f"  [PV UNREACHABLE] {pv_name:<40s} = {value!r:<16}{tag}")
            log.warning("PV unreachable: %s", pv_name)
            return False

        pv.put(value, timeout=timeout)
        print(f"  [PV OK]          {pv_name:<40s} = {value!r:<16}{tag}")
        log.info("PV set: %s = %r", pv_name, value)
        return True

    except Exception as exc:
        print(f"  [PV ERROR]       {pv_name:<40s} = {value!r:<16}{tag}  error: {exc}")
        log.error("PV write error for %s: %s", pv_name, exc)
        return False


def write_calibration_to_pvs(
    pv_map: dict[str, str],
    sdd: float,
    bcx: float,
    bcy: float,
    tilt_x: float,
    tilt_y: float,
    report_message: Optional[str] = None,
) -> dict[str, bool]:
    """
    Write optimised calibration parameters to EPICS PVs.

    Prints a human-readable table of every PV write attempt with its outcome
    so the operator can verify the operation at a glance.

    Parameters
    ----------
    pv_map : dict
        Mapping from parameter name to PV name.  Expected keys:
        "bcx", "bcy", "tilt_x", "tilt_y", "sdd", "report".
    sdd, bcx, bcy, tilt_x, tilt_y : float
        Optimised geometry parameters.
    report_message : str, optional
        Short message to write to the CalibrationReport PV.  A default
        timestamp message is used if None.

    Returns
    -------
    dict mapping parameter names to True (written) / False (failed).
    """
    if report_message is None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_message = f"pyNika calibration OK at {ts}"

    print("pyNika: writing calibration parameters to EPICS PVs …")

    results: dict[str, bool] = {}
    results["sdd"]    = _put(pv_map.get("sdd",    ""), sdd,            label="SDD (mm)")
    results["bcx"]    = _put(pv_map.get("bcx",    ""), bcx,            label="beam center X (px)")
    results["bcy"]    = _put(pv_map.get("bcy",    ""), bcy,            label="beam center Y (px)")
    results["tilt_x"] = _put(pv_map.get("tilt_x", ""), tilt_x,         label="TiltX (deg)")
    results["tilt_y"] = _put(pv_map.get("tilt_y", ""), tilt_y,         label="TiltY (deg)")
    results["report"] = _put(pv_map.get("report", ""), report_message, label="CalibrationReport")

    n_ok    = sum(results.values())
    n_total = sum(1 for v in pv_map.values() if v)  # only count configured PVs
    n_total = max(n_total, len(results))
    status  = "ALL OK" if n_ok == n_total else f"{n_ok}/{n_total} written"
    print(f"pyNika: PV write complete — {status}")
    return results


def write_failure_report(pv_map: dict[str, str], reason: str = "calibration failed") -> None:
    """Write a failure message to the CalibrationReport PV (or console)."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"pyNika FAILED: {reason} at {ts}"
    print(f"pyNika: writing failure report to EPICS CalibrationReport PV …")
    _put(pv_map.get("report", ""), msg, label="CalibrationReport (failure)")
