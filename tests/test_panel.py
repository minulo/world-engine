"""The control panel (panel/): whether the engine runs, the run file `serve` writes for it, stopping a server the panel
did not start, upgrading, deleting, its settings, its shortcuts and its icons. Nothing here needs tkinter, except the
panel's own self-test at the end, which is skipped where there is none (or no screen). The workflow
.github/workflows/local-run.yml runs this file on Windows and macOS too."""
import http.server
import importlib.util
import json
import os
import plistlib
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

import pytest
import yaml

from conftest import DATA, ROOT
from worldengine import cli, server, store
from worldengine.engine import Engine

PANEL = ROOT / "panel"
sys.path.insert(0, str(PANEL))
import control  # noqa: E402
import icons  # noqa: E402
import make_icons  # noqa: E402

ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


@pytest.fixture(scope="module")
def geometry_store(tmp_path_factory):
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    models["slots"] = {"PlanetGeometry": models["slots"]["PlanetGeometry"]}
    e = Engine(DATA, profile="preview", overrides={"models": models, "interventions": []})
    return store.save(e.build(), e, tmp_path_factory.mktemp("worlds") / "geometry.zarr")


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    folder = tmp_path / "run"
    monkeypatch.setenv("WORLDENGINE_RUN_DIR", str(folder))
    return folder


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve_process(store_path, port, run_folder):
    """`serve` in a process of its own, as a terminal runs it; collected by a thread so that its pid is freed when it
    ends (a zombie still counts as alive on POSIX)."""
    log = open(run_folder.parent / f"serve-{port}.log", "w+", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "worldengine", "serve", str(store_path), "--port", str(port)],
                         env={**ENV, "WORLDENGINE_RUN_DIR": str(run_folder)}, stdout=log, stderr=subprocess.STDOUT)
    threading.Thread(target=p.wait, daemon=True).start()
    assert control.wait_until(lambda: control.read_run_file(port) is not None or p.poll() is not None, 120), "no run file"
    return p, log


def output(log):
    log.flush()
    log.seek(0)
    return log.read()


# ---------------------------------------------------------------------------------------------- what runs where
def test_the_panel_needs_nothing_but_the_standard_library():
    """The panel runs on the system's Python, before .venv exists: its modules import nothing of the engine's packages,
    and control.py and icons.py not even tkinter."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import control, icons, make_icons; "
            "bad = {'numpy', 'scipy', 'yaml', 'zarr', 'numba', 'worldengine', 'tkinter'} & set(sys.modules); "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-I", "-c", code, str(PANEL)], check=True)


def test_the_probe_tells_the_engine_from_another_program_and_from_nothing(geometry_store):
    srv = server.make_server(geometry_store, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class Impostor(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                   # the engine's answer, from a program that is not the engine
            body = json.dumps({"meta": {"cells": 1}, "fields": {}, "seed": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    other = http.server.HTTPServer(("127.0.0.1", 0), Impostor)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        answer = control.probe(srv.server_address[1])
        assert answer.kind == "engine" and answer.world["meta"]["cells"] == 10242
        assert control.probe(other.server_address[1]).kind == "other"
        assert control.probe(free_port()).kind == "nothing"
    finally:
        for s in (srv, other):
            s.shutdown()
            s.server_close()


# ---------------------------------------------------------------------------------------------- the run file
def test_serve_writes_its_run_file_and_the_panel_stops_it_by_asking(geometry_store, run_dir):
    """`serve` says in .worldengine/server-<port>.json which process serves; the panel, which did not start it, stops it
    with POST /api/stop and the file's token; the server says so and removes the file. On every system."""
    port = free_port()
    p, log = serve_process(geometry_store, port, run_dir)
    info = control.read_run_file(port)
    # the run file names the process that serves. On Windows the Python of a venv is a small program that starts the
    # real interpreter as its child, so that process is not the one Popen started (seen on windows-latest)
    assert info["pid"] == p.pid or (control.ON_WINDOWS and control.pid_alive(info["pid"]))
    assert info["port"] == port and info["world"] == str(Path(geometry_store).resolve())
    assert info["url"] == f"http://127.0.0.1:{port}/" and len(info["stop_token"]) == 32 and info["engine_version"]
    c = control.Controller()
    c.settings["port"] = port
    st = c.status()
    assert st.state == control.RUNNING and st.pid == info["pid"] and st.can_stop and not st.owned
    assert "asked to stop" in c.stop()
    assert control.wait_until(lambda: p.poll() is not None, 30) and p.returncode == 0
    assert "stopped (asked by the control panel)" in output(log)
    assert not (run_dir / f"server-{port}.json").exists() and c.status().state == control.STOPPED


