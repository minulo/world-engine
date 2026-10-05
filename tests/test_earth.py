"""Single processes, and the whole engine on Earth's relief, judged against patterns measured on Earth (design, Layer 9).

The first part hands one process inputs measured on Earth (relief, rain, temperature) and asks for a pattern that
an atlas shows: given the truth as its input, does the process return the truth as its output? Those runs are on
the standard mesh, 163,842 cells about 60 km apart. The last part builds the Earth twin, the whole engine on
Earth's relief, on the preview mesh (10,242 cells about 240 km apart). The data is fetched by
tools/fetch_reference_data.py; without it every test here is skipped.

What each condition is and where it comes from:
  * "the design's": the pattern stands in the design document's table of tests (Layer 9), which was written and
    approved before any code: the Amazon reaches the Atlantic and the Nile the Mediterranean, central Asia and
    the Great Basin are closed hollows, the Amazon carries the most water, the Caspian stays a closed lake, Earth's
    water on Earth's relief gives Earth's sea level and share of land, real temperature and rain give the
    Köppen-Geiger classes. The numbers that make a test of a pattern (how near, how much) are not in the design:
    they were chosen when the test was written. A design condition that the engine fails is NOT loosened: it
    stays as it was written and is marked as an expected failure, with the number measured.
  * "found, then kept": something that a run showed, or a condition written with its result in view. It guards
    against losing it, and proves less.
Every test of this file came into the repository together with its first results (commits f61f923 and 41e3423).
No record therefore shows that any number here was set before the process had been run on Earth's data. Earlier
versions of this file called several conditions "set before the run"; the fourth check of build step 2 found
that the history can verify that for none of them, and for the list of 24 river mouths the first commit says
"Found, then kept" itself. The label is gone.
An expected failure (xfail) states a pattern of Earth that the engine does not return, with the reason and the
number measured. It is strict and names its exception: if the engine starts to return the pattern, or the test
breaks for another reason, the run fails and the mark must go. Every pattern that a test of this file asks for and
the engine misses is written this way, and a test near each holds the numbers of its reason. The count of
expected failures is not the count of known misses: docs/BUILD_NOTES.md lists misses that no test states (the
lake at the Caspian's place at two and a half to three times the real sea's size, three rivers that meet their
condition by ways that are not their valleys, the twin's far south 7 K too warm).

What the rivers of these tests can and cannot show [MEASURED: python tools/earth_relief.py, python
tools/earth_rivers.py --settlements 20; docs/BUILD_NOTES.md, section 4.4]. Three things stand between the relief
data and a river, and none of them is the process under test:
  * The data. ETOPO5 holds closed hollows and closed valleys of its own, on its grid of 9 km: 13 % of what is not
    ocean lies under water when every hollow of the data is full, and five of six narrows of great rivers looked
    at are closed in the data themselves. A river that goes astray there says nothing about Drainage.
  * Exact ties. The data come in whole metres, half of the land in steps of 100 feet. On the mesh a third of the
    land cells have a neighbour at exactly their own height, and where heights tie the data cannot say which way
    a river runs. The tests settle ties as the engine does (the wider way), and beside it at random, SETTLEMENTS
    times: a random settlement draws everything that the heights leave open (the width of every way, the order
    of the cells, and which of several passes of one height is taken). A river whose outcome changes with the
    settling is decided by the ties and not by anything measured; its reason says so, with the count. A count is
    of the draws made: "in none of 20" rules out only what comes more often than about one time in seven. The
    counts of 100 draws are in docs/BUILD_NOTES.md, section 4.4 (python tools/earth_rivers.py --settlements 100);
    no test holds those. As the engine settles ties is one settlement among many, with no better claim to be
    Earth's than a random one: where the two disagree, the engine's outcome is no finding either way.
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
from conftest import DATA, tool
from worldengine.engine import Engine
from worldengine.library import operators as op
from worldengine.mesh import get_mesh

pytestmark = pytest.mark.skipif(not ref.available(), reason="the Earth reference data is not here: run python tools/fetch_reference_data.py")

R = ref.EARTH_RADIUS_M
YEAR_S = ref.YEAR_S
LEVEL = 7
missed = lambda reason: pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)


SETTLEMENTS = 20            # how often the exact ties of the relief are settled at random, beside the engine's own way
LEVEL_WITH_THE_WATER = 1722 # land cells whose ground lies exactly at the level to which the hollow around them fills


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
    """The design's: Earth's water on Earth's relief returns Earth's sea level and Earth's share of land. The bounds
    were chosen when the test was written: the sea level within 60 m of zero, the sea over 69 to 73 % of the
    planet, one ocean. The volume poured is the planet file's, 1.335e18 m3 [DOCUMENTED there]; ETOPO5's own sea
    holds 0.23 % more [MEASURED by the reviewer of build step 2], about 8 m of sea level. The lists of places below
    were written with the first run in view: found, then kept."""
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
    "the Black Sea": ((43.0, 34.0), "The relief data cut the Black Sea off themselves: on their own grid the lowest way from it to the ocean "
                                    "rises to 2 m above the sea [MEASURED]. A mesh that follows these data cannot join it to the ocean "
                                    "[INFERRED]. Hydrology fills it as a lake."),
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
    """The design's: the Amazon reaches the Atlantic and the Nile the Mediterranean. Chosen when the test was written:
    that it is asked from Manaus and from Khartoum, and that "reaches" means within 600 km of the river's mouth.
    The bounds on the areas drained were written after the first run (found, then kept): the Amazon drains 5.85
    million km2 [DOCUMENTED: Dai and Trenberth, Table 2, at the river mouth], the Nile about 3.3 million
    [UNVERIFIED: from memory].
    The Amazon meets it however the ties are settled. The Nile meets it as the engine settles them, and in 10 of
    20 random settlements: the ties decide, and the pass is no finding. It meets it by distance alone: the mesh's
    Nile leaves its valley near 22 degrees north, crosses the hollows of the Western Desert and reaches the coast
    270 km west of the delta [MEASURED: python tools/earth_rivers.py --trace Nile; the last assertion]."""
    basin = earth.drainage.fields["basin_id"]
    amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
    assert earth.km(amazon, -0.5, -50.0) < 600.0 and earth.km(nile, 31.5, 31.0) < 600.0
    area = earth.drainage.fields["drainage_area"]
    assert 4.5e12 < area[amazon] < 8.0e12 and 2.5e12 < area[nile] < 4.5e12        # m2
    assert sum(r["mouth_km"]["Amazon"] < 600.0 for r in drawn(outcomes)) == SETTLEMENTS
    assert sum(r["mouth_km"]["Nile"] < 600.0 for r in drawn(outcomes)) == 10
    desert = [c for c in ref.way_of(earth, "Nile") if 26.0 < c["lat"] < 30.0]
    assert desert and all(c["lon"] < 28.5 for c in desert)                        # the real river runs east of 30.5 E there


def test_central_asia_and_the_great_basin_are_closed_hollows(earth):
    """The design's: central Asia and the Great Basin are found as closed hollows. Chosen when the test was written:
    the two places asked. Found, then kept: the Tarim's water collects within 400 km of Lop Nur, at 600 to 900 m."""
    f, t = earth.drainage.fields, earth.drainage.tables["hollows"]
    tarim, great_basin = earth.cell(39.0, 83.0), earth.cell(40.0, -116.5)
    assert f["depression_id"][tarim] > 0 and f["depression_id"][great_basin] > 0
    bottom = int(t["bottom_cell"][f["depression_id"][tarim]])
    assert earth.km(bottom, 40.2, 90.5) < 400.0 and 600.0 < t["bottom_m"][f["depression_id"][tarim]] < 900.0


