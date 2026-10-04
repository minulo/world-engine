# Build notes

State of the build on 2026-10-04: build steps 0 and 1 of the design document "World engine design:
physical causes, replaceable processes", after two independent reviews and a third, narrower check,
each followed by fixes (section 4).

Labels: **[MEASURED]** I ran it in the build environment and read the number. **[DOCUMENTED]** I opened
the source during the build. **[INFERRED]** my reasoning. **[UNVERIFIED]** recalled, not checked.
**[PROVISIONAL]** a first value that an Earth test must tune. **[CALIBRATED]** set by hand on the default
planet.

The build environment was a cloud workspace with 2 processor cores and about 8 GB of memory, Python 3.13,
and the versions in `requirements.lock`. Nothing here was run on the target laptop.

## 1. What exists

| Build step | State | Evidence |
|---|---|---|
| 0. Skeleton | Done | 264 tests: mesh, parameter files, the scheduler with every refusal, rounds, pushes, labels, the store, the server, the test harness |
| 1. The slice | Done, with the gaps listed in section 5 | 98 further tests of the ten processes and of the whole world; two trials in `trials/results/` |
| 2 to 11 | Not started | |

`python -m pytest` runs 362 tests in about five minutes. [MEASURED: 4 min 56 s]

## 2. Step 0 against its "done when"

| Condition in the design | Result |
|---|---|
| Three toy processes with a loop, a modifier and a push reach a known steady answer | Pass. a = 7 and b = 8 to within 1e-6 after 52 rounds [MEASURED: `tests/test_engine.py`] |
| First-round defaults are tested | Pass. Round 1 reads the default of fields.yaml; round 2 reads the blended copy |
| Every refusal message is tested | Pass. Every refusal of the scheduler is checked for its message (`tests/test_scheduler.py`, 60 tests), and the engine's own in the four engine test files |
| A world holding only geometry is identical on a second run | Pass, and identical in two fresh interpreters with different hash seeds |
| It opens in the viewer through the local server | Pass. Checked in a headless browser (`tools/viewer_check.py`) and by tests of the server's answers |

The scheduler is the routine of the design's check script, ported with its messages. It gives the
design's order for all 22 declarations and for the slice. [MEASURED: `tests/test_scheduler.py`,
which holds the design's declarations as test data] It was not changed by any of the reviews.

The mesh: cell areas add up to the sphere to 12 digits; the largest cell has 1.36 times the area
of the smallest, at every level from 5 to 7; the cells are 240, 120 and 60 km apart. [MEASURED]

## 3. Step 1 against its "done when"

| Condition in the design | Result |
|---|---|
| Each process meets the fixed pass conditions of its first version | Pass for the conditions that need no Earth data (section 3.1). The conditions that feed a process real inputs are not run: section 5 |
| Its tolerance is recorded | Not done. A tolerance is a misfit against Earth data, and there is no Earth data yet |
| The two patterns the first version cannot show are measured and recorded as failures | Not measured against ERA5. What the engine's own world shows: no wind reverses with the season, and the sinking air is the same at every longitude |
| The crust trial meets conditions fixed before it runs | Pass on the default world at both mesh sizes, after one change to how the first condition is measured. Two failures outside the default setting. Section 3.2 gives all of it, and the choice it leaves you |
| explain() returns a chain | Pass |
| The frozen-region example works in reduced form | Pass (section 3.4) |
| A place label alone changes no other field | Pass: every other field keeps its fingerprint |
| Both poles are colder than the equator and below freezing in the yearly mean, and the Albedo slice marks ice at both | Pass (section 3.3) |
| Run times are measured for the preview and standard profiles | Done (section 3.5) |
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
| Moisture | One ridge across a steady wind: wet on the side facing the wind, dry on the sheltered side; evaporation equals precipitation over the globe; the driest land band between the equator and 60° lies between 15° and 40° | Pass: the side facing the wind gets 2.9 times the rain of the same strip without the ridge, the sheltered side 0.2 times; evaporation over precipitation is 1.000000; the driest land bands lie at 29° N and 24° S (both at 24° on the standard mesh) |
| Biomes | Twelve months at 26 °C with 300 mm each give tropical rainforest and class Af; a warmest month below freezing gives ice and no plant cover; seven further classes follow the published rules | Pass |

