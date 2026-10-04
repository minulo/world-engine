"""Edge cases of the engine found by the review of build steps 0 and 1. Each test states the rule it guards."""
import copy
import shutil

import numpy as np
import pytest
import yaml

from conftest import TOY
import toy_processes as T
from worldengine import interventions as iv
from worldengine import store
from worldengine.causes import as_text, class_name, explain
from worldengine.engine import Engine, EngineError
from worldengine.fields import Registry
from worldengine.library import operators as op
from worldengine.mesh import get_mesh
from worldengine.params import ParameterError, Parameters
from worldengine.process import ContractError
from worldengine.store import MemoryView, StoreView, chunk_shape
from worldengine.testing import Harness

WHOLE_PLANET = {"circle": {"lat": 0.0, "lon": 0.0, "radius_km": 30000}}
WITH_GEO = {"stages": [{"name": "setup", "clock": "once"},
                       {"name": "geo", "clock": "geological", "round_length_my": 1.0, "history_length_my": 5.0},
                       {"name": "climate", "clock": "climate"}]}


def toy_file(name):
    return yaml.safe_load((TOY / f"{name}.yaml").read_text())


def number(**more):
    return dict(family="Toy", unit="none", shape="cell", kind="number", dtype="float64", **more)


def slot(cls, writes, **more):
    return {"implementation": f"toy_processes:{cls}", "writes": writes, **more}


def engine(slots, fields=None, groups=None, pushes=(), stages=None, tables=None, max_rounds=None, keep_trio=False, profile=None):
    """An engine on the toy data with the given slots; the three toy processes of the loop are left out unless kept."""
    models = {"shared": {"one": 1.0}, "slots": dict(toy_file("models")["slots"]) if keep_trio else {}}
    models["slots"].update(slots)
    f = toy_file("fields")
    f["fields"].update(fields or {})
    f["groups"].update(groups or {})
    overrides = {"models": models, "fields": f, "interventions": list(pushes)}
    if stages:
        overrides["stages"] = stages
    if tables:
        overrides["tables"] = tables
    p = toy_file("profiles")
    if max_rounds:
        p["profiles"]["toy"]["climate"]["max_rounds"] = max_rounds
    p["profiles"]["toy"].update(profile or {})
    overrides["profiles"] = p
    return Engine(TOY, profile="toy", overrides=overrides)


# ------------------------------------------------------------------------------------------ pushes limited to rounds
GEO_FIELDS = {"ones": number(), "elev": number(),
              "month_no": dict(family="Toy", unit="none", shape="month_cell", kind="number"),
              "heading": dict(family="Toy", unit="none", shape="cell", kind="direction")}
GEO_GROUPS = {"geo_push": {"unit": "m", "shape": "cell"}, "geo_now": {"unit": "m", "shape": "cell"}}
GEO_SLOTS = {"Marker": slot("Marker", ["ones", "month_no", "heading"]), "Ground": slot("Ground", ["elev"])}


def geo_engine(pushes, **kw):
    return engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, pushes, stages=WITH_GEO, **kw)


