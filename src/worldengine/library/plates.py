"""Plates on the mesh: the mathematics that the two implementations of Tectonics share.

Moved here from processes/tectonics_snapshot.py (build step 3) so that the snapshot and the plate history use one
seeded start and one reading of the boundaries; no process imports another. See the snapshot's file for the model.
"""
import numpy as np
import scipy.sparse as sp
from scipy.spatial import cKDTree

from . import operators as op  # noqa: F401
from .noise import WAVE_NUMBERS, wave_field
from .units import CM_PER_M, YEARS_PER_MY

OCEANIC, CONTINENTAL = 0, 1
NONE, RIDGE, TRENCH, COLLISION, TRANSFORM = 0, 1, 2, 3, 4
EVENT_SUBDUCTION, EVENT_COLLISION, EVENT_SPREADING = 1, 2, 4
EVENT_CODES = 8                 # room for the kinds of event when a pair of plates and a kind are packed into one number


SAME_WITHIN = 1.0e-9            # two lengths or distances that differ by less than this share count as equal
JOINED_STEPS_PER_CELL = 3       # sides walked along a boundary for each cell spacing of reach: enough to cover the reach
                                # (a side is about 0.6 of a spacing long), few enough not to walk round a small plate twice
CANDIDATES = 4                  # how many nearest points are looked at first when looking for points that are equally near


def _arc(chord):
    return 2 * np.arcsin(np.clip(chord / 2, 0, 1))


def _nearest(points, targets, first_key, second_key):
    """For each target, the straight-line distance to the nearest of the points and that point's index.

    On this mesh many cells lie exactly as far from two boundary cells as from one, and a cell at the middle of a
    round plate lies as far from every cell of its rim. Which of them a search tree returns depends on the order of
    the cells, so that turning the planet by one face of the mesh changed the world (second review). Of the points
    that are equally near, the one with the highest first key is taken, then the highest second key: what the
    points are decides, not how they are numbered. All points that are equally near are compared, however many
    (third check: a fixed handful was not enough for a plate centred on a pole)."""
    tree = cKDTree(points)
    dist, index = np.empty(len(targets)), np.empty(len(targets), dtype=np.int64)
    todo = np.arange(len(targets))
    count = min(CANDIDATES, len(points))
    while todo.size:
        d, idx = tree.query(targets[todo], k=count)
        if count == 1:
            d, idx = d[:, None], idx[:, None]
        tied = d <= d[:, :1] * (1.0 + SAME_WITHIN) + np.finfo(float).tiny
        more = tied[:, -1] & (count < len(points))               # every point looked at is equally near: look at more
        key = np.where(tied, first_key[idx], -np.inf)
        top = key.max(axis=1, keepdims=True)
        best = tied & (key >= top - SAME_WITHIN * np.abs(top))
        pick = np.argmax(np.where(best, second_key[idx].astype(np.float64), -np.inf), axis=1)
        rows = np.arange(todo.size)
        settled = ~more
        dist[todo[settled]], index[todo[settled]] = d[rows, pick][settled], idx[rows, pick][settled]
        todo = todo[more]
        count = min(2 * count, len(points))
    return dist, index


