# Handoff: world engine, build step 2 close-out (written 2026-10-05, about 22:20 EDT)

This file hands the work to a fresh session. Read it first, then `handoff/PROGRESS.md` (the running log, last entry
"State 20:30 EDT"), then `docs/BUILD_NOTES.md` (the notes of commit c8c8448, which are STALE in places listed below).

## What Minh asked for (standing instructions)

- The original brief is in `handoff/brief.md`, verbatim. Read it. Short form: a world-generation engine in Python,
  every feature from a stated physical cause, named simplified models with what each ignores, three time scales,
  a "why is it like this?" answer recorded while computing, fields on one spherical mesh (about 160,000 cells),
  processes that declare reads and writes and never call each other, constants in data files, same seed gives the
  same world, an external-push mechanism, tests against real-world patterns.
- The design was approved ("be sure to have sth like north/south poles that is cold. I approve otherwise").
  The design document is a Claude doc: https://claude.ai/code/artifact/0ad5d499-95b9-4211-8e8c-74651f03652b
  (its last revision still describes step 1; it has not been updated for step 2).
- Latest instruction: "I confirm, now, continue making progress." Scope decided: finish the close-out of build
  step 2, deliver, and propose what to mend next. Do NOT start build step 3 before Minh answers.
- How Minh wants answers: complete sentences; for explanations the three moves Definition, Mechanism, Actuality
  in numbered layers, no undefined jargon, tables for comparison, a closing prose summary; every claim labelled
  [DOCUMENTED], [INFERRED], [MEASURED] or [UNVERIFIED], and never an unverified claim stated as fact.
- Out of scope, not to be built: magic weather, cultures, species, settlements, trade.

## State of this branch (`step2-fifth-check-wip`)

Everything since c8c8448 is the answer to the FIFTH independent check of build step 2
(`handoff/reviews/report_numbers5.md`, `report_record5.md`). It is work in progress and the suite does NOT pass.

