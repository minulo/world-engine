"""What decides where the ground cannot, and the rules of the table of hollows (design, Layer 9).

Exact ties are common: every coast (one water level, and wide stretches of sea floor at one depth), and all
relief given in whole metres. The first part holds the routing library to its order of settling them, and to
never using a cell's number where it was handed an order. The second part breaks the table of hollows one rule
at a time and asks for the refusal that names that rule."""
import numpy as np
import pytest

from worldengine.library import drainage as dr
from worldengine.library import lakes as lk
from worldengine.mesh import get_mesh
from worldengine.testing import Harness

from test_water import R, angle_from, drained, lake_case, region_of, rough_ground, three_pits, two_bowls, watered

STEP = 40.0                 # metres: the ground of these tests comes in whole steps, as measured relief does


# ------------------------------------------------------------------------------------------ ties
def stepped(m, seed):
    """Rough ground in whole steps of 40 m, under a sea whose floor lies at three depths: level ground, level
    floors, passes of equal height and coasts with equal beds, all over. Returns surface, sea, bed."""
    rng = np.random.default_rng(seed)
    ground = np.round(rough_ground(m, seed, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0)) / STEP) * STEP
    shore = np.round(np.quantile(ground, 0.15) / STEP) * STEP
    sea = ground < shore                                                         # land at the height of the water stays land
    bed = np.where(sea, shore - 1000.0 * rng.integers(1, 4, m.n), ground)
    return np.where(sea, shore, ground), sea, bed


def given_ties(m, seed, choices=3):
    """An order for ties that has nothing to do with the cell numbers: each pair of neighbours gets one of a few
    widths, so that the widths themselves often tie, and the cells an order drawn at random."""
    rng = np.random.default_rng(1000 + seed)
    width = rng.integers(0, choices, m.edge_cells.shape[0]).astype(np.float64)
    way = np.where(m.nbr >= 0, width[np.maximum(m.nbr_edge, 0)], -np.inf)
    return dr.Ties(way=way, edge=width, rank=rng.permutation(m.n))


def routed(surface, sea, nbr, edge_cells, area, bed, ties):
    recv = dr.receivers(surface, sea, nbr, bed, ties)
    stack = dr.flow_stack(recv)
    label, table = dr.hollows(surface, sea, recv, stack, edge_cells, area, bed, ties)
    full = dr.overflow_receivers(recv, surface, nbr, label, table, ties)
    return recv, stack, label, table, full


def described(table, label, to):
    """The table of hollows in words that do not depend on the order of its rows: each hollow by the bottoms inside
    it, with its pass, its family and its lake. `to` maps cell numbers. Returns (what must be equal, what must be close)."""
    bottom = table["bottom_cell"]
    name = lambda k: None if k < 0 else frozenset(int(to(bottom[j])) for j in region_of(table, k))
    cell = lambda c: None if c < 0 else int(to(c))
    exact, close = {}, {}
    for k in range(1, len(bottom)):
        spill = table["spill_m"][k]
        into = int(table["spill_into_hollow"][k])
        exact[name(k)] = (None if np.isnan(spill) else float(spill), cell(table["spill_from_cell"][k]), cell(table["spill_into_cell"][k]),
                          "no way out" if into < 0 else "sea" if into == 0 else cell(bottom[into]),
                          name(table["parent"][k]), name(table["sibling"][k]), name(table["first_child"][k]), name(table["second_child"][k]),
                          cell(bottom[k]), float(table["bottom_m"][k]))
        close[name(k)] = (table["area_when_full_m2"][k], table["volume_when_full_m3"][k])
    return exact, close


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_numbering_the_cells_otherwise_changes_nothing_once_the_order_for_ties_is_given(seed):
    """The cells get new numbers at random, the neighbours of every cell and the pairs of neighbours are listed in
    another order, and the order for ties is carried along with the cells. Every receiver, every hollow, every
    pass and every way across a full lake must then be the same cell as before. A place where the library still
    used a cell's own number, or the order in which it happened to meet the cells, shows here."""
    m = get_mesh(4)
    n, around = m.nbr.shape
    area = m.area * R * R
    surface, sea, bed = stepped(m, seed)
    ties = given_ties(m, seed)
    recv, stack, label, table, full = routed(surface, sea, m.nbr, m.edge_cells, area, bed, ties)

    rng = np.random.default_rng(2000 + seed)
    new = rng.permutation(n)                                                     # new[i]: the new number of cell i
    old = np.argsort(new)                                                        # old[j]: the cell that got the number j
    to = lambda cells: np.where(np.asarray(cells) >= 0, new[np.maximum(cells, 0)], -1)
    slots = np.argsort(rng.random((n, around)), axis=1)
    nbr2 = to(np.take_along_axis(m.nbr, slots, axis=1))[old]
    pairs = rng.permutation(m.edge_cells.shape[0])
    edges2 = np.sort(to(m.edge_cells[pairs]), axis=1)
    ties2 = dr.Ties(way=np.take_along_axis(ties.way, slots, axis=1)[old], edge=ties.edge[pairs], rank=ties.rank[old])
    recv2, stack2, label2, table2, full2 = routed(surface[old], sea[old], nbr2, edges2, area[old], bed[old], ties2)

    assert np.array_equal(recv2[new], to(recv))
    assert np.array_equal(full2[new], to(full))
    assert np.array_equal(label2[new] > 0, label > 0)
    inside = label > 0
    assert np.array_equal(table2["bottom_cell"][label2[new]][inside], to(table["bottom_cell"][label])[inside])
    exact, close = described(table, label, lambda c: new[c])
    exact2, close2 = described(table2, label2, lambda c: c)
    assert exact2 == exact
    assert all(np.allclose(close2[k], close[k], rtol=1e-12, equal_nan=True) for k in close)
    values = rng.random(n) * (rng.random(n) < 0.7)                               # many sources that give nothing, and
    values[::5] = 0.3                                                            # many that give the same
    source = dr.largest_upstream(stack, recv, values, ties.rank)
    assert np.array_equal(dr.largest_upstream(stack2, recv2, values[old], ties2.rank)[new], to(source))

    # the case: this ground is full of ties, and each step of the order decides some of them
    level = sea | (recv >= 0)
    stuck_then_drained = (~sea & (recv >= 0) & (surface[np.maximum(recv, 0)] == surface)).sum()
    assert stuck_then_drained > 50                                               # level ground
    floors = [k for k in range(1, len(table["parent"])) if table["first_child"][k] < 0
              and (surface[m.nbr[table["bottom_cell"][k]][m.nbr[table["bottom_cell"][k]] >= 0]] == table["bottom_m"][k]).any()]
    assert len(floors) > 5 and level.sum() > 0                                   # level floors
    turned = dr.Ties(ties.way, ties.edge, ties.rank.max() - ties.rank)           # the order of the cells the other way round
    even = dr.Ties(np.where(m.nbr >= 0, 0.0, -np.inf), np.zeros_like(ties.edge), ties.rank)     # every way equally wide
    on_level_ground = ~sea & (recv >= 0) & (surface[np.maximum(recv, 0)] == surface)
    for other in (turned, even):
        recv3, _, _, table3, full3 = routed(surface, sea, m.nbr, m.edge_cells, area, bed, other)
        assert (recv3 != recv).sum() > 20 and (full3 != full).sum() > 20
        assert ((recv3 != recv) & on_level_ground).sum() >= 3                    # on level ground as well: its ways are settled the same way
        assert described(table3, None, int)[0] != exact


