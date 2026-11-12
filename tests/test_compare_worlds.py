"""tools/compare_worlds.py: how far apart two worlds are, field by field; and the job of the workflow
.github/workflows/local-run.yml that runs it on the worlds of the systems.

The worlds here run the setup and geological stages only, over a history of 8 My on the preview mesh, with a uniform
runoff in place of the climate (as tests/test_history.py builds them), so that one builds in seconds. The world is
built twice: two builds on one machine must be the same bit for bit, and the tool must say so. Then copies of it
are changed by hand, and the tool must report each change with the right numbers and the right verdict."""
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest
import yaml
import zarr

from conftest import DATA, ROOT, tool
from worldengine import store
from worldengine.engine import Engine

cw = tool("compare_worlds")
GEOLOGY = ("PlanetGeometry", "Tectonics", "Isostasy", "Lithology", "FluvialErosion", "SeaLevel", "Drainage", "SurfaceAge")
WORKFLOW = ROOT / ".github" / "workflows" / "local-run.yml"


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


def _cut_rows(group, keep):
    """Keep the rows `keep` (indices, in that order) of every column of a stored table."""
    for col in list(group.array_keys()):
        kept = group[col][...][keep]
        del group[col]
        group.create_array(name=col, shape=kept.shape, dtype=kept.dtype)[...] = kept


def test_two_builds_of_the_same_world_on_one_machine_are_identical(built, tmp_path, capsys):
    a, b = built
    result = cw.compare(a, b)
    assert result["verdict"] == "identical", result["verdict_text"]
    c = result["counts"]
    assert c["fields"] == c["fields_identical"] > 0 and c["fields_beyond_rounding"] == c["fields_beyond_noise"] == 0
    assert c["tables"] == c["tables_identical"] > 0 and c["mesh_arrays"] == c["mesh_arrays_identical"] == len(cw.MESH)
    assert all(t["rows_only_in_a"] == t["rows_only_in_b"] == 0 for t in result["tables"].values())
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
    assert f["largest_relative"] == pytest.approx(expected / span) and f["range"] == pytest.approx(span)
    assert f["cells_beyond_rounding"] == f["cells_beyond_noise"] == 3 and f["cells"] == len(e)
    assert f["share_cells_beyond_noise"] == pytest.approx(3 / len(e))
    d = result["fields"]["sea_depth"]
    assert not d["identical"] and d["cells_beyond_rounding"] == 0 and d["cells_beyond_noise"] == 0   # a last bit is rounding
    assert result["counts"]["fields_identical"] == result["counts"]["fields"] - 2
    assert result["counts"]["fields_beyond_rounding"] == 1 and result["counts"]["fields_beyond_noise"] == 0
    assert result["counts"]["largest_relative_field"] == "elevation"
    assert result["verdict"] == "same planet with rounding noise", result["verdict_text"]            # three cells are a few
    assert "elevation" in cw.text(result) and "sea_depth" in cw.text(result)

    many = e.copy()
    many[:200] += np.float32(50.0)                          # 200 of 10,242 cells is more than a few
    root["fields/elevation"][...] = many
    result = cw.compare(built[0], path)
    assert result["fields"]["elevation"]["cells_beyond_noise"] == 200
    assert result["verdict"] == "same planet with grown differences" and "elevation" in result["verdict_text"]

    small = e.copy()
    small[:200] += np.float32(0.5e-3 * span)                # on as many cells, but half the noise threshold: still noise
    root["fields/elevation"][...] = small
    result = cw.compare(built[0], path)
    f = result["fields"]["elevation"]
    assert f["cells_beyond_rounding"] == 200 and f["cells_beyond_noise"] == 0
    assert result["verdict"] == "same planet with rounding noise", result["verdict_text"]


