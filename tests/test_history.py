"""The geological history of build step 3: snapshots, continuing a stored history, and the known answers of the plate
history, Lithology and SurfaceAge (docs/step3/TASKS.md, T1 to T4). The worlds here run the setup and geological stages
only, so that a history of a few rounds builds in seconds."""
import copy

import numpy as np
import pytest
import yaml

from conftest import DATA
from worldengine import store
from worldengine.engine import Engine, EngineError
from worldengine.server import WorldService
from worldengine.testing import Harness

GEOLOGY = ("PlanetGeometry", "Tectonics", "Isostasy", "Lithology", "FluvialErosion", "SeaLevel", "Drainage", "SurfaceAge")


def text(name):
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


def geology_engine(history_my, seed=None, every=2):
    """The default world's setup and geological stages, with a history of the given length and a picture every
    `every` rounds."""
    models = text("models.yaml")
    models["slots"] = {k: v for k, v in models["slots"].items() if k in GEOLOGY}
    models["slots"]["Runoff"] = {"implementation": "toy_processes:UniformRunoff", "standing": "Test", "model": "uniform runoff",
                                 "ignores": "the climate", "wrong_where": "everywhere", "writes": ["runoff_annual"],
                                 "constants": {"mm_per_year": 300.0}}
    stages = text("stages.yaml")
    for s in stages["stages"]:
        if s["clock"] == "geological":
            s["history_length_my"] = float(history_my)
    profiles = text("profiles.yaml")
    profiles["profiles"]["preview"]["snapshot_every_rounds"] = every
    return Engine(DATA, profile="preview", seed=seed, overrides={"models": models, "stages": stages, "profiles": profiles})


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    """A history of 8 My kept, one of 16 My continued from it, and one of 16 My in one run."""
    d = tmp_path_factory.mktemp("history")
    e8 = geology_engine(8)
    w8 = e8.build()
    store.save(w8, e8, d / "a8.zarr")
    e16 = geology_engine(16)
    w16c = e16.build(continue_from=store.StoreView(d / "a8.zarr"))
    store.save(w16c, e16, d / "b16.zarr")
    e16b = geology_engine(16)
    w16 = e16b.build()
    store.save(w16, e16b, d / "c16.zarr")
    return d, w8, w16c, w16


def test_a_history_continued_from_a_stored_world_equals_one_run_of_the_same_length(stores):
    """The design's condition for step 3, here at 8 then 16 My (the notes measured it at 20 then 40 My on the whole
    engine): every field and every table column is the same, bit for bit."""
    _, _, continued, whole = stores
    assert continued.fingerprints() == whole.fingerprints()
    assert continued.rounds_used["geological"] == whole.rounds_used["geological"] == 8


def test_a_world_stopped_early_is_a_moment_inside_a_longer_history(stores):
    """The land of a world stopped at 8 My equals, bit for bit, the picture at 8 My kept inside the run of 16 My."""
    _, early, _, whole = stores
    at = [s["round"] for s in whole.snapshots].index(4)
    for field, picture in whole.snapshots[at]["fields"].items():
        assert np.array_equal(early.fields[field], picture), field


def test_the_store_keeps_the_pictures_of_the_history_and_the_server_hands_them_out(stores):
    d, _, continued, whole = stores
    view = store.StoreView(d / "c16.zarr")
    h = view.history()
    assert h["rounds"] == [2, 4, 6, 8] and h["times_my"] == [4.0, 8.0, 12.0, 16.0]
    assert h["fields"] == ["crust_type", "elevation", "ocean_mask", "plate_id"]
    assert np.array_equal(view.history_field("elevation")[-1], whole.fields["elevation"])
    assert store.StoreView(d / "b16.zarr").history() == h                 # a continued history keeps the pictures before it
    service = WorldService(view)
    assert service.world()["history"] == h
    assert np.array_equal(np.frombuffer(service.history_field("elevation", 0), dtype="<f4"),
                          whole.snapshots[0]["fields"]["elevation"].astype("<f4"))
    with pytest.raises(KeyError, match="the history holds no pictures of biome"):
        service.history_field("biome", 0)
    with pytest.raises(IndexError, match="picture 9 is outside 0 to 3"):
        service.history_field("elevation", 9)