def test_the_count_of_ties_is_the_count_a_walk_over_the_cells_gives():
    """count_ties says how many choices are ties and which step of the order settles each: the tools print it for a
    world and for Earth's relief. Here against a walk over the cells, one by one."""
    m = get_mesh(4)
    surface, sea, bed = stepped(m, 2)
    ties = given_ties(m, 2)
    want = dict(choose=0, tied=0, by_bed=0, by_width=0, by_number=0, level=0)
    for c in np.flatnonzero(~sea):
        ring = [(int(j), k) for k, j in enumerate(m.nbr[c]) if j >= 0]
        lowest = min(surface[j] for j, _ in ring)
        want["level"] += lowest == surface[c]
        if lowest >= surface[c]:
            continue
        want["choose"] += 1
        low = [(j, k) for j, k in ring if surface[j] == lowest]
        if len(low) == 1:
            continue
        want["tied"] += 1
        deep = [(j, k) for j, k in low if bed[j] == min(bed[i] for i, _ in low)]
        wide = [(j, k) for j, k in deep if ties.way[c, k] == max(ties.way[c, i] for _, i in deep)]
        want["by_bed" if len(deep) == 1 else "by_width" if len(wide) == 1 else "by_number"] += 1
    assert dr.count_ties(surface, sea, m.nbr, bed, ties) == want
    assert min(want.values()) > 10 and want["tied"] == want["by_bed"] + want["by_width"] + want["by_number"]


