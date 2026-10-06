"""The numbers and the longer texts that rewrite_notes.py puts into docs/BUILD_NOTES.md.
Numbers come from scratchpad/step2/fourth/final2 (the measurement after the fixes) and from numbers.py beside this file."""
from pathlib import Path

import numbers_measured as N

HERE = Path(__file__).resolve().parent

FIFTH = N.FIFTH
N_TESTS, N_PASS, N_XFAIL, N_SKIP, N_REST, SUITE_MIN = N.N_TESTS, N.N_PASS, N.N_XFAIL, N.N_SKIP, N.N_REST, N.SUITE_MIN
REST_SENTENCE = N.REST_SENTENCE

FAMILIES = "272, 1,056 and 4,160"
FAMILIES_8 = ("The worked-out lengths of 8 pairs of\n"
              "    neighbouring families overlap in this way on the standard mesh. On the high_fidelity mesh, which\n"
              "    was not run, there are 16,512 families, the rounding errors inside one reach 6e-11 of the\n"
              "    longest boundary, and 870 pairs overlap. [MEASURED: the geometry of the four meshes. A test\n"
              "    holds the families of the meshes up to the standard one and asks, for three symmetries that\n"
              "    generate all 120, that the widths around a cell are those around its image] Another processor\n"
              "    may round the geometry otherwise and so put such a pair in the other order; a tie between those\n"
              "    two widths would then go the other way, on that machine and every time. [INFERRED: not tried.\n"
              "    The fourth check found the lengths to differ by 1.4e-16 of the longest with the AVX-512\n"
              "    instructions switched off. The nearest two families of the standard mesh differ by 5e-12, tens\n"
              "    of thousands of times as much, so a change of order there would take a far larger difference\n"
              "    between machines than the one seen; on the high_fidelity mesh the nearest two differ by 2e-14]")

CASPIAN_SHARES = ("At each of the five other valley shares tried it stays closed in all of 20 random settlements.")

SEC45 = '''### 4.5 The valley share

A river runs along the floor of its valley, not at the mean height of the 60 km around it. The design
asked for "relief converted so that valley floors survive". The Earth tests hand Drainage, for each
land cell, the height below which a tenth of the cell's land points lie. The rule and the tenth are
mine. The tenth stands in the first commit of the Earth tests and in every commit since. [MEASURED:
`git log -S VALLEY_SHARE`] The history cannot show what was tried before that commit; I recall
trying no other value. [UNVERIFIED] The rule keeps valley floors, loses the ridges between them and
raises drowned valleys (section 4.4, point 3). The second review asked what the share decides.
[MEASURED: `python tools/earth_rivers.py --valley-share x --settlements 20`, one run for each
share. Tests hold the column of the tenth; nothing holds the other five]

''' + N.SHARE_TABLE + '''
What the columns show:

* **The counts hardly move, and at every share the ties move them as much as the share does.**
  Which rivers pass changes with both. The Nile's mouth fails in all 20 settlements at shares of
  0.02 and 0.05, passes in 10 at the tenth and in all 20 from 0.2 up. The Congo's passes at 0.02
  alone, in 9 of 20: there the rule brings the barrier of its valley down to 457 m, the level of
  the lake above it, and the ties decide whether the river takes the valley.
* **The water of all the land moves little, and one way.** The larger the share, the more land lies
  under lakes (5.5 to 6.8 %) and the less water reaches the sea (32.1 to 31.1 thousand km³ a year).
* **The closed Caspian** is the one design condition of step 2 that fails as built, and it fails
  at this share alone. At five of the six shares the lake stays closed in all 20 settlements. At
  the tenth it stands exactly at the brim of its hollow, at 61 m, and the ties decide whether a
  little runs over: it stays closed in 10 of 20 settlements and in 55 of 100. On the data's own
  grid that brim stands at 91 m, one step of 100 feet higher. [MEASURED: `tools/earth_relief.py`]
* **The lake is far too large at every share:** 0.88 to 1.14 million km² up to a share of 0.3,
  which is 2.4 to 3.1 times the 371,000 km² of the real sea and 2.0 to 2.6 times the 436,000 km²
  of the other source (section 4.4). At 0.5, as the engine settles ties, one lake of 2.09 million
  km² covers the hollow of the Caspian and that of the Black Sea, where its lowest point lies; in
  the random settlements the lake at the Caspian's place covers 1.31 to 2.10 million km².
* **The engine's own settlement is one draw among many.** At a share of 0.05 it gives a
  like-for-like figure of 0.74, outside the 0.67 to 0.71 of the 20 random settlements.

A different, equally defensible share would have let me report that every condition of the design
passes. I report the tenth, as built: the condition fails. Every column shows the miss that
matters, a lake two to three times the real sea's size. Whether a lake at its brim runs over is no
finding either way.

'''

