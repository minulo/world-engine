"""Water in the soil through a year that repeats: the bucket.

Model: the bucket of Manabe's climate models, as the description of the GFDL model gives it
[DOCUMENTED: https://pcmdi.llnl.gov/projects/modeldoc/cmip1/gfdl_tbls.html]. The soil of a cell
is one store with a capacity. Rain and melted snow fill it; what does not fit runs off. The
air takes water from it at the rate it demands, times an efficiency

    efficiency = store / (critical share * capacity), and never more than 1

so a soil that is nearly full gives the air all it asks for, and a drying soil gives less and
less. With the store W, the supply S and the demand D of a month:

    dW/dt = S - D * min(1, W / Wc)        Wc = critical share * capacity
    whatever would raise W above the capacity runs off instead

Within a month S and D are steady, and the equation is solved exactly. At or above Wc the
store changes at the steady rate S - D. Below Wc it relaxes toward the level S * Wc / D at
which the air takes exactly what arrives. A month may pass from one rule to the other once,
and the moment is found.

The formulas for the store are written so that a demand of next to nothing changes the store
by next to nothing: none of them subtracts two large numbers that nearly agree. What the air
took is then what is left of the month's balance (the store before, plus the supply, less the
store after and the overflow), and that does subtract numbers that nearly agree: where the air
asks for next to nothing, the amount it is said to take can exceed its demand by about a
billionth of a millimetre [MEASURED by the fourth check of build step 2: 1.2e-9 mm].

A knife edge. Where the year's supply equals its demand exactly and the store stays above Wc,
the store neither rises nor falls: every level is a year that repeats, and the one returned is
the one the search began from, which rounding can make another in an array of cells than for
the cell alone. What the air takes and what runs off are the same whichever level it is
[MEASURED by the third check of build step 2: seven such soils among 2,433 built to tie; the
store differed by up to 1,250 mm, the fluxes by 0.00002 mm].

Ignores: layers in the soil, roots, plants closing their pores, water that runs off a wet
surface before the soil is full, frozen ground, and groundwater.
"""
import numpy as np

SERIES_BELOW = 1.0e-4          # below this value of x the two functions of x that follow are summed as series
JUMP_AFTER_YEARS = 3           # in bucket_repeating: the store is moved ahead after every this many years followed
RATIO_MOST = 0.999999          # ... if the last changes shrink by a steady ratio no nearer to 1 than this
THREE_FACTORIAL, FOUR_FACTORIAL = 6.0, 24.0        # in the two series


def _decay(x):
    """(1 - exp(-x)) / x, which is 1 at x = 0."""
    x = np.asarray(x, dtype=np.float64)
    safe = np.where(x < SERIES_BELOW, 1.0, x)
    return np.where(x < SERIES_BELOW, 1.0 - x / 2.0 + x * x / THREE_FACTORIAL, -np.expm1(-x) / safe)


def _lag(x):
    """(x - (1 - exp(-x))) / x**2, which is 1/2 at x = 0."""
    x = np.asarray(x, dtype=np.float64)
    safe = np.where(x < SERIES_BELOW, 1.0, x)
    return np.where(x < SERIES_BELOW, 0.5 - x / THREE_FACTORIAL + x * x / FOUR_FACTORIAL, (x + np.expm1(-x)) / (safe * safe))


def _steady(start, rate, time, capacity):
    """The store changing at a steady rate for `time`, held at the capacity once it is reached.
    Returns (end, what ran off, the store summed over the time)."""
    free = start + rate * time
    over = np.maximum(free - capacity, 0.0)
    rising = rate > 0.0
    until_full = np.where(rising, np.clip((capacity - start) / np.where(rising, rate, 1.0), 0.0, time), time)
    summed = until_full * (start + 0.5 * rate * until_full) + (time - until_full) * capacity
    return free - over, over, summed


def _relaxing(start, supply, pull, time):
    """The store under dW/dt = supply - pull * W for `time`. Returns (end, the store summed over the time).
    With no pull the store simply gains the supply."""
    x = pull * time
    gone = time * _decay(x)                                  # (1 - exp(-pull * time)) / pull
    end = start + (supply - pull * start) * gone
    summed = start * gone + supply * time * time * _lag(x)
    return end, summed


def bucket_month(store: np.ndarray, supply: np.ndarray, demand: np.ndarray, capacity: np.ndarray, critical: np.ndarray):
    """One month of the bucket, solved exactly. All arguments one value per cell, in mm and mm a month.
    Returns (store at the end, mean store of the month, evaporation, overflow)."""
    holds = critical > 0.0
    safe_critical = np.where(holds, critical, 1.0)
    pull = np.where(holds, demand / safe_critical, 0.0)      # the rate at which a drying soil loses water to the air
    asks = pull > 0.0
    rate = supply - demand
    steady_first = (store >= critical) | ~asks               # the month begins under the steady rule
    falls = steady_first & asks & (rate < 0.0)               # ... and falls to the critical level
    until_critical = np.where(falls, (store - critical) / np.where(falls, -rate, 1.0), np.inf)
    climbs = ~steady_first & (rate > 0.0)                    # the month begins drying and climbs past the critical level
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        gap = np.where(climbs, (critical - store) * pull / np.where(climbs, rate, 1.0), 0.0)
        until_past = np.where(climbs, np.log1p(gap) / np.where(asks, pull, 1.0), np.inf)
    first = np.clip(np.where(steady_first, until_critical, until_past), 0.0, 1.0)
    rest = 1.0 - first
    # the month under the steady rule first, then drying
    a_end, a_over, a_sum = _steady(store, rate, first, capacity)
    a_end2, a_sum2 = _relaxing(critical, supply, pull, rest)
    # the month drying first, then under the steady rule
    b_end, b_sum = _relaxing(store, supply, pull, first)
    b_end2, b_over2, b_sum2 = _steady(critical, rate, rest, capacity)
    switched = rest > 0.0
    end = np.where(steady_first, np.where(switched, a_end2, a_end), np.where(switched, b_end2, b_end))
    over = np.where(steady_first, a_over, np.where(switched, b_over2, 0.0))
    mean = np.where(steady_first, a_sum + np.where(switched, a_sum2, 0.0), b_sum + np.where(switched, b_sum2, 0.0))
    # rounding can leave the store a hair above full or below empty: the hair goes to the overflow, or comes off what
    # the air took, so that the store keeps its bounds and the month its balance
    above = np.maximum(end - capacity, 0.0)
    end, over = np.maximum(end - above, 0.0), over + above
    # a cell whose soil holds nothing: what falls goes to the air as far as it asks, and the rest runs off
    end = np.where(holds, end, 0.0)
    mean = np.where(holds, mean, 0.0)
    taken = np.where(holds, store + supply - end - over, np.minimum(supply, demand))
    over = np.where(holds, over, supply - np.minimum(supply, demand))
    return end, mean, np.maximum(taken, 0.0), over


