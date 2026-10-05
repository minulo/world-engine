"""Known answers for water on land: the routing library, Drainage, and Hydrology with its lakes (design, Layer 9)."""
import numpy as np
import pytest

from worldengine.library import drainage as dr
from worldengine.library.flood import barriers
from worldengine.library.noise import wave_field
from worldengine.mesh import get_mesh
from worldengine.testing import Harness

R = 6.371e6


def angle_from(mesh, lat, lon):
    """Degrees of arc from the point at (lat, lon) to every cell."""
    a, b = np.deg2rad(lat), np.deg2rad(lon)
    centre = np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])
    return np.rad2deg(np.arccos(np.clip(mesh.xyz @ centre, -1, 1)))


def rough_ground(mesh, seed, relief=1500.0, bumps=1.0, waves=24, wave_number=(2.0, 9.0)):
    """Smooth random ground with random bumps of up to `bumps` metres on every cell, so that no two cells tie.
    Large bumps make many small hollows inside larger ones."""
    rng = np.random.default_rng(seed)
    return relief * wave_field(mesh.xyz, rng.random((waves, 4)), wave_number) + bumps * rng.random(mesh.n)


def drained(elevation, volume, level=4):
    """SeaLevel and then Drainage on the given ground: the harness, the sea's fields and tables, and Drainage's result."""
    hh = Harness(level=level, planet={"surface_water_volume_m3": float(volume)})
    area = hh.run("PlanetGeometry").fields["cell_area"]
    sea = hh.run("SeaLevel", reads={"elevation": elevation, "cell_area": area})
    out = hh.run("Drainage", reads={"elevation": elevation, "ocean_mask": sea.fields["ocean_mask"],
                                    "sea_depth": sea.fields["sea_depth"], "cell_area": area},
                 tables={"seas": sea.tables["seas"]})
    return hh, area, sea, out


def follow(recv, start):
    path = [int(start)]
    while recv[path[-1]] >= 0:
        path.append(int(recv[path[-1]]))
    return path


# ------------------------------------------------------------------------------------------ the routing library
def region_of(table, row):
    """The hollows with one bottom each that lie inside the hollow `row`."""
    first, second = table["first_child"], table["second_child"]
    todo, leaves = [int(row)], []
    while todo:
        k = todo.pop()
        if first[k] < 0:
            leaves.append(k)
        else:
            todo += [int(first[k]), int(second[k])]
    return leaves


