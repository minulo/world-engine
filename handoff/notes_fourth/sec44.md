### 4.4 The great rivers, taken apart

Three tools print every number in this section: `python tools/earth_relief.py`,
`python tools/earth_rivers.py --settlements 100 --demands` and
`python tools/earth_rivers.py --trace RIVER`. [MEASURED] `tests/test_earth.py` holds the numbers
of the engine's own settlement and of 20 random ones, and the lines of the reports that carry
them. The counts of 100 random settlements are from one run of the tool; no test holds those.

**What I had wrong.** Two checks took my accounts of this section apart, with measurements of
their own. I have repeated each measurement with tools of mine, and they hold.

The third check:

* I laid six closed valleys to the mesh: "narrows narrower than a cell are closed at 60 km". Five of
  the six are closed in the relief data themselves, on their grid of 9 km.
* I wrote that on plains "the rule of the lowest neighbour takes a river across ground that is a
  little lower". The ground was not lower. It was exactly as high, and the cell numbers chose.
* I wrote that the land sheds too much in cold, wet plains, and that this is why the lake at the
  Caspian's place is too large. The comparison set unlike areas side by side. Like for like the land
  sheds too little in ten basins of fourteen, and 0.68 of the measured depth over all of them.

The fourth check, of the account I wrote after the third:

* I gave the shortfall a measured cause: the demand for water "1.31 times too high over land with one
  share of sunshine", with clouds as the mend. That was not measured. The table it rested on puts the
  sunlight at the ground within half a percent of the published figure, a cut of the demand with
  another cause fits as well, and neither cut mends the single basins (below, "What the land sheds").
* I counted in how many of 20 random settlements of the ties each river passes, and wrote "every time"
  and "never". The random settlements drew two of the four things that settle a tie between passes
  and left the other two as the engine has them. With all of it drawn, rivers that "never" passed
  pass half the time (below, point 2).
* I wrote of the Volga that "a fifth of the excess is the model's [MEASURED]". The source gives the
  river's runoff twice, and the two figures do not agree. On the other one the model's part is nothing.
* I laid the sixth closed valley, the St Lawrence's, to the width of a cell. It is closed by my own
  rule for putting the relief on the mesh (below, point 3).

What follows replaces those accounts.

**1. The relief data hold closed hollows of their own.** On ETOPO5's own grid, with water raised from
the ocean over everything else, 13.3 % of all that is not ocean lies under water when every hollow
is full. On the mesh, with the valley rule of section 4.5, it is 10.2 %, and another 3.6 % of the
land lies exactly level with that water: the mesh does not add hollows to Earth's relief on the
whole. Of the mesh's twelve lakes larger than 100,000 km², eleven lie in hollows that the data hold
as well; at five of the eleven the data's own hollow is a half to a fifth of the mesh's lake in
size. [MEASURED: the eleven by `tools/earth_relief.py`; the sizes by the fourth check] Some of those
hollows are real: the Caspian, the Black Sea, and the Great Lakes, whose beds the data
give. Others are not: the basins of the Congo, the Amazon and the Danube, the West Siberian plain and
the lowlands of the Amur and the Lena hold no such lakes on Earth. [MEASURED that the data hold the
hollows; UNVERIFIED, from memory, which of them are real] The six narrows:

| Narrows | In the data: the river above stands at | its valley rises to | joined to the ocean, by any way, at | On the mesh: the valley rises to | the lake above stands at |
|---|---|---|---|---|---|
| Congo, Bolobo to Kinshasa | 274 m | 610 m | 457 m | 518 m | 457 m |
| Danube, the Iron Gate | 98 m | 317 m | 317 m | 208 m | 177 m |
| Lena, Zhigansk to the delta | 91 m | 152 m | 152 m | 137 m | 122 m |
| Amur, below Komsomolsk | 76 m | 213 m | 122 m | 137 m | 107 m |
| Yangtze, the Three Gorges | 404 m | 945 m | 823 m | 762 m | 381 m |
| St Lawrence, below Quebec | open to the sea | | | 204 m | 102 m |

