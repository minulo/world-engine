"""Build step 8: the weather of a day, computed on request, and the clock that steps through dates, with its run store.

The toy world: ToyRain draws each day's rain from the seed and the date; RainBarrel keeps 0.9 of yesterday's water and
catches the day's rain. Design, Layer 3: weather keeps no state, so a day is the same however it is reached; a stage
that steps through dates keeps its state in a run store beside the world, and a continued run equals one made in one go.
The last part tests stages that step by a month and by a year beside one that steps by a day (steps_engine).
"""
import copy
import math
import shutil

import numpy as np
import pytest
import yaml

from conftest import TOY
from worldengine import store
from worldengine.engine import Engine, EngineError, engine_for_store
from worldengine.library import days as dy
from worldengine.library.units import SECONDS_PER_DAY
from worldengine.params import ParameterError
from worldengine.scheduler import Refused
from worldengine.server import WorldService
from worldengine.store import StoreView
from worldengine.testing import Harness

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


def test_a_stage_that_steps_by_a_month_runs_once_a_month(world, tmp_path):
    """Until the dated steps were built this run was refused ("only a daily step is built")."""
    eng = steps_engine(order=("flock", "barrel"), barrel="toy_processes:RainBarrel")
    eng.run_dated(world, tmp_path / "r", last_day=100)
    kept = store.read_run(tmp_path / "r")
    log = kept["tables"]["toy_items"]
    assert log["item"].tolist() == [0, 1, 2, 3] and log["value"].tolist() == [31, 30, 31, 30]    # day 100 lies in month 3
    assert kept["steps"] == {"flock": {"step": "month", "reached": 3}, "barrel": {"step": "day", "reached": 100}}
    assert kept["fields"]["flock"].max() > 0


def test_the_server_gives_the_weather_of_a_day_and_refuses_a_day_or_a_field_it_cannot_give(world):
    """(tools/refusal_audit.py found these three refusals of the server reached by no test.)"""
    service = WorldService(world)
    want = np.ascontiguousarray(day_engine().day_weather(world, 12)["toy_rain"], dtype="<f4").tobytes()
    assert service.weather("toy_rain", 12) == want
    with pytest.raises(IndexError, match="day -1 is before the first day, 0"):
        service.weather("toy_rain", -1)
    with pytest.raises(KeyError, match="the weather of a day holds no field named barrel"):
        service.weather("barrel", 12)
    broken = StoreView(world.path)                               # read as a world whose parameters this code cannot take
    text = broken.attrs["parameters_text"]
    broken.attrs["parameters_text"] = {**text, "models": text["models"].replace("toy_processes:ToyRain", "toy_processes:NoSuchRain")}
    with pytest.raises(KeyError, match="the days of this world cannot be computed: ParameterError: models.yaml.slots.Rain"):
        WorldService(broken).weather("toy_rain", 3)


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


# ------------------------------------------------------------------------------------- steps of a month and a year
# A grove that steps by a year, a flock that steps by a month and the barrel, which steps by a day. The flock grows on
# the water it finds in the barrel, adds its warmth to a group and logs its steps in a table; the barrel loses what the
# flock adds to the group; the grove grows on the flock. So the toy holds every kind of state that a stage carries from
# step to step: fields, the copies read from the previous step, a table, a member of a group and the causes of a step.
STEPS = {"grove": "year", "flock": "month", "barrel": "day"}
STAGE_OF_SLOT = {"Barrel": "barrel", "Flock": "flock", "Grove": "grove"}
STEP_FIELDS = {name: dict(family="Toy", unit="none", shape="cell", kind="number", dtype="float64", default=0.0)
               for name in ("flock", "flock_saw", "flock_heat", "grove", "grove_days", "grove_year")}
DAYS_IN_YEAR = toy("planet")["year_length_s"] / SECONDS_PER_DAY  # 365.256 days, as in data/planet.yaml


def steps_engine(**kw):
    return Engine(TOY, profile="toy", overrides=steps_overrides(**kw))


