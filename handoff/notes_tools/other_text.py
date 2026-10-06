"""The parts of docs/BUILD_NOTES.md outside sections 4.2 to 4.5 and 5.4: the head, sections 1, 4.7 and 11 written anew,
and for the other sections the single statements that are replaced, each as (old words, new words). `x` holds the
measured values (values.json), `o` the tables read from the logs (sec4.sec44_tables), `d` the logs."""
import logs as lg
import sec5_text
from sec4 import N


def head(x):
    return f"""# Build notes

State of the build on {x['date']}: build steps 0, 1 and 2 of the design document "World engine design:
physical causes, replaceable processes". Steps 0 and 1 had two independent reviews and a third,
narrower check. Step 2 had two independent reviews, a third check that overturned part of what I
had concluded from the Earth tests, and a fourth, by two reviewers, of what I changed in answer and
of the engine, the tests, the tools and these notes. The fourth overturned part of the account I
wrote after the third. Each was followed by fixes (section 5). {sec5_text.FIFTH_HEAD}

Labels: **[MEASURED]** I ran it in the build environment and read the number. **[DOCUMENTED]** I opened
the source during the build. **[INFERRED]** my reasoning. **[UNVERIFIED]** recalled, not checked.
**[PROVISIONAL]** a first value that an Earth test must tune. **[CALIBRATED]** set by hand on the default
planet.

The build environment was a cloud workspace with 2 processor cores and about 8 GB of memory, Python 3.13,
and the versions in `requirements.lock`. The measurements of {x['date']} were made in a fresh workspace
of the same kind, set up from the lock file. Nothing here was run on the target laptop.

"""


def sec1(x, o):
    s = x["suite"]
    return f"""## 1. What exists

| Build step | State | Evidence |
|---|---|---|
| 0. Skeleton | Done | Tests of the mesh, parameter files, the scheduler with every refusal, rounds, pushes, labels, the store, the server, the test harness |
| 1. The slice | Done, with the gaps of section 6 | Tests of the ten processes and of the whole world; two trials in `trials/results/` |
| 2. Water on land | Built. One condition of the design for it fails on Earth, the closed Caspian, and the land sheds too little water (section 4) | Drainage, Hydrology and a stand-in for Soils; tests of each on ground built for the purpose, on the default world and on Earth's own relief, rain and warmth |
| 3 to 11 | Not started | |

`python -m pytest` runs {s['tests']} tests in about {s['minutes']} minutes. {s['passed']} pass. The other {s['xfailed']} are
expected failures: each states a pattern of Earth, or a condition of the design, that the engine does
not meet, with the number measured (sections 3.1 and 4.2 to 4.6). Two conditions of the design are
among them: the dry belt of the north, which fails on the engine's own world and again on Earth's
relief, and the closed Caspian. Without the Earth reference data (section 4.3) the {s['skipped']} tests that
need it are skipped. Of the other {s['tests'] - s['skipped']}, {s['passed_without']} pass and {s['xfailed_without']} is an expected failure that the engine's own
world gives without any data of Earth. [MEASURED: the whole suite on commit {s['commit']}, with the data
({s['seconds']} s) and without ({s['seconds_without']} s); `handoff/logs/suite_with_data.log`, `suite_without_data.log`]

"""


