"""What the measurement after the fixes gave (scratchpad/step2/fourth/final2), read out of its logs, and the texts built
from those numbers. Nothing here is typed from memory but the constants marked BY HAND, each with where it comes from."""
import json
import os
import re
from pathlib import Path

from share_table import share_table

HERE = Path(__file__).resolve().parent
F = HERE.parent / "final2"
OLD = HERE.parent / "final"
MUT = HERE.parent.parent / "mut4"
DRAFT = bool(os.environ.get("NOTES_DRAFT"))     # a trial run of the rewrite before every log is there: gaps are marked, not guessed


def timed(name, folder=F):
    """(seconds, GB) of the last line of a log written by timed.py."""
    if DRAFT and not (folder / f"{name}.log").exists():
        return float("nan"), float("nan")
    last = (folder / f"{name}.log").read_text().strip().splitlines()[-1]
    m = re.match(r"TIMED: ([\d.]+) s; peak memory ([\d.]+) GB; exit (\d+)", last)
    if DRAFT and not m:
        return float("nan"), float("nan")
    assert m and m[3] == "0", (name, last)
    return float(m[1]), float(m[2])


def answers(name):
    text = (F / f"why_scan_{name}.log").read_text()
    m = re.search(r"(\d+) answers read; none says anything its numbers contradict", text)
    assert m, text[-300:]
    return int(m[1])


def size_mb(name):
    for line in (F / "sizes.log").read_text().splitlines():
        if line.strip().endswith(f"{name}.zarr"):
            return int(line.split()[0])
    raise KeyError(name)


def rounds(name):
    text = (F / f"{name}.log").read_text()
    m = re.search(r"'climate': (\d+)", text) or re.search(r"\((\d+) cells, (\d+) climate rounds", text)
    return int(m[1] if "climate':" in m[0] else m[2])


# ------------------------------------------------------------------------------------------------ the suite (BY HAND, from
# final2/suite_with_data.log and final2/suite_without_data.log; see suite_numbers() below, which reads them)
def suite_numbers():
    if DRAFT and not (F / "suite_without_data.log").exists():
        return {"tests": 0, "passed": 0, "xfailed": 0, "minutes": 0.0, "skipped": 0, "rest_passed": 0, "rest_xfailed": 0, "minutes_without": 0.0}
    with_data = (F / "suite_with_data.log").read_text()
    without = (F / "suite_without_data.log").read_text()
    m = re.search(r"(\d+) passed, (\d+) xfailed(?:, \d+ warnings?)? in ([\d.]+)s", with_data)
    assert m and not re.search(r"\d+ (failed|errors?)\b", with_data.splitlines()[-1]), with_data[-400:]
    passed, xfailed, seconds = int(m[1]), int(m[2]), float(m[3])
    w = re.search(r"(\d+) passed, (\d+) skipped(?:, (\d+) xfailed)?(?:, \d+ warnings?)? in ([\d.]+)s", without)
    assert w and not re.search(r"\d+ (failed|errors?)\b", without.splitlines()[-1]), without[-400:]
    return {"tests": passed + xfailed, "passed": passed, "xfailed": xfailed, "minutes": seconds / 60.0,
            "skipped": int(w[2]), "rest_passed": int(w[1]), "rest_xfailed": int(w[3] or 0), "minutes_without": float(w[4]) / 60.0}


S = suite_numbers()
N_TESTS, N_PASS, N_XFAIL, N_SKIP = S["tests"], S["passed"], S["xfailed"], S["skipped"]
N_REST = S["rest_passed"] + S["rest_xfailed"]
REST_XFAIL = S["rest_xfailed"]
SUITE_MIN = round(S["minutes"])
assert N_SKIP + N_REST == N_TESTS, S
REST_SENTENCE = (f"Of the other {N_REST}, {S['rest_passed']} pass and {REST_XFAIL} "
                 + ("is an expected failure" if REST_XFAIL == 1 else "are expected failures")
                 + " that the engine's own world gives without any data of Earth.")

# ------------------------------------------------------------------------------------------------ the changes on purpose
MUTATIONS = list({r["id"]: r for r in (json.loads(line) for line in (MUT / "results.jsonl").read_text().splitlines())}.values())
# (a change run more than once counts with its last run: two were run again after a test that failed by itself was mended)
NOT_NOTICED = sorted(r["id"] for r in MUTATIONS if not r["caught"])
N_RUNS, N_NOTICED = len(MUTATIONS), sum(1 for r in MUTATIONS if r["caught"])

# ------------------------------------------------------------------------------------------------ texts
SHARE_TABLE = share_table(F / "shares" if (F / "shares" / "share_0.1.log").exists() else HERE.parent / "after4" / "shares")
assert DRAFT or (F / "shares" / "share_0.1.log").exists()

