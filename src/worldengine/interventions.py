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
_TESTS = {"is_one_of": ("category", "index", "boolean"), "is": ("category", "index", "boolean", "number"),
          "above": ("number", "index"), "below": ("number", "index")}
_CONDITION_KEYS = ("field", "lagged", "month", "is_one_of", "is", "above", "below")
MIN_CORNERS = 3
_PROBE = 1.0e-3            # how far beside a side the sense of an outline is probed, as a share of the side's length
_ON_A_SIDE = 1.0e-9        # a point nearer than this to a side of an outline (radians) lies on it, and counts as inside
_CAP_STEPS = 200           # steps of the search for the smallest cap that holds an outline's corners
_QUARTER_TURN_DEG, _HALF_TURN_DEG = 90.0, 180.0


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
        # A condition on the push's own target is no separate read: to modify a field is to read it and then change it.
        own = None if self.on_group else self.target
        d = {"id": self.id, "op": self.op,
             "where": sorted({c.field for c in self.region.conditions if not c.lagged and c.field != own}),
             "where_lagged": sorted({c.field for c in self.region.conditions if c.lagged})}
        d["group" if self.on_group else "field"] = self.target
        return d


def _conditions(spec, where: str) -> list:
    if spec is None:
        return []
    items = spec if isinstance(spec, list) else [spec]
    out = []
    for c in items:
        if not isinstance(c, dict):
            raise ParameterError(f"{where}: a condition is written as keys (field, one test, and if wanted month and lagged); "
                                 f"found {c!r}")
        unknown = sorted(str(k) for k in c if k not in _CONDITION_KEYS)
        if unknown:
            raise ParameterError(f"{where}: a condition has no key named {', '.join(unknown)} (it takes: {', '.join(_CONDITION_KEYS)})")
        if not isinstance(c.get("field"), str):
            raise ParameterError(f"{where}: a condition must name the field it tests")
        tests = [k for k in ("is_one_of", "is", "above", "below") if k in c]
        if len(tests) != 1:
            raise ParameterError(f"{where}: a condition needs exactly one of is_one_of, is, above, below")
        if not isinstance(c.get("lagged", False), bool):
            raise ParameterError(f"{where}: lagged is true or false, found {c['lagged']!r}")
        out.append(Condition(field=c["field"], lagged=c.get("lagged", False), test=tests[0],
                             value=c[tests[0]], month=c.get("month")))
    return out


def _cap_centre(pts) -> np.ndarray:
    """The middle of the smallest cap of the sphere that holds all the points, found by walking toward the farthest
    point in ever smaller steps (the method of Badoiu and Clarkson for the smallest ball). The mean of the points
    will not do: several corners close together pull it toward themselves, away from a far corner."""
    centre = pts.sum(axis=0)
    centre = pts[0].copy() if np.linalg.norm(centre) < _ON_A_SIDE else centre / np.linalg.norm(centre)
    for k in range(1, _CAP_STEPS + 1):
        farthest = pts[np.argmin(pts @ centre)]
        centre = centre + (farthest - centre) / (k + 1)
        size = np.linalg.norm(centre)
        if size < _ON_A_SIDE:                                # the points surround the planet: no cap smaller than half of it
            return -farthest
        centre /= size
    return centre


