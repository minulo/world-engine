"""The engine's planet against a full circulation model (build step 10): aquaplanets at a chosen rotation period.

A planet covered by sea, with Earth's sunlight, tilt and size, is built by the engine (its relief is a flat sea floor read
from a file, as the Earth twin reads Earth's) and compared with an ExoPlaSim aquaplanet run with the same rotation period
[DOCUMENTED: ExoPlaSim, Paradise et al. 2022, a model of the general circulation extended for other rocky planets;
its runs are made by /tmp scripts of the build, whose zonal means this tool reads from a JSON file]. Compared, on the
year's zonal means: where the surface wind turns from easterly to westerly (the edge of the trade winds), where the
westerlies are strongest, the temperature at the equator and the drop to 60 degrees, and the latitude of the rain belt.

    python tools/gcm_compare.py GCM.json [--days 1.0] [--data DIR] [--profile preview]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from earth_reference import WITHOUT_CRUST, earth_twin_explanations, earth_twin_stages  # noqa: E402
from worldengine.engine import Engine  # noqa: E402
from worldengine.mesh import get_mesh  # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR  # noqa: E402

FLOOR_M = -4000.0                 # the flat sea floor: deep enough for the planet's water to cover it everywhere
SIDEREAL_DAY_S = 86164.1          # the default planet's day; a GCM's rotation period in days is scaled by it
FOLDER_VARIABLE = "WORLDENGINE_AQUA_FOLDER"


def aquaplanet_overrides(data_dir, mesh, days):
    read = lambda name: yaml.safe_load((Path(data_dir) / name).read_text(encoding="utf-8"))
    folder = Path(tempfile.mkdtemp(prefix="aqua-"))
    path = folder / f"flat_{mesh.level}.npy"
    np.save(path, np.full(mesh.n, FLOOR_M))
    os.environ[FOLDER_VARIABLE] = str(folder)
    models = read("models.yaml")
    models["slots"] = {k: v for k, v in models["slots"].items() if k not in WITHOUT_CRUST}
    models["slots"]["Isostasy"] = {
        "implementation": "worldengine.processes.relief_from_file:ReliefFromFile", "standing": "Test",
        "model": "a flat sea floor: an aquaplanet", "ignores": "land", "wrong_where": "anywhere a planet has land",
        "writes": ["elevation"],
        "constants": {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "folder_from_env": FOLDER_VARIABLE}}
    if "Soils" in models["slots"]:
        models["slots"]["Lithology"] = {
            "implementation": "worldengine.processes.relief_from_file:GroundWithoutHistory", "standing": "Test",
            "model": "no ground", "ignores": "ground", "wrong_where": "land", "writes": ["rock_type", "surface_age", "erosion_rate"],
            "constants": {"rock": "stable_platform", "surface_age_my": 100.0}}
    planet = read("planet.yaml")
    planet["rotation_period_s"] = float(days) * SIDEREAL_DAY_S
    return {"models": models, "explanations": earth_twin_explanations(read("explanations.yaml")),
            "stages": earth_twin_stages(read("stages.yaml")), "planet": planet}


def crossings(lat, east):
    """The latitudes where the surface wind turns from easterly to westerly, going poleward in each hemisphere, and where
    the westerlies are strongest."""
    out = {}
    for name, sign in (("north", 1), ("south", -1)):
        sel = np.argsort(sign * lat)
        la, u = sign * lat[sel], east[sel]
        keep = la > 0
        la, u = la[keep], u[keep]
        turn = np.flatnonzero((u[:-1] < 0) & (u[1:] >= 0))
        edge = float(la[turn[0]] + (la[turn[0] + 1] - la[turn[0]]) * -u[turn[0]] / (u[turn[0] + 1] - u[turn[0]])) if turn.size else float("nan")
        out[name] = {"trade_wind_edge_deg": edge, "westerly_peak_deg": float(la[int(np.argmax(u))])}
    return out


def summary(lat, t_c, east, rain):
    def at(target, width=5.0):
        sel = np.abs(np.abs(lat) - target) <= width
        return float(t_c[sel].mean())
    north = lat >= 0
    return {"winds": crossings(lat, east), "equator_c": at(0.0), "drop_to_60_k": at(0.0) - at(60.0),
            "rain_belt_deg": float(lat[int(np.argmax(rain))]), "rain_belt_north_share": float(rain[north].sum() / rain.sum())}


def engine_aquaplanet(data_dir, profile, days):
    level = yaml.safe_load((Path(data_dir) / "profiles.yaml").read_text(encoding="utf-8"))["profiles"][profile]["mesh_level"]
    mesh = get_mesh(level)
    e = Engine(data_dir, profile=profile, overrides=aquaplanet_overrides(data_dir, mesh, days))
    w = e.build()
    m = e.mesh
    bands = np.arange(-88.0, 89.0, 4.0)
    t = w.fields["surface_temperature"].mean(axis=0) - 273.15
    east = np.einsum("mij,ij->mi", w.fields["wind"], m.east).mean(axis=0)
    rain = w.fields["precipitation"].mean(axis=0)
    zonal = lambda f: np.array([f[np.abs(m.lat - b) <= 2.0].mean() for b in bands])
    return bands, zonal(t), zonal(east), zonal(rain), w


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gcm")
    ap.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--profile", default="preview")
    args = ap.parse_args(argv)
    g = json.loads(Path(args.gcm).read_text())
    days = g["rotation_days"]
    lat_g = np.asarray(g["lat"])
    gcm = summary(lat_g, np.asarray(g["ts"]) - 273.15, np.asarray(g["ua_lowest"]), np.asarray(g["pr"]))
    lat_e, t_e, u_e, p_e, w = engine_aquaplanet(args.data, args.profile, days)
    eng = summary(lat_e, t_e, u_e, p_e)
    print(json.dumps({"rotation_days": days, "engine": eng, "gcm": gcm, "engine_settled": w.settled}, indent=1))


if __name__ == "__main__":
    main()
