"""The mesh: an icosahedral division of the unit sphere into cells.

Design, Layer 1. Start from a solid with 20 triangular faces, split each face into four
`level` times, and push every corner onto the sphere. Each corner owns the patch of
surface nearest to it, and that patch is one cell. A level gives 10 * 4**level + 2 cells:
all six-sided except twelve five-sided ones.

Everything here is on the unit sphere. Lengths are in radians and areas in steradians;
a process multiplies by the planet radius where it needs metres.

Two properties matter to the rest of the engine:
  * the build is whole-array arithmetic in a fixed order, so the same level always gives
    the same bits;
  * the cells of level k are the first cells of level k + 1, so meshes nest.
"""
from __future__ import annotations

import numpy as np

LEVEL_MAX = 9


def cell_count(level: int) -> int:
    return 10 * 4 ** level + 2


def _normalise(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _triangle_area(a, b, c):
    """Area of spherical triangles with unit-vector corners (Van Oosterom and Strackee)."""
    num = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
    den = 1.0 + np.einsum("ij,ij->i", a, b) + np.einsum("ij,ij->i", b, c) + np.einsum("ij,ij->i", c, a)
    return 2.0 * np.arctan2(num, den)


def _arc(a, b):
    """Great-circle angle between unit vectors, accurate for small angles."""
    return 2.0 * np.arcsin(np.clip(0.5 * np.linalg.norm(a - b, axis=-1), 0.0, 1.0))


def _base_icosahedron():
    """Twelve corners with one at each pole, and twenty faces wound counter-clockwise from outside."""
    lat = np.arctan(0.5)
    pts = [(0.0, 0.0, 1.0)]
    for k in range(5):
        lon = np.deg2rad(72.0 * k)
        pts.append((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))
    for k in range(5):
        lon = np.deg2rad(36.0 + 72.0 * k)
        pts.append((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), -np.sin(lat)))
    pts.append((0.0, 0.0, -1.0))
    faces = []
    for k in range(5):
        a, b = 1 + k, 1 + (k + 1) % 5          # upper ring
        c, d = 6 + k, 6 + (k + 1) % 5          # lower ring; c lies between a and b in longitude
        faces.append((0, a, b))
        faces.append((a, c, b))
        faces.append((b, c, d))
        faces.append((11, d, c))
    return _normalise(np.array(pts, dtype=np.float64)), np.array(faces, dtype=np.int64)