def outline_problems(outline) -> list:
    """What makes an outline unusable, as sentences; an empty list if it can be used. An outline is a list of
    [latitude, longitude] corners, joined by the shorter arcs between them; it must enclose an area smaller than half
    the planet, and its sides must not cross."""
    problems = []
    if any(not -_QUARTER_TURN_DEG <= la <= _QUARTER_TURN_DEG for la, _ in outline):
        problems.append("a corner has a latitude outside -90 to 90")
    if any(not -2 * _HALF_TURN_DEG <= lo <= 2 * _HALF_TURN_DEG for _, lo in outline):
        problems.append("a corner has a longitude outside -360 to 360")
    if problems:
        return problems
    pts = np.array([_unit(la, lo) for la, lo in outline])
    nxt = np.roll(pts, -1, axis=0)
    if np.any(np.linalg.norm(pts - nxt, axis=1) < _ON_A_SIDE):
        return ["two corners in a row are the same point"]
    if np.any(np.linalg.norm(pts + nxt, axis=1) < _ON_A_SIDE):
        return ["two corners in a row lie opposite each other on the planet, so the side between them is not defined"]
    if np.any(pts @ _cap_centre(pts) <= 0.0):
        return ["its corners do not fit inside half the planet; an outline must be smaller than a hemisphere"]
    # Just beside the middle of every side, one point must lie inside and the other outside, and the inside must be on
    # the same hand all the way round. Sides that cross, and an outline with no area, break this.
    hands = []
    for a, b in zip(pts, nxt):
        mid = (a + b) / np.linalg.norm(a + b)
        sideways = np.cross(mid, b - a)
        sideways /= np.linalg.norm(sideways)
        step = _PROBE * np.linalg.norm(b - a)
        pair = np.array([mid + step * sideways, mid - step * sideways])
        pair /= np.linalg.norm(pair, axis=1, keepdims=True)
        left, right = _turns(pair, pts)
        inside = (abs(left) > np.pi, abs(right) > np.pi)
        if inside[0] == inside[1]:
            return ["it encloses no area, or its sides cross"]
        hands.append(inside[0])
    if len(set(hands)) != 1:
        return ["its sides cross"]
    return problems


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
        sizes = {"edge_km": r.get("edge_km", 0.0), **({"circle.radius_km": r["circle"].get("radius_km")} if r.get("circle") else {})}
        for name, size in sizes.items():
            if isinstance(size, bool) or not isinstance(size, (int, float)) or not np.isfinite(size) or size < 0:
                raise ParameterError(f"{where}: region.{name} must be a length in km, zero or more and not infinite; got {size!r}")
        region = Region(circle=r.get("circle"), outline=r.get("outline"),
                        conditions=_conditions(r.get("where"), where), edge_km=float(r.get("edge_km", 0.0)))
        if region.circle is None and region.outline is None and not region.conditions:
            raise ParameterError(f"{where}: the region needs a circle, an outline or a condition")
        if region.outline is not None and len(region.outline) < MIN_CORNERS:
            raise ParameterError(f"{where}: an outline needs at least {MIN_CORNERS} corners")
        if region.outline is not None and outline_problems(region.outline):
            raise ParameterError(f"{where}: the outline cannot be used: {'; '.join(outline_problems(region.outline))}")
        when = e.get("when") or {}
        rounds = tuple(when["rounds"]) if "rounds" in when else None
        if rounds is not None and rounds[0] > rounds[1]:
            raise ParameterError(f"{where}: when.rounds gives the first round and then the last; {list(rounds)} runs backwards")
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


