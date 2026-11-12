"""The gaps the passes leave before the last bump, for several numbers of passes and relaxations."""
import sys
import time
import types

import numpy as np
import yaml

sys.path.insert(0, HERE)
from measure import region_of  # noqa: E402

from worldengine import detail as real  # noqa: E402
from worldengine import store  # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR  # noqa: E402
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts

src = open(real.__file__).read()
src = src.replace("        left = target[..., inner] - coarse_mean(values)\n",
                  "        left = target[..., inner] - coarse_mean(values)\n"
                  "        RECORD.append(np.abs(left[..., np.searchsorted(inner, region)]).max())\n")
src = src.replace("    total = coarse_mean(rain)\n", "    total = coarse_mean(rain)\n"
                  "    RECORD.append(np.abs(total[:, np.searchsorted(inner, region)] / p[:, region] - 1).max())\n")
assert src.count("RECORD") == 2
mod = types.ModuleType("worldengine.detail_x")
mod.__package__ = "worldengine"
mod.RECORD = []
exec(compile(src, "detail_x", "exec"), mod.__dict__)
view = store.StoreView(sys.argv[1])
own = yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))
regions = [("section 21", region_of(view))]
lat, lon = np.asarray(view.field("latitude")), np.asarray(view.field("longitude"))
for k in (100, 2000, 5000, 7777, 9000):
    regions.append((f"at cell {k} ({lat[k]:.0f}, {lon[k]:.0f})",
                    real.region_cells(real.get_mesh(5), float(lat[k]), float(lon[k]), 600, view.attrs["planet"]["radius_m"])))
settings = [(int(a), float(b)) for a, b in (x.split(":") for x in sys.argv[2:])] or [(8, 1.0), (8, 1.4), (12, 1.4), (16, 1.4)]
for name, region in regions:
    for n, w in settings:
        mod.RECORD.clear()
        mod.constants = lambda v, n=n, w=w: {**own, "mean_iterations": n, "relaxation": w}
        t0 = time.time()
        d = mod.refine(view, region)
        h, t, r = mod.RECORD
        print(f"{name:28s} passes {n:2d} relax {w}: left height {h:.3g} m, temperature {t:.3g} K, rain share {r:.3g}; "
              f"rain min {d.fields['precipitation'].min():.3g}; {time.time() - t0:.1f} s, {d.cells.size} fine cells")
