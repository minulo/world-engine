"""Open the viewer on a world store in a headless browser and save screenshots.

A development tool, not part of the engine. It needs the Python package playwright and a Chromium.
    python tools/viewer_check.py STORE OUT_DIR [field ...]
For each field it saves a globe view and a flat view, then clicks the middle of the globe and
saves the page with the cell panel filled in. It prints what the page reported.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from playwright.sync_api import sync_playwright          # noqa: E402

from worldengine.server import make_server                # noqa: E402


def main(store, out_dir, fields):
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
        page.goto(f"http://127.0.0.1:{port}/")
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
        page.click("#viewglobe")
        box = page.locator("#gl").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.42)
        page.wait_for_timeout(1200)
        print("cell:", page.inner_text("#celltitle"))
        print("why:", page.inner_text("#why")[:900])
        page.screenshot(path=str(out / "cell_panel.png"))
        print("status:", page.inner_text("#status"))
        browser.close()
    srv.shutdown()
    print("page errors:", problems or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
