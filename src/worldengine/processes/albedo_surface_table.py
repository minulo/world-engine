"""Albedo: the share of sunlight a surface reflects, first version.

Model (Rule). A table sets the reflection of each surface type: sea, land, and snow or ice.
Ice lies wherever last round's temperature was below freezing, with a narrow ramp so that the
rounds settle. A constant share of sunlight is reflected by cloud and air, and more is reflected
at low sun angles: that term, 0.202 times the second Legendre polynomial of the sine of
latitude, is the fit of North, Cahalan and Coakley 1981 (equation 18), and the ice value is
chosen so that an ice-covered cell reflects the 0.62 of the same paper.

    albedo = cloud + (1 - ice) * low_sun * P2(sin latitude) + (1 - cloud)^2 * surface

Ignores: where clouds actually form, plant cover (until Biomes feeds it back), dust, snow depth.
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
    shared = ("freezing_point_k", "sea_freezing_point_k")
    model = "surface table with ice below freezing, a constant cloud share and a low-sun term"
    drivers = {"albedo": ("from_surface_type", "from_snow_and_ice", "from_cloud_and_sun_angle")}
    additive = ("albedo",)

    def run(self, ctx):
        c = ctx.const
        sea = ctx.read("ocean_mask")
        s = np.sin(np.deg2rad(ctx.read("latitude")))
        temperature = ctx.read_lagged("surface_temperature").astype(np.float64)
        legendre = (3 * s * s - 1) / 2                                   # the second Legendre polynomial
        freezing = np.where(sea, ctx.shared["sea_freezing_point_k"], ctx.shared["freezing_point_k"])
        ice = np.clip(0.5 + (freezing - temperature) / c["ice_ramp_k"], 0.0, 1.0)
        base = np.where(sea, c["surface"]["sea"], c["surface"]["land"])
        through = (1 - c["cloud_share"]) ** 2                            # sunlight that passes the cloud twice
        from_type = np.broadcast_to(through * base, temperature.shape)
        from_ice = ice * (through * (c["surface"]["ice"] - base) - c["low_sun_term"] * legendre)
        from_sky = np.broadcast_to(c["cloud_share"] + c["low_sun_term"] * legendre, temperature.shape)
        ctx.write("albedo", np.clip(from_type + from_ice + from_sky, 0.0, 1.0))
        ctx.driver("albedo", "from_surface_type", from_type)
        ctx.driver("albedo", "from_snow_and_ice", from_ice)
        ctx.driver("albedo", "from_cloud_and_sun_angle", from_sky)
