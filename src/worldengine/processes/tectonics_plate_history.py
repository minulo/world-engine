"""Tectonics, second version: a history of moving plates (build step 3).

Model (Adapted): the plate model of Cortial et al. 2019, "Procedural Tectonic Planets", with the design's two
changes and one addition (design, Layer 5). Rigid plates turn about axes through the planet's centre. The crust
rides on crust points, about one per cell, which turn with their plates. Every round of 2 My:
  1. each point is thinned by what erosion took from its cell in the round before (the group
     crust_thickness_tendency), before it moves;
  2. the points turn with their plates; the ocean floor and mountain belts grow older;
  3. where two plates overlap, one dives under the other. Ocean floor dives under a continent; of two ocean
     floors, the older plate dives along the whole of their shared front. A diving point is consumed (subduction).
     Where two continents overlap, the continent of the plate with less continental crust goes under: its points
     are consumed and their crust is piled onto the other continent near the front (collision), so no continental
     rock is lost. A collision that has gone on for a set number of rounds welds the terrane, the continent of the
     lower plate that touches the front, to the upper plate;
  4. each cell takes the crust of its nearest point. A cell with no point near it lies in a gap where plates part:
     it gets a new point of ocean floor of age zero on the nearer plate (spreading);
  5. behind each trench the overriding crust thickens by the paper's uplift divided by the share of added
     thickness that becomes height (the design's first change: the rules thicken the crust, Isostasy lifts it).
     Ocean crust thickened past a set thickness becomes continental crust: an island arc that has grown;
  6. a plate may split, by seeded draws, with the paper's chance P = L exp(-L), into 2 to 4 parts along warped
     lines; the parts move apart (rifting). Slab pull turns each plate's motion toward the fronts where it dives;
  7. every few rounds the points are replaced by one fresh point per cell, each filled from the three old points of
     its plate around it with weights that give back exactly a value that changes evenly; the table of crust points
     records those three and their weights (in other rounds: the one point each row came from), so that SurfaceAge
     can carry its own values across.

Addition (a departure from the design): crust thicker than a set thickness flows sideways under its own weight, by
one diffusion step a round that keeps its volume. Without it, collision fronts piled single columns to the cap.
Ignores: the paper's own erosion, ocean-floor height and trench sediment (replaced by FluvialErosion and Isostasy);
hot spots, plumes and flood basalts; the true shape of a subducting slab; deposition of eroded rock; the sinking of
old floor under its own weight before it meets a trench. Mantle convection is not modelled: plates keep their
motion except for slab pull and rifting.
Wrong where: the size of the thickening and the chance of rifting are tuned numbers; welding is all or nothing;
fronts are as rough as the mesh. Mountain belts form only where continents close or ocean dives.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from ..library import operators as op
from ..library.noise import WAVE_NUMBERS, wave_field
from ..library.plates import (CONTINENTAL, OCEANIC, NONE, RIDGE, TRENCH, COLLISION, TRANSFORM, EVENT_SUBDUCTION,
                              EVENT_COLLISION, EVENT_SPREADING, _arc, _nearest, boundaries, diving, seeded_start)
from ..library.units import M_PER_KM, YEARS_PER_MY
from ..process import Process

EVENT_SPLIT = 3


def rotate(pos, axis, angle):
    """Turn each position about its own axis by its own angle (Rodrigues' formula)."""
    c, s = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return pos * c + np.cross(axis, pos) * s + axis * np.einsum("ij,ij->i", axis, pos)[:, None] * (1 - c)


def _unit(v):
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(norm, np.finfo(float).tiny)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class PlateHistory(Process):
    stage = "geological"
    reads = ("cell_area",)
    reads_lagged = ("table:crust_points", "table:plates", "table:tectonic_events")
    writes = ("plate_id", "plate_velocity", "crust_type", "crust_thickness", "ocean_crust_age", "orogeny_age",
              "boundary_kind", "boundary_distance", "convergence_rate", "volcanism",
              "table:crust_points", "table:plates", "table:tectonic_events")
    reads_groups_lagged = ("crust_thickness_tendency",)
    has_start = True
    draws = ("plate_centres", "plate_axes", "plate_speeds", "outline_waves", "continent_plates", "continent_waves",
             "thickness_waves", "rift_chance", "rift_parts", "rift_centres", "rift_waves", "rift_speeds")
    model = "a history of moving plates, after Cortial et al. 2019"
    drivers = {"crust_thickness": ("formed_thickness", "thickened_by_plates", "removed_by_erosion", "event"),
               "plate_id": ("history",)}
    additive = ("crust_thickness",)

    # ------------------------------------------------------------------ the seeded start
    def start(self, ctx):
        seeded_start(ctx)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _initial_ages(c, mesh, plate, ctype, rotation, radius, k):
        """The ocean floor of the seeded start has no history yet: its age is read off the distance to its plate's
        nearest spreading ridge at half the opening speed there, as the snapshot does, capped at the oldest age."""
        is_b, facing, faces_cont, b_kind, b_close = boundaries(mesh, plate, ctype, rotation, radius, k, c["boundaries"])
        a = c["ocean_age"]
        ocean = ctype == OCEANIC
        age = np.where(ocean, a["maximum_my"], np.nan)
        for p in range(k):
            mine = np.flatnonzero((plate == p) & ocean)
            rp = np.flatnonzero((plate == p) & is_b & (b_kind == RIDGE))
            if mine.size and rp.size:
                d, idx = _nearest(mesh.xyz[rp], mesh.xyz[mine], -b_close[rp], b_kind[rp])
                half = np.maximum(-b_close[rp[idx]] / 2, a["minimum_half_rate_m_per_year"])
                age[mine] = np.minimum(_arc(d) * radius / half / YEARS_PER_MY, a["maximum_my"])
        return age

    # ------------------------------------------------------------------ one round
    def run(self, ctx):
        c, mesh, n = ctx.const, ctx.mesh, ctx.mesh.n
        h = c["history"]
        dt = float(ctx.step_length)
        radius = ctx.planet["radius_m"]
        spacing = mesh.spacing()
        area_m2 = ctx.read("cell_area").astype(np.float64)
        pts, plates, events = (ctx.read_lagged("table:crust_points"), ctx.read_lagged("table:plates"),
                               ctx.read_lagged("table:tectonic_events"))
        tendency = ctx.read_group_lagged("crust_thickness_tendency").total
        now = ctx.round * dt

        pos = np.stack([pts["x"], pts["y"], pts["z"]], axis=1).astype(np.float64)
        plate = pts["plate"].astype(np.int64)
        ctype = pts["crust_type"].astype(np.int16)
        thick = pts["thickness_m"].astype(np.float64)
        oage = pts["ocean_age_my"].astype(np.float64)
        orog = pts["orogeny_age_my"].astype(np.float64)
        tbp = pts["thickened_by_plates_m"].astype(np.float64)
        rbe = pts["removed_by_erosion_m"].astype(np.float64)
        formed = pts["formed_m"].astype(np.float64)
        last_event = pts["last_event"].astype(np.int64)
        row = np.arange(pos.shape[0])                                 # the row of last round's table each point came from

        k = plates["plate"].size
        axis = np.stack([plates["axis_x"], plates["axis_y"], plates["axis_z"]], axis=1).astype(np.float64)
        omega = plates["angular_speed_rad_per_my"].astype(np.float64)
        w = axis * omega[:, None]                                      # rotation vector, radians per My
        cont_area = plates["area_m2"] * plates["continental_share"]
        event_rows = {key: list(np.asarray(events[key])) for key in events}
        first_new_event = len(event_rows["kind"])

        def add_event(kind, a, b, cells):
            event_rows["time_my"].append(now)
            event_rows["kind"].append(kind)
            event_rows["plate_a"].append(a)
            event_rows["plate_b"].append(b)
            event_rows["cells"].append(cells)
            return len(event_rows["kind"]) - 1

        if ctx.round == 1 and np.isnan(oage[ctype == OCEANIC]).any():      # the seeded start: one point per cell
            oage = np.where(ctype == OCEANIC, self._initial_ages(c, mesh, plate.astype(np.int32), ctype,
                                                                 w / YEARS_PER_MY, radius, k), np.nan)

        # 1. erosion of the round before thins each point, before it moves
        here = op.nearest_cell(mesh, pos, ctx.memo)
        change = tendency[here].astype(np.float64)
        floor = np.minimum(thick, h["minimum_thickness_m"])
        new_thick = np.maximum(thick + change, floor)
        rbe = rbe + np.maximum(thick - new_thick, 0.0)
        thick = new_thick

        # 2. the points turn with their plates
        pos = _unit(rotate(pos, _unit(axis)[plate], omega[plate] * dt))
        oage = oage + dt
        orog = orog + dt

        # 3. overlaps: subduction and collision
        contact = h["contact_cells"] * spacing
        pairs = cKDTree(pos).query_pairs(contact, output_type="ndarray")
        gone = np.zeros(pos.shape[0], dtype=bool)
        piled = np.zeros(pos.shape[0])
        weld_pairs = []
        if pairs.size:
            a, b = pairs[:, 0], pairs[:, 1]
            cross = plate[a] != plate[b]
            a, b = a[cross], b[cross]
            ca, cb = ctype[a] == CONTINENTAL, ctype[b] == CONTINENTAL
            lo, hi = np.minimum(plate[a], plate[b]), np.maximum(plate[a], plate[b])
            key = lo * k + hi
            # of two ocean floors the older plate dives along the whole of their front
            ocean_pair = ~ca & ~cb
            age_a = np.where(np.isnan(oage[a]), 0.0, oage[a])
            age_b = np.where(np.isnan(oage[b]), 0.0, oage[b])
            age_lo = np.where(plate[a] == lo, age_a, age_b)
            age_hi = np.where(plate[a] == lo, age_b, age_a)
            s_lo = np.bincount(key[ocean_pair], weights=age_lo[ocean_pair], minlength=k * k)
            s_hi = np.bincount(key[ocean_pair], weights=age_hi[ocean_pair], minlength=k * k)
            lo_dives = (s_lo > s_hi + h["equal_age_my"]) | ((np.abs(s_lo - s_hi) <= h["equal_age_my"]))   # equal: the lower number dives
            # of two continents the plate with less continental crust goes under
            lo_under = cont_area[lo] <= cont_area[hi]                     # equal: the lower number goes under
            a_under = np.where(ca & ~cb, False, np.where(~ca & cb, True,
                               np.where(ocean_pair, np.where(plate[a] == lo, lo_dives[key], ~lo_dives[key]),
                                        np.where(plate[a] == lo, lo_under, ~lo_under))))
            under, top = np.where(a_under, a, b), np.where(a_under, b, a)
            gone[under] = True
            collide = (ctype[under] == CONTINENTAL) & (ctype[top] == CONTINENTAL)
            # the crust of a consumed continent is piled onto the upper continent near the front
            cu = np.unique(under[collide])
            if cu.size:
                top_ok = (ctype == CONTINENTAL) & ~gone
                receivers = np.flatnonzero(top_ok)
                reach = h["collision_spread_km"] * M_PER_KM / radius
                found = cKDTree(pos[cu]).sparse_distance_matrix(cKDTree(pos[receivers]), reach, output_type="coo_matrix")
                same_side = plate[receivers[found.col]] != plate[cu[found.row]]
                r_, c_, d_ = found.row[same_side], found.col[same_side], found.data[same_side]
                wgt = (1 - (d_ / reach) ** 2) ** 2
                total = np.bincount(r_, weights=wgt, minlength=cu.size)
                volume = thick[cu] * area_m2[here[cu]]
                share = wgt * (volume[r_] / np.maximum(total[r_], np.finfo(float).tiny))
                piled_volume = np.bincount(c_, weights=share, minlength=receivers.size)
                piled[receivers] = piled_volume / area_m2[here[receivers]]
            # events: one row per pair of plates and kind
            pk_all = np.minimum(plate[under], plate[top]) * k + np.maximum(plate[under], plate[top])
            for kind, mask in ((EVENT_SUBDUCTION, ~collide), (EVENT_COLLISION, collide)):
                for pk_ in np.unique(pk_all[mask]):
                    sel = mask & (pk_all == pk_)
                    rid = add_event(kind, int(pk_ // k), int(pk_ % k), int(np.unique(under[sel]).size))
                    if kind == EVENT_COLLISION:
                        u_pl, t_pl = int(plate[under[sel]][0]), int(plate[top[sel]][0])
                        weld_pairs.append((u_pl, t_pl, rid))
                        last_event[(piled > 0) & (plate == t_pl)] = rid
                    else:
                        last_event[np.unique(top[sel])] = rid
        consumed_pos = pos[gone]
        consumed_plate = plate[gone]
        piled_thick = np.minimum(thick + piled, np.maximum(thick, h["maximum_thickness_m"]))
        tbp, thick = tbp + (piled_thick - thick), piled_thick
        orog = np.where(piled > h["active_above_m_per_round"], 0.0, orog)
        keep = ~gone
        pos, plate, ctype, thick, oage, orog, tbp, rbe, formed, last_event, row = (
            pos[keep], plate[keep], ctype[keep], thick[keep], oage[keep], orog[keep], tbp[keep], rbe[keep], formed[keep],
            last_event[keep], row[keep])

        # 4. draw the crust onto the mesh; a cell with no point near it lies in a gap where plates part
        d, near = _nearest(pos, mesh.xyz, ctype.astype(np.float64), thick)
        gap = np.flatnonzero(d > h["gap_cells"] * spacing)
        if gap.size:
            on = plate[near[gap]]
            start_at = pos.shape[0]
            pos = np.concatenate([pos, mesh.xyz[gap]])
            plate = np.concatenate([plate, on])
            ctype = np.concatenate([ctype, np.full(gap.size, OCEANIC, dtype=np.int16)])
            oceanic = c["thickness"]["oceanic_m"]
            thick = np.concatenate([thick, np.full(gap.size, oceanic)])
            oage = np.concatenate([oage, np.zeros(gap.size)])
            orog = np.concatenate([orog, np.full(gap.size, np.nan)])
            tbp = np.concatenate([tbp, np.zeros(gap.size)])
            rbe = np.concatenate([rbe, np.zeros(gap.size)])
            formed = np.concatenate([formed, np.full(gap.size, oceanic)])
            last_event = np.concatenate([last_event, np.full(gap.size, -1)])
            row = np.concatenate([row, np.full(gap.size, -1)])
            near[gap] = np.arange(start_at, pos.shape[0])
        new_floor = np.zeros(n, dtype=bool)
        new_floor[gap] = True

        # 6a. welding: a collision that has gone on long enough joins the lower continent to the upper plate
        plate_c = plate[near]
        ctype_c = ctype[near]
        if weld_pairs:
            past = np.asarray(event_rows["time_my"][:first_new_event])
            kinds = np.asarray(event_rows["kind"][:first_new_event])
            pa, pb = np.asarray(event_rows["plate_a"][:first_new_event]), np.asarray(event_rows["plate_b"][:first_new_event])
            window = int(h["weld_after_rounds"])
            for u_pl, t_pl, rid in weld_pairs:
                lo, hi = min(u_pl, t_pl), max(u_pl, t_pl)
                times = past[(kinds == EVENT_COLLISION) & (pa == lo) & (pb == hi) & (past > now - window * dt - 1e-9)]
                if np.unique(np.round(times / dt)).size + 1 < window:
                    continue
                cells = (plate_c == u_pl) & (ctype_c == CONTINENTAL)
                if not cells.any():
                    continue
                i, j = mesh.edge_cells[:, 0], mesh.edge_cells[:, 1]
                both = cells[i] & cells[j]
                graph = coo_matrix((np.ones(both.sum()), (i[both], j[both])), shape=(n, n))
                _, comp = connected_components(graph, directed=False)
                lost_here = consumed_pos[consumed_plate == u_pl]
                if not lost_here.size:
                    continue
                front_cells = np.flatnonzero(cells)
                dd, _ = cKDTree(lost_here).query(mesh.xyz[front_cells])
                touching = front_cells[dd <= h["weld_reach_cells"] * spacing]
                terrane = cells & np.isin(comp, np.unique(comp[touching]))
                moved = (plate == u_pl) & (ctype == CONTINENTAL) & terrane[op.nearest_cell(mesh, pos, ctx.memo)]
                if moved.any():
                    plate[moved] = t_pl
                    add_event(EVENT_COLLISION, lo, hi, int(moved.sum()))
            plate_c = plate[near]

        # 5. thickening behind trenches (subduction uplift of the paper, as thickness)
        rotation = w / YEARS_PER_MY                                        # radians per year
        k = w.shape[0]
        thick_c, oage_c = thick[near], oage[near]
        is_b, facing, faces_cont, b_kind, b_close = boundaries(mesh, plate_c.astype(np.int32), ctype_c, rotation, radius, k,
                                                               c["boundaries"])
        ocean_c = ctype_c == OCEANIC
        age_c = np.where(np.isnan(oage_c), 0.0, oage_c)
        b_dive = diving(plate_c, facing, faces_cont, b_kind, ocean_c, age_c, k, c["ocean_age"]["equal_within_my"])
        front = is_b & (b_kind == TRENCH) & ~b_dive
        s = c["subduction"]
        # the height of the diving floor next to each front cell: from its age, between ridge and abyssal plain
        nb = mesh.nbr
        valid = nb >= 0
        safe = np.where(valid, nb, 0)
        across = valid & (plate_c[safe] == facing[:, None]) & ocean_c[safe]
        dive_age = np.where(across, age_c[safe], 0.0).sum(axis=1) / np.maximum(across.sum(axis=1), 1)
        fh = s["floor_height"]
        z = fh["ridge_m"] + (fh["abyssal_m"] - fh["ridge_m"]) * np.clip(dive_age / fh["abyssal_age_my"], 0, 1)
        z = np.where(across.any(axis=1), z, fh["abyssal_m"])
        hz = ((z - s["lowest_m"]) / (s["highest_m"] - s["lowest_m"])) ** 2
        gv = np.clip(b_close / s["reference_speed_m_per_year"], 0.0, s["maximum_speed_factor"])
        strength = np.where(front, gv * hz, 0.0)
        uplift = np.zeros(n)
        dist_front = np.full(n, np.inf)
        reach_m, peak_m = s["reach_km"] * M_PER_KM, s["peak_km"] * M_PER_KM
        for p in np.unique(plate_c[front]):
            mine = np.flatnonzero(plate_c == p)
            fp = np.flatnonzero(front & (plate_c == p))
            dd, idx = _nearest(mesh.xyz[fp], mesh.xyz[mine], strength[fp], b_close[fp])
            dm = _arc(dd) * radius
            f = np.where(dm <= peak_m, _smoothstep(dm / peak_m), 1 - _smoothstep((dm - peak_m) / (reach_m - peak_m)))
            uplift[mine] = s["uplift_m_per_my"] * dt * f * strength[fp[idx]]
            dist_front[mine] = dm
        thickening_c = uplift / s["height_share_of_thickening"]
        cell_now = op.nearest_cell(mesh, pos, ctx.memo)
        add = np.where(plate == plate_c[cell_now], thickening_c[cell_now], 0.0)
        capped = np.minimum(thick + add, np.maximum(thick, h["maximum_thickness_m"]))
        add = capped - thick
        thick, tbp = capped, tbp + add
        orog = np.where(add > h["active_above_m_per_round"], 0.0, orog)
        # which trench made it: the event row of the subduction between the plate and the one it overrides
        sub_rows = {}
        for r_ in range(first_new_event, len(event_rows["kind"])):
            if event_rows["kind"][r_] == EVENT_SUBDUCTION:
                sub_rows[(event_rows["plate_a"][r_], event_rows["plate_b"][r_])] = r_
        if (add > 0).any():
            fc = np.flatnonzero(front)
            if fc.size:
                nearest_front = fc[cKDTree(mesh.xyz[fc]).query(pos[add > 0])[1]]
                pa_, pb_ = plate_c[nearest_front], facing[nearest_front]
                rows_ = np.array([sub_rows.get((int(min(x, y)), int(max(x, y))), -1) for x, y in zip(pa_, pb_)], dtype=np.int64)
                last_event[add > 0] = np.where(rows_ >= 0, rows_, last_event[add > 0])
        # crust thicker than a set thickness flows sideways under its own weight (the collapse of thick mountain belts):
        # its excess is spread by one implicit diffusion step, which keeps its volume
        fl = h["crust_flow"]
        excess = np.maximum(thick[near] - fl["above_m"], 0.0)
        if excess.any():
            spread = op.smooth(mesh, excess, fl["length_km"] * M_PER_KM / radius, ctx.memo)
            flow = (spread - excess)[cell_now]
            thick, tbp = np.maximum(thick + flow, h["minimum_thickness_m"]), tbp + np.maximum(thick + flow, h["minimum_thickness_m"]) - thick
        # an island arc that has grown thick enough is continental crust
        grown = (ctype == OCEANIC) & (thick > h["arc_becomes_continental_above_m"])
        ctype = np.where(grown, CONTINENTAL, ctype).astype(np.int16)
        oage = np.where(grown, np.nan, oage)
        orog = np.where(grown, 0.0, orog)

        # 6b. rifting: a plate may split, by seeded draws (the paper's P = L exp(-L))
        r = c["rifting"]
        plate_area = np.bincount(plate[near], weights=area_m2, minlength=k)
        cont_share = np.bincount(plate[near], weights=area_m2 * (ctype[near] == CONTINENTAL), minlength=k) / np.maximum(plate_area, 1.0)
        mean_area = 4 * np.pi * radius ** 2 / int(c["plates"])
        lam = r["rate_per_round"] * (1 + r["continent_weight"] * cont_share) * plate_area / mean_area
        chance = lam * np.exp(-lam)
        draw = ctx.draw.uniform("rift_chance", k)
        splitting = np.flatnonzero((draw < chance) & (plate_area > r["smallest_share_of_mean"] * mean_area))
        if splitting.size > int(r["most_per_round"]):
            splitting = splitting[np.argsort(draw[splitting] / chance[splitting], kind="stable")[: int(r["most_per_round"])]]
            splitting.sort()
        parts_draw = ctx.draw.uniform("rift_parts", max(1, splitting.size))
        centres_draw = ctx.draw.uniform("rift_centres", max(1, splitting.size) * 4)
        speed_draw = ctx.draw.uniform("rift_speeds", max(1, splitting.size) * 4)
        u_waves = ctx.draw.uniform("rift_waves", 3 * WAVE_NUMBERS * int(r["waves"]))
        new_axes, new_speeds = [], []
        for si, p in enumerate(splitting):
            members = np.flatnonzero(plate == p)
            parts = 2 + int(parts_draw[si] * 3)
            parts = min(parts, 4)
            cells_p = np.flatnonzero(plate[near] == p)
            centres = mesh.xyz[cells_p[(centres_draw[si * 4: si * 4 + parts] * cells_p.size).astype(np.int64)]]
            if np.unique(centres, axis=0).shape[0] < parts:
                continue
            u3 = u_waves.reshape(3, -1)
            shift = np.stack([wave_field(pos[members], u3[i], r["wave_number"]) for i in range(3)], axis=1)
            warped = _unit(pos[members] + r["warp_rad"] * shift)
            part = cKDTree(centres).query(warped)[1]
            centroid = _unit(pos[members].mean(axis=0))
            lo_s, hi_s = r["parting_speed_cm_per_year"]
            if np.unique(part).size < parts:                         # a part that holds no point: no split
                continue
            for q in range(1, parts):
                new_id = k + len(new_axes)
                plate[members[part == q]] = new_id
                cq = _unit(pos[members[part == q]].mean(axis=0))
                away = _unit(np.cross(centroid, cq))
                speed = (lo_s + (hi_s - lo_s) * speed_draw[si * 4 + q]) / 100.0 / radius * YEARS_PER_MY
                new_axes.append(w[p] + speed * away)
            c0 = _unit(pos[members[part == 0]].mean(axis=0))
            speed = (lo_s + (hi_s - lo_s) * speed_draw[si * 4]) / 100.0 / radius * YEARS_PER_MY
            w[p] = w[p] + speed * _unit(np.cross(centroid, c0))
            add_event(EVENT_SPLIT, int(p), int(k + len(new_axes) - 1), int(members.size))
        if new_axes:
            w = np.concatenate([w, np.asarray(new_axes)])
            k = w.shape[0]

        # 6c. slab pull: each plate's motion turns toward the fronts where it dives
        sp_ = c["slab_pull"]
        dive_cells = np.flatnonzero(is_b & b_dive)
        centre = np.zeros((k, 3))
        np.add.at(centre, plate[near], mesh.xyz * mesh.area[:, None])
        centre = _unit(centre)
        if dive_cells.size:
            pl = plate[near[dive_cells]]
            pull = np.zeros((k, 3))
            np.add.at(pull, pl, _unit(np.cross(centre[pl], mesh.xyz[dive_cells])))
            has = np.linalg.norm(pull, axis=1) > 0
            size = np.linalg.norm(w, axis=1)
            share = min(1.0, sp_["turn_share_per_my"] * dt)
            turned = (1 - share) * w + share * size[:, None] * _unit(pull)
            w = np.where(has[:, None], _unit(turned) * size[:, None], w)
        top_speed = sp_["fastest_cm_per_year"] / 100.0 / radius * YEARS_PER_MY
        size = np.linalg.norm(w, axis=1)
        w = w * (np.minimum(size, top_speed) / np.maximum(size, np.finfo(float).tiny))[:, None]

        # 7. resampling: a fresh even set of points, each filled from the three old points of its plate around it
        none = np.full(row.size, -1)
        srcs = np.stack([row, none, none], axis=1)                      # -1: a point that was not there last round
        wts = np.stack([(row >= 0).astype(np.float64), np.zeros(row.size), np.zeros(row.size)], axis=1)
        if ctx.round % int(h["resample_every_rounds"]) == 0:
            d3, i3 = cKDTree(pos).query(mesh.xyz, k=3)
            places = np.transpose(pos[i3], (0, 2, 1))
            flat = np.abs(np.linalg.det(places)) < h["flat_determinant"]
            places[flat] = np.eye(3)
            bary = np.clip(np.linalg.solve(places, mesh.xyz[:, :, None])[:, :, 0], 0.0, None)
            bary[flat] = 1.0 / np.maximum(d3[flat], 1e-12)
            bary *= plate[i3] == plate[near][:, None]
            alone = bary.sum(axis=1) <= 0
            bary[alone] = i3[alone] == near[alone][:, None]
            bary /= bary.sum(axis=1)[:, None]

            def mix(v):
                vv = v[i3]
                miss = np.isnan(vv)
                ww = np.where(miss, 0.0, bary)
                tot = ww.sum(axis=1)
                return np.where(tot > 0, (np.where(miss, 0.0, vv) * ww).sum(axis=1) / np.maximum(tot, 1e-300), np.nan)
            ctype_new = ctype[near]
            oage_new = np.where(ctype_new == OCEANIC, mix(oage), np.nan)
            oage_new = np.where((ctype_new == OCEANIC) & np.isnan(oage_new), 0.0, oage_new)
            orog_new = mix(orog)
            pos, plate, ctype = mesh.xyz.copy(), plate[near], ctype_new
            thick, tbp, rbe, formed = mix(thick), mix(tbp), mix(rbe), mix(formed)
            oage, orog = oage_new, orog_new
            last_event = last_event[near]
            srcs = np.where(bary > 0, row[i3], -1)
            wts = np.where(srcs >= 0, bary, 0.0)
            near = np.arange(n)

        # draw every field onto the mesh
        plate_c, ctype_c, thick_c = plate[near], ctype[near], thick[near]
        oage_c = np.where(ctype_c == OCEANIC, oage[near], np.nan)
        orog_c = orog[near]
        land = ctype_c == CONTINENTAL
        rotation = w / YEARS_PER_MY
        velocity = np.cross(rotation[plate_c], mesh.xyz) * radius
        is_b, facing, faces_cont, b_kind, b_close = boundaries(mesh, plate_c.astype(np.int32), ctype_c, rotation, radius, k,
                                                               c["boundaries"])
        age_c = np.where(np.isnan(oage_c), 0.0, oage_c)
        b_dive = diving(plate_c, facing, faces_cont, b_kind, ~land, age_c, k, c["ocean_age"]["equal_within_my"])
        near_b = np.full(n, -1, dtype=np.int64)
        dist = np.full(n, np.pi * radius)
        for p in np.unique(plate_c):
            mine = np.flatnonzero(plate_c == p)
            bp = mine[is_b[mine]]
            if bp.size:
                dd, idx = _nearest(mesh.xyz[bp], mesh.xyz[mine], b_close[bp], b_kind[bp])
                near_b[mine], dist[mine] = bp[idx], _arc(dd) * radius
        has = near_b >= 0
        sb = np.where(has, near_b, 0)
        kind_near = np.where(has, b_kind[sb], NONE)
        close_near = np.where(has, b_close[sb], 0.0)
        overriding = (kind_near == TRENCH) & ~np.where(has, b_dive[sb], False)
        g, z_, v = c["orogeny"], c["zones"], c["volcanism"]
        reach = np.select([kind_near == RIDGE, kind_near == TRENCH, kind_near == COLLISION, kind_near == TRANSFORM],
                          [z_["ridge_km"], g["subduction_width_km"], g["collision_width_km"], z_["transform_km"]], 0.0) * M_PER_KM
        kind = np.where(dist <= reach, kind_near, NONE).astype(np.int16)
        factor = np.clip(close_near / g["reference_speed_m_per_year"], 0.0, g["maximum_speed_factor"])
        arc = np.exp(-((dist - v["arc_distance_km"] * M_PER_KM) / (v["arc_width_km"] * M_PER_KM)) ** 2) * np.minimum(factor, 1.0)
        crest = np.exp(-(dist / (v["ridge_width_km"] * M_PER_KM)) ** 2)
        volcanism = np.where(overriding, arc, np.where(kind_near == RIDGE, crest, 0.0))

        ctx.write("plate_id", plate_c.astype(np.int32))
        ctx.write("plate_velocity", velocity)
        ctx.write("crust_type", ctype_c)
        ctx.write("crust_thickness", thick_c)
        ctx.write("ocean_crust_age", oage_c)
        ctx.write("orogeny_age", orog_c)
        ctx.write("boundary_kind", kind)
        ctx.write("boundary_distance", dist)
        ctx.write("convergence_rate", close_near)
        ctx.write("volcanism", volcanism)
        ctx.driver("crust_thickness", "formed_thickness", formed[near])
        ctx.driver("crust_thickness", "thickened_by_plates", tbp[near])
        ctx.driver("crust_thickness", "removed_by_erosion", -rbe[near])
        ctx.driver("crust_thickness", "event", last_event[near])
        ctx.driver("plate_id", "history", np.ones(n, dtype=np.int32))

        ctx.write_table("table:crust_points", {
            "plate": plate, "x": pos[:, 0], "y": pos[:, 1], "z": pos[:, 2], "crust_type": ctype,
            "thickness_m": thick, "ocean_age_my": oage, "orogeny_age_my": orog, "thickened_by_plates_m": tbp,
            "removed_by_erosion_m": rbe, "formed_m": formed, "last_event": last_event,
            "source_a": srcs[:, 0], "source_b": srcs[:, 1], "source_c": srcs[:, 2],
            "weight_a": wts[:, 0], "weight_b": wts[:, 1], "weight_c": wts[:, 2]})
        plate_area = np.bincount(plate_c, weights=area_m2, minlength=k)
        cont = np.bincount(plate_c, weights=area_m2 * land, minlength=k)
        centre = np.zeros((k, 3))
        np.add.at(centre, plate_c, mesh.xyz * mesh.area[:, None])
        centre = _unit(centre)
        size = np.linalg.norm(w, axis=1)
        ctx.write_table("table:plates", {
            "plate": np.arange(k), "axis_x": _unit(w)[:, 0], "axis_y": _unit(w)[:, 1], "axis_z": _unit(w)[:, 2],
            "angular_speed_rad_per_my": size, "area_m2": plate_area, "continental_share": cont / np.maximum(plate_area, 1.0),
            "carries_continent": cont > 0, "centre_x": centre[:, 0], "centre_y": centre[:, 1], "centre_z": centre[:, 2]})
        # spreading: one row per plate that grew new floor this round, with the plate it parted from
        if gap.size:
            fp = facing[gap]
            pp = plate_c[gap]
            key = np.minimum(pp, np.where(fp >= 0, fp, pp)) * (k + 1) + np.where(fp >= 0, np.maximum(pp, fp), k)
            for kk, cnt in zip(*np.unique(key, return_counts=True)):
                b_ = int(kk % (k + 1))
                add_event(EVENT_SPREADING, int(kk // (k + 1)), -1 if b_ == k else b_, int(cnt))
        ctx.write_table("table:tectonic_events", {key: np.asarray(v_) for key, v_ in event_rows.items()})
