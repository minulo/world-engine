"""A trial outside the engine: the equation of EnergyBalance solved with a spreading that varies with latitude and
surface, in the form and with the constants of Ziegler and Rehfeld 2021 (equation 2 and Table 1, read out by a page
reader on 2026-10-06): over sea 0.90 at the equator falling to 0.40 at the poles, over northern land 0.65 to 0.45,
over southern land 0.65 to 0.12, each as (equator - pole) * cos(latitude)^5 + pole. Between two cells the spreading
is the mean of the two. Earth's land and sea on the preview mesh, flat ground, an albedo of 0.31 everywhere.

    PYTHONPATH=src python handoff/pass3/eb_varying.py
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import earth_reference as ref
from worldengine.testing import Harness

h = Harness(level=5)
m = h.mesh
lat, lon, height = ref.relief()
sea = ref.cell_means(m, lat, lon, height.astype(np.float64)) < 0.0
geo = h.run("PlanetGeometry").fields
sun = h.run("Insolation", reads={"latitude": geo["latitude"]}).fields["insolation"].astype(np.float64)
area = geo["cell_area"].astype(np.float64)
steradians = area / ref.EARTH_RADIUS_M ** 2
te = ref.at_cell_centres(m, *ref.temperature_monthly())
mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
YEAR = ref.YEAR_S


def solve(d_cell, c_land, c_sea, a, b, albedo=0.31, waves=2):
    i, j = m.edge_cells[:, 0], m.edge_cells[:, 1]
    w = (m.edge_dual / m.edge_dist) * 0.5 * (d_cell[i] + d_cell[j])
    lap = sp.csr_matrix((np.concatenate([w, w, -w, -w]), (np.concatenate([i, j, i, j]), np.concatenate([j, i, i, j]))), shape=(m.n, m.n))
    cap = np.where(sea, c_sea, c_land)
    spectrum = np.fft.rfft(sun * (1 - albedo) - a, axis=0) / 12
    answer = np.zeros_like(spectrum)
    for k in range(waves + 1):
        diag = steradians * (b + 1j * k * 2 * np.pi / YEAR * cap)
        answer[k] = spla.splu((sp.diags(diag) - lap).tocsc()).solve(steradians * spectrum[k])
    return np.fft.irfft(answer * 12, n=12, axis=0)


def report(name, t):
    out = []
    for lo, hi in ((40, 60), (20, 40), (60, 90)):
        land, water = ~sea & (m.lat > lo) & (m.lat < hi), sea & (m.lat > lo) & (m.lat < hi)
        out.append(f"{mean(t[6] - t[0], land):6.1f} {mean(t[6] - t[0], water):6.1f}")
    everywhere = np.ones(m.n, dtype=bool)
    eq, pole = np.abs(m.lat) < 10, m.lat > 70
    print(f"{name:58s} " + "   ".join(out) + f"   {mean(t.mean(axis=0), everywhere):6.1f} {mean(t.mean(axis=0), eq) - mean(t.mean(axis=0), pole):6.1f}")


x = np.cos(np.deg2rad(m.lat)) ** 5
varying = np.where(sea, (0.90 - 0.40) * x + 0.40, np.where(m.lat >= 0, (0.65 - 0.45) * x + 0.45, (0.65 - 0.12) * x + 0.12))
print(f"{'July less January, K: land and sea at':58s} {'40-60 N':>13s}   {'20-40 N':>13s}   {'60-90 N':>13s}   {'globe':>6s} {'equator less north pole':>6s}")
report("Earth (the temperature data; heights and all)", te)
report("engine's constants: D 0.649, land 1.055e7, sea 3.10e8", solve(np.full(m.n, 0.649), 1.055e7, 3.10e8, 203.3, 2.09))
report("spreading as Ziegler and Rehfeld, the engine's capacities", solve(varying, 1.055e7, 3.10e8, 203.3, 2.09))
report("... and their capacities (land 1.87e6, sea 3.94e8)", solve(varying, 1.87e6, 3.9447e8, 203.3, 2.09))
report("... and their A 210.2 and B 2.13", solve(varying, 1.87e6, 3.9447e8, 210.2, 2.13))
report("engine's D, a sea of 25 m (1.03e8)", solve(np.full(m.n, 0.649), 1.055e7, 1.03e8, 203.3, 2.09))
report("Z and R spreading, land 1.87e6, a sea of 25 m", solve(varying, 1.87e6, 1.03e8, 203.3, 2.09))
