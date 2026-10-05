"""Single processes judged against patterns measured on Earth (design, Layer 9).

Each test hands one process inputs measured on Earth (relief, rain, temperature) and asks for a pattern that an
atlas shows. Nothing here builds a seeded world: the question is whether a process, given the truth as its input,
returns the truth as its output. The data is fetched by tools/fetch_reference_data.py; without it every test here
is skipped. All runs are on the standard mesh, 163,842 cells about 60 km apart.

What each condition is and when it was set:
  * the conditions marked "set before the run" were written down before the process had been run on Earth's data;
  * the conditions marked "found, then kept" describe something the first run showed and nobody had asked for.
    They guard against losing it, and prove less.
A test marked xfail records a pattern of Earth that the engine does not return, with the reason. It is strict: if
the engine starts to return the pattern, the mark must go.

The places are given to the nearest half degree from memory [UNVERIFIED]; the distances asked for are hundreds of
kilometres, so that is close enough.
"""
import numpy as np
import pytest
import yaml

from conftest import DATA
from worldengine import reference as ref
from worldengine.engine import Engine
from worldengine.library import drainage as dr
from worldengine.library import operators as op
from worldengine.mesh import get_mesh
from worldengine.testing import Harness

pytestmark = pytest.mark.skipif(not ref.available(), reason="the Earth reference data is not here: run python tools/fetch_reference_data.py")

R = 6.371e6
YEAR_S = 31558150.0
LEVEL = 7
VALLEY_SHARE = 0.1          # a land cell's height for drainage is the height below which a tenth of its land points lie


class Earth:
    """Earth on the mesh: its relief, the sea that SeaLevel pours on it, its drainage, and its measured climate."""

    def __init__(self, level=LEVEL):
        self.mesh = m = get_mesh(level)
        self.h = hh = Harness(level=level)
        g = hh.run("PlanetGeometry").fields
        self.area, self.latitude = g["cell_area"], g["latitude"]
        lat, lon, height = ref.relief()
        cells = ref.cell_of_every_point(m, lat, lon)
        self.mean = ref.cell_means(m, lat, lon, height, cells)
        self.sea = hh.run("SeaLevel", reads={"elevation": self.mean, "cell_area": self.area})
        self.wet = self.sea.fields["ocean_mask"]
        self.land = ~self.wet
        self.sea_level = float(self.sea.tables["seas"]["surface_m"][0])
        floors = ref.cell_low_values(m, lat, lon, np.where(height > self.sea_level, height, np.nan), VALLEY_SHARE, cells)
        self.ground = np.where(self.wet | ~np.isfinite(floors), self.mean, floors)
        self.drainage = hh.run("Drainage", reads={"elevation": self.ground, "ocean_mask": self.wet, "sea_depth": self.sea.fields["sea_depth"],
                                                  "cell_area": self.area}, tables={"seas": self.sea.tables["seas"]})
        self.rain = ref.at_cell_centres(m, *ref.rain_monthly())
        self.celsius = ref.at_cell_centres(m, *ref.temperature_monthly())

    def cell(self, lat, lon):
        a, b = np.deg2rad(lat), np.deg2rad(lon)
        return int(np.argmax(self.mesh.xyz @ np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])))

    def km(self, cell, lat, lon):
        return float(np.arccos(np.clip(self.mesh.xyz[cell] @ self.mesh.xyz[self.cell(lat, lon)], -1, 1)) * R / 1000.0)

    def hydrology(self):
        if not hasattr(self, "_hydrology"):
            kelvin = self.celsius + 273.15
            snow_share = np.clip((276.15 - kelvin) / 6.0, 0.0, 1.0)             # the ramp Moisture uses for monthly means
            sunlight = self.h.run("Insolation", reads={"latitude": self.latitude}).fields["insolation"]
            d = self.drainage
            self._hydrology = self.h.run("Hydrology", reads={
                "precipitation": self.rain, "snowfall": self.rain * snow_share, "surface_temperature": kelvin, "insolation": sunlight,
                "elevation": self.ground, "height_above_sea": np.where(self.wet, 0.0, self.mean - self.sea_level),
                "flow_receiver": d.fields["flow_receiver"], "depression_id": d.fields["depression_id"], "cell_area": self.area,
                "ocean_mask": self.wet}, tables={"hollows": d.tables["hollows"]})
        return self._hydrology

    def lake_at(self, lat, lon):
        """The row of the table of lakes for the lake at a place, or None."""
        row = int(self.hydrology().drivers["lake_fraction"]["lake"][self.cell(lat, lon)])
        return None if row < 0 else {k: v[row] for k, v in self.hydrology().tables["lakes"].items()}


