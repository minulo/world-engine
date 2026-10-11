"""Biomes, second version: BIOME1 of Prentice et al. 1992, with the Köppen-Geiger climate class alongside (build step 7).

Model (Established). A biome is a large region with its own characteristic climate and plant cover. BIOME1 admits
each plant functional type where five bioclimatic indices lie within its limits: the mean temperature of the coldest
month, the growing degree-days above 5 C and above 0 C, the mean temperature of the warmest month, and the
Priestley-Taylor coefficient, the yearly ratio of actual to potential evapotranspiration, a drought index. Of the types
admitted, those of the highest rank of dominance are kept, and the biome is the one whose set of types they make
[DOCUMENTED: Prentice et al. 1992, Tables 1 and 5, as tabulated in the CRAN package macroBiome (its sysdata.rda), read
on 2026-10-09; the paper itself was not opened]. A set that names no biome takes the biome whose set shares the most
types with it (my rule [INFERRED]; the tabulation leaves such a cell without a class).
In detail, from the monthly fields of the climate stage: degree-days are each month's days times its mean temperature
above the base; actual evapotranspiration in a month is the smaller of the demand (potential evapotranspiration) and a
supply that grows with the soil's moisture, a set rate times its relative moisture [the form of BIOME1's bucket as the
design describes it; the rate is UNVERIFIED]. The plant cover of a biome is a set share, smaller in the months too cold
for growth for the biomes that shed their leaves or die back, and smaller on poor soil.
Land under lasting ice, and sea under ice for most of the year, are ice; the rest of the sea is ocean.
The Köppen-Geiger class follows the rules of Peel, Finlayson and McMahon 2007 (library/koppen.py).

Ignores: fire, grazing, competition over time, the level of carbon dioxide, the soil's own effect on which types grow.
Wrong where: the edges of savanna and grassland that fire sets; degree-days from monthly means fall short where the
months straddle the base. The authors report "good agreement" with mapped ecosystems "except where intensive agriculture
has obliterated the natural patterns" [DOCUMENTED in the design: the abstract].
"""
import numpy as np

from ..library.koppen import GROUP_SEA, koppen
from ..library.units import SECONDS_PER_DAY, TINY, ZERO_CELSIUS_IN_K
from ..process import Process

RULE_SEA, RULE_ICE, RULE_TYPES, RULE_NEAREST_SET, RULE_SEA_ICE = 0, 1, 2, 3, 4
LIMIT_NONE, LIMIT_COLD, LIMIT_DRY, LIMIT_NOT_LAND = range(4)
INDICES = ("tc", "gdd5", "gdd0", "tw", "alpha")


