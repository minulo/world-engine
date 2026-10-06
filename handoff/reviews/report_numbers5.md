# Fifth check of build step 2, part "numbers": Earth's rivers and the land's water

Work folder: `…/scratchpad/review_step2d/work_numbers` (scripts in `scripts/`, what they printed in `out/`). Labels: **[RAN]** I ran it in my copy and read the output. **[OPENED]** a source read through a page reader; direct download is refused by the proxy, and the reader gives quotations of at most 125 characters. **[READ]** taken from the builder's logs or stores. **[INFERRED]** my reasoning. Line numbers are those of HEAD `c8c8448`.

## 1. Verdict in five lines

1. The numbers hold. Every number of my sections that a tool prints, I printed again and got the same; the builder's logs for 100 settlements, the six shares, the twin and the two worlds agree with the texts; "pass" and "fails" follow the tests (33 fail under `--runxfail`, each with its reason's number); the published figures stand in their sources as read out to me.
2. The account built on them still claims more than was measured, in the places rewritten last. The worst: "the closed Caspian … fails at this share alone". Six shares were tried. At 0.09, 0.11 and 0.12 it fails as built as well, by 4 to 13 km³ a year, and at 0.11 and 0.12 in 20 and 19 of 20 random settlements.
3. Two things that decide the Earth outcomes are named nowhere. One is the volume of water poured: with the relief's own volume, which the design's row names, the lake overflows in all 20 settlements, the Nile passes in all 20 and the Amazon's mouth moves to 354 km. The other is the rule for level ground, which no draw touches: with it drawn, the Brahmaputra's gauge passes in 5 of 20 where the notes report none of 100 and give a cause.
4. Causes are still stated beyond the evidence. The Volga's "the model's part lies between nothing and a fifth" needs the paper's precipitation to be the true one. "The one thing a share of sunshine sets" is false of the formula, and the withdrawn "error of the one share of sunshine" still stands in section 7. Five gauge misses are laid to closed valleys though three miss on the water alone. The Caspian's "larger catchment" sets a figure with the lake beside one without.
5. I changed nothing under `/home/claude/world-engine`: its 136 files outside `.git`, `worlds`, `reference_data` and the caches have the same SHA-256 as my copy made at the start, and HEAD is `c8c8448`.

## 2. Findings, most serious first

### R1 (high). "It fails at this share alone" is false

**Where.** `docs/BUILD_NOTES.md` 768–769 ("it fails at this share alone"); 663–664 ("That holds at the valley share of a tenth alone"); 781–784 ("Whether a lake at its brim runs over is no finding either way").

**What the evidence shows.** [RAN] The builder's own tool at the shares between the six tried:

| Valley share | As the engine settles ties | In 20 random settlements |
|---|---|---|
| 0.07, 0.08 | closed | not run |
| 0.09 | overflows by 4.11 km³ a year | closed in 14, overflow up to 9.18 |
| 0.10 (the notes) | overflows by 0.47 | closed in 10, up to 5.99 |
| 0.11 | overflows by 12.78 | closed in **0**, up to 18.76 |
| 0.12 | overflows by 6.27 | closed in **1**, up to 16.17 |
| 0.13, 0.15, 0.17 | closed | not run |

So the design's condition fails over a band of shares. At 0.11 it fails however the 20 draws settle the ties, by 27 times the 0.47 that the notes report. "The ties decide whether a little runs over" is true at 0.09 and 0.10 only.

**How I know.** `python tools/earth_rivers.py --valley-share 0.11 --settlements 20` printed "engine: overflows by 12.78 km3 a year … at random: closed in 0 of 20, overflow up to 18.76 km3 a year". The same at 0.12 and 0.09 printed the rows above. `scripts/m8_shares_between.py` gave the shares as built.

**Left out, and it cuts the other way.** [RAN `m10_overflow.py`] In every case I traced, the overflow runs three or four cells east from 40.2° N, 56.9° E and ends on land in a second, closed lake near 42° N, 57° E (529 km² as built; 31 to 14,306 km² in the others). The cases are: as built at 0.09 to 0.12, and the six of random settlements 1 to 8 that overflow. Nothing reaches the sea. No text says where the overflow goes.

