"""tools/compare_worlds.py: how far apart two worlds are, field by field.

The worlds here run the setup and geological stages only, over a history of 8 My on the preview mesh, with a uniform
runoff in place of the climate (as tests/test_history.py builds them), so that one builds in seconds. The world is
built twice: two builds on one machine must be the same bit for bit, and the tool must say so. Then copies of it
are changed by hand, and the tool must report each change with the right numbers and the right verdict."""
import json
import shutil

import numpy as np
import pytest
import yaml
import zarr

from conftest import DATA, tool
from worldengine import store
from worldengine.engine import Engine

cw = tool("compare_worlds")
GEOLOGY = ("PlanetGeometry", "Tectonics", "Isostasy", "Lithology", "FluvialErosion", "SeaLevel", "Drainage", "SurfaceAge")


def _text(name):
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


def _geology_world(path):
    models = _text("models.yaml")
    models["slots"] = {k: v for k, v in models["slots"].items() if k in GEOLOGY}
    models["slots"]["Runoff"] = {"implementation": "toy_processes:UniformRunoff", "standing": "Test", "model": "uniform runoff",
                                 "ignores": "the climate", "wrong_where": "everywhere", "writes": ["runoff_annual"],
                                 "constants": {"mm_per_year": 300.0}}
    stages = _text("stages.yaml")
    for s in stages["stages"]:
        if s["clock"] == "geological":
            s["history_length_my"] = 8.0
    e = Engine(DATA, profile="preview", overrides={"models": models, "stages": stages})
    return store.save(e.build(), e, path)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("compare")
    return _geology_world(d / "a.zarr"), _geology_world(d / "b.zarr")


@pytest.fixture
def copy(built, tmp_path):
    """A copy of the world, open for writing (a store is never changed otherwise), and its path."""
    target = tmp_path / "changed.zarr"
    shutil.copytree(built[0], target)
    return zarr.open_group(store=str(target), mode="r+"), target


def test_two_builds_of_the_same_world_on_one_machine_are_identical(built, tmp_path, capsys):
    a, b = built
    result = cw.compare(a, b)
    assert result["verdict"] == "identical", result["verdict_text"]
    assert result["counts"]["fields"] == result["counts"]["fields_identical"] > 0
    assert result["counts"]["tables"] == result["counts"]["tables_identical"] > 0
    out = tmp_path / "same.json"
    assert cw.main([str(a), str(b), "--json", str(out), "--markdown", str(tmp_path / "same.md")]) == 0
    assert "Verdict: identical" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "identical"
    assert "**identical:" in (tmp_path / "same.md").read_text(encoding="utf-8")


def test_a_perturbed_field_is_reported_with_its_numbers(built, copy):
    root, path = copy
    e = root["fields/elevation"][...]
    span = float(e.max() - e.min())
    cells = [10, 500, 2000]
    changed = e.copy()
    changed[cells] += np.float32(50.0)                       # 50 m is more than a thousandth of the range of heights
    root["fields/elevation"][...] = changed
    expected = float(np.abs(changed.astype(np.float64) - e.astype(np.float64)).max())
    h = root["fields/sea_depth"][...]
    root["fields/sea_depth"][...] = np.nextafter(h, np.float32(np.inf))   # one unit in the last place, everywhere
    result = cw.compare(built[0], path)
    f = result["fields"]["elevation"]
    assert f["kind"] == "number" and not f["identical"]
    assert f["largest_absolute"] == pytest.approx(expected) and expected == pytest.approx(50.0, abs=0.01)
    assert f["largest_relative"] == pytest.approx(expected / span)
    assert f["cells_beyond_rounding"] == f["cells_beyond_noise"] == 3 and f["cells"] == len(e)
    assert f["share_cells_beyond_noise"] == pytest.approx(3 / len(e))
    d = result["fields"]["sea_depth"]
    assert not d["identical"] and d["cells_beyond_rounding"] == 0 and d["cells_beyond_noise"] == 0   # a last bit is rounding
    assert result["verdict"] == "rounding noise", result["verdict_text"]                          # three cells are a few
    assert "elevation" in cw.text(result) and "sea_depth" in cw.text(result)

    many = e.copy()
    many[:200] += np.float32(50.0)                          # 200 of 10,242 cells is more than a few
    root["fields/elevation"][...] = many
    result = cw.compare(built[0], path)
    assert result["fields"]["elevation"]["cells_beyond_noise"] == 200
    assert result["verdict"] == "grown differences" and "elevation" in result["verdict_text"]


