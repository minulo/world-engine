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


def split_planet(h, pole, axis_a, axis_b, speed_a, speed_b, continental=None):
    """Two plates divided by the great circle whose pole is `pole`; plate 0 is the side the pole is on.
    Each plate turns about its own axis at its own speed (radians per million years)."""
    m = h.mesh
    n = m.n
    pole, axis_a, axis_b = (np.asarray(v, dtype=float) / np.linalg.norm(v) for v in (pole, axis_a, axis_b))
    plate = np.where(m.xyz @ pole > 0, 0, 1).astype(np.int32)
    ctype = np.zeros(n, dtype=np.int16) if continental is None else continental.astype(np.int16)
    zero = np.zeros(n, dtype=np.float32)
    none = np.full(n, -1, dtype=np.int32)
    points = {"plate": plate, "x": m.xyz[:, 0], "y": m.xyz[:, 1], "z": m.xyz[:, 2], "crust_type": ctype,
              "thickness_m": np.where(ctype == 1, 35000.0, 7000.0), "ocean_age_my": np.full(n, np.nan),
              "orogeny_age_my": np.full(n, np.nan), "thickened_by_plates_m": zero, "removed_by_erosion_m": zero,
              "source_a": none, "source_b": none, "source_c": none, "weight_a": zero, "weight_b": zero, "weight_c": zero}
    plates = {"plate": [0, 1], "axis_x": [axis_a[0], axis_b[0]], "axis_y": [axis_a[1], axis_b[1]], "axis_z": [axis_a[2], axis_b[2]],
              "angular_speed_rad_per_my": [speed_a, speed_b], "area_m2": [0.0, 0.0], "continental_share": [0.0, 0.0],
              "carries_continent": [False, False], "centre_x": [0.0, 0.0], "centre_y": [0.0, 0.0], "centre_z": [1.0, -1.0]}
    events = {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []}
    return plate, {"crust_points": points, "plates": plates, "tectonic_events": events}


def touching_another_plate(mesh, plate):
    i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
    cross = plate[i] != plate[j]
    out = np.zeros(mesh.n, dtype=bool)
    out[i[cross]] = True
    out[j[cross]] = True
    return out


BOUNDARY_POLES = [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.3, -0.8, 0.52), (-0.61, 0.2, 0.77)]


@pytest.mark.parametrize("pole", BOUNDARY_POLES)
def test_plates_sliding_past_each_other_make_a_transform_boundary_whichever_way_it_runs(h, pole):
    """Both plates turn about the pole of the circle that divides them, in opposite senses: everywhere along the
    boundary they slide past each other at 6.4 cm a year and neither close nor part. On a mesh of six-sided cells
    the sides of the boundary cells stand 30 to 60 degrees off the boundary, so a rule that judges by single sides
    reports false ridges and trenches here."""
    g = geometry(h)
    plate, tables = split_planet(h, pole, pole, pole, 0.005, -0.005)
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables)
    f = out.fields
    kinds = h.registry.fields["boundary_kind"].categories
    edge = touching_another_plate(h.mesh, plate)
    assert set(f["boundary_kind"][edge]) == {kinds.index("transform")}
    assert np.abs(f["convergence_rate"][edge]).max() < 0.25 * 0.0637            # the closing reported is a small share of the sliding
    assert f["volcanism"].max() == 0.0
    assert np.allclose(f["crust_thickness"], 7000.0)
    assert len(out.tables["tectonic_events"]["kind"]) == 0                        # sliding past makes no ridge, trench or collision


@pytest.mark.parametrize("pole", BOUNDARY_POLES)
def test_the_closing_speed_of_a_head_on_boundary_is_reported_to_within_three_percent(h, pole):
    """Both plates turn about one axis lying in the plane of their boundary, in opposite senses: a quarter turn from
    that axis they meet head on."""
    g = geometry(h)
    m = h.mesh
    pole = np.asarray(pole) / np.linalg.norm(pole)
    axis = np.cross(pole, [0.0, 1.0, 0.0] if abs(pole[1]) < 0.9 else [1.0, 0.0, 0.0])
    axis /= np.linalg.norm(axis)
    speed = 0.005
    plate, tables = split_planet(h, pole, axis, axis, speed, -speed)
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables)
    # the true closing speed at each cell: its own plate's velocity relative to the other, along the line to the other plate
    own = np.where((plate == 0)[:, None], axis, -axis) * (2 * speed / 1e6)
    relative = np.cross(own, m.xyz) * R
    toward = np.where((plate == 0)[:, None], -pole, pole)
    toward = toward - (toward * m.xyz).sum(axis=1)[:, None] * m.xyz
    true = (relative * toward).sum(axis=1) / np.maximum(np.linalg.norm(toward, axis=1), 1e-12)
    strong = touching_another_plate(m, plate) & (np.abs(true) > 0.03)
    assert strong.sum() > 20
    ratio = out.fields["convergence_rate"][strong] / true[strong]
    assert ratio.min() > 0.97 and ratio.max() < 1.01


def test_ocean_floor_dives_under_a_continent_and_the_belt_rises_on_the_continent_only():
    h = Harness(level=5)                                                     # the belt is 600 km wide: it needs cells smaller than that
    g = geometry(h)
    m = h.mesh
    for continent_plate in (0, 1):                                           # either plate may carry the continent
        plate0 = m.xyz[:, 2] > 0
        continental = plate0 if continent_plate == 0 else ~plate0
        plate, tables = split_planet(h, (0, 0, 1), (1, 0, 0), (1, 0, 0), -0.005, 0.005, continental=continental)
        out = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables)
        f = out.fields
        near = (np.abs(m.lat) < 6) & (np.abs(m.lon - 90) < 25)                # here the plates close head on
        thickened = out.drivers["crust_thickness"]["thickened_by_plates"]
        assert thickened[near & continental].max() > 5000.0
        assert thickened[~continental].max() == 0.0
        arc = (f["volcanism"] > 0.1) & (np.abs(m.lon - 90) < 25)              # (on the far side of the planet the plates part)
        assert arc[near & continental].any() and not arc[~continental].any()  # the volcanic arc stands on the overriding plate


def test_between_two_ocean_floors_one_plate_dives_along_the_whole_trench(h):
    """Equal ages: the plate with the higher number dives, so the volcanic arc stands on plate 0 only."""
    g = geometry(h)
    m = h.mesh
    plate, tables = split_planet(h, (0, 0, 1), (1, 0, 0), (1, 0, 0), -0.005, 0.005)
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables)
    f = out.fields
    kinds = h.registry.fields["boundary_kind"].categories
    here = np.abs(m.lon - 90) < 25                                             # where the plates close head on
    closing = here & touching_another_plate(m, plate) & (f["boundary_kind"] == kinds.index("trench"))
    assert closing[plate == 0].any() and closing[plate == 1].any()
    arc = here & (f["volcanism"] > 0.1)
    assert arc[plate == 0].any() and not arc[plate == 1].any()


