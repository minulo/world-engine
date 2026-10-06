"""Rewrite docs/BUILD_NOTES.md from the committed version (HEAD), with the numbers of values.py filled in.
Run from /home/claude/world-engine. Every replacement must find its place exactly once."""
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import values as V

s = subprocess.run(["git", "show", "HEAD:docs/BUILD_NOTES.md"], capture_output=True, text=True, check=True).stdout


def swap(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:100])
    s = s.replace(old, new)


def between(start, end, new):
    """Replace from `start` up to (not including) `end`."""
    global s
    assert s.count(start) == 1, (s.count(start), start[:100])
    a = s.index(start)
    b = s.index(end, a + len(start))
    s = s[:a] + new + s[b:]


# ---------------------------------------------------------------------------------------------- the head
between("State of the build on 2026-10-05:", "Labels: **[MEASURED]**", f'''State of the build on 2026-10-05: build steps 0, 1 and 2 of the design document "World engine design:
physical causes, replaceable processes". Steps 0 and 1 had two independent reviews and a third,
narrower check. Step 2 had two independent reviews, a third check that overturned part of what I
had concluded from the Earth tests, and a fourth, by two reviewers, of what I changed in answer and
of the engine, the tests, the tools and these notes. The fourth overturned part of the account I
wrote after the third. Each was followed by fixes (section 5). {V.FIFTH}

''')

# ---------------------------------------------------------------------------------------------- section 1
between("`python -m pytest` runs 643 tests", "## 2. Step 0 against its", f'''`python -m pytest` runs {V.N_TESTS} tests in about {V.SUITE_MIN} minutes. {V.N_PASS} pass. The other {V.N_XFAIL} are
expected failures: each states a pattern of Earth, or a condition of the design, that the engine does
not meet, with the number measured (sections 3.1 and 4.2 to 4.6). Two conditions of the design are
among them: the dry belt of the north, which fails on the engine's own world and again on Earth's
relief, and the closed Caspian. Without the Earth reference data (section 4.3) the {V.N_SKIP} tests that
need it are skipped. {V.REST_SENTENCE} [MEASURED]

''')
swap("| 2. Water on land | Done, with the misses of section 4 | Drainage, Hydrology and a stand-in for Soils; tests of each on ground built for the purpose, on the default world and on Earth's own relief, rain and warmth |",
     "| 2. Water on land | Built. One condition of the design for it fails on Earth, the closed Caspian, and the land sheds too little water (section 4) | Drainage, Hydrology and a stand-in for Soils; tests of each on ground built for the purpose, on the default world and on Earth's own relief, rain and warmth |")

# ---------------------------------------------------------------------------------------------- section 3.1
swap("north, 297 mm. A sixth of that band is land. It stands 1,080 m high on average, its yearly mean is",
     "north, 297 mm. A sixth of that band is land. It stands 1,053 m high on average, its yearly mean is")
swap('''gives the air nothing back. [MEASURED] On Earth the land at these latitudes gets 690 mm. [MEASURED from''',
     '''gives the air nothing back. [MEASURED: a test holds each of these numbers; I had written 1,080 m,
and the fourth check measured the band] On Earth the land at these latitudes gets 690 mm. [MEASURED from''')

# ---------------------------------------------------------------------------------------------- section 3.2: when the conditions were set
swap("""Three conditions were written before the first run: (A) a marked patch of crust lies within one
cell of the place its plate's motion gives; (B) the area of continental crust changes by no more
than 2 % beyond what closing plates destroyed; (C) fewer than 1 % of cells a round switch crust
type and switch back.
""", """The design, which was approved before any code was written, fixes three conditions for the trial:
(A) a marked patch of crust lies within one cell of the place its plate's motion gives; (B) the
area of continental crust changes by no more than a stated share beyond what closing plates
destroyed; (C) fewer than a stated share of cells a round switch crust type and switch back. The
trial sets the two shares at 2 % and 1 %. [DOCUMENTED: the design's build order, step 1] The trial
came into the repository together with its first results, so the history cannot show that the two
shares were written before the first run. I recall that they were. [UNVERIFIED]
""")

