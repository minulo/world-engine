"""Drainage: where water runs over the land, and where it collects.

Model (Established). Every cell hands its water to its lowest neighbour. Water therefore ends
in the sea or at the bottom of a closed hollow, a place with no lower neighbour. The hollows
are found as a depression hierarchy [DOCUMENTED: Barnes, Callaghan and Wickert 2020]:
  * two neighbouring hollows meet at their lowest pass, the pair of neighbouring cells, one in
    each, whose higher cell is lowest ("the higher of the two is the outlet cell, and its
    elevation is the depression's spill elevation");
  * the passes are taken from the lowest up. Two hollows that have both filled to their pass
    become one larger hollow, which fills on to its own lowest pass;
  * a hollow whose lowest pass leads to ground that already drains to the sea ends its tree:
    when it is full its water runs on from the cell beyond the pass.
The design named Priority-Flood (Barnes, Lehman and Mulla 2014) for this. Priority-Flood gives
the level to which each hollow fills when it is full [DOCUMENTED when the design was written:
that paper, arXiv 1511.04463]. The hierarchy gives the same levels for full hollows [INFERRED:
a hollow is linked to the sea through ground whose own pass is no higher; MEASURED: equal to
the levels of a Priority-Flood written for the comparison, on every ground tried] and adds
how the hollows nest, which Hydrology needs to size a lake that is only part full.

Whether a hollow holds a lake, and whether that lake overflows, depends on the climate, and
this process runs on the geological clock, which has none. It therefore writes two things:
  * the plain facts of the relief: the receiver of each cell, the hollow it drains into
    (depression_id) and the table of hollows;
  * the river basins and drained areas as they are when every hollow is full and overflows
    (basin_id, drainage_area): the water of a full hollow crosses its lake to the outlet cell
    and runs on from there. Hydrology decides which hollows do fill; where one does not, the
    land above it has no river mouth on the sea, whatever basin_id says.

On the sea the surface that water runs over is the water surface of the cell's own body of
water, taken from the table of seas. Sea cells have no receiver.

Ignores: rivers that split, as in deltas; groundwater; valleys narrower than a cell; the
currents inside a lake (its water is handed to the outlet by the shortest way).
Wrong where: a cell has one height, and no valley narrower than a cell is in it. A river
that crosses a range through a gorge finds the range closed: the mesh then shows a hollow
where there is none, or sends the river out by another pass [INFERRED. MEASURED on Earth's
relief for the estuary of the St Lawrence; five other narrows looked at are closed in the
relief data before any mesh: docs/BUILD_NOTES.md, section 4.4]. Where heights are exactly
equal the rule of the lowest neighbour cannot choose. The choice then falls to the bed, to
the mesh's geometry and last to the cell numbers (library/drainage.py, "Ties"): in a world
of the engine's own that touches only the choice of the sea cell a river runs into, but on
relief given in whole metres it decides where whole rivers go [MEASURED: on Earth's relief
a third of the land cells tie with a neighbour, and settling the ties otherwise moves the
mouth of a seventh of the land's area: docs/BUILD_NOTES.md, section 4.4].
"""
import numpy as np

from ..library import drainage as dr
from ..process import Process

RUNS_DOWN, IS_SEA, IS_BOTTOM, LEVEL_GROUND = range(4)                            # why a cell drains as it does
AT_SEA, REACHES_THE_SEA, NO_WAY_OUT = range(3)                                  # where a cell's water ends
OPEN_GROUND, UNDER_A_FULL_HOLLOW, SEA_CELL = range(3)                           # what a cell is when every hollow is full


class LowestNeighbourDrainage(Process):
    stage = "geological"
    reads = ("elevation", "ocean_mask", "sea_depth", "cell_area", "table:seas")
    writes = ("flow_receiver", "drainage_area", "basin_id", "depression_id", "spill_elevation", "slope", "table:hollows")
    model = "each cell drains to its lowest neighbour; hollows as a depression hierarchy (Barnes, Callaghan and Wickert 2020)"
    drivers = {"flow_receiver": ("rule",), "depression_id": ("hollow",), "basin_id": ("ends",), "drainage_area": ("cell_is",)}

    def run(self, ctx):
        mesh = ctx.mesh
        radius = ctx.planet["radius_m"]
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        area = ctx.read("cell_area").astype(np.float64)
        bed = ctx.read("elevation").astype(np.float64)
        surface = dr.drainage_surface(bed, ctx.read("sea_depth"), sea, ctx.read("table:seas")["surface_m"])
        ties = dr.mesh_ties(mesh)                                               # exact ties: the wider way, then the cell numbers
        recv = dr.receivers(surface, sea, mesh.nbr, bed, ties)
        stack = dr.flow_stack(recv)
        label, table = dr.hollows(surface, sea, recv, stack, mesh.edge_cells, area, bed, ties)

        # with every hollow full: one path from each cell to the sea, across each lake to its outlet
        full = dr.overflow_receivers(recv, surface, mesh.nbr, label, table, ties)
        full_stack = dr.flow_stack(full)
        drained = dr.accumulate(full_stack, full, np.where(sea, 0.0, area))
        mouth = dr.mouths(full_stack, full, sea)

        has = recv >= 0
        to = np.where(has, recv, 0)
        slot = np.argmax(mesh.nbr == to[:, None], axis=1)                    # which neighbour the receiver is
        distance = mesh.nbr_dist[np.arange(mesh.n), slot] * radius
        slope = np.where(has, (surface - surface[to]) / distance, 0.0)
        spill = np.where(label > dr.SEA, table["spill_m"][label], np.nan)

        ctx.write("flow_receiver", recv.astype(np.int32))
        ctx.write("drainage_area", drained)
        ctx.write("basin_id", mouth.astype(np.int32))
        ctx.write("depression_id", label.astype(np.int32))
        ctx.write("spill_elevation", spill)
        ctx.write("slope", slope)
        ctx.write_table("table:hollows", table)
        if ctx.recording:
            lowest = np.where(mesh.nbr >= 0, surface[np.maximum(mesh.nbr, 0)], np.inf).min(axis=1)
            rule = np.where(sea, IS_SEA, np.where(~has, IS_BOTTOM, np.where(lowest < surface, RUNS_DOWN, LEVEL_GROUND)))
            ctx.driver("flow_receiver", "rule", rule.astype(np.int32))
            ctx.driver("depression_id", "hollow", np.where(label > dr.SEA, label, -1).astype(np.int32))
            end = dr.terminal(full_stack, full)
            ctx.driver("basin_id", "ends", np.where(sea, AT_SEA, np.where(sea[end], REACHES_THE_SEA, NO_WAY_OUT)).astype(np.int32))
            full_level = table["spill_m"][dr.top_hollows(table)[label]]          # of the largest hollow around the cell
            in_water = (label > dr.SEA) & (surface <= np.where(np.isnan(full_level), -np.inf, full_level))
            ctx.driver("drainage_area", "cell_is", np.where(sea, SEA_CELL, np.where(in_water, UNDER_A_FULL_HOLLOW, OPEN_GROUND)).astype(np.int32))
