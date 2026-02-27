"""
Known calibrant d-spacings (in Angstroms).

D-spacings for AgBehenate and LaB6 are transcribed from the Nika Igor Pro
package (NI1_BeamCenterUtils.ipf) to preserve exact numerical compatibility.

References
----------
AgBehenate: T. C. Huang et al., J. Appl. Cryst. 26, 180-184 (1993).
            q = 0.1076 Å⁻¹, d₁ = 58.380 Å
LaB6:       P. Lee (APS/XSD, unpublished values used in Nika).
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Calibrant:
    """A diffraction calibrant with up to 10 d-spacings."""

    name: str
    d_spacings: list[float]           # in Angstroms, largest first
    use_flags: list[bool]             # True = include in fit
    search_widths: list[float]        # ± pixels around theoretical ring
    description: str = ""

    def __post_init__(self) -> None:
        n = len(self.d_spacings)
        if len(self.use_flags) != n:
            self.use_flags = [True] * n
        if len(self.search_widths) != n:
            self.search_widths = [30.0] * n


# ---------------------------------------------------------------------------
# AgBehenate  (SAXS default)
# ---------------------------------------------------------------------------
AG_BEHENATE = Calibrant(
    name="AgBehenate",
    description="Silver behenate — primary SAXS calibrant. d₁ = 58.380 Å.",
    d_spacings=[
        58.380,   # 1st order
        29.185,   # 2nd
        19.46,    # 3rd
        14.595,   # 4th
        11.676,   # 5th  (corrected from 11.767 in Nika v2.22)
         9.73,    # 6th
         8.34,    # 7th
         7.2975,  # 8th
         6.48667, # 9th
         5.838,   # 10th
    ],
    use_flags=[True] * 10,
    search_widths=[50, 30, 20, 20, 20, 20, 20, 20, 20, 20],
)

# ---------------------------------------------------------------------------
# LaB6  (WAXS default)
# ---------------------------------------------------------------------------
LAB6 = Calibrant(
    name="LaB6",
    description="Lanthanum hexaboride — primary WAXS calibrant.",
    d_spacings=[
        4.15690,   # [100]  rel. int. 60
        2.93937,   # [110]  100
        2.39999,   # [111]  45
        2.07845,   # [200]  23.6
        1.85902,   # [210]  55
        1.69705,   # [211]
        1.46969,   # [220]
        1.38564,   # [300/221]
        1.31453,   # [310]
        1.25336,   # [311]
    ],
    use_flags=[True] * 10,
    search_widths=[20] * 10,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
CALIBRANTS: dict[str, Calibrant] = {
    "AgBehenate": AG_BEHENATE,
    "LaB6": LAB6,
}


def get_calibrant(name: str) -> Calibrant:
    """Return a *copy* of the named calibrant so callers can mutate it safely."""
    import copy
    if name not in CALIBRANTS:
        raise KeyError(f"Unknown calibrant '{name}'. Available: {list(CALIBRANTS)}")
    return copy.deepcopy(CALIBRANTS[name])