def test_the_stop_request_needs_the_token(geometry_store):
    srv = server.make_server(geometry_store, port=0, stop_token="right")
    plain = server.make_server(geometry_store, port=0)
    loops = [threading.Thread(target=s.serve_forever, daemon=True) for s in (srv, plain)]
    for t in loops:
        t.start()
    try:
        assert not control.ask_to_stop(srv.server_address[1], "wrong")
        assert not control.ask_to_stop(plain.server_address[1], "right")       # no token: no such request
        assert control.probe(srv.server_address[1]).kind == "engine"
        assert control.ask_to_stop(srv.server_address[1], "right")
        loops[0].join(10)
        assert not loops[0].is_alive() and loops[1].is_alive()                 # serve_forever returned: `serve` ends
    finally:
        plain.shutdown()
        for s in (srv, plain):
            s.server_close()


def test_the_run_file_is_gone_after_check(geometry_store, run_dir):
    assert cli.main(["serve", str(geometry_store), "--port", "0", "--check"]) == 0
    assert run_dir.is_dir() and not list(run_dir.glob("server-*.json"))


def test_no_run_file_where_the_folder_cannot_be_written(geometry_store, tmp_path, monkeypatch):
    """In the container /app belongs to root: the server serves all the same."""
    blocker = tmp_path / "a file"
    blocker.write_text("x")
    monkeypatch.setenv("WORLDENGINE_RUN_DIR", str(blocker / "run"))
    assert cli.main(["serve", str(geometry_store), "--port", "0", "--check"]) == 0


@pytest.mark.skipif(sys.platform == "win32", reason="Windows stops a process without a signal")
def test_the_run_file_is_removed_on_sigterm(geometry_store, run_dir):
    port = free_port()
    p, log = serve_process(geometry_store, port, run_dir)
    assert (run_dir / f"server-{port}.json").exists()
    p.terminate()
    assert control.wait_until(lambda: p.poll() is not None, 30)
    assert "stopped" in output(log) and not (run_dir / f"server-{port}.json").exists()


def test_a_stale_run_file_is_ignored_and_removed(run_dir, tmp_path):
    """Left by a server that was killed: its process has ended, or nothing listens on its port."""
    run_dir.mkdir()
    ended = subprocess.Popen([sys.executable, "-c", "pass"])
    ended.wait()
    port, port2 = free_port(), free_port()
    for p, pid in ((port, ended.pid), (port2, os.getpid())):     # the second: a live process, but nothing on the port
        (run_dir / f"server-{p}.json").write_text(json.dumps({"pid": pid, "port": p, "stop_token": "x"}))
    c = control.Controller(tmp_path)
    for p in (port, port2):
        c.settings["port"] = p
        st = c.status()
        assert st.state == control.STOPPED and not st.can_stop
        assert not (run_dir / f"server-{p}.json").exists()


def test_a_server_without_a_token_is_stopped_by_its_pid(geometry_store, run_dir):
    """A server whose run file holds no token (or does not answer the request) is ended through its pid: SIGTERM on
    macOS and Linux (it then stops cleanly), taskkill on Windows."""
    port = free_port()
    p, log = serve_process(geometry_store, port, run_dir)
    path = run_dir / f"server-{port}.json"
    info = json.loads(path.read_text())
    info.pop("stop_token")
    path.write_text(json.dumps(info))
    c = control.Controller()
    c.settings["port"] = port
    said = c.stop()
    assert f"process {info['pid']}" in said and "asked" not in said           # (on Windows not p.pid: see above)
    assert control.wait_until(lambda: p.poll() is not None, 30)
    assert c.status().state == control.STOPPED
    if sys.platform != "win32":
        assert "SIGTERM" in said and "stopped" in output(log) and not path.exists()