def steps_overrides(order=("grove", "flock", "barrel"), steps=None, barrel="toy_processes:FlockBarrel", planet=None):
    """The toy data of an engine whose stages on the dated clock are those of `order`, listed in that order after the
    weather, each stepping as STEPS (or `steps`) says; `planet` changes entries of the toy planet."""
    models = toy("models")
    models["slots"].update({
        "Rain": {"implementation": "toy_processes:ToyRain", "writes": ["toy_rain"]},
        "Barrel": {"implementation": barrel, "writes": ["barrel"], "constants": {"keep": 0.9}},
        "Flock": {"implementation": "toy_processes:MonthlyFlock", "writes": ["flock", "flock_heat", "flock_saw", "table:toy_items"],
                  "constants": {"keep": 0.5, "share": 0.1, "jitter": 0.01, "heat": 0.001}},
        "Grove": {"implementation": "toy_processes:YearlyGrove", "writes": ["grove", "grove_days", "grove_year"],
                  "constants": {"keep": 0.9, "share": 0.2}}})
    models["slots"] = {s: c for s, c in models["slots"].items() if s not in STAGE_OF_SLOT or STAGE_OF_SLOT[s] in order}
    fields = toy("fields")
    fields["fields"].update(FIELDS)
    fields["fields"].update(STEP_FIELDS)
    seeds = toy("seeds")
    seeds["draws"].update({"Rain": ["rain"], "Flock": ["graze"]})
    stages = STAGES[:3] + [{"name": s, "clock": "dated", "step": (steps or STEPS)[s]} for s in order]
    overrides = {"models": models, "fields": fields, "seeds": seeds, "stages": {"stages": stages}}
    if planet:
        overrides["planet"] = {**toy("planet"), **planet}
    return overrides


def same_run(a, b):
    """Two run stores hold the same state, bit for bit: every field and copy, table column, member of a group and cause."""
    assert (a["steps"], a["day_reached"], a["calendar"]) == (b["steps"], b["day_reached"], b["calendar"])
    for key in ("fields", "lagged"):
        assert sorted(a[key]) == sorted(b[key]), key
        for name in a[key]:
            assert (a[key][name].dtype, a[key][name].tobytes()) == (b[key][name].dtype, b[key][name].tobytes()), (key, name)
    for key in store.RUN_NESTED:
        assert sorted(a[key]) == sorted(b[key]), key
        for name in a[key]:
            assert sorted(a[key][name]) == sorted(b[key][name]), (key, name)
            for part in a[key][name]:
                assert a[key][name][part].tobytes() == b[key][name][part].tobytes(), (key, name, part)


@pytest.mark.parametrize("order,barrel", [(("grove", "flock", "barrel"), "toy_processes:FlockBarrel"),
                                          (("barrel", "flock", "grove"), "toy_processes:RainBarrel")],
                         ids=["the longest step listed first", "the daily step listed first"])
def test_a_run_continued_inside_a_month_equals_one_long_run_bit_for_bit(world, tmp_path, order, barrel):
    """Days 0 to 800 in one run, or in four joined at day 173 (inside month 5, which began on day 153), day 400 (inside
    month 13 and year 1) and day 730 (the last day of year 1 and of month 23)."""
    make = lambda: steps_engine(order=order, barrel=barrel)
    make().run_dated(world, tmp_path / "whole", last_day=800)
    before = None
    for k, stop in enumerate((173, 400, 730, 800)):
        make().run_dated(world, tmp_path / f"part{k}", last_day=stop, continue_from=before)
        before = tmp_path / f"part{k}"
    whole, joined = store.read_run(tmp_path / "whole"), store.read_run(before)
    same_run(whole, joined)
    assert (joined["first_day"], joined["day_reached"]) == (0, 800)
    assert whole["steps"] == {"barrel": {"step": "day", "reached": 800}, "flock": {"step": "month", "reached": 26},
                              "grove": {"step": "year", "reached": 2}}
    for f in ("barrel", "flock", "flock_saw", "grove"):                # the test does not pass on empty state
        assert np.abs(whole["fields"][f]).max() > 0, f
    assert {g: list(m) for g, m in whole["group_now"].items()} == {"toy_heat": ["flock_heat"]}
    assert whole["tables"]["toy_items"]["item"].tolist() == list(range(27)) and "flock" in whole["drivers"]
    assert np.all(whole["fields"]["grove_year"] == 2.0)


