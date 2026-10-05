"""The "why is it like this?" query (design, Layer 7).

explain(view, cell, field) starts at the field and reads its largest drivers. It follows each
driver to the field it came from and repeats, until it reaches a parameter, a seeded starting
condition or a push. The walk is written once, here. The sentence patterns are data
(explanations.yaml), stored in the world, so processes still never call each other.

A pattern entry, under the slot and the field it writes:
    says:     sentence for the field; slots {value}, {lat}, {lon}, {planet[...]} and one per driver
    says_missing:  sentence used in its place where the field has no value in the cell;
              follows_missing: the fields the walk then continues to
    form:     sum (the drivers add up to the field), rule (a driver names the rule that fired), or plain
    says_zero:     for form sum: the sentence used where no driver has anything to say and the value is nothing;
              follows_zero: the fields the walk then continues to
    cases:    a list; each case has `when` (a driver that holds a class -> the class name, or a list of names)
              and any of the entries says, says_zero, follows, follows_zero, form, unit and ends, which replace
              those of the pattern in the cells where every driver named under `when` holds one of its names.
              The first case that holds is taken. `quiet: true` keeps the drivers from adding to the sentence.
    unit:     how to print numbers: C_from_K, K_difference, km2_from_m2, km3_from_m3, percent_from_share, or any
              text put after the number
    ends:     text saying why the chain ends here (a parameter, a seeded starting condition)
    follows:  fields the walk continues to when no driver says otherwise
    drivers:  per driver: says (slot {v}, and {at} for the cell that the driver named under "at" holds),
              follows (fields), at (a driver holding the cell to continue at),
              ends (text saying why the chain ends at this driver: it is given, once, where the driver is one of
              those that the walk would follow),
              names (for a driver that holds a class), follows_by (class name -> fields),
              cell (the driver holds a cell number: it is used by "at" and not spoken),
              row_of (the driver holds a row of this table: says may then use {row}, or {row_number} if the table has
              a column called row, and one slot per column; values maps a column's codes to words, and units
              maps a column to the unit its number is printed in),
              aside (the driver is a number for the sentences to use by its name: it is no part of a sum, is not
              spoken by itself and is not followed)
"""
from __future__ import annotations

import numpy as np

MAX_DEPTH = 8
MAX_STEPS = 16                 # an answer holds at most this many entries, and then one that says where it stopped
FOLLOW_TOP = 2
WORTH_FOLLOWING = 0.1          # a driver smaller than this share of the largest one is not followed
WORTH_SAYING = 0.002           # a driver smaller than this share of the largest one is not mentioned
NO_VALUE = "no value"          # how a missing value is worded


def _fmt(v, unit):
    if v is None or (isinstance(v, float) and v != v):
        return NO_VALUE
    if unit == "C_from_K":
        return f"{v - 273.15:.1f} °C"
    if unit == "K_difference":
        return f"{v:+.1f} °C"
    if unit == "km2_from_m2":
        return f"{v / 1e6:,.0f} km²"
    if unit == "km3_from_m3":
        a = abs(v) / 1e9
        return f"{v / 1e9:,.0f} km³" if a >= 100 else f"{v / 1e9:.1f} km³" if a >= 1 else f"{v / 1e9:.3g} km³"
    if unit == "percent_from_share":                         # a share that is not nothing is not printed as 0 %, nor one short of all as 100 %
        return "under 1 %" if 0.0 < v < 0.005 else "over 99 %" if 0.995 <= v < 1.0 else f"{v * 100:.0f} %"
    if isinstance(v, (bool, np.bool_)):
        return "true" if v else "false"
    if isinstance(v, (int, np.integer)):
        return f"{int(v)}{(' ' + unit) if unit else ''}"
    a = abs(v)
    text = f"{v:.0f}" if a >= 1000 else f"{v:.1f}" if a >= 10 else f"{v:.2f}" if a >= 0.1 or a == 0 else f"{v:.3g}"
    return f"{text}{(' ' + unit) if unit else ''}"


