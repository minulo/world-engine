import sys, runpy
import os as _os
HERE = _os.path.dirname(_os.path.abspath(__file__))   # the folder of these scripts
sys.argv = sys.argv[:2]
g = runpy.run_path(HERE + "/exp_core.py")
