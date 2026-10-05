"""Hydrology: what becomes of the water that falls on land.

Model (Assembled), in the order the water takes:

1. Snow. Snowfall fills a store on the ground and warmth empties it, by the degree-day rule of
   melt (Hock 2003; library/snow.py), through the year that repeats. Where more snow falls in
   a year than the year can melt, snow older than a set number of years leaves the cell as ice
   and is counted as runoff: that excess stands in for the flow of a glacier [INFERRED].
2. The air's demand for water. The Priestley-Taylor rule, in the form of Davis et al. 2017
   (library/evaporation.py): the energy the surface gains from radiation, times the share of
   it that goes into evaporating water at the cell's temperature and air pressure. The energy
   is the sunlight the ground absorbs less the heat it radiates away, both by the formulas of
   the same paper. They ask for the share of the possible hours of sunshine. The engine has no
   clouds to give it, so one share stands for every cell and month [INFERRED: the value that
   returns Earth's mean sunlight absorbed at the surface and Earth's mean loss of heat from
   it]. A day's mean is used, so what the night gives back as dew is taken off the day.
   Ground under snow gives the air nothing: the demand counts for the share of the cell that
   is free of snow [INFERRED: snow lost straight to the air is ignored].
3. Soil water. The bucket of Manabe's models (library/soil_water.py): rain and melted snow fill
   the soil, the air takes what it demands times how full the soil is, and what does not fit
   runs off.
4. Rivers. Each month the runoff is summed down the flow paths that Drainage found.
5. Lakes. Water that runs into a closed hollow floods it from the bottom up. Open water
   evaporates at the full demand of the air [INFERRED: the Priestley-Taylor rule is stated for
   a wet surface], worked out for a surface as dark as water: more than the land it covers
   gave. The lake spreads until that extra loss
   equals the water arriving: a closed lake, salt in the end. If the hollow fills to its pass
   first, the rest overflows and runs on (library/lakes.py, after Fill-Spill-Merge, Barnes,
   Callaghan and Wickert 2021). Nothing is placed: a dry basin, a closed lake and a lake with
   an outlet all follow from the water arriving against the loss of the flooded ground.

The water returned to the air, from soil and from lakes, is this process's member of the group
moisture_source, which Moisture reads in the next round: that is how rain inland is fed by
land upwind.

Ignores: groundwater; the time water takes along a river; wetlands and flood plains; lakes
that swell and shrink with the seasons, and the time a lake takes to fill; plants (their
roots, and their closing of pores in drought); frozen ground; snow lost straight to the air;
wind and the dryness of the air in the demand for water; and clouds: every cell gets the same
share of sunshine.
Wrong where: the timing of floods in very large basins. In deserts the real demand for water
is higher than the rule gives, twice over: the air is dry and the sky is clear. Closed lakes
there come out too large. Under the cloud of the wet tropics the demand is too high. A lake smaller than a cell
is drawn as a share of its cell, without a shape. Until FluvialErosion has cut valleys (build
step 4) the relief has far more closed hollows than a planet with rivers would keep, so far
too much of the land drains into lakes. The flow through a flooded cell counts the runoff of
the ground under the lake as if it were dry; the lake's own budget is right.
"""
import numpy as np

from ..library import drainage as dr
from ..library import evaporation as ev
from ..library import lakes as lk
from ..library.snow import degree_day_melt, snow_year
from ..library.soil_water import bucket_repeating
from ..library.units import MM_PER_M, SECONDS_PER_DAY, ZERO_CELSIUS_IN_K
from ..process import Process

NO_LAKE, LAKE_WITH_OUTLET, CLOSED_LAKE = range(3)


