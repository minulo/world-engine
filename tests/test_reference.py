"""The Earth reference tooling: the mapping of grids onto the mesh, the readers, the fetch tool, the relief file.

None of this is part of the engine; the Earth tests and the Earth twin stand on it. The tests of the mapping and of
the fetch tool need no data and always run. The tests of the readers need the reference files and are skipped
without them. Facts about Earth used to check a reader (which month is wettest where, where the highest ground
lies) are from memory [UNVERIFIED] unless the test says where they come from; each is of a kind that a reader which
is wrong by a month, a row or a column would break.
"""
import functools
import hashlib
import http.server
import importlib.util
import shutil
import threading

import numpy as np
import pytest
import yaml

import earth_reference as ref
from conftest import DATA, ROOT
from worldengine.engine import Engine
from worldengine.mesh import get_mesh
from worldengine.params import ParameterError

needs_data = pytest.mark.skipif(not ref.available(), reason="the Earth reference data is not here: run python tools/fetch_reference_data.py")


def grid(step):
    """A latitude-longitude grid of the given step in degrees, laid out as the files are: from north to south, and
    eastward from 0 degrees."""
    lat = 90.0 - step / 2 - step * np.arange(int(round(180 / step)))
    lon = step / 2 + step * np.arange(int(round(360 / step)))
    return lat, lon


# ---------------------------------------------------------------------------------------------- grids onto the mesh
def test_a_grid_is_put_in_order_whatever_order_its_file_has():
    lat, lon = grid(30.0)
    values = lat[:, None] * 1000.0 + lon[None, :]
    la, lo, v = ref._ordered(lat, lon, np.stack([values, 2 * values]))
    assert np.all(np.diff(la) > 0) and np.all(np.diff(lo) > 0) and lo.min() == -165.0 and lo.max() == 165.0
    for i in (0, 3, 5):
        for j in (0, 4, 11):
            east = lo[j] % 360.0
            assert v[0, i, j] == la[i] * 1000.0 + east and v[1, i, j] == 2 * v[0, i, j]


def test_the_mean_over_a_cell_weights_every_grid_point_by_the_area_it_stands_for():
    """Toward the poles the points of a latitude-longitude grid crowd together. Each stands for an area that shrinks
    with the cosine of its latitude; a plain mean would let the crowded side of a cell outvote the other."""
    m = get_mesh(3)
    lat, lon = grid(1.0)
    la, lo, values = ref._ordered(lat, lon, np.sin(np.deg2rad(lat))[:, None] ** 3 * np.ones((1, lon.size)) + 0.01 * lon[None, :])
    cells = ref.cell_of_every_point(m, la, lo)
    got = ref.cell_means(m, la, lo, values, cells)
    weight = (np.cos(np.deg2rad(la))[:, None] * np.ones((1, lo.size))).ravel()
    flat = values.ravel()
    plain = np.array([flat[cells == c].mean() for c in range(m.n)])
    weighted = np.array([(flat * weight)[cells == c].sum() / weight[cells == c].sum() for c in range(m.n)])
    assert np.allclose(got, weighted, rtol=1e-12)
    assert np.abs(plain - weighted).max() > 1e-3                                  # the two means differ, most near the poles
    # every point lies in the cell whose centre is nearest
    points = ref._points(la, lo)
    for k in (0, 777, 30000, 64799):
        assert cells[k] == int(np.argmax(m.xyz @ points[k]))
    # a cell that holds no grid point gets no value; missing values are left out of a mean
    coarse = ref.cell_means(get_mesh(4), *ref._ordered(*grid(30.0), np.ones((6, 12))))
    assert np.isnan(coarse).sum() > 2000 and np.all(coarse[np.isfinite(coarse)] == 1.0)
    holed = values.copy()
    holed[::2, :] = np.nan
    half = ref.cell_means(m, la, lo, holed, cells)
    rows = np.repeat(np.arange(la.size), lo.size)
    kept = np.array([(flat * weight)[(cells == c) & (rows % 2 == 1)].sum() / weight[(cells == c) & (rows % 2 == 1)].sum() for c in range(m.n)])
    assert np.allclose(half, kept, rtol=1e-12)


