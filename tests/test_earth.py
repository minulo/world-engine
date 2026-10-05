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
known misses.

What the rivers of these tests can and cannot show [MEASURED: python tools/earth_relief.py, python
tools/earth_rivers.py --settlements 20; docs/BUILD_NOTES.md, section 4.4]. Three things stand between the relief
data and a river, and none of them is the process under test:
  * The data. ETOPO5 holds closed hollows and closed valleys of its own, on its grid of 9 km: 13 % of what is not
    ocean lies under water when every hollow of the data is full, and five of six narrows of great rivers looked
    at are closed in the data themselves. A river that goes astray there says nothing about Drainage.
  * Exact ties. The data come in whole metres, half of the land in steps of 100 feet. On the mesh a third of the
    land cells have a neighbour at exactly their own height, and where heights tie the data cannot say which way
    a river runs. The tests settle ties as the engine does (the wider way), and beside it at random, SETTLEMENTS
    times. A river whose outcome changes with the settling is decided by the ties and not by anything measured;
    its reason says so, with the count.
  * The valley rule. A river runs along the floor of its valley, not at the mean height of the 60 km around it.
    The design asked for "relief converted so that valley floors survive"; here a land cell's height for
    drainage is the height below which a tenth of its land points lie (earth_reference.VALLEY_SHARE). The tenth
    was chosen when this file was first written and has not been tuned since. The rule keeps valley floors and
    loses the ridges between them: a cell that holds a shore and a range is handed in at the height of the shore.
A reason gives a cause only where one of the tools measures it. Where a river misses and no cause was measured,
the reason gives the numbers and says that the cause is not established.

The places are given to the nearest half degree from memory [UNVERIFIED]; the distances asked for are hundreds of
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


SETTLEMENTS = 20            # how often the exact ties of the relief are settled at random, beside the engine's own way


@pytest.fixture(scope="module")
def earth():
    return ref.Earth(LEVEL)


@pytest.fixture(scope="module")
def flood():
    """The closed hollows of the relief data on their own grid, before any mesh."""
    return ref.raw_flood()


@pytest.fixture(scope="module")
def outcomes(earth):
    """earth_reference.summary for the engine's own way of settling exact ties ("engine"), and for SETTLEMENTS ways
    drawn at random (seeds 1 to SETTLEMENTS)."""
    out = {"engine": ref.summary(earth)}
    for seed in range(1, SETTLEMENTS + 1):
        out[seed] = ref.summary(earth.settled(seed))
    return out


def drawn(outcomes):
    return [outcomes[seed] for seed in range(1, SETTLEMENTS + 1)]


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


STRAITS = {
    "the Black Sea": ((43.0, 34.0), "The relief data cut the Black Sea off themselves: on their own grid the Bosporus stands at 2 m above the sea. "
                                    "No mesh could join it to the ocean from these data. Hydrology fills it as a lake."),
    "the Red Sea": ((20.0, 38.5), "In the data the Red Sea is joined to the ocean; its strait is narrower than a cell and is closed on this mesh."),
    "the Baltic": ((58.0, 20.0), "In the data the Baltic is joined to the ocean; the straits of Denmark are narrower than a cell and are closed on "
                                 "this mesh. Hydrology fills it as a lake.")}


@pytest.mark.parametrize("name", [pytest.param(name, marks=missed(reason)) for name, (place, reason) in STRAITS.items()])
def test_a_sea_behind_a_narrow_strait_is_part_of_the_ocean(earth, name):
    """Stated as misses when the first run showed them. The reasons say where each sea is lost [MEASURED: the test
    below]."""
    assert earth.wet[earth.cell(*STRAITS[name][0])], name


def test_where_the_seas_behind_straits_are_lost(earth, flood):
    """Found, then kept: it keeps the reasons above true. The Black Sea is no part of the ocean in the data
    themselves: the lowest way from it to the ocean rises to 2 m. The Red Sea and the Baltic are ocean in the data
    and not sea on the mesh. The Caspian is cut off in both, as it should be: the data join it to the ocean at 91 m."""
    at = lambda name: ref.raw_at(flood, *STRAITS[name][0])
    assert not at("the Black Sea")["ocean"] and at("the Black Sea")["level"] == 2.0
    assert at("the Red Sea")["ocean"] and at("the Baltic")["ocean"]
    caspian = ref.raw_at(flood, *ref.CASPIAN)
    assert not caspian["ocean"] and caspian["level"] == 91.0 and caspian["height"] < -20.0
    assert not earth.wet[earth.cell(*ref.CASPIAN)]
    for place in ((35.0, 18.0), (60.0, -85.0), (40.0, 135.0)):                    # the Mediterranean, Hudson Bay, the Sea of Japan
        assert ref.raw_at(flood, *place)["ocean"] and earth.wet[earth.cell(*place)]


# ---------------------------------------------------------------------------------------------- Drainage
def test_the_amazon_reaches_the_atlantic_and_the_nile_the_mediterranean(earth, outcomes):
    """Set before the run (the design's own list): from Manaus the water reaches the sea within 600 km of the Amazon's
    mouth, and from Khartoum within 600 km of the Nile's. The bounds on the areas drained were written after the
    first run (found, then kept): the Amazon drains 5.85 million km2 [DOCUMENTED: Dai and Trenberth, Table 2, at the
    river mouth], the Nile about 3.3 million [UNVERIFIED: from memory].
    The condition asks where the water leaves the land, not by which way, and the Nile meets it by distance alone:
    the mesh's Nile leaves its valley near 22 degrees north, crosses the hollows of the Western Desert and reaches
    the coast 270 km west of the delta [MEASURED: python tools/earth_rivers.py --trace Nile; the last assertion]. In
    one of the 20 random settlements of the ties it does not come within 600 km."""
    basin = earth.drainage.fields["basin_id"]
    amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
    assert earth.km(amazon, -0.5, -50.0) < 600.0 and earth.km(nile, 31.5, 31.0) < 600.0
    area = earth.drainage.fields["drainage_area"]
    assert 4.5e12 < area[amazon] < 8.0e12 and 2.5e12 < area[nile] < 4.5e12        # m2
    assert sum(r["mouth_km"]["Amazon"] < 600.0 for r in drawn(outcomes)) == SETTLEMENTS
    assert sum(r["mouth_km"]["Nile"] < 600.0 for r in drawn(outcomes)) == SETTLEMENTS - 1
    desert = [c for c in ref.way_of(earth, "Nile") if 26.0 < c["lat"] < 30.0]
    assert desert and all(c["lon"] < 28.5 for c in desert)                        # the real river runs east of 30.5 E there


