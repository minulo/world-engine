"""More facts for the rewritten Earth tests, and one diagnosis: the valley rule with the ocean's points of a cell
counted at the level of the mesh's sea."""
import json
import numpy as np
import earth_reference as ref
from worldengine.library import drainage as dr
P = print
earth = ref.Earth(7)
flood = ref.raw_flood()
m = earth.mesh
h = earth.hydrology()
flow = earth.yearly_flow()
g = ref.rivers_at_gauges(earth)
for river in ("Yenisei", "Lena", "Mekong", "Amur", "St Lawrence", "Danube", "Congo", "Yangtze", "Mackenzie", "Orinoco", "Niger", "Zambezi", "Indus", "Ganges", "Ob", "Amazon", "Mississippi", "Parana", "Columbia", "Rhine"):
    way = [c for c in ref.way_of(earth, river) if c["step"] != "sea"]
    lat, lon = ref.GAUGES[river][:2]
    near = min(way, key=lambda c: earth.km(c["cell"], lat, lon))
    on_way = g[river]["cell"] in {c["cell"] for c in way}
    best = max(way, key=lambda c: flow[c["cell"]])
    P("%-12s way nearest its station: %.0f km, at %.1f, %.1f, flow there %.0f km3; gauge cell on the way: %s (flow %.0f, %.0f km from station); largest flow on the way %.0f at %.1f, %.1f" % (
      river, earth.km(near["cell"], lat, lon), near["lat"], near["lon"], flow[near["cell"]], on_way, g[river]["flow"], earth.km(g[river]["cell"], lat, lon), flow[best["cell"]], best["lat"], best["lon"]))
ob = [c for c in ref.way_of(earth, "Ob") if c["step"] != "sea"]
P("Ob beyond 67 N:", [(round(c["lat"], 1), round(c["lon"], 1), c["step"], c["lake_level_m"]) for c in ob if c["lat"] > 67.0])
hh = [c for c in ref.way_of(earth, "Huang He") if c["step"] != "sea"]
P("Huang He: northmost %.1f at lon %.1f; last land cell %.1f, %.1f" % (max(c["lat"] for c in hh), max(hh, key=lambda c: c["lat"])["lon"], hh[-1]["lat"], hh[-1]["lon"]))
am = [c for c in ref.way_of(earth, "Amur") if c["step"] != "sea"]
P("Amur: last land cell %.1f, %.1f" % (am[-1]["lat"], am[-1]["lon"]))
ya = [c for c in ref.way_of(earth, "Yangtze") if c["step"] != "sea"]
P("Yangtze between 108 and 112.5 E: lats", [round(c["lat"], 1) for c in ya if 108.0 < c["lon"] < 112.5])
le = [c for c in ref.way_of(earth, "Lena") if c["step"] != "sea"]
P("Lena north of 70: lons", [round(c["lon"], 1) for c in le if c["lat"] > 70.0])
lakes = h.tables["lakes"]
i = int(h.drivers["lake_fraction"]["lake"][earth.cell(44.7, 20.4)])
P("lake above the Iron Gate: row %d, %.0f km2 at %.0f m, loss to air %.1f km3, inflow %.1f, outflow %.1f" % (i, lakes["area_m2"][i] / 1e6, lakes["level_m"][i], lakes["loss_to_air_m3_per_year"][i] / 1e9, lakes["inflow_m3_per_year"][i] / 1e9, lakes["outflow_m3_per_year"][i] / 1e9))
P("lakes table keys:", sorted(lakes))
# ---- the diagnosis: the ocean's points of a cell counted at the level of the mesh's sea
lat, lon, height = flood["lat"], flood["lon"], flood["height"]
cells = ref.cell_of_every_point(m, lat, lon)
counted = np.where(flood["ocean"], earth.sea_level, np.where(height > earth.sea_level, height, np.nan)).astype(np.float64)
floors = ref.cell_low_values(m, lat, lon, counted, earth.valley_share, cells)
ground = np.where(np.isfinite(floors), floors, earth.mean)
other = earth.with_ground(ground)
P("\nDIAGNOSIS: ocean points counted at the sea's level (%.2f m)" % earth.sea_level)
P("   land cells handed in otherwise: %d of %d; at the sea's level: %d (as built %d at or below it)" % ((other.ground != earth.ground)[earth.land].sum(), earth.land.sum(),
  (earth.land & (np.abs(other.ground - earth.sea_level) < 1e-3)).sum(), (earth.land & (earth.ground <= earth.sea_level)).sum()))
for name, e in (("as built", earth), ("sea points at sea level", other)):
    s = ref.summary(e)
    w = ref.land_water(e)
    near = sum(km < 300.0 for km in s["mouth_km"].values())
    within = sum(ref.within_a_factor_of_two(ref.GAUGES[r][2], f) for r, f in s["flow"].items())
    P("   %-24s mouths %d of 24; gauges %d of 21; like %.3f; back to air %.4f; to sea %.2f; lakes %.2f %% of land; Caspian %s" % (name, near, within, s["like_all"], w["back_to_air"], w["to_sea"], 100 * w["lakes_share"], s["caspian"]))
    P("      mouths:", {r: round(km) for r, km in s["mouth_km"].items()})
    P("      flows:", {r: round(f) for r, f in s["flow"].items()})
    for nm, place in (("Black Sea", (43.0, 34.0)), ("Baltic", (58.0, 20.0)), ("Great Lakes", (47.5, -87.0))):
        L = ref.lake_books(e, place)
        P("      %-12s %s" % (nm, None if L is None else (round(L["area_km2"]), L["level_m"], L["overflows"], L["overflow"]["ends"])))
    n = ref.narrows(e)
    P("      narrows:", {r: (round(x["barrier_m"]), None if x["lake_level_m"] is None else round(x["lake_level_m"])) for r, x in n.items()})
    mh = ref.mesh_hollows(e)
    P("      under water if full %.4f; closed hollow share %.4f; land at or below the sea's level %d" % (mh["under_share"], mh["closed_hollow_share"], (e.land & (e.ground <= earth.sea_level)).sum()))
