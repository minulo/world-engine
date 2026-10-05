"""Lakes in closed hollows under a steady climate: which hollows hold water, how far it spreads, which overflow.

Model (Adapted). The water-moving step of Fill-Spill-Merge [DOCUMENTED: Barnes, Callaghan and
Wickert 2021] with one change, which is mine [INFERRED]. There each hollow can hold a volume,
and water is passed on until no hollow holds more than its volume. Here the climate repeats
year after year, and a lake has stopped growing when the water that arrives in a year equals
what its surface loses to the air in a year. What a hollow can take is therefore not a volume
but a yearly loss:

    the yearly loss of a flooded cell = its area * (what open water evaporates - what the land
    it covers would have evaporated anyway)

Water floods the cells of a hollow from the lowest up, as in the published method. Cells of
equal height flood together. The lake spreads until the cells it covers lose as much as
arrives, and then it is a closed lake below its pass. If the hollow is flooded to its pass and
more arrives than it loses, the rest overflows: into the neighbouring hollow, and when that
one is full as well the two are one lake, which rises to the next pass.

settle() moves the water, in the order of the published method: the hollows of a tree from the
smallest up, and the trees in the order in which one overflows into the next.
flooded() turns the result into the flooded share of every cell and the level of every lake.
lake_flows() follows the water through the lakes month by month: every month a lake passes
on the same share of what reaches it, the share that it passes on over the whole year.

Ignores: the time a lake takes to fill; lakes that swell and shrink with the seasons; water
that seeps through the ground from one hollow to the next; ice on the lake.
"""
import numpy as np

from . import drainage as dr

DUST = 1.0e-6          # m3 a year: less water than this counts as none
HAIR = 1.0e-9          # ... and so does less than this share of what reaches a hollow: rounding cannot make a lake overflow


def tree_order(table) -> list:
    """The largest hollows (those inside no other) in an order in which each comes before the one it overflows into."""
    parent = np.asarray(table["parent"])
    into = np.asarray(table["spill_into_hollow"])
    top = dr.top_hollows(table)
    tops = [int(k) for k in np.flatnonzero(parent < 0) if k > dr.SEA]
    steps = {}                                               # how many overflows lie between a hollow and the sea
    for start in tops:
        chain, k = [], start
        while k not in steps:
            chain.append(k)
            g = int(into[k])
            if g <= dr.SEA:
                steps[k] = 0
                chain.pop()
                break
            k = int(top[g])
        for back, node in enumerate(reversed(chain), 1):
            steps[node] = steps[k] + back
    return sorted(tops, key=lambda t: (-steps[t], t))


def settle(table, inflow, room):
    """Move a year's water through the hollows until every lake loses what it receives.

    inflow   per row of the table of hollows: the water (m3 a year) that runs to the bottom of each hollow with one
             bottom; zero for the others
    room     per row: the yearly loss of the cells that this hollow floods beyond what its parts flood (m3 a year)

    Returns a dict:
      extra      per row, how much of its room the hollow uses
      overflows  per row, whether more reached the hollow than all its room takes: it stands at its pass and sends
                 the rest on
      to_sea     water that left the hollows for ground that drains to the sea
      nowhere    water left over in a hollow that has no way out and cannot lose all that reaches it
    """
    parent = np.asarray(table["parent"]).tolist()
    sibling = np.asarray(table["sibling"]).tolist()
    first = np.asarray(table["first_child"]).tolist()
    second = np.asarray(table["second_child"]).tolist()
    into = np.asarray(table["spill_into_hollow"]).tolist()
    rows = len(parent)
    water = [float(v) for v in inflow]
    room = [float(v) for v in room]
    extra, over, surplus = [0.0] * rows, [False] * rows, [0.0] * rows

    def fill(k, w):
        reached = w
        take = min(w, room[k] - extra[k])
        if take > 0.0:
            extra[k] += take
            w -= take
        if w > DUST + HAIR * reached:
            over[k] = True
            return w
        return 0.0

    def add(leaf, w, within):
        """Pour w into the hollow `leaf`, which lies inside the hollow `within`; returns what `within` cannot take."""
        stops, cur = [within], leaf
        while True:
            w = fill(cur, w)
            if w <= 0.0:
                return 0.0
            if cur == stops[-1]:                             # the hollow that was being filled is full
                stops.pop()
                if not stops:
                    return w
                cur = parent[cur]                            # it and the one that overflowed into it are now one lake
            elif over[sibling[cur]]:
                cur = parent[cur]                            # its neighbour is full too: the two are one lake
            else:
                stops.append(sibling[cur])                   # it overflows into its neighbour
                cur = into[cur]

    top = dr.top_hollows(table)
    members = {}
    for k in range(1, rows):                                 # rows rise from parts to wholes, so each list is in that order
        members.setdefault(int(top[k]), []).append(k)
    to_sea = nowhere = 0.0
    for t in tree_order(table):
        for k in members[t]:
            if first[k] < 0:
                surplus[k] = fill(k, water[k])
                continue
            a, b = first[k], second[k]
            if surplus[a] > 0.0 and surplus[b] > 0.0:
                w = surplus[a] + surplus[b]
            elif surplus[a] > 0.0:
                w = add(into[a], surplus[a], b)
            elif surplus[b] > 0.0:
                w = add(into[b], surplus[b], a)
            else:
                w = 0.0
            surplus[k] = fill(k, w) if w > 0.0 else 0.0
        if surplus[t] > 0.0:
            if into[t] > dr.SEA:
                water[into[t]] += surplus[t]
            elif into[t] == dr.SEA:
                to_sea += surplus[t]
            else:
                nowhere += surplus[t]
    return {"extra": np.array(extra), "overflows": np.array(over, dtype=bool), "to_sea": to_sea, "nowhere": nowhere}


