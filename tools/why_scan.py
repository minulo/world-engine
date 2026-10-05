"""Read the "why" answers of a world and report every one that says something the stored numbers contradict.

    python tools/why_scan.py worlds/first.zarr [--every 1]

For every cell (or every n-th with --every n) and every field of water on land, the answer is asked for and held
against the fields of the same cell: a sea cell must be called sea, ground under a lake must not be said to shed
runoff, a river's "largest source upstream" must be another cell, and so on. Every answer is also read for the
marks of a sentence that fell apart: a slot left unfilled, stray punctuation, a number of ten digits.

The rules are the ones that the review of build step 2 found broken. A world that passes has answers that are true
of its numbers in these respects; it says nothing about whether the numbers are right.
"""
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldengine import store                            # noqa: E402
from worldengine.causes import explain                   # noqa: E402

FIELDS = ("river_discharge", "runoff", "runoff_annual", "lake_fraction", "lake_level", "soil_moisture", "evapotranspiration",
          "snow_water", "snow_cover", "potential_evapotranspiration", "drainage_area", "basin_id", "depression_id",
          "spill_elevation", "flow_receiver", "slope", "soil_water_capacity")
BROKEN = [(re.compile(pattern), what) for pattern, what in (
    (r"[{}]", "a slot left unfilled"), (r"\s[.,;:]", "a space before a mark"), (r"\.\.", "two full stops"),
    (r"[:;,]\.", "a mark before the full stop"), (r"  ", "two spaces"), (r"\bnan\b|\binf\b|\bNone\b", "a value that is no value"),
    (r"\d{9,}", "a number of nine digits or more"), (r":\s*$", "ends on a colon"), (r"; [A-Z]", "a capital after a semicolon"))]


