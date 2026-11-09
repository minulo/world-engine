"""The fantasy layer magic (data/fantasy/magic.yaml): mana with invented physics, run through the engine's machinery.

Every rule of the layer is invented [INVENTED]; these tests hold the layer to its own rules (its books balance, salt
water, ice, rivers and ley lines do what the rules say), to the engine's contract (off by default, adding only, the
climate untouched while its feedback is 0, the same answer for the same input) and to its explanations (every "why"
answer about mana says that its rule is invented and gives the numbers the world holds)."""
import shutil

import numpy as np
import pytest
import yaml

from conftest import DATA, tool
from worldengine import cli, store
from worldengine.causes import explain
from worldengine.engine import Engine, engine_for_store
from worldengine.library.orbit import monthly_insolation
from worldengine.params import ParameterError, Parameters, fantasy_layers
from worldengine.testing import Harness

MAGIC = ("magic",)
KINDS = ("plate_motion", "fire", "old_ground", "life", "storms")


@pytest.fixture(scope="module")
def h():
    return Harness(level=4, fantasy=MAGIC)


def constants(h, slot="Mana"):
    return h.params["models"]["slots"][slot]["constants"]


def cell_at(mesh, lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return int(np.argmax(mesh.xyz @ np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])))


def plain_land(h, **changes):
    """Inputs for Mana alone: continental land everywhere, no plate boundary, fire, plants, ice, river or storm."""
    m, n, months = h.mesh, h.mesh.n, h.months
    zero = np.zeros((months, n))
    reads = {"cell_area": h.run("PlanetGeometry").fields["cell_area"], "ocean_mask": np.zeros(n, dtype=bool),
             "crust_type": np.ones(n, dtype=np.int16), "surface_age": np.zeros(n), "volcanism": np.zeros(n),
             "convergence_rate": np.zeros(n), "boundary_distance": np.full(n, 1.0e8), "flow_receiver": np.full(n, -1, dtype=np.int32),
             "river_discharge": zero, "vegetation_cover": zero, "snow_ice_cover": zero, "storm_track_density": zero,
             "tc_genesis_potential": zero}
    reads.update(changes)
    return reads


def rich(h):
    """Inputs on which every source, every loss and every kind of ley line acts somewhere."""
    m, n, months = h.mesh, h.mesh.n, h.months
    sea = (m.lon > 60) & (m.lon < 150)
    receiver = np.full(n, -1, dtype=np.int32)
    path = walk(m, cell_at(m, 40, -60), cell_at(m, 10, -60))
    receiver[path[:-1]] = path[1:]
    discharge = np.zeros((months, n))
    discharge[:, path[:-1]] = 5000.0
    ice = np.where(m.lat > 65, 1.0, 0.0)[None, :] * np.ones((months, 1))
    return plain_land(h, ocean_mask=sea, crust_type=np.where(sea, 0, 1).astype(np.int16), surface_age=np.where(sea, 50.0, 250.0),
                      volcanism=np.clip(np.cos(np.deg2rad(m.lon * 3)), 0, 1) * (np.abs(m.lat) < 20),
                      convergence_rate=np.full(n, 0.04), boundary_distance=np.abs(m.lat) * 111.0e3,
                      flow_receiver=receiver, river_discharge=discharge,
                      vegetation_cover=np.where(sea, 0.0, 0.5 + 0.4 * np.cos(np.deg2rad(m.lat)))[None, :] * np.ones((months, 1)),
                      snow_ice_cover=ice, storm_track_density=np.ones((months, n)) * (1.0 + np.abs(np.sin(np.deg2rad(m.lat))))[None, :],
                      tc_genesis_potential=np.where(sea & (np.abs(m.lat) < 25), 3.0, 0.0)[None, :] * np.ones((months, 1)))


def walk(mesh, start, end):
    """Cells from start to end, each a neighbour of the one before: always the neighbour nearest the end."""
    path = [start]
    while path[-1] != end:
        around = mesh.nbr[path[-1]][mesh.nbr[path[-1]] >= 0]
        path.append(int(around[np.argmax(mesh.xyz[around] @ mesh.xyz[end])]))
    return np.array(path)


def km2(reads):
    return reads["cell_area"].astype(np.float64) / 1.0e6


def total(field, reads):
    return float((np.asarray(field, dtype=np.float64) * km2(reads)).sum())


# ---------------------------------------------------------------------------------------------- off by default, adding only
def contained(small, large, where=""):
    """Every entry of `small` is in `large` with the same value."""
    if isinstance(small, dict):
        return all(isinstance(large, dict) and k in large and contained(v, large[k], f"{where}.{k}") for k, v in small.items())
    return small == large