def test_central_asia_and_the_great_basin_are_closed_hollows(earth):
    """Set before the run (the design's own list): the Tarim basin and the Great Basin drain into closed hollows.
    Found, then kept: the Tarim's water collects within 400 km of Lop Nur, at 600 to 900 m."""
    f, t = earth.drainage.fields, earth.drainage.tables["hollows"]
    tarim, great_basin = earth.cell(39.0, 83.0), earth.cell(40.0, -116.5)
    assert f["depression_id"][tarim] > 0 and f["depression_id"][great_basin] > 0
    bottom = int(t["bottom_cell"][f["depression_id"][tarim]])
    assert earth.km(bottom, 40.2, 90.5) < 400.0 and 600.0 < t["bottom_m"][f["depression_id"][tarim]] < 900.0


# The rivers that do not leave the land within 300 km of their real mouths when the ties are settled as the engine
# settles them. Every number is measured: the distances by tools/earth_rivers.py (parts 3 and 7), the heights on the
# data's own grid by tools/earth_relief.py (part 3), the heights on the mesh by tools/earth_rivers.py (part 6), and what
# is said of a river's way by tools/earth_rivers.py --trace. The tests below keep them true: MOUTHS, NARROWS_ON_THE_MESH
# and NARROWS_IN_THE_DATA.
MISLED = {
    "Congo": "603 km as the engine settles ties, 668 to 738 km in 20 random settlements. The data close the river's valley "
             "themselves: on their own grid the valley from Bolobo to Kinshasa rises to 610 m, where the river above it "
             "stands at 274 m, and the basin is joined to the ocean at 457 m by another way. On the mesh the basin fills as a "
             "lake of 880,226 km2 to 457 m and overflows westward, to the sea at 1.5 degrees south.",
    "Ob": "633 km in every settlement. The mesh's river comes within 28 km of its real mouth, at the head of its estuary, and "
          "runs on: the Gulf of Ob is ocean in the data, 3 to 13 m deep, but the cells that hold it and its shores have mean "
          "heights of -7 to 8 m and are not sea on the mesh, whose sea stands at -5.3 m. The river follows the gulf as a lake "
          "to its seaward end.",
    "Danube": "1,212 km as the engine settles ties, 1,171 to 1,212 km in 20 random settlements. The data close the Iron Gate "
              "themselves: on their own grid the valley rises to 317 m, where the river above it stands at 98 m. On the mesh "
              "the valley rises to 208 m; the plain above it fills as a lake of 226,505 km2 to 177 m and overflows to the "
              "Adriatic, through a coastal cell whose mean height is 544 m and which the valley rule hands to Drainage at 0 m.",
    "Yenisei": "350 km in every settlement. Near 66 degrees north the mesh's river leaves its valley, runs west over ground "
               "that is level at 30 m in the heights handed to Drainage, and enters the estuary of the Ob, which is not sea "
               "on the mesh (see the Ob): it leaves the land with the Ob. Why it leaves its valley is not established.",
    "Volga": "1,865 km. Not a fault of the relief or of the mesh. The Volga ends in the Caspian, a closed sea, and this "
             "condition follows the water on as if every hollow were full: over the Caspian's rim, across the bed of the "
             "Black Sea and out to the Aegean. A river of a closed sea cannot meet the condition as it was written. Where the "
             "mesh's Volga ends is tested with the Caspian, below.",
    "St Lawrence": "1,090 km in every settlement. This one the mesh closes: in the data the estuary below Quebec is open to "
                   "the sea, but it is narrower than a cell, and on the mesh the valley's floor rises to 204 m. The river "
                   "above it fills a lake to 102 m, which overflows southward, by Lake Champlain and the Hudson.",
    "Amur": "1,274 km as the engine settles ties, up to 1,290 km in 20 random settlements. The data close the lower river "
            "themselves: on their own grid the valley below Komsomolsk rises to 213 m, where the river stands at 76 m, and the "
            "lowland above it is joined to the ocean at 122 m by a way south. On the mesh the valley rises to 137 m; the "
            "lowland fills as a lake of 180,651 km2 to 107 m and its water leaves south, to the Sea of Japan.",
    "Huang He": "1,261 km as the engine settles ties, and within 300 km in 2 of 20 random settlements: the ties decide. On the "
                "mesh the river's way to the sea crosses 47 cells under the water of full hollows and 4 of level ground, "
                "north-east over Mongolia and Manchuria, and leaves the land with the Amur's."}

# For every great river: how far from its real mouth it leaves the land when the ties are settled as the engine settles
# them (km), and in how many of the SETTLEMENTS random settlements it does so within 300 km.
MOUTHS = {"Amazon": (203, 20), "Nile": (270, 19), "Mississippi": (252, 20), "Congo": (603, 0), "Yangtze": (60, 6), "Ob": (633, 0),
          "Mackenzie": (83, 20), "Danube": (1212, 0), "Ganges": (26, 20), "Parana": (112, 20), "Niger": (142, 20), "Lena": (174, 20),
          "Yenisei": (350, 0), "Indus": (75, 20), "Murray": (133, 20), "Volga": (1865, 0), "Zambezi": (46, 20), "Orinoco": (245, 20),
          "St Lawrence": (1090, 0), "Columbia": (115, 20), "Rhine": (39, 20), "Mekong": (202, 20), "Amur": (1274, 0), "Huang He": (1261, 2)}

# Six narrows of great rivers. On the mesh: the height to which the valley's floor rises, and the level of the lake that
# stands above it. In the data, on their own grid of 5 minutes of arc: the height of the river above the narrows, the
# height to which its valley rises, and the level at which the place is joined to the ocean by any way (None: the place
# is open to the sea). Metres.
NARROWS_ON_THE_MESH = {"Congo": (518, 457), "Danube": (208, 177), "Lena": (137, 122), "St Lawrence": (204, 102), "Amur": (137, 107),
                       "Yangtze": (762, 381)}