def sec47(x):
    t = x["times"]
    row = lambda what, cells, k, extra="": f"| {what} | {cells} | {t[k]['s']} | {extra} | {t[k]['gb']} |"
    return f"""### 4.7 Run times

All [MEASURED] on {x['date']}, on a 2-core cloud workspace with about 7 GB of memory, each run with the
machine to itself (`handoff/logs/`, the files ending in `.time`). The laptop is not timed.

| What | Cells | Whole run | Climate rounds | Most memory held |
|---|---|---|---|---|
{row("Default world, preview profile", "10,242", "build_preview", t['rounds']['preview'])}
{row("Default world, standard profile", "163,842", "build_standard", t['rounds']['standard'])}
{row("Earth twin, preview (the build and its comparison with Earth)", "10,242", "twin_preview", t['rounds']['twin_preview'])}
{row("Earth twin, standard", "163,842", "twin_standard", t['rounds']['twin_standard'])}
{row("Earth's rivers (`tools/earth_rivers.py`, standard mesh)", "163,842", "rivers")}
{row("… with 20 random settlements of the ties", "163,842", "rivers_s20")}
{row("… with 100, and the table of the cuts", "163,842", "rivers_s100")}
{row("Earth's relief (`tools/earth_relief.py`)", "163,842", "relief")}
{row("The demand for water (`tools/earth_demand.py`)", "163,842", "demand")}
{row('The scan of the "why" answers (`tools/why_scan.py`), preview world, every cell', "10,242", "scan_preview")}
{row("… standard world, every 23rd cell", "7,124", "scan_standard")}
| The test suite, with the Earth data | | {x['suite']['seconds']} s | | |
| … without | | {x['suite']['seconds_without']} s | | |
{x['audit_time_row']}

The world stores take {t['sizes']['first']} MB (preview) and {t['sizes']['big']} MB (standard); the twins {t['sizes']['twin_preview']} and {t['sizes']['twin_standard']} MB.
The limit of the standard profile is 1,800 s. The standard builds hold more than 5 GB at their peak:
on this machine nothing else of size can run beside one.

**The machine's speed changes within a day, by a factor of two.** Earlier measurements, on other
workspaces of the same kind: for the standard build 492 to 531 s at the end of step 1, and 1,186 s,
580 s and 598 s on 2026-10-05, all three in one day; for the preview build 23 s to 48 s. The times
in the table are good to that factor of two and no better. Like for like, step 2 costs seven more
climate rounds than step 1 (23 for 16 on the preview mesh, 24 for 17 on the standard one), because
the water that land gives back must settle with the rain it feeds. [MEASURED on 2026-10-05] The
high_fidelity profile was not run. Its solvers would need about four times the memory of the
standard profile's, so whether it fits in 32 GB is open. [INFERRED]

The same seed gave the same world in two fresh interpreters with different hash seeds. [MEASURED:
test, preview mesh] {x['worlds_same']}
"""


def sec11(x, o):
    ls, w = o["ls"], o["w"]
    t20, t100 = o["t20"], o["t100"]
    return f"""## 11. Next

Step 2 is built. By the design's "done when", read strictly, it is not done: the closed Caspian
fails as built (sections 4.2 and 4.5). Its largest known error is that the land gives the air too
much water and the rivers too little, by a size that is measured and for a cause that is not
(section 4.4). I count the step closed with both stated. Build step 3 is not started, and I will not
start it before you answer.

**Four questions for you.**

1. **What to mend first.** My candidate is the cold northern summers of the climate. It is the
   largest known error of the whole engine, and step 2 did not touch it. On Earth's relief the
   engine's land between 40° and 60° north is {x['twin']['swing']} K warmer in July than in January where Earth's is
   {x['twin']['swing_earth']} K; its coldest month is right and its warmest 17 K too cold (on the preview mesh); the polar climate takes {x['twin']['E']} % of the land
   for Earth's 13 %, and {x['twin']['white']} % of the land is white all year. [MEASURED: section 4.6] The cause is not
   established: a seasonal forcing that is too weak and snow that never melts are not told apart
   (section 8). So the first piece of work would be to tell them apart, by runs of EnergyBalance
   and Albedo alone, before any constant is changed. The Earth twin gives four tests to judge a mend
   by, all expected failures today. They pass at three quarters of Earth's 31 K between July and
   January on northern land, at 15 % of the land in the cold climates with warm summers, with the
   driest land band of the north between 15° and 40°, and at three quarters of Earth's rain on the
   land between 40° and 60° north. The other candidate is the water that the land gives back
   (section 4.4, point 7); nothing at hand says which formula or constant is wrong there, so a mend
   chosen now would be a fit to one published budget and {ls['alike']} basins. I would leave it until data
   by region are at hand.
2. **Do the 21 gauges belong to the "done when" of Hydrology?** The design's row says "River flow
   data is still to be chosen". I chose the last gauging stations of 21 great rivers and asked for
   the measured flow within a factor of two. As built {o['gauges_n']} pass and {21 - o['gauges_n']} miss, and section 4.4 shows
   that the gauges test the relief data and the precipitation handed in at least as much as they
   test Hydrology. If they belong to the "done when", step 2 is further from done than the one
   failed design condition says.
3. **Does a Caspian whose overflow ends in a neighbouring closed lake "stay a closed lake"?** As
   built the lake at the Caspian's place overflows by {o['c']['overflow']:.1f} km³ a year, of {o['c']['brought']} that rivers and
   shores bring it, and that water ends in a second, closed lake {o['c']['cells']} cells away; none reaches the sea,
   as built or in any of 100 random settlements. No water of the Caspian's basin leaves for the
   ocean, which may be what the design's sentence meant; the lake itself is not closed, which is what
   it says. The test reads it as written and fails. Either answer leaves the larger miss standing:
   the lake is two and a half to three times the real sea's size.
4. **Relief with its rivers cut in, fetched on your machine?** The mouths and the gauges test the
   relief data, their ties, the valley rule and the water poured more than they test Drainage
   (section 4.4). Tuning the harness moves single rivers and not the counts (section 4.5). Relief
   made for hydrology would make those tests mean something about Drainage. It is not among the
   data the build environment reaches; on your machine it could be fetched. [UNVERIFIED: that a
   data set of this kind is free to fetch; I recall several and opened none]

One thing more that only your machine can show: a first run on Windows. Nothing was run there
(section 6).
"""