# The rivers that do not leave the land within 300 km of their real mouths when the ties are settled as the engine
# settles them. Every number is measured: the distances by tools/earth_rivers.py (parts 3 and 7), the heights on the
# data's own grid by tools/earth_relief.py (part 3), the heights on the mesh by tools/earth_rivers.py (part 6), and what
# is said of a river's way by tools/earth_rivers.py --trace. The tests below keep them true: MOUTHS, NARROWS_ON_THE_MESH
# and NARROWS_IN_THE_DATA. "In none of 20" and the like are counts of 20 random settlements of the ties.
MISLED = {
    "Congo": "603 km as the engine settles ties, 668 to 738 km in 20 random settlements, within 300 km in none. The data close "
             "the river's valley themselves: on their own grid the valley from Bolobo to Kinshasa rises to 610 m, where the "
             "river above it stands at 274 m, and the basin is joined to the ocean at 457 m by another way. On the mesh the "
             "basin fills as a lake of 880,226 km2 to 457 m and overflows westward, to the sea at 1.5 degrees south.",
    "Ob": "633 km as the engine settles ties, 633 to 734 km in 20 random settlements, within 300 km in none. The mesh's river "
          "comes within 28 km of its real mouth, at the head of its estuary, and runs on: the Gulf of Ob is ocean in the data, "
          "3 to 13 m deep, but the cells that hold it and its shores have mean heights of -7 to 8 m and are not sea on the "
          "mesh, whose sea stands at -5.3 m. The river follows the gulf as a lake to its seaward end.",
    "Danube": "1,212 km as the engine settles ties, 1,171 to 1,212 km in 20 random settlements. The data close the Iron Gate "
              "themselves: on their own grid the valley rises to 317 m, where the river above it stands at 98 m. On the mesh "
              "the valley rises to 208 m; the plain above it fills as a lake of 226,505 km2 to 177 m and overflows to the "
              "Adriatic, through a coastal cell whose mean height is 544 m and which the valley rule hands to Drainage at 0 m.",
    "Yenisei": "350 km as the engine settles ties, and within 300 km in 1 of 20 random settlements: the ties decide, and mostly "
               "against the river. Near 66 degrees north the mesh's river leaves its valley, runs west over ground that is "
               "level at 30 m in the heights handed to Drainage, and enters the estuary of the Ob, which is not sea on the "
               "mesh (see the Ob): it leaves the land with the Ob. On level ground nothing but the ties chooses the way.",
    "Volga": "1,865 km, however the ties are settled. Not a fault of the relief or of the mesh. The Volga ends in the Caspian, "
             "a closed sea, and this condition follows the water on as if every hollow were full: over the Caspian's rim, "
             "across the bed of the Black Sea and out to the Aegean. A river of a closed sea cannot meet the condition as it "
             "was written. Where the mesh's Volga ends is tested with the Caspian, below.",
    "St Lawrence": "1,090 km in every one of 20 random settlements. In the data the estuary below Quebec is open to the sea. It "
                   "is closed by the way the relief is put on the mesh: two of the cells that hold the estuary are land on "
                   "the mesh by their mean heights though 62 % and 32 % of their points are ocean in the data, and the valley "
                   "rule gives a land cell the height of its land points alone, 162 and 204 m. The river above fills a lake "
                   "to 102 m, which overflows southward, by Lake Champlain and the Hudson. With every point of a cell counted "
                   "the valley is open and the river leaves the land 32 km from its mouth; that reading floods 11.5 % of the "
                   "land and is no better rule.",
    "Amur": "1,274 km as the engine settles ties, up to 1,290 km in 20 random settlements. The data close the lower river "
            "themselves: on their own grid the valley below Komsomolsk rises to 213 m, where the river stands at 76 m, and the "
            "lowland above it is joined to the ocean at 122 m by a way south. On the mesh the valley rises to 137 m; the "
            "lowland fills as a lake of 180,651 km2 to 107 m and its water leaves south, to the Sea of Japan.",
    "Huang He": "1,261 km as the engine settles ties, and within 300 km in 14 of 20 random settlements: the ties decide, and "
                "the engine's way of settling them gives the rarer outcome. On the mesh, as the engine settles ties, the "
                "river's way to the sea crosses 48 cells under the water of full hollows and 4 of level ground, north-east "
                "over Mongolia and Manchuria, and leaves the land with the Amur's."}

# For every great river: how far from its real mouth it leaves the land when the ties are settled as the engine settles
# them (km), and in how many of the SETTLEMENTS random settlements it does so within 300 km.
MOUTHS = {"Amazon": (203, 20), "Nile": (270, 10), "Mississippi": (252, 20), "Congo": (603, 0), "Yangtze": (60, 6), "Ob": (633, 0),
          "Mackenzie": (83, 20), "Danube": (1212, 0), "Ganges": (26, 20), "Parana": (112, 20), "Niger": (142, 20), "Lena": (174, 20),
          "Yenisei": (350, 1), "Indus": (75, 20), "Murray": (133, 20), "Volga": (1865, 0), "Zambezi": (46, 20), "Orinoco": (245, 20),
          "St Lawrence": (1090, 0), "Columbia": (115, 20), "Rhine": (39, 20), "Mekong": (202, 20), "Amur": (1274, 0), "Huang He": (1261, 14)}

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
    Found, then kept: the test came into the repository together with its first results, under the name
    test_two_thirds_of_the_great_rivers_reach_the_sea_where_they_do_on_earth, and no record shows the list of
    rivers or the 300 km set before a run. Neither has been changed since. The ties are settled as the engine
    settles them: 16 of the 24 pass, and each of the other 8 is an expected failure of its own, with its distance
    and what was measured about its cause. Four of the 24 are decided by the ties, two of them among the 16 that
    pass (the Nile and the Yangtze) and two among the 8 that fail (the Yenisei and the Huang He): for those four
    neither the pass nor the failure is a finding (MOUTHS, and the test after the next). The condition asks where
    the water leaves the land and not by which way: the Yangtze, the Lena and the Nile meet it by ways that are
    not their valleys (python tools/earth_rivers.py --trace)."""
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
    In a random settlement 14 to 17 rivers pass. Fourteen pass in all 20 and six in none; four are decided by the
    ties: the Nile (10 of 20), the Yangtze (6), the Yenisei (1) and the Huang He (14). The Nile and the Yangtze pass
    as the engine settles ties, the Yenisei and the Huang He fail: none of the four is a finding.
    [Until the fourth check of build step 2 the random settlements drew the widths and the order of the cells and
    left the choice among passes of one height as the engine makes it. The counts were then 19, 6, 0 and 2, and
    read as if the ties decided little: they decide more.]"""
    assert set(MOUTHS) == set(ref.GREAT_RIVERS)
    near = lambda r, river: r["mouth_km"][river] < ref.MOUTH_WITHIN_KM
    got = {river: (round(outcomes["engine"]["mouth_km"][river]), sum(near(r, river) for r in drawn(outcomes))) for river in MOUTHS}
    off = {river: got[river] for river in MOUTHS if abs(got[river][0] - MOUTHS[river][0]) > 5 or got[river][1] != MOUTHS[river][1]}
    assert not off, off
    counts = [sum(near(r, river) for river in MOUTHS) for r in drawn(outcomes)]
    assert (min(counts), max(counts)) == (14, 17) and sum(near(outcomes["engine"], river) for river in MOUTHS) == 16
    assert {river for river, (_, k) in MOUTHS.items() if 0 < k < SETTLEMENTS} == {"Nile", "Yangtze", "Yenisei", "Huang He"}
    assert {river for river, (_, k) in MOUTHS.items() if k == 0} == set(MISLED) - {"Huang He", "Yenisei"}
    assert sum(k == SETTLEMENTS for _, k in MOUTHS.values()) == 14 and sum(k == 0 for _, k in MOUTHS.values()) == 6
    spread = lambda river: (min(r["mouth_km"][river] for r in drawn(outcomes)), max(r["mouth_km"][river] for r in drawn(outcomes)))
    for river, (low, high) in {"Congo": (668, 738), "Ob": (633, 734), "Danube": (1171, 1212), "Amur": (1274, 1290), "St Lawrence": (1090, 1090),
                               "Volga": (1865, 1865), "Huang He": (64, 1261), "Nile": (270, 2400)}.items():      # what the reasons quote
        assert abs(spread(river)[0] - low) < 5 and abs(spread(river)[1] - high) < 5, (river, spread(river))
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
    assert (sum(c["step"] == "lake" for c in way), sum(c["step"] == "level" for c in way)) == (48, 4)


def test_the_narrows_are_closed_in_the_data_before_the_mesh_closes_them(earth, flood):
    """Found, then kept: it keeps true what the reasons say about narrows. In each of six valleys the mesh's ground
    rises above the level of the lake that stands above the narrows; five of those lakes overflow by another way,
    and the sixth, in the Sichuan basin above the Three Gorges, keeps its water. But five of the six are closed in
    the relief data themselves, on their own grid of 9 km, where the valley rises far above the river. Only the
    estuary of the St Lawrence is open in the data and closed on the mesh, and what closes it there is the valley
    rule of the harness, not the width of a cell (the test after this one).
    [The third check of build step 2 found the first. I had laid all six to the mesh. The fourth found the second:
    I had laid the St Lawrence to the mesh's spacing.]"""
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


def test_the_estuary_of_the_st_lawrence_is_closed_by_the_valley_rule_and_not_by_the_width_of_a_cell(earth, flood):
    """Found, then kept: it keeps the St Lawrence's reason in MISLED and docs/BUILD_NOTES.md, section 4.5, true.
    A cell is sea on the mesh if its mean height lies below the sea. A cell that holds an arm of the sea between
    high shores is therefore land, and the valley rule hands it to Drainage at the height below which a tenth of
    its points ABOVE the sea lie: the water in it is left out. Two such cells stand in the St Lawrence's way. With
    every point counted, the valley is open and the river leaves the land near its mouth. That other reading is
    kept as a diagnosis and not taken as the rule: it lays 4,008 land cells at or below the sea's level (388 as
    built) and floods 11.5 % of the land."""
    held = ref.data_points_of_cells(earth, flood)
    share, land = held["ocean_share"], earth.land
    assert share.min() >= 0.0 and share.max() <= 1.0 and share[earth.cell(*ref.OPEN_OCEAN)] == 1.0 and share[earth.cell(33.0, 88.0)] == 0.0
    closing = [earth.cell(47.3, -70.6), earth.cell(47.4, -69.9)]                  # two cells on the estuary below Quebec
    assert [(bool(land[c]), round(float(earth.ground[c])), round(100 * float(share[c]))) for c in closing] == [(True, 162, 62), (True, 204, 32)]
    assert all(earth.mean[c] > 150.0 for c in closing)                           # land by their mean heights, with half their points in the sea
    built = ref.narrows(earth)["St Lawrence"]
    assert built["barrier_m"] == 204.0 and built["lake_level_m"] == 102.0 and abs(built["barrier_at"][0] - 47.4) < 0.1
    much = land & (share >= 0.1)
    assert (int(much.sum()), int((much & (earth.ground > 10.0)).sum()), int((much & (earth.ground > 100.0)).sum())) == (3951, 1240, 590)
    ground_before, drainage_before = earth.ground.copy(), earth.drainage
    other = earth.with_ground(held["every_point"])
    assert np.array_equal(earth.ground, ground_before) and earth.drainage is drainage_before      # the Earth of the tests is left as it was
    assert [round(float(other.ground[c])) for c in closing] == [-10, -10]
    place, mouth = ref.GREAT_RIVERS["St Lawrence"]
    leaves = lambda e: e.km(int(e.drainage.fields["basin_id"][e.cell(*place)]), *mouth)
    assert abs(leaves(earth) - 1090.0) < 5.0 and abs(leaves(other) - 32.0) < 5.0
    opened = ref.narrows(other)["St Lawrence"]
    assert opened["barrier_m"] == 84.0 and opened["lake_level_m"] is None       # the valley rises no higher than the place the river starts from
    assert (int((land & (earth.ground <= earth.sea_level)).sum()), int((land & (other.ground <= earth.sea_level)).sum())) == (388, 4008)
    assert abs(ref.land_water(other)["lakes_share"] - 0.115) < 0.002 and abs(ref.land_water(earth)["lakes_share"] - 0.060) < 0.002