NARROWS_IN_THE_DATA = {"Congo": (274, 610, 457), "Danube": (98, 317, 317), "Lena": (91, 152, 152), "St Lawrence": None,
                       "Amur": (76, 213, 122), "Yangtze": (404, 945, 823)}


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(MISLED[name])) if name in MISLED else name for name in ref.GREAT_RIVERS])
def test_a_great_river_reaches_the_sea_where_it_does_on_earth(earth, river):
    """Each of 24 great rivers, with every hollow on its way full, leaves the land within 300 km of its real mouth.
    The list of rivers and the 300 km were written before the first run; which rivers fail was found by it. The ties
    are settled as the engine settles them: 16 of the 24 pass, and each of the other 8 is an expected failure of its
    own, with its distance and what was measured about its cause. The condition asks where the water leaves the
    land and not by which way: the Yangtze, the Lena and the Nile meet it by ways that are not their valleys
    (python tools/earth_rivers.py --trace)."""
    place, mouth = ref.GREAT_RIVERS[river]
    km = earth.km(int(earth.drainage.fields["basin_id"][earth.cell(*place)]), *mouth)
    assert km < ref.MOUTH_WITHIN_KM, f"{river}: {km:.0f} km from its mouth"


def test_a_settlement_of_the_ties_reaches_drainage_and_hydrology_alike(earth):
    """Earth.settled(seed) must hand its ties to both processes: Hydrology settles the ways across its lakes, and if
    it kept the mesh's own ties while Drainage took the drawn ones, the two would disagree about where a lake's water
    goes and every "in 20 random settlements" of these tests would mean less than it says."""
    from worldengine.library import drainage as dr
    other = earth.settled(3)
    given = other._ties()
    surface, full = other.full_ways()
    assert np.array_equal(other.drainage.fields["flow_receiver"], dr.receivers(surface, earth.wet, earth.mesh.nbr, earth.ground, given))
    assert (other.drainage.fields["flow_receiver"] != earth.drainage.fields["flow_receiver"]).sum() > 1000      # the case: the draw changes many ways
    handed = other.books()["ties"]
    assert np.array_equal(handed.rank, given.rank) and np.array_equal(handed.edge, given.edge) and np.array_equal(handed.way, given.way)
    own = earth.books()["ties"]
    mesh = dr.mesh_ties(earth.mesh)
    assert np.array_equal(own.rank, mesh.rank) and np.array_equal(own.edge, mesh.edge)
    assert not np.array_equal(handed.edge, mesh.edge)
    # so the ways Hydrology takes across its lakes are Drainage's, wherever the lake fills its whole hollow
    ways = other.books()["flows"]["receivers"]
    lakes = other.hydrology().tables["lakes"]
    table = other.drainage.tables["hollows"]
    label = other.drainage.fields["depression_id"].astype(np.int64)
    top = dr.top_hollows(table)[label]
    brim = {int(k) for k, spills in zip(lakes["hollow"], lakes["overflows"]) if spills and table["parent"][int(k)] < 0}
    assert len(brim) > 50
    under = np.isin(top, sorted(brim)) & (surface <= table["spill_m"][top])
    assert under.sum() > 500 and np.array_equal(ways[under], full[under])


def test_what_the_ties_decide_about_the_mouths(earth, outcomes, flood):
    """Found, then kept: it keeps MOUTHS, the reasons in MISLED and docs/BUILD_NOTES.md true. A change to Drainage, or
    to the way Earth's relief is put on the mesh, that moves a mouth by more than 5 km, or changes in how many random
    settlements a river passes, fails here, and the records must then be measured again.
    Over the random settlements 15 to 17 rivers pass. Fourteen pass in every one and seven in none; three are decided
    by the ties: the Nile (19 of 20), the Yangtze (6) and the Huang He (2). The Yangtze passes as the engine settles
    ties: that pass is no more a finding than the Huang He's miss."""
    assert set(MOUTHS) == set(ref.GREAT_RIVERS)
    near = lambda r, river: r["mouth_km"][river] < ref.MOUTH_WITHIN_KM
    got = {river: (round(outcomes["engine"]["mouth_km"][river]), sum(near(r, river) for r in drawn(outcomes))) for river in MOUTHS}
    off = {river: got[river] for river in MOUTHS if abs(got[river][0] - MOUTHS[river][0]) > 5 or got[river][1] != MOUTHS[river][1]}
    assert not off, off
    counts = [sum(near(r, river) for river in MOUTHS) for r in drawn(outcomes)]
    assert (min(counts), max(counts)) == (15, 17) and sum(near(outcomes["engine"], river) for river in MOUTHS) == 16
    assert {river for river, (_, k) in MOUTHS.items() if 0 < k < SETTLEMENTS} == {"Nile", "Yangtze", "Huang He"}
    assert {river for river, (_, k) in MOUTHS.items() if k == 0} == set(MISLED) - {"Huang He"}
    # what the reasons say of the Ob's way: it reaches the head of its estuary, which the data have as ocean and the mesh has not
    assert min(c["km_to_mouth"] for c in ref.way_of(earth, "Ob") if c["step"] != "sea") < 60.0
    gulf = [(lat, 73.3) for lat in (67.5, 68.0, 69.0, 69.5, 70.0, 70.5, 71.0)]
    assert all(ref.raw_at(flood, *place)["ocean"] and -13.0 <= ref.raw_at(flood, *place)["height"] <= -3.0 for place in gulf)
    assert not any(earth.wet[earth.cell(*place)] for place in gulf)
    assert all(-7.5 < earth.mean[earth.cell(*place)] < 8.5 for place in gulf) and abs(earth.sea_level + 5.3) < 0.05
    # ... of the Yenisei's: level ground at 30 m, westward, between 66 and 67.5 north
    west = [c for c in ref.way_of(earth, "Yenisei") if 66.2 < c["lat"] < 67.2]
    assert len(west) >= 4 and all(c["step"] == "level" and c["ground_m"] == 30.0 for c in west)
    # ... and of the Huang He's
    way = [c for c in ref.way_of(earth, "Huang He") if c["step"] != "sea"]
    assert (sum(c["step"] == "lake" for c in way), sum(c["step"] == "level" for c in way)) == (47, 4)


