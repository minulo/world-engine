## The ocean's overturning driven by density (2026-11-09)

Section 22.3 named the next cause of the cold northern summers: the twin's ocean carries 0.52 PW southward across the
equator where Earth's carries about 0.4 PW northward, through an overturning driven by density that the engine did not
have. This section builds that overturning from causes, measures it on the preview Earth twin, and keeps it out of the
default world: it moves the twin's ocean heat, hemispheres and northern summer the right way, and it makes four of the
twin's tests fail that pass without it. Every number is the preview mesh [MEASURED: `handoff/overturning/`, scripts and
logs], unless a line says otherwise.

### What was built

**A second version of OceanCurrents**, not a new slot (`ocean_wind_and_density.py`, with `library/overturning.py`). The
design has one ocean slot, and its first version's `ignores` names "deep overturning driven by density": a second version
removes an ignore rather than adding a process to the design's list. The two parts also share what one of them alone
would have to guess: the salt that sets the overturning is carried by the loops, the wind's drift across the Southern
Ocean feeds it, and its heat goes into the same member of `surface_heat_flux`, `ocean_heat_convergence`, with a driver
of its own (`carried_by_overturning`). The wind-driven part is the first version's, unchanged; the first version stays in
its file and is still the default. Swapping is one line in `data/models.yaml`, with two more fields in the slot's
`writes`, `sea_surface_salinity` and `overturning_sinking`; the constants sit under `OceanCurrents.overturning`.

- **Salt.** The surface salinity tends to the steady balance of the layer whose temperature the loops carry (300 m of the
  loops' 1,000): the salt that the freshwater balance leaves (Moisture's evaporation over the sea less its rain, and
  Hydrology's rivers where they reach the sea, all of this round), carried by the loops and by the overturning's own
  upper water, and mixed along every side by eddies at 1,000 m²/s [UNVERIFIED: a common value, recalled]. Where the sea
  loses water the salt it leaves is the mean salinity's; where rain and rivers give more than the air takes they dilute
  the water's own salt, so that no cell falls below nothing [INFERRED; with the mean salinity there too a cell of the
  world of seed 7 fell to -7.8 psu, MEASURED]. Salt is kept: each connected sea's mean is 35 psu. On the twin the
  freshwater balance closes almost by itself: the sea loses 1,274 mm a year to the air, gets 1,194 back as rain and
  80 from rivers [MEASURED].
- **Density.** The simplified equation of state of Vallis 2006, straight in salinity and curved in temperature, so that
  near freezing water changes its density little with temperature [DOCUMENTED for the thermal coefficients 1.67e-4 per K
  and 1e-5 per K², at 10 °C and 35 psu: Nycander, Hieronymus and Roquet 2015, read in a search service's excerpt;
  UNVERIFIED for the haline coefficient 7.8e-4 per psu, recalled]. The sea's water is held at -1.8 °C or above, since
  the engine's temperature over a winter sea is the air's.
- **Regions.** The planet is cut into bands of latitude two cell spacings wide, and a band in which the sea deeper than
  1,000 m runs all the way round the planet is taken out: no coast there holds up the east-west difference of pressure
  that a north-south current in the balance of the spin needs [INFERRED: the reason the Drake Passage matters, as
  recalled]. What is left of the sea falls into connected regions. On the twin the bands that go round lie between
  64.1 and 55.5° S and north of 82.5° N, and the sea falls into two regions: one from 55° S to 82° N, in which the
  Atlantic, Indian and Pacific join south of Africa and Australia, and the seas around Antarctica south of 64° S.
  Nothing is placed by name or by hemisphere.
- **Where the deep water forms.** In each region, over sea at least 1,000 m deep, each cell counts the month of its
  densest water. Ice is a lid: a month counts lighter by the contrast times the logarithm of the open share of the cell,
  so water under ice all month counts not at all. Where the wind's drift presses the light upper water down (an
  anticyclonic gyre) the water counts lighter, and where it lifts the water beneath (a cyclonic gyre) about as it is
  [INFERRED: after the preconditioning of deep convection that Marshall and Schott 1999 describe, as recalled]. A cell's
  share of the region's sinking is its area times a factor that falls by e for every 0.5 kg/m³ by which its water counts
  lighter than the region's densest [PROVISIONAL]. Brine from freezing sea ice, which makes Antarctic Bottom Water on
  Earth, is ignored.
