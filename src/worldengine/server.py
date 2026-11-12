"""The small local server (design, Question 8 and Layer 8).

It opens one world store for reading only, serves the viewer page, and answers what the page
asks for: field values, the values of one cell, the "why" answers, and the weather of a day,
which it computes on request with the parameters the world was built with (build step 8), with
the cause records from which the "why" answers of that day are read. By default it listens on
this machine only; `serve --host 0.0.0.0` opens it to the network, which a container needs.
Anything it keeps between requests equals what a fresh computation gives.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from scipy.spatial import cKDTree

from . import __version__
from .causes import class_name, explain
from .store import StoreView, code_fingerprint, field_specs, lock_fingerprint
from .library.units import SECONDS_PER_DAY

VIEWER_DIR = Path(__file__).resolve().parents[2] / "viewer"

KEEP_DAYS = 2                   # the days of weather kept, with their cause records: the one shown and the one asked for next

# The types of the viewer's own files, fixed here. mimetypes reads them from the system, and on Windows from the
# registry, where another program may have set .js to text/plain [DOCUMENTED: Lib/mimetypes.py of Python 3.13, "on
# Windows, the default values are taken from the registry"]. A browser does not apply a style sheet sent as
# text/plain to a page in standards mode [DOCUMENTED: the HTML standard, the link type "stylesheet"]. Not run on Windows.
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


class WorldService:
    """Everything the page can ask for, as plain functions over a read-only world."""

    def __init__(self, view):
        self.view = view
        self._lock = threading.Lock()
        self._idmaps: dict[int, bytes] = {}
        self._stats: dict[str, dict] = {}
        self._fields: dict[str, np.ndarray] = {}
        self._weather_lock = threading.Lock()
        self._engine, self._engine_error, self._days = None, None, OrderedDict()
        self._set_threads()

    def _set_threads(self):
        try:
            from threadpoolctl import threadpool_limits
            self._limit = threadpool_limits(limits=int(self.view.meta.get("math_threads", 1)))
        except ImportError:
            self._limit = None

    def warnings(self) -> list:
        a, out = self.view.attrs, []
        if a.get("engine_version") != __version__:
            out.append(f"This world was built by engine version {a.get('engine_version')}; the running engine is {__version__}.")
        if a.get("code_fingerprint") != code_fingerprint():
            out.append("The engine's code has changed since this world was built, so answers computed now may differ from the build.")
        if a.get("lock_fingerprint") != lock_fingerprint():
            out.append("The lock file of package versions differs from the one this world was built with.")
        return out

    def _field(self, name):
        with self._lock:
            if name not in self._fields:
                if name not in self.view.field_names():
                    raise KeyError(f"the world holds no field named {name}")
                self._fields[name] = self.view.field(name)
            return self._fields[name]

    def world(self) -> dict:
        a = self.view.attrs
        stored = self.view.field_names()
        notices = []
        for nt in a.get("notices") or []:
            if nt["kind"] == "climate_not_settled":
                notices.append(f"The climate did not settle within {nt['rounds']} rounds. Its fields are a solver's unfinished working step.")
            elif nt["kind"] == "climate_rerun_not_settled":
                notices.append(f"The climate rerun inside the history after round {nt['after_round']} did not settle within "
                               f"{nt['rounds']} rounds; the rounds after it eroded with an unfinished climate.")
            elif nt["kind"] == "model_outside_range":
                notices.append(f"{nt['slot']} ran outside the range in which its model is expected to hold "
                               f"({nt['parameter']} = {nt['value']}, expected {nt['expected'][0]} to {nt['expected'][1]}).")
            elif nt["kind"] == "field_outside_range":
                notices.append(f"The field {nt['field']} left its valid range in some cells.")
            elif nt["kind"] == "push_touched_nothing":
                notices.append(f"The push {nt['push']} changed nothing" + (f": {nt['why']}." if nt.get("why") else ": its region covers no cell."))
            elif nt["kind"] == "process_note":
                notices.append(f"{nt['slot']} noted: {nt['what']}.")
            elif nt["kind"] == "run_time_over_limit":
                notices.append(f"The build took {nt['seconds']} seconds, more than the {nt['limit_s']} seconds its profile allows.")
        return {"meta": a["meta"], "planet": a["planet"], "seed": a["seed"],
                "fields": {n: a["fields"][n] for n in stored}, "lineage": a["lineage"], "models": a.get("models", {}),
                "notices": notices, "warnings": self.warnings(), "colors": a.get("category_colors", {}),
                "engine_version": a.get("engine_version"),
                "history": self.view.history() if hasattr(self.view, "history") else {"rounds": [], "times_my": [], "fields": []},
                "weather": self.weather_info()}

    # ------------------------------------------------------------------ the weather of a day
    def _weather_engine(self):
        """The engine that computes days, with the world's own parameters; made once, on the first request."""
        if self._engine is None and self._engine_error is None:
            try:
                from .engine import engine_for_store
                self._engine = engine_for_store(self.view)
            except Exception as e:                           # a world from another version: it still shows, without days
                self._engine_error = f"{type(e).__name__}: {e}"
        return self._engine

    def weather_info(self):
        """The fields of a day that the world can compute, or None if no process of it runs on the weather clock."""
        with self._weather_lock:
            eng = self._weather_engine()
        if eng is None:
            return {"fields": {}, "days_per_year": 0, "why_not": f"the days of this world cannot be computed: {self._engine_error}"}
        if not eng.weather_stages():
            return None
        specs = field_specs(eng)
        names = [f for f, st in eng.stage_of.items() if eng.clocks.get(st) == "weather" and f in specs]
        writers = {f: step for step, d in eng.decls.items() for f in d["writes"] if f in names}
        return {"fields": {f: specs[f] for f in names}, "writers": writers,
                "days_per_year": eng.params["planet"]["year_length_s"] / SECONDS_PER_DAY}

    def day_view(self, day):
        """The weather of a day with its cause records (Engine.day_view): worked out once for its field values and its
        "why" answers, which come out the same bit for bit as when the day is worked out alone."""
        if day < 0:
            raise IndexError(f"day {day} is before the first day, 0")
        from .engine import EngineError
        with self._weather_lock:
            eng = self._weather_engine()
            if eng is None:
                raise KeyError(f"the days of this world cannot be computed: {self._engine_error}")
            if day in self._days:
                self._days.move_to_end(day)
            else:
                try:
                    self._days[day] = eng.day_view(self.view, int(day))
                except EngineError as e:                     # a world without a weather stage
                    raise KeyError(str(e)) from None
                while len(self._days) > KEEP_DAYS:
                    self._days.popitem(last=False)
            return self._days[day], eng

    def weather(self, name, day, part=None) -> bytes:
        """One field of the weather of a day, for display (the speed or one part of a direction)."""
        view, eng = self.day_view(day)
        if name not in view.day_fields():
            raise KeyError(f"the weather of a day holds no field named {name}")
        return np.ascontiguousarray(self._part(view.field(name), eng.registry.fields[name].kind, part), dtype="<f4").tobytes()

    def _part(self, a, kind, part):
        if kind != "direction":
            return a
        if part == "east":
            return np.einsum("ij,ij->i", a, self.view.mesh_array("east"))
        if part == "north":
            return np.einsum("ij,ij->i", a, self.view.mesh_array("north"))
        return np.linalg.norm(a, axis=-1)

    def idmap(self, width: int) -> bytes:
        """For a flat grid of longitude and latitude, the cell nearest to each point (unsigned 32-bit, row 0 in the north)."""
        width = max(256, min(4096, int(width)))
        with self._lock:
            if width not in self._idmaps:
                height = width // 2
                lon = np.deg2rad(-180.0 + (np.arange(width) + 0.5) * 360.0 / width)
                lat = np.deg2rad(90.0 - (np.arange(height) + 0.5) * 180.0 / height)
                cl = np.cos(lat)[:, None]
                pts = np.stack([cl * np.cos(lon)[None, :], cl * np.sin(lon)[None, :],
                                np.broadcast_to(np.sin(lat)[:, None], (height, width))], axis=-1).reshape(-1, 3)
                _, idx = cKDTree(self.view.mesh_array("xyz")).query(pts)
                self._idmaps[width] = idx.astype("<u4").tobytes()
            return self._idmaps[width]

    def mesh(self, part: str) -> bytes:
        """The mesh, for a drawing that needs more than the nearest cell: "xyz", the centres of the cells as unit
        vectors (three 32-bit floats a cell), or "nbr", the neighbours of each cell (six 32-bit integers a cell,
        counter-clockwise, -1 where a cell has only five)."""
        if part not in MESH_PARTS:
            raise _BadRequest(f"the mesh has no part {part!r}: ask for {' or '.join(MESH_PARTS)}")
        return np.ascontiguousarray(self.view.mesh_array(part), dtype=MESH_PARTS[part]).tobytes()

    def _plane(self, name, month, part):
        """One value per cell for display: a month of a monthly field, the speed or one part of a direction."""
        a = self._field(name)                                # says so if the world has no such field
        spec = self.view.specs[name]
        monthly = spec["shape"] == "month_cell"
        if monthly:
            m = int(month) if month is not None else 0
            if not (0 <= m < a.shape[0]):
                raise IndexError(f"month {m + 1} is outside 1 to {a.shape[0]}")
            a = a[m]
        return self._part(a, spec["kind"], part)

    def history_field(self, name, index) -> bytes:
        """One picture of the geological history of a field."""
        h = self.view.history()
        if name not in h["fields"]:
            raise KeyError(f"the history holds no pictures of {name}")
        a = self.view.history_field(name)
        if not (0 <= index < a.shape[0]):
            raise IndexError(f"picture {index} is outside 0 to {a.shape[0] - 1}")
        return np.ascontiguousarray(a[index], dtype="<f4").tobytes()

    def field(self, name, month=None, part=None) -> bytes:
        return np.ascontiguousarray(self._plane(name, month, part), dtype="<f4").tobytes()

    def stats(self, name) -> dict:
        with self._lock:
            hit = self._stats.get(name)
        if hit is None:
            a = self._field(name)
            spec = self.view.specs[name]
            if spec["kind"] == "direction":
                a = np.linalg.norm(a, axis=-1)
            a = a.astype(np.float64)
            f = a[np.isfinite(a)]
            if f.size == 0:
                hit = {"min": None, "max": None, "low": None, "high": None, "top": None}
            else:
                lo, hi, top = np.percentile(f, [2.0, 98.0, 99.9])      # top: for fields a few cells of which hold most (a river)
                hit = {"min": float(f.min()), "max": float(f.max()), "low": float(lo), "high": float(hi), "top": float(top)}
            with self._lock:
                self._stats[name] = hit
        return hit

    def cell(self, cell: int) -> dict:
        n = self.view.meta["cells"]
        if not (0 <= cell < n):
            raise IndexError(f"cell {cell} is outside 0 to {n - 1}")
        out = {"cell": cell, "lat": float(self.view.mesh_array("lat")[cell]), "lon": float(self.view.mesh_array("lon")[cell]), "values": {}}
        east, north = self.view.mesh_array("east")[cell], self.view.mesh_array("north")[cell]
        for name in self.view.field_names():
            spec = self.view.specs[name]
            a = self._field(name)
            v = a[cell] if spec["shape"] != "month_cell" else a[:, cell]
            if spec["kind"] == "direction":
                v = np.stack([v @ east, v @ north], axis=-1)
            if spec["kind"] == "category":
                v = [class_name(spec["categories"], x) for x in np.atleast_1d(v)]
                v = v[0] if spec["shape"] != "month_cell" else v
            else:
                v = np.asarray(v, dtype=np.float64)
                v = [None if not np.isfinite(x) else float(x) for x in v.ravel()]
                if spec["shape"] != "month_cell" and spec["kind"] != "direction":
                    v = v[0]
            out["values"][name] = v
        return out

    def explain(self, cell: int, field: str, day=None) -> dict:
        """The "why" answer for a field in a cell; for a field of a day, the answer of that day."""
        spec = self.view.specs.get(field)
        daily = spec is not None and spec["shape"] == "day_cell"
        if day is None:
            return explain(self.view, cell, field)           # which refuses a field of a day, asked without one
        if spec is None:
            raise KeyError(f"the world holds no field named {field}")
        if not daily:
            raise KeyError(f"{field} is not a field of a day: ask for it without a day")
        n = self.view.meta["cells"]
        if not (0 <= cell < n):                              # before the day is worked out
            raise IndexError(f"cell {cell} is outside 0 to {n - 1}")
        return explain(self.day_view(day)[0], cell, field)


