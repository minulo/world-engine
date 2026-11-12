"""ManaSurge, the fantasy layer "magic": the wild magic of one day, where the day's storms cross a fall of mana.

Model (Invented; data/fantasy/magic.yaml). Every rule here is made up [INVENTED]: a rule of the fantasy layer, not a
claim about any real world.

Aura's wild_magic is the wild magic of the year: the fall of the mana's density against the storminess of the climate.
This is the same rule on the weather clock, for one day: with G the fall of the density across the cell (thaum/km² per
km, as Aura takes it) and S the storm influence of the day (SynopticStorms: each storm alive on the day, its strength
fading with the distance from its centre),

    mana_surge = 1 - exp(-(G / G0) * (S / S0)),

0 where no storm reaches or the mana lies level, near 1 where a strong storm crosses a steep fall. G0 is Aura's
reference for the fall, shared, so that the day and the year are measured against the same fall. A surge follows the
day's storms across the map; like every field of the weather clock it is worked out on request and never stored, and
the same day gives the same surge however it is reached.

Ignores: everything: the layer is invented. Within its own rules it ignores any effect of a surge on the mana it comes
from (a surge is a reading of the density and the day's storms, not a part of the mana's budget) and on the weather.
Wrong where: everywhere, as a claim about any real world: it is not one. Within its rules the fall is taken across one
cell, as coarse as the mesh.
"""
import numpy as np

from ..library import mana as mn
from ..library.units import M_PER_KM
from ..process import Process


class StormSurge(Process):
    stage = "weather"
    reads = ("mana_density", "storm_influence")
    writes = ("mana_surge",)
    shared = ("mana_fall_reference_thaum_km2_per_km",)
    model = "invented: the day's wild magic, where the day's storms cross a fall of mana"
    drivers = {"mana_surge": ("fall", "storms")}

    def run(self, ctx):
        c = ctx.const
        density = ctx.read("mana_density").astype(np.float64)
        storms = np.maximum(ctx.read("storm_influence").astype(np.float64), 0.0)
        fall = mn.fall(ctx.mesh, density, ctx.planet["radius_m"] / M_PER_KM)                 # thaum/km² per km
        ctx.write("mana_surge", mn.surge(fall, storms, ctx.shared["mana_fall_reference_thaum_km2_per_km"],
                                         c["storm_influence_reference"]))
        if ctx.recording:
            ctx.driver("mana_surge", "fall", fall)
            ctx.driver("mana_surge", "storms", storms)
