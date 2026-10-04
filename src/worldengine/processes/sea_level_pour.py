"""SeaLevel: where the planet's water comes to rest.

Model (Adapted). The planet file gives a volume of water, not a level. The process pours that
volume in at the lowest point of the planet. The water fills a hollow to its rim, spills into
the next, and stops when the volume is used up (the Fill-Spill-Merge method of Barnes et al.
2021, used here for the sea itself). Every cell under the poured water counts as sea, whichever
body of water it lies in. The sea level is the surface of the body with the largest area.

Ignores: tides, the sinking of the sea floor under the weight of water, and water held as ice,
in lakes, in the ground and in the air.
Wrong where: straits narrower than a cell open or close by accident. With little water all of
it collects in the deepest hollows in a chain that starts at the lowest point, and the climate
is not consulted.
"""
import numpy as np

from ..library import flood
from ..library import operators as op
from ..process import Process

ABOVE_SEA_LEVEL, MAIN_SEA, SEPARATE_WATER, KEPT_DRY_BY_BARRIER = 0, 1, 2, 3


class PouredSea(Process):
    stage = "geological"
    reads = ("elevation", "cell_area")
    writes = ("ocean_mask", "sea_depth", "height_above_sea", "coast_distance", "table:seas")
    model = "a volume of water poured in at the lowest point (Fill-Spill-Merge, Barnes et al. 2021)"
    drivers = {"ocean_mask": ("reason", "barrier_cell"), "height_above_sea": ("ground_height", "sea_level")}

    def run(self, ctx):
        mesh, n = ctx.mesh, ctx.mesh.n
        radius = ctx.planet["radius_m"]
        height = ctx.read("elevation").astype(np.float64)
        area = ctx.read("cell_area")
        body, level = flood.pour(height, area, mesh.nbr, mesh.nbr_count, ctx.planet["surface_water_volume_m3"])
        surface = np.where(body >= 0, level[np.maximum(body, 0)] if level.size else 0.0, -np.inf)
        depth = np.maximum(surface - height, 0.0)
        wet = depth > 0.0
        # the bodies of water, largest area first
        ids = np.unique(body[wet])
        rows = []
        for b in ids:
            cells = np.flatnonzero(wet & (body == b))
            rows.append((-float(area[cells].sum()), int(cells[np.argmin(height[cells])]), float(level[b]),
                         float(area[cells].sum()), float((area[cells] * depth[cells]).sum()), int(cells.size), int(b)))
        rows.sort()
        main = rows[0][6] if rows else -1
        sea_level = rows[0][2] if rows else 0.0             # with no water, heights are measured from the reference level
        in_main = wet & (body == main)
        above = np.where(wet, surface, height) - sea_level
        if wet.any() and not wet.all():
            to_wet = op.arc_distance_to_set(mesh, wet)[0]
            to_dry = op.arc_distance_to_set(mesh, ~wet)[0]
            coast = np.where(wet, to_dry, to_wet) * radius
        else:
            coast = np.full(n, np.pi * radius)
        ctx.write("ocean_mask", wet)
        ctx.write("sea_depth", depth)
        ctx.write("height_above_sea", above)
        ctx.write("coast_distance", coast)
        ctx.write_table("table:seas", {
            "surface_m": [r[2] for r in rows], "area_m2": [r[3] for r in rows], "volume_m3": [r[4] for r in rows],
            "cells": [r[5] for r in rows], "lowest_cell": [r[1] for r in rows]})
        if ctx.recording:
            reason = np.where(in_main, MAIN_SEA, np.where(wet, SEPARATE_WATER, ABOVE_SEA_LEVEL)).astype(np.int32)
            barrier = np.full(n, -1, dtype=np.int32)
            low = ~wet & (height < sea_level)
            if low.any() and in_main.any():
                _, at = flood.barriers(height, mesh.nbr, mesh.nbr_count, in_main, sea_level)
                reason[low] = KEPT_DRY_BY_BARRIER
                barrier[low] = at[low]
            ctx.driver("ocean_mask", "reason", reason)
            ctx.driver("ocean_mask", "barrier_cell", barrier)
            ctx.driver("height_above_sea", "ground_height", np.where(wet, surface, height))
            ctx.driver("height_above_sea", "sea_level", np.full(n, -sea_level))
