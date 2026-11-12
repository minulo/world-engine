"""Finer detail over one region of a finished world (build step 11).

What it is. A region is the cells of a finished world whose centres lie within a distance of a point. Each of them is
split into the cells of a finer level of the same mesh (meshes nest: about 4 ** extra_levels fine cells to a coarse one,
each fine cell belonging to the coarse cell whose centre is nearest), and what the ground needs is worked out again on
the fine cells (design, build order, step 11):
  * heights: a smooth surface through the coarse heights, roughened by waves whose size follows the spread of the
    coarse heights around, and lifted or lowered, smoothly over a few passes and then by what is left, so that each
    coarse cell keeps its height on the mean;
  * sea and lakes: fine cells below the sea level where the coarse sea is near, and below a coarse lake's level;
  * rivers: inside each coarse cell the water runs over the fine cells to the fine cell nearest the coarse cell's
    receiver, and the river of each coarse cell upstream enters at the fine cell nearest it, with the finished world's
    flow. The flow is summed with the library's routines (flow_stack, accumulate);
  * climate: the temperature moved by the lapse rate for each fine cell's height, and the rain spread over the fine
    cells by the way their slopes face the year's wind, each keeping the coarse cell's mean.
The random draws are tied to the sphere, not to the region: the waves are drawn once from the world seed. A fine cell's
values depend only on its place and the coarse cells within a few rings of it, so two regions that overlap agree on the
cells they share, and one region asked for twice is the same bit for bit.

Departures from the design [INFERRED]: this is a computation on request beside the world, not a stage of stages.yaml,
and the world store keeps nothing of it. Rivers stay inside their coarse cell until they leave it toward the coarse
receiver: the region's rivers leave it where the coarse rivers do, and no divide moves.
Ignores: landforms below the coarse mesh that no process makes (valleys cut by the rivers, ridges, cliffs).
Wrong where: the roughness is a stand-in for those landforms, and the rule for rain on slopes is set here
[PROVISIONAL]. What is left after the smooth passes is put right cell by cell, which leaves small steps at the edges of
the coarse cells.
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
SECOND_RING = 19                                  # a cell, its 6 neighbours and their 12 further ones: the most two steps reach
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
    """The constants of the detail: those the world was built with, else the engine's own."""
    text = (view.attrs.get("parameters_text") or {}).get("detail")
    if not text:
        text = (DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


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


def _second_ring(mesh, cells):
    """For each cell, itself and the cells within two steps, sorted, padded with -1: one row per cell."""
    one = np.concatenate([cells[:, None], mesh.nbr[cells]], axis=1)
    two = np.concatenate([one, np.where(one[:, 1:, None] >= 0, mesh.nbr[np.maximum(one[:, 1:], 0)], -1).reshape(len(cells), -1)], axis=1)
    two = np.sort(np.where(two < 0, mesh.n, two), axis=1)
    two[:, 1:][two[:, 1:] == two[:, :-1]] = mesh.n                  # each cell once
    two = np.sort(two, axis=1)[:, :SECOND_RING]                       # one width for every row, so that every sum over a row
    return np.where(two == mesh.n, -1, two)                           # is taken in the same order whatever the region


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
    iterations = int(c["mean_iterations"])
    foot = _grow(coarse, region, 2 * iterations + 6)                 # every coarse cell a value in the region can depend on
    ring = _second_ring(coarse, foot)
    fine_of = lambda cells: np.concatenate([order[start[k]:start[k + 1]] for k in cells]) if len(cells) else np.zeros(0, np.int64)
    inner = _grow(coarse, region, 2 * iterations + 3)                 # the coarse cells whose fine cells are worked out
    cells = np.sort(fine_of(inner))
    where = {int(k): i for i, k in enumerate(foot)}
    row = np.array([where[int(k)] for k in own[cells]])
    cand = ring[row]
    valid = cand >= 0
    d2 = ((fine.xyz[cells][:, None, :] - coarse.xyz[np.maximum(cand, 0)]) ** 2).sum(axis=-1)
    sigma = c["smoothing_spacings"] * coarse.spacing()
    w = np.where(valid, np.exp(-d2 / (sigma * sigma)), 0.0)
    w = w / w.sum(axis=1, keepdims=True)
    safe = np.maximum(cand, 0)

    def smooth(values):                                               # a coarse field (cells first) at the fine cells
        v = values[safe]
        if v.ndim == 2:
            return (w * v).sum(axis=1)
        return np.einsum("ij,ijk->ik", w, v)

    area = fine.area
    local = np.searchsorted(inner, own[cells])

    def coarse_mean(values):                                          # over the fine cells of each coarse cell of `inner`
        weight = area[cells]
        return np.bincount(local, weights=weight * values, minlength=inner.size) / np.bincount(local, weights=weight, minlength=inner.size)

    seed = int(view.attrs["seed"])
    z = np.asarray(view.field("elevation"), dtype=np.float64)
    spread = np.zeros(coarse.n)
    one = np.concatenate([foot[:, None], coarse.nbr[foot]], axis=1)
    spread[foot] = np.array([z[r[r >= 0]].std() for r in one])
    lengths = (c["wave_lengths_in_spacings"][0] * coarse.spacing(), c["wave_lengths_in_spacings"][1] * coarse.spacing())
    rough = c["roughness_share"] * smooth(spread) * _waves(seed, fine.xyz[cells], int(c["waves"]), lengths)
    shift = np.zeros(coarse.n)
    for _ in range(iterations):                                       # keep each coarse cell's mean height
        height = smooth(z + shift) + rough
        shift[inner] += z[inner] - coarse_mean(height)
    height = smooth(z + shift) + rough
    height = height + (z[inner] - coarse_mean(height))[local]        # what the passes left: each coarse cell's mean exactly

    seas = view.table("seas")
    sea_level = float(seas["surface_m"][0]) if len(seas["surface_m"]) else 0.0
    ocean = np.asarray(view.field("ocean_mask"), dtype=bool)
    near_sea = np.zeros(coarse.n, dtype=bool)
    near_sea[foot] = [ocean[r[r >= 0]].any() for r in one]
    sea = (height < sea_level) & near_sea[own[cells]]
    lake_level = np.asarray(view.field("lake_level"), dtype=np.float64)
    lake = ~sea & np.isfinite(lake_level[own[cells]]) & (height < np.nan_to_num(lake_level[own[cells]], nan=-np.inf))

    models = yaml.safe_load(view.attrs["parameters_text"]["models"])
    lapse = models["shared"]["lapse_rate_k_per_km"] / M_PER_KM
    above = np.maximum(height - sea_level, 0.0)
    h_coarse = np.maximum(np.asarray(view.field("height_above_sea"), dtype=np.float64), 0.0)
    t = np.asarray(view.field("surface_temperature"), dtype=np.float64)
    temperature = smooth((t + lapse * h_coarse[None, :]).T).T - lapse * above[None, :]
    temperature = np.stack([temperature[m] + (t[m][inner] - coarse_mean(temperature[m]))[local] for m in range(t.shape[0])])

    # rain on the slopes that face the year's wind, each coarse cell keeping its total
    radius = float(view.attrs["planet"]["radius_m"])
    pos = {int(k): i for i, k in enumerate(cells)}
    nb = fine.nbr[cells]
    has = np.array([[k >= 0 and int(k) in pos for k in r] for r in nb])
    nbi = np.where(has, [[pos.get(int(k), 0) for k in r] for r in nb], 0)
    step = (fine.xyz[cells][nbi] - fine.xyz[cells][:, None, :]) * radius            # metres, nearly in the tangent plane
    rise = np.where(has, height[nbi] - height[:, None], 0.0)
    norm = np.where(has, (step * step).sum(axis=-1), 0.0).sum(axis=1) / 2.0
    gradient = (rise[:, :, None] * step).sum(axis=1) / np.maximum(norm, 1.0)[:, None]
    wind = smooth(np.asarray(view.field("wind"), dtype=np.float64).mean(axis=0))
    toward = wind / np.maximum(np.linalg.norm(wind, axis=1, keepdims=True), 1e-9)
    facing = np.clip(1.0 + c["rain_per_windward_slope"] * (gradient * toward).sum(axis=1), c["rain_factor_limits"][0], c["rain_factor_limits"][1])
    p = np.asarray(view.field("precipitation"), dtype=np.float64)
    base = smooth(p.T).T * facing[None, :]
    rain = np.stack([base[m] * p[m][inner][local] / np.maximum(coarse_mean(base[m])[local], 1e-12) for m in range(p.shape[0])])

    # rivers: inside each coarse cell of the region, to the fine cell nearest its coarse receiver
    keep = np.isin(own[cells], region)
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
    local_q = np.where(land & ~sk, runoff[own[out_cells]] / 1000.0 * area[out_cells] * radius * radius / year, 0.0)
    stack = dr.flow_stack(recv)
    discharge = dr.accumulate(stack, recv, local_q + inflow)
    discharge = np.where(land, discharge, 0.0)

    fields = {"elevation": height[keep], "ocean_mask": sea[keep], "lake": lake[keep],
              "height_above_sea": (height - sea_level)[keep], "surface_temperature": temperature[:, keep],
              "precipitation": rain[:, keep], "river_discharge": discharge,
              "flow_receiver": np.where(recv >= 0, out_cells[np.maximum(recv, 0)], -1)}     # fine cells of the mesh, -1 for none
    return Detail(fine.level, out_cells, own[out_cells], fields, region, outlets)
