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

Ignores: layers in the soil, roots, plants closing their pores, water that runs off a wet
surface before the soil is full, frozen ground, and groundwater.
"""
import numpy as np


def _steady(start, rate, time, capacity):
    """The store changing at a steady rate for `time`, held at the capacity once it is reached.
    Returns (end, what ran off, the store summed over the time)."""
    free = start + rate * time
    over = np.maximum(free - capacity, 0.0)
    rising = rate > 0.0
    until_full = np.where(rising, np.clip((capacity - start) / np.where(rising, rate, 1.0), 0.0, time), time)
    summed = until_full * (start + 0.5 * rate * until_full) + (time - until_full) * capacity
    return free - over, over, summed


def _relaxing(start, pull, level, time):
    """The store relaxing toward `level` at the rate `pull` for `time`. Returns (end, the store summed over the time)."""
    safe = np.where(pull > 0.0, pull, 1.0)
    gone = -np.expm1(-pull * time)                           # 1 - exp(-pull * time)
    end = level + (start - level) * (1.0 - gone)
    summed = level * time + (start - level) * gone / safe
    return end, summed


def bucket_month(store: np.ndarray, supply: np.ndarray, demand: np.ndarray, capacity: np.ndarray, critical: np.ndarray):
    """One month of the bucket, solved exactly. All arguments one value per cell, in mm and mm a month.
    Returns (store at the end, mean store of the month, evaporation, overflow)."""
    holds = critical > 0.0
    safe_critical = np.where(holds, critical, 1.0)
    pull = np.where(holds, demand / safe_critical, 0.0)      # the rate at which a drying soil loses water to the air
    asks = pull > 0.0
    rate = supply - demand
    level = np.where(asks, supply / np.where(asks, pull, 1.0), np.inf)       # where a drying soil comes to rest
    steady_first = (store >= critical) | ~asks               # the month begins under the steady rule
    with np.errstate(divide="ignore", invalid="ignore"):
        falls = steady_first & asks & (rate < 0.0)           # ... and falls to the critical level
        until_critical = np.where(falls, (store - critical) / np.where(falls, -rate, 1.0), np.inf)
        climbs = ~steady_first & (level > critical)          # the month begins drying and climbs past the critical level
        until_past = np.where(climbs, np.log(np.where(climbs, (level - store) / np.where(climbs, level - critical, 1.0), 1.0))
                              / np.where(asks, pull, 1.0), np.inf)
    first = np.clip(np.where(steady_first, until_critical, until_past), 0.0, 1.0)
    rest = 1.0 - first
    finite_level = np.where(np.isfinite(level), level, 0.0)
    # the month under the steady rule first, then drying
    a_end, a_over, a_sum = _steady(store, rate, first, capacity)
    a_end2, a_sum2 = _relaxing(critical, pull, finite_level, rest)
    # the month drying first, then under the steady rule
    b_end, b_sum = _relaxing(store, pull, finite_level, first)
    b_end2, b_over2, b_sum2 = _steady(critical, rate, rest, capacity)
    switched = rest > 0.0
    end = np.where(steady_first, np.where(switched, a_end2, a_end), np.where(switched, b_end2, b_end))
    over = np.where(steady_first, a_over, np.where(switched, b_over2, 0.0))
    mean = np.where(steady_first, a_sum + np.where(switched, a_sum2, 0.0), b_sum + np.where(switched, b_sum2, 0.0))
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
    """The year of the bucket that repeats: the store at its end equals the store at its start to within `within_mm`.

    Years are followed one after another from an estimate of the store: full where the year's supply exceeds its
    demand, and otherwise the level at which a steady supply and a steady demand balance (an empty soil where
    nothing arrives and the air asks for nothing: soil that liquid water never reaches). Twice on the way the
    store is moved to where the last three years say it is heading (Aitken's rule for a sequence that closes in
    on its limit by a steady ratio), which shortens the wait in cells that settle slowly.

    Returns (mean store of each month, evaporation of each month, overflow of each month, years followed,
    the largest difference left between the store at the end and at the start of the last year).
    """
    year_supply, year_demand = supply.sum(axis=0), demand.sum(axis=0)
    critical = critical_share * capacity
    steady = critical * year_supply / np.where(year_demand > 0.0, year_demand, 1.0)
    store = np.where(year_supply > year_demand, capacity, np.minimum(steady, capacity))
    history = [store]
    jumps = (3, 7)                                                    # after these years the store is moved ahead
    left = np.inf
    years = 0
    out = None
    while years < years_most:
        end, mean, evaporation, overflow = bucket_year(supply, demand, capacity, critical_share, store)
        years += 1
        left = float(np.abs(end - store).max()) if end.size else 0.0
        out = (mean, evaporation, overflow)
        if left <= within_mm:
            break
        history.append(end)
        store = end
        if years in jumps:
            a, b, c = history[-3], history[-2], history[-1]
            first, second = b - a, c - b
            ratio = second / np.where(first != 0.0, first, 1.0)
            closing = (first != 0.0) & (ratio > 0.0) & (ratio < 0.999)
            ahead = c + second * ratio / np.where(closing, 1.0 - ratio, 1.0)
            store = np.where(closing, np.clip(ahead, 0.0, capacity), c)
            history = [store]
    return out + (years, left)
