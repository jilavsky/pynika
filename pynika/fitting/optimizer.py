"""
Least-squares optimiser for SAXS/WAXS detector geometry calibration.

Algorithm (mirrors Nika, NI1_BeamCenterUtils.ipf):
  1. For each enabled calibrant d-spacing:
     a. Compute expected ring radius at each azimuthal angle using the
        tilted-detector model (expected_ring_radius from geometry.py).
     b. Extract a 1-D radial intensity profile in a search window around the
        expected radius (radial_profile_at_angle).
     c. Fit Gaussian + linear background; record the peak radial position.
     d. Skip azimuthal directions outside detector bounds or with too many
        masked pixels.
  2. Collect all fitted peak positions (d, angle, radius_fit).
  3. Run scipy.optimize.least_squares: residual = radius_fit - radius_model(params).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import curve_fit, least_squares

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FitConfig:
    """Configuration for the ring-fitting optimisation."""

    step_deg: float = 1.0               # azimuthal step in degrees
    transverse_px: float = 5.0          # strip half-width perpendicular to radial (px)
    masked_fraction_limit: float = 0.5  # skip strip if >50% transverse pixels masked

    fit_bcx: bool = True
    fit_bcy: bool = True
    fit_sdd: bool = True
    fit_tilt_x: bool = True
    fit_tilt_y: bool = True

    bcx_limits: tuple[float, float] = (-np.inf, np.inf)
    bcy_limits: tuple[float, float] = (-np.inf, np.inf)
    sdd_limits: tuple[float, float] = (1.0, np.inf)
    tilt_x_limits: tuple[float, float] = (-45.0, 45.0)
    tilt_y_limits: tuple[float, float] = (-45.0, 45.0)

    min_amplitude_sigma: float = 2.0   # peak must exceed background by N*std
    min_peaks_per_ring: int = 10       # minimum fitted peaks per d-spacing


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PeakFit:
    """Result of a single Gaussian fit along one radial strip."""

    d_spacing: float
    angle_deg: float
    radius_px: float      # fitted peak position (pixels from beam center)
    amplitude: float
    fwhm: float
    chi_square: float
    converged: bool = True


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


# ---------------------------------------------------------------------------
# Gaussian fitting
# ---------------------------------------------------------------------------

def _gauss_linear(x: np.ndarray, A: float, mu: float, sigma: float,
                  m: float, b: float) -> np.ndarray:
    return A * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + m * x + b


def fit_gaussian_linear(
    x: np.ndarray,
    y: np.ndarray,
) -> Optional[dict]:
    """
    Fit  f(x) = A*exp(-0.5*((x-mu)/sigma)^2) + m*x + b  to noisy data.

    Returns a dict with keys {amplitude, center, sigma, slope, intercept,
    chi_square} or None if the fit did not converge.
    """
    valid = np.isfinite(y)
    if valid.sum() < 5:
        return None

    xv = x[valid]
    yv = y[valid]

    # Initial guesses
    idx_max = int(np.argmax(yv))
    y_low = float(np.percentile(yv, 20))
    A0 = float(yv[idx_max]) - y_low
    mu0 = float(xv[idx_max])
    sigma0 = max(1.0, (float(xv[-1]) - float(xv[0])) / 4.0)
    span = float(xv[-1]) - float(xv[0])
    m0 = (float(yv[-1]) - float(yv[0])) / span if span > 0 else 0.0
    b0 = float(yv[0]) - m0 * float(xv[0])

    p0 = [max(A0, 1.0), mu0, sigma0, m0, b0]
    lb = [0.0,      float(xv[0]),  1e-3,  -np.inf, -np.inf]
    ub = [np.inf,   float(xv[-1]), span,   np.inf,  np.inf]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(
                _gauss_linear, xv, yv,
                p0=p0, bounds=(lb, ub), maxfev=2000,
            )
        A, mu, sigma, m, b = popt
        residuals = yv - _gauss_linear(xv, *popt)
        chi2 = float(np.sum(residuals**2)) / max(1, len(yv) - 5)
        return {
            "amplitude": float(A),
            "center": float(mu),
            "sigma": float(abs(sigma)),
            "slope": float(m),
            "intercept": float(b),
            "chi_square": chi2,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ring peak finding
# ---------------------------------------------------------------------------

def find_ring_peaks(
    image: np.ndarray,
    mask: np.ndarray,
    bcx: float,
    bcy: float,
    d_spacing: float,
    wavelength: float,
    sdd_mm: float,
    pixel_size_mm: float,
    search_width: float,
    tilt_x_deg: float,
    tilt_y_deg: float,
    config: FitConfig,
) -> list[PeakFit]:
    """
    Scan azimuthally around the expected ring for *d_spacing* and fit a
    Gaussian at each direction.

    Returns converged PeakFit objects (one per azimuthal direction where a
    peak was found within the search window).
    """
    from pynika.geometry import expected_ring_radius, radial_profile_at_angle

    sin_arg = wavelength / (2.0 * d_spacing)
    if abs(sin_arg) >= 1.0:
        log.warning("d=%.4f A unreachable with lambda=%.4f A — skipping", d_spacing, wavelength)
        return []
    theta_bragg = float(np.arcsin(sin_arg))

    ny, nx = image.shape
    peaks: list[PeakFit] = []
    angles_deg = np.arange(0.0, 360.0, config.step_deg)

    for angle_deg in angles_deg:
        angle_rad = float(np.deg2rad(angle_deg))

        # Expected ring radius at this azimuthal angle
        r_center = expected_ring_radius(
            theta_bragg, angle_rad, bcx, bcy, sdd_mm, pixel_size_mm,
            tilt_x_deg, tilt_y_deg,
        )
        if not np.isfinite(r_center) or r_center <= 0:
            continue

        # Extract radial profile
        radii, intensities, within = radial_profile_at_angle(
            image, mask, bcx, bcy, angle_rad,
            r_center, search_width, config.transverse_px,
        )
        if not within or len(radii) < 5:
            continue

        # Skip if too many NaN (masked) points
        nan_frac = float(np.sum(~np.isfinite(intensities))) / len(intensities)
        if nan_frac > config.masked_fraction_limit:
            continue

        # Fit Gaussian + linear background
        fit = fit_gaussian_linear(radii, intensities)
        if fit is None:
            continue

        # Peak must be inside the search window
        if not (r_center - search_width <= fit["center"] <= r_center + search_width):
            continue

        # Peak amplitude must exceed local noise
        valid_int = intensities[np.isfinite(intensities)]
        noise = float(np.std(valid_int)) if len(valid_int) >= 3 else 1.0
        if fit["amplitude"] < config.min_amplitude_sigma * noise:
            continue

        peaks.append(PeakFit(
            d_spacing=d_spacing,
            angle_deg=float(angle_deg),
            radius_px=fit["center"],
            amplitude=fit["amplitude"],
            fwhm=2.3548 * fit["sigma"],
            chi_square=fit["chi_square"],
            converged=True,
        ))

    log.debug("d=%.4f A: %d peaks found out of %d directions",
              d_spacing, len(peaks), len(angles_deg))
    return peaks


# ---------------------------------------------------------------------------
# Full geometry optimisation
# ---------------------------------------------------------------------------

def optimise_geometry(
    image: np.ndarray,
    mask: np.ndarray,
    calibrant,
    wavelength: float,
    pixel_size_mm: float,
    sdd_init: float,
    bcx_init: float,
    bcy_init: float,
    tilt_x_init: float,
    tilt_y_init: float,
    config: Optional[FitConfig] = None,
) -> OptimisationResult:
    """
    Run the full least-squares geometry optimisation.

    Parameters
    ----------
    image, mask   : 2-D detector image and boolean mask (True = excluded)
    calibrant     : pynika.calibrants.Calibrant instance
    wavelength    : X-ray wavelength in Angstroms
    pixel_size_mm : pixel size in mm (assumed square)
    sdd_init, bcx_init, bcy_init, tilt_x_init, tilt_y_init : initial guesses
    config        : FitConfig (uses defaults if None)

    Returns
    -------
    OptimisationResult
    """
    from pynika.geometry import expected_ring_radius

    if config is None:
        config = FitConfig()

    # ------------------------------------------------------------------
    # Step 1: collect Gaussian peak positions at initial parameter values
    # ------------------------------------------------------------------
    all_peaks: list[PeakFit] = []
    for i, d_spacing in enumerate(calibrant.d_spacings):
        if not calibrant.use_flags[i]:
            continue
        search_width = calibrant.search_widths[i]
        ring_peaks = find_ring_peaks(
            image, mask, bcx_init, bcy_init,
            d_spacing, wavelength, sdd_init, pixel_size_mm,
            search_width, tilt_x_init, tilt_y_init, config,
        )
        if len(ring_peaks) < config.min_peaks_per_ring:
            log.warning(
                "d=%.4f A: only %d peaks (< min %d) — ring may be outside detector",
                d_spacing, len(ring_peaks), config.min_peaks_per_ring,
            )
            all_peaks.extend(ring_peaks)
            continue

        # Outlier rejection per ring: discard peaks whose radius deviates more
        # than 3 * MAD from the median (filters noise / spurious Gaussian fits)
        radii_arr = np.array([p.radius_px for p in ring_peaks])
        med = float(np.median(radii_arr))
        mad = float(np.median(np.abs(radii_arr - med))) + 1e-6
        inliers = [p for p in ring_peaks if abs(p.radius_px - med) <= 3.0 * mad]
        n_rej = len(ring_peaks) - len(inliers)
        if n_rej > 0:
            log.debug("d=%.4f A: rejected %d outlier peaks (MAD=%.2f px)",
                      d_spacing, n_rej, mad)
        all_peaks.extend(inliers)

    if not all_peaks:
        return OptimisationResult(
            sdd=sdd_init, bcx=bcx_init, bcy=bcy_init,
            tilt_x=tilt_x_init, tilt_y=tilt_y_init,
            chi_square=float("nan"), n_peaks_used=0,
            success=False, message="No diffraction peaks found in the image",
            peak_fits=[],
        )

    log.info("Collected %d peaks across %d d-spacings for optimisation",
             len(all_peaks),
             len([d for d, f in zip(calibrant.d_spacings, calibrant.use_flags) if f]))

    # Precompute Bragg angles
    peak_thetas = []
    for p in all_peaks:
        sin_arg = wavelength / (2.0 * p.d_spacing)
        peak_thetas.append(float(np.arcsin(np.clip(sin_arg, -1, 1))))

    # ------------------------------------------------------------------
    # Step 2: encode free parameters
    # ------------------------------------------------------------------
    param_names: list[str] = []
    p0: list[float] = []
    lb: list[float] = []
    ub: list[float] = []
    fixed: dict[str, float] = {
        "bcx": bcx_init, "bcy": bcy_init, "sdd": sdd_init,
        "tilt_x": tilt_x_init, "tilt_y": tilt_y_init,
    }

    spec = [
        ("bcx",    bcx_init,    config.fit_bcx,    config.bcx_limits),
        ("bcy",    bcy_init,    config.fit_bcy,    config.bcy_limits),
        ("sdd",    sdd_init,    config.fit_sdd,    config.sdd_limits),
        ("tilt_x", tilt_x_init, config.fit_tilt_x, config.tilt_x_limits),
        ("tilt_y", tilt_y_init, config.fit_tilt_y, config.tilt_y_limits),
    ]
    for name, init, fit_flag, limits in spec:
        if fit_flag:
            param_names.append(name)
            p0.append(init)
            lb.append(limits[0])
            ub.append(limits[1])
        # fixed dict already set above

    if not param_names:
        return OptimisationResult(
            sdd=sdd_init, bcx=bcx_init, bcy=bcy_init,
            tilt_x=tilt_x_init, tilt_y=tilt_y_init,
            chi_square=float("nan"), n_peaks_used=len(all_peaks),
            success=False, message="No free parameters selected for fitting",
            peak_fits=all_peaks,
        )

    def decode(p: np.ndarray) -> dict[str, float]:
        vals = dict(fixed)
        for j, name in enumerate(param_names):
            vals[name] = float(p[j])
        return vals

    # ------------------------------------------------------------------
    # Step 3: residual function
    # ------------------------------------------------------------------
    peak_angles = np.array([np.deg2rad(p.angle_deg) for p in all_peaks])
    peak_radii  = np.array([p.radius_px             for p in all_peaks])

    def residuals(p: np.ndarray) -> np.ndarray:
        v = decode(p)
        res = np.empty(len(all_peaks))
        for k, (theta, phi, r_fit) in enumerate(
            zip(peak_thetas, peak_angles, peak_radii)
        ):
            r_model = expected_ring_radius(
                theta, float(phi),
                v["bcx"], v["bcy"], v["sdd"], pixel_size_mm,
                v["tilt_x"], v["tilt_y"],
            )
            res[k] = r_fit - r_model if np.isfinite(r_model) else 1000.0
        return res

    # ------------------------------------------------------------------
    # Step 4: run optimisation
    # ------------------------------------------------------------------
    log.info("Starting least_squares with %d free params, %d residuals",
             len(param_names), len(all_peaks))
    try:
        result = least_squares(
            residuals, p0,
            bounds=(lb, ub),
            method="trf",
            ftol=1e-8, xtol=1e-8, gtol=1e-8,
            max_nfev=2000 * len(param_names),
        )
    except Exception as exc:
        return OptimisationResult(
            sdd=sdd_init, bcx=bcx_init, bcy=bcy_init,
            tilt_x=tilt_x_init, tilt_y=tilt_y_init,
            chi_square=float("nan"), n_peaks_used=len(all_peaks),
            success=False, message=f"Optimiser exception: {exc}",
            peak_fits=all_peaks,
        )

    v_final = decode(result.x)
    n_dof = max(1, len(all_peaks) - len(param_names))
    chi2 = float(np.sum(result.fun**2)) / n_dof
    success = bool(result.success) and chi2 < 1000.0

    log.info(
        "Optimisation %s: chi2/dof=%.4g, %d peaks, cost=%.4g, msg=%s",
        "OK" if success else "FAILED",
        chi2, len(all_peaks), float(result.cost), result.message,
    )

    return OptimisationResult(
        sdd=v_final["sdd"],
        bcx=v_final["bcx"],
        bcy=v_final["bcy"],
        tilt_x=v_final["tilt_x"],
        tilt_y=v_final["tilt_y"],
        chi_square=chi2,
        n_peaks_used=len(all_peaks),
        success=success,
        message=result.message,
        peak_fits=all_peaks,
    )
