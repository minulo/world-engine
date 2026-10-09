"""SurfaceAge: how long ago the ground was last renewed.

Model (Rule). Age grows by one round each round and resets to zero where lava covers the ground (strong
volcanism), where erosion cuts deep in a round, and where land rises from the sea. New ocean floor starts at zero.
The ages ride on the crust points: each round they are carried to the new table of crust points with the sources
and weights that Tectonics records there, and drawn onto the mesh from the nearest point.
Ignores: sediment that buries a surface, soils, ice.
Wrong where: ages before the history began are unknown; they count from its start.
"""
import numpy as np
from scipy.spatial import cKDTree

from ..library import operators as op
from ..library.units import MM_PER_M, TINY, YEARS_PER_MY
from ..process import Process


class PointSurfaceAge(Process):
    stage = "geological"
    reads = ("erosion_rate", "volcanism", "ocean_mask", "table:crust_points")
    reads_lagged = ("table:surface_age_points",)
    writes = ("surface_age", "table:surface_age_points")
    has_start = True
    model = "ages on the crust points, renewed by lava, deep erosion and rising from the sea"
    drivers = {"surface_age": ("renewed_by",)}

    def start(self, ctx):
        pts = ctx.read("table:crust_points")
        m = pts["x"].size
        ctx.write_table("table:surface_age_points", {"age_my": np.zeros(m), "was_sea": np.zeros(m, dtype=bool)})

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        dt = float(ctx.step_length)
        pts = ctx.read("table:crust_points")
        old = ctx.read_lagged("table:surface_age_points")
        old_age, old_sea = old["age_my"].astype(np.float64), old["was_sea"]
        src = np.stack([pts["source_a"], pts["source_b"], pts["source_c"]], axis=1).astype(np.int64)
        wts = np.stack([pts["weight_a"], pts["weight_b"], pts["weight_c"]], axis=1).astype(np.float64)
        known = (src >= 0) & (src < old_age.size)
        wts = np.where(known, wts, 0.0)
        total = wts.sum(axis=1)
        safe = np.where(known, src, 0)
        fresh = total <= 0                                   # new ocean floor: no older point
        age = np.where(fresh, 0.0, (old_age[safe] * wts).sum(axis=1) / np.maximum(total, TINY)) + np.where(fresh, 0.0, dt)
        was_sea = np.where(fresh, True, old_sea[safe[:, 0]])
        pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
        cell = op.nearest_cell(mesh, pos, ctx.memo)
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        lava = ctx.read("volcanism")[cell] > c["lava_above"]
        worn_m = ctx.read("erosion_rate")[cell] * dt * YEARS_PER_MY / MM_PER_M          # mm/yr over the round, in m
        deep = worn_m > c["deep_erosion_m_per_round"]
        risen = was_sea & ~sea[cell]
        reason = np.select([fresh, lava, deep, risen], [1, 2, 3, 4], 0)
        age = np.where(reason > 0, 0.0, age)
        ctx.write_table("table:surface_age_points", {"age_my": age, "was_sea": sea[cell]})
        near = cKDTree(pos).query(mesh.xyz)[1]
        ctx.write("surface_age", age[near])
        # the last renewal of the ground at the cell: 0 none in this round, 1 new floor, 2 lava, 3 deep erosion, 4 risen
        ctx.driver("surface_age", "renewed_by", reason[near].astype(np.int32))
