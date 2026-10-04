"""Smooth random fields defined in sphere coordinates, so that one seed gives the same pattern at every mesh level."""
import numpy as np

from .units import TWO_PI


def wave_field(xyz: np.ndarray, u: np.ndarray, wave_number_range, slope: float = 1.0) -> np.ndarray:
    """A sum of plane waves through the sphere, scaled to unit variance over the points given.

    u holds 4 uniform numbers per wave: two for its direction, one for its wave number inside
    wave_number_range (radians of phase per unit of distance on the unit sphere), one for its phase.
    A wave's amplitude falls as its wave number to the power -slope, so long waves dominate.
    """
    k = u.size // 4
    z = 2.0 * u[:k] - 1.0
    lon = TWO_PI * u[k:2 * k]
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    direction = np.stack([r * np.cos(lon), r * np.sin(lon), z], axis=1)
    lo, hi = wave_number_range
    number = lo + (hi - lo) * u[2 * k:3 * k]
    phase = TWO_PI * u[3 * k:4 * k]
    out = np.zeros(xyz.shape[0])
    for i in range(k):                                        # a fixed order, so the sum never varies
        out += number[i] ** (-slope) * np.sin(number[i] * (xyz @ direction[i]) + phase[i])
    return (out - out.mean()) / out.std()
