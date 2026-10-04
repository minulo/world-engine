"""Moisture, first version: one layer of air that carries water vapour.

Model (Adapted): a one-layer water budget, as in the atmosphere of the UVic model (Weaver et al.
2001). Vapour leaves the sea, travels with the wind, and falls where the air is too moist to
hold it. Each month is solved as a steady state, because vapour stays in the air for only about
ten days [UNVERIFIED: the usual figure for Earth, recalled]. Vapour also mixes sideways, which
stands for the passing storms the model does not follow. Three rules make rain.
  Rain where the air is too moist: rain rises steeply with the humidity of the whole column,
    P = exp(11.4 (r - 0.522)) mm a day, the fit of Bretherton, Peters and Back 2004 (their
    equation 2) to monthly data over tropical seas. The design named a sharp threshold at 85 %
    humidity; the build replaced it, because with the threshold no rain fell anywhere in the
    trade-wind belts (measured; see docs/BUILD_NOTES.md). My extensions [INFERRED]: outside the
    tropics the rate is scaled by how much vapour the air can hold, and the law's value in air
    that holds no water is subtracted, so that such air gives no rain.
  Rain on rising ground: where the surface wind blows against higher ground, a set share of the
    vapour that lies below the higher ground's level falls as rain on that higher ground, more
    of it the moister the air [INFERRED: the share is a tuned number; in the simplest textbook
    picture all of that vapour would condense].
  Less rain under sinking air: the humidity needed for a given rain rises with the subsidence
    of the overturning loop.

The flow that carries the vapour. Circulation's surface wind flows toward where the air rises
in a layer about a kilometre deep, while vapour reaches higher [UNVERIFIED: my recollection of
the depth of Earth's trade-wind inflow]. So the carrying flow is first
fitted from the surface wind on flat ground: it is the smallest change to the surface wind's
flow after which it gathers and spreads only a set share as strongly as the surface wind does.
That is exactly the part of the wind that turns without gathering, plus the set share of the
part that gathers (the Helmholtz split).

High ground. Air moves sideways at its own height. So between a high cell and a low one, only
the part of each column that lies above the higher ground can cross, whether the wind carries
it or mixing does. That part is what air as cold as the column would be at the higher level
can hold, against what it can hold at the column's own ground (cooling with height at the
shared lapse rate), so that air moved onto high ground keeps its humidity [INFERRED: my
extension]. Three things follow.
  * Behind high ground more air leaves than crosses. The difference comes down from above the
    vapour and brings none, so the vapour there is thin: the rain shadow.
  * Before high ground more air arrives than can cross: it is held back. The share named above
    is lifted: of its vapour, the part given by the humidity rains on the higher ground, and
    what is left stays in the cell at the foot. The rest of the air is turned aside: it spreads
    through the part of the vapour layer that is open, over a set reach, and gathers there, which makes a
    broad wet zone before a long range and lets air flow around the end of a short one. This
    stands in for what the surface wind would do if Circulation knew the ground (the idea of
    mass-consistent wind models: Sasaki 1958, Sherman 1978) [INFERRED: my construction]. An
    earlier version let the held-back vapour pile up in the last cell before the high ground,
    where the rain grew without limit as the cells shrank (second review).
  * Ground below sea level counts as standing at sea level.

Ignores: the layers of the air, how thunderstorms organise, evaporation from land (until
Hydrology adds it to the group), passing storms, and how stable the air is, which in truth
decides how much of a flow goes over high ground and how much around it.
Wrong where: land everywhere is too dry, because land gets only what the sea supplies: on
Earth about 40 % of the rain over land is water that evaporated from land (van der Ent et al.
2010, read at second hand). Rain totals in the tropics; ranges narrower than a cell; hot land
near 30 degrees in summer, where one layer of air tends to rain where Earth has desert. Before
a long wall kilometres high the wet zone is probably too wet: about a third of the vapour held
back by a wall 2.5 km high rains within 500 km of it. The rain of rising ground falls on the
first higher cell, so at a cliff it grows as the cells shrink, while the amount per kilometre
of cliff stays the same; the seeded continents end in cliffs, which no real coast does. In the
default world the wettest such cell gets 3.2 m of this rain a year on the preview mesh, 6.5 m
at twice the detail and 12.5 m on the standard mesh [MEASURED]; spreading it over a set distance
inland would end that, and is left for the upgrade of this process (build step 5). Where the
air is cold the vapour layer is shallower than the fixed depth used to spread the held-back
air. Simple models of rain on slopes "must be calibrated to perform well" (Minder and Roe, in
the design's sources), and the same holds for this whole budget: its constants were set by hand
on the default planet.

A month in which nothing feeds the air (no sea, and no water given off by land) is not solved:
its steady state holds no water.
"""
import hashlib

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..library import operators as op
from ..library.transport import Ladder, evaporation_from_humidity, rain_from_humidity
from ..library.units import M_PER_KM, SECONDS_PER_DAY, ZERO_CELSIUS_IN_K
from ..mesh import get_mesh
from ..process import Process


