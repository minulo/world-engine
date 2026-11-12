"""Biomes, first version: Whittaker's chart, with the Köppen-Geiger climate class alongside.

Model (Established). A biome is a large region with its own characteristic climate and plant
cover. Whittaker's chart assigns one from the mean yearly temperature and the yearly
precipitation; the outlines are those of Figure 5.5 in Ricklefs 2008, as digitised by the R
package plotbiomes. Land whose warmest month is below freezing is ice, and has no plant cover.
Sea is shown as ice where Albedo lays ice on it: where the mean temperature of the year is below
-10 C (North, Cahalan and Coakley 1981), so that the map and the reflected sunlight agree.
The Köppen-Geiger class follows the rules of Peel, Finlayson and McMahon 2007 (their Table 1),
which the maps of Beck et al. 2018 also use; the arid classes are identified first.

Ignores: seasons (the chart sees only yearly values), soils, fire, grazing, competition over
time, the level of carbon dioxide.
Wrong where: the edges of savanna and grassland that fire sets; climates with one very dry
season, which the chart cannot tell from evenly moist ones. A climate off the chart takes the
nearest biome on it. The climate classes and the chart assume 12 months.
"""
import numpy as np

from ..library.koppen import koppen  # noqa: F401  (the tests import it from here)
from ..library.units import ZERO_CELSIUS_IN_K
from ..process import Process

RULE_SEA, RULE_FROZEN, RULE_ON_CHART, RULE_NEAREST, RULE_FROZEN_SEA = 0, 1, 2, 3, 4
LIMIT_NONE, LIMIT_COLD, LIMIT_DRY, LIMIT_NOT_LAND = range(4)
GROUP_SEA, GROUP_ARID, GROUP_TROPICAL, GROUP_TEMPERATE, GROUP_COLD, GROUP_POLAR = 0, 1, 2, 3, 4, 5


def inside_outline(x, y, outline):
    """Points inside a closed outline of (x, y) corners: a ray to the right crosses its sides an odd number of times."""
    px, py = outline[:, 0], outline[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    inside = np.zeros(x.shape, dtype=bool)
    for a in range(px.size):                                   # a fixed order over the sides
        if py[a] == qy[a]:
            continue
        crosses = (py[a] > y) != (qy[a] > y)
        at = px[a] + (y - py[a]) * (qx[a] - px[a]) / (qy[a] - py[a])
        inside ^= crosses & (x < at)
    return inside


class WhittakerKoppen(Process):
    stage = "climate"
    reads = ("surface_temperature", "precipitation", "ocean_mask")
    writes = ("climate_class", "biome", "vegetation_cover")
    shared = ("freezing_point_k", "sea_ice_yearly_mean_below_k")
    model = "Whittaker's chart of yearly temperature against precipitation, with the Köppen-Geiger class"
    drivers = {"biome": ("rule", "limit", "yearly_temperature", "yearly_precipitation"), "climate_class": ("group",)}

    def run(self, ctx):
        c, n, months = ctx.const, ctx.mesh.n, ctx.months
        sea = ctx.read("ocean_mask")
        temperature = ctx.read("surface_temperature").astype(np.float64)
        rain = ctx.read("precipitation").astype(np.float64)
        land = np.flatnonzero(~sea)
        t_c = temperature[:, land] - ZERO_CELSIUS_IN_K
        mat, yearly_cm = t_c.mean(axis=0), rain[:, land].sum(axis=0) / c["mm_per_cm"]
        biome_names = list(ctx.categories("biome"))
        chart = [b for b in c["chart"] if "outline" in b]
        scale_t, scale_p = c["chart_scale"]["temperature_c"], c["chart_scale"]["precipitation_cm"]

        biome = np.full(land.size, -1, dtype=np.int64)
        nearest, distance = np.full(land.size, -1, dtype=np.int64), np.full(land.size, np.inf)
        for b in chart:                                        # the chart's own order; a point belongs to the first outline that holds it
            outline = np.array(b["outline"], dtype=np.float64)
            code = biome_names.index(b["name"])
            hit = (biome < 0) & inside_outline(mat, yearly_cm, outline)
            biome[hit] = code
            for corner in outline:
                d = ((mat - corner[0]) / scale_t) ** 2 + ((yearly_cm - corner[1]) / scale_p) ** 2
                closer = d < distance
                nearest[closer], distance[closer] = code, d[closer]
        rule = np.where(biome >= 0, RULE_ON_CHART, RULE_NEAREST)
        biome = np.where(biome >= 0, biome, nearest)
        frozen = t_c.max(axis=0) < ctx.shared["freezing_point_k"] - ZERO_CELSIUS_IN_K
        biome[frozen], rule[frozen] = biome_names.index("ice"), RULE_FROZEN
        dry_set = [biome_names.index(x) for x in c["limited_by_dryness"]]
        cold_set = [biome_names.index(x) for x in c["limited_by_cold"]]
        limit = np.where(np.isin(biome, cold_set), LIMIT_COLD, np.where(np.isin(biome, dry_set), LIMIT_DRY, LIMIT_NONE))

        class_names = list(ctx.categories("climate_class"))
        if months == c["koppen"]["months"]:
            names, group = koppen(t_c, rain[:, land], c["koppen"])
            lookup = {name: class_names.index(name) for name in class_names}
            classes = np.array([lookup[x] for x in names], dtype=np.int64)
        else:                                                   # the rules are written for 12 months
            ctx.note("the climate classes assume 12 months and were not computed", months=months)
            classes, group = np.full(land.size, class_names.index("ocean")), np.zeros(land.size, dtype=np.int64)

        cover_of = np.zeros(len(biome_names))
        for b in c["chart"]:
            cover_of[biome_names.index(b["name"])] = b.get("cover", 0.0)
        out_biome = np.full(n, biome_names.index("ocean"), dtype=np.int64)
        out_class = np.full(n, class_names.index("ocean"), dtype=np.int64)
        out_biome[land], out_class[land] = biome, classes
        frozen_sea = sea & (temperature.mean(axis=0) < ctx.shared["sea_ice_yearly_mean_below_k"])   # the sea ice of the Albedo rule
        out_biome[frozen_sea] = biome_names.index("ice")
        ctx.write("biome", out_biome)
        ctx.write("climate_class", out_class)
        ctx.write("vegetation_cover", np.broadcast_to(cover_of[out_biome], (months, n)))
        if ctx.recording:
            full = lambda values, fill, dtype: self._spread(n, land, values, fill, dtype)
            rule_all = full(rule, RULE_SEA, np.int32)
            rule_all[frozen_sea] = RULE_FROZEN_SEA
            ctx.driver("biome", "rule", rule_all)
            ctx.driver("biome", "limit", full(limit, LIMIT_NOT_LAND, np.int32))
            ctx.driver("biome", "yearly_temperature", full(mat + ZERO_CELSIUS_IN_K, np.nan, np.float64))
            ctx.driver("biome", "yearly_precipitation", full(yearly_cm * c["mm_per_cm"], np.nan, np.float64))
            ctx.driver("climate_class", "group", full(group, GROUP_SEA, np.int32))

    @staticmethod
    def _spread(n, land, values, fill, dtype):
        out = np.full(n, fill, dtype=dtype)
        out[land] = values
        return out