class Biome1(Process):
    stage = "climate"
    reads = ("surface_temperature", "precipitation", "potential_evapotranspiration", "soil_moisture", "soil_water_capacity",
             "soil_fertility", "permafrost", "snow_ice_cover", "ocean_mask")
    writes = ("climate_class", "biome", "vegetation_cover")
    model = "BIOME1 (Prentice et al. 1992): plant types admitted by five bioclimatic indices, the dominant ones naming the biome; with the Köppen-Geiger class"
    drivers = {"biome": ("rule", "limit", "coldest_month", "warmest_month", "degree_days_above_5", "drought_index"),
               "climate_class": ("group",), "vegetation_cover": ("biome_cover", "season", "soil")}

    def run(self, ctx):
        c, n, months = ctx.const, ctx.mesh.n, ctx.months
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        land = np.flatnonzero(~sea)
        t = ctx.read("surface_temperature").astype(np.float64) - ZERO_CELSIUS_IN_K
        rain = ctx.read("precipitation").astype(np.float64)
        demand = ctx.read("potential_evapotranspiration").astype(np.float64)
        moist = np.nan_to_num(ctx.read("soil_moisture").astype(np.float64), nan=1.0)
        ctx.read("soil_water_capacity")
        ctx.read("permafrost")
        fertility = ctx.read("soil_fertility").astype(np.float64)
        cover_ice = ctx.read("snow_ice_cover").astype(np.float64)
        days = ctx.planet["year_length_s"] / months / SECONDS_PER_DAY
        tl = t[:, land]
        index = {"tc": tl.min(axis=0), "tw": tl.max(axis=0),
                 "gdd5": (days * np.maximum(tl - c["gdd_bases_c"]["gdd5"], 0.0)).sum(axis=0),
                 "gdd0": (days * np.maximum(tl - c["gdd_bases_c"]["gdd0"], 0.0)).sum(axis=0)}
        supply = c["supply_mm_per_day"] * days * moist[:, land]
        actual = np.minimum(demand[:, land], supply)
        total_demand = demand[:, land].sum(axis=0)
        index["alpha"] = np.where(total_demand > 0, actual.sum(axis=0) / np.maximum(total_demand, TINY), 1.0)

        types = c["plant_types"]
        present = np.ones((len(types), land.size), dtype=bool)
        for i, pt in enumerate(types):
            for key in INDICES:
                lo, hi = pt["limits"].get(key, [None, None])
                if lo is not None:
                    present[i] &= index[key] >= lo
                if hi is not None:
                    present[i] &= index[key] < hi
        rank = np.array([pt["dominance"] for pt in types])
        top = np.where(present, rank[:, None], np.iinfo(np.int64).max).min(axis=0)
        kept = present & (rank[:, None] == top[None, :])
        names = [pt["name"] for pt in types]
        biome_names = list(ctx.categories("biome"))
        table = [b for b in c["biomes"] if "plant_types" in b]                                      # (ocean and ice are not in it)
        sets = np.array([[pt in b["plant_types"] for pt in names] for b in table])                 # (biomes, types)
        same = (kept.T[:, None, :] == sets[None, :, :]).all(axis=2)                                 # (cells, biomes)
        shared = (kept.T[:, None, :] & sets[None, :, :]).sum(axis=2) / np.maximum((kept.T[:, None, :] | sets[None, :, :]).sum(axis=2), 1)
        exact = same.any(axis=1)
        choice = np.where(exact, np.argmax(same, axis=1), np.argmax(shared, axis=1))
        biome = np.array([biome_names.index(table[k]["name"]) for k in choice], dtype=np.int64)
        rule = np.where(exact, RULE_TYPES, RULE_NEAREST_SET)
        lasting_ice = cover_ice[:, land].min(axis=0) >= c["lasting_ice_cover"]
        biome[lasting_ice], rule[lasting_ice] = biome_names.index("ice"), RULE_ICE
        cold = [biome_names.index(x) for x in c["limited_by_cold"]]
        dry = [biome_names.index(x) for x in c["limited_by_dryness"]]
        limit = np.where(np.isin(biome, cold), LIMIT_COLD, np.where(np.isin(biome, dry), LIMIT_DRY, LIMIT_NONE))

        class_names = list(ctx.categories("climate_class"))
        if months == c["koppen"]["months"]:
            knames, group = koppen(tl, rain[:, land], c["koppen"])
            lookup = {name: class_names.index(name) for name in class_names}
            classes = np.array([lookup[x] for x in knames], dtype=np.int64)
        else:
            ctx.note("the climate classes assume 12 months and were not computed", months=months)
            classes, group = np.full(land.size, class_names.index("ocean")), np.zeros(land.size, dtype=np.int64)

        out_biome = np.full(n, biome_names.index("ocean"), dtype=np.int64)
        out_biome[land] = biome
        sea_ice = sea & (cover_ice.mean(axis=0) > c["sea_ice_biome_above"])
        out_biome[sea_ice] = biome_names.index("ice")
        out_class = np.full(n, class_names.index("ocean"), dtype=np.int64)
        out_class[land] = classes
        # plant cover: the biome's share, smaller in months too cold to grow for the biomes that shed leaves or die back,
        # and smaller on poor soil
        cover_of = np.zeros(len(biome_names))
        seasonal_of = np.zeros(len(biome_names), dtype=bool)
        for b in list(table) + list(c["without_plants"]):
            cover_of[biome_names.index(b["name"])] = b["cover"]
            seasonal_of[biome_names.index(b["name"])] = b.get("seasonal", False)
        base = np.broadcast_to(cover_of[out_biome], (months, n))
        grow = np.clip((t - c["growth_from_c"]) / (c["full_growth_at_c"] - c["growth_from_c"]), c["dormant_share"], 1.0)
        season = np.where(seasonal_of[out_biome][None, :], grow, 1.0)
        soil = np.where(sea, 1.0, 1.0 - c["poor_soil_effect"] * (1.0 - np.clip(fertility, 0.0, 1.0)))
        cover = base * season * soil[None, :]
        ctx.write("biome", out_biome)
        ctx.write("climate_class", out_class)
        ctx.write("vegetation_cover", cover)
        if ctx.recording:
            spread = lambda values, fill, dtype: self._spread(n, land, values, fill, dtype)
            rule_all = spread(rule, RULE_SEA, np.int32)
            rule_all[sea_ice] = RULE_SEA_ICE
            ctx.driver("biome", "rule", rule_all)
            ctx.driver("biome", "limit", spread(limit, LIMIT_NOT_LAND, np.int32))
            ctx.driver("biome", "coldest_month", spread(index["tc"] + ZERO_CELSIUS_IN_K, np.nan, np.float64))
            ctx.driver("biome", "warmest_month", spread(index["tw"] + ZERO_CELSIUS_IN_K, np.nan, np.float64))
            ctx.driver("biome", "degree_days_above_5", spread(index["gdd5"], np.nan, np.float64))
            ctx.driver("biome", "drought_index", spread(index["alpha"], np.nan, np.float64))
            ctx.driver("climate_class", "group", spread(group, GROUP_SEA, np.int32))
            ctx.driver("vegetation_cover", "biome_cover", base)
            ctx.driver("vegetation_cover", "season", season)
            ctx.driver("vegetation_cover", "soil", np.broadcast_to(soil, (months, n)))

    @staticmethod
    def _spread(n, land, values, fill, dtype):
        out = np.full(n, fill, dtype=dtype)
        out[land] = values
        return out
