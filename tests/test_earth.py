"""Single processes, and the whole engine on Earth's relief, judged against patterns measured on Earth (design, Layer 9).

The first part hands one process inputs measured on Earth (relief, rain, temperature) and asks for a pattern that
an atlas shows: given the truth as its input, does the process return the truth as its output? Those runs are on
the standard mesh, 163,842 cells about 60 km apart. The last part builds the Earth twin, the whole engine on
Earth's relief, on the preview mesh (10,242 cells about 240 km apart). The data is fetched by
tools/fetch_reference_data.py; without it every test here is skipped.

What each condition is and when it was set:
  * "set before the run": written down before the process had been run on Earth's data. These are the tests that
    can show the engine wrong. A condition of this kind that the engine fails is NOT loosened: it stays as it was
    written and is marked as an expected failure, with the number measured.
  * "found, then kept": something the first run showed and nobody had asked for. It guards against losing it, and
    proves less.
An expected failure (xfail) states a pattern of Earth that the engine does not return, with the reason and the
number measured. It is strict and names its exception: if the engine starts to return the pattern, or the test
breaks for another reason, the run fails and the mark must go. Every pattern the engine is known to miss is
written this way, as the statement of what Earth does, so that the count of expected failures is the count of
known misses. The reasons give causes; where a cause is my reading and not a measurement it says [INFERRED].

Numbers that belong to these tests and are not Earth's:
  * The valley share, 0.1 (earth_reference.VALLEY_SHARE). A river runs along the floor of its valley, not at the
    mean height of the 60 km around it. The design asked for "relief converted so that valley floors survive";
    here a land cell's height for drainage is the height below which a tenth of its land points lie. The tenth was
    chosen when this file was first written and has not been tuned since. The outcomes depend on it [MEASURED with
    tools/earth_rivers.py --valley-share; docs/BUILD_NOTES.md gives the table]: for shares from 0.02 to 0.5, 15 to
    17 of the 24 river mouths lie within 300 km and 6 or 7 of the 21 gauges within a factor of two, but which
    rivers they are changes with the share, and so does whether the lake at the Caspian's place overflows.
  * The places, given to the nearest half degree from memory [UNVERIFIED]; the distances asked for are hundreds of
    kilometres, so that is close enough.
"""
import numpy as np
import pytest
import yaml

import earth_reference as ref
from conftest import DATA
from worldengine.engine import Engine
from worldengine.library import operators as op
from worldengine.mesh import get_mesh

pytestmark = pytest.mark.skipif(not ref.available(), reason="the Earth reference data is not here: run python tools/fetch_reference_data.py")

R = ref.EARTH_RADIUS_M
YEAR_S = ref.YEAR_S
LEVEL = 7
missed = lambda reason: pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)


@pytest.fixture(scope="module")
def earth():
    return ref.Earth(LEVEL)


# ---------------------------------------------------------------------------------------------- the patterns on Earth
def land_rain_by_band():
    """Earth's yearly rain over land in bands of 5 degrees of latitude: GPCP 1979 to 2010 over the land of the
    one-degree mask. Returns (latitude of each band, mm a year, mean over all land)."""
    lat, lon, rain = ref.rain_monthly()
    yearly = rain.sum(axis=0)
    mlat, mlon, land = ref.land_share()
    share = np.zeros(yearly.shape)
    count = np.zeros(yearly.shape)
    weight = np.cos(np.deg2rad(mlat))[:, None] * np.ones((1, mlon.size))
    rows = np.clip(((mlat - (lat[0] - 1.25)) / 2.5).astype(int), 0, lat.size - 1)
    cols = (((mlon - (lon[0] - 1.25)) % 360.0) / 2.5).astype(int) % lon.size
    np.add.at(share, (rows[:, None], cols[None, :]), land * weight)
    np.add.at(count, (rows[:, None], cols[None, :]), weight)
    share /= count
    area = np.cos(np.deg2rad(lat))[:, None] * share
    bands = yearly.reshape(36, 2, -1), area.reshape(36, 2, -1)
    band_lat = lat.reshape(36, 2).mean(axis=1)
    land_in_band = bands[1].sum(axis=(1, 2))
    has_land = land_in_band > 0                              # (the band at 57.5 S holds no land at all)
    land_rain = np.where(has_land, (bands[0] * bands[1]).sum(axis=(1, 2)) / np.where(has_land, land_in_band, 1.0), np.nan)
    return band_lat, land_rain, float((yearly * area).sum() / area.sum())


