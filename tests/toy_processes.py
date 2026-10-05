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


# ---------------------------------------------------------------- toy processes for the tests of the engine's edge cases
class SetupMember(Process):
    """A member of the group toy_heat worked out in the setup stage."""
    stage = "setup"
    adds_to = {"toy_heat": "heat_setup"}

    def run(self, ctx):
        ctx.add_to_group("toy_heat", np.full(ctx.mesh.n, 10.0))


class ClimateMember(Process):
    """A member of the group toy_heat worked out in the climate stage."""
    stage = "climate"
    adds_to = {"toy_heat": "heat_climate"}

    def run(self, ctx):
        ctx.add_to_group("toy_heat", np.full(ctx.mesh.n, 1.0))


class SumNow(Process):
    """Reads the group in the same round."""
    stage = "climate"
    reads_groups = ("toy_heat",)
    writes = ("sum_now",)

    def run(self, ctx):
        g = ctx.read_group("toy_heat")
        SumNow.members = sorted(g.members)
        ctx.write("sum_now", g.total)


class SumLagged(Process):
    """Reads the group from the previous round."""
    stage = "climate"
    reads_groups_lagged = ("toy_heat",)
    writes = ("sum_lagged",)

    def run(self, ctx):
        g = ctx.read_group_lagged("toy_heat")
        SumLagged.members = sorted(g.members)
        ctx.write("sum_lagged", g.total)


class Flipper(Process):
    """A true-or-false field that is the opposite of its own value in the previous round: it can never settle."""
    stage = "climate"
    reads_lagged = ("flag",)
    writes = ("flag",)

    def run(self, ctx):
        ctx.write("flag", ~ctx.read_lagged("flag"))


class Stepper(Process):
    """An index field that goes up by one every round: it can never settle."""
    stage = "climate"
    reads_lagged = ("step_no",)
    writes = ("step_no",)

    def run(self, ctx):
        ctx.write("step_no", ctx.read_lagged("step_no") + 1)


class PartlyMissing(Process):
    """The same values every round, with one cell missing."""
    stage = "climate"
    reads_lagged = ("gappy",)
    writes = ("gappy",)

    def run(self, ctx):
        ctx.read_lagged("gappy")
        v = np.full(ctx.mesh.n, 5.0)
        v[0] = np.nan
        ctx.write("gappy", v)


class LateFill(Process):
    """Missing everywhere in round 1, a number from round 2 on: the kept copy must not stay missing."""
    stage = "climate"
    reads_lagged = ("gappy",)
    writes = ("gappy",)
    seen = []

    def run(self, ctx):
        LateFill.seen.append(float(ctx.read_lagged("gappy")[0]))
        ctx.write("gappy", np.full(ctx.mesh.n, np.nan if ctx.round == 1 else 5.0))


class Overshoot(Process):
    """Outside the valid range of a (0 to 100) in round 1 only, with a note in round 1 only."""
    stage = "climate"
    reads_lagged = ("a",)
    writes = ("a",)

    def run(self, ctx):
        ctx.read_lagged("a")
        if ctx.round == 1:
            ctx.note("a rough first round")
        ctx.write("a", np.full(ctx.mesh.n, 500.0 if ctx.round == 1 else 7.0))


class AlwaysNotes(Process):
    """Raises the same note in every round."""
    stage = "climate"
    reads_lagged = ("a",)
    writes = ("a",)

    def run(self, ctx):
        ctx.note("the solver stopped at its cap", cap=3)
        ctx.write("a", 0.5 * ctx.read_lagged("a") + 1.0)


class Counter(Process):
    """Carries a count in a table from round to round: it can never settle."""
    stage = "climate"
    reads_lagged = ("table:toy_items",)
    writes = ("table:toy_items", "c")
    has_start = True

    def start(self, ctx):
        ctx.write_table("table:toy_items", {"item": [0], "value": [0.0]})

    def run(self, ctx):
        t = ctx.read_lagged("table:toy_items")
        v = float(t["value"][0])
        ctx.write_table("table:toy_items", {"item": [0], "value": [v + 1.0]})
        ctx.write("c", np.full((ctx.months, ctx.mesh.n), v))


class TableMaker(Process):
    """Writes a table in the setup stage."""
    stage = "setup"
    writes = ("table:toy_items",)
    columns = {"item": [0, 1], "value": [1.0, 2.5]}

    def run(self, ctx):
        ctx.write_table("table:toy_items", TableMaker.columns)


