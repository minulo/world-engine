"""The fantasy layer magic (data/fantasy/magic.yaml): mana with invented physics, run through the engine's machinery;
and the layer magic-warming, which lets spent mana warm the world.

Every rule of the layers is invented [INVENTED]; these tests hold them to their own rules (the books balance; salt
water, ice, rivers and plate lines do what the rules say; each aspect is the mana of its source; a day's surge follows
the day's storms), to the engine's contract (off by default, adding only, the climate untouched by magic alone, the
same answer for the same input) and to their explanations (every "why" answer about mana says that its rule is
invented and gives the numbers the world holds)."""
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

MAGIC, WARMING = ("magic",), ("magic-warming",)
KINDS = ("plate_motion", "fire", "old_ground", "life", "storms")
ASPECTS = ("deep", "ember", "elder", "verdant", "tempest")          # the aspect of the mana of each kind, in that order


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
                      convergence_rate=np.full(n, 0.04), boundary_distance=np.abs(m.lat) * 45.0e3,   # a plate line 3 degrees to either side
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
    assert fantasy_layers(DATA) == ["magic", "magic-warming"]
    assert plain.fantasy == [] and "Mana" not in plain["models"]["slots"] and "fantasy" not in plain["models"]
    for stem in ("models", "fields", "tables", "explanations"):          # off: the files as written, word for word
        assert plain.text[stem] == (DATA / f"{stem}.yaml").read_text(encoding="utf-8")
        assert contained(plain[stem], magic[stem]), f"the layer changed an entry of {stem}.yaml"
    added = ("Mana", "Aura", "ManaSurge")
    assert magic.fantasy == ["magic"] and set(added) <= set(magic["models"]["slots"]) and "ManaWarmth" not in magic["models"]["slots"]
    assert all(cfg["standing"] == "Invented" for slot, cfg in magic["models"]["slots"].items() if slot in added)
    assert not set(added) & set(sum(Engine(DATA, profile="preview").order().values(), []))
    order = Engine(DATA, profile="preview", fantasy=MAGIC).order()
    climate = order["climate"]
    assert climate.index("Mana") > climate.index("StormClimatology") and climate.index("Aura") > climate.index("Mana")
    assert order["weather"] == ["SynopticStorms", "DailyWeather", "ManaSurge"]


def test_magic_alone_stays_out_of_the_climates_rounds_and_the_warming_layer_brings_it_in():
    """Nothing in the climate reads a field of the layer magic, so Mana and Aura run once, after the climate has settled
    (Engine._tail), with the storm maps they read: a world with magic costs no round of the climate more than one without.
    The layer magic-warming adds the one reader, of the mana spent in the round before, and with it Mana and the storm
    maps take part in the rounds. Aura, which nothing reads, never does."""
    plain = Engine(DATA, profile="preview")
    magic = Engine(DATA, profile="preview", fantasy=MAGIC)
    warm = Engine(DATA, profile="preview", fantasy=WARMING)
    assert magic._tail("climate") == plain._tail("climate") | {"Mana", "Aura"}
    assert "StormClimatology" in plain._tail("climate")
    assert warm._tail("climate") & {"Mana", "Aura", "StormClimatology", "ManaWarmth"} == {"Aura"}
    assert "mana_spent" in warm.lagged_fields and "mana_spent" not in magic.lagged_fields


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
    for name in ("magic", "magic-warming"):
        text = (DATA / "fantasy" / f"{name}.yaml").read_text(encoding="utf-8")
        layer = yaml.safe_load(text)
        assert unlabelled_constants(text) == [], name
        assert "Invented" in layer["about"]
        for slot in layer["adds"]["explanations"].values():      # no answer tells an invented rule as if it were physics
            for pattern in slot.values():
                assert all(pattern[k].startswith("By the invented rules of the magic layer") for k in ("says", "says_zero") if k in pattern)
                assert all(case.get("says", "By the invented rules of the magic layer").startswith("By the invented rules of the magic layer")
                           for case in pattern.get("cases", []))
        for spec in layer["adds"]["fields"]["fields"].values():
            assert spec["description"].startswith("Invented, the fantasy layer magic")
    text = (DATA / "fantasy" / "magic.yaml").read_text(encoding="utf-8")
    assert unlabelled_constants(text.replace("[INVENTED]; with", "; with")) == ["conductivity_land_km2_per_year"]   # the test sees
    assert unlabelled_constants(text.replace("by the same\n", "\n").replace("ley_rule) [INVENTED, all]", "ley_rule)")) == [
        "boundary_gain", "boundary_width_km", "river_from_m3_s", "river_half_discharge_m3_s", "river_carry_per_year", "river_strip_km"]