# ---------------------------------------------------------------------------------------------- single statements
def r2(x, o, d):
    return [
        ("| Three toy processes with a loop, a modifier and a push reach a known steady answer | Pass. a = 7 and b = 8 to within 1e-6 after 52 rounds [MEASURED: `tests/test_engine.py`] |",
         "| Three toy processes with a loop, a modifier and a push reach a known steady answer | Pass. a = 7 and b = 8 [MEASURED: `tests/test_engine.py`, which asks for them to within 1e-5; the fifth check measured 8.5e-7 after 52 rounds] |"),
        ("| Every refusal message is tested | Pass. Every refusal of the scheduler is checked for its message (`tests/test_scheduler.py`, 60 tests), and the engine's own in the four engine test files |",
         "| Every refusal message is tested | " + x["refusals_row"] + " |"),
    ]


def r3(x, o, d):
    return [
        ("after one change to how the first condition is measured. Two failures outside the default setting. Section 3.2 gives all of it.",
         "after one change to how the first condition is measured. Outside the default setting three runs fail the second condition, and in four of ten other seeds the first cannot be measured. Section 3.2 gives all of it."),
        ("and the first reviewer of\nstep 2 found that.", "and the second review of\nstep 2, the engine's, found that."),
    ]


def r41(x, o, d):
    return [("the air's demand for water by the Priestley-Taylor rule in the form of Davis et al. 2017;",
             "the air's demand for water by the Priestley-Taylor rule, with the constants and the two radiation formulas of Davis et al. 2017, applied to the whole day, which is not the paper's way (section 7, item 14);")]


def r46(x, o, d):
    return x["twin_table"] + [
        ("left out: the twin has no plates and no crust, and says so when asked why its ground stands where it\ndoes.",
         "left out: the twin has no plates and no crust, and says so when asked why its ground stands where it\ndoes. The water poured on the twin is the planet file's volume, which is a parameter of the planet;\nthe Earth tests of sections 4.2 to 4.5 pour what the ocean of the relief data holds, 0.19 % more."),
        ("""One cause runs through all four. The engine's
land is too cold and its summers too weak, so snow that should melt stays, the polar climate takes
the place of the cold one, cold air carries little vapour and white ground gives none back.
[INFERRED: the chain is my reading; the first link is measured in section 8]""",
         """What is measured of the first, on the preview twin: over the land between 40° and 60° north the coldest
month is as cold as Earth's (−12.6 °C for −12.7 °C) and the warmest is 17 K too cold (1.4 °C for
18.4 °C); the year is 9.3 K too cold (−5.8 °C for 3.5 °C); and 52 % of that land lies under snow in
every month. [MEASURED: `handoff/pass2/twin_seasons.log`; a test holds these numbers] That the four
failures share one cause is my reading: summers too weak, so that snow which should melt stays, the
polar climate takes the place of the cold one, cold air carries little vapour and white ground
gives none back. [INFERRED: the chain was not measured link by link] Which cause makes the summers
weak is not established (section 8)."""),
        ("""is 7 K too warm, and more land lies under lakes than under Earth's measured climate on the same
relief (8.5 % for 6.0 %): a hollow under snow that never melts loses nothing to the air, and fills.
[MEASURED; the cause of the last INFERRED]""",
         f"""is 7 K too warm, and {x['twin']['lakes_standard']} % of the land lies under lakes. [MEASURED] That is not to be set beside the
lakes of section 4.3, as I had done: the twin's Drainage is handed the cells' mean heights, the Earth
tests the valley floors. Earth's measured climate on the mean heights gives 7.3 %. The twin's excess
over that lies between 40° and 60° north (18.9 % for 14.1 %); between 60° and 90° north, where all the
twin's land is under snow all year, lakes cover 11.2 % for 11.0 %. [MEASURED by a reviewer of the fifth
check on the stores of 2026-10-05; I did not repeat it]"""),
    ]


