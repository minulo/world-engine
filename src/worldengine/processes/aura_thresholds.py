"""Aura, the fantasy layer "magic": wild magic where mana falls steeply under storms, and the aura of each place.

Model (Invented; data/fantasy/magic.yaml). Every rule here is made up [INVENTED]: a rule of the fantasy layer, not a
claim about any real world.

Wild magic: where the density of mana falls steeply and storms pass, mana tears loose. With G the fall of the density
across the cell (the size of its gradient, thaum/km² per km) and W the storminess (the yearly storm tracks and cyclone
potential, each over the layer's reference, as Mana counts them),

    wild_magic = 1 - exp(-(G / G0) * (W / W0)),

0 where either is missing and near 1 where both are large.

The aura of a place, by the first rule that holds: wild where wild_magic reaches the layer's threshold; a wellspring
where the table of wellsprings (Mana) lists the cell; then strong, steady, faint or a dead zone by the density of mana,
against the layer's thresholds.

Ignores: everything: the layer is invented. Within its own rules it ignores how wild magic would change the mana it
comes from (it is a reading of the density, not a part of its budget), and the seasons.
Wrong where: everywhere, as a claim about any real world: it is not one. Within its rules the fall of the density is
taken across one cell, so it is as coarse as the mesh.
"""
import numpy as np

from ..library import operators as op
from ..library.units import M_PER_KM
from ..process import Process

DEAD_ZONE, FAINT, STEADY, STRONG, WELLSPRING, WILD = "dead_zone", "faint", "steady", "strong", "wellspring", "wild"


class ThresholdAura(Process):
    stage = "climate"
    reads = ("mana_density", "storm_track_density", "tc_genesis_potential", "table:wellsprings")
    writes = ("wild_magic", "aura")
    shared = ("mana_storm_track_reference", "mana_cyclone_reference")
    model = "invented aura rules: wild magic where steep falls of mana meet storms; classes by density, wellsprings from Mana's table"
    drivers = {"wild_magic": ("fall", "storminess"), "aura": ("rule", "density", "wildness")}

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        radius_km = ctx.planet["radius_m"] / M_PER_KM
        year = lambda name: ctx.read(name).astype(np.float64).mean(axis=0)
        density = ctx.read("mana_density").astype(np.float64)
        fall = np.linalg.norm(op.gradient(mesh, density), axis=1) / radius_km               # thaum/km² per km
        storminess = (year("storm_track_density") / ctx.shared["mana_storm_track_reference"]
                      + year("tc_genesis_potential") / ctx.shared["mana_cyclone_reference"])
        w = c["wild"]
        wild = 1 - np.exp(-(fall / w["fall_reference_thaum_km2_per_km"]) * (storminess / w["storminess_reference"]))
        names = list(ctx.categories("aura"))
        k = c["classes"]
        aura = np.full(mesh.n, names.index(DEAD_ZONE), dtype=np.int16)
        for name, lowest in ((FAINT, k["faint_from_thaum_km2"]), (STEADY, k["steady_from_thaum_km2"]),
                             (STRONG, k["strong_from_thaum_km2"])):
            aura[density >= lowest] = names.index(name)
        aura[np.asarray(ctx.read("table:wellsprings")["cell"], dtype=np.int64)] = names.index(WELLSPRING)
        aura[wild >= w["wild_from"]] = names.index(WILD)
        ctx.write("wild_magic", wild)
        ctx.write("aura", aura)
        if ctx.recording:
            ctx.driver("wild_magic", "fall", fall)
            ctx.driver("wild_magic", "storminess", storminess)
            ctx.driver("aura", "rule", aura.astype(np.int32))
            ctx.driver("aura", "density", density)
            ctx.driver("aura", "wildness", wild)