def plate_tables(mesh, plate, axes, speeds, continental=None):
    """The tables Tectonics reads, for any number of plates: one turning axis and one speed (radians per My) each."""
    n, k = mesh.n, len(speeds)
    axes = np.asarray(axes, dtype=float)
    axes = axes / np.linalg.norm(axes, axis=1, keepdims=True)
    ctype = np.zeros(n, dtype=np.int16) if continental is None else np.asarray(continental).astype(np.int16)
    zero, none = np.zeros(n, dtype=np.float32), np.full(n, -1, dtype=np.int32)
    points = {"plate": np.asarray(plate).astype(np.int32), "x": mesh.xyz[:, 0], "y": mesh.xyz[:, 1], "z": mesh.xyz[:, 2],
              "crust_type": ctype, "thickness_m": np.where(ctype == 1, 35000.0, 7000.0), "ocean_age_my": np.full(n, np.nan),
              "orogeny_age_my": np.full(n, np.nan), "thickened_by_plates_m": zero, "removed_by_erosion_m": zero,
              "source_a": none, "source_b": none, "source_c": none, "weight_a": zero, "weight_b": zero, "weight_c": zero}
    plates = {"plate": list(range(k)), "axis_x": list(axes[:, 0]), "axis_y": list(axes[:, 1]), "axis_z": list(axes[:, 2]),
              "angular_speed_rad_per_my": list(speeds), "area_m2": [0.0] * k, "continental_share": [0.0] * k,
              "carries_continent": [False] * k, "centre_x": [0.0] * k, "centre_y": [0.0] * k, "centre_z": [1.0] * k}
    return {"crust_points": points, "plates": plates, "tectonic_events": {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []}}


@pytest.mark.parametrize("half_width_cells", [0.6, 1.0, 2.0])
def test_a_narrow_plate_sliding_inside_another_is_a_transform_on_both_flanks(h, half_width_cells):
    """A strip around the equator turns about the pole, inside one plate that stands still on both sides of it:
    along both of its flanks it slides past. The direction of a boundary is added up over a stretch four cells long,
    and a strip narrower than that has its other flank within reach. Added in, that flank cancelled the direction or
    turned it by chance: the second review found ridges and trenches all along such a strip, and not one transform."""
    m = h.mesh
    g = geometry(h)
    half_width = half_width_cells * np.rad2deg(m.spacing())
    plate = np.where(np.abs(m.lat) > half_width, 0, 1)
    tables = plate_tables(m, plate, [(0, 0, 1)] * 2, [0.0, 0.006])
    f = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables).fields
    kinds = h.registry.fields["boundary_kind"].categories
    edge = touching_another_plate(m, plate)
    assert edge[plate == 1].sum() > 50
    assert set(f["boundary_kind"][edge]) == {kinds.index("transform")}
    assert np.abs(f["convergence_rate"][edge]).max() < 0.25 * 0.006 * R / 1e6     # the closing reported is a small share of the sliding
    assert np.allclose(f["crust_thickness"], 7000.0) and f["volcanism"].max() == 0.0


def test_a_plate_of_one_cell_has_no_ridge_or_trench(h):
    """The outline of one cell adds up to round-off, which points anywhere. Taken as a direction, it made three such
    plates in ten a spreading ridge opening at the plate's full speed (second review)."""
    m = h.mesh
    g = geometry(h)
    kinds = h.registry.fields["boundary_kind"].categories
    for cell in (0, 5, 333, 1500, 2000):
        plate = np.zeros(m.n, dtype=np.int32)
        plate[cell] = 1
        axis = np.cross(m.xyz[cell], [0.0, 0.0, 1.0] if abs(m.xyz[cell][2]) < 0.9 else [1.0, 0.0, 0.0])
        f = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=plate_tables(m, plate, [axis, axis], [0.0, 0.0094])).fields
        assert f["boundary_kind"][cell] == kinds.index("transform") and f["convergence_rate"][cell] == 0.0


def turned_and_plain(hh, points, plates):
    """Tectonics run on the given tables, and on the same tables turned by a fifth of a circle about the poles, which
    maps the mesh onto itself. Returns both sets of fields and, for every cell, the cell it lands on."""
    m = hh.mesh
    g = geometry(hh)
    turn = np.deg2rad(72.0)
    rz = np.array([[np.cos(turn), -np.sin(turn), 0.0], [np.sin(turn), np.cos(turn), 0.0], [0.0, 0.0, 1.0]])
    goes_to = np.argmax(m.xyz @ rz.T @ m.xyz.T, axis=1)                       # where each cell lands
    assert np.allclose(m.xyz[goes_to], m.xyz @ rz.T, atol=1e-12) and len(set(goes_to)) == m.n
    points = {name: np.asarray(col) for name, col in points.items()}
    plates = {name: np.asarray(col) for name, col in plates.items()}
    turned_points = {name: np.empty_like(col) for name, col in points.items()}
    for name, col in points.items():
        turned_points[name][goes_to] = col
    turned_points.update(x=m.xyz[:, 0], y=m.xyz[:, 1], z=m.xyz[:, 2])
    axes = np.stack([plates["axis_x"], plates["axis_y"], plates["axis_z"]], axis=1) @ rz.T
    turned_plates = dict(plates, axis_x=axes[:, 0], axis_y=axes[:, 1], axis_z=axes[:, 2])
    events = {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []}
    run = lambda pts, pl: hh.run("Tectonics", reads={"cell_area": g["cell_area"]},
                                 lagged_tables={"crust_points": pts, "plates": pl, "tectonic_events": events}).fields
    return run(points, plates), run(turned_points, turned_plates), goes_to


def assert_the_same_world_turned(plain, turned, goes_to):
    for name in ("plate_id", "crust_type", "boundary_kind"):
        assert np.array_equal(turned[name][goes_to], plain[name]), name
    for name, within in (("crust_thickness", 1.0), ("convergence_rate", 1e-6), ("boundary_distance", 1.0), ("volcanism", 1e-5)):
        assert np.abs(turned[name][goes_to].astype(np.float64) - plain[name]).max() < within, name
    age_plain, age_turned = plain["ocean_crust_age"].astype(np.float64), turned["ocean_crust_age"][goes_to].astype(np.float64)
    assert np.array_equal(np.isnan(age_plain), np.isnan(age_turned))
    if not np.isnan(age_plain).all():
        assert np.nanmax(np.abs(age_plain - age_turned)) < 1e-3


