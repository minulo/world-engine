# Fifth check, part "record": the claims about the checks, the engine's own claims, the hand-over texts

Paths: `R` = `/home/claude/world-engine` (HEAD `c8c8448`; line numbers are of that commit). `S` = `/tmp/claude-0/-home-claude/059ceeac-064c-547a-88dd-cb05ea65ee21/scratchpad`. `W` = `S/review_step2d/work_record` (my copy `W/world-engine`, scripts `W/scripts`, logs `W/out`). Everything was run in `W/world-engine` with `PYTHONPATH=src`. "The 300 engine tests" are `tests/test_engine.py`, `test_engine_cases.py`, `test_engine_round2.py`, `test_engine_round3.py`, `test_contract.py` and `test_scheduler.py`.

## 1. Verdict

1. The numbers hold. The account of what is done does not: two claims a reader would act on are false, and about twenty smaller statements claim more than the evidence bears.
2. Worst: `R/docs/BUILD_NOTES.md:1302` says of the 21 departures "Each is recorded in the design document as well". The design document stood at revision 462 at 19:38 on 2026-10-05 with nine departures, all of step 1.
3. Second: section 2 gives the design's condition "every refusal message is tested" a "Pass". I disabled twelve of the engine's refusals and reworded three more, one at a time; all 300 engine tests passed each time.
4. Section 5.3 carries all 22 findings of the fourth check at their strength, except N10 (no entry) and four small misstatements. Of my 13: 8 mended, 4 partly (N4, F3, F8, F9), 1 left as found and said (F12).
5. Two mends made new claims that do not hold: the new "why" sentence for a cell wholly under a closed lake, and "one thing the check cannot show" where the fourth check named two.

## 2. Findings, most serious first

### 1. The departures of step 2 are not in the design document (high)

- **Claim.** "Each is recorded in the design document as well. Items 1 to 8 are of step 1; 9 to 21 of step 2." (`R/docs/BUILD_NOTES.md:1302`)
- **Evidence.** The table of departures in the design document has nine rows, all of step 1:
  - Rows 1 to 6: the rain rule, where ice lies, air blocked by ranges, the wind that carries vapour, the one direct solver, constants set by hand.
  - Rows 7 to 9: the frozen-region cap of −15 °C, pushes on groups, and snapshots and clocks refused on loading.
  - The notes' items 1, 2, 4, 5, 6, 7 and 8 have a row. Items 9 to 21 have none. I found none for item 3 either (seven hits for "seeded start", none of them that record).
  - The document's rows 7 and 9 are not in section 7 of the notes at all (they stand at lines 215 and 1285).
- **How I know.**
  - I read the live document (`https://claude.ai/code/artifact/0ad5d499-95b9-4211-8e8c-74651f03652b`, tab "Design") read-only through the document connector at about 19:10 and again at 19:38 EDT. Both reads returned revision 462; the table was last changed at revision 455.
  - Searches of the tab: "wider way" 0 hits, "hierarchy" 0, "snow_cover" 0, "Build step 2" 0. "Priority-Flood" has 3 hits, all in the tables of models and sources.
  - The document's results table still states the step-1 world: "The land is too dry. It gets 306 mm of rain a year".
  - The builder's own files say the same. `S/step2/PROGRESS.md:254`: "doc at rev 462 unchanged; texts for the update in fourth/doc_final.md". `S/step2/fourth/doc_final.md:1`: "Design-document update after build step 2 (texts to apply; …)", and `:25`: "departures: new rows 10 to 22".
- **True wording.** "Items 1, 2 and 4 to 8 are recorded in the design document. Item 3 and items 9 to 21 are not yet: the texts are written and are to be applied before hand-over." Or apply the update first, and hold the rows applied against section 7.

### 2. "Every refusal message is tested | Pass" (high)

- **Claim.** "Every refusal message is tested | Pass. Every refusal of the scheduler is checked for its message (`tests/test_scheduler.py`, 60 tests), and the engine's own in the four engine test files" (`R/docs/BUILD_NOTES.md:40`). The design's step-0 condition reads "First-round defaults and every refusal message are tested" (design document, build-order table, revision 462).
- **Evidence.** The scheduler half holds: every message of `scheduler.py` has words in `tests/test_scheduler.py`. The engine's own half does not. Each change below was made alone in my copy and restored; the 300 engine tests were run each time.

