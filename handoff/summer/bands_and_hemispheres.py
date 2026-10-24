"""Read a twin saved by summer_causes.py (--save=DIR) beside CRU: the yearly, July and January means of land and sea by
band of latitude, the absorbed sunlight and EnergyBalance's terms by band, the heat the wind and the ocean carry over
the planet, the ocean's northward heat transport across chosen latitudes, and the means of the two hemispheres.

    PYTHONPATH=src python handoff/summer/bands_and_hemispheres.py DIR/as_built.npz
"""
import sys

import numpy as np

import earth_reference as ref
from worldengine.mesh import get_mesh

B = 2.09                                                         # W/m2 per K, EnergyBalance's loss_per_kelvin
BANDS = ((-90, -60), (-60, -40), (-40, -20), (-20, 0), (0, 20), (20, 40), (40, 60), (60, 90))

d = np.load(sys.argv[1])
lat, area, sea = d["lat"], d["cell_area"].astype(float), d["ocean_mask"]
mesh = get_mesh({2562: 4, 10242: 5, 40962: 6}[lat.size])
t = d["surface_temperature"].astype(float) - 273.15
te = ref.at_cell_centres(mesh, *ref.temperature_monthly())
absorbed = (d["insolation"].astype(float) * (1 - d["albedo"].astype(float))).mean(0)
drivers = [k for k in d.files if k.startswith("driver_")]
print("band       kind  twin ann  CRU ann  twin Jul  CRU Jul  twin Jan  CRU Jan  absorbed  " + " ".join(k[7:19] for k in drivers))
for lo, hi in BANDS:
    b = (lat >= lo) & (lat < hi)
    for name, mk in (("land", b & ~sea), ("sea", b & sea)):
        if not mk.any():
            continue
        w = area[mk] / area[mk].sum()
        f = lambda x: float((x[..., mk] * w).sum(-1))
        terms = [f(d[k].astype(float).mean(0)) - (273.15 if "sunlight" in k else 0.0) for k in drivers]
        print(f"{lo:4d}..{hi:3d} {name:4s} {f(t.mean(0)):9.1f} {f(te.mean(0)):8.1f} {f(t[6]):9.1f} {f(te[6]):8.1f} {f(t[0]):9.1f} "
              f"{f(te[0]):8.1f} {f(absorbed):9.1f}  " + " ".join(f"{v:11.1f}" for v in terms))
for k in ("driver_carried_by_wind", "driver_other_heat"):
    v = d[k].astype(float).mean(0) * B
    print(f"{k[7:]}: over the planet {(v * area).sum() / area.sum():+.2f} W/m2")
conv = d["driver_other_heat"].astype(float).mean(0) * B * area                    # W, the ocean's heat convergence
order = np.argsort(lat)
south_of = np.cumsum(conv[order])
for edge in (-40.0, -20.0, 0.0, 20.0, 26.5, 40.0, 60.0):
    print(f"the ocean carries {-south_of[np.searchsorted(lat[order], edge) - 1] / 1e15:+.2f} PW northward across {edge:g} degrees")
for name, mk in (("north", lat > 0), ("south", lat < 0)):
    w = area[mk] / area[mk].sum()
    print(f"{name}ern hemisphere: twin {(t.mean(0)[mk] * w).sum():.2f} C, CRU {(te.mean(0)[mk] * w).sum():.2f} C")
