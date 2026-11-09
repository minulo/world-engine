"""SynopticStorms: single storms, on the weather clock (build step 8).

Model (Adapted; design, Layer 5). Synoptic means the scale of whole weather systems, about a thousand kilometres. Storm
births are drawn at random where and when the storm maps are high: mid-latitude storms in proportion to the track
density of StormClimatology, tropical cyclones in proportion to its genesis potential, each map's month against its
year, so that a stated number a day on the year's mean comes more often in the stormy season. Tropical cyclones follow the
beta-and-advection model: the steering wind plus a steady drift caused by the planet's spin, toward the pole and the
west [DOCUMENTED in the design: Emanuel et al. 2006; the engine has one steering wind, not the two heights of the model;
the size of the drift is UNVERIFIED]. Mid-latitude storms follow the steering wind alone (the design's extension). A
mid-latitude storm grows and fades over a set life; a tropical cyclone holds the strength its sea allows and fades over
land and cold water [INFERRED].
Weather keeps no state (design, Layer 3): the storms alive on a day are found by drawing again the births of the days
of a look-back window, each keyed by its own date, and following each track forward day by day. No storm lives longer
than the window, so any day comes out the same however it is reached.

When a day is recomputed for a "why" answer, the process records what made each cell's influence: the part that
mid-latitude storms give and the part that tropical cyclones give (with the cell each kind's strongest storm there was
born in, where the storm maps decided its birth), what the cap on overlapping storms takes, and the row of the table of
storms that gives the most. The three parts add up to the influence. A storm is said to reach a cell within twice its
radius, where its influence is e^-4 of its strength, about 2 % [a choice of wording for the answers, not a part of the
model], and a cyclone that has lost all its strength reaches none; a cell no storm reaches is said to have none worth
naming. The record changes nothing that the process writes.

Ignores: storms acting on each other, and weather fronts.
Wrong where: each path is a plausible sample, not a prediction; counts are those of the maps, which are not counts.
"""
import numpy as np

from ..library import days as dy
from ..library import operators as op
from ..library.units import M_PER_KM, SECONDS_PER_DAY, ZERO_CELSIUS_IN_K
from ..process import Process

MIDLATITUDE, TROPICAL = 1, 2
NOT_REACHED, REACHED = 0, 1             # the classes of the driver `reached`
REACH_IN_RADII = 2                       # a storm reaches the cells within this many of its radii (the answers' wording)