# ---------------------------------------------------------------------------------------------- start and stop
def test_start_running_stop_with_the_panels_own_child(geometry_store, run_dir, tmp_path, monkeypatch):
    """The panel's Start runs the launcher detached, its output to .worldengine/launcher.log; Running when the server
    answers; Stop ends it and the light goes back to Stopped. (The launcher stands in by `serve` itself.)"""
    port = free_port()
    c = control.Controller(tmp_path, launcher=lambda port, world: [sys.executable, "-m", "worldengine", "serve",
                                                                   str(geometry_store), "--port", str(port)])
    c.settings["port"] = port
    monkeypatch.setenv("PYTHONPATH", ENV["PYTHONPATH"])
    try:
        c.start()
        assert c.status().state in (control.STARTING, control.RUNNING)
        assert c.wait_running(120), c.log_text()
        st = c.status()
        assert st.state == control.RUNNING and st.owned and st.can_stop and st.world == str(Path(geometry_store).resolve())
        assert control.button_states(st)["stop"] and control.button_states(st)["browser"] and not control.button_states(st)["start"]
        assert "viewer at" in c.take_output()
        c.stop()
        st = c.status()
        assert st.state == control.STOPPED and not c.child_running() and control.button_states(st)["start"]
    finally:
        if c.child_running():
            c.stop()


STEP = "import sys, time; print(sys.argv[1], flush=True); time.sleep(120)"


@pytest.mark.parametrize("line, state", [("== Making the environment .venv with python3.13", control.INSTALLING),
                                         ("== Installing the pinned packages of requirements.lock", control.INSTALLING),
                                         ("== Building the preview world into worlds/first.zarr", control.BUILDING),
                                         ("== Serving worlds/first.zarr", control.STARTING)])
def test_the_launchers_steps_set_the_state_and_stop_ends_the_whole_launcher(run_dir, tmp_path, line, state):
    c = control.Controller(tmp_path, launcher=lambda port, world: [sys.executable, "-c", STEP, line])
    c.settings["port"] = free_port()
    c.start()
    assert control.wait_until(lambda: c.status().state == state, 30), (c.status(), c.log_text())
    assert c.building() == (state == control.BUILDING)
    assert control.button_states(c.status())["stop"]
    said = c.stop()
    assert "ended" in said and not c.child_running() and c.status().state == control.STOPPED


def test_a_launcher_that_fails_shows_its_reason(run_dir, tmp_path):
    fail = "import sys; print('== Serving worlds/first.zarr'); print('refused: cannot listen on 127.0.0.1 port 1'); sys.exit(2)"
    c = control.Controller(tmp_path, launcher=lambda port, world: [sys.executable, "-c", fail])
    c.settings["port"] = free_port()
    c.start()
    assert control.wait_until(lambda: c.status().state == control.ERROR, 30)
    st = c.status()
    assert st.detail.startswith("refused: cannot listen") and "exit code 2" in st.detail
    assert control.button_states(st)["start"] and not control.button_states(st)["stop"]


def test_the_build_warning_says_what_is_left():
    """store.save writes a world to <name>.partial and gives it its name only when whole; save removes a .partial left
    by an earlier build first."""
    text = control.Controller().build_stop_warning()
    assert "first.zarr.partial" in text and "removes" in text
    src = (ROOT / "src" / "worldengine" / "store.py").read_text(encoding="utf-8")
    assert 'partial = path.with_name(path.name + ".partial")' in src and "shutil.rmtree(partial)" in src