def r48(x, o, d):
    return x["step2_table"]


def r5(x, o, d):
    return [
        ("""Every finding marked high or medium that a test can hold
has one; a finding about what I had written is mended in the text, and no test can hold that. The
second review of step 1 found three such tests that also passed on the faulty code; they were
rewritten, and from then on each new test was run against the code as it stood, to see it fail.""",
         """Findings marked high or medium were given a test
where a test can hold them; that every one has one I have not checked, and the fifth check found
two claims of that kind that did not hold (section 5.4). A finding about what I had written is
mended in the text, and no test can hold that. The second review of step 1 found three tests that
also passed on the faulty code; they were rewritten. The fault came back: the second, third and
fourth checks of step 2 each found tests that could not fail."""),
        ("One constant had the exponent of its formula run into it (33.912 for 33.91) | Section 5.1 |",
         "One constant had the exponent of its formula run into it (33.912 for 33.91). With numpy's AVX-512 code switched off, on the same machine, the preview world came out with other last digits | Section 5.1 |"),
        ("The data tools failed on Windows encodings and trusted files they had not checked. Two machines with different processors gave different last digits | Section 5.1 |",
         "The data tools failed on Windows encodings and trusted files they had not checked | Section 5.1 |"),
        ("The check of the table of hollows still let eight breakages through.", "The check of the table of hollows still let nine breakages through."),
        ("| Step 2, 5. One reviewer: the claims alone, in the notes, the README, the tests' reasons and the descriptions in the code | ⟦FIFTH_ROW⟧ | Section 5.4 |",
         "| Step 2, 5. Two reviewers: the claims alone, in the notes, the README, the tests' reasons and the descriptions in the code | " + sec5_text.FIFTH_ROW + " | Section 5.4 |"),
        ("A test of 21 great rivers at their gauges was\n  written before it was run; 15 failed.",
         "A test of 21 great rivers at their gauges was\n  added; 15 failed. (No record shows that it was written before it was run: section 4.3.)"),
        ("23\n  to the Earth harness and its tools, and 7 to the smaller things.", "23\n  to the Earth harness, and 7 to the smaller things."),
        ("What the check cannot show is in section 9.",
         "Of the first reviewer's eight, seven are refused now; the eighth, two rows that change\n  places, is accepted still, and the table's description now says that no reader relies on the\n  order. What the check cannot show is in section 9."),
        ("""The Amazon carries half its weight; two of its
  fourteen rows hold more measured runoff than the rain data can supply; taken after the engine's
  own lakes it is 0.62 for 0.68. All three are in section 4.4, in the tool's report and in a test.""",
         """The Amazon carries half its weight; two of its
  fourteen rows cannot test Hydrology (one holds more measured runoff than the rain handed in, the
  other 0.64 of it); taken after the engine's own lakes it was 0.62 for 0.68. All three are in
  section 4.4 and in the tool's report."""),
        ("""* **The suite had not been run whole on the code as committed (low).**""",
         """* **Labels (low).** A published budget was called "measured", and texts of `data/models.yaml` that
  say where a model is wrong carried no labels. Each was changed where it stood; this entry was
  missing until the fifth check. Eight of those texts still carry no label. [MEASURED by the fifth
  check]
* **The suite had not been run whole on the code as committed (low).**"""),
        ("""Run whole
  before this was written, the suite failed in five tests. One was a number written into the
  library's code, against the design's rule that code holds none. Four were older tests that""",
         """Run whole
  before this was written, the suite failed in four tests, and a fifth had failed by itself in the
  run of the changes on purpose. That fifth was a number written into the library's code, against
  the design's rule that code holds none. The four were older tests that"""),
        ("""The numbers of section 1 are of the whole suite on the code as committed,
  with the Earth data and without.""",
         """The numbers that section 1 gave after the fourth check were of the whole suite on the working
  tree, 2 to 19 minutes before the commit; two text files changed after it, and the one test that
  reads one of them passes on the commit. [MEASURED by the fifth check]"""),
        ("with 13 changes of my own to the code written since: 75 runs. The suite\nnotices 71.",
         "with 13 changes of my own to the code written since: 75 runs, 73 of them on the test files as they\nstood half an hour before the commit. The suite\nnotices 71."),
    ]


