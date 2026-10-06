"""The tools and the command line as programs: what they do with their arguments, and that their text prints on any
system. What the tools compute is tested where the data for it is: the Earth tools in tests/test_earth.py, the
world report and the scan of the "why" answers in tests/test_world.py.

[The fourth check of build step 2 found that no test ran any tool, that a misspelt option was passed over without a
word, that --help ended with an error code, and that one tool built a world when asked for its help.]"""
import os
import subprocess
import sys

import pytest
import yaml

from conftest import DATA, ROOT, tool
from worldengine import cli, console, store
from worldengine.engine import Engine

# every script, with the arguments it cannot do without
TOOLS = {"earth_rivers": [], "earth_relief": [], "earth_demand": [], "earth_twin": [], "fetch_reference_data": [],
         "world_report": ["no_such.zarr"], "why_scan": ["no_such.zarr"], "make_biomes_yaml": ["no_such_folder"],
         "viewer_check": ["no_such.zarr", "out"], "refusal_audit": []}
TRIALS = {"climate_round_cost": [], "crust_points_trial": []}


def script(name):
    return ROOT / ("trials" if name in TRIALS else "tools") / f"{name}.py"


def run(*args, **env):
    """A script or the command line in a process of its own; returns (exit code, what it printed, what it said in error)."""
    done = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, timeout=300,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src"), **env})
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("name", [*TOOLS, *TRIALS])
def test_a_script_explains_itself_when_asked_and_does_nothing_else(name, tmp_path):
    """--help prints the script's own description and ends with 0, as a process of its own, and no world is built
    (the folder worlds/ holds what it held), whatever else the script would do without arguments."""
    before = sorted(p.name for p in (ROOT / "worlds").glob("*")) if (ROOT / "worlds").exists() else []
    code, out, err = run(script(name), "--help")
    assert code == 0, (name, err)
    first_line = script(name).read_text(encoding="utf-8").split('"""')[1].strip().splitlines()[0]
    assert first_line in out and "usage: python" in out
    assert before == (sorted(p.name for p in (ROOT / "worlds").glob("*")) if (ROOT / "worlds").exists() else [])


@pytest.mark.parametrize("name", [*TOOLS, "climate_round_cost"])
def test_a_script_refuses_an_option_it_does_not_know(name, capsys):
    """An option that the script does not know ends the run with 2 and a line that names it. Before, such an option
    was passed over: a misspelt --settlements ran the whole report without the part that was asked for."""
    module = tool(name) if name in TOOLS else _trial(name)
    with pytest.raises(SystemExit) as stop:
        module.main([*TOOLS.get(name, []), "--no-such-option"])
    assert stop.value.code == 2
    assert "unrecognized arguments: --no-such-option" in capsys.readouterr().err


def _trial(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, script(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name, arguments, words", [
    ("earth_rivers", ["--settlement", "5"], "unrecognized arguments: --settlement 5"),          # one letter short of --settlements
    ("earth_rivers", ["--ties", "Mean"], "'Mean' is not one of engine, mean, or a whole number"),
    ("earth_rivers", ["--trace", "Styx"], "invalid choice: 'Styx'"),
    ("earth_rivers", ["--valley-share", "0"], "0 is outside above 0 to 1"),
    ("earth_rivers", ["--settlements", "-3"], "-3 is below 0"),
    ("earth_rivers", ["--level", "seven"], "'seven' is not a whole number"),
    ("earth_relief", ["--level", "12"], "12 is outside 3 to 8"),
    ("earth_twin", ["--profile", "no_such"], "invalid choice: 'no_such'"),
    ("earth_rivers", ["--sea-water", "lake"], "invalid choice: 'lake'"),
    ("earth_relief", ["--sea-water", "lake"], "invalid choice: 'lake'"),
    ("earth_demand", ["--sea-water", "lake"], "invalid choice: 'lake'"),
    ("refusal_audit", ["--most", "0"], "0 is below 1"),
    ("why_scan", ["no_such.zarr", "--every", "0"], "0 is below 1"),
    ("climate_round_cost", ["no_such_profile"], "invalid choice: 'no_such_profile'"),
])
def test_a_script_refuses_a_value_it_cannot_use_in_words_that_name_it(name, arguments, words, capsys):
    module = tool(name) if name in TOOLS else _trial(name)
    with pytest.raises(SystemExit) as stop:
        module.main(arguments)
    assert stop.value.code == 2 and words in capsys.readouterr().err


@pytest.mark.parametrize("name", ["world_report", "why_scan", "viewer_check", "make_biomes_yaml"])
def test_a_script_that_reads_a_store_says_so_when_there_is_none(name, capsys):
    assert tool(name).main(TOOLS[name]) == 2
    said = capsys.readouterr().err
    assert ("no world store at no_such.zarr" in said) if name != "make_biomes_yaml" else ("it is not a clone of plotbiomes" in said)


