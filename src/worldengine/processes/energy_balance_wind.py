"""EnergyBalance, second version: spreading of heat, and heat carried by the wind (build step 5).

Model (Adapted): the energy balance model of North, Cahalan and Coakley 1981, as in the first version
(energy_balance_spreading.py), with the design's addition: "the full version also carries heat with last round's
wind". The wind of the previous round carries the temperature of the air across each side of a cell, upwind and in
advective form, in a column of air of set mass; the heat that arrives is a known amount in the equation, worked out
from the temperature of the round's own solution and solved again a set number of times with the same prepared
solver (design, Layer 3: the wind's heat as a known amount, so that the solver is prepared once for each climate run).
Where the wind spreads out of a cell, air sinks in from above: air that rose where the wind gathers, carried aloft
along the divergent part of the flow turned around, at the temperature it rose with. A closed overturning of one layer,
so that the wind moves heat and makes none (added on 2026-10-24: the advective form alone took 3.9 W/m2 out of the
Earth twin, about 1.9 K, most of the twin's cold bias of 2.1 K).
The depth of the sea that the seasons warm and cool is the one OceanCurrents stirred in the last round (a departure
from the design's declarations, build step 4: docs/BUILD_NOTES.md, section 4.9, found the sea's seasons the larger
cause of the cold northern summers). The spreading constant is fitted again with the wind and the ocean carrying heat (tools/fit_spreading.py), so that the
heat they carry is not carried twice.

    C dT/dt = Q (1 - albedo) - (A + B T) + D * Laplacian(T) + other heat + heat carried by the wind

Ignores: the layers of the air, heat carried as water vapour, the make-up of the air (A and B are fitted to Earth's
air and clouds), sea ice as a lid on the sea. The yearly cycle is held as its mean and a few waves in time.
Wrong where: high plateaus, which heat the air above them; anything narrower than the spreading length. The seasons
of land are too weak (the first version's largest known error; this version measures whether the wind mends it).
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..library import ocean as oc
from ..library import operators as op
from ..library.units import M_PER_KM, TWO_PI, ZERO_CELSIUS_IN_K
from ..process import Process


class WindEnergyBalance(Process):
    stage = "climate"
    reads = ("insolation", "albedo", "ocean_mask", "height_above_sea", "cell_area")
    reads_lagged = ("wind", "mixed_layer_depth")
    reads_groups_lagged = ("surface_heat_flux",)
    writes = ("surface_temperature",)
    shared = ("lapse_rate_k_per_km",)
    model = "energy balance model of North, Cahalan and Coakley 1981, with heat carried by last round's wind"
    drivers = {"surface_temperature": ("sunlight_against_heat_loss", "spread_from_neighbours", "seasonal_storage",
                                       "other_heat", "carried_by_wind", "cooling_from_height")}
    additive = ("surface_temperature",)

    def run(self, ctx):
        c, mesh, months = ctx.const, ctx.mesh, ctx.months
        radius = ctx.planet["radius_m"]
        sea = ctx.read("ocean_mask")
        area = ctx.read("cell_area") / (radius * radius)                 # steradians
        absorbed = ctx.read("insolation").astype(np.float64) * (1 - ctx.read("albedo").astype(np.float64))
        other = ctx.read_group_lagged("surface_heat_flux").total
        height = np.maximum(ctx.read("height_above_sea").astype(np.float64), 0.0)
        a, b = c["loss_at_zero_celsius_w_m2"], c["loss_per_kelvin_w_m2_k"]
        spread = c["spreading_constant_w_m2_k"] * (c["spreading_constant_radius_m"] / radius) ** 2
        # the sea warms through the depth that the wind stirred in the last round, in whole steps, so that the solver is
        # prepared again only when that depth changes by a step (a departure from the design: build step 4)
        stirred = ctx.read_lagged("mixed_layer_depth").astype(np.float64)
        stirred = np.where(sea & (stirred > 0), np.round(stirred / c["mixed_layer_step_m"]) * c["mixed_layer_step_m"],
                           c["heat_capacity_sea_j_m2_k"] / c["sea_heat_capacity_j_m3_k"])
        capacity = np.where(sea, c["sea_heat_capacity_j_m3_k"] * stirred, c["heat_capacity_land_j_m2_k"])
        waves = min(int(c["time_waves"]), months // 2)
        key = ("energy balance", mesh.level, waves, b, spread, capacity.tobytes(), ctx.planet["year_length_s"], sea.tobytes())
        if key not in ctx.memo:                                          # prepared again only when the stirred depth changes
            for old in [k for k in ctx.memo if isinstance(k, tuple) and k and k[0] == "energy balance"]:
                del ctx.memo[old]                                        # one prepared solver is kept at a time
            lap = op.laplacian_matrix(mesh)
            year_rate = TWO_PI / ctx.planet["year_length_s"]
            solvers = []
            for k in range(waves + 1):
                diag = area * (b + 1j * k * year_rate * capacity) if k else area * b
                solvers.append(spla.splu((sp.diags(diag) - spread * lap).tocsc()))
            ctx.memo[key] = (lap, solvers)
        lap, solvers = ctx.memo[key]
        forcing = absorbed - a + other                                   # W/m2, month by cell

        def solve(f):
            spectrum = np.fft.rfft(f, axis=0) / months
            answer = np.zeros_like(spectrum)
            for k in range(waves + 1):
                rhs = area * spectrum[k]
                answer[k] = solvers[k].solve(rhs.real) if k == 0 else solvers[k].solve(rhs)
            return np.fft.irfft(answer * months, n=months, axis=0)       # degrees C at sea level
        # the heat the wind of the last round carries: a known amount, from this round's own solution, solved again
        wind = ctx.read_lagged("wind").astype(np.float64)
        column = c["air_column_kg_m2"] * c["air_heat_capacity_j_kg_k"]                  # J/m2 per kelvin
        flows = [oc.transport_across_edges(mesh, wind[m], np.ones(mesh.n, dtype=bool), radius) for m in range(months)]
        carried = np.zeros((months, mesh.n))
        if ("upper branch", mesh.level) not in ctx.memo:                 # the flow aloft of the wind's overturning
            ctx.memo[("upper branch", mesh.level)] = oc.upper_branch_solver(mesh)
        upper = ctx.memo[("upper branch", mesh.level)]
        sea_level_c = solve(forcing)
        for _ in range(int(c["wind_heat_passes"])):
            carried = np.stack([column * (oc.upwind_heating(mesh, flows[m], sea_level_c[m], radius)
                                          + oc.returned_from_aloft(mesh, flows[m], sea_level_c[m], radius, upper)) for m in range(months)])
            sea_level_c = solve(forcing + carried)
        cooling = -ctx.shared["lapse_rate_k_per_km"] * height / M_PER_KM
        ctx.write("surface_temperature", sea_level_c + ZERO_CELSIUS_IN_K + cooling)
        if ctx.recording:
            def kept(series):                                            # the part of a yearly cycle that the solution holds
                held = np.fft.rfft(series, axis=0)
                held[waves + 1:] = 0.0
                return np.fft.irfft(held, n=months, axis=0)
            # The drivers are those of the equation as it was solved: with the sunlight's yearly mean and its first waves.
            # What is then left over is exactly the heat going into and out of storage, -(C / B) dT/dt.
            balance = ZERO_CELSIUS_IN_K + (kept(absorbed) - a) / b
            moved = np.stack([spread * (lap @ sea_level_c[m]) / area / b for m in range(months)])
            extra = kept(np.broadcast_to(other, absorbed.shape)) / b
            by_wind = kept(carried) / b
            ctx.driver("surface_temperature", "sunlight_against_heat_loss", balance)
            ctx.driver("surface_temperature", "spread_from_neighbours", moved)
            ctx.driver("surface_temperature", "other_heat", extra)
            ctx.driver("surface_temperature", "carried_by_wind", by_wind)
            ctx.driver("surface_temperature", "seasonal_storage", sea_level_c + ZERO_CELSIUS_IN_K - balance - moved - extra - by_wind)
            ctx.driver("surface_temperature", "cooling_from_height", np.broadcast_to(cooling, sea_level_c.shape))
