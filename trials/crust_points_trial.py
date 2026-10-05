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
  4. every `resample` rounds the points are replaced by one point per cell, filled from the three old points
     of the same plate nearest to it.

Pass conditions. The design fixes their form in its build order, step 1 (within one cell; no more than a stated
share; fewer than a stated share), and it was approved before any code was written. The two shares, 2 % and 1 %,
are set here. The trial came into the repository together with its first results, so no record shows that they
were set before the first run [UNVERIFIED: I recall that they were]:
  A. after 125 rounds a marked patch of crust lies within one cell of the place its plate's motion gives;
  B. the area of continental crust has changed by no more than 2 % beyond what the closing of plates destroyed;
  C. fewer than 1 % of cells, on average, switch crust type and switch back within three rounds.

Two things were changed after the reviews of build step 1, when the trial was run again on plates seeded
differently and failed condition A as it was first measured. docs/BUILD_NOTES.md, section 3.2, gives the numbers.

  How A is measured. Every point now carries its home: the place where its crust stood at the start. The place a
  plate's motion gives a piece of crust is its home turned by that motion over the whole run. The miss of the patch
  is the distance between the centre of the marked crust that is left and the centre of the places its plate's
  motion gives that same crust. The first version compared the centre of what was left with the place of the whole
  patch's centre. That reads a patch that was partly consumed as a patch that moved. It is still reported, as
  patch_centre_miss_cells, with the share of the patch that is left.

  How a fresh point is filled (rule 4). "even": with the weights that write the fresh point's place as a mix of the
  three old places. They give back exactly any value that changes evenly across the three points, which is how the
  paper fills its points (Cortial et al. 2019, section 6: it interpolates inside the triangle of old points).
  "inverse_distance": with one over the distance to each old point, the first version of this trial, which shifts
  values by up to a fifth of a cell at every resampling. Both are run.

The drift of every point of continental crust is reported too: how far the point stands from the place its
plate's motion gives its crust.

    python trials/crust_points_trial.py [level ...]          the default world: three resampling intervals, both fills
    python trials/crust_points_trial.py seeds [level ...]    ten other seeds at the trial's own interval, even fill
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
FILLS = ("even", "inverse_distance")
FLAT = 1e-12                    # three old points whose places span less than this (as a determinant) lie in a row


def rotate(pos, axis, angle):
    """Turn each position about its own axis by its own angle (Rodrigues' formula)."""
    c, s = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return pos * c + np.cross(axis, pos) * s + axis * np.einsum("ij,ij->i", axis, pos)[:, None] * (1 - c)


def fill_weights(old, fresh, distance, fill):
    """The weights of the three old points around each fresh point.

    old: (n, 3, 3), the places of the three old points; fresh: (n, 3); distance: (n, 3) between them.
    "even" writes each fresh place as a mix of the three old places. A fresh point outside the triangle of the three
    would need a negative weight; that weight is set to zero, so the value is taken from the nearest side or corner.
    Three points in a row have no such mix: there, and for "inverse_distance", the weight is one over the distance."""
    by_distance = 1.0 / np.maximum(distance, 1e-9)
    if fill == "inverse_distance":
        return by_distance
    places = np.transpose(old, (0, 2, 1))                       # the three places as the columns of a matrix
    in_a_row = np.abs(np.linalg.det(places)) < FLAT
    places[in_a_row] = np.eye(3)
    weights = np.clip(np.linalg.solve(places, fresh[:, :, None])[:, :, 0], 0.0, None)
    weights[in_a_row] = by_distance[in_a_row]
    return weights


