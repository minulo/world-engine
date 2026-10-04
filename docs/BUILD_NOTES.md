# Build notes

State of the build on 2026-10-04, after build steps 0 and 1 of the design document
"World engine design: physical causes, replaceable processes".

Labels: **[MEASURED]** I ran it in the build environment and read the number. **[DOCUMENTED]** I opened
the source during the build. **[INFERRED]** my reasoning. **[UNVERIFIED]** recalled, not checked.
**[PROVISIONAL]** a first value that an Earth test must tune.

The build environment was a cloud workspace with 2 processor cores and 7 GB of memory, Python 3.13, and
the versions in `requirements.lock`. Nothing here was run on the target laptop.

## 1. What exists

| Build step | State | Evidence |
|---|---|---|
| 0. Skeleton | Done | 106 tests: mesh, parameter files, scheduler with every refusal, engine rounds, pushes, labels, store, server |
| 1. The slice | Done, with the gaps listed in section 4 | 75 further tests; two trials in `trials/results/` |
| 2 to 11 | Not started | |

`python -m pytest` runs 181 tests in about two minutes. [MEASURED: 1 min 48 s]

## 2. Step 0 against its "done when"

| Condition in the design | Result |
|---|---|
| Three toy processes with a loop, a modifier and a push reach a known steady answer | Pass. a = 7 and b = 8 to within 1e-5 after 52 rounds [MEASURED: `tests/test_engine.py`] |
| First-round defaults are tested | Pass. Round 1 reads the default of fields.yaml; round 2 reads the blended copy |
| Every refusal message is tested | Pass. 50 refusal cases of the scheduler, each checked for its message, plus the engine's own (`tests/test_scheduler.py`, `tests/test_engine.py`) |
| A world holding only geometry is identical on a second run | Pass, and identical in two fresh interpreters with different hash seeds |
| It opens in the viewer through the local server | Pass. Checked in a headless browser (`tools/viewer_check.py`) and by tests of the server's answers |

The scheduler is the routine of the design's check script, ported with its messages. It gives the
design's order for all 22 declarations and for the slice. [MEASURED: `tests/test_scheduler.py`,
which holds the design's declarations as test data]

The mesh: cell areas add up to the sphere to 12 digits; the largest cell has 1.36 times the area
of the smallest, at every level from 5 to 7. [MEASURED] The design left that number open.

## 3. Step 1 against its "done when"

| Condition in the design | Result |
|---|---|
| Each process meets the fixed pass conditions of its first version | Pass for the conditions that need no Earth data (section 3.1). The conditions that feed a process real inputs are not run: section 4 |
| Its tolerance is recorded | Not done. A tolerance is a misfit against Earth data, and there is no Earth data yet |
| The two patterns the first version cannot show are measured and recorded as failures | Not measured against ERA5. What the engine's own world shows: no wind reverses with the season, and the sinking air is the same at every longitude |
| The crust trial meets conditions fixed before it runs | Pass at both mesh sizes (section 3.2) |
| explain() returns a chain | Pass |
| The frozen-region example works in reduced form | Pass (section 3.4) |
| A place label alone changes no other field | Pass: every other field keeps its fingerprint |
| Both poles are colder than the equator and below freezing in the yearly mean, and the Albedo slice marks ice at both | Pass (section 3.3) |
| Run times are measured for the preview and standard profiles | Done (section 3.5) |
| The viewer shows any stored field on the globe or a flat map, plays the months, and on a click shows the cell's values and its "why" answer, with a notice when the climate did not settle or a model ran outside its range | Done. Checked in a headless browser |

### 3.1 Pass conditions, on the default world (preview mesh, seed 20261004)

All [MEASURED] by `tests/test_world.py` and `tests/test_processes.py`.