def test_a_push_limited_to_rounds_acts_in_those_rounds_only_whatever_its_kind():
    """when.rounds was ignored for a push on a group with a fixed region: the reader received it in every round."""
    pushes = [
        {"id": "kept", "region": WHOLE_PLANET, "when": {"rounds": [3, 4]}, "pushes": [{"group": "geo_push", "add": 5.0}]},
        {"id": "now", "region": WHOLE_PLANET, "when": {"rounds": [3, 4]}, "pushes": [{"group": "geo_now", "add": 3.0}]},
        {"id": "where", "region": {"where": {"field": "ones", "above": 0.5}}, "when": {"rounds": [2, 2]},
         "pushes": [{"group": "geo_now", "add": 7.0}]},
        {"id": "raise", "reason": "a passing bulge", "region": WHOLE_PLANET, "when": {"rounds": [2, 3]}, "pushes": [{"field": "elev", "add": 50.0}]},
        {"id": "never", "region": WHOLE_PLANET, "when": {"rounds": [9, 9]}, "pushes": [{"field": "elev", "add": 1.0}]},
    ]
    T.Ground.seen = []
    e = geo_engine(pushes)
    w = e.build()
    # round, the group read from the previous round, the group read in the same round
    assert T.Ground.seen == [(1, 0.0, 0.0), (2, 0.0, 7.0), (3, 0.0, 3.0), (4, 5.0, 3.0), (5, 5.0, 0.0)]
    # the stored value is that of round 5, in which the push on elev did not act: no record may claim it did
    assert np.all(w.fields["elev"] == 100.0)
    assert sorted(w.push_records) == ["kept:geo_push"]                    # the only push in what the last round was given
    text = as_text(explain(MemoryView(w, e), 0, "elev"))
    assert "push" not in text.lower()
    # what each push did is kept, round counts included
    assert w.push_activity["raise:elev"] == {"stage": "geo", "first_round": 2, "last_round": 3, "rounds": 2, "touched": True}
    assert w.push_activity["where:geo_now"]["rounds"] == 1 and w.push_activity["now:geo_now"]["rounds"] == 2
    # only the push that was in no round at all is reported as having touched nothing
    assert [n for n in w.notices if n["kind"] == "push_touched_nothing"] == [
        {"kind": "push_touched_nothing", "push": "never:elev", "why": "it was in no round that it applies to"}]


def test_a_push_in_its_last_active_round_is_recorded_with_what_it_changed():
    e = geo_engine([{"id": "raise", "reason": "a late bulge", "region": WHOLE_PLANET, "when": {"rounds": [4, 5]},
                     "pushes": [{"field": "elev", "add": 50.0}]},
                    {"id": "where", "reason": "a late sink", "region": {"where": {"field": "ones", "above": 0.5}},
                     "when": {"rounds": [5, 5]}, "pushes": [{"group": "geo_now", "add": 7.0}]}])
    T.Ground.seen = []
    w = e.build()
    assert np.all(w.fields["elev"] == 150.0)
    assert np.all(w.push_records["raise:elev"]["before"] == 100.0)
    record = w.push_records["where:geo_now"]                             # a push on a group with a condition leaves a record too
    assert record["group"] == "geo_now" and record["reason"] == "a late sink" and np.all(record["weight"] == 1.0)
    assert "entry raise (a late bulge)" in as_text(explain(MemoryView(w, e), 0, "elev"))
    assert not [n for n in w.notices if n["kind"] == "push_touched_nothing"]


def test_a_push_limited_to_rounds_is_refused_on_a_climate_target_until_the_climate_reruns_inside_the_history():
    for target in ({"field": "a", "add": 1.0}, {"group": "toy_heat", "add": 1.0}):
        with pytest.raises(ParameterError) as err:
            engine({"HeatReader": slot("HeatReader", ["c"])}, pushes=[{"id": "late", "region": WHOLE_PLANET, "when": {"rounds": [1, 2]},
                                                                         "pushes": [target]}], keep_trio=True)
        assert "limited to geological rounds 1 to 2" in str(err.value) and "build step 9" in str(err.value)
    with pytest.raises(ParameterError) as err:
        geo_engine([{"id": "back", "region": WHOLE_PLANET, "when": {"rounds": [4, 2]}, "pushes": [{"field": "elev", "add": 1.0}]}])
    assert "runs backwards" in str(err.value)


def test_a_group_push_that_nothing_reads_is_reported():
    e = engine({}, pushes=[{"id": "lost", "region": WHOLE_PLANET, "pushes": [{"group": "toy_heat", "add": 1.0}]}], keep_trio=True)
    w = e.build()
    assert {"kind": "push_touched_nothing", "push": "lost:toy_heat", "why": "no process reads group toy_heat"} in w.notices
    assert "lost:toy_heat" not in w.push_records


# ------------------------------------------------------------------------------------------ groups across stages
HEAT_FIELDS = {"heat_setup": number(), "heat_climate": number(), "sum_now": number(), "sum_lagged": number()}
SETUP_MEMBER = {"SetupMember": slot("SetupMember", ["heat_setup"])}
CLIMATE_MEMBER = {"ClimateMember": slot("ClimateMember", ["heat_climate"])}


