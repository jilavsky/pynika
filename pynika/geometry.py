"""
Geometry conversion utilities following Nika conventions.

Nika defines detector geometry with:
    BeamCenterX, BeamCenterY  — beam center in pixels (Nika x/y convention)
    SDD                       — sample-to-detector distance in mm
    TiltX, TiltY              — detector tilt angles in degrees

The relationship between pixel radius r (pixels) and scattering angle 2θ
for a tilted detector is computed as in Nika (NI1_ConvProc.ipf).

All units follow Nika:
    distances   → mm
    pixel sizes → mm
    angles      → degrees
    d-spacings  → Angstroms
    wavelength  → Angstroms
"""

from __future__ import annotations
import numpy as np


def d_to_pixel_radius(
    d_spacing: float,
    wavelength: float,
    sdd: float,
    pixel_size: float,
) -> float:
    """
    Convert a d-spacing to an expected ring radius on the detector (pixels).

    Uses Bragg's law and the small-angle approximation:
        r = SDD * tan(2θ) / pixel_size

    where  sin(θ) = λ / (2d).

    Parameters
    ----------
    d_spacing : float
        d-spacing in Angstroms.
    wavelength : float
        X-ray wavelength in Angstroms.
    sdd : float
        Sample-to-detector distance in mm.
    pixel_size : float
        Pixel size in mm.

    Returns
    -------
    float
        Expected ring radius in pixels.
    """
    sin_theta = wavelength / (2.0 * d_spacing)
    if sin_theta >= 1.0:
        raise ValueError(
            f"d_spacing={d_spacing} Å too small for wavelength={wavelength} Å "
            f"(sin θ = {sin_theta:.3f} ≥ 1)"
        )
    theta = np.arcsin(sin_theta)
    return sdd * np.tan(2.0 * theta) / pixel_size


def pixel_to_d(
    radius_px: float,
    wavelength: float,
    sdd: float,
    pixel_size: float,
) -> float:
    """Inverse of :func:`d_to_pixel_radius`."""
    two_theta = np.arctan(radius_px * pixel_size / sdd)
    return wavelength / (2.0 * np.sin(two_theta / 2.0))


def ring_xy(
    bcx: float,
    bcy: float,
    radius_px: float,
    n_points: int = 360,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return x, y coordinates of a ring on the detector (no tilt correction).

    For display purposes only.  The optimiser uses the tilted model.
    """
    angles = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
    x = bcx + radius_px * np.cos(angles)
    y = bcy + radius_px * np.sin(angles)
    return x, y


def radial_profile_at_angle(
    image: np.ndarray,
    bcx: float,
    bcy: float,
    angle_rad: float,
    r_center: float,
    r_half_width: float,
    transverse_half_width: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract an intensity profile along the radial direction at a given angle.

    Averages `transverse_half_width` pixels on each side perpendicular to the
    radial direction to improve statistics (mirrors the Nika approach).

    Parameters
    ----------
    image : np.ndarray, shape (ny, nx)
        2D detector image.  NaN values are ignored.
    bcx, bcy : float
        Beam center in pixels.
    angle_rad : float
        Azimuthal angle in radians (0 = +x axis, increases CCW).
    r_center : float
        Theoretical ring radius at this angle (pixels).
    r_half_width : float
        Search range ±r_half_width pixels around r_center.
    transverse_half_width : float
        Half-width of the strip perpendicular to the radial direction (pixels).

    Returns
    -------
    radii : np.ndarray
        Radial positions (pixels from beam center).
    intensities : np.ndarray
        Mean intensity at each radial position.
    """
    ny, nx = image.shape
    r_min = max(0.0, r_center - r_half_width)
    r_max = r_center + r_half_width
    n_r = int(r_max - r_min) + 1
    radii = np.linspace(r_min, r_max, n_r)
    intensities = np.full(n_r, np.nan)

    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    # perpendicular direction
    cos_p = -sin_a
    sin_p = cos_a

    for i, r in enumerate(radii):
        # sample a strip of pixels perpendicular to the radial direction
        samples = []
        for dp in np.linspace(-transverse_half_width, transverse_half_width, int(2 * transverse_half_width) + 1):
            px = bcx + r * cos_a + dp * cos_p
            py = bcy + r * sin_a + dp * sin_p
            ix = int(round(px))
            iy = int(round(py))
            if 0 <= ix < nx and 0 <= iy < ny:
                val = image[iy, ix]
                if np.isfinite(val):
                    samples.append(val)
        if samples:
            intensities[i] = np.mean(samples)

    return radii, intensities
