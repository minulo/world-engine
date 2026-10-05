"""The skeleton of the engine (build step 0): rounds, defaults, the contract, pushes, labels, groups, cause records."""
import copy
import os
import subprocess
import sys

import numpy as np
import pytest
import yaml

from conftest import ROOT, TOY
from worldengine import interventions as iv
from worldengine.causes import as_text, explain
from worldengine.engine import Engine, EngineError
from worldengine.mesh import get_mesh
from worldengine.params import ParameterError, Parameters
from worldengine.process import ContractError
from worldengine.store import MemoryView


def toy(**overrides):
    return Engine(TOY, profile="toy", overrides=overrides or None)


def toy_file(name):
    return yaml.safe_load((TOY / f"{name}.yaml").read_text(encoding="utf-8"))


def with_slot(name, cls, writes, keep=("ToySource", "ToyFollower", "ToyModifier")):
    m = toy_file("models")
    m["slots"] = {k: v for k, v in m["slots"].items() if k in keep}
    m["slots"][name] = {"implementation": f"toy_processes:{cls}", "writes": writes}
    return m


def test_three_toy_processes_reach_the_known_steady_answer():
    e = toy()
    assert e.order()["climate"] == ["ToySource", "Push[lift:a]", "ToyFollower", "ToyModifier"]
    w = e.build()
    assert w.settled["climate"] and not w.notices
    assert np.allclose(w.fields["a"], 7.0, atol=1e-5) and np.allclose(w.fields["b"], 8.0, atol=1e-5)
    assert set(w.fields["kind_of_place"]) == {1}


def test_first_round_reads_the_default_of_fields_yaml():
    p = toy_file("profiles")
    p["profiles"]["toy"]["climate"]["max_rounds"] = 1
    w = toy(profiles=p).build()
    # b defaults to 4, so round 1 gives a = 1 + 0.5 * 4, plus the push of 2; then b = a + 1
    assert np.array_equal(w.fields["a"], np.full(w.n, 5.0)) and np.array_equal(w.fields["b"], np.full(w.n, 6.0))
    assert {"kind": "climate_not_settled", "stage": "climate", "rounds": 1} in w.notices


def test_lagged_copy_is_a_blend():
    p = toy_file("profiles")
    p["profiles"]["toy"]["climate"]["max_rounds"] = 2
    w = toy(profiles=p).build()
    # after round 1 the copy of b is 4 + 0.5 * (6 - 4) = 5, so round 2 gives a = 1 + 0.5 * 5 + 2
    assert np.array_equal(w.fields["a"], np.full(w.n, 5.5))


def test_drivers_add_up_to_the_field_before_the_push():
    e = toy()
    w = e.build()
    total = w.drivers["a"]["base"].astype(np.float64) + w.drivers["a"]["from_b"]
    assert np.allclose(total, w.push_records["lift:a"]["before"], atol=1e-5)
    assert np.allclose(w.fields["a"] - w.push_records["lift:a"]["before"], 2.0)


def test_explain_names_the_push_and_the_loop():
    e = toy()
    w = e.build()
    ans = explain(MemoryView(w, e), 3, "a")
    text = as_text(ans)
    assert "entry lift" in text and "not physical" in text and "A test push" in text
    assert ans["chain"][0]["writer"] == "ToySource"


def test_second_run_is_identical():
    assert toy().build().fingerprint() == toy().build().fingerprint()


def test_fresh_interpreters_with_different_hash_seeds_agree():
    code = ("import sys; sys.path[:0] = [r'%s', r'%s']; from worldengine.engine import Engine; "
            "print(Engine(r'%s', profile='toy').build().fingerprint())" % (ROOT / "src", ROOT / "tests", TOY))
    prints = set()
    for seed in ("0", "4242"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed}, check=True)
        prints.add(out.stdout.strip())
    assert len(prints) == 1


@pytest.mark.parametrize("cls,message", [
    ("BadReader", "read a, which it did not declare"),
    ("BadWriter", "wrote a, which it did not declare"),
    ("Forgetful", "declared but did not write: c"),
])
def test_contract_is_enforced_at_once(cls, message):
    with pytest.raises(ContractError) as err:
        toy(models=with_slot("Extra", cls, ["c"])).build()
    assert message in str(err.value)


def test_unlisted_draw_is_refused():
    with pytest.raises(PermissionError) as err:
        toy(models=with_slot("Extra", "BadDraw", ["c"])).build()
    assert "seeds.yaml does not list" in str(err.value)


