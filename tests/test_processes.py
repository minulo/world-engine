"""Known answers: each process of the slice alone, on an input built so that the result is known (design, Layer 9)."""
import numpy as np
import pytest

from worldengine.library import operators as op
from worldengine.library.flood import barriers, pour
from worldengine.library.orbit import daily_insolation, monthly_insolation
from worldengine.mesh import get_mesh
from worldengine.processes.biomes_whittaker_koppen import koppen
from worldengine.testing import Harness

R = 6.371e6
CIRCULAR = {"orbit": {"eccentricity": 0.0, "perihelion_solar_longitude_deg": 0.0, "northward_equinox_year_fraction": 0.0}}


@pytest.fixture(scope="module")
def h():
    return Harness(level=4)


def geometry(h):
    return h.run("PlanetGeometry").fields


# ------------------------------------------------------------------------------------------ PlanetGeometry
def test_geometry_cell_areas_add_up_to_the_sphere(h):
    g = geometry(h)
    assert abs(g["cell_area"].sum() / (4 * np.pi * R * R) - 1) < 1e-12
    assert np.allclose(g["coriolis_parameter"], 2 * (2 * np.pi / 86164.1) * np.sin(np.deg2rad(g["latitude"])))


# ------------------------------------------------------------------------------------------ Tectonics
def two_plates(h, speed_north, speed_south):
    """A northern and a southern plate, each turning about the x axis, so that along the equator near longitude 90
    they move toward the poles (apart) or toward each other."""
    m = h.mesh
    n = m.n
    north = m.xyz[:, 2] > 0
    plate = np.where(north, 0, 1).astype(np.int32)
    zero = np.zeros(n, dtype=np.float32)
    none = np.full(n, -1, dtype=np.int32)
    points = {"plate": plate, "x": m.xyz[:, 0], "y": m.xyz[:, 1], "z": m.xyz[:, 2], "crust_type": np.zeros(n, dtype=np.int16),
              "thickness_m": np.full(n, 7000.0), "ocean_age_my": np.full(n, np.nan), "orogeny_age_my": np.full(n, np.nan),
              "thickened_by_plates_m": zero, "removed_by_erosion_m": zero, "source_a": none, "source_b": none, "source_c": none,
              "weight_a": zero, "weight_b": zero, "weight_c": zero}
    plates = {"plate": [0, 1], "axis_x": [1.0, 1.0], "axis_y": [0.0, 0.0], "axis_z": [0.0, 0.0],
              "angular_speed_rad_per_my": [speed_north, speed_south], "area_m2": [0.0, 0.0], "continental_share": [0.0, 0.0],
              "carries_continent": [False, False], "centre_x": [0.0, 0.0], "centre_y": [0.0, 0.0], "centre_z": [1.0, -1.0]}
    events = {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []}
    return points, plates, events


def test_two_plates_moving_apart_make_young_floor_along_the_line_where_they_part(h):
    g = geometry(h)
    points, plates, events = two_plates(h, 0.005, -0.005)            # at longitude 90 the north plate moves north, the south plate south
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]},
                lagged_tables={"crust_points": points, "plates": plates, "tectonic_events": events})
    f, m = out.fields, h.mesh
    kinds = h.registry.fields["boundary_kind"].categories
    near = (np.abs(m.lat) < 2.6) & (np.abs(m.lon - 90) < 30)
    far = (np.abs(m.lat) > 40) & (np.abs(m.lon - 90) < 30)
    assert set(f["boundary_kind"][near]) == {kinds.index("ridge")}
    assert np.all(f["convergence_rate"][near] < 0)
    assert f["ocean_crust_age"][near].max() < f["ocean_crust_age"][far].min()        # youngest along the ridge
    assert f["ocean_crust_age"][near].min() < 5.0
    assert np.all(f["volcanism"][near] > 0.3)
    spreading = 4
    assert spreading in set(out.tables["tectonic_events"]["kind"])