def seeded_start(ctx):
    """The seeded start of the plates and their crust (one crust point on each cell centre), written as the three tables."""
    c, mesh, n = ctx.const, ctx.mesh, ctx.mesh.n
    k = int(c["plates"])
    centres = ctx.draw.sphere_points("plate_centres", k)
    axes = ctx.draw.sphere_points("plate_axes", k)
    lo, hi = c["plate_speed_cm_per_year"]
    speed = (lo + (hi - lo) * ctx.draw.uniform("plate_speeds", k)) / CM_PER_M          # m per year at the plate's widest circle
    angular = speed / ctx.planet["radius_m"] * YEARS_PER_MY                           # radians per My
    # outlines: each cell joins the nearest plate centre, seen from a position shifted by a smooth random field
    o = c["outline"]
    dims = mesh.xyz.shape[1]                                 # one field of waves for each direction of the shift
    u = ctx.draw.uniform("outline_waves", int(o["waves"]) * dims * WAVE_NUMBERS).reshape(int(o["waves"]), dims, WAVE_NUMBERS)
    shift = np.stack([wave_field(mesh.xyz, u[:, i], o["wave_number"]) for i in range(dims)], axis=1)
    moved = mesh.xyz + o["amplitude_rad"] * shift
    moved /= np.linalg.norm(moved, axis=1, keepdims=True)
    plate = cKDTree(centres).query(moved)[1].astype(np.int32)
    # continents: a score from a smooth field, a per-plate bias and the distance from the plate's edge;
    # the highest-scoring share of the area is continental crust
    q = c["continents"]
    edge = boundary_cells(mesh, plate)
    depth = np.zeros(n)
    for p in range(k):
        mine = np.flatnonzero(plate == p)
        b = mine[edge[mine]]
        if b.size:
            depth[mine] = _arc(cKDTree(mesh.xyz[b]).query(mesh.xyz[mine])[0])
    bias = np.where(ctx.draw.uniform("continent_plates", k) < q["plate_share"], 1.0, -1.0)
    field = wave_field(mesh.xyz, ctx.draw.uniform("continent_waves", WAVE_NUMBERS * int(q["waves"])), q["wave_number"])
    score = field + q["plate_bias"] * bias[plate] + q["interior_weight"] * depth / max(depth.max(), np.finfo(float).tiny)
    order = np.lexsort((np.arange(n), -score))                                     # ties broken by cell number
    share = np.cumsum(mesh.area[order]) / mesh.area.sum()
    ctype = np.zeros(n, dtype=np.int16)
    ctype[order[share <= q["fraction"]]] = CONTINENTAL
    # thickness before any plate acts on it
    t = c["thickness"]
    vary = wave_field(mesh.xyz, ctx.draw.uniform("thickness_waves", WAVE_NUMBERS * int(t["variation_waves"])),
                      t["variation_wave_number"])
    thick = np.where(ctype == CONTINENTAL, t["continental_normal_m"] + t["continental_excess_m"] + t["variation_m"] * vary,
                     t["oceanic_m"])
    none = np.full(n, -1, dtype=np.int32)
    zero = np.zeros(n, dtype=np.float32)
    ctx.write_table("table:crust_points", {
        "plate": plate, "x": mesh.xyz[:, 0], "y": mesh.xyz[:, 1], "z": mesh.xyz[:, 2], "crust_type": ctype,
        "thickness_m": thick, "ocean_age_my": np.full(n, np.nan), "orogeny_age_my": np.full(n, np.nan),
        "thickened_by_plates_m": zero, "removed_by_erosion_m": zero, "formed_m": thick, "last_event": none,
        "source_a": none, "source_b": none, "source_c": none, "weight_a": zero, "weight_b": zero, "weight_c": zero})
    ctx.write_table("table:plates", {
        "plate": np.arange(k), "axis_x": axes[:, 0], "axis_y": axes[:, 1], "axis_z": axes[:, 2],
        "angular_speed_rad_per_my": angular, "area_m2": np.zeros(k), "continental_share": np.zeros(k),
        "carries_continent": bias > 0, "centre_x": centres[:, 0], "centre_y": centres[:, 1], "centre_z": centres[:, 2]})
    ctx.write_table("table:tectonic_events", {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []})


def boundary_cells(mesh, plate):
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    cross = plate[i] != plate[j]
    edge = np.zeros(mesh.n, dtype=bool)
    edge[i[cross]] = True
    edge[j[cross]] = True
    return edge

