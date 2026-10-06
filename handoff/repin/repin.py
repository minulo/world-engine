"""Every number that tests/test_earth.py pins, measured again with the harness of the snapshot (the relief's own sea
water; level ground drawn), and printed as the literals of the test file. Run in the snapshot:
    PYTHONPATH=<snapshot>/src python repin.py > repin.log"""
import json
import sys
import numpy as np
import earth_reference as ref
from worldengine.library import drainage as dr

SETTLEMENTS = 20
earth = ref.Earth(7)
flood = ref.raw_flood()
out = {"engine": ref.summary(earth)}
for seed in range(1, SETTLEMENTS + 1):
    out[seed] = ref.summary(earth.settled(seed))
drawn = [out[s] for s in range(1, SETTLEMENTS + 1)]
P = print
P("sea level %.3f; sea share %.4f; land cells %d; sea volume %.6e" % (earth.sea_level, earth.area[earth.wet].sum() / earth.area.sum(), earth.land.sum(), earth.sea_volume))
seas = earth.sea.tables["seas"]
P("main sea's share of the water %.5f; bodies of water %d" % (seas["volume_m3"][0] / seas["volume_m3"].sum(), len(seas["volume_m3"])))
for name, place in {"the Mediterranean": (35.0, 18.0), "the Gulf of Mexico": (25.0, -90.0), "Hudson Bay": (60.0, -85.0), "the Sea of Japan": (40.0, 135.0),
                    "Tibet": (33.0, 88.0), "the Sahara": (23.0, 5.0), "the Amazon lowland": (-3.0, -60.0), "the Caspian": (42.0, 51.0),
                    "the Black Sea": (43.0, 34.0), "the Red Sea": (20.0, 38.5), "the Baltic": (58.0, 20.0)}.items():
    P("   %-20s sea on the mesh: %s; data: %s" % (name, bool(earth.wet[earth.cell(*place)]), ref.raw_at(flood, *place)))
basin = earth.drainage.fields["basin_id"]
area = earth.drainage.fields["drainage_area"]
amazon, nile = int(basin[earth.cell(-3.1, -60.0)]), int(basin[earth.cell(15.6, 32.5)])
P("Amazon: %.0f km, drains %.3e m2; Nile: %.0f km, drains %.3e m2" % (earth.km(amazon, -0.5, -50.0), area[amazon], earth.km(nile, 31.5, 31.0), area[nile]))
P("within 600 km in 20: Amazon %d, Nile %d" % (sum(r["mouth_km"]["Amazon"] < 600 for r in drawn), sum(r["mouth_km"]["Nile"] < 600 for r in drawn)))
desert = [c for c in ref.way_of(earth, "Nile") if 26.0 < c["lat"] < 30.0]
P("Nile between 26 and 30 north: lons", [round(c["lon"], 1) for c in desert])
f, t = earth.drainage.fields, earth.drainage.tables["hollows"]
tarim, great_basin = earth.cell(39.0, 83.0), earth.cell(40.0, -116.5)
bottom = int(t["bottom_cell"][f["depression_id"][tarim]])
P("Tarim hollow %d, Great Basin hollow %d; Tarim bottom %.0f km from Lop Nur at %.0f m" % (f["depression_id"][tarim], f["depression_id"][great_basin], earth.km(bottom, 40.2, 90.5), t["bottom_m"][f["depression_id"][tarim]]))
near = lambda r, river: r["mouth_km"][river] < ref.MOUTH_WITHIN_KM
mouths = {river: (round(out["engine"]["mouth_km"][river]), sum(near(r, river) for r in drawn)) for river in ref.GREAT_RIVERS}
P("MOUTHS =", mouths)
counts = [sum(near(r, river) for river in mouths) for r in drawn]
P("mouths passing: engine %d; random %d to %d; all %d none %d some %s" % (sum(near(out["engine"], r) for r in mouths), min(counts), max(counts),
  sum(k == SETTLEMENTS for _, k in mouths.values()), sum(k == 0 for _, k in mouths.values()), sorted(r for r, (_, k) in mouths.items() if 0 < k < SETTLEMENTS)))
P("spread of mouths:", {river: (round(min(r["mouth_km"][river] for r in drawn)), round(max(r["mouth_km"][river] for r in drawn))) for river in mouths})
P("Ob: nearest to its mouth on its way %.0f km" % min(c["km_to_mouth"] for c in ref.way_of(earth, "Ob") if c["step"] != "sea"))
gulf = [(lat, 73.3) for lat in (67.5, 68.0, 69.0, 69.5, 70.0, 70.5, 71.0)]
P("Gulf of Ob: data", [(ref.raw_at(flood, *p)["ocean"], ref.raw_at(flood, *p)["height"]) for p in gulf], "mesh sea", [bool(earth.wet[earth.cell(*p)]) for p in gulf],
  "means", [round(float(earth.mean[earth.cell(*p)]), 1) for p in gulf])