| Change | Where in `R/src/worldengine/` | Result |
|---|---|---|
| A condition with two tests is no longer refused | `interventions.py:91-92` | 300 passed |
| Two pushes of one entry on one target | `interventions.py:191-192` | 300 passed |
| A push with two operations | `interventions.py:183-184` | 300 passed |
| `above` given a list | `interventions.py:234-235` | 300 passed |
| A push naming a field and a group, or neither | `interventions.py:186-187` | 300 passed |
| A label push that sets something other than its entry's id | `interventions.py:202-204` | 300 passed |
| `is_one_of` given one value | `interventions.py:230-231` | 300 passed |
| A direction not given as east and north | `interventions.py:264-265` | 300 passed |
| Monthly amounts that are not all finite | `interventions.py:421-422` | 300 passed |
| An id used twice in the pushes file | `interventions.py:161-162` | 300 passed |
| A value that fits none of the allowed forms of a schema | `params.py:98` | 300 passed |
| A category, index or true-or-false field given fractions | `fields.py:72-73` | 300 passed |
| Message reworded: unknown profile | `engine.py:276` | 300 passed |
| Message reworded: "not valid YAML" | `params.py:149` | 300 passed |
| Message reworded: no value for a mesh level | `engine.py:43` | 300 passed |
| A table written with other columns than `tables.yaml` lists | `engine.py:552-553` | noticed (`KeyError`) |

- **How I know.**
  - `python W/scripts/mut_mine.py Q1 … Q16` (logs `W/out/mut_mine_4.log`, `mut_mine_6.log`) printed lines such as "Q1 NOT NOTICED [engine-files; 25 s] … 300 passed in 23.75s".
  - A grep of 18 distinctive wordings over `tests/` gave 0 lines for each; among them "exactly one of", "two pushes of this entry", "takes one value", "no profile named", "not valid YAML".
  - No other test file tests these: `ParameterError` occurs only in the four engine files and once in `tests/test_reference.py:560`, which is about sentence patterns.
  - These are refusals a user meets. `python -m worldengine order --profile preview --interventions W/pushes/a_two_tests.yaml` printed "refused: interventions.yaml[0] (probe): a condition needs exactly one of is_one_of, is, above, below". Seven more malformed files gave the other messages (`W/out/refusals_as_met.log`).
- **True wording.** "Not met in full. Every refusal of the scheduler is checked for its message. Of the engine's own, at least fifteen (the pushes file, the schemas, the profile, the mesh level) have no test: twelve can be taken out and three reworded with every test passing."

### 3. The new "why" sentence for a cell wholly under a closed lake (medium)

- **Claim.** "the answer now gives what arrives and what of it goes into the lake … none says anything that its numbers contradict. [MEASURED]" (`R/docs/BUILD_NOTES.md:1127-1144`). The new sentence is at `R/data/explanations.yaml:323`: "From upstream {from_upstream} reach the lake in this cell on the year's average."
- **Evidence.** For such a cell the amount is the water the routing carries on under the lake, so each cell along a drowned way says that the same water "reach[es] the lake in this cell".

| World | Cells wholly under a closed lake | With water from upstream | Answer gives more than the cells draining into it carry |
|---|---|---|---|
| My preview build | 16 | 9 | 5 |
| Builder's preview twin | 5 | 4 | 1 |
| Builder's standard world | 469 | 163 | 117 |

- **How I know.** `python W/scripts/why_drowned.py STORE` (log `W/out/why_drowned.log`).
  - Preview cell 7987 says "From upstream 18719 m³/s reach the lake in this cell".
  - The cells that drain into it carry 219.6 + 55.7 m³/s in `river_discharge`; its three drowned donors carry 0.
  - Its drowned donor 1170 says 18,444, and that cell's drowned donor 7988 says 16,740. The same water "reaches the lake" in three cells in a row.
  - The scan checks only the words "wholly under a closed lake" for these cells (`R/tools/why_scan.py:195`). Its rule on amounts covers partly flooded cells only (`:202-204`).
- **What holds.** The five kinds the fourth check found are gone (`W/scripts/why_five.py`, my preview world: 0 of each). My run of the scan printed "225324 answers read; none says anything its numbers contradict". The notes do add that the scan "proves nothing about faults of another kind".
- **True wording.** Add: "For a cell wholly under a closed lake the answer gives the water passing under the lake, and the scan has no rule for it: 117 of 469 such answers on the standard world give more than the cells upstream carry." Reword the sentence to "… pass under the lake here".

