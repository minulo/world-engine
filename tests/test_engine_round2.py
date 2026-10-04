"""Edge cases of the engine found by the second review of build steps 0 and 1. Each test states the rule it guards."""
import copy
import json
import shutil
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import yaml
import zarr

from conftest import TOY
import toy_processes as T
from test_engine_cases import (BOOL_TABLE, GEO_FIELDS, GEO_GROUPS, GEO_SLOTS, MARKED, WHOLE_PLANET, WITH_GEO, engine, geo_engine,
                               number, slot, toy_file)
from worldengine import cli
from worldengine import interventions as iv
from worldengine import store
from worldengine.causes import MAX_STEPS, as_text, explain
from worldengine.engine import Engine
from worldengine.fields import Registry
from worldengine.library import operators as op
from worldengine.mesh import get_mesh
from worldengine.params import ParameterError, Parameters, load_yaml_text
from worldengine.process import ContractError
from worldengine.server import make_server
from worldengine.store import MemoryView, StoreView
from worldengine.testing import Harness

EVERYWHERE = {"where": {"field": "ones", "above": 0.5}}                   # a region given by a condition that every cell meets


def touched_nothing(w):
    return {n["push"]: n.get("why") for n in w.notices if n["kind"] == "push_touched_nothing"}


# ------------------------------------------------------------------------------------------ pushes on groups
def test_a_group_push_leaves_a_record_only_if_a_reader_was_given_it_whatever_its_kind():
    """A push with a condition left a record whenever it was in force in the last round, read or not, and none when
    the reader of the last round was given the sum of the round before. A push with a fixed region did the opposite.
    The group geo_push is read from the previous round only, and the history has five rounds."""
    pushes = [
        {"id": "late_fixed", "region": WHOLE_PLANET, "when": {"rounds": [5, 5]}, "pushes": [{"group": "geo_push", "add": 1.0}]},
        {"id": "late_cond", "region": EVERYWHERE, "when": {"rounds": [5, 5]}, "pushes": [{"group": "geo_push", "add": 2.0}]},
        {"id": "prev_fixed", "region": WHOLE_PLANET, "when": {"rounds": [4, 4]}, "pushes": [{"group": "geo_push", "add": 4.0}]},
        {"id": "prev_cond", "reason": "read a round later", "region": EVERYWHERE, "when": {"rounds": [4, 4]},
         "pushes": [{"group": "geo_push", "add": 8.0}]},
    ]
    T.Ground.seen = []
    w = geo_engine(pushes).build()
    assert [before for _, before, _ in T.Ground.seen] == [0.0, 0.0, 0.0, 0.0, 12.0]       # round 5 is given the sum of round 4
    assert sorted(w.push_records) == ["prev_cond:geo_push", "prev_fixed:geo_push"]
    record = w.push_records["prev_cond:geo_push"]
    assert record["group"] == "geo_push" and record["reason"] == "read a round later" and np.all(record["weight"] == 1.0)
    unread = "no process read group geo_push in a round whose sum held it"
    assert touched_nothing(w) == {"late_fixed:geo_push": unread, "late_cond:geo_push": unread}
    for pid, rounds in (("late_fixed", 5), ("late_cond", 5), ("prev_fixed", 4), ("prev_cond", 4)):     # in force, read or not
        assert w.push_activity[pid + ":geo_push"] == {"stage": "geo", "first_round": rounds, "last_round": rounds, "rounds": 1,
                                                        "touched": True}


def test_the_rounds_a_group_push_was_in_force_are_counted_once_however_often_the_group_is_read():
    """A push limited to two rounds showed three: a read of the same round and a read from the previous round each
    counted the round they were made in."""
    fields = {k: v for k, v in GEO_FIELDS.items()}
    slots = {"Marker": GEO_SLOTS["Marker"], "TwoReads": slot("TwoReads", ["elev"])}
    pushes = [{"id": "fixed", "region": WHOLE_PLANET, "when": {"rounds": [2, 3]}, "pushes": [{"group": "geo_now", "add": 3.0}]},
              {"id": "cond", "region": EVERYWHERE, "when": {"rounds": [2, 3]}, "pushes": [{"group": "geo_now", "add": 4.0}]}]
    T.TwoReads.seen = []
    w = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO).build()
    assert T.TwoReads.seen == [(1, 0.0, 0.0), (2, 0.0, 7.0), (3, 7.0, 7.0), (4, 7.0, 0.0), (5, 0.0, 0.0)]
    for pid in ("fixed:geo_now", "cond:geo_now"):
        assert w.push_activity[pid] == {"stage": "geo", "first_round": 2, "last_round": 3, "rounds": 2, "touched": True}
    assert not w.push_records and not touched_nothing(w)                  # read in rounds 2 to 4, and in no sum of round 5


def test_a_push_with_a_condition_on_a_group_that_nothing_reads_is_reported_too():
    """Only the push with a fixed region was reported."""
    pushes = [{"id": "lost", "region": {"where": {"field": "a", "above": -1.0}}, "pushes": [{"group": "toy_heat", "add": 1.0}]}]
    w = engine({"HeatMember": slot("HeatMember", ["heat_member"])}, pushes=pushes, keep_trio=True).build()
    assert touched_nothing(w) == {"lost:toy_heat": "no process reads group toy_heat"} and not w.push_records