def test_how_coarse_the_relief_is_and_what_settles_its_ties(earth):
    """Found, then kept: it keeps true what this file and docs/BUILD_NOTES.md say about the relief data and about
    ties. ETOPO5 is in whole metres, 48 % of its land in steps of 100 feet. On the mesh 35.8 % of the land cells
    have a land neighbour at exactly their own height. Of the land cells that have a lower neighbour, 23.0 % have
    several equally low: the bed settles a third of those (on coasts), the wider way two thirds, and the cell
    numbers 52 cells. With the wider way left out, as it was before the third check, the water of 15.5 % of the
    land reached the sea in another cell; with the order of the cells turned round, as things stand, of 0.03 %.
    [The numbers 6,521 and 52 were 6,508 and 65 while the widths of the ways were rounded to settle their ties:
    thirteen ties between mirror images of one boundary were then left to the cell numbers.]"""
    s = ref.relief_steps(earth)
    assert s["whole_metres"] and 0.45 < s["hundred_feet_share"] < 0.50
    assert (s["land_cells"], s["tied_cells"]) == (48733, 17454)
    assert [height for height, _ in s["commonest"][:2]] == [91.0, 61.0]
    assert (s["coast_cells"], s["coast_low"], s["coast_low_but_high"]) == (4646, 2078, 69)
    t = ref.tie_counts(earth)
    assert (t["choose"], t["tied"], t["by_bed"], t["by_width"], t["by_number"], t["level"]) == (42980, 9869, 3296, 6521, 52, 5063)
    assert 0.0002 < t["mouth_moved_by_numbers"] < 0.0005 and 0.14 < t["mouth_moved_by_width"] < 0.17     # (a measure that measured nothing would give 0)


def test_the_data_hold_most_of_the_great_lakes_that_the_mesh_shows(earth, flood):
    """Found, then kept. Of all that is not ocean in the data, 13.3 % lies under water when every hollow of the data
    is full, on the data's own grid; on the mesh, with the valley rule, 10.2 %. The mesh does not add hollows to
    Earth's relief on the whole: the data bring them. Eleven of the mesh's twelve lakes larger than 100,000 km2 lie
    in hollows that the data hold as well; the twelfth is the Baltic, which the data join to the ocean. Some of the
    eleven are real (the Caspian, the Black Sea, the Great Lakes, whose beds the data give); the basins of the
    Congo, the Amazon and the Danube, the West Siberian plain and the lowlands of the Amur and the Lena are not
    [UNVERIFIED, from memory, which of them hold lakes on Earth]."""
    r = ref.raw_hollows(flood)
    assert abs(r["not_ocean"] - 0.133) < 0.002 and abs(r["land"] - 0.126) < 0.002 and abs(r["ocean_share_of_planet"] - 0.711) < 0.002
    from worldengine.library import drainage as dr
    label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
    full = table["spill_m"][dr.top_hollows(table)[label]]
    under = earth.land & (label > 0) & (earth.ground < np.where(np.isnan(full), np.inf, full))
    assert abs(earth.area[under].sum() / earth.area[earth.land].sum() - 0.102) < 0.002
    # the same from the harness, which the tools print: "under water" is ground below the level, as in the data's own count
    # (level > height). Ground exactly at the level is another 3.6 % of the land on this relief of whole metres, and is not counted
    h = ref.mesh_hollows(earth)
    assert np.array_equal(h["under"], under) and int(under.sum()) == 4898
    level_with = earth.land & (label > 0) & (earth.ground == np.where(np.isnan(full), np.inf, full))
    assert int(level_with.sum()) == LEVEL_WITH_THE_WATER and abs(h["under_share"] - 0.1021) < 0.0005 and abs(h["under_share_60"] - 0.1156) < 0.0005
    assert abs(h["not_sea_share"] - 0.2972) < 0.0005 and abs(h["closed_hollow_share"] - 0.6055) < 0.0005
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
    """The bounds were chosen when the test was written: of the rain on land, between 0.50 and 0.75 goes back to the air,
    and 28,000 to 52,000 km3 a year reach the sea. Earth: 74 of 114 thousand km3 go back, 0.65, and 40 thousand
    reach the sea [DOCUMENTED when build step 2 was written: Trenberth, Fasullo and Mackaro 2011].
    The engine: 0.735 goes back and 31.7 thousand km3 reach the sea, of 119.8 thousand that GPCP's rain puts on the
    mesh's land [MEASURED: python tools/earth_rivers.py, part 5]. Inside the range, at its dry end: the land gives
    the air too much and the rivers too little. 0.706 would go back if no cell were flooded, and the lakes give the
    air the rest. These totals hardly depend on how the ties are settled: over 20 random settlements 0.7347 to
    0.7352 and 31.72 to 31.77."""
    f = earth.hydrology().fields
    fell = (earth.rain.sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_sea = f["river_discharge"].astype(np.float64)[:, earth.wet].mean(axis=0).sum() * YEAR_S
    assert 0.50 < to_air / fell < 0.75
    assert 28.0e12 < to_sea < 52.0e12
    assert abs((fell - to_air) / to_sea - 1) < 1e-3            # and none is lost on the way
    assert not earth.hydrology().notices
    assert all(0.7343 < r["back_to_air"] < 0.7357 and 31.65 < r["to_sea"] < 31.82 for r in outcomes.values())
    from worldengine.library import drainage as dr
    assert dr.mesh_ties.__name__ == "mesh_ties"               # the settlements left the library as they found it


def test_the_amazon_carries_the_most_water(earth):
    """The design's: the Amazon carries the most water. Chosen when the test was written: that the largest flow into
    the sea lies within 800 km of the Amazon's mouth and is within a factor of two of the Amazon's, 6,642 km3 a
    year at its mouth, 210,000 m3/s [DOCUMENTED: Dai and Trenberth, Table 2]. Two things are asked, because two
    cells can be called the largest flow into the sea: the sea cell that receives the most (on the mesh one sea
    cell can take the water of two mouths), and the land cell that carries the most. The engine gives 161,911 and
    145,456 m3/s [MEASURED]."""
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
# a test keeps it true. "In none of 20" and the like are counts of 20 random settlements of the ties.
OFF_AT_GAUGE = {
    "Congo": "8 km3 a year against 1,271, and within a factor of two in none of 20 random settlements. The data close the "
             "river's valley above Kinshasa themselves (MISLED): the basin fills as a lake and its water leaves westward. "
             "Land of 50 thousand km2 reaches the gauge, of the real 3,475.",
    "Orinoco": "355 km3 a year against 984 as the engine settles ties; 350 to 606 in 20 random settlements, within a factor of "
               "two in 2: the ties decide, and mostly against the river. As the engine settles them, land of 563 thousand km2 "
               "reaches the gauge (836 on Earth), and it sheds 704 mm a year where 1,177 are measured: like for like 0.60.",
    "Yangtze": "127 km3 a year against 910, and within a factor of two in none of 20 random settlements. With every hollow full "
               "1,567 thousand km2 drain to the gauge (1,705 on Earth), but only 839 reach it: the data close the Three "
               "Gorges themselves (their valley rises to 945 m on the data's grid, where the river above stands at 404 m), "
               "and the lake that the Sichuan basin holds behind them keeps its water. And like for like the land sheds 115 "
               "mm a year where 534 are measured, 0.21: the rain on it, 1,151 mm, is hardly more than the demand for water "
               "the engine gives it, 1,141 mm.",
    "Brahmaputra": "273 km3 a year against 613, and within a factor of two in none of 20 random settlements. The basin is "
                   "nearly right (507 thousand km2 reach the gauge; 555 on Earth), but its land sheds 578 mm a year where "
                   "1,105 are measured. The rain handed to the engine puts 1,565 mm a year on it; on its grid of 2.5 degrees "
                   "it cannot hold the rain of the mountain front [INFERRED].",
    "Yenisei": "77 km3 a year against 577 as the engine settles ties; 73 to 810 in 20 random settlements, within a factor of "
               "two in 3: the ties decide. As the engine settles them the mesh's river leaves its valley south of the gauge "
               "(MISLED), and land of 201 thousand km2 reaches the gauge, of the real 2,440.",
    "Lena": "11 km3 a year against 526, and within a factor of two in none of 20 random settlements (153 at most). The data "
            "close the valley above the delta themselves: on their own grid it rises to 152 m, where the river at Zhigansk "
            "stands at 91 m. On the mesh the lowland above fills as a lake of 150,490 km2 to 122 m, which overflows to the sea "
            "west of the delta and of the gauge. Land of 278 thousand km2 reaches the gauge, of the real 2,430.",
    "Mekong": "143 km3 a year against 292 as the engine settles ties; 35 to 143 in 20 random settlements, under half in every "
              "one. Land of 275 thousand km2 reaches the gauge, of the real 545. Seven of the 21 land cells on the river's way "
              "lie on level ground, where only the ties choose the way. The cause is not established.",
    "St Lawrence": "470 km3 a year against 226 as the engine settles ties: too much. In 20 random settlements 213 to 477, "
                   "within a factor of two in 11: the ties decide, and the engine's failure here is no finding. As the engine "
                   "settles them, land of 1,244 thousand km2 reaches the gauge (774 on Earth) and sheds 443 mm a year where "
                   "292 are measured. Like for like, on the mesh's own river of 1,012 thousand km2, the land sheds 423 mm: "
                   "1.45 of the measured depth.",
    "Amur": "26 km3 a year against 312, and within a factor of two in none of 20 random settlements. The data close the lower "
            "river themselves (MISLED), and its water leaves south to the Sea of Japan: land of 100 thousand km2 reaches the "
            "gauge, of the real 1,730.",
    "Mackenzie": "115 km3 a year against 288, the same in every one of 20 random settlements. The basin is right (1,740 "
                 "thousand km2 reach the gauge; 1,660 on Earth), but its land sheds 88 mm a year where 173 are measured, like "
                 "for like 0.51, and lakes on the way lose 37 km3 of that.",
    "Danube": "24 km3 a year against 202, and within a factor of two in none of 20 random settlements. The data close the "
              "Iron Gate themselves, and on the mesh the plain above it overflows to the Adriatic (MISLED): land of 145 "
              "thousand km2 reaches the gauge, of the real 807.",
    "Niger": "5 km3 a year against 33, and within a factor of two in none of 20 random settlements. Land of 116 thousand km2 "
             "reaches the gauge, of the real 1,516: closed lakes upstream keep the rest. Like for like the land sheds 8 mm a "
             "year where 22 are measured, 0.37.",
    "Zambezi": "11 km3 a year against 105, the same in every one of 20 random settlements. With every hollow full 2,016 "
               "thousand km2 drain to the gauge (940 on Earth), but only 233 reach it: closed lakes upstream keep the rest. "
               "That land sheds 71 mm a year where 112 are measured.",
    "Indus": "No river at all within 150 km of the gauge, against 89 km3 a year, in every one of 20 random settlements. With "
             "every hollow full 1,371 thousand km2 drain there (975 on Earth); as the water runs, land of 69 thousand km2 "
             "reaches the place and sheds nothing, and closed lakes upstream keep the rest. Like for like the land sheds 12 "
             "mm a year where 91 are measured, 0.13."}

# For every gauged river, with the ties settled as the engine settles them: the flow at the gauge (km3 a year) and the land
# whose water reaches it (thousand km2); and in how many of the SETTLEMENTS random settlements the flow is within a factor
# of two of the measured one.
AT_GAUGE = {"Amazon": (4515, 5921, 20), "Congo": (8, 50, 0), "Orinoco": (355, 563, 2), "Yangtze": (127, 839, 0), "Brahmaputra": (273, 507, 0),
            "Mississippi": (482, 2396, 20), "Yenisei": (77, 201, 3), "Parana": (480, 2987, 20), "Lena": (11, 278, 0), "Mekong": (143, 275, 0),
            "Ob": (604, 2865, 1), "Ganges": (273, 507, 20), "St Lawrence": (470, 1244, 11), "Amur": (26, 100, 0), "Mackenzie": (115, 1740, 0),
            "Columbia": (117, 484, 20), "Danube": (24, 145, 0), "Niger": (5, 116, 0), "Zambezi": (11, 233, 0), "Indus": (0, 69, 0),
            "Rhine": (84, 187, 20)}

# Like for like (earth_reference.like_for_like), with the ties settled as the engine settles them: for each gauged river
# whose basin on the mesh, with every hollow full, is within a factor of 1.5 of the real one's area, what its land sheds
# over the depth measured; and in how many of the SETTLEMENTS random settlements its basin is alike.
ALIKE = {"Amazon": (0.72, 20), "Orinoco": (0.60, 19), "Yangtze": (0.21, 20), "Brahmaputra": (0.23, 3), "Mississippi": (1.13, 20),
         "Parana": (0.78, 20), "Ob": (1.27, 1), "Ganges": (0.57, 20), "St Lawrence": (1.45, 9), "Mackenzie": (0.51, 20),
         "Columbia": (0.32, 20), "Niger": (0.37, 20), "Indus": (0.13, 20), "Rhine": (1.18, 20)}


@pytest.fixture(scope="module")
def gauges(earth):
    return ref.rivers_at_gauges(earth)


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(OFF_AT_GAUGE[name])) if name in OFF_AT_GAUGE else name for name in ref.GAUGES])
def test_a_great_river_carries_at_its_last_gauge_what_it_carries_on_earth(gauges, river):
    """Under Earth's rain and warmth, the largest yearly flow within 150 km of the station (the mesh may run the river
    through the next cell) is within a factor of two of the flow measured there [DOCUMENTED: Dai and Trenberth,
    Table 2; earth_reference.GAUGES]. Found, then kept: the 21 gauges, the 150 km and the factor of two came into
    the repository together with their results, and no record shows them set before a run. None has been changed
    since. With the ties settled as the engine settles them 7 of the 21 rivers pass, and each of the other 14 is
    an expected failure of its own. Four of the 21 are decided by the ties: the Ob, which passes, and the Orinoco,
    the Yenisei and the St Lawrence, which fail (AT_GAUGE, and the test after the next two).
    The test mixes two things: where the mesh runs the rivers, which the relief data and their ties mostly decide,
    and what the land sheds. The second is tested by itself below, like for like.
    The rule takes the largest flow near the station, whichever river carries it: for the Ganges that is the mesh's
    Brahmaputra. The cell taken lies 138 km from the Ganges's station; the two stations lie 179 km apart."""
    r = gauges[river]
    assert within_a_factor_of_two(r["measured"], r["flow"]), f"{river}: {r['flow']:.0f} km3 a year against {r['measured']:.0f}"