def test_a_group_keeps_the_member_of_an_earlier_stage_when_a_later_stage_adds_its_own():
    """The engine emptied the whole group at the start of a round of any stage that had a member in it."""
    w = engine({**SETUP_MEMBER, **CLIMATE_MEMBER, "SumNow": slot("SumNow", ["sum_now"])}, HEAT_FIELDS).build()
    assert np.all(w.fields["sum_now"] == 11.0) and T.SumNow.members == ["heat_climate", "heat_setup"]
    assert set(w.group_records["toy_heat"]) == {"heat_climate", "heat_setup"}


def test_a_group_read_from_the_previous_round_holds_the_stored_members_of_other_stages():
    w = engine({**SETUP_MEMBER, "SumLagged": slot("SumLagged", ["sum_lagged"])}, HEAT_FIELDS).build()
    assert np.all(w.fields["sum_lagged"] == 10.0) and w.rounds_used["climate"] == 1
    w = engine({**SETUP_MEMBER, **CLIMATE_MEMBER, "SumLagged": slot("SumLagged", ["sum_lagged"])}, HEAT_FIELDS).build()
    assert w.settled["climate"] and np.allclose(w.fields["sum_lagged"], 11.0, atol=1e-5)
    assert T.SumLagged.members == ["heat_climate", "heat_setup"]
    assert [g["name"] for g in w.settle_log[-1]["gaps"]] == ["group:toy_heat"]      # the sum is what the stage reads from its last round


def test_a_member_must_have_the_layout_of_its_group():
    with pytest.raises(ParameterError) as err:
        engine({"MonthlyMember": slot("MonthlyMember", ["c"])})
    assert "a member must have the layout of its group" in str(err.value)


# ------------------------------------------------------------------------------------------ what counts as settled
def test_a_true_or_false_field_that_keeps_changing_keeps_the_climate_from_settling():
    """True-or-false and index fields read from the previous round were left out of the test; a stage could be called
    settled in round 1 while such a field flipped every round."""
    w = engine({"Flipper": slot("Flipper", ["flag"])},
               {"flag": dict(family="Toy", unit="true or false", shape="cell", kind="boolean", default=False)}, max_rounds=6).build()
    assert w.rounds_used["climate"] == 6 and not w.settled["climate"]
    assert {"kind": "climate_not_settled", "stage": "climate", "rounds": 6} in w.notices
    assert w.settle_log[-1]["gaps"] == [{"name": "flag", "share_changed_class": 1.0, "ok": False}]


def test_an_index_field_that_keeps_changing_keeps_the_climate_from_settling():
    w = engine({"Stepper": slot("Stepper", ["step_no"])},
               {"step_no": dict(family="Toy", unit="count", shape="cell", kind="index", default=0)}, max_rounds=5).build()
    assert w.rounds_used["climate"] == 5 and not w.settled["climate"] and np.all(w.fields["step_no"] == 5)


def test_a_missing_value_that_stays_missing_does_not_keep_the_climate_from_settling():
    """One NaN made the mean gap NaN, so the stage ran to its cap and was reported as not settled."""
    gappy = {"gappy": number(default=0.0, allow_missing=True)}
    w = engine({"PartlyMissing": slot("PartlyMissing", ["gappy"])}, gappy).build()
    assert w.settled["climate"] and w.rounds_used["climate"] < 40 and not w.notices
    assert np.isnan(w.fields["gappy"][0]) and np.all(w.fields["gappy"][1:] == 5.0)


def test_a_value_that_was_missing_and_is_now_known_enters_the_kept_copy_whole():
    """The blend old + w (new - old) kept a missing value for ever. A change from missing to known counts as unsettled."""
    T.LateFill.seen = []
    w = engine({"LateFill": slot("LateFill", ["gappy"])}, {"gappy": number(default=0.0, allow_missing=True)}).build()
    assert w.settled["climate"] and w.rounds_used["climate"] == 3
    assert T.LateFill.seen[0] == 0.0 and np.isnan(T.LateFill.seen[1]) and T.LateFill.seen[2:] == [5.0, 5.0]
    assert w.settle_log[1]["gaps"][0]["share_over_cell_tolerance"] == pytest.approx(1.0)     # round 2: missing became known


