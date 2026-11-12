"""OceanCurrents, second version: the wind-driven ocean of build step 4, and an overturning driven by density.

The wind-driven part is the first version's (ocean_wind_driven.py), unchanged: the loops of one layer in the balance of
Stommel 1948 and Sverdrup, the Ekman drift of the surface layer and its upwelling, the heat they carry, held by soft
limits, and the depth the wind stirs. What this version adds is the overturning that the first version's `ignores`
names, the deep circulation driven by density, worked out from causes so that it finds its own place on any planet.

Salt (Assembled). The sea's surface salinity is the steady balance of a layer as deep as the one whose temperature the
loops carry: the salt that the freshwater balance leaves (evaporation from the sea less rain on it and the rivers that
reach it, Moisture's and Hydrology's fields of this round, as a flux of salt at the water's own salinity), carried by
the wind's loops and by the overturning's own upper water, and mixed along every side by eddies. Salt is kept: what
the freshwater balance of a connected sea leaves over is spread over it, and its mean is the planet's.

Density. A simplified equation of state, straight in salinity and curved in temperature (the form and coefficients
of Vallis 2006, as Nycander, Hieronymus and Roquet 2015 give them). The water is held at the freezing point of sea
water, since the engine's temperature over a winter sea is the air's.

Where the deep water forms. The sea is cut into regions: the latitudes at which deep sea runs all the way round the
planet are taken out, for there no coast holds up the east-west difference of pressure that a north-south flow in
the balance of the spin needs, and the rest falls into connected regions (on Earth the Atlantic, Indian and Pacific
join south of Africa and Australia into one region north of the Drake Passage, and the seas around Antarctica make
another). In each region the deep water forms in its densest open water over sea deeper than a set depth. Each
cell counts the month of its densest water, made lighter in the count by ice (a lid: water under ice all month counts
not at all) and by the wind's drift where it presses the light upper water down, as over an anticyclonic gyre (where
the drift lifts the water beneath, as in a cyclonic gyre, the light layer is thin) [INFERRED: after the
preconditioning of deep convection that Marshall and Schott 1999 describe, as recalled]. A cell's share of the
sinking is its area times a factor that falls by e for every set contrast by which its water counts as lighter than
the region's densest, so that two ends of a basin that are equally dense share the sinking equally, and the sinking
moves smoothly as the densities change (a sharp choice left the climate unsettled, MEASURED).

How much forms (Gnanadesikan 1999, the balance of the light upper water's volume as restated by Gnanadesikan, de Boer
and Mignone 2007, eqs. 2 and 3): the sinking g' D^2 / eps equals what mixing lifts over the region, 2 Kv A / D, plus
the wind's drift into the region across a latitude that goes round, tau Lx / (rho f), less the eddies' return across
it, A_I Lx D / Ly. g' is the planet's gravity times the sinking water's density over the mean density of the
region's surface water, and eps a set multiple of |f| where the water sinks. The deep water rises again where it is
lifted: evenly over the region by mixing, and at the border of a latitude that goes round by the wind's drift (or,
where the eddies return more than the wind brings, more water sinks there).

The upper water flows from where the deep water rises to where it sinks: a potential flow within each region. It
carries heat (in the advective form of the loops' heat, with a share of the gap between the surface and the deep
water) and salt; the deep water rises at the temperature of the water that sank in its region that month, so the
overturning moves heat and makes none. The salinity and the overturning are worked out together in passes, from the
last round's salinity: salt sets density, density sets the sinking, the overturning's flow carries salt, and the
salinity moves part of the way to the steady state of those flows, until it moves less than a set amount or a set
number of passes is reached.

Ignores: deep water made by the salt that freezing sea ice leaves behind (Antarctic Bottom Water forms under ice; here
ice is a lid), the layers of the deep sea and the depth at which each water mass spreads, the time the deep water
takes to travel (the overturning is steady within a year), the sills and straits that hold deep water back, the
mixing of the Southern Ocean's channel itself, the salt of the deep sea beyond the sinking water's, and the seasons of
the overturning.
Wrong where: the overturning chooses between states that feed themselves (salty water sinks, and its flow brings more
salt); each climate run starts from a sea with no overturning, so a planet whose ocean could hold either state gets
the one reached from there. On Earth's relief (the preview twin) the deep water forms at about 40 to 50 degrees north
in both northern oceans and in the subtropical North Pacific, where Earth's forms in the North Atlantic beyond 55
degrees: the twin's subtropical North Pacific holds 37.8 psu (Earth's about 35, UNVERIFIED: recalled), and its
northern seas are colder and more often frozen than Earth's [MEASURED: docs/BUILD_NOTES.md, section 28]. Every water mass that sinks fills the same deep sea. The upper water's path
is a potential flow, not the western boundary currents that carry it on Earth. The Southern Ocean's terms rest on the
wind of Circulation, which is weak over the twin's Southern Ocean, and they apply at the edge of any sea that goes
round, a polar sea among them. A latitude that goes round is found on the mesh's cells in bands of a set width: a gap
narrower than a band can be missed, and an aquaplanet has no region and no overturning.
"""
import numpy as np
import scipy.sparse.linalg as spla

