"""Compare two world stores field by field and say how far apart the two worlds are.

    python tools/compare_worlds.py STORE_A STORE_B [--json OUT] [--markdown OUT] [--title TEXT]

The same seed and parameters give the same world, bit for bit, on one machine; between machines the fingerprints of
many fields differ (README, "Worlds from another system"). A fingerprint says only that a field differs. This tool
measures by how much. STORE_A is the reference.

For every field, every array of the mesh and every column of every table it gives:

  * for a number (a float array): the largest absolute difference; the same as a share of the field's range (the
    largest value less the smallest, over both worlds); the share of the cells, and for a field with one slice per
    month the share of the cell-months, that differ by more than the float32 rounding of the value; and the same
    shares beyond the noise threshold below;
  * for a category, an index or a true-or-false field (ocean_mask, biome, climate_class, plate_id, soil_order, ...):
    the share of the cells (and cell-months) whose value differs;
  * for a table (plates, seas, lakes, hollows, ...): the number of rows in each world; the rows of the two worlds
    matched by the table's key columns (KEYS: a plate by its number, a sea by its lowest cell, a lake or a hollow
    by the cell at its bottom), and how many rows of each world find no match; and each column over the matched
    rows, as above. A key that repeats (a hollow made of two has the bottom cell of its deeper part) is matched in
    the order its rows come in. A table without a key is matched row by row, where both have as many rows.

A cell counts once however many of its months or components differ (a direction has three). Then one verdict:

  identical                           every array is the same, bit for bit;
  same planet with rounding noise     land and sea, the plates and the crust agree on all but a few cells, every
                                      table has the same rows, and no field or column differs by more than
                                      NOISE_SHARE_OF_RANGE of its range on more than FEW_CELLS_SHARE of its cells
                                      or rows;
  same planet with grown differences  land and sea, the plates and the crust agree as above, but some field or
                                      column differs by more than the noise threshold on more than a few cells or
                                      rows, a table has rows that the other lacks, or a field is in one world only;
  different planet                    land and sea, the plates or the crust differ on more than FEW_CELLS_SHARE of
                                      the cells, or the two worlds do not have the same plates;
  not comparable                      the meshes have other sizes or other neighbours: their cells do not correspond.

The thresholds, and why:

  * The float32 rounding of a value is one unit in the last place of the value as a float32 (numpy.spacing of the
    larger of the two values). Two computations of the same quantity that round differently once end one unit
    apart; a field stored in float32 cannot hold a smaller difference. A float64 array (cell_area, the mesh's
    coordinates, most table columns) is held to the same unit, so that a difference in its last bits as a float64
    does not count.
  * NOISE_SHARE_OF_RANGE = 0.001, a thousandth of the field's range. It lies four orders of magnitude above the
    rounding of a float32 (about 6e-8 to 1.2e-7 of a value), which leaves room for a difference of one unit to
    grow through the rounds of the history and the climate. The viewer colours a field with a table of 256 colours
    over its 2nd to 98th percentiles [DOCUMENTED: viewer/viewer.js, lut and rangeOf]: a thousandth of the whole
    range is less than one step of colour wherever those percentiles span more than about a quarter of the whole
    range, so a map does not show it [INFERRED: one step is a 256th of the span between the percentiles, and a
    thousandth of the whole range is less than that where the span exceeds 0.256 of it; a field drawn on a
    logarithmic scale is not covered by this].
    Its limit: for a field whose range is set by a few large values (drainage_area, river_discharge), a thousandth
    of the range is large against most cells. A river that takes another way shows in flow_receiver and basin_id,
    which are compared as indices, cell by cell.
  * FEW_CELLS_SHARE = 0.001, a thousandth of the cells: 10 of the 10,242 cells of the preview world. A few cells of
    coast that fall the other way are a detail of the coastline; more are another coastline.
  * Land and sea, the plates and the crust (SHAPE_FIELDS) decide whether the planet is another: they are its
    continents and the pieces that carry them. A change of an index that only numbers things (depression_id is a
    row of the table of hollows, and one hollow more renumbers those after it) counts as a grown difference,
    never as another planet.

The tool reads the stores and changes nothing. It ends with 0 whatever the verdict (a difference is information),
and with 2 when a store is missing or cannot be read.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldengine import console                          # noqa: E402
from worldengine.store import StoreView                  # noqa: E402

NOISE_SHARE_OF_RANGE = 1e-3       # a difference larger than this share of a field's range is not rounding noise
FEW_CELLS_SHARE = 1e-3            # a share of the cells (or rows) that may differ before the difference is more than "a few"
SHAPE_FIELDS = ("ocean_mask", "plate_id", "crust_type")   # land and sea, the plates and the crust: the planet's shape
SHAPE_TABLE = "plates"            # a world with other plates is another planet
MESH = ("xyz", "nbr", "nbr_count", "area", "lat", "lon", "east", "north")
MESH_TOPOLOGY = ("nbr", "nbr_count")                      # where these differ, the cells of the two worlds do not correspond
CATEGORICAL_KINDS = ("category", "index", "boolean")
TIME_SHAPES = {"month_cell": "month", "day_cell": "day"}   # an array with one slice per month (or day), then one per cell
KEYS = {"plates": ("plate",), "seas": ("lowest_cell",), "lakes": ("bottom_cell",), "hollows": ("bottom_cell",),
        "tectonic_events": ("time_my", "kind", "plate_a", "plate_b"), "storms": ("kind", "born_day")}
PROVENANCE = ("engine_version", "code_fingerprint", "lock_fingerprint", "seed", "packages")
META = ("profile", "mesh_level", "cells", "months", "seed", "math_threads", "parameters_fingerprint")
VERDICTS = ("identical", "same planet with rounding noise", "same planet with grown differences", "different planet",
            "not comparable")


# ---------------------------------------------------------------------------------------------- one array against another
def _per_cell(mask, time):
    """A mask over the array, reduced to one value per cell (any month, any component) and, for an array with one slice
    per month or day, one per cell-month. Returns (cells differing, cells, cell-months differing or None, cell-months
    or None)."""
    if mask.ndim == 0:
        mask = mask.reshape(1)
    lead = 2 if time and mask.ndim >= 2 else 1
    flat = mask.reshape(mask.shape[:lead] + (-1,)).any(axis=-1)          # the components of a direction fold into their cell
    if lead == 2:
        return int(flat.any(axis=0).sum()), int(flat.shape[1]), int(flat.sum()), int(flat.size)
    return int(flat.sum()), int(flat.shape[0]), None, None


def _share(count, total):
    return float(count / total) if total else 0.0


def _counts(out, what, mask, time):
    """Add the number and the share of the cells (and cell-months) where `mask` holds, under names ending in `what`."""
    cells, n, slices, ns = _per_cell(mask, time)
    out.update({"cells": n, f"cells_{what}": cells, f"share_cells_{what}": _share(cells, n)})
    if slices is not None:
        out.update({f"cell_{time}s_{what}": slices, f"share_cell_{time}s_{what}": _share(slices, ns)})


def compare_array(a, b, categorical, time=None):
    """How far the array `b` lies from the reference `a`, as a dict that JSON can hold. `time` is "month" (or "day")
    for an array whose first axis is the months (or days) and whose second is the cells."""
    a, b = np.asarray(a), np.asarray(b)
    out = {"kind": "category" if categorical else "number", "shape": list(a.shape), "dtype": str(a.dtype)}
    if a.shape != b.shape:
        out.update(identical=False, shapes=[list(a.shape), list(b.shape)])
        return out
    out["identical"] = bool(a.dtype == b.dtype and np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes())
    if categorical:
        _counts(out, "differing", a != b, time)
        return out
    x, y = a.astype(np.float64), b.astype(np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        lost = np.isnan(x) != np.isnan(y)                               # a value missing in one world and present in the other
        gap = np.where(np.isnan(x) | np.isnan(y) | (x == y), 0.0, np.abs(x - y))
        unit = np.spacing(np.maximum(np.abs(x), np.abs(y)).astype(np.float32)).astype(np.float64)
        values = np.concatenate([x[np.isfinite(x)], y[np.isfinite(y)]])
        span = float(values.max() - values.min()) if values.size else 0.0
        if span == 0.0:                                                 # a field of one value: its size stands for its range
            span = float(np.abs(values).max()) if values.size else 0.0
        beyond_rounding = lost | (gap > unit) | np.isinf(gap)
        beyond_noise = lost | (gap > NOISE_SHARE_OF_RANGE * span) | np.isinf(gap)
    largest = float(gap.max()) if gap.size else 0.0
    out.update(range=span, largest_absolute=largest,
               largest_relative=(largest / span if span else (0.0 if largest == 0.0 else float("inf"))),
               missing_in_one=int(lost.sum()))
    _counts(out, "beyond_rounding", beyond_rounding, time)
    _counts(out, "beyond_noise", beyond_noise, time)
    return out


def _is_categorical(array, spec=None):
    return (spec or {}).get("kind") in CATEGORICAL_KINDS or np.asarray(array).dtype.kind in "biu"


def _over_rounding(entry):
    """Whether one compared array differs, on some cell or row, by more than the float32 rounding (or in category)."""
    if "shapes" in entry:
        return True
    return bool(entry.get("cells_differing", entry.get("cells_beyond_rounding", 0)))


def _over_noise(entry):
    """Whether one compared array differs by more than rounding noise on more than a few of its cells or rows."""
    if "shapes" in entry:
        return True
    if entry["kind"] == "category":
        return entry["share_cells_differing"] > FEW_CELLS_SHARE
    return entry["share_cells_beyond_noise"] > FEW_CELLS_SHARE


# ---------------------------------------------------------------------------------------------- tables
def _rows(table):
    return int(len(next(iter(table.values())))) if table else 0


def _row_keys(table, columns):
    """The key of every row: the values of its key columns and, for a key that repeats, which repeat it is (a hollow
    made of two has the bottom cell of its deeper part)."""
    seen, keys = {}, []
    for values in zip(*(np.asarray(table[c]).tolist() for c in columns)):
        keys.append((*values, seen.get(values, 0)))
        seen[values] = seen.get(values, 0) + 1
    return keys


def compare_table(name, ta, tb) -> dict:
    """Two versions of one table: their rows, the rows matched by the key, and each column over the matched rows."""
    rows = [_rows(ta), _rows(tb)]
    key = [c for c in KEYS.get(name, ()) if c in ta and c in tb]
    if key and len(key) == len(KEYS[name]):
        ka, kb = _row_keys(ta, key), _row_keys(tb, key)
        where_b = {k: i for i, k in enumerate(kb)}
        ia = [i for i, k in enumerate(ka) if k in where_b]
        ib = [where_b[ka[i]] for i in ia]
    else:
        key = []                                                        # matched by position, where the rows are as many
        ia = ib = list(range(rows[0])) if rows[0] == rows[1] else []
    matched = len(ia)
    entry = {"rows": rows, "key": key or None, "rows_matched": matched,
             "rows_only_in_a": rows[0] - matched, "rows_only_in_b": rows[1] - matched,
             "columns_only_in_a": sorted(set(ta) - set(tb)), "columns_only_in_b": sorted(set(tb) - set(ta)), "columns": {}}
    ia, ib = np.asarray(ia, dtype=np.int64), np.asarray(ib, dtype=np.int64)
    if matched:
        for col in sorted(set(ta) & set(tb)):
            a, b = np.asarray(ta[col]), np.asarray(tb[col])
            entry["columns"][col] = compare_array(a[ia], b[ib], _is_categorical(a))
    entry["same_rows"] = rows[0] == rows[1] == matched
    entry["identical"] = bool(entry["same_rows"] and set(ta) == set(tb) and np.array_equal(ia, ib)
                              and all(c["identical"] for c in entry["columns"].values()))
    return entry


# ---------------------------------------------------------------------------------------------- two stores
def _view(store):
    return store if isinstance(store, StoreView) else StoreView(store)


def compare(store_a, store_b) -> dict:
    """Compare two world stores (paths or StoreViews). Returns everything the tool reports, as a dict JSON can hold."""
    va, vb = _view(store_a), _view(store_b)
    out = {"a": str(va.path), "b": str(vb.path),
           "thresholds": {"float32_rounding": "one unit in the last place of the value as a float32",
                          "noise_share_of_range": NOISE_SHARE_OF_RANGE, "few_cells_share": FEW_CELLS_SHARE,
                          "shape_fields": list(SHAPE_FIELDS), "shape_table": SHAPE_TABLE},
           "provenance": {}, "mesh": {}, "fields": {}, "tables": {}}
    for key in PROVENANCE:
        if va.attrs.get(key) != vb.attrs.get(key):
            out["provenance"][key] = [va.attrs.get(key), vb.attrs.get(key)]
    for key in META:
        if va.meta.get(key) != vb.meta.get(key):
            out["provenance"][f"meta.{key}"] = [va.meta.get(key), vb.meta.get(key)]

    if va.meta.get("cells") != vb.meta.get("cells"):
        return _verdict(out, "not comparable", [f"the meshes hold {va.meta.get('cells')} and {vb.meta.get('cells')} cells"])
    for name in MESH:
        a, b = va.mesh_array(name), vb.mesh_array(name)
        out["mesh"][name] = compare_array(a, b, _is_categorical(a))
    torn = [n for n in MESH_TOPOLOGY if not out["mesh"][n]["identical"]]
    if torn:
        return _verdict(out, "not comparable", [f"the mesh's {', '.join(torn)} differ: the cells of the two worlds do not correspond"])

    names_a, names_b = set(va.field_names()), set(vb.field_names())
    out["only_in_a"], out["only_in_b"] = sorted(names_a - names_b), sorted(names_b - names_a)
    for name in sorted(names_a & names_b):
        spec = va.specs.get(name) or {}
        a, b = va.field(name), vb.field(name)
        out["fields"][name] = compare_array(a, b, _is_categorical(a, spec), TIME_SHAPES.get(spec.get("shape")))

    tables_a, tables_b = set(va.table_names()), set(vb.table_names())
    out["tables_only_in_a"], out["tables_only_in_b"] = sorted(tables_a - tables_b), sorted(tables_b - tables_a)
    for t in sorted(tables_a & tables_b):
        out["tables"][t] = compare_table(t, va.table(t), vb.table(t))
    return _judge(out)


def _verdict(out, verdict, reasons):
    out["verdict"], out["reasons"] = verdict, reasons
    out["verdict_text"] = f"{verdict}: " + "; ".join(reasons)
    return out


def _largest(fields):
    """The largest difference of any number field, as a share of its range, and the field's name."""
    return max(((f["largest_relative"], n) for n, f in fields.items() if f["kind"] == "number" and "shapes" not in f),
               default=(0.0, None))