def test_the_narrows_are_closed_in_the_data_before_the_mesh_closes_them(earth, flood):
    """Found, then kept: it keeps true what the reasons say about narrows. In each of six valleys the mesh's ground
    rises above the level of the lake that stands above the narrows; five of those lakes overflow by another way,
    and the sixth, in the Sichuan basin above the Three Gorges, keeps its water. But five of the six are closed in
    the relief data themselves, on their own grid of 9 km, where the valley rises far above the river. Only the
    estuary of the St Lawrence is open in the data and closed by the mesh.
    [The third check of build step 2 found this. I had laid all six to the mesh.]"""
    found = ref.narrows(earth)
    assert set(found) == set(NARROWS_ON_THE_MESH)
    for river, (barrier, lake) in NARROWS_ON_THE_MESH.items():
        r = found[river]
        assert abs(r["barrier_m"] - barrier) <= 1.0 and abs(r["lake_level_m"] - lake) <= 1.0, (river, r)
        assert r["barrier_m"] > r["lake_level_m"] and r["lake_overflows"] == (river != "Yangtze")
    raw = ref.raw_narrows(flood)
    for river, heights in NARROWS_IN_THE_DATA.items():
        r = raw[river]
        if heights is None:
            assert r["start_m"] < 0.0 and np.isnan(r["to_ocean_m"]), (river, r)   # the place itself is ocean in the data
        else:
            assert (r["start_m"], r["barrier_m"], r["to_ocean_m"]) == heights, (river, r)
            assert r["barrier_m"] > r["start_m"] + 50.0                           # closed, and by far more than a step of 100 feet
    # the Danube's water leaves through a range that the valley rule lowered to the height of the shore
    danube = found["Danube"]
    assert danube["over_mean_m"] > 500.0 and danube["handed_m"] == 0.0 and abs(danube["leaves_at"][1] - 14.2) < 0.5


def test_how_coarse_the_relief_is_and_what_settles_its_ties(earth):
    """Found, then kept: it keeps true what this file and docs/BUILD_NOTES.md say about the relief data and about
    ties. ETOPO5 is in whole metres, 48 % of its land in steps of 100 feet. On the mesh 35.8 % of the land cells
    have a land neighbour at exactly their own height. Of the land cells that have a lower neighbour, 23.0 % have
    several equally low: the bed settles a third of those (on coasts), the wider way two thirds, and the cell
    numbers 65 cells. With the wider way left out, as it was before the third check, the water of 15.5 % of the
    land reached the sea in another cell."""
    s = ref.relief_steps(earth)
    assert s["whole_metres"] and 0.45 < s["hundred_feet_share"] < 0.50
    assert (s["land_cells"], s["tied_cells"]) == (48733, 17454)
    assert [height for height, _ in s["commonest"][:2]] == [91.0, 61.0]
    assert (s["coast_cells"], s["coast_low"], s["coast_low_but_high"]) == (4646, 2078, 69)
    t = ref.tie_counts(earth)
    assert (t["choose"], t["tied"], t["by_bed"], t["by_width"], t["by_number"], t["level"]) == (42980, 9869, 3296, 6508, 65, 5063)
    assert t["mouth_moved_by_numbers"] < 0.001 and 0.14 < t["mouth_moved_by_width"] < 0.17


def test_the_data_hold_most_of_the_great_lakes_that_the_mesh_shows(earth, flood):
    """Found, then kept. Of all that is not ocean in the data, 13.3 % lies under water when every hollow of the data
    is full, on the data's own grid; on the mesh, with the valley rule, 10.2 %. The mesh does not add hollows to
    Earth's relief on the whole: the data bring them. Eleven of the mesh's twelve lakes larger than 100,000 km2 lie
    in hollows that the data hold as well; the twelfth is the Baltic, which the data join to the ocean. Some of the
    eleven are real (the Caspian, the Black Sea, the Great Lakes, whose beds the data give); the basins of the
    Congo, the Amazon and the Danube, the West Siberian plain and the lowlands of the Amur and the Lena are not."""
    r = ref.raw_hollows(flood)
    assert abs(r["not_ocean"] - 0.133) < 0.002 and abs(r["land"] - 0.126) < 0.002 and abs(r["ocean_share_of_planet"] - 0.711) < 0.002
    from worldengine.library import drainage as dr
    label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
    full = table["spill_m"][dr.top_hollows(table)[label]]
    under = earth.land & (label > 0) & (earth.ground < np.where(np.isnan(full), np.inf, full))
    assert abs(earth.area[under].sum() / earth.area[earth.land].sum() - 0.102) < 0.002
    lakes = earth.hydrology().tables["lakes"]
    big = np.flatnonzero(lakes["area_m2"] > 1.0e11)
    held = []
    for i in big:
        c = int(lakes["bottom_cell"][i])
        x = ref.raw_at(flood, float(earth.mesh.lat[c]), float(earth.mesh.lon[c]))
        held.append((not x["ocean"]) and x["level"] > x["height"])
    assert big.size == 12 and sum(held) == 11
    for place, height, level in (((-3.0, 16.5), 274.0, 457.0), ((0.0, -63.0), 30.0, 61.0), ((58.2, 68.4), 61.0, 91.0)):
        x = ref.raw_at(flood, *place)                                             # the Congo's basin, the Amazon's, West Siberia
        assert (x["height"], x["level"]) == (height, level), (place, x)


