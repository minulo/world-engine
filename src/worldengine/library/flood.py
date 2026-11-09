"""Filling hollows with water: plain functions shared by SeaLevel and, later, Hydrology (design, Layer 2).

pour() pours a volume of water in at the lowest point. The water fills a hollow to its rim,
spills into the next, and stops when the volume is used up, as in the Fill-Spill-Merge method
of Barnes et al. 2021, used here for the sea itself.

Every tie is broken by cell number, so the result never varies.

The loops are compiled (numba, fastmath off) and do exactly what the plain Python of the first versions did, step
for step: the same queues taken in the same order, the same sums in the same order (build-speed, in docs/BUILD_NOTES.md:
the same bits on the default worlds; SeaLevel took 0.75 s a round on the standard mesh where it took 2.12). A queue is
a heap ordered by (height, cell number); two entries that compare equal are the same entry, so no heap can take them
in another order.
"""
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def _before(key_a, id_a, key_b, id_b):
    """The order of every queue: lower key first, then lower cell number (as Python compares the pairs)."""
    return key_a < key_b or (key_a == key_b and id_a < id_b)


@njit(cache=True)
def _sift_down(keys, ids, start, pos):
    """heapq's _siftdown: the new entry at pos moves up toward the root at start."""
    k, i = keys[pos], ids[pos]
    while pos > start:
        up = (pos - 1) >> 1
        if _before(k, i, keys[up], ids[up]):
            keys[pos], ids[pos] = keys[up], ids[up]
            pos = up
            continue
        break
    keys[pos], ids[pos] = k, i


@njit(cache=True)
def _sift_up(keys, ids, size, pos):
    """heapq's _siftup: the entry at pos goes down to a leaf along the smaller children, then up into place."""
    start = pos
    k, i = keys[pos], ids[pos]
    child = 2 * pos + 1
    while child < size:
        right = child + 1
        if right < size and not _before(keys[child], ids[child], keys[right], ids[right]):
            child = right
        keys[pos], ids[pos] = keys[child], ids[child]
        pos = child
        child = 2 * pos + 1
    keys[pos], ids[pos] = k, i
    _sift_down(keys, ids, start, pos)


@njit(cache=True)
def _push(keys, ids, size, key, cell):
    """Add an entry; returns the arrays (grown if full) and the new size."""
    if size == keys.size:
        grown_keys = np.empty(2 * keys.size + 1, dtype=np.float64)
        grown_ids = np.empty(2 * keys.size + 1, dtype=np.int64)
        grown_keys[:size] = keys[:size]
        grown_ids[:size] = ids[:size]
        keys, ids = grown_keys, grown_ids
    keys[size], ids[size] = key, cell
    _sift_down(keys, ids, 0, size)
    return keys, ids, size + 1


@njit(cache=True)
def _pop(keys, ids, size):
    """Remove the first entry; returns the new size (the entry is read from keys[0], ids[0] before the call)."""
    size -= 1
    if size > 0:
        keys[0], ids[0] = keys[size], ids[size]
        _sift_up(keys, ids, size, 0)
    return size


@njit(cache=True)
def _find(parent, b):
    while parent[b] != b:
        parent[b] = parent[parent[b]]
        b = parent[b]
    return b


