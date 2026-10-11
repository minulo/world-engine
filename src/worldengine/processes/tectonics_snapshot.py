"""Tectonics, first version: one snapshot of seeded plates.

Model (Adapted): the plate picture of Cortial et al. 2019, frozen at one moment. Plates are rigid
caps, each turning about an axis through the planet's centre. Their outlines, motions and the
continents they carry are a seeded starting condition, drawn in sphere coordinates. Where two
plates close, the crust is thicker: on the overriding side of a trench and on both sides of a
collision between continents. Isostasy then turns thickness into height.

Ignores: time. Nothing has moved, so the ocean floor's age is read off the distance to the
nearest spreading ridge and the spreading speed there; mountain belts have no history; island
arcs, hot spots, shelves and rifts are absent.
Wrong where: everywhere a history matters. The size and width of the thickening are tuned
numbers, not derived. A plate with no ridge of its own, or floor far from one, gets the oldest
age allowed: a quarter to a half of the ocean floor sits at that cap, where Earth's floor is on
average about 60 My old [UNVERIFIED: recalled]. A continent ends in a cliff: crust of its full
thickness stands beside ocean floor with no shelf or slope between, so a coastal cell can stand
kilometres high. Build step 3 replaces this with the full plate history.

State: the seeded plates and crust points are made once, in start(), and carried in tables.
In this version one crust point sits on each cell centre and does not move.
"""
import numpy as np
import scipy.sparse as sp
from scipy.spatial import cKDTree

from ..library import operators as op
from ..library.noise import WAVE_NUMBERS, wave_field
from ..library.units import CM_PER_M, M_PER_KM, YEARS_PER_MY
from ..process import Process

from ..library.plates import (CONTINENTAL, OCEANIC, NONE, RIDGE, TRENCH, COLLISION, TRANSFORM, EVENT_SUBDUCTION,
                              EVENT_COLLISION, EVENT_SPREADING, EVENT_CODES, _arc, _nearest, boundaries, boundary_cells,
                              diving, seeded_start)


