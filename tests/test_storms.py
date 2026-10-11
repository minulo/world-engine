"""Known answers of the four processes of build step 8 (design, Layer 9): StormClimatology, WeatherStatistics,
SynopticStorms and DailyWeather, each on inputs built so that the result is known."""
import numpy as np
import pytest

from conftest import DATA
from worldengine.library.units import SECONDS_PER_DAY
from worldengine.testing import Harness

MONTHS = 12


@pytest.fixture(scope="module")
def h():
    return Harness(level=4, data_dir=DATA)


def monthly(h, value):
    a = np.asarray(value, dtype=np.float64)
    return np.broadcast_to(a, (h.months,) + a.shape).copy()


def geometry(h):
    return h.run("PlanetGeometry").fields


def days_per_month(h):
    return h.planet["year_length_s"] / h.months / SECONDS_PER_DAY


# ------------------------------------------------------------------------------------------- StormClimatology
def storm_inputs(h, sea=None, t=301.15, wind=None, steer=None, growth=0.0, water=None):
    g, n = geometry(h), h.mesh.n
    sea = np.ones(n, dtype=bool) if sea is None else sea
    wind = np.zeros((n, 3)) if wind is None else wind
    steer = wind if steer is None else steer
    return {"surface_temperature": monthly(h, np.full(n, t) if np.isscalar(t) else t), "wind": monthly(h, wind),
            "steering_wind": monthly(h, steer), "baroclinicity": monthly(h, np.full(n, growth) if np.isscalar(growth) else growth),
            "column_water": monthly(h, np.full(n, 50.0 if water is None else water)), "ocean_mask": sea,
            "coriolis_parameter": g["coriolis_parameter"]}


def test_without_wind_the_track_density_is_the_growth_over_a_storms_life(h):
    """With nothing carried, the steady answer of growth against fading is the growth rate times the life."""
    out = h.run("StormClimatology", reads=storm_inputs(h, growth=0.4)).fields["storm_track_density"]
    life = h.params["models"]["slots"]["StormClimatology"]["constants"]["storm_life_days"]
    assert np.allclose(out, 0.4 * life, rtol=1e-6)


def test_tracks_lie_downwind_of_where_storms_grow(h):
    m = h.mesh
    patch = (np.abs(m.lat - 45) < 6) & (np.abs(m.lon) < 6)
    out = h.run("StormClimatology", reads=storm_inputs(h, steer=12.0 * m.east, growth=np.where(patch, 1.0, 0.0))).fields
    d = out["storm_track_density"][0]
    band = np.abs(m.lat - 45) < 6
    downwind = band & (m.lon > 15) & (m.lon < 35)
    upwind = band & (m.lon < -15) & (m.lon > -35)
    assert d[downwind].mean() > 10 * max(d[upwind].mean(), 1e-12)


def test_potential_intensity_follows_its_relation_and_is_zero_over_land_and_cool_sea(h):
    c = h.params["models"]["slots"]["StormClimatology"]["constants"]
    m, n = h.mesh, h.mesh.n
    sea = m.lon > -150
    t = np.where(m.lat > 0, 301.15, 288.15)                       # 28 C in the north, 15 C in the south
    out = h.run("StormClimatology", reads=storm_inputs(h, sea=sea, t=t)).fields["potential_intensity"][0]
    want = c["intensity_a_m_s"] + c["intensity_b_m_s"] * np.exp(c["intensity_c_per_k"] * (28.0 - c["intensity_t0_c"]))
    assert np.allclose(out[sea & (m.lat > 0)], want, rtol=1e-6)
    assert (out[~sea] == 0).all() and (out[m.lat < 0] == 0).all()


def test_no_cyclone_forms_at_the_equator_over_land_or_where_the_wind_shears(h):
    m = h.mesh
    sea = m.lon > -150
    calm = h.run("StormClimatology", reads=storm_inputs(h, sea=sea)).fields["tc_genesis_potential"][0]
    assert (calm[~sea] == 0).all()
    assert calm[sea & (np.abs(m.lat) < 2)].mean() < 0.05 * calm[sea & (np.abs(m.lat - 15) < 3)].mean()
    # the spin term grows with the Coriolis parameter, to the power 1.5, where nothing else changes
    a, b = sea & (np.abs(m.lat - 10) < 1.5), sea & (np.abs(m.lat - 20) < 1.5)
    ratio = calm[b].mean() / calm[a].mean()
    want = (np.sin(np.deg2rad(m.lat[b])).mean() / np.sin(np.deg2rad(m.lat[a])).mean()) ** 1.5
    assert ratio == pytest.approx(want, rel=0.1)
    # a shear of 10 m/s divides the index by (1 + 0.1 * 10)^2 = 4
    sheared = h.run("StormClimatology", reads=storm_inputs(h, sea=sea, steer=10.0 * m.east)).fields["tc_genesis_potential"][0]
    assert np.allclose(sheared[sea], calm[sea] / 4.0, rtol=1e-6)


