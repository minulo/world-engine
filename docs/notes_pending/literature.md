## The recalled constants, looked up (2026-11-09)

### What was done

The constants of `data/models.yaml` that carried [UNVERIFIED], and the docstrings in `src/` that carried the same
label for those constants, were searched for in the literature. Where a source I read confirms a value, its label now
says [DOCUMENTED] with the source and what was read. Where a source gives another value, the number was left as it is
and the other value is recorded below as a proposal. Where nothing was found, the label stays and the search is
recorded. No number and no line of logic changed: the parsed contents of `data/models.yaml` are identical to those of
the base commit [MEASURED: `yaml.safe_load` of both files compared equal], and only comments and docstrings were edited.

The design also asks for one more search for a published model before a rule table is built, for the Cryosphere and
for the soil classes (section 16.1: "No record of such a search was kept"). That search is recorded in the last two
parts below.

How the sources were reached. Journals' pages and arXiv are blocked from this machine, and so were the two other hosts
tried with a page reader (`www.ldeo.columbia.edu`, for an author's copy of Camargo et al. 2007, and `en.wikipedia.org`):
neither resolved [MEASURED]. What was read is therefore of three kinds:

- **Abstracts**, through the Consensus search tool. An abstract counts only for what it says; where a paper's table or
  equation holds the number, the abstract does not confirm it. Some records carry a chapter's or paper's opening in
  place of an abstract, and the table says so where that was used. The tool's free allowance for the month ran out
  after 30 searches that returned results [MEASURED: its message, "You've used 100% of your free Consensus usage this
  month"], before the stream power exponent, the vapour's scale height and some ocean numbers were searched.
- **Code that carries a published formula**, through GitHub's code search, which returns the matching lines. This is
  [DOCUMENTED at second hand], as the build already did for the SPLASH code (section 10): the code's author read the
  paper, I read the code.
- **Computation with a standard's own code**: the TEOS-10 package `gsw` 3.6.23, installed from the Python package index
  into a scratch folder, for the density and heat capacity of sea water [MEASURED].

A web search tool was tried twice, for the genesis index and for the stream power exponent. It returns a summary
written by the tool, not the page, so nothing it said is used as a source; its leads are listed under "Not done".

### The constants

Labels before and after: 56 lines of `data/models.yaml` carried [UNVERIFIED] and 34 [DOCUMENTED]; now 31 and 61
[MEASURED: `grep -c`]. Some of the 31 are new mentions that name what is still not looked up inside a now documented
comment (the vapour's gas constant in Bolton's formula). The 66 lines labelled [PROVISIONAL] were not searched: they
are first values that an Earth test must tune, and no source can confirm a tuned number. Two whose labels carried a
recalled fact were searched (the cap on cyclone winds; the look-back window).

| Constant | Value | Old label | New label, or proposal | Source |
|---|---|---|---|---|
| `shared.lapse_rate_k_per_km` | 6.5 | UNVERIFIED | DOCUMENTED at second hand | Code carrying the U.S. Standard Atmosphere 1976 (-0.0065 K/m to 11,000 m); Hydrology's own 0.0065 K/m from Davis et al. 2017, eq. 20; Konashenok 2012 (a teaching text, as Consensus gives it): "Average lapse rate is 6.5°/km". The standard's record has no numbers |
| `shared.weather_look_back_days` | 8 | PROVISIONAL, with "storms live a few days to a week, UNVERIFIED" | Kept | Searched (lifetimes of extratropical cyclones): the abstracts give trends in lifespan, not a mean |
| `Tectonics.plate_speed_cm_per_year` | [1, 9] | UNVERIFIED | Kept | DeMets et al. 2010 (MORVEL): no speeds in the abstract. Zheng et al. 2014, abstract: Antarctica and Eurasia move 4 and 3 mm a year (root mean square, in their frame of seismic anisotropy), below the range's lower end |
| `continents.fraction` | 0.40 | UNVERIFIED | DOCUMENTED | Cogley 1984, abstract: 210.4 million km², "41% of the earth's surface", submerged margins included; Cawood et al. 2019, abstract: "around 40%" |
| `thickness.continental_normal_m` | 35000 | UNVERIFIED | Kept; **proposal 36 km** | Cogley 1984, abstract: a mean of 36 km for continents whose mean height is about 120 m. Also found: 41.1 km mean (Christensen and Mooney 1995, at second hand in Yanagi 2011); 30 km at sea level in South America (Chapin 1996, abstract) |
| `thickness.oceanic_m` | 7000 | UNVERIFIED | DOCUMENTED | White et al. 1992, abstract: "averages 7.1±0.8 km thick away from anomalous regions" |
| `ocean_age.maximum_my` | 180 | UNVERIFIED | DOCUMENTED | Kawano et al. 2023, abstract: "the oldest (170–180 Ma) Pacific seafloor"; Cogné et al. 2004, abstract: area per unit age falls to zero at 180.2 ± 9.7 Ma |
| `history.maximum_thickness_m` | 70000 | UNVERIFIED | DOCUMENTED | Zhu et al. 2023, abstract: southern Tibet, "the world's thickest crust", "greater than 70 km after 32 Ma". At second hand (Yanagi 2011): Christensen and Mooney give 14 to 80 km |
| `slab_pull.fastest_cm_per_year` | 10 | UNVERIFIED | Kept | Searched with the plate speeds; nothing |
| `Isostasy.crust_density_kg_m3` | 2800 | UNVERIFIED | Kept | Searched; no abstract states it. Nearest: a crust-mantle contrast of 0.45 g/cm³ for South America (Chapin 1996), 0.315 for Anatolia, "low compared to the global average" (Karabulut et al. 2019); upper crust 2.77 and lower 2.9 g/cm³ in the Levant (Segev et al. 2006) |
| `Isostasy.mantle_density_kg_m3` | 3300 | UNVERIFIED | Kept | Same search. Mantle under continents 2770 to 3649 kg/m³ from gravity (Tenzer et al. 2012); "density values for the crust and mantle, commonly used for isostatic modeling result in highly inaccurate prediction of topography" (Theunissen et al. 2022) |
| `FluvialErosion.area_exponent_m` | 0.5 | UNVERIFIED | Kept | Not searched in Consensus (allowance spent). Web search leads only, not read |
| `FluvialErosion.reference_runoff_mm_per_year` | 300 | UNVERIFIED | Kept | Not searched |
| `FluvialErosion.creep_m2_per_year` | 0.01 | UNVERIFIED | DOCUMENTED that it lies within published values | Abstracts: about 50 cm²/yr, 0.005 m² (Dietrich et al. 1995, northern California); 360 cm²/yr, 0.036 m² (McKean et al. 1993); 1 to 6 m² per thousand years (Ben-Asher et al. 2017, Golan cinder cones) |
| `Albedo.surface.sea` | 0.07 | UNVERIFIED | Kept | Payne 1972, abstract: 0.061 under heavy overcast, 0.03 for a high sun under clear sky, more at low sun; no mean over the day |
| `Albedo.surface.bare_ground` | 0.25 | UNVERIFIED | Kept | Searched (MODIS albedo by land cover): no value per class in the abstracts. Earth's mean land albedo is 0.24, snow included (Zhang et al. 2010); deserts vary by a factor of 2.5 (Tsvetsinskaya et al. 2002) |
| `Albedo.surface.under_plants` | 0.15 | UNVERIFIED | Kept | Same search; nothing |
| `Cryosphere.permafrost_full_below_k` | 265.15 (-8 °C) | UNVERIFIED | DOCUMENTED | Smith and Riseborough 2002, abstract: "The transition from discontinuous to continuous permafrost occurs between a MAAT of −6° to −8°C"; -8 is the cold end |
| `Cryosphere.permafrost_none_above_k` | 272.15 (-1 °C) | UNVERIFIED | DOCUMENTED for one region | Jin et al. 2007, abstract: the southern limit in northeastern China on the -1 to 0 °C isotherms in the western Da Xing'anling, about 0 °C on the Songnen Plain, 0 to +1 °C in the Xiao Xing'anling; -1 is the cold end. No global value found |
| `EnergyBalance.air_heat_capacity_j_kg_k` | 1004.0 | UNVERIFIED | DOCUMENTED at second hand | MetPy's constants: 3.5 times the gas constant of dry air, 1004.67 J/kg/K; Baumgartner et al. 2020, abstract: the literature gives different values |
| `Circulation.stability_per_s` | 0.012 | UNVERIFIED | Kept | Searched; no value found. INFERRED check from the standard atmosphere's lapse rate: 0.0106 at 288 K, 0.0113 at 250 K, 0.0122 at 217 K; 0.012 is the value near the top of the weather layer |
| `Circulation.weather_layer_depth_m` | 11000 | UNVERIFIED | DOCUMENTED at second hand | The tropopause of the U.S. Standard Atmosphere 1976 at 11 km, as code carries it; Konashenok 2012: "Average height is 10-11 km", 15 to 16 km at the equator |
| `OceanCurrents.air_density_kg_m3` | 1.2 | UNVERIFIED | Kept | Not searched. INFERRED check: dry air at 101,325 Pa and 288.15 K, with MetPy's gas constant, is 1.225 kg/m³ |
| `OceanCurrents.drag_coefficient` | 1.3e-3 | UNVERIFIED | DOCUMENTED that it lies within a published range; **proposal 1.2e-3** | Kondo 1975, abstract: 10³ CD = 1.11 to 1.70 for 4 to 20 m/s. Large and Pond 1981 as two ocean codes carry it, naming them (umwm; NPIOcean/kval), FVCOM with the same formula: 1.2e-3 from 4 to 11 m/s, and (0.49 + 0.065 U) e-3 above; 1.3e-3 is theirs at 12.5 m/s. Their abstract: the coefficient "increases with wind speed above 10 m s−1", no number |
| `OceanCurrents.sea_water_density_kg_m3` | 1025 | UNVERIFIED | MEASURED with TEOS-10's code | gsw 3.6.23, practical salinity 35, surface: 1026.0 kg/m³ at 15 °C, 1025.3 at 18 °C, 1024.8 at 20 °C |
| `OceanCurrents.sea_water_heat_capacity_j_kg_k` | 3990 | UNVERIFIED | DOCUMENTED, and MEASURED | TEOS-10's cp0 = 3991.86795711963 J/kg/K, "The 'specific heat' for use with Conservative Temperature" (GSW-C and GSW-Python); gsw 3.6.23: 3986.4 at 0 °C, 3990.1 at 10 °C, 4000.5 at 28 °C |
| `OceanCurrents.drift_depth_m` | 50 | UNVERIFIED | Kept | Searched with the Ekman scale; nothing for the depth |
| `OceanCurrents.mixing_coefficient` (the form of the scale) | 0.6 u*/abs(f) | "the form of the scale is recalled: UNVERIFIED" | Form DOCUMENTED; the coefficient stays CALIBRATED | Lozovatsky et al. 2005, abstract: "hD ≈ 0.44Lf, where Lf = u*/f is the Ekman scale", on a section at 53° N |
| `OceanCurrents.upwelling_cooling_limit_w_m2`, `carried_heat_limit_w_m2` | 100, 250 | PROVISIONAL, with recalled facts | Kept | Not searched |
| `Moisture.exchange_coefficient` (the comment's "measured values are 1.1 to 1.5 thousandths") | 0.95e-3 | UNVERIFIED for the measured range | DOCUMENTED | Kondo 1975, abstract: 10³ CE = 1.18 to 1.30 for 4 to 20 m/s; Hicks 1972, abstract: "about 1.4 × 10−3" for heat and water vapour over water bodies of several sizes |
| `Moisture.saturation` (Bolton 1980) | 611.2, 17.67, 29.65, 461.5 | UNVERIFIED | DOCUMENTED for the form; numbers at second hand; the gas constant UNVERIFIED | Bolton 1980, abstract: "new empirical formulas ... for the saturated vapor pressure of water". Code of a hydrology textbook's figures (jpgannon/IntroHydro_Figures): "6.112 * np.exp(17.67 * T / (T + 243.5))", "Bolton (1980)"; 273.15 - 243.5 = 29.65 |
| `Moisture.vapour_scale_height_m` | 2500 | UNVERIFIED | Kept | Not searched |
| Moisture's recalled water budget, trade-wind depth, wet coasts | — | UNVERIFIED | Kept | Not searched |
| `Hydrology.snow.daily_spread_k` | 5.0 | UNVERIFIED | DOCUMENTED; a caveat | Fausto et al. 2011 (the opening Consensus gives): Greenland models give the degree-day method's standard deviation, after Braithwaite 1984 and Reeh 1991, "a single value which typically spans the interval 4.5–5.5°C" (the record's text renders the degree sign as "8", "4.5–5.58C"). Rogozhina et al. 2014, abstract: "Neither the climate data set analyzed nor in situ measurements taken in Greenland support ... uniform SD values (~ 5 °C)"; in summer where melting occurs they are "~ 1 to 2.5 °C". Wake et al. 2015: a fixed value "does not hold". Reeh 1991 itself was not read |
| `Hydrology.demand.sunlight.water_reflects` | 0.07 | UNVERIFIED, "the usual value for water under a high sun" | Kept; **the reason does not hold** | Payne 1972, abstract: 0.03 for a high sun under clear sky; 0.061 under heavy overcast. The number is near the overcast value |
| `Hydrology.demand.air.specific_heat_air_j_kg_k` | 1004.6 | UNVERIFIED | DOCUMENTED at second hand | MetPy, 1004.67 J/kg/K, as above |
| `Soils.depth.fastest_production_m_per_year` | 7.7e-5 | UNVERIFIED | DOCUMENTED | Heimsath et al. 1999, abstract, in northern California as the 1997 paper [INFERRED: the same site; both abstracts describe the same two methods]: "from 0.077 mm/year with no soil mantle to 0.0077 mm/year under 1 m of soil". Elsewhere 53 m/My (southeastern Australia, Heimsath et al. 2000) and 268 m/My (Oregon, Heimsath et al. 2001) |
| `Soils.depth.decline_depth_m` | 0.5 | UNVERIFIED | Kept; **proposal 0.43 m** | The same abstract: a tenfold fall over 1 m is h0 = 1 m / ln 10 = 0.434 m; with 0.5 m, 1 m of soil keeps 0.135 of P0. The Australian site's 53 and 7 m/My over 1 m give 0.49 m |
| `Soils.root_depth_m` | 1.5 | UNVERIFIED | DOCUMENTED as typical | Jackson et al. 1996, abstract: the global profile 1 - β^d, d in cm, β = 0.966, which puts 99.4 % of roots above 1.5 m [INFERRED from it]; Schenk and Jackson 2002, abstract: in over 90 % of profiles 95 % of roots lie in the upper 2 m; Canadell et al. 1996: the deepest roots reach 4.6 m on the global mean |
| `Biomes.supply_mm_per_day` | 5.0 | UNVERIFIED | Kept | Searched in code: SPLASH, which Hydrology follows, has a supply constant of 1.05 mm an hour after Federer 1982 (rsofun, cran/splash, safricaro), an hourly rate in a scheme that integrates over the day: not the same quantity. Nothing for BIOME1's own rate |
| `StormClimatology.storm_life_days` | 4 | UNVERIFIED | Kept | Searched; nothing |
| `StormClimatology.intensity_a/b/c/t0` | 28.2, 55.8, 0.1813, 30 | UNVERIFIED | DOCUMENTED for the form and the basin; the numbers at second hand | DeMaria and Kaplan 1994, abstract: "An empirical relationship between climatological sea surface temperature (SST) and the maximum intensity of tropical cyclones in the North Atlantic basin ... from a 31-year sample (1962–1992)". The numbers: MichaelFischerWx/TC-ATLAS (`favorability.py`), guillem/how-things-work, and a saved copy of Wikipedia's "Tropical cyclone forecasting" (A = 28.2, C = 0.1813, "the 99th percentile of empirical tropical cyclone intensity data") |
| `StormClimatology.intensity_cap_m_s` | 90 | PROVISIONAL, "about the strongest winds measured, UNVERIFIED" | Kept; **proposal 95 m/s if the cap is the record** | Rogers et al. 2017 (the chapter text Consensus gives): Patricia's 185 kt, about 95 m/s, "ties the record for the globe with Typhoon Nancy's (1961)"; Foltz et al. 2016, abstract: "a peak intensity of 95 m s−1" |
| `StormClimatology.gpi` | 1e5, 1.5, 50, 3, 70, 3, 0.1, -2 | UNVERIFIED | DOCUMENTED at second hand | The xtci package (wy2136/xtci, `xtci/ERA5.py`, `AMx.py`, `MERRA2.py`): "GPI (Emanuel and Nolan 2004): \|10\*\*5\\eta\|\*\*(3/2) \* (H/50)\*\*3 \* (Vpot/70)\*\*3 \* (1+0.1\*Vshear)\*\*(-2)". Camargo, Emanuel and Sobel 2007, abstract: the four terms, vorticity at 850 hPa, humidity at 600 hPa, shear from 850 to 200 hPa, potential intensity |
| `SynopticStorms.midlatitude_births_per_day` | 6.0 | PROVISIONAL, UNVERIFIED for Earth | Kept | Not searched |
| `SynopticStorms.tropical_births_per_day` | 0.25 | UNVERIFIED | DOCUMENTED | Emanuel and Nolan 2004, abstract: "Some 90 tropical cyclones develop each year around the globe ... a standard deviation of only 10"; also Zhou et al. 2024 (~90), Ramsay 2017 (about 80) |
| `SynopticStorms.beta_drift_m_s` | 2.0 | UNVERIFIED | DOCUMENTED | Gonzalez et al. 2015, abstract: beta "causes tropical cyclones to propagate poleward and westward at approximately 2 m s−1" |
| `SynopticStorms.tropical_needs_sea_c` | 26 | UNVERIFIED | DOCUMENTED | Cione 2015, abstract: "the oft-cited 26°C hurricane threshold linked to hurricane maintenance", 6 % of the hurricanes sampled over cooler sea. For formation the thresholds are 25.5 to 26.5 °C (Dare et al. 2011; Tory et al. 2015) |
| `DailyWeather.storm_low_pa` | 2000 | UNVERIFIED | Kept | Not searched |

The docstrings changed with them: `processes/storm_climatology.py` (the index and the potential intensity),
`library/snow.py` (the degree-day method of Reeh 1991: Calov and Greve 2005, as Consensus gives their opening, "A form,
which is based on that and is widely used in current ice-dynamic models, was proposed by Reeh (1991)"),
`processes/ocean_wind_driven.py` (the form of the Ekman scale; its coefficient was called PROVISIONAL there and is
CALIBRATED in `data/models.yaml`, which the docstring now says), `processes/synoptic_storms.py` (the size of the
drift) and `processes/tectonics_snapshot.py` (the mean age of the ocean floor, 64.2 My: Seton et al. 2020, abstract).
`processes/cryosphere_thresholds.py` and `processes/soils_jenny_rules.py` say what the model search found.

Labels in `docs/BUILD_NOTES.md` that this supersedes, left for the merge (that file is not edited here): section 16.1
on the permafrost thresholds ("[UNVERIFIED: rules of thumb]") and the daily spread ("[UNVERIFIED: about the value of
Reeh 1991, as I recall]"); section 18.1 on the index ("[UNVERIFIED: the exponents and divisors are recalled]") and the
potential intensity ("[UNVERIFIED: the form and the numbers are recalled]").

### Proposals (not applied)

1. **`Tectonics.thickness.continental_normal_m` and `Isostasy.continental_normal_thickness_m`: 36 km** (Cogley 1984),
   with Isostasy's `reference_offset_m` set again, since the offset was set with 35 km. The sources disagree among
   themselves (30, 36, 41.1 km), so this is the weakest of the proposals.
2. **`Soils.depth.decline_depth_m`: 0.43 m**, from the abstract that confirms P0. The 1997 paper's own fit was not read;
   it may give 0.5 m, and the abstract's "0.0077 mm/year under 1 m" may be rounded. The balance depth h0 ln(P0/E) scales
   with it and would be 13 % shallower [INFERRED: 0.434 / 0.5].
3. **`OceanCurrents.drag_coefficient`: 1.2e-3** for winds of 4 to 11 m/s, which hold the trade winds of about 5 m/s
   that Circulation's drag is set for (Large and Pond 1981 at second hand), or their wind-dependent form. Kondo's range
   holds both values.
4. **`StormClimatology.intensity_cap_m_s`: 95 m/s** if the cap is meant to be the strongest measured wind. The cap is a
   plain minimum on the fitted curve, which reaches 90 m/s over a sea of 30.6 °C and 95 m/s over 31.0 °C [INFERRED:
   computed from the four numbers], so the change touches only the warmest seas. It is labelled [PROVISIONAL], and 90
   may stand for a reason of its own.
5. **`Hydrology.demand.sunlight.water_reflects`**: the stated reason, "the usual value for water under a high sun", is
   contradicted by Payne 1972 (0.03 under a high sun and clear sky); 0.07 is near his overcast value. The number may
   stand; the reason should change.
6. **`Hydrology.snow.daily_spread_k`**: the 5 K is the usual value, and the abstracts of Rogozhina et al. 2014 and Wake
   et al. 2015 show that a single value overstates the spread where snow is melting (1 to 2.5 K in a Greenland summer).
   Not a number to put in, but a known direction: a spread that shrinks over melting snow would melt less [INFERRED:
   fewer warm days above freezing in a month just below it]. This matters
   because the daily spread was the change of step 6 that moved the twin most (section 16.1).

### The model search: Cryosphere

- **Permafrost.** The frost number of Nelson and Outcalt 1987, "a dimensionless ratio defined by manipulation of either
  freezing and thawing degree-day sums or frost and thaw penetration depths, can be used to define an unambiguous
  latitudinal zonation of permafrost continuity" [DOCUMENTED: abstract]. It is still used to map frozen ground (Li et
  al. 2021; Zhan et al. 2022, from monthly gridded temperatures: abstracts), with the usual limit F = 0.5 (Huang 2012,
  abstract) and classes of stability above it (Wei et al. 2022). The engine could compute the degree-day sums from its
  monthly temperatures and their daily spread, as `library/snow.py` already does for melt [INFERRED]. The TTOP model
  (Smith and Riseborough 2002), which the current map of the Northern Hemisphere at 1 km uses (Obu et al. 2019), needs
  the ground's thermal conductivity ratio and n-factors, which its own users find do not carry from site to site
  (Garibaldi et al. 2026) [DOCUMENTED: the three abstracts], and which the engine does not have.
- **Sea ice.** Semtner 1976, "A model for the thermodynamic growth of sea ice in numerical investigations of climate",
  with a simpler form without heat storage in its appendix (Semtner 1984, abstract: that form errs by a month in phase
  and about 50 % in amplitude) and Winton's three-layer form (Winton 2000). All need an energy balance of the ice's surface
  and a sea under a lid; EnergyBalance ignores "sea ice as a lid on the sea" [INFERRED from its own statement]. The
  choice between the zero-layer and three-layer forms decides whether an aquaplanet has waterbelt states (Hörner et
  al. 2024, abstract), so for planets unlike Earth the choice matters.
- **Snow cover and lasting ice** are already a published rule (Dutra et al. 2010, section 10).

Should the rule table stay? For sea ice and snow, yes, until EnergyBalance treats ice as a lid. For permafrost, the
two thresholds could be replaced by the frost number with no new input; that is a change of model, not of labels, and
was not made here.

### The model search: the soil classes

No published model was found that gives a soil class from its causes on a planet other than Earth. What exists:

- Maps learned from Earth's soil profiles: SoilGrids (Hengl et al. 2017; Poggio et al. 2021), which predict the classes
  of the World Reference Base and the USDA from about 150,000 profiles and 158 covariates [DOCUMENTED: abstracts]. They
  cannot be carried to another planet, but they are the map to test the twin's soils against.
- Mechanistic models of a profile: Kirkby 2018 (horizons A, B and C from climate and parent material, "parsimonious"
  enough for landform models) and SoilGen (Keyvanshokouhi et al. 2016), which give horizons or properties, not classes.
  Minasny and McBratney 1999 give only thickness, as the engine's depth already does.
- A published table of the kind the engine has: Gray et al. 2011, the dominant WRB groups for each of 70 regimes of
  climate, parent material and relief from the ISRIC WISE database; "58% of test samples matching one of the top three
  predictions, and 74% matching one of the top five", and it "could not be relied upon to predict a single specific soil
  group" [DOCUMENTED: abstract].

Should the rule table stay? Yes: a classification is a rule, and the published alternative is itself a table. A
replacement could follow Gray et al. 2011, which would change the engine's classes from USDA orders to WRB groups; its
regimes would need the engine's climate, rock and relief mapped onto them [INFERRED].

### Not done, and why

- Not searched, once the Consensus allowance was spent: the stream power exponent m (web search leads, not read: "How
  concave are river channels?", Earth Surf. Dynam. 6, 505, 2018; the search summary also names Whipple and Tucker 1999
  for 0.35 to 0.6 and a compilation of 2020 for a median of 0.425), the reference runoff, the vapour's scale height,
  the limits on upwelling cooling and carried heat, the depth of a storm's low, and the recalled claims that are not
  constants (Albedo's "freeze over more easily", Hydrology's deserts, Moisture's residence time of ten days and
  trade-wind depths, the swing of North America's seasons in `energy_balance_spreading.py`).
- Not in scope: the planet's own numbers in `data/planet.yaml` (Earth's tilt, day, year, gravity), the places of
  `src/earth_reference`, and the [UNVERIFIED] statements about methods (Aitken's rule, the order of a drainage sort).
- Papers that the abstracts point to and that hold the numbers were not read: Emanuel and Nolan 2004's equation, DeMaria
  and Kaplan 1994's fit, Reeh 1991, Large and Pond 1981's formula, Heimsath et al. 1997's fit, Bolton 1980's formula.
- I noticed that the docstring of `cryosphere_thresholds.py` still says sea ice forms "below the freezing point of sea
  water", where `data/models.yaml` uses -10 °C of the air; that is not a label and was left.

### Sources (all read on 2026-11-09)

Abstracts, through Consensus:
[Bolton 1980](https://consensus.app/papers/details/fecd808e058a58a4b0458414b1077590/?utm_source=claude_desktop) ·
[Camargo et al. 2007, J. Climate](https://consensus.app/papers/details/626def251920528098a84c06456a267e/?utm_source=claude_desktop) ·
[Camargo et al. 2007, Tellus A](https://consensus.app/papers/details/2e951f4bdd715235bd02a206027ddb7e/?utm_source=claude_desktop) ·
[DeMaria and Kaplan 1994](https://consensus.app/papers/details/9654f92c1cb85557853169671c4288eb/?utm_source=claude_desktop) ·
[Emanuel and Nolan 2004](https://consensus.app/papers/details/f11bda3c7a4a520a928a84ec9577c1ac/?utm_source=claude_desktop) ·
[Zhou et al. 2024](https://consensus.app/papers/details/97704135d343588f84335616460643e8/?utm_source=claude_desktop) ·
[Ramsay 2017](https://consensus.app/papers/details/55b96b47333b59a5bd79570d6965228b/?utm_source=claude_desktop) ·
[Gonzalez et al. 2015](https://consensus.app/papers/details/878058eaee2451e0a82f90a43b247f82/?utm_source=claude_desktop) ·
[Cione 2015](https://consensus.app/papers/details/271d775584d854c8a4bf31b379f10d33/?utm_source=claude_desktop) ·
[Dare et al. 2011](https://consensus.app/papers/details/b65e846e9a3a5b40acc193330324d798/?utm_source=claude_desktop) ·
[Tory et al. 2015](https://consensus.app/papers/details/1f5743762309589cb80230ad6db1adbe/?utm_source=claude_desktop) ·
[Rogers et al. 2017](https://consensus.app/papers/details/654034cd9e725f7ca3875dafd9ab72b3/?utm_source=claude_desktop) ·
[Foltz et al. 2016](https://consensus.app/papers/details/2abae92863fe52bc81b79341c202bc9b/?utm_source=claude_desktop) ·
[Smith and Riseborough 2002](https://consensus.app/papers/details/d438ab27d4d8512195f45b220c775fc3/?utm_source=claude_desktop) ·
[Jin et al. 2007](https://consensus.app/papers/details/c8458be5dfbe597ab29989f1d063863a/?utm_source=claude_desktop) ·
[Nelson and Outcalt 1987](https://consensus.app/papers/details/17b3317ff3375a32a62b0b6d81577aa1/?utm_source=claude_desktop) ·
[Huang 2012](https://consensus.app/papers/details/b711aa26a64253a982be361d11b4bafc/?utm_source=claude_desktop) ·
[Li et al. 2021](https://consensus.app/papers/details/636762bece0e5b8d9d03160aa6d4c0de/?utm_source=claude_desktop) ·
[Zhan et al. 2022](https://consensus.app/papers/details/ae05e47c921559cd8716097e2ce6f369/?utm_source=claude_desktop) ·
[Wei et al. 2022](https://consensus.app/papers/details/07a57952566a5e6689cd965c8c680933/?utm_source=claude_desktop) ·
[Obu et al. 2019](https://consensus.app/papers/details/dcb9dc3c56c35fec8145282dab177ee0/?utm_source=claude_desktop) ·
[Garibaldi et al. 2026](https://consensus.app/papers/details/374b615a0e4c57f682a4b2429fd7e1d7/?utm_source=claude_desktop) ·
[Semtner 1976](https://consensus.app/papers/details/3bf21b3f874654a2a39b113c100bc1a2/?utm_source=claude_desktop) ·
[Semtner 1984](https://consensus.app/papers/details/2bd0be450a745f71b21334f75ea4da8c/?utm_source=claude_desktop) ·
[Winton 2000](https://consensus.app/papers/details/843db4e71ff5595ba0b991c9f6b6273d/?utm_source=claude_desktop) ·
[Hörner et al. 2024](https://consensus.app/papers/details/1f09cd0c0b475204a53af76af55645fd/?utm_source=claude_desktop) ·
[Fausto et al. 2011](https://consensus.app/papers/details/a0e1cfd0c3a7555a958e8e9251a5e486/?utm_source=claude_desktop) ·
[Calov and Greve 2005](https://consensus.app/papers/details/0de1d79f829d5ebeae74e3822bf84095/?utm_source=claude_desktop) ·
[Rogozhina et al. 2014](https://consensus.app/papers/details/804ac109307a5afabaf3fa93ab63f35f/?utm_source=claude_desktop) ·
[Wake et al. 2015](https://consensus.app/papers/details/0ede4956a79253b0a35accab83f81474/?utm_source=claude_desktop) ·
[Heimsath et al. 1997](https://consensus.app/papers/details/2b0ebb0a2242565ab759fb0fed2f7889/?utm_source=claude_desktop) ·
[Heimsath et al. 1999](https://consensus.app/papers/details/7ec56742eaa551b18b4b0332416be8c6/?utm_source=claude_desktop) ·
[Heimsath et al. 2000](https://consensus.app/papers/details/e68299cc46b3554fbb4e5ace891dad8a/?utm_source=claude_desktop) ·
[Heimsath et al. 2001](https://consensus.app/papers/details/8f7fe3658d985037ba6ed38f316276f5/?utm_source=claude_desktop) ·
[Dietrich et al. 1995](https://consensus.app/papers/details/86b48ca2419d50ddbfa815aba1e22a9c/?utm_source=claude_desktop) ·
[McKean et al. 1993](https://consensus.app/papers/details/9d2e483fc3ee56fbaee9405498410e71/?utm_source=claude_desktop) ·
[Ben-Asher et al. 2017](https://consensus.app/papers/details/874e5730eb115701837306061ff1d283/?utm_source=claude_desktop) ·
[Payne 1972](https://consensus.app/papers/details/d5f11377d114554c9cc39fff511445f7/?utm_source=claude_desktop) ·
[Zhang et al. 2010](https://consensus.app/papers/details/da20c4e13c0e5d8bb013aedd69239afc/?utm_source=claude_desktop) ·
[Tsvetsinskaya et al. 2002](https://consensus.app/papers/details/b97136c8178d51f0a0fcbef4557c88d9/?utm_source=claude_desktop) ·
[Large and Pond 1981](https://consensus.app/papers/details/cc29566d8d9556adb0f3daf9e894b381/?utm_source=claude_desktop) ·
[Kondo 1975](https://consensus.app/papers/details/02df8cb8a6775e78aa6043925c47353e/?utm_source=claude_desktop) ·
[Hicks 1972](https://consensus.app/papers/details/e9e765ad685e565fa22534fd0c9efc83/?utm_source=claude_desktop) ·
[Lozovatsky et al. 2005](https://consensus.app/papers/details/d8738526cead55d08a682f06d2a3a25a/?utm_source=claude_desktop) ·
[Konashenok 2012](https://consensus.app/papers/details/c288bdac6b8453a8ab99764fb68c708d/?utm_source=claude_desktop) ·
[U.S. Standard Atmosphere 1976](https://consensus.app/papers/details/549fca3b0eab5eb6bfba7da9c933a824/?utm_source=claude_desktop) ·
[Baumgartner et al. 2020](https://consensus.app/papers/details/ea6dd91ecb2851c4acd0cd47ba599290/?utm_source=claude_desktop) ·
[Cogley 1984](https://consensus.app/papers/details/c93e1687cf36534795cc8ec825564813/?utm_source=claude_desktop) ·
[Yanagi 2011](https://consensus.app/papers/details/0ac28ddff403567aa23e85ece164f30e/?utm_source=claude_desktop) ·
[Cawood et al. 2019](https://consensus.app/papers/details/97baf4fd90f45a018b8e247ccb7f8ac2/?utm_source=claude_desktop) ·
[Zhu et al. 2023](https://consensus.app/papers/details/fb3fb4253750533a8387aaf3cb8cec9a/?utm_source=claude_desktop) ·
[White et al. 1992](https://consensus.app/papers/details/3bb64dd7dbfc5fe78719bd8fc61d46ae/?utm_source=claude_desktop) ·
[Seton et al. 2020](https://consensus.app/papers/details/dce3b02d148e5e52b04791011c40a74e/?utm_source=claude_desktop) ·
[Cogné et al. 2004](https://consensus.app/papers/details/4ae08d47f9df53038d20914da281a435/?utm_source=claude_desktop) ·
[Kawano et al. 2023](https://consensus.app/papers/details/5ab47a3716525c68b7519e35794c2d28/?utm_source=claude_desktop) ·
[DeMets et al. 2010](https://consensus.app/papers/details/4bb740a5da785e1c8d7e193a1d9ae157/?utm_source=claude_desktop) ·
[Zheng et al. 2014](https://consensus.app/papers/details/0ba679036306551a9eef20206f446c77/?utm_source=claude_desktop) ·
[Chapin 1996](https://consensus.app/papers/details/507b24268fb856a4af017f6b0a07d76a/?utm_source=claude_desktop) ·
[Karabulut et al. 2019](https://consensus.app/papers/details/353f928b520f597583a19ecd1ffe4bf4/?utm_source=claude_desktop) ·
[Tenzer et al. 2012](https://consensus.app/papers/details/ca57ea3be87a5b5594de608dc1995c39/?utm_source=claude_desktop) ·
[Segev et al. 2006](https://consensus.app/papers/details/61f1ea7964ce55e1934cd898732a5f11/?utm_source=claude_desktop) ·
[Theunissen et al. 2022](https://consensus.app/papers/details/ba6d98f427e851a7958b42bb32ce943d/?utm_source=claude_desktop) ·
[Jackson et al. 1996](https://consensus.app/papers/details/d7a508b775105247a9a1cefd92c79fbc/?utm_source=claude_desktop) ·
[Schenk and Jackson 2002](https://consensus.app/papers/details/753b157fdcec57b593e35ed7b31c3ab4/?utm_source=claude_desktop) ·
[Canadell et al. 1996](https://consensus.app/papers/details/8caf193dd79b51da9bc9a69f81cf7289/?utm_source=claude_desktop) ·
[Gray et al. 2011](https://consensus.app/papers/details/262da6acc39e5415a81454e9cfd8004c/?utm_source=claude_desktop) ·
[Hengl et al. 2017](https://consensus.app/papers/details/2a3e8e21d081561398c34ca89a66ce5f/?utm_source=claude_desktop) ·
[Poggio et al. 2021](https://consensus.app/papers/details/8be4086db9a457f9b158c879159b57d9/?utm_source=claude_desktop) ·
[Kirkby 2018](https://consensus.app/papers/details/b22b998990aa513ea5b71be27cee53e8/?utm_source=claude_desktop) ·
[Keyvanshokouhi et al. 2016](https://consensus.app/papers/details/1465e07f2a705bb0aa6e7690a040a13a/?utm_source=claude_desktop) ·
[Minasny and McBratney 1999](https://consensus.app/papers/details/7c61bfc6386451b39ddbc95439ea8122/?utm_source=claude_desktop) ·
[Li et al. 2026 (cyclone lifespans)](https://consensus.app/papers/details/67cdff7140d25e928ae48d016909d71a/?utm_source=claude_desktop)

Code, through GitHub's code search (the matching lines read): wy2136/xtci (`xtci/ERA5.py`, `xtci/AMx.py`,
`xtci/MERRA2.py`); MichaelFischerWx/TC-ATLAS (`favorability.py`); guillem/how-things-work
(`src/routes/atmosphere-weather/atmosphere.ts`); sanjaymurali/Information-Retrieval (a saved copy of Wikipedia's
"Tropical cyclone forecasting"); umwm/umwm (`src/umwm_domain.f90`), NPIOcean/kval (`src/kval/ocean/empirical.py`),
FVCOM-GitHub/FVCOM (`src/mod_bulk.F`, the same formula without the name); TEOS-10/GSW-C and TEOS-10/GSW-Python
(`gsw_internal_const.h`);
Unidata/MetPy (`src/metpy/constants/default.py`, `src/metpy/calc/thermo.py`); jpgannon/IntroHydro_Figures
(`figures/ch03/vapor_pressure/vapor_pressure.py`); code carrying the U.S. Standard Atmosphere 1976
(imshivanshutiwari/ballistic-6dof-sim `src/atmosphere.py`, Stratolink-hq/Stratolink `isa.py`); the SPLASH code
(geco-bern/rsofun `src/waterbal_splash.mod.f90`, cran/splash `R/splash.R`, simonbrewer/safricaro `src/splash.f`);
deepayan/r-refmans (macroBiome's reference manual).

Computed: TEOS-10's `gsw` 3.6.23 from the Python package index.
