"""Relief read from a file: a planet's measured relief in place of a model of it.

Model (Test). None: the height of every cell is read from a file that holds one number per
cell of the mesh. tools/earth_twin.py makes such a file from ETOPO5, the mean height of
Earth's land and sea floor over each cell, and puts this process in the Isostasy slot. The
engine's sea, climate and water then run on Earth's own relief, and their results can be held
against Earth: the Earth twin. No seeded world uses this process.

The constants name the file and its SHA-256, and the process refuses a file that does not
match, so that the copy of the parameters kept in a world still says exactly what made it. A
file given by its bare name is looked for in the folder that the environment variable named
under folder_from_env holds: the parameters of the world then do not depend on where the file
lies on one machine.

Ignores: everything that Tectonics and Isostasy work out. A world built on this process has
no crust to explain its relief; the Earth twin leaves the Tectonics slot out.
Wrong where: a strait or a gorge narrower than a cell is closed, since a cell's height is the
mean of its ground: on the standard mesh the Black Sea, the Red Sea and the Baltic are cut off
from the ocean [MEASURED: tests/test_earth.py]. Lakes are given by their surface in some
places and by their bed in others [MEASURED on ETOPO5 by the reviewer of build step 2: the
Caspian and Baikal by their surface, Superior and Michigan by their bed].
"""
import hashlib
import os
from pathlib import Path

import numpy as np

from ..process import Process


class ReliefFromFile(Process):
    stage = "geological"
    writes = ("elevation",)
    model = "measured relief read from a file, not computed"

    def run(self, ctx):
        name, expected = ctx.const["file"], ctx.const["sha256"]
        variable = ctx.const.get("folder_from_env")
        if variable:
            if not os.environ.get(variable):
                raise ValueError(f"the relief file {name} is to be found in the folder named by the environment variable "
                                 f"{variable}, which is not set")
            path = Path(os.environ[variable]) / name
        else:
            path = Path(name)
        with open(path, "rb") as f:
            found = hashlib.sha256(f.read()).hexdigest()
        if found != expected:
            raise ValueError(f"the relief file {path} has SHA-256 {found}, and the constants name {expected}")
        relief = np.load(path)
        if relief.shape != (ctx.mesh.n,) or relief.dtype.kind != "f" or not np.isfinite(relief).all():
            raise ValueError(f"the relief file {path} must hold one finite height for each of the {ctx.mesh.n} cells of this mesh")
        ctx.write("elevation", relief)
