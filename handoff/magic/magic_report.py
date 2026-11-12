"""The numbers that docs/BUILD_NOTES.md, section 31, gives for a world with the invented layer magic.

    PYTHONPATH=src python handoff/magic/magic_report.py MAGIC_STORE [PLAIN_STORE]

MAGIC_STORE is a world built with --fantasy magic (or magic-warming); PLAIN_STORE, if given, is the same world built
without a layer, and the two are compared (every field the plain world holds, and the temperature)."""
import sys

import numpy as np

from worldengine import store

ASPECTS = ("deep", "ember", "elder", "verdant", "tempest")
v = store.StoreView(sys.argv[1])
meta = v.attrs["meta"]
area = np.asarray(v.field("cell_area")).astype(np.float64) / 1.0e6                      # km²
sea = np.asarray(v.field("ocean_mask")).astype(bool)
land = ~sea
f = lambda name: np.asarray(v.field(name)).astype(np.float64)
total = lambda x, where=slice(None): float((x * area)[where].sum())
share = lambda where, of: float(area[where & of].sum() / area[of].sum())
print(f"world: {meta['cells']} cells, layers {meta.get('fantasy')}, built in {meta['build_seconds']:.1f} s, "
      f"climate rounds {meta['rounds_used']['climate']}, fingerprint {v.attrs['world_fingerprint'][:16]}")
m, src, spent, frozen = f("mana_density"), f("mana_source"), f("mana_spent"), f("frozen_mana")
made = total(src)
print(f"mana: {total(m):.3e} thaum free ({total(m, land):.3e} on land), {total(frozen):.3e} frozen; {made:.3e} thaum made a year; "
      f"spent {total(spent) / made:.3f} of it, of which at sea {total(spent, sea) / made:.3f}; the rest life takes up")
for k in ("decays", "grounded", "from_ice"):
    print(f"  spent, {k}: {total(np.asarray(v.driver('mana_spent', k)).astype(np.float64)) / made:.3f} of what is made")
for k in ("plate_motion", "fire", "old_ground", "life", "storms"):
    print(f"  made by {k}: {total(np.asarray(v.driver('mana_source', k)).astype(np.float64)) / made:.3f}")
print("density, thaum/km²: land mean %.1f, sea mean %.1f, highest %.1f" % (total(m, land) / area[land].sum(), total(m, sea) / area[sea].sum(), m.max()))
for name in ("aura", "mana_aspect", "ley_line"):
    classes = v.specs[name]["categories"]
    values = np.asarray(v.field(name))
    print(f"{name}, share of the land (of the sea): " + "; ".join(
        f"{c} {share(values == k, land):.3f} ({share(values == k, sea):.3f})" for k, c in enumerate(classes)))
line = np.asarray(v.field("ley_line"))
flow = f("ley_flow")
print(f"ley lines: {int((line == 1).sum())} cells on plate lines, {int((line == 2).sum())} on river lines, {int((line == 3).sum())} at a nexus; "
      f"flow on the lines: median {np.median(flow[line > 0]):.0f}, highest {flow.max():.0f} thaum/km/yr; cells off the lines with a flow: {int((flow[line == 0] != 0).sum())}")
for a in ASPECTS:
    print(f"  {a}: {total(f('mana_' + a)) / total(m):.3f} of the free mana, {total(f('mana_' + a), land) / total(m, land):.3f} of the land's")
w = v.table("wellsprings")
print(f"wellsprings: {len(w['cell'])}; on land {int(land[np.asarray(w['cell'])].sum())}; by cause (plates, fire, old ground, life, storms) "
      f"{np.bincount(np.asarray(w['cause']), minlength=5).tolist()}")
for row in range(min(3, len(w["cell"]))):
    print(f"  {row + 1}. {w['latitude'][row]:.1f} N, {w['longitude'][row]:.1f} E: {w['mana_density'][row]:.1f} thaum/km², "
          f"{ASPECTS[int(w['cause'][row])]} ({w['cause_share'][row]:.2f})")
wild = f("wild_magic")
print(f"wild magic at least 0.5: {share(wild >= 0.5, land):.3f} of the land, {share(wild >= 0.5, sea):.3f} of the sea")
if "spent_mana_heat" in v.field_names():
    heat = f("spent_mana_heat").mean(axis=0)
    print(f"spent mana's heat: mean {total(heat) / area.sum():.2f} W/m², highest {heat.max():.1f}")
if len(sys.argv) > 2:
    p = store.StoreView(sys.argv[2])
    mine, theirs = v.attrs["fingerprints"], p.attrs["fingerprints"]
    same = sum(mine.get(k) == theirs[k] for k in theirs)
    print(f"against the plain world: {same} of {len(theirs)} fields and columns bit for bit the same; "
          f"climate rounds {p.attrs['meta']['rounds_used']['climate']} there")
    t, t0 = f("surface_temperature").mean(axis=0), np.asarray(p.field("surface_temperature")).astype(np.float64).mean(axis=0)
    whole = area.sum()
    print(f"  temperature: planet {((t - t0) * area).sum() / whole:+.2f} K against it (land {((t - t0) * area)[land].sum() / area[land].sum():+.2f}, "
          f"sea {((t - t0) * area)[sea].sum() / area[sea].sum():+.2f}); mean {(t * area).sum() / whole - 273.15:.2f} C")
    if "spent_mana_heat" in v.field_names():
        most, least = heat >= np.percentile(heat, 90), heat <= np.percentile(heat, 50)
        print(f"  the tenth of cells with the most heat warms {(t - t0)[most].mean():+.2f} K, the half with the least {(t - t0)[least].mean():+.2f} K")
