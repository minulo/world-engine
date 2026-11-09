"""Finer detail over one region of a finished world (build step 11).

What it is. A region is the cells of a finished world whose centres lie within a distance of a point. Each of them is
split into the cells of a finer level of the same mesh (meshes nest: about 4 ** extra_levels fine cells to a coarse one,
each fine cell belonging to the coarse cell whose centre is nearest), and what the ground needs is worked out again on
the fine cells (design, build order, step 11):
  * heights: a surface through the coarse cell centres, planar between each three neighbouring centres, roughened by
    waves whose size follows the spread of the coarse heights around. The values it passes through at the centres are
    lifted or lowered over a few passes so that each coarse cell keeps its height on the mean, and what is left is put
    in by a bump that is highest at the cell's centre and nothing on its edge, so that no coarse cell is moved as one;
  * sea and lakes: fine cells below the sea level where the coarse sea is near, and below a coarse lake's level;
  * rivers: inside each coarse cell the water runs over the fine cells to the fine cell nearest the coarse cell's
    receiver, and the river of each coarse cell upstream enters at the fine cell nearest it, with the finished world's
    flow. The flow is summed with the library's routines (flow_stack, accumulate);
  * climate: the temperature at sea level laid on the same surface and moved by the lapse rate for each fine cell's
    height, and the rain laid on it in logarithms (so that it stays above zero) and spread over the fine cells by the
    way their slopes face the year's wind, each kept on the coarse cell's mean in the same way as the heights.
The random draws are tied to the sphere, not to the region: the waves are drawn once from the world seed. A fine cell's
values depend only on its place and the coarse cells within a few rings of it, so two regions that overlap agree on the
cells they share, and one region asked for twice is the same bit for bit.

Why a planar surface. A first version laid the surface with smooth weights that fall off with the distance to each
centre (a Gaussian 0.6 coarse spacings wide). Such weights flatten the surface near each centre and steepen it near the
edges between coarse cells: on section 21's region its fine steps across those edges were larger than inside a cell
even when its passes had converged and no last correction was made [MEASURED, docs/notes_pending/detail-edges.md]. A
surface planar between three centres has no such places, and each of its passes leaves about a third of the gap where
the Gaussian surface's left about 0.7 [MEASURED, same place].

Departures from the design [INFERRED]: this is a computation on request beside the world, not a stage of stages.yaml,
and the world store keeps nothing of it. Rivers stay inside their coarse cell until they leave it toward the coarse
receiver: the region's rivers leave it where the coarse rivers do, and no divide moves.
Ignores: landforms below the coarse mesh that no process makes (valleys cut by the rivers, ridges, cliffs).
Wrong where: the roughness is a stand-in for those landforms, and the rule for rain on slopes is set here
[PROVISIONAL]. The surface bends along the lines between neighbouring centres, which the roughness hides but does not
remove. A world cell with no rain at all keeps none on its fine cells, and its edge is a step down to nothing.
"""
from __future__ import annotations

import heapq

import numpy as np
import yaml
from scipy.spatial import cKDTree

from . import draws
from .library import drainage as dr
from .library.units import M_PER_KM, TWO_PI
from .mesh import get_mesh
from .params import DEFAULT_DATA_DIR

SLOT = "Detail"                                   # the name its random draws are keyed by
WAVE_NUMBERS = 4                                  # uniform numbers that make one wave: two for its direction, its length, its phase
CORNERS = 6                                       # a cell is a corner of at most six triangles of cell centres
_CACHE: dict = {}


