"""The field dictionary: what fields.yaml and tables.yaml declare (design, Layer 1).

A field is a named array with one value per cell. Some fields have a second axis (one slice
per month) or hold the 3 components of a direction. A field is rounded to its stored type
when written, and every reader gets that stored value.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import ParameterError

KINDS = ("number", "direction", "category", "boolean", "index")
SHAPES = ("cell", "month_cell", "day_cell")
_DEFAULT_DTYPE = {"number": "float32", "direction": "float32", "category": "int16", "boolean": "bool", "index": "int32"}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    family: str
    unit: str
    shape: str
    kind: str
    dtype: str
    default: object
    range: tuple | None
    categories: tuple | None
    label_stage: str | None
    allow_missing: bool
    pushable: bool
    settle: dict | None
    description: str

    @property
    def is_label(self) -> bool:
        return self.label_stage is not None

    @property
    def structural(self) -> bool:
        """A field whose values must obey a rule a push cannot see: mesh geometry, or the number of a cell or item."""
        return self.family == "Geometry" or self.kind == "index" or not self.pushable

    def array_shape(self, n_cells: int, months: int) -> tuple:
        s = (n_cells,) if self.shape == "cell" else (months, n_cells) if self.shape == "month_cell" else (n_cells,)
        return s + (3,) if self.kind == "direction" else s

    def code(self, category) -> int:
        try:
            return self.categories.index(category)
        except ValueError:
            raise ParameterError(f"{category!r} is not a class of {self.name} (classes: {', '.join(self.categories)})") from None

    def default_array(self, n_cells: int, months: int) -> np.ndarray:
        d = self.default
        if self.kind == "category":
            d = self.code(d)
        return np.full(self.array_shape(n_cells, months), d, dtype=self.dtype)

    def cast(self, value, n_cells: int, months: int) -> np.ndarray:
        """Round a computed value to the stored type and check its shape. Returns a new read-only array."""
        want = self.array_shape(n_cells, months)
        a = np.asarray(value)
        if a.shape != want:
            raise ValueError(f"{self.name} must have shape {want}, got {a.shape}")
        if self.kind in ("category", "index", "boolean") and a.dtype.kind == "f":
            raise ValueError(f"{self.name} is of kind {self.kind} and cannot take fractional values")
        out = np.array(a, dtype=self.dtype, order="C", copy=True)
        if out.dtype.kind in "iu" and a.dtype.kind in "iu" and a.size and not np.array_equal(out, a):
            raise ValueError(f"{self.name} is stored as {self.dtype}, which cannot hold every value given "
                             f"(from {int(a.min())} to {int(a.max())}); they would be changed without a word")
        out.flags.writeable = False
        return out

    def outside_range(self, a: np.ndarray):
        """Count of values outside the valid range, with the extremes found; None if all are inside."""
        if self.kind == "category":
            bad = (a < 0) | (a >= len(self.categories))
            return {"count": int(bad.sum())} if bad.any() else None
        if self.kind in ("boolean", "index"):
            return None
        finite = np.isfinite(a) if a.dtype.kind == "f" else np.ones(a.shape, dtype=bool)
        infinite = int(np.isinf(a).sum()) if a.dtype.kind == "f" else 0
        missing = int((~finite).sum()) - infinite
        out = {}
        if missing and not self.allow_missing:
            out["missing"] = missing
        if infinite:                                         # a missing value may be allowed; an endless one never is
            out["infinite"] = infinite
        if self.range is not None and finite.any():
            lo, hi = self.range
            v = a[finite]
            below, above = int((v < lo).sum()), int((v > hi).sum())
            if below or above:
                out.update(count=below + above, lowest=float(v.min()), highest=float(v.max()), range=[lo, hi])
        return out or None


@dataclass(frozen=True)
class GroupSpec:
    name: str
    unit: str
    shape: str
    description: str

    def array_shape(self, n_cells: int, months: int) -> tuple:
        return (n_cells,) if self.shape == "cell" else (months, n_cells)


@dataclass(frozen=True)
class TableSpec:
    name: str                    # without the "table:" prefix
    columns: dict                # column -> dtype
    description: str


class Registry:
    """Fields, groups and tables as the data files declare them."""

    def __init__(self, params):
        self.fields: dict[str, FieldSpec] = {}
        self.groups: dict[str, GroupSpec] = {}
        self.tables: dict[str, TableSpec] = {}
        fy = params["fields"]
        for name, e in (fy.get("fields") or {}).items():
            kind = e["kind"]
            cats = e.get("categories")
            if "categories_from" in e:
                src = e["categories_from"]
                try:
                    cats = [c["name"] if isinstance(c, dict) else c for c in params[src["file"]][src["key"]]]
                except KeyError:
                    raise ParameterError(f"fields.yaml.fields.{name}: categories_from names {src}, which does not exist") from None
            label = e.get("label")
            if kind == "category" and not cats and not label:
                raise ParameterError(f"fields.yaml.fields.{name}: a category field needs its list of classes")
            if label and kind != "category":
                raise ParameterError(f"fields.yaml.fields.{name}: a label field must be of kind category")
            default = e.get("default", {"number": 0.0, "direction": 0.0, "boolean": False, "index": -1}.get(kind))
            if e.get("default") == "missing":
                if kind not in ("number", "direction"):
                    raise ParameterError(f"fields.yaml.fields.{name}: only a number or a direction can start as missing; "
                                         f"a field of kind {kind} has no way to store a missing value")
                default = float("nan")
            elif kind == "boolean" and not isinstance(default, bool):
                raise ParameterError(f"fields.yaml.fields.{name}: the default of a true-or-false field is true or false, found {default!r}")
            elif kind in ("number", "direction", "index") and (isinstance(default, bool) or not isinstance(default, (int, float))):
                raise ParameterError(f"fields.yaml.fields.{name}: the default {default!r} is not a number")
            if kind == "category":
                cats = list(cats or [])
                if label and "none" not in cats:
                    cats = ["none"] + cats
                default = default if default is not None else cats[0]
                if default not in cats:
                    raise ParameterError(f"fields.yaml.fields.{name}: the default {default!r} is not among its classes")
            self.fields[name] = FieldSpec(
                name=name, family=e["family"], unit=e["unit"], shape=e["shape"], kind=kind,
                dtype=e.get("dtype", _DEFAULT_DTYPE[kind]), default=default,
                range=tuple(e["range"]) if e.get("range") is not None else None,
                categories=tuple(cats) if cats is not None else None,
                label_stage=label["stage"] if label else None, allow_missing=bool(e.get("allow_missing", False)),
                pushable=bool(e.get("pushable", True)), settle=e.get("settle"), description=e.get("description", ""))
        for name, e in (fy.get("groups") or {}).items():
            self.groups[name] = GroupSpec(name=name, unit=e["unit"], shape=e["shape"], description=e.get("description", ""))
        for name, e in (params["tables"].get("tables") or {}).items():
            self.tables[name] = TableSpec(name=name, columns=dict(e["columns"]), description=e.get("description", ""))

    def with_label_classes(self, classes_by_field: dict):
        """Label fields hold the ids of the entries that set them; the push file decides the list."""
        for name, ids in classes_by_field.items():
            spec = self.fields[name]
            cats = ["none"] + [i for i in ids if i != "none"]
            self.fields[name] = FieldSpec(**{**spec.__dict__, "categories": tuple(cats)})

    def kind(self, name: str) -> str:
        return self.fields[name].kind if name in self.fields else "number"

    def structural(self, name: str) -> bool:
        return name in self.fields and self.fields[name].structural

    @property
    def labels(self) -> dict:
        return {n: s.label_stage for n, s in self.fields.items() if s.is_label}

    def table_names(self):
        return {"table:" + n for n in self.tables}