def check(push: Push, registry, months: int) -> list:
    """Everything about a push that can be judged before a world exists: what its conditions test, and whether its
    amount fits its target. Returns the problems found, as sentences."""
    problems = []
    for c in push.region.conditions:
        spec = registry.fields.get(c.field)
        if spec is None:
            continue                                        # named already by the caller
        if spec.kind not in _TESTS[c.test]:
            problems.append(f"push {push.id}: the test {c.test} cannot be made on {c.field}, a field of kind {spec.kind} "
                            f"(it applies to: {', '.join(_TESTS[c.test])})")
            continue
        monthly = spec.shape == "month_cell"
        if c.month is not None:
            if not monthly:
                problems.append(f"push {push.id}: the condition on {c.field} names a month, but that field has no months")
            elif isinstance(c.month, bool) or not isinstance(c.month, int) or not (1 <= c.month <= months):
                problems.append(f"push {push.id}: the condition on {c.field} names month {c.month!r}; months run from 1 to {months}")
        elif monthly and c.test in ("is", "is_one_of"):
            problems.append(f"push {push.id}: a condition on the monthly field {c.field} with {c.test} needs a month")
        values = c.value if isinstance(c.value, list) else [c.value]
        if c.test == "is_one_of" and not isinstance(c.value, list):
            problems.append(f"push {push.id}: is_one_of on {c.field} takes a list")
        if c.test == "is_one_of" and isinstance(c.value, list) and not c.value:
            problems.append(f"push {push.id}: is_one_of on {c.field} is given an empty list, which no cell can match")
        if c.test != "is_one_of" and isinstance(c.value, list):
            problems.append(f"push {push.id}: {c.test} on {c.field} takes one value, not a list")
        for v in values:
            if spec.kind == "category":
                if v not in spec.categories:
                    problems.append(f"push {push.id}: {v!r} is not a class of {c.field} (classes: {', '.join(spec.categories)})")
            elif spec.kind == "boolean":
                if not isinstance(v, bool):
                    problems.append(f"push {push.id}: {c.field} is true or false; the condition gives {v!r}")
            elif isinstance(v, bool) or not isinstance(v, (int, float)):
                problems.append(f"push {push.id}: the condition on {c.field} needs a number, found {v!r}")
            elif not np.isfinite(v):
                problems.append(f"push {push.id}: the condition on {c.field} needs a finite number, found {v!r}")
            elif spec.kind == "index" and not isinstance(v, int):
                problems.append(f"push {push.id}: {c.field} holds whole numbers; the condition gives {v!r}")
    if push.on_group:
        spec_kind, monthly, code = "number", (registry.groups[push.target].shape == "month_cell" if push.target in registry.groups else False), None
    elif push.target in registry.fields:
        spec = registry.fields[push.target]
        spec_kind, monthly, code = spec.kind, spec.shape == "month_cell", spec.code
    else:
        return problems
    if spec_kind == "index":
        return problems                                     # the scheduler refuses a push on an index field
    a = push.amount
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and bool(np.isfinite(v))
    if spec_kind == "direction":
        if push.op == "scale":
            if not number(a):
                problems.append(f"push {push.id}: scale on a direction takes one number")
        elif not (isinstance(a, dict) and set(a) == {"east", "north"} and number(a["east"]) and number(a["north"])):
            problems.append(f"push {push.id}: a direction is given as its east and north parts, two numbers")
        return problems
    try:
        amount_array(push, spec_kind, (months, 1) if monthly else (1,), months, None, code=code)
    except ParameterError as e:
        problems.append(str(e))
    return problems


