"""Trial of build step 3 (task T6): a history ten times the default, measured every 250 My.

Runs the setup and the geological stage only (the climate has no part in the history until build step 9), on the
preview mesh, for 2,500 My (1,250 rounds of 2 My), and every 250 My records:
  * the volume of continental crust (thickness times area over the cells of continental crust),
  * the share of the surface that is land,
  * the number of plates that carry at least one cell,
  * the mean height of the land above the sea,
  * the stray of a marked patch of crust: the distance, in cell spacings, between the centre of the marked crust and
    the place its plates' motions give that same crust: every point carries the place where its plate's motion puts
    it, turned each round with the plate that carries the point (so a patch that a rift splits or a weld moves is
    followed piece by piece), and carried through resampling with the same sources and weights as the mark. The patch
    is the continent of one plate around the point that lies deepest inside both its coast and its plate's edge.
    Two first versions measured otherwise and were dropped: one took a patch across two plates, whose parts parted;
    one followed the whole patch with the plate that carried most of it, which a rift through the patch defeats.
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


def rotate_each(pos, axis, angle):
    """Turn each position about its own axis by its own angle (Rodrigues' formula)."""
    c, s = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return pos * c + np.cross(axis, pos) * s + axis * np.einsum("ij,ij->i", axis, pos)[:, None] * (1 - c)


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
        should = (track["expected"] * mark[:, None]).sum(axis=0)
        stray = float(np.arccos(np.clip(centre @ should / np.linalg.norm(centre) / np.linalg.norm(should), -1, 1)) / spacing) \
            if mark.sum() > 0 else None
        row = {"time_my": r * dt, "continental_volume_km3": float((f["crust_thickness"] * cell_area)[cont].sum() / 1e9),
               "continental_area_share": float(area[cont].sum()), "land_share": float(area[land].sum()),
               "plates": int(np.unique(f["plate_id"]).size),
               "mean_land_height_m": float(np.average(f["height_above_sea"][land], weights=area[land])) if land.any() else None,
               "mean_continental_thickness_m": float(np.average(f["crust_thickness"][cont], weights=area[cont])),
               "patch_left_share": float(mark.sum() / track["mark0"]), "patch_stray_cells": stray,
               "patch_plates": {int(p): round(float(x), 2) for p, x in enumerate(np.bincount(pts["plate"], weights=mark)) if x > 0.5}}
        rows.append(row)
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)

    original_round, original_end = eng._run_round, eng._end_round

    def run_round(stage, round_no, recording, replay=False, starting=False):
        if stage == "geological" and not starting and "mark" in track:          # each point's expected place turns with its plate
            pts, plates = w.tables["crust_points"], w.tables["plates"]
            axes = np.stack([plates["axis_x"], plates["axis_y"], plates["axis_z"]], axis=1)[pts["plate"]]
            track["expected"] = rotate_each(track["expected"], axes, plates["angular_speed_rad_per_my"][pts["plate"]] * dt)
        return original_round(stage, round_no, recording, replay, starting)

    def end_round(stage, weight):
        original_end(stage, weight)
        if stage != "geological":
            return
        r = w.written_round["elevation"]
        pts = w.tables["crust_points"]
        if "mark" not in track:                                  # the patch: one plate's continent, around the point deepest inside
            cont = w.fields["crust_type"] == CONTINENTAL     # both its coast and its plate's edge (as in the crust trial of step 1)
            plate = w.fields["plate_id"]
            i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
            differ = (plate[i] != plate[j]) | (cont[i] != cont[j])
            edge_cell = np.zeros(mesh.n, dtype=bool)
            edge_cell[i[differ]] = edge_cell[j[differ]] = True
            depth = cKDTree(mesh.xyz[edge_cell]).query(mesh.xyz)[0]
            depth[~cont] = -1
            centre = int(np.argmax(depth))
            pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
            near = np.linalg.norm(pos - mesh.xyz[centre], axis=1) < min(0.6 * depth[centre], 4 * spacing)
            track["mark"] = (near & (pts["crust_type"] == CONTINENTAL) & (pts["plate"] == plate[centre])).astype(np.float64)
            track["mark0"] = track["mark"].sum()
            track["expected"] = pos.copy()
        else:
            src = np.stack([pts["source_a"], pts["source_b"], pts["source_c"]], axis=1).astype(np.int64)
            wts = np.stack([pts["weight_a"], pts["weight_b"], pts["weight_c"]], axis=1).astype(np.float64)
            ok = (src >= 0) & (src < track["mark"].size)
            wts = np.where(ok, wts, 0.0)
            tot = wts.sum(axis=1)
            track["mark"] = np.where(tot > 0, (track["mark"][np.where(ok, src, 0)] * wts).sum(axis=1) / np.maximum(tot, 1e-300), 0.0)
            pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
            carried = (track["expected"][np.where(ok, src, 0)] * wts[:, :, None]).sum(axis=1)
            norm = np.linalg.norm(carried, axis=1)
            track["expected"] = np.where((tot > 0)[:, None], carried / np.maximum(norm, 1e-300)[:, None], pos)
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
