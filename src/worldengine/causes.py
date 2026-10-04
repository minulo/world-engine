"""The "why is it like this?" query (design, Layer 7).

explain(view, cell, field) starts at the field and reads its largest drivers. It follows each
driver to the field it came from and repeats, until it reaches a parameter, a seeded starting
condition or a push. The walk is written once, here. The sentence patterns are data
(explanations.yaml), stored in the world, so processes still never call each other.

A pattern entry, under the slot and the field it writes:
    says:     sentence for the field; slots {value}, {lat}, {lon}, {planet[...]} and one per driver
    form:     sum (the drivers add up to the field), rule (a driver names the rule that fired), or plain
    unit:     how to print numbers: K, C_from_K, or any text put after the number
    ends:     text saying why the chain ends here (a parameter, a seeded starting condition)
    follows:  fields the walk continues to when no driver says otherwise
    drivers:  per driver: says (slot {v}), follows (fields), at (a driver holding the cell to continue at),
              names (for a driver that holds a class), follows_by (class name -> fields)
"""
from __future__ import annotations

import numpy as np

MAX_DEPTH = 8
FOLLOW_TOP = 2


def _fmt(v, unit):
    if v is None or (isinstance(v, float) and v != v):
        return "undefined"
    if unit == "C_from_K":
        return f"{v - 273.15:.1f} °C"
    if unit == "K_difference":
        return f"{v:+.1f} °C"
    if isinstance(v, (bool, np.bool_)):
        return "true" if v else "false"
    if isinstance(v, (int, np.integer)):
        return f"{int(v)}{(' ' + unit) if unit else ''}"
    a = abs(v)
    text = f"{v:.0f}" if a >= 1000 else f"{v:.1f}" if a >= 10 else f"{v:.2f}" if a >= 0.1 or a == 0 else f"{v:.3g}"
    return f"{text}{(' ' + unit) if unit else ''}"


def cell_value(view, field, cell):
    """The value shown for one cell: the yearly mean of a monthly number, the class name of a category,
    the speed of a direction."""
    spec = view.specs[field]
    a = view.field(field)
    kind = spec["kind"]
    if kind == "direction":
        v = a[cell] if a.ndim == 2 else a[:, cell].mean(axis=0)
        return float(np.linalg.norm(v))
    v = a[cell] if a.ndim == 1 else a[:, cell]
    if kind == "category":
        if np.ndim(v):
            v = np.bincount(v).argmax()
        return spec["categories"][int(v)]
    if kind == "boolean":
        return bool(v if not np.ndim(v) else v.any())
    if kind == "index":
        return int(v)
    return float(np.mean(v))