def test_on_earth_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40():
    """The design's pass condition for rain (Layer 9), measured on Earth itself: it holds. North: 566 mm at 27.5
    degrees; south: 629 mm at 32.5. The bands at 47.5, 52.5 and 57.5 north get 645, 689 and 690 mm. The engine's
    own worlds are asked the same in tests/test_world.py and at the end of this file. [MEASURED from the reference
    data; found, then kept, to the numbers given.]"""
    band_lat, land_rain, all_land = land_rain_by_band()
    assert abs(all_land - 804.0) < 10.0                                           # mm a year over land
    for sign, driest_at, driest_mm in ((1, 27.5, 566.0), (-1, 32.5, 629.0)):
        side = (sign * band_lat > 0) & (sign * band_lat < 60) & np.isfinite(land_rain)
        k = np.argmin(np.where(side, land_rain, np.inf))
        assert 15 <= sign * band_lat[k] <= 40                                     # the design's condition
        assert sign * band_lat[k] == driest_at and abs(land_rain[k] - driest_mm) < 5.0
        storm_belt = land_rain[(sign * band_lat > 40) & (sign * band_lat < 55)].mean()
        assert storm_belt > 1.1 * land_rain[k]                                    # the weaker pattern that test_world.py also asks
    north = {lat: mm for lat, mm in zip(band_lat, land_rain) if lat in (47.5, 52.5, 57.5)}
    assert all(abs(north[lat] - mm) < 8.0 for lat, mm in ((47.5, 645.0), (52.5, 689.0), (57.5, 690.0)))


# ---------------------------------------------------------------------------------------------- SeaLevel
def test_earths_water_poured_on_earths_relief_comes_to_rest_at_earths_sea_level(earth):
    """Set before the run: the sea level within 60 m of zero, the sea over 69 to 73 % of the planet, one ocean.
    The volume poured is the planet file's, 1.335e18 m3 [DOCUMENTED there]; ETOPO5's own sea holds 0.23 % more
    [MEASURED by the reviewer of build step 2], about 8 m of sea level. The lists of places below were written
    with the first run in view: found, then kept."""
    seas = earth.sea.tables["seas"]
    assert abs(earth.sea_level) < 60.0
    assert 0.69 < earth.area[earth.wet].sum() / earth.area.sum() < 0.73
    assert seas["volume_m3"][0] / seas["volume_m3"].sum() > 0.99
    for name, place in {"the Mediterranean": (35.0, 18.0), "the Gulf of Mexico": (25.0, -90.0), "Hudson Bay": (60.0, -85.0),
                        "the Sea of Japan": (40.0, 135.0)}.items():
        assert earth.wet[earth.cell(*place)], name
    for name, place in {"Tibet": (33.0, 88.0), "the Sahara": (23.0, 5.0), "the Amazon lowland": (-3.0, -60.0), "the Caspian": (42.0, 51.0)}.items():
        assert not earth.wet[earth.cell(*place)], name                            # (the Caspian lies below sea level, behind a barrier)


@pytest.mark.parametrize("name,place", [("the Black Sea", (43.0, 34.0)), ("the Red Sea", (20.0, 38.5)), ("the Baltic", (58.0, 20.0))])
@missed("Straits narrower than a cell are closed on this mesh: the Bosporus, the strait at the mouth of the Red Sea and the straits "
        "of Denmark. The sea behind each stays dry in SeaLevel; Hydrology then fills the Black Sea and the Baltic as lakes.")
def test_a_sea_behind_a_narrow_strait_is_part_of_the_ocean(earth, name, place):
    assert earth.wet[earth.cell(*place)], name


# ---------------------------------------------------------------------------------------------- Drainage
def test_the_amazon_reaches_the_atlantic_and_the_nile_the_mediterranean(earth):
    """Set before the run (the design's own list): from Manaus the water reaches the sea within 600 km of the Amazon's
    mouth, and from Khartoum within 600 km of the Nile's. The bounds on the areas drained were written after the
    first run (found, then kept): the Amazon drains 5.85 million km2 [DOCUMENTED: Dai and Trenberth, Table 2, at the
    river mouth], the Nile about 3.3 million [UNVERIFIED: from memory]."""
    basin = earth.drainage.fields["basin_id"]
    amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
    assert earth.km(amazon, -0.5, -50.0) < 600.0 and earth.km(nile, 31.5, 31.0) < 600.0
    area = earth.drainage.fields["drainage_area"]
    assert 4.5e12 < area[amazon] < 8.0e12 and 2.5e12 < area[nile] < 4.5e12        # m2


def test_central_asia_and_the_great_basin_are_closed_hollows(earth):
    """Set before the run (the design's own list): the Tarim basin and the Great Basin drain into closed hollows.
    Found, then kept: the Tarim's water collects within 400 km of Lop Nur, at 600 to 900 m."""
    f, t = earth.drainage.fields, earth.drainage.tables["hollows"]
    tarim, great_basin = earth.cell(39.0, 83.0), earth.cell(40.0, -116.5)
    assert f["depression_id"][tarim] > 0 and f["depression_id"][great_basin] > 0
    bottom = int(t["bottom_cell"][f["depression_id"][tarim]])
    assert earth.km(bottom, 40.2, 90.5) < 400.0 and 600.0 < t["bottom_m"][f["depression_id"][tarim]] < 900.0