def lake_units(table, overflows):
    """Which hollows are single lakes.

    A hollow with one bottom can hold a lake of its own. A larger hollow is one lake only once both its parts have
    overflowed. Returns (one_lake, lake): for each row whether it is one lake, and the row of the largest such lake
    that it is part of (-1 for a row that is not one lake)."""
    parent = np.asarray(table["parent"])
    first, second = np.asarray(table["first_child"]), np.asarray(table["second_child"])
    rows = parent.size
    one = first < 0
    merged = ~one
    one[merged] = overflows[first[merged]] & overflows[second[merged]]
    one[dr.SEA] = False
    lake = np.where(one, np.arange(rows), -1)
    for k in range(rows - 1, 0, -1):                         # wholes before parts
        p = parent[k]
        if one[k] and p >= 0 and one[p]:
            lake[k] = lake[p]
    return one, lake


def flooded(table, own, surface, loss, extra, overflows):
    """How much of every cell lies under a lake, and the level of each lake.

    own      per cell, the hollow whose rise floods it (drainage.owners)
    surface  per cell, the height of the ground
    loss     per cell, the yearly loss it takes once it is wholly flooded (m3 a year)
    Returns (share, level, lake): per cell the flooded share and the row of its lake (-1 for none), and per row of
    the table the level of the lake's surface (no value where the row is not a lake of its own or holds no water).
    """
    n = own.size
    rows = np.asarray(table["parent"]).size
    spill = np.asarray(table["spill_m"], dtype=np.float64)
    first = np.asarray(table["first_child"])
    one, unit = lake_units(table, overflows)
    share = np.zeros(n)
    held = own >= 0
    share[held & overflows[np.maximum(own, 0)]] = 1.0        # a hollow that overflows is flooded to its pass
    top_ground = np.full(rows, -np.inf)                      # the highest ground the lake of a part-full hollow reaches
    part = held & one[np.maximum(own, 0)] & ~overflows[np.maximum(own, 0)] & (extra[np.maximum(own, 0)] > 0.0)
    cells = np.flatnonzero(part)
    if cells.size:
        order = np.lexsort((cells, surface[cells], own[cells]))
        cells = cells[order]
        k, z = own[cells], surface[cells]
        new_level = np.ones(cells.size, dtype=bool)
        new_level[1:] = (k[1:] != k[:-1]) | (z[1:] != z[:-1])
        level_of = np.cumsum(new_level) - 1                  # cells of one hollow at one height flood together
        takes = np.bincount(level_of, weights=loss[cells])
        level_hollow = k[new_level]
        level_height = z[new_level]
        total = np.cumsum(takes)
        start = np.ones(takes.size, dtype=bool)
        start[1:] = level_hollow[1:] != level_hollow[:-1]
        before_hollow = np.maximum.accumulate(np.where(start, total - takes, -np.inf))
        left = extra[level_hollow] - (total - takes - before_hollow)       # water not yet used when this level is reached
        covered = np.where(takes > 0.0, np.clip(left / np.where(takes > 0.0, takes, 1.0), 0.0, 1.0), (left > DUST) * 1.0)
        share[cells] = covered[level_of]
        wet = covered > 0.0
        np.maximum.at(top_ground, level_hollow[wet], level_height[wet])
    level = np.full(rows, np.nan)
    for u in np.flatnonzero(one & (unit == np.arange(rows))):
        if overflows[u]:
            level[u] = spill[u]                              # (a hollow with no way out has no level of overflow)
        elif np.isfinite(top_ground[u]):
            level[u] = top_ground[u]
        elif first[u] >= 0:
            level[u] = spill[first[u]]                       # two full parts and nothing more: the lake stands at their pass
    lake = np.where(share > 0.0, unit[np.maximum(own, 0)], -1)
    return share, level, lake