# ---------------------------------------------------------------------------------------------- Hydrology
def test_under_earths_rain_and_warmth_the_land_gives_back_what_earths_land_gives_back(earth, outcomes):
    """Set before the run: of the rain on land, between 0.50 and 0.75 goes back to the air, and 28,000 to 52,000 km3 a
    year reach the sea. Earth: 74 of 114 thousand km3 go back, 0.65, and 40 thousand reach the sea [DOCUMENTED when
    build step 2 was written: Trenberth, Fasullo and Mackaro 2011].
    The engine: 0.735 goes back and 31.7 thousand km3 reach the sea, of 119.8 thousand that GPCP's rain puts on the
    mesh's land [MEASURED: python tools/earth_rivers.py, part 5]. Inside the range, at its dry end: the land gives
    the air too much and the rivers too little. 0.706 would go back if no cell were flooded, and the lakes give the
    air the rest. These totals do not depend on how the ties are settled: over 20 random settlements 0.7350 to
    0.7352 and 31.71 to 31.74."""
    f = earth.hydrology().fields
    fell = (earth.rain.sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_sea = f["river_discharge"].astype(np.float64)[:, earth.wet].mean(axis=0).sum() * YEAR_S
    assert 0.50 < to_air / fell < 0.75
    assert 28.0e12 < to_sea < 52.0e12
    assert abs((fell - to_air) / to_sea - 1) < 1e-3            # and none is lost on the way
    assert not earth.hydrology().notices
    assert all(0.7345 < r["back_to_air"] < 0.7357 and 31.6 < r["to_sea"] < 31.8 for r in outcomes.values())
    from worldengine.library import drainage as dr
    assert dr.mesh_ties.__name__ == "mesh_ties"               # the settlements left the library as they found it


def test_the_amazon_carries_the_most_water(earth):
    """Set before the run: the largest flow into the sea lies within 800 km of the Amazon's mouth and is within a
    factor of two of the Amazon's: 6,642 km3 a year at its mouth, 210,000 m3/s [DOCUMENTED: Dai and Trenberth,
    Table 2]. Two things are asked, because two cells can be called the largest flow into the sea: the sea cell that
    receives the most (on the mesh one sea cell can take the water of two mouths), and the land cell that carries
    the most. The engine gives 161,911 and 145,456 m3/s [MEASURED]."""
    river = earth.hydrology().fields["river_discharge"].astype(np.float64).mean(axis=0)
    into_sea = int(np.argmax(np.where(earth.wet, river, -1.0)))
    on_land = int(np.argmax(np.where(earth.land, river, -1.0)))
    for cell in (into_sea, on_land):
        assert earth.km(cell, -0.5, -50.0) < 800.0
        assert 105_000.0 < river[cell] < 420_000.0
    assert earth.wet[earth.drainage.fields["flow_receiver"][on_land]]             # the largest river is at its mouth


# The rivers whose flow at the last gauge the engine misses by more than a factor of two, with the ties settled as the
# engine settles them. Each reason gives the flow, the land whose water reaches the gauge against the real basin, and
# what was measured about the cause [MEASURED: python tools/earth_rivers.py, parts 1, 2, 6 and 7; python
# tools/earth_relief.py, part 3]. "Like for like" is what the land sheds on the mesh's own river at the gauge where its
# basin is like the real one in size, over the depth measured (ALIKE below). AT_GAUGE holds the numbers of every river;
# a test keeps it true.
OFF_AT_GAUGE = {
    "Congo": "8 km3 a year against 1,271, in every settlement. The data close the river's valley above Kinshasa themselves "
             "(MISLED): the basin fills as a lake and its water leaves westward. Land of 50 thousand km2 reaches the gauge, of "
             "the real 3,475.",
    "Orinoco": "355 km3 a year against 984, in every settlement. Land of 563 thousand km2 reaches the gauge (836 on Earth), and "
               "it sheds 704 mm a year where 1,177 are measured: like for like 0.60.",
    "Yangtze": "127 km3 a year against 910, in every settlement. With every hollow full 1,567 thousand km2 drain to the gauge "
               "(1,705 on Earth), but only 839 reach it: the data close the Three Gorges themselves (their valley rises to "
               "945 m on the data's grid, where the river above stands at 404 m), and the lake that the Sichuan basin holds "
               "behind them keeps its water. And like for like the land sheds 115 mm a year where 534 are measured, 0.21: "
               "the rain on it, 1,151 mm, is hardly more than the demand for water the engine gives it, 1,141 mm.",
    "Brahmaputra": "273 km3 a year against 613, in every settlement. The basin is nearly right (507 thousand km2 reach the "
                   "gauge; 555 on Earth), but its land sheds 578 mm a year where 1,105 are measured. The rain handed to the "
                   "engine puts 1,565 mm a year on it; on its grid of 2.5 degrees it cannot hold the rain of the mountain "
                   "front [INFERRED].",
    "Yenisei": "77 km3 a year against 577 as the engine settles ties, and within a factor of two in 6 of 20 random "
               "settlements, with up to 731 km3: the ties decide. As the engine settles them the mesh's river leaves its "
               "valley south of the gauge (MISLED), and land of 201 thousand km2 reaches the gauge, of the real 2,440.",
    "Lena": "11 km3 a year against 526, in every settlement. The data close the valley above the delta themselves: on their "
            "own grid it rises to 152 m, where the river at Zhigansk stands at 91 m. On the mesh the lowland above fills as a "
            "lake of 150,490 km2 to 122 m, which overflows to the sea west of the delta and of the gauge. Land of 278 "
            "thousand km2 reaches the gauge, of the real 2,430.",
    "Mekong": "143 km3 a year against 292 as the engine settles ties; 31 to 143 in 20 random settlements, under half in every "
              "one. Land of 275 thousand km2 reaches the gauge, of the real 545. Seven of the 20 land cells on the river's way "
              "lie on level ground, where only the ties choose the way. The cause is not established.",
    "St Lawrence": "470 km3 a year against 226: too much, in every settlement. On the mesh land of 1,244 thousand km2 reaches "
                   "the gauge (774 on Earth), and it sheds 443 mm a year where 292 are measured: like for like 1.45.",
    "Amur": "26 km3 a year against 312, in every settlement. The data close the lower river themselves (MISLED), and its "
            "water leaves south to the Sea of Japan: land of 100 thousand km2 reaches the gauge, of the real 1,730.",
    "Mackenzie": "115 km3 a year against 288, in every settlement. The basin is right (1,740 thousand km2 reach the gauge; 1,660 "
                 "on Earth), but its land sheds 88 mm a year where 173 are measured, like for like 0.51, and lakes on the way "
                 "lose 37 km3 of that.",
    "Danube": "24 km3 a year against 202, in every settlement. The data close the Iron Gate themselves, and on the mesh the "
              "plain above it overflows to the Adriatic (MISLED): land of 145 thousand km2 reaches the gauge, of the real 807.",
    "Niger": "5 km3 a year against 33, in every settlement. Land of 116 thousand km2 reaches the gauge, of the real 1,516: "
             "closed lakes upstream keep the rest. Like for like the land sheds 8 mm a year where 22 are measured, 0.37.",
    "Zambezi": "11 km3 a year against 105, in every settlement. With every hollow full 2,016 thousand km2 drain to the gauge "
               "(940 on Earth), but only 233 reach it: closed lakes upstream keep the rest. That land sheds 71 mm a year where "
               "112 are measured.",
    "Indus": "No river at all within 150 km of the gauge, against 89 km3 a year, in every settlement. With every hollow full "
             "1,371 thousand km2 drain there (975 on Earth); closed lakes upstream keep all of it. Like for like the land sheds "
             "12 mm a year where 91 are measured, 0.13."}

# For every gauged river, with the ties settled as the engine settles them: the flow at the gauge (km3 a year) and the land
# whose water reaches it (thousand km2); and in how many of the SETTLEMENTS random settlements the flow is within a factor
# of two of the measured one.
AT_GAUGE = {"Amazon": (4515, 5921, 20), "Congo": (8, 50, 0), "Orinoco": (355, 563, 0), "Yangtze": (127, 839, 0), "Brahmaputra": (273, 507, 0),
            "Mississippi": (482, 2396, 20), "Yenisei": (77, 201, 6), "Parana": (480, 2987, 20), "Lena": (11, 278, 0), "Mekong": (143, 275, 0),
            "Ob": (604, 2865, 7), "Ganges": (273, 507, 20), "St Lawrence": (470, 1244, 0), "Amur": (26, 100, 0), "Mackenzie": (115, 1740, 0),
            "Columbia": (117, 484, 20), "Danube": (24, 145, 0), "Niger": (5, 116, 0), "Zambezi": (11, 233, 0), "Indus": (0, 69, 0),
            "Rhine": (84, 187, 20)}

# Like for like (earth_reference.like_for_like), with the ties settled as the engine settles them: for each gauged river
# whose basin on the mesh, with every hollow full, is within a factor of 1.5 of the real one's area, what its land sheds
# over the depth measured; and in how many of the SETTLEMENTS random settlements its basin is alike.
ALIKE = {"Amazon": (0.72, 20), "Orinoco": (0.60, 19), "Yangtze": (0.21, 20), "Brahmaputra": (0.23, 11), "Mississippi": (1.13, 20),
         "Parana": (0.78, 20), "Ob": (1.27, 7), "Ganges": (0.57, 20), "St Lawrence": (1.45, 20), "Mackenzie": (0.51, 20),
         "Columbia": (0.32, 20), "Niger": (0.37, 20), "Indus": (0.13, 20), "Rhine": (1.18, 20)}


@pytest.fixture(scope="module")
def gauges(earth):
    return ref.rivers_at_gauges(earth)


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(OFF_AT_GAUGE[name])) if name in OFF_AT_GAUGE else name for name in ref.GAUGES])
def test_a_great_river_carries_at_its_last_gauge_what_it_carries_on_earth(gauges, river):
    """Set before the run, and left as it was set: under Earth's rain and warmth, the largest yearly flow within 150 km
    of the station (the mesh may run the river through the next cell) is within a factor of two of the flow
    measured there [DOCUMENTED: Dai and Trenberth, Table 2; earth_reference.GAUGES]. With the ties settled as the
    engine settles them 7 of the 21 rivers pass, and each of the other 14 is an expected failure of its own.
    The test mixes two things: where the mesh runs the rivers, which the relief data and their ties mostly decide,
    and what the land sheds. The second is tested by itself below, like for like.
    The rule takes the largest flow near the station, whichever river carries it: for the Ganges that is the mesh's
    Brahmaputra, whose station lies 147 km from the Ganges's."""
    r = gauges[river]
    assert within_a_factor_of_two(r["measured"], r["flow"]), f"{river}: {r['flow']:.0f} km3 a year against {r['measured']:.0f}"


