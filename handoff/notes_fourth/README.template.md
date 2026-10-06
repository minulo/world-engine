# World engine

A generator for a planet's geography, natural systems and climate, in which every feature follows
from a stated physical cause. The design is in the design document "World engine design: physical
causes, replaceable processes"; this folder is its build. What was measured, what the rounds of
checking changed, where the build departs from the design and where its worlds are wrong are in
[docs/BUILD_NOTES.md](docs/BUILD_NOTES.md). Read its sections 4, 6 and 8 before trusting a map.

Built so far: the skeleton (build step 0), the smallest end-to-end slice (step 1: terrain,
temperature, wind, rainfall and biomes, with a viewer) and the water on land (step 2: drainage,
snow, soil water, rivers, lakes, and the water that land gives back to the air). Erosion, moving
plates, ocean currents, soils, storms and daily weather are designed and not built.

## Install

The lock file pins the versions the engine was built and tested with, on Python 3.13.

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock        # Windows: .venv\Scripts\python
    .venv/bin/python -m pip install -e .

The commands below assume the environment is active (`source .venv/bin/activate`, or
`.venv\Scripts\activate` on Windows). Nothing else is needed: the viewer is a plain web page with
no third-party code. With another Python version the lock file may not install; `pip install -e
".[test]"` then takes current versions, and a world may differ in its last digits from one built
with the pinned ones.

Nothing was run on Windows. Paths, text encodings and line endings are written for it and tested
as far as Linux can show (docs/BUILD_NOTES.md, sections 5.3 and 6); the first install there is a
test of its own.

## Use

    python -m worldengine order                                  # the running order computed from the declarations
    python -m worldengine build --profile preview  --out worlds/first.zarr     # 10,242 cells; half a minute where it was built
    python -m worldengine build --profile standard --out worlds/big.zarr       # 163,842 cells; 10 to 20 minutes where it was built
    python -m worldengine serve worlds/first.zarr                 # then open http://127.0.0.1:8765/
    python -m worldengine explain worlds/first.zarr --lat 18 --lon -102 --field biome
    python -m worldengine info worlds/first.zarr

    python -m worldengine build --profile preview --seed 7 --out worlds/other.zarr
    python -m worldengine build --profile preview --interventions data/examples/frozen_region.yaml --out worlds/frozen.zarr
    python -m worldengine build --profile preview --interventions data/examples/place_label.yaml --out worlds/forest.zarr

The archive that was handed over comes with `worlds/first.zarr`, the default world on the preview
mesh, so `serve` works at once. A clone of the repository does not hold it (`worlds/` is not under
version control): the second command above builds it. The times are from a two-core machine whose
speed changes from day to day by a factor of two (docs/BUILD_NOTES.md, section 4.7); nothing was
timed on a laptop.

The same seed and parameters always give the same world, bit for bit, on one machine with the pinned
versions. On a machine with another kind of processor the last digits can differ (docs/BUILD_NOTES.md,
section 5.3); a world store carries its fingerprints, so a difference shows. A world store is written
once and never changed.

In the viewer: choose a field, drag to turn the globe, scroll to zoom, switch to the flat map, play
the months, and click a cell for its values and its "why" answer.

### A "why" answer

Every process records the terms that made its result, and `explain` walks back through them to a
planet parameter, a seeded start or a push. For the mouth of the largest river of the default world
(shortened):

    python -m worldengine explain worlds/first.zarr --lat 27.1 --lon -166.1 --field river_discharge

    Why is river_discharge like this at 27.1° N, 166.1° W (cell 7516)?
    1. This cell is sea. The rivers that end here deliver 100694 m³/s on the year's average: 100694 m³/s
       arrive from upstream, where the largest single source is cell 456, at 23.3° N, 166.1° E.
    2. At 23.3° N, 166.1° E (cell 456), where the cause lies: Runoff here averages 125.9 mm/month: ice
       leaving ground where snow never melts away gives 88.9 mm/month; rain that the soil could not hold
       gives 33.4 mm/month; melted snow that the soil could not hold gives 3.71 mm/month.
    3. [...] The snow on the ground here holds 1085 mm of water on the year's average, and lies all
       year: more snow falls in a year than the year can melt. [...]
    5. [...] Precipitation here averages 125.9 mm/month: moist air rains 92.1 mm/month; air forced up
       rising ground adds 70.4 mm/month; sinking air changes it by -36.5 mm/month.
    ...
    11. [...] The temperature here averages -2.5 °C over the year: sunlight absorbed against heat lost
        to space would give -27.3 °C; heat spread from neighbouring cells changes it by +48.5 °C; its
        height changes it by -23.7 °C.
    12. [...] Sunlight at the top of the air averages 384.9 W/m² over the year here.
    13. [...] The chain ends here, at planet parameters: the latitude of 23.3° north, the axial tilt of
        23.44 degrees and the star output of 1361.0 W/m².