Two conditions were added by the reviews and hold on every mesh tried. The rain over the 500 km
before a wall 2.5 km high is 4.1, 3.9, 3.9 and 3.9 m a year at cells 480, 240, 120 and 60 km
apart. Air over cold high ground holds at most 0.9 of what it can hold. [MEASURED by the third check]

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
its own resampling interval it does, with the measure of A changed as described. My reading is
that the crust stays on the points, with three duties for step 3: fill fresh points as the paper
does, make new ocean floor at parting margins before drawing, and carry conditions A to C into
the tests of the real Tectonics at both mesh sizes. Because I changed a measure after a failure,
the decision is yours to confirm. [INFERRED]

### 3.3 Cold poles

The requirement added when the design was approved. Nothing in the engine places cold.

* Yearly sunlight at each pole is 41.5 % of the equator's at a tilt of 23.44°. [MEASURED: test]
* Default world, preview mesh: the north pole averages −20.1 °C over the year and its warmest
  month −16.5 °C; the south pole −15.6 °C and −14.1 °C; the equator +26.1 °C. On the standard
  mesh: −21.2, −16.2 and +25.6 °C. The north pole is the colder one because it is land 640 m
  high and the south pole is sea. [MEASURED]
* Albedo marks ice at both pole cells in every month, and the biome there is ice. [MEASURED]
* Ten other seeds all have cold poles: between −9 and −22 °C in the yearly mean, below −6 °C
  in the warmest month, with ice at both poles in every month. [MEASURED]
* A planet tilted 60° is still built; the world store then names EnergyBalance as outside its
  range, and the pole gets more yearly sunlight than the equator, as the formula says.
  [MEASURED: test]

### 3.4 Pushes

`data/examples/frozen_region.yaml` on the default world: the order becomes Albedo, Insolation,
EnergyBalance, **push: cap**, Circulation, Moisture, Biomes, as the design's table shows. The
centre of the region is sea. In the plain world its months run from 2.7 to 6.9 °C. The heat
sink of −120 W/m² alone brings them to −1.6 to 2.1 °C. The cap then holds every month at −15 °C,
and the biome becomes ice. Between 900 and 1,500 km from the centre, outside the region, the
year is 2.8 K colder. The fields of the geological stage keep their values. The "why" answer
names the entry, its reason, "not physical", the heat sink and the value before the cap.
[MEASURED: test] The cap is −15 °C and not the design's −5 °C because ice lies on the sea only
below a yearly mean of −10 °C (section 6, item 5). The third push of the design's example, on
the day's temperature, waits for the weather stage of step 8.

`data/examples/place_label.yaml` names the forest inside a circle. Its circle now lies where
forest grows in the default world (50° S, 105° E): 72 cells are labelled on the preview mesh,
every one a forest cell, and no other field changes. Moved to a place without forest, the entry
labels nothing and the world store says so. [MEASURED: test]

### 3.5 Run times and the cost of a climate round

All [MEASURED] on the 2-core build environment; the laptop is not timed.

| Profile | Cells | Whole build | Climate rounds | One later round | Preparing the heat solver | Peak memory | World store |
|---|---|---|---|---|---|---|---|
| preview | 10,242 | 23 s | 16 | 1.1 s | 0.45 s | 0.4 GB | 17 MB |
| standard | 163,842 | 492 to 531 s in three runs | 17 | 23.5 s | 34 s | 4.8 GB | 194 MB |

In a standard round Moisture takes 20.3 s, Circulation 2.2 s, Biomes 0.5 s, EnergyBalance 0.4 s.
Before the reviews a standard build took 233 s; the rule for air held back by high ground
(section 6, item 6) costs two extra solves per month and mesh level. The limit of the standard
profile is 1,800 s. The three standard builds gave the same world, bit for bit: the last was
made after the fixes of the third check, which therefore changed nothing in the default world. The high_fidelity profile was not run. Its solvers would need about four
times the memory of the standard profile's, so whether it fits in 32 GB is open. [INFERRED]