### 4. "One thing the check cannot show" (medium)

- **Claim.** "One thing the check cannot show: that the pass a hollow names is its lowest."
  - It stands at `R/docs/BUILD_NOTES.md:1572-1573`, `R/data/tables.yaml:22` and `R/src/worldengine/library/lakes.py:68`, and is repeated at `R/docs/BUILD_NOTES.md:1230`.
  - Section 9 also says "heights are those of the field `elevation`" (`:1567-1568`).
- **Evidence.**
  - The fourth check named two things (`S/review_step2c/report_physics4.md:125`): "…the lake stands at 894 m for 530 m. A pass into the sea is bounded from below only."
  - The second is still true and is not reported. The check is `spill[k] < high - slack` for a pass into the sea (`lakes.py:204`).
  - A test's own docstring says so: "the height of a pass into the sea is only bounded from below" (`R/tests/test_water_rules.py:874`).
- **How I know.**
  - `python W/scripts/sea_pass_too_high.py` printed "spill_m of the pass into the sea raised by 5000 m to 5010 m: ACCEPTED by check_table". Lowered by 3 m, it was refused.
  - `python W/scripts/sea_pass_hydrology.py`, on the builder's rough ground, printed "row 10: pass into the sea at -135.2 m, written as 64.8 m: Hydrology ran; notices []". The lake's area went from 191,897 to 967,530 km².
- **True wording.** "Two things the check cannot show: that the pass a hollow names is its lowest, and the level of a pass into the sea, which it bounds from below only. A level 200 m too high is accepted, and the lake stands 200 m too high."

### 5. What holds the scan's own rules (medium)

- **Claim.** "tests/test_world.py plants each fault in an answer and asks that the scan report it." (`R/tools/why_scan.py:26`)
- **Evidence.** The scan can report at 94 places (54 `must`, 15 `must_not`, 25 direct `wrong`). The test plants 28 faults. Each of the five kinds of the fourth check has one; most other rules have none.
- **How I know.** I took out four rules, one at a time, and ran `tests/test_world.py -k "scan_of_the_why or no_why_answer_for_water"`. Each run printed "2 passed, 31 deselected" (`W/out/mut_mine_2.log`):
  - "runoff under a lake must say wholly under a lake";
  - "a river must not name the cell's own runoff where the cell sheds none";
  - "a sea cell's river answer says 'This cell is sea'";
  - the level of a lake's answer held against the table of lakes.
  
  A fifth, "the lake fills hollow H", was noticed at `tests/test_world.py:668`.
- **Second claim.** "here it reads every seventh cell and every cell under a lake" (`R/tests/test_world.py:540-541`). The code takes `under_lake[::3]`: 1,563 of 10,242 cells, and 150 of the 318 cells under a lake.
- **True wording.** "…plants 28 faults, one for each kind the fourth check found; most other rules of the scan have no planted fault." And: "every seventh cell, every third cell under a lake, and every cell at a closed lake or at a brim".

### 6. "from then on each new test was run … to see it fail" (medium to low)

- **Claim.** "they were rewritten, and from then on each new test was run against the code as it stood, to see it fail." (`R/docs/BUILD_NOTES.md:926-927`, no label). The same paragraph says "Every finding marked high or medium that a test can hold has one" (`:924-925`).
- **Evidence.** The first sentence is carried unchanged from the step-1 notes (`git show a7b3fb0:docs/BUILD_NOTES.md`, lines 218-219). The record after it contradicts it:
  - `:939`: "Tests that could not fail";
  - `:1042-1043`: "the identity it was checked against could not fail";
  - `:1040-1041`: "one test accepted any of several refusals, so a check could be removed unnoticed";
  - `:1159`: "Tests that could not fail, and tools that no test ran".
  
  The second sentence is a totality I could not check beyond the fourth check; findings 2 and 4 are counter-examples of its kind. It is a suspicion.
- **True wording.** "…they were rewritten. The fault came back: the second, third and fourth checks of step 2 each found tests that could not fail."

### 7. Statements about other processors claim more than was run (low to medium)

- **Claims.**
  - "Two machines with different processors gave different last digits" (`R/docs/BUILD_NOTES.md:939`, in the row "Step 2, 2. Engine").
  - "The second reviewer of step 2 built the default world on a processor without the AVX-512 instructions" (`:1255-1256`).
  - "On a processor with other vector instructions the last bits … differ [MEASURED …]" (`R/src/worldengine/mesh.py:13-16`).
