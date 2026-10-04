"""Steady transport of water vapour by wind on the mesh, with sources and sinks.

The water budget of every air column is solved by sweeps: one cell at a time, the cell's own
balance is solved from the latest values of its neighbours. Sweeps alone settle slowly, because
they remove errors only a few cells wide. So the sweeps are run on a ladder of meshes (the
multigrid method, in its form for equations that are not linear): the broad part of the
error is corrected on coarser meshes, whose cells are the first cells of the finer one.

The compiled loops run on one thread and never reorder a sum, so the same input gives the same
bits. Numba compiles them; fastmath is off (design, Layer 8).
"""
import numpy as np
from numba import njit


@njit(cache=True)
def sweep(w, nbr, nbr_count, out_coef, in_coef, mix_own, mix_other, area, evap_coef, w_sat, rain_scale, rain_steepness,
          rain_humidity, lift_coef, source, extra, orders, cycles, newton_steps, newton_tolerance):
    """Solve cell by cell, in each of the given orders, `cycles` times over

        sum_k out[i,k] W[i] - sum_k in[i,k] W[j] + sum_k (mix_own[i,k] W[i] - mix_other[i,k] W[j]) + area[i] rain(W[i])
            = area[i] * (evap[i] * max(1 - W[i]/Wsat[i], 0) + source[i]) + extra[i]

    with rain(W) = rain_scale[i] * exp(rain_steepness * (W/Wsat[i] - rain_humidity[i])) + lift[i] * W * W / Wsat[i].
    Above saturation (W > Wsat) the first term goes on as a straight line with the slope it has at saturation,
    and nothing evaporates. mix_own and mix_other are the same number where two cells stand at the same height;
    where they do not, each carries the share of its column that lies above the higher of the two grounds.
    The cell's own equation is not linear, so it is solved by a few Newton steps. W is changed in place.
    Returns the largest change of the last cycle.
    """
    n = w.shape[0]
    change = 0.0
    for _ in range(cycles):
        change = 0.0
        for s in range(orders.shape[0]):
            for idx in range(n):
                i = orders[s, idx]
                gain = area[i] * source[i] + extra[i]
                loss = 0.0
                for k in range(nbr_count[i]):
                    j = nbr[i, k]
                    gain += (in_coef[i, k] + mix_other[i, k]) * w[j]
                    loss += out_coef[i, k] + mix_own[i, k]
                x = w[i]
                for _n in range(newton_steps):
                    humidity = x / w_sat[i]
                    if humidity <= 1.0:
                        wet = rain_scale[i] * np.exp(rain_steepness * (humidity - rain_humidity[i]))
                        wet_slope = wet * rain_steepness / w_sat[i]
                        dry = evap_coef[i] * (1.0 - humidity)
                        dry_slope = -evap_coef[i] / w_sat[i]
                    else:                                    # above saturation the law goes on as a straight line
                        top = rain_scale[i] * np.exp(rain_steepness * (1.0 - rain_humidity[i]))
                        wet = top * (1.0 + rain_steepness * (humidity - 1.0))
                        wet_slope = top * rain_steepness / w_sat[i]
                        dry = 0.0
                        dry_slope = 0.0
                    f = loss * x + area[i] * (wet + lift_coef[i] * x * x / w_sat[i] - dry) - gain
                    slope = loss + area[i] * (wet_slope + 2.0 * lift_coef[i] * x / w_sat[i] - dry_slope)
                    step = f / slope
                    x -= step
                    if x < 0.0:
                        x = 0.0
                    if abs(step) < newton_tolerance:
                        break
                d = abs(x - w[i])
                if d > change:
                    change = d
                w[i] = x
    return change


