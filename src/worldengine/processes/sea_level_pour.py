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
is not consulted. In such a chain the last hollow is only part filled: its dry ground lies
below sea level with no barrier in the way, and the cause record says that the water ran out.
"""
import numpy as np

from ..library import flood
from ..library import operators as op
from ..process import Process

ABOVE_SEA_LEVEL, MAIN_SEA, SEPARATE_WATER, KEPT_DRY_BY_BARRIER, WATER_RAN_OUT = range(5)


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
            rows.append({"body": int(b), "surface_m": float(level[b]), "area_m2": float(area[cells].sum()),
                         "volume_m3": float((area[cells] * depth[cells]).sum()), "cells": int(cells.size),
                         "lowest_cell": int(cells[np.argmin(height[cells])])})
        rows.sort(key=lambda r: (-r["area_m2"], r["lowest_cell"]))
        main = rows[0]["body"] if rows else -1
        sea_level = rows[0]["surface_m"] if rows else 0.0   # with no water, heights are measured from the reference level
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
        ctx.write_table("table:seas", {name: [r[name] for r in rows]
                                       for name in ("surface_m", "area_m2", "volume_m3", "cells", "lowest_cell")})
        if ctx.recording:
            reason = np.where(in_main, MAIN_SEA, np.where(wet, SEPARATE_WATER, ABOVE_SEA_LEVEL)).astype(np.int32)
            barrier = np.full(n, -1, dtype=np.int32)
            low = ~wet & (height < sea_level)
            if low.any() and in_main.any():
                # Dry ground below sea level has one of two causes. Either the sea would have to rise over higher
                # ground to reach it, and that ground is the barrier. Or the way is open: the sea stands at its rim
                # and spilled into this hollow, and the water ran out before the hollow filled.
                reach, at = flood.barriers(height, mesh.nbr, mesh.nbr_count, in_main, sea_level)
                behind = low & (reach > sea_level)
                reason[behind] = KEPT_DRY_BY_BARRIER
                barrier[behind] = at[behind]
                reason[low & ~behind] = WATER_RAN_OUT
            ctx.driver("ocean_mask", "reason", reason)
            ctx.driver("ocean_mask", "barrier_cell", barrier)
            ctx.driver("height_above_sea", "ground_height", np.where(wet, surface, height))
            ctx.driver("height_above_sea", "sea_level", np.full(n, -sea_level))