def test_turning_the_planet_by_one_face_of_the_mesh_turns_the_tectonics_with_it():
    """The mesh maps onto itself when turned by a fifth of a circle about its poles. Many cells lie exactly as far
    from two boundary cells as from one, and a cell can share the same length of side with two plates; if such ties
    are settled by the order of the cells or by the last bit of a sum, the turned planet is a different world (second
    review: the crust differed by up to 10.6 km in the default world)."""
    hh = Harness(level=4, seed=20261004)
    g = geometry(hh)
    seeded = hh.run("Tectonics", reads={"cell_area": g["cell_area"]}, start=True)
    plain, turned, goes_to = turned_and_plain(hh, seeded.tables["crust_points"], seeded.tables["plates"])
    assert_the_same_world_turned(plain, turned, goes_to)


@pytest.mark.parametrize("radius_deg", [13.0, 20.0, 31.0])
def test_a_round_plate_centred_on_a_pole_is_the_same_world_when_turned(radius_deg):
    """The cells near the middle of a round plate lie exactly as far from many cells of its rim: from five of them,
    or from ten. Comparing only the four nearest left the choice among the rest to the order of the cells, and the
    turned planet differed in the closing speed at the five-sided cells and in the crust (third check)."""
    hh = Harness(level=4, seed=1)
    m = hh.mesh
    plate = (np.rad2deg(np.arccos(np.clip(m.xyz[:, 2], -1, 1))) < radius_deg).astype(np.int32)      # the cap around the north pole
    continental = (plate == 0) & (m.lat < np.deg2rad(60.0))                # the cap moves against a continent on one side
    tables = plate_tables(m, plate, [(0, 0, 1), (1, 0, 0)], [0.0, 0.008], continental=continental)
    plain, turned, goes_to = turned_and_plain(hh, tables["crust_points"], tables["plates"])
    assert plate.sum() > 5 and len(set(plain["boundary_kind"])) > 2          # the rim holds several kinds of boundary
    assert_the_same_world_turned(plain, turned, goes_to)


def test_which_plate_dives_follows_the_continent_first_and_then_the_older_floor():
    """The rules of the trench, on eight made-up boundary cells: four of plate 0 facing four of plate 1.
    A review found that swapping the rules for 'the higher plate number dives' passed every other test."""
    from worldengine.processes.tectonics_snapshot import TRENCH, SnapshotPlates
    plate = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    facing = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    kind = np.full(8, TRENCH, dtype=np.int16)
    sea_floor = np.ones(8, dtype=bool)
    nowhere = np.zeros(8, dtype=bool)
    dives = lambda faces_continent, ocean, age: SnapshotPlates._diving(plate, facing, faces_continent, kind, ocean,
                                                                       np.asarray(age, dtype=float), 2, 0.1)
    # two ocean floors: the older floor dives, here the plate with the lower number
    assert dives(nowhere, sea_floor, [100.0] * 4 + [20.0] * 4).tolist() == [True] * 4 + [False] * 4
    assert dives(nowhere, sea_floor, [20.0] * 4 + [100.0] * 4).tolist() == [False] * 4 + [True] * 4
    # floors of the same age: the higher plate number, so that one plate dives along the whole trench
    assert dives(nowhere, sea_floor, [60.0] * 8).tolist() == [False] * 4 + [True] * 4
    # plate 1 carries a continent along half of the trench (cells 6 and 7). Plate 0's floor dives under it there,
    # and therefore along the rest of the same trench as well, although plate 1's floor is the older one there.
    ocean = np.array([True] * 6 + [False] * 2)
    faces_continent = np.array([False, False, True, True, False, False, False, False])
    age = [50.0, 50.0, 50.0, 50.0, 150.0, 150.0, np.nan, np.nan]
    assert dives(faces_continent, ocean, age).tolist() == [True] * 4 + [False] * 4


def test_events_count_boundary_cells_and_a_cell_names_its_event_only_where_mountains_are_building(h):
    g = geometry(h)
    points, plates, events = two_plates(h, -0.005, 0.005)
    points["crust_type"] = np.ones(h.mesh.n, dtype=np.int16)
    points["thickness_m"] = np.full(h.mesh.n, 35000.0)
    out = h.run("Tectonics", reads={"cell_area": g["cell_area"]},
                lagged_tables={"crust_points": points, "plates": plates, "tectonic_events": events})
    ev = out.tables["tectonic_events"]
    collision, spreading = 2, 4                                                # the plates close on one side of the planet and part on the other
    assert list(ev["kind"]) == [collision, spreading] and list(ev["plate_a"]) == [0, 0] and list(ev["plate_b"]) == [1, 1]
    # the count is of the cells along the boundary, not of the sides between them
    edge = touching_another_plate(h.mesh, points["plate"])
    kinds = h.registry.fields["boundary_kind"].categories
    for row, name in enumerate(("collision", "ridge")):
        assert int(ev["cells"][row]) == int((edge & (out.fields["boundary_kind"] == kinds.index(name))).sum())
    assert int(ev["cells"].sum()) < int(edge.sum())                            # near the turning axis the plates slide past
    d = out.drivers["crust_thickness"]
    active = d["thickened_by_plates"] > 500.0
    assert active.any() and np.array_equal(d["event"] >= 0, active)
    assert set(d["event"][active]) == {0}                                      # row 0 of the table: the collision
    assert np.all(np.isnan(out.fields["orogeny_age"][~active])) and np.all(out.fields["orogeny_age"][active] == 0.0)


