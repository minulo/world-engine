"""Shared mathematics on the mesh: plain functions that any process may call (design, Layer 2).

All operators work on the unit sphere. A process converts to metres with the planet radius:
a gradient divides by the radius, a Laplacian by the radius squared.

The scheme is the usual finite-volume one for cells of this kind: fluxes cross each cell
boundary along the line joining the two cell centres. It ignores the small curvature of the
boundary segments, so results carry an error of a few parts in a thousand at the 60 km mesh
(measured in tests/test_mesh.py).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.spatial import cKDTree

from ..mesh import Mesh


def laplacian_matrix(mesh: Mesh) -> sp.csr_matrix:
    """Area-integrated Laplacian: (L f)[i] = sum over neighbours j of (dual / dist) * (f[j] - f[i])."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    c = mesh.edge_dual / mesh.edge_dist
    n = mesh.n
    rows = np.concatenate([i, j, i, j]); cols = np.concatenate([j, i, i, j])
    vals = np.concatenate([c, c, -c, -c])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def laplacian(mesh: Mesh, f: np.ndarray) -> np.ndarray:
    """Laplacian of a per-cell field on the unit sphere (per steradian)."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    flux = (mesh.edge_dual / mesh.edge_dist) * (f[..., j] - f[..., i])
    out = np.zeros(f.shape)
    if f.ndim == 1:
        out = np.bincount(i, weights=flux, minlength=mesh.n) - np.bincount(j, weights=flux, minlength=mesh.n)
    else:
        for k in range(f.shape[0]):
            out[k] = np.bincount(i, weights=flux[k], minlength=mesh.n) - np.bincount(j, weights=flux[k], minlength=mesh.n)
    return out / mesh.area


def _gradient_weights(mesh: Mesh) -> np.ndarray:
    """Per cell and neighbour, the vector c with gradient = sum of c * (f[neighbour] - f[cell]).
    A least-squares fit in the tangent plane, exact for a field that is linear there."""
    w = getattr(mesh, "_gradient_weights", None)
    if w is None:
        valid = mesh.nbr >= 0
        nb = np.where(valid, mesh.nbr, 0)
        d = mesh.xyz[nb] - mesh.xyz[:, None, :]
        d -= np.einsum("ikj,ij->ik", d, mesh.xyz)[:, :, None] * mesh.xyz[:, None, :]
        norm = np.linalg.norm(d, axis=2)
        d *= (mesh.nbr_dist / np.where(norm > 0, norm, 1.0))[:, :, None]      # arc length along the tangent direction
        dx = np.einsum("ikj,ij->ik", d, mesh.east) * valid
        dy = np.einsum("ikj,ij->ik", d, mesh.north) * valid
        sxx, sxy, syy = (dx * dx).sum(1), (dx * dy).sum(1), (dy * dy).sum(1)
        det = sxx * syy - sxy * sxy
        cx = (syy[:, None] * dx - sxy[:, None] * dy) / det[:, None]
        cy = (sxx[:, None] * dy - sxy[:, None] * dx) / det[:, None]
        w = cx[:, :, None] * mesh.east[:, None, :] + cy[:, :, None] * mesh.north[:, None, :]
        w.flags.writeable = False
        object.__setattr__(mesh, "_gradient_weights", w)
    return w


def gradient(mesh: Mesh, f: np.ndarray) -> np.ndarray:
    """Gradient of a per-cell field: tangent vectors (n, 3), per radian."""
    w = _gradient_weights(mesh)
    nb = np.where(mesh.nbr >= 0, mesh.nbr, np.arange(mesh.n)[:, None])        # a missing neighbour adds nothing
    return np.einsum("ikj,ik->ij", w, f[nb] - f[:, None])


def divergence(mesh: Mesh, v: np.ndarray) -> np.ndarray:
    """Divergence of a tangent vector field (n, 3), per radian."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    flux = mesh.edge_dual * np.einsum("ij,ij->i", 0.5 * (v[i] + v[j]), mesh.edge_normal)
    return (np.bincount(i, weights=flux, minlength=mesh.n) - np.bincount(j, weights=flux, minlength=mesh.n)) / mesh.area


def edge_normal_speed(mesh: Mesh, v: np.ndarray) -> np.ndarray:
    """Speed of a vector field across each edge, positive from the edge's first cell to its second."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    return np.einsum("ij,ij->i", 0.5 * (v[i] + v[j]), mesh.edge_normal)


def to_east_north(mesh: Mesh, v: np.ndarray):
    """East and north parts of tangent vectors (..., n, 3)."""
    return np.einsum("...ij,ij->...i", v, mesh.east), np.einsum("...ij,ij->...i", v, mesh.north)


def from_east_north(mesh: Mesh, east, north) -> np.ndarray:
    return np.asarray(east)[..., None] * mesh.east + np.asarray(north)[..., None] * mesh.north


def smooth(mesh: Mesh, f: np.ndarray, length: float, memo: dict | None = None) -> np.ndarray:
    """Smooth a field over a length (radians) by solving (1 - length**2 * Laplacian) u = f.

    One direct solve with SuperLU. The prepared solver is kept in `memo` if one is given,
    keyed by the mesh level and the length, and equals a fresh one bit for bit.
    """
    key = ("smooth", mesh.level, float(length))
    lu = memo.get(key) if memo is not None else None
    if lu is None:
        m = sp.diags(mesh.area) - (length ** 2) * laplacian_matrix(mesh)
        lu = spla.splu(m.tocsc())
        if memo is not None:
            memo[key] = lu
    return lu.solve(mesh.area * np.asarray(f, dtype=np.float64))


def area_mean(mesh: Mesh, f: np.ndarray, mask: np.ndarray | None = None) -> float:
    w = mesh.area if mask is None else mesh.area * mask
    return float((f * w).sum() / w.sum())


def nearest_cell(mesh: Mesh, points: np.ndarray, memo: dict | None = None) -> np.ndarray:
    """Cell whose centre lies nearest to each unit vector in `points`."""
    key = ("kdtree", mesh.level)
    tree = memo.get(key) if memo is not None else None
    if tree is None:
        tree = cKDTree(mesh.xyz)
        if memo is not None:
            memo[key] = tree
    return tree.query(points)[1]


def arc_distance_to_set(mesh: Mesh, members: np.ndarray):
    """For every cell, the great-circle angle to the nearest cell of the set, and that cell's number.
    Ties go to the lower cell number, because the tree is built in cell order."""
    idx = np.flatnonzero(members)
    if idx.size == 0:
        return np.full(mesh.n, np.pi), np.full(mesh.n, -1, dtype=np.int64)
    d, k = cKDTree(mesh.xyz[idx]).query(mesh.xyz)
    return 2.0 * np.arcsin(np.clip(0.5 * d, 0.0, 1.0)), idx[k]


def zonal_mean(mesh: Mesh, f: np.ndarray, band_deg: float, mask: np.ndarray | None = None):
    """Area-weighted mean of a field in latitude bands. Returns the band centres (degrees) and the means.
    A band with no cell in the mask gives NaN."""
    nb = int(round(180.0 / band_deg))
    b = np.clip(((mesh.lat + 90.0) / band_deg).astype(np.int64), 0, nb - 1)
    w = mesh.area if mask is None else mesh.area * mask
    num = np.bincount(b, weights=w * f, minlength=nb)
    den = np.bincount(b, weights=w, minlength=nb)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    return -90.0 + band_deg * (np.arange(nb) + 0.5), out
