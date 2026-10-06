"""Facts that the rewritten Earth tests state, measured on the working tree."""
import dataclasses, json, sys
import numpy as np
import yaml
import earth_reference as ref
from worldengine.library import drainage as dr
P = print
earth = ref.Earth(7)
flood = ref.raw_flood()
m = earth.mesh
held = ref.data_points_of_cells(earth, flood)
h = earth.hydrology()
lakes = h.tables["lakes"]
lake_of = h.drivers["lake_fraction"]["lake"]
frac = h.fields["lake_fraction"].astype(np.float64)
g = ref.rivers_at_gauges(earth)
# Q1 the Danube's gauge
c = g["Danube"]["cell"]
row = int(lake_of[c])
P("Q1 Danube gauge cell %d at %.1f, %.1f; km from station %.0f; lake row %d; lake fraction %.2f; ground %.0f mean %.1f" % (c, m.lat[c], m.lon[c], earth.km(c, 45.2, 28.7), row, frac[c], earth.ground[c], earth.mean[c]))
if row >= 0:
    P("   lake there: %.0f km2 at %.0f m; overflows %s" % (lakes["area_m2"][row] / 1e6, lakes["level_m"][row], bool(lakes["overflows"][row])))
P("   gauge row:", json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in g["Danube"].items()}))
b = ref.river_books(earth)
P("   river books keys:", sorted(b))
for name in ("Lena", "Indus", "Niger", "Zambezi", "Mekong", "Yenisei", "Congo", "Amur", "Yangtze", "Mackenzie", "St Lawrence", "Orinoco", "Brahmaputra", "Ganges"):
    c = g[name]["cell"]; row = int(lake_of[c])
    P("   %-12s gauge cell at %.1f, %.1f (%.0f km from the station); lake row %d fraction %.2f%s" % (name, m.lat[c], m.lon[c], earth.km(c, *ref.GAUGES[name][:2]), row, frac[c],
      "" if row < 0 else "; lake %.0f km2 at %.0f m, overflows %s" % (lakes["area_m2"][row] / 1e6, lakes["level_m"][row], bool(lakes["overflows"][row]))))
# Q2 the seas as lakes
for name, place in (("Black Sea", (43.0, 34.0)), ("Baltic", (58.0, 20.0)), ("Great Lakes", (47.5, -87.0)), ("Caspian", ref.CASPIAN), ("Congo", (-3.0, 16.5))):
    L = ref.lake_books(earth, place)
    c = L["outlet_cell"]
    P("Q2 %-12s %s" % (name, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in L.items() if k != "overflow"})), L["overflow"])
    if c >= 0:
        P("    outlet cell %d at %.1f, %.1f: ocean share %.2f, mean %.1f, handed %.0f, wet %s" % (c, m.lat[c], m.lon[c], held["ocean_share"][c], earth.mean[c], earth.ground[c], bool(earth.wet[c])))
# what the Black Sea's outlet cell would be handed in at with every point counted
bs = ref.lake_books(earth, (43.0, 34.0))["outlet_cell"]
P("   Black Sea outlet: every-point height %.1f" % held["every_point"][bs])
# Q3 level ground drawn
other = earth.settled(3)
given = other._ties()
surface, full = other.full_ways()
with_level = dr.receivers(surface, earth.wet, m.nbr, earth.ground, given)
without = dr.receivers(surface, earth.wet, m.nbr, earth.ground, given._replace(level=None))
diff = np.flatnonzero(with_level != without)
lev = lambda recv, cells: bool(np.all(surface[recv[cells]] == surface[cells]))
P("Q3 level drawn: differing cells %d; all on level ground under both: %s %s; given.level shape %s; equal to Drainage's field: %s" % (diff.size, lev(with_level, diff), lev(without, diff), given.level.shape,
  np.array_equal(other.drainage.fields["flow_receiver"], with_level)))
handed = other.books()["ties"]
P("   Hydrology handed level: %s; equal: %s; own earth ties level: %s" % (handed.level is not None, handed.level is not None and np.array_equal(handed.level, given.level), earth.books()["ties"].level))
t = ref.tie_counts(earth)
P("   level cells (tie_counts): %d" % t["level"])
# Q6 the Caspian hollow with every hollow full
label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
top = dr.top_hollows(table)[label]
cc = earth.cell(*ref.CASPIAN)
P("Q6 Caspian: hollow %d, top hollow %d, spill of the top %.0f m; own hollow spill %.0f m; parent %d" % (label[cc], top[cc], table["spill_m"][top[cc]], table["spill_m"][label[cc]], table["parent"][label[cc]]))
vw = ref.way_of(earth, "Volga")
P("   Volga way: steps", [(round(c["lat"], 1), round(c["lon"], 1), c["step"], c["ground_m"]) for c in vw if c["step"] == "down"])
# Q7 the Yenisei's and the Ob's ways through cells that the data have as ocean
for river in ("Yenisei", "Ob", "Danube", "Amazon"):
    w = [c for c in ref.way_of(earth, river) if c["step"] != "sea"]
    P("Q7 %s way keys %s" % (river, sorted(w[0])))
    P("   cells whose centre is ocean in the data: %d of %d" % (sum(bool(ref.raw_at(flood, c["lat"], c["lon"])["ocean"]) for c in w), len(w)))
    P("   nearest to its mouth %.0f km; last land cell at %.1f, %.1f" % (min(c["km_to_mouth"] for c in w), w[-1]["lat"], w[-1]["lon"]))
# Q9 the Amazon's last cells
w = ref.way_of(earth, "Amazon")
P("Q9 Amazon end:", [(round(c["lat"], 1), round(c["lon"], 1), c["step"], c["ground_m"], round(c["mean_m"], 1) if "mean_m" in c else None, round(c["km_to_mouth"])) for c in w[-3:]])
# Q4 tally
out = [ref.summary(earth.settled(s)) for s in range(1, 21)]
T = ref.tally(out)
P("Q4 tally keys:", sorted(T)); P("   caspian_closed %s caspian_to_sea %s" % (T["caspian_closed"], T.get("caspian_to_sea")))
P("   summary caspian keys:", sorted(ref.summary(earth)["caspian"]))
P("   engine caspian:", ref.summary(earth)["caspian"])
