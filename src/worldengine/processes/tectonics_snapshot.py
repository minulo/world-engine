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
numbers, not derived. Build step 3 replaces this with the full plate history.

State: the seeded plates and crust points are made once, in start(), and carried in tables.
In this version one crust point sits on each cell centre and does not move.
"""
import numpy as np
from scipy.spatial import cKDTree

from ..library import operators as op
from ..library.noise import wave_field
from ..library.units import CM_PER_M, M_PER_KM, YEARS_PER_MY
from ..process import Process

OCEANIC, CONTINENTAL = 0, 1
NONE, RIDGE, TRENCH, COLLISION, TRANSFORM = 0, 1, 2, 3, 4
EVENT_SUBDUCTION, EVENT_COLLISION, EVENT_SPREADING = 1, 2, 4
EVENT_CODES = 8                 # room for the kinds of event when a pair of plates and a kind are packed into one number


def _arc(chord):
    return 2 * np.arcsin(np.clip(chord / 2, 0, 1))


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
        c, mesh, n = ctx.const, ctx.mesh, ctx.mesh.n
        k = int(c["plates"])
        centres = ctx.draw.sphere_points("plate_centres", k)
        axes = ctx.draw.sphere_points("plate_axes", k)
        lo, hi = c["plate_speed_cm_per_year"]
        speed = (lo + (hi - lo) * ctx.draw.uniform("plate_speeds", k)) / CM_PER_M          # m per year at the plate's widest circle
        angular = speed / ctx.planet["radius_m"] * YEARS_PER_MY                           # radians per My
        # outlines: each cell joins the nearest plate centre, seen from a position shifted by a smooth random field
        o = c["outline"]
        u = ctx.draw.uniform("outline_waves", 3 * 4 * int(o["waves"])).reshape(3, -1)
        shift = np.stack([wave_field(mesh.xyz, u[i], o["wave_number"]) for i in range(3)], axis=1)
        moved = mesh.xyz + o["amplitude_rad"] * shift
        moved /= np.linalg.norm(moved, axis=1, keepdims=True)
        plate = cKDTree(centres).query(moved)[1].astype(np.int32)
        # continents: a score from a smooth field, a per-plate bias and the distance from the plate's edge;
        # the highest-scoring share of the area is continental crust
        q = c["continents"]
        edge = self._boundary_cells(mesh, plate)
        depth = np.zeros(n)
        for p in range(k):
            mine = np.flatnonzero(plate == p)
            b = mine[edge[mine]]
            if b.size:
                depth[mine] = _arc(cKDTree(mesh.xyz[b]).query(mesh.xyz[mine])[0])
        bias = np.where(ctx.draw.uniform("continent_plates", k) < q["plate_share"], 1.0, -1.0)
        field = wave_field(mesh.xyz, ctx.draw.uniform("continent_waves", 4 * int(q["waves"])), q["wave_number"])
        score = field + q["plate_bias"] * bias[plate] + q["interior_weight"] * depth / max(depth.max(), np.finfo(float).tiny)
        order = np.lexsort((np.arange(n), -score))                                     # ties broken by cell number
        share = np.cumsum(mesh.area[order]) / mesh.area.sum()
        ctype = np.zeros(n, dtype=np.int16)
        ctype[order[share <= q["fraction"]]] = CONTINENTAL
        # thickness before any plate acts on it
        t = c["thickness"]
        vary = wave_field(mesh.xyz, ctx.draw.uniform("thickness_waves", 4 * int(t["variation_waves"])), t["variation_wave_number"])
        thick = np.where(ctype == CONTINENTAL, t["continental_normal_m"] + t["continental_excess_m"] + t["variation_m"] * vary,
                         t["oceanic_m"])
        none = np.full(n, -1, dtype=np.int32)
        zero = np.zeros(n, dtype=np.float32)
        ctx.write_table("table:crust_points", {
            "plate": plate, "x": mesh.xyz[:, 0], "y": mesh.xyz[:, 1], "z": mesh.xyz[:, 2], "crust_type": ctype,
            "thickness_m": thick, "ocean_age_my": np.full(n, np.nan), "orogeny_age_my": np.full(n, np.nan),
            "thickened_by_plates_m": zero, "removed_by_erosion_m": zero,
            "source_a": none, "source_b": none, "source_c": none, "weight_a": zero, "weight_b": zero, "weight_c": zero})
        ctx.write_table("table:plates", {
            "plate": np.arange(k), "axis_x": axes[:, 0], "axis_y": axes[:, 1], "axis_z": axes[:, 2],
            "angular_speed_rad_per_my": angular, "area_m2": np.zeros(k), "continental_share": np.zeros(k),
            "carries_continent": bias > 0, "centre_x": centres[:, 0], "centre_y": centres[:, 1], "centre_z": centres[:, 2]})
        ctx.write_table("table:tectonic_events", {"time_my": [], "kind": [], "plate_a": [], "plate_b": [], "cells": []})

    @staticmethod
    def _boundary_cells(mesh, plate):
        i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
        cross = plate[i] != plate[j]
        edge = np.zeros(mesh.n, dtype=bool)
        edge[i[cross]] = True
        edge[j[cross]] = True
        return edge

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

        # every edge between two plates: closing speed and sliding speed
        i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
        cross = np.flatnonzero(plate[i] != plate[j])
        ci, cj, normal = i[cross], j[cross], mesh.edge_normal[cross]
        rel = velocity[ci] - velocity[cj]
        closing = np.einsum("ij,ij->i", rel, normal)                                    # positive where the plates close
        sliding = np.linalg.norm(rel - closing[:, None] * normal, axis=1)
        b = c["boundaries"]
        e_kind = np.where(np.abs(closing) < b["transform_ratio"] * sliding, TRANSFORM,
                          np.where(closing < 0, RIDGE,
                                   np.where((ctype[ci] == CONTINENTAL) & (ctype[cj] == CONTINENTAL), COLLISION, TRENCH)))
        e_kind = np.where(np.abs(closing) + sliding < b["minimum_speed_m_per_year"], TRANSFORM, e_kind)

        # boundary cells: each takes the kind and closing speed of its fastest cross-plate edge
        speed = np.abs(closing) + sliding
        cells = np.concatenate([ci, cj]); other = np.concatenate([cj, ci])
        e_all = np.concatenate([np.arange(cross.size)] * 2)
        order = np.lexsort((e_all, -speed[e_all], cells))
        first = np.ones(order.size, dtype=bool)
        first[1:] = cells[order][1:] != cells[order][:-1]
        pick = order[first]
        bcell, bedge, bother = cells[pick], e_all[pick], other[pick]
        is_boundary = np.zeros(n, dtype=bool); is_boundary[bcell] = True
        b_kind = np.zeros(n, dtype=np.int16); b_kind[bcell] = e_kind[bedge]
        b_close = np.zeros(n); b_close[bcell] = closing[bedge]
        b_other = np.full(n, -1, dtype=np.int64); b_other[bcell] = bother

        # every cell: its nearest boundary cell on its own plate
        near = np.full(n, -1, dtype=np.int64)
        dist = np.full(n, np.pi * radius)
        for p in range(k):
            mine = np.flatnonzero(plate == p)
            bp = mine[is_boundary[mine]]
            if bp.size:
                d, idx = cKDTree(mesh.xyz[bp]).query(mesh.xyz[mine])
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
                d, idx = cKDTree(mesh.xyz[rp]).query(mesh.xyz[mine])
                half = np.maximum(-b_close[rp[idx]] / 2, a["minimum_half_rate_m_per_year"])
                age[mine] = np.minimum(_arc(d) * radius / half / YEARS_PER_MY, a["maximum_my"])

        # at a trench the oceanic side dives; between two ocean floors the older one dives
        partner = np.where(has, b_other[safe], 0)
        own_c, other_c = ctype[safe] == CONTINENTAL, ctype[partner] == CONTINENTAL
        own_age = np.where(np.isnan(age[safe]), 0.0, age[safe])
        other_age = np.where(np.isnan(age[partner]), 0.0, age[partner])
        older = (own_age > other_age) | ((own_age == other_age) & (plate[safe] > plate[partner]))
        diving = (kind_near == TRENCH) & (~own_c) & (other_c | older)
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
        # a mountain belt has no sharp ends: spread the thickening over a set length, inside continental crust
        if land.any():
            length = g["smoothing_km"] * M_PER_KM / radius
            mask = land.astype(np.float64)
            weight = op.smooth(mesh, mask, length, ctx.memo)
            thickening = np.where(land, op.smooth(mesh, thickening, length, ctx.memo) / np.maximum(weight, np.finfo(float).tiny), 0.0)
            thickening = np.maximum(thickening, 0.0)
        thickness = base + thickening
        orogeny = np.where(thickening > g["active_above_m"], 0.0, np.nan)

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

        # events: one row for each pair of plates and kind of meeting
        pa, pb = np.minimum(plate[ci], plate[cj]), np.maximum(plate[ci], plate[cj])
        code = np.select([e_kind == TRENCH, e_kind == COLLISION, e_kind == RIDGE], [EVENT_SUBDUCTION, EVENT_COLLISION, EVENT_SPREADING], 0)
        keep = code > 0
        key = (pa[keep] * k + pb[keep]) * EVENT_CODES + code[keep]
        uniq, counts = np.unique(key, return_counts=True)
        ev_kind, ev_pair = uniq % EVENT_CODES, uniq // EVENT_CODES
        ev_a, ev_b = ev_pair // k, ev_pair % k
        event_of_pair = {(int(x), int(y), int(q)): r for r, (x, y, q) in enumerate(zip(ev_a, ev_b, ev_kind))}
        event = np.full(n, -1, dtype=np.int32)
        for cell in np.flatnonzero(thickening > 0):
            p1, p2 = sorted((int(plate[safe[cell]]), int(plate[partner[cell]])))
            event[cell] = event_of_pair.get((p1, p2, EVENT_COLLISION if kind_near[cell] == COLLISION else EVENT_SUBDUCTION), -1)

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
