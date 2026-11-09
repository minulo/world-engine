"""Experiments on the height field of the detail: which part of the edge steps comes from the kernel, which from the
last correction. Prints the median steps across edges and inside, and the largest residual before the last correction."""
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from measure import region_of  # noqa: E402

from worldengine import detail as dt
from worldengine import store
from worldengine.mesh import get_mesh

view = store.StoreView(sys.argv[1])
region = np.unique(region_of(view))
c = dt.constants(view)
coarse = get_mesh(int(view.meta["mesh_level"]))
fine = get_mesh(coarse.level + 2)
own, order, start = dt._owners(coarse, fine)
RINGS = 40
inner = dt._grow(coarse, region, RINGS)
cells = np.sort(np.concatenate([order[start[k]:start[k + 1]] for k in inner]))
local = np.searchsorted(inner, own[cells])
area = fine.area[cells]
z = np.asarray(view.field("elevation"), dtype=np.float64)


def coarse_mean(v):
    return np.bincount(local, weights=area * v, minlength=inner.size) / np.bincount(local, weights=area, minlength=inner.size)


# Gaussian weights over the second ring of the owner
foot = dt._grow(coarse, inner, 3)
ring = dt._second_ring(coarse, foot)
where = np.full(coarse.n, -1); where[foot] = np.arange(foot.size)
cand = ring[where[own[cells]]]


def gauss_weights(sig):
    d2 = ((fine.xyz[cells][:, None, :] - coarse.xyz[np.maximum(cand, 0)]) ** 2).sum(axis=-1)
    sigma = sig * coarse.spacing()
    w = np.where(cand >= 0, np.exp(-d2 / (sigma * sigma)), 0.0)
    return np.maximum(cand, 0), w / w.sum(axis=1, keepdims=True)


# barycentric weights in the triangles of world-cell centres around the owner
faces = coarse.faces
inc = [[] for _ in range(coarse.n)]
for fi, (a, b, cc) in enumerate(faces):
    inc[a].append(fi); inc[b].append(fi); inc[cc].append(fi)


def linear_weights():
    idx = np.zeros((cells.size, 3), dtype=np.int64)
    w = np.zeros((cells.size, 3))
    worst = 1.0
    for i, f in enumerate(cells):
        p = fine.xyz[f]
        best = None
        for fi in inc[own[f]]:
            tri = faces[fi]
            A = coarse.xyz[tri].T
            lam = np.linalg.solve(A, p)
            lam = lam / lam.sum()
            if best is None or lam.min() > best[1].min():
                best = (tri, lam)
        worst = min(worst, best[1].min())
        idx[i] = best[0]
        w[i] = np.maximum(best[1], 0.0) / np.maximum(best[1], 0.0).sum()
    print(f"   smallest barycentric coordinate before clipping {worst:.3g}")
    return idx, w


def interp(idx, w, values):
    return (w * values[idx]).sum(axis=1)


spread = np.zeros(coarse.n)
one = np.concatenate([foot[:, None], coarse.nbr[foot]], axis=1)
spread[foot] = np.array([z[r[r >= 0]].std() for r in one])
lengths = (c["wave_lengths_in_spacings"][0] * coarse.spacing(), c["wave_lengths_in_spacings"][1] * coarse.spacing())
waves = dt._waves(int(view.attrs["seed"]), fine.xyz[cells], int(c["waves"]), lengths)

keep = np.isin(own[cells], region)
pos = {int(x): i for i, x in enumerate(cells)}
a_, b_ = [], []
for i in np.flatnonzero(keep):
    for g in fine.nbr[cells[i]]:
        g = int(g)
        if g > cells[i] and g in pos and keep[pos[g]]:
            a_.append(i); b_.append(pos[g])
a_, b_ = np.array(a_), np.array(b_)
edge = own[cells[a_]] != own[cells[b_]]


def steps(h):
    d = np.abs(h[a_] - h[b_])
    return np.median(d[edge]), np.median(d[~edge])


li, lw = linear_weights()
gi, gw = gauss_weights(0.6)
rng = np.random.default_rng(1)
for name, s in (("iid", rng.normal(size=coarse.n)), ("planar x", coarse.xyz[:, 0] * 1.0), ("planar z", coarse.xyz[:, 2] * 1.0), ("world z", z)):
    for kn, (ii, ww) in (("linear", (li, lw)), ("gauss", (gi, gw))):
        h = interp(ii, ww, s)
        e, i = steps(h)
        print(f"{name:10s} {kn:7s} across {e:.4g} inside {i:.4g} ratio {e/i:.3f}")
# the direction mix: pair length
L = np.linalg.norm(fine.xyz[cells[a_]] - fine.xyz[cells[b_]], axis=1)
print("pair length median edge", np.median(L[edge]), "inside", np.median(L[~edge]))