class StormTracks(Process):
    stage = "weather"
    reads = ("storm_track_density", "tc_genesis_potential", "potential_intensity", "steering_wind", "ocean_mask",
             "surface_temperature", "coriolis_parameter", "cell_area")
    writes = ("storm_influence", "table:storms")
    draws = ("midlatitude_births", "tropical_births")
    shared = ("weather_look_back_days",)
    model = "storms born where the storm maps are high, carried by the steering wind (tropical cyclones: beta-and-advection, Emanuel et al. 2006)"
    drivers = {"storm_influence": ("from_midlatitude_storms", "from_tropical_cyclones", "above_the_cap", "midlatitude_born_at",
                                   "tropical_born_at", "strongest_storm", "reached")}
    additive = ("storm_influence",)

    def run(self, ctx):
        c, mesh = ctx.const, ctx.mesh
        radius, day, window = ctx.planet["radius_m"], int(ctx.round), int(ctx.shared["weather_look_back_days"])
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        density = ctx.read("storm_track_density").astype(np.float64)
        genesis = ctx.read("tc_genesis_potential").astype(np.float64)
        intensity = ctx.read("potential_intensity").astype(np.float64)
        steer = ctx.read("steering_wind").astype(np.float64)
        t = ctx.read("surface_temperature").astype(np.float64)
        f = ctx.read("coriolis_parameter").astype(np.float64)
        area = ctx.read("cell_area").astype(np.float64)
        tree_memo = ctx.memo
        # births follow the maps in place and in season: the stated number a day is the mean over the year
        kinds = ((MIDLATITUDE, "midlatitude_births", np.maximum(density, 0.0) * area, c["midlatitude_births_per_day"]),
                 (TROPICAL, "tropical_births", np.maximum(genesis, 0.0) * area, c["tropical_births_per_day"]))
        storms = []                                                    # kind, born, birth cell, position
        for born in range(day - window + 1, day + 1):
            m = dy.month_weights(born, ctx.planet, ctx.months)[0]
            for kind, purpose, weight, per_day in kinds:
                year_mean = weight.sum(axis=1).mean()
                if year_mean <= 0:
                    continue
                chance = per_day * weight[m] / year_mean
                cells = np.flatnonzero(ctx.draw.on(born).uniform(purpose, mesh.n) < chance)
                storms += [(kind, born, int(i), mesh.xyz[i].copy()) for i in cells]
        rows = []
        influence = np.zeros(mesh.n)
        part = {MIDLATITUDE: np.zeros(mesh.n), TROPICAL: np.zeros(mesh.n)}          # the cause record: each kind's share,
        best = {MIDLATITUDE: np.zeros(mesh.n), TROPICAL: np.zeros(mesh.n)}          # its strongest storm's reach in each cell,
        born_at = {MIDLATITUDE: np.full(mesh.n, -1), TROPICAL: np.full(mesh.n, -1)}  # and the cell that storm was born in
        strongest, strongest_reach, reached = np.full(mesh.n, -1), np.zeros(mesh.n), np.zeros(mesh.n, dtype=bool)
        for k, (kind, born, birth_cell, pos) in enumerate(storms):
            strength = 1.0
            for step_day in range(born, day):                          # one day's move at a time, the wind of that day's month
                cell = int(op.nearest_cell(mesh, pos[None, :], tree_memo)[0])
                m = dy.month_weights(step_day, ctx.planet, ctx.months)[0]
                move = steer[m, cell].copy()
                if kind == TROPICAL:                                   # the beta drift: toward the pole and the west
                    toward_pole = np.sign(f[cell]) * mesh.north[cell]
                    move += c["beta_drift_m_s"] * (c["beta_poleward_share"] * toward_pole - (1 - c["beta_poleward_share"]) * mesh.east[cell])
                    warm = sea[cell] and t[m, cell] - ZERO_CELSIUS_IN_K >= c["tropical_needs_sea_c"]
                    strength *= 1.0 if warm else c["tropical_daily_decay"]
                pos = pos + move * SECONDS_PER_DAY / radius
                pos /= np.linalg.norm(pos)
            age = day - born
            if kind == MIDLATITUDE:
                strength = np.sin(np.pi * (age + 0.5) / window)
                size = c["midlatitude_radius_km"]
            else:
                cell = int(op.nearest_cell(mesh, pos[None, :], tree_memo)[0])
                m = dy.month_weights(day, ctx.planet, ctx.months)[0]
                strength *= min(1.0, intensity[m, cell] / c["tropical_reference_intensity_m_s"]) if sea[cell] else c["tropical_daily_decay"]
                size = c["tropical_radius_km"]
            distance = np.arccos(np.clip(mesh.xyz @ pos, -1.0, 1.0)) * radius / M_PER_KM
            reach = strength * np.exp(-(distance / size) ** 2)
            influence += reach
            if ctx.recording:
                part[kind] += reach
                more = reach > best[kind]
                best[kind] = np.where(more, reach, best[kind])
                born_at[kind] = np.where(more, birth_cell, born_at[kind])
                more = reach > strongest_reach
                strongest_reach = np.where(more, reach, strongest_reach)
                strongest = np.where(more, k, strongest)
                if strength > 0.0:                                     # a cyclone that has lost all its strength reaches nothing
                    reached |= distance <= REACH_IN_RADII * size
            lat = float(np.rad2deg(np.arcsin(np.clip(pos[2], -1, 1))))
            lon = float(np.rad2deg(np.arctan2(pos[1], pos[0])))
            rows.append((kind, born, lat, lon, strength))
        order = sorted(range(len(rows)), key=lambda k: (rows[k][1], rows[k][0], rows[k][2], rows[k][3]))     # a fixed order
        rows = [rows[k] for k in order]
        capped = np.clip(influence, 0.0, c["influence_cap"])
        ctx.write("storm_influence", capped)
        if ctx.recording:
            row_of = np.full(len(order) + 1, -1)                       # a storm's place in the stored table; the last
                                                                       # entry, -1, is that of `strongest` where no storm is
            row_of[np.asarray(order, dtype=np.int64)] = np.arange(len(order))
            ctx.driver("storm_influence", "from_midlatitude_storms", part[MIDLATITUDE])
            ctx.driver("storm_influence", "from_tropical_cyclones", part[TROPICAL])
            ctx.driver("storm_influence", "above_the_cap", capped - influence)
            ctx.driver("storm_influence", "midlatitude_born_at", np.where(reached, born_at[MIDLATITUDE], -1))
            ctx.driver("storm_influence", "tropical_born_at", np.where(reached, born_at[TROPICAL], -1))
            ctx.driver("storm_influence", "strongest_storm", np.where(reached, row_of[strongest], -1))
            ctx.driver("storm_influence", "reached", np.where(reached, REACHED, NOT_REACHED))
        ctx.write_table("table:storms", {"kind": [r[0] for r in rows], "born_day": [r[1] for r in rows],
                                         "lat": [r[2] for r in rows], "lon": [r[3] for r in rows],
                                         "strength": [r[4] for r in rows]})
