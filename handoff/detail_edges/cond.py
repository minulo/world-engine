"""Section 21.2's conditions measured on the store, as the tests in tests/test_world.py compute them."""
import sys
import types

import numpy as np

sys.path.insert(0, HERE)
import measure  # noqa: E402

from worldengine import detail as dt  # noqa: E402
from worldengine import store  # noqa: E402
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts

if "--base" in sys.argv:
    dt = types.ModuleType("worldengine.detail_base")
    dt.__package__ = "worldengine"
    exec(compile(open(HERE + "/detail_base.py").read(),
                 "detail_base", "exec"), dt.__dict__)
if "--own" in sys.argv:
    import yaml
    from worldengine.params import DEFAULT_DATA_DIR
    dt.constants = lambda v: yaml.safe_load((DEFAULT_DATA_DIR / "detail.yaml").read_text(encoding="utf-8"))

view = store.StoreView(sys.argv[1])
coarse = dt.get_mesh(int(view.meta["mesh_level"]))
lat, lon, hs = (np.asarray(view.field(n)) for n in ("latitude", "longitude", "height_above_sea"))
k = int(np.argmax(np.where(np.abs(lat) < 50, hs, -1e9)))
centre = (float(lat[k]), float(lon[k]))
region = lambda dlat, dlon, km: dt.region_cells(coarse, centre[0] + dlat, centre[1] + dlon, km, view.attrs["planet"]["radius_m"])
d = dt.refine(view, region(0, 0, 800))
fine = dt.get_mesh(d.level)
for name in ("elevation", "surface_temperature", "precipitation"):
    gap = np.abs(d.coarse_means(name, fine.area) - np.asarray(view.field(name), dtype=np.float64)[..., d.region])
    print(f"largest gap {name}: {gap.max():.2g}")
recv, sea = np.asarray(view.field("flow_receiver")), np.asarray(view.field("ocean_mask")).astype(bool)
q = np.asarray(view.field("river_discharge"), dtype=np.float64).mean(axis=0)
at = {int(c): i for i, c in enumerate(d.cells)}
inside = set(d.region.tolist())
has_sea = {int(x) for x in d.owner[d.fields["ocean_mask"]]}
leaving = [x for x in d.region if not sea[x] and recv[x] >= 0 and recv[x] not in inside and x not in has_sea]
inland = [x for x in d.region if not sea[x] and recv[x] >= 0 and x not in has_sea]
ratio = lambda ks: np.array([d.fields["river_discharge"][at[d.outlets[x]]] / q[x] for x in ks if q[x] > 1.0])
ri, rl = ratio(inland), ratio(leaving)
print(f"inland cells {len(inland)}, with flow above 1 m3/s {ri.size}: ratios {ri.min():.4f} to {ri.max():.4f}; "
      f"leaving cells {len(leaving)}: ratios {rl.min() if rl.size else float('nan'):.4f} to {rl.max() if rl.size else float('nan'):.4f}")
print(f"cells with fine sea {len(has_sea)}; coast cells of land {len([x for x in d.region if not sea[x] and x in has_sea])}")
dry = [x for x in inland if q[x] == 0.0]
print("dry inland cells", len(dry), "all dry on fine cells", all(d.fields["river_discharge"][at[d.outlets[x]]] == 0.0 for x in dry))
ends = d.cells[d.fields["flow_receiver"] < 0]
print("ends allowed", set(ends.tolist()) <= set(d.outlets.values()) | set(d.cells[d.fields["ocean_mask"]].tolist()) | set(d.cells[sea[d.owner]].tolist()))
a, b = dt.refine(view, region(0, 0, 600)), dt.refine(view, region(4, 4, 600))
shared = np.intersect1d(a.cells, b.cells)
ia, ib = np.searchsorted(a.cells, shared), np.searchsorted(b.cells, shared)
same = all(a.fields[n][..., ia].tobytes() == b.fields[n][..., ib].tobytes() for n in a.fields)
print(f"overlap: {shared.size} shared fine cells, bit for bit {same}")
again = dt.refine(view, region(0, 0, 800))
print("twice identical", all(again.fields[n].tobytes() == d.fields[n].tobytes() for n in d.fields))
