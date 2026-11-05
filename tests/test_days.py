"""Build step 8: the weather of a day, computed on request, and the clock that steps through dates, with its run store.

The toy world: ToyRain draws each day's rain from the seed and the date; RainBarrel keeps 0.9 of yesterday's water and
catches the day's rain. Design, Layer 3: weather keeps no state, so a day is the same however it is reached; a stage
that steps through dates keeps its state in a run store beside the world, and a continued run equals one made in one go.
"""
import copy

import numpy as np
import pytest
import yaml

from conftest import TOY
from worldengine import store
from worldengine.engine import Engine, EngineError, engine_for_store
from worldengine.params import ParameterError
from worldengine.scheduler import Refused
from worldengine.store import StoreView

STAGES = [{"name": "setup", "clock": "once"}, {"name": "climate", "clock": "climate"},
          {"name": "weather", "clock": "weather"}, {"name": "barrel", "clock": "dated", "step": "day"}]
FIELDS = {"toy_rain": dict(family="Toy", unit="mm/day", shape="day_cell", kind="number", default=0.0),
          "barrel": dict(family="Toy", unit="mm", shape="cell", kind="number", dtype="float64", default=0.0),
          "herd": dict(family="Toy", unit="none", shape="cell", kind="number", default=0.0),
          "x": dict(family="Toy", unit="none", shape="cell", kind="number", default=0.0),
          "herd_breath": dict(family="Toy", unit="W/m2", shape="cell", kind="number", default=0.0)}


def toy(name):
    return yaml.safe_load((TOY / f"{name}.yaml").read_text(encoding="utf-8"))


def day_engine(slots=None, stages=None, step="day"):
    models = toy("models")
    models["slots"].update({"Rain": {"implementation": "toy_processes:ToyRain", "writes": ["toy_rain"]},
                            "Barrel": {"implementation": "toy_processes:RainBarrel", "writes": ["barrel"], "constants": {"keep": 0.9}}})
    models["slots"].update(slots or {})
    fields = toy("fields")
    fields["fields"].update(FIELDS)
    seeds = toy("seeds")
    seeds["draws"]["Rain"] = ["rain"]
    st = copy.deepcopy(stages or STAGES)
    for s in st:
        if s["clock"] == "dated":
            s["step"] = step
    return Engine(TOY, profile="toy", overrides={"models": models, "fields": fields, "seeds": seeds, "stages": {"stages": st}})


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    eng = day_engine()
    path = tmp_path_factory.mktemp("days") / "world.zarr"
    store.save(eng.build(), eng, path)
    return StoreView(path)


def test_the_barrel_on_day_400_is_the_same_reached_in_one_run_or_in_two_joined_at_a_saved_state(world, tmp_path):
    whole = day_engine().run_dated(world, tmp_path / "whole", last_day=400)["barrel"]
    day_engine().run_dated(world, tmp_path / "first", last_day=173)
    joined = day_engine().run_dated(world, tmp_path / "second", last_day=400, continue_from=tmp_path / "first")["barrel"]
    assert whole.tobytes() == joined.tobytes()
    assert whole.max() > 0                                      # it caught rain: the test does not pass on empty barrels
    kept = store.read_run(tmp_path / "second")
    assert (kept["first_day"], kept["day_reached"]) == (0, 400)
    assert kept["world"] == world.attrs["world_fingerprint"]


def test_the_barrel_follows_its_rule_day_by_day(world, tmp_path):
    eng = day_engine()
    before = eng.run_dated(world, tmp_path / "a", last_day=9)["barrel"].copy()
    rain = eng.day_weather(world, 10)["toy_rain"]
    after = day_engine().run_dated(world, tmp_path / "b", last_day=10, continue_from=tmp_path / "a")["barrel"]
    assert np.allclose(after, 0.9 * before + rain, rtol=0, atol=1e-12)


def test_a_day_of_weather_is_the_same_however_it_is_reached(world):
    eng = day_engine()
    first = eng.day_weather(world, 37)["toy_rain"].copy()
    other = eng.day_weather(world, 5)["toy_rain"].copy()
    again = day_engine().day_weather(world, 37)["toy_rain"]
    assert first.tobytes() == eng.day_weather(world, 37)["toy_rain"].tobytes() == again.tobytes()
    assert not np.array_equal(first, other)


def test_an_engine_made_from_a_store_computes_the_same_days(world):
    assert engine_for_store(world).day_weather(world, 12)["toy_rain"].tobytes() == day_engine().day_weather(world, 12)["toy_rain"].tobytes()