def test_a_layer_that_is_unknown_named_twice_or_would_change_an_entry_is_refused(tmp_path):
    with pytest.raises(ParameterError, match="there is no fantasy layer named 'dragons' \\(there are: magic, magic-warming\\)"):
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


def test_a_layer_that_needs_another_has_it_laid_first(tmp_path):
    """magic-warming builds on magic (its `needs`): naming it alone lays magic first, and naming both, in either order,
    gives the same files. A layer that needs one that is not there, and two that need each other, are refused."""
    alone = Parameters(DATA, fantasy=WARMING)
    assert alone.fantasy == ["magic", "magic-warming"] and {"Mana", "Aura", "ManaSurge", "ManaWarmth"} <= set(alone["models"]["slots"])
    for both in (("magic", "magic-warming"), ("magic-warming", "magic")):
        assert Parameters(DATA, fantasy=both).data == alone.data
    with pytest.raises(ParameterError, match="the fantasy layer magic-warming is named twice"):
        Parameters(DATA, fantasy=("magic-warming", "magic", "magic-warming"))
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    (data / "fantasy" / "orphan.yaml").write_text(yaml.safe_dump({"about": "x", "needs": ["griffins"], "adds": {}}), encoding="utf-8")
    with pytest.raises(ParameterError, match="there is no fantasy layer named 'griffins', which the layer orphan needs"):
        Parameters(data, fantasy=("orphan",))
    for name, other in (("chicken", "egg"), ("egg", "chicken")):
        (data / "fantasy" / f"{name}.yaml").write_text(yaml.safe_dump({"about": "x", "needs": [other], "adds": {}}), encoding="utf-8")
    with pytest.raises(ParameterError, match="the fantasy layers chicken and egg need each other"):
        Parameters(data, fantasy=("chicken",))


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
    said = capsys.readouterr().out
    assert "StormClimatology -> Mana -> Aura" in said and "DailyWeather -> ManaSurge" in said and "ManaWarmth" not in said
    assert cli.main(["order", "--fantasy", "magic-warming"]) == 0          # the layer it needs comes with it
    said = capsys.readouterr().out
    assert "Mana -> Aura" in said and "ManaWarmth" in said
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
    # the mana spent (decayed, grounded at sea, decayed in the ice) and the mana life takes up are all the mana made
    taken = np.where(sea, 0, loss["life_uptake_per_year"] * year("vegetation_cover")) * f["mana_density"]
    assert abs((total(f["mana_spent"], reads) + total(taken, reads)) / total(f["mana_source"], reads) - 1) < 1e-5
    spent = sum(out.drivers["mana_spent"][k].astype(np.float64) for k in ("decays", "grounded", "from_ice"))
    assert np.allclose(spent, f["mana_spent"], rtol=1e-5, atol=1e-6) and np.all(out.drivers["mana_spent"]["grounded"][~sea] == 0)


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
    assert np.all(over_sea.fields["ley_flow"] == 0) and np.all(over_land.fields["ley_flow"] == 0)   # no ley line: plain ground, sea


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


