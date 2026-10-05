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


def check_hollows(mesh, surface, sea, area):
    """The table of hollows against its definition, worked out the slow way: for each hollow, the lowest pass that
    leads out of it, and the lake that fills it to that pass."""
    recv = dr.receivers(surface, sea, mesh.nbr)
    stack = dr.flow_stack(recv)
    label, table = dr.hollows(surface, sea, recv, stack, mesh.edge_cells, area)
    a, b = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    pass_height = np.maximum(surface[a], surface[b])
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
    recv, stack, label, table = check_hollows(m, surface, sea, area)
    merged = table["first_child"] >= 0
    assert (~merged[1:]).sum() >= 100 and merged.sum() >= 20                 # many hollows, many of them inside larger ones
    assert (table["parent"][merged] >= 0).any()                              # and some of those inside larger ones again
    # with every hollow full, each cell has one way to the sea
    full = dr.overflow_receivers(recv, sea, table)
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
    full = dr.overflow_receivers(recv, sea, table)
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
        if recv[mouth] >= 0:
            assert wet[recv[mouth]]                                          # a mouth hands its water to the sea
        else:                                                                # or it is the deepest cell of a hollow that overflows into the sea
            hollow = tops[f["depression_id"][mouth]]
            assert t["bottom_cell"][hollow] == mouth and wet[t["spill_into_cell"][hollow]]
            assert np.all(f["basin_id"][np.isin(f["depression_id"], region_of(t, hollow))] == mouth)     # one basin for the whole hollow
            by_lake += 1
    assert by_lake == (0 if seed == 21 else 1)                               # two of the three grounds hold a hollow on the coast


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


