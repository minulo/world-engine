# Build notes

State of the build on 2026-10-05: build steps 0, 1 and 2 of the design document "World engine design:
physical causes, replaceable processes". Steps 0 and 1 had two independent reviews and a third,
narrower check. Step 2 had two independent reviews, a third check that overturned part of what I
had concluded from the Earth tests, and a fourth of what was changed in answer. Each was followed
by fixes (section 5).

Labels: **[MEASURED]** I ran it in the build environment and read the number. **[DOCUMENTED]** I opened
the source during the build. **[INFERRED]** my reasoning. **[UNVERIFIED]** recalled, not checked.
**[PROVISIONAL]** a first value that an Earth test must tune. **[CALIBRATED]** set by hand on the default
planet.

The build environment was a cloud workspace with 2 processor cores and about 8 GB of memory, Python 3.13,
and the versions in `requirements.lock`. Nothing here was run on the target laptop.

## 1. What exists

| Build step | State | Evidence |
|---|---|---|
| 0. Skeleton | Done | Tests of the mesh, parameter files, the scheduler with every refusal, rounds, pushes, labels, the store, the server, the test harness |
| 1. The slice | Done, with the gaps of section 6 | Tests of the ten processes and of the whole world; two trials in `trials/results/` |
| 2. Water on land | Done, with the misses of section 4 | Drainage, Hydrology and a stand-in for Soils; tests of each on ground built for the purpose, on the default world and on Earth's own relief, rain and warmth |
| 3 to 11 | Not started | |

`python -m pytest` runs 643 tests in about 9 minutes. 609 pass. The other 34 are
expected failures: each states a pattern of Earth, or a condition of the design, that the engine does
not meet, with the number measured (sections 4.2 to 4.6). Without the Earth reference data
(section 4.3) the 85 tests that need it are skipped, and the rest pass. [MEASURED]

## 2. Step 0 against its "done when"

| Condition in the design | Result |
|---|---|
| Three toy processes with a loop, a modifier and a push reach a known steady answer | Pass. a = 7 and b = 8 to within 1e-6 after 52 rounds [MEASURED: `tests/test_engine.py`] |
| First-round defaults are tested | Pass. Round 1 reads the default of fields.yaml; round 2 reads the blended copy |
| Every refusal message is tested | Pass. Every refusal of the scheduler is checked for its message (`tests/test_scheduler.py`, 60 tests), and the engine's own in the four engine test files |
| A world holding only geometry is identical on a second run | Pass, and identical in two fresh interpreters with different hash seeds |
| It opens in the viewer through the local server | Pass. Checked in a headless browser (`tools/viewer_check.py`) and by tests of the server's answers |

The scheduler is the routine of the design's check script, ported with its messages. It gives the
design's order for all 22 declarations and for the processes built so far. [MEASURED:
`tests/test_scheduler.py`, which holds the design's declarations as test data] It was not changed by
any of the reviews.

The mesh: cell areas add up to the sphere to 12 digits; the largest cell has 1.36 times the area
of the smallest, at every level from 5 to 7; the cells are 240, 120 and 60 km apart. [MEASURED]

## 3. Step 1 against its "done when"

| Condition in the design | Result |
|---|---|
| Each process meets the fixed pass conditions of its first version | Pass for the conditions that need no Earth data, with one exception since step 2: the dry belt of the north (section 3.1). The conditions that feed a process real inputs are run for four processes (section 4.3) |
| Its tolerance is recorded | Not done. Section 4.3 gives the misfits measured so far; none is adopted as a tolerance |
| The two patterns the first version cannot show are measured and recorded as failures | Not measured against ERA5. What the engine's own world shows: no wind reverses with the season, and the sinking air is the same at every longitude |
| The crust trial meets conditions fixed before it runs | Pass on the default world at both mesh sizes, after one change to how the first condition is measured. Two failures outside the default setting. Section 3.2 gives all of it. You confirmed the decision on 2026-10-04: the crust stays on moving points |
| explain() returns a chain | Pass |
| The frozen-region example works in reduced form | Pass (section 3.4) |
| A place label alone changes no other field | Pass: every other field keeps its fingerprint |
| Both poles are colder than the equator and below freezing in the yearly mean, and the Albedo slice marks ice at both | Pass (section 3.3) |
| Run times are measured for the preview and standard profiles | Done (section 4.7 for the build as it stands) |
| The viewer shows any stored field on the globe or a flat map, plays the months, and on a click shows the cell's values and its "why" answer, with a notice when the climate did not settle or a model ran outside its range | Done. Checked in a headless browser |

### 3.1 Pass conditions, on inputs built for the purpose and on the default world

All [MEASURED] by `tests/test_processes.py` and `tests/test_world.py` (preview mesh, seed 20261004).

| Process | Fixed pass condition | Result |
|---|---|---|
| PlanetGeometry | Areas total 510.1 million km²; Coriolis parameter 1.03e-4 per second at 45° | 510.06; 1.031e-4 |
| Tectonics | Two plates moving apart make floor that is youngest where they part; closing continents thicken the crust on both sides; plates sliding past each other make a transform boundary whichever way the boundary runs; a head-on closing speed is reported to within 3 %; one seed gives the same plates at two mesh levels; the planet turned by one face of the mesh is the same world turned | Pass |
| Isostasy | Depth 2,500 m at age zero and 2,500 + 350 √age for young floor, the published rule for old floor from the age where the two cross (26 My); 15 % of added thickness becomes height | Pass |
| SeaLevel | In a flat basin the level is volume over floor area; water spills over a rim, and two hollows merge; low ground behind a barrier stays dry and the barrier is named; the sea holds the planet's water | Pass; the volume is held to 1 part in 10,000 |
| Insolation | Equator at an equinox gets star output ÷ π; polar day and night at a solstice; the global mean is a quarter of the star output | Pass |
| Albedo | With cloud and low-sun terms at zero, each surface returns its table value; ice-covered cells reflect 0.62; ice lies on the sea where the year's mean is below −10 °C; snow lies on land only where it fell and until it has melted | Pass |
| EnergyBalance | Without spreading, the yearly mean is (absorbed sunlight − A) ÷ B; colder toward the poles; a larger swing inland than over sea; 6.5 K per km of height | Pass |
| Circulation | On an all-ocean planet each month in the north mirrors the south half a year later; trade winds from the east, westerlies in mid-latitudes, high pressure near 30°; as much air sinks as rises | Pass |
| Moisture | One ridge across a steady wind: wet on the side facing the wind, dry on the sheltered side; evaporation equals precipitation over the globe; the driest land band between the equator and 60° lies between 15° and 40° | The first two pass: the side facing the wind gets 2.9 times the rain of the same strip without the ridge, the sheltered side 0.2 times (numbers of the third check of step 1); evaporation over precipitation is 1.0000. **The third passes in the south (24°, 269 mm) and fails in the north since step 2**: the driest band there lies at 58°, with 297 mm, and the dry belt at 24° gets 362 mm. See below |
| Biomes | Twelve months at 26 °C with 300 mm each give tropical rainforest and class Af; a warmest month below freezing gives ice and no plant cover; seven further classes follow the published rules | Pass |

**The dry belt of the north.** In step 1 land gave no water back to the air, the land was far too dry,
and the dry belt was its driest band. With water returned by the land (step 2) the land of the default
world gets twice the rain it did, the dry belt at 24° north gets 362 mm, and one band is drier: at 58°
north, 297 mm. A sixth of that band is land. It stands 1,080 m high on average, its yearly mean is
−13 °C and it lies under snow in every month. Cold air holds little vapour, and ground under snow
gives the air nothing back. [MEASURED] On Earth the land at these latitudes gets 690 mm. [MEASURED from
the rain data of section 4.3] The same condition fails in the north on Earth's own relief (section
4.6), which points at the engine's cold northern land and not at this world's mountains. [INFERRED]

When the condition first failed I reworded the test so that it passed, and the first reviewer of
step 2 found that. The design's condition is back as the design wrote it
(`test_the_driest_land_band_between_the_equator_and_60_degrees_lies_between_15_and_40`), marked as an
expected failure in the north. The rewording is kept beside it under its own name: equatorward of
50° the driest band lies in the dry belt, with 1.55 and 2.09 times as much rain on the land of the
storm belt. It proves less.

Two conditions were added by the reviews of step 1 and hold on every mesh tried. The rain over the
500 km before a wall 2.5 km high is 4.1, 3.9, 3.9 and 3.9 m a year at cells 480, 240, 120 and 60 km
apart. Air over cold high ground holds at most 0.9 of what it can hold. [MEASURED by the third check
of step 1]

### 3.2 The crust trial (Question 16)

`trials/crust_points_trial.py`. A bare model of moving plates: points turn with their plates for
125 rounds of 2 My; a point that meets a point of another plate with priority is consumed; a cell
with no point nearby becomes new ocean floor; the crust is drawn onto the mesh every round, and
every 20 rounds the points are replaced by one fresh point per cell, filled from the old points.
Three conditions were written before the first run: (A) a marked patch of crust lies within one
cell of the place its plate's motion gives; (B) the area of continental crust changes by no more
than 2 % beyond what closing plates destroyed; (C) fewer than 1 % of cells a round switch crust
type and switch back.

**What happened.** The first run, before the reviews, passed all three at both mesh sizes. The
reviews changed how plates are seeded, so the trial now runs on other plates. Run again, it
failed condition A in five runs of six: the patch lay 1.3 to 1.9 cells from its place, and 0.9
in the sixth. [MEASURED]
The cause is in the measurement, and I changed the measurement after seeing the failure. That is
what a condition fixed beforehand is meant to rule out, so here is everything needed to judge it.

* On the new plates the marked patch is partly consumed where two plates close: 7 to 44 % of it
  in those six runs. The first measure compared the centre of what was left with the place of
  the whole patch's centre. A patch that loses one side has its centre shifted, though no crust
  moved. On the old plates the patch stayed whole, and the measure read 0.13 cell on the preview
  mesh and 0.04 on the standard mesh. [MEASURED]
* The new measure follows the crust that is left. Every point carries its home, the place its
  crust stood at the start. The place a plate's motion gives a piece of crust is its home turned
  by that motion. The miss is the distance between the centre of the marked crust that is left
  and the centre of the places its plate's motion gives that same crust. Where the patch stays
  whole (six other seeds, below), the old measure reads 0.1 to 0.4 cell and the new one less
  than 0.01. [MEASURED]
* The new measure showed a real fault of the trial that the old one had hidden: fresh points were
  filled with weights of one over the distance, which shift every value by up to a fifth of a
  cell at each resampling. With resampling every 10 rounds the crust that was left lay 0.88 cell
  from its place on the preview mesh. [MEASURED] The paper fills a fresh point from the triangle
  of old points around it, with weights that give back any evenly changing value exactly. The
  trial now does the same, and still runs the old weights beside it.

**Results on the default world**, fresh points filled as the paper does. [MEASURED]

| Mesh | Resampled every | Patch left | A: miss, limit 1 cell | Old measure of A | B: area change, limit 2 % | C: switching cells, limit 1 % |
|---|---|---|---|---|---|---|
| Preview | 20 rounds | 65 % | 0.02 cell | 1.74 | 0.4 % | 0.08 % |
| Preview | 10 rounds | 63 % | 0.01 cell | 1.91 | **7.3 %: fails** | 0.08 % |
| Preview | 60 rounds | 64 % | 0.01 cell | 1.86 | 0.2 % | 0.09 % |
| Standard | 20 rounds | 78 % | 0.00 cell | 1.28 | 0.0 % | 0.13 % |
| Standard | 10 rounds | 87 % | 0.01 cell | 0.90 | 0.6 % | 0.14 % |
| Standard | 60 rounds | 77 % | 0.00 cell | 1.34 | −0.1 % | 0.10 % |

With the first version's weights the miss is 0.32, 0.88 and 0.04 cell on the preview mesh and
0.07, 0.31 and 0.02 cell on the standard mesh, in the same order.

**Ten other seeds**, resampled every 20 rounds (`python trials/crust_points_trial.py seeds`). [MEASURED]

| Mesh | A | B | C |
|---|---|---|---|
| Preview | 6 of 10 pass with a miss of at most 0.004 cell. In the other 4 the whole patch was consumed, so nothing is left to measure | 8 pass; **2 fail, with 2.1 % and 2.9 %** | 10 pass (0.1 to 0.3 %) |
| Standard | 6 of 10 pass with a miss of at most 0.002 cell; the same 4 patches were consumed | 10 pass (−0.6 to −0.1 %) | 10 pass (0.1 to 0.3 %) |

**How far single points stray.** Over all continental crust on the default world, resampled
every 20 rounds: the mean point stands 0.07 cell from its place on the preview mesh and 0.02 on
the standard mesh; 95 in 100 stand within 0.38 and 0.04 cell; the worst stands 2.5 and 2.3 cells
away. The strays sit at plate edges. [MEASURED]

