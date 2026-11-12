"""The preview Earth twin with the first and the second OceanCurrents, side by side: the numbers of
docs/BUILD_NOTES.md, section 28. A measurement, not a setting of the engine: the second version is put in the
slot by an override, whatever data/models.yaml names as the default.

    WORLDENGINE_REFERENCE_DATA=... PYTHONPATH=src python handoff/overturning/overturning_twin.py

The ocean's heat across a latitude is read off its heat convergence, as handoff/summer/bands_and_hemispheres.py reads
it; the overturning's own, off its driver. The basins named below are boxes of longitude and latitude for reading
the result only: nothing in the engine knows them.
"""
import copy
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import earth_reference as ref  # noqa: E402
from worldengine.engine import Engine  # noqa: E402
from worldengine.library import overturning as ov  # noqa: E402
from worldengine.mesh import get_mesh  # noqa: E402

DATA = ROOT / "data"
SECOND = "worldengine.processes.ocean_wind_and_density:WindAndDensityOcean"
EXTRA = ["sea_surface_salinity", "overturning_sinking"]
READ = lambda name: yaml.safe_load((DATA / name).read_text(encoding="utf-8"))
LAST = {}


def kept(mesh, c, **kw):                                  # the last overturning worked out, for its regions' terms
    out = KEPT(mesh, c, **kw)
    LAST.update(out=out, kw=kw)
    return out


KEPT, ov.overturn = ov.overturn, kept


def twin(second):
    models = ref.earth_twin_models(copy.deepcopy(READ("models.yaml")), get_mesh(5))
    if second:
        slot = models["slots"]["OceanCurrents"]
        slot["implementation"], slot["writes"] = SECOND, slot["writes"] + EXTRA
    e = Engine(DATA, profile="preview", overrides={"models": models, "explanations": ref.earth_twin_explanations(READ("explanations.yaml")),
                                                   "stages": ref.earth_twin_stages(READ("stages.yaml"))})
    t0 = time.time()
    return e, e.build(), time.time() - t0


def box(m, lat0, lat1, lon0, lon1):
    return (m.lat >= lat0) & (m.lat < lat1) & (m.lon >= lon0) & (m.lon < lon1)


