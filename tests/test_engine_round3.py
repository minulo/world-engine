"""Edge cases of the engine found by the third check of build steps 0 and 1. Each test states the rule it guards."""
import json
import urllib.error
import urllib.request

import numpy as np
import pytest

from conftest import TOY
import toy_processes as T
from test_engine_cases import GEO_FIELDS, GEO_GROUPS, GEO_SLOTS, WHOLE_PLANET, WITH_GEO, engine, geo_engine, number, slot, toy_file
from test_engine_round2 import served, touched_nothing
from worldengine import interventions as iv
from worldengine import store
from worldengine.causes import MAX_STEPS, as_text, explain
from worldengine.fields import Registry
from worldengine.mesh import get_mesh
from worldengine.params import ParameterError, Parameters
from worldengine.process import ContractError
from worldengine.store import MemoryView
from worldengine.testing import Harness

LIFT = {"id": "lift", "region": WHOLE_PLANET, "pushes": [{"field": "a", "add": 2.0}]}      # with it the toy loop settles at b = 8
B_STILL_LOW = {"where": {"field": "b", "lagged": True, "below": 4.5}}      # true in round 1 only: b starts at 4 and climbs
B_HAS_RISEN = {"where": {"field": "b", "lagged": True, "above": 4.5}}      # true from round 2 on


def one_round(pushes, slots=GEO_SLOTS):
    stages = {"stages": [{"name": "setup", "clock": "once"},
                         {"name": "geo", "clock": "geological", "round_length_my": 1.0, "history_length_my": 1.0},
                         {"name": "climate", "clock": "climate"}]}
    return engine(slots, GEO_FIELDS, GEO_GROUPS, pushes, stages=stages)


# ------------------------------------------------------------------------------------------ what a push did
def test_a_climate_push_that_covers_no_cell_in_the_settled_round_is_reported_as_having_changed_nothing():
    """The rounds of the climate clock are a solver's working steps, and the world holds the settled round only. A push
    whose condition held in an early round and in no cell at the end changed nothing in the stored world. Since the
    fixes of the second review, "covered a cell in some round" counted, and the notice was no longer raised."""
    pushes = [LIFT,
              {"id": "early_field", "region": B_STILL_LOW, "pushes": [{"field": "c", "add": 1.0}]},
              {"id": "early_group", "region": B_STILL_LOW, "pushes": [{"group": "toy_heat", "add": 1.0}]},
              {"id": "late_field", "region": B_HAS_RISEN, "pushes": [{"field": "sum_now", "add": 1.0}]}]
    e = engine({"Zeros": slot("Zeros", ["c"]), "SumNow": slot("SumNow", ["sum_now"])}, {"sum_now": number()}, pushes=pushes, keep_trio=True)
    w = e.build()
    assert w.settled["climate"] and w.rounds_used["climate"] > 3 and np.allclose(w.fields["b"], 8.0, atol=1e-4)
    assert np.all(w.fields["c"] == 0.0)                                   # neither early push shows in the stored world
    assert np.all(w.fields["sum_now"] == 1.0)                             # the group gave nothing; the late push added its 1
    assert touched_nothing(w) == {"early_field:c": None, "early_group:toy_heat": None}
    rounds = w.rounds_used["climate"]
    for pid, touched in (("early_field:c", False), ("early_group:toy_heat", False), ("late_field:sum_now", True)):
        assert w.push_activity[pid] == {"stage": "climate", "first_round": 1, "last_round": rounds, "rounds": rounds, "touched": touched}
    assert not w.push_records["early_field:c"]["weight"].any() and not w.push_records["early_group:toy_heat"]["weight"].any()
    assert w.push_records["late_field:sum_now"]["weight"].all()


def test_in_a_history_a_push_that_covered_cells_in_an_early_round_is_not_reported():
    """The other clock: every round of a history happened, so a push that covered cells in round 2 did change the world,
    whatever it covers in the last round."""
    fields = {**GEO_FIELDS, "round_no": number()}
    slots = {**GEO_SLOTS, "RoundField": slot("RoundField", ["round_no"])}
    in_round_two = {"where": [{"field": "round_no", "above": 1.5}, {"field": "round_no", "below": 2.5}]}
    pushes = [{"id": "second", "region": in_round_two, "pushes": [{"field": "elev", "add": 9.0}]}]
    w = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO).build()
    assert np.all(w.fields["elev"] == 100.0) and touched_nothing(w) == {}
    assert w.push_activity["second:elev"] == {"stage": "geo", "first_round": 1, "last_round": 5, "rounds": 5, "touched": True}


