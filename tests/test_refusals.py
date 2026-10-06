"""Refusals that no test reached, or whose words no test held (build step 0: "every refusal message is tested").

The fifth check of build step 2 took fifteen refusals out of the engine, or reworded them, and every test passed.
tools/refusal_audit.py then looked at all 249 that are written in the engine's code: no test reached 66, and nine
more were reached by a test that did not look at what they said. Each of those 75 has a test here, which asks for
the refusal in its own words. The audit says whether that still holds: python tools/refusal_audit.py.
"""
import argparse
import copy

import numpy as np
import pytest

from conftest import TOY
import toy_processes as T
from test_engine_cases import GEO_FIELDS, GEO_GROUPS, GEO_SLOTS, MARKED, WHOLE_PLANET, WITH_GEO, engine, slot, toy_file
from worldengine import console, draws, store
from worldengine import interventions as iv
from worldengine.engine import Engine, EngineError
from worldengine.fields import Registry
from worldengine.library import drainage as dr
from worldengine.mesh import LEVEL_MAX, get_mesh
from worldengine.params import ParameterError, Parameters, validate
from worldengine.process import ContractError, Process
from worldengine.server import WorldService
from worldengine.store import MemoryView
from worldengine.testing import Harness

N, MONTHS = 162, 12                      # the toy world: mesh level 2, twelve months


# ---------------------------------------------------------------------------------------------- a process that breaks its word
_made = []


def rogue(deed, **declared):
    """A process that does `deed(ctx)` when it runs, declared as given. Returns (the name of its slot, the slot's
    entry for models.yaml)."""
    name = f"Rogue{len(_made)}"
    cls = type(name, (Process,), {"stage": "climate", "model": "a process that breaks its word", **declared,
                                  "run": lambda self, ctx: deed(ctx)})
    globals()[name] = cls                # the engine loads a process by the name of its module and of its class
    _made.append(cls)
    return name, {"implementation": f"{__name__}:{name}", "writes": sorted(list(cls.writes) + list(cls.adds_to.values()))}


def alone(deed, given=None, **declared):
    """Run such a process by itself, as the test harness runs any process; `given` holds the fields it is handed."""
    name, entry = rogue(deed, **declared)
    h = Harness(level=2, data_dir=TOY)
    h.params["models"]["slots"][name] = entry
    return h.run(name, reads=given)


zeros, monthly_zeros = np.zeros(N), np.zeros((MONTHS, N))
ITEMS = {"item": [0, 1], "value": [1.0, 2.0]}

BROKEN_WORDS = [
    (lambda c: c.read("table:toy_items"), dict(reads=("table:toy_items",)), EngineError, "read table:toy_items before anything wrote it"),
    (lambda c: c.read_lagged("a"), {}, ContractError, "read a from the previous round, which it did not declare"),
    (lambda c: c.read_group("toy_heat"), {}, ContractError, "read group toy_heat in the same round, which it did not declare"),
    (lambda c: c.read_group_lagged("toy_heat"), {}, ContractError, "read group toy_heat from the previous round, which it did not declare"),
    (lambda c: c.categories("kind_of_place"), {}, ContractError, "asked for the classes of kind_of_place, which it did not declare"),
    (lambda c: c.write("heat_member", zeros), dict(adds_to={"toy_heat": "heat_member"}), ContractError,
     "must hand heat_member to its group with add_to_group"),
    (lambda c: c.write("table:toy_items", ITEMS), dict(writes=("table:toy_items",)), ContractError, "a table is written with write_table"),
    (lambda c: c.write_table("table:toy_items", ITEMS), {}, ContractError, "wrote table:toy_items, which it did not declare under writes"),
    (lambda c: c.add_to_group("toy_heat", zeros), {}, ContractError, "added to group toy_heat, which it did not declare"),
    (lambda c: c.driver("a", "part", zeros), {}, ContractError, "recorded a driver for a, which it does not write"),
    (lambda c: (c.write("c", monthly_zeros), c.driver("c", "other", monthly_zeros)), dict(writes=("c",), drivers={"c": ("part",)}), ContractError,
     "recorded the driver other for c, which its driver list does not name"),
    (lambda c: c.write("c", monthly_zeros), dict(writes=("c",), drivers={"c": ("part", "rest")}), ContractError,
     "did not record the drivers it lists for c: part, rest"),
    (lambda c: c.read("a"), dict(reads=("a",)), EngineError, "read a before anything wrote it"),
]