for river in ("Yenisei", "Huang He", "Mekong", "Nile", "Yangtze", "Lena", "Amazon", "Danube"):
    way = [c for c in ref.way_of(earth, river) if c["step"] != "sea"]
    P("%s way: %d land cells; lake %d; level %d; down %d" % (river, len(way), sum(c["step"] == "lake" for c in way), sum(c["step"] == "level" for c in way), sum(c["step"] == "down" for c in way)))
west = [c for c in ref.way_of(earth, "Yenisei") if 66.2 < c["lat"] < 67.2]
P("Yenisei between 66.2 and 67.2 north:", [(c["step"], c["ground_m"], round(c["lon"], 1)) for c in west])
found = ref.narrows(earth)
P("NARROWS_ON_THE_MESH =", {river: (round(r["barrier_m"]), None if r["lake_level_m"] is None else round(r["lake_level_m"])) for river, r in found.items()})
P("narrows detail:", json.dumps({k: {a: (b if not isinstance(b, tuple) else [round(x, 1) for x in b]) for a, b in v.items()} for k, v in found.items()}))
raw = ref.raw_narrows(flood)
P("NARROWS_IN_THE_DATA =", {river: (r["start_m"], r["barrier_m"], r["to_ocean_m"]) for river, r in raw.items()})
held = ref.data_points_of_cells(earth, flood)
share, land = held["ocean_share"], earth.land
closing = [earth.cell(47.3, -70.6), earth.cell(47.4, -69.9)]
P("St Lawrence closing cells:", [(bool(land[c]), round(float(earth.ground[c])), round(100 * float(share[c])), round(float(earth.mean[c]))) for c in closing])
much = land & (share >= 0.1)
P("land cells a tenth or more ocean in the data: %d; above 10 m: %d; above 100 m: %d" % (much.sum(), (much & (earth.ground > 10.0)).sum(), (much & (earth.ground > 100.0)).sum()))
other = earth.with_ground(held["every_point"])
place, mouth = ref.GREAT_RIVERS["St Lawrence"]
leaves = lambda e: e.km(int(e.drainage.fields["basin_id"][e.cell(*place)]), *mouth)
P("St Lawrence: as built %.0f km; every point %.0f km; closing cells then at %s; narrows then %s" % (leaves(earth), leaves(other), [round(float(other.ground[c])) for c in closing], ref.narrows(other)["St Lawrence"]))
P("land at or below the sea's level: as built %d; every point %d; lakes share as built %.4f, every point %.4f" % ((land & (earth.ground <= earth.sea_level)).sum(), (land & (other.ground <= earth.sea_level)).sum(),
  ref.land_water(earth)["lakes_share"], ref.land_water(other)["lakes_share"]))
os_ = ref.summary(other)
P("every point: mouths within 300 km %d" % sum(os_["mouth_km"][r] < 300 for r in ref.GREAT_RIVERS))
s = ref.relief_steps(earth)
P("relief_steps:", {k: v for k, v in s.items()})
P("tie_counts:", ref.tie_counts(earth))
r = ref.raw_hollows(flood)
P("raw_hollows:", r)
h = ref.mesh_hollows(earth)
P("mesh_hollows:", {k: (v if not hasattr(v, "sum") else int(v.sum())) for k, v in h.items()})
label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
full = table["spill_m"][dr.top_hollows(table)[label]]
level_with = earth.land & (label > 0) & (earth.ground == np.where(np.isnan(full), np.inf, full))
P("LEVEL_WITH_THE_WATER = %d" % level_with.sum())
lakes = earth.hydrology().tables["lakes"]
big = np.flatnonzero(lakes["area_m2"] > 1.0e11)
heldl = []
for i in big:
    c = int(lakes["bottom_cell"][i])
    x = ref.raw_at(flood, float(earth.mesh.lat[c]), float(earth.mesh.lon[c]))
    heldl.append((round(float(lakes["area_m2"][i]) / 1e6), round(float(earth.mesh.lat[c]), 1), round(float(earth.mesh.lon[c]), 1), (not x["ocean"]) and x["level"] > x["height"]))
P("big lakes:", heldl)
for place_, in (((-3.0, 16.5),), ((0.0, -63.0),), ((58.2, 68.4),)):
    P("   data at", place_, ref.raw_at(flood, *place_))
w = ref.land_water(earth)
P("WATER_OF_THE_LAND =", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in w.items()})
P("spread over settlements: back_to_air %.4f to %.4f; to_sea %.2f to %.2f; lakes_share %.4f to %.4f" % (
  min(r["back_to_air"] for r in out.values()), max(r["back_to_air"] for r in out.values()), min(r["to_sea"] for r in out.values()), max(r["to_sea"] for r in out.values()),
  min(r["lakes_share"] for r in out.values()), max(r["lakes_share"] for r in out.values())))