def test_the_low_value_of_a_cell_is_taken_among_its_points_that_have_a_value():
    """A land cell's valley floor is the height below which a tenth of its land points lie. Points without a value
    (the sea) used to be counted: on a cell half under the sea the tenth became a fifth of the land points."""
    m = get_mesh(3)
    lat, lon = grid(1.0)
    la, lo, _ = ref._ordered(lat, lon, np.zeros((lat.size, lon.size)))
    rng = np.random.default_rng(2)
    values = rng.random((la.size, lo.size)) * 1000.0
    values[rng.random(values.shape) < 0.5] = np.nan                               # half the points have no value
    values[:40, :] = np.nan                                                       # and none south of 50 S
    cells = ref.cell_of_every_point(m, la, lo)
    got = ref.cell_low_values(m, la, lo, values, 0.1, cells)
    flat = values.ravel()
    for c in range(m.n):
        mine = np.sort(flat[(cells == c) & np.isfinite(flat)])
        if mine.size == 0:
            assert np.isnan(got[c])
        else:
            assert got[c] == mine[min(int(0.1 * mine.size), mine.size - 1)]
    assert np.isnan(got).sum() > 20 and np.isfinite(got).sum() > 400
    assert np.array_equal(ref.cell_low_values(m, la, lo, values, 0.0, cells)[np.isfinite(got)],
                          np.array([np.nanmin(flat[cells == c]) for c in np.flatnonzero(np.isfinite(got))]))


def test_a_coarse_grid_is_read_between_the_four_points_around_each_cell_centre():
    m = get_mesh(4)
    lat, lon = grid(5.0)
    la, lo, _ = ref._ordered(lat, lon, np.zeros((lat.size, lon.size)))
    # a field that is a straight line in latitude and in longitude is returned exactly, away from the date line and
    # from the two rows nearest the poles
    plane = 3.0 * la[:, None] - 0.5 * lo[None, :] + 7.0
    got = ref.at_cell_centres(m, la, lo, plane)
    inside = (np.abs(m.lat) < 87.5) & (np.abs(m.lon) < 177.5)
    assert np.allclose(got[inside], (3.0 * m.lat - 0.5 * m.lon + 7.0)[inside], atol=1e-9)
    nearest = plane[np.abs(la[:, None] - m.lat[None, :]).argmin(axis=0), np.abs(lo[:, None] - m.lon[None, :]).argmin(axis=0)]
    assert np.abs(nearest - got)[inside].max() > 5.0                              # which the nearest grid point would not do
    # longitude wraps: a smooth field is smooth across the date line
    wave = np.cos(np.deg2rad(lo))[None, :] * np.cos(np.deg2rad(la))[:, None]
    off = np.abs(ref.at_cell_centres(m, la, lo, wave) - np.cos(np.deg2rad(m.lon)) * np.cos(np.deg2rad(m.lat)))
    beyond = np.abs(m.lon) > 177.5                                               # cells between the last column and the first
    assert beyond.sum() > 5 and off[np.abs(m.lat) < 87.5].max() < 0.005 and off[beyond & (np.abs(m.lat) < 87.5)].max() < 0.005
    # beyond the last row toward a pole, the last row is used
    rows = la[:, None] * np.ones((1, lo.size))
    at_poles = ref.at_cell_centres(m, la, lo, rows)
    assert at_poles[0] == 87.5 and at_poles[11] == -87.5
    # a leading axis is kept, month by month
    both = ref.at_cell_centres(m, la, lo, np.stack([plane, 2 * plane]))
    assert both.shape == (2, m.n) and np.allclose(both[1], 2 * both[0])
    # where some of the four points have no value the others are used, and where none has one there is none
    holed = plane.copy()
    holed[10:14, 20:24] = np.nan
    patched = ref.at_cell_centres(m, la, lo, holed)
    inner = (m.lat > la[10] + 0.1) & (m.lat < la[13] - 0.1) & (m.lon > lo[20] + 0.1) & (m.lon < lo[23] - 0.1)
    assert inner.any() and np.all(np.isnan(patched[inner]))
    edge = np.isfinite(patched) & (np.abs(patched - got) > 1e-9)
    assert edge.any() and np.abs(patched - got)[edge].max() < 20.0                # made from the neighbours that have a value


