"""Circulation, first version: belts with their rising and sinking air, land-sea pressure, drag balance.

Model (Assembled; the process the design trusts least).
(a) The tropical overturning loop, the Hadley cell: air rises near the warmest latitude of the
    month, flows poleward aloft, sinks, and returns along the surface. Its poleward edge follows
    the scaling sqrt(N H / (spin rate * radius)) (Lu, Vecchi and Reichler 2007, after Held 2000).
    The loop gives the subsidence field, the same at every longitude.
(b) Pressure belts: low under the rising air, high under the sinking edge of the loop, low again
    on the poleward side of the latitude where storms grow fastest, high at the poles. The depth
    of the belts is a set of parameters. This is the closest the engine comes to placing an
    outcome: the westerlies are not simulated, a rule sets them where storm growth is strongest.
(c) Warm surfaces lower the pressure above them and cold ones raise it (Lindzen and Nigam 1987,
    used here over land and outside the tropics as well).
(d) Surface wind follows from a balance of pressure, the planet's spin and drag on the ground.
(e) Wind aloft comes from the thermal wind relation; storm growth is the Eady growth rate.

Ignores: single storms, the waves that mountain ranges raise in the flow, the turning aside of
wind by high ground, how monsoons really work. Stability and layer depth are constants.
Wrong where: the seasonal shift of the tropical rain belt, monsoons, storm paths downwind of
great ranges. The thermal wind relation fails near the equator. Planets with high tilt, or with
spin rates far from Earth's, are beyond it until build step 10.
"""
import numpy as np

from ..library import operators as op
from ..library.units import M_PER_KM, SECONDS_PER_DAY, TWO_PI
from ..process import Process

NO_BRANCH, RISING, SINKING_NORTH, SINKING_SOUTH = 0, 1, 2, 3
POLE_DEG = 90.0


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


class BeltCirculation(Process):
    stage = "climate"
    reads = ("surface_temperature", "coriolis_parameter", "latitude", "height_above_sea", "cell_area")
    writes = ("sea_level_pressure", "wind", "steering_wind", "subsidence", "baroclinicity")
    shared = ("lapse_rate_k_per_km",)
    model = "pressure belts tied to the Hadley cell and to storm growth, warm-surface lows, and a drag balance"
    drivers = {"sea_level_pressure": ("mean_pressure", "belt_part", "warm_or_cold_surface_part"),
               "wind": ("from_belts", "from_surface_temperature"),
               "subsidence": ("branch",)}
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
            up = np.exp(-((lat - rise) / o["rising_width_deg"]) ** 2)
            north_w, south_w = (edge - rise) ** o["winter_loop_power"], (edge + rise) ** o["winter_loop_power"]
            down_n = np.exp(-((lat - o["sinking_position"] * edge) / o["sinking_width_deg"]) ** 2)
            down_s = np.exp(-((lat + o["sinking_position"] * edge) / o["sinking_width_deg"]) ** 2)
            lifted = (up * weight).sum()
            scale_n = lifted * north_w / (north_w + south_w) / (down_n * weight).sum()
            scale_s = lifted * south_w / (north_w + south_w) / (down_s * weight).sum()
            subsidence[m] = o["rising_speed_mm_s"] * (scale_n * down_n + scale_s * down_s - up)
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
