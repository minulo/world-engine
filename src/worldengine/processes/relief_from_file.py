"""Relief read from a file: a planet's measured relief in place of a model of it.

Model (Test). None: the height of every cell is read from a file that holds one number per
cell of the mesh. tools/earth_twin.py makes such a file from ETOPO5, the mean height of
Earth's land and sea floor over each cell, and puts this process in the Isostasy slot. The
engine's sea, climate and water then run on Earth's own relief, and their results can be held
against Earth: the Earth twin. No seeded world uses this process.

The file is named in the constants with its SHA-256, and the process refuses a file that does
not match, so that the copy of the parameters kept in a world still says exactly what made it.

Ignores: everything that Tectonics and Isostasy work out. The fields of the crust still come
from the seeded plates and have nothing to do with this relief.
Wrong where: a strait or a gorge narrower than a cell is closed, since a cell's height is the
mean of its ground: on the standard mesh the Black Sea, the Red Sea and the Baltic are cut off
from the ocean. Lakes are given by their surface in some places and by their bed in others.
"""
import hashlib

import numpy as np

from ..process import Process


class ReliefFromFile(Process):
    stage = "geological"
    writes = ("elevation",)
    model = "measured relief read from a file (the Earth twin)"

    def run(self, ctx):
        path, expected = ctx.const["file"], ctx.const["sha256"]
        with open(path, "rb") as f:
            found = hashlib.sha256(f.read()).hexdigest()
        if found != expected:
            raise ValueError(f"the relief file {path} has SHA-256 {found}, and the constants name {expected}")
        relief = np.load(path)
        if relief.shape != (ctx.mesh.n,) or not np.isfinite(relief).all():
            raise ValueError(f"the relief file {path} must hold one finite height for each of the {ctx.mesh.n} cells of this mesh")
        ctx.write("elevation", relief)