MESH_PARTS = {"xyz": "<f4", "nbr": "<i4"}       # what GET /api/mesh gives, and how each is written


class _BadRequest(Exception):
    """The request itself is wrong: a part is missing, or is not the kind of value it must be."""


def _asked(q, name, kind=str):
    """One part of a request, as text or as a whole number."""
    if name not in q:
        raise _BadRequest(f"the request needs {name}")
    try:
        return kind(q[name])
    except ValueError:
        raise _BadRequest(f"{name} must be a whole number, got {q[name]!r}") from None


class _Handler(BaseHTTPRequestHandler):
    service: WorldService = None
    viewer_dir: Path = VIEWER_DIR
    stop_token: str = None
    server_version = "WorldEngine/" + __version__

    def log_message(self, fmt, *args):                       # quiet by default
        pass

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        s = self.service
        try:
            if url.path == "/api/world":
                return self._json(s.world())
            if url.path == "/api/idmap":
                return self._send(200, s.idmap(_asked(q, "width", int) if "width" in q else 2048), "application/octet-stream")
            if url.path == "/api/mesh":
                return self._send(200, s.mesh(_asked(q, "part")), "application/octet-stream")
            if url.path == "/api/field":
                month = _asked(q, "month", int) - 1 if "month" in q else None
                return self._send(200, s.field(_asked(q, "name"), month, q.get("part")), "application/octet-stream")
            if url.path == "/api/history":
                return self._send(200, s.history_field(_asked(q, "name"), _asked(q, "index", int)), "application/octet-stream")
            if url.path == "/api/weather":
                return self._send(200, s.weather(_asked(q, "name"), _asked(q, "day", int), q.get("part")), "application/octet-stream")
            if url.path == "/api/stats":
                return self._json(s.stats(_asked(q, "name")))
            if url.path == "/api/cell":
                return self._json(s.cell(_asked(q, "id", int)))
            if url.path == "/api/explain":
                return self._json(s.explain(_asked(q, "cell", int), _asked(q, "field"), _asked(q, "day", int) if "day" in q else None))
            if url.path.startswith("/api/"):
                return self._json({"error": f"no such request: {url.path}"}, 404)
            rel = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            if "\\" in rel or ":" in rel:                      # on Windows a drive, a share or a stream: never looked up
                return self._json({"error": "not found"}, 404)
            path = (self.viewer_dir / rel).resolve()
            if self.viewer_dir.resolve() not in path.parents or not path.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return self._send(200, path.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        except (_BadRequest, KeyError, IndexError) as e:    # a wrong request, or a field, cell or month the world does not have
            said = e.args[0] if isinstance(e, KeyError) and e.args else str(e)    # (a KeyError's text is quoted; another's ends as written)
            return self._json({"error": str(said)}, 400)
        except Exception as e:                               # a fault of the engine: say so, and keep the connection whole
            return self._json({"error": f"the server could not answer ({type(e).__name__}: {e})"}, 500)


    def do_POST(self):
        """POST /api/stop, with the header X-World-Engine-Stop holding the token of the run file: the server stops as on
        Ctrl+C. For the control panel (panel/), which on Windows has no other clean way to stop a server it did not
        start. The token is in the run file only, which only this computer's user can read; and a header of its own
        makes a browser ask the server first (a CORS preflight, which this server never allows), so no web page sends it."""
        given = self.headers.get("X-World-Engine-Stop", "")
        if urlparse(self.path).path != "/api/stop" or not self.stop_token:
            return self._json({"error": f"no such request: POST {urlparse(self.path).path}"}, 404)
        if not hmac.compare_digest(given.encode("utf-8"), self.stop_token.encode("utf-8")):
            return self._json({"error": "the stop request needs the token of the run file"}, 403)
        self._json({"stopping": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()


class _Server(ThreadingHTTPServer):
    """The standard threaded server, except that a port another server listens on is refused on every system.
    HTTPServer asks for SO_REUSEADDR. On Linux and macOS that only lets a stopped server's port be taken again at once;
    on Windows it lets a second server take a port that another is still listening on [DOCUMENTED: Microsoft, "Using
    SO_REUSEADDR and SO_EXCLUSIVEADDRUSE", Winsock documentation]. On Windows the port is asked for alone instead
    [not run on Windows: the workflow .github/workflows/local-run.yml runs the test there]."""

    def server_bind(self):
        if sys.platform == "win32":
            self.allow_reuse_address = False
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(store_path, host="127.0.0.1", port=8765, viewer_dir=None, stop_token=None) -> ThreadingHTTPServer:
    """A server for one world store. Call serve_forever() on the result, and shutdown() to stop it. Port 0 takes a
    free port; server_address then holds the one taken. A port that is in use raises OSError. With a stop_token the
    server also stops when it is POSTed to /api/stop with that token (_Handler.do_POST)."""
    service = WorldService(StoreView(store_path))
    handler = type("Handler", (_Handler,), {"service": service, "viewer_dir": Path(viewer_dir) if viewer_dir else VIEWER_DIR,
                                            "stop_token": stop_token})
    return _Server((host, port), handler)


def run_dir():
    """The folder in which `serve` says that it runs, for the control panel (panel/control.py): <repository>/.worldengine,
    or the folder that WORLDENGINE_RUN_DIR names. None where the engine is not run from a repository."""
    if os.environ.get("WORLDENGINE_RUN_DIR"):
        return Path(os.environ["WORLDENGINE_RUN_DIR"])
    root = Path(__file__).resolve().parents[2]
    return root / ".worldengine" if (root / "pyproject.toml").is_file() else None


def write_run_file(server, store_path, stop_token=None):
    """Write <run_dir>/server-<port>.json, which tells the control panel that this process serves on the port: its pid,
    the address, the world, when it started, the engine's version and the token of POST /api/stop. Written whole or
    not at all; where the folder cannot be written (in the container, /app belongs to root) nothing is written, and
    None is returned."""
    folder = run_dir()
    if folder is None:
        return None
    host, port = server.server_address[:2]
    path = folder / f"server-{port}.json"
    info = {"pid": os.getpid(), "port": port, "host": host, "url": local_url(server), "world": str(Path(store_path).resolve()),
            "started_at": time.time(), "engine_version": __version__, "stop_token": stop_token}
    try:
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / f".server-{port}.json.{os.getpid()}"
        part.write_text(json.dumps(info, indent=1), encoding="utf-8")
        os.replace(part, path)
    except OSError:
        return None
    return path


def remove_run_file(path):
    """Remove the run file when the server stops (nothing happens if it is gone already)."""
    if path is not None:
        try:
            Path(path).unlink()
        except OSError:
            pass


def local_url(server) -> str:
    """The address at which a browser on this machine reaches the server (a server on every address, 0.0.0.0, is
    reached at 127.0.0.1)."""
    host, port = server.server_address[:2]
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"


def check(server, timeout_s=600) -> list:
    """Ask a running server for what the browser asks for first: the page, its two scripts and its style sheet with
    the types a browser accepts, and /api/world. Returns one line for each; raises RuntimeError if an answer is wrong. For the
    launchers' and the workflow's check that a world serves; no proxy is used, whatever the environment sets."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base, said = local_url(server), []
    for name, want, holds in (("", "text/html", b"World viewer"), ("viewer.js", "text/javascript", b"WebGL2"),
                              ("draw.js", "text/javascript", b"#version 300 es"), ("style.css", "text/css", b"")):
        with opener.open(base + name, timeout=timeout_s) as r:
            body, ctype = r.read(), r.headers.get_content_type()
        if ctype != want or holds not in body:
            raise RuntimeError(f"GET /{name} gave {len(body)} bytes of {ctype}; expected {want}" + (f" holding {holds.decode()}" if holds else ""))
        said.append(f"GET /{name} gave {len(body)} bytes of {ctype}")
    with opener.open(base + "api/world", timeout=timeout_s) as r:
        world = json.loads(r.read())
    cells, fields = world["meta"]["cells"], len(world["fields"])
    if not (cells > 0 and fields > 0):
        raise RuntimeError(f"GET /api/world gave a world of {cells} cells and {fields} fields")
    said.append(f"GET /api/world gave a world of {cells} cells, {fields} fields, seed {world['seed']}")
    return said