def check_hollows(mesh, surface, sea, area, count=None):
    """The table of hollows against its definition, worked out the slow way: for each hollow, the lowest pass that
    leads out of it, and the lake that fills it to that pass. `count`, a dict, collects how often a hollow had
    several passes of exactly its level, and how often those led to ground of different heights."""
    recv = dr.receivers(surface, sea, mesh.nbr)
    stack = dr.flow_stack(recv)
    label, table = dr.hollows(surface, sea, recv, stack, mesh.edge_cells, area)
    a, b = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    pass_height = np.maximum(surface[a], surface[b])
    far_side = np.minimum(surface[a], surface[b])
    rows = len(table["parent"])
    end = dr.terminal(stack, recv)
    assert np.array_equal(label > 0, ~sea[end])                              # a cell has a hollow exactly if its water stops on land
    for k in range(1, rows):
        inside = np.isin(label, region_of(table, k))
        leaving = inside[a] != inside[b]
        spill = table["spill_m"][k]
        if not leaving.any():                                                # the whole planet: no way out
            assert np.isnan(spill) and table["parent"][k] < 0
            continue
        assert spill == pass_height[leaving].min()                           # it overflows at its lowest pass
        out_cell, in_cell = table["spill_into_cell"][k], table["spill_from_cell"][k]
        assert inside[in_cell] and not inside[out_cell] and out_cell in mesh.nbr[in_cell]
        assert max(surface[in_cell], surface[out_cell]) == spill
        assert label[out_cell] == table["spill_into_hollow"][k]
        # among passes of exactly that level, the water leaves toward the lowest ground: the rule for a single cell
        level = leaving & (pass_height == spill)
        assert min(surface[in_cell], surface[out_cell]) == far_side[level].min()
        if count is not None and level.sum() > 1:
            count["several"] = count.get("several", 0) + 1
            count["unequal"] = count.get("unequal", 0) + (np.unique(far_side[level]).size > 1)
        if table["parent"][k] >= 0:                                          # two hollows that meet: each names the other's ground
            sibling = table["sibling"][k]
            assert table["spill_m"][sibling] == spill and table["parent"][sibling] == table["parent"][k]
            assert label[out_cell] in region_of(table, sibling)
            parent_spill = table["spill_m"][table["parent"][k]]
            assert np.isnan(parent_spill) or parent_spill >= spill           # the larger hollow overflows no lower
        under = inside & (surface < spill)
        assert np.isclose(table["area_when_full_m2"][k], area[under].sum(), rtol=1e-12)
        assert np.isclose(table["volume_when_full_m3"][k], (area[under] * (spill - surface[under])).sum(), rtol=1e-9, atol=1.0)
        assert table["bottom_m"][k] == surface[inside].min() and surface[table["bottom_cell"][k]] == table["bottom_m"][k]
    # every cell belongs to the smallest hollow around it whose pass stands above it
    own = dr.owners(surface, label, table)
    spill = np.where(np.isnan(table["spill_m"]), np.inf, table["spill_m"])
    for c in range(mesh.n):
        k = label[c] if label[c] > 0 else -1
        while k >= 0 and surface[c] >= spill[k]:
            k = table["parent"][k]
        assert own[c] == k
    return recv, stack, label, table


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_every_hollow_overflows_at_the_lowest_pass_that_leads_out_of_it(seed):
    m = get_mesh(4)
    area = m.area * R * R
    ground = rough_ground(m, seed, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
    shore = np.quantile(ground, 0.1)
    sea = ground < shore
    surface = np.where(sea, shore, ground)
    count = {}
    recv, stack, label, table = check_hollows(m, surface, sea, area, count)
    merged = table["first_child"] >= 0
    assert (~merged[1:]).sum() >= 100 and merged.sum() >= 20                 # many hollows, many of them inside larger ones
    assert (table["parent"][merged] >= 0).any()                              # and some of those inside larger ones again
    # Passes of exactly one height are common, with no two cells of the ground equal: an outlet cell with several
    # lower neighbours beyond its hollow. Each of these grounds has some that lead to ground of different heights.
    assert count["several"] >= 5 and count["unequal"] >= 3
    # with every hollow full, each cell has one way to the sea
    full = dr.overflow_receivers(recv, surface, m.nbr, label, table)
    end = dr.terminal(dr.flow_stack(full), full)
    assert sea[end].all()


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_on_a_planet_without_sea_the_hollows_nest_into_one_that_has_no_way_out(seed):
    m = get_mesh(4)
    area = m.area * R * R
    ground = rough_ground(m, seed, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
    sea = np.zeros(m.n, dtype=bool)
    recv, stack, label, table = check_hollows(m, ground, sea, area)
    tops = np.flatnonzero(table["parent"][1:] < 0) + 1
    assert tops.size == 1 and np.isnan(table["spill_m"][tops[0]])
    assert table["bottom_cell"][tops[0]] == np.argmin(ground)
    full = dr.overflow_receivers(recv, ground, m.nbr, label, table)
    full_stack = dr.flow_stack(full)
    assert set(dr.terminal(full_stack, full)) == {int(np.argmin(ground))}      # every drop ends at the deepest bottom
    assert np.isclose(dr.accumulate(full_stack, full, area)[np.argmin(ground)], area.sum(), rtol=1e-12)


def test_level_ground_drains_by_the_shortest_way_out_and_a_level_floor_to_one_of_its_cells():
    m = get_mesh(4)
    away = angle_from(m, 0, 0)
    floor = angle_from(m, 0, 180) < 15
    sea = away < 30
    surface = np.where(sea, 0.0, np.where(floor, 50.0, 100.0))               # a plain at 100 m with a level-floored pit in it
    recv = dr.receivers(surface, sea, m.nbr)
    stack = dr.flow_stack(recv)
    end = dr.terminal(stack, recv)
    assert set(end[floor]) == {int(np.flatnonzero(floor).min())}             # the floor drains to its lowest-numbered cell
    plain = ~sea & ~floor
    assert np.all(sea[end[plain]] | floor[end[plain]])
    # steps to the nearest lower ground, counted outward from it ring by ring
    steps = np.where(sea | floor, 0, -1)
    ring = 0
    while (steps < 0).any():
        ring += 1
        nxt = (steps < 0) & (np.where(m.nbr >= 0, steps[np.maximum(m.nbr, 0)] == ring - 1, False)).any(axis=1)
        steps[nxt] = ring
    for c in np.flatnonzero(plain):
        assert steps[recv[c]] == steps[c] - 1                                # each step is one ring closer: the shortest way


def test_sums_along_the_flow_paths_count_every_cell_once():
    m = get_mesh(4)
    ground = rough_ground(m, 7)
    sea = ground < 0
    surface = np.where(sea, 0.0, ground)
    recv = dr.receivers(surface, sea, m.nbr)
    stack = dr.flow_stack(recv)
    ones = np.ones(m.n)
    total = dr.accumulate(stack, recv, ones)
    for c in np.random.default_rng(0).choice(np.flatnonzero(~sea), 40, replace=False):
        path = follow(recv, c)
        assert np.all(np.diff(surface[path]) < 0)                            # water only runs down
        assert np.all(np.diff(total[path]) > 0)                              # and a river only grows
    ends = recv < 0
    assert total[ends].sum() == m.n
    monthly = dr.accumulate(stack, recv, np.stack([ones, 2 * ones]))
    assert np.array_equal(monthly[0], total) and np.array_equal(monthly[1], 2 * total)
    loop = recv.copy()
    c = int(np.flatnonzero(recv >= 0)[0])
    loop[recv[c]] = c
    with pytest.raises(ValueError, match="loop"):
        dr.flow_stack(loop)


# ------------------------------------------------------------------------------------------ Drainage
def test_on_a_single_cone_every_cell_drains_to_the_foot():
    m = get_mesh(4)
    away = angle_from(m, 40, 25)                                             # a cone with its top at 40 N, 25 E
    ground = 3000.0 - 60.0 * away
    area = m.area * R * R
    foot = away > 60
    hh, area, sea, out = drained(np.where(foot, -1000.0, ground), area[foot].sum() * 400.0)
    f = out.fields
    wet = sea.fields["ocean_mask"]
    assert np.array_equal(wet, foot)
    assert len(out.tables["hollows"]["parent"]) == 1 and not f["depression_id"].any()        # no hollow: only the row of the sea
    recv = f["flow_receiver"]
    assert np.all(recv[wet] == -1) and np.all(recv[~wet] >= 0)
    assert np.all(away[recv[~wet]] > away[~wet])                             # every step leads away from the top
    for c in np.flatnonzero(~wet)[::37]:
        path = follow(recv, c)
        assert wet[path[-1]] and not wet[path[:-1]].any()
        assert f["basin_id"][c] == path[-2]                                  # its basin is named after the last land cell
    assert np.isclose(f["drainage_area"][wet].sum(), area[~wet].sum(), rtol=1e-12)
    assert np.all(np.isnan(f["spill_elevation"]))
    top = int(np.argmin(away))
    assert f["drainage_area"][top] == area[top]                              # nothing drains through the top but itself
    slope = f["slope"][~wet & (away < 55) & (away > 5)]
    assert np.all(slope > 0) and abs(np.median(slope) / (60.0 / np.deg2rad(1.0) / R) - 1) < 0.1      # 60 m per degree of arc
    # cell by cell: the fall to the receiver over the distance between the two centres. On the coast the receiver is a
    # sea cell, and the water falls to the sea's surface, not to its bed 1,000 m down [the fourth check of build step 2
    # took the bed for the surface, and no test noticed: the line above leaves the coast out]
    level = float(sea.tables["seas"]["surface_m"][0])
    ground_given = np.where(foot, -1000.0, ground)
    dry = np.flatnonzero(~wet)
    to = recv[dry]
    distance = np.arccos(np.clip(np.einsum("ij,ij->i", m.xyz[dry], m.xyz[to]), -1.0, 1.0)) * R
    fall = ground_given[dry] - np.where(wet[to], level, ground_given[to])
    assert np.allclose(f["slope"][dry], fall / distance, rtol=2e-4, atol=0.0)       # (heights and slopes are kept in single precision)
    coast = wet[to]
    assert coast.sum() > 20 and -1000.0 < level < ground_given[dry][coast].min()
    assert np.all(f["slope"][dry][coast] < 0.5 * (ground_given[dry][coast] + 1000.0) / distance[coast])      # (to the bed it would be far steeper)
    assert not f["slope"][wet].any()
    assert set(out.drivers["flow_receiver"]["rule"][~wet]) == {0} and set(out.drivers["flow_receiver"]["rule"][wet]) == {1}


def two_bowls(mesh):
    """A ring of high ground with two bowls inside it, a deep one and a shallower one, a saddle between them, and one
    notch cut through the ring that leads down to the sea."""
    deep, shallow = angle_from(mesh, 0, -12), angle_from(mesh, 0, 12)
    middle = angle_from(mesh, 0, 0)
    bowls = np.minimum(200.0 + 60.0 * deep, 600.0 + 60.0 * shallow)          # bottoms at 200 m and at 600 m
    inside = np.maximum(bowls, 2000.0 - 300.0 * (26.0 - middle))             # the inner face of the ring
    ground = np.where(middle < 26, inside, 2000.0 - 150.0 * (middle - 26.0)) # its outer face falls toward the sea
    notch = angle_from(mesh, 0, 26) < 5
    ground = np.where(notch, np.minimum(ground, 1500.0 - 20.0 * (middle - 21.0)), ground)    # its floor falls outward
    ground = np.where(middle > 34, -3000.0, ground)
    ground += 0.05 * np.arange(mesh.n) / mesh.n                              # no two cells tie
    ground = ground.astype(np.float32).astype(np.float64)                    # as a field stores it
    return ground, deep, shallow, notch


def test_two_bowls_side_by_side_meet_at_their_saddle_and_overflow_together_through_the_notch():
    m = get_mesh(5)
    ground, deep, shallow, notch = two_bowls(m)
    area = m.area * R * R
    hh, area, sea, out = drained(ground, area[ground < -1000].sum() * 2500.0, level=5)
    f, t = out.fields, out.tables["hollows"]
    wet = sea.fields["ocean_mask"]
    assert np.array_equal(wet, ground < -1000)
    a_bottom, b_bottom = int(np.argmin(np.where(wet, np.inf, ground))), int(np.argmin(np.where(shallow < 6, ground, np.inf)))
    a, b = f["depression_id"][a_bottom], f["depression_id"][b_bottom]
    assert {a, b} == {1, 2} and len(t["parent"]) == 4                        # the sea, two bowls, and the two as one
    both = t["parent"][a]
    assert both == 3 == t["parent"][b] and t["first_child"][both] == a and t["second_child"][both] == b     # the deeper one first
    assert t["bottom_cell"][a] == a_bottom and t["bottom_cell"][b] == b_bottom and t["bottom_cell"][both] == a_bottom
    # the saddle between the bowls, found another way: the least height that water rising in one must reach to enter the other
    reach, _ = barriers(ground, m.nbr, m.nbr_count, np.arange(m.n) == a_bottom, ground[a_bottom])
    saddle = reach[b_bottom]
    assert t["spill_m"][a] == t["spill_m"][b] == saddle and 1000.0 < saddle < 1250.0        # near 1,120 m by the geometry
    assert f["depression_id"][t["spill_from_cell"][a]] == a and f["depression_id"][t["spill_into_cell"][a]] == b
    assert f["depression_id"][t["spill_from_cell"][b]] == b and f["depression_id"][t["spill_into_cell"][b]] == a
    # the two as one overflow through the notch, on the way to the sea
    way_out = reach[wet].min()
    assert t["spill_m"][both] == way_out and saddle < way_out < 1520.0
    assert notch[t["spill_from_cell"][both]] and notch[t["spill_into_cell"][both]]
    assert t["spill_into_hollow"][both] == 0 and t["parent"][both] == -1
    assert f["depression_id"][t["spill_into_cell"][both]] == 0
    # the lakes that fill them
    in_a, in_b = f["depression_id"] == a, f["depression_id"] == b
    for k, inside in ((a, in_a), (b, in_b), (both, in_a | in_b)):
        under = inside & (ground < t["spill_m"][k])
        assert np.isclose(t["area_when_full_m2"][k], area[under].sum(), rtol=1e-9)
        assert np.isclose(t["volume_when_full_m3"][k], (area[under] * (t["spill_m"][k] - ground[under])).sum(), rtol=1e-6)
    assert np.allclose(f["spill_elevation"][in_a | in_b], saddle, atol=1e-2) and np.all(np.isnan(f["spill_elevation"][~(in_a | in_b)]))
    # with both full, everything inside the ring leaves by one mouth
    mouth = f["basin_id"][a_bottom]
    assert mouth == f["basin_id"][b_bottom] and wet[m.nbr[mouth]].any()
    assert np.isclose(f["drainage_area"][mouth], area[f["basin_id"] == mouth].sum(), rtol=1e-9)
    assert f["drainage_area"][mouth] > area[in_a | in_b].sum()
    assert set(out.drivers["flow_receiver"]["rule"][[a_bottom, b_bottom]]) == {2}


@pytest.mark.parametrize("seed", [21, 22, 24])
def test_every_land_cell_reaches_the_sea_or_a_closed_hollow_and_the_drained_areas_add_up(seed):
    m = get_mesh(4)
    ground = rough_ground(m, seed, bumps=400.0)
    area = m.area * R * R
    hh, area, sea, out = drained(ground, area[ground < 0].sum() * 1000.0)
    f, t = out.fields, out.tables["hollows"]
    wet = sea.fields["ocean_mask"]
    land = ~wet
    recv = f["flow_receiver"]
    surface = np.where(wet, ground.astype(np.float32) + sea.fields["sea_depth"], ground.astype(np.float32))
    bottoms = set(t["bottom_cell"][1:][t["first_child"][1:] < 0].tolist())
    for c in np.flatnonzero(land):
        path = follow(recv, c)
        assert np.all(np.diff(surface[path]) <= 0)
        last = path[-1]
        if wet[last]:
            assert f["depression_id"][c] == 0 and np.isnan(f["spill_elevation"][c])
        else:
            assert last in bottoms and t["bottom_cell"][f["depression_id"][c]] == last
            assert f["spill_elevation"][c] == np.float32(t["spill_m"][f["depression_id"][c]])
    assert (f["depression_id"][land] > 0).any() and (f["depression_id"][land] == 0).any()
    # with every hollow full: each basin is the land behind one mouth, and the basins share out the land
    mouths = np.unique(f["basin_id"][land])
    assert np.all(f["basin_id"][wet] == -1) and np.all(land[mouths])
    assert np.isclose(f["drainage_area"][mouths].sum(), area[land].sum(), rtol=1e-12)
    assert np.isclose(f["drainage_area"][wet].sum(), area[land].sum(), rtol=1e-12)
    tops = dr.top_hollows(t)
    by_lake = 0
    for mouth in mouths:
        assert f["basin_id"][mouth] == mouth and np.isclose(f["drainage_area"][mouth], area[f["basin_id"] == mouth].sum(), rtol=1e-12)
        if recv[mouth] >= 0 and wet[recv[mouth]]:
            continue                                                         # a mouth hands its water to the sea
        hollow = tops[f["depression_id"][mouth]]                             # or it is the outlet cell of a hollow on the coast,
        assert t["spill_from_cell"][hollow] == mouth and wet[t["spill_into_cell"][hollow]]       # which overflows into the sea
        assert np.all(f["basin_id"][np.isin(f["depression_id"], region_of(t, hollow))] == mouth)     # one basin for the whole hollow
        by_lake += 1
    alone = (t["parent"] < 0) & (np.arange(len(t["parent"])) > 0)
    assert by_lake == (alone & wet[np.maximum(t["spill_into_cell"], 0)]).sum()      # as many as there are hollows on the coast
    assert by_lake >= (0 if seed == 21 else 1)                               # two of the three grounds hold one
    # A full hollow sends all its water through its outlet cell: that cell counts the whole hollow and all that runs
    # into it, and the cell beyond the pass counts that and its own.
    surface = np.where(wet, ground.astype(np.float32) + sea.fields["sea_depth"], ground.astype(np.float32)).astype(np.float64)
    for hollow in np.flatnonzero((t["parent"] < 0) & (np.arange(len(t["parent"])) > 0)):
        inside = np.isin(f["depression_id"], region_of(t, hollow))
        outlet, beyond = t["spill_from_cell"][hollow], t["spill_into_cell"][hollow]
        assert f["drainage_area"][outlet] >= area[inside].sum() * (1 - 1e-12)
        if not wet[beyond]:
            assert f["drainage_area"][beyond] >= f["drainage_area"][outlet] + area[beyond] * (1 - 1e-9)
        under = np.flatnonzero(inside & (surface <= t["spill_m"][hollow]))   # the ground its lake covers
        assert outlet in under


def test_a_planet_without_sea_is_one_basin_that_ends_at_its_deepest_bottom():
    m = get_mesh(4)
    ground = rough_ground(m, 31)
    hh, area, sea, out = drained(ground, 0.0)
    f, t = out.fields, out.tables["hollows"]
    lowest = int(np.argmin(ground))
    assert not sea.fields["ocean_mask"].any() and np.all(f["depression_id"] > 0)
    assert set(f["basin_id"]) == {lowest} and np.isclose(f["drainage_area"][lowest], area.sum(), rtol=1e-12)
    top = int(np.flatnonzero(t["parent"][1:] < 0)[0]) + 1
    assert np.isnan(t["spill_m"][top]) and np.isnan(t["volume_when_full_m3"][top])
    assert set(out.drivers["basin_id"]["ends"]) == {2}


def test_land_that_stands_at_sea_level_drains_into_the_sea():
    """The sea rises to the foot of a shelf and stops there. A field is stored rounded, so a sea surface rebuilt as
    ground plus depth can come out a hair above the true one, and above the shelf: 2,000.12353 m of water over a
    floor at -2,000 m is stored as 2,000.12354 m. The shelf would then look like the floor of a hollow of its own.
    Drainage takes the surface of each body of water from the table of seas instead."""
    m = get_mesh(4)
    away = angle_from(m, 0, 0)
    area = m.area * R * R
    at_the_water = 0.12353
    ground = np.where(away < 25, -2000.0, at_the_water + 10.0 * (away - 25))  # a basin, and land rising gently from its edge
    shelf = (away >= 25) & (away < 29)
    ground[shelf] = at_the_water                                             # the first ring of land: all at one height
    hh, area, sea, out = drained(ground, area[away < 25].sum() * (2000.0 + at_the_water))
    wet = sea.fields["ocean_mask"]
    assert np.array_equal(wet, away < 25)
    level = sea.tables["seas"]["surface_m"][0]
    assert abs(level - at_the_water) < 1e-6
    rebuilt = (ground.astype(np.float32).astype(np.float64) + sea.fields["sea_depth"])[wet]
    assert rebuilt.min() > np.float32(at_the_water)                          # the case: the rebuilt surface stands above the shelf
    f = out.fields
    assert not f["depression_id"].any() and len(out.tables["hollows"]["parent"]) == 1
    assert np.all(f["flow_receiver"][shelf] >= 0)


@pytest.mark.parametrize("seed", list(range(41, 61)))
def test_turning_the_planet_turns_the_drainage_with_it(seed):
    """A fifth of a turn about the axis maps the mesh onto itself, with other cell numbers. Nothing in the drainage
    may depend on those numbers. One ground is no test of that: on a coast most cells have several sea cells for
    neighbours, all at one water level, and with ties going to the lowest cell number the drainage of 27 of 58
    grounds changed under the turn. Ties now go to the lower sea bed."""
    m = get_mesh(4)
    turn = np.deg2rad(72.0)
    rz = np.array([[np.cos(turn), -np.sin(turn), 0.0], [np.sin(turn), np.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    goes_to = np.argmax(m.xyz @ rz.T @ m.xyz.T, axis=1)
    assert len(set(goes_to)) == m.n
    ground = rough_ground(m, seed)
    turned_ground = np.empty_like(ground)
    turned_ground[goes_to] = ground
    area = m.area * R * R
    volume = area[ground < 0].sum() * 1000.0
    _, _, sea, plain = drained(ground, volume)
    _, _, _, turned = drained(turned_ground, volume)
    p, t = plain.fields, turned.fields
    lands = lambda cells: np.where(cells >= 0, goes_to[np.maximum(cells, 0)], -1)
    assert np.array_equal(t["flow_receiver"][goes_to], lands(p["flow_receiver"]))
    assert np.array_equal(t["basin_id"][goes_to], lands(p["basin_id"]))
    assert np.allclose(t["drainage_area"][goes_to], p["drainage_area"], rtol=1e-9)
    assert np.array_equal(np.isnan(t["spill_elevation"][goes_to]), np.isnan(p["spill_elevation"]))
    assert np.allclose(t["spill_elevation"][goes_to], p["spill_elevation"], equal_nan=True)
    assert np.allclose(t["slope"][goes_to], p["slope"], rtol=1e-5, atol=1e-9)
    bottom_p, bottom_t = plain.tables["hollows"]["bottom_cell"], turned.tables["hollows"]["bottom_cell"]
    assert np.array_equal(bottom_t[t["depression_id"][goes_to]], lands(bottom_p[p["depression_id"]]))
    # the hollows overflow at the same places: every hollow, small or made of others, by its bottom and its two pass cells
    passes = lambda table, to: {(int(to(b)), int(to(a)), int(to(c))) for b, a, c in zip(
        table["bottom_cell"][1:], table["spill_from_cell"][1:], table["spill_into_cell"][1:])}
    same = lambda cell: cell
    assert passes(turned.tables["hollows"], same) == passes(plain.tables["hollows"], lambda cell: lands(np.array([cell]))[0])
    wet = sea.fields["ocean_mask"]
    several = (wet[np.maximum(m.nbr, 0)] & (m.nbr >= 0)).sum(axis=1) > 1
    assert (several & ~wet).sum() > 20                                           # the case: coast cells with several sea neighbours


def test_among_equally_low_neighbours_water_runs_to_the_one_whose_bed_lies_lowest():
    m = get_mesh(4)
    away = angle_from(m, 0, 0)
    sea = away < 40
    rng = np.random.default_rng(4)
    bed = np.where(sea, -3000.0 * rng.random(m.n), 10.0 + 50.0 * (away - 40))
    surface = np.where(sea, 0.0, bed)
    by_bed = dr.receivers(surface, sea, m.nbr, bed)
    by_number = dr.receivers(surface, sea, m.nbr)
    checked = 0
    for c in np.flatnonzero(~sea):
        around = m.nbr[c][m.nbr[c] >= 0]
        wet = around[sea[around]]
        if wet.size > 1:
            assert by_bed[c] == wet[np.argmin(bed[wet])] and by_number[c] == wet.min()
            checked += by_bed[c] != by_number[c]
    assert checked > 10                                                          # and the two rules differ on this coast


def test_each_sea_cell_takes_the_level_of_its_own_body_of_water():
    """Three bodies of water at -400, 0 and 250 m. Ground plus depth is stored rounded, so each sea cell takes the
    nearest of the levels the table of seas holds, not the nearest below or above."""
    levels = np.array([-400.0, 0.0, 250.0])
    rng = np.random.default_rng(6)
    body = rng.integers(0, 3, 600)
    sea = rng.random(600) < 0.8
    depth = np.where(sea, 5.0 + 3000.0 * rng.random(600), 0.0).astype(np.float32)
    elevation = np.where(sea, levels[body] - depth.astype(np.float64), 500.0 + 100.0 * rng.random(600)).astype(np.float32)
    surface = dr.drainage_surface(elevation, depth, sea, levels[[2, 0, 1]])       # the table lists them in any order
    rebuilt = elevation.astype(np.float64) + depth
    assert np.abs(rebuilt[sea] - levels[body[sea]]).max() > 1e-5                  # the case: the rounding shows
    assert np.array_equal(surface[sea], levels[body[sea]])
    assert np.array_equal(surface[~sea], elevation[~sea].astype(np.float64))
    assert all((sea & (body == k)).sum() > 50 for k in range(3))
    one = dr.drainage_surface(elevation, depth, sea, levels[:1])                  # one level listed: every sea cell takes it
    assert np.all(one[sea] == -400.0)
    none = dr.drainage_surface(elevation, depth, sea)                             # none listed: ground plus depth
    assert np.array_equal(none[sea], rebuilt[sea])


def test_drainage_records_why_each_cell_drains_as_it_does():
    """The codes behind the "why" answers: a slope, the sea, the bottom of a hollow and level ground each get their
    own; a sea cell is no part of a river basin; and a cell's hollow is named by its own row of the table."""
    m = get_mesh(4)
    away = angle_from(m, 0, 0)
    floor = angle_from(m, 0, 180) < 15
    ground = np.where(away < 30, -500.0, np.where(floor, 50.0, np.where(angle_from(m, 0, 180) < 40, 100.0, 100.0 + 5.0 * (150.0 - away))))
    area = m.area * R * R
    hh, area, sea, out = drained(ground, area[away < 30].sum() * 500.0)
    wet = sea.fields["ocean_mask"]
    assert np.array_equal(wet, away < 30)
    f, t, d = out.fields, out.tables["hollows"], out.drivers
    rule = d["flow_receiver"]["rule"]
    plain = ~wet & ~floor & (angle_from(m, 0, 180) < 38)                          # the level plain around the pit
    at_the_rim = plain & (floor[np.maximum(m.nbr, 0)] & (m.nbr >= 0)).any(axis=1) # its cells beside the pit run down into it
    assert set(rule[wet]) == {1} and set(rule[plain & ~at_the_rim]) == {3} and set(rule[at_the_rim]) == {0}
    assert (plain & ~at_the_rim).sum() > 50 and at_the_rim.sum() > 10
    bottoms = t["bottom_cell"][1:][t["first_child"][1:] < 0]
    assert set(rule[bottoms]) == {2} and (rule == 0).sum() > 100
    assert set(rule[floor]) == {2, 3} and (rule[floor] == 2).sum() == 1           # a level floor: one bottom, the rest level ground
    ends = d["basin_id"]["ends"]
    assert set(ends[wet]) == {0} and set(ends[~wet]) == {1}
    hollow = d["depression_id"]["hollow"]
    label = f["depression_id"]
    assert np.array_equal(hollow[label > 0], label[label > 0]) and set(hollow[label == 0]) == {-1} and (label > 0).any()
    kind = d["drainage_area"]["cell_is"]
    top = dr.top_hollows(t)
    full_level = np.where(label > 0, t["spill_m"][top[label]], -np.inf)
    under = (label > 0) & (ground.astype(np.float32) <= full_level)
    assert set(kind[wet]) == {2} and np.array_equal(kind == 1, under) and under.sum() > 50 and (kind == 0).sum() > 20


def test_with_every_hollow_full_the_water_crosses_each_lake_to_its_outlet_by_the_shortest_way():
    m = get_mesh(4)
    area = m.area * R * R
    for seed in (1, 2, 3):
        ground = rough_ground(m, seed, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
        shore = np.quantile(ground, 0.1)
        sea = ground < shore
        surface = np.where(sea, shore, ground)
        recv = dr.receivers(surface, sea, m.nbr)
        label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area)
        rows = np.arange(len(table["parent"]))
        tops = rows[(table["parent"] < 0) & (rows > 0)]
        full, lake = dr.through_full_hollows(recv, surface, m.nbr, label, table, tops)
        top = dr.top_hollows(table)
        under = (label > 0) & (surface <= table["spill_m"][top[label]])
        assert np.array_equal(lake >= 0, under) and np.array_equal(lake[under], top[label][under])
        assert np.array_equal(full[~under], recv[~under])                         # ground above the water keeps its receiver
        # steps to the outlet, counted outward from it over the flooded cells of the same lake
        steps = np.full(m.n, -1)
        steps[table["spill_from_cell"][tops]] = 0
        ring = 0
        while True:
            ring += 1
            near = np.where(m.nbr >= 0, (steps[np.maximum(m.nbr, 0)] == ring - 1) & (lake[np.maximum(m.nbr, 0)] == lake[:, None]), False).any(axis=1)
            new = under & (steps < 0) & near
            if not new.any():
                break
            steps[new] = ring
        assert np.all(steps[under] >= 0)
        inner = under & (steps > 0)
        assert np.all(steps[full[inner]] == steps[inner] - 1) and np.all(lake[full[inner]] == lake[inner])
        for c in np.flatnonzero(inner):                                           # among equally short ways: over the lowest ground
            around = m.nbr[c][m.nbr[c] >= 0]
            ways = around[(lake[around] == lake[c]) & (steps[around] == steps[c] - 1)]
            assert surface[full[c]] == surface[ways].min()
        assert np.array_equal(full[table["spill_from_cell"][tops]], table["spill_into_cell"][tops])
        stack = dr.flow_stack(full)                                               # no loop, and everything reaches the sea
        assert sea[dr.terminal(stack, full)].all()
        drained_area = dr.accumulate(stack, full, np.where(sea, 0.0, area))
        for k in tops:
            inside = np.isin(label, region_of(table, k))
            assert drained_area[table["spill_from_cell"][k]] >= area[inside].sum() * (1 - 1e-12)
    with pytest.raises(ValueError, match="together|outlet|pass"):                 # a hollow and one of its parts cannot both be named
        part = int(np.flatnonzero(table["parent"] >= 0)[0])
        dr.through_full_hollows(recv, surface, m.nbr, label, table, [part, int(top[part])])


def test_the_largest_source_of_a_river_is_never_the_cell_itself():
    """For each cell the one cell, among those whose water passes through it, with the largest value: found here by
    walking down from every cell. It used to count the cell itself, so that the answer to "where does most of this
    river come from" was "from here" for half of all river cells."""
    m = get_mesh(4)
    ground = rough_ground(m, 9)
    sea = ground < 0
    recv = dr.receivers(np.where(sea, 0.0, ground), sea, m.nbr)
    stack = dr.flow_stack(recv)
    rng = np.random.default_rng(1)
    values = rng.random(m.n) * (rng.random(m.n) < 0.7)                            # many zeros: ties among sources that give nothing
    values[::5] = 0.3                                                             # and ties among sources that give the same
    best, where = np.full(m.n, -np.inf), np.full(m.n, -1)
    for c in range(m.n):
        for below in follow(recv, c)[1:]:
            if values[c] > best[below] or (values[c] == best[below] and c < where[below]):
                best[below], where[below] = values[c], c
    got = dr.largest_upstream(stack, recv, values)
    assert np.array_equal(got, where)
    assert (got == -1).sum() > 200 and np.all(got != np.arange(m.n))


# ------------------------------------------------------------------------------------------ snow (library)
from worldengine.library import evaporation as ev                       # noqa: E402
from worldengine.library import lakes as lk                             # noqa: E402
from worldengine.library.snow import degree_day_melt, snow_year         # noqa: E402
from worldengine.library.soil_water import bucket_month, bucket_repeating, bucket_year    # noqa: E402

from conftest import YEAR_S                                             # noqa: E402

MONTH_S = YEAR_S / 12
MONTH_DAYS = MONTH_S / 86400.0


def column(values):
    """Twelve monthly values as one cell's column."""
    return np.asarray(values, dtype=np.float64).reshape(12, 1)


def test_the_snow_of_a_year_that_melts_it_all_followed_by_hand():
    """Six months at -5 C with 10 mm of snowfall each, then six months at +5 C without. At the end of the cold months
    the store holds 10, 20 ... 60 mm, and its mean in each is 5, 15 ... 55. A month at +5 C can melt 4 mm a day per
    degree times 30.44 days times 5 degrees = 609 mm, so the 60 mm are gone after 60 / 609 of the first warm month:
    its mean store is that share of the month times the 30 mm the snow averaged while it lay, 2.96 mm."""
    temperature = column(273.15 + np.array([-5.0] * 6 + [5.0] * 6))
    could_melt = degree_day_melt(temperature, 273.15, 4.0, MONTH_DAYS)
    assert np.allclose(could_melt[6:], 608.8, atol=0.1) and np.all(could_melt[:6] == 0)
    store, melted, left, cover = snow_year(column([10.0] * 6 + [0.0] * 6), could_melt, 1.0, 15.0)
    thaw = 4.0 * MONTH_DAYS * 5.0
    assert np.allclose(store[:, 0], [5, 15, 25, 35, 45, 55, 30.0 * 60.0 / thaw, 0, 0, 0, 0, 0])
    assert abs(store[6, 0] - 2.96) < 0.01
    assert np.allclose(melted[:, 0], [0] * 6 + [60] + [0] * 5) and not left.any()
    # The share of the ground under snow, full from 15 mm. In the first month the store rises from 0 to 10 mm: two
    # thirds covered at its end, one third on average. In the second it passes 15 mm half-way: (0.5 * (10 + 15) / 15
    # + 1) / 2 = 0.917. Then full cover, until the thaw: the 60 mm take 60 / 609 of the month to go, and for the
    # last quarter of that time less than 15 mm lie, so the month is covered for 45 / 609 + 0.5 * 15 / 609 of it.
    assert np.allclose(cover[:, 0], [1 / 3, 0.5 * (25 / 30 + 1), 1, 1, 1, 1, (45 + 7.5) / thaw, 0, 0, 0, 0, 0])
    assert abs(cover[6, 0] - 0.086) < 0.001                                       # white for 2.6 days of the month
    # Deep snow outlasts the thaw: 600 mm against 243.5 mm of melt a month at +2 C is gone in the third warm month,
    # 113 mm into it, after 113 / 243.5 of the month.
    late = degree_day_melt(column(273.15 + np.array([-5.0] * 6 + [2.0] * 6)), 273.15, 4.0, MONTH_DAYS)
    store, melted, left, cover = snow_year(column([100.0] * 6 + [0.0] * 6), late, 1.0, 15.0)
    thaw = 4.0 * MONTH_DAYS * 2.0
    rest = 600 - 2 * thaw
    assert np.allclose(store[6:, 0], [600 - thaw / 2, 600 - 1.5 * thaw, 0.5 * rest * rest / thaw, 0, 0, 0])
    assert np.isclose(melted.sum(), 600.0) and not left.any()
    # The month in which the snow goes counts as white only for the days it lies: five months of 20 mm, then a month
    # at +8 C that could melt 974 mm. The 100 mm last 3.1 days; the month's mean store is 5.1 mm, not the 50 mm that
    # the average of its first and last day would give.
    warm = degree_day_melt(column(273.15 + np.array([-5.0] * 5 + [8.0] * 7)), 273.15, 4.0, MONTH_DAYS)
    store, melted, left, cover = snow_year(column([20.0] * 5 + [0.0] * 7), warm, 1.0, 15.0)
    assert abs(store[5, 0] - 5.13) < 0.01 and abs(100.0 / warm[5, 0] * MONTH_DAYS - 3.1) < 0.05
    assert abs(cover[5, 0] - (85.0 + 7.5) / warm[5, 0]) < 1e-9 and cover[5, 0] < 0.1
    # No snowfall, no snow, however cold.
    store, melted, left, cover = snow_year(column([0.0] * 12), column([0.0] * 12), 1.0, 15.0)
    assert not store.any() and not melted.any() and not left.any() and not cover.any()
    # Snow that falls in a month that could melt more than falls never lies: the store stays empty.
    store, melted, left, cover = snow_year(column([30.0] * 12), column([50.0] * 12), 1.0, 15.0)
    assert not store.any() and np.allclose(melted, 30.0) and not left.any() and not cover.any()
    # A thin store: 6 mm lying all month cover 6 / 15 of the ground.
    store, melted, left, cover = snow_year(column([0.5] * 12), column([0.0] * 12), 1.0, 15.0)
    assert np.allclose(store, 6.0) and np.allclose(cover, 0.4) and np.allclose(left, 0.5)


def test_the_snow_year_is_the_one_that_years_followed_from_bare_ground_come_to():
    """A year that begins in its warm season starts with the snow of the last cold season on the ground. The plain
    rule is followed here in two thousand small steps a month, with snow falling and melting at steady rates."""
    rng = np.random.default_rng(3)
    snowfall = rng.random((12, 200)) * 40.0
    melt = rng.random((12, 200)) * 150.0 * (rng.random((12, 200)) < 0.4)          # some months melt, most do not
    melt[:, snowfall.sum(axis=0) >= melt.sum(axis=0)] *= 3.0                      # keep to years that melt all their snow
    seasonal = snowfall.sum(axis=0) < melt.sum(axis=0)
    assert seasonal.sum() > 100
    store, melted, left, cover = snow_year(snowfall, melt, 1.0, 15.0)
    on_ground, steps = np.zeros(200), 2000
    for _ in range(5):                                                            # the plain rule, year after year
        means = np.zeros((12, 200))
        gone = np.zeros((12, 200))
        white = np.zeros((12, 200))
        for m in range(12):
            for _ in range(steps):
                there = on_ground + snowfall[m] / steps
                took = np.minimum(melt[m] / steps, there)
                means[m] += 0.5 * (on_ground + there - took) / steps
                white[m] += np.minimum(0.5 * (on_ground + there - took) / 15.0, 1.0) / steps
                gone[m] += took
                on_ground = there - took
    assert np.abs(store - means)[:, seasonal].max() < 0.02                        # mm, of stores of up to some hundred
    assert np.abs(cover - white)[:, seasonal].max() < 2e-3                        # the share of the ground under snow
    assert ((cover > 0.05) & (cover < 0.95))[:, seasonal].sum() > 100             # with many months neither bare nor white
    assert np.abs(melted - gone)[:, seasonal].max() < 1e-6
    assert np.allclose(melted.sum(axis=0)[seasonal], snowfall.sum(axis=0)[seasonal])       # all that fell has melted
    assert not left[:, seasonal].any()
    runs_out = (store[:, seasonal] > 0) & (np.roll(store, -1, axis=0)[:, seasonal] == 0)
    assert runs_out.sum() > 50                                                    # months in which the snow goes are in the sample


def test_where_more_snow_falls_than_melts_the_excess_leaves_as_ice_and_the_store_holds_a_set_number_of_years():
    """30 mm of snowfall every month, and three summer months that could melt 100 mm each. The year gains 60 mm.
    That much leaves as ice, 5 mm a month, and at the end of summer the store holds one year's gain. By hand the store
    at the end of each month is 185, 210, 235, 260, 285, 210, 135, 60, 85, 110, 135, 160."""
    snowfall = column([30.0] * 12)
    melt = column([0.0] * 5 + [100.0] * 3 + [0.0] * 4)
    store, melted, left, cover = snow_year(snowfall, melt, 1.0, 15.0)
    ends = np.array([185, 210, 235, 260, 285, 210, 135, 60, 85, 110, 135, 160.0])
    starts = np.roll(ends, 1)
    assert np.allclose(store[:, 0], 0.5 * (starts + ends))
    assert np.allclose(melted, melt) and np.allclose(left, 5.0)
    assert np.isclose(snowfall.sum(), melted.sum() + left.sum())                  # what falls melts or leaves as ice
    assert np.allclose(cover, 1.0)                                                # never less than 60 mm on the ground
    deeper, melted5, left5, cover5 = snow_year(snowfall, melt, 5.0, 15.0)         # five years' gain kept: only the store changes
    assert np.allclose(deeper - store, 4 * 60.0) and np.array_equal(melted5, melted) and np.array_equal(left5, left)
    # Land that never thaws keeps a year of what falls: 2 mm a month makes 24 mm, white ground all year.
    store, melted, left, cover = snow_year(column([2.0] * 12), column([0.0] * 12), 1.0, 15.0)
    assert np.allclose(store, 24.0) and np.allclose(left, 2.0) and not melted.any() and np.allclose(cover, 1.0)
    # Where a year only just keeps its snow, the ground is nearly bare at the end of summer, and how bare depends on
    # the number of years of net snowfall the store holds: 30 mm a month, three months that could melt 119 mm each.
    # The year gains 3 mm, which leave as 0.25 mm of ice a month. With one year kept, the store falls from 92.25 mm
    # to 3 mm in the last month of summer, 89.25 mm in all: for the last 12 of those it is below 15 mm, 0.6 covered
    # on average. In the month after it rises from 3 mm to 32.75 mm and passes 15 mm after 12 / 29.75 of the month.
    thin = column([0.0] * 5 + [119.0] * 3 + [0.0] * 4)
    store, melted, left, cover = snow_year(snowfall, thin, 1.0, 15.0)
    assert np.allclose(left, 0.25) and np.isclose(store[7, 0], 0.5 * (92.25 + 3.0)) and np.isclose(store[8, 0], 0.5 * (3.0 + 32.75))
    assert np.isclose(cover[7, 0], 1 - 12 / 89.25 * 0.4) and np.isclose(cover[8, 0], 1 - 12 / 29.75 * 0.4)
    store5, _, left5, cover5 = snow_year(snowfall, thin, 5.0, 15.0)               # five years kept: 15 mm at the least
    assert np.allclose(store5 - store, 12.0) and np.allclose(cover5, 1.0) and np.array_equal(left5, left)


def test_the_snow_store_does_not_jump_where_a_year_tips_from_losing_its_snow_to_keeping_it():
    """A limit on the depth of the store made it jump by the whole limit when the year's gain crossed zero; one cell
    tipping kept the climate rounds from settling. With snow leaving by age, the two cases meet."""
    snowfall = column([30.0] * 12)
    stores, ice = [], []
    for gain in (-1e-6, 0.0, 1e-6):
        melt = column([0.0] * 5 + [(360.0 - gain) / 3] * 3 + [0.0] * 4)
        store, melted, left, cover = snow_year(snowfall, melt, 1.0, 15.0)
        stores.append(store)
        ice.append(left.sum())
        assert np.isclose(snowfall.sum(), melted.sum() + left.sum())
    assert np.abs(stores[0] - stores[1]).max() < 1e-5 and np.abs(stores[2] - stores[1]).max() < 1e-5
    assert ice[0] == 0.0 and ice[1] == 0.0 and np.isclose(ice[2], 1e-6)
    assert np.isclose(stores[1].min(), 15.0) and stores[1].max() > 200.0          # bare at the end of summer (the month after
                                                                                  # holds 0 to 30 mm), deep in winter


# ------------------------------------------------------------------------------------------ soil water (library)
def test_a_soil_that_gets_more_than_the_air_asks_stays_full_and_sheds_the_rest():
    supply, demand = column([100.0] * 12), column([60.0] * 12)
    soil, taken, shed, years, left = bucket_repeating(supply, demand, np.array([150.0]), 0.75, 60, 0.01)
    assert np.allclose(soil, 150.0) and np.allclose(taken, 60.0) and np.allclose(shed, 40.0) and years == 1


def test_a_soil_that_gets_less_than_the_air_asks_settles_where_the_air_takes_all_it_gets():
    """With a steady supply S below a steady demand D the store comes to rest at S / D of the critical level,
    because the air then takes D * (store / critical) = S."""
    supply, demand = column([30.0] * 12), column([90.0] * 12)
    soil, taken, shed, years, left = bucket_repeating(supply, demand, np.array([150.0]), 0.75, 60, 0.01)
    assert np.allclose(soil, 0.75 * 150.0 * 30.0 / 90.0, atol=1e-6) and np.allclose(taken, 30.0) and not shed.any()
    # no water at all: an empty soil, and nothing for the air
    soil, taken, shed, years, left = bucket_repeating(column([0.0] * 12), demand, np.array([150.0]), 0.75, 60, 0.01)
    assert not soil.any() and not taken.any() and not shed.any()
    # a soil that holds nothing: the air gets what falls as far as it asks, the rest runs off at once
    soil, taken, shed, years, left = bucket_repeating(column([50.0, 10.0] * 6), column([30.0] * 12), np.array([0.0]), 0.75, 60, 0.01)
    assert not soil.any() and np.allclose(taken[:, 0], [30.0, 10.0] * 6) and np.allclose(shed[:, 0], [20.0, 0.0] * 6)


def test_a_soil_dries_through_a_rainless_season_as_the_exact_solution_says():
    """From full, with no supply and a demand D: the store falls by D a month down to the critical level Wc, and from
    there as Wc * exp(-D * t / Wc)."""
    capacity, critical, d = 150.0, 112.5, 75.0
    end, mean, taken, shed = bucket_year(np.zeros((12, 1)), np.full((12, 1), d), np.array([capacity]), 0.75, np.array([capacity]))
    reached = (capacity - critical) / d                                           # months to the critical level: half a month
    after = lambda months: critical * np.exp(-d * (months - reached) / critical)
    assert abs(end[0] - after(12.0)) < 1e-9 * critical
    stores = capacity - np.cumsum(taken[:, 0])
    assert np.allclose(stores, [after(m) for m in range(1, 13)], rtol=1e-9)
    assert np.isclose(taken.sum(), capacity - end[0]) and not shed.any()
    # the first month's mean store: half a month falling from 150 to 112.5, half a month of the exponential
    half = 0.5 * 0.5 * (capacity + critical) + critical * (critical / d) * (1 - np.exp(-d * 0.5 / critical))
    assert abs(mean[0, 0] - half) < 1e-9 * critical


def test_one_month_of_the_bucket_is_the_exact_solution_whichever_rules_it_passes_through():
    """Each month against the same equation stepped in 20,000 small steps: a soil that stays wet, one that stays dry,
    one that dries past the critical level, one that fills past it and overflows, with and without demand."""
    rng = np.random.default_rng(8)
    n = 300
    capacity = np.where(rng.random(n) < 0.05, 0.0, 20.0 + 300.0 * rng.random(n))
    critical = 0.75 * capacity
    store = capacity * rng.random(n)
    supply = 250.0 * rng.random(n) * (rng.random(n) < 0.7)
    demand = 200.0 * rng.random(n) * (rng.random(n) < 0.9)
    tiny = np.arange(n) % 10 == 0                                                 # every tenth cell: a demand of next to nothing
    demand[tiny] = 10.0 ** rng.uniform(-18, -3, tiny.sum())
    end, mean, taken, shed = bucket_month(store, supply, demand, capacity, critical)
    w, steps = store.copy(), 20000
    e = o = total = 0.0
    for _ in range(steps):
        eff = np.where(critical > 0, np.minimum(1.0, w / np.where(critical > 0, critical, 1.0)), 1.0)
        take = np.minimum(demand * eff / steps, w + supply / steps)
        nxt = w + supply / steps - take
        spill = np.maximum(nxt - capacity, 0.0)
        total = total + 0.5 * (w + nxt - spill) / steps
        w, e, o = nxt - spill, e + take, o + spill
    scale = 1.0 + supply + demand
    assert np.abs(end - w).max() < 2e-3 and np.abs(taken - e).max() / scale.max() < 1e-4
    assert np.abs(shed - o).max() < 2e-2 and np.abs(mean - total).max() < 2e-2
    assert np.allclose(store + supply, end + taken + shed, atol=1e-9)             # the water is all accounted for
    kinds = [(store >= critical) & (end < critical), (store < critical) & (end >= critical) & (critical > 0), shed > 0, demand == 0,
             tiny & (store < critical) & (supply > 0)]
    assert all(k.sum() >= 5 for k in kinds)                                       # every passage occurs in the sample
    assert np.all(taken <= demand * (1 + 1e-9) + 1e-12)                           # the air never takes more than it asks


def test_the_store_of_the_bucket_keeps_its_bounds_to_the_last_digit():
    """Never below empty and never above full, and the month's water all accounted for. Rounding used to leave the
    store a hair outside: 3e-14 mm below nothing, 3e-13 mm above full [MEASURED by the third check of build step 2].
    The cases are drawn where rounding bites: stores at the brim, at the critical level and at nothing, supply and
    demand that nearly cancel, and soils from a millimetre to five metres."""
    rng = np.random.default_rng(31)
    n = 400_000
    capacity = 10.0 ** rng.uniform(0.0, 3.7, n)
    critical = 0.75 * capacity
    at = rng.integers(0, 5, n)
    store = np.select([at == 0, at == 1, at == 2, at == 3], [capacity, critical, np.zeros(n), capacity * (1.0 - 10.0 ** rng.uniform(-16, -1, n))],
                      capacity * rng.random(n))
    demand = 10.0 ** rng.uniform(-3, 2.7, n) * (rng.random(n) < 0.95)
    supply = np.where(rng.random(n) < 0.4, demand * (1.0 + 10.0 ** rng.uniform(-16, -1, n) * rng.choice([-1.0, 1.0], n)), 10.0 ** rng.uniform(-3, 2.7, n))
    supply = np.maximum(supply, 0.0) * (rng.random(n) < 0.9)
    end, mean, taken, shed = bucket_month(store, supply, demand, capacity, critical)
    assert end.min() >= 0.0 and (end <= capacity).all()
    assert mean.min() >= -1e-9 and (mean <= capacity * (1.0 + 1e-12) + 1e-9).all()
    assert taken.min() >= 0.0 and shed.min() >= 0.0
    assert np.abs(store + supply - end - taken - shed).max() < 1e-9 * (1.0 + (store + supply).max())
    assert (end == 0.0).sum() > 100 and (end == capacity).sum() > 1000                # the case: both bounds are reached exactly


def test_a_demand_of_next_to_nothing_takes_next_to_nothing():
    """A soil at 50 mm, 100 mm of rain in the month, capacity 150 mm: the soil is just full at the end, nothing runs
    off, and the air has taken its demand times how full the soil was. The formulas used to subtract two large
    numbers that nearly agree: at a demand of 1e-15 mm they returned 62.5 mm of runoff from nowhere."""
    for demand in (1e-3, 1e-6, 1e-9, 1e-11, 1e-13, 1e-15, 1e-18, 1e-300, 0.0):
        end, mean, taken, shed = bucket_month(np.array([50.0]), np.array([100.0]), np.array([demand]), np.array([150.0]), np.array([112.5]))
        assert abs(end[0] - 150.0) <= demand + 1e-12 and abs(shed[0]) < 1e-9
        assert 0.0 <= taken[0] <= demand + 1e-12
        # By hand: the soil is below its critical level, 112.5 mm, for 0.625 of the month and gives the air 0.722 of
        # its demand on average there, and all of it for the rest: 0.625 * 0.722 + 0.375 = 0.826 of the demand.
        if demand >= 1e-11:
            assert abs(taken[0] / demand - 0.826) < 0.002
        assert abs(50.0 + 100.0 - end[0] - taken[0] - shed[0]) < 1e-12
        assert abs(mean[0] - 100.0) <= demand + 1e-9                              # it rises in a straight line from 50 to 150


def test_the_bucket_keeps_the_water_balance_and_finds_the_year_that_repeats():
    rng = np.random.default_rng(5)
    n = 400
    wet_season = (np.arange(12)[:, None] + rng.integers(0, 12, n)[None, :]) % 12 < 5
    supply = rng.random((12, n)) * 200.0 * wet_season * rng.random(n) ** 2
    demand = rng.random((12, n)) * 180.0 * rng.random(n)
    demand[:, :20] *= 1e-3                                                        # some cells where the air asks for next to nothing
    capacity = 20.0 + 300.0 * rng.random(n)
    soil, taken, shed, years, left = bucket_repeating(supply, demand, capacity, 0.75, 60, 0.01)
    assert left <= 0.01 and years < 60
    assert np.all(taken >= 0) and np.all(shed >= 0) and np.all(taken <= demand + 1e-9)
    assert np.all(soil >= 0) and np.all(soil <= capacity + 1e-9)
    balance = supply.sum(axis=0) - taken.sum(axis=0) - shed.sum(axis=0)           # what the store itself changed by in the year
    assert np.abs(balance).max() <= 0.01
    # the plain way: four hundred years one after another from a full soil come to the same year
    store = capacity.copy()
    for _ in range(400):
        store, mean_plain, taken_plain, shed_plain = bucket_year(supply, demand, capacity, 0.75, store)
    settled = np.abs(taken_plain - taken).max(axis=0) < 0.05
    assert settled.mean() > 0.97                                                  # (the rest settle over more than 400 plain years)
    assert np.abs(shed_plain.sum(axis=0) - shed.sum(axis=0)).max() < 0.02


@pytest.mark.parametrize("depth", [150.0, 500.0, 2000.0, 5000.0])
def test_the_repeating_year_of_the_bucket_is_the_root_that_bisection_finds_in_shallow_and_in_deep_soil(depth):
    """The store at the end of a year never falls when the store at its start rises, and rises by no more. So the
    store that repeats is found by halving the range from empty to full sixty times. The bucket must return that
    year, and the store itself, not only the year's totals: in soil of which the air asks little the store closes in
    on its repeating year by a ratio near 1 a year, and the bucket used to stop there while the store was still
    hundreds of millimetres from where it was heading."""
    rng = np.random.default_rng(7)
    n = 3000
    t = (np.arange(12)[:, None] + 0.5) / 12 * 2 * np.pi
    phase = rng.uniform(0, 2 * np.pi, n)
    supply = 10 ** rng.uniform(-3, 2.5, n) * np.clip(1 + rng.uniform(0, 1.5, n) * np.cos(t + phase), 0, None)
    demand = 10 ** rng.uniform(-4, 2.5, n) * np.clip(1 + rng.uniform(0, 1.5, n) * np.cos(t + phase + rng.uniform(0, 2 * np.pi, n)), 0, None)
    demand[:, rng.random(n) < 0.05] = 0.0
    supply[:, rng.random(n) < 0.05] = 0.0
    capacity = np.full(n, depth)
    soil, taken, shed, years, left = bucket_repeating(supply, demand, capacity, 0.75, 60, 0.01)
    assert left <= 0.01 and years < 30
    lo, hi = np.zeros(n), capacity.copy()
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        end, *_ = bucket_year(supply, demand, capacity, 0.75, mid)
        rises = end > mid
        lo, hi = np.where(rises, mid, lo), np.where(rises, hi, mid)
    start = 0.5 * (lo + hi)
    end, soil_b, taken_b, shed_b = bucket_year(supply, demand, capacity, 0.75, start)
    one_answer = np.abs(end - start) < 1e-6                                       # (no supply and no demand: any store repeats)
    assert one_answer.mean() > 0.9
    slow = one_answer & (demand.sum(axis=0) < 0.05 * 0.75 * depth)                # the air takes under a twentieth of the store a year
    assert slow.sum() > 100
    assert np.abs(soil - soil_b)[:, one_answer].max() < 0.05                      # mm of store
    assert np.abs(taken.sum(axis=0) - taken_b.sum(axis=0))[one_answer].max() < 0.02
    assert np.abs(shed.sum(axis=0) - shed_b.sum(axis=0))[one_answer].max() < 0.02
    assert np.abs(supply.sum(axis=0) - taken.sum(axis=0) - shed.sum(axis=0)).max() <= 0.01      # the books of the returned year


# ------------------------------------------------------------------------------------------ the demand for water (library)
def demand_constants():
    return Harness(level=2).params["models"]["slots"]["Hydrology"]["constants"]["demand"]


def test_the_numbers_of_the_priestley_taylor_rule_at_twenty_degrees_are_the_textbook_ones():
    d = demand_constants()
    t = np.array([20.0])
    # Pa/K. By hand from the same formula: 2.503e6 * exp(17.27 * 20 / 257.3) / 257.3**2 = 144.7
    assert abs(ev.saturation_slope(t, d["vapour"])[0] - 144.7) < 0.3
    # J/kg. [DOCUMENTED: FAO Irrigation and Drainage Paper 56, Annex 3: "A single value may be taken (for T = 20 C):
    # 2.45 MJ/kg".] Without the square of the bracket the formula gives 2.17 MJ/kg, and this fails.
    assert abs(ev.latent_heat(t, d["heat"])[0] / 2.45e6 - 1) < 0.005
    sea_level = ev.air_pressure(np.array([0.0]), 9.80665, d["air"])
    assert sea_level[0] == 101325.0
    # [UNVERIFIED: the International Standard Atmosphere at 5 km as I recall it, 54.0 kPa]
    assert abs(ev.air_pressure(np.array([5000.0]), 9.80665, d["air"])[0] / 54020.0 - 1) < 0.002
    g = ev.psychrometric(sea_level, ev.latent_heat(t, d["heat"]), d["air"])[0]
    assert abs(g - 66.7) < 0.6                                                    # Pa/K. By hand: 1004.6 * 0.028963 / 0.01802 * 101325 / 2.4535e6
    share = lambda c: (lambda s, gg: s / (s + gg))(ev.saturation_slope(np.array([c]), d["vapour"])[0],
                                                   ev.psychrometric(sea_level, ev.latent_heat(np.array([c]), d["heat"]), d["air"])[0])
    assert abs(share(0.0) - 0.40) < 0.01 and abs(share(30.0) - 0.78) < 0.01       # the share of the energy that evaporates water
    # The one share of sunshine returns the two means of Earth's whole surface, land and sea [DOCUMENTED: Trenberth,
    # Fasullo and Kiehl 2009, Table 2b, the row of the globe: 161.2 W/m2 of sunlight absorbed, 396 up less 333 back
    # = 63 lost]. The row of the land alone gives 145.1 absorbed and 79.6 lost; data/models.yaml says what the one
    # share misses there.
    sun = d["sunshine_fraction"]
    assert abs(ev.net_longwave(np.array([15.0]), sun, d["longwave"])[0] - 63.0) < 1.5         # W/m2 lost at 15 C
    assert np.isclose(ev.net_longwave(np.array([15.0]), sun, d["longwave"])[0], (0.2 + 0.8 * 0.62) * (107.0 - 15.0))    # 64.0
    assert ev.net_longwave(np.array([150.0]), sun, d["longwave"])[0] == 0.0
    ground = d["sunlight"]["ground_reflects"]
    absorbed = ev.absorbed_sunlight(np.array([341.3]), np.array([0.0]), sun, ground, d["sunlight"])[0]
    assert abs(absorbed / 161.0 - 1) < 0.03                                       # W/m2 absorbed, of 341.3 at the top of the air
    assert np.isclose(absorbed, 0.83 * (0.25 + 0.5 * 0.62) * 341.3)               # the paper's formula, with its numbers written out
    high = ev.absorbed_sunlight(np.array([341.3]), np.array([4000.0]), sun, ground, d["sunlight"])[0]
    assert np.isclose(high / absorbed, 1 + 2.67e-5 * 4000.0)                      # thinner air lets more through
    water = ev.absorbed_sunlight(np.array([341.3]), np.array([0.0]), sun, d["sunlight"]["water_reflects"], d["sunlight"])[0]
    assert np.isclose(water / absorbed, 0.93 / 0.83)                              # a lake is darker than the ground


def test_the_demand_for_water_by_hand_and_none_where_the_surface_loses_more_energy_than_it_gains():
    d = demand_constants()
    t, p = np.array([20.0]), np.array([101325.0])
    by_hand = 1.26 * 144.7 / (144.7 + 66.7) * 100.0 / 2.453e6 * 86400.0           # mm a day for 100 W/m2: 3.04
    got = ev.priestley_taylor(np.array([100.0]), t, p, d["priestley_taylor_extra"], d["vapour"], d["heat"], d["air"])[0] * 86400.0
    assert abs(by_hand - 3.04) < 0.01 and abs(got / by_hand - 1) < 0.005
    none = ev.priestley_taylor(np.array([-40.0]), t, p, d["priestley_taylor_extra"], d["vapour"], d["heat"], d["air"])
    assert none[0] == 0.0
    high = ev.priestley_taylor(np.array([100.0]), t, ev.air_pressure(np.array([4000.0]), 9.80665, d["air"]),
                               d["priestley_taylor_extra"], d["vapour"], d["heat"], d["air"])[0] * 86400.0
    assert 1.05 < high / got < 1.15                                               # thinner air takes more of the energy as vapour


def test_where_the_formulas_of_the_demand_are_held_at_a_limit():
    """The published formulas are fitted to ground between the sea and the mountains. Outside that each is held at a
    limit [INFERRED: every limit here is mine; the paper does not treat these cases]:
      * ground below sea level gets the sunlight of sea level: the gain with height is not carried below zero;
      * the air never lets through more sunlight than arrives at its top;
      * a surface hotter than the formula's 107 C loses nothing, and never gains;
      * the air pressure is not carried above the height at which the formula ends: it is held at the set share of
        its base, which is reached about 44 km up. Below sea level the formula is carried on: there is more air
        above ground that lies below the sea."""
    d = demand_constants()
    sun, ground = d["sunshine_fraction"], d["sunlight"]["ground_reflects"]
    at = lambda z: ev.absorbed_sunlight(np.array([400.0]), np.array([z]), sun, ground, d["sunlight"])[0]
    assert at(-400.0) == at(0.0) and at(-4000.0) == at(0.0)
    assert at(1000.0) > at(0.0)
    assert np.isclose(at(60_000.0), (1 - ground) * 400.0)           # (0.25 + 0.5 * 0.62)(1 + 2.67e-5 z) passes 1 at 29 km
    assert at(100_000.0) == at(60_000.0)
    assert ev.net_longwave(np.array([107.0, 300.0]), sun, d["longwave"]).tolist() == [0.0, 0.0]
    g = 9.80665
    power = g * 0.028963 / (8.31447 * 0.0065)
    pressure = lambda z: ev.air_pressure(np.array([z]), g, d["air"])[0]
    held_at = 101325.0 * 0.01 ** power                                # by hand: the base of the power held at 0.01
    assert np.isclose(pressure(50_000.0), held_at, rtol=1e-12) and pressure(200_000.0) == pressure(50_000.0)
    assert pressure(288.15 / 0.0065 * (1 - 0.0101)) > held_at         # just below that height the formula still runs
    assert np.isclose(pressure(-400.0), 101325.0 * (1 + 0.0065 * 400.0 / 288.15) ** power) and pressure(-400.0) > 101325.0


# ------------------------------------------------------------------------------------------ lakes (library)
def lake_case(mesh, ground, sea, area, loss, runoff):
    """Hollows, then lakes: `loss` is what each cell loses a year once flooded (m3), `runoff` what each cell sheds
    in each month (months x cells, m3)."""
    recv = dr.receivers(ground, sea, mesh.nbr)
    stack = dr.flow_stack(recv)
    label, table = dr.hollows(ground, sea, recv, stack, mesh.edge_cells, area)
    own = dr.owners(ground, label, table)
    rows = len(table["parent"])
    leaves = np.flatnonzero((table["first_child"] < 0) & (np.arange(rows) > 0))
    plain = dr.accumulate(stack, recv, runoff)
    inflow = np.zeros(rows)
    inflow[leaves] = plain[:, table["bottom_cell"][leaves]].sum(axis=0)
    room = np.bincount(own[own >= 0], weights=loss[own >= 0], minlength=rows)
    moved = lk.settle(table, inflow, room)
    share, level, lake = lk.flooded(table, own, ground, loss, moved["extra"], moved["overflows"])
    lk.check_table(table, label, recv, sea, ground, mesh.nbr)
    flows = lk.lake_flows(table, label, recv, ground, mesh.nbr, share, lake, runoff, moved["extra"], moved["overflows"])
    found = flows["lakes"]
    by_row = {int(r): {k: v[i] for k, v in found.items()} for i, r in enumerate(found["row"])}
    return dict(recv=recv, stack=stack, label=label, table=table, own=own, inflow=inflow, room=room, moved=moved, share=share,
                level=level, lake=lake, discharge=flows["discharge"], passing=flows["passing"], real=flows["receivers"],
                crossing=flows["crossing"], found=found, by_row=by_row, leaves=leaves)


def poured(mesh, where_and_how_much, split=(0.7, 0.3)):
    """Runoff of two "months": the given yearly amounts at the given cells, 70 % in the first and 30 % in the second."""
    runoff = np.zeros((2, mesh.n))
    for cell, amount in where_and_how_much:
        runoff[:, cell] += np.array(split) * amount
    return runoff


@pytest.fixture(scope="module")
def bowls():
    m = get_mesh(5)
    ground, deep, shallow, notch = two_bowls(m)
    area = m.area * R * R
    sea = ground < -1000
    base = lake_case(m, ground, sea, area, area.copy(), np.zeros((2, m.n)))          # every flooded square metre loses a metre a year
    t = base["table"]
    a, b = int(base["label"][np.argmin(np.where(sea, np.inf, ground))]), None
    b = 3 - a
    both = int(t["parent"][a])
    room = base["room"]
    assert both == 3 and room[a] > 0 and room[b] > 0 and room[both] > 0
    return dict(m=m, ground=ground, area=area, sea=sea, t=t, a=a, b=b, both=both, ra=room[a], rb=room[b], rp=room[both],
                bottom_a=int(t["bottom_cell"][a]), bottom_b=int(t["bottom_cell"][b]))


def run_bowls(bw, into_a, into_b):
    return lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], bw["area"].copy(),
                     poured(bw["m"], [(bw["bottom_a"], into_a), (bw["bottom_b"], into_b)]))


def test_a_lake_spreads_until_its_surface_loses_what_arrives(bowls):
    bw = bowls
    a, b, both, ra, rb = bw["a"], bw["b"], bw["both"], bw["ra"], bw["rb"]
    r = run_bowls(bw, 0.5 * ra, 0.25 * rb)
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert np.isclose(extra[a], 0.5 * ra) and np.isclose(extra[b], 0.25 * rb) and extra[both] == 0 and not over.any()
    assert r["moved"]["to_sea"] == 0 and r["moved"]["nowhere"] == 0
    for k, water in ((a, 0.5 * ra), (b, 0.25 * rb)):
        mine = r["label"] == k
        assert np.isclose((r["share"] * bw["area"])[mine].sum(), water)              # flooded area times a metre a year = the water arriving
        level = r["level"][k]
        assert level < bw["t"]["spill_m"][k]                                         # a closed lake, below its pass
        assert np.all(r["share"][mine & (bw["ground"] < level)] == 1.0) and not r["share"][mine & (bw["ground"] > level)].any()
        assert set(r["lake"][mine & (r["share"] > 0)]) == {k}
        row = r["by_row"][k]
        assert np.isclose(row["inflow"], water) and np.isclose(row["loss"], water) and row["outflow"] == 0
        assert not row["overflows"] and row["into_cell"] == -1
    assert np.isnan(r["level"][both]) and not r["share"][r["label"] == 0].any()
    assert not r["discharge"][:, bw["sea"]].any()                                    # nothing reaches the sea
    assert np.allclose(r["passing"][:, bw["bottom_a"]], [0.35 * ra, 0.15 * ra])      # the water reaches the bottom of the bowl
    assert not r["discharge"][:, bw["bottom_a"]].any()                               # which lies under a closed lake: no river there
    assert np.array_equal(r["real"], r["recv"]) and np.all(r["crossing"] == -1)      # and no lake to carry water across


def test_a_full_lake_overflows_into_its_neighbour_and_two_full_ones_become_one(bowls):
    bw = bowls
    a, b, both, ra, rb, rp, t = bw["a"], bw["b"], bw["both"], bw["ra"], bw["rb"], bw["rp"], bw["t"]
    saddle, way_out = t["spill_m"][a], t["spill_m"][both]
    # the deep bowl gets more than it can lose: the rest runs over the saddle into the shallow one
    r = run_bowls(bw, ra + 0.5 * rb, 0.0)
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert np.isclose(extra[a], ra) and over[a] and np.isclose(extra[b], 0.5 * rb) and not over[b] and extra[both] == 0
    assert r["level"][a] == saddle and r["level"][b] < saddle
    assert np.all(r["share"][(r["own"] == a)] == 1.0)
    first, second = r["by_row"][a], r["by_row"][b]
    assert np.isclose(first["inflow"], ra + 0.5 * rb) and np.isclose(first["loss"], ra) and np.isclose(first["outflow"], 0.5 * rb)
    assert first["overflows"] and first["into_cell"] == t["spill_into_cell"][a]
    assert np.isclose(second["inflow"], 0.5 * rb) and np.isclose(second["loss"], 0.5 * rb) and second["outflow"] == 0
    beyond, outlet = t["spill_into_cell"][a], t["spill_from_cell"][a]
    assert np.allclose(r["discharge"][:, beyond], [0.35 * rb, 0.15 * rb])            # each month the lake passes on the same share
    assert np.allclose(r["passing"][:, bw["bottom_b"]], [0.35 * rb, 0.15 * rb])      # ... and it runs down to the other bottom
    assert not r["discharge"][:, bw["bottom_b"]].any()                               # where a closed lake keeps it
    # The water crosses the full lake to its outlet cell: all of it passes there, and what the lake does not lose
    # goes on. The flow at the outlet cell is the lake's outflow.
    assert np.allclose(r["passing"][:, outlet], np.array([0.7, 0.3]) * (ra + 0.5 * rb))
    assert np.allclose(r["discharge"][:, outlet], [0.35 * rb, 0.15 * rb]) and r["real"][outlet] == beyond
    under = (r["label"] == a) & (bw["ground"] <= t["spill_m"][a])
    assert np.array_equal(r["crossing"] == a, under) and under[bw["bottom_a"]] and under[outlet]
    for c in np.flatnonzero(under)[::7]:                                             # every flooded cell hands its water on, cell
        path = follow(r["real"], c)                                                  # by cell inside the lake, to the outlet
        k = path.index(outlet)
        assert np.all(under[path[:k + 1]]) and path[k + 1] == beyond
    share_on = 0.5 * rb / (ra + 0.5 * rb)
    assert np.allclose(r["discharge"][:, under], share_on * r["passing"][:, under])  # inside: the share that will leave
    # the other way round
    r = run_bowls(bw, 0.0, rb + 0.3 * ra)
    assert np.isclose(r["moved"]["extra"][a], 0.3 * ra) and r["moved"]["overflows"][b] and not r["moved"]["overflows"][a]
    # both full: one lake, standing between the saddle and the way out
    r = run_bowls(bw, ra + rb + 0.5 * rp, 0.0)
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert over[a] and over[b] and not over[both] and np.isclose(extra[both], 0.5 * rp)
    assert saddle < r["level"][both] < way_out and np.isnan(r["level"][a]) and np.isnan(r["level"][b])
    wet = r["share"] > 0
    assert set(r["lake"][wet]) == {both} and np.all(r["share"][bw["ground"] < saddle][np.isin(r["label"][bw["ground"] < saddle], (a, b))] == 1.0)
    assert list(r["found"]["row"]) == [both]
    one = r["by_row"][both]
    assert np.isclose(one["inflow"], ra + rb + 0.5 * rp) and np.isclose(one["loss"], one["inflow"]) and one["outflow"] == 0
    assert np.isclose((r["share"] * bw["area"]).sum(), ra + rb + 0.5 * rp)
    # each gets more than it can lose by itself: the same one lake
    r = run_bowls(bw, 1.5 * ra, 1.2 * rb)
    assert 0.5 * ra + 0.2 * rb < rp
    assert np.isclose(r["moved"]["extra"][both], 0.5 * ra + 0.2 * rb) and list(r["found"]["row"]) == [both]
    # more than the whole hollow can lose: it stands at the notch and the rest runs to the sea
    spare = 0.25 * ra
    r = run_bowls(bw, ra + rb + rp + spare, 0.0)
    assert r["moved"]["overflows"][both] and np.isclose(r["moved"]["to_sea"], spare) and r["level"][both] == way_out
    one = r["by_row"][both]
    assert one["overflows"] and one["into_cell"] == t["spill_into_cell"][both] and np.isclose(one["outflow"], spare)
    assert np.allclose(r["discharge"][:, bw["sea"]].sum(axis=1), [0.7 * spare, 0.3 * spare])
    assert np.all(r["share"][np.isin(r["label"], (a, b)) & (bw["ground"] < way_out)] == 1.0)


def test_cells_that_lose_nothing_when_flooded_are_flooded_only_while_water_is_left(bowls):
    """Where the air already takes all it asks from wet ground, flooding costs nothing more. Such ground floods as the
    water passes it and stays dry once the water is used up lower down."""
    bw = bowls
    a, t = bw["a"], bw["t"]
    own_a = np.flatnonzero(lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], bw["area"].copy(), np.zeros((2, bw["m"].n)))["own"] == a)
    by_height = own_a[np.argsort(bw["ground"][own_a])]
    loss = bw["area"].copy()
    free = by_height[3:6]                                                         # the fourth to sixth lowest cells cost nothing
    loss[free] = 0.0
    lowest = bw["area"][by_height[:3]].sum()
    r = lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], loss, poured(bw["m"], [(bw["bottom_a"], 0.5 * lowest)]))
    assert not r["share"][free].any()                                             # the water is used up below them
    r = lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], loss, poured(bw["m"], [(bw["bottom_a"], lowest + 0.5 * bw["area"][by_height[6]])]))
    assert np.all(r["share"][free] == 1.0) and np.isclose(r["share"][by_height[6]], 0.5)
    # hollows that lose nothing at all overflow with the first drop, one into the next and on to the sea
    r = lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], np.zeros(bw["m"].n), poured(bw["m"], [(bw["bottom_a"], 5.0)]))
    assert np.all(r["moved"]["overflows"][[a, bw["b"], bw["both"]]]) and np.all(r["share"][r["own"] >= 0] == 1.0)
    assert list(r["found"]["row"]) == [bw["both"]] and np.isclose(r["by_row"][bw["both"]]["outflow"], 5.0)
    assert np.isclose(r["moved"]["to_sea"], 5.0) and r["level"][bw["both"]] == t["spill_m"][bw["both"]]
    # with a loss only in the shallow bowl, the deep one still overflows with the first drop, and the shallow one keeps it
    only_b = np.where(r["label"] == bw["b"], bw["area"], 0.0)
    r = lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], only_b, poured(bw["m"], [(bw["bottom_a"], 5.0)]))
    assert r["moved"]["overflows"][a] and not r["moved"]["overflows"][bw["b"]] and np.isclose(r["by_row"][a]["outflow"], 5.0)
    assert np.all(r["share"][r["own"] == a] == 1.0) and np.isclose(r["moved"]["extra"][bw["b"]], 5.0)
    # ... but not with none
    r = lake_case(bw["m"], bw["ground"], bw["sea"], bw["area"], np.zeros(bw["m"].n), np.zeros((2, bw["m"].n)))
    assert not r["moved"]["overflows"].any() and not r["share"].any() and len(r["found"]["row"]) == 0


