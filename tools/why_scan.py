"""Read the "why" answers of a world and report every one that says something the stored numbers contradict.

    python tools/why_scan.py worlds/first.zarr [--every 1]

For every cell (or every n-th with --every n) and every field of FIELDS, the answer is asked for and held against the
fields of the same cell. The rules are of three kinds.

  * What a sentence says of the place: a sea cell must be called sea, ground under a lake must not be said to shed
    runoff, a river's "largest source upstream" must be another cell, a cell under "the sinking branch of the
    northern loop" must lie north of the equator, a receiver called "its lowest neighbour" must be the lowest
    neighbour, and so on.
  * The numbers a sentence gives, read back out of it: the parts of a sum must add up to the value given, a
    temperature must be the stored one, a change of temperature must carry its sign, the water that "melts" and
    the water that "leaves as ice" must be the stored ones in that order, a lake's inflow must be a volume and the
    stored one, and the place given for a cell must be where the mesh has that cell, north or south, east or west.
  * The marks of a sentence that fell apart: a slot left unfilled, stray punctuation, a number of nine digits.

The rules are the ones that the checks of build step 2 found broken or found untested: the first review's; five that
the fourth check found broken (a cell at the brim of a lake said to lie in it and to be reached by no lake; water
said to "arrive" that was the arriving water times the dry share of the cell; a largest source that sheds nothing;
a lake's answer that went on to another hollow's level as if it were the lake's; snow said to lie "for part of the
year" where it lies all year); the ones the fourth check found that no test would notice if they broke (the
sentence patterns of sea and land, of the loops, of what limits plants, of level ground; the units and signs of
numbers; places); and one that the fifth check found broken (in a cell under a closed lake, water said to arrive
that had entered the lake further up). A world that passes has answers that are true of its numbers in these
respects. It says nothing about whether the numbers are right, nor about faults of a kind nobody has found yet.

What holds the scan itself: tests/test_world.py plants 33 faults in true answers, one for each kind of fault that a
check found and for some of the other rules, and asks that the scan report each and nothing else. Most of the
rules below have no planted fault of their own: the fifth check took four of them out, one at a time, and no test
noticed (those four have one now).
"""
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml                                              # noqa: E402

from worldengine import console, store                   # noqa: E402
from worldengine.causes import as_text, explain          # noqa: E402
from worldengine.library import drainage as dr           # noqa: E402

FIELDS = ("river_discharge", "runoff", "runoff_annual", "lake_fraction", "lake_level", "soil_moisture", "evapotranspiration",
          "snow_water", "snow_cover", "potential_evapotranspiration", "drainage_area", "basin_id", "depression_id",
          "spill_elevation", "flow_receiver", "slope", "soil_water_capacity",
          "ocean_mask", "subsidence", "biome", "surface_temperature", "precipitation")
NUMBER = r"-?\d[\d,]*(?:\.\d+)?(?:e[+-]?\d+)?"         # a number as a sentence prints it: 1,234 or 0.05 or 1.2e-05
PLACE = re.compile(r"([\d.]+)° ([NS]), ([\d.]+)° ([EW])")
BROKEN = [(re.compile(pattern), what) for pattern, what in (
    (r"[{}]", "a slot left unfilled"), (r"\s[.,;:]", "a space before a mark"), (r"\.\.", "two full stops"),
    (r"[:;,]\.", "a mark before the full stop"), (r"  ", "two spaces"), (r"\bnan\b|\binf\b|\bNone\b", "a value that is no value"),
    (r"\d{9,}", "a number of nine digits or more"), (r":\s*$", "ends on a colon"), (r"; [A-Z]", "a capital after a semicolon"))]


IN_A_LAKE, CLOSED_LAKE, AT_THE_BRIM, UNDER_A_CLOSED_LAKE = 1, 2, 4, 5       # the classes of the driver river_discharge.place


def number(text) -> float:
    return float(text.replace(",", ""))


def is_place(found, lat, lon) -> bool:
    """Whether "12.3° S, 45.6° W" (as PLACE found it) is the place with this latitude and longitude, to the decimal printed."""
    text_lat, ns, text_lon, ew = found
    return (abs(float(text_lat) - abs(lat)) < 0.051 and abs(float(text_lon) - abs(lon)) < 0.051
            and (ns == ("N" if lat >= 0 else "S") or abs(lat) < 0.05)
            and (ew == ("E" if lon >= 0 else "W") or abs(lon) < 0.05 or abs(abs(lon) - 180.0) < 0.05))


