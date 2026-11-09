"""Build step 8: the weather of a day, computed on request, and the clock that steps through dates, with its run store;
and why the weather of a day is as it is.

The toy world: ToyRain draws each day's rain from the seed and the date; RainBarrel keeps 0.9 of yesterday's water and
catches the day's rain. Design, Layer 3: weather keeps no state, so a day is the same however it is reached; a stage
that steps through dates keeps its state in a run store beside the world, and a continued run equals one made in one go.

The weather world: the real SynopticStorms and DailyWeather around a climate planted by hand (PlantedClimate), so that a
day takes a fraction of a second. When a day is recomputed on request its processes record their causes, and the "why"
answers of the day walk from them into the climate the day was drawn around (design: "weather causes when a day is
recomputed on request").
"""
import copy
import json

import numpy as np
import pytest
import yaml

from conftest import DATA, TOY
from worldengine import store
from worldengine.causes import as_text, explain
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


# ---------------------------------------------------------------------------------------------- why the weather of a day is so
CLIMATE = ["ocean_mask", "surface_temperature", "precipitation", "wind", "steering_wind", "sea_level_pressure",
           "daily_temperature_spread", "wet_day_fraction", "storm_track_density", "tc_genesis_potential", "potential_intensity"]
WEATHER = ("weather_temperature", "weather_precipitation", "weather_pressure", "weather_wind", "storm_influence")
DAYS = (40, 200, 275)                    # a northern winter, a northern summer with tropical cyclones, an autumn


def weather_engine(explanations=None):
    """The engine of the weather world, on mesh level 4 (2,562 cells); with `explanations`, those sentence patterns in
    place of the data's."""
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    models["slots"] = {k: models["slots"][k] for k in ("PlanetGeometry", "SynopticStorms", "DailyWeather")}
    models["slots"]["Climate"] = {"implementation": "toy_processes:PlantedClimate", "writes": CLIMATE}
    profiles = yaml.safe_load((DATA / "profiles.yaml").read_text(encoding="utf-8"))
    profiles["profiles"]["preview"]["mesh_level"] = 4
    overrides = {"models": models, "profiles": profiles, "interventions": []}
    if explanations is not None:
        overrides["explanations"] = explanations
    return Engine(DATA, profile="preview", overrides=overrides)


def save_weather_world(path, explanations=None):
    eng = weather_engine(explanations)
    store.save(eng.build(), eng, path)
    return StoreView(path)


@pytest.fixture(scope="module")
def weather_world(tmp_path_factory):
    return save_weather_world(tmp_path_factory.mktemp("weather") / "world.zarr")


def test_a_day_worked_out_with_its_causes_is_the_day_worked_out_without(weather_world):
    """The weather processes record their causes when a day is recomputed for a "why" answer, and only then. The record
    changes nothing the day holds, bit for bit, and the record of one day never stands beside another."""
    eng = engine_for_store(weather_world)
    for day in DAYS:
        plain = eng.day_weather(weather_world, day)
        plain = {k: (dict(v) if k.startswith("table:") else v) for k, v in plain.items()}
        assert not set(WEATHER) & set(eng.world.drivers)                    # no record without the asking
        view = eng.day_view(weather_world, day)
        held = view.values
        assert sorted(held) == sorted(plain) and sorted(view.day_fields()) == sorted(WEATHER)
        for k, v in plain.items():
            if k.startswith("table:"):
                assert sorted(v) == sorted(held[k]) and all(v[c].tobytes() == held[k][c].tobytes() for c in v), k
            else:
                assert v.tobytes() == held[k].tobytes(), k
        for slot in ("SynopticStorms", "DailyWeather"):
            for field, terms in eng.procs[slot].drivers.items():
                assert sorted(view.attrs["drivers"][field]) == sorted(terms)
                assert view.attrs["lineage"][field]["writer"] == slot and view.attrs["lineage"][field]["round"] == day
        assert "weather_temperature" not in weather_world.attrs["lineage"]   # the stored world is left as it was
    eng.day_weather(weather_world, 3)
    assert not set(WEATHER) & set(eng.world.drivers)