def test_state_carried_in_a_table_is_part_of_the_loop_and_of_the_test():
    """A table read from the previous round was not seen as a loop: the stage ran one round and called itself settled."""
    e = engine({"Counter": slot("Counter", ["c", "table:toy_items"])}, max_rounds=7)
    assert e._has_loop("climate")
    w = e.build()
    assert w.rounds_used["climate"] == 7 and not w.settled["climate"]
    assert w.settle_log[-1]["gaps"] == [{"name": "table:toy_items", "unchanged": False, "ok": False}]
    assert w.tables["toy_items"]["value"][0] == 7.0
    again = e.build()                                                    # each climate run starts from the start step's table
    assert again.tables["toy_items"]["value"][0] == 7.0
    steady = engine({"TableKeeper": slot("TableKeeper", ["table:toy_items"])}).build()
    assert steady.settled["climate"] and steady.rounds_used["climate"] == 1


# ------------------------------------------------------------------------------------------ notices
def test_a_notice_about_an_early_round_does_not_outlive_it():
    """An out-of-range notice from round 1 survived into a world whose field was in range; so did a process's note."""
    w = engine({"Overshoot": slot("Overshoot", ["a"])}).build()
    assert w.settled["climate"] and np.all(w.fields["a"] == 7.0)
    assert w.notices == []


def test_a_note_raised_in_the_settled_round_is_kept_once():
    w = engine({"AlwaysNotes": slot("AlwaysNotes", ["a"])}).build()
    r = w.rounds_used["climate"]
    assert w.notices == [{"kind": "process_note", "slot": "AlwaysNotes", "stage": "climate", "what": "the solver stopped at its cap",
                          "cap": 3, "first_round": r, "last_round": r, "rounds": 1}]


def test_a_value_out_of_range_at_the_end_is_reported_and_an_endless_value_always():
    w = engine({"TooBig": slot("TooBig", ["a"])}).build()
    assert [n for n in w.notices if n["kind"] == "field_outside_range"][0]["highest"] == 500.0
    spec = Registry(Parameters(TOY, {"fields": {"fields": {"x": number(allow_missing=True)}, "groups": {}}})).fields["x"]
    assert spec.outside_range(np.array([1.0, np.nan])) is None            # a missing value is allowed here
    assert spec.outside_range(np.array([1.0, np.inf, -np.inf])) == {"infinite": 2}


def test_a_build_that_overruns_its_time_limit_says_so():
    w = engine({}, keep_trio=True, profile={"run_time_limit_s": 1.0e-9}).build()
    over = [n for n in w.notices if n["kind"] == "run_time_over_limit"]
    assert len(over) == 1 and over[0]["limit_s"] == 1.0e-9 and over[0]["profile"] == "toy"
    assert not [n for n in engine({}, keep_trio=True, profile={"run_time_limit_s": 600}).build().notices]


# ------------------------------------------------------------------------------------------ tables
def test_a_process_that_only_reads_a_table_cannot_change_it():
    """read() handed out the stored dict itself; a reader replaced a column and the built world held the change."""
    makers = {"TableMaker": slot("TableMaker", ["table:toy_items"])}
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    with pytest.raises(TypeError):
        engine({**makers, "TableVandal": slot("TableVandal", ["c"])}).build()
    with pytest.raises(ValueError):
        engine({**makers, "ColumnVandal": slot("ColumnVandal", ["c"])}).build()


def test_a_table_column_refuses_values_that_do_not_fit_its_type():
    """A fraction written to a whole-number column was cut off without a word."""
    T.TableMaker.columns = {"item": [0.5, 1.0], "value": [1.0, 2.5]}
    with pytest.raises(ContractError) as err:
        engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
    assert "column item holds values that do not fit its type int32" in str(err.value)
    T.TableMaker.columns = {"item": [0.0, 3.0e10], "value": [1.0, 2.5]}
    with pytest.raises(ContractError):
        engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
    T.TableMaker.columns = {"item": [0.0, 1.0], "value": [1, 2]}             # whole numbers given as floats, and the reverse, do fit
    w = engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
    assert w.tables["toy_items"]["item"].dtype == np.int32 and w.tables["toy_items"]["value"].dtype == np.float64
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}


