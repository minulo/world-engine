"""The prose of sections 4 (head), 4.3, 4.4 and 4.5 of docs/BUILD_NOTES.md, around the tables of sec4.py. Every number
in an f-string slot comes out of a log through handoff/notes_tools/logs.py; the few typed by hand are held by a test of
tests/test_earth.py that the sentence names, or carry their own label."""
import sec4
from sec4 import N


def head(d, o):
    return f"""## 4. Step 2: water on land

The design's "done when" for step 2: the river and closed-basin tests pass. Section 4.2 holds them
against the build. By that "done when", read strictly, step 2 is not done: one closed-basin test,
the Caspian, fails as built. The design's row for Hydrology also says "River flow data is still to
be chosen"; I chose 21 gauges, and {21 - o['gauges_n']} of them miss. I count the step closed with both stated. The
judgment is mine and yours to overrule (section 11).

Sections 4.3 to 4.6 hold the two processes against data sets of Earth. Every number in sections 4.2
to 4.5 was measured again after the fifth check, which changed the water that is poured on Earth's
relief and what a random settlement of the ties draws (section 5.4). The tables of sections 4.2, 4.4
and 4.5 are written out of the tools' logs by a script (`handoff/notes_tools/sec4.py`), not typed.

"""


def sec43(d, o, biomes):
    t20, w, c, ls, r = o["t20"], o["w"], o["c"], o["ls"], o["r"]
    return f"""### 4.3 Earth's data, and the Earth tests

Step 1 could not be tested against Earth: the build environment reaches package registries and GitHub
only. One public repository on GitHub carries four files that serve: NCAR's GeoCAT-datafiles, example
data for a plotting library.

| File | What it holds | Used for |
|---|---|---|
| `ETOPO5.DAT` | Height of land and sea floor, every 5 minutes of arc | Earth's relief on the mesh |
| `V22_GPCP.1979-2010.nc` | GPCP 2.2: precipitation, each month of 1979 to 2010, every 2.5° | Rain handed to Hydrology and Biomes; the yardstick for the twin's rain |
| `absolute.nc` | The Climatic Research Unit's mean surface temperature of each month, 1961 to 1990, every 5° | Warmth handed to Hydrology and Biomes; the yardstick for the twin's temperature |
| `landsea.nc` | A land-sea mask, every 1° | Rain over land by latitude |

`python tools/fetch_reference_data.py` fetches them from one pinned commit and checks each against its
size and SHA-256 (`tools/reference_data.yaml`). They are not kept in the repository. The repository
carries an Apache-2.0 licence file; the data sets were made by others, and the precipitation file
asks that GPCP be cited in anything published from it. [DOCUMENTED: the repository and the files'
own attributes] The readers live in `src/earth_reference/`, a package beside the engine that the
engine never imports. What is still missing: winds and pressure (ERA5), measured evaporation, a map
of climate classes, a map of river basins, relief with its rivers cut in, ocean-floor ages and crust
thickness.

**The inputs are data sets, not the truth.** The relief is in whole metres on a grid of 9 km. Rain
every 2.5° and temperature every 5° are read off between grid points at each cell's centre;
mountains narrower than that are not in them. No data set of snowfall is at hand: the snow handed to
Hydrology is made by the harness from each month's mean temperature. Where a published figure can be
set beside it, over the Volga's basin, the snow made is 43 % of the precipitation and the published
share 30 %, and what the land sheds there follows the snow (section 4.4). [MEASURED for the 43 %;
DOCUMENTED for the 30 %: Kalugin 2022] Earlier versions of this section said that a test hands a
process "the truth as its input"; the fifth check found that it does not.

**How the tests are built.** A test hands one process those data and asks for a pattern an atlas
shows. Each condition says where it comes from. "The design's" means that the pattern stands in the
design document's table of tests, which was written and approved before any code: the Amazon reaches
the Atlantic, the Caspian stays closed. The numbers that make a test of such a pattern (within how
many kilometres, by what factor) are not in the design; they were chosen when the test was written.
"Found, then kept" is something a run showed, or a condition written with its result in view; it
guards a result and proves less. A design condition that the engine fails is not loosened: it stays,
marked as an expected failure, with the number measured.

No number of these tests can be shown to have been set before a run. Every Earth test came into the
repository together with its first results. [MEASURED: `git log` of `tests/test_earth.py`] Every
miss that a test asks about is an expected failure. Their count is not the count of known misses:
sections 4.4, 4.6 and 8 list misses that no test states, among them the lake at the Caspian's place
at two and a half to three times the real sea's size, rivers that meet their condition by ways that
are not their valleys, and the far south of the Earth twin, 7 K too warm.

**What the river tests can show** is little about Drainage (section 4.4). Four things stand between
the relief data and a river, and none of them is the process under test: closed valleys in the data,
exact ties of whole metres, my rule for putting the relief on the mesh, and the volume of water
poured. The tests settle the ties twenty times at random beside the engine's own way; the tool does
it a hundred times. A reason of an expected failure names a cause only where a tool measures it.

| Process | Fed with | Condition | Where it comes from | Result |
|---|---|---|---|---|
| SeaLevel | Earth's relief, and the water that the ocean of the relief data holds ({r['own']:.4e} m³) | The sea rests within 60 m of Earth's level and covers 69 to 73 % of the planet, as one ocean | The design's pattern and the design's water; the bounds chosen with the test | Pass: {r['sea_level']:+.1f} m, {r['sea_share']:.2f} % |
| SeaLevel | the same | The Black Sea, the Red Sea and the Baltic are part of the ocean | Stated as misses | **3 fail.** The relief data cut the Black Sea off themselves: on their own grid the lowest way from it to the ocean rises to 2 m. The Red Sea and the Baltic are ocean in the data. On the mesh a cell is sea only if the water covers its mean height: the cell that holds the Red Sea's strait has a mean height of 15.8 m though 65 % of its points are ocean in the data, and the cell that keeps the Baltic apart 2.1 m with 75 %. (I had laid both to straits "narrower than a cell"; the fifth check measured the cells) |
| Drainage | Earth's relief (valley floors: section 4.5) | The design's two conditions for Drainage (section 4.2) | The design's patterns; the 600 km chosen with the test | Pass as built and in each of 20 random settlements |
| Drainage | the same | Each of 24 great rivers leaves the land within 300 km of its real mouth | Found, then kept | As built **{o['mn']} pass, {24 - o['mn']} fail**; in a random settlement {t20['mouths_random'][0]} to {t20['mouths_random'][1]} pass. {t20['mouths_all_none_some'][0]} rivers pass in all of 20 settlements, {t20['mouths_all_none_some'][1]} in none, and {t20['mouths_all_none_some'][2]} are decided by the ties |
| Hydrology | Earth's relief, rain and warmth; snow made by the harness | Of the rain on land, 0.50 to 0.75 goes back to the air; 28 to 52 thousand km³ a year reach the sea | The bounds chosen with the test | Pass, at the dry end: {w['back']:.3f} and {w['to_sea']:.1f}, of {w['rain']:.1f} thousand km³ of rain. A published budget has 0.65 and 40, of 114 [DOCUMENTED: Trenberth, Fasullo and Mackaro 2011] |
| Hydrology | the same | The largest flow into the sea is the Amazon's, within a factor of two | The design's pattern; the bounds chosen with the test | Pass |
| Hydrology | the same | Each of 21 great rivers carries, at its last gauging station, the flow measured there within a factor of two | Found, then kept | As built **{o['gauges_n']} pass, {21 - o['gauges_n']} fail**; in a random settlement {t20['gauges_random'][0]} to {t20['gauges_random'][1]} pass. {t20['gauges_all_none_some'][0]} rivers pass in all of 20 settlements, {t20['gauges_all_none_some'][1]} in none, and {t20['gauges_all_none_some'][2]} are decided by the ties |
| Hydrology | the same | Like for like, the land of the great basins sheds within 15 % of the depth measured | Stated as a miss, after the third check | **Fails: {ls['all']:.2f}** of the measured depth, over the {ls['alike']} basins whose size on the mesh is like the real one's ({ls['without_heavy']:.2f} without the Amazon, which carries {ls['heavy_weight']} % of the weight) |
| Hydrology | the same | The Caspian stays closed | The design's | **Fails as built** (section 4.2) |
| Hydrology | the same | Lakes cover under 4 % of the land | Stated as a miss | **Fails: {w['lakes_share']:.1f} %**. Earth: 3.7 % of its ice-free land, lakes of all sizes [DOCUMENTED at second hand: Verpoorter et al. 2014] |
| Hydrology | the same | The basin of the Congo holds no great lake | Stated as a miss | **Fails**: a lake of 880,226 km². The relief data close the river's valley |
| Hydrology | the same | The Black Sea, the Baltic and the Great Lakes come back as lakes near their real size | Found, then kept; the bounds are those of the first version | **2 pass, 1 fails.** The Baltic 265,947 km² at 8 m and the Great Lakes 298,119 km² at 179 m pass. The lake at the Black Sea's place, 612,693 km², stands at 32 m where the test asks for under 30: its outlet cell is 78 % ocean in the data, has a mean height of −5.6 m and is handed to Drainage at 32 m by the valley rule. Before the fifth check's change of the water it stood at 0 m and the test passed |
| Hydrology | the same | Open water at the Caspian's place loses 0.8 to 1.1 m a year | Found, then kept | Pass: 1.00 m at the place tested, {c['loses'] / 1000:.2f} m over the whole lake |
| Biomes | Earth's rain and warmth | Each of the five main climate groups takes a share of the land within 6 points of Peel, Finlayson and McMahon 2007 | The design asks for more, agreement with the published map; five shares and the 6 points were chosen with the test | Pass: {biomes} |

All [MEASURED: `tests/test_earth.py`, on the standard mesh]. The design asks Biomes for agreement with
the published map cell by cell; five shares are a weaker test, and the map is not at hand.

Earth itself meets the design's dry-belt condition: its driest land bands lie at 27.5° north (566 mm)
and 32.5° south (629 mm). [MEASURED from the rain data and the land mask]
"""