def test_a_push_that_covered_cells_in_an_early_round_is_not_reported_as_having_touched_nothing():
    """What a push covered is remembered over its rounds; the last round alone does not decide."""
    fields = {**GEO_FIELDS, "round_no": number()}
    slots = {**GEO_SLOTS, "RoundField": slot("RoundField", ["round_no"])}
    pushes = [{"id": "early", "region": {"where": {"field": "round_no", "below": 2.5}}, "pushes": [{"field": "elev", "add": 1.0}]},
              {"id": "never", "region": {"where": {"field": "round_no", "above": 99.0}}, "pushes": [{"field": "elev", "add": 1.0}]}]
    w = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO).build()
    assert w.push_activity["early:elev"] == {"stage": "geo", "first_round": 1, "last_round": 5, "rounds": 5, "touched": True}
    assert touched_nothing(w) == {"never:elev": None}                      # in force in every round, and it never covered a cell


# ------------------------------------------------------------------------------------------ what counts as settled
def test_a_label_read_from_the_previous_round_keeps_the_climate_going_until_its_reader_has_seen_it():
    """A label field was left out of the test: the stage called itself settled in round 1, in which every read from
    the previous round still returns the default, so that the reader never saw the label."""
    label = {"id": "mark", "region": {"circle": {"lat": 0.0, "lon": 0.0, "radius_km": 4000}}, "pushes": [{"field": "place_label", "set": "mark"}]}
    w = engine({"LabelCounter": slot("LabelCounter", ["c"])}, pushes=[label]).build()
    labelled = w.fields["place_label"] == 1
    assert labelled.any() and not labelled.all()
    assert w.rounds_used["climate"] == 2 and w.settled["climate"]
    assert np.array_equal(w.fields["c"][0] > 0, labelled)                  # the reader saw the label
    # the same for a push whose condition reads the label from the previous round
    lift = {"id": "lift", "region": {"where": {"field": "place_label", "is": "mark", "lagged": True}}, "pushes": [{"field": "a", "add": 10.0}]}
    w = engine({}, pushes=[label, lift], keep_trio=True).build()
    assert w.settled["climate"] and w.fields["a"][labelled].min() > w.fields["a"][~labelled].max() + 5.0


# ------------------------------------------------------------------------------------------ values a field cannot hold
def test_an_infinite_value_is_refused_where_it_is_written_and_the_writer_is_named():
    """An infinite value made the settled test compute inf - inf, with warnings and no answer; in the fade of a push it
    turned into a missing value."""
    with pytest.raises(ValueError) as err:
        engine({"Endless": slot("Endless", ["a"])}).build()
    assert "Endless: a was given an infinite value" in str(err.value)
    with pytest.raises(ValueError) as err:                               # too large for a 32-bit number: no silent overflow, no warning
        engine({"TooLarge": slot("TooLarge", ["c"])}).build()
    assert "TooLarge: c was given an infinite value, or a value too large for its stored type float32" in str(err.value)
    push = {"id": "huge", "region": WHOLE_PLANET, "pushes": [{"field": "c", "add": 1.0e39}]}
    with pytest.raises(ValueError) as err:
        engine({"Zeros": slot("Zeros", ["c"])}, pushes=[push]).build()
    assert "Push[huge:c]: c was given" in str(err.value)


# ------------------------------------------------------------------------------------------ start steps and notes
def test_a_field_filled_by_a_start_step_is_what_round_one_reads_from_the_previous_round():
    """Round 1 was given the default of fields.yaml, not what the start step wrote; and the start step's note was dropped."""
    T.StartsField.seen = []
    w = engine({"StartsField": slot("StartsField", ["seeded"])}, {"seeded": number(default=-1.0)}).build()
    assert T.StartsField.seen[0] == 42.0 and np.all(w.fields["seeded"] == 42.0)
    assert w.notices == [{"kind": "process_note", "slot": "StartsField", "stage": "climate", "what": "the start step filled the field",
                          "value": 42, "first_round": 0, "last_round": 0, "rounds": 1}]


def test_a_note_cannot_take_the_names_the_engine_uses_for_its_own_entries():
    """ctx.note("...", kind="mine") turned the notice into one of kind "mine"."""
    with pytest.raises(ContractError) as err:
        engine({"BadNote": slot("BadNote", ["a"])}).build()
    assert "a note cannot carry a detail named kind, rounds" in str(err.value)


def test_a_note_raised_in_every_round_of_a_history_counts_its_rounds():
    fields = {**GEO_FIELDS, "round_no": number()}
    w = engine({**GEO_SLOTS, "RoundField": slot("RoundField", ["round_no"])}, fields, GEO_GROUPS, stages=WITH_GEO).build()
    assert [n for n in w.notices if n["kind"] == "process_note"] == [
        {"kind": "process_note", "slot": "RoundField", "stage": "geo", "what": "another round", "first_round": 1, "last_round": 5, "rounds": 5}]


