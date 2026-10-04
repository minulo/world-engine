"""The scheduler computes the order the design document shows and makes every refusal it promises (build step 0)."""
import copy

import pytest

import design_declarations as D
from worldengine.scheduler import Refused, blank, schedule, visible


def run(procs, pushes=(), stages=None, clocks=None, labels=None, steps=None):
    return schedule(procs, list(pushes), stages=stages or D.STAGES, clocks=clocks or D.CLOCKS, groups=set(D.GROUPS),
                    tables=set(D.TABLES), labels=D.LABELS if labels is None else labels, kind=D.kind,
                    structural=D.structural, steps_of_dated=steps)


def base():
    return copy.deepcopy(D.P)


def order_of(plan):
    return {s: visible(o) for s, o in plan.order.items()}


def test_full_design_order():
    plan = run(base())
    assert order_of(plan) == D.DESIGN_ORDER
    assert plan.notes == []


def test_order_never_varies_with_dictionary_order():
    reversed_decls = dict(reversed(list(base().items())))
    assert order_of(run(reversed_decls)) == D.DESIGN_ORDER


def test_first_slice_order():
    names = ["PlanetGeometry", "Tectonics", "Isostasy", "SeaLevel", "Insolation", "Albedo", "EnergyBalance",
             "Circulation", "Moisture", "Biomes"]
    sl = {n: copy.deepcopy(D.P[n]) for n in names}
    sl["Tectonics"]["lagged"], sl["Tectonics"]["lagged_group"] = [], []
    sl["Albedo"]["lagged"] = ["surface_temperature"]
    sl["EnergyBalance"]["lagged"] = []
    sl["Moisture"]["reads"] = ["wind", "subsidence", "surface_temperature", "height_above_sea", "ocean_mask", "cell_area"]
    sl["Biomes"]["reads"] = ["surface_temperature", "precipitation", "ocean_mask"]
    plan = run(sl)
    assert order_of(plan) == {"setup": ["PlanetGeometry"], "geological": ["Tectonics", "Isostasy", "SeaLevel"],
                              "climate": ["Albedo", "Insolation", "EnergyBalance", "Circulation", "Moisture", "Biomes"],
                              "weather": []}
    assert any("surface_heat_flux has no members" in n for n in plan.notes)
    assert any("moisture_source has no members" in n for n in plan.notes)


def test_frozen_region_pushes_take_their_place():
    pushes = [{"id": "sink", "group": "surface_heat_flux", "op": "add"},
              {"id": "cap", "field": "surface_temperature", "op": "cap_max"},
              {"id": "day", "field": "weather_temperature", "op": "cap_max"}]
    plan = run(base(), pushes)
    climate = visible(plan.order["climate"])
    assert climate.index("Push[cap]") == climate.index("EnergyBalance") + 1
    assert climate.index("Push[cap]") < climate.index("Circulation")
    assert plan.constant_members == {"surface_heat_flux": ["sink"]}
    assert visible(plan.order["weather"])[-1] == "Push[day]"


def test_label_push_runs_after_its_condition():
    pushes = [{"id": "forest", "field": "place_label", "op": "set", "where": ["biome"]},
              {"id": "vapour", "group": "moisture_source", "op": "add", "where": ["biome"]}]
    plan = run(base(), pushes)
    climate = plan.order["climate"]
    assert climate.index("Push[forest]") > climate.index("Biomes")
    assert climate.index("Push[forest]") > climate.index("Default[place_label]")
    assert "Push[vapour]" in plan.members["moisture_source"]


def test_new_modifier_is_placed_by_priority():
    p = base()
    p["GlacialErosion"] = blank("geological", modifies=["elevation"], order=20, reads=["cell_area"])
    geo = visible(run(p).order["geological"])
    assert geo.index("FluvialErosion") < geo.index("GlacialErosion") < geo.index("SeaLevel")


def test_group_read_in_the_same_round_orders_the_reader_after_every_member():
    p = base()
    p["HeatReader"] = blank("climate", group_reads=["surface_heat_flux"], writes=["heat_total"])
    climate = visible(run(p).order["climate"])
    assert climate.index("OceanCurrents") < climate.index("HeatReader")


def test_dated_stage_is_ordered_after_the_weather():
    p = base()
    p["Herds"] = blank("herds", reads=["weather_precipitation"], lagged=["herd_density"], writes=["herd_density"])
    plan = run(p, stages=D.STAGES + ["herds"], clocks={**D.CLOCKS, "herds": "dated"}, steps={"herds": "day"})
    assert visible(plan.order["herds"]) == ["Herds"]


def test_deep_time_process_keeps_state_in_a_table():
    p = base()
    p["Evolution"] = blank("geological", reads=["table:crust_points"], lagged=["runoff_annual", "table:lineages"],
                           writes=["table:lineages"], start=True)
    tables = set(D.TABLES) | {"table:lineages"}
    plan = schedule(p, [], stages=D.STAGES, clocks=D.CLOCKS, groups=set(D.GROUPS), tables=tables, labels=D.LABELS,
                    kind=D.kind, structural=D.structural)
    assert "Evolution" in plan.order["geological"]


