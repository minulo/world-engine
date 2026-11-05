"""DailyWeather: the weather of one day, drawn around the climate (build step 8).

Model (Adapted; design, Layer 5). A weather generator in the line of Richardson 1981: wet and dry spells persist, and
amounts and temperatures are drawn around the monthly means. How far they stray and how often it rains are read from
the two fields of WeatherStatistics. Rain amounts are drawn from a skewed distribution, because small daily amounts are
common and large ones rare [DOCUMENTED in the design: Wilks and Wilby 1999]; here the exponential, the simplest such,
drawn through smoothed noise so that a wet day's amounts vary together over neighbouring cells [INFERRED].
The usual rule of such generators, that the chance of rain depends on whether yesterday was wet, needs yesterday's state,
so it is replaced by the look-back sum of the design (Layer 3): noise that is a weighted sum of the last days' noise
fields, each keyed by its date, so spells persist and any day comes out the same however it is reached. Neighbouring
cells vary together through noise smoothed on the mesh [the design names Lindgren et al. 2011 for smooth random fields on
a meshed sphere; here a plain smoothing of white noise stands in, INFERRED]. Storms from SynopticStorms pass through:
they make rain likelier where they are and lower the pressure; a day warmer than usual has lower pressure too, as the warm
air ahead of a low does [INFERRED]; a wet day's amount is the day's mean rain over the day's
chance of rain, so that the rain of passing storms is counted inside each month's total.

When a day is recomputed for a "why" answer, the process records the terms of each field: the monthly means around the
date, and the day's own part, with the remembered noise and the spread it was scaled by; for the rain, whether the day
is wet, dry or in a month without rain, the chance of rain and its two sources, the draw of the date and the amount
drawn. Temperature, pressure and wind are the sums of their terms.

Ignores: the motion of the air itself.
Wrong where: this is the weakest causal link in the chain: a believable sample around a physically derived climate, not
a simulation. One year differs too little from the next: every generated year is drawn around the same average year,
and the noise remembers nothing beyond its window [INFERRED in the design].
"""
import numpy as np
from scipy.special import ndtr

from ..library import days as dy
from ..library import operators as op
from ..library.units import M_PER_KM, TINY
from ..process import Process

DRY, WET, NO_RAIN = 0, 1, 2                      # the classes of the driver `day_kind`


class RemembersNoiseWeather(Process):
    stage = "weather"
    reads = ("surface_temperature", "precipitation", "wind", "sea_level_pressure", "daily_temperature_spread",
             "wet_day_fraction", "storm_influence")
    writes = ("weather_temperature", "weather_precipitation", "weather_wind", "weather_pressure")
    draws = ("temperature_noise", "rain_noise", "rain_amounts", "wind_noise_east", "wind_noise_north")
    shared = ("weather_look_back_days",)
    model = "a weather generator in the line of Richardson 1981, with noise remembered over a window of days"
    drivers = {"weather_temperature": ("month_mean", "departure", "noise_sd", "spread_k"),
               "weather_precipitation": ("day_kind", "month_rain_per_day", "chance", "wet_day_share", "storm_chance", "draw", "amount"),
               "weather_pressure": ("month_mean", "from_warm_day", "from_storms"),
               "weather_wind": ("month_wind", "gust")}
    additive = ("weather_temperature", "weather_pressure", "weather_wind")

    def run(self, ctx):
        c, mesh, planet = ctx.const, ctx.mesh, ctx.planet
        day, window, n = int(ctx.round), int(ctx.shared["weather_look_back_days"]), ctx.mesh.n
        reach = c["noise_length_km"] * M_PER_KM / planet["radius_m"]

        def smooth(field):
            s = op.smooth(mesh, field, reach, ctx.memo)
            return (s - s.mean()) / max(s.std(), TINY)

        noise = lambda purpose: dy.remembered_noise(ctx.draw, purpose, day, window, c["persistence"], n, smooth)
        mean_t = dy.on_day(ctx.read("surface_temperature").astype(np.float64), day, planet)
        spread = dy.on_day(ctx.read("daily_temperature_spread").astype(np.float64), day, planet)
        warm = noise("temperature_noise")
        temperature = mean_t + spread * warm
        days_per_month = dy.days_in_year(planet) / ctx.months
        rain_day = dy.on_day(ctx.read("precipitation").astype(np.float64), day, planet) / days_per_month
        share = np.clip(dy.on_day(ctx.read("wet_day_fraction").astype(np.float64), day, planet), 0.0, 1.0)
        storms = ctx.read("storm_influence").astype(np.float64)
        by_storms = np.clip(c["storm_rain_chance"] * storms, 0.0, 1.0)
        chance = 1.0 - (1.0 - share) * (1.0 - by_storms)
        draw = ndtr(noise("rain_noise"))
        wet = (draw < chance) & (rain_day > 0)
        # amounts: exponential at each cell, drawn through smoothed noise so that neighbouring cells rain alike (the
        # normal value of the noise turned into a uniform one, then into an exponential one)
        amounts = -np.log(np.clip(1.0 - ndtr(smooth(ctx.draw.normal("rain_amounts", n))), TINY, 1.0))
        rain = np.where(wet, rain_day / np.maximum(chance, TINY) * amounts, 0.0)
        mean_p = dy.on_day(ctx.read("sea_level_pressure").astype(np.float64), day, planet)
        by_warmth, by_lows = -c["pressure_spread_pa_per_k"] * spread * warm, -c["storm_low_pa"] * storms
        pressure = mean_p + by_warmth + by_lows
        wind = dy.on_day(ctx.read("wind").astype(np.float64), day, planet)
        gust = c["wind_spread_m_s"] * (noise("wind_noise_east")[:, None] * mesh.east + noise("wind_noise_north")[:, None] * mesh.north)
        ctx.write("weather_temperature", temperature)
        ctx.write("weather_precipitation", rain)
        ctx.write("weather_pressure", pressure)
        ctx.write("weather_wind", wind + gust)
        if ctx.recording:
            ctx.driver("weather_temperature", "month_mean", mean_t)
            ctx.driver("weather_temperature", "departure", spread * warm)
            ctx.driver("weather_temperature", "noise_sd", warm)
            ctx.driver("weather_temperature", "spread_k", spread)
            ctx.driver("weather_precipitation", "day_kind", np.where(rain_day > 0, np.where(wet, WET, DRY), NO_RAIN))
            ctx.driver("weather_precipitation", "month_rain_per_day", rain_day)
            ctx.driver("weather_precipitation", "chance", chance)
            ctx.driver("weather_precipitation", "wet_day_share", share)
            ctx.driver("weather_precipitation", "storm_chance", by_storms)
            ctx.driver("weather_precipitation", "draw", draw)
            ctx.driver("weather_precipitation", "amount", amounts)
            ctx.driver("weather_pressure", "month_mean", mean_p)
            ctx.driver("weather_pressure", "from_warm_day", by_warmth)
            ctx.driver("weather_pressure", "from_storms", by_lows)
            ctx.driver("weather_wind", "month_wind", wind)
            ctx.driver("weather_wind", "gust", gust)