@pytest.fixture(scope="module")
def earth():
    return Earth()


# ---------------------------------------------------------------------------------------------- the pattern itself
def test_on_earth_the_driest_land_lies_in_a_belt_between_15_and_40_degrees():
    """The pattern that tests/test_world.py asks of a seeded world, measured on Earth: GPCP rain of 1979 to 2010 over
    the land of a one-degree mask, in bands of 5 degrees. North: 566 mm at 27.5; south: 629 mm at 32.5."""
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
    assert abs((yearly * area).sum() / area.sum() - 804.0) < 10.0                  # mm a year over land; 1,048 over the sea
    bands = yearly.reshape(36, 2, -1), area.reshape(36, 2, -1)
    band_lat = lat.reshape(36, 2).mean(axis=1)
    land_rain = (bands[0] * bands[1]).sum(axis=(1, 2)) / np.maximum(bands[1].sum(axis=(1, 2)), 1e-12)
    for sign, driest_at, driest_mm in ((1, 27.5, 566.0), (-1, 32.5, 629.0)):
        side = (sign * band_lat > 0) & (sign * band_lat < 50)
        k = np.argmin(np.where(side, land_rain, np.inf))
        assert sign * band_lat[k] == driest_at and abs(land_rain[k] - driest_mm) < 5.0
        storm_belt = land_rain[(sign * band_lat > 40) & (sign * band_lat < 55)].mean()
        assert storm_belt > 1.1 * land_rain[k]


# ---------------------------------------------------------------------------------------------- SeaLevel
def test_earths_water_poured_on_earths_relief_comes_to_rest_at_earths_sea_level(earth):
    """Set before the run: the sea level within 60 m of zero, the sea over 69 to 73 % of the planet, one ocean.
    Measured: 5 m below zero, 70.3 %."""
    seas = earth.sea.tables["seas"]
    assert abs(earth.sea_level) < 60.0
    assert 0.69 < earth.area[earth.wet].sum() / earth.area.sum() < 0.73
    assert seas["volume_m3"][0] / seas["volume_m3"].sum() > 0.99
    for name, place in {"the Mediterranean": (35.0, 18.0), "the Gulf of Mexico": (25.0, -90.0), "Hudson Bay": (60.0, -85.0),
                        "the Sea of Japan": (40.0, 135.0)}.items():
        assert earth.wet[earth.cell(*place)], name
    for name, place in {"Tibet": (33.0, 88.0), "the Sahara": (23.0, 5.0), "the Amazon lowland": (-3.0, -60.0), "the Caspian": (42.0, 51.0)}.items():
        assert not earth.wet[earth.cell(*place)], name                            # (the Caspian lies below sea level, behind a barrier)


@pytest.mark.xfail(strict=True, reason="Straits narrower than a cell are closed on this mesh: the Bosporus, the strait at the mouth "
                                       "of the Red Sea and the straits of Denmark. The seas behind them stay dry in SeaLevel, and "
                                       "Hydrology then fills the Black Sea and the Baltic as lakes.")
def test_the_black_sea_the_red_sea_and_the_baltic_are_part_of_the_ocean(earth):
    for place in ((43.0, 34.0), (20.0, 38.5), (58.0, 20.0)):
        assert earth.wet[earth.cell(*place)]


