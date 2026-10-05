"""The world store and the local server (build step 0): a world holding only geometry is identical on a
second run and opens in the viewer through the local server."""
import http.client
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
import yaml

import toy_processes as T
from conftest import DATA
from test_engine_cases import BOOL_TABLE, GEO_FIELDS, engine, slot
from worldengine import store
from worldengine.engine import Engine
from worldengine.server import WorldService, make_server


def geometry_only():
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    models["slots"] = {"PlanetGeometry": models["slots"]["PlanetGeometry"]}
    return Engine(DATA, profile="preview", overrides={"models": models, "interventions": []})


@pytest.fixture(scope="module")
def geometry_store(tmp_path_factory):
    e = geometry_only()
    w = e.build()
    path = tmp_path_factory.mktemp("worlds") / "geometry.zarr"
    store.save(w, e, path)
    return e, w, path


def test_geometry_world_is_identical_on_a_second_run(geometry_store):
    _, w, _ = geometry_store
    again = geometry_only().build()
    assert again.fingerprints() == w.fingerprints()
    assert sorted(w.fields) == ["cell_area", "coriolis_parameter", "latitude", "longitude", "place_label"]


def test_planet_geometry_known_answers(geometry_store):
    _, w, _ = geometry_store
    assert abs(w.fields["cell_area"].sum() / 1e12 - 510.1) < 0.1               # million km², with Earth's radius
    lat45 = np.argmin(np.abs(w.fields["latitude"] - 45.0))
    f45 = w.fields["coriolis_parameter"][lat45] / np.sin(np.deg2rad(w.fields["latitude"][lat45])) * np.sin(np.pi / 4)
    assert abs(f45 - 1.03e-4) < 0.01e-4                                         # per second, at 45 degrees
    assert w.meta["mesh"]["area_max_over_min"] > 1.0


def test_store_holds_what_was_built_and_how(geometry_store):
    e, w, path = geometry_store
    v = store.StoreView(path)
    for name, a in w.fields.items():
        assert np.array_equal(v.field(name), a)
    assert v.fingerprints() == w.fingerprints() == v.attrs["fingerprints"]
    a = v.attrs
    assert a["seed"] == e.seed and a["meta"]["math_threads"] == 1 and a["code_fingerprint"] and a["packages"]["numpy"]
    assert yaml.safe_load(a["parameters_text"]["planet"]) == e.params["planet"]
    assert a["lineage"]["cell_area"]["writer"] == "PlanetGeometry"


def test_the_fingerprint_of_the_code_is_the_same_on_every_system_and_another_for_other_code(tmp_path):
    """The store records which code built it. The owner's machine is a Windows laptop: the same files checked out
    there may end their lines with carriage return and line feed, and name their folders with backslashes. One
    checkout must give one fingerprint. Any change to a file's text, to a file's name or to which files there are
    gives another."""
    files = {"engine.py": b"a = 1\nb = 2\n", "library/snow.py": b"def melt():\n    return 0\n", "library/notes.txt": b"not code\n"}

    def tree(name, files, line_end=b"\n"):
        root = tmp_path / name
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(text.replace(b"\n", line_end))
        return store.code_fingerprint(root)
    unix = tree("unix", files)
    assert len(unix) == 16 and unix == tree("again", files)
    assert tree("windows", files, b"\r\n") == unix
    assert tree("no_notes", {k: v for k, v in files.items() if k.endswith(".py")}) == unix             # only the Python files count
    assert tree("changed", {**files, "engine.py": b"a = 1\nb = 3\n"}) != unix
    assert tree("renamed", {"engine.py": files["engine.py"], "library/thaw.py": files["library/snow.py"]}) != unix
    assert tree("moved", {"engine.py": files["engine.py"], "snow.py": files["library/snow.py"]}) != unix
    assert tree("more", {**files, "extra.py": b""}) != unix
    assert store.code_fingerprint() == store.code_fingerprint() and len(store.code_fingerprint()) == 16
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"numpy==2.5.3\nscipy==1.0\n")
    pinned = store.lock_fingerprint(lock)
    lock.write_bytes(b"numpy==2.5.3\r\nscipy==1.0\r\n")
    assert store.lock_fingerprint(lock) == pinned and len(pinned) == 16
    lock.write_bytes(b"numpy==2.5.4\nscipy==1.0\n")
    assert store.lock_fingerprint(lock) != pinned
    assert store.lock_fingerprint(tmp_path / "none.lock") is None


