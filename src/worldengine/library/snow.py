"""Snow on the ground through a year that repeats: a store that snowfall fills and warmth empties.

Model: the degree-day (temperature-index) rule of snow melt, M = factor * positive degrees * time
[DOCUMENTED: Hock 2003, equation 1], on monthly means. Within a month snow falls and melts at
steady rates, so the store changes at a steady rate until it is gone:

    store at the end = max(store at the start + snowfall - melt, 0)

and the year is the one that repeats: the store at its end equals the store at its start. The
mean store of a month is the mean over its days: where the snow runs out part-way through the
month, the days without snow count as nothing.

How much of the ground the snow covers: the ground counts as fully covered once the store
holds a set depth of water, and as covered in proportion below that [DOCUMENTED when build
step 1 was written: the form of the older ECMWF land scheme, Dutra et al. 2010, equation A2,
with 15 mm]. That rule is stated for the store of the moment. The cover of a month is
therefore the mean over its days of the cover of each day, not the cover that the month's mean
store would give: a deep store that melts away in the first week of a month leaves the ground
bare for the other three.

Two cases. Where the year can melt more than falls, the snow is gone by the end of the warm
season, and the repeating year is the one that years followed from bare ground come to after
their first. Where more falls in a year than the year can melt, the store would grow without
end: that is where an ice sheet builds. There the store is held to a set number of years' net
snowfall, and what is older leaves the cell as ice, at a steady rate through the year
[INFERRED: a stand-in for snow turning to glacier ice and flowing away. The ice that leaves is
the year's net snowfall whatever that number is. The number sets how much snow is left at the
end of summer where a year just fails to melt its snow, and so how white that ground is and
how much the air can take from it: it moves the edge of the ground that stays white. MEASURED
on the default preview world: with 0.2 years in place of 1, up to 0.8 K in temperature and
74 cells of 10,242 with another biome; with 2 or 5 years, at most 0.002 K and one cell].
The two cases meet without a jump: as the year's net snowfall falls to nothing, so do the ice
that leaves and the snow that outlasts the summer.

Ignores: days warmer or colder than their month's mean (a month just below freezing melts
nothing here), rain falling on snow, snow blown by wind, and snow lost straight to the air.
"""
import numpy as np

STEEP = 1.0e-6                 # in _mean_cover: a month's change smaller than this share of the store counts as none


def degree_day_melt(temperature_k: np.ndarray, freezing_k: float, factor_mm_per_day_k: float, month_days: float) -> np.ndarray:
    """What a month could melt (mm of water): the factor times the degrees above freezing times the days of the month."""
    return factor_mm_per_day_k * month_days * np.maximum(temperature_k - freezing_k, 0.0)


def _mean_cover(start, rate, full):
    """The mean over a month of min(store / full, 1), where the store is max(start + rate * t, 0) for t from 0 to 1."""
    end = start + rate                                       # where the straight line stands at the month's end

    def area_below(y):                                       # the integral of min(max(y, 0), full) up to y
        y = np.maximum(y, 0.0)
        return np.where(y <= full, 0.5 * y * y, full * y - 0.5 * full * full)
    steep = np.abs(rate) > STEEP * (np.abs(start) + full)    # else the line is as good as level: its middle will do
    mean = np.where(steep, (area_below(end) - area_below(start)) / np.where(steep, rate, 1.0),
                    np.clip(start + 0.5 * rate, 0.0, full))
    mean = np.where((start >= full) & (end >= full), full, mean)        # covered all month: exactly so, not to rounding
    mean = np.where((start <= 0.0) & (end <= 0.0), 0.0, mean)           # and bare all month
    return np.clip(mean / full, 0.0, 1.0) + 0.0              # (adding zero turns a minus zero into zero)


def _year_from(store, snowfall, melt, full):
    mean, melted, cover = np.zeros(snowfall.shape), np.zeros(snowfall.shape), np.zeros(snowfall.shape)
    for m in range(snowfall.shape[0]):
        start = store
        there = start + snowfall[m]
        melted[m] = np.minimum(melt[m], there)
        store = there - melted[m]
        # The mean over the month. The store changes at the steady rate snowfall - melt. If that empties it before
        # the month ends, it falls in a straight line to nothing and stays there: what falls after that melts at once.
        rate = snowfall[m] - melt[m]
        runs_out = start + rate < 0.0
        share_of_month = start / np.where(runs_out, -rate, 1.0)
        mean[m] = np.where(runs_out, 0.5 * start * share_of_month, 0.5 * (start + store))
        cover[m] = _mean_cover(start, rate, full)
    return store, mean, melted, cover


def snow_year(snowfall: np.ndarray, melt: np.ndarray, ice_after_years: float, full_cover_mm: float):
    """The year that repeats. snowfall, melt: (months, n), mm of water a month; melt is what the month could melt if
    the snow were there. Returns four arrays of that shape:
      store     the mean store during each month
      melted    what melted in each month
      left      what left the cell as ice in each month: nothing where the year melts all its snow
      cover     the mean share of the ground under snow during each month: the ground counts as fully covered while
                the store holds full_cover_mm or more, and in proportion below that
    """
    months = snowfall.shape[0]
    change = snowfall - melt
    gain = change.sum(axis=0)
    # Where the year melts all its snow: one year from bare ground ends with the store that every later year ends with.
    end, _, _, _ = _year_from(np.zeros(snowfall.shape[1]), snowfall, melt, full_cover_mm)
    _, mean, melted, cover = _year_from(end, snowfall, melt, full_cover_mm)
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
        cover[:, keeps] = _mean_cover(starts, ends - starts, full_cover_mm)
    return mean, melted, left, cover
