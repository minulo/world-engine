"""Measure the steps between fine neighbours across world-cell edges and inside cells, on section 21's region."""
import sys
import time

import numpy as np

from worldengine import detail as dt
from worldengine import store
from worldengine.mesh import get_mesh
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts


def region_of(view, km=800.0, dlat=0.0, dlon=0.0):
    coarse = get_mesh(int(view.meta["mesh_level"]))
    lat, hs = np.asarray(view.field("latitude")), np.asarray(view.field("height_above_sea"))
    k = int(np.argmax(np.where(np.abs(lat) < 50, hs, -1e9)))
    return dt.region_cells(coarse, float(lat[k]) + dlat, float(np.asarray(view.field("longitude"))[k]) + dlon, km,
                           view.attrs["planet"]["radius_m"])


def pairs(d):
    fine = get_mesh(d.level)
    pos = {int(c): i for i, c in enumerate(d.cells)}
    a, b = [], []
    for i, c in enumerate(d.cells):
        for g in fine.nbr[c]:
            g = int(g)
            if g > c and g in pos:
                a.append(i); b.append(pos[g])
    a, b = np.array(a), np.array(b)
    return a, b, d.owner[a] != d.owner[b]


def steps(d, values, a, b, edge):
    diff = np.abs(values[a] - values[b])
    return float(np.median(diff[edge])), float(np.median(diff[~edge]))


def local_ratio(d, values, a, b, edge):
    """Per world-cell edge inside the region: the median step across it over the median step inside the two cells."""
    diff = np.abs(values[a] - values[b])
    oa, ob = d.owner[a], d.owner[b]
    out = []
    for k in d.region:
        for j in get_mesh(d.level - 2).nbr[k]:
            j = int(j)
            if j > k and j in set(d.region.tolist()):
                m = edge & (((oa == k) & (ob == j)) | ((oa == j) & (ob == k)))
                n = (~edge) & ((oa == k) | (oa == j))
                if m.any() and np.median(diff[n]) > 0:
                    out.append(np.median(diff[m]) / np.median(diff[n]))
    return float(np.median(out)), len(out)


def report(d, view, label=""):
    a, b, edge = pairs(d)
    f = d.fields
    fine = get_mesh(d.level)
    out = {}
    e, i = steps(d, f["elevation"], a, b, edge)
    out["height"] = (e, i, e / i)
    t = f["surface_temperature"].mean(axis=0)
    e, i = steps(d, t, a, b, edge)
    out["temp_annual"] = (e, i, e / i)
    tm = [steps(d, f["surface_temperature"][m], a, b, edge) for m in range(12)]
    out["temp_months_median"] = (float(np.median([x[0] for x in tm])), float(np.median([x[1] for x in tm])),
                                 float(np.median([x[0] / x[1] for x in tm])))
    p = f["precipitation"].sum(axis=0)
    e, i = steps(d, p, a, b, edge)
    out["rain_annual"] = (e, i, e / i)
    lp = np.log(np.maximum(p, 1e-9))
    e, i = steps(d, lp, a, b, edge)
    out["rain_log"] = (e, i, e / i)
    for name, vals in (("height", f["elevation"]), ("temp_annual", f["surface_temperature"].mean(axis=0)),
                       ("rain_annual", f["precipitation"].sum(axis=0)), ("rain_log", lp)):
        lr, n = local_ratio(d, vals, a, b, edge)
        out[name + "_local"] = (lr, n, lr)
    print(f"{label} region {d.region.size} world cells, {d.cells.size} fine cells, pairs edge {edge.sum()} inside {(~edge).sum()}")
    for k, v in out.items():
        print(f"   {k:20s} across {v[0]:10.4g}  inside {v[1]:10.4g}  ratio {v[2]:.4f}")
    w = {n: np.asarray(view.field(n), dtype=np.float64) for n in ("elevation", "surface_temperature", "precipitation")}
    for n in w:
        gap = np.abs(d.coarse_means(n, fine.area) - w[n][..., d.region]).max()
        print(f"   largest gap {n}: {gap:.3g}")
    return out


if __name__ == "__main__":
    view = store.StoreView(sys.argv[1])
    if "--base" in sys.argv:                                  # the module as it stood at the base commit
        import types
        base = types.ModuleType("worldengine.detail_base")
        base.__package__ = "worldengine"
        exec(compile(open(HERE + "/detail_base.py").read(),
                     "detail_base", "exec"), base.__dict__)
        dt = base
    if "--own" in sys.argv:                                   # the engine's constants, not the store's copy
        import yaml
        from worldengine.params import DEFAULT_DATA_DIR
        dt.constants = lambda v: yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))
    region = region_of(view)
    t0 = time.time()
    d = dt.refine(view, region)
    print(f"refine {time.time() - t0:.2f} s")
    report(d, view, "store")
    f = d.fields
    print("   fine heights", f["elevation"].min(), f["elevation"].max(), " sea share", f["ocean_mask"].mean(), " lake share", f["lake"].mean())
    print("   rain min", f["precipitation"].min(), "max", f["precipitation"].max(), "; temperature", f["surface_temperature"].min(), f["surface_temperature"].max())
    print("   largest river", f["river_discharge"].max())