def test_a_value_brought_back_into_range_by_a_later_step_leaves_no_notice():
    """The notice belongs to the value the world ends with, not to a step on the way there."""
    fields = {"level": number(range=[0, 100]), "ones": number(), "month_no": GEO_FIELDS["month_no"], "heading": GEO_FIELDS["heading"]}
    slots = {"SetupTooBig": slot("SetupTooBig", ["level"])}
    cap = {"id": "cap", "region": WHOLE_PLANET, "pushes": [{"field": "level", "cap_max": 50.0}]}
    assert engine(slots, fields, pushes=[cap]).build().notices == []
    left = engine(slots, fields).build().notices
    assert len(left) == 1 and left[0]["kind"] == "field_outside_range" and left[0]["highest"] == 500.0


# ------------------------------------------------------------------------------------------ tables
@pytest.mark.parametrize("values,said", [(["a", "b"], "<U1"), ([None, 1.0], "object"), ([1 + 2j, 3.0], "complex128"),
                                         (["1.5", "2.5"], "<U3")])
def test_a_table_column_takes_numbers_or_true_and_false_and_nothing_else(values, said):
    """Text became True in a true-or-false column, numbers written as text and complex numbers were taken as numbers,
    and None raised an error that named nothing."""
    T.TableMaker.columns = {"item": [0, 1], "value": values}
    try:
        with pytest.raises(ContractError) as err:
            engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
        assert f"column value holds values of type {said}" in str(err.value)
    finally:
        T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}


def test_text_in_a_true_or_false_column_is_refused():
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5], "ok": ["yes", "no"]}
    try:
        with pytest.raises(ContractError) as err:
            engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}, tables=BOOL_TABLE).build()
        assert "column ok holds values of type" in str(err.value)
    finally:
        T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}


def test_a_table_read_from_the_previous_round_cannot_be_changed_by_its_reader():
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    with pytest.raises(TypeError):
        engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "LaggedTableVandal": slot("LaggedTableVandal", ["c"])}).build()


# ------------------------------------------------------------------------------------------ outlines
def test_a_cell_exactly_on_a_side_of_an_outline_is_inside_whichever_way_the_corners_run():
    """Such a cell subtends half a turn, counted as plus or minus by the last bit of a sum: it was inside for one
    order of travel and outside for the other (15 cells of an L-shaped outline in the second review)."""
    m = get_mesh(5)
    shape = [[0, 0], [0, 40], [20, 40], [20, 20], [40, 20], [40, 0]]          # an L; its west side runs along the meridian of 0 degrees
    one_way, other_way = iv._inside_outline(m.xyz, shape), iv._inside_outline(m.xyz, shape[::-1])
    on_the_west_side = (np.abs(m.lon) < 1e-9) & (m.lat >= 0.0) & (m.lat <= 40.0)
    assert on_the_west_side.sum() >= 5 and one_way[on_the_west_side].all()
    assert np.array_equal(one_way, other_way)
    assert not one_way[(m.lon > 25.0) & (m.lat > 25.0)].any()                 # the notch of the L is outside


@pytest.mark.parametrize("corners,said", [
    ([[0, 0], [0, 40], [40, 0], [40, 40]], "its sides cross"),
    ([[0, 0], [0, 20], [0, 40]], "it encloses no area"),
    ([[0, 0], [100, 20], [0, 40]], "a corner has a latitude outside -90 to 90"),
    ([[0, 0], [0, 180], [40, 90]], "lie opposite each other"),
    ([[0, 0], [0, 0], [40, 20]], "two corners in a row are the same point"),
    ([[0, 0], [0, 120], [0, 240]], "must be smaller than a hemisphere"),
    ([[60, 0], [60, 120], [60, 240], [-50, 170]], "must be smaller than a hemisphere"),
])
def test_an_outline_that_cannot_be_used_is_refused_on_loading(corners, said):
    """Outlines with no area, with sides that cross, with a latitude of 100 or wider than half the planet were taken,
    and what they covered was decided by chance."""
    with pytest.raises(ParameterError) as err:
        engine(MARKED, GEO_FIELDS, pushes=[{"id": "p", "region": {"outline": corners}, "pushes": [{"field": "a", "add": 1.0}]}], keep_trio=True)
    assert "the outline cannot be used" in str(err.value) and said in str(err.value)
    assert said in "; ".join(iv.outline_problems(corners))
    assert iv.outline_problems([[10, -10], [10, 10], [-10, 10], [-10, -10]]) == []


def test_the_fade_of_a_circle_that_holds_no_cell_centre_still_reaches_the_cells_around_it():
    """The earlier test of this rule used a circle that happened to hold a cell centre, so it guarded nothing."""
    m = get_mesh(5)
    centre_cell = int(np.argmax(m.xyz @ iv._unit(12.3, 45.6)))
    corner = m.xyz[centre_cell] + m.xyz[m.nbr[centre_cell, 0]] + m.xyz[m.nbr[centre_cell, 1]]     # where three cells meet
    corner /= np.linalg.norm(corner)
    lat, lon = float(np.rad2deg(np.arcsin(corner[2]))), float(np.rad2deg(np.arctan2(corner[1], corner[0])))
    region = iv.Region(circle={"lat": lat, "lon": lon, "radius_km": 50.0}, outline=None, conditions=[], edge_km=1000.0)
    d = np.arccos(np.clip(m.xyz @ corner, -1, 1)) * 6371.0
    assert not (d <= 50.0).any()                                          # no cell centre lies inside the circle
    w = iv.region_weights(region, m, 6.371e6, None, True)
    assert (w > 0).sum() > 50 and np.allclose(w, np.clip(1.0 - np.maximum(d - 50.0, 0.0) / 1000.0, 0.0, 1.0), atol=1e-6)


