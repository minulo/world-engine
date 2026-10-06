"""Fill the counts of README.md from the measurement (numbers_measured.py). Run from /home/claude/world-engine.
The README keeps its marks in README.template.md beside this script, so that the filling can be repeated."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numbers_measured as N

template = HERE / "README.template.md"
readme = Path("README.md")
if "⟦" in readme.read_text(encoding="utf-8"):
    template.write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")       # the README as edited, marks and all
s = template.read_text(encoding="utf-8")
for mark, value in (("⟦N_TESTS⟧", N.N_TESTS), ("⟦SUITE_MIN⟧", N.SUITE_MIN), ("⟦N_XFAIL⟧", N.N_XFAIL), ("⟦N_SKIP⟧", N.N_SKIP),
                    ("⟦S100_MIN⟧", N.S100_MIN)):
    assert s.count(mark) >= 1, mark
    s = s.replace(mark, str(value))
assert "⟦" not in s
readme.write_text(s, encoding="utf-8")
print("README filled:", N.N_TESTS, "tests,", N.SUITE_MIN, "minutes,", N.N_XFAIL, "expected failures,", N.N_SKIP, "skipped without data,", N.S100_MIN, "minutes for 100 settlements")
