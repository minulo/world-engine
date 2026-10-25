# World engine

A generator for a planet's geography, natural systems and climate, in which every feature follows
from a stated physical cause. The design is in the design document "World engine design: physical
causes, replaceable processes"; this folder is its build. What was measured, what the rounds of
checking changed, where the build departs from the design and where its worlds are wrong are in
[docs/BUILD_NOTES.md](docs/BUILD_NOTES.md). Read its sections 4, 6 and 8 before trusting a map.

Built so far: the skeleton (build step 0), the smallest end-to-end slice (step 1: terrain,
temperature, wind, rainfall and biomes, with a viewer), the water on land (step 2), deep time (step 3:
250 My of moving plates, rivers that cut the land as it rises, the rock at the surface and the age of
each surface, and a film of the history), the wind-driven ocean and its heat (step 4), wind that carries
heat and a rising branch that follows warm land (step 5), sea ice, lasting ice and frozen ground (step 6),
soils and the BIOME1 biomes (step 7), storm maps, single storms and the weather of any day, with a clock
that steps through dates (step 8), the climate rerun inside the history (step 9), a first comparison with
a full circulation model (step 10) and finer detail over a region (step 11). What steps 4 to 11 measured,
what they did not do and where the worlds are wrong is in docs/BUILD_NOTES.md, sections 13 to 21. Read
section 13 first: the northern continents of the Earth twin are still far too cold in summer, and the
standard build takes longer than its profile allows.

## Run it on your computer

One command installs the engine into a folder of its own (`.venv`, inside the repository), builds the
default world once into `worlds/first.zarr` and opens it in the browser. Run it again later and it skips
what is done: the viewer opens at once. Ctrl+C stops the server.

You need Python 3.13, a 64-bit system and an internet connection for the first run. Install Python first:

| System | Install Python 3.13 | Then, in the repository folder |
|---|---|---|
| macOS on Apple silicon | `brew install python@3.13`, or the installer from python.org | `scripts/run.sh` |
| Ubuntu 25.04 and 25.10 | `sudo apt install python3.13 python3.13-venv` | `scripts/run.sh` |
| Ubuntu 22.04, 24.04 and 26.04 | `sudo add-apt-repository ppa:deadsnakes/ppa`, `sudo apt update`, then the line above | `scripts/run.sh` |
| Windows 10 and 11 | `winget install Python.Python.3.13`, or the 64-bit installer from python.org; then open a new terminal | `scripts\run.cmd`, or double-click `run.cmd` in the `scripts` folder |
| macOS on an Intel processor | not possible: see below | Docker, below |

