"""OceanCurrents: the wind-driven ocean, its upwelling and the heat it carries (build step 4).

Model (Established, with the design's additions). The wind-driven loop model [DOCUMENTED in the design: University of
Hawaii notes]: in mid-ocean the twisting force of the wind sets a slow drift (Sverdrup balance); friction closes each
loop with a narrow, fast current on the western side of the basin (Stommel 1948). The model ocean is one uniform layer
over a flat floor. The yearly mean wind stress drives one steady streamfunction psi on the sea cells:

    r lap(psi) + beta d(psi)/dx = curl(tau) / rho,   psi = 0 on every coast,

with the current k x grad(psi) / depth. The friction r is set so that the western boundary layer, r / beta, is a set
number of cells wide at the latitude where it is set: the design's "it cannot be narrower than a few cells".
Upwelling, deep water rising to the surface, comes from the wind pushing surface water away from a coast, or apart
along the equator [DOCUMENTED in the design: Ekman transport]: the transport of the surface layer is
(r_e tau - f k x tau) / (rho (r_e^2 + f^2)), where near the equator a friction r_e replaces the spin term, which is zero
there; its divergence with no flow across a coast is the upwelling. Upwelled water cools the surface through an assumed
deep-water temperature, the coldest ice-free sea [the design's choice], with a set efficiency.

Bounds (a departure from the design, build step 4): the cooling by upwelling, and the heat the loops and the drift carry
into a cell, each pass through a soft limit, x -> L tanh(x / L). Without them the climate rounds ran away [MEASURED on
the default world: the heat of one equatorial cell went from -2,600 W/m2 in the first round to -2.8e14 in the eighth].
The loop is the Bjerknes feedback: cold upwelled water raises the pressure (Circulation's warm-surface rule), the wind
strengthens, more water upwells. The real ocean bounds it through the depth of its warm layer, which one layer lacks.

Heat (written monthly into ocean_heat_convergence, a member of surface_heat_flux): the loops and the drift carry the
temperature of the month's surface water across each edge (upwind, advective form) in a layer of set depth; upwelling
cools by its rate times the gap to the deep water. The ocean neither makes nor loses heat: each month the sum over the
sea is taken back out, spread evenly over the sea [INFERRED: the closure of a model with no deep ocean].

How deep the sea is stirred (a departure from the design's declarations, build step 4): the wind stirs the sea to the
Ekman depth scale, a coefficient times the friction velocity sqrt(|tau| / rho) over |f| [UNVERIFIED: the form of the
scale as recalled; the coefficient is PROVISIONAL], kept between two limits. EnergyBalance reads it in the next round as
the depth of the sea that the seasons warm and cool. The diagnosis of the cold northern summers (docs/BUILD_NOTES.md,
section 4.9) found the sea's seasons the larger cause, and left the mend to the ocean: "how deep wind and cooling stir
the sea". Cooling's share, convection in winter, is not modelled.

Ignores: deep overturning driven by density, eddies, layers in the sea, the shape of the sea floor, sea ice as a lid.
Wrong where: too little heat is carried poleward where deep overturning matters; channels that circle the globe have no
coast to lean on; the western current is wider and slower than real ones; straits narrower than a cell are lost.
"""
import numpy as np
import scipy.sparse.linalg as spla

from ..library import ocean as oc
from ..library.units import SECONDS_PER_DAY, TWO_PI
from ..process import Process