@pytest.mark.parametrize("deed,declared,kind,said", BROKEN_WORDS, ids=[said for *_, said in BROKEN_WORDS])
def test_a_process_that_breaks_its_declaration_is_told_how(deed, declared, kind, said):
    with pytest.raises(kind) as err:
        alone(deed, **declared)
    assert said in str(err.value) and str(err.value).startswith("Rogue")       # ... and which process it was


def test_a_field_read_before_its_writer_ran_in_the_round_is_refused():
    """A process that reads, as it stands, a field of its own stage that has not been written in this round has been
    put in the wrong order. The scheduler never orders one so; the engine checks all the same."""
    with pytest.raises(EngineError, match="read c before its writer ran in this round; the order is wrong"):
        alone(lambda c: c.read("c"), given={"c": monthly_zeros}, reads=("c",), writes=("c",))


# ---------------------------------------------------------------------------------------------- the parameter files
def world_with(deed=None, pushes=(), fields=None, stages=None, constants=None, **declared):
    """The toy world with one more slot, filled by a process as `rogue` makes it."""
    name, entry = rogue(deed or (lambda c: None), **declared)
    if constants is not None:
        entry["constants"] = constants
    return engine({name: entry}, fields=fields, pushes=pushes, stages=stages, keep_trio=True)


def test_a_constant_that_names_a_missing_file_or_a_mesh_level_without_a_value_is_refused():
    with pytest.raises(ParameterError, match=r"constants\.table: from_file names \{'file': 'nowhere', 'key': 'k'\}, which does not exist"):
        world_with(constants={"table": {"from_file": {"file": "nowhere", "key": "k"}}})
    with pytest.raises(ParameterError, match=r"constants\.reach: no value for mesh level 2 \(given for: \[5, 7\]\)"):
        world_with(constants={"reach": {"by_level": {5: 1.0, 7: 2.0}}})


def test_a_profile_that_the_file_does_not_hold_is_refused_with_the_ones_it_holds():
    with pytest.raises(ParameterError, match=r"profiles.yaml has no profile named 'standrad' \(it has: toy\)"):
        Engine(TOY, profile="standrad")


class NotAProcess:
    pass


def test_what_a_slot_names_must_exist():
    """A draw that seeds.yaml does not list, a shared constant that models.yaml lacks, an implementation that cannot
    be loaded or is no process, and a table, a field or a stage that no file declares."""
    with pytest.raises(ParameterError, match="seeds.yaml does not list the draw 'dice' that Rogue"):
        world_with(draws=("dice",))
    with pytest.raises(ParameterError, match=r"models.yaml.shared lacks the constants \['two'\] that Rogue"):
        world_with(shared=("two",))
    for path, said in (("no_such_module:Thing", "cannot load the implementation 'no_such_module:Thing': No module named"),
                       (f"{__name__}:NoSuchClass", "cannot load the implementation"), ("no_colon", "cannot load the implementation 'no_colon'"),
                       (f"{__name__}:NotAProcess", f"models.yaml.slots.Extra: {__name__}:NotAProcess is not a Process")):
        with pytest.raises(ParameterError) as err:
            engine({"Extra": {"implementation": path, "writes": []}}, keep_trio=True)
        assert said in str(err.value), path
    with pytest.raises(ParameterError, match="names table:ledger, which tables.yaml does not declare"):
        world_with(reads=("table:ledger",))
    with pytest.raises(ParameterError, match="names the field depth, which fields.yaml does not declare"):
        world_with(reads=("depth",))
    with pytest.raises(ParameterError, match="names stage weathering, which stages.yaml does not contain"):
        world_with(stage="weathering")


def test_a_push_that_tests_a_field_no_file_declares_is_refused():
    push = {"id": "p", "region": {"where": {"field": "depth", "above": 1.0}}, "pushes": [{"field": "a", "add": 1.0}]}
    with pytest.raises(ParameterError, match="push p:a tests depth, which fields.yaml does not declare"):
        engine({}, pushes=[push], keep_trio=True)