- **How much forms.** The balance of the light upper water's volume of Gnanadesikan 1999: g′D²/ε = 2KvA/D + τLx/(ρf) −
  A_I Lx D/Ly, sinking against mixing, the wind's drift into the region across a latitude that goes round, and the
  eddies' return across it [DOCUMENTED: the four terms as Gnanadesikan, de Boer and Mignone 2007 restate them, eqs. 2a,
  2b, 3a and 3b, read in search excerpts; Kv = 1e-5 m²/s from Gnanadesikan 1999's 0.1 to 0.15 cm²/s, and A_I = 1,000
  m²/s within the 300 to 4,000 of a GFDL study, both read in excerpts]. Its one positive root is found by halving. g′ is
  gravity times the sinking water's density over the mean density of the region's surface water; ε is 2|f| where the
  water sinks [UNVERIFIED: the transport g′D²/(2f) of a current in the balance of the spin whose light layer thins from
  D to nothing, recalled; the excerpts call ε a resistance and give no value]. The wind's drift is the first version's
  Ekman transport across the border; the eddies' length is the border's east-west length (counted along the cells'
  zigzag it was 55,300 km on the twin [MEASURED], about 2.5 times the circle at 56° S).
- **The upper water and its heat.** The deep water rises evenly over the region by mixing, and at the border by the
  wind's drift; the upper water flows from where it rises to where it sinks, as a potential flow within the region. It
  carries 0.7 of the gap between the surface's temperature and the deep water's [CALIBRATED on Earth's numbers at
  26.5° N: 17.2 Sv and 1.22 to 1.33 PW, 88 % of it by the overturning, as search excerpts of the RAPID array's papers
  give them, an effective gap of 15.6 K where the surface is about 22 K warmer than the deep water, UNVERIFIED], in the
  advective form of the loops' heat; the deep water rises at the temperature of the water that sank in its region that
  month. What rises equals what sinks in each region, so the overturning moves heat and makes none.
- **Salt and overturning together.** Salt sets density, density the sinking, and the overturning's flow carries salt.
  They are worked out in passes from the last round's salinity (from a sea with no overturning in a climate run's first
  round): each pass moves the salinity half way to the steady state of that pass's flows, until it moves less than
  0.001 psu on the sea's mean or eight passes are done.

### Conditions

| Condition | Result |
|---|---|
| A closed basin saltier toward its north pole sinks there and carries heat north | Passes (`tests/test_overturning.py`): a sea from 60° S to 60° N that evaporates more in its north; 6.3 Sv sink, all north of 40° N, the north 2.6 psu saltier on the mean, and the overturning carries 0.19 PW north across the equator |
| A mirror-symmetric basin carries no heat across its equator | Passes: the same sea, mapped onto itself by the mesh's own symmetry, with the same freshwater balance in both halves; the two ends share the sinking to 5e-16, and 0.05 W crosses the equator, against 1.9e14 W in the sea above |
| The heat sums to zero over the sea | Passes: to 1e-12 of the heat moved in double precision, for any rise and sinking; to 1e-6 in the stored fields, which are single precision |
| Determinism | Passes: the same inputs give the same fields and drivers bit for bit. The default world, whose slot is still the first version, has the same 138 fingerprints as before this work, in the same 41 rounds |
| Ice is a lid; the latitudes that go round are found; the depth balance has its one root, and without the Southern Ocean's terms the sinking grows as Kv^(2/3) (Bryan 1987's scaling) | Pass |
| The tests catch a broken overturning | Five breakages tried, each caught: deep water rising at 0 K, the upper water flowing backwards, sinking chosen without density, the lightest water sinking, ice no lid |

