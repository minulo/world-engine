# Build step 3: the tasks

Seven work packages. Each can be given to one agent. The order matters where a package names what it needs.
Nothing of step 3 is built yet (2026-10-06): no code, no tests, no pass condition. `GOAL.md` says what the step is
for; `ACTIONS.md` says how to work and what to hand back.

Until package G, the default world stays as it is: every new process is developed as an ALTERNATIVE
implementation, chosen in tests through the engine's `overrides={"models": ...}` (as
`earth_reference.earth_twin_models` does for the Earth twin), so that `main` stays green and the 864 tests keep
passing. Package G makes the switch and re-measures every pinned number.

## T0. Fix the pass conditions before any run (first; small; needs nothing)

The record of this project shows conditions written after their results four times (`docs/BUILD_NOTES.md`,
section 5). So: write `docs/step3/PASS_CONDITIONS.md` and commit it BEFORE any code of step 3 is run. For each
"done when" of `GOAL.md` and each known answer below, state the measure, the mesh, the seed(s) and the number that
passes. Where the design gives the pattern and not the number, choose the number now and say it was chosen now.
Later changes to that file must be separate commits that say why.

Known answers the design fixes (its Layer 9 table):
- Tectonics: two plates set to move apart: new floor forms between them and is youngest along the line where
  they part. Mountain belts lie along edges where plates close. Heights cluster in two groups (continents, floor).