def _judge(out) -> dict:
    fields, tables, mesh = out["fields"], out["tables"], out["mesh"]
    worst = _largest(fields)
    out["counts"] = {"fields": len(fields), "fields_identical": sum(f["identical"] for f in fields.values()),
                     "fields_beyond_rounding": sum(_over_rounding(f) for f in fields.values()),
                     "fields_beyond_noise": sum(_over_noise(f) for f in fields.values()),
                     "tables": len(tables), "tables_identical": sum(t["identical"] for t in tables.values()),
                     "mesh_arrays": len(mesh), "mesh_arrays_identical": sum(m["identical"] for m in mesh.values()),
                     "largest_relative": worst[0], "largest_relative_field": worst[1]}
    one_side = out["only_in_a"] + out["only_in_b"] + out["tables_only_in_a"] + out["tables_only_in_b"]
    if (all(f["identical"] for f in [*mesh.values(), *fields.values()]) and all(t["identical"] for t in tables.values())
            and not one_side):
        return _verdict(out, "identical", ["every field, table and array of the mesh is the same, bit for bit"])

    shape = []
    for name in SHAPE_FIELDS:
        f = fields.get(name)
        if f is not None and "shapes" not in f and f["share_cells_differing"] > FEW_CELLS_SHARE:
            shape.append(f"{name} differs on {f['cells_differing']} of {f['cells']} cells ({f['share_cells_differing']:.2%})")
    plates = tables.get(SHAPE_TABLE)
    if plates and not plates["same_rows"]:
        shape.append(f"the worlds have {plates['rows'][0]} and {plates['rows'][1]} plates, {plates['rows_matched']} of "
                     f"them with the same number")
    if shape:
        return _verdict(out, "different planet", shape)

    kept = [f"{name} differs on {fields[name]['cells_differing']} cells" for name in SHAPE_FIELDS
            if name in fields and fields[name].get("cells_differing")]
    land = ("land and sea, plates and crust agree" + (f" but for a few cells ({'; '.join(kept)})" if kept else " on every cell"))
    grown = [n for n, f in fields.items() if _over_noise(f)] + [f"mesh {n}" for n, m in mesh.items() if _over_noise(m)]
    rows = [f"{t} ({e['rows'][0]} and {e['rows'][1]} rows, {e['rows_matched']} matched)"
            for t, e in tables.items() if not e["same_rows"]]
    grown_columns = [f"{t}.{c}" for t, e in tables.items() for c, col in e["columns"].items() if _over_noise(col)]
    if grown or rows or grown_columns or one_side:
        reasons = [land]
        if grown:
            reasons.append(f"{len(grown)} fields differ by more than {NOISE_SHARE_OF_RANGE:g} of their range (or in category) "
                           f"on more than {FEW_CELLS_SHARE:.1%} of the cells: {', '.join(grown)}")
        if rows:
            reasons.append("tables with rows the other lacks: " + ", ".join(rows))
        if grown_columns:
            reasons.append(f"{len(grown_columns)} table columns differ beyond the noise threshold: " + ", ".join(grown_columns))
        if one_side:
            reasons.append(f"fields or tables in one world only: {', '.join(one_side)}")
        return _verdict(out, "same planet with grown differences", reasons)
    reasons = [land, f"no field differs by more than {NOISE_SHARE_OF_RANGE:g} of its range on more than {FEW_CELLS_SHARE:.1%} "
                     f"of the cells; every table has the same rows"]
    if worst[1] is not None:
        reasons.append(f"the largest difference is {worst[0]:.3g} of the range of {worst[1]}")
    return _verdict(out, "same planet with rounding noise", reasons)


