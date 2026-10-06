# Build step 3, "Deep time": the goal

Written 2026-10-06 for an agent that has not seen the earlier work. Read this file, then `TASKS.md`, then
`ACTIONS.md` (all in `docs/step3/`). The owner is Minh. The state of everything built so far is in
`docs/BUILD_NOTES.md` (start with sections 1, 6, 8 and 11) and `HANDOFF.md`.

## What step 3 is

The approved design ("World engine design", the Claude doc linked from `HANDOFF.md`) orders the build in steps.
Steps 0, 1 and 2 are built. Step 3 in the design's own words:

| | |
|---|---|
| Builds | Full plate history, FluvialErosion, Lithology, SurfaceAge. One trial of a history ten times the default. History snapshots, which the viewer plays as a film. |
| Done when | Relief tests and the slope-area test pass. The land of a world stopped at 250 My equals, bit for bit, the land at 250 My inside a longer run. In a history of 2,500 My, the volume of continental crust, the share of land, the number of plates, the mean height of the land and the distance a marked patch of crust has strayed from the place its plate's motion gives are measured every 250 My. A steady drift in any of them is recorded as a failure, and the expected range of history length in models.yaml is set to the span that showed none. A world built to 250 My and then continued to 500 My equals, bit for bit, a world built to 500 My in one run. |

Today the geological stage runs ONE round: Tectonics is a frozen snapshot of seeded plates
(`src/worldengine/processes/tectonics_snapshot.py`), and `data/stages.yaml` sets `history_length_my: 2.0`. Step 3
makes the plates move for 250 My (125 rounds of 2 My), lets rivers cut the land while it rises, and records what
kind of rock and how old each surface is.

## Why it matters to the worlds

Known errors of today's world that step 3 is expected to mend or change (`docs/BUILD_NOTES.md`, section 8):
continents end in cliffs; a quarter to a half of the ocean floor sits at the age cap; half the land drains into
closed hollows and a twelfth lies under lakes, because no river has ever cut the seeded relief. None of these
expectations is measured. Each must be measured after the step and reported as it comes out.

## What the design says each process is (Layer 5 of the design document)

- **Tectonics** [Adapted: Cortial et al. 2019, "Procedural Tectonic Planets"]. Rigid plates turn about axes
  through the planet's centre. Rules decide which plate dives under which (subduction), when continents collide
  and weld, where new ocean floor forms, and when a plate splits. Two changes and one addition by the design:
  (1) the paper lifts the ground directly; here the same rules THICKEN THE CRUST and Isostasy turns thickness into
  height (about 15 % of added thickness becomes height), so that erosion and rebound keep count of rock;
  (2) the paper's own erosion and ocean-floor height rules are replaced by FluvialErosion and Isostasy;
  (addition) crust lives on the table `crust_points`, about one point per cell, which ride with the plates; every
  round the crust fields are drawn onto the mesh from the points; erosion computed on cells returns to the points
  through the group `crust_thickness_tendency` (each point is thinned by what its cell lost, before the points
  move); every so many rounds the points are replaced by a fresh even set, each filled from the three old points
  around it, and the table records those three and their weights so that another process (SurfaceAge) can carry
  its own values across.
- **FluvialErosion** [Established]. The stream power law, solved with the implicit method of Braun and Willett
  2013 (long time steps). Hillsides are slowly smoothed. It modifies `elevation` (priority 10), writes
  `erosion_rate`, and contributes `erosion_thinning` to the group `crust_thickness_tendency`. It reads
  `erodibility`, `cell_area`, and from the previous round `runoff_annual` and the table of seas. The eroded rock is
  laid down nowhere (a stated limit).
- **Lithology** [Rule]. A table maps tectonic setting to a rock family and an erodibility. Reads `crust_type`,
  `orogeny_age`, `volcanism`, `boundary_kind`; writes `rock_type`, `erodibility`.
- **SurfaceAge** [Rule]. Age grows every round and resets where lava, deep erosion or emergence from the sea
  renews the ground. Ages are kept on the crust points (table `surface_age_points`) and drawn onto the mesh.

The exact declarations (reads, writes, lagged reads, groups, order) are test data already:
`tests/design_declarations.py`. The scheduler's order for the geological stage is
Tectonics, Isostasy, Lithology, FluvialErosion, SeaLevel, Drainage, SurfaceAge.

## What the plate paper gives (read out by a page reader on 2026-10-06; open it again before relying on it)

Source: https://perso.liris.cnrs.fr/eric.galin/Articles/2019-planets.pdf . Label everything below
[DOCUMENTED: Cortial et al. 2019, as a page reader gave it; not seen as printed].

- Time step 2 My. Points are resampled every 10 to 60 steps "depending on the observed maximum plate speed";
  fresh points between diverging plates are new ocean floor, the others are filled by barycentric interpolation.
- Subduction (4.1): of two ocean plates the older dives; ocean always dives under continent. Uplift of the
  overriding plate = u0 * f(distance to the front) * g(relative speed) * h(height of the diving plate), with
  u0 = 0.6 mm/y, g(v) = v / v0, v0 = 100 mm/y, f a piecewise cubic that peaks at a control distance and fades to
  zero at the subduction distance rs = 1,800 km, h the square of the normalised height
  (z - zt) / (zc - zt), zt = -10 km, zc = 10 km. Slab pull turns the plate's axis a little toward its
  subduction fronts.
- Collision (4.2): triggered when two continents interpenetrate by more than 300 km; the terrane is cut from
  its plate and welded to the other; height surge = dc * A * (1 - (d / r)^2)^2 within
  r = rc * sqrt(v / v0) * sqrt(A / A0), rc = 4,200 km, dc = 1.3e-5 per km, A the terrane's area, A0 the mean
  starting plate area.
- Spreading (4.3): new points appear in the gap along the ridge and join the nearer plate; age counts from there.
- Rifting (4.4): a plate splits with probability P = L * exp(-L), L = L0 * f(continental share) * A / A0, into 2
  to 4 parts along warped Voronoi lines.
- Table 3 also gives: ridge height -1 km, abyssal plain -6 km, the paper's own erosion 0.03 mm/y and ocean
  damping 0.04 mm/y, trench sediment 0.3 mm/y. The design replaces the last three by FluvialErosion and Isostasy.

## What must stay true (the owner's standing rules)

1. Every feature follows from a stated cause. Never place an outcome.
2. A process declares what it reads and writes and never calls another process. A new model for a slot is one
   new file in `src/worldengine/processes/` plus its constants in `data/models.yaml`.
3. Every constant lives in a data file with a label saying where it comes from.
4. The same seed and parameters give the same world, bit for bit, on one machine.
5. Every cell can answer "why is it like this?": each process records its drivers, and
   `data/explanations.yaml` holds the sentence patterns.
6. A design condition that fails is NOT loosened. It stays, marked as a strict expected failure with the number
   measured.
7. Out of scope: magic weather, cultures, species, settlements, trade.

## What "finished" means for the whole step

Every row of the "Done when" above is either met and held by a test, or failed and recorded as a strict expected
failure with its measured number; the suite passes with and without the Earth data; `docs/BUILD_NOTES.md`, the
README, the design document and the project note say what was measured; and an independent reviewer who did not
write the code has checked the claims.