def test_asking_for_more_draws_leaves_the_earlier_ones_as_they_were():
    """Adding a plate must not move the plates already drawn; adding a wave must not change the waves already there."""
    from worldengine import draws
    from worldengine.library.noise import WAVE_NUMBERS, wave_field
    from worldengine.mesh import get_mesh
    key = (7, "Tectonics", "plate_centres", "start")
    assert np.array_equal(draws.sphere_points(*key, 14), draws.sphere_points(*key, 15)[:14])
    assert np.array_equal(draws.normal(*key, 5), draws.normal(*key, 9)[:5])
    assert np.array_equal(draws.uniform(*key, 5), draws.uniform(*key, 9)[:5])
    assert not np.array_equal(draws.uniform(*key, 5), draws.uniform(7, "Tectonics", "plate_axes", "start", 5))
    spread = draws.sphere_points(*key, 4000)
    assert np.abs(spread.mean(axis=0)).max() < 0.05 and abs((spread[:, 2] ** 2).mean() - 1 / 3) < 0.02      # even over the sphere
    bell = draws.normal(*key, 20000)
    assert abs(bell.mean()) < 0.03 and abs(bell.std() - 1) < 0.03
    # a wave field: wave k is made from row k of the numbers, so a longer list only adds waves
    xyz = get_mesh(2).xyz
    u = draws.uniform(*key, WAVE_NUMBERS * 6).reshape(6, WAVE_NUMBERS)
    one = wave_field(xyz, u[:1], (2.0, 5.0))
    again = wave_field(xyz, draws.uniform(*key, WAVE_NUMBERS * 9).reshape(9, WAVE_NUMBERS)[:1], (2.0, 5.0))
    assert np.array_equal(one, again)


def test_a_process_that_changes_its_answer_is_caught_by_the_cause_pass():
    with pytest.raises(EngineError) as err:
        toy(models=with_slot("Extra", "Unsteady", ["c"])).build()
    assert "must give the same output for the same input" in str(err.value)


def test_slot_must_write_its_list():
    m = toy_file("models")
    m["slots"]["ToySource"]["writes"] = ["a", "c"]
    with pytest.raises(ParameterError) as err:
        toy(models=m)
    assert "the slot must write" in str(err.value)


def test_unknown_field_name_is_refused_before_anything_runs():
    with pytest.raises(ParameterError) as err:
        toy(interventions=[{"id": "x", "region": {"circle": {"lat": 0, "lon": 0, "radius_km": 10}}, "pushes": [{"field": "nope", "set": 1.0}]}])
    assert "targets nope, which fields.yaml does not declare" in str(err.value)


def test_value_outside_its_valid_range_is_recorded_not_stopped():
    m = toy_file("models")
    m["slots"] = {"TooBig": {"implementation": "toy_processes:TooBig", "writes": ["a"]}}
    w = toy(models=m, interventions=[]).build()
    notice = [n for n in w.notices if n["kind"] == "field_outside_range"][0]
    assert notice["field"] == "a" and notice["highest"] == 500.0


def test_group_members_reach_the_reader_with_a_constant_push():
    m = with_slot("HeatMember", "HeatMember", ["heat_member"])
    m["slots"]["HeatReader"] = {"implementation": "toy_processes:HeatReader", "writes": ["c"]}
    pushes = toy_file("interventions") + [{"id": "sink", "region": {"circle": {"lat": 0, "lon": 0, "radius_km": 30000}},
                                           "pushes": [{"group": "toy_heat", "add": -1.0}]}]
    e = toy(models=m, interventions=pushes)
    w = e.build()
    import toy_processes
    assert toy_processes.HeatReader.last_members == ["heat_member", "push:sink:toy_heat"]
    assert np.allclose(w.fields["c"][0], 0.1 * 7.0 - 1.0, atol=1e-4)


def test_table_is_carried_from_the_start_step():
    e = toy(models=with_slot("TableKeeper", "TableKeeper", ["table:toy_items"]))
    w = e.build()
    assert list(w.tables["toy_items"]["value"]) == [1.0, 2.0, 3.0]


def test_a_place_label_alone_changes_no_other_field():
    plain = toy().build()
    label = {"id": "the_hill", "physical": False, "reason": "A named place",
             "region": {"circle": {"lat": 0.0, "lon": 0.0, "radius_km": 3000}, "where": {"field": "kind_of_place", "is_one_of": ["high"]}},
             "pushes": [{"field": "place_label", "set": "the_hill"}]}
    e = toy(interventions=toy_file("interventions") + [label])
    named = e.build()
    assert e.registry.fields["place_label"].categories == ("none", "the_hill")
    assert 0 < int((named.fields["place_label"] == 1).sum()) < named.n
    a, b = plain.fingerprints(), named.fingerprints()
    assert {k: v for k, v in a.items() if k != "place_label"} == {k: v for k, v in b.items() if k != "place_label"}
    assert named.rounds_used == plain.rounds_used
    order = e.plan.order["climate"]
    assert order.index("Push[the_hill:place_label]") > order.index("ToyFollower")


