# Design-document update after build step 2 (texts to apply; N_TESTS, N_XFAIL, SUITE_MIN, FIFTH to fill)

## results table: new rows (two cells each)

Step 2: the design's five conditions on ground built for the purpose (a cone, every cell reaches the sea or a hollow, areas add up, one basin under even rain, water in equals water out)
-> All met

Step 2: the design's four patterns of Earth
-> Three are met as built: the Amazon reaches the Atlantic and the Nile the Mediterranean, central Asia and the Great Basin are closed, and the Amazon carries the most water. One fails as built: the lake at the Caspian's place overflows, by 0.47 of the 669 km³ that reach it in a year. The paragraph on Earth's rivers says what these four results can bear

Step 2: tests on Earth beyond the design
-> As built, 16 of 24 great rivers leave the land within 300 km of their real mouths, and 7 of 21 carry the measured flow within a factor of two at their gauges. Like for like, the land of fourteen great basins sheds 0.68 of the measured depth. Lakes cover 6.0 % of the land, against 3.7 % on Earth. Each miss is a test marked as an expected failure

Step 2: run times
-> Preview profile 27 s. Standard profile 599 s, with 5.3 GB of memory at its peak. The suite holds N_TESTS tests, N_XFAIL of them expected failures, and runs in SUITE_MIN minutes

## paragraph after the crust paragraph

**Earth's rivers, and what the tests on Earth can bear.** Step 2 found four public data files: Earth's relief, rain, temperature and a land mask. Four processes are now tested on them, and the whole engine runs on Earth's relief as a twin. Two later checks overturned what I had concluded from the rivers. The relief file comes in whole metres and holds closed valleys of its own, and a third of the land cells tie exactly with a neighbour. So where a river runs on it is decided mostly by the data, by my rule for putting them on the mesh, and by how exact ties are settled, not by Drainage. With the ties settled at random 100 times, 14 of the 24 mouths pass every time, 6 never, and 4 turn on the ties; the lake at the Caspian's place stays closed in 55. It is two and a half to three times the real sea's size however the ties fall. What the data do measure is the water of the land: the engine's land gives the air 1.17 times the published amount, and like for like it sheds 0.68 of the measured runoff. Why is not established. I had named a cause as measured, and the fourth check showed that it was not. [MEASURED; docs/BUILD_NOTES.md, sections 4.3 to 4.5, has every number and what each can bear]

## departures: row 6, why

They were set before any Earth data was at hand. Relief, rain and temperature were found in step 2; the constants are due again on the Earth twin, not by hand

## departures: new rows 10 to 22 (No. | This design said | What was built | Why)

10 | Drainage fills every hollow to its brim (Priority-Flood) | Hollows are found as a hierarchy and written as a table: each hollow, its bottom, its pass and the hollow it spills into. [DOCUMENTED: Barnes, Callaghan and Wickert 2020] | Lakes need what filling erases
11 | The declarations of Drainage and Hydrology in Layer 4 | Drainage also reads sea_depth and the table of seas. Hydrology reads height_above_sea and the table of hollows, and does not read albedo, spill_elevation or vegetation_cover | The albedo field is the planet's as seen from above the clouds, and plant cover does not exist yet
12 | Soils arrives in step 7 | A Soils slot exists now, as a stand-in: every soil holds 150 mm of water | Hydrology reads the field as it will read the real one, so step 7 replaces one file
13 | The snow store has a limit on its depth | Where more snow falls in a year than the year can melt, the store holds one year's net snowfall, and what is older leaves as ice and counts as runoff. A new field, snow_cover, stands outside the list of 74. [INFERRED: mine] | With a depth limit the store jumped when a cell tipped from losing its snow to keeping it, and each such cell cost the climate two or three rounds
14 | The bucket takes ten sub-steps a month | A month of the bucket is solved exactly | No error of the step
15 | The demand for water uses the energy the engine computes | The Priestley-Taylor rule on two radiation formulas, with one share of sunshine for every cell and month, applied to the whole day. [DOCUMENTED for the formulas: Davis et al. 2017; applying them to the whole day is mine] | The engine's energy balance is a budget at the top of the air. Over Earth's land the formulas leave 1.31 times the energy of a published budget; why the land then sheds too little water is not established
16 | Lakes fill by volume (Fill-Spill-Merge) | A lake has stopped growing when a year's inflow equals a year's loss from its surface; the order of filling, spilling and merging is the published one. [INFERRED: the change is mine] | A climate that repeats has no filling
17 | Settle tolerances belong to fields | A group may carry one too; moisture_source does | The water that land gives back must settle with the rain it feeds
18 | The dry-belt condition is met | It is an expected failure in the north of the default world: the driest band lies at 58°, where the land is high, cold and white all year | The condition stands as the design wrote it, and the engine fails it
19 | The Earth twin is a parameter file of the engine | The Earth data and the twin live beside the engine, and the twin is built without Tectonics | A world on measured relief has no plates to explain
20 | One sentence pattern for each field | A pattern has cases | One sentence could not be true of land, lake and sea alike
21 | Each cell drains to its lowest neighbour | Where neighbours are exactly equally low, the lower bed decides, then the wider way (the longer boundary between the two cells), then the order of the cells. [INFERRED: mine] | The rule says nothing of ties. They are common on coasts and on relief given in whole metres, and there they decide where rivers go
22 | potential_evapotranspiration as the paper defines it | The demand over the whole day, on the ground that is free of snow | See row 15