@njit(cache=True)
def _pour(z, ar, nbr, nbr_count, volume, lowest):
    n = z.size
    owner = np.full(n, -1, dtype=np.int64)                   # body a cell was added to
    parent = np.empty(n, dtype=np.int64)                     # union-find over bodies (a body starts at a cell of its own)
    level = np.empty(n, dtype=np.float64)
    wet_area = np.empty(n, dtype=np.float64)
    heap_keys = [np.empty(0, dtype=np.float64) for _ in range(0)]
    heap_ids = [np.empty(0, dtype=np.int64) for _ in range(0)]
    sizes = np.zeros(n, dtype=np.int64)
    stack = np.empty(n, dtype=np.int64)
    bodies = 0

    # new_body(lowest)
    b = bodies
    bodies += 1
    parent[b], level[b], wet_area[b] = b, z[lowest], ar[lowest]
    owner[lowest] = b
    keys = np.empty(nbr_count[lowest], dtype=np.float64)
    ids = np.empty(nbr_count[lowest], dtype=np.int64)
    size = 0
    for k in range(nbr_count[lowest]):
        keys, ids, size = _push(keys, ids, size, z[nbr[lowest, k]], nbr[lowest, k])
    heap_keys.append(keys)
    heap_ids.append(ids)
    sizes[b] = size
    stack[0] = b
    depth = 1
    left = volume
    while left > 0.0:
        b = stack[depth - 1]
        keys, ids, size = heap_keys[b], heap_ids[b], sizes[b]
        if size == 0:                                        # nothing left to flood: the whole planet is under water
            level[b] += left / wet_area[b]
            break
        zc, c = keys[0], ids[0]
        if owner[c] >= 0 and _find(parent, owner[c]) == b:
            sizes[b] = _pop(keys, ids, size)
            continue
        if depth > 1 and zc >= level[stack[depth - 2]]:     # risen to the body it spilled from: the two merge
            p = stack[depth - 2]
            need = wet_area[b] * (level[p] - level[b])
            if need > left:
                level[b] += left / wet_area[b]
                break
            left -= need
            if sizes[b] <= sizes[p]:                         # the smaller queue is poured into the larger
                small_keys, small_ids, small_size = heap_keys[b], heap_ids[b], sizes[b]
                big_keys, big_ids, big_size = heap_keys[p], heap_ids[p], sizes[p]
            else:
                small_keys, small_ids, small_size = heap_keys[p], heap_ids[p], sizes[p]
                big_keys, big_ids, big_size = heap_keys[b], heap_ids[b], sizes[b]
            for m in range(small_size):
                big_keys, big_ids, big_size = _push(big_keys, big_ids, big_size, small_keys[m], small_ids[m])
            heap_keys[p], heap_ids[p], sizes[p] = big_keys, big_ids, big_size
            heap_keys[b], heap_ids[b], sizes[b] = np.empty(0, dtype=np.float64), np.empty(0, dtype=np.int64), 0
            wet_area[p] += wet_area[b]
            parent[b] = p
            depth -= 1
            continue
        size = _pop(keys, ids, size)
        sizes[b] = size
        if owner[c] >= 0:                                    # a cell of another body below this one's reach: not ours
            continue
        if zc >= level[b]:                                   # the water must rise to reach this cell
            need = wet_area[b] * (zc - level[b])
            if need > left:
                level[b] += left / wet_area[b]
                break
            left -= need
            level[b] = zc
            owner[c] = b
            wet_area[b] += ar[c]
            for k in range(nbr_count[c]):
                j = nbr[c, k]
                if owner[j] < 0 or _find(parent, owner[j]) != b:
                    keys, ids, size = _push(keys, ids, size, z[j], j)
            heap_keys[b], heap_ids[b], sizes[b] = keys, ids, size
        else:                                                # lower ground beyond a rim: the water spills into a new hollow
            keys, ids, size = _push(keys, ids, size, zc, c)
            heap_keys[b], heap_ids[b], sizes[b] = keys, ids, size
            q = c
            while True:
                best = q
                for k in range(nbr_count[q]):
                    j = nbr[q, k]
                    if owner[j] < 0 and _before(z[j], j, z[best], best):
                        best = j
                if best == q:
                    break
                q = best
            # new_body(q)
            nb_ = bodies
            bodies += 1
            parent[nb_], level[nb_], wet_area[nb_] = nb_, z[q], ar[q]
            owner[q] = nb_
            keys = np.empty(nbr_count[q], dtype=np.float64)
            ids = np.empty(nbr_count[q], dtype=np.int64)
            size = 0
            for k in range(nbr_count[q]):
                keys, ids, size = _push(keys, ids, size, z[nbr[q, k]], nbr[q, k])
            heap_keys.append(keys)
            heap_ids.append(ids)
            sizes[nb_] = size
            stack[depth] = nb_
            depth += 1
    body = np.full(n, -1, dtype=np.int64)
    for i in range(n):
        if owner[i] >= 0:
            body[i] = _find(parent, owner[i])
    return body, level[:bodies].copy()


def pour(height: np.ndarray, area: np.ndarray, nbr: np.ndarray, nbr_count: np.ndarray, volume: float):
    """Pour `volume` in at the lowest cell.

    Returns (body, level): for each cell the number of the body of water it lies in (-1 if dry or
    only touched at zero depth is still a member), and for each body the height of its surface.
    A cell is under water where level[body] > height.
    """
    n = height.size
    if volume <= 0.0 or n == 0:
        return np.full(n, -1, dtype=np.int64), np.zeros(0)
    z = np.ascontiguousarray(height, dtype=np.float64)
    return _pour(z, np.ascontiguousarray(area, dtype=np.float64), np.ascontiguousarray(nbr, dtype=np.int64),
                 np.ascontiguousarray(nbr_count, dtype=np.int64), float(volume), int(np.argmin(height)))


@njit(cache=True)
def _barriers(z, nbr, nbr_count, sources, source_level):
    n = z.size
    reach = np.full(n, np.inf)
    reached = np.zeros(n, dtype=np.bool_)
    barrier = np.full(n, -1, dtype=np.int64)
    keys = np.empty(sources.size + 1, dtype=np.float64)
    ids = np.empty(sources.size + 1, dtype=np.int64)
    size = 0
    for i in sources:
        reach[i] = source_level
        reached[i] = True
        keys, ids, size = _push(keys, ids, size, source_level, i)
    while size > 0:
        r, i = keys[0], ids[0]
        size = _pop(keys, ids, size)
        if r > reach[i]:
            continue
        for k in range(nbr_count[i]):
            j = nbr[i, k]
            if z[j] > r:
                rj, bj = z[j], j
            else:
                rj, bj = r, barrier[i]
            if not reached[j] or rj < reach[j]:
                reach[j], barrier[j] = rj, bj
                reached[j] = True
                keys, ids, size = _push(keys, ids, size, rj, j)
    return reach, barrier


def barriers(height: np.ndarray, nbr: np.ndarray, nbr_count: np.ndarray, source: np.ndarray, source_level: float):
    """For every cell outside `source`, the lowest height that water from the source would have to rise to in order
    to reach it, and the cell where that height is set (the barrier). Cells of the source get the source level and -1."""
    return _barriers(np.ascontiguousarray(height, dtype=np.float64), np.ascontiguousarray(nbr, dtype=np.int64),
                     np.ascontiguousarray(nbr_count, dtype=np.int64), np.flatnonzero(source).astype(np.int64),
                     float(source_level))