**What the trial says, and what it leaves open.**

1. Crust carried on moving points keeps its place. That was the risk the design named, and it
   holds at both mesh sizes, provided fresh points are filled with weights that are exact for an
   evenly changing value. [MEASURED]
2. The area of continents is not kept within 2 % on the coarse preview mesh in every case.
   [MEASURED] The likely cause: where plates part, the drawing lets continental crust reach up
   to three quarters of a cell into the gap before new floor appears, and each resampling keeps
   it. [INFERRED from the rules of the trial; I did not isolate it] On the standard mesh every
   run passes.
3. The trial's rule lets continents overrun each other: 28 to 76 % of the continental crust is
   consumed in 250 My, and the chosen patch disappears in 4 seeds of 10. [MEASURED] The full
   plate model of step 3 thickens crust in a collision and slows the plates; nothing here tests
   that.

The gate of Question 16 was that the trial meets its conditions. On the default world and at
its own resampling interval it does, with the measure of A changed as described. Because I had
changed a measure after a failure, I left the decision to you. **You confirmed it on 2026-10-04:
the crust stays on moving points.** Three duties follow for step 3: fill fresh points as the paper
does, make new ocean floor at parting margins before drawing, and carry conditions A to C into the
tests of the real Tectonics at both mesh sizes.

### 3.3 Cold poles

The requirement added when the design was approved. Nothing in the engine places cold.

* Yearly sunlight at each pole is 41.5 % of the equator's at a tilt of 23.44°. [MEASURED: test]
* Default world: both poles are below freezing in the yearly mean and far colder than the equator,
  Albedo marks ice at both pole cells in every month, and the biome there is ice. [MEASURED:
  `test_both_poles_are_cold_and_carry_ice`; section 8 gives the temperatures]
* Ten other seeds all have cold poles: between −10 and −23 °C in the yearly mean. [MEASURED on the
  build as it stands]
* A planet tilted 60° is still built; the world store then names EnergyBalance as outside its
  range, and the pole gets more yearly sunlight than the equator, as the formula says.
  [MEASURED: test]

### 3.4 Pushes

`data/examples/frozen_region.yaml` on the default world: the order becomes Albedo, Insolation,
EnergyBalance, **push: cap**, Circulation, Moisture, Biomes, Hydrology, Soils. The centre of the
region is sea. The heat sink of −120 W/m² alone cools every month there; the cap then holds every
month at −15 °C, and the biome becomes ice. Between 900 and 1,500 km from the centre, outside the
region, the year is colder as well. The fields of the geological stage keep their values. The "why"
answer names the entry, its reason, "not physical", the heat sink and the value before the cap.
[MEASURED: test] The cap is −15 °C and not the design's −5 °C because ice lies on the sea only
below a yearly mean of −10 °C (section 7, item 5). The third push of the design's example, on
the day's temperature, waits for the weather stage of step 8.

`data/examples/place_label.yaml` names the forest inside a circle. Its circle lies where forest
grows in the default world (50° S, 105° E): every labelled cell is a forest cell, and no other field
changes. Moved to a place without forest, the entry labels nothing and the world store says so.
[MEASURED: test]

## 4. Step 2: water on land

The design's "done when" for step 2: the river and closed-basin tests pass. Section 4.2 holds them
against the build, and sections 4.3 to 4.6 go further than the design asked, on Earth's own data.

### 4.1 What was built

| Slot | Stage | Model | What it writes |
|---|---|---|---|
| Drainage | geological | Every cell hands its water to its lowest neighbour. The closed hollows are found as a depression hierarchy (Barnes, Callaghan and Wickert 2020): each hollow, its bottom, its pass, the hollow it spills into, and how hollows nest | `flow_receiver`, `depression_id`, `spill_elevation`, `slope`; `drainage_area` and `basin_id`, both as they are with every hollow full; the table `hollows` |
| Hydrology | climate | In the order the water takes: a snow store with degree-day melt (Hock 2003); the air's demand for water by the Priestley-Taylor rule in the form of Davis et al. 2017; soil water as Manabe's bucket; runoff summed down the flow paths; lakes that spread in closed hollows until their surface loses what arrives, or overflow at their pass (after Fill-Spill-Merge, Barnes, Callaghan and Wickert 2021) | `snow_water`, `snow_cover`, `potential_evapotranspiration`, `soil_moisture`, `runoff`, `runoff_annual`, `river_discharge`, `lake_fraction`, `lake_level`, the table `lakes`; and `evapotranspiration`, its member of the group `moisture_source`, which Moisture reads in the next round |
| Soils | climate | A stand-in until step 7: every soil holds 150 mm, Manabe's bucket | `soil_water_capacity` |

Seventeen fields and two tables are new; the world now holds 52 fields. Nothing in them is placed. A
dry basin, a closed lake and a lake with an outlet all follow from the water arriving against what the
flooded ground loses to the air. The land's evaporation closes the loop the design drew: rain inland
is now fed by land upwind, and the climate rounds repeat until that settles.

`python -m worldengine explain` answers for all of them. A river's answer names the cell that gives it
the most water and goes on from there to that cell's rain; a lake's answer gives its books.

### 4.2 The design's conditions (Layer 9)

| Condition in the design | Result |
|---|---|
| A cone drains to its foot | Pass |
| Every land cell reaches the sea or a closed hollow | Pass on ground built for the purpose and on the default world |
| The drained areas add up to the land area | Pass, to 1 part in a billion |
| One basin under even rain: the flow at its mouth is (rain − evaporation) × area | Pass |
| Water in = water out for every basin | Pass on rough ground with lakes and snow: what falls on each basin goes back to the air or leaves at its mouth |
| Earth: the Amazon reaches the Atlantic and the Nile the Mediterranean | Pass: 203 and 270 km from their mouths, where 600 km was allowed. The Amazon passes however the ties of the relief are settled. The Nile passes in 19 of 20 random settlements, and by a way that is not its valley (section 4.4) |
| Earth: central Asia and the Great Basin are closed | Pass |
| Earth: the Amazon carries the most water | Pass: the largest flow into the sea is 161,911 m³/s, 142 km from the Amazon's mouth. The Amazon carries 210,000 m³/s [DOCUMENTED: Dai and Trenberth, Table 2] |
| Earth: the Caspian stays closed | **Not decided by the relief data.** As the engine settles ties the lake overflows, by 0.47 km³ of the 669 that reach it in a year. In 20 random settlements of the ties it stays closed in 5. It stands at the brim of its hollow, at about three times the real sea's size (section 4.4) |

All [MEASURED]: `tests/test_water.py` and `tests/test_water_rules.py` for the first five,
`tests/test_earth.py` for the rest.

### 4.3 Earth's data, and the Earth tests

Step 1 could not be tested against Earth: the build environment reaches package registries and GitHub
only. One public repository on GitHub carries four files that serve: NCAR's GeoCAT-datafiles, example
data for a plotting library.

| File | What it holds | Used for |
|---|---|---|
| `ETOPO5.DAT` | Height of land and sea floor, every 5 minutes of arc | Earth's relief on the mesh |
| `V22_GPCP.1979-2010.nc` | GPCP 2.2: precipitation, each month of 1979 to 2010, every 2.5° | Rain handed to Hydrology and Biomes; the yardstick for the twin's rain |
| `absolute.nc` | The Climatic Research Unit's mean surface temperature of each month, 1961 to 1990, every 5° | Warmth handed to Hydrology and Biomes; the yardstick for the twin's temperature |
| `landsea.nc` | A land-sea mask, every 1° | Rain over land by latitude |

`python tools/fetch_reference_data.py` fetches them from one pinned commit and checks each against its
size and SHA-256 (`tools/reference_data.yaml`). They are not kept in the repository. The repository
carries an Apache-2.0 licence file; the data sets were made by others, and the precipitation file
asks that GPCP be cited in anything published from it. [DOCUMENTED: the repository and the files'
own attributes] The readers live in `src/earth_reference/`, a package beside the engine that the
engine never imports. What is still missing: winds and pressure (ERA5), measured evaporation, a map
of climate classes, a map of river basins, relief with its rivers cut in, ocean-floor ages and crust
thickness.

The grids are coarse beside the mesh. Rain every 2.5° and temperature every 5° are read off between
grid points at each cell's centre; mountains narrower than that are not in them.

**How the tests are built.** A test hands one process inputs measured on Earth and asks for a pattern
an atlas shows: given the truth as its input, does the process return the truth? Each condition says
when it was set. "Set before the run" was written before the process had seen Earth's data; such a
condition is not loosened when the engine fails it. It stays, marked as an expected failure, with the
number measured. "Found, then kept" is something a first run showed; it guards a result and proves
less. The second review of step 2 found conditions of mine that had been written after the run and
could not fail; they are now labelled for what they are, and the known misses are expected failures,
so that their count is the count of known misses.

**What the river tests can show.** Less than I first wrote. The third check found that the relief
data decide most of what the rivers do, before any process runs (section 4.4). The tests now settle
the exact ties of the relief twenty times at random beside the engine's own way, and a reason names
a cause only where a tool measures it.

| Process | Fed with | Condition | When set | Result |
|---|---|---|---|---|
| SeaLevel | Earth's relief, the planet file's water | The sea rests within 60 m of Earth's level and covers 69 to 73 % of the planet, as one ocean | Before | Pass: −5 m, 70.3 % |
| SeaLevel | the same | The Black Sea, the Red Sea and the Baltic are part of the ocean | Stated as misses | **3 fail.** The relief data cut the Black Sea off themselves: on their own grid the Bosporus stands 2 m above the sea. The Red Sea and the Baltic are ocean in the data; their straits are narrower than a cell and closed on the mesh |
| Drainage | Earth's relief (valley floors: section 4.5) | The design's four conditions (section 4.2) | Before | Three pass; the Caspian is not decided |
| Drainage | the same | Each of 24 great rivers leaves the land within 300 km of its real mouth | Before | As the engine settles ties **16 pass, 8 fail**; in 20 random settlements 15 to 17 pass. 14 rivers pass in every settlement, 7 in none, and 3 are decided by the ties: section 4.4 |
| Hydrology | Earth's relief, rain and warmth | Of the rain on land, 0.50 to 0.75 goes back to the air; 28 to 52 thousand km³ a year reach the sea | Before | Pass, at the dry end: 0.735 and 31.7, however the ties are settled. Earth: 0.65 and 40 [DOCUMENTED: Trenberth, Fasullo and Mackaro 2011] |
| Hydrology | the same | The largest flow into the sea is the Amazon's, within a factor of two | Before | Pass |
| Hydrology | the same | Each of 21 great rivers carries, at its last gauging station, the flow measured there within a factor of two | Before | As the engine settles ties **7 pass, 14 fail**; in 20 random settlements 6 or 7 pass. 6 rivers pass in every settlement, 13 in none, and 2 are decided by the ties: section 4.4 |
| Hydrology | the same | Like for like, the land of the great basins sheds within 15 % of the depth measured | Stated as a miss, after the third check | **Fails: 0.68** of the measured depth, over the 14 basins whose size on the mesh is like the real one's |
| Hydrology | the same | The Caspian stays closed | Before | **Not decided by the data** (section 4.2) |
| Hydrology | the same | Lakes cover under 4 % of the land | Stated as a miss | **Fails: 6.0 %**. Earth: 3.7 % of its ice-free land, lakes of all sizes [DOCUMENTED at second hand: Verpoorter et al. 2014] |
| Hydrology | the same | The basin of the Congo holds no great lake | Stated as a miss | **Fails**: a lake of 880,226 km². The relief data close the river's valley |
| Hydrology | the same | The Black Sea, the Baltic and the Great Lakes come back as lakes near their real size; open water at the Caspian's place loses 0.8 to 1.1 m a year | Found, then kept | Pass: 472,814, 294,490 and 298,119 km²; 1.00 m at the place tested, 0.94 m over the whole lake |
| Biomes | Earth's rain and warmth | Each of the five main climate groups takes a share of the land within 6 points of Peel, Finlayson and McMahon 2007 | Before | Pass: tropical 21.1 (19.0), dry 24.7 (30.2), temperate 13.3 (13.4), cold 26.2 (24.6), polar 14.7 (12.8) |

All [MEASURED: `tests/test_earth.py`, on the standard mesh]. The design asks Biomes for agreement with
the published map cell by cell; five shares are a weaker test, and the map is not at hand.

Earth itself meets the design's dry-belt condition: its driest land bands lie at 27.5° north (566 mm)
and 32.5° south (629 mm). [MEASURED from the rain data and the land mask]

### 4.4 The great rivers, taken apart