def test_the_ties_of_a_mesh_go_to_the_wider_way_and_rounding_errors_seldom_settle_them():
    m = get_mesh(4)
    t = dr.mesh_ties(m)
    assert np.array_equal(t.rank, np.arange(m.n)) and t.edge.shape == (m.edge_cells.shape[0],)
    valid = m.nbr >= 0
    assert np.array_equal(t.way[valid], t.edge[m.nbr_edge[valid]]) and np.all(np.isneginf(t.way[~valid]))
    wider = np.argsort(m.edge_dual)
    assert np.all(np.diff(t.edge[wider]) >= 0) and np.unique(t.edge).size > 20   # the longer boundary never ranks lower
    # A fifth of a turn about the axis maps the mesh onto itself. The boundaries around a cell and around its image
    # are the same lengths, but worked out from other numbers, so they differ in their last digits: as ties they
    # must still count as equal.
    turn = np.deg2rad(72.0)
    rz = np.array([[np.cos(turn), -np.sin(turn), 0.0], [np.sin(turn), np.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    goes_to = np.argmax(m.xyz @ rz.T @ m.xyz.T, axis=1)
    assert np.array_equal(np.sort(t.way, axis=1), np.sort(t.way[goes_to], axis=1))
    lengths = np.where(valid, m.nbr_dual, -np.inf)
    assert not np.array_equal(np.sort(lengths, axis=1), np.sort(lengths[goes_to], axis=1))      # the case: the raw lengths differ
    # two boundaries a part in ten billion apart count as one width; a part in a hundred million apart do not
    class Two:
        edge_dual = np.array([1.0, 1.0 + 1e-10, 1.0 - 1e-8])
        nbr = np.array([[1, 2, -1], [0, 2, -1], [0, 1, -1]])
        nbr_edge = np.array([[0, 1, -1], [0, 2, -1], [1, 2, -1]])
        n = 3
    two = dr.mesh_ties(Two)
    assert two.edge[0] == two.edge[1] and two.edge[2] < two.edge[0]
    # ... but the rounding is a grid and not a tolerance: two lengths on either side of a rounding step are told
    # apart however near they are. Here they differ by two parts in ten trillion
    Two.edge_dual = np.array([1.0, 0.5 + 0.4999e-9, 0.5 + 0.5001e-9])
    split = dr.mesh_ties(Two)
    assert split.edge[2] == split.edge[1] + 1.0


@pytest.mark.parametrize("level", [5, 6])
def test_how_often_the_rounding_errors_of_the_mesh_still_settle_a_tie(level):
    """What mesh_ties says of itself. The mesh has boundaries that are mirror images of each other and exactly as
    long; worked out, they differ by rounding errors. In the sorted list of all lengths those are the neighbours
    that differ by less than 1e-11 of the longest: nearly all of the list. The rounding must make them equal, so
    that the order of the cells settles such a tie and not the rounding error, and it does but for the few that
    fall on either side of a rounding step [MEASURED in the build environment: none of 30,448 at level 5, 2 of
    121,824 at level 6, 29 of 487,377 at level 7. The counts may differ on another processor, so the test asks
    for under one in a thousand]."""
    m = get_mesh(level)
    order = np.argsort(m.edge_dual)
    raw, rounded = m.edge_dual[order], dr.mesh_ties(m).edge[order]
    gap = np.diff(raw) / raw.max()
    alike = gap < 1e-11
    assert alike.sum() > 0.9 * gap.size                                         # the case: the mesh is full of such pairs
    assert (np.diff(raw)[alike] > 0).sum() > 0.5 * alike.sum()                   # ... and their worked-out lengths do differ
    split = alike & (np.diff(rounded) != 0)
    assert split.sum() < 1e-3 * alike.sum(), (int(split.sum()), int(alike.sum()))
    # unlike lengths stay unlike where they differ by more than a few rounding steps
    assert np.all(np.diff(rounded)[gap > 2.0 * dr.EQUAL_WIDTHS] > 0)


def test_drainage_settles_its_ties_by_the_mesh_and_not_by_the_cell_numbers():
    """Drainage on stepped ground: its fields are those the library gives with the ties of the mesh, in each of the
    three places where it hands them over, and not those the cell numbers alone would give."""
    m = get_mesh(4)
    area = m.area * R * R
    ground = np.round(rough_ground(m, 7, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0)) / STEP) * STEP
    hh, area, sea, out = drained(ground, area[ground < -200.0].sum() * 300.0)
    wet = sea.fields["ocean_mask"]
    surface = dr.drainage_surface(ground, sea.fields["sea_depth"], wet, sea.tables["seas"]["surface_m"])
    ties = dr.mesh_ties(m)
    recv, stack, label, table, full = routed(surface, wet, m.nbr, m.edge_cells, area, ground, ties)
    f, t = out.fields, out.tables["hollows"]
    drained_through = lambda ways: dr.accumulate(dr.flow_stack(ways), ways, np.where(wet, 0.0, area.astype(np.float64)))
    passes = lambda tb: (list(tb["spill_from_cell"]), list(tb["spill_into_cell"]), list(tb["parent"]))
    assert np.array_equal(f["flow_receiver"], recv)
    assert np.array_equal(f["depression_id"], label) and passes(t) == passes(table)
    assert np.allclose(f["drainage_area"], drained_through(full), rtol=1e-6)     # the field is stored in single precision
    # the case: handed no ties, each of the three library calls gives something else on this ground
    plain = dr.receivers(surface, wet, m.nbr, ground)
    assert (plain != recv).sum() > 20
    assert passes(dr.hollows(surface, wet, recv, stack, m.edge_cells, area, ground)[1]) != passes(table)
    by_number = drained_through(dr.overflow_receivers(recv, surface, m.nbr, label, table))       # another way across the lakes
    assert (np.abs(by_number - drained_through(full)) > 1e-3 * drained_through(full)).sum() > 20
    # on a coast the wider way is the longer shore: a land cell beside several sea cells of one depth drains to the
    # one it shares the longest boundary with
    checked = 0
    for c in np.flatnonzero(~wet):
        ring = [int(j) for j in m.nbr[c] if j >= 0]
        lowest = [j for j in ring if surface[j] == min(surface[i] for i in ring)]
        deepest = [j for j in lowest if ground[j] == min(ground[i] for i in lowest)]
        if surface[lowest[0]] < surface[c] and len(deepest) > 1 and all(wet[j] for j in lowest):
            widths = {j: ties.way[c, list(m.nbr[c]).index(j)] for j in deepest}
            widest = [j for j in deepest if widths[j] == max(widths.values())]
            if len(widest) == 1:
                assert recv[c] == widest[0]
                checked += 1
    assert checked >= 5


def test_both_processes_take_their_ties_from_one_function_of_the_library(monkeypatch):
    """Drainage and Hydrology settle ties alike because both ask library/drainage.mesh_ties for them and hand on what
    it gives: Hydrology to the ways across its lakes and to the choice among equal sources of a river. The Earth
    tools stand in for that one function to settle the ties of measured relief otherwise; this is what they rely on."""
    m = get_mesh(4)
    ground = np.round(rough_ground(m, 7, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0)) / STEP) * STEP
    given = given_ties(m, 5)
    asked = []
    monkeypatch.setattr(dr, "mesh_ties", lambda mesh: asked.append(mesh) or given)
    seen = {}
    real_flows, real_source, real_receivers, real_hollows, real_overflow = lk.lake_flows, dr.largest_upstream, dr.receivers, dr.hollows, dr.overflow_receivers
    monkeypatch.setattr(lk, "lake_flows", lambda *a, **k: seen.__setitem__("flows", (a, k)) or real_flows(*a, **k))
    monkeypatch.setattr(dr, "largest_upstream", lambda *a, **k: seen.__setitem__("source", (a, k)) or real_source(*a, **k))
    monkeypatch.setattr(dr, "receivers", lambda *a, **k: seen.__setitem__("receivers", (a, k)) or real_receivers(*a, **k))
    monkeypatch.setattr(dr, "hollows", lambda *a, **k: seen.__setitem__("hollows", (a, k)) or real_hollows(*a, **k))
    monkeypatch.setattr(dr, "overflow_receivers", lambda *a, **k: seen.__setitem__("overflow", (a, k)) or real_overflow(*a, **k))
    area = m.area * R * R
    hh, area, sea, d, out, reads = watered(ground, area[ground < -200.0].sum() * 300.0, 150.0, 20.0, 300.0)
    holds = lambda name: any(x is given for x in seen[name][0]) or any(x is given for x in seen[name][1].values())
    assert len(asked) == 2 and all(mesh is hh.mesh for mesh in asked)
    assert holds("receivers") and holds("hollows") and holds("overflow") and holds("flows")
    assert any(x is given.rank for x in seen["source"][0]) or any(x is given.rank for x in seen["source"][1].values())
    assert out.tables["lakes"]["overflows"].any()                                # the case: lakes that water crosses


def ring_of(m, centre):
    """The neighbours of a cell, and three of them of which no two are neighbours of each other."""
    ring = [int(j) for j in m.nbr[centre] if j >= 0]
    apart = lambda a, b: b not in m.nbr[a]
    for a in ring:
        for b in ring:
            for c in ring:
                if a < b < c and apart(a, b) and apart(b, c) and apart(a, c):
                    return ring, (a, b, c)
    raise AssertionError("no three neighbours apart")


def hill_with_a_hole(m, centre=100):
    """Ground that rises away from one cell on every side, so that only what a test puts beside that cell is low."""
    away = np.rad2deg(np.arccos(np.clip(m.xyz @ m.xyz[centre], -1, 1)))
    return 500.0 + 10.0 * away


def test_water_leaves_a_hollow_toward_the_lowest_ground_beyond_its_outlet_and_then_toward_the_lowest_bed():
    """The outlet cell of a hollow stands at 10 m. Beyond the hollow it has two lower neighbours: a sea cell, with
    its water at 0 m over a floor at -3,000 m, and dry ground at -50 m that is the bottom of a second hollow. Both
    passes are exactly 10 m high. A single cell's water runs to the lowest surface, the dry ground, so the hollow
    overflows into the second hollow, and the two together into the sea; ordering the passes by the bed of the far
    side would send it straight to the sea. Then the same outlet beside two sea cells with floors at -3,000 and
    -500 m: the water leaves over the deeper floor, whatever the numbers of the cells."""
    m = get_mesh(4)
    area = m.area * R * R
    here = 100
    ring, (one, two, three) = ring_of(m, here)
    ground = hill_with_a_hole(m, here)
    ground[here] = 10.0
    ground[one] = -100.0                                                         # the bottom of the hollow the outlet drains into
    sea = np.zeros(m.n, dtype=bool)
    # 1. a sea cell and lower dry ground
    dry, wet = two, three
    bed = ground.copy()
    bed[dry], bed[wet] = -50.0, -3000.0
    sea[wet] = True
    surface = np.where(sea, 0.0, bed)
    recv = dr.receivers(surface, sea, m.nbr, bed)
    assert recv[here] == one and recv[one] == -1 and recv[dry] == -1
    label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area, bed)
    first, second = int(label[one]), int(label[dry])
    assert label[here] == first and first != second and min(first, second) > 0
    assert table["spill_m"][first] == 10.0 and table["spill_from_cell"][first] == here and table["spill_into_cell"][first] == dry
    both = int(table["parent"][first])
    assert both > 0 and table["parent"][second] == both and table["sibling"][first] == second
    assert table["spill_m"][both] == 10.0 and table["spill_from_cell"][both] == here and table["spill_into_cell"][both] == wet
    assert table["spill_into_hollow"][both] == 0
    # 2. two sea cells: the deeper floor wins, whichever of the two has the lower number
    for deep, shallow in ((two, three), (three, two)):
        sea = np.zeros(m.n, dtype=bool)
        sea[[deep, shallow]] = True
        bed = ground.copy()
        bed[deep], bed[shallow] = -3000.0, -500.0
        surface = np.where(sea, 0.0, bed)
        recv = dr.receivers(surface, sea, m.nbr, bed)
        label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area, bed)
        k = int(label[one])
        assert table["parent"][k] == -1 and table["spill_from_cell"][k] == here and table["spill_into_cell"][k] == deep
        # with the ties of the mesh as well: the bed still comes first
        mesh_ties = dr.mesh_ties(m)
        label, table = dr.hollows(surface, sea, dr.receivers(surface, sea, m.nbr, bed, mesh_ties), dr.flow_stack(recv), m.edge_cells, area, bed, mesh_ties)
        assert table["spill_into_cell"][int(label[one])] == deep


