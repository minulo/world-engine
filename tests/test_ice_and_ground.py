"""Known answers of the processes of build steps 6 and 7 (design, Layer 9): Cryosphere and the Albedo that reads it,
Soils and the BIOME1 Biomes, each on inputs built so that the result follows from its rule."""
import numpy as np
import pytest

from conftest import DATA
from worldengine.library.units import ZERO_CELSIUS_IN_K
from worldengine.testing import Harness


@pytest.fixture(scope="module")
def h():
    return Harness(level=3, data_dir=DATA)


def const(h, slot):
    return h.params["models"]["slots"][slot]["constants"]


def monthly(h, v):
    a = np.asarray(v, dtype=np.float64)
    return np.broadcast_to(a, (h.months,) + a.shape).copy()


def spread(h, lo, hi):
    """A value for each cell rising evenly from lo to hi over the cells."""
    return np.linspace(lo, hi, h.mesh.n)


# ------------------------------------------------------------------------------------------- Cryosphere (step 6)
def test_sea_ice_is_half_at_its_threshold_and_full_or_none_beyond_the_ramp(h):
    c = const(h, "Cryosphere")
    n = h.mesh.n
    t = np.full(n, c["sea_freezes_below_k"])
    t[: n // 3] -= c["sea_ice_ramp_k"]
    t[n // 3: 2 * n // 3] += c["sea_ice_ramp_k"]
    out = h.run("Cryosphere", reads={"surface_temperature": monthly(h, t), "ocean_mask": np.ones(n, dtype=bool)}).fields
    cover = out["snow_ice_cover"][0]
    assert (cover[: n // 3] == 1).all() and (cover[n // 3: 2 * n // 3] == 0).all() and np.allclose(cover[2 * n // 3:], 0.5)
    assert (out["permafrost"] == 0).all()                                    # no frozen ground under the sea


def test_snow_covers_the_ground_in_proportion_to_its_store_up_to_full(h):
    c = const(h, "Cryosphere")
    n = h.mesh.n
    store = spread(h, 0.0, 2 * c["full_cover_mm"])
    out = h.run("Cryosphere", reads={"surface_temperature": monthly(h, np.full(n, 270.0)), "ocean_mask": np.zeros(n, dtype=bool)},
                lagged={"snow_water": monthly(h, store)}).fields["snow_ice_cover"][0]
    assert np.allclose(out, np.minimum(store / c["full_cover_mm"], 1.0), atol=1e-6)


def test_permafrost_follows_the_year_s_mean_between_its_two_thresholds(h):
    c = const(h, "Cryosphere")
    full, none = c["permafrost_full_below_k"], c["permafrost_none_above_k"]
    yearly = spread(h, full - 2, none + 2)
    swing = 10.0 * np.cos(np.arange(h.months) * 2 * np.pi / h.months)[:, None]        # seasons around the yearly mean
    out = h.run("Cryosphere", reads={"surface_temperature": yearly[None, :] + swing, "ocean_mask": np.zeros(h.mesh.n, dtype=bool)}).fields
    assert np.allclose(out["permafrost"], np.clip((none - yearly) / (none - full), 0, 1), atol=1e-5)


# ------------------------------------------------------------------------------------------- Albedo (step 6)
def albedo(h, sea, ice, plants):
    g = h.run("PlanetGeometry").fields
    n = h.mesh.n
    return h.run("Albedo", reads={"ocean_mask": np.full(n, sea), "latitude": g["latitude"], "cell_area": g["cell_area"]},
                 lagged={"snow_ice_cover": monthly(h, np.full(n, ice)), "vegetation_cover": monthly(h, np.full(n, plants))}).fields["albedo"][0]


def test_full_ice_reflects_what_the_ice_cap_of_north_et_al_reflects_where_the_sun_angle_term_vanishes(h):
    """Where the second Legendre polynomial of the sine of latitude is zero (35.26 degrees), the low-sun term drops out:
    open sea reflects cloud plus sea seen twice through the gaps in the cloud, and full ice 0.62 (North et al. 1981)."""
    c = const(h, "Albedo")
    lat = h.run("PlanetGeometry").fields["latitude"]
    at = np.abs(np.abs(lat) - np.rad2deg(np.arcsin(np.sqrt(1 / 3)))) < 2.0
    through = (1 - c["cloud_share"]) ** 2
    assert np.allclose(albedo(h, True, 0.0, 0.0)[at], c["cloud_share"] + through * c["surface"]["sea"], atol=0.01)
    assert np.allclose(albedo(h, True, 1.0, 0.0)[at], 0.62, atol=0.01)


def test_plants_hide_part_of_the_snow_beneath_them(h):
    c = const(h, "Albedo")
    covered = albedo(h, False, 1.0, 1.0)
    plain_covered = albedo(h, False, 0.0, 1.0)
    # the snow's own share of the reflection is cut by the hidden share under full plant cover
    snow_under = covered - plain_covered
    s = np.sin(np.deg2rad(h.run("PlanetGeometry").fields["latitude"]))
    through = (1 - c["cloud_share"]) ** 2
    t = c["surface"]
    want = (1 - c["snow_hidden_by_plants"]) * (through * (t["ice"] - t["under_plants"]) - c["low_sun_term"] * (3 * s * s - 1) / 2)
    assert np.allclose(snow_under, want, atol=1e-5)


# ------------------------------------------------------------------------------------------- Soils (step 7)
def soil_inputs(h, mean_c=2.5, rain=None, demand=None, erosion=0.0, age=1000.0, rock="stable_platform", frozen=0.0, ice=0.0):
    n = h.mesh.n
    rocks = h.registry.fields["rock_type"].categories
    full = lambda v: np.full(n, v) if np.isscalar(v) else v
    return {"surface_temperature": monthly(h, full(mean_c + ZERO_CELSIUS_IN_K)),
            "precipitation": monthly(h, full(100.0 if rain is None else rain)),
            "potential_evapotranspiration": monthly(h, full(50.0 if demand is None else demand)),
            "soil_moisture": monthly(h, np.full(n, 0.5)), "rock_type": np.full(n, rocks.index(rock), dtype=np.int16),
            "slope": np.zeros(n), "surface_age": full(age), "erosion_rate": full(erosion), "permafrost": full(frozen),
            "snow_ice_cover": monthly(h, full(ice))}


def test_soil_at_balance_with_erosion_is_h0_ln_p0_over_e(h):
    """Usual warmth and water (the climate factor is one at 2.5 C mean and rain above demand): with erosion at P0 / e^2 the
    soil stands at 2 h0, where production meets erosion (Heimsath et al. 1997)."""
    d = const(h, "Soils")["depth"]
    erosion_mm = d["fastest_production_m_per_year"] / np.e ** 2 * 1000.0
    out = h.run("Soils", reads=soil_inputs(h, erosion=erosion_mm)).fields
    assert np.allclose(out["soil_depth"], 2 * d["decline_depth_m"], rtol=1e-4)


def test_ground_worn_faster_than_soil_forms_is_bare_rock(h):
    d = const(h, "Soils")["depth"]
    out = h.run("Soils", reads=soil_inputs(h, erosion=10 * d["fastest_production_m_per_year"] * 1000.0 * d["most_production_share"])).fields
    orders = h.registry.fields["soil_order"].categories
    assert (out["soil_depth"] == 0).all() and (out["soil_order"] == orders.index("bare_rock")).all()


def test_young_ground_has_had_only_its_time_to_weather(h):
    d = const(h, "Soils")["depth"]
    out = h.run("Soils", reads=soil_inputs(h, age=0.0)).fields["soil_depth"]
    want = d["decline_depth_m"] * np.log1p(d["fastest_production_m_per_year"] * d["least_time_my"] * 1e6 / d["decline_depth_m"])
    assert np.allclose(out, want, rtol=1e-4)


def test_frozen_ground_is_gelisol_and_lasting_ice_is_ice(h):
    orders = h.registry.fields["soil_order"].categories
    n = h.mesh.n
    frozen = np.where(np.arange(n) % 2 == 0, 1.0, 0.0)
    out = h.run("Soils", reads=soil_inputs(h, mean_c=-12.0, frozen=frozen, ice=np.where(np.arange(n) % 4 == 1, 1.0, 0.0))).fields["soil_order"]
    assert (out[frozen == 1] == orders.index("gelisols")).all()
    assert (out[np.arange(n) % 4 == 1] == orders.index("ice")).all()


# ------------------------------------------------------------------------------------------- Biomes: BIOME1 (step 7)
def biome_of(h, mean_c, swing_c, rain_mm, demand_mm=80.0, moisture=0.9):
    n = h.mesh.n
    t = mean_c + swing_c * np.cos(np.arange(h.months) * 2 * np.pi / h.months)[:, None] * np.ones(n)
    reads = {"surface_temperature": t + ZERO_CELSIUS_IN_K, "precipitation": monthly(h, np.full(n, rain_mm)),
             "potential_evapotranspiration": monthly(h, np.full(n, demand_mm)), "soil_moisture": monthly(h, np.full(n, moisture)),
             "soil_water_capacity": np.full(n, 150.0), "soil_fertility": np.full(n, 0.6), "permafrost": np.zeros(n),
             "snow_ice_cover": monthly(h, np.zeros(n)), "ocean_mask": np.zeros(n, dtype=bool)}
    names = h.registry.fields["biome"].categories
    out = h.run("Biomes", reads=reads).fields["biome"]
    return {names[int(k)] for k in np.unique(out)}


@pytest.mark.parametrize("climate,expected", [
    (dict(mean_c=27.0, swing_c=1.0, rain_mm=250.0), "tropical_rain_forest"),     # hot, wet in every month
    (dict(mean_c=27.0, swing_c=3.0, rain_mm=1.0, moisture=0.0, demand_mm=180.0), "hot_desert"),
    (dict(mean_c=-2.0, swing_c=18.0, rain_mm=50.0), "taiga"),                   # long cold winters, short mild summers
    (dict(mean_c=-25.0, swing_c=10.0, rain_mm=10.0), "polar_desert"),           # no month above freezing
], ids=["rain forest", "hot desert", "taiga", "polar desert"])
def test_the_dominant_plant_types_name_the_biome_of_prentice_et_al(h, climate, expected):
    assert biome_of(h, **climate) == {expected}
