"""Insolation: incoming sunlight at the top of the air.

Model (Established): the astronomical formula gives the daily mean from latitude, season, tilt
and orbit (Rose, The Climate Laboratory). Each month is the mean of several moments.

Ignores: the air (this is sunlight before any is absorbed), the time of day, shading by
terrain, and the ageing of the star.
Wrong where: planets whose day is a large part of their year.
"""
from ..library.orbit import monthly_insolation
from ..process import Process


class DailyMeanInsolation(Process):
    stage = "climate"
    reads = ("latitude",)
    writes = ("insolation",)
    model = "daily-mean insolation from latitude, season, tilt and orbit"

    def run(self, ctx):
        key = ("insolation", ctx.mesh.level)
        if key not in ctx.memo:                               # the same every round: latitude and the planet do not change
            p, o = ctx.planet, ctx.planet["orbit"]
            ctx.memo[key] = monthly_insolation(
                ctx.read("latitude"), ctx.months, int(ctx.const["samples_per_month"]), p["axial_tilt_deg"], p["star_output_w_m2"],
                o["eccentricity"], o["perihelion_solar_longitude_deg"], o["northward_equinox_year_fraction"])
        else:
            ctx.read("latitude")
        ctx.write("insolation", ctx.memo[key])
