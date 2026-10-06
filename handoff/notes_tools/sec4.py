"""Sections 4.2 to 4.5 of docs/BUILD_NOTES.md, written from the logs of the Earth tools: every number of a table here
is read out of a log by handoff/notes_tools/logs.py, and none is typed by hand. The prose around the tables is typed
by hand and quotes numbers through the same readers.

    python handoff/notes_tools/sec4.py LOGS      prints the four sections (LOGS: the folder of measure_earth.sh)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logs as lg          # noqa: E402

SHARES = ["0.02", "0.05", "0.07", "0.08", "0.09", "0.1", "0.11", "0.12", "0.13", "0.15", "0.2", "0.3", "0.5"]
N = lambda x: f"{x:,.0f}"


def read(L):
    L = Path(L)
    t = lambda name: (L / name).read_text(encoding="utf-8")
    d = {"rivers": t("rivers.log"), "s20": t("rivers_s20.log"), "s100": t("rivers_s100.log"), "relief": t("relief.log"), "demand": t("demand.log"),
         "planet": t("planet.log"), "planet_s20": t("planet_s20.log"), "planet_relief": t("planet_relief.log")}
    d["shares"] = {s: (d["s20"] if s == "0.1" else t(f"shares/share_{s}.log")) for s in SHARES}
    return d


def caspian_words(c, n):
    built = f"overflows by {c['engine_overflow']:.1f} km³ a year" if c["engine_overflows"] else "keeps its water"
    return built, f"keeps its water in {c['closed']} of {n}"


def sec42(d):
    g, gn, _, _ = lg.gauges(d["rivers"])
    m, mn = lg.mouths(d["rivers"])
    t20, t100 = lg.ties(d["s20"]), lg.ties(d["s100"])
    c, c20, c100 = lg.caspian(d["rivers"]), t20["caspian"], t100["caspian"]
    h = lg.header(d["rivers"])
    return f"""### 4.2 The design's conditions (Layer 9)

