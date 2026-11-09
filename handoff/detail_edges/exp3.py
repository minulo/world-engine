import sys
import numpy as np
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts
exec(open(HERE + "/exp_core.py").read().split("li, lw = linear_weights()")[0])
li, lw = linear_weights()
gi, gw = gauss_weights(0.6)
reg = set(region.tolist())
interior = np.array([k for k in region if all((n < 0) or (int(n) in reg) for n in coarse.nbr[k])])
print("region", region.size, "interior cells", interior.size)
oa, ob = own[cells[a_]], own[cells[b_]]
for name, s in (("world z", z),):
    for kn, (ii, ww) in (("linear", (li, lw)), ("gauss", (gi, gw))):
        h = interp(ii, ww, s)
        d = np.abs(h[a_] - h[b_])
        # 1. inside pairs only in interior cells; edge pairs with both owners interior
        ins = (~edge) & np.isin(oa, interior)
        eds = edge & np.isin(oa, interior) & np.isin(ob, interior)
        print(f"{kn:7s} all: {np.median(d[edge])/np.median(d[~edge]):.3f}   interior only: {np.median(d[eds])/np.median(d[ins]):.3f} ({eds.sum()} / {ins.sum()})")
        # 2. per coarse edge: median across k|j over median inside k and j
        r = []
        for k in region:
            for j in coarse.nbr[k]:
                j = int(j)
                if j > k and j in reg:
                    m = edge & (((oa == k) & (ob == j)) | ((oa == j) & (ob == k)))
                    n = (~edge) & ((oa == k) | (oa == j))
                    if m.any():
                        r.append(np.median(d[m]) / np.median(d[n]))
        print(f"         per world-cell edge, median of local ratios: {np.median(r):.3f} over {len(r)} edges")
