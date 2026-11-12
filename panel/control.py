"""What the control panel does, without its window: whether the world engine runs, and starting, stopping, upgrading,
rebuilding, resetting and deleting it. Standard library only, and no tkinter, so that it runs on the system's Python
before the engine's environment .venv exists, and so that tests/test_panel.py can test it anywhere.

Whether the engine runs is decided by asking it: GET /api/world on 127.0.0.1:<port> must answer as the engine does.
`serve` also writes a run file, .worldengine/server-<port>.json (src/worldengine/server.py, write_run_file), which says
which process serves there, so that the panel can stop a server that it did not start.
"""
from __future__ import annotations

import json
import os
import plistlib
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765
DEFAULT_WORLD = "worlds/first.zarr"
ENGINE_WORLDS = (DEFAULT_WORLD,)           # the worlds the launcher builds by itself: an upgrade deletes them
APP_NAME = "World Engine"
ON_WINDOWS = sys.platform == "win32"
ON_MAC = sys.platform == "darwin"

# The states the light shows.
STOPPED, INSTALLING, BUILDING, STARTING, RUNNING, STOPPING, WORKING, ERROR = (
    "Stopped", "Installing", "Building the world", "Starting", "Running", "Stopping", "Working", "Error")

# The step lines of the launchers (scripts/run.sh and run.ps1 print "== <step>") and the state each one starts.
STEP_STATES = (("== The environment .venv does not run", INSTALLING), ("== Making the environment", INSTALLING),
               ("== Installing", INSTALLING), ("== Building", BUILDING), ("== Serving", STARTING))

# Programs started from the panel get no console window of their own on Windows (the panel runs under pythonw).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if ON_WINDOWS else 0


class ControlError(Exception):
    """Something the panel could not do; the message says what, and what to do about it, in plain words."""


# ---------------------------------------------------------------------------------------------- asking the server
@dataclass
class Probe:
    """What answered on the port: "engine" (the world engine; `world` holds its /api/world), "other" (some other
    program), "busy" (something took the connection but did not answer in time) or "nothing"."""
    kind: str
    world: dict = None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # 127.0.0.1 never goes through a proxy


CONNECT_S = 5.0   # how long a connection may take to be refused: on Windows a closed port of this computer is refused
                  # only after about 2 s, so a shorter wait reads "nothing listens" as "something is busy" (the first run
                  # of the workflow on windows-latest; on macOS and Linux it is refused at once)


def listening(port, host="127.0.0.1", timeout=CONNECT_S):
    """True if something accepts connections on the port, False if the connection is refused, None if it neither
    accepts nor refuses within `timeout`."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, TimeoutError):
        return None
    except OSError:
        return False


def probe(port, host="127.0.0.1", timeout=3.0) -> Probe:
    """Ask GET /api/world. The engine answers with its Server header "WorldEngine/<version>" and a world that has
    cells, fields and a seed; an open port alone is not the engine. Whether anything listens is asked first, with time
    enough for Windows to refuse (CONNECT_S), so that `timeout` bounds only the wait for the answer."""
    there = listening(port, host, max(timeout, CONNECT_S))
    if there is False:
        return Probe("nothing")
    if there is None:
        return Probe("busy")
    try:
        with _OPENER.open(f"http://{host}:{int(port)}/api/world", timeout=timeout) as r:
            server_header = r.headers.get("Server", "")
            body = r.read()
    except urllib.error.HTTPError as e:
        return Probe("engine" if e.headers.get("Server", "").startswith("WorldEngine/") else "other")
    except (ConnectionError, socket.timeout, TimeoutError) as e:
        return Probe("busy" if isinstance(e, (socket.timeout, TimeoutError)) else "nothing")
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return Probe("busy")
        return Probe("nothing")
    except (OSError, ValueError):
        return Probe("other")
    try:
        world = json.loads(body)
        ok = (server_header.startswith("WorldEngine/") and isinstance(world, dict) and isinstance(world.get("meta"), dict)
              and "cells" in world["meta"] and "fields" in world and "seed" in world)
    except ValueError:
        ok = False
    return Probe("engine", world) if ok else Probe("other")


def ask_to_stop(port, token, host="127.0.0.1", timeout=5.0) -> bool:
    """POST /api/stop with the run file's token (src/worldengine/server.py, _Handler.do_POST). True if it agreed."""
    req = urllib.request.Request(f"http://{host}:{int(port)}/api/stop", data=b"", method="POST",
                                 headers={"X-World-Engine-Stop": token})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------------------------- processes