def test_flipped_ocean_cells_make_a_different_planet(built, copy):
    root, path = copy
    sea = root["fields/ocean_mask"][...]
    few = sea.copy()
    few[:5] = 1 - few[:5]                                   # five cells of coast the other way: still the same planet
    root["fields/ocean_mask"][...] = few
    result = cw.compare(built[0], path)
    assert result["fields"]["ocean_mask"]["cells_differing"] == 5
    assert result["verdict"] == "same planet with rounding noise" and "ocean_mask differs on 5 cells" in result["verdict_text"]

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


def test_tables_are_compared_by_their_rows_and_key_columns(built, copy):
    root, path = copy
    seas = root["tables/seas"]
    seas["surface_m"][...] = seas["surface_m"][...] + 100.0
    hollows = root["tables/hollows"]
    rows = hollows["parent"].shape[0]
    _cut_rows(hollows, np.arange(rows - 1))
    result = cw.compare(built[0], path)
    h = result["tables"]["hollows"]
    assert h["rows"] == [rows, rows - 1] and h["rows_matched"] == rows - 1 and h["key"] == ["bottom_cell"]
    assert h["rows_only_in_a"] == 1 and h["rows_only_in_b"] == 0 and all(c["identical"] for c in h["columns"].values())
    assert result["tables"]["seas"]["columns"]["surface_m"]["largest_absolute"] == pytest.approx(100.0)
    assert result["tables"]["plates"]["identical"]
    assert result["verdict"] == "same planet with grown differences"
    assert f"hollows ({rows} and {rows - 1} rows, {rows - 1} matched)" in result["verdict_text"]
    lines = cw.table_lines(result)
    assert f"hollows: {rows} and {rows - 1} rows; {rows - 1} matched by bottom_cell, 1 in A only, 0 in B only" in lines
    assert any(line.startswith("seas: 1 row in each, matched by lowest_cell; 1 of 5 columns differ") for line in lines)

    plates = root["tables/plates"]
    _cut_rows(plates, np.arange(plates["plate"].shape[0] - 1))
    result = cw.compare(built[0], path)
    assert result["verdict"] == "different planet" and "plates" in result["verdict_text"]   # a plate fewer is another planet


def test_rows_are_matched_by_their_key_not_by_their_place(built, copy):
    """A hollow missing from the middle of the table (the small world has no lakes: it has no climate): the hollows
    after it are matched to themselves by the cell at their bottom, so the columns of the matched rows are the same
    bit for bit. The same hollows in another order are the same rows, and the same numbers, though not the same
    bytes. A table without a key is matched row by row."""
    root, path = copy
    hollows = store.StoreView(built[0]).table("hollows")
    bottoms = list(hollows["bottom_cell"])
    n = len(bottoms)
    gone = next((i for i in range(1, n - 1) if bottoms.count(bottoms[i]) == 1), None)
    assert gone is not None, "the small world has no hollow in the middle of its table whose bottom is its own"
    _cut_rows(root["tables/hollows"], np.r_[0:gone, gone + 1:n])
    result = cw.compare(built[0], path)
    t = result["tables"]["hollows"]
    assert t["rows"] == [n, n - 1] and t["rows_matched"] == n - 1 and not t["same_rows"]
    assert t["rows_only_in_a"] == 1 and t["rows_only_in_b"] == 0
    assert all(c["identical"] for c in t["columns"].values()), [c for c, v in t["columns"].items() if not v["identical"]]
    assert result["verdict"] == "same planet with grown differences" and "hollows (" in result["verdict_text"]

    plates = store.StoreView(built[0]).table("plates")
    turned = cw.compare_table("plates", plates, {c: a[::-1] for c, a in plates.items()})
    assert turned["same_rows"] and turned["rows_matched"] == len(plates["plate"]) > 1 and not turned["identical"]
    assert all(c["identical"] for c in turned["columns"].values())

    points = cw.compare_table("crust_points", {"x": np.arange(5.0)}, {"x": np.arange(5.0)[::-1]})
    assert points["key"] is None and points["same_rows"] and points["columns"]["x"]["share_cells_beyond_noise"] == pytest.approx(0.8)
    unequal = cw.compare_table("crust_points", {"x": np.arange(5.0)}, {"x": np.arange(4.0)})
    assert unequal["rows_matched"] == 0 and unequal["columns"] == {} and not unequal["same_rows"]