- **Evidence.** No second machine or processor was used by anyone.
  - `S/review_step2/report_physics.md:33`: "A build with numpy's AVX-512 paths switched off gives another fingerprint (differences up to 4e-6, no class changed)".
  - `:342` of the same report: the preview world, `NPY_DISABLE_CPU_FEATURES=X86_V4`, 20 fields.
  - `S/review_step2c/report_engine4.md:185`: 21 fields, at most 3.3e-6, on the preview mesh.
  - The labels at `:1257` and in `mesh.py` do say "switched off"; the sentences before them do not.
  - The finding is the physics reviewer's, the table's "Step 2, 1.". `report_engine.md` has no word on processors.
- **True wording.** "With numpy's AVX-512 code switched off, on the same machine, the preview world came out with other last digits. That another processor does the same is [INFERRED]." Move the item to the row "Step 2, 1. Physics".

### 8. The record of the last suite run and of the changes on purpose (low)

| Claim and place | What the builder's own logs show | True wording |
|---|---|---|
| "Run whole before this was written, the suite failed in five tests" (`R/docs/BUILD_NOTES.md:1218`) | `S/step2/fourth/final2/suite_with_data_first_try.log`: "4 failed, 749 passed, 34 xfailed in 530.48s". The fifth (`tests/test_contract.py:45`) failed in the run of the changes on purpose and was mended at 17:57, before that suite run. | "…failed in four tests; a fifth had failed by itself in the run of the changes on purpose." |
| "The numbers of section 1 are of the whole suite on the code as committed" (`:1224`) | The suite ran 18:11:38 to 18:27:51 on the working tree. `README.md` and `docs/BUILD_NOTES.md` were changed at 18:28:58; the commit is 18:30:41. `tests/test_world.py:708` reads the README. I ran `tests/test_world.py` on the commit: "32 passed, 1 xfailed in 309.41s". | "…on the working tree, 2 to 19 minutes before the commit; two text files changed after it, and the one test that reads one of them passes on the commit." |
| "The builds of the worlds, the test suite and the tools had the machine to themselves, but for two rows" (`:855-857`) | `S/step2/mut4/run_fb_fc.log` (18:14:26): two test runs of 73 s each ran inside the suite's run (18:11:38 to 18:20:54). | Add the suite to the exceptions. |
| "75 runs. The suite notices 71 … [MEASURED …]" (`:1235-1248`) | The counts hold. 73 of the 75 ran before 17:56 on older test files: `run_final.log` has failures at `tests/test_water_rules.py:947` and `tests/test_world.py:542`, where the commit has 981 and 550. Five files changed after. | "…73 of them on the test files as they stood at 17:56." My 12 re-applications on the commit were each noticed. |
| "The table is of 2026-10-05, after the fixes" (`:878-879`) | The four stores carry code fingerprint `b60504409eb6c1ba`; the commit's is `642db4929d0c2bcf`. `library/drainage.py` changed at 17:57, after the builds. My preview build of the commit equals the builder's store in all 52 fields and 63 table columns. Nobody built the standard world from the commit. | "The four worlds were built one change before the commit (a number of the library given a name)." |
| "The machine's speed changes from day to day, by a factor of two" (`:878`; `R/README.md:47-48`) | All three standard builds of step 2 are of one day: 1,186 s (log of 05:45), 580 s (12:20), 598 s (17:23), all 2026-10-05. | "changes within a day, by a factor of two" |

### 9. Small misstatements in section 5.3 and its table row (low)