def test_a_history_is_continued_only_from_its_own_seed_and_mesh_and_only_forward(stores):
    d, _, _, _ = stores
    stored = store.StoreView(d / "a8.zarr")
    with pytest.raises(EngineError, match="a history can be continued only with the seed and the mesh level of the stored world"):
        geology_engine(16, seed=7).build(continue_from=stored)
    with pytest.raises(EngineError, match="the stored world has run 4 rounds of geological; asked to stop after 2"):
        geology_engine(4).build(continue_from=stored)


def test_a_store_without_the_state_of_its_history_cannot_be_continued(tmp_path, stores):
    d, _, _, _ = stores
    import shutil
    import zarr
    shutil.copytree(d / "a8.zarr", tmp_path / "old.zarr")
    root = zarr.open_group(store=str(tmp_path / "old.zarr"), mode="a")
    del root["carry"]
    with pytest.raises(KeyError, match="holds no state of its geological history to continue from"):
        geology_engine(16).build(continue_from=store.StoreView(tmp_path / "old.zarr"))


# ------------------------------------------------------------------------------------------ the plate history alone
def two_plates_apart(h):
    """Two ocean plates, north and south of the equator, turning apart about an axis in the equator."""
    m = h.mesh
    plate = np.where(m.lat >= 0, 0, 1).astype(np.int32)
    n = m.n
    zero, none = np.zeros(n, dtype=np.float32), np.full(n, -1, dtype=np.int32)
    points = {"plate": plate, "x": m.xyz[:, 0], "y": m.xyz[:, 1], "z": m.xyz[:, 2], "crust_type": np.zeros(n, dtype=np.int16),
              "thickness_m": np.full(n, 7000.0), "ocean_age_my": np.full(n, 50.0), "orogeny_age_my": np.full(n, np.nan),
              "thickened_by_plates_m": zero, "removed_by_erosion_m": zero, "formed_m": np.full(n, 7000.0), "last_event": none,
              "source_a": none, "source_b": none, "source_c": none, "weight_a": zero, "weight_b": zero, "weight_c": zero}
    speed = 0.01                                                       # radians per My, 6.4 cm a year at the widest circle
    plates = {"plate": [0, 1], "axis_x": [0.0, 0.0], "axis_y": [-1.0, 1.0], "axis_z": [0.0, 0.0],
              "angular_speed_rad_per_my": [speed, speed], "area_m2": [1.0, 1.0], "continental_share": [0.0, 0.0],
              "carries_continent": [False, False], "centre_x": [0.0, 0.0], "centre_y": [0.0, 0.0], "centre_z": [1.0, -1.0]}
    events = {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []}
    return {"crust_points": points, "plates": plates, "tectonic_events": events}


def test_two_plates_moving_apart_make_new_floor_youngest_where_they_part():
    """The design's known answer for Tectonics: plates set to move apart make new floor between them, youngest along
    the line where they part. Two rounds of the plate history, with no rifting (its chance set to zero)."""
    h = Harness(level=5)
    g = h.run("PlanetGeometry").fields
    tables = two_plates_apart(h)
    no_rift = {"rifting": {"rate_per_round": 0.0}}
    for r in (1, 2):
        out = h.run("Tectonics", reads={"cell_area": g["cell_area"]}, lagged_tables=tables, constants=no_rift, round_no=r,
                    groups={"crust_thickness_tendency": {}})
        tables = {k: dict(v) for k, v in out.tables.items()}
    age = out.fields["ocean_crust_age"]
    m = h.mesh
    young = age < 4.0
    assert young.sum() > 10
    meridian = np.abs(m.lon) < 60                                      # where the two plates' motions part fastest
    assert np.all(np.abs(m.lat[young & meridian]) < 8.0)               # new floor lies along the equator, where they part
    near = meridian & (np.abs(m.lat) < 2.0)
    far = meridian & (np.abs(m.lat) > 20.0)
    assert age[near].mean() < age[far].mean()                          # youngest along the line, older away from it
    kinds = h.registry.fields["boundary_kind"].categories
    assert (out.fields["boundary_kind"][near] == kinds.index("ridge")).mean() > 0.5


