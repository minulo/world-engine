"""Compare two world stores field by field and say how far apart the two worlds are.

    python tools/compare_worlds.py STORE_A STORE_B [--json OUT] [--markdown OUT]

The same seed and parameters give the same world, bit for bit, on one machine; between machines the fingerprints of
many fields differ (README, "Worlds from another system"). This tool measures by how much. STORE_A is the reference.

For every field, every array of the mesh and every column of every table it gives:

  * for a number (a float array): the largest absolute difference; the same as a share of the field's range (the
    largest value less the smallest, over both worlds); the share of the cells, and for a field with one slice per
    month the share of the cell-months, that differ by more than the float32 rounding of the value; and the share
    of the cells that differ by more than the noise threshold below;
  * for a category, an index or a true-or-false field (ocean_mask, biome, climate_class, plate_id, rock_type, ...):
    the share of the cells (and cell-months) whose value differs;
  * for a table (plates, lakes, seas, storms, ...): the number of rows in each world, and, where the numbers agree,
    each column as above, row by row.

A cell counts as differing when any of its months or components does. Then one verdict:

  identical             every array is the same, bit for bit;
  rounding noise        the same planet with rounding noise: land and sea, plates and crust agree on all but a few
                        cells, every table has the same rows, and no field or column differs by more than
                        NOISE_SHARE_OF_RANGE of its range on more than FEW_CELLS_SHARE of its cells or rows;
  grown differences     the same land and sea, plates and crust (as above), but some field or column differs by more
                        than the noise threshold on more than a few cells, or a table has other rows;
  different planet      land and sea, the plates or the crust differ on more than FEW_CELLS_SHARE of the cells, or
                        the plates table has another number of plates;
  not comparable        the stores hold meshes of other sizes or other neighbours, so their cells do not correspond.

The thresholds, and why:

  * The float32 rounding of a value is one unit in the last place of the value as a float32 (numpy.spacing). Two
    computations of the same quantity that round differently once end one unit apart; a field stored in float32
    cannot hold a smaller difference, and a float64 field (cell_area, latitude) is held to the same unit, so that
    its differences in the last bits of a float64 do not count.
  * NOISE_SHARE_OF_RANGE = 0.001: a thousandth of the field's range. It lies four orders of magnitude above the
    rounding of a float32 (about 1.2e-7 of a value), leaving room for a last-bit difference to grow through the
    rounds of the climate, and below what a map shows: a colour scale of 256 steps over the range resolves about
    0.004 of it [INFERRED from the arithmetic; how the viewer colours a field was not read for this].
  * FEW_CELLS_SHARE = 0.001: a thousandth of the cells, 10 of the 10,242 cells of the preview world. "A few cells"
    of coast that fall the other way are a detail; more is another coastline.

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
SHAPE_TABLE = "plates"            # a world with another number of plates is another planet
MESH_TOPOLOGY = ("nbr", "nbr_count")                      # where these differ, the cells of the two worlds do not correspond
CATEGORICAL_KINDS = ("category", "index", "boolean")
PROVENANCE = ("engine_version", "code_fingerprint", "lock_fingerprint", "seed", "packages")
META = ("profile", "mesh_level", "cells", "months", "seed", "math_threads", "parameters_fingerprint")
VERDICTS = ("identical", "rounding noise", "grown differences", "different planet", "not comparable")


# ---------------------------------------------------------------------------------------------- one array against another
def _per_cell(mask, months_first):
    """A mask over the array, reduced to one value per cell (any month, any component) and, for an array with one slice
    per month, one per cell-month. Returns (cells differing, cells, cell-months differing or None, cell-months or None)."""
    if mask.ndim == 0:
        mask = mask.reshape(1)
    lead = 2 if months_first and mask.ndim >= 2 else 1
    flat = mask.reshape(mask.shape[:lead] + (-1,)).any(axis=-1)          # components of a direction folded into their cell
    if lead == 2:
        return int(flat.any(axis=0).sum()), int(flat.shape[1]), int(flat.sum()), int(flat.size)
    return int(flat.sum()), int(flat.shape[0]), None, None


def _share(count, total):
    return float(count / total) if total else 0.0


def compare_array(a, b, categorical, months_first=False):
    """How far the array `b` lies from the reference `a`. A dict that JSON can hold."""
    a, b = np.asarray(a), np.asarray(b)
    out = {"kind": "category" if categorical else "number", "shape": list(a.shape), "dtype": str(a.dtype)}
    if a.shape != b.shape:
        out.update(identical=False, shapes=[list(a.shape), list(b.shape)])
        return out
    out["identical"] = bool(a.dtype == b.dtype and np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes())
    if categorical:
        differ = a != b
        cells, n, months, nm = _per_cell(differ, months_first)
        out.update(cells=n, cells_differing=cells, share_cells_differing=_share(cells, n))
        if months is not None:
            out.update(cell_months_differing=months, share_cell_months_differing=_share(months, nm))
        return out
    x, y = a.astype(np.float64), b.astype(np.float64)
    with np.errstate(invalid="ignore", over="ignore"):
        missing = np.isnan(x) | np.isnan(y)
        lost = np.isnan(x) != np.isnan(y)                               # a value missing in one world and present in the other
        gap = np.where(missing | (x == y), 0.0, np.abs(x - y))
        unit = np.spacing(np.maximum(np.abs(x), np.abs(y)).astype(np.float32)).astype(np.float64)
        beyond_rounding = lost | (gap > unit) | np.isinf(gap)
        values = np.concatenate([x[np.isfinite(x)], y[np.isfinite(y)]])
        span = float(values.max() - values.min()) if values.size else 0.0
        if span == 0.0:
            span = float(np.abs(values).max()) if values.size else 0.0
        beyond_noise = lost | (gap > NOISE_SHARE_OF_RANGE * span) | np.isinf(gap)
    largest = float(gap.max()) if gap.size else 0.0
    out.update(range=span, largest_absolute=largest,
               largest_relative=(largest / span if span else (0.0 if largest == 0.0 else float("inf"))),
               missing_in_one=int(lost.sum()))
    cells, n, months, nm = _per_cell(beyond_rounding, months_first)
    out.update(cells=n, cells_beyond_rounding=cells, share_cells_beyond_rounding=_share(cells, n))
    if months is not None:
        out.update(cell_months_beyond_rounding=months, share_cell_months_beyond_rounding=_share(months, nm))
    cells, n, months, nm = _per_cell(beyond_noise, months_first)
    out.update(cells_beyond_noise=cells, share_cells_beyond_noise=_share(cells, n))
    if months is not None:
        out.update(cell_months_beyond_noise=months, share_cell_months_beyond_noise=_share(months, nm))
    return out


def _is_categorical(array, spec=None):
    return (spec or {}).get("kind") in CATEGORICAL_KINDS or np.asarray(array).dtype.kind in "biu"


def _over_noise(entry):
    """Whether one compared array differs by more than rounding noise on more than a few of its cells or rows."""
    if "shapes" in entry:
        return True
    if entry["kind"] == "category":
        return entry["share_cells_differing"] > FEW_CELLS_SHARE
    return entry["share_cells_beyond_noise"] > FEW_CELLS_SHARE


# ---------------------------------------------------------------------------------------------- two stores
def compare(store_a, store_b) -> dict:
    """Compare two world stores (paths or StoreViews). Returns everything the tool reports, as a dict JSON can hold."""
    va = store_a if isinstance(store_a, StoreView) else StoreView(store_a)
    vb = store_b if isinstance(store_b, StoreView) else StoreView(store_b)
    out = {"a": str(va.path), "b": str(vb.path),
           "thresholds": {"float32_rounding": "one unit in the last place of the value as a float32",
                          "noise_share_of_range": NOISE_SHARE_OF_RANGE, "few_cells_share": FEW_CELLS_SHARE,
                          "shape_fields": list(SHAPE_FIELDS)},
           "provenance": {}, "mesh": {}, "fields": {}, "tables": {}}
    for key in PROVENANCE:
        if va.attrs.get(key) != vb.attrs.get(key):
            out["provenance"][key] = [va.attrs.get(key), vb.attrs.get(key)]
    for key in META:
        if va.meta.get(key) != vb.meta.get(key):
            out["provenance"][f"meta.{key}"] = [va.meta.get(key), vb.meta.get(key)]

    if va.meta.get("cells") != vb.meta.get("cells"):
        return _verdict(out, "not comparable", [f"the meshes hold {va.meta.get('cells')} and {vb.meta.get('cells')} cells"])
    mesh_names = ("xyz", "nbr", "nbr_count", "area", "lat", "lon", "east", "north")
    for name in mesh_names:
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
        months_first = str(spec.get("shape", "")).startswith("month")
        out["fields"][name] = compare_array(a, b, _is_categorical(a, spec), months_first)

    tables_a, tables_b = set(va.table_names()), set(vb.table_names())
    out["tables_only_in_a"], out["tables_only_in_b"] = sorted(tables_a - tables_b), sorted(tables_b - tables_a)
    for t in sorted(tables_a & tables_b):
        ta, tb = va.table(t), vb.table(t)
        rows = [_rows(ta), _rows(tb)]
        entry = {"rows": rows, "columns": {}}
        if rows[0] == rows[1]:
            for col in sorted(set(ta) & set(tb)):
                entry["columns"][col] = compare_array(ta[col], tb[col], _is_categorical(ta[col]))
        entry["identical"] = rows[0] == rows[1] and set(ta) == set(tb) and all(c["identical"] for c in entry["columns"].values())
        out["tables"][t] = entry
    return _judge(out)


def _rows(table):
    return int(len(next(iter(table.values())))) if table else 0


def _verdict(out, verdict, reasons):
    out["verdict"], out["reasons"] = verdict, reasons
    out["verdict_text"] = f"{verdict}: " + "; ".join(reasons)
    return out


def _judge(out) -> dict:
    fields, tables = out["fields"], out["tables"]
    everything = [*out["mesh"].values(), *fields.values(), *(c for t in tables.values() for c in t["columns"].values())]
    out["counts"] = {"fields": len(fields), "fields_identical": sum(f["identical"] for f in fields.values()),
                     "tables": len(tables), "tables_identical": sum(t["identical"] for t in tables.values()),
                     "mesh_arrays_identical": sum(m["identical"] for m in out["mesh"].values())}
    if (all(e["identical"] for e in everything) and all(t["identical"] for t in tables.values())
            and not (out["only_in_a"] or out["only_in_b"] or out["tables_only_in_a"] or out["tables_only_in_b"])):
        return _verdict(out, "identical", ["every field, table column and mesh array is the same, bit for bit"])

    shape = []
    for name in SHAPE_FIELDS:
        f = fields.get(name)
        if f is not None and "shapes" not in f and f["share_cells_differing"] > FEW_CELLS_SHARE:
            shape.append(f"{name} differs on {f['cells_differing']} of {f['cells']} cells ({f['share_cells_differing']:.2%})")
    plates = tables.get(SHAPE_TABLE)
    if plates and plates["rows"][0] != plates["rows"][1]:
        shape.append(f"the worlds have {plates['rows'][0]} and {plates['rows'][1]} plates")
    if shape:
        return _verdict(out, "different planet", shape)

    kept = [f"{name} differs on {fields[name]['cells_differing']} cells" for name in SHAPE_FIELDS
            if name in fields and fields[name].get("cells_differing")]
    grown = [n for n, f in fields.items() if _over_noise(f)]
    grown += [f"mesh {n}" for n, m in out["mesh"].items() if _over_noise(m)]
    rows = [f"{t} ({e['rows'][0]} and {e['rows'][1]} rows)" for t, e in tables.items() if e["rows"][0] != e["rows"][1]]
    grown_columns = [f"{t}.{c}" for t, e in tables.items() for c, col in e["columns"].items() if _over_noise(col)]
    worst = max(((f["largest_relative"], n) for n, f in fields.items() if f["kind"] == "number" and "shapes" not in f),
                default=(0.0, None))
    land = ("land and sea, plates and crust agree" + (f" but for a few cells ({'; '.join(kept)})" if kept else " on every cell"))
    if grown or rows or grown_columns or out["only_in_a"] or out["only_in_b"]:
        reasons = [land]
        if grown:
            reasons.append(f"{len(grown)} fields differ by more than {NOISE_SHARE_OF_RANGE:g} of their range (or in category) "
                           f"on more than {FEW_CELLS_SHARE:.1%} of the cells: {', '.join(grown)}")
        if rows:
            reasons.append("tables with other rows: " + ", ".join(rows))
        if grown_columns:
            reasons.append(f"{len(grown_columns)} table columns differ beyond the noise threshold: " + ", ".join(grown_columns))
        if out["only_in_a"] or out["only_in_b"]:
            reasons.append(f"fields in one world only: {', '.join(out['only_in_a'] + out['only_in_b'])}")
        return _verdict(out, "grown differences", reasons)
    reasons = [land, f"no field differs by more than {NOISE_SHARE_OF_RANGE:g} of its range on more than {FEW_CELLS_SHARE:.1%} "
                     f"of the cells; every table has the same rows"]
    if worst[1] is not None:
        reasons.append(f"the largest difference is {worst[0]:.3g} of the range of {worst[1]}")
    return _verdict(out, "rounding noise", reasons)


# ---------------------------------------------------------------------------------------------- what it prints
def _percent(share):
    return "0" if share == 0 else (f"{share:.2%}" if share >= 1e-4 else f"{share:.1e}")


def rows_of(result) -> list:
    """One row per field that is not the same bit for bit: name, kind, largest absolute, as a share of the range,
    cells beyond rounding (or differing), cell-months beyond rounding (or differing), cells beyond the noise threshold."""
    out = []
    for name, f in result["fields"].items():
        if f["identical"]:
            continue
        if "shapes" in f:
            out.append([name, f["kind"], "shapes " + " and ".join(map(str, f["shapes"])), "", "", "", ""])
        elif f["kind"] == "category":
            out.append([name, "category", "", "", _percent(f["share_cells_differing"]),
                        _percent(f["share_cell_months_differing"]) if "share_cell_months_differing" in f else "", ""])
        else:
            missing = f" (missing in one world: {f['missing_in_one']} values)" if f["missing_in_one"] else ""
            out.append([name, "number", f"{f['largest_absolute']:.3g}{missing}", f"{f['largest_relative']:.2e}",
                        _percent(f["share_cells_beyond_rounding"]),
                        _percent(f["share_cell_months_beyond_rounding"]) if "share_cell_months_beyond_rounding" in f else "",
                        _percent(f["share_cells_beyond_noise"])])
    return out


HEADER = ["field", "kind", "largest difference", "of the range", "cells beyond rounding (or differing)",
          "cell-months beyond rounding", "cells beyond the noise threshold"]


def _rows_text(n):
    return f"{n} row" + ("" if n == 1 else "s")


def table_lines(result) -> list:
    lines = []
    for t, e in result["tables"].items():
        if e["identical"]:
            continue
        if e["rows"][0] != e["rows"][1]:
            lines.append(f"{t}: {e['rows'][0]} and {e['rows'][1]} rows")
            continue
        over = [c for c, col in e["columns"].items() if _over_noise(col)]
        differ = [c for c, col in e["columns"].items() if not col["identical"]]
        lines.append(f"{t}: {_rows_text(e['rows'][0])} in each; {len(differ)} of {len(e['columns'])} columns differ"
                     + (f", beyond the noise threshold on more than a few rows: {', '.join(over)}" if over else ", within the noise threshold"))
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
                     f"same bit for bit; {c['mesh_arrays_identical']} of {len(result['mesh'])} arrays of the mesh.")
    mesh = [n for n, m in result["mesh"].items() if not m["identical"]]
    if mesh:
        lines.append("Mesh arrays that differ: " + ", ".join(
            f"{n} (largest {result['mesh'][n].get('largest_relative', 0):.2e} of the range)" if result["mesh"][n]["kind"] == "number"
            else n for n in mesh))
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
    if isinstance(value, list):
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
    except (KeyError, ValueError, OSError) as problem:
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