def test_the_layer_is_off_by_default_and_only_adds_when_asked():
    plain, magic = Parameters(DATA), Parameters(DATA, fantasy=MAGIC)
    assert fantasy_layers(DATA) == ["magic"]
    assert plain.fantasy == [] and "Mana" not in plain["models"]["slots"] and "fantasy" not in plain["models"]
    for stem in ("models", "fields", "tables", "explanations"):          # off: the files as written, word for word
        assert plain.text[stem] == (DATA / f"{stem}.yaml").read_text(encoding="utf-8")
        assert contained(plain[stem], magic[stem]), f"the layer changed an entry of {stem}.yaml"
    assert magic.fantasy == ["magic"] and {"Mana", "Aura"} <= set(magic["models"]["slots"])
    assert all(cfg["standing"] == "Invented" for slot, cfg in magic["models"]["slots"].items() if slot in ("Mana", "Aura"))
    assert "Mana" not in sum(Engine(DATA, profile="preview").order().values(), [])
    order = Engine(DATA, profile="preview", fantasy=MAGIC).order()["climate"]
    assert order.index("Mana") > order.index("StormClimatology") and order.index("Aura") > order.index("Mana")


def unlabelled_constants(text):
    """The numbers of the models part of a layer's file whose own comment (with the comment lines that follow it) and
    whose enclosing entries' comments all lack the label [INVENTED."""
    statements = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):                         # a comment line goes on the comment of the entry above it
            if statements:
                statements[-1][3] += " " + stripped
            continue
        key, _, rest = stripped.partition(":")
        value, _, comment = rest.partition("#")
        statements.append([len(line) - len(line.lstrip()), key, value.strip(), comment])
    out, stack, inside = [], [], False
    for indent, key, value, comment in statements:
        if indent == 2:
            inside = key == "models"
        while stack and stack[-1][0] >= indent:
            stack.pop()
        labelled = "[INVENTED" in comment or any(s[1] for s in stack)
        stack.append((indent, labelled))
        try:
            float(value)
        except ValueError:
            continue
        if inside and not labelled:
            out.append(key)
    return out


def test_every_constant_and_rule_of_the_layer_is_labelled_invented():
    text = (DATA / "fantasy" / "magic.yaml").read_text(encoding="utf-8")
    layer = yaml.safe_load(text)
    assert unlabelled_constants(text) == []
    assert unlabelled_constants(text.replace("[INVENTED]; with", "; with")) == ["conductivity_land_km2_per_year"]   # the test sees
    assert "Invented" in layer["about"]
    for slot in layer["adds"]["explanations"].values():      # no answer tells an invented rule as if it were physics
        for pattern in slot.values():
            assert pattern["says"].startswith("By the invented rules of the magic layer")
    for spec in layer["adds"]["fields"]["fields"].values():
        assert spec["description"].startswith("Invented, the fantasy layer magic")


def test_a_layer_that_is_unknown_named_twice_or_would_change_an_entry_is_refused(tmp_path):
    with pytest.raises(ParameterError, match="there is no fantasy layer named 'dragons' \\(there are: magic\\)"):
        Parameters(DATA, fantasy=("dragons",))
    with pytest.raises(ParameterError, match="the fantasy layer magic is named twice"):
        Parameters(DATA, fantasy=("magic", "magic"))
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    layer = yaml.safe_load((data / "fantasy" / "magic.yaml").read_text(encoding="utf-8"))
    changing = {**layer, "adds": {**layer["adds"], "models": {"shared": {"lapse_rate_k_per_km": 9.8}}}}
    (data / "fantasy" / "changes.yaml").write_text(yaml.safe_dump(changing), encoding="utf-8")
    with pytest.raises(ParameterError, match="models.shared.lapse_rate_k_per_km: the fantasy layer would change this entry"):
        Parameters(data, fantasy=("changes",))
    (data / "fantasy" / "elsewhere.yaml").write_text(yaml.safe_dump({"about": "x", "adds": {"biomes": {"x": 1}}}), encoding="utf-8")
    with pytest.raises(ParameterError, match="adds to biomes, which is not one of the parameter files"):
        Parameters(data, fantasy=("elsewhere",))
    (data / "fantasy" / "bare.yaml").write_text(yaml.safe_dump({"adds": {}}), encoding="utf-8")
    with pytest.raises(ParameterError, match="fantasy/bare.yaml: the key 'about' is missing"):
        Parameters(data, fantasy=("bare",))