def three_pits(mesh):
    """A cone with three pits down one side: each one overflows into the ground of the next, the last toward the sea."""
    from_top = angle_from(mesh, 90, 0)
    ground = 3000.0 - 30.0 * from_top
    for lat in (75.0, 55.0, 37.0):
        ground = np.minimum(ground, 3000.0 - 30.0 * (90.0 - lat) - 600.0 + 100.0 * angle_from(mesh, lat, 0))
    sea = from_top > 64
    ground = np.where(sea, -3000.0, ground) + 0.05 * np.arange(mesh.n) / mesh.n
    return ground.astype(np.float32).astype(np.float64), sea


def test_a_chain_of_lakes_passes_its_water_down_from_the_highest_to_the_sea():
    m = get_mesh(6)
    area = m.area * R * R
    ground, sea = three_pits(m)
    base = lake_case(m, ground, sea, area, area.copy(), np.zeros((2, m.n)))
    t = base["table"]
    assert len(t["parent"]) == 4 and list(t["spill_into_hollow"][1:]) == [2, 3, 0]   # three hollows, each a tree of its own
    assert lk.tree_order(t) == [1, 2, 3]
    r1, r2, r3 = base["room"][1:]
    bottoms = t["bottom_cell"]
    assert 0.3 * r2 < r3
    r = lake_case(m, ground, sea, area, area.copy(), poured(m, [(bottoms[1], r1 + 0.6 * r2), (bottoms[2], 0.7 * r2)]))
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert list(over[1:]) == [True, True, False]
    assert np.allclose(extra[1:], [r1, r2, 0.3 * r2]) and r["moved"]["to_sea"] == 0
    rows = r["by_row"]
    assert np.isclose(rows[1]["outflow"], 0.6 * r2) and np.isclose(rows[2]["inflow"], 1.3 * r2) and np.isclose(rows[2]["outflow"], 0.3 * r2)
    assert np.isclose(rows[3]["inflow"], 0.3 * r2) and rows[3]["outflow"] == 0 and not rows[3]["overflows"]
    assert r["level"][1] == t["spill_m"][1] and r["level"][2] == t["spill_m"][2] and r["level"][3] < t["spill_m"][3]
    # month by month: the first lake passes on 0.6 r2 of r1 + 0.6 r2, the second 0.3 of the 1.3 r2 that reach it
    assert np.allclose(r["discharge"][:, t["spill_into_cell"][1]], np.array([0.7, 0.3]) * 0.6 * r2)
    assert np.allclose(r["passing"][:, t["spill_from_cell"][2]], np.array([0.7, 0.3]) * 1.3 * r2)       # all of it crosses the second lake
    assert np.allclose(r["discharge"][:, t["spill_from_cell"][2]], np.array([0.7, 0.3]) * 0.3 * r2)     # and this much leaves it
    assert np.allclose(r["discharge"][:, t["spill_into_cell"][2]], np.array([0.7, 0.3]) * 0.3 * r2)
    assert not r["discharge"][:, bottoms[3]].any() and np.allclose(r["passing"][:, bottoms[3]].sum(), 0.3 * r2)
    assert not r["discharge"][:, sea].any()
    # enough for all three: what is left reaches the sea
    r = lake_case(m, ground, sea, area, area.copy(), poured(m, [(bottoms[1], r1 + r2 + r3 + 7.0e9)]))
    assert list(r["moved"]["overflows"][1:]) == [True, True, True] and np.isclose(r["moved"]["to_sea"], 7.0e9)
    assert np.allclose(r["discharge"][:, sea].sum(axis=1), np.array([0.7, 0.3]) * 7.0e9)
    assert np.isclose((r["share"] * area).sum(), r1 + r2 + r3)


