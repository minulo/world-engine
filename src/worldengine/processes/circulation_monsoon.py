"""Circulation, second version: the belts of the first version, and a stand-in for the summer sinking of air west of hot
land (build step 5).

Model (Assembled). Everything of circulation_belts.py: the tropical overturning loop with its edge from the scaling of
Lu, Vecchi and Reichler 2007, pressure belts, warm surfaces lowering the pressure above them (Lindzen and Nigam 1987),
a balance of pressure, spin and drag for the surface wind, the thermal wind and the Eady growth rate.
Added in build step 5, as upgrades: (1) the rising branch of the loop follows the warmest latitude of each band of
longitude, near the thermal equator, and not only the warmest latitude around the whole planet: over a continent that
the summer heats it moves far toward the pole, and the pressure belts follow it, so that the wind of the tropics can
turn with the season (a monsoon trough) [INFERRED: the design's own extension, made per band of longitude]. (2) On Earth the summer descent over the subtropical deserts is tied to monsoon
heating to their east, which produces "a region of adiabatic descent" on its western side [DOCUMENTED in the design:
Rodwell and Hoskins 2001]. This version has no monsoon heating of its own; it stands in for it with the land of each
month that is warmer than the mean of its latitude, between two set latitudes: that warmth, smoothed, sets air sinking
at a set distance to its west, in proportion to it. Moisture then rains less there, as under any sinking air.

Ignores: single storms, the waves that mountain ranges raise in the flow, the turning aside of wind by high ground, the
rain that heats a real monsoon (the stand-in reads warmth, not rain). Stability and layer depth are constants.
Wrong where: the seasonal shift of the tropical rain belt, the strength of monsoons, storm paths downwind of great
ranges, the thermal wind near the equator. Where the warm land is itself a desert, its sinking air lies over the sea to
its west. Planets with high tilt, or spin rates far from Earth's, are beyond it until build step 10.
"""
import numpy as np

from ..library import operators as op
from ..library.units import M_PER_KM, SECONDS_PER_DAY, TWO_PI
from ..process import Process

NO_BRANCH, RISING, SINKING_NORTH, SINKING_SOUTH = 0, 1, 2, 3
POLE_DEG = 90.0
HALF_TURN = 180.0
TINY_DEG = 1.0e-6
SINKING_MARGIN_DEG = 10.0      # degrees beyond the heated band at which the reach is no longer widened toward the pole


def _soft_peak(x, score, sharpness):
    """Where the score is largest, as a weighted mean that moves smoothly when the score changes."""
    w = np.exp((score - score.max()) * sharpness)
    return float((x * w).sum() / w.sum())


def _belt_profile(lat, nodes, values):
    """A smooth curve through (node, value) pairs, flat at every node."""
    out = np.empty_like(lat)
    for a, b, va, vb in zip(nodes[:-1], nodes[1:], values[:-1], values[1:]):
        inside = (lat >= a) & (lat <= b)
        s = (lat[inside] - a) / (b - a)
        out[inside] = va + (vb - va) * (1 - np.cos(np.pi * s)) / 2
    return out