# ---------------------------------------------------------------------------------------------- section 4, head, and 4.2
between('''The design's "done when" for step 2: the river and closed-basin tests pass.''', "### 4.1 What was built", '''The design's "done when" for step 2: the river and closed-basin tests pass. Section 4.2 holds them
against the build, and sections 4.3 to 4.6 go further than the design asked, on Earth's own data.
By that "done when", read strictly, step 2 is not done: one closed-basin test, the Caspian, fails as
built. I count the step closed with that failure stated. The reasons are in sections 4.4 and 4.5; the
judgment is mine and yours to overrule.

''')
swap('''| Earth: the Amazon reaches the Atlantic and the Nile the Mediterranean | Pass: 203 and 270 km from their mouths, where 600 km was allowed. The Amazon passes however the ties of the relief are settled. The Nile passes in 19 of 20 random settlements, and by a way that is not its valley (section 4.4) |''',
     '''| Earth: the Amazon reaches the Atlantic and the Nile the Mediterranean | Pass as built: 203 and 270 km from their mouths, where 600 km was allowed. The Amazon passes however the ties of the relief are settled. The Nile passes in 10 of 20 random settlements, and by a way that is not its valley: its pass is no finding (section 4.4) |''')
swap('''| Earth: the Caspian stays closed | **Not decided by the relief data.** As the engine settles ties the lake overflows, by 0.47 km³ of the 669 that reach it in a year. In 20 random settlements of the ties it stays closed in 5. It stands at the brim of its hollow, at about three times the real sea's size (section 4.4) |''',
     f'''| Earth: the Caspian stays closed | **Fails as built.** As the engine settles ties the lake overflows, by 0.47 km³ of the 669 that reach it in a year. In random settlements of the ties it stays closed in 10 of 20 and in 55 of 100: it stands at the brim of its hollow, and the ties decide whether a little runs over. {V.CASPIAN_SHARES} What no settlement and no share changes: the lake is two to three times the real sea's size, or more (sections 4.4 and 4.5) |''')

