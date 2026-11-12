"""The made-up physics of mana on the mesh: plain functions for the fantasy layer "magic" (data/fantasy/magic.yaml).

Every rule these functions carry out is invented [INVENTED]: none is a claim about any real world. They are written
with the same finite-volume scheme as the real transport of the engine (library/operators.py: fluxes cross each side
of a cell along the line joining the two centres), so that mana is moved and kept by the same kind of arithmetic as
heat, and adds up the same way.

  edge_conductance()   the conductance of each edge for a conductivity held on cells: the two halves in series
  spreading_matrix()   the net amount that spreading carries out of each cell, as a sparse matrix
  edge_flows()         what crosses each edge by spreading, for a solved density
  through_cell()       the amount that passes through each cell, either way
  local_peaks()        the cells that hold at least as much as every neighbour
  uphill_peak()        for each cell, the peak that steps to the highest neighbour lead to
  ley_rule()           the two kinds of ley line: what a plate boundary adds to plain ground's conductivity, and the
                       share of its carrying rate at which a great river carries mana downstream
  river_carrying()     how much of a cell's mana its river hands to the cell downstream
  carrying_matrix()    what rivers carry out of each cell, net, as a sparse matrix
  fall()               how steeply a density falls across each cell
  surge()              how wild the magic runs where a fall of mana meets storms, from 0 to 1

A conductivity is in area per time (km²/yr in the fantasy layer); the mesh's lengths are on the unit sphere, and an
edge's conductance is the conductivity times the length of the side it crosses over the distance between the centres,
which is the same on any sphere. Each function says what it takes.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from . import operators as op

# The kinds of source of mana, in the order of the wellsprings' codes, and the aspect of the mana each makes [INVENTED]
KINDS = ("plate_motion", "fire", "old_ground", "life", "storms")
ASPECTS = ("deep", "ember", "elder", "verdant", "tempest")


def edge_conductance(mesh, conductivity: np.ndarray) -> np.ndarray:
    """The conductance of each edge: the two half-cells on either side in series, so that the harmonic mean of the two
    cells' conductivities crosses the edge, times the length of the side over the distance between the centres. A cell
    that conducts nothing closes all its edges."""
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



def ley_rule(sea: np.ndarray, boundary_km: np.ndarray, discharge: np.ndarray, ley: dict) -> tuple:
    """The two kinds of ley line, by the layer's rules [INVENTED, both]. Returns (boundary gain, river share).

    A plate boundary on land adds to the conductivity of plain ground the layer's gain, in units of it, fading with the
    distance from the boundary, as far as it at least doubles what plain ground conducts (a gain of at least 1): that
    far the cell lies on a plate line, and beyond it the ground is plain and the gain is 0. A great river carries mana
    downstream: the share of its full carrying rate rises from 0 at the least discharge of a ley line toward 1 with
    what the river carries above it; a cell where the share is above 0 lies on a river line. Under salt water there is
    no ley line: both are zero at sea."""
    gain = ley["boundary_gain"] * np.exp(-boundary_km / ley["boundary_width_km"])
    boundary = np.where(sea | (gain < 1), 0.0, gain)
    above = np.maximum(discharge - ley["river_from_m3_s"], 0.0)
    river = np.where(sea, 0.0, above / (above + ley["river_half_discharge_m3_s"]))
    return boundary, river


def river_carrying(mesh, receiver: np.ndarray, rate_per_year: np.ndarray, strip_km: float, area_km2: np.ndarray,
                   radius_km: float) -> np.ndarray:
    """How much of a cell's mana its river hands to the cell its water runs to, as an area per time (km²/yr): times the
    cell's density it is thaum/yr. The river sweeps a strip of the given width along its reach (the distance between
    the two cells' centres) at the given rate, so that a river takes the same per kilometre of its length on any mesh;
    never more than the cell's own area at that rate. A cell with no receiver (-1) hands nothing on."""
    has = receiver >= 0
    to = np.where(has, receiver, 0)
    reach_km = radius_km * np.arccos(np.clip(np.einsum("ij,ij->i", mesh.xyz, mesh.xyz[to]), -1.0, 1.0))
    return np.where(has, rate_per_year * np.minimum(strip_km * reach_km, area_km2), 0.0)


def carrying_matrix(mesh, receiver: np.ndarray, carried: np.ndarray) -> sp.csr_matrix:
    """What rivers carry out of each cell, net, as a sparse matrix: (C m)[i] = carried[i] m[i] - the sum over the cells
    j whose water runs to i of carried[j] m[j]. Every column adds up to zero: carrying moves mana downstream and
    neither makes nor destroys it."""
    n = mesh.n
    cells = np.flatnonzero((receiver >= 0) & (carried > 0))
    rows = np.concatenate([cells, receiver[cells]])
    cols = np.concatenate([cells, cells])
    vals = np.concatenate([carried[cells], -carried[cells]])
    return sp.csr_matrix((vals, (rows, cols)), shape=(n, n))


def fall(mesh, density: np.ndarray, radius_km: float) -> np.ndarray:
    """How steeply a density falls across each cell: the size of its gradient, per kilometre on a sphere of the given
    radius."""
    return np.linalg.norm(op.gradient(mesh, density), axis=1) / radius_km


def surge(fall_per_km: np.ndarray, storms: np.ndarray, fall_reference: float, storm_reference: float) -> np.ndarray:
    """How wild the magic runs, from 0 to 1, where a fall of mana meets storms [INVENTED]: 1 - exp(-(fall / its
    reference) * (storms / their reference)). No fall or no storm gives none; it nears 1 where both are several times
    their references."""
    return 1 - np.exp(-(fall_per_km / fall_reference) * (storms / storm_reference))
