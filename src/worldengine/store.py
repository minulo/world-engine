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
from pathlib import Path

import numpy as np
import zarr

from . import __version__

FORMAT = 1
_PACKAGES = ("numpy", "scipy", "numba", "llvmlite", "zarr", "numcodecs", "PyYAML", "threadpoolctl")


def code_fingerprint() -> str:
    """SHA-256 over the engine's own source files, in name order."""
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def lock_fingerprint() -> str | None:
    lock = Path(__file__).resolve().parents[2] / "requirements.lock"
    return hashlib.sha256(lock.read_bytes()).hexdigest()[:16] if lock.exists() else None


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


def _put(group, name, array):
    a = np.ascontiguousarray(array)
    if a.dtype == np.bool_:
        a = a.astype(np.uint8)
    chunks = a.shape if a.ndim == 1 or a.nbytes <= 8_000_000 else (1,) + a.shape[1:]
    arr = group.create_array(name=name, shape=a.shape, dtype=a.dtype, chunks=chunks)
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
        "lineage": world.lineage, "notices": world.notices, "settle_log": world.settle_log[-3:],
        "explanations": engine.params["explanations"], "category_colors": category_colors(engine),
        "models": {slot: {k: cfg.get(k) for k in ("implementation", "model", "ignores", "wrong_where")} for slot, cfg in slots.items()},
        "drivers": {f: sorted(t) for f, t in world.drivers.items()},
        "additive": sorted({f for p in engine.procs.values() for f in p.additive}),
        "pushes": {pid: {k: v for k, v in rec.items() if not isinstance(v, np.ndarray)} for pid, rec in world.push_records.items()},
        "timings": world.timings, "fingerprints": world.fingerprints(), "world_fingerprint": world.fingerprint(),
    })


def save(world, engine, path) -> Path:
    """Write a finished world. Refuses to overwrite an existing store."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; a world store is written once and never changed")
    root = zarr.open_group(store=str(path), mode="w")
    root.attrs.update(world_attributes(world, engine))
    mesh = root.create_group("mesh")
    for name in ("xyz", "nbr", "nbr_count", "area", "lat", "lon", "east", "north"):
        _put(mesh, name, getattr(world.mesh, name))
    g = root.create_group("fields")
    for name in sorted(world.fields):
        _put(g, name, world.fields[name])
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
            _put(fg, term, world.drivers[f][term])
    pg = causes.create_group("pushes")
    for k, pid in enumerate(sorted(world.push_records)):
        rec = world.push_records[pid]
        rg = pg.create_group(f"p{k}")
        rg.attrs.update({"id": pid})
        _put(rg, "weight", rec["weight"])
        if "before" in rec:
            _put(rg, "before", rec["before"])
    return path


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


class StoreView(WorldView):
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"no world store at {self.path}")
        self._root = zarr.open_group(store=str(self.path), mode="r")
        self.attrs = dict(self._root.attrs)
        self._bool = {n for n, s in self.attrs["fields"].items() if s["kind"] == "boolean"}
        self._push_group = {self._root["causes/pushes"][k].attrs["id"]: k for k in self._root["causes/pushes"].group_keys()}

    def field(self, name):
        a = self._root["fields"][name][...]
        return a.astype(bool) if name in self._bool else a

    def field_names(self):
        return sorted(self._root["fields"].array_keys())

    def driver(self, field, term):
        return self._root["causes/drivers"][field][term][...]

    def table(self, name):
        g = self._root["tables"][name]
        return {c: g[c][...] for c in sorted(g.array_keys())}

    def push_arrays(self, push_id):
        g = self._root["causes/pushes"][self._push_group[push_id]]
        return {c: g[c][...] for c in g.array_keys()}

    def mesh_array(self, name):
        return self._root["mesh"][name][...]

    def fingerprints(self) -> dict:
        """Recomputed from the stored bytes, for comparison with the fingerprints kept at build time."""
        out = {}
        for name in self.field_names():
            out[name] = hashlib.sha256(np.ascontiguousarray(self.field(name)).tobytes()).hexdigest()
        return out