def pid_alive(pid) -> bool:
    """Whether a process with this number exists (on POSIX a zombie counts until its parent collects it)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if ON_WINDOWS:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5                 # ERROR_ACCESS_DENIED: it exists, and is not ours
        code = wintypes.DWORD()
        try:
            ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
        finally:
            k32.CloseHandle(handle)
        return bool(ok) and code.value == 259                   # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def wait_until(condition, timeout, step=0.2) -> bool:
    end = time.monotonic() + timeout
    while True:
        if condition():
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(step)


def _taskkill(pid, force) -> str:
    """Windows: end a process and the processes it started. Without /F, taskkill asks politely, which a program
    without a window (as here) cannot answer, so the forced form follows [DOCUMENTED: Microsoft, taskkill]."""
    cmd = ["taskkill", "/PID", str(int(pid)), "/T"] + (["/F"] if force else [])
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    return (r.stdout + r.stderr).strip()


def end_process(pid, own_group=False, timeout=10.0, child=None) -> str:
    """End a process and what it started: on macOS and Linux SIGTERM (to the whole group if it leads one the panel made),
    then SIGKILL after `timeout`; on Windows taskkill /T, then taskkill /T /F. `child`: the Popen, when the process is
    the panel's own child (which stays a zombie, alive to pid_alive, until it is collected). Returns what was done."""
    alive = (lambda: child.poll() is None) if child is not None else (lambda: pid_alive(pid))
    if not alive():
        return f"process {pid} had ended already"
    if ON_WINDOWS:
        said = _taskkill(pid, force=False)
        if wait_until(lambda: not alive(), min(timeout, 5.0)):
            return f"process {pid} ended (taskkill)"
        said = _taskkill(pid, force=True)
        if wait_until(lambda: not alive(), timeout):
            return f"process {pid} was ended by force (taskkill /F)"
        raise ControlError(f"Process {pid} did not end: {said}")
    send = (lambda s: os.killpg(pid, s)) if own_group else (lambda s: os.kill(pid, s))
    try:
        send(signal.SIGTERM)
    except ProcessLookupError:
        return f"process {pid} had ended already"
    if wait_until(lambda: not alive(), timeout):
        return f"process {pid} ended (SIGTERM)"
    try:
        send(signal.SIGKILL)
    except ProcessLookupError:
        pass
    if wait_until(lambda: not alive(), 5.0):
        return f"process {pid} was ended by force (SIGKILL)"
    raise ControlError(f"Process {pid} did not end, even after SIGKILL.")


# ---------------------------------------------------------------------------------------------- files
def run_dir(repo=REPO) -> Path:
    """Where `serve` writes its run files and the panel its settings and the launcher's output (the folder of
    src/worldengine/server.py run_dir(), which WORLDENGINE_RUN_DIR can move, for tests)."""
    return Path(os.environ.get("WORLDENGINE_RUN_DIR") or Path(repo) / ".worldengine")


def read_run_file(port, repo=REPO):
    """The run file of a server on this port, or None if there is none or it cannot be read."""
    path = run_dir(repo) / f"server-{int(port)}.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) and "pid" in info else None


def remove_stale_run_file(port, repo=REPO, answer: Probe = None) -> bool:
    """A run file whose process is gone, or whose port nothing listens on, is left from a server that did not stop
    cleanly (killed, or the computer turned off): remove it. True if one was removed."""
    info = read_run_file(port, repo)
    if info is None:
        return False
    answer = answer or probe(port)
    if pid_alive(info["pid"]) and answer.kind != "nothing":
        return False
    try:
        (run_dir(repo) / f"server-{int(port)}.json").unlink()
    except OSError:
        return False
    return True


def worlds(repo=REPO) -> list:
    """The worlds in worlds/, as paths relative to the repository (the panel's dropdown)."""
    folder = Path(repo) / "worlds"
    found = sorted(p for p in folder.glob("*.zarr") if p.is_dir()) if folder.is_dir() else []
    return [p.relative_to(repo).as_posix() for p in found]


def load_settings(repo=REPO) -> dict:
    """The panel's settings in .worldengine/panel.json: the port, the world, and the shortcuts it installed."""
    out = {"port": DEFAULT_PORT, "world": DEFAULT_WORLD, "shortcuts": []}
    try:
        saved = json.loads((run_dir(repo) / "panel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if isinstance(saved, dict):
        if isinstance(saved.get("port"), int) and 1 <= saved["port"] <= 65535:
            out["port"] = saved["port"]
        if isinstance(saved.get("world"), str) and saved["world"].strip():
            out["world"] = saved["world"]
        if isinstance(saved.get("shortcuts"), list):
            out["shortcuts"] = [s for s in saved["shortcuts"] if isinstance(s, str)]
    return out


def save_settings(settings, repo=REPO):
    folder = run_dir(repo)
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / "panel.json.part"
    part.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    os.replace(part, folder / "panel.json")


def check_port(text) -> int:
    try:
        port = int(str(text).strip())
    except ValueError:
        raise ControlError(f"The port must be a whole number from 1 to 65535, not {text!r}.") from None
    if not 1 <= port <= 65535:
        raise ControlError(f"The port must be a whole number from 1 to 65535, not {port}.")
    return port


def _rmtree(path):
    """Remove a folder, including files marked read-only (which Windows refuses to delete otherwise)."""
    def again(func, p, *_):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=again)
    else:
        shutil.rmtree(path, onerror=again)


def remove(path, repo=REPO, allowed_outside=()) -> bool:
    """Delete a file or folder that the engine or the panel made. Never the repository itself or a folder above it,
    and nothing outside it except the shortcuts the panel installed. True if something was removed."""
    path = Path(path)
    if not (path.exists() or path.is_symlink()):
        return False
    real, root = path.resolve(), Path(repo).resolve()
    inside = root in real.parents
    if real == root or real in root.parents or not (inside or str(path) in allowed_outside):
        raise ControlError(f"Refused to delete {path}: the panel deletes only what it or the engine made.")
    try:
        if path.is_dir() and not path.is_symlink():
            _rmtree(path)
        else:
            path.unlink()
    except OSError as e:
        raise ControlError(f"Could not delete {path}: {e.strerror or e}. If a program still uses it (the server, or a "
                           f"window of Explorer or Finder open in it), close that and try again.") from None
    return True


# ---------------------------------------------------------------------------------------------- the launcher
def launcher_command(port, world, repo=REPO, windows=ON_WINDOWS) -> list:
    """The launcher of scripts/ as a person runs it, without a browser: it makes .venv, installs the packages and
    builds the world when they are missing, then serves. The panel repeats none of that."""
    repo = Path(repo)
    if windows:
        shell = shutil.which("powershell") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                                           "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / "run.ps1"),
                "-NoBrowser", "-Port", str(port), "-World", str(world)]
    return ["/bin/sh", str(repo / "scripts" / "run.sh"), "--no-browser", "--port", str(port), "--world", str(world)]


