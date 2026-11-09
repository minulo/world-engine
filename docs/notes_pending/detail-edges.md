## Finer detail without steps at the edges of the world's cells (amends section 21)

Section 21.3.3 said that the last correction cell by cell left steps at the edges of the world cells: the median height
step between fine neighbours was 583 m across an edge against 408 m inside a cell. This work removed the constant offset
per world cell, measured the temperature and the rain the same way, and found that most of the steps came from
somewhere else: the smooth weights themselves. Every number below is the preview world (seed 20261004, built with
`python -m worldengine build --profile preview`) on section 21's region, the 43 world cells within 800 km of the highest
ground outside the polar caps, 680 fine cells, 530 pairs of fine neighbours across an edge and 1,397 inside a cell
[MEASURED on the built store, with the module before and after this change; a world built in memory, as the test
fixture builds it, gives the same numbers], unless a line says otherwise.

### What the steps were made of

The surface was laid through the world's values with Gaussian weights 0.6 coarse spacings wide over the two rings
around each fine cell's world cell, lifted or lowered over 8 passes, and what the passes left was added as one number
to every fine cell of the world cell. Taken apart (median height step across an edge, against inside, and the ratio):

| | Across | Inside | Ratio | Gap left by the passes |
|---|---|---|---|---|
| As built: 8 passes, then the offset per cell | 583.5 m | 408.4 m | 1.428 | 138 m |
| 8 passes, no offset | 565.7 | 408.4 | 1.385 | 138 m |
| 30 passes, no offset | 574.9 | 406.5 | 1.414 | 0.08 m |
| No passes, no offset | 409.6 | 308.5 | 1.328 | 3,570 m |

The offset gave 18 m of the 175 m by which the edge steps exceeded those inside; passes run to convergence left the
ratio at 1.414. The Gaussian weights flatten the surface near each centre and steepen it near the edges, as any such
blend of values does [INFERRED: between two centres the blend is a logistic curve whose slope at the middle is 2.5
times its slope an eighth of the way from a centre, at this width]. On a plane tilted through the world (the x or z
coordinate of the sphere), which has no edges at all, the Gaussian surface steps 1.25 and 1.13 times as much across an
edge as inside; a surface planar between three centres steps 1.005 and 1.000 times as much.

The statistic of section 21 has a bias of its own on this region. The world's heights laid planar between the centres,
with no passes and no roughness, a surface on which nothing happens at the edges, score 1.367: the pairs that cross an
edge lie nearer the steep middle of a region centred on a peak, and the pairs inside the rim cells, whose edges
outward are not counted, are on its flatter foot. So the work also measured edge by edge: for each of the region's 106
edges between two of its world cells, the median step across that edge over the median step inside the two cells, and
the median of those. Edge by edge, the world's heights laid planar score 1.000 and laid with the Gaussian weights 1.221.

### What was built

`src/worldengine/detail.py`, with `data/detail.yaml`:

- **A surface planar between three centres.** Each fine cell lies in one of the triangles of world-cell centres that its
  world cell is a corner of (`mesh.faces`), and takes the three corners' values weighted by its barycentric coordinates
  in the plane of the triangle seen from the sphere's centre, so that two triangles that share a side agree along it
  [MEASURED: the smallest coordinate before the cut at nothing was −1.6e-15]. This replaces the Gaussian weights
  everywhere they were used: the heights, the size of the roughness, the sea-level temperature, the rain and the wind
  that the slopes face. `smoothing_spacings` is gone from detail.yaml.
- **Passes that converge.** The values the surface passes through at the centres start at the world's and are moved
  over 12 passes, each by 1.4 times its cell's gap (`mean_iterations: 12`, `relaxation: 1.4`). A world cell's mean on the
  planar surface holds 0.61 to 0.66 of its own centre's value [MEASURED, preview mesh; 0.611 on a plane of equal
  triangles, by calculation], so a pattern that alternates between neighbours keeps about 0.44 of itself, and
  1.4 = 2 / (0.44 + 1) shrinks the slowest and the fastest patterns alike [INFERRED]. Each pass leaves about a third of
  the gap; the Gaussian surface's passes left about 0.7 of it.
