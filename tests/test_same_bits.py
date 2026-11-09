"""The faster forms of build-speed give the bits of the forms they replaced (build-speed, in docs/BUILD_NOTES.md).

Each test keeps the replaced form here, as it stood in the code before, and compares the answers byte for byte on
inputs chosen to be hard for it: many ties, flat ground, groups with no cell, a cached solver handed a changed depth.
A world built before and after the change had the same fingerprint; these tests keep each piece honest on its own.
"""
import heapq

import numpy as np
import pytest
import scipy.sparse as sp
from numba import njit

from worldengine.library import flood, ocean as oc, operators as op, plates, transport
from worldengine.mesh import get_mesh
from worldengine.testing import Harness

R = 6.371e6


# ------------------------------------------------------------------------------------------ the replaced forms
def plain_pour(height, area, nbr, nbr_count, volume):
    """flood.pour() as plain Python with heapq, as it stood before build-speed."""
    n = height.size
    z = [float(v) for v in height]
    ar = [float(v) for v in area]
    neighbours = [[int(j) for j in nbr[i, :nbr_count[i]]] for i in range(n)]
    owner = [-1] * n
    parent, level, wet_area, heaps = [], [], [], []

    def find(b):
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]
        return b

    def new_body(cell):
        b = len(parent)
        parent.append(b); level.append(z[cell]); wet_area.append(ar[cell])
        owner[cell] = b
        heap = [(z[j], j) for j in neighbours[cell]]
        heapq.heapify(heap)
        heaps.append(heap)
        return b

    if volume <= 0.0 or n == 0:
        return np.full(n, -1, dtype=np.int64), np.zeros(0)
    stack = [new_body(int(np.argmin(height)))]
    left = float(volume)
    while left > 0.0:
        b = stack[-1]
        heap = heaps[b]
        if not heap:
            level[b] += left / wet_area[b]
            break
        zc, c = heap[0]
        if owner[c] >= 0 and find(owner[c]) == b:
            heapq.heappop(heap)
            continue
        if len(stack) > 1 and zc >= level[stack[-2]]:
            p = stack[-2]
            need = wet_area[b] * (level[p] - level[b])
            if need > left:
                level[b] += left / wet_area[b]
                break
            left -= need
            small, big = (heaps[b], heaps[p]) if len(heaps[b]) <= len(heaps[p]) else (heaps[p], heaps[b])
            for item in small:
                heapq.heappush(big, item)
            heaps[p], heaps[b] = big, []
            wet_area[p] += wet_area[b]
            parent[b] = p
            stack.pop()
            continue
        heapq.heappop(heap)
        if owner[c] >= 0:
            continue
        if zc >= level[b]:
            need = wet_area[b] * (zc - level[b])
            if need > left:
                level[b] += left / wet_area[b]
                break
            left -= need
            level[b] = zc
            owner[c] = b
            wet_area[b] += ar[c]
            for j in neighbours[c]:
                if owner[j] < 0 or find(owner[j]) != b:
                    heapq.heappush(heap, (z[j], j))
        else:
            heapq.heappush(heap, (zc, c))
            q = c
            while True:
                best = q
                for j in neighbours[q]:
                    if owner[j] < 0 and (z[j], j) < (z[best], best):
                        best = j
                if best == q:
                    break
                q = best
            stack.append(new_body(q))
    body = np.array([find(o) if o >= 0 else -1 for o in owner], dtype=np.int64)
    return body, np.array(level)


def plain_barriers(height, nbr, nbr_count, source, source_level):
    """flood.barriers() as plain Python with heapq, as it stood before build-speed."""
    n = height.size
    z = [float(v) for v in height]
    neighbours = [[int(j) for j in nbr[i, :nbr_count[i]]] for i in range(n)]
    reach = [None] * n
    barrier = [-1] * n
    heap = []
    for i in np.flatnonzero(source):
        reach[int(i)] = float(source_level)
        heap.append((float(source_level), int(i)))
    heapq.heapify(heap)
    while heap:
        r, i = heapq.heappop(heap)
        if r > reach[i]:
            continue
        for j in neighbours[i]:
            if z[j] > r:
                rj, bj = z[j], j
            else:
                rj, bj = r, barrier[i]
            if reach[j] is None or rj < reach[j]:
                reach[j], barrier[j] = rj, bj
                heapq.heappush(heap, (rj, j))
    return np.array([np.inf if r is None else r for r in reach]), np.array(barrier, dtype=np.int64)


