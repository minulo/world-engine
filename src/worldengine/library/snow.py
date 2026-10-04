"""Snow on the ground through a repeating year: a store that snowfall fills and warmth empties.

Model: the degree-day (temperature-index) rule of snow melt, M = factor * positive degrees * time
(Hock 2003, equation 1), on monthly means. The store of each cell is followed month by month,
starting from bare ground:

    store[m] = max(store[m - 1] + snowfall[m] - melt[m], 0)

Where a year's snowfall exceeds what its warm months can melt, the store grows from year to
year without end: that is where an ice sheet builds. Where it does not, the store is empty by
the end of summer and the same year repeats.

Ignores: days warmer or colder than their month's mean (a month just below freezing melts
nothing here), rain falling on snow, snow blown by wind, and snow lost straight to the air.
"""
import numpy as np


def snow_store(snowfall: np.ndarray, melt: np.ndarray, years: int) -> np.ndarray:
    """The mean store during each month (mm of water) in the last of `years` years followed from bare ground.

    snowfall, melt: (months, n), mm of water a month; melt is what the month could melt if the snow were there.
    The mean of a month is taken as the average of the store at its start and at its end.
    """
    months = snowfall.shape[0]
    store = np.zeros(snowfall.shape[1])
    mean = np.zeros(snowfall.shape)
    for _ in range(int(years)):
        for m in range(months):
            start = store
            store = np.maximum(start + snowfall[m] - melt[m], 0.0)
            mean[m] = 0.5 * (start + store)
    return mean


def degree_day_melt(temperature_k: np.ndarray, freezing_k: float, factor_mm_per_day_k: float, month_days: float) -> np.ndarray:
    """What a month could melt (mm of water): the factor times the degrees above freezing times the days of the month."""
    return factor_mm_per_day_k * month_days * np.maximum(temperature_k - freezing_k, 0.0)
