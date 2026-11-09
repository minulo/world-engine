"""The same measurements on a world built in memory, as the test fixture builds it."""
import sys

sys.path.insert(0, HERE)
import measure  # noqa: E402

from worldengine import detail as dt  # noqa: E402
from worldengine import store  # noqa: E402
from worldengine.engine import Engine  # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR  # noqa: E402
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts

e = Engine(DEFAULT_DATA_DIR, profile="preview")
w = e.build()
view = store.MemoryView(w, e)
d = dt.refine(view, measure.region_of(view))
measure.report(d, view, "memory")
f = d.fields
print("   fine heights", f["elevation"].min(), f["elevation"].max())
