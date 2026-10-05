"""Snow on the ground through a year that repeats: a store that snowfall fills and warmth empties.

Model: the degree-day (temperature-index) rule of snow melt, M = factor * positive degrees * time
(Hock 2003, equation 1), on monthly means. Through each month the store changes by

    store at the end = max(store at the start + snowfall - melt, 0)

and the year is the one that repeats: the store at its end equals the store at its start.

Two cases. Where the year can melt more than falls, the snow is gone by the end of the warm
season, and the repeating year is the one that years followed from bare ground come to after
their first. Where more falls in a year than the year can melt, the store would grow without
end: that is where an ice sheet builds. There the store is held to a set number of years' net
snowfall, and what is older leaves the cell as ice, at a steady rate through the year
[INFERRED: a stand-in for snow turning to glacier ice and flowing away. The ice that leaves is
the year's net snowfall whatever that number is; only the depth of the store depends on it].
The two cases meet without a jump: as the year's net snowfall falls to nothing, so do the ice
that leaves and the snow that outlasts the summer.

Ignores: days warmer or colder than their month's mean (a month just below freezing melts
nothing here), rain falling on snow, snow blown by wind, and snow lost straight to the air.
"""
import numpy as np


def degree_day_melt(temperature_k: np.ndarray, freezing_k: float, factor_mm_per_day_k: float, month_days: float) -> np.ndarray:
    """What a month could melt (mm of water): the factor times the degrees above freezing times the days of the month."""
    return factor_mm_per_day_k * month_days * np.maximum(temperature_k - freezing_k, 0.0)


def _year_from(store, snowfall, melt):
    mean, melted = np.zeros(snowfall.shape), np.zeros(snowfall.shape)
    for m in range(snowfall.shape[0]):
        start = store
        there = start + snowfall[m]
        melted[m] = np.minimum(melt[m], there)
        store = there - melted[m]
        mean[m] = 0.5 * (start + store)
    return store, mean, melted


def snow_year(snowfall: np.ndarray, melt: np.ndarray, ice_after_years: float):
    """The year that repeats. snowfall, melt: (months, n), mm of water a month; melt is what the month could melt if
    the snow were there. Returns three arrays of that shape:
      store     the mean store during each month, taken as the average of the store at its start and at its end
      melted    what melted in each month
      left      what left the cell as ice in each month: nothing where the year melts all its snow
    """
    months = snowfall.shape[0]
    change = snowfall - melt
    gain = change.sum(axis=0)
    # Where the year melts all its snow: one year from bare ground ends with the store that every later year ends with.
    end, _, _ = _year_from(np.zeros(snowfall.shape[1]), snowfall, melt)
    _, mean, melted = _year_from(end, snowfall, melt)
    left = np.zeros(snowfall.shape)
    keeps = gain > 0.0
    if keeps.any():                                          # where snow outlasts the summer
        steady = gain[keeps] / months                        # ice leaving in each month
        path = np.cumsum(change[:, keeps] - steady, axis=0)  # the store at the end of each month, but for a constant
        ends = ice_after_years * gain[keeps] + path - path.min(axis=0)
        starts = np.concatenate([ends[-1:], ends[:-1]])
        mean[:, keeps] = 0.5 * (starts + ends)
        melted[:, keeps] = melt[:, keeps]
        left[:, keeps] = steady
    return mean, melted, left