# ------------------------------------------------------------------------------------------ conditions and amounts
@pytest.mark.parametrize("where,said", [
    ("ones above 0.5", "a condition is written as keys"),
    (7, "a condition is written as keys"),
    ({"above": 0.5}, "a condition must name the field it tests"),
    ({"field": "ones", "above": 0.5, "mnth": 3}, "a condition has no key named mnth"),
    ({"field": "ones", "above": 0.5, "lagged": "no"}, "lagged is true or false, found 'no'"),
    ({"field": "ones", "above": float("nan")}, "needs a finite number"),
    ({"field": "ones", "below": float("inf")}, "needs a finite number"),
    ({"field": "kind_of_place", "is_one_of": []}, "is given an empty list"),
    ({"field": "step_no", "is": 3.5}, "step_no holds whole numbers; the condition gives 3.5"),
])
def test_a_condition_that_cannot_be_read_is_refused_with_the_reason(where, said):
    """These raised errors that named neither the push nor the problem, or were taken as they stood."""
    fields = {**GEO_FIELDS, "step_no": dict(family="Toy", unit="count", shape="cell", kind="index", default=0)}
    slots = {**MARKED, "Stepper": slot("Stepper", ["step_no"])}
    with pytest.raises(ParameterError) as err:
        engine(slots, fields, pushes=[{"id": "p", "region": {"where": where}, "pushes": [{"field": "a", "add": 1.0}]}], keep_trio=True)
    assert said in str(err.value)


def test_a_class_that_does_not_exist_is_refused_with_the_name_of_the_push():
    with pytest.raises(ParameterError) as err:
        engine({}, pushes=[{"id": "p", "region": WHOLE_PLANET, "pushes": [{"field": "kind_of_place", "set": "tall"}]}], keep_trio=True)
    assert "push p:kind_of_place: 'tall' is not a class of kind_of_place" in str(err.value)


def test_a_push_may_test_the_field_it_changes():
    """The scheduler was handed the condition as a second read of the target and refused the push."""
    high = {"id": "high", "region": {"where": {"field": "a", "above": -1.0}}, "pushes": [{"field": "a", "add": 2.0}]}
    e = engine({}, pushes=[high], keep_trio=True)
    assert e.order()["climate"] == ["ToySource", "Push[high:a]", "ToyFollower", "ToyModifier"]
    w = e.build()
    assert w.settled["climate"] and np.allclose(w.fields["a"], 7.0, atol=1e-4)       # as with the unconditional push of the toy data
    assert np.allclose(w.push_records["high:a"]["before"], 5.0, atol=1e-4)           # the condition saw the value before the push


# ------------------------------------------------------------------------------------------ settings
def test_more_settings_that_mean_nothing_where_they_stand_are_refused_on_loading():
    """The rerun of the climate was refused only when the history ran, and not at all without a geological stage; a
    first date on a stage without dates and two stages of one name went through or failed with another message."""
    with pytest.raises(ParameterError) as err:
        engine({}, keep_trio=True, profile={"climate_rerun_every_rounds": 5})
    assert "that link is built in step 9" in str(err.value)
    stages = copy.deepcopy(WITH_GEO)
    stages["stages"][2]["first_date"] = "0001-01-01"
    with pytest.raises(ParameterError) as err:
        engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages)
    assert "gives a first date, which only a stage that steps through dates takes" in str(err.value)
    stages = copy.deepcopy(WITH_GEO)
    stages["stages"].append({"name": "climate", "clock": "climate"})
    with pytest.raises(ParameterError) as err:
        engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages)
    assert "names the stage climate more than once" in str(err.value)


@pytest.mark.parametrize("entry,said", [
    (dict(kind="index", default=1.5), "an index field holds whole numbers"),
    (dict(kind="number", default=float("inf")), "is not a finite number"),
    (dict(kind="number", dtype="int16"), "a field of kind number cannot be stored as int16"),
    (dict(kind="boolean", dtype="float32"), "a field of kind boolean cannot be stored as float32"),
    (dict(kind="category", categories=["x", "y"], dtype="float32"), "a field of kind category cannot be stored as float32"),
    (dict(kind="number", range=[10, 0]), "runs backwards"),
    (dict(kind="category", categories=[f"c{k}" for k in range(40000)]), "40000 classes do not fit the stored type int16"),
])
def test_a_field_entry_that_cannot_be_stored_as_written_is_refused(entry, said):
    f = toy_file("fields")
    f["fields"]["x"] = dict(family="Toy", unit="none", shape="cell", **entry)
    with pytest.raises(ParameterError) as err:
        Engine(TOY, profile="toy", overrides={"fields": f})
    assert said in str(err.value)