def test_a_hollow_with_two_equal_passes_overflows_over_the_wider_and_then_by_the_order_of_the_cells():
    """The outlet cell of a hollow beside two sea cells whose floors are equally deep: two passes of one height, one
    far side and one bed. The hollow overflows across the wider boundary, whatever the order of the cells says;
    with boundaries equally wide, into the cell that comes first in that order; and its water, once the hollow is
    full, takes the same way."""
    m = get_mesh(4)
    area = m.area * R * R
    here = 100
    ring, (one, two, three) = ring_of(m, here)
    ground = hill_with_a_hole(m, here)
    ground[here], ground[one] = 10.0, -100.0
    sea = np.zeros(m.n, dtype=bool)
    sea[[two, three]] = True
    bed = ground.copy()
    bed[two] = bed[three] = -3000.0
    surface = np.where(sea, 0.0, bed)
    boundary = lambda j: int(m.nbr_edge[here, list(m.nbr[here]).index(j)])

    def leaves(width, rank):
        ties = dr.Ties(way=np.where(m.nbr >= 0, width[np.maximum(m.nbr_edge, 0)], -np.inf), edge=width, rank=rank)
        recv = dr.receivers(surface, sea, m.nbr, bed, ties)
        assert recv[here] == one
        label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area, bed, ties)
        k = int(label[one])
        assert table["parent"][k] == -1 and table["spill_from_cell"][k] == here and table["spill_m"][k] == 10.0
        full = dr.overflow_receivers(recv, surface, m.nbr, label, table, ties)
        assert full[here] == table["spill_into_cell"][k]                         # the water takes the pass the table names
        return int(table["spill_into_cell"][k])

    up, down = np.arange(m.n), np.arange(m.n)[::-1].copy()
    for wide in (two, three):
        width = np.ones(m.edge_cells.shape[0])
        width[boundary(wide)] = 2.0
        assert leaves(width, up) == wide and leaves(width, down) == wide         # the wider way, whatever the order
    even = np.ones(m.edge_cells.shape[0])
    assert leaves(even, up) == min(two, three) and leaves(even, down) == max(two, three)      # equally wide: the order of the cells
    # the mesh's own ties: its longer boundary, if the two differ
    t = dr.mesh_ties(m)
    if t.edge[boundary(two)] != t.edge[boundary(three)]:
        assert leaves(t.edge, t.rank) == max((two, three), key=lambda j: t.edge[boundary(j)])