Three tools print every number in this section: `python tools/earth_relief.py`,
`python tools/earth_rivers.py --settlements 20` and `python tools/earth_rivers.py --trace RIVER`.
[MEASURED] `tests/test_earth.py` keeps the numbers true.

**What I had wrong.** My first account of this section gave three causes for the rivers that go
astray, and the third check took two of them apart with measurements of its own. I have repeated
those measurements with tools of mine, and they hold.

* I laid six closed valleys to the mesh: "narrows narrower than a cell are closed at 60 km". Five of
  the six are closed in the relief data themselves, on their grid of 9 km.
* I wrote that on plains "the rule of the lowest neighbour takes a river across ground that is a
  little lower". The ground was not lower. It was exactly as high, and the cell numbers chose.
* I wrote that the land sheds too much in cold, wet plains, and that this is why the lake at the
  Caspian's place is too large. The comparison set unlike areas side by side. Like for like the land
  sheds too little in ten basins of fourteen, and 0.68 of the measured depth over all of them.

What follows replaces that account.

**1. The relief data hold closed hollows of their own.** On ETOPO5's own grid, with water raised from
the ocean over everything else, 13.3 % of all that is not ocean lies under water when every hollow
is full. On the mesh, with the valley rule of section 4.5, it is 10.2 %: the mesh does not add
hollows to Earth's relief on the whole. Of the mesh's twelve lakes larger than 100,000 km², eleven
lie in hollows that the data hold as well. Some of those are real: the Caspian, the Black Sea, and
the Great Lakes, whose beds the data give. Others are not: the basins of the Congo, the Amazon and
the Danube, the West Siberian plain and the lowlands of the Amur and the Lena. The six narrows:

| Narrows | In the data: the river above stands at | its valley rises to | joined to the ocean, by any way, at | On the mesh: the valley rises to | the lake above stands at |
|---|---|---|---|---|---|
| Congo, Bolobo to Kinshasa | 274 m | 610 m | 457 m | 518 m | 457 m |
| Danube, the Iron Gate | 98 m | 317 m | 317 m | 208 m | 177 m |
| Lena, Zhigansk to the delta | 91 m | 152 m | 152 m | 137 m | 122 m |
| Amur, below Komsomolsk | 76 m | 213 m | 122 m | 137 m | 107 m |
| Yangtze, the Three Gorges | 404 m | 945 m | 823 m | 762 m | 381 m |
| St Lawrence, below Quebec | open to the sea | | | 204 m | 102 m |

Only the St Lawrence is closed by the mesh. The other five are closed before the mesh sees them,
and a mesh of any spacing would inherit them from these data. Relief made for hydrology has its
rivers cut in beforehand. [UNVERIFIED: recalled; I know of such data sets but opened none] Nothing of
the kind is among the four files.

**2. The heights tie, and ties decide where rivers go.** ETOPO5 is in whole metres, and 48 % of its
land lies in steps of 100 feet. On the mesh 17,454 of 48,733 land cells have a land neighbour at
exactly their own height; 91 m is the height of 1,543 cells and 61 m of 1,257. Where two ways are
exactly equal the rule of the lowest neighbour cannot choose, and the data cannot say which is
right. Of the 42,980 land cells that have a lower neighbour, 9,869 have several equally low, and
5,063 more lie on level ground.

Until the third check such a tie went to the lower bed and then to the lower cell number. After the
bed it now goes to the wider way, the longer boundary between two cells (section 7, item 20). That
is no truer than the cell number. It does not depend on how the cells are numbered, and that is all
it claims. The measure of how much ties matter: with the wider way left out again, the water of
15.5 % of the land reaches the sea in another cell.

So the tests settle the ties twenty times at random, and a result counts as a finding only if it is
the same every time:

| Outcome | As the engine settles ties | In 20 random settlements |
|---|---|---|
| River mouths within 300 km, of 24 | 16 | 15 to 17. Fourteen rivers pass every time and seven never |
| The Nile's mouth | 270 km: passes | passes in 19 |
| The Yangtze's mouth | 60 km: passes | passes in 6 |
| The Huang He's mouth | 1,261 km: fails | passes in 2 |
| Gauges within a factor of two, of 21 | 7 | 6 or 7. Six rivers pass every time and thirteen never |
| The Yenisei at its gauge (577 km³ measured) | 77 km³: fails | 105 to 731 km³; passes in 6 |
| The Ob at its gauge (397 km³ measured) | 604 km³: passes | 140 to 604 km³; passes in 7 |
| The lake at the Caspian's place | overflows, by 0.47 km³ a year | closed in 5; overflows by up to 6.9 km³ |
| Rain on land that goes back to the air | 0.735 | 0.735 every time |
| Rivers reaching the sea | 31.7 thousand km³ | 31.7 every time |
| Land under lakes | 6.0 % | 6.0 % every time |

The Yangtze's pass and the Ob's pass are no more findings than the Huang He's miss. The totals of
the land do not depend on ties at all.

**3. The valley rule lowers divides.** Section 4.5 hands Drainage the floor of each cell's valleys.
A cell that holds a shore and a range is then handed in at the height of the shore: 2,078 of the
4,646 coastal land cells come in at 1 m or lower, and 69 of those have a mean height above 300 m.
The Danube shows what follows. The plain above the Iron Gate fills to 177 m and overflows to the
Adriatic through a coastal cell whose mean height is 544 m and which came in at 0 m.

**Where the rivers leave the land.** As the engine settles ties, eight of 24 great rivers leave the
land more than 300 km from their real mouths.

| River | Distance | In 20 random settlements | What was measured |
|---|---|---|---|
| Congo | 603 km | 668 to 738 km | The data close its valley (table above). The basin fills as a lake of 880,226 km² to 457 m and overflows westward, to the sea at 1.5° south |
| Danube | 1,212 km | 1,171 to 1,212 km | The data close the Iron Gate. The plain above it overflows to the Adriatic, through the lowered divide described above |
| Amur | 1,274 km | up to 1,290 km | The data close the lower river, and join the lowland above it to the ocean by a way south. On the mesh the water leaves south, to the Sea of Japan |
| St Lawrence | 1,090 km | the same | The mesh closes the estuary, which is narrower than a cell. The lake above it overflows south, by Lake Champlain and the Hudson |
| Ob | 633 km | the same | The river reaches the head of its estuary, 28 km from its real mouth, and runs on. The Gulf of Ob is ocean in the data, 3 to 13 m deep; the cells that hold it and its shores have mean heights of −7 to 8 m, and the mesh's sea stands at −5.3 m. On the mesh the gulf is a lake, and the river follows it to its seaward end |
| Yenisei | 350 km | the same | Near 66° north the river leaves its valley, runs west over ground that is level at 30 m, and joins the Ob in its estuary. Why it leaves its valley is not established |
| Huang He | 1,261 km | 118 to 1,261 km; passes in 2 | The ties decide. Its way crosses 47 cells under the water of full hollows and 4 of level ground |
| Volga | 1,865 km | the same | Not a fault of relief or mesh. The Volga ends in a closed sea, and this condition follows the water on as if every hollow were full. A river of a closed sea cannot meet it as I wrote it |

The condition asks where the water leaves the land, not by which way. Three rivers that pass do so
by ways that are not their valleys. The Nile leaves its valley near 22° north, crosses the hollows of
the Western Desert and reaches the coast 270 km west of the delta. The Yangtze passes south of the
Three Gorges, over a divide. The Lena leaves through a lake that overflows west of its delta. A pass
of this condition says less than it seems to.

**What the rivers carry.** The engine's flow at a gauge is the land whose water reaches it, times
what that land sheds, less what lakes on the way lose. Each of the three is worked out by itself,
and the books of all 21 gauges close to within 0.00003 km³ a year. Areas are in thousand km², flows
in km³ a year, depths in mm a year. Rivers in bold miss by more than a factor of two.

| River | Flow measured | Flow, engine | Within a factor of two in, of 20 | Basin on Earth | Land that reaches the gauge on the mesh | Shed, measured | Shed, engine | Lakes on the way lose |
|---|---|---|---|---|---|---|---|---|
| Amazon | 5,330 | 4,515 | 20 | 4,619 | 5,921 | 1,154 | 814 | 306 |
| Mississippi | 536 | 482 | 20 | 2,896 | 2,396 | 185 | 211 | 25 |
| Paraná | 476 | 480 | 20 | 2,346 | 2,987 | 203 | 168 | 23 |
| Ob | 397 | 604 | 7 | 2,430 | 2,865 | 163 | 244 | 96 |
| Ganges | 382 | 273 | 20 | 952 | 507 | 401 | 578 | 20 |
| Columbia | 172 | 117 | 20 | 614 | 484 | 280 | 303 | 29 |
| Rhine | 73 | 84 | 20 | 180 | 187 | 406 | 477 | 5 |
| **Congo** | 1,271 | 8 | 0 | 3,475 | 50 | 366 | 250 | 4 |
| **Orinoco** | 984 | 355 | 0 | 836 | 563 | 1,177 | 704 | 41 |
| **Yangtze** | 910 | 127 | 0 | 1,705 | 839 | 534 | 187 | 29 |
| **Brahmaputra** | 613 | 273 | 0 | 555 | 507 | 1,105 | 578 | 20 |
| **Yenisei** | 577 | 77 | 6 | 2,440 | 201 | 236 | 395 | 2 |
| **Lena** | 526 | 11 | 0 | 2,430 | 278 | 216 | 42 | 1 |
| **Amur** | 312 | 26 | 0 | 1,730 | 100 | 180 | 317 | 6 |
| **Mekong** | 292 | 143 | 0 | 545 | 275 | 536 | 559 | 11 |
| **Mackenzie** | 288 | 115 | 0 | 1,660 | 1,740 | 173 | 88 | 37 |
| **St Lawrence** | 226 | 470 | 0 | 774 | 1,244 | 292 | 443 | 81 |
| **Danube** | 202 | 24 | 0 | 807 | 145 | 250 | 181 | 2 |
| **Zambezi** | 105 | 11 | 0 | 940 | 233 | 112 | 71 | 6 |
| **Indus** | 89 | 0 | 0 | 975 | none | 91 | | |
| **Niger** | 33 | 5 | 0 | 1,516 | 116 | 22 | 78 | 4 |

The measured flows and basins are [DOCUMENTED: Dai and Trenberth, Table 2, the columns of the station.
A page reader gave me the rows; the areas were read out twice, and the two readings agree]. The rule
takes the largest flow within 150 km of the station. For the Ganges that is the mesh's Brahmaputra,
whose station lies 147 km away. No cell within 150 km of the Indus's station carries any water.

The fourteen misses, by what was measured:

* **The data close the valley** (five): the Congo, the Lena, the Amur, the Danube and the Yangtze.
  The first four leave by another way; the Yangtze's Sichuan basin keeps its water as a closed lake.
* **The ties decide** (one): the Yenisei. The Mekong may belong here: 7 of the 20 land cells on its
  way lie on level ground, it carries 31 to 143 km³ over the random settlements, and it never passes.
  Its cause is not established.
* **Closed lakes upstream keep the water** (three): the Niger, the Zambezi and the Indus. With every
  hollow full their basins are of the right order or larger, and the climate the engine gives them
  never fills the hollows. The land sheds too little there (below), so these are misses of the
  water as much as of the relief.
* **The land sheds too little** (three): the Orinoco, the Brahmaputra and the Mackenzie, whose
  basins are nearly right.
* **Too much** (one): the St Lawrence, with half as much land again as on Earth and more shed from
  each part of it.

**What the land sheds, like for like.** The table above mixes two things: where the mesh runs the
rivers, and what the land sheds. To see the second alone, take for each gauge the mesh's own river
there, the cell within 150 km whose basin with every hollow full is nearest the real one in size,
and keep the basins within a factor of 1.5 of the real area. Fourteen are alike as the engine
settles ties. "Alike" here means near the gauge and alike in size. Whether the mesh's basin covers
the same land as the real one I could not check, because no map of the real basins is among the
data at hand: a basin of the right size may still take in a neighbour's land and leave out some of
its own. [UNVERIFIED: that the fourteen cover the land of their real basins] The Brahmaputra, alike
in only 11 of 20 settlements, and the Ob, in 7, show how loosely the mesh holds some of them.