def test_continents_closing_thicken_the_crust_on_both_sides(h):
    g = geometry(h)
    points, plates, events = two_plates(h, -0.005, 0.005)            # now the plates close along the equator near longitude 90
    points["crust_type"] = np.ones(h.mesh.n, dtype=np.int16)
    points["thickness_m"] = np.full(h.mesh.n, 35000.0)
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]},
                lagged_tables={"crust_points": points, "plates": plates, "tectonic_events": events})
    f, m = out.fields, h.mesh
    kinds = h.registry.fields["boundary_kind"].categories
    for side in (1, -1):
        belt = (side * m.lat > 0) & (side * m.lat < 4) & (np.abs(m.lon - 90) < 20)
        assert set(f["boundary_kind"][belt]) == {kinds.index("collision")}
        assert f["crust_thickness"][belt].min() > 45000.0
    away = (np.abs(m.lat) > 30) & (np.abs(m.lon - 90) < 20)
    assert np.allclose(f["crust_thickness"][away], 35000.0, atol=1.0)
    d = out.drivers["crust_thickness"]
    total = d["normal_thickness"].astype(float) + d["seeded_variation"] + d["thickened_by_plates"]
    assert np.allclose(total, f["crust_thickness"], atol=0.01)


def test_seeded_plates_are_the_same_at_every_mesh_level_and_differ_with_the_seed():
    def seeded(level, seed):
        hh = Harness(level=level, seed=seed)
        g = geometry(hh)
        out = hh.run("Tectonics", reads={"cell_area": g["cell_area"]}, start=True)
        return hh.mesh, out
    m3, a = seeded(3, 5)
    m4, b = seeded(4, 5)
    _, c = seeded(4, 6)
    for col in ("axis_x", "axis_y", "axis_z", "angular_speed_rad_per_my", "centre_x"):
        assert np.array_equal(a.tables["plates"][col], b.tables["plates"][col])           # drawn in sphere coordinates
    assert np.mean(a.fields["plate_id"] == b.fields["plate_id"][:m3.n]) > 0.99            # the coarse cells are the first fine cells
    assert not np.array_equal(b.tables["plates"]["axis_x"], c.tables["plates"]["axis_x"])
    share = (b.fields["crust_type"] * m4.area).sum() / m4.area.sum()
    assert abs(share - 0.40) < 0.01


# ------------------------------------------------------------------------------------------ Isostasy
def test_ocean_depth_follows_the_age_of_the_floor(h):
    n = h.mesh.n
    age = np.linspace(0.0, 180.0, n)
    out = h.run("Isostasy", reads={"crust_type": np.zeros(n, dtype=np.int16), "crust_thickness": np.full(n, 7000.0),
                                   "ocean_crust_age": age}, constants={"ocean_floor": {"reference_offset_m": 0.0}})
    depth = -out.fields["elevation"].astype(np.float64)
    assert abs(depth[0] - 2500.0) < 0.01
    young = age <= 70.0
    assert np.allclose(depth[young], 2500.0 + 350.0 * np.sqrt(age[young]), atol=0.5)
    assert np.all(np.diff(depth) >= -1e-3) and depth[-1] < 6400.0 and depth[-1] > 5400.0


def test_thicker_crust_stands_higher_by_about_fifteen_percent_of_the_added_thickness(h):
    n = h.mesh.n
    land = np.ones(n, dtype=np.int16)
    def height(thickness):
        return h.run("Isostasy", reads={"crust_type": land, "crust_thickness": np.full(n, thickness),
                                        "ocean_crust_age": np.full(n, np.nan)}).fields["elevation"]
    assert np.allclose(height(35000.0), 0.0, atol=0.01)
    assert np.allclose(height(45000.0), 10000.0 * (1 - 2800.0 / 3300.0), atol=0.5)


# ------------------------------------------------------------------------------------------ SeaLevel
def basin(mesh, radius_deg=30.0, floor=-1000.0, wall=1000.0):
    inside = np.rad2deg(np.arccos(np.clip(mesh.xyz[:, 0], -1, 1))) < radius_deg
    return inside, np.where(inside, floor, wall)


def test_water_in_a_flat_basin_stands_at_volume_over_floor_area(h):
    g = geometry(h)
    inside, elevation = basin(h.mesh)
    floor_area = g["cell_area"][inside].sum()
    hh = Harness(level=4, planet={"surface_water_volume_m3": float(floor_area * 400.0)})
    out = hh.run("SeaLevel", reads={"elevation": elevation, "cell_area": g["cell_area"]})
    f = out.fields
    assert np.array_equal(f["ocean_mask"], inside)
    assert np.allclose(f["sea_depth"][inside], 400.0, atol=1e-2)
    assert abs(out.tables["seas"]["surface_m"][0] + 600.0) < 1e-6 and len(out.tables["seas"]["surface_m"]) == 1
    assert np.allclose(f["height_above_sea"][~inside], 1600.0, atol=1e-2) and np.allclose(f["height_above_sea"][inside], 0.0, atol=1e-2)
    assert abs((f["sea_depth"] * g["cell_area"]).sum() / (floor_area * 400.0) - 1) < 1e-6      # the sea holds the planet's water
    coast = f["coast_distance"]
    assert coast[inside].max() < np.deg2rad(31.0) * R and coast.min() > 0