def test_level_ground_beside_the_sea_drains_over_the_deepest_bed():
    """A cell of land exactly at the height of the water, beside two sea cells: it has no lower neighbour, so it is
    level ground, and its way out is the sea cell whose floor lies deepest, whichever has the lower number."""
    m = get_mesh(4)
    here = 100
    ring, (one, two, three) = ring_of(m, here)
    for deep, shallow in ((two, three), (three, two)):
        ground = hill_with_a_hole(m, here)
        sea = np.zeros(m.n, dtype=bool)
        sea[[deep, shallow]] = True
        bed = ground.copy()
        bed[here], bed[deep], bed[shallow] = 0.0, -3000.0, -500.0
        surface = np.where(sea, 0.0, bed)
        assert dr.receivers(surface, sea, m.nbr, bed)[here] == deep
        assert dr.receivers(surface, sea, m.nbr, bed, dr.mesh_ties(m))[here] == deep
    assert dr.receivers(surface, sea, m.nbr)[here] == min(two, three)             # handed no bed: the cell numbers


def test_drainage_hands_the_sea_floor_to_the_hollows():
    """The same outlet beside two sea cells, through the process: the hollow overflows over the deeper floor. The
    deeper floor is given to the sea cell that the widths of the mesh and the cell numbers would not have chosen."""
    m = get_mesh(4)
    here = 100
    ring, (one, two, three) = ring_of(m, here)
    ties = dr.mesh_ties(m)
    slot = lambda j: int(np.flatnonzero(m.nbr[here] == j)[0])
    shallow, deep = sorted((two, three), key=lambda j: (-ties.way[here, slot(j)], j))      # the mesh alone would pick `shallow`
    ground = hill_with_a_hole(m, here)
    ground[here], ground[one] = 10.0, -100.0
    ground[deep], ground[shallow] = -3000.0, -500.0
    wet = np.zeros(m.n, dtype=bool)
    wet[[deep, shallow]] = True
    hh = Harness(level=4)
    area = hh.run("PlanetGeometry").fields["cell_area"]
    seas = {"surface_m": np.array([0.0]), "area_m2": np.array([float(area[wet].sum())]), "volume_m3": np.array([float((area * -ground)[wet].sum())]),
            "cells": np.array([2], dtype=np.int32), "lowest_cell": np.array([deep], dtype=np.int32)}
    out = hh.run("Drainage", reads={"elevation": ground, "ocean_mask": wet, "sea_depth": np.where(wet, -ground, 0.0), "cell_area": area},
                 tables={"seas": seas})
    t = out.tables["hollows"]
    k = int(out.fields["depression_id"][one])
    assert k > 0 and t["spill_from_cell"][k] == here and t["spill_into_cell"][k] == deep
    assert out.fields["basin_id"][one] == here                                   # with the hollow full, its water leaves the land here


