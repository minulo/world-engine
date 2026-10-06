"""Is every refusal of the engine held by a test? (The design's condition for build step 0: "every refusal message
is tested".)

    python tools/refusal_audit.py [--list] [--only FILE.py ...] [--tests PATH ...] [--most N]

A refusal is a sentence that the engine gives in place of doing what it was asked. The audit finds them by reading
the code of src/worldengine (not the tools, not the Earth harness). Four forms count:
  * the words of a `raise`, where they are written in the statement;
  * a sentence added to a list named `problems`, which a caller raises later;
  * a sentence handed to a local function named `refuse`;
  * a sentence in a list returned by a function whose name ends in `problems`.
A `raise` that passes on words made elsewhere (a variable, a joined list of problems) has no words of its own; the
audit counts those and looks at the places where their words are made.

For every such place the audit does two things.
  1. It runs the tests once and notes, test by test, which places were reached (through Python's own monitoring,
     so it needs Python 3.12 or later).
  2. For each place that a test reached, it writes other words in the place of the refusal's, in a copy of the
     folder, and runs the tests that reached it. A test that holds the words fails. If none fails, the refusal can
     say anything, or nothing true, and no test notices.
It prints the places that no test reached, the places whose words no test holds, and the count of those held. It
returns 0 only if both lists are empty.

What it cannot show: that a test holds the RIGHT words (a test that asks for one word of a sentence is counted as
holding it), or that the refusal comes at the right moment. A place that is reached only inside a fixture shared
by several tests is laid to the first test that used the fixture.

--list     print the places and stop
--only     the audit of these files of src/worldengine alone (names as they are printed by --list)
--tests    the tests to run in step 1 (the default: the whole folder tests/). With a part of the tests, a place
           that only the others reach is reported as not reached
--most     run at most this many of the tests that reach a place (the default: 60)

The whole audit takes about as long as three runs of the test suite.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "worldengine"
OTHER_WORDS = "words that tools/refusal_audit.py wrote in the place of a refusal"
RECORD = "WORLDENGINE_REFUSAL_AUDIT"            # the file the recorder writes to; set for the run of step 1 alone
LEFT_OUT = ("worlds", "reference_data", ".git", ".pytest_cache", "__pycache__")
TOOL = 4                                        # an identifier of Python's monitoring that no debugger or profiler claims


def is_text(node) -> bool:
    """Whether an expression is written as text: a string, a string with slots, or such strings joined or chosen."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return is_text(node.left) or is_text(node.right)
    if isinstance(node, ast.IfExp):
        return is_text(node.body) and is_text(node.orelse)
    return False


def places(only=()) -> tuple:
    """(places, passed_on): every refusal written in the code, and the number of raises that pass on words made
    elsewhere. A place is a dict: file (as printed), path, the lines of the statement it stands in (first, last),
    the span of its words in the file (line, column, end line, end column; columns count bytes), and its words as
    written."""
    found, passed_on = [], 0
    for path in sorted(SOURCE.rglob("*.py")):
        name = path.relative_to(SOURCE).as_posix()
        if only and name not in only:
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)

        def add(statement, words):
            found.append({"file": name, "path": str(path), "first": statement.lineno, "last": statement.end_lineno,
                          "span": (words.lineno, words.col_offset, words.end_lineno, words.end_col_offset),
                          "words": " ".join((ast.get_source_segment(text, words) or "").split())})
        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        listing = {id(r) for f in functions if f.name.endswith("problems") for r in ast.walk(f) if isinstance(r, ast.Return)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                call = node.exc
                if isinstance(call, ast.Call) and call.args and is_text(call.args[0]):
                    add(node, call.args[0])
                elif isinstance(call, ast.Call):
                    passed_on += 1
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and node.value.args:
                call = node.value
                to_problems = (isinstance(call.func, ast.Attribute) and call.func.attr == "append"
                               and isinstance(call.func.value, ast.Name) and call.func.value.id == "problems")
                refuses = isinstance(call.func, ast.Name) and call.func.id == "refuse"
                if (to_problems or refuses) and is_text(call.args[0]):
                    add(node, call.args[0])
            elif isinstance(node, ast.Return) and id(node) in listing and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if is_text(item):
                        add(node, item)
    return sorted(found, key=lambda p: (p["file"], p["span"])), passed_on


def with_other_words(path, span) -> bytes:
    """The file with the words at `span` replaced."""
    lines = Path(path).read_bytes().split(b"\n")
    line, column, end_line, end_column = span
    before, after = lines[line - 1][:column], lines[end_line - 1][end_column:]
    lines[line - 1:end_line] = [before + repr(OTHER_WORDS).encode() + after]
    return b"\n".join(lines)


# ---------------------------------------------------------------------------------------------- step 1: the recorder
# Loaded into the test run as a plugin (python -m pytest -p refusal_audit): it notes which places each test reaches.
_asked, _reached, _now = {}, {}, [None]


def _line(code, line):
    wanted = _asked.get(code.co_filename)
    if wanted:
        for place in wanted.get(line, ()):
            _reached.setdefault(place, []).append(_now[0])
    return sys.monitoring.DISABLE                # each line speaks once per test; pytest_runtest_setup wakes them again


def pytest_sessionstart(session):
    if not os.environ.get(RECORD):
        return
    for k, place in enumerate(places()[0]):
        lines = _asked.setdefault(place["path"], {})
        for line in range(place["first"], place["last"] + 1):
            lines.setdefault(line, []).append(k)
    sys.monitoring.use_tool_id(TOOL, "refusal_audit")
    sys.monitoring.register_callback(TOOL, sys.monitoring.events.LINE, _line)
    sys.monitoring.set_events(TOOL, sys.monitoring.events.LINE)


def pytest_runtest_logstart(nodeid, location):
    if os.environ.get(RECORD):
        _now[0] = nodeid
        sys.monitoring.restart_events()


def pytest_sessionfinish(session, exitstatus):
    if not os.environ.get(RECORD):
        return
    sys.monitoring.set_events(TOOL, 0)
    sys.monitoring.free_tool_id(TOOL)
    reached = {str(k): sorted(set(t for t in tests if t)) for k, tests in _reached.items()}
    Path(os.environ[RECORD]).write_text(json.dumps({"exit": int(exitstatus), "reached": reached}), encoding="utf-8")


# ---------------------------------------------------------------------------------------------- the audit
def run_tests(folder, tests, record=None, quiet=True):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(folder) / "src"), str(Path(folder) / "tools")]))
    env.pop(RECORD, None)
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-x", "-q", *tests]
    if record:
        env[RECORD] = str(record)
        command[3:3] = ["-p", "refusal_audit"]
        command.remove("-x")
    return subprocess.run(command, cwd=folder, env=env, capture_output=quiet, text=True)