def test_a_great_river_carries_mana_downstream_and_a_small_one_does_not(h):
    """Running water carries mana: a great river hands the mana of the strip it sweeps to the cell downstream, so the
    mana of a fire in the middle of its course runs down the river and not up it. A river that carries less than the
    layer's least discharge for a ley line carries none."""
    m = h.mesh
    ley = h.params["models"]["shared"]["mana_ley"]
    path = walk(m, cell_at(m, 50, 30), cell_at(m, -10, 30))
    assert len(path) >= 13
    middle = len(path) // 2
    fire = np.where(np.arange(m.n) == path[middle], 1.0, 0.0)
    receiver = np.full(m.n, -1, dtype=np.int32)
    receiver[path[:-1]] = path[1:]
    flowing = np.zeros((h.months, m.n))
    flowing[:, path[:-1]] = ley["river_from_m3_s"] + 20000.0
    brook = np.where(flowing > 0, ley["river_from_m3_s"], 0.0)                    # at the least discharge, not above it
    dry = h.run("Mana", reads=plain_land(h, volcanism=fire, flow_receiver=receiver))
    small = h.run("Mana", reads=plain_land(h, volcanism=fire, flow_receiver=receiver, river_discharge=brook))
    river = h.run("Mana", reads=plain_land(h, volcanism=fire, flow_receiver=receiver, river_discharge=flowing))
    d, plain = river.fields["mana_density"].astype(np.float64), dry.fields["mana_density"].astype(np.float64)
    for steps in (2, 3, 4):
        down, up = path[middle + steps], path[middle - steps]
        assert d[down] > 3 * plain[down] and d[down] > 3 * d[up]             # down the river, far more than plain ground spreads
        assert d[up] < plain[up]                                           # ... and up it less: the river takes it away
    assert np.array_equal(small.fields["mana_density"], dry.fields["mana_density"]) and np.all(small.fields["ley_flow"] == 0)
    flow = river.fields["ley_flow"].astype(np.float64)
    assert np.all(flow[path[:-1]] > 0) and np.all(np.delete(flow, path[:-1]) == 0)     # the river's cells, and no other, carry
    assert flow[path[middle]] == flow.max()                                # the most where the fire feeds the river
    assert river.drivers["ley_flow"]["ley"][path[1]] == 2 and river.drivers["ley_flow"]["runs_to"][path[1]] == path[2]
    # spreading and carrying move mana and make none: what the fire makes is what decays
    c = constants(h)
    reads = plain_land(h)
    for out in (dry, river):
        assert abs(total(out.fields["mana_density"], reads) * np.log(2) / c["half_life_years"] / total(out.fields["mana_source"], reads) - 1) < 1e-5


def test_plate_boundaries_on_land_are_ley_lines(h):
    m = h.mesh
    fire = np.where(np.arange(m.n) == cell_at(m, 0, 0), 1.0, 0.0)
    along, across = cell_at(m, 0, 16), cell_at(m, 16, 0)        # 2,000 km along the boundary, 1,500 km across it
    wide = {"mana_ley": {**h.params["models"]["shared"]["mana_ley"], "boundary_width_km": 150.0}}   # a line this coarse mesh can hold
    line = h.run("Mana", reads=plain_land(h, volcanism=fire, boundary_distance=np.abs(m.lat) * 111.0e3), shared=wide)
    none = h.run("Mana", reads=plain_land(h, volcanism=fire), shared=wide)
    d, plain = line.fields["mana_density"], none.fields["mana_density"]
    assert float(d[along]) > 5 * float(plain[along])          # the line carries the mana of its fire far along it ...
    assert float(d[across]) < 1.5 * float(plain[across])      # ... and hardly any further away from it
    assert line.drivers["ley_flow"]["ley"][cell_at(m, 0, 40)] == 1    # the class "plate_boundary"
    flow = line.fields["ley_flow"].astype(np.float64)
    assert flow[cell_at(m, 0, 8)] > 0 and np.all(flow[np.abs(m.lat) > 20] == 0) and np.all(none.fields["ley_flow"] == 0)
    sea = h.run("Mana", reads=plain_land(h, volcanism=fire, boundary_distance=np.abs(m.lat) * 111.0e3, ocean_mask=m.lon > 4), shared=wide)
    assert np.all(sea.fields["ley_flow"][m.lon > 4] == 0) and set(sea.drivers["ley_flow"]["ley"][m.lon > 4]) == {4}   # none under salt water


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
    assert "spent_mana_heat" not in f                             # the layer magic delivers no heat: that is magic-warming's
    for k, a in zip(KINDS, ASPECTS):                              # each aspect is the mana its kind of source made
        assert np.array_equal(f[f"mana_{a}"], d["mana_density"][f"from_{k}"].astype(f[f"mana_{a}"].dtype))
        at = d[f"mana_{a}"]["made_at"]
        assert np.array_equal(at, d["mana_density"][f"{k}_at"]) and np.allclose(d[f"mana_{a}"]["peak"], f[f"mana_{a}"][at])
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