def r6(x, o, d):
    return [("⟦NOT_DONE_REVIEW⟧\n", f"""11. **The same world on another processor.** With numpy's AVX-512 code switched off, on the same
    machine, the default world comes out with other last digits: differences of at most 4 parts in a
    million, no class changed. [MEASURED by a reviewer of step 2; the fourth check measured it again
    on the preview mesh: 21 of 52 fields, at most 3.3 parts in a million, no class, index or
    true-or-false value] That a processor without those instructions does the same is likely and was
    not tried: no second machine was used. [INFERRED] The design's promise is the same world, bit for
    bit, on one machine with the pinned versions, and that holds. [MEASURED: two fresh interpreters]
    Across machines I know no way to make it hold short of giving up the fast mathematics library. A
    world store carries its own fingerprints, so a difference is seen, not hidden.
12. **Biomes' design test.** The design asks for agreement with the published map of climate
    classes, cell by cell. Five shares of the land are tested instead; the map is not at hand
    (section 4.3).
13. **The crust trial's open ends** (section 3.2): three runs fail its second condition outside the
    default setting, and three duties follow for step 3.
14. **The viewer has no test in the suite** beyond the server's answers. The check in a browser is a
    tool that needs a package the suite does not have (`tools/viewer_check.py`). {x['viewer_check']}
15. **The contract test of imports and draws covers `processes/` only**, not the library.
    [MEASURED by the fifth check: `tests/test_contract.py`]
16. **The install by the README's three commands** (a virtual environment, the lock file, the
    editable install) {x['install']}
17. **Two limits of the checks on water** (section 5.4): the check of the table of hollows cannot
    bound a pass into the sea from above, and most rules of the scan of the "why" answers have no
    planted fault.
18. **The design's river-flow data.** The design left them "still to be chosen". With the 21 gauges
    I chose, {21 - o['gauges_n']} miss as built (sections 4.2 and 11).
19. **The design document** {x['design_doc_s6']}
""")]