| Claim and place | Evidence | True wording |
|---|---|---|
| "two of its fourteen rows hold more measured runoff than the rain data can supply" (`R/docs/BUILD_NOTES.md:1180-1181`) | One does: the Brahmaputra, 1,105 mm against 1,013 mm. `:594` itself says "Over its Columbia basin the runoff measured is 0.64 of the rain handed in". The fourth check said "Two rows cannot test Hydrology". | "two of its fourteen rows cannot test Hydrology: one holds more runoff than the rain handed in, the other 0.64 of it" |
| "Earth's '10 % under ice' … is [DOCUMENTED: National Snow and Ice Data Center] in all" (`:1205-1207`) | `R/data/models.yaml:144` and `R/src/worldengine/processes/albedo_surface_table.py:40` put "a tenth of Earth's land lies under ice" under "[MEASURED: docs/BUILD_NOTES.md, sections 4.6 and 8]". | Label those two, or say "in the notes and the tool". |
| "23 to the Earth harness and its tools" (`:1060-1061`) | All 23 are in `src/earth_reference/__init__.py` (`S/step2/mut3/list_third.py`). N5 named this line (`report_physics4.md:133`, `:137`); it is unchanged. | "23 to the Earth harness" |
| "Eight breakages of the first reviewer … were accepted. … The check now asks that …" (`:1145-1151`) | Seven are refused now. The eighth, two rows changed places, is still accepted: `python W/scripts/rows_swapped.py` printed "ACCEPTED by check_table". The table's description was changed instead ("no reader relies on that order"). | Add: "The eighth was a matter of the description, which now says that no reader relies on the order." |
| "still let eight breakages through" (`:941`) | 5.3 has eight and one. | "nine" |
| "48 ways of breaking the table" (`:1571`) | `:1152` says 49; the tests hold 49. | "49" |
| N10 (labels) has no entry in 5.3 | The row counts it among "9 low". Its items are changed where they stood. | One line in 5.3 for N10. |

### 10. "Two failures outside the default setting" (low)

- **Claim.** `R/docs/BUILD_NOTES.md:59`.
- **Evidence.** Section 3.2's own tables show three runs that fail condition B: the preview mesh resampled every 10 rounds (7.3 %, `:150`) and two of ten seeds (2.1 % and 2.9 %, `:163`). In four of the ten seeds the patch is consumed and A cannot be measured, on both meshes.
- **True wording.** "Three runs fail B outside the default setting, and in four of ten other seeds A cannot be measured."

### 11. Cross-references and attributions (low)

| Claim and place | Evidence |
|---|---|
| "(docs/BUILD_NOTES.md, section 5.3)" for the note on other processors (`R/README.md:52-53`) | The note stands under the heading 5.4 (`R/docs/BUILD_NOTES.md:1251-1263`), "What the fifth check … changed". It is not a finding of the fifth check, and section 6 does not list it. |
| "the first reviewer of step 2 found that" (`R/docs/BUILD_NOTES.md:94-95`) | It is in the engine report (`S/review_step2/report_engine.md:10`, `:91`), the table's "Step 2, 2.". `report_physics.md` has no word on it. |
| "which the build notes quote for the decision they led to" (`R/trials/climate_round_cost.py:6-7`) | The notes quote the 16 and 17 rounds once, as a comparison (`:884`), and name no decision. |
| "the Priestley-Taylor rule in the form of Davis et al. 2017" (`R/docs/BUILD_NOTES.md:237`) | `:1411` says "The rule is applied to the whole day, which is not the paper's way", and `:1588-1590` says the same. |
| "Left as found, and said" (`:1226-1231`) | One of its four items was changed: the trials now write only with `--write`. |
| "Step 2, 5. One reviewer" (`:942`) | Two reviewers share this check, by the common brief. |

### 12. Hock's Table 1 (low; the upper values are a suspicion)

- **Claim.** "[DOCUMENTED: Hock 2003 … her Table 1 gives 2.5 to 5.5 for snow" (`R/docs/BUILD_NOTES.md:1364-1365`).
- **Evidence.** Read twice through a page reader, the table gives these snow factors under "Non-glaciated sites": 2.5, 4.5, 2.7 to 4.9, 5.5, 2.8 to 4.9. For glacier sites it lists larger ones (Glacier AX010: 7.3, 8.7, 11.6). The reader's columns for the glacier rows were unreliable, so the upper values are a suspicion.
- **True wording.** "her Table 1 gives 2.5 to 5.5 for snow at sites without glaciers".

### 13. Docstrings of tests, and one label (low)

- `R/tests/test_tools.py:38-39`: "nothing is built, fetched or written". The test asserts the exit code, the first line and the listing of `worlds/` only. True wording: "no world is built".
- `R/docs/BUILD_NOTES.md:38`: "to within 1e-6 after 52 rounds [MEASURED: `tests/test_engine.py`]". I measured 8.49e-07 after 52 rounds, so the number holds. The test asserts 1e-5 and no count of rounds (`R/tests/test_engine.py:41`).

### 14. Missing from section 6 or from the README

