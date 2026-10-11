"""Soils, second version: depth, water, fertility and the soil order (build step 7).

Model (Rule for the class, Established for the depth; design, Layer 5).
Depth: soil forms from rock more slowly as the soil thickens, "an exponential decline of soil production rates with
increasing soil depth" [DOCUMENTED in the design: Heimsath et al. 1997], P = P0 exp(-h / h0), balanced against the
erosion that FluvialErosion measured: at balance h = h0 ln(P0 / E), and none where erosion outpaces the fastest
production (bare rock). A young surface has not had the time: from bare rock, h(t) = h0 ln(1 + P0 t / h0) after t years,
and the soil is the thinner of the two. The fastest production P0 is the documented one under usual warmth and water, more
in hot wet ground and less in cold or dry ground [PROVISIONAL: a factor of my own on the documented law; a first factor
that only lowered P0 left 55 % of the default world's land as bare rock, where half the land wears at more than 0.03 mm
a year (MEASURED, build step 7)].
Water: the soil holds a set depth of water per metre, by the family of its rock, over the depth that roots reach.
Class: a rule table over Jenny's five factors (climate, living things, relief, parent rock, time) onto the 12 orders
of the USDA Soil Taxonomy, plus no-soil classes for ice, bare rock and shifting sand [DOCUMENTED in the design: Soils of
Canada for the factors; University of Idaho for the orders]. The rows are tried in order and the first that matches
wins; their thresholds are mine [PROVISIONAL], drawn from the definitions of the orders as the design describes them.
Fertility: a set share for each order, the soil's store of the nutrients plants take [PROVISIONAL].

Ignores: everything finer than an order, farming, and soil laid down by rivers, wind and ice. Flood plains and belts of
wind-blown silt are not made.
Wrong where: this is a classification, not a physical model: Jenny's equation "is purely a symbolic expression" and "is
without a solution in the mathematical sense" [DOCUMENTED in the design: Jeffrey]. Boundaries are sharper than in
nature. Surface ages count from the start of the history, so old shields are younger than they are.
"""
import numpy as np

from ..library.units import MM_PER_M, TINY, YEARS_PER_MY, ZERO_CELSIUS_IN_K
from ..process import Process

SEA_CELL = -1


