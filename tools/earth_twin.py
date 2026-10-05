"""The Earth twin: the engine run on Earth's own relief, and its result held against Earth.

    python tools/earth_twin.py [--profile preview|standard] [--out worlds/earth_twin.zarr]
    python tools/earth_twin.py --compare worlds/earth_twin.zarr          compare a twin built earlier

The Isostasy slot is filled by a process that reads the mean height of ETOPO5 over each cell; everything after it
(the sea, the climate, the water on land, the biomes) is the engine's own. The comparison prints the twin's numbers
beside Earth's: temperature from the Climatic Research Unit's means of 1961 to 1990, rain from GPCP 1979 to 2010,
both read off at the cell centres. It needs the reference data (tools/fetch_reference_data.py).

A twin is not a test that passes or fails. It shows where the engine's climate departs from the one planet whose
climate is known, on relief it did not make.
"""
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldengine import reference as ref                 # noqa: E402
from worldengine import store                            # noqa: E402
from worldengine.engine import Engine                    # noqa: E402
from worldengine.library import operators as op          # noqa: E402
from worldengine.mesh import get_mesh                    # noqa: E402

DATA = ROOT / "data"
YEAR_S = 31558150.0
PEEL = {"A": 19.0, "B": 30.2, "C": 13.4, "D": 24.6, "E": 12.8}     # shares of the land, Peel, Finlayson and McMahon 2007


def build(profile: str, out: str):
    level = yaml.safe_load((DATA / "profiles.yaml").read_text())["profiles"][profile]["mesh_level"]
    models = ref.earth_twin_models(yaml.safe_load((DATA / "models.yaml").read_text()), get_mesh(level))
    engine = Engine(DATA, profile=profile, overrides={"models": models}, log=print)
    world = engine.build()
    store.save(world, engine, out)
    print(f"the Earth twin is in {out}")
    return out


def compare(path):
    v = store.StoreView(path)
    meta = v.attrs["meta"]
    m = get_mesh(meta["mesh_level"])
    f = {n: v.field(n) for n in v.field_names()}
    area = f["cell_area"].astype(np.float64)
    wet = f["ocean_mask"]
    land = ~wet
    mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
    everywhere = np.ones(m.n, dtype=bool)
    t_earth = ref.at_cell_centres(m, *ref.temperature_monthly())
    p_earth = ref.at_cell_centres(m, *ref.rain_monthly())
    t = f["surface_temperature"].astype(np.float64) - 273.15
    p = f["precipitation"].astype(np.float64)
    rows = []
    add = lambda what, twin, earth, unit="": rows.append((what, twin, earth, unit))
    add("sea level against Earth's", float(v.table("seas")["surface_m"][0]), 0.0, "m")
    add("share of the planet under sea", 100 * area[wet].sum() / area.sum(), 70.8, "%")
    add("mean temperature of the year", mean(t.mean(axis=0), everywhere), mean(t_earth.mean(axis=0), everywhere), "C")
    add("  over land", mean(t.mean(axis=0), land), mean(t_earth.mean(axis=0), land), "C")
    add("  over sea", mean(t.mean(axis=0), wet), mean(t_earth.mean(axis=0), wet), "C")
    for lo, hi in ((-90, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 90)):
        band = (m.lat >= lo) & (m.lat < hi)
        add(f"  between {lo} and {hi} degrees", mean(t.mean(axis=0), band), mean(t_earth.mean(axis=0), band), "C")
    north_land = land & (m.lat > 40) & (m.lat < 60)
    add("July less January, land at 40 to 60 N", mean(t[6] - t[0], north_land), mean(t_earth[6] - t_earth[0], north_land), "K")
    add("rain of the year", mean(p.sum(axis=0), everywhere), mean(p_earth.sum(axis=0), everywhere), "mm")
    add("  over land", mean(p.sum(axis=0), land), mean(p_earth.sum(axis=0), land), "mm")
    add("  over sea", mean(p.sum(axis=0), wet), mean(p_earth.sum(axis=0), wet), "mm")
    for lo, hi in ((-60, -40), (-40, -15), (-15, 15), (15, 40), (40, 60), (60, 90)):
        band = land & (m.lat >= lo) & (m.lat < hi)
        if band.any():
            add(f"  land between {lo} and {hi} degrees", mean(p.sum(axis=0), band), mean(p_earth.sum(axis=0), band), "mm")
    names = v.attrs["fields"]["climate_class"]["categories"]
    group = np.array([n[0] for n in names])[f["climate_class"]]
    for letter, share in PEEL.items():
        add(f"climate group {letter}, share of land", 100 * area[land & (group == letter)].sum() / area[land].sum(), share, "%")
    if "evapotranspiration" in f:
        fell = (p.sum(axis=0) * area)[land].sum() / 1000.0
        to_air = (f["evapotranspiration"].astype(np.float64).sum(axis=0) * area)[land].sum() / 1000.0
        to_sea = f["river_discharge"].astype(np.float64)[:, wet].mean(axis=0).sum() * YEAR_S
        add("rain on land that goes back to the air", 100 * to_air / fell, 65.0, "%")
        add("rivers reaching the sea", to_sea / 1e12, 40.0, "thousand km3 a year")
        recv = f["flow_receiver"]
        coast = np.flatnonzero(land & (recv >= 0) & wet[np.maximum(recv, 0)])
        river = f["river_discharge"].astype(np.float64).mean(axis=0)
        largest = int(coast[np.argmax(river[coast])])
        add("largest river", river[largest], 220_000.0, f"m3/s (the twin's at {m.lat[largest]:.0f}, {m.lon[largest]:.0f}; the Amazon's mouth is at 0, -50)")
        add("land under lakes", 100 * (f["lake_fraction"].astype(np.float64) * area).sum() / area[land].sum(), 2.0, "% (Earth: about 2, from memory)")
    print(f"\nThe Earth twin ({meta['cells']} cells, {meta['rounds_used'].get('climate')} climate rounds, settled: {meta['settled'].get('climate')}) beside Earth")
    print(f"{'':44s}{'twin':>10s}{'Earth':>10s}")
    for what, twin, earth, unit in rows:
        print(f"{what:44s}{twin:10.1f}{earth:10.1f}  {unit}")
    both = np.isfinite(t_earth.mean(axis=0))
    difference = (t.mean(axis=0) - t_earth.mean(axis=0))[both]
    print(f"yearly temperature, cell by cell: the twin differs from Earth by {np.sqrt((difference ** 2 * area[both]).sum() / area[both].sum()):.1f} K (root mean square)")
    ratio = np.corrcoef(np.log1p(p.sum(axis=0)), np.log1p(p_earth.sum(axis=0)))[0, 1]
    print(f"yearly rain, cell by cell: correlation of the logarithms {ratio:.2f}")
    for nt in v.attrs.get("notices") or []:
        print("notice:", nt)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not ref.available():
        sys.exit("the Earth reference data is not here: run python tools/fetch_reference_data.py")
    if "--compare" in args:
        compare(args[args.index("--compare") + 1])
    else:
        profile = args[args.index("--profile") + 1] if "--profile" in args else "preview"
        out = args[args.index("--out") + 1] if "--out" in args else str(ROOT / "worlds" / f"earth_twin_{profile}.zarr")
        compare(build(profile, out))
