## Worlds from another system, measured field by field (tools/compare_worlds.py)

On the workflow's first run the preview world built from the same seed on ubuntu-latest, macos-latest, windows-latest
and in Docker differed in 60 to 96 of its 138 fingerprints (README, "Worlds from another system"). A fingerprint says
that a field differs, not by how much: whether the systems round the last digits differently or build other
continents was not known. This work builds the tool that measures it and has the workflow run it. The workflow has
not run with the change, so no result across systems is given here; what was measured is on the build machine.

### What was built

- **`tools/compare_worlds.py STORE_A STORE_B [--json OUT] [--markdown OUT] [--title TEXT]`.** It reads both stores
  through `StoreView` (which gained `table_names()`, also on `MemoryView` and `WorldView`; `fingerprints()` now uses
  it). STORE_A is the reference. For every field, every array of the mesh and every column of every table:
  - a number (a float array): the largest absolute difference; the same as a share of the field's range, the largest
    value less the smallest over both worlds; the share of the cells, and of the cell-months for a field with one
    slice per month, that differ by more than the float32 rounding of the value; the same shares beyond the noise
    threshold; and how many values are missing in one world and not in the other;
  - a category, an index or a true-or-false field (the kinds category, index and boolean, and any integer array):
    the share of the cells, and of the cell-months, whose value differs;
  - a table: its rows in each world, the rows matched by the table's key columns (a plate by its number, a sea by
    its lowest cell, a lake or a hollow by the cell at its bottom, a tectonic event by its time, kind and plates),
    the rows of each world that find no match, and each column over the matched rows as above. A table without a
    key (the crust points and their surface ages) is matched row by row where both have as many rows.
  A cell counts once however many of its months or of the three components of a direction differ. The tool also
  names what differs in the stores' provenance (seed, code and lock fingerprints, package versions), and gives one
  verdict. It ends with 0 whatever the verdict and with 2 when a store is missing or cannot be read.
- **The verdicts.**

  | Verdict | When |
  |---|---|
  | identical | every field, table and array of the mesh is the same, bit for bit |
  | same planet with rounding noise | land and sea, the plates and the crust (ocean_mask, plate_id, crust_type) agree on all but a few cells, every table has the same rows, and no field or column differs by more than a thousandth of its range on more than a thousandth of its cells or rows |
  | same planet with grown differences | the shape agrees as above, but some field or column differs beyond the noise threshold on more than a few cells or rows, a table has rows the other lacks, or a field is in one world only |
  | different planet | ocean_mask, plate_id or crust_type differs on more than a thousandth of the cells, or the plates table has other rows |
  | not comparable | the meshes have other sizes or other neighbours |

- **The thresholds, and why.** The float32 rounding of a value is one unit in its last place as a float32, taken at
  the larger of the two values: two computations that round differently once end one unit apart, and a float32
  field cannot hold less. A float64 array (cell_area, the mesh's coordinates, most table columns) is held to the same
  unit. The noise threshold, a thousandth of the range, lies four orders of magnitude above that rounding (6e-8 to
  1.2e-7 of a value), and below one step of the viewer's colours: the viewer colours a field with a table of 256
  colours over its 2nd to 98th percentiles [DOCUMENTED: viewer/viewer.js, `lut` and `rangeOf`], so a thousandth of
  the whole range is less than a step wherever those percentiles span more than 0.256 of it [INFERRED: arithmetic].
  "A few cells" is a thousandth of the cells, 10 of the 10,242 of the preview mesh. All three are [PROVISIONAL]:
  they were set before any world of another system was compared.
- **The workflow** (`.github/workflows/local-run.yml`). Each native job zips `worlds/first.zarr` (1,681 files on the
  build machine) where it exists and uploads it as `world-<system>`; the Docker job zips the world of its volume as
  `world-docker`. Both are kept 14 days and not compressed again. The job "The worlds of the systems, side by side"
  keeps its table of fingerprints, then checks out the engine, installs the lock file, downloads the worlds, runs
  the tool on each against the world of ubuntu-latest, writes a table (verdict, fields the same bit for bit, fields
  beyond the rounding, fields beyond the noise threshold, cells of ocean_mask that differ, the largest difference)
  and the tool's own section for each system to the step summary, and uploads the JSON and the sections as the
  artifact `world-comparisons`. It fails only when the tool does: a zip file that cannot be opened is handed to the
  tool as it is, and the tool's refusal fails the job. The YAML loads with `yaml.safe_load` [MEASURED].
- **Tests** (`tests/test_compare_worlds.py`, nine tests, 15 to 20 s): the world of the setup and geological stages
  over 8 My on the preview mesh, with a uniform runoff for the climate (as `tests/test_history.py` builds it), built
  twice and changed by hand in copies. Two of them read the workflow: one, that every system uploads its world and
  the last job downloads them and keeps the fingerprints; the other takes the native job's zip command and the
  compare job's script out of it and runs them on that world. `tests/test_tools.py` holds the tool to the rules of every tool
  (its help, an option it does not know, a store that is not there).

### Conditions

| Condition | Result |
|---|---|
| Two builds of the same small world are identical | Pass: the small world built twice is "identical", every field, table and array of the mesh. The whole preview world built twice: identical, 71 of 71 fields, 7 of 7 tables, 8 of 8 arrays of the mesh [MEASURED] |
| A perturbed field is reported with the right numbers | Pass: 50 m added to 3 cells of elevation gives a largest difference of 50 m, that over the range as its share, and 3 cells beyond the rounding and beyond the noise threshold; one unit in the last place added to every cell of sea_depth is "not identical" with no cell beyond the rounding; the verdict is the same planet with rounding noise. On 200 cells it is grown differences; on 200 cells at half the threshold, rounding noise again |
| Flipped ocean cells give "a different planet" | Pass: 5 cells flipped give the same planet with rounding noise, and the verdict names them; every 50th cell (205 of 10,242, 2.0 %) gives a different planet |
| Tables by row counts and key columns | Pass: a hollow cut from the middle of its table leaves the others matched to themselves, every column the same bit for bit; a plate fewer is a different planet; a table turned round has the same rows and numbers, though not the same bytes |
| Seconds on the preview world | 1.6 to 2.0 s a comparison, with the start of the interpreter [MEASURED] |
| The compare job fails only if the tool errors | Pass, on its own script run here: worlds the same and changed end with 0 and the table; an unreadable zip ends with the tool's exit 2 and the job's failure |

### Measured on the build machine

A 4-core Intel Xeon at 2.10 GHz with AVX-512, Python 3.13.18, the pinned packages: the preview world of seed
20261004 built four times, and once with seed 7 [MEASURED, 2026-11-09]. `NPY_DISABLE_CPU_FEATURES=X86_V4` switches
off numpy's AVX-512 code, as the reviewer of step 2 did (section 6, item 11); `NUMBA_CPU_NAME=generic` compiles
numba's loops for a generic x86-64 processor (numba wrote a second copy of each cached loop at the start of that
build [MEASURED: the files of its cache], so the loops were compiled again, not read back).

