## Build speed: the same worlds, sooner (2026-11-09)

Sections 13 and 19 left the standard build at 4,660 s against its limit of 1,800 s. This step made the build faster
without changing what it builds: every change keeps every world the same, bit for bit, and a change that would have
altered a bit was not made but is listed below as an option. The engine's rule (the same output for the same input,
and no round that depends on the rounds before it except through what it reads) is unchanged. The standard build
still takes longer than its limit: 2,631 and 2,697 s in two builds beside one or more other jobs, against 3,440 s
before.

### What was built

- **SeaLevel's pouring, compiled** (`library/flood.py`). `pour()` and `barriers()` were plain Python over heaps
  (`heapq`); they are now compiled loops (numba, fastmath off) that take the same entries off the same queues in the
  same order and do the same sums in the same order. A queue is ordered by (height, cell number), as Python compared
  the pairs; two entries that compare equal are the same entry, so no heap can take them in another order.
- **The distance to the coast searched once a cell** (`operators.arc_distance_across`, used by SeaLevel). Each cell
  needs the distance to the nearest wet cell or to the nearest dry one; both were searched for every cell and one was
  dropped. Each kept number is worked out at its own place in an array of the same length as before.
- **The joined sides of a plate boundary by a walk** (`library/plates.py`, `_joined_within`). Which sides lie within
  twelve joined steps of a cell's own sides was found by twelve products of sparse matrices; a compiled walk outward,
  one ring of sides at a time, gives the same yes or no.
- **EnergyBalance keeps what does not change** (`energy_balance_wind.py`, `library/ocean.py`). The solver of the
  yearly mean (wave 0) does not depend on how slowly a cell warms, so it is prepared once in a climate run, not once a
  round; the solvers of the two waves are still prepared again whenever the stirred depth changes (below). What the
  air aloft takes from the wind's flow alone (where air rises and sinks, the potential of the flow aloft, the order
  of the cells and the lists of what flows into each) is worked out once a round (`ocean.aloft_paths`), not once in
  each of the three passes of the wind's heat. The mesh's Laplacian is kept for the climate run.
- **Moisture's sweeps prepared once a solve** (`library/transport.py`, `prepare`). In every visit of a cell the sweep
  added up the coefficients of its six sides and worked out the rain law's value in dry air and at saturation and
  the slope of evaporation; these do not change within a solve, so they are worked out once for it, with the same
  sums in the same order.
- **Circulation's band means of all sectors in one pass** (`operators.zonal_means_of_groups`). Each of the monsoon's
  sectors of longitude took a masked band mean of the whole field; one pass now gives all of them, leaving out only
  the cells outside a sector, which added exactly zero to its sums (a partial sum that starts at +0 is never −0, so
  adding +0 never changes it).
- **Tests** (`tests/test_same_bits.py`, 15 tests): each piece is compared byte for byte with the form it replaced,
  kept in the test file, on inputs chosen to be hard for it (heights with many ties and flat ground, empty groups and
  empty bands, saturated air); a harness that keeps EnergyBalance's solvers from run to run is checked against fresh
  ones after changes of the stirred depth and of the matrix's constants. Each test was seen to fail with its piece
  broken (a tie broken the other way, one step fewer in the walk, a sum in another order, a key without the depth or
  without B, the cells aloft taken in the wrong order, the coast searched from the wrong side).

### Conditions

| Condition | Result |
|---|---|
| Every world the same, bit for bit | Met [MEASURED]. Preview, seed 20261004: `world_fingerprint` 2c1ec14dd7744f7d… before and after, all 138 field fingerprints equal, after each change and in four builds side by side. Standard: d09bbe6c195eaae2… before and in both builds after, 138 of 138 equal, 46 climate rounds each |
| The standard profile inside its limit (1,800 s) | Not met: 2,697 and 2,631 s [MEASURED, beside one to four and beside up to two other jobs]; it was 3,440 s |
| The tests the change touches | `tests/test_contract.py`, `test_same_bits.py`, `test_processes.py`, `test_water.py`, `test_ocean.py`, `test_history.py`, `test_mesh.py`: 294 pass; `tests/test_world.py` with the new tests and the contract: 128 pass [MEASURED]. The whole suite was not run |

