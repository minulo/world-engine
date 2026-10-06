"""values.json for build_notes.py: the measured values that are not in the logs of the Earth tools. Read from the
`.time` files and the suite logs; the few sentences that state what was run are typed here, beside their numbers."""
import json, re, sys
from pathlib import Path
L, SUITE, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
def tm(path):
    m = re.match(r"([\d.]+) s; peak memory ([\d.]+) GB; exit (\d+)", Path(path).read_text())
    assert m and m[3] in ("0", "1"), path
    return {"s": f"{float(m[1]):,.0f} s", "gb": f"{float(m[2]):.1f} GB", "exit": int(m[3]), "seconds": float(m[1])}
def suite(name):
    text = (SUITE / name).read_text()
    m = re.search(r"(\d+) passed(?:, (\d+) skipped)?, (\d+) xfailed in ([\d.]+)s", text)
    assert m and not re.search(r"\d+ (failed|error)", text.splitlines()[-2]), text[-300:]
    return int(m[1]), int(m[2] or 0), int(m[3]), float(m[4])
a, b = suite("suite_with_data.log"), suite("suite_without_data.log")
commit = (SUITE / "suite_code_state.txt").read_text().split()[0][:7]
assert len((SUITE / "suite_code_state.txt").read_text().split()) == 1, "the suite ran on a tree with changes"
W = L / "worlds"
x = {"date": "2026-10-06", "biomes": "tropical 20.9 (19.0), dry 24.9 (30.2), temperate 13.3 (13.4), cold 26.5 (24.6), polar 14.5 (12.8)",
     "suite": {"tests": a[0] + a[2], "minutes": f"{a[3] / 60:.0f}", "passed": a[0], "xfailed": a[2], "skipped": b[1], "passed_without": b[0], "xfailed_without": b[2],
               "commit": commit, "seconds": f"{a[3]:,.0f}", "seconds_without": f"{b[3]:,.0f}"},
     "times": {"rounds": {"preview": 23, "standard": 24, "twin_preview": 15, "twin_standard": 15},
               "sizes": {k: int((W / "sizes.txt").read_text().split("\n")[i].split()[0]) for k, i in (("big", 0), ("first", 1), ("twin_preview", 2), ("twin_standard", 3))},
               **{k: tm(W / f"{k}.log.time") for k in ("build_preview", "build_standard", "twin_preview", "twin_standard", "scan_preview", "scan_standard")},
               **{k: tm(L / f"{k}.log.time") for k in ("rivers", "rivers_s20", "rivers_s100", "relief", "demand")}},
     "twin": {"swing": 13.6, "swing_earth": 30.9, "E": 46, "white": 35, "lakes_standard": 8.5},
     "twin_table": [], "step2_table": [], "world_table": []}
for line, key in zip((W / "sizes.txt").read_text().splitlines(), ("big", "first", "twin_preview", "twin_standard")):
    assert key.replace("big", "big.zarr").replace("first", "first.zarr") in line or key in line, (line, key)
audit = tm(SUITE / "refusal_audit.log.time")
x["audit_seconds"] = audit["seconds"]; x["audit_exit"] = audit["exit"]
x["audit_time_row"] = f"| The refusal audit (`tools/refusal_audit.py`) | | {audit['s']} | | {audit['gb']} |"
x.update(json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")))
OUT.write_text(json.dumps(x, indent=1, ensure_ascii=False), encoding="utf-8")
print("values written:", x["suite"], audit)
