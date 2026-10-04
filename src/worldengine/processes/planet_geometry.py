"""PlanetGeometry: the geometry of a sphere.

Model: textbook geometry. Latitude, longitude and cell area follow from the mesh and the radius.
The Coriolis parameter is twice the spin rate times the sine of latitude.
Ignores: the flattening of a planet by its own spin.
Wrong where: fast-spinning planets, whose equators bulge.
"""
from ..library.units import TWO_PI
from ..process import Process


class SphereGeometry(Process):
    stage = "setup"
    writes = ("latitude", "longitude", "cell_area", "coriolis_parameter")
    model = "geometry of a sphere"

    def run(self, ctx):
        mesh, radius = ctx.mesh, ctx.planet["radius_m"]
        spin = TWO_PI / ctx.planet["rotation_period_s"]
        ctx.write("latitude", mesh.lat)
        ctx.write("longitude", mesh.lon)
        ctx.write("cell_area", mesh.area * radius * radius)
        ctx.write("coriolis_parameter", 2 * spin * mesh.xyz[:, 2])