def test_a_later_stage_reading_a_table_from_the_previous_round_gets_the_stored_table():
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    w = engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "LaterTableReader": slot("LaterTableReader", ["c"])}).build()
    assert np.all(w.fields["c"] == 3.5) and w.rounds_used["climate"] == 1


BOOL_TABLE = {"tables": {"toy_items": {"columns": {"item": "int32", "value": "float64", "ok": "bool"}}}}


def test_the_store_keeps_true_or_false_columns_and_tables_without_rows(tmp_path):
    """True-or-false columns came back as numbers; a table with no rows made the save fail half way."""
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5], "ok": [True, False]}
    e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}, tables=BOOL_TABLE)
    w = e.build()
    view = StoreView(store.save(w, e, tmp_path / "a.zarr"))
    assert view.table("toy_items")["ok"].dtype == np.bool_ and list(view.table("toy_items")["ok"]) == [True, False]
    T.TableMaker.columns = {"item": [], "value": [], "ok": []}
    e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}, tables=BOOL_TABLE)
    w = e.build()
    view = StoreView(store.save(w, e, tmp_path / "b.zarr"))
    assert {c: a.size for c, a in view.table("toy_items").items()} == {"item": 0, "ok": 0, "value": 0}
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}


def test_a_failed_save_leaves_nothing_behind(tmp_path, monkeypatch):
    e = engine({}, keep_trio=True)
    w = e.build()
    real = store._put

    def fails_late(group, name, array, *a, **k):
        if name == "kind_of_place":
            raise OSError("the disk is full")
        return real(group, name, array, *a, **k)
    monkeypatch.setattr(store, "_put", fails_late)
    target = tmp_path / "w.zarr"
    with pytest.raises(OSError):
        store.save(w, e, target)
    assert list(tmp_path.iterdir()) == []                                 # no store, and no partial one
    monkeypatch.setattr(store, "_put", real)
    assert StoreView(store.save(w, e, target)).field_names()              # the same place can be written afterwards


def test_arrays_are_cut_by_month_or_by_blocks_of_cells_never_one_cell_a_piece():
    """Per-cell arrays above 8 MB (the positions of a level-8 mesh) were stored as one piece per cell: 655,362 files."""
    cells = 655362
    assert chunk_shape((cells, 3), 8, False) == (333333, 3)
    assert chunk_shape((cells, 6), 4, False) == (333333, 6)
    assert chunk_shape((12, cells), 4, True) == (1, cells)
    assert chunk_shape((12, cells, 3), 4, True) == (1, cells, 3)
    assert chunk_shape((12, 4 * cells, 3), 4, True) == (1, 666666, 3)
    assert chunk_shape((12, 10242), 4, True) == (1, 10242) and chunk_shape((10242,), 8, False) == (10242,)
    assert chunk_shape((0,), 8, False) == (1,)
    assert chunk_shape((12, 3), 8, False) == (12, 3)                       # twelve rows of a table are not twelve months


# ------------------------------------------------------------------------------------------ pushes: shapes and operations
def test_set_gives_a_value_to_a_cell_that_had_none():
    """old + w (new - old) stays missing where old is missing; the age of the ocean floor is missing on land."""
    old = np.array([np.nan, 1.0, np.nan, 1.0])
    out = iv.apply_op("set", old, np.full(4, 5.0), np.array([1.0, 1.0, 0.0, 0.5]), "number")
    assert out[0] == 5.0 and out[1] == 5.0 and np.isnan(out[2]) and out[3] == 3.0
    assert iv.apply_op("set", old, np.full(4, 5.0), np.full(4, 0.5), "number")[0] == 5.0      # in the fade there is nothing to mix with
    assert np.isnan(iv.apply_op("add", old, np.full(4, 5.0), np.ones(4), "number")[0])       # nothing can be added to a missing value
    monthly = iv.apply_op("set", np.full((12, 4), np.nan), np.full((12, 4), 2.0), np.array([1.0, 0.0, 1.0, 0.0]), "number")
    assert np.all(monthly[:, [0, 2]] == 2.0) and np.all(np.isnan(monthly[:, [1, 3]]))