def test_the_launcher_command_on_each_system(tmp_path):
    posix = control.launcher_command(8765, tmp_path / "w.zarr", tmp_path, windows=False)
    assert posix[:2] == ["/bin/sh", str(tmp_path / "scripts" / "run.sh")] and "--no-browser" in posix
    assert posix[posix.index("--port") + 1] == "8765" and posix[posix.index("--world") + 1] == str(tmp_path / "w.zarr")
    win = control.launcher_command(9000, tmp_path / "w.zarr", tmp_path, windows=True)
    assert win[1:5] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"] and win[5].endswith("run.ps1")
    assert "-NoBrowser" in win and win[win.index("-Port") + 1] == "9000"
    for option in ("-NoBrowser", "-Port", "-World"):                 # the launcher has each option the panel passes
        assert option.lstrip("-") in (ROOT / "scripts" / "run.ps1").read_text(encoding="utf-8")
    for option in ("--no-browser", "--port", "--world"):
        assert option in (ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- the buttons
def test_each_button_is_enabled_only_when_it_makes_sense():
    S, B = control.Status, control.button_states
    stopped, running = B(S(control.STOPPED)), B(S(control.RUNNING, can_stop=True))
    assert stopped["start"] and not stopped["stop"] and not stopped["browser"] and stopped["upgrade"] and stopped["settings"]
    assert not running["start"] and running["stop"] and running["browser"] and running["upgrade"] and not running["settings"]
    foreign = B(S(control.RUNNING, can_stop=False))                  # a server without a run file: cannot be stopped here
    assert foreign["browser"] and not foreign["stop"] and not foreign["upgrade"] and not foreign["delete"]
    for state in (control.INSTALLING, control.BUILDING, control.STARTING):
        b = B(S(state, can_stop=True))
        assert b["stop"] and not b["start"] and not b["upgrade"] and not b["delete"] and not b["browser"]
    for state in (control.STOPPING, control.WORKING):
        b = B(S(state, can_stop=True))
        assert not any(b[n] for n in ("start", "stop", "upgrade", "rebuild", "reset", "delete", "settings"))
    busy = B(S(control.STOPPED), action="Upgrade")
    assert not busy["start"] and not busy["delete"] and busy["folder"] and busy["copy"]


# ---------------------------------------------------------------------------------------------- upgrade
def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def clone(tmp_path, monkeypatch, run_dir):
    """A repository to upgrade: a clone of a bare origin, with a world built in it, and a second clone that publishes."""
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.invalid"), ("GIT_COMMITTER_NAME", "t"),
                 ("GIT_COMMITTER_EMAIL", "t@example.invalid"), ("GIT_CONFIG_GLOBAL", os.devnull), ("GIT_CONFIG_NOSYSTEM", "1")):
        monkeypatch.setenv(k, v)
    origin, mine, theirs = tmp_path / "origin.git", tmp_path / "mine", tmp_path / "theirs"
    git("-c", "init.defaultBranch=main", "init", "--bare", str(origin))
    git("clone", str(origin), str(theirs))
    (theirs / "engine.txt").write_text("1\n")
    git("add", ".", cwd=theirs)
    git("commit", "-m", "one", cwd=theirs)
    git("push", "origin", "HEAD:main", cwd=theirs)
    git("clone", "--branch", "main", str(origin), str(mine))
    for w in ("first.zarr", "other.zarr"):
        (mine / "worlds" / w).mkdir(parents=True)
        (mine / "worlds" / w / "zarr.json").write_text("{}")
    (mine / ".gitignore").write_text("worlds/\n")
    return mine, theirs


def publish(theirs, text):
    (theirs / "engine.txt").write_text(text)
    git("commit", "-am", text, cwd=theirs)
    git("push", "origin", "HEAD:main", cwd=theirs)


def test_upgrade_pulls_and_deletes_the_default_world(clone):
    mine, theirs = clone
    c = control.Controller(mine)
    c.settings["port"] = free_port()
    same = c.upgrade()
    assert not same.changed and "Already up to date" in same.message and (mine / "worlds" / "first.zarr").exists()
    publish(theirs, "2\n")
    said = []
    result = c.upgrade(log=said.append)
    assert result.changed and (mine / "engine.txt").read_text() == "2\n"
    assert not (mine / "worlds" / "first.zarr").exists() and (mine / "worlds" / "other.zarr").exists()
    assert "first.zarr was deleted" in result.message and any("git pull --ff-only" in s for s in said)


def test_upgrade_refuses_what_is_not_a_fast_forward_and_changes_nothing(clone):
    mine, theirs = clone
    (mine / "mine.txt").write_text("my own\n")
    git("add", "mine.txt", cwd=mine)
    git("commit", "-m", "my own", cwd=mine)
    publish(theirs, "3\n")
    head = git("rev-parse", "HEAD", cwd=mine)
    c = control.Controller(mine)
    c.settings["port"] = free_port()
    with pytest.raises(control.ControlError) as e:
        c.upgrade()
    assert "git pull --ff-only failed" in str(e.value) and "Nothing was changed" in str(e.value)
    assert git("rev-parse", "HEAD", cwd=mine) == head and (mine / "worlds" / "first.zarr").exists()


def test_upgrade_without_git_or_outside_a_clone_says_so(clone, tmp_path, monkeypatch):
    mine, _ = clone
    monkeypatch.setattr(control.shutil, "which", lambda name: None)
    with pytest.raises(control.ControlError, match="Git was not found"):
        control.Controller(mine).upgrade()
    with pytest.raises(control.ControlError, match="not a Git clone"):
        control.Controller(tmp_path / "no-clone").upgrade()
    assert (mine / "worlds" / "first.zarr").exists()


