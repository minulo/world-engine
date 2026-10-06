import json
import numpy as np
import earth_reference as ref
P = print
earth = ref.Earth(7); flood = ref.raw_flood()
held = ref.data_points_of_cells(earth, flood)
o = ref.other_valley_reading(earth, flood)
other = o["earth"]
P("changed %d at_sea %d" % (o["changed"], o["at_sea"]))
P("built:", {k: v for k, v in o["built"].items() if k not in ("mouth_km", "flow")}); P("other:", {k: v for k, v in o["other"].items() if k not in ("mouth_km", "flow")})
P("moved:", {r: (round(a), round(b)) for r, (a, b) in o["moved"].items()})
P("flows moved:", {r: (round(o["built"]["flow"][r]), round(o["other"]["flow"][r])) for r in ref.GAUGES if abs(o["built"]["flow"][r] - o["other"]["flow"][r]) > max(2.0, 0.02 * o["built"]["flow"][r])})
closing = [earth.cell(47.3, -70.6), earth.cell(47.4, -69.9)]
P("closing cells: built", [float(earth.ground[c]) for c in closing], "other", [float(other.ground[c]) for c in closing], "share", [round(float(held["ocean_share"][c]), 2) for c in closing], "sea level f32", float(np.float32(earth.sea_level)))
n = ref.narrows(other)
P("narrows other:", json.dumps({k: {a: (b if not isinstance(b, tuple) else [round(x, 1) for x in b]) for a, b in v.items()} for k, v in n.items() if k in ("Danube", "St Lawrence")}))
for nm, place in (("Black Sea", (43.0, 34.0)), ("Baltic", (58.0, 20.0))):
    L = ref.lake_books(other, place)
    P(nm, None if L is None else {k: (round(v, 1) if isinstance(v, float) else v) for k, v in L.items() if k != "overflow"})
P("Baltic cell: wet %s ground built %.2f other %.3f" % (earth.wet[earth.cell(58.0, 20.0)], earth.ground[earth.cell(58.0, 20.0)], other.ground[earth.cell(58.0, 20.0)]))
w = ref.land_water(other)
P("other land water: lakes_share %.4f back %.4f to_sea %.2f" % (w["lakes_share"], w["back_to_air"], w["to_sea"]))
P("land at or below the sea's level: built %d other %d" % ((earth.land & (earth.ground <= earth.sea_level)).sum(), (earth.land & (other.ground <= earth.sea_level)).sum()))
much = earth.land & (held["ocean_share"] >= 0.1)
P("much:", int(much.sum()), int((much & (earth.ground > earth.sea_level + 10.0)).sum()), int((much & (earth.ground > earth.sea_level + 100.0)).sum()), "| above 10 m / 100 m absolute:", int((much & (earth.ground > 10.0)).sum()), int((much & (earth.ground > 100.0)).sum()))
P("of the changed cells: with ocean share >= 0.1: %d; other.ground == sea: %d" % (int(((other.ground != earth.ground) & much).sum()), o["at_sea"]))
ya = [c for c in ref.way_of(other, "Danube") if c["step"] != "sea"]
P("Danube under the other reading: last land cell %.1f, %.1f; km %.0f; cells %d" % (ya[-1]["lat"], ya[-1]["lon"], ya[-1]["km_to_mouth"], len(ya)))