from ..library import ocean as oc
from ..library import operators as op
from ..library import overturning as ov
from ..library.units import MM_PER_M, SECONDS_PER_DAY, TWO_PI
from ..process import Process


class WindAndDensityOcean(Process):
    stage = "climate"
    reads = ("wind", "ocean_mask", "coriolis_parameter", "surface_temperature", "cell_area", "sea_depth", "snow_ice_cover",
             "ocean_evaporation", "precipitation", "river_discharge")
    reads_lagged = ("sea_surface_salinity",)
    writes = ("ocean_current", "upwelling", "mixed_layer_depth", "sea_surface_salinity", "overturning_sinking")
    adds_to = {"surface_heat_flux": "ocean_heat_convergence"}
    shared = ("sea_ice_yearly_mean_below_k",)
    model = ("wind-driven loops (Sverdrup balance, Stommel 1948) and Ekman upwelling in one layer, with an overturning "
             "driven by density (Gnanadesikan 1999) and the salt that sets it")
    drivers = {"ocean_heat_convergence": ("carried_by_loops", "carried_by_drift", "upwelling", "carried_by_overturning",
                                          "evened_over_the_sea"),
               "ocean_current": ("loops", "drift", "overturning"), "mixed_layer_depth": ("friction_velocity_m_s",),
               "sea_surface_salinity": ("evaporation_less_rain_and_rivers_mm_yr",),
               "overturning_sinking": ("winter_density_kg_m3",)}
    additive = ("ocean_heat_convergence", "ocean_current")

    def run(self, ctx):
        c, mesh, months = ctx.const, ctx.mesh, ctx.months
        radius = ctx.planet["radius_m"]
        spin = TWO_PI / ctx.planet["rotation_period_s"]
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        f = ctx.read("coriolis_parameter").astype(np.float64)
        wind = ctx.read("wind").astype(np.float64)
        temp = ctx.read("surface_temperature").astype(np.float64)
        ctx.read("cell_area")
        rho, cp = c["sea_water_density_kg_m3"], c["sea_water_heat_capacity_j_kg_k"]
        # ---------------------------------------------------------------- the wind-driven ocean (the first version's)
        tau = oc.wind_stress(wind, c["air_density_kg_m3"], c["drag_coefficient"])           # (months, n, 3)
        tau = np.where(sea[None, :, None], tau, 0.0)
        lat = np.arcsin(np.clip(mesh.xyz[:, 2], -1.0, 1.0))
        beta = 2 * spin * np.cos(lat) / radius
        width = c["western_layer_cells"] * mesh.spacing() * radius
        friction = 2 * spin * np.cos(np.deg2rad(c["western_layer_set_at_deg"])) / radius * width
        psi = np.zeros(mesh.n)
        if sea.any():
            key = ("gyres", mesh.level, sea.tobytes(), friction, radius, spin)
            if key not in ctx.memo:
                ctx.memo[key] = spla.splu(oc.gyre_operator(mesh, sea, beta, friction, radius))
            rhs = (mesh.area * radius * radius) * oc.curl(mesh, tau.mean(axis=0), radius) / rho
            psi[sea] = ctx.memo[key].solve(rhs[sea])
        loops_q = oc.edge_transport(mesh, psi)                                              # m3/s, the whole layer
        loops_v = np.where(sea[:, None], oc.cell_velocity(mesh, psi, c["layer_depth_m"], radius), 0.0)
        r_e = 2 * spin * np.sin(np.deg2rad(c["equatorial_friction_latitude_deg"]))
        share = c["heat_layer_depth_m"] / c["layer_depth_m"]
        t_freeze = ctx.shared["sea_ice_yearly_mean_below_k"]
        yearly = temp.mean(axis=0)
        open_sea = sea & (yearly > t_freeze)
        deep_t = float(yearly[open_sea].min()) if open_sea.any() else float(yearly[sea].min()) if sea.any() else 0.0
        heat_loops, heat_drift, heat_up = (np.zeros((months, mesh.n)) for _ in range(3))
        rise = np.zeros((months, mesh.n))
        drift_v = np.zeros((months, mesh.n, 3))
        drift_q = np.zeros(mesh.edge_cells.shape[0])
        for m in range(months):
            M = np.where(sea[:, None], oc.ekman_transport(tau[m], f, r_e, rho, mesh.xyz), 0.0)
            w = oc.closed_divergence(mesh, M, sea, radius)                                  # m/s, up where positive
            rise[m] = w
            drift_v[m] = M / c["drift_depth_m"]
            across = oc.transport_across_edges(mesh, M, sea, radius)
            drift_q += across / months
            heat_loops[m] = rho * cp * share * oc.upwind_heating(mesh, loops_q, temp[m], radius)
            heat_drift[m] = rho * cp * oc.upwind_heating(mesh, across, temp[m], radius)
            raw = rho * cp * c["upwelling_efficiency"] * np.maximum(w, 0.0) * np.maximum(temp[m] - deep_t, 0.0)
            heat_up[m] = -c["upwelling_cooling_limit_w_m2"] * np.tanh(raw / c["upwelling_cooling_limit_w_m2"])
        carried = heat_loops + heat_drift
        limit = c["carried_heat_limit_w_m2"]                 # a soft limit: |heat| never passes it, small values pass unchanged
        bounded = limit * np.tanh(carried / limit)
        scale = np.where(np.abs(carried) > 0, bounded / np.where(carried == 0, 1.0, carried), 1.0)
        heat_loops, heat_drift = heat_loops * scale, heat_drift * scale
        # ---------------------------------------------------------------- the overturning driven by density
        o = c["overturning"]
        depth = ctx.read("sea_depth").astype(np.float64)
        ice = ctx.read("snow_ice_cover").astype(np.float64)
        month_s = ctx.planet["year_length_s"] / months
        evaporation = ctx.read("ocean_evaporation").astype(np.float64).mean(axis=0) / MM_PER_M / month_s     # m/s
        rain = ctx.read("precipitation").astype(np.float64).mean(axis=0) / MM_PER_M / month_s
        rivers = ctx.read("river_discharge").astype(np.float64).mean(axis=0)                                # m3/s
        area_m2 = mesh.area * radius * radius
        lost = np.where(sea, (evaporation - rain) * area_m2 - rivers, 0.0)                  # m3/s of water the sea loses
        deep = sea & (depth >= o["open_to_deep_m"])
        band_rad = o["band_spacings"] * mesh.spacing()
        gkey = ("overturning regions", mesh.level, sea.tobytes(), deep.tobytes(), band_rad, radius)
        if gkey not in ctx.memo:
            band, goes_round = ov.circumpolar(mesh, deep, band_rad)
            region = ov.regions(mesh, sea, sea & goes_round[band])
            ctx.memo[gkey] = (region, ov.channel_sides(mesh, sea, band, goes_round, region, band_rad, radius),
                              ov.branch_solver(mesh, region))
        region, sides, solver = ctx.memo[gkey]
        water = np.maximum(temp, o["freezing_point_k"])
        consts = {**o, "reference_density_kg_m3": rho, "loop_share": share, "salt_layer_m": c["heat_layer_depth_m"],
                  "lifting_scale_m_s": o["lifting_scale_m_yr"] / ctx.planet["year_length_s"]}
        f_floor = 2 * spin * np.sin(np.deg2rad(c["mixing_spin_floor_deg"]))
        out = {"salinity": np.zeros(mesh.n), "winter_density": np.zeros(mesh.n), "rise": np.zeros(mesh.n),
               "sink": np.zeros(mesh.n), "flow": np.zeros(mesh.edge_cells.shape[0]), "potential": np.zeros(mesh.n),
               "regions": {}}
        kept = ctx.read_lagged("sea_surface_salinity").astype(np.float64)     # the sea keeps its salt from round to round
        start = kept if np.isfinite(kept[sea]).all() else None                 # (missing in the first round: from rest)
        if sea.any():
            out = ov.overturn(mesh, consts, sea=sea, deep=deep, region=region, sides=sides, water_k=water,
                              ice=ice, lost=lost, loops_q=loops_q, ekman_q=drift_q,
                              spin_abs=np.maximum(np.abs(f), f_floor), gravity=ctx.planet["surface_gravity_m_s2"],
                              radius=radius, solver=solver, lifting=rise.mean(axis=0), start=start)
        branch = o["branch_share"]
        heat_over = rho * cp * branch * ov.heat(mesh, out["flow"], out["rise"], out["sink"], region, water, radius)
        made = heat_loops + heat_drift + heat_up + heat_over
        sea_area = (mesh.area * sea).sum()
        evened = np.zeros_like(made)
        if sea_area > 0:
            evened = -((made * (mesh.area * sea)).sum(axis=1) / sea_area)[:, None] * sea[None, :]
        total = np.where(sea[None, :], made + evened, 0.0)
        # the upper water's speed: its transport per unit width over the depth of the light upper water of its region
        upper_depth = np.zeros(mesh.n)
        for r, row in out["regions"].items():
            upper_depth[region == r] = row["depth_m"]
        held = np.where(upper_depth > 0, upper_depth, 1.0)
        over_v = np.where((upper_depth > 0)[:, None], -op.gradient(mesh, out["potential"]) / radius / held[:, None], 0.0)
        current = loops_v + drift_v.mean(axis=0) + over_v
        friction_velocity = np.sqrt(np.linalg.norm(tau, axis=-1).mean(axis=0) / rho)
        stirred = c["mixing_coefficient"] * friction_velocity / np.maximum(np.abs(f), f_floor)
        mixed = np.where(sea, np.clip(stirred, c["mixed_layer_m"][0], c["mixed_layer_m"][1]), 0.0)
        year_s = ctx.planet["year_length_s"]
        ctx.write("ocean_current", current)
        ctx.write("upwelling", rise * SECONDS_PER_DAY)                                     # m per day
        ctx.write("mixed_layer_depth", mixed)
        ctx.write("sea_surface_salinity", np.where(sea, out["salinity"], 0.0))
        ctx.write("overturning_sinking", np.where(sea, (out["sink"] - out["rise"]) / area_m2 * year_s, 0.0))    # m a year
        ctx.add_to_group("surface_heat_flux", total)
        if ctx.recording:
            ctx.driver("ocean_heat_convergence", "carried_by_loops", np.where(sea, heat_loops, 0.0))
            ctx.driver("ocean_heat_convergence", "carried_by_drift", np.where(sea, heat_drift, 0.0))
            ctx.driver("ocean_heat_convergence", "upwelling", np.where(sea, heat_up, 0.0))
            ctx.driver("ocean_heat_convergence", "carried_by_overturning", np.where(sea, heat_over, 0.0))
            ctx.driver("ocean_heat_convergence", "evened_over_the_sea", evened)
            ctx.driver("ocean_current", "loops", loops_v)
            ctx.driver("ocean_current", "drift", drift_v.mean(axis=0))
            ctx.driver("ocean_current", "overturning", over_v)
            ctx.driver("mixed_layer_depth", "friction_velocity_m_s", np.where(sea, friction_velocity, 0.0))
            ctx.driver("sea_surface_salinity", "evaporation_less_rain_and_rivers_mm_yr",
                       np.where(sea, lost / area_m2 * year_s * MM_PER_M, 0.0))
            ctx.driver("overturning_sinking", "winter_density_kg_m3", np.where(sea, np.nan_to_num(out["winter_density"]), 0.0))
