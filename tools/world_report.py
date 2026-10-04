"""Print the numbers by which a built world is judged: land and sea, temperature, wind, rain, classes.

A development tool. It reads a world store and changes nothing.
    python tools/world_report.py STORE
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine.library import operators as op          # noqa: E402
from worldengine.mesh import get_mesh                    # noqa: E402
from worldengine.store import StoreView                  # noqa: E402


def main(path):
    v = StoreView(path)
    meta = v.attrs["meta"]
    m = get_mesh(meta["mesh_level"])
    f = {n: v.field(n) for n in v.field_names()}
    area = f["cell_area"]
    total = area.sum()
    wet = f["ocean_mask"]
    land = ~wet
    share = lambda mask: float((area * mask).sum() / total)
    mean = lambda x, mask=None: float((x * area * (1 if mask is None else mask)).sum() / (area * (1 if mask is None else mask)).sum())
    print(f"world: {meta['cells']} cells, profile {meta['profile']}, seed {meta['seed']}, {meta['build_seconds']:.0f} s, "
          f"climate rounds {meta['rounds_used'].get('climate')}, settled {meta['settled'].get('climate')}")
    print(f"notices: {v.attrs['notices'] or 'none'}")
    h = f["height_above_sea"]
    print(f"land share {share(land):.3f}; mean sea depth {mean(f['sea_depth'], wet):.0f} m; mean land height {mean(h, land):.0f} m; "
          f"highest {h.max():.0f} m; land below sea level {share(land & (h < 0)) / share(land):.3f} of land; "
          f"sea level {v.table('seas')['surface_m'][0]:.0f} m; bodies of water {len(v.table('seas')['surface_m'])}")
    if "surface_temperature" not in f:
        return
    t = f["surface_temperature"].astype(np.float64) - 273.15
    yearly = t.mean(axis=0)
    swing = (t.max(axis=0) - t.min(axis=0)) / 2
    mid = (np.abs(m.lat) > 40) & (np.abs(m.lat) < 60)
    print(f"temperature: global mean {mean(yearly):.1f} C; north pole {yearly[0]:.1f}, south pole {yearly[11]:.1f}; "
          f"equator (within 5 degrees) {mean(yearly, np.abs(m.lat) < 5):.1f}")
    print(f"  half the yearly swing at 40-60 degrees: land {mean(swing, mid & land):.1f}, sea {mean(swing, mid & wet):.1f}; largest {swing.max():.1f}")
    print(f"  mean albedo {mean(f['albedo'].astype(np.float64).mean(axis=0)):.3f}")
    east, north = op.to_east_north(m, f["wind"].astype(np.float64).mean(axis=0))
    lat, u = op.zonal_mean(m, east, 10.0)
    _, vv = op.zonal_mean(m, north, 10.0)
    print("wind toward the east by band, south to north:", u.round(1))
    print("wind toward the north by band:", vv.round(1))
    rain = f["precipitation"].astype(np.float64).sum(axis=0)
    evap = f["ocean_evaporation"].astype(np.float64).sum(axis=0)
    print(f"rain: global {mean(rain):.0f} mm/yr; land {mean(rain, land):.0f}; sea {mean(rain, wet):.0f}; evaporation over rain {mean(evap) / mean(rain):.6f}")
    lat5, lr = op.zonal_mean(m, rain, 5.0, mask=land.astype(np.float64))
    _, ar = op.zonal_mean(m, rain, 5.0)
    for sign, name in ((1, "north"), (-1, "south")):
        side = (sign * lat5 > 0) & (sign * lat5 < 60) & ~np.isnan(lr)
        print(f"  driest land band, {name}: {sign * lat5[side][np.argmin(lr[side])]:.0f} degrees, {lr[side].min():.0f} mm/yr")
    lat10, a10 = op.zonal_mean(m, rain, 10.0)
    print("  rain by 10-degree band, south to north:", a10.round(0))
    print(f"  wettest 10-degree band {a10.max():.0f} mm/yr; land under 250 mm: {share(land & (rain < 250)) / share(land):.2f} of land; "
          f"land over 1500 mm: {share(land & (rain > 1500)) / share(land):.2f}")
    names = v.specs["biome"]["categories"]
    b = np.bincount(f["biome"], weights=area, minlength=len(names)) / total
    print("biomes, share of the surface:", {n: round(float(s), 3) for n, s in zip(names, b) if s > 0})
    print(f"  sea frozen all year: {share(wet & (f['biome'] == names.index('ice'))):.3f} of the surface")
    kn = v.specs["climate_class"]["categories"]
    k = np.bincount(f["climate_class"], weights=area * land, minlength=len(kn)) / (area * land).sum()
    groups = {}
    for n, s in zip(kn, k):
        if n != "ocean":
            groups[n[0] if n[0] != "B" else n[:2]] = groups.get(n[0] if n[0] != "B" else n[:2], 0.0) + float(s)
    print("climate classes, share of the land:", {g: round(s, 3) for g, s in sorted(groups.items())})
    print("timings (s):", {key: round(val, 1) for key, val in v.attrs["timings"].items() if val > 1})


if __name__ == "__main__":
    main(sys.argv[1])