### Measured

Every number is from the build machine (4 cores, 15 GB), with one other agent's work sharing it; what ran beside each
build was logged once a minute [MEASURED].

**Standard profile**, one build before (commit 0dc5136) and two after, seconds of each process over the whole build:

| | Before | After | After, again |
|---|---|---|---|
| The build | 3,440 | 2,697 | 2,631 |
| Geological stage | 598 | 425 | 426 |
| Climate stage (46 rounds and the cause pass) | 2,819 | 2,249 | 2,182 |
| EnergyBalance | 1,492 (31.7 a round) | 1,202 (25.6) | 1,169 (24.9) |
| Moisture | 973 (20.7) | 696 (14.8) | 662 (14.1) |
| SeaLevel | 265 (2.12 a round) | 94 (0.75) | 92 (0.74) |
| Tectonics | 219 | 213 | 217 |
| Circulation | 172 | 162 | 159 |
| OceanCurrents, Hydrology, SurfaceAge, StormClimatology, FluvialErosion, Isostasy, Drainage | 70, 54, 38, 36, 28, 24, 23 | 73, 56, 39, 37, 29, 24, 24 | 73, 57, 40, 37, 27, 24, 24 (not changed) |
| Largest memory of the process | 7.12 GB | 7.21 GB | 7.19 GB |
| Beside it | 0 other jobs for 18 of 58 minutes, 1 for 27, 2 for 13 (this step's preview builds and benchmarks, for 11 minutes a factorization test on three threads, the other agent's tests and builds); mean load 2.45 | 0 for 2 of 45 minutes, 1 for 15, 2 for 18, 3 or 4 for 10 (this step's preview builds and tests, the other agent's builds); mean load 2.91 | 0 for 12 of 44 minutes, 1 for 23, 2 for 9 (the other agent's jobs); mean load 2.01 |

The first build after had more beside it than the build before, so its gain is if anything understated [INFERRED].
The second, with less beside it, was faster by 2 % only: here the load moved the time by a few per cent, not by the
half of section 13, so alone the build would still be far over 1,800 s [INFERRED from the two builds; none was run
alone]. The standard world now takes 46 climate rounds, not the 30 of section 19 [INFERRED: the changes of
section 22 came between, and took the twin from 20 rounds to 32], and peaked at 7.1 GB before this step, not 6.7.

**Preview profile**, two builds before and two after, alternating, beside the standard build above and, in part,
the other agent's builds (the load over a minute between 2.0 and 3.6):

| | Before | After |
|---|---|---|
| The build | 100.0, 102.8 | 78.6, 78.0 |
| Geological stage | 35.4, 34.1 | 22.0, 22.7 |
| Climate stage (41 rounds) | 62.8, 66.9 | 55.0, 53.7 |
| Moisture | 26.1, 27.6 | 23.0, 22.2 |
| EnergyBalance | 22.2, 23.5 | 17.3, 17.4 |
| Tectonics | 17.1, 16.7 | 14.0, 14.4 |
| SeaLevel | 12.6, 12.0 | 2.9, 3.0 |
| Circulation | 6.7, 7.6 | 5.9, 6.1 |

**Pieces on their own** [MEASURED, beside other jobs]:
- Moisture's ladder, the 12 monthly solves of one round: on the preview mesh (problems taken from round 10 of the
  default world) 0.369 s before, 0.256 s after; on the standard mesh (the preview world's climate carried cell by
  cell to level 7, a stand-in for a standard round) 10.68 s before, 6.50 s after. Same bits both times. With the new
  sweeps the whole Moisture run took 10.9 s there, of which the sweeps 5.6 and the prepared solvers' 120 solves 2.2.
