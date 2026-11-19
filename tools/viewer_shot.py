"""Save pictures of the viewer, for looking at what it draws.

A development tool, not part of the engine. It needs the Python package playwright and a Chromium
(requirements-viewer-check.lock says how to get them).
    python tools/viewer_shot.py STORE OUT_DIR NAME=QUERY [NAME=QUERY ...] [--size 1500x860] [--scale 1] [--page]
                                [--dark] [--do JAVASCRIPT]
It serves the world store itself, opens the viewer once for each NAME=QUERY and saves OUT_DIR/NAME.png:
the map alone, or with --page the whole page. QUERY is the page's query, as in the browser's address:
    globe=                                  the page as it opens
    close=?lat=-2&lon=-12&zoom=11           a place, close in
    flat=?view=flat                         the flat map
    biome=?field=biome&lat=10&lon=95&zoom=3 the data look of one field
Where the view is close enough for the finer cells of a region, it waits for them. --do runs a line of
JavaScript in the page before the picture is taken (the page's own names are in reach: state, draw, ...).
It prints what the page reported for each picture, and ends with 1 if the page reported an error.

A browser without a graphics card draws the illustrated look slowly (seconds for a picture), which is why
the tool waits for the drawing to be done before it takes each picture.
"""
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine import console                          # noqa: E402
from worldengine.server import make_server                # noqa: E402

GRAPHICS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
DRAWN = "() => { draw(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4)); }"   # reading a point waits for the drawing


def a_chromium():
    """A Chromium of this machine other than the one the installed playwright asks for by its number: the one that
    WORLDENGINE_CHROMIUM names, or one in a folder of playwright's browsers. None if there is none."""
    named = os.environ.get("WORLDENGINE_CHROMIUM")
    if named:
        return named
    folders = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers", str(Path.home() / ".cache" / "ms-playwright")]
    for folder in filter(None, folders):
        for pattern in ("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell*", "chromium-*/chrome-*/chrome",
                        "chromium-*/chrome-*/chrome.exe", "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"):
            found = sorted(Path(folder).glob(pattern)) if Path(folder).is_dir() else []
            if found:
                return str(found[-1])
    return None


def launch(playwright):
    """A headless Chromium that can draw WebGL without a graphics card: the one playwright was installed with, or
    failing that another one of this machine (a_chromium)."""
    try:
        return playwright.chromium.launch(args=GRAPHICS)
    except Exception as e:                                # (playwright's own error class; its text names the missing file)
        other = a_chromium()
        if other is None or "xecutable" not in str(e):
            raise
        return playwright.chromium.launch(args=GRAPHICS, executable_path=other)


def wait_for_the_drawing(page, timeout_ms=180000):
    """Wait until the page is ready, the finer cells have come where the view asks for them, and all is drawn."""
    page.wait_for_function("window.viewerReady === true", timeout=timeout_ms)
    wants = ("() => typeof considerDetail === 'function' && state.look === 'map' && state.finer && state.mesh && "
             "(() => { const v = viewOnSphere(); return !!v && v.cellPx >= DETAIL.from; })()")
    if page.evaluate(wants):
        try:
            page.wait_for_function("state.detail !== null || !state.finer", timeout=60000)
        except Exception:                                 # the picture is taken without them, and says so
            print("  (no finer cells came)")
    page.evaluate(DRAWN)


def shots(store, out_dir, wanted, size=(1500, 860), scale=1.0, whole_page=False, dark=False, do=None) -> int:
    from playwright.sync_api import sync_playwright          # needed for this one step only: --help works without it
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    srv = make_server(store, port=0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    problems = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=scale,
                                color_scheme="dark" if dark else "light")
        page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(str(e)))
        for name, query in wanted:
            page.goto(f"http://127.0.0.1:{port}/{query}")
            try:
                wait_for_the_drawing(page)
            except Exception as e:
                problems.append(f"{name}: the page was not ready ({str(e).splitlines()[0]}); it says {page.inner_text('#status')!r}")
                continue
            if do:
                page.evaluate(do)
                page.evaluate(DRAWN)
            (page if whole_page else page.locator("#stage")).screenshot(path=str(out / f"{name}.png"), timeout=180000)
            print(f"{name}: saved {out / (name + '.png')}; status {page.inner_text('#status')!r}")
        browser.close()
    srv.shutdown()
    print("page errors:", problems or "none")
    return 1 if problems else 0


def parser():
    p = console.tool_parser(__doc__, "python tools/viewer_shot.py")
    p.add_argument("store", metavar="STORE")
    p.add_argument("out_dir", metavar="OUT_DIR")
    p.add_argument("wanted", nargs="+", metavar="NAME=QUERY", help="a picture to take: its name, and the page's query (which may be empty)")
    p.add_argument("--size", default="1500x860", metavar="WxH", help="the window's size in points (default 1500x860)")
    p.add_argument("--scale", type=float, default=1.0, help="device pixels to a point: 2 for a sharp picture (default 1)")
    p.add_argument("--page", action="store_true", help="the whole page, not the map alone")
    p.add_argument("--dark", action="store_true", help="as a system set to dark shows it")
    p.add_argument("--do", default=None, metavar="JAVASCRIPT", help="run in the page before each picture is taken")
    return p


def main(argv=None) -> int:
    console.print_anywhere()
    args = parser().parse_args(argv)
    try:
        size = tuple(int(v) for v in args.size.lower().split("x"))
        wanted = [tuple(w.split("=", 1)) for w in args.wanted]
        if len(size) != 2 or min(size) < 1 or any(len(w) != 2 or not w[0] for w in wanted):
            raise ValueError
    except ValueError:
        print("refused: --size is WIDTHxHEIGHT in points, and each picture is NAME=QUERY (the query may be empty)", file=sys.stderr)
        return 2
    if not Path(args.store).exists():
        print(f"refused: no world store at {args.store}", file=sys.stderr)
        return 2
    return shots(args.store, args.out_dir, wanted, size, args.scale, args.page, args.dark, args.do)


if __name__ == "__main__":
    sys.exit(main())