def test_the_steps_follow_the_calendar_by_which_the_weather_of_a_day_mixes_the_months(world, tmp_path):
    """The flock steps on the first day of each month, and every day of a month is one that the weather of the day
    takes more of that month than of any other (library/days.py, month_weights). Twelve months make a year of whole
    days, which begins on the first day at or after a whole number of the planet's years; the grove steps on that day."""
    steps_engine().run_dated(world, tmp_path / "r", last_day=1095)
    kept = store.read_run(tmp_path / "r")
    log = kept["tables"]["toy_items"]
    lengths = log["value"].astype(int)
    assert log["item"].tolist() == list(range(36)) and set(lengths.tolist()) == {30, 31}
    starts = np.concatenate([[0], np.cumsum(lengths)[:-1]])
    planet = toy("planet")
    for month, (first, length) in enumerate(zip(starts, lengths)):
        for day in range(first, first + length):
            a, b, weight = dy.month_weights(day, planet, 12)
            nearer = (a,) if weight > 0.5 else (b,) if weight < 0.5 else (a, b)
            assert month % 12 in nearer, (day, month)
    years = [math.ceil(y * DAYS_IN_YEAR) for y in (1, 2, 3)]
    assert years == [366, 731, 1096]
    assert [starts[12], starts[24], starts[-1] + lengths[-1]] == years
    assert np.all(kept["fields"]["grove_days"] == 1096.0) and np.all(kept["fields"]["grove_year"] == 2.0)