def within_a_factor_of_two(measured, flow):
    return measured / ref.FLOW_WITHIN < flow < measured * ref.FLOW_WITHIN


def test_within_a_factor_of_two_means_two():
    """The tools and the harness ask it in one place (earth_reference.within_a_factor_of_two), the tests above in
    their own words: the two must agree, at the edges as well."""
    assert ref.FLOW_WITHIN == 2.0
    for measured, flow, within in ((100.0, 199.9, True), (100.0, 200.0, False), (100.0, 50.1, True), (100.0, 50.0, False), (100.0, 290.0, False),
                                   (100.0, 34.0, False), (100.0, 100.0, True), (100.0, 0.0, False)):
        assert ref.within_a_factor_of_two(measured, flow) is within and bool(within_a_factor_of_two(measured, flow)) is within, (measured, flow)


def test_what_the_ties_decide_about_the_gauges(earth, gauges, outcomes):
    """Found, then kept: it keeps AT_GAUGE, the reasons in OFF_AT_GAUGE and docs/BUILD_NOTES.md true. A change that
    moves a flow or the land that reaches a gauge by more than 2 % (or by 1 km3, or 2 thousand km2), or changes in how
    many random settlements a river passes, fails here, and the records must then be measured again.
    In a random settlement 6 to 9 rivers pass. Six pass in all 20: the Amazon, the Mississippi, the Parana, the
    Ganges, the Columbia and the Rhine. Eleven pass in none. Four are decided by the ties: the Orinoco (2 of 20),
    the Yenisei (3), the Ob (1) and the St Lawrence (11). The Ob passes as the engine settles ties, which a random
    settlement does once in 20: that pass is no finding. The St Lawrence fails as the engine settles ties, which a
    random settlement does about half the time: that failure is none either.
    [Until the fourth check of build step 2 the random settlements left the choice among passes of one height as
    the engine makes it. The counts were then 0, 6, 7 and 0, and the St Lawrence and the Orinoco were said to
    fail "in every settlement".]"""
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
    assert (min(counts), max(counts)) == (6, 9) and sum(ok(outcomes["engine"], river) for river in AT_GAUGE) == 7
    assert {river for river, (_, _, k) in AT_GAUGE.items() if 0 < k < SETTLEMENTS} == {"Orinoco", "Yenisei", "Ob", "St Lawrence"}
    assert sum(k == 0 for _, _, k in AT_GAUGE.values()) == 11
    spread = lambda river: (min(r["flow"][river] for r in drawn(outcomes)), max(r["flow"][river] for r in drawn(outcomes)))
    for river, (low, high) in {"Orinoco": (350, 606), "Yenisei": (73, 810), "Mekong": (35, 143), "St Lawrence": (213, 477), "Ob": (29, 599),
                               "Mackenzie": (115, 115), "Zambezi": (11, 11), "Lena": (10, 153)}.items():        # what the reasons quote
        assert abs(spread(river)[0] - low) < max(2.0, 0.02 * low) and abs(spread(river)[1] - high) < max(2.0, 0.02 * high), (river, spread(river))
    # the Ganges's row is the mesh's Brahmaputra: one cell serves both stations, 138 km from the Ganges's and 179 km between the two
    assert gauges["Ganges"]["cell"] == gauges["Brahmaputra"]["cell"]
    ganges, brahmaputra = ref.GAUGES["Ganges"][:2], ref.GAUGES["Brahmaputra"][:2]
    assert abs(earth.km(gauges["Ganges"]["cell"], *ganges) - 138.0) < 3.0 and abs(earth.km(earth.cell(*brahmaputra), *ganges) - 179.0) < 35.0
    between = np.arccos(np.clip(ref._points(np.array([ganges[0]]), np.array([ganges[1]]))[0] @ ref._points(np.array([brahmaputra[0]]), np.array([brahmaputra[1]]))[0], -1, 1))
    assert abs(between * R / 1000.0 - 179.0) < 2.0
    # ... and of the Mekong's way: 21 land cells, 7 of them on level ground
    way = [c for c in ref.way_of(earth, "Mekong") if c["step"] != "sea"]
    assert (len(way), sum(c["step"] == "level" for c in way)) == (21, 7)
    assert {river for river, (_, _, k) in AT_GAUGE.items() if k == SETTLEMENTS} == {"Amazon", "Mississippi", "Parana", "Ganges", "Columbia", "Rhine"}
    assert gauges["Indus"]["no_river"] and not any(r["no_river"] for name, r in gauges.items() if name != "Indus")