class JennyRuleSoils(Process):
    stage = "climate"
    reads = ("surface_temperature", "precipitation", "potential_evapotranspiration", "soil_moisture", "rock_type", "slope",
             "surface_age", "erosion_rate", "permafrost", "snow_ice_cover")
    reads_lagged = ("vegetation_cover", "biome")
    writes = ("soil_order", "soil_depth", "soil_water_capacity", "soil_fertility")
    model = "soil depth from production that slows as the soil thickens (Heimsath et al. 1997) against erosion and time; the order from a rule table over Jenny's five factors"
    drivers = {"soil_order": ("rule",), "soil_depth": ("at_balance_with_erosion", "time_since_renewal", "cell_is"),
               "soil_water_capacity": ("per_metre", "root_depth", "cell_is"), "soil_fertility": ("cell_is",)}

    def run(self, ctx):
        c = ctx.const
        t = ctx.read("surface_temperature").astype(np.float64) - ZERO_CELSIUS_IN_K
        rain = ctx.read("precipitation").astype(np.float64).sum(axis=0)
        demand = ctx.read("potential_evapotranspiration").astype(np.float64).sum(axis=0)
        moist = ctx.read("soil_moisture").astype(np.float64)
        sea = np.isnan(moist).all(axis=0)
        rock = ctx.read("rock_type")
        slope = ctx.read("slope").astype(np.float64)
        age_my = ctx.read("surface_age").astype(np.float64)
        erosion = ctx.read("erosion_rate").astype(np.float64) / MM_PER_M                    # m per year
        frozen = ctx.read("permafrost").astype(np.float64)
        ice = ctx.read("snow_ice_cover").astype(np.float64).min(axis=0)
        plants = ctx.read_lagged("vegetation_cover").astype(np.float64).mean(axis=0)
        biome = ctx.read_lagged("biome")
        rocks, biomes, orders = ctx.categories("rock_type"), ctx.categories("biome"), list(ctx.categories("soil_order"))
        mat = t.mean(axis=0)
        wet = np.where(demand > 0, rain / np.maximum(demand, 1.0), c["wet_without_demand"])   # yearly rain over demand

        # depth: production slows as the soil thickens; at balance with erosion, and no older than the surface
        d = c["depth"]
        warmth = np.clip((mat - d["production_from_c"]) / (d["production_full_at_c"] - d["production_from_c"]), 0.0, 1.0)
        water = np.clip(wet, 0.0, 1.0)
        climate = np.clip(warmth * water / d["usual_warmth_and_water"], d["least_production_share"], d["most_production_share"])
        p0 = d["fastest_production_m_per_year"] * climate
        h0 = d["decline_depth_m"]
        balance = np.where(erosion > 0, h0 * np.log(np.maximum(p0 / np.maximum(erosion, TINY), 1.0)), d["deepest_m"])
        grown = h0 * np.log1p(p0 * np.maximum(age_my, d["least_time_my"]) * YEARS_PER_MY / h0)
        depth = np.clip(np.minimum(balance, grown), 0.0, d["deepest_m"])
        depth = np.where(sea, 0.0, depth)

        # the order: the first row of the table whose conditions all hold
        index = {"mean_temperature_c": mat, "wet": wet, "depth_m": depth, "slope": slope, "age_my": age_my,
                 "permafrost": frozen, "lasting_ice": ice, "plants": plants}
        order = np.full(ctx.mesh.n, -1, dtype=np.int64)
        rule_of = np.full(ctx.mesh.n, SEA_CELL, dtype=np.int32)
        for i, row in enumerate(c["orders"]):
            match = (order < 0) & ~sea
            for key, (lo, hi) in (row.get("where") or {}).items():
                if lo is not None:
                    match &= index[key] >= lo
                if hi is not None:
                    match &= index[key] < hi
            if "rock" in row:
                match &= np.isin(rock, [rocks.index(r) for r in row["rock"]])
            if "biome" in row:
                match &= np.isin(biome, [biomes.index(b) for b in row["biome"] if b in biomes])
            order[match] = orders.index(row["order"])
            rule_of[match] = i
        order[sea] = orders.index("none_sea")

        # water the soil holds for plants, and fertility
        per_metre = np.array([c["water_per_metre_mm"].get(r, c["water_per_metre_mm"]["default"]) for r in rocks])[rock]
        root = np.minimum(depth, c["root_depth_m"])
        capacity = np.where(sea, 0.0, np.maximum(per_metre * root, c["least_capacity_mm"]))
        fertility_of = np.array([c["fertility"].get(o, 0.0) for o in orders])
        ctx.write("soil_order", order.astype(np.int16))
        ctx.write("soil_depth", depth)
        ctx.write("soil_water_capacity", capacity)
        ctx.write("soil_fertility", np.where(sea, 0.0, fertility_of[order]))
        if ctx.recording:
            ctx.driver("soil_order", "rule", rule_of)
            ctx.driver("soil_depth", "at_balance_with_erosion", np.where(sea, np.nan, np.minimum(balance, d["deepest_m"])))
            ctx.driver("soil_depth", "time_since_renewal", np.where(sea, np.nan, age_my))
            ctx.driver("soil_water_capacity", "per_metre", np.where(sea, 0.0, per_metre))
            ctx.driver("soil_water_capacity", "root_depth", root)
            cell_is = sea.astype(np.int32)                                   # 0 land, 1 sea: the "why" answer of a sea cell
            for field in ("soil_depth", "soil_water_capacity", "soil_fertility"):
                ctx.driver(field, "cell_is", cell_is)