def aura_reads(h, density, **changes):
    """Inputs for Aura alone: the density all of one aspect (ember), calm skies, plain land with no boundary and no river."""
    n, calm = h.mesh.n, np.zeros((h.months, h.mesh.n))
    reads = {"mana_density": density, "storm_track_density": calm, "tc_genesis_potential": calm, "ocean_mask": np.zeros(n, dtype=bool),
             "boundary_distance": np.full(n, 1.0e8), "river_discharge": calm,
             **{f"mana_{a}": density if a == "ember" else np.zeros(n) for a in ASPECTS}}
    reads.update(changes)
    return reads


def test_the_aura_follows_the_density_the_wellsprings_and_wild_magic(h):
    m = h.mesh
    c = constants(h, "Aura")["classes"]
    density = np.where(m.lat > 30, c["strong_from_thaum_km2"] + 1, np.where(m.lat > 0, c["steady_from_thaum_km2"],
                       np.where(m.lat > -30, c["faint_from_thaum_km2"], c["faint_from_thaum_km2"] - 0.5)))
    spring = cell_at(m, 60, 0)
    table = {"cell": [spring], "latitude": [60.0], "longitude": [0.0], "mana_density": [200.0], "cause": [1], "cause_share": [0.9]}
    out = h.run("Aura", reads=aura_reads(h, density), tables={"wellsprings": table})
    names = h.registry.fields["aura"].categories
    aura = np.array(names)[out.fields["aura"]]
    assert aura[spring] == "wellspring" and np.all(out.fields["wild_magic"] == 0)     # without storms nothing runs wild
    others = np.arange(m.n) != spring
    assert set(aura[(m.lat > 30) & others]) == {"strong"} and set(aura[(m.lat > 0) & (m.lat <= 30)]) == {"steady"}
    assert set(aura[(m.lat > -30) & (m.lat <= 0)]) == {"faint"} and set(aura[m.lat <= -30]) == {"dead_zone"}
    stormy = np.full((h.months, m.n), 40.0)
    wild = h.run("Aura", reads=aura_reads(h, density, storm_track_density=stormy), tables={"wellsprings": table})
    steep = np.abs(m.lat) < 5                                 # where the density falls by steps, under storms, it runs wild
    assert np.mean(np.array(names)[wild.fields["aura"][steep]] == "wild") > 0.5
    assert wild.fields["wild_magic"][m.lat > 50].max() < 0.5    # a level density stays calm, storms or not