def test_the_record_of_a_group_push_with_a_condition_carries_the_weights_of_the_sum_that_was_read():
    """Two pushes on a group that is read from the previous round: one covers the planet in rounds 1 to 4, the other in
    round 5. The reader of round 5 is given the sum of round 4, which holds the first at full weight and the second
    at none. The records said the opposite: each carried the weights of the last round the push was worked out in."""
    fields = {**GEO_FIELDS, "round_no": number()}
    slots = {**GEO_SLOTS, "RoundField": slot("RoundField", ["round_no"])}
    pushes = [{"id": "first_four", "region": {"where": {"field": "round_no", "below": 4.5}}, "pushes": [{"group": "geo_push", "add": 100.0}]},
              {"id": "fifth", "region": {"where": {"field": "round_no", "above": 4.5}}, "pushes": [{"group": "geo_push", "add": 7.0}]}]
    T.Ground.seen = []
    w = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO).build()
    assert [before for _, before, _ in T.Ground.seen] == [0.0, 100.0, 100.0, 100.0, 100.0]
    assert np.all(w.push_records["first_four:geo_push"]["weight"] == 1.0)
    assert np.all(w.push_records["fifth:geo_push"]["weight"] == 0.0)
    assert touched_nothing(w) == {}                                       # both covered cells in some round of the history


def test_a_group_read_both_ways_records_the_weights_of_the_later_sum():
    fields = {**GEO_FIELDS, "round_no": number()}
    slots = {"Marker": GEO_SLOTS["Marker"], "RoundField": slot("RoundField", ["round_no"]), "TwoReads": slot("TwoReads", ["elev"])}
    pushes = [{"id": "fifth", "region": {"where": {"field": "round_no", "above": 4.5}}, "pushes": [{"group": "geo_now", "add": 7.0}]}]
    T.TwoReads.seen = []
    w = engine(slots, fields, GEO_GROUPS, pushes, stages=WITH_GEO).build()
    assert T.TwoReads.seen[-1] == (5, 0.0, 7.0)                           # the same-round read is given the sum of round 5
    assert np.all(w.push_records["fifth:geo_now"]["weight"] == 1.0)


def test_before_the_first_round_of_a_history_no_push_was_in_force_whatever_its_region():
    """A push with a fixed region and no `when` reached a reader "from the previous round" in round 1, as if it had been
    in force before the history began; the same push with `when`, or with a condition, reached it from round 2. In
    a history of one round the first left a record and the others were reported as never read."""
    kinds = [{"id": "fixed", "region": WHOLE_PLANET, "pushes": [{"group": "geo_push", "add": 1.0}]},
             {"id": "fixed_when", "region": WHOLE_PLANET, "when": {"rounds": [1, 5]}, "pushes": [{"group": "geo_push", "add": 2.0}]},
             {"id": "condition", "region": {"where": {"field": "ones", "above": 0.5}}, "pushes": [{"group": "geo_push", "add": 4.0}]}]
    T.Ground.seen = []
    w = geo_engine(kinds).build()
    assert [before for _, before, _ in T.Ground.seen] == [0.0, 7.0, 7.0, 7.0, 7.0]
    assert sorted(w.push_records) == ["condition:geo_push", "fixed:geo_push", "fixed_when:geo_push"] and touched_nothing(w) == {}
    T.Ground.seen = []
    w = one_round(kinds).build()
    assert [before for _, before, _ in T.Ground.seen] == [0.0]
    unread = "no process read group geo_push in a round whose sum held it"
    assert w.push_records == {} and touched_nothing(w) == {pid + ":geo_push": unread for pid in ("fixed", "fixed_when", "condition")}
    for pid in ("fixed", "fixed_when", "condition"):
        assert w.push_activity[pid + ":geo_push"]["rounds"] == 1