| World B, against a plain build | Verdict | Fields the same bit for bit | Beyond the float32 rounding on some cell | Beyond the noise threshold | Fingerprints differing | Largest difference |
|---|---|---|---|---|---|---|
| A second plain build | identical | 71 of 71 | 0 | 0 | 0 of 138 | none |
| numpy's AVX-512 code switched off | same planet with rounding noise | 35 of 71 | 32 | 0 | 42 of 138 | 3.6e-5 of the range of snow_cover |
| That, and numba's loops for a generic processor | the same world as the row above, bit for bit | 35 of 71 | 32 | 0 | 42 of 138 | the same |
| Another seed (7) | different planet | 6 of 71 | 65 | 65 | 132 of 138 | ocean_mask differs on 37.4 % of the cells; 23 and 30 plates |

With numpy's AVX-512 code switched off:

- The planet's shape is untouched. elevation, ocean_mask, plate_id, crust_type, cell_area, sea_depth, flow_receiver,
  basin_id and depression_id are the same bit for bit, and none of the 12 category, index and true-or-false fields
  differs on any cell.
- The climate differs in its last digits, on many cells: wind beyond the rounding on 98 % of the cells, precipitation
  on 80 %. The largest difference of any field is 3.6e-5 of its range (snow_cover; soil_moisture 3.1e-5,
  ocean_heat_convergence 2.9e-5). Four fields differ by no more than the rounding: latitude, longitude,
  sea_level_pressure and surface_temperature.
- The lakes are the same 17. Six of their 14 columns differ, by at most 1.7e-7 of their range.
- The mesh's latitude and longitude differ in the last bits of a float64 (7.9e-17 of their range); its areas do not.

The fourth check of step 2 measured 21 of 52 fields differing, at most 3.3 parts in a million (section 6, item 11);
the world has grown since by steps 3 to 11. That numba's loops gave the same world for a generic processor suggests
that numpy's routines, not numba's code, make this machine's two worlds differ [INFERRED from the one machine]. On
the workflow's run the mesh's own cell areas differed between systems (README), which they did not here; the areas
enter the 250 My of the history from its first round, so the differences across systems may reach the land and sea,
which one machine cannot show [INFERRED: Tectonics and SeaLevel declare cell_area among what they read]. The
workflow now measures that.

### Departures and limits

1. **Four verdicts, not three.** The brief names identical, the same planet with rounding noise and a different
   planet. A world whose land, plates and crust agree but whose climate has grown past the noise threshold is
   neither, and is named "same planet with grown differences". "Not comparable" covers meshes whose cells do not
   correspond.
2. **"A different planet" counts the plates and the crust as well as land and sea**: plate_id and crust_type
   beside ocean_mask, and the rows of the plates table.
3. **The noise threshold is a share of the range.** For a field whose range a few large values set
   (drainage_area, river_discharge) it is lenient on most cells. A river that takes another way shows in
   flow_receiver and basin_id, which are compared as indices.
4. **An index that numbers things counts as differing when it is renumbered.** depression_id is a row of the table
   of hollows, so one hollow more renumbers those after it: a grown difference, never another planet.
5. **A key that repeats is matched in the order of its rows.** A hollow made of two has the bottom cell of its
   deeper part; where a hollow with one bottom is missing in one world, the larger hollows on the same bottom are
   paired one place out.
6. **The storms table and the fields of a day are not in a store**: the weather clock is worked out on request and
   never stored. The tool has a key for storms (kind and day of birth) and reads a field with one slice per day as
   one with one per month, for a store that would hold them; neither was tried on a world.
7. **Not compared**: the pictures of the history (`history/`), the state carried to continue a history (`carry/`)
   and the cause records (`causes/`).
8. **The workflow's change has not run.** No result across systems exists. Its `paths` filter does not name
   `tools/compare_worlds.py`, so a change to the tool alone does not start the workflow; `workflow_dispatch` does.
9. **The earlier branch.** The tool, its tests and the workflow's steps were begun on
   `claude/quirky-newton-a5zchs-wip-compare-worlds` and left untested. Their structure was kept. This work added
   the matching of rows by key, the counts the workflow's table reads, the reading of day fields, the guard on the
   zip step and the handing of a broken zip file to the tool, the tests of rows, of the workflow's own script and of
   a store that is no store, and named the verdicts as the brief does.