@njit(cache=True)
def residual(w, nbr, nbr_count, out_coef, in_coef, mix_own, mix_other, area, evap_coef, w_sat, rain_scale, rain_steepness,
             rain_humidity, lift_coef, source, extra):
    """What is left of each cell's balance: right-hand side minus left-hand side of the equation in sweep()."""
    n = w.shape[0]
    r = np.empty(n)
    for i in range(n):
        gain = area[i] * source[i] + extra[i]
        loss = 0.0
        for k in range(nbr_count[i]):
            j = nbr[i, k]
            gain += (in_coef[i, k] + mix_other[i, k]) * w[j]
            loss += out_coef[i, k] + mix_own[i, k]
        x = w[i]
        humidity = x / w_sat[i]
        if humidity <= 1.0:
            wet = rain_scale[i] * np.exp(rain_steepness * (humidity - rain_humidity[i]))
            dry = evap_coef[i] * (1.0 - humidity)
        else:
            wet = rain_scale[i] * np.exp(rain_steepness * (1.0 - rain_humidity[i])) * (1.0 + rain_steepness * (humidity - 1.0))
            dry = 0.0
        r[i] = gain - loss * x - area[i] * (wet + lift_coef[i] * x * x / w_sat[i] - dry)
    return r


class Ladder:
    """The meshes from coarse to fine, with the budget's coefficients on each."""

    W_SAT = 8                                            # where the saturation column stands among the coefficients

    def __init__(self, meshes, coefficients):
        self.meshes, self.co = meshes, coefficients      # coefficients[k]: what sweep() takes after w, with the orders last

    def _sweep(self, k, w, extra, cycles, steps, newton_tolerance):
        c = self.co[k]
        return sweep(w, *c[:-1], extra, c[-1], cycles, steps, newton_tolerance)

    def _residual(self, k, w, extra):
        return residual(w, *self.co[k][:-1], extra)

    def cycle(self, k, w, extra, steps, newton_tolerance, coarsest_cycles):
        """One trip down the ladder and back up from mesh k. Returns the largest change of the last sweep on mesh k."""
        if k == 0:
            return self._sweep(0, w, extra, coarsest_cycles, steps, newton_tolerance)
        self._sweep(k, w, extra, 1, steps, newton_tolerance)
        fine, coarse = self.meshes[k], self.meshes[k - 1]
        nc = coarse.n
        pa, pb = fine.parents[nc:, 0], fine.parents[nc:, 1]
        r = self._residual(k, w, extra)
        r_coarse = r[:nc] + 0.5 * (np.bincount(pa, weights=r[nc:], minlength=nc) + np.bincount(pb, weights=r[nc:], minlength=nc))
        w_coarse = w[:nc].copy()
        before = w_coarse.copy()
        extra_coarse = r_coarse - self._residual(k - 1, w_coarse, np.zeros(nc))
        self.cycle(k - 1, w_coarse, extra_coarse, steps, newton_tolerance, coarsest_cycles)
        correction = w_coarse - before
        w[:nc] += correction
        w[nc:] += 0.5 * (correction[pa] + correction[pb])
        np.maximum(w, 0.0, out=w)
        return self._sweep(k, w, extra, 1, steps, newton_tolerance)

    def solve(self, start_humidity, tolerance, max_trips, steps, coarsest_cycles):
        """Solve on every mesh in turn, each answer starting the next finer one. Returns the answer on the
        finest mesh, the trips used there, and the largest change of its last sweep."""
        newton_tolerance = 0.1 * tolerance
        humidity = start_humidity
        w, trips, change = None, 0, 0.0
        for k, mesh in enumerate(self.meshes):
            if humidity.size < mesh.n:                    # carry the coarser answer onto the finer mesh
                pa, pb = mesh.parents[humidity.size:, 0], mesh.parents[humidity.size:, 1]
                humidity = np.concatenate([humidity, 0.5 * (humidity[pa] + humidity[pb])])
            w_sat = self.co[k][self.W_SAT]
            w = humidity * w_sat
            zero = np.zeros(mesh.n)
            for trips in range(1, max_trips + 1):
                change = self.cycle(k, w, zero, steps, newton_tolerance, coarsest_cycles)
                if change < tolerance:
                    break
            humidity = w / w_sat
        return w, trips, change


def rain_from_humidity(humidity, scale, steepness, at_one):
    """The rain law of sweep() for arrays: exponential in the humidity of the column up to saturation, a straight line above."""
    below = scale * np.exp(steepness * (np.minimum(humidity, 1.0) - at_one))
    return below * (1.0 + steepness * np.maximum(humidity - 1.0, 0.0))


def evaporation_from_humidity(humidity, at_zero_humidity):
    """The evaporation law of sweep() for arrays: falls in a straight line as the air fills, and stops at saturation."""
    return at_zero_humidity * np.maximum(1.0 - humidity, 0.0)