def sec44(d, o):
    t20, t100, w, c, ls, r, v, dm, cuts = o["t20"], o["t100"], o["w"], o["c"], o["ls"], o["r"], o["v"], o["dm"], o["cutrows"]
    like = o["like_rows"]
    low = min((x["ratio"], k) for k, x in like.items() if x["alike"])
    high = max((x["ratio"], k) for k, x in like.items() if x["alike"])
    above = sorted((k for k, x in like.items() if x["alike"] and x["ratio"] > 1), key=lambda k: -like[k]["ratio"])
    p = v["published"]
    c100 = t100["caspian"]
    return f"""### 4.4 The great rivers, taken apart

Three tools print the numbers of this section: `python tools/earth_relief.py`,
`python tools/earth_rivers.py --settlements 100 --demands` and `python tools/earth_demand.py`; the way
of one river, cell by cell, is `python tools/earth_rivers.py --trace RIVER`. [MEASURED: the logs of
these runs on the committed code are in `handoff/logs/`] `tests/test_earth.py` holds the numbers of
the engine's own settlement and of 20 random ones. The counts of 100 random settlements are from one
run of the tool; no test holds those. Where this section says what a river does on its way, the
reason of that river's expected failure in `tests/test_earth.py` says it at length, and a test beside
it holds its numbers.

Three checks took earlier accounts of this section apart (sections 5.2 to 5.4). What they left is
below. It says less than the accounts it replaces: numbers and what was measured, and a cause only
where a tool measures one.

**1. Four things decide where these rivers run, and none is Drainage.**

*The relief data hold closed hollows and closed valleys of their own.* On ETOPO5's own grid
{r['data_under']:.1f} % of all that is not ocean lies under water when every hollow of the data is full. On the
mesh, with the valley rule of section 4.5, it is {r['mesh_under']:.1f} %, and another {w['level_with']:.1f} % of the land lies exactly
level with that water. Of the mesh's {r['big'][0]} lakes larger than 100,000 km², {r['big'][1]} have their lowest point
in a hollow that the data hold as well. [MEASURED: `tools/earth_relief.py`, parts 2 and 4] Six narrows
of great rivers:

{o['narrows']}

{r['closed_in_data'][0]} of the six are closed in the data, before the mesh sees them. [MEASURED: `tools/earth_relief.py`,
part 3] Relief made for hydrology has its rivers cut in beforehand. [UNVERIFIED: recalled; I know of
such data sets and opened none] Nothing of the kind is among the four files.

*The heights tie.* ETOPO5 is in whole metres, and {r['hundred_feet']} % of its land lies in steps of 100 feet. On
the mesh {N(r['tied'])} of {N(r['land_cells'])} land cells have a land neighbour at exactly their own height. Of the
{N(r['choose'])} land cells that have a lower neighbour, {N(r['several'])} have several equally low: the lower bed
settles {N(r['by_bed'])} of those, the wider way {N(r['by_width'])} and the order of the cells {r['by_number']}. Another {N(r['level'])} cells
lie on level ground. With the wider way left out, the water of {r['moved_by_width']:.1f} % of the land reaches the sea
in another cell; with the order of the cells turned round, of {r['moved_by_numbers']:.2f} %. [MEASURED: `tools/earth_relief.py`,
part 1] Where two ways are exactly equal the data cannot say which is right, and the engine's rule
(the lower bed, then the wider way: section 7, item 20) claims no knowledge of the ground. As the
engine settles ties is one settlement among many. So the ties are also settled at random. A random
settlement draws four things: the width of every way, the order of the cells, which of several
passes of one height is taken, and the order in which level ground is drained. It does not draw
the way across the water of a full hollow, which decides the cells the water passes and not where
it leaves. A count of draws bounds little: "in none of 20" rules out only what comes more often than
about one time in seven. [Twice a check found that "in all" and "in none" had been counted over
draws that left a step out: the fourth, the choice among passes; the fifth, level ground.]

*The valley rule* (section 4.5) hands Drainage the floor of each cell's valleys and leaves out the
water in a cell. A cell is sea on the mesh if the poured water covers its mean height; a cell that
holds an arm of the sea between high shores is therefore land, and is handed in at the height of its
shores. Two of the cells that hold the St Lawrence's estuary below Quebec are such cells: 62 % and
32 % of their points are ocean in the data, and they come in at 162 and 204 m. Of the land cells, 3,418
are a tenth or more ocean in the data; 2,956 of those come in above 10 m and 1,125 above 100 m. The
same rule raises the lakes that stand for the Black Sea and the Baltic; and the Gulf of Ob, which is
ocean in the data, is not sea on the mesh. [MEASURED: `tests/test_earth.py`, the test of the estuary and the test of the seas
behind straits]

*The water poured* sets the level of the mesh's sea, and with it which cells are land, which points
of a cell the valley rule counts, and where a river "leaves the land". Section 4.5 gives what a
volume 0.19 % smaller decides.

**2. What the ties decide.**

{o['ties']}

[MEASURED: `tools/earth_rivers.py --settlements 20` and `--settlements 100`, part 7] An outcome that
changes with the settling is decided by the ties and not by anything measured: as built it is no
finding either way. That holds for {len(o['decided_mouths'])} mouths and {len(o['decided_gauges'])} gauges in this table. The totals of the
land hardly depend on the ties.

**3. Where the rivers leave the land.** As built, {24 - o['mn']} of 24 great rivers leave the land more than 300 km
from their real mouths.

{o['mouths']}

The condition asks where the water leaves the land, not by which way, so a pass says less than it
seems to. The Nile passes by distance alone, by a way west of its valley (section 4.2). Two rivers
pass by less than 10 km in every settlement: the Mississippi at {o['m']['Mississippi']['km']} km and the Mekong at {o['m']['Mekong']['km']}.
[MEASURED: part 3 of the tool; the ways by `--trace`]

**4. What the rivers carry.** The engine's flow at a gauge is the land whose water reaches it, times
what that land sheds, less what lakes on the way lose, less what a closed lake in the gauge's own
cell keeps. The books of all 21 gauges close to within {o['books']:.5f} km³ a year, and those of every cell
of the mesh to {o['cellbooks'] * 1e8:.0f} parts in 100 million. Areas are in thousand km², flows in km³ a year, depths
in mm a year. Rivers in bold miss by more than a factor of two as built.

{o['gauges']}

The measured flows and basins are [DOCUMENTED: Dai and Trenberth, Table 2, the columns of the
station. A page reader gave me the rows; the areas were read out twice, and the two readings agree].
The rule takes the largest flow within 150 km of the station. For the Ganges and the Brahmaputra
that is one and the same cell of the mesh: it lies 138 km from the Ganges's station. No cell within
150 km of the Indus's station carries any water; the row gives the cell that the most land drains to
with every hollow full. [MEASURED: part 1 of the tool]

I give no cause for a gauge's miss here. An earlier version sorted the misses into "the data close
the valley", "the ties decide", "closed lakes keep the water" and "the land sheds too little". The
fifth check showed that the sorting claimed more than was tested: with the Congo's valley open (a
valley share of 0.02) its gauge still misses, the Yangtze's basin sheds {like['Yangtze']['ratio']:.2f} of the measured depth
like for like, and the Lena's {t100['gauges']['Lena']['ratio_low']:.2f} in the {t100['gauges']['Lena']['alike']} of 100 settlements in which its basin is alike. What was measured beside each miss is in its reason in the test file.

**5. What the land sheds, like for like.** The table above mixes two things: where the mesh runs the
rivers, and what the land sheds. To see the second alone, take for each gauge the mesh's own river
there, the cell within 150 km whose basin with every hollow full is nearest the real one in size,
and keep the basins within a factor of 1.5 of the real area. {ls['alike']} are alike as built. "Alike" means
near the gauge and alike in size. Whether the mesh's basin covers the same land as the real one I
could not check: no map of the real basins is among the data. [UNVERIFIED: that they cover the land
of their real basins]

{o['like']}

All {ls['alike']} together, the engine's land sheds **{ls['all']:.2f}** of the depth measured ({t20['like'][2]:.2f} to {t20['like'][3]:.2f} over 20 random
settlements, {t100['like'][2]:.2f} to {t100['like'][3]:.2f} over 100). {ls['below']} basins shed too little and {ls['above']} too much; {ls['within_two']} are within a
factor of two; the lowest is the {low[1]} at {low[0]:.2f} and the highest the {high[1]} at {high[0]:.2f}. [MEASURED:
part 2 of the tool] What the figure can bear:

* It is a mean weighted by water. The Amazon carries {ls['heavy_weight']} % of it. Without the Amazon it is {ls['without_heavy']:.2f},
  and the median of the basins' own ratios is {ls['median']:.2f}.
* Two of its rows cannot test what Hydrology does with rain. Over the mesh's Brahmaputra basin the
  rain handed in, {N(like['Brahmaputra']['rain'])} mm a year, is less than the runoff measured, {N(like['Brahmaputra']['measured_depth'])} mm. Over its Columbia
  basin the runoff measured is {like['Columbia']['measured_over_rain']:.2f} of the rain handed in. Either the rain data are low there or
  the mesh's basin is not the river's. Without the two the figure is {ls['without_short']:.2f}. [MEASURED; the
  reading INFERRED]
* The engine's depth is taken before any lake loses water and the measured one after, which favours
  the engine. Taken as the flow at the same cells it is {ls['after_lakes']:.2f}.
* It is not the same number as the shortfall of the rivers reaching the sea, and the two measure
  different land.

The basins that shed more than measured are the {", the ".join(above[:-1])} and the {above[-1]}. The
share of snow in what the harness hands them runs from {min(like[k]['snow_share'] for k in above):.2f} to {max(like[k]['snow_share'] for k in above):.2f}; the Mackenzie ({like['Mackenzie']['snow_share']:.2f}) and the
Columbia ({like['Columbia']['snow_share']:.2f}) are as snowy and shed {like['Mackenzie']['ratio']:.2f} and {like['Columbia']['ratio']:.2f}. I had called the first group "all snowy
lands of the northern mid-latitudes"; the table does not bear a rule. [MEASURED]

**6. The Volga, under four precipitations.** The Volga ends in a closed sea and is not among the 21.
It is the one basin for which a published precipitation and a published share of snow are at hand
beside the published runoff: {N(p['rain'])} mm a year, {p['snow_percent']} % of it snow, over 1,360,000 km². The source gives
the runoff three times, and the three do not agree: 262 km³ a year ({p['by_volume']} mm), a runoff coefficient
of 0.38 ({p['by_coefficient']} mm) and a "water content" of 250 km³ ({p['by_content']} mm). [DOCUMENTED: Kalugin 2022; the depths
are my arithmetic] On the mesh the land that drains through Volgograd covers {N(v['mesh'] * 1000)} km².

{o['volga']}

[MEASURED: part 2 of the tool; a test holds the four rows] The last three rows are diagnoses. What
the four rows show, and all they show:

* If the published {p['rain']} mm and {p['snow_percent']} % are right for this land, the model sheds {v['published_snow']['over_coefficient']:.2f} to {v['published_snow']['over_content']:.2f} of
  the published runoff there, and the whole excess of the first row comes with what was handed in.
* If the rain data's {v['data']['rain']} mm are right, the model sheds {v['data_published_snow']['over_coefficient']:.2f} to {v['data']['over_content']:.2f} times the published
  runoff.
* The snow matters by itself: at either total, the harness's 43 % of snow in place of 30 % adds
  {v['scaled']['sheds'] - v['published_snow']['sheds']} to {v['data']['sheds'] - v['data_published_snow']['sheds']} mm to what the land sheds. Under every row the land sheds most of its
  year's water in April; the source has 53 % of the runoff in the spring flood.

Which precipitation is the true one is not known here. [UNVERIFIED either way] An earlier version
said "four fifths of the excess come with the rain data; the model's part lies between nothing and
a fifth". That rested on the second row alone, and on the published total being the true one.

**7. Why the land sheds too little is not established.** What is measured
[`python tools/earth_demand.py`; a test holds the table]:

{o['radiation']}

The published budget is a synthesis for 2000 to 2004, not a measurement of one kind. [DOCUMENTED:
Trenberth, Fasullo and Kiehl 2009, Table 2b] The formulas leave the land {dm['left'][2]:.2f} times the energy
that the budget leaves it, and the land's evaporation is {dm['evaporation'][2]:.2f} times the budget's. The second
comparison is not like for like: the engine is handed {w['rain']:.1f} thousand km³ of rain where the budget
that goes with the 0.65 has 114, and share for share it is {w['back']:.3f} of the rain for 0.65. The
excess of {dm['excess']['all']} W/m² is made of {dm['excess']['sunlight']} from the sunlight that reaches the ground, {dm['excess']['reflection']} from
the ground reflecting {dm['excess']['reflects']} of it where the budget has {dm['excess']['budget_reflects']}, and {dm['excess']['heat']} from the formula for the
heat that the ground radiates away. The one share of sunshine enters both formulas:

{o['sunshine']}

With 0.62 the sunlight at the ground is right on the land's mean and the heat loss is {dm['excess']['heat']} W/m²
too small; a share of {dm['wants'][1]} would return the heat loss and put the sunlight 13 % too high. No single
share mends both. What is measured points neither to clouds nor away from them. (I had written that
the sunlight at the ground is "the one thing a share of sunshine sets"; that is false of the
formula.)

As a diagnosis the same tests were run with the demand for water multiplied by a factor: 0.76, the
ratio of the two energies; 0.794, which is the Priestley-Taylor rule with its factor of 1.26 taken
as 1.00, a cut with another cause; and 0.60.

{o['cuts']}

[MEASURED: `python tools/earth_rivers.py --demands`; a test holds every cell of the table] That is
no setting of the engine and no fit. What it shows:

* A demand smaller by a fifth to a quarter would bring the weighted figure and the water of all the
  land near Earth's.
* The two cuts stand for different causes and mend alike, so the diagnosis cannot tell them apart,
  nor either from a cause that I did not think of.
* No one factor brings the basins' ratios to 1: at 0.76 they still run from {cuts[0.76]['lowest']:.2f} to {cuts[0.76]['highest']:.2f}. The
  ratios also carry the rain data and basins that are alike in size only, so this does not show
  what the error of the demand is.

Things I can name and did not test: the ground's reflection and the heat-loss formula over land; the
partition of the land's energy between evaporation and warming the air, which the rule sets with one
number; a rainy season as sunny as the dry one; a bucket fed with a month's mean rain, which knows
no storm; rain on a grid of 2.5°; temperatures on a grid of 5°, read without regard to a cell's
height; snow made from monthly means; frozen ground. [INFERRED: all of them. Nothing at hand
measures radiation, sunshine or daily rain by region]

**8. The lake at the Caspian's place** covers {c['area']:.2f} million km² at {c['level']} m as built, and {c100['area'][0]} to {c100['area'][1]}
million km² in 100 random settlements. The real sea covers 371,000 km² and stands 28 m below the
ocean. [DOCUMENTED at second hand: Wikipedia gives 371,000 km² without the Garabogazköl lagoon and
−28 m; a paper on the sea's level gives "about 436000 km2"] Either way the lake is two and a half to
three times too large. As built it overflows, by {c['overflow']:.1f} km³ a year; it keeps its water in {t20['caspian']['closed']} of 20
random settlements and in {c100['closed']} of 100. The water that runs over crosses {c['cells']} land cells and ends in a
second, closed lake of {N(c['ends_area'])} km²; it reaches the sea in none of the {t20['caspian']['overflowing']} of 20 and {c100['overflowing']} of 100 settlements
that overflow. That holds at this valley share; at two others it does not (section 4.5). Its books as built
[MEASURED: part 4 of the tool]:

* Rivers and shores bring it {c['brought']} km³ a year. About 300 reach the real sea. [DOCUMENTED at second
  hand, that paper: the Volga brings 237 km³ a year, about 80 % of the inflow]
* The land that feeds it covers {c['outside']:.2f} million km² without the lake ({c['catchment']:.2f} million with the ground
  under it). The paper gives about 3 million km² for the rivers that flow into the sea, and Wikipedia
  3.6 million km² for the sea's catchment. Like for like the land is not larger than the real one;
  the excess is in the depth, {c['depth']} mm a year off that land where 300 km³ off 3 million km² are 100 mm.
  (I had set the {c['catchment']:.2f} million, which holds the lake, beside the 3 million, which does not, and
  written that "the larger catchment adds to the excess".) The mesh's land {"holds" if c['voronezh'] else "does not hold"} the Don at
  Voronezh, which on Earth runs to the Black Sea.
* Each square metre of the lake loses {c['loses']} mm a year and gets {c['rain']} mm of rain.

Why twice the water arrives is not established. The land above Volgograd sheds {v['mesh'] * v['data']['sheds'] / 1000:.0f} km³ of it before
any lake on the way loses water [my arithmetic from point 6: {N(v['mesh'] * 1000)} km² times {v['data']['sheds']} mm], and point 6 leaves open
whether the Volga's excess comes with the precipitation handed in or is the model's.

**9. The land of the whole Earth, by this build:** {w['rain']:.1f} thousand km³ of rain a year (GPCP on the
mesh's land), of which {w['back_dry']:.3f} would go back to the air if no cell were flooded; lakes with an outlet
lose another {w['outlet_lose']:.1f} thousand km³ and closed lakes keep {w['closed_keep']:.1f}; {w['back']:.3f} goes back in all, {w['to_air_mm']} mm a
year over the land, and {w['to_sea']:.1f} thousand km³ reach the sea. {w['lakes']} lakes cover {w['lakes_share']:.2f} % of the land.
[MEASURED: part 5 of the tool] At the budget's share of 0.65 that rain would send {w['rain'] * 40.0 / 114.0:.1f} thousand km³
to the sea. [my arithmetic: 40 of 114]

**What this leaves of the river tests.** The totals of the land and the like-for-like depths test
Hydrology together with the data it is handed. They show that the land gives the air more and the
rivers less than a published budget has, and sheds less than was measured in {ls['below']} of {ls['alike']} gauged basins,
by a size that is measured and for a cause that is not. The mouths and the gauges test the relief data, their ties, the valley
rule and the water poured more than they test Drainage. Drainage itself is held to its rule on
ground built for the purpose, where the answer is known (section 4.2). The third and the fourth
checks held it against slow methods of their own, on 90 and on 3,450 rough grounds and on Earth's
relief, and found no wrong receiver, hollow, pass or way across a lake. A fair test of rivers on
Earth needs relief with the rivers cut in, which is not among the data at hand.
"""