def boundaries(mesh, plate, ctype, rotation, radius, k, b):
    """Every cell that touches another plate: the plate it faces, whether the crust it faces is continental, the
    kind of boundary, and the speed at which the two plates close there (negative where they part).

    The direction of a boundary is not the direction of one side of one cell. On a mesh of six-sided cells a
    straight boundary is a zigzag whose sides stand 30 to 60 degrees off it, and judging by single sides turns
    plates that slide past each other into a row of false ridges and trenches. So the sides are added up, each
    as its length times its outward direction, over the stretch of boundary within reach of the cell: the sum
    over a run of sides points squarely across the straight line that joins the two ends of the run.
    """
    n = mesh.n
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    cross = np.flatnonzero(plate[i] != plate[j])
    cell = np.concatenate([i[cross], j[cross]]).astype(np.int64)             # each such side, seen from both of its cells
    other = np.concatenate([j[cross], i[cross]]).astype(np.int64)
    length = np.concatenate([mesh.edge_dual[cross], mesh.edge_dual[cross]])
    outward = np.concatenate([mesh.edge_normal[cross], -mesh.edge_normal[cross]]) * length[:, None]
    # the plate a cell faces: the one it shares the greatest length of side with. Lengths that differ by less
    # than round-off count as equal, and the lower plate number then wins: the answer must not hang on the last
    # bit of a sum (it did, by 3e-15, in the second review).
    uniq, inverse = np.unique(cell * k + plate[other], return_inverse=True)
    shared = np.bincount(inverse, weights=length)
    u_cell, u_plate = uniq // k, uniq % k
    longest = np.zeros(n)
    np.maximum.at(longest, u_cell, shared)
    short = shared < longest[u_cell] * (1.0 - SAME_WITHIN)
    order = np.lexsort((u_plate, short, u_cell))
    first = np.ones(order.size, dtype=bool)
    first[1:] = u_cell[order][1:] != u_cell[order][:-1]
    bcell = u_cell[order][first]
    facing = np.full(n, -1, dtype=np.int64)
    facing[bcell] = u_plate[order][first]
    is_boundary = facing >= 0
    toward = plate[other] == facing[cell]                                    # the sides a cell shares with the plate it faces
    cell, other, length, outward = cell[toward], other[toward], length[toward], outward[toward]
    # add up the sides of this plate against the faced one that lie within reach of the cell
    middle = mesh.xyz[cell] + mesh.xyz[other]
    middle /= np.linalg.norm(middle, axis=1, keepdims=True)
    reach = 2 * np.sin(b["direction_reach_cells"] * mesh.spacing() / 2)       # as a straight-line distance on the unit sphere
    found = cKDTree(mesh.xyz[bcell]).sparse_distance_matrix(cKDTree(middle), reach, output_type="coo_matrix")
    at, side = bcell[found.row], found.col
    same = (plate[cell[side]] == plate[at]) & (facing[cell[side]] == facing[at])
    at, side = at[same], side[same]
    # Only sides that the boundary itself joins to the cell's own sides count. A plate narrower than the reach has
    # its other flank within reach too, facing the opposite way; added in, it cancels the direction or turns it
    # by chance (second review: a strip sliding along itself came out as ridge and trench). Two sides are joined
    # if they meet at a corner, which is where the three cells of one mesh triangle meet.
    number = np.full(2 * cross.size, -1, dtype=np.int64)                     # each kept side's place in the arrays above
    number[np.flatnonzero(toward)] = np.arange(cell.size)
    edge_key = mesh.edge_cells[:, 0].astype(np.int64) * n + mesh.edge_cells[:, 1]
    place = np.full(mesh.edge_cells.shape[0], -1, dtype=np.int64)
    place[cross] = np.arange(cross.size)
    fa, fb, fc = mesh.faces[:, 0].astype(np.int64), mesh.faces[:, 1].astype(np.int64), mesh.faces[:, 2].astype(np.int64)
    sides_of = [np.searchsorted(edge_key, np.minimum(a, c) * n + np.maximum(a, c)) for a, c in ((fa, fb), (fb, fc), (fc, fa))]
    rows, cols = [], []
    for e1, e2 in ((sides_of[0], sides_of[1]), (sides_of[1], sides_of[2]), (sides_of[2], sides_of[0])):
        both = (place[e1] >= 0) & (place[e2] >= 0)
        p1, p2 = place[e1][both], place[e2][both]
        for half1 in (0, cross.size):                                        # each side is seen from both of its cells
            for half2 in (0, cross.size):
                s1, s2 = number[p1 + half1], number[p2 + half2]
                joined = (s1 >= 0) & (s2 >= 0)
                s1, s2 = s1[joined], s2[joined]
                joined = (plate[cell[s1]] == plate[cell[s2]]) & (plate[other[s1]] == plate[other[s2]])
                rows += [s1[joined], s2[joined]]
                cols += [s2[joined], s1[joined]]
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    step = sp.csr_matrix((np.ones(rows.size), (rows, cols)), shape=(cell.size, cell.size)) + sp.identity(cell.size, format="csr")
    runs = sp.csr_matrix((np.ones(cell.size), (cell, np.arange(cell.size))), shape=(n, cell.size))     # a cell's own sides
    for _ in range(int(np.ceil(JOINED_STEPS_PER_CELL * b["direction_reach_cells"]))):
        runs = runs @ step
        runs.data[:] = 1.0
    joined = np.asarray(runs[at, side]).ravel() > 0
    at, side = at[joined], side[joined]
    order = np.lexsort((side, at))                                           # a fixed order, so the sums never vary
    at, side = at[order], side[order]
    x = mesh.xyz[bcell]
    across = np.stack([np.bincount(at, weights=outward[side, axis], minlength=n)[bcell]
                       for axis in range(outward.shape[1])], axis=1)
    across -= np.einsum("ij,ij->i", across, x)[:, None] * x                 # lying in the surface at the cell
    size = np.linalg.norm(across, axis=1)
    added = np.bincount(at, weights=length[side], minlength=n)[bcell]        # the length of side that went into the sum
    # Sides along a straight boundary add up to 0.67 to 0.87 of their length. The whole outline of a small plate
    # adds up to next to nothing, and what is left points anywhere: such a plate has no direction, and its
    # boundary counts as sliding past.
    known = size > b["direction_known_above"] * added
    normal = np.where(known[:, None], across / np.maximum(size, np.finfo(float).tiny)[:, None], 0.0)
    relative = np.cross(rotation[plate[bcell]] - rotation[facing[bcell]], x) * radius   # m per year, own plate against the faced one
    closing = np.einsum("ij,ij->i", relative, normal)                        # positive where the plates close
    sliding = np.linalg.norm(relative - closing[:, None] * normal, axis=1)
    continental_side = np.bincount(cell, weights=length * (ctype[other] == CONTINENTAL), minlength=n)
    faces_continent = np.zeros(n, dtype=bool)
    faces_continent[bcell] = (continental_side + continental_side >= np.bincount(cell, weights=length, minlength=n))[bcell]
    meeting = np.where((ctype[bcell] == CONTINENTAL) & faces_continent[bcell], COLLISION, TRENCH)
    kinds = np.where(np.abs(closing) < b["transform_ratio"] * sliding, TRANSFORM, np.where(closing < 0, RIDGE, meeting))
    kinds = np.where(np.abs(closing) + sliding < b["minimum_speed_m_per_year"], TRANSFORM, kinds)
    b_kind = np.zeros(n, dtype=np.int16)
    b_kind[bcell] = kinds
    b_close = np.zeros(n)
    b_close[bcell] = closing
    return is_boundary, facing, faces_continent, b_kind, b_close