@pytest.mark.parametrize("seed", [51, 52, 53, 54, 55, 56])
def test_on_rough_ground_every_lake_keeps_the_rules(seed):
    """Random ground with hollows inside hollows, random losses (a fifth of the cells lose nothing) and random runoff.
    Whatever the lakes come to: the water is all accounted for; no hollow loses more than its flooded ground can; a
    hollow passes water on only when it is full; a larger hollow holds water of its own only when both its parts
    overflow; in a lake the lower ground floods first; and a lake is level."""
    m = get_mesh(4)
    rng = np.random.default_rng(seed)
    area = m.area * R * R
    ground = rough_ground(m, seed, relief=500.0, bumps=600.0, wave_number=(3.0, 14.0))
    shore = np.quantile(ground, 0.1)
    sea = ground < shore
    wetness = rng.choice([0.02, 0.3, 1.5])                                        # an arid, a middling and a wet world
    loss = area * rng.random(m.n) * (rng.random(m.n) > 0.2)
    runoff = area[None, :] * rng.random((3, m.n)) * wetness * (rng.random(m.n) < 0.5)[None, :] * ~sea[None, :]
    r = lake_case(m, np.where(sea, shore, ground), sea, area, loss, runoff)
    t, extra, over, room = r["table"], r["moved"]["extra"], r["moved"]["overflows"], r["room"]
    rows = len(t["parent"])
    merged = np.flatnonzero(t["first_child"] >= 0)
    # the water
    assert np.isclose(r["inflow"].sum(), extra.sum() + r["moved"]["to_sea"] + r["moved"]["nowhere"], rtol=1e-9)
    assert np.isclose(r["discharge"][:, sea].sum(), runoff.sum() - extra.sum(), rtol=1e-9)
    # the hollows
    assert np.all(extra >= 0) and np.all(extra <= room * (1 + 1e-12) + 1e-9)
    assert np.allclose(extra[over], room[over])
    for k in merged:
        if extra[k] > 0 or over[k]:
            assert over[t["first_child"][k]] and over[t["second_child"][k]]
    # the flooded ground
    used = np.bincount(r["own"][r["own"] >= 0], weights=(r["share"] * loss)[r["own"] >= 0], minlength=rows)
    assert np.allclose(used, extra, rtol=1e-9, atol=1e-3)
    assert np.all(r["share"][(r["own"] >= 0) & over[np.maximum(r["own"], 0)]] == 1.0) and not r["share"][r["own"] < 0].any()
    surface = np.where(sea, shore, ground)
    lakes = np.unique(r["lake"][r["lake"] >= 0])
    assert lakes.size >= 3
    for u in lakes:
        cells = np.flatnonzero(r["lake"] == u)
        level = r["level"][u]
        inside = np.isin(r["label"], region_of(t, u))
        assert np.all(surface[cells] <= level)                                    # no flooded ground stands above the lake's surface
        below = inside & (surface < level)
        assert np.all(r["share"][below] == 1.0)                                   # and all ground below it is under water
        if over[u]:
            assert level == t["spill_m"][u]
        else:
            assert level < t["spill_m"][u] or np.isnan(t["spill_m"][u])
    # the yearly books of every lake
    f = r["found"]
    assert np.allclose(f["inflow"], f["loss"] + f["outflow"], rtol=1e-9, atol=1e-3)
    assert not f["outflow"][~f["overflows"]].any() and np.all(f["into_cell"][~f["overflows"]] == -1)
    assert not f["left_over"].any()                                               # with a sea, every hollow has a way out
    assert over.any() and (~f["overflows"]).any() if wetness == 0.3 else True
    assert r["moved"]["dropped"] <= 1e-9 * runoff.sum() + 1e-6 * rows             # what rounding is allowed to drop
    # the water through the lakes. A lake that overflows: all that reaches it crosses to its outlet cell, the flow
    # there is its outflow, in every month the same share of what arrives, and the cell beyond the pass takes it on.
    year, passing = r["discharge"].sum(axis=0), r["passing"].sum(axis=0)
    crossing = r["crossing"]
    for i in np.flatnonzero(f["overflows"]):
        u, out_cell, beyond = f["row"][i], t["spill_from_cell"][f["row"][i]], f["into_cell"][i]
        assert crossing[out_cell] == u and r["real"][out_cell] == beyond and crossing[beyond] != u
        assert np.isclose(passing[out_cell], f["inflow"][i], rtol=1e-9) and np.isclose(year[out_cell], f["outflow"][i], rtol=1e-9, atol=1e-3)
        if f["inflow"][i] > 0:
            assert np.allclose(r["discharge"][:, out_cell], r["passing"][:, out_cell] * f["outflow"][i] / f["inflow"][i], rtol=1e-9, atol=1e-6)
        mine = np.flatnonzero(crossing == u)
        assert np.all(surface[mine] <= t["spill_m"][u]) and np.all(np.isin(r["label"][mine], region_of(t, u)))
        assert np.all(r["share"][mine][surface[mine] < t["spill_m"][u]] == 1.0)
        inner = mine[mine != out_cell]
        assert np.all(crossing[r["real"][inner]] == u)                           # inside, water is handed on inside
        assert passing[beyond] >= f["outflow"][i] * (1 - 1e-9)                    # (what passes there, before any lake it lies in takes its share)
    # a closed lake keeps what reaches it: the flow counts for the part of a cell that is not under water
    closed = (crossing < 0) & (r["share"] > 0)
    assert np.allclose(r["discharge"][:, closed], r["passing"][:, closed] * (1 - r["share"][closed]), rtol=1e-12)
    dry = (crossing < 0) & (r["share"] == 0)
    assert np.array_equal(r["discharge"][:, dry], r["passing"][:, dry]) and np.array_equal(r["real"][dry], r["recv"][dry])
    assert np.all(r["discharge"] >= 0)


