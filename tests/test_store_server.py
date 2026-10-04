"""The world store and the local server (build step 0): a world holding only geometry is identical on a
second run and opens in the viewer through the local server."""
import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import yaml

from conftest import DATA
from worldengine import store
from worldengine.engine import Engine
from worldengine.server import make_server


def geometry_only():
    models = yaml.safe_load((DATA / "models.yaml").read_text())
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
    assert v.fingerprints() == {k: h for k, h in w.fingerprints().items() if not k.startswith("table:")}
    a = v.attrs
    assert a["seed"] == e.seed and a["meta"]["math_threads"] == 1 and a["code_fingerprint"] and a["packages"]["numpy"]
    assert yaml.safe_load(a["parameters_text"]["planet"]) == e.params["planet"]
    assert a["lineage"]["cell_area"]["writer"] == "PlanetGeometry"


def test_store_is_written_once(geometry_store):
    e, w, path = geometry_store
    with pytest.raises(FileExistsError):
        store.save(w, e, path)


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
    assert stats["min"] < stats["max"]


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