# The rivers that the mesh misleads, with the distance measured between the place where each leaves the land on the mesh
# and its real mouth [MEASURED: python tools/earth_rivers.py, part 2]. Where a reason says that narrows are closed, with
# heights, that is measured too (part 5 of the tool; NARROWS_M below, which a test keeps true). The rest of each cause
# is my reading of the river's way over the mesh [INFERRED]. MOUTH_KM holds the distance of every river; a test below
# keeps it true.
MISLED = {
    "Congo": "730 km. Between its central basin and Kinshasa the river runs in a valley narrower than a cell, which is closed "
             "on the mesh: its floor rises to 518 m. The basin fills as a lake of 880,226 km2 to 457 m and overflows "
             "westward, to the sea at the equator.",
    "Ob": "631 km. The Gulf of Ob, the river's estuary, is narrower than a cell and is land on the mesh, a lake of 43,913 km2: "
          "the river runs on along it and leaves the land at its seaward end.",
    "Danube": "1,145 km. The Iron Gate is narrower than a cell and closed on the mesh: its floor rises to 208 m. The plain "
              "above it fills as a lake of 226,505 km2 to 177 m, which overflows to the Adriatic.",
    "Yenisei": "326 km. No barrier stands in the real valley on the mesh. The plain west of it is lower, cell by cell, and "
               "the rule of the lowest neighbour takes the river across it to the Ob, with which it leaves the land.",
    "Volga": "1,848 km. The Volga ends in the Caspian, a closed sea. basin_id follows the water on as if every hollow were full, "
             "across the Black Sea's dry bed to the Aegean: a river of a closed sea cannot meet this condition as it was "
             "written. Where the mesh's Volga ends is tested with the Caspian, below.",
    "St Lawrence": "1,062 km. Below Quebec the estuary is narrower than a cell and is land on the mesh, with a floor that "
                   "rises to 204 m. The lake above it stands at 102 m and overflows southward, by Lake Champlain and the "
                   "Hudson.",
    "Amur": "1,291 km. The lower Amur is closed on the mesh: its floor rises to 137 m. The river leaves southward through a "
            "lake of 180,651 km2 that stands at 107 m, to the Sea of Japan.",
    "Huang He": "1,253 km. On the mesh the upper river ends in a closed hollow near Lanzhou; with every hollow full its water "
                "runs north-east across the hollows of Mongolia and Manchuria and leaves the land with the Amur's."}
MOUTH_KM = {"Amazon": 214, "Nile": 255, "Mississippi": 265, "Congo": 730, "Yangtze": 55, "Ob": 631, "Mackenzie": 107, "Danube": 1145,
            "Ganges": 58, "Parana": 126, "Niger": 196, "Lena": 231, "Yenisei": 326, "Indus": 110, "Murray": 0, "Volga": 1848,
            "Zambezi": 56, "Orinoco": 207, "St Lawrence": 1062, "Columbia": 108, "Rhine": 58, "Mekong": 263, "Amur": 1291,
            "Huang He": 1253}


# The narrows that the mesh closes: the height to which the valley's floor rises on the mesh, and the level of the lake
# that stands above it, in metres [MEASURED: tools/earth_rivers.py, part 5]. A test below keeps the numbers true.
NARROWS_M = {"Congo": (518, 457), "Danube": (208, 177), "Lena": (137, 122), "St Lawrence": (204, 102), "Amur": (137, 107),
             "Yangtze": (762, 381)}


def _mouth_km(earth, river):
    place, mouth = ref.GREAT_RIVERS[river]
    return earth.km(int(earth.drainage.fields["basin_id"][earth.cell(*place)]), *mouth)


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(MISLED[name])) if name in MISLED else name for name in ref.GREAT_RIVERS])
def test_a_great_river_reaches_the_sea_where_it_does_on_earth(earth, river):
    """Each of 24 great rivers, with every hollow on its way full, leaves the land within 300 km of its real mouth.
    The list of rivers and the 300 km were written before the first run; which rivers fail was found by it: 8 of
    the 24. Each is an expected failure of its own, with its distance and its cause."""
    assert _mouth_km(earth, river) < 300.0, f"{river}: {_mouth_km(earth, river):.0f} km from its mouth"


def test_the_distances_recorded_for_the_mouths_are_the_ones_the_engine_gives(earth):
    """Found, then kept: it keeps the numbers in MISLED and in docs/BUILD_NOTES.md true. A change to Drainage, or to
    the way Earth's relief is put on the mesh, that moves a mouth by more than 5 km fails here, and the records
    must then be measured again."""
    assert set(MOUTH_KM) == set(ref.GREAT_RIVERS)
    off = {river: round(_mouth_km(earth, river)) for river in MOUTH_KM if abs(_mouth_km(earth, river) - MOUTH_KM[river]) > 5.0}
    assert not off, off


