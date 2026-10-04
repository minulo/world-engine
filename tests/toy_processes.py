"""Toy processes for the tests of the skeleton (build step 0): a loop, a modifier and a push.

ToySource reads b from the previous round and writes a = one + gain * b. A push adds 2 to a.
ToyFollower reads a and writes b = a. ToyModifier adds its step to b.
With gain 0.5 and step 1 the steady answer is a = 7 and b = 8.
"""
import numpy as np

from worldengine.process import Process


class ToySource(Process):
    stage = "climate"
    reads_lagged = ("b",)
    writes = ("a",)
    shared = ("one",)
    draws = ("jitter",)
    model = "toy source"
    drivers = {"a": ("base", "from_b")}
    additive = ("a",)

    def run(self, ctx):
        b = ctx.read_lagged("b")
        part = ctx.const["gain"] * b
        ctx.write("a", ctx.shared["one"] + part)
        ctx.driver("a", "base", np.full(ctx.mesh.n, ctx.shared["one"]))
        ctx.driver("a", "from_b", part)


class ToyFollower(Process):
    stage = "climate"
    reads = ("a",)
    writes = ("b", "kind_of_place")
    model = "toy follower"

    def run(self, ctx):
        a = ctx.read("a")
        ctx.write("b", a)
        ctx.write("kind_of_place", (a > 6.0).astype(np.int16))


class ToyModifier(Process):
    stage = "climate"
    modifies = ("b",)
    priority = 10
    model = "toy modifier"

    def run(self, ctx):
        ctx.write("b", ctx.read("b") + ctx.const["step"])


class BadReader(Process):
    """Reads a field it did not declare."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)) + ctx.read("a")[0])


class BadWriter(Process):
    """Writes a field it did not declare."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)))
        ctx.write("a", np.zeros(ctx.mesh.n))


class Forgetful(Process):
    """Declares a write and does not make it."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        pass


class BadDraw(Process):
    """Asks for a random draw that seeds.yaml does not list."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)) + ctx.draw.uniform("unlisted", 1)[0])


class Unsteady(Process):
    """Gives a different answer each time it is called: the engine must notice."""
    stage = "climate"
    writes = ("c",)
    calls = 0

    def run(self, ctx):
        Unsteady.calls += 1
        ctx.write("c", np.full((ctx.months, ctx.mesh.n), float(Unsteady.calls)))


class HeatMember(Process):
    """Adds a term to the group toy_heat."""
    stage = "climate"
    adds_to = {"toy_heat": "heat_member"}
    reads = ("a",)

    def run(self, ctx):
        ctx.add_to_group("toy_heat", 0.1 * ctx.read("a"))


class HeatReader(Process):
    """Reads the group from the previous round and records one driver per member."""
    stage = "climate"
    reads_groups_lagged = ("toy_heat",)
    writes = ("c",)

    def run(self, ctx):
        g = ctx.read_group_lagged("toy_heat")
        HeatReader.last_members = sorted(g.members)
        ctx.write("c", np.broadcast_to(g.total, (ctx.months, ctx.mesh.n)))


class TableKeeper(Process):
    """Carries a table from round to round, filled by a start step."""
    stage = "climate"
    reads_lagged = ("table:toy_items",)
    writes = ("table:toy_items",)
    has_start = True

    def start(self, ctx):
        ctx.write_table("table:toy_items", {"item": [0, 1, 2], "value": [1.0, 2.0, 3.0]})

    def run(self, ctx):
        t = ctx.read_lagged("table:toy_items")
        ctx.write_table("table:toy_items", {"item": t["item"], "value": t["value"]})


class TooBig(Process):
    """Writes a value outside the valid range of its field."""
    stage = "climate"
    writes = ("a",)

    def run(self, ctx):
        ctx.write("a", np.full(ctx.mesh.n, 500.0))
