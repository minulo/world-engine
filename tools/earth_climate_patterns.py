"""The patterns of build steps 4 and 5 on the Earth twin, beside Earth.

  * cold water off west coasts (step 4): the yearly mean temperature of the sea off Peru, California, south-west
    Africa and north-west Africa, less the mean of the sea in the same band of latitude; on the twin, and on Earth from
    the Climatic Research Unit's means of 1961 to 1990 (which hold the air over the sea);
  * the summer rain of the 30-degree deserts (step 5): June to August over the Sahara and Arabia, the twin against
    GPCP 1979 to 2010;
  * the seasonal reversal of the wind over India (step 5): the twin's wind in January and in July [Earth's monsoon blows
    from the north-east in January and from the south-west in July: UNVERIFIED, recalled; the reference data hold no
    wind];
  * wind-facing coasts (step 5): January temperature of western Europe against the east coast of Asia between 45 and
    60 degrees north, on the twin and on Earth.

    python tools/earth_climate_patterns.py [--data DIR] [--profile preview]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import earth_reference as ref                                   # noqa: E402
from fit_spreading import twin_relief                           # noqa: E402
from worldengine.console import print_anywhere                  # noqa: E402
from worldengine.engine import Engine, World                    # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR                 # noqa: E402

WEST_COASTS = {"Peru": (-20, -5, -85, -75), "California": (25, 40, -127, -115), "south-west Africa": (-30, -15, 5, 15),
               "north-west Africa": (15, 30, -25, -15)}
DESERTS = {"Sahara": (15, 30, -15, 30), "Arabia": (15, 30, 40, 55)}
INDIA = (10, 25, 70, 90)
COASTS = {"western Europe": (45, 60, -10, 10), "east coast of Asia": (45, 60, 125, 145)}


def box(m, b):
    return (m.lat >= b[0]) & (m.lat <= b[1]) & (m.lon >= b[2]) & (m.lon <= b[3])


def twin_climate(data, profile):
    eng = twin_relief(data, profile)
    e = Engine(data, profile=profile, overrides=ref.earth_twin_overrides(data, eng.mesh))
    e.mesh, e.world = eng.mesh, World(eng.mesh, eng.months)
    e._fresh, e._weights, e.memo = {k: set(v) for k, v in eng._fresh.items()}, {}, {}
    e._received, e._last_given, e._applied, e._rounds_in_force = set(), {}, {}, {}
    e.world.fields.update(eng.world.fields)
    e.world.tables.update(eng.world.tables)
    e.world.rounds_used.update(eng.world.rounds_used)
    with e._limit_threads():
        e._run_climate("climate")
    return e.mesh, e.world, e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--profile", default="preview")
    ap.add_argument("--out", default=None, help="keep the twin's climate in a world store")
    args = ap.parse_args(argv)
    print_anywhere()
    m, w, e = twin_climate(args.data, args.profile)
    if args.out:
        from worldengine import store
        e._finish_push_records()
        e._lineage()
        w.meta = {"profile": args.profile, "mesh_level": e.level, "cells": w.n, "months": w.months, "seed": e.seed,
                  "rounds_used": dict(w.rounds_used), "settled": dict(w.settled), "order": e.order(), "notes": [],
                  "mesh": m.describe(), "math_threads": 1}
        store.save(w, e, args.out)
    f = w.fields
    sea = f["ocean_mask"].astype(bool)
    area = m.area
    t_twin = f["surface_temperature"].astype(np.float64) - 273.15
    t_earth = ref.at_cell_centres(m, *ref.temperature_monthly())
    p_twin = f["precipitation"].astype(np.float64)
    p_earth = ref.at_cell_centres(m, *ref.rain_monthly())
    print(f"twin: climate rounds {w.rounds_used['climate']}, settled {w.settled['climate']}")
    print("cold water off west coasts: the sea's yearly mean less that of the sea in its band (K)")
    for name, b in WEST_COASTS.items():
        here = sea & box(m, b)
        band = sea & (m.lat >= b[0]) & (m.lat <= b[1])
        anomaly = lambda t: np.nanmean(t.mean(axis=0)[here]) - np.nanmean(t.mean(axis=0)[band])
        up = f["upwelling"].mean(axis=0)[here].mean() if "upwelling" in f else float("nan")
        print(f"  {name:18s} twin {anomaly(t_twin):+5.1f}  Earth {anomaly(t_earth):+5.1f}   upwelling on the twin {up:+.2f} m/day")
    jja = [5, 6, 7]
    print("summer rain, June to August (mm/month)")
    for name, b in DESERTS.items():
        here = ~sea & box(m, b)
        print(f"  {name:18s} twin {np.average(p_twin[jja].mean(axis=0)[here], weights=area[here]):6.1f}  "
              f"Earth {np.nanmean(p_earth[jja].mean(axis=0)[here]):6.1f}")
    here = ~sea & box(m, INDIA)
    wind = f["wind"].astype(np.float64)
    for month, label in ((0, "January"), (6, "July")):
        east = np.einsum("ij,ij->i", wind[month], m.east)[here].mean()
        north = np.einsum("ij,ij->i", wind[month], m.north)[here].mean()
        print(f"  wind over India in {label}: {east:+.2f} m/s toward the east, {north:+.2f} m/s toward the north")
    print("January temperature of land between 45 and 60 north (C)")
    for name, b in COASTS.items():
        here = ~sea & box(m, b)
        print(f"  {name:18s} twin {np.average(t_twin[0][here], weights=area[here]):6.1f}  Earth {np.nanmean(t_earth[0][here]):6.1f}")


if __name__ == "__main__":
    main()
