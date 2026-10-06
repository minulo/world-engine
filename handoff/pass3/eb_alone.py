"""EnergyBalance alone on Earth's land and sea (preview mesh), flat ground, an albedo of 0.31 everywhere: how far the
land between 40 and 60 degrees north swings between January and July, under several spreading constants and heat
capacities of land. A diagnosis of one process by itself; nothing of the engine is changed.

    PYTHONPATH=src python handoff/pass3/eb_alone.py
"""
import numpy as np
import earth_reference as ref
from worldengine.testing import Harness

h = Harness(level=5)
m = h.mesh
lat, lon, height = ref.relief()
sea = ref.cell_means(m, lat, lon, height.astype(np.float64)) < 0.0
geo = h.run("PlanetGeometry").fields
sun = h.run("Insolation", reads={"latitude": geo["latitude"]}).fields["insolation"]
area = geo["cell_area"].astype(np.float64)
reads = {"insolation": sun, "albedo": np.full((12, m.n), 0.31), "ocean_mask": sea, "height_above_sea": np.zeros(m.n), "cell_area": geo["cell_area"]}
te = ref.at_cell_centres(m, *ref.temperature_monthly())
north, north_sea = ~sea & (m.lat > 40) & (m.lat < 60), sea & (m.lat > 40) & (m.lat < 60)
mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
print("July less January, K, between 40 and 60 degrees north: Earth's land %.1f, Earth's sea %.1f" % (mean(te[6] - te[0], north), mean(te[6] - te[0], north_sea)))
print(f"{'spreading D':>12s} {'land capacity':>14s} {'land':>7s} {'sea':>7s} {'land, warmest month less coldest':>34s}")
for d in (0.649, 0.45, 0.35, 0.2, 0.1, 0.0):
    for c in (1.055e7, 1.87e6):
        t = h.run("EnergyBalance", reads=reads, constants={"spreading_constant_w_m2_k": d, "heat_capacity_land_j_m2_k": c}).fields["surface_temperature"].astype(np.float64)
        series = np.array([mean(t[k], north) for k in range(12)])
        print(f"{d:12.3f} {c:14.3e} {mean(t[6] - t[0], north):7.1f} {mean(t[6] - t[0], north_sea):7.1f} {series.max() - series.min():34.1f}")
