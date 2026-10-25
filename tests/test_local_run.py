"""Running the engine on a person's own computer: what `serve` does for the launchers in scripts/, the Dockerfile and
the workflow .github/workflows/local-run.yml, and the hazards of the systems it runs on that Linux can stand in for.
The workflow runs this file on Windows and macOS too."""
import http.client
import mimetypes
import os
import signal
import subprocess
import sys
import threading

import pytest
import yaml

from conftest import DATA, ROOT
from worldengine import cli, server, store
from worldengine.engine import Engine


@pytest.fixture(scope="module")
def geometry_store(tmp_path_factory):
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    models["slots"] = {"PlanetGeometry": models["slots"]["PlanetGeometry"]}
    e = Engine(DATA, profile="preview", overrides={"models": models, "interventions": []})
    return store.save(e.build(), e, tmp_path_factory.mktemp("worlds") / "geometry.zarr")


@pytest.fixture
def running(geometry_store):
    srv = server.make_server(geometry_store, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def raw_get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, response.getheader("Content-Type"), body


def test_serve_check_starts_the_server_asks_it_for_the_page_and_the_world_and_stops(geometry_store, capsys):
    """What the launchers run with --check and the workflow runs on every system: the server answers over the network,
    and the command ends by itself with 0."""
    assert cli.main(["serve", str(geometry_store), "--port", "0", "--check"]) == 0
    out = capsys.readouterr().out
    assert "check: GET / gave" in out and "text/html" in out and "GET /viewer.js gave" in out and "text/javascript" in out
    assert "GET /style.css gave" in out and "GET /api/world gave a world of 10242 cells" in out and "check passed" in out


def test_serve_check_fails_when_the_page_is_not_whole(geometry_store, tmp_path):
    """A page without its script is a failed check, not a passed one."""
    (tmp_path / "index.html").write_text("<html><title>World viewer</title></html>", encoding="utf-8")
    srv = server.make_server(geometry_store, port=0, viewer_dir=tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(OSError):                     # the 404 for viewer.js
            server.check(srv)
    finally:
        srv.shutdown()
        srv.server_close()


def test_a_port_in_use_is_refused_in_one_line(geometry_store, running, capsys):
    """A second server on the port of a running one is refused, and says how to go on. On Windows the standard server
    would have taken the port as well (server._Server); the workflow runs this there."""
    port = running.server_address[1]
    assert cli.main(["serve", str(geometry_store), "--port", str(port)]) == 2
    err = capsys.readouterr().err
    assert f"refused: cannot listen on 127.0.0.1 port {port}" in err and "--port" in err
    assert raw_get(port, "/")[0] == 200                      # and the first server still answers


def test_the_viewer_files_go_out_with_their_own_types_whatever_the_system_says(running, monkeypatch):
    """On Windows mimetypes reads the registry, where .js may be text/plain; a browser then refuses the page's style
    sheet or script. Stood in for here by a mimetypes that says text/plain for everything."""
    monkeypatch.setattr(mimetypes, "guess_type", lambda *a, **k: ("text/plain", None))
    port = running.server_address[1]
    for path, want in (("/", "text/html"), ("/index.html", "text/html"), ("/viewer.js", "text/javascript"), ("/style.css", "text/css")):
        status, ctype, _ = raw_get(port, path)
        assert status == 200 and ctype == want + "; charset=utf-8", (path, ctype)


def test_a_path_with_a_drive_a_share_or_a_stream_is_not_looked_up(running):
    """On Windows a backslash, a drive letter or a colon in a path names something outside the viewer folder (another
    drive, a network share, a stream of a file); the server answers 404 before it touches the file system. On Linux
    and macOS these are plain names of files that do not exist, so the test can fail only on Windows (where
    index.html::$DATA is index.html itself)."""
    port = running.server_address[1]
    for path in ("/..\\README.md", "/\\\\localhost\\c$\\x", "/C:/Windows/win.ini", "/index.html::$DATA", "/viewer.js:x"):
        status, _, body = raw_get(port, path)
        assert status == 404 and b"World viewer" not in body, path


def test_a_server_on_every_address_is_reached_from_this_machine_at_127_0_0_1(geometry_store):
    srv = server.make_server(geometry_store, host="0.0.0.0", port=0)
    try:
        assert server.local_url(srv) == f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.server_close()


def test_serve_on_every_address_says_so(geometry_store, capsys):
    assert cli.main(["serve", str(geometry_store), "--host", "0.0.0.0", "--port", "0", "--check"]) == 0
    out = capsys.readouterr().out
    assert "note: listening on 0.0.0.0" in out and "check passed: the viewer and the world were served at http://127.0.0.1:" in out


def test_the_browser_is_opened_only_where_there_is_a_screen(monkeypatch, capsys):
    """On Linux without a screen webbrowser would start a text browser in the terminal of the server: --open says
    where the viewer is instead. With a screen, or a browser named in BROWSER, it opens the page."""
    import webbrowser
    opened = threading.Event()
    asked = []
    monkeypatch.setattr(webbrowser, "open", lambda url: asked.append(url) or opened.set() or True)
    monkeypatch.setattr(sys, "platform", "linux")
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "BROWSER"):
        monkeypatch.delenv(name, raising=False)
    assert cli.open_browser("http://127.0.0.1:8765/") is False
    assert "open http://127.0.0.1:8765/ in a browser" in capsys.readouterr().out and asked == []
    monkeypatch.setenv("DISPLAY", ":0")
    assert cli.open_browser("http://127.0.0.1:8765/") is True
    assert opened.wait(30) and asked == ["http://127.0.0.1:8765/"]
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("DISPLAY")
    opened.clear()
    assert cli.open_browser("http://127.0.0.1:9000/") is True and opened.wait(30) and asked[-1] == "http://127.0.0.1:9000/"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows stops a process without a signal (TerminateProcess)")
@pytest.mark.parametrize("sent", ["SIGINT", "SIGTERM"])
def test_the_server_stops_cleanly_on_ctrl_c_and_on_sigterm(geometry_store, sent):
    """Ctrl+C in the terminal (SIGINT), and `kill` or `docker stop` (SIGTERM): the server says it stopped and ends with
    0. Without its own handler for SIGTERM, the server in a container, the first process there, would not stop on it
    (cli._stop_on_sigterm)."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    with subprocess.Popen([sys.executable, "-m", "worldengine", "serve", str(geometry_store), "--port", "0"], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8") as p:
        try:
            said = []
            for line in p.stdout:
                said.append(line)
                if line.startswith("viewer at http://127.0.0.1:"):
                    break
            assert said and said[-1].startswith("viewer at"), said
            p.send_signal(getattr(signal, sent))
            rest, _ = p.communicate(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
    assert p.returncode == 0 and "stopped" in rest, (p.returncode, rest)
