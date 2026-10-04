"""Command line: build a world, look at it, ask why.

    python -m worldengine order   [--profile P]
    python -m worldengine build   --profile preview --out worlds/first.zarr [--seed N] [--interventions FILE]
    python -m worldengine serve   worlds/first.zarr [--port 8765]
    python -m worldengine explain worlds/first.zarr --lat 48 --lon -20 --field biome
    python -m worldengine info    worlds/first.zarr
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from .params import DEFAULT_DATA_DIR, ParameterError
from .scheduler import Refused


def _engine(args, log=None):
    from .engine import Engine
    overrides = {}
    if getattr(args, "interventions", None):
        overrides["interventions"] = yaml.safe_load(Path(args.interventions).read_text(encoding="utf-8")) or []
    return Engine(args.data, profile=args.profile, seed=args.seed, overrides=overrides or None, log=log)


def _nearest_cell(view, lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    p = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    return int(np.argmax(view.mesh_array("xyz") @ p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="worldengine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("order", "build"):
        sp = sub.add_parser(name)
        sp.add_argument("--data", default=str(DEFAULT_DATA_DIR), help="directory of parameter files")
        sp.add_argument("--profile", default="preview")
        sp.add_argument("--seed", type=int, default=None, help="world seed; the default is in seeds.yaml")
        sp.add_argument("--interventions", default=None, help="a push file to use in place of interventions.yaml")
        if name == "build":
            sp.add_argument("--out", required=True, help="path of the world store to write")
            sp.add_argument("--quiet", action="store_true")
    sp = sub.add_parser("serve")
    sp.add_argument("store")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--host", default="127.0.0.1")
    sp = sub.add_parser("explain")
    sp.add_argument("store")
    sp.add_argument("--field", required=True)
    sp.add_argument("--cell", type=int)
    sp.add_argument("--lat", type=float)
    sp.add_argument("--lon", type=float)
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("info")
    sp.add_argument("store")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "order":
            eng = _engine(args)
            for stage, steps in eng.order().items():
                print(f"{stage:11s}: {' -> '.join(steps) if steps else '(no process)'}")
            for note in eng.plan.notes:
                print("note:", note)
            return 0
        if args.cmd == "build":
            from . import store
            out = Path(args.out)
            if out.exists():
                print(f"{out} exists; a world store is written once and never changed. Choose another path.", file=sys.stderr)
                return 2
            t0 = time.perf_counter()
            eng = _engine(args, log=None if args.quiet else print)
            world = eng.build()
            store.save(world, eng, out)
            m = world.meta
            print(f"world written to {out}: {m['cells']} cells, seed {m['seed']}, {time.perf_counter() - t0:.1f} s, "
                  f"fingerprint {world.fingerprint()[:16]}")
            for nt in world.notices:
                print("notice:", json.dumps(nt))
            return 0
        from .store import StoreView
        view = StoreView(args.store)
        if args.cmd == "info":
            a = view.attrs
            print(json.dumps({"meta": a["meta"], "notices": a["notices"], "fields": view.field_names(),
                              "world_fingerprint": a["world_fingerprint"]}, indent=1))
            return 0
        if args.cmd == "explain":
            from .causes import as_text, explain
            cell = args.cell if args.cell is not None else _nearest_cell(view, args.lat, args.lon)
            ans = explain(view, cell, args.field)
            print(json.dumps(ans, indent=1) if args.json else as_text(ans))
            return 0
        if args.cmd == "serve":
            from .server import make_server
            srv = make_server(args.store, host=args.host, port=args.port)
            for wmsg in srv.RequestHandlerClass.service.warnings():
                print("warning:", wmsg)
            print(f"viewer at http://{args.host}:{args.port}/  (stop with Ctrl+C)")
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
            return 0
    except (ParameterError, Refused, FileNotFoundError, KeyError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
