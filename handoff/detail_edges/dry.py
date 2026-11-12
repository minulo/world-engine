"""Rain with dry cells and sharp contrasts: the means must hold, no rain may fall below zero."""
import sys

import numpy as np

sys.path.insert(0, HERE)
from measure import region_of  # noqa: E402

from worldengine import detail as dt  # noqa: E402
from worldengine import store  # noqa: E402
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts


class Dry:
    def __init__(self, view, rain):
        self.v, self.rain = view, rain
        self.attrs, self.meta = view.attrs, view.meta

    def field(self, name):
        return self.rain if name == "precipitation" else self.v.field(name)

    def table(self, name):
        return self.v.table(name)


view = store.StoreView(sys.argv[1])
region = region_of(view)
p = np.asarray(view.field("precipitation"), dtype=np.float64).copy()
near = dt._grow(dt.get_mesh(5), region, 2)
p[:, near[::3]] = 0.0                                     # every third cell nearby: no rain at all
p[:, near[1::3]] *= 1000.0                                # and others a thousand times wetter
for label, rain in (("dry and wet cells", p), ("tiny rain", np.where(p == 0, 1e-6, p))):
    d = dt.refine(Dry(view, rain), region)
    fine = dt.get_mesh(d.level)
    got = d.coarse_means("precipitation", fine.area)
    want = rain[:, d.region]
    print(f"{label}: min fine rain {d.fields['precipitation'].min():.3g}, largest relative gap "
          f"{np.max(np.abs(got - want) / np.maximum(want, 1e-300)):.3g}, largest gap {np.abs(got - want).max():.3g}, "
          f"dry cells all dry {bool(np.all(d.fields['precipitation'][:, np.isin(d.owner, d.region[want[0] == 0])] == 0))}, "
          f"finite {bool(np.isfinite(d.fields['precipitation']).all())}")
