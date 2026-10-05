"""The engine: runs the stages on their clocks, in the order the scheduler computed.

Design, Layers 2, 3, 6 and 7. The engine owns everything that is not a natural system:
the field store, the rounds of each clock, the copies read from the previous round and
their blending, the test that decides whether the climate has settled, the push hook,
and the cause records. Processes never call each other; they meet only here.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import math
import time
from pathlib import Path
from types import MappingProxyType

import numpy as np

from . import __version__
from . import interventions as iv
from .draws import Draws
from .fields import Registry
from .mesh import get_mesh
from .params import ParameterError, Parameters, fingerprint, freeze
from .process import ContractError, GroupValue, Process, declaration
from .scheduler import DEFAULT, PUSH, Plan, schedule, visible


class EngineError(Exception):
    """The engine cannot do what was asked; the message says why."""


NOTE_KEYS = frozenset({"kind", "slot", "stage", "what", "first_round", "last_round", "rounds"})     # what every note holds
START_ROUND = 0                 # the round number a start step runs under, before round 1


def _resolve_level(value, level, where):
    """A constant may be given per mesh level, as {by_level: {5: ..., 7: ...}}."""
    if isinstance(value, dict) and set(value) == {"by_level"}:
        table = value["by_level"]
        if level not in table:
            raise ParameterError(f"{where}: no value for mesh level {level} (given for: {sorted(table)})")
        return table[level]
    if isinstance(value, dict):
        return {k: _resolve_level(v, level, f"{where}.{k}") for k, v in value.items()}
    return value


def _resolve_files(value, params, where):
    """A constant may be a table kept in a category file, given as {from_file: {file: biomes, key: biomes}}."""
    if isinstance(value, dict) and set(value) == {"from_file"}:
        src = value["from_file"]
        try:
            return params[src["file"]][src["key"]]
        except KeyError:
            raise ParameterError(f"{where}: from_file names {src}, which does not exist") from None
    if isinstance(value, dict):
        return {k: _resolve_files(v, params, f"{where}.{k}") for k, v in value.items()}
    return value


def _lookup(mapping, dotted):
    cur = mapping
    for part in dotted.split("."):
        cur = cur[part]
    return cur


class World:
    """Everything a finished or half-built world holds in memory."""

    def __init__(self, mesh, months):
        self.mesh, self.months, self.n = mesh, months, mesh.n
        self.fields: dict[str, np.ndarray] = {}
        self.lagged: dict[str, np.ndarray] = {}
        self.tables: dict[str, dict] = {}
        self.lagged_tables: dict[str, dict] = {}
        self.group_now: dict[str, dict] = {}
        self.group_lagged: dict[str, dict] = {}
        self.group_const: dict[str, dict] = {}
        self.drivers: dict[str, dict] = {}
        self.push_records: dict[str, dict] = {}
        self.push_activity: dict[str, dict] = {}             # push id -> the rounds in which it acted, and whether it touched a cell
        self.group_records: dict[str, dict] = {}
        self.written_round: dict[str, int] = {}
        self.notices: list[dict] = []
        self.rounds_used: dict[str, int] = {}
        self.settled: dict[str, bool] = {}
        self.settle_log: list[dict] = []
        self.lineage: dict[str, dict] = {}
        self.timings: dict[str, float] = {}
        self.round_times: list[dict] = []                    # seconds spent in each step of each round
        self.meta: dict = {}

    def notice(self, kind, **details):
        entry = {"kind": kind, **details}
        if kind == "field_outside_range":                    # one notice per field: that of the value the world ends with
            self.clear_notices(kind, field=details.get("field"))
        if entry not in self.notices:
            self.notices.append(entry)

    def clear_notices(self, kind, **match):
        """Drop the notices of one kind whose details equal `match`: what they said is no longer true of the world."""
        self.notices = [n for n in self.notices if not (n["kind"] == kind and all(n.get(k) == v for k, v in match.items()))]

    def note(self, slot, stage, round_no, what, details):
        """A process's own note. One entry per slot and wording, with the rounds it was raised in, so that a note
        raised in every round of a long history stays one line."""
        for n in self.notices:
            if n["kind"] == "process_note" and n["slot"] == slot and n["what"] == what and n["stage"] == stage:
                n.update(details, last_round=round_no, rounds=n["rounds"] + (round_no != n["last_round"]))
                return
        self.notices.append({"kind": "process_note", "slot": slot, "stage": stage, "what": what, **details,
                             "first_round": round_no, "last_round": round_no, "rounds": 1})

    def fingerprints(self) -> dict:
        """SHA-256 of every field's and table column's stored bytes."""
        out = {}
        for name in sorted(self.fields):
            a = self.fields[name]
            out[name] = hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
        for t in sorted(self.tables):
            for col in sorted(self.tables[t]):
                out[f"table:{t}.{col}"] = hashlib.sha256(np.ascontiguousarray(self.tables[t][col]).tobytes()).hexdigest()
        return out

    def fingerprint(self) -> str:
        blob = "".join(f"{k}={v};" for k, v in self.fingerprints().items())
        return hashlib.sha256(blob.encode()).hexdigest()


class Context:
    """What one process is handed for one round. Reaching for anything undeclared fails at once."""

    def __init__(self, engine, name, proc, decl, stage, round_no, when, step_length, recording, replay):
        self._e, self._w = engine, engine.world
        self._name, self._proc, self._decl, self._stage = name, proc, decl, stage
        self._recording, self._replay = recording, replay
        self._written: set = set()
        self.mesh = engine.mesh
        self.planet = engine.planet
        self.months = engine.months
        self.const = engine.constants[name]
        self.shared = engine.shared_for[name]
        self.round = round_no
        self.step_length = step_length
        self.draw = Draws(engine.seed, name, engine.allowed_draws.get(name, ()), when)
        # A place to keep what is costly to prepare and stays the same from round to round (a solver, a table).
        # It is this process's own: no other process sees it. The key of an entry must hold everything the entry
        # depends on, because the engine empties the memo only at the start of a build and of each climate run.
        self.memo = engine.memo.setdefault(name, {})
        self.recording = recording

    # ---- reads
    def _table(self, name):
        return name[len("table:"):]

    def read(self, name):
        if name not in self._decl["reads"] and name not in self._decl["modifies"]:
            raise ContractError(f"{self._name} read {name}, which it did not declare under reads or modifies")
        if name.startswith("table:"):
            t = self._w.tables.get(self._table(name))
            if t is None:
                raise EngineError(f"{self._name} read {name} before anything wrote it")
            return MappingProxyType(t)                       # read-only: the columns are read-only arrays, and so is the list of them
        self._e._require_fresh(name, self._stage, self._name)
        return self._w.fields[name]

    def read_lagged(self, name):
        if name not in self._decl["lagged"]:
            raise ContractError(f"{self._name} read {name} from the previous round, which it did not declare")
        if name.startswith("table:"):                        # as for a field: the kept copy in its own stage, the stored table elsewhere
            own = self._e.table_stage.get(self._table(name)) == self._stage
            t = (self._w.lagged_tables if own else self._w.tables).get(self._table(name))
            return MappingProxyType(t if t is not None else self._e._empty_table(self._table(name)))
        return self._e._lagged_value(name, self._stage)

    def read_group(self, group) -> GroupValue:
        if group not in self._decl["group_reads"]:
            raise ContractError(f"{self._name} read group {group} in the same round, which it did not declare")
        value = self._e._group_value(group, False, self._stage, self.round, self._recording)
        if self._recording:
            self._w.group_records[group] = dict(value.members)
        return value

    def read_group_lagged(self, group) -> GroupValue:
        if group not in self._decl["lagged_group"]:
            raise ContractError(f"{self._name} read group {group} from the previous round, which it did not declare")
        value = self._e._group_value(group, True, self._stage, self.round, self._recording)
        if self._recording:                                  # the cause record names each member of the sum
            self._w.group_records[group] = dict(value.members)
        return value

    def categories(self, field) -> tuple:
        """The class names of a category field this process declared."""
        d = self._decl
        if field not in d["reads"] + d["lagged"] + d["writes"] + d["modifies"]:
            raise ContractError(f"{self._name} asked for the classes of {field}, which it did not declare")
        return self._e.registry.fields[field].categories

    # ---- writes
    def write(self, name, value):
        if name in self._decl["contributes"].values():
            raise ContractError(f"{self._name} must hand {name} to its group with add_to_group")
        if name not in self._decl["writes"] and name not in self._decl["modifies"]:
            raise ContractError(f"{self._name} wrote {name}, which it did not declare under writes or modifies")
        if name.startswith("table:"):
            raise ContractError(f"{self._name}: a table is written with write_table")
        self._e._store_field(name, value, self._stage, self._name, self.round, self._replay)
        self._written.add(name)

    def write_table(self, name, columns: dict):
        if name not in self._decl["writes"]:
            raise ContractError(f"{self._name} wrote {name}, which it did not declare under writes")
        self._e._store_table(self._table(name), columns, self._name, self._replay)
        self._written.add(name)

    def add_to_group(self, group, value):
        if group not in self._decl["contributes"]:
            raise ContractError(f"{self._name} added to group {group}, which it did not declare")
        member = self._decl["contributes"][group]
        self._e._store_field(member, value, self._stage, self._name, self.round, self._replay)
        self._w.group_now.setdefault(group, {})[member] = self._w.fields[member]
        self._written.add(member)

    def note(self, what: str, **details):
        """Record a fact about this run in the world store, such as a solver that stopped at its cap.
        It does not stop the run; the viewer and the "why" answers repeat it. A note says something about
        the round it is raised in: in the climate stage only the notes of the settled round are kept."""
        taken = sorted(set(details) & NOTE_KEYS)
        if taken:
            raise ContractError(f"{self._name}: a note cannot carry a detail named {', '.join(taken)}; the engine uses "
                                f"those names itself ({', '.join(sorted(NOTE_KEYS))})")
        self._w.note(self._name, self._stage, self.round, what, details)

    # ---- cause records
    def driver(self, field, term, value):
        """Record one named term of an output. Kept only in a recording pass."""
        if field not in self._decl["writes"] and field not in self._decl["modifies"] and field not in self._decl["contributes"].values():
            raise ContractError(f"{self._name} recorded a driver for {field}, which it does not write")
        if term not in self._proc.drivers.get(field, ()):
            raise ContractError(f"{self._name} recorded the driver {term} for {field}, which its driver list does not name")
        a = np.asarray(value)                                # the shape is checked in every round, so that a mistake shows at once
        want = self._e.registry.fields[field].array_shape(self._w.n, self._w.months)
        if a.shape not in (want, (self._w.n,), (self._w.months, self._w.n)):
            raise ValueError(f"driver {term} of {field} has shape {a.shape}; expected {want} or one value per cell")
        if not self._recording:
            return
        a = a.astype(np.float32 if a.dtype.kind == "f" else np.int32)
        a.flags.writeable = False
        self._w.drivers.setdefault(field, {})[term] = a

    def _finish(self, starting=False):
        if starting:
            return
        missing = [f for f in list(self._decl["writes"]) + list(self._decl["contributes"].values()) if f not in self._written]
        if missing:
            raise ContractError(f"{self._name} declared but did not write: {', '.join(missing)}")
        if self._recording:
            for f, terms in self._proc.drivers.items():
                lost = [t for t in terms if t not in self._w.drivers.get(f, {})]
                if lost:
                    raise ContractError(f"{self._name} did not record the drivers it lists for {f}: {', '.join(lost)}")


class Engine:
    """Loads the parameter files, computes the order, and builds a world."""

    def __init__(self, data_dir, profile: str = "standard", seed=None, overrides: dict | None = None, log=None):
        self.log = log or (lambda msg: None)
        self.params = Parameters(data_dir, overrides)
        p = self.params
        profiles = p["profiles"]["profiles"]
        if profile not in profiles:
            raise ParameterError(f"profiles.yaml has no profile named {profile!r} (it has: {', '.join(profiles)})")
        self.profile_name, self.profile = profile, profiles[profile]
        self.level = int(self.profile["mesh_level"])
        self.planet = freeze(p["planet"])
        self.months = int(p["planet"].get("months_per_year", 12))
        self.seed = seed if seed is not None else p["seeds"]["world_seed"]
        self.allowed_draws = {k: tuple(v) for k, v in (p["seeds"].get("draws") or {}).items()}
        self.threads = int(self.profile.get("math_threads", 1))

        self.registry = Registry(p)
        self.pushes = iv.parse(p["interventions"], self.registry)
        self.registry.with_label_classes(iv.label_classes(self.pushes, self.registry))
        self.stage_list = [s["name"] for s in p["stages"]["stages"]]
        twice = sorted({name for name in self.stage_list if self.stage_list.count(name) > 1})
        if twice:
            raise ParameterError(f"stages.yaml names the stage {', '.join(twice)} more than once; every stage needs its own name")
        self.stage_cfg = {s["name"]: s for s in p["stages"]["stages"]}
        self.clocks = {s["name"]: s["clock"] for s in p["stages"]["stages"]}

        # processes: models.yaml says which implementation fills each slot
        self.procs: dict[str, Process] = {}
        self.constants, self.shared_for, self.decls = {}, {}, {}
        shared = _resolve_level(p["models"].get("shared") or {}, self.level, "models.yaml.shared")
        for slot, cfg in (p["models"].get("slots") or {}).items():
            proc = self._load_implementation(slot, cfg["implementation"])
            decl = declaration(proc)
            must = sorted(cfg.get("writes", []))
            has = sorted(decl["writes"] + list(decl["contributes"].values()))
            if must != has:
                raise ParameterError(f"models.yaml.slots.{slot}: the slot must write {must}, but {cfg['implementation']} writes {has}")
            for purpose in proc.draws:
                if purpose not in self.allowed_draws.get(slot, ()):
                    raise ParameterError(f"seeds.yaml does not list the draw {purpose!r} that {slot} declares")
            missing = [s for s in proc.shared if s not in shared]
            if missing:
                raise ParameterError(f"models.yaml.shared lacks the constants {missing} that {slot} names")
            self.procs[slot], self.decls[slot] = proc, decl
            where = f"models.yaml.slots.{slot}.constants"
            self.constants[slot] = freeze(_resolve_files(_resolve_level(cfg.get("constants") or {}, self.level, where), p, where))
            self.shared_for[slot] = freeze({s: shared[s] for s in proc.shared})
        self._check_names()

        self.plan: Plan = schedule(
            self.decls, [q.schedule_entry() for q in self.pushes], stages=self.stage_list, clocks=self.clocks,
            groups=set(self.registry.groups), tables=self.registry.table_names(), labels=self.registry.labels,
            kind=self.registry.kind, structural=self.registry.structural,
            steps_of_dated={s: c.get("step", "day") for s, c in self.stage_cfg.items() if c["clock"] == "dated"})
        unused = sorted(slot for slot in (p["explanations"] or {}) if slot not in self.procs)
        if unused:                                           # (a world built from some of the slots, or a misspelt slot)
            self.plan.notes.append(f"explanations.yaml holds sentence patterns for {', '.join(unused)}, which this world does "
                                   f"not fill: they are not used")
        self.push_by_step = {PUSH % q.id: q for q in self.pushes}
        self.push_by_id = {q.id: q for q in self.pushes}
        self.stage_of = {f: self.plan.steps[w]["stage"] for f, w in self.plan.producer.items()}
        # the stage in which each member of a group is worked out
        self.member_stage = {(g, self.plan.steps[m]["contributes"][g]): self.plan.steps[m]["stage"]
                             for g, ms in self.plan.members.items() for m in ms}
        self.table_stage = {f[len("table:"):]: self.plan.steps[w]["stage"] for f, w in self.plan.producer.items()
                            if f.startswith("table:")}
        self._check_settings()
        steps = self.plan.steps.values()
        self.lagged_fields = sorted({f for d in steps for f in d["lagged"] if not f.startswith("table:")})
        self.lagged_tables = sorted({f[len("table:"):] for d in steps for f in d["lagged"] if f.startswith("table:")})
        self.lagged_groups = sorted({g for d in steps for g in d["lagged_group"]})
        self.mesh = None
        self.world: World | None = None
        self.memo: dict = {}
        self._fresh: dict[str, set] = {}
        self._weights: dict[str, np.ndarray] = {}
        self._received: set = set()                          # pushes on groups that some reader was given, in any round
        self._last_given: dict = {}                          # (group, read from the previous round) -> pushes in the last recorded sum
        self._applied: dict[str, np.ndarray] = {}            # push with a condition -> the weights of its last round in force
        self._rounds_in_force: dict[str, set] = {}

    # ------------------------------------------------------------------ set-up helpers
    @contextlib.contextmanager
    def _limit_threads(self):
        """The thread count of the mathematics libraries for the length of a build (design, Layer 8). The limit is
        taken when a build or a harness run starts and handed back when it ends, so that two engines in one
        interpreter do not set each other's count. That holds for the compiled loops (numba) as for the libraries."""
        import numba
        from threadpoolctl import threadpool_limits
        before = numba.get_num_threads()
        numba.set_num_threads(max(1, min(self.threads, numba.config.NUMBA_NUM_THREADS)))
        try:
            with threadpool_limits(limits=self.threads):
                yield
        finally:
            numba.set_num_threads(before)

    @staticmethod
    def _load_implementation(slot, path) -> Process:
        try:
            module, cls = path.split(":")
            proc = getattr(importlib.import_module(module), cls)()
        except (ValueError, ImportError, AttributeError) as e:
            raise ParameterError(f"models.yaml.slots.{slot}: cannot load the implementation {path!r}: {e}") from None
        if not isinstance(proc, Process):
            raise ParameterError(f"models.yaml.slots.{slot}: {path} is not a Process")
        return proc

    def _check_names(self):
        """Every declared name must have a dictionary entry, so that a misspelled name cannot pass silently."""
        problems = []
        for slot in self.procs:                              # the key of a random draw is seed|slot|purpose|round
            for name in (slot, *self.allowed_draws.get(slot, ())):
                if "|" in name:
                    problems.append(f"the name {name!r} contains the bar |, which separates the parts of a draw's key; "
                                    f"with it two different draws could get the same key")
        for slot, d in self.decls.items():
            for f in d["reads"] + d["lagged"] + d["writes"] + d["modifies"] + list(d["contributes"].values()):
                if f.startswith("table:"):
                    if f[len("table:"):] not in self.registry.tables:
                        problems.append(f"{slot} names {f}, which tables.yaml does not declare")
                elif f not in self.registry.fields:
                    problems.append(f"{slot} names the field {f}, which fields.yaml does not declare")
            if d["stage"] not in self.stage_list:
                problems.append(f"{slot} names stage {d['stage']}, which stages.yaml does not contain")
            for g, member in d["contributes"].items():        # a member has the layout of its group
                if g in self.registry.groups and member in self.registry.fields:
                    fs, gs = self.registry.fields[member], self.registry.groups[g]
                    if fs.kind != "number" or fs.shape != gs.shape:
                        problems.append(f"{slot} adds {member} ({fs.kind}, {fs.shape}) to group {g}, which holds a number "
                                        f"per {gs.shape}; a member must have the layout of its group")
        for q in self.pushes:
            if not q.on_group and q.target not in self.registry.fields and not q.target.startswith("table:"):
                problems.append(f"push {q.id} targets {q.target}, which fields.yaml does not declare")
            for c in q.region.conditions:
                if c.field not in self.registry.fields:
                    problems.append(f"push {q.id} tests {c.field}, which fields.yaml does not declare")
            problems += iv.check(q, self.registry, self.months)
        # A sentence pattern of the "why" answers may name only what its process records. The walk passes over a
        # driver it does not find, so a misspelt one would leave the answer short without a word.
        for slot, patterns in (self.params["explanations"] or {}).items():
            if slot not in self.procs:
                continue                                     # a slot this world does not fill: the next loop says so
            d, recorded = self.decls[slot], self.procs[slot].drivers
            written = set(d["writes"]) | set(d["modifies"]) | set(d["contributes"].values())
            for field, pattern in (patterns or {}).items():
                where = f"explanations.yaml: {slot}.{field}"
                if field not in written:
                    problems.append(f"{where}: {slot} does not write {field}, so this pattern would never be used")
                    continue
                spoken = (pattern or {}).get("drivers") or {}
                named = set(spoken) | {p["at"] for p in spoken.values() if p and p.get("at")}
                named |= {t for case in (pattern or {}).get("cases") or [] for t in (case.get("when") or {})}
                unknown = sorted(named - set(recorded.get(field, ())))
                if unknown:
                    problems.append(f"{where}: the pattern names the driver {', '.join(unknown)}, which {slot} does not record "
                                    f"for {field} (it records: {', '.join(recorded.get(field, ())) or 'none'})")
        if problems:
            raise ParameterError("; ".join(problems))

    def _check_settings(self):
        """Settings that name something not built yet, or that mean nothing where they stand, are refused, not ignored."""
        problems = []
        for name, cfg in self.stage_cfg.items():
            if "step" in cfg and cfg["clock"] != "dated":
                problems.append(f"stages.yaml: stage {name} gives a step, which only a stage that steps through dates takes")
            if "first_date" in cfg and cfg["clock"] != "dated":
                problems.append(f"stages.yaml: stage {name} gives a first date, which only a stage that steps through dates takes")
            if cfg["clock"] in ("weather", "dated") and visible(self.plan.order[name]):
                problems.append(f"stages.yaml: stage {name} runs on the {cfg['clock']} clock, which is built in step 8; until then "
                                f"it must stay empty, but it holds {', '.join(visible(self.plan.order[name]))}")
            elif cfg["clock"] in ("weather", "dated") and self.plan.order[name]:
                problems.append(f"stages.yaml: stage {name} runs on the {cfg['clock']} clock, which is built in step 8; until then "
                                f"no label field may belong to it")
            for key in ("round_length_my", "history_length_my"):
                if key in cfg and cfg["clock"] != "geological":
                    problems.append(f"stages.yaml: stage {name} gives {key}, which only a stage on the geological clock takes")
            if cfg["clock"] == "geological" and not ("round_length_my" in cfg and "history_length_my" in cfg):
                problems.append(f"stages.yaml: stage {name} runs on the geological clock and needs round_length_my and history_length_my")
        if self.profile.get("snapshot_every_rounds") is not None or self.profile.get("snapshot_fields"):
            problems.append(f"profiles.yaml: profile {self.profile_name} asks for snapshots of the geological history; "
                            f"they are built in step 3, with the plate history")
        if self.profile.get("climate_rerun_every_rounds") is not None:
            problems.append(f"profiles.yaml: profile {self.profile_name} reruns the climate inside the geological history; "
                            f"that link is built in step 9")
        for q in self.pushes:                                # when.rounds counts geological rounds
            if q.rounds is None:
                continue
            if q.on_group:
                stages = {st for (g, _), st in self.member_stage.items() if g == q.target} | \
                         {d["stage"] for d in self.plan.steps.values() if q.target in d["lagged_group"] + d["group_reads"]}
            else:
                stages = {self.stage_of.get(q.target)}
            late = sorted(st for st in stages if st is not None and self.clocks[st] != "geological")
            if late:
                problems.append(f"push {q.id} is limited to geological rounds {q.rounds[0]} to {q.rounds[1]}, but its target "
                                f"belongs to stage {', '.join(late)}, which does not run on the geological clock; a push "
                                f"limited to part of the history can act on the climate only once the climate is rerun "
                                f"inside the history (build step 9)")
        if problems:
            raise ParameterError("; ".join(problems))

    def order(self) -> dict:
        """The computed order per stage, as the design's tables show it."""
        return {s: visible(self.plan.order[s]) for s in self.stage_list}

    # ------------------------------------------------------------------ field store
    def _require_fresh(self, name, stage, reader):
        if name not in self.world.fields:
            raise EngineError(f"{reader} read {name} before anything wrote it")
        if self.stage_of.get(name) == stage and name not in self._fresh.setdefault(stage, set()):
            raise EngineError(f"{reader} read {name} before its writer ran in this round; the order is wrong")

    def _lagged_value(self, name, stage):
        spec = self.registry.fields[name]
        w = self.world
        if self.stage_of.get(name) == stage:
            if name in w.lagged:
                return w.lagged[name]
        elif name in w.fields:                               # the value that its own stage last stored
            return w.fields[name]
        a = spec.default_array(w.n, w.months)                # first round: the default is the first guess
        a.flags.writeable = False
        return a

    def _empty_table(self, name):
        return {c: np.zeros(0, dtype=t) for c, t in self.registry.tables[name].columns.items()}

    def _group_value(self, group, lagged, stage, round_no, recording=False) -> GroupValue:
        """A group as a reader in `stage` receives it. A read from the previous round gets the kept copy of the
        members worked out in the reader's own stage, and the stored value of the members of every other stage,
        exactly as a field read from the previous round does."""
        w = self.world
        spec = self.registry.groups[group]
        members = {k: v for k, v in w.group_now.get(group, {}).items()
                   if not lagged or self.member_stage.get((group, k)) != stage}
        if lagged:
            members.update({k: v for k, v in w.group_lagged.get(group, {}).items() if self.member_stage.get((group, k)) == stage})
        at = round_no - 1 if lagged else round_no            # the round whose sum the reader is given
        given = {}                                           # the pushes that this sum holds, each with the round it was made in
        for key in members:                                  # a push with a condition is a member worked out in its place
            q = self.push_by_id.get(key[len("push:"):]) if key.startswith("push:") else None
            if q is not None:                                # (a test harness may hand over a member under such a name)
                made_in = self.member_stage.get((group, key))
                made_at = at if made_in == stage else w.rounds_used.get(made_in, 0)     # another stage's member is read as stored
                if made_at >= 1 and self._push_active(q, made_in, made_at):
                    given[q.id] = made_at
        # A push with a fixed region is the same in every round it is in force. Before the first round of a history
        # nothing was in force: there a read from the previous round gets no push, whichever kind of region it has.
        # The climate clock has no history: its rounds are a solver's working steps, and the push is there from the first.
        before_the_history = at < 1 and self.clocks.get(stage) == "geological"
        for key, value in w.group_const.get(group, {}).items():
            q = self.push_by_id[key[len("push:"):]]
            if not before_the_history and self._push_active(q, stage, at):
                members[key] = value
                given[q.id] = at
        self._received |= set(given)
        if recording:
            self._last_given[(group, lagged)] = given
        total = np.zeros(spec.array_shape(w.n, w.months))
        for k in sorted(members):
            total = total + members[k]
        total.flags.writeable = False
        return GroupValue(total, members)

    def _store_field(self, name, value, stage, writer, round_no, replay):
        spec = self.registry.fields[name]
        w = self.world
        try:
            a = spec.cast(value, w.n, w.months)
        except ValueError as e:
            raise ValueError(f"{writer}: {e}") from None
        bad = spec.outside_range(a)
        if bad:
            w.notice("field_outside_range", field=name, writer=writer, **bad)
        else:                                                # a notice from an earlier round or an earlier step no longer holds
            w.clear_notices("field_outside_range", field=name)
        w.fields[name] = a
        w.written_round[name] = round_no
        self._fresh.setdefault(stage, set()).add(name)

    def _store_table(self, name, columns, writer, replay):
        spec = self.registry.tables[name]
        if sorted(columns) != sorted(spec.columns):
            raise ContractError(f"{writer} wrote table {name} with columns {sorted(columns)}; tables.yaml lists {sorted(spec.columns)}")
        out, length = {}, None
        for c, t in spec.columns.items():
            given = np.asarray(columns[c])
            if given.dtype.kind not in "biuf":               # text, None, complex numbers, mixed lists
                raise ContractError(f"{writer} wrote table {name}: column {c} holds values of type {given.dtype}; a column "
                                    f"takes numbers or true and false")
            with np.errstate(invalid="ignore", over="ignore"):       # a value too large for the type is caught just below
                a = np.array(given, dtype=t, copy=True)
            if a.ndim != 1 or (length is not None and a.size != length):
                raise ContractError(f"{writer} wrote table {name}: every column must be one list of the same length")
            fits = True
            if a.dtype.kind in "iu" and given.dtype.kind in "iu" and a.size:      # a whole number outside the type would wrap round
                limits = np.iinfo(a.dtype)
                fits = int(given.min()) >= limits.min and int(given.max()) <= limits.max
            if a.dtype.kind in "iub" and given.dtype.kind in "iuf" and a.size and \
                    not (fits and np.array_equal(a.astype(given.dtype), given)):
                raise ContractError(f"{writer} wrote table {name}: column {c} holds values that do not fit its type {t} "
                                    f"(a fraction, or a number too large); they would be changed without a word")
            if a.dtype.kind == "f" and a.size and np.isinf(a).any():
                raise ContractError(f"{writer} wrote table {name}: column {c} holds an infinite value, or one too large for {t}")
            length = a.size
            a.flags.writeable = False
            out[c] = a
        self.world.tables[name] = out

    # ------------------------------------------------------------------ pushes
    def _push_weights(self, q, stage):
        spec_kind = "number" if q.on_group else self.registry.fields[q.target].kind
        number_like = spec_kind in ("number", "direction")
        if q.region.fixed and q.id in self._weights:
            return self._weights[q.id]

        def read_condition(cond):
            return self._lagged_value(cond.field, stage) if cond.lagged else self.world.fields[cond.field]

        region = q.region
        if region.conditions:
            conds = []
            for c in region.conditions:
                spec = self.registry.fields[c.field]
                value = c.value
                if spec.kind == "category":
                    names = value if isinstance(value, list) else [value]
                    value = [spec.code(x) for x in names] if c.test == "is_one_of" else spec.code(names[0])
                conds.append(iv.Condition(c.field, c.lagged, c.test, value, c.month))
            region = iv.Region(region.circle, region.outline, conds, region.edge_km)
        wts = iv.region_weights(region, self.mesh, float(self.planet["radius_m"]), read_condition, number_like)
        if q.region.fixed:
            self._weights[q.id] = wts
        return wts

    def _push_active(self, q, stage, round_no):
        """A push limited to rounds counts the rounds of the geological clock (elsewhere such a limit is refused on loading)."""
        if q.rounds is None or stage is None or self.clocks[stage] != "geological":
            return True
        return q.rounds[0] <= round_no <= q.rounds[1]

    def _acted(self, q, stage, round_no, wts):
        """Keep the rounds in which a push was in force and whether it ever covered a cell. In force means: applied
        to its field, or held in its group's sum, in that round; whether a process then read the sum is kept apart."""
        seen = self._rounds_in_force.setdefault(q.id, set())
        seen.add(round_no)                                   # the cause pass runs a round a second time: it counts once
        a = self.world.push_activity.setdefault(q.id, {"stage": stage, "first_round": round_no, "last_round": round_no,
                                                        "rounds": 0, "touched": False})
        # In a history every round counts: a push that covered a cell in any round changed the world. The rounds of the
        # climate clock are a solver's working steps: only the round the world ends with says whether a cell was covered.
        covered = bool(wts.any()) if self.clocks.get(stage) == "climate" else bool(a["touched"] or wts.any())
        a.update(first_round=min(seen), last_round=max(seen), rounds=len(seen), touched=covered)

    def _push_record(self, q, wts, **more):
        return {**more, "weight": wts.astype(np.float32), "physical": q.physical, "reason": q.reason,
                "entry": q.entry_id, "op": q.op}

    def _apply_push(self, step, stage, round_no, recording, replay):
        """One push in its place in the order. The record a push leaves describes the round the world ends with: a
        push that is outside its rounds in that round leaves none, because it did not act on the stored value."""
        q = self.push_by_step[step]
        w = self.world
        active = self._push_active(q, stage, round_no)
        if q.on_group:                                       # a member worked out every round, in its place in the order
            spec = self.registry.groups[q.target]
            shape = spec.array_shape(w.n, w.months)
            wts = self._push_weights(q, stage) if active else np.zeros(w.n)
            amount = iv.amount_array(q, "number", shape, w.months, self.mesh)
            member = (amount * wts).astype(np.float32)
            member.flags.writeable = False
            w.group_now.setdefault(q.target, {})["push:" + q.id] = member
            if active:                                       # its record is written at the end, if a reader was given it
                kept = self._applied.setdefault(q.id, {})    # the weights of this round and of the one before: a reader
                kept[round_no] = wts                         # is given the sum of one or the other
                for r in [r for r in kept if r < round_no - 1]:
                    del kept[r]
                self._acted(q, stage, round_no, wts)
            return
        spec = self.registry.fields[q.target]
        old = w.fields[q.target]
        self._require_fresh(q.target, stage, step)
        if not active:
            if recording:
                w.push_records.pop(q.id, None)
            return
        wts = self._push_weights(q, stage)
        amount = iv.amount_array(q, spec.kind, old.shape, w.months, self.mesh, code=spec.code)
        new = iv.apply_op(q.op, old, amount, wts, spec.kind)
        self._acted(q, stage, round_no, wts)
        if recording:
            w.push_records[q.id] = self._push_record(q, wts, field=q.target, before=old)
        self._store_field(q.target, new, stage, step, round_no, replay)

    def _constant_group_pushes(self):
        """A push on a group with a fixed region is worked out once: it is the same in every round it acts in."""
        w = self.world
        for group, ids in self.plan.constant_members.items():
            spec = self.registry.groups[group]
            for pid in ids:
                q = self.push_by_id[pid]
                wts = self._push_weights(q, None)
                amount = iv.amount_array(q, "number", spec.array_shape(w.n, w.months), w.months, self.mesh)
                member = (amount * wts).astype(np.float32)
                member.flags.writeable = False
                w.group_const.setdefault(group, {})["push:" + pid] = member

    def _finish_push_records(self):
        """After the last stage: the records of the pushes on groups, and a notice for every push that changed nothing.

        A push on a group leaves a record if the sum that a reader was last given held it: in the last round for a
        read of the same round, in the round before for a read from the previous round. The record of a push with a
        condition carries the weights the push had in the round that sum was made in (the later one, if the group is
        read both ways). A push is reported as having changed nothing if no process reads its group, if it was in
        force in no round, if no process read the group in a round whose sum held it, or if its region covered no cell."""
        w = self.world
        read = {g for d in self.plan.steps.values() for g in d["lagged_group"] + d["group_reads"]}
        last = {}                                            # push -> the round in which the sum last given was made
        for given in self._last_given.values():
            for pid, made_at in given.items():
                last[pid] = max(made_at, last.get(pid, made_at))
        for q in self.pushes:
            if not q.on_group:
                continue
            if q.region.fixed:                               # in force in every round of the first stage that uses the group
                users = {st for (g, _), st in self.member_stage.items() if g == q.target} | \
                        {d["stage"] for d in self.plan.steps.values() if q.target in d["lagged_group"] + d["group_reads"]}
                for stage in sorted(users, key=self.stage_list.index):
                    rounds = [r for r in range(1, w.rounds_used.get(stage, 0) + 1) if self._push_active(q, stage, r)]
                    for r in rounds:
                        self._acted(q, stage, r, self._weights[q.id])
                    if rounds:
                        break
            if q.id in last:
                if q.region.fixed:
                    wts = self._weights[q.id]
                else:                                        # the weights of the round the sum was made in
                    kept = self._applied[q.id]
                    wts = kept.get(last[q.id], kept[max(kept)])
                w.push_records[q.id] = self._push_record(q, wts, group=q.target)
        for q in self.pushes:
            act = w.push_activity.get(q.id)
            if q.on_group and q.target not in read:
                why = f"no process reads group {q.target}"
            elif act is None:
                why = "it was in no round that it applies to"
            elif q.on_group and q.id not in self._received:
                why = f"no process read group {q.target} in a round whose sum held it"
            elif not act["touched"]:
                why = None                                   # its region covers no cell
            else:
                continue
            w.notice("push_touched_nothing", push=q.id, **({"why": why} if why else {}))

    # ------------------------------------------------------------------ rounds
    def _run_round(self, stage, round_no, recording, replay=False, starting=False):
        w = self.world
        cfg = self.stage_cfg[stage]
        self._fresh[stage] = set()
        for g, members in w.group_now.items():               # this stage's members are worked out afresh; other stages' stay
            for key in [k for k in members if self.member_stage.get((g, k)) == stage]:
                del members[key]
        when = "start" if starting else round_no
        spent = {}
        w.round_times.append({"stage": stage, "round": round_no, "cause_pass": bool(replay), "start_step": bool(starting), "seconds": spent})
        for step in self.plan.order[stage]:
            t0 = time.perf_counter()
            if step.startswith("Default["):
                name = step[len("Default["):-1]
                if not starting:
                    spec = self.registry.fields[name]
                    self._store_field(name, spec.default_array(w.n, w.months), stage, step, round_no, replay)
            elif step in self.push_by_step:
                if not starting:
                    self._apply_push(step, stage, round_no, recording, replay)
            else:
                proc, decl = self.procs[step], self.decls[step]
                if starting and not decl["start"]:
                    continue
                ctx = Context(self, step, proc, decl, stage, round_no, when, cfg.get("round_length_my"), recording, replay)
                (proc.start if starting else proc.run)(ctx)
                ctx._finish(starting)
            spent[step] = time.perf_counter() - t0
            w.timings[step] = w.timings.get(step, 0.0) + spent[step]

    def _blend(self, old, new, weight, kind):
        """The copy kept for the next round: old + weight * (new - old). Where the old value is missing the new one
        is taken whole, so that a missing value cannot stay in the copy for ever."""
        if weight >= 1.0 or kind not in ("number", "direction"):
            return new
        old64, new64 = old.astype(np.float64), new.astype(np.float64)
        out = np.where(np.isnan(old64), new64, old64 + weight * (new64 - old64)).astype(new.dtype)
        out.flags.writeable = False
        return out

    def _end_round(self, stage, weight):
        """Keep this round's values for the lagged reads of the next round. In the climate stage the copy is a blend."""
        w = self.world
        for f in self.lagged_fields:
            if self.stage_of.get(f) != stage or f not in w.fields:
                continue
            spec = self.registry.fields[f]
            old = w.lagged.get(f)
            if old is None:
                old = spec.default_array(w.n, w.months)
            w.lagged[f] = self._blend(old, w.fields[f], weight, spec.kind)
        for g in self.lagged_groups:                         # the members worked out in this stage; others are read as stored
            now = {k: v for k, v in w.group_now.get(g, {}).items() if self.member_stage.get((g, k)) == stage}
            prev = w.group_lagged.get(g, {})
            merged = {k: v for k, v in prev.items() if self.member_stage.get((g, k)) != stage}
            for m in sorted(set(now) | {k for k in prev if self.member_stage.get((g, k)) == stage}):
                new = now.get(m)
                old = prev.get(m)
                if new is None:
                    new = np.zeros_like(old)
                if old is None:
                    old = np.zeros_like(new)
                merged[m] = self._blend(old, new, weight, "number")
            if merged:
                w.group_lagged[g] = merged
        for t in self.lagged_tables:
            if t in w.tables and self.table_stage.get(t) == stage:
                w.lagged_tables[t] = w.tables[t]

    def _gaps(self, stage, previous_classes, tol):
        """How far this round's values lie from the copies it was given (design, Layer 3: settled means two things).
        Everything the stage reads from its own previous round is tested: numbers and directions by their gap,
        classes, true-or-false values and index numbers by the share of the area that changed, groups by the gap of
        their sum, tables by whether they are the same."""
        w = self.world
        area = self.mesh.area / self.mesh.area.sum()
        report, settled = [], True
        default = tol["default_tolerance"]

        def measure(name, new, old, spec_settle):
            nonlocal settled
            new, old = new.astype(np.float64), old.astype(np.float64)
            lost = np.isnan(new) != np.isnan(old)            # a value that is missing in one and present in the other
            gap = np.where(np.isnan(new) | np.isnan(old), 0.0, np.abs(new - old))
            if gap.ndim == 3 or (gap.ndim == 2 and gap.shape[-1] == 3):
                gap, lost = np.sqrt((gap ** 2).sum(axis=-1)), lost.any(axis=-1)
            per_cell, lost_cell = (gap, lost) if gap.ndim == 1 else (gap.max(axis=0), lost.any(axis=0))
            mean_gap = float((gap * area).sum() / (1 if gap.ndim == 1 else gap.shape[0]))
            t = spec_settle or default
            share = float(area[(per_cell > t["cell"]) | lost_cell].sum())
            ok = mean_gap <= t["mean"] and share <= tol["cell_share"]
            settled &= ok
            report.append({"name": name, "mean_gap": mean_gap, "share_over_cell_tolerance": share, "ok": bool(ok)})

        def changed(name, new, old):
            nonlocal settled
            if old is None:
                share = 1.0
            else:
                diff = new != old
                share = float(area[diff if diff.ndim == 1 else diff.any(axis=0)].sum())
            ok = share <= tol["class_change_share"]
            settled &= ok
            report.append({"name": name, "share_changed_class": share, "ok": bool(ok)})

        for f in self.lagged_fields:
            spec = self.registry.fields[f]
            if self.stage_of.get(f) != stage or f not in w.fields:
                continue
            if spec.kind in ("number", "direction"):
                measure(f, w.fields[f], self._lagged_value(f, stage), spec.settle)
            else:                    # classes (label fields among them), true-or-false and index fields: the share of the
                changed(f, w.fields[f], self._lagged_value(f, stage))      # area that differs from the copy the round was given
        read_here = {g for d in self.plan.steps.values() if d["stage"] == stage for g in d["lagged_group"]}
        for g in sorted(read_here):                          # a group that only another stage reads this way is not this stage's loop
            if not any(self.plan.steps[m]["stage"] == stage for m in self.plan.members.get(g, [])):
                continue
            spec = self.registry.groups[g]
            zero = np.zeros(spec.array_shape(w.n, w.months))
            mine = lambda members: sum((v for k, v in sorted(members.items()) if self.member_stage.get((g, k)) == stage), zero)
            measure("group:" + g, mine(w.group_now.get(g, {})), mine(w.group_lagged.get(g, {})), spec.settle)
        for f, spec in self.registry.fields.items():         # the classes that nothing reads from the previous round
            if spec.kind != "category" or spec.is_label or self.stage_of.get(f) != stage or f not in w.fields or f in self.lagged_fields:
                continue
            changed(f, w.fields[f], previous_classes.get(f))
        for t in self._loop_tables(stage):
            now, old = w.tables.get(t), w.lagged_tables.get(t)
            same = now is not None and old is not None and all(self._same_column(now[c], old[c], default["cell"]) for c in now)
            settled &= same
            report.append({"name": "table:" + t, "unchanged": bool(same), "ok": bool(same)})
        return settled, report

    @staticmethod
    def _same_column(a, b, tolerance):
        if a.shape != b.shape:
            return False
        if a.dtype.kind != "f":
            return bool(np.array_equal(a, b))
        return bool(np.array_equal(np.isnan(a), np.isnan(b)) and np.all(np.abs(np.nan_to_num(a) - np.nan_to_num(b)) <= tolerance))

    def _loop_tables(self, stage):
        """Tables that a process of the stage reads from the previous round and that the stage itself writes."""
        steps = [d for d in self.plan.steps.values() if d["stage"] == stage]
        return sorted({f[len("table:"):] for d in steps for f in d["lagged"]
                       if f.startswith("table:") and self.table_stage.get(f[len("table:"):]) == stage})

    def _has_loop(self, stage):
        """True if anything the stage works out is read by the stage from its own previous round."""
        steps = [d for d in self.plan.steps.values() if d["stage"] == stage]
        return any(self.stage_of.get(f) == stage for d in steps for f in d["lagged"] if not f.startswith("table:")) or \
            any(self.plan.steps[m]["stage"] == stage for d in steps for g in d["lagged_group"] for m in self.plan.members.get(g, [])) or \
            bool(self._loop_tables(stage))

    def _start(self, stage):
        """Start steps fill state before round 1 (design, Layer 2): a table that a process carries from round to round."""
        if any(self.decls[s]["start"] for s in self.plan.order[stage] if s in self.decls):
            self._run_round(stage, START_ROUND, recording=False, starting=True)
            for t in self.lagged_tables:
                if t in self.world.tables and self.table_stage.get(t) == stage:
                    self.world.lagged_tables[t] = self.world.tables[t]
            for f in sorted(self._fresh.get(stage, ())):     # a field filled by a start step is round 1's "previous round"
                if f in self.lagged_fields:
                    self.world.lagged[f] = self.world.fields[f]
            for g in self.lagged_groups:                     # ... and so is what a start step added to a group
                added = {k: v for k, v in self.world.group_now.get(g, {}).items() if self.member_stage.get((g, k)) == stage}
                if added:
                    self.world.group_lagged.setdefault(g, {}).update(added)

    def _run_once(self, stage):
        self._start(stage)
        self._run_round(stage, 1, recording=True)
        self._end_round(stage, 1.0)
        self.world.rounds_used[stage] = 1

    def _run_geological(self, stage):
        cfg = self.stage_cfg[stage]
        rounds = max(1, math.ceil(cfg["history_length_my"] / cfg["round_length_my"] - 1e-9))
        self._start(stage)
        for r in range(1, rounds + 1):
            self._run_round(stage, r, recording=True)      # geological causes are recorded as the stage runs
            self._end_round(stage, 1.0)
            self.log(f"  {stage} round {r} of {rounds}")
        self.world.rounds_used[stage] = rounds

    def _run_climate(self, stage):
        """Repeat the stage until it is steady, then record the causes in one extra pass over the settled round."""
        w = self.world
        tol = self.profile["climate"]
        cap, weight = int(tol["max_rounds"]), float(tol["blend_weight"])
        for f in self.lagged_fields:                         # every climate run starts from the same first guess
            if self.stage_of.get(f) == stage:
                w.lagged.pop(f, None)
        for g in self.lagged_groups:                         # ... for the members and the tables of this stage too
            kept = {k: v for k, v in w.group_lagged.get(g, {}).items() if self.member_stage.get((g, k)) != stage}
            w.group_lagged.pop(g, None)
            if kept:
                w.group_lagged[g] = kept
        for t in self.lagged_tables:
            if self.table_stage.get(t) == stage:
                w.lagged_tables.pop(t, None)
        self.memo = {}
        self._start(stage)
        loop = self._has_loop(stage)
        previous_classes, settled, r = {}, False, 0
        for r in range(1, cap + 1):
            self._run_round(stage, r, recording=False)
            if not loop:                                     # nothing is read from the previous round: one pass is the answer
                settled = True
                break
            settled, report = self._gaps(stage, previous_classes, tol)
            w.settle_log.append({"stage": stage, "round": r, "settled": bool(settled), "gaps": report})
            worst = max((g.get("mean_gap", g.get("share_changed_class", 0.0)) for g in report), default=0.0)
            self.log(f"  {stage} round {r}: {'settled' if settled else 'not settled'} (largest gap {worst:.4g})")
            if settled or r == cap:
                break
            previous_classes = {f: w.fields[f] for f, s in self.registry.fields.items()
                                if s.kind == "category" and not s.is_label and self.stage_of.get(f) == stage and f in w.fields}
            self._end_round(stage, weight)
        w.rounds_used[stage], w.settled[stage] = r, bool(settled)
        if not settled:
            w.notice("climate_not_settled", stage=stage, rounds=r)
        # The cause pass: the settled round is run once more with the same inputs, recording drivers.
        # It must leave every field as it was, and the engine checks that it did.
        # Notes and range notices of the rounds before it described working steps; only those of this pass are kept.
        w.notices = [n for n in w.notices if not (n["kind"] == "process_note" and n["stage"] == stage
                                                    and n["last_round"] != START_ROUND)]      # a start step's note stays
        for f in self.stage_of:
            if self.stage_of[f] == stage:
                w.clear_notices("field_outside_range", field=f)
        before = {f: a for f, a in w.fields.items() if self.stage_of.get(f) == stage}
        tables_before = {t: dict(c) for t, c in w.tables.items()}
        self._run_round(stage, r, recording=True, replay=True)
        for f, a in before.items():
            if not np.array_equal(a, w.fields[f], equal_nan=a.dtype.kind == "f"):
                raise EngineError(f"{f} changed when the settled round was run again for the cause records; a process "
                                  f"must give the same output for the same input ({self.plan.producer[f]} wrote it)")
        for t, cols in tables_before.items():
            if any(not np.array_equal(cols[c], w.tables[t][c], equal_nan=cols[c].dtype.kind == "f") for c in cols):
                raise EngineError(f"table {t} changed when the settled round was run again for the cause records")

    def _check_ranges(self):
        """Each model states the range of planet parameters in which it is expected to hold (design, Layer 9)."""
        for slot, cfg in (self.params["models"].get("slots") or {}).items():
            for key, (lo, hi) in (cfg.get("expected_range") or {}).items():
                if key.startswith("stage."):
                    _, st, setting = key.split(".", 2)
                    value = self.stage_cfg.get(st, {}).get(setting)
                else:
                    value = _lookup(self.params["planet"], key)
                if value is not None and not (lo <= value <= hi):
                    self.world.notice("model_outside_range", slot=slot, parameter=key, value=value, expected=[lo, hi])

    def _settle_of(self, stage) -> dict:
        """The tolerances of the settle test that fields.yaml sets for what this stage reads from its previous round."""
        out = {f: self.registry.fields[f].settle for f in self.lagged_fields
               if self.stage_of.get(f) == stage and self.registry.fields[f].settle}
        read_here = {g for d in self.plan.steps.values() if d["stage"] == stage for g in d["lagged_group"]}
        out.update({"group:" + g: self.registry.groups[g].settle for g in sorted(read_here) if self.registry.groups[g].settle})
        return out

    def _first_guess_of(self, stage) -> dict:
        """The first guesses that a climate run of this stage starts from: the defaults of fields.yaml for the fields
        that the stage reads from its previous round. The rounds stop within a tolerance of the steady state, not at
        it, so the place they started from is still in the last digits of every field of the stage."""
        return {f: (None if isinstance(d, float) and d != d else d)
                for f, d in ((f, self.registry.fields[f].default) for f in self.lagged_fields if self.stage_of.get(f) == stage)}

    def _lineage(self):
        w = self.world
        for f, writer in self.plan.producer.items():
            if f.startswith("table:") or f not in w.fields:
                continue
            d = self.plan.steps[writer]
            proc = self.procs.get(writer)
            pushes = [q for q in self.pushes if not q.on_group and q.target == f]
            groups = list(d["lagged_group"]) + list(d["group_reads"])
            modifiers = [m for m in self.plan.modifiers.get(f, []) if m in self.procs]
            describe = lambda q: {"id": q.id, "op": q.op, "amount": q.amount, "circle": q.region.circle,
                                  "outline": q.region.outline, "edge_km": q.region.edge_km, "rounds": q.rounds,
                                  "where": [[c.field, c.test, c.value, c.lagged, c.month] for c in q.region.conditions]}
            # groups that the writer or a modifier of the field reads: a push on any of them shaped the field
            all_groups = set(groups) | {g for m in modifiers for g in self.plan.steps[m]["lagged_group"] + self.plan.steps[m]["group_reads"]}
            draws = any(self.procs[x].draws for x in [writer, *modifiers] if x in self.procs)
            handed = {"constants": self.constants.get(writer, {}), "shared": self.shared_for.get(writer, {}),
                      "planet": self.planet, "pushes": [describe(q) for q in pushes],
                      "group_pushes": [describe(q) for q in self.pushes if q.on_group and q.target in all_groups],
                      "modifiers": {m: {"constants": self.constants.get(m, {}), "shared": self.shared_for.get(m, {})}
                                    for m in modifiers},
                      "mesh_level": self.level,
                      "stage": self.stage_cfg[d["stage"]],           # the clock, and the length and number of its rounds
                      "seed": self.seed if draws else None,          # the seed counts where a draw is made
                      "climate": self.profile["climate"] if self.clocks[d["stage"]] == "climate" else None,
                      # the tolerances that decide when the rounds of the stage stop shaped every field of it,
                      # and so did the first guesses from which its rounds set out
                      "settle": self._settle_of(d["stage"]) if self.clocks[d["stage"]] == "climate" else None,
                      "first_guess": self._first_guess_of(d["stage"]) if self.clocks[d["stage"]] == "climate" else None}
            w.lineage[f] = {
                "writer": writer, "stage": d["stage"], "model": proc.model if proc else "the engine's default for a label field",
                "version": proc.version if proc else __version__,
                "fingerprint": fingerprint(handed), "reads": list(d["reads"]), "reads_lagged": list(d["lagged"]),
                "groups": groups, "modified_by": modifiers,
                "pushes": [q.id for q in pushes], "round": w.written_round.get(f)}

    # ------------------------------------------------------------------ the build
    def build(self) -> World:
        with self._limit_threads():
            return self._build()

    def _build(self) -> World:
        t0 = time.perf_counter()
        self.mesh = get_mesh(self.level)
        self.world = w = World(self.mesh, self.months)
        self._fresh, self._weights, self.memo = {}, {}, {}
        self._received, self._last_given, self._applied, self._rounds_in_force = set(), {}, {}, {}
        self._check_ranges()
        self._constant_group_pushes()
        for stage in self.stage_list:
            clock = self.clocks[stage]
            steps = visible(self.plan.order[stage])
            if not self.plan.order[stage]:                   # no process, no push and no label field: nothing to run
                continue
            self.log(f"stage {stage} ({clock}): {' -> '.join(steps) or 'no process'}")
            if clock == "once":
                self._run_once(stage)
            elif clock == "geological":
                self._run_geological(stage)
            elif clock == "climate":
                self._run_climate(stage)
            else:                                            # refused on loading: see _check_settings
                raise EngineError(f"stage {stage} runs on the {clock} clock, which is built in step 8")
        self._finish_push_records()
        self._lineage()
        w.meta = {
            "engine_version": __version__, "profile": self.profile_name, "mesh_level": self.level, "cells": w.n,
            "months": self.months, "seed": self.seed, "math_threads": self.threads,
            "order": self.order(), "notes": list(self.plan.notes), "rounds_used": dict(w.rounds_used),
            "settled": dict(w.settled), "parameters_fingerprint": self.params.fingerprint(),
            "mesh": self.mesh.describe(), "build_seconds": time.perf_counter() - t0,
        }
        limit = self.profile.get("run_time_limit_s")
        if limit is not None and w.meta["build_seconds"] > limit:
            w.notice("run_time_over_limit", profile=self.profile_name, seconds=round(w.meta["build_seconds"], 1), limit_s=limit)
        return w
