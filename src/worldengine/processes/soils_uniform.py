"""Soils, first version: every soil holds the same depth of water.

Model (Rule). The bucket of Manabe's climate models gives every soil one capacity, "field
capacity everywhere 0.15 m" [DOCUMENTED: the description of the GFDL model,
https://pcmdi.llnl.gov/projects/modeldoc/cmip1/gfdl_tbls.html]. This process writes that one
number for every land cell, so that Hydrology reads the capacity of the soil as a field from
the start. The Soils process of build step 7 replaces this one and writes a capacity that
follows rock, slope, climate and age, with no change to Hydrology.

Ignores: everything that makes soils differ.
Wrong where: sand and bare rock, which hold far less; deep loams, which hold more [UNVERIFIED:
both from general knowledge of soils, not looked up]; and every soil property but this one,
which this version does not write at all.
"""
import numpy as np

from ..process import Process


IS_LAND, IS_SEA = range(2)


class UniformSoil(Process):
    stage = "climate"
    reads = ("ocean_mask",)
    writes = ("soil_water_capacity",)
    model = "one capacity for every soil (the field capacity of Manabe's bucket)"
    drivers = {"soil_water_capacity": ("cell_is",)}

    def run(self, ctx):
        sea = np.asarray(ctx.read("ocean_mask"), dtype=bool)
        ctx.write("soil_water_capacity", np.where(sea, 0.0, ctx.const["capacity_mm"]))
        ctx.driver("soil_water_capacity", "cell_is", np.where(sea, IS_SEA, IS_LAND).astype(np.int32))
