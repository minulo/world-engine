"""Single processes, and the whole engine on Earth's relief, judged against patterns of Earth (design, Layer 9).

The first part hands one process data sets of Earth (relief, rain, temperature) and asks for a pattern that an
atlas shows. Those runs are on the standard mesh, 163,842 cells about 60 km apart. The last part builds the Earth
twin, the whole engine on Earth's relief, on the preview mesh (10,242 cells about 240 km apart). The data is
fetched by tools/fetch_reference_data.py; without it every test here is skipped.

The inputs are data sets, not the truth. The relief is in whole metres on a grid of 9 km, the rain on a grid of
2.5 degrees and the temperature on one of 5 degrees; and no data set of snowfall is at hand, so the snow handed to
Hydrology is MADE from each month's mean temperature (earth_reference.Earth.snow_handed_in). Where a published
figure can be set beside it, over the Volga's basin, the snow made is 43 % of the precipitation and the published
share 30 %, and what the land sheds there follows the snow (the Volga's test, below).

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

The fifth check of build step 2 changed two things under every number of this file, and all of them were measured
again [MEASURED: the tools named below, run after the change]:
  * The water poured. The design's row asks for "the volume of sea water measured from that relief at full
    detail". Until then these tests poured the planet file's volume, 0.19 % less. The sea of the mesh then stood
    at -5.3 m, where it now stands at +1.9 m; 771 cells changed between land and sea; and the valley rule counted
    the data's shallow sea floor down to -5 m as land. The test of the sea water, below, holds what the other
    volume would decide.
  * What a random settlement of the ties draws: now also the order in which level ground is drained.

What the rivers of these tests can and cannot show [MEASURED: python tools/earth_relief.py, python
tools/earth_rivers.py --settlements 20; docs/BUILD_NOTES.md, section 4.4]. Four things stand between the relief
data and a river, and none of them is the process under test:
  * The data. ETOPO5 holds closed hollows and closed valleys of its own, on its grid of 9 km: 13 % of what is not
    ocean lies under water when every hollow of the data is full, and five of six narrows of great rivers looked
    at are closed in the data themselves. A river that goes astray there says nothing about Drainage.
  * Exact ties. The data come in whole metres, half of the land in steps of 100 feet. On the mesh a third of the
    land cells have a neighbour at exactly their own height, and where heights tie the data cannot say which way
    a river runs. The tests settle ties as the engine does (the wider way), and beside it at random, SETTLEMENTS
    times. A random settlement draws four things: the width of every way, the order of the cells, which of
    several passes of one height is taken, and the order in which level ground is drained. It does not draw the
    way across the water of a full hollow, which decides the cells the water passes and not where it leaves. A
    river whose outcome changes with the settling is decided by the ties and not by anything measured; its
    reason says so, with the count. A count is of the draws made: "in none of 20" rules out only what comes more
    often than about one time in seven. The counts of 100 draws are in docs/BUILD_NOTES.md, section 4.4 (python
    tools/earth_rivers.py --settlements 100); no test holds those. As the engine settles ties is one settlement
    among many, with no better claim to be Earth's than a random one: where the two disagree, the engine's
    outcome is no finding either way. [Twice a check found that "in all" and "in none" had been counted over
    draws that left a step out: the fourth, the choice among passes; the fifth, level ground.]
  * The valley rule. A river runs along the floor of its valley, not at the mean height of the 60 km around it.
    The design asked for "relief converted so that valley floors survive"; here a land cell's height for
    drainage is the height below which a tenth of its land points lie (earth_reference.VALLEY_SHARE). The tenth
    was chosen when this file was first written and has not been tuned since. The rule keeps valley floors and
    loses the ridges between them, and it leaves out the water in a cell: a land cell that holds an arm of the
    sea is handed in at the height of its shores. That closes the St Lawrence's estuary and raises the lakes
    that stand for the Black Sea and the Baltic (tests below).
  * The water poured, as above: it sets the level of the mesh's sea, and with it which cells are land, which
    points of a cell the valley rule counts, and where a river "leaves the land".
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
LEVEL_WITH_THE_WATER = 1747 # land cells whose ground lies exactly at the level to which the hollow around them fills
SEA_LEVEL_M = 1.9           # where the mesh's sea comes to rest under the water that the relief's own ocean holds


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
    """The design's: Earth's water on Earth's relief returns Earth's sea level and Earth's share of land. The water
    poured is the design's as well, "the volume of sea water measured from that relief at full detail": what the
    ocean of the relief data holds (the test after this one). The bounds were chosen when the test was written:
    the sea level within 60 m of zero, the sea over 69 to 73 % of the planet, one ocean. Found, then kept: the sea
    of the mesh comes to rest at +1.9 m and covers 70.75 % of the planet (the data's own ocean: 71.1 %). The lists
    of places below were written with the first run in view: found, then kept."""
    seas = earth.sea.tables["seas"]
    assert abs(earth.sea_level) < 60.0
    assert 0.69 < earth.area[earth.wet].sum() / earth.area.sum() < 0.73
    assert seas["volume_m3"][0] / seas["volume_m3"].sum() > 0.99
    assert abs(earth.sea_level - SEA_LEVEL_M) < 0.05 and abs(earth.area[earth.wet].sum() / earth.area.sum() - 0.7075) < 0.0005
    assert abs(seas["volume_m3"].sum() / earth.sea_volume - 1.0) < 1e-9          # SeaLevel poured what it was handed
    for name, place in {"the Mediterranean": (35.0, 18.0), "the Gulf of Mexico": (25.0, -90.0), "Hudson Bay": (60.0, -85.0),
                        "the Sea of Japan": (40.0, 135.0)}.items():
        assert earth.wet[earth.cell(*place)], name
    for name, place in {"Tibet": (33.0, 88.0), "the Sahara": (23.0, 5.0), "the Amazon lowland": (-3.0, -60.0), "the Caspian": (42.0, 51.0)}.items():
        assert not earth.wet[earth.cell(*place)], name                            # (the Caspian lies below sea level, behind a barrier)


def test_the_water_poured_is_what_the_ocean_of_the_relief_data_holds_and_what_the_other_volume_would_decide(earth, outcomes):
    """The design's row for SeaLevel asks for "the volume of sea water measured from that relief at full detail".
    That is 1.3376e18 m3: the depth below 0 m of every point of the data's own ocean (the water joined to the open
    Pacific below 0 m, so neither the Black Sea, which the data cut off, nor the Caspian), times the area the point
    stands for. It is worked out here once more by the plain rule (each point a square of 5 minutes of arc,
    narrowed by the cosine of its latitude). The planet file's 1.335e18 m3 is 0.19 % less; every point below 0 m,
    the Black Sea and the Caspian with it, would be 0.23 % more than the planet file's.
    Found, then kept: what the other volume decides. Until the fifth check of build step 2 these tests poured the
    planet file's, and no text said that it mattered. It does: the sea of the mesh stands 7.2 m lower, 771 cells
    change between land and sea, the heights handed to Drainage differ in 3,850 of the 47,962 cells that are land
    under both, and of the outcomes that the tests judge by, the Amazon's mouth moves from 203 to 354 km, one
    more river passes at its mouth and one fewer at its gauge, and the lake at the Caspian's place overflows by
    0.47 km3 a year where it now overflows by 17.9."""
    lat, lon, height = ref.relief()
    ocean = ref.ocean_of_grid(lat, lon, height)
    side = np.deg2rad(5.0 / 60.0) * R
    plain = float((np.where(ocean, -height.astype(np.float64), 0.0) * np.cos(np.deg2rad(lat))[:, None]).sum() * side * side)
    own = ref.relief_sea_volume()
    assert abs(own / 1.337585e18 - 1.0) < 1e-6 and abs(plain / own - 1.0) < 1e-5 and earth.sea_water == "relief" and earth.sea_volume == own
    planet = float(yaml.safe_load((DATA / "planet.yaml").read_text(encoding="utf-8"))["surface_water_volume_m3"])
    assert planet == 1.335e18 and abs(own / planet - 1.0019) < 0.0001
    everything_below = float((np.where(height < 0, -height.astype(np.float64), 0.0).sum(axis=1) * ref.box_areas(lat, lon)).sum())
    assert abs(everything_below / planet - 1.0023) < 0.0001
    row = lambda place: (int(np.argmin(np.abs(lat - place[0]))), int(np.argmin(np.abs(lon - place[1]))))
    assert not ocean[row((43.0, 34.0))] and not ocean[row(ref.CASPIAN)] and ocean[row((35.0, 18.0))] and height[row(ref.CASPIAN)] < 0
    assert abs(ref.box_areas(lat, lon).sum() * lon.size / (4.0 * np.pi * R * R) - 1.0) < 1e-6     # the boxes cover the sphere
    other = ref.Earth(LEVEL, sea_water="planet")
    assert other.sea_volume == planet and abs(other.sea_level + 5.26) < 0.05 and abs(earth.sea_level - other.sea_level - 7.2) < 0.1
    assert (int(other.land.sum()), int(earth.land.sum()), int((other.wet != earth.wet).sum())) == (48733, 47962, 771)
    both = other.land & earth.land
    assert int(both.sum()) == 47962 and int((other.ground != earth.ground)[both].sum()) == 3850
    then, now = ref.summary(other), outcomes["engine"]
    near = lambda r: sum(km < ref.MOUTH_WITHIN_KM for km in r["mouth_km"].values())
    within = lambda r: sum(within_a_factor_of_two(ref.GAUGES[river][2], flow) for river, flow in r["flow"].items())
    assert (near(then), near(now), within(then), within(now)) == (16, 15, 7, 8)
    assert abs(then["mouth_km"]["Amazon"] - 203.0) < 5.0 and abs(now["mouth_km"]["Amazon"] - 354.0) < 5.0
    assert then["caspian"]["overflows"] and abs(then["caspian"]["outflow_km3"] - 0.47) < 0.05 and abs(now["caspian"]["outflow_km3"] - 17.9) < 0.2
    black_sea = other.lake_at(43.0, 34.0)                                        # under the other water this lake stood at the sea's level
    assert abs(black_sea["area_m2"] / 1e6 - 472_814) < 500 and black_sea["level_m"] == 0.0
    with pytest.raises(ValueError, match="sea_water can be 'relief' or 'planet', not 'tap'"):
        ref.Earth(LEVEL, sea_water="tap")


STRAITS = {
    "the Black Sea": ((43.0, 34.0), "The relief data cut the Black Sea off themselves: on their own grid the lowest way from it to the ocean "
                                    "rises to 2 m above the sea [MEASURED]. A mesh that follows these data cannot join it to the ocean "
                                    "[INFERRED]. Hydrology fills it as a lake."),
    "the Red Sea": ((20.0, 38.5), "In the data the Red Sea is joined to the ocean. On the mesh a cell is sea only if the poured water covers "
                                  "its mean height, and the cell that holds the strait, at 13.1 north, has a mean height of 15.8 m though 65 % "
                                  "of its points are ocean in the data [MEASURED]. The fourth check of build step 2 had laid a like case, the "
                                  "St Lawrence, to the width of a cell; the fifth found that this one had been left so."),
    "the Baltic": ((58.0, 20.0), "In the data the Baltic is joined to the ocean. The cell that keeps it apart on the mesh, at 55.1 north, 10.9 "
                                 "east, has a mean height of 2.1 m, a hand's breadth above the mesh's sea at 1.9 m, though 75 % of its points "
                                 "are ocean in the data [MEASURED]. Hydrology fills it as a lake.")}


@pytest.mark.parametrize("name", [pytest.param(name, marks=missed(reason)) for name, (place, reason) in STRAITS.items()])
def test_a_sea_behind_a_narrow_strait_is_part_of_the_ocean(earth, name):
    """Stated as misses when the first run showed them. The reasons say where each sea is lost [MEASURED: the test
    below]."""
    assert earth.wet[earth.cell(*STRAITS[name][0])], name


def test_where_the_seas_behind_straits_are_lost(earth, flood):
    """Found, then kept: it keeps the reasons above true. The Black Sea is no part of the ocean in the data
    themselves: the lowest way from it to the ocean rises to 2 m. The Red Sea and the Baltic are ocean in the data
    and not sea on the mesh: each is kept apart by one cell most of whose points are ocean in the data, and whose
    mean height stands above the mesh's sea. The Caspian is cut off in both, as it should be: the data join it to
    the ocean at 91 m."""
    at = lambda name: ref.raw_at(flood, *STRAITS[name][0])
    assert not at("the Black Sea")["ocean"] and at("the Black Sea")["level"] == 2.0
    assert at("the Red Sea")["ocean"] and at("the Baltic")["ocean"]
    for name, (lat, lon, mean, share, handed) in {"the Red Sea": (13.1, 43.2, 15.8, 0.65, 107.0), "the Baltic": (55.1, 10.9, 2.1, 0.75, 4.0)}.items():
        k = ref.kept_apart(earth, flood, STRAITS[name][0])
        assert abs(k["lat"] - lat) < 0.1 and abs(k["lon"] - lon) < 0.1 and abs(k["mean_m"] - mean) < 0.1 and abs(k["ocean_share"] - share) < 0.01, (name, k)
        assert k["handed_m"] == handed and k["mean_m"] > earth.sea_level and not earth.wet[k["cell"]]
    assert ref.kept_apart(earth, flood, (35.0, 18.0)) is None                    # the Mediterranean is sea on the mesh: nothing keeps it apart
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
    Both meet it as the engine settles ties, at 354 and 270 km, and in every one of 20 random settlements. [Under
    the planet file's water, which these tests poured until the fifth check of build step 2, the Nile met it in 10
    of 20.] The Nile meets it by distance alone: between 26 and 30 degrees north the mesh's Nile runs west of 28.5
    east, where the real river runs east of 30.5, and it reaches the coast 270 km west of the delta [MEASURED:
    python tools/earth_rivers.py --trace Nile, and the last assertion; UNVERIFIED, from memory: where the real
    river runs]."""
    basin = earth.drainage.fields["basin_id"]
    amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
    assert earth.km(amazon, -0.5, -50.0) < 600.0 and earth.km(nile, 31.5, 31.0) < 600.0
    assert abs(earth.km(amazon, -0.5, -50.0) - 354.0) < 5.0 and abs(earth.km(nile, 31.5, 31.0) - 270.0) < 5.0
    area = earth.drainage.fields["drainage_area"]
    assert 4.5e12 < area[amazon] < 8.0e12 and 2.5e12 < area[nile] < 4.5e12        # m2
    assert sum(r["mouth_km"]["Amazon"] < 600.0 for r in drawn(outcomes)) == SETTLEMENTS
    assert sum(r["mouth_km"]["Nile"] < 600.0 for r in drawn(outcomes)) == SETTLEMENTS
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
    "Amazon": "354 km, as the engine settles ties and in every one of 20 random settlements. The mesh's river runs east from "
              "Manaus between 3 and 1.7 degrees south and meets the mesh's sea at 53 degrees west: the sea cell there has a "
              "mean height of -2 m, below the mesh's sea at +1.9 m, and lies 297 km from the place taken as the mouth. Under "
              "the planet file's water, 0.19 % less, the sea stood 7 m lower and the river left the land 203 km from that "
              "place. The water poured decides this one; and the condition measures how far the mesh's sea reaches up the "
              "estuary as much as it measures the river's way [INFERRED from the two runs].",
    "Congo": "603 km as the engine settles ties, 603 to 668 km in 20 random settlements, within 300 km in none. The data close "
             "the river's valley themselves: on their own grid the valley from Bolobo to Kinshasa rises to 610 m, where the "
             "river above it stands at 274 m, and the basin is joined to the ocean at 457 m by another way. On the mesh the "
             "basin fills as a lake of 880,226 km2 to 457 m and overflows westward, to the sea at 1.5 degrees south.",
    "Ob": "586 km as the engine settles ties, 581 to 631 km in 20 random settlements, within 300 km in none. The mesh's river "
          "comes within 71 km of its real mouth, at the head of its estuary, and runs on: from there to the sea its way "
          "crosses a hollow that is full to 30 m. The Gulf of Ob is ocean in the data, 3 to 13 m deep; of seven cells along "
          "it none is sea on the mesh. Their mean heights run from -7 to 8 m: three stand above the mesh's sea at +1.9 m, "
          "and the sea does not reach the four that lie below it.",
    "Danube": "579 km as the engine settles ties and in every one of 20 random settlements. The mesh's river passes the Iron "
              "Gate, where the valley rises to 208 m, the level of the lake that stands above it, and enters the lake that "
              "fills the hollow of the Black Sea to 32 m, 203 km from its real mouth at the nearest. With every hollow full "
              "the water goes on across that lake and leaves the land at the Dardanelles. The relief data cut the Black Sea "
              "off from the ocean themselves (STRAITS), so the river of a sea that is a lake on the mesh is asked where the "
              "lake's water leaves the land: it cannot meet the condition as it was written [INFERRED]. [Under the planet "
              "file's water the plain above the Iron Gate overflowed to the Adriatic instead, 1,212 km from the mouth.]",
    "Yenisei": "398 km as the engine settles ties; 294 to 398 km in 20 random settlements, within 300 km in 1: the ties "
               "decide, and mostly against the river. Near 66 degrees north the mesh's river turns west, across a hollow "
               "that is full to 30 m, and passes four cells whose centres are ocean in the data and which are not sea on "
               "the mesh (see the Ob): it leaves the land with the Ob.",
    "Volga": "1,865 km, however the ties are settled. Not a fault of the relief or of the mesh. The Volga ends in the Caspian, "
             "a closed sea, and this condition follows the water on as if every hollow were full: over the rim of the "
             "Caspian's hollow at 62 m, across the lake that fills the hollow of the Black Sea and out at the Dardanelles. "
             "A river of a closed sea cannot meet the condition as it was written. Where the mesh's Volga ends is tested "
             "with the Caspian, below.",
    "St Lawrence": "1,090 km in every one of 20 random settlements. In the data the estuary below Quebec is open to the sea. It "
                   "is closed by the way the relief is put on the mesh: two of the cells that hold the estuary are land on "
                   "the mesh by their mean heights though 62 % and 32 % of their points are ocean in the data, and the valley "
                   "rule gives a land cell the height of its land points alone, 162 and 204 m. The river above fills a lake "
                   "to 102 m, which overflows southward and leaves the land at 41 degrees north. With the ocean points of "
                   "each cell counted as well, at the level of the sea, the valley is open and the river leaves the land 232 "
                   "km from its mouth; that reading sends the Danube to the Adriatic and is no mend (the test of the "
                   "estuary, below).",
    "Amur": "1,290 km as the engine settles ties and in every one of 20 random settlements. The data close the lower river "
            "themselves: on their own grid the valley below Komsomolsk rises to 213 m, where the river stands at 76 m, and the "
            "lowland above it is joined to the ocean at 122 m by a way south. On the mesh the valley rises to 137 m; the "
            "lowland fills as a lake of 180,651 km2 to 107 m and its water leaves south, to the Sea of Japan.",
    "Huang He": "1,215 km as the engine settles ties, and within 300 km in 13 of 20 random settlements (203 km at the "
                "nearest): the ties decide, and the engine's way of settling them gives the rarer outcome. As the engine "
                "settles ties, the river's way to the sea crosses 48 cells under the water of full hollows and 4 of level "
                "ground, runs north-east as far as 53.6 degrees north, and leaves the land where the mesh's Amur does."}

