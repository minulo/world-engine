"""Fit EnergyBalance's spreading constant again, on the Earth twin against Earth's measured temperatures.

The constant of North, Cahalan and Coakley 1981 (0.649 W/m2 per K) was fitted to the observed fall of temperature from
the equator to the poles with spreading as the only way heat moves sideways. Once another process carries heat (the
ocean in build step 4, the wind in step 5), the constant must be fitted again, or that heat is carried twice (design,
Layer 5). This tool builds the relief of the Earth twin once, runs the climate stage for each value asked, and prints
how far the twin's yearly mean temperature, averaged around each 5-degree band of latitude, lies from the Climatic
Research Unit's means of 1961 to 1990 read off at the same cells, and the fall of the yearly mean from the tropics
(within 10 degrees) to the polar caps (beyond 60). The fit is the value at which that fall equals Earth's, as the
constant of 1981 was fitted to the fall from the equator to the poles; the band misfit is printed beside it.

    python tools/fit_spreading.py [--data DIR] [--profile preview] 0.3 0.4 0.5 0.649
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import earth_reference as ref                                   # noqa: E402
from worldengine.console import print_anywhere                  # noqa: E402
from worldengine.engine import Engine, World                    # noqa: E402
from worldengine.mesh import get_mesh                           # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR                 # noqa: E402

BAND_DEG = 5.0


def twin_relief(data, profile):
    """The fields and tables of the twin's setup and geological stages."""
    level = Engine(data, profile=profile).level
    eng = Engine(data, profile=profile, overrides=ref.earth_twin_overrides(data, get_mesh(level)))
    eng.mesh = get_mesh(eng.level)
    eng.world = World(eng.mesh, eng.months)
    eng._fresh, eng._weights, eng.memo = {}, {}, {}
    eng._received, eng._last_given, eng._applied, eng._rounds_in_force = set(), {}, {}, {}
    with eng._limit_threads():
        eng._run_once("setup")
        eng._run_geological("geological")
    return eng


def climate_with(eng, data, profile, value):
    over = ref.earth_twin_overrides(data, eng.mesh)
    slot = over["models"]["slots"]["EnergyBalance"]
    slot["constants"] = {**slot["constants"], "spreading_constant_w_m2_k": float(value)}
    e = Engine(data, profile=profile, overrides=over)
    e.mesh, e.world = eng.mesh, World(eng.mesh, eng.months)
    e._fresh, e._weights, e.memo = {k: set(v) for k, v in eng._fresh.items()}, {}, {}
    e._received, e._last_given, e._applied, e._rounds_in_force = set(), {}, {}, {}
    w = e.world
    w.fields.update(eng.world.fields)
    w.tables.update(eng.world.tables)
    w.rounds_used.update(eng.world.rounds_used)
    with e._limit_threads():
        e._run_climate("climate")
    return w


def misfit(mesh, world, earth):
    t = world.fields["surface_temperature"].mean(axis=0) - 273.15
    have = ~np.isnan(earth)
    lat, area = mesh.lat, mesh.area
    bands = np.floor(lat / BAND_DEG).astype(int)
    rows = []
    for b in np.unique(bands):
        sel = have & (bands == b)
        if sel.any():
            rows.append((b, np.average(t[sel] - earth[sel], weights=area[sel]), area[sel].sum()))
    gaps = np.array([r[1] for r in rows])
    weights = np.array([r[2] for r in rows])
    rms = float(np.sqrt(np.average(gaps ** 2, weights=weights)))
    tropics = have & (np.abs(lat) < 10)
    polar = have & (np.abs(lat) >= 60)
    contrast = lambda x: np.average(x[tropics], weights=area[tropics]) - np.average(x[polar], weights=area[polar])
    return rms, float(contrast(t)), float(contrast(earth)), bool(world.settled.get("climate"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--profile", default="preview")
    ap.add_argument("values", type=float, nargs="+")
    args = ap.parse_args(argv)
    print_anywhere()
    if not ref.available("absolute.nc", "ETOPO5.DAT"):
        sys.exit("the Earth data are missing: python tools/fetch_reference_data.py")
    eng = twin_relief(args.data, args.profile)
    earth = np.nanmean(ref.at_cell_centres(eng.mesh, *ref.temperature_monthly()), axis=0)
    print(f"{'spreading W/m2/K':>17} {'band misfit K (rms)':>20} {'tropics-polar K':>16} {'Earth':>7} {'settled':>8} {'s':>5}")
    best, rows = None, []
    for value in args.values:
        t0 = time.perf_counter()
        rms, model, measured, settled = misfit(eng.mesh, climate_with(eng, args.data, args.profile, value), earth)
        print(f"{value:17.3f} {rms:20.2f} {model:16.1f} {measured:7.1f} {str(settled):>8} {time.perf_counter() - t0:5.0f}", flush=True)
        rows.append((value, model, measured))
        if best is None or rms < best[1]:
            best = (value, rms)
    print(f"smallest misfit: {best[0]} ({best[1]:.2f} K)")
    # the fit of 1981 was to the fall of temperature from the equator to the poles: the value at which the twin's fall from
    # the tropics to the polar caps equals Earth's, by straight lines between the values tried
    rows.sort()
    for (v0, m0, e0), (v1, m1, _) in zip(rows[:-1], rows[1:]):
        if (m0 - e0) * (m1 - e0) <= 0 and m0 != m1:
            print(f"the fall from the tropics to the poles equals Earth's ({e0:.1f} K) at {v0 + (v1 - v0) * (e0 - m0) / (m1 - m0):.3f}")
            break
    else:
        print("the fall from the tropics to the poles equals Earth's at no value between those tried")


if __name__ == "__main__":
    main()
