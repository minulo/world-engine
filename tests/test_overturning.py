"""Known answers of the second OceanCurrents, the overturning driven by density (ocean_wind_and_density.py), on inputs
built so that the result is known. The process is run alone through the harness, under the slot OceanCurrents."""
import numpy as np
import pytest

from conftest import DATA
from worldengine.library import overturning as ov
from worldengine.testing import Harness

SECOND = "worldengine.processes.ocean_wind_and_density:WindAndDensityOcean"
MIRROR_LON = -36.0      # the level-5 mesh maps onto itself under (lat, lon) -> (-lat, MIRROR_LON - lon), to rounding
ON_THE_EQUATOR_DEG = 1e-6   # the mesh's cells on the equator hold latitudes of either sign, of the order of 1e-14


@pytest.fixture(scope="module")
def h():
    return Harness(level=5, data_dir=DATA)


def run(h, sea, temperature, evaporation, rain, rivers=None, wind=None, ice=None, depth=4000.0, **kw):
    """Run the second OceanCurrents with the given sea, yearly temperature (K), evaporation and rain (mm a month, the same
    in every month), and the rest at rest: no wind, no ice, no rivers, deep sea everywhere."""
    m, months = h.mesh, h.months
    g = h.run("PlanetGeometry").fields
    every = lambda x: np.broadcast_to(np.asarray(x, dtype=np.float64), (months, m.n)).copy()
    reads = {"wind": np.zeros((months, m.n, 3)) if wind is None else wind, "ocean_mask": sea,
             "coriolis_parameter": g["coriolis_parameter"], "surface_temperature": every(temperature),
             "cell_area": g["cell_area"], "sea_depth": np.where(sea, depth, 0.0),
             "snow_ice_cover": every(0.0) if ice is None else ice,
             "ocean_evaporation": every(np.where(sea, evaporation, 0.0)), "precipitation": every(rain),
             "river_discharge": every(0.0) if rivers is None else rivers}
    return h.run("OceanCurrents", implementation=SECOND, reads=reads, **kw)


def mirrored_basin(h):
    """A closed sea from 60 S to 60 N, 60 degrees wide, that the mesh's own symmetry maps onto itself."""
    m = h.mesh
    centre = MIRROR_LON / 2
    return (np.abs(m.lat) < 60.0) & (np.abs(m.lon - centre) < 30.0)


def warm_equator(h):
    return 271.35 + 28.0 * np.cos(np.deg2rad(h.mesh.lat)) ** 2


def north(h):
    return h.mesh.lat > ON_THE_EQUATOR_DEG


def south(h):
    return h.mesh.lat < -ON_THE_EQUATOR_DEG


def across_the_equator(h, heat_w_m2):
    """The heat a yearly heating carries northward across the equator (W): half of what the north gains less what the
    south gains, so that the cells on the equator count half to each side."""
    q = heat_w_m2.mean(axis=0) * h.mesh.area * h.planet["radius_m"] ** 2
    return 0.5 * (q[north(h)].sum() - q[south(h)].sum())


def test_a_closed_basin_saltier_toward_its_north_pole_sinks_there_and_carries_heat_north(h):
    """The sea evaporates more in its northern half than in its southern, under the same temperatures in both: its north
    grows saltier, so the densest water lies at its northern end, and the deep water forms there. The upper water
    flows north from where the deep water rises to where it sinks, warm across the equator, and the overturning
    carries heat north across it. Measured on the commit that wrote this test: 6.3 Sv sink, all of it north of 40 N
    (0.91 of it north of 50 N), the north 2.6 psu saltier on the mean than the south, and the overturning carries
    0.19 PW north across the equator."""
    m = h.mesh
    sea = mirrored_basin(h)
    out = run(h, sea, warm_equator(h), np.where(m.lat > 0, 120.0, 80.0), 100.0)
    salt = out.fields["sea_surface_salinity"]
    mean = lambda x, mk: (x * m.area)[mk].sum() / m.area[mk].sum()
    assert mean(salt, sea & north(h)) > mean(salt, sea & south(h)) + 1.0
    sinking = np.maximum(out.fields["overturning_sinking"], 0.0) * m.area
    assert sinking[sea & (m.lat > 40)].sum() > 0.99 * sinking.sum() > 0
    assert sinking[sea & (m.lat > 50)].sum() > 0.5 * sinking.sum()
    heat = out.drivers["ocean_heat_convergence"]["carried_by_overturning"]
    assert across_the_equator(h, heat) > 0.1e15
    assert heat.mean(axis=0)[sea & (m.lat > 50)].mean() > 0                 # the north gains the heat