def test_on_the_climate_clock_a_push_with_a_fixed_region_is_there_from_the_first_round():
    """The climate clock has no history: its rounds lead to one settled year, and the push belongs to that year."""
    T.LaggedSumLog.seen = []
    w = engine({"LaggedSumLog": slot("LaggedSumLog", ["c"])},
               pushes=[{"id": "sink", "region": WHOLE_PLANET, "pushes": [{"group": "toy_heat", "add": -3.0}]}]).build()
    assert T.LaggedSumLog.seen[0] == -3.0 and np.all(w.fields["c"] == -3.0)
    assert np.all(w.push_records["sink:toy_heat"]["weight"] == 1.0)


# ------------------------------------------------------------------------------------------ start steps
def test_what_a_start_step_adds_to_a_group_is_what_round_one_reads_from_the_previous_round():
    T.LaggedSumLog.seen = []
    slots = {"StartsMember": slot("StartsMember", ["heat_member"]), "LaggedSumLog": slot("LaggedSumLog", ["c"])}
    w = engine(slots).build()
    assert T.LaggedSumLog.seen[0] == 5.0 and np.all(w.fields["c"] == 5.0)


def test_the_harness_hands_round_one_what_the_start_step_filled_as_the_engine_does():
    """The harness carried only tables from a start step: a field filled there was read as its default (-1 for 42)."""
    h = Harness(level=2, data_dir=TOY)
    h.params.data["models"]["slots"]["StartsField"] = slot("StartsField", ["seeded"])
    h.params.data["models"]["slots"]["StartsMember"] = slot("StartsMember", ["heat_member"])
    h.registry = Registry(Parameters(TOY, {"fields": {"fields": {**toy_file("fields")["fields"], "seeded": number(default=-1.0)},
                                                      "groups": toy_file("fields")["groups"]}}))
    T.StartsField.seen = []
    out = h.run("StartsField", start=True)
    assert T.StartsField.seen == [42.0] and np.all(out.fields["seeded"] == 42.0)
    with pytest.raises(ValueError) as err:                                # the test cannot give the same field a second time
        h.run("StartsField", start=True, lagged={"seeded": np.zeros(h.mesh.n)})
    assert "start=True fills seeded" in str(err.value)
    T.StartsField.seen = []
    h.run("StartsField", lagged={"seeded": np.full(h.mesh.n, 3.0)})       # without the start step the given value is read
    assert T.StartsField.seen == [3.0]


def test_the_harness_refuses_an_input_that_the_process_never_reads():
    """Such an input is never read, so a test that gives it checks less than it seems to."""
    h = Harness(level=2, data_dir=TOY)
    n = h.mesh.n
    with pytest.raises(KeyError) as err:
        h.run("ToySource", reads={"b": np.zeros(n)})                      # ToySource reads b from the previous round
    assert "hands ToySource b under reads, but the process does not declare it there" in str(err.value)
    with pytest.raises(KeyError) as err:
        h.run("ToySource", lagged={"b": np.zeros(n), "a": np.zeros(n)})
    assert "hands ToySource a under lagged" in str(err.value)
    h.params.data["models"]["slots"]["Reader"] = slot("HeatReader", ["c"])
    with pytest.raises(KeyError) as err:
        h.run("Reader", groups={"toy_heat": {"heat_member": np.zeros(n)}}, reads={"a": np.zeros(n)})
    assert "hands Reader a under reads" in str(err.value)
    assert h.run("ToySource", lagged={"b": np.full(n, 4.0)}).fields["a"][0] == 3.0


# ------------------------------------------------------------------------------------------ tables and fields
def test_a_whole_number_too_large_for_its_column_is_refused_whatever_type_it_arrives_in():
    """An unsigned 4,000,000,000 in a 32-bit column wrapped round to a negative number, and cast back it looked unchanged."""
    T.TableMaker.columns = {"item": np.array([4_000_000_000, 1], dtype=np.uint32), "value": [1.0, 2.5]}
    try:
        with pytest.raises(ContractError) as err:
            engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
        assert "column item holds values that do not fit its type" in str(err.value)
        T.TableMaker.columns = {"item": np.array([40_000, 1], dtype=np.uint16), "value": [1.0, 2.5]}     # this one fits
        w = engine({"TableMaker": slot("TableMaker", ["table:toy_items"])}).build()
        assert w.tables["toy_items"]["item"].tolist() == [40_000, 1]
    finally:
        T.TableMaker.columns = {"item": [0, 1], "value": [1.0, 2.5]}