| River | Basin on Earth | On the mesh | Shed, measured | Shed, engine | Engine over measured | Alike in, of 20 |
|---|---|---|---|---|---|---|
| Amazon | 4,619 | 5,154 | 1,154 | 828 | 0.72 | 20 |
| Orinoco | 836 | 563 | 1,177 | 704 | 0.60 | 19 |
| Yangtze | 1,705 | 1,567 | 534 | 115 | 0.21 | 20 |
| Brahmaputra | 555 | 735 | 1,105 | 257 | 0.23 | 11 |
| Mississippi | 2,896 | 2,431 | 185 | 208 | 1.13 | 20 |
| Paraná | 2,346 | 3,134 | 203 | 158 | 0.78 | 20 |
| Ob | 2,430 | 3,176 | 163 | 207 | 1.27 | 7 |
| Ganges | 952 | 967 | 401 | 231 | 0.57 | 20 |
| St Lawrence | 774 | 1,012 | 292 | 423 | 1.45 | 20 |
| Mackenzie | 1,660 | 1,690 | 173 | 88 | 0.51 | 20 |
| Columbia | 614 | 515 | 280 | 91 | 0.32 | 20 |
| Niger | 1,516 | 1,135 | 22 | 8 | 0.37 | 20 |
| Indus | 975 | 1,301 | 91 | 12 | 0.13 | 20 |
| Rhine | 180 | 178 | 406 | 479 | 1.18 | 20 |

All fourteen together, the engine's land sheds **0.68** of the depth measured, and 0.65 to 0.72 over
the random settlements. Ten basins shed too little and four too much; nine are within a factor of
two. The engine's figure is taken before any lake loses water and the measured one after, which
favours the engine. This is the same error that puts 31.7 thousand km³ a year into the sea where
Earth's rivers carry 40.

The four basins that shed too much (the St Lawrence, the Ob, the Rhine and the Mississippi) are
all snowy lands of the northern mid-latitudes, and so is a fifth that is not among the 21 because it
ends in a closed sea: the Volga sheds 1.8 times the published depth, like for like. For the Volga
the cause is measured: four fifths of the excess come with the rain data and a fifth is the model's
(below, at the Caspian). For the other four I have no published precipitation to hold the rain data
against. [MEASURED for the ratios; UNVERIFIED that the rain data are high there as well]

Its measured part: the demand for water is too high over land. With one share of sunshine for every
cell and month, the radiation formulas leave the land 85.7 W/m² to warm the air and evaporate water,
where 65.5 are measured: 1.31 times too much (section 7, item 14). As a diagnosis I ran the same
tests with the demand cut to 0.76 of its value, which is that ratio, and to 0.60:

| | Demand as it is | × 0.76 | × 0.60 | Earth |
|---|---|---|---|---|
| Like for like, engine over measured | 0.68 | 0.97 | 1.23 | 1 |
| … basin by basin, lowest and highest | 0.13 and 1.45 | 0.32 and 1.74 | 0.42 and 2.28 | |
| Rain on land that goes back to the air | 0.735 | 0.632 | 0.542 | 0.65 |
| Rivers reaching the sea, thousand km³ | 31.7 | 44.1 | 54.9 | 40 |
| Gauges within a factor of two, of 21 | 7 | 11 | 10 | |

[MEASURED: `tools/earth_rivers.py --demand-times`] That is no setting of the engine and no fit. It
shows that the error of the mean is the measured error of the radiation, and that a spread remains
which no one factor removes. The spread is largest where the rain comes in the warm season and
nearly matches the demand: the Yangtze 0.21, the Brahmaputra 0.23. Two things could do that: the
engine's rainy season is as sunny as its dry one, and a bucket fed with a month's mean rain sheds
water only when the month's rain exceeds the month's demand, so it knows no storm. [INFERRED: both. I
have no measured sunshine and no daily rain to test either with] Other things I did not rule out:
rain on a grid of 2.5°, which cannot hold the rain of a mountain front; temperatures on a grid of
5°, read without regard to a cell's height; frozen ground.

**The lake at the Caspian's place.** Its size does not depend on the ties: 1.09 to 1.11 million km²
at 60 to 61 m, where the real sea covers 371,000 to 436,000 km² in the sources I could open and
stands 28 m below the ocean. [DOCUMENTED at second hand: Wikipedia gives 371,000 km² without the
Garabogazköl lagoon and −28 m; a paper on the sea's level gives "about 436000 km2". The two
disagree and I could not settle it; either way the lake is two and a half to three times too large]
Its books as the engine settles ties:

* Rivers and shores bring it 588 km³ a year. About 300 reach the real sea. [DOCUMENTED at second
  hand, the same paper: the Volga brings 237 km³ a year, about 80 % of the inflow]
* The land that drains to it covers 4.06 million km², the lake included; the real sea drains about 3
  million. [the same paper] The mesh's catchment holds the Don at Voronezh, which on Earth runs to the
  Black Sea.
* Each square metre of the lake loses 936 mm a year and gets 408 mm of rain.

Why twice the water arrives is established in part. The Volga gives most of it, and four fifths of
the Volga's excess come with the rain data:

| Over the land that drains through the Volga at Volgograd | Published for the real basin | On the mesh, under the rain data | On the mesh, handed the published precipitation |
|---|---|---|---|
| Area | 1.36 million km² | 1.25 million km² | the same land |
| Rain and snow | 585 mm a year | 744 mm | 585 mm |
| Shed to the river | 193 mm (262 km³ a year) | 342 mm | 224 mm |
| Back to the air | 392 mm | 402 mm | 361 mm |

[MEASURED for the mesh: the like-for-like measure at the place of Volgograd, in part 2 of
`tools/earth_rivers.py`. The third reviewer found the first of the two columns at Samara, with a
script of the reviewer's own: 775, 367 and 408 mm over 1.0 million km². DOCUMENTED for the basin:
Kalugin 2022 gives the area, 585 mm and 262 km³; the two depths in mm are my arithmetic] The ties do
not decide it: in 20 random settlements the rain data hold 717 to 750 mm over that land.

The last column is a diagnosis. The rain data over that land are scaled by one factor in every
month, so that the year's total is the published one. The land then sheds 1.17 times the published
depth (224 to 225 mm in eight ways of settling the ties), where under the rain data it sheds 1.77
times. So about four fifths of the river's excess
come with the rain data, which hold a quarter more over this land than the paper gives for the
basin, and a fifth is the model's: on this cold plain the engine sheds a sixth too much and gives
the air 8 % too little. [MEASURED] The third reviewer and I both first read the 402 mm beside the
392 as agreement, "the engine's evaporation matches". It is two errors that nearly cancel: more
rain than published, and too small a share of it given back. Why the model sheds too much here,
where over the fourteen basins together it sheds too little, I did not establish. [INFERRED: snow
gives the air nothing while it lies, and it melts in a pulse that a soil of 150 mm cannot hold]
Which of the two precipitations is nearer the truth I cannot say. [UNVERIFIED: I recall that GPCP
raises its gauge readings for the snow that gauges miss, which would put it above plain station
means; the page on GPCP that I opened does not say so]

The larger catchment adds to the lake's excess. My earlier sentence, that the snowy plains shed
too much, compared the runoff of a box with the published runoff of the basin and missed that the
rain differed. A sixth too much, on one basin, is what is left of it.