def sparse_joined(cell, rows, cols, at, side, steps):
    """The joined sides of plates.boundaries() as products of sparse matrices, as they stood before build-speed."""
    n = int(max(cell.max(), at.max())) + 1
    step = sp.csr_matrix((np.ones(rows.size), (rows, cols)), shape=(cell.size, cell.size)) + sp.identity(cell.size, format="csr")
    runs = sp.csr_matrix((np.ones(cell.size), (cell, np.arange(cell.size))), shape=(n, cell.size))
    for _ in range(steps):
        runs = runs @ step
        runs.data[:] = 1.0
    return np.asarray(runs[at, side]).ravel() > 0


def plain_returned_from_aloft(mesh, q, temperature, radius, solver):
    """ocean.returned_from_aloft() as it stood before build-speed, with its loop in plain Python."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    spreads = np.bincount(i, weights=q, minlength=mesh.n) - np.bincount(j, weights=q, minlength=mesh.n)
    sinks, rises = np.maximum(spreads, 0.0), np.maximum(-spreads, 0.0)
    if rises.sum() <= 0.0:
        return np.zeros(mesh.n)
    sources = rises - sinks
    sources[0] = 0.0
    chi = solver.solve(sources)
    aloft_q = (mesh.edge_dual / mesh.edge_dist) * (chi[i] - chi[j])
    upstream, downstream = np.where(aloft_q > 0, i, j), np.where(aloft_q > 0, j, i)
    flow = np.abs(aloft_q)
    temperature = np.asarray(temperature, dtype=np.float64)
    incoming = [[] for _ in range(mesh.n)]
    for e in range(flow.size):
        incoming[downstream[e]].append(e)
    aloft = temperature.copy()
    for c in np.argsort(-chi, kind="stable"):
        mass = rises[c]
        heat = rises[c] * temperature[c]
        for e in incoming[c]:
            mass += flow[e]
            heat += flow[e] * aloft[upstream[e]]
        if mass > 0.0:
            aloft[c] = heat / mass
    return sinks * (aloft - temperature) / (mesh.area * radius * radius)


@njit(cache=True)
def plain_sweep(w, nbr, nbr_count, out_coef, in_coef, mix_own, mix_other, area, evap_coef, w_sat, rain_scale, rain_steepness,
                rain_humidity, lift_coef, source, extra, orders, cycles, newton_steps, newton_tolerance):
    """transport.sweep() as it stood before build-speed: every sum over the sides worked out in every visit."""
    n = w.shape[0]
    change = 0.0
    for _ in range(cycles):
        change = 0.0
        for s in range(orders.shape[0]):
            for idx in range(n):
                i = orders[s, idx]
                gain = area[i] * source[i] + extra[i]
                loss = 0.0
                for k in range(nbr_count[i]):
                    j = nbr[i, k]
                    gain += (in_coef[i, k] + mix_other[i, k]) * w[j]
                    loss += out_coef[i, k] + mix_own[i, k]
                x = w[i]
                in_dry_air = rain_scale[i] * np.exp(-rain_steepness * rain_humidity[i])
                for _n in range(newton_steps):
                    humidity = x / w_sat[i]
                    if humidity <= 1.0:
                        grown = rain_scale[i] * np.exp(rain_steepness * (humidity - rain_humidity[i]))
                        wet = grown - in_dry_air
                        wet_slope = grown * rain_steepness / w_sat[i]
                        dry = evap_coef[i] * (1.0 - humidity)
                        dry_slope = -evap_coef[i] / w_sat[i]
                    else:
                        top = rain_scale[i] * np.exp(rain_steepness * (1.0 - rain_humidity[i]))
                        wet = top * (1.0 + rain_steepness * (humidity - 1.0)) - in_dry_air
                        wet_slope = top * rain_steepness / w_sat[i]
                        dry = 0.0
                        dry_slope = 0.0
                    f = loss * x + area[i] * (wet + lift_coef[i] * x * x / w_sat[i] - dry) - gain
                    slope = loss + area[i] * (wet_slope + 2.0 * lift_coef[i] * x / w_sat[i] - dry_slope)
                    step = f / slope
                    x -= step
                    if x < 0.0:
                        x = 0.0
                    if abs(step) < newton_tolerance:
                        break
                d = abs(x - w[i])
                if d > change:
                    change = d
                w[i] = x
    return change


@njit(cache=True)
def plain_residual(w, nbr, nbr_count, out_coef, in_coef, mix_own, mix_other, area, evap_coef, w_sat, rain_scale, rain_steepness,
                   rain_humidity, lift_coef, source, extra):
    """transport.residual() as it stood before build-speed."""
    n = w.shape[0]
    r = np.empty(n)
    for i in range(n):
        gain = area[i] * source[i] + extra[i]
        loss = 0.0
        for k in range(nbr_count[i]):
            j = nbr[i, k]
            gain += (in_coef[i, k] + mix_other[i, k]) * w[j]
            loss += out_coef[i, k] + mix_own[i, k]
        x = w[i]
        humidity = x / w_sat[i]
        in_dry_air = rain_scale[i] * np.exp(-rain_steepness * rain_humidity[i])
        if humidity <= 1.0:
            wet = rain_scale[i] * np.exp(rain_steepness * (humidity - rain_humidity[i])) - in_dry_air
            dry = evap_coef[i] * (1.0 - humidity)
        else:
            wet = rain_scale[i] * np.exp(rain_steepness * (1.0 - rain_humidity[i])) * (1.0 + rain_steepness * (humidity - 1.0)) - in_dry_air
            dry = 0.0
        r[i] = gain - loss * x - area[i] * (wet + lift_coef[i] * x * x / w_sat[i] - dry)
    return r


class PlainLadder(transport.Ladder):
    """The ladder with the sweeps of before build-speed."""

    def __init__(self, meshes, coefficients):
        self.meshes, self.co = meshes, coefficients

    def _sweep(self, k, w, extra, cycles, steps, newton_tolerance):
        c = self.co[k]
        return plain_sweep(w, *c[:-1], extra, c[-1], cycles, steps, newton_tolerance)

    def _residual(self, k, w, extra):
        return plain_residual(w, *self.co[k][:-1], extra)


def same(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


# ------------------------------------------------------------------------------------------ SeaLevel
def heights(kind, m, rng):
    if kind == "rough":
        return rng.normal(0.0, 1000.0, m.n)
    if kind == "terraced":                                   # many cells of exactly one height: ties everywhere
        return np.round(rng.normal(0.0, 3.0, m.n)) * 100.0
    if kind == "flat":
        return np.zeros(m.n)
    return rng.normal(0.0, 1000.0, m.n).astype(np.float32).astype(np.float64)


@pytest.mark.parametrize("level", [3, 4])
@pytest.mark.parametrize("kind", ["rough", "terraced", "flat", "single"])
def test_the_compiled_pour_and_barriers_give_the_bits_of_the_plain_python(level, kind):
    m = get_mesh(level)
    rng = np.random.default_rng(level * 10 + len(kind))
    for trial in range(6):
        height = heights(kind, m, rng)
        area = (m.area * R * R).astype(np.float32) if trial % 2 else m.area * R * R
        volume = float(np.asarray(area, dtype=np.float64).sum() * [0.0, 1.0, 100.0, 700.0, 3000.0, 1e7][trial])
        body, level_ = flood.pour(height, area, m.nbr, m.nbr_count, volume)
        body0, level0 = plain_pour(height, area, m.nbr, m.nbr_count, volume)
        assert same(body, body0) and same(level_, level0)
        source = rng.random(m.n) < 0.3 if trial % 3 else height < np.median(height)
        reach, at = flood.barriers(height, m.nbr, m.nbr_count, source, float(np.median(height)))
        reach0, at0 = plain_barriers(height, m.nbr, m.nbr_count, source, float(np.median(height)))
        assert same(reach, reach0) and same(at, at0)


def test_the_distance_to_the_coast_searched_once_a_cell_is_that_of_both_full_searches():
    """SeaLevel's distance to the coast took, for every cell, the distance to the nearest wet cell and to the nearest
    dry cell, and kept one of them; now only the one kept is searched for."""
    m = get_mesh(5)
    rng = np.random.default_rng(19)
    for share in (0.001, 0.3, 0.7, 0.999):
        wet = rng.random(m.n) < share
        wet[0], wet[1] = True, False
        to_wet = op.arc_distance_to_set(m, wet)[0]
        to_dry = op.arc_distance_to_set(m, ~wet)[0]
        assert same(op.arc_distance_across(m, wet) * R, np.where(wet, to_dry, to_wet) * R)


# ------------------------------------------------------------------------------------------ Tectonics
def test_the_walk_along_joined_sides_answers_as_the_sparse_products_did():
    rng = np.random.default_rng(7)
    for trial in range(30):
        sides = int(rng.integers(1, 300))
        cell = rng.integers(0, 40, sides)
        links = int(rng.integers(0, 3 * sides))
        a, b = rng.integers(0, sides, links), rng.integers(0, sides, links)
        rows, cols = np.concatenate([a, b]).astype(np.int64), np.concatenate([b, a]).astype(np.int64)
        pairs = int(rng.integers(1, 400))
        at = cell[rng.integers(0, sides, pairs)].astype(np.int64)
        side = rng.integers(0, sides, pairs).astype(np.int64)
        for steps in (0, 1, 3, 12):
            assert np.array_equal(plates._joined_within(cell.astype(np.int64), rows, cols, at, side, steps),
                                  sparse_joined(cell, rows, cols, at, side, steps))


# ------------------------------------------------------------------------------------------ EnergyBalance
def test_the_heat_returned_from_aloft_is_the_same_with_the_paths_worked_out_once():
    m = get_mesh(4)
    rng = np.random.default_rng(5)
    wind = rng.normal(0.0, 5.0, m.n)[:, None] * m.north + rng.normal(0.0, 5.0, m.n)[:, None] * m.east
    q = oc.transport_across_edges(m, wind, np.ones(m.n, dtype=bool), R)
    solver = oc.upper_branch_solver(m)
    paths = oc.aloft_paths(m, q, solver)
    for t in (rng.normal(15.0, 10.0, m.n), 30.0 * np.cos(np.deg2rad(m.lat)) - 10.0):
        before = plain_returned_from_aloft(m, q, t, R, solver)
        assert same(oc.returned_from_aloft(m, q, t, R, solver, paths), before)
        assert same(oc.returned_from_aloft(m, q, t, R, solver), before)
    still = np.zeros(m.edge_cells.shape[0])
    assert oc.aloft_paths(m, still, solver) == () and same(oc.returned_from_aloft(m, still, t, R), np.zeros(m.n))


class KeepingHarness(Harness):
    """A harness whose processes keep what they prepared from one run to the next, as within a climate run."""
    kept: dict = {}

    @property
    def memo(self):
        return self.kept

    @memo.setter
    def memo(self, value):
        pass


def test_a_solver_kept_from_an_earlier_round_gives_the_bits_of_a_fresh_one():
    """EnergyBalance keeps the solver of the yearly mean for the whole climate run and that of the waves while the
    stirred depth stays the same. Run after run with other depths and other constants of the matrix, what it keeps
    must answer as a fresh one does. (The sun has seasons, so that the waves and their solvers count.)"""
    m = get_mesh(3)
    rng = np.random.default_rng(11)
    months = 12
    sea = m.lat < 20
    season = np.cos(2 * np.pi * np.arange(months) / months)[:, None] * np.sin(np.deg2rad(m.lat))[None, :]
    reads = {"insolation": 300.0 + 100.0 * np.cos(np.deg2rad(m.lat))[None, :] + 150.0 * season,
             "albedo": np.full((months, m.n), 0.3), "ocean_mask": sea, "height_above_sea": np.where(sea, 0.0, 500.0),
             "cell_area": m.area * R * R}
    wind = np.broadcast_to(rng.normal(0.0, 3.0, m.n)[:, None] * m.east, (months, m.n, 3)).copy()
    depths = [np.full(m.n, 50.0), np.where(m.lon > 0, 80.0, 50.0), np.full(m.n, 50.0), np.full(m.n, 52.0)]
    KeepingHarness.kept = {}
    keeping = KeepingHarness(level=3)
    changed = [None, None, None, None, {"loss_per_kelvin_w_m2_k": 2.2}, {"spreading_constant_w_m2_k": 0.6}, None]
    for depth, constants in zip(depths + depths[:3], changed):
        lagged = {"wind": wind, "mixed_layer_depth": depth}
        kept = keeping.run("EnergyBalance", reads=reads, lagged=lagged, constants=constants).fields["surface_temperature"]
        fresh = Harness(level=3).run("EnergyBalance", reads=reads, lagged=lagged, constants=constants).fields["surface_temperature"]
        assert same(kept, fresh)
    assert any(isinstance(k, tuple) and k[0] == "energy balance, yearly mean" for k in KeepingHarness.kept["EnergyBalance"])


# ------------------------------------------------------------------------------------------ Moisture
def ladder_problem(rng, meshes, saturated_share):
    coefficients = []
    for msh in meshes:
        n = msh.n
        valid = msh.nbr >= 0
        sides = valid.shape[1]
        flow = rng.normal(0.0, 1e7, (n, sides)) * valid
        w_sat = rng.uniform(5.0, 60.0, n)
        idx = np.arange(n)
        orders = np.stack([np.lexsort((idx, msh.lon)), np.lexsort((idx, -msh.lon)),
                           np.lexsort((idx, msh.lat)), np.lexsort((idx, -msh.lat))]).astype(np.int64)
        coefficients.append((msh.nbr, msh.nbr_count, np.maximum(flow, 0.0), np.maximum(-flow, 0.0),
                             rng.uniform(0.0, 1e6, (n, sides)) * valid, rng.uniform(0.0, 1e6, (n, sides)) * valid,
                             msh.area * R * R, rng.uniform(0.0, 1e-4, n), w_sat, w_sat / 40.0 / 86400.0, 11.4,
                             rng.uniform(0.4, 0.7, n), rng.uniform(0.0, 1e-7, n),
                             np.where(rng.random(n) < saturated_share, rng.uniform(0.0, 1e-4, n), 0.0), orders))
    return coefficients


@pytest.mark.parametrize("saturated_share", [0.0, 0.5])
def test_the_prepared_sweeps_give_the_bits_of_the_sweeps_that_summed_in_every_visit(saturated_share):
    meshes = [get_mesh(k) for k in range(1, 5)]
    rng = np.random.default_rng(13)
    for _ in range(3):
        coefficients = ladder_problem(rng, meshes, saturated_share)
        start = np.full(meshes[0].n, 0.6)
        new = transport.Ladder(meshes, coefficients).solve(start, 2e-3, 30, 6, 20)
        old = PlainLadder(meshes, coefficients).solve(start, 2e-3, 30, 6, 20)
        assert same(new[0], old[0]) and new[1:] == old[1:]


# ------------------------------------------------------------------------------------------ Circulation
def test_the_band_means_of_all_groups_at_once_are_those_of_each_group_alone():
    m = get_mesh(4)
    rng = np.random.default_rng(17)
    f = rng.normal(280.0, 20.0, m.n)
    lon = np.rad2deg(np.arctan2(m.xyz[:, 1], m.xyz[:, 0]))
    for groups, band in ((18, 5.0), (36, 3.0), (90, 2.0)):              # 90 groups of 4 degrees: some band of each is empty
        group = np.minimum(((lon + 180.0) / (360.0 / groups)).astype(np.int64), groups - 1)
        group = np.where(group == 3, 4, group)                         # and one group holds no cell at all
        for fill in (False, True):
            centres, means = op.zonal_means_of_groups(m, f, band, group, groups, fill=fill)
            for k in range(groups):
                if not (group == k).any():
                    assert np.isnan(means[k]).all()
                    continue
                c0, m0 = op.zonal_mean(m, f, band, mask=(group == k).astype(np.float64), fill=fill)
                assert same(centres, c0) and same(means[k], m0)
