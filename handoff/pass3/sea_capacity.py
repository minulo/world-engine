"""Which heat capacity of the sea returns the seasons of Earth's open sea? The preview Earth twin is built with the
published capacity (3.10e8 J/m2/K, a mixed layer of 75 m) divided by several factors, and the swing of the sea's
temperature between its warmest and coldest month is read off over open sea, cells whose centre lies more than 600 km
from any land cell, in four bands of latitude, beside the same from the temperature data (CRU, 1961 to 1990, on a grid
of 5 degrees, read at the same cells). The measure is the sea's alone; the land is looked at afterwards.

    PYTHONPATH=src python handoff/pass3/sea_capacity.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import earth_reference as ref
from seasons_apart import twin, eb, BASE

SEA = BASE["slots"]["EnergyBalance"]["constants"]["heat_capacity_sea_j_m2_k"]
BANDS = ((20, 40), (40, 60), (-40, -20), (-60, -40))
FACTORS = (1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0)


def swings(w):
    m, f = w.mesh, w.fields
    area, wet = f["cell_area"].astype(np.float64), f["ocean_mask"]
    land_xyz = m.xyz[~wet]
    nearest = np.array([np.arccos(np.clip((land_xyz @ m.xyz[c]).max(), -1, 1)) for c in range(m.n)]) * ref.EARTH_RADIUS_M / 1000.0
    open_sea = wet & (nearest > 600.0)
    t = f["surface_temperature"].astype(np.float64) - 273.15
    te = ref.at_cell_centres(m, *ref.temperature_monthly())
    out = []
    for lo, hi in BANDS:
        mask = open_sea & (m.lat > lo) & (m.lat < hi)
        series = lambda x: np.array([(x[k] * area)[mask].sum() / area[mask].sum() for k in range(12)])
        a, b = series(t), series(te)
        out.append((a.max() - a.min(), b.max() - b.min(), int(mask.sum())))
    return out


if __name__ == "__main__":
    print("warmest month less coldest over open sea (more than 600 km from land), K: the twin, and Earth's data at the same cells")
    print(f"{'sea capacity':>26s}  " + "  ".join(f"{lo:>4d} to {hi:<4d}" for lo, hi in BANDS) + "   root mean square of the four differences")
    for k in FACTORS:
        e, w = twin(eb("heat_capacity_sea_j_m2_k", SEA / k))
        s = swings(w)
        if k == FACTORS[0]:
            print(f"{'Earth':>26s}  " + "  ".join(f"{b:12.1f}" for _, b, _ in s) + "   (cells: " + ", ".join(str(n) for _, _, n in s) + ")")
        rms = float(np.sqrt(np.mean([(a - b) ** 2 for a, b, _ in s])))
        print(f"{SEA / k:14.3e} (1/{k:<3.1f})    " + "  ".join(f"{a:12.1f}" for a, _, _ in s) + f"   {rms:6.2f}", flush=True)