# ---------------------------------------------------------------------------------------------- what it prints
def _percent(share):
    return "0" if share == 0 else (f"{share:.2%}" if share >= 1e-4 else f"{share:.1e}")


def _months(f, what):
    key = next((k for k in f if k.startswith("share_cell_") and k.endswith(what)), None)
    return _percent(f[key]) if key else ""


HEADER = ["field", "kind", "largest difference", "of the range", "cells beyond rounding (or differing)",
          "cell-months beyond rounding (or differing)", "cells beyond the noise threshold"]


def rows_of(result) -> list:
    """One row per field that is not the same bit for bit, under HEADER."""
    out = []
    for name, f in result["fields"].items():
        if f["identical"]:
            continue
        if "shapes" in f:
            out.append([name, f["kind"], "shapes " + " and ".join(map(str, f["shapes"])), "", "", "", ""])
        elif f["kind"] == "category":
            out.append([name, "category", "", "", _percent(f["share_cells_differing"]), _months(f, "_differing"),
                        _percent(f["share_cells_differing"])])
        else:
            missing = f" (missing in one world: {f['missing_in_one']} values)" if f["missing_in_one"] else ""
            out.append([name, "number", f"{f['largest_absolute']:.3g}{missing}", f"{f['largest_relative']:.2e}",
                        _percent(f["share_cells_beyond_rounding"]), _months(f, "_beyond_rounding"),
                        _percent(f["share_cells_beyond_noise"])])
    return out