- **What is left goes in as a bump.** After the passes each world cell's gap is added in proportion to a bump that is 1 at
  the fine cell on its centre and 0 on its edges (the owner's coordinate less the largest other one, cut at nothing),
  scaled so that the cell's mean comes out exact. No world cell is moved as one. With 12 passes the bump is at most
  7.1 mm high on the region's fine cells, and 3.0e-5 K for the temperature.
- **Temperature** is the sea-level temperature laid on the surface, kept on each cell's mean through the lapse rate in
  the same passes and bump. Before, it had no passes: one smooth pass and the offset per cell.
- **Rain** is laid in logarithms, `facing × exp(surface)`, so that it can never fall below zero, and kept on each cell's
  mean by passes on the logarithm of the gap; what is left goes in as a bump that multiplies. A world cell whose bump
  would take some fine cell to nothing or below, which happens only to a cell with no rain at all, is scaled as one
  instead, so it stays dry. Rain below `rain_floor_mm: 0.001` a month is taken as that much while the passes run, so
  that it has a logarithm. Before, the rain was scaled by one factor per cell.
- The passes need more of the world around the region: the fine cells of the world cells within 2 × 12 + 1 = 25 rings
  of the region are worked out, against 19 before. A region of 43 cells is refined in 1.7 s, as before, of which most
  is finding the fine cells of each world cell the first time; asked again, 0.5 s.
- A world built before this change keeps its own `mean_iterations` (8); the constants that its copy of detail.yaml
  lacks are the engine's.

### Conditions

| Condition | Result |
|---|---|
| Averaged back, the region agrees with the world | Yes, to rounding: largest gaps 1.8e-12 m, 1.7e-13 K, 2.8e-14 mm (9.1e-13 m, 1.7e-13 K, 4.3e-14 mm before) |
| Its rivers leave the region where the world's rivers do | Yes. The two cells whose rivers leave pass on 0.971 and 1.063 of the world's flow (as before); the 9 inland cells 0.937 to 1.063 (as before, over 10 cells: one more land cell now has fine sea) |
| Two regions that overlap agree on their shared cells | Bit for bit (144 shared cells, every field) |
| One region asked for twice is identical | Bit for bit |
| No step at the edges, heights | Median step across an edge 510.1 m against 456.8 m inside, ratio 1.117 (1.428 before); edge by edge 1.004 (1.300 before) |
| The same for the year's mean temperature | 0.704 K against 0.745 K, ratio 0.946 (0.946 K against 0.377 K, 2.51, before); the median month 0.934 (2.37); edge by edge 0.960 (1.413) |
| The same for the year's rain | 75.4 mm against 77.8 mm, ratio 0.970 (112.5 against 63.0, 1.79, before); its logarithm 0.996 (1.95); edge by edge 0.878 (1.333) |
| Rain with dry cells | On a copy of the world in which every third cell near the region had no rain and others a thousand times their rain: no fine rain below zero, every dry cell dry, means within 6.4e-16 of the world's, relatively |

`tests/test_world.py` holds the ratios as found, then kept (`test_a_refined_region_steps_across_the_edges_of_the_world_s_cells_as_it_steps_inside_them`):
1.117, 0.946 and 0.996 within 0.03, 0.05 and 0.05, and 1.004 edge by edge within 0.03 over 106 edges. The module as it
stood fails all four. The new module with no passes fails three of them, with the bump (1.10, 1.09, 1.13 and 1.13
edge by edge) and with an offset per cell for the heights and the temperature (2.23, 2.69 and 2.08 edge by edge; the
rain, whose last step was left as built, 1.01).

Across five more regions of 600 km (at 74° S, 35° N, 69° N, 10° S and 22° S), 12 passes left at most 1.0 mm of height,
3.6e-6 K and 6.9e-7 of the rain for the bump, and section 21's region 2.2 mm, 9.6e-6 K and 7.1e-7.

### Departures and limits

1. The surface is planar between three centres: it bends along the lines between neighbouring centres, which the
   roughness hides and does not remove. Its slopes, and with them the rule for rain on slopes, change most near a
   centre where the facets meet, so the rain steps less across an edge than inside a cell (0.878 edge by edge).
2. A surface that keeps each cell's mean and joins its neighbours without a step must rise higher at the centre of a
   high cell than one that is nearly flat inside each cell. The fine heights now reach 10,244 m and −10,170 m (8,718 m
   and −8,875 m before), where the highest world cell of the region is 4,808 m on the mean and the deepest −6,500 m.
   The steps inside a cell grew (456.8 m from 408.4 m), the steps across an edge fell.
3. A world cell with no rain at all keeps none on its fine cells, and its edge is a step down to nothing: rain that
   cannot fall below zero cannot both keep a mean of nothing and join a wet neighbour without a step.
4. The bias of section 21's statistic on this region (1.367 for a surface with no edges) means its ratio cannot reach 1
   here; the edge-by-edge ratio is the one that says whether a step is left.
