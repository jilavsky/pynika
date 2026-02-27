"""
Least-squares optimiser for detector geometry calibration.

Algorithm overview (stub — see doc/implementation_plan.md for full spec):

1.  For each enabled calibrant d-spacing:
    a.  Compute the theoretical ring radius r₀ (pixels) from d, λ, SDD.
    b.  At each azimuthal direction (step_deg increments around 360°):
        i.  Extract a radial intensity profile ±search_width pixels around r₀.
        ii. Fit a Gaussian + linear background; record peak position if fit converges.
        iii. Skip directions where the strip falls outside the detector or in dead zones.
2.  For each fitted peak position, compare against the model prediction at the
    current parameter values (bcx, bcy, sdd, tilt_x, tilt_y) using the Nika
    geometry model.
3.  Minimise the sum of squared residuals (fitted position − model position)
    over all peaks using scipy.optimize.least_squares.

This module provides stub implementations of each step.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FitConfig:
    """Configuration for the ring-fitting optimisation."""

    step_deg: float = 1.0              # azimuthal step in degrees
    transverse_px: float = 5.0        # strip half-width perpendicular to radial (px)
    fit_bcx: bool = True
    fit_bcy: bool = True
    fit_sdd: bool = True
    fit_tilt_x: bool = True
    fit_tilt_y: bool = True
    bcx_limits: tuple[float, float] = (-np.inf, np.inf)
    bcy_limits: tuple[float, float] = (-np.inf, np.inf)
    sdd_limits: tuple[float, float] = (0.0, np.inf)
    tilt_x_limits: tuple[float, float] = (-45.0, 45.0)
    tilt_y_limits: tuple[float, float] = (-45.0, 45.0)


@dataclass
class PeakFit:
    """Result of a single Gaussian fit along one radial strip."""

    d_spacing: float
    angle_deg: float
    radius_px: float
    amplitude: float
    fwhm: float
    chi_square: float
    converged: bool


@dataclass
class OptimisationResult:
    """Result of the full geometry optimisation."""

    sdd: float
    bcx: float
    bcy: float
    tilt_x: float
    tilt_y: float
    chi_square: float
    n_peaks_used: int
    success: bool
    message: str
    peak_fits: list[PeakFit] = field(default_factory=list)


def fit_gaussian_linear(
    x: np.ndarray,
    y: np.ndarray,
) -> Optional[dict]:
    """
    Fit  f(x) = A·exp(-0.5·((x-μ)/σ)²) + m·x + b  to data.

    Returns a dict with keys {amplitude, center, sigma, slope, intercept,
    chi_square} or None if the fit did not converge.

    This is a stub — implementation to follow.
    """
    raise NotImplementedError("fit_gaussian_linear not yet implemented")


def find_ring_peaks(
    image: np.ndarray,
    mask: np.ndarray,
    bcx: float,
    bcy: float,
    d_spacing: float,
    wavelength: float,
    sdd: float,
    pixel_size: float,
    search_width: float,
    config: FitConfig,
) -> list[PeakFit]:
    """
    Scan azimuthally around the theoretical ring position for *d_spacing* and
    fit a Gaussian at each direction.

    Returns a list of :class:`PeakFit` (only converged fits).

    This is a stub — implementation to follow.
    """
    raise NotImplementedError("find_ring_peaks not yet implemented")


def optimise_geometry(
    image: np.ndarray,
    mask: np.ndarray,
    calibrant,          # pynika.calibrants.Calibrant
    wavelength: float,
    pixel_size: float,
    sdd_init: float,
    bcx_init: float,
    bcy_init: float,
    tilt_x_init: float,
    tilt_y_init: float,
    config: Optional[FitConfig] = None,
) -> OptimisationResult:
    """
    Run the full least-squares geometry optimisation.

    Steps:
    1.  Build pixel mask from *mask*.
    2.  For each enabled d-spacing in *calibrant*, call :func:`find_ring_peaks`.
    3.  Feed collected peak positions to scipy.optimize.least_squares.
    4.  Return :class:`OptimisationResult`.

    This is a stub — implementation to follow.
    """
    raise NotImplementedError("optimise_geometry not yet implemented")
