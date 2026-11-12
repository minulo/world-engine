"""Mana, the fantasy layer "magic": mana made by the planet's own causes, spread like heat, lost as it decays.

Model (Invented; data/fantasy/magic.yaml). Every rule here is made up [INVENTED]: a rule of the fantasy layer, not a
claim about any real world. It is written with the engine's own machinery so that it stays consistent: one density
per cell, a steady state of sources, spreading and losses, solved as one sparse linear system as EnergyBalance solves
for heat. With M the mana density (thaum/km²), per cell

    (lambda + k_ice * ice + k_life * plants + k_sea * sea) M - div(K grad M) + carried off by its river - carried in by
        the rivers that run to it = s_motion + s_fire + s_old + s_life + s_storm

  lambda = ln 2 / half-life       mana decays into heat ("spent mana")
  k_ice * ice                     ice locks mana into frozen mana F, which decays with a longer half-life:
                                  F = k_ice * ice * M / lambda_frozen
  k_life * plants                 living things take up a share of the mana around them
  k_sea * sea                     salt water grounds mana: the sea takes a share of its mana each year, spent as heat
  K                               the conductivity: plain land; a small share of it under salt water; raised near plate
                                  boundaries on land (the plate lines; under salt water there are none)
  carried                         running water carries mana: a great river sweeps a strip along its reach and hands
                                  the mana to the cell its water runs to, at a rate that rises with what it carries above
                                  the layer's least discharge for a ley line (the river lines). The mana runs downstream
                                  with the water and gathers toward the mouth, where the sea grounds it
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

The mana of each kind of source is a field of its own, its aspect [INVENTED: deep for the plates' mana, ember for
fire's, elder for old ground's, verdant for life's, tempest for the storms']; Aura names the aspect that leads in each
place. The flow along the ley lines is what the plate lines' own share of the conductance spreads and what the rivers
carry: what plain ground would spread anyway is left out, so that the lines show as lines.

Spent mana (mana_spent) is what decays or is grounded each year, (lambda + k_sea * sea) M + lambda_frozen F. Nothing in
the climate reads any field of this process, so it runs once, after the climate has settled, and the climate is the
same, bit for bit, as without the layer (tests/test_magic.py). The layer magic-warming (data/fantasy/) adds a process
that reads the spent mana of the last round and delivers its heat to the surface; with it, this process takes part in
the climate's rounds.

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
from ..library.mana import ASPECTS, KINDS      # the kinds of source, in the order of the table's codes, and their aspects
from ..library.units import M2_PER_KM2, M_PER_KM
from ..process import Process

PLAIN, BOUNDARY, RIVER, BOTH, SEA = 0, 1, 2, 3, 4                       # the classes of the driver ley_flow.ley


class ThaumicSpreading(Process):
    stage = "climate"
    reads = ("cell_area", "ocean_mask", "crust_type", "surface_age", "volcanism", "convergence_rate", "boundary_distance",
             "flow_receiver", "river_discharge", "vegetation_cover", "snow_ice_cover", "storm_track_density",
             "tc_genesis_potential")
    writes = ("mana_density", "mana_source", "frozen_mana", "ley_flow", "mana_spent") + tuple(f"mana_{a}" for a in ASPECTS) \
        + ("table:wellsprings",)
    shared = ("mana_storm_track_reference", "mana_cyclone_reference", "mana_ley")
    model = "invented thaumic theory: mana from plates, fire, old ground, life and storms, spread like heat along ley lines, lost as it decays"
    drivers = {"mana_density": tuple(f"from_{k}" for k in KINDS) + tuple(f"{k}_at" for k in KINDS),
               "mana_source": KINDS,
               "frozen_mana": ("ice", "state"),
               "ley_flow": ("ley", "conducts", "carried_off", "runs_to"),
               "mana_spent": ("decays", "grounded", "from_ice"),
               **{f"mana_{a}": ("peak", "made_at") for a in ASPECTS}}
    additive = ("mana_density", "mana_source", "mana_spent")

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
        # spreading: the surface, and what the plate lines add to it; carrying: the reaches of great rivers
        ley = ctx.shared["mana_ley"]
        plain = c["conductivity_land_km2_per_year"]
        ground = np.where(sea, plain * c["sea_conductivity_share"], plain)
        boundary_gain, river_share = mn.ley_rule(sea, boundary_km, discharge, ley)
        receiver = np.asarray(ctx.read("flow_receiver"), dtype=np.int64)
        plain_conductance = mn.edge_conductance(mesh, ground)
        ley_conductance = mn.edge_conductance(mesh, ground * (1 + boundary_gain)) - plain_conductance
        conductance = plain_conductance + ley_conductance
        carry_rate = ley["river_carry_per_year"] * river_share                              # per year, of the strip's mana
        carried = mn.river_carrying(mesh, receiver, carry_rate, ley["river_strip_km"], area, ctx.planet["radius_m"] / M_PER_KM)
        loss = decay + locking + uptake + grounding
        key = ("mana", mesh.level, loss.tobytes(), area.tobytes(), conductance.tobytes(), carried.tobytes(), receiver.tobytes())
        if key not in ctx.memo:                                  # prepared again only when an input of the matrix changes
            ctx.memo.clear()
            ctx.memo[key] = spla.splu((sp.diags(area * loss) + mn.spreading_matrix(mesh, conductance)
                                       + mn.carrying_matrix(mesh, receiver, carried)).tocsc())
        solver = ctx.memo[key]
        parts = solver.solve(np.ascontiguousarray(np.stack([area * made[k] for k in KINDS], axis=1)))
        density = parts.sum(axis=1)                              # the density is the sum of what each kind makes
        frozen = locking * density / frozen_decay
        spent_parts = {"decays": decay * density, "grounded": grounding * density, "from_ice": frozen_decay * frozen}
        spent = spent_parts["decays"] + spent_parts["grounded"] + spent_parts["from_ice"]   # thaum/km²/yr: decayed, or grounded at sea
        by_river = carried * density                             # thaum/yr that the cell's river hands downstream
        on_plate_line = boundary_gain > 0                        # counted in the cells of the line, not in those beside it
        along_plate_line = np.where(on_plate_line, mn.through_cell(mesh, mn.edge_flows(mesh, density, ley_conductance)), 0.0)
        flow = (along_plate_line + by_river) / np.sqrt(area)     # thaum/km/yr
        ctx.write("mana_density", density)
        ctx.write("mana_source", source)
        ctx.write("frozen_mana", frozen)
        ctx.write("ley_flow", flow)
        ctx.write("mana_spent", spent)
        for a, part in zip(ASPECTS, parts.T):
            ctx.write(f"mana_{a}", part)
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
            for k, a, part in zip(KINDS, ASPECTS, parts.T):
                peak = mn.uphill_peak(mesh, part).astype(np.int32)
                ctx.driver("mana_density", f"from_{k}", part)
                ctx.driver("mana_density", f"{k}_at", peak)
                ctx.driver(f"mana_{a}", "peak", part[peak])
                ctx.driver(f"mana_{a}", "made_at", peak)
                ctx.driver("mana_source", k, made[k])
            ctx.driver("frozen_mana", "ice", ice)
            ctx.driver("frozen_mana", "state", (ice > 0).astype(np.int32))           # no_ice, ice: whether ice lies in any month
            boundary, river = boundary_gain >= 1, river_share > 0     # a plate line at least doubles the ground's; a great river
            ley_class = np.where(sea, SEA, np.where(boundary & river, BOTH, np.where(river, RIVER, np.where(boundary, BOUNDARY, PLAIN))))
            ctx.driver("ley_flow", "ley", ley_class.astype(np.int32))
            ctx.driver("ley_flow", "conducts", ground * (1 + boundary_gain) / plain)          # against plain land
            ctx.driver("ley_flow", "carried_off", carried / area)                            # the share of its mana a year
            ctx.driver("ley_flow", "runs_to", np.where(carried > 0, receiver, -1).astype(np.int32))
            for name, part in spent_parts.items():
                ctx.driver("mana_spent", name, part)
