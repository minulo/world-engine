# Step 2 working notes (kept for resuming after a context summary)

User (2026-10-04 21:04): "I confirm, now, continue making progress."  -> crust stays on points (Q16 confirmed).
Device: Minh's Windows machine "permanent-kick" is linked, no connected folders. Do not write there unasked; offer at the end.

## Plan
1. Record Q16 confirmation in design doc + BUILD_NOTES.                         [ ]
2. Step 2: library/drainage (flow routing, hollows), Drainage process, tests.    [ ]
3. Step 2: Hydrology (bucket, Priestley-Taylor, snow, runoff, rivers, lakes).    [ ]
4. World tests, explanations.yaml, viewer (rivers), re-measure both meshes.      [ ]
5. Earth reference data: fetch tool (git clone of public repos), mesh conversion,
   Earth tests (SeaLevel, Drainage, Hydrology, Koppen shares, GPCP land rain by
   latitude), Earth twin (Isostasy slot replaced by ReliefFromFile).             [ ]
6. Independent review of step 2, fixes, notes, design doc, project note, deliver.[ ]

## Design declarations (tests/design_declarations.py)
Drainage (geological): reads elevation, ocean_mask, cell_area;
  writes flow_receiver, drainage_area, basin_id, depression_id, spill_elevation, slope.
Hydrology (climate): reads precipitation, snowfall, surface_temperature, insolation, albedo, elevation,
  flow_receiver, depression_id, spill_elevation, cell_area, ocean_mask; lagged soil_water_capacity (Soils, step 7:
  not yet), vegetation_cover; writes potential_evapotranspiration, soil_moisture, snow_water, runoff, runoff_annual,
  river_discharge, lake_fraction, lake_level, table:lakes; adds evapotranspiration to group moisture_source.
Field dictionary: depression_id "zero if it drains to the sea"; lakes table "outlet cell, area, volume, whether it overflows".
Why answers: "Local rain against water arriving from upstream; melt against rain; why a lake is closed or open".
Tests (Layer 9): cone drains to foot; every land cell reaches sea or closed hollow; drained areas add up to land area;
  one basin uniform rain: outlet flow = (rain - evaporation) * area; water in = water out for every basin.
  Earth: Amazon -> Atlantic, Nile -> Mediterranean, central Asia + Great Basin closed; Amazon carries most water; Caspian closed.

## Earth data reachable by git clone (GitHub public repos)
- NCAR/GeoCAT-datafiles: binary_files/ETOPO5.DAT (5 arc-min relief), netcdf_files/V22_GPCP.1979-2010.nc (precip),
  absolute.nc (CRU abs. temperature?), T2M_ERAINT..., tas_mon_1961-1990..., slp.mon.mean.nc, landsea.nc, xieArkin-T42.nc ...
  WARNING: never `git ls-tree -l` on a blobless clone (fetches every blob). Clone is in scratchpad/earth/ (975 MB partial).
- matplotlib/basemap: doc/examples/etopo20data.gz (+lats, lons): 20 arc-min relief.
- cran/oce: data/topoWorld.rda; cran/ocedata: levitus.rda.

## Decisions taken while building (keep; they are not in the repository yet until coded)
D1. Drainage reads elevation, ocean_mask, sea_depth, cell_area, table:seas. Sea surface of a sea cell = the level of the
    nearest row of table:seas (exact float64 of the pour), so land at exactly sea level ties with the sea and drains to it.
D2. Drainage writes flow_receiver (-1 sea/bottom), drainage_area and basin_id "with every hollow full" (bottoms of all
    leaves of a top hollow -> spill_into_cell of the top; basin_id = last land cell before the sea; sea cells: basin -1,
    area = land draining straight into them), depression_id = leaf row of table:hollows (0 = drains to sea),
    spill_elevation = leaf's pass (missing for 0), slope = drop/distance to receiver (0 if none), table:hollows.
    Departure from design: depression hierarchy (Barnes, Callaghan, Wickert 2020) instead of Priority-Flood (2014).
