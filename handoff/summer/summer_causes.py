"""What holds down the summers of the twin's northern land, after build steps 4 to 11? A diagnosis on the preview
Earth twin, not a setting of the engine: the twin is built with one change at a time, and the land between 40 and 60
degrees north is read off beside Earth's (CRU), with the terms of EnergyBalance's own account of July.

    PYTHONPATH=src python handoff/summer/summer_causes.py [run names...]
"""
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

import earth_reference as ref
from worldengine.engine import Engine
from worldengine.mesh import get_mesh

DATA = Path(__file__).resolve().parents[2] / "data"
BASE = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
READ = lambda name: yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


def twin(change):
    models = ref.earth_twin_models(copy.deepcopy(BASE), get_mesh(5))
    change(models["slots"])
    e = Engine(DATA, profile="preview", overrides={"models": models, "explanations": ref.earth_twin_explanations(READ("explanations.yaml")),
                                                   "stages": ref.earth_twin_stages(READ("stages.yaml"))})
    return e, e.build()


def numbers(e, w):
    m, f = w.mesh, w.fields
    area, wet = f["cell_area"].astype(np.float64), f["ocean_mask"]
    land = ~wet
    t = f["surface_temperature"].astype(np.float64) - 273.15
    te = ref.at_cell_centres(m, *ref.temperature_monthly())
    north = land & (m.lat > 40) & (m.lat < 60)
    nsea = wet & (m.lat > 40) & (m.lat < 60)
    mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
    mine = np.array([mean(t[k], north) for k in range(12)])
    earths = np.array([mean(te[k], north) for k in range(12)])
    cover = f["snow_ice_cover"].astype(np.float64)
    alb = f["albedo"].astype(np.float64)
    ins = f["insolation"].astype(np.float64)
    out = {"cold": mine.min(), "warm": mine.max(), "year": mine.mean(), "jul_minus_jan": mine[6] - mine[0],
           "earth": [earths.min(), earths.max(), earths.mean(), earths[6] - earths[0]],
           "sea_jul": mean(t[6], nsea), "sea_jan": mean(t[0], nsea), "earth_sea_jul": mean(te[6], nsea), "earth_sea_jan": mean(te[0], nsea),
           "white_all_year": float(area[north & (cover.min(axis=0) > 0.5)].sum() / area[north].sum()),
           "white_july": mean(cover[6], north), "albedo_july": mean(alb[6], north), "albedo_jan": mean(alb[0], north),
           "sun_july": mean(ins[6], north), "absorbed_july": mean(ins[6] * (1 - alb[6]), north),
           "globe": mean(t.mean(axis=0), np.ones(m.n, bool)), "earth_globe": mean(te.mean(axis=0), np.ones(m.n, bool)),
           "rounds": int(w.rounds_used["climate"]), "settled": bool(w.settled["climate"])}
    d = w.drivers.get("surface_temperature", {})
    for name, v in d.items():
        v = np.asarray(v, dtype=np.float64)
        if v.ndim == 2 and v.shape[0] == 12:
            out["july_" + name] = mean(v[6], north) - (273.15 if name == "sunlight_against_heat_loss" else 0.0)
            out["jan_" + name] = mean(v[0], north) - (273.15 if name == "sunlight_against_heat_loss" else 0.0)
    a = w.drivers.get("albedo", {})
    for name, v in a.items():
        v = np.asarray(v, dtype=np.float64)
        if v.ndim == 2:
            out["albedo_july_" + name] = mean(v[6], north)
    return {k: (round(v, 3) if isinstance(v, float) else [round(x, 2) for x in v] if isinstance(v, list) else v) for k, v in out.items()}


def const(slot, key, value):
    def change(slots):
        target = slots[slot]["constants"]
        *path, last = key.split(".")
        for p in path:
            target = target[p]
        target[last] = value
    return change


def both(*changes):
    def change(slots):
        for c in changes:
            c(slots)
    return change


RUNS = {
    "as_built": lambda slots: None,
    "no_snow_on_land": const("Cryosphere", "full_cover_mm", 1.0e9),
    "no_low_sun_term": const("Albedo", "low_sun_term", 0.0),
    "wind_column_half": const("EnergyBalance", "air_column_kg_m2", 1000.0),
    "no_wind_heat": const("EnergyBalance", "air_column_kg_m2", 0.0),
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(RUNS)
    for name in names:
        t0 = time.time()
        e, w = twin(RUNS[name])
        row = numbers(e, w)
        row["seconds"] = round(time.time() - t0, 1)
        print(name, json.dumps(row), flush=True)
