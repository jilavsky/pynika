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


def _scalar(v) -> float:
    """Extract a Python float from an HDF5 value that may be shape () or (1,)."""
    return float(np.asarray(v).flat[0])


_METADATA_KEYS = [
    "pin_ccd_center_x_pixel", "pin_ccd_center_y_pixel",
    "pin_ccd_tilt_x", "pin_ccd_tilt_y",
    "waxs_ccd_center_x_pixel", "waxs_ccd_center_y_pixel",
    "waxs_ccd_tilt_x", "waxs_ccd_tilt_y",
    "wavelength", "monoE", "StartTime",
]


def load_image_and_params(hdf5_path: str) -> dict[str, Any]:
    """
    Load the 2-D detector image and all calibration-relevant parameters.

    Returns
    -------
    dict with keys:
        "image"      : np.ndarray float64 (ny, nx)
        "mask"       : np.ndarray bool    (ny, nx) — True = excluded
        "sdd"        : float  sample-to-detector distance (mm)
        "pixel_size" : float  pixel size (mm)
        "wavelength" : float  X-ray wavelength (Angstrom)
        "bcx"        : float  beam center column (pixels)
        "bcy"        : float  beam center row    (pixels)
        "tilt_x"     : float  HorizontalTilt (degrees)
        "tilt_y"     : float  VerticalTilt   (degrees)
        "instrument" : str    "SAXS" | "WAXS" | "unknown"
        "metadata"   : dict
        "hdf5_path"  : str
    """
    with h5py.File(hdf5_path, "r") as f:
        # 2-D image — squeeze away any singleton dimensions.
        # The HDF5 file stores the image in Nika/Igor Pro convention:
        #   image[x_index, y_index]  where x is the SHORT (horizontal) dimension
        #   and y is the LONG (vertical) dimension — opposite to numpy (row, col).
        # Transpose immediately so the rest of the code uses the standard numpy
        # convention:  image[row, col] = image[y_index, x_index].
        raw = np.array(f["/entry/data/data"], dtype=np.float64)
        image = np.squeeze(raw)
        if image.ndim != 2:
            raise ValueError(
                f"Expected 2-D image in /entry/data/data, got shape {raw.shape}"
            )
        image = image.T   # (nx_short, ny_long) → (ny_long, nx_short)

        # Instrument subtree
        det = f["/entry/instrument/detector"]
        sdd        = _scalar(det["distance"][()])
        pixel_size = _scalar(det["x_pixel_size"][()])
        bcx_inst   = _scalar(det["beam_center_x"][()])
        bcy_inst   = _scalar(det["beam_center_y"][()])

        wavelength = _scalar(f["/entry/instrument/monochromator"]["wavelength"][()])

        # Metadata scalars (PV snapshots recorded at acquisition time)
        meta_grp = f["/entry/Metadata"]
        metadata: dict[str, Any] = {}
        for key in _METADATA_KEYS:
            if key in meta_grp:
                val = meta_grp[key][()]
                try:
                    metadata[key] = _scalar(val)
                except (ValueError, TypeError):
                    metadata[key] = val  # keep strings and other non-numeric types

    # Auto-detect SAXS vs WAXS from metadata keys
    if "pin_ccd_tilt_x" in metadata:
        instrument = "SAXS"
        bcx    = float(metadata.get("pin_ccd_center_x_pixel", bcx_inst))
        bcy    = float(metadata.get("pin_ccd_center_y_pixel", bcy_inst))
        tilt_x = float(metadata.get("pin_ccd_tilt_x", 0.0))
        tilt_y = float(metadata.get("pin_ccd_tilt_y", 0.0))
    elif "waxs_ccd_tilt_x" in metadata:
        instrument = "WAXS"
        bcx    = float(metadata.get("waxs_ccd_center_x_pixel", bcx_inst))
        bcy    = float(metadata.get("waxs_ccd_center_y_pixel", bcy_inst))
        tilt_x = float(metadata.get("waxs_ccd_tilt_x", 0.0))
        tilt_y = float(metadata.get("waxs_ccd_tilt_y", 0.0))
    else:
        instrument = "unknown"
        bcx, bcy, tilt_x, tilt_y = bcx_inst, bcy_inst, 0.0, 0.0

    mask = make_mask(image, instrument)

    log.info(
        "Loaded %s %s: shape=%s sdd=%.1f mm lam=%.4f A bcx=%.1f bcy=%.1f",
        instrument, hdf5_path, image.shape, sdd, wavelength, bcx, bcy,
    )

    return {
        "image": image,
        "mask": mask,
        "sdd": sdd,
        "pixel_size": pixel_size,
        "wavelength": wavelength,
        "bcx": bcx,
        "bcy": bcy,
        "tilt_x": tilt_x,
        "tilt_y": tilt_y,
        "instrument": instrument,
        "metadata": metadata,
        "hdf5_path": hdf5_path,
    }


