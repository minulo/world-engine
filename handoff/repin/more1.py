import json, sys
import numpy as np
import earth_reference as ref
P = lambda *a: print(*a, flush=True)
earth = ref.Earth(7)
flood = ref.raw_flood()
for name, place in (("the Black Sea", (43.0, 34.0)), ("the Baltic", (58.0, 20.0)), ("the Great Lakes", (47.5, -87.0)), ("the Caspian", ref.CASPIAN)):
    lake = earth.lake_at(*place)
    P(name, "lake: %.0f km2 at %.1f m, overflows %s" % (lake["area_m2"] / 1e6, lake["level_m"], bool(lake["overflows"])), "| data at the place:", ref.raw_at(flood, *place))
    k = ref.kept_apart(earth, flood, place)
    P("   kept apart:", {a: (round(b, 3) if isinstance(b, float) else b) for a, b in k.items()})
    lakes = earth.hydrology().tables["lakes"]
    which = np.asarray(earth.hydrology().drivers["lake_fraction"]["lake"]).astype(np.int64)
    row = int(which[earth.cell(*place)])
    oc = int(lakes["outlet_cell"][row])
    if oc >= 0:
        share = ref.data_points_of_cells(earth, flood)["ocean_share"]
        P("   outlet cell %d at %.1f, %.1f: mean %.1f m, handed %.1f m, ocean share %.3f" % (oc, earth.mesh.lat[oc], earth.mesh.lon[oc], earth.mean[oc], earth.ground[oc], share[oc]))
f = earth.hydrology().fields
lakes = earth.hydrology().tables["lakes"]
big = np.flatnonzero(lakes["area_m2"] > 1e11)
which = np.asarray(earth.hydrology().drivers["lake_fraction"]["lake"]).astype(np.int64)
tot = 0.0
for row in big:
    cells = np.flatnonzero((which == row) & (f["lake_fraction"] > 0))
    # deepest cell of the lake by handed ground
    c = int(cells[np.argmin(earth.ground[cells])])
    lat, lon = float(earth.mesh.lat[c]), float(earth.mesh.lon[c])
    d = ref.raw_at(flood, lat, lon)
    # share of the lake's cells whose nearest data point lies in a data hollow (level above height, not ocean)
    inh = 0
    for k in cells:
        r = ref.raw_at(flood, float(earth.mesh.lat[k]), float(earth.mesh.lon[k]))
        inh += (not r["ocean"]) and r["level"] > r["height"]
    tot += lakes["area_m2"][row] / 1e6
    P("big lake row %d: %.0f km2 at %.0f m, overflows %s; deepest cell at %.1f, %.1f; data there %s; cells %d, of them in a hollow of the data %d" % (
        row, lakes["area_m2"][row] / 1e6, lakes["level_m"][row], bool(lakes["overflows"][row]), lat, lon, d, len(cells), inh))
w = ref.land_water(earth)
P("big lakes: %d, together %.0f km2, share of all lakes %.4f; lakes %.0f km2, %.4f of land" % (len(big), tot, tot / w["lakes_km2"], w["lakes_km2"], w["lakes_share"]))
air = f["evapotranspiration"].astype(np.float64).sum(axis=0)[earth.cell(*ref.CASPIAN)]
P("open water at the Caspian's place: %.1f mm; lake fraction there %.3f" % (air, f["lake_fraction"][earth.cell(*ref.CASPIAN)]))
b = ref.lake_books(earth)
P("lake_books:", json.dumps({k: (round(x, 3) if isinstance(x, float) else x) for k, x in b.items()}))
P("inflow km3 %.2f" % (earth.lake_at(*ref.CASPIAN)["inflow_m3_per_year"] / 1e9))