D3. New slot Soils with a stub (UniformSoil: every soil holds 150 mm, Manabe) writing soil_water_capacity, so Hydrology
    reads it lagged as designed and step 7 replaces the stub without touching Hydrology.
D4. Hydrology reads precipitation, snowfall, surface_temperature, insolation, albedo, elevation, height_above_sea,
    flow_receiver, depression_id, cell_area, ocean_mask, table:hollows; lagged soil_water_capacity. NOT vegetation_cover.
    Writes potential_evapotranspiration, soil_moisture, snow_water, runoff, runoff_annual, river_discharge, lake_fraction,
    lake_level, table:lakes; adds evapotranspiration to moisture_source.
D5. Snow: exact periodic store by composing monthly clamp maps (C, lo, hi); start = hi if C > 0 else lo; cap (limit) in
    models.yaml; excess over cap leaves as ice = runoff in the same month. Albedo then reads lagged snow_water
    (cover = min(1, store / full_cover_mm)); settle entry moves from snowfall to snow_water.
D6. Bucket: W capped at capacity C; beta = min(1, W / (0.75 C)); 10 sub-steps a month, exact exponential step below the
    critical level; years repeated until the January store repeats (tolerance), Aitken jump after years 2 and 5; note if not.
D7. PET = (1 + 0.26) * s/(s+gamma) * max(Rn, 0) / (rho_w * Lv); Rn = k_s * Q * (1 - albedo) - (b + (1-b) Sf)(A - T_C).
    k_s (share of absorbed sunlight absorbed at the surface, Trenberth et al. 2009: 161/239) MUST BE OPENED before use.
D8. Lakes: capacity of a cell x = sum_m (PET - ET_land) * area; cells of equal height in a hollow flood together (same
    fraction); nodes settled in post-order, trees in reverse link order, add(leaf, w, upto) as in the summary; lake unit =
    maximal node whose children are full; monthly outflow of a unit = (annual out / annual in) * monthly inflow, put in
    at spill_into_cell; evapotranspiration = (1-f) ET_land + f PET; runoff field = (1-f) runoff_land.
D9. Why answers: runoff = from_rain + from_snowmelt + from_ice (sum); river_discharge = local + from_upstream with the
    driver wettest_source (cell); lake_fraction: driver state (names) + row of table:lakes.
D10. Tests go to a new file tests/test_water.py. Earth data tests in tests/test_earth.py (skip without reference_data/).

## State (update as work proceeds)
CODED (uncommitted, in /home/claude/world-engine):
- library/drainage.py (receivers, flow_stack, accumulate, terminal, hollows, owners, top_hollows, overflow_receivers,
  mouths, largest_upstream, drainage_surface with sea levels snapped to table:seas)
- processes/drainage_lowest_neighbour.py (slot Drainage), tests/test_water.py (19 tests pass: library + Drainage)
- library/snow.py REWRITTEN: snow_year(snowfall, melt, ice_after_years): seasonal = clamp year from bare ground twice;
  perennial (gain > 0) = store holds ice_after_years (=1) of net gain + seasonal path, export gain/12 each month. No jump.
  (First tried a depth limit of 3000 mm: one cell tipping -> mean gap 0.29 -> 3 more rounds each; 4 such jumps seen.)
- library/soil_water.py (bucket_year, bucket_repeating), library/evaporation.py (Priestley-Taylor pieces),
  library/lakes.py (tree_order, settle, lake_units, flooded, lake_flows)
- processes/hydrology_bucket_lakes.py (slot Hydrology), processes/soils_uniform.py (slot Soils, stub 150 mm)
- Albedo now reads lagged snow_water (constant snow_full_cover_mm); snowfall lost its settle entry.
- Engine: groups may carry `settle` (fields.py GroupSpec.settle, engine._gaps, schema); moisture_source {0.05, 1.0};
  snow_water settle {mean 0.05, cell 2.0}. causes.py: unit km2_from_m2; floats of table rows formatted.
- data: fields.yaml (+12 fields), tables.yaml (hollows, lakes), models.yaml (Drainage, Hydrology, Soils; Albedo consts),
  explanations.yaml (Drainage, Hydrology, Soils).