def saturation_vapour_density(temperature_k, s):
    """Mass of water vapour that a cubic metre of air can hold (kg/m3), from the saturation pressure over water.
    Below the formula's lowest temperature the value at that temperature is used."""
    temperature_k = np.maximum(temperature_k, s["lowest_temperature_k"])
    t_c = temperature_k - ZERO_CELSIUS_IN_K
    pressure = s["pressure_at_zero_pa"] * np.exp(s["exponent_factor"] * t_c / (temperature_k - s["exponent_offset_k"]))
    return pressure / (s["vapour_gas_constant_j_kg_k"] * temperature_k)


class OneLayerMoisture(Process):
    stage = "climate"
    reads = ("wind", "subsidence", "surface_temperature", "height_above_sea", "ocean_mask", "cell_area")
    reads_groups_lagged = ("moisture_source",)
    writes = ("ocean_evaporation", "column_water", "precipitation", "snowfall")
    shared = ("lapse_rate_k_per_km",)
    model = ("one-layer water budget after the UVic model: vapour crosses high ground only above it, the air held back is "
             "partly lifted and partly turned aside, and sinking air brings less rain")
    drivers = {"precipitation": ("from_moist_air", "from_rising_ground", "stopped_by_sinking_air", "vapour_came_from"),
               "snowfall": ("share_falling_as_snow",)}
    additive = ("precipitation",)

    def _flat(self, ctx, msh):
        """What depends on the mesh alone: how easily the flow across each side is changed on flat ground, and the
        prepared solver that goes with it."""
        key = ("moisture flat", msh.level)
        if key not in ctx.memo:
            valid = msh.nbr >= 0
            ctx.memo[key] = (np.where(valid, msh.nbr_dual / np.where(valid, msh.nbr_dist, 1.0), 0.0),
                             op.potential_solver(op.laplacian_matrix(msh), msh.area))
        return ctx.memo[key]

    def _fixed(self, ctx, msh, ground, mark):
        """What depends only on the mesh and the ground, kept for the whole climate run: the geometry of the sides,
        how open each side is to a vapour layer, and the prepared solver that spreads the air held back by high ground."""
        c, radius = ctx.const, ctx.planet["radius_m"]
        reach = c["carrying_wind"]["turned_aside_reach_km"] * M_PER_KM / radius        # radians
        key = ("moisture ladder", msh.level, radius, c["mixing_m2_s"], c["vapour_scale_height_m"], reach, mark)
        if key not in ctx.memo:
            depth = c["vapour_scale_height_m"]
            valid = msh.nbr >= 0
            nb = np.where(valid, msh.nbr, 0)
            g = ground[:msh.n]
            first, second = msh.edge_cells[:, 0], msh.edge_cells[:, 1]
            open_edge = np.exp(-np.maximum(g[first], g[second]) / depth)   # share of a sea-level vapour layer above the higher ground
            idx = np.arange(msh.n)
            orders = np.stack([np.lexsort((idx, msh.lon)), np.lexsort((idx, -msh.lon)),             # four sweep directions:
                               np.lexsort((idx, msh.lat)), np.lexsort((idx, -msh.lat))])            # east, west, north, south
            spread = sp.diags(msh.area) - reach * reach * op.weighted_laplacian_matrix(msh, open_edge)
            ctx.memo[key] = dict(
                valid=valid, nb=nb, side=np.where(valid, msh.nbr_dual * radius, 0.0),               # side lengths, m
                rise=np.abs(g[nb] - g[:, None]) * valid, own_is_lower=g[:, None] < g[nb],
                open=np.where(valid, op.side_values(msh, open_edge), 1.0),
                aside=reach * reach * op.side_values(msh, open_edge * msh.edge_dual / msh.edge_dist),
                spread_solver=spla.splu(spread.tocsc()),
                layer=np.exp(-g / depth),                                  # share of a sea-level vapour layer above each cell's ground
                mix=np.where(valid, c["mixing_m2_s"] * msh.nbr_dual / np.where(valid, msh.nbr_dist, 1.0), 0.0),
                area=msh.area * radius * radius, orders=orders.astype(np.int64))
        return ctx.memo[key]

    def run(self, ctx):
        c, mesh, months, n = ctx.const, ctx.mesh, ctx.months, ctx.mesh.n
        seconds = ctx.planet["year_length_s"] / months                    # length of a month
        wind = ctx.read("wind").astype(np.float64)                         # the wind at the surface
        sinking = ctx.read("subsidence").astype(np.float64)
        temperature = ctx.read("surface_temperature").astype(np.float64)
        height = ctx.read("height_above_sea").astype(np.float64)
        sea = ctx.read("ocean_mask")
        land_source = ctx.read_group_lagged("moisture_source").total / seconds           # mm/month -> kg/m2/s

        ground = np.maximum(height, 0.0)                                 # ground below sea level counts as at sea level
        # The budget is solved on a ladder of meshes, coarse to fine; the cells of each coarser mesh are the first
        # cells of the finer one, so a field is carried down the ladder by taking its first values.
        meshes = [get_mesh(k) for k in range(max(mesh.level - int(c["coarser_meshes"]), 0), mesh.level)] + [mesh]
        mark = hashlib.sha256(ground.tobytes()).hexdigest()              # the kept coefficients hold the ground's height
        fixed = [self._fixed(ctx, msh, ground, mark) for msh in meshes]
        flat = [self._flat(ctx, msh) for msh in meshes]
        law, carry, saturation = c["rain_law"], c["carrying_wind"], c["saturation"]
        depth, efficiency = c["vapour_scale_height_m"], c["rising_ground_efficiency"]
        lapse = ctx.shared["lapse_rate_k_per_km"] / M_PER_KM

        shape = (months, n)
        water, evaporation, rain_moist = np.zeros(shape), np.zeros(shape), np.zeros(shape)
        rain_lift, rain_stopped = np.zeros(shape), np.zeros(shape)
        came_from = np.zeros(shape, dtype=np.int32)
        worst_change = 0.0
        for m in range(months):
            holds = saturation_vapour_density(temperature[m], saturation)                # kg/m3 at the surface
            w_sat = holds * depth
            speed = np.sqrt(np.einsum("ij,ij->i", wind[m], wind[m]) + c["gust_m_s"] ** 2)     # of the surface wind, gusts included
            evap = np.where(sea, c["exchange_coefficient"] * speed * holds, 0.0)         # kg/m2/s at zero humidity
            if not evap.any() and not land_source[m].any():
                # Nothing feeds the air in this month, so its steady state holds no water and no rain falls. The
                # solver would get there only slowly, because air that holds little water rains very little: it
                # stopped with a part of its first guess still in the air, more of it the finer the mesh (third check).
                came_from[m] = -1
                continue
            rain_scale = w_sat / law["reference_column_kg_m2"] / SECONDS_PER_DAY         # kg/m2/s where the law gives 1 mm a day
            shifted = law["humidity_at_one_mm_per_day"] + c["sinking_shift"] * np.clip(sinking[m] / c["sinking_reference_mm_s"], 0.0, 1.0)
            coefficients = []
            for msh, f, (flat_ease, flat_solver) in zip(meshes, fixed, flat):
                k = msh.n
                # The share of each column that lies above the higher of two neighbouring grounds: what the lower
                # column's air can hold once it is as cold as it would be at the higher level, against what it holds now.
                lower_t = np.where(f["own_is_lower"], temperature[m][:k][:, None], temperature[m][:k][f["nb"]])
                above = saturation_vapour_density(lower_t - lapse * f["rise"], saturation) / saturation_vapour_density(lower_t, saturation)
                share_own = np.where(f["own_is_lower"], above, 1.0)
                share_beside = np.where(f["own_is_lower"], 1.0, above)
                # The carrying flow on flat ground: the surface wind's flow, changed as little as possible so that it
                # gathers only a set share as strongly as the surface wind does.
                out_speed = op.side_speeds(msh, wind[m][:k])              # the surface wind, outward across each side
                through = out_speed * f["side"]
                carried = op.fit_side_flows(msh, carry["share_of_turning_wind"] * through,
                                            carry["share_of_converging_wind"] * through.sum(axis=1), flat_ease, flat_solver)
                # Over the ground as it is, only the open part of each side lets the flow pass. Where less can leave a
                # cell than arrives, air is held back. A share of it is lifted (the rain on rising ground, below); the
                # rest is turned aside: it spreads over the reach through whatever part of the layer is open, and
                # gathers there. Where more leaves than arrives, behind high ground, air comes down from above the
                # vapour and brings none: that thins the vapour in the lee.
                crossing = carried * f["open"]
                held = np.maximum(f["layer"] * carried.sum(axis=1) - crossing.sum(axis=1), 0.0)
                gathers = f["spread_solver"].solve(held)
                aside = f["aside"] * (gathers[:, None] - gathers[f["nb"]])
                flow = crossing + (1.0 - efficiency) * aside
                out_coef = np.maximum(flow, 0.0) * share_own / f["open"]
                in_coef = np.maximum(-flow, 0.0) * share_beside / f["open"]
                # Rain on rising ground: a share of the vapour that the surface wind pushes against higher ground, taken
                # from the part of the column below that ground's level.
                pushed = efficiency * np.maximum(out_speed, 0.0) * f["side"] * (1.0 - share_own)
                coefficients.append((msh.nbr, msh.nbr_count, out_coef, in_coef, f["mix"] * share_own, f["mix"] * share_beside,
                                     f["area"], np.ascontiguousarray(evap[:k]), np.ascontiguousarray(w_sat[:k]),
                                     np.ascontiguousarray(rain_scale[:k]), law["steepness"], np.ascontiguousarray(shifted[:k]),
                                     pushed.sum(axis=1) / f["area"], np.ascontiguousarray(land_source[m][:k]), f["orders"]))
            ladder = Ladder(meshes, coefficients)
            first_guess = np.full(meshes[0].n, law["humidity_at_one_mm_per_day"])        # the same first guess every month
            w, cycles, change = ladder.solve(first_guess, c["tolerance_kg_m2"], int(c["maximum_trips"]), int(c["newton_steps"]),
                                             int(c["coarsest_cycles"]))
            humidity = w / w_sat
            if change >= c["tolerance_kg_m2"]:
                worst_change = max(worst_change, float(change))
            f = fixed[-1]                                                  # the world's own mesh; pushed and in_coef are its
            water[m] = w
            evaporation[m] = evaporation_from_humidity(humidity, evap)
            # The rain of rising ground leaves the lower column and falls on the higher cell.
            rain_lift[m] = np.bincount(f["nb"].ravel(), weights=(pushed * (humidity * w)[:, None]).ravel(), minlength=n) / f["area"]
            at_plain = rain_from_humidity(humidity, rain_scale, law["steepness"], law["humidity_at_one_mm_per_day"])
            rain_moist[m] = at_plain
            rain_stopped[m] = rain_from_humidity(humidity, rain_scale, law["steepness"], shifted) - at_plain
            inflow = in_coef * w[f["nb"]]
            came_from[m] = np.where(inflow.max(axis=1) > 0, f["nb"][np.arange(n), np.argmax(inflow, axis=1)], -1)
        if worst_change > 0.0:
            ctx.note("the solver of the vapour budget stopped at its cap before reaching the tolerance",
                     cap=int(c["maximum_trips"]), tolerance_kg_m2=c["tolerance_kg_m2"])
        to_mm = seconds                                                    # kg/m2/s -> mm per month (1 kg/m2 of water is 1 mm)
        rain = (rain_moist + rain_lift + rain_stopped) * to_mm
        s = c["snow"]
        snow_share = np.clip((s["all_rain_above_k"] - temperature) / (s["all_rain_above_k"] - s["all_snow_below_k"]), 0.0, 1.0)
        ctx.write("column_water", water)
        ctx.write("ocean_evaporation", evaporation * to_mm)
        ctx.write("precipitation", rain)
        ctx.write("snowfall", rain * snow_share)
        if ctx.recording:
            ctx.driver("precipitation", "from_moist_air", rain_moist * to_mm)
            ctx.driver("precipitation", "from_rising_ground", rain_lift * to_mm)
            ctx.driver("precipitation", "stopped_by_sinking_air", rain_stopped * to_mm)
            ctx.driver("precipitation", "vapour_came_from", came_from)
            ctx.driver("snowfall", "share_falling_as_snow", snow_share)