@pytest.mark.parametrize("entry,said", [
    (dict(family="Toy", unit="count", shape="cell", kind="index", dtype="int16", default=100000), "does not fit the stored type int16"),
    (dict(family="Toy", unit="none", shape="cell", kind="number", dtype="float32", default=1.0e39), "too large for the stored type float32"),
])
def test_a_default_that_its_stored_type_cannot_hold_is_refused_on_loading(entry, said):
    """Such a default was accepted and failed, or became infinite, when the first round asked for it."""
    with pytest.raises(ParameterError) as err:
        engine({}, {"odd": entry}, keep_trio=True)
    assert "fields.yaml.fields.odd" in str(err.value) and said in str(err.value)


def test_the_fingerprint_of_a_field_follows_the_settings_of_its_stage():
    """Three rounds of history instead of five make another world; the fingerprint did not change."""
    def prints(length):
        stages = {"stages": [{"name": "setup", "clock": "once"},
                             {"name": "geo", "clock": "geological", "round_length_my": 1.0, "history_length_my": length},
                             {"name": "climate", "clock": "climate"}]}
        w = engine(GEO_SLOTS, GEO_FIELDS, GEO_GROUPS, stages=stages).build()
        return {f: w.lineage[f]["fingerprint"] for f in ("elev", "ones")}
    five, three, five_again = prints(5.0), prints(3.0), prints(5.0)
    assert five == five_again
    assert five["elev"] != three["elev"]                                  # elev is worked out in the history
    assert five["ones"] == three["ones"]                                  # ones is not


# ------------------------------------------------------------------------------------------ regions of pushes
def test_an_outline_is_judged_by_the_smallest_cap_that_holds_its_corners_not_by_their_mean():
    """A belt 150 degrees long was accepted with four corners and refused with three more corners at one end: the
    mean of the corners moved toward that end, away from the far corner. Both fit in half the planet."""
    belt = [[-5, 0], [5, 0], [5, 150], [-5, 150]]
    crowded = [[-5, 0], [-2, 0], [0, 0], [2, 0], [5, 0], [5, 150], [-5, 150]]
    assert iv.outline_problems(belt) == [] and iv.outline_problems(crowded) == []
    m = get_mesh(4)
    assert np.array_equal(iv._inside_outline(m.xyz, belt), iv._inside_outline(m.xyz, crowded))
    inside = iv._inside_outline(m.xyz, crowded)
    assert inside[(np.abs(m.lat) < 3.0) & (m.lon > 10.0) & (m.lon < 140.0)].all()
    assert not inside[np.abs(m.lat) > 20.0].any()                         # its long sides are arcs that bulge to 18.7 degrees
    assert "must be smaller than a hemisphere" in "; ".join(iv.outline_problems([[-5, 0], [5, 0], [5, 120], [5, 240], [-5, 240], [-5, 120]]))
    assert iv.outline_problems([[60, 0], [60, 120], [60, 240], [-50, 170]]) == []      # fits a cap 85 degrees wide; the mean said no


def test_a_cell_centre_that_is_a_corner_of_an_outline_lies_inside_it():
    """The distance to a corner was taken from a dot product, which cannot tell nothing from 0.000001 degrees: a cell
    centre used as a corner came out as outside in 13 of 300 triangles."""
    m = get_mesh(4)
    rng = np.random.default_rng(3)
    missed = 0
    for _ in range(200):
        while True:
            a = int(rng.integers(m.n))
            near = np.flatnonzero((m.xyz @ m.xyz[a] > np.cos(0.5)) & (m.xyz @ m.xyz[a] < np.cos(0.1)))
            b, c = (int(x) for x in rng.choice(near, 2, replace=False))
            corners = [[float(m.lat[k]), float(m.lon[k])] for k in (a, b, c)]
            if not iv.outline_problems(corners):
                break
        inside = iv._inside_outline(m.xyz, corners)
        missed += int(not inside[[a, b, c]].all())
    assert missed == 0