# For every great river: how far from its real mouth it leaves the land when the ties are settled as the engine settles
# them (km), and in how many of the SETTLEMENTS random settlements it does so within 300 km.
MOUTHS = {"Amazon": (354, 0), "Nile": (270, 20), "Mississippi": (295, 20), "Congo": (603, 0), "Yangtze": (60, 12), "Ob": (586, 0),
          "Mackenzie": (26, 20), "Danube": (579, 0), "Ganges": (253, 20), "Parana": (20, 20), "Niger": (142, 20), "Lena": (206, 13),
          "Yenisei": (398, 1), "Indus": (75, 20), "Murray": (33, 20), "Volga": (1865, 0), "Zambezi": (101, 20), "Orinoco": (244, 20),
          "St Lawrence": (1090, 0), "Columbia": (115, 20), "Rhine": (99, 20), "Mekong": (292, 20), "Amur": (1290, 0), "Huang He": (1215, 13)}

# Six narrows of great rivers. On the mesh: the height to which the valley's floor rises, and the level of the lake that
# stands above it. In the data, on their own grid of 5 minutes of arc: the height of the river above the narrows, the
# height to which its valley rises, and the level at which the place is joined to the ocean by any way (None: the place
# is open to the sea). Metres.
NARROWS_ON_THE_MESH = {"Congo": (518, 457), "Danube": (208, 208), "Lena": (137, 122), "St Lawrence": (204, 102), "Amur": (137, 107),
                       "Yangtze": (762, 396)}
NARROWS_IN_THE_DATA = {"Congo": (274, 610, 457), "Danube": (98, 317, 317), "Lena": (91, 152, 152), "St Lawrence": None,
                       "Amur": (76, 213, 122), "Yangtze": (404, 945, 823)}


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(MISLED[name])) if name in MISLED else name for name in ref.GREAT_RIVERS])
def test_a_great_river_reaches_the_sea_where_it_does_on_earth(earth, river):
    """Each of 24 great rivers, with every hollow on its way full, leaves the land within 300 km of its real mouth.
    Found, then kept: the test came into the repository together with its first results, under the name
    test_two_thirds_of_the_great_rivers_reach_the_sea_where_they_do_on_earth, and no record shows the list of
    rivers or the 300 km set before a run. Neither has been changed since. The ties are settled as the engine
    settles them: 15 of the 24 pass, and each of the other 9 is an expected failure of its own, with its distance
    and what was measured about its cause. Four of the 24 are decided by the ties, two of them among the 15 that
    pass (the Yangtze and the Lena) and two among the 9 that fail (the Yenisei and the Huang He): for those four
    neither the pass nor the failure is a finding (MOUTHS, and the test after the next). The water poured decides
    one more, the Amazon. The condition asks where the water leaves the land and not by which way: the Yangtze,
    the Lena and the Nile meet it by ways that are not their valleys (python tools/earth_rivers.py --trace; the
    test after the next holds where those ways run)."""
    place, mouth = ref.GREAT_RIVERS[river]
    km = earth.km(int(earth.drainage.fields["basin_id"][earth.cell(*place)]), *mouth)
    assert km < ref.MOUTH_WITHIN_KM, f"{river}: {km:.0f} km from its mouth"