## 4. Three rounds of checking, and what they changed

Each round was done by reviewers who had not seen the code being written, with scripts of their
own. Their reports are summarised here. Every finding marked high or medium has a test. The
second review found three such tests that also passed on the faulty code; they were rewritten,
and from then on each new test was run against the code as it stood, to see it fail.

| Round | Found | Changed |
|---|---|---|
| 1. Physics | 2 high, 2 medium, 5 low. Plate boundaries were judged along the line between two cell centres, so plates sliding past each other came out as ridges and collisions. Vapour mixed into the thin cold air over high ground: one cell got 72 m of rain a year, and 43 % of the land's rain fell on 4 % of the land | The direction of a boundary is added up along the boundary. Vapour crosses between columns only above the higher ground. Evaporation uses the surface wind. The climate classes follow the published rule where a climate is dry in summer and in winter |
| 1. Engine | 1 high, 14 medium, 9 low. A push limited to rounds was applied in every round. Groups with members in two stages lost a member. True-or-false and missing values were left out of the test for a settled climate. A push could not set a cell that had no value. A long outline pushed cells on the far side of the planet | All fixed, 47 tests (`tests/test_engine_cases.py`) |
| 2. Physics | 1 high, 1 medium, 4 low. The climate could run away to a frozen planet: 1 seed in 32, and the default planet with 2 % less sunlight. Rain piled up in the last cell before high ground and grew as the cells shrank | Snow needs snowfall (section 6, item 5). Air held back by high ground is partly lifted and partly turned aside (item 6). Ties in Tectonics are settled by what the cells are, not by their numbers |
| 2. Engine | 19 groups of defects, and about 20 changes made to the engine on purpose that no test noticed | All fixed, 62 tests (`tests/test_engine_round2.py`). Afterwards 44 changes made on purpose were each noticed by the suite |
| 3. Physics | No high. 1 medium: on a planet without sea the solver left water in the air, more on finer meshes. 3 low, and five numbers in comments that did not reproduce | A month that nothing feeds is given its exact answer, zero. Ties among any number of equally near cells. The comments carry the measured numbers |
| 3. Engine | No high. 4 medium, one of them new: a notice silenced by a fix of round 2. 7 low | All fixed, 22 tests (`tests/test_engine_round3.py`) |
| My own re-measurement | The crust trial no longer passed as measured | Section 3.2 |

Left as found, and listed in section 7: the rain of rising ground falls in one cell, and the
seasons on land are too weak.

## 5. What is not done, and why

1. **No test against Earth data.** The build environment reaches package registries and GitHub
   only, so ETOPO, ERA5 and the other reference data of Layer 9 could not be fetched, and ERA5
   needs an account. Every "Earth pattern" and the "Earth twin" are therefore untested. No
   tolerance is recorded. The pass conditions above are the fixed ones, checked on the engine's
   own world or on inputs built for the purpose. This is the largest gap of step 1.
2. **Isostasy's reference level is not tuned on Earth.** `reference_offset_m` was set before the
   reviews so that the sea of the default world came to rest near the reference level. After
   the fixes the sea rests 153 m below it on the preview mesh and 225 m below it on the standard
   mesh, and I did not set the number again, because the design's tuning on Earth's crust and
   floor ages replaces it. [MEASURED; PROVISIONAL]
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

## 6. Departures from the approved design

Each is recorded in the design document as well.

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
   [CALIBRATED; the aims UNVERIFIED]
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
   where a store filled by snowfall and emptied by warmth holds snow. The melt is 4 mm a day for
   each degree above freezing. [DOCUMENTED: Hock 2003, equation 1, for the rule; her Table 1 gives
   2.5 to 5.5 for snow; 4 is my choice] The ground counts as white once the store holds 15 mm of
   water. [DOCUMENTED: Dutra et al. 2010, equation A2] The low-sun term and the ice value come
   from the 1981 paper. [DOCUMENTED] Sea that is frozen all year is shown as the biome "ice".
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

## 7. What the first world looks like, and where it is wrong

