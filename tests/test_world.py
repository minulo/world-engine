"""The slice as a whole, on the preview mesh (build step 1): terrain -> temperature -> wind -> rainfall -> biomes.

Each test states a pass condition that was fixed before the run it judges (design, Layer 9): a sign, a direction
or a latitude band. No test here compares with data measured on Earth; those tests wait for the reference data.
"""
import json
import os
import subprocess
import sys
import threading
import urllib.request

import numpy as np
import pytest
import yaml

from conftest import DATA, ROOT
from worldengine import store
from worldengine.causes import as_text, explain
from worldengine.engine import Engine
from worldengine.library import operators as op
from worldengine.server import make_server

NORTH_POLE, SOUTH_POLE = 0, 11          # the mesh has a cell at each pole


def build(**overrides):
    e = Engine(DATA, profile="preview", overrides=overrides or None)
    return e, e.build()


def example(name):
    return yaml.safe_load((DATA / "examples" / name).read_text())


@pytest.fixture(scope="module")
def plain():
    return build()


@pytest.fixture(scope="module")
def frozen():
    return build(interventions=example("frozen_region.yaml"))


def cell_at(mesh, lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return int(np.argmax(mesh.xyz @ np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])))


# ---------------------------------------------------------------------------------------------- the order and the run
def test_the_slice_runs_in_the_computed_order_and_settles(plain):
    e, w = plain
    assert e.order() == {"setup": ["PlanetGeometry"], "geological": ["Tectonics", "Isostasy", "SeaLevel"],
                         "climate": ["Albedo", "Insolation", "EnergyBalance", "Circulation", "Moisture", "Biomes"], "weather": []}
    assert w.settled["climate"] and w.rounds_used["climate"] < e.profile["climate"]["max_rounds"]
    assert w.notices == []                                  # nothing left its valid range, no solver stopped at its cap
    assert any("surface_heat_flux has no members" in n for n in e.plan.notes)


# ---------------------------------------------------------------------------------------------- cold poles
def test_both_poles_are_cold_and_carry_ice(plain):
    """The requirement added when the design was approved. Nothing places the cold: at a tilt of 23.44 degrees each
    pole gets 41 % of the equator's yearly sunlight, and the energy balance does the rest."""
    e, w = plain
    f, m = w.fields, w.mesh
    t = f["surface_temperature"].astype(np.float64)
    yearly = t.mean(axis=0)
    equator = np.abs(m.lat) < 5
    equator_mean = (yearly[equator] * m.area[equator]).sum() / m.area[equator].sum()
    for pole in (NORTH_POLE, SOUTH_POLE):
        assert yearly[pole] < 273.15                         # below freezing in the yearly mean
        assert yearly[pole] < equator_mean - 30.0            # and far colder than the equator
        assert w.drivers["albedo"]["from_snow_and_ice"][:, pole].min() > 0.0      # the Albedo slice marks ice there
        assert e.registry.fields["biome"].categories[f["biome"][pole]] == "ice"
    insolation = f["insolation"].astype(np.float64).mean(axis=0)
    ratio = insolation[NORTH_POLE] / insolation[equator].mean()
    assert abs(ratio - 0.415) < 0.01                         # the cause: 41 % of the equator's yearly sunlight
    lat, zonal = op.zonal_mean(m, yearly, 10.0)
    assert abs(lat[np.argmin(zonal)]) > 75 and abs(lat[np.argmax(zonal)]) < 25    # coldest at a pole, warmest in the tropics
    assert np.all(np.diff(zonal[lat > 20]) < 0) and np.all(np.diff(zonal[lat < -20]) > 0)   # colder toward each pole


def _mean_temperature_c(w):
    area = w.fields["cell_area"]
    return float((w.fields["surface_temperature"].astype(np.float64).mean(axis=0) * area).sum() / area.sum()) - 273.15


def _deep_ice_age_notes(w):
    return [n for n in w.notices if n["kind"] == "process_note" and n["slot"] == "Albedo"]


