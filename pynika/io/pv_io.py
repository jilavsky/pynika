"""
EPICS PV read/write for pyNika.

Wraps pyepics with graceful degradation: if pyepics is not installed or the
PVs are unreachable (e.g. on an off-site workstation), the values that *would*
have been written are printed to the console instead of raising an exception.
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


def _put(pv_name: str, value: float | str, timeout: float = 5.0) -> bool:
    """
    Attempt to write *value* to *pv_name*.

    Returns True on success, False on failure (timeout / connection error).
    Prints a console message on failure instead of raising.
    """
    if not _EPICS_AVAILABLE:
        print(f"  [PV would be set]  {pv_name} = {value!r}  (pyepics not installed)")
        return False

    pv = _epics.PV(pv_name, connection_timeout=timeout)
    if not pv.connected:
        print(f"  [PV unreachable]   {pv_name} = {value!r}")
        return False

    pv.put(value, timeout=timeout)
    log.info("PV set: %s = %r", pv_name, value)
    return True


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
    dict mapping parameter names to True/False (write success).
    """
    if report_message is None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_message = f"pyNika calibration OK at {ts}"

    results: dict[str, bool] = {}
    results["bcx"]    = _put(pv_map["bcx"],    bcx)
    results["bcy"]    = _put(pv_map["bcy"],    bcy)
    results["tilt_x"] = _put(pv_map["tilt_x"], tilt_x)
    results["tilt_y"] = _put(pv_map["tilt_y"], tilt_y)
    results["sdd"]    = _put(pv_map["sdd"],    sdd)
    results["report"] = _put(pv_map["report"], report_message)
    return results


def write_failure_report(pv_map: dict[str, str], reason: str = "calibration failed") -> None:
    """Write a failure message to the CalibrationReport PV (or console)."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"pyNika {reason} at {ts}"
    _put(pv_map.get("report", ""), msg)