def bowl_and_two_pits(mesh):
    """The ring of two_bowls, but in place of the shallow bowl two pits that share a low sill: a hollow inside the ring
    that is itself made of two."""
    deep = angle_from(mesh, 0, -12)
    north_pit, south_pit = angle_from(mesh, 5, 14), angle_from(mesh, -5, 14)
    middle = angle_from(mesh, 0, 0)
    floors = np.minimum(200.0 + 60.0 * deep, np.minimum(500.0 + 60.0 * north_pit, 400.0 + 60.0 * south_pit))
    inside = np.maximum(floors, 2000.0 - 300.0 * (26.0 - middle))
    ground = np.where(middle < 26, inside, 2000.0 - 150.0 * (middle - 26.0))
    notch = angle_from(mesh, 0, 26) < 5
    ground = np.where(notch, np.minimum(ground, 1500.0 - 20.0 * (middle - 21.0)), ground)
    ground = np.where(middle > 34, -3000.0, ground) + 0.05 * np.arange(mesh.n) / mesh.n
    return ground.astype(np.float32).astype(np.float64)


@pytest.fixture(scope="module")
def nest():
    m = get_mesh(5)
    ground = bowl_and_two_pits(m)
    area = m.area * R * R
    sea = ground < -1000
    base = lake_case(m, ground, sea, area, area.copy(), np.zeros((2, m.n)))
    t = base["table"]
    at = lambda lat, lon: int(base["label"][np.argmin(angle_from(m, lat, lon))])
    deep, north, south = at(0, -12), at(5, 14), at(-5, 14)
    pair, whole = int(t["parent"][north]), int(t["parent"][deep])
    assert sorted((deep, north, south)) == [1, 2, 3] and t["parent"][south] == pair and t["parent"][pair] == whole and t["parent"][whole] == -1
    assert t["spill_into_hollow"][deep] == south and t["spill_into_hollow"][south] == north and t["spill_into_hollow"][north] == south
    room = base["room"]
    run = lambda *pours: lake_case(m, ground, sea, area, area.copy(), poured(m, [(t["bottom_cell"][k], w) for k, w in pours]))
    return dict(m=m, ground=ground, area=area, sea=sea, t=t, deep=deep, north=north, south=south, pair=pair, whole=whole,
                room=room, run=run)


