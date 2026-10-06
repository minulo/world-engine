"""The preview Earth twin with a sea that warms and cools faster: a diagnosis that follows handoff/pass3/eb_varying.py.
The heat capacity of the sea is the published 3.10e8 J/m2/K (a mixed layer of 75 m) divided by 2, 3 and 4.

    PYTHONPATH=src python handoff/pass3/seasons_sea.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import earth_reference as ref
from seasons_apart import twin, numbers, eb, no_snow, both, BASE

SEA = BASE["slots"]["EnergyBalance"]["constants"]["heat_capacity_sea_j_m2_k"]


def more(e, w):
    m, f = w.mesh, w.fields
    area, wet = f["cell_area"].astype(np.float64), f["ocean_mask"]
    land = ~wet
    t = f["surface_temperature"].astype(np.float64) - 273.15
    te = ref.at_cell_centres(m, *ref.temperature_monthly())
    p = f["precipitation"].astype(np.float64).sum(axis=0)
    pe = ref.at_cell_centres(m, *ref.rain_monthly()).sum(axis=0)
    mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
    north, water = land & (m.lat > 40) & (m.lat < 60), wet & (m.lat > 40) & (m.lat < 60)
    snow = f["snow_cover"].astype(np.float64)
    rms = float(np.sqrt(mean((t.mean(axis=0) - te.mean(axis=0)) ** 2, np.ones(m.n, dtype=bool))))
    return {"sea_swing": mean(t[6] - t[0], water), "earth_sea_swing": mean(te[6] - te[0], water), "rain": mean(p, north), "earth_rain": mean(pe, north),
            "white_all": 100.0 * area[land & (snow.min(axis=0) > 0.5)].sum() / area[land].sum(), "land": mean(t.mean(axis=0), land), "earth_land": mean(te.mean(axis=0), land), "rms": rms,
            "south": mean(t.mean(axis=0), m.lat < -60), "earth_south": mean(te.mean(axis=0), m.lat < -60)}


RUNS = [("as built", lambda s: None), ("sea 2 times faster", eb("heat_capacity_sea_j_m2_k", SEA / 2)), ("sea 3 times faster", eb("heat_capacity_sea_j_m2_k", SEA / 3)),
        ("sea 4 times faster", eb("heat_capacity_sea_j_m2_k", SEA / 4)), ("sea 3 times faster, no snow on the ground", both(eb("heat_capacity_sea_j_m2_k", SEA / 3), no_snow))]
print("preview Earth twin; land between 40 and 60 degrees north unless said; temperatures in C, shares in %, rain in mm a year")
print(f"{'':44s} coldest warmest   year Jul-Jan  sea Jul-Jan  white  group D group E  rain   all land white  land year  globe  60-90 S  cell rms  rounds")
first = True
for name, change in RUNS:
    e, w = twin(change)
    r, x = numbers(e, w), more(e, w)
    if first:
        a = r["earth"]
        print(f"{'Earth':44s} {a[0]:7.1f} {a[1]:7.1f} {a[2]:6.1f} {a[3]:7.1f}  {x['earth_sea_swing']:11.1f}  {'':5s}  {24.6:7.1f} {12.8:7.1f} {x['earth_rain']:5.0f}  {'':14s}  {x['earth_land']:9.1f} {a[4]:6.1f}  {x['earth_south']:7.1f}")
        first = False
    print(f"{name:44s} {r['cold']:7.1f} {r['warm']:7.1f} {r['year']:6.1f} {r['swing']:7.1f}  {x['sea_swing']:11.1f}  {r['white']:5.1f}  {r['D']:7.1f} {r['E']:7.1f} {x['rain']:5.0f}  {x['white_all']:14.1f}  {x['land']:9.1f} {r['globe']:6.1f}  {x['south']:7.1f}  {x['rms']:8.1f}  {r['rounds']:3d}{'' if r['settled'] else ' NOT SETTLED'}", flush=True)
