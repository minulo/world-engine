"""The overturning of the ocean driven by density, on the mesh: plain functions for the second implementation of
OceanCurrents (ocean_wind_and_density.py).

  sea_water_density()     a simplified equation of state: density from temperature and salinity
  circumpolar()           the latitudes at which deep sea runs all the way round the planet
  regions()               the connected parts of the sea once those latitudes are taken out
  channel_sides()         the sides between a region and those latitudes, for the Southern Ocean's terms
  pycnocline_depth()      the depth of the light upper water, from the volume balance of Gnanadesikan 1999
  upwind_matrix()         a flow across the cell sides as a sparse matrix of what it brings to each cell
  salinity()              the sea's steady surface salinity under its freshwater balance, the flows and mixing
  branch_solver()         the prepared solver of surface_branch for one set of regions
  surface_branch()        the flow of the upper water from where the deep water rises to where it sinks
  sinking_weights()       how a region's deep water shares out among the cells that may sink
  overturn()              the overturning of every region and the salinity it leaves, worked out together
  heat()                  what the overturning does to the temperature of each cell, month by month

All lengths are in metres here: each function takes the planet radius where it needs one. A model constant reaches
these functions as an argument; none sits in their code.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import breadth_first_order, connected_components

from . import operators as op

HALF_TURN = np.pi                                  # radians: a step of longitude larger than this has gone round


def sea_water_density(temperature_k, salinity, reference_density, expansion, cabbeling, contraction, reference_k,
                      reference_salinity):
    """rho = rho0 [1 - a (T - T0) - (c / 2) (T - T0)^2 + b (S - S0)] at the surface: a straight line in salinity and
    a curve in temperature, so that cold water changes its density less with temperature than warm water does."""
    dt = np.asarray(temperature_k, dtype=np.float64) - reference_k
    return reference_density * (1.0 - expansion * dt - 0.5 * cabbeling * dt * dt
                                + contraction * (np.asarray(salinity, dtype=np.float64) - reference_salinity))


def _edges_within(mesh, members: np.ndarray) -> tuple:
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    keep = members[i] & members[j]
    return i[keep], j[keep]


def circumpolar(mesh, deep: np.ndarray, band_rad: float) -> tuple:
    """The latitudes at which the deep sea runs all the way round the planet, with no coast to stop it.

    The planet is cut into bands of latitude of the given width. In each band the deep cells are joined along the
    sides of the mesh that lie within the band, and a joined set goes round the planet when a path along it gains a
    whole turn of longitude: each cell's longitude is carried along a tree of the set, and a side of the set whose
    two ends then differ by a turn closes a loop round the pole. Returns (the band of each cell, the bands that go
    round, as a boolean per band)."""
    lat = np.arcsin(np.clip(mesh.xyz[:, 2], -1.0, 1.0))
    lon = np.arctan2(mesh.xyz[:, 1], mesh.xyz[:, 0])
    count = int(np.ceil(np.pi / band_rad))
    band = np.minimum(((lat + np.pi / 2) / band_rad).astype(np.int64), count - 1)
    goes_round = np.zeros(count, dtype=bool)
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    same = deep[i] & deep[j] & (band[i] == band[j])
    i, j = i[same], j[same]
    graph = sp.csr_matrix((np.ones(i.size), (i, j)), shape=(mesh.n, mesh.n))
    graph = graph + graph.T
    _, label = connected_components(graph, directed=False)
    step = lambda a, b: (lon[b] - lon[a] + HALF_TURN) % (2 * HALF_TURN) - HALF_TURN
    for root in np.unique(label[deep], return_index=True)[1]:
        root = int(np.flatnonzero(deep)[root])
        order, parent = breadth_first_order(graph, root, directed=False, return_predecessors=True)
        unwrapped = np.zeros(mesh.n)
        for c in order[1:]:
            unwrapped[c] = unwrapped[parent[c]] + step(parent[c], c)
        inside = label[i] == label[root]
        gap = unwrapped[i[inside]] + step(i[inside], j[inside]) - unwrapped[j[inside]]
        if gap.size and np.abs(gap).max() > HALF_TURN:
            goes_round[band[root]] = True
    return band, goes_round


def regions(mesh, sea: np.ndarray, channel: np.ndarray) -> np.ndarray:
    """The connected parts of the sea once the cells of the latitudes that go round are taken out: -1 on land and in
    those latitudes, else 0, 1, 2, ... in the order of each part's first cell."""
    keep = sea & ~channel
    i, j = _edges_within(mesh, keep)
    graph = sp.csr_matrix((np.ones(i.size), (i, j)), shape=(mesh.n, mesh.n))
    _, label = connected_components(graph + graph.T, directed=False)
    out = np.full(mesh.n, -1, dtype=np.int64)
    firsts = np.unique(label[keep], return_index=True)
    order = np.argsort(firsts[1])
    renumber = dict(zip(firsts[0][order].tolist(), range(order.size)))
    out[keep] = [renumber[k] for k in label[keep]]
    return out