class Detail:
    """The fine cells of a region (their numbers in the mesh of `level`) and the fields worked out on them."""

    def __init__(self, level, cells, owner, fields, region, outlets):
        self.level, self.cells, self.owner, self.fields, self.region = level, cells, owner, fields, region
        self.outlets = outlets                    # coarse cell -> the fine cell where its water leaves it

    def coarse_means(self, name, area):
        """The area-weighted mean of a field over the fine cells of each coarse cell of the region."""
        a = self.fields[name]
        w = area[self.cells]
        sums = np.zeros((a.shape[0], self.region.size) if a.ndim == 2 else self.region.size)
        idx = np.searchsorted(self.region, self.owner)
        if a.ndim == 2:
            for m in range(a.shape[0]):
                sums[m] = np.bincount(idx, weights=w * a[m], minlength=self.region.size)
        else:
            sums = np.bincount(idx, weights=w * a, minlength=self.region.size)
        return sums / np.bincount(idx, weights=w, minlength=self.region.size)


def constants(view) -> dict:
    """The constants of the detail: those the world was built with, else the engine's own. A constant that the world's
    copy lacks, because it was added after the world was built, is the engine's own."""
    own = yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))
    text = (view.attrs.get("parameters_text") or {}).get("detail")
    return {**own, **(yaml.safe_load(text) if text else {})}


def _owners(coarse, fine):
    """For each fine cell the coarse cell whose centre is nearest, and the fine cells of each coarse cell in order."""
    key = (coarse.level, fine.level)
    if key not in _CACHE:
        own = cKDTree(coarse.xyz).query(fine.xyz)[1].astype(np.int64)
        order = np.argsort(own, kind="stable")
        start = np.searchsorted(own[order], np.arange(coarse.n + 1))
        _CACHE[key] = (own, order, start)
    return _CACHE[key]


def _grow(mesh, cells, rings):
    """The cells within `rings` steps of the given ones."""
    inside = np.zeros(mesh.n, dtype=bool)
    inside[cells] = True
    for _ in range(rings):
        near = mesh.nbr[inside]
        inside[near[near >= 0]] = True
    return np.flatnonzero(inside)


def _dot(u, v):
    """Dot products along the last axis, summed in one fixed order."""
    return u[..., 0] * v[..., 0] + u[..., 1] * v[..., 1] + u[..., 2] * v[..., 2]


def _triangles_of(mesh):
    """For each cell the triangles of cell centres (mesh.faces) it is a corner of, padded with -1."""
    key = ("triangles", mesh.level)
    if key not in _CACHE:
        corner = mesh.faces.ravel()
        order = np.argsort(corner, kind="stable")
        first = np.searchsorted(corner[order], np.arange(mesh.n))
        table = np.full((mesh.n, CORNERS), -1, dtype=np.int64)
        table[corner[order], np.arange(corner.size) - first[corner[order]]] = order // 3
        _CACHE[key] = table
    return _CACHE[key]


def _planar(coarse, xyz, owner):
    """For each point, the three coarse cells at the corners of the triangle of their centres that holds it, among the
    triangles its owner is a corner of, and its weights on them: the point's barycentric coordinates in the plane of the
    triangle, seen from the centre of the sphere, so that two triangles that share a side give the same weights along it.
    A point a hair outside every triangle (rounding) takes the nearest and its weights cut at nothing."""
    tri = _triangles_of(coarse)[owner]
    corners = coarse.faces[np.maximum(tri, 0)]
    a, b, c = (coarse.xyz[corners[..., i]] for i in range(3))
    p = np.broadcast_to(xyz[:, None, :], a.shape)
    lam = np.stack([_dot(p, np.cross(b, c)), _dot(a, np.cross(p, c)), _dot(a, np.cross(b, p))], axis=-1)
    lam = lam / (lam[..., 0] + lam[..., 1] + lam[..., 2])[..., None]
    best = np.argmax(np.where(tri >= 0, lam.min(axis=-1), -np.inf), axis=1)
    rows = np.arange(xyz.shape[0])
    corners, weights = corners[rows, best], np.maximum(lam[rows, best], 0.0)
    return corners, weights / (weights[:, 0] + weights[:, 1] + weights[:, 2])[:, None]