def test_store_is_written_once(geometry_store):
    e, w, path = geometry_store
    with pytest.raises(FileExistsError):
        store.save(w, e, path)


def test_a_store_that_cannot_be_given_its_name_at_once_is_not_lost(geometry_store, tmp_path, monkeypatch):
    """The last step of writing a store is a rename. Where another program holds a file of the store open for a
    moment, the rename fails (a virus scanner on Windows does that [INFERRED: not run on Windows]). It is tried
    again; and if it never succeeds, the store is left whole under its other name and the refusal says where, so
    that a world that took hours is not thrown away over a name. Tried here by making the rename fail on purpose."""
    e, w, _ = geometry_store
    real, waits, failures = Path.rename, [], [3]

    def held(self, target):
        if self.name.endswith(".partial") and failures[0] > 0:
            failures[0] -= 1
            raise PermissionError(13, "held open by another program")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", held)
    monkeypatch.setattr(store.time, "sleep", waits.append)
    path = store.save(w, e, tmp_path / "late.zarr")                    # refused three times, then given its name
    assert path.exists() and not path.with_name("late.zarr.partial").exists() and waits == [store.MOVE_WAIT_S] * 3
    assert store.StoreView(path).fingerprints() == w.fingerprints()
    failures[0], waits[:] = 10 ** 6, []
    with pytest.raises(PermissionError) as err:
        store.save(w, e, tmp_path / "never.zarr")
    left = tmp_path / "never.zarr.partial"
    assert str(left) in str(err.value) and "Rename that folder to never.zarr by hand" in str(err.value)
    assert len(waits) == store.MOVE_TRIES - 1 and not (tmp_path / "never.zarr").exists()
    assert store.StoreView(left).fingerprints() == w.fingerprints()    # what was left behind is the whole world


@pytest.fixture(scope="module")
def served(geometry_store):
    _, _, path = geometry_store
    srv = make_server(path, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read(), r.headers.get_content_type()


def test_server_serves_the_viewer_page(served):
    body, ctype = get(served + "/")
    assert ctype == "text/html" and b"World viewer" in body
    assert b"WebGL2" in get(served + "/viewer.js")[0]


def test_server_answers_the_page(served, geometry_store):
    _, w, _ = geometry_store
    world = json.loads(get(served + "/api/world")[0])
    assert world["meta"]["cells"] == w.n and "latitude" in world["fields"]
    lat = np.frombuffer(get(served + "/api/field?name=latitude")[0], dtype="<f4")
    assert np.allclose(lat, w.fields["latitude"], atol=1e-4)
    ids = np.frombuffer(get(served + "/api/idmap?width=256")[0], dtype="<u4").reshape(128, 256)
    assert np.all(w.fields["latitude"][ids[0]] > 80) and np.all(w.fields["latitude"][ids[-1]] < -80)
    cell = json.loads(get(served + "/api/cell?id=0")[0])
    assert cell["lat"] == 90.0 and cell["values"]["place_label"] == "none"
    why = json.loads(get(served + "/api/explain?cell=5&field=coriolis_parameter")[0])
    assert why["chain"][-1]["end"] is True
    stats = json.loads(get(served + "/api/stats?name=cell_area")[0])
    area = w.fields["cell_area"].astype(np.float64)
    assert stats["min"] == area.min() and stats["max"] == area.max()
    low, high, top = np.percentile(area, [2.0, 98.0, 99.9])
    assert np.isclose(stats["low"], low) and np.isclose(stats["high"], high) and np.isclose(stats["top"], top)
    assert stats["low"] < stats["high"] <= stats["top"] <= stats["max"]            # top: the scale of a field a few cells of which hold most


def test_same_request_in_two_server_sessions_gives_the_same_bytes(served, geometry_store):
    _, _, path = geometry_store
    other = make_server(path, port=0)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    url2 = f"http://127.0.0.1:{other.server_address[1]}"
    for q in ("/api/field?name=cell_area", "/api/idmap?width=256", "/api/explain?cell=7&field=latitude"):
        assert get(served + q)[0] == get(url2 + q)[0]
    other.shutdown()


def test_server_refuses_what_it_does_not_have(served):
    for q in ("/api/field?name=no_such_field", "/api/cell?id=99999999", "/../secrets"):
        with pytest.raises(urllib.error.HTTPError) as err:
            get(served + q)
        assert err.value.code in (400, 404)


# ---------------------------------------------------------------------------------------------- what the fourth check of step 2 found untested
@pytest.fixture(scope="module")
def toy_store(tmp_path_factory):
    """A small world with every kind of thing a store holds: numbers, a direction, a true-or-false field, and a table
    with a true-or-false column."""
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5], "ok": [True, False]}
    try:
        e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "Marker": slot("Marker", ["ones", "month_no", "heading"]),
                    "Flipper": slot("Flipper", ["flag"])},
                   {**GEO_FIELDS, "flag": dict(family="Toy", unit="true or false", shape="cell", kind="boolean", default=False)},
                   tables=BOOL_TABLE, max_rounds=3)
        w = e.build()
    finally:
        T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    return e, w, store.save(w, e, tmp_path_factory.mktemp("worlds") / "toy.zarr")