**The land of the whole Earth, by this build:** 119.8 thousand km³ of rain a year (GPCP on the
mesh's land), of which 0.706 would go back to the air if no cell were flooded; lakes with an outlet
lose another 3.0 thousand km³ and closed lakes keep 0.4; 0.735 goes back in all, and 31.7 thousand
km³ reach the sea. [MEASURED]

**What this leaves of the river tests.** The totals of the land and the like-for-like depths test
Hydrology, and they show one error of known size. The mouths and the gauges test the relief data,
their ties and the valley rule more than they test Drainage. Drainage itself is held to its rule on
ground built for the purpose, where the answer is known (section 4.2). The third reviewer's slow
methods found no wrong receiver, hollow or pass on 90 rough grounds; that was before the ties were
changed, and the tests of ties were written since (`tests/test_water_rules.py`). A fair test of
rivers on Earth needs relief with the rivers cut in, which is not among the data at hand.

### 4.5 The valley share

A river runs along the floor of its valley, not at the mean height of the 60 km around it. The design
asked for "relief converted so that valley floors survive". The Earth tests hand Drainage, for each
land cell, the height below which a tenth of the cell's land points lie. The rule and the tenth are
mine. The tenth was chosen when the tests were first written and has not been tuned since. The rule
keeps valley floors and loses the ridges between them (section 4.4, point 3). The second review
asked what the share decides. [MEASURED: `python tools/earth_rivers.py --valley-share x --settlements 20`]

| Share of a cell's land points below the height used | 0.02 | 0.05 | **0.1** | 0.2 | 0.3 | 0.5 |
|---|---|---|---|---|---|---|
| River mouths within 300 km, of 24, as the engine settles ties | 17 | 16 | **16** | 16 | 16 | 15 |
| … in 20 random settlements | 14 to 18 | 14 to 16 | **15 to 17** | 14 to 16 | 14 to 17 | 14 to 17 |
| Gauges within a factor of two, of 21, as the engine settles ties | 8 | 9 | **7** | 7 | 6 | 7 |
| … in 20 random settlements | 6 to 8 | 6 to 9 | **6 or 7** | 7 to 9 | 6 or 7 | 6 to 8 |
| The lake at the Caspian's place: closed in, of 20 | 20 | 20 | **5** | 20 | 20 | 20 |
| Its level | 30 m | 30 m | **61 m** | 61 m | 76 m | 106 m |
| Its area, million km² | 0.87 to 1.03 | 0.89 to 1.06 | **1.09 to 1.11** | 1.11 to 1.14 | 1.09 to 1.12 | 2.09 to 2.11 |
| Like for like, engine over measured | 0.68 to 0.76 | 0.68 to 0.74 | **0.65 to 0.72** | 0.66 to 0.71 | 0.65 to 0.70 | 0.69 to 0.74 |
| Land under lakes | 5.5 % | 5.7 % | **6.0 %** | 6.2 % | 6.3 % | 6.8 % |
| Rain on land that goes back to the air | 0.732 | 0.733 | **0.735** | 0.736 | 0.737 | 0.741 |

The counts hardly move, and at every share the ties move them as much as the share does. Which
rivers pass changes with both. The one design condition that is not met, the closed Caspian, is met
in every settlement at five of the six shares. At the tenth the lake stands exactly at the brim of
its hollow, at 61 m, and the ties decide whether a little runs over. The data give that brim as
91 m; the valley rule lowered it by one step of 100 feet. A different, equally defensible share
would have let me report that every condition of the design passes. The reading that every column
gives is the honest one: the lake stands at about three times the real sea's size, and whether it
overflows is not a finding.

### 4.6 The Earth twin

`python tools/earth_twin.py` builds the whole engine on Earth's relief: only the heights are Earth's.
The sea, the climate, the water on land and the biomes are the engine's own. The Isostasy slot is
filled by a process that reads the mean height of ETOPO5 over each cell, and the Tectonics slot is
left out: the twin has no plates and no crust, and says so when asked why its ground stands where it
does. A twin is not a test. It shows where the engine's climate departs from the one planet whose
climate is known, on relief the engine did not make.

| | Twin, standard mesh | Twin, preview mesh | Earth |
|---|---|---|---|
| Sea level against Earth's | −5 m | +2 m | 0 |
| Share of the planet under sea | 70.3 % | 70.9 % | 70.8 % |
| Mean temperature of the year | 13.3 °C | 13.4 °C | 14.0 °C |
| … over land | 4.0 °C | 4.0 °C | 8.8 °C |
| … over sea | 17.2 °C | 17.3 °C | 16.1 °C |
| … from 60° to 90° south | −11.1 °C | −10.9 °C | −18.0 °C |
| … from 30° to 60° north | 1.8 °C | 2.0 °C | 9.3 °C |
| … from 60° to 90° north | −15.5 °C | −15.3 °C | −9.8 °C |
| July less January, land from 40° to 60° north | 13.6 K | 13.4 K | 30.9 K |
| Rain of the year | 1,086 mm | 1,094 mm | 977 mm |
| … over land | 672 mm | 672 mm | 790 mm |
| … over sea | 1,260 mm | 1,268 mm | 1,056 mm |
| … land from 15° south to 15° north | 1,644 mm | 1,582 mm | 1,640 mm |
| … land from 15° to 40° north | 521 mm | 547 mm | 586 mm |
| … land from 40° to 60° north | 420 mm | 440 mm | 657 mm |
| … land from 60° to 90° north | 176 mm | 181 mm | 496 mm |
| Climate groups, share of land: tropical / dry / temperate / cold / polar | 16 / 19 / 17 / 2 / 46 % | 17 / 17 / 19 / 2 / 46 % | 19 / 30 / 13 / 25 / 13 % |
| Driest land band of the north, below 60° | 58°, 265 mm | 58°, 273 mm | 29°, 542 mm |
| Driest land band of the south, below 60° | 29°, 533 mm | 29°, 577 mm | 29°, 601 mm |
| Rain on land that goes back to the air | 67 % | 68 % | 65 % |
| Rivers reaching the sea | 33.8 thousand km³ | 31.6 thousand km³ | 40 thousand km³ |
| Largest river | 164,400 m³/s, at the Amazon's mouth | 148,900 m³/s, at the Amazon's mouth | 210,000 m³/s, the Amazon |
| Land under lakes | 8.5 % | 5.5 % | 3.7 % of the ice-free land |
| Land under snow in every month | 35 % | 35 % | about 10 % under ice |
| Yearly temperature, cell by cell: root mean square of the difference | 6.2 K | 6.1 K | |
| Yearly rain, cell by cell: correlation of the logarithms | 0.51 | 0.51 | |

The twin's columns are [MEASURED: `tools/earth_twin.py`; 15 climate rounds on both meshes]. Earth's
temperatures and rain are [MEASURED from the data of section 4.3, read at the cells of the standard
mesh] and banded as the twin's are, so that the two are measured alike. That is why Earth's driest
bands stand here at 29° with 542 and 601 mm, and in sections 4.3 and 8 at 27.5° north with 566 mm
and 32.5° south with 629 mm: those are on the rain data's own grid of 2.5°, with the data's own
land mask. Read at the cells of the preview mesh, Earth's driest northern band is the one at 39°,
with 542 mm: two bands of the north are within a millimetre of each other. The climate groups are
from Peel, Finlayson and McMahon 2007, the water of the land from Trenberth, Fasullo and Mackaro
2011, the Amazon from Dai and Trenberth [DOCUMENTED]; the lakes from Verpoorter et al. 2014
[DOCUMENTED at second hand]; the land under ice from the National Snow and Ice Data Center
[DOCUMENTED in step 1].

Four of these are stated as tests, and all four are expected failures (`tests/test_earth.py`, on the
preview mesh): northern land is far warmer in July than in January; the cold climates with warm
summers take a fifth of the land; the driest land band of the north lies in the dry belt; the land
between 40° and 60° north gets the rain of Earth's. One cause runs through all four. The engine's
land is too cold and its summers too weak, so snow that should melt stays, the polar climate takes
the place of the cold one, cold air carries little vapour and white ground gives none back.
[INFERRED: the chain is my reading; the first link is measured in section 8]

What the twin gets right, on relief it did not make: the level and the extent of the sea, the mean
temperature of the planet to within 1 K, the rain of tropical land to within 4 %, the dry belt of
the south, and the Amazon as the largest river, at 0.7 to 0.8 of its flow. What it gets wrong beyond
the cold north: the sea gets a fifth too much rain and the land a seventh too little, the far south
is 7 K too warm, and more land lies under lakes than under Earth's measured climate on the same
relief (8.5 % for 6.0 %): a hollow under snow that never melts loses nothing to the air, and fills.
[MEASURED; the cause of the last INFERRED]

### 4.7 Run times

All [MEASURED] on the 2-core build environment, on an idle machine; the laptop is not timed.

| What | Cells | Whole run | Climate rounds | A later round | Most memory held | World store |
|---|---|---|---|---|---|---|
| Default world, preview profile | 10,242 | 29 s | 23 | 1.0 s | 0.4 GB | 21 MB |
| Default world, standard profile | 163,842 | 580 s | 24 | 20 s | 5.2 GB | 219 MB |
| Earth twin, preview | 10,242 | 23 s | 15 | 0.9 s | 0.6 GB | 20 MB |
| Earth twin, standard | 163,842 | 360 s | 15 | 18 s | 5.2 GB | 209 MB |
| Earth's rivers (`tools/earth_rivers.py`, standard mesh) | 163,842 | 14 s | | | 1.4 GB | |
| Earth's relief (`tools/earth_relief.py`) | 163,842 | 16 s | | | 1.4 GB | |
| The demand for water (`tools/earth_demand.py`) | 163,842 | 14 s | | | 1.2 GB | |
| The test suite | | 9 minutes | | | | |

In a later round of the standard build Moisture takes 16 s, Circulation 2.3 s, Hydrology 1.2 s,
EnergyBalance and Biomes 0.5 s each. The first round takes 73 s: EnergyBalance prepares its solver
(31 s) and Moisture starts from dry air. The pass that records the causes costs one more round. The
limit of the standard profile is 1,800 s.

**The machine's speed changes from day to day, by a factor of two.** The table is of 2026-10-05.
Two days of measurement before it gave, for the standard build, 492 to 531 s at the end of step 1
and 1,186 s at the first measurement of step 2; the preview build took 23 s, 48 s and now 29 s. On
the slow day the code of step 1 was run again and took 1.5 times as long as on the day it was
first measured. Like for like, step 2 costs seven more climate rounds (23 for 16 on the preview
mesh, 24 for 17 on the standard one), because the water that land gives back must settle with the
rain it feeds, and about 5 % more per round for Hydrology. The times in the table are good to that
factor of two and no better. The high_fidelity profile was not run. Its solvers would need about
four times the memory of the standard profile's, so whether it fits in 32 GB is open. [INFERRED]

The same seed gave the same world in two fresh interpreters with different hash seeds. [MEASURED:
test, preview mesh] The standard world was built twice, before and after the third check: every
field on land came out the same, and the numbers of section 8 with it. [MEASURED: the two reports
compared line by line; the code differed between the two builds in how exact ties are settled, so
this is not a test of repeatability]

### 4.8 What step 2 changed in the default world

Standard mesh, seed 20261004. [MEASURED: the left column is that of the step 1 notes]

| | End of step 1 | Now |
|---|---|---|
| Rain over land | 306 mm a year | 618 mm |
| Rain over the globe | 800 mm | 945 mm |
| Share of all rain that had been on land before | none | 0.17 |
| Land that gets under 250 mm a year | 63 % | 37 % |
| Climate rounds until the climate settles | 17 | 24 |
| Mean temperature | 11.4 °C | 11.4 °C |
| Land under snow in every month | 20 % | 20 % |
| Climate groups, share of land: tropical / dry / temperate / cold / polar | 8 / 54 / 5 / 3 / 30 % | 10 / 36 / 17 / 4 / 33 % |

The land was the driest part of step 1's world, and section 7 of the step 1 notes named the cause:
land gave nothing back. That is mended. The cold, white north is not: it is the same fault as in
step 1, and it now shows in the rain as well.

## 5. Rounds of checking, and what they changed

Each round was done by reviewers who had not seen the code being written, with scripts of their
own. Their reports are summarised here. Every finding marked high or medium has a test. The
second review of step 1 found three such tests that also passed on the faulty code; they were
rewritten, and from then on each new test was run against the code as it stood, to see it fail.

| Round | Found | Changed |
|---|---|---|
| Step 1, 1. Physics | 2 high, 2 medium, 5 low. Plate boundaries were judged along the line between two cell centres, so plates sliding past each other came out as ridges and collisions. Vapour mixed into the thin cold air over high ground: one cell got 72 m of rain a year, and 43 % of the land's rain fell on 4 % of the land | The direction of a boundary is added up along the boundary. Vapour crosses between columns only above the higher ground. Evaporation uses the surface wind. The climate classes follow the published rule where a climate is dry in summer and in winter |
| Step 1, 1. Engine | 1 high, 14 medium, 9 low. A push limited to rounds was applied in every round. Groups with members in two stages lost a member. True-or-false and missing values were left out of the test for a settled climate. A push could not set a cell that had no value. A long outline pushed cells on the far side of the planet | All fixed, 47 tests (`tests/test_engine_cases.py`) |
| Step 1, 2. Physics | 1 high, 1 medium, 4 low. The climate could run away to a frozen planet: 1 seed in 32, and the default planet with 2 % less sunlight. Rain piled up in the last cell before high ground and grew as the cells shrank | Snow needs snowfall (section 7, item 5). Air held back by high ground is partly lifted and partly turned aside (item 6). Ties in Tectonics are settled by what the cells are, not by their numbers |
| Step 1, 2. Engine | 19 groups of defects, and about 20 changes made to the engine on purpose that no test noticed | All fixed, 62 tests (`tests/test_engine_round2.py`). Afterwards 44 changes made on purpose were each noticed by the suite |
| Step 1, 3. Physics | No high. 1 medium: on a planet without sea the solver left water in the air, more on finer meshes. 3 low, and five numbers in comments that did not reproduce | A month that nothing feeds is given its exact answer, zero. Ties among any number of equally near cells. The comments carry the measured numbers |
| Step 1, 3. Engine | No high. 4 medium, one of them new: a notice silenced by a fix of round 2. 7 low | All fixed, 22 tests (`tests/test_engine_round3.py`) |
| My own re-measurement | The crust trial no longer passed as measured | Section 3.2 |
| Step 2, 1. Physics | The "why" answers contradicted their own numbers: in 52 % of river cells the "largest source upstream" was the cell itself; runoff was explained under a lake; sea cells were described as land. Where two passes out of a hollow tied, the lower-numbered cell won, not the lower ground. The mean snow of a month was wrong in the month the snow ran out. The bucket lost its footing where the air asks for next to nothing, and did not settle in deep soils. The demand's formula for heat radiated away gives 14 % too little over land. One constant had the exponent of its formula run into it (33.912 for 33.91) | Section 5.1 |
| Step 2, 2. Engine | Tests that could not fail, and conditions reworded after a failure (the dry belt; several Earth tests). 28 of 53 changes made on purpose went unnoticed, among them halving the melt of snow. The Earth twin said its relief "follows from the planet parameters and the mesh alone". Hydrology trusted the table of hollows unseen. The fingerprint of a world left out the settle tolerances. The data tools failed on Windows encodings and trusted files they had not checked. Two machines with different processors gave different last digits | Section 5.1 |
| Step 2, 3. Physics and numbers | No wrong number in Drainage, the snow year, the bucket or the lakes against slow methods of the reviewer's own. 3 high, 4 medium and 5 low in what I had concluded and claimed. Earth's relief is in whole metres, and ties settled by cell numbers decided several rivers. Five of six narrows "closed by the mesh" are closed in the relief data. "Too much runoff in cold plains" compared unlike land. A label marked DOCUMENTED misstated its paper. The check of the table of hollows let 5 of 36 breakages through. The books of a gauge could not fail to close. In the engine's own world the cell number chose the sea cell a river runs into | Section 5.2 |
| Step 2, 4. A check of those changes, and of the engine, the tests, the tools and these notes | ⟦FOURTH_FOUND⟧ | ⟦FOURTH_CHANGED⟧ |

Left as found, and listed in section 8: the rain of rising ground falls in one cell, the seasons on
land are too weak, and the demand for water knows no cloud.

### 5.1 What the two reviews of step 2 changed

* **Drainage.** Where neighbours or passes tie in height, the lower bed decides and then the cell
  number; before, the cell number alone. (The third check changed this again: section 5.2.) With a hollow full, flooded ground hands its water by the
  shortest way to the hollow's outlet cell, which hands it over the pass: a river now runs through
  a full lake without a break, and `basin_id` names the last land cell before the sea.
* **Snow.** The mean store of a month is exact where the snow runs out part-way. A new field,
  `snow_cover`, holds the month's mean of the ground covered day by day; Albedo and the demand for
  water read it. A deep store that melts in the first week of a month no longer whitens the whole
  month.
* **Soil water.** A month of the bucket is solved exactly, with no sub-steps. The repeating year is
  found by following years and jumping ahead; it agrees with a search by halving to 0.02 mm for soils
  from 150 to 5,000 mm deep. [MEASURED: tests]
* **Lakes.** A lake that overflows passes on, month by month, the share of its inflow that it does
  not lose over the year; the flow shown at its outlet cell is its outflow. The rule is mine
  (section 7, item 15). Hydrology checks the table of hollows against seven stated rules before it
  uses it, and refuses a table that breaks one.
* **"Why" answers.** A pattern can now say different things for land, lake and sea, name a cell
  with its place, print areas and volumes in km² and km³, and end a chain at a seed with a sentence
  that says so. `tools/why_scan.py` reads every answer for water on land and holds it against the
  numbers of its cell. None contradicts them: 174,114 answers on the default preview world (every
  cell), 121,108 on the standard one (every 23rd cell) and 174,114 on the preview twin. [MEASURED]
  The scan knows the faults the first review found; it proves nothing about faults of another kind.
* **The demand for water.** The constant is 33.91, as two published copies of the model's code have
  it. The formula's shortfall over land is measured and recorded (section 7, item 14); I did not fit
  it away.
* **Earth tests.** Rewritten as section 4.3 describes. A test of 21 great rivers at their gauges was
  written before it was run; 15 failed. What I then wrote about why did not survive the third check
  (section 5.2).
* **The twin** has no Tectonics slot and answers truthfully about its relief. Its relief file is made
  afresh from the checked ETOPO5 on every use; a file left in its place is replaced.
* **The engine.** The fingerprint of a world holds the settle tolerances. A view of a store keeps
  what it has read: a "why" answer from a store took 0.58 s and takes under a millisecond.
  [MEASURED] Every file is read and written as UTF-8.
* **The viewer.** Numbers that name things (a receiver cell, a basin) are shown whole. On a scale of
  ratios a cell that holds exactly zero gets a plain colour of its own, one for land and one for sea,
  so that a dry valley no longer looks like the sea.
* **Changes made on purpose.** 129 changes were made to the code of step 2 and its tools, one at a
  time, in a copy of the folder. The suite noticed 110. Of the 19 it did not notice, nine were
  checks of the table of hollows whose refusal another check gave as well; four were the order of
  settling ties by the bed; one was a branch that no case reaches; and five were single lines: an
  outlet cell outside its hollow, the runoff recorded under a closed lake, Hydrology's call of the
  check of the table, the line endings in the code's fingerprint, and a way through a valley that
  crossed the sea. Each of the 18 that can matter has a test now, and the branch is gone
  (section 5.2). [MEASURED]

### 5.2 What the third check of step 2 changed

The third check was done by one reviewer, with slow methods written for the purpose: a brute-force
search for every drainage result, a day-by-day snow store, the bucket stepped 80,000 times a month,
lakes poured with exact fractions. Against those the reviewer found no wrong number in Drainage, the
snow year, the bucket, the lakes or any field that Hydrology writes. What was wrong was what I had
concluded from the Earth tests, one label, and several checks that did less than they claimed. I
repeated each measurement with tools of my own before acting on it.

* **Ties.** A tie among equally low neighbours or equally high passes went to the lower bed and then
  to the lower cell number. It now goes to the lower bed, then to the wider way (the longer boundary
  between the two cells), and only then to the order of the cells (section 7, item 20). The routing
  library takes that order as an argument and never uses a cell's own number where it was handed
  one: a test renumbers the cells at random, lists every cell's neighbours in another order, and
  asks for the same receivers, hollows, passes and ways across lakes, cell for cell. In the default
  world on the preview mesh, 399 of 3,489 land cells with a lower neighbour have several equally
  low: these are coasts, where all the sea stands at one level. The bed settles 199, the wider way
  193 and the cell numbers 7. On the standard mesh it is 1,663 of 58,514: 780, 875 and 8.
  [MEASURED: `tools/world_report.py`] Before the change the sea cell that a river runs into
  depended on the cell numbers for the land of 11 % of the preview world and 8 % of the standard
  one; now for 0.2 % and 0.02 %. [MEASURED] Nothing on land changed: on the preview mesh 48 of the
  52 fields are the same bit for bit, and the four that differ are the receiver of 146 coastal
  cells, their slope, and the two fields that say which sea cell takes a river's water. [MEASURED:
  the preview world built before and after] On the standard mesh the report of the world is the
  same line for line, but for the last digits of the sum of the rivers. [MEASURED]
