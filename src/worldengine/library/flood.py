"""Filling hollows with water: plain functions shared by SeaLevel and, later, Hydrology (design, Layer 2).

pour() pours a volume of water in at the lowest point. The water fills a hollow to its rim,
spills into the next, and stops when the volume is used up, as in the Fill-Spill-Merge method
of Barnes et al. 2021, used here for the sea itself.

Every tie is broken by cell number, so the result never varies.
"""
from __future__ import annotations

import heapq

import numpy as np


def pour(height: np.ndarray, area: np.ndarray, nbr: np.ndarray, nbr_count: np.ndarray, volume: float):
    """Pour `volume` in at the lowest cell.

    Returns (body, level): for each cell the number of the body of water it lies in (-1 if dry or
    only touched at zero depth is still a member), and for each body the height of its surface.
    A cell is under water where level[body] > height.
    """
    n = height.size
    z = [float(v) for v in height]
    ar = [float(v) for v in area]
    neighbours = [[int(j) for j in nbr[i, :nbr_count[i]]] for i in range(n)]
    owner = [-1] * n                    # body a cell was added to
    parent = []                         # union-find over bodies
    level, wet_area, heaps = [], [], []

    def find(b):
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]
        return b

    def new_body(cell):
        b = len(parent)
        parent.append(b); level.append(z[cell]); wet_area.append(ar[cell])
        owner[cell] = b
        heap = [(z[j], j) for j in neighbours[cell]]
        heapq.heapify(heap)
        heaps.append(heap)
        return b

    if volume <= 0.0 or n == 0:
        return np.full(n, -1, dtype=np.int64), np.zeros(0)
    stack = [new_body(int(np.argmin(height)))]
    left = float(volume)
    while left > 0.0:
        b = stack[-1]
        heap = heaps[b]
        if not heap:                                         # nothing left to flood: the whole planet is under water
            level[b] += left / wet_area[b]
            break
        zc, c = heap[0]
        if owner[c] >= 0 and find(owner[c]) == b:
            heapq.heappop(heap)
            continue
        if len(stack) > 1 and zc >= level[stack[-2]]:        # risen to the body it spilled from: the two merge
            p = stack[-2]
            need = wet_area[b] * (level[p] - level[b])
            if need > left:
                level[b] += left / wet_area[b]
                break
            left -= need
            small, big = (heaps[b], heaps[p]) if len(heaps[b]) <= len(heaps[p]) else (heaps[p], heaps[b])
            for item in small:
                heapq.heappush(big, item)
            heaps[p], heaps[b] = big, []
            wet_area[p] += wet_area[b]
            parent[b] = p
            stack.pop()
            continue
        heapq.heappop(heap)
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
            for j in neighbours[c]:
                if owner[j] < 0 or find(owner[j]) != b:
                    heapq.heappush(heap, (z[j], j))
        else:                                                # lower ground beyond a rim: the water spills into a new hollow
            heapq.heappush(heap, (zc, c))
            q = c
            while True:
                best = q
                for j in neighbours[q]:
                    if owner[j] < 0 and (z[j], j) < (z[best], best):
                        best = j
                if best == q:
                    break
                q = best
            stack.append(new_body(q))
    body = np.array([find(o) if o >= 0 else -1 for o in owner], dtype=np.int64)
    return body, np.array(level)


def barriers(height: np.ndarray, nbr: np.ndarray, nbr_count: np.ndarray, source: np.ndarray, source_level: float):
    """For every cell outside `source`, the lowest height that water from the source would have to rise to in order
    to reach it, and the cell where that height is set (the barrier). Cells of the source get the source level and -1."""
    n = height.size
    z = [float(v) for v in height]
    neighbours = [[int(j) for j in nbr[i, :nbr_count[i]]] for i in range(n)]
    reach = [None] * n
    barrier = [-1] * n
    heap = []
    for i in np.flatnonzero(source):
        reach[int(i)] = float(source_level)
        heap.append((float(source_level), int(i)))
    heapq.heapify(heap)
    while heap:
        r, i = heapq.heappop(heap)
        if r > reach[i]:
            continue
        for j in neighbours[i]:
            if z[j] > r:
                rj, bj = z[j], j
            else:
                rj, bj = r, barrier[i]
            if reach[j] is None or rj < reach[j]:
                reach[j], barrier[j] = rj, bj
                heapq.heappush(heap, (rj, j))
    out = np.array([np.inf if r is None else r for r in reach])
    return out, np.array(barrier, dtype=np.int64)
