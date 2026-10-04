# World engine

A generator for a planet's geography, natural systems and climate, in which every feature follows
from a stated physical cause. The design is in the design document "World engine design: physical
causes, replaceable processes"; this folder is its build. What was measured, what three rounds of
checking changed, where the build departs from the design and where the first world is wrong are
in [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md). Read its sections 3.2, 5 and 7 before trusting a map.

Built so far: the skeleton (build step 0) and the smallest end-to-end slice (build step 1):
terrain, temperature, wind, rainfall and biomes, with a viewer. Rivers, lakes, erosion, ocean
currents, soils, storms and daily weather are designed and not built.

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

## Use

    python -m worldengine order                                  # the running order computed from the declarations
    python -m worldengine build --profile preview  --out worlds/first.zarr     # 10,242 cells; 23 s where it was built
    python -m worldengine build --profile standard --out worlds/big.zarr       # 163,842 cells; 8 to 9 minutes where it was built
    python -m worldengine serve worlds/first.zarr                 # then open http://127.0.0.1:8765/
    python -m worldengine explain worlds/first.zarr --lat 18 --lon -102 --field biome
    python -m worldengine info worlds/first.zarr

    python -m worldengine build --profile preview --seed 7 --out worlds/other.zarr
    python -m worldengine build --profile preview --interventions data/examples/frozen_region.yaml --out worlds/frozen.zarr
    python -m worldengine build --profile preview --interventions data/examples/place_label.yaml --out worlds/forest.zarr

The folder comes with `worlds/first.zarr`, the default world on the preview mesh, so `serve` works
at once. The times are from a slow two-core machine; a laptop should be several times faster.

The same seed and parameters always give the same world, bit for bit, on one machine with the pinned
versions. A world store is written once and never changed.

In the viewer: choose a field, drag to turn the globe, scroll to zoom, switch to the flat map, play
the months, and click a cell for its values and its "why" answer.

### A "why" answer

Every process records the terms that made its result, and `explain` walks back through them to a
planet parameter, a seeded start or a push. For a desert cell of the default world (shortened):

    Why is biome like this at 18.1° N, 101.8° W (cell 8869)?
    1. The biome here is subtropical desert: Whittaker's chart places this climate here; the yearly mean
       temperature is 14.5 °C; the yearly precipitation is 7.16 mm; what limits plant life here is drought.
    2. Precipitation here averages 0.60 mm/month: moist air rains 0.77 mm/month; sinking air changes it
       by -0.17 mm/month.
    ...
    9. Air here sinks at 1.16 mm/s on average (a negative value means it rises). It lies under the
       sinking branch of the northern loop.
    10. The temperature here averages 14.5 °C over the year: sunlight absorbed against heat lost to space
        would give 36.7 °C; heat spread from neighbouring cells changes it by -17.6 °C; its height
        changes it by -4.6 °C.
    11. Sunlight at the top of the air averages 396.8 W/m² over the year here.
    12. The chain ends here, at planet parameters: the latitude of 18.1° north, the axial tilt of
        23.44 degrees and the star output of 1361.0 W/m².

## Tests

    python -m pytest                    # 362 tests, about five minutes where it was built

Extra checks that are not part of the test run:

    python trials/crust_points_trial.py            # the trial of crust carried on moving points (docs/BUILD_NOTES.md, 3.2)
    python trials/crust_points_trial.py seeds      # the same on ten other seeds
    python trials/climate_round_cost.py standard   # what a climate round costs on this machine
    python tools/world_report.py worlds/first.zarr # the numbers by which a world is judged
    python tools/viewer_check.py worlds/first.zarr shots biome precipitation   # screenshots; needs playwright

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
      testing.py          the harness that runs one process alone
      library/            shared mathematics: mesh operators, flooding, transport, snow, orbit, noise
      processes/          one file per implementation of a slot; each file's first lines name the model,
                          what it ignores and where it is wrong
    viewer/               the viewer page
    tests/                the test suite; toy processes and the design's declarations as test data
    trials/               the two trials of build step 1 and their results
    tools/                development tools
    docs/BUILD_NOTES.md   the state of the build

## How to add things

* A better model for a slot: one new file in `processes/`, its constants in `data/models.yaml`, and one
  changed line naming it. It may read different fields, but it must write the slot's list.
* A new field: one entry in `data/fields.yaml` plus a process that writes it.
* A push (an external change to a field or a group): one entry in `data/interventions.yaml`.
  No code changes. `data/examples/` shows two.
* A new stage on a clock the engine has: one entry in `data/stages.yaml`.
* A test of one process alone: `worldengine.testing.Harness` feeds it inputs built for the purpose.
  It refuses an input the process does not declare, and a constant that does not exist.