**True wording.** "Of the six shares tried it fails at the tenth alone. Between them it fails as well: at 0.09, 0.11 and 0.12 as built, by 4 to 13 km³ a year, and at 0.11 and 0.12 in 20 and 19 of 20 random settlements; it stays closed at 0.08 and below and at 0.13 and above. In every case traced the overflow ends in a second closed lake 250 km east; none of it reaches the sea."

### R2 (medium to high). The outcomes turn on the volume of water poured, which no text names as deciding anything

**Where.** Notes 321 ("the planet file's water"); `tests/test_earth.py` 152–153; section 7 has no item; every "the ties decide" of 4.2, 4.4 and 4.5.

**What the evidence shows.** The design's row for SeaLevel names "the volume of sea water measured from that relief at full detail" [READ: design document, table of tests]. The tests pour the planet file's 1.335e18 m³. ETOPO5's own ocean holds 1.3376e18 m³, 0.19 % more [RAN]. With that volume, valley share 0.1:

| | Planet file's volume | The relief's own |
|---|---|---|
| Sea level; sea's share | −5.3 m; 70.28 % | +1.9 m; 70.75 % |
| Lake at the Caspian's place, as built | overflows by 0.47 km³ | overflows by 17.88 |
| … closed in, of 20 random settlements | 10 | **0** (overflow 3.3 to 23.4) |
| Nile's mouth within 300 km, of 20 | 10 | **20** |
| Amazon's mouth | 203 km | 354 km, in all 20 |
| Mouths within 300 km / gauges within a factor of two, as built | 16 / 7 | 15 / 8 |

The valley rule counts a cell's points "above the sea", so 7 m of sea level changes the heights handed to Drainage.

**How I know.** `scripts/m12_sea_volume.py` and `m13_sea_volume_settlements.py`: the builder's harness, with the Harness handed the other volume.

**True wording.** "The Earth tests pour the planet file's volume, not the relief's own as the design's row says. That is a departure. With the relief's own volume the lake overflows in all of 20 settlements, the Nile passes in all 20 and the Amazon leaves the land 354 km from its mouth. The counts of section 4.4 are of one volume."

### R3 (medium). The random settlements still leave a step out: level ground

**Where.** Notes 315–316 ("with everything drawn that the heights leave open"); `tests/test_earth.py` 41–42, 249 ("On level ground nothing but the ties chooses the way"), 553–554; the help of `tools/earth_rivers.py`, part 7; notes 525 (Brahmaputra "0 | 0") and 556–557.

**What the evidence shows.** `library/drainage.py`, `receivers()`, drains level ground "ring by ring inward", each cell toward its nearest way out counted in cells. The draws choose only among neighbours one ring nearer. 5,063 land cells lie on level ground. [RAN `m15_level_ground.py`] I replaced that one rule, in my process only, by another that the heights allow (a tree grown from the ways out in random order):

- Engine's own ties, 10 draws: about 1,080 receivers differ. The Huang He's mouth passes in 3, the Brahmaputra's gauge in 3 (flow up to 510 km³), the Ob's gauge fails in 1, and the lake at the Caspian's place is closed in 3.
- Random settlements 1 to 20 with level ground drawn as well: the Brahmaputra's gauge passes in **5 of 20** (251 to 514 km³). The builder's logs have 0 of 20 and 0 of 100 (251 to 277), and the notes file it under "The land sheds too little". The Ob passes in 0 (29 to 150 km³). The Caspian is closed in 13.

This is one other rule and 20 draws; it bounds no more than that.

**True wording.** "A random settlement draws the widths, the order and the choice among passes of one height. It does not draw the way over level ground, which goes to the nearest way out counted in cells. With that drawn by one other rule the Brahmaputra's gauge passes in 5 of 20."

### R4 (medium to high). The Volga: the conclusion rests on a premise the notes say they cannot decide

**Where.** Notes 605–608, 674–675, 695–697 ("the model's part lies between nothing and a fifth. [MEASURED for the mesh's side]"), 372–373; `tests/test_earth.py` 981–982 and 998–999.

**What the evidence shows.**

