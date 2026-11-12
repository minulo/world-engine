"""ManaWarmth, the fantasy layer "magic-warming": spent mana warms the world.

Model (Invented; data/fantasy/magic-warming.yaml, which needs the layer magic). Every rule here is made up [INVENTED]:
a rule of the fantasy layer, not a claim about any real world.

Mana ends as heat: what decays, or is grounded at sea, each year (Mana's field mana_spent, thaum/km²/yr) delivers
heat to the surface in proportion, at the layer's heat of a thaum spent,

    spent_mana_heat = h * mana_spent      (W/m², the same in every month),

a member of the group surface_heat_flux, which EnergyBalance adds to the sunlight it balances. The spent mana is that of
the last round, a known amount, as the ocean's heat is: so the climate and the mana settle together, and Mana, with the
storms and plants it reads, takes part in the climate's rounds. Without this layer nothing reads the mana, Mana runs
once after the climate has settled, and the climate is untouched.

Ignores: everything: the layer is invented. Within its own rules: the season of the mana's decay (the heat is the
year's, spread evenly over the months), and where the heat of mana grounded at sea goes below the surface.
Wrong where: everywhere, as a claim about any real world: it is not one.
"""
import numpy as np

from ..process import Process


class SpentManaWarmth(Process):
    stage = "climate"
    reads_lagged = ("mana_spent",)
    adds_to = {"surface_heat_flux": "spent_mana_heat"}
    model = "invented: the mana spent in the last round warms the surface in proportion"
    drivers = {"spent_mana_heat": ("spent",)}

    def run(self, ctx):
        spent = np.maximum(ctx.read_lagged("mana_spent").astype(np.float64), 0.0)            # thaum/km²/yr
        heat = ctx.const["heat_w_m2_per_thaum_km2_yr"] * spent
        ctx.add_to_group("surface_heat_flux", np.broadcast_to(heat, (ctx.months, ctx.mesh.n)))
        if ctx.recording:
            ctx.driver("spent_mana_heat", "spent", spent)