# ---------------------------------------------------------------------------------------------- refusals
def _two_writers(p): p["Extra"] = blank("climate", writes=["albedo"])
def _unknown_stage(p): p["Extra"] = blank("nowhere", writes=["x"])
def _undeclared_group(p): p["Extra"] = blank("climate", contributes={"no_such_group": "x"})
def _modifies_label(p): p["Extra"] = blank("climate", modifies=["place_label"], order=5)
def _writes_label(p): p["Extra"] = blank("climate", writes=["place_label"])
def _no_priority(p): p["Extra"] = blank("geological", modifies=["elevation"])
def _same_priority(p): p["Extra"] = blank("geological", modifies=["elevation"], order=10)
def _weather_lagged(p): p["DailyWeather"]["lagged"] = ["weather_temperature"]
def _reads_own(p): p["Extra"] = blank("climate", reads=["x"], writes=["x"])
def _group_now_and_adds(p): p["Extra"] = blank("climate", group_reads=["surface_heat_flux"], contributes={"surface_heat_flux": "x"})
def _geo_lagged_own(p): p["Isostasy"]["lagged"] = ["elevation"]
def _geo_lagged_other(p): p["Lithology"]["lagged"] = ["elevation"]
def _once_lagged(p): p["PlanetGeometry"]["lagged"] = ["cell_area"]
def _reads_and_modifies(p): p["Extra"] = blank("geological", reads=["elevation"], modifies=["elevation"], order=30)
def _reads_weather(p): p["Extra"] = blank("climate", reads=["weather_temperature"], writes=["x"])
def _reads_nothing(p): p["Extra"] = blank("climate", reads=["no_such_field"], writes=["x"])
def _reads_later(p): p["Isostasy"]["reads"].append("precipitation")
def _modifies_nothing(p): p["Extra"] = blank("climate", modifies=["no_such_field"], order=5)
def _modifies_other_stage(p): p["Extra"] = blank("climate", modifies=["elevation"], order=30)
def _lagged_nothing(p): p["Albedo"]["lagged"].append("snow_cover_misspelled")
def _reads_undeclared_group(p): p["Extra"] = blank("climate", lagged_group=["no_such_group"], writes=["x"])
def _group_now_member_later(p): p["Extra"] = blank("geological", group_reads=["surface_heat_flux"], writes=["x"])
def _weather_feeds_group(p): p["SynopticStorms"]["contributes"] = {"surface_heat_flux": "storm_heat"}
def _loop(p): p["Albedo"]["lagged"].remove("snow_ice_cover"); p["Albedo"]["reads"].append("snow_ice_cover")


REFUSALS = [
    (_two_writers, "two writers for albedo"),
    (_unknown_stage, "which the stage list does not contain"),
    (_undeclared_group, "adds to group no_such_group, which is not declared"),
    (_modifies_label, "a label field, which only a push may set"),
    (_writes_label, "a label field, which no process may write"),
    (_no_priority, "states no priority"),
    (_same_priority, "with the same priority 10"),
    (_weather_lagged, "which keeps no memory"),
    (_reads_own, "a process cannot read its own output of the same round"),
    (_group_now_and_adds, "reads group surface_heat_flux in the same round and also adds to it"),
    (_geo_lagged_own, "its own output, from the previous round"),
    (_geo_lagged_other, "the output of Isostasy, from the previous round"),
    (_once_lagged, "runs once and has no previous round"),
    (_reads_and_modifies, "under both reads and modifies"),
    (_reads_weather, "the weather stage stores nothing for another stage to read"),
    (_reads_nothing, "reads no_such_field, which nothing writes"),
    (_reads_later, "from a later stage without marking the read as lagged"),
    (_modifies_nothing, "modifies no_such_field, which nothing writes"),
    (_modifies_other_stage, "but elevation is written in stage geological"),
    (_lagged_nothing, "from the previous round, but nothing writes it"),
    (_reads_undeclared_group, "reads group no_such_group, which is not declared"),
    (_group_now_member_later, "the read must be marked as lagged"),
    (_weather_feeds_group, "in the weather stage, which stores nothing"),
    (_loop, "loop in stage climate"),
]


@pytest.mark.parametrize("change,message", REFUSALS, ids=[c.__name__.lstrip("_") for c, _ in REFUSALS])
def test_refusal(change, message):
    p = base()
    change(p)
    with pytest.raises(Refused) as e:
        run(p)
    assert message in str(e.value)


def test_loop_message_names_the_loop():
    p = base()
    _loop(p)
    with pytest.raises(Refused) as e:
        run(p)
    text = str(e.value)
    assert "Albedo" in text and "Cryosphere" in text and "->" in text