def test_flipped_ocean_cells_make_a_different_planet(built, copy):
    root, path = copy
    sea = root["fields/ocean_mask"][...]
    few = sea.copy()
    few[:5] = 1 - few[:5]                                   # five cells of coast the other way: still the same planet
    root["fields/ocean_mask"][...] = few
    result = cw.compare(built[0], path)
    assert result["fields"]["ocean_mask"]["cells_differing"] == 5
    assert result["verdict"] in ("rounding noise", "grown differences") and "ocean_mask differs on 5 cells" in result["verdict_text"]

    many = sea.copy()
    many[::50] = 1 - many[::50]
    root["fields/ocean_mask"][...] = many
    flipped = len(sea[::50])
    result = cw.compare(built[0], path)
    f = result["fields"]["ocean_mask"]
    assert f["kind"] == "category" and f["cells_differing"] == flipped
    assert f["share_cells_differing"] == pytest.approx(flipped / len(sea))
    assert result["verdict"] == "different planet"
    assert f"ocean_mask differs on {flipped} of {len(sea)} cells" in result["verdict_text"]


def test_tables_are_compared_by_their_rows_and_columns(built, copy):
    root, path = copy
    seas = root["tables/seas"]
    seas["surface_m"][...] = seas["surface_m"][...] + 100.0
    hollows = root["tables/hollows"]
    rows = hollows["parent"].shape[0]
    for col in list(hollows.array_keys()):
        kept = hollows[col][...][:-1]
        del hollows[col]
        hollows.create_array(name=col, shape=kept.shape, dtype=kept.dtype)[...] = kept
    result = cw.compare(built[0], path)
    assert result["tables"]["hollows"]["rows"] == [rows, rows - 1]
    assert result["tables"]["seas"]["columns"]["surface_m"]["largest_absolute"] == pytest.approx(100.0)
    assert result["tables"]["plates"]["identical"]
    assert result["verdict"] == "grown differences" and f"hollows ({rows} and {rows - 1} rows)" in result["verdict_text"]
    lines = cw.table_lines(result)
    assert f"hollows: {rows} and {rows - 1} rows" in lines and any(line.startswith("seas: ") for line in lines)

    plates = root["tables/plates"]
    for col in list(plates.array_keys()):
        kept = plates[col][...][:-1]
        del plates[col]
        plates.create_array(name=col, shape=kept.shape, dtype=kept.dtype)[...] = kept
    assert cw.compare(built[0], path)["verdict"] == "different planet"                 # a plate fewer is another planet


def test_cells_and_cell_months_are_counted_apart():
    """A field with one slice per month: a cell counts once however many of its months differ; a direction counts
    once however many of its components."""
    a = np.linspace(0.0, 100.0, 12 * 50, dtype=np.float32).reshape(12, 50)
    b = a.copy()
    b[0, 5] += 10.0
    b[3, 5] += 10.0
    b[7, 9] += 10.0
    r = cw.compare_array(a, b, categorical=False, months_first=True)
    assert r["cells_beyond_rounding"] == 2 and r["cell_months_beyond_rounding"] == 3
    assert r["share_cell_months_beyond_rounding"] == pytest.approx(3 / 600) and r["share_cells_beyond_rounding"] == pytest.approx(2 / 50)
    assert r["largest_absolute"] == pytest.approx(10.0, abs=1e-4) and r["range"] == pytest.approx(100.0)
    w = np.zeros((12, 50, 3), dtype=np.float32)
    v = w.copy()
    v[2, 4, :] = 5.0
    r = cw.compare_array(w, v, categorical=False, months_first=True)
    assert r["cells_beyond_rounding"] == 1 and r["cell_months_beyond_rounding"] == 1
    c = np.zeros(50, dtype=np.int16)
    d = c.copy()
    d[[1, 2]] = 4
    r = cw.compare_array(c, d, categorical=True)
    assert r["kind"] == "category" and r["cells_differing"] == 2 and "largest_absolute" not in r
    n = np.full(4, 1.0, dtype=np.float32)
    m = n.copy()
    m[1] = np.nan                                           # a value missing in one world is a difference beyond rounding
    r = cw.compare_array(n, m, categorical=False)
    assert r["missing_in_one"] == 1 and r["cells_beyond_rounding"] == 1 and r["cells_beyond_noise"] == 1


def test_a_store_that_is_missing_ends_the_run_with_2(built, capsys):
    assert cw.main([str(built[0]), "no_such.zarr"]) == 2
    assert "no world store at no_such.zarr" in capsys.readouterr().err
