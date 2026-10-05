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
   returns the mean sunlight absorbed at Earth's whole surface, land and sea, and the mean
   loss of heat from it; data/models.yaml gives the numbers, and what the same value misses
   over land alone]. The paper works with a day's mean, in which the night's loss of heat is
   set against the day's gain [DOCUMENTED: its equation 18].
   Ground under snow gives the air nothing: the demand is counted for the share of the ground
   that is free of snow on the month's average, and the field potential_evapotranspiration
   holds it that way [INFERRED: snow lost straight to the air is ignored]. That share, the
   month's mean of the cover of each day, is written as the field snow_cover, which Albedo
   reads in the next round.
3. Soil water. The bucket of Manabe's models (library/soil_water.py): rain and melted snow fill
   the soil, the air takes what it demands times how full the soil is, and what does not fit
   runs off.
4. Rivers. Each month the runoff is summed down the flow paths that Drainage found.
5. Lakes. Water that runs into a closed hollow floods it from the bottom up. Open water
   evaporates at the full demand of the air [INFERRED: the Priestley-Taylor rule is stated for
   a wet surface], worked out for a surface as dark as water: more than the land it covers
   gave. The lake spreads until that extra loss equals the water arriving: a closed lake. If
   the hollow fills to its pass first, the rest overflows and runs on (library/lakes.py, after
   Fill-Spill-Merge, Barnes, Callaghan and Wickert 2021). Nothing is placed: a dry basin, a
   closed lake and a lake with an outlet all follow from the water arriving against the loss
   of the flooded ground.
   A river that meets a lake with an outlet runs on through it: the flow is carried across
   the lake to its outlet cell and over the pass, less what the lake loses (library/lakes.py
   says how, and that the rule is mine).

The water returned to the air, from soil and from lakes, is this process's member of the group
moisture_source, which Moisture reads in the next round: rain inland can then be fed by land
upwind.

Before it uses the table of hollows, the process checks that the table keeps the rules it
relies on (library/lakes.py, check_table; data/tables.yaml states them) and refuses one that
does not.