- **The premise.** "Comes with the rain data" makes the model's part small only if the paper's 585 mm is the true precipitation. If the rain data's 744 mm is, the engine sheds 0.46 of a true rain where the basin sheds 0.26 to 0.30, and the whole excess is the model's. Line 703 says "Which of the two … I cannot say". [INFERRED]
- **The two precipitations differ almost only in snow.** [RAN `m11_volga_snow.py`; OPENED Kalugin 2022: "solid and liquid precipitation are 30% and 70%"] Rain data: 320 mm of snow and 424 of rain. The paper: 175 and 410. Of the 159 mm between them, 144 are snow.
- **The engine's runoff there is the snow it is handed.** [RAN]

| Handed in | Precipitation (snow), mm | Sheds | April | Of the 193 / of the 222 |
|---|---|---|---|---|
| The rain data | 744 (319) | 342 | 319 | 1.77 / 1.54 |
| One factor in every month (the notes) | 585 (251) | 224 | 222 | 1.17 / 1.01 |
| The paper's total with its 30 % of snow | 585 (179) | 178 | 162 | 0.92 / 0.80 |
| The rain data's total, 30 % of it snow | 744 (228) | 285 | 233 | 1.48 / 1.28 |

  The "1.17 or 1.01" comes from carrying the rain data's 43 % of snow into the published case. With the paper's own share the same land sheds less than published.
- **A third published figure is left out.** [OPENED] The same paragraph has "water content (250 km3 per year)", 184 mm. The harness's own comment gives it (`src/earth_reference/__init__.py` 525); the notes say the source gives the runoff "twice". On it the excess is 1.86 times and the model's part a quarter.
- **The unverified recollection at line 703 is documented.** [OPENED: GPCP Version 2 documentation, 26 September 2002; version 2, not 2.2] "corrected for climatological estimates of systematic error due to wind effects, side-wetting, evaporation, etc., following Legates (1987)". That does not say which precipitation is right.

**True wording.** "On this basin the engine sheds, in April, a depth equal to the snow it is handed. Under the rain data that is 320 mm, by the paper's figures 175. Handed the paper's total it sheds 224 mm with the rain data's share of snow and 178 mm with the paper's; the paper has 184, 193 or 222. If the paper's precipitation is right the excess comes with the rain data; if the rain data are right it is the model's. I cannot say which."

### R5 (medium). "The one thing a share of sunshine sets" is false, and the withdrawn cause still stands in section 7

**Where.** Notes 616–617; 1399–1400; 1419–1420 ("the error of the one share of sunshine is six times as large and of the other sign"); `library/evaporation.py` 35–37 (the same); 1642–1645 ("What is measured does not point to clouds").

**What the evidence shows.** The heat-loss formula takes the share as well: `net_longwave` is `(b + (1 − b) · sunshine)(A − T)`. [OPENED: Davis et al. 2017, equation 13: "ILW = [b + (1 − b) Sf](A − Tair)"] The tool prints the share that would return the heat loss, 0.76. [RAN `m3_sunshine.py`] Over Earth's land:

| Share | Sunlight at the ground | Heat radiated away | Left |
|---|---|---|---|
| 0.50 | 165.7 | 58.9 | 78.6 |
| 0.62 (built) | 185.6 | 68.3 | 85.7 |
| 0.763 | 209.3 | 79.6 | 94.1 |
| Budget | 184.7 | 79.6 | 65.5 |

Of the 20.2 W/m² excess, 11.3 lie in a formula that the share scales. "No single share mends both" is right. "The one thing" is wrong, and "the error of the one share of sunshine" is the cause that the fourth check found unmeasured (its N1) and that 4.4 withdraws.

**True wording.** "The share enters both formulas. With 0.62 the sunlight at the ground is right on the land's mean and the heat loss is 11.3 W/m² too small; 0.76 would return the heat loss and put the sunlight 13 % too high. What is measured points neither to clouds nor away from them." At 1419: "the energy the formulas leave the land is 31 % above the budget's, six times as much and of the other sign".

### R6 (medium). Causes of the gauge misses, and what sends two rivers astray

**Where.** Notes 546–557, 719–720; reasons in `OFF_AT_GAUGE`.

