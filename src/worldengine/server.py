"""The small local server (design, Question 8 and Layer 8).

It opens one world store for reading only, serves the viewer page, and answers what the page
asks for: field values, the values of one cell, and the "why" answers. It listens on this
machine only. Anything it keeps between requests equals what a fresh computation gives.
"""
from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from scipy.spatial import cKDTree

from . import __version__
from .causes import class_name, explain
from .store import StoreView, code_fingerprint, lock_fingerprint

VIEWER_DIR = Path(__file__).resolve().parents[2] / "viewer"


class WorldService:
    """Everything the page can ask for, as plain functions over a read-only world."""

    def __init__(self, view):
        self.view = view
        self._lock = threading.Lock()
        self._idmaps: dict[int, bytes] = {}
        self._stats: dict[str, dict] = {}
        self._fields: dict[str, np.ndarray] = {}
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
                "history": self.view.history() if hasattr(self.view, "history") else {"rounds": [], "times_my": [], "fields": []}}

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
        if spec["kind"] == "direction":
            if part == "east":
                a = np.einsum("ij,ij->i", a, self.view.mesh_array("east"))
            elif part == "north":
                a = np.einsum("ij,ij->i", a, self.view.mesh_array("north"))
            else:
                a = np.linalg.norm(a, axis=-1)
        return a

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

    def explain(self, cell: int, field: str) -> dict:
        return explain(self.view, cell, field)


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
            if url.path == "/api/field":
                month = _asked(q, "month", int) - 1 if "month" in q else None
                return self._send(200, s.field(_asked(q, "name"), month, q.get("part")), "application/octet-stream")
            if url.path == "/api/history":
                return self._send(200, s.history_field(_asked(q, "name"), _asked(q, "index", int)), "application/octet-stream")
            if url.path == "/api/stats":
                return self._json(s.stats(_asked(q, "name")))
            if url.path == "/api/cell":
                return self._json(s.cell(_asked(q, "id", int)))
            if url.path == "/api/explain":
                return self._json(s.explain(_asked(q, "cell", int), _asked(q, "field")))
            if url.path.startswith("/api/"):
                return self._json({"error": f"no such request: {url.path}"}, 404)
            rel = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            path = (self.viewer_dir / rel).resolve()
            if self.viewer_dir.resolve() not in path.parents or not path.is_file():
                return self._json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return self._send(200, path.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        except (_BadRequest, KeyError, IndexError) as e:    # a wrong request, or a field, cell or month the world does not have
            return self._json({"error": str(e).strip("'\"")}, 400)
        except Exception as e:                               # a fault of the engine: say so, and keep the connection whole
            return self._json({"error": f"the server could not answer ({type(e).__name__}: {e})"}, 500)


def make_server(store_path, host="127.0.0.1", port=8765, viewer_dir=None) -> ThreadingHTTPServer:
    """A server for one world store. Call serve_forever() on the result, and shutdown() to stop it."""
    service = WorldService(StoreView(store_path))
    handler = type("Handler", (_Handler,), {"service": service, "viewer_dir": Path(viewer_dir) if viewer_dir else VIEWER_DIR})
    return ThreadingHTTPServer((host, port), handler)