def within_a_factor_of_two(measured, flow):
    return measured / ref.FLOW_WITHIN < flow < measured * ref.FLOW_WITHIN


def test_what_the_ties_decide_about_the_gauges(gauges, outcomes):
    """Found, then kept: it keeps AT_GAUGE, the reasons in OFF_AT_GAUGE and docs/BUILD_NOTES.md true. A change that
    moves a flow or the land that reaches a gauge by more than 2 % (or by 1 km3, or 2 thousand km2), or changes in how
    many random settlements a river passes, fails here, and the records must then be measured again.
    Over the random settlements 6 or 7 rivers pass. Six pass in every one: the Amazon, the Mississippi, the Parana,
    the Ganges, the Columbia and the Rhine. Thirteen pass in none. Two are decided by the ties: the Yenisei (6 of
    20) and the Ob (7 of 20). The Ob passes as the engine settles ties: that pass is no finding."""
    assert set(AT_GAUGE) == set(ref.GAUGES)
    ok = lambda r, river: within_a_factor_of_two(ref.GAUGES[river][2], r["flow"][river])
    off = {}
    for river, (flow, reaches, passes) in AT_GAUGE.items():
        r = gauges[river]
        k = sum(ok(x, river) for x in drawn(outcomes))
        if abs(r["flow"] - flow) > max(0.02 * flow, 1.0) or abs(r["reaches"] - reaches) > max(0.02 * reaches, 2.0) or k != passes:
            off[river] = (round(r["flow"]), round(r["reaches"]), k)
    assert not off, off
    counts = [sum(ok(r, river) for river in AT_GAUGE) for r in drawn(outcomes)]
    assert (min(counts), max(counts)) == (6, 7) and sum(ok(outcomes["engine"], river) for river in AT_GAUGE) == 7
    assert {river for river, (_, _, k) in AT_GAUGE.items() if 0 < k < SETTLEMENTS} == {"Yenisei", "Ob"}
    assert {river for river, (_, _, k) in AT_GAUGE.items() if k == SETTLEMENTS} == {"Amazon", "Mississippi", "Parana", "Ganges", "Columbia", "Rhine"}
    assert gauges["Indus"]["no_river"] and not any(r["no_river"] for name, r in gauges.items() if name != "Indus")


