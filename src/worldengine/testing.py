"""The test harness: run one process alone, on inputs built for the purpose (design, Layer 9).

Because a process touches only declared fields, it can be fed any inputs and judged on its
outputs, with no other process present. The harness hands the process the same Context the
engine does, so the contract is enforced in a test exactly as in a build.

    h = Harness(level=4)
    out = h.run("Isostasy", reads={"crust_type": ..., "crust_thickness": ..., "ocean_crust_age": ...})
    out.fields["elevation"]
"""
from __future__ import annotations

import copy

import numpy as np

from .engine import Context, Engine, World, _resolve_files, _resolve_level
from .fields import Registry
from .mesh import get_mesh
from .params import DEFAULT_DATA_DIR, Parameters, freeze
from .process import declaration


class Result:
    def __init__(self, world):
        self.fields, self.tables, self.drivers, self.notices = world.fields, world.tables, world.drivers, world.notices


def _merge(base, changes):
    out = copy.deepcopy(base)
    for k, v in (changes or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Harness(Engine):
    """An engine that runs no stage: it holds the data files and a mesh, and runs single processes on request."""

    def __init__(self, level: int = 4, data_dir=DEFAULT_DATA_DIR, planet: dict | None = None, seed: int = 1):
        self.log = lambda msg: None
        self.params = Parameters(data_dir)
        self.level = level
        self.mesh = get_mesh(level)
        self._planet = _merge(self.params["planet"], planet)
        self.planet = freeze(self._planet)
        self.months = int(self._planet.get("months_per_year", 12))
        self.seed = seed
        self.allowed_draws = {k: tuple(v) for k, v in (self.params["seeds"].get("draws") or {}).items()}
        self.registry = Registry(self.params)
        self.threads = 1
        self._limit_threads()
        self.constants, self.shared_for, self.decls, self.procs = {}, {}, {}, {}
        self.memo = {}

    def run(self, slot, reads=None, lagged=None, groups=None, tables=None, lagged_tables=None, constants=None,
            shared=None, round_no=1, recording=True, start=False) -> Result:
        """Run one slot's process once.

        reads           field -> array, for its plain reads (and the fields it modifies)
        lagged          field -> array, for its reads from the previous round (a missing one gets the default)
        groups          group -> {member: array}, for the groups it reads
        tables          name -> {column: array}, for tables it reads as they stand
        lagged_tables   name -> {column: array}, for tables it reads from the previous round
        constants       changes to the slot's constants in models.yaml, merged key by key
        shared          changes to the shared constants
        start           True to call the process's start step before its run
        """
        cfg = self.params["models"]["slots"][slot]
        proc = self._load_implementation(slot, cfg["implementation"])
        decl = declaration(proc)
        where = f"models.yaml.slots.{slot}.constants"
        consts = _resolve_files(_resolve_level(_merge(cfg.get("constants") or {}, constants), self.level, where), self.params, where)
        all_shared = _merge(_resolve_level(self.params["models"].get("shared") or {}, self.level, "models.yaml.shared"), shared)
        self.procs, self.decls = {slot: proc}, {slot: decl}
        self.constants = {slot: freeze(consts)}
        self.shared_for = {slot: freeze({s: all_shared[s] for s in proc.shared})}
        self.world = w = World(self.mesh, self.months)
        self.memo = {}                                       # nothing is carried from one run of the harness to the next
        self.stage_of = {f: "elsewhere" for f in list(reads or {}) + list(lagged or {})}
        self.stage_of.update({f: decl["stage"] for f in decl["writes"] + decl["modifies"] + list(decl["contributes"].values())})
        self._fresh = {decl["stage"]: set()}
        for name, value in (reads or {}).items():
            w.fields[name] = self.registry.fields[name].cast(value, w.n, w.months)
            if name in decl["modifies"]:
                self._fresh[decl["stage"]].add(name)
        for name, value in (lagged or {}).items():
            w.lagged[name] = self.registry.fields[name].cast(value, w.n, w.months)
            self.stage_of[name] = decl["stage"]
        for group, members in (groups or {}).items():
            w.group_lagged[group] = dict(members)
            w.group_now[group] = dict(members)
        for name, cols in (tables or {}).items():
            w.tables[name] = {c: np.asarray(v) for c, v in cols.items()}
        for name, cols in (lagged_tables or {}).items():
            w.lagged_tables[name] = {c: np.asarray(v) for c, v in cols.items()}
        step = self.params["stages"]["stages"]
        length = next((s.get("round_length_my") for s in step if s["name"] == decl["stage"]), None)
        if start:
            ctx = Context(self, slot, proc, decl, decl["stage"], 0, "start", length, False, False)
            proc.start(ctx)
            for t in list(w.tables):
                w.lagged_tables[t] = w.tables[t]
        ctx = Context(self, slot, proc, decl, decl["stage"], round_no, round_no, length, recording, False)
        proc.run(ctx)
        ctx._finish()
        return Result(w)