def test_stages_that_cannot_run_yet_or_lack_their_lengths_are_refused():
    weather = {"stages": toy_file("stages")["stages"] + [{"name": "weather", "clock": "weather"}]}
    with pytest.raises(ParameterError, match="stage weather runs on the weather clock, which is built in step 8; until then it must stay empty, but it holds Rogue"):
        world_with(lambda c: c.write("c", monthly_zeros), stages=weather, stage="weather", writes=("c",))
    stages = copy.deepcopy(WITH_GEO)
    del stages["stages"][1]["history_length_my"]
    with pytest.raises(ParameterError, match="stage geo runs on the geological clock and needs round_length_my and history_length_my"):
        engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages)
    e = Engine(TOY, profile="toy")
    e.clocks["climate"] = "weather"                          # past the check on loading: the build refuses as well
    with pytest.raises(EngineError, match="stage climate runs on the weather clock, which is built in step 8"):
        e.build()


@pytest.mark.parametrize("columns,said", [
    ({"item": [0, 1]}, r"wrote table toy_items with columns \['item'\]; tables.yaml lists \['item', 'value'\]"),
    ({"item": [0, 1], "value": [1.0]}, "wrote table toy_items: every column must be one list of the same length"),
    ({"item": [0], "value": [float("inf")]}, "wrote table toy_items: column value holds an infinite value, or one too large for float64"),
])
def test_a_table_that_is_not_what_the_file_declares_is_refused(columns, said, monkeypatch):
    monkeypatch.setattr(T.TableMaker, "columns", columns)
    with pytest.raises(ContractError, match=f"TableMaker {said}"):
        engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()


def test_a_table_that_changes_when_the_settled_round_is_run_again_is_refused():
    """The cause records are made by running the settled round once more, and a process must then give what it gave
    before. For a field that was tested; for a table it was not."""
    def deed(ctx):                                           # another table in the pass that records the causes
        ctx.write_table("table:toy_items", {"item": [0], "value": [2.0 if ctx.recording else 1.0]})
    name, made = rogue(deed, writes=("table:toy_items",))
    with pytest.raises(EngineError, match="table toy_items changed when the settled round was run again for the cause records"):
        engine({name: made}).build()


# ---------------------------------------------------------------------------------------------- fields
def spec_of(name, **entry):
    f = toy_file("fields")
    if entry:
        f["fields"][name] = dict(family="Toy", unit="none", shape="cell", **entry)
    return Registry(Parameters(TOY, {"fields": f})).fields[name]


@pytest.mark.parametrize("field,value,said", [
    ("a", np.zeros(3), r"a must have shape \(162,\), got \(3,\)"),
    ("a", np.array(["deep"] * N), "a was given values of type <U4; a field takes numbers or true and false"),
    ("kind_of_place", np.full(N, 0.5), "kind_of_place is of kind category and cannot take fractional values"),
])
def test_a_value_that_a_field_cannot_take_is_refused(field, value, said):
    with pytest.raises(ValueError, match=said):
        spec_of(field).cast(value, N, MONTHS)


@pytest.mark.parametrize("entry,said", [
    (dict(kind="category", categories_from={"file": "nowhere", "key": "k"}), r"categories_from names \{'file': 'nowhere', 'key': 'k'\}, which does not exist"),
    (dict(kind="category"), "fields.yaml.fields.x: a category field needs its list of classes"),
    (dict(kind="number", label={"stage": "climate"}), "fields.yaml.fields.x: a label field must be of kind category"),
    (dict(kind="boolean", default=1), "the default of a true-or-false field is true or false, found 1"),
    (dict(kind="number", default="deep"), "fields.yaml.fields.x: the default 'deep' is not a number"),
    (dict(kind="category", categories=["low", "high"], default="middle"), "fields.yaml.fields.x: the default 'middle' is not among its classes"),
])
def test_a_field_entry_that_means_nothing_is_refused(entry, said):
    f = toy_file("fields")
    f["fields"]["x"] = dict(family="Toy", unit="none", shape="cell", **entry)
    with pytest.raises(ParameterError, match=said):
        Engine(TOY, profile="toy", overrides={"fields": f})


# ---------------------------------------------------------------------------------------------- pushes
FLAG = {"flag": dict(family="Toy", unit="true or false", shape="cell", kind="boolean", default=False)}


def pushed(entry, fields=None):
    """The toy world with the fields of the edge cases and one entry of pushes; refused on loading if the entry is."""
    return engine(MARKED, {**GEO_FIELDS, **(fields or {})}, pushes=[entry], keep_trio=True)


def entry(pushes=None, region=None, **more):
    return {"id": "p", "region": WHOLE_PLANET if region is None else region, "pushes": [{"field": "a", "add": 1.0}] if pushes is None else pushes, **more}