| Process | Fixed pass condition | Result |
|---|---|---|
| PlanetGeometry | Areas total 510.1 million km²; Coriolis parameter 1.03e-4 per second at 45° | 510.06; 1.031e-4 |
| Tectonics | Two plates moving apart make floor that is youngest where they part; closing continents thicken the crust on both sides; one seed gives the same plates at two mesh levels | Pass |
| Isostasy | Depth 2,500 m at age zero and 2,500 + 350 √age for young floor; 15 % of added thickness becomes height | Pass |
| SeaLevel | In a flat basin the level is volume over floor area; water spills over a rim, and two hollows merge; low ground behind a barrier stays dry and the barrier is named; the sea holds the planet's water | Pass; the volume is held to 1 part in 10,000 |
| Insolation | Equator at an equinox gets star output ÷ π; polar day and night at a solstice; the global mean is a quarter of the star output | Pass |
| Albedo | With cloud and low-sun terms at zero, each surface returns its table value; ice-covered cells reflect 0.62 | Pass |
| EnergyBalance | Without spreading, the yearly mean is (absorbed sunlight − A) ÷ B; colder toward the poles; a larger swing inland than over sea; 6.5 K per km of height | Pass |
| Circulation | On an all-ocean planet each month in the north mirrors the south half a year later; trade winds from the east, westerlies in mid-latitudes, high pressure near 30°; as much air sinks as rises | Pass |
| Moisture | One ridge across a steady wind: wet on the side facing the wind, dry on the sheltered side; evaporation equals precipitation over the globe; the driest land band between the equator and 60° lies between 15° and 40° | Pass: the windward side gets 2.9 times the rain of the lee; E/P = 1.0000006; driest land bands at 24° N and 29° S |
| Biomes | Twelve months at 26 °C with 300 mm each give tropical rainforest and class Af; a warmest month below freezing gives ice and no plant cover; seven further classes follow the published rules | Pass |

### 3.2 The crust trial (Question 16)

`trials/crust_points_trial.py`. A bare model of moving plates: points turn with their plates for
125 rounds of 2 My; a point that meets a point of another plate with priority is consumed; a cell
with no point nearby becomes new ocean floor; the crust is drawn onto the mesh every round and the
points are resampled every 20 rounds. The three conditions were written before the first run.

| Condition | Limit | Preview mesh | Standard mesh |
|---|---|---|---|
| A marked patch lies within one cell of where its plate's motion puts it | 1 cell | 0.13 cell, after travelling 39 cells | 0.04 cell, after travelling 148 cells |
| Continental area changed beyond what closing plates destroyed | 2 % | 0.8 % | 0.2 % |
| Cells that switch crust type and switch back within three rounds | 1 % of cells per round | 0.09 % | 0.11 % |

All [MEASURED]. Resampling every 10 and every 60 rounds also passes at both sizes; the worst case
is an area change of 1.8 % on the preview mesh when resampling every 10 rounds.

What the trial does not show. The bare rule lets continents overrun each other, and 45 % of the
continental crust was consumed in 250 My. [MEASURED] The full plate model of step 3 thickens crust
in a collision and slows the plates; nothing here tests that. The trial tests the storage of crust
on moving points and the drawing onto the mesh, which was the risk the design named. It passed, so
the crust stays on the points. [INFERRED]

### 3.3 Cold poles

The requirement added when the design was approved. Nothing in the engine places cold.

* Yearly sunlight at each pole is 41.5 % of the equator's at a tilt of 23.44°. [MEASURED: test]
* Yearly mean temperature of the pole cells of the default world: −17.8 °C (north) and −18.5 °C
  (south); every month is below −16 °C. The equator averages +27 °C. [MEASURED]
* Albedo marks ice at both pole cells in every month, and the biome there is ice. [MEASURED]
* A second seed gives cold poles too. A planet tilted 60° is still built; the world store then
  names EnergyBalance as outside its range, and the pole gets more yearly sunlight than the
  equator, as the formula says. [MEASURED: tests]

### 3.4 Pushes

`data/examples/frozen_region.yaml` on the default world: the order becomes Albedo, Insolation,
EnergyBalance, **push: cap**, Circulation, Moisture, Biomes, as the design's table shows. At the
centre the plain world has 3.5 to 7.3 °C; the heat sink alone brings the year to 0.2 °C; the cap
holds every month at −5 °C; the biome becomes ice; the fields of the geological stage keep their
fingerprints. The "why" answer names the entry, its reason, "not physical", the heat sink of
−120 W/m² and the value before the cap. [MEASURED: test] The third push of the design's example,
on the day's temperature, waits for the weather stage of step 8.