@pytest.mark.parametrize("seed", [20261004, 7, 11])
def test_in_a_seeded_world_the_two_sides_of_a_trench_do_not_both_dive_or_both_override(seed):
    """One side of a trench dives and the other overrides. The two sides may disagree only where the crust beside the
    trench changes from continent to ocean and the trench truly turns over; that must stay rare."""
    from worldengine.processes.tectonics_snapshot import TRENCH, SnapshotPlates
    hh = Harness(level=5, seed=seed)
    g = geometry(hh)
    out = hh.run("Tectonics", reads={"cell_area": g["cell_area"]}, start=True)
    m, f, pl = hh.mesh, out.fields, out.tables["plates"]
    plate, ctype = f["plate_id"], f["crust_type"]
    k = len(pl["plate"])
    rotation = np.stack([pl["axis_x"], pl["axis_y"], pl["axis_z"]], axis=1) * (pl["angular_speed_rad_per_my"] / 1e6)[:, None]
    c = hh.constants["Tectonics"]
    _, facing, faces_continent, kind, _ = SnapshotPlates._boundaries(m, plate, ctype, rotation, R, k, c["boundaries"])
    diving = SnapshotPlates._diving(plate, facing, faces_continent, kind, ctype == 0, f["ocean_crust_age"].astype(float), k,
                                    c["ocean_age"]["equal_within_my"])
    i, j = m.edge_cells[:, 0], m.edge_cells[:, 1]
    trench = (plate[i] != plate[j]) & (kind[i] == TRENCH) & (kind[j] == TRENCH) & (facing[i] == plate[j]) & (facing[j] == plate[i])
    assert trench.sum() > 100
    alike = trench & (diving[i] == diving[j])
    assert alike.sum() <= 0.01 * trench.sum()
    turn_over = (faces_continent[i] != (ctype[j] == 1)) | (faces_continent[j] != (ctype[i] == 1))
    assert not (alike & ~turn_over).any()


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
    first = 2500.0 + 350.0 * np.sqrt(age)                              # Parsons and Sclater 1977: floor of 0 to 70 My
    second = 6400.0 - 3200.0 * np.exp(-age / 62.8)                     # the same paper: floor older than 20 My
    assert np.allclose(depth[age <= 20.0], first[age <= 20.0], atol=0.5)
    assert np.allclose(depth[age >= 70.0], second[age >= 70.0], atol=0.5)
    between = (age > 20.0) & (age < 70.0)                              # both rules hold here; the process uses one or the other
    assert np.all(np.minimum(np.abs(depth - first), np.abs(depth - second))[between] < 0.5)
    assert np.abs(np.diff(depth)).max() < 350.0 * np.sqrt(age[1]) + 0.5   # no step where the rule changes (the first step is the largest)
    assert np.all(np.diff(depth) >= -1e-3)                             # older floor is never shallower
    assert abs(depth[-1] - (6400.0 - 3200.0 * np.exp(-180.0 / 62.8))) < 0.5
    changeover = age[np.flatnonzero(np.abs(depth - second) < np.abs(depth - first))[0]]
    assert 25.0 < changeover < 28.0                                    # the two rules cross near 26 My


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


def test_dry_ground_in_a_part_filled_hollow_is_put_down_to_the_water_running_out_not_to_a_barrier(h):
    """A wide basin holds the lowest point. A sill at its rim leads to a small deep bowl. The water fills the basin
    to the sill, spills into the bowl and runs out there. The dry sides of the bowl lie below sea level with the way
    open, so no barrier can be named; a walled pit elsewhere is the case with a barrier."""
    g = geometry(h)
    m = h.mesh
    def angle_from(lat, lon):
        centre = np.array([np.cos(np.deg2rad(lat)) * np.cos(np.deg2rad(lon)), np.cos(np.deg2rad(lat)) * np.sin(np.deg2rad(lon)),
                           np.sin(np.deg2rad(lat))])
        return np.rad2deg(np.arccos(np.clip(m.xyz @ centre, -1, 1)))
    basin, bowl_at, sill_at, pit_at = angle_from(0, 0), angle_from(0, 62), angle_from(0, 44), angle_from(0, 180)
    height = np.full(m.n, 1000.0)
    in_basin, in_bowl = basin < 40, bowl_at < 15
    height[sill_at < 9] = -500.0                                              # the open way between the two
    height[in_basin] = -3000.0
    height[in_bowl] = -2500.0 + 2000.0 * (bowl_at[in_bowl] / 15.0) ** 2
    in_pit = pit_at < 10
    height[in_pit] = -800.0
    area = g["cell_area"]
    part_of_bowl = (area * np.maximum(-1500.0 - height, 0.0))[in_bowl].sum()   # fills the bowl to 1,500 m below the reference
    volume = (area[in_basin] * 2500.0).sum() + part_of_bowl
    hh = Harness(level=4, planet={"surface_water_volume_m3": float(volume)})
    out = hh.run("SeaLevel", reads={"elevation": height, "cell_area": area})
    f, d = out.fields, out.drivers["ocean_mask"]
    seas = out.tables["seas"]
    assert abs(seas["surface_m"][0] + 500.0) < 1.0 and abs(seas["surface_m"][1] + 1500.0) < 30.0
    dry_bowl = in_bowl & ~f["ocean_mask"]
    assert dry_bowl.sum() > 5 and np.all(f["height_above_sea"][dry_bowl] < 0)   # dry, and below the sea's surface
    ran_out, behind_barrier = 4, 3
    assert set(d["reason"][dry_bowl]) == {ran_out} and set(d["barrier_cell"][dry_bowl]) == {-1}
    assert set(d["reason"][in_pit]) == {behind_barrier}
    assert np.all(height[d["barrier_cell"][in_pit]] == 1000.0)                 # the pit's barrier is the wall around it


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
def albedo_inputs(h, sea):
    g = geometry(h)
    return {"ocean_mask": sea, "latitude": g["latitude"], "cell_area": g["cell_area"]}


def test_albedo_returns_the_table_value_of_each_surface_type(h):
    sea = h.mesh.xyz[:, 0] > 0
    bare = {"cloud_share": 0.0, "low_sun_term": 0.0}
    warm = np.full((12, h.mesh.n), 300.0)
    a = h.run("Albedo", reads=albedo_inputs(h, sea), lagged={"surface_temperature": warm}, constants=bare).fields["albedo"]
    assert np.allclose(a[:, sea], 0.07) and np.allclose(a[:, ~sea], 0.20)
    snowing = np.full((12, h.mesh.n), 20.0)
    cold = h.run("Albedo", reads=albedo_inputs(h, sea), lagged={"surface_temperature": warm - 100.0, "snowfall": snowing},
                 constants=bare).fields["albedo"]
    assert np.allclose(cold, 0.658)                                    # ice on the sea, snow on the land
    dry = h.run("Albedo", reads=albedo_inputs(h, sea), lagged={"surface_temperature": warm - 100.0}, constants=bare).fields["albedo"]
    assert np.allclose(dry[:, sea], 0.658) and np.allclose(dry[:, ~sea], 0.20)      # cold land on which no snow falls stays dark


def test_albedo_with_cloud_and_ice_gives_the_published_values_and_its_drivers_add_up(h):
    sea = h.mesh.xyz[:, 0] > 0
    t = np.where(h.mesh.lat > 60, 250.0, 300.0) * np.ones((12, 1))
    snowing = np.where(h.mesh.lat > 60, 20.0, 0.0) * np.ones((12, 1))
    out = h.run("Albedo", reads=albedo_inputs(h, sea), lagged={"surface_temperature": t, "snowfall": snowing})
    a = out.fields["albedo"].astype(np.float64)
    assert np.allclose(a[:, h.mesh.lat > 60], 0.62, atol=2e-3)         # ice-covered cells reflect the 0.62 of North et al. 1981
    free = h.mesh.lat <= 60
    assert a[0, free & (np.abs(h.mesh.lat) < 10)].mean() < a[0, free & (h.mesh.lat > 50)].mean()   # more reflection at low sun
    total = sum(v.astype(np.float64) for v in out.drivers["albedo"].values())
    assert np.allclose(total, a, atol=1e-6)
    assert not out.notices                                             # a sixteenth of the planet under ice is no deep ice age
    first_guess = h.run("Albedo", reads=albedo_inputs(h, sea))
    assert np.all(first_guess.drivers["albedo"]["from_snow_and_ice"] == 0.0)     # the first guess of fields.yaml is a planet without ice


