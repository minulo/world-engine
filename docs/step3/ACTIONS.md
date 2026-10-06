# Build step 3: how to work, and what to hand back

For any agent that takes a package of `TASKS.md`. Short, and every line is here because its absence cost a
round of rework in steps 1 and 2 (`docs/BUILD_NOTES.md`, section 5).

## Set up

    git clone https://github.com/minulo/world-engine && cd world-engine
    python -m pip install -r requirements.lock           # Python 3.13
    python tools/fetch_reference_data.py                 # 34 MB of Earth data; without it 102 tests are skipped
    PYTHONPATH=src python -m pytest                      # 864 tests, about 10 minutes: 829 pass, 35 expected failures

Work on a branch named for the package (`step3-t2-plate-history`). Commit and push after each finished piece.
Do not push to `main`; the owner or the close-out agent merges.

## Read first, in this order

1. `docs/step3/GOAL.md`, `docs/step3/TASKS.md`, this file.
2. `README.md` (layout, "How to add things").
3. `docs/BUILD_NOTES.md`: sections 1, 3.2 (the crust trial), 6, 7, 8, 9, 11.
4. The code your package touches. For any package: `src/worldengine/process.py`, `engine.py` (class Context,
   `_run_round`, `_run_geological`), `testing.py` (the Harness that runs one process alone),
   `tests/design_declarations.py`, `data/models.yaml`, `data/fields.yaml`, `data/tables.yaml`.

## Rules of the build

1. **Conditions before runs.** A pass condition is written and committed before the code it judges is run
   (`docs/step3/PASS_CONDITIONS.md`). A test written with its result in view is labelled "found, then kept" and
   proves less. Say which each test is.
2. **Never loosen.** If a condition fixed beforehand fails, it stays as written and becomes
   `pytest.mark.xfail(strict=True, raises=AssertionError, reason=...)` with the measured number in the reason, and a
   test beside it holds that number. Never change the measure after seeing the failure without saying so in the
   notes, with both measures reported.
3. **Never place an outcome.** No "put a mountain here". If a constant must be tuned, it is labelled
   [CALIBRATED] or [PROVISIONAL] in `data/models.yaml` with what it was tuned on; a tuned constant is never
   labelled [DOCUMENTED].
4. **Labels on every claim** in code comments, data files, tests' reasons, notes and reports:
   [MEASURED] you ran it and read the number; [DOCUMENTED] you opened the source in this session (say how: page
   reader, PDF); [INFERRED] your reasoning; [UNVERIFIED] recalled. A cause is [MEASURED] only if a run isolates
   it. "In none of 20" is a count, not "never".
5. **No number in code.** Constants live in `data/*.yaml`; `tests/test_contract.py` enforces it for processes
   and the library.
6. **One process, one file; no process imports another.** Shared mathematics goes to `src/worldengine/library/`.
   Declarations must match `tests/design_declarations.py`; a departure from the design is allowed only if
   recorded: a numbered item in `docs/BUILD_NOTES.md` section 7 and a row in the design document's table.
7. **Determinism.** Same seed, same world, bit for bit: no dependence on array order where things tie, no
   set or dict order, no threads, draws only through `ctx.draw` with purposes listed in `data/seeds.yaml`.
8. **"Why" answers.** Every field a process writes has drivers recorded in the recording pass and a sentence
   pattern in `data/explanations.yaml`; `tools/why_scan.py` gets a rule for each new kind of sentence, and a
   planted fault that the rule catches.
9. **Refusals.** Every sentence the engine gives in place of doing what it was asked has a test that holds its
   words (`python tools/refusal_audit.py`).
10. **Run the whole suite before you say "passes".** Tests of the file you changed are not the suite. Say on
    which commit it ran. Do not edit files while a measurement reads them.
11. **Memory.** The machine of the earlier work had 2 cores and 7 GB. The standard build holds 5.3 GB. Develop
    on the preview mesh (level 5, 10,242 cells); run the standard mesh (level 7) alone.
12. **Out of scope.** Do not start steps 4 to 11. Do not mend the cold summers (notes 4.9) or the land's water
    (notes 4.4): both are recorded and wait for the ocean's step. Do not add deposition to erosion.

## What to hand back

A report in complete sentences, with these parts and nothing else:
1. What was finished, by file.
2. What was verified by running it: the command, the commit, the result.
3. What was not finished or not verified, and why.
4. Every condition of `PASS_CONDITIONS.md` that belongs to the package: met (the test that holds it) or failed
   (the measured number, the expected-failure test).
5. Departures from the design, each with its reason.
6. Decisions that are the owner's, as questions.
And in the repository: the logs of every measurement the report quotes, under `handoff/step3/<package>/`, with
the script that made each.