def numbers(e, w):
    m, f = w.mesh, w.fields
    area, sea = f["cell_area"].astype(np.float64), np.asarray(f["ocean_mask"], dtype=bool)
    land = ~sea
    t = f["surface_temperature"].astype(np.float64) - 273.15
    te = ref.at_cell_centres(m, *ref.temperature_monthly())
    mean = lambda x, mk: float((x * area)[mk].sum() / area[mk].sum())
    north = land & (m.lat > 40) & (m.lat < 60)
    nsea = sea & (m.lat > 40) & (m.lat < 60)
    months = np.array([mean(t[k], north) for k in range(12)])
    earth_months = np.array([mean(te[k], north) for k in range(12)])
    everywhere = np.ones(m.n, dtype=bool)
    rows = {"climate rounds": w.rounds_used["climate"], "settled": w.settled["climate"],
            "land 40-60 N, warmest month C": (months.max(), earth_months.max()),
            "land 40-60 N, coldest month C": (months.min(), earth_months.min()),
            "land 40-60 N, year C": (months.mean(), earth_months.mean()),
            "sea 40-60 N, year C": (mean(t.mean(0), nsea), mean(te.mean(0), nsea)),
            "sea 40-60 N, July C": (mean(t[6], nsea), mean(te[6], nsea)),
            "planet, year C": (mean(t.mean(0), everywhere), mean(te.mean(0), everywhere)),
            "northern half, year C": (mean(t.mean(0), m.lat > 0), mean(te.mean(0), m.lat > 0)),
            "southern half, year C": (mean(t.mean(0), m.lat < 0), mean(te.mean(0), m.lat < 0))}
    have = ~np.isnan(te.mean(0))
    tropics, polar = have & (np.abs(m.lat) < 10), have & (np.abs(m.lat) >= 60)
    fall = lambda x: np.average(x[tropics], weights=area[tropics]) - np.average(x[polar], weights=area[polar])
    rows["tropics less polar caps, year K"] = (fall(t.mean(0)), fall(te.mean(0)))
    b = e.params["models"]["slots"]["EnergyBalance"]["constants"]["loss_per_kelvin_w_m2_k"]
    order = np.argsort(m.lat)
    conv = np.asarray(w.drivers["surface_temperature"]["other_heat"], dtype=np.float64).mean(0) * b * area
    south = np.cumsum(conv[order])
    for edge in (-40.0, -20.0, 0.0, 20.0, 26.5, 40.0, 60.0):
        rows[f"ocean's heat northward across {edge:g}, PW"] = -south[np.searchsorted(m.lat[order], edge) - 1] / 1e15
    # the freshwater balance of the sea by basin (boxes of longitude and latitude), and the westerlies of the Southern Ocean
    month_s = e.planet["year_length_s"] / e.months
    lost = (f["ocean_evaporation"].astype(np.float64).mean(0) - f["precipitation"].astype(np.float64).mean(0)) / 1000.0 / month_s * area \
        - f["river_discharge"].astype(np.float64).mean(0)
    atlantic = sea & (box(m, -35, 66, -100, 20) | box(m, 8, 30, -100, -70)) & ~box(m, -35, 8, -100, -70)
    pacific = sea & ~atlantic & (box(m, -35, 66, 120, 181) | box(m, -35, 66, -181, -70))
    for name, mk in (("Atlantic 35 S to 66 N", atlantic), ("Pacific 35 S to 66 N", pacific), ("Indian 35 S to 30 N", sea & box(m, -35, 30, 20, 120))):
        rows[f"sea loses to the air less rain and rivers, {name}, Sv and mm a year"] = (lost[mk].sum() / 1e6, lost[mk].sum() / area[mk].sum() * e.planet["year_length_s"] * 1000.0)
    east = np.einsum("mij,ij->mi", f["wind"].astype(np.float64), m.east).mean(0)
    rows["eastward wind over the sea at 55 to 60 S, m/s"] = float(east[sea & (m.lat > -60) & (m.lat < -55)].mean())
    over = w.drivers["ocean_heat_convergence"].get("carried_by_overturning")
    if over is not None:
        o = np.asarray(over, dtype=np.float64).mean(0) * area
        south = np.cumsum(o[order])
        for edge in (-40.0, -20.0, 0.0, 26.5, 40.0, 60.0):
            rows[f"the overturning's alone across {edge:g}, PW"] = -south[np.searchsorted(m.lat[order], edge) - 1] / 1e15
        sink = np.maximum(f["overturning_sinking"].astype(np.float64), 0.0) * area / e.planet["year_length_s"]
        rows["sinking, all, Sv"] = sink.sum() / 1e6
        places = {"North Atlantic and Arctic (north of 40 N, 80 W to 30 E)": box(m, 40, 91, -80, 30),
                  "North Pacific (north of 20 N, 110 E to 100 W)": box(m, 20, 91, 110, 181) | box(m, 20, 91, -181, -100),
                  "south of 40 S": m.lat < -40,
                  "North Atlantic 40-50 N (80 W to 0)": box(m, 40, 50, -80, 0),
                  "North Atlantic 20-40 N (80 W to 5 W)": box(m, 20, 40, -80, -5),
                  "Labrador and Nordic seas 50-80 N (70 W to 30 E)": box(m, 50, 80, -70, 30),
                  "North Pacific 40-50 N": box(m, 40, 50, 110, 181) | box(m, 40, 50, -181, -100),
                  "North Pacific 20-40 N west of 180 (Japan Sea within)": box(m, 20, 40, 110, 181),
                  "north of 80 N, at the edge of the polar sea that goes round": m.lat >= 80}
        for name, mk in places.items():
            rows[f"sinking, {name}, Sv"] = sink[mk].sum() / 1e6
        for lo, hi in ((-90, -60), (-60, -40), (20, 40), (40, 50), (50, 60), (60, 91)):
            rows[f"sinking between {lo} and {min(hi, 90)}, Sv"] = sink[(m.lat >= lo) & (m.lat < hi)].sum() / 1e6
        salt = f["sea_surface_salinity"].astype(np.float64)
        for name, mk in {"North Atlantic 50-65 N": box(m, 50, 65, -60, 0), "North Pacific 45-60 N": box(m, 45, 60, 150, 181) | box(m, 45, 60, -181, -130),
                         "subtropical North Atlantic 20-35 N": box(m, 20, 35, -70, -20), "subtropical North Pacific 20-35 N": box(m, 20, 35, 140, 181) | box(m, 20, 35, -181, -130),
                         "Southern Ocean 50-60 S": (m.lat > -60) & (m.lat < -50), "Arctic, north of 70 N": m.lat > 70}.items():
            rows[f"salinity, {name}, psu"] = mean(salt, sea & mk)
        rows["salinity, lowest and highest, psu"] = (float(salt[sea].min()), float(salt[sea].max()))
        kw = LAST["kw"]
        band_rad = kw["sides"]["width_m"].min() / kw["radius"] if kw["sides"]["width_m"].size else float("nan")
        _, goes = ov.circumpolar(m, kw["deep"], 2 * m.spacing())
        rows["bands that go round, degrees"] = [(round(float(np.rad2deg(k * 2 * m.spacing()) - 90), 1),
                                                 round(float(np.rad2deg((k + 1) * 2 * m.spacing()) - 90), 1)) for k in np.flatnonzero(goes)]
        region = kw["region"]
        for r, row in LAST["out"]["regions"].items():
            cells = region == r
            rows[f"region {r}: {int(cells.sum())} cells, {m.lat[cells].min():.0f} to {m.lat[cells].max():.0f} degrees"] = {
                k: (round(v / 1e6, 2) if k.endswith("_m3_s") else round(v, 5) if isinstance(v, float) else v) for k, v in row.items()}
        rows["passes in the last round"] = LAST["out"]["passes"]
    return rows


if __name__ == "__main__":
    for second in (False, True):
        e, w, seconds = twin(second)
        print(f"== OceanCurrents: {e.params['models']['slots']['OceanCurrents']['implementation']} ({seconds:.0f} s)")
        for k, v in numbers(e, w).items():
            if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, (float, np.floating)) for x in v):
                print(f"  {k:62s} {v[0]:8.2f}   (Earth {v[1]:.2f})" if k.endswith(" C") or k.endswith(" K") else f"  {k:62s} {v[0]:8.2f} {v[1]:8.2f}")
            elif isinstance(v, (float, np.floating)):
                print(f"  {k:62s} {v:8.2f}")
            else:
                print(f"  {k:62s} {v}")
        sys.stdout.flush()