def step_state(line):
    """The state a line of the launcher's output starts, or None."""
    for prefix, state in STEP_STATES:
        if line.startswith(prefix):
            return state
    return None


def error_line(lines) -> str:
    """The line that says best why the launcher stopped: a refusal or an error if there is one, else the last line."""
    lines = [ln.strip() for ln in lines if ln.strip()]
    for ln in reversed(lines):
        low = ln.lower()
        if low.startswith(("refused", "error", "no python", "could not", "the packages did not", "this is an intel mac")) \
                or "error:" in low:
            return ln
    return lines[-1] if lines else "the launcher stopped without saying why"


@dataclass
class Status:
    state: str
    detail: str = ""
    url: str = None
    world: str = None
    pid: int = None
    started_at: float = None
    version: str = None
    owned: bool = False            # started by this panel (its launcher is the panel's child)
    can_stop: bool = False         # something the panel can stop: its own launcher, or a server with a run file

    @property
    def uptime(self) -> str:
        if not self.started_at:
            return ""
        s = max(0, int(time.time() - self.started_at))
        if s < 60:
            return f"{s} s"
        if s < 3600:
            return f"{s // 60} min"
        return f"{s // 3600} h {s % 3600 // 60} min"


BUTTONS = ("start", "stop", "browser", "upgrade", "rebuild", "reset", "delete", "folder", "install", "copy")


def button_states(st: Status, action=None) -> dict:
    """Which buttons make sense now: each name of BUTTONS to True (enabled) or False. `action` is the name of an action
    of the panel that is still running; while one runs, only the harmless buttons work."""
    starting = st.state in (INSTALLING, BUILDING, STARTING)
    idle = action is None and st.state not in (STOPPING, WORKING)
    # what changes files: allowed when nothing runs, or when what runs can be stopped first
    may_change = idle and not starting and (st.state in (STOPPED, ERROR) or st.can_stop)
    return {"start": idle and st.state in (STOPPED, ERROR) and not st.can_stop,
            "stop": idle and (st.state in (RUNNING, ERROR) or starting) and st.can_stop,
            "browser": st.state == RUNNING,
            "upgrade": may_change, "rebuild": may_change, "reset": may_change, "delete": may_change,
            "folder": True, "install": action is None, "copy": True,
            "settings": idle and st.state in (STOPPED, ERROR) and not st.can_stop}


@dataclass
class UpgradeResult:
    changed: bool                # the code of this copy changed
    message: str
    output: str = ""
    deleted: list = field(default_factory=list)
    panel_changed: bool = False  # the panel's own code changed too: it must be opened again to use it


@dataclass
class Version:
    """One version of the engine: a branch of the repository this copy was cloned from, at its newest commit there."""
    branch: str                  # "" for a copy that is on no branch (it holds one commit, checked out by its id)
    commit: str
    date: str = ""               # of the commit, as 2026-11-12
    subject: str = ""            # the first line of what the commit says
    current: bool = False        # the branch this copy is on
    behind: int = 0              # for the current branch: the commits of the newest version that this copy lacks

    @property
    def label(self) -> str:
        return f"{self.branch}   ({self.date})"