# ---------------------------------------------------------------------------------------------- the relief data by itself
def island_grid():
    """A grid of one degree, all ocean at -100 m but for one land between 20 south and 20 north, 40 and 100 east:
    a plateau at 100 m with, inside it,
      a basin, floor at 20 m, behind a ring at 300 m with one notch at 150 m;
      an inland sea, bed at -50 m, behind ground at 5 m that reaches the coast;
      a pit, floor at 40 m, behind a wall at 400 m whose one gap, at 60 m, touches the pit at a corner only;
    and, across the line where the grid's columns begin, a strip of land at 10 m from 175 east to 175 west with a
    bay at -30 m that is open to the ocean only toward the west, beyond the last column."""
    lat = -89.5 + np.arange(180.0)
    lon = -179.5 + np.arange(360.0)
    la, lo = lat[:, None] * np.ones((1, 360)), np.ones((180, 1)) * lon[None, :]
    h = np.full((180, 360), -100.0)
    land = (np.abs(la) < 20) & (lo > 40) & (lo < 100)
    h[land] = 100.0
    ring = (np.abs(la) < 10) & (lo > 50) & (lo < 70)
    h[ring] = 300.0
    h[(np.abs(la) < 8) & (lo > 52) & (lo < 68)] = 20.0                           # the basin
    h[(np.abs(la - 0.5) < 0.6) & (lo > 67.9) & (lo < 70)] = 150.0                # the notch through the ring, eastward
    h[(np.abs(la) < 5) & (lo > 80) & (lo < 90)] = -50.0                          # the inland sea
    h[(np.abs(la) < 7) & (lo > 78) & (lo < 92) & (h > 0)] = 5.0                  # its low shores
    h[(np.abs(la) < 2) & (lo >= 92) & (lo < 100)] = 5.0                          # ... and low ground from them to the coast
    h[(la > -19) & (la < -14) & (lo > 92) & (lo < 97)] = 400.0                   # the wall, one point thick, round ...
    h[(la > -18) & (la < -15) & (lo > 93) & (lo < 96)] = 40.0                    # ... the pit, three points by three
    h[(np.abs(la + 14.5) < 0.1) & (np.abs(lo - 96.5) < 0.1)] = 60.0              # the gap: the wall's north-east corner
    strip = (np.abs(la) < 10) & ((lo > 175) | (lo < -175))
    h[strip] = 10.0
    h[(np.abs(la) < 3) & (lo > 177)] = -30.0                                     # the bay: columns 177.5 to 179.5 east
    h[(np.abs(la) < 3) & (lo < -175)] = -30.0                                    # ... and on through the first columns, to the ocean
    return lat, lon, h


def test_water_raised_from_the_ocean_finds_the_hollows_of_a_grid():
    """A Priority-Flood written for the comparison with the mesh, on a grid built for the purpose: what is ocean,
    and the level at which every other point is joined to it."""
    lat, lon, h = island_grid()
    f = ref.flood_grid(lat, lon, h, open_ocean=(-60.0, -120.0))
    at = lambda la, lo: ref.raw_at(f, la, lo)
    assert at(-60.0, -120.0)["ocean"] and at(30.5, 60.5)["ocean"]
    assert at(0.5, 85.5) == {"height": -50.0, "ocean": False, "level": 5.0}       # below sea level, but behind land: no ocean
    assert at(0.5, 45.5) == {"height": 100.0, "ocean": False, "level": 100.0}     # the plateau drains down to the sea
    assert at(0.5, 60.5) == {"height": 20.0, "ocean": False, "level": 150.0}      # the basin fills to its notch, not to its ring
    assert at(9.5, 60.5)["level"] == 300.0                                        # the ring itself
    # the pit is joined to the plateau through the corner of its wall: water passes between two points that touch
    # at a corner. Counting the four points beside each point alone, the pit would fill to the top of its wall
    assert at(-16.5, 94.5) == {"height": 40.0, "ocean": False, "level": 100.0}
    assert at(-14.5, 96.5) == {"height": 60.0, "ocean": False, "level": 100.0} and at(-14.5, 95.5)["level"] == 400.0
    assert at(0.5, 179.5)["ocean"] and at(0.5, -177.5)["ocean"]                   # the bay is ocean: the columns wrap round
    assert at(8.5, 179.5) == {"height": 10.0, "ocean": False, "level": 10.0}
    r = ref.raw_hollows(f)
    weight = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, 360))
    not_ocean = ~f["ocean"]
    under = not_ocean & np.isin(h, (20.0, -50.0, 40.0, 60.0))                    # the basin, the inland sea, the pit and its gap: nothing else
    assert np.isclose(r["not_ocean"], (weight * under).sum() / (weight * not_ocean).sum())
    assert np.isclose(r["land"], (weight * np.isin(h, (20.0, 40.0, 60.0))).sum() / (weight * (not_ocean & (h > 0))).sum())
    assert np.isclose(r["ocean_share_of_planet"], (weight * f["ocean"]).sum() / weight.sum())
    with pytest.raises(ValueError, match="open ocean is not below sea level"):
        ref.flood_grid(lat, lon, h, open_ocean=(0.5, 45.5))


