"""Trial of build step 1: carry the crust on points that ride with the plates, and draw it onto the mesh.

The design keeps the crust on crust points (Question 16) and makes this trial the test of that choice,
before any process depends on it. This is a trial, not engine code: a bare model of moving plates with
just enough rules to open and close oceans.

Each round of 2 My:
  1. every point turns with its plate about the plate's axis;
  2. where plates close, a point that comes within half a cell of a point of another plate with priority is
     consumed (continental crust has priority over ocean floor; otherwise the plate with the lower number);
  3. each mesh cell takes the crust of the nearest point; a cell with no point within three quarters of a cell
     is new ocean floor, and gets a point of its own on the nearer plate;
  4. every `resample` rounds the points are replaced by one point per cell, filled from the old points.

Pass conditions, fixed before the first run:
  A. after 125 rounds a marked patch of crust lies within one cell of the place its plate's motion gives;
  B. the area of continental crust has changed by no more than 2 % beyond what the closing of plates destroyed;
  C. fewer than 1 % of cells, on average, switch crust type and switch back within three rounds.

    python trials/crust_points_trial.py [level ...]
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine.testing import Harness                      # noqa: E402

ROUNDS, STEP_MY, RESAMPLE = 125, 2.0, 20
LIMIT_PATCH_CELLS, LIMIT_AREA, LIMIT_FLICKER = 1.0, 0.02, 0.01


def rotate(pos, axis, angle):
    """Turn each position about its own axis by its own angle (Rodrigues' formula)."""
    c, s = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return pos * c + np.cross(axis, pos) * s + axis * np.einsum("ij,ij->i", axis, pos)[:, None] * (1 - c)


def trial(level, seed=20261004, resample=RESAMPLE, log=print):
    h = Harness(level=level, seed=seed)
    mesh = h.mesh
    n, spacing = mesh.n, mesh.spacing()
    g = h.run("PlanetGeometry").fields
    start = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, start=True)
    plates, pts = start.tables["plates"], start.tables["crust_points"]
    axes = np.stack([plates["axis_x"], plates["axis_y"], plates["axis_z"]], axis=1)
    rate = plates["angular_speed_rad_per_my"] * STEP_MY          # radians per round
    pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1).copy()
    plate, ctype = pts["plate"].astype(np.int64).copy(), pts["crust_type"].astype(np.int64).copy()
    area = mesh.area.copy()                                     # the area each point stands for

    # the marked patch: continental crust around the continental cell farthest from any other kind of crust or plate
    edge = np.zeros(n, dtype=bool)
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    differ = (plate[i] != plate[j]) | (ctype[i] != ctype[j])
    edge[i[differ]] = True
    edge[j[differ]] = True
    depth = cKDTree(mesh.xyz[edge]).query(mesh.xyz)[0]
    depth[ctype != 1] = -1
    centre = int(np.argmax(depth))
    patch_radius = min(0.6 * depth[centre], 6 * spacing)
    mark = ((np.linalg.norm(mesh.xyz - mesh.xyz[centre], axis=1) < patch_radius) & (ctype == 1)).astype(np.float64)
    home_plate = int(plate[centre])
    expected = mesh.xyz[centre].copy()

    cell_tree = cKDTree(mesh.xyz)
    cont0 = float(mesh.area[ctype == 1].sum())
    destroyed = 0.0
    drawn_prev2 = drawn_prev = ctype.copy()
    flicker, consumed_total, created_total = [], 0, 0
    t0 = time.time()
    for r in range(1, ROUNDS + 1):
        pos = rotate(pos, axes[plate], rate[plate])
        expected = rotate(expected[None, :], axes[[home_plate]], rate[[home_plate]])[0]
        # 2. plates closing: a point too close to a point of another plate with priority is consumed
        tree = cKDTree(pos)
        pairs = tree.query_pairs(0.5 * spacing, output_type="ndarray")
        gone = np.zeros(pos.shape[0], dtype=bool)
        if pairs.size:
            a, b = pairs[:, 0], pairs[:, 1]
            cross = plate[a] != plate[b]
            a, b = a[cross], b[cross]
            a_wins = (ctype[a] > ctype[b]) | ((ctype[a] == ctype[b]) & (plate[a] < plate[b]))
            gone[np.where(a_wins, b, a)] = True
        destroyed += float(area[gone & (ctype == 1)].sum())
        consumed_total += int(gone.sum())
        keep = ~gone
        pos, plate, ctype, mark, area = pos[keep], plate[keep], ctype[keep], mark[keep], area[keep]
        # 3. draw the crust onto the mesh; uncovered cells are new ocean floor
        tree = cKDTree(pos)
        dist, near = tree.query(mesh.xyz)
        gap = dist > 0.75 * spacing
        if gap.any():
            cells = np.flatnonzero(gap)
            pos = np.concatenate([pos, mesh.xyz[cells]])
            plate = np.concatenate([plate, plate[near[cells]]])
            ctype = np.concatenate([ctype, np.zeros(cells.size, dtype=np.int64)])
            mark = np.concatenate([mark, np.zeros(cells.size)])
            area = np.concatenate([area, mesh.area[cells]])
            near[cells] = np.arange(pos.shape[0] - cells.size, pos.shape[0])
            created_total += int(cells.size)
        drawn = ctype[near]
        if r >= 2:
            flicker.append(float(((drawn_prev != drawn_prev2) & (drawn == drawn_prev2)).mean()))
        drawn_prev2, drawn_prev = drawn_prev, drawn
        # 4. resampling: one fresh point per cell, filled from the three old points around it
        if resample and r % resample == 0:
            d3, i3 = cKDTree(pos).query(mesh.xyz, k=3)
            w3 = 1.0 / np.maximum(d3, 1e-9)
            same = plate[i3] == plate[near][:, None]             # interpolate inside one plate only
            w3 = w3 * same
            new_mark = (w3 * mark[i3]).sum(axis=1) / w3.sum(axis=1)
            pos, plate, ctype, mark, area = mesh.xyz.copy(), plate[near], ctype[near], new_mark, mesh.area.copy()
    seconds = time.time() - t0
    # the three measurements
    dist, near = cKDTree(pos).query(mesh.xyz)
    mark_cells = mark[near] * mesh.area
    centroid = (mesh.xyz * mark_cells[:, None]).sum(axis=0)
    centroid /= np.linalg.norm(centroid)
    miss_cells = float(np.arccos(np.clip(centroid @ expected, -1, 1)) / spacing)
    travelled = float(np.arccos(np.clip(mesh.xyz[centre] @ expected, -1, 1)) / spacing)
    cont_end = float(mesh.area[ctype[near] == 1].sum())
    area_error = (cont_end - cont0 + destroyed) / cont0
    mean_flicker = float(np.mean(flicker))
    result = {
        "level": level, "cells": n, "rounds": ROUNDS, "resample_every": resample, "seconds": round(seconds, 1),
        "patch_travelled_cells": round(travelled, 1), "patch_miss_cells": round(miss_cells, 3),
        "patch_mark_kept": round(float(mark_cells.sum() / (mesh.area * ((np.linalg.norm(mesh.xyz - mesh.xyz[centre], axis=1) < patch_radius))).sum()), 3),
        "continental_area_start_share": round(cont0 / mesh.area.sum(), 4), "continental_area_end_share": round(cont_end / mesh.area.sum(), 4),
        "destroyed_by_closing_share_of_start": round(destroyed / cont0, 4), "area_change_beyond_rules": round(area_error, 4),
        "flicker_mean_share": round(mean_flicker, 5), "flicker_max_share": round(float(np.max(flicker)), 5),
        "points_consumed": consumed_total, "points_created": created_total, "points_at_end": int(pos.shape[0]),
        "pass_A_patch": bool(miss_cells <= LIMIT_PATCH_CELLS), "pass_B_area": bool(abs(area_error) <= LIMIT_AREA),
        "pass_C_flicker": bool(mean_flicker < LIMIT_FLICKER)}
    for k, v in result.items():
        log(f"  {k}: {v}")
    out = Path(__file__).resolve().parent / "results"
    out.mkdir(exist_ok=True)
    (out / f"crust_points_level{level}_resample{resample}.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    levels = [int(a) for a in sys.argv[1:]] or [5, 7]
    for level in levels:
        for every in (RESAMPLE, 10, 60):                        # the paper resamples every 10 to 60 steps
            print(f"crust trial at mesh level {level}, resampling every {every} rounds")
            trial(level, resample=every)