@pytest.mark.parametrize("corners", [[[20, 0], [-20, 0], [0, 150]], [[0, 150], [-20, 0], [20, 0]]])
def test_a_long_outline_holds_the_cells_inside_it_and_none_on_the_far_side(corners):
    """The far side was told apart by the sum of the corners, which fails for a long thin outline: a tenth of its
    area was left out, and as many cells on the other side of the planet were pushed."""
    m = get_mesh(6)
    inside = iv._inside_outline(m.xyz, corners)
    assert inside.sum() == 7588
    assert m.lon[inside].min() > 0.0 and m.lon[inside].max() < 150.0      # none on the far side, between 30 and 64 degrees west
    assert np.abs(m.lat[inside]).max() < 37.0                             # the long sides are great circles, which bow toward the poles
    # every cell of a narrow band along the middle line of the outline, from end to end, is inside
    middle = (np.abs(m.lat) < 1.0) & (m.lon > 5.0) & (m.lon < 140.0)
    assert inside[middle].all()


def test_the_fade_of_a_small_circle_reaches_the_cells_its_edge_covers_even_if_no_cell_lies_inside():
    """A 50 km circle with a 1,000 km edge did nothing on the preview mesh, whose cells are 240 km apart."""
    m = get_mesh(5)
    region = iv.Region(circle={"lat": 12.3, "lon": 45.6, "radius_km": 50.0}, outline=None, conditions=[], edge_km=1000.0)
    w = iv.region_weights(region, m, 6.371e6, None, True)
    centre = iv._unit(12.3, 45.6)
    d = np.arccos(np.clip(m.xyz @ centre, -1, 1)) * 6371.0
    assert (w > 0).sum() > 50 and np.allclose(w, np.clip(1.0 - np.maximum(d - 50.0, 0.0) / 1000.0, 0.0, 1.0), atol=1e-6)
    assert np.all(iv.region_weights(region, m, 6.371e6, None, False) == (d <= 50.0))        # a class takes the bare shape


def test_the_fade_of_an_outline_is_measured_from_the_outline_itself():
    m = get_mesh(5)
    square = [[10, -10], [10, 10], [-10, 10], [-10, -10]]
    region = iv.Region(circle=None, outline=square, conditions=[], edge_km=500.0)
    w = iv.region_weights(region, m, 6.371e6, None, True)
    east = (np.abs(m.lat) < 3.0) & (m.lon > 10.0) & (m.lon < 15.0)         # just outside the eastern side
    expected = 1.0 - np.deg2rad(m.lon[east] - 10.0) * np.cos(np.deg2rad(m.lat[east])) * 6371.0 / 500.0
    assert east.sum() > 3 and np.allclose(w[east], np.clip(expected, 0.0, 1.0), atol=0.02)
    assert np.all(w[iv._inside_outline(m.xyz, square)] == 1.0) and np.all(w[np.abs(m.lon) > 20] == 0.0)


MARKED = {"Marker": slot("Marker", ["ones", "month_no", "heading"])}


@pytest.mark.parametrize("region,amount,message", [
    ({"where": {"field": "heading", "above": 0.0}}, 2.0, "the test above cannot be made on heading, a field of kind direction"),
    ({"where": {"field": "month_no", "above": 5.0, "month": 0}}, 2.0, "names month 0; months run from 1 to 12"),
    ({"where": {"field": "month_no", "above": 5.0, "month": 13}}, 2.0, "names month 13; months run from 1 to 12"),
    ({"where": {"field": "ones", "above": 0.5, "month": 3}}, 2.0, "names a month, but that field has no months"),
    ({"where": {"field": "kind_of_place", "is": "tall"}}, 2.0, "'tall' is not a class of kind_of_place"),
    ({"where": {"field": "kind_of_place", "above": 0}}, 2.0, "the test above cannot be made on kind_of_place"),
    ({"where": {"field": "ones", "above": "much"}}, 2.0, "needs a number, found 'much'"),
    (WHOLE_PLANET, "a lot", "the amount 'a lot' is not a number"),
    (WHOLE_PLANET, [1.0, 2.0], "one amount per month fits only a monthly target"),
    ({"outline": [[0, 0], [10, 10]]}, 2.0, "an outline needs at least 3 corners"),
])
def test_what_a_push_tests_and_how_much_it_pushes_are_checked_on_loading(region, amount, message):
    """A condition on a direction raised an array error in the middle of a build; month 0 quietly tested month 12."""
    with pytest.raises(ParameterError) as err:
        engine(MARKED, GEO_FIELDS, pushes=[{"id": "p", "region": region, "pushes": [{"field": "a", "add": amount}]}], keep_trio=True)
    assert message in str(err.value)