`data/examples/place_label.yaml`: the label changes no other field. On the default preview world
its region holds no forest, so the entry touches nothing and the world store says so; the test
accepts either outcome and checks the fingerprints in both. [MEASURED]

### 3.5 Run times and the cost of a climate round

All [MEASURED] on the 2-core build environment; the laptop is not timed.

| Profile | Cells | Whole build | Climate rounds | One later round | Preparing the heat solver |
|---|---|---|---|---|---|
| preview | 10,242 | 12.5 s | 17 | 0.63 s | 0.3 s |
| standard | 163,842 | 233 s | 17 | 10.5 s | 27 s |

In a standard round Moisture takes 7.5 s, Circulation 2.1 s, EnergyBalance 0.5 s, Biomes 0.35 s.
The heat solver is prepared once for a climate run, as the design chose. Preparing it takes 27 s
and not the 5 s of the design's probe, because the repeating year is solved as a yearly mean plus
two waves in time, and each wave is a system of its own in complex numbers. Memory at the standard
size was 3.2 GB when I looked during the run, and the world store takes 183 MB on disk (14 MB at
the preview size). [MEASURED] The high_fidelity profile was not run.

## 4. What is not done, and why

1. **No test against Earth data.** The build environment reaches package registries and GitHub
   only, so ETOPO, ERA5 and the other reference data of Layer 9 could not be fetched, and ERA5
   needs an account. Every "Earth pattern" and the "Earth twin" are therefore untested. No
   tolerance is recorded. The pass conditions above are the fixed ones, checked on the engine's
   own world or on inputs built for the purpose. This is the largest gap of step 1.
2. **Isostasy's reference level is not tuned on Earth.** `reference_offset_m` is set so that the
   default world's sea rests near the reference level (within 40 m at the standard size). The
   design asks for a tuning on Earth's crust thickness and floor ages. [PROVISIONAL]
3. **The label on a finished world.** The design says a label entry can be applied to a finished
   world in one pass. That command is not built; a label is applied by building the world.
4. **The viewer reads the store through the server.** The design mentions a Zarr reader in the
   page. The page asks the local server for arrays instead, and the server reads the Zarr store.
   The store is unchanged by this, and the page holds no third-party code.
5. **history_length_my is one round.** The first Tectonics is a single snapshot, so a history of
   125 identical rounds would only cost time. The designed default of 250 My returns in step 3.
6. **Snapshots of the history, the rerun of the climate inside the history, the weather clock and
   the clock that steps through dates** are not built. The engine refuses them with the build step
   that brings them. The scheduler already orders and checks them.

## 5. Departures from the approved design

Each is recorded in the design document as well.

