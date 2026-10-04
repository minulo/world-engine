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
from .params import DEFAULT_DATA_DIR, Parameters, _load_yaml, freeze, validate
from .process import declaration


class Result:
    def __init__(self, world):
        self.fields, self.tables, self.drivers, self.notices = world.fields, world.tables, world.drivers, world.notices


def _merge(base, changes, where=None):
    """The base with the changes laid over it, key by key. With `where` given, a change may only replace a value that
    exists: a misspelt constant would otherwise change nothing and leave the test that sets it empty."""
    out = copy.deepcopy(base)
    for k, v in (changes or {}).items():
        if where is not None and k not in out:
            raise KeyError(f"{where} has no entry named {k!r} (it has: {', '.join(map(str, out)) or 'none'})")
        if isinstance(v, dict) and isinstance(out.get(k), dict) and set(out[k]) != {"from_file"}:
            out[k] = _merge(out[k], v, None if where is None else f"{where}.{k}")
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
        schema_dir = self.params.data_dir / "schemas"
        if not schema_dir.exists():
            schema_dir = DEFAULT_DATA_DIR / "schemas"
        validate(self._planet, _load_yaml(schema_dir / "planet.yaml")[1], "planet.yaml")     # as the engine would refuse it
        self.planet = freeze(self._planet)
        self.months = int(self._planet.get("months_per_year", 12))
        self.seed = seed
        self.allowed_draws = {k: tuple(v) for k, v in (self.params["seeds"].get("draws") or {}).items()}
        self.registry = Registry(self.params)
        self.threads = 1
        self.constants, self.shared_for, self.decls, self.procs = {}, {}, {}, {}
        self.memo = {}
        self.member_stage, self.table_stage, self.push_by_id = {}, {}, {}
        self.clocks = {s["name"]: s["clock"] for s in self.params["stages"]["stages"]}
        self._received, self._last_given, self._applied, self._rounds_in_force = set(), {}, {}, {}

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
        slots = self.params["models"]["slots"]
        if slot not in slots:
            raise KeyError(f"models.yaml has no slot named {slot!r} (it has: {', '.join(slots)})")
        cfg = slots[slot]
        proc = self._load_implementation(slot, cfg["implementation"])
        decl = declaration(proc)
        if start and not decl["start"]:
            raise ValueError(f"{slot} has no start step; start=True asks for one")
        where = f"models.yaml.slots.{slot}.constants"
        consts = _resolve_files(_resolve_level(_merge(cfg.get("constants") or {}, constants, where), self.level, where), self.params, where)
        all_shared = _merge(_resolve_level(self.params["models"].get("shared") or {}, self.level, "models.yaml.shared"), shared,
                            "models.yaml.shared")
        for kind, names, known in (("field", list(reads or {}) + list(lagged or {}), self.registry.fields),
                                   ("group", list(groups or {}), self.registry.groups),
                                   ("table", list(tables or {}) + list(lagged_tables or {}), self.registry.tables)):
            unknown = sorted(n for n in names if n not in known)
            if unknown:
                raise KeyError(f"the test hands {slot} the {kind} {', '.join(unknown)}, which the data files do not declare")
        # an input that the process does not declare would never be read: the test that gives it tests less than it says
        tabled = lambda names: {f[len("table:"):] for f in names if f.startswith("table:")}
        declared = {"reads": set(decl["reads"]) | set(decl["modifies"]), "lagged": set(decl["lagged"]),
                    "groups": set(decl["lagged_group"]) | set(decl["group_reads"]),
                    "tables": tabled(decl["reads"]), "lagged_tables": tabled(decl["lagged"])}
        for where_given, given in (("reads", reads), ("lagged", lagged), ("groups", groups), ("tables", tables),
                                   ("lagged_tables", lagged_tables)):
            unread = sorted(set(given or {}) - declared[where_given])
            if unread:
                raise KeyError(f"the test hands {slot} {', '.join(unread)} under {where_given}, but the process does not declare "
                               f"it there, so it would never read it")
        self.procs, self.decls = {slot: proc}, {slot: decl}
        self.constants = {slot: freeze(consts)}
        self.shared_for = {slot: freeze({s: all_shared[s] for s in proc.shared})}
        self.world = w = World(self.mesh, self.months)
        self.memo = {}                                       # nothing is carried from one run of the harness to the next
        stage = decl["stage"]
        self.stage_of = {f: "elsewhere" for f in list(reads or {}) + list(lagged or {})}
        self.stage_of.update({f: stage for f in decl["writes"] + decl["modifies"] + list(decl["contributes"].values())})
        self.member_stage = {(g, member): stage for g, member in decl["contributes"].items()}
        # a table read from the previous round is looked up among the kept copies, where the test put it
        self.table_stage = {t: stage for t in list(lagged_tables or {}) +
                            [f[len("table:"):] for f in decl["writes"] if f.startswith("table:")]}
        self._fresh = {stage: set()}
        for name, value in (reads or {}).items():
            w.fields[name] = self.registry.fields[name].cast(value, w.n, w.months)
            if name in decl["modifies"]:
                self._fresh[stage].add(name)
        for name, value in (lagged or {}).items():
            w.lagged[name] = self.registry.fields[name].cast(value, w.n, w.months)
            self.stage_of[name] = stage
        for group, members in (groups or {}).items():        # members as the engine would hand them: stored type, read-only
            want = self.registry.groups[group].array_shape(w.n, w.months)
            cast = {}
            for member, value in members.items():
                # as the engine would hand it over: a member that is a declared field in that field's stored type,
                # a push in the type the engine stores a push in
                a = np.array(value, dtype=self.registry.fields[member].dtype if member in self.registry.fields else np.float32)
                if a.shape != want:
                    raise ValueError(f"member {member} of group {group} must have shape {want}, got {a.shape}")
                a.flags.writeable = False
                cast[member] = a
            w.group_lagged[group] = dict(cast)
            w.group_now[group] = dict(cast)
        for name, cols in (tables or {}).items():            # tables through the engine's own door: typed, checked, read-only
            self._store_table(name, cols, "the test", False)
        for name, cols in (lagged_tables or {}).items():
            now = w.tables.pop(name, None)
            self._store_table(name, cols, "the test", False)
            w.lagged_tables[name] = w.tables.pop(name)
            if now is not None:
                w.tables[name] = now
        step = self.params["stages"]["stages"]
        length = next((s.get("round_length_my") for s in step if s["name"] == stage), None)
        with self._limit_threads():
            if start:
                ctx = Context(self, slot, proc, decl, stage, 0, "start", length, False, False)
                proc.start(ctx)
                for name in sorted(ctx._written):            # what the start step filled is the state that round 1 reads
                    t = name[len("table:"):]
                    if name.startswith("table:"):
                        if t in (lagged_tables or {}):
                            raise ValueError(f"start=True fills table {t}; a test cannot also give it under lagged_tables")
                        w.lagged_tables[t] = w.tables[t]
                    elif name in w.fields:                   # a field, as the engine hands it to round 1's read from the previous round
                        if name in (lagged or {}):
                            raise ValueError(f"start=True fills {name}; a test cannot also give it under lagged")
                        w.lagged[name] = w.fields[name]
                for group, member in decl["contributes"].items():    # and what the start step added to a group
                    if member in w.group_now.get(group, {}):
                        w.group_lagged.setdefault(group, {})[member] = w.group_now[group][member]
            ctx = Context(self, slot, proc, decl, stage, round_no, round_no, length, recording, False)
            proc.run(ctx)
            ctx._finish()
        return Result(w)