* **Earth's rivers.** Section 4.4 is rewritten. `earth_reference.Earth` can settle the ties of the
  relief at random, and the tests do so twenty times. Three tools are new: `tools/earth_relief.py`
  (what the relief data hold before any process runs), `tools/earth_demand.py` (the demand for water
  against measured radiation) and a trace of one river's way, cell by cell
  (`tools/earth_rivers.py --trace`). Every reason of an expected failure was written again from
  what these print.
* **What the land sheds, like for like.** A new measure and two new tests (section 4.4).
* **The label on the demand for water.** A docstring said the paper "works with a day's mean, in
  which the night's loss of heat is set against the day's gain [DOCUMENTED: its equation 18]". That
  was false, and marked as documented. The paper counts the hours of gain alone and gives the
  night's loss back to the soil as dew; equation 18 is the dew. The engine's form is mine. It is now
  said to be, with its size (section 7, item 14).
* **The check of the table of hollows** let through 5 of the reviewer's 36 breakages. It now also
  holds `depression_id` against the receivers, cell by cell, checks the height of every bottom and
  the bottom of every hollow made of two, and refuses a hollow without a pass that keeps a level.
  Each of 37 ways of breaking the table now has a test that asks for the refusal in the words of
  the rule broken. Before, one test accepted any of several refusals, so a check could be removed
  unnoticed.
* **The books of a gauge.** "What the lakes on the way lose" had been worked out as what was left
  over, so the identity it was checked against could not fail. It is now summed from the lakes'
  own losses, and a test adds them up once more by walking up the rivers.
* **Smaller things.** The soil's store keeps its bounds to the last digit (it could end a month
  3e-14 mm below empty). A driver that names a cell or a row is printed as "cell 456", not as
  "456 m³/s". A branch of the lake flows that no case reached is gone. [MEASURED: 60 rough grounds
  under random climates] The fingerprints of the code and of the lock file do not depend on line
  endings, and a test says so. The statements the reviewer found without labels carry them, and the
  stale ones are corrected (land "too dry because nothing evaporates from it", snow "too thin").