MEASURED preview (p5.zarr, 22 rounds, 48 s): land rain 609 mm (was ~300), ET 436, PET 849, runoff 187, ET/P 0.716;
  rivers to sea = land P - ET exactly; 20 lakes, 9.1 % of land flooded (two giant full hollows 7.6 and 3.6 M km2: no
  erosion yet), 46.8 % of land drains into hollows; loop convergence ratio ~0.82 per round (recycling gain ~0.74).
TODO next: tests for snow/bucket/PT/lakes/Hydrology (test_water.py), fix tests broken by the changes (test_world order
  test, Albedo tests in test_processes.py, contract), world tests, viewer, Earth data, review, docs, deliver.
Sources opened this session: Trenberth 2009 numbers via ClimaTalk + ETH ocean wiki (161 surface, 78 atmosphere, 102
  reflected, 341.3 in, 396 up, 333 back, 80 latent, 17 sensible); Davis et al. 2017 again via d-nb.info/1143531264/34.

## State at the Earth-test stage (nothing committed yet since a7b3fb0!)
DONE since last note:
- Bucket made exact per month (bucket_month), no steps_per_month constant. Empty soil where nothing arrives.
- Demand for water: SPLASH radiation (Davis 2017 eqs 10-13) with ONE sunshine fraction 0.62 (returns Earth's 161/341 absorbed and
  63 W/m2 net longwave: Trenberth 2009 via ClimaTalk + ETH wiki); ground reflects 0.17, lake water 0.07 (lake demand separate);
  demand counts only for the snow-free share (shared constant snow_full_cover_mm 15). Hydrology no longer reads albedo.
  (First version used 0.67 * Q * (1 - planetary albedo): gave Kazan PET 362 mm, Caspian 648: too low; replaced.)
- Lakes: HAIR relative threshold; overflow_receivers routes every bottom of a top hollow to its deepest bottom, then out
  (so a hollow that overflows straight into the sea is ONE basin named after its deepest cell).
- causes.py: says_zero / follows_zero for form sum; trailing colon fixed. Viewer: log scale, water map, index colours; server stats "top".
- Mutation runs ONLY on a copy (scratchpad/step2/mutate.py): 14/14 lakes+routing caught, 21/21 hydrology caught.
  (A killed run once left soil_water.py broken; restored and verified.)
- World tests: order test, water budget test, dry belt test RESTATED (low between two wetter belts, equatorward of 50;
  old form failed: 285 mm at 58N in lee of a 2-3 km range vs 339 mm at 24N), 5 new water-on-land world tests.
- Earth reference: tools/reference_data.yaml + tools/fetch_reference_data.py (HTTPS raw.githubusercontent, SHA-256),
  src/worldengine/reference.py, tests/test_earth.py (10 pass, 3 strict xfail: straits; Congo gorge; Caspian overflows),
  processes/relief_from_file.py + tools/earth_twin.py.
MEASURED on Earth (level 7, GPCP rain 1979-2010 + CRU T 1961-90 as inputs):
- SeaLevel: sea level -5.3 m, sea share 70.3 %. Black Sea, Red Sea, Baltic, Persian Gulf dry (straits).
- Drainage (valley floors = lowest tenth of land points): Amazon mouth 214 km off, Nile 206 km; 16 of 24 great rivers within
  300 km; off: Congo, Ob, Danube, Yenisei, Volga, St Lawrence, Amur, Huang He. 1055 hollows, 61 % of land drains into hollows.
- Hydrology: land ET/P 0.718 (Earth 0.65), rivers to sea 33,828 km3 (Earth 40,000), Amazon 142,950 m3/s (Earth 220,000),
  lakes 6.5 % of land (false lakes behind closed gorges: Congo 880,000 km2, Amazon lowland 648,000);
  Black Sea lake 511,364 km2 at 5 m (real 436,000), Baltic 227,705 at -1 m, Great Lakes 298,119 km2 at 179 m (real 244,000 at 176-183),
  Caspian: evap 949 mm (real ~1000) but inflow 821 km3 (real ~300) -> overflows (xfail).
