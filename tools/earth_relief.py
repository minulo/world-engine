"""What Earth's relief data can and cannot say about rivers, before any process of the engine has run.

    python tools/earth_relief.py [--level 7] [--valley-share 0.1]

The Earth tests put ETOPO5 on the mesh and ask Drainage and Hydrology for Earth's rivers and lakes
(python tools/earth_rivers.py). A river that goes astray there may be a fault of the processes, of the mesh, of
the way the relief was put on the mesh, or of the relief data. This tool measures the last three.

  1. How coarse the heights are, how many cells tie exactly with a neighbour on the mesh, and what settles the
     ties.
  2. The closed hollows of the data on their own grid of 5 minutes of arc (about 9 km), beside those of the mesh.
  3. Six narrows of great rivers: in the data, and on the mesh.
  4. Seas behind narrow straits, and the mesh's twelve largest lakes: whether the data cut them off as well.
  5. What the valley rule does on coasts (earth_reference.Earth): cells that hold a shore and a range.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402

SEAS = {"the Black Sea": (43.0, 34.0), "the Red Sea": (20.0, 38.5), "the Baltic": (58.0, 20.0), "the Caspian": ref.CASPIAN,
        "the Mediterranean": (35.0, 18.0), "Hudson Bay": (60.0, -85.0)}


def option(args, name, default, kind=float):
    return kind(args[args.index(name) + 1]) if name in args else default


def report(level=7, valley_share=ref.VALLEY_SHARE, say=print):
    e = ref.Earth(level, valley_share)
    m, area, land = e.mesh, e.area.astype(np.float64), e.land
    say(f"Earth's relief (ETOPO5) on {m.n} cells; valley floors at the lowest {valley_share:g} of each cell's land points")

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
    f = ref.raw_flood()
    r = ref.raw_hollows(f)
    say(f"the data: the ocean (water below 0 m joined to the open Pacific) covers {100 * r['ocean_share_of_planet']:.1f} % of the planet. Of all that is not "
        f"ocean, {100 * r['not_ocean']:.1f} % lies under water when every hollow of the data is full ({100 * r['not_ocean_60']:.1f} % between 60 south and "
        f"60 north); of the land above 0 m alone, {100 * r['land']:.1f} % ({100 * r['land_60']:.1f} %)")
    from worldengine.library import drainage as dr
    d = e.drainage
    label, table = d.fields["depression_id"].astype(np.int64), d.tables["hollows"]
    full_level = table["spill_m"][dr.top_hollows(table)[label]]
    under = land & (label > 0) & (e.ground < np.where(np.isnan(full_level), np.inf, full_level))
    mid = np.abs(m.lat) < 60.0
    say(f"the mesh: {100 * area[land].sum() / area.sum():.1f} % of the planet is not sea. Of it, {100 * area[under].sum() / area[land].sum():.1f} % lies under "
        f"water when every hollow is full ({100 * area[under & mid].sum() / area[land & mid].sum():.1f} % between 60 south and 60 north); "
        f"{100 * area[land & (label > 0)].sum() / area[land].sum():.1f} % drains into a closed hollow")

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
    for name, place in SEAS.items():
        x = ref.raw_at(f, *place)
        say(f"{name:18s} the data: {x['height']:6.0f} m, " + ("ocean" if x["ocean"] else f"cut off from the ocean: joined to it at {x['level']:.0f} m")
            + f"; the mesh: {'sea' if e.wet[e.cell(*place)] else 'not sea'}")
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
    say(f"of {s['coast_cells']} coastal land cells, {s['coast_low']} are handed to Drainage at 1 m or lower, and {s['coast_low_but_high']} of those have a mean "
        f"height above 300 m: cells that hold a shore and a range, handed in at the height of the shore. In all, {s['at_or_below_zero']} land cells "
        f"are handed in at 0 m or lower (the sea of the mesh stands at {e.sea_level:.1f} m).")
    return e, f


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        sys.exit(__doc__)
    if not ref.available():
        sys.exit("the Earth reference data is not here: run python tools/fetch_reference_data.py")
    report(option(args, "--level", 7, int), option(args, "--valley-share", ref.VALLEY_SHARE))
