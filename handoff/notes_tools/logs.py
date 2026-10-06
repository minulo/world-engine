"""The reports of the Earth tools, read back into numbers: nothing in the notes about Earth's rivers is typed by hand
that one of these functions can read out of a log. Every function takes the text of a log of tools/earth_rivers.py
(or earth_relief.py, earth_demand.py) and fails loudly if the line it wants is not there."""
import re

NUM = r"-?[\d,]+(?:\.\d+)?(?:e[+-]?\d+)?"
f = lambda s: float(s.replace(",", ""))


def need(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    assert m, f"not found: {pattern}\n in: {text[:300]}"
    return m


def part(text, start, end=None):
    """The text of one part of a report: from the line that begins with `start` to the line that begins with `end`."""
    i = text.index("\n" + start) + 1 if not text.startswith(start) else 0
    j = len(text) if end is None else text.index("\n" + end, i)
    return text[i:j]


def header(text):
    m = need(rf"sea water poured: ({NUM}) m3, (what the ocean of the relief data holds|the planet file's); the sea of the mesh comes to rest at "
             rf"([+-]?[\d.]+) m and covers ([\d.]+) % of the planet; (\d+) land cells", text)
    share = need(r"valley floors at the lowest ([\d.]+) of each cell's land points", text)
    return {"volume": f(m[1]), "water": "relief" if m[2].startswith("what") else "planet", "sea_level": float(m[3]), "sea_share": float(m[4]),
            "land_cells": int(m[5]), "valley_share": float(share[1])}


def gauges(text):
    """Part 1: {river: dict}, and the count within a factor of two."""
    rows = {}
    for line in part(text, "1. Great rivers", "2. Like for like").splitlines():
        m = re.match(rf"^(\S.*?)\s+({NUM})\s+({NUM})\s+(yes|NO)\s+\|\s+({NUM})\s+({NUM})\s+({NUM})\s+\|\s*({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+\|\s+({NUM})", line)
        if m:
            rows[m[1].strip()] = {"measured": f(m[2]), "flow": f(m[3]), "within": m[4] == "yes", "real": f(m[5]), "reaches": f(m[6]), "full": f(m[7]),
                                  "measured_depth": f(m[8]), "sheds": f(m[9]), "rain": f(m[10]), "demand": f(m[11]), "lost": f(m[12]),
                                  "no_river": "no river within 150 km" in line}
    assert len(rows) == 21, len(rows)
    m = need(r"within a factor of two of the measured flow: (\d+) of 21", text)
    b = need(r"= the flow, to within ([\d.e+-]+) km3 a year", text)
    c = need(r"and at every cell of the mesh, to within ([\d.e+-]+) of the larger", text)
    return rows, int(m[1]), float(b[1]), float(c[1])


def like(text):
    """Part 2: {river: dict}, and the summary lines."""
    rows = {}
    for line in part(text, "2. Like for like", "3. Where each great river").splitlines():
        m = re.match(rf"^(\S.*?)\s+({NUM})\s+({NUM})\s+(yes|no)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s*$", line)
        if m:
            rows[m[1].strip()] = {"real": f(m[2]), "mesh": f(m[3]), "alike": m[4] == "yes", "measured_depth": f(m[5]), "sheds": f(m[6]), "ratio": f(m[7]),
                                  "rain": f(m[8]), "demand": f(m[9]), "measured_over_rain": f(m[10]), "snow_share": f(m[11])}
    assert len(rows) == 21, len(rows)
    a = need(r"basins alike: (\d+) of 21\. All of them together, the engine sheds ([\d.]+) of the measured depth; basin by basin ([\d.]+) to ([\d.]+), "
             r"(\d+) below 1 and (\d+) above; within a factor of two: (\d+)", text)
    b = need(r"the (\w[\w ]*?) carries (\d+) % of the weight\. Without the \w[\w ]*?: ([\d.]+)\. The median of the basins' own ratios: ([\d.]+)", text)
    c = re.search(r"more than what Hydrology does with rain: (.*?)\. Without them: ([\d.]+)", text)
    d = need(r"have lost theirs: ([\d.]+)\)", text)
    return rows, {"alike": int(a[1]), "all": float(a[2]), "lowest": float(a[3]), "highest": float(a[4]), "below": int(a[5]), "above": int(a[6]),
                  "within_two": int(a[7]), "heavy": b[1], "heavy_weight": int(b[2]), "without_heavy": float(b[3]), "median": float(b[4]),
                  "short": c[1] if c else "", "without_short": float(c[2]) if c else None, "after_lakes": float(d[1])}


def volga(text):
    out = {}
    head = need(r"The Volga at Volgograd.*?basin (\d+) real, (\d+) on the mesh \((alike|not alike)\)", text)
    out["real"], out["mesh"], out["alike"] = int(head[1]), int(head[2]), head[3] == "alike"
    pub = need(r"published for the basin: precipitation (\d+) mm a year, (\d+) % of it snow \((\d+) mm\); (\d+) % of the runoff in the spring flood; and three "
               r"figures for the runoff that do not agree: 262 km3 of runoff, (\d+) mm; a runoff coefficient of 0.38, (\d+) mm; a water content of 250 km3, (\d+) mm", text)
    out["published"] = {"rain": int(pub[1]), "snow_percent": int(pub[2]), "snow": int(pub[3]), "spring": int(pub[4]), "by_volume": int(pub[5]),
                        "by_coefficient": int(pub[6]), "by_content": int(pub[7])}
    for key, words in (("data", "under the rain data"), ("scaled", "the rain data scaled to the published total"),
                       ("published_snow", "the published total with the published share of snow"),
                       ("data_published_snow", "the rain data's total with the published share of snow")):
        m = need(rf"^\s+{re.escape(words)}\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) \(month\s+(\d+)\)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", text, re.M)
        out[key] = {"rain": int(m[1]), "snow": int(m[2]), "sheds": int(m[3]), "most": int(m[4]), "month": int(m[5]),
                    "over_volume": float(m[6]), "over_coefficient": float(m[7]), "over_content": float(m[8])}
    return out


def mouths(text):
    rows = {}
    for line in part(text, "3. Where each great river", "4. The largest lakes").splitlines():
        m = re.match(rf"^(\S.*?)\s+(\d+) km from its mouth, at\s+({NUM}),\s+({NUM})", line)
        if m:
            rows[m[1].strip()] = {"km": int(m[2]), "lat": float(m[3]), "lon": float(m[4])}
    assert len(rows) == 24
    return rows, int(need(r"within 300 km: (\d+) of 24", text)[1])


def lakes(text):
    rows = []
    for line in part(text, "4. The largest lakes", "5. The water of all the land").splitlines():
        m = re.match(rf"^\s+({NUM})\s+({NUM})\s+(yes|no)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM}),\s+({NUM})\s*$", line)
        if m:
            rows.append({"area": f(m[1]), "level": f(m[2]), "outlet": m[3] == "yes", "reaches": f(m[4]), "extra_loss": f(m[5]), "runs_on": f(m[6]),
                         "rain": f(m[7]), "evaporates": f(m[8]), "lat": f(m[9]), "lon": f(m[10])})
    big = need(r"lakes larger than 100,000 km2: (\d+), with (\d+) % of all the land under lakes", text)
    return rows, int(big[1]), int(big[2])


def caspian(text):
    a = need(r"The lake at the Caspian's place: ([\d.]+) million km2 at (-?\d+) m; (it keeps its water|it overflows by ([\d.]+) km3 a year)", text)
    b = need(r"rivers and shores bring it (\d+) km3 a year; each square metre of it gives the air (\d+) mm a year and gets (\d+) mm of rain", text)
    c = need(r"the land whose water reaches it: ([\d.]+) million km2 with the ground under the lake, ([\d.]+) without; over that land the water brought is "
             r"(\d+) mm a year; it (holds|does not hold) the Don at Voronezh", text)
    d = re.search(rf"the water that runs over crosses (\d+) land cells and ends in (the sea|a (closed lake|lake with no way out|dry hollow)(?: of ({NUM}) km2)?), at ({NUM}), ({NUM})", text)
    return {"area": float(a[1]), "level": int(a[2]), "overflows": a[4] is not None, "overflow": float(a[4]) if a[4] else 0.0, "brought": int(b[1]),
            "loses": int(b[2]), "rain": int(b[3]), "catchment": float(c[1]), "outside": float(c[2]), "depth": int(c[3]), "voronezh": c[4] == "holds",
            "ends": None if not d else ("sea" if d[2] == "the sea" else d[3]), "ends_area": f(d[4]) if d and d[4] else None,
            "ends_at": (f(d[5]), f(d[6])) if d else None, "cells": int(d[1]) if d else None}


def land_water(text):
    a = need(r"rain on land ([\d.]+); back to the air ([\d.]+) \(([\d.]+) of the rain\); rivers reaching the sea ([\d.]+)", text)
    b = need(r"shed by the land as if none of it were flooded ([\d.]+) \(([\d.]+) of the rain back to the air\); lakes with an outlet lose ([\d.]+) more than "
             r"the ground they cover; closed lakes keep ([\d.]+)", text)
    c = need(r"land whose water reaches the sea as the water runs: ([\d.]+) %; land that drains into a closed hollow \(depression_id above 0\): ([\d.]+) %; "
             r"land under water if every hollow were full: ([\d.]+) %, and another ([\d.]+) % exactly level with that water", text)
    d = need(r"the air's demand for water over land (\d+) mm a year; rain (\d+) mm; back to the air (\d+) mm; lakes cover ([\d.]+) % of the land: (\d+) lakes, "
             r"(\d+) with an outlet", text)
    return {"rain": float(a[1]), "to_air": float(a[2]), "back": float(a[3]), "to_sea": float(a[4]), "shed": float(b[1]), "back_dry": float(b[2]),
            "outlet_lose": float(b[3]), "closed_keep": float(b[4]), "reaches_sea": float(c[1]), "closed_hollow": float(c[2]), "under_if_full": float(c[3]),
            "level_with": float(c[4]), "demand_mm": int(d[1]), "rain_mm": int(d[2]), "to_air_mm": int(d[3]), "lakes_share": float(d[4]),
            "lakes": int(d[5]), "lakes_outlet": int(d[6])}


def narrows(text):
    rows = {}
    block = part(text, "6. Narrows", "7. What the ties decide") if "\n7. What the ties decide" in text else part(text, "6. Narrows", "8. The land's water") \
        if "\n8. The land's water" in text else part(text, "6. Narrows")
    for m in re.finditer(r"^(\S.*?)\s+the valley rises to (\d+) m, at (-?[\d.]+), (-?[\d.]+); (no lake stands above it|the lake above it stands at (-?\d+) m and "
                         r"(keeps its water|overflows, and the valley stands no higher than its water|overflows by another way))", block, re.M):
        rows[m[1].strip()] = {"barrier": int(m[2]), "at": (float(m[3]), float(m[4])), "lake": None if m[6] is None else int(m[6]), "fate": m[7]}
    for m in re.finditer(r"^(\S.*?)\s+the valley.*\n\s+its water leaves the land at (-?[\d.]+), (-?[\d.]+); the highest cell on its way, by mean height: "
                         r"(-?\d+) m at (-?[\d.]+), (-?[\d.]+), handed to Drainage at (-?\d+) m", block, re.M):
        rows[m[1].strip()].update(leaves=(float(m[2]), float(m[3])), over_mean=int(m[4]), over_at=(float(m[5]), float(m[6])), handed=int(m[7]))
    assert len(rows) == 6, rows.keys()
    return rows


def ties(text):
    """Part 7: the counts over the random settlements."""
    block = part(text, "7. What the ties decide", "8. The land's water") if "\n8. The land's water" in text else part(text, "7. What the ties decide")
    n = int(need(r"and (\d+) settlements at random", block)[1])
    head = need(r"River mouths within 300 km, of 24: engine (\d+); mean heights (\d+); at random (\d+) to (\d+)", block)
    out = {"n": n, "mouths_engine": int(head[1]), "mouths_mean": int(head[2]), "mouths_random": (int(head[3]), int(head[4])), "mouths": {}, "gauges": {}}
    mouth_part = block[block.index("River mouths within"):block.index("Gauges within a factor of two")]
    for m in re.finditer(rf"^(\S.*?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) of {n}", mouth_part, re.M):
        out["mouths"][m[1].strip()] = {"engine": int(m[2]), "mean": int(m[3]), "low": int(m[4]), "high": int(m[5]), "passes": int(m[6])}
    assert len(out["mouths"]) == 24
    m = need(rf"in all {n}: (\d+) rivers; in none: (\d+); in some: (\d+)", mouth_part)
    out["mouths_all_none_some"] = (int(m[1]), int(m[2]), int(m[3]))
    head = need(r"Gauges within a factor of two, of 21: engine (\d+); mean heights (\d+); at random (\d+) to (\d+)", block)
    out.update(gauges_engine=int(head[1]), gauges_mean=int(head[2]), gauges_random=(int(head[3]), int(head[4])))
    gauge_part = block[block.index("Gauges within a factor of two"):block.index("Like for like, all like basins together")]
    for m in re.finditer(rf"^(\S.*?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+) of {n}.*?\|\s+(\d+) of {n}(?:\s+([\d.]+)\s+([\d.]+))?", gauge_part, re.M):
        out["gauges"][m[1].strip()] = {"measured": int(m[2]), "engine": int(m[3]), "mean": int(m[4]), "low": int(m[5]), "high": int(m[6]), "passes": int(m[7]),
                                       "alike": int(m[8]), "ratio_low": float(m[9]) if m[9] else None, "ratio_high": float(m[10]) if m[10] else None}
    assert len(out["gauges"]) == 21, len(out["gauges"])
    m = need(rf"in all {n}: (\d+) rivers; in none: (\d+); in some: (\d+)", gauge_part)
    out["gauges_all_none_some"] = (int(m[1]), int(m[2]), int(m[3]))
    m = need(r"Like for like, all like basins together, the engine sheds of the measured depth: engine ([\d.]+); mean heights ([\d.]+); at random ([\d.]+) to ([\d.]+)", block)
    out["like"] = (float(m[1]), float(m[2]), float(m[3]), float(m[4]))
    for key, words in (("back", "Of the rain on land, back to the air"), ("to_sea", "Rivers reaching the sea, thousand km3 a year"), ("lakes", "Land under lakes, %")):
        m = need(rf"{re.escape(words)}: engine ([\d.]+); mean heights ([\d.]+); at random ([\d.]+) to ([\d.]+)", block)
        out[key] = (float(m[1]), float(m[2]), float(m[3]), float(m[4]))
    m = need(r"The Volga at Volgograd, like for like: engine: basin (\d+), rain (\d+) mm, sheds (\d+); at random: alike in (\d+) of \d+, basin (\d+) to (\d+), "
             r"rain (\d+) to (\d+), sheds (\d+) to (\d+), back to the air (\d+) to (\d+)", block)
    out["volga"] = {"basin": int(m[1]), "rain": int(m[2]), "sheds": int(m[3]), "alike": int(m[4]), "basin_span": (int(m[5]), int(m[6])),
                    "rain_span": (int(m[7]), int(m[8])), "sheds_span": (int(m[9]), int(m[10])), "back_span": (int(m[11]), int(m[12]))}
    m = need(rf"The lake at the Caspian's place: engine: (.*?); mean heights: (.*?); at random: closed in (\d+) of {n}(?:, overflow up to ([\d.]+) km3 a year)?"
             rf"(?:, ([\d.]+) to ([\d.]+) million km2 at (-?\d+) to (-?\d+) m)?; of the (\d+) that overflow, the water reaches the sea in (\d+)", block)
    eng = re.match(r"(overflows by ([\d.]+) km3 a year|closed), ([\d.]+) million km2 at (-?\d+) m", m[1])
    out["caspian"] = {"engine_overflows": eng[2] is not None, "engine_overflow": float(eng[2]) if eng[2] else 0.0, "engine_area": float(eng[3]), "engine_level": int(eng[4]),
                      "mean": m[2], "closed": int(m[3]), "overflow_up_to": float(m[4]) if m[4] else None, "area": (float(m[5]), float(m[6])),
                      "level": (int(m[7]), int(m[8])), "overflowing": int(m[9]), "to_sea": int(m[10])}
    return out


def demands(text):
    rows = {}
    for m in re.finditer(r"^\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+(\d+) of 21", part(text, "8. The land's water"), re.M):
        rows[float(m[1])] = {"like": float(m[2]), "median": float(m[3]), "without_amazon": float(m[4]), "lowest": float(m[5]), "highest": float(m[6]),
                             "within_15": int(m[7]), "back": float(m[8]), "mm": int(m[9]), "to_sea": float(m[10]), "gauges": int(m[11])}
    assert len(rows) == 4, rows
    return rows


def relief(text):
    out = {}
    m = need(r"the ocean of the data holds ([\d.e+]+) m3 of water below 0 m; the planet file has ([\d.e+]+) m3, ([\d.]+) % less\. Poured here: (the first|the second); "
             r"the sea of the mesh comes to rest at ([+-][\d.]+) m and covers ([\d.]+) % of the planet, with (\d+) land cells", text)
    out.update(own=float(m[1]), planet=float(m[2]), less=float(m[3]), sea_level=float(m[5]), sea_share=float(m[6]), land_cells=int(m[7]))
    m = need(r"of its land \(by area\), (\d+) % lies within half a metre of a whole number of hundreds of feet", text)
    out["hundred_feet"] = int(m[1])
    m = need(r"of (\d+) land cells (\d+) \(([\d.]+) %\) have a land neighbour at exactly their own height; the commonest heights handed to Drainage: (.*)", text)
    out.update(tied=int(m[2]), tied_percent=float(m[3]), commonest=[(int(a), int(b)) for a, b in re.findall(r"(-?\d+) m \((\d+) cells\)", m[4])])
    m = need(r"of (\d+) land cells with a lower neighbour, (\d+) \(([\d.]+) %\) have several equally low: the lower bed settles (\d+), the wider way (\d+), the cell numbers (\d+); "
             r"another (\d+) land cells \(([\d.]+) %\) lie on level ground", text)
    out.update(choose=int(m[1]), several=int(m[2]), several_percent=float(m[3]), by_bed=int(m[4]), by_width=int(m[5]), by_number=int(m[6]), level=int(m[7]), level_percent=float(m[8]))
    m = need(r"the water of ([\d.]+) % of the land's area reaches the sea in another cell when the order of the cells is turned round, and of ([\d.]+) % when", text)
    out.update(moved_by_numbers=float(m[1]), moved_by_width=float(m[2]))
    m = need(r"the data: the ocean .* covers ([\d.]+) % of the planet\. Of all that is not ocean, ([\d.]+) % lies under water when every hollow of the data is full "
             r"\(([\d.]+) % between 60 south and 60 north\); of the land above 0 m alone, ([\d.]+) % \(([\d.]+) %\)", text)
    out.update(data_ocean=float(m[1]), data_under=float(m[2]), data_under_60=float(m[3]), data_land_under=float(m[4]))
    m = need(r"the mesh: ([\d.]+) % of the planet is not sea\. Of it, ([\d.]+) % lies under water when every hollow is full \(([\d.]+) % between 60 south and 60 north\); "
             r"([\d.]+) % drains into a closed hollow", text)
    out.update(mesh_not_sea=float(m[1]), mesh_under=float(m[2]), mesh_under_60=float(m[3]), mesh_closed=float(m[4]))
    rows = {}
    for line in part(text, "3. Narrows of six great rivers", "4. Seas behind straits").splitlines():
        m = re.match(r"^(\S.*?)\s+(-?\d+) m\s+(?:open to the sea|(\d+) m\s+(\d+) m)\s+\|\s+(\d+) m(?:\s+(\d+) m)?", line)
        if m:
            rows[m[1].strip()] = {"river_at": int(m[2]), "data_barrier": None if m[3] is None else int(m[3]), "data_joined": None if m[4] is None else int(m[4]),
                                  "mesh_barrier": int(m[5]), "mesh_lake": None if m[6] is None else int(m[6])}
    assert len(rows) == 6
    out["narrows"] = rows
    m = need(r"closed in the data themselves: (\d+) of 6 \((.*?)\)", text)
    out["closed_in_data"] = (int(m[1]), m[2])
    out["big_lakes"] = [(f(a), int(b), float(c), float(d), "a closed hollow of the data" in rest) for a, b, c, d, rest in
                        re.findall(rf"^\s+({NUM}) km2 at\s+(-?\d+) m, lowest point\s+({NUM}),\s+({NUM}): (.*)$", text, re.M)]
    m = need(r"of these (\d+) lakes, (\d+) lie in hollows that the data hold on their own grid", text)
    out["big"] = (int(m[1]), int(m[2]))
    return out


def demand_report(text):
    out = {}
    for key, words in (("reaches", "sunlight that reaches the ground"), ("absorbed", "sunlight that the ground absorbs"), ("lost", "heat that the ground radiates away"),
                       ("left", "left to warm the air and evaporate"), ("evaporation", "of that, evaporation takes")):
        m = need(rf"^{re.escape(words)}\s+([\d.]+)\s+([\d.]+)(?:\s+the engine has ([\d.]+) of the budget's)?", text, re.M)
        out[key] = (float(m[1]), float(m[2]), float(m[3]) if m[3] else None)
    m = need(r"the excess of ([\d.]+) W/m2 taken apart: ([\d.]+) from the sunlight that reaches the ground; ([\d.]+) from the ground reflecting ([\d.]+) of it where the "
             r"budget has ([\d.]+); ([\d.]+) from the heat", text)
    out["excess"] = {"all": float(m[1]), "sunlight": float(m[2]), "reflection": float(m[3]), "reflects": float(m[4]), "budget_reflects": float(m[5]), "heat": float(m[6])}
    m = need(r"return the budget's sunlight at the ground: ([\d.]+); the budget's loss of heat: ([\d.]+)", text)
    out["wants"] = (float(m[1]), float(m[2]))
    out["shares"] = [(float(a), float(b), float(c), float(d)) for a, b, c, d in re.findall(r"^\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s+as built)?\s*$",
                                                                                         part(text, "the share of sunshine enters both formulas", "(the budget is"), re.M)]
    assert len(out["shares"]) == 3, out["shares"]
    m = need(r"the field potential_evapotranspiration: (\d+);", text)
    out["field"] = int(m[1])
    m = need(r"^all land\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)", text, re.M)
    out["all_land"] = {"engine": int(m[1]), "paper": int(m[2]), "dew": int(m[3]), "net": int(m[4]), "ratio": float(m[5])}
    m = need(r"in ([\d.]+) % of the land's cells and months the engine's demand is nothing", text)
    out["none_where_some"] = float(m[1])
    return out


def trace_summary(text):
    m = need(r"(\d+) land cells: (\d+) steps down to lower ground, (\d+) over level ground, (\d+) across full hollows; nearest to its real mouth: (\d+) km; "
             r"leaves the land (\d+) km from it", text)
    return {"cells": int(m[1]), "down": int(m[2]), "level": int(m[3]), "lake": int(m[4]), "nearest": int(m[5]), "leaves": int(m[6])}


if __name__ == "__main__":
    import sys
    from pathlib import Path
    L = Path(sys.argv[1])
    t = (L / "rivers.log").read_text()
    print(header(t)); g = gauges(t); print(g[1:], g[0]["Amazon"]); l = like(t); print(l[1], l[0]["Ob"]); print(volga(t)); print(mouths(t)[1]); print(lakes(t)[1:])
    print(caspian(t)); print(land_water(t)); print(narrows(t)["Danube"])
    print(relief((L / "relief.log").read_text())["narrows"]); print(demand_report((L / "demand.log").read_text()))
    s = ties((L / "rivers_s20.log").read_text()); print(s["caspian"], s["mouths"]["Nile"], s["gauges"]["Ob"], s["volga"])