def test_turning_the_planet_turns_the_drainage_with_it():
    m = get_mesh(4)
    turn = np.deg2rad(72.0)
    rz = np.array([[np.cos(turn), -np.sin(turn), 0.0], [np.sin(turn), np.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    goes_to = np.argmax(m.xyz @ rz.T @ m.xyz.T, axis=1)
    assert len(set(goes_to)) == m.n
    ground = rough_ground(m, 41)
    turned_ground = np.empty_like(ground)
    turned_ground[goes_to] = ground
    area = m.area * R * R
    volume = area[ground < 0].sum() * 1000.0
    _, _, _, plain = drained(ground, volume)
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
    assert (p["depression_id"] > 0).any()
    assert np.array_equal(bottom_t[t["depression_id"][goes_to]], lands(bottom_p[p["depression_id"]]))


# ------------------------------------------------------------------------------------------ snow (library)
from worldengine.library import evaporation as ev                       # noqa: E402
from worldengine.library import lakes as lk                             # noqa: E402
from worldengine.library.snow import degree_day_melt, snow_year         # noqa: E402
from worldengine.library.soil_water import bucket_month, bucket_repeating, bucket_year    # noqa: E402

YEAR_S = 31558150.0
MONTH_S = YEAR_S / 12
MONTH_DAYS = MONTH_S / 86400.0


def column(values):
    """Twelve monthly values as one cell's column."""
    return np.asarray(values, dtype=np.float64).reshape(12, 1)


def test_the_snow_of_a_year_that_melts_it_all_followed_by_hand():
    """Six months at -5 C with 10 mm of snowfall each, then six months at +5 C without. At the end of the cold months
    the store holds 10, 20 ... 60 mm. A month at +5 C can melt 4 mm a day per degree times 30.44 days times 5 degrees
    = 609 mm, so the first warm month empties the store. The mean store of a month is the average of its start and its
    end: 5, 15, 25, 35, 45, 55, then 30, then nothing."""
    temperature = column(273.15 + np.array([-5.0] * 6 + [5.0] * 6))
    could_melt = degree_day_melt(temperature, 273.15, 4.0, MONTH_DAYS)
    assert np.allclose(could_melt[6:], 608.8, atol=0.1) and np.all(could_melt[:6] == 0)
    store, melted, left = snow_year(column([10.0] * 6 + [0.0] * 6), could_melt, 1.0)
    assert np.allclose(store[:, 0], [5, 15, 25, 35, 45, 55, 30, 0, 0, 0, 0, 0])
    assert np.allclose(melted[:, 0], [0] * 6 + [60] + [0] * 5) and not left.any()
    # Deep snow outlasts the thaw: 600 mm against 243.5 mm of melt a month at +2 C is gone in the third warm month.
    late = degree_day_melt(column(273.15 + np.array([-5.0] * 6 + [2.0] * 6)), 273.15, 4.0, MONTH_DAYS)
    store, melted, left = snow_year(column([100.0] * 6 + [0.0] * 6), late, 1.0)
    thaw = 4.0 * MONTH_DAYS * 2.0
    assert np.allclose(store[6:, 0], [600 - thaw / 2, 600 - 1.5 * thaw, (600 - 2 * thaw) / 2, 0, 0, 0])
    assert np.isclose(melted.sum(), 600.0) and not left.any()
    # No snowfall, no snow, however cold.
    store, melted, left = snow_year(column([0.0] * 12), column([0.0] * 12), 1.0)
    assert not store.any() and not melted.any() and not left.any()


def test_the_snow_year_is_the_one_that_years_followed_from_bare_ground_come_to():
    """A year that begins in its warm season starts with the snow of the last cold season on the ground."""
    rng = np.random.default_rng(3)
    snowfall = rng.random((12, 200)) * 40.0
    melt = rng.random((12, 200)) * 150.0 * (rng.random((12, 200)) < 0.4)          # some months melt, most do not
    melt[:, snowfall.sum(axis=0) >= melt.sum(axis=0)] *= 3.0                      # keep to years that melt all their snow
    seasonal = snowfall.sum(axis=0) < melt.sum(axis=0)
    assert seasonal.sum() > 100
    store, melted, left = snow_year(snowfall, melt, 1.0)
    on_ground = np.zeros(200)
    for _ in range(5):                                                            # the plain rule, year after year
        means = np.zeros((12, 200))
        for m in range(12):
            after = np.maximum(on_ground + snowfall[m] - melt[m], 0.0)
            means[m] = 0.5 * (on_ground + after)
            on_ground = after
    assert np.allclose(store[:, seasonal], means[:, seasonal], atol=1e-9)
    assert np.allclose(melted.sum(axis=0)[seasonal], snowfall.sum(axis=0)[seasonal])       # all that fell has melted
    assert not left[:, seasonal].any()


def test_where_more_snow_falls_than_melts_the_excess_leaves_as_ice_and_the_store_holds_a_set_number_of_years():
    """30 mm of snowfall every month, and three summer months that could melt 100 mm each. The year gains 60 mm.
    That much leaves as ice, 5 mm a month, and at the end of summer the store holds one year's gain. By hand the store
    at the end of each month is 185, 210, 235, 260, 285, 210, 135, 60, 85, 110, 135, 160."""
    snowfall = column([30.0] * 12)
    melt = column([0.0] * 5 + [100.0] * 3 + [0.0] * 4)
    store, melted, left = snow_year(snowfall, melt, 1.0)
    ends = np.array([185, 210, 235, 260, 285, 210, 135, 60, 85, 110, 135, 160.0])
    starts = np.roll(ends, 1)
    assert np.allclose(store[:, 0], 0.5 * (starts + ends))
    assert np.allclose(melted, melt) and np.allclose(left, 5.0)
    assert np.isclose(snowfall.sum(), melted.sum() + left.sum())                  # what falls melts or leaves as ice
    deeper, melted5, left5 = snow_year(snowfall, melt, 5.0)                       # five years' gain kept: only the store changes
    assert np.allclose(deeper - store, 4 * 60.0) and np.array_equal(melted5, melted) and np.array_equal(left5, left)
    # Land that never thaws keeps a year of what falls: 2 mm a month makes 24 mm, white ground all year.
    store, melted, left = snow_year(column([2.0] * 12), column([0.0] * 12), 1.0)
    assert np.allclose(store, 24.0) and np.allclose(left, 2.0) and not melted.any()


def test_the_snow_store_does_not_jump_where_a_year_tips_from_losing_its_snow_to_keeping_it():
    """A limit on the depth of the store made it jump by the whole limit when the year's gain crossed zero; one cell
    tipping kept the climate rounds from settling. With snow leaving by age, the two cases meet."""
    snowfall = column([30.0] * 12)
    stores, ice = [], []
    for gain in (-1e-6, 0.0, 1e-6):
        melt = column([0.0] * 5 + [(360.0 - gain) / 3] * 3 + [0.0] * 4)
        store, melted, left = snow_year(snowfall, melt, 1.0)
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
    kinds = [(store >= critical) & (end < critical), (store < critical) & (end >= critical) & (critical > 0), shed > 0, demand == 0]
    assert all(k.sum() >= 5 for k in kinds)                                       # every passage occurs in the sample


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
    assert settled.mean() > 0.97                                                  # (cells that settle over centuries are within the tolerance of the balance, not of the store)
    assert np.abs(shed_plain.sum(axis=0) - shed.sum(axis=0)).max() < 0.02


# ------------------------------------------------------------------------------------------ the demand for water (library)
def demand_constants():
    return Harness(level=2).params["models"]["slots"]["Hydrology"]["constants"]["demand"]


def test_the_numbers_of_the_priestley_taylor_rule_at_twenty_degrees_are_the_textbook_ones():
    d = demand_constants()
    t = np.array([20.0])
    assert abs(ev.saturation_slope(t, d["vapour"])[0] - 144.7) < 0.3              # Pa/K: 0.1447 kPa/K in the usual tables
    assert abs(ev.latent_heat(t, d["heat"])[0] / 2.45e6 - 1) < 0.005              # J/kg: 2.45 MJ/kg
    sea_level = ev.air_pressure(np.array([0.0]), 9.80665, d["air"])
    assert sea_level[0] == 101325.0
    assert abs(ev.air_pressure(np.array([5000.0]), 9.80665, d["air"])[0] / 54020.0 - 1) < 0.002     # the standard atmosphere at 5 km
    g = ev.psychrometric(sea_level, ev.latent_heat(t, d["heat"]), d["air"])[0]
    assert abs(g - 66.7) < 0.6                                                    # Pa/K
    share = lambda c: (lambda s, gg: s / (s + gg))(ev.saturation_slope(np.array([c]), d["vapour"])[0],
                                                   ev.psychrometric(sea_level, ev.latent_heat(np.array([c]), d["heat"]), d["air"])[0])
    assert abs(share(0.0) - 0.40) < 0.01 and abs(share(30.0) - 0.78) < 0.01       # the share of the energy that evaporates water
    # the one share of sunshine returns the two means of Earth's surface (Trenberth, Fasullo and Kiehl 2009, at second hand):
    sun = d["sunshine_fraction"]
    assert abs(ev.net_longwave(np.array([15.0]), sun, d["longwave"])[0] - 63.0) < 1.5         # W/m2 lost: 396 up less 333 back
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
    discharge, found = lk.lake_flows(table, label, recv, stack, runoff, moved["extra"], moved["overflows"])
    by_row = {int(r): {k: v[i] for k, v in found.items()} for i, r in enumerate(found["row"])}
    return dict(recv=recv, stack=stack, label=label, table=table, own=own, inflow=inflow, room=room, moved=moved, share=share,
                level=level, lake=lake, discharge=discharge, found=found, by_row=by_row, leaves=leaves)


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
    assert np.allclose(r["discharge"][:, bw["bottom_a"]], [0.35 * ra, 0.15 * ra])


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
    beyond = t["spill_into_cell"][a]
    assert np.allclose(r["discharge"][:, beyond], [0.35 * rb, 0.15 * rb])            # each month the lake passes on the same share
    assert np.allclose(r["discharge"][:, bw["bottom_b"]], [0.35 * rb, 0.15 * rb])    # ... and it runs down to the other bottom
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
    assert np.allclose(r["discharge"][:, bottoms[2]], np.array([0.7, 0.3]) * 1.3 * r2)
    assert np.allclose(r["discharge"][:, t["spill_into_cell"][2]], np.array([0.7, 0.3]) * 0.3 * r2)
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
    assert over.any() and (~f["overflows"]).any() if wetness == 0.3 else True


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
    heat = 1.91846e6 * ((celsius + 273.15) / (celsius + 273.15 - 33.912)) ** 2
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
    assert dr_["river_discharge"]["largest_source"][top] == top and not dr_["river_discharge"]["from_upstream"][:, top].any()


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
    # every basin: rain less evaporation leaves the land. A plain river leaves through its mouth. A hollow that
    # overflows straight into the sea is named after its deepest cell, and what leaves is the outflow of its lake.
    recv, t = d.fields["flow_receiver"], d.tables["hollows"]
    tops = dr.top_hollows(t)
    outflow = dict(zip(lakes["hollow"].tolist(), lakes["outflow_m3_per_year"].tolist()))
    leaves_land = np.array([river[mo] if recv[mo] >= 0 else outflow.get(int(tops[d.fields["depression_id"][mo]]), 0.0) for mo in mouths])
    # The books close to within what the bucket allows a year to differ from the next (0.01 mm) and the rounding of
    # the stored fields (a few millionths of the rain).
    slack = np.bincount(basin[land], weights=((0.02 + 5e-6 * fell) * area / 1000.0)[land], minlength=m.n)[mouths]
    assert np.all(np.abs(leaves_land - kept) <= slack)
    assert (recv[mouths] < 0).any()                                               # the case holds a hollow on the coast
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
    assert np.array_equal(which >= 0, flooded)
    assert np.allclose(f["lake_level"][flooded], lakes["level_m"][which[flooded]], atol=1e-2)
    assert np.all(ground[flooded] <= f["lake_level"][flooded] + 1e-2)             # no flooded ground stands above its lake
    full = f["lake_fraction"] == 1.0
    strong = demand[:, full] > 80.0                          # open water gives the air all it asks, and it asks more of dark water:
    ratio = f["evapotranspiration"][:, full][strong] / demand[:, full][strong]       # by 0.93 / 0.83 in sunlight absorbed, and by
    assert full.any() and strong.sum() > 100 and ratio.min() > 1.12 and ratio.max() < 1.3  # more in energy left after the heat radiated away
    assert np.all(f["evapotranspiration"][:, full] >= demand[:, full] * (1 - 1e-5))
    # the parts recorded for the "why" answers add up
    for name in ("runoff", "river_discharge", "evapotranspiration"):
        total = sum(v.astype(np.float64) for v in out.drivers[name].values() if v.dtype.kind == "f")
        value = f[name].astype(np.float64)
        assert np.allclose(total, value, rtol=1e-4, atol=1e-6 * np.abs(value).max())
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
    assert np.allclose(f["snow_water"][:, land], np.array([20, 60, 100, 140, 180, 220, 120, 0, 0, 0, 0, 0.0])[:, None])
    assert not f["potential_evapotranspiration"][:7, land].any()                  # ground under snow gives the air nothing
    assert np.all(f["potential_evapotranspiration"][7:, land] > 50.0)
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