def test_water_spills_over_a_rim_into_the_next_hollow_and_the_two_merge():
    m = get_mesh(4)
    area = m.area * R * R
    lon, lat = m.lon, m.lat
    a = (np.abs(lat) < 20) & (np.abs(lon + 40) < 25)                 # a deep hollow
    b = (np.abs(lat) < 20) & (np.abs(lon - 40) < 25)                 # a shallower hollow
    ridge = (np.abs(lat) < 20) & (np.abs(lon) <= 15)                 # the rim between them
    height = np.full(m.n, 3000.0)
    height[a], height[b], height[ridge] = -2000.0, -1000.0, 0.0
    cap_a = area[a].sum() * 2000.0                                   # what the deep hollow holds below the rim
    body, level = pour(height, area, m.nbr, m.nbr_count, 0.5 * cap_a)
    assert set(body[a]) == {body[np.argmin(height)]} and np.all(body[b] == -1)
    assert abs(level[body[a][0]] + 1000.0) < 1e-6
    body, level = pour(height, area, m.nbr, m.nbr_count, cap_a + 0.5 * area[b].sum() * 1000.0)
    wet_b = body[b]
    assert np.all(wet_b >= 0) and abs(level[wet_b[0]] + 500.0) < 1e-6          # the deep one is full, the other half full
    assert abs(level[body[a][0]] - 0.0) < 1e-6
    body, level = pour(height, area, m.nbr, m.nbr_count, cap_a + area[b].sum() * 1000.0 + (area[a | b | ridge].sum()) * 100.0)
    assert len(set(body[a | b | ridge])) == 1 and abs(level[body[a][0]] - 100.0) < 1e-6      # one sea above the rim
    depth = np.where(body >= 0, level[np.maximum(body, 0)] - height, 0.0)
    assert abs((depth * area).sum() / (cap_a + area[b].sum() * 1000.0 + area[a | b | ridge].sum() * 100.0) - 1) < 1e-9


def test_low_ground_behind_a_barrier_stays_dry_and_the_barrier_is_named(h):
    g = geometry(h)
    m = h.mesh
    height = np.full(m.n, 500.0)
    sea = np.abs(m.lon) > 90
    hollow = (np.abs(m.lat) < 10) & (np.abs(m.lon) < 10)
    height[sea], height[hollow] = -3000.0, -200.0
    hh = Harness(level=4, planet={"surface_water_volume_m3": float(g["cell_area"][sea].sum() * 2900.0)})
    out = hh.run("SeaLevel", reads={"elevation": height, "cell_area": g["cell_area"]})
    assert not out.fields["ocean_mask"][hollow].any()
    assert np.all(out.fields["height_above_sea"][hollow] < 0)
    reason, barrier = out.drivers["ocean_mask"]["reason"], out.drivers["ocean_mask"]["barrier_cell"]
    assert set(reason[hollow]) == {3} and np.all(height[barrier[hollow]] == 500.0)
    reach, at = barriers(height, m.nbr, m.nbr_count, sea, -100.0)
    assert np.all(reach[hollow] == 500.0)


def test_a_planet_without_water_has_no_sea(h):
    g = geometry(h)
    hh = Harness(level=4, planet={"surface_water_volume_m3": 0.0})
    elevation = 1000.0 * h.mesh.xyz[:, 2]
    out = hh.run("SeaLevel", reads={"elevation": elevation, "cell_area": g["cell_area"]})
    assert not out.fields["ocean_mask"].any() and len(out.tables["seas"]["surface_m"]) == 0
    assert np.allclose(out.fields["height_above_sea"], elevation, atol=1e-3)


# ------------------------------------------------------------------------------------------ Insolation
def test_equator_at_an_equinox_gets_the_star_output_over_pi():
    assert abs(daily_insolation(0.0, 0.0, np.deg2rad(23.44), 1361.0) - 1361.0 / np.pi) < 1e-9