def test_water_that_overflows_into_a_hollow_made_of_two_fills_them_in_the_order_the_ground_gives(nest):
    """The deep bowl overflows into the southern pit. That pit fills and overflows into the northern one. When both are
    full they are one lake, which rises until it meets the deep bowl's own lake at the saddle; then all three are one."""
    n = nest
    deep, north, south, pair, whole, room, run = (n[k] for k in ("deep", "north", "south", "pair", "whole", "room", "run"))
    rd, rn, rs, rp, rw = room[deep], room[north], room[south], room[pair], room[whole]
    # into the southern pit, and from it half-way up the northern one
    r = run((deep, rd + rs + 0.5 * rn))
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert over[deep] and over[south] and not over[north] and not over[pair]
    assert np.allclose(extra[[deep, south, north, pair, whole]], [rd, rs, 0.5 * rn, 0, 0])
    rows = r["by_row"]
    assert sorted(rows) == sorted((deep, south, north))                              # three lakes, each in its own hollow
    assert np.isclose(rows[deep]["outflow"], rs + 0.5 * rn) and np.isclose(rows[south]["inflow"], rs + 0.5 * rn)
    assert np.isclose(rows[south]["outflow"], 0.5 * rn) and np.isclose(rows[north]["inflow"], 0.5 * rn) and rows[north]["outflow"] == 0
    # both pits full: the pair is one lake, part full, and the deep bowl still overflows into it
    r = run((deep, rd + rs + rn + 0.5 * rp))
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert over[deep] and over[south] and over[north] and not over[pair] and np.isclose(extra[pair], 0.5 * rp) and extra[whole] == 0
    assert sorted(r["by_row"]) == sorted((deep, pair))
    assert np.isclose(r["by_row"][pair]["inflow"], rs + rn + 0.5 * rp) and np.isclose(r["by_row"][pair]["loss"], rs + rn + 0.5 * rp)
    assert n["t"]["spill_m"][south] < r["level"][pair] < n["t"]["spill_m"][pair]
    assert set(r["lake"][np.isin(r["label"], (north, south)) & (r["share"] > 0)]) == {pair}
    # everything full to the saddle and half the room above it: one lake
    r = run((deep, rd + rs + rn + rp + 0.5 * rw))
    assert np.all(r["moved"]["overflows"][[deep, north, south, pair]]) and not r["moved"]["overflows"][whole]
    assert np.isclose(r["moved"]["extra"][whole], 0.5 * rw) and list(r["found"]["row"]) == [whole]
    assert np.isclose((r["share"] * n["area"]).sum(), rd + rs + rn + rp + 0.5 * rw)
    # the northern pit overflows into the southern one, and the deep bowl adds to it from the other side
    r = run((north, rn + 0.2 * rs), (deep, rd + 0.5 * rs))
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert over[north] and over[deep] and not over[south] and np.isclose(extra[south], 0.7 * rs) and extra[pair] == 0
    assert np.isclose(r["by_row"][south]["inflow"], 0.7 * rs)
    # ... and fills it: with the northern pit already full, the two are one lake at once
    r = run((north, rn + 0.2 * rs), (deep, rd + rs))
    extra, over = r["moved"]["extra"], r["moved"]["overflows"]
    assert over[north] and over[south] and over[deep] and not over[pair] and np.isclose(extra[pair], 0.2 * rs)
    assert sorted(r["by_row"]) == sorted((deep, pair))


def test_rounding_cannot_make_a_lake_overflow(nest):
    """A lake that receives what it can lose stands at its pass and passes nothing on. A sum that comes out a hair too
    large must not turn that into an overflow, with a lake of its own downstream: less than a billionth of what reaches
    a hollow counts as none."""
    n = nest
    full = n["room"][n["north"]]
    r = n["run"]((n["north"], full * (1 + 1e-12)))
    assert not r["moved"]["overflows"].any() and not r["moved"]["extra"][n["south"]]
    assert list(r["found"]["row"]) == [n["north"]] and r["found"]["outflow"][0] == 0
    r = n["run"]((n["north"], full * (1 + 1e-6)))                                    # a millionth more is water
    assert r["moved"]["overflows"][n["north"]] and np.isclose(r["moved"]["extra"][n["south"]], full * 1e-6, rtol=1e-3)


def test_less_than_a_millionth_of_a_cubic_metre_a_year_is_no_water():
    """The other allowance of settle(): what is left of a pour once it is below a millionth of a cubic metre a year
    counts as none, however large a share of the pour it is. One hollow that overflows to the sea, handed amounts
    of that size and then real ones."""
    table = {"parent": np.array([-1, -1]), "sibling": np.array([-1, -1]), "first_child": np.array([-1, -1]),
             "second_child": np.array([-1, -1]), "spill_into_hollow": np.array([-1, 0])}
    moved = lk.settle(table, np.array([0.0, 2.0e-7]), np.array([0.0, 1.0e-7]))
    assert not moved["overflows"][1] and moved["to_sea"] == 0.0
    assert moved["extra"][1] == 1.0e-7 and np.isclose(moved["dropped"], 1.0e-7, rtol=1e-9)
    moved = lk.settle(table, np.array([0.0, 2.0]), np.array([0.0, 1.0]))
    assert moved["overflows"][1] and moved["to_sea"] == 1.0 and moved["dropped"] == 0.0 and moved["extra"][1] == 1.0


def test_two_full_hollows_with_nothing_more_stand_as_one_lake_at_the_pass_between_them(nest):
    n = nest
    t, north, south, pair = n["t"], n["north"], n["south"], n["pair"]
    rows = len(t["parent"])
    over = np.zeros(rows, dtype=bool)
    over[[north, south]] = True
    extra = np.where(over, n["room"], 0.0)
    own = dr.owners(n["ground"], lake_case(n["m"], n["ground"], n["sea"], n["area"], n["area"], np.zeros((2, n["m"].n)))["label"], t)
    share, level, lake = lk.flooded(t, own, n["ground"], n["area"], extra, over)
    assert level[pair] == t["spill_m"][north] and np.isnan(level[north]) and np.isnan(level[south])
    assert set(lake[share > 0]) == {pair} and np.all(share[np.isin(own, (north, south))] == 1.0) and not share[own == pair].any()


# ------------------------------------------------------------------------------------------ Hydrology and Soils
def monthly(value, n):
    """A value for every month and cell from a number, one value per cell, twelve monthly values, or the full array."""
    a = np.asarray(value, dtype=np.float64)
    if a.ndim == 2:
        return a
    if a.shape == (12,):
        return a[:, None] * np.ones((1, n))
    return np.broadcast_to(a, (12, n)).copy()


def watered(elevation, volume, rain, temperature_c, sunlight=300.0, snowfall=0.0, level=4, capacity=None, constants=None):
    """SeaLevel, Drainage and then Hydrology on the given ground under the given climate."""
    hh, area, sea, d = drained(elevation, volume, level)
    n = hh.mesh.n
    reads = {"precipitation": monthly(rain, n), "snowfall": monthly(snowfall, n), "surface_temperature": monthly(temperature_c, n) + 273.15,
             "insolation": monthly(sunlight, n), "elevation": elevation,
             "height_above_sea": sea.fields["height_above_sea"], "flow_receiver": d.fields["flow_receiver"],
             "depression_id": d.fields["depression_id"], "cell_area": area, "ocean_mask": sea.fields["ocean_mask"]}
    lagged = {} if capacity is None else {"soil_water_capacity": np.where(sea.fields["ocean_mask"], 0.0, capacity)}
    out = hh.run("Hydrology", reads=reads, lagged=lagged, tables={"hollows": d.tables["hollows"]}, constants=constants)
    return hh, area, sea, d, out, reads


def cone(mesh):
    away = angle_from(mesh, 40, 25)
    return np.where(away > 60, -1000.0, 3000.0 - 60.0 * away), away


def demand_by_hand(net_radiation, celsius, height_m):
    """The Priestley-Taylor rule with every number written out, in mm a month."""
    slope = 2.503e6 * np.exp(17.27 * celsius / (celsius + 237.3)) / (celsius + 237.3) ** 2
    heat = 1.91846e6 * ((celsius + 273.15) / (celsius + 273.15 - 33.91)) ** 2
    pressure = 101325.0 * (1 - 0.0065 * height_m / 288.15) ** (9.81 * 0.028963 / (8.31447 * 0.0065))
    psychrometric = 1004.6 * 0.028963 * pressure / (0.01802 * heat)
    return 1.26 * slope / (slope + psychrometric) * np.maximum(net_radiation, 0.0) / heat * MONTH_S


def test_in_a_basin_under_even_rain_the_flow_at_the_mouth_is_rain_less_evaporation_times_the_area():
    m = get_mesh(4)
    ground, away = cone(m)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, rain=100.0, temperature_c=20.0)
    f = out.fields
    wet = sea.fields["ocean_mask"]
    land = ~wet
    # the demand of the air, by hand: of 300 W/m2 of sunlight the share 0.25 + 0.5 * 0.62 reaches the ground at sea level
    # and more at height, the ground absorbs 0.83 of it, and it radiates away (0.2 + 0.8 * 0.62) * (107 - 20) W/m2
    height = sea.fields["height_above_sea"].astype(np.float64)
    net = 0.83 * (0.25 + 0.5 * 0.62) * (1 + 2.67e-5 * height) * 300.0 - (0.2 + 0.8 * 0.62) * (107.0 - 20.0)
    assert abs(net[land].min() - 78.9) < 0.2                 # W/m2 on the coast; 92 W/m2 on the top, 3,600 m above this sea
    by_hand = demand_by_hand(net, 20.0, height)
    assert np.allclose(f["potential_evapotranspiration"][:, land], by_hand[land], rtol=2e-5)
    assert np.allclose(out.drivers["potential_evapotranspiration"]["net_radiation"][:, land], net[land], rtol=1e-5)
    low = land & (height < 30.0)
    assert low.any() and np.all(np.abs(f["potential_evapotranspiration"][0, low] - 73.0) < 0.3)       # mm a month on the coast
    assert np.all(f["potential_evapotranspiration"][0, land & (height > 3000)] > 86.0)                 # more in the thin air of the top
    # more rain than the air asks for: the soil stays full, the air gets all it asks, the rest runs off
    assert np.allclose(f["soil_moisture"][:, land], 1.0) and np.allclose(f["evapotranspiration"][:, land], by_hand[land], rtol=2e-5)
    assert np.allclose(f["runoff"][:, land], 100.0 - by_hand[land], rtol=1e-4) and np.allclose(f["runoff_annual"][land], 12 * (100.0 - by_hand[land]), rtol=1e-4)
    # at every mouth: rain less evaporation, times the area of the basin
    basin = d.fields["basin_id"]
    net_water = (100.0 - f["evapotranspiration"][0].astype(np.float64)) * area / 1000.0 / MONTH_S      # m3/s from each cell
    mouths = np.unique(basin[land])
    expected = np.bincount(basin[land], weights=net_water[land], minlength=m.n)[mouths]
    assert np.allclose(f["river_discharge"][0, mouths], expected, rtol=1e-5)
    assert np.allclose(f["river_discharge"][:, mouths].std(axis=0), 0.0, atol=1e-6 * expected.max())     # the same in every month
    # the sea receives it all, and holds none of the land's fields
    assert np.isclose(f["river_discharge"][0, wet].sum(), net_water[land].sum(), rtol=1e-5)
    assert not f["evapotranspiration"][:, wet].any() and not f["runoff"][:, wet].any() and not f["snow_water"].any()
    assert np.all(np.isnan(f["potential_evapotranspiration"][:, wet])) and np.all(np.isnan(f["soil_moisture"][:, wet]))
    assert not f["lake_fraction"].any() and np.all(np.isnan(f["lake_level"])) and len(out.tables["lakes"]["hollow"]) == 0
    dr_ = out.drivers
    assert np.allclose(dr_["runoff"]["from_rain"], f["runoff"], atol=1e-4) and not dr_["runoff"]["from_snowmelt"].any()
    top = int(np.argmin(away))
    source = dr_["river_discharge"]["largest_source"]
    assert source[top] == -1 and not dr_["river_discharge"]["from_upstream"][:, top].any()      # nothing lies above the top
    # The largest single source of a river: the cell upstream of it, never the cell itself, that sheds the most water.
    recv = d.fields["flow_receiver"]
    sheds = f["runoff_annual"].astype(np.float64) * area
    paths = {int(c): follow(recv, c) for c in np.flatnonzero(land)}
    for c in np.flatnonzero(land)[::23]:
        above = [k for k, path in paths.items() if c in path[1:]]                # the cells whose water passes c
        if above:
            assert source[c] in above and sheds[source[c]] == max(sheds[k] for k in above)
        else:
            assert source[c] == -1
    assert (source[land] >= 0).sum() > 300 and np.all(source[land] != np.flatnonzero(land))
    assert set(dr_["river_discharge"]["place"][land]) == {0} and set(dr_["river_discharge"]["place"][wet]) == {3}
    assert not dr_["river_discharge"]["through_lake"].any()