def close(said, stored, volume=False) -> bool:
    """Whether a number read out of a sentence is the stored one, as far as a sentence prints it. A sentence prints a
    number with no decimal from 1000 on, one from 10, two from a tenth, and three figures below (causes._fmt); a
    volume in km³ with none from 100 on and one from 1."""
    size = abs(stored)
    step = (1.0 if size >= 100 else 0.1 if size >= 1 else None) if volume else (1.0 if size >= 1000 else 0.1 if size >= 10 else 0.01 if size >= 0.1 else None)
    return abs(said - stored) <= (0.51 * step if step else 0.006 * size + 1e-12)


def scan(view, cells=None, fields=FIELDS) -> list:
    """The problems found: a list of (cell, field, what is wrong, the sentence)."""
    have = set(view.field_names())
    fields = [f for f in fields if f in have]
    wanted = set(fields) | {"ocean_mask", "lake_fraction", "runoff", "snow_water", "snow_cover", "river_discharge", "flow_receiver",
                           "depression_id", "elevation", "sea_depth", "height_above_sea", "biome"}
    f = {name: np.asarray(view.field(name)) for name in wanted if name in have}
    n = view.attrs["meta"]["cells"]
    lat, lon = np.asarray(view.mesh_array("lat")), np.asarray(view.mesh_array("lon"))
    sea = f["ocean_mask"].astype(bool) if "ocean_mask" in f else np.zeros(n, dtype=bool)
    year = lambda name: f[name].astype(np.float64).mean(axis=0) if f[name].ndim == 2 else f[name].astype(np.float64)
    share = f["lake_fraction"].astype(np.float64) if "lake_fraction" in f else np.zeros(n)
    runoff = year("runoff") if "runoff" in f else np.zeros(n)
    snow = f["snow_water"].astype(np.float64) if "snow_water" in f else np.zeros((1, n))
    cover = f["snow_cover"].astype(np.float64) if "snow_cover" in f else np.zeros((1, n))
    rivers = "river_discharge" in f
    place = np.asarray(view.driver("river_discharge", "place")) if rivers else np.zeros(n, dtype=np.int64)
    in_lake, brim, closed, drowned = (place == code for code in (IN_A_LAKE, AT_THE_BRIM, CLOSED_LAKE, UNDER_A_CLOSED_LAKE))
    snowy = "snow_water" in have
    ice = np.asarray(view.driver("snow_water", "left_as_ice")).astype(np.float64).sum(axis=0) > 0 if snowy else None
    lakes = view.table("lakes") if "lake_fraction" in f else None
    brought = np.zeros(n)                                    # what the cells that drain into each cell carry, by the stored field:
    if rivers and "flow_receiver" in f:                      # down the receivers, and from a lake that overflows into the cell
        to = f["flow_receiver"].astype(np.int64)
        np.add.at(brought, to[to >= 0], year("river_discharge")[to >= 0])
        if lakes is not None:
            runs = np.asarray(lakes["overflows"]).astype(bool)
            np.add.at(brought, np.asarray(lakes["spills_into_cell"])[runs], year("river_discharge")[np.asarray(lakes["outlet_cell"])[runs]])
    lake_of = np.asarray(view.driver("lake_fraction", "lake")) if "lake_fraction" in f else None
    # the sea, worked out from the fields themselves: the cells of the main sea are the wet cells joined to its lowest cell
    main_sea, sea_level, surface, nbr = None, None, None, np.asarray(view.mesh_array("nbr"))
    if "ocean_mask" in f and "elevation" in f:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        seas = view.table("seas")
        sea_level = float(seas["surface_m"][0])
        a = np.repeat(np.arange(n), nbr.shape[1])
        b = nbr.ravel()
        joined = (b >= 0) & sea[a] & sea[np.maximum(b, 0)]
        _, body = connected_components(coo_matrix((np.ones(int(joined.sum())), (a[joined], b[joined])), shape=(n, n)), directed=False)
        main_sea = sea & (body == body[int(seas["lowest_cell"][0])])
        if "sea_depth" in f:
            surface = dr.drainage_surface(f["elevation"].astype(np.float64), f["sea_depth"], sea, seas["surface_m"])
    limits = {}
    if "biome" in fields:                                    # which biomes the model's constants call limited by cold, and by drought
        constants = yaml.safe_load(view.attrs["parameters_text"]["models"])["slots"]["Biomes"]["constants"]
        limits = {**{name: "what limits plant life here is cold" for name in constants["limited_by_cold"]},
                  **{name: "what limits plant life here is drought" for name in constants["limited_by_dryness"]}}
        biome_names = view.specs["biome"]["categories"]
    problems = []
    for cell in (range(n) if cells is None else cells):
        cell = int(cell)
        for field in fields:
            answer = explain(view, cell, field)
            chain = answer["chain"]
            first = chain[0]["text"]

            def wrong(what, text=first):
                problems.append((cell, field, what, text))

            def must(words, when=True):
                if when and not any(w in first for w in ([words] if isinstance(words, str) else words)):
                    wrong(f"does not say {words!r}")

            def must_not(words, when=True):
                if when and words in first:
                    wrong(f"says {words!r}")

            def read(pattern, what):
                """The numbers of a place in the sentence, or None with a problem reported: the sentence has not the form asked."""
                found = re.search(pattern, first)
                if not found:
                    wrong(f"gives no {what} in the form asked ({pattern})")
                return None if not found else [number(g) for g in found.groups()]
            heading = as_text(answer).split("\n", 1)[0]
            at = PLACE.search(heading)
            if not heading.startswith(f"Why is {field} like this at ") or not heading.endswith(f" (cell {cell})?") or not at \
                    or not is_place(at.groups(), lat[cell], lon[cell]):
                wrong("the heading does not give the place of the cell", heading)
            for step in chain:
                for pattern, what in BROKEN:
                    if pattern.search(step["text"]):
                        wrong(what, step["text"])
                if not step["text"].rstrip().endswith((".", ")")):
                    wrong("does not end as a sentence", step["text"])
                if step["field"] == "depression_id" and "of the table of hollows" in step["text"] and "innermost" not in step["text"]:
                    wrong("speaks of the hollow a cell drains into without saying that it is the innermost one", step["text"])
                elsewhere = re.match(r"At ([\d.]+)° ([NS]), ([\d.]+)° ([EW]) \(cell (\d+)\), where the cause lies: ", step["text"])
                if elsewhere and (int(elsewhere.group(5)) != step["cell"] or not is_place(elsewhere.groups()[:4], lat[step["cell"]], lon[step["cell"]])):
                    wrong("gives another place than that of the cell the step is about", step["text"])
                if step["cell"] != cell and not elsewhere:
                    wrong("speaks of another cell without saying where it lies", step["text"])
                for named in re.finditer(r"cell (\d+), at ([\d.]+)° ([NS]), ([\d.]+)° ([EW])", step["text"]):
                    k = int(named.group(1))
                    if not (0 <= k < n) or not is_place(named.groups()[1:], lat[k], lon[k]):
                        wrong(f"gives another place for cell {k} than the mesh has", step["text"])
                for said in re.finditer(r"([\d.]+)° (north|south)\b", step["text"]):
                    here = lat[step["cell"]]
                    if abs(float(said.group(1)) - abs(here)) > 0.051 or (said.group(2) != ("north" if here >= 0 else "south") and abs(here) > 0.05):
                        wrong("gives another latitude than that of the cell the step is about", step["text"])
            value = year(field)[cell] if f[field].dtype.kind == "f" else None
            wet, full, part = bool(sea[cell]), share[cell] >= 1.0, 0.0 < share[cell] < 1.0
            if field in ("runoff", "precipitation") and first.startswith(("Runoff here averages", "Precipitation here averages")) and ":" in first:
                # the parts of a sum add up to the value given: a part of any size left out, or printed in another unit, shows
                parts = [number(x) for x in re.findall(rf"({NUMBER}) mm/month", re.sub(r"\([^)]*\)", "", first.split(":", 1)[1]))]
                if not parts or abs(sum(parts) - value) > 0.012 * sum(abs(x) for x in parts) + 0.02:
                    wrong(f"gives parts that add up to {sum(parts):.4g} mm/month, where the field holds {value:.4g}")
            if field == "runoff":
                must("This cell is sea", wet)
                must("wholly under a lake", not wet and full)
                must("No water runs off", not wet and not full and value == 0)
                must("Runoff here averages", not wet and not full and value > 0)
            elif field == "river_discharge":
                must("This cell is sea", wet)
                must("no river ends in it", wet and value == 0)
                must("This cell lies in a lake that overflows", in_lake[cell])
                must("at the brim of a lake that overflows", brim[cell])
                must_not("This cell lies in a lake that overflows", share[cell] == 0)
                must("partly under a closed lake", closed[cell])
                must("wholly under a closed lake", drowned[cell])
                if (in_lake[cell] or closed[cell] or drowned[cell]) != (share[cell] > 0) or (drowned[cell] and not full):
                    wrong("names a place that the lake's share of the cell contradicts")
                dry = not wet and not (in_lake[cell] or brim[cell] or closed[cell] or drowned[cell])
                must("No river runs through this cell", dry and value == 0)
                must("The river here carries", dry and value > 0)
                must_not("the cell's own runoff gives", runoff[cell] == 0)
                # in a cell of a closed lake the water said to arrive is the river of the cells that drain into it, counted once
                arrives = re.search(rf"(?:: |; )({NUMBER}) m³/s arrive from upstream", first)
                if closed[cell] and arrives and not close(number(arrives.group(1)), brought[cell]):
                    wrong(f"says that {arrives.group(1)} m³/s arrive from upstream, where the cells that drain into this one carry {brought[cell]:.4g}")
                if closed[cell] and ":" in first:                 # ... and with the cell's own runoff and what the lake takes it adds up to the river
                    parts = [number(x) for x in re.findall(rf"({NUMBER}) m³/s", re.sub(r"\([^)]*\)", "", first.split(":", 1)[1]))]
                    if not parts or abs(sum(parts) - value) > 0.012 * sum(abs(x) for x in parts) + 0.02:
                        wrong(f"gives parts that add up to {sum(parts):.4g} m³/s, where the field holds {value:.4g}")
                if drowned[cell]:
                    said = read(rf"bring the lake ({NUMBER}) m³/s here on the year's average", "water that the rivers bring the lake here")
                    if said and not close(said[0], brought[cell]):
                        wrong(f"says that the rivers bring the lake {said[0]:g} m³/s here, where the cells that drain into this one carry {brought[cell]:.4g}")
                named = re.search(r"where the largest single source is cell (\d+),", first)
                if "arrive from upstream" in first:
                    if not named or int(named.group(1)) == cell:
                        wrong("names the cell itself, or no cell, as the largest source upstream")
                    else:
                        source = int(named.group(1))
                        told = [step for step in chain[1:] if step["cell"] == source and step["field"] == "runoff"]
                        if not told and len(chain) < 16 and float(view.driver(field, "from_upstream")[:, cell].mean()) >= 0.1 * value:
                            wrong("does not go on to the cell it names as the largest source upstream")
                        if runoff[source] == 0 and not (share[source] >= 1.0 and all("would shed if it were dry" in step["text"] for step in told)):
                            wrong("names as the largest source upstream a cell that sheds nothing, without saying how it counts")
            elif field == "evapotranspiration":
                must("This cell is sea", wet)
                must("No water goes back", not wet and value == 0)
                must("returns", not wet and value > 0)
                must_not("open water of a lake", share[cell] == 0)
                must_not("the soil gives", not wet and full)
            elif field == "potential_evapotranspiration":
                some = not wet and cover[:, cell].max() > 0.0 and cover[:, cell].min() < 1.0
                must("This cell is sea", wet)
                must("snow covers it through every month", not wet and cover[:, cell].min() >= 1.0)
                must("no snow covers it in any month", not wet and cover[:, cell].max() == 0.0)
                must("some of the ground for some or all of the year", some)
                must_not("for part of the year", some)
                must_not(" 100 % of the ground is bare", some)
                must_not(", 0 % of the ground is bare", some)
                must_not("could take 0.00", not wet and "gains" in first and cover[:, cell].max() == 0.0
                         and float(np.asarray(view.driver(field, "net_radiation"))[:, cell].min()) > 5.0)
            elif field in ("snow_water", "snow_cover"):
                must("This cell is sea", wet)
                must(["No snow lies"], not wet and snow[:, cell].max() == 0.0)
                must("lies all year", field == "snow_water" and not wet and bool(ice[cell]))
                must_not("all melt", field == "snow_water" and not wet and bool(ice[cell]))
                if field == "snow_water" and not wet and snow[:, cell].max() > 0.0:
                    held = read(rf"holds ({NUMBER}) mm of water on the year's average", "depth of water in mm")
                    if held and not close(held[0], snow[:, cell].mean()):
                        wrong(f"gives {held[0]:g} mm of water, where the field holds {snow[:, cell].mean():.4g} on the year's average")
                if field == "snow_water" and not wet and bool(ice[cell]):
                    said = read(rf"Of the ({NUMBER}) mm/month that fall on the year's average, ({NUMBER}) mm/month melt and ({NUMBER}) mm/month leave as ice",
                                "snow that falls, melts and leaves as ice")
                    stored = [float(np.asarray(view.driver("snow_water", term))[:, cell].mean()) for term in ("fell", "melted", "left_as_ice")]
                    if said and not all(close(a, b) for a, b in zip(said, stored)):
                        wrong(f"gives {said} mm/month for the snow that falls, melts and leaves as ice, where the model's books hold "
                              f"{[round(x, 4) for x in stored]}")
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
                must("No lake reaches it", share[cell] == 0 and not brim[cell])
                must_not("No lake reaches it", brim[cell])
                must("stands exactly at the height of this cell", brim[cell])
                must(["It is a lake with an outlet", "It is a closed lake", "It is a lake in a hollow with no way out"], share[cell] > 0)
                must("km²", share[cell] > 0 or brim[cell])
                if share[cell] > 0 or brim[cell]:                # the lake's own hollow and its own level, not another hollow's
                    row = int(lake_of[cell])
                    must(f"the lake fills hollow {int(lakes['hollow'][row])} of the table of hollows", row >= 0)
                    must(f"(row {row} of the table of lakes)", row >= 0)
                    if row < 0:
                        wrong("speaks of a lake and names no row of the table of lakes")
                    else:                                    # the lake's books, each in its own unit and its own place in the sentence
                        said = read(rf"each year ({NUMBER}) km³ of water run toward this lake, counted as if its ground were dry; flooding its "
                                    rf"({NUMBER}) km² lets the air take ({NUMBER}) km³ more than the same ground would give dry, and ({NUMBER}) km³ "
                                    rf"leave over the pass; its open water gives the air ({NUMBER}) km³ a year, and ({NUMBER}) km³ fall on it",
                                    "books of the lake")
                        stored = [float(lakes[name][row]) / scale for name, scale in (
                            ("inflow_m3_per_year", 1e9), ("area_m2", 1e6), ("loss_to_air_m3_per_year", 1e9), ("outflow_m3_per_year", 1e9),
                            ("evaporation_m3_per_year", 1e9), ("rain_on_lake_m3_per_year", 1e9))]
                        if said and not all(abs(a - b) < 0.51 if k == 1 else close(a, b, volume=True) for k, (a, b) in enumerate(zip(said, stored))):
                            wrong(f"gives {said} for the lake's inflow, area, extra loss, outflow, evaporation and rain (km³, km²), where its row holds "
                                  f"{[round(x, 3) for x in stored]}")
                        level = read(rf"and stands at ({NUMBER}) m \(row", "level of the lake")
                        if level and not close(level[0], float(lakes["level_m"][row])):
                            wrong(f"gives {level[0]:g} m for the lake's level, where its row holds {float(lakes['level_m'][row]):.4g}")
            elif field == "lake_level":
                must("No lake covers any of this cell", share[cell] == 0)
                must("The surface of the lake here stands at", share[cell] > 0)
            elif field == "ocean_mask" and main_sea is not None:
                low = float(f["elevation"][cell]) <= sea_level
                must("it was flooded from the main sea", bool(main_sea[cell]))
                must("it lies in a separate body of water", wet and not main_sea[cell])
                must("the ground stands above sea level", not wet and not low)
                must(["it is low ground that a barrier keeps dry", "it is low ground in a hollow that the sea spilled into"], not wet and low)
                must("Under water here: true", wet)
                must("Under water here: false", not wet)
            elif field == "subsidence":
                must_not("the northern loop", lat[cell] < -0.05)
                must_not("the southern loop", lat[cell] > 0.05)
                must(["under no branch", "the rising branch", "the sinking branch of the northern loop", "the sinking branch of the southern loop"])
            elif field == "biome":
                name = biome_names[int(f["biome"][cell])]
                must(f"The biome here is {name.replace('_', ' ')}")
                must("the cell is sea", wet and name != "ice")
                must("ice lies on the sea here", wet and name == "ice")
                for words in ("what limits plant life here is cold", "what limits plant life here is drought", "neither cold nor drought limits plant life here"):
                    wanted_words = limits.get(name, "neither cold nor drought limits plant life here")
                    must(words, not wet and words == wanted_words)
                    must_not(words, wet or words != wanted_words)
            elif field == "surface_temperature":
                said = read(rf"The temperature here averages ({NUMBER}) °C over the year", "temperature in °C")
                if said and abs(said[0] - (value - 273.15)) > 0.051:
                    wrong(f"gives {said[0]:g} °C, where the field holds {value - 273.15:.3f} °C on the year's average")
                for change in re.finditer(r"changes it by (\S+) °C", first):
                    if not re.fullmatch(r"[+-]\d+\.\d", change.group(1)):
                        wrong(f"gives a change of temperature without its sign, or not as a change: {change.group(1)!r}")
                cooled = re.search(rf"its height changes it by ({NUMBER}|\+{NUMBER}) °C", first)
                if cooled and "height_above_sea" in f:
                    height = max(float(f["height_above_sea"][cell]), 0.0)
                    if number(cooled.group(1)) > 0.05 or abs(number(cooled.group(1))) > 0.012 * height + 0.2:
                        wrong(f"gives {cooled.group(1)} °C for the cooling by a height of {height:.0f} m, which no lapse of temperature with height gives")
            elif field == "flow_receiver":
                to = int(f["flow_receiver"][cell])
                must(f"runs to cell {to} ")
                must("The cell is sea", wet)
                must("the bottom of a closed hollow", not wet and to < 0)
                if surface is not None and not wet and to >= 0:
                    around = nbr[cell][nbr[cell] >= 0]
                    lower, level = surface[to] < surface[cell], surface[to] == surface[cell]
                    must("That is its lowest neighbour", lower)
                    must("The ground is level here", level)
                    must_not("That is its lowest neighbour", not lower)
                    if to not in around or surface[to] > surface[cell]:
                        wrong("names as receiver a cell that is no neighbour, or one that stands higher")
                    elif lower and surface[to] != surface[around].min():
                        wrong("calls its lowest neighbour a cell that is not the lowest of its neighbours")
    return problems


def report(world, every=1, say=print) -> int:
    """Scan a world (the path of its store, or a view of it) and say what was found. Returns the number of problems."""
    v = world if isinstance(world, store.WorldView) else store.StoreView(world)
    n = v.attrs["meta"]["cells"]
    found = scan(v, range(0, n, every))
    kinds = {}
    for cell, field, what, text in found:
        kinds.setdefault((field, what), []).append((cell, text))
    for (field, what), cases in sorted(kinds.items()):
        say(f"{field}: {what}: {len(cases)} answers, the first at cell {cases[0][0]}:\n    {cases[0][1]}")
    asked = len(range(0, n, every)) * len([f for f in FIELDS if f in v.field_names()])
    say(f"{asked} answers read; {len(found)} problems" if found else f"{asked} answers read; none says anything its numbers contradict")
    return len(found)


def parser():
    p = console.tool_parser(__doc__, "python tools/why_scan.py")
    p.add_argument("store", metavar="STORE")
    p.add_argument("--every", type=console.whole_number(1), default=1, metavar="N")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not Path(args.store).exists():
        print(f"no world store at {args.store}", file=sys.stderr)
        return 2
    return 1 if report(args.store, args.every) else 0


if __name__ == "__main__":
    sys.exit(main())