def scan(view, cells=None, fields=FIELDS) -> list:
    """The problems found: a list of (cell, field, what is wrong, the sentence)."""
    have = set(view.field_names())
    fields = [f for f in fields if f in have]
    f = {name: np.asarray(view.field(name)) for name in set(fields) | {"ocean_mask", "lake_fraction", "runoff", "snow_water", "snow_cover"}
         if name in have}
    sea = f["ocean_mask"].astype(bool)
    year = lambda name: f[name].astype(np.float64).mean(axis=0) if f[name].ndim == 2 else f[name].astype(np.float64)
    share = f["lake_fraction"].astype(np.float64) if "lake_fraction" in f else np.zeros(sea.size)
    runoff = year("runoff") if "runoff" in f else np.zeros(sea.size)
    snow = f["snow_water"].astype(np.float64) if "snow_water" in f else np.zeros((1, sea.size))
    cover = f["snow_cover"].astype(np.float64) if "snow_cover" in f else np.zeros((1, sea.size))
    crossing = np.asarray(view.driver("river_discharge", "place")) == 1 if "river_discharge" in f else np.zeros(sea.size, dtype=bool)
    ice = np.asarray(view.driver("snow_water", "left_as_ice")).astype(np.float64).sum(axis=0) > 0 if "snow_water" in have else None
    problems = []
    for cell in (range(sea.size) if cells is None else cells):
        cell = int(cell)
        for field in fields:
            chain = explain(view, cell, field)["chain"]
            first = chain[0]["text"]

            def wrong(what, text=first):
                problems.append((cell, field, what, text))

            def must(words, when=True):
                if when and not any(w in first for w in ([words] if isinstance(words, str) else words)):
                    wrong(f"does not say {words!r}")

            def must_not(words, when=True):
                if when and words in first:
                    wrong(f"says {words!r}")
            for step in chain:
                for pattern, what in BROKEN:
                    if pattern.search(step["text"]):
                        wrong(what, step["text"])
                if not step["text"].rstrip().endswith((".", ")")):
                    wrong("does not end as a sentence", step["text"])
            value = year(field)[cell]
            wet, full, part = bool(sea[cell]), share[cell] >= 1.0, 0.0 < share[cell] < 1.0
            if field == "runoff":
                must("This cell is sea", wet)
                must("wholly under a lake", not wet and full)
                must("No water runs off", not wet and not full and value == 0)
                must("Runoff here averages", not wet and not full and value > 0)
            elif field == "river_discharge":
                must("This cell is sea", wet)
                must("no river ends in it", wet and value == 0)
                must("lake that overflows", crossing[cell])
                must("closed lake", not wet and not crossing[cell] and share[cell] > 0)
                must("No river runs through this cell", not wet and not crossing[cell] and share[cell] == 0 and value == 0)
                must("The river here carries", not wet and not crossing[cell] and share[cell] == 0 and value > 0)
                must_not("the cell's own runoff gives", runoff[cell] == 0)
                named = re.search(r"where the largest single source is cell (\d+),", first)
                if "arrive from upstream" in first:
                    if not named or int(named.group(1)) == cell:
                        wrong("names the cell itself, or no cell, as the largest source upstream")
                    elif not any(step["cell"] == int(named.group(1)) and step["field"] == "runoff" for step in chain[1:]) \
                            and len(chain) < 16 and float(view.driver(field, "from_upstream")[:, cell].mean()) >= 0.1 * value:
                        wrong("does not go on to the cell it names as the largest source upstream")
            elif field == "evapotranspiration":
                must("This cell is sea", wet)
                must("No water goes back", not wet and value == 0)
                must("returns", not wet and value > 0)
                must_not("open water of a lake", share[cell] == 0)
                must_not("the soil gives", not wet and full)
            elif field == "potential_evapotranspiration":
                must("This cell is sea", wet)
                must("snow covers it through every month", not wet and cover[:, cell].min() >= 1.0)
                must("no snow covers it in any month", not wet and cover[:, cell].max() == 0.0)
                must("for part of the year", not wet and cover[:, cell].max() > 0.0 and cover[:, cell].min() < 1.0)
                must_not("could take 0.00", not wet and "gains" in first and cover[:, cell].max() == 0.0
                         and float(np.asarray(view.driver(field, "net_radiation"))[:, cell].min()) > 5.0)
            elif field in ("snow_water", "snow_cover"):
                must("This cell is sea", wet)
                must(["No snow lies"], not wet and snow[:, cell].max() == 0.0)
                must("lies all year", field == "snow_water" and not wet and bool(ice[cell]))
                must_not("all melt", field == "snow_water" and not wet and bool(ice[cell]))
            elif field == "soil_moisture":
                must("This cell is sea: it has no soil.", wet)
                must("under a lake", not wet and full)
                must("Part of the cell lies under a lake", not wet and part)
            elif field == "drainage_area":
                must("This cell is sea.", wet)
                must_not("its own area, plus", wet)
            elif field == "basin_id":
                must("belongs to no river basin", wet)
                must(f"leaves the land at cell {int(f['basin_id'][cell])},", not wet)
            elif field == "soil_water_capacity":
                must("it has no soil", wet)
                must("can hold", not wet)
            elif field == "lake_fraction":
                must("No lake reaches it", share[cell] == 0)
                must(["It is a lake with an outlet", "It is a closed lake", "It is a lake in a hollow with no way out"], share[cell] > 0)
                must("km²", share[cell] > 0)
            elif field == "lake_level":
                must("No lake reaches this cell", share[cell] == 0)
    return problems


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    every = int(args[args.index("--every") + 1]) if "--every" in args else 1
    v = store.StoreView(args[0])
    n = v.attrs["meta"]["cells"]
    found = scan(v, range(0, n, every))
    kinds = {}
    for cell, field, what, text in found:
        kinds.setdefault((field, what), []).append((cell, text))
    for (field, what), cases in sorted(kinds.items()):
        print(f"{field}: {what}: {len(cases)} answers, the first at cell {cases[0][0]}:\n    {cases[0][1]}")
    asked = len(range(0, n, every)) * len([f for f in FIELDS if f in v.field_names()])
    print(f"{asked} answers read; {len(found)} problems" if found else f"{asked} answers read; none says anything its numbers contradict")
    sys.exit(1 if found else 0)