def test_the_drivers_of_a_day_add_up_to_its_fields_and_hold_the_rule_of_its_rain(weather_world):
    """Where a weather process calls a field a sum, its recorded terms add up to the field (the asides, numbers for the
    sentences, left out). The rain's record holds the rule the rain was made by: a wet day where the draw of the date
    fell below the chance of rain, the chance joining the month's wet days to the storms' chance, and a wet day's rain
    the day's mean over the chance of rain times the amount drawn. (The record is kept in 32 bits: a draw below the
    chance in 64 bits is at most equal to it in 32.)"""
    eng = engine_for_store(weather_world)
    patterns = weather_world.attrs["explanations"]
    for day in DAYS:
        view = eng.day_view(weather_world, day)
        for slot in ("SynopticStorms", "DailyWeather"):
            for field in eng.procs[slot].additive:
                aside = {t for t, how in patterns[slot][field]["drivers"].items() if (how or {}).get("aside")}
                terms = [np.asarray(view.driver(field, t)) for t in eng.procs[slot].drivers[field] if t not in aside]
                total = sum(a.astype(np.float64) for a in terms if a.dtype.kind == "f")
                value = view.field(field).astype(np.float64)
                assert np.allclose(total, value, rtol=0, atol=2e-5 * max(1.0, float(np.abs(value).max()))), (day, field)
        rec = {t: np.asarray(view.driver("weather_precipitation", t)) for t in eng.procs["DailyWeather"].drivers["weather_precipitation"]}
        rain = view.field("weather_precipitation").astype(np.float64)
        kind, month = rec["day_kind"], rec["month_rain_per_day"].astype(np.float64)
        wet, dry = kind == 1, kind == 0
        assert wet.any() and dry.any() and (kind == 2).any()                # wet days, dry days and the desert
        assert np.array_equal(wet, rain > 0) and np.array_equal(kind == 2, month <= 0)
        assert (rec["draw"][wet] <= rec["chance"][wet]).all() and (rec["draw"][dry] >= rec["chance"][dry]).all()
        share, storms = rec["wet_day_share"].astype(np.float64), rec["storm_chance"].astype(np.float64)
        assert np.allclose(rec["chance"], 1.0 - (1.0 - share) * (1.0 - storms), rtol=0, atol=1e-6)
        assert ((rec["likelier_by"] == 1) <= (storms >= share)).all() and ((rec["likelier_by"] == 0) <= (storms <= share)).all()
        assert (rec["likelier_by"] == 1).any() and (rec["likelier_by"] == 0).any()
        assert np.allclose(rain[wet], (month / rec["chance"] * rec["amount"])[wet], rtol=1e-5)


def test_a_days_answer_is_the_same_however_the_day_is_reached(weather_world):
    """Design, Layer 3: a day comes out the same however it is reached, and so do its "why" answers: asked alone of a
    fresh engine, of one built from the data rather than from the store, or after other days were worked out, with and
    without their causes. Another day has other answers, so the test does not pass on answers that ignore the day."""
    cells = range(0, weather_world.meta["cells"], 97)
    answers = lambda view: json.dumps([explain(view, c, f) for c in cells for f in WEATHER])
    alone = answers(engine_for_store(weather_world).day_view(weather_world, 200))
    assert answers(weather_engine().day_view(weather_world, 200)) == alone
    eng = engine_for_store(weather_world)
    eng.day_view(weather_world, 199)
    eng.day_weather(weather_world, 201)
    eng.day_view(weather_world, 40)
    assert answers(eng.day_view(weather_world, 200)) == alone
    assert answers(eng.day_view(weather_world, 201)) != alone