def diving(plate, facing, faces_continent, b_kind, ocean, age, k, equal_within_my):
    """Which boundary cells lie on the side of a trench that dives.

    The ocean floor dives under a continent. Between two ocean floors one plate dives along the whole of the
    trench that the two plates share, so that a trench keeps its direction along its length:
      * the plate whose floor already dives under the other plate's continent somewhere along that trench
        (if both do, the one that does so along more of it);
      * otherwise the plate whose floor at the trench is older (the higher plate number if the ages are equal).
    The two sides of a trench can then disagree only at a place where the crust beside the trench changes from
    continent to ocean and the direction of the trench truly turns over."""
    is_boundary = facing >= 0
    faced = np.maximum(facing, 0)
    pair = plate.astype(np.int64) * k + faced            # [own plate, plate it faces]
    at_trench = is_boundary & ocean & (b_kind == TRENCH)

    def count(cells):
        return np.bincount(pair[cells], minlength=k * k).reshape(k, k)

    def mean_age(cells):
        total = np.bincount(pair[cells], weights=age[cells], minlength=k * k).reshape(k, k)
        return total / np.maximum(count(cells), 1)
    under_continent = count(at_trench & faces_continent)
    lead = under_continent - under_continent.T           # above zero: this plate's floor dives under the other's continent
    floor_age = np.where(count(at_trench) > 0, mean_age(at_trench), mean_age(is_boundary & ocean))
    gap = floor_age - floor_age.T
    number = np.arange(k)
    older = (gap > equal_within_my) | ((np.abs(gap) <= equal_within_my) & (number[:, None] > number[None, :]))
    plate_dives = (lead > 0) | ((lead == 0) & older)
    return at_trench & (faces_continent | plate_dives[plate, faced])