def pycnocline_depth(stiffness: float, eddy_per_depth: float, ekman: float, mixing: float) -> float:
    """The depth D of the light upper water, from the balance of its volume (Gnanadesikan 1999):

        g' D^2 / eps  =  2 Kv A / D  +  Mek  -  A_I Lx D / Ly
        (sinking)        (mixing up)   (Southern wind)  (eddies)

    with stiffness = g' / eps, eddy_per_depth = A_I Lx / Ly, ekman = Mek and mixing = 2 Kv A. Multiplied out it is the
    cubic stiffness D^3 + eddy_per_depth D^2 - ekman D - mixing = 0, which has exactly one positive root while the
    mixing is positive: its coefficients change sign once, whatever the sign of the wind's term. The root is found by
    halving an interval that holds it, until the interval is as narrow as the numbers allow."""
    f = lambda d: ((stiffness * d + eddy_per_depth) * d - ekman) * d - mixing
    lo, hi = 0.0, 1.0
    while f(hi) <= 0.0:
        lo, hi = hi, 2 * hi
    while True:
        mid = 0.5 * (lo + hi)
        if mid <= lo or mid >= hi:
            return hi
        lo, hi = (mid, hi) if f(mid) <= 0.0 else (lo, mid)


def upwind_matrix(mesh, q: np.ndarray) -> sp.csr_matrix:
    """A flow q across the cell sides (m3/s, from each side's first cell to its second) as the sparse matrix M for
    which (M x)[c] is the inflowing water's value less the cell's own, times the volume flowing in: the advective
    form of upwind_heating in library/ocean.py, without the division by area."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    into_j, into_i = np.maximum(q, 0.0), np.maximum(-q, 0.0)
    rows = np.concatenate([j, j, i, i])
    cols = np.concatenate([i, j, j, i])
    vals = np.concatenate([into_j, -into_j, into_i, -into_i])
    return sp.csr_matrix((vals, (rows, cols)), shape=(mesh.n, mesh.n))


def salinity(mesh, sea: np.ndarray, flows: sp.spmatrix, mixing: np.ndarray, gain: np.ndarray, rise: np.ndarray,
             sink: np.ndarray, region: np.ndarray, mean: float) -> tuple:
    """The steady salinity of the sea's surface water (psu), and of the deep water of each region.

    For each sea cell, in psu m3/s: what the flows bring (flows @ S, an upwind matrix of divergence-free flows and of
    the overturning's surface branch), what mixing along the sides brings (mixing, m3/s per side, times the
    difference), what the rising deep water brings, rise (S_deep - S), and the salt that the freshwater balance
    leaves, gain (psu m3/s: the mean salinity times evaporation less rain and rivers). The deep water of a region
    holds the salt of the water that sinks in it: sum of sink (S - S_deep) = 0. Salt is kept: what the freshwater
    balance leaves over each connected sea is spread over it by area first, and each connected sea's mean is the
    given mean. Returns (S per cell, zero on land; S_deep per region, the mean where the region has no sinking)."""
    n = mesh.n
    sea_idx = np.flatnonzero(sea)
    i, j = _edges_within(mesh, sea)
    graph = sp.csr_matrix((np.ones(i.size), (i, j)), shape=(n, n))
    _, part = connected_components(graph + graph.T, directed=False)
    area = mesh.area
    forcing = np.where(sea, gain, 0.0)
    for p in np.unique(part[sea]):                          # salt is kept within each connected sea
        cells = sea & (part == p)
        forcing[cells] -= forcing[cells].sum() * area[cells] / area[cells].sum()
    mix = sp.csr_matrix((np.concatenate([mixing, mixing, -mixing, -mixing]),
                         (np.concatenate([i, j, i, j]), np.concatenate([j, i, i, j]))), shape=(n, n))
    regions_with_sinking = [r for r in np.unique(region[region >= 0]) if sink[region == r].sum() > 0]
    k = len(regions_with_sinking)
    deep_of = {r: n + a for a, r in enumerate(regions_with_sinking)}
    rows, cols, vals = [], [], []
    for r in regions_with_sinking:
        cells = np.flatnonzero(region == r)
        up = cells[rise[cells] != 0]
        rows += [up, up]; cols += [np.full(up.size, deep_of[r]), up]; vals += [rise[up], -rise[up]]
        down = cells[sink[cells] > 0]
        rows += [np.full(down.size, deep_of[r]), np.full(down.size, deep_of[r])]
        cols += [down, np.full(down.size, deep_of[r])]; vals += [sink[down], -sink[down]]
    rows, cols, vals = (np.concatenate(x) if x else np.zeros(0, dtype=t) for x, t in ((rows, int), (cols, int), (vals, float)))
    extra = sp.csr_matrix((vals, (rows, cols)), shape=(n + k, n + k))
    full = sp.bmat([[flows + mix, None], [None, sp.csr_matrix((k, k))]], format="csr") + extra
    keep = np.concatenate([sea_idx, n + np.arange(k)])
    system = full[keep][:, keep]
    rhs = -np.concatenate([forcing[sea_idx], np.zeros(k)])
    held = np.zeros(keep.size)                              # one value held in each connected sea: the rest follow,
    held[[int(np.flatnonzero(part[sea_idx] == p)[0]) for p in np.unique(part[sea])]] = 1.0     # their sum being kept
    rhs[held > 0] = 0.0
    system = sp.diags(1.0 - held) @ system + sp.diags(held)
    solved = spla.splu(system.tocsc()).solve(rhs)
    out = np.zeros(n)
    out[sea_idx] = solved[:sea_idx.size]
    deep = np.full(int(region.max()) + 1 if (region >= 0).any() else 0, mean)
    shifts = {}
    for p in np.unique(part[sea]):
        cells = sea & (part == p)
        shifts[p] = mean - (out[cells] * area[cells]).sum() / area[cells].sum()
        out[cells] += shifts[p]
    for a, r in enumerate(regions_with_sinking):
        deep[r] = solved[sea_idx.size + a] + shifts[part[np.flatnonzero(region == r)[0]]]
    return out, deep


def branch_solver(mesh, region: np.ndarray):
    """The prepared solver of surface_branch for one set of regions: the mesh's graph Laplacian over the sides that
    join two cells of the same region, so that no flow leaves a region."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    inside = ((region[i] == region[j]) & (region[i] >= 0)).astype(np.float64)
    return op.potential_solver(op.weighted_laplacian_matrix(mesh, inside), mesh.area), inside