### Measured on the Earth twin

The preview twin built with each version [MEASURED: `handoff/overturning/overturning_twin.log`; the first version's
column is the twin of section 22, the same numbers]:

| | First version (default) | Second version | Earth |
|---|---|---|---|
| Ocean's heat across 20° S | 1.04 PW southward | 1.03 PW southward | |
| Ocean's heat across the equator | 0.52 PW southward | 0.13 PW southward | about 0.4 PW northward |
| Ocean's heat across 26.5° N | 0.41 PW northward | 0.86 PW northward | 1.3 PW, the Atlantic's alone |
| Ocean's heat across 40° N | 0.22 PW northward | 0.43 PW northward | |
| The overturning's own, across the equator and 26.5° N | | 0.30 and 0.44 PW northward | |
| Northern half, year | 11.83 °C | 12.33 °C | 14.61 °C |
| Southern half, year | 14.84 °C | 14.60 °C | 13.25 °C |
| The planet, year | 13.35 °C | 13.48 °C | 13.96 °C |
| Sea at 40 to 60° N, year | 3.77 °C | 4.94 °C | 7.79 °C |
| Sea at 40 to 60° N, July | 8.04 °C | 9.48 °C | 13.06 °C |
| Land at 40 to 60° N, warmest month | 10.21 °C | 11.28 °C | 18.38 °C |
| Land at 40 to 60° N, coldest month | −13.72 °C | −13.09 °C | −12.67 °C |
| Land at 40 to 60° N, year | −2.35 °C | −1.48 °C | 3.45 °C |
| Tropics less polar caps, year | 40.0 K | 39.1 K | 40.0 K |
| Climate rounds to settle | 32 | 19 | |

(Earth's column: CRU at the same cells; the heat across the equator after Marshall et al. 2013 and across 26.5° N after
Hirschi et al. 2020, as section 22.3 gives them.)