def test_label_must_hold_the_id_of_its_entry():
    bad = {"id": "x", "region": {"circle": {"lat": 0, "lon": 0, "radius_km": 10}}, "pushes": [{"field": "place_label", "set": "other"}]}
    with pytest.raises(ParameterError):
        toy(interventions=[bad])


# ---------------------------------------------------------------------------------------------- pushes, one by one
def test_push_operations_and_the_fading_edge():
    mesh = get_mesh(4)
    radius = 6.371e6
    region = iv.Region(circle={"lat": 0.0, "lon": 0.0, "radius_km": 2000}, outline=None, conditions=[], edge_km=1000)
    w = iv.region_weights(region, mesh, radius, None, True)
    d = np.arccos(np.clip(mesh.xyz[:, 0], -1, 1)) * radius
    assert np.all(w[d <= 2.0e6] == 1.0) and np.all(w[d >= 3.0e6] == 0.0)
    mid = (d > 2.2e6) & (d < 2.8e6)
    assert np.allclose(w[mid], 1.0 - (d[mid] - 2.0e6) / 1.0e6)
    bare = iv.region_weights(region, mesh, radius, None, False)
    assert set(np.unique(bare)) == {0.0, 1.0}
    old = np.full(mesh.n, 10.0)
    assert np.allclose(iv.apply_op("add", old, np.full(mesh.n, 5.0), w, "number"), 10 + 5 * w)
    assert np.allclose(iv.apply_op("scale", old, np.full(mesh.n, 2.0), w, "number"), 10 + 10 * w)
    assert np.allclose(iv.apply_op("set", old, np.full(mesh.n, 1.0), w, "number"), 10 - 9 * w)
    assert np.allclose(iv.apply_op("cap_max", old, np.full(mesh.n, 4.0), w, "number"), 10 - 6 * w)
    assert np.allclose(iv.apply_op("cap_min", old, np.full(mesh.n, 4.0), w, "number"), 10.0)
    monthly = iv.apply_op("add", np.zeros((12, mesh.n)), np.ones((12, mesh.n)), w, "number")
    assert monthly.shape == (12, mesh.n) and np.allclose(monthly[5], w)
    cats = iv.apply_op("set", np.zeros(mesh.n, dtype=np.int16), np.full(mesh.n, 3), bare, "category")
    assert set(np.unique(cats)) == {0, 3} and np.array_equal(cats == 3, bare == 1.0)
    wind = iv.apply_op("add", np.zeros((mesh.n, 3)), 2.0 * mesh.east, w, "direction")
    assert np.allclose(np.einsum("ij,ij->i", wind, mesh.east), 2.0 * w)


def test_outline_region():
    mesh = get_mesh(4)
    region = iv.Region(circle=None, outline=[[-20, -30], [-20, 30], [20, 30], [20, -30]], conditions=[], edge_km=0.0)
    w = iv.region_weights(region, mesh, 6.371e6, None, True)
    inside = (np.abs(mesh.lat) < 15) & (np.abs(mesh.lon) < 25)
    outside = (np.abs(mesh.lat) > 30) | (np.abs(mesh.lon) > 40)
    assert np.all(w[inside] == 1.0) and np.all(w[outside] == 0.0)


# ---------------------------------------------------------------------------------------------- parameter files
def test_number_written_as_text_is_refused_with_advice(tmp_path):
    for f in TOY.glob("*.yaml"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8").replace("star_output_w_m2: 1361.0", "star_output_w_m2: 1e3"), encoding="utf-8")
    with pytest.raises(ParameterError) as err:
        Parameters(tmp_path)
    assert "is text, not a number" in str(err.value) and "1.0e-5" in str(err.value)


def test_unknown_key_and_meaningless_value_are_refused(tmp_path):
    for f in TOY.glob("*.yaml"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8").replace("radius_m: 6.371e+6", "radius_m: 0.0\ncolour: blue"), encoding="utf-8")
    with pytest.raises(ParameterError) as err:
        Parameters(tmp_path)
    assert "radius_m: 0.0 must be above 0" in str(err.value) and "the key 'colour' is not allowed" in str(err.value)


def test_missing_file_is_named(tmp_path):
    with pytest.raises(ParameterError) as err:
        Parameters(tmp_path)
    assert "planet.yaml: the file is missing" in str(err.value)


def test_constant_given_per_mesh_level():
    m = toy_file("models")
    m["slots"]["ToySource"]["constants"] = {"gain": {"by_level": {2: 0.5, 7: 0.25}}}
    assert toy(models=m).constants["ToySource"]["gain"] == 0.5
    m["slots"]["ToySource"]["constants"] = {"gain": {"by_level": {7: 0.25}}}
    with pytest.raises(ParameterError):
        toy(models=m)
