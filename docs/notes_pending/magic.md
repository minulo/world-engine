## Magic: an invented layer

A new label for these notes: **[INVENTED]** a rule of the fantasy layer: made up, not a claim about any real world.
Every constant and every rule below that belongs to the layer carries it. Nothing invented is offered as physics: each
"why" answer about mana begins "By the invented rules of the magic layer", each of its fields says "Invented" in its
description, and the viewer says so above a world that has the layer.

The owner asked for "one for magic. For mana. Make up physics as well." The layer is off unless asked for, and runs
through the engine's own machinery: two processes on the climate clock, their constants in YAML, a steady state solved
as one sparse linear system as EnergyBalance solves for heat, drivers and sentence patterns for the "why" walk, the
store, the server and the viewer.

### What was built

- **The switch.** A fantasy layer is a file of `data/fantasy/`: `magic.yaml` says what the layer is and what it adds to
  which parameter files (models, fields, tables, explanations; its schema is `data/schemas/fantasy.yaml`).
  `Parameters(data_dir, fantasy=("magic",))` lays it over the files when asked, and only then. A layer only adds: an
  entry it names that the files hold already must be a map on both sides, and anything else is refused ("the fantasy
  layer would change this entry ... a fantasy layer only adds to them"). So is an unknown layer, a layer named twice
  and a layer that adds to a file that is not a parameter file. The layer's name goes into the merged models.yaml
  under `fantasy`, and the merged files keep their text, so a world store's own copy of its parameters says which
  layers made it, and `engine_for_store` rebuilds the same engine. `Engine(..., fantasy=...)`,
  `Harness(..., fantasy=...)`, `python -m worldengine build|order --fantasy magic`, `scripts/run.sh --fantasy magic`
  and `scripts\run.cmd -Fantasy magic` pass it on; the launchers then name the world `worlds/first-magic.zarr` (or
  `worlds/<profile>[-seedN]-magic.zarr`). The world's meta holds `"fantasy": ["magic"]`; a world without the layer
  holds no such key.
- **Mana** (`processes/mana_thaumic_spreading.py`, standing Invented). It writes `mana_density`, `mana_source`,
  `frozen_mana`, `ley_flow`, the table of `wellsprings`, and `spent_mana_heat`, its member of the group
  `surface_heat_flux`. Its arithmetic is in `library/mana.py` (the WIP branch's first file, kept in part: the edge
  conductances in series, the spreading matrix, the flow through a cell and the local peaks; new are the conductance of
  river reaches and the climb to the peak of a density; the upwind and downstream hand-on, the meeting of streams and
  the nearest other plate are dropped, because the layer spreads by diffusion alone and Tectonics already gives the
  distance to the nearest boundary).
- **Aura** (`processes/aura_thresholds.py`, standing Invented). It writes `wild_magic` and `aura`.
- **Explaining and showing.** Drivers for every field of the layer and sentence patterns for each (section "Thaumic
  theory" says which). `tools/why_scan.py` reads the layer's fields where a world has them, with rules of their own:
  the parts of a sum add up to the value, the frozen mana, wild magic and class named are the stored ones, a wellspring
  is one that the table lists, the sea is called sea, no heat is said where none is given, and every answer about a
  field of the layer says that its rule is invented. Two optional keys of fields.yaml, new in its schema: `display`
  names the viewer's colour map of a number (`aether`, `wild`, new in `viewer/viewer.js`, with `scale: log` for the
  frozen mana) and `colors` gives the colours of a category's classes (the aura's: grey dead zones, slate
  faint, blue steady, violet strong, gold wellsprings, red wild). The server hands both on; the default files use
  neither, so a world without the layer is stored as before.
- **The control panel.** A box "Magic (invented physics)" under Settings (`panel/world_engine_panel.py`). Ticking it
  moves the default world to `worlds/first-magic.zarr` (clearing it moves it back; a world of one's own choosing
  stays), keeps the choice in `.worldengine/panel.json`, and Start passes `--fantasy magic` (`-Fantasy magic`) to the
  launcher (`panel/control.py`: `launcher_command(..., fantasy=)`, `world_for_magic`, `Controller.magic`).