class TableVandal(Process):
    """Declares only a read of the table, then tries to change it."""
    stage = "climate"
    reads = ("table:toy_items",)
    writes = ("c",)

    def run(self, ctx):
        t = ctx.read("table:toy_items")
        t["value"] = np.array([99.0, 99.0])
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)))


class ColumnVandal(Process):
    """Declares only a read of the table, then tries to change a value inside one of its columns."""
    stage = "climate"
    reads = ("table:toy_items",)
    writes = ("c",)

    def run(self, ctx):
        ctx.read("table:toy_items")["value"][0] = 99.0
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)))


class LaterTableReader(Process):
    """Reads, from the previous round, a table that an earlier stage wrote."""
    stage = "climate"
    reads_lagged = ("table:toy_items",)
    writes = ("c",)

    def run(self, ctx):
        t = ctx.read_lagged("table:toy_items")
        ctx.write("c", np.full((ctx.months, ctx.mesh.n), float(t["value"].sum()) if t["value"].size else -1.0))


class Ground(Process):
    """A geological toy: writes the same height every round, and remembers what its group held in each round."""
    stage = "geo"
    reads_groups_lagged = ("geo_push",)
    reads_groups = ("geo_now",)
    writes = ("elev",)
    seen = []

    def run(self, ctx):
        before, now = ctx.read_group_lagged("geo_push"), ctx.read_group("geo_now")
        Ground.seen.append((ctx.round, float(before.total[0]), float(now.total[0])))
        ctx.write("elev", np.full(ctx.mesh.n, 100.0))


class Marker(Process):
    """A setup field of ones, for the conditions of pushes; and a monthly one that counts the months."""
    stage = "setup"
    writes = ("ones", "month_no", "heading")

    def run(self, ctx):
        ctx.write("ones", np.ones(ctx.mesh.n))
        ctx.write("month_no", np.repeat(np.arange(1.0, ctx.months + 1)[:, None], ctx.mesh.n, axis=1))
        ctx.write("heading", ctx.mesh.east)


class MonthlyMember(Process):
    """Adds a monthly field to a group that holds one value per cell: the engine must refuse it on loading."""
    stage = "climate"
    adds_to = {"toy_heat": "c"}

    def run(self, ctx):
        ctx.add_to_group("toy_heat", np.zeros((ctx.months, ctx.mesh.n)))


class WrongDriver(Process):
    """Records a driver of the wrong shape. The mistake must show in round 1, not only in the cause pass."""
    stage = "climate"
    reads_lagged = ("a",)
    writes = ("a",)
    drivers = {"a": ("part",)}
    rounds_run = 0

    def run(self, ctx):
        WrongDriver.rounds_run += 1
        ctx.write("a", 0.5 * ctx.read_lagged("a") + 1.0)
        ctx.driver("a", "part", np.zeros(3))


class MemoWriter(Process):
    """Keeps a value in its memo."""
    stage = "climate"
    writes = ("a",)

    def run(self, ctx):
        ctx.memo["shared?"] = 1.0
        ctx.write("a", np.ones(ctx.mesh.n))


class MemoReader(Process):
    """Looks for the other process's value in its own memo: it must not be there."""
    stage = "climate"
    reads = ("a",)
    writes = ("b", "kind_of_place")
    found = None

    def run(self, ctx):
        MemoReader.found = "shared?" in ctx.memo
        ctx.write("b", ctx.read("a"))
        ctx.write("kind_of_place", np.zeros(ctx.mesh.n, dtype=np.int16))


# ---------------------------------------------------------------- toy processes for the cases of the second review
class TwoReads(Process):
    """A geological toy that reads one group both from the previous round and in the same round."""
    stage = "geo"
    reads_groups_lagged = ("geo_now",)
    reads_groups = ("geo_now",)
    writes = ("elev",)
    seen = []

    def run(self, ctx):
        before, now = ctx.read_group_lagged("geo_now"), ctx.read_group("geo_now")
        TwoReads.seen.append((ctx.round, float(before.total[0]), float(now.total[0])))
        ctx.write("elev", np.full(ctx.mesh.n, 100.0))


class RoundField(Process):
    """A geological field that holds the number of the round, and a note raised in every round."""
    stage = "geo"
    writes = ("round_no",)

    def run(self, ctx):
        ctx.note("another round")
        ctx.write("round_no", np.full(ctx.mesh.n, float(ctx.round)))