def test_the_lineage_fingerprint_changes_with_everything_a_push_is_given():
    """Two worlds whose push tested different months had the same fingerprint for the pushed field."""
    def build(month, rounds_field=None):
        push = {"id": "lift", "region": {"where": {"field": "month_no", "above": 5.0, "month": month}}, "pushes": [{"field": "a", "add": 2.0}]}
        e = engine(MARKED, GEO_FIELDS, pushes=[push], keep_trio=True)
        return e.build()
    early, late = build(1), build(12)
    assert np.allclose(early.fields["a"], 3.0, atol=1e-5) and np.allclose(late.fields["a"], 7.0, atol=1e-5)
    assert early.lineage["a"]["fingerprint"] != late.lineage["a"]["fingerprint"]
    assert early.lineage["a"]["fingerprint"] == build(1).lineage["a"]["fingerprint"]
    # the constants of a process that modifies the field count too
    m = toy_file("models")
    m["slots"]["ToyModifier"]["constants"]["step"] = 2.0
    plain, changed = Engine(TOY, profile="toy").build(), Engine(TOY, profile="toy", overrides={"models": m}).build()
    assert plain.lineage["b"]["fingerprint"] != changed.lineage["b"]["fingerprint"]


# ------------------------------------------------------------------------------------------ settings that are refused, not ignored
def test_settings_for_what_is_not_built_are_refused_not_ignored():
    """Every profile asked for snapshots of the history, and nothing read the setting."""
    with pytest.raises(ParameterError) as err:
        engine({}, keep_trio=True, profile={"snapshot_every_rounds": 5})
    assert "they are built in step 3" in str(err.value)
    stages = copy.deepcopy(WITH_GEO)
    stages["stages"][2]["step"] = "day"
    with pytest.raises(ParameterError) as err:
        engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages)
    assert "gives a step, which only a stage that steps through dates takes" in str(err.value)
    stages = copy.deepcopy(WITH_GEO)
    stages["stages"][2]["history_length_my"] = 3.0
    with pytest.raises(ParameterError) as err:
        engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages)
    assert "only a stage on the geological clock takes" in str(err.value)


def test_a_weather_stage_that_holds_only_a_label_is_refused_like_any_other():
    stages = {"stages": [{"name": "setup", "clock": "once"}, {"name": "climate", "clock": "climate"}, {"name": "weather", "clock": "weather"}]}
    label = {"storm_label": dict(family="Labels", unit="category", shape="cell", kind="category", label={"stage": "weather"}, default="none")}
    with pytest.raises(EngineError) as err:
        engine({}, label, stages=stages, keep_trio=True).build()
    assert "runs on the weather clock, which is built in step 8" in str(err.value)
    assert engine({}, stages=stages, keep_trio=True).build().settled["climate"]          # an empty weather stage is simply skipped


def test_a_key_written_twice_in_a_parameter_file_is_refused(tmp_path):
    """YAML keeps the last of two equal keys and says nothing: a constant set twice took its second value."""
    data = tmp_path / "data"
    shutil.copytree(TOY, data)
    text = (data / "models.yaml").read_text()
    (data / "models.yaml").write_text(text.replace("    constants: {gain: 0.5}", "    constants: {gain: 0.5}\n    constants: {gain: 0.9}"))
    with pytest.raises(ParameterError) as err:
        Engine(data, profile="toy")
    assert "models.yaml" in str(err.value) and "the key 'constants' is written twice" in str(err.value)