def test_a_mirror_symmetric_basin_carries_no_heat_across_its_equator(h):
    """The same sea with the same freshwater balance in both halves: the two ends are equally dense, share the sinking
    equally, and the overturning carries as much heat north as south. What is left is rounding: 0.05 W when this test
    was written, against 1.9e14 W in the sea of the test above, and the test allows a millionth of the latter."""
    m = h.mesh
    sea = mirrored_basin(h)
    out = run(h, sea, warm_equator(h), 100.0 + 20.0 * np.cos(np.deg2rad(2 * m.lat)), 100.0)
    sinking = np.maximum(out.fields["overturning_sinking"], 0.0) * m.area
    assert sinking.sum() > 0
    assert abs(sinking[north(h)].sum() - sinking[south(h)].sum()) < 1e-6 * sinking.sum()
    heat = out.drivers["ocean_heat_convergence"]["carried_by_overturning"]
    poleward = (heat.mean(axis=0) * m.area * h.planet["radius_m"] ** 2)[sea & (np.abs(m.lat) > 40)].sum()
    assert poleward > 0                                     # it does carry heat: toward both poles
    assert abs(across_the_equator(h, heat)) < 1e-6 * 1.9e14


def test_the_overturning_moves_heat_and_makes_none(h):
    """Summed over the sea, the overturning's heat is zero in every month, before the ocean's own evening; and so is the
    ocean's whole heat, with the wind's loops and drift as well."""
    m = h.mesh
    sea = mirrored_basin(h) | ((m.lat < -50) & (m.lat > -70))       # with a sea all the way round in the south
    s = np.clip((m.lat + 70) / 130, 0, 1)
    wind = np.broadcast_to((-6.0 * np.cos(3 * np.pi * s))[:, None] * m.east, (h.months, m.n, 3)).copy()
    t = np.broadcast_to(warm_equator(h), (h.months, m.n)) + 3.0 * np.sin(np.arange(h.months) * 2 * np.pi / h.months)[:, None] * np.sign(m.lat)
    out = run(h, sea, t, np.where(m.lat > 0, 120.0, 80.0), 100.0, wind=wind)
    weigh = lambda q: (q * m.area).sum(axis=1)
    over = out.drivers["ocean_heat_convergence"]["carried_by_overturning"]
    assert np.abs(over).max() > 1.0                         # there is an overturning, W/m2
    assert np.abs(weigh(over)).max() < 1e-6 * weigh(np.abs(over)).max()   # stored in single precision
    total = out.fields["ocean_heat_convergence"]                   # stored in single precision
    assert np.abs(weigh(total)).max() < 1e-6 * weigh(np.abs(total)).max()
    salt = out.fields["sea_surface_salinity"]
    assert abs((salt * m.area)[sea].sum() / m.area[sea].sum() - 35.0) < 1e-9 * 35.0      # and salt is kept


def test_the_overturning_heat_of_any_rise_and_sinking_adds_up_to_zero_in_double_precision(h):
    """The closure itself, apart from the process: deep water rising evenly over a basin and sinking at an uneven set of
    cells, a potential flow between them, and temperatures that change from month to month and cell to cell."""
    m, radius = h.mesh, h.planet["radius_m"]
    sea = mirrored_basin(h)
    region = np.where(sea, 0, -1)
    sink = np.where(sea & (m.lat > 45), 1.0e6 * (1.0 + np.cos(np.deg2rad(5 * m.lon)) ** 2), 0.0)
    rise = np.where(sea, sink.sum() * m.area / m.area[sea].sum(), 0.0)
    q, _, rise = ov.surface_branch(m, rise, sink, ov.branch_solver(m, region))
    months = np.arange(h.months)[:, None]
    water = 275.0 + 20.0 * np.cos(np.deg2rad(m.lat))[None, :] + 4.0 * np.sin(months + np.deg2rad(m.lon)[None, :])
    heat = ov.heat(m, q, rise, sink, region, water, radius)
    weighed = (heat * m.area * radius * radius).sum(axis=1)
    assert np.abs(heat).max() > 0
    assert np.abs(weighed).max() < 1e-12 * (np.abs(heat) * m.area * radius * radius).sum(axis=1).max()