def r7(x, o, d):
    dm = lg.demand_report(d["demand"])
    a = dm["all_land"]
    table = f"""    | Over land, W/m² | The engine's formulas under Earth's measured temperatures | The published budget of the land |
    |---|---|---|
    | Sunlight that reaches the ground | {dm['reaches'][0]} | {dm['reaches'][1]} |
    | Sunlight that the ground absorbs | {dm['absorbed'][0]} | {dm['absorbed'][1]} |
    | Heat that the ground radiates away | {dm['lost'][0]} | {dm['lost'][1]} |
    | Left to warm the air and evaporate water | {dm['left'][0]} | {dm['left'][1]} |
    | Of that, taken by evaporation | {dm['evaporation'][0]} (Hydrology under the rain data) | {dm['evaporation'][1]} |
"""
    old_table = """    | Over land, W/m² | The engine's formulas under Earth's measured temperatures | The published budget of the land |
    |---|---|---|
    | Sunlight that reaches the ground | 185.6 | 184.7 |
    | Sunlight that the ground absorbs | 154.0 | 145.1 |
    | Heat that the ground radiates away | 68.3 | 79.6 |
    | Left to warm the air and evaporate water | 85.7 | 65.5 |
    | Of that, taken by evaporation | 45.1 (Hydrology under Earth's measured rain) | 38.5 |
"""
    return [
        ("Each is recorded in the design document as well. Items 1 to 8 are of step 1; 9 to 21 of step 2.", x["design_doc_s7"]),
        ("her Table 1\n    gives 2.5 to 5.5 for snow; 4 is my choice]", "her Table 1\n    gives 2.5 to 5.5 for snow at sites without glaciers, as a page reader gave it; 4 is my choice]"),
        ("""With it the formulas return the means of
    Earth's whole surface: 161 W/m² of sunlight absorbed and 63 W/m² of heat lost. [DOCUMENTED for
    Earth: Trenberth, Fasullo and Kiehl 2009, Table 2b] Over land alone they do not:""",
         """With it the formulas come near the means of
    Earth's whole surface: 0.465 of the sunlight at the top of the air absorbed at the surface, which
    is 158.7 of 341.3 W/m², and 64.0 W/m² of heat lost at 15 °C, where Earth has 161.2 and 63.
    [MEASURED for the formulas: the comment in `data/models.yaml`; DOCUMENTED for Earth: Trenberth,
    Fasullo and Kiehl 2009, Table 2b] Over land alone they do not:"""),
        (old_table, table),
        ("""The land is left 1.31 times the energy of the budget, and
    gives the air 1.17 times the water. The excess of 20.2 W/m² taken apart: 0.7 from the sunlight
    that reaches the ground, 8.2 from the ground reflecting 0.17 of it where the budget has 0.21, and
    11.3 from the formula for the heat radiated away. The share of sunshine sets the first of these,
    and the first is right: the share that would return the budget's sunlight at the ground is 0.61.
    The formula for the heat loss would want a share of 0.76; no single share mends both.""",
         f"""The land is left {dm['left'][2]:.2f} times the energy of the budget, and
    gives the air {dm['evaporation'][2]:.2f} times the water, on rain that is not the budget's (section 4.4, point 7).
    The excess of {dm['excess']['all']} W/m² taken apart: {dm['excess']['sunlight']} from the sunlight that reaches the ground,
    {dm['excess']['reflection']} from the ground reflecting {dm['excess']['reflects']} of it where the budget has {dm['excess']['budget_reflects']}, and {dm['excess']['heat']} from the
    formula for the heat radiated away. The share of sunshine enters both formulas: the share that
    would return the budget's sunlight at the ground is {dm['wants'][0]}, the one that would return its loss
    of heat is {dm['wants'][1]}, and no single share mends both."""),
        ("""Over Earth's land the engine's demand is
    1,003 mm a year. The paper's form gives 1,246 mm from the same numbers and gives 194 mm back as
    dew: 1,052 mm net.""",
         f"""Over Earth's land the engine's demand is
    {N(a['engine'])} mm a year. The paper's form gives {N(a['paper'])} mm from the same numbers and gives {a['dew']} mm back as
    dew: {N(a['net'])} mm net."""),
        ("""I kept it and said so: the error of the one
    share of sunshine is six times as large and of the other sign, and 194 mm of dew a year over all
    land is more than I can hold against anything measured.""",
         f"""I kept it and said so: the energy that the two radiation
    formulas leave the land is 31 % above the published budget's, six times as much and of the other
    sign, and {a['dew']} mm of dew a year over all land is more than I can hold against anything measured."""),
        ("""21. **`potential_evapotranspiration` is not the paper's quantity of that name** (item 14): it is the
    demand over the whole day, on the ground that is free of snow.
""",
         """21. **`potential_evapotranspiration` is not the paper's quantity of that name** (item 14): it is the
    demand over the whole day, on the ground that is free of snow.
22. **The frozen-region example caps the temperature at −15 °C**, not at the design's −5 °C (section
    3.4). It is of step 1; these notes had it in section 3.4 only.
23. **Snapshots of the history, the rerun of the climate inside the history, the weather clock and
    the clock that steps through dates are refused on loading** until their build steps (section 6,
    item 6). Of step 1; these notes had it in section 6 only.
24. **River-flow data.** The design left them to be chosen. I chose the last gauging stations of 21
    great rivers [DOCUMENTED: Dai and Trenberth, Table 2] and a factor of two (sections 4.2 and 4.4).
25. **The water poured on Earth's relief.** The design's test of SeaLevel names the volume measured
    from the relief at full detail. Until the fifth check the Earth tests poured the planet file's
    volume instead, 0.19 % less, and that departure was recorded nowhere. They follow the design now
    (section 4.5). The Earth twin pours the planet file's volume.
"""),
    ]