def test_the_aspect_of_a_place_is_the_kind_of_mana_it_holds_most_of(h):
    """Each fifth of the planet's longitudes holds most of one aspect; south of 60 S the mana is too thin for an aura, and
    so for an aspect. The share recorded is the leading aspect's share of the density."""
    m = h.mesh
    c = constants(h, "Aura")["classes"]
    sector = np.clip(((m.lon + 180.0) // 72.0).astype(int), 0, 4)
    thin = m.lat < -60
    parts = {a: np.where(thin, 0.1, np.where(sector == k, 40.0, 5.0)) for k, a in enumerate(ASPECTS)}
    density = sum(parts.values())
    assert density[~thin].min() >= c["faint_from_thaum_km2"] > density[thin].max()
    empty = {"cell": [], "latitude": [], "longitude": [], "mana_density": [], "cause": [], "cause_share": []}
    out = h.run("Aura", reads=aura_reads(h, density, **{f"mana_{a}": v for a, v in parts.items()}), tables={"wellsprings": empty})
    aspect = np.array(h.registry.fields["mana_aspect"].categories)[out.fields["mana_aspect"]]
    assert set(aspect[thin]) == {"none"}
    for k, a in enumerate(ASPECTS):
        assert set(aspect[~thin & (sector == k)]) == {a}
    share = out.drivers["mana_aspect"]["share"].astype(np.float64)
    assert np.allclose(share[~thin], 40.0 / 60.0, atol=1e-6) and np.array_equal(out.drivers["mana_aspect"]["rule"], out.fields["mana_aspect"])


def test_the_ley_lines_on_the_map_are_the_lines_mana_runs_along(h):
    """Aura's map of the ley lines and Mana's spreading and carrying read one rule (library/mana.py, ley_rule): a plate
    line where a plate boundary on land at least doubles what plain ground conducts, a river line along a great river,
    a nexus where they cross, and none under salt water."""
    reads = rich(h)
    mana = h.run("Mana", reads=reads)
    f = mana.fields
    line = h.run("Aura", reads={**{k: reads[k] for k in ("ocean_mask", "boundary_distance", "river_discharge", "storm_track_density",
                                                          "tc_genesis_potential")},
                                "mana_density": f["mana_density"], **{f"mana_{a}": f[f"mana_{a}"] for a in ASPECTS}},
                 tables={"wellsprings": mana.tables["wellsprings"]})
    names = np.array(h.registry.fields["ley_line"].categories)[line.fields["ley_line"]]
    told = np.array(["none", "plate_line", "river_line", "nexus", "none"])[mana.drivers["ley_flow"]["ley"]]   # plain, boundary, river, both, sea
    assert np.array_equal(names, told) and {"plate_line", "river_line", "none"} <= set(names)
    sea = reads["ocean_mask"]
    assert set(names[sea]) == {"none"} and np.all(f["ley_flow"][names == "none"] == 0)
    m = h.mesh
    crossing = h.run("Aura", reads=aura_reads(h, np.full(m.n, 60.0), boundary_distance=np.abs(m.lat) * 45.0e3,
                                              river_discharge=np.where(np.abs(m.lon) < 10, 9000.0, 0.0)[None, :] * np.ones((h.months, 1))),
                     tables={"wellsprings": {k: [] for k in mana.tables["wellsprings"]}})
    crossed = np.array(h.registry.fields["ley_line"].categories)[crossing.fields["ley_line"]]
    assert set(crossed[(np.abs(m.lat) < 1) & (np.abs(m.lon) < 9)]) == {"nexus"} and crossed[cell_at(m, 40, 0)] == "river_line"
    assert crossed[cell_at(m, 0, 90)] == "plate_line" and crossed[cell_at(m, 40, 90)] == "none"


# ---------------------------------------------------------------------------------------------- the surge of a day
def test_a_days_surge_is_where_the_days_storms_cross_a_fall_of_mana(h):
    """ManaSurge is Aura's rule for wild magic on the weather clock: no storm, or mana that lies level, gives none; under
    one storm the surge is higher where the mana falls more steeply, and a stronger storm raises it."""
    m = h.mesh
    density = np.where(m.lat > 0, 150.0, 20.0) + 0.0 * m.lon              # one step along the equator, level elsewhere
    storm = np.exp(-(np.arccos(np.clip(m.xyz @ m.xyz[cell_at(m, 0, 0)], -1, 1)) * 6371.0 / 1500.0) ** 2)      # of one day
    run = lambda **reads: h.run("ManaSurge", reads={"mana_density": density, "storm_influence": storm, **reads}, round_no=200)
    out = run()
    surge = out.fields["mana_surge"].astype(np.float64)
    assert 0 <= surge.min() and surge.max() <= 1
    at_step, level, far = cell_at(m, 0, 0), cell_at(m, 30, 0), cell_at(m, 0, 150)
    assert surge[at_step] > 0.3 and surge[level] < 0.01 and surge[far] < 0.01
    assert np.all(run(storm_influence=np.zeros_like(storm)).fields["mana_surge"] == 0)
    assert np.all(run(mana_density=np.full(m.n, 80.0)).fields["mana_surge"] < 1e-6)
    stronger = run(storm_influence=2 * storm).fields["mana_surge"].astype(np.float64)
    assert np.all(stronger >= surge) and stronger[cell_at(m, 0, 20)] > surge[cell_at(m, 0, 20)]
    c, shared = constants(h, "ManaSurge"), h.params["models"]["shared"]
    fall = out.drivers["mana_surge"]["fall"].astype(np.float64)
    told = 1 - np.exp(-(fall / shared["mana_fall_reference_thaum_km2_per_km"]) * (storm / c["storm_influence_reference"]))
    assert np.allclose(surge, told, atol=1e-6)
    again = run()
    assert np.array_equal(out.fields["mana_surge"], again.fields["mana_surge"])


def test_spent_mana_warms_the_surface_where_it_was_spent(h):
    """The layer magic-warming: the mana spent in the round before delivers heat in proportion, the same in every month,
    through surface_heat_flux; EnergyBalance then warms the most where the most was spent."""
    reads = rich(h)
    spent = h.run("Mana", reads=reads).fields["mana_spent"].astype(np.float64)
    hw = Harness(level=4, fantasy=WARMING)
    per_thaum = hw.params["models"]["slots"]["ManaWarmth"]["constants"]["heat_w_m2_per_thaum_km2_yr"]
    out = hw.run("ManaWarmth", lagged={"mana_spent": spent})
    heat = out.fields["spent_mana_heat"].astype(np.float64)
    assert per_thaum > 0 and heat.shape == (hw.months, hw.mesh.n) and np.allclose(heat, per_thaum * spent[None, :], rtol=1e-5)
    assert np.allclose(out.drivers["spent_mana_heat"]["spent"], spent, rtol=1e-6) and heat.max() > 1.0
    first = hw.run("ManaWarmth")                                 # before any mana was spent: the first round of a climate
    assert np.all(first.fields["spent_mana_heat"] == 0)
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
    """The small world without the layer, with it, and with the layer magic-warming, in which spent mana warms the world."""
    plain = small_engine().build()
    e = small_engine(fantasy=MAGIC)
    magic = e.build()
    path = store.save(magic, e, tmp_path_factory.mktemp("magic") / "small-magic.zarr")
    warm = small_engine(fantasy=WARMING).build()
    return {"plain": plain, "magic": magic, "store": path, "warm": warm}


NEW_FIELDS = ["aura", "frozen_mana", "ley_flow", "ley_line", "mana_aspect", "mana_density", "mana_source", "mana_spent", "wild_magic"] \
    + [f"mana_{a}" for a in ASPECTS]
NEW_COLUMNS = [f"table:wellsprings.{c}" for c in ("cause", "cause_share", "cell", "latitude", "longitude", "mana_density")]


def test_with_the_layer_on_the_world_is_the_same_bit_for_bit(worlds):
    """Magic alone cannot change the world it is laid over: every field and table the plain world holds is the same bit
    for bit, in the same number of rounds, and the layer's own fields stand beside them."""
    plain, magic = worlds["plain"].fingerprints(), worlds["magic"].fingerprints()
    assert {k: magic[k] for k in plain} == plain
    assert sorted(set(magic) - set(plain)) == sorted(NEW_FIELDS + NEW_COLUMNS)
    assert worlds["plain"].rounds_used == worlds["magic"].rounds_used
    assert worlds["magic"].meta["fantasy"] == ["magic"] and "fantasy" not in worlds["plain"].meta


def test_with_the_warming_layer_spent_mana_warms_the_world_where_it_is_spent(worlds):
    """Found, then kept (the small world): the planet as a whole warms, and the cells where most mana is spent warm more
    than those where least is. The climate settles with the mana in its rounds, and the mana itself is another world's:
    its plants, ice and storms have changed with the warmth."""
    warm, plain, magic = worlds["warm"], worlds["plain"], worlds["magic"]
    assert warm.meta["fantasy"] == ["magic", "magic-warming"]
    # the mana and its heat have settled with the climate's rounds. (This small world's climate as a whole has not, within
    # the 60 rounds its profile allows: its yearly runoff still moves by 0.019 mm on the mean where 0.01 is asked. The
    # default world on the preview mesh settles, in 41 rounds [MEASURED: docs/BUILD_NOTES.md, section 31].)
    last = {gap["name"]: gap for gap in warm.settle_log[-1]["gaps"]}
    assert last["mana_spent"]["ok"] and last["group:surface_heat_flux"]["ok"]
    assert sorted(set(warm.fingerprints()) - set(plain.fingerprints())) == sorted(NEW_FIELDS + NEW_COLUMNS + ["spent_mana_heat"])
    heat = warm.fields["spent_mana_heat"].astype(np.float64).mean(axis=0)
    # the heat is that of the mana spent in the round before: it is the layer's heat of a thaum times the mana now spent,
    # within what the settle test lets the spent mana of a cell move in a round (fields: mana_spent, settle)
    layer = lambda name: yaml.safe_load((DATA / "fantasy" / f"{name}.yaml").read_text(encoding="utf-8"))["adds"]
    per_thaum = layer("magic-warming")["models"]["slots"]["ManaWarmth"]["constants"]["heat_w_m2_per_thaum_km2_yr"]
    may_move = layer("magic")["fields"]["fields"]["mana_spent"]["settle"]["cell"]
    gap = np.abs(warm.fields["spent_mana_heat"].astype(np.float64)[0] - per_thaum * warm.fields["mana_spent"].astype(np.float64))
    assert gap.max() < per_thaum * may_move
    change = warm.fields["surface_temperature"].astype(np.float64).mean(axis=0) - plain.fields["surface_temperature"].astype(np.float64).mean(axis=0)
    area = warm.mesh.area / warm.mesh.area.sum()
    most, least = heat >= np.percentile(heat, 90), heat <= np.percentile(heat, 50)
    assert heat.max() > 1.0 and (change * area).sum() > 0.2
    assert change[most].mean() > change[least].mean() + 0.1
    assert not np.array_equal(warm.fields["mana_density"], magic.fields["mana_density"])


def test_a_small_magic_world_is_stored_rebuilt_and_explained(worlds):
    view = store.StoreView(worlds["store"])
    assert view.meta["fantasy"] == ["magic"] and view.attrs["fields"]["mana_density"]["display"] == {"map": "aether"}
    assert view.attrs["category_colors"]["aura"][4] == "#ffd166" and len(view.attrs["category_colors"]["mana_aspect"]) == 6
    e = engine_for_store(view)                                # the store's own copy of its parameters holds the layer
    assert e.params.fantasy == ["magic"] and e.order()["climate"][-3:] == ["Mana", "Aura", "WeatherStatistics"]
    scan = tool("why_scan")
    n = view.meta["cells"]
    assert set(scan.MAGIC_FIELDS) - {"spent_mana_heat"} <= set(view.field_names())
    assert scan.scan(view, range(0, n, 5), fields=scan.MAGIC_FIELDS) == []
    top = int(view.table("wellsprings")["cell"][0])
    reached = {step["field"] for step in explain(view, top, "mana_density")["chain"]}
    assert "mana_source" in reached and reached & {"volcanism", "convergence_rate", "vegetation_cover", "storm_track_density"}
    aura = explain(view, top, "aura")["chain"][0]["text"]
    assert "the aura here is of the class wellspring" in aura or "the aura here is of the class wild" in aura
    aspects = view.specs["mana_aspect"]["categories"]
    aspect = aspects[int(view.field("mana_aspect")[top])]
    cause = ASPECTS[int(view.table("wellsprings")["cause"][0])]
    told = explain(view, top, "mana_aspect")["chain"]
    assert aspect == cause and f"the aspect of the mana here is {aspect}:" in told[0]["text"]     # the table's cause and the map agree
    assert f"mana_{aspect}" in {step["field"] for step in told}


def test_the_surge_of_a_day_is_worked_out_on_request_and_explained(worlds):
    """The weather clock of a magic world: a day's surge of wild magic comes with the day's weather, the same however the
    day is reached, and its "why" answer says that its rule is invented and leads on to the day's storms and the mana."""
    view = store.StoreView(worlds["store"])
    e = engine_for_store(view)
    day = 200
    alone = e.day_weather(view, day)
    assert "mana_surge" in alone and alone["mana_surge"].shape[-1] == view.meta["cells"]
    surge, storms = np.asarray(alone["mana_surge"], dtype=np.float64).ravel(), np.asarray(alone["storm_influence"], dtype=np.float64).ravel()
    assert 0 < surge.max() <= 1 and np.all(surge[storms == 0] == 0) and (surge > 0.1).sum() > 0
    e.day_weather(view, day - 3)
    assert np.array_equal(e.day_weather(view, day)["mana_surge"], alone["mana_surge"])
    today = e.day_view(view, day)
    scan = tool("why_scan")
    assert scan.scan(today, range(0, view.meta["cells"], 3), fields=scan.MAGIC_DAY_FIELDS + ("storm_influence",)) == []
    cell = int(np.argmax(surge))
    chain = explain(today, cell, "mana_surge")["chain"]
    assert chain[0]["text"].startswith("By the invented rules of the magic layer: On day 200, the surge of wild magic here is")
    assert {"storm_influence", "mana_density"} <= {step["field"] for step in chain}