- **Tests.** `tests/test_magic.py` (19 tests) and one in `tests/test_panel.py`. `tests/test_contract.py` now applies
  the contract to the slots a fantasy layer adds as well.

### Thaumic theory [INVENTED, all of it]

Mana is a substance of the ground and of the water on it, measured in thaums. Its density M (thaum/km²) in each cell
is the yearly steady state of

    (λ + k_ice·c + k_life·v + k_sea·σ) M − ∇·(K ∇M) = s_motion + s_fire + s_old + s_life + s_storm
    F = k_ice·c·M / λ_frozen

with c the yearly mean of `snow_ice_cover`, v that of `vegetation_cover` (land only), σ = 1 on sea cells and 0 on land,
and F the frozen mana (thaum/km²). The five sources, in thaum/km²/yr:

| Source | Rule | Reads |
|---|---|---|
| Plates closing or parting | 15 × \|convergence_rate\| / (0.05 m/yr) × exp(−d / 150 km), d the distance to the nearest boundary | `convergence_rate`, `boundary_distance` |
| Volcanic fire | 25 × volcanism | `volcanism` |
| Old ground | 2 × (1 − exp(−age / 100 My)) on continental crust, a slow seep from old stable ground | `surface_age`, `crust_type` |
| Living land | 8 × v: living land breathes mana out in proportion to its cover of plants | `vegetation_cover` |
| Storms | 0.3 × (storm tracks / 1 e-folding + cyclone genesis potential / 4) | `storm_track_density`, `tc_genesis_potential` |

The losses, as shares of the free mana per year: decay into heat, λ = ln 2 / 12 yr; ice locks k_ice·c into frozen mana,
k_ice = 0.1, and frozen mana decays with a half-life of 120 years (λ_frozen = ln 2 / 120 yr); living land takes up
k_life·v, k_life = 0.02; salt water grounds k_sea = 0.25, spent as heat at sea. Spreading: K = 9,000 km²/yr on plain land, a spreading length √(K/λ) of 395 km;
near a plate boundary on land K is multiplied by 1 + 10 exp(−d / 150 km), so a boundary is a ley line along which mana
spreads 1,309 km; under salt water K is 5 % of plain land's and no ley line runs, a spreading length of 38 km with the
grounding; and running water carries mana: each river reach adds 9,000 × 20 × Q / (Q + 2,000 m³/s) km²/yr to the edge
from a land cell to the cell its water runs to (`flow_receiver`), Q the cell's yearly mean `river_discharge`.