def test_the_outlet_of_a_full_hollow_must_lie_in_that_hollow():
    m = get_mesh(4)
    area = m.area * R * R
    ground = rough_ground(m, 3, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
    shore = np.quantile(ground, 0.1)
    sea = ground < shore
    surface = np.where(sea, shore, ground)
    recv = dr.receivers(surface, sea, m.nbr)
    label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area)
    rows = np.arange(len(table["parent"]))
    tops = rows[(table["parent"] < 0) & (rows > 0)]
    wrong = {name: np.array(col) for name, col in table.items()}
    wrong["spill_from_cell"][tops[0]] = int(np.flatnonzero((label == 0) & ~sea)[0])      # ground that drains to the sea
    with pytest.raises(ValueError, match="names an outlet cell for hollow .* that does not lie in that hollow"):
        dr.through_full_hollows(recv, surface, m.nbr, label, wrong, tops)


# ------------------------------------------------------------------------------------------ the rules of the table of hollows
@pytest.fixture(scope="module")
def rough():
    """Rough ground with many hollows inside one another, and the table Drainage's library writes for it."""
    m = get_mesh(4)
    area = m.area * R * R
    ground = rough_ground(m, 4242, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
    shore = np.quantile(ground, 0.3)
    sea = ground < shore
    bed = ground.copy()
    surface = np.where(sea, shore, ground)
    recv = dr.receivers(surface, sea, m.nbr, bed)
    label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area, bed)
    lk.check_table(table, label, recv, sea, surface)                              # as written, it keeps its rules
    return dict(m=m, table=table, label=label, recv=recv, sea=sea, ground=surface)


def leaves_of(table, k):
    return set(region_of(table, k))


BREAKAGES = []


def breaks(words):
    """Registers a way of breaking the table, with the words of the refusal it must meet."""
    def register(change):
        BREAKAGES.append(pytest.param(change, words, id=change.__name__))
        return change
    return register


class Case:
    """The table and what belongs to it, as copies a breakage may change; and some rows a breakage may want."""

    def __init__(self, base):
        self.t = {name: np.array(col) for name, col in base["table"].items()}
        self.label, self.recv, self.sea, self.ground = (base[k].copy() for k in ("label", "recv", "sea", "ground"))
        self.m = base["m"]
        t = self.t
        self.rows = len(t["parent"])
        row = np.arange(self.rows)
        self.single = int((t["first_child"][1:] < 0).sum())
        self.merged = int(np.flatnonzero(t["first_child"] >= 0)[0])               # a hollow made of two
        self.part = int(np.flatnonzero((t["first_child"] < 0) & (t["parent"] >= 0) & (row > 0))[0])      # one bottom, inside another
        self.merged_part = int(np.flatnonzero((t["first_child"] >= 0) & (t["parent"] >= 0))[0])
        self.tops = row[(t["parent"] < 0) & (row > 0)]
        self.top = int(self.tops[0])
        self.a, self.b = 1, 2                                                     # two hollows with one bottom

    def check(self):
        lk.check_table(self.t, self.label, self.recv, self.sea, self.ground)


@breaks("it has no column sibling")
def a_column_is_missing(c):
    c.t.pop("sibling")


@breaks("row 0 must stand for the sea")
def the_sea_is_given_a_parent(c):
    c.t["parent"][0] = c.merged


@breaks("row 0 must stand for the sea")
def the_sea_is_given_a_part(c):
    c.t["first_child"][0] = 1


@breaks("must come first, in rows 1 to H")
def a_hollow_made_of_two_stands_among_those_with_one_bottom(c):
    """The last hollow with one bottom and the first made of two change rows, and everything that names a row
    follows: only the order of the rows is against the rules."""
    one, two = c.single, c.single + 1
    swap = np.arange(c.rows)
    swap[[one, two]] = [two, one]
    for name in c.t:
        c.t[name] = c.t[name][swap]
    for name in ("parent", "sibling", "first_child", "second_child", "spill_into_hollow"):
        c.t[name] = np.where(c.t[name] >= 0, swap[np.maximum(c.t[name], 0)], c.t[name]).astype(np.int32)
    c.label = swap[c.label]


@breaks("must name two different parts, both in earlier rows")
def a_hollow_names_one_row_as_both_its_parts(c):
    c.t["second_child"][c.merged] = c.t["first_child"][c.merged]


@breaks("must name two different parts, both in earlier rows")
def a_part_stands_in_a_later_row_than_its_hollow(c):
    c.t["first_child"][c.merged] = c.rows - 1 if c.merged != c.rows - 1 else c.merged


@breaks("a part of a hollow must name that hollow as its parent")
def a_part_does_not_name_its_hollow_as_parent(c):
    c.t["parent"][c.t["first_child"][c.merged]] = -1


@breaks("a parent must stand in a later row than its parts")
def a_hollow_inside_no_other_names_an_earlier_row_as_parent(c):
    top = int(c.tops[c.tops > 1][0])
    c.t["parent"][top] = 1


@breaks("the two parts of a hollow must name each other as sibling")
def a_part_names_itself_as_sibling(c):
    k = c.t["first_child"][c.merged]
    c.t["sibling"][k] = k


@breaks("the two parts of a hollow must name each other as sibling")
def a_part_names_no_sibling(c):
    c.t["sibling"][c.t["first_child"][c.merged]] = -1


@breaks("a hollow inside no other has no sibling")
def a_hollow_inside_no_other_names_a_sibling(c):
    c.t["sibling"][c.top] = 1 if c.top != 1 else 2


@breaks("depression_id must be 0 or the row of a hollow with one bottom")
def a_cell_is_said_to_drain_into_a_hollow_made_of_two(c):
    c.label[np.flatnonzero(c.label > 0)[0]] = c.rows - 1


