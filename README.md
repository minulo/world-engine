# World engine

A generator for a planet's geography, natural systems and climate, in which every feature follows
from a stated physical cause. The design is in the design document "World engine design: physical
causes, replaceable processes"; this folder is its build. The state of the build, what was measured
and what is still open are in [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md).

Built so far: the skeleton (build step 0) and the smallest end-to-end slice (build step 1):
terrain, temperature, wind, rainfall and biomes, with a viewer.

## Install

Python 3.11 or newer. The lock file pins the versions the engine was built and tested with.

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock        # Windows: .venv\Scripts\python
    .venv/bin/python -m pip install -e .

Nothing else is needed. The viewer is a plain web page with no third-party code.

## Use

    python -m worldengine order                                  # the running order computed from the declarations
    python -m worldengine build --profile preview  --out worlds/first.zarr     # 10,242 cells, seconds
    python -m worldengine build --profile standard --out worlds/big.zarr       # 163,842 cells, minutes
    python -m worldengine serve worlds/first.zarr                 # then open http://127.0.0.1:8765/
    python -m worldengine explain worlds/first.zarr --lat 48 --lon -20 --field biome
    python -m worldengine info worlds/first.zarr

    python -m worldengine build --profile preview --seed 7 --out worlds/other.zarr
    python -m worldengine build --profile preview --interventions data/examples/frozen_region.yaml --out worlds/frozen.zarr

The same seed and parameters always give the same world, bit for bit, on one machine with the pinned
versions. A world store is written once and never changed.

In the viewer: choose a field, drag to turn the globe, scroll to zoom, switch to the flat map, play
the months, and click a cell for its values and its "why" answer.

## Tests

    python -m pytest                    # about two minutes

Extra checks that are not part of the test run:

    python trials/crust_points_trial.py            # the trial of crust carried on moving points
    python trials/climate_round_cost.py standard   # what a climate round costs on this machine
    python tools/viewer_check.py worlds/first.zarr shots biome precipitation   # screenshots; needs playwright

## Layout

    data/                 every number: planet, models and their constants, profiles, stages, fields, tables,
                          seeds, pushes, category lists, sentence patterns; schemas/ holds the allowed keys and ranges
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
      library/            shared mathematics: mesh operators, flooding, transport, orbit, noise
      processes/          one file per implementation of a slot
    viewer/               the viewer page
    tests/                the test suite; toy processes and the design's declarations as test data
    trials/               the two trials of build step 1 and their results
    tools/                development tools

## How to add things

* A better model for a slot: one new file in `processes/`, its constants in `data/models.yaml`, and one
  changed line naming it. It may read different fields, but it must write the slot's list.
* A new field: one entry in `data/fields.yaml` plus a process that writes it.
* A push (an external change to a field or a group): one entry in `data/interventions.yaml`.
  No code changes. `data/examples/` shows two.
* A new stage on a clock the engine has: one entry in `data/stages.yaml`.
