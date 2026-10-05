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

Heights here are those of the "drainage surface": the ground on land, the water surface on the sea.

Ties. Among equally low neighbours the one with the lowest cell number is taken, and level ground is
drained toward its nearest way out. Real relief has next to no exact ties; relief given in whole metres has
many. A result therefore does not depend on anything that varies from run to run, but on ground that is
exactly symmetric it does depend on how the cells are numbered.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from numba import njit

NO_CELL = -1                    # no receiver: a sea cell, or the bottom of a hollow
SEA = 0                         # the label of ground that drains to the sea, and row 0 of the table of hollows


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


def receivers(surface: np.ndarray, sea: np.ndarray, nbr: np.ndarray) -> np.ndarray:
    """For each cell, the neighbour its water runs to; NO_CELL for a sea cell and for the bottom of a hollow.

    A cell drains to its lowest neighbour if that neighbour is lower. Level ground (cells with a neighbour at
    their own height and none lower) drains toward its nearest way out, a cell at the same height that does
    drain. Level ground with no way out is the floor of a hollow: it drains to one of its cells, the one with the
    lowest number, which is the hollow's bottom.
    """
    n = surface.size
    valid = nbr >= 0
    around = np.where(valid, surface[np.where(valid, nbr, 0)], np.inf)
    lowest = around.min(axis=1)
    none = np.iinfo(np.int64).max
    pick = np.where(around == lowest[:, None], nbr.astype(np.int64), none).min(axis=1)
    recv = np.where((lowest < surface) & ~sea, pick, NO_CELL)
    stuck = np.flatnonzero((recv < 0) & ~sea & (lowest == surface))
    if stuck.size == 0:
        return recv
    neighbours = [[j for j in row if j >= 0] for row in nbr.tolist()]
    height = surface.tolist()
    is_stuck = np.zeros(n, dtype=bool)
    is_stuck[stuck] = True
    seen = np.zeros(n, dtype=bool)
    for start in stuck.tolist():
        if seen[start]:
            continue
        level = height[start]
        ground = [start]                                     # the level ground this cell belongs to
        seen[start] = True
        k = 0
        while k < len(ground):
            for j in neighbours[ground[k]]:
                if is_stuck[j] and not seen[j] and height[j] == level:
                    seen[j] = True
                    ground.append(j)
            k += 1
        inside = set(ground)
        queue, done = deque(), set()
        for i in sorted(ground):                             # the ways out: cells at the same height that drain
            ways = [j for j in neighbours[i] if height[j] == level and j not in inside and (sea[j] or recv[j] >= 0)]
            if ways:
                recv[i] = min(ways)
                done.add(i)
                queue.append(i)
        if not queue:                                        # no way out: the floor of a hollow
            bottom = min(ground)
            done.add(bottom)
            queue.append(bottom)
        while queue:
            i = queue.popleft()
            for j in neighbours[i]:
                if j in inside and j not in done:
                    recv[j] = i
                    done.add(j)
                    queue.append(j)
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
    """The cells in an order in which every cell comes after the cell it drains to (Braun and Willett's stack)."""
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
            area: np.ndarray):
    """The closed hollows of the land and how they nest (Barnes, Callaghan and Wickert 2020).

    A hollow is the ground that drains to one bottom. Two neighbouring hollows meet at their lowest pass: the
    pair of neighbouring cells, one in each, whose higher cell is lowest. When both have filled to that pass they
    are one larger hollow, which fills on to its own lowest pass. Passes are taken from the lowest up, so the
    hollows form a tree of pairs; a hollow whose lowest pass leads to ground that already drains to the sea ends
    its tree, and its overflow runs on from the cell beyond the pass.

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
    a, b = a[touch], b[touch]
    swap = label[a] > label[b]
    a, b = np.where(swap, b, a), np.where(swap, a, b)        # the cell with the lower label first
    one, other = label[a], label[b]
    height = np.maximum(surface[a], surface[b])
    order = np.lexsort((b, a, height, other, one))
    one, other, a, b, height = one[order], other[order], a[order], b[order], height[order]
    lowest = np.ones(one.size, dtype=bool)
    lowest[1:] = (one[1:] != one[:-1]) | (other[1:] != other[:-1])
    one, other, a, b, height = one[lowest], other[lowest], a[lowest], b[lowest], height[lowest]
    order = np.lexsort((b, a, height))                       # the passes from the lowest up

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
        if (bottom_height[tb], bottom_cell[tb]) < (bottom_height[ta], bottom_cell[ta]):
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


def overflow_receivers(recv: np.ndarray, sea: np.ndarray, table) -> np.ndarray:
    """The receivers as they are when every hollow is full and overflows. Within the largest hollow that holds it,
    every bottom hands its water to that hollow's deepest bottom, and the deepest bottom hands it to the cell beyond
    the hollow's pass. Every path then ends in the sea, or, for a hollow with no way out at all, at that hollow's
    deepest bottom. A hollow overflows into ground whose own hollow overflows at a pass no higher, so the paths hold
    no loop."""
    out = np.array(recv, dtype=np.int64)
    parent = np.asarray(table["parent"])
    bottom = np.asarray(table["bottom_cell"])
    beyond = np.asarray(table["spill_into_cell"])
    top = top_hollows(table)
    leaves = np.flatnonzero((np.asarray(table["first_child"]) < 0) & (np.arange(parent.size) > SEA))
    deepest = bottom[top[leaves]]
    way_out = np.where(beyond[top[leaves]] >= 0, beyond[top[leaves]], NO_CELL)
    out[bottom[leaves]] = np.where(bottom[leaves] == deepest, way_out, deepest)
    return out


def mouths(stack: np.ndarray, recv: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """For each land cell, the last land cell its water passes before it ends (in the sea, or at a bottom): the
    mouth of its river. With the receivers of overflow_receivers, a hollow that overflows straight into the sea has
    its deepest bottom as its mouth. NO_CELL for sea cells."""
    recv = np.asarray(recv, dtype=np.int64)
    on_land = np.where((recv >= 0) & sea[np.maximum(recv, 0)], NO_CELL, recv)      # stop one cell before the sea
    end = _terminal(stack, np.ascontiguousarray(on_land))
    return np.where(sea, NO_CELL, end)


@njit(cache=True)
def _largest_upstream(stack, recv, values):
    best = values.copy()
    where = np.arange(recv.size)
    for k in range(stack.size - 1, -1, -1):
        i = stack[k]
        r = recv[i]
        if r >= 0 and (best[i] > best[r] or (best[i] == best[r] and where[i] < where[r])):
            best[r] = best[i]
            where[r] = where[i]
    return where


def largest_upstream(stack: np.ndarray, recv: np.ndarray, values: np.ndarray) -> np.ndarray:
    """For each cell, the cell with the largest of `values` among itself and every cell that drains through it."""
    return _largest_upstream(stack, np.ascontiguousarray(recv, dtype=np.int64), np.ascontiguousarray(values, dtype=np.float64))