class SummerSinkingCirculation(Process):
    stage = "climate"
    reads = ("surface_temperature", "coriolis_parameter", "latitude", "height_above_sea", "ocean_mask", "cell_area")
    writes = ("sea_level_pressure", "wind", "steering_wind", "subsidence", "baroclinicity")
    shared = ("lapse_rate_k_per_km",)
    model = "pressure belts tied to the Hadley cell and to storm growth, warm-surface lows, a drag balance, and sinking air west of hot land"
    drivers = {"sea_level_pressure": ("mean_pressure", "belt_part", "warm_or_cold_surface_part"),
               "wind": ("from_belts", "from_surface_temperature"),
               "subsidence": ("branch", "west_of_hot_land")}
    additive = ("sea_level_pressure", "wind")

    def run(self, ctx):
        c, mesh, months = ctx.const, ctx.mesh, ctx.months
        p = ctx.planet
        radius, gravity = p["radius_m"], p["surface_gravity_m_s2"]
        spin = TWO_PI / p["rotation_period_s"]
        lat = ctx.read("latitude")
        f = ctx.read("coriolis_parameter")
        area = ctx.read("cell_area")
        height = np.maximum(ctx.read("height_above_sea").astype(np.float64), 0.0)
        land = ~np.asarray(ctx.read("ocean_mask"), dtype=bool)
        s = c["summer_sinking"]
        lo_lat, hi_lat = s["heating_latitudes_deg"]
        heated_band = land & (np.abs(lat) >= lo_lat) & (np.abs(lat) <= hi_lat)
        # the cell that lies the set distance east of each cell along its circle of latitude: its warmth sinks air here
        key = ("east of each cell", mesh.level, s["reach_km"], radius)
        if key not in ctx.memo:
            turn = s["reach_km"] * M_PER_KM / (radius * np.maximum(np.cos(np.deg2rad(lat)), np.cos(np.deg2rad(hi_lat + SINKING_MARGIN_DEG))))
            cos_t, sin_t = np.cos(turn), np.sin(turn)
            x, y = mesh.xyz[:, 0], mesh.xyz[:, 1]
            east_of = np.stack([x * cos_t - y * sin_t, x * sin_t + y * cos_t, mesh.xyz[:, 2]], axis=1)
            ctx.memo[key] = op.nearest_cell(mesh, east_of, ctx.memo)
        source_cell = ctx.memo[key]
        sink_extra = np.zeros((months, mesh.n))
        lon = np.rad2deg(np.arctan2(mesh.xyz[:, 1], mesh.xyz[:, 0]))
        sector_width = c["monsoon"]["sector_deg"]
        n_sectors = int(round(2 * HALF_TURN / sector_width))
        sector = np.minimum(((lon + HALF_TURN) / sector_width).astype(np.int64), n_sectors - 1)
        temp = ctx.read("surface_temperature").astype(np.float64) + ctx.shared["lapse_rate_k_per_km"] * height / M_PER_KM

        band = c["band_deg"]
        edge = float(np.clip(np.rad2deg(c["hadley_edge_factor"] * np.sqrt(c["stability_per_s"] * c["weather_layer_depth_m"] / (spin * radius))),
                             c["hadley_edge_limits_deg"][0], c["hadley_edge_limits_deg"][1]))
        b, o = c["belts"], c["overturning"]
        rho, drag = c["air_density_kg_m3"], c["drag_per_s"]
        warm_coefficient = rho * gravity * c["warm_layer_depth_m"] / (2 * c["reference_temperature_k"])   # Pa per kelvin
        f_floor = 2 * spin * np.sin(np.deg2rad(c["thermal_wind_floor_deg"]))
        f_safe = np.where(f >= 0, 1.0, -1.0) * np.maximum(np.abs(f), f_floor)
        smooth_length = c["warm_smoothing_km"] * M_PER_KM / radius

        shape = (months, mesh.n)
        pressure, belt_out, warm_out = np.zeros(shape), np.zeros(shape), np.zeros(shape)
        wind, wind_belt, wind_warm, steering = (np.zeros(shape + (3,)) for _ in range(4))
        subsidence, growth = np.zeros(shape), np.zeros(shape)
        branch = np.zeros(shape, dtype=np.int32)
        weight = area / area.sum()
        for m in range(months):
            centres, zonal = op.zonal_mean(mesh, temp[m], band, fill=True)
            zonal = np.convolve(np.pad(zonal, 1, mode="edge"), np.ones(3) / 3, mode="valid")       # a light smoothing
            # (a) the rising branch sits at the warmest latitude of the month
            tropics = np.abs(centres) <= o["rising_search_deg"]
            rise = _soft_peak(centres[tropics], zonal[tropics], o["rising_sharpness_per_k"])
            limit = min(o["rising_limit_deg"], edge - o["rising_margin_from_edge_deg"])
            rise = float(np.clip(rise, -limit, limit))
            # the rising branch at each longitude: the warmest latitude of that band of longitude, near the thermal
            # equator, so that over a hot continent it moves far toward the summer pole (a monsoon trough)
            m_cfg = c["monsoon"]
            sector_rise = np.empty(n_sectors)
            for k in range(n_sectors):
                in_sector = sector == k
                if not in_sector.any():
                    sector_rise[k] = rise
                    continue
                s_centres, s_zonal = op.zonal_mean(mesh, temp[m], band, mask=in_sector.astype(np.float64), fill=True)
                near = np.abs(s_centres) <= o["rising_search_deg"]
                sector_rise[k] = _soft_peak(s_centres[near], s_zonal[near], o["rising_sharpness_per_k"])
            reach = min(m_cfg["rising_limit_deg"], edge - o["rising_margin_from_edge_deg"])
            kernel = np.ones(int(m_cfg["smoothing_sectors"])) / int(m_cfg["smoothing_sectors"])
            wrapped = np.concatenate([sector_rise[-len(kernel):], sector_rise, sector_rise[:len(kernel)]])
            sector_rise = np.convolve(wrapped, kernel, mode="same")[len(kernel):-len(kernel)]
            sector_rise = np.clip(rise + m_cfg["share"] * (sector_rise - rise), -reach, reach)
            centres_lon = (np.arange(n_sectors) + 0.5) * sector_width - HALF_TURN
            rise_cell = np.interp(lon, centres_lon, sector_rise, period=2 * HALF_TURN)
            # the latitude of strongest storm growth in each hemisphere: the steepest fall of temperature
            slope = np.abs(np.gradient(zonal, centres))
            lows = []
            for sign in (-1.0, 1.0):
                side = (sign * centres >= edge + b["storm_search_from_edge_deg"]) & (sign * centres <= b["storm_search_to_deg"])
                storm = _soft_peak(sign * centres[side], slope[side], b["storm_sharpness"] / max(slope[side].max(), np.finfo(float).tiny))
                lows.append(float(np.clip(2 * storm - edge, edge + b["low_minimum_from_edge_deg"], b["low_limit_deg"])))
            # (b) pressure belts
            nodes = np.array([-POLE_DEG, -lows[0], -edge, rise, edge, lows[1], POLE_DEG])
            values = np.array([b["polar_pa"], -b["subpolar_low_pa"], b["subtropical_high_pa"], -b["equatorial_low_pa"],
                               b["subtropical_high_pa"], -b["subpolar_low_pa"], b["polar_pa"]])
            belt = _belt_profile(lat, nodes, values)
            # inside the tropics the low follows the rising branch of the cell's own longitude
            inside = np.abs(lat) <= edge
            low_side = inside & (lat <= rise_cell)
            frac = np.where(low_side, (lat + edge) / np.maximum(rise_cell + edge, TINY_DEG),
                            (lat - rise_cell) / np.maximum(edge - rise_cell, TINY_DEG))
            curve = (1 - np.cos(np.pi * np.clip(frac, 0, 1))) / 2
            high, low = b["subtropical_high_pa"], -b["equatorial_low_pa"]
            belt = np.where(inside, np.where(low_side, high + (low - high) * curve, low + (high - low) * curve), belt)
            belt -= (belt * weight).sum()
            # (c) warm surfaces lower the pressure: the departure from the mean of the latitude, smoothed
            departure = temp[m] - np.interp(lat, centres, zonal)
            warm = -warm_coefficient * op.smooth(mesh, departure, smooth_length, ctx.memo)
            warm -= (warm * weight).sum()
            belt_out[m], warm_out[m] = belt, warm
            pressure[m] = c["mean_pressure_pa"] + belt + warm
            # (d) surface wind from pressure, spin and drag: (drag + f k x) u = -grad p / rho
            for part, target in ((belt, wind_belt), (warm, wind_warm)):
                push = -op.gradient(mesh, part) / (radius * rho)
                turned = np.cross(mesh.xyz, push)
                target[m] = (drag * push - f[:, None] * turned) / (drag * drag + f * f)[:, None]
            wind[m] = wind_belt[m] + wind_warm[m]
            # (e) wind aloft and storm growth from the temperature contrast
            grad_t = op.gradient(mesh, temp[m]) / radius
            shear = gravity / (f_safe * c["reference_temperature_k"])[:, None] * np.cross(mesh.xyz, grad_t)   # per second
            steering[m] = wind[m] + shear * c["steering_height_m"]
            growth[m] = c["eady_coefficient"] * np.abs(f) / c["stability_per_s"] * np.linalg.norm(shear, axis=1) * SECONDS_PER_DAY
            # the overturning loop: rising at the warmest latitude, sinking toward each edge, with no net flow of air
            up = np.exp(-((lat - rise_cell) / o["rising_width_deg"]) ** 2)
            north_w, south_w = (edge - rise) ** o["winter_loop_power"], (edge + rise) ** o["winter_loop_power"]
            down_n = np.exp(-((lat - o["sinking_position"] * edge) / o["sinking_width_deg"]) ** 2)
            down_s = np.exp(-((lat + o["sinking_position"] * edge) / o["sinking_width_deg"]) ** 2)
            lifted = (up * weight).sum()
            scale_n = lifted * north_w / (north_w + south_w) / (down_n * weight).sum()
            scale_s = lifted * south_w / (north_w + south_w) / (down_s * weight).sum()
            subsidence[m] = o["rising_speed_mm_s"] * (scale_n * down_n + scale_s * down_s - up)
            # the stand-in for summer descent west of heated land
            warmth = np.where(heated_band, np.maximum(departure, 0.0), 0.0)
            warmth = op.smooth(mesh, warmth, s["smoothing_km"] * M_PER_KM / radius, ctx.memo)
            sink_extra[m] = np.where(np.abs(lat) <= hi_lat + SINKING_MARGIN_DEG, s["sinking_mm_s_per_k"] * warmth[source_cell], 0.0)
            subsidence[m] += sink_extra[m]
            strongest = np.argmax(np.stack([np.full(mesh.n, o["branch_threshold"]), up, scale_n * down_n, scale_s * down_s]), axis=0)
            branch[m] = strongest
        ctx.write("sea_level_pressure", pressure)
        ctx.write("wind", wind)
        ctx.write("steering_wind", steering)
        ctx.write("subsidence", subsidence)
        ctx.write("baroclinicity", growth)
        if ctx.recording:
            ctx.driver("sea_level_pressure", "mean_pressure", np.full(shape, c["mean_pressure_pa"]))
            ctx.driver("sea_level_pressure", "belt_part", belt_out)
            ctx.driver("sea_level_pressure", "warm_or_cold_surface_part", warm_out)
            ctx.driver("wind", "from_belts", wind_belt)
            ctx.driver("wind", "from_surface_temperature", wind_warm)
            ctx.driver("subsidence", "branch", branch)
            ctx.driver("subsidence", "west_of_hot_land", sink_extra)