How the second version's overturning is made up on the twin [MEASURED: the same log]: the region north of the Drake
Passage sinks 16.0 Sv of dense water, from a light upper layer 291 m deep with g′ = 0.036 m/s²; mixing lifts 22.5 Sv,
the wind's drift brings 1.6 Sv across the Southern Ocean's border and the eddies take 8.2 Sv back across it, so that
water sinks along that border too. The twin's westerlies there are weak: 2.5 m/s toward the east on the mean over the
sea between 55 and 60° S (2.4 with the first version) [MEASURED]; with Gnanadesikan's 0.1 to 0.2 Pa the wind's term on
Earth would be 18 to 36 Sv [INFERRED: τLx/(ρf) at 56° S]. Of the 20.4 Sv that sink in all, 3.9 sink in the North Atlantic between 40 and 50° N, 1.0 in the Labrador and
Nordic seas, 1.0 in the subtropical North Atlantic, 2.0 in the North Pacific between 40 and 50° N, 4.6 in the
subtropical northwestern Pacific (the Japan Sea within it), 2.2 at the edge of the polar sea north of 82.5° N (the
eddies' return there, a term written for the Southern Ocean), and 5.6 south of 40° S, most of it along the Southern
Ocean's border. Earth's northern deep water forms in the North Atlantic beyond 55° N. The surface salinity comes out
34.4 psu in the North Atlantic at 50 to 65° N and 33.0 in the North Pacific at 45 to 60° N, Earth's order; 37.4 and
37.8 in the subtropical North Atlantic and North Pacific; 32.0 in the Southern Ocean at 50 to 60° S and 32.4 in the
Arctic; from 20.4 to 39.8 over all [MEASURED]. The twin's northern seas are colder and freeze more than Earth's, so its
densest open water lies further south than Earth's [INFERRED].

The twin's freshwater balance favours the Atlantic only a little: between 35° S and 66° N its Atlantic loses 0.49 Sv
more to the air than rain and rivers give it, 222 mm a year, and its Pacific 0.79 Sv, 183 mm a year (219 and 180 with
the second version) [MEASURED: boxes of longitude and latitude, in the same log]. Earth's Pacific gains fresh water
[UNVERIFIED: recalled].

**The spreading constant.** With the second version the fall from the tropics to the polar caps is 39.1 K at 0.57,
against CRU's 40.0 K; it equals CRU's at 0.549 (40.1 K at 0.545, 39.5 K at 0.56; `handoff/overturning/fit_spreading.log`,
run with the second version as the slot's default). The constant stays 0.57, the first version's fit, since the first
version stays the default; its label gives the other fit.

### The decision: the second version is not the default

The rule was: the default only if the twin improves measurably (the ocean's heat across the equator toward the right
sign, the northern summer warmer, the planet within 2 K) and no design condition gets worse. The first three hold: 0.52
PW southward becomes 0.13, the warmest month of land at 40 to 60° N is 1.1 K warmer, and the planet is 0.5 K colder
than Earth's where it was 0.6 K. But with the second version in the slot, four of the twin's tests that pass fail
[MEASURED: `python -m pytest tests/test_earth.py -k "twin or amazon_carries_its_water"` with the slot switched in
`data/models.yaml`, then switched back; the numbers from `handoff/overturning/twin_pins_second_version_spreading_0.57.log`
beside `handoff/summer/twin_pins.log`]:

| Test of the twin | First version | Second version | The test asks |
|---|---|---|---|
| The Sahara's rain, June to August | 24.4 mm a month | 41.3 mm a month | under 30 (GPCP 15.2) |
| Desert biomes over the Sahara | 0.84 | 0.38 | over 0.8 |
| The largest river at a coast (the Amazon) | 134,451 m³/s | 93,112 m³/s | within a factor of two of 210,000 |
| Cold water off north-west Africa, against its band | −0.7 K | +0.4 K | colder than its band |

Two strict expected failures would pass and become tests: group D on 16.6 % of the twin's land (14.9 % before; the test
asks over 15 %), and the sea off California 0.5 K colder than its band (0.6 K warmer before; Earth's 2.7 K colder). Other
numbers that move: Canada's boreal share 0.31 (0.22), western Europe's January −2.9 °C (−4.5; Earth 3.2), Arabia's summer
rain 84.0 mm a month (77.4; GPCP 4.7), the land at 40 to 60° N 22.2 K warmer in July than in January (21.7; Earth 31.1).
With the spreading constant refitted to 0.55 the same four fail, by about as much (41.4 mm, 0.36, 94,088 m³/s, +0.5 K;
`twin_pins_second_version_spreading_0.55.log`). The four are tests of patterns of Earth, and the Sahara's summer rain is
one of the conditions of build step 5 (section 15.2): a condition gets worse, so the slot keeps its first version.

Why the Sahara gets wetter and the Amazon drier was not measured. The overturning moves heat from the southern hemisphere
to the northern, and on Earth that is what holds the tropical rain belt north of the equator (Marshall et al. 2013, as
section 22.3 reads it); the twin's rain may follow its warmer north [INFERRED, not measured]. The overturning also puts
much of its heat at 20 to 50° N, close to the Sahara, where Earth's goes further north.

### What was tried on the way, and why the forms are as they are

All on the preview worlds [MEASURED unless marked]:

1. **A sharp choice of where water sinks** (the densest cells only) sank about 16 Sv in the Japan Sea and the North
   Pacific at 40 to 44° N on the twin, and the climate did not settle in 60 rounds: the sinking leapt between the North
   Pacific, the eastern North Atlantic at 42 to 44° N and the Southern Ocean from round to round, each warming its own
   water until another was denser. A share that falls smoothly with density settled the twin; with a contrast of
   0.3 kg/m³ the default world still did not settle.
2. **Each round from rest** (the salinity of a sea with no overturning, then the passes) gave the same leaping while
   the choice was sharp, and keeping the salt from round to round did not stop it. With the smooth share, passes that
   each move the salinity half way to their steady state until it moves less than 0.001 psu settled the twin, the
   default world and seed 7; without the halving the passes did not converge on seed 10 (eight passes in every round).
3. **Sharp rules for ice and for the wind's lifting** (no deep water under ice in more than half of a cell, none where
   the drift presses down) left the climate of seed 10 unsettled after 60 rounds, the heat of the ocean changing by a
   little more than the settle test allows from round to round. Making the rule for ice smooth did not settle it; making
   the rule for the wind's lifting smooth as well did, in 42 rounds.
4. With all of this, the climate settles in 19 rounds on the twin, 30 on the default world, 43 with seed 7 and 42 with
   seed 10, where the first version takes 32, 41, 34 and 27.
5. Without the wind's lifting the twin's overturning is weaker: the ocean's heat across the equator 0.20 PW southward,
   the northern half 12.20 °C, the warmest month 10.96 °C. With it sharp (and the climate of seed 10 left unsettled) it
   was stronger: 0.09 PW northward, 12.52 °C and 11.47 °C. How the four tests of the twin above fare under those forms
   was not measured.

### Departures and limits

- The design's list of processes is kept: the overturning is a second version of OceanCurrents, not a twenty-third
  process. It reads five fields more than the first (`sea_depth`, `snow_ice_cover`, `ocean_evaporation`, `precipitation`,
  `river_discharge`) and its own salinity from the last round.
- One deep sea per region: every water mass that sinks fills it, and the layers of the deep sea and the depth at which
  each water spreads are ignored, and so are sills and straits: the Japan Sea and the Mediterranean join the open ocean
  at the mesh's resolution, and the Japan Sea sinks with the rest of the North Pacific.
- The Southern Ocean's terms apply at the edge of any band of sea that goes round, so at the edge of the polar sea north
  of 82.5° N as well, where they sink 2.2 Sv on the twin.
- The overturning can hold more than one state, and each climate run starts from a sea with no overturning: it finds the
  state reached from there. Kicks of 2 and 4 psu to the North Atlantic at the start did not hold an Atlantic state in
  an early form of the process [MEASURED, offline on the twin's fields].
- The upper water flows as a potential flow, not along western boundary currents, and its heat lands where it
  converges: up to 46 W/m² on the year's mean near where it sinks on the twin.
- Cost: one run of the process from rest on the standard mesh (163,842 cells, eight passes) took 31 s where the first
  version takes 4 s [MEASURED: the process alone on made-up inputs]. In a climate run the early rounds take eight passes
  and the late ones one or two; the standard build was not run.
- No "why" patterns for the two new fields or the two new drivers: the engine refuses patterns for what the slot's
  implementation does not write, and the default does not write them. They are to be written when the second version
  becomes the default.
- Not done: the standard mesh; a test of the second version on the whole default world (its tests are of the process
  alone); the climate rerun inside the history of a seeded world, which the default profiles do not run.

### Sources

Read through a search service, in excerpts (the journals' own pages, arxiv.org and the GFDL archive could not be reached
from the build machine): Gnanadesikan 1999 (Science 283) and Gnanadesikan, de Boer and Mignone 2007 (AGU Monograph 173)
for the four terms of the balance and the values of Kv and A_I; Cimatoribus et al. (Ocean Science preprint), citing
Marotzke 1997, for the scaling Ψ ~ Δb D²/f; Nycander, Hieronymus and Roquet 2015 (GRL 42) for Vallis's coefficients;
papers of the RAPID array for 17.2 Sv and 1.22 to 1.33 PW at 26.5° N and the overturning's 88 %; Stommel 1961 for the two
regimes of a two-box flow; Park and Bryan 2000 for the measured exponent of Bryan's scaling (closer to 1/2 than 2/3).
Recalled, not read: the haline coefficient 7.8e-4, the freezing point −1.8 °C, Earth's mean salinity 34.7, the eddies'
mixing of salt 1,000 m²/s, g′D²/(2f), Marshall and Schott 1999 on preconditioning, and the temperatures of Earth's
surface and deep water at 26.5° N.