def _year(mean_c, swing):
    """Twelve monthly temperatures (K) with the given mean and half-swing, warmest in July."""
    return 273.15 + mean_c + swing * np.array([np.cos(2 * np.pi * (m - 6.5) / 12) for m in range(12)])


def _white_months(h, sea, temperature, snowfall=0.0):
    """Per month, the share of the surface that Albedo covers with snow or ice, with the cloud and the low sun left out."""
    n = h.mesh.n
    t = np.asarray(temperature, dtype=np.float64).reshape(12, 1) * np.ones((1, n))
    snow = np.broadcast_to(np.asarray(snowfall, dtype=np.float64).reshape(-1, 1), (12, n))
    out = h.run("Albedo", reads=albedo_inputs(h, np.full(n, sea)), lagged={"surface_temperature": t, "snowfall": snow},
                constants={"cloud_share": 0.0, "low_sun_term": 0.0})
    return out.drivers["albedo"]["from_snow_and_ice"][:, 0].astype(np.float64) / (0.658 - (0.07 if sea else 0.20))


def test_ice_lies_on_the_sea_where_the_mean_of_the_year_is_below_minus_ten(h):
    """North, Cahalan and Coakley 1981, p. 102: an ice cap whose edge is the yearly mean of -10 C."""
    assert np.all(_white_months(h, True, _year(-5.0, 12.0)) == 0.0)        # eight months below freezing, yet no ice
    assert np.allclose(_white_months(h, True, _year(-15.0, 20.0)), 1.0)    # ice in every month, the warm ones included
    assert np.allclose(_white_months(h, True, _year(-9.5, 0.0)), 0.25, atol=1e-4)     # inside the ramp, 2 K wide, the ice is partial
    assert np.all(_white_months(h, True, _year(-8.9, 0.0)) == 0.0)
    assert np.allclose(_white_months(h, True, _year(-15.0, 20.0), snowfall=0.0), 1.0)  # sea ice asks for no snowfall


def test_snow_lies_on_land_only_where_it_fell_and_until_it_has_melted(h):
    """The snow store, by hand. Six months at -5 C with 10 mm of snowfall each, then six months at +5 C without.
    At the end of the cold months the store holds 10, 20 ... 60 mm. A month at +5 C can melt 4 mm a day per degree
    times 30.44 days times 5 degrees = 609 mm, so the first warm month empties the store. The mean store of a month
    is the average of its start and its end: 5, 15, 25, 35, 45, 55, then 30, then nothing. The ground is fully white
    from 15 mm on. The earlier rule, snow in every month below freezing and no other, made cold dry ground white and
    froze one seeded world in 32 (second review)."""
    cold_then_warm = 273.15 + np.array([-5.0] * 6 + [5.0] * 6)
    white = _white_months(h, False, cold_then_warm, [10.0] * 6 + [0.0] * 6)
    assert np.allclose(white, [1 / 3, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0], atol=1e-5)
    assert np.all(_white_months(h, False, cold_then_warm, 0.0) == 0.0)               # no snowfall, no snow, however cold
    assert np.all(_white_months(h, False, np.full(12, 220.0), 0.0) == 0.0)
    # Deep snow outlasts the thaw: 600 mm against 243.5 mm of melt a month at +2 C is gone in the third warm month.
    late = _white_months(h, False, 273.15 + np.array([-5.0] * 6 + [2.0] * 6), [100.0] * 6 + [0.0] * 6)
    assert np.allclose(late, [1] * 9 + [0] * 3, atol=1e-5)
    # Land that never thaws keeps what falls: 2 mm a month is an ice sheet by the third year followed.
    assert np.allclose(_white_months(h, False, np.full(12, 250.0), 2.0), 1.0)
    # ... and a cold desert with 0.1 mm a month holds 2.4 to 3.6 mm in that year: mostly dark.
    desert = _white_months(h, False, np.full(12, 250.0), 0.1)
    assert np.allclose(desert, (2.45 + 0.1 * np.arange(12)) / 15.0, atol=1e-5)


def test_albedo_says_so_when_snow_and_ice_cover_more_than_a_third_of_the_planet(h):
    sea = h.mesh.xyz[:, 0] > 0
    t = np.where(np.abs(h.mesh.lat) > 15, 240.0, 300.0) * np.ones((12, 1))            # ice down to 15 degrees: three quarters of the surface
    out = h.run("Albedo", reads=albedo_inputs(h, sea), lagged={"surface_temperature": t, "snowfall": np.full((12, h.mesh.n), 20.0)})
    notes = [n for n in out.notices if n["kind"] == "process_note"]
    assert len(notes) == 1 and "deep ice age" in notes[0]["what"] and abs(notes[0]["share_covered"] - (1 - np.sin(np.deg2rad(15)))) < 0.02


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


def test_the_storage_driver_is_the_heat_going_into_and_out_of_storage_and_nothing_else(h):
    """With real sunlight, whose yearly cycle at the poles is far from a smooth wave, the driver named seasonal storage
    must equal -(C / B) dT/dt, with C the heat capacity of land or sea. It used to hold the dropped part of the sunlight too."""
    m = h.mesh
    sea = m.lon < 0
    out = h.run("EnergyBalance", reads=energy_inputs(h, sea))
    t = out.fields["surface_temperature"].astype(np.float64)
    spectrum = np.fft.rfft(t, axis=0)
    wave = np.arange(spectrum.shape[0])[:, None]
    rate = np.fft.irfft(spectrum * 1j * wave * 2 * np.pi / 3.15576e7, n=12, axis=0)       # dT/dt in K per second
    capacity = np.where(sea, 3.10e8, 1.055e7)
    expected = -capacity * rate / 2.09
    d = out.drivers["surface_temperature"]
    assert np.abs(expected).max() > 5.0                                                    # the test has something to see
    assert np.abs(d["seasonal_storage"] - expected).max() < 0.01
    total = sum(v.astype(np.float64) for v in d.values())
    assert np.allclose(total, t, atol=1e-3)


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
def ridge_run(h, top_m, constants=None):
    """A strip of land across a steady wind from the west, with a ridge of the given height along its middle."""
    g = geometry(h)
    m = h.mesh
    n = m.n
    shape = np.exp(-(m.lon / 6.0) ** 2) * (np.abs(m.lat) < 35)
    land = 2500.0 * shape > 50.0                                       # the same land whatever the height of the ridge
    ridge = top_m * shape
    wind = np.broadcast_to(6.0 * np.cos(np.deg2rad(m.lat))[:, None] * m.east, (12, n, 3))
    temperature = np.broadcast_to(292.0 - 6.5 * ridge / 1000.0, (12, n))
    out = h.run("Moisture", reads={"wind": wind, "subsidence": np.zeros((12, n)), "surface_temperature": temperature,
                                   "height_above_sea": ridge, "ocean_mask": ~land, "cell_area": g["cell_area"]}, constants=constants)
    return out, ridge


