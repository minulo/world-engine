"""The world store: one directory in Zarr, an open format for chunked, compressed arrays.

Design, Layer 1 and Layer 8. A world store holds the mesh, the fields, the tables, the cause
records, and a full copy of the seed and parameters that made it, with the code version, the
thread count and the fingerprint of the lock file. A world can therefore be rebuilt, and a
mismatch can be explained. The store is written once and never changed afterwards.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import shutil
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import zarr

from . import __version__

FORMAT = 1
CHUNK_BYTES = 8_000_000         # the store is cut into pieces of about this size
KEEP_BYTES = 512_000_000        # a view of a store keeps up to this much of what it has read
_PACKAGES = ("numpy", "scipy", "numba", "llvmlite", "zarr", "numcodecs", "PyYAML", "threadpoolctl")


def code_fingerprint(root=None) -> str:
    """SHA-256 over the engine's own source files (or the Python files under `root`), in name order. Names are
    taken with forward slashes and line ends as single line feeds, so that one checkout gives one fingerprint on
    every system."""
    root = Path(__file__).resolve().parent if root is None else Path(root)
    h = hashlib.sha256()
    for name, path in sorted((p.relative_to(root).as_posix(), p) for p in root.rglob("*.py")):
        h.update(name.encode("utf-8"))
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def lock_fingerprint(lock=None) -> str | None:
    """SHA-256 over the lock file of the pinned packages, line ends taken as single line feeds; None without one."""
    lock = Path(__file__).resolve().parents[2] / "requirements.lock" if lock is None else Path(lock)
    return hashlib.sha256(lock.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16] if lock.exists() else None


def package_versions() -> dict:
    out = {}
    for name in _PACKAGES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def _clean(value):
    """JSON cannot hold NaN or NumPy scalars."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def chunk_shape(shape: tuple, itemsize: int, months_first: bool) -> tuple:
    """How an array is cut into pieces in the store. An array with one slice per month is cut by month, so that the
    viewer can fetch one month; any array still larger than CHUNK_BYTES is cut along its cells into equal blocks.
    A piece never has a side of length zero (a table may have no rows)."""
    chunks = [max(1, int(c)) for c in shape]
    if not shape:
        return ()
    cells = 0
    if months_first and len(shape) > 1:
        chunks[0], cells = 1, 1
    size = itemsize * math.prod(chunks)
    if size > CHUNK_BYTES:
        per_cell = max(1, size // chunks[cells])
        chunks[cells] = max(1, min(chunks[cells], CHUNK_BYTES // per_cell))
    return tuple(chunks)


def _put(group, name, array, months=None, cells=None):
    """Store one array. `months` and `cells` are the world's counts: an array laid out month by cell is cut by month."""
    a = np.ascontiguousarray(array)
    if a.dtype == np.bool_:
        a = a.astype(np.uint8)
    months_first = a.ndim >= 2 and months is not None and a.shape[0] == months and a.shape[1] == cells
    arr = group.create_array(name=name, shape=a.shape, dtype=a.dtype, chunks=chunk_shape(a.shape, a.dtype.itemsize, months_first))
    arr[...] = a


def field_specs(engine) -> dict:
    out = {}
    for name, s in engine.registry.fields.items():
        out[name] = {"family": s.family, "unit": s.unit, "shape": s.shape, "kind": s.kind, "dtype": s.dtype,
                     "range": list(s.range) if s.range else None, "categories": list(s.categories) if s.categories else None,
                     "label": s.is_label, "description": s.description}
    return out


def category_colors(engine) -> dict:
    """Display colours of the classes of a category field, where its category file gives them."""
    out = {}
    for name, e in (engine.params["fields"].get("fields") or {}).items():
        src = e.get("categories_from")
        if src:
            items = engine.params[src["file"]][src["key"]]
            cols = [c.get("color") if isinstance(c, dict) else None for c in items]
            if any(cols):
                out[name] = cols
    return out


def world_attributes(world, engine) -> dict:
    slots = engine.params["models"].get("slots") or {}
    return _clean({
        "format": FORMAT, "engine_version": __version__, "code_fingerprint": code_fingerprint(),
        "lock_fingerprint": lock_fingerprint(), "packages": package_versions(),
        "meta": world.meta, "seed": engine.seed, "planet": engine.params["planet"],
        "parameters_text": engine.params.text, "fields": field_specs(engine),
        "groups": {g: {"unit": s.unit, "shape": s.shape, "description": s.description} for g, s in engine.registry.groups.items()},
        "tables": {t: {"columns": dict(s.columns), "description": s.description} for t, s in engine.registry.tables.items()},
        "lineage": world.lineage, "notices": world.notices, "settle_log": world.settle_log[-3:],
        "explanations": engine.params["explanations"], "category_colors": category_colors(engine),
        "models": {slot: {k: cfg.get(k) for k in ("implementation", "model", "ignores", "wrong_where")} for slot, cfg in slots.items()},
        "drivers": {f: sorted(t) for f, t in world.drivers.items()},
        "additive": sorted({f for p in engine.procs.values() for f in p.additive}),
        "pushes": {pid: {k: v for k, v in rec.items() if not isinstance(v, np.ndarray)} for pid, rec in world.push_records.items()},
        "push_activity": world.push_activity,
        "timings": world.timings, "round_times": world.round_times, "fingerprints": world.fingerprints(), "world_fingerprint": world.fingerprint(),
    })


def save(world, engine, path) -> Path:
    """Write a finished world. Refuses to overwrite an existing store. The store is written beside its final place
    and moved there only when it is whole, so that a failed write leaves nothing behind that looks like a world."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; a world store is written once and never changed")
    partial = path.with_name(path.name + ".partial")
    if partial.is_dir() and not partial.is_symlink():        # what a failed write left behind, whatever it is
        shutil.rmtree(partial)
    elif partial.exists() or partial.is_symlink():
        partial.unlink()
    try:
        _write(world, engine, partial)
        partial.rename(path)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return path


def _write(world, engine, path):
    months, cells = world.months, world.n
    root = zarr.open_group(store=str(path), mode="w")
    root.attrs.update(world_attributes(world, engine))
    mesh = root.create_group("mesh")
    for name in ("xyz", "nbr", "nbr_count", "area", "lat", "lon", "east", "north"):
        _put(mesh, name, getattr(world.mesh, name))
    g = root.create_group("fields")
    for name in sorted(world.fields):
        _put(g, name, world.fields[name], months, cells)
    g = root.create_group("tables")
    for t in sorted(world.tables):
        tg = g.create_group(t)
        for col in sorted(world.tables[t]):
            _put(tg, col, world.tables[t][col])
    causes = root.create_group("causes")
    dg = causes.create_group("drivers")
    for f in sorted(world.drivers):
        fg = dg.create_group(f)
        for term in sorted(world.drivers[f]):
            _put(fg, term, world.drivers[f][term], months, cells)
    gg = causes.create_group("groups")
    for group in sorted(world.group_records):
        mg = gg.create_group(group)
        for j, member in enumerate(sorted(world.group_records[group])):
            arr = mg.create_group(f"m{j}")
            arr.attrs.update({"member": member})
            _put(arr, "value", world.group_records[group][member], months, cells)
    pg = causes.create_group("pushes")
    for k, pid in enumerate(sorted(world.push_records)):
        rec = world.push_records[pid]
        rg = pg.create_group(f"p{k}")
        rg.attrs.update({"id": pid})
        _put(rg, "weight", rec["weight"])
        if "before" in rec:
            _put(rg, "before", rec["before"], months, cells)


class WorldView:
    """Read-only access to a world, whether in memory or in a store. The server, the viewer's
    answers and explain() all go through this, so they cannot change a world."""

    attrs: dict

    @property
    def meta(self):
        return self.attrs["meta"]

    @property
    def specs(self):
        return self.attrs["fields"]

    def field(self, name) -> np.ndarray:
        raise NotImplementedError

    def field_names(self) -> list:
        raise NotImplementedError

    def driver(self, field, term) -> np.ndarray:
        raise NotImplementedError

    def table(self, name) -> dict:
        raise NotImplementedError

    def push_arrays(self, push_id) -> dict:
        raise NotImplementedError

    def mesh_array(self, name) -> np.ndarray:
        raise NotImplementedError

    def group_members(self, group) -> dict:
        """The members of a group as its reader received them in the recorded pass: member -> array."""
        raise NotImplementedError


class MemoryView(WorldView):
    def __init__(self, world, engine):
        self._w = world
        self.attrs = json.loads(json.dumps(world_attributes(world, engine)))

    def field(self, name):
        return self._w.fields[name]

    def field_names(self):
        return sorted(self._w.fields)

    def driver(self, field, term):
        return self._w.drivers[field][term]

    def table(self, name):
        return self._w.tables[name]

    def push_arrays(self, push_id):
        return {k: v for k, v in self._w.push_records[push_id].items() if isinstance(v, np.ndarray)}

    def mesh_array(self, name):
        return getattr(self._w.mesh, name)

    def group_members(self, group):
        return dict(self._w.group_records.get(group, {}))


class StoreView(WorldView):
    """A world store on disk, read only. What has been read is kept, up to KEEP_BYTES, so that one "why" answer after
    another does not read the same arrays again: a store is written once and never changes."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"no world store at {self.path}")
        self._root = zarr.open_group(store=str(self.path), mode="r")
        self.attrs = dict(self._root.attrs)
        self._bool = {n for n, s in self.attrs["fields"].items() if s["kind"] == "boolean"}
        self._bool_columns = {(t, c) for t, s in (self.attrs.get("tables") or {}).items()
                              for c, kind in s["columns"].items() if kind == "bool"}
        self._push_group = {self._root["causes/pushes"][k].attrs["id"]: k for k in self._root["causes/pushes"].group_keys()}
        self._kept, self._kept_bytes, self._lock = OrderedDict(), 0, threading.Lock()

    def _keep(self, key, read):
        """What `read` returns (an array, or a dict of arrays), read once and kept while there is room."""
        with self._lock:
            if key in self._kept:
                self._kept.move_to_end(key)
                return self._kept[key]
        value = read()
        arrays = list(value.values()) if isinstance(value, dict) else [value]
        for a in arrays:
            a.flags.writeable = False                        # one copy is handed to every caller
        size = sum(a.nbytes for a in arrays)
        with self._lock:
            if key not in self._kept and size <= KEEP_BYTES:
                self._kept[key] = value
                self._kept_bytes += size
                while self._kept_bytes > KEEP_BYTES:
                    _, old = self._kept.popitem(last=False)
                    self._kept_bytes -= sum(a.nbytes for a in (old.values() if isinstance(old, dict) else [old]))
        return value

    def field(self, name):
        def read():
            a = self._root["fields"][name][...]
            return a.astype(bool) if name in self._bool else a
        return self._keep(("field", name), read)

    def field_names(self):
        return sorted(self._root["fields"].array_keys())

    def driver(self, field, term):
        return self._keep(("driver", field, term), lambda: self._root["causes/drivers"][field][term][...])

    def table(self, name):
        def read():
            g = self._root["tables"][name]
            return {c: g[c][...].astype(bool) if (name, c) in self._bool_columns else g[c][...] for c in sorted(g.array_keys())}
        return dict(self._keep(("table", name), read))

    def push_arrays(self, push_id):
        def read():
            g = self._root["causes/pushes"][self._push_group[push_id]]
            out = {c: g[c][...] for c in g.array_keys()}
            if "before" in out and self.attrs["pushes"][push_id].get("field") in self._bool:
                out["before"] = out["before"].astype(bool)
            return out
        return dict(self._keep(("push", push_id), read))

    def mesh_array(self, name):
        return self._keep(("mesh", name), lambda: self._root["mesh"][name][...])

    def group_members(self, group):
        if group not in self._root["causes/groups"]:
            return {}

        def read():
            g = self._root["causes/groups"][group]
            return {g[k].attrs["member"]: g[k]["value"][...] for k in sorted(g.group_keys())}
        return dict(self._keep(("group", group), read))

    def fingerprints(self) -> dict:
        """Recomputed from the stored bytes, for comparison with the fingerprints kept at build time."""
        out = {}
        for name in self.field_names():
            out[name] = hashlib.sha256(np.ascontiguousarray(self.field(name)).tobytes()).hexdigest()
        return out