def test_the_narrows_recorded_as_closed_are_closed_on_the_mesh(earth):
    """Found, then kept: it keeps true what the reasons of the expected failures say about closed narrows. In each of
    six valleys the mesh's ground rises above the level of the lake that stands above the narrows; five of those
    lakes overflow by another way, and the sixth, in the Sichuan basin above the Three Gorges, keeps its water."""
    found = ref.narrows(earth)
    assert set(found) == set(NARROWS_M)
    for river, (barrier, lake) in NARROWS_M.items():
        r = found[river]
        assert abs(r["barrier_m"] - barrier) <= 1.0 and abs(r["lake_level_m"] - lake) <= 1.0, (river, r)
        assert r["barrier_m"] > r["lake_level_m"] and r["lake_overflows"] == (river != "Yangtze")


# ---------------------------------------------------------------------------------------------- Hydrology
def test_under_earths_rain_and_warmth_the_land_gives_back_what_earths_land_gives_back(earth):
    """Set before the run: of the rain on land, between 0.50 and 0.75 goes back to the air, and 28,000 to 52,000 km3 a
    year reach the sea. Earth: 74 of 114 thousand km3 go back, 0.65, and 40 thousand reach the sea [DOCUMENTED when
    build step 2 was written: Trenberth, Fasullo and Mackaro 2011].
    The engine: 0.735 goes back and 31.7 thousand km3 reach the sea, of 119.8 thousand that GPCP's rain puts on the
    mesh's land [MEASURED: python tools/earth_rivers.py, part 4]. Inside the range, and too much: 0.706 would go
    back if no cell were flooded, and the lakes, most of which Earth does not have, give the air the rest. The
    total hides errors of both signs, which the test of the gauges below takes apart river by river."""
    f = earth.hydrology().fields
    fell = (earth.rain.sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_sea = f["river_discharge"].astype(np.float64)[:, earth.wet].mean(axis=0).sum() * YEAR_S
    assert 0.50 < to_air / fell < 0.75
    assert 28.0e12 < to_sea < 52.0e12
    assert abs((fell - to_air) / to_sea - 1) < 1e-3            # and none is lost on the way
    assert not earth.hydrology().notices


def test_the_amazon_carries_the_most_water(earth):
    """Set before the run: the largest flow into the sea lies within 800 km of the Amazon's mouth and is within a
    factor of two of the Amazon's: 6,642 km3 a year at its mouth, 210,000 m3/s [DOCUMENTED: Dai and Trenberth,
    Table 2]. Two things are asked, because two cells can be called the largest flow into the sea: the sea cell that
    receives the most (on the mesh one sea cell can take the water of two mouths), and the land cell that carries
    the most. The engine gives 150,010 and 145,166 m3/s [MEASURED]."""
    river = earth.hydrology().fields["river_discharge"].astype(np.float64).mean(axis=0)
    into_sea = int(np.argmax(np.where(earth.wet, river, -1.0)))
    on_land = int(np.argmax(np.where(earth.land, river, -1.0)))
    for cell in (into_sea, on_land):
        assert earth.km(cell, -0.5, -50.0) < 800.0
        assert 105_000.0 < river[cell] < 420_000.0
    assert earth.wet[earth.drainage.fields["flow_receiver"][on_land]]             # the largest river is at its mouth


# The rivers whose flow at the last gauge the engine misses by more than a factor of two, each with the flow it gives
# and the reason, taken apart by tools/earth_rivers.py (part 1) [MEASURED]: the land whose water reaches the gauge on the
# mesh against the real basin, and what that land sheds in a year against the measured flow over the real basin. Where
# a reason names a cause beyond those numbers, it is my reading [INFERRED]. AT_GAUGE holds, for every river, the flow
# (km3 a year) and the land that reaches the gauge (thousand km2); a test below keeps it true.
OFF_AT_GAUGE = {
    "Congo": "7 km3 a year against 1,271. The river's valley between its central basin and Kinshasa is narrower than a cell "
             "and closed on the mesh: the basin fills as a lake and its water leaves westward, at the equator. Land of 43 "
             "thousand km2 reaches the gauge, of the real 3,475.",
    "Orinoco": "351 km3 a year against 984. Land of 557 thousand km2 reaches the gauge (836 on Earth), and it sheds 704 mm a year "
               "where 1,177 are measured.",
    "Yangtze": "127 km3 a year against 910. The Three Gorges are narrower than a cell and closed on the mesh: their floor rises "
               "to 762 m, and the Sichuan basin above them holds a lake at 381 m that keeps its water. Land of 842 thousand "
               "km2 reaches the gauge (1,705 on Earth). And that land sheds 185 mm a year where 534 are measured: its rain, "
               "1,342 mm, is hardly more than the demand for water the engine gives it, 1,202 mm.",
    "Brahmaputra": "258 km3 a year against 613. The basin is nearly right (483 thousand km2 reach the gauge; 555 on Earth), but its "
                   "land sheds 575 mm a year where 1,105 are measured. The rain handed to the engine puts 1,563 mm a year on it; "
                   "on its grid of 2.5 degrees it cannot hold the rain of the mountain front [INFERRED].",
    "Yenisei": "107 km3 a year against 577. The mesh's Yenisei turns west at 63 degrees north, across lower ground, and "
               "reaches the sea with the Ob, 227 km from the gauge at its nearest: land of 251 thousand km2 reaches the "
               "gauge, of the real 2,440.",
    "Lena": "10 km3 a year against 526. The narrows above the delta, where the gauge stands, are closed on the mesh: their floor "
            "rises to 137 m. The lowland above them fills as a lake of 150,490 km2 to 122 m, which overflows to the sea west "
            "of the delta, 214 km from the gauge at its nearest. Land of 272 thousand km2 reaches the gauge, of the real 2,430.",
    "Mekong": "34 km3 a year against 292. The mesh's Mekong runs west of its real valley, across lower ground, and passes 173 km "
              "from the gauge: land of 53 thousand km2 reaches the gauge, of the real 545.",
    "Ob": "139 km3 a year against 397. The mesh's Ob crosses a lake of 437,843 km2 on the West Siberian plain, runs north-east "
          "and enters its estuary from the east, 442 km from the gauge at its nearest: land of 294 thousand km2 reaches the "
          "gauge, of the real 2,430.",
    "St Lawrence": "477 km3 a year against 226: too much. On the mesh land of 1,261 thousand km2 reaches the gauge (774 on Earth), "
                   "and it sheds 442 mm a year where 292 are measured.",
    "Amur": "26 km3 a year against 312. The lower Amur is closed on the mesh, and the river leaves southward to the Sea of "
            "Japan: land of 100 thousand km2 reaches the gauge, of the real 1,730.",
    "Mackenzie": "115 km3 a year against 288. The basin is right (1,740 thousand km2 reach the gauge; 1,660 on Earth), but its "
                 "land sheds 88 mm a year where 173 are measured, and lakes on the way, two of them of 131,455 and 88,461 km2, "
                 "lose 37 km3 of that.",
    "Danube": "19 km3 a year against 202. The Iron Gate is closed on the mesh, and the river leaves to the Adriatic: land of 133 "
              "thousand km2 reaches the gauge, of the real 807.",
    "Niger": "6 km3 a year against 33. Hollows that the real valley does not have keep the river, and in so dry a climate "
             "they do not fill: land of 125 thousand km2 reaches the gauge, of the real 1,516.",
    "Zambezi": "11 km3 a year against 105. Hollows that the real valley does not have keep the upper river: land of 233 "
               "thousand km2 reaches the gauge, of the real 940, and it sheds 71 mm a year where 112 are measured.",
    "Indus": "Under 1 km3 a year against 89. On its plain the mesh's Indus ends in shallow hollows that the real plain does "
             "not have, and that so dry a climate never fills: land of 23 thousand km2 reaches the gauge, of the real 975."}
AT_GAUGE = {"Amazon": (4333, 5584), "Congo": (7, 43), "Orinoco": (351, 557), "Yangtze": (127, 842), "Brahmaputra": (258, 483),
            "Mississippi": (417, 2164), "Yenisei": (107, 251), "Parana": (484, 2866), "Lena": (10, 272), "Mekong": (34, 53),
            "Ob": (139, 294), "Ganges": (258, 483), "St Lawrence": (477, 1261), "Amur": (26, 100), "Mackenzie": (115, 1740),
            "Columbia": (117, 484), "Danube": (19, 133), "Niger": (6, 125), "Zambezi": (11, 233), "Indus": (0, 23), "Rhine": (82, 184)}


@pytest.fixture(scope="module")
def gauges(earth):
    return ref.rivers_at_gauges(earth)


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(OFF_AT_GAUGE[name])) if name in OFF_AT_GAUGE else name for name in ref.GAUGES])
def test_a_great_river_carries_at_its_last_gauge_what_it_carries_on_earth(gauges, river):
    """Set before the run, and left as it was set: under Earth's rain and warmth, the largest yearly flow within 150 km
    of the station (the mesh may run the river through the next cell) is within a factor of two of the flow
    measured there [DOCUMENTED: Dai and Trenberth, Table 2; earth_reference.GAUGES]. 6 of the 21 rivers pass. Each
    of the 15 that fail is an expected failure of its own. Eleven fail because under half of the real basin
    reaches the gauge on the mesh: narrows are closed, or the river crosses lower ground beside its valley, or
    hollows that the real valley does not have keep its water. The others because the land sheds too little or too
    much (docs/BUILD_NOTES.md).
    The rule takes the largest flow near the station, whichever river carries it. For the Ganges that is the mesh's
    Brahmaputra, 147 km from the station; the mesh's own Ganges carries 231 km3 there and would pass as well."""
    r = gauges[river]
    assert r["measured"] / 2.0 < r["flow"] < r["measured"] * 2.0, f"{river}: {r['flow']:.0f} km3 a year against {r['measured']:.0f}"