Ignores: groundwater; the time water takes along a river; wetlands and flood plains; lakes
that swell and shrink with the seasons, and the time a lake takes to fill; the currents in a
lake; plants (their roots, and their closing of pores in drought); frozen ground; snow lost
straight to the air; wind and the dryness of the air in the demand for water; and clouds:
every cell gets the same share of sunshine.
Wrong where: the timing of floods in very large basins, and below every lake, whose outflow
keeps the seasons of its inflow. Over land the heat radiated away comes out too small with
the one share of sunshine, so the demand for water is too high on the whole [MEASURED against
Earth: docs/BUILD_NOTES.md]. In dry air and under a clear sky the real demand is higher than
the rule gives, so closed lakes in deserts come out too large; under the cloud of the wet
tropics it is lower [UNVERIFIED: both from memory of how the rule is used]. A lake smaller than
a cell is drawn as a share of its cell, without a shape, and a lake's level moves in steps of
the cells' heights. A hollow under snow that never melts loses nothing to the air, so it
fills and shows as a lake where a real one would hold ice. Far too much of the land drains
into closed hollows, and so into lakes: about half of the default world's land, and six
tenths of Earth's own relief once it is sampled on this mesh [MEASURED: docs/BUILD_NOTES.md],
where about a fifth of the real Earth's land drains to no sea [UNVERIFIED: recalled]. The
seeded relief has had no rivers to cut it, and a cell's mean height closes every valley
narrower than a cell. FluvialErosion (build step 4) cuts valleys on the mesh itself [INFERRED:
that this removes most of the excess; it is tested there].
"""
import numpy as np

from ..library import drainage as dr
from ..library import evaporation as ev
from ..library import lakes as lk
from ..library.snow import degree_day_melt, snow_year
from ..library.soil_water import bucket_repeating
from ..library.units import MM_PER_M, SECONDS_PER_DAY, ZERO_CELSIUS_IN_K
from ..process import Process

NO_LAKE, LAKE_WITH_OUTLET, CLOSED_LAKE, LAKE_WITH_NO_WAY_OUT = range(4)
DRY_LAND, PARTLY_UNDER_A_LAKE, UNDER_A_LAKE, AT_SEA = range(4)                  # what covers a cell
ON_DRY_GROUND, IN_A_LAKE_THAT_OVERFLOWS, IN_A_CLOSED_LAKE, RIVERS_END_AT_SEA = range(4)      # where a river is
NO_SNOW, SNOW_PART_OF_THE_YEAR, SNOW_ALL_YEAR, SNOW_ON_SEA = range(4)


class BucketHydrology(Process):
    stage = "climate"
    reads = ("precipitation", "snowfall", "surface_temperature", "insolation", "elevation", "height_above_sea",
             "flow_receiver", "depression_id", "cell_area", "ocean_mask", "table:hollows")
    reads_lagged = ("soil_water_capacity",)
    writes = ("potential_evapotranspiration", "soil_moisture", "snow_water", "snow_cover", "runoff", "runoff_annual",
              "river_discharge", "lake_fraction", "lake_level", "table:lakes")
    adds_to = {"moisture_source": "evapotranspiration"}
    shared = ("freezing_point_k",)
    model = ("snow store with degree-day melt; Priestley-Taylor demand; Manabe's bucket; runoff summed down the flow paths "
             "and through the lakes; lakes that spread until their loss to the air matches the water arriving "
             "(after Fill-Spill-Merge)")
    drivers = {"snow_water": ("state", "fell", "melted", "left_as_ice"),
               "snow_cover": ("state",),
               "potential_evapotranspiration": ("state", "net_radiation", "snow_free"),
               "soil_moisture": ("cover",),
               "runoff": ("from_rain", "from_snowmelt", "from_ice", "cover"),
               "river_discharge": ("local_runoff", "from_upstream", "through_lake", "largest_source", "place", "lake"),
               "evapotranspiration": ("from_soil_and_plants", "from_lake", "cover"),
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
        snow, melted, ice, white = snow_year(snowfall, could_melt, c["snow"]["ice_after_years"], c["snow"]["full_cover_mm"])

        # 2. the air's demand for water, from ground and from open water
        d = c["demand"]
        height = ctx.read("height_above_sea").astype(np.float64)
        sunlight = ctx.read("insolation").astype(np.float64)
        loses = ev.net_longwave(celsius, d["sunshine_fraction"], d["longwave"])
        pressure = ev.air_pressure(height, ctx.planet["surface_gravity_m_s2"], d["air"])
        free_of_snow = 1.0 - white

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
        lk.check_table(table, label, recv, sea, ground)
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
        flows = lk.lake_flows(table, label, recv, ground, ctx.mesh.nbr, share, lake, volume, moved["extra"], moved["overflows"])
        discharge, found, crossing = flows["discharge"], flows["lakes"], flows["crossing"]

        to_air = np.where(land, (1.0 - share) * from_soil + share * from_water, 0.0)
        runoff = (1.0 - share) * shed
        in_lake = lake >= 0
        with np.errstate(invalid="ignore", divide="ignore"):
            moisture = np.where(capacity > 0.0, soil / np.where(capacity > 0.0, capacity, 1.0), np.nan)
        moisture = share + (1.0 - share) * np.clip(moisture, 0.0, 1.0)          # ground under a lake counts as full
        ctx.write("potential_evapotranspiration", np.where(land, demand, np.nan))
        ctx.write("soil_moisture", moisture)
        ctx.write("snow_water", snow)
        ctx.write("snow_cover", white)
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
        count = found["row"].size
        wet = (share * area)[cells]                                   # m2 of each cell under water
        flooded_area = np.bincount(lake_row, weights=wet, minlength=count)
        depth = np.maximum(level[lake[cells]] - ground[cells], 0.0)
        held = np.bincount(lake_row, weights=wet * np.where(np.isfinite(depth), depth, 0.0), minlength=count)
        rained = np.bincount(lake_row, weights=wet * fall.sum(axis=0)[cells] / MM_PER_M, minlength=count)
        evaporated = np.bincount(lake_row, weights=wet * from_water.sum(axis=0)[cells] / MM_PER_M, minlength=count)
        hollow = found["row"]
        ctx.write_table("table:lakes", {
            "hollow": hollow.astype(np.int32), "bottom_cell": table["bottom_cell"][hollow], "level_m": level[hollow],
            "area_m2": flooded_area, "volume_m3": held, "inflow_m3_per_year": found["inflow"],
            "loss_to_air_m3_per_year": found["loss"], "outflow_m3_per_year": found["outflow"],
            "left_over_m3_per_year": found["left_over"],
            "rain_on_lake_m3_per_year": rained, "evaporation_m3_per_year": evaporated,
            "overflows": found["overflows"].astype(bool),
            "outlet_cell": np.where(found["overflows"], table["spill_from_cell"][hollow], -1).astype(np.int32),
            "spills_into_cell": found["into_cell"].astype(np.int32)})

        if ctx.recording:
            cover = np.where(sea, AT_SEA, np.where(share >= 1.0, UNDER_A_LAKE, np.where(share > 0.0, PARTLY_UNDER_A_LAKE, DRY_LAND)))
            cover = cover.astype(np.int32)
            keeps = ice.sum(axis=0) > 0.0                             # snow that outlasts the summer
            lies = snow.sum(axis=0) > 0.0
            ctx.driver("snow_water", "state", np.where(sea, SNOW_ON_SEA, np.where(keeps, SNOW_ALL_YEAR, np.where(
                lies, SNOW_PART_OF_THE_YEAR, NO_SNOW))).astype(np.int32))
            ctx.driver("snow_cover", "state", np.where(sea, SNOW_ON_SEA, np.where(keeps, SNOW_ALL_YEAR, np.where(
                lies, SNOW_PART_OF_THE_YEAR, NO_SNOW))).astype(np.int32))
            ctx.driver("snow_water", "fell", snowfall)
            ctx.driver("snow_water", "melted", melted)
            ctx.driver("snow_water", "left_as_ice", ice)
            bare = free_of_snow.mean(axis=0)
            ctx.driver("potential_evapotranspiration", "state", np.where(sea, SNOW_ON_SEA, np.where(
                bare <= 0.0, SNOW_ALL_YEAR, np.where(bare < 1.0, SNOW_PART_OF_THE_YEAR, NO_SNOW))).astype(np.int32))
            ctx.driver("potential_evapotranspiration", "net_radiation", np.where(land, net_radiation, np.nan))
            ctx.driver("potential_evapotranspiration", "snow_free", np.where(land, free_of_snow, np.nan))
            ctx.driver("soil_moisture", "cover", cover)
            supply = rain + melted
            of_rain = np.where(supply > 0.0, rain / np.where(supply > 0.0, supply, 1.0), 0.0)
            ctx.driver("runoff", "from_rain", (1.0 - share) * overflow * of_rain)
            ctx.driver("runoff", "from_snowmelt", (1.0 - share) * overflow * (1.0 - of_rain))
            ctx.driver("runoff", "from_ice", (1.0 - share) * ice)
            ctx.driver("runoff", "cover", cover)
            # a river: on dry ground the runoff of the cell and what arrives; in a lake that overflows, what goes on
            flow = discharge / month_seconds
            crosses = crossing >= 0
            local = np.where(crosses, 0.0, (1.0 - share) * volume / month_seconds)
            through = np.where(crosses, flow, 0.0)
            ctx.driver("river_discharge", "local_runoff", local)
            ctx.driver("river_discharge", "through_lake", through)
            ctx.driver("river_discharge", "from_upstream", flow - local - through)
            source = dr.largest_upstream(flows["stack"], flows["receivers"], volume.sum(axis=0))
            ctx.driver("river_discharge", "largest_source", source.astype(np.int32))
            ctx.driver("river_discharge", "place", np.where(sea, RIVERS_END_AT_SEA, np.where(
                crosses, IN_A_LAKE_THAT_OVERFLOWS, np.where(share > 0.0, IN_A_CLOSED_LAKE, ON_DRY_GROUND))).astype(np.int32))
            which = np.full(n, -1, dtype=np.int32)
            which[cells] = lake_row
            through_row = np.where(crosses, row_of[np.maximum(crossing, 0)], which)
            ctx.driver("river_discharge", "lake", through_row.astype(np.int32))
            ctx.driver("evapotranspiration", "from_soil_and_plants", np.where(land, (1.0 - share) * from_soil, 0.0))
            ctx.driver("evapotranspiration", "from_lake", np.where(land, share * from_water, 0.0))
            ctx.driver("evapotranspiration", "cover", cover)
            state = np.full(n, NO_LAKE, dtype=np.int32)
            state[cells] = np.where(found["overflows"][lake_row], LAKE_WITH_OUTLET,
                                    np.where(found["left_over"][lake_row] > 0.0, LAKE_WITH_NO_WAY_OUT, CLOSED_LAKE))
            ctx.driver("lake_fraction", "state", state)
            ctx.driver("lake_fraction", "lake", which)