# ---------------------------------------------------------------------------------------------- section 4.3
between("**How the tests are built.**", "| Process | Fed with | Condition | When set | Result |", '''**How the tests are built.** A test hands one process inputs measured on Earth and asks for a pattern
an atlas shows: given the truth as its input, does the process return the truth? Each condition says
where it comes from. "The design's" means that the pattern stands in the design document's table of
tests, which was written and approved before any code: the Amazon reaches the Atlantic, the Caspian
stays closed. The numbers that make a test of such a pattern (within how many kilometres, by what
factor) are not in the design; they were chosen when the test was written. "Found, then kept" is
something a run showed, or a condition written with its result in view; it guards a result and
proves less. A design condition that the engine fails is not loosened: it stays, marked as an
expected failure, with the number measured.

No number of these tests can be shown to have been set before a run. Every Earth test came into the
repository together with its first results, and for the 24 river mouths the first commit says "Found,
then kept" itself. Earlier versions of these notes and of the test file called several conditions
"set before the run"; the fourth check found that the history bears that out for none of them, and
the label is gone. [MEASURED: `git log` of `tests/test_earth.py`]

The second review of step 2 found conditions of mine that had been written after the run and could
not fail; they are labelled for what they are, and every miss that a test asks about is an expected
failure. Their count is not the count of known misses: sections 4.4, 4.6 and 8 list misses that no
test states, among them the lake at the Caspian's place at two and a half to three times the real
sea's size, three rivers that meet their condition by ways that are not their valleys, and the far
south of the Earth twin, 7 K too warm.

**What the river tests can show.** Less than I first wrote, and less again than I wrote after the
third check. The relief data decide most of what the rivers do, before any process runs (section
4.4). The tests settle the exact ties of the relief twenty times at random beside the engine's own
way, with everything drawn that the heights leave open; the tool does it a hundred times. A reason
names a cause only where a tool measures it.

''')
between("| Process | Fed with | Condition | When set | Result |", "All [MEASURED: `tests/test_earth.py`, on the standard mesh].", '''| Process | Fed with | Condition | Where it comes from | Result |
|---|---|---|---|---|
| SeaLevel | Earth's relief, the planet file's water | The sea rests within 60 m of Earth's level and covers 69 to 73 % of the planet, as one ocean | The design's pattern; the bounds chosen with the test | Pass: −5 m, 70.3 % |
| SeaLevel | the same | The Black Sea, the Red Sea and the Baltic are part of the ocean | Stated as misses | **3 fail.** The relief data cut the Black Sea off themselves: on their own grid the lowest way from it to the ocean rises to 2 m. The Red Sea and the Baltic are ocean in the data; their straits are narrower than a cell and closed on the mesh |
| Drainage | Earth's relief (valley floors: section 4.5) | The design's two conditions for Drainage (section 4.2): the Amazon reaches the Atlantic and the Nile the Mediterranean; central Asia and the Great Basin are closed | The design's patterns; the 600 km chosen with the test | Pass as built. The Nile passes in 10 of 20 random settlements of the ties |
| Drainage | the same | Each of 24 great rivers leaves the land within 300 km of its real mouth | Found, then kept | As the engine settles ties **16 pass, 8 fail**; in a random settlement 14 to 17 pass. 14 rivers pass in all of 20 settlements, 6 in none, and 4 are decided by the ties: section 4.4 |
| Hydrology | Earth's relief, rain and warmth | Of the rain on land, 0.50 to 0.75 goes back to the air; 28 to 52 thousand km³ a year reach the sea | The bounds chosen with the test | Pass, at the dry end: 0.735 and 31.7, whatever the ties. Earth: 0.65 and 40 [DOCUMENTED: Trenberth, Fasullo and Mackaro 2011] |
| Hydrology | the same | The largest flow into the sea is the Amazon's, within a factor of two | The design's pattern; the bounds chosen with the test | Pass |
| Hydrology | the same | Each of 21 great rivers carries, at its last gauging station, the flow measured there within a factor of two | Found, then kept | As the engine settles ties **7 pass, 14 fail**; in a random settlement 6 to 9 pass. 6 rivers pass in all of 20 settlements, 11 in none, and 4 are decided by the ties: section 4.4 |
| Hydrology | the same | Like for like, the land of the great basins sheds within 15 % of the depth measured | Stated as a miss, after the third check | **Fails: 0.68** of the measured depth, over the 14 basins whose size on the mesh is like the real one's (0.64 without the Amazon, which carries half the weight) |
| Hydrology | the same | The Caspian stays closed | The design's | **Fails as built** (section 4.2) |
| Hydrology | the same | Lakes cover under 4 % of the land | Stated as a miss | **Fails: 6.0 %**. Earth: 3.7 % of its ice-free land, lakes of all sizes [DOCUMENTED at second hand: Verpoorter et al. 2014] |
| Hydrology | the same | The basin of the Congo holds no great lake | Stated as a miss | **Fails**: a lake of 880,226 km². The relief data close the river's valley |
| Hydrology | the same | The Black Sea, the Baltic and the Great Lakes come back as lakes near their real size; open water at the Caspian's place loses 0.8 to 1.1 m a year | Found, then kept | Pass: 472,814, 294,490 and 298,119 km²; 1.00 m at the place tested, 0.94 m over the whole lake |
| Biomes | Earth's rain and warmth | Each of the five main climate groups takes a share of the land within 6 points of Peel, Finlayson and McMahon 2007 | The design asks for more, agreement with the published map; five shares and the 6 points were chosen with the test | Pass: tropical 21.1 (19.0), dry 24.7 (30.2), temperate 13.3 (13.4), cold 26.2 (24.6), polar 14.7 (12.8) |

''')