What follows from the rules, and the choices made in them [INFERRED from the equations; the books, the sum of the parts
and the aura's rules are held by tests]:

- **The books balance.** Spreading moves mana and makes none, so at the steady state the mana made equals the mana
  decayed, grounded, locked by ice (which then decays from the frozen store at the same rate) and taken up by life.
  With none of the last three, the total is the sources over λ.
- **The density is the sum of what each kind of source makes alone**, because the equation is linear. Those five
  parts are the drivers of `mana_density`, each with the cell its part peaks at, found by climbing it from the cell
  (always to the highest neighbour, while one is higher); the "why" walk goes on there to `mana_source`, whose drivers
  are the five sources, and from them to the plates (`convergence_rate`, `volcanism`), the age of the ground
  (`surface_age`, `crust_type`), the plants (`vegetation_cover`) and the storms (`storm_track_density`,
  `tc_genesis_potential`), and back through their own answers to planet parameters and seeded starts.
- **Yearly, not monthly.** A source that swings with the year by its own mean moves the density by k / √(k² + (2π per
  year)²) of the density's mean, k the cell's loss rate, in a cell without spreading: 0.9 % on bare land, 2.8 % under
  full ice and plants, at most 6 % at sea. So the yearly means of the monthly inputs stand for every month.
- **Diffusion only, no drift with the wind.** Mana belongs to the ground and the water on it. The rule keeps one
  symmetric system with one prepared solver for all five parts, makes the climb to a peak a fair answer to "where does
  this part come from", and leaves the rivers, not the air, as the one thing that carries mana along.
- **Ley flow** is what crosses a cell's sides each year, half the sum of the flows across its edges either way, over
  the cell's width √area (thaum/km/yr), so that the ley lines, which carry most, stand out. Its drivers are the kind of
  ground (plain land, plate boundary, river, both, sea: a boundary or a river counts where it at least doubles the
  conductivity) and how much better than plain land it conducts.
- **Wild magic** is where a steep fall of mana meets storms: 1 − exp(−(G / 0.35) × (W / 2)), G the size of the gradient
  of M (thaum/km² per km) and W the storminess of the sources' table. Its drivers are G and W.
- **Aura**, by the first rule that holds: wild where wild magic reaches 0.5; a wellspring where the table of wellsprings
  lists the cell (a cell that holds at least 150 thaum/km² and at least as much as each neighbour); strong from 100,
  steady from 50, faint from 20 thaum/km²; else a dead zone.
- **Spent mana warms the world.** What decays or is grounded, (λ + k_sea·σ) M + λ_frozen F, delivers ε times itself as
  heat (W/m²) to the surface through `surface_heat_flux`, with ε = 0 in the layer's file. The member is then exactly
  zero.

### Where the layer stands in the order, and why (a departure from the brief)

The brief asked that the layer stand where, with its feedback at 0, it cannot change the climate: in a stage after the
climate, or outside its loop. Neither lets the feedback act. A member of `surface_heat_flux` that EnergyBalance reads
must be worked out in the climate's rounds: a member worked out in a later stage is read as that stage last stored it,
and in one build the climate runs before a later stage has stored anything; a process outside the loop adds nothing
the loop reads [INFERRED from engine.py, `_group_value` and `_tail`]. So Mana stands inside the loop, after StormClimatology, and the
climate is kept unchanged another way, which the engine's own rules make exact:

1. Its member is ε × spent = 0.0 exactly at ε = 0, and the engine adds members to a zero array in order, so the sum
   that EnergyBalance reads, and the gap of the group that the settle test measures, are the same bits.
2. Nothing in the loop reads a field of the layer.
3. The layer writes no class into the loop: the aura, a class that the settle test would watch, is written by Aura,
   which nothing reads from the previous round and which the engine therefore runs once, after the climate has
   settled (the tail of build step 9).

[MEASURED, preview, seed 20261004] With the layer on and ε = 0, every one of the 138 fields and table columns of the
default world has the same fingerprint as without it, the climate settles after the same 41 rounds, and the order of the
other processes is unchanged. Without the layer the default world's fingerprint is 2c1ec14dd7744f7d before and after
this change.

The price: Mana reads the storm maps, so StormClimatology, which ran once after the loop, now runs in every round. On the
preview mesh StormClimatology took 19.8 s instead of 1.2 s, and Mana 3.6 s, so the build took 125 s against 104 to
107 s without the layer, 17 to 21 % longer, and passed the preview profile's limit of 120 s, which the world's notices
say [MEASURED, two builds of each, lowered in priority on a shared 4-core machine]. The standard mesh was not built
with the layer.

### Conditions

| Condition | Result |
|---|---|
| Off by default: the default world is unchanged | The default files are untouched; without the switch the parameter files load word for word, no slot of the layer exists, and the preview world's fingerprint is 2c1ec14dd7744f7d before and after [MEASURED]. `test_the_layer_is_off_by_default_and_only_adds_when_asked` |
| On, with its feedback at 0, the rest of the world is unchanged | Every field of the default preview world, bit for bit, the same 41 rounds [MEASURED]; the same on a small world of 2,562 cells in every test run (`test_with_the_layer_on_and_its_feedback_at_zero_the_world_is_the_same_bit_for_bit`) |
| Conservation at the steady state | Mana made = mana decayed, grounded, locked and taken up, within 1e-5, and the total = sources / λ without ice, life and sea; the frozen store is steady too. On the default world the books close to 1.000000 [MEASURED] |
| Salt water lowers the flow across a sea | Across a strait of about 1,100 km, the flow at its middle and on the far shore falls below 1 % of what crosses the same ground as land; the density on the far shore below 2 %; with the grounding off, the low conductivity alone keeps it below 20 % |
| Ice holds mana | Under a polar cap of full ice the free mana falls below half that of bare ground, and free plus frozen mana is more than 3 times what the bare ground held |
| A river carries mana further than plain land | About 1,800 km down a river of 20,000 m³/s the density from a fire at its head is more than 10 times that without the river, and more than 5 times that off the river as far from the fire |
| Plate boundaries on land are ley lines | 2,000 km along the boundary from a fire, more than 5 times the density without the boundary; 1,500 km across it, less than 1.5 times |
| Drivers add up | The five parts of `mana_density` add up to it and the five sources to `mana_source` (relative 1e-5); each part's named cell holds at least as much of the part; each wellspring's cause is its largest part, its share that part's |
| Determinism | The same inputs give the same fields, table and drivers bit for bit, in one harness and in a new one |
| Feedback above 0 warms where mana decays | Alone, EnergyBalance given the member warms every cell, and the tenth of cells given most heat by more than 1.5 times the half given least. In a built small world with ε = 0.5 the planet warms, and the tenth of cells with most heat warms by more than 0.1 K beyond the half with least |
| End to end, with its "why" answers | A small magic world is built, stored and read back; its meta and its store's parameters name the layer; `engine_for_store` rebuilds Mana and Aura; why_scan's rules find no problem in the layer's answers on every fifth cell; the answer at the strongest wellspring reaches its sources and their causes |
| why_scan on the default world with the layer | Every cell, the 7 fields of the layer: 71,694 answers; and `python tools/why_scan.py STORE --every 7`, every seventh cell and all 29 fields it reads: 42,456 answers. In neither does an answer say anything its numbers contradict [MEASURED] |
| The panel | The box names its world, keeps its choice and passes the layer to the launcher (`tests/test_panel.py`) |

Each condition of the rules was seen to fail when its rule was taken out (the conductivity and the grounding of the sea
set to land's, the locking by ice, the river and boundary gains set to 0) [MEASURED].

### Measured on the default world with the layer (preview, seed 20261004, ε = 0) [MEASURED]

- **Total mana**: 1.68e10 thaum free and 2.01e10 thaum frozen; 3.15e9 thaum are made each year. Of what is made, 63.3 %
  is grounded at sea, 30.8 % decays, 3.7 % is locked by ice (and decays from the frozen store) and 2.2 % is taken up by
  life. Land holds 52.5 % of the free mana on 27.7 % of the surface; 27.9 % of the mana is made on land.
- **What makes it**: volcanic fire 45.7 % of what is made (36.0 % of the density), plates closing or parting 28.5 %
  (22.1 %), living land 12.0 % (24.7 %), storms 8.8 % (8.7 %), old ground 5.0 % (8.5 %). Life and old ground make more
  of the density than of the sources because they lie inland, where nothing grounds their mana [INFERRED: the
  grounding at sea is the largest loss, and fire and plates lie mostly at sea or on coasts].
- **Density**: on land a median of 60.9 thaum/km² (tenth and ninetieth percentiles 24.4 and 100.9, at most 238.4); at
  sea a median of 5.2 (1.8 and 90.1, at most 148.4).
- **Aura, share of the land**: dead zone 7.4 %, faint 26.9 %, steady 55.5 %, strong 9.4 %, wellspring 0.6 %, wild 0.2 %.
  At sea: dead zone 72.8 %, faint 9.3 %, steady 7.4 %, strong 6.2 %, wild 4.5 %. Over the planet wild magic covers
  3.3 %: of its 345 cells 338 are sea, 320 lie on or beside a cell of volcanism above 0.3, where the density falls
  steeply into the grounding sea, and 203 where the cyclone potential is above 1.
- **Ley flow**: the median cell of a plate boundary on land carries 1,627 thaum/km/yr, of a river 650, of both 2,079,
  of plain land 268 and of the sea 15. Of the tenth of land cells that carry most, 274 of 283 lie on a ley line. On
  the preview mesh the rivers are many (a reach counts where it at least doubles the conductivity, from about
  105 m³/s: 1,671 of the 2,829 land cells), so the flow shows as bands along the boundaries and the river networks rather
  than as thin lines.
- **Wellsprings**: 17, all on land. The strongest:

| | Place | Density (thaum/km²) | Cause (share of the density) | Biome |
|---|---|---|---|---|
| 1 | 21.7° S, 106.7° E | 238.4 | plates closing or parting (0.64) | tropical dry forest and savanna |
| 2 | 18.1° N, 13.5° E | 227.2 | volcanic fire (0.68) | tropical dry forest and savanna |
| 3 | 17.6° S, 59.1° E | 226.1 | volcanic fire (0.65) | xerophytic woods and scrub |
| 4 | 25.9° S, 3.9° W | 189.0 | volcanic fire (0.57) | xerophytic woods and scrub |
| 5 | 24.8° S, 89.2° W | 183.9 | volcanic fire (0.57) | xerophytic woods and scrub |
| 6 | 11.8° S, 158.0° E | 183.4 | volcanic fire (0.46) | semi-desert |
| 7 | 1.7° S, 172.1° E | 161.9 | volcanic fire (0.36) | warm mixed forest |

  Of the 17, 15 are fire's and 2 the plates'.
- **With the feedback on** (ε = 0.5 W/m² per thaum/km²/yr, a world built for the measurement only): spent mana delivers
  3.08 W/m² on the planet's mean, at most 22.9 W/m²; the planet warms by 1.90 K on the year's mean (land 2.05 K, sea
  1.84 K); the tenth of cells given most heat warms by 2.10 K, the half given least by 1.75 K; the climate settles in
  39 rounds instead of 41, and 91 of the 138 fields and table columns of the world without the layer keep their
  fingerprints: those of the setup and the geological history, the sunlight, the label field and the columns of the
  table of lakes that name hollows and cells. The warmer world holds 3.3 % more free mana.

A viewer screenshot of the default world with the layer is in the session's scratchpad (`magic_shots/`), not in the
repository.

### Departures and limits

1. **The layer stands in the climate's loop**, not after it (above). Its guarantee that a feedback of 0 changes nothing
   rests on exact arithmetic and on the engine's rules for the tail, and it is held by a test that builds a whole small
   world; a change to how the engine adds the members of a group, or to what its settle test watches, must keep it.
2. **"Salt water grounds mana" is two rules**: the sea conducts at 5 % of land's rate, as the brief said, and it also
   takes 0.25 of its mana a year, spent as heat. With low conductivity alone, and ley lines running under the sea, the
   first trial put all 83 of its wellsprings at sea, 81 of them fire's, on the mid-ocean ridges, where volcanism is high
   and the sea held the mana in place, and 20 % of the sea was wild [MEASURED, first trial, superseded]. The grounding and the rule that no ley line
   runs under salt water leave the seas as dead zones and the wellsprings on land.
3. **The constants were set by eye** on the default preview world, after that trial: the sources of fire, plates, old
   ground and life were raised from 15, 10, 1.5 and 4 and that of storms lowered from 0.6, so that storms are no longer a
   near-even background of a quarter of the density; the aura's thresholds were placed so that the land shows every class.
   They are [INVENTED]; on another planet the shares of the auras will differ, because the thresholds are amounts, not
   shares.
4. **Storm mana uses StormClimatology's maps**, which brings StormClimatology into the loop (17 to 21 % longer on the
   preview mesh). Circulation's storm growth rate, already in the loop, would have been cheaper but is not what the brief named.
5. **The climb to a part's peak** follows a smooth part a long way: the storms' part climbs a median 1,440 km, a tenth
   of the cells over 3,600 km, and from 75.3° N, 40.6° E it climbs 4,600 km [MEASURED]. The sentence says "highest, up its
   slope from here, at", not "nearby".
6. **On the preview mesh a ley line is one cell wide** (cells about 220 km apart), and the spreading length of plain
   land is under two cells; the same constants on the standard mesh give finer lines of the same lengths [INFERRED: the
   constants are lengths and rates, not counts of cells; not built].
7. **Grounded mana counts as spent**: with the feedback on it warms the sea it is grounded in, which is most of the heat.
8. Not done: the standard mesh with the layer; `tools/refusal_audit.py` (a quarter of an hour), so whether the new
   refusals are each held by a test was checked by hand only (`tests/test_magic.py` raises each of them).