# ---------------------------------------------------------------------------------------------- delete, rebuild, reset
def fake_repo(tmp_path):
    repo = tmp_path / "world-engine"
    for d in (".venv/bin", "worlds/first.zarr", "worlds/first.zarr.partial", ".worldengine", "src"):
        (repo / d).mkdir(parents=True)
    (repo / "README.md").write_text("code\n")
    (repo / ".venv" / "bin" / "python").write_text("")
    (repo / ".worldengine" / "panel.json").write_text("{}")
    return repo


def test_delete_lists_what_it_removes_and_what_it_leaves_and_keeps_the_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("WORLDENGINE_RUN_DIR", raising=False)
    repo = fake_repo(tmp_path)
    app = control.install_mac_app(ROOT, tmp_path / "Applications")       # a shortcut the panel made, for another repo
    c = control.Controller(repo)
    c.settings["port"] = free_port()
    c.settings["shortcuts"] = [str(app)]
    gone, kept = c.delete_plan()
    assert [p for p, _ in gone] == [repo / ".venv", repo / "worlds", repo / ".worldengine"]   # the app points elsewhere
    assert kept[0][0] == repo and "delete it yourself" in kept[0][1] and [w for _, w in kept[1:]] == ["Python", "Git"]
    removed = c.delete_everything()
    assert removed == [repo / ".venv", repo / "worlds", repo / ".worldengine"]
    assert repo.is_dir() and (repo / "README.md").exists() and (repo / "src").is_dir() and app.exists()


def test_delete_removes_the_app_it_installed_for_this_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("WORLDENGINE_RUN_DIR", raising=False)
    repo = fake_repo(tmp_path)
    shutil.copytree(PANEL / "assets", repo / "panel" / "assets")
    c = control.Controller(repo)
    c.settings["port"] = free_port()
    made = c.install_shortcut(tmp_path / "Applications") if not control.ON_WINDOWS else \
        [control.install_mac_app(repo, tmp_path / "Applications")]
    c.settings["shortcuts"] = [str(m) for m in made]
    assert str(made[0]) in [str(p) for p, _ in c.delete_plan()[0]]
    c.delete_everything()
    assert not made[0].exists() and repo.is_dir()