* **Left as found, and said:** two knife edges. Where three hollows meet at one pass cell and each is
  exactly full, their one sheet of water is named as two lakes or three (117 of 21,591 lakes in the
  reviewer's sample). Where a soil's supply equals its demand to the last digit, every store is a
  year that repeats, and the one returned is the one the search began from. Both are in the
  libraries' descriptions.
* **Changes made on purpose.** 81 more, one at a time, to the code written after the third check:
  23 to the settling of ties, 9 to the two processes' use of it, 19 to the check of the table, 23
  to the Earth harness and its tools, and 7 to the smaller things. The suite noticed 75. Of the six
  it did not notice, three change nothing that can be seen: a condition on level ground that says
  the same as the one it replaced; a line of the flood of the raw grid that did nothing, and is
  gone; and the lakes' losses at a gauge worked out as what is left over, which equals their sum
  whenever the books close, and the test holds either against a walk up the rivers. One moves
  3e-13 mm of water out of the soil's overflow, below anything a test can hold. Two were gaps in the
  Earth harness: a random settlement of the ties could have left the cells in their numbered order,
  and a settlement's ties could have failed to reach Hydrology, and no test would have said so.
  Both have tests now. Three more changes were noticed only by the Earth tests, a minute and a half
  into a run, and not by a test of the routine itself: the width of a way ignored on level ground,
  the narrowest pass taken first, and four neighbours for eight in the flood of the raw grid. Each
  has a test of its own now. [MEASURED: every one of these run again against its new test]

**Not mended: the same world on another processor.** The second reviewer built the default world on
a processor without the AVX-512 instructions and got other last digits: differences of at most 4
parts in a million, no class changed. [MEASURED by the reviewer, with the instructions switched off]
The design's promise is the same world, bit for bit, on one machine with the pinned versions, and
that holds. [MEASURED: two fresh interpreters] Across machines it does not hold to the last bit, and
I know no way to make it hold short of giving up the fast mathematics library. A world store carries
its own fingerprints, so a difference is seen, not hidden.

## 6. What is not done, and why

1. **Earth tests for half the processes.** With the four files of section 4.3, SeaLevel, Drainage,
   Hydrology and Biomes are tested on Earth's data, and the twin shows the whole. Insolation needs no
   data. Albedo, EnergyBalance, Circulation and Moisture are held against Earth only through the
   twin, because winds, pressure and measured evaporation are not at hand (ERA5 needs an account).
   Tectonics and Isostasy wait for ocean-floor ages and crust thickness. No tolerance is recorded:
   a tolerance is a misfit I would promise to stay within, and the misfits of sections 4.4 and 4.6
   are too large to promise.
2. **Isostasy's reference level is not tuned on Earth.** `reference_offset_m` was set before the
   reviews of step 1 so that the sea of the default world came to rest near the reference level.
   The sea now rests 153 m below it on the preview mesh, and I did not set the number again, because
   the design's tuning on Earth's crust and floor ages replaces it. [MEASURED; PROVISIONAL]
3. **The label on a finished world.** The design says a label entry can be applied to a finished
   world in one pass. That command is not built; a label is applied by building the world.
4. **The viewer reads the store through the server.** The design mentions a Zarr reader in the
   page. The page asks the local server for arrays instead, and the server reads the Zarr store.
   The store is unchanged by this, and the page holds no third-party code.
5. **history_length_my is one round.** The first Tectonics is a single snapshot, so a history of
   125 identical rounds would only cost time. The designed default of 250 My returns in step 3.
6. **Snapshots of the history, the rerun of the climate inside the history, the weather clock and
   the clock that steps through dates** are not built. The engine refuses each on loading, with
   the build step that brings it. The scheduler already orders and checks them.
7. **The high_fidelity profile was not run**, and nothing was timed on the laptop.
8. **Rivers and lakes are not drawn as lines and outlines.** The viewer colours cells by flow and by
   the share of the cell under a lake. A lake smaller than a cell has no shape.
9. **A fair test of rivers on Earth.** The relief data at hand hold closed valleys and exact ties
   that decide where rivers go before any process runs (section 4.4). Relief with its rivers cut in
   would make the tests of the mouths and the gauges mean something about Drainage. It is not among
   the data the build environment reaches.

## 7. Departures from the approved design

Each is recorded in the design document as well. Items 1 to 8 are of step 1; 9 to 21 of step 2.

1. **The rain rule.** The design named the UVic model's rule: rain where humidity exceeds 85 %.
   With that rule no rain fell anywhere in the trade-wind belts: yearly rain between 10° and 40°
   was 4 to 15 mm, land and sea alike. [MEASURED on the first build] Rain now rises smoothly with
   the humidity of the column: P = exp(11.4 (r − 0.522)) mm a day, fitted to monthly data over
   tropical seas. [DOCUMENTED: Bretherton, Peters and Back 2004, equation 2] Two additions are
   mine: outside the tropics the rate is scaled by how much vapour the air can hold, and the
   law's value in air that holds nothing is taken off, so that dry air gives no rain. [INFERRED]
2. **Constants set by hand** on the default planet, not on Earth: the drag of Circulation; in
   Moisture the shift under sinking air, the exchange coefficient, the gust speed, the mixing,
   the share of the converging wind (0.25), the share of lifted vapour that rains (0.08) and the
   reach of air turned aside (500 km). The aims were Earth's water budget as I recalled it.
   [CALIBRATED; the aims UNVERIFIED] They were set when the land gave no water back. I did not set
   them again in step 2: with Earth data at hand they should be set on the twin, not by hand.
3. **Tectonics keeps its seeded start in tables**, as the full version will, where the design's
   check 8 declared the slice version without them. The order is the same. The floor's age is
   capped at 180 My, and a quarter to a half of the floor sits at the cap. [MEASURED by a reviewer]
4. **The vapour budget is solved by sweeps on a ladder of meshes** (the multigrid method), which
   repeats until its last sweep changes little. The design's rule names one direct solver for
   large systems. The sweeps run on one thread in a fixed order and give the same bits each time.
   [MEASURED: the two-interpreter test] The stop test is not a bound on the error: the answer
   lies 0.002 to 0.012 kg/m² from the fully settled one, and the rain within 0.03 %. [MEASURED by
   a reviewer]
5. **Where snow and ice lie.** The design's slice put ice wherever the last round was below
   freezing. With that rule, ground that is cold but dry turned white with no snow to make it
   so, and one seeded world in 32 froze over. [MEASURED by a reviewer] Now ice lies on the sea
   where the year's mean is below −10 °C, the rule of North, Cahalan and Coakley 1981, which I
   apply to the sea only. [DOCUMENTED for the rule; INFERRED for the sea only] Snow lies on land
   where a store filled by snowfall and emptied by warmth holds snow (item 12). The low-sun term
   and the ice value come from the 1981 paper. [DOCUMENTED] Sea that is frozen all year is shown as
   the biome "ice".
6. **Air and high ground.** The design said Moisture ignores air blocked and turned aside by
   ranges. The first build let vapour pile up before high ground, so three rules were added.
   Between cells of different height only the part of a column above the higher ground crosses.
   Of the air held back, a set share is lifted and rains on the higher ground. The rest is
   turned aside and gathers within a set reach. The idea is that of mass-consistent wind models
   (Sasaki 1958; Sherman 1978), which I know only through a later chapter that describes them.
   [INFERRED: the construction is mine. DOCUMENTED at second hand: Juárez et al. 2012]
7. **The wind that carries vapour** is fitted from the surface wind: the whole of the part that
   circles, a quarter of the part that gathers. The design used the surface wind as it is.
   [INFERRED: mine]
8. **Pushes on groups.** A push is in force in the rounds its entry allows. Its record exists
   only if a reader was given a sum that held it, and the world store says why a push changed
   nothing. Before the first round of a history no push is in force. The design did not go into
   this. [INFERRED]
9. **Hollows are found as a hierarchy, not filled.** The design named Priority-Flood (Barnes et al.
   2014), which fills every hollow to its brim and leaves a surface that drains. Lakes need what
   filling erases: each hollow, its bottom, its pass and the hollow it spills into. Drainage finds
   them as a depression hierarchy. [DOCUMENTED: Barnes, Callaghan and Wickert 2020] It writes them as
   a table, `hollows`, which Hydrology reads. `drainage_area` and `basin_id` are what Priority-Flood
   would have given: the paths with every hollow full.
10. **What the two processes read.** Drainage also reads `sea_depth` and the table of seas, to know
    where the sea's surface stands. Hydrology reads `height_above_sea` and the table of hollows, and
    does not read `albedo`, `spill_elevation` or `vegetation_cover`, which the design's declaration
    listed: the albedo field is the planet's as seen from above the clouds, not the ground's, and
    plant cover does not exist yet. Hydrology reads `soil_water_capacity` from the previous round,
    as designed.
11. **A Soils slot exists already**, as a stand-in that gives every soil 150 mm. [DOCUMENTED when
    step 2 was written: the bucket of Manabe's models] Hydrology reads the field as it will read the
    real one, so step 7 replaces one file and touches nothing else.
12. **Snow.** One store, written by Hydrology: snowfall fills it and warmth empties it, 4 mm a day
    for each degree above freezing. [DOCUMENTED: Hock 2003, equation 1, for the rule; her Table 1
    gives 2.5 to 5.5 for snow; 4 is my choice] The ground counts as covered in proportion until the
    store holds 15 mm of water. [DOCUMENTED: Dutra et al. 2010, equation A2] `snow_cover`, the
    month's mean of that, is a field outside the design's list of 74; the Cryosphere of step 6 should
    take it over. Where more snow falls in a year than the year can melt, the store is held to one
    year's net snowfall, and what is older leaves as ice and is counted as runoff: a stand-in for a
    glacier. [INFERRED: mine] The design set a limit on depth instead; with that the store jumped by
    the whole limit when a cell tipped from losing its snow to keeping it, and each such cell cost
    the climate two or three more rounds. [MEASURED] What the number decides: with 0.2 years in
    place of 1, temperatures move by up to 0.8 K and 74 cells of 10,242 change biome; with 2 or 5
    years, by 0.002 K and one cell. [MEASURED on the default preview world]
13. **The bucket is solved exactly, month by month.** The design said ten sub-steps a month.
14. **The demand for water, and its error over land.** The Priestley-Taylor rule needs the energy the
    ground gains from radiation. The engine's own energy balance is a budget at the top of the air and
    does not give it. Hydrology therefore uses the two radiation formulas of the paper it takes the
    rule's constants from. [DOCUMENTED: Davis et al. 2017, equations 10 to 13] They ask for the share of
    the possible hours of sunshine, cell by cell and month by month. The engine has no clouds, so one
    share, 0.62, stands for every cell and month. [INFERRED] With it the formulas return the means of
    Earth's whole surface: 161 W/m² of sunlight absorbed and 63 W/m² of heat lost. [DOCUMENTED for
    Earth: Trenberth, Fasullo and Kiehl 2009, Table 2b] Over land alone they do not:

    | Over land, W/m² | The engine's formulas under Earth's measured temperatures | Measured |
    |---|---|---|
    | Sunlight that reaches the ground | 185.6 | 184.7 |
    | Sunlight that the ground absorbs | 154.0 | 145.1 |
    | Heat that the ground radiates away | 68.3 | 79.6 |
    | Left to warm the air and evaporate water | 85.7 | 65.5 |

    [MEASURED: `python tools/earth_demand.py`; DOCUMENTED for the right-hand column: the same table's
    row for land] The land is left 1.31 times the energy measured. No single share mends both parts:
    the sunlight wants 0.61 and the heat 0.76. Part of the excess lies on snow, ice and desert, where
    it takes no water. What reaches the rivers is in section 4.4: like for like, the land sheds 0.68
    of the depth measured, and with the demand cut by that same factor of 1.31 it sheds 0.97. I left
    the published constants as published. The mend is a process that makes clouds, which the design
    does not have (section 11).

    **The rule is applied to the whole day, which is not the paper's way.** The paper applies it to
    the hours in which the ground gains energy and gives the night's loss of heat back to the soil as
    dew. [DOCUMENTED: its equations 14, 16, 18, 24 and 25, read through a page reader, twice] The
    engine takes the net radiation of the whole day. This began as my misreading of the paper, which
    I had labelled as documented; the third check found it. Over Earth's land the engine's demand is
    1,003 mm a year. The paper's form gives 1,246 mm from the same numbers and gives 194 mm back as
    dew: 1,052 mm net. [MEASURED: `tools/earth_demand.py`] So the engine's field
    `potential_evapotranspiration` is a fifth below the quantity the paper calls by that name, and
    its net taking of water is 5 % below the paper's. I kept it and said so: the error of the one
    share of sunshine is six times as large and of the other sign, and 194 mm of dew a year over all
    land is more than I can hold against anything measured. [UNVERIFIED: that real dew is far less]
15. **Lakes.** The published method moves water until no hollow holds more than its volume. A climate
    that repeats has no filling: a lake has stopped growing when a year's inflow equals a year's loss
    from its surface. So a hollow's room is a yearly loss, not a volume; the order of filling,
    spilling and merging is the published one. [INFERRED: the change is mine] Open water loses the
    full demand of the air, worked out for a surface as dark as water. A lake with an outlet passes
    on, every month, the share of its inflow that it does not lose over the year: it does not even
    out the seasons of the river below it, as a real lake does. [INFERRED: mine]
16. **A group may carry its own settle tolerance.** `moisture_source` has one. The design gave
    tolerances to fields only.
17. **The dry-belt condition is an expected failure in the north** (section 3.1).
18. **The Earth data lives beside the engine**, in `src/earth_reference/`, and the twin is built
    without Tectonics. The design had the twin as a parameter file of the engine; a world built on
    measured relief has no plates to explain, and should not pretend to.
19. **Why-answers have cases.** The design gave each field one sentence pattern. One sentence could
    not be true of land, lake and sea alike.
20. **Exact ties go to the wider way.** The design's rule, each cell to its lowest neighbour, says
    nothing of neighbours that are equally low. They are common: on every coast, because the cells
    of one sea stand at one level and wide stretches of sea floor lie at one depth; and on any
    relief given in whole metres. A tie goes to the lower bed, then to the wider way, the longer
    boundary shared by the two cells, and last to the order of the cells. [INFERRED: mine. The
    wider way is a property of the mesh and not of the ground. It claims no knowledge of the ground;
    it only keeps the result from depending on how the cells happen to be numbered, and it turns
    with the planet] The lengths are rounded to a billionth of the longest before they are compared.
    The mesh has boundaries that are mirror images of each other, exactly as long, and its geometry
    carries rounding errors of up to about 1e-11 of the longest boundary on the standard mesh.
    Unrounded, those errors would tell nearly every such pair apart. Rounded, the pair counts as
    equal and the cell numbers decide, except where the two lengths fall on either side of a rounding
    step: 29 of 487,377 such neighbours in the sorted list of lengths on the standard mesh, 2 of
    121,824 one level coarser, none on the preview mesh. [MEASURED] There the rounding error decides,
    the same on every run. The fourth round of my own checking found this; I had written that
    rounding "does not settle a tie", which the rounding does not ensure. Hydrology settles the ways
    across its lakes the same way; both processes take the rule from one function of the library.
21. **`potential_evapotranspiration` is not the paper's quantity of that name** (item 14): it is the
    demand over the whole day, on the ground that is free of snow.

## 8. What the world looks like now, and where it is wrong

Default world, seed 20261004. [MEASURED unless marked: `python tools/world_report.py STORE`]

| | Standard mesh | Preview mesh | Earth |
|---|---|---|---|
| Land, share of the surface | 36 % | 34 % | 29 % [from the sea area in the design's source: NOAA, 361.9 of 510.1 million km²] |
| Mean depth of the sea | 4,070 m | 3,990 m | about 3,700 m [DOCUMENTED in the design: NOAA] |
| Mean temperature | 11.4 °C | 11.9 °C | 14.0 °C [MEASURED from the temperature data of section 4.3] |
| The poles, yearly mean | −21.1 °C (land) and −16.4 °C (sea) | −20.0 and −15.8 °C | |
| July less January, land from 40° to 60° north | 12.3 K | 11.6 K | 30.9 K [MEASURED from the same data] |
| Land under snow in every month | 20 % | 20 % | 10 % under ice [DOCUMENTED: National Snow and Ice Data Center] |
| Rain over the globe | 945 mm a year | 969 mm | 977 mm [MEASURED from the rain data of section 4.3] |
| Rain over land | 618 mm | 643 mm | 790 mm [MEASURED from the same; DOCUMENTED: Schneider et al. 2017 give the same number] |
| Rain on land that goes back to the air | 0.74 | 0.74 | 0.65 [DOCUMENTED: Trenberth, Fasullo and Mackaro 2011] |
| Rivers reaching the sea | 29.7 thousand km³ a year | 29.8 | 40 [the same source] |
| Largest river | 100,500 m³/s | 100,700 m³/s | 210,000 m³/s, the Amazon [DOCUMENTED: Dai and Trenberth] |
| Driest land band below 60°, north and south | 58° (290 mm) and 24° (251 mm) | 58° (297 mm) and 24° (269 mm) | 27.5° (566 mm) and 32.5° (629 mm) [MEASURED from the rain data] |
| Land that drains into a closed hollow | 48 % | 47 % | |
| Land whose water never reaches the sea, as the water runs | 18 % | 19 % | |
| Land under lakes | 8.3 % | 8.9 % | 3.7 % of the ice-free land [DOCUMENTED at second hand: Verpoorter et al. 2014] |
| Largest lake | 5.9 million km² | 7.6 million km² | 0.37 million km², the Caspian [UNVERIFIED] |
| Climate groups, share of land: tropical / dry / temperate / cold / polar | 10 / 36 / 17 / 4 / 33 % | 11 / 37 / 17 / 3 / 32 % | 19 / 30 / 13 / 25 / 13 % [DOCUMENTED: Peel et al. 2007] |
| Wettest land cell | 13.5 m a year | 4.3 m | |

In order of how much they distort the world:

* **The seasons on land are too weak, and too much land is white all year.** This is the largest
  known error, and step 2 did not touch its cause. One spreading constant in EnergyBalance ties land
  to the sea too tightly. Measured with EnergyBalance alone: the centre of a continent 60° of
  longitude wide swings 10.7 K either side of its mean at 50° north, and one 140° wide swings 20 K.
  Later models of this family let the spreading vary with latitude and surface. [DOCUMENTED: Ziegler
  and Rehfeld 2021] On Earth's own relief the engine's land between 40° and 60° north is 13 K warmer
  in July than in January, where Earth's is 31 K; the cold climates with warm summers take 2 % of the
  land for Earth's 25 %, and the polar climate 46 % for 13 % (section 4.6). With weak summers the
  snow of land poleward of about 50° never melts; the white ground then gives the air no water, and
  the north is dry as well. In ten other seeds 11 to 47 % of the land is white all year. [MEASURED]
* **The engine has no clouds.** Albedo gives every sky the same share of cloud, and Hydrology gives
  every month the same share of sunshine. The first costs the cloud decks of cool seas and the
  cloud bands of the tropics. The second is measured: section 4.4 and section 7, item 14.
* **Half the land drains into closed hollows, and a twelfth of it lies under lakes.** Two of the
  lakes are inland seas of 5.9 and 3.6 million km², in basins below sea level that the ocean does not
  reach. The seeded relief has had no rivers to cut it. FluvialErosion (step 3) cuts valleys on the
  mesh itself. [INFERRED: that this removes most of the excess; it is tested there] Earth's measured
  relief says nothing either way about this: its hollows are in the data (section 4.4).
* **The land gives the air too much water and the rivers too little.** Under Earth's own rain and
  warmth the land of fourteen great basins sheds 0.68 of the depth measured, and 31.7 thousand km³ a
  year reach the sea where Earth's rivers carry 40. The measured part of the cause is the demand for
  water, 1.31 times too high over land with one share of sunshine everywhere (section 7, item 14).
  The error is not even: the land sheds least where the rain comes in the warm season (the Yangtze
  0.21, the Brahmaputra 0.23) and a little too much in four basins (the St Lawrence 1.45). Dry land
  sheds nothing at all, where on Earth it sheds its rare cloudbursts: a bucket fed with a month's
  mean rain knows no storm. Frozen ground is not in the model. [MEASURED for the numbers; INFERRED
  for the storm and the frozen ground]
* **Rivers have no travel time and lakes do not even out the seasons.** A month's runoff is at the
  sea in the same month.
* **Land warms a month late.** Land lags the sun by 41 to 62 days, and northern land is warmest
  in August. [MEASURED by a reviewer on the first build; not measured again]
* **The planet is near the edge of a deep ice age.** With 2 % less sunlight the default planet is
  4.8 K colder and stays open. With 5 % less it averages −2.9 °C, and the world store says "a deep
  ice age". Models of this kind tip more easily than fuller ones. [MEASURED for the numbers;
  UNVERIFIED for the comparison]
* **The rain of rising ground falls in one cell.** The amount per kilometre of cliff is the same
  on every mesh, so the amount per cell grows as cells shrink. The seeded continents end in cliffs,
  which no real coast does. Spreading that rain over a set distance inland is left for the upgrade
  of Moisture (step 5). The wettest land cell gets 4.3 m a year on the preview mesh and 13.5 m on
  the standard one. [MEASURED]
* **Snow that never melts feeds rivers as "ice that leaves".** It stands in for glaciers. With
  summers this weak it reaches far toward the equator: the cell that gives the largest river of the
  preview world the most water lies at 23° north, under snow all year, and 89 of the 126 mm a month
  it sheds are ice. [MEASURED]
* **A hollow under snow that never melts fills as a lake**, where a real one would hold ice.
* **Deep basins that the sea did not reach** are now lakes or dry, as their climate decides.
* The plates are a snapshot: ocean-floor ages are read off distances, not lived through.

## 9. What a replacement of Drainage or Hydrology must honour

The design's promise is that a process can be replaced by a better model without touching the
others. For these two the scheduler checks the fields; four things it cannot check.

1. **The table of hollows has rules**, stated in `data/tables.yaml` and checked by
   `library/lakes.py: check_table` whenever Hydrology runs: row 0 is the sea; the hollows with one
   bottom come first, one for every land cell without a receiver, and `depression_id` names the one
   that a cell's water ends in, down its receivers; a larger hollow is made of two earlier rows and
   has the bottom of the deeper; passes lead where the table says; heights are those of the field
   `elevation`; a hollow with no way out has no level. A Drainage that writes another kind of table
   must come with a Hydrology that reads it. [MEASURED: 37 ways of breaking the table, each refused
   in the words of its rule]
2. **`flow_receiver` is −1 for a sea cell and for the bottom of a hollow.** `basin_id` and
   `drainage_area` describe the land with every hollow full, whatever the climate.
3. **The sentence patterns name drivers.** A replacement records the drivers that
   `data/explanations.yaml` names for its fields, or brings its own patterns. The engine refuses, on
   loading, a pattern that names a driver its process does not record, and a pattern for a field its
   slot does not write. [MEASURED: test]
4. **Ties are settled in one place.** Drainage and Hydrology both ask `library/drainage.mesh_ties`
   how exact ties are settled, so that the ways across a lake agree with the ways on dry ground. A
   replacement of one that settles ties otherwise must change that function, not go round it.
   [MEASURED: test]

Hydrology's field `potential_evapotranspiration` is the demand over the snow-free share of the
ground, worked out from the net radiation of the whole day: it is neither the demand of a wet
surface nor the quantity that the paper behind its formulas calls by that name (section 7, item 14).
A model that reads it must know that. Biomes does not read it yet.

## 10. Sources opened during the build

| Source | Used for | How I checked it |
|---|---|---|
| North, Cahalan, Coakley 1981 (in the design) | Co-albedo 0.681 − 0.202 P2, ice co-albedo 0.38, heat capacities, ice at the −10 °C yearly mean | Opened; a reviewer matched the constants and the quote on page 102 |
| [Bretherton, Peters, Back 2004](https://www.aos.wisc.edu/~lback/wvpprecip.pdf), J. Climate 17, 1517 | The rain law and its two numbers | Opened as an author's copy; equation 2 read |
| Peel, Finlayson, McMahon 2007, Hydrol. Earth Syst. Sci. 11, 1633 | Every rule of the climate classes; Earth's share of each class | Opened |
| Beck et al. 2018 (in the design) | Arid classes take precedence; a climate dry in summer and in winter | Opened |
| [Hock 2003](https://www.oocities.org/haniskywalker/hock2003.pdf), J. Hydrology 282, 104 | The degree-day rule of melt and its factors for snow | Opened as a copy on a personal site |
| [Dutra et al. 2010](https://www.fs.usda.gov/rm/pubs_other/rmrs_2010_dutra_e001.pdf), J. Hydrometeor. 11, 899 | Snow cover from the snow store, equation A2 | Opened |
| Juárez et al. 2012, a chapter on mass-consistent wind models | The idea behind turning held-back air aside; it cites Sasaki 1958 and Sherman 1978 | Opened; the two papers it cites were not |
| [Ziegler and Rehfeld 2021](https://gmd.copernicus.org/articles/14/2843/2021/gmd-14-2843-2021.pdf), Geosci. Model Dev. 14, 2843 | Later two-dimensional energy balance models let the spreading vary | Opened |
| van der Ent et al. 2010, Water Resour. Res. 46 | 40 % of land rain comes from land | Read at second hand, in a paper that cites it |
| [National Snow and Ice Data Center, Glacier Quick Facts](https://nsidc.org/learn/parts-cryosphere/glaciers/glacier-quick-facts) | 10 % of Earth's land is under ice | Opened |
| [NCAR Climate Data Guide, GPCP monthly](https://climatedataguide.ucar.edu/climate-data/gpcp-monthly-global-precipitation-climatology-project) | Earth's mean precipitation, 2.67 mm a day | Opened |
| [Schneider et al. 2017](https://www.mdpi.com/2073-4433/8/3/52), Atmosphere 8, 52 | Earth's precipitation over land, 790 mm a year | Opened, abstract |
| Ferreira et al. 2014, Icarus 243, 236 (in the design) | The tilt above which poles get more yearly sunlight than the equator | Opened as a copy on an author's site |
| plotbiomes, an R package by V. Stefan (MIT licence) | The outlines of Whittaker's chart, digitised from Ricklefs 2008 | Cloned from GitHub and read |
| Barnes, Callaghan and Wickert 2020 and 2021 (depression hierarchy; Fill-Spill-Merge), arXiv | Finding the hollows and the order in which water fills, spills and merges | Opened when the design and step 2 were written; the change from volumes to yearly losses is mine |
| [Davis et al. 2017](https://gmd.copernicus.org/articles/10/689/2017/gmd-10-689-2017.pdf), Geosci. Model Dev. 10, 689 (the SPLASH model) | The Priestley-Taylor rule, the two radiation formulas and every constant of the demand for water; and what the engine does not take from it: the hours of gain and the dew | Opened as a library copy; the constants of equations 10 to 13, 20, 22, B1, B2 and B8 read. Equations 14, 16, 18, 24 and 25 read out by a page reader, twice, after the third check |
| The SPLASH code: [geco-bern/rsofun](https://github.com/geco-bern/rsofun), `src/waterbal_splash.mod.f90`, and dsval/rsplash, `src/EVAP.cpp` | The heat of vaporisation, where the paper's text layer runs an exponent into a number | Fetched and read: "1.91846e6*((tc + 273.15)/(tc + 273.15 - 33.91))**2" |
| FAO Irrigation and Drainage Paper 56, Annex 3 | The heat of vaporisation at 20 °C, 2.45 MJ/kg, as a test of that formula | Opened |
| [Trenberth, Fasullo and Kiehl 2009, "Earth's Global Energy Budget"](https://staff.cgd.ucar.edu/trenbert/trenberth.papers/TFK_bams09.pdf), Bull. Amer. Meteor. Soc. 90, 311, Table 2b | Sunlight absorbed and heat lost at Earth's surface: the globe, the land and the sea | Opened; the three rows read, and read out again by a page reader on 2026-10-05: land 145.1 absorbed, 39.6 reflected, 79.6 net loss of heat; globe 161.2 and 63 |
| [Trenberth, Fasullo and Mackaro 2011, "Atmospheric Moisture Transports from Ocean to Land and Global Energy Flows in Reanalyses"](https://staff.cgd.ucar.edu/trenbert/trenberth.papers/2011jcli24.pdf), J. Climate 24, 4907 | Rain on land, evaporation from land and river flow to the sea: 114, 74 and 40 thousand km³ a year | Opened when step 2 was written, and read out again by a page reader on 2026-10-05: "For land, the precipitation value is 114 × 10³ km³ yr⁻¹", "evapotranspiration is 74", discharge 40, for 2002 to 2008 |
| [Dai and Trenberth, "New Estimates of Continental Discharge and Oceanic Freshwater Transport"](https://ams.confex.com/ams/pdfpapers/55037.pdf), Table 2 | The flow and the basin of 21 great rivers at their last gauging stations; the Amazon's flow at its mouth | Read out by a page reader, row by row; the basins read twice. I have not seen the table myself |
| [Verpoorter et al. 2014, "A global inventory of lakes based on high-resolution satellite imagery"](https://agupubs.onlinelibrary.wiley.com/doi/10.1002/2014GL060641), Geophys. Res. Lett. 41, 6396 | Lakes cover 3.7 % of Earth's ice-free land | At second hand: a page that reports the paper. The paper would not open, again on 2026-10-05 (the publisher refuses the reader) |
| [NCAR/GeoCAT-datafiles](https://github.com/NCAR/GeoCAT-datafiles) | The four data files of section 4.3 | Fetched; the files' own attributes read for what they hold and who made them |
| ["Investigation of Caspian Sea Level Fluctuations ..."](https://www.ijcoe.org/article_149296_f5ae89f43cbcf8f98aa838f382fb2416.pdf), Int. J. Coastal and Offshore Eng. | The Caspian: the Volga brings 237 km³ a year, about 80 % of the inflow; a catchment of about 3 million km²; "about 436000 km2" of sea | Read out by a page reader. Its own evaporation and rain do not balance its inflow, so I use only the inflow and the catchment |
| [Wikipedia, "Caspian Sea"](https://en.wikipedia.org/wiki/Caspian_Sea) | The Caspian: 371,000 km² without the Garabogazköl lagoon, 28 m below the ocean | Read out by a page reader. It disagrees with the paper above on the area; both are given in section 4.4 |
| [Kalugin 2022, "Hydrological and Meteorological Variability in the Volga River Basin under Global Warming by 1.5 and 2 Degrees"](https://www.mdpi.com/2225-1154/10/7/107), Climate 10(7), 107 | The Volga's basin: 1,360,000 km², 585 mm of precipitation and 262 km³ of runoff a year, "based on the author's calculations for current climatic conditions (since the late 1980s)" | Found by the third reviewer; then read out to me by a page reader, with the three sentences quoted |
| [Barnes, Callaghan and Wickert 2020, "Computing water flow through complex landscapes – Part 2: Finding hierarchies in depressions and morphological segmentations"](https://esurf.copernicus.org/articles/8/431/2020/), Earth Surf. Dynam. 8, 431 | The sentence Drainage quotes for a pass: "The higher of the two is the outlet cell, and its elevation is the depression's spill elevation" | Opened again on 2026-10-05; the sentence read out by a page reader |
| [FAO Irrigation and Drainage Paper 56, Chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm) | "a single value of 2.45 MJ kg-1 ... This is the latent heat for an air temperature of about 20°C" | Opened on 2026-10-05, beside Annex 3 above |

## 11. Next

Step 2 is closed as far as its own models go, with one condition of the design that Earth's relief
data cannot decide (the closed Caspian) and one known error of size (the land sheds two thirds of
the water it should). Before step 3 (the plates) I would mend one of the two faults that distort
every map the engine draws. They are yours to rank.

1. **The seasons of the land** (EnergyBalance: the spreading of heat, and how snow and ice feed
   back). It is the largest known error. On Earth's relief the engine's northern land is 13 K warmer
   in July than in January where Earth's is 31 K, the polar climate takes 46 % of the land for
   Earth's 13 %, and a third of the land is white all year. [MEASURED: section 4.6] The Earth twin
   gives three tests to judge a mend by: 31 K between July and January on northern land, a fifth of
   the land in the cold climates, and the dry belt as the driest band.
2. **Clouds.** A process that gives each cell and month a share of sunshine from the air's moisture
   and its rising and sinking, read by Albedo and by Hydrology. The design has no such process, so
   this one needs a design decision first. What would judge it is measured already: the radiation
   left to the land (85.7 W/m² for 65.5: `tools/earth_demand.py`) and the like-for-like depths
   (0.68: `tools/earth_rivers.py`). The gauges would not judge it: where the rivers run on Earth's
   relief is decided by the relief data and their ties.

My proposal is the first, then step 3, with clouds designed alongside step 5 (the upgrade of
Circulation and Moisture), where rising air and moisture are remade anyway.

One thing would make Earth a better yardstick for rivers at any time: relief with its rivers cut in.
It is not among the data the build environment reaches. On your machine it could be fetched; say so
if you want the tests of the mouths and the gauges to mean more than they do now.