- The design document is not updated (finding 1).
- The step-0 condition is not met in full (finding 2).
- "Not mended: the same world on another processor" stands in 5.4 only.
- Biomes' design test, agreement with the published map cell by cell, is not done; this is said at `:335-336` only.
- The crust trial's failures and the three duties for step 3 stand in 3.2 only.
- The viewer has no test in the suite beyond the server's answers; the browser check is a tool that needs a package the suite does not have.
- The contract test of imports and draws covers `processes/` only (`R/tests/test_contract.py:53`).
- No one has run a fresh install by the README's three commands with the new lock file.
- The scan has no rule for cells wholly under a closed lake (finding 3).

### In the other reviewer's part, one line each

- `R/docs/BUILD_NOTES.md:1511`: "no mend has been tried". The step-1 notes recorded one: "With a smaller constant (0.35 for 0.649) the same two continents swing 15.9 and 27.6 K" (`git show a7b3fb0:docs/BUILD_NOTES.md`, line 333).
- "two and a half to three times" (`:309`, `:661`) against "two to three times" (`:260`, `:783`).
- `R/src/worldengine/processes/energy_balance_spreading.py:33` has "15 to 48 %" where `:1507` has 11 to 47 %; I measured 11.1 to 46.8 %.

## 3. The fourth check's findings, one by one

The row "Step 2, 4." (`R/docs/BUILD_NOTES.md:941`) is a fair summary. The severities are right: 1 high (N1); 8 medium (N2 to N5, F1 to F4); 4 between (N6, N7, F5, F6); 9 low. The counts 126 = 33 + 93, 56 and 3,450 = 2,736 + 318 + 396 are right. Nothing is softened. The one slip is "eight breakages" for nine.

