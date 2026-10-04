"""The process contract (design, Layer 2).

A process is one unit of code that computes one natural system. Before it runs it states the
stage it belongs to and what it reads, reads from the previous round, writes, modifies and
adds to a group. The running order, replaceability, external pushes, the lineage and the
ability to test a process alone all rest on that declaration.

A process is handed a Context and nothing else. Through it the process reaches only the
fields it declared, the mesh, the planet parameters, its own constants, the shared constants
it names, the round with the length of its step, and the engine's draw function.
"""
from __future__ import annotations


class ContractError(Exception):
    """A process reached for something it did not declare, or broke its declaration."""


class Process:
    stage: str = ""
    reads: tuple = ()                 # fields and tables ("table:<name>") at their current values
    reads_lagged: tuple = ()          # fields and tables at their values from the previous round
    writes: tuple = ()                # fields and tables it creates; each has exactly one writer
    modifies: tuple = ()              # fields it reads and then changes, after their writer has run
    priority: int | None = None       # required of a modifier; its place among the modifiers of a field
    adds_to: dict = {}                # group -> the member field this process writes into the sum
    reads_groups: tuple = ()          # groups read in the same round
    reads_groups_lagged: tuple = ()   # groups read from the previous round
    has_start: bool = False           # True if start() fills state before round 1
    draws: tuple = ()                 # purposes of its random draws; seeds.yaml must list them too
    shared: tuple = ()                # names of the shared constants it needs
    model: str = ""                   # name of the model, for the lineage
    version: str = "1"
    drivers: dict = {}                # field -> names of the drivers recorded for it
    additive: tuple = ()              # fields whose drivers are the terms of a sum equal to the field

    def start(self, ctx) -> None:     # called once before round 1 of the stage, if has_start
        raise NotImplementedError

    def run(self, ctx) -> None:
        raise NotImplementedError


def declaration(proc: Process) -> dict:
    """The declaration in the form the scheduler takes."""
    return dict(stage=proc.stage, reads=list(proc.reads), lagged=list(proc.reads_lagged), writes=list(proc.writes),
                modifies=list(proc.modifies), contributes=dict(proc.adds_to), lagged_group=list(proc.reads_groups_lagged),
                group_reads=list(proc.reads_groups), order=proc.priority, start=bool(proc.has_start))


class GroupValue:
    """A group as its reader receives it: the sum, and each named member, so that the reader can
    record one cause per member."""

    def __init__(self, total, members: dict):
        self.total, self.members = total, members