Default world, standard mesh, unless marked. [MEASURED unless marked]

| | This world | Earth |
|---|---|---|
| Land, share of the surface | 36 % | 29 % [DOCUMENTED in the design: NOAA] |
| Mean depth of the sea | 4,070 m | about 3,700 m [DOCUMENTED in the design: NOAA] |
| Mean temperature | 11.4 °C | about 14 °C [UNVERIFIED] |
| Yearly swing on land at 40° to 60°, either side of the mean | 6.2 K | 15 to 20 K inside the northern continents [UNVERIFIED] |
| Land under snow or ice all year | 20 % | 10 % [DOCUMENTED: National Snow and Ice Data Center] |
| Rain over the globe | 800 mm a year | 975 mm (2.67 mm a day) [DOCUMENTED: GPCP, 1979 to 2010] |
| Rain over land | 306 mm a year | 790 mm [DOCUMENTED: Schneider et al. 2017] |
| Climate classes, share of land: tropical / dry / temperate / cold / polar | 8 / 54 / 5 / 3 / 30 % | 19 / 30 / 13 / 25 / 13 % [DOCUMENTED: Peel et al. 2007] |

* **The land is too dry**: it gets about 40 % of Earth's rain, and 63 % of it gets under 250 mm
  a year. Land gives no water back to the air until Hydrology exists (step 2). On Earth about
  40 % of the rain over land is water that evaporated from land. [DOCUMENTED at second hand: van
  der Ent et al. 2010] Nothing in the first Circulation makes a monsoon either (step 5).
* **The seasons on land are too weak, and too much land is white all year.** One spreading
  constant ties land to the sea too tightly. Measured with EnergyBalance alone: the centre of a
  continent 60° of longitude wide swings 10.7 K either side of its mean at 50° north, and one
  140° wide swings 20 K. With weak summers the snow of land poleward of about 50° never melts.
  In ten seeded worlds 15 to 48 % of the land is white all year. Later models of this family
  let the spreading vary with latitude and surface. [DOCUMENTED: Ziegler and Rehfeld 2021] With a
  smaller constant (0.35 for 0.649) the same two continents swing 15.9 and 27.6 K. That change
  needs a test against Earth, so I propose it as the first refinement once Earth data is at hand.
* **Land warms a month late.** Land lags the sun by 41 to 62 days, and northern land is warmest
  in August. [MEASURED by a reviewer on the first build; not measured again]
* **The planet is near the edge of a deep ice age.** With 2 % less sunlight the default planet is
  4.2 K colder and stays open, as do ten other seeds (2.8 to 3.7 K colder). With 5 % less it
  averages below freezing, and the world store says "a deep ice age". Models of this kind tip
  more easily than fuller ones. [MEASURED for the numbers; UNVERIFIED for the comparison]
* **The rain of rising ground falls in one cell.** The amount per kilometre of cliff is the same
  on every mesh, so the amount per cell grows as cells shrink: 3.2 m a year in the wettest such
  cell on the preview mesh, 6.5 m at twice the detail, 13 m on the standard mesh. The seeded
  continents end in cliffs, which no real coast does. Spreading that rain over a set distance
  inland is left for the upgrade of Moisture (step 5).
* **The wet zone before a long, high wall is probably too wet.** About a third of the vapour
  held back by a wall 2.5 km high rains within 500 km of it. [MEASURED; the judgment INFERRED]
* **The rain belt at the equator** brings 2,280 mm a year in its wettest band 10° wide. The
  driest land bands lie at 24° north and south, with 148 and 75 mm.
* **Deep basins that the sea did not reach stay dry**, by the design's rule. About 4 % of the
  land lies below sea level. Lakes come in step 2.
* The plates are a snapshot: ocean-floor ages are read off distances, not lived through.

## 8. Sources opened during the build

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

## 9. Next

Build step 2 (Drainage and Hydrology: rivers, lakes, and water given back to the air by land).
Before it, on the target machine: fetch the Earth reference data and run the Earth-pattern tests
that step 1 could not. Then the first refinement I would propose is the spreading of heat in
EnergyBalance, tested against Earth's seasons.