def _subdivide(xyz, faces):
    n = xyz.shape[0]
    a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
    lo = np.concatenate([np.minimum(a, b), np.minimum(b, c), np.minimum(c, a)])
    hi = np.concatenate([np.maximum(a, b), np.maximum(b, c), np.maximum(c, a)])
    key = lo * n + hi
    uniq, inverse = np.unique(key, return_inverse=True)        # sorted, so the numbering never varies
    mid = _normalise(xyz[uniq // n] + xyz[uniq % n])
    m = inverse.reshape(3, -1) + n
    ab, bc, ca = m[0], m[1], m[2]
    new_faces = np.concatenate([
        np.stack([a, ab, ca], axis=1), np.stack([b, bc, ab], axis=1),
        np.stack([c, ca, bc], axis=1), np.stack([ab, bc, ca], axis=1)])
    return np.concatenate([xyz, mid]), new_faces


class Mesh:
    """Read-only geometry of one mesh level on the unit sphere.

    xyz            (n, 3)  cell centres, unit vectors
    lat, lon       (n,)    degrees; longitude in (-180, 180]
    east, north    (n, 3)  local unit vectors (at the two pole cells the pair is fixed by convention)
    area           (n,)    cell area in steradians; the areas add up to 4 pi
    nbr            (n, 6)  neighbour cells, counter-clockwise seen from outside, padded with -1
    nbr_count      (n,)    5 or 6
    nbr_edge       (n, 6)  index of the edge shared with each neighbour, padded with -1
    edge_cells     (e, 2)  the two cells of each edge, lower number first
    edge_dual      (e,)    length of the cell boundary crossed by the edge (radians)
    edge_dist      (e,)    distance between the two cell centres (radians)
    edge_normal    (e, 3)  unit vector at the edge midpoint, pointing from the first cell to the second
    faces          (f, 3)  the triangles whose corners are cell centres (used by the viewer)
    """

    def __init__(self, level: int):
        if not (0 <= level <= LEVEL_MAX):
            raise ValueError(f"mesh level {level} is outside 0 to {LEVEL_MAX}")
        xyz, faces = _base_icosahedron()
        for _ in range(level):
            xyz, faces = _subdivide(xyz, faces)
        n = xyz.shape[0]
        assert n == cell_count(level)
        self.level, self.n = level, n
        self.xyz, self.faces = xyz, faces

        a, b, c = xyz[faces[:, 0]], xyz[faces[:, 1]], xyz[faces[:, 2]]
        cc = _normalise(np.cross(b - a, c - a))                 # circumcentre of each triangle
        cc *= np.sign(np.einsum("ij,ij->i", cc, a))[:, None]

        # edges, each with the two triangles beside it
        fa, fb, fc = faces[:, 0], faces[:, 1], faces[:, 2]
        lo = np.concatenate([np.minimum(fa, fb), np.minimum(fb, fc), np.minimum(fc, fa)])
        hi = np.concatenate([np.maximum(fa, fb), np.maximum(fb, fc), np.maximum(fc, fa)])
        fidx = np.tile(np.arange(faces.shape[0]), 3)
        key = lo * n + hi
        order = np.lexsort((fidx, key))                          # by edge, then by triangle number
        key, fidx = key[order], fidx[order]
        assert key.size % 2 == 0 and np.all(key[0::2] == key[1::2])
        e_lo, e_hi = key[0::2] // n, key[0::2] % n
        f1, f2 = fidx[0::2], fidx[1::2]
        self.edge_cells = np.stack([e_lo, e_hi], axis=1).astype(np.int32)
        self.edge_dual = _arc(cc[f1], cc[f2])
        self.edge_dist = _arc(xyz[e_lo], xyz[e_hi])
        self.edge_normal = _normalise(xyz[e_hi] - xyz[e_lo])
        ne = e_lo.size

        # cell areas: each triangle gives each of its corners the kite (corner, midpoint, circumcentre, midpoint)
        area = np.zeros(n)
        for p, q, r in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
            v, vq, vr = xyz[faces[:, p]], xyz[faces[:, q]], xyz[faces[:, r]]
            m1, m2 = _normalise(v + vq), _normalise(v + vr)
            area += np.bincount(faces[:, p], weights=_triangle_area(v, m1, cc) + _triangle_area(v, cc, m2), minlength=n)
        self.area = area

        # local directions
        z = np.array([0.0, 0.0, 1.0])
        east = np.cross(z, xyz)
        norm = np.linalg.norm(east, axis=1)
        pole = norm < 1e-12
        east[pole] = np.array([0.0, 1.0, 0.0])                   # convention at the two pole cells
        east = _normalise(east)
        self.east, self.north = east, np.cross(xyz, east)
        self.lat = np.rad2deg(np.arcsin(np.clip(xyz[:, 2], -1.0, 1.0)))
        lon = np.rad2deg(np.arctan2(xyz[:, 1], xyz[:, 0]))
        lon[pole] = 0.0
        self.lon = lon

        # neighbour lists, counter-clockwise
        src = np.concatenate([e_lo, e_hi]); dst = np.concatenate([e_hi, e_lo])
        eid = np.concatenate([np.arange(ne), np.arange(ne)])
        d = xyz[dst] - xyz[src]
        ang = np.arctan2(np.einsum("ij,ij->i", d, self.north[src]), np.einsum("ij,ij->i", d, east[src]))
        order = np.lexsort((ang, src))
        src, dst, eid = src[order], dst[order], eid[order]
        count = np.bincount(src, minlength=n)
        start = np.concatenate([[0], np.cumsum(count)[:-1]])
        slot = np.arange(src.size) - start[src]
        nbr = np.full((n, 6), -1, dtype=np.int32); nbr_edge = np.full((n, 6), -1, dtype=np.int32)
        nbr[src, slot] = dst; nbr_edge[src, slot] = eid
        self.nbr, self.nbr_edge, self.nbr_count = nbr, nbr_edge, count.astype(np.int32)
        assert int((count == 5).sum()) == 12 and int((count == 6).sum()) == n - 12

        # the same edge data laid out per cell and neighbour, for loops that walk cell by cell
        valid = nbr >= 0
        safe_e = np.where(valid, nbr_edge, 0)
        self.nbr_dual = np.where(valid, self.edge_dual[safe_e], 0.0)
        self.nbr_dist = np.where(valid, self.edge_dist[safe_e], 1.0)
        sign = np.where(self.edge_cells[safe_e, 0] == np.arange(n)[:, None], 1.0, -1.0)
        self.nbr_sign = np.where(valid, sign, 0.0)                # +1 where the edge normal points away from the cell

        self.area_spread = float(area.max() / area.min())
        for arr in (self.xyz, self.faces, self.edge_cells, self.edge_dual, self.edge_dist, self.edge_normal,
                    self.area, self.east, self.north, self.lat, self.lon, self.nbr, self.nbr_edge,
                    self.nbr_count, self.nbr_dual, self.nbr_dist, self.nbr_sign):
            arr.flags.writeable = False

    def spacing(self) -> float:
        """Mean distance between neighbouring cell centres, in radians, from the mean cell area."""
        return float(np.sqrt(self.area.mean() * 2.0 / np.sqrt(3.0)))

    def describe(self) -> dict:
        return {"level": self.level, "cells": self.n, "edges": int(self.edge_cells.shape[0]),
                "area_max_over_min": self.area_spread, "area_sum_over_4pi": float(self.area.sum() / (4 * np.pi)),
                "mean_spacing_rad": self.spacing()}


_CACHE: dict[int, Mesh] = {}


def get_mesh(level: int) -> Mesh:
    """One Mesh per level for the life of the interpreter. A cached mesh equals a fresh one bit for bit."""
    if level not in _CACHE:
        _CACHE[level] = Mesh(level)
    return _CACHE[level]
