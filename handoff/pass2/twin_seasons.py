"""The twin's seasons over northern land, beside Earth's (preview mesh): what the twin's expected failures state."""
import numpy as np, yaml
from pathlib import Path
import earth_reference as ref
from worldengine.engine import Engine
from worldengine.mesh import get_mesh
DATA = Path("data")
models = ref.earth_twin_models(yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8")), get_mesh(5))
e = Engine(DATA, profile="preview", overrides={"models": models, "explanations": ref.earth_twin_explanations(yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8")))})
w = e.build()
m, f = w.mesh, w.fields
area = f["cell_area"].astype(np.float64); wet = f["ocean_mask"]; land = ~wet
t = f["surface_temperature"].astype(np.float64) - 273.15
te = ref.at_cell_centres(m, *ref.temperature_monthly())
mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
P = print
P("sea level %.2f m; sea share %.4f; planet volume poured %.6e; rounds %s settled %s" % (w.tables["seas"]["surface_m"][0], area[wet].sum() / area.sum(), e.params["planet"]["surface_water_volume_m3"] if hasattr(e, "params") else float("nan"), w.rounds_used["climate"], w.settled["climate"]))
for lo, hi in ((40, 60), (30, 60), (60, 90)):
    north = land & (m.lat > lo) & (m.lat < hi)
    series = np.array([mean(t[k], north) for k in range(12)]); earths = np.array([mean(te[k], north) for k in range(12)])
    P("land %d to %d N: year %.1f vs %.1f; coldest month %.1f (month %d) vs %.1f (month %d); warmest %.1f (month %d) vs %.1f (month %d); July less January %.1f vs %.1f" % (
      lo, hi, series.mean(), earths.mean(), series.min(), series.argmin() + 1, earths.min(), earths.argmin() + 1, series.max(), series.argmax() + 1, earths.max(), earths.argmax() + 1,
      mean(t[6] - t[0], north), mean(te[6] - te[0], north)))
    P("   by month, twin:", np.round(series, 1).tolist()); P("   by month, Earth:", np.round(earths, 1).tolist())
    snow = f["snow_cover"].astype(np.float64)
    P("   under snow in every month (cover > 0.5): %.1f %% of that land; mean snow cover in July %.2f, in January %.2f" % (100 * area[north & (snow.min(axis=0) > 0.5)].sum() / area[north].sum(), mean(snow[6], north), mean(snow[0], north)))
allc = (m.lat > 30) & (m.lat < 60)
P("all cells 30 to 60 N: year %.1f vs %.1f" % (mean(t.mean(axis=0), allc), mean(te.mean(axis=0), allc)))
names = e.registry.fields["climate_class"].categories
group = np.array([n[0] for n in names])[f["climate_class"]]
for letter in "ABCDE":
    P("group %s: %.1f %%" % (letter, 100 * area[land & (group == letter)].sum() / area[land].sum()))
snow = f["snow_cover"].astype(np.float64)
P("land under snow in every month: %.1f %%" % (100 * area[land & (snow.min(axis=0) > 0.5)].sum() / area[land].sum()))
p = f["precipitation"].astype(np.float64).sum(axis=0); pe = ref.at_cell_centres(m, *ref.rain_monthly()).sum(axis=0)
for lo, hi in ((40, 60), (60, 90)):
    north = land & (m.lat > lo) & (m.lat < hi)
    P("rain on land %d to %d N: %.0f vs %.0f mm" % (lo, hi, mean(p, north), mean(pe, north)))
from worldengine.library import operators as op
lat, land_rain = op.zonal_mean(m, p, 5.0, mask=land.astype(np.float64))
_, earth_rain = op.zonal_mean(m, pe, 5.0, mask=land.astype(np.float64))
side = (lat > 0) & (lat < 60) & ~np.isnan(land_rain)
P("driest northern band: twin at %.1f with %.0f mm; Earth's rain at the same cells driest at %.1f" % (lat[side][np.argmin(land_rain[side])], land_rain[side].min(), lat[side][np.nanargmin(earth_rain[side])]))
P("lakes share of land %.2f %%" % (100 * (f["lake_fraction"].astype(np.float64) * area).sum() / area[land].sum()))
