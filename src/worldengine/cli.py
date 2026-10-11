"""Command line: build a world, look at it, ask why.

    python -m worldengine order   [--profile P]
    python -m worldengine build   --profile preview --out worlds/first.zarr [--seed N] [--interventions FILE]
                                  [--history-my 500 --continue-from worlds/older.zarr]
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

from .console import print_anywhere
from .params import DEFAULT_DATA_DIR, ParameterError, load_yaml_text
from .scheduler import Refused


def _engine(args, log=None):
    from .engine import Engine
    overrides = {}
    if getattr(args, "interventions", None):                 # read with the same rules as the files of the data directory
        path = Path(args.interventions)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ParameterError(f"{path}: the push file is missing") from None
        overrides["interventions"] = load_yaml_text(text, path.name) or []
    if getattr(args, "history_my", None) is not None:        # the length of the geological history, in place of stages.yaml's
        stages = load_yaml_text((Path(args.data) / "stages.yaml").read_text(encoding="utf-8"), "stages.yaml")
        for s in stages["stages"]:
            if s.get("clock") == "geological":
                s["history_length_my"] = float(args.history_my)
        overrides["stages"] = stages
    return Engine(args.data, profile=args.profile, seed=args.seed, overrides=overrides or None, log=log)


def _nearest_cell(view, lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    p = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    return int(np.argmax(view.mesh_array("xyz") @ p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="worldengine", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=lambda **kw: argparse.ArgumentParser(**{**kw, "allow_abbrev": False}))
    for name in ("order", "build"):
        sp = sub.add_parser(name)
        sp.add_argument("--data", default=str(DEFAULT_DATA_DIR), help="directory of parameter files")
        sp.add_argument("--profile", default="preview")
        sp.add_argument("--seed", type=int, default=None, help="world seed; the default is in seeds.yaml")
        sp.add_argument("--interventions", default=None, help="a push file to use in place of interventions.yaml")
        if name == "build":
            sp.add_argument("--out", required=True, help="path of the world store to write")
            sp.add_argument("--quiet", action="store_true")
            sp.add_argument("--history-my", type=float, default=None, help="length of the geological history in My")
            sp.add_argument("--continue-from", default=None, help="a world store whose geological history this build goes on from")
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
    sp = sub.add_parser("weather", help="the weather of one day at one place, worked out on request (build step 8)")
    sp.add_argument("store")
    sp.add_argument("--day", type=int, required=True, help="days from the first day of year 0")
    sp.add_argument("--days", type=int, default=1, help="this many days from --day on")
    sp.add_argument("--cell", type=int)
    sp.add_argument("--lat", type=float)
    sp.add_argument("--lon", type=float)
    sp = sub.add_parser("detail", help="finer cells over one region of a world: a summary of what they hold (build step 11)")
    sp.add_argument("store")
    sp.add_argument("--lat", type=float, required=True)
    sp.add_argument("--lon", type=float, required=True)
    sp.add_argument("--radius-km", type=float, default=500.0)
    args = ap.parse_args(argv)
    print_anywhere()
    if args.cmd in ("explain", "weather") and args.cell is None and (args.lat is None or args.lon is None):
        print(f"refused: {args.cmd} needs a place: --cell N, or --lat and --lon", file=sys.stderr)
        return 2
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
            carry = None
            if args.continue_from:
                from .store import StoreView
                carry = StoreView(args.continue_from)
            world = eng.build(continue_from=carry)
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
        if args.cmd == "weather":
            from .engine import EngineError, engine_for_store
            cell = args.cell if args.cell is not None else _nearest_cell(view, args.lat, args.lon)
            eng = engine_for_store(view)
            try:
                for day in range(args.day, args.day + max(1, args.days)):
                    w = eng.day_weather(view, day)
                    wind = w["weather_wind"][cell]
                    speed = float(np.linalg.norm(wind))
                    print(f"day {day}: {w['weather_temperature'][cell] - 273.15:6.1f} C, {w['weather_precipitation'][cell]:6.1f} mm, "
                          f"{w['weather_pressure'][cell] / 100:7.1f} hPa, wind {speed:4.1f} m/s, storms {w['storm_influence'][cell]:.2f}")
            except EngineError as e:
                print(f"refused: {e}", file=sys.stderr)
                return 2
            return 0
        if args.cmd == "detail":
            from . import detail as dt
            from .mesh import get_mesh
            coarse = get_mesh(int(view.meta["mesh_level"]))
            region = dt.region_cells(coarse, args.lat, args.lon, args.radius_km, view.attrs["planet"]["radius_m"])
            if region.size == 0:
                print("refused: no cell of the world lies within that distance", file=sys.stderr)
                return 2
            d = dt.refine(view, region)
            f = d.fields
            print(f"{region.size} cells of the world, {d.cells.size} fine cells of mesh level {d.level}")
            print(f"heights {f['elevation'].min():.0f} to {f['elevation'].max():.0f} m; sea on {f['ocean_mask'].mean():.0%} of the fine "
                  f"cells, lakes on {f['lake'].mean():.0%}; the largest river carries {f['river_discharge'].max():.0f} m3/s")
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
    except (ParameterError, Refused, FileNotFoundError, KeyError, IndexError) as e:      # (IndexError: a cell the world does not have)
        print(f"refused: {str(e).strip(chr(39) + chr(34))}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