def test_the_harness_hands_a_process_of_a_monthly_stage_the_days_of_its_step_as_the_engine_does(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(TOY, data)
    for stem, value in steps_overrides(order=("flock", "barrel"), barrel="toy_processes:RainBarrel").items():
        (data / f"{stem}.yaml").write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    h = Harness(level=2, data_dir=data)
    for month, days in ((0, 31), (1, 30), (8, 30), (11, 31), (12, 30)):      # month 12 is the first month of year 1
        log = h.run("Flock", round_no=month).tables["toy_items"]
        assert (log["item"].tolist(), log["value"].tolist()) == ([month], [float(days)])


def test_a_monthly_stage_listed_before_a_daily_one_steps_first_on_the_first_day_of_its_month(world, tmp_path):
    """The flock steps on day 153, the first day of month 5, before the barrel's step of that day: it finds the barrel
    of day 152, and the barrel of day 153 loses what the flock of month 5 adds to the group."""
    steps_engine().run_dated(world, tmp_path / "a", last_day=152)
    steps_engine().run_dated(world, tmp_path / "b", last_day=153, continue_from=tmp_path / "a")
    a, b = store.read_run(tmp_path / "a"), store.read_run(tmp_path / "b")
    assert b["fields"]["flock_saw"].tobytes() == a["fields"]["barrel"].tobytes()
    assert not np.array_equal(a["fields"]["flock"], b["fields"]["flock"])
    rain = steps_engine().day_weather(world, 153)["toy_rain"]
    drunk = b["group_now"]["toy_heat"]["flock_heat"]
    assert np.allclose(drunk, 0.001 * b["fields"]["flock"], rtol=0, atol=1e-15) and drunk.max() > 0
    assert np.allclose(b["fields"]["barrel"], 0.9 * a["fields"]["barrel"] + rain - drunk, rtol=0, atol=1e-12)


def test_a_monthly_stage_listed_after_a_daily_one_steps_after_it(world, tmp_path):
    """Listed after the barrel, the flock finds the barrel as it stands at the end of the first day of its month."""
    steps_engine(order=("barrel", "flock"), barrel="toy_processes:RainBarrel").run_dated(world, tmp_path / "a", last_day=153)
    steps_engine(order=("barrel", "flock"), barrel="toy_processes:RainBarrel").run_dated(world, tmp_path / "b", last_day=152)
    a, b = store.read_run(tmp_path / "a"), store.read_run(tmp_path / "b")
    assert a["fields"]["flock_saw"].tobytes() == a["fields"]["barrel"].tobytes()
    assert not np.array_equal(a["fields"]["barrel"], b["fields"]["barrel"])       # the barrel of day 153 is not that of 152


def test_a_run_that_makes_no_step_of_a_stage_keeps_its_state_and_the_causes_of_its_last_step(world, tmp_path):
    """Days 174 to 180 lie inside month 5 (days 153 to 182): the continued run makes no monthly step, and its store keeps
    the flock, its log and the causes of its step of day 153."""
    steps_engine().run_dated(world, tmp_path / "a", last_day=173)
    steps_engine().run_dated(world, tmp_path / "b", last_day=180, continue_from=tmp_path / "a")
    a, b = store.read_run(tmp_path / "a"), store.read_run(tmp_path / "b")
    assert b["steps"]["flock"] == {"step": "month", "reached": 5} and b["steps"]["barrel"]["reached"] == 180
    assert b["fields"]["flock"].tobytes() == a["fields"]["flock"].tobytes()
    assert b["tables"]["toy_items"]["item"].tolist() == list(range(6))
    assert not np.array_equal(a["fields"]["barrel"], b["fields"]["barrel"])
    assert sorted(b["drivers"]["flock"]) == ["grown", "kept"]
    for term in ("kept", "grown"):
        assert b["drivers"]["flock"][term].tobytes() == a["drivers"]["flock"][term].tobytes()
    causes = a["drivers"]["flock"]                                     # recorded in the step of day 153, the last one made
    assert np.allclose(causes["kept"].astype(np.float64) + causes["grown"], a["fields"]["flock"], rtol=1e-6, atol=0)


def test_a_run_starts_on_the_first_day_of_a_step_of_each_of_its_stages(world, tmp_path):
    make = lambda: steps_engine(order=("flock", "barrel"), barrel="toy_processes:RainBarrel")
    make().run_dated(world, tmp_path / "r", last_day=130, first_day=92)                 # month 3 begins on day 92
    kept = store.read_run(tmp_path / "r")
    assert kept["first_day"] == 92 and kept["tables"]["toy_items"]["item"].tolist() == [3, 4]
    with pytest.raises(EngineError) as err:
        make().run_dated(world, tmp_path / "s", last_day=130, first_day=100)
    assert ("a run starts on the first day of a step of each of its stages, but day 100 lies inside a month of stage flock, "
            "which began on day 92; the next begins on day 122") in str(err.value)
    with pytest.raises(EngineError) as err:
        steps_engine().run_dated(world, tmp_path / "t", last_day=500, first_day=396)       # month 13 begins, but not a year
    assert "day 396 lies inside a year of stage grove, which began on day 366; the next begins on day 731" in str(err.value)


ELSEWISE = [
    (dict(steps={**STEPS, "flock": "day"}), "the run store's stages step through dates as follows: stage barrel by a day, "
     "stage flock by a month, stage grove by a year; this engine's: stage barrel by a day, stage flock by a day, stage grove "
     "by a year. A run continues only with the stages and the steps it began with"),
    (dict(order=("flock", "barrel")), "this engine's: stage barrel by a day, stage flock by a month. A run continues only "
     "with the stages and the steps it began with"),
    (dict(planet={"year_length_s": 360 * SECONDS_PER_DAY}), "the run store's calendar has 365.25636574074076 days in a year and 12 "
     "months; this engine's has 360.0 days and 12 months. A run continues only on the calendar it began on"),
]


@pytest.mark.parametrize("other,said", ELSEWISE, ids=["another step", "another set of stages", "another calendar"])
def test_a_run_continues_only_with_the_stages_the_steps_and_the_calendar_it_began_with(world, tmp_path, other, said):
    steps_engine().run_dated(world, tmp_path / "first", last_day=40)
    with pytest.raises(EngineError) as err:
        steps_engine(**other).run_dated(world, tmp_path / "second", last_day=60, continue_from=tmp_path / "first")
    assert said in str(err.value)


def test_a_run_cannot_continue_from_a_run_store_that_is_not_there(world, tmp_path):
    with pytest.raises(FileNotFoundError) as err:
        steps_engine().run_dated(world, tmp_path / "second", last_day=60, continue_from=tmp_path / "nowhere")
    assert f"no run store at {tmp_path / 'nowhere'}" in str(err.value)
    assert not (tmp_path / "second").exists()


@pytest.mark.parametrize("year_s,said", [(6 * SECONDS_PER_DAY, "stage flock steps by a month, but a month of this planet lasts 0.5 days"),
                                         (0.5 * SECONDS_PER_DAY, "stage grove steps by a year, but a year of this planet lasts 0.5 days")],
                         ids=["a month", "a year"])
def test_a_step_shorter_than_a_day_is_refused(year_s, said):
    with pytest.raises(ParameterError) as err:
        steps_engine(planet={"year_length_s": year_s})
    assert said + "; a step must hold at least one whole day" in str(err.value)


@pytest.mark.parametrize("days", [dict(last_day=2.5), dict(last_day=10, first_day=-31)], ids=["half a day", "before day 0"])
def test_a_run_to_or_from_a_day_that_cannot_be_is_refused(world, tmp_path, days):
    with pytest.raises(EngineError) as err:
        steps_engine().run_dated(world, tmp_path / "r", **days)
    assert "a day is a whole number from 0, the first day of year 0" in str(err.value)