def _rows_text(n):
    return f"{n} row" + ("" if n == 1 else "s")


def table_lines(result) -> list:
    """One line per table that is not the same bit for bit."""
    lines = []
    for t, e in result["tables"].items():
        if e["identical"]:
            continue
        by = f"matched by {', '.join(e['key'])}" if e["key"] else "matched row by row"
        if not e["same_rows"]:
            lines.append(f"{t}: {e['rows'][0]} and {e['rows'][1]} rows; {e['rows_matched']} {by}, "
                         f"{e['rows_only_in_a']} in A only, {e['rows_only_in_b']} in B only")
            continue
        over = [c for c, col in e["columns"].items() if _over_noise(col)]
        differ = [c for c, col in e["columns"].items() if not col["identical"]]
        lines.append(f"{t}: {_rows_text(e['rows'][0])} in each, {by}; {len(differ)} of {len(e['columns'])} columns differ"
                     + (f", beyond the noise threshold on more than a few rows: {', '.join(over)}" if over
                        else ", within the noise threshold"))
    return lines


def text(result) -> str:
    lines = [f"A: {result['a']}", f"B: {result['b']}"]
    for key, (a, b) in result["provenance"].items():
        if key == "packages":
            changed = sorted(k for k in set(a or {}) | set(b or {}) if (a or {}).get(k) != (b or {}).get(k))
            lines.append("  packages differ: " + ", ".join(f"{k} {(a or {}).get(k)} and {(b or {}).get(k)}" for k in changed))
        else:
            lines.append(f"  {key} differs: {a} and {b}")
    lines.append("")
    lines.append(f"Verdict: {result['verdict_text']}.")
    if "counts" in result:
        c = result["counts"]
        lines.append(f"{c['fields_identical']} of {c['fields']} fields and {c['tables_identical']} of {c['tables']} tables are the "
                     f"same bit for bit, and {c['mesh_arrays_identical']} of {c['mesh_arrays']} arrays of the mesh; "
                     f"{c['fields_beyond_rounding']} fields differ beyond the float32 rounding (or in category) on some cell, "
                     f"{c['fields_beyond_noise']} beyond the noise threshold on more than a few cells.")
    mesh = [n for n, m in result["mesh"].items() if not m["identical"]]
    if mesh:
        lines.append("Mesh arrays that differ: " + ", ".join(
            f"{n} (largest {result['mesh'][n]['largest_relative']:.2e} of the range)" if result["mesh"][n]["kind"] == "number"
            and "shapes" not in result["mesh"][n] else n for n in mesh))
    rows = rows_of(result)
    if rows:
        widths = [max(len(str(r[i])) for r in [HEADER] + rows) for i in range(len(HEADER))]
        lines.append("")
        lines.append("Fields that differ (shares of the cells; 'of the range' is the largest difference over the field's range):")
        lines.append("  " + " | ".join(h.ljust(w) for h, w in zip(HEADER, widths)).rstrip())
        for r in rows:
            lines.append(("  " + " | ".join(str(v).ljust(w) for v, w in zip(r, widths))).rstrip())
    tl = table_lines(result)
    if tl:
        lines.append("")
        lines.append("Tables that differ:")
        lines.extend("  " + t for t in tl)
    return "\n".join(lines)