def sec45(d, o):
    table, info = sec4.share_table(d)
    water, a, b = sec4.water_table(d)
    closed_built = [s for s in sec4.SHARES if not info[s]["caspian"]["engine_overflows"]]
    over_built = [s for s in sec4.SHARES if info[s]["caspian"]["engine_overflows"]]
    never = [s for s in sec4.SHARES if info[s]["caspian"]["closed"] == 20]
    areas = [x for s in sec4.SHARES if s != "0.5" for x in info[s]["caspian"]["area"]]
    to_sea = [s for s in sec4.SHARES if info[s]["caspian"]["to_sea"]]
    lakes = [info[s]["lakes"][0] for s in sec4.SHARES]
    seas = [info[s]["to_sea"][0] for s in sec4.SHARES]
    mouths = [info[s]["mouths_engine"] for s in sec4.SHARES]
    gauges = [info[s]["gauges_engine"] for s in sec4.SHARES]
    return f"""### 4.5 The valley share, and the water poured

**The valley rule.** A river runs along the floor of its valley, not at the mean height of the 60 km
around it. The design asked for "relief converted so that valley floors survive". The Earth tests
hand Drainage, for each land cell, the height below which a tenth of the cell's land points lie. The
rule and the tenth are mine. The tenth stands in the first commit of the Earth tests and in every
commit since. [MEASURED: `git log -S VALLEY_SHARE`] The history cannot show what was tried before
that commit; I recall trying no other value. [UNVERIFIED] The rule keeps valley floors, loses the
ridges between them and leaves out the water in a cell (section 4.4, point 1).

What the share decides, at thirteen shares. Each row is one run of
`python tools/earth_rivers.py --valley-share x --settlements 20`. [MEASURED: `handoff/logs/shares/`.
Tests hold the row of the tenth; nothing holds the other twelve]

{table}

What the rows show:

* **The counts hardly move.** As built {min(mouths)} to {max(mouths)} mouths and {min(gauges)} to {max(gauges)} gauges pass over the thirteen
  shares. Which rivers pass changes with the share and with the ties.
* **The water of all the land moves little.** From the smallest share to the largest, more land lies
  under lakes ({min(lakes):.2f} to {max(lakes):.2f} %) and less water reaches the sea ({max(seas):.2f} to {min(seas):.2f} thousand km³ a
  year), with one step the other way, between 0.07 and 0.08.
* **The closed Caspian fails as built at {len(over_built)} of the thirteen shares** ({", ".join(over_built)}) and holds at {len(closed_built)}
  ({", ".join(closed_built)}). At {len(never)} shares ({", ".join(never)}) the lake keeps its water in all 20 random
  settlements; at the others it overflows in some. No band of shares is safe, and the tenth is not a
  share at which the condition fails "alone", as I had written from six shares: the fifth check ran
  the shares between them.
* **Where the overflow ends depends on the share as well.** At the tenth it ends in a closed lake in
  every settlement that overflows. At {", ".join(to_sea)} it reaches the sea: {"; ".join(f"at {s} in {info[s]['caspian']['to_sea']} of the {info[s]['caspian']['overflowing']} random settlements that overflow" for s in to_sea)}.
  Whether it reaches the sea as built at those shares I did not look. [The sixth check found this in
  my own logs; I had left it out.]
* **The lake is far too large at every share:** {min(areas):.2f} to {max(areas):.2f} million km² up to a share of 0.3, {min(areas) / 0.371:.1f} to
  {max(areas) / 0.371:.1f} times the 371,000 km² of the real sea. At 0.5 the lake covers {info['0.5']['caspian']['engine_area']:.2f} million km², at {info['0.5']['caspian']['engine_level']} m.
* **The engine's own settlement is one draw among many.** At a share of 0.05 it gives a like-for-like
  figure of {info['0.05']['like'][0]:.2f}, outside the {info['0.05']['like'][2]:.2f} to {info['0.05']['like'][3]:.2f} of the 20 random settlements.

At {len(closed_built)} of the thirteen shares the Caspian's condition holds as built. I report the tenth, as
built: it fails. (I did not run the design's other Earth conditions at the other shares under the
water as it is now poured.)

**Another reading of the rule, as a diagnosis.** With the ocean points of a cell counted as well, at
the level of the mesh's sea, the St Lawrence's estuary is open and the river leaves the land 232 km
from its mouth; the Danube's water then leaves for the Adriatic, 1,212 km from its mouth. 16 mouths
pass for 15, 8 gauges for 8, and lakes cover 5.57 % of the land for 6.28 %. [MEASURED:
`earth_reference.other_valley_reading`; a test holds it] Tuning the rule moves single rivers and not
the counts. The tests stay on the rule as first chosen: the other was looked at with the results of
the first in view.

**The water poured.** The design's row for SeaLevel asks for "the volume of sea water measured from
that relief at full detail". Until the fifth check the Earth tests poured the planet file's volume,
0.19 % less, and no text said that it decides anything. It does. [MEASURED:
`python tools/earth_rivers.py --sea-water planet --settlements 20` beside the run as built]

{water}

The sea of the mesh stands 7.2 m lower under the planet file's water, 771 cells change between land
and sea, and the heights handed to Drainage differ in 3,850 of the land cells common to both.
[MEASURED: a test holds these] The Earth tests and tools now pour the relief's own water. The Earth
twin still pours the planet file's, because that volume is a parameter of the planet and the twin is
the engine as it stands (section 4.6).
"""
