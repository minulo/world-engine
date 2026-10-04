"""The engine: runs the stages on their clocks, in the order the scheduler computed.

Design, Layers 2, 3, 6 and 7. The engine owns everything that is not a natural system:
the field store, the rounds of each clock, the copies read from the previous round and
their blending, the test that decides whether the climate has settled, the push hook,
and the cause records. Processes never call each other; they meet only here.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import time
from pathlib import Path

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
        if kind == "field_outside_range":                    # one notice per field: the latest round's
            self.notices = [n for n in self.notices if not (n["kind"] == kind and n.get("field") == details.get("field"))]
        if entry not in self.notices:
            self.notices.append(entry)

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
        self.memo = engine.memo
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
            return t
        self._e._require_fresh(name, self._stage, self._name)
        return self._w.fields[name]

    def read_lagged(self, name):
        if name not in self._decl["lagged"]:
            raise ContractError(f"{self._name} read {name} from the previous round, which it did not declare")
        if name.startswith("table:"):
            t = self._w.lagged_tables.get(self._table(name))
            return t if t is not None else self._e._empty_table(self._table(name))
        return self._e._lagged_value(name, self._stage)

    def read_group(self, group) -> GroupValue:
        if group not in self._decl["group_reads"]:
            raise ContractError(f"{self._name} read group {group} in the same round, which it did not declare")
        value = self._e._group_value(group, lagged=False)
        if self._recording:
            self._w.group_records[group] = dict(value.members)
        return value

    def read_group_lagged(self, group) -> GroupValue:
        if group not in self._decl["lagged_group"]:
            raise ContractError(f"{self._name} read group {group} from the previous round, which it did not declare")
        value = self._e._group_value(group, lagged=True)
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
        It does not stop the run; the viewer and the "why" answers repeat it."""
        self._w.notice("process_note", slot=self._name, what=what, **details)

    # ---- cause records
    def driver(self, field, term, value):
        """Record one named term of an output. Kept only in a recording pass."""
        if field not in self._decl["writes"] and field not in self._decl["modifies"] and field not in self._decl["contributes"].values():
            raise ContractError(f"{self._name} recorded a driver for {field}, which it does not write")
        if term not in self._proc.drivers.get(field, ()):
            raise ContractError(f"{self._name} recorded the driver {term} for {field}, which its driver list does not name")
        if not self._recording:
            return
        a = np.asarray(value)
        want = self._e.registry.fields[field].array_shape(self._w.n, self._w.months)
        if a.shape not in (want, (self._w.n,), (self._w.months, self._w.n)):
            raise ValueError(f"driver {term} of {field} has shape {a.shape}; expected {want} or one value per cell")
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
        self._limit_threads()

        self.registry = Registry(p)
        self.pushes = iv.parse(p["interventions"], self.registry)
        self.registry.with_label_classes(iv.label_classes(self.pushes, self.registry))
        self.stage_list = [s["name"] for s in p["stages"]["stages"]]
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
        self.push_by_step = {PUSH % q.id: q for q in self.pushes}
        self.stage_of = {f: self.plan.steps[w]["stage"] for f, w in self.plan.producer.items()}
        steps = self.plan.steps.values()
        self.lagged_fields = sorted({f for d in steps for f in d["lagged"] if not f.startswith("table:")})
        self.lagged_tables = sorted({f[len("table:"):] for d in steps for f in d["lagged"] if f.startswith("table:")})
        self.lagged_groups = sorted({g for d in steps for g in d["lagged_group"]})
        self.mesh = None
        self.world: World | None = None
        self.memo: dict = {}
        self._fresh: dict[str, set] = {}
        self._weights: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------ set-up helpers
    def _limit_threads(self):
        try:
            from threadpoolctl import threadpool_limits
            self._thread_limit = threadpool_limits(limits=self.threads)
        except ImportError:                                  # the lock file pins threadpoolctl; without it we say so
            self._thread_limit = None
        try:
            import numba
            numba.set_num_threads(max(1, min(self.threads, numba.config.NUMBA_NUM_THREADS)))
        except Exception:
            pass

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
        for slot, d in self.decls.items():
            for f in d["reads"] + d["lagged"] + d["writes"] + d["modifies"] + list(d["contributes"].values()):
                if f.startswith("table:"):
                    if f[len("table:"):] not in self.registry.tables:
                        problems.append(f"{slot} names {f}, which tables.yaml does not declare")
                elif f not in self.registry.fields:
                    problems.append(f"{slot} names the field {f}, which fields.yaml does not declare")
            if d["stage"] not in self.stage_list:
                problems.append(f"{slot} names stage {d['stage']}, which stages.yaml does not contain")
        for q in self.pushes:
            if not q.on_group and q.target not in self.registry.fields and not q.target.startswith("table:"):
                problems.append(f"push {q.id} targets {q.target}, which fields.yaml does not declare")
            for c in q.region.conditions:
                if c.field not in self.registry.fields:
                    problems.append(f"push {q.id} tests {c.field}, which fields.yaml does not declare")
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

    def _group_value(self, group, lagged) -> GroupValue:
        w = self.world
        spec = self.registry.groups[group]
        members = dict((w.group_lagged if lagged else w.group_now).get(group, {}))
        members.update(w.group_const.get(group, {}))
        total = np.zeros(spec.array_shape(w.n, w.months))
        for k in sorted(members):
            total = total + members[k]
        total.flags.writeable = False
        return GroupValue(total, members)

    def _store_field(self, name, value, stage, writer, round_no, replay):
        spec = self.registry.fields[name]
        w = self.world
        a = spec.cast(value, w.n, w.months)
        bad = spec.outside_range(a)
        if bad:
            w.notice("field_outside_range", field=name, writer=writer, **bad)
        w.fields[name] = a
        w.written_round[name] = round_no
        self._fresh.setdefault(stage, set()).add(name)

    def _store_table(self, name, columns, writer, replay):
        spec = self.registry.tables[name]
        if sorted(columns) != sorted(spec.columns):
            raise ContractError(f"{writer} wrote table {name} with columns {sorted(columns)}; tables.yaml lists {sorted(spec.columns)}")
        out, length = {}, None
        for c, t in spec.columns.items():
            a = np.array(columns[c], dtype=t, copy=True)
            if a.ndim != 1 or (length is not None and a.size != length):
                raise ContractError(f"{writer} wrote table {name}: every column must be one list of the same length")
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
        if q.rounds is None or self.clocks[stage] != "geological":
            return True
        return q.rounds[0] <= round_no <= q.rounds[1]

    def _apply_push(self, step, stage, round_no, recording, replay):
        q = self.push_by_step[step]
        w = self.world
        if q.on_group:                                       # a member worked out every round, in its place in the order
            spec = self.registry.groups[q.target]
            shape = spec.array_shape(w.n, w.months)
            wts = self._push_weights(q, stage) if self._push_active(q, stage, round_no) else np.zeros(w.n)
            amount = iv.amount_array(q, "number", shape, w.months, self.mesh)
            member = (amount * wts).astype(np.float32)
            member.flags.writeable = False
            w.group_now.setdefault(q.target, {})["push:" + q.id] = member
            if recording and not wts.any():
                w.notice("push_touched_nothing", push=q.id)
            return
        spec = self.registry.fields[q.target]
        old = w.fields[q.target]
        self._require_fresh(q.target, stage, step)
        if not self._push_active(q, stage, round_no):
            return
        wts = self._push_weights(q, stage)
        amount = iv.amount_array(q, spec.kind, old.shape, w.months, self.mesh, code=spec.code)
        new = iv.apply_op(q.op, old, amount, wts, spec.kind)
        w.push_records[q.id] = {"field": q.target, "before": old, "weight": wts.astype(np.float32),
                                "physical": q.physical, "reason": q.reason, "entry": q.entry_id, "op": q.op}
        if recording and not wts.any():
            w.notice("push_touched_nothing", push=q.id)
        self._store_field(q.target, new, stage, step, round_no, replay)

    def _constant_group_pushes(self):
        w = self.world
        for group, ids in self.plan.constant_members.items():
            spec = self.registry.groups[group]
            for pid in ids:
                q = next(x for x in self.pushes if x.id == pid)
                wts = self._push_weights(q, None)
                amount = iv.amount_array(q, "number", spec.array_shape(w.n, w.months), w.months, self.mesh)
                member = (amount * wts).astype(np.float32)
                member.flags.writeable = False
                w.group_const.setdefault(group, {})["push:" + pid] = member
                w.push_records[pid] = {"group": group, "weight": wts.astype(np.float32), "physical": q.physical,
                                       "reason": q.reason, "entry": q.entry_id, "op": q.op}
                if not wts.any():
                    w.notice("push_touched_nothing", push=pid)

    # ------------------------------------------------------------------ rounds
    def _run_round(self, stage, round_no, recording, replay=False, starting=False):
        w = self.world
        cfg = self.stage_cfg[stage]
        self._fresh[stage] = set()
        for g in list(w.group_now):
            if any(self.plan.steps[m]["stage"] == stage for m in self.plan.members.get(g, [])):
                w.group_now[g] = {}
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
        if weight >= 1.0 or kind not in ("number", "direction"):
            return new
        out = (old.astype(np.float64) + weight * (new.astype(np.float64) - old)).astype(new.dtype)
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
        for g in self.lagged_groups:
            now = w.group_now.get(g, {})
            prev = w.group_lagged.get(g, {})
            merged = {}
            for m in sorted(set(now) | set(prev)):
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
            if t in w.tables:
                w.lagged_tables[t] = w.tables[t]

    def _gaps(self, stage, previous_classes, tol):
        """How far this round's values lie from the copies it was given (design, Layer 3: settled means two things)."""
        w = self.world
        area = self.mesh.area / self.mesh.area.sum()
        report, settled = [], True
        default = tol["default_tolerance"]

        def measure(name, new, old, spec_settle):
            nonlocal settled
            gap = np.abs(new.astype(np.float64) - old.astype(np.float64))
            if gap.ndim == 3 or (gap.ndim == 2 and gap.shape[-1] == 3):
                gap = np.sqrt((gap ** 2).sum(axis=-1))
            per_cell = gap if gap.ndim == 1 else gap.max(axis=0)
            mean_gap = float((gap * area).sum() / (1 if gap.ndim == 1 else gap.shape[0]))
            t = spec_settle or default
            share = float(area[per_cell > t["cell"]].sum())
            ok = mean_gap <= t["mean"] and share <= tol["cell_share"]
            settled &= ok
            report.append({"name": name, "mean_gap": mean_gap, "share_over_cell_tolerance": share, "ok": bool(ok)})

        for f in self.lagged_fields:
            spec = self.registry.fields[f]
            if self.stage_of.get(f) != stage or spec.kind not in ("number", "direction") or f not in w.fields:
                continue
            measure(f, w.fields[f], self._lagged_value(f, stage), spec.settle)
        for g in self.lagged_groups:
            if not any(self.plan.steps[m]["stage"] == stage for m in self.plan.members.get(g, [])):
                continue
            spec = self.registry.groups[g]
            zero = np.zeros(spec.array_shape(w.n, w.months))
            now = sum((v for _, v in sorted(w.group_now.get(g, {}).items())), zero)
            old = sum((v for _, v in sorted(w.group_lagged.get(g, {}).items())), zero)
            measure("group:" + g, now, old, None)
        for f, spec in self.registry.fields.items():
            if spec.kind != "category" or spec.is_label or self.stage_of.get(f) != stage or f not in w.fields:
                continue
            if f not in previous_classes:
                changed = 1.0
            else:
                diff = w.fields[f] != previous_classes[f]
                changed = float(area[diff if diff.ndim == 1 else diff.any(axis=0)].sum())
            ok = changed <= tol["class_change_share"]
            settled &= ok
            report.append({"name": f, "share_changed_class": changed, "ok": bool(ok)})
        return settled, report

    def _has_loop(self, stage):
        steps = [d for d in self.plan.steps.values() if d["stage"] == stage]
        return any(self.stage_of.get(f) == stage for d in steps for f in d["lagged"] if not f.startswith("table:")) or \
            any(self.plan.steps[m]["stage"] == stage for d in steps for g in d["lagged_group"] for m in self.plan.members.get(g, []))

    def _start(self, stage):
        """Start steps fill state before round 1 (design, Layer 2): a table that a process carries from round to round."""
        if any(self.decls[s]["start"] for s in self.plan.order[stage] if s in self.decls):
            self._run_round(stage, 0, recording=False, starting=True)
            for t in self.lagged_tables:
                if t in self.world.tables:
                    self.world.lagged_tables[t] = self.world.tables[t]

    def _run_once(self, stage):
        self._start(stage)
        self._run_round(stage, 1, recording=True)
        self._end_round(stage, 1.0)
        self.world.rounds_used[stage] = 1

    def _run_geological(self, stage):
        cfg = self.stage_cfg[stage]
        rounds = max(1, math.ceil(cfg["history_length_my"] / cfg["round_length_my"] - 1e-9))
        if self.profile.get("climate_rerun_every_rounds"):
            raise EngineError("this profile reruns the climate inside the geological history; that link is built in step 9")
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
        for g in self.lagged_groups:
            w.group_lagged.pop(g, None)
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

    def _lineage(self):
        w = self.world
        for f, writer in self.plan.producer.items():
            if f.startswith("table:") or f not in w.fields:
                continue
            d = self.plan.steps[writer]
            proc = self.procs.get(writer)
            pushes = [q for q in self.pushes if not q.on_group and q.target == f]
            handed = {"constants": self.constants.get(writer, {}), "shared": self.shared_for.get(writer, {}),
                      "planet": self.planet,
                      "pushes": [{"id": q.id, "op": q.op, "amount": q.amount, "circle": q.region.circle,
                                  "outline": q.region.outline, "edge_km": q.region.edge_km,
                                  "where": [[c.field, c.test, c.value, c.lagged] for c in q.region.conditions]} for q in pushes]}
            w.lineage[f] = {
                "writer": writer, "stage": d["stage"], "model": proc.model if proc else "the engine's default for a label field",
                "version": proc.version if proc else __version__,
                "fingerprint": fingerprint(handed), "reads": list(d["reads"]), "reads_lagged": list(d["lagged"]),
                "groups": list(d["lagged_group"]) + list(d["group_reads"]),
                "modified_by": [m for m in self.plan.modifiers.get(f, []) if m in self.procs],
                "pushes": [q.id for q in pushes], "round": w.written_round.get(f)}

    # ------------------------------------------------------------------ the build
    def build(self) -> World:
        t0 = time.perf_counter()
        self.mesh = get_mesh(self.level)
        self.world = w = World(self.mesh, self.months)
        self._fresh, self._weights, self.memo = {}, {}, {}
        self._check_ranges()
        self._constant_group_pushes()
        for stage in self.stage_list:
            clock = self.clocks[stage]
            steps = visible(self.plan.order[stage])
            if not steps and not any(s == stage for s in self.registry.labels.values()):
                continue
            self.log(f"stage {stage} ({clock}): {' -> '.join(steps) or 'no process'}")
            if clock == "once":
                self._run_once(stage)
            elif clock == "geological":
                self._run_geological(stage)
            elif clock == "climate":
                self._run_climate(stage)
            elif clock == "weather":
                if steps:
                    raise EngineError(f"stage {stage} runs on the weather clock, which is built in step 8")
            else:
                raise EngineError(f"stage {stage} steps through dates; that clock is built in step 8")
        self._lineage()
        w.meta = {
            "engine_version": __version__, "profile": self.profile_name, "mesh_level": self.level, "cells": w.n,
            "months": self.months, "seed": self.seed, "math_threads": self.threads,
            "order": self.order(), "notes": list(self.plan.notes), "rounds_used": dict(w.rounds_used),
            "settled": dict(w.settled), "parameters_fingerprint": self.params.fingerprint(),
            "mesh": self.mesh.describe(), "build_seconds": time.perf_counter() - t0,
        }
        return w