Five of the six are closed before the mesh sees them. A mesh of another spacing would be handed the
same closed valleys by these data. [INFERRED: not tried on another mesh. On this one the valley rule
lowers all five barriers, the Congo's from 610 to 518 m. At a valley share of 0.02 it brings the
Congo's down to 457 m, the level of the lake above it, and the ties then decide whether the river
takes its valley: section 4.5] Relief made for hydrology has its rivers cut in beforehand. [UNVERIFIED:
recalled; I know of such data sets but opened none] Nothing of the kind is among the four files.

**2. The heights tie, and ties decide where rivers go.** ETOPO5 is in whole metres, and 48 % of its
land lies in steps of 100 feet. On the mesh 17,454 of 48,733 land cells have a land neighbour at
exactly their own height; 91 m is the height of 1,543 cells and 61 m of 1,257. Where two ways are
exactly equal the rule of the lowest neighbour cannot choose, and the data cannot say which is
right. Of the 42,980 land cells that have a lower neighbour, 9,869 have several equally low: the
lower bed settles 3,296 of those, the wider way 6,521 and the order of the cells 52. Another 5,063
cells lie on level ground.

Until the third check such a tie went to the lower bed and then to the lower cell number. After the
bed it now goes to the wider way, the longer boundary between two cells (section 7, item 20). That
is no truer than the cell number. Its one merit is that it does not change when the cells are
numbered otherwise; what it leaves open, images of one boundary and level ground, still goes to the
order of the cells. [MEASURED by the fourth check: under a random renumbering the receivers of 525
to 627 land cells on level floors change, and no mouth, gauge or total moves] The measure of how
much ties matter: with the wider way left out again, the water of 15.5 % of the land reaches the
sea in another cell; with the order of the cells turned round, of 0.03 %.

As the engine settles ties is therefore one settlement among many, with no better claim to be
Earth's than another. So the ties are also settled at random: every way draws its width, every cell
its place in the order, and among passes of one height any may be taken. A result counts as a
finding only if the draws agree with the engine's settlement. A count of draws bounds little: "in
none of 20" rules out only what comes more often than about one time in seven.

| Outcome | As the engine settles ties | In 20 random settlements | In 100 |
|---|---|---|---|
| River mouths within 300 km, of 24 | 16 | 14 to 17 | 14 to 17 |
| … rivers that pass in all, in none, in some | | 14, 6, 4 | 14, 6, 4 |
| The Nile's mouth | 270 km: passes | passes in 10 | in 64 |
| The Yangtze's mouth | 60 km: passes | in 6 | in 38 |
| The Yenisei's mouth | 350 km: fails | in 1 | in 3 |
| The Huang He's mouth | 1,261 km: fails | in 14 | in 56 |
| Gauges within a factor of two, of 21 | 7 | 6 to 9 | 6 to 9 |
| … rivers that pass in all, in none, in some | | 6, 11, 4 | 6, 11, 4 |
| The Orinoco at its gauge (984 km³ measured) | 355 km³: fails | 350 to 606 km³; passes in 2 | 348 to 606; in 9 |
| The Yenisei at its gauge (577 km³) | 77 km³: fails | 73 to 810; in 3 | 71 to 847; in 14 |
| The Ob at its gauge (397 km³) | 604 km³: passes | 29 to 599; in 1 | 26 to 605; in 6 |
| The St Lawrence at its gauge (226 km³) | 470 km³: fails | 213 to 477; in 11 | 213 to 477; in 52 |
| The lake at the Caspian's place | overflows, by 0.47 km³ a year | closed in 10; overflows by up to 6.0 km³ | closed in 55; by up to 8.7 km³ |
| … its size | 1.11 million km² at 61 m | 1.08 to 1.11 million km² at 54 to 61 m | the same |
| Like for like, engine over measured | 0.68 | 0.64 to 0.70 | 0.63 to 0.72 |
| Rain on land that goes back to the air | 0.7352 | 0.7347 to 0.7352 | 0.7347 to 0.7353 |
| Rivers reaching the sea, thousand km³ | 31.72 | 31.72 to 31.77 | 31.71 to 31.77 |
| Land under lakes | 6.02 % | 5.99 to 6.03 % | 5.99 to 6.03 % |