@breaks("depression_id must be 0 or the row of a hollow with one bottom")
def a_cell_has_no_hollow_and_not_the_sea(c):
    c.label[np.flatnonzero(c.label > 0)[0]] = -1


@breaks("must be a land cell without a receiver that drains into that hollow")
def a_bottom_has_a_receiver(c):
    c.t["bottom_cell"][c.a] = np.flatnonzero((c.label == c.a) & (c.recv >= 0))[0]


@breaks("must be a land cell without a receiver that drains into that hollow")
def a_bottom_is_a_sea_cell(c):
    c.t["bottom_cell"][c.a] = np.flatnonzero(c.sea)[0]


@breaks("must be a land cell without a receiver that drains into that hollow")
def two_hollows_name_one_bottom(c):
    c.t["bottom_cell"][c.a] = c.t["bottom_cell"][c.b]


@breaks("every land cell without a receiver must be the bottom of one hollow")
def a_bottom_of_the_ground_is_in_no_row(c):
    """A cell on a slope loses its receiver: it is a bottom now, and the table knows nothing of it."""
    cell = int(np.flatnonzero((c.label == 0) & ~c.sea & (c.recv >= 0))[0])
    c.recv[cell] = -1


@breaks("depression_id is .*, but down its receivers its water ends at the bottom of hollow")
def a_cell_is_said_to_drain_into_the_hollow_next_door(c):
    cell = int(np.flatnonzero((c.label == c.a) & (c.recv >= 0))[0])
    c.label[cell] = c.b


@breaks("depression_id is 0, but down its receivers its water ends at the bottom of hollow")
def a_cell_that_drains_into_a_hollow_is_said_to_reach_the_sea(c):
    c.label[np.flatnonzero((c.label == c.a) & (c.recv >= 0))[0]] = 0


@breaks("but down its receivers its water ends in the sea")
def a_cell_that_reaches_the_sea_is_said_to_drain_into_a_hollow(c):
    c.label[np.flatnonzero((c.label == 0) & ~c.sea)[0]] = c.a


@breaks("has the bottom of its deeper part for its bottom")
def a_hollow_made_of_two_names_the_bottom_of_its_shallower_part(c):
    k = c.merged
    one, two = c.t["first_child"][k], c.t["second_child"][k]
    shallower = one if c.t["bottom_m"][one] > c.t["bottom_m"][two] else two
    assert c.t["bottom_m"][one] != c.t["bottom_m"][two]
    c.t["bottom_cell"][k] = c.t["bottom_cell"][shallower]


@breaks("bottom_m is .* m, but its bottom cell stands at")
def the_height_of_a_bottom_is_fifty_metres_out(c):
    c.t["bottom_m"][c.a] += 50.0


@breaks("a hollow inside another must name its pass")
def a_hollow_inside_another_names_no_pass(c):
    c.t["spill_into_cell"][c.part] = -1


@breaks("a hollow with no way out has no value for spill_m")
def a_hollow_without_a_pass_still_has_a_level(c):
    for name in ("spill_into_cell", "spill_from_cell", "spill_into_hollow"):
        c.t[name][c.top] = -1


@breaks("a hollow with no way out has no value for spill_m")
def a_hollow_without_a_pass_still_names_where_it_overflows(c):
    c.t["spill_into_cell"][c.top] = -1
    c.t["spill_m"][c.top] = np.nan


@breaks("a hollow with a pass must give its level and its two cells")
def a_hollow_with_a_pass_has_no_level(c):
    c.t["spill_m"][c.top] = np.nan


@breaks("spill_into_hollow must be the hollow with one bottom that the cell beyond the pass drains into")
def the_pass_is_said_to_lead_into_the_larger_hollow_around_the_far_cell(c):
    c.t["spill_into_hollow"][c.part] = c.t["parent"][c.part]


@breaks("spill_into_hollow must be the hollow with one bottom that the cell beyond the pass drains into")
def the_pass_is_said_to_lead_into_another_hollow(c):
    c.t["spill_into_hollow"][c.part] = [k for k in range(1, c.single + 1) if k != c.t["spill_into_hollow"][c.part]][0]


@breaks("the cell on a hollow's own side of its pass must drain into that hollow")
def the_outlet_cell_lies_outside_its_hollow(c):
    inside = np.isin(c.label, list(leaves_of(c.t, c.top)))
    c.t["spill_from_cell"][c.top] = np.flatnonzero(~inside & ~c.sea)[0]


@breaks("the pass of a part of a hollow must lead into the other part")
def the_pass_of_a_part_leads_past_its_sibling(c):
    k = c.part
    kin = leaves_of(c.t, c.t["sibling"][k]) | {k}
    cell = int(np.flatnonzero(~np.isin(c.label, list(kin)) & (c.label > 0))[0])
    c.t["spill_into_cell"][k], c.t["spill_into_hollow"][k] = cell, c.label[cell]


@breaks("a hollow inside no other cannot overflow into itself")
def a_hollow_inside_no_other_overflows_into_its_own_ground(c):
    c.t["spill_into_cell"][c.top] = c.t["bottom_cell"][c.top]
    c.t["spill_into_hollow"][c.top] = c.label[c.t["bottom_cell"][c.top]]


@breaks("a hollow cannot overflow lower than its parts do")
def a_hollow_overflows_lower_than_its_parts(c):
    k = c.merged_part
    c.t["spill_m"][k] = c.t["spill_m"][c.t["first_child"][k]] - 5.0
    c.t["spill_m"][c.t["sibling"][k]] = c.t["spill_m"][k]


