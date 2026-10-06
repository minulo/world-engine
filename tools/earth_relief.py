"""What Earth's relief data can and cannot say about rivers, before any process of the engine has run.

    python tools/earth_relief.py [--level 7] [--valley-share 0.1] [--sea-water relief|planet]

The Earth tests put ETOPO5 on the mesh and ask Drainage and Hydrology for Earth's rivers and lakes
(python tools/earth_rivers.py). A river that goes astray there may be a fault of the processes, of the mesh, of
the way the relief was put on the mesh, or of the relief data. This tool measures the last three.

  1. How coarse the heights are, how many cells tie exactly with a neighbour on the mesh, and what settles the
     ties.
  2. The closed hollows of the data on their own grid of 5 minutes of arc (about 9 km), beside those of the mesh.
  3. Six narrows of great rivers: in the data, and on the mesh.
  4. Seas behind narrow straits, and the mesh's twelve largest lakes: whether the data cut them off as well.
  5. What the valley rule does on coasts (earth_reference.Earth): cells that hold a shore and a range; and, as a
     diagnosis, what would change if the sea in a cell were counted (earth_reference.other_valley_reading).

--sea-water chooses the volume of water that SeaLevel pours on the relief: "relief" (the default: what the ocean of
the data holds) or "planet" (the planet file's). The first line of the report gives both volumes and where the sea
of the mesh comes to rest.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402
from worldengine import console                          # noqa: E402

SEAS = {"the Black Sea": (43.0, 34.0), "the Red Sea": (20.0, 38.5), "the Baltic": (58.0, 20.0), "the Caspian": ref.CASPIAN,
        "the Mediterranean": (35.0, 18.0), "Hudson Bay": (60.0, -85.0)}


def report(level=7, valley_share=ref.VALLEY_SHARE, say=print, earth=None, flood=None, sea_water=ref.SEA_WATER):
    """The report. `earth` is an Earth built already (its level, valley share and sea water then stand), `flood` the
    data's own hollows worked out already (earth_reference.raw_flood)."""
    e = earth if earth is not None else ref.Earth(level, valley_share, None, sea_water)
    valley_share = e.valley_share
    m = e.mesh
    say(f"Earth's relief (ETOPO5) on {m.n} cells; valley floors at the lowest {valley_share:g} of each cell's land points")
    own, planet = ref.relief_sea_volume(), float(e.h.params["planet"]["surface_water_volume_m3"])
    say(f"the ocean of the data holds {own:.5e} m3 of water below 0 m; the planet file has {planet:.5e} m3, {100 * (1 - planet / own):.2f} % less. "
        f"Poured here: {'the first' if e.sea_water == 'relief' else 'the second'}; the sea of the mesh comes to rest at {e.sea_level:+.1f} m and covers "
        f"{100 * e.area[e.wet].sum() / e.area.sum():.2f} % of the planet, with {int(e.land.sum())} land cells")

    say("\n1. How coarse the heights are, and how often they tie")
    s = ref.relief_steps(e)
    say(f"every height of the data is a whole number of metres: {'yes' if s['whole_metres'] else 'no'}; of its land (by area), "
        f"{100 * s['hundred_feet_share']:.0f} % lies within half a metre of a whole number of hundreds of feet")
    say(f"on the mesh, of {s['land_cells']} land cells {s['tied_cells']} ({100 * s['tied_cells'] / s['land_cells']:.1f} %) have a land neighbour at exactly "
        f"their own height; the commonest heights handed to Drainage: " + ", ".join(f"{h:.0f} m ({c} cells)" for h, c in s["commonest"]))
    t = ref.tie_counts(e)
    say(f"of {t['choose']} land cells with a lower neighbour, {t['tied']} ({100 * t['tied'] / t['choose']:.1f} %) have several equally low: the lower bed "
        f"settles {t['by_bed']}, the wider way {t['by_width']}, the cell numbers {t['by_number']}; another {t['level']} land cells "
        f"({100 * t['level'] / s['land_cells']:.1f} %) lie on level ground")
    say(f"with every hollow full, the water of {100 * t['mouth_moved_by_numbers']:.2f} % of the land's area reaches the sea in another cell when the order "
        f"of the cells is turned round, and of {100 * t['mouth_moved_by_width']:.1f} % when the wider way is left out and the cell numbers settle the ties")

    say("\n2. The closed hollows of the data on their own grid, and of the mesh")
    f = flood if flood is not None else ref.raw_flood()
    r = ref.raw_hollows(f)
    say(f"the data: the ocean (water below 0 m joined to the open Pacific) covers {100 * r['ocean_share_of_planet']:.1f} % of the planet. Of all that is not "
        f"ocean, {100 * r['not_ocean']:.1f} % lies under water when every hollow of the data is full ({100 * r['not_ocean_60']:.1f} % between 60 south and "
        f"60 north); of the land above 0 m alone, {100 * r['land']:.1f} % ({100 * r['land_60']:.1f} %)")
    h = ref.mesh_hollows(e)
    say(f"the mesh: {100 * h['not_sea_share']:.1f} % of the planet is not sea. Of it, {100 * h['under_share']:.1f} % lies under "
        f"water when every hollow is full ({100 * h['under_share_60']:.1f} % between 60 south and 60 north); "
        f"{100 * h['closed_hollow_share']:.1f} % drains into a closed hollow")

    say("\n3. Narrows of six great rivers: in the data (5 minutes of arc), and on the mesh")
    say(f"{'':12s}{'the data: the river stands at':>30s}{'its valley rises to':>21s}{'joined to the ocean at':>24s} | {'the mesh: the valley rises to':>30s}{'the lake above stands at':>26s}")
    raw, on_mesh = ref.raw_narrows(f), ref.narrows(e)
    for name in ref.NARROWS:
        a, b = raw[name], on_mesh[name]
        open_sea = not np.isfinite(a["to_ocean_m"])
        say(f"{name:12s}{a['start_m']:28.0f} m" + (f"{'open to the sea':>21s}{'':24s}" if open_sea else f"{a['barrier_m']:19.0f} m{a['to_ocean_m']:22.0f} m")
            + f" | {b['barrier_m']:28.0f} m" + ("" if b["lake_level_m"] is None else f"{b['lake_level_m']:24.0f} m"))
    closed = [name for name in ref.NARROWS if np.isfinite(raw[name]["to_ocean_m"]) and raw[name]["barrier_m"] > raw[name]["start_m"]]
    say(f"closed in the data themselves: {len(closed)} of {len(ref.NARROWS)} ({', '.join(closed)})")

    say("\n4. Seas behind straits, and the mesh's largest lakes: what the data make of each place")
    held = ref.data_points_of_cells(e, f)
    for name, place in SEAS.items():
        x = ref.raw_at(f, *place)
        say(f"{name:18s} the data: {x['height']:6.0f} m, " + ("ocean" if x["ocean"] else f"cut off from the ocean: joined to it at {x['level']:.0f} m")
            + f"; the mesh: {'sea' if e.wet[e.cell(*place)] else 'not sea'}")
        if x["ocean"] and not e.wet[e.cell(*place)]:         # the data join it to the ocean and the mesh does not: what stands between
            k = ref.kept_apart(e, f, place)
            say(f"{'':18s} kept apart from the mesh's sea by the cell at {k['lat']:.1f}, {k['lon']:.1f}: {100 * k['ocean_share']:.0f} % of its points are ocean in "
                f"the data, its mean height is {k['mean_m']:+.1f} m (the sea of the mesh stands at {e.sea_level:+.1f} m), and it is handed to Drainage at {k['handed_m']:.0f} m")
        lake = None if e.wet[e.cell(*place)] else ref.lake_books(e, place)
        if lake is not None and lake["outlet_cell"] >= 0:
            c = lake["outlet_cell"]
            say(f"{'':18s} under Earth's rain a lake of {lake['area_km2']:,.0f} km2 stands there at {lake['level_m']:.0f} m. It leaves through the cell at {m.lat[c]:.1f}, "
                f"{m.lon[c]:.1f}: {100 * held['ocean_share'][c]:.0f} % of its points are ocean in the data, its mean height is {e.mean[c]:+.1f} m, and it is handed to "
                f"Drainage at {e.ground[c]:.0f} m")
    lakes = e.hydrology().tables["lakes"]
    say("the mesh's lakes larger than 100,000 km2 (under Earth's rain and warmth), at the lowest point of each:")
    held = 0
    big = [i for i in np.argsort(-lakes["area_m2"]) if lakes["area_m2"][i] > 1.0e11]
    for i in big:
        c = int(lakes["bottom_cell"][i])
        x = ref.raw_at(f, float(m.lat[c]), float(m.lon[c]))
        hollow = (not x["ocean"]) and x["level"] > x["height"]
        held += hollow
        say(f"   {lakes['area_m2'][i] / 1e6:10,.0f} km2 at {lakes['level_m'][i]:5.0f} m, lowest point {m.lat[c]:6.1f}, {m.lon[c]:7.1f}: the data there {x['height']:6.0f} m, "
            + ("ocean" if x["ocean"] else f"joined to the ocean at {x['level']:.0f} m" + (": a closed hollow of the data" if hollow else ": no hollow in the data")))
    say(f"of these {len(big)} lakes, {held} lie in hollows that the data hold on their own grid")

    say("\n5. The valley rule on coasts")
    say(f"of {s['coast_cells']} coastal land cells, {s['coast_low']} are handed to Drainage no more than {ref.COAST_LOW_M:g} m above the sea of the mesh "
        f"(which stands at {e.sea_level:+.1f} m), and {s['coast_low_but_high']} of those have a mean height above 300 m: cells that hold a shore and a range, "
        f"handed in at the height of the shore. In all, {s['at_or_below_sea']} land cells are handed in at or below the level of that sea: dry ground "
        f"that the sea does not reach.")
    o = ref.other_valley_reading(e, f)
    b, c = o["built"], o["other"]
    say(f"A diagnosis, not the rule of the tests: the valley rule leaves out the sea in a cell. With the ocean's points of each cell counted as well, at the "
        f"level of the mesh's sea, {o['changed']} land cells are handed in at another height, {o['at_sea']} of them at the sea's own level. Great rivers that "
        f"leave the land within {ref.MOUTH_WITHIN_KM:g} km of their mouths: {c['mouths']}, for {b['mouths']} as built; gauges within a factor of two: "
        f"{c['gauges']} for {b['gauges']}; lakes on {100 * c['lakes_share']:.2f} % of the land for {100 * b['lakes_share']:.2f} %. Mouths that move by more than 5 km: "
        + "; ".join(f"{river} {then:.0f} to {now:.0f} km" for river, (then, now) in o["moved"].items()))
    return e, f


def parser():
    p = console.tool_parser(__doc__, "python tools/earth_relief.py")
    p.add_argument("--level", type=console.whole_number(3, 8), default=7, metavar="LEVEL")
    p.add_argument("--valley-share", type=console.number_between(0.0, 1.0, open_low=True), default=ref.VALLEY_SHARE, metavar="SHARE")
    p.add_argument("--sea-water", choices=("relief", "planet"), default=ref.SEA_WATER)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not ref.available():
        print("the Earth reference data is not here: run python tools/fetch_reference_data.py", file=sys.stderr)
        return 1
    report(args.level, args.valley_share, sea_water=args.sea_water)
    return 0


if __name__ == "__main__":
    sys.exit(main())