def test_the_books_of_every_gauge_close(earth, gauges):
    """The flow at a gauge is the land whose water reaches it, times what that land sheds, less what the lakes with an
    outlet on the way lose, less what a closed lake inside the gauge's own cell keeps. The parts are worked out
    apart: the first two summed down the ways the water takes, the third from the yearly loss of each lake whose
    outlet lies upstream, and for a cell inside such a lake from the share of the passing water that the lake will
    lose; the fourth from the share of the cell that the closed lake covers. The flow is the field river_discharge.
    [The third check found that the third had been worked out as what was left over, so that this could not fail.
    The fourth found that no gauge stood at an outlet or in a closed lake as built, so that two cases of the books
    were held by nothing: the test after this one holds them at every cell.]"""
    for river, r in gauges.items():
        assert abs(r["reaches"] * r["sheds"] / 1000.0 - r["lost_in_lakes"] - r["kept_here"] - r["flow"]) < 1e-6 * max(r["flow"], 1.0) + 1e-4, (river, r)
        assert abs(r["unbalanced"]) < 1e-6 * max(r["flow"], 1.0) + 1e-4, (river, r)
        assert r["lost_in_lakes"] >= 0.0 and r["kept_here"] >= 0.0
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


def test_the_books_of_the_river_close_at_every_cell(earth):
    """What the test above asks of 21 gauges, at every cell of the planet, and again with the demand for water cut
    to 0.76 of itself, where other lakes stay closed: the water shed upstream, less what the lakes with an outlet
    lose on the way, less what a closed lake in the cell itself keeps, is the field river_discharge. Among the cells
    are the three kinds that no gauge stands on as built: the outlet cell of a lake, a cell inside a lake that is not
    its outlet, and a cell partly under a closed lake. Each kind must be there, and each must carry a part of the
    books that is far larger than what the books may be out by, or the test would hold nothing."""
    extra = earth.h.params["models"]["slots"]["Hydrology"]["constants"]["demand"]["priestley_taylor_extra"]
    for words, water in (("as built", None), ("demand x 0.76", earth.hydrology({"demand": {"priestley_taylor_extra": (1.0 + extra) * 0.76 - 1.0}}))):
        b = ref.river_books(earth, water)
        books = earth.books(water)
        size = np.maximum(np.maximum(b["flow"], b["shed"]), 1.0)                  # km3 a year
        assert (np.abs(b["unbalanced"]) < 1e-6 * size).all(), (words, float(np.abs(b["unbalanced"] / size).max()))
        flows = books["flows"]
        found = flows["lakes"]
        runs = found["overflows"].astype(bool)
        outlet = np.zeros(earth.mesh.n, dtype=bool)
        outlet[np.asarray(books["table"]["spill_from_cell"])[found["row"][runs]]] = True
        inside = (flows["crossing"] >= 0) & ~outlet
        share = (water or earth.hydrology()).fields["lake_fraction"].astype(np.float64)
        in_closed = (flows["crossing"] < 0) & (share > 0.0) & (share < 1.0)
        for kind, cells, part in (("an outlet", outlet, b["lost"]), ("inside a lake", inside, b["lost"]), ("partly under a closed lake", in_closed, b["kept_here"])):
            assert cells.sum() > 100, (words, kind, int(cells.sum()))
            assert (part[cells] > 1e-3 * size[cells]).sum() > 50, (words, kind)   # the part matters there: leaving it out would show
        assert (b["kept_here"][~in_closed & (share < 1.0)] == 0.0).all() and (b["lost"] >= 0.0).all()
        # a cell wholly under a closed lake carries no river at all: the lake has taken everything that arrived
        under = (flows["crossing"] < 0) & (share == 1.0)
        assert under.sum() > 50 and (b["flow"][under] == 0.0).all() and np.allclose(b["kept_here"][under], (b["shed"] - b["lost"])[under], rtol=1e-6, atol=1e-6)
    # the Niger's gauge at demand x 0.76, the case that the fourth check found unaccounted: its cell lies partly under a closed lake
    niger = ref.rivers_at_gauges(earth, water)["Niger"]
    assert niger["kept_here"] > 0.1 and abs(niger["unbalanced"]) < 1e-6 * max(niger["flow"], 1.0)


# ---------------------------------------------------------------------------------------------- the numbers the tools print
# [The fourth check of build step 2: no test ran a tool, the tools did their own arithmetic, and ten changes made on
# purpose to that arithmetic went unnoticed. The arithmetic is now in earth_reference, the tools print what it gives,
# and the tests below hold both: the numbers, and the lines of the reports that carry them.]
WATER_OF_THE_LAND = {        # earth_reference.land_water as the engine settles ties: (value, how near it must stay)
    "rain": (119.78, 0.05), "to_air": (88.06, 0.05), "back_to_air": (0.7352, 0.0004), "to_sea": (31.72, 0.03), "rain_mm": (790.3, 0.4),
    "to_air_mm": (581.0, 0.4), "demand_mm": (1003.3, 0.6), "lakes_share": (0.06025, 0.0002), "lakes_km2": (9_131_859.0, 3_000.0),
    "lakes": (544, 0), "lakes_with_outlet": (434, 0), "shed": (35.17, 0.03), "back_to_air_dry": (0.7064, 0.0004),
    "lakes_with_outlet_lose": (3.014, 0.01), "closed_lakes_keep": (0.434, 0.004), "reaches_sea_share": (0.7074, 0.0005),
    "closed_hollow_share": (0.6055, 0.0005), "under_water_if_full_share": (0.1022, 0.0004), "level_with_the_water_share": (0.0358, 0.0004)}

# earth_reference.under_demand: the land's water with the air's demand for water multiplied by a factor
# (like for like, its median, without the Amazon, back to the air, to the sea, mm to the air, gauges within a factor of two)
UNDER_DEMAND = {1.0: (0.683, 0.587, 0.644, 0.7352, 31.72, 581.0, 7), 0.794: (0.926, 0.873, 0.906, 0.6487, 42.08, 512.6, 12),
                0.76: (0.973, 0.914, 0.963, 0.6317, 44.11, 499.2, 11), 0.6: (1.227, 1.124, 1.276, 0.5416, 54.90, 428.0, 10)}


def test_the_water_of_all_the_land_adds_up_and_is_what_the_notes_say(earth, outcomes):
    """Found, then kept: it keeps docs/BUILD_NOTES.md, section 4.4, true. The parts must add up among themselves as
    well: what the land sheds, less what the lakes with an outlet lose and what closed lakes keep, reaches the sea;
    and the share of the land under lakes is their area over the land's, not over the planet's."""
    w = ref.land_water(earth)
    assert set(w) == set(WATER_OF_THE_LAND)
    off = {key: w[key] for key, (value, near) in WATER_OF_THE_LAND.items() if abs(w[key] - value) > near}
    assert not off, off
    assert abs(w["rain"] - w["to_air"] - w["to_sea"]) < 1e-3 * w["to_sea"]
    assert abs(w["shed"] - w["lakes_with_outlet_lose"] - w["closed_lakes_keep"] - w["to_sea"]) < 1e-3 * w["to_sea"]
    land_km2 = earth.area[earth.land].sum() / 1e6
    assert abs(w["lakes_km2"] / land_km2 - w["lakes_share"]) < 1e-9 and w["lakes_km2"] / (earth.area.sum() / 1e6) < 0.02
    assert abs(w["to_air_mm"] / w["rain_mm"] - w["back_to_air"]) < 1e-9
    for r in outcomes.values():                                                   # ... and for every way of settling the ties
        assert 0.0595 < r["lakes_share"] < 0.0607, r["lakes_share"]
    assert outcomes["engine"]["lakes_share"] == w["lakes_share"] and outcomes["engine"]["to_sea"] == w["to_sea"]