def test_a_valley_is_judged_inside_its_own_box_and_against_the_way_round():
    """The basin of island_grid as a river's valley. Inside a box that holds the notch, the way out rises to 150 m,
    to a place beyond the ring and to the sea alike. Inside a box that leaves the notch out, it rises to the ring,
    300 m; by any way at all the basin is joined to the ocean at 150 m. A place that is ocean has no level and
    stands open. A place outside its box is refused."""
    lat, lon, h = island_grid()
    f = ref.flood_grid(lat, lon, h, open_ocean=(-60.0, -120.0))
    places = {"through the notch": ((0.5, 60.5), (0.5, 75.5), (-15.0, 15.0, 45.0, 79.0)),
              "through the notch to the sea": ((0.5, 60.5), None, (-25.0, 25.0, 45.0, 110.0)),
              "over the ring": ((0.5, 60.5), None, (-25.0, 25.0, 35.0, 67.5)),
              "open": ((30.5, 60.5), None, (25.0, 35.0, 50.0, 70.0))}
    r = ref.raw_narrows(f, places)
    assert r["through the notch"] == {"start_m": 20.0, "barrier_m": 150.0, "to_ocean_m": 150.0}
    assert r["through the notch to the sea"] == {"start_m": 20.0, "barrier_m": 150.0, "to_ocean_m": 150.0}
    assert r["over the ring"] == {"start_m": 20.0, "barrier_m": 300.0, "to_ocean_m": 150.0}
    assert r["open"]["start_m"] == -100.0 and np.isnan(r["open"]["to_ocean_m"])
    for outside in (((40.5, 60.5), None, (-15.0, 15.0, 45.0, 79.0)), ((0.5, 60.5), (40.5, 60.5), (-15.0, 15.0, 45.0, 79.0))):
        with pytest.raises(ValueError, match="does not lie inside the valley's box"):
            ref.raw_narrows(f, {"outside": outside})


class FlatEarth:
    """As much of earth_reference.Earth as narrows() looks at, on ground built for the purpose."""

    def __init__(self, mesh, ground, wet, ways=None):
        self.mesh, self.ground, self.mean, self.wet, self.ways = mesh, ground, ground + 50.0, wet, ways

    def cell(self, lat, lon):
        a, b = np.deg2rad(lat), np.deg2rad(lon)
        return int(np.argmax(self.mesh.xyz @ np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])))

    def lake_at(self, lat, lon):
        return {"level_m": 40.0, "overflows": True}

    def books(self):
        return {} if self.ways is None else {"flows": {"receivers": self.ways}}


def test_the_way_through_a_valley_on_the_mesh_stays_on_land_and_inside_its_box():
    """A valley along the equator from 0 to 40 east, floor at 10 m, with a bar across it at 20 east that rises to
    200 m. North of it lies a sea, and south of it a second valley without a bar. The way from one end to the other
    must go over the bar: it may not take to the sea, and it may not leave the box for the valley to the south."""
    m = get_mesh(5)
    lat, lon = m.lat, m.lon
    ground = np.full(m.n, 1000.0)
    valley = (np.abs(lat) < 3.5) & (lon > -5) & (lon < 45)
    ground[valley] = 10.0
    ground[valley & (np.abs(lon - 20) < 2.5)] = 200.0                             # the bar
    wet = (lat >= 3.5) & (lat < 12) & (lon > -5) & (lon < 45)                     # a sea along the valley's north side
    ground[wet] = -50.0
    south = (lat <= -3.5) & (lat > -9) & (lon > -5) & (lon < 45)
    ground[south] = 10.0                                                         # the valley to the south: no bar
    earth = FlatEarth(m, ground, wet)
    box = (-3.4, 12.0, -3.0, 43.0)
    r = ref.narrows(earth, {"bar": ((0.0, 2.0), (0.0, 38.0), box)})["bar"]
    assert r["barrier_m"] == 200.0 and abs(r["barrier_at"][1] - 20.0) < 3.0 and abs(r["barrier_at"][0]) < 3.5
    assert r["lake_level_m"] == 40.0 and r["lake_overflows"] and r["leaves_at"] is None
    # with the valley to the south inside the box, the way goes round the bar
    assert ref.narrows(earth, {"bar": ((0.0, 2.0), (0.0, 38.0), (-9.0, 12.0, -3.0, 43.0))})["bar"]["barrier_m"] == 10.0
    # to the sea: the goal is any sea cell inside the box, and it is reached at once, at the valley's own height
    assert ref.narrows(earth, {"bar": ((0.0, 2.0), None, box)})["bar"]["barrier_m"] == 10.0
    # where the water goes instead: down the ways handed over, to the sea; the cell of the highest mean on that way
    ways = np.full(m.n, -1)
    path = [earth.cell(0.0, lon_) for lon_ in (2.0, 6.0, 10.0, 14.0)]
    path = [c for k, c in enumerate(path) if c not in path[:k]]
    north = earth.cell(6.0, 14.0)
    for a, b in zip(path, path[1:] + [north]):
        ways[a] = b
    earth = FlatEarth(m, ground, wet, ways)
    earth.mean[path[1]] = 900.0
    r = ref.narrows(earth, {"bar": ((0.0, 2.0), (0.0, 38.0), box)})["bar"]
    assert r["over_mean_m"] == 900.0 and r["handed_m"] == 10.0 and r["over_at"] == (float(lat[path[1]]), float(lon[path[1]]))
    assert r["leaves_at"] == (float(lat[path[-1]]), float(lon[path[-1]]))