t_prev, m_prev = timed("default_preview")
t_std, m_std = timed("default_standard")
t_tprev, m_tprev = timed("twin_preview")
t_tstd, m_tstd = timed("twin_standard")
t_riv, m_riv = timed("earth_rivers")
t_s20, m_s20 = timed("earth_rivers_s20")
t_s100, m_s100 = timed("earth_rivers_s100")
t_rel, m_rel = timed("earth_relief")
t_dem, m_dem = timed("earth_demand")
t_scan, _ = timed("why_scan_preview")
S100_MIN = round(t_s100 / 60.0) if t_s100 == t_s100 else 0

# BY HAND, from final2/rounds2.py on the four stores (the seconds of each round are in the stores): a later round, whole,
# as the median of rounds 3 on; the first round and its parts on the standard mesh; the pass that records the causes
LATER = {"default_preview": 0.9, "default_standard": 20.8, "twin_preview": 0.8, "twin_standard": 18.8}
FIRST_STANDARD = {"whole": 68.6, "EnergyBalance": 28.2, "Moisture": 30.3, "Circulation": 7.6}
LATER_STANDARD = {"Moisture": 16.4, "Circulation": 2.3, "Hydrology": 1.2, "Biomes": 0.5, "EnergyBalance": 0.4}
CAUSE_PASS_STANDARD = 22.2
OLD_STD, _ = timed("default_standard", OLD)
OLD_TSTD, _ = timed("twin_standard", OLD)
OLD_PREV, _ = timed("default_preview", OLD)
OLD_TPREV, _ = timed("twin_preview", OLD)

SEC47 = f'''### 4.7 Run times

All [MEASURED] on the 2-core build environment, on 2026-10-05. The builds of the worlds, the test
suite and the tools had the machine to themselves, but for two rows: the scan and the 100
settlements ran beside another job and may be slow by a half. The laptop is not timed.

| What | Cells | Whole run | Climate rounds | A later round | Most memory held | World store |
|---|---|---|---|---|---|---|
| Default world, preview profile | 10,242 | {t_prev:.0f} s | {rounds("default_preview")} | {LATER["default_preview"]} s | {m_prev:.1f} GB | {size_mb("default_preview")} MB |
| Default world, standard profile | 163,842 | {t_std:.0f} s | {rounds("default_standard")} | {LATER["default_standard"]:.0f} s | {m_std:.1f} GB | {size_mb("default_standard")} MB |
| Earth twin, preview | 10,242 | {t_tprev:.0f} s | {rounds("twin_preview")} | {LATER["twin_preview"]} s | {m_tprev:.1f} GB | {size_mb("twin_preview")} MB |
| Earth twin, standard | 163,842 | {t_tstd:.0f} s | {rounds("twin_standard")} | {LATER["twin_standard"]:.0f} s | {m_tstd:.1f} GB | {size_mb("twin_standard")} MB |
| Earth's rivers (`tools/earth_rivers.py`, standard mesh) | 163,842 | {t_riv:.0f} s | | | {m_riv:.1f} GB | |
| … with 20 random settlements of the ties | 163,842 | {t_s20:.0f} s | | | {m_s20:.1f} GB | |
| … with 100, and the table of the cuts | 163,842 | {t_s100:.0f} s | | | {m_s100:.1f} GB | |
| Earth's relief (`tools/earth_relief.py`) | 163,842 | {t_rel:.0f} s | | | {m_rel:.1f} GB | |
| The demand for water (`tools/earth_demand.py`) | 163,842 | {t_dem:.0f} s | | | {m_dem:.1f} GB | |
| The scan of the "why" answers (`tools/why_scan.py`), preview world, every cell | 10,242 | {t_scan:.0f} s | | | | |
| The test suite | | {SUITE_MIN} minutes | | | | |

In a later round of the standard build Moisture takes {LATER_STANDARD["Moisture"]:.0f} s, Circulation {LATER_STANDARD["Circulation"]} s, Hydrology {LATER_STANDARD["Hydrology"]} s,
Biomes {LATER_STANDARD["Biomes"]} s and EnergyBalance {LATER_STANDARD["EnergyBalance"]} s. The first round takes {FIRST_STANDARD["whole"]:.0f} s: EnergyBalance prepares its solver
({FIRST_STANDARD["EnergyBalance"]:.0f} s) and Moisture starts from dry air ({FIRST_STANDARD["Moisture"]:.0f} s). The pass that records the causes costs one more round.
The limit of the standard profile is 1,800 s.

**The machine's speed changes from day to day, by a factor of two.** The table is of 2026-10-05,
after the fixes that answer the fourth check. The measurement before them, earlier the same day, gave
{OLD_STD:.0f} s and {OLD_TSTD:.0f} s for the two standard builds and {OLD_PREV:.0f} s and {OLD_TPREV:.0f} s for the two preview ones. Two days of
measurement before that gave, for the standard build, 492 to 531 s at the end of step 1 and 1,186 s
at the first measurement of step 2; the preview build took 23 s and 48 s. On the slow day the code
of step 1 was run again and took 1.5 times as long as on the day it was first measured. Like for
like, step 2 costs seven more climate rounds (23 for 16 on the preview mesh, 24 for 17 on the
standard one), because the water that land gives back must settle with the rain it feeds, and about
5 % more per round for Hydrology. The times in the table are good to that factor of two and no
better. The high_fidelity profile was not run. Its solvers would need about four times the memory of
the standard profile's, so whether it fits in 32 GB is open. [INFERRED]

The same seed gave the same world in two fresh interpreters with different hash seeds. [MEASURED:
test, preview mesh] The standard world was built before the third check and after it. Of its 52
fields, four differ between the two builds: the receiver and the slope of 557 coastal land cells,
and, in sea cells only, the two fields that say which sea cell takes a river's water. That is the
change in how exact ties are settled (section 5.2). [MEASURED: the two stores compared entry by
entry. The fourth check found the 557 cells; I had written that every field on land came out the
same] All four worlds of the table were built before the fixes that answer the fourth check and
after them, and each is the same in every field and every table. [MEASURED: the fingerprints of the
stores, entry by entry] The code that settles ties differed between those builds as well (section 7,
item 20), so this is no test of repeatability; it shows that the change moved nothing in these four
worlds.

'''

