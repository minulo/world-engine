# Handoff: world engine, state after the close-out of build step 2 (written 2026-10-06)

Read `docs/BUILD_NOTES.md` first: its head, section 1, section 5.4 (what the fifth check changed), section 5.5
(a sixth, narrow check) and section 11 (four questions for Minh). This file only says where things stand.

## Standing instructions (Minh)

- The brief is in `handoff/brief.md`, verbatim. The design is approved; the design document is a Claude doc:
  https://claude.ai/code/artifact/0ad5d499-95b9-4211-8e8c-74651f03652b . Its section "Build order" and its sources
  were brought up to step 2 on 2026-10-06 (revision 474); its layers still describe the design as approved.
- On 2026-10-06 Minh left the four questions of the notes to Claude ("you can decide whatever makes sense").
  The decisions are in `docs/BUILD_NOTES.md`, section 11: the seasons were diagnosed and nothing mended (section
  4.9); the 21 gauges do not belong to the "done when"; the Caspian's condition is kept as written and fails; relief
  with rivers cut in is not fetched. **Next is build step 3, as the design orders it. It is not started.**
- Never loosen a design condition to make a test pass. Every number comes from a measurement or a log; every
  claim carries [MEASURED], [DOCUMENTED], [INFERRED] or [UNVERIFIED].
- Answers to Minh: complete sentences, no undefined jargon, tables for comparison.

## Done on this branch (`step2-fifth-check-wip`)

1. `tests/test_earth.py` rewritten to the end on the numbers measured after the fifth check; passes with every
   miss a strict expected failure (62 pass, 34 expected failures).
2. Small code items (the tools tests run `refusal_audit`; the twin tool says which water it pours).
3. On the committed code: the whole suite with and without the Earth data (829 + 35 expected failures; 761 +
   102 skipped + 1), the refusal audit with every test (249 of 249 held), the Earth tools (logs equal to the
   snapshot's in every shared number but one typed 85.7), the four worlds and the scan of their "why" answers.
   Logs: `handoff/logs/`.
4. `docs/BUILD_NOTES.md` rebuilt by `handoff/notes_tools/build_notes.py` (tables of sections 4.2, 4.4, 4.5 from
   the logs; the other sections by exact replacement in the notes of commit c8c8448). To rebuild:
   `python handoff/notes_tools/make_values.py handoff/logs handoff/logs handoff/notes_tools/values.json handoff/notes_tools/extras.json`
   then `python handoff/notes_tools/build_notes.py handoff/logs handoff/notes_tools/values.json > docs/BUILD_NOTES.md`.
5. README counts; the design document; the project note `claude/world-engine-design.md`.
6. A sixth, diff-scoped check (`handoff/reviews/report_sixth.md`); its nine findings are answered (notes 5.5).
7. The diagnosis of the cold northern summers: `handoff/pass3/` (scripts and logs), notes section 4.9. No check
   by anyone else, and no test holds its numbers.

## Not done

- No archive was packaged or delivered (`main` holds the branch since 2026-10-06). `worlds/first.zarr` (not under
  version control) must be built before packaging: `python -m worldengine build --profile preview --out worlds/first.zarr`.
- After the sixth check's answers only `tests/test_earth.py` was run again, not the whole suite (the other test
  files did not change).
- The browser check of the viewer (`tools/viewer_check.py`) was not run again. Nothing was run on Windows.

## Environment

- Python 3.13; `pip install -r requirements.lock`; run with `PYTHONPATH=src` from the repository root (or the
  README's three install commands). `python tools/fetch_reference_data.py` fetches the Earth data (34 MB).
- The standard build needs 5.3 GB of memory: run nothing of size beside it on a 7 GB machine.
- Do not edit files while a measurement or an audit reads them. Never print `data/biomes.yaml` (very long lines).