def test_the_parser_of_the_tools_takes_no_shortened_option_and_its_numbers_keep_their_bounds():
    p = console.tool_parser("what the tool does", "python tools/toy.py")
    p.add_argument("--settlements", type=console.whole_number(0), default=0)
    p.add_argument("--share", type=console.number_between(0.0, 1.0, open_low=True), default=0.1)
    assert p.parse_args(["--settlements", "20", "--share", "1"]).settlements == 20
    assert p.parse_args([]).share == 0.1 and p.parse_args(["--share", "0.02"]).share == 0.02
    for bad in (["--settle", "20"], ["--settlements", "2.5"], ["--settlements", "-1"], ["--share", "0"], ["--share", "1.5"],
                ["--share", "nan"], ["--share", "a tenth"]):
        with pytest.raises(SystemExit) as stop:
            p.parse_args(bad)
        assert stop.value.code == 2, bad
    assert console.whole_number(3, 8)("8") == 8


def test_check_fetches_nothing_and_makes_nothing_not_even_the_folder(tmp_path, monkeypatch):
    """`fetch_reference_data.py --check` on a machine without the data made the data folder; and the flag was read
    with `in sys.argv`, so nothing tested that the command line honours it."""
    fetch = tool("fetch_reference_data")
    listed = {"source": {"raw": "http://127.0.0.1:9", "commit": "none"},
              "files": {"a.bin": {"path": "files/a.bin", "bytes": 3, "sha256": "0" * 64}}}
    said = []
    assert fetch.fetch_all(check_only=True, listed=listed, folder=tmp_path / "not_there", say=said.append) == 1
    assert not (tmp_path / "not_there").exists() and said[0] == "missing   a.bin"
    asked = []
    monkeypatch.setattr(fetch, "fetch_all", lambda check_only=False, **more: asked.append(check_only) or 0)
    assert fetch.main(["--check"]) == 0 and fetch.main([]) == 0 and asked == [True, False]


# ---------------------------------------------------------------------------------------------- the command line
@pytest.fixture(scope="module")
def geometry_store(tmp_path_factory):
    models = yaml.safe_load((DATA / "models.yaml").read_text(encoding="utf-8"))
    models["slots"] = {"PlanetGeometry": models["slots"]["PlanetGeometry"]}
    e = Engine(DATA, profile="preview", overrides={"models": models, "interventions": []})
    return store.save(e.build(), e, tmp_path_factory.mktemp("worlds") / "geometry.zarr")


def test_text_with_a_degree_sign_prints_where_the_system_cannot_write_one(geometry_store):
    """The engine's text holds ° ² ³. Sent to a file on Windows it is written in the system's code page, and a code
    page that lacks a character ended the run with UnicodeEncodeError (worldengine.console). Tried here by naming
    an encoding that has none of them: the answer must still come, with the character written as its escape. Not
    run on Windows."""
    code, out, err = run("-m", "worldengine", "explain", geometry_store, "--cell", "5", "--field", "latitude", PYTHONIOENCODING="ascii")
    assert code == 0, err
    assert "Why is latitude like this at" in out and "\\xb0 N" in out and "°" not in out
    code, out, err = run("-m", "worldengine", "explain", geometry_store, "--cell", "5", "--field", "latitude", PYTHONIOENCODING="utf-8")
    assert code == 0 and "° N" in out                                      # and where the system can, it is written as itself
    code, out, err = run(script("why_scan"), geometry_store, "--every", "500", PYTHONIOENCODING="ascii")
    assert code == 0 and "answers read" in out, err                              # a tool, the same way


def test_the_command_line_refuses_what_it_cannot_do_in_one_line(geometry_store, capsys):
    """A refusal is one line that says what is wrong, and the exit code 2; never a traceback."""
    assert cli.main(["explain", str(geometry_store), "--field", "latitude"]) == 2
    assert "explain needs a place: --cell N, or --lat and --lon" in capsys.readouterr().err
    assert cli.main(["explain", str(geometry_store), "--field", "latitude", "--lat", "10"]) == 2
    assert "explain needs a place" in capsys.readouterr().err
    assert cli.main(["explain", str(geometry_store), "--field", "latitude", "--cell", "99999999"]) == 2
    assert "refused: cell 99999999 is outside 0 to 10241" in capsys.readouterr().err
    assert cli.main(["explain", str(geometry_store), "--field", "no_such_field", "--cell", "3"]) == 2
    assert "refused: the world holds no field named no_such_field" in capsys.readouterr().err
    assert cli.main(["info", str(geometry_store.with_name("none.zarr"))]) == 2
    assert "refused: no world store at" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stop:                                       # a shortened option is not taken for the whole one
        cli.main(["explain", str(geometry_store), "--fiel", "latitude", "--cell", "3"])
    assert stop.value.code == 2
    capsys.readouterr()
    assert cli.main(["explain", str(geometry_store), "--field", "latitude", "--lat", "89.9", "--lon", "0"]) == 0
    assert "(cell 0)?" in capsys.readouterr().out                                 # the cell nearest the place: the north pole


def test_the_viewer_is_served_to_this_machine_alone_unless_asked_otherwise(geometry_store, monkeypatch):
    """`serve` listens on 127.0.0.1 by default: a world is not put on the network by a command that does not say so."""
    from worldengine import server
    made = []

    class Stopped:
        class RequestHandlerClass:
            class service:
                warnings = staticmethod(lambda: [])

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(server, "make_server", lambda path, host, port: made.append((host, port)) or Stopped())
    assert cli.main(["serve", str(geometry_store)]) == 0
    assert cli.main(["serve", str(geometry_store), "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert made == [("127.0.0.1", 8765), ("0.0.0.0", 9000)]