# ------------------------------------------------------------------------------------------ Lithology and SurfaceAge
@pytest.mark.parametrize("row", range(6))
def test_each_row_of_the_rock_table_fed_its_setting_returns_its_rock(row):
    """One test per row of the rule table (docs/step3/TASKS.md, T4): a setting built to trigger the row returns its rock
    family and erodibility."""
    h = Harness(level=3)
    n = h.mesh.n
    rules = h.params["models"]["slots"]["Lithology"]["constants"]["rules"]
    rule = rules[row]
    kinds = h.registry.fields["boundary_kind"].categories
    crust = np.full(n, 0 if rule.get("crust") == "oceanic" else 1, dtype=np.int16)
    orogeny = np.full(n, rule["orogeny_younger_than_my"] / 2 if "orogeny_younger_than_my" in rule else np.nan)
    volcanism = np.full(n, rule["volcanism_above"] + 0.1 if "volcanism_above" in rule else 0.0)
    boundary = np.full(n, kinds.index(rule["boundary"][0]) if "boundary" in rule else kinds.index("none"), dtype=np.int16)
    if row == len(rules) - 1:
        orogeny[:] = np.nan                                            # the last row: no setting of the rows before it
    out = h.run("Lithology", reads={"crust_type": crust, "orogeny_age": orogeny, "volcanism": volcanism, "boundary_kind": boundary})
    rocks = h.registry.fields["rock_type"].categories
    assert np.all(out.fields["rock_type"] == rocks.index(rule["rock"]))
    assert np.all(out.fields["erodibility"] == rule["erodibility"])
    assert np.all(out.drivers["rock_type"]["rule"] == row)


def test_surface_age_grows_and_resets_under_lava_deep_erosion_and_where_land_rises_from_the_sea():
    """The design's known answers for SurfaceAge: age resets to zero where lava covers the ground, where erosion cuts
    deep and where land rises from the sea; elsewhere it grows by one step each round; new floor starts at zero."""
    h = Harness(level=3)
    m = h.mesh
    n = m.n
    c = h.params["models"]["slots"]["SurfaceAge"]["constants"]
    rows = np.arange(n, dtype=np.int32)
    none, ones, zeros = np.full(n, -1, dtype=np.int32), np.ones(n, dtype=np.float32), np.zeros(n, dtype=np.float32)
    points = {"plate": np.zeros(n, dtype=np.int32), "x": m.xyz[:, 0], "y": m.xyz[:, 1], "z": m.xyz[:, 2],
              "crust_type": np.ones(n, dtype=np.int16), "thickness_m": np.full(n, 35000.0, dtype=np.float32),
              "ocean_age_my": np.full(n, np.nan), "orogeny_age_my": np.full(n, np.nan), "thickened_by_plates_m": zeros,
              "removed_by_erosion_m": zeros, "formed_m": zeros, "last_event": none,
              "source_a": np.where(rows == 0, -1, rows).astype(np.int32), "source_b": none, "source_c": none,
              "weight_a": np.where(rows == 0, 0.0, 1.0).astype(np.float32), "weight_b": zeros, "weight_c": zeros}
    old = {"age_my": np.full(n, 10.0), "was_sea": rows == 3}
    volcanism, erosion, sea = np.zeros(n), np.zeros(n), np.zeros(n, dtype=bool)
    volcanism[1] = c["lava_above"] + 0.1
    erosion[2] = 1.5 * c["deep_erosion_m_per_round"] / 2000.0            # mm/yr: 1.5 times the depth over a round of 2 My
    out = h.run("SurfaceAge", reads={"erosion_rate": erosion, "volcanism": volcanism, "ocean_mask": sea},
                tables={"crust_points": points}, lagged_tables={"surface_age_points": old})
    age = out.tables["surface_age_points"]["age_my"]
    assert age[0] == 0.0 and age[1] == 0.0 and age[2] == 0.0 and age[3] == 0.0     # new floor, lava, deep erosion, risen land
    assert np.all(age[4:] == 12.0)                                                  # elsewhere one step older
    assert list(out.drivers["surface_age"]["renewed_by"][:4]) == [1, 2, 3, 4]
