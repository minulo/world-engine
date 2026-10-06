"""What makes the summers of the twin's northern land cold? A diagnosis on the preview Earth twin, not a setting of
the engine: the twin is built again with one or two constants changed, and the seasons of the land between 40 and 60
degrees north are read off beside Earth's.

    PYTHONPATH=src python handoff/pass3/seasons_apart.py

  no snow on the ground   Hydrology's full_cover_mm made so large that no ground ever counts as covered: Albedo then
                          sees no snow on land (sea ice stays). It also lets the demand for water count all ground.
  land warms faster       the heat capacity of land divided (the published value is 0.16 B years)
  less spreading          the spreading constant D lowered (0.649 published)
"""
import copy
import sys
from pathlib import Path

import numpy as np
import yaml

import earth_reference as ref
from worldengine.engine import Engine
from worldengine.mesh import get_mesh

DATA = Path(__file__).resolve().parents[2] / "data"
BASE = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
WORDS = ref.earth_twin_explanations(yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8")))


def twin(change):
    models = ref.earth_twin_models(copy.deepcopy(BASE), get_mesh(5))
    change(models["slots"])
    e = Engine(DATA, profile="preview", overrides={"models": models, "explanations": WORDS})
    return e, e.build()


def numbers(e, w):
    m, f = w.mesh, w.fields
    area, wet = f["cell_area"].astype(np.float64), f["ocean_mask"]
    land = ~wet
    t = f["surface_temperature"].astype(np.float64) - 273.15
    te = ref.at_cell_centres(m, *ref.temperature_monthly())
    north = land & (m.lat > 40) & (m.lat < 60)
    mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
    mine, earths = np.array([mean(t[k], north) for k in range(12)]), np.array([mean(te[k], north) for k in range(12)])
    snow = f["snow_cover"].astype(np.float64)
    names = e.registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[f["climate_class"]]
    share = lambda g: 100.0 * area[land & (group == g)].sum() / area[land].sum()
    everywhere = np.ones(m.n, dtype=bool)
    return {"cold": mine.min(), "warm": mine.max(), "year": mine.mean(), "swing": mean(t[6] - t[0], north),
            "white": 100.0 * area[north & (snow.min(axis=0) > 0.5)].sum() / area[north].sum(), "D": share("D"), "E": share("E"),
            "globe": mean(t.mean(axis=0), everywhere), "sea": mean(t.mean(axis=0), wet), "rounds": w.rounds_used["climate"], "settled": bool(w.settled["climate"]),
            "earth": (earths.min(), earths.max(), earths.mean(), mean(te[6] - te[0], north), mean(te.mean(axis=0), everywhere))}


def eb(key, value):
    def change(slots):
        slots["EnergyBalance"]["constants"][key] = value
    return change


def no_snow(slots):
    slots["Hydrology"]["constants"]["snow"]["full_cover_mm"] = 1.0e9


def both(*changes):
    def change(slots):
        for c in changes:
            c(slots)
    return change


LAND = BASE["slots"]["EnergyBalance"]["constants"]["heat_capacity_land_j_m2_k"]
RUNS = [("as built", lambda slots: None),
        ("no snow on the ground", no_snow),
        ("land warms 2 times faster", eb("heat_capacity_land_j_m2_k", LAND / 2)),
        ("land warms 4 times faster", eb("heat_capacity_land_j_m2_k", LAND / 4)),
        ("less spreading, D = 0.35", eb("spreading_constant_w_m2_k", 0.35)),
        ("no snow, and land 2 times faster", both(no_snow, eb("heat_capacity_land_j_m2_k", LAND / 2))),
        ("no snow, and D = 0.35", both(no_snow, eb("spreading_constant_w_m2_k", 0.35))),
        ("no snow, land 2 times faster, D = 0.35", both(no_snow, eb("heat_capacity_land_j_m2_k", LAND / 2), eb("spreading_constant_w_m2_k", 0.35)))]

if __name__ == "__main__":
    print("land between 40 and 60 degrees north, preview Earth twin; temperatures in C, shares in %")
    print(f"{'':42s} coldest  warmest    year  Jul-Jan  white all year  group D  group E   globe     sea  rounds")
    first = True
    for name, change in RUNS:
        r = numbers(*twin(change))
        if first:
            a = r["earth"]
            print(f"{'Earth (the temperature data)':42s} {a[0]:7.1f}  {a[1]:7.1f} {a[2]:7.1f}  {a[3]:7.1f}  {'':14s}  {24.6:7.1f}  {12.8:7.1f} {a[4]:7.1f}")
            first = False
        print(f"{name:42s} {r['cold']:7.1f}  {r['warm']:7.1f} {r['year']:7.1f}  {r['swing']:7.1f}  {r['white']:14.1f}  {r['D']:7.1f}  {r['E']:7.1f} {r['globe']:7.1f} {r['sea']:7.1f}  {r['rounds']:3d}{'' if r['settled'] else ' NOT SETTLED'}", flush=True)