def surface_branch(mesh, rise: np.ndarray, sink: np.ndarray, solver) -> tuple:
    """The flow of the upper water from where the deep water rises to where it sinks (m3/s across each side, from its
    first cell to its second), a potential flow within each region: the flow out of each cell less the flow in is
    what rises in it less what sinks in it. The prepared solver holds the potential's mean by a small shift
    (operators.potential_solver), which leaves that balance out by about a part in ten million; the rise is therefore
    given back as the flow makes it, so that the water's books close to rounding. Returns (the flow across each side,
    the potential per cell, the rise in each cell that the flow and the sinking balance exactly)."""
    lap_solver, inside = solver
    chi = lap_solver.solve(sink - rise)
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    q = inside * (mesh.edge_dual / mesh.edge_dist) * (chi[i] - chi[j])
    out_less_in = np.bincount(i, weights=q, minlength=mesh.n) - np.bincount(j, weights=q, minlength=mesh.n)
    return q, chi, out_less_in + sink


def sinking_weights(density: np.ndarray, area: np.ndarray, contrast: float) -> np.ndarray:
    """How the deep water of one region shares out among the cells that may sink: in proportion to each cell's area,
    times a share that falls by a factor e for every contrast by which its water is lighter than the region's densest.
    Two places of equal density share equally, and a place a little lighter than another gets a little less, not
    nothing, so that the sinking moves smoothly as the densities change. Cells that may not sink carry -inf."""
    able = np.isfinite(density)
    top = density[able].max()
    return np.where(able, area * np.exp((np.where(able, density, top) - top) / contrast), 0.0)