def test_a_seeded_world_that_froze_over_under_the_earlier_snow_rule_now_stays_open():
    """Seed 10 was the one world in 32 that froze over in the second review: -5.4 C, 98.5 % of its land frozen all
    year, reported as an ordinary settled world. Snow then lay on any land below freezing, snowfall or none. Now snow
    must fall before it lies. The world is still a cold one, with much of its land near the poles (measured: 9 C)."""
    w = Engine(DATA, profile="preview", seed=10).build()
    assert w.settled["climate"]
    assert _mean_temperature_c(w) > 5.0
    assert not _deep_ice_age_notes(w)
    for pole in (NORTH_POLE, SOUTH_POLE):
        assert w.fields["surface_temperature"].astype(np.float64).mean(axis=0)[pole] < 273.15       # and its poles are still cold


def test_less_sunlight_cools_the_default_planet_and_a_deep_ice_age_is_reported(plain):
    """Two per cent less sunlight froze the default planet in the second review (-5.3 C). Now it cools it by about
    4 K. With five per cent less, snow and ice do take over, as they do in every model of this kind, and the world
    then says so in a note."""
    _, w0 = plain

    def dimmer(factor):
        planet = yaml.safe_load((DATA / "planet.yaml").read_text())
        planet["star_output_w_m2"] *= factor
        return build(planet=planet)[1]
    w = dimmer(0.98)
    assert w.settled["climate"] and not _deep_ice_age_notes(w)
    cooling = _mean_temperature_c(w0) - _mean_temperature_c(w)
    assert 2.0 < cooling < 7.0                                            # measured 4.2 K
    assert _mean_temperature_c(w) > 4.0
    cold = dimmer(0.95)
    notes = _deep_ice_age_notes(cold)
    assert len(notes) == 1 and "deep ice age" in notes[0]["what"] and notes[0]["share_covered"] > 1 / 3
    assert _mean_temperature_c(cold) < 0.0


def test_a_tilt_above_54_degrees_is_allowed_and_reported():
    planet = yaml.safe_load((DATA / "planet.yaml").read_text())
    planet["axial_tilt_deg"] = 60.0
    models = yaml.safe_load((DATA / "models.yaml").read_text())
    models["slots"] = {k: models["slots"][k] for k in ("PlanetGeometry", "Tectonics", "Isostasy", "SeaLevel", "Insolation",
                                                       "Albedo", "EnergyBalance", "Circulation", "Moisture")}
    e, w = build(planet=planet, models=models)
    assert {"kind": "model_outside_range", "slot": "EnergyBalance", "parameter": "axial_tilt_deg", "value": 60.0,
            "expected": [0.0, 54.0]} in w.notices
    q = w.fields["insolation"].astype(np.float64).mean(axis=0)
    assert q[NORTH_POLE] > q[np.abs(w.mesh.lat) < 5].mean()  # the sunlight model then favours the poles; the engine does not hide it


# ---------------------------------------------------------------------------------------------- wind and rain
def test_trade_winds_and_westerlies(plain):
    _, w = plain
    m = w.mesh
    east, north = op.to_east_north(m, w.fields["wind"].astype(np.float64).mean(axis=0))
    lat, u = op.zonal_mean(m, east, 10.0)
    _, v = op.zonal_mean(m, north, 10.0)
    for sign in (1, -1):
        trades = (sign * lat > 5) & (sign * lat < 25)
        assert np.all(u[trades] < -1.0)                       # from the east in the tropics
        assert np.all(sign * v[trades] < 0)                   # and toward the equator
        assert np.all(u[(sign * lat > 40) & (sign * lat < 55)] > 1.0)   # from the west in mid-latitudes
    p = w.fields["sea_level_pressure"].astype(np.float64).mean(axis=0)
    lat5, zonal = op.zonal_mean(m, p, 5.0)
    for sign in (1, -1):
        side = sign * lat5 > 0
        assert 20 <= sign * lat5[side][np.argmax(zonal[side])] <= 40      # high pressure near 30 degrees


