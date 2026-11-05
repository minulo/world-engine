"""StormClimatology: where storms grow and travel, on the climate clock (build step 8).

Model (Adapted; design, Layer 5).
Mid-latitude storms: their track density follows the storm growth rate that Circulation writes (the Eady rate),
carried downwind by the steering wind [INFERRED in the design]. Here the density is the steady answer of a transport
with decay: what the growth rate makes in a cell is carried with the steering wind and fades over a storm's life, so the
tracks lie downwind of where storms grow fastest. Solved for each month as one sparse linear system, upwind, in the
advective form, so that density does not pile up where the steering wind converges [INFERRED: the flux form drew bright
false tracks along the tropical convergence, MEASURED in build step 8]. Its unit is
the growth a storm passing the cell has gathered, in e-foldings (the growth rate times the days it acted): a number that
ranks places, not a count of storms.
Tropical cyclones: the genesis potential index of Emanuel and Nolan, built from low-level spin, mid-level humidity,
potential intensity and wind shear [DOCUMENTED in the design: Camargo et al. 2007]:
    GPI = |1e5 eta|^1.5 (H / 50)^3 (Vpot / 70)^3 (1 + 0.1 Vshear)^-2,
with eta the absolute vorticity (the planet's spin plus the curl of the surface wind), H the relative humidity in per
cent, Vpot the potential intensity and Vshear the change of wind with height (m/s) [UNVERIFIED: the exponents and
divisors are recalled, as published by Emanuel and Nolan 2004]. A one-layer engine has none of these at their heights:
the humidity is the column's water against what the column could hold at its temperature (Moisture's measure), and
the shear is the gap between the steering wind and the surface wind (my estimates [INFERRED]).
Potential intensity, the strongest wind the sea and air could sustain, is taken from the sea's temperature by an
empirical relation of the form A + B exp(C (T - T0)) [UNVERIFIED: the form and the constants are recalled, after DeMaria
and Kaplan 1994]; over land and over seas too cool for the relation it is zero.

Ignores: thunderstorms; storms acting on each other; the heights that the published index reads.
Wrong where: counts of storms; read the maps as where and when, not how many. Real storm tracks peak downwind of where
growth is fastest, which this only roughly follows.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..library import ocean as oc
from ..library.evaporation import saturation_vapour_density
from ..library.units import SECONDS_PER_DAY, TINY, ZERO_CELSIUS_IN_K
from ..process import Process

PER_CENT = 100.0


class StormMaps(Process):
    stage = "climate"
    reads = ("surface_temperature", "wind", "steering_wind", "baroclinicity", "column_water", "ocean_mask", "coriolis_parameter")
    writes = ("tc_genesis_potential", "potential_intensity", "storm_track_density")
    model = "storm tracks as storm growth carried by the steering wind; tropical cyclone genesis potential (Emanuel and Nolan)"
    drivers = {"tc_genesis_potential": ("spin", "humidity_per_cent", "potential_intensity_m_s", "shear_m_s"),
               "storm_track_density": ("growth_per_day",)}

    def run(self, ctx):
        c, mesh, months = ctx.const, ctx.mesh, ctx.months
        radius = ctx.planet["radius_m"]
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        t = ctx.read("surface_temperature").astype(np.float64)
        wind = ctx.read("wind").astype(np.float64)
        steer = ctx.read("steering_wind").astype(np.float64)
        growth = ctx.read("baroclinicity").astype(np.float64)                        # per day
        water = ctx.read("column_water").astype(np.float64)                           # mm
        f = ctx.read("coriolis_parameter").astype(np.float64)
        n = mesh.n
        area = mesh.area * radius * radius
        # mid-latitude tracks: steady transport of storm growth by the steering wind, with decay
        fade = 1.0 / (c["storm_life_days"] * SECONDS_PER_DAY)
        i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
        density = np.zeros((months, n))
        for m in range(months):
            q = oc.transport_across_edges(mesh, steer[m], np.ones(n, dtype=bool), radius)       # m2/s: per metre of depth
            out_i, out_j = np.maximum(q, 0.0), np.maximum(-q, 0.0)
            # the advective form: what flows in brings its own density, and a flow that gathers piles nothing up
            diag = area * fade + np.bincount(j, weights=out_i, minlength=n) + np.bincount(i, weights=out_j, minlength=n)
            rows = np.concatenate([j, i])
            cols = np.concatenate([i, j])
            vals = -np.concatenate([out_i, out_j])                       # what flows out of one cell comes into the other
            matrix = sp.csc_matrix((vals, (rows, cols)), shape=(n, n)) + sp.diags(diag)
            source = area * np.maximum(growth[m], 0.0) / SECONDS_PER_DAY
            density[m] = spla.spsolve(matrix, source)
        # tropical cyclones: the genesis potential index
        vorticity = np.stack([oc.curl(mesh, wind[m], radius) for m in range(months)])
        eta = np.abs(f[None, :] + vorticity)
        held = saturation_vapour_density(t, c["saturation"]) * c["vapour_scale_height_m"]                   # kg/m2, or mm
        humidity = np.clip(PER_CENT * water / np.maximum(held, TINY), 0.0, PER_CENT)
        sst_c = t - ZERO_CELSIUS_IN_K
        pi = c["intensity_a_m_s"] + c["intensity_b_m_s"] * np.exp(c["intensity_c_per_k"] * (sst_c - c["intensity_t0_c"]))
        pi = np.where(sea[None, :] & (sst_c > c["warm_enough_c"]), np.minimum(pi, c["intensity_cap_m_s"]), 0.0)
        shear = np.linalg.norm(steer - wind, axis=-1)
        g = c["gpi"]
        gpi = (np.abs(g["vorticity_scale"] * eta) ** g["vorticity_power"] * (humidity / g["humidity_ref"]) ** g["humidity_power"]
               * (pi / g["intensity_ref"]) ** g["intensity_power"] * (1 + g["shear_factor"] * shear) ** g["shear_power"])
        gpi = np.where(sea[None, :], gpi, 0.0)
        ctx.write("storm_track_density", density)
        ctx.write("tc_genesis_potential", gpi)
        ctx.write("potential_intensity", pi)
        if ctx.recording:
            ctx.driver("tc_genesis_potential", "spin", eta)
            ctx.driver("tc_genesis_potential", "humidity_per_cent", humidity)
            ctx.driver("tc_genesis_potential", "potential_intensity_m_s", pi)
            ctx.driver("tc_genesis_potential", "shear_m_s", shear)
            ctx.driver("storm_track_density", "growth_per_day", np.maximum(growth, 0.0))