# ---------------------------------------------------------------------------------------------- the readers
def test_the_three_ways_of_settling_earths_ties_are_what_the_harness_says_they_are():
    """Earth(ties=...): None leaves the engine's own rule; a number draws a width for every pair of neighbours and a
    place in the order for every cell, another draw for another number; "mean" prefers the way toward the cell of
    the lower mean height. While such an Earth runs a process, the library hands out its ties in place of the
    mesh's own, and the mesh's own again afterwards, also when the run fails."""
    from worldengine.library import drainage as dr
    m = get_mesh(4)
    bare = ref.Earth.__new__(ref.Earth)                                          # no data is read: only what the ties look at
    bare.mesh, bare.mean = m, np.linspace(500.0, -500.0, m.n)
    valid = m.nbr >= 0
    bare.ties = None
    assert bare._ties() is None
    bare.ties = 3
    three = bare._ties()
    assert sorted(three.rank) == list(range(m.n)) and not np.array_equal(three.rank, np.arange(m.n))      # the order of the cells is drawn too
    assert np.unique(three.edge).size == m.edge_cells.shape[0]                   # every pair its own width: the widths settle nearly every tie
    assert np.array_equal(three.way[valid], three.edge[m.nbr_edge[valid]]) and np.all(np.isneginf(three.way[~valid]))
    again = bare._ties()
    assert np.array_equal(again.edge, three.edge) and np.array_equal(again.rank, three.rank)              # the same draw for the same number
    bare.ties = 4
    four = bare._ties()
    assert not np.array_equal(four.edge, three.edge) and not np.array_equal(four.rank, three.rank)
    bare.ties = "mean"
    low = bare._ties()
    c = 100
    ring = [(k, int(j)) for k, j in enumerate(m.nbr[c]) if j >= 0]
    best = max(ring, key=lambda kj: low.way[c, kj[0]])[1]
    assert bare.mean[best] == min(bare.mean[j] for _, j in ring)                 # the wider way is the one toward the lower mean
    assert low.rank[np.argmin(bare.mean)] == 0 and sorted(low.rank) == list(range(m.n))
    bare.ties = "lowest"
    with pytest.raises(ValueError, match="ties can be None, a number"):
        bare._ties()
    # standing in for the library's function, and stepping out again
    real = dr.mesh_ties
    bare.ties = 3
    with bare._settling():
        handed = dr.mesh_ties(m)
        assert np.array_equal(handed.rank, three.rank) and np.array_equal(handed.edge, three.edge)
    assert dr.mesh_ties is real
    with pytest.raises(RuntimeError, match="the run fails"):
        with bare._settling():
            raise RuntimeError("the run fails")
    assert dr.mesh_ties is real
    bare.ties = None
    with bare._settling():
        assert dr.mesh_ties is real                                              # the engine's own rule: nothing is swapped


@needs_data
def test_the_relief_is_read_the_right_way_up_and_the_right_way_round():
    lat, lon, height = ref.relief()
    assert height.shape == (2160, 4320) and np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0)
    assert np.isclose(lat[0], -90.0 + 1 / 12) and lat[-1] == 90.0 and lon[0] == -180.0 and np.isclose(lon[-1], 180.0 - 1 / 12)
    at = lambda la, lo: float(height[np.abs(lat - la).argmin(), np.abs(lon - lo).argmin()])
    top = np.unravel_index(np.argmax(height), height.shape)
    # The highest point of this grid lies in the Karakoram, 7,833 m at 36.3 N, 75.1 E [MEASURED on the file]; a box
    # of 5 minutes of arc holds the mean of its ground, so Everest's box reads 6,096 m. Read the wrong way round, that
    # box would lie in the sea.
    assert 27.0 < lat[top[0]] < 37.0 and 73.0 < lon[top[1]] < 95.0 and height.max() > 7500
    assert at(27.99, 86.93) > 5500
    low = np.unravel_index(np.argmin(height), height.shape)
    assert abs(lat[low[0]] - 11.3) < 1.5 and abs(lon[low[1]] - 142.3) < 1.5 and height.min() < -9500    # the Mariana trench
    assert at(-80.0, 0.0) > 2000 and at(80.0, 0.0) < -1000                        # Antarctica is land; at 80 N, 0 E lies sea
    assert at(40.0, -100.0) > 300 and at(40.0, 100.0) > 1000 and at(0.0, -30.0) < -3000 and at(0.0, 30.0) > 500


