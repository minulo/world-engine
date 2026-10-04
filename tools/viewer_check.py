"""Open the viewer on a world store in a headless browser and save screenshots.

A development tool, not part of the engine. It needs the Python package playwright and a Chromium.
    python tools/viewer_check.py STORE OUT_DIR [field ...] ["?lat=48&lon=-20&month=7"] [--no-class=FIELD]
For each field it saves a globe view and a flat view, then clicks the middle of the globe and
saves the page with the cell panel filled in. It prints what the page reported.
With --no-class=FIELD it also checks that a class field whose every cell holds a code outside
its list is drawn in the colour kept for such codes, and not in the colour of a class.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright          # noqa: E402

from worldengine.server import make_server                # noqa: E402


NO_CLASS = [217, 26, 191]       # as in viewer.js


def main(store, out_dir, fields, query="", no_class=None):
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
        page.wait_for_function("document.querySelector('#why').innerText.length > 0", timeout=30000)
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


if __name__ == "__main__":
    args = [a for a in sys.argv[3:] if not a.startswith("?") and not a.startswith("--no-class=")]
    sys.exit(main(sys.argv[1], sys.argv[2], args, next((a for a in sys.argv[3:] if a.startswith("?")), ""),
                  next((a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--no-class=")), None)))