class SnapshotPlates(Process):
    stage = "geological"
    reads = ("cell_area",)
    reads_lagged = ("table:crust_points", "table:plates", "table:tectonic_events")
    writes = ("plate_id", "plate_velocity", "crust_type", "crust_thickness", "ocean_crust_age", "orogeny_age",
              "boundary_kind", "boundary_distance", "convergence_rate", "volcanism",
              "table:crust_points", "table:plates", "table:tectonic_events")
    has_start = True
    draws = ("plate_centres", "plate_axes", "plate_speeds", "outline_waves", "continent_plates", "continent_waves",
             "thickness_waves")
    model = "one snapshot of seeded plates, after Cortial et al. 2019"
    drivers = {"crust_thickness": ("normal_thickness", "seeded_variation", "thickened_by_plates", "event"),
               "plate_id": ("seeded",)}
    additive = ("crust_thickness",)

    # ------------------------------------------------------------------ the seeded start
    def start(self, ctx):
        seeded_start(ctx)

    _boundary_cells = staticmethod(boundary_cells)
    _boundaries = staticmethod(boundaries)
    _diving = staticmethod(diving)

    # ------------------------------------------------------------------ the snapshot
    def run(self, ctx):
        c, mesh, n = ctx.const, ctx.mesh, ctx.mesh.n
        radius = ctx.planet["radius_m"]
        area = ctx.read("cell_area")
        pts, plates = ctx.read_lagged("table:crust_points"), ctx.read_lagged("table:plates")
        ctx.read_lagged("table:tectonic_events")
        plate, ctype = pts["plate"], pts["crust_type"]
        k = plates["plate"].size
        base = pts["thickness_m"].astype(np.float64) - pts["thickened_by_plates_m"]
        axis = np.stack([plates["axis_x"], plates["axis_y"], plates["axis_z"]], axis=1)
        omega = plates["angular_speed_rad_per_my"] / YEARS_PER_MY                       # radians per year
        velocity = np.cross(axis[plate], mesh.xyz) * (omega[plate] * radius)[:, None]   # m per year

        # every cell that touches another plate: the plate it faces, and how the two plates meet there
        rotation = axis * omega[:, None]                                                # radians per year, as a vector
        is_boundary, facing, faces_continent, b_kind, b_close = self._boundaries(mesh, plate, ctype, rotation, radius, k,
                                                                                 c["boundaries"])

        # every cell: its nearest boundary cell on its own plate; of several equally near, the one that closes fastest
        near = np.full(n, -1, dtype=np.int64)
        dist = np.full(n, np.pi * radius)
        for p in range(k):
            mine = np.flatnonzero(plate == p)
            bp = mine[is_boundary[mine]]
            if bp.size:
                d, idx = _nearest(mesh.xyz[bp], mesh.xyz[mine], b_close[bp], b_kind[bp])
                near[mine], dist[mine] = bp[idx], _arc(d) * radius
        has = near >= 0
        safe = np.where(has, near, 0)
        kind_near = np.where(has, b_kind[safe], NONE)
        close_near = np.where(has, b_close[safe], 0.0)

        # age of the ocean floor: distance to the plate's nearest spreading ridge, at half the opening speed there
        a = c["ocean_age"]
        age = np.full(n, np.nan)
        ocean = ctype == OCEANIC
        age[ocean] = a["maximum_my"]
        for p in range(k):
            mine = np.flatnonzero((plate == p) & ocean)
            rp = np.flatnonzero((plate == p) & is_boundary & (b_kind == RIDGE))
            if mine.size and rp.size:
                d, idx = _nearest(mesh.xyz[rp], mesh.xyz[mine], -b_close[rp], b_kind[rp])     # of equally near ridge cells, the fastest
                half = np.maximum(-b_close[rp[idx]] / 2, a["minimum_half_rate_m_per_year"])
                age[mine] = np.minimum(_arc(d) * radius / half / YEARS_PER_MY, a["maximum_my"])

        b_diving = self._diving(plate, facing, faces_continent, b_kind, ocean, age, k, a["equal_within_my"])
        diving = np.where(has, b_diving[safe], False)
        overriding = (kind_near == TRENCH) & ~diving

        # thicker crust where plates close: continents on the overriding side of a trench, and both sides of a collision
        g = c["orogeny"]
        factor = np.clip(close_near / g["reference_speed_m_per_year"], 0.0, g["maximum_speed_factor"])
        thickening = np.zeros(n)
        land = ctype == CONTINENTAL
        # behind a trench the belt stands back from the boundary: nothing at the trench, a crest a third of the way in
        x = np.clip(dist / (g["subduction_width_km"] * M_PER_KM), 0.0, 1.0)
        crest = (1 / 3) * (1 - 1 / 3) ** 2
        sub = overriding & land
        thickening[sub] = (g["subduction_thickening_m"] * factor * x * (1 - x) ** 2 / crest)[sub]
        # a collision is thickest along the line where the continents meet, on both sides of it
        x = np.clip(dist / (g["collision_width_km"] * M_PER_KM), 0.0, 1.0)
        col = (kind_near == COLLISION) & land
        thickening[col] = (g["collision_thickening_m"] * factor * (1 - x * x) ** 2)[col]
        made = thickening > 0                                    # where a boundary thickens the crust directly
        # a mountain belt has no sharp ends: spread the thickening over a set length, inside continental crust
        if land.any():
            length = g["smoothing_km"] * M_PER_KM / radius
            mask = land.astype(np.float64)
            weight = op.smooth(mesh, mask, length, ctx.memo)
            thickening = np.where(land, op.smooth(mesh, thickening, length, ctx.memo) / np.maximum(weight, np.finfo(float).tiny), 0.0)
            thickening = np.maximum(thickening, 0.0)
        thickness = base + thickening
        active = thickening > g["active_above_m"]                # mountain building counts as acting now
        orogeny = np.where(active, 0.0, np.nan)

        # zone of influence of each kind of boundary
        z = c["zones"]
        reach = np.select([kind_near == RIDGE, kind_near == TRENCH, kind_near == COLLISION, kind_near == TRANSFORM],
                          [z["ridge_km"], g["subduction_width_km"], g["collision_width_km"], z["transform_km"]], 0.0) * M_PER_KM
        kind = np.where(dist <= reach, kind_near, NONE).astype(np.int16)

        # volcanic activity: an arc behind each trench on the overriding side, and the ridge crests
        v = c["volcanism"]
        arc = np.exp(-((dist - v["arc_distance_km"] * M_PER_KM) / (v["arc_width_km"] * M_PER_KM)) ** 2) * np.minimum(factor, 1.0)
        crest = np.exp(-(dist / (v["ridge_width_km"] * M_PER_KM)) ** 2)
        volcanism = np.where(overriding, arc, np.where(kind_near == RIDGE, crest, 0.0))

        # events: one row for each pair of plates and kind of meeting, counting the cells along that boundary
        bcell = np.flatnonzero(is_boundary)
        code = np.select([b_kind[bcell] == TRENCH, b_kind[bcell] == COLLISION, b_kind[bcell] == RIDGE],
                         [EVENT_SUBDUCTION, EVENT_COLLISION, EVENT_SPREADING], 0)
        lower, higher = np.minimum(plate[bcell], facing[bcell]), np.maximum(plate[bcell], facing[bcell])
        keep = code > 0
        key = (lower[keep].astype(np.int64) * k + higher[keep]) * EVENT_CODES + code[keep]
        uniq, row, counts = np.unique(key, return_inverse=True, return_counts=True)
        ev_kind, ev_pair = uniq % EVENT_CODES, uniq // EVENT_CODES
        ev_a, ev_b = ev_pair // k, ev_pair % k
        b_event = np.full(n, -1, dtype=np.int64)                 # the event that each boundary cell belongs to
        b_event[bcell[keep]] = row
        # The event behind a cell's thickening: that of the boundary cell that made it. Where the thickening was spread
        # in from next door, it is the event of the nearest cell that a boundary thickened directly.
        event = np.full(n, -1, dtype=np.int64)
        event[made] = b_event[safe[made]]
        spread = np.flatnonzero(active & ~made)
        if spread.size and made.any():
            source = np.flatnonzero(made)
            event[spread] = event[source[cKDTree(mesh.xyz[source]).query(mesh.xyz[spread])[1]]]
        event[~active] = -1

        normal_thickness = np.where(land, c["thickness"]["continental_normal_m"], c["thickness"]["oceanic_m"])
        ctx.write("plate_id", plate)
        ctx.write("plate_velocity", velocity)
        ctx.write("crust_type", ctype)
        ctx.write("crust_thickness", thickness)
        ctx.write("ocean_crust_age", age)
        ctx.write("orogeny_age", orogeny)
        ctx.write("boundary_kind", kind)
        ctx.write("boundary_distance", dist)
        ctx.write("convergence_rate", close_near)
        ctx.write("volcanism", volcanism)
        ctx.driver("crust_thickness", "normal_thickness", normal_thickness)
        ctx.driver("crust_thickness", "seeded_variation", base - normal_thickness)
        ctx.driver("crust_thickness", "thickened_by_plates", thickening)
        ctx.driver("crust_thickness", "event", event)
        ctx.driver("plate_id", "seeded", np.ones(n, dtype=np.int32))

        out = {name: pts[name] for name in pts}
        out.update(thickness_m=thickness, ocean_age_my=age, orogeny_age_my=orogeny, thickened_by_plates_m=thickening)
        ctx.write_table("table:crust_points", out)
        cont_area = np.bincount(plate, weights=area * land, minlength=k)
        plate_area = np.bincount(plate, weights=area, minlength=k)
        new_plates = {name: plates[name] for name in plates}
        new_plates.update(area_m2=plate_area, continental_share=cont_area / np.maximum(plate_area, np.finfo(float).tiny))
        ctx.write_table("table:plates", new_plates)
        ctx.write_table("table:tectonic_events", {"time_my": np.zeros(uniq.size), "kind": ev_kind, "plate_a": ev_a,
                                                  "plate_b": ev_b, "cells": counts})