@needs_data
def test_the_rain_is_read_month_by_month_from_january_and_missing_months_are_left_out():
    from scipy.io import netcdf_file
    raw = netcdf_file(str(ref.checked("V22_GPCP.1979-2010.nc")), "r", mmap=False)
    dates = raw.variables["date"][:]
    assert int(dates[0]) == 19790116 and int(dates[-1]) // 100 == 201012 and dates.size == 384       # the file's own calendar
    assert raw.variables["PREC"].units == b"mm/day" and (raw.variables["PREC"][:] < -9000).sum() > 0  # and it does hold missing values
    lat, lon, rain = ref.rain_monthly()
    assert rain.shape == (12, 72, 144) and np.isfinite(rain).all() and rain.min() >= 0.0 and rain.max() < 1500.0
    # by hand for one box and one month: the mean of the 32 Julys, in mm a day, times the days of the engine's month
    i, j = 40, 30
    july = raw.variables["PREC"][6::12, i, j].astype(np.float64)
    row = np.flatnonzero(lat == raw.variables["lat"][i])[0]
    col = np.flatnonzero(lon == (raw.variables["lon"][j] - 360.0 if raw.variables["lon"][j] >= 180.0 else raw.variables["lon"][j]))[0]
    assert np.isclose(rain[6, row, col], july[july > -9000].mean() * ref.YEAR_S / 86400.0 / 12.0, rtol=1e-12)
    at = lambda la, lo: rain[:, np.abs(lat - la).argmin(), np.abs(lon - lo).argmin()]
    assert at(22.5, 80.0).argmax() in (6, 7) and at(22.5, 80.0)[6] > 8 * at(22.5, 80.0)[0]             # India: the monsoon of July and August
    assert at(-13.75, 131.25).argmax() in (0, 1, 2) and at(-13.75, 131.25)[6] < 10.0                  # northern Australia: wet in January, dry in July
    area = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))
    assert abs((rain.sum(axis=0) * area).sum() / area.sum() - 977.0) < 10.0                           # mm a year over the globe


@needs_data
def test_the_temperature_is_read_in_degrees_and_in_the_months_of_the_calendar():
    lat, lon, t = ref.temperature_monthly()
    assert t.shape == (12, 36, 72) and np.isfinite(t).all() and -75.0 < t.min() < -50.0 and 30.0 < t.max() < 45.0
    at = lambda la, lo: t[:, np.abs(lat - la).argmin(), np.abs(lon - lo).argmin()]
    assert at(62.5, 127.5).argmin() == 0 and at(62.5, 127.5)[0] < -30.0 and at(62.5, 127.5).argmax() == 6     # Yakutia
    assert at(-27.5, 132.5).argmax() in (0, 1) and at(-27.5, 132.5).argmin() in (5, 6)                 # central Australia: summer in January
    assert at(-87.5, 0.0).max() < -20.0 and at(2.5, -62.5).min() > 20.0                               # the south pole; the Amazon
    area = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))
    assert abs((t.mean(axis=0) * area).sum() / area.sum() - 14.0) < 0.3                               # degrees C over the globe


@needs_data
def test_land_is_land_and_lakes_and_ice_shelves_are_not():
    """The mask's own words: "0=Ocean, 1=Land, 2=Lake, 3=Small Island, 4=Ice Shelf"."""
    from scipy.io import netcdf_file
    raw = netcdf_file(str(ref.checked("landsea.nc")), "r", mmap=False)
    assert raw.title == b"1x1 Land-Sea Mask, 0=Ocean, 1=Land, 2=Lake, 3=Small Island, 4=Ice Shelf"
    codes = raw.variables["LSMASK"][:]
    assert set(np.unique(codes).tolist()) == {0, 1, 2, 3, 4}
    lat, lon, land = ref.land_share()
    assert set(np.unique(land).tolist()) == {0.0, 1.0}
    assert land.sum() == np.isin(codes, (1, 3)).sum() and (codes == 2).sum() > 100 and (codes == 4).sum() > 100
    at = lambda la, lo: land[np.abs(lat - la).argmin(), np.abs(lon - lo).argmin()]
    assert at(23.5, 5.5) == 1 and at(0.5, -30.5) == 0                             # the Sahara; the Atlantic
    assert at(42.5, 50.5) == 0 and at(-80.5, -175.5) == 0                         # the Caspian is a lake; the Ross ice shelf
    area = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))
    assert abs((land * area).sum() / area.sum() - 0.29) < 0.01                    # the land share of the planet


@needs_data
def test_a_reference_file_that_is_not_the_one_listed_is_refused(tmp_path, monkeypatch):
    """The fetch tool checks each file when it fetches it. The readers check again, so that a file changed or put
    there afterwards is not read."""
    for name in ("absolute.nc", "landsea.nc"):
        shutil.copy(ref.folder() / name, tmp_path / name)
    monkeypatch.setenv("WORLDENGINE_REFERENCE_DATA", str(tmp_path))
    monkeypatch.setattr(ref, "_checked", {})
    assert ref.available("absolute.nc", "landsea.nc") and not ref.available() and not ref.available("ETOPO5.DAT")
    ref.temperature_monthly()
    data = bytearray((tmp_path / "absolute.nc").read_bytes())
    data[-1] ^= 1                                                                 # one bit of the last byte: the size stays
    (tmp_path / "absolute.nc").write_bytes(bytes(data))
    assert ref.available("absolute.nc")
    with pytest.raises(ValueError, match="not the one the list names"):
        ref.temperature_monthly()
    (tmp_path / "landsea.nc").write_bytes((tmp_path / "landsea.nc").read_bytes()[:-10])
    assert not ref.available("landsea.nc")
    with pytest.raises(ValueError, match="not the one the list names"):
        ref.land_share()
    with pytest.raises(FileNotFoundError, match="fetch_reference_data"):
        ref.relief()