Done (in the tree, never run together as a whole on the final code):
1. The Earth harness pours the relief's own ocean volume, as the design's row asks (`sea_water="relief"`,
   1.337585e18 m3; the planet file's 1.335e18 is 0.19 % less). Sea of the mesh at +1.9 m (was -5.3 m).
2. A random settlement of ties also draws the order in which level ground is drained (`Ties.level`).
3. Hydrology's "why" for cells under a closed lake counts water once (`from_upstream`); scan rules added.
4. `tools/refusal_audit.py` and `tests/test_refusals.py` (65 cases). An audit run WITHOUT tests/test_earth.py
   reported 249 of 249 refusals held (before: 174 held, 66 unreached, 9 reached but unheld).
5. Harness additions: `lake_books`, `kept_apart`, `volga()` with four rows, `relief_sea_volume`,
   `other_valley_reading` (replaces the old "every point" diagnosis), `snow_handed_in`.
6. Text corrections in data/models.yaml, several docstrings, tools.
7. `tests/test_earth.py`: rewritten on the new numbers from the top down to and including
   `test_what_the_land_sheds_like_for_like_basin_by_basin`. NOT YET RUN.

Not done, in this order:
1. `tests/test_earth.py`, the rest (old numbers still stand from `test_the_caspian_stays_a_closed_lake` on):
   - Caspian test: fails as built. Assertion message must be
     `the lake at the Caspian's place overflows by 17.9 km3 a year`. Facts: 1,089,603 km2 at 61 m; overflows by
     17.88 of the 669 km3 that reach it; rivers and shores bring 590 km3; loses 933 mm, gets 408 mm of rain;
     catchment 4.05 million km2 with the lake, 2.96 without; 199 mm; holds the Don at Voronezh; the overflow
     crosses 4 land cells and ends in a CLOSED lake of 19,939 km2 at 42.2 N, 57.1 E; in 20 random settlements
     closed in 1, overflow 3.07 to 23.40, and the water reaches the sea in none. Real sea: 371,000 km2 (Wikipedia
     lead), catchment about 3.6 million km2.
   - Volga test: rewrite on the four rows of `ref.volga()` (numbers in `handoff/repin/repin.log`, line "volga:").
     State it conditionally: which precipitation is true is not known.
   - Caspian ties test: numbers in repin.log, line "caspian over settlements".
   - Seas as lakes: rename to
     `test_a_sea_that_is_cut_off_or_a_great_lake_comes_back_as_a_lake_near_its_real_size(earth, name)`,
     parametrized; the Black Sea is a strict expected failure (612,693 km2 at 32 m against a bound of 30 m;
     message `the Black Sea: a lake of 612,693 km2 at 32 m`; cause measured: its outlet cell at 40.5 N, 27.3 E is
     78 % ocean in the data, mean -5.6 m, handed in at 32 m by the valley rule). Baltic 265,947 km2 at 8 m,
     Great Lakes 298,119 km2 at 179 m pass.
   - Open water at the Caspian: 1,002 mm at the place, 933 over the lake.
   - Lakes cover: 6.28 % of the land, 9.37 million km2, 6.25 to 6.28 % over settlements; message `6.3 % of ...`.
   - Twin part: correct two reasons. Measured (`handoff/pass2/twin_seasons.log`): land 40 to 60 N, year -5.8
     against 3.5 C; coldest month -12.6 against -12.7 (right); warmest 1.4 against 18.4 (17 K too cold); 52 % of
     that land under snow in every month. The old reason blames "one constant that ties land to sea" as cause:
     that is not established. Two causes are not told apart (weak seasonal forcing, snow that never melts).
   Then run `PYTHONPATH=src python -m pytest tests/test_earth.py` until it passes with every miss a strict xfail.
   Expect some of my new assertions to be off; every number comes from `handoff/repin/repin.log`,
   `handoff/logs/*.log`, `handoff/pass2/*.log`. Fix the assertion only after re-measuring, never by loosening
   a design condition.
2. Small code items: add `refusal_audit` to the tools that `tests/test_tools.py` runs; check `tests/test_reference.py`
   and `tests/test_tools.py` for strings of changed tools; `tools/earth_twin.py` should say the twin pours the
   planet file's volume.
3. Whole suite with and without Earth data; commit; then on the committed code: suite both ways, refusal audit
   with test_earth included, Earth measurements (`handoff/notes_tools/measure_earth.sh`, adapt paths) compared
   with `handoff/logs`, the four worlds with `tools/why_scan.py`.
4. Rewrite `docs/BUILD_NOTES.md` sections 2 to 11 from the logs ("say less": numbers and measured facts, no
   cause that was not measured). The list of what is stale is in `handoff/PROGRESS.md` and in the section
   "Pending" of the long summary there. Add a section "What the fifth check changed", including that I told Minh
   a false sentence ("It fails only at the setting I built with") and corrected it.
5. README counts and the new tool; update the design document (draft texts in
   `handoff/doc_final_step2_draft.md`, numbers there are OLD and must be replaced) and the project note
   `claude/world-engine-design.md`.
6. Decide on a sixth, diff-scoped independent check (leaning yes). Package, deliver, final report with questions.

## Headline numbers under the new water (measured on a snapshot; re-run before quoting)

- Mouths within 300 km: 15 of 24 as built; 13 to 16 over 20 random settlements; 13 in all, 7 in none, 4 decided
  by ties (Yangtze 12, Lena 13, Yenisei 1, Huang He 13).
- Gauges within a factor of two: 8 of 21; 6 to 9 at random; 6 in all, 10 in none, 5 decided by ties.
- Like for like the land sheds 0.69 of the measured depth (15 basins); of the rain on land 0.738 goes back to
  the air (Earth 0.65); 30.7 thousand km3 reach the sea (Earth 40).
- Radiation: the formulas leave Earth's land 85.8 W/m2 where a published budget has 65.5.
- Valley-rule diagnosis (`other_valley_reading`): 16 mouths for 15, 8 gauges for 8, lakes 5.57 % for 6.28 %.
  Conclusion to propose to Minh: tuning the harness moves single rivers, not the count; the real mend is relief
  data with rivers cut in.

## Questions to put to Minh at the end

1. What to mend first (candidate: the cold northern summers of the climate).
2. Whether the 21 chosen gauges belong to the design's "done when" for Hydrology.
3. Whether a Caspian whose overflow ends in a neighbouring closed lake meets "stays a closed lake".
4. Relief with rivers cut in, to be fetched on his machine.

## Environment

- Python 3.13, numpy, numba, zarr 3, scipy (`requirements.lock`). Run with `PYTHONPATH=src` from the repo root.
- `reference_data/` is not in the repository. `python tools/fetch_reference_data.py` fetches it (about 34 MB);
  without it every Earth test is skipped. If the fetch is blocked, ask Minh to attach the four files named in
  `tools/reference_data.yaml`.
- `worlds/` is not in the repository; `python -m worldengine build` makes a world (see README).
- Do not edit files while a measurement or audit reads them. Never print `data/biomes.yaml` (very long lines).
- Commit messages end with the attribution lines the session gives.