def test_polar_day_and_polar_night_at_the_june_solstice():
    tilt = np.deg2rad(23.44)
    lat = np.deg2rad(np.array([-90.0, -70.0, -66.0, 66.0, 70.0, 90.0]))
    q = daily_insolation(lat, np.pi / 2, tilt, 1361.0)
    assert q[0] == 0.0 and q[1] == 0.0 and q[2] > 0.0                 # the sun never rises south of the Antarctic Circle
    assert abs(q[5] - 1361.0 * np.sin(tilt)) < 1e-9                   # at the pole the sun circles at a height equal to the tilt
    assert q[4] > daily_insolation(0.0, np.pi / 2, tilt, 1361.0)      # more sunlight in a day than the equator gets


def test_yearly_sunlight_cold_poles_below_about_54_degrees_of_tilt():
    lat = np.array([0.0, 90.0])
    def ratio(tilt):
        q = monthly_insolation(lat, 12, 32, tilt, 1361.0, 0.0, 0.0, 0.0).mean(axis=0)
        return q[1] / q[0]
    assert abs(ratio(23.44) - 0.415) < 0.003                          # the pole gets 41 % of the equator's yearly sunlight
    assert ratio(50.0) < 1.0 < ratio(58.0)                            # the two are equal near 54 degrees
    lats = np.linspace(-90, 90, 181)
    yearly = monthly_insolation(lats, 12, 32, 23.44, 1361.0, 0.0, 0.0, 0.0).mean(axis=0)
    assert np.argmin(yearly) in (0, 180) and abs(yearly[0] - yearly[-1]) < 1e-6


def test_insolation_process_matches_the_formula_and_its_global_mean():
    hh = Harness(level=4, planet=CIRCULAR)
    g = geometry(hh)
    q = hh.run("Insolation", reads={"latitude": g["latitude"]}, constants={"samples_per_month": 16}).fields["insolation"]
    mean = (q.mean(axis=0) * hh.mesh.area).sum() / hh.mesh.area.sum()
    assert abs(mean / (1361.0 / 4) - 1) < 2e-3                         # a sphere intercepts a quarter of the star output
    north = hh.mesh.lat > 60                                           # this planet's year starts at the northward equinox,
    assert q[2][north].mean() > 4 * q[8][north].mean()                 # so month 3 is midsummer in the north and month 9 midwinter


# ------------------------------------------------------------------------------------------ Albedo
def test_albedo_returns_the_table_value_of_each_surface_type(h):
    g = geometry(h)
    sea = h.mesh.xyz[:, 0] > 0
    warm = np.full((12, h.mesh.n), 300.0)
    out = h.run("Albedo", reads={"ocean_mask": sea, "latitude": g["latitude"]}, lagged={"surface_temperature": warm},
                constants={"cloud_share": 0.0, "low_sun_term": 0.0})
    a = out.fields["albedo"]
    assert np.allclose(a[:, sea], 0.07) and np.allclose(a[:, ~sea], 0.20)
    cold = h.run("Albedo", reads={"ocean_mask": sea, "latitude": g["latitude"]}, lagged={"surface_temperature": warm - 100.0},
                 constants={"cloud_share": 0.0, "low_sun_term": 0.0}).fields["albedo"]
    assert np.allclose(cold, 0.658)


def test_albedo_with_cloud_and_ice_gives_the_published_values_and_its_drivers_add_up(h):
    g = geometry(h)
    sea = h.mesh.xyz[:, 0] > 0
    t = np.where(h.mesh.lat > 60, 250.0, 300.0) * np.ones((12, 1))
    out = h.run("Albedo", reads={"ocean_mask": sea, "latitude": g["latitude"]}, lagged={"surface_temperature": t})
    a = out.fields["albedo"].astype(np.float64)
    assert np.allclose(a[:, h.mesh.lat > 60], 0.62, atol=2e-3)         # ice-covered cells reflect the 0.62 of North et al. 1981
    free = h.mesh.lat <= 60
    assert a[0, free & (np.abs(h.mesh.lat) < 10)].mean() < a[0, free & (h.mesh.lat > 50)].mean()   # more reflection at low sun
    total = sum(v.astype(np.float64) for v in out.drivers["albedo"].values())
    assert np.allclose(total, a, atol=1e-6)
    first_guess = h.run("Albedo", reads={"ocean_mask": sea, "latitude": g["latitude"]})
    assert np.all(first_guess.drivers["albedo"]["from_snow_and_ice"] == 0.0)     # the first guess of fields.yaml is a planet without ice