## Where the world is wrong now (list, replaces the five items)

- **The seasons on land are too weak, and too much land is white all year.** On Earth's relief the engine's land between 40° and 60° north is 13.6 K warmer in July than in January, against 30.9 K on Earth, and 20 % of the default world's land keeps its snow all year, against 10 % of Earth's land under ice. [DOCUMENTED for Earth's ice: National Snow and Ice Data Center] I read the cause as the single spreading constant of the energy balance model, which ties land to the sea too tightly. [INFERRED: no mend has been tried] Later models of this family let the spreading vary. [DOCUMENTED: Ziegler and Rehfeld 2021] It is the largest known error, and I propose to mend it first.
- **The land gives the air too much water and the rivers too little.** Under Earth's own rain and warmth the land gives the air 1.17 times the published amount, and 31.7 thousand km³ a year reach the sea where Earth's rivers carry 40. [DOCUMENTED for Earth: Trenberth, Fasullo and Mackaro 2011] The cause is not established.
- **Half the land drains into closed hollows, and a twelfth of it lies under lakes.** The seeded relief has had no rivers to cut it. Step 3 cuts valleys on the mesh itself.
- **The land is still drier than Earth's.** It gets 618 mm of rain a year, against 790 mm on Earth [DOCUMENTED: Schneider et al. 2017]; before step 2 it got 306 mm. Nothing makes a monsoon yet (step 5).
- **The rain of rising ground falls in one cell.** The amount per kilometre of cliff is the same on every mesh, so the amount per cell grows as cells shrink: 13 m a year in the wettest cell of the standard world. Spreading it inland belongs to step 5.
- **The planet is close to a deep ice age.** With 2 % less sunlight it is 4.8 °C colder and stays open. With 5 % less it freezes, and the world store says so.
- **Land covers 36 % of the surface and ends in cliffs**, because the snapshot of plates has no shelves, and a quarter to a half of the ocean floor sits at the age cap of 180 My. Step 3 replaces the snapshot.

## Sources added with step 2 (Source | Used for | How I checked it)

Barnes, Callaghan, Wickert 2020, Finding hierarchies in depressions (https://esurf.copernicus.org/articles/8/431/2020/) | How Drainage finds the hollows, their passes and how they nest | Opened
Davis et al. 2017, the SPLASH model (https://gmd.copernicus.org/articles/10/689/2017/gmd-10-689-2017.pdf) | The Priestley-Taylor rule, the two radiation formulas and every constant of the demand for water | Opened; five of its equations read out again by a page reader
The SPLASH code, geco-bern/rsofun (https://github.com/geco-bern/rsofun) and dsval/rsplash | One constant that the paper's text layer garbles | Opened: fetched from GitHub and read
FAO Irrigation and Drainage Paper 56, Chapter 3 and Annex 3 (https://www.fao.org/4/x0490e/x0490e07.htm) | The heat of vaporisation at 20 °C, as a test of that constant | Opened
Trenberth, Fasullo, Kiehl 2009, Earth's Global Energy Budget (https://staff.cgd.ucar.edu/trenbert/trenberth.papers/TFK_bams09.pdf) | The energy budget of Earth's land, sea and whole surface | Opened; the row for land read out again by a page reader
Trenberth, Fasullo, Mackaro 2011, Atmospheric Moisture Transports from Ocean to Land (https://staff.cgd.ucar.edu/trenbert/trenberth.papers/2011jcli24.pdf) | Rain on land, evaporation from land and river flow to the sea | Opened
Dai and Trenberth, New Estimates of Continental Discharge (https://ams.confex.com/ams/pdfpapers/55037.pdf) | The flow and the basin of 21 great rivers at their last gauging stations | Read out by a page reader, row by row; I have not seen the table as printed
Verpoorter et al. 2014, A global inventory of lakes (https://agupubs.onlinelibrary.wiley.com/doi/10.1002/2014GL060641) | Lakes cover 3.7 % of Earth's ice-free land | Not opened; read at second hand, on a page that reports it
NCAR GeoCAT-datafiles (https://github.com/NCAR/GeoCAT-datafiles) | The four data files of the Earth tests: relief, rain, temperature, a land mask | Opened: fetched, and the files' own attributes read
Investigation of Caspian Sea Level Fluctuations (https://www.ijcoe.org/article_149296_f5ae89f43cbcf8f98aa838f382fb2416.pdf) | The Caspian's inflow and catchment | Read out by a page reader
Wikipedia, Caspian Sea (https://en.wikipedia.org/wiki/Caspian_Sea) | The Caspian's area and level | Read out by a page reader; it disagrees with the paper above on the area
Kalugin 2022, Hydrological and Meteorological Variability in the Volga River Basin (https://www.mdpi.com/2225-1154/10/7/107) | The Volga's basin, precipitation and runoff | Read out by a page reader, three times; its two figures for the runoff disagree
The Python documentation, sys.stdout (https://docs.python.org/3/library/sys.html) | Why printed text could end a run on Windows | Opened, as its source file on GitHub