- FluvialErosion: once uplift and erosion balance, slope falls as drained area grows, as area to the power -m/n
  (on Earth m/n is about 0.5). On worlds the engine has eroded, river length grows with basin area to a power of
  0.5 to 0.6 (Hack's law).
- Lithology: each row of the rule table, fed a setting built to trigger it, returns its rock family.
- SurfaceAge: age resets to zero where lava covers the ground, where erosion cuts deep, and where land rises
  from the sea; elsewhere it grows by one step each round; on moving crust it moves with the crust.
- The crust trial's three conditions (`trials/crust_points_trial.py`; notes section 3.2) carried into the real
  Tectonics at both mesh sizes: (A) after 125 rounds a marked patch of crust lies within one cell of the place
  its plate's motion gives; (B) continental area changes by no more than 2 % beyond what the plate rules made or
  destroyed; (C) fewer than 1 % of cells a round switch crust type and switch back.

## T1. The geological clock over many rounds (engine; needs T0)

The engine already loops geological rounds, carries tables and lagged fields, and calls start steps
(`engine.py`: `_run_geological`, `_start`, `_end_round`). Not built, and refused on loading today
(`_check_settings`): history snapshots; continuing a finished history.
- With toy processes (`tests/toy_processes.py`), test that a history of N rounds equals the first N rounds of a
  longer one, bit for bit, and that every draw depends on the seed and the round number alone.
- Build continuation: the world store keeps what the geological clock carries from round to round (tables,
  lagged fields, groups), and `build` can start from a stored world and run on. Test: 250 My then on to 500 My
  equals 500 My in one run, bit for bit (toy processes first).
- Build snapshots: `snapshot_every_rounds` and `snapshot_fields` of `data/profiles.yaml` (the design: 25 stored
  pictures of four fields, 10 My apart by default); the store holds them; remove the refusal and test the new ones.
- Every new refusal gets a test; `python tools/refusal_audit.py` must stay at "held by a test: all".

## T2. Tectonics as a plate history (the largest package; needs T0; T1 for the bit-for-bit tests)

One new file, for example `src/worldengine/processes/tectonics_plate_history.py`, with the declaration of
`tests/design_declarations.py` unchanged. Start from the seeded start of `tectonics_snapshot.py` (plates, axes,
speeds, continents, thickness: keep it, so the start of history is today's world) and from the moving-points code
of `trials/crust_points_trial.py`.
- Each round: thin each point by what its cell lost last round (group `crust_thickness_tendency`, lagged);
  turn points with their plates; subduction (which plate dives; the overriding crust thickens by the paper's
  uplift divided by the share of thickness that becomes height); collision (terrane welded to the other plate;
  the surge as thickening); spreading (new ocean-floor points in the gap, age zero); rifting (by seeded draws);
  slab pull on the axes; resampling with weights that are exact for an evenly changing value; draw every field
  onto the mesh.
- The three duties recorded in notes section 3.2: fill fresh points as the paper does; make new ocean floor at
  parting margins BEFORE drawing; carry conditions A to C into tests at both mesh sizes.
- Ties (two points equally near, two plates equally old) must be settled by what the things are, never by array
  order: turning the planet by one face of the mesh must give the same world turned (there is a test of this for
  the snapshot; keep it true).
- Drivers and "why" sentences for `crust_thickness`, `plate_id`, `ocean_crust_age`, `orogeny_age`; events in
  `table:tectonic_events` with the round they happened in.
- Constants in `data/models.yaml` with labels: [DOCUMENTED] only for what was opened and read, [CALIBRATED] or
  [PROVISIONAL] for what is tuned.

## T3. FluvialErosion (needs T0; can run beside T2 on built ground)

One new file. Stream power law, implicit solution of Braun and Willett 2013 along the flow paths that
`library/drainage.py` already gives (receivers, the stack order, hollows). Hillslope smoothing. Modifies
`elevation` with priority 10, writes `erosion_rate`, adds `erosion_thinning` to `crust_thickness_tendency`.
- Known answer: on a tilted block under steady uplift, run to balance; fit slope against drained area; the power
  is -m/n within the tolerance fixed in T0.
- Rock is conserved in the books: what leaves `elevation` is what the group hands to Tectonics.
- State where the eroded rock goes: nowhere (the design's stated limit). Do not add deposition.
- Open the sources before citing them. The design could not open Braun and Willett 2013 itself and cites
  Landlab's description of the method.

## T4. Lithology and SurfaceAge (small; needs T2's fields; testable alone on built inputs)

- Lithology: a rule table in a data file (tectonic setting -> rock family, erodibility). One test per row.
- SurfaceAge: ages on the table `surface_age_points`, carried across resampling with the sources and weights
  that Tectonics records in `crust_points`; has a start step. Tests: the four known answers of T0.

## T5. The world with deep time, measured (needs T1 to T4)

With all four processes chosen by override, at `history_length_my: 250`:
- the bit-for-bit conditions of the "done when" (stopped at 250 My; continued to 500 My), on the preview mesh,
  and on the standard mesh if the machine allows (the standard build needs more than 5 GB today);
- run times and memory against the limits of `data/profiles.yaml` (standard: 1,800 s). If 125 geological rounds
  do not fit, measure where the time goes and report; do not cut physics silently;
- relief statistics beside Earth's: the two clusters of height, mountain belts along closing edges, the share of
  land, the age of the ocean floor, land draining into closed hollows, land under lakes. Each as a number, with
  Earth's number and its source;
- the "why" answers of the new fields, and `tools/why_scan.py` extended with rules for them.

## T6. The long trial (needs T5)

A history of 2,500 My on the preview mesh: the volume of continental crust, the share of land, the number of
plates, the mean height of the land and the stray of a marked patch, measured every 250 My. A steady drift in any
of them is a failure and is recorded as one; `expected_range` of the history length in `data/models.yaml` is set
to the span that showed none. Kept as `trials/long_history_trial.py` with its results, like the two trials of
step 1.

## T7. The switch, and the close-out (last; needs everything; one agent, then an independent reviewer)

- Make the plate history and the three new processes the default; `history_length_my: 250`.
- Every pinned number of `tests/test_world.py`, the README's example answer, the Earth twin (which leaves
  Tectonics out and fills Isostasy from a file: decide and say what erosion does on measured relief) and
  `docs/BUILD_NOTES.md` is MEASURED again. Never edit a pinned number by hand to make a test pass: re-measure,
  then pin.
- Viewer: plays the snapshots as a film.
- Whole suite with and without the Earth data; `tools/refusal_audit.py`; the four worlds; `tools/why_scan.py`.
- `docs/BUILD_NOTES.md` gets a section for step 3 written from logs; README counts; the design document's
  "Build order" (results, departures, where the world is wrong now); the project note.
- An independent check by an agent that did not write the code, on the claims and on the numbers.