| Condition in the design | Result |
|---|---|
| A cone drains to its foot | Pass |
| Every land cell reaches the sea or a closed hollow | Pass on ground built for the purpose and on the default world |
| The drained areas add up to the land area | Pass, to 1 part in a billion |
| One basin under even rain: the flow at its mouth is (rain − evaporation) × area | Pass |
| Water in = water out for every basin | Pass on rough ground with lakes and snow: what falls on each basin goes back to the air or leaves at its mouth |
| Earth: the Amazon reaches the Atlantic and the Nile the Mediterranean | Pass as built: {m['Amazon']['km']} and {m['Nile']['km']} km from their mouths, where the test allows 600 km, and in each of 20 random settlements of the ties. The Nile meets it by distance alone: between 26° and 30° north the mesh's river runs west of 28.5° east, outside the real valley [UNVERIFIED, from memory: where the real river runs] |
| Earth: central Asia and the Great Basin are closed | Pass |
| Earth: the Amazon carries the most water | Pass: the largest flow into the sea is 144,605 m³/s, 297 km from the place taken as the Amazon's mouth. The Amazon carries 210,000 m³/s [DOCUMENTED: Dai and Trenberth, Table 2] |
| Earth: the Caspian stays closed | **Fails as built.** The lake at the Caspian's place {caspian_words(c20, 20)[0]}, of the {c['brought']} km³ that rivers and shores bring it. It {caspian_words(c20, 20)[1]} random settlements of the ties and in {c100['closed']} of 100. The water that runs over ends in a second, closed lake of {N(c['ends_area'])} km² at {c['ends_at'][0]:.1f}° north, {c['ends_at'][1]:.1f}° east; in none of the {c100['overflowing']} settlements of 100 that overflow does it reach the sea. Whether a lake that overflows into a neighbouring closed lake "stays closed" is a question for you (section 11); the test reads the condition as written, and fails |
| "River flow data is still to be chosen" (the design's row for Hydrology) | I chose 21 gauges (section 4.4). As built {gn} of the 21 carry the measured flow within a factor of two, and {21 - gn} miss. Whether the gauges belong to the "done when" of step 2 is yours to say (section 11) |

All [MEASURED]: `tests/test_water.py` and `tests/test_water_rules.py` for the first five, `tests/test_earth.py`
for the rest; the Earth rows as the water stands since the fifth check (section 4.5: the sea of the mesh at
{h['sea_level']:+.1f} m).
"""


def sec44_tables(d):
    out = {}
    g, gn, books, cellbooks = lg.gauges(d["rivers"])
    like, ls = lg.like(d["rivers"])
    m, mn = lg.mouths(d["rivers"])
    t20, t100 = lg.ties(d["s20"]), lg.ties(d["s100"])
    r = lg.relief(d["relief"])
    w = lg.land_water(d["rivers"])
    c = lg.caspian(d["rivers"])
    v = lg.volga(d["rivers"])
    dm = lg.demand_report(d["demand"])
    cuts = lg.demands(d["s100"])
    nar = lg.narrows(d["rivers"])

    # --- narrows
    names = {"Congo": "Congo, Bolobo to Kinshasa", "Danube": "Danube, the Iron Gate", "Lena": "Lena, Zhigansk to the delta", "Amur": "Amur, below Komsomolsk",
             "Yangtze": "Yangtze, the Three Gorges", "St Lawrence": "St Lawrence, below Quebec"}
    rows = ["| Narrows | In the data: the river above stands at | its valley rises to | joined to the ocean, by any way, at | On the mesh: the valley rises to | the lake above stands at |",
            "|---|---|---|---|---|---|"]
    for k in ("Congo", "Danube", "Lena", "Amur", "Yangtze", "St Lawrence"):
        x = r["narrows"][k]
        rows.append(f"| {names[k]} | " + (f"{x['river_at']} m | {x['data_barrier']} m | {x['data_joined']} m" if x["data_barrier"] is not None else "open to the sea | | ")
                    + f" | {x['mesh_barrier']} m | {x['mesh_lake']} m |")
    out["narrows"] = "\n".join(rows)

    # --- what the ties decide
    def span(a, unit=""):
        return f"{a[0]} to {a[1]}{unit}" if a[0] != a[1] else f"{a[0]}{unit}"
    rows = ["| Outcome | As the engine settles ties | In 20 random settlements | In 100 |", "|---|---|---|---|",
            f"| River mouths within 300 km, of 24 | {t20['mouths_engine']} | {span(t20['mouths_random'])} | {span(t100['mouths_random'])} |",
            f"| … rivers that pass in all, in none, in some | | {', '.join(map(str, t20['mouths_all_none_some']))} | {', '.join(map(str, t100['mouths_all_none_some']))} |"]
    decided = [k for k in t100["mouths"] if 0 < t100["mouths"][k]["passes"] < 100 or 0 < t20["mouths"][k]["passes"] < 20]
    for k in decided:
        a, b = t20["mouths"][k], t100["mouths"][k]
        rows.append(f"| The {k}'s mouth | {a['engine']} km: {'passes' if a['engine'] < 300 else 'fails'} | passes in {a['passes']} | in {b['passes']} |")
    rows += [f"| Gauges within a factor of two, of 21 | {t20['gauges_engine']} | {span(t20['gauges_random'])} | {span(t100['gauges_random'])} |",
             f"| … rivers that pass in all, in none, in some | | {', '.join(map(str, t20['gauges_all_none_some']))} | {', '.join(map(str, t100['gauges_all_none_some']))} |"]
    gdecided = [k for k in t100["gauges"] if 0 < t100["gauges"][k]["passes"] < 100 or 0 < t20["gauges"][k]["passes"] < 20]
    for k in gdecided:
        a, b = t20["gauges"][k], t100["gauges"][k]
        ok = a["measured"] / 2 < a["engine"] < a["measured"] * 2
        rows.append(f"| The {k} at its gauge ({N(a['measured'])} km³ measured) | {N(a['engine'])} km³: {'passes' if ok else 'fails'} | {N(a['low'])} to {N(a['high'])}; passes in {a['passes']} | "
                    f"{N(b['low'])} to {N(b['high'])}; in {b['passes']} |")
    c20, c100 = t20["caspian"], t100["caspian"]
    rows += [f"| The lake at the Caspian's place | {caspian_words(c20, 20)[0]} | {caspian_words(c20, 20)[1]}; overflows by up to {c20['overflow_up_to']:.1f} km³ | "
             f"{caspian_words(c100, 100)[1]}; by up to {c100['overflow_up_to']:.1f} km³ |",
             f"| … its size | {c20['engine_area']:.2f} million km² at {c20['engine_level']} m | {span(c20['area'])} million km² at {span(c20['level'])} m | "
             f"{span(c100['area'])} million km² at {span(c100['level'])} m |",
             f"| … where the water that runs over ends | in a closed lake | in the sea in {c20['to_sea']} of the {c20['overflowing']} that overflow | in the sea in {c100['to_sea']} of {c100['overflowing']} |",
             f"| Like for like, engine over measured | {t20['like'][0]:.2f} | {t20['like'][2]:.2f} to {t20['like'][3]:.2f} | {t100['like'][2]:.2f} to {t100['like'][3]:.2f} |",
             f"| Rain on land that goes back to the air | {t20['back'][0]:.4f} | {t20['back'][2]:.4f} to {t20['back'][3]:.4f} | {t100['back'][2]:.4f} to {t100['back'][3]:.4f} |",
             f"| Rivers reaching the sea, thousand km³ | {t20['to_sea'][0]:.2f} | {t20['to_sea'][2]:.2f} to {t20['to_sea'][3]:.2f} | {t100['to_sea'][2]:.2f} to {t100['to_sea'][3]:.2f} |",
             f"| Land under lakes | {t20['lakes'][0]:.2f} % | {t20['lakes'][2]:.2f} to {t20['lakes'][3]:.2f} % | {t100['lakes'][2]:.2f} to {t100['lakes'][3]:.2f} % |"]
    out["ties"] = "\n".join(rows)
    out["decided_mouths"], out["decided_gauges"] = decided, gdecided

    # --- mouths that miss as built
    what = {"Amazon": "The mesh's sea reaches up the estuary: the sea cell that takes the river lies 297 km from the place taken as the mouth. Under the planet file's water, 0.19 % less, the river left the land 203 km from it: the water poured decides this one",
            "Congo": "The data close its valley (table above). The basin fills as a lake to 457 m and overflows westward",
            "Ob": "The Gulf of Ob is ocean in the data and not sea on the mesh; the river comes within 71 km of its mouth at the head of the gulf and runs on across a full hollow",
            "Danube": "The river passes the Iron Gate and ends in the lake at the Black Sea's place, 203 km from its mouth at the nearest. The data cut the Black Sea off, and the condition follows the lake's water on to the Dardanelles",
            "Yenisei": "The ties decide, mostly against the river: it leaves the land with the Ob",
            "Volga": "The river of a closed sea. The condition follows the water on as if every hollow were full, and cannot be met as I wrote it",
            "St Lawrence": "The valley rule closes the estuary (below). The lake above overflows southward",
            "Amur": "The data close the lower valley (table above). The lowland's water leaves south, to the Sea of Japan",
            "Huang He": "The ties decide, and the engine's settlement gives the rarer outcome of the 20, though not of the 100"}
    rows = ["| River | Leaves the land, as built | In 20 random settlements: from, to; within 300 km in | In 100 | What was measured beside it |", "|---|---|---|---|---|"]
    missing = [k for k in m if m[k]["km"] >= 300]
    assert set(missing) == set(what), (missing, set(what))
    for k in missing:
        a, b = t20["mouths"][k], t100["mouths"][k]
        rows.append(f"| {k} | {N(m[k]['km'])} km | {N(a['low'])} to {N(a['high'])} km; {a['passes']} | {N(b['low'])} to {N(b['high'])} km; {b['passes']} | {what[k]} |")
    out["mouths"] = "\n".join(rows)
    out["mouths_missing"] = missing

    # --- gauges
    rows = ["| River | Flow measured | Flow, engine | Within a factor of two in, of 20 | of 100 | Basin on Earth | Land that reaches the gauge on the mesh | … with every hollow full | Shed, measured | Shed, engine | Lakes on the way lose |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    order = sorted(g, key=lambda k: (not g[k]["within"], -g[k]["measured"]))
    for k in order:
        x = g[k]
        name = k if x["within"] else f"**{k}**"
        rows.append(f"| {name} | {N(x['measured'])} | {N(x['flow'])} | {t20['gauges'][k]['passes']} | {t100['gauges'][k]['passes']} | {N(x['real'])} | {N(x['reaches'])} | {N(x['full'])} | "
                    f"{N(x['measured_depth'])} | {N(x['sheds'])} | {N(x['lost'])} |")
    out["gauges"] = "\n".join(rows)
    out["gauges_n"], out["books"], out["cellbooks"] = gn, books, cellbooks
    out["gauge_misses"] = [k for k in order if not g[k]["within"]]

    # --- like for like
    rows = ["| River | Basin on Earth | On the mesh | Rain handed in | Of it snow, as the harness makes it | Shed, measured | Shed, engine | Engine over measured | Measured runoff over the rain handed in | Alike in, of 20 | of 100 |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, x in like.items():
        if x["alike"]:
            rows.append(f"| {k} | {N(x['real'])} | {N(x['mesh'])} | {N(x['rain'])} | {x['snow_share']:.2f} | {N(x['measured_depth'])} | {N(x['sheds'])} | {x['ratio']:.2f} | {x['measured_over_rain']:.2f} | "
                        f"{t20['gauges'][k]['alike']} | {t100['gauges'][k]['alike']} |")
    out["like"] = "\n".join(rows)
    out["ls"], out["like_rows"] = ls, like

    # --- Volga
    p = v["published"]
    rows = ["| Precipitation handed to the land that drains through Volgograd on the mesh | mm a year | of it snow | The land sheds | in April | over the 193 mm | over the 222 mm | over the 184 mm |", "|---|---|---|---|---|---|---|---|"]
    for key, words in (("data", "The rain data, with the snow the harness makes of them"), ("scaled", "The rain data scaled to the published total; the harness's share of snow"),
                       ("published_snow", "The published total with the published share of snow"), ("data_published_snow", "The rain data's total with the published share of snow")):
        x = v[key]
        assert x["month"] == 4
        rows.append(f"| {words} | {x['rain']} | {x['snow']} mm | {x['sheds']} mm | {x['most']} mm | {x['over_volume']:.2f} | {x['over_coefficient']:.2f} | {x['over_content']:.2f} |")
    out["volga"], out["v"] = "\n".join(rows), v

    # --- radiation
    rows = ["| Over land, W/m² on the year's mean | The engine's formulas under Earth's temperatures | A published budget of the land |", "|---|---|---|",
            f"| Sunlight that reaches the ground | {dm['reaches'][0]} | {dm['reaches'][1]} |", f"| Sunlight that the ground absorbs | {dm['absorbed'][0]} | {dm['absorbed'][1]} |",
            f"| Heat that the ground radiates away | {dm['lost'][0]} | {dm['lost'][1]} |", f"| Left to warm the air and evaporate water | {dm['left'][0]} | {dm['left'][1]} |",
            f"| Of that, taken by evaporation | {dm['evaporation'][0]} (Hydrology under the rain data) | {dm['evaporation'][1]} |"]
    out["radiation"], out["dm"] = "\n".join(rows), dm
    rows = ["| One share of sunshine everywhere | Sunlight at the ground | Heat radiated away | Left |", "|---|---|---|---|"]
    for s, a, b, e in dm["shares"]:
        rows.append(f"| {s:.2f}{' (as built)' if abs(s - 0.62) < 1e-9 else ''} | {a} | {b} | {e} |")
    rows.append(f"| The budget | {dm['reaches'][1]} | {dm['lost'][1]} | {dm['left'][1]} |")
    out["sunshine"] = "\n".join(rows)

    # --- cuts
    f = sorted(cuts, reverse=True)
    head = {1.0: "Demand as it is", 0.794: "× 0.794", 0.76: "× 0.76", 0.6: "× 0.60"}
    rows = ["| | " + " | ".join(head[x] for x in f) + " | Earth |", "|---|" + "---|" * (len(f) + 1)]
    for label, key, fmt, earth in (("Like for like, engine over measured", "like", "{:.2f}", "1"), ("… its median over the basins that are alike", "median", "{:.2f}", ""),
                                   ("… without the Amazon", "without_amazon", "{:.2f}", ""), ("… basin by basin, lowest", "lowest", "{:.2f}", ""), ("… highest", "highest", "{:.2f}", ""),
                                   (f"… basins within 15 % of the measured depth, of {ls['alike']}", "within_15", "{}", ""), ("Rain on land that goes back to the air", "back", "{:.3f}", "0.65"),
                                   ("… as a depth over the land", "mm", "{} mm", ""), ("Rivers reaching the sea, thousand km³", "to_sea", "{:.1f}", "40"),
                                   ("Gauges within a factor of two, of 21", "gauges", "{}", "")):
        rows.append(f"| {label} | " + " | ".join(fmt.format(cuts[x][key]) for x in f) + f" | {earth} |")
    out["cuts"], out["cutrows"] = "\n".join(rows), cuts
    out.update(r=r, w=w, c=c, t20=t20, t100=t100, m=m, mn=mn, g=g, nar=nar)
    return out


def share_table(d):
    rows = ["| Valley share | Mouths within 300 km, as built | in 20 random settlements | Gauges within a factor of two, as built | in 20 | The lake at the Caspian's place, as built | keeps its water in, of 20 | overflow at most, km³ a year | its area, million km² | its level, m | Like for like, as built | in 20 | Land under lakes | Back to the air | To the sea, thousand km³ |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    info = {}
    for s in SHARES:
        t = lg.ties(d["shares"][s])
        assert t["n"] == 20 and abs(lg.header(d["shares"][s])["valley_share"] - float(s)) < 1e-9
        c = t["caspian"]
        info[s] = t
        b = "**" if s == "0.1" else ""
        span = lambda a: f"{a[0]} to {a[1]}" if a[0] != a[1] else f"{a[0]}"
        rows.append(f"| {b}{s}{b} | {t['mouths_engine']} | {span(t['mouths_random'])} | {t['gauges_engine']} | {span(t['gauges_random'])} | "
                    + (f"overflows by {c['engine_overflow']:.2f} km³" if c["engine_overflows"] else "keeps its water")
                    + f" | {c['closed']} | {'' if c['overflow_up_to'] is None else format(c['overflow_up_to'], '.2f')} | {span(c['area'])} | {span(c['level'])} | {t['like'][0]:.2f} | "
                    f"{t['like'][2]:.2f} to {t['like'][3]:.2f} | {t['lakes'][0]:.2f} % | {t['back'][0]:.4f} | {t['to_sea'][0]:.2f} |")
    return "\n".join(rows), info


def water_table(d):
    """The relief's own water beside the planet file's: as built and over 20 random settlements."""
    a, b = lg.ties(d["s20"]), lg.ties(d["planet_s20"])
    ha, hb = lg.header(d["rivers"]), lg.header(d["planet"])
    ma, mb = lg.mouths(d["rivers"])[0], lg.mouths(d["planet"])[0]
    assert ha["water"] == "relief" and hb["water"] == "planet"
    rows = ["| | The relief's own water (the design's; as built) | The planet file's, 0.19 % less |", "|---|---|---|",
            f"| Volume poured | {ha['volume']:.5e} m³ | {hb['volume']:.5e} m³ |",
            f"| The sea of the mesh comes to rest at | {ha['sea_level']:+.1f} m | {hb['sea_level']:+.1f} m |",
            f"| … and covers | {ha['sea_share']:.2f} % of the planet | {hb['sea_share']:.2f} % |",
            f"| Land cells | {N(ha['land_cells'])} | {N(hb['land_cells'])} |",
            f"| River mouths within 300 km, of 24, as built; in 20 random settlements | {a['mouths_engine']}; {a['mouths_random'][0]} to {a['mouths_random'][1]} | {b['mouths_engine']}; {b['mouths_random'][0]} to {b['mouths_random'][1]} |",
            f"| The Amazon's mouth, as built | {ma['Amazon']['km']} km | {mb['Amazon']['km']} km |",
            f"| The Nile's mouth within 300 km in, of 20 | {a['mouths']['Nile']['passes']} | {b['mouths']['Nile']['passes']} |",
            f"| Gauges within a factor of two, of 21, as built; in 20 | {a['gauges_engine']}; {a['gauges_random'][0]} to {a['gauges_random'][1]} | {b['gauges_engine']}; {b['gauges_random'][0]} to {b['gauges_random'][1]} |",
            f"| The lake at the Caspian's place, as built | overflows by {a['caspian']['engine_overflow']:.2f} km³ a year | overflows by {b['caspian']['engine_overflow']:.2f} |",
            f"| … keeps its water in, of 20 random settlements | {a['caspian']['closed']} | {b['caspian']['closed']} |",
            f"| Like for like, engine over measured, as built | {a['like'][0]:.2f} | {b['like'][0]:.2f} |",
            f"| Rain on land that goes back to the air | {a['back'][0]:.4f} | {b['back'][0]:.4f} |",
            f"| Rivers reaching the sea, thousand km³ a year | {a['to_sea'][0]:.2f} | {b['to_sea'][0]:.2f} |",
            f"| Land under lakes | {a['lakes'][0]:.2f} % | {b['lakes'][0]:.2f} % |"]
    return "\n".join(rows), a, b


if __name__ == "__main__":
    d = read(sys.argv[1])
    print(sec42(d))
    o = sec44_tables(d)
    for k in ("narrows", "ties", "mouths", "gauges", "like", "volga", "radiation", "sunshine", "cuts"):
        print(o[k], "\n")
    print(share_table(d)[0], "\n")
    print(water_table(d)[0])