# ---------------------------------------------------------------------------------------------- the fetch tool
def fetch_tool():
    spec = importlib.util.spec_from_file_location("fetch_reference_data", ROOT / "tools" / "fetch_reference_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CutShort(http.server.SimpleHTTPRequestHandler):
    """Serves files; a path that ends in ".cut" is announced at its full length and broken off half-way."""

    def do_GET(self):
        if not self.path.endswith(".cut"):
            return super().do_GET()
        data = b"x" * 1000
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data[:500])
        self.wfile.flush()
        self.connection.close()

    def log_message(self, *args):
        pass


@pytest.fixture()
def remote(tmp_path):
    served = tmp_path / "served" / "abc123" / "files"
    served.mkdir(parents=True)
    (served / "good.bin").write_bytes(b"the right contents" * 50)
    (served / "error.html").write_bytes(b"<html>Not here any more</html>")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(CutShort, directory=str(tmp_path / "served")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    good = (served / "good.bin").read_bytes()
    entry = lambda path, data=good: {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "what": "a test file"}
    source = {"repository": "none", "raw": f"http://127.0.0.1:{server.server_address[1]}", "commit": "abc123", "licence": "none"}
    yield source, entry, good
    server.shutdown()


def test_the_fetch_tool_fetches_what_is_missing_and_refuses_what_is_wrong(remote, tmp_path):
    source, entry, good = remote
    tool = fetch_tool()
    said = []
    run = lambda files, folder, **more: tool.main(listed={"source": source, "files": files}, folder=folder, say=said.append, **more)
    here = tmp_path / "here"
    # a missing file is fetched and checked; a second run fetches nothing
    assert run({"good.bin": entry("files/good.bin")}, here) == 0 and (here / "good.bin").read_bytes() == good
    assert any(line.startswith("fetching") for line in said) and said[-1].endswith("complete")
    said.clear()
    assert run({"good.bin": entry("files/good.bin")}, here) == 0 and not any(line.startswith("fetching") for line in said)
    # a file that is there but wrong is removed and fetched again
    (here / "good.bin").write_bytes(b"something else")
    assert run({"good.bin": entry("files/good.bin")}, here) == 0 and (here / "good.bin").read_bytes() == good
    # --check fetches nothing and removes nothing
    (here / "good.bin").write_bytes(b"something else")
    assert run({"good.bin": entry("files/good.bin"), "other.bin": entry("files/good.bin")}, here, check_only=True) == 1
    assert (here / "good.bin").read_bytes() == b"something else" and not (here / "other.bin").exists()
    # the right size with other contents, an error page in place of the file, a file that is not there, and a download
    # that breaks off half-way: each is refused, and nothing wrong is left behind
    cases = {"swapped.bin": {**entry("files/good.bin"), "sha256": "0" * 64},
             "page.bin": entry("files/error.html"),
             "absent.bin": entry("files/no_such_file.bin"),
             "broken.bin": entry("files/half.cut", b"x" * 1000)}
    there = tmp_path / "there"
    said.clear()
    assert run(cases, there) == 1
    assert sorted(p.name for p in there.iterdir()) == []                          # no file, and no part of one
    text = "\\n".join(said)
    assert text.count("REFUSED") + text.count("FAILED") == 4 and "4 file(s) missing or refused" in said[-1]
    assert "FAILED    absent.bin could not be fetched" in text and "REFUSED   swapped.bin" in text


def test_the_list_of_reference_files_names_each_file_its_size_its_hash_and_where_it_comes_from():
    listed = ref.listed()
    assert set(listed["files"]) == set(ref.NAMES)
    assert len(listed["source"]["commit"]) == 40 and "asked_of_users" in listed["source"] and "Apache-2.0" in listed["source"]["licence"]
    for name, entry in listed["files"].items():
        assert entry["bytes"] > 0 and len(entry["sha256"]) == 64 and entry["path"].endswith(name) and entry["what"]


# ---------------------------------------------------------------------------------------------- relief from a file
def relief_world(tmp_path, monkeypatch, heights, sha256=None, variable="TEST_RELIEF_FOLDER", set_variable=True, name="relief.npy"):
    np.save(tmp_path / name, heights)
    digest = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() if sha256 is None else sha256
    if set_variable:
        monkeypatch.setenv(variable, str(tmp_path))
    else:
        monkeypatch.delenv(variable, raising=False)
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    slots = {"PlanetGeometry": models["slots"]["PlanetGeometry"], "Isostasy": {
        "implementation": "worldengine.processes.relief_from_file:ReliefFromFile", "standing": "Test", "model": "a test relief",
        "ignores": "everything", "wrong_where": "everywhere", "writes": ["elevation"],
        "constants": {"file": name, "sha256": digest, "folder_from_env": variable}}}
    # The sentence patterns of the slot go with the process that fills it: the pattern of the real Isostasy names
    # drivers that this one does not record, and the engine refuses that.
    patterns = ref.earth_twin_explanations(yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8")))
    return Engine(DATA, profile="preview", overrides={"models": {"shared": models["shared"], "slots": slots}, "explanations": patterns})


def test_a_slot_filled_by_another_process_must_bring_sentence_patterns_that_fit_it(tmp_path, monkeypatch):
    """Relief read from a file in the slot of Isostasy, with the sentence patterns of the real Isostasy left in
    place: those explain the height by the crust, which this world does not have. The engine refuses the pair."""
    n = get_mesh(5).n
    np.save(tmp_path / "relief.npy", np.zeros(n, dtype=np.float32))
    monkeypatch.setenv("TEST_RELIEF_FOLDER", str(tmp_path))
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    slots = {"PlanetGeometry": models["slots"]["PlanetGeometry"], "Isostasy": {
        "implementation": "worldengine.processes.relief_from_file:ReliefFromFile", "standing": "Test", "model": "a test relief",
        "ignores": "everything", "wrong_where": "everywhere", "writes": ["elevation"],
        "constants": {"file": "relief.npy", "sha256": "0" * 64, "folder_from_env": "TEST_RELIEF_FOLDER"}}}
    with pytest.raises(ParameterError, match="Isostasy.elevation: the pattern names the driver .* which Isostasy does not record"):
        Engine(DATA, profile="preview", overrides={"models": {"shared": models["shared"], "slots": slots}})


def test_relief_from_a_file_is_taken_only_from_the_file_its_constants_name(tmp_path, monkeypatch):
    n = get_mesh(5).n
    heights = np.linspace(-4000.0, 3000.0, n).astype(np.float32)
    e = relief_world(tmp_path, monkeypatch, heights)
    w = e.build()
    assert np.array_equal(w.fields["elevation"], heights) and w.lineage["elevation"]["model"] == "measured relief read from a file, not computed"
    assert e.constants["Isostasy"]["file"] == "relief.npy"                        # the parameters do not hold where the file lies
    with pytest.raises(ValueError, match="SHA-256"):                              # another file under the same name
        relief_world(tmp_path, monkeypatch, heights + 1.0, sha256=hashlib.sha256(b"what the constants name").hexdigest()).build()
    for wrong in (heights[:-1], np.concatenate([heights, heights[:1]]), np.where(np.arange(n) == 5, np.nan, heights),
                  np.where(np.arange(n) == 5, np.inf, heights), np.arange(n), heights.reshape(2, -1)):
        with pytest.raises(ValueError, match="one finite height for each"):
            relief_world(tmp_path, monkeypatch, wrong).build()
    with pytest.raises(ValueError, match="is not set"):
        relief_world(tmp_path, monkeypatch, heights, set_variable=False).build()


@needs_data
def test_the_twins_relief_is_made_afresh_from_the_checked_file_and_a_planted_one_is_replaced(tmp_path, monkeypatch):
    """The relief file of the twin is derived from ETOPO5. A file left under its name by anyone else used to be taken
    as it stood, with a hash worked out from the planted file itself."""
    m = get_mesh(3)
    real = ref.folder()
    monkeypatch.setenv("WORLDENGINE_REFERENCE_DATA", str(tmp_path))
    monkeypatch.setattr(ref, "_checked", {})
    shutil.copy(real / "ETOPO5.DAT", tmp_path / "ETOPO5.DAT")
    (tmp_path / "mesh").mkdir()
    np.save(tmp_path / "mesh" / "earth_relief_level3.npy", np.full(m.n, 1234.0, dtype=np.float32))    # a plateau of 1,234 m
    path, digest = ref.earth_relief_file(m)
    heights = np.load(path)
    lat, lon, height = ref.relief()
    assert np.array_equal(heights, ref.cell_means(m, lat, lon, height).astype(np.float32)) and heights.min() < -4000
    assert digest == hashlib.sha256(open(path, "rb").read()).hexdigest()
    models = ref.earth_twin_models(yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8")), m)
    constants = models["slots"]["Isostasy"]["constants"]
    assert constants == {"file": "earth_relief_level3.npy", "sha256": digest, "folder_from_env": ref.RELIEF_FOLDER_VARIABLE}
    assert "Tectonics" not in models["slots"] and "Drainage" in models["slots"]
    words = ref.earth_twin_explanations(yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8")))
    assert "Tectonics" not in words and "read from a file" in words["Isostasy"]["elevation"]["says"]
