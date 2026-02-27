"""
Geometry conversion utilities — faithful Python port of the Nika tilt model.

Key functions
-------------
build_rotation_matrix   Rodrigues rotation from Nika tilt angles
expected_pixel_position Tilted-detector ring position (port of NI2T_CalculatePxPyWithTilts)
expected_ring_radius    Scalar distance from beam-center to ring
d_to_pixel_radius       Untilted ring radius
radial_profile_at_angle Extract 1-D intensity strip along a radial direction

Nika geometry convention (NI2T_ReadOrientationFromGlobals, NI1_ConvProc.ipf):
    d.R[0] = VerticalTilt   (rad)  <- stored as tilt_y / pin_ccd_tilt_y in HDF5
    d.R[1] = HorizontalTilt (rad)  <- stored as tilt_x / pin_ccd_tilt_x in HDF5
    d.R[2] = 0
"""

from __future__ import annotations
import numpy as np


# ---------------------------------------------------------------------------
# Rotation matrix
# ---------------------------------------------------------------------------

def build_rotation_matrix(tilt_x_deg: float, tilt_y_deg: float) -> np.ndarray:
    """
    Build the 3x3 Rodrigues rotation matrix from Nika tilt parameters.

    Direct port of NI2T_DetectorUpdateCalc (NI1_ConvProc.ipf line 7628).

    Parameters
    ----------
    tilt_x_deg : HorizontalTilt in degrees  (pin_ccd_tilt_x)  -> d.R[1]
    tilt_y_deg : VerticalTilt   in degrees  (pin_ccd_tilt_y)  -> d.R[0]
    """
    Rx = np.deg2rad(tilt_y_deg)   # d.R[0] = VerticalTilt
    Ry = np.deg2rad(tilt_x_deg)   # d.R[1] = HorizontalTilt
    Rz = 0.0

    theta = np.sqrt(Rx**2 + Ry**2 + Rz**2)
    if theta < 1e-10:
        return np.eye(3)

    c = np.cos(theta)
    s = np.sin(theta)
    c1 = 1.0 - c
    rx, ry, rz = Rx / theta, Ry / theta, Rz / theta

    # Rodrigues formula (mathworld.wolfram.com/RodriguesRotationFormula.html)
    return np.array([
        [c + rx*rx*c1,      rx*ry*c1 - rz*s,  ry*s + rx*rz*c1 ],
        [rz*s + rx*ry*c1,   c + ry*ry*c1,     -rx*s + ry*rz*c1],
        [-ry*s + rx*rz*c1,  rx*s + ry*rz*c1,   c + rz*rz*c1   ],
    ])


# ---------------------------------------------------------------------------
# Forward geometry: (d, azimuth) -> pixel position
# ---------------------------------------------------------------------------

def expected_pixel_position(
    theta_bragg: float,
    direction_rad: float,
    bcx: float,
    bcy: float,
    sdd_mm: float,
    pixel_size_mm: float,
    tilt_x_deg: float,
    tilt_y_deg: float,
) -> tuple[float, float]:
    """
    Expected detector pixel (column, row) for a diffraction ring.

    Direct Python port of NI2T_CalculatePxPyWithTilts
    (NI1_ConvProc.ipf line 7242).

    Parameters
    ----------
    theta_bragg   : Bragg angle (= 2theta / 2) in radians
    direction_rad : azimuthal angle in radians (0 = +column direction)
    bcx, bcy      : beam center (column, row) in pixels
    sdd_mm        : sample-to-detector distance in mm
    pixel_size_mm : pixel size in mm (assumed square)
    tilt_x_deg    : HorizontalTilt in degrees
    tilt_y_deg    : VerticalTilt   in degrees

    Returns
    -------
    (px_col, py_row) -- expected pixel coordinates, or (nan, nan) if degenerate.
    """
    rho = build_rotation_matrix(tilt_x_deg, tilt_y_deg)

    # Unit direction vector in the detector plane (pixel3XYZ without BCx/BCy shift)
    px_u = np.cos(direction_rad)
    py_u = np.sin(direction_rad)

    xyz = rho @ np.array([px_u, py_u, 0.0])
    norm = float(np.linalg.norm(xyz))
    if norm < 1e-10:
        return float("nan"), float("nan")
    xyz_n = xyz / norm

    # gamma = pi - acos( dot(xyz_n, ki) )   ki = [0, 0, 1]
    # (NI2T_pixelGamma: pi - acos(MatrixDot(kout, ki)))
    gamma = np.pi - np.arccos(float(np.clip(xyz_n[2], -1.0, 1.0)))

    two_theta = 2.0 * theta_bragg
    other_angle = np.pi - two_theta - gamma

    if abs(np.sin(other_angle)) < 1e-10:
        return float("nan"), float("nan")

    sdd_px = sdd_mm / pixel_size_mm
    dist = sdd_px * np.sin(two_theta) / np.sin(other_angle)

    return (
        bcx + dist * np.cos(direction_rad),
        bcy + dist * np.sin(direction_rad),
    )


