"""The made-up physics of mana on the mesh: plain functions for the fantasy layer's process (data/fantasy/magic.yaml).

Every rule these functions carry out is invented [INVENTED]: none is a claim about any real world. They are written
with the same finite-volume scheme as the real transport of the engine (library/operators.py, library/ocean.py), so
that mana is moved, kept and lost by the same kind of arithmetic as heat and water, and adds up the same way.

  edge_conductance()   the conductance of each edge for a conductivity held on cells: the two halves in series
  spreading_matrix()   the area-integrated spreading of a density over the edges, as a sparse matrix
  upwind_matrix()      the net outflow that a flow across the edges carries out of each cell, in flux form
  downstream_matrix()  the net outflow that a hand-on along a directed graph (rivers) carries out of each cell
  edge_flows()         what crosses each edge, by spreading and by a flow, for a solved density
  through_cell()       the amount that passes through each cell, by every way it moves
  colliding()          the part of what flows into a cell from several sides whose directions cancel
  plate_across()       for each cell, the nearest other plate and how far off it lies
  local_peaks()        the cells that hold at least as much as every neighbour

Lengths are on the unit sphere where the mesh gives them, and each function says what it takes.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.spatial import cKDTree


def edge_conductance(mesh, conductivity: np.ndarray) -> np.ndarray:
    """The conductance of each edge (the unit of the conductivity, as m2/day): the two half-cells on either side in
    series, so that the harmonic mean of the two cells' conductivities crosses the edge, times the length of the edge's
    side over the distance between the centres. A cell that conducts nothing closes all its edges."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    a, b = conductivity[i], conductivity[j]
    total = a + b
    series = np.where(total > 0, 2 * a * b / np.where(total > 0, total, 1), 0.0)
    return series * mesh.edge_dual / mesh.edge_dist


def spreading_matrix(mesh, conductance: np.ndarray) -> sp.csr_matrix:
    """The net amount that spreading carries out of each cell, (S m)[i] = sum over neighbours j of g (m[i] - m[j]),
    for edge conductances g. Every column adds up to zero: spreading moves and neither makes nor destroys."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    n = mesh.n
    rows = np.concatenate([i, j, i, j])
    cols = np.concatenate([j, i, i, j])
    vals = np.concatenate([-conductance, -conductance, conductance, conductance])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def upwind_matrix(mesh, flow: np.ndarray) -> sp.csr_matrix:
    """The net amount that a flow across the edges carries out of each cell, upwind and in flux form: across an edge
    with flow q from its first cell to its second, q times the density of the first cell leaves the first and enters
    the second (and the other way round for a negative q). Every column adds up to zero: what leaves one cell enters
    another, so where the flow gathers the density gathers too."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    n = mesh.n
    forward, backward = np.maximum(flow, 0.0), np.maximum(-flow, 0.0)
    rows = np.concatenate([i, j, j, i])
    cols = np.concatenate([i, i, j, j])
    vals = np.concatenate([forward, -forward, backward, -backward])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def downstream_matrix(n: int, receiver: np.ndarray, rate: np.ndarray) -> sp.csr_matrix:
    """The net amount that a hand-on along a directed graph carries out of each cell: cell i hands rate[i] times its
    density to receiver[i] (a cell with no receiver, -1, hands on nothing). Every column adds up to zero."""
    giver = np.flatnonzero((receiver >= 0) & (rate > 0))
    taker = receiver[giver]
    rows = np.concatenate([giver, taker])
    cols = np.concatenate([giver, giver])
    vals = np.concatenate([rate[giver], -rate[giver]])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def edge_flows(mesh, density: np.ndarray, conductance: np.ndarray, flow: np.ndarray) -> tuple:
    """What crosses each edge from its first cell to its second, for a solved density: by spreading, and by a flow
    taken upwind (the same arithmetic as spreading_matrix and upwind_matrix)."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    spread = conductance * (density[i] - density[j])
    carried = np.maximum(flow, 0.0) * density[i] - np.maximum(-flow, 0.0) * density[j]
    return spread, carried


def through_cell(mesh, edge_amount: np.ndarray) -> np.ndarray:
    """The amount that passes through each cell across its edges: half the sum of what crosses its edges, either way.
    A steady stream that enters on one side and leaves on the other counts once."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    size = np.abs(edge_amount)
    return (np.bincount(i, weights=size, minlength=mesh.n) + np.bincount(j, weights=size, minlength=mesh.n)) * 0.5


def colliding(mesh, edge_amount: np.ndarray) -> np.ndarray:
    """The part of what flows into each cell whose directions cancel: the sum of the amounts that enter, less the size of
    their sum taken as vectors along the line from where each comes from. Zero where everything enters from one side;
    all of it where equal streams meet head on."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    into_j, into_i = np.maximum(edge_amount, 0.0), np.maximum(-edge_amount, 0.0)
    total = np.bincount(j, weights=into_j, minlength=mesh.n) + np.bincount(i, weights=into_i, minlength=mesh.n)
    d = mesh.edge_normal                                       # from the first cell toward the second
    vector = np.zeros((mesh.n, 3))
    for k in range(3):
        vector[:, k] = np.bincount(j, weights=into_j * d[:, k], minlength=mesh.n) - \
            np.bincount(i, weights=into_i * d[:, k], minlength=mesh.n)
    return np.maximum(total - np.linalg.norm(vector, axis=1), 0.0)


def plate_across(xyz: np.ndarray, plate: np.ndarray) -> tuple:
    """For each cell, the plate of the nearest cell that rides on another plate, and the straight-line distance to that
    cell on the unit sphere. On a planet of one plate every cell gets -1 and an infinite distance."""
    n = plate.size
    other, distance = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
    for p in np.unique(plate):
        mine, rest = np.flatnonzero(plate == p), np.flatnonzero(plate != p)
        if rest.size == 0:
            continue
        found, nearest = cKDTree(xyz[rest]).query(xyz[mine])
        other[mine], distance[mine] = plate[rest[nearest]], found
    return other, distance


def local_peaks(mesh, value: np.ndarray) -> np.ndarray:
    """True where a cell holds at least as much as each of its neighbours."""
    valid = mesh.nbr >= 0
    around = np.where(valid, value[np.where(valid, mesh.nbr, 0)], -np.inf)
    return value >= around.max(axis=1)