def test_one_ridge_across_a_steady_wind_wet_on_the_side_facing_the_wind_dry_on_the_sheltered_side(h):
    """The known answer is the difference a ridge makes to the same strip of land: more rain where the air is held
    back and lifted, less behind it. Measured on this mesh: 2.6 times the flat strip's rain on the side facing the
    wind, a quarter of it on the sheltered side."""
    m = h.mesh
    out, ridge = ridge_run(h, 2500.0)
    flat, _ = ridge_run(h, 0.0)
    rain = out.fields["precipitation"].astype(np.float64).mean(axis=0)
    rain_flat = flat.fields["precipitation"].astype(np.float64).mean(axis=0)
    band = np.abs(m.lat) < 25
    facing = band & (m.lon > -9) & (m.lon < -2)
    sheltered = band & (m.lon > 2) & (m.lon < 9)
    foot = band & (m.lon > -16) & (m.lon < -9)
    upwind_sea = band & (m.lon > -60) & (m.lon < -30)
    assert rain[facing].mean() > 2 * rain_flat[facing].mean()          # held-back and rising air makes rain
    assert rain[sheltered].mean() < 0.5 * rain_flat[sheltered].mean()  # and leaves a rain shadow behind the ridge
    assert rain[facing].mean() > 4 * rain[sheltered].mean()
    assert rain[foot].mean() > 1.2 * rain[upwind_sea].mean()           # the air held back makes a wet zone before the ridge
    assert abs(rain[upwind_sea].mean() / rain_flat[upwind_sea].mean() - 1) < 0.02      # far upwind the ridge changes little
    d = out.drivers["precipitation"]
    total = d["from_moist_air"].astype(np.float64) + d["from_rising_ground"] + d["stopped_by_sinking_air"]
    assert np.allclose(total, out.fields["precipitation"], rtol=1e-4, atol=1e-2)
    lift = d["from_rising_ground"].mean(axis=0)
    assert lift[facing].mean() > 5.0 and lift[sheltered].max() < 1e-6    # forced ascent only where the wind blows uphill
    assert lift[ridge == 0.0].max() == 0.0                             # and its rain falls on the rising ground, never on the sea before it
    assert flat.drivers["precipitation"]["from_rising_ground"].max() == 0.0
    came_from = d["vapour_came_from"][0]
    lee = np.flatnonzero(sheltered)
    assert np.all(m.lon[came_from[lee]] < m.lon[lee])                  # the vapour came from the west, over the ridge


def wall_run(h, height_m, constants=None, wind=None):
    """A plateau with a cliff for an edge, 40 degrees of longitude wide, facing a steady wind from the west over a warm sea."""
    g = geometry(h)
    m = h.mesh
    n = m.n
    plateau = (np.abs(m.lat) < 30) & (m.lon >= 0) & (m.lon <= 40)
    height = np.where(plateau, height_m, 0.0)
    if wind is None:
        wind = np.broadcast_to(6.0 * np.cos(np.deg2rad(m.lat))[:, None] * m.east, (12, n, 3))
    out = h.run("Moisture", reads={"wind": wind, "subsidence": np.zeros((12, n)),
                                   "surface_temperature": np.broadcast_to(298.0 - 6.5 * height / 1000.0, (12, n)),
                                   "height_above_sea": height, "ocean_mask": ~plateau, "cell_area": g["cell_area"]}, constants=constants)
    return out, plateau, height


def wall_numbers(h, out, plateau):
    """Yearly rain (mm) on the sea cells that touch the cliff, on the sea within 500 km of it and far upwind, and the
    rain of rising ground per metre of cliff (kg a second), all within 20 degrees of the equator."""
    m = h.mesh
    area = geometry(h)["cell_area"]
    rain = out.fields["precipitation"].astype(np.float64).sum(axis=0)
    lift = out.drivers["precipitation"]["from_rising_ground"].astype(np.float64).sum(axis=0)
    band = np.abs(m.lat) < 20
    nb, has = np.where(m.nbr >= 0, m.nbr, 0), m.nbr >= 0
    touching = ~plateau & (plateau[nb] & has).any(axis=1) & band & (m.lon < 0)
    mean = lambda field, where: float((field * area)[where].sum() / area[where].sum())
    near, far = band & ~plateau & (m.lon > -4.5) & (m.lon < 0), band & (m.lon > -90) & (m.lon < -50)
    length = 2 * np.deg2rad(20.0) * R                                  # of the cliff inside the band, m
    seconds, kg_per_mm_m2 = 3.156e7, 1.0
    per_metre = (lift * area)[band & plateau & (m.lon < 5)].sum() * kg_per_mm_m2 / seconds / length
    return mean(rain, touching), mean(rain, near), mean(rain, far), per_metre


def test_the_rain_before_a_cliff_does_not_depend_on_the_size_of_the_cells():
    """A wall 2.5 km high facing a wind of 6 m/s. The second review measured, on the version before, 6.8, 9.8 and
    14.7 m of rain a year on the sea cells touching the wall at mesh levels 4, 5 and 6: the vapour that could not
    cross piled up in the last cell, however small. Now the air held back spreads over a set reach."""
    numbers = {}
    for level in (4, 5):
        hh = Harness(level=level)
        out, plateau, _ = wall_run(hh, 2500.0)
        numbers[level] = wall_numbers(hh, out, plateau)
        rain = out.fields["precipitation"].astype(np.float64).sum(axis=0)
        evaporation = out.fields["ocean_evaporation"].astype(np.float64).sum(axis=0)
        area = geometry(hh)["cell_area"]
        assert abs((evaporation * area).sum() / (rain * area).sum() - 1) < 1e-4      # all the water that rose came down
    (touch4, near4, far4, lift4), (touch5, near5, far5, lift5) = numbers[4], numbers[5]
    assert abs(touch5 / touch4 - 1) < 0.15 and abs(near5 / near4 - 1) < 0.10       # measured: 4.1 and 4.3 m; 4.1 and 3.9 m
    assert abs(lift5 / lift4 - 1) < 0.15                               # the rain of rising ground per metre of cliff: 8.5 and 9.1 kg/s
    assert 1.5 * far5 < near5 < 3.5 * far5                             # a wet zone before the wall, not a cloudburst (it was 4 to 9 times)