def class_name(categories, code) -> str:
    """The name of a class, or a plain statement that the code names no class of the list."""
    code = int(code)
    return categories[code] if 0 <= code < len(categories) else f"no class (code {code})"


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
            v = np.bincount(v - v.min()).argmax() + v.min()
        return class_name(spec["categories"], v)
    if kind == "boolean":
        return bool(v if not np.ndim(v) else v.any())
    if kind == "index":
        return int(v)
    return float(np.mean(v))


def _driver_value(view, field, term, cell):
    a = view.driver(field, term)
    if a.shape[-1] == 3 and a.ndim >= 2 and view.specs[field]["kind"] == "direction":
        # a part of a direction: its share along the direction of the field itself, so that the parts add up to the speed
        f = view.field(field)
        part = a[cell] if a.ndim == 2 else a[:, cell].mean(axis=0)
        whole = f[cell] if f.ndim == 2 else f[:, cell].mean(axis=0)
        size = float(np.linalg.norm(whole))
        return float(part @ whole / size) if size > 0 else 0.0
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
    entries, seen, slots_on_path = [], {}, []
    recorded = attrs.get("drivers") or {}
    push_meta = attrs.get("pushes") or {}
    models = attrs.get("models") or {}

    def here(c):
        if c == cell:
            return ""
        return (f"At {abs(lat[c]):.1f}° {'N' if lat[c] >= 0 else 'S'}, {abs(lon[c]):.1f}° {'E' if lon[c] >= 0 else 'W'} "
                f"(cell {int(c)}), where the cause lies: ")

    class Chain(list):
        """The answer's entries. Every entry about another cell than the one asked about says which cell it is
        about, and nothing is added once the entry that says where the walk stopped is in place."""

        def append(self, entry):
            if self and self[-1].get("cut"):
                return
            if len(self) >= MAX_STEPS and not entry.get("cut"):          # the answer is full, whatever was about to be added
                entry = {"field": entry["field"], "cell": entry["cell"], "end": True, "cut": True,
                         "text": f"The walk stops here: the answer has reached {MAX_STEPS} entries. "
                                 f"Ask about {entry['field']} to go on."}
            if entry["cell"] != cell and not entry["text"].startswith("At "):
                entry["text"] = here(entry["cell"]) + entry["text"]
            list.append(self, entry)

    chain = Chain(entries)

    def visit(f, c, depth, lagged, path):
        line = lineage.get(f)
        spec = specs[f]
        if line is None:
            chain.append({"field": f, "cell": int(c), "text": f"{f}: nothing in this world wrote it."})
            return
        key = (f, int(c))                                    # a step explains one field in one cell
        if key in path:                                      # the walk has come round to a step it is in the middle of explaining
            chain.append({"field": f, "cell": int(c), "loop": True,
                          "text": f"This leads back to {f}, explained in step {seen[key]}: a feedback loop, "
                                  f"which the climate rounds repeat until it is steady."})
            return
        if key in seen:
            if not (chain and chain[-1].get("again") == f and chain[-1]["cell"] == int(c)):
                chain.append({"field": f, "cell": int(c), "again": f, "text": f"For {f}, see step {seen[key]}."})
            return
        if len(chain) >= MAX_STEPS:
            chain.append({"field": f, "cell": int(c), "end": True, "cut": True,
                          "text": f"The walk stops here: the answer has reached {MAX_STEPS} entries. Ask about {f} to go on."})
            return
        seen[key] = len(chain) + 1
        path = path + (key,)
        writer = line["writer"]
        if writer not in slots_on_path:
            slots_on_path.append(writer)
        pat = (patterns.get(writer) or {}).get(f) or {}
        value = cell_value(view, f, c)
        absent = isinstance(value, float) and value != value          # the field has no value in this cell
        dpat = pat.get("drivers") or {}
        terms = [t for t in dpat if t in recorded.get(f, [])] + [t for t in recorded.get(f, []) if t not in dpat]
        dvals = {t: _driver_value(view, f, t, c) for t in terms}
        base = [t for t in terms if (dpat.get(t) or {}).get("base")]       # a fixed starting value, not a cause to weigh
        names = {}
        for t, v in dvals.items():
            p = dpat.get(t) or {}
            if "names" in p:                                 # a driver that holds a class, whatever type it was stored in
                code = int(v) if v == v else -1
                names[t] = p["names"][code] if 0 <= code < len(p["names"]) else f"no class (code {v})"
        for case in pat.get("cases") or []:                  # the first case whose classes all hold here replaces entries
            when = case.get("when") or {}
            if when and all(names.get(t) in (want if isinstance(want, list) else [want]) for t, want in when.items()):
                pat = {**pat, **{k: v for k, v in case.items() if k != "when"}}
                break
        unit = pat.get("unit", spec["unit"] if spec["kind"] in ("number", "direction") else "")
        shown = value.replace("_", " ") if isinstance(value, str) else _fmt(value, unit)
        slots = _Safe(value=shown, lat=f"{abs(lat[c]):.1f}° {'north' if lat[c] >= 0 else 'south'}",
                      lon=f"{abs(lon[c]):.1f}° {'east' if lon[c] >= 0 else 'west'}", planet=attrs["planet"], field=f)
        for t, v in dvals.items():
            p = dpat.get(t) or {}
            if t in names:
                slots[t] = names[t].replace("_", " ")
            elif p.get("cell") or p.get("row_of"):           # a driver that names a cell or a row is no amount: it takes no unit
                nothing = not (v == v) or v < 0
                slots[t] = (("no other cell" if nothing else f"cell {int(v)}") if p.get("cell") else
                            ("no row" if nothing else f"row {int(v)} of the table {p['row_of']}"))
            else:
                slots[t] = _fmt(v, p.get("unit", unit))
        quiet = bool(pat.get("quiet"))

        def said_by(t, p, text):
            """A driver's sentence, with {v} for its value and {at} for the cell that its "at" driver names."""
            given = _Safe(v=slots[t])
            other = dvals.get(p.get("at"), -1) if p.get("at") else -1
            if p.get("at"):
                given["at"] = "no other cell" if other < 0 else (
                    f"cell {int(other)}, at {abs(lat[int(other)]):.1f}° {'N' if lat[int(other)] >= 0 else 'S'}, "
                    f"{abs(lon[int(other)]):.1f}° {'E' if lon[int(other)] >= 0 else 'W'}")
            return text.format_map(given)
        if absent:
            text = (pat.get("says_missing") or f"{f} has no value here.").format_map(slots)
        elif pat.get("says"):
            text = pat["says"].format_map(slots)
        else:
            src = ", ".join(line["reads"] + line["reads_lagged"]) or "the planet parameters"
            text = f"{f} is {shown}: {writer} ({line['model']}) computed it from {src}."
        parts, order = [], []
        if absent or quiet:
            pass                                             # the drivers of a value that is not there have nothing to add
        elif pat.get("form") == "sum":
            order = sorted((t for t in dvals if not any((dpat.get(t) or {}).get(k) for k in ("names", "cell", "row_of", "aside"))),
                           key=lambda t: -abs(dvals[t]))
            largest = max((abs(dvals[t]) for t in order if t not in base), default=0.0)
            for t in order:
                p = dpat.get(t) or {}
                if abs(dvals[t]) <= WORTH_SAYING * largest and not p.get("always") and t not in base:
                    continue
                said = said_by(t, p, p.get("says") or (t.replace("_", " ") + " {v}"))
                if p.get("group"):                               # name each member of the sum that acts in this cell
                    members = []
                    for member, arr in sorted(view.group_members(p["group"]).items()):
                        mv = float(np.mean(arr[c] if arr.ndim == 1 else arr[:, c]))
                        if mv != 0.0:
                            unit_g = (attrs.get("groups") or {}).get(p["group"], {}).get("unit", "")
                            who = f"the push {member[5:]}" if member.startswith("push:") else member
                            members.append(f"{who} {_fmt(mv, unit_g)}")
                    if members:
                        said += " (" + ", ".join(members) + ")"
                parts.append(said)
        else:
            order = [t for t in dvals if not any((dpat.get(t) or {}).get(k) for k in ("cell", "row_of", "aside"))]
            for t in order:
                p = dpat.get(t) or {}
                if p.get("says") and dvals[t] == dvals[t]:      # a driver whose value is missing here has nothing to say
                    parts.append(said_by(t, p, p["says"]))
                if "says_by" in p and names.get(t) in p["says_by"]:
                    parts.append(p["says_by"][names[t]].format_map(slots))
        rows_said = []
        for t in terms:                                      # a driver that names a row of a table: say what the row holds
            p = dpat.get(t) or {}
            if not p.get("row_of") or dvals[t] < 0 or absent or quiet:
                continue
            table = view.table(p["row_of"])
            row = int(dvals[t])
            if p.get("says") and all(row < len(column) for column in table.values()):
                held = {name: table[name][row].item() for name in table}
                for name, words in (p.get("values") or {}).items():     # (a stored world holds the codes as text)
                    held[name] = words.get(held.get(name), words.get(str(held.get(name)), held.get(name)))
                units = p.get("units") or {}
                held = {name: _fmt(v, units.get(name, "")) if isinstance(v, float) else v for name, v in held.items()}
                rows_said.append(p["says"].format_map(_Safe({"row": row, "row_number": row, **held})))
        # a sum none of whose parts is worth a word. Its own sentence for that case speaks only if the value shown is
        # nothing as well: after a push, or after another process changed the field, the parts no longer add up to it.
        nothing = pat.get("form") == "sum" and not absent and not quiet and not parts
        empty = nothing and isinstance(value, float) and value == 0.0
        parts += rows_said
        if empty and pat.get("says_zero"):
            text = pat["says_zero"].format_map(slots)
            if rows_said:
                text = text.rstrip() + " " + "; ".join(rows_said) + "."
        elif parts:
            text = text.rstrip() + " " + "; ".join(parts) + "."
        else:
            if text.rstrip().endswith(":"):                                  # nothing follows the colon: end the sentence
                text = text.rstrip()[:-1] + "."
            pushed = any(float(view.push_arrays(pid)["weight"][c]) > 0.0 for pid in line.get("pushes", []) if pid in push_meta)
            if nothing and not empty and (pushed or line.get("modified_by")):
                text += " Its process found nothing here; what changed the value afterwards follows."
        for m in line.get("modified_by", []):                # processes that changed the field after its writer
            text += f" After {writer} wrote it, {m} changed it ({(models.get(m) or {}).get('model') or 'a process that modifies this field'})."
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
            if spec["kind"] == "direction":                  # (cells, 3) or (months, cells, 3)
                b = before[c] if before.ndim == 2 else before[:, c].mean(axis=0)
                b_text = _fmt(float(np.linalg.norm(b)), unit)
            else:
                b = before[c] if before.ndim == 1 else before[:, c]
                if spec["kind"] == "category":
                    b_text = class_name(spec["categories"], b if not np.ndim(b) else np.bincount(b - b.min()).argmax() + b.min())
                elif spec["kind"] == "boolean":
                    b_text = _fmt(bool(b if not np.ndim(b) else b.any()), "")
                elif spec["kind"] == "index":
                    b_text = _fmt(int(b), "")
                else:
                    b_text = _fmt(float(np.mean(b)), unit)
            kind = "a physical push" if meta.get("physical") else "a push that is not physical"
            chain.append({"field": f, "cell": int(c), "push": pid, "physical": bool(meta.get("physical")),
                          "text": f"{kind.capitalize()} acted here: entry {meta['entry']} ({meta.get('reason') or 'no reason given'}), "
                                  f"operation {meta['op']}, at {w * 100:.0f} % strength. "
                                  + ("Before the push the cell had no value." if b_text == NO_VALUE
                                     else f"Before the push the value was {b_text}.")})
        if pat.get("ends"):
            chain.append({"field": f, "cell": int(c), "end": True, "text": pat["ends"].format_map(slots)})
            return
        if depth >= MAX_DEPTH:
            chain.append({"field": f, "cell": int(c), "end": True, "text": "The walk stops here: it has reached its depth limit."})
            return
        # where to continue: the fields that the largest drivers name
        nexts = []
        if absent:                                           # why there is no value: the pattern names where to look
            for g in pat.get("follows_missing", []):
                if g in specs:
                    visit(g, int(c), depth + 1, g in line["reads_lagged"], path)
            return
        if quiet:
            candidates = []
        elif pat.get("form") == "sum":
            largest = max((abs(dvals[t]) for t in order if t not in base), default=0.0)
            worth = [t for t in order if t not in base and abs(dvals[t]) > 0.0 and abs(dvals[t]) >= WORTH_FOLLOWING * largest]
            candidates = worth[:FOLLOW_TOP if depth <= 1 else 1]
        else:
            candidates = order
        closes = None
        for t in candidates:
            p = dpat.get(t) or {}
            if closes is None and p.get("ends"):             # the chain ends at this driver: a seed, a parameter
                closes = p["ends"]
            fol = list(p.get("follows", []))
            if "follows_by" in p and names.get(t) in p["follows_by"]:
                fol += p["follows_by"][names[t]]
            at = c
            if p.get("at") and p["at"] in dvals and dvals[p["at"]] >= 0:
                at = dvals[p["at"]]
            for g in fol:
                if (g, at) not in nexts:
                    nexts.append((g, at))
        if empty and pat.get("follows_zero"):
            nexts = [(g, c) for g in pat["follows_zero"]]
        if not nexts:
            nexts = [(g, c) for g in pat.get("follows", [])]
        if not nexts and not terms and not pat:
            nexts = [(g, c) for g in line["reads"]][:FOLLOW_TOP]
        if closes is not None:
            chain.append({"field": f, "cell": int(c), "end": True, "text": closes.format_map(slots)})
        for g, at in nexts[:3]:
            if g in specs:
                visit(g, int(at), depth + 1, g in line["reads_lagged"], path)
        if not nexts and not line["reads"] and not line["reads_lagged"] and not terms:
            chain.append({"field": f, "cell": int(c), "end": True,
                          "text": f"The chain ends here: {writer} read no other field to give {f}. Its model: {line['model']}."})

    visit(field, int(cell), 0, False, ())
    notices = []
    for nt in attrs.get("notices") or []:
        if nt["kind"] == "climate_not_settled":
            notices.append(f"The climate did not settle within {nt['rounds']} rounds, so every climate value here is a "
                           f"solver's unfinished working step.")
        elif nt["kind"] == "model_outside_range" and nt["slot"] in slots_on_path:
            notices.append(f"{nt['slot']} ran outside the range in which its model is expected to hold: "
                           f"{nt['parameter']} is {nt['value']}, expected {nt['expected'][0]} to {nt['expected'][1]}.")
        elif nt["kind"] == "field_outside_range" and any(f == nt["field"] for f, _ in seen):
            notices.append(f"{nt['field']} left its valid range somewhere on the planet.")
        elif nt["kind"] == "process_note" and nt["slot"] in slots_on_path:
            notices.append(f"{nt['slot']} noted: {nt['what']}.")
        elif nt["kind"] == "run_time_over_limit":
            notices.append(f"The build took {nt['seconds']} seconds, more than the {nt['limit_s']} seconds its profile allows.")
    return {"cell": int(cell), "lat": float(lat[cell]), "lon": float(lon[cell]), "field": field, "chain": list(chain), "notices": notices}


def as_text(answer: dict) -> str:
    lines = [f"Why is {answer['field']} like this at {abs(answer['lat']):.1f}° {'N' if answer['lat'] >= 0 else 'S'}, "
             f"{abs(answer['lon']):.1f}° {'E' if answer['lon'] >= 0 else 'W'} (cell {answer['cell']})?"]
    for k, step in enumerate(answer["chain"], 1):
        lines.append(f"{k}. {step['text']}")
    for nt in answer["notices"]:
        lines.append(f"Notice: {nt}")
    return "\n".join(lines)