@pytest.mark.parametrize("given,said", [
    (entry(region={"where": {"field": "ones", "above": 0.5, "below": 2.0}}), r"interventions.yaml\[0\] \(p\): a condition needs exactly one of is_one_of, is, above, below"),
    (entry(region={"where": {"field": "ones"}}), "a condition needs exactly one of is_one_of, is, above, below"),
    (entry(region={"outline": [[0.0, 0.0], [10.0, 400.0], [10.0, 10.0]]}), "the outline cannot be used: a corner has a longitude outside -360 to 360"),
    (entry(region={}), r"interventions.yaml\[0\] \(p\): the region needs a circle, an outline or a condition"),
    (entry(pushes=[{"field": "a", "add": 1.0, "scale": 2.0}]), r"push 0 needs exactly one operation \(set, add, scale, cap_max, cap_min\)"),
    (entry(pushes=[{"field": "a"}]), "push 0 needs exactly one operation"),
    (entry(pushes=[{"field": "a", "group": "toy_heat", "add": 1.0}]), "push 0 needs a field or a group, and not both"),
    (entry(pushes=[{"add": 1.0}]), "push 0 needs a field or a group, and not both"),
    (entry(pushes=[{"field": "a", "add": 1.0}, {"field": "a", "scale": 2.0}]), "two pushes of this entry target a"),
    (entry(pushes=[{"field": "place_label", "set": "elsewhere"}]), "push p:place_label: a label field holds the id of the entry that sets it; write set: p"),
    (entry(region={"where": {"field": "month_no", "is": 3.0}}), "push p:a: a condition on the monthly field month_no with is needs a month"),
    (entry(region={"where": {"field": "kind_of_place", "is_one_of": "low"}}), "push p:a: is_one_of on kind_of_place takes a list"),
    (entry(region={"where": {"field": "ones", "above": [0.5, 1.5]}}), "push p:a: above on ones takes one value, not a list"),
    (entry(region={"where": {"field": "flag", "is": 1}}), "push p:a: flag is true or false; the condition gives 1"),
    (entry(pushes=[{"field": "heading", "scale": {"east": 1.0, "north": 0.0}}]), "push p:heading: scale on a direction takes one number"),
    (entry(pushes=[{"field": "heading", "set": 1.0}]), "push p:heading: a direction is given as its east and north parts, two numbers"),
    (entry(pushes=[{"field": "heading", "set": {"east": 1.0, "up": 0.0}}]), "a direction is given as its east and north parts, two numbers"),
    (entry(pushes=[{"field": "flag", "set": 1}]), "push p:flag: a true-or-false field takes true or false, found 1"),
    (entry(pushes=[{"field": "month_no", "add": [1.0] * 11 + [float("nan")]}]), r"push p:month_no: the monthly amounts \[1.0, .*nan\] are not all finite numbers"),
])
def test_a_push_entry_that_cannot_be_meant_is_refused_on_loading(given, said):
    with pytest.raises(ParameterError, match=said):
        pushed(given, FLAG)


def test_two_entries_of_pushes_cannot_share_an_id():
    with pytest.raises(ParameterError, match=r"interventions.yaml\[1\] \(p\): the id 'p' is used twice"):
        engine({}, pushes=[entry(), entry()], keep_trio=True)


def test_the_parts_that_apply_a_push_refuse_what_the_loading_check_would_have_refused():
    """What follows cannot be reached through the files: the check on loading refuses each case first. The functions
    that apply a push refuse them as well, so that a caller who goes round the loading check is not answered with
    nonsense."""
    mesh = get_mesh(2)
    region = iv.Region(circle=None, outline=None, conditions=[iv.Condition(field="c", lagged=False, test="is", value=1.0, month=None)], edge_km=0.0)
    with pytest.raises(ParameterError, match="a condition on the monthly field c with is needs a month"):
        iv.region_weights(region, mesh, 6.371e6, lambda cond: monthly_zeros, True)
    nowhere = iv.Region(circle=None, outline=None, conditions=[], edge_km=0.0)
    turn = lambda op, amount: iv.Push(entry_id="p", index=0, target="heading", on_group=False, op=op, amount=amount, region=nowhere,
                                      physical=False, reason="", rounds=None)
    with pytest.raises(ParameterError, match="push p:heading: scale on a direction takes one number"):
        iv.amount_array(turn("scale", {"east": 1.0, "north": 0.0}), "direction", (N, 3), MONTHS, mesh)
    with pytest.raises(ParameterError, match="push p:heading: a direction is given as its east and north parts"):
        iv.amount_array(turn("set", {"east": 1.0}), "direction", (N, 3), MONTHS, mesh)
    with pytest.raises(ParameterError, match="the operation halve does not exist"):
        iv.apply_op("halve", zeros, zeros, np.ones(N), "number")