TWIN_TABLE = None          # the twins' comparisons are the same line for line (final/twin_*.log against final2/twin_*.log)
WORLD_TABLE = None         # the world reports are the same line for line but for the times

SCAN_NOW = (f"As the scan stands\n  it reads {answers('preview'):,} answers on the default preview world (every cell), {answers('standard'):,} on the\n"
            f"  standard one (every 23rd cell) and {answers('twin_preview'):,} on the preview twin, and none says anything that\n"
            f"  its numbers contradict. [MEASURED] It knows the faults that were found; it proves nothing about\n"
            f"  faults of another kind.")

MUTATIONS_NOW = ""

FAMILY_CHANGE = ("The change moved nothing in the\n"
                 "  default world or in the Earth twin, on either mesh: every field and table is the same before and\n"
                 "  after. [MEASURED: the fingerprints of the four stores] On Earth's relief the wider way now\n"
                 "  settles 6,521 ties and the order of the cells 52, where they settled 6,508 and 65; no mouth, gauge\n"
                 "  or total moved as the engine settles ties, and the Huang He's way crosses 48 flooded cells for 47.\n"
                 "  [MEASURED]")

TWIN_SEASON, TWIN_POLAR, TWIN_WHITE = "13.6", "46", "a third"       # final2/twin_standard.log: 13.6 K; group E 46.1 %; 34.8 %

# BY HAND until the fifth check has reported
FIFTH = "⟦FIFTH⟧"
SEC54 = "### 5.4 What the fifth check of step 2 changed\n\n⟦FIFTH_FOUND⟧\n\n"
NOT_DONE_REVIEW = "⟦NOT_DONE_REVIEW⟧\n"

assert DRAFT or sorted(NOT_NOTICED) == ["Fb", "Fc", "Hk", "Hm"], NOT_NOTICED
MUTATIONS_AGAIN = (f"The 56 changes that the two reviewers had made unnoticed are 55\n"
                   f"different ones: both took the share of land under lakes of the whole planet. I carried all 55 over to\n"
                   f"the code as it stands and ran them again, seven of them a second time against the scan of the\n"
                   f"default world alone, with 13 changes of my own to the code written since: {N_RUNS} runs. The suite\n"
                   f"notices {N_NOTICED}. Of the four it does not notice, two change nothing that a test could see: the rain\n"
                   f"over a basin summed over all its cells, sea included, where no sea cell lies upstream of land; and\n"
                   f"the lake at the Caspian's place looked for one degree further north, which finds the same lake.\n"
                   f"The other two make a settle tolerance a hundred times looser, one in `data/fields.yaml` and one in\n"
                   f"`data/profiles.yaml`. That changes nothing in the default world, where a third tolerance stops\n"
                   f"the rounds. [MEASURED by the second reviewer: the same world, in 23 rounds] No test holds the\n"
                   f"values of the tolerances in the data files, and I added none: it would say only that the file is\n"
                   f"the file. At first those two seemed noticed: the test that failed by itself (above) had stopped\n"
                   f"their runs. A run of changes on purpose proves nothing unless the suite passes without them.\n"
                   f"One change was noticed on the second run only. A clause of the check of the table of\n"
                   f"hollows, that a part's sibling has the part's parent, could still be taken out unnoticed after\n"
                   f"the new tests; it has a test now. [MEASURED: each change made in a copy of the folder, one at a\n"
                   f"time, and the tests run]")
