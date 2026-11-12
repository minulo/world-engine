"""The made-up physics of mana on the mesh: plain functions for the fantasy layer "magic" (data/fantasy/magic.yaml).

Every rule these functions carry out is invented [INVENTED]: none is a claim about any real world. They are written
with the same finite-volume scheme as the real transport of the engine (library/operators.py: fluxes cross each side
of a cell along the line joining the two centres), so that mana is moved and kept by the same kind of arithmetic as
heat, and adds up the same way.

  edge_conductance()   the conductance of each edge for a conductivity held on cells: the two halves in series
  reach_conductance()  the conductance that running water adds to the edge from each cell to the cell its water runs to
  spreading_matrix()   the net amount that spreading carries out of each cell, as a sparse matrix
  edge_flows()         what crosses each edge by spreading, for a solved density
  through_cell()       the amount that passes through each cell, either way
  local_peaks()        the cells that hold at least as much as every neighbour
  uphill_peak()        for each cell, the peak that steps to the highest neighbour lead to

A conductivity is in area per time (km²/yr in the fantasy layer); the mesh's lengths are on the unit sphere, and an
edge's conductance is the conductivity times the length of the side it crosses over the distance between the centres,
which is the same on any sphere. Each function says what it takes.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp


def edge_conductance(mesh, conductivity: np.ndarray) -> np.ndarray:
    """The conductance of each edge: the two half-cells on either side in series, so that the harmonic mean of the two
    cells' conductivities crosses the edge, times the length of the side over the distance between the centres. A cell
    that conducts nothing closes all its edges."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    a, b = conductivity[i], conductivity[j]
    total = a + b
    series = np.where(total > 0, 2 * a * b / np.where(total > 0, total, 1), 0.0)
    return series * mesh.edge_dual / mesh.edge_dist


def reach_conductance(mesh, receiver: np.ndarray, conductivity: np.ndarray) -> np.ndarray:
    """The conductance added along each reach of a river: cell i passes conductivity[i] to the edge it shares with
    receiver[i], times that edge's side over its length. A cell with no receiver (-1), or with one that is not a
    neighbour, adds nothing. Returns one value per edge."""
    out = np.zeros(mesh.edge_cells.shape[0])
    valid = mesh.nbr >= 0
    hits = valid & (mesh.nbr == receiver[:, None]) & (receiver[:, None] >= 0)
    cell, slot = np.nonzero(hits)
    edge = mesh.nbr_edge[cell, slot]
    np.add.at(out, edge, conductivity[cell] * mesh.edge_dual[edge] / mesh.edge_dist[edge])
    return out


def spreading_matrix(mesh, conductance: np.ndarray) -> sp.csr_matrix:
    """The net amount that spreading carries out of each cell, (S m)[i] = sum over neighbours j of g (m[i] - m[j]),
    for edge conductances g. Every column adds up to zero: spreading moves and neither makes nor destroys."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    n = mesh.n
    rows = np.concatenate([i, j, i, j])
    cols = np.concatenate([j, i, i, j])
    vals = np.concatenate([-conductance, -conductance, conductance, conductance])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def edge_flows(mesh, density: np.ndarray, conductance: np.ndarray) -> np.ndarray:
    """What spreading carries across each edge from its first cell to its second, for a solved density (the same
    arithmetic as spreading_matrix)."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    return conductance * (density[i] - density[j])


def through_cell(mesh, edge_amount: np.ndarray) -> np.ndarray:
    """The amount that passes through each cell across its edges: half the sum of what crosses its edges, either way.
    A steady stream that enters on one side and leaves on the other counts once."""
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    size = np.abs(edge_amount)
    return (np.bincount(i, weights=size, minlength=mesh.n) + np.bincount(j, weights=size, minlength=mesh.n)) * 0.5


def local_peaks(mesh, value: np.ndarray) -> np.ndarray:
    """True where a cell holds at least as much as each of its neighbours."""
    valid = mesh.nbr >= 0
    around = np.where(valid, value[np.where(valid, mesh.nbr, 0)], -np.inf)
    return value >= around.max(axis=1)


def uphill_peak(mesh, value: np.ndarray) -> np.ndarray:
    """For each cell, the cell that steps to the highest neighbour lead to: from a cell, step to its highest neighbour
    if that holds more than the cell, and go on until no neighbour holds more. A cell that holds at least as much as
    every neighbour is its own peak. Of two equally high neighbours the first in the mesh's list is taken, so the
    answer never varies."""
    n = mesh.n
    valid = mesh.nbr >= 0
    around = np.where(valid, value[np.where(valid, mesh.nbr, 0)], -np.inf)
    best = np.argmax(around, axis=1)
    rows = np.arange(n)
    step = np.where(around[rows, best] > value, mesh.nbr[rows, best], rows)
    while True:                                        # pointer jumping: each pass doubles the length of path covered
        further = step[step]
        if np.array_equal(further, step):
            return step
        step = further