- **Gauges.** "The data close the valley (five)" is given as the cause. Three of the five miss on the water alone:
  - [READ `shares/share_0.02.log`] With the Congo's valley open and 3,641 thousand km² reaching the gauge, it carries 237 of 1,271 km³ and passes in 0 of 20. The land sheds 196 mm for 366 and lakes lose 478 km³.
  - [RAN] The Yangtze's own basin with every hollow full sheds 180 km³ against 910.
  - [READ 100-settlement log] The Lena, where its basin is alike (33 of 100), sheds 0.42.

  Four more basins fail on their own like basin's water (Brahmaputra 189 of 613, Niger 9 of 33, Indus 15 of 89, Mackenzie 112 of 288 after lakes). "The land sheds too little (two)" understates what the gauges say about Hydrology.
- **Danube and Lena.** [RAN `m4_raw_outlets.py`] The data's own hollow overflows through the valley: one outlet point at 317 m at 44.7° N, 21.7° E, and four at 152 m at 71.4 to 71.7° N, 125.2° E, all inside the valleys' boxes. The other way exists only on the mesh: 177 m and 122 m, where no way in the data is below 317 and 152. The notes say so for the Danube and not for the Lena. For the Congo, the Amur and the Yangtze the data's hollow does overflow elsewhere, and the mesh follows.

**True wording.** "The data close five valleys. Whether a gauge misses because of it was tested for none; with the valley open the Congo's still misses, and the Yangtze's and the Lena's basins shed 0.21 and 0.42. The Lena's water leaves west over a divide that the mesh has at 122 m and the data at 152 m or more."

### R7 (medium-low). The Caspian's catchment: unlike areas side by side

**Where.** Notes 669–671, 707 ("The larger catchment adds to the lake's excess"); `tests/test_earth.py` 976–977, 983.

**Evidence.** [RAN `m2_caspian.py`] 4.06 million km² is the land reaching the lake's outlet cell, with the lake's own 1.11 in it. Outside the lake it is 2.94. [OPENED] The paper's "about 3 million km2" is "the catchment area of the rivers flowing into the Sea". Like for like, 2.94 for about 3: not larger. Wikipedia, which the builder opened, has 3,626,000 km² in its box; it is not mentioned. No tool prints 4.06 or Voronezh.

**True wording.** "Outside the lake 2.94 million km² drain to it, as much as the real rivers' 3 million. The excess is in the depth: 200 mm for 100."

### R8 (medium-low). "1.17 times what a published budget gives it" is under 5 % more rain than that budget has

**Where.** Notes 613, 1396–1397, 1525–1526, 601; `data/models.yaml` 297; Hydrology's first lines; `tests/test_earth.py` 942–943.

**Evidence.** The engine is handed 119.8 thousand km³; the budget behind 0.65, 74 and 40 has 114 [OPENED: Trenberth, Fasullo and Mackaro 2011]. Share for share it is 0.735 for 0.649, 1.13 times. At Earth's share that rain would send 42.0 to the sea, so 31.7 is 0.75 of it, not 0.79. [my arithmetic]

**True wording.** "0.735 of the rain where the budget has 0.65, on 5 % more rain than the budget's."

### R9 (low to medium). "All snowy lands of the northern mid-latitudes"

**Where.** Notes 603–605, 1530–1531.

**Evidence.** [RAN `m1_basins.py`] Share of snow in what the harness hands in: Ob 0.41, St Lawrence 0.28, Rhine 0.11, Mississippi 0.09. The Mackenzie (0.35) and the Columbia (0.33) are snowier and shed 0.51 and 0.32.

**True wording.** "Four basins of the northern mid-latitudes; two are snowy."

### R10 (low to medium). The twin's lakes "on the same relief (8.5 % for 6.0 %)"

**Where.** Notes 849–851.

**Evidence.** The twin's Drainage is handed mean heights; the 6.0 % is of the valley rule. [RAN `m6_twin.py`] Earth's measured climate on the mean heights gives 7.3 %. Between 60° and 90° north, where all the twin's land is under snow all year, lakes cover 11.2 % for 11.0 %; the excess is at 40° to 60° north (18.9 for 14.1).

### R11 (low to medium). The design's third pattern for Hydrology is left out

**Where.** Notes 226–227 ("go further than the design asked"); the table of 4.2.

**Evidence.** [READ: design document, versions 6 to 440] The row reads "The Amazon carries the most water. The Caspian stays a closed lake. River flow data is still to be chosen". The data were chosen (21 gauges) and 14 miss.

**True wording.** "The design left river-flow data to be chosen. With the data I chose, 14 of 21 rivers miss; whether that belongs to the 'done when' is yours to say."

