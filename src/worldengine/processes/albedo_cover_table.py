"""Albedo, second version: the share of sunlight a surface reflects, from what covers it (build step 6).

Model (Rule). As the first version (albedo_surface_table.py): a table sets the reflection of sea, land and snow or
ice; a constant share of sunlight is reflected by cloud and air, and more at low sun angles, the fit of North,
Cahalan and Coakley 1981 (equation 18). What changed with build step 6: where snow and ice lie is no longer decided
here. It is the field snow_ice_cover that Cryosphere wrote in the last round: sea ice that comes and goes with the
months, and snow and lasting ice on land. And plant cover, from the last round's Biomes, now counts: bare ground is
lighter than ground under plants, and snow on the ground under trees reflects less, since the trees stand above it
(a share of the snow's whiteness, set by the plant cover, is hidden).

    albedo = cloud + (1 - ice) * low_sun * P2(sin latitude) + (1 - cloud)^2 * surface,
    surface on land = bare + cover_of_plants * (under plants - bare), and snow's share of it ice * (1 - hidden * plants)

Ignores: where clouds actually form, dust, the darkening of old snow, the colour of the sea under a low sun.
Wrong where: the cloud decks of cool subtropical seas and the cloud bands of the tropics; clouds are the largest known
gap in the climate stage. A planet can still freeze over, more easily than in fuller models [UNVERIFIED: recalled];
the process says so in a note when snow and ice cover more than a third of the surface.
"""
import numpy as np

from ..process import Process


class CoverTableAlbedo(Process):
    stage = "climate"
    reads = ("ocean_mask", "latitude", "cell_area")
    reads_lagged = ("snow_ice_cover", "vegetation_cover")
    writes = ("albedo",)
    model = "surface table of sea, bare ground, ground under plants and snow or ice from the cryosphere, a constant cloud share and a low-sun term"
    drivers = {"albedo": ("from_surface_type", "from_snow_and_ice", "from_cloud_and_sun_angle")}
    additive = ("albedo",)

    def run(self, ctx):
        c = ctx.const
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        s = np.sin(np.deg2rad(ctx.read("latitude")))
        area = ctx.read("cell_area")
        cover = np.clip(ctx.read_lagged("snow_ice_cover").astype(np.float64), 0.0, 1.0)            # (months, n)
        plants = np.clip(ctx.read_lagged("vegetation_cover").astype(np.float64), 0.0, 1.0)         # (months, n)
        legendre = (3 * s * s - 1) / 2
        t = c["surface"]
        land = t["bare_ground"] + plants * (t["under_plants"] - t["bare_ground"])
        base = np.where(sea[None, :], t["sea"], land)
        ice = np.where(sea[None, :], cover, cover * (1 - c["snow_hidden_by_plants"] * plants))
        through = (1 - c["cloud_share"]) ** 2
        from_type = through * base
        from_ice = ice * (through * (t["ice"] - base) - c["low_sun_term"] * legendre)
        from_sky = np.broadcast_to(c["cloud_share"] + c["low_sun_term"] * legendre, cover.shape)
        ctx.write("albedo", np.clip(from_type + from_ice + from_sky, 0.0, 1.0))
        covered = float((ice.mean(axis=0) * area).sum() / area.sum())
        if covered > c["note_when_covered_above"]:
            ctx.note("snow and ice cover more than a third of the planet's surface on the year's average: a deep ice age",
                     share_covered=round(covered, 3))
        ctx.driver("albedo", "from_surface_type", from_type)
        ctx.driver("albedo", "from_snow_and_ice", from_ice)
        ctx.driver("albedo", "from_cloud_and_sun_angle", from_sky)
