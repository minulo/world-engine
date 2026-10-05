"""Contract tests, applied to every process automatically (design, Layer 9)."""
import ast
import importlib
from pathlib import Path

import numpy as np
import pytest
import yaml

from conftest import DATA, ROOT
from worldengine.process import Process

PROCESS_DIR = ROOT / "src" / "worldengine" / "processes"
LIBRARY_DIR = ROOT / "src" / "worldengine" / "library"
FILES = sorted(p for p in PROCESS_DIR.glob("*.py") if p.name != "__init__.py")
LIBRARY_FILES = sorted(p for p in LIBRARY_DIR.glob("*.py") if p.name != "__init__.py")
ALLOWED_NUMBERS = {0, 1, 2, 3, 4, 0.5, -1}


def slots():
    return yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))["slots"]


def implementation(path) -> Process:
    module, cls = path.split(":")
    return getattr(importlib.import_module(module), cls)()


@pytest.mark.parametrize("path", FILES + LIBRARY_FILES, ids=[p.stem for p in FILES] + [f"library.{p.stem}" for p in LIBRARY_FILES])
def test_process_code_holds_no_number_outside_the_allowed_list(path):
    """Every model constant lives in models.yaml. Code may hold only small whole numbers and one half; a named
    constant at the top of the file (a class code, a number of mathematics, a limit of the numerical method) is
    allowed. The library that the processes share keeps the same rule: a model constant reaches it as an argument,
    from the process that read it from models.yaml, and never sits in its code."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, (ast.Name, ast.Tuple)) for t in node.targets):
            names = [n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            if all(n.isupper() or "_" in n and n.upper() == n for n in names):
                top_level.update(id(c) for c in ast.walk(node.value))
    bad = [(n.lineno, n.value) for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
           and id(n) not in top_level and n.value not in ALLOWED_NUMBERS]
    assert not bad, f"numbers that belong in models.yaml: {bad}"


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_processes_do_not_import_each_other_and_draw_only_through_the_engine(path):
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = "." * node.level + (node.module or "")
            assert "processes" not in target and not (node.level == 1 and node.module not in (None,)), \
                f"{path.name} imports {target}: a process may import the library and the contract, never another process"
            assert node.module not in ("random", "secrets")
        if isinstance(node, ast.Import):
            assert all(a.name not in ("random", "secrets") for a in node.names)
        if isinstance(node, ast.Attribute) and node.attr == "random" and isinstance(node.value, ast.Name) and node.value.id == "np":
            raise AssertionError(f"{path.name} uses np.random; every random draw goes through the engine's draw function")
    assert "fastmath" not in text


def test_every_slot_names_its_model_and_what_it_ignores():
    for slot, cfg in slots().items():
        proc = implementation(cfg["implementation"])
        assert proc.model, f"{slot} states no model name for the lineage"
        for key in ("model", "ignores", "wrong_where", "standing"):
            assert cfg.get(key), f"models.yaml: {slot} lacks {key}"
        doc = importlib.import_module(cfg["implementation"].split(":")[0]).__doc__ or ""
        assert "Ignores" in doc and "Wrong where" in doc, f"{slot}: the file must say what its model ignores and where it will be wrong"


def test_every_additive_field_lists_its_drivers_and_every_driver_field_is_written():
    for slot, cfg in slots().items():
        proc = implementation(cfg["implementation"])
        outputs = set(proc.writes) | set(proc.modifies) | set(proc.adds_to.values())
        assert set(proc.drivers) <= outputs, f"{slot} lists drivers for fields it does not write"
        assert set(proc.additive) <= set(proc.drivers), f"{slot} calls a field additive without listing its drivers"


def test_every_listed_draw_is_declared_by_its_process():
    seeds = yaml.safe_load((DATA / "seeds.yaml").read_text(encoding="utf-8"))["draws"]
    for slot, purposes in seeds.items():
        proc = implementation(slots()[slot]["implementation"])
        assert sorted(purposes) == sorted(proc.draws)
