"""Albedo: the share of sunlight a surface reflects, first version.

Model (Rule). A table sets the reflection of each surface type: sea, land, and snow or ice.
Snow and ice follow the two rules of the seasonal model in North, Cahalan and Coakley 1981
(page 102: "an ice cap whose edge is at the mean annual -10 C isotherm" and "a seasonally moving
snow line on land whose edge is at the instantaneous 0 C isotherm"), read off last round's
temperature:
  * ice on the sea wherever the mean temperature of the year is below -10 C;
  * snow on land, month by month, wherever that month is below freezing. Land whose every month
    is below freezing is therefore white all year: that is the ice sheet on land.
The first rule is applied to the sea only [INFERRED: my reading]. On land it would put an ice
sheet over ground with a cold year but warm summers, as in the heart of a large continent,
where snow melts every summer; the second rule already covers land.
Each rule has a narrow ramp so that the rounds settle. A constant share of sunlight is reflected
by cloud and air, and more is reflected at low sun angles: that term, 0.202 times the second
Legendre polynomial of the sine of latitude, is the fit of the same paper (equation 18), and
the ice value is chosen so that an ice-covered cell reflects the paper's 0.62.

    albedo = cloud + (1 - ice) * low_sun * P2(sin latitude) + (1 - cloud)^2 * surface

The constants of EnergyBalance were fitted together with these rules. An earlier version of
this process put ice wherever a month was below freezing, sea included; with the same constants
that made the planet several degrees too cold and brought it to the edge of freezing over.

Ignores: where clouds actually form, plant cover (until Biomes feeds it back), dust, snow depth,
sea ice that comes and goes with the seasons, and the difference between snow and ice.
Wrong where: the cloud decks of cool subtropical seas and the cloud bands of the tropics.
Clouds are the largest known gap in the climate stage.
"""
import numpy as np

from ..process import Process


class SurfaceTableAlbedo(Process):
    stage = "climate"
    reads = ("ocean_mask", "latitude")
    reads_lagged = ("surface_temperature",)
    writes = ("albedo",)
    shared = ("freezing_point_k", "sea_ice_yearly_mean_below_k")
    model = "surface table with sea ice by the year's mean, snow on land below freezing, a constant cloud share and a low-sun term"
    drivers = {"albedo": ("from_surface_type", "from_snow_and_ice", "from_cloud_and_sun_angle")}
    additive = ("albedo",)

    def run(self, ctx):
        c = ctx.const
        sea = ctx.read("ocean_mask")
        s = np.sin(np.deg2rad(ctx.read("latitude")))
        temperature = ctx.read_lagged("surface_temperature").astype(np.float64)
        legendre = (3 * s * s - 1) / 2                                   # the second Legendre polynomial
        ramp = lambda limit, value: np.clip(0.5 + (limit - value) / c["ice_ramp_k"], 0.0, 1.0)
        sea_ice = ramp(ctx.shared["sea_ice_yearly_mean_below_k"], temperature.mean(axis=0))       # the same in every month
        snow = ramp(ctx.shared["freezing_point_k"], temperature)                                  # month by month
        ice = np.where(sea, sea_ice, snow)
        base = np.where(sea, c["surface"]["sea"], c["surface"]["land"])
        through = (1 - c["cloud_share"]) ** 2                            # sunlight that passes the cloud twice
        from_type = np.broadcast_to(through * base, temperature.shape)
        from_ice = ice * (through * (c["surface"]["ice"] - base) - c["low_sun_term"] * legendre)
        from_sky = np.broadcast_to(c["cloud_share"] + c["low_sun_term"] * legendre, temperature.shape)
        ctx.write("albedo", np.clip(from_type + from_ice + from_sky, 0.0, 1.0))
        ctx.driver("albedo", "from_surface_type", from_type)
        ctx.driver("albedo", "from_snow_and_ice", from_ice)
        ctx.driver("albedo", "from_cloud_and_sun_angle", from_sky)