# ---------------------------------------------------------------------------------------------- section 4.4
between("### 4.4 The great rivers, taken apart", "### 4.5 The valley share", (HERE / "sec44.md").read_text(encoding="utf-8").rstrip("\n") + "\n\n")

# ---------------------------------------------------------------------------------------------- section 4.5
between("### 4.5 The valley share", "### 4.6 The Earth twin", V.SEC45)

# ---------------------------------------------------------------------------------------------- section 4.6 (numbers) and 4.7
if V.TWIN_TABLE:
    between("| | Twin, standard mesh | Twin, preview mesh | Earth |", "The twin's columns are [MEASURED:", V.TWIN_TABLE)
swap("is known, on relief the engine did not make.\n", "is known, on relief the engine did not make. A test holds the lines of the tool's report against\nnumbers worked out apart from it.\n")
between("### 4.7 Run times", "### 4.8 What step 2 changed in the default world", V.SEC47)

# ---------------------------------------------------------------------------------------------- section 5
swap("""own. Their reports are summarised here. Every finding marked high or medium has a test. The
second review of step 1 found three such tests that also passed on the faulty code; they were
rewritten, and from then on each new test was run against the code as it stood, to see it fail.""",
     """own. Their reports are summarised here. Every finding marked high or medium that a test can hold
has one; a finding about what I had written is mended in the text, and no test can hold that. The
second review of step 1 found three such tests that also passed on the faulty code; they were
rewritten, and from then on each new test was run against the code as it stood, to see it fail.""")
swap("| Step 2, 4. A check of those changes, and of the engine, the tests, the tools and these notes | ⟦FOURTH_FOUND⟧ | ⟦FOURTH_CHANGED⟧ |",
     "| Step 2, 4. Two reviewers: the changes after the third check, and the engine, the tests, the tools and these notes | No wrong number in a world against slow methods on 3,450 rough grounds and on Earth's relief. 1 finding marked high, 8 medium, 4 between medium and low and 9 low, in what I had concluded, labelled and tested. The cause of the runoff shortfall was stated as measured, and was not. \"The same every time\" rested on random settlements that left out the step that decides most. The Volga's \"a fifth is the model's\" stood on one of two published figures that disagree. The one design condition that fails on Earth had been reworded as \"not decided\". A \"set before the run\" label contradicted the test's first commit. \"Why\" answers contradicted their numbers in five ways. The check of the table of hollows still let eight breakages through. Of 126 changes made on purpose, 56 went unnoticed; no test ran any tool | Section 5.3 |\n| Step 2, 5. One reviewer: the claims alone, in the notes, the README, the tests' reasons and the descriptions in the code | ⟦FIFTH_ROW⟧ | Section 5.4 |")
swap('''Left as found, and listed in section 8: the rain of rising ground falls in one cell, the seasons on
land are too weak, and the demand for water knows no cloud.''',
     '''Left as found, and listed in section 8: the rain of rising ground falls in one cell, the seasons on
land are too weak, and the land gives the air too much water.''')
swap('''  that says so. `tools/why_scan.py` reads every answer for water on land and holds it against the
  numbers of its cell. None contradicts them: 174,114 answers on the default preview world (every
  cell), 121,108 on the standard one (every 23rd cell) and 174,114 on the preview twin. [MEASURED]
  The scan knows the faults the first review found; it proves nothing about faults of another kind.''',
     '''  that says so. `tools/why_scan.py` reads every answer for water on land and holds it against the
  numbers of its cell. After these two reviews none contradicted them, by the rules the scan then
  had. The fourth check found five kinds of contradiction that those rules did not look for
  (section 5.3, which gives the counts of the scan as it stands). The scan knows the faults that
  the reviews found; it proves nothing about faults of another kind.''')