# ------------------------------------------------------------------------------------------- WeatherStatistics
def stats_inputs(h, t, height=0.0, tracks=1.0, rain=60.0, sea=None):
    n = h.mesh.n
    return {"surface_temperature": monthly(h, t), "height_above_sea": np.full(n, height) if np.isscalar(height) else height,
            "storm_track_density": monthly(h, np.full(n, tracks)), "precipitation": monthly(h, np.full(n, rain) if np.isscalar(rain) else rain),
            "ocean_mask": np.zeros(n, dtype=bool) if sea is None else sea}


def test_an_even_temperature_strays_nowhere(h):
    out = h.run("WeatherStatistics", reads=stats_inputs(h, np.full(h.mesh.n, 285.0))).fields["daily_temperature_spread"]
    assert np.abs(out).max() < 1e-9


def test_the_spread_is_the_contrast_across_one_mixing_length(h):
    """A temperature falling by 0.6 K per degree of latitude, on land with dense storm tracks: away from the poles,
    the spread is that gradient times the mixing length."""
    m = h.mesh
    c = h.params["models"]["slots"]["WeatherStatistics"]["constants"]
    per_m = 0.6 / (np.deg2rad(1.0) * h.planet["radius_m"])
    out = h.run("WeatherStatistics", reads=stats_inputs(h, 300.0 - 0.6 * np.abs(m.lat))).fields["daily_temperature_spread"][0]
    mid = (np.abs(m.lat) > 30) & (np.abs(m.lat) < 60)
    assert np.median(out[mid]) == pytest.approx(per_m * c["mixing_length_km"] * 1000.0, rel=0.1)


def test_a_mountain_that_is_cold_only_by_its_height_adds_no_spread(h):
    m = h.mesh
    lapse = h.params["models"]["shared"]["lapse_rate_k_per_km"]
    height = 3000.0 * np.exp(-((m.lat - 40) ** 2 + m.lon ** 2) / 50.0)
    out = h.run("WeatherStatistics", reads=stats_inputs(h, 290.0 - lapse * height / 1000.0, height=height)).fields
    assert np.abs(out["daily_temperature_spread"]).max() < 1e-4      # the inputs are stored in 32 bits


def test_wet_days_grow_with_rain_to_the_power_0_45_and_never_exceed_every_day(h):
    c = h.params["models"]["slots"]["WeatherStatistics"]["constants"]
    n, per = h.mesh.n, days_per_month(h)
    rain = np.where(np.arange(n) % 3 == 0, 0.0, np.where(np.arange(n) % 3 == 1, 2.0 * per, 500.0 * per))
    out = h.run("WeatherStatistics", reads=stats_inputs(h, np.full(n, 285.0), rain=rain)).fields["wet_day_fraction"][0]
    assert (out[rain == 0] == 0).all()
    assert np.allclose(out[rain == 2.0 * per], c["wet_day_scale"] * 2.0 ** 0.45, rtol=1e-5)
    assert (out[rain == 500.0 * per] == 1.0).all()


# ------------------------------------------------------------------------------------------- SynopticStorms
def storms_inputs(h, density=None, genesis=None, steer=None, t=302.0, intensity=70.0):
    g, n = geometry(h), h.mesh.n
    return {"storm_track_density": monthly(h, np.zeros(n) if density is None else density),
            "tc_genesis_potential": monthly(h, np.zeros(n) if genesis is None else genesis),
            "potential_intensity": monthly(h, np.full(n, intensity)), "steering_wind": monthly(h, np.zeros((n, 3)) if steer is None else steer),
            "ocean_mask": np.ones(n, dtype=bool), "surface_temperature": monthly(h, np.full(n, t)),
            "coriolis_parameter": g["coriolis_parameter"], "cell_area": g["cell_area"]}


def test_a_day_of_storms_is_the_same_however_often_it_is_asked_for(h):
    m = h.mesh
    ins = storms_inputs(h, density=np.where(np.abs(m.lat) > 30, 2.0, 0.0), steer=10.0 * m.east)
    a = h.run("SynopticStorms", reads=ins, round_no=50).tables["storms"]
    h.run("SynopticStorms", reads=ins, round_no=49)
    b = h.run("SynopticStorms", reads=ins, round_no=50).tables["storms"]
    assert all(np.array_equal(a[k], b[k]) for k in a)