@pytest.mark.parametrize("entry, said", [
    (dict(kind="category", categories=["a", "b"], colors=["#000000"]), "colors gives one display colour per class"),
    (dict(kind="number", colors=["#000000"]), "colors gives one display colour per class"),
    (dict(kind="category", categories=["a"], display={"map": "aether"}), "display names the colour map of a number"),
])
def test_display_colours_must_fit_the_field(tmp_path, entry, said):
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    fields = yaml.safe_load((data / "fields.yaml").read_text(encoding="utf-8"))
    fields["fields"]["odd"] = {"family": "x", "unit": "x", "shape": "cell", **entry}
    (data / "fields.yaml").write_text(yaml.safe_dump(fields, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ParameterError, match=said):
        Engine(data, profile="preview")


def test_the_command_line_takes_the_layer_and_refuses_one_it_does_not_know(capsys):
    assert cli.main(["order", "--fantasy", "magic"]) == 0
    assert "StormClimatology -> Mana -> Aura" in capsys.readouterr().out
    assert cli.main(["order", "--fantasy", "unicorns"]) == 2
    assert "there is no fantasy layer named 'unicorns'" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------- the rules of the layer
def test_at_the_steady_state_the_mana_made_is_the_mana_lost(h):
    """With no ice, plants or sea, every thaum made is lost by decay: the total is the sources over the decay rate. With
    all of them, what is made is what decays, is grounded, is locked by ice and is taken up by life."""
    c = constants(h)
    decay = np.log(2) / c["half_life_years"]
    reads = plain_land(h, volcanism=np.where(np.arange(h.mesh.n) % 97 == 0, 1.0, 0.0), surface_age=np.full(h.mesh.n, 200.0))
    out = h.run("Mana", reads=reads)
    made = total(out.fields["mana_source"], reads)
    assert made > 0
    assert abs(total(out.fields["mana_density"], reads) * decay / made - 1) < 1e-5
    reads = rich(h)
    out = h.run("Mana", reads=reads)
    f = {k: np.asarray(v, dtype=np.float64) for k, v in out.fields.items()}
    year = lambda name: np.asarray(reads[name], dtype=np.float64).mean(axis=0)
    loss = c["losses"]
    sea = reads["ocean_mask"]
    lost = (decay + loss["ice_locking_per_year"] * year("snow_ice_cover") + np.where(sea, 0, loss["life_uptake_per_year"] * year("vegetation_cover"))
            + np.where(sea, loss["sea_grounding_per_year"], 0.0)) * f["mana_density"]
    assert abs(total(lost, reads) / total(f["mana_source"], reads) - 1) < 1e-5
    frozen_decay = np.log(2) / c["frozen_half_life_years"]       # the frozen store is steady too: what ice locks, decays from it
    assert abs(total(frozen_decay * f["frozen_mana"], reads) / total(loss["ice_locking_per_year"] * year("snow_ice_cover") * f["mana_density"], reads) - 1) < 1e-5


def test_salt_water_lowers_the_flow_of_mana_across_a_sea(h):
    m = h.mesh
    fire = np.where(np.arange(m.n) == cell_at(m, 0, -12), 1.0, 0.0)
    strait = np.abs(m.lon) < 5
    far = cell_at(m, 0, 12)
    over_land = h.run("Mana", reads=plain_land(h, volcanism=fire))
    over_sea = h.run("Mana", reads=plain_land(h, volcanism=fire, ocean_mask=strait))
    conducting = h.run("Mana", reads=plain_land(h, volcanism=fire, ocean_mask=strait), constants={"losses": {"sea_grounding_per_year": 0.0}})
    land_far, sea_far = float(over_land.fields["mana_density"][far]), float(over_sea.fields["mana_density"][far])
    assert sea_far < 0.02 * land_far                         # salt water grounds what it does not stop
    assert float(conducting.fields["mana_density"][far]) < 0.2 * land_far    # its low conductivity alone stops most of it
    for crossing in (cell_at(m, 0, 0), cell_at(m, 0, 8)):  # the middle of the strait, and the far shore
        assert float(over_sea.fields["ley_flow"][crossing]) < 0.01 * float(over_land.fields["ley_flow"][crossing])


def test_ice_holds_mana(h):
    m = h.mesh
    cap = m.lat > 60
    storms = np.ones((h.months, m.n))
    plain = h.run("Mana", reads=plain_land(h, storm_track_density=storms))
    iced = h.run("Mana", reads=plain_land(h, storm_track_density=storms, snow_ice_cover=np.where(cap, 1.0, 0.0)[None, :] * storms))
    inside = cap & (m.lat > 75)
    free, frozen = iced.fields["mana_density"].astype(np.float64), iced.fields["frozen_mana"].astype(np.float64)
    assert np.all(frozen[~cap] == 0) and np.all(frozen[cap] > 0) and np.all(plain.fields["frozen_mana"] == 0)
    assert free[inside].max() < 0.5 * plain.fields["mana_density"][inside].min()      # ice takes mana out of the free store ...
    assert (free + frozen)[inside].min() > 3 * plain.fields["mana_density"][inside].max()    # ... and holds more of it than the ground did


def test_a_river_carries_mana_further_than_plain_land(h):
    m = h.mesh
    path = walk(m, cell_at(m, 50, 30), cell_at(m, 10, 30))
    assert len(path) >= 9
    fire = np.where(np.arange(m.n) == path[0], 1.0, 0.0)
    receiver = np.full(m.n, -1, dtype=np.int32)
    receiver[path[:-1]] = path[1:]
    flowing = np.zeros((h.months, m.n))
    flowing[:, path[:-1]] = 20000.0
    dry = h.run("Mana", reads=plain_land(h, volcanism=fire, flow_receiver=receiver))
    river = h.run("Mana", reads=plain_land(h, volcanism=fire, flow_receiver=receiver, river_discharge=flowing))
    downstream = path[4]                                    # about 1,800 km down the river
    assert float(river.fields["mana_density"][downstream]) > 10 * float(dry.fields["mana_density"][downstream])
    beside = cell_at(m, float(m.lat[downstream]), 30 + 2 * (float(m.lon[downstream]) - 30) + 17.0)   # as far from the source, off the river
    assert float(river.fields["mana_density"][downstream]) > 5 * float(river.fields["mana_density"][beside])
    assert river.drivers["ley_flow"]["ley"][path[1]] == 2       # the class "river" of the driver ley


def test_plate_boundaries_on_land_are_ley_lines(h):
    m = h.mesh
    fire = np.where(np.arange(m.n) == cell_at(m, 0, 0), 1.0, 0.0)
    along, across = cell_at(m, 0, 16), cell_at(m, 16, 0)        # 2,000 km along the boundary, 1,500 km across it
    line = h.run("Mana", reads=plain_land(h, volcanism=fire, boundary_distance=np.abs(m.lat) * 111.0e3))
    none = h.run("Mana", reads=plain_land(h, volcanism=fire))
    d, plain = line.fields["mana_density"], none.fields["mana_density"]
    assert float(d[along]) > 5 * float(plain[along])          # the line carries the mana of its fire far along it ...
    assert float(d[across]) < 1.5 * float(plain[across])      # ... and hardly any further away from it
    assert line.drivers["ley_flow"]["ley"][cell_at(m, 0, 40)] == 1    # the class "plate_boundary"


def test_the_drivers_add_up_and_name_the_cells_their_parts_peak_at(h):
    reads = rich(h)
    out = h.run("Mana", reads=reads)
    d, f = out.drivers, out.fields
    parts = sum(d["mana_density"][f"from_{k}"].astype(np.float64) for k in KINDS)
    assert np.allclose(parts, f["mana_density"], rtol=1e-5, atol=1e-6)
    made = sum(d["mana_source"][k].astype(np.float64) for k in KINDS)
    assert np.allclose(made, f["mana_source"], rtol=1e-5, atol=1e-6)
    for k in KINDS:
        assert np.all(d["mana_source"][k] >= 0)
        part, at = d["mana_density"][f"from_{k}"], d["mana_density"][f"{k}_at"]
        assert np.all(part[at] >= part - 1e-6)                  # the cell named holds at least as much of the part as the cell itself
    assert set(np.unique(d["ley_flow"]["ley"])) == {0, 1, 2, 4}
    heat = out.fields["spent_mana_heat"]
    assert np.all(heat == 0) and np.all(d["spent_mana_heat"]["feedback"] == 0)     # the feedback is 0 by default
    w = out.tables["wellsprings"]
    assert len(w["cell"]) and np.all(np.diff(w["mana_density"]) <= 0)
    for row in range(len(w["cell"])):                         # the cause of a wellspring is the kind that made the most of it
        cell = int(w["cell"][row])
        shares = [float(d["mana_density"][f"from_{k}"][cell]) for k in KINDS]
        assert int(w["cause"][row]) == int(np.argmax(shares))
        assert abs(float(w["cause_share"][row]) - max(shares) / float(f["mana_density"][cell])) < 1e-4


def test_the_same_inputs_give_the_same_mana_bit_for_bit(h):
    reads = rich(h)
    first, again = h.run("Mana", reads=reads), Harness(level=4, fantasy=MAGIC).run("Mana", reads=reads)
    for name in first.fields:
        assert np.array_equal(first.fields[name], again.fields[name])
    for column in first.tables["wellsprings"]:
        assert np.array_equal(first.tables["wellsprings"][column], again.tables["wellsprings"][column])
    for field, terms in first.drivers.items():
        for term, value in terms.items():
            assert np.array_equal(value, again.drivers[field][term])


def test_the_aura_follows_the_density_the_wellsprings_and_wild_magic(h):
    m = h.mesh
    c = constants(h, "Aura")["classes"]
    density = np.where(m.lat > 30, c["strong_from_thaum_km2"] + 1, np.where(m.lat > 0, c["steady_from_thaum_km2"],
                       np.where(m.lat > -30, c["faint_from_thaum_km2"], c["faint_from_thaum_km2"] - 0.5)))
    spring = cell_at(m, 60, 0)
    table = {"cell": [spring], "latitude": [60.0], "longitude": [0.0], "mana_density": [200.0], "cause": [1], "cause_share": [0.9]}
    calm = np.zeros((h.months, m.n))
    out = h.run("Aura", reads={"mana_density": density, "storm_track_density": calm, "tc_genesis_potential": calm},
                tables={"wellsprings": table})
    names = h.registry.fields["aura"].categories
    aura = np.array(names)[out.fields["aura"]]
    assert aura[spring] == "wellspring" and np.all(out.fields["wild_magic"] == 0)     # without storms nothing runs wild
    others = np.arange(m.n) != spring
    assert set(aura[(m.lat > 30) & others]) == {"strong"} and set(aura[(m.lat > 0) & (m.lat <= 30)]) == {"steady"}
    assert set(aura[(m.lat > -30) & (m.lat <= 0)]) == {"faint"} and set(aura[m.lat <= -30]) == {"dead_zone"}
    stormy = np.full((h.months, m.n), 40.0)
    wild = h.run("Aura", reads={"mana_density": density, "storm_track_density": stormy, "tc_genesis_potential": calm},
                 tables={"wellsprings": table})
    steep = np.abs(m.lat) < 5                                 # where the density falls by steps, under storms, it runs wild
    assert np.mean(np.array(names)[wild.fields["aura"][steep]] == "wild") > 0.5
    assert wild.fields["wild_magic"][m.lat > 50].max() < 0.5    # a level density stays calm, storms or not


def test_spent_mana_warms_the_surface_where_it_decays(h):
    reads = rich(h)
    warming = h.run("Mana", reads=reads, constants={"spent_mana_heat_w_m2_per_thaum_km2_yr": 0.2})
    heat = warming.fields["spent_mana_heat"].astype(np.float64)
    assert np.allclose(heat, 0.2 * warming.drivers["spent_mana_heat"]["spent"].astype(np.float64)[None, :], rtol=1e-5)
    assert np.all(warming.drivers["spent_mana_heat"]["feedback"] == 1) and heat.max() > 1.0
    g = h.run("PlanetGeometry").fields
    energy = {"insolation": monthly_insolation(g["latitude"], 12, 8, 23.44, 1361.0, 0.0, 0.0, 0.0), "albedo": np.full((12, h.mesh.n), 0.3),
              "ocean_mask": reads["ocean_mask"], "height_above_sea": np.zeros(h.mesh.n), "cell_area": g["cell_area"]}
    cold = h.run("EnergyBalance", reads=energy).fields["surface_temperature"].astype(np.float64).mean(axis=0)
    warm = h.run("EnergyBalance", reads=energy, groups={"surface_heat_flux": {"spent_mana_heat": heat}})
    change = warm.fields["surface_temperature"].astype(np.float64).mean(axis=0) - cold
    yearly = heat.mean(axis=0)
    most, least = yearly >= np.percentile(yearly, 90), yearly <= np.percentile(yearly, 50)
    assert change.min() > 0 and change[most].mean() > 1.5 * change[least].mean()


# ---------------------------------------------------------------------------------------------- small worlds, built whole
def small_engine(data=DATA, fantasy=()):
    """The default world on the mesh of level 4 (2,562 cells) with 10 My of history: a world in about twenty seconds."""
    profiles = yaml.safe_load((data / "profiles.yaml").read_text(encoding="utf-8"))
    profiles["profiles"]["small"] = {**profiles["profiles"]["preview"], "mesh_level": 4}
    stages = yaml.safe_load((data / "stages.yaml").read_text(encoding="utf-8"))
    for s in stages["stages"]:
        if s["clock"] == "geological":
            s["history_length_my"] = 10.0
    models = yaml.safe_load((data / "models.yaml").read_text(encoding="utf-8"))
    models["slots"]["FluvialErosion"]["constants"]["coefficient_per_year"]["by_level"][4] = 1.2e-7
    return Engine(data, profile="small", overrides={"profiles": profiles, "stages": stages, "models": models}, fantasy=fantasy)


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    """The small world without the layer, with it, and with it and spent mana warming the world."""
    plain = small_engine().build()
    e = small_engine(fantasy=MAGIC)
    magic = e.build()
    path = store.save(magic, e, tmp_path_factory.mktemp("magic") / "small-magic.zarr")
    data = tmp_path_factory.mktemp("warm") / "data"
    shutil.copytree(DATA, data)
    layer = yaml.safe_load((data / "fantasy" / "magic.yaml").read_text(encoding="utf-8"))
    layer["adds"]["models"]["slots"]["Mana"]["constants"]["spent_mana_heat_w_m2_per_thaum_km2_yr"] = 0.5
    (data / "fantasy" / "magic.yaml").write_text(yaml.safe_dump(layer, allow_unicode=True), encoding="utf-8")
    warm = small_engine(data, fantasy=MAGIC).build()
    return {"plain": plain, "magic": magic, "store": path, "warm": warm}


def test_with_the_layer_on_and_its_feedback_at_zero_the_world_is_the_same_bit_for_bit(worlds):
    plain, magic = worlds["plain"].fingerprints(), worlds["magic"].fingerprints()
    assert {k: magic[k] for k in plain} == plain
    assert sorted(set(magic) - set(plain)) == sorted(
        ["aura", "frozen_mana", "ley_flow", "mana_density", "mana_source", "spent_mana_heat", "wild_magic"]
        + [f"table:wellsprings.{c}" for c in ("cause", "cause_share", "cell", "latitude", "longitude", "mana_density")])
    assert worlds["plain"].rounds_used == worlds["magic"].rounds_used
    assert worlds["magic"].meta["fantasy"] == ["magic"] and "fantasy" not in worlds["plain"].meta


def test_with_its_feedback_above_zero_spent_mana_warms_the_world_where_it_decays(worlds):
    """Found, then kept (first run, the small world): the cells where most mana is spent warm more than those where
    least is, and the planet as a whole warms."""
    warm, plain = worlds["warm"], worlds["plain"]
    heat = warm.fields["spent_mana_heat"].astype(np.float64).mean(axis=0)
    change = warm.fields["surface_temperature"].astype(np.float64).mean(axis=0) - plain.fields["surface_temperature"].astype(np.float64).mean(axis=0)
    area = warm.mesh.area / warm.mesh.area.sum()
    most, least = heat >= np.percentile(heat, 90), heat <= np.percentile(heat, 50)
    assert heat.max() > 1.0 and (change * area).sum() > 0
    assert change[most].mean() > change[least].mean() + 0.1


def test_a_small_magic_world_is_stored_rebuilt_and_explained(worlds):
    view = store.StoreView(worlds["store"])
    assert view.meta["fantasy"] == ["magic"] and view.attrs["fields"]["mana_density"]["display"] == {"map": "aether"}
    assert view.attrs["category_colors"]["aura"][4] == "#ffd166"
    e = engine_for_store(view)                                # the store's own copy of its parameters holds the layer
    assert e.params.fantasy == ["magic"] and e.order()["climate"][-3:] == ["Mana", "Aura", "WeatherStatistics"]
    scan = tool("why_scan")
    n = view.meta["cells"]
    assert scan.scan(view, range(0, n, 5), fields=scan.MAGIC_FIELDS) == []
    top = int(view.table("wellsprings")["cell"][0])
    reached = {step["field"] for step in explain(view, top, "mana_density")["chain"]}
    assert "mana_source" in reached and reached & {"volcanism", "convergence_rate", "vegetation_cover", "storm_track_density"}
    aura = explain(view, top, "aura")["chain"][0]["text"]
    assert "the aura here is of the class wellspring" in aura or "the aura here is of the class wild" in aura