Eight outcomes turn on the ties: four mouths and four gauges. Three of them pass as the engine
settles ties (the Nile's and the Yangtze's mouths, the Ob's gauge) and five fail, and none of the
eight is a finding. The Ob passes as built and in 6 random settlements of 100. The Huang He's mouth
and the St Lawrence's gauge fail as built and pass in more than half. The two columns of counts
disagree with each other as well: the Nile passes in 10 of the first 20 draws and in 64 of 100. The
totals of the land hardly depend on ties at all.

Until the fourth check the random settlements drew the widths and the order and left the choice
among passes of one height as the engine makes it: the pass whose lower cell lies lowest. That
choice is where a single cell's water would go when the lower cell is the far side of the pass.
When it is the hollow's own cell, the choice is no truer than any other: on Earth's relief 47 of
1,034 hollows then take a pass across a far cell level with the water, where a pass of the same
height led down. [MEASURED by the fourth check] With that step left as it was, the counts of 20 read
19, 6, 0 and 2 for the four mouths and 0, 6, 7 and 0 for the four gauges, and I wrote that the St
Lawrence and the Orinoco fail "in every settlement".

**3. The valley rule lowers divides and raises drowned valleys.** Section 4.5 hands Drainage the
floor of each cell's valleys. A cell that holds a shore and a range is then handed in at the height
of the shore: 2,078 of the 4,646 coastal land cells come in at 1 m or lower, and 69 of those have a
mean height above 300 m. The Danube shows what follows. The plain above the Iron Gate fills to 177 m
and overflows to the Adriatic through a coastal cell whose mean height is 544 m and which came in at
0 m.

The rule's other side closes the St Lawrence. A cell is sea on the mesh if its mean height lies
below the sea. A cell that holds an arm of the sea between high shores is therefore land, and the
rule gives it the height below which a tenth of its points above the sea lie: the water in it is
left out. Two of the cells that hold the estuary below Quebec are such cells: 62 % and 32 % of their
points are ocean in the data, their mean heights are 175 and 235 m, and they come in at 162 and
204 m. Of the 48,733 land cells, 3,951 are a tenth or more ocean in the data; 1,240 of those come in
above 10 m and 590 above 100 m. With every point of a cell counted instead, the estuary is open and
the river leaves the land 32 km from its real mouth. That reading is no better rule: it lays 4,008
land cells at or below the sea's level, where the rule as built lays 388, floods 11.5 % of the land,
and brings 15 great rivers within 300 km of their mouths where the rule as built brings 16.
[MEASURED: `tests/test_earth.py`; the fourth check found it]

**Where the rivers leave the land.** As the engine settles ties, eight of 24 great rivers leave the
land more than 300 km from their real mouths.

| River | Distance | In 100 random settlements | What was measured |
|---|---|---|---|
| Congo | 603 km | 603 to 738 km; within 300 km in none | The data close its valley (table above). The basin fills as a lake of 880,226 km² to 457 m and overflows westward, to the sea at 1.5° south |
| Danube | 1,212 km | 1,171 to 1,212 km; in none | The data close the Iron Gate. The plain above it overflows to the Adriatic, through the lowered divide described above |
| Amur | 1,274 km | up to 1,290 km; in none | The data close the lower river, and join the lowland above it to the ocean by a way south. On the mesh the water leaves south, to the Sea of Japan |
| St Lawrence | 1,090 km | the same; in none | The valley rule closes the estuary (point 3). The lake above it overflows south, by Lake Champlain and the Hudson |
| Ob | 633 km | 633 to 734 km; in none | The river reaches the head of its estuary, 28 km from its real mouth, and runs on. The Gulf of Ob is ocean in the data, 3 to 13 m deep; the cells that hold it and its shores have mean heights of −7 to 8 m, and the mesh's sea stands at −5.3 m. On the mesh the gulf is a lake, and the river follows it to its seaward end |
| Yenisei | 350 km | 246 to 350 km; in 3 | The ties decide, mostly against the river. Near 66° north it leaves its valley, runs west over ground that is level at 30 m, and joins the Ob in its estuary |
| Huang He | 1,261 km | 64 to 7,570 km; in 56 | The ties decide, and the engine's settlement gives the rarer outcome. As built its way crosses 48 cells under the water of full hollows and 4 of level ground |
| Volga | 1,865 km | the same; in none | Not a fault of relief or mesh. The Volga ends in a closed sea, and this condition follows the water on as if every hollow were full. A river of a closed sea cannot meet it as I wrote it |

The condition asks where the water leaves the land, not by which way. Three rivers that pass do so
by ways that are not their valleys. The Nile leaves its valley near 22° north, crosses the hollows of
the Western Desert and reaches the coast 270 km west of the delta. The Yangtze passes south of the
Three Gorges, over a divide. The Lena leaves through a lake that overflows west of its delta. A pass
of this condition says less than it seems to.

**What the rivers carry.** The engine's flow at a gauge is the land whose water reaches it, times
what that land sheds, less what lakes on the way lose, less what a closed lake in the gauge's own
cell keeps. Each part is worked out by itself. The books of all 21 gauges close to within 0.00003
km³ a year, and those of every cell of the mesh to 6 parts in 100 million. Areas are in thousand
km², flows in km³ a year, depths in mm a year. Rivers in bold miss by more than a factor of two as
the engine settles ties.

| River | Flow measured | Flow, engine | Within a factor of two in, of 20 | of 100 | Basin on Earth | Land that reaches the gauge on the mesh | Shed, measured | Shed, engine | Lakes on the way lose |
|---|---|---|---|---|---|---|---|---|---|
| Amazon | 5,330 | 4,515 | 20 | 100 | 4,619 | 5,921 | 1,154 | 814 | 306 |
| Mississippi | 536 | 482 | 20 | 100 | 2,896 | 2,396 | 185 | 211 | 25 |
| Paraná | 476 | 480 | 20 | 100 | 2,346 | 2,987 | 203 | 168 | 23 |
| Ob | 397 | 604 | 1 | 6 | 2,430 | 2,865 | 163 | 244 | 96 |
| Ganges | 382 | 273 | 20 | 100 | 952 | 507 | 401 | 578 | 20 |
| Columbia | 172 | 117 | 20 | 100 | 614 | 484 | 280 | 303 | 29 |
| Rhine | 73 | 84 | 20 | 100 | 180 | 187 | 406 | 477 | 5 |
| **Congo** | 1,271 | 8 | 0 | 0 | 3,475 | 50 | 366 | 250 | 4 |
| **Orinoco** | 984 | 355 | 2 | 9 | 836 | 563 | 1,177 | 704 | 41 |
| **Yangtze** | 910 | 127 | 0 | 0 | 1,705 | 839 | 534 | 187 | 29 |
| **Brahmaputra** | 613 | 273 | 0 | 0 | 555 | 507 | 1,105 | 578 | 20 |
| **Yenisei** | 577 | 77 | 3 | 14 | 2,440 | 201 | 236 | 395 | 2 |
| **Lena** | 526 | 11 | 0 | 0 | 2,430 | 278 | 216 | 42 | 1 |
| **Amur** | 312 | 26 | 0 | 0 | 1,730 | 100 | 180 | 317 | 6 |
| **Mekong** | 292 | 143 | 0 | 0 | 545 | 275 | 536 | 559 | 11 |
| **Mackenzie** | 288 | 115 | 0 | 0 | 1,660 | 1,740 | 173 | 88 | 37 |
| **St Lawrence** | 226 | 470 | 11 | 52 | 774 | 1,244 | 292 | 443 | 81 |
| **Danube** | 202 | 24 | 0 | 0 | 807 | 145 | 250 | 181 | 2 |
| **Zambezi** | 105 | 11 | 0 | 0 | 940 | 233 | 112 | 71 | 6 |
| **Indus** | 89 | 0 | 0 | 0 | 975 | 69 | 91 | 0 | 0 |
| **Niger** | 33 | 5 | 0 | 0 | 1,516 | 116 | 22 | 78 | 4 |

The measured flows and basins are [DOCUMENTED: Dai and Trenberth, Table 2, the columns of the station.
A page reader gave me the rows; the areas were read out twice, and the two readings agree]. The rule
takes the largest flow within 150 km of the station. For the Ganges that is the mesh's Brahmaputra:
the cell taken lies 138 km from the Ganges's station, and the two stations lie 179 km apart. No cell
within 150 km of the Indus's station carries any water; the row gives the cell that the most land
drains to with every hollow full, which 69 thousand km² reach as the water runs, shedding nothing.

The fourteen that miss as the engine settles ties, by what was measured:

* **The data close the valley** (five): the Congo, the Lena, the Amur, the Danube and the Yangtze.
  The first four leave by another way; the Yangtze's Sichuan basin keeps its water as a closed lake.
* **The ties decide** (three): the Yenisei, the Orinoco and the St Lawrence, which pass in 14, 9 and
  52 of 100 random settlements. The Mekong may belong here: 7 of the 21 land cells on its way lie on
  level ground and it carries 31 to 143 km³ over the random settlements, but it passes in none. Its
  cause is not established.
* **Closed lakes upstream keep the water** (three): the Niger, the Zambezi and the Indus. With every
  hollow full their basins are of the right order or larger, and the climate the engine gives them
  never fills the hollows. The land sheds too little there (below), so these are misses of the
  water as much as of the relief.
* **The land sheds too little** (two): the Brahmaputra and the Mackenzie, whose basins are nearly
  right. For the Brahmaputra the rain handed in may be at fault as much as the model (below).

**What the land sheds, like for like.** The table above mixes two things: where the mesh runs the
rivers, and what the land sheds. To see the second alone, take for each gauge the mesh's own river
there, the cell within 150 km whose basin with every hollow full is nearest the real one in size,
and keep the basins within a factor of 1.5 of the real area. Fourteen are alike as the engine
settles ties. "Alike" here means near the gauge and alike in size. Whether the mesh's basin covers
the same land as the real one I could not check, because no map of the real basins is among the
data at hand: a basin of the right size may still take in a neighbour's land and leave out some of
its own. [UNVERIFIED: that the fourteen cover the land of their real basins] The Brahmaputra, alike
in 22 of 100 random settlements, and the Ob, in 6, show how loosely the mesh holds some of them.

| River | Basin on Earth | On the mesh | Rain handed in | Shed, measured | Shed, engine | Engine over measured | Measured runoff over the rain handed in | Alike in, of 20 | of 100 |
|---|---|---|---|---|---|---|---|---|---|
| Amazon | 4,619 | 5,154 | 2,339 | 1,154 | 828 | 0.72 | 0.49 | 20 | 100 |
| Orinoco | 836 | 563 | 2,080 | 1,177 | 704 | 0.60 | 0.57 | 19 | 96 |
| Yangtze | 1,705 | 1,567 | 1,151 | 534 | 115 | 0.21 | 0.46 | 20 | 100 |
| Brahmaputra | 555 | 735 | 1,013 | 1,105 | 257 | 0.23 | 1.09 | 3 | 22 |
| Mississippi | 2,896 | 2,431 | 947 | 185 | 208 | 1.13 | 0.20 | 20 | 100 |
| Paraná | 2,346 | 3,134 | 1,228 | 203 | 158 | 0.78 | 0.17 | 20 | 100 |
| Ob | 2,430 | 3,176 | 568 | 163 | 207 | 1.27 | 0.29 | 1 | 6 |
| Ganges | 952 | 967 | 1,045 | 401 | 231 | 0.57 | 0.38 | 20 | 100 |
| St Lawrence | 774 | 1,012 | 1,005 | 292 | 423 | 1.45 | 0.29 | 9 | 48 |
| Mackenzie | 1,660 | 1,690 | 426 | 173 | 88 | 0.51 | 0.41 | 20 | 100 |
| Columbia | 614 | 515 | 437 | 280 | 91 | 0.32 | 0.64 | 20 | 100 |
| Niger | 1,516 | 1,135 | 312 | 22 | 8 | 0.37 | 0.07 | 20 | 100 |
| Indus | 975 | 1,301 | 464 | 91 | 12 | 0.13 | 0.20 | 20 | 100 |
| Rhine | 180 | 178 | 1,118 | 406 | 479 | 1.18 | 0.36 | 20 | 100 |

All fourteen together, the engine's land sheds **0.68** of the depth measured, and 0.63 to 0.72 over
100 random settlements. Ten basins shed too little and four too much; nine are within a factor of
two. What the figure can bear:

* It is a mean weighted by water. The Amazon carries 53 % of it. Without the Amazon it is 0.64, and
  the median of the fourteen basins' own ratios is 0.59.
* Two of its rows cannot test what Hydrology does with rain. Over the mesh's Brahmaputra basin the
  rain handed in, 1,013 mm a year, is less than the runoff measured, 1,105 mm: no evaporation, however
  small, gives 1 there. Over its Columbia basin the runoff measured is 0.64 of the rain handed in.
  Either the rain data are low there or the mesh's basin is not the river's. Without the two the
  figure is 0.72. [MEASURED; the reading INFERRED]
* The engine's depth is taken before any lake loses water and the measured one after, which favours
  the engine. Taken after the engine's own lakes, as the flow at the same cells, it is 0.62.
  [MEASURED; the fourth check found it]
* It is not the same number as the shortfall of the rivers reaching the sea, 31.7 thousand km³ for
  Earth's 40, which is 0.79. The two point the same way and measure different land.

The four basins that shed too much (the St Lawrence, the Ob, the Rhine and the Mississippi) are
all snowy lands of the northern mid-latitudes, and so is a fifth that is not among the 21 because it
ends in a closed sea: the Volga sheds 1.8 or 1.5 times the published depth, like for like, according
to which of two published figures is taken (below, at the Caspian). For the Volga most or all of
the excess comes with the rain data. For the other four I have no published precipitation to hold
the rain data against. [MEASURED for the ratios; UNVERIFIED that the rain data are high there as well]

**Why the land sheds too little is not established.** What is measured [`python tools/earth_demand.py`;
section 7, item 14]: the radiation formulas leave Earth's land 85.7 W/m² to warm the air and
evaporate water, where a published budget of the land has 65.5, 1.31 times as much; and the land's
evaporation under Earth's rain takes 45.1 W/m², where that budget has 38.5, 1.17 times as much. The
excess of 20.2 W/m² is made of 0.7 from the sunlight that reaches the ground, 8.2 from the ground
reflecting 0.17 of it where the budget has 0.21, and 11.3 from the formula for the heat that the
ground radiates away. The sunlight at the ground, the one thing a share of sunshine sets, is right
on the land's mean.

As a diagnosis I ran the same tests with the demand for water multiplied by a factor: 0.76, the
ratio of the two energies; 0.794, which is the Priestley-Taylor rule with its factor of 1.26 taken
as 1.00, a cut with another cause; and 0.60.

| | Demand as it is | × 0.794 | × 0.76 | × 0.60 | Earth |
|---|---|---|---|---|---|
| Like for like, engine over measured | 0.68 | 0.93 | 0.97 | 1.23 | 1 |
| … its median over the fourteen basins | 0.59 | 0.87 | 0.91 | 1.12 | |
| … without the Amazon | 0.64 | 0.91 | 0.96 | 1.28 | |
| … basin by basin, lowest and highest | 0.13 and 1.45 | 0.28 and 1.67 | 0.32 and 1.74 | 0.42 and 2.28 | |
| … basins within 15 % of the measured depth, of 14 | 1 | 2 | 2 | 4 | |
| Rain on land that goes back to the air | 0.735 | 0.649 | 0.632 | 0.542 | 0.65 |
| … as a depth over the land | 581 mm | 513 mm | 499 mm | 428 mm | |
| Rivers reaching the sea, thousand km³ | 31.7 | 42.1 | 44.1 | 54.9 | 40 |
| Gauges within a factor of two, of 21 | 7 | 12 | 11 | 10 | |

[MEASURED: `python tools/earth_rivers.py --demands`; a test holds every cell of the table] That is
no setting of the engine and no fit. What it shows:

* A demand smaller by a fifth to a quarter would bring the weighted figure and the water of all the
  land to Earth's.
* The two cuts stand for different causes and mend alike, so the diagnosis cannot tell them apart.
  Nor can it tell either from a third cause that I did not think of.
* No one factor mends the basins. With the demand at 0.76 of itself the Amazon sheds 0.98 of its
  measured depth and the Niger 1.10; the Mississippi, the Paraná, the Ob, the Rhine and the St
  Lawrence shed 1.4 to 1.7 times theirs; and the Brahmaputra, the Columbia and the Indus a third.
  The error is not one factor on the demand.

What I had written here, that the table "shows that the error of the mean is the measured error of
the radiation", does not follow from it, and the cause I named, one share of sunshine for every
cell, is not what the radiation table shows to be off. Things I can name and did not test: the
ground's reflection and the heat-loss formula over land; the partition of the land's energy between
evaporation and warming the air, which the rule sets with one number; a rainy season as sunny as
the dry one; a bucket fed with a month's mean rain, which sheds water only when the month's rain
exceeds the month's demand and knows no storm; rain on a grid of 2.5°, which cannot hold the rain of
a mountain front; temperatures on a grid of 5°, read without regard to a cell's height; frozen
ground. [INFERRED: all of them. Nothing at hand measures radiation, sunshine or daily rain by region]

**The lake at the Caspian's place.** It is far too large however the ties are settled: 1.08 to 1.11
million km² at 54 to 61 m, where the real sea covers 371,000 to 436,000 km² in the sources I could
open and stands 28 m below the ocean. [DOCUMENTED at second hand: Wikipedia gives 371,000 km² without
the Garabogazköl lagoon and −28 m; a paper on the sea's level gives "about 436000 km2". The two
disagree and I could not settle it; either way the lake is two and a half to three times too large]
Whether it overflows is decided by the ties: as built it does, by 0.47 km³ of the 669 that reach it
in a year, and in 100 random settlements it stays closed in 55. That holds at the valley share of
a tenth alone. At each of the five other shares tried it stays closed in all of 20 random
settlements (section 4.5). Its books as the engine settles ties:

* Rivers and shores bring it 588 km³ a year. About 300 reach the real sea. [DOCUMENTED at second
  hand, the same paper: the Volga brings 237 km³ a year, about 80 % of the inflow]
* The land that drains to it covers 4.06 million km², the lake included; the real sea drains about 3
  million. [the same paper] The mesh's catchment holds the Don at Voronezh, which on Earth runs to the
  Black Sea.
* Each square metre of the lake loses 936 mm a year and gets 408 mm of rain.

Why twice the water arrives is established in part. The Volga gives most of it, and most or all of
the Volga's excess comes with the rain data:

| Over the land that drains through the Volga at Volgograd | Published for the real basin | On the mesh, under the rain data | On the mesh, handed the published precipitation |
|---|---|---|---|
| Area | 1.36 million km² | 1.25 million km² | the same land |
| Rain and snow | 585 mm a year | 744 mm | 585 mm |
| Shed to the river | 193 mm (262 km³ a year), or 222 mm (a runoff coefficient of 0.38) | 342 mm | 224 mm |
| Back to the air | 392 mm, or 363 mm | 402 mm | 361 mm |

[MEASURED for the mesh: the like-for-like measure at the place of Volgograd, in part 2 of
`tools/earth_rivers.py`. The third reviewer found the first of the two columns at Samara, with a
script of the reviewer's own: 775, 367 and 408 mm over 1.0 million km². DOCUMENTED for the basin:
Kalugin 2022 gives the area, 585 mm, "The annual runoff of the Volga River is 262 km3" and, in the
same paragraph, "The runoff coefficient of the Volga River is 0.38"; the depths in mm are my
arithmetic. The two figures do not agree: 262 km³ over the basin is 0.33 of the precipitation] The
ties do not decide it: in 100 random settlements the rain data hold 715 to 752 mm over that land.

The last column is a diagnosis. The rain data over that land are scaled by one factor in every
month, so that the year's total is the published one. The land then sheds 224 mm: 1.17 times the
one published figure and 1.01 times the other, where under the rain data it sheds 1.77 or 1.54
times. So four fifths of the river's excess, or all of it, come with the rain data, which hold a
quarter more over this land than the paper gives for the basin; the model's part lies between
nothing and a fifth. [MEASURED for the mesh's side] I had written "a fifth is the model's
[MEASURED]" on the 193 mm alone; the fourth check found the second figure in the same paragraph of
the source. The timing is the model's whatever the yearly sum: the engine makes 43 % of that
precipitation snow and sheds 319 of its 342 mm in April, where the paper has 30 % of it as snow and
53 % of the runoff in the spring flood. [MEASURED for the engine, by the fourth check and again by
me; DOCUMENTED for the paper's two shares]
Which of the two precipitations is nearer the truth I cannot say. [UNVERIFIED: I recall that GPCP
raises its gauge readings for the snow that gauges miss, which would put it above plain station
means; the page on GPCP that I opened does not say so]

The larger catchment adds to the lake's excess. My earlier sentence, that the snowy plains shed
too much, compared the runoff of a box with the published runoff of the basin and missed that the
rain differed.

**The land of the whole Earth, by this build:** 119.8 thousand km³ of rain a year (GPCP on the
mesh's land), of which 0.706 would go back to the air if no cell were flooded; lakes with an outlet
lose another 3.0 thousand km³ and closed lakes keep 0.4; 0.735 goes back in all, 581 mm a year over
the land, and 31.7 thousand km³ reach the sea. [MEASURED]

**What this leaves of the river tests.** The totals of the land and the like-for-like depths test
Hydrology. They show that the land gives the air too much and the rivers too little, by a size that
is measured and a cause that is not. The mouths and the gauges test the relief data, their ties and
the valley rule more than they test Drainage: of their 45 outcomes 8 turn on the ties, and of the
17 that fail in every draw, 9 are laid to valleys that the relief data or the valley rule close.
Drainage itself is held to its rule on
ground built for the purpose, where the answer is known (section 4.2). The third and the fourth
checks held it against slow methods of their own, on 90 and on 3,450 rough grounds and on Earth's
relief, and found no wrong receiver, hollow, pass or way across a lake. A fair test of rivers on
Earth needs relief with the rivers cut in, which is not among the data at hand.