def test_the_same_inputs_give_the_same_overturning_bit_for_bit(h):
    m = h.mesh
    sea = mirrored_basin(h)
    a = run(h, sea, warm_equator(h), np.where(m.lat > 0, 120.0, 80.0), 100.0)
    b = run(h, sea, warm_equator(h), np.where(m.lat > 0, 120.0, 80.0), 100.0)
    for name in a.fields:
        assert np.array_equal(a.fields[name], b.fields[name]), name
    for field, terms in a.drivers.items():
        for term, value in terms.items():
            assert np.array_equal(np.asarray(value), np.asarray(b.drivers[field][term])), (field, term)


def test_water_under_ice_all_year_does_not_sink(h):
    """Ice is a lid: the northern end, the densest, lies under ice in every month, so the deep water forms elsewhere."""
    m = h.mesh
    sea = mirrored_basin(h)
    ice = np.broadcast_to(np.where(m.lat > 45, 1.0, 0.0), (h.months, m.n)).copy()
    out = run(h, sea, warm_equator(h), np.where(m.lat > 0, 120.0, 80.0), 100.0, ice=ice)
    sinking = np.maximum(out.fields["overturning_sinking"], 0.0)
    assert sinking.sum() > 0 and sinking[m.lat > 45].max() == 0.0


def test_a_latitude_that_goes_round_is_found_and_cut_from_the_regions(h):
    """A sea all the way round between 68 and 52 S, joined to a basin to its north and to a bay to its south. Every band
    of latitude that lies within the ring goes round, no band north or south of it does, and once the bands that go
    round are cut out the sea falls into two regions: the basin with what is left of the ring north of the cut, and
    the bay. Without the ring nothing goes round."""
    m = h.mesh
    ring = (m.lat < -52) & (m.lat > -68)
    bay = (m.lat < -60) & (m.lat > -80) & (np.abs(m.lon) < 20)
    sea = mirrored_basin(h) | ring | bay
    band_rad = 2 * m.spacing()
    band, goes = ov.circumpolar(m, sea, band_rad)
    low = np.rad2deg(np.arange(goes.size) * band_rad) - 90                   # the southern edge of each band
    high = low + np.rad2deg(band_rad)
    assert goes[(low >= -68) & (high <= -52)].all() and goes.any()
    assert not goes[(low >= -52) | (high <= -68)].any()
    region = ov.regions(m, sea, sea & goes[band])
    labels = np.unique(region[region >= 0])
    assert labels.size == 2
    assert region[sea & (np.abs(m.lat) < 5)].min() == region[sea & (np.abs(m.lat) < 5)].max() != region[bay & (m.lat < -75)][0]
    assert not ov.circumpolar(m, mirrored_basin(h) | bay, band_rad)[1].any()


@pytest.mark.parametrize("ekman, eddies", [(0.0, 0.0), (2.0e7, 5.0e3), (-1.0e7, 5.0e3)])
def test_the_depth_of_the_light_water_balances_its_volume(ekman, eddies):
    """Gnanadesikan's balance has one positive root, whatever the sign of the wind's term; without the Southern Ocean's
    terms it is the cube root of Bryan's balance, so that the sinking grows as the mixing to the power two thirds."""
    stiffness, mixing = 0.03 / 2.5e-4, 2 * 1.0e-5 * 3.0e14
    d = ov.pycnocline_depth(stiffness, eddies, ekman, mixing)
    assert d > 0
    assert abs(((stiffness * d + eddies) * d - ekman) * d - mixing) < 1e-9 * mixing
    if ekman == 0 and eddies == 0:
        assert d == pytest.approx((mixing / stiffness) ** (1 / 3), rel=1e-12)
        more = ov.pycnocline_depth(stiffness, 0.0, 0.0, 8 * mixing)
        assert stiffness * more ** 2 == pytest.approx(4 * stiffness * d ** 2, rel=1e-9)
