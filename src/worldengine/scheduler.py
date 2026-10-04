"""The scheduler: turns declarations into a running order, or refuses with the reason (design, Layer 2).

It draws an arrow from each writer to each reader and sorts the steps of a stage so that every
arrow points forward. Ties are broken by name, so the result never varies. This is the routine
that the design document's check script tested, ported with the same rules and the same
refusal messages.

A declaration is a dict with the keys
    stage, reads, lagged, writes, modifies, contributes {group: member field}, lagged_group,
    group_reads, order (priority of a modifier), start
A table is named "table:<name>" inside reads, lagged and writes.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field

OPS = {"number": ["set", "add", "scale", "cap_max", "cap_min"], "direction": ["set", "add", "scale"],
       "category": ["set"], "boolean": ["set"]}
ALL_OPS = sorted({o for v in OPS.values() for o in v})
DEFAULT = "Default[%s]"      # the engine step that fills a label field with its default
PUSH = "Push[%s]"
CLOCK_KINDS = ("once", "geological", "climate", "weather", "dated")


class Refused(Exception):
    """The declarations cannot be ordered, or break a rule. The message names every problem found."""


def blank(stage, **kw):
    d = dict(stage=stage, reads=[], lagged=[], writes=[], modifies=[], contributes={}, lagged_group=[],
             group_reads=[], order=None, start=False)
    d.update(kw)
    return d


@dataclass
class Plan:
    order: dict                     # stage -> list of step names (processes and pushes) in running order
    steps: dict                     # step name -> declaration (processes, pushes that take a place, default fills)
    producer: dict                  # field or table -> the step that writes it
    modifiers: dict                 # field -> steps that modify it, in order
    members: dict                   # group -> steps that add to it in their place in the order
    constant_members: dict          # group -> ids of pushes with a fixed region
    notes: list = field(default_factory=list)

    def chain(self, name):
        return [self.producer[name]] + list(self.modifiers.get(name, []))


def find_loop(names, edges):
    """Return one loop among the given nodes as a list, or None."""
    color, stack = {}, []

    def dfs(a):
        color[a] = 1
        stack.append(a)
        for b in sorted(edges[a]):
            if b not in names:
                continue
            if color.get(b) == 1:
                return stack[stack.index(b):] + [b]
            if b not in color:
                r = dfs(b)
                if r:
                    return r
        color[a] = 2
        stack.pop()
        return None

    for n in sorted(names):
        if n not in color:
            r = dfs(n)
            if r:
                return r
    return None


def schedule(procs, pushes=(), *, stages, clocks, groups, tables, labels, kind, structural, steps_of_dated=None) -> Plan:
    """Compute the running order.

    procs       name -> declaration
    pushes      list of dicts: id, field or group, op, optional stage, where (plain reads), where_lagged
    stages      list of stage names in running order
    clocks      stage -> one of CLOCK_KINDS (a stage named nowhere runs once)
    groups      names of the declared groups
    tables      names of the declared tables, each as "table:<name>"
    labels      label field -> its stage
    kind        function: field name -> number, direction, category, boolean or index
    structural  function: field name -> True if a push cannot target it
    steps_of_dated  stage -> day, month or year, for stages on the dated clock
    """
    procs = copy.deepcopy(dict(procs))
    six = {s: i for i, s in enumerate(stages)}
    problems, notes, edges = [], [], defaultdict(set)
    producer, modifiers, members = {}, defaultdict(list), defaultdict(list)
    step = dict(steps_of_dated or {})
    clock = dict(clocks)
    for st, ck in sorted(clock.items()):
        if ck not in CLOCK_KINDS:
            problems.append(f"stage {st} names the clock {ck}, which does not exist (clocks: {', '.join(CLOCK_KINDS)})")
    for st in sorted(s for s, c in clock.items() if c == "dated"):
        if st not in six:
            problems.append(f"stage {st} is said to step through dates, but the stage list does not contain it")
            continue
        sp = step.get(st, "day")
        step[st] = sp
        if sp not in ("day", "month", "year"):
            problems.append(f"stage {st} steps by {sp}; a step is a day, a month or a year")
        for ws in stages:
            if clock.get(ws) == "weather" and six[st] < six[ws]:
                problems.append(f"stage {st} steps through dates but is listed before the {ws} stage, whose days it would read")
    kind_of = lambda st: clock.get(st, "once")
    stateless = lambda st: kind_of(st) == "weather"               # a stage that stores nothing between its rounds
    for n, d in procs.items():
        if d["stage"] not in six:
            problems.append(f"{n} names stage {d['stage']}, which the stage list does not contain")
        for f in d["writes"] + list(d["contributes"].values()):
            if f in producer:
                problems.append(f"two writers for {f}: {producer[f]} and {n}")
            producer[f] = n
        for g, f in d["contributes"].items():
            if g not in groups:
                problems.append(f"{n} adds to group {g}, which is not declared")
            members[g].append(n)
        for f in d["modifies"]:
            if f in labels:
                problems.append(f"{n} modifies {f}, a label field, which only a push may set")
            modifiers[f].append(n)
    for f, st in labels.items():                       # a label field: the engine's default fill stands in for its writer
        if f in producer:
            problems.append(f"{producer[f]} writes {f}, a label field, which no process may write")
        elif st not in six:
            problems.append(f"label field {f} names stage {st}, which the stage list does not contain")
        else:
            procs[DEFAULT % f] = blank(st, writes=[f])
            producer[f] = DEFAULT % f
    if problems:
        raise Refused("; ".join(problems))
    # process modifiers: each needs its own priority number; equal numbers on one field are refused
    for f, ms in modifiers.items():
        seen = {}
        for n in ms:
            o = procs[n]["order"]
            if o is None:
                problems.append(f"{n} modifies {f} but states no priority")
            elif o in seen:
                problems.append(f"{n} and {seen[o]} modify {f} with the same priority {o}")
            else:
                seen[o] = n
        ms.sort(key=lambda n: (procs[n]["order"] if procs[n]["order"] is not None else 0, n))
    # pushes. A field push becomes a step after all process modifiers, in file order. A group push with a fixed region
    # is a constant member of the sum and takes no place in the order. A region's condition is a declared read of the
    # push: a plain read by default, so the push runs after the writer of every field it tests; a condition marked
    # lagged reads the previous round. A group push with a condition is a member worked out every round, in its place.
    constant_members = defaultdict(list)

    def group_stage(g):
        sts = {procs[m]["stage"] for m in members.get(g, [])} | \
              {d["stage"] for d in procs.values() if g in d["lagged_group"] + d["group_reads"]}
        return sorted(sts, key=lambda s: six[s])

    for k, iv in enumerate(pushes):
        cond, cond_lag = list(iv.get("where", [])), list(iv.get("where_lagged", []))
        name = PUSH % iv["id"]
        if "group" in iv:
            g = iv["group"]
            if g not in groups:
                problems.append(f"push {iv['id']} adds to group {g}, which is not declared")
                continue
            if iv.get("op", "add") != "add":
                problems.append(f"push {iv['id']}: only add is allowed on a group")
            sts = group_stage(g)
            if "stage" in iv and sts and iv["stage"] not in sts:
                problems.append(f"push {iv['id']} is declared for stage {iv['stage']} but group {g} is used in stage {', '.join(sts)}")
            if not (cond or cond_lag):
                constant_members[g].append(iv["id"])
                continue
            st = iv.get("stage") or (sts[0] if sts else None)
            if st is None:
                problems.append(f"push {iv['id']} has a condition but group {g} has no member and no reader to give it a stage")
                continue
            procs[name] = blank(st, reads=cond, lagged=cond_lag, contributes={g: "push:" + iv["id"]})
            members[g].append(name)
            continue
        f = iv["field"]
        if f in tables:
            problems.append(f"push {iv['id']} targets {f}; tables cannot be pushed")
            continue
        if f not in producer:
            problems.append(f"push {iv['id']} targets {f}, which nothing writes")
            continue
        if structural(f):
            problems.append(f"push {iv['id']} targets {f}, which cannot be pushed: its values must obey rules that a push cannot see")
            continue
        op, fk = iv.get("op", "set"), kind(f)
        if op not in ALL_OPS:
            problems.append(f"push {iv['id']} uses the operation {op}, which does not exist")
            continue
        if op not in OPS[fk]:
            problems.append(f"push {iv['id']} uses {op} on {f}, a field of kind {fk}, which accepts only: {', '.join(OPS[fk])}")
            continue
        procs[name] = blank(procs[producer[f]]["stage"], modifies=[f], order=1000 + k, reads=cond, lagged=cond_lag)
        if "stage" in iv and iv["stage"] != procs[producer[f]]["stage"]:
            problems.append(f"push {iv['id']} is declared for stage {iv['stage']} but {f} is written in stage {procs[producer[f]]['stage']}")
        modifiers[f].append(name)
    chain = lambda f: [producer[f]] + modifiers.get(f, [])
    for n, d in procs.items():
        s, k = six[d["stage"]], kind_of(d["stage"])
        if stateless(d["stage"]) and (d["lagged"] or d["lagged_group"]):
            problems.append(f"{n} reads from the previous round in stage {d['stage']}, which keeps no memory")
        for f in d["reads"]:                               # the shortest loop there is: a process that reads its own output
            if f in d["writes"] or f in d["contributes"].values():
                problems.append(f"{n} reads {f}, which it writes itself; a process cannot read its own output of the same round")
        for g in d["group_reads"]:
            if g in d["contributes"]:
                problems.append(f"{n} reads group {g} in the same round and also adds to it")
        if k == "geological":                              # the crust moves under the mesh: nothing per cell is carried between rounds
            for f in d["lagged"]:
                if f in tables or f not in producer:
                    continue
                if kind_of(procs[producer[f]]["stage"]) == "geological":
                    who = "its own output" if producer[f] == n else f"the output of {producer[f]}"
                    problems.append(f"{n} reads {f}, {who}, from the previous round in stage {d['stage']}, where the crust moves under the mesh; a per-cell value of that clock cannot be carried between rounds on mesh cells, and what must travel with the crust is kept on the crust points")
        if k == "once":                                    # a stage that runs once has no previous round of its own
            for f in d["lagged"]:
                if f in producer and procs[producer[f]]["stage"] == d["stage"]:
                    problems.append(f"{n} reads {f} from the previous round, but stage {d['stage']} runs once and has no previous round")
        for f in sorted(set(d["reads"]) & set(d["modifies"])):
            problems.append(f"{n} lists {f} under both reads and modifies; modifies already means read and then change")
        for f in d["reads"] + d["lagged"]:
            if f not in producer:
                continue
            pst = procs[producer[f]]["stage"]
            pk = kind_of(pst)
            if pk == "weather" and pst != d["stage"]:      # a stage that stores nothing has nothing for another stage to read
                if k == "dated" and six[d["stage"]] > six[pst]:                 # ... except the weather of the date a dated stage is at
                    if step[d["stage"]] != "day":
                        problems.append(f"{n} (stage {d['stage']}) reads {f}, the weather of one day, but its stage steps by a {step[d['stage']]}")
                    elif f in d["lagged"]:
                        problems.append(f"{n} (stage {d['stage']}) reads {f} from the previous step, but the {pst} stage stores nothing; a stage that steps through dates reads only the weather of the date it is at")
                else:
                    problems.append(f"{n} (stage {d['stage']}) reads {f}, but the {pst} stage stores nothing for another stage to read")
            elif pk == "dated" and k != "dated":           # a stage that steps through dates is a dead end for every other stage
                problems.append(f"{n} (stage {d['stage']}) reads {f}, which stage {pst} writes; a stage that steps through dates is a dead end, and no stage without dates may read it")
            elif k == "dated" and pk != "dated" and f in d["lagged"]:
                problems.append(f"{n} (stage {d['stage']}) reads {f} from the previous step, but {f} belongs to stage {pst}, which does not step through dates; read it as it stands")
        for f in d["reads"]:
            if f not in producer:
                problems.append(f"{n} reads {f}, which nothing writes")
                continue
            if stateless(procs[producer[f]]["stage"]) and procs[producer[f]]["stage"] != d["stage"]:
                continue
            ps = six[procs[producer[f]]["stage"]]
            if ps > s:
                problems.append(f"{n} reads {f} from a later stage without marking the read as lagged")
            elif ps == s:
                for w in chain(f):
                    if w != n:
                        edges[w].add(n)
        for f in d["modifies"]:
            if f not in producer:
                problems.append(f"{n} modifies {f}, which nothing writes")
                continue
            if procs[producer[f]]["stage"] != d["stage"]:
                problems.append(f"{n} modifies {f} in stage {d['stage']}, but {f} is written in stage {procs[producer[f]]['stage']}")
                continue
            c = chain(f)
            edges[c[c.index(n) - 1]].add(n)
        for f in d["lagged"]:
            if f not in producer:
                problems.append(f"{n} reads {f} from the previous round, but nothing writes it")
        for g in d["lagged_group"] + d["group_reads"]:
            if g not in groups:
                problems.append(f"{n} reads group {g}, which is not declared")
            elif not members.get(g) and not constant_members.get(g):
                notes.append(f"{n}: group {g} has no members, sums to zero")
        for g in d["group_reads"]:                       # a group read "now": the reader runs after every member
            for m in members.get(g, []):
                if procs[m]["stage"] == d["stage"] and m != n:
                    edges[m].add(n)
                elif six[procs[m]["stage"]] > s:
                    problems.append(f"{n} reads group {g} in the same round, but its member {m} runs in the later stage {procs[m]['stage']}; the read must be marked as lagged")
        for g in d["lagged_group"] + d["group_reads"]:
            for m in members.get(g, []):
                mst = procs[m]["stage"]
                if stateless(mst) and mst != d["stage"]:  # a stage that stores nothing cannot feed a group another stage reads
                    problems.append(f"{m} adds to group {g} in the {mst} stage, which stores nothing, but {n} reads that group in stage {d['stage']}")
                elif kind_of(mst) == "dated" and k != "dated":   # nor can a stage that steps through dates: it is a dead end
                    problems.append(f"{m} adds to group {g} in stage {mst}, which steps through dates and is a dead end, but {n} reads that group in stage {d['stage']}")
    if problems:
        raise Refused("; ".join(problems))
    order = {}
    for st in stages:
        names = sorted(n for n, d in procs.items() if d["stage"] == st)
        indeg = {n: 0 for n in names}
        for a in names:
            for b in edges[a]:
                if b in indeg:
                    indeg[b] += 1
        out, ready = [], sorted(n for n in names if indeg[n] == 0)
        while ready:
            a = ready.pop(0)
            out.append(a)
            for b in sorted(edges[a]):
                if b in indeg:
                    indeg[b] -= 1
                    if indeg[b] == 0:
                        ready.append(b)
                        ready.sort()
        if len(out) != len(names):
            left = set(names) - set(out)
            loop = find_loop(left, edges)
            real = lambda xs: [n for n in xs if not n.startswith("Default[")]      # count processes and pushes, not engine steps
            raise Refused(f"loop in stage {st}: {' -> '.join(loop)} ; {len(real(left))} of {len(real(names))} processes cannot be ordered")
        order[st] = out
    return Plan(order=order, steps=procs, producer=producer, modifiers=dict(modifiers), members=dict(members),
                constant_members=dict(constant_members), notes=notes)


def visible(order_of_stage):
    """The steps of a stage without the engine's own default fills: what the design's tables show."""
    return [n for n in order_of_stage if not n.startswith("Default[")]