# ------------------------------------------------------------------------------------------ EnergyBalance
def energy_inputs(h, sea=None, height=None):
    g = geometry(h)
    n = h.mesh.n
    q = monthly_insolation(g["latitude"], 12, 8, 23.44, 1361.0, 0.0, 0.0, 0.0)
    return {"insolation": q, "albedo": np.full((12, n), 0.3), "ocean_mask": np.zeros(n, dtype=bool) if sea is None else sea,
            "height_above_sea": np.zeros(n) if height is None else height, "cell_area": g["cell_area"]}


def test_without_spreading_the_yearly_mean_is_absorbed_sunlight_minus_a_over_b(h):
    reads = energy_inputs(h)
    t = h.run("EnergyBalance", reads=reads, constants={"spreading_constant_w_m2_k": 0.0}).fields["surface_temperature"]
    expected = 273.15 + (0.7 * reads["insolation"].mean(axis=0) - 203.3) / 2.09
    assert np.allclose(t.astype(np.float64).mean(axis=0), expected, atol=2e-3)


def test_spreading_warms_the_poles_cools_the_equator_and_keeps_the_mean(h):
    reads = energy_inputs(h)
    bare = h.run("EnergyBalance", reads=reads, constants={"spreading_constant_w_m2_k": 0.0}).fields["surface_temperature"].mean(axis=0)
    out = h.run("EnergyBalance", reads=reads)
    t = out.fields["surface_temperature"].astype(np.float64).mean(axis=0)
    w = h.mesh.area / h.mesh.area.sum()
    assert abs((t * w).sum() - (bare * w).sum()) < 1e-3                # spreading moves heat; it makes none
    pole, equator = h.mesh.lat > 80, np.abs(h.mesh.lat) < 5
    assert t[pole].mean() > bare[pole].mean() + 20 and t[equator].mean() < bare[equator].mean() - 5
    assert t[pole].mean() < t[equator].mean() - 20                    # colder toward the poles
    total = sum(v.astype(np.float64) for v in out.drivers["surface_temperature"].values())
    assert np.allclose(total, out.fields["surface_temperature"], atol=1e-3)


def test_land_swings_more_than_sea_and_height_cools(h):
    m = h.mesh
    sea = m.lon < 0                                                   # half the planet is sea
    height = np.where((~sea) & (np.abs(m.lat - 20) < 10), 3000.0, 0.0)
    t = h.run("EnergyBalance", reads=energy_inputs(h, sea, height)).fields["surface_temperature"].astype(np.float64)
    swing = t.max(axis=0) - t.min(axis=0)
    band = (m.lat > 40) & (m.lat < 60)
    inland, offshore = band & (np.abs(m.lon - 90) < 30), band & (np.abs(m.lon + 90) < 30)
    assert swing[inland].mean() > 3 * swing[offshore].mean()          # a larger summer-to-winter swing inside continents
    flat = h.run("EnergyBalance", reads=energy_inputs(h, sea)).fields["surface_temperature"].astype(np.float64)
    assert np.allclose((flat - t)[:, height > 0], 6.5 * 3.0, atol=1e-3)   # 6.5 K per km


def test_a_member_of_the_heat_group_shifts_the_mean_by_its_size_over_b(h):
    reads = energy_inputs(h)
    n = h.mesh.n
    plain = h.run("EnergyBalance", reads=reads).fields["surface_temperature"].astype(np.float64)
    pushed = h.run("EnergyBalance", reads=reads, groups={"surface_heat_flux": {"push:test": np.full((12, n), -20.9)}})
    assert np.allclose(pushed.fields["surface_temperature"] - plain, -10.0, atol=2e-3)
    assert np.allclose(pushed.drivers["surface_temperature"]["other_heat"], -10.0, atol=1e-4)


