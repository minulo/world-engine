"""WeatherStatistics: the two numbers that describe a month's day-to-day weather (build step 8).

Model (Assembled; design, Layer 5).
(a) How far a day's temperature strays from the monthly mean. Storms carry air across the temperature contrast, so the
spread is about the contrast times a mixing length, the typical distance the air is carried; the source puts that
length on the order of 900 km near the surface in mid-latitudes [DOCUMENTED in the design: Schneider, Bischoff and
Plotka 2015, equation 2]. The design's extensions: the relation used at the surface; the contrast in any direction,
measured as the gradient of the temperature smoothed over half a mixing length, times the length (so that a sharp edge
cannot give a spread larger than the step across it), after each cell's temperature is brought to sea level (so that a mountain side does not count
as contrast); the length shrunk where storm tracks are thin; the spread damped over the sea [INFERRED].
(b) The share of wet days in the month grows with the month's rain to the power 0.45 and is never more than every day
wet [DOCUMENTED in the design: New, Hulme and Jones 2000, equation 4]. Here the rain is counted per day, and one scale
for the whole planet stands in for a place's own measured averages [INFERRED]. A wet day is one with at least 0.1 mm of
rain or snow [DOCUMENTED in the design: Harris et al. 2020].
The power is the published one; the mixing length, its shrinking, the damping over the sea and the scale of the wet days
are set here and not yet fitted to Earth's daily data, which the reference data do not hold [PROVISIONAL].

Ignores: the difference between day and night; spells held in place when storm tracks stall; swings caused by cloud or
thunderstorms.
Wrong where: the spread is too small in the tropics, and wherever swings come from cloud or thunderstorms. One scale for
the whole planet cannot tell a drizzle climate from one of rare downpours. Equations that derive daily numbers from
monthly ones "can lead to serious errors or even nonsense" beyond the range of their calibration data [DOCUMENTED in the
design: Wilks and Wilby 1999, reporting Hutchinson]; an invented planet lies outside any such data.
"""
import numpy as np

from ..library import operators as op
from ..library.units import M_PER_KM, SECONDS_PER_DAY, TINY
from ..process import Process


class MixingLengthWeather(Process):
    stage = "climate"
    reads = ("surface_temperature", "height_above_sea", "storm_track_density", "precipitation", "ocean_mask")
    writes = ("daily_temperature_spread", "wet_day_fraction")
    shared = ("lapse_rate_k_per_km",)
    model = "temperature spread as contrast times a mixing length (Schneider et al. 2015); wet days from monthly rain to the power 0.45 (New, Hulme and Jones 2000)"
    drivers = {"daily_temperature_spread": ("contrast_k", "mixing_length_km"), "wet_day_fraction": ("rain_per_day_mm",)}

    def run(self, ctx):
        c, mesh, months = ctx.const, ctx.mesh, ctx.months
        radius = ctx.planet["radius_m"]
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        height = np.maximum(ctx.read("height_above_sea").astype(np.float64), 0.0)
        t = ctx.read("surface_temperature").astype(np.float64) + ctx.shared["lapse_rate_k_per_km"] * height / M_PER_KM
        tracks = ctx.read("storm_track_density").astype(np.float64)
        rain = ctx.read("precipitation").astype(np.float64)
        days = ctx.planet["year_length_s"] / months / SECONDS_PER_DAY
        # the mixing length: full where storm tracks are dense, shrunk where they are thin
        top = np.percentile(tracks, c["dense_tracks_percentile"], axis=1, keepdims=True)
        share = np.clip(tracks / np.maximum(top, TINY), 0.0, 1.0)
        length_km = c["mixing_length_km"] * (c["thin_track_share"] + (1 - c["thin_track_share"]) * share)
        # the contrast across one mixing length: the gradient of the temperature smoothed over half that length, times the
        # length, so that an edge sharper than the length gives no more than the step across it
        reach = c["mixing_length_km"] * M_PER_KM / radius
        contrast = np.stack([np.linalg.norm(op.gradient(mesh, op.smooth(mesh, t[m], reach / 2, ctx.memo)), axis=1) * reach
                             for m in range(months)])
        spread = contrast * length_km / c["mixing_length_km"]
        spread = np.where(sea[None, :], spread * c["sea_damping"], spread)
        per_day = rain / days
        wet = np.clip(c["wet_day_scale"] * per_day ** c["wet_day_power"], 0.0, 1.0)
        ctx.write("daily_temperature_spread", spread)
        ctx.write("wet_day_fraction", wet)
        if ctx.recording:
            ctx.driver("daily_temperature_spread", "contrast_k", contrast)
            ctx.driver("daily_temperature_spread", "mixing_length_km", length_km)
            ctx.driver("wet_day_fraction", "rain_per_day_mm", per_day)
