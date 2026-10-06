"""Two things the notes quote that no tool prints: the shares of the climate groups under Earth's measured climate
(the Biomes test of tests/test_earth.py), and July less January over the land between 40 and 60 north of a world store."""
import sys
import numpy as np
import earth_reference as ref
P = lambda *a: print(*a, flush=True)
earth = ref.Earth(7)
out = earth.h.run("Biomes", reads={"surface_temperature": earth.celsius + 273.15, "precipitation": earth.rain, "ocean_mask": earth.wet})
names = earth.h.registry.fields["climate_class"].categories
group = np.array([n[0] for n in names])[out.fields["climate_class"]]
land_area = earth.area[earth.land].sum()
P("climate groups under Earth's measured climate, % of the mesh's land:", {g: round(100.0 * earth.area[earth.land & (group == g)].sum() / land_area, 1) for g in "ABCDE"})
from worldengine.store import StoreView
from worldengine.mesh import get_mesh
for path in sys.argv[1:]:
    v = StoreView(path)
    m = get_mesh(v.attrs["meta"]["mesh_level"])
    area, wet = v.field("cell_area").astype(np.float64), v.field("ocean_mask")
    t = v.field("surface_temperature").astype(np.float64)
    north = ~wet & (m.lat > 40) & (m.lat < 60)
    P(path.split("/")[-1], "July less January over land at 40 to 60 north: %.1f K" % (((t[6] - t[0]) * area)[north].sum() / area[north].sum()))
