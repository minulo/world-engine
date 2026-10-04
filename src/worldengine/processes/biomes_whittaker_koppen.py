"""Biomes, first version: Whittaker's chart, with the Köppen-Geiger climate class alongside.

Model (Established). A biome is a large region with its own characteristic climate and plant
cover. Whittaker's chart assigns one from the mean yearly temperature and the yearly
precipitation; the outlines are those of Figure 5.5 in Ricklefs 2008, as digitised by the R
package plotbiomes. A cell whose warmest month is below freezing is ice, and has no plant cover;
at sea that means water that stays frozen all year, judged by the freezing point of sea water.
The Köppen-Geiger class follows the rules of Peel, Finlayson and McMahon 2007 (their Table 1),
which the maps of Beck et al. 2018 also use; the arid classes are identified first.

Ignores: seasons (the chart sees only yearly values), soils, fire, grazing, competition over
time, the level of carbon dioxide.
Wrong where: the edges of savanna and grassland that fire sets; climates with one very dry
season, which the chart cannot tell from evenly moist ones. A climate off the chart takes the
nearest biome on it. The climate classes and the chart assume 12 months.
"""
import numpy as np

from ..library.units import ZERO_CELSIUS_IN_K
from ..process import Process

RULE_SEA, RULE_FROZEN, RULE_ON_CHART, RULE_NEAREST, RULE_FROZEN_SEA = 0, 1, 2, 3, 4
LIMIT_NONE, LIMIT_COLD, LIMIT_DRY = 0, 1, 2
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


def koppen(temperature_c, rain_mm, k):
    """Köppen-Geiger class names for land cells from 12 monthly temperatures (C) and precipitation totals (mm)."""
    t, p = temperature_c, rain_mm
    n = t.shape[1]
    warm_half = np.array(k["summer_months_north"]) - 1
    cool_half = np.array([m for m in range(t.shape[0]) if m not in warm_half])
    summer = t[warm_half].mean(axis=0) >= t[cool_half].mean(axis=0)     # True where the listed months are the warmer half
    def pick(months_a, months_b, fn):
        return np.where(summer, fn(p[months_a], axis=0), fn(p[months_b], axis=0))
    p_s_dry, p_s_wet = pick(warm_half, cool_half, np.min), pick(warm_half, cool_half, np.max)
    p_w_dry, p_w_wet = pick(cool_half, warm_half, np.min), pick(cool_half, warm_half, np.max)
    p_summer = pick(warm_half, cool_half, np.sum)
    mat, t_cold, t_hot = t.mean(axis=0), t.min(axis=0), t.max(axis=0)
    warm_months = (t > k["warm_month_c"]).sum(axis=0)
    total, p_dry = p.sum(axis=0), p.min(axis=0)
    safe_total = np.maximum(total, np.finfo(float).tiny)
    threshold = k["arid_per_degree_mm"] * mat + np.where(
        (total - p_summer) / safe_total >= k["season_share"], 0.0,
        np.where(p_summer / safe_total >= k["season_share"], k["arid_summer_rain_mm"], k["arid_even_rain_mm"]))
    arid = total < k["arid_factor"] * threshold
    polar = ~arid & (t_hot <= k["warm_month_c"])
    tropical = ~arid & ~polar & (t_cold >= k["tropical_coldest_c"])
    cold = ~arid & ~polar & ~tropical & (t_cold <= k["cold_coldest_c"])
    temperate = ~arid & ~polar & ~tropical & ~cold
    names = np.full(n, "", dtype="U3")
    group = np.select([arid, tropical, temperate, cold, polar], [GROUP_ARID, GROUP_TROPICAL, GROUP_TEMPERATE, GROUP_COLD, GROUP_POLAR])
    desert = total < k["desert_factor"] * threshold
    hot = mat >= k["arid_hot_c"]
    for sel, name in ((arid & desert & hot, "BWh"), (arid & desert & ~hot, "BWk"), (arid & ~desert & hot, "BSh"), (arid & ~desert & ~hot, "BSk")):
        names[sel] = name
    rainforest = p_dry >= k["rainforest_driest_mm"]
    monsoon = ~rainforest & (p_dry >= k["monsoon_base_mm"] - total / k["monsoon_divisor"])
    names[tropical & rainforest] = "Af"
    names[tropical & monsoon] = "Am"
    names[tropical & ~rainforest & ~monsoon] = "Aw"
    dry_summer = (p_s_dry < k["dry_summer_mm"]) & (p_s_dry < p_w_wet / k["dry_summer_ratio"])
    dry_winter = ~dry_summer & (p_w_dry < p_s_wet / k["dry_winter_ratio"])
    hot_summer = t_hot >= k["hot_summer_c"]
    warm_summer = ~hot_summer & (warm_months >= k["warm_summer_months"])
    severe = ~hot_summer & ~warm_summer & (t_cold < k["severe_winter_c"])
    for main, sel in (("C", temperate), ("D", cold)):
        for second, s2 in (("s", dry_summer), ("w", dry_winter), ("f", ~dry_summer & ~dry_winter)):
            names[sel & s2 & hot_summer] = main + second + "a"
            names[sel & s2 & warm_summer] = main + second + "b"
            rest = sel & s2 & ~hot_summer & ~warm_summer
            names[rest] = main + second + "c"
            if main == "D":
                names[rest & severe] = main + second + "d"
    names[polar & (t_hot > k["frost_warmest_c"])] = "ET"
    names[polar & (t_hot <= k["frost_warmest_c"])] = "EF"
    return names, group


class WhittakerKoppen(Process):
    stage = "climate"
    reads = ("surface_temperature", "precipitation", "ocean_mask")
    writes = ("climate_class", "biome", "vegetation_cover")
    shared = ("freezing_point_k", "sea_freezing_point_k")
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
        frozen_sea = sea & (temperature.max(axis=0) < ctx.shared["sea_freezing_point_k"])       # sea that stays frozen all year
        out_biome[frozen_sea] = biome_names.index("ice")
        ctx.write("biome", out_biome)
        ctx.write("climate_class", out_class)
        ctx.write("vegetation_cover", np.broadcast_to(cover_of[out_biome], (months, n)))
        if ctx.recording:
            full = lambda values, fill, dtype: self._spread(n, land, values, fill, dtype)
            rule_all = full(rule, RULE_SEA, np.int32)
            rule_all[frozen_sea] = RULE_FROZEN_SEA
            ctx.driver("biome", "rule", rule_all)
            ctx.driver("biome", "limit", full(limit, LIMIT_NONE, np.int32))
            ctx.driver("biome", "yearly_temperature", full(mat + ZERO_CELSIUS_IN_K, np.nan, np.float64))
            ctx.driver("biome", "yearly_precipitation", full(yearly_cm * c["mm_per_cm"], np.nan, np.float64))
            ctx.driver("climate_class", "group", full(group, GROUP_SEA, np.int32))

    @staticmethod
    def _spread(n, land, values, fill, dtype):
        out = np.full(n, fill, dtype=dtype)
        out[land] = values
        return out