- EnergyBalance on the standard mesh, in the harness: 37.3 s with its three solvers to prepare, 4.1 s with them kept.
  Preparing the solver of the yearly mean alone took 5.5 s (39.2 million entries in its two factors).
- Compiling the changed loops with an empty numba cache, as on the first build after an install: 10.5 s for the
  modules changed here, against 1.8 s before (most of it SeaLevel's queues). Later builds read the cache.

### EnergyBalance's solvers: why they are prepared again

A probe that logged the stirred depth EnergyBalance was handed, in 5 m steps, round by round [MEASURED]:

| | Preview | Standard |
|---|---|---|
| Calls (climate rounds and the cause pass) | 42 | 47 |
| Different depths | 41 | 46 |
| Cells whose step changed from the round before | 7,346 in round 2, 1,121 in round 5, 87 in round 20, 2 in round 41 | 119,660 in round 2, 16,805 in round 5, 1,668 in round 20, 17 in round 46 |
| A depth seen again | only in the cause pass, which repeats the last round and already kept its solver | the same |

So the waves' solvers miss because their matrix truly changes in every round until the last: the depth's step
moves in fewer cells as the climate settles, but never in none, and no depth ever comes back. Keeping more solvers
would not be used once; fewer distinct depths cannot arise without handing the solver a depth other than the one the
round read, which changes the answer. Only the yearly mean's solver was prepared again for nothing. After this step
the waves' two factorizations are about 21 s of each 25.6 s round of EnergyBalance at standard [MEASURED: the cause
pass, which keeps them, took 4.2 s], about 960 s of the build: the largest single cost left.

### Options that would change bits (not made)

- **Prepare the waves' solvers less often**: keep a cell's step until its depth moves by more than a step, or keep
  last round's factorization as the start of an iterative solve. Either changes the last digits or makes a round
  depend on the rounds before it. Worth up to about 960 s at standard [INFERRED from the line above].
- **Another order of the columns in SuperLU** (minimum degree on A + Aᵀ, the symmetric mode): other rounding. Not
  measured to the end: that ordering of the yearly mean's matrix on the standard mesh had not finished after 10
  minutes, against 5.5 s with COLAMD, and was stopped.
- **More threads for the mathematics libraries.** The profiles hold them to one (`math_threads`); with more, BLAS
  may split sums differently [INFERRED], not tried.
- **Several right-hand sides in one solve** (Moisture's months, EnergyBalance's waves): SuperLU hands several to other
  BLAS routines than one, which may round differently [UNVERIFIED: from memory of SuperLU's solve routine], not tried.

### Tried and dropped, and not done

- A packed layout of Moisture's per-cell numbers, one row of a table for each cell: 6.60 s against 6.50 for the
  standard-mesh ladder, no gain; and numba's numpy error model for its divisions: 6.51 s, no gain [MEASURED]. The
  sweep waits on its exponentials and divisions, not on memory [INFERRED from these two].
- StormClimatology solves its 12 monthly matrices twice, in the run after the climate settles and in the cause pass,
  with the same matrices. A prepared solver per month gives the bits of `spsolve` [MEASURED on matrices of the same form on the preview mesh,
  with random winds], but
  keeping twelve on the standard mesh would hold gigabytes [INFERRED from EnergyBalance's factors]; about 18 s, not done.
- `upwind_heating` as a compiled loop: about 0.6 s a round of EnergyBalance and OceanCurrents at standard together,
  so under 30 s a build [INFERRED]; not done.
- Tectonics barely moved (219 to 213 s): most of its time is in searches of point trees (`_nearest`, `nearest_cell`,
  the boundary's search within reach) [MEASURED: a profile of 12 rounds on the standard mesh], each a search the answer
  needs [INFERRED]; nothing there was found that could be shared or left out with the bits kept.