def test_rain_on_rising_ground_follows_the_surface_wind_and_falls_on_the_higher_cell(h):
    """The air pushed up a slope is the air near the ground, so the rule takes the surface wind, not the flow that
    carries the whole column. Here the surface wind only flows toward the wall from both sides, and the carrying flow
    is given no share of such a wind: nothing is carried, yet rain falls on the rising ground, and it equals the
    rule applied by hand to the surface wind."""
    m = h.mesh
    n = m.n
    toward_wall = np.broadcast_to((-4.0 * np.sin(np.deg2rad(m.lon)) * np.cos(np.deg2rad(m.lat)))[:, None] * m.east, (12, n, 3))
    constants = {"carrying_wind": {"share_of_turning_wind": 0.0, "share_of_converging_wind": 0.0}}
    out, plateau, height = wall_run(h, 1500.0, constants=constants, wind=toward_wall)
    lift = out.drivers["precipitation"]["from_rising_ground"].astype(np.float64)[0]
    assert lift[plateau].max() > 5.0 and lift[~plateau].max() == 0.0   # mm a month, on the plateau's edge only
    c = h.constants["Moisture"]
    from worldengine.processes.moisture_one_layer import saturation_vapour_density
    holds = lambda t: saturation_vapour_density(t, c["saturation"])
    t_sea = 298.0
    share = holds(t_sea - 6.5 * 1.5) / holds(t_sea)                     # of a sea-level column, the part above 1,500 m
    water = out.fields["column_water"].astype(np.float64)[0]
    humidity = water / (holds(t_sea) * c["vapour_scale_height_m"])
    out_speed = op.side_speeds(m, toward_wall[0].astype(np.float64))
    nb, has = np.where(m.nbr >= 0, m.nbr, 0), m.nbr >= 0
    uphill = has & ~plateau[:, None] & plateau[nb]
    pushed = c["rising_ground_efficiency"] * np.maximum(out_speed, 0.0) * (m.nbr_dual * R) * (1 - share) * uphill
    area = geometry(h)["cell_area"]
    month_s = 31558150.0 / 12
    by_hand = np.bincount(nb.ravel(), weights=(pushed * (humidity * water)[:, None]).ravel(), minlength=n) / area * month_s
    assert np.allclose(lift, by_hand, rtol=2e-3, atol=1e-3)


@pytest.mark.parametrize("level", [4, 5])
def test_a_planet_without_sea_has_no_vapour_and_no_rain(level):
    """On a planet without sea nothing evaporates, so the air holds nothing and no rain falls. The solver alone does
    not get there: it starts from moist air, and air that holds little water rains very little, so it stopped with
    0.03 kg/m2 still in the air on the preview mesh and 1.3 on the standard mesh, and rained it out (third check).
    A month that nothing feeds is now given its answer outright."""
    hh = Harness(level=level)
    g = geometry(hh)
    n = hh.mesh.n
    out = hh.run("Moisture", reads={"wind": np.broadcast_to(5.0 * hh.mesh.east, (12, n, 3)), "subsidence": np.zeros((12, n)),
                                    "surface_temperature": np.full((12, n), 290.0), "height_above_sea": np.zeros(n),
                                    "ocean_mask": np.zeros(n, dtype=bool), "cell_area": g["cell_area"]})
    for name in ("column_water", "precipitation", "snowfall", "ocean_evaporation"):
        assert out.fields[name].max() == 0.0 and out.fields[name].min() == 0.0, name
    assert (out.drivers["precipitation"]["vapour_came_from"] == -1).all()
    assert out.notices == []


def test_the_rain_law_gives_nothing_in_air_that_holds_no_water_and_never_less_than_nothing(h):
    """The published law alone gives a millimetre a year from air that holds nothing (second review); its value in
    dry air is taken off. With one small sea, most of the planet is nearly dry: no cell may get negative rain."""
    from worldengine.library.transport import rain_from_humidity
    law = h.params["models"]["slots"]["Moisture"]["constants"]["rain_law"]
    assert rain_from_humidity(np.zeros(3), np.ones(3), law["steepness"], law["humidity_at_one_mm_per_day"]).tolist() == [0.0] * 3
    g = geometry(h)
    n = h.mesh.n
    sea = h.mesh.xyz @ h.mesh.xyz[100] > np.cos(np.deg2rad(8.0))                # one sea about 900 km across
    out = h.run("Moisture", reads={"wind": np.broadcast_to(5.0 * h.mesh.east, (12, n, 3)), "subsidence": np.zeros((12, n)),
                                   "surface_temperature": np.full((12, n), 290.0), "height_above_sea": np.where(sea, 0.0, 10.0),
                                   "ocean_mask": sea, "cell_area": g["cell_area"]})
    rain = out.fields["precipitation"].astype(np.float64)
    assert sea.sum() > 5 and rain.min() >= 0.0 and rain.max() > 0.0
    area = g["cell_area"]
    assert abs((out.fields["ocean_evaporation"].astype(np.float64).sum(axis=0) * area).sum() / (rain.sum(axis=0) * area).sum() - 1) < 2e-3


def test_cold_high_ground_does_not_draw_in_vapour_from_the_air_below_it(h):
    """Vapour mixes sideways between air at the same height. A rule that mixes whole columns pumps vapour from low,
    unsaturated neighbours into the thin cold column over high ground, which then holds several times what it can
    and rains without limit (measured before the first fix: 3 times saturation, 72 m of rain a year in one cell)."""
    m = h.mesh
    out, ridge = ridge_run(h, 4000.0)
    c = h.constants["Moisture"]
    from worldengine.processes.moisture_one_layer import saturation_vapour_density
    holds = saturation_vapour_density(292.0 - 6.5 * ridge / 1000.0, c["saturation"]) * c["vapour_scale_height_m"]
    humidity = out.fields["column_water"].astype(np.float64) / holds
    assert humidity.max() < 1.0                                        # no column holds more than it can
    rain = out.fields["precipitation"].astype(np.float64).mean(axis=0)
    high, sea = ridge > 2500.0, ridge == 0.0
    assert high.sum() > 10 and rain[high].mean() < rain[sea].mean()    # the crest is not the wettest place on the planet
    # With still air nothing is carried uphill. Water at any height then fills the air above it to the same humidity,
    # in warm air and in cold: the part of a column that reaches above high ground is what air that cold can hold.
    # (With a fixed thinning of 2.5 km for every temperature, the humidity over a ridge 4 km high in air of 250 K came
    # out 2.4 times the lowland's: second review.)
    g = geometry(h)
    n = m.n
    for at_sea_level in (292.0, 250.0):
        temperature = at_sea_level - 6.5 * ridge / 1000.0
        still = h.run("Moisture", reads={"wind": np.zeros((12, n, 3)), "subsidence": np.zeros((12, n)),
                                         "surface_temperature": np.broadcast_to(temperature, (12, n)),
                                         "height_above_sea": ridge, "ocean_mask": np.ones(n, dtype=bool), "cell_area": g["cell_area"]})
        can_hold = saturation_vapour_density(temperature, c["saturation"]) * c["vapour_scale_height_m"]
        still_humidity = still.fields["column_water"].astype(np.float64)[0] / can_hold
        assert abs(still_humidity[high].mean() / still_humidity[sea].mean() - 1) < 0.02
        assert still_humidity.max() < 1.02 * still_humidity[sea].mean()