def test_cells_and_cell_months_are_counted_apart():
    """A field with one slice per month: a cell counts once however many of its months differ; a direction counts
    once however many of its components."""
    a = np.linspace(0.0, 100.0, 12 * 50, dtype=np.float32).reshape(12, 50)
    b = a.copy()
    b[0, 5] += 10.0
    b[3, 5] += 10.0
    b[7, 9] += 10.0
    r = cw.compare_array(a, b, categorical=False, time="month")
    assert r["cells_beyond_rounding"] == 2 and r["cell_months_beyond_rounding"] == 3 and r["cells"] == 50
    assert r["share_cell_months_beyond_rounding"] == pytest.approx(3 / 600) and r["share_cells_beyond_rounding"] == pytest.approx(2 / 50)
    assert r["largest_absolute"] == pytest.approx(10.0, abs=1e-4) and r["range"] == pytest.approx(100.0)
    assert cw.compare_array(a, b, categorical=False)["cells"] == 12          # without the months, the first axis is the cells
    w = np.zeros((12, 50, 3), dtype=np.float32)
    v = w.copy()
    v[2, 4, :] = 5.0                                        # every component of one cell
    v[2, 7, 2] = 5.0                                        # the last component alone of another
    r = cw.compare_array(w, v, categorical=False, time="month")
    assert r["cells_beyond_rounding"] == 2 and r["cell_months_beyond_rounding"] == 2
    r = cw.compare_array(w[0], v[2], categorical=False)                      # a direction of one time: (cells, 3)
    assert r["cells"] == 50 and r["cells_beyond_rounding"] == 2
    c = np.zeros(50, dtype=np.int16)
    d = c.copy()
    d[[1, 2]] = 4
    r = cw.compare_array(c, d, categorical=True)
    assert r["kind"] == "category" and r["cells_differing"] == 2 and "largest_absolute" not in r
    r = cw.compare_array(np.zeros((3, 50), np.int16), np.ones((3, 50), np.int16), categorical=True, time="day")
    assert r["cells_differing"] == 50 and r["cell_days_differing"] == 150
    n = np.full(4, 1.0, dtype=np.float32)
    m = n.copy()
    m[1] = np.nan                                           # a value missing in one world is a difference beyond rounding
    r = cw.compare_array(n, m, categorical=False)
    assert r["missing_in_one"] == 1 and r["cells_beyond_rounding"] == 1 and r["cells_beyond_noise"] == 1
    r = cw.compare_array(np.array([np.nan, 2.0]), np.array([np.nan, 2.0]), categorical=False)
    assert r["identical"] and r["cells_beyond_rounding"] == 0
    x = np.array([1.5, 3000.0], dtype=np.float64)             # a float64 is held to the rounding of a float32
    unit = np.spacing(x.astype(np.float32)).astype(np.float64)
    r = cw.compare_array(x, x + 0.9 * unit, categorical=False)
    assert not r["identical"] and r["cells_beyond_rounding"] == 0
    r = cw.compare_array(x, x + np.array([0.5, 1.5]) * unit, categorical=False)
    assert r["cells_beyond_rounding"] == 1 and r["largest_absolute"] == pytest.approx(1.5 * unit[1])


def test_a_store_that_is_missing_or_is_no_store_ends_the_run_with_2(built, tmp_path, capsys):
    assert cw.main([str(built[0]), "no_such.zarr"]) == 2
    assert "no world store at no_such.zarr" in capsys.readouterr().err
    (tmp_path / "empty").mkdir()
    assert cw.main([str(built[0]), str(tmp_path / "empty")]) == 2
    assert "the stores could not be compared" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------- the workflow's job
def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step(job, name_start):
    return next(s for s in job["steps"] if s.get("name", "").startswith(name_start))


def _heredoc(run):
    """The Python of a step that runs `python - <<'EOF' ... EOF`."""
    lines = run.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith("<<'EOF'"))
    return "\n".join(lines[start + 1:lines.index("EOF", start)])