def make_mask(image: np.ndarray, instrument: str) -> np.ndarray:
    """
    Build the bad-pixel mask for the given instrument.

    *image* is assumed to already be in numpy convention (ny, nx) after the
    load-time transpose applied in load_image_and_params.

    Returns a boolean array, same shape as *image*, where True = excluded.

    SAXS (Eiger):
        mask negative pixels + dead bands at y-rows 0-3 and 242-244
        (in the original Nika/Igor image these were axis-1 columns 0-3 and
        242-244; after the (nx,ny)→(ny,nx) transpose they become axis-0 rows).

    WAXS (Pilatus):
        mask pixels > 1e7 + module-gap rows 511-515, 1026-1040, 1551-1555
        (same axis convention after transpose).
    """
    mask = np.zeros(image.shape, dtype=bool)

    if instrument == "SAXS":
        mask[image < 0] = True
        mask[:4, :]      = True   # dead band y=0–3   (was mask[:, :4] on raw image)
        mask[242:245, :] = True   # dead band y=242–244 (was mask[:, 242:245] on raw)
    elif instrument == "WAXS":
        mask[image > 1e7]  = True
        mask[511:516, :]   = True   # module gap (was mask[:, 511:516] on raw)
        mask[1026:1041, :] = True   # module gap (was mask[:, 1026:1041] on raw)
        mask[1551:1556, :] = True   # module gap (was mask[:, 1551:1556] on raw)
    # "unknown" or "Custom": no masking by default

    n_masked = int(np.sum(mask))
    log.debug("Mask: %d / %d pixels excluded (%.1f%%)",
              n_masked, mask.size, 100.0 * n_masked / mask.size)
    return mask


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

    Updates /entry/instrument/detector datasets and /entry/Metadata scalars.
    """
    with h5py.File(hdf5_path, "r+") as f:
        det = f["/entry/instrument/detector"]
        det["distance"][()]      = sdd
        det["beam_center_x"][()] = bcx
        det["beam_center_y"][()] = bcy

        meta = f["/entry/Metadata"]
        if instrument == "SAXS":
            _write_if_exists(meta, "pin_ccd_center_x_pixel", bcx)
            _write_if_exists(meta, "pin_ccd_center_y_pixel", bcy)
            _write_if_exists(meta, "pin_ccd_tilt_x",         tilt_x)
            _write_if_exists(meta, "pin_ccd_tilt_y",         tilt_y)
        elif instrument == "WAXS":
            _write_if_exists(meta, "waxs_ccd_center_x_pixel", bcx)
            _write_if_exists(meta, "waxs_ccd_center_y_pixel", bcy)
            _write_if_exists(meta, "waxs_ccd_tilt_x",         tilt_x)
            _write_if_exists(meta, "waxs_ccd_tilt_y",         tilt_y)

    log.info("Saved parameters to %s", hdf5_path)


def _write_if_exists(group: h5py.Group, key: str, value: float) -> None:
    if key in group:
        group[key][()] = value
    else:
        log.warning("HDF5 key '%s' not found — skipping write", key)