1. **The rain rule.** The design named the UVic model's rule: rain where humidity exceeds 85 %.
   With that rule no rain fell anywhere in the trade-wind belts: yearly rain between 10° and 40°
   was 4 to 15 mm, land and sea alike, and 69 % of the land got under 250 mm. [MEASURED] The cause:
   air in the trades is carried toward the equator before its humidity reaches the threshold. Rain
   now rises smoothly with the humidity of the column, P = exp(a (r − r0)), the form Bretherton,
   Peters and Back 2004 fitted over tropical seas. [DOCUMENTED for the form; the two numbers,
   11.4 and 0.522, are UNVERIFIED: the paper's page did not return them and I recalled them.]
   Outside the tropics the rate is scaled by how much vapour the air can hold. [INFERRED: mine]
2. **Three constants of Moisture and Circulation are calibrated by hand** to the engine's own
   world, not to Earth: the drag (so that trade winds blow about 5 m/s westward and 2 m/s
   equatorward), the share of the surface wind that carries vapour (0.5), and the stirring of
   vapour (3 million m²/s). [PROVISIONAL]
3. **Tectonics keeps its seeded start in tables**, as the full version will, where the design's
   check 8 declared the slice version without them. The order is the same.
4. **The vapour budget is solved by sweeps on a ladder of meshes** (the multigrid method), a
   method that repeats until it is close enough. The design's rule names one direct solver for
   large systems. The sweeps run on one thread in a fixed order and give the same bits each time
   [MEASURED: the two-interpreter test], and a direct solve of twelve systems a round would have
   cost about a minute a round at the standard size. [INFERRED from the 5 s per system measured]
5. **Albedo's low-sun term and ice value** now come from North, Cahalan and Coakley 1981
   (equation 18: 0.202 times the second Legendre polynomial; 0.62 over ice). [DOCUMENTED] The
   surface table and the cloud share stay a rule of mine. The search promised under Question 15
   found no simple published table by surface type.
6. **Sea that stays frozen all year is shown as the biome "ice"**, so that the polar caps are
   visible on the biome map. The design's rule spoke of land.

## 6. What the first world looks like, and where it is wrong

Default world, standard mesh. [MEASURED unless marked]

* Land 28 % of the surface, sea 72 %; mean sea depth 3,630 m; mean land height 770 m; highest
  ground 5,900 m. Earth: 29 %, 3,690 m, about 840 m. [Earth figures UNVERIFIED except the depth]
* Global mean temperature 11.5 °C against about 14 to 15 °C on Earth. [Earth figure UNVERIFIED]
  The poles average −18.4 °C (north) and −18.8 °C (south), the equator +27.1 °C.
* **The seasons are too weak.** Land between 40° and 60° swings 6.5 °C either side of its yearly
  mean, sea 2.3 °C. The energy balance model spreads heat over 3,500 km, and this world's
  continents are small, so the sea damps them. One consequence: almost no cold-winter (D)
  climates, and tundra or ice where Earth has boreal forest.
* **The land is too dry.** Yearly rain is 915 mm over the globe and 890 mm over land on average,
  but 57 % of the land gets under 250 mm. By the Köppen rules 39 % of the land is desert (BW),
  11 % steppe (BS), 35 % polar (tundra or ice), 7 % tropical, 6 % temperate and 2 % cold-winter.
  On Earth deserts are roughly a seventh of the land and polar climates an eighth. [Earth figures
  UNVERIFIED: recalled from Peel et al. 2007] Two causes, both expected by the design: land gives
  no water back to the air until Hydrology exists (step 2), and nothing in the first Circulation
  makes a monsoon (step 5).
* **The rain belt at the equator is too narrow and too strong:** 5,100 mm a year in the wettest
  band 10° wide, against roughly 2,000 mm on Earth. [Earth figure UNVERIFIED] The driest land
  bands lie at 24° north and 24° south, with 137 and 86 mm a year.
* **Sea ice reaches too far** (about 13 % of the surface stays frozen all year), because the model
  ignores sea ice as a lid on the sea and so gives polar seas almost no summer.
* **Deep basins that the sea did not reach stay dry**, by the design's rule. About 8 % of the
  land lies below sea level. Lakes come in step 2.
* The plates are a snapshot: ocean-floor ages are read off distances, not lived through.

## 7. Sources opened during the build

| Source | Used for | How I checked it |
|---|---|---|
| North, Cahalan, Coakley 1981 (already in the design) | Co-albedo 0.681 − 0.202 P2, ice co-albedo 0.38, heat capacities of 0.16 B and 4.7 B years | Opened; values returned by the fetch tool with page numbers |
| Peel, Finlayson, McMahon 2007, Hydrol. Earth Syst. Sci. 11, 1633 | Every rule of the climate classes | Opened |
| Beck et al. 2018 (already in the design) | Arid classes take precedence | Opened; the table itself was not returned |
| Bretherton, Peters, Back 2004, J. Climate 17, 1517 | The form of the rain law | Opened; the fitted numbers were not returned |
| Ferreira et al. 2014, Icarus 243, 236 | The tilt above which poles get more yearly sunlight than the equator | Opened as a copy on an author's site |
| plotbiomes, an R package by V. Stefan (MIT licence) | The outlines of Whittaker's chart, digitised from Ricklefs 2008 | Cloned from GitHub and read |

## 8. Next

Build step 2 (Drainage and Hydrology: rivers, lakes, and water given back to the air by land).
Before it, on the target machine: fetch the Earth reference data and run the Earth-pattern tests
that step 1 could not.