class BucketHydrology(Process):
    stage = "climate"
    reads = ("precipitation", "snowfall", "surface_temperature", "insolation", "elevation", "height_above_sea",
             "flow_receiver", "depression_id", "cell_area", "ocean_mask", "table:hollows")
    reads_lagged = ("soil_water_capacity",)
    writes = ("potential_evapotranspiration", "soil_moisture", "snow_water", "runoff", "runoff_annual", "river_discharge",
              "lake_fraction", "lake_level", "table:lakes")
    adds_to = {"moisture_source": "evapotranspiration"}
    shared = ("freezing_point_k", "snow_full_cover_mm")
    model = ("snow store with degree-day melt; Priestley-Taylor demand; Manabe's bucket; runoff summed down the flow paths; "
             "lakes that spread until their loss to the air matches the water arriving (after Fill-Spill-Merge)")
    drivers = {"runoff": ("from_rain", "from_snowmelt", "from_ice"),
               "river_discharge": ("local_runoff", "from_upstream", "largest_source"),
               "evapotranspiration": ("from_soil_and_plants", "from_lake"),
               "potential_evapotranspiration": ("net_radiation",),
               "lake_fraction": ("state", "lake")}
    additive = ("runoff", "river_discharge", "evapotranspiration")

    def run(self, ctx):
        c = ctx.const
        n, months = ctx.mesh.n, ctx.months
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        land = ~sea
        area = ctx.read("cell_area").astype(np.float64)
        month_seconds = ctx.planet["year_length_s"] / months
        temperature = ctx.read("surface_temperature").astype(np.float64)
        celsius = temperature - ZERO_CELSIUS_IN_K
        fall = np.where(land, ctx.read("precipitation").astype(np.float64), 0.0)
        snowfall = np.minimum(np.where(land, ctx.read("snowfall").astype(np.float64), 0.0), fall)
        rain = fall - snowfall

        # 1. snow
        could_melt = degree_day_melt(temperature, ctx.shared["freezing_point_k"], c["snow"]["melt_mm_per_day_per_k"],
                                     month_seconds / SECONDS_PER_DAY)
        snow, melted, ice = snow_year(snowfall, could_melt, c["snow"]["ice_after_years"])

        # 2. the air's demand for water, from ground and from open water
        d = c["demand"]
        height = ctx.read("height_above_sea").astype(np.float64)
        sunlight = ctx.read("insolation").astype(np.float64)
        loses = ev.net_longwave(celsius, d["sunshine_fraction"], d["longwave"])
        pressure = ev.air_pressure(height, ctx.planet["surface_gravity_m_s2"], d["air"])
        free_of_snow = 1.0 - np.clip(snow / ctx.shared["snow_full_cover_mm"], 0.0, 1.0)

        def asked(reflects):
            gains = ev.absorbed_sunlight(sunlight, height, d["sunshine_fraction"], reflects, d["sunlight"])
            rate = ev.priestley_taylor(gains - loses, celsius, pressure, d["priestley_taylor_extra"], d["vapour"], d["heat"], d["air"])
            return gains - loses, rate * month_seconds * free_of_snow
        net_radiation, demand = asked(d["sunlight"]["ground_reflects"])
        _, from_water = asked(d["sunlight"]["water_reflects"])          # a lake is darker than the ground: it takes up more

        # 3. soil water
        capacity = np.where(land, ctx.read_lagged("soil_water_capacity").astype(np.float64), 0.0)
        s = c["soil"]
        soil, from_soil, overflow, years, left = bucket_repeating(rain + melted, demand, capacity, s["critical_share"],
                                                                  s["years_most"], s["repeat_within_mm"])
        if left > s["repeat_within_mm"]:
            ctx.note("the soil water of some cells was still changing from one year to the next when the bucket stopped",
                     years_followed=years, largest_change_mm=round(left, 4))
        shed = overflow + ice                                         # mm a month, as if no cell were flooded

        # 4. and 5. rivers and lakes
        table = ctx.read("table:hollows")
        recv = ctx.read("flow_receiver").astype(np.int64)
        label = ctx.read("depression_id").astype(np.int64)
        ground = ctx.read("elevation").astype(np.float64)
        stack = dr.flow_stack(recv)
        own = dr.owners(ground, label, table)
        rows = len(table["parent"])
        volume = shed * area / MM_PER_M                               # m3 a month
        loss = np.maximum(from_water - from_soil, 0.0).sum(axis=0) * area / MM_PER_M  # m3 a year, if the cell is flooded
        leaves = np.flatnonzero((table["first_child"] < 0) & (np.arange(rows) > dr.SEA))
        plain = dr.accumulate(stack, recv, volume)
        inflow = np.zeros(rows)
        inflow[leaves] = plain[:, table["bottom_cell"][leaves]].sum(axis=0)
        room = np.bincount(own[own >= 0], weights=loss[own >= 0], minlength=rows)
        moved = lk.settle(table, inflow, room)
        if moved["nowhere"] > 0.0:
            ctx.note("more water reaches a hollow with no way out than its whole surface can lose to the air; the rest is dropped",
                     dropped_m3_per_year=float(moved["nowhere"]))
        share, level, lake = lk.flooded(table, own, ground, loss, moved["extra"], moved["overflows"])
        discharge, found = lk.lake_flows(table, label, recv, stack, volume, moved["extra"], moved["overflows"])

        to_air = np.where(land, (1.0 - share) * from_soil + share * from_water, 0.0)
        runoff = (1.0 - share) * shed
        in_lake = lake >= 0
        with np.errstate(invalid="ignore", divide="ignore"):
            moisture = np.where(capacity > 0.0, soil / np.where(capacity > 0.0, capacity, 1.0), np.nan)
        ctx.write("potential_evapotranspiration", np.where(land, demand, np.nan))
        ctx.write("soil_moisture", np.clip(moisture, 0.0, 1.0))
        ctx.write("snow_water", snow)
        ctx.write("runoff", runoff)
        ctx.write("runoff_annual", runoff.sum(axis=0))
        ctx.write("river_discharge", discharge / month_seconds)
        ctx.write("lake_fraction", share)
        ctx.write("lake_level", np.where(in_lake, level[np.maximum(lake, 0)], np.nan))
        ctx.add_to_group("moisture_source", to_air)

        # the table of lakes: one row per lake that receives water
        row_of = np.full(rows, -1, dtype=np.int64)
        row_of[found["row"]] = np.arange(found["row"].size)
        cells = np.flatnonzero(in_lake)
        lake_row = row_of[lake[cells]]
        flooded_area = np.bincount(lake_row, weights=(share * area)[cells], minlength=found["row"].size)
        depth = np.maximum(level[lake[cells]] - ground[cells], 0.0)
        held = np.bincount(lake_row, weights=(share * area)[cells] * np.where(np.isfinite(depth), depth, 0.0),
                           minlength=found["row"].size)
        hollow = found["row"]
        ctx.write_table("table:lakes", {
            "hollow": hollow.astype(np.int32), "bottom_cell": table["bottom_cell"][hollow], "level_m": level[hollow],
            "area_m2": flooded_area, "volume_m3": held, "inflow_m3_per_year": found["inflow"],
            "loss_to_air_m3_per_year": found["loss"], "outflow_m3_per_year": found["outflow"],
            "overflows": found["overflows"].astype(bool),
            "outlet_cell": np.where(found["overflows"], table["spill_from_cell"][hollow], -1).astype(np.int32),
            "spills_into_cell": found["into_cell"].astype(np.int32)})

        if ctx.recording:
            supply = rain + melted
            of_rain = np.where(supply > 0.0, rain / np.where(supply > 0.0, supply, 1.0), 0.0)
            ctx.driver("runoff", "from_rain", (1.0 - share) * overflow * of_rain)
            ctx.driver("runoff", "from_snowmelt", (1.0 - share) * overflow * (1.0 - of_rain))
            ctx.driver("runoff", "from_ice", (1.0 - share) * ice)
            local = volume / month_seconds
            ctx.driver("river_discharge", "local_runoff", local)
            ctx.driver("river_discharge", "from_upstream", discharge / month_seconds - local)
            # the way the water really takes: over the pass of every lake that overflows
            real = recv.copy()
            _, unit = lk.lake_units(table, moved["overflows"])
            out = unit[leaves]
            runs_on = moved["overflows"][out] & (table["spill_into_cell"][out] >= 0)
            real[table["bottom_cell"][leaves][runs_on]] = table["spill_into_cell"][out][runs_on]
            source = dr.largest_upstream(dr.flow_stack(real), real, volume.sum(axis=0))
            ctx.driver("river_discharge", "largest_source", source.astype(np.int32))
            ctx.driver("evapotranspiration", "from_soil_and_plants", np.where(land, (1.0 - share) * from_soil, 0.0))
            ctx.driver("evapotranspiration", "from_lake", np.where(land, share * from_water, 0.0))
            ctx.driver("potential_evapotranspiration", "net_radiation", np.where(land, net_radiation, np.nan))
            state = np.full(n, NO_LAKE, dtype=np.int32)
            state[cells] = np.where(found["overflows"][lake_row], LAKE_WITH_OUTLET, CLOSED_LAKE)
            ctx.driver("lake_fraction", "state", state)
            which = np.full(n, -1, dtype=np.int32)
            which[cells] = lake_row
            ctx.driver("lake_fraction", "lake", which)