def test_the_flows_recorded_for_the_gauges_are_the_ones_the_engine_gives(gauges):
    """Found, then kept: it keeps the numbers in OFF_AT_GAUGE and in docs/BUILD_NOTES.md true. A change that moves a
    flow or the land that reaches a gauge by more than 2 % (or by 1 km3, or 2 thousand km2) fails here, and the
    records must then be measured again."""
    assert set(AT_GAUGE) == set(ref.GAUGES)
    off = {}
    for river, (flow, reaches) in AT_GAUGE.items():
        r = gauges[river]
        if abs(r["flow"] - flow) > max(0.02 * flow, 1.0) or abs(r["reaches"] - reaches) > max(0.02 * reaches, 2.0):
            off[river] = (round(r["flow"]), round(r["reaches"]))
    assert not off, off
    for r in gauges.values():                                 # the parts add up to the flow, river by river
        assert abs(r["reaches"] * r["sheds"] / 1000.0 - r["lost_in_lakes"] - r["flow"]) < 1e-6 * max(r["flow"], 1.0)


@missed("The lake at the Caspian's place overflows. The mesh's rivers bring it 575 km3 a year [MEASURED], where about 300 reach "
        "the real sea [UNVERIFIED: recalled]: the snowy plains to its north shed more than they do on Earth (docs/BUILD_NOTES.md). "
        "The lake spreads over 1,113,492 km2 and stands at 61 m before its surface loses what arrives, and 4 km3 a year still "
        "run over its pass [MEASURED]. The real sea covers about 371,000 km2 and stands 28 m below the ocean [UNVERIFIED]. "
        "The outcome hangs on those 4 km3: with the valley share at 0.02, 0.05, 0.2 or 0.3 in place of 0.1 the lake stays "
        "closed, at 1.0 to 1.1 million km2 [MEASURED].")
