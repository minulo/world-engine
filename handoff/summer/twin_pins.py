"""Every number that the twin's tests and the reasons of its expected failures quote, measured on the twin as the
engine now stands (tests/test_earth.py builds the same twin). Used to set those numbers again after the northern-summer
work of 2026-10-24 and 25.

    PYTHONPATH=src:tests python handoff/summer/twin_pins.py
"""
import numpy as np

import earth_reference as ref
import test_earth as te
from worldengine.library import operators as op

twin = te.twin.__wrapped__() if hasattr(te.twin, "__wrapped__") else te.twin()
e, w = twin
m, f, area, wet, land, celsius, earth_celsius = te._twin_numbers(twin)
mean = lambda x, mask: float((x * area)[mask].sum() / area[mask].sum())
north = land & (m.lat > 40) & (m.lat < 60)
mine = np.array([mean(celsius[k], north) for k in range(12)])
earths = np.array([mean(earth_celsius[k], north) for k in range(12)])
print(f"40-60 N land: swing {mean(celsius[6] - celsius[0], north):.1f} K (Earth {mean(earth_celsius[6] - earth_celsius[0], north):.1f}); "
      f"year {mine.mean():.1f} ({earths.mean():.1f}); coldest {mine.min():.1f} ({earths.min():.1f}); warmest {mine.max():.1f} ({earths.max():.1f})")
snow = f["snow_cover"].astype(np.float64)
print(f"snow in every month: {100 * area[north & (snow.min(0) > 0.5)].sum() / area[north].sum():.1f} % of 40-60 N land, "
      f"{100 * area[land & (snow.min(0) > 0.5)].sum() / area[land].sum():.1f} % of all land")
names = e.registry.fields["climate_class"].categories
group = np.array([n[0] for n in names])[f["climate_class"]]
for g in "ABCDE":
    print(f"group {g}: {100 * area[land & (group == g)].sum() / area[land].sum():.1f} % of the land")
everywhere = np.ones(m.n, dtype=bool)
gap = mean(celsius.mean(0), everywhere) - mean(earth_celsius.mean(0), everywhere)
recv = f["flow_receiver"]
coast = np.flatnonzero(land & (recv >= 0) & wet[np.maximum(recv, 0)])
print(f"the year: {mean(celsius.mean(0), everywhere):.1f} C against {mean(earth_celsius.mean(0), everywhere):.1f} ({gap:+.1f} K); "
      f"largest river at a coast {f['river_discharge'].astype(np.float64).mean(0)[coast].max():,.0f} m3/s")
print(f"western Europe permafrost {f['permafrost'][land & te._box(m, 45, 55, 0, 15)].mean():.2f}")
biomes = e.registry.fields["biome"].categories
boreal = ["taiga", "cold_mixed_forest", "cold_deciduous_forest", "cool_conifer_forest", "cool_mixed_forest"]
for name, box in (("Siberia 55-65 N", (55, 65, 90, 130)), ("Canada 50-60 N", (50, 60, -110, -80))):
    cells = land & te._box(m, *box)
    kinds, counts = np.unique(np.asarray(biomes)[f["biome"][cells]], return_counts=True)
    print(f"{name}: boreal {te._share(f['biome'], biomes, cells, boreal):.2f};", dict(zip(kinds.tolist(), counts.tolist())))
g = (f["tc_genesis_potential"].astype(np.float64) * area)
quiet = (m.lat < 0) & (m.lon > -140) & (m.lon <= 20)
print(f"genesis potential in the SE Pacific and S Atlantic {g.sum(0)[quiet].sum() / g.sum():.3f}; south of the equator {g.sum(0)[m.lat < 0].sum() / g.sum():.3f}; "
      f"peak months north {int(np.argmax(g[:, m.lat > 0].sum(1))) + 1}, south {int(np.argmax(g[:, m.lat < 0].sum(1))) + 1}")
