"""Earth's great rivers and lakes as the engine's Drainage and Hydrology make them, beside the measured ones.

    python tools/earth_rivers.py [--level 7] [--valley-share 0.1] [--demand-times 1.0] [--ties engine|mean|SEED] [--settlements N]
    python tools/earth_rivers.py --trace RIVER [--ties ...]

Earth's relief (ETOPO5) is put on the mesh, SeaLevel pours Earth's water on it, Drainage finds the ways down, and
Hydrology is handed Earth's measured rain (GPCP, 1979 to 2010) and warmth (CRU, 1961 to 1990). Nothing of the
engine's own climate enters: what is printed is how these two processes do when their inputs are the truth.

Read part 7 before any single river. The relief comes in whole metres, a third of the land cells tie exactly with a
neighbour, and where heights tie the data cannot say which way a river runs (python tools/earth_relief.py). Parts 1
to 6 show one way of settling those ties; part 7 settles them at random many times and shows which outcomes stay.

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
     the cells' mean heights.

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
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402


def option(args, name, default, kind=float):
    return kind(args[args.index(name) + 1]) if name in args else default


def ties_of(word):
    return None if word in (None, "engine") else word if word == "mean" else int(word)


def within(measured, flow):
    return measured / ref.FLOW_WITHIN < flow < measured * ref.FLOW_WITHIN


def report(level=7, valley_share=ref.VALLEY_SHARE, demand_times=1.0, ties=None, settlements=0, say=print):
    e = ref.Earth(level, valley_share, ties)
    constants = None
    if demand_times != 1.0:
        extra = e.h.params["models"]["slots"]["Hydrology"]["constants"]["demand"]["priestley_taylor_extra"]
        constants = {"demand": {"priestley_taylor_extra": (1.0 + extra) * demand_times - 1.0}}
    h = e.hydrology(constants)
    m, area, land = e.mesh, e.area.astype(np.float64), e.land
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
    say(f"the books of every gauge close: land that reaches it x what it sheds - what lakes lose = the flow, to within "
        f"{max(abs(r['unbalanced']) for r in rows.values()):.1e} km3 a year")

    say("\n2. Like for like: what the land of each basin sheds, on the mesh's own river at the gauge (areas in thousand km2, depths in mm a year)")
    say(f"{'':12s}{'basin: real':>12s}{'mesh':>8s}  {'alike':6s}{'sheds: measured':>16s}{'engine':>8s}{'engine / measured':>19s}{'rain':>7s}{'demand':>8s}")
    like = ref.like_for_like(e, h)
    for name, r in like.items():
        say(f"{name:12s}{r['station_area']:12.0f}{r['basin']:8.0f}  {'yes' if r['like'] else 'no':6s}{r['measured_depth']:16.0f}{r['sheds']:8.0f}"
            f"{r['ratio']:19.2f}{r['rain']:7.0f}{r['demand']:8.0f}")
    alike = [r for r in like.values() if r["like"]]
    if alike:
        ratios = sorted(r["ratio"] for r in alike)
        say(f"basins alike: {len(alike)} of {len(like)}. All of them together, the engine sheds "
            f"{sum(r['sheds'] * r['basin'] for r in alike) / sum(r['measured_depth'] * r['basin'] for r in alike):.2f} of the measured depth; "
            f"basin by basin {ratios[0]:.2f} to {ratios[-1]:.2f}, {sum(x < 1.0 for x in ratios)} below 1 and {sum(x >= 1.0 for x in ratios)} above; "
            f"within a factor of two: {sum(0.5 < x < 2.0 for x in ratios)}")
        say("(the engine's depth is taken before any lake loses water, the measured one after: that favours the engine)")
    if demand_times == 1.0:
        v = ref.volga(e, h)
        d, p, rain = v["data"], v["published_rain"], ref.VOLGA["precipitation_mm"]
        say(f"The Volga at Volgograd, which ends in a closed sea and is not among the gauges: basin {d['station_area']:.0f} real, {d['basin']:.0f} on the mesh "
            f"({'alike' if d['like'] else 'not alike'}). Published for the basin: rain {rain:.0f}, sheds {d['measured_depth']:.0f}, back to the air {rain - d['measured_depth']:.0f}")
        say(f"   under the rain data:                rain {d['rain']:.0f}, sheds {d['sheds']:.0f} ({d['ratio']:.2f} of the published), back to the air {d['rain'] - d['sheds']:.0f}")
        say(f"   handed the published rain instead:  rain {p['rain']:.0f}, sheds {p['sheds']:.0f} ({p['ratio']:.2f} of the published), back to the air {p['rain'] - p['sheds']:.0f}"
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
    f = h.fields
    fell = (e.rain.sum(axis=0) * area)[land].sum() / 1e15                      # mm on m2, to thousand km3
    to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * area)[land].sum() / 1e15
    to_sea = f["river_discharge"].astype(np.float64)[:, e.wet].mean(axis=0).sum() * ref.YEAR_S / 1e12
    flooded = (f["lake_fraction"].astype(np.float64) * area).sum() / area[land].sum()
    asked = np.nansum(f["potential_evapotranspiration"].astype(np.float64), axis=0)
    say(f"rain on land {fell:.1f}; back to the air {to_air:.1f} ({to_air / fell:.3f} of the rain); rivers reaching the sea {to_sea:.1f}")
    books = e.books(h)
    if books:
        shed = books["shed"].sum(axis=0)[land].sum() / 1e12
        with_outlet = lakes["overflows"].astype(bool)
        say(f"shed by the land as if none of it were flooded {shed:.1f} ({1 - shed / fell:.3f} of the rain back to the air); "
            f"lakes with an outlet lose {lakes['loss_to_air_m3_per_year'][with_outlet].sum() / 1e12:.2f} more than the ground they cover; "
            f"closed lakes keep {lakes['inflow_m3_per_year'][~with_outlet].sum() / 1e12:.2f}")
        from worldengine.library import drainage as dr
        ways = books["flows"]["receivers"]
        ends = dr.terminal(dr.flow_stack(ways), ways)
        full = e.drainage.drivers["drainage_area"]["cell_is"]
        say(f"land whose water reaches the sea as the water runs: {100 * area[land & e.wet[ends]].sum() / area[land].sum():.1f} %; "
            f"land that drains into a closed hollow (depression_id above 0): "
            f"{100 * area[land & (books['label'] > 0)].sum() / area[land].sum():.1f} %; "
            f"land under water if every hollow were full: {100 * area[land & (full == 1)].sum() / area[land].sum():.1f} %")
    say(f"the air's demand for water over land {(asked * area)[land].sum() / area[land].sum():.0f} mm a year; rain "
        f"{1e15 * fell / area[land].sum():.0f} mm; lakes cover {100 * flooded:.2f} % of the land: {len(lakes['hollow'])} lakes, "
        f"{int(lakes['overflows'].sum())} with an outlet")

    if demand_times == 1.0:
        say("\n6. Narrows (the lowest way through the valley, on the heights Drainage was handed), and where the water goes instead")
        for name, r in ref.narrows(e).items():
            lake = ("no lake stands above it" if r["lake_level_m"] is None else
                    f"the lake above it stands at {r['lake_level_m']:.0f} m and " + ("overflows by another way" if r["lake_overflows"] else "keeps its water"))
            say(f"{name:12s} the valley rises to {r['barrier_m']:.0f} m, at {r['barrier_at'][0]:.1f}, {r['barrier_at'][1]:.1f}; {lake}")
            if r["leaves_at"] is not None:
                say(f"{'':12s} its water leaves the land at {r['leaves_at'][0]:.1f}, {r['leaves_at'][1]:.1f}; the highest cell on its way, by mean height: "
                    f"{r['over_mean_m']:.0f} m at {r['over_at'][0]:.1f}, {r['over_at'][1]:.1f}, handed to Drainage at {r['handed_m']:.0f} m")

    if settlements and demand_times == 1.0:
        what_the_ties_decide(e, settlements, say)
    return e, h, rows


def what_the_ties_decide(e, settlements, say=print):
    """Part 7: the outcomes with the ties settled at random `settlements` times, by the cells' mean heights, and as the
    engine settles them. Returns the summaries: {"engine": ..., "mean": ..., 1: ..., 2: ...}."""
    runs = {"engine": ref.summary(e if e.ties is None else e.settled(None)), "mean": ref.summary(e.settled("mean"))}
    for seed in range(1, settlements + 1):
        runs[seed] = ref.summary(e.settled(seed))
    drawn = [runs[seed] for seed in range(1, settlements + 1)]
    n = settlements
    say(f"\n7. What the ties decide: the engine's way of settling them, the cells' mean heights, and {n} settlements at random")
    near = lambda r: sum(v < ref.MOUTH_WITHIN_KM for v in r["mouth_km"].values())
    say(f"\nRiver mouths within {ref.MOUTH_WITHIN_KM:.0f} km, of {len(ref.GREAT_RIVERS)}: engine {near(runs['engine'])}; mean heights {near(runs['mean'])}; "
        f"at random {min(near(r) for r in drawn)} to {max(near(r) for r in drawn)}")
    say(f"{'':12s}{'engine':>8s}{'mean':>8s}{'at random: from':>18s}{'to':>7s}   within {ref.MOUTH_WITHIN_KM:.0f} km in")
    for name in ref.GREAT_RIVERS:
        ks = [r["mouth_km"][name] for r in drawn]
        k = sum(v < ref.MOUTH_WITHIN_KM for v in ks)
        say(f"{name:12s}{runs['engine']['mouth_km'][name]:8.0f}{runs['mean']['mouth_km'][name]:8.0f}{min(ks):18.0f}{max(ks):7.0f}   {k:2d} of {n}"
            + ("" if k in (0, n) else "   <- the ties decide"))
    ok = lambda name, r: within(ref.GAUGES[name][2], r["flow"][name])
    hits = lambda r: sum(ok(name, r) for name in ref.GAUGES)
    say(f"\nGauges within a factor of two, of {len(ref.GAUGES)}: engine {hits(runs['engine'])}; mean heights {hits(runs['mean'])}; "
        f"at random {min(hits(r) for r in drawn)} to {max(hits(r) for r in drawn)}")
    say(f"{'':12s}{'measured':>9s}{'engine':>8s}{'mean':>8s}{'at random: from':>18s}{'to':>7s}   within x2 in   | like for like: alike in, engine / measured from, to")
    for name in ref.GAUGES:
        fs = [r["flow"][name] for r in drawn]
        k = sum(ok(name, r) for r in drawn)
        ls = [r["like"][name] for r in drawn]
        alike = [x[1] for x in ls if x[0]]
        say(f"{name:12s}{ref.GAUGES[name][2]:9.0f}{runs['engine']['flow'][name]:8.0f}{runs['mean']['flow'][name]:8.0f}{min(fs):18.0f}{max(fs):7.0f}   "
            f"{k:2d} of {n}{'   <- the ties decide' if 0 < k < n else '':21s} | {len(alike):2d} of {n}"
            + (f"   {min(alike):.2f}  {max(alike):.2f}" if alike else ""))
    say(f"\nLike for like, all like basins together, the engine sheds of the measured depth: engine {runs['engine']['like_all']:.2f}; "
        f"mean heights {runs['mean']['like_all']:.2f}; at random {min(r['like_all'] for r in drawn):.2f} to {max(r['like_all'] for r in drawn):.2f}")
    for key, words, scale, digits in (("back_to_air", "Of the rain on land, back to the air", 1.0, 4), ("to_sea", "Rivers reaching the sea, thousand km3 a year", 1.0, 2),
                                      ("lakes_share", "Land under lakes, %", 100.0, 2)):
        say(f"{words}: engine {scale * runs['engine'][key]:.{digits}f}; mean heights {scale * runs['mean'][key]:.{digits}f}; "
            f"at random {scale * min(r[key] for r in drawn):.{digits}f} to {scale * max(r[key] for r in drawn):.{digits}f}")
    lake = lambda r: r["caspian"]
    words = lambda c: "no lake" if c is None else (f"overflows by {c['outflow_km3']:.2f} km3 a year" if c["overflows"] else "closed") + f", {c['area_km2'] / 1e6:.2f} million km2 at {c['level_m']:.0f} m"
    v = [r["volga"] for r in drawn]
    say(f"The Volga at Volgograd, like for like: engine: basin {runs['engine']['volga']['basin']:.0f}, rain {runs['engine']['volga']['rain']:.0f} mm, sheds "
        f"{runs['engine']['volga']['sheds']:.0f}; at random: alike in {sum(x['like'] for x in v)} of {n}, basin {min(x['basin'] for x in v):.0f} to "
        f"{max(x['basin'] for x in v):.0f}, rain {min(x['rain'] for x in v):.0f} to {max(x['rain'] for x in v):.0f}, sheds {min(x['sheds'] for x in v):.0f} to "
        f"{max(x['sheds'] for x in v):.0f}, back to the air {min(x['rain'] - x['sheds'] for x in v):.0f} to {max(x['rain'] - x['sheds'] for x in v):.0f}")
    there = [lake(r) for r in drawn if lake(r) is not None]
    say(f"The lake at the Caspian's place: engine: {words(lake(runs['engine']))}; mean heights: {words(lake(runs['mean']))}; at random: closed in "
        f"{sum(not c['overflows'] for c in there)} of {n}, " + (f"overflow up to {max(c['outflow_km3'] for c in there):.2f} km3 a year, "
        f"{min(c['area_km2'] for c in there) / 1e6:.2f} to {max(c['area_km2'] for c in there) / 1e6:.2f} million km2" if there else ""))
    return runs


def trace(river, level=7, valley_share=ref.VALLEY_SHARE, ties=None, say=print):
    e = ref.Earth(level, valley_share, ties)
    flood = ref.raw_flood()
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


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        sys.exit(__doc__)
    if not ref.available():
        sys.exit("the Earth reference data is not here: run python tools/fetch_reference_data.py")
    if "--trace" in args:
        river = option(args, "--trace", None, str)
        if river not in ref.GREAT_RIVERS:
            sys.exit(f"no great river named {river!r}: one of {', '.join(ref.GREAT_RIVERS)}")
        trace(river, option(args, "--level", 7, int), option(args, "--valley-share", ref.VALLEY_SHARE), ties_of(option(args, "--ties", None, str)))
        sys.exit(0)
    report(option(args, "--level", 7, int), option(args, "--valley-share", ref.VALLEY_SHARE), option(args, "--demand-times", 1.0),
           ties_of(option(args, "--ties", None, str)), option(args, "--settlements", 0, int))