def test_a_days_answer_walks_back_into_the_climate_it_was_drawn_around(weather_world):
    """The answer for a field of a day starts at the day's own part, which it names however small beside the month's
    mean, and walks on from the record into the climate fields the day read: the remembered noise of the date ends at
    the seed, the spread and the month's temperature follow; the rain of a wet day that the storms made likely goes to
    the storm that passed; and the storm goes back to the cell its strongest one was born in, where the storm map made
    the birth likely."""
    view = engine_for_store(weather_world).day_view(weather_world, 200)
    rec = lambda field, term: np.asarray(view.driver(field, term))
    cell = int(np.argmax(np.abs(rec("weather_temperature", "departure"))))
    ans = explain(view, cell, "weather_temperature")
    assert ans["day"] == 200 and as_text(ans).startswith("Why is weather_temperature like this on day 200 at ")
    assert "the day's own departure changes it by" in ans["chain"][0]["text"]
    assert any(step.get("end") and "the remembered noise of a date" in step["text"] for step in ans["chain"])
    assert {"daily_temperature_spread", "surface_temperature"} <= {step["field"] for step in ans["chain"]}
    stormy = (rec("weather_precipitation", "day_kind") == 1) & (rec("weather_precipitation", "likelier_by") == 1)
    ans = explain(view, int(np.flatnonzero(stormy)[0]), "weather_precipitation")
    assert "It is a wet day" in ans["chain"][0]["text"] and ans["chain"][1]["field"] == "storm_influence"
    reached = rec("storm_influence", "reached") == 1
    for part, born_at, the_map in (("from_midlatitude_storms", "midlatitude_born_at", "storm_track_density"),
                                   ("from_tropical_cyclones", "tropical_born_at", "tc_genesis_potential")):
        cell = int(np.argmax(np.where(reached, rec("storm_influence", part), 0.0)))
        born = int(rec("storm_influence", born_at)[cell])
        chain = explain(view, cell, "storm_influence")["chain"]
        assert born >= 0 and "the strongest storm here is" in chain[0]["text"]
        assert any(step["field"] == the_map and step["cell"] == born for step in chain), (part, cell, born)
    warmth, mean = rec("weather_pressure", "from_warm_day"), rec("weather_pressure", "month_mean")
    small = np.flatnonzero((np.abs(warmth) < 0.002 * np.abs(mean)) & (warmth != 0))      # below what a sum names otherwise
    assert small.size and "the day's own warmth changes it by" in explain(view, int(small[0]), "weather_pressure")["chain"][0]["text"]
    quiet = int(np.flatnonzero(~reached)[0])
    assert "no storm of the day comes within twice its radius" in explain(view, quiet, "storm_influence")["chain"][0]["text"]


def test_a_field_of_a_day_is_explained_on_a_day_and_only_so(weather_world, capsys):
    """`explain --day N` answers for a field of a day; the field asked without a day, a field that is not of a day asked
    with one, and a day before the first are refused, in words that say what to ask instead."""
    from worldengine import cli
    with pytest.raises(KeyError) as err:
        explain(weather_world, 5, "weather_temperature")
    assert "is a field of a day, worked out on request: ask with a day" in str(err.value)
    path = str(weather_world.path)
    assert cli.main(["explain", path, "--cell", "5", "--field", "weather_precipitation", "--day", "200"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Why is weather_precipitation like this on day 200 at ") and "\n1. On day 200, " in out
    assert cli.main(["explain", path, "--lat", "50", "--lon", "10", "--field", "storm_influence", "--day", "40", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["day"] == 40
    for args, words in ((["--cell", "5", "--field", "weather_wind"], "is a field of a day, worked out on request: ask with --day N"),
                        (["--cell", "5", "--field", "surface_temperature", "--day", "3"], "is not a field of a day: ask for it without --day"),
                        (["--cell", "5", "--field", "weather_wind", "--day", "-1"], "a day is a whole number from 0"),
                        (["--cell", "99999", "--field", "weather_wind", "--day", "3"], "cell 99999 is outside 0 to 2561")):
        assert cli.main(["explain", path, *args]) == 2, args
        assert words in capsys.readouterr().err


def test_a_world_stored_before_the_weather_had_patterns_borrows_those_of_this_engine(weather_world, tmp_path):
    """A world stored before the weather processes had sentence patterns is answered with the patterns of this copy of
    the engine, wherever every driver they name is one its processes record; the answer says so."""
    patterns = yaml.safe_load((DATA / "explanations.yaml").read_text(encoding="utf-8"))
    for slot in ("SynopticStorms", "DailyWeather"):
        del patterns[slot]
    old = save_weather_world(tmp_path / "old.zarr", explanations=patterns)
    assert "DailyWeather" not in old.attrs["explanations"]
    then, now = (engine_for_store(v).day_view(v, 200) for v in (old, weather_world))
    for cell in (0, 777, 1500):
        for field in WEATHER:
            a, b = explain(then, cell, field), explain(now, cell, field)
            assert [step["text"] for step in a["chain"]] == [step["text"] for step in b["chain"]]
            assert any("stored before the weather had sentence patterns of its own" in n for n in a["notices"])
            assert not any("stored before the weather" in n for n in b["notices"])
