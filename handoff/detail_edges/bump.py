"""The height of the last bump at the fine cells of the region, with the engine's constants."""
import sys
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
old = "        return values + bump * (left / coarse_mean(bump))[..., local]\n"
assert old in src
src = src.replace(old, "        added = bump * (left / coarse_mean(bump))[..., local]\n"
                       "        RECORD.append(np.abs(added[..., np.isin(owner, region)]).max())\n" + old)
mod = types.ModuleType("worldengine.detail_b")
mod.__package__ = "worldengine"
mod.RECORD = []
exec(compile(src, "detail_b", "exec"), mod.__dict__)
own = yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))
mod.constants = lambda v: own
view = store.StoreView(sys.argv[1])
mod.refine(view, region_of(view))
print("largest bump on the region's fine cells: height %.3g m, temperature %.3g K" % tuple(mod.RECORD))