class LabelCounter(Process):
    """Reads the label field from the previous round and writes where it found a label."""
    stage = "climate"
    reads_lagged = ("place_label",)
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.broadcast_to((ctx.read_lagged("place_label") > 0).astype(np.float64), (ctx.months, ctx.mesh.n)))


class Endless(Process):
    """Writes an infinite value."""
    stage = "climate"
    writes = ("a",)

    def run(self, ctx):
        ctx.write("a", np.full(ctx.mesh.n, np.inf))


class TooLarge(Process):
    """Writes a value that the stored type of c, a 32-bit number, cannot hold."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.full((ctx.months, ctx.mesh.n), 1.0e39))


class StartsField(Process):
    """Fills a field in its start step, reads it from the previous round, and notes what it did at the start."""
    stage = "climate"
    reads_lagged = ("seeded",)
    writes = ("seeded",)
    has_start = True
    seen = []

    def start(self, ctx):
        ctx.note("the start step filled the field", value=42)
        ctx.write("seeded", np.full(ctx.mesh.n, 42.0))

    def run(self, ctx):
        value = ctx.read_lagged("seeded")
        StartsField.seen.append(float(value[0]))
        ctx.write("seeded", value)


class BadNote(Process):
    """Raises a note whose details take the names the engine uses itself."""
    stage = "climate"
    writes = ("a",)

    def run(self, ctx):
        ctx.note("a note", kind="mine", rounds=99)
        ctx.write("a", np.ones(ctx.mesh.n))


class SetupTooBig(Process):
    """A setup field far outside its valid range, for a push to bring back in."""
    stage = "setup"
    writes = ("level",)

    def run(self, ctx):
        ctx.write("level", np.full(ctx.mesh.n, 500.0))


class LaggedTableVandal(Process):
    """Reads a table from the previous round and tries to replace one of its columns."""
    stage = "climate"
    reads_lagged = ("table:toy_items",)
    writes = ("c",)

    def run(self, ctx):
        t = ctx.read_lagged("table:toy_items")
        t["value"] = np.array([99.0, 99.0])
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)))


class MemoCounter(Process):
    """Counts its own runs in its memo and writes the count: a second build must start counting afresh."""
    stage = "setup"
    writes = ("ones",)

    def run(self, ctx):
        ctx.memo["runs"] = ctx.memo.get("runs", 0) + 1
        ctx.write("ones", np.full(ctx.mesh.n, float(ctx.memo["runs"])))


class ThreadProbe(Process):
    """Remembers how many threads the compiled loops and the mathematics libraries may use while it runs."""
    stage = "setup"
    writes = ("ones",)
    seen = None

    def run(self, ctx):
        import numba
        from threadpoolctl import threadpool_info
        ThreadProbe.seen = (numba.get_num_threads(), sorted({lib["num_threads"] for lib in threadpool_info()}))
        ctx.write("ones", np.ones(ctx.mesh.n))


class OddClass(Process):
    """Writes a class code that the field's list does not hold."""
    stage = "climate"
    writes = ("b", "kind_of_place")
    reads = ("a",)

    def run(self, ctx):
        ctx.write("b", ctx.read("a"))
        ctx.write("kind_of_place", np.full(ctx.mesh.n, 5, dtype=np.int16))


class ClassDriver(Process):
    """Records a driver that holds a class, stored as fractions, and one that names a row of a table."""
    stage = "climate"
    reads = ("table:toy_items",)
    writes = ("c",)
    drivers = {"c": ("regime", "item")}

    def run(self, ctx):
        ctx.read("table:toy_items")
        ctx.write("c", np.ones((ctx.months, ctx.mesh.n)))
        ctx.driver("c", "regime", np.full(ctx.mesh.n, 1.0))
        ctx.driver("c", "item", np.ones(ctx.mesh.n, dtype=np.int32))


class GroupModifier(Process):
    """Modifies b by the sum of a group read from the previous round."""
    stage = "climate"
    modifies = ("b",)
    priority = 20
    reads_groups_lagged = ("toy_heat",)

    def run(self, ctx):
        ctx.write("b", ctx.read("b") + ctx.read_group_lagged("toy_heat").total)


class Zeros(Process):
    """Writes nothing but zeros to the monthly field c."""
    stage = "climate"
    writes = ("c",)

    def run(self, ctx):
        ctx.write("c", np.zeros((ctx.months, ctx.mesh.n)))


