import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT / "src"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA = ROOT / "data"
TOY = HERE / "toy_data"


def _year_s():
    import yaml
    return float(yaml.safe_load((DATA / "planet.yaml").read_text(encoding="utf-8"))["year_length_s"])


YEAR_S = _year_s()               # the year of the default planet, read where the engine reads it


def tool(name):
    """A script of tools/ as a module (the folder is not a package)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