def test_on_low_ground_under_even_rain_every_river_carries_its_drained_area_times_one_number():
    """The statement of the design, to the letter: with the same rain and the same evaporation everywhere, the flow at
    an outlet is (rain - evaporation) times the area of the basin. On a cone that rises 30 m above the sea the air's
    demand is the same everywhere to within a third of a percent (it grows by about 0.8 % for every 100 m of height)."""
    m = get_mesh(4)
    away = angle_from(m, 40, 25)
    ground = np.where(away > 60, -1000.0, 30.0 - 0.5 * away)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 995.0, rain=100.0, temperature_c=20.0)
    f = out.fields
    land = ~sea.fields["ocean_mask"]
    assert sea.fields["height_above_sea"][land].max() < 40.0
    to_air = f["evapotranspiration"][0, land].astype(np.float64)
    assert to_air.max() / to_air.min() < 1.004 and abs(to_air.mean() - 73.05) < 0.2
    flow = (100.0 - to_air.mean()) * d.fields["drainage_area"] / 1000.0 / MONTH_S
    assert np.allclose(f["river_discharge"][:, land], flow[land], rtol=1e-2)      # at every cell of every river, in every month


def test_in_a_dry_climate_the_air_takes_all_the_rain_and_no_river_runs():
    m = get_mesh(4)
    ground, away = cone(m)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, rain=20.0, temperature_c=20.0)
    f = out.fields
    land = ~sea.fields["ocean_mask"]
    demand = f["potential_evapotranspiration"].astype(np.float64)
    assert np.allclose(f["evapotranspiration"][:, land], 20.0, atol=1e-4) and not f["runoff"].any() and not f["river_discharge"].any()
    # the soil rests where the air takes exactly what falls: at 20 / demand of the critical level, 0.75 of its capacity
    assert np.allclose(f["soil_moisture"][:, land], 0.75 * 20.0 / demand[:, land], rtol=1e-4)
    assert not out.notices


def test_water_in_equals_water_out_for_every_basin_on_rough_ground_with_lakes_and_snow():
    m = get_mesh(4)
    rng = np.random.default_rng(61)
    ground = rough_ground(m, 61, relief=1500.0, bumps=400.0)
    lat = np.deg2rad(m.lat)
    season = np.cos(2 * np.pi * (np.arange(12) - 6.5) / 12)[:, None] * np.sign(m.lat)[None, :]        # warm in each half's summer
    celsius = 26.0 - 40.0 * np.sin(lat)[None, :] ** 2 + 12.0 * season - 6.5e-3 * np.maximum(ground, 0.0)[None, :]
    rain = (20.0 + 130.0 * rng.random(m.n))[None, :] * (0.4 + 0.6 * rng.random((12, m.n)))
    snowfall = np.where(celsius < 0.0, rain, 0.0)
    sunlight = 340.0 * np.cos(lat)[None, :] * (1.0 + 0.5 * season * np.abs(np.sin(lat))[None, :])
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[ground < 0].sum() * 1000.0, rain, celsius, sunlight, snowfall)
    f, lakes = out.fields, out.tables["lakes"]
    wet = sea.fields["ocean_mask"]
    land = ~wet
    fell = reads["precipitation"].sum(axis=0)
    to_air = f["evapotranspiration"].astype(np.float64).sum(axis=0)
    net = (fell - to_air) * area / 1000.0                                          # m3 a year that each cell does not give back to the air
    river = f["river_discharge"].astype(np.float64).sum(axis=0) * MONTH_S          # m3 a year through each cell
    basin = d.fields["basin_id"]
    mouths = np.unique(basin[land])
    kept = np.bincount(basin[land], weights=net[land], minlength=m.n)[mouths]
    # every basin: rain less evaporation leaves the land. A plain river leaves through its mouth, the last land cell
    # before the sea. A hollow on the coast, which would overflow straight into the sea, is named after its outlet
    # cell: what leaves there is the outflow of its lake, and nothing if the lake stands below its pass.
    recv, t = d.fields["flow_receiver"], d.tables["hollows"]
    tops = dr.top_hollows(t)
    outflow = dict(zip(lakes["hollow"].tolist(), lakes["outflow_m3_per_year"].tolist()))
    on_coast = ~((recv[mouths] >= 0) & wet[np.maximum(recv[mouths], 0)])          # outlet cells of hollows on the coast
    leaves_land = np.where(on_coast, [outflow.get(int(tops[d.fields["depression_id"][mo]]), 0.0) for mo in mouths], river[mouths])
    # The books close to within what the bucket allows a year to differ from the next (0.01 mm) and the rounding of
    # the stored fields (a few millionths of the rain).
    slack = np.bincount(basin[land], weights=((0.02 + 5e-6 * fell) * area / 1000.0)[land], minlength=m.n)[mouths]
    assert np.all(np.abs(leaves_land - kept) <= slack)
    assert on_coast.any()                                                         # the case holds a hollow on the coast
    for mo in mouths[on_coast]:                                                   # where its lake overflows, the river at the
        if outflow.get(int(tops[d.fields["depression_id"][mo]]), 0.0) > 0:        # outlet cell is that outflow
            assert np.isclose(river[mo], outflow[int(tops[d.fields["depression_id"][mo]])], rtol=1e-5)
    assert (kept > 100 * slack).sum() > 20                                        # and the test is not empty: most basins shed water
    assert np.isclose(river[wet].sum(), net[land].sum(), rtol=1e-5)
    demand = f["potential_evapotranspiration"].astype(np.float64)
    dry_ground = land & (f["lake_fraction"] == 0)
    assert np.all(f["evapotranspiration"][:, dry_ground] <= demand[:, dry_ground] * (1 + 1e-5) + 1e-4)
    # the case holds what it should: lakes of both kinds, snow that melts and snow that stays, dry soils and wet ones
    assert lakes["overflows"].any() and (~lakes["overflows"]).any()
    assert np.allclose(lakes["inflow_m3_per_year"], lakes["loss_to_air_m3_per_year"] + lakes["outflow_m3_per_year"], rtol=1e-9, atol=1.0)
    assert np.all(lakes["outlet_cell"][~lakes["overflows"]] == -1) and np.all(lakes["spills_into_cell"][lakes["overflows"]] >= 0)
    snow = f["snow_water"].astype(np.float64)
    assert (snow.min(axis=0)[land] > 0).any() and ((snow.max(axis=0) > 0) & (snow.min(axis=0) == 0))[land].any()
    moisture = f["soil_moisture"].astype(np.float64)
    assert np.nanmin(moisture[:, land]) < 0.2 and np.nanmax(moisture[:, land]) == 1.0
    # the lakes on the map are the lakes of the table
    flooded = f["lake_fraction"] > 0
    assert np.isclose((f["lake_fraction"].astype(np.float64) * area).sum(), lakes["area_m2"].sum(), rtol=1e-5)
    assert np.array_equal(flooded, ~np.isnan(f["lake_level"])) and not flooded[wet].any()
    which = out.drivers["lake_fraction"]["lake"]
    # a lake is named for the ground it covers, and for a cell at its brim: ground exactly at the level of a lake that
    # overflows, which the lake covers none of and whose water crosses it on the way to the pass
    brim = out.drivers["lake_fraction"]["state"] == 4
    assert np.array_equal(which >= 0, flooded | brim) and not (flooded & brim).any()
    assert np.all(out.drivers["river_discharge"]["place"][brim] == 4) and np.all(lakes["overflows"][which[brim]])
    assert np.allclose(ground[brim], lakes["level_m"][which[brim]], atol=1e-2)
    assert np.allclose(f["lake_level"][flooded], lakes["level_m"][which[flooded]], atol=1e-2)
    assert np.all(ground[flooded] <= f["lake_level"][flooded] + 1e-2)             # no flooded ground stands above its lake
    full = f["lake_fraction"] == 1.0
    strong = demand[:, full] > 80.0                          # open water gives the air all it asks, and it asks more of dark water:
    ratio = f["evapotranspiration"][:, full][strong] / demand[:, full][strong]       # by 0.93 / 0.83 in sunlight absorbed, and by
    assert full.any() and strong.sum() > 100 and ratio.min() > 1.12 and ratio.max() < 1.3  # more in energy left after the heat radiated away
    assert np.all(f["evapotranspiration"][:, full] >= demand[:, full] * (1 - 1e-5))
    # the parts recorded for the "why" answers add up
    # (shed_as_if_dry is no part of the sum: it is what the ground would shed with no lake on it, kept for the sentence
    # of a cell under a lake, whose field holds nothing)
    for name in ("runoff", "river_discharge", "evapotranspiration"):
        total = sum(v.astype(np.float64) for term, v in out.drivers[name].items() if v.dtype.kind == "f" and term != "shed_as_if_dry")
        value = f[name].astype(np.float64)
        assert np.allclose(total, value, rtol=1e-4, atol=1e-6 * np.abs(value).max())
    as_if_dry = out.drivers["runoff"]["shed_as_if_dry"].astype(np.float64)
    runoff_field = f["runoff"].astype(np.float64)
    no_lake = land & (f["lake_fraction"] == 0)
    assert np.allclose(as_if_dry[:, no_lake], runoff_field[:, no_lake], rtol=1e-5, atol=1e-6) and not as_if_dry[:, wet].any()
    assert np.all(as_if_dry[:, flooded] >= runoff_field[:, flooded] - 1e-6) and (as_if_dry[:, full].sum(axis=0) > 0).any()
    into = out.drivers["river_discharge"]["into_the_lake"].astype(np.float64)
    under_closed = np.isin(out.drivers["river_discharge"]["place"], (2, 5))       # partly or wholly under a closed lake
    assert np.all(into <= 0) and not into[:, ~under_closed].any() and (into[:, under_closed] < 0).any()
    source = out.drivers["river_discharge"]["largest_source"]
    big = int(mouths[np.argmax(river[mouths])])
    assert basin[source[big]] == big                                              # the largest source of a river lies in its basin
    shed = f["runoff_annual"].astype(np.float64) * area
    assert shed[source[big]] >= shed[big]
    assert not out.notices


def test_a_hollow_in_a_dry_climate_holds_a_closed_lake_and_in_a_wet_one_a_lake_with_an_outlet():
    """The ring of two_bowls. In the dry case rain falls on the high ground only, as behind a range: it runs down into
    the two bowls, where the air takes far more than falls. Each bowl holds a lake that spreads until its surface
    loses what the streams bring: nothing leaves the ring. In the wet case rain exceeds the air's demand everywhere:
    flooding costs nothing, the bowls fill, join, and overflow through the notch."""
    m = get_mesh(5)
    ground, deep, shallow, notch = two_bowls(m)
    volume = (m.area * R * R)[ground < -1000].sum() * 2500.0
    high = ground > 1300.0
    hh, area, sea, d, out, reads = watered(ground, volume, np.where(high, 150.0, 5.0), 25.0, 350.0, level=5)
    f, lakes, t = out.fields, out.tables["lakes"], d.tables["hollows"]
    wet = sea.fields["ocean_mask"]
    label = d.fields["depression_id"]
    inside = label > 0
    assert len(lakes["hollow"]) == 2 and set(lakes["hollow"]) == {1, 2} and not lakes["overflows"].any()
    assert np.allclose(lakes["inflow_m3_per_year"], lakes["loss_to_air_m3_per_year"], rtol=1e-9) and not lakes["outflow_m3_per_year"].any()
    assert np.all(lakes["level_m"] < t["spill_m"][lakes["hollow"]]) and np.all(lakes["area_m2"] > 0) and np.all(lakes["volume_m3"] > 0)
    assert np.all(lakes["outlet_cell"] == -1) and np.all(lakes["spills_into_cell"] == -1)
    fell = reads["precipitation"].sum(axis=0)
    to_air = f["evapotranspiration"].astype(np.float64).sum(axis=0)
    assert abs(((fell - to_air) * area)[inside].sum()) < 1e-6 * (fell * area)[inside].sum()        # all that falls inside goes back to the air
    for row in range(2):
        k = lakes["hollow"][row]
        mine = label == k
        share = f["lake_fraction"].astype(np.float64)
        dry_loss = 5.0 * 12                                                         # dry, the floor gives the air its 5 mm of rain a month
        extra = ((to_air - dry_loss) * area / 1000.0)[mine & (share > 0)].sum()      # what the flooded cells give beyond that
        assert np.isclose(extra, lakes["inflow_m3_per_year"][row], rtol=1e-4)       # the lake's extra loss is what the streams bring
        covered = mine & (share == 1)
        water_asks = to_air[covered] / 12.0                                         # open water gives the air all it asks
        ground_asks = f["potential_evapotranspiration"][0, covered].astype(np.float64)
        assert covered.sum() > 5 and np.all(water_asks > 1.1 * ground_asks) and np.all(water_asks < 1.3 * ground_asks)      # and dark water is asked for more
        assert np.isclose((share * area)[mine].sum(), lakes["area_m2"][row], rtol=1e-6)
        part = mine & (share > 0) & (share < 1)
        assert part.sum() == 1 and np.all(ground[mine & (share == 1)] < ground[part]) and np.all(ground[mine & (share == 0)] > ground[part])
        assert abs(lakes["level_m"][row] - ground[part][0]) < 1e-2
    state = out.drivers["lake_fraction"]["state"]
    assert set(state[f["lake_fraction"] > 0]) == {2} and set(state[f["lake_fraction"] == 0]) == {0}
    beyond = t["spill_into_cell"][3]
    assert out.drivers["river_discharge"]["largest_source"][beyond] not in np.flatnonzero(inside)      # nothing from inside passes the notch
    # what the fields hold under and beside a closed lake
    share = f["lake_fraction"].astype(np.float64)
    whole, part, dry = share == 1, (share > 0) & (share < 1), (share == 0) & ~wet
    assert not f["runoff"][:, whole].any() and np.allclose(f["soil_moisture"][:, whole], 1.0)        # under water: no runoff, ground full
    parts = out.drivers["evapotranspiration"]
    assert not parts["from_soil_and_plants"][:, whole].any() and np.all(parts["from_lake"][:, whole] > 0)
    assert not parts["from_lake"][:, dry].any() and np.all(parts["from_soil_and_plants"][:, dry] > 0)
    assert np.all(parts["from_lake"][:, part] > 0) and np.all(parts["from_soil_and_plants"][:, part] > 0)
    dry_soil = f["soil_moisture"][:, dry & inside & ~high].astype(np.float64)
    assert dry_soil.max() < 0.2                                                   # the floor of the bowls is dry ground
    for c in np.flatnonzero(part):                                                # a cell partly under water: its dry part as dry as
        assert np.allclose(f["soil_moisture"][:, c], share[c] + (1 - share[c]) * dry_soil.mean(axis=1), atol=0.02)      # the ground around
    cover = out.drivers["runoff"]["cover"]
    assert set(cover[whole]) == {2} and set(cover[part]) == {1} and set(cover[dry]) == {0} and set(cover[wet]) == {3}
    assert np.array_equal(out.drivers["soil_moisture"]["cover"], cover) and np.array_equal(parts["cover"], cover)
    assert np.array_equal(lakes["bottom_cell"], t["bottom_cell"][lakes["hollow"]])
    assert np.all(share[lakes["bottom_cell"]] == 1.0)
    river = f["river_discharge"].astype(np.float64)
    place = out.drivers["river_discharge"]["place"]
    assert set(place[whole]) == {5} and set(place[part]) == {2} and set(place[dry]) == {0} and set(place[wet]) == {3}
    assert not river[:, whole].any() and np.all(river[:, part].sum(axis=0) > 0)   # no river under a closed lake; one reaches its shore
    assert not out.drivers["river_discharge"]["through_lake"].any()
    # the books of each lake in the terms of a map: what the streams and its own shores bring is what its open water
    # gives the air less the rain that falls on it
    fell_on = lakes["rain_on_lake_m3_per_year"]
    gave = lakes["evaporation_m3_per_year"]
    for row in range(2):
        mine = (label == lakes["hollow"][row]) & (share > 0)
        assert np.isclose(fell_on[row], (share * area * 5.0 * 12 / 1000.0)[mine].sum(), rtol=1e-6)
        assert np.isclose(gave[row], (share * area * to_air / 1000.0)[mine & whole].sum()
                          + (out.drivers["evapotranspiration"]["from_lake"].astype(np.float64).sum(axis=0) * area / 1000.0)[mine & part].sum(), rtol=1e-4)
        from_land = (f["runoff_annual"].astype(np.float64) * area / 1000.0)[label == lakes["hollow"][row]].sum()
        assert from_land > 0 and np.isclose(from_land, gave[row] - fell_on[row], rtol=1e-4)
    assert not lakes["left_over_m3_per_year"].any()
    # the wet case
    hh, area, sea, d, out, reads = watered(ground, volume, 150.0, 25.0, 350.0, level=5)
    f, lakes = out.fields, out.tables["lakes"]
    assert list(lakes["hollow"]) == [3] and lakes["overflows"][0] and lakes["level_m"][0] == t["spill_m"][3]
    assert lakes["outlet_cell"][0] == t["spill_from_cell"][3] and lakes["spills_into_cell"][0] == beyond
    assert np.isclose(lakes["area_m2"][0], t["area_when_full_m2"][3], rtol=1e-6) and np.isclose(lakes["volume_m3"][0], t["volume_when_full_m3"][3], rtol=1e-4)
    # dark water gives the air more than the wet ground it covers did: a loss, but a small one beside what arrives
    assert 0.02 < lakes["loss_to_air_m3_per_year"][0] / lakes["inflow_m3_per_year"][0] < 0.5
    assert np.isclose(lakes["outflow_m3_per_year"][0], lakes["inflow_m3_per_year"][0] - lakes["loss_to_air_m3_per_year"][0], rtol=1e-9)
    river = f["river_discharge"].astype(np.float64).sum(axis=0) * MONTH_S
    assert river[beyond] >= lakes["outflow_m3_per_year"][0] * (1 - 1e-6)
    assert set(out.drivers["lake_fraction"]["state"][f["lake_fraction"] > 0]) == {1}
    # the river runs through the lake: at its outlet cell it carries the lake's outflow, and inside the lake the flow
    # never exceeds that; the parts recorded for the answers say "through the lake" there and nothing else
    outlet = lakes["outlet_cell"][0]
    assert np.isclose(river[outlet], lakes["outflow_m3_per_year"][0], rtol=1e-5)
    place = out.drivers["river_discharge"]["place"]
    in_lake, at_brim = place == 1, place == 4
    crossed = in_lake | at_brim                                                   # the cells that the lake's water crosses
    # the outlet cell stands exactly at the level of the lake: the lake covers none of it, and it is said to be at the
    # brim, not in the lake [the fourth check of step 2 found it said to lie in the lake and to be reached by no lake]
    assert at_brim[outlet] and not f["lake_fraction"][at_brim].any() and np.all(f["lake_fraction"][in_lake] > 0)
    assert np.all(f["lake_fraction"][in_lake & (ground < t["spill_m"][3])] == 1.0)
    assert np.all(river[crossed] <= river[outlet] * (1 + 1e-6)) and (river[in_lake] > 0).sum() > 10
    through = out.drivers["river_discharge"]["through_lake"].astype(np.float64).sum(axis=0) * MONTH_S
    assert np.allclose(through[crossed], river[crossed], rtol=1e-5) and not through[~crossed].any()
    assert not out.drivers["river_discharge"]["local_runoff"][:, crossed].any()
    assert set(out.drivers["river_discharge"]["lake"][crossed]) == {0}            # the row of the lake in the table of lakes
    assert set(out.drivers["lake_fraction"]["state"][at_brim]) == {4} and set(out.drivers["lake_fraction"]["lake"][at_brim]) == {0}
    months = f["river_discharge"].astype(np.float64)[:, outlet]
    assert np.allclose(months, months.mean(), rtol=1e-5)                          # even rain in, even flow out
    fell = reads["precipitation"].sum(axis=0)
    to_air = f["evapotranspiration"].astype(np.float64).sum(axis=0)
    assert np.isclose(river[wet].sum(), ((fell - to_air) * area / 1000.0)[~wet].sum(), rtol=1e-5)
    # asked why the river below the notch is so large, the walk goes through the lake to the wettest ground behind it
    assert inside[out.drivers["river_discharge"]["largest_source"][beyond]]