def test_the_rain_and_the_demand_over_the_land_that_reaches_a_gauge(gauges):
    """Found, then kept: the two columns of the report that say why a basin sheds what it sheds. The rain is far above
    the demand on the Amazon and the Yenisei, and far below it on the Niger and the Indus."""
    kept = {"Amazon": (2314, 1657), "Mississippi": (954, 935), "Yenisei": (652, 267), "Niger": (874, 1715), "Indus": (261, 1460), "Rhine": (1111, 698)}
    for river, (rain, demand) in kept.items():
        r = gauges[river]
        assert abs(r["rain"] - rain) < 0.01 * rain + 2 and abs(r["demand"] - demand) < 0.01 * demand + 2, (river, round(r["rain"]), round(r["demand"]))


def test_a_smaller_demand_would_mend_the_shortfall_whichever_of_two_causes_made_it_smaller(earth):
    """Found, then kept: it keeps the table of docs/BUILD_NOTES.md, section 4.4, true, and the reading that the notes
    give it. Like for like the land sheds 0.68 of the measured depth. With the demand for water multiplied by 0.76
    it sheds 0.97, and with 0.794 it sheds 0.93: both would meet the test that the engine fails, and both bring the
    water of all the land to Earth's (0.65 of the rain back to the air, 40 thousand km3 a year to the sea). But
    0.76 stands for an error in the energy that the formulas leave to the land (85.7 W/m2 where a published budget
    has 65.5), and 0.794 for the Priestley-Taylor rule without its factor of 1.26: two different causes that this
    diagnosis cannot tell apart. [The fourth check of build step 2 found this, after I had stated the first cause
    as measured.]"""
    rows = tool("earth_rivers").what_a_smaller_demand_would_do(earth, say=lambda line: None)
    assert set(rows) == set(UNDER_DEMAND)
    for factor, (like, median, without_amazon, back, to_sea, mm, within) in UNDER_DEMAND.items():
        r = rows[factor]
        got = (r["like_all"], r["like_median"], r["like_without_amazon"], r["back_to_air"], r["to_sea"], r["to_air_mm"], r["gauges_within"])
        near = (0.004, 0.004, 0.004, 0.0004, 0.03, 0.4, 0)
        assert all(abs(a - b) <= c for a, b, c in zip(got, (like, median, without_amazon, back, to_sea, mm, within), near)), (factor, got)
    for factor in (0.794, 0.76):                                                  # each of the two cuts would pass the tests that the engine fails
        r = rows[factor]
        assert 0.85 < r["like_all"] < 1.15 and 0.62 < r["back_to_air"] < 0.66 and 40.0 < r["to_sea"] < 45.0
    # ... on the weighted figure, which the Amazon carries. Neither mends the basins: one factor for all land leaves two of
    # the fourteen within 15 % of the measured depth, and the rest spread from a third of it to 1.7 times it
    spread = {factor: (round(r["like_lowest"], 2), round(r["like_highest"], 2), r["like_within_15"]) for factor, r in rows.items()}
    assert spread == {1.0: (0.13, 1.45, 1), 0.794: (0.28, 1.67, 2), 0.76: (0.32, 1.74, 2), 0.6: (0.42, 2.28, 4)}, spread
    assert abs(1.0 / 1.26 - 0.794) < 0.001 and abs(65.5 / 85.7 - 0.764) < 0.001   # where the two factors come from
    assert abs(ref.demand_times(earth, 0.794)["demand"]["priestley_taylor_extra"]) < 0.001      # 0.794: the rule with nothing extra


def test_what_the_like_for_like_figure_can_bear(outcomes, earth):
    """Found, then kept: it keeps the caveats of docs/BUILD_NOTES.md, section 4.4, true. The 0.68 is a mean weighted by
    water: the Amazon carries 53 % of it, and without the Amazon it is 0.64; the median of the fourteen basins'
    own ratios is 0.59. In two of the basins the comparison cannot test what Hydrology does: over the mesh's
    Brahmaputra the rain handed in (1,013 mm a year) is less than the runoff measured (1,105 mm), and over its
    Columbia the measured runoff would leave 157 mm for evaporation. Without those two the figure is 0.72."""
    like = ref.like_for_like(earth)
    all_of_them = ref.like_together(like)
    assert set(all_of_them["basins"]) == set(ALIKE) and abs(all_of_them["ratio"] - outcomes["engine"]["like_all"]) < 1e-12
    assert abs(all_of_them["ratio"] - 0.683) < 0.003 and abs(all_of_them["median"] - 0.587) < 0.004
    assert abs(sum(all_of_them["weights"].values()) - 1.0) < 1e-9 and abs(all_of_them["weights"]["Amazon"] - 0.531) < 0.005
    assert (all_of_them["below_one"], all_of_them["above_one"], all_of_them["within_two"]) == (10, 4, 9)
    assert abs(ref.like_together(like, ("Amazon",))["ratio"] - 0.644) < 0.004
    b, c = like["Brahmaputra"], like["Columbia"]
    assert abs(b["rain"] - 1013.0) < 5.0 and abs(b["measured_depth"] - 1104.5) < 0.5 and b["rain"] < b["measured_depth"]
    assert abs(c["rain"] - 437.0) < 4.0 and abs(c["rain"] - c["measured_depth"] - 157.0) < 4.0
    asked = sorted(((like[name]["measured_depth"] / like[name]["rain"], name) for name in ALIKE), reverse=True)
    assert [name for _, name in asked[:3]] == ["Brahmaputra", "Columbia", "Orinoco"] and asked[1][0] > ref.MUCH_OF_THE_RAIN > asked[2][0]
    assert abs(asked[0][0] - 1.09) < 0.01 and abs(asked[1][0] - 0.64) < 0.01 and abs(asked[2][0] - 0.57) < 0.01
    assert abs(ref.like_together(like, ("Brahmaputra", "Columbia"))["ratio"] - 0.724) < 0.004
    by_hand = sum(like[name]["sheds"] * like[name]["basin"] for name in ALIKE) / sum(like[name]["measured_depth"] * like[name]["basin"] for name in ALIKE)
    assert abs(by_hand - all_of_them["ratio"]) < 1e-12


def test_the_radiation_over_earths_land_and_what_the_engines_excess_is_made_of(earth):
    """Found, then kept: it keeps docs/BUILD_NOTES.md, section 7, item 14, true (python tools/earth_demand.py).
    The engine's formulas leave Earth's land 85.7 W/m2 to warm the air and evaporate water, where a published
    budget has 65.5 [DOCUMENTED: Trenberth, Fasullo and Kiehl 2009, Table 2b, land]: 1.31 times as much. Of the
    excess of 20.2, 0.7 come from the sunlight that reaches the ground, 8.2 from the ground reflecting 0.17 of it
    where the budget has 0.21, and 11.3 from the heat that the ground radiates away. The land's evaporation, under
    Earth's measured rain, takes 45.1 W/m2 where the budget has 38.5: 1.17 times as much.
    The published numbers are written here once more, as the table gives them: a slip in the tool's copy would
    change every ratio the notes draw from it."""
    demand = tool("earth_demand")
    m = demand.LAND_MEASURED
    assert m == {"reaches": 184.7, "absorbed": 145.1, "lost": 79.6, "evaporation": 38.5, "sensible": 27.0}
    assert abs(m["reaches"] - m["absorbed"] - 39.6) < 1e-9 and abs(m["absorbed"] - m["lost"] - m["evaporation"] - m["sensible"]) < 1e-9
    said = []
    r = demand.report(earth=earth, say=said.append)
    b, x = r["budget"], r["excess"]
    for key, value in (("reaches", 185.6), ("absorbed", 154.0), ("lost", 68.3), ("evaporation", 45.1)):
        assert abs(b[key] - value) < 0.1, (key, b[key])
    left, left_measured = b["absorbed"] - b["lost"], m["absorbed"] - m["lost"]
    assert abs(left - 85.7) < 0.1 and abs(left / left_measured - 1.308) < 0.004 and abs(b["evaporation"] / m["evaporation"] - 1.172) < 0.004
    assert abs(sum(x.values()) - (left - left_measured)) < 1e-9                    # the three parts are the whole excess
    for key, value in (("sunlight", 0.70), ("reflection", 8.24), ("heat_loss", 11.26)):
        assert abs(x[key] - value) < 0.06, (key, x[key])
    assert abs(r["wants_sun"] - 0.615) < 0.004 and abs(r["wants_heat"] - 0.763) < 0.004 and r["sunshine"] == 0.62
    # the demand in the engine's form and in the paper's: 1,003 against 1,246 mm a year less 194 that the night gives back
    a = r["bands"]["all land"]
    assert abs(r["field"] - 1003.3) < 0.6 and abs(a["engine"] - r["field"]) < 0.01 and r["largest_gap_to_the_field"] < 1e-3
    assert abs(a["paper"] - 1246.4) < 1.5 and abs(a["dew"] - 194.4) < 0.6 and abs(r["none_where_the_paper_has_some"] - 0.0268) < 0.001
    assert all(1.02 < (v["paper"] - v["dew"]) / v["engine"] < 1.06 for v in r["bands"].values())
    text = "\n".join(said)
    assert "left to warm the air and evaporate        85.7      65.5   the engine has 1.31 of the measured" in text
    assert "of that, evaporation takes                45.1      38.5   the engine has 1.17 of the measured" in text
    assert "0.7 from the sunlight that reaches the ground; 8.2 from the ground reflecting 0.17 of it where the budget has 0.21; 11.3 from the heat" in text


