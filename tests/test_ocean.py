"""Known answers of OceanCurrents (design, Layer 9; build step 4), on inputs built so that the result is known."""
import numpy as np
import pytest

from conftest import DATA
from worldengine.testing import Harness


@pytest.fixture(scope="module")
def h():
    return Harness(level=5, data_dir=DATA)


def basin(h, lat_range=(15.0, 55.0), lon_range=(-60.0, 0.0)):
    """A closed sea between two meridians and two parallels, land everywhere else."""
    m = h.mesh
    return (m.lat > lat_range[0]) & (m.lat < lat_range[1]) & (m.lon > lon_range[0]) & (m.lon < lon_range[1])


def zonal_wind(h, lat_range, speed):
    """Easterlies in the south of the basin and westerlies in the north, the same in every month: u = -speed cos(pi s)
    with s from 0 to 1 across the basin. Its curl is negative throughout, as over a subtropical ocean."""
    m = h.mesh
    s = np.clip((m.lat - lat_range[0]) / (lat_range[1] - lat_range[0]), 0, 1)
    east = -speed * np.cos(np.pi * s)
    wind = east[:, None] * m.east
    return np.broadcast_to(wind, (h.months,) + wind.shape).copy()


def inputs(h, sea, wind, temperature=None):
    g = h.run("PlanetGeometry").fields
    t = np.full((h.months, h.mesh.n), 288.0) if temperature is None else temperature
    return {"wind": wind, "ocean_mask": sea, "coriolis_parameter": g["coriolis_parameter"], "surface_temperature": t,
            "cell_area": g["cell_area"]}


def test_in_a_closed_basin_under_a_steady_wind_the_current_is_strongest_on_the_western_side(h):
    """The western-side test of the design (Layer 9, build step 4): friction closes the loop with a narrow, fast current
    on the western side (Stommel 1948). Measured: the mean speed in the western fifth of the basin against the
    eastern fifth, along its middle latitudes; the condition, written with the test, asks at least twice."""
    lat_range, lon_range = (15.0, 55.0), (-60.0, 0.0)
    sea = basin(h, lat_range, lon_range)
    out = h.run("OceanCurrents", reads=inputs(h, sea, zonal_wind(h, lat_range, 8.0)))
    loops = out.drivers["ocean_current"]["loops"]
    speed = np.linalg.norm(loops, axis=1)
    m = h.mesh
    middle = sea & (m.lat > 25) & (m.lat < 45)
    width = lon_range[1] - lon_range[0]
    west = middle & (m.lon < lon_range[0] + width / 5)
    east = middle & (m.lon > lon_range[1] - width / 5)
    assert speed[west].mean() > 2 * speed[east].mean()
    # the loop turns clockwise, as under a subtropical wind: northward in the west, southward in the middle
    north = np.einsum("ij,ij->i", loops, m.north)
    centre = middle & (np.abs(m.lon - (lon_range[0] + width / 2)) < width / 5)
    assert north[west].mean() > 0 > north[centre].mean()


def test_no_wind_moves_no_water_and_carries_no_heat(h):
    sea = basin(h)
    t = 270.0 + 30.0 * np.cos(np.deg2rad(h.mesh.lat))
    out = h.run("OceanCurrents", reads=inputs(h, sea, np.zeros((h.months, h.mesh.n, 3)), np.broadcast_to(t, (h.months, h.mesh.n)).copy()))
    assert np.abs(out.fields["ocean_current"]).max() == 0.0
    assert np.abs(out.fields["upwelling"]).max() == 0.0
    assert np.abs(out.fields["ocean_heat_convergence"]).max() == 0.0


def test_wind_along_a_west_coast_toward_the_equator_brings_up_cold_water_and_the_ocean_makes_no_heat(h):
    """Off a coast with the land to the east, a wind toward the equator pushes the surface water out to sea (to the left
    of the wind in the south, to the right in the north): deep water rises along the coast and cools it. The heat the
    ocean moves adds up to zero over the sea in every month."""
    m = h.mesh
    sea = ~((m.lon > 0) & (np.abs(m.lat) < 60))                       # a continent east of the meridian 0
    coast = sea & (m.lon > -6) & (m.lon < 0) & (m.lat > 15) & (m.lat < 35)
    v_north = np.where((m.lat > 10) & (m.lat < 40), -6.0, 0.0)      # wind toward the equator, in the north
    wind = np.broadcast_to(v_north[:, None] * m.north, (h.months, m.n, 3)).copy()
    t = np.broadcast_to(273.0 + 30.0 * np.cos(np.deg2rad(m.lat)), (h.months, m.n)).copy()
    out = h.run("OceanCurrents", reads=inputs(h, sea, wind, t))
    up = out.fields["upwelling"].mean(axis=0)
    assert up[coast].mean() > 0
    q = out.fields["ocean_heat_convergence"]
    assert q[:, coast].mean() < 0
    assert np.abs((q * m.area).sum(axis=1)).max() < 1e-6 * np.abs(q * m.area).sum(axis=1).max()