swap('''  [MEASURED: `tools/world_report.py`] Before the change the sea cell that a river runs into
  depended on the cell numbers for the land of 11 % of the preview world and 8 % of the standard
  one; now for 0.2 % and 0.02 %. [MEASURED] Nothing on land changed: on the preview mesh 48 of the
  52 fields are the same bit for bit, and the four that differ are the receiver of 146 coastal
  cells, their slope, and the two fields that say which sea cell takes a river's water. [MEASURED:
  the preview world built before and after] On the standard mesh the report of the world is the
  same line for line, but for the last digits of the sum of the rivers. [MEASURED]''',
     '''  [MEASURED: `tools/world_report.py`] With the order of the cells turned round, the sea cell
  that a river runs into was another for the land of 13.9 % of the preview world and 12.9 % of the
  standard one before the change, and is another for 0.2 % and 0.02 % now. [MEASURED by the fourth
  check, both pairs by one measure; I had set the 0.2 % and 0.02 % beside 11 % and 8 %, which are
  the land whose sea cell changed with the rule, another measure] On the preview mesh 48 of the 52
  fields are the same bit for bit, and the four that differ are the receiver of 146 coastal cells,
  their slope, and the two fields that say which sea cell takes a river's water. [MEASURED: the
  preview world built before and after] On the standard mesh the same four fields differ: the
  receiver and the slope in 557 coastal land cells, the other two in sea cells only. The report of
  the world is the same line for line but for the last digits of the sum of the rivers. [MEASURED:
  the standard world built before and after, compared entry by entry; the fourth check found the
  557 cells]''')
swap('''  3e-14 mm below empty). A driver that names a cell or a row is printed as "cell 456", not as
  "456 m³/s". A branch of the lake flows that no case reached is gone. [MEASURED: 60 rough grounds
  under random climates] The fingerprints of the code and of the lock file do not depend on line''',
     '''  3e-14 mm below empty). A driver that names a cell or a row is printed as "cell 456", not as
  "456 m³/s". A branch of the lake flows that no case reached is gone. [MEASURED: 60 rough grounds
  under random climates, and 1,110 more of the fourth check. That check built by hand the one case
  that reaches it: a hollow that receives less than a millionth of a cubic metre of water a year,
  over ground that loses nothing when flooded. The water concerned is that millionth] The
  fingerprints of the code and of the lock file do not depend on line''')
between("**Not mended: the same world on another processor.**", "## 6. What is not done, and why", V.SEC53 + '''**Not mended: the same world on another processor.** The second reviewer of step 2 built the default
world on a processor without the AVX-512 instructions and got other last digits: differences of at
most 4 parts in a million, no class changed. [MEASURED by the reviewer, with the instructions
switched off; the fourth check measured it again on the preview mesh: 21 of 52 fields, at most 3.3
parts in a million, no class, index or true-or-false value] The design's promise is the same world,
bit for bit, on one machine with the pinned versions, and that holds. [MEASURED: two fresh
interpreters] Across machines it does not hold to the last bit, and I know no way to make it hold
short of giving up the fast mathematics library. A world store carries its own fingerprints, so a
difference is seen, not hidden.

''')

# ---------------------------------------------------------------------------------------------- section 6
swap('''   would make the tests of the mouths and the gauges mean something about Drainage. It is not among
   the data the build environment reaches.
''', f'''   would make the tests of the mouths and the gauges mean something about Drainage. It is not among
   the data the build environment reaches.
10. **Nothing was run on Windows.** The owner's machine is a Windows laptop. Paths, text encodings
    and line endings are handled for it and tested as far as Linux can show (section 5.3); the
    install by the lock file, the build, the viewer and the tools have not been run there.
{V.NOT_DONE_REVIEW}''')

