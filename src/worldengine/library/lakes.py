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

check_table() refuses a table of hollows that does not keep the rules this module relies on.
settle() moves the water, in the order of the published method [DOCUMENTED when build step 2 was
written: Barnes, Callaghan and Wickert 2021]: the hollows of a tree from the smallest up, and
the trees in the order in which one overflows into the next.
flooded() turns the result into the flooded share of every cell and the level of every lake.
lake_flows() follows the water through the lakes month by month.

The water inside a lake [INFERRED: all of it mine; the engine has no model of a lake's
currents or of its level through the year]:
  * A lake that overflows passes on, in every month, the same share of the water that reaches
    it: the share it passes on over the whole year. A real lake with an outlet evens out the
    seasons of the river below it [UNVERIFIED: recalled]; this one does not.
  * Inside such a lake the water is handed from cell to cell to the outlet cell (the cell on
    the lake's side of its pass; drainage.through_full_hollows), and of the water passing a
    cell the flow counts the share that will leave the lake. The flow at the outlet cell is
    therefore the lake's outflow, and the river runs on from there without a break.
  * A closed lake passes nothing on. The flow shown in one of its cells is that over the part
    of the cell the lake does not cover: the river on its way to the water.

Water is conserved to within one part in a billion of what reaches a hollow (HAIR), not to
rounding: less than that is not allowed to make a lake overflow, and is counted as dropped.

A knife edge. Hollows are joined two at a time. Where three meet at one pass cell and each is
full to that pass with nothing to spare, their waters stand at one level and touch, but they
are named as two lakes or three, not one [MEASURED by the third check of build step 2: 117 of
21,591 lakes on rough ground under random climates]. Their sizes and their books are right
either way.

Ignores: the time a lake takes to fill; lakes that swell and shrink with the seasons; water
that seeps through the ground from one hollow to the next; ice on the lake; currents.
"""
import numpy as np
from numba import njit

from . import drainage as dr

DUST = 1.0e-6          # m3 a year: less water than this counts as none
HAIR = 1.0e-9          # ... and so does less than this share of what reaches a hollow: rounding cannot make a lake overflow
HEIGHTS_AGREE = 1.0e-6     # in check_table: a pass may differ from the ground handed over by this share of its height (and by this many metres)


def check_table(table, label: np.ndarray, recv: np.ndarray, sea: np.ndarray, ground: np.ndarray, nbr: np.ndarray) -> None:
    """Refuse a table of hollows that does not keep the rules this module relies on (data/tables.yaml states them).

    label   per cell, the hollow it drains into (the field depression_id)
    recv    per cell, its receiver; sea: per cell, whether it is sea; ground: per cell, the height of the ground
    nbr     per cell, its neighbours (-1 where a cell has fewer)
    Raises ValueError naming the first rule broken.

    Two things it cannot show.
      * That the pass a hollow names is its lowest. A table that names a higher pass, with the right cells and the
        right height, keeps every rule here, and its lake then stands too high. To show otherwise would be to find
        the hollows again [MEASURED by the fourth check of step 2: a pass at 894 m named for one at 530 m is
        accepted].
      * The level of a pass into the sea, which is bounded from below only: no lower than the cell on the hollow's
        own side. Its true level is the higher of that cell and the sea's surface beside it, and this check is not
        handed the sea's surface (Hydrology does not read it). A level written too high is accepted, and the lake
        then stands too high [MEASURED by the fifth check of step 2: a pass into the sea written 200 m too high
        was accepted, and Hydrology ran without a notice].
    """
    def refuse(what):
        raise ValueError(f"the table of hollows does not keep its rules: {what}")
    names = ("parent", "sibling", "first_child", "second_child", "bottom_cell", "bottom_m", "spill_m",
             "spill_from_cell", "spill_into_cell", "spill_into_hollow")
    missing = [name for name in names if name not in table]
    if missing:
        refuse(f"it has no column {missing[0]}")
    parent, sibling = np.asarray(table["parent"], dtype=np.int64), np.asarray(table["sibling"], dtype=np.int64)
    first, second = np.asarray(table["first_child"], dtype=np.int64), np.asarray(table["second_child"], dtype=np.int64)
    bottom = np.asarray(table["bottom_cell"], dtype=np.int64)
    low = np.asarray(table["bottom_m"], dtype=np.float64)
    spill = np.asarray(table["spill_m"], dtype=np.float64)
    here, beyond = np.asarray(table["spill_from_cell"], dtype=np.int64), np.asarray(table["spill_into_cell"], dtype=np.int64)
    into = np.asarray(table["spill_into_hollow"], dtype=np.int64)
    rows, n = parent.size, label.size
    row = np.arange(rows)
    if rows < 1 or parent[dr.SEA] >= 0 or first[dr.SEA] >= 0 or second[dr.SEA] >= 0:
        refuse("row 0 must stand for the sea, with no parent and no parts")
    single = (first < 0) & (row > dr.SEA)
    count = int(single.sum())
    if not single[1:count + 1].all():
        refuse("the hollows with one bottom must come first, in rows 1 to H, before every hollow made of two")
    merged = row > count
    if ((first[merged] < 1) | (second[merged] < 1) | (first[merged] >= row[merged]) | (second[merged] >= row[merged])
            | (first[merged] == second[merged])).any():
        k = int(row[merged][np.flatnonzero((first[merged] < 1) | (second[merged] < 1) | (first[merged] >= row[merged])
                                           | (second[merged] >= row[merged]) | (first[merged] == second[merged]))[0]])
        refuse(f"row {k}: a hollow made of two must name two different parts, both in earlier rows")
    for child in (first, second):
        if (parent[child[merged]] != row[merged]).any():
            refuse("a part of a hollow must name that hollow as its parent")
    has_parent = parent >= 0
    has_parent[dr.SEA] = False
    if (parent[has_parent] <= row[has_parent]).any() or (parent[has_parent] >= rows).any():
        refuse("a parent must stand in a later row than its parts")
    named = np.bincount(parent[has_parent], minlength=rows)  # how many rows name each row as their parent
    if (named[merged] != 2).any() or (named[~merged] != 0).any():
        k = int(row[np.where(merged, named != 2, named != 0)][0])
        refuse(f"row {k} is named as parent by {int(named[k])} rows: a hollow made of two is the parent of its two parts "
               f"and of no other row, and a hollow with one bottom is the parent of none")
    sib = sibling[has_parent]
    if ((sib < 1) | (sib >= rows)).any() or (parent[np.clip(sib, 0, rows - 1)] != parent[has_parent]).any() \
            or (sib == row[has_parent]).any():
        refuse("the two parts of a hollow must name each other as sibling")
    if (sibling[~has_parent] >= 0).any():
        refuse("a hollow inside no other has no sibling")
    if ((label < 0) | (label > count)).any():
        refuse("depression_id must be 0 or the row of a hollow with one bottom")
    cells = bottom[1:count + 1]
    if ((cells < 0) | (cells >= n)).any() or (recv[cells] >= 0).any() or sea[cells].any() or (label[cells] != row[1:count + 1]).any():
        refuse("the bottom cell of a hollow with one bottom must be a land cell without a receiver that drains into that hollow")
    row_at = np.zeros(n, dtype=np.int64)                     # for each bottom cell, the row of its hollow
    row_at[cells] = row[1:count + 1]
    if np.unique(cells).size != count or (row_at[(recv < 0) & ~sea] == dr.SEA).any():
        refuse("every land cell without a receiver must be the bottom of one hollow with one bottom, and no two hollows share a bottom")
    end = dr.terminal(dr.flow_stack(recv), recv)             # where the water of every cell ends
    drains_into = np.where(sea[end], dr.SEA, row_at[end])
    if (label != drains_into).any():
        c = int(np.flatnonzero(label != drains_into)[0])
        refuse(f"cell {c}: depression_id is {int(label[c])}, but down its receivers its water ends "
               + ("in the sea" if drains_into[c] == dr.SEA else f"at the bottom of hollow {int(drains_into[c])}")
               + ": depression_id must be the hollow with one bottom that the cell drains into (0 for the sea)")
    if not np.isfinite(low[1:]).all():
        k = 1 + int(np.flatnonzero(~np.isfinite(low[1:]))[0])
        refuse(f"row {k}: bottom_m must be a height, and it is {low[k]}")
    one, two = first[merged], second[merged]                 # a hollow made of two: its bottom is that of its deeper part
    deepest = np.minimum(low[one], low[two])
    if (((bottom[merged] != bottom[one]) | (low[one] > deepest)) & ((bottom[merged] != bottom[two]) | (low[two] > deepest))).any():
        refuse("a hollow made of two has the bottom of its deeper part for its bottom")
    slack = HEIGHTS_AGREE * np.maximum(np.abs(low[1:]), 1.0)
    if ((bottom[1:] < 0) | (bottom[1:] >= n)).any() or (np.abs(low[1:] - ground[np.clip(bottom[1:], 0, n - 1)]) > slack).any():
        k = 1 + int(np.flatnonzero((bottom[1:] < 0) | (bottom[1:] >= n) | (np.abs(low[1:] - ground[np.clip(bottom[1:], 0, n - 1)]) > slack))[0])
        refuse(f"row {k}: bottom_m is {low[k]:.3f} m, but its bottom cell stands at "
               f"{float(ground[np.clip(bottom[k], 0, n - 1)]):.3f} m in the field elevation: the heights of the table must be "
               f"those of that field")
    has_pass = beyond >= 0
    has_pass[dr.SEA] = False
    if (has_pass & has_parent != has_parent).any():
        refuse("a hollow inside another must name its pass")
    no_pass = ~has_pass
    no_pass[dr.SEA] = False
    if (~np.isnan(spill[no_pass])).any() or (here[no_pass] != -1).any() or (beyond[no_pass] != -1).any() or (into[no_pass] != -1).any():
        refuse("a hollow with no way out has no value for spill_m, and -1 for the cells of its pass and for spill_into_hollow")
    if not np.isfinite(spill[has_pass]).all() or ((here[has_pass] < 0) | (here[has_pass] >= n) | (beyond[has_pass] >= n)).any():
        refuse("a hollow with a pass must give its level, a height, and its two cells")
    k = row[has_pass]
    if not (nbr[here[k]] == beyond[k][:, None]).any(axis=1).all():
        j = int(k[np.flatnonzero(~(nbr[here[k]] == beyond[k][:, None]).any(axis=1))[0]])
        refuse(f"row {j}: the two cells of a pass must be neighbours, and cells {int(here[j])} and {int(beyond[j])} are not")
    if (into[has_pass] != label[beyond[has_pass]]).any():
        k = int(row[has_pass][np.flatnonzero(into[has_pass] != label[beyond[has_pass]])[0]])
        refuse(f"row {k}: spill_into_hollow must be the hollow with one bottom that the cell beyond the pass drains into "
               f"(0 if it drains to the sea)")
    inside = np.zeros(rows, dtype=np.int64)                  # for each row, the hollow inside no other that holds it
    inside[:] = row
    for k in range(rows - 1, dr.SEA, -1):
        if parent[k] >= 0:
            inside[k] = inside[parent[k]]
    k = row[has_pass]
    up = label[here[k]]                                      # the outlet cell drains into the row itself, or into a part of it
    for _ in range(rows):
        done = (up == k) | (up <= dr.SEA) | (parent[np.maximum(up, 0)] < 0)
        if done.all():
            break
        up = np.where(done, up, parent[np.maximum(up, 0)])
    if (up != k).any():
        j = int(k[np.flatnonzero(up != k)[0]])
        refuse(f"row {j}: the cell on a hollow's own side of its pass must drain into that hollow, and cell {int(here[j])} "
               f"drains into " + ("the sea" if label[here[j]] == dr.SEA else f"hollow {int(label[here[j]])}, which is no part of it"))
    in_sibling = has_parent.copy()
    if in_sibling.any():                                     # the water of a part runs into its sibling
        k = row[in_sibling]
        up = into[k]
        for _ in range(rows):
            done = (up == sibling[k]) | (up < 0)
            if done.all():
                break
            up = np.where(done, up, parent[np.maximum(up, 0)])
        if (up != sibling[k]).any():
            refuse("the pass of a part of a hollow must lead into the other part")
    tops = row[has_pass & ~has_parent]
    if (inside[into[tops]] == tops).any():
        refuse("a hollow inside no other cannot overflow into itself")
    if (spill[has_parent] > np.where(np.isnan(spill[parent[has_parent]]), np.inf, spill[parent[has_parent]])).any():
        refuse("a hollow cannot overflow lower than its parts do")
    if (spill[has_parent] != spill[sibling[has_parent]]).any():
        refuse("the two parts of a hollow meet at one pass, at one level")
    k = row[has_pass]
    land_pass = ~sea[beyond[k]]
    high = np.where(land_pass, np.maximum(ground[here[k]], ground[beyond[k]]), ground[here[k]])
    slack = HEIGHTS_AGREE * np.maximum(np.abs(spill[k]), 1.0)
    wrong = np.where(land_pass, np.abs(spill[k] - high) > slack, spill[k] < high - slack)
    if wrong.any():
        j = int(k[np.flatnonzero(wrong)[0]])
        refuse(f"row {j}: spill_m is {spill[j]:.3f} m, but the higher of the two cells of its pass stands at "
               f"{float(np.maximum(ground[here[j]], ground[beyond[j]])):.3f} m in the field elevation: the heights of the table "
               f"must be those of that field")
    far = inside[into[tops]]                                 # the hollow inside no other around the cell beyond the pass (0: the sea)
    onward = np.where(far == dr.SEA, -np.inf, np.where(np.isnan(spill[far]), np.inf, spill[far]))
    higher = onward > spill[tops] + HEIGHTS_AGREE * np.maximum(np.abs(spill[tops]), 1.0)
    if higher.any():
        j = int(tops[np.flatnonzero(higher)[0]])
        f = int(inside[into[j]])
        refuse(f"row {j} overflows at {spill[j]:.3f} m into the ground of hollow {f}, which "
               + ("has no way out" if np.isnan(spill[f]) else f"overflows only at {spill[f]:.3f} m")
               + ": a hollow inside no other overflows into ground whose own hollow overflows no higher")
    tree_order(table)                                        # refuses a ring of hollows that overflow into one another


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
            if k in chain:
                raise ValueError(f"the table of hollows does not keep its rules: hollow {k} overflows, by way of others, "
                                 f"into itself")
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
      overflows  per row, whether more reached the hollow than all its room takes: it is flooded to its pass, and the
                 rest runs on (or, in a hollow with no way out, has nowhere to go)
      to_sea     water that left the hollows for ground that drains to the sea
      nowhere    water left over in a hollow that has no way out and cannot lose all that reaches it
      dropped    water too little to count: what is left of a pour once it is below DUST and below the share HAIR of
                 what reached the hollow
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
    dropped = [0.0]

    def fill(k, w):
        reached = w
        take = min(w, room[k] - extra[k])
        if take > 0.0:
            extra[k] += take
            w -= take
        if w > DUST + HAIR * reached:
            over[k] = True
            return w
        dropped[0] += max(w, 0.0)
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
    return {"extra": np.array(extra), "overflows": np.array(over, dtype=bool), "to_sea": to_sea, "nowhere": nowhere,
            "dropped": dropped[0]}


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

    The level of a lake that overflows is that of its pass. The level of a lake below its pass is the height of
    the highest ground it wets: a cell has one height, so the level moves in steps of the cells' heights. A hollow
    with no way out that is flooded whole stands at its highest ground.
    """
    n = own.size
    rows = np.asarray(table["parent"]).size
    spill = np.asarray(table["spill_m"], dtype=np.float64)
    first, second = np.asarray(table["first_child"]), np.asarray(table["second_child"])
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
    highest = np.full(rows, -np.inf)                         # the highest ground of each hollow
    np.maximum.at(highest, own[held], surface[held])
    for k in np.flatnonzero(first >= 0):                     # parts before wholes
        highest[k] = max(highest[k], highest[first[k]], highest[second[k]])
    level = np.full(rows, np.nan)
    for u in np.flatnonzero(one & (unit == np.arange(rows))):
        if overflows[u]:
            level[u] = spill[u] if np.isfinite(spill[u]) else (highest[u] if np.isfinite(highest[u]) else np.nan)
        elif np.isfinite(top_ground[u]):
            level[u] = top_ground[u]
        elif first[u] >= 0:
            level[u] = spill[first[u]]                       # two full parts and nothing more: the lake stands at their pass
    lake = np.where(share > 0.0, unit[np.maximum(own, 0)], -1)
    return share, level, lake


@njit(cache=True)
def _through_lakes(stack, recv, values, crossing, held):
    """values (months, n) summed down the receivers, with what each lake that overflows keeps taken off where the
    water leaves it. Returns (passing, passed, reached): per month and cell the water passing before the lake's
    share is applied, and per row of the table the share a lake that overflows passes on and the water that
    reaches it in the year. A closed lake needs no rule here: its cells drain to its bottom, which has no receiver,
    so nothing that enters it is handed on. [MEASURED: on 60 rough grounds under random climates no cell of a closed
    lake had a receiver outside that lake, and on 1,110 more of the fourth check of build step 2. That check also built
    the one case in which a cell has: a hollow that receives less than a millionth of a cubic metre of water a year,
    over ground that loses nothing when flooded. The water concerned is that millionth.]"""
    months, n = values.shape
    passing = values.copy()
    passed = np.zeros(held.size)
    reached = np.zeros(held.size)
    for k in range(n - 1, -1, -1):
        i = stack[k]
        r = recv[i]
        if r < 0:
            continue
        u = crossing[i]
        f = 1.0
        if u >= 0:
            if crossing[r] != u:                             # the outlet cell: the lake passes on what it does not lose
                year = 0.0
                for m in range(months):
                    year += passing[m, i]
                reached[u] = year
                f = (year - held[u]) / year if year > held[u] else 0.0
                passed[u] = f
        for m in range(months):
            passing[m, r] += f * passing[m, i]
    return passing, passed, reached


def lake_flows(table, label, recv, surface, nbr, share, lake, runoff, extra, overflows, ties=None):
    """The water through the lakes, month by month.

    label    per cell, the hollow with one bottom that it drains into (0: it drains to the sea)
    recv     per cell, its receiver on dry ground; surface, nbr: the ground and the neighbours of every cell
    share, lake  per cell, the flooded share and the row of its lake (from flooded())
    runoff   (months, n): the water each cell sheds in each month, as if none of it were flooded (m3 a month)
    ties     how exact ties among the ways across a lake are settled (drainage.Ties)

    Returns a dict:
      discharge  (months, n) m3 a month: the water passing through each cell. Inside a lake that overflows: the
                 share of the passing water that will leave the lake. In a cell of a closed lake: the flow over
                 the part of the cell that is not flooded.
      passing    (months, n) m3 a month: the water passing through each cell before that share is taken
      receivers  per cell, the way the water takes: as `recv`, but across each lake that overflows to its outlet
                 cell and from there to the cell beyond the pass
      stack      the flow stack of those receivers
      crossing   per cell, the row of the lake that overflows whose water covers it (-1 for none)
      lakes      a dict of arrays, one entry per lake that receives water: row (in the table of hollows), inflow,
                 loss and outflow (m3 a year), left_over (m3 a year: in a lake with no way out, what reaches it
                 beyond what its whole surface can lose), overflows, and the cell its overflow runs into (-1 for none)
    """
    parent = np.asarray(table["parent"])
    first = np.asarray(table["first_child"])
    beyond = np.asarray(table["spill_into_cell"])
    bottom = np.asarray(table["bottom_cell"])
    rows = parent.size
    one, unit = lake_units(table, overflows)
    held = np.array(extra, dtype=np.float64)                 # the loss of a lake: its own and that of its full parts
    for k in range(1, rows):
        if one[k] and parent[k] >= 0 and one[parent[k]]:
            held[parent[k]] += held[k]
    lakes = np.flatnonzero(one & (unit == np.arange(rows)))
    runs_over = lakes[overflows[lakes] & (beyond[lakes] >= 0)]
    real, crossing = dr.through_full_hollows(recv, surface, nbr, label, table, runs_over, ties)
    stack = dr.flow_stack(real)
    closed = np.where((crossing < 0) & (share > 0.0), lake, -1).astype(np.int64)
    passing, passed, reached = _through_lakes(stack, real, np.ascontiguousarray(runoff, dtype=np.float64), crossing, held)
    counts = np.where(crossing >= 0, passed[np.maximum(crossing, 0)], np.where(closed >= 0, 1.0 - share, 1.0))
    discharge = passing * counts
    year = passing.sum(axis=0)
    leaves = np.flatnonzero((first < 0) & (np.arange(rows) > dr.SEA))
    arriving = np.zeros(rows)                                # what runs to the bottoms of each lake that keeps its water
    np.add.at(arriving, unit[leaves], year[bottom[leaves]])
    arriving[runs_over] = reached[runs_over]
    out = {"row": [], "inflow": [], "loss": [], "outflow": [], "left_over": [], "overflows": [], "into_cell": []}
    for u in lakes.tolist():
        if not (arriving[u] > DUST or held[u] > 0.0):
            continue
        runs = bool(overflows[u]) and beyond[u] >= 0
        beyond_loss = max(arriving[u] - held[u], 0.0)
        out["row"].append(u); out["inflow"].append(float(arriving[u])); out["loss"].append(float(held[u]))
        out["outflow"].append(beyond_loss if runs else 0.0)
        out["left_over"].append(beyond_loss if (overflows[u] and not runs) else 0.0)
        out["overflows"].append(runs)
        out["into_cell"].append(int(beyond[u]) if runs else -1)
    kinds = {"row": np.int64, "into_cell": np.int64, "overflows": bool}
    return {"discharge": discharge, "passing": passing, "receivers": real, "stack": stack, "crossing": crossing,
            "lakes": {name: np.array(col, dtype=kinds.get(name, np.float64)) for name, col in out.items()}}
