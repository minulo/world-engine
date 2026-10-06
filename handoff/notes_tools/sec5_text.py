"""Section 5.4 of docs/BUILD_NOTES.md and the row of the table of rounds that goes with it. Typed by hand from the two
reports of the fifth check (handoff/reviews/) and from what was changed in answer; the slots are filled by
build_notes.py from measurements."""

FIFTH_HEAD = ("A fifth check, by two reviewers, looked at nothing but the claims: these notes, the README, the reasons of "
              "the tests and the descriptions in the code. It found no wrong number and again found that the account claimed "
              "more than was measured (section 5.4). The answer to it was written in two sittings; the second worked from the "
              "first's written hand-over and logs (`HANDOFF.md`, `handoff/`), and measured every number of sections 4.2 to "
              "4.5 again on the committed code.")

FIFTH_ROW = ("No wrong number: every number that a tool prints was printed again by the reviewers and came out the same. 3 "
             "findings marked high, 2 between high and medium, 6 medium and 18 lower, all in what I had claimed. \"The "
             "closed Caspian fails at this share alone\" was false: it fails at shares between the six I had tried. The "
             "Earth tests poured another volume of water than the design's row names, and the outcomes turn on it. The "
             "random settlements still left one step undrawn, level ground. The Volga's \"the model's part lies between "
             "nothing and a fifth\" rested on a premise the notes could not decide. The notes said that all 21 departures "
             "are in the design document; 13 were not. \"Every refusal message is tested: Pass\" was false: fifteen "
             "refusals could be taken out or reworded with every engine test passing")