The answer is true of the world and shows one of its known errors at work: snow that never melts on a
mountain at 23° north (docs/BUILD_NOTES.md, section 8).

## Earth, as a yardstick

Four public data files let single processes be judged against Earth, and let the whole engine be run
on Earth's own relief (docs/BUILD_NOTES.md, sections 4.3 to 4.6). They are not kept in this folder.

    python tools/fetch_reference_data.py           # fetches 35 MB from one pinned commit and checks every file
    python tools/earth_relief.py                   # what the relief data hold before any process runs: closed valleys, exact ties
    python tools/earth_rivers.py --settlements 20  # Earth's great rivers and lakes as the engine makes them, beside the measured
                                                   # ones, and how often each outcome comes when the exact ties of the relief
                                                   # are settled at random; --settlements 100 --demands prints the numbers of
                                                   # section 4.4 of the notes, in about ⟦S100_MIN⟧ minutes where it was built
    python tools/earth_rivers.py --trace Danube    # one river's way over the mesh, cell by cell
    python tools/earth_demand.py                   # the air's demand for water over land, beside a published budget of the land
    python tools/earth_twin.py --profile preview   # the whole engine on Earth's relief, printed beside Earth

Read section 4.4 of the notes before any single river. The relief file comes in whole metres and
holds closed valleys of its own, so where a river runs on it is decided mostly by the data, by the
rule that puts them on the mesh and by how exact ties are settled, not by the engine. What the
yardstick does measure: the water of all the land, and what the land of a great basin sheds, like
for like. There the engine's land sheds 0.68 of the measured depth, and why is not established.

Without the data the tests that need it are skipped. The precipitation file asks that GPCP be cited
in anything published from it (`tools/reference_data.yaml`).

## Tests

    python -m pytest                    # ⟦N_TESTS⟧ tests, about ⟦SUITE_MIN⟧ minutes where it was built

⟦N_XFAIL⟧ of them are expected failures: patterns of Earth, and two conditions of the design (the dry
belt of the north and the closed Caspian), that the engine is known to miss, each with the number
measured. `python -m pytest -rx` prints them. They are not the whole list of known errors: the
notes' sections 4.4, 4.6 and 8 name misses that no test states. Without the Earth data the
⟦N_SKIP⟧ tests that need it are skipped.

Extra checks that are not part of the test run:

    python trials/crust_points_trial.py            # the trial of crust carried on moving points (docs/BUILD_NOTES.md, 3.2)
    python trials/crust_points_trial.py seeds      # the same on ten other seeds
    python trials/climate_round_cost.py standard   # what a climate round costs on this machine
    python tools/world_report.py worlds/first.zarr # the numbers by which a world is judged
    python tools/why_scan.py worlds/first.zarr     # reads the "why" answers of every cell against the numbers of the cell
    python tools/viewer_check.py worlds/first.zarr shots biome river_discharge   # screenshots and checks in a headless browser

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
                          soil water, the demand for water, lakes
      processes/          one file per implementation of a slot; each file's first lines name the model,
                          what it ignores and where it is wrong
    src/earth_reference/  readers of the Earth data, Earth on the mesh, the Earth twin. Not part of the engine:
                          the engine never imports it
    viewer/               the viewer page
    tests/                the test suite; toy processes and the design's declarations as test data
    trials/               the two trials of build step 1 and their results
    tools/                development tools
    docs/BUILD_NOTES.md   the state of the build

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