# ---------------------------------------------------------------------------------------------- section 7, items 14 and 20
between("14. **The demand for water, and its error over land.**", "    **The rule is applied to the whole day, which is not the paper's way.**", '''14. **The demand for water, and its error over land.** The Priestley-Taylor rule needs the energy the
    ground gains from radiation. The engine's own energy balance is a budget at the top of the air and
    does not give it. Hydrology therefore uses the two radiation formulas of the paper it takes the
    rule's constants from. [DOCUMENTED: Davis et al. 2017, equations 10 to 13] They ask for the share of
    the possible hours of sunshine, cell by cell and month by month. The engine has no clouds, so one
    share, 0.62, stands for every cell and month. [INFERRED] With it the formulas return the means of
    Earth's whole surface: 161 W/m² of sunlight absorbed and 63 W/m² of heat lost. [DOCUMENTED for
    Earth: Trenberth, Fasullo and Kiehl 2009, Table 2b] Over land alone they do not:

    | Over land, W/m² | The engine's formulas under Earth's measured temperatures | The published budget of the land |
    |---|---|---|
    | Sunlight that reaches the ground | 185.6 | 184.7 |
    | Sunlight that the ground absorbs | 154.0 | 145.1 |
    | Heat that the ground radiates away | 68.3 | 79.6 |
    | Left to warm the air and evaporate water | 85.7 | 65.5 |
    | Of that, taken by evaporation | 45.1 (Hydrology under Earth's measured rain) | 38.5 |

    [MEASURED: `python tools/earth_demand.py`, and a test that holds every number; DOCUMENTED for the
    right-hand column: the same table's row for land, "This paper": net solar 145.1, solar reflected
    39.6, net longwave 79.6, evaporation 38.5, sensible heat 27. It is a published synthesis for 2000
    to 2004, not a measurement of one kind] The land is left 1.31 times the energy of the budget, and
    gives the air 1.17 times the water. The excess of 20.2 W/m² taken apart: 0.7 from the sunlight
    that reaches the ground, 8.2 from the ground reflecting 0.17 of it where the budget has 0.21, and
    11.3 from the formula for the heat radiated away. The share of sunshine sets the first of these,
    and the first is right: the share that would return the budget's sunlight at the ground is 0.61.
    The formula for the heat loss would want a share of 0.76; no single share mends both.

    What this does and does not show. It shows where the formulas depart from one published budget
    of all land, on the land's mean. It does not show where on the land the energy is too much: the
    budget is one number. And it does not show that the excess is why rivers get too little: part of
    it lies on snow, ice and desert, where it takes no water, and section 4.4 shows that a cut of
    the demand with another cause mends the rivers as well and that no one factor mends the single
    basins. I left the published constants as published. I had written here that "the mend is a
    process that makes clouds"; nothing measured says so (section 11).

''')
between("20. **Exact ties go to the wider way.**", "21. **`potential_evapotranspiration` is not the paper's quantity of that name**", f'''20. **Exact ties go to the wider way.** The design's rule, each cell to its lowest neighbour, says
    nothing of neighbours that are equally low. They are common: on every coast, because the cells
    of one sea stand at one level and wide stretches of sea floor lie at one depth; and on any
    relief given in whole metres. A tie goes to the lower bed, then to the wider way, the longer
    boundary shared by the two cells, and last to the order of the cells. [INFERRED: mine. The
    wider way is a property of the mesh and not of the ground. It claims no knowledge of the ground;
    it only keeps most of the result from depending on how the cells happen to be numbered]

    How lengths are compared. The mesh has boundaries that are images of each other under the 120
    turns and mirrorings that map it onto itself, and exactly as long. Worked out, their lengths
    differ by the rounding errors of the geometry: up to 1e-12 of the longest boundary on the
    preview mesh and 1.5e-11 on the standard one. So every boundary takes the length of its family,
    the boundaries that are images of it, and the families are put in order of length. Images then
    tie exactly and the order of the cells settles them; there are {V.FAMILIES} families on the
    preview, the middle and the standard mesh. Two families whose lengths differ at all are told apart, by
    however little: on the standard mesh the two nearest differ by 5e-12 of the longest boundary,
    less than the rounding errors inside a family, so which of those two counts as the longer is
    settled by those errors, the same way for every image. {V.FAMILIES_8}

    Until the fourth check the lengths were rounded to a billionth instead. That is a grid, not a
    tolerance: two lengths on either side of a rounding step stayed apart, and 29 of the 4,160
    families of the standard mesh were split by their rounding errors, 580 of 16,512 one level
    finer. I had written that rounding "does not settle a tie", found in my own check that it does
    for those, and said so; both reviewers then proposed the families. Hydrology settles the ways
    across its lakes the same way; both processes take the rule from one function of the library.
''')

