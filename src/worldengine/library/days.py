"""Days on the weather clock: plain functions for the processes of the weather stage (design, Layer 3).

A day is a whole number counted from the first day of the planet's year 0. Weather keeps no state: everything a day
needs is drawn again from the seed and the dates of the days before it, within a fixed look-back window.
"""
import numpy as np

from .units import SECONDS_PER_DAY


def days_in_year(planet) -> float:
    return planet["year_length_s"] / SECONDS_PER_DAY


def month_weights(day: int, planet, months: int):
    """The two months whose means a day lies between, and the weight of the first: the monthly means are taken to hold
    at the middle of each month, and a day between two middles mixes them linearly."""
    per_month = days_in_year(planet) / months
    x = (day % days_in_year(planet)) / per_month - 0.5
    first = int(np.floor(x)) % months
    weight = 1.0 - (x - np.floor(x))
    return first, (first + 1) % months, weight


def on_day(monthly: np.ndarray, day: int, planet) -> np.ndarray:
    """The value of a monthly field (months first) on a day."""
    a, b, w = month_weights(day, planet, monthly.shape[0])
    return w * monthly[a] + (1.0 - w) * monthly[b]


def remembered_noise(draw, purpose, day, window, persistence, n, smooth):
    """Noise smooth in space and in time: a weighted sum of the last `window` daily noise fields, each drawn from its own
    date and smoothed in space by `smooth` (a function of one field), with weights persistence**age, scaled to unit
    variance. The sum is always made afresh over its days, in date order, never carried from the day before."""
    weights = persistence ** np.arange(window)
    weights = weights / np.sqrt((weights ** 2).sum())
    total = np.zeros(n)
    for age in range(window - 1, -1, -1):                           # oldest first: a fixed order
        field = smooth(draw.on(day - age).normal(purpose, n))
        total += weights[age] * field
    return total
