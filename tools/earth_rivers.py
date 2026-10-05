"""Earth's great rivers and lakes as the engine's Drainage and Hydrology make them, beside the measured ones.

    python tools/earth_rivers.py [--level 7] [--valley-share 0.1] [--demand-times 1.0]

Earth's relief (ETOPO5) is put on the mesh, SeaLevel pours Earth's water on it, Drainage finds the ways down, and
Hydrology is handed Earth's measured rain (GPCP, 1979 to 2010) and warmth (CRU, 1961 to 1990). Nothing of the
engine's own climate enters: what is printed is how these two processes do when their inputs are the truth.

  1. Each great river at its last gauging station (Dai and Trenberth, Table 2): the flow measured and the flow
     the engine gives, and the reasons for the difference, taken apart:
       the land that drains to the gauge: on Earth; on the mesh as the water runs ("reaches": closed hollows
           upstream keep their water); and on the mesh if every hollow were full
       what that land sheds in a year: measured (the flow over the real basin), and the engine's over the land
           that reaches the gauge, with the rain on it and the air's demand for water
       what the lakes with an outlet on the way lose to the air
     so that the engine's flow = the land that reaches the gauge x what it sheds - what the lakes lose.
  2. Where each great river leaves the land on the mesh, against its real mouth.
  3. The largest lakes, with the model's books of each.
  4. The water of all the land.
  5. Narrows of six great rivers: how high the mesh's ground stands in the valley, against the level of the lake
     that the closed valley dams above it.

--valley-share   the share of a cell's land points that lie below the height Drainage is handed (the Earth tests
                 use 0.1; see earth_reference.Earth). The outcomes depend on it, and this option shows how.
--demand-times   a diagnosis, not a setting of the engine: the air's demand for water multiplied by this factor.
                 It shows how much of a miss follows from the demand.

The Earth tests (tests/test_earth.py) state the misses printed here as expected failures, one by one.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                            # noqa: E402

TWICE = 2.0                 # the Earth tests ask for the measured flow within this factor


def option(args, name, default, kind=float):
    return kind(args[args.index(name) + 1]) if name in args else default


def report(level=7, valley_share=ref.VALLEY_SHARE, demand_times=1.0, say=print):
    e = ref.Earth(level, valley_share)
    constants = None
    if demand_times != 1.0:
        extra = e.h.params["models"]["slots"]["Hydrology"]["constants"]["demand"]["priestley_taylor_extra"]
        constants = {"demand": {"priestley_taylor_extra": (1.0 + extra) * demand_times - 1.0}}
    h = e.hydrology(constants)
    m, area, land = e.mesh, e.area.astype(np.float64), e.land
    flow = e.yearly_flow(h)
    say(f"Earth on {m.n} cells; valley floors at the lowest {valley_share:g} of each cell's land points"
        + ("" if demand_times == 1.0 else f"; the demand for water multiplied by {demand_times:g} (a diagnosis)"))

    say("\n1. Great rivers at their last gauging stations (flows in km3 a year, areas in thousand km2, depths in mm a year)")
    say(f"{'':12s}{'flow':>19s}{'':11s} | {'land that drains to the gauge':>30s}   | {'what that land sheds':>20s}{'':14s} | lakes on the")
    say(f"{'':12s}{'measured':>9s}{'engine':>8s}  {'within x2':10s} | {'real':>8s}{'reaches':>9s}{'all hollows full':>18s} |"
        f"{'measured':>9s}{'engine':>8s}{'rain':>7s}{'demand':>8s} | way lose")
    rows = ref.rivers_at_gauges(e, h)
    hit = 0
    for name, r in rows.items():
        ok = r["measured"] / TWICE < r["flow"] < r["measured"] * TWICE
        hit += ok
        say(f"{name:12s}{r['measured']:9.0f}{r['flow']:8.0f}  {'yes' if ok else 'NO':10s} | {r['station_area']:8.0f}{r['reaches']:9.0f}"
            f"{r['basin']:18.0f} |{r['measured_depth']:9.0f}{r['sheds']:8.0f}{r['rain']:7.0f}{r['demand']:8.0f} | {r['lost_in_lakes']:8.0f}")
    say(f"within a factor of two of the measured flow: {hit} of {len(rows)}")

    say("\n2. Where each great river leaves the land with every hollow full, against its real mouth")
    basin = e.drainage.fields["basin_id"]
    for name, (place, mouth) in ref.GREAT_RIVERS.items():
        end = int(basin[e.cell(*place)])
        say(f"{name:12s}{e.km(end, *mouth):7.0f} km from its mouth, at {m.lat[end]:6.1f}, {m.lon[end]:7.1f}")

    say("\n3. The largest lakes (km2; m; km3 a year)")
    lakes = h.tables["lakes"]
    say(f"{'area':>12s}{'level':>7s}  {'outlet':6s}{'reaches it':>11s}{'extra loss':>11s}{'runs on':>9s}{'rain on it':>11s}{'evaporates':>11s}   lowest point at")
    for i in np.argsort(-lakes["area_m2"])[:12]:
        b = int(lakes["bottom_cell"][i])
        say(f"{lakes['area_m2'][i] / 1e6:12,.0f}{lakes['level_m'][i]:7.0f}  {'yes' if lakes['overflows'][i] else 'no':6s}"
            f"{lakes['inflow_m3_per_year'][i] / 1e9:11.0f}{lakes['loss_to_air_m3_per_year'][i] / 1e9:11.0f}"
            f"{lakes['outflow_m3_per_year'][i] / 1e9:9.0f}{lakes['rain_on_lake_m3_per_year'][i] / 1e9:11.0f}"
            f"{lakes['evaporation_m3_per_year'][i] / 1e9:11.0f}   {m.lat[b]:6.1f}, {m.lon[b]:7.1f}")

    say("\n4. The water of all the land (thousand km3 a year)")
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
        say(f"land whose water reaches the sea as the water runs: {100 * area[land & e.wet[ends]].sum() / area[land].sum():.1f} %; "
            f"land that drains into a closed hollow (depression_id above 0): "
            f"{100 * area[land & (books['label'] > 0)].sum() / area[land].sum():.1f} %")
    say(f"the air's demand for water over land {(asked * area)[land].sum() / area[land].sum():.0f} mm a year; rain "
        f"{1e15 * fell / area[land].sum():.0f} mm; lakes cover {100 * flooded:.2f} % of the land: {len(lakes['hollow'])} lakes, "
        f"{int(lakes['overflows'].sum())} with an outlet")
    if demand_times == 1.0:
        say("\n5. Narrows that the mesh closes (the lowest way through the valley, on the heights Drainage was handed)")
        for name, r in ref.narrows(e).items():
            lake = ("no lake stands above it" if r["lake_level_m"] is None else
                    f"the lake above it stands at {r['lake_level_m']:.0f} m and " + ("overflows by another way" if r["lake_overflows"] else "keeps its water"))
            say(f"{name:12s} the valley rises to {r['barrier_m']:.0f} m, at {r['barrier_at'][0]:.1f}, {r['barrier_at'][1]:.1f}; {lake}")
    return e, h, rows


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        sys.exit(__doc__)
    if not ref.available():
        sys.exit("the Earth reference data is not here: run python tools/fetch_reference_data.py")
    report(option(args, "--level", 7, int), option(args, "--valley-share", ref.VALLEY_SHARE), option(args, "--demand-times", 1.0))