def test_the_reports_of_the_tools_print_what_the_harness_measures(earth, flood, gauges, outcomes):
    """The reports are read by a person and quoted in the notes. Their lines are held here against the numbers of the
    harness, which the tests above hold: a report that printed another number, or met a gauge within a factor of
    three, would show."""
    said = []
    tool("earth_rivers").report(earth=earth, say=said.append)
    text = "\n".join(said)
    passing = [name for name, r in gauges.items() if within_a_factor_of_two(r["measured"], r["flow"])]
    assert len(passing) == 7 and f"within a factor of two of the measured flow: 7 of {len(gauges)}" in text
    for name, r in gauges.items():                                                # every row says yes or NO as the test of that gauge does
        row = next(line for line in said if line.startswith(f"{name:12s}") and "|" in line and ("yes" in line.split("|")[0] or "NO" in line.split("|")[0]))
        assert ("yes" in row.split("|")[0]) == (name in passing), row
        assert f"{r['measured']:9.0f}{r['flow']:8.0f}" in row and f"{r['station_area']:8.0f}{r['reaches']:9.0f}{r['basin']:18.0f}" in row
    assert "the books of every gauge close" in text and "and at every cell of the mesh, to within" in text
    assert "basins alike: 14 of 21. All of them together, the engine sheds 0.68 of the measured depth; basin by basin 0.13 to 1.45, 10 below 1 and 4 above; within a factor of two: 9" in text
    assert "the Amazon carries 53 % of the weight. Without the Amazon: 0.64. The median of the basins' own ratios: 0.59" in text
    assert "the Brahmaputra (rain 1013, measured runoff 1105), the Columbia (rain 437, measured runoff 280). Without them: 0.72" in text
    assert f"{'Brahmaputra':12s}" in text and any(line.startswith("Brahmaputra") and line.rstrip().endswith("1.09") for line in said)      # measured / rain
    assert "Published for the basin: rain 585, sheds 193, back to the air 392" in text and "a runoff coefficient of 0.38, which makes 222 mm of its 585" in text
    assert "handed the published rain instead:  rain 585, sheds 224 (1.17 of the 193, 1.01 of the 222), back to the air 361" in text
    assert "within 300 km: 16 of 24" in text
    assert "rain on land 119.8; back to the air 88.1 (0.735 of the rain); rivers reaching the sea 31.7" in text
    assert "shed by the land as if none of it were flooded 35.2 (0.706 of the rain back to the air); lakes with an outlet lose 3.01 more than the ground they cover; closed lakes keep 0.43" in text
    assert "land under water if every hollow were full: 10.2 %, and another 3.6 % exactly level with that water" in text
    assert "the air's demand for water over land 1003 mm a year; rain 790 mm; back to the air 581 mm; lakes cover 6.02 % of the land: 544 lakes, 434 with an outlet" in text
    assert "lakes larger than 100,000 km2: 12, with 54 % of all the land under lakes" in text
    said = []
    tool("earth_relief").report(earth=earth, flood=flood, say=said.append)
    text = "\n".join(said)
    assert "of 48733 land cells 17454 (35.8 %) have a land neighbour at exactly their own height" in text
    assert "of 42980 land cells with a lower neighbour, 9869 (23.0 %) have several equally low: the lower bed settles 3296, the wider way 6521, the cell numbers 52; another 5063 land cells (10.4 %) lie on level ground" in text
    assert "reaches the sea in another cell when the order of the cells is turned round, and of 15.5 % when the wider way is left out" in text
    assert "Of all that is not ocean, 13.3 % lies under water when every hollow of the data is full" in text
    assert "the mesh: 29.7 % of the planet is not sea. Of it, 10.2 % lies under water when every hollow is full (11.6 % between 60 south and 60 north); 60.6 % drains into a closed hollow" in text
    assert "closed in the data themselves: 5 of 6 (Congo, Danube, Lena, Amur, Yangtze)" in text
    assert "of these 12 lakes, 11 lie in hollows that the data hold on their own grid" in text
    assert "of 4646 coastal land cells, 2078 are handed to Drainage at 1 m or lower, and 69 of those have a mean height above 300 m" in text
    # part 7, on summaries that are at hand: the counts printed are those of earth_reference.tally
    t = ref.tally(drawn(outcomes))
    assert t["runs"] == SETTLEMENTS and t["mouths"]["Amazon"][0] == SETTLEMENTS and t["mouths"]["Congo"][0] == 0
    assert t["caspian_closed"] == sum(not r["caspian"]["overflows"] for r in drawn(outcomes))
    assert t["gauges"]["Amazon"][0] == SETTLEMENTS and t["gauges"]["Amazon"][3] == sum(r["like"]["Amazon"][0] for r in drawn(outcomes))
    assert t["mouths_passing"] == (min(sum(r["mouth_km"][x] < 300.0 for x in MOUTHS) for r in drawn(outcomes)),
                                   max(sum(r["mouth_km"][x] < 300.0 for x in MOUTHS) for r in drawn(outcomes)))


def test_the_expected_failures_about_lakes_fail_by_the_numbers_their_reasons_give(earth):
    """An expected failure counts as expected whatever makes its condition fail: one that looked at the wrong lake
    would pass for years. Each condition is run here and must fail in the words, and with the number, that its
    reason gives. (The rivers' expected failures are held the same way by MOUTHS and AT_GAUGE.)"""
    with pytest.raises(AssertionError, match=r"^a lake of 880,226 km2"):
        test_the_basin_of_the_congo_holds_no_great_lake.__wrapped__(earth) if hasattr(test_the_basin_of_the_congo_holds_no_great_lake, "__wrapped__") \
            else test_the_basin_of_the_congo_holds_no_great_lake(earth)
    with pytest.raises(AssertionError, match=r"^6\.0 % of the land under lakes"):
        test_lakes_cover_no_more_of_the_land_than_on_earth(earth)
    with pytest.raises(AssertionError):
        test_the_caspian_stays_a_closed_lake(earth)
    lake = earth.lake_at(*ref.CASPIAN)                                            # ... and for the reason given: a lake stands there, and it overflows
    assert lake is not None and bool(lake["overflows"]) and abs(lake["outflow_m3_per_year"] / 1e9 - 0.47) < 0.05
    assert missed("a reason").kwargs == {"strict": True, "raises": AssertionError, "reason": "a reason"}


@missed("Like for like, the engine's land sheds 0.68 of the depth measured over the fourteen basins that are alike (0.64 to "
        "0.70 in 20 random settlements): too little. The figure is a mean weighted by water: the Amazon carries 53 % of it, "
        "without the Amazon it is 0.64, and the median of the fourteen basins' own ratios is 0.59. They run from 0.13 (the "
        "Indus) to 1.45 (the St Lawrence), ten below 1 and four above. Two of the low ones cannot test the model: over the "
        "mesh's Brahmaputra the rain handed in, 1,013 mm a year, is less than the runoff measured, and over its Columbia "
        "the runoff measured is 0.64 of the rain handed in; without the two the figure is 0.72. The cause of the shortfall "
        "is not established. What is measured: the engine's formulas leave Earth's land 1.31 times the energy that a "
        "published budget leaves it, and the land's evaporation is 1.17 times that budget's (python tools/earth_demand.py); "
        "with the demand for water cut to 0.76 of itself the figure is 0.97, and with the Priestley-Taylor rule's factor of "
        "1.26 taken as 1.00, a cut to 0.794 with another cause, it is 0.93 (python tools/earth_rivers.py --demands). Which "
        "of the two, or what else, is at fault, nothing measured here can say [INFERRED: any cause named]. "
        "[MEASURED: tools/earth_rivers.py, parts 2 and 8]")
def test_like_for_like_the_land_of_the_great_basins_sheds_what_it_sheds_on_earth(outcomes):
    """Stated as a miss, with the number in view: over the basins that are alike in size, the engine's land sheds
    within 15 % of the depth measured. This is the test of what Hydrology makes of rain and warmth; where the
    rivers run does not enter it. The tests under "the numbers the tools print", above, hold every number of the
    reason."""
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
    spread = [r["like_all"] for r in drawn(outcomes)]
    assert abs(min(spread) - 0.64) < 0.006 and abs(max(spread) - 0.70) < 0.006


@missed("The design's condition fails as built: as the engine settles ties the lake at the Caspian's place overflows, by 0.47 "
        "km3 of the 669 that reach it in a year. In 20 random settlements it stays closed in 10 and overflows in 10, by up "
        "to 6.0 km3: the lake stands at the brim of its hollow, and the ties decide whether a little runs over. What does "
        "not depend on the ties is that it is far too large: 1.08 to 1.11 million km2 at 54 to 61 m, where the real sea "
        "covers 371,000 to 436,000 km2 in the sources opened and stands 28 m below the ocean. The lake's books: rivers and "
        "shores bring it 588 km3 a year, about twice the 300 that reach the real sea [DOCUMENTED at second hand: the Volga "
        "237 km3 a year, about 80 % of the inflow], off land of 4.06 million km2 where the real sea drains about 3 "
        "million; its water loses 936 mm a year and gets 408 mm of rain. Most of the excess is the Volga's. Over the land "
        "that drains through Volgograd the rain data hold 744 mm a year where 585 are published for the basin, and the "
        "engine sheds 342 mm where the published figures give 193 mm (262 km3 over the basin) or 222 mm (a runoff "
        "coefficient of 0.38): the source gives both. Handed the published 585 mm instead, the same land sheds 224 mm. "
        "Most of the river's excess comes with the rain data, then, and the model's part of it lies between nothing and "
        "a fifth, according to which published figure is taken [MEASURED for the engine; DOCUMENTED for the basin: "
        "Kalugin 2022]. The larger catchment adds to it. [MEASURED]")