# ---------------------------------------------------------------------------------------------- smaller things
def test_a_draw_key_cannot_hold_the_bar_that_separates_its_parts():
    with pytest.raises(ValueError, match=r"the slot 'a\|b' or one of its draws \('x',\) has the bar \| in its name"):
        draws.Draws(7, "a|b", ("x",), "start")


def test_a_mesh_level_outside_the_range_is_refused():
    with pytest.raises(ValueError, match=f"mesh level {LEVEL_MAX + 1} is outside 0 to {LEVEL_MAX}"):
        get_mesh(LEVEL_MAX + 1)


def test_full_hollows_cannot_include_one_without_a_pass():
    """library/drainage.through_full_hollows is asked for the ways of the water when given hollows are full. A hollow
    with no way out has no outlet cell to route its water to; asking for it is refused in so many words."""
    table = {"parent": np.array([-1, -1]), "spill_m": np.array([np.nan, np.nan]), "spill_from_cell": np.array([-1, -1]),
             "spill_into_cell": np.array([-1, -1])}
    mesh = get_mesh(1)
    with pytest.raises(ValueError, match="a hollow without a pass cannot overflow: it has no outlet cell to route its water to"):
        dr.through_full_hollows(np.full(mesh.n, -1), np.zeros(mesh.n), mesh.nbr, np.ones(mesh.n, dtype=np.int64), table, [1])


@pytest.mark.parametrize("value,schema,said", [
    ("yes", {"type": "boolean"}, "w: expected true or false, found 'yes'"),
    ({}, {"type": "map", "required": ["depth"], "keys": {"depth": {"type": "number"}}}, "w: the key 'depth' is missing"),
    ({1: 2.0}, {"type": "map", "keys": {}}, "w: the key 1 must be text"),
    ("deep", {"type": "one_of", "options": [{"type": "number"}, {"type": "boolean"}]},
     r"w: fits none of the allowed forms \(w: expected a number, found str 'deep' \| w: expected true or false, found 'deep'\)"),
    (1.0, {"type": "tuple"}, "w: the schema names an unknown type 'tuple'"),
])
def test_a_value_that_does_not_fit_its_schema_is_refused_in_words(value, schema, said):
    with pytest.raises(ParameterError, match=said):
        validate(value, schema, "w")


def test_an_override_or_a_data_folder_that_lacks_what_the_engine_needs_is_refused(tmp_path):
    import shutil
    with pytest.raises(ParameterError, match="override names 'modles', which is not a parameter file"):
        Parameters(TOY, {"modles": {}})
    data = tmp_path / "data"
    shutil.copytree(TOY, data)
    (data / "schemas").mkdir()                               # a data folder with schemas of its own, and not all of them
    from worldengine.params import DEFAULT_DATA_DIR
    for schema in (DEFAULT_DATA_DIR / "schemas").glob("*.yaml"):
        if schema.stem != "seeds":
            shutil.copy(schema, data / "schemas" / schema.name)
    with pytest.raises(ParameterError, match=r"seeds.yaml has no schema in .*schemas"):
        Parameters(data)


def test_the_server_refuses_a_month_and_a_cell_that_the_world_does_not_have():
    e = engine(MARKED, GEO_FIELDS)                           # a world with a monthly field
    service = WorldService(MemoryView(e.build(), e))
    with pytest.raises(IndexError, match="month 14 is outside 1 to 12"):
        service.field("month_no", month=13)                  # (months are counted from 0 in a request, from 1 in the words)
    with pytest.raises(IndexError, match=f"cell {N} is outside 0 to {N - 1}"):
        service.cell(N)


def test_a_world_store_is_never_written_over(tmp_path):
    e = Engine(TOY, profile="toy")
    w = e.build()
    target = store.save(w, e, tmp_path / "w.zarr")
    with pytest.raises(FileExistsError, match="w.zarr exists; a world store is written once and never changed"):
        store.save(w, e, target)


def test_an_option_that_is_no_number_is_refused_in_words():
    with pytest.raises(argparse.ArgumentTypeError, match="'much' is not a number"):
        console.number_between(0.0, 1.0)("much")