def _unit(lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def _turns(xyz, pts) -> np.ndarray:
    """The angles that the sides of an outline subtend at each point, added up: a full turn (plus or minus 2 pi) at a
    point inside, nothing outside. On a sphere there is a third zone: the mirror image of the inside on the far side
    of the planet, where the sum is a full turn the other way."""
    total = np.zeros(xyz.shape[0])
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        pa, pb = xyz @ a, xyz @ b
        total += np.arctan2(xyz @ np.cross(a, b), (a @ b) - pa * pb)
    return total


def _outline_sense(pts) -> float:
    """+1 if the corners run counter-clockwise seen from outside the planet, -1 if clockwise.

    Found by looking just beside the middle of each side, on both sides of it: one of the two points lies inside,
    where the sum of turns is a full turn, counted positive for a counter-clockwise outline and negative for a
    clockwise one; the other lies outside, where the sum is nothing. No guess about the size or the shape of the
    outline is needed, only that its sides do not cross."""
    left = []
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        middle = a + b
        size = np.linalg.norm(middle)
        if size == 0.0 or np.allclose(a, b):                 # corners opposite each other, or the same corner twice
            continue
        middle /= size
        sideways = np.cross(middle, b - a)                   # to the left of the direction of travel
        sideways /= np.linalg.norm(sideways)
        step = _PROBE * np.linalg.norm(b - a)
        left.append(middle + step * sideways)
        left.append(middle - step * sideways)
    if not left:
        return 1.0
    probes = np.array(left)
    probes /= np.linalg.norm(probes, axis=1, keepdims=True)
    return 1.0 if _turns(probes, pts).sum() >= 0.0 else -1.0     # of each pair of probes one lies inside; its turn sets the sign


def _inside_outline(xyz, outline) -> np.ndarray:
    """Cells inside an outline given as [lat, lon] corners, in either order of travel. The outline must be smaller
    than a hemisphere and its sides must not cross; each side is the shorter arc between two corners."""
    pts = np.array([_unit(la, lo) for la, lo in outline])
    inside = _outline_sense(pts) * _turns(xyz, pts) > np.pi   # the mirror image on the far side has the other sign
    # A point exactly on a side subtends half a turn there, counted as plus or minus by the last bit of a sum: it
    # was inside for one order of travel and outside for the other. A point on a side belongs to the outline.
    return inside | (_outside_outline_m(xyz, outline, 1.0) < _ON_A_SIDE)


def _outside_outline_m(xyz, outline, radius_m) -> np.ndarray:
    """Distance from each point to the nearest side of an outline, in metres."""
    pts = np.array([_unit(la, lo) for la, lo in outline])
    best = np.full(xyz.shape[0], np.inf)
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        normal = np.cross(a, b)
        size = np.linalg.norm(normal)
        to_a = 2.0 * np.arcsin(np.clip(np.linalg.norm(xyz - a, axis=1) / 2.0, 0.0, 1.0))    # by the chord: the angle from
        to_b = 2.0 * np.arcsin(np.clip(np.linalg.norm(xyz - b, axis=1) / 2.0, 0.0, 1.0))    # the dot product is blunt near zero
        d = np.minimum(to_a, to_b)
        if size > 0.0:
            normal /= size
            foot = xyz - (xyz @ normal)[:, None] * normal                      # nearest point of the side's great circle
            within = (np.cross(a, foot) @ normal >= 0.0) & (np.cross(foot, b) @ normal >= 0.0)   # ... if it lies between the corners
            d = np.where(within, np.minimum(d, np.abs(np.arcsin(np.clip(xyz @ normal, -1.0, 1.0)))), d)
        best = np.minimum(best, d)
    return best * radius_m


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
        dist_out = _outside_outline_m(mesh.xyz, push_region.outline, radius_m) if push_region.circle is None else None
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
    if number_like and edge > 0.0 and not inside.all():
        # The fade is measured from the shape itself where the region is one circle or one outline: a shape smaller
        # than a cell then still reaches the cells its edge covers. A region with a condition, or with two shapes,
        # has no outline to measure from; there the fade is measured from the centre of the nearest cell inside.
        if dist_out is None and inside.any():
            idx = np.flatnonzero(inside)
            chord, _ = cKDTree(mesh.xyz[idx]).query(mesh.xyz)
            dist_out = 2.0 * np.arcsin(np.clip(0.5 * chord, 0, 1)) * radius_m
        if dist_out is not None:
            w = np.where(inside, 1.0, np.clip(1.0 - dist_out / edge, 0.0, 1.0))
    return w


def amount_array(push: Push, spec_kind: str, shape: tuple, months: int, mesh, code=None) -> np.ndarray:
    """The amount of a push laid out to match the target's shape."""
    a = push.amount
    if spec_kind == "category":
        try:
            return np.full(shape, code(a), dtype=np.int64)
        except ParameterError as e:
            raise ParameterError(f"push {push.id}: {e}") from None
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
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) for v in a):
            raise ParameterError(f"push {push.id}: the monthly amounts {a!r} are not all finite numbers")
        return np.broadcast_to(np.asarray(a, dtype=np.float64)[:, None], shape).copy()
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not np.isfinite(a):
        raise ParameterError(f"push {push.id}: the amount {a!r} is not a finite number")
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
    w = np.broadcast_to(w, old.shape)
    # Full weight gives the pushed value itself and no weight the old one, exactly. In the fade the two are mixed;
    # where the old value is missing there is nothing to mix with, and the pushed value is taken.
    mixed = np.where(np.isnan(old), new, old + w * (new - old))
    return np.where(w >= 1.0, new, np.where(w <= 0.0, old, mixed))