def expected_ring_radius(
    theta_bragg: float,
    direction_rad: float,
    bcx: float,
    bcy: float,
    sdd_mm: float,
    pixel_size_mm: float,
    tilt_x_deg: float,
    tilt_y_deg: float,
) -> float:
    """
    Distance from beam-center to the expected ring position (pixels).

    Used as the model prediction for least-squares residuals.
    """
    px, py = expected_pixel_position(
        theta_bragg, direction_rad, bcx, bcy, sdd_mm, pixel_size_mm,
        tilt_x_deg, tilt_y_deg,
    )
    if not (np.isfinite(px) and np.isfinite(py)):
        return float("nan")
    return float(np.sqrt((px - bcx)**2 + (py - bcy)**2))


# ---------------------------------------------------------------------------
# Untilted helpers (fast, for initial estimates and display)
# ---------------------------------------------------------------------------

def d_to_pixel_radius(
    d_spacing: float,
    wavelength: float,
    sdd: float,
    pixel_size: float,
) -> float:
    """
    Ring radius on an *untilted* detector (pixels).

    r = SDD * tan(2theta) / pixel_size,   sin(theta) = lambda / (2*d)
    """
    sin_theta = wavelength / (2.0 * d_spacing)
    if abs(sin_theta) >= 1.0:
        raise ValueError(
            f"d_spacing={d_spacing} A too small for wavelength={wavelength} A "
            f"(sin theta = {sin_theta:.3f} >= 1)"
        )
    theta = np.arcsin(sin_theta)
    return sdd * np.tan(2.0 * theta) / pixel_size


def pixel_to_d(
    radius_px: float,
    wavelength: float,
    sdd: float,
    pixel_size: float,
) -> float:
    """Inverse of d_to_pixel_radius."""
    two_theta = np.arctan2(radius_px * pixel_size, sdd)
    return wavelength / (2.0 * np.sin(two_theta / 2.0))