@breaks("the two parts of a hollow meet at one pass, at one level")
def the_two_parts_of_a_hollow_overflow_at_different_levels(c):
    c.t["spill_m"][c.part] -= 0.5


@breaks("spill_m is .* m, but the higher of the two cells of its pass stands at")
def the_level_of_a_pass_is_three_metres_too_high(c):
    c.t["spill_m"][c.top] += 3.0


@breaks("spill_m is .* m, but the higher of the two cells of its pass stands at")
def the_level_of_a_pass_is_three_metres_too_low(c):
    c.t["spill_m"][c.top] -= 3.0


@breaks("spill_m is .* m, but the higher of the two cells of its pass stands at")
def the_field_of_heights_is_on_another_datum(c):
    c.ground += 100.0
    c.t["bottom_m"] = c.t["bottom_m"] + 100.0                                     # the bottoms follow; the passes do not


@pytest.mark.parametrize("change, words", BREAKAGES)
def test_a_table_of_hollows_that_breaks_one_rule_is_refused_in_the_words_of_that_rule(rough, change, words):
    """Hydrology takes the table of hollows from whatever process fills the Drainage slot, and data/tables.yaml states
    the rules that table keeps. Each case breaks the table in one way, leaving the rest as Drainage wrote it, and
    must meet the refusal that names what is wrong: a refusal for another reason would show a check that does not
    work, or one that another check hides."""
    case = Case(rough)
    case.check()                                                                 # as written, the table is accepted
    change(case)
    with pytest.raises(ValueError, match="the table of hollows does not keep its rules: .*" + words):
        case.check()


def test_a_ring_of_hollows_whose_passes_are_all_in_order_is_refused():
    """Three pits, each overflowing into the next and the last toward the sea. The last is made to overflow into the
    first instead: from its true outlet cell into the bottom of the first pit, at the height of the higher of those
    two cells, so that every rule about a single pass is kept. Only the order in which to fill them has no end."""
    m = get_mesh(6)
    area = m.area * R * R
    ground, sea = three_pits(m)
    base = lake_case(m, ground, sea, area, area.copy(), np.zeros((2, m.n)))
    t, label = base["table"], base["label"]
    assert list(t["spill_into_hollow"][1:4]) == [2, 3, 0] and len(t["parent"]) == 4
    ring = {name: np.array(col) for name, col in t.items()}
    here, beyond = int(t["spill_from_cell"][3]), int(t["bottom_cell"][1])
    ring["spill_into_cell"][3], ring["spill_into_hollow"][3] = beyond, 1
    ring["spill_m"][3] = max(ground[here], ground[beyond])
    with pytest.raises(ValueError, match="hollow .* overflows, by way of others, into itself"):
        lk.check_table(ring, label, base["recv"], sea, ground)


def test_hydrology_refuses_a_table_of_hollows_that_breaks_its_rules():
    m = get_mesh(5)
    ground = two_bowls(m)[0]
    volume = (m.area * R * R)[ground < -1000].sum() * 2500.0
    hh, area, sea, d = drained(ground, volume, level=5)
    table = {name: np.array(col) for name, col in d.tables["hollows"].items()}
    table["spill_m"][1] += 3.0
    table["spill_m"][2] += 3.0
    reads = {"precipitation": np.full((12, m.n), 50.0), "snowfall": np.zeros((12, m.n)), "surface_temperature": np.full((12, m.n), 290.0),
             "insolation": np.full((12, m.n), 300.0), "elevation": ground, "height_above_sea": sea.fields["height_above_sea"],
             "flow_receiver": d.fields["flow_receiver"], "depression_id": d.fields["depression_id"], "cell_area": area,
             "ocean_mask": sea.fields["ocean_mask"]}
    with pytest.raises(ValueError, match="the table of hollows does not keep its rules"):
        hh.run("Hydrology", reads=reads, tables={"hollows": table})
    hh.run("Hydrology", reads=reads, tables={"hollows": d.tables["hollows"]})        # and takes the table as Drainage wrote it


def test_under_a_closed_lake_a_cell_counts_the_runoff_of_its_dry_part_only():
    """The two bowls under six wet months and six dry ones. In the wet months the ground sheds water; over the year
    open water loses more than arrives, so the lake stays closed, with one cell half under water. Of that cell, half
    the ground sheds water into a river: the answer to "what makes this river" must not count the flooded half."""
    m = get_mesh(5)
    ground = two_bowls(m)[0]
    volume = (m.area * R * R)[ground < -1000].sum() * 2500.0
    hh, area, sea, d, out, reads = watered(ground, volume, np.array([230.0] * 6 + [0.0] * 6), 25.0, 350.0, level=5)
    share = out.fields["lake_fraction"].astype(np.float64)
    part = (share > 0) & (share < 1)
    assert part.sum() == 1 and 0.3 < share[part][0] < 0.7 and not out.tables["lakes"]["overflows"].any()
    local = out.drivers["river_discharge"]["local_runoff"].astype(np.float64)
    runoff = out.fields["runoff"].astype(np.float64)                             # mm a month over the whole cell: the dry share is counted in
    month_s = hh.params["planet"]["year_length_s"] / 12.0
    assert runoff[:, part].sum() > 100.0                                         # the case: the dry part does shed water
    assert np.allclose(local[:, part], (runoff * area / 1000.0 / month_s)[:, part], rtol=1e-5)
    whole = share == 1
    assert whole.sum() > 5 and not local[:, whole].any()
