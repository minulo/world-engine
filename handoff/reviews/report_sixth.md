# Sixth check (narrow): what was rewritten on 2026-10-06

Repository /home/claude/world-engine, HEAD 21447f6. Nothing under it was changed: `git status --short` is empty after my runs [RAN]. Labels: [RAN] I ran it; [READ] I read a log, a test or a text; [INFERRED] my reasoning. Line numbers are of HEAD.

## 1. Verdict

1. The numbers hold again: every table cell and almost every hand-typed number I traced stands in a log of `handoff/logs/` or in an assertion [READ], and the one set I recomputed came out the same [RAN].
2. The account again says more than its own logs in one place that matters: the builder's log for valley share 0.07 has the Caspian's overflow reaching the SEA in 2 of the 3 random settlements that overflow, and at 0.5 in 20 of 20. Sections 4.5, 5.4 and 11 (question 3) do not say so.
3. The head says the fifth check "found no wrong number"; section 5.4 itself lists wrong numbers it found (five for four, eight for nine, 48 for 49, 161 and 63 for 158.7 and 64.0).
4. In the test file, four numbers of the twin's reasons are held by no assertion, two of those reasons state an unmeasured cause without a label, and the Volga test's docstring contradicts the notes (runoff "twice" against "three times"; 0.80 to 0.92 against 0.80 to 0.97).
5. The mends I spot-checked are real (design document, refusal audit, 65 cases, suite counts, run times).

## 2. Findings, most serious first

### S1 (medium to high). Where the Caspian's overflow ends depends on the valley share; the notes report only the share at which it never reaches the sea

- **Place.** `docs/BUILD_NOTES.md` section 4.5, "What the rows show" (lines 727-746) and its table (711-725); section 5.4 line 1278-1280 ("into a second, closed lake, not to the sea"); section 11, question 3 (1830-1836: "none reaches the sea, as built or in any of 100 random settlements. No water of the Caspian's basin leaves for the ocean").
- **Claim.** Read together: the overflow ends in a neighbouring closed lake, and the open question is only whether that counts as "closed". Section 4.5 presents thirteen shares and says what they show; where the overflow ends is not among it.
- **Evidence.** [READ] `handoff/logs/shares/share_0.07.log`, last line: "at random: closed in 17 of 20, overflow up to 3.92 km3 a year, ...; of the 3 that overflow, the water reaches the sea in 2". `share_0.5.log`: "of the 20 that overflow, the water reaches the sea in 20". At the other shares that overflow (0.05, 0.08, 0.09, 0.1, 0.12, 0.2, 0.3) it is 0. [RAN] `grep -ho 'of the [0-9]* that overflow, the water reaches the sea in [0-9]*' shares/*.log`. `handoff/notes_tools/logs.py:175-179` parses this very count (`to_sea`), and `sec4.py:106` prints it for the tenth only; the table of 4.5 has no such column.
- **Why it matters.** Question 3 asks the owner to rule on a Caspian "whose overflow ends in a neighbouring closed lake". The statement is true at the tenth (0 of 19, 0 of 93). At 0.07, three hundredths away and inside the band the notes call unsafe, the builder's own run has water of the Caspian's basin leaving for the ocean. The sentence "No water of the Caspian's basin leaves for the ocean" is a fact of one share.
- **True wording.** "At the tenth the overflow ends in a closed lake, as built and in the 19 of 20 and 93 of 100 settlements that overflow. That too depends on the share: at 0.07 it reaches the sea in 2 of the 3 settlements that overflow, and at 0.5 in all 20. Whether it reaches the sea as built at 0.5 I did not look." And a column "reaches the sea in" in the table of 4.5.

### S2 (medium). "It found no wrong number" (the head) against section 5.4's own list