def test_a_true_or_false_field_takes_no_other_whole_numbers_than_0_and_1():
    f = toy_file("fields")
    f["fields"]["flag"] = dict(family="Toy", unit="true or false", shape="cell", kind="boolean", default=False)
    spec = Registry(Parameters(TOY, {"fields": f})).fields["flag"]
    assert spec.cast(np.array([0, 1] * 81), 162, 12).dtype == np.bool_
    with pytest.raises(ValueError) as err:
        spec.cast(np.array([0, 2] * 81), 162, 12)
    assert "takes only 0 and 1" in str(err.value)


# ------------------------------------------------------------------------------------------ the fingerprint of a field
def test_the_fingerprint_of_a_field_holds_everything_that_shaped_it():
    """It left out a push on a group that a modifier of the field reads, the seed where a draw is made, the settings
    of the climate rounds and the mesh level. Two worlds that differed in one of these carried the same fingerprint."""
    def prints(pushes=(), profile=None, seed=None, extra=None):
        slots = {"GroupModifier": slot("GroupModifier", [])}
        slots.update(extra or {})
        e = engine(slots, pushes=list(pushes), keep_trio=True, profile=profile)
        if seed is not None:
            e.seed = seed
        e.build()
        return e.world.lineage
    heat = lambda amount, **more: {"id": "heat", "region": WHOLE_PLANET, "pushes": [{"group": "toy_heat", "add": amount}], **more}
    plain = prints([heat(0.5)])
    assert plain["b"]["fingerprint"] == prints([heat(0.5)])["b"]["fingerprint"]
    assert plain["b"]["fingerprint"] != prints([heat(0.25)])["b"]["fingerprint"]        # a push on the group its modifier reads
    assert plain["a"]["fingerprint"] == prints([heat(0.25)])["a"]["fingerprint"]        # ... which is nothing to a
    assert plain["a"]["fingerprint"] != prints([heat(0.5)], seed=8)["a"]["fingerprint"]    # ToySource declares a draw
    assert plain["b"]["fingerprint"] == prints([heat(0.5)], seed=8)["b"]["fingerprint"]    # ToyFollower and its modifiers make none
    slower = copy.deepcopy(toy_file("profiles")["profiles"]["toy"]["climate"])
    slower["blend_weight"] = 0.25
    assert plain["b"]["fingerprint"] != prints([heat(0.5)], profile={"climate": slower})["b"]["fingerprint"]
    assert plain["b"]["fingerprint"] != prints([heat(0.5)], profile={"mesh_level": 3})["b"]["fingerprint"]


def test_the_fingerprint_changes_with_the_rounds_of_a_push_and_with_a_push_on_a_group_the_writer_reads():
    def elev(pushes):
        T.Ground.seen = []
        return geo_engine(pushes).build().lineage["elev"]["fingerprint"]
    on_field = lambda rounds: [{"id": "p", "region": WHOLE_PLANET, "when": {"rounds": rounds}, "pushes": [{"field": "elev", "add": 1.0}]}]
    on_group = lambda amount: [{"id": "g", "region": WHOLE_PLANET, "pushes": [{"group": "geo_now", "add": amount}]}]
    assert elev(on_field([1, 2])) == elev(on_field([1, 2])) != elev(on_field([1, 3]))
    assert elev(on_group(1.0)) == elev(on_group(1.0)) != elev(on_group(2.0))
    assert elev(on_group(1.0)) != elev([])


# ------------------------------------------------------------------------------------------ parameter files
CHAINED = """
base: &base {a: 1, b: 2}
middle: &middle
  <<: *base
  b: 3
top:
  <<: *middle
  a: 4
again:
  <<: *middle
"""


def test_a_key_taken_over_from_an_anchor_and_set_again_is_not_a_key_written_twice():
    """The check ran after the merges had been worked into the maps, so a legal file was refused: a map that merges a
    map which itself merges another, and overrides one of its keys."""
    assert load_yaml_text(CHAINED, "chained.yaml") == {"base": {"a": 1, "b": 2}, "middle": {"a": 1, "b": 3},
                                                      "top": {"a": 4, "b": 3}, "again": {"a": 1, "b": 3}}
    with pytest.raises(ParameterError) as err:
        load_yaml_text("x: {a: 1, a: 2}", "twice.yaml")
    assert "twice.yaml" in str(err.value) and "the key 'a' is written twice" in str(err.value)
    with pytest.raises(ParameterError):
        load_yaml_text("top:\n  <<: {a: 1}\n  b: 2\n  b: 3\n", "twice.yaml")
    assert load_yaml_text("", "empty.yaml") is None


def test_a_push_file_given_on_the_command_line_is_read_with_the_same_rules(tmp_path, capsys):
    """It was read with plain YAML: a key written twice went through, and the second value was used."""
    pushes = tmp_path / "pushes.yaml"
    pushes.write_text("- id: lift\n  region: {circle: {lat: 0.0, lon: 0.0, radius_km: 30000}}\n"
                      "  pushes:\n    - {field: a, add: 2.0, add: 3.0}\n")
    assert cli.main(["order", "--data", str(TOY), "--profile", "toy", "--interventions", str(pushes)]) == 2
    assert "the key 'add' is written twice" in capsys.readouterr().err
    assert cli.main(["order", "--data", str(TOY), "--profile", "toy", "--interventions", str(tmp_path / "none.yaml")]) == 2
    assert "the push file is missing" in capsys.readouterr().err
    pushes.write_text("- id: lift\n  region: {circle: {lat: 0.0, lon: 0.0, radius_km: 30000}}\n  pushes:\n    - {field: a, add: 2.0}\n")
    assert cli.main(["order", "--data", str(TOY), "--profile", "toy", "--interventions", str(pushes)]) == 0
    assert "Push[lift:a]" in capsys.readouterr().out


