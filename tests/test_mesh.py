"""The mesh and the shared operators on it (build step 0)."""
import numpy as np
import pytest

from worldengine.library import operators as op
from worldengine.mesh import Mesh, cell_count, get_mesh


@pytest.mark.parametrize("level", [0, 1, 3, 5])
def test_cell_count_and_area(level):
    m = Mesh(level)
    assert m.n == cell_count(level) == 10 * 4 ** level + 2
    assert abs(m.area.sum() / (4 * np.pi) - 1.0) < 1e-12
    assert int((m.nbr_count == 5).sum()) == 12
    assert m.edge_cells.shape[0] == 3 * (m.n - 2)


def test_design_cell_counts():
    assert cell_count(5) == 10242 and cell_count(7) == 163842 and cell_count(8) == 655362


def test_neighbours_are_mutual_and_counter_clockwise():
    m = get_mesh(4)
    for i in (0, 5, 100, m.n - 1):
        for k in range(m.nbr_count[i]):
            j = m.nbr[i, k]
            assert i in m.nbr[j, :m.nbr_count[j]]
        d = m.xyz[m.nbr[i, :m.nbr_count[i]]] - m.xyz[i]
        ang = np.arctan2(d @ m.north[i], d @ m.east[i])
        assert np.all(np.diff(ang) > 0)


def test_meshes_nest_and_poles_are_cells():
    a, b = get_mesh(3), get_mesh(4)
    assert np.array_equal(a.xyz, b.xyz[:a.n])
    assert a.lat[0] == 90.0 and a.lat[11] == -90.0


def test_mesh_is_identical_when_built_twice():
    a, b = Mesh(4), Mesh(4)
    for name in ("xyz", "area", "nbr", "edge_cells", "edge_dual", "edge_dist", "edge_normal"):
        assert np.array_equal(getattr(a, name), getattr(b, name))


def test_area_spread_is_measured():
    m = get_mesh(5)
    assert 1.2 < m.area_spread < 1.5                       # the cells are nearly, not exactly, equal in area
    assert abs(m.spacing() * 6371.0 - 240.0) < 2.0         # the design's 240 km for the preview mesh


def test_operators_on_known_functions():
    m = get_mesh(5)
    z, x = m.xyz[:, 2], m.xyz[:, 0]
    assert np.abs(op.laplacian(m, z) + 2 * z).max() < 5e-3              # z is an eigenfunction: Laplacian = -2 z
    exact = np.array([1.0, 0, 0]) - x[:, None] * m.xyz
    assert np.abs(op.gradient(m, x) - exact).max() < 1e-2
    assert np.abs(op.divergence(m, exact) + 2 * x).max() < 1e-2
    assert np.abs(op.laplacian(m, np.ones(m.n))).max() < 1e-12
    assert abs((op.divergence(m, exact) * m.area).sum()) < 1e-12        # what leaves one cell enters its neighbour


def test_laplacian_matrix_matches_the_operator_and_is_symmetric():
    m = get_mesh(3)
    lap = op.laplacian_matrix(m)
    f = np.sin(3 * m.xyz[:, 0]) + m.xyz[:, 1] ** 2
    assert np.allclose(lap @ f / m.area, op.laplacian(m, f))
    assert abs(lap - lap.T).max() < 1e-14


def test_smoothing_keeps_the_mean_and_flattens():
    m = get_mesh(4)
    f = np.where(m.xyz[:, 2] > 0, 1.0, 0.0)
    s = op.smooth(m, f, 0.2)
    assert abs(op.area_mean(m, s) - op.area_mean(m, f)) < 1e-10
    assert s.max() < 1.0 and s.min() > 0.0


def test_a_wind_is_split_into_the_part_that_converges_and_the_part_that_turns():
    """A wind that only circles has no converging part; a wind that only flows toward one latitude is all converging."""
    m = get_mesh(5)
    rms = lambda v: float(np.sqrt((np.einsum("ij,ij->i", v, v) * m.area).sum() / m.area.sum()))
    lat = np.deg2rad(m.lat)
    circling = np.cross(np.array([0.3, -0.2, 0.93]), m.xyz) * 7.0            # the surface turning about a tilted axis
    assert rms(op.converging_part(m, circling)) < 0.01 * rms(circling)
    toward_equator = (-5.0 * np.sin(2 * lat))[:, None] * m.north             # the gradient of 2.5 cos(2 lat)
    part = op.converging_part(m, toward_equator)
    assert rms(part - toward_equator) < 0.02 * rms(toward_equator)
    both = circling + toward_equator
    memo = {}
    part = op.converging_part(m, both, memo)
    assert rms(part - toward_equator) < 0.02 * rms(toward_equator)
    assert rms((both - part) - circling) < 0.02 * rms(circling)
    assert np.array_equal(part, op.converging_part(m, both, memo))           # the kept solver gives the same bits
    assert np.array_equal(part, op.converging_part(m, both))                 # and so does a fresh one


def test_zonal_mean_and_east_north():
    m = get_mesh(4)
    lat, mean = op.zonal_mean(m, m.lat, 10.0)
    assert np.all(np.abs(lat - mean) < 5.0)
    v = op.from_east_north(m, np.full(m.n, 3.0), np.full(m.n, -2.0))
    e, n = op.to_east_north(m, v)
    assert np.allclose(e, 3.0) and np.allclose(n, -2.0)