def test_snow_holds_the_winter_back_and_the_thaw_sends_it_down_the_rivers():
    """Six months at -5 C in which 40 mm fall as snow each, then six months at +8 C with 40 mm of rain each. Through
    the winter nothing runs off and the store grows to 240 mm. The first warm month could melt 974 mm: all 240 mm melt
    in it, on top of that month's rain, and the soil, which holds 150 mm, sheds most of it."""
    m = get_mesh(4)
    ground, away = cone(m)
    celsius = np.array([-5.0] * 6 + [8.0] * 6)
    sun = np.array([40.0] * 6 + [330.0] * 6)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, 40.0, celsius, sun,
                                           snowfall=np.array([40.0] * 6 + [0.0] * 6))
    f = out.fields
    land = np.flatnonzero(~sea.fields["ocean_mask"])
    thaw = 4.0 * MONTH_DAYS * 8.0                                                 # 974 mm: the 240 mm are gone after a quarter of the month
    assert np.allclose(f["snow_water"][:, land], np.array([20, 60, 100, 140, 180, 220, 120 * 240 / thaw, 0, 0, 0, 0, 0.0])[:, None])
    # the share of the ground under snow: 15 mm lie after 0.375 of the first month; in the thaw the ground is white
    # until 225 mm have gone, and half white, on average, while the last 15 mm go
    cover = np.array([0.375 * 0.5 + 0.625, 1, 1, 1, 1, 1, (225 + 7.5) / thaw, 0, 0, 0, 0, 0.0])
    assert np.allclose(f["snow_cover"][:, land], cover[:, None], atol=1e-6)
    demand = f["potential_evapotranspiration"].astype(np.float64)[:, land]
    assert not demand[:6].any()                                                   # ground under snow gives the air nothing
    assert np.all(demand[7:] > 50.0)
    # the month of the thaw has the sun and the warmth of the months after it, and bare ground for 0.76 of its days
    assert np.allclose(demand[6] / demand[7], 1 - cover[6], rtol=1e-5) and abs(1 - cover[6] - 0.761) < 0.001
    bare = out.drivers["potential_evapotranspiration"]["snow_free"][:, land]
    assert np.allclose(bare, 1 - cover[:, None], atol=1e-6)
    assert set(out.drivers["potential_evapotranspiration"]["state"][land]) == {1} and set(out.drivers["snow_water"]["state"][land]) == {1}
    runoff = f["runoff"].astype(np.float64)[:, land]
    assert not runoff[:6].any() and np.all(runoff[6] > 100.0) and np.all(runoff[6] > 5 * runoff[7:].max(axis=0))
    parts = out.drivers["runoff"]
    assert np.allclose(parts["from_snowmelt"][6, land] / runoff[6], 240.0 / 280.0, atol=1e-3)         # melt against rain, in the month's shares
    assert not parts["from_ice"].any() and not parts["from_snowmelt"][7:].any()
    river = f["river_discharge"].astype(np.float64)
    mouth = int(d.fields["basin_id"][land[0]])
    assert river[6, mouth] > 5 * river[7:, mouth].max() and not river[:6].any()


def test_where_snow_never_melts_the_excess_leaves_as_ice_down_the_same_paths():
    m = get_mesh(4)
    ground, away = cone(m)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, 20.0, -10.0, 100.0, snowfall=20.0)
    f = out.fields
    wet = sea.fields["ocean_mask"]
    land = ~wet
    assert np.allclose(f["snow_water"][:, land], 240.0)                           # one year of what falls: older snow counts as ice
    assert np.allclose(f["runoff"][:, land], 20.0) and np.allclose(out.drivers["runoff"]["from_ice"][:, land], 20.0)
    assert not f["evapotranspiration"].any() and not f["potential_evapotranspiration"][:, land].any()
    assert np.allclose(f["soil_moisture"][:, land], 0.0)                          # no liquid water ever reaches the soil
    assert np.isclose(f["river_discharge"][0, wet].sum(), (20.0 * area[land] / 1000.0).sum() / MONTH_S, rtol=1e-5)


def test_a_month_just_above_freezing_melts_four_millimetres_a_day_for_each_degree():
    """The degree-day factor as the parameter file ships it, through the process: six months at -5 C with 100 mm of
    snow each, then months at +1 C. Each of those can melt 4 mm a day for the one degree, 121.75 mm a month: the
    600 mm take five months to go, and the store at the end of each is 478.25, 356.5, 234.75, 113 and 0 mm. With
    half the factor the snow would never go at all."""
    m = get_mesh(4)
    ground, away = cone(m)
    celsius = np.array([-5.0] * 6 + [1.0] * 6)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, np.array([100.0] * 6 + [0.0] * 6),
                                           celsius, 200.0, snowfall=np.array([100.0] * 6 + [0.0] * 6))
    f = out.fields
    land = np.flatnonzero(~sea.fields["ocean_mask"])
    melt = 4.0 * MONTH_DAYS * (float(np.float32(274.15)) - 273.15)                # (the temperature is stored in single precision)
    assert abs(melt - 121.75) < 0.01
    ends = np.array([100, 200, 300, 400, 500, 600, 600 - melt, 600 - 2 * melt, 600 - 3 * melt, 600 - 4 * melt, 0.0, 0.0])
    starts = np.roll(ends, 1)
    means = 0.5 * (starts + ends)
    rest = 600 - 4 * melt                                                         # 113 mm, gone after 113 / 121.75 of the eleventh month
    means[10] = 0.5 * rest * rest / melt
    assert np.allclose(f["snow_water"][:, land], means[:, None], rtol=1e-5)
    melted = out.drivers["snow_water"]["melted"].astype(np.float64)[:, land]
    assert np.allclose(melted, np.array([0] * 6 + [melt] * 4 + [rest, 0])[:, None], rtol=1e-5)
    assert set(out.drivers["snow_water"]["state"][land]) == {1} and not out.drivers["snow_water"]["left_as_ice"].any()
    assert np.allclose(out.drivers["snow_water"]["fell"][:, land], reads["snowfall"][:, land])


def test_snowfall_is_never_more_than_the_precipitation_it_is_part_of():
    """The two fields come from another process and are stored rounded. Snow that outweighs the precipitation of its
    month would make rain negative."""
    m = get_mesh(4)
    ground, away = cone(m)
    hh, area, sea, d, out, reads = watered(ground, (m.area * R * R)[away > 60].sum() * 400.0, 20.0, -10.0, 100.0, snowfall=25.0)
    land = ~sea.fields["ocean_mask"]
    assert np.allclose(out.drivers["snow_water"]["fell"][:, land], 20.0)
    assert np.allclose(out.fields["runoff"][:, land], 20.0)                       # what falls leaves as ice, and no more than falls


def test_a_hollow_with_no_way_out_that_gets_more_than_it_can_lose_is_flooded_whole_and_said_to_be():
    """A planet without sea under heavy rain: the one hollow fills to its rim. It has no pass to overflow at, so it is
    no lake with an outlet. The table says what cannot be lost, and the process says that it drops it."""
    m = get_mesh(3)
    ground = rough_ground(m, 71, relief=800.0, bumps=5.0)
    hh, area, sea, d, out, reads = watered(ground, 0.0, 200.0, 20.0, level=3)
    f, lakes = out.fields, out.tables["lakes"]
    assert len(lakes["hollow"]) == 1 and not lakes["overflows"][0] and lakes["outflow_m3_per_year"][0] == 0
    assert lakes["outlet_cell"][0] == -1 and lakes["spills_into_cell"][0] == -1
    spare = ((200.0 * 12 - f["evapotranspiration"].astype(np.float64).sum(axis=0)) * area / 1000.0).sum()
    assert np.isclose(lakes["left_over_m3_per_year"][0], spare, rtol=1e-4) and spare > 0
    assert np.isclose(lakes["inflow_m3_per_year"][0], lakes["loss_to_air_m3_per_year"][0] + lakes["left_over_m3_per_year"][0], rtol=1e-9)
    assert np.all(f["lake_fraction"] == 1.0)
    top = float(ground.astype(np.float32).max())
    assert np.isclose(lakes["level_m"][0], top) and np.allclose(f["lake_level"], top)       # it stands at its highest ground
    assert np.isclose(lakes["area_m2"][0], area.sum(), rtol=1e-6)
    assert np.isclose(lakes["volume_m3"][0], ((top - ground.astype(np.float32).astype(np.float64)) * area).sum(), rtol=1e-4)
    assert set(out.drivers["lake_fraction"]["state"]) == {3} and not f["river_discharge"].any()
    assert set(out.drivers["river_discharge"]["place"]) == {5}                  # wholly under a lake that keeps its water


def test_a_soil_that_holds_more_carries_more_water_into_the_dry_season():
    """Six wet months and six rainless ones. In the dry season the air gets what the soil still holds, so a soil of
    300 mm gives it more than one of 150 mm, and sheds less in the wet season. Without a capacity from Soils the
    process reads the default of the field, 150 mm."""
    m = get_mesh(4)
    ground, away = cone(m)
    volume = (m.area * R * R)[away > 60].sum() * 400.0
    rain = np.array([200.0] * 6 + [0.0] * 6)
    runs = {}
    for name, capacity in (("default", None), ("150", 150.0), ("300", 300.0)):
        hh, area, sea, d, out, reads = watered(ground, volume, rain, 20.0, capacity=capacity)
        land = ~sea.fields["ocean_mask"]
        cell = int(np.flatnonzero(land & (sea.fields["height_above_sea"] < 30.0))[0])
        runs[name] = {k: out.fields[k].astype(np.float64)[..., cell] for k in ("evapotranspiration", "runoff", "potential_evapotranspiration", "soil_moisture")}
    assert np.array_equal(runs["default"]["evapotranspiration"], runs["150"]["evapotranspiration"])
    demand = runs["150"]["potential_evapotranspiration"][0]
    for name, capacity in (("150", 150.0), ("300", 300.0)):
        critical = 0.75 * capacity
        full_demand_months = (capacity - critical) / demand                       # the dry season begins with a full soil
        left = critical * np.exp(-demand * (6 - full_demand_months) / critical)
        dry = runs[name]["evapotranspiration"][6:].sum()
        assert np.isclose(dry, capacity - left, rtol=1e-4)
        assert np.isclose(runs[name]["evapotranspiration"].sum() + runs[name]["runoff"].sum(), 1200.0, rtol=1e-5)
    assert runs["300"]["evapotranspiration"][6:].sum() > runs["150"]["evapotranspiration"][6:].sum() + 100.0
    assert runs["300"]["runoff"].sum() < runs["150"]["runoff"].sum() - 80.0


def test_hydrology_says_so_when_the_soil_has_not_settled_or_water_has_nowhere_to_go():
    m = get_mesh(3)
    ground = rough_ground(m, 71, relief=800.0, bumps=5.0)
    # a planet without sea, on which more rain falls than the air can take: the one hollow fills and has no way out
    hh, area, sea, d, out, reads = watered(ground, 0.0, 200.0, 20.0, level=3)
    notes = [n for n in out.notices if n["kind"] == "process_note"]
    assert len(notes) == 1 and "no way out" in notes[0]["what"]
    spare = ((200.0 * 12 - out.fields["evapotranspiration"].astype(np.float64).sum(axis=0)) * area / 1000.0).sum()
    assert np.isclose(notes[0]["dropped_m3_per_year"], spare, rtol=1e-4)
    assert np.all(out.fields["lake_fraction"] == 1.0) and len(out.tables["lakes"]["hollow"]) == 1
    # a year the bucket is not given time to repeat
    rain = np.array([30.0] * 3 + [0.0] * 9)
    hh, area, sea, d, out, reads = watered(ground, 0.0, rain, 20.0, sunlight=np.array([200.0] * 12), level=3,
                                           constants={"soil": {"years_most": 1}})
    notes = [n for n in out.notices if n["kind"] == "process_note"]
    assert len(notes) == 1 and "still changing" in notes[0]["what"] and notes[0]["years_followed"] == 1


def test_until_soils_exist_every_soil_holds_the_bucket_of_manabe():
    hh = Harness(level=3)
    sea = hh.mesh.lat < 0
    out = hh.run("Soils", reads={"ocean_mask": sea})
    assert np.all(out.fields["soil_water_capacity"][~sea] == 150.0) and not out.fields["soil_water_capacity"][sea].any()
    assert hh.registry.fields["soil_water_capacity"].default == 150.0             # what Hydrology reads in the first round