# ---------------------------------------------------------------------------------------------- Drainage
def test_the_amazon_reaches_the_atlantic_and_the_nile_the_mediterranean(earth):
    """Set before the run (the design's own list): from Manaus the water reaches the sea within 600 km of the Amazon's
    mouth, and from Khartoum within 600 km of the Nile's. Measured: 214 km and 206 km."""
    basin = earth.drainage.fields["basin_id"]
    amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
    assert earth.km(amazon, -0.5, -50.0) < 600.0 and earth.km(nile, 31.5, 31.0) < 600.0
    area = earth.drainage.fields["drainage_area"]
    assert 4.5e12 < area[amazon] < 8.0e12                    # m2: the Amazon drains 6.9 million km2 (measured 6.0)
    assert 2.5e12 < area[nile] < 4.5e12                      # the Nile about 3.3 million km2 (measured 3.7)


def test_central_asia_and_the_great_basin_are_closed_hollows(earth):
    """Set before the run (the design's own list)."""
    f, t = earth.drainage.fields, earth.drainage.tables["hollows"]
    tarim, great_basin = earth.cell(39.0, 83.0), earth.cell(40.0, -116.5)
    assert f["depression_id"][tarim] > 0 and f["depression_id"][great_basin] > 0
    bottom = int(t["bottom_cell"][f["depression_id"][tarim]])
    assert earth.km(bottom, 40.2, 90.5) < 400.0              # found, then kept: the Tarim's water collects near Lop Nur (measured 150 km)
    assert 600.0 < t["bottom_m"][f["depression_id"][tarim]] < 900.0


GREAT_RIVERS = {    # a place on the river, and its mouth
    "Amazon": ((-3.1, -60.0), (-0.5, -50.0)), "Nile": ((15.6, 32.5), (31.5, 31.0)), "Mississippi": ((35.1, -90.0), (29.2, -89.3)),
    "Congo": ((0.5, 25.2), (-6.0, 12.4)), "Yangtze": ((29.6, 106.5), (31.4, 121.8)), "Ob": ((55.0, 83.0), (66.5, 69.0)),
    "Mackenzie": ((61.9, -121.4), (69.0, -134.0)), "Danube": ((48.2, 16.4), (45.2, 29.7)), "Ganges": ((25.3, 83.0), (22.0, 90.0)),
    "Parana": ((-25.3, -57.6), (-34.5, -58.0)), "Niger": ((13.5, 2.1), (4.3, 6.0)), "Lena": ((62.0, 129.7), (72.5, 127.0)),
    "Yenisei": ((56.0, 92.9), (71.0, 83.0)), "Indus": ((27.7, 68.9), (24.0, 67.5)), "Murray": ((-34.2, 142.2), (-35.5, 138.9)),
    "Volga": ((55.8, 49.1), (46.0, 48.5)), "Zambezi": ((-17.9, 25.9), (-18.8, 36.3)), "Orinoco": ((8.1, -63.5), (8.6, -61.0)),
    "St Lawrence": ((45.5, -73.6), (49.0, -66.0)), "Columbia": ((45.6, -121.2), (46.2, -124.0)), "Rhine": ((50.9, 7.0), (52.0, 4.1)),
    "Mekong": ((18.0, 102.6), (10.0, 106.5)), "Amur": ((48.5, 135.1), (52.9, 141.2)), "Huang He": ((36.1, 103.8), (37.8, 119.0))}
MISLED = {"Congo", "Ob", "Danube", "Yenisei", "Volga", "St Lawrence", "Amur", "Huang He"}


def test_two_thirds_of_the_great_rivers_reach_the_sea_where_they_do_on_earth(earth):
    """Found, then kept. With every hollow full, 16 of these 24 rivers leave the land within 300 km of their real
    mouths. The other eight are named: if one of them comes right, or another goes wrong, this test says so.

    Why the eight go wrong [INFERRED from the map of each]: the Congo, the Danube and the Huang He leave their
    inland basins through gorges narrower than a cell, which the mesh shows closed, so each finds another pass. The
    Volga ends in the Caspian, which is a hollow: full, it overflows to the Black Sea, which is a hollow too on this
    mesh, and the mouth named is where that one overflows, at the Dardanelles. On the plains of western Siberia the
    Ob and the Yenisei run together. The St Lawrence takes the valley of the Hudson and the Amur the lowland of
    Lake Khanka: each is a low pass a cell or two from the true course."""
    basin = earth.drainage.fields["basin_id"]
    off = {name for name, (place, mouth) in GREAT_RIVERS.items() if earth.km(int(basin[earth.cell(*place)]), *mouth) > 300.0}
    assert off == MISLED