- Koppen with observed climate: A 21.1 (19.0) B 24.7 (30.2) C 13.3 (13.4) D 26.2 (24.6) E 14.7 (12.8).
- GPCP land rain by band: N min 566 at 27.5; S min 629 at 32.5; land mean 804, sea 1048, global 977.
EARTH TWIN preview (10,242 cells, 12 rounds): sea level +2.3 m, sea 70.9 %; T 13.3 (14.0); land 3.7 (8.6); 30-60N 1.6 (9.3);
  Jul-Jan land 40-60N 12.8 K (31.1!); rain 1083 (977), land 656 (781), sea 1259 (1057); Koppen A 16.2 B 17.0 C 18.5 D 1.6 (24.6!)
  E 46.8 (12.8!); ET/P 67.4 %; rivers 31,700 km3; largest river 148,720 m3/s at (-2,-51) = Amazon; lakes 5.5 %; T rms 6.3 K;
  rain log-correlation 0.51.  => biggest flaw: land seasons far too weak (EnergyBalance), proposed as the next refinement.
Preview default world (p6.zarr): 25 rounds, 47 s; land rain 623, ET 451 (0.724), PET 830; 20 lakes, 9.0 % of land flooded.
TODO: full suite green -> commit; twin test in test_earth; standard-mesh measurements (default + twin); viewer screenshots;
  record Q16 confirmation; BUILD_NOTES/README/design doc/project note; independent review; package; deliver.

## State after the two step-2 reviews (2026-10-05) -- fixes mostly done, ALL UNCOMMITTED (last commit 5d37e81)
Reports: review_step2/report_physics.md, report_engine.md. Fixed: drainage ties + flow through full hollows; snow_cover field;
exact bucket; lake flow rule (rho = out/in); check_table; why-answer cases/units/{at}; StoreView cache; earth_reference package;
fetch tool; test_water (87), test_reference (13). tools/why_scan.py scans why-answers.
GAUGE ANALYSIS (fix/gauge_analysis.py, fix/demand_experiment.py; logs in fix/logs/):
 - Dai & Trenberth Table 2 station areas (10^3 km2), read twice via WebFetch of ams.confex.com/ams/pdfpapers/55037.pdf (row order
   is "Vol, DA mouth, DA station"): Amazon 4619, Congo 3475, Orinoco 836, Yangtze 1705, Brahmaputra 555, Mississippi 2896,
   Yenisei 2440, Parana 2346, Lena 2430, Mekong 545, Ob 2430, Ganges 952, St Lawrence 774, Amur 1730, Mackenzie 1660,
   Columbia 614, Danube 807, Niger 1516, Zambezi 940, Indus 975, Rhine 180.
 - No fault found in lake_flows. Causes of the 15 gauge misses: (a) mesh runs the river elsewhere (basin near gauge << real):
   Congo 43/3475, Yenisei 251/2440, Lena 272/2430, Mekong 53/545, Ob 294/2430, Amur 100/1730, Danube 140/807; (b) too little
   runoff where yearly rain ~ yearly demand (Yangtze depth 117 vs 534 mm, Mackenzie 86/173, Zambezi 40/112, Indus 12/91,
   Niger 10/22, Ganges+Brahmaputra 285 vs 660, Orinoco 704/1177, Amazon 823/1154); cold wet basins are at or above measured.
 - Totals Earth L7: rain on land 119,778 km3; shed (no lakes) 35,165 (0.706 back); to sea 31,722 (0.735); open lakes lose 2,987;
   closed keep 456. DIAGNOSIS ONLY: demand x0.76 -> 0.632 back, 44.1 to sea, 9/21 gauges; x0.60 -> 0.542, 54.9.
 - Decision: NO model change now. Document: demand too high where rain comes with cloud (no clouds: one sunshine share);
   propose Clouds / land seasons as refinements. Lakes: Verpoorter 2014: 3.7 % of non-glaciated land (via geographyrealm page).