def test_a_settlement_of_the_ties_reaches_drainage_and_hydrology_alike(earth):
    """Earth.settled(seed) must hand its ties to both processes: Hydrology settles the ways across its lakes, and if
    it kept the mesh's own ties while Drainage took the drawn ones, the two would disagree about where a lake's water
    goes and every "in 20 random settlements" of these tests would mean less than it says. And it must draw all four
    things that the texts say it draws: the last, the order in which level ground is drained, was added by the
    fifth check of build step 2, and is held here by what it changes."""
    from worldengine.library import drainage as dr
    other = earth.settled(3)
    given = other._ties()
    surface, full = other.full_ways()
    assert np.array_equal(other.drainage.fields["flow_receiver"], dr.receivers(surface, earth.wet, earth.mesh.nbr, earth.ground, given))
    assert (other.drainage.fields["flow_receiver"] != earth.drainage.fields["flow_receiver"]).sum() > 1000      # the case: the draw changes many ways
    handed = other.books()["ties"]
    assert np.array_equal(handed.rank, given.rank) and np.array_equal(handed.edge, given.edge) and np.array_equal(handed.way, given.way)
    assert given.passes is not None and np.array_equal(handed.passes, given.passes)
    assert given.level is not None and given.level.shape == (earth.mesh.n,) and np.array_equal(handed.level, given.level)
    own = earth.books()["ties"]
    mesh = dr.mesh_ties(earth.mesh)
    assert np.array_equal(own.rank, mesh.rank) and np.array_equal(own.edge, mesh.edge) and own.passes is None and own.level is None
    assert not np.array_equal(handed.edge, mesh.edge)
    # level ground: the same draw without its fourth part gives other ways, and on level ground alone
    without = dr.receivers(surface, earth.wet, earth.mesh.nbr, earth.ground, given._replace(level=None))
    drained = other.drainage.fields["flow_receiver"]
    moved = np.flatnonzero(drained != without)
    assert moved.size > 500 and (surface[without[moved]] == surface[moved]).all() and (surface[drained[moved]] == surface[moved]).all()
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
    In a random settlement 13 to 16 rivers pass. Thirteen pass in all 20 and seven in none; four are decided by the
    ties: the Yangtze (12 of 20), the Lena (13), the Yenisei (1) and the Huang He (13). The Yangtze and the Lena pass
    as the engine settles ties, the Yenisei and the Huang He fail: none of the four is a finding. Two more pass by
    less than 10 km in every settlement: the Mississippi at 295 km and the Mekong at 292.
    [Twice these counts claimed more than was drawn. Until the fourth check of build step 2 a random settlement
    left the choice among passes of one height as the engine makes it; until the fifth, the order in which level
    ground is drained.]"""
    assert set(MOUTHS) == set(ref.GREAT_RIVERS)
    near = lambda r, river: r["mouth_km"][river] < ref.MOUTH_WITHIN_KM
    got = {river: (round(outcomes["engine"]["mouth_km"][river]), sum(near(r, river) for r in drawn(outcomes))) for river in MOUTHS}
    off = {river: got[river] for river in MOUTHS if abs(got[river][0] - MOUTHS[river][0]) > 5 or got[river][1] != MOUTHS[river][1]}
    assert not off, off
    counts = [sum(near(r, river) for river in MOUTHS) for r in drawn(outcomes)]
    assert (min(counts), max(counts)) == (13, 16) and sum(near(outcomes["engine"], river) for river in MOUTHS) == 15
    assert {river for river, (_, k) in MOUTHS.items() if 0 < k < SETTLEMENTS} == {"Yangtze", "Lena", "Yenisei", "Huang He"}
    assert {river for river, (_, k) in MOUTHS.items() if k == 0} == set(MISLED) - {"Huang He", "Yenisei"}
    assert sum(k == SETTLEMENTS for _, k in MOUTHS.values()) == 13 and sum(k == 0 for _, k in MOUTHS.values()) == 7
    spread = lambda river: (min(r["mouth_km"][river] for r in drawn(outcomes)), max(r["mouth_km"][river] for r in drawn(outcomes)))
    for river, (low, high) in {"Amazon": (354, 354), "Congo": (603, 668), "Ob": (581, 631), "Danube": (579, 579), "Amur": (1290, 1290),
                               "St Lawrence": (1090, 1090), "Volga": (1865, 1865), "Huang He": (203, 1215), "Yenisei": (294, 398),
                               "Mississippi": (295, 295), "Mekong": (292, 292), "Yangtze": (60, 787), "Lena": (206, 302),
                               "Nile": (121, 270)}.items():                           # what the reasons and the texts quote
        assert abs(spread(river)[0] - low) < 5 and abs(spread(river)[1] - high) < 5, (river, spread(river))
    land_way = lambda river: [c for c in ref.way_of(earth, river) if c["step"] != "sea"]
    # what the reasons say of the Amazon's way: east between 3 and 1.7 south to 53 west, where a cell of the mesh's sea lies 297 km from the mouth
    way = ref.way_of(earth, "Amazon")
    assert all(-3.2 < c["lat"] < -1.6 for c in way) and all(a["lon"] < b["lon"] for a, b in zip(way, way[1:]))
    assert abs(way[-2]["lon"] + 53.0) < 0.1 and way[-1]["step"] == "sea" and abs(way[-1]["mean_m"] + 2.1) < 0.1 and abs(way[-1]["km_to_mouth"] - 297.0) < 3.0
    # ... of the Ob's: it reaches the head of its estuary, which the data have as ocean and the mesh has not, and crosses a full hollow from there
    way = land_way("Ob")
    assert abs(min(c["km_to_mouth"] for c in way) - 71.0) < 5.0
    beyond = [c for c in way if c["lat"] > 67.0]
    assert [c["step"] for c in beyond] == ["lake"] * 10 + ["level", "down"] and all(c["lake_level_m"] == 30.0 for c in beyond[:10])
    gulf = [(lat, 73.3) for lat in (67.5, 68.0, 69.0, 69.5, 70.0, 70.5, 71.0)]
    assert all(ref.raw_at(flood, *place)["ocean"] and -13.0 <= ref.raw_at(flood, *place)["height"] <= -3.0 for place in gulf)
    assert not any(earth.wet[earth.cell(*place)] for place in gulf)
    means = [earth.mean[earth.cell(*place)] for place in gulf]
    assert all(-7.5 < mean < 8.5 for mean in means) and abs(earth.sea_level - SEA_LEVEL_M) < 0.05
    assert (sum(mean > earth.sea_level for mean in means), sum(mean < earth.sea_level for mean in means)) == (3, 4)
    # ... of the Yenisei's: westward near 66 north across a hollow full to 30 m, over four cells that are ocean in the data, to the Ob's end
    yenisei = land_way("Yenisei")
    west = [c for c in yenisei if 66.2 < c["lat"] < 67.2]
    assert len(west) == 4 and all(c["step"] == "lake" and c["lake_level_m"] == 30.0 for c in west) and all(a["lon"] > b["lon"] for a, b in zip(west, west[1:]))
    assert sum(ref.raw_at(flood, c["lat"], c["lon"])["ocean"] for c in yenisei) == 4 and yenisei[-1]["cell"] == way[-1]["cell"]
    # ... of the Huang He's
    way = land_way("Huang He")
    assert (sum(c["step"] == "lake" for c in way), sum(c["step"] == "level" for c in way)) == (48, 4)
    assert abs(max(c["lat"] for c in way) - 53.6) < 0.1 and way[-1]["cell"] == land_way("Amur")[-1]["cell"]
    # ... of the Danube's and the Volga's: into the lake at the Black Sea's place, and out at the Dardanelles
    danube, volga = land_way("Danube"), land_way("Volga")
    assert abs(min(c["km_to_mouth"] for c in danube) - 203.0) < 5.0 and danube[-1]["cell"] == volga[-1]["cell"]
    assert abs(danube[-1]["lat"] - 40.5) < 0.1 and abs(danube[-1]["lon"] - 26.7) < 0.1
    assert sum(c["lake_level_m"] == 32.0 for c in danube) >= 10 and sum(c["lake_level_m"] == 32.0 for c in volga) >= 20
    assert [c["ground_m"] for c in volga if c["step"] == "down"] == [62.0, 21.0]         # over the Caspian's rim, and out of the lake
    # ... and the three that meet the condition by ways that are not their valleys (the Nile's: the test of the Nile, above)
    assert all(c["lat"] < 29.0 for c in land_way("Yangtze") if 108.0 < c["lon"] < 112.5)      # the real river runs north of 29.5 there [UNVERIFIED]
    assert all(c["lon"] < 123.0 for c in land_way("Lena") if c["lat"] > 70.0) and ref.GAUGES["Lena"][1] == 127.4   # its last gauge stands at 127.4 east


def test_the_narrows_are_closed_in_the_data_before_the_mesh_closes_them(earth, flood):
    """Found, then kept: it keeps true what the reasons say about narrows. In five of six valleys the mesh's ground
    rises above the level of the lake that stands above the narrows; four of those lakes overflow by another way,
    and the fifth, in the Sichuan basin above the Three Gorges, keeps its water. In the sixth, the Danube's Iron
    Gate, the valley rises to 208 m and the lake above it stands at 208 m: the plain fills until its water runs
    through the gate. Five of the six are closed in the relief data themselves, on their own grid of 9 km, where
    the valley rises far above the river. Only the estuary of the St Lawrence is open in the data and closed on
    the mesh, and what closes it there is the valley rule of the harness, not the width of a cell (the test after
    this one).
    [The third check of build step 2 found the first. I had laid all six to the mesh. The fourth found the second:
    I had laid the St Lawrence to the mesh's spacing.]"""
    found = ref.narrows(earth)
    assert set(found) == set(NARROWS_ON_THE_MESH)
    for river, (barrier, lake) in NARROWS_ON_THE_MESH.items():
        r = found[river]
        assert abs(r["barrier_m"] - barrier) <= 1.0 and abs(r["lake_level_m"] - lake) <= 1.0, (river, r)
        assert (r["barrier_m"] > r["lake_level_m"]) == (river != "Danube") and r["lake_overflows"] == (river != "Yangtze")
    raw = ref.raw_narrows(flood)
    for river, heights in NARROWS_IN_THE_DATA.items():
        r = raw[river]
        if heights is None:
            assert r["start_m"] < 0.0 and np.isnan(r["to_ocean_m"]), (river, r)   # the place itself is ocean in the data
        else:
            assert (r["start_m"], r["barrier_m"], r["to_ocean_m"]) == heights, (river, r)
            assert r["barrier_m"] > r["start_m"] + 50.0                           # closed, and by far more than a step of 100 feet
    # the Danube's water passes the gate and leaves the land at the Dardanelles
    danube = found["Danube"]
    assert danube["barrier_m"] == danube["lake_level_m"] == 208.0 and abs(danube["leaves_at"][0] - 40.5) < 0.1 and abs(danube["leaves_at"][1] - 26.7) < 0.1


def test_the_estuary_of_the_st_lawrence_is_closed_by_the_valley_rule_and_not_by_the_width_of_a_cell(earth, flood):
    """Found, then kept: it keeps the St Lawrence's reason in MISLED and docs/BUILD_NOTES.md, section 4.4, true.
    A cell is sea on the mesh if the poured water covers its mean height. A cell that holds an arm of the sea
    between high shores is therefore land, and the valley rule hands it to Drainage at the height below which a
    tenth of its points ABOVE the sea lie: the water in it is left out. Two such cells stand in the St Lawrence's
    way. Of the 3,418 land cells of which a tenth or more is ocean in the data, 2,956 are handed in above 10 m and
    1,125 above 100 m.
    The other reading, as a diagnosis (earth_reference.other_valley_reading): the ocean points of a cell counted
    as well, at the level of the mesh's sea. It opens the estuary, and the river then leaves the land 232 km from
    its mouth. It is no mend. It hands in 3,448 land cells at the sea's own level, a range on a coast among them:
    the Danube's water then leaves for the Adriatic, 1,212 km from its mouth, over a cell whose mean height is
    544 m. Sixteen of the 24 great rivers then meet their condition where fifteen do as built, eight of the 21
    gauges under either reading, and lakes cover 5.6 % of the land where they cover 6.3 %. The tests stay on the
    rule as it was first chosen: the other was looked at with the results of the first in view.
    [Until the fifth check of build step 2 the diagnosis counted every point of a cell with its depth below the
    sea, which floods the coasts; it was said to be "no better rule" on that ground.]"""
    held = ref.data_points_of_cells(earth, flood)
    share, land = held["ocean_share"], earth.land
    assert share.min() >= 0.0 and share.max() <= 1.0 and share[earth.cell(*ref.OPEN_OCEAN)] == 1.0 and share[earth.cell(33.0, 88.0)] == 0.0
    closing = [earth.cell(47.3, -70.6), earth.cell(47.4, -69.9)]                  # two cells on the estuary below Quebec
    assert [(bool(land[c]), round(float(earth.ground[c])), round(100 * float(share[c]))) for c in closing] == [(True, 162, 62), (True, 204, 32)]
    assert all(earth.mean[c] > 150.0 for c in closing)                           # land by their mean heights, with half their points in the sea
    built = ref.narrows(earth)["St Lawrence"]
    assert built["barrier_m"] == 204.0 and built["lake_level_m"] == 102.0 and abs(built["barrier_at"][0] - 47.4) < 0.1
    assert abs(built["leaves_at"][0] - 40.9) < 0.1 and abs(built["leaves_at"][1] + 73.9) < 0.1
    much = land & (share >= 0.1)
    assert (int(much.sum()), int((much & (earth.ground > 10.0)).sum()), int((much & (earth.ground > 100.0)).sum())) == (3418, 2956, 1125)
    ground_before, drainage_before = earth.ground.copy(), earth.drainage
    o = ref.other_valley_reading(earth, flood)
    other = o["earth"]
    assert np.array_equal(earth.ground, ground_before) and earth.drainage is drainage_before      # the Earth of the tests is left as it was
    at_sea = float(np.float32(earth.sea_level))
    assert [float(other.ground[c]) for c in closing] == [at_sea, at_sea]
    assert (o["changed"], o["at_sea"]) == (4086, 3448) and int((land & (share >= 0.2) & (other.ground != at_sea)).sum()) == 0
    assert int((land & (share == 0.0) & (other.ground != earth.ground)).sum()) == 0      # a cell with no ocean in it is handed in as before
    opened = ref.narrows(other)["St Lawrence"]
    assert opened["barrier_m"] == 84.0 and opened["lake_level_m"] is None       # the valley rises no higher than the place the river starts from
    moved = {river: (round(a), round(b)) for river, (a, b) in o["moved"].items()}
    assert moved == {"Yangtze": (60, 100), "Ob": (586, 581), "Mackenzie": (26, 32), "Danube": (579, 1212), "Yenisei": (398, 343), "Murray": (33, 74),
                     "Orinoco": (244, 192), "St Lawrence": (1090, 232), "Amur": (1290, 1274), "Huang He": (1215, 1261)}, moved
    assert (o["built"]["mouths"], o["other"]["mouths"], o["built"]["gauges"], o["other"]["gauges"]) == (15, 16, 8, 8)
    assert abs(o["built"]["lakes_share"] - 0.0628) < 0.0003 and abs(o["other"]["lakes_share"] - 0.0557) < 0.0003
    danube = ref.narrows(other)["Danube"]
    assert abs(danube["leaves_at"][1] - 14.2) < 0.5 and abs(danube["over_mean_m"] - 544.0) < 2.0 and danube["handed_m"] == at_sea


def test_how_coarse_the_relief_is_and_what_settles_its_ties(earth):
    """Found, then kept: it keeps true what this file and docs/BUILD_NOTES.md say about the relief data and about
    ties. ETOPO5 is in whole metres, 48 % of its land in steps of 100 feet. On the mesh 34.4 % of the land cells
    have a land neighbour at exactly their own height. Of the land cells that have a lower neighbour, 22.6 % have
    several equally low: the bed settles a third of those (cells with several neighbours in the sea), the wider
    way two thirds, and the cell numbers 51 cells. With the wider way left out, as it was before the third check,
    the water of 14.9 % of the land reached the sea in another cell; with the order of the cells turned round, as
    things stand, of 0.04 %. Another 4,578 land cells lie on level ground.
    On coasts: 248 of 4,800 coastal land cells are handed in no more than 5 m above the mesh's sea, 10 of them
    with a mean height above 300 m (cells that hold a shore and a range); and 437 land cells are handed in at or
    below the level of that sea, dry ground that the sea does not reach."""
    s = ref.relief_steps(earth)
    assert s["whole_metres"] and 0.45 < s["hundred_feet_share"] < 0.50
    assert (s["land_cells"], s["tied_cells"]) == (47962, 16510)
    assert [height for height, _ in s["commonest"][:2]] == [91.0, 61.0]
    assert (s["coast_cells"], s["coast_low"], s["coast_low_but_high"], s["at_or_below_sea"]) == (4800, 248, 10, 437) and ref.COAST_LOW_M == 5.0
    t = ref.tie_counts(earth)
    assert (t["choose"], t["tied"], t["by_bed"], t["by_width"], t["by_number"], t["level"]) == (42657, 9641, 3341, 6249, 51, 4578)
    assert 0.0002 < t["mouth_moved_by_numbers"] < 0.0006 and 0.14 < t["mouth_moved_by_width"] < 0.16     # (a measure that measured nothing would give 0)


def test_the_data_hold_most_of_the_great_lakes_that_the_mesh_shows(earth, flood):
    """Found, then kept. Of all that is not ocean in the data, 13.3 % lies under water when every hollow of the data
    is full, on the data's own grid; on the mesh, with the valley rule, 10.5 %. Eleven of the mesh's twelve lakes
    larger than 100,000 km2 lie in hollows that the data hold as well; the twelfth is the Baltic, which the data
    join to the ocean. Five of the eleven have their lowest points where Earth has a sea or a great lake, though
    not one of their size: the Caspian, the Black Sea, the upper Great Lakes, Lake Ontario and Great Slave Lake.
    Six stand where Earth has no such water: in the basins of the Congo, the Amazon and the Danube, on the West
    Siberian plain and in the lowlands of the Amur and the Lena [UNVERIFIED, from memory: which waters Earth has
    at those places]."""
    r = ref.raw_hollows(flood)
    assert abs(r["not_ocean"] - 0.133) < 0.002 and abs(r["land"] - 0.126) < 0.002 and abs(r["ocean_share_of_planet"] - 0.711) < 0.002
    from worldengine.library import drainage as dr
    label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
    full = table["spill_m"][dr.top_hollows(table)[label]]
    under = earth.land & (label > 0) & (earth.ground < np.where(np.isnan(full), np.inf, full))
    assert abs(earth.area[under].sum() / earth.area[earth.land].sum() - 0.105) < 0.002
    # the same from the harness, which the tools print: "under water" is ground below the level, as in the data's own count
    # (level > height). Ground exactly at the level is another 3.7 % of the land on this relief of whole metres, and is not counted
    h = ref.mesh_hollows(earth)
    assert np.array_equal(h["under"], under) and int(under.sum()) == 4948
    level_with = earth.land & (label > 0) & (earth.ground == np.where(np.isnan(full), np.inf, full))
    assert int(level_with.sum()) == LEVEL_WITH_THE_WATER and abs(h["under_share"] - 0.1051) < 0.0005 and abs(h["under_share_60"] - 0.1190) < 0.0005
    assert abs(h["not_sea_share"] - 0.2925) < 0.0005 and abs(h["closed_hollow_share"] - 0.6239) < 0.0005
    lakes = earth.hydrology().tables["lakes"]
    big = np.flatnonzero(lakes["area_m2"] > 1.0e11)
    held, at = [], []
    for i in big:
        c = int(lakes["bottom_cell"][i])
        x = ref.raw_at(flood, float(earth.mesh.lat[c]), float(earth.mesh.lon[c]))
        held.append((not x["ocean"]) and x["level"] > x["height"])
        at.append((float(earth.mesh.lat[c]), float(earth.mesh.lon[c])))
    assert big.size == 12 and sum(held) == 11
    # the twelve, by the lowest point of each (degrees north, east); the one that lies in no hollow of the data is the Baltic's
    lowest = {"the Caspian": (38.7, 49.1), "the Black Sea": (43.3, 36.8), "the upper Great Lakes": (47.5, -86.9), "Lake Ontario": (43.6, -78.6),
              "Great Slave Lake": (61.2, -115.2), "the Congo's basin": (-3.0, 16.5), "the Amazon's": (0.0, -63.0), "the Danube's": (44.7, 20.4),
              "West Siberia": (58.2, 68.4), "the Amur's lowland": (50.1, 136.5), "the Lena's": (65.9, 125.0), "the Baltic": (57.3, 19.9)}
    for name, (lat, lon) in lowest.items():
        found = [k for k, (a, b) in enumerate(at) if abs(a - lat) < 0.1 and abs(b - lon) < 0.1]
        assert len(found) == 1 and held[found[0]] == (name != "the Baltic"), name
    for place, height, level in (((-3.0, 16.5), 274.0, 457.0), ((0.0, -63.0), 30.0, 61.0), ((58.2, 68.4), 61.0, 91.0)):
        x = ref.raw_at(flood, *place)                                             # the Congo's basin, the Amazon's, West Siberia
        assert (x["height"], x["level"]) == (height, level), (place, x)


# ---------------------------------------------------------------------------------------------- Hydrology
def test_under_earths_rain_and_warmth_the_land_gives_back_what_earths_land_gives_back(earth, outcomes):
    """The bounds were chosen when the test was written: of the rain on land, between 0.50 and 0.75 goes back to the air,
    and 28,000 to 52,000 km3 a year reach the sea. Earth: 74 of 114 thousand km3 go back, 0.65, and 40 thousand
    reach the sea [DOCUMENTED when build step 2 was written: Trenberth, Fasullo and Mackaro 2011].
    The engine: 0.738 goes back and 30.7 thousand km3 reach the sea, of 117.2 thousand that GPCP's rain puts on the
    mesh's land [MEASURED: python tools/earth_rivers.py, part 5]. Inside the range, at its dry end: the land gives
    the air too much and the rivers too little, on 3 % more rain than the budget's. 0.708 would go back if no cell
    were flooded, and the lakes give the air the rest. These totals hardly depend on how the ties are settled:
    over 20 random settlements 0.7380 to 0.7385 and 30.66 to 30.72."""
    f = earth.hydrology().fields
    fell = (earth.rain.sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * earth.area)[earth.land].sum() / 1000.0
    to_sea = f["river_discharge"].astype(np.float64)[:, earth.wet].mean(axis=0).sum() * YEAR_S
    assert 0.50 < to_air / fell < 0.75
    assert 28.0e12 < to_sea < 52.0e12
    assert abs((fell - to_air) / to_sea - 1) < 1e-3            # and none is lost on the way
    assert not earth.hydrology().notices
    assert all(0.7376 < r["back_to_air"] < 0.7389 and 30.60 < r["to_sea"] < 30.78 for r in outcomes.values())
    from worldengine.library import drainage as dr
    assert dr.mesh_ties.__name__ == "mesh_ties"               # the settlements left the library as they found it


def test_the_amazon_carries_the_most_water(earth):
    """The design's: the Amazon carries the most water. Chosen when the test was written: that the largest flow into
    the sea lies within 800 km of the Amazon's mouth and is within a factor of two of the Amazon's, 6,642 km3 a
    year at its mouth, 210,000 m3/s [DOCUMENTED: Dai and Trenberth, Table 2]. Two things are asked, because two
    cells can be called the largest flow into the sea: the sea cell that receives the most (on the mesh one sea
    cell can take the water of two mouths), and the land cell that carries the most. The engine gives 144,605 and
    144,453 m3/s, 0.69 of the Amazon's [MEASURED]."""
    river = earth.hydrology().fields["river_discharge"].astype(np.float64).mean(axis=0)
    into_sea = int(np.argmax(np.where(earth.wet, river, -1.0)))
    on_land = int(np.argmax(np.where(earth.land, river, -1.0)))
    for cell in (into_sea, on_land):
        assert earth.km(cell, -0.5, -50.0) < 800.0
        assert 105_000.0 < river[cell] < 420_000.0
    assert earth.wet[earth.drainage.fields["flow_receiver"][on_land]]             # the largest river is at its mouth
    assert abs(river[into_sea] - 144_605.0) < 300.0 and abs(river[on_land] - 144_453.0) < 300.0


# The rivers whose flow at the last gauge the engine misses by more than a factor of two, with the ties settled as the
# engine settles them. Each reason gives the flow, the land whose water reaches the cell taken against the real basin,
# and what was measured beside it [MEASURED: python tools/earth_rivers.py, parts 1, 2, 6 and 7; python
# tools/earth_relief.py, part 3]. "The cell taken" is the cell with the largest flow within 150 km of the station. "Like
# for like" is what the land sheds on the mesh's own river at the gauge where its basin is like the real one in size,
# over the depth measured (ALIKE below). AT_GAUGE holds the numbers of every river; a test keeps it true. "In none of
# 20" and the like are counts of 20 random settlements of the ties. No reason names a cause that was not measured.
OFF_AT_GAUGE = {
    "Congo": "8 km3 a year against 1,271, and within a factor of two in none of 20 random settlements. Land of 50 thousand "
             "km2 reaches the cell taken, of the real 3,475. The mesh's river comes no nearer the station than 366 km, where "
             "it carries 188 km3 a year: the data close the river's valley above Kinshasa themselves (MISLED), the basin "
             "fills as a lake and its water leaves westward.",
    "Orinoco": "356 km3 a year against 984 as the engine settles ties; 351 to 606 in 20 random settlements, within a factor of "
               "two in 2: the ties decide, and mostly against the river. As the engine settles them, land of 563 thousand km2 "
               "reaches the gauge (836 on Earth), and it sheds 705 mm a year where 1,177 are measured: like for like 0.60.",
    "Yangtze": "128 km3 a year against 910, and within a factor of two in none of 20 random settlements. With every hollow full "
               "1,567 thousand km2 drain to the gauge (1,705 on Earth), but only 839 reach it: the data close the Three "
               "Gorges themselves (their valley rises to 945 m on the data's grid, where the river above stands at 404 m), "
               "and the lake that the Sichuan basin holds behind them keeps its water. And like for like the land sheds 115 "
               "mm a year where 534 are measured, 0.22: the rain on it, 1,151 mm, is hardly more than the demand for water "
               "the engine gives it, 1,140 mm.",
    "Yenisei": "77 km3 a year against 577 as the engine settles ties; 73 to 816 in 20 random settlements, within a factor of "
               "two in 2: the ties decide, and mostly against the river. As the engine settles them the cell taken does not "
               "lie on the mesh's river: land of 201 thousand km2 reaches it, of the real 2,440. The mesh's river comes no "
               "nearer the station than 166 km, outside the 150 km within which the largest flow is taken, and carries 293 "
               "km3 a year there, which is within a factor of two of the 577: the 150 km decide this failure as much as the "
               "ties do.",
    "Lena": "4 km3 a year against 526, and within a factor of two in none of 20 random settlements (154 at most). The cell "
            "taken does not lie on the mesh's river: land of 32 thousand km2 reaches it, of the real 2,430. The mesh's river "
            "comes no nearer the station than 194 km, where it carries 148 km3 a year. The data close the valley above the "
            "delta themselves: on their own grid it rises to 152 m, where the river at Zhigansk stands at 91 m. On the mesh "
            "the lowland above fills as a lake of 150,490 km2 to 122 m, which overflows to the sea west of the delta and of "
            "the gauge.",
    "Mekong": "143 km3 a year against 292 as the engine settles ties; 36 to 143 in 20 random settlements, under half in every "
              "one. Land of 275 thousand km2 reaches the gauge, of the real 545, and sheds 559 mm a year where 536 are "
              "measured: the river carries half because half the basin reaches it. Why the basin is half is not established; "
              "4 of the 16 land cells on the river's way lie on level ground, where only the ties choose the way.",
    "St Lawrence": "470 km3 a year against 226 as the engine settles ties: too much. In 20 random settlements 214 to 477, "
                   "within a factor of two in 11: the ties decide, and the engine's failure here is no finding. As the engine "
                   "settles them, land of 1,244 thousand km2 reaches the gauge (774 on Earth) and sheds 443 mm a year where "
                   "292 are measured. Like for like, on the mesh's own river of 1,012 thousand km2, the land sheds 423 mm: "
                   "1.45 of the measured depth.",
    "Amur": "26 km3 a year against 312, and within a factor of two in none of 20 random settlements. Land of 100 thousand km2 "
            "reaches the cell taken, of the real 1,730. The data close the lower river themselves (MISLED), and the water of "
            "the lowland leaves south to the Sea of Japan: the mesh's river comes no nearer the station than 265 km.",
    "Mackenzie": "116 km3 a year against 288, the same in every one of 20 random settlements. The basin is right (1,740 "
                 "thousand km2 reach the gauge; 1,660 on Earth), but its land sheds 88 mm a year where 173 are measured, like "
                 "for like 0.51, and lakes on the way lose 37 km3 of that.",
    "Danube": "66 km3 a year against 202, and within a factor of two in none of 20 random settlements. Land of 650 thousand "
              "km2 reaches the cell taken (807 on Earth) and sheds 293 mm a year where 250 are measured, 190 km3; lakes on "
              "the way lose 124 km3 of it. One of them stands above the Iron Gate at 208 m and loses 72 km3; and the cell "
              "taken, 138 km from the station, lies under the lake that fills the hollow of the Black Sea to 32 m. Earth has "
              "no lake at either place, the plain above the Iron Gate or the lower Danube [UNVERIFIED: from memory].",
    "Niger": "5 km3 a year against 33, and within a factor of two in none of 20 random settlements. Land of 116 thousand km2 "
             "reaches the gauge, of the real 1,516. Like for like the land sheds 8 mm a year where 22 are measured, 0.37.",
    "Zambezi": "11 km3 a year against 105, the same in every one of 20 random settlements. With every hollow full 2,016 "
               "thousand km2 drain to the gauge (940 on Earth), but only 233 reach it as the water runs, and that land sheds "
               "71 mm a year where 112 are measured.",
    "Indus": "No river at all within 150 km of the gauge, against 89 km3 a year, in every one of 20 random settlements. With "
             "every hollow full 1,397 thousand km2 drain there (975 on Earth); as the water runs, land of 95 thousand km2 "
             "reaches the place and sheds nothing: 289 mm of rain a year fall on it, and the demand for water is 1,465 mm. "
             "Like for like the land sheds 12 mm a year where 91 are measured, 0.13."}

# For every gauged river, with the ties settled as the engine settles them: the flow at the gauge (km3 a year) and the land
# whose water reaches it (thousand km2); and in how many of the SETTLEMENTS random settlements the flow is within a factor
# of two of the measured one.
AT_GAUGE = {"Amazon": (4519, 5921, 20), "Congo": (8, 50, 0), "Orinoco": (356, 563, 2), "Yangtze": (128, 839, 0), "Brahmaputra": (348, 565, 2),
            "Mississippi": (482, 2396, 20), "Yenisei": (77, 201, 2), "Parana": (480, 3010, 20), "Lena": (4, 32, 0), "Mekong": (143, 275, 0),
            "Ob": (598, 2853, 1), "Ganges": (348, 565, 20), "St Lawrence": (470, 1244, 11), "Amur": (26, 100, 0), "Mackenzie": (116, 1740, 0),
            "Columbia": (117, 484, 20), "Danube": (66, 650, 0), "Niger": (5, 116, 0), "Zambezi": (11, 233, 0), "Indus": (0, 95, 0),
            "Rhine": (82, 184, 20)}

# Like for like (earth_reference.like_for_like), with the ties settled as the engine settles them: for each gauged river
# whose basin on the mesh, with every hollow full, is within a factor of 1.5 of the real one's area, what its land sheds
# over the depth measured; and in how many of the SETTLEMENTS random settlements its basin is alike.
ALIKE = {"Amazon": (0.72, 20), "Orinoco": (0.60, 19), "Yangtze": (0.22, 20), "Brahmaputra": (0.23, 3), "Mississippi": (1.13, 20),
         "Parana": (0.78, 20), "Ob": (1.27, 1), "Ganges": (0.58, 20), "St Lawrence": (1.45, 9), "Mackenzie": (0.51, 20),
         "Columbia": (0.32, 20), "Danube": (1.17, 20), "Niger": (0.37, 20), "Indus": (0.13, 20), "Rhine": (1.18, 20)}


@pytest.fixture(scope="module")
def gauges(earth):
    return ref.rivers_at_gauges(earth)


@pytest.mark.parametrize("river", [pytest.param(name, marks=missed(OFF_AT_GAUGE[name])) if name in OFF_AT_GAUGE else name for name in ref.GAUGES])
def test_a_great_river_carries_at_its_last_gauge_what_it_carries_on_earth(gauges, river):
    """Under Earth's rain and warmth, the largest yearly flow within 150 km of the station (the mesh may run the river
    through the next cell) is within a factor of two of the flow measured there [DOCUMENTED: Dai and Trenberth,
    Table 2; earth_reference.GAUGES]. Found, then kept: the 21 gauges, the 150 km and the factor of two came into
    the repository together with their results, and no record shows them set before a run. None has been changed
    since. With the ties settled as the engine settles them 8 of the 21 rivers pass, and each of the other 13 is
    an expected failure of its own. Five of the 21 are decided by the ties: the Brahmaputra and the Ob, which pass
    as the engine settles ties and in 2 and 1 of 20 random settlements, and the Orinoco, the Yenisei and the St
    Lawrence, which fail (AT_GAUGE, and the test after the next two).
    The test mixes two things: where the mesh runs the rivers, which the relief data and their ties mostly decide,
    and what the land sheds. The second is tested by itself below, like for like.
    The rule takes the largest flow near the station, whichever river carries it. For four rivers the cell taken
    does not lie on the mesh's river at all, which passes more than 150 km away (the Congo, the Yenisei, the Lena,
    the Amur). And one cell serves the stations of the Ganges and of the Brahmaputra, 138 and 129 km from them: the
    two stations lie 179 km apart. That cell does not lie on the mesh's Ganges, which carries 212 km3 a year where
    it passes its own station, within a factor of two of the 382 measured as well."""
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
    Ganges, the Columbia and the Rhine. Ten pass in none. Five are decided by the ties: the Orinoco (2 of 20), the
    Brahmaputra (2), the Yenisei (2), the Ob (1) and the St Lawrence (11). The Brahmaputra and the Ob pass as the
    engine settles ties, which a random settlement seldom does: those passes are no findings. The St Lawrence
    fails as the engine settles ties, which a random settlement does about half the time: that failure is none
    either.
    [Twice these counts claimed more than was drawn: see the test of the mouths.]"""
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
    assert (min(counts), max(counts)) == (6, 9) and sum(ok(outcomes["engine"], river) for river in AT_GAUGE) == 8
    assert {river for river, (_, _, k) in AT_GAUGE.items() if 0 < k < SETTLEMENTS} == {"Orinoco", "Brahmaputra", "Yenisei", "Ob", "St Lawrence"}
    assert sum(k == 0 for _, _, k in AT_GAUGE.values()) == 10
    assert {river for river in AT_GAUGE if not ok(outcomes["engine"], river)} == set(OFF_AT_GAUGE)
    spread = lambda river: (min(r["flow"][river] for r in drawn(outcomes)), max(r["flow"][river] for r in drawn(outcomes)))
    for river, (low, high) in {"Orinoco": (351, 606), "Yenisei": (73, 816), "Mekong": (36, 143), "St Lawrence": (214, 477), "Ob": (28, 589),
                               "Mackenzie": (116, 116), "Zambezi": (11, 11), "Lena": (3, 154), "Brahmaputra": (247, 338)}.items():   # what the texts quote
        assert abs(spread(river)[0] - low) < max(2.0, 0.02 * low) and abs(spread(river)[1] - high) < max(2.0, 0.02 * high), (river, spread(river))
    # one cell serves the stations of the Ganges and the Brahmaputra: 138 and 129 km from them, 179 km between the two, and not on the mesh's Ganges
    assert gauges["Ganges"]["cell"] == gauges["Brahmaputra"]["cell"]
    ganges, brahmaputra = ref.GAUGES["Ganges"][:2], ref.GAUGES["Brahmaputra"][:2]
    assert abs(earth.km(gauges["Ganges"]["cell"], *ganges) - 138.0) < 3.0 and abs(earth.km(gauges["Ganges"]["cell"], *brahmaputra) - 129.0) < 3.0
    between = np.arccos(np.clip(ref._points(np.array([ganges[0]]), np.array([ganges[1]]))[0] @ ref._points(np.array([brahmaputra[0]]), np.array([brahmaputra[1]]))[0], -1, 1))
    assert abs(between * R / 1000.0 - 179.0) < 2.0
    land_way = lambda river: [c for c in ref.way_of(earth, river) if c["step"] != "sea"]
    way = land_way("Ganges")
    nearest = min(way, key=lambda c: earth.km(c["cell"], *ganges))
    own = earth.yearly_flow()[nearest["cell"]]
    assert gauges["Ganges"]["cell"] not in {c["cell"] for c in way} and abs(earth.km(nearest["cell"], *ganges) - 44.0) < 3.0
    assert abs(own - 212.0) < 3.0 and within_a_factor_of_two(ref.GAUGES["Ganges"][2], own)
    # the four whose cell is not on the mesh's river: how near the river comes to the station, and what it carries there (km; km3 a year)
    flow = earth.yearly_flow()
    for river, (km, carries) in {"Congo": (366, 188), "Yenisei": (166, 293), "Lena": (194, 148), "Amur": (265, 43)}.items():
        way = land_way(river)
        nearest = min(way, key=lambda c: earth.km(c["cell"], *ref.GAUGES[river][:2]))
        assert gauges[river]["cell"] not in {c["cell"] for c in way}
        assert abs(earth.km(nearest["cell"], *ref.GAUGES[river][:2]) - km) < 3.0 and abs(flow[nearest["cell"]] - carries) < 3.0, river
        assert earth.km(nearest["cell"], *ref.GAUGES[river][:2]) > ref.NEAR_GAUGE_KM
    assert within_a_factor_of_two(ref.GAUGES["Yenisei"][2], 293.0) and ref.NEAR_GAUGE_KM == 150.0
    for river in set(ref.GAUGES) - {"Congo", "Yenisei", "Lena", "Amur", "Ganges", "Brahmaputra"}:     # (the Brahmaputra is no great river of the list)
        assert gauges[river]["cell"] in {c["cell"] for c in land_way(river)}, river
    # ... the Mekong's way: 16 land cells, 4 of them on level ground; its gauge's cell is on it
    way = land_way("Mekong")
    assert (len(way), sum(c["step"] == "level" for c in way)) == (16, 4)
    assert {river for river, (_, _, k) in AT_GAUGE.items() if k == SETTLEMENTS} == {"Amazon", "Mississippi", "Parana", "Ganges", "Columbia", "Rhine"}
    assert gauges["Indus"]["no_river"] and not any(r["no_river"] for name, r in gauges.items() if name != "Indus")
    # ... and the Danube's: its cell lies under the lake at the Black Sea's place, and the lake above the Iron Gate loses 72 km3 a year
    water = earth.hydrology()
    lakes, row = water.tables["lakes"], water.drivers["lake_fraction"]["lake"]
    black_sea, danube = int(row[earth.cell(43.0, 34.0)]), gauges["Danube"]["cell"]
    assert int(row[danube]) == black_sea and water.fields["lake_fraction"][danube] == 1.0 and lakes["level_m"][black_sea] == 32.0
    above_the_gate = int(row[earth.cell(44.7, 20.4)])
    assert lakes["level_m"][above_the_gate] == 208.0 and abs(lakes["loss_to_air_m3_per_year"][above_the_gate] / 1e9 - 72.0) < 1.0
    d = gauges["Danube"]
    assert abs(d["reaches"] * d["sheds"] / 1000.0 - 190.0) < 2.0 and abs(d["lost_in_lakes"] - 124.0) < 2.0 and abs(earth.km(danube, *ref.GAUGES["Danube"][:2]) - 138.0) < 3.0


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
    walked = 0
    for river, r in gauges.items():
        if not (crossing[r["cell"]] < 0 or r["cell"] in outlet):                  # the gauge stands inside a lake's water: the test after this one
            continue
        walked += 1
        above, todo = {r["cell"]}, [r["cell"]]
        while todo:
            for cell in donors.get(todo.pop(), ()):
                above.add(cell)
                todo.append(cell)
        lost = sum(loss for loss, runs, at in zip(lakes["loss"], lakes["overflows"], outlet) if runs and int(at) in above) / 1e9
        assert abs(lost - r["lost_in_lakes"]) < 1e-6 * max(lost, 1.0), (river, lost, r["lost_in_lakes"])
        assert abs(sum(float(earth.area[c]) for c in above if earth.land[c]) / 1e9 - r["reaches"]) < 1e-6 * max(r["reaches"], 1.0)
    assert walked >= 12, walked


def test_the_books_of_the_river_close_at_every_cell(earth):
    """What the test above asks of 21 gauges, at every cell of the planet, and again with the demand for water cut
    to 0.76 of itself, where other lakes stay closed: the water shed upstream, less what the lakes with an outlet
    lose on the way, less what a closed lake in the cell itself keeps, is the field river_discharge. Among the cells
    are the three kinds that few gauges stand on: the outlet cell of a lake, a cell inside a lake that is not its
    outlet, and a cell partly under a closed lake. Each kind must be there, and each must carry a part of the
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
    # the gauges at demand x 0.76: wherever a gauge's cell lies partly under a closed lake, what the lake keeps there is in its books
    for river, r in ref.rivers_at_gauges(earth, water).items():
        assert abs(r["unbalanced"]) < 1e-6 * max(r["flow"], 1.0) + 1e-4, river


# ---------------------------------------------------------------------------------------------- the numbers the tools print
# [The fourth check of build step 2: no test ran a tool, the tools did their own arithmetic, and ten changes made on
# purpose to that arithmetic went unnoticed. The arithmetic is now in earth_reference, the tools print what it gives,
# and the tests below hold both: the numbers, and the lines of the reports that carry them.]
WATER_OF_THE_LAND = {        # earth_reference.land_water as the engine settles ties: (value, how near it must stay)
    "rain": (117.23, 0.05), "to_air": (86.57, 0.05), "back_to_air": (0.7385, 0.0004), "to_sea": (30.66, 0.03), "rain_mm": (785.7, 0.4),
    "to_air_mm": (580.2, 0.4), "demand_mm": (1003.6, 0.6), "lakes_share": (0.06281, 0.0002), "lakes_km2": (9_371_432.0, 3_000.0),
    "lakes": (561, 0), "lakes_with_outlet": (451, 0), "shed": (34.20, 0.03), "back_to_air_dry": (0.7083, 0.0004),
    "lakes_with_outlet_lose": (3.072, 0.01), "closed_lakes_keep": (0.468, 0.004), "reaches_sea_share": (0.7134, 0.0005),
    "closed_hollow_share": (0.6239, 0.0005), "under_water_if_full_share": (0.1051, 0.0004), "level_with_the_water_share": (0.0367, 0.0004)}

# earth_reference.under_demand: the land's water with the air's demand for water multiplied by a factor
# (like for like, its median, without the Amazon, back to the air, to the sea, mm to the air, gauges within a factor of two)
UNDER_DEMAND = {1.0: (0.690, 0.599, 0.660, 0.7385, 30.66, 580.2, 8), 0.794: (0.933, 0.943, 0.921, 0.6517, 40.84, 512.0, 13),
                0.76: (0.980, 0.983, 0.977, 0.6347, 42.83, 498.7, 12), 0.6: (1.236, 1.184, 1.293, 0.5441, 53.45, 427.5, 11)}


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
        assert 0.0620 < r["lakes_share"] < 0.0633, r["lakes_share"]
    assert outcomes["engine"]["lakes_share"] == w["lakes_share"] and outcomes["engine"]["to_sea"] == w["to_sea"]
    # beside Earth's budget, as the notes put it: 3 % more rain than the budget's 114 thousand km3; and of that rain Earth's share,
    # 40 of 114, would send 41 thousand km3 to the sea, of which the engine's 30.7 are three quarters
    assert abs(w["rain"] / 114.0 - 1.028) < 0.003 and abs(w["to_sea"] / (w["rain"] * 40.0 / 114.0) - 0.745) < 0.005


def test_the_rain_and_the_demand_over_the_land_that_reaches_a_gauge(gauges):
    """Found, then kept: the two columns of the report that say why a basin sheds what it sheds. The rain is far above
    the demand on the Amazon and the Yenisei, and far below it on the Niger and the Indus."""
    kept = {"Amazon": (2314, 1656), "Mississippi": (954, 935), "Yenisei": (652, 267), "Niger": (874, 1714), "Indus": (289, 1465), "Rhine": (1113, 699)}
    for river, (rain, demand) in kept.items():
        r = gauges[river]
        assert abs(r["rain"] - rain) < 0.01 * rain + 2 and abs(r["demand"] - demand) < 0.01 * demand + 2, (river, round(r["rain"]), round(r["demand"]))


def test_a_smaller_demand_would_mend_the_shortfall_whichever_of_two_causes_made_it_smaller(earth):
    """Found, then kept: it keeps the table of docs/BUILD_NOTES.md, section 4.4, true, and the reading that the notes
    give it. Like for like the land sheds 0.69 of the measured depth. With the demand for water multiplied by 0.76
    it sheds 0.98, and with 0.794 it sheds 0.93: both would meet the test that the engine fails, and both bring the
    water of all the land near Earth's (0.65 of the rain back to the air, 40 thousand km3 a year to the sea). But
    0.76 stands for an error in the energy that the formulas leave to the land (85.8 W/m2 where a published budget
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
    # the fifteen within 15 % of the measured depth, and the rest spread from a third of it to 1.7 times it
    spread = {factor: (round(r["like_lowest"], 2), round(r["like_highest"], 2), r["like_within_15"]) for factor, r in rows.items()}
    assert spread == {1.0: (0.13, 1.45, 1), 0.794: (0.28, 1.67, 2), 0.76: (0.32, 1.74, 2), 0.6: (0.42, 2.28, 4)}, spread
    assert abs(1.0 / 1.26 - 0.794) < 0.001 and abs(65.5 / 85.8 - 0.763) < 0.001   # where the two factors come from
    assert abs(ref.demand_times(earth, 0.794)["demand"]["priestley_taylor_extra"]) < 0.001      # 0.794: the rule with nothing extra


def test_what_the_like_for_like_figure_can_bear(outcomes, earth):
    """Found, then kept: it keeps the caveats of docs/BUILD_NOTES.md, section 4.4, true. The 0.69 is a mean weighted by
    water: the Amazon carries 52 % of it, and without the Amazon it is 0.66; the median of the fifteen basins'
    own ratios is 0.60. In two of the basins the comparison cannot test what Hydrology does: over the mesh's
    Brahmaputra the rain handed in (1,013 mm a year) is less than the runoff measured (1,105 mm), and over its
    Columbia the measured runoff would leave 157 mm for evaporation. Without those two the figure is 0.73. And the
    engine's depth is taken before any lake loses water, the measured one after, which favours the engine: taken
    as the flow at the same cells, the figure is 0.62."""
    like = ref.like_for_like(earth)
    all_of_them = ref.like_together(like)
    assert set(all_of_them["basins"]) == set(ALIKE) and abs(all_of_them["ratio"] - outcomes["engine"]["like_all"]) < 1e-12
    assert abs(all_of_them["ratio"] - 0.690) < 0.003 and abs(all_of_them["median"] - 0.599) < 0.004
    assert abs(sum(all_of_them["weights"].values()) - 1.0) < 1e-9 and abs(all_of_them["weights"]["Amazon"] - 0.523) < 0.005
    assert (all_of_them["below_one"], all_of_them["above_one"], all_of_them["within_two"]) == (10, 5, 10)
    assert abs(ref.like_together(like, ("Amazon",))["ratio"] - 0.660) < 0.004
    b, c = like["Brahmaputra"], like["Columbia"]
    assert abs(b["rain"] - 1013.0) < 5.0 and abs(b["measured_depth"] - 1104.5) < 0.5 and b["rain"] < b["measured_depth"]
    assert abs(c["rain"] - 437.0) < 4.0 and abs(c["rain"] - c["measured_depth"] - 157.0) < 4.0
    asked = sorted(((like[name]["measured_depth"] / like[name]["rain"], name) for name in ALIKE), reverse=True)
    assert [name for _, name in asked[:3]] == ["Brahmaputra", "Columbia", "Orinoco"] and asked[1][0] > ref.MUCH_OF_THE_RAIN > asked[2][0]
    assert abs(asked[0][0] - 1.09) < 0.01 and abs(asked[1][0] - 0.64) < 0.01 and abs(asked[2][0] - 0.57) < 0.01
    assert abs(ref.like_together(like, ("Brahmaputra", "Columbia"))["ratio"] - 0.731) < 0.004
    by_hand = sum(like[name]["sheds"] * like[name]["basin"] for name in ALIKE) / sum(like[name]["measured_depth"] * like[name]["basin"] for name in ALIKE)
    assert abs(by_hand - all_of_them["ratio"]) < 1e-12
    # after the lakes: the flow that passes the same cells, over what the measured depth would send through them (km3 a year over mm x thousand km2)
    after = 1000.0 * sum(like[name]["flow"] for name in ALIKE) / sum(like[name]["measured_depth"] * like[name]["basin"] for name in ALIKE)
    assert abs(after - all_of_them["after_lakes"]) < 1e-12 and abs(after - 0.619) < 0.004 and after < all_of_them["ratio"]
    # the share of the precipitation handed in as snow, which is made and not measured: none in the tropics, most in Siberia
    assert like["Amazon"]["snow_share"] == 0.0 and abs(like["Ob"]["snow_share"] - 0.41) < 0.01 and abs(like["Yenisei"]["snow_share"] - 0.61) < 0.01


def test_the_radiation_over_earths_land_and_what_the_engines_excess_is_made_of(earth):
    """Found, then kept: it keeps docs/BUILD_NOTES.md, section 7, item 14, true (python tools/earth_demand.py).
    The engine's formulas leave Earth's land 85.8 W/m2 to warm the air and evaporate water, where a published
    budget has 65.5 [DOCUMENTED: Trenberth, Fasullo and Kiehl 2009, Table 2b, land: a synthesis of measurements
    and models, not a measurement]: 1.31 times as much. Of the excess of 20.3, 0.8 come from the sunlight that
    reaches the ground, 8.2 from the ground reflecting 0.17 of it where the budget has 0.21, and 11.3 from the
    heat that the ground radiates away. The land's evaporation, under the rain data, takes 45.1 W/m2 where the
    budget has 38.5: 1.17 times as much.
    The one share of sunshine, 0.62, enters both formulas. The sunlight at the ground is the budget's with it
    (185.7 for 184.7); the heat radiated away is 68.3 where the budget has 79.6, and would be the budget's with a
    share of 0.76, which would put 209.4 W/m2 of sunlight on the ground. No one share returns both. [The fifth
    check of build step 2 found that the notes had the longwave formula without the share.]
    The published numbers are written here once more, as the table gives them: a slip in the tool's copy would
    change every ratio the notes draw from it."""
    demand = tool("earth_demand")
    m = demand.LAND_MEASURED
    assert m == {"reaches": 184.7, "absorbed": 145.1, "lost": 79.6, "evaporation": 38.5, "sensible": 27.0}
    assert abs(m["reaches"] - m["absorbed"] - 39.6) < 1e-9 and abs(m["absorbed"] - m["lost"] - m["evaporation"] - m["sensible"]) < 1e-9
    said = []
    r = demand.report(earth=earth, say=said.append)
    b, x = r["budget"], r["excess"]
    for key, value in (("reaches", 185.7), ("absorbed", 154.1), ("lost", 68.3), ("evaporation", 45.1)):
        assert abs(b[key] - value) < 0.1, (key, b[key])
    left, left_measured = b["absorbed"] - b["lost"], m["absorbed"] - m["lost"]
    assert abs(left - 85.8) < 0.1 and abs(left / left_measured - 1.310) < 0.004 and abs(b["evaporation"] / m["evaporation"] - 1.172) < 0.004
    assert abs(sum(x.values()) - (left - left_measured)) < 1e-9                    # the three parts are the whole excess
    for key, value in (("sunlight", 0.78), ("reflection", 8.25), ("heat_loss", 11.25)):
        assert abs(x[key] - value) < 0.06, (key, x[key])
    assert abs(r["wants_sun"] - 0.614) < 0.004 and abs(r["wants_heat"] - 0.763) < 0.004 and r["sunshine"] == 0.62
    # the share enters both formulas: with the three shares of the table
    shares = {round(share, 2): v for share, v in r["shares"].items()}
    assert sorted(shares) == [0.5, 0.62, 0.76]
    for share, (reaches, lost, stays) in {0.5: (165.8, 58.9, 78.7), 0.62: (185.7, 68.3, 85.8), 0.76: (209.4, 79.6, 94.2)}.items():
        v = shares[share]
        assert abs(v["reaches"] - reaches) < 0.1 and abs(v["lost"] - lost) < 0.1 and abs(v["left"] - stays) < 0.1, (share, v)
    assert abs(shares[0.62]["left"] - left) < 1e-9 and abs(shares[0.76]["lost"] - m["lost"]) < 0.05      # the third share is the one that returns the budget's loss
    assert shares[0.5]["lost"] < shares[0.62]["lost"] < shares[0.76]["lost"] and shares[0.5]["reaches"] < shares[0.62]["reaches"] < shares[0.76]["reaches"]
    # the demand in the engine's form and in the paper's: 1,004 against 1,247 mm a year less 195 that the night gives back
    a = r["bands"]["all land"]
    assert abs(r["field"] - 1003.6) < 0.6 and abs(a["engine"] - r["field"]) < 0.01 and r["largest_gap_to_the_field"] < 1e-3
    assert abs(a["paper"] - 1246.8) < 1.5 and abs(a["dew"] - 194.5) < 0.6 and abs(r["none_where_the_paper_has_some"] - 0.0268) < 0.001
    assert all(1.02 < (v["paper"] - v["dew"]) / v["engine"] < 1.06 for v in r["bands"].values())
    text = "\n".join(said)
    assert "left to warm the air and evaporate        85.8        65.5   the engine has 1.31 of the budget's" in text
    assert "of that, evaporation takes                45.1        38.5   the engine has 1.17 of the budget's" in text
    assert "0.8 from the sunlight that reaches the ground; 8.2 from the ground reflecting 0.17 of it where the budget has 0.21; 11.3 from the heat" in text
    assert "the share of sunshine that would return the budget's sunlight at the ground: 0.61; the budget's loss of heat: 0.76" in text
    rows = [line.split() for line in said if line.split() and line.split()[0] in ("0.50", "0.62", "0.76", "budget")]
    assert rows == [["0.50", "165.8", "58.9", "78.7"], ["0.62", "185.7", "68.3", "85.8", "as", "built"], ["0.76", "209.4", "79.6", "94.2"],
                    ["budget", "184.7", "79.6", "65.5"]], rows


def test_the_reports_of_the_tools_print_what_the_harness_measures(earth, flood, gauges, outcomes):
    """The reports are read by a person and quoted in the notes. Their lines are held here against the numbers of the
    harness, which the tests above hold: a report that printed another number, or met a gauge within a factor of
    three, would show."""
    said = []
    tool("earth_rivers").report(earth=earth, say=said.append)
    text = "\n".join(said)
    assert ("sea water poured: 1.33758e+18 m3, what the ocean of the relief data holds; the sea of the mesh comes to rest at +1.9 m and covers "
            "70.75 % of the planet; 47962 land cells") in text
    passing = [name for name, r in gauges.items() if within_a_factor_of_two(r["measured"], r["flow"])]
    assert len(passing) == 8 and f"within a factor of two of the measured flow: 8 of {len(gauges)}" in text
    for name, r in gauges.items():                                                # every row says yes or NO as the test of that gauge does
        row = next(line for line in said if line.startswith(f"{name:12s}") and "|" in line and ("yes" in line.split("|")[0] or "NO" in line.split("|")[0]))
        assert ("yes" in row.split("|")[0]) == (name in passing), row
        assert f"{r['measured']:9.0f}{r['flow']:8.0f}" in row and f"{r['station_area']:8.0f}{r['reaches']:9.0f}{r['basin']:18.0f}" in row
    assert "the books of every gauge close" in text and "and at every cell of the mesh, to within" in text
    assert "basins alike: 15 of 21. All of them together, the engine sheds 0.69 of the measured depth; basin by basin 0.13 to 1.45, 10 below 1 and 5 above; within a factor of two: 10" in text
    assert "the Amazon carries 52 % of the weight. Without the Amazon: 0.66. The median of the basins' own ratios: 0.60" in text
    assert "the Brahmaputra (rain 1013, measured runoff 1105), the Columbia (rain 437, measured runoff 280). Without them: 0.73" in text
    assert "after closed hollows upstream have kept their water and lakes on the way have lost theirs: 0.62)" in text
    words = lambda start: next(line for line in said if line.strip().startswith(start)).split()
    like_row = next(line for line in said if line.startswith("Brahmaputra") and "|" not in line).split()
    assert like_row[-6:] == ["257", "0.23", "1013", "977", "1.09", "0.04"]       # ... sheds, engine / measured, rain, demand, measured / rain, snow / rain
    assert ("published for the basin: precipitation 585 mm a year, 30 % of it snow (176 mm); 53 % of the runoff in the spring flood; and three figures for "
            "the runoff that do not agree: 262 km3 of runoff, 193 mm; a runoff coefficient of 0.38, 222 mm; a water content of 250 km3, 184 mm") in text
    for start, numbers in (("under the rain data", ["747", "321", "345", "322", "(month", "4)", "1.79", "1.55", "1.88"]),
                           ("the rain data scaled to the published total", ["585", "251", "225", "223", "(month", "4)", "1.17", "1.01", "1.22"]),
                           ("the published total with the published share of snow", ["585", "176", "178", "160", "(month", "4)", "0.92", "0.80", "0.97"]),
                           ("the rain data's total with the published share of snow", ["747", "224", "287", "232", "(month", "4)", "1.49", "1.29", "1.56"])):
        assert words(start)[-9:] == numbers, words(start)
    assert "within 300 km: 15 of 24" in text
    assert "rain on land 117.2; back to the air 86.6 (0.738 of the rain); rivers reaching the sea 30.7" in text
    assert "shed by the land as if none of it were flooded 34.2 (0.708 of the rain back to the air); lakes with an outlet lose 3.07 more than the ground they cover; closed lakes keep 0.47" in text
    assert "land under water if every hollow were full: 10.5 %, and another 3.7 % exactly level with that water" in text
    assert "the air's demand for water over land 1004 mm a year; rain 786 mm; back to the air 580 mm; lakes cover 6.28 % of the land: 561 lakes, 451 with an outlet" in text
    assert "lakes larger than 100,000 km2: 12, with 54 % of all the land under lakes" in text
    assert "The lake at the Caspian's place: 1.09 million km2 at 61 m; it overflows by 17.88 km3 a year" in text
    assert "rivers and shores bring it 590 km3 a year; each square metre of it gives the air 933 mm a year and gets 408 mm of rain" in text
    assert ("the land whose water reaches it: 4.05 million km2 with the ground under the lake, 2.96 without; over the land without the lake, the water "
            "brought is 199 mm a year; it holds the Don at Voronezh") in text
    assert "the water that runs over crosses 4 land cells and ends in a closed lake of 19,939 km2, at 42.2, 57.1" in text
    assert "the valley rises to 208 m, at 43.9, 22.2; the lake above it stands at 208 m and overflows, and the valley stands no higher than its water" in text
    said = []
    tool("earth_relief").report(earth=earth, flood=flood, say=said.append)
    text = "\n".join(said)
    assert ("the ocean of the data holds 1.33758e+18 m3 of water below 0 m; the planet file has 1.33500e+18 m3, 0.19 % less. Poured here: the first; the sea "
            "of the mesh comes to rest at +1.9 m and covers 70.75 % of the planet, with 47962 land cells") in text
    assert "of 47962 land cells 16510 (34.4 %) have a land neighbour at exactly their own height" in text
    assert "of 42657 land cells with a lower neighbour, 9641 (22.6 %) have several equally low: the lower bed settles 3341, the wider way 6249, the cell numbers 51; another 4578 land cells (9.5 %) lie on level ground" in text
    assert "reaches the sea in another cell when the order of the cells is turned round, and of 14.9 % when the wider way is left out" in text
    assert "Of all that is not ocean, 13.3 % lies under water when every hollow of the data is full" in text
    assert "the mesh: 29.3 % of the planet is not sea. Of it, 10.5 % lies under water when every hollow is full (11.9 % between 60 south and 60 north); 62.4 % drains into a closed hollow" in text
    assert "closed in the data themselves: 5 of 6 (Congo, Danube, Lena, Amur, Yangtze)" in text
    assert ("kept apart from the mesh's sea by the cell at 13.1, 43.2: 65 % of its points are ocean in the data, its mean height is +15.8 m (the sea of the mesh "
            "stands at +1.9 m), and it is handed to Drainage at 107 m") in text
    assert ("under Earth's rain a lake of 612,693 km2 stands there at 32 m. It leaves through the cell at 40.5, 27.3: 78 % of its points are ocean in the data, its "
            "mean height is -5.6 m, and it is handed to Drainage at 32 m") in text
    assert "of these 12 lakes, 11 lie in hollows that the data hold on their own grid" in text
    assert "of 4800 coastal land cells, 248 are handed to Drainage no more than 5 m above the sea of the mesh (which stands at +1.9 m), and 10 of those have a mean height above 300 m" in text
    assert "In all, 437 land cells are handed in at or below the level of that sea" in text
    assert ("4086 land cells are handed in at another height, 3448 of them at the sea's own level. Great rivers that leave the land within 300 km of their mouths: "
            "16, for 15 as built; gauges within a factor of two: 8 for 8; lakes on 5.57 % of the land for 6.28 %. Mouths that move by more than 5 km: "
            "Yangtze 60 to 100 km; Ob 586 to 581 km; Mackenzie 26 to 32 km; Danube 579 to 1212 km; Yenisei 398 to 343 km; Murray 33 to 74 km; "
            "Orinoco 244 to 192 km; St Lawrence 1090 to 232 km; Amur 1290 to 1274 km; Huang He 1215 to 1261 km") in text
    # part 7, on summaries that are at hand: the counts printed are those of earth_reference.tally
    t = ref.tally(drawn(outcomes))
    assert t["runs"] == SETTLEMENTS and t["mouths"]["Mackenzie"][0] == SETTLEMENTS and t["mouths"]["Congo"][0] == 0
    assert t["caspian_closed"] == sum(not r["caspian"]["overflows"] for r in drawn(outcomes))
    assert t["caspian_to_sea"] == sum(r["caspian"]["overflow_ends"] == "sea" for r in drawn(outcomes)) == 0
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
    with pytest.raises(AssertionError, match=r"^6\.3 % of the land under lakes"):
        test_lakes_cover_no_more_of_the_land_than_on_earth(earth)
    with pytest.raises(AssertionError, match=r"^the lake at the Caspian's place overflows by 17\.9 km3 a year"):
        test_the_caspian_stays_a_closed_lake(earth)
    with pytest.raises(AssertionError, match=r"^the Black Sea: a lake of 612,693 km2 at 32 m"):
        test_a_sea_that_is_cut_off_or_a_great_lake_comes_back_as_a_lake_near_its_real_size(earth, "the Black Sea")
    assert missed("a reason").kwargs == {"strict": True, "raises": AssertionError, "reason": "a reason"}


@missed("Like for like, the engine's land sheds 0.69 of the depth measured over the fifteen basins that are alike (0.65 to "
        "0.71 in 20 random settlements): too little. The figure is a mean weighted by water: the Amazon carries 52 % of it, "
        "without the Amazon it is 0.66, and the median of the fifteen basins' own ratios is 0.60. They run from 0.13 (the "
        "Indus) to 1.45 (the St Lawrence), ten below 1 and five above. Two of the low ones cannot test the model: over the "
        "mesh's Brahmaputra the rain handed in, 1,013 mm a year, is less than the runoff measured, and over its Columbia "
        "the runoff measured is 0.64 of the rain handed in; without the two the figure is 0.73. The engine's depth is taken "
        "before any lake loses water and the measured one after: taken as the flow at the same cells the figure is 0.62. "
        "The cause of the shortfall is not established. What is measured: the engine's formulas leave Earth's land 1.31 "
        "times the energy that a published budget leaves it, and the land's evaporation is 1.17 times that budget's (python "
        "tools/earth_demand.py); with the demand for water cut to 0.76 of itself the figure is 0.98, and with the "
        "Priestley-Taylor rule's factor of 1.26 taken as 1.00, a cut to 0.794 with another cause, it is 0.93 (python "
        "tools/earth_rivers.py --demands). Which of the two, or what else, is at fault, nothing measured here can say "
        "[INFERRED: any cause named]. [MEASURED: tools/earth_rivers.py, parts 2 and 8]")
def test_like_for_like_the_land_of_the_great_basins_sheds_what_it_sheds_on_earth(outcomes):
    """Stated as a miss, with the number in view: over the basins that are alike in size, the engine's land sheds
    within 15 % of the depth measured. This is the test of what Hydrology makes of rain and warmth; where the
    rivers run does not enter it. The tests under "the numbers the tools print", above, hold every number of the
    reason."""
    assert 0.85 < outcomes["engine"]["like_all"] < 1.15, f"{outcomes['engine']['like_all']:.2f} of the measured depth"


def test_what_the_land_sheds_like_for_like_basin_by_basin(outcomes):
    """Found, then kept: it keeps ALIKE and the reasons that quote it true. Fifteen basins are alike as the engine
    settles ties; ten of them shed within a factor of two of the measured depth. Which basins are alike depends on
    the ties as well: three of the fifteen are alike in fewer than half of 20 random settlements (the Brahmaputra
    in 3, the Ob in 1, the St Lawrence in 9), and two that are not alike as built are alike in 7 (the Yenisei and
    the Lena)."""
    like = outcomes["engine"]["like"]
    assert {river for river, (alike, _) in like.items() if alike} == set(ALIKE)
    off = {river: (round(like[river][1], 2), sum(r["like"][river][0] for r in drawn(outcomes))) for river, (ratio, k) in ALIKE.items()
           if abs(like[river][1] - ratio) > 0.02 or sum(r["like"][river][0] for r in drawn(outcomes)) != k}
    assert not off, off
    assert sum(0.5 < ratio < 2.0 for ratio, _ in ALIKE.values()) == 10 and sum(ratio < 1.0 for ratio, _ in ALIKE.values()) == 10
    assert {river for river, (_, k) in ALIKE.items() if k < SETTLEMENTS / 2} == {"Brahmaputra", "Ob", "St Lawrence"}
    others = {river: sum(r["like"][river][0] for r in drawn(outcomes)) for river in set(ref.GAUGES) - set(ALIKE)}
    assert others == {"Congo": 0, "Yenisei": 7, "Lena": 7, "Mekong": 0, "Amur": 0, "Zambezi": 0}, others
    assert abs(outcomes["engine"]["like_all"] - 0.69) < 0.01
    spread = [r["like_all"] for r in drawn(outcomes)]
    assert abs(min(spread) - 0.65) < 0.006 and abs(max(spread) - 0.71) < 0.006


@missed("The design's condition fails as built: as the engine settles ties the lake at the Caspian's place overflows, by 17.9 "
        "km3 of the 669 that reach it in a year. In 20 random settlements it keeps its water in 1 and overflows in 19, by "
        "3.1 to 23.4 km3. The water that runs over does not reach the sea, as built or in any of the 20: as built it "
        "crosses 4 land cells and ends in a closed lake of 19,939 km2 at 42.2 N, 57.1 E. Whether that meets \"stays a "
        "closed lake\" is a question for the design; this test reads the condition as written and fails. As built and "
        "in each of the 20 the lake is far too large: 1.07 to 1.09 million km2 at 60 to 61 m, where the real sea "
        "covers 371,000 km2 and stands 28 m below the ocean [DOCUMENTED at second hand: Wikipedia, read out by a page "
        "reader; a paper on the sea's level gives about 436,000 km2]. The lake's books: rivers and shores bring it 590 km3 "
        "a year, where about 300 reach the real sea [DOCUMENTED at second hand, that paper: the Volga 237 km3 a year, "
        "about 80 % of the inflow]. The land that feeds it is not larger than the real rivers' catchment: 2.96 million km2 "
        "without the lake (4.05 million with the ground under it), where that paper gives about 3 million km2 for the "
        "rivers that flow into the sea and Wikipedia 3.6 million for the sea's catchment. The excess is in the depth: "
        "199 mm a year off that land, where 300 km3 off 3 million km2 are 100 mm. That land holds the Don at Voronezh, "
        "which on Earth runs to the Black Sea. The lake's water loses 933 mm a year and gets 408 mm of rain. What the "
        "Volga's part of the excess is made of is the subject of the next test, which leaves it open. [MEASURED for the "
        "mesh: earth_reference.lake_books; handoff/repin/repin.log]")
def test_the_caspian_stays_a_closed_lake(earth):
    """The design's: the Caspian stays a closed lake."""
    lake = earth.lake_at(*ref.CASPIAN)
    assert lake is not None
    assert not lake["overflows"], f"the lake at the Caspian's place overflows by {lake['outflow_m3_per_year'] / 1e9:.1f} km3 a year"


def test_what_the_volgas_land_sheds_under_four_precipitations(earth, outcomes):
    """Found, then kept: it keeps the Caspian's reason, the head of this file and section 4.4 of the notes true. It
    is a conditional statement and no more: which precipitation over the Volga's basin is the true one is NOT
    known here. The rain data and the published figure disagree, and no test of this file can say which is right.

    The Volga is the one basin for which a published precipitation and a published share of snow are at hand
    beside the published runoff [DOCUMENTED: Kalugin 2022: 1,360,000 km2, 585 mm of which 30 % solid, 262 km3 a
    year]. The source gives the runoff three times, and the three do not agree: 262 km3 over the basin is 193 mm,
    its "runoff coefficient of 0.38" makes 222 mm of the 585, and its "water content" of 250 km3 is 184 mm. The
    table and the assertions below use the first two; the tool prints all three (the test of the tools' reports).

    The land that drains through Volgograd on the mesh (1,222 thousand km2), under four precipitations
    (earth_reference.volga) [MEASURED: handoff/repin/repin.log, line "volga:"]:

        precipitation handed in                          mm    snow   sheds   over 193 mm   over 222 mm
        the rain data, the harness's snow               747    43 %    345       1.79          1.55
        the published total, the harness's snow         585    43 %    225       1.17          1.01
        the published total and share of snow           585    30 %    178       0.92          0.80
        the rain data's total, the published snow       747    30 %    287       1.49          1.29

    What the four rows show, and all they show: IF the published 585 mm and 30 % are right for this land, the model
    sheds between 0.80 and 0.92 of the published runoff there (0.97 on the third figure), and the whole excess of
    the first row comes with what was handed in (of its 345 mm, 120 go with the larger total and 47 with the
    harness's snow; taken in the other order, 58 with the snow and 109 with the total). IF the rain data's 747 mm
    are right, the model sheds 1.3 to 1.8 times the published runoff (1.9 on the third figure). The snow matters by itself: at either total,
    the harness's 43 % of snow in place of 30 % adds 47 to 58 mm to what the land sheds. The snow handed in is
    made from monthly mean temperatures and is no measurement.
    [An earlier version said "four fifths of the excess come with the rain data, the model's part lies between
    nothing and a fifth". That rested on the second row alone, with the harness's snow. The fifth check of build
    step 2 pointed at what the snow decides.]"""
    published_rain = ref.VOLGA["precipitation_mm"]
    by_volume = 1000.0 * ref.VOLGA["gauge"][2] / ref.VOLGA["gauge"][3]            # 262 km3 over 1,360 thousand km2
    by_coefficient = ref.VOLGA["runoff_coefficient"] * published_rain           # 0.38 of 585 mm
    assert abs(by_volume - 192.6) < 0.1 and abs(by_coefficient - 222.3) < 0.1 and ref.VOLGA["snow_share"] == 0.30
    v = outcomes["engine"]["volga"]
    assert v["like"] and abs(v["basin"] - 1221.7) < 5.0 and abs(v["rain"] - 747.1) < 3.0 and abs(v["sheds"] - 344.9) < 3.0
    assert abs(v["ratio"] - 1.79) < 0.03 and abs(v["sheds"] / by_coefficient - 1.55) < 0.03
    for r in [outcomes["engine"]] + drawn(outcomes):                           # in the engine's settlement and in each of 20 drawn
        assert r["volga"]["like"], r["volga"]
        assert 1.20 < r["volga"]["rain"] / published_rain < 1.30, r["volga"]    # the rain data: a quarter more than published
        assert 1.6 < r["volga"]["ratio"] < 1.9, r["volga"]
    rain_before, water_before = earth.rain.copy(), earth.hydrology()
    rows = ref.volga(earth)
    assert np.array_equal(earth.rain, rain_before) and earth.hydrology() is water_before     # the Earth of the tests is left as it was
    assert {k: x for k, x in rows["data"].items() if k not in ("snow", "sheds_most", "sheds_most_month")} == outcomes["engine"]["volga"]
    area = earth.area.astype(np.float64)
    assert abs(area[rows["land"]].sum() / 1e9 - rows["data"]["basin"]) < 1e-6 * rows["data"]["basin"]      # the land that was handed the other precipitations
    pinned = {"data": (747.1, 0.43, 344.9, 1.79, 1.55), "published_rain": (585.0, 0.43, 224.9, 1.17, 1.01),
              "published_rain_and_snow": (585.0, 0.30, 177.7, 0.92, 0.80), "data_rain_published_snow": (747.1, 0.30, 287.2, 1.49, 1.29)}
    for name, (rain, snow_share, sheds, over_volume, over_coefficient) in pinned.items():
        row = rows[name]
        assert row["cell"] == rows["data"]["cell"] and row["like"], (name, row)
        assert abs(row["rain"] - rain) < (0.01 if rain == published_rain else 3.0), (name, row)
        assert abs(row["snow"] / row["rain"] - snow_share) < 0.005 and abs(row["snow_share"] - snow_share) < 0.005, (name, row)
        assert abs(row["sheds"] - sheds) < 3.0, (name, row)
        assert abs(row["sheds"] / by_volume - over_volume) < 0.02 and abs(row["sheds"] / by_coefficient - over_coefficient) < 0.02, (name, row)
        assert row["sheds_most_month"] == 4, (name, row)                        # the land sheds the most in April under each
    # the conditional statements of the docstring, as the rows give them
    both = rows["published_rain_and_snow"]["sheds"]
    assert both < by_volume < by_coefficient                                    # under the published figures the model sheds less than either published runoff
    assert rows["data_rain_published_snow"]["sheds"] > 1.25 * by_coefficient    # under the rain data's total it sheds more than either
    for more_snow, less_snow in (("data", "data_rain_published_snow"), ("published_rain", "published_rain_and_snow")):
        assert 45.0 < rows[more_snow]["sheds"] - rows[less_snow]["sheds"] < 60.0      # what the harness's snow adds, at either total


def test_what_the_ties_decide_about_the_caspian(earth, outcomes):
    """Found, then kept: it keeps the Caspian's reason true [MEASURED: handoff/repin/repin.log, lines "lake_books"
    and "caspian over settlements"]. The lake overflows as the engine settles ties and in 19 of 20 random
    settlements, by 3.1 to 23.4 km3 a year; in 1 it keeps its water. In none does the water that runs over reach
    the sea: it ends in a closed lake. ("In none of 20" rules out only what comes more often than about one time in
    seven.)"""
    built = outcomes["engine"]["caspian"]
    assert built["overflows"] and abs(built["outflow_km3"] - 17.88) < 0.05 and abs(built["area_km2"] - 1_089_603) < 1_000 and built["level_m"] == 61.0
    assert built["overflow_ends"] == "closed lake"
    there = [r["caspian"] for r in drawn(outcomes)]
    assert sum(not c["overflows"] for c in there) == 1
    over = [c["outflow_km3"] for c in there if c["overflows"]]
    assert abs(min(over) - 3.07) < 0.05 and abs(max(over) - 23.40) < 0.05
    assert all(c["overflow_ends"] == "closed lake" for c in there if c["overflows"]) and all(c["overflow_ends"] is None for c in there if not c["overflows"])
    assert abs(min(c["area_km2"] for c in there) - 1_072_838) < 1_000 and abs(max(c["area_km2"] for c in there) - 1_089_603) < 1_000
    assert min(c["level_m"] for c in there) == 60.0 and max(c["level_m"] for c in there) == 61.0
    assert all(c["area_km2"] > 2.4 * 436_000 for c in there)                    # far too large in every one of the 20 drawn
    t = ref.tally(drawn(outcomes))
    assert t["caspian_closed"] == 1 and t["caspian_to_sea"] == 0
    lake = earth.lake_at(*ref.CASPIAN)
    assert abs(lake["inflow_m3_per_year"] / 1e9 - 669.0) < 3.0
    # the arithmetic of the reason: the depth off the land that feeds the lake, beside 300 km3 off 3 million km2
    assert abs(1e6 * 300.0 / 3.0e6 - 100.0) < 1e-9 and abs(237.0 / 0.8 - 296.0) < 0.5
    books = ref.lake_books(earth)
    assert abs(books["brought_km3"] - 590.0) < 3.0 and abs(books["outflow_km3"] - built["outflow_km3"]) < 1e-9
    assert abs(books["loses_mm"] - 933.0) < 3.0 and abs(books["rain_mm"] - 408.0) < 3.0
    assert abs(books["catchment_km2"] - 4.05e6) < 0.02e6 and abs(books["outside_km2"] - 2.96e6) < 0.02e6 and abs(books["depth_mm"] - 199.0) < 2.0
    assert books["holds_voronezh"]
    end = books["overflow"]
    assert end["ends"] == "closed lake" and end["cells"] == 4 and abs(end["area_km2"] - 19_939) < 100
    assert abs(end["lat"] - 42.2) < 0.1 and abs(end["lon"] - 57.1) < 0.1


INLAND = {      # a place in it; the area (km2) and the level (m) between which the lake must come back: chosen when the test was first written
    "the Black Sea": ((43.0, 34.0), (350_000, 650_000), (-20.0, 30.0)),
    "the Baltic": ((58.0, 20.0), (150_000, 450_000), (-20.0, 20.0)),
    "the Great Lakes": ((47.5, -87.0), (200_000, 400_000), (165.0, 195.0)),
}
INLAND_MISSED = {
    "the Black Sea": "A lake of 612,693 km2 stands at 32 m at the Black Sea's place, where the test asks for under 30 m. Its water "
                     "leaves through a cell at 40.5 N, 27.3 E. Of that cell's data points 78 % are ocean in the data and its "
                     "mean height is -5.6 m; the valley rule, which leaves out the water in a cell, hands it to Drainage at 32 "
                     "m, the height of its shores. [MEASURED: handoff/repin/more1.log] Under the water poured before the "
                     "fifth check the lake stood at 0 m and this test passed.",
}


@pytest.mark.parametrize("name", [pytest.param(name, marks=missed(INLAND_MISSED[name])) if name in INLAND_MISSED else name for name in INLAND])
def test_a_sea_that_is_cut_off_or_a_great_lake_comes_back_as_a_lake_near_its_real_size(earth, name):
    """Found, then kept. SeaLevel leaves the Black Sea and the Baltic dry: the data cut off the first, the mesh the
    second. Hydrology fills them again from Earth's rain: more water reaches each than its surface can lose, as on
    Earth, so each rises until it overflows. The Great Lakes appear too. The engine gives 612,693 km2 at 32 m,
    265,947 km2 at 8 m and 298,119 km2 at 179 m [MEASURED]. The sizes of Earth's seas and lakes are from memory
    [UNVERIFIED]: the Black Sea 436,000 km2, the Baltic 377,000 km2, Superior, Michigan and Huron together
    244,000 km2 at 176 to 183 m. The bounds are those of the test's first version and were not moved when the
    Black Sea's lake rose above its bound. Under a wet climate these hollows overflow, so the test shows
    that the relief holds the hollows, and little about the water [INFERRED: one climate was run]."""
    place, area_km2, level_m = INLAND[name]
    lake = earth.lake_at(*place)
    assert lake is not None and lake["overflows"]
    assert area_km2[0] < lake["area_m2"] / 1e6 < area_km2[1] and level_m[0] < lake["level_m"] < level_m[1], \
        f"{name}: a lake of {lake['area_m2'] / 1e6:,.0f} km2 at {lake['level_m']:.0f} m"


def test_the_lakes_that_stand_for_the_inland_seas_and_what_raises_the_black_sea(earth, flood):
    """Found, then kept: it keeps the numbers of the test above and of its reason true."""
    found = {name: earth.lake_at(*place) for name, (place, _, _) in INLAND.items()}
    assert {name: (round(float(lake["area_m2"]) / 1e6, -2), float(lake["level_m"])) for name, lake in found.items()} == {
        "the Black Sea": (612_700.0, 32.0), "the Baltic": (265_900.0, 8.0), "the Great Lakes": (298_100.0, 179.0)}
    h = earth.hydrology()
    row = int(np.asarray(h.drivers["lake_fraction"]["lake"]).astype(np.int64)[earth.cell(*INLAND["the Black Sea"][0])])
    outlet = int(h.tables["lakes"]["outlet_cell"][row])
    assert abs(earth.mesh.lat[outlet] - 40.5) < 0.1 and abs(earth.mesh.lon[outlet] - 27.3) < 0.1
    assert abs(ref.data_points_of_cells(earth, flood)["ocean_share"][outlet] - 0.78) < 0.01
    assert abs(earth.mean[outlet] - (-5.6)) < 0.1 and earth.ground[outlet] == 32.0 and not earth.wet[outlet]
    assert not ref.raw_at(flood, *INLAND["the Black Sea"][0])["ocean"] and ref.raw_at(flood, *INLAND["the Baltic"][0])["ocean"]


def test_open_water_under_the_caspians_sky_loses_about_a_metre_a_year(earth):
    """Found, then kept: what the demand for water gives for open water at the place of the Caspian, 800 to 1,100 mm
    a year (the engine: 1,002 mm at the place, 933 mm over the whole lake [MEASURED]). The real sea loses about
    1,000 mm a year [UNVERIFIED: from memory; one source opened gives 670 mm from a weather model's data, with a
    sea of 436,000 km2, numbers that do not balance its own inflow]."""
    air = earth.hydrology().fields["evapotranspiration"].astype(np.float64).sum(axis=0)[earth.cell(*ref.CASPIAN)]
    assert earth.hydrology().fields["lake_fraction"][earth.cell(*ref.CASPIAN)] == 1.0 and 800.0 < air < 1100.0
    assert abs(air - 1002.0) < 2.0 and abs(ref.lake_books(earth)["loses_mm"] - 933.0) < 3.0


@missed("6.28 % of the land lies under lakes, 9.37 million km2 (6.25 to 6.28 % in 20 random settlements). Twelve lakes larger "
        "than 100,000 km2 hold 54 % of it, where Earth has one of that size, the Caspian. Eleven of the twelve have their "
        "lowest point in a hollow that the relief data hold on their own grid. Five of the eleven stand where Earth has a "
        "sea or a great lake, though none of that size: at the places of the Caspian (1,089,603 km2, two and a half to "
        "three times the sea), the Black Sea (612,693), the upper Great Lakes (298,119), Great Slave Lake (131,455) and "
        "Lake Ontario (109,370). Six stand where Earth has no such water: in the basins of the Congo (880,226 km2), the "
        "Amazon (629,173) and the Danube (250,841), on the West Siberian plain (437,843) and in the lowlands of the Amur "
        "(180,651) and the Lena (150,490). The twelfth is the Baltic (265,947), which is ocean in the data and which the "
        "mesh cuts off. [MEASURED: tools/earth_relief.py, part 4; handoff/repin/more1.log. UNVERIFIED, from memory: "
        "which waters Earth has at those places]")
def test_lakes_cover_no_more_of_the_land_than_on_earth(earth):
    """Lakes larger than 0.002 km2 cover 3.7 % of Earth's land that is free of ice [DOCUMENTED at second hand:
    Verpoorter et al. 2014, as a page that reports the paper quotes it; the paper itself could not be opened]. The
    condition asks for under 4 % of the mesh's land. It was written with the engine's 6 % in view, as the
    statement of a pattern that the engine is known to miss."""
    f = earth.hydrology().fields
    flooded = (f["lake_fraction"].astype(np.float64) * earth.area).sum() / earth.area[earth.land].sum()
    assert flooded < 0.04, f"{100 * flooded:.1f} % of the land under lakes"


def test_the_twelve_great_lakes_of_the_mesh_and_the_hollows_of_the_data(earth, flood, outcomes):
    """Found, then kept: it keeps the reason above true. Twelve lakes are larger than 100,000 km2; they hold 54 % of
    the water surface; the deepest cell of eleven lies at a data point that is not ocean and is joined to the ocean
    only above its own height; the twelfth, the Baltic, lies on ocean of the data."""
    h = earth.hydrology()
    lakes, f = h.tables["lakes"], h.fields
    which = np.asarray(h.drivers["lake_fraction"]["lake"]).astype(np.int64)
    big = np.flatnonzero(lakes["area_m2"] > 1e11)
    assert sorted(round(float(a) / 1e6) for a in lakes["area_m2"][big]) == [
        109_370, 131_455, 150_490, 180_651, 250_841, 265_947, 298_119, 437_843, 612_693, 629_173, 880_226, 1_089_603]
    all_lakes = (f["lake_fraction"].astype(np.float64) * earth.area).sum()
    assert abs(lakes["area_m2"][big].sum() / all_lakes - 0.537) < 0.002 and abs(all_lakes / 1e12 - 9.371) < 0.003
    in_a_hollow_of_the_data, on_ocean = [], []
    for row in big:
        cells = np.flatnonzero((which == row) & (f["lake_fraction"] > 0))
        deepest = int(cells[np.argmin(earth.ground[cells])])
        data = ref.raw_at(flood, float(earth.mesh.lat[deepest]), float(earth.mesh.lon[deepest]))
        (on_ocean if data["ocean"] else in_a_hollow_of_the_data if data["level"] > data["height"] else []).append(round(float(lakes["area_m2"][row]) / 1e6))
    assert on_ocean == [265_947] and len(in_a_hollow_of_the_data) == 11
    shares = [r["lakes_share"] for r in drawn(outcomes)]
    assert abs(outcomes["engine"]["lakes_share"] - 0.0628) < 0.0002 and abs(min(shares) - 0.0625) < 0.0002 and abs(max(shares) - 0.0628) < 0.0002


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
    e = Engine(DATA, profile="preview", overrides=ref.earth_twin_overrides(DATA, get_mesh(5)))
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


@missed("13.4 K against Earth's 31.1 K [MEASURED]. Over that land the twin's coldest month is as cold as Earth's (-12.6 C "
        "against -12.7 C) and its warmest is 17 K too cold (1.4 C against 18.4 C); the year is 9.3 K too cold (-5.8 C against "
        "3.5 C), and 52 % of that land lies under snow in every month [MEASURED: handoff/pass2/twin_seasons.log; the test of "
        "the twin's expected failures, below]. Two causes were measured afterwards, on twins built with one "
        "constant changed (python handoff/pass3/seasons_apart.py, seasons_sea.py; their logs beside them; no test holds "
        "those runs): with no snow counted on the ground the warmest month is 9.1 C and the coldest -7.3 C, and with a sea "
        "that warms three times faster the swing is 20.5 K. The sea of the twin hardly has seasons, and the land is tied "
        "to it; snow that never melts cools summer and winter alike, which hides in winter that the land is tied to the "
        "sea. No single heat capacity of the sea returns both the northern and the southern seas, so nothing is mended "
        "(docs/BUILD_NOTES.md, section 4.9).")
def test_northern_land_is_far_warmer_in_july_than_in_january_as_on_earth(twin):
    """Between 40 and 60 degrees north Earth's land is 31 K warmer in July than in January [MEASURED from the
    temperature data]. The condition: the twin's land reaches three quarters of that."""
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    north = land & (m.lat > 40) & (m.lat < 60)
    swing = ((celsius[6] - celsius[0]) * area)[north].sum() / area[north].sum()
    measured = ((earth_celsius[6] - earth_celsius[0]) * area)[north].sum() / area[north].sum()
    assert abs(measured - 31.0) < 2.0                         # Earth, from the temperature data
    assert swing > 0.75 * measured, f"{swing:.1f} K against {measured:.1f} K"


@missed("Group D takes 2.1 % of the twin's land, and the polar group E 46.3 % where Earth has 12.8 %, and 35 % of "
        "the twin's land lies under snow in every month [MEASURED]. That group D is missing because northern land with "
        "warm summers on Earth stays under 10 C in its warmest month on the twin is a reading: the share of that land "
        "was not counted [INFERRED].")
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
    "at 39 degrees [MEASURED]. The twin's northern land is too cold and too dry: between 40 and 60 degrees it gets 440 mm "
    "against Earth's 654, and poleward of 60 degrees 181 mm against 495 [MEASURED]. That it is dry because it is cold is a "
    "reading, not a measurement [INFERRED].")), "south"])