def lake_flows(table, label, recv, stack, runoff, extra, overflows):
    """The water through the lakes, month by month.

    label    per cell, the hollow with one bottom that it drains into (0: it drains to the sea)
    runoff   (months, n): the water each cell sheds in each month, as if none of it were flooded (m3 a month)
    Returns (discharge, lakes):
      discharge  (months, n) m3 a month: the water passing through each cell, with the overflow of every lake added
                 where it leaves, on the cell beyond the lake's pass
      lakes      a dict of arrays, one entry per lake that receives water: row (in the table of hollows), inflow,
                 loss and outflow (m3 a year), overflows, and the cell its overflow runs into (-1 for none)
    """
    parent = np.asarray(table["parent"])
    first = np.asarray(table["first_child"])
    into = np.asarray(table["spill_into_hollow"])
    beyond = np.asarray(table["spill_into_cell"])
    bottom = np.asarray(table["bottom_cell"])
    rows = parent.size
    months = runoff.shape[0]
    one, unit = lake_units(table, overflows)
    plain = dr.accumulate(stack, recv, runoff)
    held = np.array(extra, dtype=np.float64)                 # the loss of a lake: its own and that of its full parts
    for k in range(1, rows):
        if one[k] and parent[k] >= 0 and one[parent[k]]:
            held[parent[k]] += held[k]
    leaves = np.flatnonzero((first < 0) & (np.arange(rows) > dr.SEA))
    arriving = np.zeros((months, rows))                      # what runs to the bottoms of each lake from its own ground
    np.add.at(arriving, (slice(None), unit[leaves]), plain[:, bottom[leaves]])
    lakes = np.flatnonzero(one & (unit == np.arange(rows)))
    target = np.where(overflows[lakes] & (into[lakes] > dr.SEA), unit[np.maximum(into[lakes], 0)], -1)
    target = dict(zip(lakes.tolist(), target.tolist()))
    steps = {}

    def distance(u):                                         # overflows between this lake and the end of its chain
        chain = []
        while u not in steps and target[u] >= 0:
            chain.append(u)
            u = target[u]
        steps.setdefault(u, 0)
        for back, node in enumerate(reversed(chain), 1):
            steps[node] = steps[u] + back
    for u in lakes.tolist():
        distance(u)
    passed_on = np.zeros((months, rows))
    out = {"row": [], "inflow": [], "loss": [], "outflow": [], "overflows": [], "into_cell": []}
    source = np.zeros(runoff.shape)
    for u in sorted(lakes.tolist(), key=lambda v: (-steps[v], v)):
        year = float(arriving[:, u].sum())
        leaving = max(year - held[u], 0.0) if overflows[u] else 0.0
        if leaving > 0.0:
            passed_on[:, u] = arriving[:, u] * (leaving / year)
            if target[u] >= 0:
                arriving[:, target[u]] += passed_on[:, u]
            if beyond[u] >= 0:
                source[:, beyond[u]] += passed_on[:, u]
        if year > DUST or held[u] > 0.0:
            out["row"].append(u); out["inflow"].append(year); out["loss"].append(float(held[u]))
            out["outflow"].append(leaving); out["overflows"].append(bool(overflows[u]))
            out["into_cell"].append(int(beyond[u]) if overflows[u] else -1)
    discharge = plain + dr.accumulate(stack, recv, source) if source.any() else plain
    kinds = {"row": np.int64, "into_cell": np.int64, "overflows": bool}
    return discharge, {name: np.array(col, dtype=kinds.get(name, np.float64)) for name, col in out.items()}