def test_the_driest_land_band_lies_between_15_and_40_degrees(plain):
    """Deserts near 30 degrees north and south: between the equator and 60 degrees in each hemisphere, yearly rain
    over land, averaged around each latitude, is lowest between 15 and 40 degrees."""
    _, w = plain
    m, f = w.mesh, w.fields
    yearly = f["precipitation"].astype(np.float64).sum(axis=0)
    lat, land_rain = op.zonal_mean(m, yearly, 5.0, mask=(~f["ocean_mask"]).astype(np.float64))
    for sign in (1, -1):
        side = (sign * lat > 0) & (sign * lat < 60) & ~np.isnan(land_rain)
        driest = sign * lat[side][np.argmin(land_rain[side])]
        assert 15 <= driest <= 40
    _, all_rain = op.zonal_mean(m, yearly, 5.0)
    assert abs(lat[np.argmax(all_rain)]) < 10                 # the rain belt lies near the equator


def test_water_that_evaporates_equals_water_that_falls(plain):
    _, w = plain
    f = w.fields
    e = (f["ocean_evaporation"].astype(np.float64) * f["cell_area"]).sum()
    p = (f["precipitation"].astype(np.float64) * f["cell_area"]).sum()
    assert abs(e / p - 1) < 1e-3
    assert np.all(f["snowfall"] <= f["precipitation"])


def test_the_sea_holds_the_planets_water_and_land_is_a_minor_share(plain):
    e, w = plain
    f = w.fields
    volume = (f["sea_depth"].astype(np.float64) * f["cell_area"]).sum()
    assert abs(volume / e.planet["surface_water_volume_m3"] - 1) < 1e-4
    land = ((~f["ocean_mask"]) * f["cell_area"]).sum() / f["cell_area"].sum()
    assert 0.15 < land < 0.45
    assert abs(w.tables["seas"]["volume_m3"].sum() / e.planet["surface_water_volume_m3"] - 1) < 1e-9


def test_mountains_sit_on_plate_edges_where_plates_close(plain):
    e, w = plain
    f = w.fields
    high = f["height_above_sea"] > 3000.0
    assert high.sum() > 10
    assert np.all(f["convergence_rate"][high] > 0)            # every high cell lies beside a closing boundary
    assert np.median(f["boundary_distance"][high]) < 1.0e6    # and within about a thousand kilometres of it


# ---------------------------------------------------------------------------------------------- cause records
def test_drivers_add_up_to_the_stored_field(plain):
    e, w = plain
    for name, proc in e.procs.items():
        for field in proc.additive:
            d = w.drivers[field]
            total = sum(v.astype(np.float64) for k, v in d.items() if v.dtype.kind == "f")
            value = w.fields[field].astype(np.float64)
            scale = max(1.0, float(np.nanmax(np.abs(value))))
            assert np.allclose(total, value, atol=2e-5 * scale), f"{name}: the drivers of {field} do not add up"