def test_the_books_of_every_gauge_close(earth, gauges):
    """The flow at a gauge is the land whose water reaches it, times what that land sheds, less what the lakes with an
    outlet on the way lose. The three are worked out apart: the first two summed down the ways the water takes, the
    third from the yearly loss of each lake whose outlet lies upstream, and for a cell inside such a lake from the
    share of the passing water that the lake will lose. The flow is the field river_discharge. [The third check
    found that the third had been worked out as what was left over, so that this could not fail.]"""
    for river, r in gauges.items():
        assert abs(r["reaches"] * r["sheds"] / 1000.0 - r["lost_in_lakes"] - r["flow"]) < 1e-6 * max(r["flow"], 1.0) + 1e-4, (river, r)
        assert r["lost_in_lakes"] >= 0.0
    assert gauges["St Lawrence"]["lost_in_lakes"] > 50.0 and gauges["Amazon"]["lost_in_lakes"] > 200.0       # km3 a year: the case
    # the third part once more, the slow way: every cell upstream of the gauge is found by walking up the ways the water
    # takes, and the yearly losses of the lakes whose outlets lie among those cells are added up
    books = earth.books()
    ways = books["flows"]["receivers"]
    lakes = books["flows"]["lakes"]
    outlet = np.asarray(books["table"]["spill_from_cell"])[lakes["row"]]
    crossing = books["flows"]["crossing"]
    donors = {}
    for cell in np.flatnonzero(ways >= 0):
        donors.setdefault(int(ways[cell]), []).append(int(cell))
    for river in ("Amazon", "Mississippi", "Mackenzie", "Rhine"):
        r = gauges[river]
        assert crossing[r["cell"]] < 0 or r["cell"] in outlet                     # the gauge does not stand inside a lake's water
        above, todo = {r["cell"]}, [r["cell"]]
        while todo:
            for cell in donors.get(todo.pop(), ()):
                above.add(cell)
                todo.append(cell)
        lost = sum(loss for loss, runs, at in zip(lakes["loss"], lakes["overflows"], outlet) if runs and int(at) in above) / 1e9
        assert abs(lost - r["lost_in_lakes"]) < 1e-6 * max(lost, 1.0), (river, lost, r["lost_in_lakes"])
        assert abs(sum(float(earth.area[c]) for c in above if earth.land[c]) / 1e9 - r["reaches"]) < 1e-6 * r["reaches"]


@missed("Like for like, the engine's land sheds 0.68 of the depth measured over the fourteen basins that are alike (0.65 to "
        "0.72 in 20 random settlements): too little, and the same error that puts 31.7 thousand km3 a year into the sea where "
        "Earth's rivers carry 40. Basin by basin it runs from 0.13 (the Indus) to 1.45 (the St Lawrence), ten below 1 and "
        "four above. It is least where the rain comes in the warm season and nearly matches the demand the engine gives "
        "the air: the Yangtze 0.21, the Brahmaputra 0.23. The demand is too high over land because every cell gets the "
        "same share of sunshine [MEASURED over all land: docs/BUILD_NOTES.md, section 7, item 14; INFERRED for the "
        "single basins: there is no measured sunshine here to test it with]. [MEASURED: tools/earth_rivers.py, part 2]")
def test_like_for_like_the_land_of_the_great_basins_sheds_what_it_sheds_on_earth(outcomes):
    """Stated as a miss, with the number in view: over the basins that are alike in size, the engine's land sheds
    within 15 % of the depth measured. This is the test of what Hydrology makes of rain and warmth; where the
    rivers run does not enter it."""
    assert 0.85 < outcomes["engine"]["like_all"] < 1.15, f"{outcomes['engine']['like_all']:.2f} of the measured depth"


def test_what_the_land_sheds_like_for_like_basin_by_basin(outcomes):
    """Found, then kept: it keeps ALIKE and the reasons that quote it true. Fourteen basins are alike as the engine
    settles ties; nine of them shed within a factor of two of the measured depth."""
    like = outcomes["engine"]["like"]
    assert {river for river, (alike, _) in like.items() if alike} == set(ALIKE)
    off = {river: (round(like[river][1], 2), sum(r["like"][river][0] for r in drawn(outcomes))) for river, (ratio, k) in ALIKE.items()
           if abs(like[river][1] - ratio) > 0.02 or sum(r["like"][river][0] for r in drawn(outcomes)) != k}
    assert not off, off
    assert sum(0.5 < ratio < 2.0 for ratio, _ in ALIKE.values()) == 9 and sum(ratio < 1.0 for ratio, _ in ALIKE.values()) == 10
    assert abs(outcomes["engine"]["like_all"] - 0.68) < 0.01
    assert all(0.64 < r["like_all"] < 0.73 for r in drawn(outcomes))


@missed("As the engine settles ties the lake at the Caspian's place overflows, by 0.47 km3 of the 669 that reach it in a year. "
        "In 20 random settlements it stays closed in 5 and overflows in 15, by up to 6.9 km3: the lake stands at the brim "
        "of its hollow, and the ties decide whether a little runs over. What does not depend on the ties is its size: 1.09 "
        "to 1.11 million km2 at 60 to 61 m, where the real sea covers 371,000 to 436,000 km2 in the sources opened and "
        "stands 28 m below the ocean. The lake's books: rivers and shores bring it 588 km3 a year, about twice the 300 "
        "that reach the real sea [DOCUMENTED at second hand: the Volga 237 km3 a year, about 80 % of the inflow], off land "
        "of 4.06 million km2 where the real sea drains about 3 million; its water loses 936 mm a year and gets 408 mm of "
        "rain. Most of the excess is the Volga's. Over the land that drains through Volgograd the rain data hold 744 mm a "
        "year where 585 are published for the basin, and the engine sheds 342 mm where 193 are published. Handed the "
        "published 585 mm instead, the same land sheds 224 mm: four fifths of the river's excess come with the rain data, "
        "and a fifth is the model's [MEASURED; DOCUMENTED for the basin: Kalugin 2022]. The larger catchment adds to it. "
        "[MEASURED]")
def test_the_caspian_stays_a_closed_lake(earth):
    """Set before the run (the design's own list)."""
    lake = earth.lake_at(*ref.CASPIAN)
    assert lake is not None and not lake["overflows"]


