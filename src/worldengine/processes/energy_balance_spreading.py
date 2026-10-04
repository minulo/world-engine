"""EnergyBalance, first version: spreading of heat only, on the two-dimensional mesh.

Model (Adapted): the energy balance model of North, Cahalan and Coakley 1981 with its constants.
Temperature settles where absorbed sunlight equals heat lost to space plus heat spread sideways:

    C dT/dt = Q (1 - albedo) - (A + B T) + D * Laplacian(T) + other heat

Heat lost to space is a straight-line function of temperature, A + B T. Land and sea differ in
how slowly they warm and cool (C). The repeating year is solved directly: the monthly forcing
is split into its yearly mean and a few waves in time, and each is one linear system on the
mesh, prepared once for a climate run with a direct solver. My additions: height cools the
surface at a fixed rate per kilometre, and the heat group enters as a known amount.

Ignores: the layers of the air, heat carried as water vapour, heat carried by wind and ocean
(their effect is folded into D, which was fitted to the observed fall of temperature from
equator to pole), sea ice as a lid on the sea, and the make-up of the air: A and B are fitted
to Earth's air and clouds.
Wrong where: it spreads heat over about 3,500 km, so anything narrower is smoothed away.
Coasts facing the wind are not milder than coasts facing away. High plateaus are too cold.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..library import operators as op
from ..library.units import M_PER_KM, TWO_PI, ZERO_CELSIUS_IN_K
from ..process import Process


class SpreadingEnergyBalance(Process):
    stage = "climate"
    reads = ("insolation", "albedo", "ocean_mask", "height_above_sea", "cell_area")
    reads_groups_lagged = ("surface_heat_flux",)
    writes = ("surface_temperature",)
    shared = ("lapse_rate_k_per_km",)
    model = "energy balance model of North, Cahalan and Coakley 1981, heat spreading only"
    drivers = {"surface_temperature": ("sunlight_against_heat_loss", "spread_from_neighbours", "seasonal_storage",
                                       "other_heat", "cooling_from_height")}
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
        capacity = np.where(sea, c["heat_capacity_sea_j_m2_k"], c["heat_capacity_land_j_m2_k"])
        waves = min(int(c["time_waves"]), months // 2)
        key = ("energy balance", mesh.level, waves, b, spread, c["heat_capacity_sea_j_m2_k"], c["heat_capacity_land_j_m2_k"],
               ctx.planet["year_length_s"], sea.tobytes())
        if key not in ctx.memo:                                          # prepared once for each climate run
            lap = op.laplacian_matrix(mesh)
            year_rate = TWO_PI / ctx.planet["year_length_s"]
            solvers = []
            for k in range(waves + 1):
                diag = area * (b + 1j * k * year_rate * capacity) if k else area * b
                solvers.append(spla.splu((sp.diags(diag) - spread * lap).tocsc()))
            ctx.memo[key] = (lap, solvers)
        lap, solvers = ctx.memo[key]
        forcing = absorbed - a + other                                   # W/m2, month by cell
        spectrum = np.fft.rfft(forcing, axis=0) / months
        answer = np.zeros_like(spectrum)
        for k in range(waves + 1):
            rhs = area * spectrum[k]
            answer[k] = solvers[k].solve(rhs.real) if k == 0 else solvers[k].solve(rhs)
        sea_level_c = np.fft.irfft(answer * months, n=months, axis=0)    # degrees C at sea level
        cooling = -ctx.shared["lapse_rate_k_per_km"] * height / M_PER_KM
        ctx.write("surface_temperature", sea_level_c + ZERO_CELSIUS_IN_K + cooling)
        if ctx.recording:
            balance = ZERO_CELSIUS_IN_K + (absorbed - a) / b
            moved = np.stack([spread * (lap @ sea_level_c[m]) / area / b for m in range(months)])
            extra = other / b
            ctx.driver("surface_temperature", "sunlight_against_heat_loss", balance)
            ctx.driver("surface_temperature", "spread_from_neighbours", moved)
            ctx.driver("surface_temperature", "other_heat", extra)
            ctx.driver("surface_temperature", "seasonal_storage", sea_level_c + ZERO_CELSIUS_IN_K - balance - moved - extra)
            ctx.driver("surface_temperature", "cooling_from_height", np.broadcast_to(cooling, sea_level_c.shape))