def _waves(seed, xyz, count, lengths):
    """A sum of plane waves through the sphere, drawn once from the seed; lengths in radians, longest first. Unlike the
    noise of the processes it is not scaled over the points given, so every point has its value whatever else is asked."""
    u = draws.uniform(seed, SLOT, "roughness", 0, WAVE_NUMBERS * count).reshape(count, WAVE_NUMBERS)
    z = 2.0 * u[:, 0] - 1.0
    lon = TWO_PI * u[:, 1]
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    longest, shortest = lengths
    length = longest * (shortest / longest) ** u[:, 2]
    number = TWO_PI / length
    amp = length / longest                                            # longer waves are higher
    out = np.zeros(xyz.shape[0])
    for i in range(count):                                            # whole-array steps in a fixed order
        along = xyz[:, 0] * (r[i] * np.cos(lon[i])) + xyz[:, 1] * (r[i] * np.sin(lon[i])) + xyz[:, 2] * z[i]
        out += amp[i] * np.sin(number[i] * along + TWO_PI * u[i, 3])
    return out / np.sqrt(0.5 * (amp * amp).sum())


def region_cells(coarse, lat, lon, radius_km, planet_radius_m):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    centre = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    reach = radius_km * M_PER_KM / planet_radius_m
    return np.flatnonzero(np.arccos(np.clip(coarse.xyz @ centre, -1.0, 1.0)) <= reach)