# ------------------------------------------------------------------------------------------ Circulation
def mirrored_temperature(mesh):
    """A sea-level temperature that depends on latitude and season, the south half a year behind the north."""
    lat = np.deg2rad(mesh.lat)
    months = np.arange(12)[:, None]
    season = np.cos(2 * np.pi * (months - 6.5) / 12)
    return 300.0 - 45.0 * np.sin(lat)[None, :] ** 2 + 12.0 * season * np.sin(lat)[None, :]


def run_circulation(h, temperature, **kw):
    g = geometry(h)
    n = h.mesh.n
    return h.run("Circulation", reads={"surface_temperature": temperature, "coriolis_parameter": g["coriolis_parameter"],
                                       "latitude": g["latitude"], "height_above_sea": np.zeros(n), "cell_area": g["cell_area"]}, **kw)


def test_on_an_all_ocean_planet_each_month_in_the_north_mirrors_the_south_half_a_year_later(h):
    out = run_circulation(h, mirrored_temperature(h.mesh))
    p = out.fields["sea_level_pressure"].astype(np.float64)
    for month in (0, 3, 6):
        lat, north = op.zonal_mean(h.mesh, p[month], 10.0)
        _, south = op.zonal_mean(h.mesh, p[(month + 6) % 12], 10.0)
        assert np.allclose(north, south[::-1], atol=5.0)              # pascals
    s = out.fields["subsidence"].astype(np.float64)
    _, sn = op.zonal_mean(h.mesh, s[0], 10.0)
    _, ss = op.zonal_mean(h.mesh, s[6], 10.0)
    assert np.allclose(sn, ss[::-1], atol=0.05)


def test_trade_winds_westerlies_and_high_pressure_near_thirty_degrees(h):
    out = run_circulation(h, mirrored_temperature(h.mesh))
    f, m = out.fields, h.mesh
    east, north = op.to_east_north(m, f["wind"].astype(np.float64).mean(axis=0))
    lat, u = op.zonal_mean(m, east, 10.0)
    _, v = op.zonal_mean(m, north, 10.0)
    band = lambda a, b: (lat > a) & (lat < b)
    assert np.all(u[band(5, 25)] < -1.0) and np.all(u[band(-25, -5)] < -1.0)          # trade winds blow from the east
    assert np.all(u[band(40, 55)] > 1.0) and np.all(u[band(-55, -40)] > 1.0)          # westerlies in mid-latitudes
    assert np.all(v[band(10, 25)] < 0) and np.all(v[band(-25, -10)] > 0)              # and the trades blow toward the equator
    lat5, p = op.zonal_mean(m, f["sea_level_pressure"].astype(np.float64).mean(axis=0), 5.0, fill=True)
    north_high = lat5[lat5 > 0][np.argmax(p[lat5 > 0])]
    assert 22.0 <= north_high <= 38.0                                                 # high pressure near 30 degrees
    s = f["subsidence"].astype(np.float64)
    assert np.all(np.abs((s * m.area).sum(axis=1) / m.area.sum()) < 1e-6)             # as much air sinks as rises
    _, sz = op.zonal_mean(m, s.mean(axis=0), 10.0)
    assert sz[band(-10, 10)].min() < -1.0 and sz[band(20, 30)].min() > 0.5            # rising near the equator, sinking near 25
    d = out.drivers
    assert np.allclose(sum(v.astype(np.float64) for v in d["sea_level_pressure"].values()), f["sea_level_pressure"], atol=0.05)
    assert np.allclose(d["wind"]["from_belts"].astype(np.float64) + d["wind"]["from_surface_temperature"], f["wind"], atol=1e-4)


def test_a_warm_patch_lowers_the_pressure_and_storm_growth_follows_the_temperature_contrast(h):
    m = h.mesh
    base = mirrored_temperature(m)
    patch = np.exp(-(np.rad2deg(np.arccos(np.clip(m.xyz @ np.array([np.cos(np.deg2rad(45)), 0, np.sin(np.deg2rad(45))]), -1, 1))) / 12.0) ** 2)
    plain = run_circulation(h, base).fields
    warm = run_circulation(h, base + 10.0 * patch).fields
    centre = patch > 0.8
    assert (warm["sea_level_pressure"][0] - plain["sea_level_pressure"][0])[centre].mean() < -150.0
    flat = run_circulation(h, np.full((12, m.n), 288.0)).fields
    assert flat["baroclinicity"].max() < 1e-6
    assert plain["baroclinicity"].max() > 0.3
    assert np.abs(plain["baroclinicity"][:, np.abs(m.lat) < 3]).max() < 0.2 * plain["baroclinicity"].max()   # none at the equator