def _driver_value(view, field, term, cell):
    a = view.driver(field, term)
    v = a[cell] if a.ndim == 1 else a[:, cell]
    if a.dtype.kind in "iu":
        return int(v if not np.ndim(v) else np.bincount(v - v.min()).argmax() + v.min())
    return float(np.mean(v))


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def explain(view, cell: int, field: str) -> dict:
    """The chain of causes for one field in one cell."""
    attrs = view.attrs
    specs, lineage, patterns = attrs["fields"], attrs["lineage"], attrs.get("explanations") or {}
    lat, lon = view.mesh_array("lat"), view.mesh_array("lon")
    if field not in specs or field not in lineage:
        raise KeyError(f"the world holds no field named {field}")
    n = attrs["meta"]["cells"]
    if not (0 <= cell < n):
        raise IndexError(f"cell {cell} is outside 0 to {n - 1}")
    chain, seen, slots_on_path = [], {}, []
    recorded = attrs.get("drivers") or {}
    push_meta = attrs.get("pushes") or {}

    def visit(f, c, depth, lagged):
        line = lineage.get(f)
        spec = specs[f]
        if line is None:
            chain.append({"field": f, "cell": int(c), "text": f"{f}: nothing in this world wrote it."})
            return
        key = (f, int(c))
        if f in seen:
            chain.append({"field": f, "cell": int(c), "loop": True,
                          "text": f"This leads back to {f}, already explained in step {seen[f]}: a feedback loop, "
                                  f"which the climate rounds repeat until it is steady."})
            return
        seen[f] = len(chain) + 1
        writer = line["writer"]
        if writer not in slots_on_path:
            slots_on_path.append(writer)
        pat = (patterns.get(writer) or {}).get(f) or {}
        unit = pat.get("unit", spec["unit"] if spec["kind"] == "number" else "")
        value = cell_value(view, f, c)
        shown = value if isinstance(value, str) else _fmt(value, unit)
        terms = recorded.get(f, [])
        dvals = {t: _driver_value(view, f, t, c) for t in terms}
        dpat = pat.get("drivers") or {}
        slots = _Safe(value=shown, lat=f"{abs(lat[c]):.1f}° {'north' if lat[c] >= 0 else 'south'}",
                      lon=f"{abs(lon[c]):.1f}° {'east' if lon[c] >= 0 else 'west'}", planet=attrs["planet"], field=f)
        names = {}
        for t, v in dvals.items():
            p = dpat.get(t) or {}
            if "names" in p:
                names[t] = p["names"][v] if 0 <= v < len(p["names"]) else str(v)
                slots[t] = names[t]
            else:
                slots[t] = _fmt(v, p.get("unit", unit))
        if pat.get("says"):
            text = pat["says"].format_map(slots)
        else:
            src = ", ".join(line["reads"] + line["reads_lagged"]) or "the planet parameters"
            text = f"{f} is {shown}: {writer} ({line['model']}) computed it from {src}."
        parts, order = [], []
        if pat.get("form") == "sum":
            order = sorted((t for t in dvals if not (dpat.get(t) or {}).get("names")), key=lambda t: -abs(dvals[t]))
            for t in order:
                p = dpat.get(t) or {}
                if dvals[t] == 0.0 and not p.get("always"):
                    continue
                parts.append((p.get("says") or (t.replace("_", " ") + " {v}")).format_map(_Safe(v=slots[t])))
        else:
            order = list(dvals)
            for t in order:
                p = dpat.get(t) or {}
                if p.get("says"):
                    parts.append(p["says"].format_map(_Safe(v=slots[t])))
                if "says_by" in p and names.get(t) in p["says_by"]:
                    parts.append(p["says_by"][names[t]].format_map(slots))
        if parts:
            text = text.rstrip() + " " + "; ".join(parts) + "."
        step = {"field": f, "cell": int(c), "writer": writer, "model": line["model"], "value": shown, "text": text,
                "drivers": {t: slots[t] for t in dvals}}
        if lagged:
            step["lagged"] = True
        chain.append(step)
        # pushes on this field in this cell
        for pid in line.get("pushes", []):
            meta = push_meta.get(pid)
            if meta is None:
                continue
            arr = view.push_arrays(pid)
            w = float(arr["weight"][c])
            if w <= 0.0:
                continue
            before = arr["before"]
            b = before[c] if before.ndim == 1 else before[:, c]
            if spec["kind"] == "category":
                b_text = spec["categories"][int(b if not np.ndim(b) else np.bincount(b).argmax())]
            elif spec["kind"] == "direction":
                b_text = _fmt(float(np.linalg.norm(b if b.ndim == 1 else b.mean(axis=0))), unit)
            else:
                b_text = _fmt(float(np.mean(b)), unit)
            kind = "a physical push" if meta.get("physical") else "a push that is not physical"
            chain.append({"field": f, "cell": int(c), "push": pid, "physical": bool(meta.get("physical")),
                          "text": f"{kind.capitalize()} acted here: entry {meta['entry']} ({meta.get('reason') or 'no reason given'}), "
                                  f"operation {meta['op']}, at {w * 100:.0f} % strength. Before the push the value was {b_text}."})
        if pat.get("ends"):
            chain.append({"field": f, "cell": int(c), "end": True, "text": pat["ends"].format_map(slots)})
            return
        if depth >= MAX_DEPTH:
            chain.append({"field": f, "cell": int(c), "end": True, "text": "The walk stops here: it has reached its depth limit."})
            return
        # where to continue: the fields that the largest drivers name
        nexts = []
        for t in order[:max(FOLLOW_TOP, 1)] if pat.get("form") == "sum" else order:
            p = dpat.get(t) or {}
            fol = list(p.get("follows", []))
            if "follows_by" in p and names.get(t) in p["follows_by"]:
                fol += p["follows_by"][names[t]]
            at = c
            if p.get("at") and p["at"] in dvals and dvals[p["at"]] >= 0:
                at = dvals[p["at"]]
            for g in fol:
                if (g, at) not in nexts:
                    nexts.append((g, at))
        if not nexts:
            nexts = [(g, c) for g in pat.get("follows", [])]
        if not nexts and not terms and not pat:
            nexts = [(g, c) for g in line["reads"]][:FOLLOW_TOP]
        for g, at in nexts[:3]:
            if g.startswith("group:"):
                continue
            if g in specs:
                visit(g, int(at), depth + 1, g in line["reads_lagged"])
        if not nexts:
            chain.append({"field": f, "cell": int(c), "end": True,
                          "text": f"The chain ends here: {f} follows from the planet parameters and the mesh alone."})

    visit(field, int(cell), 0, False)
    notices = []
    for nt in attrs.get("notices") or []:
        if nt["kind"] == "climate_not_settled":
            notices.append(f"The climate did not settle within {nt['rounds']} rounds, so every climate value here is a "
                           f"solver's unfinished working step.")
        elif nt["kind"] == "model_outside_range" and nt["slot"] in slots_on_path:
            notices.append(f"{nt['slot']} ran outside the range in which its model is expected to hold: "
                           f"{nt['parameter']} is {nt['value']}, expected {nt['expected'][0]} to {nt['expected'][1]}.")
        elif nt["kind"] == "field_outside_range" and nt["field"] in seen:
            notices.append(f"{nt['field']} left its valid range somewhere on the planet.")
    return {"cell": int(cell), "lat": float(lat[cell]), "lon": float(lon[cell]), "field": field, "chain": chain, "notices": notices}


def as_text(answer: dict) -> str:
    lines = [f"Why is {answer['field']} like this at {abs(answer['lat']):.1f}° {'N' if answer['lat'] >= 0 else 'S'}, "
             f"{abs(answer['lon']):.1f}° {'E' if answer['lon'] >= 0 else 'W'} (cell {answer['cell']})?"]
    for k, step in enumerate(answer["chain"], 1):
        lines.append(f"{k}. {step['text']}")
    for nt in answer["notices"]:
        lines.append(f"Notice: {nt}")
    return "\n".join(lines)
