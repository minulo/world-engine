"""The wind-driven ocean on the mesh: plain functions for OceanCurrents (design, Layer 5).

  wind_stress()        the drag of the surface wind on the sea
  curl()               the vertical part of the curl of a tangent field
  edge_faces()         for each edge of the mesh, its two triangles, the one to its left first
  gyre_operator()      the Stommel balance r lap(psi) + beta d(psi)/dx = curl(tau) / rho as a sparse system on sea cells
  edge_transport()     the volume crossing each edge for a streamfunction held on cells: exactly free of divergence
  cell_velocity()      the depth-mean current at each cell for a streamfunction, k x grad(psi) / depth
  ekman_transport()    the wind-driven transport of the surface layer, with friction where the spin term vanishes
  closed_divergence()  the divergence of a transport with no flow across a coast
  upwind_heating()     the heat that a flow across the edges brings to each cell, in advective form

All lengths are in metres here: each function takes the planet radius where it needs one.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from . import operators as op


def wind_stress(wind: np.ndarray, air_density: float, drag: float) -> np.ndarray:
    """tau = rho_air C_D |U| U (N/m2), for winds of any leading shape (..., n, 3)."""
    speed = np.linalg.norm(wind, axis=-1, keepdims=True)
    return air_density * drag * speed * wind


def curl(mesh, v: np.ndarray, radius: float) -> np.ndarray:
    """k . curl(v) per metre, for a tangent field v (n, 3): minus the divergence of k x v."""
    return -op.divergence(mesh, np.cross(mesh.xyz, v)) / radius


def edge_faces(mesh) -> tuple:
    """For each edge (in the order of mesh.edge_cells), its two triangles: the first lies to the left of the edge's
    normal (on the side of k x n), the second to the right. Kept on the mesh once worked out."""
    kept = getattr(mesh, "_edge_faces", None)
    if kept is not None:
        return kept
    n = mesh.n
    key = mesh.edge_cells[:, 0].astype(np.int64) * n + mesh.edge_cells[:, 1]
    f = mesh.faces.astype(np.int64)
    sides = np.concatenate([np.stack([f[:, a], f[:, b]], axis=1) for a, b in ((0, 1), (1, 2), (2, 0))])
    owner = np.tile(np.arange(f.shape[0]), 3)
    ekey = np.minimum(sides[:, 0], sides[:, 1]) * n + np.maximum(sides[:, 0], sides[:, 1])
    edge = np.searchsorted(key, ekey)
    order = np.lexsort((owner, edge))
    edge, owner = edge[order], owner[order]
    first, second = owner[0::2], owner[1::2]                 # every edge belongs to exactly two triangles
    centre = mesh.xyz[f].mean(axis=1)
    centre /= np.linalg.norm(centre, axis=1, keepdims=True)
    mid = mesh.xyz[mesh.edge_cells[:, 0]] + mesh.xyz[mesh.edge_cells[:, 1]]
    left_dir = np.cross(mid, mesh.edge_normal)
    first_left = np.einsum("ij,ij->i", centre[first] - mid / np.linalg.norm(mid, axis=1, keepdims=True), left_dir) > 0
    left = np.where(first_left, first, second)
    right = np.where(first_left, second, first)
    out = (left, right)
    object.__setattr__(mesh, "_edge_faces", out)
    return out


def east_derivative_matrix(mesh) -> sp.csr_matrix:
    """The eastward part of the least-squares gradient as a sparse matrix (per radian)."""
    w = op._gradient_weights(mesh)
    valid = mesh.nbr >= 0
    ce = np.einsum("ikj,ij->ik", w, mesh.east) * valid
    rows = np.repeat(np.arange(mesh.n), mesh.nbr.shape[1])
    cols = np.where(valid, mesh.nbr, np.arange(mesh.n)[:, None]).ravel()
    m = sp.csr_matrix((ce.ravel(), (rows, cols)), shape=(mesh.n, mesh.n))
    return m - sp.diags(np.asarray(m.sum(axis=1)).ravel())


def gyre_operator(mesh, sea: np.ndarray, beta: np.ndarray, friction: float, radius: float) -> sp.csc_matrix:
    """The Stommel balance on the sea cells, each row integrated over its cell (m2):
        friction lap(psi) + beta d(psi)/dx = curl(tau) / rho,   psi = 0 on land.
    Rows and columns are the sea cells in increasing order."""
    idx = np.flatnonzero(sea)
    lap = op.laplacian_matrix(mesh) / (radius * radius)              # area-integrated on the unit sphere: per m2 of sphere
    area = mesh.area * radius * radius
    dx = east_derivative_matrix(mesh) / radius
    full = friction * lap * (radius * radius) + sp.diags(area * beta) @ dx
    return full.tocsr()[idx][:, idx].tocsc()


def edge_transport(mesh, psi: np.ndarray) -> np.ndarray:
    """The volume crossing each edge from its first cell to its second (m3/s), for a streamfunction psi (m3/s) held on
    cells: psi at a triangle is the mean of its three cells, and the flow across an edge is the difference of psi at
    its two ends. Around any cell the differences add up to zero, so the flow gathers nowhere."""
    left, right = edge_faces(mesh)
    at_face = psi[mesh.faces].mean(axis=1)
    return at_face[right] - at_face[left]


def cell_velocity(mesh, psi: np.ndarray, depth: float, radius: float) -> np.ndarray:
    """The depth-mean current k x grad(psi) / depth (m/s) at each cell."""
    return np.cross(mesh.xyz, op.gradient(mesh, psi) / radius) / depth


def ekman_transport(tau: np.ndarray, f: np.ndarray, friction: float, density: float, xyz: np.ndarray) -> np.ndarray:
    """The transport of the wind-driven surface layer (m2/s): the steady balance (r + f k x) M = tau / rho, so that
    M = (r tau - f k x tau) / (rho (r^2 + f^2)). Away from the equator it is the Ekman transport, at right angles to the
    wind; near the equator, where f vanishes, friction turns it toward the wind."""
    k_cross = np.cross(xyz, tau)
    return (friction * tau - f[:, None] * k_cross) / (density * (friction * friction + f * f))[:, None]


def closed_divergence(mesh, transport: np.ndarray, sea: np.ndarray, radius: float) -> np.ndarray:
    """Divergence (m/s) of a transport (m2/s per cell, (n, 3)) over the sea, with nothing crossing a coast."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    open_edge = sea[i] & sea[j]
    flux = np.where(open_edge, mesh.edge_dual * radius * np.einsum("ij,ij->i", 0.5 * (transport[i] + transport[j]), mesh.edge_normal), 0.0)
    out = np.bincount(i, weights=flux, minlength=mesh.n) - np.bincount(j, weights=flux, minlength=mesh.n)
    return np.where(sea, out / (mesh.area * radius * radius), 0.0)