SEC47 = N.SEC47

TWIN_TABLE = N.TWIN_TABLE
WORLD_TABLE = N.WORLD_TABLE

SEC53 = '''### 5.3 What the fourth check of step 2 changed

Two reviewers, neither of whom had seen the work. One took the changes made after the third check
and the account built on them, with slow methods written for the purpose: 3,450 rough grounds,
Earth's relief, 100 random settlements of its ties, and the sources opened again. The other took
the engine, the tests, the tools and these notes. Between them they made 126 changes to the code
on purpose. Neither found a wrong number in a world. [MEASURED by them: no difference in a
receiver, a hollow, a pass, a way across a lake or a sum on those grounds and on Earth's relief;
the numbers of these notes reproduced but for the ones listed below] What they found was, once
more, in what I had concluded, labelled and tested. I repeated each measurement with tools of my
own before acting on it, and each held.

Before they began I had found four things alone, and named them in the brief as unchecked: that
rounding the boundary lengths does settle some ties; that the Earth harness had handed its tools
heights in double precision where Drainage is handed single; the Volga; and what 81 changes on
purpose had shown. They found the four as I had measured them, and found that I had drawn too
much from the first and the third (the items on the boundary lengths and on the Volga, below).

* **A cause stated as measured (high).** Five places said that the land sheds too little because
  the demand for water is "1.31 times too high over land with one share of sunshine", and that
  clouds are the mend: section 4.4 of these notes, section 7 item 14, section 8, the description of
  Hydrology in the code and in `data/models.yaml`, and the reason of an expected failure. Section
  11 ranked the next step on it. The radiation table shows something else: the sunlight at the
  ground is right, and the excess lies in the ground's reflection and in the formula for the heat
  radiated away. A cut of the same size with another cause mends the mean as well, and neither
  mends the single basins. Each place now says that the cause is not established, gives both cuts
  and labels every cause it names [INFERRED]. The land's evaporation is set beside the published
  one as well: it is 1.17 times, not 1.31. `tools/earth_rivers.py --demands` prints the table of
  the cuts and a test holds every cell of it; another holds the radiation table and its parts.
* **"Every time" and "never" (medium).** The random settlements of the ties drew two of the four
  things that settle a tie between passes of one height. With every one drawn, the St Lawrence,
  which "fails in every settlement", passes in half, and the Ob, which passed, passes in 6 of 100.
  The harness now draws every step that is no truer than another. The tests hold the counts of 20
  draws as counts, the tool runs any number, and section 4.4 gives 20 and 100 side by side. The
  description of the first step said "the pass whose far side lies lowest"; the code takes the
  pass whose lower cell lies lowest, which may be the hollow's own cell. The description now says
  what the code does and what follows from it.
* **The Volga (medium).** "A fifth of the excess is the model's [MEASURED]" stood on one of two
  figures of the same paragraph of the source. Both are given now, with the model's part "between
  nothing and a fifth"; the test that carried the conclusion in its name is renamed. What the
  reviewer measured beside it is recorded: the engine sheds 319 of that land's 342 mm in April.
* **A failed condition reported as "not decided" (medium).** The closed Caspian is the one
  condition of the design that step 2 fails on Earth. The version before the third check said
  "fails"; the one after it said "not decided by the relief data", while a pass that the ties can
  undo as well, the Nile's, stayed "pass". Both are now reported as built, with their counts: the
  Caspian fails, the Nile passes, and neither is a finding (sections 4.2 to 4.5, 11; the README;
  the test's reason).
* **"Set before the run" (medium).** The notes and the test file said of several conditions that
  they were written before the first run. The first commit of the test of the 24 river mouths
  calls it "Found, then kept", and no version of any Earth test from before its first results
  exists. The label is gone; section 4.3 says what the history can and cannot show.
* **"Why" answers that contradicted their numbers, in five ways (medium).** A cell at the brim of a
  lake was said to lie in the lake and to be reached by no lake: such a cell has its own sentence
  now. In a cell partly under a closed lake, the water said to "arrive from upstream" was the
  arriving water times the dry share of the cell: the answer now gives what arrives and what of it
  goes into the lake. The "largest source upstream" could be a cell whose own answer said that no
  runoff is counted there, because it lies under a lake: that answer now says what the cell counts
  with in the books of the rivers, the water its ground would shed if it were dry. The answer of a
  lake cell went on to the level of the innermost hollow as if that were the lake's own: the
  lake's answer now names the hollow that the lake fills and its level, and the hollow's answer
  says that it may lie inside a larger one. The demand said that snow covers the ground "for part
  of the year" where the snow answer said that it lies all year: the sentence now says "some of
  the ground for some or all of the year". `tools/why_scan.py` has a rule for each of the five,
  and for what the second reviewer found that nothing would notice: the sentences for sea and land, for the two
  loops of the air, for what limits plants and for level ground, the units and signs of numbers,
  and the place a heading gives. A test plants 28 faults in true answers, each in an answer of
  its own, and asks the scan to report every one of them and nothing else. ''' + N.SCAN_NOW + '''
* **The check of the table of hollows (medium).** Eight breakages of the first reviewer and one of
  the second were accepted. With one, Hydrology ran without a word and lost an eighth of the rain
  on a ground built for it; with another, a lake's outlet handed its water to a sea cell 19,000 km
  away. The check now asks that exactly two rows name each parent and that those two name each
  other, that no height is missing or infinite where a rule asks for one, that the two cells of a
  pass are neighbours (it is handed the mesh's neighbours for this), that the outlet lies in the
  row's own ground, and that a hollow inside no other overflows into the sea or into ground whose
  hollow overflows no higher. 49 ways of breaking the table are each refused in the words of the
  rule broken, and a test ties every written rule of `data/tables.yaml` to the refusals that
  enforce it. What the check cannot show is in section 9.
* **A first guess outside the lineage (low to medium).** A field that a process reads from the
  round before starts from the default in `data/fields.yaml`. Changing that default changed 20
  fields of a world and none of their lineage fingerprints. The first guesses are in the lineage
  now, and a test changes one and asks for other fingerprints.
* **Tests that could not fail, and tools that no test ran (medium).** Of the reviewers' 126
  changes, 56 went unnoticed: 46 of 93 outside the routing and water code (the "why" sentences
  and their numbers, the store, the server, the command line, the reading of parameters, the scan
  itself) and 10 of 33 in the water code and the Earth tools. No test ran any tool, and no test
  held the radiation table or the table of the cuts. New since: tests of the answers' numbers,
  units, signs and places on a toy world (`tests/test_answers.py`); of the tools and the command
  line as programs (`tests/test_tools.py`); of the store, the server and the refusals of the
  parameter files; of the tools' reports on Earth, line by line against numbers worked out apart
  from them; and of the README's example answer, word for word.''' + N.MUTATIONS_NOW + '''
* **The St Lawrence (medium to low).** I had laid its closed estuary to the width of a cell. The
  valley rule closes it (section 4.4, point 3). The test's reason is corrected, and a test holds
  what the reviewer measured: with every point of a cell counted the estuary is open, and that
  reading floods a ninth of the land.
* **The boundary lengths (low to medium).** Rounding them to a billionth left 29 of the 4,160
  families of images on the standard mesh split, and 580 of 16,512 one level finer. Every boundary
  now takes the length of its family (section 7, item 20). ''' + N.FAMILY_CHANGE + '''
* **What the like-for-like figure can bear (low).** The Amazon carries half its weight; two of its
  fourteen rows hold more measured runoff than the rain data can supply; taken after the engine's
  own lakes it is 0.62 for 0.68. All three are in section 4.4, in the tool's report and in a test.
* **The tools took any option (low).** A misspelt option was passed over without a word, `--help`
  ended with an error code, one tool built a world when asked for its help, and
  `fetch_reference_data.py --check` made the folder it was asked only to look at. Every tool now
  reads its arguments with one parser that refuses what it does not know; a test runs each with
  `--help` and with an unknown option.
* **Windows (low; read, not run).** Printed text holds ° ² ³, which a redirected output on a
  Windows code page may not be able to write. [DOCUMENTED: the Python documentation of
  `sys.stdout`] The command line and the tools now write such a character as its escape where the
  system has none for it. [MEASURED on Linux with an ASCII output; not run on Windows] The last
  step of writing a store, a rename, is tried six times over two and a half seconds if another
  program holds a file, and if it still fails the store is left whole under its temporary name and
  the message says so. [MEASURED: a test makes the rename fail on purpose. INFERRED that this is
  what a virus scanner on Windows needs; not run there] The lock file pins the indirect packages
  as well, and the browser check has a lock file of its own.
* **Smaller statements, each corrected where it stood.** The land of the dry band of the north
  stands 1,053 m high, not 1,080 (a test holds the band's numbers now). "The sea cell a river runs
  into depended on the cell numbers for 11 % and 8 % of the land; now 0.2 % and 0.02 %" set two
  measures side by side; by one measure it was 13.9 % and 12.9 % (section 5.2). On the standard
  mesh the change of the third check moved the receiver of 557 coastal land cells, where I had
  written that every field on land came out the same. "The count of expected failures is the
  count of known misses" was false; section 4.3 says what is missing. The README said that the
  folder comes with a built world, which is true of the archive I hand over and not of a clone.
  The mesh's description said "the same bits" without "on one machine". Earth's "10 % under ice"
  carried three different labels in three places; it is [DOCUMENTED: National Snow and Ice Data
  Center] in all. The Brahmaputra's and the Ganges's stations lie 179 km apart, not 147. The
  Mekong's way has 21 land cells, not 20. The Indus's cell is reached by 69 thousand km², not by
  none. The St Lawrence's "443 mm" and "1.45" were of different land. "About three times the real
  sea's size at every share" was false of the share of 0.5 (section 4.5). At a demand of 0.76 of
  itself the books of the Niger's gauge did not close: its cell lies in a closed lake, and the
  books now count what such a lake keeps and close at every cell of the mesh. The test that the
  largest river "runs where it rains" passes on a source cell that lies under snow all year; its
  description says so now.
* **The suite had not been run whole on the code as committed (low).** One test file was changed
  after the last full run and before the commit. The fault then recurred, and worse, while I made
  the fixes above: I ran the tests of what I was changing and not the whole suite. Run whole
  before this was written, the suite failed in five tests. One was a number written into the
  library's code, against the design's rule that code holds none. Four were older tests that
  still asked for what the fixes of the "why" answers had changed on purpose: the outlet cell of
  a lake counted as lying in the lake, a cell wholly under a closed lake given the code of one
  partly under it, and every recorded driver counted as a term of a sum. None was a wrong number
  in a world: the four worlds of section 4.7 are the same in every field and table as before the
  fixes. [MEASURED] The numbers of section 1 are of the whole suite on the code as committed,
  with the Earth data and without.
* **Left as found, and said.** The Earth harness writes a folder beside the reference data and
  sets one variable of the environment; both are in the descriptions of the functions that do it.
  The two trials of step 1 wrote their result files on every run, and a README command would have
  overwritten the records of step 1: they print now, and write only when asked with `--write`.
  The check of the table of hollows cannot show that a pass is the lowest (section 9). The
  far south of the twin, 7 K too warm, has no test.

**Changes made on purpose, run again.** ''' + N.MUTATIONS_AGAIN + '''

''' + N.SEC54

