"""Moisture, first version: one layer of air that carries water vapour.

Model (Adapted): a one-layer water budget, as in the atmosphere of the UVic model (Weaver et al.
2001). Vapour leaves the sea, travels with the wind, and falls where the air is too moist to
hold it. Three rules make rain here.
  Rain where the air is too moist: rain rises steeply with the humidity of the whole column,
    P = exp(11.4 (r - 0.522)) mm a day, the fit of Bretherton, Peters and Back 2004 (their
    equation 2) to monthly data over tropical seas.
    The design named a sharp threshold at 85 % humidity; the build replaced it, because with the
    threshold no rain fell anywhere in the trade-wind belts (measured; see docs/BUILD_NOTES.md).
    My extension: outside the tropics the rate is scaled by how much vapour the air can hold.
  Rain on rising ground: air forced up a slope cools and rains; on the far side it warms and
    dries, which is the rain shadow.
  Less rain under sinking air: the humidity needed for a given rain rises with the subsidence
    of the overturning loop.
Each month is solved as a steady state, because vapour stays in the air for only about ten days.
Vapour also mixes sideways, which stands for the passing storms the model does not follow.
Air moves sideways at its own height. So between a high cell and a low one, only the part of
each column that lies above the higher ground can cross, whether the wind carries it or mixing
does [INFERRED: my extension; the vapour is taken to thin with height at the fixed scale
height]. The vapour that cannot cross stays in the low cell and rains out there, at the foot of
the high ground. Without this rule, cold high ground draws in vapour that in truth lies below
it: mixing whole columns filled one cell to three times what it can hold (measured).

The wind that carries the vapour is made from the surface wind in two parts (the Helmholtz
split). The part that flows toward where the air rises is shallow, about a kilometre deep, while
vapour reaches higher, so that part carries only a share of the column. The part that circles
without gathering, the trades and the westerlies along their belts, is deep and carries all of it.

Ignores: the layers of the air, how thunderstorms organise, air blocked and turned aside by
ranges, evaporation from land (until Hydrology adds it to the group), passing storms.
Wrong where: land everywhere is too dry, because land gets only what the sea supplies: on
Earth about 40 % of the rain over land is water that evaporated from land (van der Ent et al.
2010, read at second hand). Rain totals in
the tropics; ranges narrower than a cell; hot land near 30 degrees in summer, where one layer
of air tends to rain where Earth has desert. One wind carries the vapour, a set share of the
surface wind, although the flow into the rain belt is shallow and the flow along the belts is
deep. Simple models of rain on slopes must be calibrated to perform well, and the same holds
for this whole budget: its constants were set by hand on the default planet.
"""
import hashlib

import numpy as np

from ..library import operators as op
from ..library.transport import Ladder, evaporation_from_humidity, rain_from_humidity
from ..library.units import SECONDS_PER_DAY, ZERO_CELSIUS_IN_K
from ..mesh import get_mesh
from ..process import Process


def saturation_vapour_density(temperature_k, s):
    """Mass of water vapour that a cubic metre of air can hold (kg/m3), from the saturation pressure over water."""
    t_c = temperature_k - ZERO_CELSIUS_IN_K
    pressure = s["pressure_at_zero_pa"] * np.exp(s["exponent_factor"] * t_c / (temperature_k - s["exponent_offset_k"]))
    return pressure / (s["vapour_gas_constant_j_kg_k"] * temperature_k)