Python 3.13 is in the official archive of Ubuntu 25.04 and 25.10 only; 24.04 has 3.12 and 26.04 has 3.14, and
the deadsnakes archive provides 3.13 for 22.04, 24.04 and 26.04 [DOCUMENTED: Launchpad, the publishing history of
python3.13 and the deadsnakes archive, read on 2026-10-25]. If the launcher finds no 3.13 it takes a 3.12 or 3.14
and says so. The pinned packages have wheels for both [DOCUMENTED: PyPI's file lists], and on 3.12.3 they installed
and the viewer served here [MEASURED], but the tests were not run on either, and a world may differ in its last digits.

The launcher takes these options (in PowerShell and `run.cmd`, the same with a single dash and capitals:
`-World`, `-Profile`, `-Seed`, `-Port`, `-Host`, `-Python`, `-NoBrowser`, `-Check`):

    scripts/run.sh --world worlds/other.zarr --profile preview --seed 7   # another world, built if it is not there
    scripts/run.sh --port 9000 --host 127.0.0.1                           # where the server listens
    scripts/run.sh --python /opt/homebrew/bin/python3.13                  # a Python of your choice
    scripts/run.sh --no-browser                                           # serve, without opening a browser
    scripts/run.sh --check                                                # install, build, serve, fetch the page and
                                                                          # /api/world from the server, stop

What it needs and how long it takes, measured on a 4-core Linux cloud machine with 15 GB of memory (Ubuntu 24.04,
Python 3.13.16) on 2026-10-25 [MEASURED]:

| | |
|---|---|
| The first run of `scripts/run.sh --check`: environment, packages, preview world, check | 98 s, with pip's cache already holding the packages (the download was not timed) |
| The preview build within it, and two more builds on their own | 66.6 s, 63.8 s and 62.3 s, the same world each time |
| The largest memory of one process during a preview build | 0.59 GB |
| A second run, which skips the installation and the build | 1.8 s |
| The download of the pinned packages (from PyPI's file sizes) | 120 MB on Linux, 98 MB on Windows, 88 MB on a Mac |
| `.venv` on disk | 452 MB in 7,693 files |
| `worlds/first.zarr` on disk | 37 MB (26 MB of data in 1,681 files) |

The other times in this README come from two-core machines. Plan for about 1 GB of disk and 1 GB of free memory
for the preview world; the standard world needs 6.7 GB of memory at its peak (under "Use", below). Nothing was
measured on a Mac or on Windows by hand. The workflow `.github/workflows/local-run.yml` runs the launcher there,
twice, then the tests (all but `tests/test_world.py`), then the server in the background; on its first run, on
2026-10-25, every step passed on ubuntu-latest, macos-latest (Apple silicon) and windows-latest (through Windows
PowerShell 5.1 and PowerShell 7), the launcher refused on macos-15-intel as it should, and the Docker job passed
[MEASURED: GitHub Actions run 40146705857, commit 7a3bdee]. The preview build took 124 s there on Ubuntu, 94 s on
macOS, 76 s on Windows and 114 s in Docker.

**Intel Macs.** The pinned numba 0.68.0 and llvmlite 0.50.0 publish no wheels for Intel Macs; numba stopped making
them with 0.63.0, in December 2025 [DOCUMENTED: PyPI's file lists, read on 2026-10-25]. pip would try to compile
llvmlite from source, which needs LLVM, and fail. The launcher stops and says so; use Docker instead.

**Windows.** Keep the repository out of a folder that OneDrive keeps in step (Documents and Desktop are, in many
Windows 11 setups): it would copy the 7,700 files of `.venv` and the 1,700 of each world, and may hold them open
while a world is written [INFERRED]. Keep the path of the repository folder under about 120 characters: the longest
path in `.venv` is 105 characters past `.venv\Lib\site-packages\`, and Windows refuses paths of more than 260 unless
long paths are switched on [MEASURED on Linux; the Windows limit DOCUMENTED by Microsoft, "Maximum Path Length
Limitation"]. `run.cmd` starts `run.ps1` with the execution policy set aside for that script alone.

**Worlds from another system.** The same seed and parameters give the same world, bit for bit, on one machine. On
the build machine the world built in Docker (Debian 13, Python 3.13.17) had the same fingerprint as the one built in
`.venv` on Ubuntu 24.04 (Python 3.13.16) [MEASURED]. Between machines it is not so. On the workflow's first run, of
the 138 fields of the preview world, the one built in Docker differed from the one built on the Ubuntu runner in 60,
the one built on Windows in 88 and the one built on macOS in 96, among them the mesh's own cell areas [MEASURED: run
40146705857, the job "The worlds of the systems, side by side"]. The numba loops are compiled for the processor they
run on, and numpy chooses its routines by processor too, so two machines may round differently [INFERRED]. How far
the worlds differ, in the last digits or in their continents, was not measured: the job compares fingerprints only.
The numbers this README and the notes quote are those of the build machine. A world built on one system opens on any other: nothing refuses a world for its fingerprints.
The viewer shows a warning when the engine's code or the lock file differ from those that built it.

### Run it in Docker

The same commands work on Linux, on macOS (Apple silicon and Intel) and on Windows, with Docker Desktop or Docker
Engine. They were run here on Linux only [MEASURED], and the workflow runs them on ubuntu-latest. On Apple silicon
the image is built for arm64, from other wheels, so its worlds may differ in their last digits from those of an
Intel or AMD processor [INFERRED].

    docker build -t worldengine .
    docker run --rm -p 127.0.0.1:8765:8765 -v worldengine-worlds:/app/worlds worldengine
    docker compose up                       # the same, from compose.yaml

Then open http://localhost:8765/. The first start builds the preview world into the volume `worldengine-worlds`
(74 to 76 s on the machine above [MEASURED]), and later starts serve it at once. `docker stop` and
`docker compose down` stop it within a second [MEASURED: 0.3 and 0.7 s]; so should Ctrl+C, which the server
handles [INFERRED; not tried in Docker]. Inside the container the server listens on every address
(`serve --host 0.0.0.0`); `-p 127.0.0.1:8765:8765` keeps it to this machine, as the engine's own server is by
default. `-e WORLDENGINE_PROFILE=standard` builds the standard world instead, which needs Docker Desktop to have
8 GB of memory or more [INFERRED from its peak of 6.7 GB]. The image is 782 MB [MEASURED]. Whether Docker Desktop still runs on every Intel Mac was not
checked [UNVERIFIED].

## Install by hand

The launcher above does this. The lock file pins the versions the engine was built and tested with, on Python 3.13;
they install on 3.12 to 3.14 and not on 3.11 (numpy 2.5.3 needs 3.12).

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock        # Windows: .venv\Scripts\python
    .venv/bin/python -m pip install -e .

The commands below assume the environment is active (`source .venv/bin/activate`, or
`.venv\Scripts\activate` on Windows). Nothing else is needed: the viewer is a plain web page with
no third-party code. With another Python version the lock file may not install; `pip install -e
".[test]"` then takes current versions, and a world may differ in its last digits from one built
with the pinned ones.

Nothing was run on Windows by hand. Paths, text encodings and line endings are written for it and tested
as far as Linux can show (docs/BUILD_NOTES.md, sections 5.3 and 6); the workflow above is the first test there.

## Use

    python -m worldengine order                                  # the running order computed from the declarations
    python -m worldengine build --profile preview  --out worlds/first.zarr     # 10,242 cells; about two minutes where it was built
    python -m worldengine build --profile standard --out worlds/big.zarr       # 163,842 cells; 40 to 80 minutes where it was built
    python -m worldengine serve worlds/first.zarr                 # then open http://127.0.0.1:8765/ (--open opens it)
    python -m worldengine explain worlds/first.zarr --lat 18 --lon -102 --field biome
    python -m worldengine info worlds/first.zarr
    python -m worldengine weather worlds/first.zarr --day 180 --days 7 --lat 50 --lon 10   # a place's days, worked out on request
    python -m worldengine detail worlds/first.zarr --lat 45 --lon 10 --radius-km 500      # finer cells over one region

    python -m worldengine build --profile preview --history-my 500 --continue-from worlds/first.zarr --out worlds/later.zarr
                                                                  # the same history, run on from 250 to 500 My
    python -m worldengine build --profile preview --seed 7 --out worlds/other.zarr
    python -m worldengine build --profile preview --interventions data/examples/frozen_region.yaml --out worlds/frozen.zarr
    python -m worldengine build --profile preview --interventions data/examples/place_label.yaml --out worlds/forest.zarr

The archive that was handed over comes with `worlds/first.zarr`, the default world on the preview
mesh, so `serve` works at once. A clone of the repository does not hold it (`worlds/` is not under
version control): the second command above builds it. The times are from two-core cloud machines whose
speed changes within a day by a factor of two (docs/BUILD_NOTES.md, section 4.7); nothing was
timed on a laptop. The standard build holds 6.7 GB of memory at its peak.

The same seed and parameters always give the same world, bit for bit, on one machine with the pinned
versions. With numpy's AVX-512 code switched off the last digits differ, so on another kind of
processor they probably do too; that was not tried (docs/BUILD_NOTES.md, section 6, item 11). A world
store carries its fingerprints, so a difference shows. A world store is written
once and never changed.

In the viewer: choose a field, drag to turn the globe, scroll to zoom, switch to the flat map, play
the months, and click a cell for its values and its "why" answer. For elevation, ocean_mask, plate_id
and crust_type a second slider plays the geological history as a film, one picture every 10 My. The fields
of a day (weather temperature, rain, pressure, wind and storm influence) are in the list under "Storms and weather
(one day)": a day slider and a play button step through the days, which the server works out on request.

### A "why" answer

Every process records the terms that made its result, and `explain` walks back through them to a
planet parameter, a seeded start or a push. For the mouth of one of the large rivers of the default world,
which carries the snow of a northern plain to the sea (shortened):

    python -m worldengine explain worlds/first.zarr --lat 69.3 --lon 66.6 --field river_discharge

    Why is river_discharge like this at 69.3° N, 66.6° E (cell 7146)?
    1. This cell is sea. The rivers that end here deliver 37335 m³/s on the year's average: 37335 m³/s
       arrive from upstream, where the largest single source is cell 1815, at 54.2° N, 52.0° E.
    2. At 54.2° N, 52.0° E (cell 1815), where the cause lies: Runoff here averages 50.2 mm/month: melted
       snow that the soil could not hold gives 35.9 mm/month; rain that the soil could not hold gives
       14.3 mm/month.
    3. [...] The snow on the ground here holds 94.7 mm of water on the year's average. It builds up in
       the cold months and is gone by the end of the warm ones: of the 38.3 mm/month that fall as snow
       on the year's average, all melt. [...]
    5. [...] Precipitation here averages 67.2 mm/month: moist air rains 65.6 mm/month; air forced up
       rising ground adds 1.62 mm/month.
    ...
    11. [...] The temperature here averages -4.0 °C over the year: sunlight absorbed against heat lost
        to space would give -40.7 °C; heat spread from neighbouring cells changes it by +33.0 °C; heat
        the wind carries in changes it by +8.8 °C; its height changes it by -5.2 °C.
    12. [...] Sunlight at the top of the air averages 264.2 W/m² over the year here.
    13. [...] The chain ends here, at planet parameters: the latitude of 54.2° north, the axial tilt of
        23.44 degrees and the star output of 1361.0 W/m².
    14. [...] Over the year, 0.56 of the sunlight is reflected here: cloud and the low sun reflect 0.31;
        the surface type reflects 0.15; snow and ice add 0.0954.

Most of what this river carries is snow that melts in the warm months (35.9 of 50.2 mm/month at its largest
source), and the warmth that melts it is mostly brought: sunlight alone would hold the ground at -40.7 °C over
the year, and heat spread from neighbouring cells and carried by the wind adds 41.8 K. Until 2026-10-25 the mouth of the
largest river was fed by snow that never melted at 51° north (docs/BUILD_NOTES.md, sections 13 and 22).

## Earth, as a yardstick

Four public data files let single processes be judged against Earth, and let the whole engine be run
on Earth's own relief (docs/BUILD_NOTES.md, sections 4.3 to 4.6). They are not kept in this folder.

    python tools/fetch_reference_data.py           # fetches 35 MB from one pinned commit and checks every file
    python tools/earth_relief.py                   # what the relief data hold before any process runs: closed valleys, exact ties
    python tools/earth_rivers.py --settlements 20  # Earth's great rivers and lakes as the engine makes them, beside the measured
                                                   # ones, and how often each outcome comes when the exact ties of the relief
                                                   # are settled at random; --settlements 100 --demands prints the numbers of
                                                   # section 4.4 of the notes, in about 4 to 6 minutes where it was built
    python tools/earth_rivers.py --trace Danube    # one river's way over the mesh, cell by cell
    python tools/earth_demand.py                   # the air's demand for water over land, beside a published budget of the land
    python tools/earth_twin.py --profile preview   # the whole engine on Earth's relief, printed beside Earth

Read section 4.4 of the notes before any single river. The relief file comes in whole metres and
holds closed valleys of its own, so where a river runs on it is decided mostly by the data, by the
rule that puts them on the mesh, by how exact ties are settled and by the volume of water poured,
not by the engine. The tools pour what the ocean of the relief data holds, as the design asks;
`--sea-water planet` pours the planet file's volume, 0.19 % less, and moves several outcomes
(section 4.5). What the yardstick does measure: the water of all the land, and what the land of a
great basin sheds, like for like. There the engine's land sheds 0.69 of the measured depth, and why
is not established. The inputs are data sets, not the truth; the snowfall is not measured at all,
but made from monthly temperatures.

Without the data the tests that need it are skipped. The precipitation file asks that GPCP be cited
in anything published from it (`tools/reference_data.yaml`).

## Tests

    python -m pytest                    # 997 tests; with the Earth data, under an hour where it was built
    python -m pytest --ignore=tests/test_world.py     # all but the whole-world tests, as the workflow runs them

Without the Earth data, the second command ran in 3 min 11 s on the 4-core machine of "Run it on your computer"
(838 passed, 119 skipped), and `tests/test_world.py`, which builds whole worlds, in 13 min 49 s on its own
[MEASURED].

37 of them are expected failures, all in `tests/test_earth.py`: patterns of Earth, and one condition of
the design (the closed Caspian), that the engine is known to miss, each with the number measured.
`python -m pytest -rx` prints them. They are not the whole list of known errors: the notes' sections
4.4, 4.6, 8 and 13 to 22 name misses that no test states. Without the Earth data the 119 tests that
need it are skipped.

Extra checks that are not part of the test run:

    python trials/crust_points_trial.py            # the trial of crust carried on moving points (docs/BUILD_NOTES.md, 3.2)
    python trials/crust_points_trial.py seeds      # the same on ten other seeds
    python trials/climate_round_cost.py standard   # what a climate round costs on this machine
    python trials/long_history_trial.py            # 2,500 My of plates on the preview mesh, measured every 250 My
    python handoff/step3/relief_report.py worlds/first.zarr [older.zarr]   # relief, ocean floor, rivers and lakes
    python tools/world_report.py worlds/first.zarr # the numbers by which a world is judged
    python tools/why_scan.py worlds/first.zarr     # reads the "why" answers of every cell against the numbers of the cell
    python tools/earth_climate_patterns.py         # the patterns of steps 4 and 5 on the Earth twin, beside Earth
    python tools/gcm_compare.py RUN.json           # the engine's aquaplanet against an ExoPlaSim run (build step 10)
    python tools/viewer_check.py worlds/first.zarr shots biome river_discharge   # screenshots and checks in a headless browser
    python tools/refusal_audit.py                  # is every refusal of the engine held by a test? A quarter of an hour
                                                   # where it was built

The two trials print their results. The files in `trials/results/` are the records of build step 1,
and a trial writes over them only when run with `--write`. `tools/viewer_check.py` needs the
package playwright and a Chromium, which the engine and its tests do not:
`pip install -r requirements-viewer-check.lock`. Every tool explains itself with `--help` and
refuses an option it does not know.

## Layout

    data/                 every number: planet, models and their constants, profiles, stages, fields, tables,
                          seeds, pushes, category lists, sentence patterns; schemas/ holds the allowed keys and ranges
    data/models.yaml      for each process: the model it uses, what it ignores, where it is wrong, its constants
    data/examples/        push files that work today: the frozen region, a place label
    src/worldengine/
      mesh.py             the icosahedral mesh
      params.py           parameter files and their schemas
      fields.py           the field dictionary
      scheduler.py        the running order from declarations, and every refusal
      engine.py           clocks, rounds, blending and settling, the push hook, lineage
      process.py          the contract every process keeps
      interventions.py    regions and operations of pushes
      draws.py            random draws keyed by seed, slot, purpose and round
      causes.py           the "why" walk
      store.py            the world store (Zarr)
      server.py, cli.py   the local server and the command line
      console.py          what the command line and the tools share: one way of reading arguments, and text
                          that prints on any system
      testing.py          the harness that runs one process alone
      library/            shared mathematics: mesh operators, flooding, transport, orbit, noise, drainage, snow,
                          soil water, the demand for water, lakes, the ocean's loops, days, the Koppen classes
      detail.py           finer cells over one region of a finished world (build step 11)
      library/plates.py   the seeded start and the reading of plate boundaries that both Tectonics implementations share
      processes/          one file per implementation of a slot; each file's first lines name the model,
                          what it ignores and where it is wrong
    src/earth_reference/  readers of the Earth data, Earth on the mesh, the Earth twin. Not part of the engine:
                          the engine never imports it
    viewer/               the viewer page
    tests/                the test suite; toy processes and the design's declarations as test data
    trials/               the two trials of build step 1 and their results
    tools/                development tools
    scripts/              the launchers (run.sh; run.ps1 and run.cmd for Windows) and what the container runs
    Dockerfile, compose.yaml   the engine in a container
    .github/workflows/    local-run.yml: the launchers, the tests and the server on Linux, macOS and Windows, and Docker
    docs/BUILD_NOTES.md   the state of the build
    HANDOFF.md, handoff/  the working record of the close-out of build step 2: the reports of its fifth check,
                          the logs of the tools that the notes quote, and the scripts that write the notes' tables

## How to add things

* A better model for a slot: one new file in `processes/`, its constants in `data/models.yaml`, and one
  changed line naming it. It may read different fields, but it must write the slot's list.
  docs/BUILD_NOTES.md, section 9, says what a replacement of Drainage or Hydrology must also honour:
  the rules of the table of hollows, and one place where exact ties are settled.
* A new field: one entry in `data/fields.yaml` plus a process that writes it.
* A push (an external change to a field or a group): one entry in `data/interventions.yaml`.
  No code changes. `data/examples/` shows two.
* A new stage on a clock the engine has: one entry in `data/stages.yaml`.
* A test of one process alone: `worldengine.testing.Harness` feeds it inputs built for the purpose.
  It refuses an input the process does not declare, and a constant that does not exist.