NOT_DONE_REVIEW = N.NOT_DONE_REVIEW

SEC11 = '''## 11. Next

Step 2 is built. By the design's "done when", read strictly, it is not done: the closed Caspian
fails as built (sections 4.2 and 4.5). Its largest known error is that the land gives the air too
much water and the rivers too little, by a size that is measured and for a cause that is not
(section 4.4). I count the step closed with both stated. What to mend first is yours to rank.

1. **The seasons of the land** (EnergyBalance: the spreading of heat, and how snow and ice feed
   back). It is the largest known error of the whole engine, and step 2 did not touch it. Its cause
   is my reading, not a measurement (section 8). On Earth's relief the engine's northern land is
   ''' + N.TWIN_SEASON + ''' K warmer in July than in January where Earth's is 31 K, the polar climate takes ''' + N.TWIN_POLAR + ''' %
   of the land for Earth's 13 %, and ''' + N.TWIN_WHITE + ''' of the land is white all year. [MEASURED: section 4.6]
   The Earth twin gives four tests to judge a mend by, all of them expected failures today: 31 K
   between July and January on northern land, a fifth of the land in the cold climates, the dry
   belt as the driest band of the north, and Earth's rain on the land between 40° and 60° north.
2. **The water that the land gives back.** I proposed "clouds" here before the fourth check. What
   is measured does not point to clouds: the sunlight at the ground is right on the land's mean,
   and the excess of energy lies in the ground's reflection and in the formula for the heat
   radiated away (section 7, item 14). Three things could be tried, each a change of constants or
   of one formula inside Hydrology, and none needs a design decision: the ground's reflection over
   land, the heat-loss formula, and the one number by which the Priestley-Taylor rule divides the
   energy between evaporation and warming the air. What would judge a mend is at hand: the
   published budget of the land (`tools/earth_demand.py`), the water of all the land, and the
   like-for-like depths basin by basin (`tools/earth_rivers.py --demands`). What is not at hand is
   anything that would say which of the three is wrong, or whether the fault is elsewhere: no
   measured radiation, sunshine or daily rain by region. A mend chosen now would be a fit to one
   published budget and fourteen basins. [INFERRED]

My proposal is the first, then step 3 (the plates). The first will not mend the second: the tests
that measure the land's water hand Hydrology Earth's own rain and warmth, so nothing that
EnergyBalance does can change them. I would leave the second until data by region are at hand. The
other choice is yours to make: to set the land's constants now so that the land's budget and the
water of all the land come out as published, and to label them as fitted. It would bring the
world's rivers nearer to Earth's in size and prove nothing about the cause. A process that makes
clouds stays a question for the design of step 5 (the upgrade of Circulation and Moisture), where
rising air and moisture are remade anyway; nothing measured here argues for it or against it.

Two things outside the engine would make its tests on Earth mean more:

* **Relief with its rivers cut in.** The mouths and the gauges test the relief data, their ties
  and the valley rule more than they test Drainage (section 4.4). Such relief is not among the
  data the build environment reaches. On your machine it could be fetched. [UNVERIFIED: that a
  data set of this kind is free to fetch; I recall several and opened none]
* **A first run on Windows.** Nothing was run there (section 6).
'''