class OneLayerMoisture(Process):
    stage = "climate"
    reads = ("wind", "subsidence", "surface_temperature", "height_above_sea", "ocean_mask", "cell_area")
    reads_groups_lagged = ("moisture_source",)
    writes = ("ocean_evaporation", "column_water", "precipitation", "snowfall")
    model = "one-layer water budget after the UVic model, with rain on rising ground and less rain under sinking air"
    drivers = {"precipitation": ("from_moist_air", "from_rising_ground", "stopped_by_sinking_air", "vapour_came_from"),
               "snowfall": ("share_falling_as_snow",)}
    additive = ("precipitation",)

    def run(self, ctx):
        c, mesh, months, n = ctx.const, ctx.mesh, ctx.months, ctx.mesh.n
        radius = ctx.planet["radius_m"]
        seconds = ctx.planet["year_length_s"] / months                    # length of a month
        wind = ctx.read("wind").astype(np.float64)                         # the wind at the surface
        # The wind that carries the vapour of the whole column. The part of the surface wind that flows toward where
        # the air rises is shallow, so it carries a small share of the column; the part that circles is deep.
        t = c["carrying_wind"]
        converging = np.stack([op.converging_part(mesh, wind[m], ctx.memo) for m in range(months)])
        carrying = t["share_of_turning_wind"] * (wind - converging) + t["share_of_converging_wind"] * converging
        sinking = ctx.read("subsidence").astype(np.float64)
        temperature = ctx.read("surface_temperature").astype(np.float64)
        height = ctx.read("height_above_sea").astype(np.float64)
        sea = ctx.read("ocean_mask")
        area = ctx.read("cell_area")
        land_source = ctx.read_group_lagged("moisture_source").total / seconds           # mm/month -> kg/m2/s

        ground = np.maximum(height, 0.0)
        slope = op.gradient(mesh, ground) / radius                       # rise of the ground per metre, as a vector
        # The budget is solved on a ladder of meshes, coarse to fine; the cells of each coarser mesh are the first
        # cells of the finer one, so a field is carried down the ladder by taking its first values.
        meshes = [get_mesh(k) for k in range(max(mesh.level - int(c["coarser_meshes"]), 0), mesh.level)] + [mesh]
        law = c["rain_law"]
        fixed = []
        ground_mark = hashlib.sha256(ground.tobytes()).hexdigest()       # the kept coefficients hold the ground's height
        for msh in meshes:
            key = ("moisture ladder", msh.level, radius, c["mixing_m2_s"], c["vapour_scale_height_m"], ground_mark)
            if key not in ctx.memo:
                valid = msh.nbr >= 0
                side = msh.nbr_dual * radius                             # length of each cell side, m
                idx = np.arange(msh.n)
                # Between two cells, only the share of each column that lies above the higher of the two grounds can
                # cross, by wind or by mixing: air moves sideways at its own height.
                own = ground[:msh.n][:, None]
                beside = ground[:msh.n][np.where(valid, msh.nbr, 0)]
                top = np.maximum(own, beside)
                share_own = np.exp(-(top - own) / c["vapour_scale_height_m"])
                share_beside = np.exp(-(top - beside) / c["vapour_scale_height_m"])
                mix = np.where(valid, c["mixing_m2_s"] * side / (msh.nbr_dist * radius), 0.0)
                ctx.memo[key] = (valid, side, share_own, share_beside, mix,
                                 np.where(valid, msh.nbr_edge, 0), msh.area * radius * radius,
                                 np.stack([np.lexsort((idx, msh.lon)), np.lexsort((idx, -msh.lon)),          # four sweep directions:
                                           np.lexsort((idx, msh.lat)), np.lexsort((idx, -msh.lat))]).astype(np.int64))   # east, west, north, south
            fixed.append(ctx.memo[key])

        shape = (months, n)
        water, evaporation, rain_moist = np.zeros(shape), np.zeros(shape), np.zeros(shape)
        rain_lift, rain_stopped = np.zeros(shape), np.zeros(shape)
        came_from = np.zeros(shape, dtype=np.int32)
        nb = np.where(mesh.nbr >= 0, mesh.nbr, 0)
        worst_change = 0.0
        for m in range(months):
            w_sat = saturation_vapour_density(temperature[m], c["saturation"]) * c["vapour_scale_height_m"]
            speed = np.sqrt(np.einsum("ij,ij->i", wind[m], wind[m]) + c["gust_m_s"] ** 2)     # of the surface wind, gusts included
            evap = np.where(sea, c["exchange_coefficient"] * speed * w_sat / c["vapour_scale_height_m"], 0.0)   # kg/m2/s at zero humidity
            rain_scale = w_sat / law["reference_column_kg_m2"] / SECONDS_PER_DAY         # kg/m2/s where the law gives 1 mm a day
            shifted = law["humidity_at_one_mm_per_day"] + c["sinking_shift"] * np.clip(sinking[m] / c["sinking_reference_mm_s"], 0.0, 1.0)
            upslope = np.maximum(np.einsum("ij,ij->i", wind[m], slope), 0.0)            # m/s of forced ascent
            lift = c["rising_ground_efficiency"] * upslope / c["vapour_scale_height_m"]
            coefficients = []
            for msh, (valid, side, share_own, share_beside, mix, edge, cell_area, orders) in zip(meshes, fixed):
                k = msh.n
                across = op.edge_normal_speed(msh, carrying[m][:k])[edge] * msh.nbr_sign  # outward speed across each side
                finest_inflow = np.where(valid, side * np.maximum(-across, 0.0) * share_beside, 0.0)
                coefficients.append((msh.nbr, msh.nbr_count, np.where(valid, side * np.maximum(across, 0.0) * share_own, 0.0),
                                     finest_inflow, mix * share_own, mix * share_beside, cell_area,
                                     np.ascontiguousarray(evap[:k]), np.ascontiguousarray(w_sat[:k]), np.ascontiguousarray(rain_scale[:k]),
                                     law["steepness"], np.ascontiguousarray(shifted[:k]), np.ascontiguousarray(lift[:k]),
                                     np.ascontiguousarray(land_source[m][:k]), orders))
            ladder = Ladder(meshes, coefficients)
            first_guess = np.full(meshes[0].n, law["humidity_at_one_mm_per_day"])        # the same first guess every month
            w, cycles, change = ladder.solve(first_guess, c["tolerance_kg_m2"], int(c["maximum_trips"]), int(c["newton_steps"]),
                                             int(c["coarsest_cycles"]))
            in_coef = finest_inflow
            humidity = w / w_sat
            if change >= c["tolerance_kg_m2"]:
                worst_change = max(worst_change, float(change))
            water[m] = w
            evaporation[m] = evaporation_from_humidity(humidity, evap)
            rain_lift[m] = lift * humidity * w
            at_plain = rain_from_humidity(humidity, rain_scale, law["steepness"], law["humidity_at_one_mm_per_day"])
            rain_moist[m] = at_plain
            rain_stopped[m] = rain_from_humidity(humidity, rain_scale, law["steepness"], shifted) - at_plain
            inflow = in_coef * w[nb]
            came_from[m] = np.where(inflow.max(axis=1) > 0, nb[np.arange(n), np.argmax(inflow, axis=1)], -1)
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