def test_storms_are_born_where_the_maps_allow_and_live_no_longer_than_the_window(h):
    m = h.mesh
    window = h.params["models"]["shared"]["weather_look_back_days"]
    per_day = h.params["models"]["slots"]["SynopticStorms"]["constants"]["midlatitude_births_per_day"]
    counts = []
    for day in range(100, 400, 25):
        t = h.run("SynopticStorms", reads=storms_inputs(h, density=np.where(m.lat > 40, 1.0, 0.0)), round_no=day).tables["storms"]
        assert (np.asarray(t["kind"]) == 1).all()                  # no genesis potential: no tropical cyclone
        assert (np.asarray(t["lat"]) > 38).all()                   # no wind: a storm stays where it was born
        assert (np.asarray(t["born_day"]) > day - window).all()
        counts.append(len(t["kind"]))
    assert np.mean(counts) == pytest.approx(per_day * window, rel=0.25)


def test_a_tropical_cyclone_without_steering_drifts_toward_the_pole_and_the_west(h):
    m = h.mesh
    seed_cell = int(np.argmin((m.lat - 15) ** 2 + (m.lon - 140) ** 2))
    genesis = np.zeros(m.n)
    genesis[seed_cell] = 1.0
    moved = []
    for day in range(200, 300, 7):
        t = h.run("SynopticStorms", reads=storms_inputs(h, genesis=genesis), round_no=day).tables["storms"]
        for lat, lon, born in zip(t["lat"], t["lon"], t["born_day"]):
            if born < day:
                moved.append((lat - m.lat[seed_cell], lon - m.lon[seed_cell]))
    assert len(moved) > 3
    assert all(dlat > 0 and dlon < 0 for dlat, dlon in moved)


# ------------------------------------------------------------------------------------------- DailyWeather
def weather_inputs(h, t=285.0, rain=60.0, wet=0.4, spread=4.0, storms=0.0):
    m, n = h.mesh, h.mesh.n
    full = lambda v: monthly(h, np.full(n, v) if np.isscalar(v) else v)
    return {"surface_temperature": full(t), "precipitation": full(rain), "wind": monthly(h, 5.0 * m.east),
            "sea_level_pressure": full(101325.0), "daily_temperature_spread": full(spread), "wet_day_fraction": full(wet),
            "storm_influence": np.full(n, storms) if np.isscalar(storms) else storms}


def test_days_scatter_around_the_climate_by_its_spread_and_keep_its_rain(h):
    n, per = h.mesh.n, days_per_month(h)
    temps, rains = [], []
    for day in range(0, 360, 3):
        out = h.run("DailyWeather", reads=weather_inputs(h), round_no=day).fields
        temps.append(out["weather_temperature"])
        rains.append(out["weather_precipitation"])
        assert np.mean(out["weather_temperature"]) == pytest.approx(285.0, abs=1e-3)     # the day's noise has no mean over the planet
    temps, rains = np.array(temps), np.array(rains)
    assert np.median(temps.std(axis=0)) == pytest.approx(4.0, rel=0.25)
    assert rains.mean() == pytest.approx(60.0 / per, rel=0.1)                   # the month's rain, a day at a time
    assert (rains >= 0.1).mean() == pytest.approx(0.4, abs=0.05)                # the share of wet days


def test_where_no_rain_falls_in_the_month_none_falls_on_any_day(h):
    m = h.mesh
    rain = np.where(m.lat > 0, 0.0, 90.0)
    for day in (3, 77, 300):
        out = h.run("DailyWeather", reads=weather_inputs(h, rain=rain), round_no=day).fields["weather_precipitation"]
        assert (out[m.lat > 0] == 0).all() and out[m.lat < 0].max() > 0


def test_a_storm_lowers_the_pressure_and_brings_rain(h):
    m = h.mesh
    c = h.params["models"]["slots"]["DailyWeather"]["constants"]
    storm = np.where(m.lat > 0, 1.0, 0.0)
    calm = h.run("DailyWeather", reads=weather_inputs(h, spread=0.0, wet=0.1), round_no=40).fields
    stormy = h.run("DailyWeather", reads=weather_inputs(h, spread=0.0, wet=0.1, storms=storm), round_no=40).fields
    assert np.allclose(stormy["weather_pressure"] - calm["weather_pressure"], -c["storm_low_pa"] * storm)
    assert (stormy["weather_precipitation"][m.lat > 0] > 0).mean() > 2 * (calm["weather_precipitation"][m.lat > 0] > 0).mean()
