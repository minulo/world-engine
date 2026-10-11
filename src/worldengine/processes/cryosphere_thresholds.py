"""Cryosphere: the frozen part of the surface (build step 6).

Model (Rule). The cryosphere is the frozen part of the surface. Sea ice forms where the sea would be below freezing;
lasting land ice forms where snow survives the summer; permafrost, ground that stays frozen all year, forms where the
yearly mean is cold enough. The thresholds are parameters (design, Layer 5). In detail:
  * sea ice, month by month: the sea is covered in a month whose temperature lies below the freezing point of sea water,
    over a narrow ramp so that the climate rounds settle. Sea ice now comes and goes with the seasons; the first
    version of Albedo laid it by the year's mean alone;
  * snow and ice on land, month by month: the share of the ground under the snow store of the last round, full once
    the store holds a set depth of water (the form of the older ECMWF land scheme, Dutra et al. 2010, as Hydrology
    uses it). Where the store never empties in the year, the ground is lasting land ice;
  * permafrost: full where the yearly mean lies at or below one threshold, none where it lies at or above another,
    and in between by a straight line. A land cell colder than the first in every month therefore has full
    permafrost, and one above freezing in every month has none (the design's known answers).
Before this step Albedo decided for itself where snow and ice lay; it now reads snow_ice_cover from the last round.

Ignores: ice that flows, glaciers carving valleys, ice ages, the insulation of the ground by snow, sea ice blown by
the wind, and the salt of the sea beyond its freezing point.
Wrong where: there are no fjords or glacial lakes, and the edges of ice sheets will be wrong. Permafrost under deep
snow, and at the edges of its zone, will be wrong. The thresholds are not tested against a map of Earth's frozen
ground; the reference data hold none.
"""
import numpy as np

from ..process import Process

OPEN, SEASONAL_SNOW, LASTING_ICE, SEA_ICE = 0, 1, 2, 3          # what covers a cell, for the cause record


class ThresholdCryosphere(Process):
    stage = "climate"
    reads = ("surface_temperature", "ocean_mask")
    reads_lagged = ("snow_water",)
    writes = ("snow_ice_cover", "permafrost")
    model = "sea ice below the freezing point of sea water, snow and lasting ice from the snow store, permafrost from the year's mean"
    drivers = {"snow_ice_cover": ("covered_by",), "permafrost": ("yearly_mean",)}

    def run(self, ctx):
        c = ctx.const
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        t = ctx.read("surface_temperature").astype(np.float64)                      # (months, n), kelvin
        store = np.maximum(ctx.read_lagged("snow_water").astype(np.float64), 0.0)   # mm of water
        sea_ice = np.clip(0.5 + (c["sea_freezes_below_k"] - t) / c["sea_ice_ramp_k"], 0.0, 1.0)
        snow = np.minimum(store / c["full_cover_mm"], 1.0)
        lasting = ~sea & (store.min(axis=0) > 0.0)
        cover = np.where(sea[None, :], sea_ice, snow)
        yearly = t.mean(axis=0)
        full, none = c["permafrost_full_below_k"], c["permafrost_none_above_k"]
        frozen = np.where(sea, 0.0, np.clip((none - yearly) / (none - full), 0.0, 1.0))
        ctx.write("snow_ice_cover", cover)
        ctx.write("permafrost", frozen)
        if ctx.recording:
            kind = np.where(sea[None, :], np.where(sea_ice > 0, SEA_ICE, OPEN),
                            np.where(lasting[None, :], LASTING_ICE, np.where(snow > 0, SEASONAL_SNOW, OPEN)))
            ctx.driver("snow_ice_cover", "covered_by", kind.astype(np.int32))
            ctx.driver("permafrost", "yearly_mean", yearly)