class Controller:
    """The panel's actions. Each runs to its end (the window calls them from a worker thread); status() may be called
    from another thread at the same time."""

    def __init__(self, repo=REPO, launcher=None):
        self.repo = Path(repo)
        self.settings = load_settings(self.repo)
        self._launcher = launcher                  # a command in place of the launcher of scripts/ (tests)
        self._lock = threading.RLock()
        self._child = None
        self._child_stopped = False                # the panel stopped its child: its exit is not an error
        self._busy = None                          # (state, detail) while an action runs
        self._step = None                          # the launcher's latest step
        self._log_pos = 0
        self._log_lines = []                       # the launcher's output, for the window and for errors
        self._pending = []                         # the output not yet taken by the window
        self._error = None
        self._git_lock = threading.RLock()         # one of the panel's threads changes the clone at a time

    # ------------------------------------------------------------------ settings
    @property
    def port(self) -> int:
        return int(self.settings["port"])

    @property
    def world(self) -> str:
        return self.settings["world"]

    def world_path(self, world=None) -> Path:
        p = Path(world or self.world)
        return p if p.is_absolute() else self.repo / p

    def set_settings(self, port=None, world=None):
        if port is not None:
            self.settings["port"] = check_port(port)
        if world is not None and str(world).strip():
            self.settings["world"] = str(world).strip()
        try:
            save_settings(self.settings, self.repo)
        except OSError:
            pass                                    # a folder that cannot be written: the settings last this session

    @property
    def log_path(self) -> Path:
        return run_dir(self.repo) / "launcher.log"

    # ------------------------------------------------------------------ the launcher's output
    def _pump(self):
        """Read what the launcher wrote since the last call, note its step, and keep it for the window."""
        with self._lock:
            try:
                with open(self.log_path, "rb") as f:
                    size = os.fstat(f.fileno()).st_size
                    if size < self._log_pos:        # a new start truncated it
                        self._log_pos = 0
                    f.seek(self._log_pos)
                    data = f.read()
            except OSError:
                return
            # keep a line that is still being written for the next call
            cut = data.rfind(b"\n") + 1
            if cut == 0:
                return
            self._log_pos += cut
            text = data[:cut].decode("utf-8", errors="replace").replace("\r\n", "\n")
            for line in text.splitlines():
                self._log_lines.append(line)
                st = step_state(line)
                if st is not None:
                    self._step = st
            del self._log_lines[:-2000]
            self._pending.append(text)

    def take_output(self) -> str:
        """The launcher's output since the last call (for the window's Details)."""
        self._pump()
        with self._lock:
            out, self._pending = "".join(self._pending), []
        return out

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self._log_lines)

    # ------------------------------------------------------------------ status
    def child_running(self) -> bool:
        with self._lock:
            return self._child is not None and self._child.poll() is None

    def status(self) -> Status:
        """Ask the server whether it runs, and combine that with what the panel is doing."""
        port = self.port
        answer = probe(port)
        self._pump()
        if answer.kind != "engine":
            remove_stale_run_file(port, self.repo, answer)
        info = read_run_file(port, self.repo)
        with self._lock:
            child = self._child
            child_alive = child is not None and child.poll() is None
            if child is not None and not child_alive and not self._child_stopped and child.returncode not in (0, None):
                self._error = error_line(self._log_lines[-40:]) + f" (the launcher ended with exit code {child.returncode})"
                self._child = None
            elif child is not None and not child_alive:
                self._child = None
            busy, step, error = self._busy, self._step, self._error
        st = Status(STOPPED, owned=child_alive)
        if info:
            st.pid, st.started_at, st.version, st.url = info.get("pid"), info.get("started_at"), info.get("engine_version"), info.get("url")
            st.world = self._show(info.get("world"))
        st.can_stop = child_alive or bool(info and pid_alive(info.get("pid")))
        if busy:
            st.state, st.detail = busy
            return st
        if answer.kind == "engine" or (answer.kind == "busy" and info):
            st.state = RUNNING
            st.url = st.url or f"http://127.0.0.1:{port}/"
            if not st.world and answer.world:
                st.world = f"seed {answer.world.get('seed')}"
            st.detail = "busy answering; it runs" if answer.kind == "busy" else ""
            if not info and not child_alive:
                st.detail = ("started without a run file (an older engine, or another folder): the panel can open it, "
                             "but stop it only from where it was started")
            with self._lock:
                self._error = None
            return st
        if child_alive:
            st.state = step or STARTING
            st.detail = {INSTALLING: "Making the environment .venv and installing the packages (about 100 MB the first time)",
                         BUILDING: f"Building the world {self.world}: one to two minutes for the preview",
                         STARTING: "Starting the server"}.get(st.state, "")
            return st
        if answer.kind == "other":
            st.state, st.detail = ERROR, f"Another program uses port {port}. Close it, or choose another port."
            return st
        if error:
            st.state, st.detail = ERROR, error
            return st
        return st

    def _show(self, world):
        if not world:
            return None
        try:
            return Path(world).resolve().relative_to(self.repo.resolve()).as_posix()
        except ValueError:
            return str(world)

    # ------------------------------------------------------------------ actions
    def _doing(self, state, detail=""):
        with self._lock:
            self._busy = (state, detail) if state else None

    def start(self):
        """Run the launcher without a browser, detached from the panel so that the server outlives the panel if the
        person wants it to; its output goes to .worldengine/launcher.log, which the panel reads."""
        port = self.port
        if self.child_running():
            raise ControlError("The world engine is starting already.")
        if probe(port).kind == "engine":
            raise ControlError(f"The world engine runs already on port {port}.")
        if probe(port).kind == "other":
            raise ControlError(f"Another program uses port {port}. Close it, or choose another port in the panel.")
        cmd = self._launcher(port, self.world_path()) if callable(self._launcher) else \
            launcher_command(port, self.world_path(), self.repo)
        run_dir(self.repo).mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        kwargs = {"creationflags": NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if ON_WINDOWS else {"start_new_session": True}
        with self._lock:
            self._log_pos, self._step, self._error, self._child_stopped = 0, STARTING, None, False
            self._log_lines.append(f"--- Start: {' '.join(cmd)}")
            self._pending.append(f"--- Start: {' '.join(cmd)}\n")
            with open(self.log_path, "wb") as log:
                try:
                    self._child = subprocess.Popen(cmd, cwd=self.repo, stdin=subprocess.DEVNULL, stdout=log,
                                                   stderr=subprocess.STDOUT, env=env, **kwargs)
                except OSError as e:
                    raise ControlError(f"Could not run the launcher {cmd[0]}: {e.strerror or e}") from None

    def wait_running(self, timeout) -> bool:
        """Wait until the server answers, or the launcher ends (tests and the workflow)."""
        return wait_until(lambda: probe(self.port).kind == "engine" or
                          (self._child is not None and self._child.poll() is not None), timeout, 0.5) and \
            probe(self.port).kind == "engine"

    def stop(self, timeout=20.0) -> str:
        """Stop the engine on the panel's port: first by asking the server (POST /api/stop with the run file's token),
        then by ending the panel's own launcher, or the process the run file names. Checked by asking again."""
        port = self.port
        said = []
        self._doing(STOPPING, "Stopping the world engine")
        try:
            info = read_run_file(port, self.repo)
            if info and info.get("stop_token") and probe(port).kind in ("engine", "busy"):
                if ask_to_stop(port, info["stop_token"]):
                    said.append("the server was asked to stop and agreed")
                    wait_until(lambda: not pid_alive(info["pid"]) or probe(port, timeout=1).kind == "nothing", timeout)
            with self._lock:
                child = self._child
                self._child_stopped = True
            if child is not None and child.poll() is None:
                asked = bool(said)                          # after a clean stop the launcher ends by itself
                if not (asked and wait_until(lambda: child.poll() is not None, 5.0)):
                    said.append(end_process(child.pid, own_group=not ON_WINDOWS, timeout=timeout, child=child))
                try:
                    child.wait(10)
                except subprocess.TimeoutExpired:
                    pass
            info = read_run_file(port, self.repo)
            if info and pid_alive(info["pid"]) and probe(port, timeout=1).kind != "nothing":
                said.append(end_process(info["pid"], timeout=timeout))
            if not wait_until(lambda: probe(port, timeout=1).kind == "nothing", 10.0):
                kind = probe(port).kind
                if kind == "engine" and not read_run_file(port, self.repo):
                    raise ControlError(f"A world engine answers on port {port}, but it left no run file, so the panel "
                                       f"does not know which process it is. Stop it where it was started (Ctrl+C).")
                raise ControlError(f"Something still answers on port {port} after the stop.")
            remove_stale_run_file(port, self.repo)
            return "; ".join(said) or "nothing was running"
        finally:
            self._doing(None)

    def stop_if_running(self) -> str:
        if self.child_running() or probe(self.port).kind in ("engine", "busy"):
            return self.stop()
        return ""

    def building(self) -> bool:
        with self._lock:
            return self.child_running() and self._step == BUILDING

    def build_stop_warning(self) -> str:
        """What stopping in the middle of a build leaves (src/worldengine/store.py, save: a world is written to
        <name>.partial and given its name only when whole)."""
        w = self.world_path()
        return (f"The world {self.world} is being built. Stopping now throws away the build: the world is written to "
                f"disk only at its very end, so at most a folder {w.name}.partial is left, which the next start removes "
                f"before it builds the world again from the beginning.")

    def open_browser(self):
        st_url = (read_run_file(self.port, self.repo) or {}).get("url") or f"http://127.0.0.1:{self.port}/"
        webbrowser.open(st_url)
        return st_url

    # ------------------------------------------------------------------ upgrade, rebuild, reset, delete
    def _git(self, *args, timeout=300):
        git = shutil.which("git")
        if not git:
            raise ControlError("Git was not found. Install Git (Windows: winget install Git.Git; macOS: brew install git, "
                               "or the Xcode command line tools), then try again; or download the repository again.")
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # never wait for a password typed into a terminal nobody sees
        try:
            return subprocess.run([git, "-C", str(self.repo), *args], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", env=env, timeout=timeout, creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise ControlError(f"git {' '.join(args)} did not finish within {timeout} s.") from None

    def _need_clone(self, to="upgraded with git pull"):
        if not (self.repo / ".git").exists():
            raise ControlError(f"{self.repo} is not a Git clone, so it cannot be {to}. Download the new version into "
                               f"a new folder instead.")

    def _remote(self) -> str:
        """The name of the place this copy was cloned from (origin, unless somebody renamed it)."""
        names = self._git("remote").stdout.split()
        if not names:
            raise ControlError("This copy does not know where it was cloned from (git remote lists nothing), so there is "
                               "nowhere to fetch versions from. Clone the repository again into a new folder.")
        return "origin" if "origin" in names else names[0]

    def current_version(self):
        """The version this copy holds: its branch and its commit. None where that cannot be told (no Git, no clone)."""
        if not (self.repo / ".git").exists() or not shutil.which("git"):
            return None
        r = self._git("log", "-1", "--date=short", "--format=%H%x09%cd%x09%s")
        if r.returncode != 0 or not r.stdout.strip():
            return None
        commit, date, subject = (r.stdout.strip().split("\t", 2) + ["", ""])[:3]
        b = self._git("symbolic-ref", "--short", "-q", "HEAD")
        return Version(b.stdout.strip() if b.returncode == 0 else "", commit, date, subject, current=True)

    def _fetch(self, remote, log, timeout=300):
        """Learn of every branch of the remote and its newest commit. Changes no file of the folder, only what the
        clone knows of the remote (also in a clone that was made of one branch alone)."""
        log(f"$ git fetch --prune {remote}\n")
        r = self._git("fetch", "--prune", remote, f"+refs/heads/*:refs/remotes/{remote}/*", timeout=timeout)
        output = (r.stdout + r.stderr).strip()
        if output:
            log(output + "\n")
        if r.returncode != 0:
            raise ControlError(f"The versions could not be fetched (git fetch, exit code {r.returncode}). Is this "
                               f"computer online? Nothing was changed.\n\n{output[-1500:]}")

    def versions(self, fetch=True, log=lambda text: None, timeout=300) -> list:
        """The versions that can be chosen, the newest first: each branch of the repository this copy was cloned from.
        With `fetch` they are asked for there first (git fetch); without, the list is what the clone knew already."""
        self._need_clone("moved to another version")
        with self._git_lock:
            remote = self._remote()
            if fetch:
                self._fetch(remote, log, timeout)
            r = self._git("for-each-ref", "--sort=-committerdate", f"refs/remotes/{remote}", "--format="
                          "%(refname:lstrip=3)%09%(objectname)%09%(committerdate:short)%09%(subject)")
            if r.returncode != 0:
                raise ControlError(f"git for-each-ref failed (exit code {r.returncode}).\n\n{(r.stdout + r.stderr)[-1500:]}")
            here = self.current_version()
            found = []
            for line in r.stdout.splitlines():
                branch, commit, date, subject = (line.split("\t", 3) + ["", "", ""])[:4]
                if not branch or branch == "HEAD" or not commit:
                    continue
                v = Version(branch, commit, date, subject)
                if here is not None and here.branch == branch:
                    v.current = True
                    n = self._git("rev-list", "--count", f"HEAD..refs/remotes/{remote}/{branch}")
                    v.behind = int(n.stdout.strip()) if n.returncode == 0 and n.stdout.strip().isdigit() else 0
                found.append(v)
            return found

    def _pull(self, log) -> str:
        log("$ git pull --ff-only\n")
        r = self._git("pull", "--ff-only")
        output = (r.stdout + r.stderr).strip()
        log(output + "\n")
        if r.returncode != 0:
            low, hint = output.lower(), ""
            if "fast-forward" in low or "diverg" in low:
                hint = (" Your copy has commits of its own that the new version does not have, so it cannot simply "
                        "move forward. Nothing was changed. Ask for help, or keep your changes elsewhere and run "
                        "\"git reset --hard @{u}\" in the folder.")
            elif "would be overwritten" in low:
                hint = " Files you changed in the folder would be overwritten. Nothing was changed."
            elif "not currently on a branch" in low or "no tracking information" in low:
                hint = (" This copy follows no version of its own (it is on no branch, or on one that was never "
                        "published). Nothing was changed. Choose a version in the panel and upgrade to that one.")
            raise ControlError(f"git pull --ff-only failed (exit code {r.returncode}).{hint}\n\n{output[-1500:]}")
        return output

    def _switch(self, version, log) -> str:
        """Move this copy to the newest commit of the branch `version` of the remote. Either all of it happens or
        nothing does: the one command that changes files (git checkout -B) refuses as a whole."""
        remote = self._remote()
        self._fetch(remote, log)
        theirs = f"refs/remotes/{remote}/{version}"
        if version.startswith("-") or self._git("show-ref", "--verify", "--quiet", theirs).returncode != 0:
            raise ControlError(f"There is no version \"{version}\" at {remote}. Look for versions again and choose one of "
                               f"the list. Nothing was changed.")
        mine = f"refs/heads/{version}"
        if (self._git("show-ref", "--verify", "--quiet", mine).returncode == 0
                and self._git("merge-base", "--is-ancestor", mine, theirs).returncode != 0):
            raise ControlError(f"This copy has commits of its own on the version \"{version}\" that {remote} does not "
                               f"have, so it cannot simply move forward to it. Nothing was changed. Ask for help, or "
                               f"keep your changes elsewhere and delete your branch (git branch -D {version}).")
        log(f"$ git checkout -B {version} --track {remote}/{version}\n")
        r = self._git("checkout", "-B", version, "--track", theirs)
        output = (r.stdout + r.stderr).strip()
        log(output + "\n")
        if r.returncode != 0:
            hint = (" Files you changed or added in the folder would be overwritten. Nothing was changed."
                    if "would be overwritten" in output.lower() else "")
            raise ControlError(f"git checkout failed (exit code {r.returncode}).{hint}\n\n{output[-1500:]}")
        return output

    def upgrade(self, log=lambda text: None, version=None) -> UpgradeResult:
        """Stop the engine, fetch the new version, and delete the default world so that the next start builds it with
        the new engine (docs/RUNNING.md, section 4). The new version is the newest commit of the branch this copy is on
        (`git pull --ff-only`) or, with `version` the name of another branch, of that one, to which the copy switches.
        If git is missing or the fetch fails, nothing else is done."""
        self._need_clone()
        self._git("--version")
        here = self.current_version()
        switch = bool(version) and (here is None or version != here.branch)
        stopped = self.stop_if_running()
        if stopped:
            log(f"Stopped: {stopped}\n")
        self._doing(WORKING, f"Switching to the version {version}" if switch else "Upgrading: git pull --ff-only")
        try:
            with self._git_lock:
                before = self._git("rev-parse", "HEAD").stdout.strip()
                output = self._switch(version, log) if switch else self._pull(log)
                after = self._git("rev-parse", "HEAD").stdout.strip()
                now = f" This copy is now on the version {version}." if switch else ""
                if before == after:
                    if switch:
                        return UpgradeResult(False, f"{now.strip()} It holds the same code ({after[:8]}), so nothing else "
                                             f"was changed, and the world is kept.", output)
                    return UpgradeResult(False, "Already up to date: nothing was changed, and the world is kept.", output)
                panel_changed = self._git("diff", "--quiet", before, after, "--", "panel", "scripts").returncode != 0
            deleted = []
            for world in ENGINE_WORLDS:
                for p in (self.world_path(world), self.world_path(world + ".partial")):
                    if remove(p, self.repo):
                        deleted.append(p)
            msg = f"Upgraded from {before[:8]} to {after[:8]}.{now}"
            for world in ENGINE_WORLDS:
                if self.world_path(world) in deleted:
                    msg += f" The default world {world} was deleted, so the next start builds it with the new engine."
            if panel_changed:
                msg += " The control panel changed too: open it again to use its new version."
            return UpgradeResult(True, msg, output, deleted, panel_changed)
        finally:
            self._doing(None)

    def delete_world(self, world=None) -> Path:
        """Delete one world (a *.zarr folder) and what a stopped build left of it, for a rebuild."""
        p = self.world_path(world)
        if p.suffix != ".zarr":
            raise ControlError(f"{p} is not a world folder (its name must end in .zarr).")
        self.stop_if_running()
        self._doing(WORKING, f"Deleting the world {p.name}")
        try:
            remove(p, self.repo)
            remove(p.with_name(p.name + ".partial"), self.repo)
        finally:
            self._doing(None)
        return p

    def reset_environment(self) -> bool:
        """Delete .venv; the next start makes it again and installs the packages."""
        self.stop_if_running()
        self._doing(WORKING, "Deleting the environment .venv")
        try:
            return remove(self.repo / ".venv", self.repo)
        finally:
            self._doing(None)

    def delete_plan(self):
        """What Delete removes (each with a few words on it) and what it leaves, for the confirmation."""
        rd = run_dir(self.repo)
        gone = [(self.repo / ".venv", "the Python environment with the engine's packages (about 450 MB)"),
                (self.repo / "worlds", "every world built here (about 37 MB each)"),
                (rd, "the panel's settings, the launcher's output and the run files")]
        gone = [(p, what) for p, what in gone if p.exists()]
        for s in self.shortcut_paths():
            gone.append((Path(s), "a shortcut the panel installed"))
        kept = [(self.repo, "this folder itself, with the engine's code: delete it yourself after the panel has closed "
                            "(docs/RUNNING.md, section 5)"),
                (Path(sys.executable), "Python"), (Path(shutil.which("git") or "git"), "Git")]
        return gone, kept

    def shortcut_paths(self) -> list:
        """The shortcuts (or the app) the panel installed and that still exist and still point here."""
        out = []
        for s in self.settings.get("shortcuts", []):
            p = Path(s)
            if p.suffix == ".app":
                marker = p / "Contents" / "Resources" / "world-engine-repo.txt"
                try:
                    if marker.read_text(encoding="utf-8").strip() == str(self.repo):
                        out.append(str(p))
                except OSError:
                    pass
            elif p.exists():
                out.append(str(p))
        return out

    def delete_everything(self) -> list:
        """Stop the engine, then delete what delete_plan() lists. The repository folder stays."""
        gone, _ = self.delete_plan()
        self.stop_if_running()
        self._doing(WORKING, "Deleting")
        removed = []
        try:
            shortcuts = set(self.shortcut_paths())
            for p, _what in gone:
                if remove(p, self.repo, allowed_outside=shortcuts):
                    removed.append(p)
        finally:
            self._doing(None)
        with self._lock:
            self._log_pos, self._log_lines, self._pending = 0, [], []
        self.settings["shortcuts"] = []
        return removed

    # ------------------------------------------------------------------ shortcuts
    def _remember_shortcuts(self, paths):
        known = [s for s in self.settings.get("shortcuts", []) if s not in map(str, paths)]
        self.settings["shortcuts"] = known + [str(p) for p in paths]
        try:
            save_settings(self.settings, self.repo)
        except OSError:
            pass

    def install_shortcut(self, dest=None) -> list:
        """Windows: "World Engine.lnk" on the Desktop and in the Start menu (or in `dest`); macOS: the app
        ~/Applications/World Engine.app (or in `dest`). Returns the paths made."""
        if ON_WINDOWS:
            made = install_windows_shortcuts(self.repo, [dest] if dest else None)
        elif ON_MAC or dest:
            made = [install_mac_app(self.repo, dest)]
        else:
            raise ControlError("Shortcuts are made on Windows and macOS only; on Linux run: python3 panel/world_engine_panel.py")
        self._remember_shortcuts(made)
        return made


# ---------------------------------------------------------------------------------------------- shortcuts and the app
def panel_python(executable=None, windows=ON_WINDOWS) -> str:
    """The Python to start the panel with: pythonw.exe on Windows, which opens no console window."""
    exe = Path(executable or sys.executable)
    if windows and exe.name.lower() == "python.exe" and exe.with_name("pythonw.exe").exists():
        return str(exe.with_name("pythonw.exe"))
    return str(exe)


def panel_command(repo=REPO, executable=None, windows=ON_WINDOWS) -> list:
    """The command that opens the panel of this folder, with the Python that runs this one."""
    return [panel_python(executable, windows), str(Path(repo) / "panel" / "world_engine_panel.py")]


def open_panel_again(repo=REPO, command=None) -> subprocess.Popen:
    """Open a new panel that outlives this one (after an upgrade, the new one runs the panel's new code)."""
    cmd = command or panel_command(repo)
    kwargs = {"creationflags": NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if ON_WINDOWS else {"start_new_session": True}
    try:
        return subprocess.Popen(cmd, cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, **kwargs)
    except OSError as e:
        raise ControlError(f"Could not open the panel again ({cmd[0]}): {e.strerror or e}. Open it yourself.") from None


def install_windows_shortcuts(repo=REPO, dest_dirs=None) -> list:
    """Make "World Engine.lnk" with the app's icon, through the WScript.Shell object of Windows (from PowerShell): on
    the Desktop and in the Start menu's Programs, or in each of dest_dirs. Paths go through environment variables, so
    that no quoting can break them."""
    repo = Path(repo)
    script = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$dirs = @()
if ($env:WE_DEST) { $dirs = $env:WE_DEST -split ';' } else {
    $dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
}
foreach ($d in $dirs) {
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
    $path = Join-Path $d 'World Engine.lnk'
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $env:WE_TARGET
    $link.Arguments = '"' + $env:WE_SCRIPT + '"'
    $link.WorkingDirectory = $env:WE_REPO
    $link.IconLocation = $env:WE_ICON + ',0'
    $link.Description = 'World Engine: start, stop and upgrade the world engine'
    $link.Save()
    Write-Output $path
}
"""
    env = {**os.environ, "WE_TARGET": panel_python(windows=True), "WE_SCRIPT": str(repo / "panel" / "world_engine_panel.py"),
           "WE_REPO": str(repo), "WE_ICON": str(repo / "panel" / "assets" / "world-engine.ico"),
           "WE_DEST": ";".join(str(d) for d in dest_dirs) if dest_dirs else ""}
    shell = shutil.which("powershell") or "powershell"
    r = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True,
                       text=True, env=env, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise ControlError(f"The shortcut could not be made: {(r.stderr or r.stdout).strip()[-800:]}")
    return [Path(line.strip()) for line in r.stdout.splitlines() if line.strip().lower().endswith(".lnk")]


def app_launcher_script(repo, python) -> str:
    """The executable of World Engine.app: a shell script that runs the panel of this repository with the Python that
    installed the app. An app opened from the Finder starts with a short PATH (/usr/bin:/bin:/usr/sbin:/sbin), so the
    paths are absolute; if that Python has gone (an upgrade of Homebrew's), the usual places are tried."""
    return f"""#!/bin/sh
# Made by the World Engine control panel (panel/control.py, install_mac_app). It opens the panel of the repository
# below; move the repository and the app must be installed again from the panel.
REPO={shlex.quote(str(repo))}
PYTHON={shlex.quote(str(python))}
if [ ! -f "$REPO/panel/world_engine_panel.py" ]; then
    /usr/bin/osascript -e "display alert \\"World Engine\\" message \\"The folder $REPO is gone. Install the app again from the panel of the folder that holds the engine now.\\"" >/dev/null 2>&1
    exit 1
fi
if [ ! -x "$PYTHON" ]; then
    for p in /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \\
             /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if [ -x "$p" ] && "$p" -c "import tkinter" >/dev/null 2>&1; then PYTHON=$p; break; fi
    done
fi
exec "$PYTHON" "$REPO/panel/world_engine_panel.py" "$@"
"""


def install_mac_app(repo=REPO, dest=None, python=None) -> Path:
    """Make World Engine.app in ~/Applications (or in `dest`): Info.plist, the executable script above and the icon.
    The files are written here, not downloaded, so they carry no quarantine attribute for Gatekeeper to check
    (docs/RUNNING.md, "The control panel")."""
    repo = Path(repo).resolve()
    dest = Path(dest) if dest else Path.home() / "Applications"
    app = dest / f"{APP_NAME}.app"
    if app.exists():
        marker = app / "Contents" / "Resources" / "world-engine-repo.txt"
        if not marker.exists():
            raise ControlError(f"{app} exists and was not made by this panel; it is left alone. Move it away and try again.")
        _rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    info = {"CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME, "CFBundleExecutable": "world-engine",
            "CFBundleIdentifier": "local.world-engine.panel", "CFBundleIconFile": "world-engine.icns",
            "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1",
            "CFBundleInfoDictionaryVersion": "6.0", "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True}
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    exe = contents / "MacOS" / "world-engine"
    exe.write_text(app_launcher_script(repo, python or sys.executable), encoding="utf-8")
    exe.chmod(0o755)
    shutil.copyfile(repo / "panel" / "assets" / "world-engine.icns", contents / "Resources" / "world-engine.icns")
    (contents / "Resources" / "world-engine-repo.txt").write_text(str(repo) + "\n", encoding="utf-8")
    return app


def open_folder(path):
    """Show a folder (or a file) in Explorer or the Finder."""
    path = str(path)
    if ON_WINDOWS:
        os.startfile(path)                                       # noqa: the documented way on Windows
    elif ON_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