# ---------------------------------------------------------------- toy processes for the cases of the third check
class StartsMember(Process):
    """Adds a member to the group toy_heat in its start step and in every round."""
    stage = "climate"
    adds_to = {"toy_heat": "heat_member"}
    has_start = True

    def start(self, ctx):
        ctx.add_to_group("toy_heat", np.full(ctx.mesh.n, 5.0))

    def run(self, ctx):
        ctx.add_to_group("toy_heat", np.full(ctx.mesh.n, 5.0))


class LaggedSumLog(Process):
    """Reads the group from the previous round, keeps what it was given in each round, and writes it."""
    stage = "climate"
    reads_groups_lagged = ("toy_heat",)
    writes = ("c",)
    seen = []

    def run(self, ctx):
        total = ctx.read_group_lagged("toy_heat").total
        LaggedSumLog.seen.append(float(total[0]))
        ctx.write("c", np.broadcast_to(total, (ctx.months, ctx.mesh.n)))



class Trickle(Process):
    """A sum of two parts that are both nothing in the first ten cells."""
    stage = "setup"
    writes = ("trickle",)
    drivers = {"trickle": ("from_spring", "from_rain")}
    additive = ("trickle",)

    def run(self, ctx):
        flows = (np.arange(ctx.mesh.n) >= 10).astype(np.float64)
        ctx.write("trickle", 3.0 * flows)
        ctx.driver("trickle", "from_spring", 1.0 * flows)
        ctx.driver("trickle", "from_rain", 2.0 * flows)


# ---------------------------------------------------------------- toy processes for the cases of build step 2's review
class Pond(Process):
    """A sum of two parts with a driver that says what the cell is, and one that names a row of a table.
    Cells 0 to 9 are sea and hold nothing, cells 10 to 19 are lake, the rest is land."""
    stage = "climate"
    reads = ("table:toy_items",)
    writes = ("pond",)
    drivers = {"pond": ("from_stream", "from_spring", "ground", "lake")}
    additive = ("pond",)

    def run(self, ctx):
        ctx.read("table:toy_items")
        cells = np.arange(ctx.mesh.n)
        ground = np.where(cells < 10, 2, np.where(cells < 20, 1, 0))
        stream = np.where(ground == 2, 0.0, np.where(ground == 1, 4.0, 1.0))
        spring = np.where(ground == 0, 2.0, 0.0)
        ctx.write("pond", np.broadcast_to(stream + spring, (ctx.months, ctx.mesh.n)))
        ctx.driver("pond", "from_stream", stream)
        ctx.driver("pond", "from_spring", spring)
        ctx.driver("pond", "ground", ground.astype(np.int32))
        ctx.driver("pond", "lake", np.where(ground == 1, 1, -1).astype(np.int32))


class TrickleInTheLoop(Process):
    """The sum of Trickle, in the climate stage, so that a push can change it after it is written."""
    stage = "climate"
    writes = ("trickle",)
    drivers = {"trickle": ("from_spring", "from_rain")}
    additive = ("trickle",)

    def run(self, ctx):
        flows = (np.arange(ctx.mesh.n) >= 10).astype(np.float64)
        ctx.write("trickle", 3.0 * flows)
        ctx.driver("trickle", "from_spring", 1.0 * flows)
        ctx.driver("trickle", "from_rain", 2.0 * flows)


# ---------------------------------------------------------------- a toy process for the forms of an answer (fourth check of step 2)
class Pointer(Process):
    """A sum of three parts, of which the second is a hundredth and the third a thousandth of the first; a driver that
    names a cell (`target`, for every cell but the first ten, which name none), one that names row 0 of a table, and
    an amount in a unit of its own."""
    stage = "climate"
    reads = ("table:toy_items",)
    writes = ("pointed",)
    drivers = {"pointed": ("large", "small", "tiny", "to_cell", "to_row", "span")}
    additive = ("pointed",)
    target = 0

    def run(self, ctx):
        ctx.read("table:toy_items")
        n = ctx.mesh.n
        to_cell = np.full(n, Pointer.target, dtype=np.int32)
        to_cell[:10] = -1
        ctx.write("pointed", np.full(n, 101.1))
        ctx.driver("pointed", "large", np.full(n, 100.0))
        ctx.driver("pointed", "small", np.full(n, 1.0))
        ctx.driver("pointed", "tiny", np.full(n, 0.1))
        ctx.driver("pointed", "to_cell", to_cell)
        ctx.driver("pointed", "to_row", np.zeros(n, dtype=np.int32))
        ctx.driver("pointed", "span", np.full(n, 3.0e6))