def channel_sides(mesh, sea: np.ndarray, band: np.ndarray, goes_round: np.ndarray, region: np.ndarray, band_rad: float,
                  radius: float) -> dict:
    """The sides between a region and a latitude that goes round, for the Southern Ocean's terms of Gnanadesikan 1999:
    for each such side its index, the cell on the region's side, +1 where that cell is the side's second cell (-1
    where it is the first), its east-west length (m), and the north-south width (m) of the run of bands that go round to which
    the cell on the other side belongs."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    channel = sea & goes_round[band]
    side = (sea[i] & sea[j]) & ((channel[i] & (region[j] >= 0)) | (channel[j] & (region[i] >= 0)))
    e = np.flatnonzero(side)
    second_inside = region[j[e]] >= 0
    inner = np.where(second_inside, j[e], i[e])
    outer = np.where(second_inside, i[e], j[e])
    run = np.zeros(goes_round.size, dtype=np.int64)          # the length, in bands, of the run each band belongs to
    k = 0
    while k < goes_round.size:
        end = k
        if goes_round[k]:
            while end + 1 < goes_round.size and goes_round[end + 1]:
                end += 1
            run[k:end + 1] = end - k + 1
        k = end + 1
    facing = np.abs(np.einsum("ij,ij->i", mesh.edge_normal[e], mesh.north[inner]))      # a zigzag border counts its
    return {"edge": e, "cell": inner, "sign": np.where(second_inside, 1.0, -1.0),         # east-west length only
            "length_m": mesh.edge_dual[e] * radius * facing, "width_m": run[band[outer]] * band_rad * radius}


def overturn(mesh, c, *, sea, deep, region, sides, water_k, open_months, gain, loops_q, ekman_q, spin_abs, gravity,
             radius, solver, start=None) -> dict:
    """The overturning of every region, with the salinity it leaves, worked out in passes: the salinity under the
    freshwater balance, the wind's loops and mixing; the density it gives; where the deep water forms and how much;
    then the salinity again with the overturning's own flow, and so on, a set number of times.

    c holds the constants (models.yaml, OceanCurrents.constants.overturning). water_k (months, n) is the sea's
    temperature, held at or above the freezing point of sea water; open_months (months, n) is True where less than
    half of a cell lies under ice; gain (n) is the salt that the freshwater balance leaves (psu m3/s); loops_q and
    ekman_q are the wind's loops and its surface drift across each side (m3/s); spin_abs (n) is |f|, held off zero
    near the equator; solver is branch_solver's for these regions. start, where given, is the salinity the passes
    begin from (the last round's); without it they begin from the salinity of a sea with no overturning.

    In each region the deep water forms in its densest open water that lies over deep sea (sinking_weights, by each
    cell's densest open month). How much forms follows the balance of Gnanadesikan 1999 (pycnocline_depth): the sinking
    g' D^2 / eps, with g' from the sinking water's density over the mean density of the region's surface water and
    eps a set multiple of |f| where the water sinks, is fed by mixing over the region's whole area and, where the
    region borders a latitude that goes round, by the wind's drift across that border less the eddies' return."""
    area = mesh.area
    area_m2 = area * radius * radius
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    eos = (c["reference_density_kg_m3"], c["thermal_expansion_per_k"], c["cabbeling_per_k2"], c["haline_contraction_per_psu"],
           c["reference_temperature_k"], c["mean_salinity_psu"])
    loop_flows = c["loop_share"] * upwind_matrix(mesh, loops_q)
    joined = sea[i] & sea[j]
    mixing = (c["salt_mixing_m2_s"] * c["salt_layer_m"] * mesh.edge_dual / mesh.edge_dist)[joined]
    share = c["branch_share"]
    nothing = np.zeros(mesh.n)
    if start is None:                                       # from rest: the salinity of a sea without an overturning
        salt, deep_salt = salinity(mesh, sea, loop_flows, mixing, gain, nothing, nothing, region, c["mean_salinity_psu"])
    else:
        salt = np.where(sea, start, 0.0)
        deep_salt = np.full(int(region.max()) + 1 if (region >= 0).any() else 0, c["mean_salinity_psu"])
    rise, sink, q, chi, winter, rows = nothing, nothing, np.zeros(i.size), nothing, np.full(mesh.n, -np.inf), {}
    contrast, eddy = c["sinking_contrast_kg_m3"], c["eddy_diffusivity_m2_s"]
    for _ in range(int(c["passes"])):
        density = sea_water_density(water_k, salt[None, :], *eos)
        winter = np.where(open_months, density, -np.inf).max(axis=0)
        yearly = density.mean(axis=0)
        candidate = deep & (region >= 0) & np.isfinite(winter)
        rise, sink, rows = np.zeros(mesh.n), np.zeros(mesh.n), {}
        for r in np.unique(region[region >= 0]):
            cells = region == r
            here = candidate & cells
            if not here.any():
                continue
            weight = sinking_weights(np.where(here, winter, -np.inf), np.where(here, area_m2, 0.0), contrast)
            sinking_density = float((weight * np.where(here, winter, 0.0)).sum() / weight.sum())
            upper = float((yearly[cells] * area[cells]).sum() / area[cells].sum())
            reduced_gravity = gravity * (sinking_density - upper) / c["reference_density_kg_m3"]
            if reduced_gravity <= 0.0:
                continue
            resistance = c["resistance_per_spin"] * float((weight * spin_abs).sum() / weight.sum())
            pick = region[sides["cell"]] == r
            ekman_in = sides["sign"][pick] * ekman_q[sides["edge"][pick]]
            reach = sides["length_m"][pick] / sides["width_m"][pick]
            mixing_up = 2 * c["vertical_diffusivity_m2_s"] * float(area_m2[cells].sum())
            d = pycnocline_depth(reduced_gravity / resistance, eddy * float(reach.sum()), float(ekman_in.sum()), mixing_up)
            net = np.bincount(sides["cell"][pick], weights=ekman_in - eddy * d * reach, minlength=mesh.n)
            from_mixing = mixing_up / d
            strength = from_mixing + float(net.sum())             # = g' D^2 / eps, to the precision of the root
            rise = rise + np.where(cells, from_mixing * area / area[cells].sum(), 0.0) + np.maximum(net, 0.0)
            sink = sink + np.maximum(-net, 0.0) + strength * weight / weight.sum()
            rows[int(r)] = {"strength_m3_s": strength, "depth_m": d, "reduced_gravity_m_s2": reduced_gravity,
                            "sinking_density_kg_m3": sinking_density, "upper_density_kg_m3": upper,
                            "from_mixing_m3_s": from_mixing, "southern_wind_m3_s": float(ekman_in.sum()),
                            "eddies_m3_s": float(eddy * d * reach.sum()), "resistance_per_s": resistance,
                            "sinking_cells": int((weight > 0).sum())}
        q, chi, rise = surface_branch(mesh, rise, sink, solver)
        flows = loop_flows + share * upwind_matrix(mesh, q)
        salt, deep_salt = salinity(mesh, sea, flows, mixing, gain, share * rise, share * sink, region, c["mean_salinity_psu"])
    return {"salinity": salt, "deep_salinity": deep_salt, "winter_density": np.where(np.isfinite(winter), winter, np.nan),
            "rise": rise, "sink": sink, "flow": q, "potential": chi, "regions": rows}


def heat(mesh, q: np.ndarray, rise: np.ndarray, sink: np.ndarray, region: np.ndarray, water_k: np.ndarray,
         radius: float) -> np.ndarray:
    """What the overturning does to the temperature of each cell (K m/s, months by cells): the upper water flowing in
    at the temperature of the cell upstream (the advective form of library/ocean.py's upwind_heating) and the deep
    water rising at the temperature of the water that sank in its region that month. Summed over the sea, weighted
    by area, it is zero: what rises equals what sinks in each region, so the overturning moves heat and makes none."""
    area_m2 = mesh.area * radius * radius
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    into_j, into_i = np.maximum(q, 0.0), np.maximum(-q, 0.0)
    out = np.zeros(water_k.shape)
    sinking = [region == r for r in np.unique(region[(region >= 0) & (sink > 0)])]
    for m in range(water_k.shape[0]):
        t = water_k[m]
        deep = np.zeros(mesh.n)
        for cells in sinking:
            deep[cells] = (sink[cells] * t[cells]).sum() / sink[cells].sum()
        gain = np.bincount(j, weights=into_j * (t[i] - t[j]), minlength=mesh.n) + \
            np.bincount(i, weights=into_i * (t[j] - t[i]), minlength=mesh.n)
        out[m] = (gain + rise * (deep - t)) / area_m2
    return out