def test_a_bar_in_the_name_of_a_slot_or_of_a_draw_is_refused():
    """The key of a draw is seed|slot|purpose|round: slot a|b with purpose c got the key of slot a with purpose b|c."""
    with pytest.raises(ParameterError) as err:
        engine({"Odd|Name": slot("MemoWriter", ["a"])})
    assert "contains the bar |" in str(err.value)
    seeds = toy_file("seeds")
    seeds["draws"]["ToySource"] = ["jitter", "one|two"]
    with pytest.raises(ParameterError) as err:
        Engine(TOY, profile="toy", overrides={"seeds": seeds})
    assert "'one|two' contains the bar |" in str(err.value)


# ------------------------------------------------------------------------------------------ the harness
def test_the_harness_refuses_what_would_leave_a_test_empty():
    """A misspelt constant was passed on in silence, so that a test meant to change a constant changed nothing; an
    unknown slot, table or group raised an error that named nothing."""
    h = Harness(level=2, data_dir=TOY)
    h.params.data["models"]["slots"]["Reader"] = slot("HeatReader", ["c"])
    h.params.data["models"]["slots"]["Keeper"] = slot("TableKeeper", ["table:toy_items"])
    with pytest.raises(KeyError) as err:
        h.run("ToySource", lagged={"b": np.zeros(h.mesh.n)}, constants={"gian": 2.0})
    assert "models.yaml.slots.ToySource.constants has no entry named 'gian' (it has: gain)" in str(err.value)
    with pytest.raises(KeyError) as err:
        h.run("ToySource", lagged={"b": np.zeros(h.mesh.n)}, shared={"won": 2.0})
    assert "models.yaml.shared has no entry named 'won'" in str(err.value)
    with pytest.raises(KeyError) as err:
        h.run("NoSuchSlot")
    assert "models.yaml has no slot named 'NoSuchSlot'" in str(err.value)
    for kind, inputs in (("group", {"groups": {"heat": {"m": np.zeros(h.mesh.n)}}}), ("table", {"lagged_tables": {"items": {}}}),
                         ("field", {"lagged": {"bb": np.zeros(h.mesh.n)}})):
        with pytest.raises(KeyError) as err:
            h.run("Reader", **inputs)
        assert f"the test hands Reader the {kind}" in str(err.value) and "which the data files do not declare" in str(err.value)
    with pytest.raises(ValueError) as err:
        h.run("ToySource", lagged={"b": np.zeros(h.mesh.n)}, start=True)
    assert "ToySource has no start step" in str(err.value)
    assert np.all(h.run("ToySource", lagged={"b": np.full(h.mesh.n, 2.0)}, constants={"gain": 2.0}).fields["a"] == 5.0)


def test_the_harness_hands_over_group_members_as_the_engine_stores_them():
    """A member is handed over read-only and in its stored type: that of its field if it is a declared field (the
    engine stores heat_member as fields.yaml says), a 32-bit number for a push."""
    h = Harness(level=2, data_dir=TOY)
    h.params.data["models"]["slots"]["Reader"] = slot("HeatReader", ["c"])
    f = h.registry.fields
    h.registry.fields = {**f, "heat_member": type(f["heat_member"])(**{**f["heat_member"].__dict__, "dtype": "float64"})}
    seen = {}

    class Spy(T.HeatReader):
        def run(self, ctx):
            g = ctx.read_group_lagged("toy_heat")
            seen.update({k: (v.dtype, v.flags.writeable) for k, v in g.members.items()})
            ctx.write("c", np.broadcast_to(g.total, (ctx.months, ctx.mesh.n)))
    T.Spy = Spy
    h.params.data["models"]["slots"]["Spy"] = slot("Spy", ["c"])
    third = np.full(h.mesh.n, 1.0 / 3.0)
    out = h.run("Spy", groups={"toy_heat": {"heat_member": third, "push:test": third}})
    assert seen == {"heat_member": (np.dtype("float64"), False), "push:test": (np.dtype("float32"), False)}
    assert np.allclose(out.fields["c"], 2.0 / 3.0, atol=1e-7)