# ---------------------------------------------------------------------------------------------- section 8
if V.WORLD_TABLE:
    between("| | Standard mesh | Preview mesh | Earth |", "In order of how much they distort the world:", V.WORLD_TABLE)
between("* **The seasons on land are too weak, and too much land is white all year.**", "* **The engine has no clouds.**", '''* **The seasons on land are too weak, and too much land is white all year.** This is the largest
  known error, and step 2 did not touch it. On Earth's own relief the engine's land between 40° and
  60° north is 13.6 K warmer in July than in January, where Earth's is 30.9 K; the cold climates
  with warm summers take 2 % of the land for Earth's 25 %, and the polar climate 46 % for 13 %
  (section 4.6). In ten other seeds 11 to 47 % of the land is white all year. [MEASURED] The cause,
  as I read it, is the one spreading constant of EnergyBalance, which ties land to the sea too
  tightly. Run alone, EnergyBalance gives the centre of a continent 60° of longitude wide a swing
  of 10.7 K either side of its mean at 50° north, and one 140° wide a swing of 20 K. [MEASURED for
  the two swings; INFERRED that the constant is the cause: no mend has been tried] Later models of
  this family let the spreading vary with latitude and surface. [DOCUMENTED: Ziegler and Rehfeld
  2021] With weak summers the snow of land poleward of about 50° never melts; the white ground then
  gives the air no water, and the north is dry as well. [INFERRED: the chain is my reading]
''')
between("* **The engine has no clouds.**", "* **Half the land drains into closed hollows", '''* **The engine has no clouds.** Albedo gives every sky the same share of cloud, and Hydrology gives
  every month the same share of sunshine. The first costs the cloud decks of cool seas and the
  cloud bands of the tropics. [INFERRED: not measured against Earth] What the second costs is not
  known: on the mean of Earth's land the one share gives the right sunlight at the ground (section
  7, item 14), and nothing at hand measures sunshine by region.
''')
between("* **The land gives the air too much water and the rivers too little.**", "* **Rivers have no travel time", '''* **The land gives the air too much water and the rivers too little.** Under Earth's own rain and
  warmth the land gives the air 1.17 times what a published budget gives it, the land of fourteen
  great basins sheds 0.68 of the depth measured (0.64 without the Amazon), and 31.7 thousand km³ a
  year reach the sea where Earth's rivers carry 40. The cause is not established (section 4.4). The
  error is not even: the land sheds least in the Indus, the Yangtze and the Brahmaputra (0.13, 0.21
  and 0.23, the last on rain data that hold less than the river carries) and too much in four snowy
  basins of the north (the St Lawrence 1.45). Dry land sheds nothing at all, where on Earth it sheds
  its rare cloudbursts: a bucket fed with a month's mean rain knows no storm. Frozen ground is not in
  the model. [MEASURED for the numbers; INFERRED for the storm and the frozen ground]
''')
swap('''* **Rivers have no travel time and lakes do not even out the seasons.** A month's runoff is at the
  sea in the same month.''', '''* **Rivers have no travel time and lakes do not even out the seasons.** A month's runoff is at the
  sea in the same month. On the mesh's Volga 319 of the year's 342 mm are shed in April, where the
  real river carries about half its water in the spring flood. [MEASURED; DOCUMENTED for the river:
  Kalugin 2022]''')