def audit(only=(), tests=("tests",), most=60, say=print) -> int:
    if sys.version_info < (3, 12):
        say("the audit needs Python 3.12 or later: it notes which lines a test reaches through sys.monitoring")
        return 2
    found, passed_on = places(only)
    all_places = places()[0]                                  # the recorder numbers every place of the code
    number = {(p["file"], p["span"]): k for k, p in enumerate(all_places)}
    say(f"{len(found)} refusals are written in the code of src/worldengine" + (f" (in {', '.join(only)})" if only else "")
        + f"; {passed_on} raises pass on words made elsewhere")
    with tempfile.TemporaryDirectory() as scratch:
        record = Path(scratch) / "reached.json"
        say("step 1: the tests are run once, to see which refusals each one reaches ...")
        first = run_tests(ROOT, tests, record)
        if not record.exists():
            say("the run of the tests wrote no record:\n" + (first.stdout or "")[-2000:] + (first.stderr or "")[-2000:])
            return 2
        noted = json.loads(record.read_text(encoding="utf-8"))
        if noted["exit"] != 0:
            say(f"the tests do not pass as they stand (pytest ended with {noted['exit']}): an audit of failing tests would show nothing")
            return 2
        copy = Path(scratch) / "copy"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(*LEFT_OUT))
        if (ROOT / "reference_data").exists() and not os.environ.get("WORLDENGINE_REFERENCE_DATA"):
            os.environ["WORLDENGINE_REFERENCE_DATA"] = str(ROOT / "reference_data")      # the copy reads the data where it lies
        unreached, unheld, held, broke = [], [], 0, []
        say("step 2: other words are written in the place of each refusal that a test reached, and those tests are run ...")
        for place in found:
            reaching = noted["reached"].get(str(number[(place["file"], place["span"])]), [])
            where = f"{place['file']}:{place['span'][0]}"
            if not reaching:
                unreached.append(place)
                continue
            target = copy / "src" / "worldengine" / place["file"]
            original = target.read_bytes()
            target.write_bytes(with_other_words(target, place["span"]))
            try:
                done = run_tests(copy, reaching[:most])
            finally:
                target.write_bytes(original)
            if done.returncode == 1:
                held += 1
            elif done.returncode == 0:
                unheld.append((place, len(reaching)))
            else:
                broke.append((place, done.returncode))
            say(f"   {where:38s} {'held' if done.returncode == 1 else 'NOT HELD' if done.returncode == 0 else f'the run ended with {done.returncode}'}"
                f"   ({min(len(reaching), most)} of {len(reaching)} tests run)")
    short = lambda p: f"   {p['file']}:{p['span'][0]}   {p['words'][:150]}"
    say(f"\nno test reaches {len(unreached)} of the {len(found)} refusals" + (":" if unreached else ""))
    for place in unreached:
        say(short(place))
    say(f"\na test reaches {len(unheld)} more whose words no test holds" + (":" if unheld else ""))
    for place, count in unheld:
        say(short(place) + f"   [{count} tests reach it]")
    if broke:
        say(f"\nfor {len(broke)} the run of the tests ended neither in a pass nor in a failed test:")
        for place, code in broke:
            say(short(place) + f"   [pytest ended with {code}]")
    say(f"\nheld by a test: {held} of {len(found)}")
    return 0 if not (unreached or unheld or broke) else 1


def parser():
    sys.path.insert(0, str(ROOT / "src"))
    from worldengine import console
    p = console.tool_parser(__doc__, "python tools/refusal_audit.py")
    p.add_argument("--list", action="store_true")
    p.add_argument("--only", nargs="+", default=[], metavar="FILE.py")
    p.add_argument("--tests", nargs="+", default=["tests"], metavar="PATH")
    p.add_argument("--most", type=console.whole_number(1), default=60, metavar="N")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    from worldengine import console
    console.print_anywhere()
    if args.list:
        found, passed_on = places(args.only)
        for place in found:
            print(f"{place['file']}:{place['span'][0]}   {place['words'][:160]}")
        print(f"{len(found)} refusals; {passed_on} raises pass on words made elsewhere")
        return 0
    return audit(tuple(args.only), tuple(args.tests), args.most)


if __name__ == "__main__":
    sys.exit(main())