TODO order: test_earth reasons (+Amazon test fix, twin numbers) -> test_world rework -> viewer -> contract over library ->
 mutation gaps -> re-measure sensitivities -> full tests + mutation on copy -> final measurement -> third review -> BUILD_NOTES,
 README, design doc (rev 462 bookmark), project note -> commit -> package -> deliver -> final message.

## State 2026-10-05 ~06:30 (third-check stage; ALL STILL UNCOMMITTED since 5d37e81 until the commit noted below)
DONE this context: gauge analysis -> no fault in lake_flows; tools/earth_rivers.py (5 parts: gauges, mouths, lakes, totals,
 narrows; options --valley-share, --demand-times); earth_reference: Earth class, GAUGES, GREAT_RIVERS, NARROWS,
 rivers_at_gauges(), narrows(); test_earth.py reasons all MEASURED (AT_GAUGE, MOUTH_KM, NARROWS_M self-check tests);
 test_world.py: design dry-belt condition back as strict xfail north; why_scan test; viewer fixed (index numbers, zero on log
 scales, legend); contract test over library; conftest YEAR_S + tool(); engine refuses a sentence pattern naming a driver the
 process does not record (+ note for unused slots); causes: driver-level `ends`; tests for E1/K121/L2.
FINAL MEASUREMENT (scratchpad/step2/final/*.log; stores *.zarr there): default preview 48 s, 23 rounds, 0.44 GB, 21 MB;
 default standard 1,186 s, 24 rounds, 5.23 GB, 219 MB (later round 42 s: Moisture 36); twin preview 42 s, 15 rounds;
 twin standard 710 s build, 15 rounds, 5.15 GB; earth_rivers 22 s. Machine was 1.5x slower than on step-1 day (old code
 preview 34.5 s vs 23 s recorded). why_scan: 174,114 / 121,108 / 174,114 answers, none contradicts.
 Standard default world: T 11.4 C, land 35.8 %, land rain 618, globe 945, back to air 0.736, rivers 29.7, lakes 8.3 %
 (largest 5.9 M km2), hollows 47.5 %, white all year 20 %, driest N 58 deg 290 mm (24 deg: 320), S 24 deg 251; classes
 9.5/36.4/17.2/4.3/32.6; wettest land cell 13.5 m.
 Twin standard: T 13.3 (14.0), land 4.0 (8.8), Jul-Jan 13.6 (30.9), land rain 672 (790), classes 16/19/17/2/46, lakes 8.5 %.
DOCS: docs/BUILD_NOTES.md REWRITTEN (placeholders left: TESTS, MINUTES, PASSED, XFAILED, EARTHTESTS, MUTATIONS,
 THIRD_CHECK_FOUND/CHANGED); README.md rewritten (placeholders PREVIEW_TIME, STANDARD_TIME, WHY_EXAMPLE, TESTS, MINUTES,
 XFAILED). Design doc (rev 462) NOT yet updated: plan = edit .133203, add step-2 blocks after list .265689, update .66 lead,
 .143536 summary, sources .267172/.267267, counts "79 of the 84", field count note for snow_cover (.68422).
NEXT: full suite (running, logs/full_suite.log) -> fill counts -> commit -> mut2/make_copy.sh + `python run.py list_final.py`
 (129 breakages) -> third review agents (briefs in scratchpad/review_step2b/) -> fixes -> rebuild worlds/first.zarr ->
 design doc + project note -> commit -> package -> deliver -> final message (Explanation Protocol; propose land seasons next,
 clouds as second option).

## State 2026-10-05 ~12:10 (before the fourth check; everything since 41e3423 still UNCOMMITTED)
Third check answered (see BUILD_NOTES 5.2). mut3 run finished: 81 changes, 75 caught; survivors T08 (equivalent), S02 (3e-13 mm),
 E04 (redundant line, removed), E10 (remainder = sum when books close), E16 + E17 (harness gaps: now tested); caught late and now
 with own tests: T05, T10, E01.
My own findings while waiting (all in notes/tests):
 - mesh_ties rounding: grid, not tolerance; geometry noise up to 1e-11 at L7; split pairs 0 / 2 / 29 at L5/6/7 (test + docstring + notes item 20).
 - Earth harness: self.ground now float32-exact (what Drainage is handed). Before, tools saw 380 sub-sea-level land cells' means a
   hair off whole metres: tie counts were 17,366/43,066/9,825/3,298/6,462/4,961, now 17,454/42,980/9,869/3,296/6,508/5,063 (65 by number
   unchanged). No river, gauge, like-for-like, lake or narrows number changed (earth_rivers --settlements 20 diff: only Volga lines).
 - Volga (Kalugin 2022 opened by me: 1,360,000 km2, 585 mm, 262 km3): mesh at Volgograd basin 1,248, rain 744 (717-750 over 20 seeds),
   sheds 342 (1.77x), back 402; handed published 585 mm: sheds 224.5 (1.17x; 224.3-224.7 over 8 settlements), back 360.5.
   => four fifths of the excess with the rain data, a fifth the model's. ref.VOLGA, ref.volga(), Earth.full_ways(), Earth.with_rain().
 - Sources re-opened with links: Barnes 2020 (esurf 8/431), TFK 2009 (staff.cgd.ucar.edu ... TFK_bams09.pdf), TFM 2011
   (staff.cgd.ucar.edu ... 2011jcli24.pdf), FAO-56 ch.3, Kalugin 2022 (mdpi). Verpoorter still 403.
 - "FluvialErosion (step 4)" -> step 3 (notes + hydrology docstring).
Full suite on final-ish code: 643 tests, 609 pass, 34 xfail, 0 fail, 8 min 36 s (11:57:51-12:06:27).
RUNNING: fourth/final/measure.sh (default preview 28.7 s 0.44 GB; twin preview; tools; default standard; twin standard; reports;
 why_scans) -> logs in step2/fourth/final/.
NEXT: fill notes sec 1, 4.6-4.8, README counts/times/example; rebuild worlds/first.zarr; commit; launch BOTH reviewers in ONE
 message (briefs: review_step2c/); verify findings; fixes; fill FOURTH_FOUND/CHANGED (+ own findings above); design doc (rev 462;
 plan in my head: lead .66, .133203, .259937, table .260336 rows, new paragraph on Earth's rivers after .261305, departures rows
 10-21 + row 6, list .265689 rewritten, sources .140895/.267172/.267267 (+12 sources: 96 total, 90 opened), summary .143536,
 .269033); project note; commit; package; deliver; final message (Explanation Protocol).

## 2026-10-05, after the fourth check (reports: review_step2c/report_physics4.md N1-N10, report_engine4.md F1-F12)
State at ~16:00 EDT. HEAD 6f632d1; everything below is UNCOMMITTED in /home/claude/world-engine.
DONE in code (with tests passing in their files):
- check_table stricter (takes nbr); why answers a-e + why_scan rules + scan self-test; first guesses in lineage;
  Ties.passes; boundary families in mesh_ties (replaces rounding); harness draws passes; river_books + rivers_at_gauges
  with kept_here (books close at every cell, 5.8e-8 relative; checked by step2/fourth/after4/books_check.py).
TODO, in order:
 A1 test_the_books_of_every_gauge_close: kept_here, all cells, a gauge in a closed lake (demand x0.76: Niger)
 A2 tools: argparse (refuse unknown options, --help exit 0), report functions take an Earth, tests of tool numbers
 A3 harness: land_water(); summary uses it; lakes_share tested; two-sided mouth_moved_by_numbers (0.041 % measured by reviewer)
 B  tests for engine reviewer's 46 unnoticed changes (work_engine/mutation/list1.py list2.py list3.py results.jsonl)
    then re-run both reviewers' unnoticed lists in a scratch copy
 C  F10 stdout encoding/store rename/lock; F12 doc; F8 (1,053 m; mesh.py bits; README clone sentence); N9 items; N6 verify
 D  re-measure: Earth engine rule + 100 settlements; six valley shares; demand x0.76/0.60/0.794; default+twin worlds preview+standard; why_scan x3
 E  notes 4.2-4.5, 4.7, 5 (placeholders FOURTH_FOUND/FOURTH_CHANGED), 6, 7(14,20), 8, 9, 10, 11; README; models.yaml labels; test reasons as frequencies
 F  full suite with/without data; rebuild worlds/first.zarr; commit
 G  design doc (rev 462, plan in step2/fourth/doc_draft.md); project note; package; deliver; final message

## State ~18:40 EDT (still uncommitted on 6f632d1)
DONE since last entry: books test all cells (+Niger x0.76); src/worldengine/console.py (print_anywhere, tool_parser);
 all tools + trials on argparse (main(argv)), report functions take earth=/flood=/say=; cli: no abbrev, explain needs place,
 IndexError refused; store: _move_into_place (retry rename), StoreView.fingerprints incl. tables; requirements.lock with
 indirect pins + requirements-viewer-check.lock; harness: within_a_factor_of_two, land_water, mesh_hollows, like_together,
 demand_times, under_demand, tally, MUCH_OF_THE_RAIN, VOLGA runoff_coefficient 0.38 (Kalugin re-read: 262 km3, 0.38, 250 km3
 "water content", 30 % solid, 53 % spring flood); earth_demand: evaporation 45.1 vs 38.5 (TFK Table 2b Land re-read: 145.1,
 39.6 reflected, LH 38.5, SH 27, net LW 79.6), excess 20.2 = 0.7 + 8.2 + 11.3; why_scan extended (heading/places, sums,
 ocean_mask, subsidence, biome, surface_temperature, snow numbers, lake books, flow_receiver) + 28 planted faults in self-test.
NEW TESTS: tests/test_tools.py, tests/test_answers.py (+toy Pointer), store/server (dtype, read-only, kept, tables in
 fingerprints, direction east/north, idmap, outside files, warnings), params refusals + fingerprint, field's own settle
 tolerance (52/12/20/76 rounds), Earth: water_of_all_the_land, rain/demand at gauges, under_demand table, like-for-like
 caveats, radiation/excess, tool reports, xfail reasons (lakes; twin), twin report; reference: steep date-line wrap, polar
 rows; water: slope cell by cell incl. coast; rules text tied to refusals; world_report; dry-belt reason numbers (1,053 m);
 README example test.
NUMBERS (engine's rule, family widths): ties by_width 6521, by_number 52 (were 6508/65); mouth_moved_by_numbers 0.032 %;
 land under water if full 10.2 % + 3.6 % exactly level; 4898 cells under, 1722 level.
 under_demand: 1.0 -> 0.683/0.587/0.644/0.7352/31.72/581/7; 0.794 -> 0.926/0.873/0.906/0.6487/42.08/513/12;
 0.76 -> 0.973/0.914/0.963/0.6317/44.11/499/11; 0.6 -> 1.227/1.124/1.276/0.5416/54.90/428/10.
 20 settlements with passes drawn (old log after4/rivers_s20_first.log): mouths 14-17; Nile 10, Yangtze 6, Yenisei 1,
 Huang He 14; gauges 6-9; Orinoco 2, Yenisei 3, Ob 1, St Lawrence 11; Caspian closed 10 of 20.
RUNNING: after4/rivers_s100.log (100 settlements + demands).
NEXT: full test_earth -> update MOUTHS/AT_GAUGE/ALIKE/Caspian/Volga records + reasons as frequencies; N6 verify (St Lawrence
 valley rule); re-run reviewers' unnoticed mutations (work_engine/mutation list1/2/3, work_physics/scripts/mut_list.py) in a
 scratch copy; re-measure worlds; notes/README/models.yaml labels; full suite; rebuild first.zarr; commit; doc; deliver.

## State 18:02 EDT, 2026-10-05 (clock of the container; still uncommitted on 6f632d1)
DONE since last entry: breakage list re-run twice (mut4/results_first_run.jsonl: 71 runs, M15 survived -> new test
 a_part_names_a_row_of_another_hollow_as_sibling; mut4/results.jsonl: 75 runs on the synced copy, 73 "caught", Hk/Hm
 survive (equivalent); BUT Fb, Fc were caught only by tests/test_contract.py failing on its own: `mesh.xyz[:12]` in
 library/drainage.boundary_families broke the no-numbers rule. FIXED: CORNERS = 12 named at the top of drainage.py.
 Fb, Fc must be run again after syncing the scratch copy (expected: survive).
 Re-measurement fourth/final2/ (measure.sh): all four worlds identical to those before the fixes (fingerprints, 115/73
 entries); preview 27.4 s, standard 598.5 s / 5.28 GB, twins 21.7 s and 364.6 s; tools 15.5/18.7/14.8 s; s20 71 s;
 s100+demands 374.5 s (under load; log equals after4/rivers_s100.log in parts 1-7); why_scan: 225,324 / 156,728 (every
 23rd) / 225,324 answers, none contradicts; six valley shares x 20 settlements (final2/shares: same tables as
 after4/shares): Caspian closed 20/20 at 0.02, 0.05, 0.2, 0.3, 0.5 and 10/20 at 0.1; Nile 0,0,10,20,20,20; viewer check ok.
 New tests: store rename retries (test_store_server), families on the standard mesh (test_water_rules), sibling breakage.
 Texts: crust trial "fixed before the first run" corrected (trial docstring + notes 3.2: form in the design, the two
 shares not verifiable); "three times" -> "two and a half to three times" in test_earth.py; labels on which hollows are real.
 Notes: fourth/notes/{rewrite_notes.py, values.py, numbers_measured.py, share_table.py, sec44.md, fill_readme.py};
 draft run with NOTES_DRAFT=1 works (4 placeholders left: FIFTH, FIFTH_ROW, FIFTH_FOUND, NOT_DONE_REVIEW).
 README edited with marks (N_TESTS etc.) to be filled by fill_readme.py.
 Docs: guide read; doc at rev 462 unchanged; texts for the update in fourth/doc_final.md (sources 91 of 97; 13 added in step 2).
 Fifth check: brief at review_step2d/brief_claims.md (claims only).
RUNNING: fourth/final2/suite.sh (whole suite with data, then without) -> suite_with_data.log, suite_without_data.log.
NEXT: read the suite; rerun Fb/Fc in mut4 (sync first); run rewrite_notes.py (no NOTES_DRAFT) + fill_readme.py; rebuild
 worlds/first.zarr; commit; launch the fifth reviewer; fix; final suite; commit; design doc (apply doc_final.md);
 project note; package (zip with worlds/first.zarr, without reference_data); SendUserFile; tasks 21/35/36/37; final message.

## State 20:30 EDT 2026-10-05 (after the fifth check's reports; nothing mended yet; repo clean at c8c8448)
Reports: review_step2d/report_numbers5.md (R1..R15), report_record5.md (1..14). Two messages sent to Minh (18:30, 20:10).
DECISIONS for the answer to the fifth check (work folder step2/fifth/):
 D1. Earth harness pours the RELIEF'S OWN ocean volume (design, Layer 9, SeaLevel row), default; option sea_water="planet"
     keeps the old way; tools get --sea-water relief|planet. The twin keeps the planet file's volume (it is a planet parameter).
     => every pinned number of tests/test_earth.py and of notes section 4 is measured again.
 D2. Random settlements also draw the way over level ground (new Ties.level in library/drainage.py; engine path unchanged).
 D3. "why" sentence for a cell wholly under a closed lake: no amount "from upstream"; scan rule + planted fault.
 D4. Refusals: tests for the 15 untested + an audit tool that replaces each refusal's message and runs the engine tests.
 D5. check_table: bound a pass into the sea from above if the table allows; else say "two things the check cannot show".
 D6. Notes 4.2-4.5 rebuilt: tables from tool logs, prose cut to labelled statements; say less.
 D7. After the fixes: a sixth, diff-scoped check (new numbers and rewritten text only); decide when the diff is known.
Order: code+tests -> measure (step2/fifth/logs) -> re-pin tests -> suite -> worlds -> breakage list -> notes/README ->
       design doc (guide first!) -> project note -> package -> final message.
