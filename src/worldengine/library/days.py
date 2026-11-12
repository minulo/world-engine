"""Days on the weather clock: plain functions for the processes of the weather stage (design, Layer 3), and the calendar
by which the engine steps the stages that step through dates.

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


def step_of(day: int, planet, months: int, step: str) -> int:
    """The number of the step a day lies in, counted from 0, the first step of year 0: the day itself, its month counted
    over all the years, or its year. A day lies in year floor(day / D), where D is the year in days, and in month
    floor((day mod D) / (D / months)) of that year: the month whose middle is nearer to it of the two that month_weights
    mixes, so the calendar of the steps and the weather of a day agree on the month a day belongs to."""
    if step == "day":
        return int(day)
    length = days_in_year(planet)
    year = int(day // length)
    if step == "year":
        return year
    return year * months + min(int((day % length) / (length / months)), months - 1)


def first_day_of_step(number: int, planet, months: int, step: str) -> int:
    """The first day of a step: the earliest day whose step is `number` or later (step_of never decreases)."""
    if step == "day":
        return int(number)
    per_step = days_in_year(planet) / (months if step == "month" else 1)
    day = max(0, int(np.ceil(number * per_step)))
    while day > 0 and step_of(day - 1, planet, months, step) >= number:
        day -= 1
    while step_of(day, planet, months, step) < number:
        day += 1
    return day


def days_in_step(number: int, planet, months: int, step: str) -> int:
    """The number of whole days a step holds."""
    return first_day_of_step(number + 1, planet, months, step) - first_day_of_step(number, planet, months, step)


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