def test_the_caspian_stays_a_closed_lake(earth):
    """Set before the run (the design's own list)."""
    lake = earth.lake_at(42.0, 51.0)
    assert lake is not None and not lake["overflows"]


def test_seas_that_the_mesh_cuts_off_and_the_great_lakes_come_back_as_lakes_near_their_real_size(earth):
    """Found, then kept. SeaLevel leaves the Black Sea and the Baltic dry, because their straits are narrower than a
    cell. Hydrology fills them again from Earth's rain: more water reaches each than its surface can lose, as on
    Earth, so each rises until it overflows. The Great Lakes appear too. The engine gives 472,814 km2 at 0 m,
    298,005 km2 at -1 m and 298,119 km2 at 179 m [MEASURED]. The sizes of Earth's seas and lakes are from memory
    [UNVERIFIED]: the Black Sea 436,000 km2, the Baltic 377,000 km2, Superior, Michigan and Huron together
    244,000 km2 at 176 to 183 m. This test passes under any wet climate, since these hollows then overflow
    whatever the rain: it shows that the relief holds the hollows, and little about the water."""
    for place, area_km2, level_m in (((43.0, 34.0), (350_000, 650_000), (-20.0, 30.0)), ((58.0, 20.0), (150_000, 450_000), (-20.0, 20.0)),
                                     ((47.5, -87.0), (200_000, 400_000), (165.0, 195.0))):
        lake = earth.lake_at(*place)
        assert lake is not None and lake["overflows"]
        assert area_km2[0] < lake["area_m2"] / 1e6 < area_km2[1] and level_m[0] < lake["level_m"] < level_m[1]


def test_open_water_under_the_caspians_sky_loses_about_a_metre_a_year(earth):
    """Found, then kept: what the demand for water gives for open water at the place of the Caspian, 800 to 1,100 mm
    a year (the engine: 936 mm over the whole lake [MEASURED]). The real sea loses about 1,000 mm a year
    [UNVERIFIED: from memory]."""
    air = earth.hydrology().fields["evapotranspiration"].astype(np.float64).sum(axis=0)[earth.cell(42.0, 51.0)]
    assert earth.hydrology().fields["lake_fraction"][earth.cell(42.0, 51.0)] == 1.0 and 800.0 < air < 1100.0


@missed("6.03 % of the land lies under lakes, 9.14 million km2. Twelve lakes larger than 100,000 km2 hold 54 % of it, where Earth "
        "has one of that size, the Caspian: the Caspian at three times its size, the basins of the Congo (880,226 km2) and of "
        "the Amazon (629,173) and the West Siberian plain (437,843), each behind a gorge or a low divide narrower than a cell, "
        "and the Black Sea and the Baltic, which are seas. [MEASURED]")
def test_lakes_cover_no_more_of_the_land_than_on_earth(earth):
    """Lakes larger than 0.002 km2 cover 3.7 % of Earth's land that is free of ice [DOCUMENTED at second hand:
    Verpoorter et al. 2014, as a page that reports the paper quotes it; the paper itself could not be opened]. The
    condition asks for under 4 % of the mesh's land. It was written with the engine's 6 % in view, as the
    statement of a pattern that the engine is known to miss."""
    f = earth.hydrology().fields
    flooded = (f["lake_fraction"].astype(np.float64) * earth.area).sum() / earth.area[earth.land].sum()
    assert flooded < 0.04, f"{100 * flooded:.1f} % of the land under lakes"


