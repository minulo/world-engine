"""External pushes (design, Layer 6).

An entry of interventions.yaml names a region and one or more pushes. A push on a field is
scheduled exactly like a process that modifies that field; a push on a group is one more
member of the sum. This module parses the entries, works out the weight of a region on the
mesh, and applies an operation. The scheduler decides when each push runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from .params import ParameterError

_OPS = ("set", "add", "scale", "cap_max", "cap_min")


@dataclass
class Condition:
    field: str
    lagged: bool
    test: str                 # is_one_of, is, above, below
    value: object
    month: int | None


@dataclass
class Region:
    circle: dict | None
    outline: list | None
    conditions: list
    edge_km: float

    @property
    def fixed(self) -> bool:
        return not self.conditions


@dataclass
class Push:
    entry_id: str
    index: int
    target: str               # field or group name
    on_group: bool
    op: str
    amount: object
    region: Region
    physical: bool
    reason: str
    rounds: tuple | None      # geological rounds it applies to (first, last), counted from the start
    id: str = field(init=False)

    def __post_init__(self):
        self.id = f"{self.entry_id}:{self.target}"

    def schedule_entry(self) -> dict:
        d = {"id": self.id, "op": self.op,
             "where": [c.field for c in self.region.conditions if not c.lagged],
             "where_lagged": [c.field for c in self.region.conditions if c.lagged]}
        d["group" if self.on_group else "field"] = self.target
        return d


def _conditions(spec, where: str) -> list:
    if spec is None:
        return []
    items = spec if isinstance(spec, list) else [spec]
    out = []
    for c in items:
        tests = [k for k in ("is_one_of", "is", "above", "below") if k in c]
        if len(tests) != 1:
            raise ParameterError(f"{where}: a condition needs exactly one of is_one_of, is, above, below")
        out.append(Condition(field=c["field"], lagged=bool(c.get("lagged", False)), test=tests[0],
                             value=c[tests[0]], month=c.get("month")))
    return out


def parse(entries, registry) -> list[Push]:
    """Turn the entries of interventions.yaml into pushes, in file order."""
    pushes, seen = [], set()
    for k, e in enumerate(entries or []):
        eid = e["id"]
        where = f"interventions.yaml[{k}] ({eid})"
        if eid in seen:
            raise ParameterError(f"{where}: the id {eid!r} is used twice")
        seen.add(eid)
        r = e.get("region") or {}
        region = Region(circle=r.get("circle"), outline=r.get("outline"),
                        conditions=_conditions(r.get("where"), where), edge_km=float(r.get("edge_km", 0.0)))
        if region.circle is None and region.outline is None and not region.conditions:
            raise ParameterError(f"{where}: the region needs a circle, an outline or a condition")
        when = e.get("when") or {}
        rounds = tuple(when["rounds"]) if "rounds" in when else None
        for i, p in enumerate(e["pushes"]):
            ops = [o for o in _OPS if o in p]
            if len(ops) != 1:
                raise ParameterError(f"{where}: push {i} needs exactly one operation ({', '.join(_OPS)})")
            on_group = "group" in p
            if on_group == ("field" in p):
                raise ParameterError(f"{where}: push {i} needs a field or a group, and not both")
            target = p["group"] if on_group else p["field"]
            push = Push(entry_id=eid, index=i, target=target, on_group=on_group, op=ops[0], amount=p[ops[0]],
                        region=region, physical=bool(e.get("physical", False)), reason=str(e.get("reason", "")), rounds=rounds)
            if any(q.id == push.id for q in pushes):
                raise ParameterError(f"{where}: two pushes of this entry target {target}")
            pushes.append(push)
    return pushes


def label_classes(pushes, registry) -> dict:
    """For each label field, the ids of the entries that set it, in file order."""
    out = {name: [] for name, spec in registry.fields.items() if spec.is_label}
    for p in pushes:
        if not p.on_group and p.target in out and p.entry_id not in out[p.target]:
            if p.amount != p.entry_id:
                raise ParameterError(f"push {p.id}: a label field holds the id of the entry that sets it; "
                                     f"write set: {p.entry_id}")
            out[p.target].append(p.entry_id)
    return out


def _unit(lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def _inside_outline(xyz, outline) -> np.ndarray:
    """Cells inside an outline given as [lat, lon] corners: the angles that the sides subtend at a
    cell add up to a full turn inside and to nothing outside. The outline must be smaller than a hemisphere."""
    pts = np.array([_unit(la, lo) for la, lo in outline])
    total = np.zeros(xyz.shape[0])
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        pa, pb = xyz @ a, xyz @ b
        total += np.arctan2(xyz @ np.cross(a, b), (a @ b) - pa * pb)
    centre = pts.sum(axis=0)
    return (np.abs(total) > np.pi) & (xyz @ centre > 0.0)       # the far side of the sphere is outside


def region_weights(push_region: Region, mesh, radius_m: float, read_condition, number_like: bool) -> np.ndarray:
    """Weight of the region in every cell: 1 inside, fading to 0 across the edge, 0 outside.

    read_condition(cond) returns the field values the condition tests (per cell, or month by cell).
    The fade is used only for number fields, directions and groups; a category or true-or-false
    field takes the bare region.
    """
    n = mesh.n
    inside = np.ones(n, dtype=bool)
    dist_out = None                                    # metres outside the shape, where known exactly
    if push_region.circle is not None:
        c = push_region.circle
        centre = _unit(c["lat"], c["lon"])
        d = 2.0 * np.arcsin(np.clip(0.5 * np.linalg.norm(mesh.xyz - centre, axis=1), 0, 1)) * radius_m
        inside &= d <= c["radius_km"] * 1000.0
        dist_out = np.maximum(d - c["radius_km"] * 1000.0, 0.0)
    if push_region.outline is not None:
        inside &= _inside_outline(mesh.xyz, push_region.outline)
        dist_out = None
    for cond in push_region.conditions:
        v = np.asarray(read_condition(cond))
        if v.ndim == 2:                                 # a monthly field: one month, or the yearly mean
            if cond.month is not None:
                v = v[int(cond.month) - 1]
            elif cond.test in ("above", "below"):
                v = v.mean(axis=0)
            else:
                raise ParameterError(f"a condition on the monthly field {cond.field} with {cond.test} needs a month")
        if cond.test == "is_one_of":
            ok = np.isin(v, np.asarray(cond.value))
        elif cond.test == "is":
            ok = v == cond.value
        elif cond.test == "above":
            ok = v > cond.value
        else:
            ok = v < cond.value
        inside &= ok
        dist_out = None
    w = inside.astype(np.float64)
    edge = push_region.edge_km * 1000.0
    if number_like and edge > 0.0 and inside.any() and not inside.all():
        if dist_out is None:                            # distance to the nearest cell of the region
            idx = np.flatnonzero(inside)
            chord, _ = cKDTree(mesh.xyz[idx]).query(mesh.xyz)
            dist_out = 2.0 * np.arcsin(np.clip(0.5 * chord, 0, 1)) * radius_m
        w = np.where(inside, 1.0, np.clip(1.0 - dist_out / edge, 0.0, 1.0))
    return w


def amount_array(push: Push, spec_kind: str, shape: tuple, months: int, mesh, code=None) -> np.ndarray:
    """The amount of a push laid out to match the target's shape."""
    a = push.amount
    if spec_kind == "category":
        return np.full(shape, code(a), dtype=np.int64)
    if spec_kind == "boolean":
        if not isinstance(a, bool):
            raise ParameterError(f"push {push.id}: a true-or-false field takes true or false, found {a!r}")
        return np.full(shape, a, dtype=bool)
    if spec_kind == "direction":
        if push.op == "scale":
            if isinstance(a, dict):
                raise ParameterError(f"push {push.id}: scale on a direction takes one number")
            return np.full(shape[:-1] + (1,), float(a))
        if not (isinstance(a, dict) and set(a) == {"east", "north"}):
            raise ParameterError(f"push {push.id}: a direction is given as its east and north parts")
        return np.broadcast_to(float(a["east"]) * mesh.east + float(a["north"]) * mesh.north, shape).copy()
    if isinstance(a, list):
        if len(shape) != 2 or len(a) != months:
            raise ParameterError(f"push {push.id}: one amount per month fits only a monthly target with {months} months")
        return np.broadcast_to(np.asarray(a, dtype=np.float64)[:, None], shape).copy()
    if isinstance(a, bool) or not isinstance(a, (int, float)):
        raise ParameterError(f"push {push.id}: the amount {a!r} is not a number")
    return np.full(shape, float(a))


def apply_op(op: str, old: np.ndarray, amount: np.ndarray, weight: np.ndarray, kind: str) -> np.ndarray:
    """The pushed value. Inside the fade the result is a weighted mix of the pushed and the unpushed value."""
    if kind in ("category", "boolean"):
        w = weight > 0.5
        w = w if old.ndim == 1 else np.broadcast_to(w, old.shape)
        return np.where(w, amount, old)
    old = old.astype(np.float64)
    if op == "set":
        new = np.broadcast_to(amount, old.shape)
    elif op == "add":
        new = old + amount
    elif op == "scale":
        new = old * amount
    elif op == "cap_max":
        new = np.minimum(old, amount)
    elif op == "cap_min":
        new = np.maximum(old, amount)
    else:
        raise ParameterError(f"the operation {op} does not exist")
    w = weight
    if kind == "direction":
        w = weight[:, None] if old.ndim == 2 else weight[None, :, None]
    elif old.ndim == 2:
        w = weight[None, :]
    return old + w * (new - old)