def r8(x, o, d):
    ls, w, v = o["ls"], o["w"], o["v"]
    like = o["like_rows"]
    dm = o["dm"]
    lowest = sorted((r["ratio"], k) for k, r in like.items() if r["alike"])[:3]
    highest = max((r["ratio"], k) for k, r in like.items() if r["alike"])
    return x["world_table"] + [
        ("Default world, seed 20261004. [MEASURED unless marked: `python tools/world_report.py STORE`]",
         "Default world, seed 20261004. [MEASURED unless marked: `python tools/world_report.py STORE`; two rows that\nthe tool does not print say where they come from]"),
        ("| 0.37 million km², the Caspian [UNVERIFIED] |", "| 0.37 million km², the Caspian [DOCUMENTED at second hand: Wikipedia] |"),
        ("In order of how much they distort the world:",
         "In the order in which I judge them to distort the world. The order is a judgment; nothing measures it."),
        ("""[MEASURED] The cause,
  as I read it, is the one spreading constant of EnergyBalance, which ties land to the sea too
  tightly. Run alone, EnergyBalance gives the centre of a continent 60° of longitude wide a swing
  of 10.7 K either side of its mean at 50° north, and one 140° wide a swing of 20 K. [MEASURED for
  the two swings; INFERRED that the constant is the cause: no mend has been tried] Later models of
  this family let the spreading vary with latitude and surface. [DOCUMENTED: Ziegler and Rehfeld
  2021] With weak summers the snow of land poleward of about 50° never melts; the white ground then
  gives the air no water, and the north is dry as well. [INFERRED: the chain is my reading]""",
         """[MEASURED] The cause is
  not established. What is measured, on the Earth twin: over the land between 40° and 60° north the
  coldest month is as cold as Earth's and the warmest is 17 K too cold, and 52 % of that land lies
  under snow in every month (section 4.6). Two candidates are not told apart by anything measured: a
  seasonal forcing that is too weak, and snow that never melts and keeps the summer cold. Each
  would feed the other. [INFERRED: both] I had named the one spreading constant of EnergyBalance as
  the cause, "which ties land to the sea too tightly"; a land tied to the sea would have winters
  too warm, and the twin's winter is right. What was measured with EnergyBalance alone, in step 1:
  the centre of a continent 60° of longitude wide swings 10.7 K either side of its mean at 50°
  north, and one 140° wide 20 K; with a smaller constant (0.35 for 0.649) the same two swing 15.9
  and 27.6 K. [MEASURED in step 1; not run again] Later models of this family let the spreading
  vary with latitude and surface. [DOCUMENTED: Ziegler and Rehfeld 2021] With weak summers the snow
  of land poleward of about 50° never melts; the white ground then gives the air no water, and the
  north is dry as well. [INFERRED: the chain is my reading]"""),
        ("""on the mean of Earth's land the one share gives the right sunlight at the ground (section
  7, item 14), and nothing at hand measures sunshine by region.""",
         """on the mean of Earth's land the one share gives the right sunlight at the ground and too
  small a loss of heat (section 7, item 14), and nothing at hand measures sunshine by region."""),
        ("""Under Earth's own rain and
  warmth the land gives the air 1.17 times what a published budget gives it, the land of fourteen
  great basins sheds 0.68 of the depth measured (0.64 without the Amazon), and 31.7 thousand km³ a
  year reach the sea where Earth's rivers carry 40. The cause is not established (section 4.4). The
  error is not even: the land sheds least in the Indus, the Yangtze and the Brahmaputra (0.13, 0.21
  and 0.23, the last on rain data that hold less than the river carries) and too much in four snowy
  basins of the north (the St Lawrence 1.45).""",
         f"""Under the rain and warmth
  of Earth's data sets the land gives back {w['back']:.3f} of the rain where a published budget has 0.65, the
  land of {ls['alike']} great basins sheds {ls['all']:.2f} of the depth measured ({ls['without_heavy']:.2f} without the Amazon), and {w['to_sea']:.1f}
  thousand km³ a year reach the sea where that budget has 40, on {w['rain']:.1f} thousand km³ of rain for its
  114. The cause is not established (section 4.4). The error is not even: the land sheds least in the
  {lowest[0][1]}, the {lowest[1][1]} and the {lowest[2][1]} ({lowest[0][0]:.2f}, {lowest[1][0]:.2f} and {lowest[2][0]:.2f}; the Brahmaputra on rain data that hold
  less than the river carries) and more than measured in {ls['above']} basins (the {highest[1]} {highest[0]:.2f})."""),
        ("On the mesh's Volga 319 of the year's 342 mm are shed in April,",
         f"On the mesh's Volga {v['data']['most']} of the year's {v['data']['sheds']} mm are shed in April,"),
    ]