def test_the_panel_never_deletes_the_folder_itself_or_anything_outside_it(tmp_path):
    repo = fake_repo(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    for p in (repo, tmp_path, outside):
        with pytest.raises(control.ControlError, match="Refused to delete"):
            control.remove(p, repo)
    assert repo.is_dir() and outside.is_dir()
    with pytest.raises(control.ControlError, match="not a world folder"):
        control.Controller(repo).delete_world("README.md")


def test_rebuild_and_reset_delete_the_world_and_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("WORLDENGINE_RUN_DIR", raising=False)
    repo = fake_repo(tmp_path)
    c = control.Controller(repo)
    c.settings["port"] = free_port()
    c.delete_world()
    assert not (repo / "worlds" / "first.zarr").exists() and not (repo / "worlds" / "first.zarr.partial").exists()
    assert c.reset_environment() and not (repo / ".venv").exists() and not c.reset_environment()


# ---------------------------------------------------------------------------------------------- settings
def test_the_settings_are_kept_and_checked(tmp_path, run_dir):
    c = control.Controller(tmp_path)
    assert (c.port, c.world) == (8765, "worlds/first.zarr")
    c.set_settings(port=" 9001 ", world="worlds/other.zarr")
    again = control.Controller(tmp_path)
    assert (again.port, again.world) == (9001, "worlds/other.zarr")
    for bad in ("abc", "0", "70000"):
        with pytest.raises(control.ControlError, match="whole number from 1 to 65535"):
            again.set_settings(port=bad)
    (run_dir / "panel.json").write_text("{not json")
    assert control.load_settings(tmp_path)["port"] == 8765
    (run_dir / "panel.json").write_text(json.dumps({"port": "8765; rm", "world": 3, "shortcuts": "x", "magic": "yes"}))
    assert control.load_settings(tmp_path) == {"port": 8765, "world": "worlds/first.zarr", "magic": False, "shortcuts": []}


def test_the_magic_box_names_its_own_world_and_passes_the_layer_to_the_launcher(tmp_path, run_dir, monkeypatch):
    """The box "Magic (invented physics)": the default world gives way to worlds/first-magic.zarr and back, a world of
    one's own choosing stays, the choice is kept, and the launcher builds with --fantasy magic (-Fantasy magic)."""
    c = control.Controller(tmp_path)
    assert not c.magic and c.world == control.DEFAULT_WORLD
    c.set_settings(magic=True)
    assert c.magic and c.world == control.MAGIC_WORLD == "worlds/first-magic.zarr"
    again = control.Controller(tmp_path)
    assert again.magic and again.world == control.MAGIC_WORLD
    again.set_settings(magic=False)
    assert not again.magic and again.world == control.DEFAULT_WORLD
    again.set_settings(world="worlds/mine.zarr", magic=True)
    assert again.magic and again.world == "worlds/mine.zarr"
    posix = control.launcher_command(8765, tmp_path / "w.zarr", tmp_path, windows=False, fantasy="magic")
    win = control.launcher_command(8765, tmp_path / "w.zarr", tmp_path, windows=True, fantasy="magic")
    assert posix[-2:] == ["--fantasy", "magic"] and win[-2:] == ["-Fantasy", "magic"]
    assert not any("antasy" in a for a in control.launcher_command(8765, tmp_path / "w.zarr", tmp_path, windows=False) +
                   control.launcher_command(8765, tmp_path / "w.zarr", tmp_path, windows=True))
    run_sh, run_ps1 = ((ROOT / "scripts" / name).read_text(encoding="utf-8") for name in ("run.sh", "run.ps1"))
    assert "--fantasy) FANTASY=$2" in run_sh and '${FANTASY:+--fantasy "$FANTASY"}' in run_sh and "first${FANTASY:+-$FANTASY}.zarr" in run_sh
    assert "[string]$Fantasy" in run_ps1 and '@("--fantasy", $Fantasy)' in run_ps1 and '("first" + $layer + ".zarr")' in run_ps1
    asked = []

    def launcher(port, world, repo, fantasy=None):
        asked.append((world, fantasy))
        return [sys.executable, "-c", "pass"]
    monkeypatch.setattr(control, "launcher_command", launcher)
    c = control.Controller(tmp_path)
    c.set_settings(port=free_port())
    c.start()
    c.wait_running(30)
    assert asked == [(tmp_path / "worlds" / "mine.zarr", "magic")]


def test_the_worlds_of_the_dropdown(tmp_path):
    for d in ("worlds/b.zarr", "worlds/a.zarr", "worlds/a.zarr.partial", "worlds/notes"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "worlds" / "file.zarr").write_text("")
    assert control.worlds(tmp_path) == ["worlds/a.zarr", "worlds/b.zarr"]


# ---------------------------------------------------------------------------------------------- shortcuts and the app
def test_the_mac_app_is_a_whole_bundle_that_runs_the_panel_of_this_folder(tmp_path):
    app = control.install_mac_app(ROOT, tmp_path, python="/opt/homebrew/bin/python3.13")
    assert app == tmp_path / "World Engine.app"
    with open(app / "Contents" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleExecutable"] == "world-engine" and info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleIconFile"] == "world-engine.icns" and info["CFBundleName"] == "World Engine"
    exe = app / "Contents" / "MacOS" / "world-engine"
    text = exe.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and str(ROOT.resolve()) in text and "/opt/homebrew/bin/python3.13" in text
    assert (app / "Contents" / "Resources" / "world-engine.icns").read_bytes() == (PANEL / "assets" / "world-engine.icns").read_bytes()
    if sys.platform != "win32":
        assert os.access(exe, os.X_OK)
        subprocess.run(["/bin/sh", "-n", str(exe)], check=True)
    control.install_mac_app(ROOT, tmp_path)                                  # made again over its own
    foreign = tmp_path / "other" / "World Engine.app"
    foreign.mkdir(parents=True)
    with pytest.raises(control.ControlError, match="not made by this panel"):
        control.install_mac_app(ROOT, tmp_path / "other")


@pytest.mark.skipif(sys.platform == "win32", reason="the app's script is a POSIX shell script")
def test_the_mac_apps_script_finds_the_panel_and_passes_its_arguments(tmp_path):
    """Run the app's executable as LaunchServices would (a short PATH): it starts the panel with the given Python."""
    app = control.install_mac_app(ROOT, tmp_path, python=sys.executable)
    r = subprocess.run([str(app / "Contents" / "MacOS" / "world-engine"), "--help"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)})
    assert r.returncode == 0 and "--self-test" in r.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")