# ------------------------------------------------------------------------------------------ threads and memos
def test_a_build_sets_the_thread_counts_and_hands_them_back_the_compiled_loops_included():
    """The count of the compiled loops (numba) stayed at the last build's value for the rest of the interpreter."""
    import numba
    from threadpoolctl import threadpool_info
    if numba.config.NUMBA_NUM_THREADS < 2:
        pytest.skip("this machine gives the compiled loops one thread only")
    before_numba = numba.get_num_threads()
    numba.set_num_threads(2)
    try:
        before = sorted({lib["num_threads"] for lib in threadpool_info()})
        fields = {"ones": number(), "month_no": GEO_FIELDS["month_no"], "heading": GEO_FIELDS["heading"]}
        engine({"ThreadProbe": slot("ThreadProbe", ["ones"])}, fields).build()
        inside_numba, inside_libraries = T.ThreadProbe.seen
        assert inside_numba == 1 and set(inside_libraries) <= {1}        # the toy profile asks for one thread
        assert numba.get_num_threads() == 2                              # handed back
        assert sorted({lib["num_threads"] for lib in threadpool_info()}) == before
        h = Harness(level=2, data_dir=TOY)
        h.params.data["models"]["slots"]["ThreadProbe"] = slot("ThreadProbe", ["ones"])
        h.registry = Registry(Parameters(TOY, {"fields": {"fields": {**toy_file("fields")["fields"], **fields}, "groups": {}}}))
        h.run("ThreadProbe")
        assert T.ThreadProbe.seen[0] == 1 and numba.get_num_threads() == 2
    finally:
        numba.set_num_threads(before_numba)


def test_a_second_build_of_one_engine_starts_with_empty_memos():
    """A world with no climate stage, so that nothing but the start of the build empties the memos."""
    overrides = {"models": {"shared": {}, "slots": {"MemoCounter": slot("MemoCounter", ["ones"])}},
                 "fields": {"fields": {"ones": number()}, "groups": {}}, "interventions": [],
                 "stages": {"stages": [{"name": "setup", "clock": "once"}]}}
    e = Engine(TOY, profile="toy", overrides=overrides)
    first, second = e.build().fields["ones"][0], e.build().fields["ones"][0]
    assert first == second == 1.0


# ------------------------------------------------------------------------------------------ the store
def test_a_stale_file_where_the_partial_store_goes_does_not_stop_a_save(tmp_path):
    e = engine({}, keep_trio=True)
    w = e.build()
    target = tmp_path / "w.zarr"
    (tmp_path / "w.zarr.partial").write_text("left behind by something else")
    assert StoreView(store.save(w, e, target)).field_names() and sorted(p.name for p in tmp_path.iterdir()) == ["w.zarr"]


def test_a_monthly_field_is_stored_one_month_to_a_piece(tmp_path):
    """So that the viewer can fetch one month. A table with twelve rows is not cut that way."""
    T.TableMaker.columns = {"item": list(range(12)), "value": [0.5] * 12}
    e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "LaterTableReader": slot("LaterTableReader", ["c"])}, keep_trio=True)
    w = e.build()
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    root = zarr.open_group(store=str(store.save(w, e, tmp_path / "w.zarr")), mode="r")
    assert root["fields"]["c"].shape == (12, w.n) and root["fields"]["c"].chunks == (1, w.n)
    assert root["fields"]["a"].chunks == (w.n,) and root["tables"]["toy_items"]["value"].chunks == (12,)


# ------------------------------------------------------------------------------------------ why answers and the server
def served(path):
    srv = make_server(path, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_a_class_code_outside_the_list_is_shown_as_such_by_the_why_answer_and_by_the_server(tmp_path):
    e = engine({"ToySource": toy_file("models")["slots"]["ToySource"], "ToyFollower": slot("OddClass", ["b", "kind_of_place"])})
    w = e.build()
    assert [n["kind"] for n in w.notices] == ["field_outside_range"]
    view = MemoryView(w, e)
    assert explain(view, 3, "kind_of_place")["chain"][0]["value"] == "no class (code 5)"
    srv, base = served(store.save(w, e, tmp_path / "w.zarr"))
    try:
        assert json.loads(urllib.request.urlopen(base + "/api/cell?id=3").read())["values"]["kind_of_place"] == "no class (code 5)"
    finally:
        srv.shutdown()


def test_why_answers_say_which_cell_every_entry_is_about_and_stay_within_their_length():
    """Entries about another cell than the one asked about (a push there, the end of the chain there) did not say so;
    answers ran to 18 entries where 16 were announced."""
    lift = {"id": "lift", "region": WHOLE_PLANET, "pushes": [{"field": "a", "add": 2.0}]}
    e = engine({}, pushes=[lift], keep_trio=True)
    w = e.build()
    patterns = {"ToyFollower": {"b": {"says": "b is {value}.", "follows": ["a"], "drivers": {}}},
                "ToySource": {"a": {"says": "a is {value}:", "form": "sum",
                                    "drivers": {"base": {"base": True, "says": "it starts from {v}"},
                                                "from_b": {"says": "b adds {v}", "follows": ["b"], "at": "elsewhere"}}}}}
    view = MemoryView(w, e)
    view.attrs["explanations"] = patterns
    w.drivers["a"]["elsewhere"] = np.full(w.n, 7, dtype=np.int32)         # the cause of a lies in cell 7, for every cell
    view.attrs["drivers"]["a"] = sorted(w.drivers["a"])
    answer = explain(view, 3, "b")
    others = [entry for entry in answer["chain"] if entry["cell"] != 3]
    assert others and all(entry["text"].startswith("At ") for entry in others)
    assert any("push" in entry for entry in others)                       # the push in cell 7 is among them
    assert len(answer["chain"]) <= MAX_STEPS + 1
    assert "After ToyFollower wrote it, ToyModifier changed it" in answer["chain"][0]["text"]     # a modifier is named


def test_a_missing_value_a_true_or_false_field_and_a_pushed_direction_are_put_into_words():
    """"The ocean floor here is undefined old"; a true-or-false value before a push printed as 0.00; and the why
    answer for a pushed direction with one value per cell failed in every pushed cell."""
    fields = {**GEO_FIELDS, "flag": dict(family="Toy", unit="true or false", shape="cell", kind="boolean", default=False),
              "gappy": number(default=0.0, allow_missing=True)}
    slots = {**GEO_SLOTS, "Flipper": slot("Flipper", ["flag"]), "PartlyMissing": slot("PartlyMissing", ["gappy"])}
    pushes = [{"id": "turn", "region": WHOLE_PLANET, "pushes": [{"field": "heading", "set": {"east": 0.0, "north": 2.0}}]},
              {"id": "yes", "region": WHOLE_PLANET, "pushes": [{"field": "flag", "set": True}]}]
    e = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO, max_rounds=3)
    w = e.build()
    view = MemoryView(w, e)
    for cell in (0, 5, 100):
        text = as_text(explain(view, cell, "heading"))
        assert "entry turn" in text and "Before the push the value was 1.00" in text
    text = as_text(explain(view, 5, "flag"))
    assert "entry yes" in text and ("Before the push the value was true" in text or "Before the push the value was false" in text)
    assert "0.00" not in text
    assert explain(view, 0, "gappy")["chain"][0]["text"] == "gappy has no value here."        # cell 0 is the missing one
    view.attrs["explanations"] = {"PartlyMissing": {"gappy": {"says": "It is {value}.", "says_missing": "Nothing was measured at {lat}."}}}
    assert explain(view, 0, "gappy")["chain"][0]["text"].startswith("Nothing was measured at 90.0° north")
    assert explain(view, 1, "gappy")["chain"][0]["text"] == "It is 5.00 none."


