"""Trial of build step 1: what one climate round costs.

It builds a world and reports, for the climate stage, the time each process took in each round, the time
of the first round (which includes preparing the solver of the energy balance and compiling the loops),
and the totals. Results are written to trials/results/.

    python trials/climate_round_cost.py [profile]
"""
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine.engine import Engine                        # noqa: E402
from worldengine.params import DEFAULT_DATA_DIR              # noqa: E402


def main(profile="standard"):
    t0 = time.perf_counter()
    e = Engine(DEFAULT_DATA_DIR, profile=profile)
    w = e.build()
    total = time.perf_counter() - t0
    rounds = [r for r in w.round_times if r["stage"] == "climate" and not r["start_step"]]
    steps = [s for s in e.order()["climate"]]
    later = [r for r in rounds[1:] if not r["cause_pass"]]
    result = {
        "profile": profile, "cells": w.n, "machine": platform.processor() or platform.machine(), "cores": os.cpu_count(),
        "total_seconds": round(total, 1), "climate_rounds": w.rounds_used["climate"], "settled": w.settled["climate"],
        "first_round_seconds": {s: round(rounds[0]["seconds"].get(s, 0.0), 2) for s in steps},
        "later_round_seconds_mean": {s: round(float(np.mean([r["seconds"].get(s, 0.0) for r in later])), 2) for s in steps},
        "later_round_total_mean": round(float(np.mean([sum(r["seconds"].values()) for r in later])), 2),
        "cause_pass_seconds": round(sum(rounds[-1]["seconds"].values()), 2),
        "geological_seconds": round(sum(sum(r["seconds"].values()) for r in w.round_times if r["stage"] == "geological"), 2),
        "notices": w.notices}
    result["solver_preparation_seconds"] = round(result["first_round_seconds"]["EnergyBalance"] - result["later_round_seconds_mean"]["EnergyBalance"], 2)
    out = Path(__file__).resolve().parent / "results"
    out.mkdir(exist_ok=True)
    (out / f"climate_round_cost_{profile}.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:2])