river = earth.hydrology().fields["river_discharge"].astype(np.float64).mean(axis=0)
into_sea = int(np.argmax(np.where(earth.wet, river, -1.0)))
on_land = int(np.argmax(np.where(earth.land, river, -1.0)))
P("largest flow into the sea: %.0f m3/s, %.0f km from the Amazon's mouth; largest on land %.0f m3/s, %.0f km; its receiver is sea: %s" % (
  river[into_sea], earth.km(into_sea, -0.5, -50.0), river[on_land], earth.km(on_land, -0.5, -50.0), bool(earth.wet[earth.drainage.fields["flow_receiver"][on_land]])))
gauges = ref.rivers_at_gauges(earth)
ok = lambda r, river_: ref.within_a_factor_of_two(ref.GAUGES[river_][2], r["flow"][river_])
P("AT_GAUGE =", {river_: (round(g["flow"]), round(g["reaches"]), sum(ok(x, river_) for x in drawn)) for river_, g in gauges.items()})
P("gauges detail:", json.dumps({k: {a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()} for k, v in gauges.items()}))
counts = [sum(ok(r, river_) for river_ in ref.GAUGES) for r in drawn]
P("gauges passing: engine %d; random %d to %d" % (sum(ok(out["engine"], r) for r in ref.GAUGES), min(counts), max(counts)))
P("spread of flows:", {river_: (round(min(r["flow"][river_] for r in drawn)), round(max(r["flow"][river_] for r in drawn))) for river_ in ref.GAUGES})
ganges, brahmaputra = ref.GAUGES["Ganges"][:2], ref.GAUGES["Brahmaputra"][:2]
P("Ganges cell %d, Brahmaputra cell %d; Ganges cell %.0f km from its station; Brahmaputra's cell %.0f km from the Ganges's station" % (
  gauges["Ganges"]["cell"], gauges["Brahmaputra"]["cell"], earth.km(gauges["Ganges"]["cell"], *ganges), earth.km(earth.cell(*brahmaputra), *ganges)))
P("no_river:", [n for n, g in gauges.items() if g["no_river"]])
like = ref.like_for_like(earth)
P("ALIKE =", {name: (round(r["ratio"], 2), sum(x["like"][name][0] for x in drawn)) for name, r in like.items() if r["like"]})
P("alike in 20, for those not alike as built:", {name: sum(x["like"][name][0] for x in drawn) for name, r in like.items() if not r["like"]})
P("like detail:", json.dumps({k: {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()} for k, v in like.items()}))
t_ = ref.like_together(like)
P("like_together:", {k: (v if not isinstance(v, float) else round(v, 4)) for k, v in t_.items() if k != "weights"}, "Amazon weight %.4f" % t_["weights"]["Amazon"])
P("without the Amazon %.4f; without Brahmaputra and Columbia %.4f" % (ref.like_together(like, ("Amazon",))["ratio"], ref.like_together(like, ("Brahmaputra", "Columbia"))["ratio"]))
asked = sorted(((like[name]["measured_depth"] / like[name]["rain"], name) for name in t_["basins"]), reverse=True)
P("measured runoff over rain, highest:", [(round(a, 3), n) for a, n in asked[:4]])
P("like_all over settlements: %.3f to %.3f" % (min(r["like_all"] for r in drawn), max(r["like_all"] for r in drawn)))
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("earth_rivers", pathlib.Path(ref.ROOT) / "tools" / "earth_rivers.py")
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
rows = tool.what_a_smaller_demand_would_do(earth, say=lambda line: None)
P("UNDER_DEMAND =", {factor: (round(r["like_all"], 3), round(r["like_median"], 3), round(r["like_without_amazon"], 3), round(r["back_to_air"], 4), round(r["to_sea"], 2), round(r["to_air_mm"], 1), r["gauges_within"]) for factor, r in rows.items()})
P("spread under demand:", {factor: (round(r["like_lowest"], 2), round(r["like_highest"], 2), r["like_within_15"]) for factor, r in rows.items()})
v = ref.volga(earth)
P("volga:", json.dumps({k: {a: (round(b, 2) if isinstance(b, float) else b) for a, b in x.items()} for k, x in v.items() if k != "land"}), "land km2 %.0f" % (earth.area[v["land"]].sum() / 1e6))
c = ref.lake_books(earth)
P("lake_books:", json.dumps({k: (round(x, 3) if isinstance(x, float) else x) for k, x in c.items()}))
P("caspian over settlements:", [(r["caspian"]["overflows"], round(r["caspian"]["outflow_km3"], 2), r["caspian"]["overflow_ends"], round(r["caspian"]["area_km2"]), r["caspian"]["level_m"]) for r in drawn])
P("lakes: at the Black Sea, the Baltic, the Great Lakes, the Congo:", [None if (x := earth.lake_at(*p)) is None else (round(float(x["area_m2"]) / 1e6), float(x["level_m"]), bool(x["overflows"])) for p in ((43.0, 34.0), (58.0, 20.0), (47.5, -87.0), (-3.0, 16.5))])