- **Place.** Notes line 8 (head): "It found no wrong number and again found that the account claimed more than was measured". The same in the table of section 5, line 939: "No wrong number: every number that a tool prints was printed again by the reviewers and came out the same".
- **Evidence.** [READ] Both reports open "The numbers hold", and both then list wrong numbers in the texts: `report_record5.md` finding 8 ("failed in five tests": four), finding 9 ("eight breakages": nine; "48 ways": 49; "two of its fourteen rows": one), finding 10 ("Two failures": three), its last lines ("15 to 48 %" where 11 to 47 % was measured); `report_numbers5.md` R15 ("return 161 and 63": the code's comment has 158.7 and 64.0; "every column ... two to three times": the 0.5 column is 3.0 to 5.7; "Eleven of the twelve" lists ten; "7 K too cold (2.0 C against 9.3 C)" was of all cells, not land). Section 5.4 lines 1353-1364 repeats most of these. So the head contradicts 5.4.
- **Second half.** "every number that a tool prints was printed again by the reviewers" (line 939; 5.4 line 1263-1264 "every number that a tool prints they printed again and got the same. [MEASURED by them]"). [READ] `report_numbers5.md` line 7 goes on: "the builder's logs for 100 settlements, the six shares, the twin and the two worlds agree with the texts", and its section 5: "Not run: the standard profile, 100 settlements, the whole suite, the twin's build. Held against the builder's logs and stores." Five of six shares, the 100 settlements, the twin and both worlds were read, not printed again.
- **True wording.** "No number that a tool prints was found wrong: the reviewers printed again what runs in minutes and read the builder's logs for the 100 settlements, five of the six shares, the twin and the worlds. About ten counts and small numbers typed in the texts were wrong (section 5.4)."

### S3 (medium). Twin reasons in `tests/test_earth.py`: four numbers that no assertion holds, and two causes without a label

These reasons were not rewritten today, but they are in the part of the file I was given.

| Place | Number or cause | What holds it |
|---|---|---|
| line 1550, reason of the group D test | "the polar group E 46.3 % ... [MEASURED]" | Nothing. [RAN] `grep -n '46\.3' tests/test_earth.py` gives this line only. The last test pins D at 2.1 and the snow at 35.3; `test_the_twins_report...` compares the tool's row with a value worked out in the test, not with 46.3. The number is true [READ `handoff/pass2/twin_seasons.log`: "group E: 46.3 %"; `worlds/twin_preview.log`] |
| line 1571-1572, reason of the driest band, north | "Earth's own rain over the same cells is driest at 39 degrees [MEASURED]" | Nothing in the test file. True by the log (38.9) [READ] |
| line 1573, same reason | "poleward of 60 degrees 181 mm against 495" | Nothing. True by the logs (180.6 and 495.0) [READ] |
| line 1354-1355, `INLAND_MISSED` | "Under the water poured before the fifth check the lake stood at 0 m and this test passed" | Nothing: `test_the_water_poured...` (191-230) asserts the sea level, the cells, the mouths, the gauges and the Caspian under the other water, not the Black Sea's lake. True by `handoff/logs/planet_relief.log` line 26: "a lake of 472,814 km2 stands there at 0 m" [READ] |
| line 1550-1552 | "with summers as weak as the test above measures, northern land that has warm summers on Earth stays under 10 C in its warmest month" | Not measured in this form anywhere I could find. The log has the MEAN warmest month of the land at 40 to 60 north (1.4 C); no cell-wise count under 10 C. Stated after "[MEASURED]:" with no label of its own |
| line 1572 | "The twin's northern land is too cold and so too dry" | A cause, unlabelled. The neighbouring reason (1584-1587) says of the same chain "was not measured link by link [INFERRED]" |

- **True wording.** Pin 46.3, 39 (38.9), 181 and 495 and the Black Sea's 0 m in a test, or cite the log beside each. "... [INFERRED: that this is why group D is missing; the share of that land whose warmest month stays under 10 C was not counted]". "... too cold and too dry [the link INFERRED]".

### S4 (medium to low). The Volga test's docstring contradicts section 4.4, point 6, and the tool

- **Place.** `tests/test_earth.py` 1254-1276 (rewritten today) against notes 560-583.
- **Claims.** Docstring: "The source gives the runoff twice, and the two do not agree"; "the model sheds between 0.80 and 0.92 of the published runoff"; "IF the rain data's 747 mm are right, the model sheds 1.3 to 1.8 times". Notes: "The source gives the runoff three times, and the three do not agree" (193, 222, 184 mm); "0.80 to 0.97"; "1.29 to 1.88".
- **Evidence.** [READ] `rivers.log` Volga block has three figures and the columns "over the 193 / 222 / 184": 0.92, 0.80, 0.97 and 1.79, 1.55, 1.88, 1.49, 1.29, 1.56. The third figure was the fifth check's R4 ("A third published figure is left out"); the docstring still leaves it out. The test's own `pinned` rows hold only two ratios per row; the third column and the April depths (322, 223, 160, 232) are held only as strings of the tool's print in `test_the_reports_of_the_tools...` (lines 1120-1123), so "a test holds the four rows" (notes 574) is true by that other test. All four rows are there [READ].
- **Also.** "of its 345 mm, 120 go with the larger total and 47 with the harness's snow" is one order of taking the two apart; in the other order it is 58 and 109 (345 - 287 = 58; 287 - 178 = 109) [my arithmetic from the log]. Stated as the split.
- **True wording.** "three times ... 0.80 to 0.97 ... 1.29 to 1.88", as the notes; "120 and 47, or 109 and 58 taken in the other order".

### S5 (low to medium). "The water of all the land moves little, and one way"

- **Place.** Notes 731-733: "The larger the share, the more land lies under lakes (5.87 to 6.94 %) and the less water reaches the sea (30.99 to 30.25)".
- **Evidence.** [READ] The table two paragraphs above, and `share_0.07.log` / `share_0.08.log`: lakes 6.21 % at 0.07 and 6.19 % at 0.08; to the sea 30.74 at 0.07 and 30.75 at 0.08. One step of twelve runs the other way in both columns.
- **True wording.** "With one step back between 0.07 and 0.08, the larger the share, the more ...".

### S6 (low to medium). "What does not depend on the ties", from 20 draws

- **Place.** `tests/test_earth.py` 1230-1231 (Caspian reason): "What does not depend on the ties is that the lake is far too large: 1.07 to 1.09 million km2"; assertion comment at 1328 "that is no matter of ties".
- **Evidence.** Held over the engine's settlement and 20 draws (assertions 1326-1328) [READ]. The fifth check's R15 named this shape ("however the ties are settled", "whatever the ties": "These are 100 of 100 draws"). The notes' own rule (line 400-401): "in none of 20" rules out only what comes more often than about one time in seven.
- **True wording.** "In the engine's settlement and in each of 20 random ones the lake is far too large: ...".
- **Same shape, notes line 663:** "it reaches the sea in none of the settlements" has no count in the sentence; the counts (19 of 20, 93 of 100) stand elsewhere.

### S7 (low). "The logs of the Earth tools agree number for number ...; two lines of the tools' wording had changed since" (5.4, line 1379)

- **Evidence.** [RAN] `diff` of each log with `handoff/logs/before_rerun/`. `rivers*.log`, `planet*.log`, the shares and the traces: one line of wording each ("over the land without the lake" for "over that land"), numbers identical. `rivers_s100.log` line 211: "65.5 over 85.8" where the snapshot has "85.7", a number in a sentence. `relief.log`: five lines are new (the lakes and closing cells of the Black Sea, the Red Sea, the Baltic, the Caspian), the "diagnosis" line is new, and one line changed its measure and its counts: snapshot "0 are handed to Drainage at 1 m or lower, and 0 of those ..."; now "248 are handed to Drainage no more than 5 m above the sea of the mesh ..., and 10 of those".
- **True wording.** "Every number that the two sets of logs share is the same but one typed 85.7 that is now 85.8. Since the snapshot one line of wording changed in the rivers tool, and the relief tool prints seven lines more and counts the coastal cells by another rule (248 and 10 where it had 0 and 0)."

### S8 (low). Counts typed in 5.4 that are not the reports'

- "Three cross-references and attributions" (1362-1363). [READ] `report_record5.md` finding 11 has six rows. I found five of the six changed in the texts (the README's reference, "the second review ..., the engine's", `climate_round_cost.py`, "applied to the whole day, which is not the paper's way", "Two reviewers" in the table).
- "Eight things that were not done stood elsewhere or nowhere; they are in section 6 now" (1365-1366). [READ] The report's finding 14 has nine bullets; section 6 gained nine items (11 to 19), of which six are bullets of that finding, one is the design document in a new form, and two come from other findings. I could not make eight of it.
- Not carried into 5.4 at all [READ]: R6's second part (the Danube's and the Lena's other way exists only on the mesh; the reviewer's true wording names the Lena's divide at 122 m against 152 m); R14's "the 0.62 is in the tool's report and in a test. It is in neither"; record finding 8, third row (the suite did not have the machine to itself); record finding 9, second row (the label of "10 % under ice"). "Smaller, each corrected where it stood" cannot be checked for items that are not named.

### S9 (low). Small inconsistencies and unlabelled statements

- Notes line 15: the build environment had "about 8 GB of memory" and the measurements of 2026-10-06 were made "in a fresh workspace of the same kind"; section 4.7, line 861: "about 7 GB". [READ]
- Notes line 677: "The Volga gives most of it" (of the 590 km3 that reach the lake). No log line gives the Volga's flow into the lake. It follows roughly from 1,222 thousand km2 x 345 mm = 421 km3 shed above Volgograd, before any lake on the way loses water [my arithmetic]; unlabelled.
- Section 11, question 2 (1826-1828): "section 4.4 shows that the gauges test the relief data and the precipitation handed in at least as much as they test Hydrology". Section 4.4 says "more than they test Drainage" and measures no such ranking against Hydrology; "at least as much" is a judgment. [READ]
- `tests/test_earth.py` 1366-1368 (docstring kept today, with a sentence added before it): "This test passes under any wet climate, since these hollows then overflow whatever the rain". One climate was run, and for the Black Sea the test is now an expected failure. [READ]
- `HANDOFF.md` line 15 at HEAD still says of the design document "it has not been updated for step 2", against notes 5.4, 6 (item 19) and 7. The document is updated (below). Outside my scope; one line for whoever reads the hand-over.

### Categories with nothing found

- C (labels): nothing labelled MEASURED that was only read from a reviewer without saying so; where a reviewer's number is used the text says "MEASURED by a reviewer ...; I did not repeat it" (4.6, 5.4). One odd source: section 7, item 14, "[MEASURED for the formulas: the comment in `data/models.yaml`]" for 158.7 and 64.0; a test does hold them (`tests/test_water.py` 949-954) [READ].
- G: beyond S1 and the "at least as much" of question 2, the four questions state what the logs and tests show.

## 3. Claims tested and found true

| Claim | Place | What I checked |
|---|---|---|
| 864 tests, 829 pass, 35 expected failures, 575 s; without data 761 pass, 102 skipped, 1 expected failure, 396 s; on d116240 | 1; README | [READ] `suite_with_data.log`, `suite_without_data.log`, `suite_code_state.txt`; [RAN] `git diff --stat d116240 21447f6`: only notes, README, logs and notes tools changed after |
| 249 refusals, all reached, all held; 847 s; 65 cases | 2, 5.4, 4.7 | [READ] `refusal_audit.log` (249 "held" lines; "held by a test: 249 of 249"), `.time` 846.8 s; [RAN] collect-only of `tests/test_refusals.py`: 65. The log also says "6 raises pass on words made elsewhere", which the tool's description explains |
| The table of 4.2: 354 and 270 km; 20 of 20; 144,605 m3/s at 297 km; 17.9 of 590; 1 of 20, 7 of 100; 19,939 km2 at 42.2, 57.1; 0 of 93; 8 and 13 | 4.2 | [READ] `rivers.log`, `rivers_s20.log`, `rivers_s100.log`, `traces/trace_Amazon.log`, test 675 |
| The table of 4.3: 13/7/4, 6/10/5, 13 to 16, 6 to 9, 0.738, 30.7, 117.2, 0.69 and 0.66 and 52 %, 6.3 %, 880,226, the three lakes, 78 % and -5.6 m and 32 m, 15.8 m and 65 %, 2.1 m and 75 %, 1.00 and 0.93 m | 4.3 | [READ] the same logs, `relief.log` part 4, tests 1379-1397 |
| Biomes: 20.9 / 24.9 / 13.3 / 26.5 / 14.5 | 4.3 | [RAN] my script `sixth/biomes.py` on `earth_reference.Earth(7)`: the same. No test pins these five; the test asks only for 6 points |
| 4.4 point 1: 13.3 %, 10.5 %, 3.7 %, 11 of 12, the narrows table, 5 of 6, 48 %, 16,510 of 47,962, 9,641 of 42,657, 3,341 / 6,249 / 51, 4,578, 14.9 % and 0.04 %; 3,418 / 2,956 / 1,125; 162 and 204 m | 4.4 | [READ] `relief.log` parts 1 to 3, `rivers.log` part 5, test 553 |
| 4.4 point 2, every cell of the table of ties | 4.4 | [READ] `rivers_s20.log` and `rivers_s100.log`, part 7, cell by cell |
| 4.4 point 3: nine rows; the Ob 71 km, the Danube 203 km, the Amazon 297 and 203 km; the Huang He "the rarer outcome of the 20, though not of the 100" (7 of 20 fail, 57 of 100 fail); Mississippi 295, Mekong 292 in every settlement | 4.4 | [READ] the logs, three traces, `planet.log` |
| 4.4 point 4 and 5, both tables (all 21 and all 15 rows), the books (1.0e-05; 5.8e-08), 0.69 / 0.66 / 0.60 / 0.73 / 0.62, 10 and 5, snow 0.09 to 0.41; the Congo at 0.02 (239 km3, 0 of 20), the Yangtze 0.22, the Lena 0.42 in 33 of 100 | 4.4 | [READ] `rivers.log` parts 1 and 2, `rivers_s100.log`, `shares/share_0.02.log` |
| 4.4 point 6: the four rows, 43 %, 47 to 58 mm, April in every row, 1,222,000 km2 | 4.4 | [READ] `rivers.log`; my arithmetic for 193, 222, 184, 47, 58 |
| 4.4 point 7: both radiation tables, 1.31, 1.17, 20.3 = 0.8 + 8.2 + 11.3, 0.61 and 0.76, 13 %; the table of the cuts, every cell | 4.4; 7 item 14 | [READ] `demand.log`, `rivers_s100.log` part 8; test 951-952 |
| 4.4 points 8 and 9: 1.09 million km2 at 61 m, 590, 2.96 and 4.05, 199 mm, 933 and 408 mm, 4 cells; 0.708, 3.1, 0.5, 580 mm, 561 lakes, 41.1 | 4.4 | [READ] `rivers.log` parts 4 and 5; assertions 1332-1342 |
| 4.5: the thirteen rows (I compared ten of the twelve logs line by line for mouths, gauges, the lake, like for like, lakes, back to the air, to the sea); 6 and 7 shares; 4 shares with 20 of 20; 0.89 to 1.14 and 2.4 to 3.1 times; 0.74 outside 0.68 to 0.71 at 0.05 | 4.5 | [READ] `shares/*.log` |
| 4.5, another reading: 232 km, 1,212 km, 16 for 15, 8 for 8, 5.57 for 6.28 % | 4.5 | [READ] `relief.log` part 5 |
| 4.5, the water poured: every row; 7.2 m, 771, 3,850 | 4.5 | [READ] `planet.log`, `planet_s20.log`; assertions 217-226 |
| 4.6 changed paragraphs: -12.6 / -12.7, 1.4 / 18.4, -5.8 / 3.5, 52 %; the twin table against the new logs (both columns, every row I read) | 4.6 | [READ] `pass2/twin_seasons.log`, `worlds/twin_*.log`; assertions 1650-1655 |
| 4.7: every row of the table; 21 / 220 / 20 / 210 MB; 225,324 and 156,728 answers, none reported; the tree of 8e5f588 with two files modified | 4.7 | [READ] the `.time` files, `worlds/sizes.txt`, `scan_*.log`, `worlds/code_state.txt`; 10,242 x 22 and 7,124 x 22 |
| "between the two only the README, the reasons of two tests and the hand-over files changed" | 5.4 | [RAN] `git diff 8e5f588 d116240 -- . ':!handoff'`: README and `tests/test_earth.py`; in the test file two reasons and one added assertion of arithmetic |
| Severities and counts of the fifth check (3 high, 2 between, 6 medium, 18 lower); the findings named in 5.4 at their strength | 5, 5.4 | [READ] both reports, finding by finding |
| The design document is updated | 5.4, 6 item 19, 7 | [RAN] read-only searches of the live document: revision 470 (462 at the fifth check); "wider way" now 1 hit in a table of departures; "306 mm" now in "before step 2 it got 306 mm"; "snow_cover" 0 hits in the field dictionary, as item 19 says. I did not count its rows 10 to 25 |
| Section 11: 13.6 and 30.9 K; 46 % and 13 %; 35 %; the four pass marks (three quarters of 31 K, 15 %, 15 to 40 degrees, three quarters of the rain) | 11 | [READ] `worlds/twin_standard.log`; test lines 1547, 1560, 1581, 1596 |
| README: 864, 35, 102, about 10 minutes, 0.69, a quarter of an hour, 4 to 6 minutes | README | [READ] the logs above; `rivers_s100.log.time` 252.5 s |
| Caspian reason, `INLAND_MISSED`, lakes reason, Congo reason, the three other twin numbers (13.4 / 31.1, 2.1, 58 with 273, 440 / 654, 35.3): each number held | tests 1226-1655 | [READ] assertions 1173-1181, 1319-1342, 1379-1386, 1428-1440, 1636-1655; `NARROWS_*` for 457, 610, 274 |

## 4. What I did not check

- I ran no test of `tests/test_earth.py` and none of the Earth tools; everything about them is from the builder's logs and from reading assertions. Whether the assertions pass today rests on `suite_with_data.log`.
- The standard world, the twins, the 100 settlements: logs only.
- Shares 0.13 and 0.15 line by line (only their last lines); whether the overflow reaches the sea as built at 0.5.
- The part of `tests/test_earth.py` before line 1226, except where an assertion there holds a number of the notes; `OFF_AT_GAUGE` and `MISLED` reason by reason; so "none names a cause that was not measured" (5.4) is unchecked for the gauges.
- The Nile's way west of 28.5 east (I saw the assertion at line 295, not the trace); the 24 traces other than three.
- Items 22 to 25 and 14 of section 7 beyond the numbers of item 14; section 9 item 1 beyond its agreement with the fifth report; the mends of the "why" answer and of the scan's planted faults in the code.
- Every published source. The messages to the owner that 5.4 mentions.
- The design document beyond three searches.