def test_a_driver_that_names_a_class_or_a_row_is_read_whatever_it_is_stored_as():
    """A class driver stored as fractions raised a TypeError; so did a table with a column called row."""
    T.TableMaker.columns = {"row": [10, 20], "value": [1.0, 2.5]}
    tables = {"tables": {"toy_items": {"columns": {"row": "int32", "value": "float64"}}}}
    e = engine({"TableMaker": slot("TableMaker", ["table:toy_items"]), "ClassDriver": slot("ClassDriver", ["c"])}, tables=tables)
    w = e.build()
    T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}
    view = MemoryView(w, e)
    view.attrs["explanations"] = {"ClassDriver": {"c": {"says": "c is {value}:", "drivers": {
        "regime": {"names": ["calm", "stormy"], "says": "the regime is {v}"},
        "item": {"row_of": "toy_items", "says": "see row {row_number}, whose own column row holds {row} and whose value is {value}"}}}}}
    text = explain(view, 2, "c")["chain"][0]["text"]
    assert "the regime is stormy" in text and "see row 1, whose own column row holds 20 and whose value is 2.5" in text


def test_the_page_shows_every_kind_of_notice_and_a_fault_in_an_answer_comes_back_as_an_answer(tmp_path, monkeypatch):
    """A process's note and an overrun time limit were not shown; an error inside a why answer closed the connection."""
    e = engine({"AlwaysNotes": slot("AlwaysNotes", ["a"])}, profile={"run_time_limit_s": 1.0e-9})
    w = e.build()
    srv, base = served(store.save(w, e, tmp_path / "w.zarr"))
    try:
        notices = json.loads(urllib.request.urlopen(base + "/api/world").read())["notices"]
        assert any("AlwaysNotes noted: the solver stopped at its cap" in n for n in notices)
        assert any("more than the 1e-09 seconds its profile allows" in n for n in notices)
        why = json.loads(urllib.request.urlopen(base + "/api/explain?cell=1&field=a").read())
        assert any("AlwaysNotes noted" in n for n in why["notices"]) and any("seconds its profile allows" in n for n in why["notices"])
        from worldengine import server

        def broken(view, cell, field):
            raise RuntimeError("a fault of the engine")
        monkeypatch.setattr(server, "explain", broken)
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/api/explain?cell=1&field=a")
        assert err.value.code == 500 and "RuntimeError: a fault of the engine" in json.loads(err.value.read())["error"]
    finally:
        srv.shutdown()


# ------------------------------------------------------------------------------------------ means around the planet
def test_zonal_means_of_a_monthly_field_come_month_by_month():
    """A field with one slice per month raised "object too deep"."""
    m = get_mesh(3)
    monthly = np.stack([np.cos(np.deg2rad(m.lat)) * (k + 1) for k in range(12)])
    lat, means = op.zonal_mean(m, monthly, 10.0)
    assert means.shape == (12, lat.size)
    for k in (0, 7):
        assert np.array_equal(means[k], op.zonal_mean(m, monthly[k], 10.0)[1])
    with pytest.raises(ValueError) as err:
        op.zonal_mean(m, np.zeros((m.n, 3)), 10.0)
    assert "one value per cell, or one per month and cell" in str(err.value)
