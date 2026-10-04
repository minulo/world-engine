"""Isostasy: height from crust thickness, and ocean depth from the age of the floor.

Model (Assembled). Crust floats on denser rock beneath it, as ice floats on water, so thicker
crust stands higher (Airy isostasy). Height is the local crust thickness minus the depth of the
crust's root; the root is computed from a thickness smoothed over a set length, inside
continental crust only. Ocean depth follows the age of the floor (Parsons and Sclater 1977):
2500 + 350 sqrt(age) metres for young floor, and 6400 - 3200 exp(-age / 62.8) metres for old
floor, which levels off. The paper gives the first rule for ages up to 70 million years and the
second for ages above 20; in between both hold, and they differ by at most 78 m. The process
changes from the first to the second at the age where the two cross (about 26 million years),
so the depth has no step. Both the crust rule and the age rule measure from one reference level:
the height at which continental crust of normal thickness stands.

Ignores: ground held up or pulled down by flow deep below, differences in how stiff the plate
is, the weight of sediment and of water. It makes no deep ocean trenches.
Wrong where: broad swells and high plateaus far from plate edges, basins beside mountain belts,
trenches. The age rule was fitted under Earth's depth of water.
"""
import numpy as np
from scipy.optimize import brentq

from ..library import operators as op
from ..library.units import M_PER_KM
from ..process import Process

CONTINENTAL = 1


class AiryIsostasy(Process):
    stage = "geological"
    reads = ("crust_type", "crust_thickness", "ocean_crust_age")
    writes = ("elevation",)
    model = "Airy isostasy with the age-depth rule of Parsons and Sclater 1977"
    drivers = {"elevation": ("from_crust_thickness", "from_ocean_floor_age")}
    additive = ("elevation",)

    @staticmethod
    def _young(age, o):
        return o["ridge_depth_m"] + o["deepening_m_per_root_my"] * np.sqrt(age)

    @staticmethod
    def _old(age, o):
        return o["old_floor_depth_m"] - o["old_floor_amplitude_m"] * np.exp(-age / o["levelling_time_my"])

    @classmethod
    def _changeover(cls, o):
        """The age at which the rule for young floor hands over to the rule for old floor: where the two give the same
        depth, inside the span of ages in which the paper says both hold. If they do not cross there, the end of the
        span at which they lie closer."""
        first, last = o["old_rule_from_my"], o["young_rule_until_my"]
        gap = lambda age: float(cls._old(age, o) - cls._young(age, o))
        if gap(first) * gap(last) < 0:
            return brentq(gap, first, last, xtol=np.finfo(float).eps * last)
        return first if abs(gap(first)) <= abs(gap(last)) else last

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        land = ctx.read("crust_type") == CONTINENTAL
        thickness = ctx.read("crust_thickness").astype(np.float64)
        age = ctx.read("ocean_crust_age").astype(np.float64)
        ratio = c["crust_density_kg_m3"] / c["mantle_density_kg_m3"]
        # the root hangs from a thickness smoothed inside continental crust only
        length = c["root_smoothing_km"] * M_PER_KM / ctx.planet["radius_m"]
        mask = land.astype(np.float64)
        if land.any():
            weight = op.smooth(mesh, mask, length, ctx.memo)
            smooth = op.smooth(mesh, thickness * mask, length, ctx.memo) / np.maximum(weight, np.finfo(float).tiny)
        else:
            smooth = thickness
        from_thickness = thickness - ratio * smooth - c["continental_normal_thickness_m"] * (1 - ratio)
        # depth of ocean floor below the reference level
        o = c["ocean_floor"]
        t = np.where(np.isnan(age), 0.0, age)
        depth = np.where(t <= self._changeover(o), self._young(t, o), self._old(t, o))
        from_age = o["reference_offset_m"] - depth
        ctx.write("elevation", np.where(land, from_thickness, from_age))
        ctx.driver("elevation", "from_crust_thickness", np.where(land, from_thickness, 0.0))
        ctx.driver("elevation", "from_ocean_floor_age", np.where(land, 0.0, from_age))
