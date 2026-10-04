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


def _flows(m, v):
    """What a wind carries out of each cell across each side: side length times speed."""
    return m.nbr_dual * op.side_speeds(m, v)


def _uniform_ease(m):
    ease = np.where(m.nbr >= 0, m.nbr_dual / np.where(m.nbr >= 0, m.nbr_dist, 1.0), 0.0)
    return ease, op.potential_solver(op.laplacian_matrix(m), m.area)


def test_what_leaves_a_cell_across_a_side_enters_its_neighbour():
    m = get_mesh(4)
    v = np.cross(np.array([0.3, -0.2, 0.93]), m.xyz) + 0.4 * m.north
    out = op.side_speeds(m, v)
    i, k = np.nonzero(m.nbr >= 0)
    j = m.nbr[i, k]
    back = np.array([np.flatnonzero(m.nbr[b] == a)[0] for a, b in zip(i, j)])      # the same side, seen from the neighbour
    assert np.array_equal(out[i, k], -out[j, back])
    assert np.array_equal(out[m.nbr < 0], np.zeros((m.nbr < 0).sum()))
    per_edge = np.arange(m.edge_cells.shape[0], dtype=np.float64)
    handed = op.side_values(m, per_edge)
    assert np.array_equal(handed[i, k], handed[j, back]) and np.array_equal(handed[i, k], per_edge[m.nbr_edge[i, k]])


def test_fitting_flows_to_no_gathering_keeps_the_part_of_a_wind_that_turns():
    """A wind that only circles is left alone; a wind that only flows toward one latitude is removed whole.
    Unlike a split made on the wind vectors, the fit works in the measure the transport scheme uses: what is
    left gathers nowhere, to within the solver's shift of one part in a million (the second review measured 8 %
    left over by the earlier split)."""
    m = get_mesh(5)
    ease, solver = _uniform_ease(m)
    size = lambda f: float(np.sqrt((f * f).sum()))
    nothing = np.zeros(m.n)
    lat = np.deg2rad(m.lat)
    circling = _flows(m, np.cross(np.array([0.3, -0.2, 0.93]), m.xyz) * 7.0)     # the surface turning about a tilted axis
    toward_equator = _flows(m, (-5.0 * np.sin(2 * lat))[:, None] * m.north)      # the gradient of 2.5 cos(2 lat)
    assert size(op.fit_side_flows(m, circling, nothing, ease, solver) - circling) < 0.01 * size(circling)
    assert size(op.fit_side_flows(m, toward_equator, nothing, ease, solver)) < 0.02 * size(toward_equator)
    both = circling + toward_equator
    turning = op.fit_side_flows(m, both, nothing, ease, solver)
    assert size(turning - circling) < 0.02 * size(circling)
    assert np.abs(turning.sum(axis=1)).max() < 1e-6 * np.abs(both.sum(axis=1)).max()       # gathers nowhere
    assert np.array_equal(turning, op.fit_side_flows(m, both, nothing, ease, solver))       # the same bits again
    fresh = op.potential_solver(op.laplacian_matrix(m), m.area)
    assert np.array_equal(turning, op.fit_side_flows(m, both, nothing, ease, fresh))        # and with a fresh solver


def test_fitted_flows_add_up_to_what_is_wanted_and_avoid_sides_that_are_hard_to_cross():
    """The flow out of every cell meets the wanted amount, and stays equal and opposite on the two faces of a side.
    Where a band of sides is made a hundred times harder to change, the fit sends the correction around it."""
    m = get_mesh(4)
    flow = _flows(m, 3.0 * m.east + 1.0 * m.north)
    wanted = m.area * np.sin(3 * np.deg2rad(m.lon)) * np.cos(np.deg2rad(m.lat))
    wanted -= m.area * wanted.sum() / m.area.sum()                              # it must add up to zero over the planet
    i, j = m.edge_cells[:, 0], m.edge_cells[:, 1]
    hard = (np.abs(m.lon[i]) < 30.0) & (np.abs(m.lon[j]) < 30.0)                # a band about the reference meridian
    weight = np.where(hard, 0.01, 1.0)
    ease = op.side_values(m, weight * m.edge_dual / m.edge_dist)
    solver = op.potential_solver(op.weighted_laplacian_matrix(m, weight), m.area)
    fitted = op.fit_side_flows(m, flow, wanted, ease, solver)
    assert np.abs(fitted.sum(axis=1) - wanted).max() < 1e-6 * np.abs(flow.sum(axis=1) - wanted).max()
    a, k = np.nonzero(m.nbr >= 0)
    b = m.nbr[a, k]
    back = np.array([np.flatnonzero(m.nbr[q] == p)[0] for p, q in zip(a, b)])
    assert np.array_equal(fitted[a, k], -fitted[b, back])
    change = np.abs(fitted - flow)
    in_band = op.side_values(m, hard.astype(np.float64)) > 0
    assert change[in_band].mean() < 0.2 * change[(m.nbr >= 0) & ~in_band].mean()        # measured: 0.10


def test_zonal_mean_and_east_north():
    m = get_mesh(4)
    lat, mean = op.zonal_mean(m, m.lat, 10.0)
    assert np.all(np.abs(lat - mean) < 5.0)
    v = op.from_east_north(m, np.full(m.n, 3.0), np.full(m.n, -2.0))
    e, n = op.to_east_north(m, v)
    assert np.allclose(e, 3.0) and np.allclose(n, -2.0)