def refine(view, region, extra_levels=None) -> Detail:
    """The detail of a region: `region` holds the numbers of whole coarse cells of the world in `view`."""
    c = constants(view)
    extra = int(extra_levels if extra_levels is not None else c["extra_levels"])
    coarse = get_mesh(int(view.meta["mesh_level"]))
    fine = get_mesh(coarse.level + extra)
    own, order, start = _owners(coarse, fine)
    region = np.unique(np.asarray(region, dtype=np.int64))
    passes, relax = int(c["mean_iterations"]), float(c["relaxation"])
    # How far a value in the region reaches. After n passes a coarse value is the same in every region whose passes ran
    # over the coarse cells within n - 1 rings of it, and a fine cell's surface reads the coarse cells within one ring of
    # its own. The climate's passes run over the cells within `passes` rings of the region and read the fine heights one
    # ring further out, so the heights' passes run over passes + 1 rings more.
    near = _grow(coarse, region, passes)                              # the coarse cells whose climate is kept on the mean
    inner = _grow(coarse, region, 2 * passes + 1)                     # the coarse cells whose fine cells are worked out
    fine_of = lambda cells: np.concatenate([order[start[k]:start[k + 1]] for k in cells]) if len(cells) else np.zeros(0, np.int64)
    cells = np.sort(fine_of(inner))
    owner = own[cells]
    corners, weights = _planar(coarse, fine.xyz[cells], owner)

    def lay(values):                                                  # a coarse field (cells last) at the fine cells
        v = values[..., corners]
        return v[..., 0] * weights[:, 0] + v[..., 1] * weights[:, 1] + v[..., 2] * weights[:, 2]

    at_owner = corners == owner[:, None]
    bump = np.maximum(weights[at_owner] - np.where(at_owner, -np.inf, weights).max(axis=1), 0.0)   # 1 at a centre, 0 on an edge
    area = fine.area[cells]
    local = np.searchsorted(inner, owner)
    in_near = np.searchsorted(inner, near)

    def coarse_mean(values):                                          # over the fine cells of each coarse cell of `inner`
        weight = np.bincount(local, weights=area, minlength=inner.size)
        if values.ndim == 2:
            return np.stack([np.bincount(local, weights=area * v, minlength=inner.size) for v in values]) / weight
        return np.bincount(local, weights=area * values, minlength=inner.size) / weight

    def held(start_values, cells_kept, gap):                          # coarse values whose surface keeps the means
        s = np.array(start_values, dtype=np.float64)
        for _ in range(passes):
            s[..., cells_kept] += relax * gap(s)
        return s

    def exact(values, target):                                        # what the passes left, as a bump in each cell
        left = target[..., inner] - coarse_mean(values)
        return values + bump * (left / coarse_mean(bump))[..., local]

    seed = int(view.attrs["seed"])
    z = np.asarray(view.field("elevation"), dtype=np.float64)
    spread = np.zeros(coarse.n)
    around = _grow(coarse, inner, 1)
    one = np.concatenate([around[:, None], coarse.nbr[around]], axis=1)
    spread[around] = np.array([z[r[r >= 0]].std() for r in one])
    lengths = (c["wave_lengths_in_spacings"][0] * coarse.spacing(), c["wave_lengths_in_spacings"][1] * coarse.spacing())
    rough = c["roughness_share"] * lay(spread) * _waves(seed, fine.xyz[cells], int(c["waves"]), lengths)
    lift = held(z, inner, lambda s: z[inner] - coarse_mean(lay(s) + rough))
    height = exact(lay(lift) + rough, z)

    seas = view.table("seas")
    sea_level = float(seas["surface_m"][0]) if len(seas["surface_m"]) else 0.0
    ocean = np.asarray(view.field("ocean_mask"), dtype=bool)
    near_sea = ocean | np.where(coarse.nbr >= 0, ocean[np.maximum(coarse.nbr, 0)], False).any(axis=1)
    sea = (height < sea_level) & near_sea[owner]
    lake_level = np.asarray(view.field("lake_level"), dtype=np.float64)
    lake = ~sea & np.isfinite(lake_level[owner]) & (height < np.nan_to_num(lake_level[owner], nan=-np.inf))

    models = yaml.safe_load(view.attrs["parameters_text"]["models"])
    lapse = models["shared"]["lapse_rate_k_per_km"] / M_PER_KM
    above = np.maximum(height - sea_level, 0.0)
    h_coarse = np.maximum(np.asarray(view.field("height_above_sea"), dtype=np.float64), 0.0)
    t = np.asarray(view.field("surface_temperature"), dtype=np.float64)
    warm = held(t + lapse * h_coarse[None, :], near, lambda s: t[:, near] - coarse_mean(lay(s) - lapse * above)[:, in_near])
    temperature = exact(lay(warm) - lapse * above, t)

    # rain on the slopes that face the year's wind, each coarse cell keeping its total
    radius = float(view.attrs["planet"]["radius_m"])
    index = np.full(fine.n, -1, dtype=np.int64)
    index[cells] = np.arange(cells.size)
    nb = fine.nbr[cells]
    nbi = np.where(nb >= 0, index[np.maximum(nb, 0)], -1)
    has = nbi >= 0
    nbi = np.maximum(nbi, 0)
    step = (fine.xyz[cells][nbi] - fine.xyz[cells][:, None, :]) * radius            # metres, nearly in the tangent plane
    rise = np.where(has, height[nbi] - height[:, None], 0.0)
    norm = np.where(has, (step * step).sum(axis=-1), 0.0).sum(axis=1) / 2.0
    gradient = (rise[:, :, None] * step).sum(axis=1) / np.maximum(norm, 1.0)[:, None]
    wind = lay(np.asarray(view.field("wind"), dtype=np.float64).mean(axis=0).T).T
    toward = wind / np.maximum(np.linalg.norm(wind, axis=1, keepdims=True), 1e-9)
    facing = np.clip(1.0 + c["rain_per_windward_slope"] * (gradient * toward).sum(axis=1), c["rain_factor_limits"][0], c["rain_factor_limits"][1])
    p = np.asarray(view.field("precipitation"), dtype=np.float64)
    floor = float(c["rain_floor_mm"])
    log_p = np.log(np.maximum(p, floor))
    wet = held(log_p, near, lambda s: log_p[:, near] - np.log(np.maximum(coarse_mean(facing * np.exp(lay(s)))[:, in_near], floor)))
    rain = facing * np.exp(lay(wet))
    total = coarse_mean(rain)
    lift_rain = bump * ((p[:, inner] - total) / coarse_mean(rain * bump))[:, local]
    below = np.stack([np.bincount(local, weights=(f <= -1.0), minlength=inner.size) > 0 for f in lift_rain])
    rain = np.where(below[:, local], rain * (p[:, inner] / total)[:, local], rain * (1.0 + lift_rain))  # a dry cell: scaled

    # rivers: inside each coarse cell of the region, to the fine cell nearest its coarse receiver
    keep = np.isin(owner, region)
    out_cells = cells[keep]
    recv_c = np.asarray(view.field("flow_receiver"), dtype=np.int64)
    runoff = np.asarray(view.field("runoff_annual"), dtype=np.float64)
    q_coarse = np.asarray(view.field("river_discharge"), dtype=np.float64).mean(axis=0)
    year = float(view.attrs["planet"]["year_length_s"])
    lid = {int(k): i for i, k in enumerate(out_cells)}
    flows = np.flatnonzero(recv_c >= 0)
    by_receiver = flows[np.argsort(recv_c[flows], kind="stable")]
    first = np.searchsorted(recv_c[by_receiver], np.arange(coarse.n + 1))
    recv = np.full(out_cells.size, -1, dtype=np.int64)
    inflow = np.zeros(out_cells.size)
    hk, sk = height[keep], sea[keep]

    def nearest(members, point):
        return members[int(np.argmin(((fine.xyz[members] - point) ** 2).sum(axis=1)))]

    outlets = {}
    for k in region:
        mine = order[start[k]:start[k + 1]]
        if ocean[k]:
            continue
        r = recv_c[k]
        if r >= 0:
            outlet = nearest(mine, coarse.xyz[k] + coarse.xyz[r])
        else:                                                         # the bottom of a closed hollow: its lowest fine cell
            outlet = mine[int(np.argmin(height[np.searchsorted(cells, mine)]))]
        outlets[int(k)] = int(outlet)
        for d in by_receiver[first[k]:first[k + 1]]:                  # rivers from upstream enter nearest where they come from
            inflow[lid[int(nearest(mine, coarse.xyz[k] + coarse.xyz[d]))]] += q_coarse[d]
        reached = {int(outlet)}
        heap = [(float(hk[lid[int(outlet)]]), 0, int(outlet))]
        count = 1
        member = set(int(x) for x in mine)
        for s in mine:                                                # the sea inside a land cell takes water too
            if sk[lid[int(s)]] and int(s) not in reached:
                reached.add(int(s))
                heapq.heappush(heap, (float(hk[lid[int(s)]]), count, int(s)))
                count += 1
        while heap:                                                   # priority flood from the outlets, over this cell's fine cells
            level, _, f = heapq.heappop(heap)
            for g in fine.nbr[f]:
                g = int(g)
                if g < 0 or g not in member or g in reached:
                    continue
                reached.add(g)
                recv[lid[g]] = lid[f]
                heapq.heappush(heap, (max(level, float(hk[lid[g]])), count, g))
                count += 1
    land = ~ocean[own[out_cells]]
    local_q = np.where(land & ~sk, runoff[own[out_cells]] / 1000.0 * area[keep] * radius * radius / year, 0.0)
    stack = dr.flow_stack(recv)
    discharge = dr.accumulate(stack, recv, local_q + inflow)
    discharge = np.where(land, discharge, 0.0)

    fields = {"elevation": height[keep], "ocean_mask": sea[keep], "lake": lake[keep],
              "height_above_sea": (height - sea_level)[keep], "surface_temperature": temperature[:, keep],
              "precipitation": rain[:, keep], "river_discharge": discharge,
              "flow_receiver": np.where(recv >= 0, out_cells[np.maximum(recv, 0)], -1)}     # fine cells of the mesh, -1 for none
    return Detail(fine.level, out_cells, own[out_cells], fields, region, outlets)