def test_every_system_uploads_its_world_and_the_last_job_compares_each_with_ubuntus():
    jobs = _workflow()["jobs"]
    native = jobs["native"]["steps"]
    zip_step = _step(jobs["native"], "The world itself, in one zip file")
    assert "make_archive" in zip_step["run"] and "first.zarr" in zip_step["run"]
    uploads = {s["with"]["name"]: s["with"]["path"] for s in [*native, *jobs["docker"]["steps"]]
               if s.get("uses", "").startswith("actions/upload-artifact")}
    assert uploads["world-${{ matrix.os }}"] == "world-${{ matrix.os }}.zip" and uploads["world-docker"] == "world-docker.zip"
    assert "fingerprint-${{ matrix.os }}" in uploads and "fingerprint-docker" in uploads          # the fingerprints are kept
    assert "make_archive(\"/out/world-docker\"" in _step(jobs["docker"], "The world's fingerprints in the container")["run"]
    compare = jobs["compare"]
    assert set(compare["needs"]) == {"native", "docker"}
    downloads = [s["with"]["pattern"] for s in compare["steps"] if s.get("uses", "").startswith("actions/download-artifact")]
    assert downloads == ["fingerprint-*", "world-*"]
    assert "Which fields are the same, bit for bit" in " ".join(s.get("name", "") for s in compare["steps"])
    assert any(s.get("uses", "").startswith("actions/upload-artifact") and s["with"]["name"] == "world-comparisons"
               for s in compare["steps"])


def test_the_workflows_comparison_runs_the_tool_on_each_world_and_fails_only_when_the_tool_does(built, copy, tmp_path):
    """The native job's zip command and the compare job's script, taken out of the workflow and run here on the
    small world: as built twice ("ubuntu-latest" and "docker") and changed ("macos-latest")."""
    root, changed = copy
    e = root["fields/elevation"][...]
    root["fields/elevation"][...] = e + np.float32(50.0)              # more than a thousandth of the range, everywhere
    jobs = _workflow()["jobs"]
    zip_code = re.search(r'-c "([^"]+)"', _step(jobs["native"], "The world itself, in one zip file")["run"]).group(1)
    script = _heredoc(_step(jobs["compare"], "How far the worlds differ")["run"])
    script = script.replace("engine/tools/compare_worlds.py", (ROOT / "tools" / "compare_worlds.py").as_posix())  # no \ in a literal
    work = tmp_path / "job"
    (work / "worlds").mkdir(parents=True)
    for system, world in (("ubuntu-latest", built[0]), ("docker", built[1]), ("macos-latest", changed)):
        side = tmp_path / system
        shutil.copytree(world, side / "worlds" / "first.zarr")
        done = subprocess.run([sys.executable, "-c", zip_code, str(work / "worlds" / f"world-{system}")], cwd=side)
        assert done.returncode == 0
    summary = work / "summary.md"
    env = {**os.environ, "GITHUB_STEP_SUMMARY": str(summary), "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run([sys.executable, "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    said = summary.read_text(encoding="utf-8")
    assert "| docker | identical |" in said
    assert "| macos-latest | same planet with grown differences |" in said and "elevation" in said
    result = json.loads((work / "comparisons" / "macos-latest.json").read_text(encoding="utf-8"))
    assert result["fields"]["elevation"]["cells_beyond_rounding"] == len(e)
    assert sorted(p.name for p in (work / "comparisons").iterdir()) == ["details.md", "docker.json", "macos-latest.json"]

    (work / "worlds" / "world-windows-latest.zip").write_bytes((work / "worlds" / "world-docker.zip").read_bytes()[:1000])
    done = subprocess.run([sys.executable, "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode != 0 and "compare_worlds.py failed for: windows-latest" in done.stderr   # the tool's failure fails the job
    assert "| windows-latest | the tool failed (exit 2) |" in summary.read_text(encoding="utf-8")