def test_most_of_the_volgas_excess_comes_with_the_rain_data_and_a_fifth_is_the_models(earth, outcomes):
    """Found, then kept: it keeps the reason above and section 4.4 of the notes true. The Volga is the one basin for
    which a published precipitation is at hand beside the published runoff [DOCUMENTED: Kalugin 2022: 1,360,000 km2,
    585 mm, 262 km3 a year]. Like for like, the mesh's Volga at Volgograd sheds 1.8 times the published depth, and
    the rain data hold a quarter more over that land than is published, however the ties are settled. Handed the
    published precipitation instead (the rain data over that land, scaled by one factor in every month), the same
    land sheds 1.17 times the published depth: that part is the model's."""
    published_rain = ref.VOLGA["precipitation_mm"]
    published_runoff = 1000.0 * ref.VOLGA["gauge"][2] / ref.VOLGA["gauge"][3]
    assert abs(published_runoff - 192.6) < 0.1
    v = outcomes["engine"]["volga"]
    assert v["like"] and abs(v["basin"] - 1248.0) < 5.0 and abs(v["rain"] - 744.0) < 3.0 and abs(v["sheds"] - 342.0) < 3.0
    assert abs(v["ratio"] - 1.77) < 0.03
    for r in [outcomes["engine"]] + drawn(outcomes):
        v = r["volga"]
        assert v["like"], v
        assert 1.20 < v["rain"] / published_rain < 1.30, v                       # the rain data: a quarter more than published
        assert 1.6 < v["ratio"] < 1.9, v
    rain_before, water_before = earth.rain.copy(), earth.hydrology()
    both = ref.volga(earth)
    assert np.array_equal(earth.rain, rain_before) and earth.hydrology() is water_before     # the Earth of the tests is left as it was
    assert both["data"] == outcomes["engine"]["volga"]
    area = earth.area.astype(np.float64)
    assert abs(area[both["land"]].sum() / 1e9 - both["data"]["basin"]) < 1e-6 * both["data"]["basin"]      # the land that was handed the other rain
    p = both["published_rain"]
    assert p["cell"] == both["data"]["cell"] and abs(p["rain"] - published_rain) < 0.01
    assert abs(p["sheds"] - 224.5) < 3.0 and abs(p["ratio"] - 1.17) < 0.02       # the model's part: a sixth too much
    with_the_data = both["data"]["sheds"] - published_runoff
    assert 0.75 < (both["data"]["sheds"] - p["sheds"]) / with_the_data < 0.83    # four fifths of the excess come with the rain data


def test_what_the_ties_decide_about_the_caspian(earth, outcomes):
    """Found, then kept: it keeps the reason above true."""
    built = outcomes["engine"]["caspian"]
    assert built["overflows"] and abs(built["outflow_km3"] - 0.47) < 0.05 and abs(built["area_km2"] - 1_113_492) < 1_000 and built["level_m"] == 61.0
    there = [r["caspian"] for r in drawn(outcomes)]
    assert sum(not c["overflows"] for c in there) == 5 and 6.5 < max(c["outflow_km3"] for c in there) < 7.5
    assert all(1.09e6 < c["area_km2"] < 1.12e6 and 60.0 <= c["level_m"] <= 61.0 for c in there)
    lake = earth.lake_at(*ref.CASPIAN)
    brings = (lake["outflow_m3_per_year"] + lake["evaporation_m3_per_year"] - lake["rain_on_lake_m3_per_year"]) / 1e9
    assert abs(brings - 588.0) < 3.0 and abs(lake["inflow_m3_per_year"] / 1e9 - 669.0) < 3.0
    assert abs(1000.0 * lake["evaporation_m3_per_year"] / lake["area_m2"] - 936.0) < 3.0
    assert abs(1000.0 * lake["rain_on_lake_m3_per_year"] / lake["area_m2"] - 408.0) < 3.0


def test_seas_that_are_cut_off_and_the_great_lakes_come_back_as_lakes_near_their_real_size(earth):
    """Found, then kept. SeaLevel leaves the Black Sea and the Baltic dry: the data cut off the first, the mesh the
    second. Hydrology fills them again from Earth's rain: more water reaches each than its surface can lose, as on
    Earth, so each rises until it overflows. The Great Lakes appear too. The engine gives 472,814 km2 at 0 m,
    294,490 km2 at -1 m and 298,119 km2 at 179 m [MEASURED]. The sizes of Earth's seas and lakes are from memory
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
    a year (the engine: 1,003 mm at the place, 936 mm over the whole lake [MEASURED]). The real sea loses about
    1,000 mm a year [UNVERIFIED: from memory; one source opened gives 670 mm from a weather model's data, with a
    sea of 436,000 km2, numbers that do not balance its own inflow]."""
    air = earth.hydrology().fields["evapotranspiration"].astype(np.float64).sum(axis=0)[earth.cell(*ref.CASPIAN)]
    assert earth.hydrology().fields["lake_fraction"][earth.cell(*ref.CASPIAN)] == 1.0 and 800.0 < air < 1100.0


@missed("6.02 % of the land lies under lakes, 9.13 million km2, however the ties are settled. Twelve lakes larger than 100,000 "
        "km2 hold 54 % of it, where Earth has one of that size, the Caspian. Eleven of the twelve lie in hollows that the "
        "relief data hold on their own grid: the Caspian at three times its size, the Black Sea and the Great Lakes, which "
        "are real, and the basins of the Congo (880,226 km2), the Amazon (629,173) and the Danube, the West Siberian plain "
        "(437,843) and the lowlands of the Amur and the Lena, which the data close and Earth does not. The twelfth is the "
        "Baltic, which the mesh cuts off. [MEASURED: tools/earth_relief.py]")
def test_lakes_cover_no_more_of_the_land_than_on_earth(earth):
    """Lakes larger than 0.002 km2 cover 3.7 % of Earth's land that is free of ice [DOCUMENTED at second hand:
    Verpoorter et al. 2014, as a page that reports the paper quotes it; the paper itself could not be opened]. The
    condition asks for under 4 % of the mesh's land. It was written with the engine's 6 % in view, as the
    statement of a pattern that the engine is known to miss."""
    f = earth.hydrology().fields
    flooded = (f["lake_fraction"].astype(np.float64) * earth.area).sum() / earth.area[earth.land].sum()
    assert flooded < 0.04, f"{100 * flooded:.1f} % of the land under lakes"


@missed("A lake of 880,226 km2 stands at 457 m in the basin of the Congo. The relief data close the valley through which "
        "the real river leaves the basin: on their own grid it rises to 610 m, and the basin's floor, at 274 m, is joined to "
        "the ocean only at 457 m. [MEASURED: tools/earth_relief.py]")
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