def ring_xy(
    bcx: float,
    bcy: float,
    radius_px: float,
    n_points: int = 360,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (x, y) circle coordinates for GUI overlay display (no tilt)."""
    angles = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
    return bcx + radius_px * np.cos(angles), bcy + radius_px * np.sin(angles)


def ring_xy_tilted(
    d_spacing: float,
    wavelength: float,
    bcx: float,
    bcy: float,
    sdd_mm: float,
    pixel_size_mm: float,
    tilt_x_deg: float,
    tilt_y_deg: float,
    n_points: int = 360,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (x, y) pixel coordinates for a tilted-detector diffraction ring.

    Uses the full Nika tilt model (vectorised) so the displayed ring is an
    accurate ellipse for large tilts.  Returns NaN entries where the geometry
    is degenerate; callers should use ``connect='finite'`` in pyqtgraph.

    Returns empty arrays if the d-spacing is unreachable (sin θ ≥ 1).
    """
    sin_arg = wavelength / (2.0 * d_spacing)
    if abs(sin_arg) >= 1.0:
        return np.array([]), np.array([])
    theta = float(np.arcsin(sin_arg))

    rho = build_rotation_matrix(tilt_x_deg, tilt_y_deg)
    angles = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    # Rotate unit direction vectors; shape (3, n_points)
    vecs = np.vstack([cos_a, sin_a, np.zeros(n_points)])
    xyz = rho @ vecs                                           # (3, n)
    norms = np.linalg.norm(xyz, axis=0)                       # (n,)
    ok = norms > 1e-10
    xyz_n = np.where(ok, xyz / np.where(ok, norms, 1.0), 0.0)

    gamma = np.pi - np.arccos(np.clip(xyz_n[2], -1.0, 1.0))
    two_theta = 2.0 * theta
    other_angle = np.pi - two_theta - gamma

    sdd_px = sdd_mm / pixel_size_mm
    with np.errstate(invalid="ignore", divide="ignore"):
        dist = np.where(
            np.abs(other_angle) > 1e-10,
            sdd_px * np.sin(two_theta) / np.sin(other_angle),
            np.nan,
        )

    x = bcx + dist * cos_a
    y = bcy + dist * sin_a
    return x, y


# ---------------------------------------------------------------------------
# Radial profile extraction
# ---------------------------------------------------------------------------

def radial_profile_at_angle(
    image: np.ndarray,
    mask: np.ndarray,
    bcx: float,
    bcy: float,
    angle_rad: float,
    r_center: float,
    r_half_width: float,
    transverse_half_width: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """
    Extract a 1-D intensity profile along a radial strip.

    Mirrors Nika's ImageLineProfile approach (NI1_BeamCenterUtils.ipf line 2409):
    traces a straight path at angle_rad from the beam center, averaging
    transverse_half_width pixels on each side perpendicular to the radial
    direction.

    Parameters
    ----------
    image : np.ndarray, shape (ny, nx)
    mask  : np.ndarray bool, shape (ny, nx) -- True = pixel excluded
    bcx, bcy : beam center (column, row) in pixels
    angle_rad : azimuthal direction
    r_center  : expected ring radius (pixels)
    r_half_width : search half-window around r_center (pixels)
    transverse_half_width : averaging strip half-width perpendicular to radial

    Returns
    -------
    radii       : 1-D array of radial distances (pixels)
    intensities : 1-D array of mean intensities (NaN where no valid pixels)
    within_detector : False if the strip extends outside the image bounds
    """
    ny, nx = image.shape
    r_max = r_center + r_half_width
    # Mirror the Igor approach: check that the search window itself is within
    # the detector — NOT the full path from the beam center (which may be
    # outside the image for edge/partial-view geometries).
    r_check_inner = max(1.0, r_center - r_half_width)
    r_min = max(0.0, r_center - r_half_width)

    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    cos_p = -sin_a          # perpendicular (transverse) direction
    sin_p =  cos_a

    # Quick bounds check at corners of the SEARCH STRIP only
    for r in (r_check_inner, r_max):
        for dp in (-transverse_half_width, transverse_half_width):
            xi = bcx + r * cos_a + dp * cos_p
            yi = bcy + r * sin_a + dp * sin_p
            if not (0 <= xi < nx and 0 <= yi < ny):
                return np.array([]), np.array([]), False

    n_r = max(2, int(round(r_max - r_min)) + 1)
    radii = np.linspace(r_min, r_max, n_r)

    n_trans = max(3, int(2 * transverse_half_width) + 1)
    dp_arr = np.linspace(-transverse_half_width, transverse_half_width, n_trans)

    # Vectorised: compute all (n_r × n_trans) pixel coordinates at once
    cols = np.round(bcx + radii[:, None] * cos_a + dp_arr[None, :] * cos_p).astype(int)
    rows = np.round(bcy + radii[:, None] * sin_a + dp_arr[None, :] * sin_p).astype(int)

    in_bounds = (cols >= 0) & (cols < nx) & (rows >= 0) & (rows < ny)
    safe_cols = np.clip(cols, 0, nx - 1)
    safe_rows = np.clip(rows, 0, ny - 1)

    img_vals = image[safe_rows, safe_cols].astype(float)
    is_masked = mask[safe_rows, safe_cols]
    valid = in_bounds & ~is_masked & np.isfinite(img_vals)

    # Use explicit sum/count to avoid RuntimeWarning from nanmean on all-NaN rows
    n_valid = valid.sum(axis=1)                            # (n_r,)
    sum_vals = np.where(valid, img_vals, 0.0).sum(axis=1)  # (n_r,)
    intensities = np.where(n_valid > 0, sum_vals / np.where(n_valid > 0, n_valid, 1), np.nan)

    return radii, intensities, True