@missed("A lake of 880,226 km2 stands at 457 m in the basin of the Congo: the valley through which the real river leaves the "
        "basin toward Kinshasa is narrower than a cell, and its floor rises to 518 m on the mesh. [MEASURED]")
def test_the_basin_of_the_congo_holds_no_great_lake(earth):
    """The Congo drains its basin through a gorge to the Atlantic; no lake of any size lies at 3 S, 16.5 E."""
    lake = earth.lake_at(-3.0, 16.5)
    assert lake is None or lake["area_m2"] < 5.0e10, f"a lake of {lake['area_m2'] / 1e6:,.0f} km2"


# ---------------------------------------------------------------------------------------------- Biomes
def test_earths_measured_climate_falls_into_the_climate_classes_in_earths_shares(earth):
    """Set before the run: with CRU temperature and GPCP rain, each of the five main Köppen-Geiger groups takes a
    share of the land within 6 points of the share Peel, Finlayson and McMahon 2007 give [DOCUMENTED when build step
    2 was written]: arid B 30.2 %, cold D 24.6 %, tropical A 19.0 %, temperate C 13.4 %, polar E 12.8 %. The test
    compares five shares; the design asks for agreement with the published map, cell by cell, which needs the map."""
    out = earth.h.run("Biomes", reads={"surface_temperature": earth.celsius + 273.15, "precipitation": earth.rain, "ocean_mask": earth.wet})
    names = earth.h.registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[out.fields["climate_class"]]
    land_area = earth.area[earth.land].sum()
    for letter, share in (("A", 19.0), ("B", 30.2), ("C", 13.4), ("D", 24.6), ("E", 12.8)):
        found = 100.0 * earth.area[earth.land & (group == letter)].sum() / land_area
        assert abs(found - share) < 6.0, (letter, round(found, 1))


# ---------------------------------------------------------------------------------------------- the Earth twin
@pytest.fixture(scope="module")
def twin():
    """The whole engine on Earth's relief, on the preview mesh (10,242 cells about 240 km apart): only the heights are
    Earth's. tools/earth_twin.py builds the same world and prints it beside Earth."""
    models = ref.earth_twin_models(yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8")), get_mesh(5))
    e = Engine(DATA, profile="preview", overrides={"models": models, "explanations": ref.earth_twin_explanations(
        yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8")))})
    return e, e.build()


def _twin_numbers(twin):
    e, w = twin
    m, f = w.mesh, w.fields
    area = f["cell_area"].astype(np.float64)
    wet = f["ocean_mask"]
    celsius = f["surface_temperature"].astype(np.float64) - 273.15
    earth_celsius = ref.at_cell_centres(m, *ref.temperature_monthly())
    return m, f, area, wet, ~wet, celsius, earth_celsius


def test_on_earths_relief_the_engine_makes_earths_sea_a_climate_near_earths_mean_and_the_amazon(twin):
    """Found, then kept (first run of the twin): the sea stands within 60 m of Earth's level and covers 69 to 73 % of
    the planet; the mean temperature of the year is within 2 K of Earth's; the wettest land lies within 15 degrees
    of the equator; and the largest river of the twin reaches the sea within 800 km of the Amazon's mouth, with a
    flow within a factor of two of the Amazon's 210,000 m3/s."""
    e, w = twin
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    assert w.settled["climate"] and e.order()["geological"][0] == "Isostasy" and "Tectonics" not in e.order()["geological"]
    assert abs(w.tables["seas"]["surface_m"][0]) < 60.0 and 0.69 < area[wet].sum() / area.sum() < 0.73
    mean = lambda x, mask: (x * area)[mask].sum() / area[mask].sum()
    everywhere = np.ones(m.n, dtype=bool)
    assert abs(mean(celsius.mean(axis=0), everywhere) - mean(earth_celsius.mean(axis=0), everywhere)) < 2.0
    yearly = f["precipitation"].astype(np.float64).sum(axis=0)
    lat, land_rain = op.zonal_mean(m, yearly, 10.0, mask=land.astype(np.float64))
    assert abs(lat[np.nanargmax(land_rain)]) <= 15.0
    recv = f["flow_receiver"]
    coast = np.flatnonzero(land & (recv >= 0) & wet[np.maximum(recv, 0)])
    river = f["river_discharge"].astype(np.float64).mean(axis=0)
    largest = int(coast[np.argmax(river[coast])])
    a, b = np.deg2rad(-0.5), np.deg2rad(-50.0)
    mouth = np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])
    assert np.arccos(np.clip(m.xyz[largest] @ mouth, -1, 1)) * R / 1000.0 < 800.0
    assert 105_000.0 < river[largest] < 420_000.0


def test_the_twin_says_where_its_relief_comes_from(twin):
    """A world built on measured relief has no plates and no crust to explain its heights, and must not say it has."""
    from worldengine import store
    from worldengine.causes import as_text, explain
    e, w = twin
    view = store.MemoryView(w, e)
    m = w.mesh
    a, b = np.deg2rad(28.0), np.deg2rad(87.0)                                     # the Himalaya
    cell = int(np.argmax(m.xyz @ np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])))
    text = as_text(explain(view, cell, "elevation"))
    assert "Earth's measured relief" in text and "read from a file" in text
    assert "planet parameters and the mesh alone" not in text and "crust" not in text.split("\n", 2)[1]
    with pytest.raises(KeyError, match="the world holds no field named crust_thickness"):
        explain(view, cell, "crust_thickness")                # no process of this world writes the crust
    assert "Tectonics" not in w.lineage["elevation"]["model"] and "crust_thickness" not in w.lineage