def transport_across_edges(mesh, transport: np.ndarray, sea: np.ndarray, radius: float) -> np.ndarray:
    """The volume a transport (m2/s per cell) carries across each edge from its first cell to its second (m3/s), zero
    across a coast."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    q = mesh.edge_dual * radius * np.einsum("ij,ij->i", 0.5 * (transport[i] + transport[j]), mesh.edge_normal)
    return np.where(sea[i] & sea[j], q, 0.0)


def upwind_heating(mesh, q: np.ndarray, temperature: np.ndarray, radius: float) -> np.ndarray:
    """What a flow q (m3/s across each edge, first cell to second) does to the temperature of each cell, as
    K m/s: the inflowing water's temperature less the cell's own, times the volume that flows in, per square metre.
    Multiplied by density and heat capacity it is W/m2. (The advective form: a flow that gathers adds no heat.)"""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    into_j = np.maximum(q, 0.0)
    into_i = np.maximum(-q, 0.0)
    gain = np.bincount(j, weights=into_j * (temperature[i] - temperature[j]), minlength=mesh.n) + \
        np.bincount(i, weights=into_i * (temperature[j] - temperature[i]), minlength=mesh.n)
    return gain / (mesh.area * radius * radius)


def returned_from_aloft(mesh, q: np.ndarray, temperature: np.ndarray, radius: float) -> np.ndarray:
    """The other half of what a surface flow q (m3/s across each edge) does to temperature, as K m/s: air that gathers
    in a cell rises out of it, and air that spreads out of a cell is replaced from above by air that rose elsewhere.
    upwind_heating counts what flows in sideways; this counts what sinks in from above, at the mean temperature of the
    air that rose, weighted by how much rose. Together the two move heat and neither make nor destroy it: their sum
    over the planet, weighted by area, is zero (a closed overturning of one layer)."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    spreads = np.bincount(i, weights=q, minlength=mesh.n) - np.bincount(j, weights=q, minlength=mesh.n)  # out less in
    sinks, rises = np.maximum(spreads, 0.0), np.maximum(-spreads, 0.0)
    if rises.sum() <= 0.0:
        return np.zeros(mesh.n)
    aloft = float((rises * temperature).sum() / rises.sum())
    return sinks * (aloft - temperature) / (mesh.area * radius * radius)