# ---------------------------------------------------------------------------------------------- section 9
between("1. **The table of hollows has rules**", "2. **`flow_receiver` is −1 for a sea cell", '''1. **The table of hollows has rules**, stated in `data/tables.yaml` and checked by
   `library/lakes.py: check_table` whenever Hydrology runs: row 0 is the sea; the hollows with one
   bottom come first, one for every land cell without a receiver, and `depression_id` names the one
   that a cell's water ends in, down its receivers; a larger hollow is made of two earlier rows,
   which name it and each other and which no third row names, and has the bottom of the deeper;
   the two cells of a pass are neighbours and passes lead where the table says; heights are those of
   the field `elevation`, and none is missing or infinite where a rule asks for one; a hollow with no
   way out has no level; a hollow inside no other overflows into the sea or into ground whose own
   hollow overflows no higher. A Drainage that writes another kind of table must come with a
   Hydrology that reads it. [MEASURED: 48 ways of breaking the table, each refused in the words of
   its rule, and a test that ties each written rule to the refusals that enforce it] One thing the
   check cannot show: that the pass a hollow names is its lowest. A table that keeps every rule and
   names a higher pass is accepted, and the lake then stands too high. [MEASURED by the fourth
   check: 894 m for 530 m on a ground built for it] To show it Hydrology would have to find the
   hollows again.
''')

# ---------------------------------------------------------------------------------------------- section 10: sources
swap('''| Opened; the three rows read, and read out again by a page reader on 2026-10-05: land 145.1 absorbed, 39.6 reflected, 79.6 net loss of heat; globe 161.2 and 63 |''',
     '''| Opened; the three rows read, and read out again by a page reader on 2026-10-05, twice: land ("This paper") net solar 145.1, solar reflected 39.6, evaporation 38.5, sensible heat 27, net longwave 79.6; globe 161.2 and 63 |''')
swap('''| The Volga's basin: 1,360,000 km², 585 mm of precipitation and 262 km³ of runoff a year, "based on the author's calculations for current climatic conditions (since the late 1980s)" | Found by the third reviewer; then read out to me by a page reader, with the three sentences quoted |''',
     '''| The Volga's basin: 1,360,000 km², 585 mm of precipitation and 262 km³ of runoff a year, "based on the author's calculations for current climatic conditions (since the late 1980s)"; and in the same paragraph "The runoff coefficient of the Volga River is 0.38", which does not agree with the 262 km³; 30 % of the precipitation as snow; 53 % of the runoff in the spring flood | Found by the third reviewer; then read out to me by a page reader, three times in all, with the sentences quoted. The fourth check found the second figure, which my first two readings had not asked for |''')
swap('''| [FAO Irrigation and Drainage Paper 56, Chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm) | "a single value of 2.45 MJ kg-1 ... This is the latent heat for an air temperature of about 20°C" | Opened on 2026-10-05, beside Annex 3 above |
''', '''| [FAO Irrigation and Drainage Paper 56, Chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm) | "a single value of 2.45 MJ kg-1 ... This is the latent heat for an air temperature of about 20°C" | Opened on 2026-10-05, beside Annex 3 above |
| [The Python documentation, `sys.stdout`](https://docs.python.org/3/library/sys.html), read as its source for Python 3.13, `Doc/library/sys.rst` | "On Windows, UTF-8 is used for the console device. Non-character devices such as disk files and pipes use the system locale encoding (i.e. the ANSI codepage)": why printed text could end a run on Windows, and what `worldengine/console.py` does about it | Fetched from the CPython repository on GitHub and read |
''')

# ---------------------------------------------------------------------------------------------- section 11
assert s.count("## 11. Next") == 1
s = s[:s.index("## 11. Next")] + V.SEC11

Path("docs/BUILD_NOTES.md").write_text(s, encoding="utf-8")
left = [line for line in s.splitlines() if "⟦" in line or "TODO" in line]
print("written;", len(s.splitlines()), "lines; placeholders left:", len(left))
for line in left[:20]:
    print("   ", line[:160])