@missed("13.4 K against Earth's 31.1 K [MEASURED]. The seasons of the engine's land are far too weak: its EnergyBalance spreads "
        "heat with one constant, which ties the land to the sea too tightly [INFERRED from runs of EnergyBalance alone: "
        "docs/BUILD_NOTES.md]. This is the largest known error of the climate.")
def test_northern_land_is_far_warmer_in_july_than_in_january_as_on_earth(twin):
    """Between 40 and 60 degrees north Earth's land is 31 K warmer in July than in January [MEASURED from the
    temperature data]. The condition: the twin's land reaches three quarters of that."""
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    north = land & (m.lat > 40) & (m.lat < 60)
    swing = ((celsius[6] - celsius[0]) * area)[north].sum() / area[north].sum()
    measured = ((earth_celsius[6] - earth_celsius[0]) * area)[north].sum() / area[north].sum()
    assert abs(measured - 31.0) < 2.0                         # Earth, from the temperature data
    assert swing > 0.75 * measured, f"{swing:.1f} K against {measured:.1f} K"


@missed("Group D takes 2.1 % of the twin's land, and the polar group E 46.3 % where Earth has 12.8 % [MEASURED]: with summers "
        "as weak as the test above measures, northern land that has warm summers on Earth stays under 10 C in its warmest "
        "month, and 35 % of the twin's land lies under snow in every month.")
def test_the_cold_climates_with_warm_summers_take_a_fifth_of_the_twins_land_as_on_earth(twin):
    """Group D of Köppen and Geiger takes 24.6 % of Earth's land (Peel, Finlayson and McMahon 2007). The condition:
    more than 15 % of the twin's."""
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    names = twin[0].registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[f["climate_class"]]
    share = area[land & (group == "D")].sum() / area[land].sum()
    assert share > 0.15, f"group D takes {100 * share:.1f} % of the twin's land"


def _twin_land_rain(twin):
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    yearly = f["precipitation"].astype(np.float64).sum(axis=0)
    lat, land_rain = op.zonal_mean(m, yearly, 5.0, mask=land.astype(np.float64))
    return m, land, yearly, lat, land_rain


@pytest.mark.parametrize("half", [pytest.param("north", marks=missed(
    "The twin's driest northern band lies at 58 degrees, with 273 mm a year, where Earth's own rain over the same cells is driest "
    "at 39 degrees [MEASURED]. The twin's northern land is too cold and so too dry: between 40 and 60 degrees it gets 440 mm "
    "against Earth's 654, and poleward of 60 degrees 181 mm against 495.")), "south"])
def test_on_the_twin_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40(twin, half):
    """The design's pass condition for rain, on the engine's own climate over Earth's land, where Earth itself
    meets it (the first test of this file)."""
    m, land, yearly, lat, land_rain = _twin_land_rain(twin)
    sign = 1 if half == "north" else -1
    side = (sign * lat > 0) & (sign * lat < 60) & ~np.isnan(land_rain)
    driest = sign * lat[side][np.argmin(land_rain[side])]
    assert 15 <= driest <= 40, f"the driest band lies at {driest:.0f} degrees, with {land_rain[side].min():.0f} mm"


@missed("440 mm a year against Earth's 654 mm [MEASURED]. The twin's land there is 7 K too cold in the yearly mean (2.0 C between "
        "30 and 60 degrees north, against 9.3 C), cold air holds little vapour, and ground under snow gives none back "
        "[INFERRED: the chain, not measured link by link].")
def test_the_twins_land_between_40_and_60_north_gets_the_rain_of_earths(twin):
    """Earth's rain, read at the same cells [MEASURED from GPCP]. The condition: the twin's land at 40 to 60 degrees
    north gets at least three quarters of it."""
    m, land, yearly, lat, land_rain = _twin_land_rain(twin)
    area = twin[1].fields["cell_area"].astype(np.float64)
    earth_rain = ref.at_cell_centres(m, *ref.rain_monthly()).sum(axis=0)
    north = land & (m.lat > 40) & (m.lat < 60)
    mine, earths = (yearly * area)[north].sum() / area[north].sum(), (earth_rain * area)[north].sum() / area[north].sum()
    assert mine > 0.75 * earths, f"{mine:.0f} mm against {earths:.0f} mm"
