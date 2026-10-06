"""Where water runs over the land: plain functions shared by Drainage, Hydrology and, later, FluvialErosion.

The rule (design, Layer 5, Drainage): every cell hands its water to its lowest neighbour. Water therefore
ends in the sea or at the bottom of a closed hollow, a place with no lower neighbour.

The parts:
  receivers()                the neighbour each cell drains to
  flow_stack(), accumulate(), terminal()
                             sums along the flow paths
  hollows()                  the closed hollows, how they nest, and where each one overflows: the depression
                             hierarchy of Barnes, Callaghan and Wickert 2020
  owners()                   for each cell, the hollow whose lake reaches it first as the water rises
  through_full_hollows()     the flow paths once given hollows are full: across each lake to its outlet cell,
                             and from there to the cell beyond the pass
  Ties, mesh_ties()          how exact ties are settled
  count_ties()               how many choices are ties, and what settles them

Heights here are those of the "drainage surface": the ground on land, the water surface on the sea.

Ties. Where two ways are exactly equal in height the rule of the lowest neighbour cannot choose, and the
height says nothing about which is right. Such ties are common in two places [MEASURED: docs/BUILD_NOTES.md]:
on every coast, because all cells of one sea stand at one water level and wide stretches of a sea floor
made by one rule lie at one depth; and on relief that is given in whole metres, as measured relief is.
They are settled in this order.
  1. The lower bed: the solid ground of the cell the water would run to, which differs from the drainage
     surface under the sea.
  2. The wider way: the longer boundary shared by the two cells (Ties.way, Ties.edge). [INFERRED: mine.
     It is a property of the mesh's geometry and not of the ground, so it settles a tie without claiming
     to know the ground better than the data do, and it does not change when the cells are numbered
     otherwise. mesh_ties says how the lengths are compared. What it leaves open goes to step 3, and
     that does change with the numbering unless the caller hands in an order: boundaries that are
     images of each other are exactly as wide, and level ground has no wider way out.]
  3. The order of the cells that the caller gives (Ties.rank); the cell numbers if none is given.
The same three steps settle every choice among equals in this module:
  * a cell with several equally low neighbours;
  * a hollow with several passes of exactly its height. Before the three steps the pass whose lower cell
    lies lowest is taken. Where the higher cell of the pass is the hollow's own, that lower cell is the
    far side, and the choice is where a single cell's water goes by the rule. Where the higher cell is the
    far one, the lower cell is the hollow's own, and the choice is no truer than any other [MEASURED by
    the fourth check of step 2: on Earth's relief 47 of 1,034 hollows take such a pass, across a far cell
    level with the water, where a pass of the same height led down];
  * level ground, which is drained toward its nearest way out, counted in cells, and among equally near
    ways by the three steps; a level floor with no way out drains to one of its cells, the first in the
    order of step 3, which is then the bottom of its hollow;
  * the water of a full hollow, which crosses its lake to the outlet cell by the shortest way, counted in
    cells, among equally short ways over the lowest ground, and then by steps 2 and 3.
Without `ties` only step 1 and the cell numbers decide. Nothing here varies from run to run. With the
ties of the mesh (mesh_ties) a result depends on how the cells are numbered only where bed and boundary
are both equal: where the ground repeats itself exactly across a line of symmetry of the mesh, and in
the choice of the bottom of a level floor.

Ties.passes lets a caller put an order of its own before everything else among passes of one height, and
Ties.level an order in which level ground is drained, in place of "toward its nearest way out". The
engine uses neither. The Earth harness uses both (src/earth_reference), to draw at random the choices
that the heights do not make, and so to see which of its results the relief decides and which the ties.
What no caller can change: the water of a full hollow crosses its lake by the shortest way to the outlet
cell, which decides the cells it passes and not where it leaves the lake.
"""
from __future__ import annotations

import heapq
from typing import NamedTuple

import numpy as np
from numba import njit

NO_CELL = -1                    # no receiver: a sea cell, or the bottom of a hollow
SEA = 0                         # the label of ground that drains to the sea, and row 0 of the table of hollows
SAME_PLACE = 1.0e-9             # boundary_families: two boundaries are images of each other when what places them agrees to this
CORNERS = 12                    # an icosahedron has twelve corners; a mesh keeps them as its first twelve cells (mesh.py)