def markdown(result, title=None) -> str:
    lines = [f"### {title or result['b']}", "", f"**{result['verdict_text']}.**", ""]
    rows = rows_of(result)
    if rows:
        lines.append("| " + " | ".join(HEADER) + " |")
        lines.append("|" + "---|" * len(HEADER))
        lines.extend("| " + " | ".join(str(v) for v in r) + " |" for r in rows)
        lines.append("")
    lines.extend(f"- {t}" for t in table_lines(result))
    return "\n".join(lines) + "\n"


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value


def parser():
    p = console.tool_parser(__doc__, "python tools/compare_worlds.py")
    p.add_argument("store_a", metavar="STORE_A", help="the reference world store")
    p.add_argument("store_b", metavar="STORE_B", help="the world store compared with it")
    p.add_argument("--json", metavar="OUT", help="write everything measured to this file, as JSON")
    p.add_argument("--markdown", metavar="OUT", help="append the verdict and the table of differing fields to this file")
    p.add_argument("--title", help="the heading of the markdown section (default: STORE_B)")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    for path in (args.store_a, args.store_b):
        if not Path(path).exists():
            print(f"no world store at {path}", file=sys.stderr)
            return 2
    try:
        result = compare(args.store_a, args.store_b)
    except (KeyError, ValueError, OSError) as problem:      # zarr's "no group found" (a folder that is no store) is an OSError
        print(f"the stores could not be compared: {problem!r}", file=sys.stderr)
        return 2
    print(text(result))
    if args.json:
        Path(args.json).write_text(json.dumps(_json_safe(result), indent=1), encoding="utf-8")
    if args.markdown:
        with open(args.markdown, "a", encoding="utf-8") as f:
            f.write(markdown(result, args.title) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