p = te._patterns()
for name in ("Peru", "south-west Africa", "north-west Africa", "California"):
    b = p.WEST_COASTS[name]
    up = f["upwelling"].astype(np.float64).mean(0)[wet & p.box(m, b)].mean() * 86400.0
    print(f"west coast {name}: {te._west_coast_anomaly(twin, name):+.1f} K against its band; upwelling {up:+.2f} m a day")
jan = {k: np.average(celsius[0][land & p.box(m, b)], weights=area[land & p.box(m, b)]) for k, b in p.COASTS.items()}
print("January coasts:", {k: round(float(v), 1) for k, v in jan.items()})
for name in ("Sahara", "Arabia"):
    print(f"{name} June to August rain {te._summer_rain(twin, name):.1f} mm a month")
here = land & p.box(m, p.INDIA)
for month in (0, 6):
    print(f"India month {month + 1}: east {float(np.einsum('ij,ij->i', f['wind'][month], m.east)[here].mean()):+.2f} m/s, "
          f"north {float(np.einsum('ij,ij->i', f['wind'][month], m.north)[here].mean()):+.2f} m/s")
d = f["storm_track_density"]
bands = np.arange(-87.5, 90.0, 5.0)
for months, hemisphere in (([0, 1, 11], 1), ([0, 1, 11], -1), ([5, 6, 7], -1)):
    zonal = np.array([d[months].mean(axis=0)[np.abs(m.lat - b) <= 2.5].mean() for b in bands])
    side = hemisphere * bands > 0
    print(f"storm tracks months {months} hemisphere {hemisphere}: peak at {bands[side][int(np.argmax(zonal[side]))]:+.1f}")
ice = f["snow_ice_cover"]
print(f"sea ice: Arctic (north of 70) March {ice[2][wet & (m.lat > 70)].mean():.2f}, September {ice[8][wet & (m.lat > 70)].mean():.2f}; "
      f"south of 60 S September {ice[8][wet & (m.lat < -60)].mean():.2f}, March {ice[2][wet & (m.lat < -60)].mean():.2f}")
for box in ((60, 70, 90, 130), (60, 70, -100, -80)):
    print(f"permafrost {box}: {f['permafrost'][land & te._box(m, *box)].mean():.2f}")
m_, land_, yearly, lat, land_rain = te._twin_land_rain(twin)
for sign in (1, -1):
    side = (sign * lat > 0) & (sign * lat < 60) & ~np.isnan(land_rain)
    k = int(np.flatnonzero(side)[np.argmin(land_rain[side])])
    print(f"driest land band {'north' if sign > 0 else 'south'}: {lat[k]:+.1f} with {land_rain[k]:.0f} mm")
print(f"40-60 N land rain {mean(yearly, north):.0f} mm; far north (>60) {mean(yearly, land & (m.lat > 60)):.1f} mm")
sahara, amazon, congo = land & te._box(m, 18, 28, -10, 25), land & te._box(m, -10, 2, -70, -50), land & te._box(m, -5, 3, 15, 28)
soils = e.registry.fields["soil_order"].categories
tropical = ["tropical_rain_forest", "tropical_seasonal_forest"]
temperate = ["temperate_deciduous_forest", "warm_mixed_forest", "cool_mixed_forest", "cool_conifer_forest"]
print(f"biomes: Sahara desert {te._share(f['biome'], biomes, sahara, ['hot_desert', 'semi_desert']):.2f}, aridisols "
      f"{te._share(f['soil_order'], soils, sahara, ['aridisols', 'shifting_sand']):.2f}; Amazon tropical {te._share(f['biome'], biomes, amazon, tropical):.2f}, "
      f"Congo {te._share(f['biome'], biomes, congo, tropical):.2f}; Amazon oxisols+ultisols {te._share(f['soil_order'], soils, amazon, ['oxisols', 'ultisols']):.2f}; "
      f"eastern US temperate {te._share(f['biome'], biomes, land & te._box(m, 33, 42, -90, -75), temperate):.2f}; Greenland ice "
      f"{te._share(f['biome'], biomes, land & te._box(m, 70, 80, -50, -30), ['ice']):.2f}")
print(f"climate rounds {w.rounds_used['climate']}, settled {w.settled['climate']}")