def test_a_store_hands_out_what_was_built_in_kind_as_well_as_in_value(toy_store):
    """A true-or-false field must come back true-or-false: as numbers 0 and 1 it compares equal to what was built and
    then fails where it is used as a mask (~ of 1 is -2). Every field and every column of every table is held to the
    type and the bytes of the world in memory."""
    e, w, path = toy_store
    view = store.StoreView(path)
    assert w.fields["flag"].dtype == np.bool_ and w.fields["heading"].shape == (w.n, 3)
    for name, built in w.fields.items():
        read = view.field(name)
        assert read.dtype == built.dtype and read.shape == built.shape and np.array_equal(read, built, equal_nan=built.dtype.kind == "f"), name
    assert view.field("flag").dtype == np.bool_
    for name, column in w.tables["toy_items"].items():
        assert view.table("toy_items")[name].dtype == column.dtype and np.array_equal(view.table("toy_items")[name], column), name
    assert view.fingerprints() == w.fingerprints() and any(key.startswith("table:toy_items.") for key in w.fingerprints())


def test_what_a_view_hands_out_cannot_be_changed_and_is_read_once(toy_store, monkeypatch):
    """A view gives one copy of an array to every caller, so no caller may change it; and it keeps what it has read,
    up to a limit, so that one "why" answer after another does not read the same arrays again."""
    _, w, path = toy_store
    view = store.StoreView(path)
    ones = view.field("ones")
    assert view.field("ones") is ones                         # the second asking reads nothing: it is handed the array that was kept
    for array in (ones, view.field("flag"), view.table("toy_items")["value"], view.mesh_array("lat")):
        assert not array.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            array[0] = 5
    assert view.table("toy_items")["value"] is view.table("toy_items")["value"]            # the table's arrays are kept too
    # the limit: with room for one field only, the view still answers rightly, and holds no more than it may
    monkeypatch.setattr(store, "KEEP_BYTES", ones.nbytes + 8)
    small = store.StoreView(path)
    for name in ("ones", "month_no", "heading", "ones"):
        assert np.array_equal(small.field(name), w.fields[name])
        assert small._kept_bytes <= store.KEEP_BYTES
    assert ("field", "ones") in small._kept and ("field", "month_no") not in small._kept    # what does not fit is not kept


def test_the_fingerprint_of_a_world_holds_its_tables(toy_store):
    """The table of hollows and the table of lakes are part of a world. Two worlds that differ in one value of one
    table must not carry one fingerprint."""
    e, w, _ = toy_store
    before, prints = w.fingerprint(), w.fingerprints()
    assert {"table:toy_items.item", "table:toy_items.value", "table:toy_items.ok"} <= set(prints)
    kept = w.tables["toy_items"]
    other = kept["value"].copy()                              # (a world's own arrays cannot be written to)
    other[1] += 1.0e-9
    try:
        w.tables["toy_items"] = {**kept, "value": other}
        assert w.fingerprint() != before and w.fingerprints()["table:toy_items.value"] != prints["table:toy_items.value"]
        assert {k for k, v in w.fingerprints().items() if v != prints[k]} == {"table:toy_items.value"}
    finally:
        w.tables["toy_items"] = kept
    assert w.fingerprint() == before


