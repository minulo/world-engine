"""Print the numbers by which a built world is judged: land and sea, temperature, wind, rain, classes.

A development tool. It reads a world store and changes nothing.
    python tools/world_report.py STORE
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine import console                          # noqa: E402
from worldengine.library import drainage as dr           # noqa: E402
from worldengine.library import operators as op          # noqa: E402
from worldengine.mesh import get_mesh                    # noqa: E402
from worldengine.store import StoreView, WorldView       # noqa: E402


def report(world, say=print):
    """Print the report. `world` is the path of a world store, or a view of a world (worldengine.store)."""
    v = world if isinstance(world, WorldView) else StoreView(world)
    meta = v.attrs["meta"]
    m = get_mesh(meta["mesh_level"])
    f = {n: v.field(n) for n in v.field_names()}
    area = f["cell_area"]
    total = area.sum()
    wet = f["ocean_mask"]
    land = ~wet
    share = lambda mask: float((area * mask).sum() / total)
    mean = lambda x, mask=None: float((x * area * (1 if mask is None else mask)).sum() / (area * (1 if mask is None else mask)).sum())
    say(f"world: {meta['cells']} cells, profile {meta['profile']}, seed {meta['seed']}, {meta['build_seconds']:.0f} s, "
          f"climate rounds {meta['rounds_used'].get('climate')}, settled {meta['settled'].get('climate')}")
    say(f"notices: {v.attrs['notices'] or 'none'}")
    h = f["height_above_sea"]
    say(f"land share {share(land):.3f}; mean sea depth {mean(f['sea_depth'], wet):.0f} m; mean land height {mean(h, land):.0f} m; "
          f"highest {h.max():.0f} m; land below sea level {share(land & (h < 0)) / share(land):.3f} of land; "
          f"sea level {v.table('seas')['surface_m'][0]:.0f} m; bodies of water {len(v.table('seas')['surface_m'])}")
    if "surface_temperature" not in f:
        return
    t = f["surface_temperature"].astype(np.float64) - 273.15
    yearly = t.mean(axis=0)
    swing = (t.max(axis=0) - t.min(axis=0)) / 2
    mid = (np.abs(m.lat) > 40) & (np.abs(m.lat) < 60)
    say(f"temperature: global mean {mean(yearly):.1f} C; north pole {yearly[0]:.1f}, south pole {yearly[11]:.1f}; "
          f"equator (within 5 degrees) {mean(yearly, np.abs(m.lat) < 5):.1f}")
    say(f"  half the yearly swing at 40-60 degrees: land {mean(swing, mid & land):.1f}, sea {mean(swing, mid & wet):.1f}; largest {swing.max():.1f}")
    say(f"  mean albedo {mean(f['albedo'].astype(np.float64).mean(axis=0)):.3f}")
    white = v.driver("albedo", "from_snow_and_ice").astype(np.float64) > 0.05
    say(f"  land under snow in every month {share(land & white.all(axis=0)) / share(land):.2f} of land, in some month "
          f"{share(land & white.any(axis=0)) / share(land):.2f}; land whose warmest month is below freezing "
          f"{share(land & (t.max(axis=0) < 0)) / share(land):.2f}; sea under ice {share(wet & white.all(axis=0)) / share(wet):.3f} of the sea")
    by_band = lambda lo, hi: mean(swing, land & (np.abs(m.lat) >= lo) & (np.abs(m.lat) < hi))
    say(f"  half the yearly swing over land by latitude: 20-40 {by_band(20, 40):.1f}, 40-50 {by_band(40, 50):.1f}, "
          f"50-60 {by_band(50, 60):.1f}, 60-70 {by_band(60, 70):.1f}")
    east, north = op.to_east_north(m, f["wind"].astype(np.float64).mean(axis=0))
    lat, u = op.zonal_mean(m, east, 10.0)
    _, vv = op.zonal_mean(m, north, 10.0)
    say(f"wind toward the east by band, south to north: {u.round(1)}")
    say(f"wind toward the north by band: {vv.round(1)}")
    rain = f["precipitation"].astype(np.float64).sum(axis=0)
    evap = f["ocean_evaporation"].astype(np.float64).sum(axis=0)
    from_land = f["evapotranspiration"].astype(np.float64).sum(axis=0) if "evapotranspiration" in f else np.zeros(m.n)
    say(f"rain: global {mean(rain):.0f} mm/yr; land {mean(rain, land):.0f}; sea {mean(rain, wet):.0f}; "
          f"evaporation (sea and land) over rain {(mean(evap) + mean(from_land)) / mean(rain):.6f}")
    lat5, lr = op.zonal_mean(m, rain, 5.0, mask=land.astype(np.float64))
    _, ar = op.zonal_mean(m, rain, 5.0)
    for sign, name in ((1, "north"), (-1, "south")):
        side = (sign * lat5 > 0) & (sign * lat5 < 60) & ~np.isnan(lr)
        belt = side & (sign * lat5 < 50)
        storm = lr[(sign * lat5 > 40) & (sign * lat5 < 55)].mean()
        say(f"  driest land band, {name}: {sign * lat5[side][np.argmin(lr[side])]:.0f} degrees, {lr[side].min():.0f} mm/yr; equatorward of 50: "
              f"{sign * lat5[belt][np.argmin(lr[belt])]:.0f} degrees, {lr[belt].min():.0f} mm/yr; land of the storm belt at 40 to 55: {storm:.0f} mm/yr")
    lifted = v.driver("precipitation", "from_rising_ground").astype(np.float64).sum(axis=0)
    say(f"  wettest cell {rain.max():.0f} mm/yr ({'land' if land[np.argmax(rain)] else 'sea'}); wettest land cell {rain[land].max():.0f}; "
          f"rain of rising ground: {mean(lifted, land):.0f} mm/yr over land, {(lifted * area).sum() / (rain * area).sum():.3f} of all rain")
    lat10, a10 = op.zonal_mean(m, rain, 10.0)
    say(f"  rain by 10-degree band, south to north: {a10.round(0)}")
    say(f"  wettest 10-degree band {a10.max():.0f} mm/yr; land under 250 mm: {share(land & (rain < 250)) / share(land):.2f} of land; "
          f"land over 1500 mm: {share(land & (rain > 1500)) / share(land):.2f}")
    names = v.specs["biome"]["categories"]
    b = np.bincount(f["biome"], weights=area, minlength=len(names)) / total
    shares = {n: round(float(s), 3) for n, s in zip(names, b) if s > 0}
    say(f"biomes, share of the surface: {shares}")
    say(f"  sea under ice: {share(wet & (f['biome'] == names.index('ice'))):.3f} of the surface")
    kn = v.specs["climate_class"]["categories"]
    k = np.bincount(f["climate_class"], weights=area * land, minlength=len(kn)) / (area * land).sum()
    groups = {}
    for n, s in zip(kn, k):
        if n != "ocean":
            groups[n[0] if n[0] != "B" else n[:2]] = groups.get(n[0] if n[0] != "B" else n[:2], 0.0) + float(s)
    shares = {g: round(s, 3) for g, s in sorted(groups.items())}
    say(f"climate classes, share of the land: {shares}")
    if "river_discharge" in f:
        water(v, m, f, area, land, wet, rain, from_land, mean, share, say)
    long = {key: round(val, 1) for key, val in v.attrs["timings"].items() if val > 1}
    say(f"timings (s): {long}")


def water(v, m, f, area, land, wet, rain, from_land, mean, share, say=print):
    """Water on land (build step 2): what falls, what goes back to the air, what the rivers carry, the lakes, the snow."""
    year_s = v.attrs["planet"]["year_length_s"]
    demand = np.nansum(f["potential_evapotranspiration"].astype(np.float64), axis=0)
    shed = f["runoff_annual"].astype(np.float64)
    say(f"water on land, mm/yr: rain {mean(rain, land):.0f}; back to the air {mean(from_land, land):.0f} ({mean(from_land, land) / mean(rain, land):.3f} of the rain); "
          f"the air's demand {mean(demand, land):.0f}; runoff {mean(shed, land):.0f}")
    river = f["river_discharge"].astype(np.float64).mean(axis=0)
    to_sea = river[wet].sum() * year_s
    kept = ((rain - from_land) * area)[land].sum() / 1000.0
    say(f"  rivers reaching the sea {to_sea / 1e12:.1f} thousand km3 a year; rain less evaporation over land {kept / 1e12:.1f}; ratio {to_sea / kept:.6f}")
    recv = f["flow_receiver"]
    coast = np.flatnonzero(land & (recv >= 0) & wet[np.maximum(recv, 0)])
    top = coast[np.argsort(-river[coast])[:5]]
    say(f"  largest rivers at the coast (m3/s at lat, lon): {[(int(river[c]), round(float(m.lat[c]), 1), round(float(m.lon[c]), 1)) for c in top]}")
    hollows, lakes = v.table("hollows"), v.table("lakes")
    in_hollow = f["depression_id"] > 0
    say(f"  closed hollows: {int((hollows['first_child'][1:] < 0).sum())} with one bottom, {int((hollows['first_child'] >= 0).sum())} made of two; "
          f"{share(land & in_hollow) / share(land):.3f} of the land drains into one")
    elevation = f["elevation"].astype(np.float64)
    surface = dr.drainage_surface(elevation, f["sea_depth"], wet, v.table("seas")["surface_m"])
    t = dr.count_ties(surface, wet, m.nbr, elevation, dr.mesh_ties(m))
    say(f"  exact ties: of {t['choose']} land cells with a lower neighbour, {t['tied']} have several equally low: the lower bed settles {t['by_bed']}, "
          f"the wider way {t['by_width']}, the cell numbers {t['by_number']}; {t['level']} land cells lie on level ground")
    flooded = f["lake_fraction"].astype(np.float64)
    order = np.argsort(-lakes["area_m2"])[:5]
    say(f"  lakes: {len(lakes['hollow'])}, of which {int(lakes['overflows'].sum())} overflow; {(flooded * area).sum() / (area * land).sum():.3f} of the land under water; "
          f"largest (km2): {[int(a / 1e6) for a in lakes['area_m2'][order]]}; closed lakes take {lakes['loss_to_air_m3_per_year'][~lakes['overflows']].sum() / 1e12:.2f} thousand km3 a year")
    basins = np.unique(f["basin_id"][land])
    sizes = np.sort(f["drainage_area"][basins])[::-1]
    say(f"  river basins with every hollow full: {basins.size}; the largest drains {sizes[0] / (area * land).sum():.3f} of the land")
    snow = f["snow_water"].astype(np.float64)
    say(f"  snow: on the ground all year on {share(land & (snow.min(axis=0) > 0)) / share(land):.3f} of the land, in some month on "
          f"{share(land & (snow.max(axis=0) > 0)) / share(land):.3f}; deepest store of a cell that loses its snow {snow[:, snow.min(axis=0) == 0].max():.0f} mm")
    moisture = f["soil_moisture"].astype(np.float64)
    say(f"  soil: {np.nanmean(moisture[:, land]):.2f} full on average; rounds {v.attrs['meta']['rounds_used'].get('climate')}")
    lat10, land_rain = op.zonal_mean(m, rain, 10.0, mask=land.astype(np.float64))
    _, land_air = op.zonal_mean(m, from_land, 10.0, mask=land.astype(np.float64))
    say(f"  land rain by 10-degree band, south to north: {np.nan_to_num(land_rain).round(0)}")
    say(f"  land evaporation by 10-degree band:         {np.nan_to_num(land_air).round(0)}")


def parser():
    p = console.tool_parser(__doc__, "python tools/world_report.py")
    p.add_argument("store", metavar="STORE")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not Path(args.store).exists():
        print(f"no world store at {args.store}", file=sys.stderr)
        return 2
    report(args.store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
