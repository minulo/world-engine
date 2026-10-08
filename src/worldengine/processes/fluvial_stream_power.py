"""FluvialErosion: rivers cut the land, and hillsides creep.

Model (Established). The stream power law: rock is worn away at E = K k Q^m S^n, with K a coefficient, k the
erodibility of the rock, Q the water that passes (drained area times runoff, relative to a reference runoff), S the
slope to the cell downstream, and n = 1. It is solved implicitly along the flow paths, from the sea upward, so a
round of 2 My is one stable step [Braun and Willett 2013, as Landlab's documentation of the method describes it;
UNVERIFIED: the paper itself was not opened]:
    h_new = (h + F h_new(downstream)) / (1 + F),   F = K k Q^m dt / L.
The flow paths are those of the land with every closed hollow filled (Priority-Flood), so that water crosses a hollow
to its outlet and the hollow's floor is not cut below its rim. Hillsides creep by one implicit diffusion step.
What is worn away leaves `elevation` now and is handed to Tectonics as thinning of the crust, which Isostasy turns
into the lasting change of height: a narrow valley keeps nearly all of its depth, a broadly worn range rebounds.
Ignores: where the eroded rock goes (laid down nowhere: the design's stated limit), glaciers, coasts.
Wrong where: the law depends on cell size, so K is set per mesh level. Before the climate is rerun inside the
history (build step 9) the runoff is the same everywhere.
"""
import heapq

import numpy as np
from numba import njit

from ..library import operators as op
from ..library.units import YEARS_PER_MY
from ..process import Process


@njit(cache=True)
def _flood_order(h, sea, nbr):
    """Priority-Flood from the sea: the receiver of each land cell on the filled surface, and the order in which
    the cells were reached (every cell after its receiver). Ties go to the lower cell number."""
    n = h.shape[0]
    recv = np.full(n, -1, dtype=np.int64)
    done = np.zeros(n, dtype=np.bool_)
    order = np.empty(n, dtype=np.int64)
    filled = h.copy()
    heap = [(0.0, np.int64(0))]
    heap.pop()
    for i in range(n):
        if sea[i]:
            heapq.heappush(heap, (h[i], np.int64(i)))
            done[i] = True
    count = 0
    while len(heap) > 0:
        level, i = heapq.heappop(heap)
        order[count] = i
        count += 1
        for j in nbr[i]:
            if j < 0 or done[j]:
                continue
            done[j] = True
            recv[j] = i
            filled[j] = max(h[j], level)
            heapq.heappush(heap, (filled[j], np.int64(j)))
    return recv, order[:count], filled


@njit(cache=True)
def _accumulate(order, recv, values):
    total = values.copy()
    for t in range(order.shape[0] - 1, -1, -1):
        i = order[t]
        r = recv[i]
        if r >= 0:
            total[r] += total[i]
    return total


@njit(cache=True)
def _implicit(order, recv, h, F, base, sea):
    out = h.copy()
    for t in range(order.shape[0]):
        i = order[t]
        if sea[i]:
            out[i] = h[i]
            continue
        r = recv[i]
        hr = base if sea[r] else out[r]
        if h[i] <= hr:                                    # a hollow's floor, below its outlet: not cut
            out[i] = h[i]
        else:
            out[i] = (h[i] + F[i] * hr) / (1.0 + F[i])
    return out


class StreamPowerErosion(Process):
    stage = "geological"
    reads = ("erodibility", "cell_area")
    reads_lagged = ("runoff_annual", "table:seas")
    modifies = ("elevation",)
    priority = 10
    writes = ("erosion_rate",)
    adds_to = {"crust_thickness_tendency": "erosion_thinning"}
    model = "the stream power law solved implicitly (Braun and Willett 2013), with hillside creep"
    drivers = {"erosion_rate": ("rivers", "creep")}
    additive = ("erosion_rate",)

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        radius = ctx.planet["radius_m"]
        dt_yr = float(ctx.step_length) * YEARS_PER_MY
        h = ctx.read("elevation").astype(np.float64)
        k = ctx.read("erodibility").astype(np.float64)
        area = ctx.read("cell_area").astype(np.float64)
        seas = ctx.read_lagged("table:seas")
        base = float(seas["surface_m"][0]) if seas["surface_m"].size else c["sea_level_before_any_sea_m"]
        runoff = ctx.read_lagged("runoff_annual").astype(np.float64)
        sea = h <= base
        if not (runoff[~sea] > 0).any():                  # no climate has run yet: one runoff everywhere
            runoff = np.full(h.size, c["reference_runoff_mm_per_year"])
        recv, order, _ = _flood_order(h, sea, mesh.nbr.astype(np.int64))
        q = _accumulate(order, recv, np.where(sea, 0.0, area * runoff / c["reference_runoff_mm_per_year"]))
        has = recv >= 0
        to = np.where(has, recv, 0)
        slot = np.argmax(mesh.nbr == to[:, None], axis=1)
        length = mesh.nbr_dist[np.arange(mesh.n), slot] * radius
        F = c["coefficient_per_year"] * k * q ** c["area_exponent_m"] * dt_yr / length
        cut = _implicit(order, recv, h, F, base, sea)
        rivers = np.maximum(h - cut, 0.0)
        # hillside creep: one implicit step of diffusion; only lowering is kept, as nothing is laid down
        reach = np.sqrt(c["creep_m2_per_year"] * dt_yr) / radius
        crept = op.smooth(mesh, cut, reach, ctx.memo)
        creep = np.where(sea, 0.0, np.maximum(cut - crept, 0.0))
        worn = rivers + creep
        ctx.write("elevation", h - worn)
        per_year = 1000.0 / dt_yr                         # m per round -> mm per year
        ctx.write("erosion_rate", worn * per_year)
        ctx.add_to_group("crust_thickness_tendency", -worn)
        ctx.driver("erosion_rate", "rivers", rivers * per_year)
        ctx.driver("erosion_rate", "creep", creep * per_year)
