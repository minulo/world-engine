"""Albedo: the share of sunlight a surface reflects, first version.

Model (Rule). A table sets the reflection of each surface type: sea, land, and snow or ice.
Until the Cryosphere process exists (build step 6), this process decides for itself where snow
and ice lie:
  * ice on the sea wherever the mean temperature of the year is below -10 C. This is the rule
    of the seasonal model in North, Cahalan and Coakley 1981 (page 102: "an ice cap whose edge
    is at the mean annual -10 C isotherm"), applied to the sea only [INFERRED: my reading];
  * snow on land wherever snow lay on the ground in the last round: Hydrology's snow store,
    which snowfall fills and warmth empties. The ground counts as fully white once the store
    holds a set amount of water (the form of the older ECMWF land scheme, Dutra et al. 2010,
    equation A2). Land where more snow falls in a year than the year can melt keeps its snow
    all year: that is the ice sheet on land.
The paper's own rule for land is simpler: "a seasonally moving snow line on land whose edge is
at the instantaneous 0 C isotherm", snow or no snow. An earlier version of this process used
it. With it, ground that is cold but dry, and high ground that is cold only by its height,
turned white with no snow to make it so, and one seeded world in 32 froze over from that
feedback (the second review of build step 1). Asking for snow makes cold deserts stay dark.
Until build step 2 this process kept a snow store of its own, from last round's snowfall and
temperature; the store is now Hydrology's, so the map of snow and the whiteness of the ground
are one and the same thing.

A constant share of sunlight is reflected by cloud and air, and more is reflected at low sun
angles: that term, 0.202 times the second Legendre polynomial of the sine of latitude, is the
fit of the same paper (equation 18), and the ice value is chosen so that an ice-covered cell
reflects the paper's 0.62.

    albedo = cloud + (1 - ice) * low_sun * P2(sin latitude) + (1 - cloud)^2 * surface

The rule for sea ice has a narrow ramp so that the rounds settle.

Ignores: where clouds actually form, plant cover (until Biomes feeds it back), dust, sea ice
that comes and goes with the seasons, the difference between snow and ice, and the darkening
of old snow and of snow under trees.
Wrong where: the cloud decks of cool subtropical seas and the cloud bands of the tropics.
Clouds are the largest known gap in the climate stage. While land is too dry (see Moisture),
snow on land is too thin and melts too early. The constants of EnergyBalance were fitted by
their authors together with their own snow rule, so with less snow this planet runs warmer
than theirs would [INFERRED]. A planet can still freeze over: with ice on most of its surface
it reflects more sunlight than it needs to stay frozen, and models of this kind tip that way
more easily than fuller ones [UNVERIFIED: my recollection of the literature on energy balance
models; the design cites Roe and Baker 2010 for the two steady states]. Measured on the
default planet: with 2 % less sunlight it is 4.2 K colder and stays open, as do ten other
seeded worlds; with 5 % less it is below freezing on average and the note below is raised.
When more than a third of the surface lies under snow and ice on the year's average, the
process says so in a note.
"""
import numpy as np

from ..process import Process


class SurfaceTableAlbedo(Process):
    stage = "climate"
    reads = ("ocean_mask", "latitude", "cell_area")
    reads_lagged = ("surface_temperature", "snow_water")
    writes = ("albedo",)
    shared = ("sea_ice_yearly_mean_below_k", "snow_full_cover_mm")
    model = "surface table with sea ice by the year's mean, snow on land where the snow store holds snow, a constant cloud share and a low-sun term"
    drivers = {"albedo": ("from_surface_type", "from_snow_and_ice", "from_cloud_and_sun_angle")}
    additive = ("albedo",)

    def run(self, ctx):
        c = ctx.const
        sea = ctx.read("ocean_mask")
        s = np.sin(np.deg2rad(ctx.read("latitude")))
        area = ctx.read("cell_area")
        temperature = ctx.read_lagged("surface_temperature").astype(np.float64)
        snow = ctx.read_lagged("snow_water").astype(np.float64)
        legendre = (3 * s * s - 1) / 2                                   # the second Legendre polynomial
        # Ice on the sea: the same in every month.
        sea_ice = np.clip(0.5 + (ctx.shared["sea_ice_yearly_mean_below_k"] - temperature.mean(axis=0)) / c["ice_ramp_k"], 0.0, 1.0)
        # Snow on land: white in proportion to the water the snow store holds, up to full cover.
        on_ground = np.clip(snow / ctx.shared["snow_full_cover_mm"], 0.0, 1.0)
        ice = np.where(sea, sea_ice, on_ground)
        base = np.where(sea, c["surface"]["sea"], c["surface"]["land"])
        through = (1 - c["cloud_share"]) ** 2                            # sunlight that passes the cloud twice
        from_type = np.broadcast_to(through * base, temperature.shape)
        from_ice = ice * (through * (c["surface"]["ice"] - base) - c["low_sun_term"] * legendre)
        from_sky = np.broadcast_to(c["cloud_share"] + c["low_sun_term"] * legendre, temperature.shape)
        ctx.write("albedo", np.clip(from_type + from_ice + from_sky, 0.0, 1.0))
        covered = float((ice.mean(axis=0) * area).sum() / area.sum())
        if covered > c["note_when_covered_above"]:
            ctx.note("snow and ice cover more than a third of the planet's surface on the year's average: a deep ice age",
                     share_covered=round(covered, 3))
        ctx.driver("albedo", "from_surface_type", from_type)
        ctx.driver("albedo", "from_snow_and_ice", from_ice)
        ctx.driver("albedo", "from_cloud_and_sun_angle", from_sky)