class Ties(NamedTuple):
    """How exact ties are settled once the bed has failed to settle them (the module's first lines, "Ties")."""
    way: np.ndarray             # (cells, neighbours): how far the way from a cell to each neighbour is preferred; the larger wins
    edge: np.ndarray            # (pairs of neighbouring cells, in the order of the mesh's edge_cells): the same number
    rank: np.ndarray            # (cells): where even that is equal, or one cell of several must be named: the lower wins
    passes: np.ndarray | None = None    # (pairs of neighbouring cells), or none: among passes of one height the lower goes
                                        # first, before the lower cell, the bed and the width are looked at
    level: np.ndarray | None = None     # (cells), or none: level ground is drained in this order, the lower first, each cell
                                        # to a neighbour that drains already, in place of "toward its nearest way out"


def boundary_families(mesh) -> np.ndarray:
    """For each pair of neighbouring cells, the number of its family: the boundaries that are images of each other
    under the 120 turns and mirrorings that map the mesh onto itself, and are therefore exactly as long.

    A boundary is placed by the sum of the positions of its two cells. Its scalar products with the twelve corners of
    the icosahedron, put in order, are the same for every image of the boundary and for no other boundary: the three
    largest name the nearest face and the place within it. Worked out, they agree among images to about 1e-15, and
    differ between families by the spacing of the mesh, so anything between serves to tell them apart (SAME_PLACE).
    The products are rounded on two grids half a step apart and boundaries that agree on either are joined: one
    grid alone would split a family whose products lie on a rounding step."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    corners = np.asarray(mesh.xyz[:CORNERS], dtype=np.float64)       # the icosahedron's corners are the first twelve cells
    a, b = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    placed = np.sort((mesh.xyz[a] + mesh.xyz[b]) @ corners.T, axis=1) / SAME_PLACE
    _, on_one = np.unique(np.round(placed), axis=0, return_inverse=True)
    _, on_other = np.unique(np.floor(placed), axis=0, return_inverse=True)
    on_one, on_other = on_one.ravel(), on_other.ravel()
    count = int(on_one.max()) + 1
    joined = coo_matrix((np.ones(a.size), (on_one, count + on_other)), shape=(count + int(on_other.max()) + 1,) * 2)
    _, family = connected_components(joined, directed=False)
    _, family = np.unique(family[on_one], return_inverse=True)       # numbered from 0, in a fixed order
    return family.ravel().astype(np.int64)


def mesh_ties(mesh) -> Ties:
    """The ties of a mesh settled by its geometry: the wider way first, the longer boundary shared by two cells,
    and then the cell numbers.

    The mesh has boundaries that are images of each other under its symmetries and exactly as long; worked out,
    their lengths differ by the rounding errors of the geometry, up to 1e-12 of the longest boundary at level 5 and
    1.5e-11 at level 7. So lengths are not compared as worked out: every boundary takes the length of its family
    (boundary_families; the shortest worked-out length of its members), and the families are put in order of that
    length. Images of one boundary then tie exactly, on every mesh, and the order of the cells settles them.
    Two families whose lengths differ at all are told apart, by however little. On the standard mesh the two
    nearest families differ by 5e-12 of the longest boundary, less than the rounding errors inside a family, so
    which of those two counts as the longer is settled by those errors: the same way on every run and for every
    image, and with no claim to be right. [MEASURED: tests/test_water_rules.py;
    before the fourth check of step 2 the lengths were rounded to a billionth, which left 29 of the 4,160 families of
    the standard mesh split by the rounding errors, and 580 of 16,512 one level finer.]"""
    cached = getattr(mesh, "_ties_of_the_mesh", None)
    if cached is not None:
        return cached
    family = boundary_families(mesh)
    length = np.full(int(family.max()) + 1, np.inf)
    np.minimum.at(length, family, np.asarray(mesh.edge_dual, dtype=np.float64))
    _, place = np.unique(length, return_inverse=True)                # the families in order of their length
    width = place.ravel()[family].astype(np.float64)
    way = np.where(mesh.nbr >= 0, width[np.maximum(mesh.nbr_edge, 0)], -np.inf)
    ties = Ties(way=way, edge=width, rank=np.arange(mesh.n, dtype=np.int64))
    try:
        mesh._ties_of_the_mesh = ties                                # a mesh is built once and never changed
    except AttributeError:
        pass
    return ties


def count_ties(surface: np.ndarray, sea: np.ndarray, nbr: np.ndarray, bed: np.ndarray, ties: Ties) -> dict:
    """How many of the choices of receivers() are exact ties, and what settles them:
      choose     land cells with a lower neighbour: they choose a receiver
      tied       of those, the ones with several equally low neighbours
      by_bed, by_width, by_number    of the tied, how many the lower bed settles, the wider way, and the order of the cells
      level      land cells on level ground: a neighbour at their own height and none lower"""
    valid = nbr >= 0
    beside = np.where(valid, nbr, 0)
    around = np.where(valid, surface[beside], np.inf)
    lowest = around.min(axis=1)
    low = around == lowest[:, None]
    chooses = ~sea & (lowest < surface)
    under = np.where(low, bed[beside], np.inf)
    deepest = low & (under == under.min(axis=1)[:, None])
    wide = np.where(deepest, ties.way, -np.inf)
    widest = deepest & (wide == wide.max(axis=1)[:, None])
    tied, bed_left, width_left = low.sum(axis=1) > 1, deepest.sum(axis=1) > 1, widest.sum(axis=1) > 1
    return {"choose": int(chooses.sum()), "tied": int((chooses & tied).sum()), "by_bed": int((chooses & tied & ~bed_left).sum()),
            "by_width": int((chooses & bed_left & ~width_left).sum()), "by_number": int((chooses & width_left).sum()),
            "level": int((~sea & (lowest == surface)).sum())}


def _settle(ties, nbr):
    """(way, rank) of `ties`; with none, every way equal and the cell numbers for rank."""
    if ties is None:
        return np.zeros(nbr.shape), np.arange(nbr.shape[0], dtype=np.int64)
    return np.asarray(ties.way, dtype=np.float64), np.asarray(ties.rank, dtype=np.int64)


def _pick(among, height, way, rank, nbr):
    """For each row of `nbr`, one neighbour of those marked in `among`: the one of lowest `height`, then of the
    widest `way`, then of the lowest `rank` (all given per row and neighbour). A row with none marked gets any."""
    low = np.where(among, height, np.inf)
    among = among & (low == low.min(axis=1)[:, None])
    wide = np.where(among, way, -np.inf)
    among = among & (wide == wide.max(axis=1)[:, None])
    slot = np.where(among, rank, np.iinfo(np.int64).max).argmin(axis=1)
    return nbr[np.arange(nbr.shape[0]), slot].astype(np.int64)


def drainage_surface(elevation: np.ndarray, sea_depth: np.ndarray, sea: np.ndarray, sea_levels=()) -> np.ndarray:
    """The surface that water runs over: the ground on land, the water surface on the sea.

    A field is stored rounded, so ground plus depth gives each cell of one body of water a slightly different
    surface. `sea_levels` holds the exact surface of every body (the table of seas); each sea cell takes the
    nearest of them. Land that stands exactly at the level of the sea beside it then counts as level with it,
    and drains into it."""
    surface = np.asarray(elevation, dtype=np.float64).copy()
    wet = np.flatnonzero(sea)
    water = surface[wet] + np.asarray(sea_depth, dtype=np.float64)[wet]
    levels = np.sort(np.asarray(sea_levels, dtype=np.float64))
    if levels.size and wet.size:
        k = np.clip(np.searchsorted(levels, water), 1, levels.size - 1) if levels.size > 1 else np.zeros(wet.size, dtype=np.int64)
        if levels.size > 1:
            k = np.where(np.abs(water - levels[k - 1]) <= np.abs(levels[k] - water), k - 1, k)
        water = levels[k]
    surface[wet] = water
    return surface


def receivers(surface: np.ndarray, sea: np.ndarray, nbr: np.ndarray, bed: np.ndarray | None = None,
              ties: Ties | None = None) -> np.ndarray:
    """For each cell, the neighbour its water runs to; NO_CELL for a sea cell and for the bottom of a hollow.

    A cell drains to its lowest neighbour if that neighbour is lower. Among equally low neighbours the one whose
    bed lies lowest is taken (`bed`: the solid ground of every cell, which differs from `surface` under the sea),
    then the one reached by the widest way, then the first in the order of the cells (`ties`; the module's first
    lines say why). Level ground (cells with a neighbour at their own height and none lower) drains toward its
    nearest way out, a cell at the same height that does drain. Level ground with no way out is the floor of a
    hollow: it drains to one of its cells, the first in the order of the cells, which is the hollow's bottom.
    With an order of the caller's own for level ground (`ties.level`) the cells beside a way out drain as before,
    and the rest is drained in that order: of the cells that touch ground which drains already, the first in the
    order goes next, to one of those neighbours. Every cell still reaches a way out; the way need not be the nearest.
    """
    n = surface.size
    bed = surface if bed is None else np.asarray(bed, dtype=np.float64)
    way, rank = _settle(ties, nbr)
    valid = nbr >= 0
    safe = np.where(valid, nbr, 0)
    around = np.where(valid, surface[safe], np.inf)
    lowest = around.min(axis=1)
    pick = _pick(around == lowest[:, None], bed[safe], way, rank[safe], nbr)
    recv = np.where((lowest < surface) & ~sea, pick, NO_CELL)
    stuck = np.flatnonzero((recv < 0) & ~sea & (lowest == surface))
    if stuck.size == 0:
        return recv
    around_of, height, bed_of, rank_of = nbr.tolist(), surface.tolist(), bed.tolist(), rank.tolist()
    drawn = None if ties is None or ties.level is None else np.asarray(ties.level, dtype=np.float64).tolist()
    is_stuck = np.zeros(n, dtype=bool)
    is_stuck[stuck] = True
    seen = np.zeros(n, dtype=bool)

    def best(cell, among):
        """Of the neighbours of `cell` for which `among` holds: the lowest bed, the widest way, the first in order."""
        return min((bed_of[j], -way[cell, k], rank_of[j], j) for k, j in enumerate(around_of[cell]) if j >= 0 and among(j))[-1]

    for start in stuck.tolist():
        if seen[start]:
            continue
        level = height[start]
        ground = [start]                                     # the level ground this cell belongs to
        seen[start] = True
        k = 0
        while k < len(ground):
            for j in around_of[ground[k]]:
                if j >= 0 and is_stuck[j] and not seen[j] and height[j] == level:
                    seen[j] = True
                    ground.append(j)
            k += 1
        inside = set(ground)
        drains = lambda j: height[j] == level and j not in inside and (sea[j] or recv[j] >= 0)
        steps = {}                                           # cells between each cell and its way out
        for i in ground:                                     # the ways out: cells at the same height that drain
            if any(j >= 0 and drains(j) for j in around_of[i]):
                recv[i] = best(i, drains)
                steps[i] = 0
        if not steps:                                        # no way out: the floor of a hollow
            steps[min(ground, key=lambda i: rank_of[i])] = 0
        if drawn is not None:                                # the caller's order: the cell that comes first among those
            waiting = [(drawn[j], j) for i in steps for j in around_of[i] if j in inside and j not in steps]
            heapq.heapify(waiting)                           # beside ground that drains already goes next
            while waiting:
                _, j = heapq.heappop(waiting)
                if j in steps:
                    continue
                recv[j] = best(j, lambda i: i in steps)
                steps[j] = 1
                for i in around_of[j]:
                    if i in inside and i not in steps:
                        heapq.heappush(waiting, (drawn[i], i))
            continue
        edge, d = list(steps), 0
        while edge:                                          # ring by ring inward: each cell to a neighbour one ring nearer
            d += 1
            ring = {j for i in edge for j in around_of[i] if j in inside and j not in steps}
            for j in ring:
                recv[j] = best(j, lambda i: steps.get(i) == d - 1)
            for j in ring:
                steps[j] = d
            edge = list(ring)
    return recv


@njit(cache=True)
def _stack(recv):
    n = recv.size
    count = np.zeros(n + 1, dtype=np.int64)
    for i in range(n):
        if recv[i] >= 0:
            count[recv[i] + 1] += 1
    start = np.cumsum(count)
    fill = start[:-1].copy()
    donors = np.empty(n, dtype=np.int64)
    for i in range(n):
        r = recv[i]
        if r >= 0:
            donors[fill[r]] = i
            fill[r] += 1
    stack = np.empty(n, dtype=np.int64)
    todo = np.empty(n, dtype=np.int64)
    top = 0
    for i in range(n):
        if recv[i] < 0:
            todo[0] = i
            m = 1
            while m > 0:
                m -= 1
                c = todo[m]
                stack[top] = c
                top += 1
                for k in range(start[c], start[c + 1]):
                    todo[m] = donors[k]
                    m += 1
    return stack, top


def flow_stack(recv: np.ndarray) -> np.ndarray:
    """The cells in an order in which every cell comes after the cell it drains to. [UNVERIFIED: this is the
    "stack" of Braun and Willett 2013 as I recall it; the paper did not open.]"""
    stack, reached = _stack(np.ascontiguousarray(recv, dtype=np.int64))
    if reached != recv.size:
        raise ValueError("the receivers hold a loop: some cells never reach the sea or the bottom of a hollow")
    return stack


@njit(cache=True)
def _accumulate(stack, recv, values):
    total = values.copy()
    for k in range(stack.size - 1, -1, -1):
        i = stack[k]
        r = recv[i]
        if r >= 0:
            total[r] += total[i]
    return total


def accumulate(stack: np.ndarray, recv: np.ndarray, values: np.ndarray) -> np.ndarray:
    """For each cell, the sum of `values` over the cell and every cell that drains through it.
    `values` holds one number per cell, or one per month and cell. The sums are taken in the order of the stack."""
    recv = np.ascontiguousarray(recv, dtype=np.int64)
    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        return _accumulate(stack, recv, np.ascontiguousarray(values))
    return np.stack([_accumulate(stack, recv, np.ascontiguousarray(row)) for row in values])


@njit(cache=True)
def _terminal(stack, recv):
    end = np.empty(recv.size, dtype=np.int64)
    for k in range(stack.size):
        i = stack[k]
        r = recv[i]
        end[i] = i if r < 0 else end[r]
    return end


def terminal(stack: np.ndarray, recv: np.ndarray) -> np.ndarray:
    """For each cell, the cell where its water ends: a sea cell or the bottom of a hollow."""
    return _terminal(stack, np.ascontiguousarray(recv, dtype=np.int64))


HOLLOW_COLUMNS = ("parent", "sibling", "first_child", "second_child", "bottom_cell", "bottom_m", "spill_m",
                  "spill_from_cell", "spill_into_cell", "spill_into_hollow", "area_when_full_m2", "volume_when_full_m3")


def hollows(surface: np.ndarray, sea: np.ndarray, recv: np.ndarray, stack: np.ndarray, edge_cells: np.ndarray,
            area: np.ndarray, bed: np.ndarray | None = None, ties: Ties | None = None):
    """The closed hollows of the land and how they nest (Barnes, Callaghan and Wickert 2020).

    A hollow is the ground that drains to one bottom. Two neighbouring hollows meet at their lowest pass: the
    pair of neighbouring cells, one in each, whose higher cell is lowest. When both have filled to that pass they
    are one larger hollow, which fills on to its own lowest pass. Passes are taken from the lowest up, so the
    hollows form a tree of pairs; a hollow whose lowest pass leads to ground that already drains to the sea ends
    its tree, and its overflow runs on from the cell beyond the pass.

    Passes of exactly equal height are common [MEASURED: tests/test_water.py counts them on rough ground where no
    two cells tie]: when the higher cell of a pass is the hollow's own, every lower
    neighbour of that cell beyond the hollow makes a pass of that same height. Among passes of one height the
    one whose lower cell is lowest is taken, which in that case is where a cell's water goes by the rule for a
    single cell (and is no truer than another choice where the higher cell of the pass is the far one: the
    module's first lines); then the lowest bed (`bed`: the solid ground, which differs from `surface` under the
    sea), then the widest pass, then the first in the order of the cells (`ties`). An order of the caller's own
    for passes of one height (`ties.passes`) comes before all of these. Of two hollows that become one, the one
    with the lower bottom is named first; of two equally low bottoms, the first in the order of the cells.

    Returns (label, table):
      label   per cell, the number of the hollow it drains into, or SEA (0) if its water reaches the sea
      table   one row per hollow, the columns of HOLLOW_COLUMNS. Row 0 stands for the sea. Rows 1 to H are the
              hollows with one bottom each, in the order of their bottom cells; later rows are hollows made of
              two that merged. parent, sibling, first_child and second_child are rows (-1 for none);
              spill_m is the height at which the hollow overflows (missing if it has no way out at all),
              spill_from_cell the cell on its own side of the pass, spill_into_cell the cell beyond it, and
              spill_into_hollow the label of that cell. area_when_full_m2 and volume_when_full_m3 describe
              the lake that fills the hollow to its pass.
    """
    n = surface.size
    end = terminal(stack, recv)
    bottoms = np.flatnonzero((recv < 0) & ~sea)
    count = bottoms.size
    number = np.zeros(n, dtype=np.int64)
    number[bottoms] = np.arange(1, count + 1)
    label = np.where(sea[end], SEA, number[end])

    parent, sibling = [-1] * (count + 1), [-1] * (count + 1)
    first_child, second_child = [-1] * (count + 1), [-1] * (count + 1)
    spill = [np.nan] * (count + 1)
    spill_from, spill_into, into_hollow = [-1] * (count + 1), [-1] * (count + 1), [-1] * (count + 1)
    bottom_cell = [-1] + bottoms.tolist()
    bottom_height = [np.nan] + surface[bottoms].tolist()

    # The lowest pass between every two labels that touch.
    a, b = edge_cells[:, 0].astype(np.int64), edge_cells[:, 1].astype(np.int64)
    touch = label[a] != label[b]
    narrow = -(np.zeros(a.size) if ties is None else np.asarray(ties.edge, dtype=np.float64))[touch]     # the widest first
    given = None if ties is None else ties.passes                   # an order of the caller's own, before all else
    first = (np.zeros(a.size) if given is None else np.asarray(given, dtype=np.float64))[touch]
    rank = np.arange(n, dtype=np.int64) if ties is None else np.asarray(ties.rank, dtype=np.int64)
    a, b = a[touch], b[touch]
    swap = label[a] > label[b]
    a, b = np.where(swap, b, a), np.where(swap, a, b)        # the cell with the lower label first
    one, other = label[a], label[b]
    under = surface if bed is None else np.asarray(bed, dtype=np.float64)
    height = np.maximum(surface[a], surface[b])
    lower = np.minimum(surface[a], surface[b])               # among passes of one height: the lowest lower cell first
    lower_bed = np.minimum(under[a], under[b])
    early, late = np.minimum(rank[a], rank[b]), np.maximum(rank[a], rank[b])     # the order of the cells, whichever side each is on
    order = np.lexsort((late, early, narrow, lower_bed, lower, first, height, other, one))
    keys = (one, other, a, b, height, first, lower, lower_bed, narrow, early, late)
    one, other, a, b, height, first, lower, lower_bed, narrow, early, late = (v[order] for v in keys)
    lowest = np.ones(one.size, dtype=bool)
    lowest[1:] = (one[1:] != one[:-1]) | (other[1:] != other[:-1])
    keys = (one, other, a, b, height, first, lower, lower_bed, narrow, early, late)
    one, other, a, b, height, first, lower, lower_bed, narrow, early, late = (v[lowest] for v in keys)
    order = np.lexsort((late, early, narrow, lower_bed, lower, first, height))   # the passes from the lowest up

    group = list(range(count + 1))                           # which labels have merged; the sea's group keeps top 0
    top = list(range(count + 1))

    def find(x):
        while group[x] != x:
            group[x] = group[group[x]]
            x = group[x]
        return x

    for k in order.tolist():
        la, lb, ca, cb, at = int(one[k]), int(other[k]), int(a[k]), int(b[k]), float(height[k])
        ra, rb = find(la), find(lb)
        if ra == rb:
            continue
        ta, tb = top[ra], top[rb]
        if ta == SEA or tb == SEA:                           # the far side already drains to the sea
            mine, here, beyond, beyond_label, sea_group, own_group = \
                (tb, cb, ca, la, ra, rb) if ta == SEA else (ta, ca, cb, lb, rb, ra)
            spill[mine], spill_from[mine], spill_into[mine], into_hollow[mine] = at, here, beyond, beyond_label
            group[own_group] = sea_group
            continue
        both = len(parent)                                   # two hollows that fill to their pass become one
        if (bottom_height[tb], rank[bottom_cell[tb]]) < (bottom_height[ta], rank[bottom_cell[ta]]):
            deeper, shallower = tb, ta
        else:
            deeper, shallower = ta, tb
        parent.append(-1); sibling.append(-1); first_child.append(deeper); second_child.append(shallower)
        spill.append(np.nan); spill_from.append(-1); spill_into.append(-1); into_hollow.append(-1)
        bottom_cell.append(bottom_cell[deeper]); bottom_height.append(bottom_height[deeper])
        parent[ta] = parent[tb] = both
        sibling[ta], sibling[tb] = tb, ta
        spill[ta] = spill[tb] = at
        spill_from[ta], spill_into[ta], into_hollow[ta] = ca, cb, lb
        spill_from[tb], spill_into[tb], into_hollow[tb] = cb, ca, la
        group[rb] = ra
        top[ra] = both

    table = {"parent": np.array(parent, dtype=np.int32), "sibling": np.array(sibling, dtype=np.int32),
             "first_child": np.array(first_child, dtype=np.int32), "second_child": np.array(second_child, dtype=np.int32),
             "bottom_cell": np.array(bottom_cell, dtype=np.int32), "bottom_m": np.array(bottom_height, dtype=np.float64),
             "spill_m": np.array(spill, dtype=np.float64), "spill_from_cell": np.array(spill_from, dtype=np.int32),
             "spill_into_cell": np.array(spill_into, dtype=np.int32),
             "spill_into_hollow": np.array(into_hollow, dtype=np.int32)}
    # the lake that fills each hollow to its pass
    rows = len(parent)
    own = owners(surface, label, table)
    held = own >= 0
    full_area = np.bincount(own[held], weights=area[held], minlength=rows)
    full_height = np.bincount(own[held], weights=(area * surface)[held], minlength=rows)
    for k in range(count + 1, rows):                         # a merged hollow holds what its two parts hold
        full_area[k] += full_area[first_child[k]] + full_area[second_child[k]]
        full_height[k] += full_height[first_child[k]] + full_height[second_child[k]]
    level = np.where(np.isnan(table["spill_m"]), 0.0, table["spill_m"])
    table["area_when_full_m2"] = np.where(np.isnan(table["spill_m"]), np.nan, full_area)
    table["volume_when_full_m3"] = np.where(np.isnan(table["spill_m"]), np.nan, level * full_area - full_height)
    return label, table


def owners(surface: np.ndarray, label: np.ndarray, table) -> np.ndarray:
    """For each cell, the hollow whose own rise of water floods it: the smallest hollow around the cell whose pass
    lies above the cell. -1 for ground that drains to the sea and for ground that stands above every pass of the
    hollows around it. A hollow with no way out (spill_m missing) floods everything left to it."""
    parent = np.asarray(table["parent"], dtype=np.int64)
    spill = np.asarray(table["spill_m"], dtype=np.float64)
    spill = np.where(np.isnan(spill), np.inf, spill)
    node = np.where(label > SEA, label, -1).astype(np.int64)
    moving = np.flatnonzero(node >= 0)
    while moving.size:
        above = surface[moving] >= spill[node[moving]]
        moving = moving[above]
        node[moving] = parent[node[moving]]
        moving = moving[node[moving] >= 0]
    return node


def top_hollows(table) -> np.ndarray:
    """For each row of the table of hollows, the row of the largest hollow that holds it (itself if none does)."""
    parent = np.asarray(table["parent"], dtype=np.int64)
    top = np.arange(parent.size)
    for k in range(parent.size - 1, 0, -1):                  # a merged hollow has a higher row than its parts
        if parent[k] >= 0:
            top[k] = top[parent[k]]
    return top


def through_full_hollows(recv: np.ndarray, surface: np.ndarray, nbr: np.ndarray, label: np.ndarray, table, rows,
                         ties: Ties | None = None):
    """The receivers as they are when the hollows `rows` (rows of the table of hollows) are full and overflow.

    Inside each of them the ground at or below the level of its pass lies under one sheet of water. That water
    is handed on from cell to cell by the shortest way, counted in cells, to the hollow's outlet cell: the cell
    on its own side of the pass. Among equally short ways the one over the lowest ground is taken, then the
    widest, then the first in the order of the cells (`ties`; the module's first lines). The outlet cell hands
    the water to the cell beyond the pass. Ground of the hollow above that level keeps its receiver, which
    leads down into the water. [INFERRED: the engine has no model of the currents in a lake; the shortest way
    is the plainest rule that brings all the water to the outlet.]

    `rows` must hold no hollow together with one of its parts, and no hollow without a pass.
    Returns (receivers, lake): for each cell its receiver, and the row of `rows` whose sheet of water covers it
    (-1 for none).
    """
    out = np.array(recv, dtype=np.int64)
    n = out.size
    rows = np.asarray(rows, dtype=np.int64)
    lake = np.full(n, -1, dtype=np.int64)
    if rows.size == 0:
        return out, lake
    parent = np.asarray(table["parent"], dtype=np.int64)
    spill = np.asarray(table["spill_m"], dtype=np.float64)
    here = np.asarray(table["spill_from_cell"], dtype=np.int64)[rows]
    beyond = np.asarray(table["spill_into_cell"], dtype=np.int64)[rows]
    if (beyond < 0).any() or np.isnan(spill[rows]).any():
        raise ValueError("a hollow without a pass cannot overflow: it has no outlet cell to route its water to")
    inside = np.full(parent.size, -1, dtype=np.int64)        # for each row of the table, the row of `rows` that holds it
    inside[rows] = rows
    for k in range(parent.size - 1, SEA, -1):                # wholes before parts
        if inside[k] < 0 and parent[k] >= 0:
            inside[k] = inside[parent[k]]
    unit = np.where(label > SEA, inside[np.maximum(label, 0)], -1)
    under = (unit >= 0) & (surface <= spill[np.maximum(unit, 0)])
    lake[under] = unit[under]
    if (lake[here] != rows).any():
        bad = int(rows[np.flatnonzero(lake[here] != rows)[0]])
        raise ValueError(f"the table of hollows names an outlet cell for hollow {bad} that does not lie in that hollow "
                         f"at or below the level of its pass")
    steps = np.full(n, -1, dtype=np.int64)                   # cells between this one and its outlet cell
    steps[here] = 0
    edge, d = here, 0
    while edge.size:
        d += 1
        near = nbr[edge]
        safe = np.maximum(near, 0)
        new = (near >= 0) & (lake[safe] == lake[edge][:, None]) & (steps[safe] < 0)
        edge = np.unique(near[new])
        steps[edge] = d
    if (under & (steps < 0)).any():
        lost = int(np.flatnonzero(under & (steps < 0))[0])
        raise ValueError(f"cell {lost} lies under the water of hollow {int(lake[lost])} when it is full, but no way "
                         f"leads from it across that water to the hollow's outlet cell")
    cells = np.flatnonzero(under & (steps > 0))
    near = nbr[cells]
    safe = np.maximum(near, 0)
    nearer = (near >= 0) & (lake[safe] == lake[cells][:, None]) & (steps[safe] == steps[cells][:, None] - 1)
    way, rank = _settle(ties, nbr)
    out[cells] = _pick(nearer, surface[safe], way[cells], rank[safe], near)
    out[here] = beyond
    return out, lake


def overflow_receivers(recv: np.ndarray, surface: np.ndarray, nbr: np.ndarray, label: np.ndarray, table,
                       ties: Ties | None = None) -> np.ndarray:
    """The receivers as they are when every hollow is full and overflows.

    Each of the largest hollows (those inside no other) then holds one lake up to its pass, and its water runs
    across that lake to the outlet cell and on to the cell beyond the pass (through_full_hollows). Every path then
    ends in the sea. A hollow with no way out at all has no outlet: every bottom inside it hands its water to its
    deepest bottom, and the paths of its ground end there. A hollow overflows into ground whose own hollow
    overflows at a pass no higher, so the paths hold no loop."""
    parent = np.asarray(table["parent"])
    bottom = np.asarray(table["bottom_cell"])
    beyond = np.asarray(table["spill_into_cell"])
    top = top_hollows(table)
    tops = np.flatnonzero((parent < 0) & (np.arange(parent.size) > SEA))
    out, _ = through_full_hollows(recv, surface, nbr, label, table, tops[beyond[tops] >= 0], ties)
    leaves = np.flatnonzero((np.asarray(table["first_child"]) < 0) & (np.arange(parent.size) > SEA))
    shut = leaves[beyond[top[leaves]] < 0]                   # bottoms inside a hollow with no way out
    deepest = bottom[top[shut]]
    out[bottom[shut]] = np.where(bottom[shut] == deepest, NO_CELL, deepest)
    return out


def mouths(stack: np.ndarray, recv: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """For each land cell, the last land cell its water passes before it ends (in the sea, or at a bottom): the
    mouth of its river. NO_CELL for sea cells."""
    recv = np.asarray(recv, dtype=np.int64)
    on_land = np.where((recv >= 0) & sea[np.maximum(recv, 0)], NO_CELL, recv)      # stop one cell before the sea
    end = _terminal(stack, np.ascontiguousarray(on_land))
    return np.where(sea, NO_CELL, end)


@njit(cache=True)
def _largest_upstream(stack, recv, values, rank):
    best = np.full(recv.size, -np.inf)                       # the largest value among the cells upstream of each cell
    where = np.full(recv.size, -1, dtype=np.int64)
    for k in range(stack.size - 1, -1, -1):
        i = stack[k]
        r = recv[i]
        if r < 0:
            continue
        b, w = best[i], where[i]                             # the largest among cell i and everything upstream of it
        if w < 0 or values[i] > b or (values[i] == b and rank[i] < rank[w]):
            b, w = values[i], i
        if where[r] < 0 or b > best[r] or (b == best[r] and rank[w] < rank[where[r]]):
            best[r] = b
            where[r] = w
    return where


def largest_upstream(stack: np.ndarray, recv: np.ndarray, values: np.ndarray, rank: np.ndarray | None = None) -> np.ndarray:
    """For each cell, the cell with the largest of `values` among the cells that drain through it, the cell itself
    left out; NO_CELL where nothing drains through the cell. Among equals the first in the order of the cells
    (`rank`; the cell numbers if none is given)."""
    rank = np.arange(recv.size, dtype=np.int64) if rank is None else np.ascontiguousarray(rank, dtype=np.int64)
    return _largest_upstream(stack, np.ascontiguousarray(recv, dtype=np.int64), np.ascontiguousarray(values, dtype=np.float64), rank)
