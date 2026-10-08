"""Trial of build step 3 (task T6): a history ten times the default, measured every 250 My.

Runs the setup and the geological stage only (the climate has no part in the history until build step 9), on the
preview mesh, for 2,500 My (1,250 rounds of 2 My), and every 250 My records:
  * the volume of continental crust (thickness times area over the cells of continental crust),
  * the share of the surface that is land,
  * the number of plates that carry at least one cell,
  * the mean height of the land above the sea,
  * the stray of a marked patch of crust: the distance, in cell spacings, between the centre of the marked crust and
    the place its plates' motions give it. The mark rides on the crust points, carried through every round with the
    sources and weights that Tectonics records; the place it should be is turned each round about the axis of the
    plate that carries most of the mark, by that plate's turn in that round.
A steady drift is judged in the notes, not here: the script prints the numbers and writes them to
trials/results/long_history_trial.json.

    python trials/long_history_trial.py [history_my] [every_my]
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine.engine import Engine, World                    # noqa: E402
from worldengine.mesh import get_mesh                           # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR                 # noqa: E402

HISTORY_MY = float(sys.argv[1]) if len(sys.argv) > 1 else 2500.0
EVERY_MY = float(sys.argv[2]) if len(sys.argv) > 2 else 250.0
CONTINENTAL = 1


def rotate(p, axis, angle):
    c, s = np.cos(angle), np.sin(angle)
    return p * c + np.cross(axis, p) * s + axis * (axis @ p) * (1 - c)


def main():
    eng = Engine(DEFAULT_DATA_DIR, profile="preview")
    cfg = dict(eng.stage_cfg["geological"])
    cfg["history_length_my"] = HISTORY_MY
    eng.stage_cfg["geological"] = cfg
    dt = float(cfg["round_length_my"])
    every = int(round(EVERY_MY / dt))
    eng.mesh = mesh = get_mesh(eng.level)
    eng.world = w = World(mesh, eng.months)
    eng._fresh, eng._weights, eng.memo = {}, {}, {}
    eng._received, eng._last_given, eng._applied, eng._rounds_in_force = set(), {}, {}, {}
    area = mesh.area / mesh.area.sum()
    spacing = mesh.spacing()
    rows, track = [], {}

    def measure(r):
        f = w.fields
        sea = f["ocean_mask"].astype(bool)
        land, cont = ~sea, f["crust_type"] == CONTINENTAL
        cell_area = f["cell_area"]
        pts = w.tables["crust_points"]
        pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
        mark = track["mark"]
        centre = (pos * mark[:, None]).sum(axis=0)
        stray = float(np.arccos(np.clip(centre @ track["expected"] / np.linalg.norm(centre), -1, 1)) / spacing) if mark.sum() > 0 else None
        row = {"time_my": r * dt, "continental_volume_km3": float((f["crust_thickness"] * cell_area)[cont].sum() / 1e9),
               "continental_area_share": float(area[cont].sum()), "land_share": float(area[land].sum()),
               "plates": int(np.unique(f["plate_id"]).size),
               "mean_land_height_m": float(np.average(f["height_above_sea"][land], weights=area[land])) if land.any() else None,
               "mean_continental_thickness_m": float(np.average(f["crust_thickness"][cont], weights=area[cont])),
               "patch_left_share": float(mark.sum() / track["mark0"]), "patch_stray_cells": stray}
        rows.append(row)
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)

    original_round, original_end = eng._run_round, eng._end_round

    def run_round(stage, round_no, recording, replay=False, starting=False):
        if stage == "geological" and not starting and "mark" in track:          # the plate that carries the mark, before it moves
            pts, plates = w.tables["crust_points"], w.tables["plates"]
            owner = int(np.bincount(pts["plate"], weights=track["mark"], minlength=plates["plate"].size).argmax())
            axis = np.array([plates["axis_x"][owner], plates["axis_y"][owner], plates["axis_z"][owner]])
            track["expected"] = rotate(track["expected"], axis, plates["angular_speed_rad_per_my"][owner] * dt)
        return original_round(stage, round_no, recording, replay, starting)

    def end_round(stage, weight):
        original_end(stage, weight)
        if stage != "geological":
            return
        r = w.written_round["elevation"]
        pts = w.tables["crust_points"]
        if "mark" not in track:                                  # the patch: continental crust around the deepest interior point
            cont = w.fields["crust_type"] == CONTINENTAL
            edge = cKDTree(mesh.xyz[~cont]).query(mesh.xyz)[0]
            edge[~cont] = -1
            centre = int(np.argmax(edge))
            pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
            near = np.linalg.norm(pos - mesh.xyz[centre], axis=1) < min(0.6 * edge[centre], 4 * spacing)
            track["mark"] = (near & (pts["crust_type"] == CONTINENTAL)).astype(np.float64)
            track["mark0"] = track["mark"].sum()
            track["expected"] = (pos * track["mark"][:, None]).sum(axis=0)
            track["expected"] /= np.linalg.norm(track["expected"])
        else:
            src = np.stack([pts["source_a"], pts["source_b"], pts["source_c"]], axis=1).astype(np.int64)
            wts = np.stack([pts["weight_a"], pts["weight_b"], pts["weight_c"]], axis=1).astype(np.float64)
            ok = (src >= 0) & (src < track["mark"].size)
            wts = np.where(ok, wts, 0.0)
            tot = wts.sum(axis=1)
            track["mark"] = np.where(tot > 0, (track["mark"][np.where(ok, src, 0)] * wts).sum(axis=1) / np.maximum(tot, 1e-300), 0.0)
        if r == 1 or r % every == 0:
            measure(r)

    eng._run_round, eng._end_round = run_round, end_round
    t0 = time.time()
    with eng._limit_threads():
        eng._run_once("setup")
        eng._run_geological("geological")
    out = {"history_my": HISTORY_MY, "every_my": EVERY_MY, "mesh_level": eng.level, "seed": eng.seed,
           "seconds": round(time.time() - t0, 1), "rows": rows}
    path = Path(__file__).resolve().parent / "results" / "long_history_trial.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("seconds", out["seconds"], "written to", path)


if __name__ == "__main__":
    main()