def test_the_windows_shortcut_is_made_in_the_folder_given(tmp_path):
    made = control.install_windows_shortcuts(ROOT, [tmp_path])
    assert made == [tmp_path / "World Engine.lnk"] and made[0].exists()
    read = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:WE_LNK); "
            "Write-Output $s.TargetPath; Write-Output $s.Arguments; Write-Output $s.IconLocation")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", read], capture_output=True, text=True, check=True,
                         env={**os.environ, "WE_LNK": str(made[0])}).stdout.splitlines()
    assert out[0].lower().endswith(("pythonw.exe", "python.exe")) and "world_engine_panel.py" in out[1]
    assert out[2].lower().endswith("world-engine.ico,0")


# ---------------------------------------------------------------------------------------------- icons
def png_pixels(data):
    """Width, height and raw rows of a PNG written by icons.png_bytes (one IDAT, filter 0)."""
    w, h = icons.png_size(data)
    pos, idat = 8, b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        assert zlib.crc32(data[pos + 4:pos + 8 + n]) & 0xFFFFFFFF == struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    assert len(raw) == h * (1 + 4 * w)
    return w, h, raw


def test_every_button_icon_is_a_whole_png_with_something_drawn():
    for name in icons.ICONS:
        for size in (20, 40):
            w, h, raw = png_pixels(icons.icon_png(name, size))
            assert (w, h) == (size, size)
            alphas = [raw[r * (1 + 4 * w) + 1 + 4 * x + 3] for r in range(h) for x in range(w)]
            assert 0.05 < sum(a > 128 for a in alphas) / len(alphas) < 0.9, name


def test_the_app_icons_hold_the_sizes_each_system_wants():
    ico = (PANEL / "assets" / "world-engine.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1)
    sizes = []
    for i in range(count):
        w, h, _, _, planes, bits, length, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
        png = ico[offset:offset + length]
        assert icons.png_size(png) == ((w or 256), (h or 256)) and (planes, bits) == (1, 32)
        sizes.append(w or 256)
    assert {16, 32, 48, 256} <= set(sizes)
    icns = (PANEL / "assets" / "world-engine.icns").read_bytes()
    assert icns[:4] == b"icns" and struct.unpack(">I", icns[4:8])[0] == len(icns)
    pos, found = 8, {}
    while pos < len(icns):
        kind, length = struct.unpack(">4sI", icns[pos:pos + 8])
        found[kind.decode()] = icons.png_size(icns[pos + 8:pos + length])[0]
        pos += length
    assert found == {kind: size for kind, size in make_icons.ICNS_TYPES}
    assert icons.png_size((PANEL / "assets" / "world-engine.png").read_bytes()) == (256, 256)
    # the files are what make_icons.py draws now
    first = struct.unpack("<BBBBHHII", ico[6:22])
    assert ico[first[7]:first[7] + first[6]] == make_icons.planet_png(16)


# ---------------------------------------------------------------------------------------------- the window
def has_tkinter():
    return importlib.util.find_spec("tkinter") is not None


@pytest.mark.skipif(not has_tkinter(), reason="this Python has no tkinter")
@pytest.mark.skipif(sys.platform.startswith("linux") and not os.environ.get("DISPLAY"), reason="no screen")
def test_the_panels_self_test(tmp_path):
    r = subprocess.run([sys.executable, str(PANEL / "world_engine_panel.py"), "--self-test",
                        "--self-test-out", str(tmp_path / "said.txt")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "self-test passed" in r.stdout, r.stdout + r.stderr
    assert (tmp_path / "said.txt").read_text().startswith("self-test passed")


def test_the_panel_says_how_to_get_tkinter_when_it_is_missing(tmp_path):
    """Homebrew's Python has no tkinter until python-tk@3.13 is installed: the panel says so, and ends with 3."""
    hide = tmp_path / "hide"
    hide.mkdir()
    (hide / "tkinter.py").write_text("raise ImportError('no tkinter here')\n")
    r = subprocess.run([sys.executable, str(PANEL / "world_engine_panel.py")], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(hide)})
    assert r.returncode == 3 and "brew install python-tk@" in r.stderr and "python.org" in r.stderr