def trial(level, seed=20261004, resample=RESAMPLE, fill="even", log=print, save=True):
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
    home = pos.copy()                                           # where each point's crust stood at the start

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
    marked_at_start = float((mark * mesh.area).sum())
    home_plate = int(plate[centre])
    expected = mesh.xyz[centre].copy()

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
        pos, plate, ctype, mark, area, home = pos[keep], plate[keep], ctype[keep], mark[keep], area[keep], home[keep]
        # 3. draw the crust onto the mesh; uncovered cells are new ocean floor
        tree = cKDTree(pos)
        dist, near = tree.query(mesh.xyz)
        gap = dist > 0.75 * spacing
        if gap.any():
            cells = np.flatnonzero(gap)
            on_plate = plate[near[cells]]
            pos = np.concatenate([pos, mesh.xyz[cells]])
            home = np.concatenate([home, rotate(mesh.xyz[cells], axes[on_plate], -rate[on_plate] * r)])
            plate = np.concatenate([plate, on_plate])
            ctype = np.concatenate([ctype, np.zeros(cells.size, dtype=np.int64)])
            mark = np.concatenate([mark, np.zeros(cells.size)])
            area = np.concatenate([area, mesh.area[cells]])
            near[cells] = np.arange(pos.shape[0] - cells.size, pos.shape[0])
            created_total += int(cells.size)
        drawn = ctype[near]
        if r >= 2:
            flicker.append(float(((drawn_prev != drawn_prev2) & (drawn == drawn_prev2)).mean()))
        drawn_prev2, drawn_prev = drawn_prev, drawn
        # 4. resampling: one fresh point per cell, filled from the three old points around it, inside one plate only
        if resample and r % resample == 0:
            d3, i3 = cKDTree(pos).query(mesh.xyz, k=3)
            w3 = fill_weights(pos[i3], mesh.xyz, d3, fill) * (plate[i3] == plate[near][:, None])
            alone = w3.sum(axis=1) <= 0                          # no weight is left: the nearest point alone
            w3[alone] = i3[alone] == near[alone][:, None]
            w3 /= w3.sum(axis=1)[:, None]
            new_home = (w3[:, :, None] * home[i3]).sum(axis=1)
            new_home /= np.linalg.norm(new_home, axis=1)[:, None]
            pos, plate, ctype, mark, area, home = (mesh.xyz.copy(), plate[near], ctype[near], (w3 * mark[i3]).sum(axis=1),
                                                   mesh.area.copy(), new_home)
    seconds = time.time() - t0
    # the measurements
    dist, near = cKDTree(pos).query(mesh.xyz)
    should = rotate(home, axes[plate], rate[plate] * ROUNDS)    # where its plate's motion puts each point's crust
    drift = np.arccos(np.clip(np.einsum("ij,ij->i", pos, should), -1, 1)) / spacing
    continental = ctype == 1
    weight = mark * area
    left = float(weight.sum() / marked_at_start)
    if weight.sum() > 0:
        centre_is = (pos * weight[:, None]).sum(axis=0)
        centre_should = (should * weight[:, None]).sum(axis=0)
        miss_cells = float(np.arccos(np.clip(centre_is @ centre_should / np.linalg.norm(centre_is) / np.linalg.norm(centre_should), -1, 1)) / spacing)
        mark_cells = mark[near] * mesh.area
        centroid = (mesh.xyz * mark_cells[:, None]).sum(axis=0)
        centre_miss = float(np.arccos(np.clip(centroid @ expected / np.linalg.norm(centroid), -1, 1)) / spacing)
    else:
        miss_cells = centre_miss = None                         # the whole patch was consumed: nothing is left to measure
    travelled = float(np.arccos(np.clip(mesh.xyz[centre] @ expected, -1, 1)) / spacing)
    cont_end = float(mesh.area[ctype[near] == 1].sum())
    area_error = (cont_end - cont0 + destroyed) / cont0
    mean_flicker = float(np.mean(flicker))
    rounded = lambda x, d: None if x is None else round(x, d)
    result = {
        "level": level, "cells": n, "seed": seed, "rounds": ROUNDS, "resample_every": resample, "fresh_points_filled": fill,
        "seconds": round(seconds, 1),
        "patch_travelled_cells": round(travelled, 1), "patch_left_share": round(left, 3),
        "patch_miss_cells": rounded(miss_cells, 3), "patch_centre_miss_cells": rounded(centre_miss, 3),
        "crust_drift_mean_cells": round(float(drift[continental].mean()), 3),
        "crust_drift_95_in_100_below_cells": round(float(np.percentile(drift[continental], 95)), 3),
        "crust_drift_largest_cells": round(float(drift[continental].max()), 3),
        "continental_area_start_share": round(cont0 / mesh.area.sum(), 4), "continental_area_end_share": round(cont_end / mesh.area.sum(), 4),
        "destroyed_by_closing_share_of_start": round(destroyed / cont0, 4), "area_change_beyond_rules": round(area_error, 4),
        "flicker_mean_share": round(mean_flicker, 5), "flicker_max_share": round(float(np.max(flicker)), 5),
        "points_consumed": consumed_total, "points_created": created_total, "points_at_end": int(pos.shape[0]),
        "pass_A_patch": None if miss_cells is None else bool(miss_cells <= LIMIT_PATCH_CELLS),
        "pass_B_area": bool(abs(area_error) <= LIMIT_AREA), "pass_C_flicker": bool(mean_flicker < LIMIT_FLICKER)}
    for k, v in result.items():
        log(f"  {k}: {v}")
    if save:
        out = Path(__file__).resolve().parent / "results"
        out.mkdir(exist_ok=True)
        (out / f"crust_points_level{level}_resample{resample}_{fill}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


OTHER_SEEDS = (1, 2, 3, 7, 10, 11, 13, 16, 25, 42)


def other_seeds(level, log=print, save=True):
    """The trial on ten other seeded worlds, to see what holds beyond the default world. One file for all ten."""
    keep = ("seed", "patch_travelled_cells", "patch_left_share", "patch_miss_cells", "patch_centre_miss_cells",
            "crust_drift_mean_cells", "crust_drift_95_in_100_below_cells", "crust_drift_largest_cells",
            "destroyed_by_closing_share_of_start", "area_change_beyond_rules", "flicker_mean_share",
            "pass_A_patch", "pass_B_area", "pass_C_flicker")
    rows = []
    for seed in OTHER_SEEDS:
        result = trial(level, seed=seed, log=lambda line: None, save=False)
        rows.append({k: result[k] for k in keep})
        log(f"  {rows[-1]}")
    if save:
        out = Path(__file__).resolve().parent / "results"
        out.mkdir(exist_ok=True)
        (out / f"crust_points_level{level}_ten_seeds.json").write_text(json.dumps(
            {"level": level, "rounds": ROUNDS, "resample_every": RESAMPLE, "fresh_points_filled": "even", "worlds": rows}, indent=1) + "\n",
            encoding="utf-8")
    return rows


def parser():
    from worldengine import console
    p = console.tool_parser(__doc__ + """
    python trials/crust_points_trial.py [seeds] [LEVEL ...] [--write]

The results are printed. With --write they are also written to trials/results/, over the files kept there. [On the
machine they were made on, a new run at mesh level 5 differed from the kept files in the seconds a run took and in
nothing else: MEASURED by the fourth check of build step 2.]
""", "python trials/crust_points_trial.py")
    p.add_argument("what", nargs="*", metavar="seeds | LEVEL", help="the word seeds for the ten other seeds; mesh levels (default: 5 and 7)")
    p.add_argument("--write", action="store_true")
    return p


def main(argv=None) -> int:
    from worldengine import console
    args = parser().parse_args(argv)
    console.print_anywhere()
    seeds = bool(args.what) and args.what[0] == "seeds"
    try:
        levels = [int(a) for a in args.what[1 if seeds else 0:]] or [5, 7]
    except ValueError:
        print(f"a mesh level is a whole number, and the word seeds comes first: {' '.join(args.what)}", file=sys.stderr)
        return 2
    for level in levels:
        if seeds:
            print(f"crust trial at mesh level {level}, ten other seeds, resampling every {RESAMPLE} rounds, fresh points filled even")
            other_seeds(level, save=args.write)
            continue
        for fill in FILLS:
            for every in (RESAMPLE, 10, 60):                    # the paper resamples every 10 to 60 steps
                print(f"crust trial at mesh level {level}, resampling every {every} rounds, fresh points filled {fill}")
                trial(level, resample=every, fill=fill, save=args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
