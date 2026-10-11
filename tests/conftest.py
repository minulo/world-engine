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


def first_version_data(folder):
    """A copy of the data in which Albedo, Biomes and Soils are filled by their first versions again, with the constants
    they were built with (toy_data/first_versions.yaml), and the biome field takes its classes from Whittaker's chart."""
    import shutil
    import yaml
    target = Path(folder) / "first_version_data"
    if not target.exists():
        shutil.copytree(DATA, target)
        models = yaml.safe_load((target / "models.yaml").read_text(encoding="utf-8"))
        first = yaml.safe_load((HERE / "toy_data" / "first_versions.yaml").read_text(encoding="utf-8"))
        models["slots"].update(first["slots"])
        (target / "models.yaml").write_text(yaml.safe_dump(models, sort_keys=False, allow_unicode=True), encoding="utf-8")
        fields = yaml.safe_load((target / "fields.yaml").read_text(encoding="utf-8"))
        fields["fields"]["biome"]["categories_from"] = {"file": "biomes", "key": "biomes"}
        (target / "fields.yaml").write_text(yaml.safe_dump(fields, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return target