def test_field_settings_that_cannot_be_stored_are_refused():
    def fields(**entry):
        f = toy_file("fields")
        f["fields"]["x"] = dict(family="Toy", unit="none", shape="cell", **entry)
        return {"fields": f}
    with pytest.raises(ParameterError) as err:
        Engine(TOY, profile="toy", overrides=fields(kind="boolean", default="missing"))
    assert "only a number or a direction can start as missing" in str(err.value)
    with pytest.raises(ParameterError):
        Engine(TOY, profile="toy", overrides=fields(kind="number", default="none"))
    spec = Registry(Parameters(TOY)).fields["kind_of_place"]
    with pytest.raises(ValueError) as err:                                # 65537 used to wrap round to class 1
        spec.cast(np.full(162, 65537), 162, 12)
    assert "cannot hold every value given" in str(err.value)


# ------------------------------------------------------------------------------------------ small things
def test_a_class_code_outside_the_list_is_named_as_such_not_as_the_last_class():
    assert class_name(["low", "high"], 1) == "high" and class_name(["low", "high"], -1) == "no class (code -1)"
    assert class_name(["low", "high"], 2) == "no class (code 2)"


def test_a_missing_value_outside_the_mask_does_not_reach_a_band_mean():
    m = get_mesh(3)
    f = np.where(m.lon > 0, 2.0, np.nan)
    lat, mean = op.zonal_mean(m, f, 10.0, mask=m.lon > 0)
    assert np.allclose(mean, 2.0)


def test_each_process_has_a_memo_of_its_own():
    engine({"ToySource": slot("MemoWriter", ["a"]), "ToyFollower": slot("MemoReader", ["b", "kind_of_place"])}).build()
    assert T.MemoReader.found is False


def test_a_driver_of_the_wrong_shape_is_refused_in_the_first_round():
    """The shape was checked only in the cause pass, after every round had run."""
    T.WrongDriver.rounds_run = 0
    with pytest.raises(ValueError) as err:
        engine({"WrongDriver": slot("WrongDriver", ["a"])}).build()
    assert "driver part of a has shape (3,)" in str(err.value) and T.WrongDriver.rounds_run == 1


# ------------------------------------------------------------------------------------------ the harness
def test_the_harness_hands_a_process_what_the_engine_would():
    """Tables went in as given (wrong types, writable, columns missing) and a planet the engine refuses was accepted."""
    h = Harness(level=2, data_dir=TOY)
    h.params.data["models"]["slots"]["Probe"] = slot("LaterTableReader", ["c"])
    out = h.run("Probe", lagged_tables={"toy_items": {"item": [0, 1], "value": [1, 2]}})
    assert np.all(out.fields["c"] == 3.0)
    with pytest.raises(ContractError):
        h.run("Probe", lagged_tables={"toy_items": {"item": [0, 1]}})                        # a column is missing
    with pytest.raises(ContractError):
        h.run("Probe", lagged_tables={"toy_items": {"item": [0.5, 1], "value": [1, 2]}})     # a fraction in a whole-number column
    with pytest.raises(ParameterError):
        Harness(level=2, data_dir=TOY, planet={"radius_m": -5.0})
    h.params.data["models"]["slots"]["Reader"] = slot("HeatReader", ["c"])
    with pytest.raises(ValueError) as err:
        h.run("Reader", groups={"toy_heat": {"m": np.zeros((12, h.mesh.n))}})
    assert "must have shape" in str(err.value)
    out = h.run("Reader", groups={"toy_heat": {"m": np.full(h.mesh.n, 2), "n": np.full(h.mesh.n, 0.5)}})
    assert np.all(out.fields["c"] == 2.5)
    h.params.data["models"]["slots"]["Keeper"] = slot("TableKeeper", ["table:toy_items"])
    with pytest.raises(ValueError) as err:
        h.run("Keeper", lagged_tables={"toy_items": {"item": [9], "value": [9.0]}}, start=True)
    assert "start=True fills table toy_items" in str(err.value)
    assert list(h.run("Keeper", start=True).tables["toy_items"]["value"]) == [1.0, 2.0, 3.0]
