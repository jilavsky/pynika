"""Basic sanity tests for calibrant d-spacing data."""

import pytest
from pynika.calibrants import get_calibrant, AG_BEHENATE, LAB6


def test_ag_behenate_d1():
    """d₁ of AgBehenate must be 58.380 Å (Huang et al. 1993)."""
    assert AG_BEHENATE.d_spacings[0] == pytest.approx(58.380)


def test_ag_behenate_ten_lines():
    assert len(AG_BEHENATE.d_spacings) == 10


def test_lab6_d1():
    """d₁ of LaB6 [100] must be 4.15690 Å."""
    assert LAB6.d_spacings[0] == pytest.approx(4.15690)


def test_lab6_ten_lines():
    assert len(LAB6.d_spacings) == 10


def test_get_calibrant_returns_copy():
    c1 = get_calibrant("AgBehenate")
    c2 = get_calibrant("AgBehenate")
    c1.d_spacings[0] = 999.0
    assert c2.d_spacings[0] == pytest.approx(58.380), "get_calibrant must return independent copies"


def test_get_calibrant_unknown():
    with pytest.raises(KeyError):
        get_calibrant("NotACalibrant")


def test_geometry_d_to_pixel():
    from pynika.geometry import d_to_pixel_radius, pixel_to_d

    d = 58.380     # Å
    lam = 1.0      # Å
    sdd = 1500.0   # mm
    pix = 0.172    # mm

    r = d_to_pixel_radius(d, lam, sdd, pix)
    assert r > 0

    d_back = pixel_to_d(r, lam, sdd, pix)
    assert d_back == pytest.approx(d, rel=1e-6)