| Finding | In 5.3, at its strength? | Fair? | Mended? (mine only) |
|---|---|---|---|
| N1 high, cause stated as measured | Yes, "high" | Fair. One sub-point is not carried: over the Amazon basin the radiation is not shown too high. | Other reviewer |
| N2 medium, "every time" | Yes | Fair; all three parts | Other reviewer |
| N3 medium, the Volga | Yes | Fair | Other reviewer |
| N4 medium, check of the table | Yes | Fair for the eight, but see findings 4 and 9 | **Partly.** Seven of eight are refused (`tests/test_water_rules.py`: 72 passed). I took out four of the new checks, each alone; each was noticed at `tests/test_water_rules.py:868`. The eighth is accepted by a changed description. Of two things the check cannot show, one is reported. |
| N5 medium, tests that cannot fail | Yes | Fair | **Mended** for what it named. Tests run every tool (`tests/test_tools.py`; with `test_answers.py` and `test_store_server.py`: 91 passed). Its ten unnoticed changes are noticed in `S/step2/mut4/results.jsonl`, and the one I re-ran was. Its "and its tools" is uncorrected. |
| N6 medium-low, St Lawrence | Yes, "medium to low" | Fair | Other reviewer |
| N7 low to medium, boundary lengths | Yes | Fair | **Mended.** `python W/scripts/families.py 5 6 7` printed 272, 1,056 and 4,160 families, with 0, 2 and 29 split by rounding, as the builder's log has. The symmetry test passes on the standard mesh. "Turns with the planet" is gone. |
| N8 low, like for like | Yes | One misstatement (finding 9) | Other reviewer |
| N9 low, small numbers | Yes, "Smaller statements" | Fair. Three items are corrected in place but not listed (`:419-420`, `:1047-1050`, `soil_water.py:22-24`). | Other reviewer |
| N10 low, labels | **No entry** | Counted in the row only | Other reviewer |
| F1 medium, "not decided" | Yes | Fair. History checked: `41e3423` has "**Fails, by 4 km³ in 673.**"; `6f632d1` has "**Not decided by the relief data.**" | Other reviewer |
| F2 medium, "set before the run" | Yes | Fair. `git show f61f923:tests/test_earth.py` has "Found, then kept." | Other reviewer |
| F3 medium, "why" answers | Yes | Fair | **Partly** (finding 3). The five kinds are gone. |
| F4 medium, tests outside the water code | Yes | Fair | **Mended** for the 46 changes. My re-runs of seven were each noticed, for example at `tests/test_answers.py:29`, `tests/test_tools.py:118` and `tests/test_store_server.py:114`. The weakness remains where nobody probed (findings 2 and 5). |
| F5 medium to low, a pass to a far cell | Yes, under "medium" | Fair | **Mended.** With the neighbour check taken out: "Failed: DID NOT RAISE" at `tests/test_water_rules.py:868`. |
| F6 low to medium, first guess | Yes | Fair | **Mended.** `python W/scripts/first_guess_lineage.py`: with the default 288.15 changed to 283.15, 20 of 52 fields differ and none keeps its lineage fingerprint. With the mend taken out, `tests/test_engine_round2.py:388` fails. By the design the fingerprint covers what was handed to the field's writer and no more: the default world and the twin share 41 of 42 lineage fingerprints. |
| F7 low, tools took any option | Yes | Fair | **Mended.** All 9 tools and both trials: `--help` exit 0, `--no-such-option` exit 2. `fetch_reference_data.py --check` on a missing folder printed four "missing" lines and made no folder. |
| F8 low, statements | Yes | Fair | **Partly.** Six of seven are corrected. The label of "10 % under ice" is not the same in all places (finding 9). |
| F9 low, suite not run whole | Yes | Fair | **Partly.** The suite was run whole and passes (the builder's logs). Two files changed after it (finding 8). The trials write only with `--write`: I ran both; `git status` stayed clean. |
| F10 low, Windows | Yes, "read, not run" | Fair | **Mended as far as Linux shows.** The quotation is word for word in the documentation's source for Python 3.13 (`Doc/library/sys.rst`, lines 1841-1843). Python's code tables show cp932 lacks ² ³ ö. The rename is tried 6 times, 0.5 s apart. Nothing was run on Windows. |
| F11 low, two machines and a length | Not named; covered by item 20 | Fair | **Mended** by the families. The remainder is labelled "[INFERRED: not tried]" (`:1459-1465`). |
| F12 low, harness changes state | Yes, "Left as found, and said" | Fair | **Left as found, and said**; both function descriptions say so. |

## 4. Claims tested and found true

| Claim | Where | What I measured or opened |
|---|---|---|
| 787 tests; 753 pass, 34 expected failures; 97 skipped without data; about 9 minutes | `R/docs/BUILD_NOTES.md:27-32`, `R/README.md:114-120` | 787 collected on the commit. Builder's logs: "753 passed, 34 xfailed in 555.08s"; "689 passed, 97 skipped, 1 xfailed". I ran 608 of the 787 in pieces: all passed, bar the one expected failure. |
| Earlier rounds: 47, 62, 22 tests; 129 to 110; 81 to 75 | `:932-936`, `:985`, `:1059` | Collect-only on exports of `b1fc4e4`, `e571222`, `9bd38e2`; the builder's lists and result files |
| 75 changes on purpose, 71 noticed, one on the second run only | `:1233-1249` | `S/step2/mut4/list_fourth.py` and `results.jsonl`: 75 entries; not noticed by the last run: Fb, Fc, Hk, Hm. I re-applied 12 on the commit; each was noticed by the test named. Fb and Fc against wider selections: not noticed. |
| Preview world: 27 s, 23 rounds, 0.4 GB, 21 MB | `:861` | My build of the commit: 29.2 s, 23 rounds, 0.48 GB, 21 MB; equal to the builder's store in 52 fields and 63 table columns |
| The other rows of the run-time table and the round costs | `:859-876` | Builder's logs and stores: 598.5 s, 21.7 s, 364.6 s; 5.28, 0.58, 5.22 GB; 220, 20, 210 MB; tools 15.5, 71.4, 374.5, 18.7, 14.8 s. My scan: 118.5 s. |
| Four worlds the same before and after the fixes | `:896-900`, `:1173-1176` | My own comparison, entry by entry: identical |
| Before and after the third check: 48 of 52 fields; 146 and 557 coastal cells | `:1016-1023`, `:891-896` | My own comparison of the stores: as stated |
| Ties: 399 of 3,489 (199, 193, 7); 1,663 of 58,514 (780, 875, 8) | `:1009-1011` | `tools/world_report.py` on my preview world; builder's standard log |
| The scan reads 225,324, 156,728 and 225,324 answers and reports none | `:1141-1143` | My run on my preview world; 10,242 × 22 and 7,124 × 22; builder's logs for the other two |
| 49 ways of breaking the table, each refused in the words of its rule | `:1152` | 49 registrations in `tests/test_water_rules.py`; 72 passed |
| Section 4.8, both columns | `:906-915` | The step-1 notes at `a7b3fb0`; the builder's standard report |
| Mesh: areas to 12 digits; 1.36; 240, 120, 60 km | `:49-50` | 1.3585, 1.3611, 1.3618; 240.6, 120.3, 60.2 km |
| The scheduler was not changed by any review; 22 declarations | `:44-47` | `git log -- src/worldengine/scheduler.py`: the first commit only; 22 in `tests/design_declarations.py` |
| Crust trial: came with its first results; first run passed; five of six then failed A | `:116-123` | Commit `80e6de2`. The first version, run on today's plates: misses 1.59, 1.94, 1.85, 1.37, 0.94, 1.31. The tables equal the stored result files. |
| The design fixes three conditions with "a stated share" | `:112-116` | The live document, and a copy dated 02:56 on 2026-10-04, 33 minutes before the first commit |
| Ten seeds: poles −10 to −23 °C; 11 to 47 % white | `:201`, `:1507` | −10.0 to −22.7 °C; 11.1 to 46.8 % by the report's own measure |
| A "why" answer from a store takes under a millisecond | `:980` | Median 0.2 to 0.5 ms after the first of a view; the first took 0.17 s |
| Section 7, item 20: the numbers, and "both reviewers then proposed the families" | `:1444-1475` | My families run; `report_physics4.md:208` and `report_engine4.md:134` |
| On Earth's relief the wider way settles 6,521 ties, was 6,508 | `:1176-1177` | The two logs of `earth_relief.py` |
| Rain law; snow cover rule | `:1307-1308`, `:1366` | Bretherton, Peters and Back 2004, equation 2; Dutra et al. 2010, equation A2 (page reader) |
| The README's commands and its example answer | `R/README.md:34-43`, `:65-83` | All run with the preview profile. The answer equals the README's piece for piece. The viewer page loads no outside code. |
| Every tool explains itself and refuses an unknown option | `R/README.md:134-135` | All 9 tools and both trials, run by me. The test of the unknown option leaves out `crust_points_trial.py`. |
| The lock file pins the versions tested with | `R/README.md:16` | The lock equals the installed versions (dry run) |
| The stored trial files are of step 1 | `R/README.md:131` | `git log -- trials/results`: last changed in `9bd38e2`; 16 and 17 rounds |

## 5. What I did not check

- The standard profile, except through the builder's stores and logs.
- The whole suite in one run. `tests/test_earth.py` and `tests/test_water.py` (179 tests) I did not run unmutated.
- The 63 other changes on purpose that the builder ran again; I read their results only.
- The crust trial on the standard mesh; `climate_round_cost.py standard`; a fresh install; `fetch_reference_data.py` without `--check`.
- Windows, another processor, and the high_fidelity mesh. Its family numbers are the builder's log only.
- These sources: North et al., Juárez et al., Barnes et al., the National Snow and Ice Data Center, Manabe. Hock, Dutra and Bretherton I read through a page reader, not as a PDF.
- The Earth tools beyond `--help`, the Huang He's 48 flooded cells, and the 100 settlements.
- "44 changes … each noticed" of step 1.
- "I repeated each measurement with tools of my own … and each held".
- That the design was approved before any code was written.
- Whether the archive to be handed over holds `worlds/first.zarr`. The one in `R/worlds` carries the commit's code fingerprint.
- The first-build numbers quoted in section 7 (4 to 15 mm, 72 m of rain, one seed in 32).
- The "How to add things" bullets, other than the harness.
- The design document beyond its departures table, its build-order row for step 0 and twelve searches.

Three things to declare:
- At the very start I ran `git status --short` and `git log` once inside `R`. `.git/index` still carries the commit's time; no file under `R` changed.
- I opened the design document read-only, although the brief assumed I could not.
- I removed the `mesh` link from my folder of data links, so that nothing was written beside the original data.

Sources:
- [Design document, "World engine design: physical causes, replaceable processes"](https://claude.ai/code/artifact/0ad5d499-95b9-4211-8e8c-74651f03652b)
- [CPython 3.13, Doc/library/sys.rst](https://raw.githubusercontent.com/python/cpython/3.13/Doc/library/sys.rst)
- [Dutra et al. 2010](https://www.fs.usda.gov/rm/pubs_other/rmrs_2010_dutra_e001.pdf)
- [Hock 2003](https://www.oocities.org/haniskywalker/hock2003.pdf)
- [Bretherton, Peters and Back 2004](https://www.aos.wisc.edu/~lback/wvpprecip.pdf)
