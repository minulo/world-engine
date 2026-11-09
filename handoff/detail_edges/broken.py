"""Would the new test fail if the feature broke? Variants of the new module, measured with the test's statistics."""
import sys
import types

import numpy as np
import yaml

sys.path.insert(0, HERE)
from measure import local_ratio, pairs, region_of, steps  # noqa: E402

from worldengine import detail as real  # noqa: E402
from worldengine import store  # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR  # noqa: E402
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts

view = store.StoreView(sys.argv[1])
region = region_of(view)
own = yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))
src = open(real.__file__).read()
offset = src.replace("        return values + bump * (left / coarse_mean(bump))[..., local]",
                     "        return values + left[..., local]")
assert offset != src
for label, text, consts in (("as built", src, own), ("no passes, bump", src, {**own, "mean_iterations": 0}),
                            ("no passes, offset per cell", offset, {**own, "mean_iterations": 0}),
                            ("12 passes, offset per cell", offset, own), ("4 passes, bump", src, {**own, "mean_iterations": 4})):
    mod = types.ModuleType("worldengine.detail_v")
    mod.__package__ = "worldengine"
    exec(compile(text, "detail_v", "exec"), mod.__dict__)
    mod.constants = lambda v, c=consts: c
    d = mod.refine(view, region)
    a, b, edge = pairs(d)
    f = d.fields
    r = [steps(d, x, a, b, edge) for x in (f["elevation"], f["surface_temperature"].mean(axis=0), np.log(f["precipitation"].sum(axis=0)))]
    lr, n = local_ratio(d, f["elevation"], a, b, edge)
    print(f"{label:28s} height {r[0][0] / r[0][1]:.3f} temperature {r[1][0] / r[1][1]:.3f} log rain {r[2][0] / r[2][1]:.3f} "
          f"height edge by edge {lr:.3f} ({n} edges)")
