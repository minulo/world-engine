"""Earth's great rivers and lakes as the engine's Drainage and Hydrology make them, beside the measured ones.

    python tools/earth_rivers.py [--level 7] [--valley-share 0.1] [--demand-times 1.0] [--ties engine|mean|SEED]
                                 [--settlements N] [--demands]
    python tools/earth_rivers.py --trace RIVER [--ties ...]

Earth's relief (ETOPO5) is put on the mesh, SeaLevel pours Earth's water on it, Drainage finds the ways down, and
Hydrology is handed Earth's measured rain (GPCP, 1979 to 2010) and warmth (CRU, 1961 to 1990). Nothing of the
engine's own climate enters: what is printed is how these two processes do when their inputs are the truth.

Read part 7 before any single river. The relief comes in whole metres, a third of the land cells tie exactly with a
neighbour, and where heights tie the data cannot say which way a river runs (python tools/earth_relief.py). Parts 1
to 6 show one way of settling those ties; part 7 settles them at random many times and counts how often each
outcome comes. A count is of the draws made: an outcome that came in none of 20 may come in one of 100.

  1. Each great river at its last gauging station (Dai and Trenberth, Table 2): the flow measured and the flow
     the engine gives, taken apart:
       the land that drains to the gauge: on Earth; on the mesh as the water runs ("reaches": closed hollows
           upstream keep their water); and on the mesh if every hollow were full
       what that land sheds in a year: measured (the flow over the real basin), and the engine's over the land
           that reaches the gauge, with the rain on it and the air's demand for water
       what the lakes with an outlet on the way lose to the air
     so that the engine's flow = the land that reaches the gauge x what it sheds - what the lakes lose. Each of
     the three is worked out by itself, and the line under the table says how nearly the books close.
  2. Like for like: what the land of each basin sheds, on the mesh's own river at the gauge wherever its basin
     with every hollow full is within a factor of 1.5 of the real one's area. Part 1 mixes where the rivers run
     with what the land sheds; this part looks at the second alone. Its last lines are the Volga, the one basin
     for which a published precipitation is at hand as well: under the rain data, and with the published
     precipitation handed in instead, so that what the rain data add can be told from what the model does.
  3. Where each great river leaves the land on the mesh, against its real mouth.
  4. The largest lakes, with the model's books of each.
  5. The water of all the land.
  6. Narrows of six great rivers: how high the mesh's ground stands in the valley, against the level of the lake
     that the closed valley dams above it, and where the water goes instead.
  7. With --settlements N: the same outcomes with the ties settled at random N times (seeds 1 to N), and once by
     the cells' mean heights. A random settlement draws everything that the heights leave open: the width of every
     way, the order of the cells, and among passes of one height which is taken (earth_reference.Earth).
  8. With --demands: the land's water with the air's demand for water multiplied by 1, 0.794, 0.76 and 0.6. A
     diagnosis: it shows how much a smaller demand would mend, and that two cuts with different causes mend alike.

--valley-share   the share of a cell's land points that lie below the height Drainage is handed (the Earth tests
                 use 0.1; see earth_reference.Earth). The outcomes depend on it, and this option shows how.
--demand-times   a diagnosis, not a setting of the engine: the air's demand for water multiplied by this factor.
--ties           how exact ties are settled in parts 1 to 6: "engine" (the default: as the engine does, by the wider
                 way), "mean" (toward the cell with the lower mean height), or a number (at random, with that seed).

--trace          instead of the report: the way of one great river over the mesh with every hollow full, cell by cell,
                 with the height each cell was handed in at, its mean height, and what the data's own grid makes of
                 the place. Where a step is "level" or "lake", the heights do not decide it.

The Earth tests (tests/test_earth.py) state the misses printed here as expected failures, one by one.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402
from worldengine import console                          # noqa: E402


within = ref.within_a_factor_of_two
DEMANDS = (1.0, 0.794, 0.76, 0.6)       # part 8: as built; the Priestley-Taylor rule without its extra (1 / 1.26); the factor that
                                        # brings the land's energy to the measured (65.5 of 85.7 W/m2); and a larger cut


def ties_of(word):
    """--ties: "engine" (None), "mean", or a whole number."""
    if word in (None, "engine"):
        return None
    if word == "mean":
        return word
    try:
        return int(word)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{word!r} is not one of engine, mean, or a whole number (the seed of a random settlement)") from None


def report(level=7, valley_share=ref.VALLEY_SHARE, demand_times=1.0, ties=None, settlements=0, say=print, earth=None, demands=False):
    """The report. `earth` is an Earth built already (its level, valley share and ties then stand)."""
    e = earth if earth is not None else ref.Earth(level, valley_share, ties)
    valley_share, ties = e.valley_share, e.ties
    h = e.hydrology(ref.demand_times(e, demand_times) if demand_times != 1.0 else None)
    m = e.mesh
    say(f"Earth on {m.n} cells; valley floors at the lowest {valley_share:g} of each cell's land points; exact ties settled "
        + ("as the engine settles them" if ties is None else "by the cells' mean heights" if ties == "mean" else f"at random (seed {ties})")
        + ("" if demand_times == 1.0 else f"; the demand for water multiplied by {demand_times:g} (a diagnosis)"))

    say("\n1. Great rivers at their last gauging stations (flows in km3 a year, areas in thousand km2, depths in mm a year)")
    say(f"{'':12s}{'flow':>19s}{'':11s} | {'land that drains to the gauge':>30s}   | {'what that land sheds':>20s}{'':14s} | lakes on the")
    say(f"{'':12s}{'measured':>9s}{'engine':>8s}  {'within x2':10s} | {'real':>8s}{'reaches':>9s}{'all hollows full':>18s} |"
        f"{'measured':>9s}{'engine':>8s}{'rain':>7s}{'demand':>8s} | way lose")
    rows = ref.rivers_at_gauges(e, h)
    hit = 0
    for name, r in rows.items():
        ok = within(r["measured"], r["flow"])
        hit += ok
        say(f"{name:12s}{r['measured']:9.0f}{r['flow']:8.0f}  {'yes' if ok else 'NO':10s} | {r['station_area']:8.0f}{r['reaches']:9.0f}"
            f"{r['basin']:18.0f} |{r['measured_depth']:9.0f}{r['sheds']:8.0f}{r['rain']:7.0f}{r['demand']:8.0f} | {r['lost_in_lakes']:8.0f}"
            + ("   no river within 150 km: the cell that the most land drains to, with every hollow full" if r["no_river"] else ""))
    say(f"within a factor of two of the measured flow: {hit} of {len(rows)}")
    say(f"the books of every gauge close: land that reaches it x what it sheds - what lakes on the way lose - what a closed lake in the "
        f"gauge's own cell keeps = the flow, to within {max(abs(r['unbalanced']) for r in rows.values()):.1e} km3 a year"
        + "".join(f"; a closed lake in the cell of the {name}'s gauge keeps {r['kept_here']:.2f} km3" for name, r in rows.items() if r["kept_here"] > 0.005))
    everywhere = ref.river_books(e, h)
    size = np.maximum(np.maximum(everywhere["flow"], everywhere["shed"]), 1.0)
    say(f"and at every cell of the mesh, to within {np.abs(everywhere['unbalanced'] / size).max():.1e} of the larger of the flow and the water shed upstream")

    say("\n2. Like for like: what the land of each basin sheds, on the mesh's own river at the gauge (areas in thousand km2, depths in mm a year)")
    say(f"{'':12s}{'basin: real':>12s}{'mesh':>8s}  {'alike':6s}{'sheds: measured':>16s}{'engine':>8s}{'engine / measured':>19s}{'rain':>7s}{'demand':>8s}"
        f"{'measured / rain':>17s}")
    like = ref.like_for_like(e, h)
    for name, r in like.items():
        say(f"{name:12s}{r['station_area']:12.0f}{r['basin']:8.0f}  {'yes' if r['like'] else 'no':6s}{r['measured_depth']:16.0f}{r['sheds']:8.0f}"
            f"{r['ratio']:19.2f}{r['rain']:7.0f}{r['demand']:8.0f}{r['measured_depth'] / max(r['rain'], 1e-9):17.2f}")
    t = ref.like_together(like)
    if t["basins"]:
        ratios = sorted(like[name]["ratio"] for name in t["basins"])
        say(f"basins alike: {len(t['basins'])} of {len(like)}. All of them together, the engine sheds {t['ratio']:.2f} of the measured depth; "
            f"basin by basin {ratios[0]:.2f} to {ratios[-1]:.2f}, {t['below_one']} below 1 and {t['above_one']} above; "
            f"within a factor of two: {t['within_two']}")
        heavy = max(t["weights"], key=t["weights"].get)
        say(f"what that figure can bear: it is a mean weighted by water, and the {heavy} carries {100 * t['weights'][heavy]:.0f} % of the weight. "
            f"Without the {heavy}: {ref.like_together(like, (heavy,))['ratio']:.2f}. The median of the basins' own ratios: {t['median']:.2f}")
        short = [name for name in t["basins"] if like[name]["measured_depth"] > ref.MUCH_OF_THE_RAIN * like[name]["rain"]]
        if short:
            say(f"basins in which the runoff measured is more than {ref.MUCH_OF_THE_RAIN:g} of the rain handed to the engine over the mesh's basin, so that the "
                "comparison tests the rain data or the basin more than what Hydrology does with rain: "
                + ", ".join(f"the {name} (rain {like[name]['rain']:.0f}, measured runoff {like[name]['measured_depth']:.0f})" for name in short)
                + f". Without them: {ref.like_together(like, short)['ratio']:.2f}")
        say("(the engine's depth is taken before any lake loses water, the measured one after: that favours the engine)")
    if demand_times == 1.0:
        v = ref.volga(e, h)
        d, p, rain = v["data"], v["published_rain"], ref.VOLGA["precipitation_mm"]
        say(f"The Volga at Volgograd, which ends in a closed sea and is not among the gauges: basin {d['station_area']:.0f} real, {d['basin']:.0f} on the mesh "
            f"({'alike' if d['like'] else 'not alike'}). Published for the basin: rain {rain:.0f}, sheds {d['measured_depth']:.0f}, back to the air {rain - d['measured_depth']:.0f}")
        other = ref.VOLGA["runoff_coefficient"] * rain
        say(f"   (the same source gives a runoff coefficient of {ref.VOLGA['runoff_coefficient']:g}, which makes {other:.0f} mm of its {rain:.0f}: "
            f"the two published figures differ, and both are set beside the engine's)")
        say(f"   under the rain data:                rain {d['rain']:.0f}, sheds {d['sheds']:.0f} ({d['ratio']:.2f} of the {d['measured_depth']:.0f}, "
            f"{d['sheds'] / other:.2f} of the {other:.0f}), back to the air {d['rain'] - d['sheds']:.0f}")
        say(f"   handed the published rain instead:  rain {p['rain']:.0f}, sheds {p['sheds']:.0f} ({p['ratio']:.2f} of the {d['measured_depth']:.0f}, "
            f"{p['sheds'] / other:.2f} of the {other:.0f}), back to the air {p['rain'] - p['sheds']:.0f}"
            f"   (a diagnosis: the rain data over that land, scaled by one factor in every month)")

    say("\n3. Where each great river leaves the land with every hollow full, against its real mouth")
    basin = e.drainage.fields["basin_id"]
    near = 0
    for name, (place, mouth) in ref.GREAT_RIVERS.items():
        end = int(basin[e.cell(*place)])
        near += e.km(end, *mouth) < ref.MOUTH_WITHIN_KM
        say(f"{name:12s}{e.km(end, *mouth):7.0f} km from its mouth, at {m.lat[end]:6.1f}, {m.lon[end]:7.1f}")
    say(f"within {ref.MOUTH_WITHIN_KM:.0f} km: {near} of {len(ref.GREAT_RIVERS)}")

    say("\n4. The largest lakes (km2; m; km3 a year)")
    lakes = h.tables["lakes"]
    say(f"{'area':>12s}{'level':>7s}  {'outlet':6s}{'reaches it':>11s}{'extra loss':>11s}{'runs on':>9s}{'rain on it':>11s}{'evaporates':>11s}   lowest point at")
    for i in np.argsort(-lakes["area_m2"])[:12]:
        b = int(lakes["bottom_cell"][i])
        say(f"{lakes['area_m2'][i] / 1e6:12,.0f}{lakes['level_m'][i]:7.0f}  {'yes' if lakes['overflows'][i] else 'no':6s}"
            f"{lakes['inflow_m3_per_year'][i] / 1e9:11.0f}{lakes['loss_to_air_m3_per_year'][i] / 1e9:11.0f}"
            f"{lakes['outflow_m3_per_year'][i] / 1e9:9.2f}{lakes['rain_on_lake_m3_per_year'][i] / 1e9:11.0f}"
            f"{lakes['evaporation_m3_per_year'][i] / 1e9:11.0f}   {m.lat[b]:6.1f}, {m.lon[b]:7.1f}")
    say("(reaches it: the water that runs toward the lake, counted as if none of its ground were flooded; so it holds the rain on the lake's own\n"
        " cells less what their ground would have given the air. What rivers and shores bring = runs on + evaporates - rain on it.)")
    big = lakes["area_m2"] > 1.0e11
    say(f"lakes larger than 100,000 km2: {int(big.sum())}, with {100 * lakes['area_m2'][big].sum() / max(lakes['area_m2'].sum(), 1e-30):.0f} % of all the land under lakes")

    say("\n5. The water of all the land (thousand km3 a year)")
    w = ref.land_water(e, h)
    say(f"rain on land {w['rain']:.1f}; back to the air {w['to_air']:.1f} ({w['back_to_air']:.3f} of the rain); rivers reaching the sea {w['to_sea']:.1f}")
    if "shed" in w:
        say(f"shed by the land as if none of it were flooded {w['shed']:.1f} ({w['back_to_air_dry']:.3f} of the rain back to the air); "
            f"lakes with an outlet lose {w['lakes_with_outlet_lose']:.2f} more than the ground they cover; closed lakes keep {w['closed_lakes_keep']:.2f}")
        say(f"land whose water reaches the sea as the water runs: {100 * w['reaches_sea_share']:.1f} %; land that drains into a closed hollow "
            f"(depression_id above 0): {100 * w['closed_hollow_share']:.1f} %; land under water if every hollow were full: "
            f"{100 * w['under_water_if_full_share']:.1f} %, and another {100 * w['level_with_the_water_share']:.1f} % exactly level with that water")
    say(f"the air's demand for water over land {w['demand_mm']:.0f} mm a year; rain {w['rain_mm']:.0f} mm; back to the air {w['to_air_mm']:.0f} mm; "
        f"lakes cover {100 * w['lakes_share']:.2f} % of the land: {w['lakes']} lakes, {w['lakes_with_outlet']} with an outlet")

    if demand_times == 1.0:
        say("\n6. Narrows (the lowest way through the valley, on the heights Drainage was handed), and where the water goes instead")
        for name, r in ref.narrows(e).items():
            through = r["lake_level_m"] is not None and r["barrier_m"] is not None and r["barrier_m"] <= r["lake_level_m"]
            lake = ("no lake stands above it" if r["lake_level_m"] is None else
                    f"the lake above it stands at {r['lake_level_m']:.0f} m and "
                    + ("keeps its water" if not r["lake_overflows"] else "overflows, and the valley stands no higher than its water" if through
                       else "overflows by another way"))
            say(f"{name:12s} the valley rises to {r['barrier_m']:.0f} m, at {r['barrier_at'][0]:.1f}, {r['barrier_at'][1]:.1f}; {lake}")
            if r["leaves_at"] is not None:
                say(f"{'':12s} its water leaves the land at {r['leaves_at'][0]:.1f}, {r['leaves_at'][1]:.1f}; the highest cell on its way, by mean height: "
                    f"{r['over_mean_m']:.0f} m at {r['over_at'][0]:.1f}, {r['over_at'][1]:.1f}, handed to Drainage at {r['handed_m']:.0f} m")

    if settlements and demand_times == 1.0:
        what_the_ties_decide(e, settlements, say)
    if demands and demand_times == 1.0:
        what_a_smaller_demand_would_do(e, say)
    return e, h, rows


def what_a_smaller_demand_would_do(e, say=print, factors=DEMANDS):
    """Part 8. Returns {factor: earth_reference.under_demand}."""
    say("\n8. The land's water with the air's demand for water multiplied by a factor (a diagnosis, not a setting of the engine)")
    say(f"{'factor':>8s}{'like for like':>15s}{'its median':>12s}{'without the Amazon':>20s}{'basins: lowest':>16s}{'highest':>9s}{'within 15 %':>13s}"
        f"{'back to the air':>17s}{'mm a year':>11s}{'to the sea':>12s}{'gauges within x2':>18s}")
    out = {}
    for factor in factors:
        r = out[factor] = ref.under_demand(e, factor)
        say(f"{factor:8g}{r['like_all']:15.2f}{r['like_median']:12.2f}{r['like_without_amazon']:20.2f}{r['like_lowest']:16.2f}{r['like_highest']:9.2f}"
            f"{r['like_within_15']:13d}{r['back_to_air']:17.3f}{r['to_air_mm']:11.0f}{r['to_sea']:12.1f}{r['gauges_within']:14d} of {len(ref.GAUGES)}")
    say("(Earth: like for like 1 by definition; 0.65 of the rain on land back to the air; 40 thousand km3 a year to the sea.\n"
        " 0.794 is the Priestley-Taylor rule with its factor of 1.26 taken as 1.00; 0.76 is 65.5 over 85.7, the energy that a published budget\n"
        " leaves the land over what the engine's formulas leave it: python tools/earth_demand.py. The two cuts have different causes and mend\n"
        " the weighted figure alike. Neither mends the basins: one factor for all land leaves them spread from a third to 1.7 times the measured.)")
    return out


def what_the_ties_decide(e, settlements, say=print):
    """Part 7: the outcomes with the ties settled at random `settlements` times, by the cells' mean heights, and as the
    engine settles them. Returns the summaries: {"engine": ..., "mean": ..., 1: ..., 2: ...}."""
    runs = {"engine": ref.summary(e if e.ties is None else e.settled(None)), "mean": ref.summary(e.settled("mean"))}
    for seed in range(1, settlements + 1):
        runs[seed] = ref.summary(e.settled(seed))
    n = settlements
    t = ref.tally([runs[seed] for seed in range(1, n + 1)])
    one = {key: ref.tally([runs[key]]) for key in ("engine", "mean")}
    say(f"\n7. What the ties decide: the engine's way of settling them, the cells' mean heights, and {n} settlements at random")
    say(f"   (a random settlement draws the width of every way, the order of the cells, and which of several passes of one height is taken)")
    say(f"\nRiver mouths within {ref.MOUTH_WITHIN_KM:.0f} km, of {len(ref.GREAT_RIVERS)}: engine {one['engine']['mouths_passing'][0]}; "
        f"mean heights {one['mean']['mouths_passing'][0]}; at random {t['mouths_passing'][0]} to {t['mouths_passing'][1]}")
    say(f"{'':12s}{'engine':>8s}{'mean':>8s}{'at random: from':>18s}{'to':>7s}   within {ref.MOUTH_WITHIN_KM:.0f} km in")
    for name in ref.GREAT_RIVERS:
        k, low, high = t["mouths"][name]
        say(f"{name:12s}{runs['engine']['mouth_km'][name]:8.0f}{runs['mean']['mouth_km'][name]:8.0f}{low:18.0f}{high:7.0f}   {k:3d} of {n}"
            + ("" if k in (0, n) else "   <- the ties decide"))
    always, never = sum(k == n for k, _, _ in t["mouths"].values()), sum(k == 0 for k, _, _ in t["mouths"].values())
    say(f"in all {n}: {always} rivers; in none: {never}; in some: {len(ref.GREAT_RIVERS) - always - never}")
    say(f"\nGauges within a factor of two, of {len(ref.GAUGES)}: engine {one['engine']['gauges_passing'][0]}; mean heights "
        f"{one['mean']['gauges_passing'][0]}; at random {t['gauges_passing'][0]} to {t['gauges_passing'][1]}")
    say(f"{'':12s}{'measured':>9s}{'engine':>8s}{'mean':>8s}{'at random: from':>18s}{'to':>7s}   within x2 in    | like for like: alike in, engine / measured from, to")
    for name in ref.GAUGES:
        k, low, high, alike, least, most = t["gauges"][name]
        say(f"{name:12s}{ref.GAUGES[name][2]:9.0f}{runs['engine']['flow'][name]:8.0f}{runs['mean']['flow'][name]:8.0f}{low:18.0f}{high:7.0f}   "
            f"{k:3d} of {n}{'   <- the ties decide' if 0 < k < n else '':21s} | {alike:3d} of {n}" + (f"   {least:.2f}  {most:.2f}" if alike else ""))
    always, never = sum(v[0] == n for v in t["gauges"].values()), sum(v[0] == 0 for v in t["gauges"].values())
    say(f"in all {n}: {always} rivers; in none: {never}; in some: {len(ref.GAUGES) - always - never}")
    say(f"\nLike for like, all like basins together, the engine sheds of the measured depth: engine {runs['engine']['like_all']:.2f}; "
        f"mean heights {runs['mean']['like_all']:.2f}; at random {t['like_all'][0]:.2f} to {t['like_all'][1]:.2f}")
    for key, words, scale, digits in (("back_to_air", "Of the rain on land, back to the air", 1.0, 4), ("to_sea", "Rivers reaching the sea, thousand km3 a year", 1.0, 2),
                                      ("lakes_share", "Land under lakes, %", 100.0, 2)):
        say(f"{words}: engine {scale * runs['engine'][key]:.{digits}f}; mean heights {scale * runs['mean'][key]:.{digits}f}; "
            f"at random {scale * t[key][0]:.{digits}f} to {scale * t[key][1]:.{digits}f}")
    words = lambda c: "no lake" if c is None else (f"overflows by {c['outflow_km3']:.2f} km3 a year" if c["overflows"] else "closed") + f", {c['area_km2'] / 1e6:.2f} million km2 at {c['level_m']:.0f} m"
    v = [runs[seed]["volga"] for seed in range(1, n + 1)]
    say(f"The Volga at Volgograd, like for like: engine: basin {runs['engine']['volga']['basin']:.0f}, rain {runs['engine']['volga']['rain']:.0f} mm, sheds "
        f"{runs['engine']['volga']['sheds']:.0f}; at random: alike in {sum(x['like'] for x in v)} of {n}, basin {min(x['basin'] for x in v):.0f} to "
        f"{max(x['basin'] for x in v):.0f}, rain {min(x['rain'] for x in v):.0f} to {max(x['rain'] for x in v):.0f}, sheds {min(x['sheds'] for x in v):.0f} to "
        f"{max(x['sheds'] for x in v):.0f}, back to the air {min(x['rain'] - x['sheds'] for x in v):.0f} to {max(x['rain'] - x['sheds'] for x in v):.0f}")
    over = t["caspian_overflow_km3"]
    say(f"The lake at the Caspian's place: engine: {words(runs['engine']['caspian'])}; mean heights: {words(runs['mean']['caspian'])}; at random: closed in "
        f"{t['caspian_closed']} of {n}" + ("" if over[1] is None else f", overflow up to {over[1]:.2f} km3 a year")
        + ("" if t["caspian_area_km2"][0] is None else f", {t['caspian_area_km2'][0] / 1e6:.2f} to {t['caspian_area_km2'][1] / 1e6:.2f} million km2 at "
           f"{t['caspian_level_m'][0]:.0f} to {t['caspian_level_m'][1]:.0f} m"))
    return runs


def trace(river, level=7, valley_share=ref.VALLEY_SHARE, ties=None, say=print, earth=None, flood=None):
    e = earth if earth is not None else ref.Earth(level, valley_share, ties)
    flood = flood if flood is not None else ref.raw_flood()
    way = ref.way_of(e, river)
    place, mouth = ref.GREAT_RIVERS[river]
    say(f"The {river} on the mesh with every hollow full, from {place[0]:.1f}, {place[1]:.1f}; its real mouth: {mouth[0]:.1f}, {mouth[1]:.1f}")
    say(f"{'':4s}{'lat':>7s}{'lon':>8s}{'handed in at':>14s}{'mean height':>13s}  {'step':6s}{'lake level':>11s}{'km to mouth':>13s}   the data there: height, joined to the ocean at")
    for k, c in enumerate(way):
        x = ref.raw_at(flood, c["lat"], c["lon"])
        say(f"{k:4d}{c['lat']:7.1f}{c['lon']:8.1f}{c['ground_m']:12.0f} m{c['mean_m']:11.0f} m  {c['step']:6s}"
            + (f"{c['lake_level_m']:9.0f} m" if c["lake_level_m"] is not None else f"{'':11s}") + f"{c['km_to_mouth']:13.0f}   "
            + (f"{x['height']:.0f} m, ocean" if x["ocean"] else f"{x['height']:.0f} m, {x['level']:.0f} m"))
    dry = [c for c in way if c["step"] != "sea"]
    kinds = {kind: sum(c["step"] == kind for c in dry) for kind in ("down", "level", "lake")}
    say(f"{len(dry)} land cells: {kinds['down']} steps down to lower ground, {kinds['level']} over level ground, {kinds['lake']} across full hollows; "
        f"nearest to its real mouth: {min(c['km_to_mouth'] for c in dry):.0f} km; leaves the land {dry[-1]['km_to_mouth']:.0f} km from it")
    return way


def parser():
    p = console.tool_parser(__doc__, "python tools/earth_rivers.py")
    p.add_argument("--level", type=console.whole_number(3, 8), default=7, metavar="LEVEL")
    p.add_argument("--valley-share", type=console.number_between(0.0, 1.0, open_low=True), default=ref.VALLEY_SHARE, metavar="SHARE")
    p.add_argument("--demand-times", type=console.number_between(0.0, 10.0, open_low=True), default=1.0, metavar="FACTOR")
    p.add_argument("--ties", type=ties_of, default=None, metavar="engine|mean|SEED")
    p.add_argument("--settlements", type=console.whole_number(0), default=0, metavar="N")
    p.add_argument("--demands", action="store_true")
    p.add_argument("--trace", choices=list(ref.GREAT_RIVERS), default=None, metavar="RIVER")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not ref.available():
        print("the Earth reference data is not here: run python tools/fetch_reference_data.py", file=sys.stderr)
        return 1
    if args.trace:
        trace(args.trace, args.level, args.valley_share, args.ties)
    else:
        report(args.level, args.valley_share, args.demand_times, args.ties, args.settlements, demands=args.demands)
    return 0


if __name__ == "__main__":
    sys.exit(main())