class WindDrivenOcean(Process):
    stage = "climate"
    reads = ("wind", "ocean_mask", "coriolis_parameter", "surface_temperature", "cell_area")
    writes = ("ocean_current", "upwelling", "mixed_layer_depth")
    adds_to = {"surface_heat_flux": "ocean_heat_convergence"}
    shared = ("sea_ice_yearly_mean_below_k",)
    model = "wind-driven loops (Sverdrup balance, Stommel 1948) and Ekman upwelling in one layer"
    drivers = {"ocean_heat_convergence": ("carried_by_loops", "carried_by_drift", "upwelling", "evened_over_the_sea"),
               "ocean_current": ("loops", "drift"), "mixed_layer_depth": ("friction_velocity_m_s",)}
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
        tau = oc.wind_stress(wind, c["air_density_kg_m3"], c["drag_coefficient"])           # (months, n, 3)
        tau = np.where(sea[None, :, None], tau, 0.0)
        lat = np.arcsin(np.clip(mesh.xyz[:, 2], -1.0, 1.0))
        beta = 2 * spin * np.cos(lat) / radius
        # the friction that makes the western layer a set number of cells wide where it is set
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
        # the wind-driven surface drift, month by month
        r_e = 2 * spin * np.sin(np.deg2rad(c["equatorial_friction_latitude_deg"]))
        share = c["heat_layer_depth_m"] / c["layer_depth_m"]
        t_freeze = ctx.shared["sea_ice_yearly_mean_below_k"]
        yearly = temp.mean(axis=0)
        open_sea = sea & (yearly > t_freeze)
        deep = float(yearly[open_sea].min()) if open_sea.any() else float(yearly[sea].min()) if sea.any() else 0.0
        heat_loops, heat_drift, heat_up = (np.zeros((months, mesh.n)) for _ in range(3))
        rise = np.zeros((months, mesh.n))
        drift_v = np.zeros((months, mesh.n, 3))
        for m in range(months):
            M = np.where(sea[:, None], oc.ekman_transport(tau[m], f, r_e, rho, mesh.xyz), 0.0)
            w = oc.closed_divergence(mesh, M, sea, radius)                                  # m/s, up where positive
            rise[m] = w
            drift_v[m] = M / c["drift_depth_m"]
            heat_loops[m] = rho * cp * share * oc.upwind_heating(mesh, loops_q, temp[m], radius)
            heat_drift[m] = rho * cp * oc.upwind_heating(mesh, oc.transport_across_edges(mesh, M, sea, radius), temp[m], radius)
            raw = rho * cp * c["upwelling_efficiency"] * np.maximum(w, 0.0) * np.maximum(temp[m] - deep, 0.0)
            heat_up[m] = -c["upwelling_cooling_limit_w_m2"] * np.tanh(raw / c["upwelling_cooling_limit_w_m2"])
        carried = heat_loops + heat_drift
        limit = c["carried_heat_limit_w_m2"]                 # a soft limit: |heat| never passes it, small values pass unchanged
        bounded = limit * np.tanh(carried / limit)
        scale = np.where(np.abs(carried) > 0, bounded / np.where(carried == 0, 1.0, carried), 1.0)
        heat_loops, heat_drift = heat_loops * scale, heat_drift * scale
        made = heat_loops + heat_drift + heat_up
        sea_area = (mesh.area * sea).sum()
        evened = np.zeros_like(made)
        if sea_area > 0:
            evened = -((made * (mesh.area * sea)).sum(axis=1) / sea_area)[:, None] * sea[None, :]
        total = np.where(sea[None, :], made + evened, 0.0)
        current = loops_v + drift_v.mean(axis=0)
        # how deep the wind stirs the sea: the Ekman depth scale, a coefficient times the friction velocity over |f|,
        # with f held at its value at a set latitude nearer the equator, and the depth kept between two limits
        friction_velocity = np.sqrt(np.linalg.norm(tau, axis=-1).mean(axis=0) / rho)
        f_floor = 2 * spin * np.sin(np.deg2rad(c["mixing_spin_floor_deg"]))
        stirred = c["mixing_coefficient"] * friction_velocity / np.maximum(np.abs(f), f_floor)
        mixed = np.where(sea, np.clip(stirred, c["mixed_layer_m"][0], c["mixed_layer_m"][1]), 0.0)
        ctx.write("ocean_current", current)
        ctx.write("upwelling", rise * SECONDS_PER_DAY)                                     # m per day
        ctx.write("mixed_layer_depth", mixed)
        ctx.add_to_group("surface_heat_flux", total)
        if ctx.recording:
            ctx.driver("ocean_heat_convergence", "carried_by_loops", np.where(sea, heat_loops, 0.0))
            ctx.driver("ocean_heat_convergence", "carried_by_drift", np.where(sea, heat_drift, 0.0))
            ctx.driver("ocean_heat_convergence", "upwelling", np.where(sea, heat_up, 0.0))
            ctx.driver("ocean_heat_convergence", "evened_over_the_sea", evened)
            ctx.driver("ocean_current", "loops", loops_v)
            ctx.driver("ocean_current", "drift", drift_v.mean(axis=0))
            ctx.driver("mixed_layer_depth", "friction_velocity_m_s", np.where(sea, friction_velocity, 0.0))