PUSH_REFUSALS = [
    ({"id": "x", "group": "no_such_group", "op": "add"}, "adds to group no_such_group, which is not declared"),
    ({"id": "x", "group": "surface_heat_flux", "op": "set"}, "only add is allowed on a group"),
    ({"id": "x", "group": "surface_heat_flux", "op": "add", "stage": "geological"}, "is used in stage climate"),
    ({"id": "x", "field": "table:plates", "op": "set"}, "tables cannot be pushed"),
    ({"id": "x", "field": "no_such_field", "op": "set"}, "which nothing writes"),
    ({"id": "x", "field": "cell_area", "op": "scale"}, "which cannot be pushed"),
    ({"id": "x", "field": "flow_receiver", "op": "set"}, "which cannot be pushed"),
    ({"id": "x", "field": "elevation", "op": "double"}, "which does not exist"),
    ({"id": "x", "field": "biome", "op": "add"}, "a field of kind category, which accepts only: set"),
    ({"id": "x", "field": "ocean_mask", "op": "scale"}, "a field of kind boolean, which accepts only: set"),
    ({"id": "x", "field": "wind", "op": "cap_max"}, "a field of kind direction"),
    ({"id": "x", "field": "elevation", "op": "add", "stage": "climate"}, "but elevation is written in stage geological"),
    ({"id": "x", "field": "albedo", "op": "set", "where": ["biome"]}, "loop in stage climate"),
    ({"id": "x", "field": "place_label", "op": "set", "where": ["weather_temperature"]}, "the weather stage stores nothing"),
]


@pytest.mark.parametrize("push,message", PUSH_REFUSALS, ids=[f"{p.get('field', p.get('group'))}-{p['op']}" for p, _ in PUSH_REFUSALS])
def test_push_refusal(push, message):
    with pytest.raises(Refused) as e:
        run(base(), [push])
    assert message in str(e.value)


def test_conditional_group_push_needs_a_stage():
    p = {"PlanetGeometry": copy.deepcopy(D.P["PlanetGeometry"])}
    with pytest.raises(Refused) as e:
        run(p, [{"id": "x", "group": "surface_heat_flux", "op": "add", "where": ["latitude"]}])
    assert "has no member and no reader to give it a stage" in str(e.value)


def test_a_loop_through_a_push_condition_is_broken_by_marking_it_lagged():
    plan = run(base(), [{"id": "x", "field": "albedo", "op": "set", "where_lagged": ["biome"]}])
    assert "Push[x]" in plan.order["climate"]


# ---------------------------------------------------------------------------------------------- clocks
def _dated(extra, step="day", stages=None, clocks=None):
    p = base()
    p.update(extra)
    st = stages or D.STAGES + ["herds"]
    return run(p, stages=st, clocks=clocks or {**D.CLOCKS, "herds": "dated"}, steps={"herds": step})


def test_unknown_clock_is_refused():
    with pytest.raises(Refused) as e:
        run(base(), clocks={**D.CLOCKS, "climate": "sundial"})
    assert "names the clock sundial, which does not exist" in str(e.value)


def test_label_field_with_unknown_stage_is_refused():
    with pytest.raises(Refused) as e:
        run(base(), labels={"place_label": "nowhere"})
    assert "label field place_label names stage nowhere" in str(e.value)


DATED_REFUSALS = [
    (dict(extra={"Herds": blank("herds", reads=["weather_precipitation"], writes=["herd_density"])}, step="month"),
     "the weather of one day, but its stage steps by a month"),
    (dict(extra={"Herds": blank("herds", lagged=["weather_precipitation"], writes=["herd_density"])}),
     "a stage that steps through dates reads only the weather of the date it is at"),
    (dict(extra={"Herds": blank("herds", writes=["herd_density"]), "Reader": blank("climate", lagged=["herd_density"], writes=["x"])}),
     "a stage that steps through dates is a dead end"),
    (dict(extra={"Herds": blank("herds", lagged=["biome"], writes=["herd_density"])}),
     "which does not step through dates; read it as it stands"),
    (dict(extra={"Herds": blank("herds", contributes={"moisture_source": "herd_breath"})}),
     "which steps through dates and is a dead end"),
    (dict(extra={"Herds": blank("herds", writes=["herd_density"])}, step="week"), "a step is a day, a month or a year"),
    (dict(extra={"Herds": blank("herds", writes=["herd_density"])}, stages=["setup", "geological", "climate", "herds", "weather"]),
     "is listed before the weather stage, whose days it would read"),
]


@pytest.mark.parametrize("case,message", DATED_REFUSALS, ids=[m[:28] for _, m in DATED_REFUSALS])
def test_dated_stage_refusal(case, message):
    with pytest.raises(Refused) as e:
        _dated(**case)
    assert message in str(e.value)


def test_dated_stage_missing_from_the_stage_list_is_refused():
    with pytest.raises(Refused) as e:
        run(base(), clocks={**D.CLOCKS, "herds": "dated"})
    assert "the stage list does not contain it" in str(e.value)