def bucket_year(supply: np.ndarray, demand: np.ndarray, capacity: np.ndarray, critical_share: float, start: np.ndarray):
    """One year of the bucket, begun with the store `start` (mm).

    supply, demand: (months, n) in mm a month; capacity: (n,) in mm.
    Returns (store at the end, mean store of each month, evaporation of each month, overflow of each month).
    """
    months, n = supply.shape
    critical = critical_share * capacity
    store = np.array(start, dtype=np.float64)
    mean, evaporation, overflow = np.zeros((months, n)), np.zeros((months, n)), np.zeros((months, n))
    for m in range(months):
        store, mean[m], evaporation[m], overflow[m] = bucket_month(store, supply[m], demand[m], capacity, critical)
    return store, mean, evaporation, overflow


def bucket_repeating(supply: np.ndarray, demand: np.ndarray, capacity: np.ndarray, critical_share: float,
                     years_most: int, within_mm: float):
    """The year of the bucket that repeats: the store at its end equals the store at its start.

    Years are followed one after another from an estimate of the store: full where the year's supply exceeds its
    demand, and otherwise the level at which a steady supply and a steady demand balance (an empty soil where
    nothing arrives and the air asks for nothing: soil that liquid water never reaches). A cell is followed until
    its year repeats exactly, or until two things hold after two years in a row: its store changed by no more than
    `within_mm` over the last year, and, where the changes of the two years shrink by a steady ratio, what that
    ratio says is still to come is no more than `within_mm` either. The second matters in soil the air asks little
    of, where the store closes in on its repeating year by a ratio near 1: a small change in a year then says
    little about how far there is to go.

    After every JUMP_AFTER_YEARS years the store of the cells still followed is moved to where the last three years
    say it is heading (Aitken's rule for a sequence that closes in on its limit by a steady ratio [UNVERIFIED: the
    name is from memory; the rule itself is three lines of arithmetic, written out below]). While a cell stays
    under one rule all year its year is a straight-line function of the store it starts with, and one such move
    lands on the repeating year.

    Returns (mean store of each month, evaporation of each month, overflow of each month, years followed,
    the largest of the two measures above left in any cell when it stopped).
    """
    months, n = supply.shape
    year_supply, year_demand = supply.sum(axis=0), demand.sum(axis=0)
    critical = critical_share * capacity
    steady = critical * year_supply / np.where(year_demand > 0.0, year_demand, 1.0)
    store = np.where(year_supply > year_demand, capacity, np.minimum(steady, capacity))
    out = [np.zeros((months, n)) for _ in range(3)]
    cells = np.arange(n)                                     # the cells still followed
    history = [store]
    before = np.full(n, np.nan)                              # the change of the year before
    left, years = 0.0, 0
    while cells.size and years < years_most:
        end, mean, evaporation, overflow = bucket_year(supply[:, cells], demand[:, cells], capacity[cells],
                                                       critical_share, store)
        years += 1
        for kept, new in zip(out, (mean, evaporation, overflow)):
            kept[:, cells] = new
        change = end - store
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = change / before
        closing = (ratio > 0.0) & (ratio < 1.0)
        to_come = np.where(closing, np.abs(change) * np.minimum(ratio, RATIO_MOST) / (1.0 - np.minimum(ratio, RATIO_MOST)), 0.0)
        far = np.maximum(np.abs(change), to_come)
        # a cell is done when its year repeats exactly, or when two years in a row say it has arrived
        going = (change != 0.0) & (np.isnan(before) | (far > within_mm))
        left = float(far.max())
        history.append(end)
        store, before = end, change
        if len(history) > JUMP_AFTER_YEARS:
            a, b, c = history[-3], history[-2], history[-1]
            first, second = b - a, c - b
            ratio = second / np.where(first != 0.0, first, 1.0)
            steadily = (first != 0.0) & (ratio > 0.0) & (ratio < RATIO_MOST)
            ahead = c + second * ratio / np.where(steadily, 1.0 - ratio, 1.0)
            store = np.where(steadily, np.clip(ahead, 0.0, capacity[cells]), c)
            before = np.where(steadily, np.nan, before)      # the next change does not continue the series
            history = [store]
        cells, store, before = cells[going], store[going], before[going]
        history = [h[going] for h in history]
    return out[0], out[1], out[2], years, left