@pytest.mark.parametrize("region,said", [
    ({"circle": {"lat": 0.0, "lon": 0.0, "radius_km": float("inf")}}, "region.circle.radius_km must be a length in km"),
    ({"circle": {"lat": 0.0, "lon": 0.0, "radius_km": 500.0}, "edge_km": float("inf")}, "region.edge_km must be a length in km"),
    ({"circle": {"lat": 0.0, "lon": 0.0, "radius_km": -5.0}}, "region.circle.radius_km: -5.0 must be above 0"),
    ({"circle": {"lat": 0.0, "lon": 0.0, "radius_km": 500.0}, "edge_km": float("nan")}, "region.edge_km: is not a number"),
])
def test_a_region_whose_size_is_not_a_length_is_refused_on_loading(region, said):
    """An infinite radius or edge was taken as it stood (the schema already refused a negative one and a missing number)."""
    with pytest.raises(ParameterError) as err:
        engine({}, pushes=[{"id": "p", "region": region, "pushes": [{"field": "a", "add": 1.0}]}], keep_trio=True)
    assert said in str(err.value)


# ------------------------------------------------------------------------------------------ why answers and the server
def test_a_missing_value_before_a_push_and_a_missing_driver_are_put_into_words():
    fields = {"gappy": number(default=0.0, allow_missing=True)}
    pushes = [{"id": "fill", "reason": "filled by hand", "region": WHOLE_PLANET, "pushes": [{"field": "gappy", "set": 5.0}]}]
    e = engine({"PartlyMissing": slot("PartlyMissing", ["gappy"])}, fields, pushes=pushes, max_rounds=3)
    w = e.build()
    assert np.all(w.fields["gappy"] == 5.0)                               # cell 0 had no value before the push
    view = MemoryView(w, e)
    assert "Before the push the cell had no value." in as_text(explain(view, 0, "gappy"))
    assert "Before the push the value was 5.00" in as_text(explain(view, 1, "gappy"))
    e = engine({}, pushes=[LIFT], keep_trio=True)
    w = e.build()
    w.drivers["a"]["from_b"] = np.full(w.n, np.nan)                       # a driver that holds nothing
    view = MemoryView(w, e)
    view.attrs["explanations"] = {"ToySource": {"a": {"says": "a is {value}:", "form": "sum",
                                                      "drivers": {"base": {"base": True, "says": "it starts from {v}"},
                                                                  "from_b": {"says": "b adds {v}"}}}}}
    text = as_text(explain(view, 3, "a"))
    assert "undefined" not in text and "nan" not in text.lower()


def test_no_answer_is_longer_than_its_limit_however_many_entries_one_step_adds():
    """The length was tested only when a new step began, so the entries that one step adds (its pushes, its ending)
    could carry an answer past the limit: 18 entries in a toy world, 17 without a closing entry on the planet."""
    pushes = [LIFT] + [{"id": f"more{k}", "region": WHOLE_PLANET, "pushes": [{"field": "a", "add": 0.0}]} for k in range(MAX_STEPS + 4)]
    e = engine({}, pushes=pushes, keep_trio=True)
    w = e.build()
    for field in ("a", "b", "kind_of_place"):
        chain = explain(MemoryView(w, e), 3, field)["chain"]
        assert len(chain) == MAX_STEPS + 1 and chain[-1].get("cut") and not any(entry.get("cut") for entry in chain[:-1])
        assert f"has reached {MAX_STEPS} entries" in chain[-1]["text"]


def test_a_fault_inside_an_answer_is_the_servers_fault_and_a_wrong_request_is_the_askers(tmp_path, monkeypatch):
    """An error of the kind ValueError raised inside a why answer came back as a wrong request (400)."""
    e = engine({}, pushes=[LIFT], keep_trio=True)
    w = e.build()
    srv, base = served(store.save(w, e, tmp_path / "w.zarr"))
    try:
        for url, code, said in (("/api/explain?cell=one&field=a", 400, "cell must be a whole number"),
                                ("/api/explain?field=a", 400, "the request needs cell"),
                                ("/api/explain?cell=1&field=nothing", 400, "no field named nothing"),
                                ("/api/explain?cell=99999&field=a", 400, "outside 0 to"),
                                ("/api/stats?name=nothing", 400, "no field named nothing"),
                                ("/api/field?name=a&month=x", 400, "month must be a whole number")):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + url)
            assert err.value.code == code and said in json.loads(err.value.read())["error"], url
        from worldengine import server

        def broken(view, cell, field):
            raise ValueError("a pattern asks for a format that does not exist")
        monkeypatch.setattr(server, "explain", broken)
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/api/explain?cell=1&field=a")
        assert err.value.code == 500 and "ValueError: a pattern asks for a format" in json.loads(err.value.read())["error"]
    finally:
        srv.shutdown()