def test_evaporation_uses_the_wind_at_the_surface_not_the_slower_wind_that_carries_the_vapour(h):
    """Over an all-sea planet with the same wind everywhere, nothing is carried anywhere: evaporation is the bulk
    formula with the surface wind, whatever the share of that wind that carries the column's vapour."""
    g = geometry(h)
    m = h.mesh
    n = m.n
    reads = {"wind": np.broadcast_to(8.0 * m.east * np.cos(np.deg2rad(m.lat))[:, None], (12, n, 3)), "subsidence": np.zeros((12, n)),
             "surface_temperature": np.full((12, n), 290.0), "height_above_sea": np.zeros(n), "ocean_mask": np.ones(n, dtype=bool),
             "cell_area": g["cell_area"]}
    full = h.run("Moisture", reads=reads, constants={"carrying_wind": {"share_of_turning_wind": 1.0}}).fields["ocean_evaporation"].astype(np.float64)
    half = h.run("Moisture", reads=reads, constants={"carrying_wind": {"share_of_turning_wind": 0.5}}).fields["ocean_evaporation"].astype(np.float64)
    assert np.allclose(full, half, rtol=2e-3)
    gust = h.constants["Moisture"]["gust_m_s"]
    equator, high = np.abs(m.lat) < 10, np.abs(m.lat) > 70
    speed = lambda lat: np.sqrt((8.0 * np.cos(np.deg2rad(lat))) ** 2 + gust ** 2)
    ratio = full[:, equator].mean() / full[:, high].mean()
    assert ratio > 1.25                                                # more evaporation where the surface wind is stronger
    assert ratio < speed(0.0) / speed(80.0)                            # by less than the ratio of the wind speeds: moister air evaporates less


def test_wind_that_flows_toward_a_belt_gathers_rain_there_by_the_share_of_the_column_it_carries(h):
    """A surface wind blowing toward the equator from both sides. The flow toward a rain belt is shallow, so it
    carries a share of the column; a wind that circles the planet carries all of it, and gathers nothing anywhere."""
    g = geometry(h)
    m = h.mesh
    n = m.n
    lat = np.deg2rad(m.lat)
    inflow = np.broadcast_to((-4.0 * np.sin(2 * lat))[:, None] * m.north, (12, n, 3))
    reads = {"wind": inflow, "subsidence": np.zeros((12, n)), "surface_temperature": np.full((12, n), 295.0),
             "height_above_sea": np.zeros(n), "ocean_mask": np.ones(n, dtype=bool), "cell_area": g["cell_area"]}
    def belt_excess(share, wind=inflow):
        out = h.run("Moisture", reads={**reads, "wind": wind}, constants={"carrying_wind": {"share_of_converging_wind": share}})
        rain = out.fields["precipitation"].astype(np.float64)[0]
        return rain[np.abs(m.lat) < 6].mean() - rain[np.abs(np.abs(m.lat) - 45) < 6].mean()
    none = belt_excess(0.0)                    # nothing gathers; what differs is the evaporation, weaker in the calm at the equator
    whole, quarter = belt_excess(1.0) - none, belt_excess(0.25) - none
    assert quarter > 20.0                                              # mm a month gathered at the equator
    assert 3.0 * quarter < whole < 5.5 * quarter                       # about four times as much for the whole column
    circling = np.broadcast_to((6.0 * np.cos(lat))[:, None] * m.east, (12, n, 3))
    assert abs(belt_excess(1.0, circling) - belt_excess(0.0, circling)) < 0.5        # a circling wind has no inflow to share out


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
    ratio = less.fields["precipitation"][0][tropics].mean() / plain[0][tropics].mean()
    assert 0.5 < ratio < 0.9          # less rain under sinking air; not far less, because the moister air also evaporates less
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


def test_sea_is_shown_as_ice_where_the_albedo_rule_lays_ice_on_it(h):
    """The mean temperature of the year below -10 C: the rule Albedo uses, so that the map and the reflected sunlight agree."""
    n = h.mesh.n
    sea = np.ones(n, dtype=bool)
    assert biome_run(h, [-20.0] * 12, [10.0] * 12, sea)[0] == "ice"
    cold_year_mild_summer = [-28, -28, -24, -16, -8, -2, 1, 0, -6, -14, -22, -27]            # mean -14.3 C
    assert biome_run(h, cold_year_mild_summer, [10.0] * 12, sea)[0] == "ice"
    assert biome_run(h, [-8.0] * 12, [10.0] * 12, sea)[0] == "ocean"                         # frozen every month, yet above -10 C
    assert biome_run(h, [-20.0] * 12, [10.0] * 12, sea)[1] == "ocean"                        # the climate class of sea stays "ocean"
    out = biome_run(h, [-20.0] * 12, [10.0] * 12, sea)[2]
    assert set(out.drivers["biome"]["rule"]) == {4} and set(out.drivers["biome"]["limit"]) == {3}


SEASONS = lambda mean, swing: [mean - swing * np.cos(2 * np.pi * (m - 0.5) / 12) for m in range(12)]          # coldest in January


@pytest.mark.parametrize("temps,rain,expected_class,expected_biome", [
    (SEASONS(27, 6), [1.0] * 12, "BWh", "subtropical_desert"),
    (SEASONS(8, 14), [20.0] * 12, "BSk", "temperate_grassland_desert"),
    (SEASONS(16, 8), [100, 90, 70, 40, 20, 5, 2, 5, 25, 60, 90, 110], "Csa", None),          # dry summer, hot summer
    (SEASONS(10, 6), [90.0] * 12, "Cfb", "temperate_seasonal_forest"),
    (SEASONS(-3, 16), [50.0] * 12, "Dfc", "boreal_forest"),
    (SEASONS(-9, 14), [25.0] * 12, "ET", "tundra"),
    (SEASONS(26, 1), [300, 250, 200, 100, 30, 5, 5, 10, 60, 150, 250, 300], "Aw", None),     # a dry season in the tropics
    # Both the dry-summer and the dry-winter rule pass. More rain falls in summer, so the winter is the dry season (Beck et al. 2018).
    (SEASONS(16, 8), [10, 10, 30, 200, 250, 5, 300, 250, 200, 30, 10, 10], "Cwa", None),
    # Both rules pass again, with more rain in winter: the summer is the dry season.
    (SEASONS(16, 8), [100, 100, 0.3, 5, 5, 2, 5, 5, 5, 100, 100, 100], "Csa", None),
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