def test_on_the_twin_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40(twin, half):
    """The design's pass condition for rain, on the engine's own climate over Earth's land, where Earth itself
    meets it (the first test of this file)."""
    m, land, yearly, lat, land_rain = _twin_land_rain(twin)
    sign = 1 if half == "north" else -1
    side = (sign * lat > 0) & (sign * lat < 60) & ~np.isnan(land_rain)
    driest = sign * lat[side][np.argmin(land_rain[side])]
    assert 15 <= driest <= 40, f"the driest band lies at {driest:.0f} degrees, with {land_rain[side].min():.0f} mm"


@missed("440 mm a year against Earth's 654 mm [MEASURED]. The twin's land there is 9.3 K too cold in the yearly mean (-5.8 C "
        "against 3.5 C) and 52 % of it lies under snow in every month [MEASURED: handoff/pass2/twin_seasons.log]. That cold "
        "air holds little vapour and that ground under snow gives none back is a chain that was not measured link by link "
        "[INFERRED].")
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
    # the numbers that the reasons give beside those: the seasons of the land at 40 to 60 north, and its snow
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    north = land & (m.lat > 40) & (m.lat < 60)
    mean = lambda x: float((x * area)[north].sum() / area[north].sum())
    mine, earths = np.array([mean(celsius[k]) for k in range(12)]), np.array([mean(earth_celsius[k]) for k in range(12)])
    assert abs(mine.mean() - (-5.8)) < 0.1 and abs(earths.mean() - 3.5) < 0.1
    assert abs(mine.min() - (-12.6)) < 0.1 and abs(earths.min() - (-12.7)) < 0.1
    assert abs(mine.max() - 1.4) < 0.1 and abs(earths.max() - 18.4) < 0.1
    snow = f["snow_cover"].astype(np.float64)
    assert abs(100.0 * area[north & (snow.min(axis=0) > 0.5)].sum() / area[north].sum() - 52.3) < 0.5
    assert abs(100.0 * area[land & (snow.min(axis=0) > 0.5)].sum() / area[land].sum() - 35.3) < 0.5
    # ... the polar group's share, Earth's own driest northern band at the same cells, and the rain poleward of 60 north
    names = twin[0].registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[f["climate_class"]]
    assert abs(100.0 * area[land & (group == "E")].sum() / area[land].sum() - 46.3) < 0.2
    _, _, yearly, lat, land_rain = _twin_land_rain(twin)
    earth_rain = ref.at_cell_centres(m, *ref.rain_monthly()).sum(axis=0)
    _, earths_bands = op.zonal_mean(m, earth_rain, 5.0, mask=land.astype(np.float64))
    side = (lat > 0) & (lat < 60) & ~np.isnan(land_rain)
    assert abs(lat[side][np.nanargmin(earths_bands[side])] - 38.9) < 0.5
    far_north = land & (m.lat > 60)
    assert abs((yearly * area)[far_north].sum() / area[far_north].sum() - 181.0) < 2.0
    assert abs((earth_rain * area)[far_north].sum() / area[far_north].sum() - 495.0) < 2.0