### R12 (low to medium). "Their inputs are the truth"

**Where.** `tools/earth_rivers.py` 8–9 ("Nothing of the engine's own climate enters"); `tests/test_earth.py` 3–4; notes 290–291.

**Evidence.** Snowfall is not measured. The harness makes it from monthly means on a 5° grid with Moisture's ramp. On the Volga that gives 43 % where the paper has 30 %, and it decides the runoff (R4).

### R13 (low; reasoning). Section 8's order

"In order of how much they distort the world" (1501) has no measure. Its second item says of itself "What the second costs is not known". It is a judgment and should be labelled one.

### R14 (low). Labels that do not hold their numbers

- Notes 343: "Three tools print every number in this section". None prints 4.06 million km², Voronezh, 43 %, 319 mm, 0.62, 175 and 235 m, or "15 great rivers". I measured each; all are true.
- Notes 1182: the 0.62 is "in the tool's report and in a test". It is in neither. [RAN: 0.622]
- Section 8's table is labelled `tools/world_report.py`. Two rows are not printed by it: "July less January" and "never reaches the sea". [RAN: 12.3 and 11.6 K from the builder's stores; 18.6 % in a preview build of mine]

### R15 (low). Leftovers and small things

- 782–783: "Every column shows … two to three times". The 0.5 column is 3.0 to 5.7 times. Mended at 773–777, left here.
- 974–975: "was written before it was run". 4.3 and the test say no record shows it.
- `tests/test_earth.py` 1225–1226: "The twin's land there is 7 K too cold (2.0 C … against 9.3 C)". Those are all cells, land and sea, from 30° to 60° north. [RAN on the builder's store] The land from 40° to 60° is −5.8 for 3.5 °C, 9.3 K. Its coldest month is right (−12.8 for −12.7) and its warmest is 17 K too cold (1.5 for 18.4). A land "tied to the sea too tightly" would have winters too warm; no text gives these two numbers.
- `tests/test_earth.py` 170–172, notes 322: "narrower than a cell" for the Red Sea and the Baltic. [RAN `m9_misc.py`] The closing cells are 65 % and 75 % ocean in the data, with means of +15.8 and +2.1 m. The mean-height rule closes them, as at the St Lawrence.
- 645: "The error is not one factor on the demand". Shown: no one factor brings the fourteen ratios to 1. The ratios also carry the rain data and basins that are alike in size only.
- 761: "at every share the ties move them as much as the share does". Not for the gauges: the share moves the engine's count by 3; the ties by 2 at three shares and 1 at 0.5.
- 1381–1383: the formulas "return" 161 and 63. `models.yaml` 323–325 gives 158.7 and 64.0.
- `tests/test_earth.py` 1072–1076: "Eleven of the twelve" lists ten. The lake at 61° N, 115° W (131,455 km²) is unnamed.
- 454–455: the two columns "disagree". The 20 are seeds 1 to 20 of the 100; 10 of 20 at a rate of 0.64 has a chance of 0.14.
- `tools/earth_demand.py` 1, 119, 130: the budget is still "measured" in the help and the report.
- 1639–1641: the four tests pass at three quarters of 31 K, at 15 % and at three quarters of the rain, not at the patterns named.
- 257, 325, 657: "however the ties are settled", "whatever the ties". These are 100 of 100 draws.
- 1497 against 659: the Caspian's area is [UNVERIFIED] in one place and documented at second hand in the other.

For the other reviewer, one line each: notes 974–975 (above); `data/models.yaml` 154–155 still labels "near a tenth" [UNVERIFIED], against 5.3's "in all"; `suite_code_state.txt` shows the suite ran on uncommitted files 19 minutes before the commit.

## 3. The fourth check's findings that are mine to follow

| | Status | Evidence |
|---|---|---|
| N1, cause stated as measured | Mended in the five places; one leftover, two new | "Not established" stands in 4.4, section 8, `models.yaml`, Hydrology's first lines and the reason. Leftover: 1419–1420 and `evaporation.py` 36. New: 616–617 and 1643 (R5) |
| N2, "every time" and "never" | Mended for the passes; the same shape remains | The passes are drawn; counts are given as counts; the library's description matches the code [READ]. Left: level ground (R3), the volume (R2) |
| N3, the Volga | Half mended | Both figures given, test renamed, April recorded. Left: the premise, the snow, the third figure (R4) |
| N6, the St Lawrence | Mended | [RAN] 62 % and 32 %; 175 and 235 m; 162 and 204 m; 32 km; 4,008 for 388; 11.5 %; 15 for 16. Same shape left at two straits (R15) |
| N8, what like for like can bear | Mended in 4.4 | 53 %, 0.64, 0.59, 0.72 by my arithmetic; 0.622 [RAN]. 5.3's "in the tool's report and in a test" is false of the 0.62 |
| N9, small numbers | Mended but one | 179 km, 21 cells, 69 thousand km², 443 against 423 mm, the Niger's books, the Congo's line at 0.02: all right now. "Two to three times" in "every column" remains |
| N10, labels | Mostly mended | "A published budget" in the notes, "measured" in the tool. Five `wrong_where` strings carry labels; eight (Tectonics, Isostasy, SeaLevel, Insolation, Circulation, Soils, Biomes, PlanetGeometry) do not |
| F1, failure as "not decided" | Mended in the verdict word, softened anew | "Fails as built" in 4.2, 4.3, 4.5, 11, the README and the reason; the Nile treated alike. New: "at this share alone" (R1) |
| F2, "set before the run" | Mended but one line | Gone from the test file and 4.3. [RAN git] 24 rivers and 300 km unchanged since `f61f923`; 21 gauges, 150 km and the factor since `41e3423`. Survivor: 974–975 |

## 4. Claims that I tested and found true

| Claim | Where | What I measured |
|---|---|---|
| Relief: 13.3 %; 10.2 % and 3.6 %; 48 %; 17,454 of 48,733; the tie counts; 15.5 % and 0.03 %; the narrows table; 2,078, 4,646, 69; eleven of twelve | 4.4, points 1 to 3 | [RAN] `earth_relief.py`: identical to the builder's log |
| Both river tables, 24 mouths, twelve lakes, water of the land, books to 2.1e-5 and 5.8e-8 | 4.3, 4.4 | [RAN] `earth_rivers.py`: identical; every cell compared |
| The column of 20 settlements | 4.4 | [RAN] identical |
| The column of 100 | 4.4 | [READ] the builder's log; every cell agrees |
| The table of the cuts; at 0.76 the Amazon 0.98, the Niger 1.10, five at 1.4 to 1.7, three at a third | 4.4 | [RAN] `--demands`, `--demand-times 0.76` |
| The valley-share table | 4.5 | [RAN] 0.02 with 20 settlements, identical; [READ] the other five, every cell |
| "A different share would have let me report that every condition passes" | 4.5 | [RAN `m5`] at 0.2, 0.05 and 0.02 all the design's Earth conditions pass as built |
| The radiation table, its three parts, 0.61 and 0.76, 1,003 / 1,246 / 194 / 1,052 | 7.14 | [RAN] `earth_demand.py`, identical |
| The land's budget: 145.1, 39.6, 79.6, 38.5, 27; globe 161.2 and 63; 2000 to 2004 | 7.14, 10 | [OPENED] Trenberth, Fasullo and Kiehl 2009, Table 2b |
| 114, 74, 40 | 4.3, 10 | [OPENED] Trenberth, Fasullo and Mackaro 2011 |
| 21 flows and 21 basins; the Amazon's 6,642 km³ and 5,854 thousand km² | 4.4, 10 | [OPENED] Dai and Trenberth, Table 2: all 42 agree |
| Kalugin: 1,360,000 km², 585 mm, 262 km³, 0.38, 30 %, 53 %, the quoted phrase | 4.4, 10 | [OPENED] word for word |
| The Caspian: 237 km³, 80 %, 3 million, "about 436000 km2"; 371,000 km² and −28 m | 4.4, 10 | [OPENED] the paper and Wikipedia |
| 790 mm over land | 8 | [OPENED] Schneider et al. 2017: "790 mm for the global land surface" |
| The constants of the demand | 7.14, `models.yaml` | [OPENED] Davis et al. 2017 |
| The arithmetic: 1.31, 1.17, 0.76, 0.794, 0.79, 193, 222, 0.33, 1.77 / 1.54 / 1.17 / 1.01, 296, 2.4 to 3.1, 210,000 m³/s | throughout | mine |
| The Volga: 1.25 million km²; 744 / 342 / 402; 585 / 224 / 361; 43 %; 319 of 342 in April | 4.4, 8 | [RAN `m1`] |
| The lake: 588 = 0.47 + 1,042 − 455; 936 and 408 mm; 4.06 with the lake; Voronezh in it | 4.4 | [RAN `m2`, `m1`] |
| The ways of the Nile, Yangtze, Lena, Danube, Congo, Amur, St Lawrence, Ob, Huang He (48 and 4), Mekong (7 of 21), Volga | 4.4, reasons | [RAN] eleven traces |
| "By another way" (Congo), "by a way south" (Amur), south of the gorges (Yangtze), in the data | 4.4 | [RAN `m4`] the data's outlets lie west, south and south-east |
| "Pass" and "fails" | 4.2, 4.3 | [RAN] `tests/test_earth.py --runxfail`: 58 pass, 33 fail with the reasons' numbers; six tests of the first five conditions pass |
| The twin's table and the text under it | 4.6 | [READ] both logs, every row |
| Section 8's table | 8 | [READ] both reports; [RAN] the two rows of R14 |
| Climate groups 21.1 / 24.7 / 13.3 / 26.2 / 14.7; open water 1,003 mm; twelve lakes hold 54 % | 4.3 | [RAN `m9`, `m14`, `m1`] |
| "Dry land sheds nothing at all" | 8 | [RAN] true of warm dry land (11.9 % of the land): no cell sheds anything. Cold dry land sheds its snow as ice |
| The tenth in every commit | 4.5 | [RAN git] |
| The design's words | 4 head, 4.5 | [READ] "relief converted so that valley floors survive"; "River and closed-basin tests pass" |
| README: 35 MB, 6 minutes, 34 failures and two conditions | README | 34.7 MB; 374 s [READ]; agrees with the notes |

## 5. What I did not check

- **Not run:** the standard profile, 100 settlements, the whole suite, the twin's build. Held against the builder's logs and stores.
- **Not opened:** Verpoorter, the National Snow and Ice Data Center, Peel, Hock, Dutra, Barnes, the FAO paper, the Python documentation. NCAR's GPCP page could not be opened (the reader asked for a permission no one was there to give). Schneider was read from a copy.
- **Seen only through a page reader:** every source. I saw no table as printed.
- **Not decided:** which precipitation is right for the Volga; whether GPCP 2.2 carries the correction that version 2 documents.
- **No data at hand:** whether the mesh's basins cover the real basins' land; radiation, sunshine or daily rain by region.
- **Narrow experiments:** the level-ground one is one other rule and 20 draws. The sea-volume one is share 0.1 and 20 draws. The shares between were run as built at nine values and with 20 settlements at three.
- **Used, not re-derived:** the builder's flood of the raw grid (the fourth check held it against its own).
- **Outside my part:** sections 1 to 3, 4.7, 4.8, 5, 6, 9 and the engine, but for the lines above.

Sources:
- [Kalugin 2022, Climate 10(7), 107](https://www.mdpi.com/2225-1154/10/7/107)
- [Trenberth, Fasullo and Kiehl 2009](https://staff.cgd.ucar.edu/trenbert/trenberth.papers/TFK_bams09.pdf)
- [Trenberth, Fasullo and Mackaro 2011](https://staff.cgd.ucar.edu/trenbert/trenberth.papers/2011jcli24.pdf)
- [Dai and Trenberth, Table 2](https://ams.confex.com/ams/pdfpapers/55037.pdf)
- [Caspian Sea level paper, IJCOE](https://www.ijcoe.org/article_149296_f5ae89f43cbcf8f98aa838f382fb2416.pdf)
- [Wikipedia, Caspian Sea](https://en.wikipedia.org/wiki/Caspian_Sea)
- [Davis et al. 2017](https://gmd.copernicus.org/articles/10/689/2017/gmd-10-689-2017.pdf)
- [Schneider et al. 2017, copy](https://pdfs.semanticscholar.org/e92b/ffdbf3981e4bed9adc5b05f5f97e5e6d60f7.pdf)
- [GPCP Version 2 documentation](https://iridl.ldeo.columbia.edu/SOURCES/.NASA/.GPCP/.V2/.dataset_documentation.html)