def test_a_world_store_holds_nothing_of_the_days(world):
    assert "toy_rain" not in world.field_names() and "barrel" not in world.field_names()


@pytest.mark.parametrize("ask,message", [
    (lambda e, w, p: e.run_dated(w, p / "r", last_day=3, continue_from=p / "first"), "the run has reached day 5; asked to stop at day 3"),
    (lambda e, w, p: e.run_dated(w, p / "first", last_day=9, continue_from=p / "first"), "a run store is written once"),
    (lambda e, w, p: e.day_weather(w, -1), "a day is a whole number from 0"),
    (lambda e, w, p: e.day_weather(w, 2.5), "a day is a whole number from 0"),
], ids=["stops before it starts", "writes over its own store", "a day before day 0", "half a day"])
def test_a_run_or_a_day_that_cannot_be_is_refused(world, tmp_path, ask, message):
    eng = day_engine()
    eng.run_dated(world, tmp_path / "first", last_day=5)
    with pytest.raises((EngineError, FileExistsError)) as err:
        ask(eng, world, tmp_path)
    assert message in str(err.value)


def test_a_run_continues_only_on_the_world_it_began_on(world, tmp_path):
    eng = day_engine()
    eng.run_dated(world, tmp_path / "first", last_day=5)
    other = day_engine(slots={"ToySource": {**toy("models")["slots"]["ToySource"], "constants": {"gain": 0.25}}})
    path = tmp_path / "other.zarr"
    store.save(other.build(), other, path)
    with pytest.raises(EngineError) as err:
        day_engine().run_dated(StoreView(path), tmp_path / "second", last_day=9, continue_from=tmp_path / "first")
    assert "belongs to another world" in str(err.value)


def test_a_stage_that_steps_by_a_month_is_refused_when_run_for_it_is_not_built(world, tmp_path):
    with pytest.raises(EngineError) as err:
        day_engine(slots={"Barrel": {"implementation": "toy_processes:ClimateReader", "writes": ["herd"]}},
                   step="month").run_dated(world, tmp_path / "r", last_day=3)
    assert "only a daily step is built" in str(err.value)


def test_a_world_without_a_weather_stage_has_no_days(tmp_path):
    eng = Engine(TOY, profile="toy")
    path = tmp_path / "plain.zarr"
    store.save(eng.build(), eng, path)
    with pytest.raises(EngineError) as err:
        eng.day_weather(StoreView(path), 3)
    assert "no weather stage" in str(err.value)
    with pytest.raises(EngineError) as err:
        eng.run_dated(StoreView(path), tmp_path / "r", last_day=3)
    assert "no stage that steps through dates" in str(err.value)


# check 11 of the design, made by the engine on loading: each misuse of a stage that steps through dates is refused
SWAP = {"Barrel": {"implementation": "toy_processes:RainBarrel", "writes": ["barrel"], "constants": {"keep": 0.9}}}
REFUSALS = [
    (dict(slots={"Herd": {"implementation": "toy_processes:RainReader", "writes": ["herd"]}}, step="month"),
     "the weather of one day, but its stage steps by a month"),
    (dict(slots={"Herd": {"implementation": "toy_processes:LaggedRainReader", "writes": ["herd"]}}),
     "a stage that steps through dates reads only the weather of the date it is at"),
    (dict(slots={"Reader": {"implementation": "toy_processes:BarrelReader", "writes": ["x"]}}),
     "a stage that steps through dates is a dead end"),
    (dict(slots={"Herd": {"implementation": "toy_processes:LaggedClimateReader", "writes": ["herd"]}}),
     "which does not step through dates; read it as it stands"),
    (dict(slots={"Herd": {"implementation": "toy_processes:BarrelHeat", "writes": ["herd_breath"]},
                 "Heat": {"implementation": "toy_processes:HeatReader", "writes": ["c"]}}),
     "which steps through dates and is a dead end"),
    (dict(stages=[STAGES[0], STAGES[1], STAGES[3], STAGES[2]]), "is listed before the weather stage, whose days it would read"),
]


@pytest.mark.parametrize("case,message", REFUSALS, ids=[m[:30] for _, m in REFUSALS])
def test_the_engine_refuses_each_misuse_of_a_stage_that_steps_through_dates(case, message):
    with pytest.raises(Refused) as err:
        day_engine(**case)
    assert message in str(err.value)


def test_a_step_that_is_not_a_day_a_month_or_a_year_is_refused():
    with pytest.raises((ParameterError, Refused)) as err:
        day_engine(step="week")
    assert "week" in str(err.value)