# ------------------------------------------------------------------------------------------ Moisture
def test_one_ridge_across_a_steady_wind_wet_on_the_side_facing_the_wind_dry_on_the_sheltered_side(h):
    g = geometry(h)
    m = h.mesh
    n = m.n
    ridge = 2500.0 * np.exp(-(m.lon / 6.0) ** 2) * (np.abs(m.lat) < 35)
    land = ridge > 50.0
    wind = np.broadcast_to(6.0 * np.cos(np.deg2rad(m.lat))[:, None] * m.east, (12, n, 3))        # steady, from the west
    temperature = np.broadcast_to(292.0 - 6.5 * ridge / 1000.0, (12, n))
    out = h.run("Moisture", reads={"wind": wind, "subsidence": np.zeros((12, n)), "surface_temperature": temperature,
                                   "height_above_sea": ridge, "ocean_mask": ~land, "cell_area": g["cell_area"]})
    rain = out.fields["precipitation"].astype(np.float64).mean(axis=0)
    band = np.abs(m.lat) < 25
    facing = band & (m.lon > -9) & (m.lon < -2)
    sheltered = band & (m.lon > 2) & (m.lon < 9)
    upwind_sea = band & (m.lon > -60) & (m.lon < -30)
    assert rain[facing].mean() > 2 * rain[sheltered].mean()
    assert rain[facing].mean() > 1.1 * rain[upwind_sea].mean() and rain[sheltered].mean() < 0.5 * rain[upwind_sea].mean()
    d = out.drivers["precipitation"]
    assert d["from_rising_ground"][0][facing].mean() > 0 and np.all(d["from_rising_ground"][0][sheltered & (m.lon > 4)] == 0)
    total = d["from_moist_air"].astype(np.float64) + d["from_rising_ground"] + d["stopped_by_sinking_air"]
    assert np.allclose(total, out.fields["precipitation"], rtol=1e-4, atol=1e-3)
    assert not out.notices
    # over the globe, the water that evaporates equals the water that falls
    e = (out.fields["ocean_evaporation"].astype(np.float64) * g["cell_area"]).sum()
    p = (out.fields["precipitation"].astype(np.float64) * g["cell_area"]).sum()
    assert abs(e / p - 1) < 2e-3
    came = d["vapour_came_from"][0]
    assert np.all(m.lon[came[facing]] < m.lon[facing] + 1e-9)          # on the windward side the vapour came from the west


def test_sinking_air_brings_less_rain_and_vapour_from_land_adds_rain_downwind(h):
    g = geometry(h)
    m = h.mesh
    n = m.n
    reads = {"wind": np.broadcast_to(5.0 * np.cos(np.deg2rad(m.lat))[:, None] * m.east, (12, n, 3)),
             "subsidence": np.zeros((12, n)), "surface_temperature": np.full((12, n), 295.0), "height_above_sea": np.zeros(n),
             "ocean_mask": np.ones(n, dtype=bool), "cell_area": g["cell_area"]}
    plain = h.run("Moisture", reads=reads).fields["precipitation"].astype(np.float64)
    sinking = np.where(np.abs(m.lat) < 20, 3.0, 0.0) * np.ones((12, 1))
    less = h.run("Moisture", reads={**reads, "subsidence": sinking})
    tropics = np.abs(m.lat) < 15
    assert less.fields["precipitation"][0][tropics].mean() < 0.75 * plain[0][tropics].mean()
    assert less.drivers["precipitation"]["stopped_by_sinking_air"][0][tropics].max() < 0
    source = np.where((np.abs(m.lat) < 10) & (np.abs(m.lon) < 10), 200.0, 0.0) * np.ones((12, 1))
    more = h.run("Moisture", reads=reads, groups={"moisture_source": {"push:test": source}}).fields["precipitation"].astype(np.float64)
    downwind = (np.abs(m.lat) < 10) & (m.lon > 10) & (m.lon < 30)
    upwind = (np.abs(m.lat) < 10) & (m.lon < -15) & (m.lon > -35)
    assert (more - plain)[0][downwind].mean() > 5 * abs((more - plain)[0][upwind].mean())
    assert (more - plain)[0][downwind].mean() > 1.0


