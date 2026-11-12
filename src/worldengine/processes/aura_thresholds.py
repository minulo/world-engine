"""Aura, the fantasy layer "magic": wild magic where mana falls steeply under storms, and the classes of each place: its
aura, the aspect of its mana, and the ley line it lies on.

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

The aspect of a place's mana: the aspect (deep, ember, elder, verdant, tempest: the mana of the plates, of fire, of old
ground, of life and of storms, each a field of Mana) that holds the most of it, however little there is; none only
where no mana stands at all.

The ley line of a place: a plate line where the plate boundary's gain to the ground's conductivity is at least 1, a
river line where a great river runs (one that carries more than the layer's least discharge for a ley line), a nexus
where both are; none elsewhere and under salt water (the same rule, with the same shared constants, as Mana's
spreading and carrying: library/mana.py, ley_rule).

The classes are written here and not by Mana because nothing reads them: this process always runs once, after the
climate has settled, so a class that changes on a few cells from round to round cannot keep the climate from settling.

Ignores: everything: the layer is invented. Within its own rules it ignores how wild magic would change the mana it
comes from (it is a reading of the density, not a part of its budget), and the seasons.
Wrong where: everywhere, as a claim about any real world: it is not one. Within its rules the fall of the density is
taken across one cell, so it is as coarse as the mesh.
"""
import numpy as np

from ..library import mana as mn
from ..library.mana import ASPECTS
from ..library.units import M_PER_KM
from ..process import Process

DEAD_ZONE, FAINT, STEADY, STRONG, WELLSPRING, WILD = "dead_zone", "faint", "steady", "strong", "wellspring", "wild"
NO_LINE, PLATE_LINE, RIVER_LINE, NEXUS = "none", "plate_line", "river_line", "nexus"
NO_ASPECT = "none"


class ThresholdAura(Process):
    stage = "climate"
    reads = ("mana_density", "storm_track_density", "tc_genesis_potential", "table:wellsprings", "ocean_mask",
             "boundary_distance", "river_discharge") + tuple(f"mana_{a}" for a in ASPECTS)
    writes = ("wild_magic", "aura", "mana_aspect", "ley_line")
    shared = ("mana_storm_track_reference", "mana_cyclone_reference", "mana_ley", "mana_fall_reference_thaum_km2_per_km")
    model = ("invented aura rules: wild magic where steep falls of mana meet storms; the aura by density, wellsprings from Mana's "
             "table; the aspect that holds the most of the mana; the ley line by what it adds to the ground's conductivity")
    drivers = {"wild_magic": ("fall", "storminess"), "aura": ("rule", "density", "wildness"),
               "mana_aspect": ("rule", "share", "density"), "ley_line": ("rule", "boundary_gain", "discharge")}

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        radius_km = ctx.planet["radius_m"] / M_PER_KM
        year = lambda name: ctx.read(name).astype(np.float64).mean(axis=0)
        density = ctx.read("mana_density").astype(np.float64)
        fall = mn.fall(mesh, density, radius_km)                                             # thaum/km² per km
        storminess = (year("storm_track_density") / ctx.shared["mana_storm_track_reference"]
                      + year("tc_genesis_potential") / ctx.shared["mana_cyclone_reference"])
        w = c["wild"]
        wild = mn.surge(fall, storminess, ctx.shared["mana_fall_reference_thaum_km2_per_km"], w["storminess_reference"])
        names = list(ctx.categories("aura"))
        k = c["classes"]
        aura = np.full(mesh.n, names.index(DEAD_ZONE), dtype=np.int16)
        for name, lowest in ((FAINT, k["faint_from_thaum_km2"]), (STEADY, k["steady_from_thaum_km2"]),
                             (STRONG, k["strong_from_thaum_km2"])):
            aura[density >= lowest] = names.index(name)
        aura[np.asarray(ctx.read("table:wellsprings")["cell"], dtype=np.int64)] = names.index(WELLSPRING)
        aura[wild >= w["wild_from"]] = names.index(WILD)
        # the aspect: the kind of mana that the place holds the most of; none only where no mana stands
        parts = np.stack([ctx.read(f"mana_{a}").astype(np.float64) for a in ASPECTS], axis=1)
        leading = np.argmax(parts, axis=1)                    # of two equal parts the first in the layer's order
        aspects = list(ctx.categories("mana_aspect"))
        empty = density <= 0
        aspect = np.where(empty, aspects.index(NO_ASPECT), np.array([aspects.index(a) for a in ASPECTS])[leading]).astype(np.int16)
        share = np.where(density > 0, parts[np.arange(mesh.n), leading] / np.where(density > 0, density, 1), 0.0)
        # the ley line: the rule of Mana's conductance, read as a class
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        discharge = np.maximum(year("river_discharge"), 0.0)
        boundary_gain, river_share = mn.ley_rule(sea, ctx.read("boundary_distance").astype(np.float64) / M_PER_KM, discharge,
                                                 ctx.shared["mana_ley"])
        on_boundary, on_river = boundary_gain >= 1, river_share > 0
        lines = list(ctx.categories("ley_line"))
        line = np.where(on_boundary & on_river, lines.index(NEXUS), np.where(on_river, lines.index(RIVER_LINE),
                        np.where(on_boundary, lines.index(PLATE_LINE), lines.index(NO_LINE)))).astype(np.int16)
        ctx.write("wild_magic", wild)
        ctx.write("aura", aura)
        ctx.write("mana_aspect", aspect)
        ctx.write("ley_line", line)
        if ctx.recording:
            ctx.driver("wild_magic", "fall", fall)
            ctx.driver("wild_magic", "storminess", storminess)
            ctx.driver("aura", "rule", aura.astype(np.int32))
            ctx.driver("aura", "density", density)
            ctx.driver("aura", "wildness", wild)
            ctx.driver("mana_aspect", "rule", aspect.astype(np.int32))
            ctx.driver("mana_aspect", "share", share)
            ctx.driver("mana_aspect", "density", density)
            ctx.driver("ley_line", "rule", line.astype(np.int32))
            ctx.driver("ley_line", "boundary_gain", boundary_gain)
            ctx.driver("ley_line", "discharge", discharge)