@pytest.fixture(scope="module")
def toy_served(toy_store, tmp_path_factory):
    """The toy world behind the server, with a viewer folder of its own and a file beside that folder."""
    _, _, path = toy_store
    home = tmp_path_factory.mktemp("served")
    (home / "viewer").mkdir()
    (home / "viewer" / "index.html").write_text("<p>the page</p>", encoding="utf-8")
    (home / "secret.txt").write_text("not for the page", encoding="utf-8")
    srv = make_server(path, port=0, viewer_dir=home / "viewer")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def raw_get(port, path):
    """A request whose path is sent exactly as written (urllib may tidy a path before it sends it)."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def test_the_server_gives_a_direction_as_east_then_north(toy_store, toy_served):
    """The field `heading` of the toy world points east everywhere. For one cell the page is given (east, north); the
    part asked for by name is that part; without a name, the speed."""
    _, w, _ = toy_store
    cell = int(np.flatnonzero(np.abs(w.mesh.lat) < 60)[7])
    status, body = raw_get(toy_served, f"/api/cell?id={cell}")
    values = json.loads(body)["values"]
    assert status == 200 and values["heading"] == pytest.approx([1.0, 0.0], abs=1e-12) and values["flag"] in (0.0, 1.0)
    part = lambda name: np.frombuffer(raw_get(toy_served, f"/api/field?name=heading{name}")[1], dtype="<f4")
    away_from_poles = np.abs(w.mesh.lat) < 89.0
    assert np.allclose(part("&part=east")[away_from_poles], 1.0, atol=1e-6) and np.allclose(part("&part=north"), 0.0, atol=1e-6)
    assert np.allclose(part("")[away_from_poles], 1.0, atol=1e-6)


def test_the_flat_map_runs_from_180_west_to_180_east_and_from_the_north_down(toy_store, toy_served):
    """The page draws the flat map from a grid of cell numbers: column 0 at 180 degrees west, the middle column at the
    meridian of 0, row 0 in the north."""
    _, w, _ = toy_store
    status, body = raw_get(toy_served, "/api/idmap?width=256")
    ids = np.frombuffer(body, dtype="<u4").reshape(128, 256)
    lat, lon = w.mesh.lat, w.mesh.lon
    spacing = 30.0                                              # degrees: the toy mesh is coarse (cells some 15 degrees apart)
    for column, east in ((0, -180.0), (64, -90.0), (128, 0.0), (192, 90.0)):
        got = lon[ids[64, column]]
        assert min(abs(got - east), abs(got - east - 360.0), abs(got - east + 360.0)) < spacing, (column, got)
    assert lat[ids[2, 128]] > 60.0 and lat[ids[125, 128]] < -60.0 and abs(lat[ids[64, 128]]) < spacing


def test_the_server_serves_its_viewer_folder_and_nothing_beside_it(toy_served):
    """A file that exists beside the viewer folder is not served, by whatever path it is asked for: the server is for
    one page and one world."""
    assert raw_get(toy_served, "/")[1] == b"<p>the page</p>" and raw_get(toy_served, "/index.html")[0] == 200
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/viewer/../../secret.txt", "//secret.txt", "/secret.txt"):
        status, body = raw_get(toy_served, path)
        assert status == 404 and b"not for the page" not in body, path


def test_the_page_is_warned_when_the_engine_is_not_the_one_that_built_the_world(toy_store):
    """A stored world is answered by the code that runs now. If that is not the code that built it, an answer worked
    out now may differ from the build, and the page says so."""
    _, _, path = toy_store
    service = WorldService(store.StoreView(path))
    assert service.warnings() == [] and service.world()["warnings"] == []
    service.view.attrs["code_fingerprint"] = "0" * 16
    assert service.warnings() == ["The engine's code has changed since this world was built, so answers computed now may differ from the build."]
    service.view.attrs["lock_fingerprint"] = "0" * 16
    service.view.attrs["engine_version"] = "0.0.0"
    said = service.world()["warnings"]
    assert len(said) == 3 and said[0].startswith("This world was built by engine version 0.0.0") and "lock file" in said[2]