def r9(x, o, d):
    return [
        ("[MEASURED: 48 ways of breaking the table, each refused in the words of", "[MEASURED: 49 ways of breaking the table, each refused in the words of"),
        ("""One thing the
   check cannot show: that the pass a hollow names is its lowest. A table that keeps every rule and
   names a higher pass is accepted, and the lake then stands too high. [MEASURED by the fourth
   check: 894 m for 530 m on a ground built for it] To show it Hydrology would have to find the
   hollows again.""",
         """Two things the
   check cannot show. One: that the pass a hollow names is its lowest. A table that keeps every rule
   and names a higher pass is accepted, and the lake then stands too high. [MEASURED by the fourth
   check: 894 m for 530 m on a ground built for it] To show it Hydrology would have to find the
   hollows again. Two: the level of a pass into the sea, which the check bounds from below only,
   because it is not handed the sea's surface. A level written 200 m too high is accepted, Hydrology
   runs without a notice, and the lake stands too high. [MEASURED by the fifth check]"""),
    ]


def r10(x, o, d):
    return [
        ("| The Caspian: 371,000 km² without the Garabogazköl lagoon, 28 m below the ocean | Read out by a page reader. It disagrees with the paper above on the area; both are given in section 4.4 |",
         "| The Caspian: 371,000 km² without the Garabogazköl lagoon, 28 m below the ocean; a catchment of 3,626,000 km² | Read out by a page reader, the catchment on 2026-10-06. It disagrees with the paper above on the area; both are given in section 4.4 |"),
        ("| The degree-day rule of melt and its factors for snow | Opened as a copy on a personal site |",
         "| The degree-day rule of melt and its factors for snow | Opened as a copy on a personal site. The fifth check read its Table 1 through a page reader: 2.5 to 5.5 at sites without glaciers, and larger factors at glacier sites, which the reader gave unreliably |"),
        ("which does not agree with the 262 km³; 30 % of the precipitation as snow; 53 % of the runoff in the spring flood |",
         "which does not agree with the 262 km³; a \"water content\" of 250 km³ a year, a third figure; 30 % of the precipitation as snow; 53 % of the runoff in the spring flood |"),
        ("## 10. Sources opened during the build\n", "## 10. Sources opened during the build\n\nOne source below was opened by a reviewer and not by me, and its row says so.\n"),
        ("| [The Python documentation, `sys.stdout`]",
         "| [GPCP Version 2 documentation](https://iridl.ldeo.columbia.edu/SOURCES/.NASA/.GPCP/.V2/.dataset_documentation.html), 2002 | Whether the rain data raise gauge readings for what gauges miss: \"corrected for climatological estimates of systematic error due to wind effects, side-wetting, evaporation, etc., following Legates (1987)\". It is of version 2, not of the 2.2 used here, and does not say which precipitation is right over the Volga | Opened by a reviewer of the fifth check, through a page reader; not by me |\n| [The Python documentation, `sys.stdout`]"),
    ]


REPLACE = {"2": r2, "3": r3, "4.1": r41, "4.6": r46, "4.8": r48, "5": r5, "6": r6, "7": r7, "8": r8, "9": r9, "10": r10}
