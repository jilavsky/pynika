"""
HDF5 read/write routines for pyNika.

Follows the HDF5 layout produced by the APS/USAXS area-detector data
collection system (see examples/convertSWAXS.py for the reference reader).
"""

from __future__ import annotations
import logging
from typing import Any

import numpy as np
import h5py

log = logging.getLogger(__name__)

# Metadata keys to load from /entry/Metadata
_METADATA_KEYS = [
    "pin_ccd_center_x_pixel", "pin_ccd_center_y_pixel",
    "pin_ccd_tilt_x", "pin_ccd_tilt_y",
    "waxs_ccd_center_x_pixel", "waxs_ccd_center_y_pixel",
    "waxs_ccd_tilt_x", "waxs_ccd_tilt_y",
    "wavelength", "monoE",
    "StartTime",
]


def load_image_and_params(hdf5_path: str) -> dict[str, Any]:
    """
    Load a 2D detector image and all calibration-relevant parameters from an
    HDF5 file.

    Returns
    -------
    dict with keys:
        "image"      : np.ndarray (2D)
        "sdd"        : float  (mm)
        "pixel_size" : float  (mm)
        "wavelength" : float  (Å)
        "bcx"        : float  (pixels, from metadata)
        "bcy"        : float  (pixels, from metadata)
        "tilt_x"     : float  (degrees)
        "tilt_y"     : float  (degrees)
        "instrument" : str    ("SAXS" | "WAXS" | "unknown")
        "metadata"   : dict   (full /entry/Metadata subset)
    """
    with h5py.File(hdf5_path, "r") as f:
        image = np.array(f["/entry/data/data"])

        # Instrument subtree
        det = f["/entry/instrument/detector"]
        sdd = float(det["distance"][()])
        pixel_size = float(det["x_pixel_size"][()])
        bcx_inst = float(det["beam_center_x"][()])
        bcy_inst = float(det["beam_center_y"][()])

        mono = f["/entry/instrument/monochromator"]
        wavelength = float(mono["wavelength"][()])

        # Metadata subtree (scalar PV snapshots)
        meta_grp = f["/entry/Metadata"]
        metadata: dict[str, Any] = {}
        for key in _METADATA_KEYS:
            if key in meta_grp:
                val = meta_grp[key][()]
                metadata[key] = float(val) if np.ndim(val) == 0 else val

    # Determine instrument and pick the right metadata keys
    if "pin_ccd_tilt_x" in metadata:
        instrument = "SAXS"
        bcx = metadata.get("pin_ccd_center_x_pixel", bcx_inst)
        bcy = metadata.get("pin_ccd_center_y_pixel", bcy_inst)
        tilt_x = metadata.get("pin_ccd_tilt_x", 0.0)
        tilt_y = metadata.get("pin_ccd_tilt_y", 0.0)
    elif "waxs_ccd_tilt_x" in metadata:
        instrument = "WAXS"
        bcx = metadata.get("waxs_ccd_center_x_pixel", bcx_inst)
        bcy = metadata.get("waxs_ccd_center_y_pixel", bcy_inst)
        tilt_x = metadata.get("waxs_ccd_tilt_x", 0.0)
        tilt_y = metadata.get("waxs_ccd_tilt_y", 0.0)
    else:
        instrument = "unknown"
        bcx, bcy, tilt_x, tilt_y = bcx_inst, bcy_inst, 0.0, 0.0

    log.info(
        "Loaded %s: image %s, sdd=%.1f mm, λ=%.4f Å, bcx=%.1f, bcy=%.1f",
        hdf5_path, image.shape, sdd, wavelength, bcx, bcy,
    )
    return {
        "image": image,
        "sdd": sdd,
        "pixel_size": pixel_size,
        "wavelength": wavelength,
        "bcx": float(bcx),
        "bcy": float(bcy),
        "tilt_x": float(tilt_x),
        "tilt_y": float(tilt_y),
        "instrument": instrument,
        "metadata": metadata,
    }


def save_params_to_hdf5(
    hdf5_path: str,
    instrument: str,
    sdd: float,
    bcx: float,
    bcy: float,
    tilt_x: float,
    tilt_y: float,
) -> None:
    """
    Write optimised calibration parameters back into the HDF5 file.

    Updates both the /entry/instrument/detector subtree and the
    /entry/Metadata scalar PVs (whichever exist).
    """
    with h5py.File(hdf5_path, "r+") as f:
        det = f["/entry/instrument/detector"]
        det["distance"][()] = sdd
        det["beam_center_x"][()] = bcx
        det["beam_center_y"][()] = bcy

        meta = f["/entry/Metadata"]
        if instrument == "SAXS":
            _write_if_exists(meta, "pin_ccd_center_x_pixel", bcx)
            _write_if_exists(meta, "pin_ccd_center_y_pixel", bcy)
            _write_if_exists(meta, "pin_ccd_tilt_x", tilt_x)
            _write_if_exists(meta, "pin_ccd_tilt_y", tilt_y)
        elif instrument == "WAXS":
            _write_if_exists(meta, "waxs_ccd_center_x_pixel", bcx)
            _write_if_exists(meta, "waxs_ccd_center_y_pixel", bcy)
            _write_if_exists(meta, "waxs_ccd_tilt_x", tilt_x)
            _write_if_exists(meta, "waxs_ccd_tilt_y", tilt_y)

    log.info("Saved parameters to %s", hdf5_path)


def _write_if_exists(group: h5py.Group, key: str, value: float) -> None:
    if key in group:
        group[key][()] = value
    else:
        log.warning("HDF5 key '%s' not found — skipping write", key)