def test_explain_returns_a_chain_that_ends_at_a_seed_or_a_parameter(plain):
    e, w = plain
    view = store.MemoryView(w, e)
    names = e.registry.fields["biome"].categories
    land = np.flatnonzero(~w.fields["ocean_mask"])
    cell = int(land[len(land) // 2])
    ans = explain(view, cell, "biome")
    text = as_text(ans)
    assert ans["chain"][0]["value"] == names[w.fields["biome"][cell]].replace("_", " ")
    assert len(ans["chain"]) >= 4
    assert any(step.get("end") for step in ans["chain"])
    assert "planet parameters" in text or "seeded starting condition" in text
    mountain = int(np.argmax(w.fields["height_above_sea"]))
    text = as_text(explain(view, mountain, "height_above_sea"))
    assert "plates closing nearby have thickened it" in text and "seeded starting condition" in text
    for field in view.field_names():                         # every stored field answers, whatever its kind
        assert explain(view, cell, field)["chain"]


def test_a_why_answer_never_points_to_a_step_about_another_cell(plain):
    """A walk that follows the vapour to the cell it came from reaches the same field at another cell. "See step N"
    used to send the reader to that other cell's step: 74 of 194 sampled answers for precipitation did so."""
    e, w = plain
    view = store.MemoryView(w, e)
    seen_reference = seen_other_cell = 0
    for cell in range(0, w.n, 53):
        ans = explain(view, cell, "precipitation")
        chain = ans["chain"]
        seen_other_cell += any(step["cell"] != cell for step in chain)
        for step in chain:
            if "see step" in step["text"] or "explained in step" in step["text"]:
                seen_reference += 1
                number = int(step["text"].split("step ")[-1].split(":")[0].rstrip("."))
                target = chain[number - 1]
                assert (target["field"], target["cell"]) == (step["field"], step["cell"])
            if step["cell"] != cell and "writer" in step:
                assert step["text"].startswith("At ")                # a step about another cell says which cell
    assert seen_other_cell > 20                                      # the test has something to see


def test_no_why_answer_on_the_planet_runs_past_its_limit_or_stumbles_over_its_words(plain):
    """Third check: the answer for ocean_evaporation in cell 7650 had 17 entries and no entry that said where it
    stopped; the sentence for snowfall said "of water of water"."""
    from worldengine.causes import MAX_STEPS
    e, w = plain
    view = store.MemoryView(w, e)
    longest = 0
    for cell in list(range(0, w.n, 499)) + [7650]:
        for field in view.field_names():
            chain = explain(view, cell, field)["chain"]
            longest = max(longest, len(chain))
            assert len(chain) <= MAX_STEPS + 1 and (len(chain) <= MAX_STEPS or chain[-1].get("cut")), (cell, field)
            text = " ".join(step["text"] for step in chain)
            assert "undefined" not in text and "of water of water" not in text, (cell, field)
    assert longest == MAX_STEPS + 1                                  # the test has something to see


def test_the_sea_cell_answer_leads_to_why_it_is_sea_and_a_mountain_names_its_event(plain):
    e, w = plain
    view = store.MemoryView(w, e)
    sea = int(np.flatnonzero(w.fields["ocean_mask"] & (np.abs(w.mesh.lat) < 30))[0])
    text = as_text(explain(view, sea, "biome"))
    assert "the cell is sea" in text and "undefined" not in text and "Under water here: true" in text
    mountain = int(np.argmax(w.drivers["crust_thickness"]["thickened_by_plates"]))
    text = as_text(explain(view, mountain, "crust_thickness"))
    row = int(w.drivers["crust_thickness"]["event"][mountain])
    events = w.tables["tectonic_events"]
    assert row >= 0 and f"between plates {events['plate_a'][row]} and {events['plate_b'][row]}" in text
    assert ("a collision of continents" in text) == (events["kind"][row] == 2)


def test_no_column_of_air_holds_far_more_vapour_than_it_can_and_no_cell_rains_without_limit(plain):
    """Before the review, vapour mixed into the thin cold columns over high ground: up to 3 times saturation, 72 m of
    rain a year in one cell, and 43 % of all rain over land on 4 % of the land."""
    from worldengine.processes.moisture_one_layer import saturation_vapour_density
    e, w = plain
    f = w.fields
    c = e.constants["Moisture"]
    holds = saturation_vapour_density(f["surface_temperature"].astype(np.float64), c["saturation"]) * c["vapour_scale_height_m"]
    humidity = f["column_water"].astype(np.float64) / holds
    assert humidity.max() < 1.0
    yearly = f["precipitation"].astype(np.float64).sum(axis=0)
    assert yearly.max() < 8000.0                                     # measured 5.4 m, under the rain belt at sea; Earth's wettest places get about 12 m
    assert yearly[~f["ocean_mask"]].max() < 6000.0                   # on land 3.7 m, where the trade winds meet a coast 4 km high
    lifted = w.drivers["precipitation"]["from_rising_ground"].astype(np.float64).sum(axis=0)
    assert lifted[f["height_above_sea"] <= 0].max() == 0.0           # the rain of rising ground falls on rising ground, never on the sea
    land = ~f["ocean_mask"]
    area = f["cell_area"]
    high = land & (f["height_above_sea"] > 2000.0)
    share_of_rain = (yearly * area)[high].sum() / (yearly * area)[land].sum()
    share_of_land = area[high].sum() / area[land].sum()
    assert high.sum() > 20 and share_of_rain < 4 * share_of_land     # high ground is wetter, but it does not hold the land's rain


# ---------------------------------------------------------------------------------------------- pushes
def test_the_frozen_region_example_works_in_reduced_form(plain, frozen):
    e0, w0 = plain
    e, w = frozen
    assert e.order()["climate"] == ["Albedo", "Insolation", "EnergyBalance", "Push[ever_winter:surface_temperature]",
                                    "Circulation", "Moisture", "Biomes"]
    assert e.plan.constant_members == {"surface_heat_flux": ["ever_winter:surface_heat_flux"]}
    m = w.mesh
    centre = cell_at(m, 48.0, -20.0)
    d = np.arccos(np.clip(m.xyz @ m.xyz[centre], -1, 1)) * 6371.0
    inside, far = d < 550.0, d > 3000.0
    t, t0 = w.fields["surface_temperature"].astype(np.float64), w0.fields["surface_temperature"].astype(np.float64)
    assert t[:, inside].max() <= 258.15 + 1e-3                # the cap guarantees the freeze in every month
    assert t0[:, inside].max() > 273.15                       # which the plain world does not have
    before = w.push_records["ever_winter:surface_temperature"]["before"].astype(np.float64)
    assert (before[:, inside] < t0[:, inside]).all()          # the heat sink alone already cools the region
    ring = (d > 900.0) & (d < 1500.0)
    assert (t.mean(axis=0)[ring] < t0.mean(axis=0)[ring]).all()            # and a faint chill reaches beyond the edge
    assert np.abs(t.mean(axis=0)[far] - t0.mean(axis=0)[far]).max() < np.abs(t.mean(axis=0)[inside] - t0.mean(axis=0)[inside]).min()
    names = e.registry.fields["biome"].categories
    assert set(names[b] for b in w.fields["biome"][inside]) == {"ice"}     # an unchanged process reacts: the biome is ice
    # fields of the geological stage are untouched
    for name in ("elevation", "ocean_mask", "crust_thickness", "plate_id"):
        assert np.array_equal(w.fields[name], w0.fields[name])
    text = as_text(explain(store.MemoryView(w, e), centre, "surface_temperature"))
    assert "entry ever_winter (The Ever-Winter)" in text and "not physical" in text
    assert "the push ever_winter:surface_heat_flux -120.0" in text and "Before the push the value was" in text


def test_a_place_label_alone_changes_no_other_field(plain):
    e0, w0 = plain
    e, w = build(interventions=example("place_label.yaml"))
    assert e.registry.fields["place_label"].categories == ("none", "whispering_forest")
    labelled = w.fields["place_label"] == 1
    names = e.registry.fields["biome"].categories
    forests = {"temperate_seasonal_forest", "temperate_rainforest", "boreal_forest"}
    assert labelled.sum() > 50                               # the example's circle lies where forest grows in the default world
    assert set(names[b] for b in w.fields["biome"][labelled]) <= forests       # the entry places no forest: it names what grew
    assert not [n for n in w.notices if n["kind"] == "push_touched_nothing"]
    centre = w.mesh.xyz[cell_at(w.mesh, -50.0, 105.0)]
    assert (np.arccos(np.clip(w.mesh.xyz[labelled] @ centre, -1, 1)) * 6371.0).max() < 1500.0 + 250.0     # inside the circle
    moved = example("place_label.yaml")
    moved[0]["region"]["circle"] = {"lat": 45.0, "lon": 10.0, "radius_km": 1500}       # no forest grows there in this world
    _, empty = build(interventions=moved)
    assert not (empty.fields["place_label"] == 1).any()
    assert {"kind": "push_touched_nothing", "push": "whispering_forest:place_label"} in empty.notices
    a, b = w0.fingerprints(), w.fingerprints()
    assert {k: v for k, v in a.items() if k != "place_label"} == {k: v for k, v in b.items() if k != "place_label"}
    assert w.rounds_used == w0.rounds_used
    order = e.plan.order["climate"]
    assert order.index("Push[whispering_forest:place_label]") > order.index("Biomes")
    assert w.lineage["place_label"]["pushes"] == ["whispering_forest:place_label"]


# ---------------------------------------------------------------------------------------------- repeatability
def test_the_preview_world_is_identical_in_two_fresh_interpreters_with_different_hash_seeds(plain):
    _, w = plain
    code = ("import sys, json; sys.path.insert(0, r'%s'); from worldengine.engine import Engine; "
            "print(json.dumps(Engine(r'%s', profile='preview').build().fingerprints()))" % (ROOT / "src", DATA))
    prints = []
    for seed in ("1", "987654"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed}, check=True)
        prints.append(json.loads(out.stdout.strip().splitlines()[-1]))
    assert prints[0] == prints[1] == w.fingerprints()


def test_another_seed_gives_another_world_with_the_same_patterns():
    e, w = Engine(DATA, profile="preview", seed=7), None
    w = e.build()
    f, m = w.fields, w.mesh
    yearly = f["surface_temperature"].astype(np.float64).mean(axis=0)
    assert yearly[NORTH_POLE] < 273.15 and yearly[SOUTH_POLE] < 273.15
    assert w.settled["climate"]
    default = Engine(DATA, profile="preview").build()
    assert not np.array_equal(default.fields["plate_id"], f["plate_id"])


# ---------------------------------------------------------------------------------------------- store, server, viewer
def test_the_world_store_round_trips_and_the_server_answers_for_every_kind_of_field(plain, tmp_path):
    e, w = plain
    path = tmp_path / "slice.zarr"
    store.save(w, e, path)
    view = store.StoreView(path)
    assert view.fingerprints() == {k: v for k, v in w.fingerprints().items() if not k.startswith("table:")}
    assert np.array_equal(view.table("seas")["surface_m"], w.tables["seas"]["surface_m"])
    assert view.attrs["meta"]["settled"] == {"climate": True}
    cell = cell_at(w.mesh, 10.0, 30.0)
    assert as_text(explain(view, cell, "precipitation")) == as_text(explain(store.MemoryView(w, e), cell, "precipitation"))
    srv = make_server(path, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    get = lambda q: urllib.request.urlopen(base + q).read()
    world = json.loads(get("/api/world"))
    assert world["models"]["Moisture"]["ignores"] and world["colors"]["biome"][0]
    july = np.frombuffer(get("/api/field?name=surface_temperature&month=7"), dtype="<f4")
    assert np.array_equal(july, w.fields["surface_temperature"][6])
    speed = np.frombuffer(get("/api/field?name=wind&month=1"), dtype="<f4")
    assert np.allclose(speed, np.linalg.norm(w.fields["wind"][0], axis=1), atol=1e-4)
    east = np.frombuffer(get("/api/field?name=wind&month=1&part=east"), dtype="<f4")
    assert np.allclose(east, np.einsum("ij,ij->i", w.fields["wind"][0], w.mesh.east), atol=1e-4)
    values = json.loads(get(f"/api/cell?id={cell}"))["values"]
    assert len(values["precipitation"]) == 12 and len(values["wind"]) == 24 and isinstance(values["biome"], str)
    why = json.loads(get(f"/api/explain?cell={cell}&field=biome"))
    assert why["chain"] and why["notices"] == []
    srv.shutdown()
