"""Lithology: the family of rock at the surface, from the tectonic setting.

Model (Rule). A table in models.yaml maps a setting to a rock family and an erodibility. Its rows are tried in
order and the first that matches wins: ocean crust is ocean-floor basalt; strong volcanism makes a volcanic arc;
recent mountain building a young fold belt; a spreading boundary in continental crust a rift basin; older mountain
building the crystalline roots of old mountains; everything else a stable platform.
Ignores: rock carried from elsewhere, weathering, layering, sediment laid down by rivers.
Wrong where: a setting holds many rocks; the erodibilities are relative numbers, not measured.
"""
import numpy as np

from ..process import Process

OCEANIC = 0


class RuleTableLithology(Process):
    stage = "geological"
    reads = ("crust_type", "orogeny_age", "volcanism", "boundary_kind")
    writes = ("rock_type", "erodibility")
    model = "a rule table from tectonic setting to rock family"
    drivers = {"rock_type": ("rule",), "erodibility": ("rock",)}

    def run(self, ctx):
        crust = ctx.read("crust_type")
        orogeny = ctx.read("orogeny_age").astype(np.float64)
        volcanism = ctx.read("volcanism").astype(np.float64)
        boundary = ctx.read("boundary_kind")
        rocks, kinds = ctx.categories("rock_type"), ctx.categories("boundary_kind")
        crusts = ctx.categories("crust_type")
        n = crust.size
        rock = np.full(n, -1, dtype=np.int64)
        erod = np.zeros(n)
        rule_of = np.full(n, -1, dtype=np.int32)
        for i, r in enumerate(ctx.const["rules"]):
            match = rock < 0
            if "crust" in r:
                match &= crust == crusts.index(r["crust"])
            if "volcanism_above" in r:
                match &= volcanism > r["volcanism_above"]
            if "orogeny_younger_than_my" in r:
                match &= ~np.isnan(orogeny) & (orogeny < r["orogeny_younger_than_my"])
            if "boundary" in r:
                match &= np.isin(boundary, [kinds.index(b) for b in r["boundary"]])
            rock[match] = rocks.index(r["rock"])
            erod[match] = r["erodibility"]
            rule_of[match] = i
        ctx.write("rock_type", rock.astype(np.int16))
        ctx.write("erodibility", erod)
        ctx.driver("rock_type", "rule", rule_of)
        ctx.driver("erodibility", "rock", rock.astype(np.int32))