@pytest.mark.xfail(strict=True, reason="A river that leaves its basin through a gorge narrower than a cell finds the range closed: "
                                       "the mesh sends the Congo out through Gabon, 730 km from its mouth.")
def test_the_congo_reaches_the_atlantic_at_its_own_mouth(earth):
    assert earth.km(int(earth.drainage.fields["basin_id"][earth.cell(0.5, 25.2)]), -6.0, 12.4) < 300.0


# ---------------------------------------------------------------------------------------------- Hydrology
def test_under_earths_rain_and_warmth_the_land_gives_back_what_earths_land_gives_back(earth):
    """Set before the run: of the rain on land, between 0.50 and 0.75 goes back to the air, and 28,000 to 52,000 km3 a
    year reach the sea. Earth: 74 of 114 thousand km3 go back, 0.65, and 40 thousand reach the sea (Trenberth, Fasullo
    and Mackaro 2011). Measured: 0.72 and 33,800 km3. The engine's land gives back too much: too much of it lies
    under lakes that are not there (see the lakes below), and under the cloud of the wet tropics the demand of the
    air is too high."""
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
    factor of two of the 220,000 m3/s that the list of rivers by discharge gives (Wikipedia). Measured: 214 km,
    143,000 m3/s."""
    f, lakes = earth.hydrology().fields, earth.hydrology().tables["lakes"]
    recv = earth.drainage.fields["flow_receiver"]
    river = f["river_discharge"].astype(np.float64).mean(axis=0)
    coast = np.flatnonzero(earth.land & (recv >= 0) & earth.wet[np.maximum(recv, 0)])
    largest = int(coast[np.argmax(river[coast])])
    into_sea = lakes["overflows"] & (lakes["spills_into_cell"] >= 0) & earth.wet[np.maximum(lakes["spills_into_cell"], 0)]
    assert not into_sea.any() or (lakes["outflow_m3_per_year"][into_sea] / YEAR_S).max() < river[largest]       # no lake outlet is larger
    assert earth.km(largest, -0.5, -50.0) < 800.0
    assert 110_000.0 < river[largest] < 440_000.0


@pytest.mark.xfail(strict=True, reason="The Caspian overflows. Its lake loses 949 mm a year, near the real figure, but 820 km3 a year "
                                       "run toward it where the real sea receives about 300 [UNVERIFIED: my recollection]: on this mesh "
                                       "its catchment takes in the Don and overflow from the Aral, and rivers that reach it "
                                       "pass through lakes that are not there.")
def test_the_caspian_stays_a_closed_lake(earth):
    """Set before the run (the design's own list)."""
    lake = earth.lake_at(42.0, 51.0)
    assert lake is not None and not lake["overflows"]


def test_seas_that_the_mesh_cuts_off_and_the_great_lakes_come_back_as_lakes_near_their_real_size(earth):
    """Found, then kept. SeaLevel leaves the Black Sea and the Baltic dry, because their straits are narrower than a
    cell. Hydrology fills them again from Earth's rain: more water reaches each than its surface can lose, as on
    Earth, so each rises until it overflows. The Great Lakes appear too.
      * the Black Sea: 511,000 km2 standing 5 m above the reference level (Earth: 436,000 km2 at sea level);
      * the Baltic: 228,000 km2 at -1 m (Earth: 377,000 km2);
      * the Great Lakes: 298,000 km2 at 179 m (Earth: 244,000 km2 at 176 to 183 m, for Superior, Michigan and Huron).
    The sizes of Earth's seas and lakes here are from memory [UNVERIFIED]."""
    for place, area_km2, level_m in (((43.0, 34.0), (350_000, 650_000), (-20.0, 30.0)), ((58.0, 20.0), (150_000, 450_000), (-20.0, 20.0)),
                                     ((47.5, -87.0), (200_000, 400_000), (165.0, 195.0))):
        lake = earth.lake_at(*place)
        assert lake is not None and lake["overflows"]
        assert area_km2[0] < lake["area_m2"] / 1e6 < area_km2[1] and level_m[0] < lake["level_m"] < level_m[1]
    caspian = earth.lake_at(42.0, 51.0)
    air = earth.hydrology().fields["evapotranspiration"].astype(np.float64).sum(axis=0)[earth.cell(42.0, 51.0)]
    assert 800.0 < air < 1100.0                              # mm a year from the open water of the Caspian (about 1,000 on Earth)
    assert caspian["inflow_m3_per_year"] > 2.0 * 300e9       # the fault recorded above: far too much water runs toward it


def test_on_earths_relief_the_mesh_floods_lowlands_that_earth_drains_through_gorges(earth):
    """Found, then kept: the size of the fault that Drainage names in its own file. A cell's height is the mean of
    its ground, so the gorges by which the Congo and the Danube leave their basins are closed, and so is the lowland
    of the Amazon in places. Hydrology floods what cannot drain: 6.5 % of the land, where Earth's lakes cover about
    2 % [UNVERIFIED]. A seeded world does not have this fault in this form: its rivers will cut their valleys on the
    mesh itself (FluvialErosion, build step 4)."""
    f = earth.hydrology().fields
    flooded = (f["lake_fraction"].astype(np.float64) * earth.area).sum() / earth.area[earth.land].sum()
    assert 0.04 < flooded < 0.09
    congo = earth.lake_at(-3.0, 16.5)
    assert congo is not None and congo["area_m2"] > 5.0e11   # a lake of 880,000 km2 in the basin of the Congo, which has none


# ---------------------------------------------------------------------------------------------- Biomes
def test_earths_measured_climate_falls_into_the_climate_classes_in_earths_shares(earth):
    """Set before the run: with CRU temperature and GPCP rain, each of the five main Köppen-Geiger groups takes a
    share of the land within 6 points of the share Peel, Finlayson and McMahon 2007 give: arid B 30.2 %, cold D
    24.6 %, tropical A 19.0 %, temperate C 13.4 %, polar E 12.8 %."""
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
    models = ref.earth_twin_models(yaml.safe_load((DATA / "models.yaml").read_text()), get_mesh(5))
    e = Engine(DATA, profile="preview", overrides={"models": models})
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
    """Found, then kept (first run of the twin): the sea stands 2 m from Earth's level and covers 70.9 % of the planet;
    the mean temperature of the year is 13.3 C against 14.0 C; the wettest land lies within 15 degrees of the equator;
    and the largest river of the twin reaches the sea where the Amazon does, with 149,000 m3/s against 220,000."""
    e, w = twin
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    assert w.settled["climate"] and e.order()["geological"][0] == "Isostasy"
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
    assert 110_000.0 < river[largest] < 440_000.0


@pytest.mark.xfail(strict=True, reason="The seasons on land are far too weak. Between 40 and 60 degrees north Earth's land is 31 K warmer "
                                       "in July than in January; the twin's is 13 K warmer. EnergyBalance spreads heat with one constant "
                                       "for land and sea, which ties the land to the sea too tightly. The next refinement proposed.")
def test_northern_land_is_far_warmer_in_july_than_in_january_as_on_earth(twin):
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    north = land & (m.lat > 40) & (m.lat < 60)
    swing = ((celsius[6] - celsius[0]) * area)[north].sum() / area[north].sum()
    measured = ((earth_celsius[6] - earth_celsius[0]) * area)[north].sum() / area[north].sum()
    assert abs(measured - 31.0) < 2.0                         # Earth, from the temperature data
    assert swing > 0.75 * measured


@pytest.mark.xfail(strict=True, reason="With summers too cool on northern land, the twin calls it polar where Earth is cold with warm "
                                       "summers: group D takes 2 % of the twin's land (Earth 24.6 %) and group E 47 % (Earth 12.8 %). "
                                       "It follows from the weak seasons; the classes themselves are right when given Earth's climate.")
def test_the_cold_climates_with_warm_summers_take_a_fifth_of_the_twins_land_as_on_earth(twin):
    m, f, area, wet, land, celsius, earth_celsius = _twin_numbers(twin)
    names = twin[0].registry.fields["climate_class"].categories
    group = np.array([n[0] for n in names])[f["climate_class"]]
    assert area[land & (group == "D")].sum() / area[land].sum() > 0.15