def test_the_caspian_stays_a_closed_lake(earth):
    """The design's: the Caspian stays a closed lake."""
    lake = earth.lake_at(*ref.CASPIAN)
    assert lake is not None and not lake["overflows"]


def test_most_of_the_volgas_excess_comes_with_the_rain_data_and_the_models_part_depends_on_the_figure_taken(earth, outcomes):
    """Found, then kept: it keeps the reason above and section 4.4 of the notes true. The Volga is the one basin for
    which a published precipitation is at hand beside the published runoff [DOCUMENTED: Kalugin 2022: 1,360,000 km2,
    585 mm, 262 km3 a year]. The source gives the runoff twice, and the two do not agree: 262 km3 over the basin is
    193 mm, and its "runoff coefficient of 0.38" makes 222 mm of the 585.
    Like for like, the mesh's Volga at Volgograd sheds 342 mm, 1.8 or 1.5 times the published depth, and the rain
    data hold a quarter more over that land than is published, however the ties are settled. Handed the published
    precipitation instead (the rain data over that land, scaled by one factor in every month), the same land sheds
    224 mm: 1.17 times the one published figure and 1.01 times the other. So four fifths of the excess, or all of
    it, come with the rain data; the model's part lies between nothing and a fifth.
    [I had written "a fifth is the model's [MEASURED]" on the 193 mm alone. The fourth check of build step 2 found
    the second figure in the same paragraph of the source.]"""
    published_rain = ref.VOLGA["precipitation_mm"]
    by_volume = 1000.0 * ref.VOLGA["gauge"][2] / ref.VOLGA["gauge"][3]            # 262 km3 over 1,360 thousand km2
    by_coefficient = ref.VOLGA["runoff_coefficient"] * published_rain           # 0.38 of 585 mm
    assert abs(by_volume - 192.6) < 0.1 and abs(by_coefficient - 222.3) < 0.1
    v = outcomes["engine"]["volga"]
    assert v["like"] and abs(v["basin"] - 1248.0) < 5.0 and abs(v["rain"] - 744.0) < 3.0 and abs(v["sheds"] - 342.0) < 3.0
    assert abs(v["ratio"] - 1.77) < 0.03 and abs(v["sheds"] / by_coefficient - 1.54) < 0.03
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
    assert abs(p["sheds"] - 224.5) < 3.0
    assert abs(p["sheds"] / by_volume - 1.17) < 0.02 and abs(p["sheds"] / by_coefficient - 1.01) < 0.02       # a sixth too much, or nothing
    with_the_rain_data = both["data"]["sheds"] - p["sheds"]                      # what the excess of rain adds to the runoff
    assert 0.75 < with_the_rain_data / (both["data"]["sheds"] - by_volume) < 0.83          # four fifths of the excess over 193 mm
    assert 0.95 < with_the_rain_data / (both["data"]["sheds"] - by_coefficient) < 1.01     # all of the excess over 222 mm


def test_what_the_ties_decide_about_the_caspian(earth, outcomes):
    """Found, then kept: it keeps the reason above true. The lake overflows as the engine settles ties and in 10 of 20
    random settlements; in the other 10 it keeps its water. (In 100 random settlements it kept it in 55: python
    tools/earth_rivers.py --settlements 100.)"""
    built = outcomes["engine"]["caspian"]
    assert built["overflows"] and abs(built["outflow_km3"] - 0.47) < 0.05 and abs(built["area_km2"] - 1_113_492) < 1_000 and built["level_m"] == 61.0
    there = [r["caspian"] for r in drawn(outcomes)]
    assert sum(not c["overflows"] for c in there) == 10 and 5.5 < max(c["outflow_km3"] for c in there) < 6.5
    assert all(1.075e6 < c["area_km2"] < 1.12e6 and 54.0 <= c["level_m"] <= 61.0 for c in there)
    assert min(c["level_m"] for c in there) == 54.0 and max(c["level_m"] for c in there) == 61.0 and min(c["area_km2"] for c in there) < 1.085e6
    assert all(c["area_km2"] > 2.4 * 436_000 for c in there)                    # far too large in every one: that is no matter of ties
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


@missed("6.02 % of the land lies under lakes, 9.13 million km2 (5.99 to 6.03 % in 20 random settlements). Twelve lakes larger than 100,000 "
        "km2 hold 54 % of it, where Earth has one of that size, the Caspian. Eleven of the twelve lie in hollows that the "
        "relief data hold on their own grid: the Caspian at two and a half to three times its size, the Black Sea and the Great Lakes, which "
        "are real, and the basins of the Congo (880,226 km2), the Amazon (629,173) and the Danube, the West Siberian plain "
        "(437,843) and the lowlands of the Amur and the Lena, which the data close and Earth does not. The twelfth is the "
        "Baltic, which the mesh cuts off. [MEASURED: tools/earth_relief.py, for the hollows of the data and of the mesh; "
        "UNVERIFIED, from memory, which of them hold lakes on Earth]")
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
    """The design asks that the classifier, fed real monthly temperature and rain, agree with the published
    Köppen-Geiger map within a tolerance. This test asks less, because the map is not among the reference data:
    with CRU temperature and GPCP rain, each of the five main groups takes a share of the land within 6 points of
    the share Peel, Finlayson and McMahon 2007 give [DOCUMENTED when build step 2 was written]: arid B 30.2 %,
    cold D 24.6 %, tropical A 19.0 %, temperate C 13.4 %, polar E 12.8 %. The 6 points were chosen when the test
    was written."""
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


def test_the_twins_report_prints_the_twin_beside_earth(twin):
    """tools/earth_twin.py prints the table of docs/BUILD_NOTES.md, section 4.6. Its rows are held here against the
    numbers that the tests above work out for themselves, and Earth's column against the sources. [No test ran the
    tool until the fourth check of build step 2 asked for one.]"""
    from worldengine import store
    e, w = twin
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    said = []
    rows = {what.strip(): (mine, earths) for what, mine, earths, _ in tool("earth_twin").compare(store.MemoryView(w, e), say=said.append)}
    north = land & (m.lat > 40) & (m.lat < 60)
    swing = ((celsius[6] - celsius[0]) * area)[north].sum() / area[north].sum()
    measured = ((earth_celsius[6] - earth_celsius[0]) * area)[north].sum() / area[north].sum()
    assert rows["July less January, land at 40 to 60 N"] == pytest.approx((swing, measured), abs=1e-9)
    names = e.registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[f["climate_class"]]
    for letter, share in (("A", 19.0), ("B", 30.2), ("C", 13.4), ("D", 24.6), ("E", 12.8)):
        mine, earths = rows[f"climate group {letter}, share of land"]
        assert earths == share and abs(mine - 100.0 * area[land & (group == letter)].sum() / area[land].sum()) < 1e-9
    assert rows["sea level against Earth's"][1] == 0.0 and abs(rows["sea level against Earth's"][0]) < 60.0
    assert rows["rain on land that goes back to the air"][1] == 65.0 and rows["rivers reaching the sea"][1] == 40.0
    assert rows["largest river"][1] == 210_000.0 and rows["land under lakes"][1] == 3.7
    everywhere = np.ones(m.n, dtype=bool)
    mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
    assert rows["mean temperature of the year"] == pytest.approx((mean(celsius.mean(axis=0), everywhere), mean(earth_celsius.mean(axis=0), everywhere)), abs=1e-9)
    yearly = f["precipitation"].astype(np.float64).sum(axis=0)
    assert abs(rows["over land"][0] - mean(celsius.mean(axis=0), land)) < 1e-9 or abs(rows["over land"][0] - mean(yearly, land)) < 1e-9
    text = "\n".join(said)
    assert f"The Earth twin ({m.n} cells, {w.rounds_used['climate']} climate rounds, settled: True) beside Earth" in text
    assert "yearly temperature, cell by cell: the twin differs from Earth by" in text and "yearly rain, cell by cell: correlation of the logarithms" in text
    row = next(line for line in said if line.startswith("July less January, land at 40 to 60 N"))
    assert f"{swing:10.1f}{measured:10.1f}" in row


def test_the_expected_failures_of_the_twin_fail_by_the_numbers_their_reasons_give(twin):
    """Each expected failure of the twin is run here and must fail in the words, and with the numbers, of its reason:
    13.4 K for Earth's 31.1 K; group D on 2.1 % of the land; the driest northern band at 58 degrees with 273 mm; 440
    mm for Earth's 654. An expected failure that looked at the wrong field or place would otherwise pass for one."""
    with pytest.raises(AssertionError, match=r"^13\.4 K against 31\.1 K"):
        test_northern_land_is_far_warmer_in_july_than_in_january_as_on_earth(twin)
    with pytest.raises(AssertionError, match=r"^group D takes 2\.1 % of the twin's land"):
        test_the_cold_climates_with_warm_summers_take_a_fifth_of_the_twins_land_as_on_earth(twin)
    with pytest.raises(AssertionError, match=r"^the driest band lies at 58 degrees, with 273 mm"):
        test_on_the_twin_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40(twin, "north")
    with pytest.raises(AssertionError, match=r"^440 mm against 654 mm"):
        test_the_twins_land_between_40_and_60_north_gets_the_rain_of_earths(twin)
    test_on_the_twin_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40(twin, "south")      # the south meets it
