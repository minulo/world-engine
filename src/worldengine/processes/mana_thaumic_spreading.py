"""Mana, the fantasy layer "magic": mana made by the planet's own causes, spread like heat, lost as it decays.

Model (Invented; data/fantasy/magic.yaml). Every rule here is made up [INVENTED]: a rule of the fantasy layer, not a
claim about any real world. It is written with the engine's own machinery so that it stays consistent: one density
per cell, a steady state of sources, spreading and losses, solved as one sparse linear system as EnergyBalance solves
for heat. With M the mana density (thaum/km²), per cell

    (lambda + k_ice * ice + k_life * plants + k_sea * sea) M - div(K grad M) = s_motion + s_fire + s_old + s_life + s_storm

  lambda = ln 2 / half-life       mana decays into heat ("spent mana")
  k_ice * ice                     ice locks mana into frozen mana F, which decays with a longer half-life:
                                  F = k_ice * ice * M / lambda_frozen
  k_life * plants                 living things take up a share of the mana around them
  k_sea * sea                     salt water grounds mana: the sea takes a share of its mana each year, spent as heat
  K                               the conductivity: plain land; a small share of it under salt water; raised near plate
                                  boundaries on land (ley lines; under salt water there are none); and running water adds
                                  a conductance along each river reach ("running water carries mana")
  s_motion                        plates closing or parting, near their boundary, in proportion to the speed
  s_fire                          volcanism
  s_old                           a slow seep from old continental ground, growing with the age of the surface
  s_life                          living land breathes mana out in proportion to its cover of plants
  s_storm                         storms spark it: the storm tracks, and the seas where tropical cyclones form

The density is the yearly steady state. Mana's half-life is many years, so the seasons of its sources move the density
by a small share of its yearly mean, and the yearly means of the monthly inputs are used [INFERRED from the equation,
for a cell without spreading: a source that swings with the year by its own mean swings M by k / sqrt(k^2 + (2 pi per
year)^2) of M's mean, with k the cell's loss rate: 0.9 % on bare land at the layer's half-life, at most 6 % at sea].
Spreading neither makes nor destroys mana, so at the steady state the mana made equals the mana decayed, grounded at
sea, locked by ice (which then decays as frozen mana) and taken up by life. Because the equation is linear, the density
is the sum of the densities each kind of source makes alone: those are its drivers.

Spent mana warms the world: what decays or is grounded ((lambda + k_sea * sea) M + lambda_frozen F) delivers heat to the
surface through the group surface_heat_flux, at a constant of the layer that is 0 unless changed. With the constant at
0 the member is exactly zero, nothing in the climate reads the layer's fields, and the layer writes no class that the
climate's settle test watches, so the climate is the same, bit for bit, as without the layer (tests/test_magic.py).

Ignores: everything: the layer is invented, and claims nothing about real rock, life, water or weather. Within its own
rules it ignores any wind-borne drift of mana (mana belongs to the ground and the water on it), the seasons, and any
limit to how much mana a place can hold.
Wrong where: everywhere, as a claim about any real world: it is not one. Within its rules the spreading is as coarse as
the mesh: a ley line is one cell wide, and on the preview mesh the spreading length of plain land is under two cells.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ..library import mana as mn
from ..library.units import M2_PER_KM2, M_PER_KM
from ..process import Process

KINDS = ("plate_motion", "fire", "old_ground", "life", "storms")         # the kinds of source, in the order of the table's codes
PLAIN, BOUNDARY, RIVER, BOTH, SEA = 0, 1, 2, 3, 4                       # the classes of the driver ley_flow.ley


class ThaumicSpreading(Process):
    stage = "climate"
    reads = ("cell_area", "ocean_mask", "crust_type", "surface_age", "volcanism", "convergence_rate", "boundary_distance",
             "flow_receiver", "river_discharge", "vegetation_cover", "snow_ice_cover", "storm_track_density",
             "tc_genesis_potential")
    writes = ("mana_density", "mana_source", "frozen_mana", "ley_flow", "table:wellsprings")
    adds_to = {"surface_heat_flux": "spent_mana_heat"}
    shared = ("mana_storm_track_reference", "mana_cyclone_reference")
    model = "invented thaumic theory: mana from plates, fire, old ground, life and storms, spread like heat along ley lines, lost as it decays"
    drivers = {"mana_density": tuple(f"from_{k}" for k in KINDS) + tuple(f"{k}_at" for k in KINDS),
               "mana_source": KINDS,
               "frozen_mana": ("ice", "state"),
               "ley_flow": ("ley", "conducts"),
               "spent_mana_heat": ("spent", "feedback")}
    additive = ("mana_density", "mana_source")

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        n = mesh.n
        year = lambda name: ctx.read(name).astype(np.float64).mean(axis=0)      # the yearly mean of a monthly field
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        continental = np.asarray(ctx.read("crust_type")) == list(ctx.categories("crust_type")).index("continental")
        area = ctx.read("cell_area").astype(np.float64) / M2_PER_KM2                      # km²
        boundary_km = ctx.read("boundary_distance").astype(np.float64) / M_PER_KM
        closing = np.abs(ctx.read("convergence_rate").astype(np.float64))               # m/yr, closing or parting
        plants, ice = year("vegetation_cover"), np.clip(year("snow_ice_cover"), 0.0, 1.0)
        discharge = np.maximum(year("river_discharge"), 0.0)
        storminess = (year("storm_track_density") / ctx.shared["mana_storm_track_reference"]
                      + year("tc_genesis_potential") / ctx.shared["mana_cyclone_reference"])
        s = c["sources"]
        near = lambda width_km: np.exp(-boundary_km / width_km)
        made = {"plate_motion": s["plate_motion_thaum_km2_yr"] * closing / s["plate_motion_reference_m_per_year"]
                * near(s["plate_motion_width_km"]),
                "fire": s["fire_thaum_km2_yr"] * ctx.read("volcanism").astype(np.float64),
                "old_ground": np.where(continental, s["old_ground_thaum_km2_yr"]
                                       * (1 - np.exp(-ctx.read("surface_age").astype(np.float64) / s["old_ground_age_my"])), 0.0),
                "life": np.where(sea, 0.0, s["life_thaum_km2_yr"] * plants),
                "storms": s["storm_thaum_km2_yr"] * storminess}
        source = np.zeros(n)
        for k in KINDS:                                                                  # thaum/km²/yr
            source = source + made[k]
        # losses, per year
        decay = np.log(2) / c["half_life_years"]
        frozen_decay = np.log(2) / c["frozen_half_life_years"]
        locking = c["losses"]["ice_locking_per_year"] * ice
        uptake = np.where(sea, 0.0, c["losses"]["life_uptake_per_year"] * plants)
        grounding = np.where(sea, c["losses"]["sea_grounding_per_year"], 0.0)       # salt water grounds mana
        # conductivity: the surface, the ley lines of plate boundaries, and the river reaches
        ley = c["ley"]
        plain = c["conductivity_land_km2_per_year"]
        boundary_factor = 1 + ley["boundary_gain"] * near(ley["boundary_width_km"])
        conductivity = np.where(sea, plain * c["sea_conductivity_share"], plain * boundary_factor)    # no ley line under salt water
        carried = np.where(sea, 0.0, plain * ley["river_gain"] * discharge / (discharge + ley["river_half_discharge_m3_s"]))
        receiver = np.asarray(ctx.read("flow_receiver"), dtype=np.int64)
        conductance = mn.edge_conductance(mesh, conductivity) + mn.reach_conductance(mesh, receiver, carried)
        loss = decay + locking + uptake + grounding
        key = ("mana", mesh.level, loss.tobytes(), area.tobytes(), conductance.tobytes())
        if key not in ctx.memo:                                  # prepared again only when an input of the matrix changes
            ctx.memo.clear()
            ctx.memo[key] = spla.splu((sp.diags(area * loss) + mn.spreading_matrix(mesh, conductance)).tocsc())
        solver = ctx.memo[key]
        parts = solver.solve(np.ascontiguousarray(np.stack([area * made[k] for k in KINDS], axis=1)))
        density = parts.sum(axis=1)                              # the density is the sum of what each kind makes
        frozen = locking * density / frozen_decay
        spent = (decay + grounding) * density + frozen_decay * frozen     # thaum/km²/yr spent as heat: decayed, or grounded at sea
        flow = mn.through_cell(mesh, mn.edge_flows(mesh, density, conductance)) / np.sqrt(area)   # thaum/km/yr
        heat = c["spent_mana_heat_w_m2_per_thaum_km2_yr"] * spent
        ctx.write("mana_density", density)
        ctx.write("mana_source", source)
        ctx.write("frozen_mana", frozen)
        ctx.write("ley_flow", flow)
        ctx.add_to_group("surface_heat_flux", np.broadcast_to(heat, (ctx.months, n)))
        # the wellsprings: every cell that holds at least as much as each neighbour and at least the layer's lowest
        # density for a wellspring, strongest first; the cause is the kind of source that made the most of its mana
        well = np.flatnonzero(mn.local_peaks(mesh, density) & (density >= c["wellspring_lowest_thaum_km2"]))
        well = well[np.lexsort((well, -density[well]))]
        cause = np.argmax(parts[well], axis=1) if well.size else np.zeros(0, dtype=np.int64)
        ctx.write_table("table:wellsprings", {
            "cell": well.astype(np.int32), "latitude": mesh.lat[well], "longitude": mesh.lon[well],
            "mana_density": density[well], "cause": cause.astype(np.int16),
            "cause_share": parts[well, cause] / density[well] if well.size else np.zeros(0)})
        if ctx.recording:
            for k, part in zip(KINDS, parts.T):
                ctx.driver("mana_density", f"from_{k}", part)
                ctx.driver("mana_density", f"{k}_at", mn.uphill_peak(mesh, part).astype(np.int32))
                ctx.driver("mana_source", k, made[k])
            ctx.driver("frozen_mana", "ice", ice)
            ctx.driver("frozen_mana", "state", (ice > 0).astype(np.int32))           # no_ice, ice: whether ice lies in any month
            boundary, river = boundary_factor >= 2, carried >= conductivity              # a ley line at least doubles the ground's
            ley_class = np.where(sea, SEA, np.where(boundary & river, BOTH, np.where(river, RIVER, np.where(boundary, BOUNDARY, PLAIN))))
            ctx.driver("ley_flow", "ley", ley_class.astype(np.int32))
            ctx.driver("ley_flow", "conducts", (conductivity + carried) / plain)   # against plain land
            ctx.driver("spent_mana_heat", "spent", spent)
            ctx.driver("spent_mana_heat", "feedback", np.full(n, int(c["spent_mana_heat_w_m2_per_thaum_km2_yr"] > 0), dtype=np.int32))