def sec54(x):
    return f"""### 5.4 What the fifth check of step 2 changed

Two reviewers, neither of whom had seen the work, with one brief: the claims alone. One took the
numbers of sections 4.2 to 4.6 and 8 and the reasons of the Earth tests; the other took the record
of the checks, the engine's own claims and the hand-over texts. Their reports are in
`handoff/reviews/`. Both begin "The numbers hold": every number that a tool prints they printed
again and got the same. [MEASURED by them] What they found was in the account built on the numbers.
I repeated the measurements that the changes below rest on; where I only read a reviewer's number
the text says "measured by the reviewer".

One thing first, because you read it. In a message to you on 2026-10-05 I wrote of the closed
Caspian: "It fails only at the setting I built with." That sentence was false. I had tried six
valley shares and it failed at one; I had not tried the shares between them. The fifth check did:
it fails as built at shares on both sides of mine. The hand-over notes of that sitting record that
I told you so in a later message. [DOCUMENTED: `HANDOFF.md`; the messages themselves are not in the
repository] Section 4.5 now gives thirteen shares.

**Claims that were false, or stronger than the evidence.**

* **"It fails at this share alone" (high).** Above. Section 4.5 is rewritten on thirteen shares. The
  reviewer also traced where the overflow goes, which no text said: into a second, closed lake, not
  to the sea. The harness now follows the water (`earth_reference.lake_books`), the tool prints it,
  and whether that meets "stays a closed lake" is put to you (section 11).
* **The water poured (medium to high).** The design's row for SeaLevel names "the volume of sea water
  measured from that relief at full detail". The Earth tests poured the planet file's volume, 0.19 %
  less, and no text named it as deciding anything. With the relief's own volume the sea of the mesh
  stands at +1.9 m for −5.3 m, and outcomes move (section 4.5, the last table). The harness now
  pours the relief's own volume, which is the design's; `--sea-water planet` keeps the other for
  comparison; and every number of sections 4.2 to 4.5 and of `tests/test_earth.py` was measured
  again. The Earth twin still pours the planet file's volume, and its tool says so.
* **Level ground (medium).** A random settlement drew the widths, the order of the cells and the
  choice among passes, and left the way over level ground as the engine has it. It now draws that
  too (`Ties.level` in `library/drainage.py`; the engine's own path is unchanged). The counts of
  section 4.4 are of settlements that draw all four.
* **The Volga (medium to high).** "Most or all of the excess comes with the rain data; the model's
  part lies between nothing and a fifth" needs the published precipitation to be the true one, and
  carried the harness's share of snow into the published case. The harness now runs four
  precipitations, the tool prints them with the source's third figure for the runoff, and section
  4.4, point 6, states them conditionally. The test that carried the conclusion in its name is
  renamed.
* **The share of sunshine (medium).** "The one thing a share of sunshine sets" was false: the share
  enters the heat-loss formula as well. Section 4.4, point 7, and section 7, item 14, say so; the
  tool prints the table of shares; and the sentence "the error of the one share of sunshine is six
  times as large", a cause that the fourth check had already found unmeasured, is gone from section
  7 and from `library/evaporation.py`.
* **Causes of the gauge misses (medium).** The sorting of fourteen misses by cause is withdrawn
  (section 4.4, point 4). The reasons of the expected failures were written again; each gives what
  was measured beside the miss and none names a cause that was not measured.
* **The Caspian's catchment (medium to low).** I had set 4.06 million km², which held the lake,
  beside the real rivers' 3 million, which does not. Like for like the land is not larger (section
  4.4, point 8).
* **"1.17 times what a published budget gives it" (medium to low)** is on rain that differs from
  the budget's. Sections 4.3, 4.4 and 8 give the shares of the rain and both amounts of rain.
* **Smaller, each corrected where it stood (low to medium, and low).** "All snowy lands of the
  northern mid-latitudes" (two of the four were not snowy). The twin's lakes "on the same relief
  (8.5 % for 6.0 %)": the twin's Drainage is handed mean heights and the 6.0 % was of the valley
  rule; the sentence is gone, and what the reviewer measured stands in section 4.6. "Their inputs
  are the truth": the snow is made, not measured. The order of section 8 "by how much they distort
  the world" has no measure and is now called a judgment. "Three tools print every number in this
  section" was not so. Two rows of section 8's table are not printed by the tool the table named.
  "Every column shows … two to three times". "Was written before it was run". The twin's land "7 K
  too cold (2.0 °C against 9.3 °C)" was of all cells, land and sea; and the cause given for the
  weak seasons, "one constant that ties the land to the sea too tightly", does not fit what the
  reviewer measured: the twin's winter is right and its summer 17 K too cold (section 8). "Narrower
  than a cell" for the Red Sea and the Baltic. "Eleven of the twelve" listed ten. The tool for the
  demand still called the budget "measured".
* **The design's third pattern for Hydrology** ("River flow data is still to be chosen") was left
  out of section 4.2. It is there now, as a question to you.

**The record.**

* **The departures of step 2 were not in the design document (high).** Section 7 said "Each is
  recorded in the design document as well". The document held nine, all of step 1; items 3 and 9 to
  21 of section 7 were not in it, and two of its rows were not in section 7. {x['design_doc']}
* **"Every refusal message is tested: Pass" (high).** The reviewer took twelve of the engine's
  refusals out and reworded three, one at a time; all 300 engine tests passed each time. New:
  `tests/test_refusals.py`, 65 cases, and `tools/refusal_audit.py`, which finds every refusal in the
  code of `src/worldengine`, notes which tests reach it, writes other words in its place in a copy
  of the folder and runs those tests. {x['audit']}
* **The "why" answer of a cell wholly under a closed lake (medium).** The sentence I had written
  to answer the fourth check gave, in every flooded cell along a drowned way, the same water as
  "reaching the lake in this cell": 117 of 469 such answers on the standard world gave more than
  the cells upstream carry. [MEASURED by the reviewer] The answer now counts water once, where the
  rivers of the cells that drain into the cell bring it; a test holds that the lake's inflow is the
  sum of those; the scan has a rule for it and a planted fault.
* **What the check of the table of hollows cannot show (medium).** I had written "one thing"; there
  are two: that the pass a hollow names is its lowest, and the level of a pass into the sea, which
  the check bounds from below only. A level written 200 m too high is accepted, and the lake then
  stands too high. [MEASURED by the reviewer] Not mended: the check is not handed the sea's
  surface. Section 9, `data/tables.yaml` and the library's description say "two things".
* **What holds the scan's own rules (medium).** "A test plants each fault" was not so: the scan can
  report at 94 places and the test planted 28 faults; the reviewer took four rules out unnoticed.
  Five more faults are planted, one for each of those four and one for the drowned cell; the
  descriptions now say that most other rules of the scan have no planted fault. The test's
  description says which cells it reads.
* **Smaller, each corrected where it stood.** "From then on each new test was run to see it fail"
  (the record after it has three rounds that found tests that could not fail). "Two machines with
  different processors": no second machine was used by anyone; the last digits differ with numpy's
  AVX-512 code switched off on the same machine. The suite's last run before the fourth commit was
  on the working tree, two text files changed after it, and it had failed in four tests, not five.
  The 75 changes on purpose were run on test files as they stood half an hour before the commit.
  The four worlds were built one change before the commit. "Two of its fourteen rows hold more
  runoff than the rain can supply" (one does). "Eight breakages" (nine). "48 ways" (49). The fourth
  check's finding on labels had no entry. "Two failures outside the default setting" of the crust
  trial (three, and four seeds in which the first condition cannot be measured). Three
  cross-references and attributions. Hock's table (her 2.5 to 5.5 are for sites without glaciers).
  One test's description claimed more than its assertions.
* **Missing from section 6.** Eight things that were not done stood elsewhere or nowhere; they are
  in section 6 now.

**Found in the answer to the fifth check, by me.**

* Under the water as it is now poured, the lake at the Black Sea's place stands at 32 m, and a test
  that passed before (the seas that come back as lakes, with a bound of 30 m written with the first
  version) fails. The bound was not moved: the test is an expected failure for the Black Sea, with
  the cause measured (section 4.3).
* The Amazon leaves the land 354 km from the place taken as its mouth, where it left it at 203 km:
  one more expected failure among the mouths, and its reason says that the water poured decides it.
* The Brahmaputra's gauge passes as built (it shares its cell with the Ganges's), and passes in 2
  of 20 and 16 of 100 random settlements: no finding.

**What was run on the code as committed** (commit {x['commit']}; `handoff/logs/`): {x['ran']}

**Not done in answer to the fifth check.** The check of the table of hollows still cannot bound a
pass into the sea from above. Most rules of the scan of the "why" answers have no planted fault.
The valley shares other than the tenth, and the counts of 100 settlements, are held by no test.
{x['not_done']}
"""