# ------------------------------------------------------------------------------------------ Biomes
def biome_run(h, temperature_c, rain_mm, sea=None):
    n = h.mesh.n
    t = np.broadcast_to(np.asarray(temperature_c, dtype=np.float64)[:, None] + 273.15, (12, n))
    p = np.broadcast_to(np.asarray(rain_mm, dtype=np.float64)[:, None], (12, n))
    out = h.run("Biomes", reads={"surface_temperature": t, "precipitation": p,
                                 "ocean_mask": np.zeros(n, dtype=bool) if sea is None else sea})
    names_b, names_c = h.registry.fields["biome"].categories, h.registry.fields["climate_class"].categories
    return names_b[out.fields["biome"][0]], names_c[out.fields["climate_class"][0]], out


def test_warm_and_wet_all_year_is_tropical_rainforest(h):
    biome, klass, out = biome_run(h, [26.0] * 12, [300.0] * 12)
    assert biome == "tropical_rainforest" and klass == "Af"
    assert np.allclose(out.fields["vegetation_cover"], 0.95)


def test_a_year_whose_warmest_month_is_below_freezing_is_ice_with_no_plant_cover(h):
    biome, klass, out = biome_run(h, [-30, -28, -25, -18, -10, -4, -1, -3, -9, -17, -24, -29], [10.0] * 12)
    assert biome == "ice" and klass == "EF"
    assert np.all(out.fields["vegetation_cover"] == 0.0)
    assert set(out.drivers["biome"]["rule"]) == {1} and set(out.drivers["biome"]["limit"]) == {1}


def test_sea_that_stays_frozen_all_year_is_ice_and_open_sea_is_ocean(h):
    n = h.mesh.n
    sea = np.ones(n, dtype=bool)
    assert biome_run(h, [-20.0] * 12, [10.0] * 12, sea)[0] == "ice"
    assert biome_run(h, [-20, -20, -15, -8, -3, 0, 2, 1, -2, -8, -14, -18], [10.0] * 12, sea)[0] == "ocean"   # it thaws in summer
    assert biome_run(h, [-20.0] * 12, [10.0] * 12, sea)[1] == "ocean"


SEASONS = lambda mean, swing: [mean - swing * np.cos(2 * np.pi * (m - 0.5) / 12) for m in range(12)]          # coldest in January


@pytest.mark.parametrize("temps,rain,expected_class,expected_biome", [
    (SEASONS(27, 6), [1.0] * 12, "BWh", "subtropical_desert"),
    (SEASONS(8, 14), [20.0] * 12, "BSk", "temperate_grassland_desert"),
    (SEASONS(16, 8), [100, 90, 70, 40, 20, 5, 2, 5, 25, 60, 90, 110], "Csa", None),          # dry summer, hot summer
    (SEASONS(10, 6), [90.0] * 12, "Cfb", "temperate_seasonal_forest"),
    (SEASONS(-3, 16), [50.0] * 12, "Dfc", "boreal_forest"),
    (SEASONS(-9, 14), [25.0] * 12, "ET", "tundra"),
    (SEASONS(26, 1), [300, 250, 200, 100, 30, 5, 5, 10, 60, 150, 250, 300], "Aw", None),     # a dry season in the tropics
])
def test_climate_classes_follow_the_published_rules(h, temps, rain, expected_class, expected_biome):
    biome, klass, _ = biome_run(h, temps, rain)
    assert klass == expected_class
    if expected_biome:
        assert biome == expected_biome


def test_summer_is_the_warmer_half_year_in_either_hemisphere(h):
    k = h.params["models"]["slots"]["Biomes"]["constants"]["koppen"]
    north = np.array(SEASONS(16, 8))[:, None]
    rain = np.array([100, 90, 70, 40, 20, 5, 2, 5, 25, 60, 90, 110], dtype=float)[:, None]
    south, rain_south = np.roll(north, 6, axis=0), np.roll(rain, 6, axis=0)
    assert koppen(north, rain, k)[0][0] == koppen(south, rain_south, k)[0][0] == "Csa"


# ------------------------------------------------------------------------------------------ the contract, in the harness
def test_harness_refuses_to_guess_a_missing_input(h):
    from worldengine.engine import EngineError
    with pytest.raises(EngineError):
        h.run("Isostasy", reads={"crust_type": np.zeros(h.mesh.n, dtype=np.int16)})      # the other reads are missing
