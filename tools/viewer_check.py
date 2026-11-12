"""Open the viewer on a world store in a headless browser and save screenshots.

A development tool, not part of the engine. It needs the Python package playwright and a Chromium.
    python tools/viewer_check.py STORE OUT_DIR [field ...] ["?lat=48&lon=-20&month=7"] [--no-class FIELD]
For each field it saves a globe view and a flat view, then clicks the middle of the globe and
saves the page with the cell panel filled in. It prints what the page reported.
With --no-class FIELD it also checks that a class field whose every cell holds a code outside
its list is drawn in the colour kept for such codes, and not in the colour of a class.
Where the world can be drawn (it has a sea), the viewer opens in the illustrated look, and the
tool first checks that look and the zoom: that the drawing shows sea where the cells are sea and
land where they are land, that it has rivers, that every way of zooming works and keeps the place
under the pointer under it, that the seasons change the drawing, and that choosing a field shows
the data again. It saves drawing_globe.png, drawing_flat.png and drawing_close.png.
Where the world holds them, it checks two more things on every run: a field of numbers that
name things (a receiver cell, a plate) is shown in whole numbers, with "none" for the number
that means none; and on a scale of ratios a cell that holds exactly zero is drawn in the plain
colour kept for it, one for land and another for the sea, and the legend says so.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine import console                          # noqa: E402
from worldengine.server import make_server                # noqa: E402


NO_CLASS = [217, 26, 191]       # as in viewer.js


def settled(page):
    """Wait until what was drawn has been drawn: a browser without a graphics card draws the illustrated look slowly,
    and a picture asked for while drawings are still waiting would time out. Reading a pixel waits for them."""
    page.evaluate("() => { draw(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4)); }")


def drawing(page, out, problems):
    """The illustrated look and the zoom, on a page that has just opened."""
    zoom = lambda: page.evaluate("state.zoom")                                                    # noqa: E731
    look = page.evaluate("state.look")
    parts = page.evaluate("state.map ? state.map.riverCount : -1")
    print(f"drawing: the viewer opened in the look {look!r}, with {parts} parts of rivers; legend {page.inner_text('#legend')[:60]!r}")
    if look != "map" or parts < 0:
        problems.append(f"the viewer did not open in the illustrated look (look {look!r})")
        return
    if page.evaluate("!!(state.map.recv && state.map.flow)") and parts == 0:
        problems.append("the world has rivers, and the drawing has none")
    page.screenshot(path=str(out / "drawing_globe.png"))
    # a cell with nothing but sea around it is drawn as sea, and one with nothing but land (and no ice or lake) as land
    seen = page.evaluate("""() => {
        const m = state.map, mesh = state.mesh, n = m.sea.length, out = {};
        const ring = (i) => [i, ...Array.from(mesh.nbr.slice(i * 6, i * 6 + 6)).filter((j) => j >= 0)];
        const wide = (i) => [...new Set(ring(i).flatMap(ring))];
        const plain = (i) => !(m.biome && m.biome[i] === m.ice) && !(m.lake && m.lake[i] >= 0.5) && !(m.snowLeast && m.snowLeast[i] >= 0.5);
        for (const [name, sea] of [["sea", 1], ["land", 0]]) {
            let id = -1;
            for (let i = 0; i < n && id < 0; i++) if (wide(i).every((j) => !!m.sea[j] === !!sea && plain(j))) id = i;
            if (id < 0) continue;
            const x = mesh.xyz[id * 3], y = mesh.xyz[id * 3 + 1], z = mesh.xyz[id * 3 + 2];
            state.lat0 = Math.asin(z) * 180 / Math.PI; state.lon0 = Math.atan2(y, x) * 180 / Math.PI; state.zoom = 12; draw();
            const px = new Uint8Array(4), near = [];
            for (const [dx, dy] of [[0, 0], [9, 0], [-9, 0], [0, 9], [0, -9]]) {      // (a small sign may lie on one of them)
                gl.readPixels(Math.floor(canvas.width / 2) + dx, Math.floor(canvas.height / 2) + dy, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
                near.push(Array.from(px).slice(0, 3));
            }
            out[name] = {id, near};
        }
        state.zoom = 0.92; state.lat0 = 20; state.lon0 = 0; draw();
        return out;
    }""")
    blue = lambda c: c[2] > c[0] + 20                                                             # noqa: E731
    for name, got in seen.items():
        as_sea = sum(1 for c in got["near"] if blue(c))
        print(f"drawing: around the middle of cell {got['id']} ({name} with {name} all around): {got['near']}")
        if (name == "sea" and as_sea < 4) or (name == "land" and as_sea > 1):
            problems.append(f"the drawing shows the {name} cell {got['id']} as {got['near']}")
    # the buttons
    start = zoom()
    page.click("#zoomin")
    closer = zoom()
    page.click("#zoomout")
    page.click("#zoomout")
    further = zoom()
    page.click("#zoomreset")
    print(f"zoom buttons: {start:.2f}, + {closer:.2f}, - - {further:.2f}, whole world {zoom():.2f}")
    if not (closer > start > further) or abs(zoom() - start) > 1e-9:
        problems.append(f"the zoom buttons: {start}, {closer}, {further}, {zoom()}")
    # the wheel, the double-click and the pinch keep the place under the pointer under it
    box = page.locator("#gl").bounding_box()
    under = lambda x, y: page.evaluate("([x, y]) => screenToLatLon(x, y)", [x, y])                 # noqa: E731
    for view in ("#viewflat", "#viewglobe"):
        page.click(view)
        x, y = box["x"] + box["width"] * 0.62, box["y"] + box["height"] * 0.41
        page.mouse.move(x, y)
        before, z0 = under(x, y), zoom()
        page.mouse.wheel(0, -600)
        page.wait_for_timeout(150)
        z1, after = zoom(), under(x, y)
        page.mouse.dblclick(x, y)
        page.wait_for_timeout(150)
        z2, again = zoom(), under(x, y)
        page.keyboard.down("Shift")
        page.mouse.dblclick(x, y)
        page.keyboard.up("Shift")
        z3 = zoom()
        page.keyboard.down("Control")
        page.mouse.wheel(0, -40)
        page.keyboard.up("Control")
        z4 = zoom()
        moved = max(abs(a - b) for a, b in zip(before + before, after + again))
        print(f"zoom on {view}: wheel {z0:.2f} to {z1:.2f}, double-click {z2:.2f}, with Shift {z3:.2f}, pinch on a trackpad {z4:.2f}; "
              f"the place under the pointer moved by at most {moved:.2f} degrees")
        if not (z1 > z0 and abs(z2 - 2 * z1) < 1e-6 and abs(z3 - z1) < 1e-6 and z4 > z3) or moved > 0.6:
            problems.append(f"zooming on {view}: {z0}, {z1}, {z2}, {z3}, {z4}; the place under the pointer moved by {moved} degrees")
    page.click("#zoomreset")
    page.focus("#gl")
    page.keyboard.press("+")
    k1 = zoom()
    page.keyboard.press("-")
    page.keyboard.press("-")
    k2 = zoom()
    page.keyboard.press("0")
    turned = page.evaluate("state.lon0")
    page.keyboard.press("ArrowRight")
    turned = page.evaluate("state.lon0") - turned
    fingers = page.evaluate("""() => {
        const c = document.getElementById('gl'), b = c.getBoundingClientRect(), cx = b.left + b.width / 2, cy = b.top + b.height / 2;
        const ev = (type, id, x) => c.dispatchEvent(new PointerEvent(type, { pointerId: id, clientX: x, clientY: cy, bubbles: true, pointerType: 'touch' }));
        const z0 = state.zoom, sel = state.selected;
        ev('pointerdown', 11, cx - 50); ev('pointerdown', 12, cx + 50); ev('pointermove', 11, cx - 100); ev('pointermove', 12, cx + 100);
        const z1 = state.zoom; ev('pointerup', 11, cx - 100); ev('pointerup', 12, cx + 100);
        const g = (type, scale) => { const e = new Event(type, { bubbles: true, cancelable: true }); e.scale = scale; e.clientX = cx; e.clientY = cy; c.dispatchEvent(e); };
        g('gesturestart', 1); g('gesturechange', 1.5);
        return { z0, z1, z2: state.zoom, selected: state.selected !== sel };
    }""")
    print(f"zoom by keys: + {k1:.2f}, - - {k2:.2f}, 0 back to the whole world; the right arrow turned the globe {turned:.1f} degrees; "
          f"two fingers apart {fingers['z0']:.2f} to {fingers['z1']:.2f}, a trackpad's gesture to {fingers['z2']:.2f}")
    if not (k1 > 0.92 > k2 and turned > 0 and abs(fingers["z1"] - 2 * fingers["z0"]) < 1e-6 and abs(fingers["z2"] - 1.5 * fingers["z1"]) < 1e-6) or fingers["selected"]:
        problems.append(f"zooming by keys or fingers: {k1}, {k2}, {turned}, {fingers}")
    page.click("#zoomreset")
    # the seasons: the month's snow and rivers
    if page.evaluate("!!(state.map.flow && state.map.flow.length > 1)"):
        whole, off = page.evaluate("state.map.riverCount"), page.is_disabled("#month")
        page.check("#season")
        flows = []
        for month in ("1", "7"):
            page.fill("#month", month)
            page.dispatch_event("#month", "input")
            page.wait_for_timeout(200)
            flows.append(page.evaluate("state.map.riverCount"))
        on = page.is_enabled("#month")
        page.fill("#month", "1")                             # (while the slider still works: it is off without the seasons)
        page.dispatch_event("#month", "input")
        page.uncheck("#season")
        print(f"seasons: parts of rivers in the year's mean {whole}, in month 1 {flows[0]}, in month 7 {flows[1]}; the month's slider off before {off}, on with the seasons {on}")
        if not (off and on) or flows[0] == flows[1] or page.evaluate("state.map.riverCount") != whole:
            problems.append(f"the seasons do not change the drawing: {whole}, {flows}, slider {off}, {on}")
    page.click("#viewflat")
    settled(page)
    page.screenshot(path=str(out / "drawing_flat.png"), timeout=120000)
    page.click("#viewglobe")
    page.evaluate("() => { const m = state.map, i = m.sea.findIndex((v, k) => !v && m.height[k] > 300); "
                  "if (i >= 0) { state.lat0 = Math.asin(state.mesh.xyz[i * 3 + 2]) * 180 / Math.PI; "
                  "state.lon0 = Math.atan2(state.mesh.xyz[i * 3 + 1], state.mesh.xyz[i * 3]) * 180 / Math.PI; } state.zoom = 6; draw(); }")
    settled(page)
    page.screenshot(path=str(out / "drawing_close.png"), timeout=120000)
    page.click("#zoomreset")
    # choosing a field shows the data; the button brings the drawing back
    field = page.eval_on_selector("#field", "e => e.value")
    page.select_option("#field", field)
    page.wait_for_timeout(500)
    data = page.evaluate("state.look")
    page.click("#lookmap")
    page.wait_for_timeout(300)
    back = page.evaluate("state.look")
    settled(page)
    print(f"looks: choosing the field {field} gave the look {data!r}; the button Illustrated gave {back!r}; the scale says {page.inner_text('#scaletext')!r}")
    if data != "data" or back != "map":
        problems.append(f"the looks do not change as they should: {data!r}, {back!r}")


def check(store, out_dir, fields, query="", no_class=None):
    from playwright.sync_api import sync_playwright          # needed for this one step only: --help works without it
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    srv = make_server(store, port=0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": 1500, "height": 860})
        page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/{query}")
        page.wait_for_function("window.viewerReady === true", timeout=120000)
        print("world:", page.inner_text("#worldinfo"))
        if "field=" not in query and "look=" not in query and page.evaluate("canDraw()"):
            drawing(page, out, problems)
        names = fields or [page.eval_on_selector("#field", "e => e.value")]
        for name in names:
            page.select_option("#field", name)
            page.wait_for_timeout(700)
            page.click("#viewglobe")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / f"{name}_globe.png"))
            page.click("#viewflat")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / f"{name}_flat.png"))
        if no_class:
            page.select_option("#field", no_class)
            page.wait_for_timeout(700)
            page.click("#viewflat")
            page.wait_for_timeout(300)
            pixel = page.evaluate("() => { draw(); const px = new Uint8Array(4); gl.readPixels(Math.floor(canvas.width / 2), "
                                  "Math.floor(canvas.height / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); return Array.from(px); }")
            legend = page.inner_text("#legend")
            print(f"class code outside the list: pixel {pixel[:3]}, legend {legend!r}")
            if any(abs(a - b) > 2 for a, b in zip(pixel[:3], NO_CLASS)) or "no class" not in legend:
                problems.append(f"a class code outside the list is drawn as {pixel[:3]}, not as {NO_CLASS}, or the legend does not name it")
        fields_here = page.evaluate("() => Object.fromEntries(Object.entries(state.world.fields).map(([n, s]) => [n, s.kind]))")
        index_field = next((n for n in ("flow_receiver", "depression_id", "plate_id") if fields_here.get(n) == "index"), None)
        if index_field:
            page.select_option("#field", index_field)
            page.wait_for_timeout(700)
            page.click("#viewflat")
            box = page.locator("#gl").bounding_box()
            shown = set()
            for fx in (0.2, 0.35, 0.5, 0.65, 0.8):
                for fy in (0.3, 0.5, 0.7):
                    page.mouse.move(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
                    page.wait_for_timeout(60)
                    shown.add(page.inner_text("#status").split(" · ")[-1])
            legend = page.inner_text("#legend")
            print(f"numbers that name things ({index_field}): shown as {sorted(shown)[:8]}; legend {legend!r}")
            import re
            bad = [t for t in shown if not re.fullmatch(r"\d+|none \(-?\d+\)|no value", t)]
            if bad or "of its own" in legend:
                problems.append(f"{index_field}: shown as {bad}, which are not whole numbers; or the legend still promises a colour to each number")
        log_field = next((n for n in ("river_discharge", "snow_water", "drainage_area") if n in fields_here), None)
        if log_field and "ocean_mask" in fields_here:
            page.select_option("#field", log_field)
            page.wait_for_timeout(900)
            page.click("#viewflat")
            page.wait_for_timeout(300)
            found = page.evaluate("""async () => {
                const out = {};
                for (const [name, sea] of [["land", 0], ["sea", 1]]) {
                    let id = -1;
                    for (let i = 0; i < state.data.length; i++) if (state.data[i] === 0 && state.sea[i] === sea) { id = i; break; }
                    if (id < 0) continue;
                    const c = await getJSON("/api/cell?id=" + id);
                    draw();
                    const fit = Math.min(1, canvas.width / canvas.height / 2);
                    const x = c.lon / 180 * 2 * fit, y = c.lat / 90 * fit;
                    const px = new Uint8Array(4);
                    gl.readPixels(Math.floor((x / (canvas.width / canvas.height) + 1) / 2 * canvas.width), Math.floor((1 + y) / 2 * canvas.height),
                                  1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
                    out[name] = {id, pixel: Array.from(px).slice(0, 3), want: name === "land" ? NOTHING_ON_LAND : NOTHING_AT_SEA};
                }
                return out;
            }""")
            legend = page.inner_text("#legend")
            print(f"exactly zero on the scale of ratios ({log_field}): {found}; legend {legend!r}")
            for name, got in found.items():
                if any(abs(a - b) > 2 for a, b in zip(got["pixel"], got["want"])):
                    problems.append(f"{log_field}: a {name} cell that holds zero is drawn as {got['pixel']}, not as {got['want']}")
            if found and "exactly zero" not in legend:
                problems.append(f"{log_field}: the legend does not say how a cell that holds zero is drawn")
        # on the flat map, the place under the pointer must stay under it while the map is dragged
        page.click("#viewflat")
        box = page.locator("#gl").bounding_box()
        ax, ay = box["x"] + box["width"] * 0.40, box["y"] + box["height"] * 0.45
        bx, by = ax + 160, ay + 60
        page.mouse.move(ax, ay)
        page.wait_for_timeout(200)
        before = page.inner_text("#status").split(" · ")[0]
        page.mouse.down()
        page.mouse.move((ax + bx) / 2, (ay + by) / 2, steps=4)
        page.mouse.move(bx, by, steps=4)
        page.mouse.up()
        page.mouse.move(bx + 1, by)
        page.mouse.move(bx, by)
        page.wait_for_timeout(200)
        after = page.inner_text("#status").split(" · ")[0]
        print(f"drag on the flat map: under the pointer before {before!r}, after {after!r}")
        if before != after:
            problems.append(f"dragging the flat map moved the place under the pointer from {before} to {after}")
        page.click("#viewglobe")
        box = page.locator("#gl").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        page.wait_for_function("(() => { const t = document.querySelector('#why').innerText; return t.length > 0 && !t.includes('asking why'); })()", timeout=30000)
        print("cell:", page.inner_text("#celltitle"))
        print("why:", page.inner_text("#why")[:1500])
        print("banner:", page.inner_text("#banner") if page.is_visible("#banner") else "none")
        if page.is_enabled("#play"):
            page.click("#play")
            page.wait_for_timeout(2400)
            print("month after playing:", page.inner_text("#monthlabel"))
            page.click("#play")
        page.screenshot(path=str(out / "cell_panel.png"))
        print("status:", page.inner_text("#status"))
        browser.close()
    srv.shutdown()
    print("page errors:", problems or "none")
    return 1 if problems else 0


def parser():
    p = console.tool_parser(__doc__, "python tools/viewer_check.py")
    p.add_argument("store", metavar="STORE")
    p.add_argument("out_dir", metavar="OUT_DIR")
    p.add_argument("fields", nargs="*", metavar="field", help="a field to show; an entry that begins with ? is the page's query instead")
    p.add_argument("--no-class", default=None, metavar="FIELD")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    if not Path(args.store).exists():
        print(f"no world store at {args.store}", file=sys.stderr)
        return 2
    queries = [a for a in args.fields if a.startswith("?")]
    if len(queries) > 1:
        print(f"one query at most, not {len(queries)}: {' '.join(queries)}", file=sys.stderr)
        return 2
    return check(args.store, args.out_dir, [a for a in args.fields if not a.startswith("?")], queries[0] if queries else "", args.no_class)


if __name__ == "__main__":
    sys.exit(main())
