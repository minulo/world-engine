"""The viewer's drawing: the arithmetic of viewer/draw.js that prepares a world for the shaders (run with node, where
there is one), and that the page, its scripts and the server agree on their names. What the shaders themselves draw is
checked in a browser by tools/viewer_check.py, which no workflow runs."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from worldengine.mesh import get_mesh

VIEWER = Path(__file__).resolve().parents[1] / "viewer"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")
RUN = ("const fs = require('fs'), vm = require('vm'), ctx = vm.createContext({});"
       "vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);"
       "ctx.given = JSON.parse(fs.readFileSync(0, 'utf8'));"
       "process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], ctx)));")


def draw_js(expression, **given):
    """The value of a JavaScript expression that may use everything draw.js defines, and `given`."""
    r = subprocess.run([NODE, "-e", RUN, str(VIEWER / "draw.js"), expression], input=json.dumps(given), capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def mesh():
    m = get_mesh(3)
    return m, m.xyz.astype(np.float32).ravel().tolist(), m.nbr.astype(np.int32).ravel().tolist()


@needs_node
def test_the_spacing_of_the_cells_is_that_of_the_mesh(mesh):
    m, xyz, nbr = mesh
    h = np.array(draw_js("Array.from(cellSpacing(Float32Array.from(given.xyz), Int32Array.from(given.nbr)))", xyz=xyz, nbr=nbr))
    even = np.sqrt(2.0 / np.sqrt(3.0) * 4.0 * np.pi / m.n)           # the spacing of six-sided cells of the mean area
    assert h.shape == (m.n,) and abs(h.mean() / even - 1.0) < 0.03 and 0.75 * even < h.min() and h.max() < 1.25 * even


@needs_node
def test_the_slope_of_a_field_that_rises_northward_points_north_with_the_right_size(mesh):
    """A height of 1000 m times the sine of the latitude rises 1000 m to the radian times the cosine, due north."""
    m, xyz, nbr = mesh
    value = (1000.0 * m.xyz[:, 2]).tolist()
    g = np.array(draw_js("Array.from(cellGradients(Float32Array.from(given.xyz), Int32Array.from(given.nbr), Float32Array.from(given.value)))",
                         xyz=xyz, nbr=nbr, value=value)).reshape(-1, 3)
    north = np.array([0.0, 0.0, 1.0]) - m.xyz * m.xyz[:, 2:3]         # the part of "up the axis" that lies along the ground
    want = 1000.0 * north
    assert np.linalg.norm(g - want, axis=1).max() < 30.0              # within 3 % of the largest slope, at every cell
    assert np.abs(np.einsum("ij,ij->i", g, m.xyz)).max() < 1e-3       # along the ground: no part points up


@needs_node
def test_a_river_is_drawn_from_cell_to_cell_and_widens_with_its_flow(mesh):
    m, xyz, nbr = mesh
    a = 100
    b = int(m.nbr[a][0])
    c = int(next(j for j in m.nbr[b] if j >= 0 and j != a and j not in m.nbr[a]))
    d = int(next(j for j in m.nbr[c] if j >= 0 and j not in (a, b) and j not in m.nbr[b]))
    low = int(next(j for j in m.nbr[a] if j >= 0 and j != b))        # a trickle into a, too small to draw
    recv, flow, sea = [-1] * m.n, [0.0] * m.n, [0] * m.n
    recv[a], recv[b], recv[c], recv[low] = b, c, d, a
    flow[a], flow[b], flow[c], flow[low], sea[d] = 10.0, 30.0, 60.0, 0.1, 1
    got = draw_js("({ parts: Array.from(riverParts(Float32Array.from(given.xyz), Int32Array.from(given.recv), Float32Array.from(given.flow), given.sea, 60)),"
                  " each: DRAWING.riverParts, floor: DRAWING.riverFloor })", xyz=xyz, recv=recv, flow=flow, sea=sea)
    each, parts = got["each"], np.array(got["parts"]).reshape(-1, 8)
    assert parts.shape[0] == 3 * each and 0.1 < got["floor"] * 60                              # a, b and c; not the trickle, not the sea
    starts, ends, q = parts[:, 0:3], parts[:, 3:6], parts[:, 6:8]
    assert np.allclose(np.linalg.norm(starts, axis=1), 1.0, atol=1e-5) and np.allclose(np.linalg.norm(ends, axis=1), 1.0, atol=1e-5)
    ways = {}
    for frm, to in ((a, b), (b, c), (c, d)):                                                   # each way runs whole from centre to centre
        k = next(k for k in range(0, 3 * each, each) if np.allclose(starts[k], m.xyz[frm], atol=1e-5))
        way = ways[frm] = slice(k, k + each)
        assert np.allclose(ends[way][-1], m.xyz[to], atol=1e-5) and np.allclose(starts[way][1:], ends[way][:-1], atol=1e-6)
        assert np.all(np.diff(q[way].ravel()) >= -1e-9)                                        # never narrower downstream
    assert np.isclose(q[ways[a]][0, 0], 0.12 * 10 / 60) and np.isclose(q[ways[a]][-1, 1], 30 / 60)   # a spring starts as a thread
    assert np.isclose(q[ways[b]][0, 0], 30 / 60) and np.isclose(q[ways[b]][-1, 1], 1.0)        # the same width where two ways meet
    assert np.isclose(q[ways[c]][0, 0], 1.0) and np.isclose(q[ways[c]][-1, 1], 1.0)            # into the sea with its own flow


@needs_node
def test_the_drawings_colours_and_signs_by_biome():
    got = draw_js("({ c: drawnBiomeColours(['taiga', 'hot_desert', 'a_biome_of_another_list', 'ice'], ['#000000', '#000000', '#ff0000', '#000000']),"
                  " p: [percentile([5, 1, 4, 2, 3], 50), percentile([NaN, 7], 99.5), percentile([], 50)], names: SIGN_NAMES.length })")
    taiga, desert, other, ice = got["c"]
    assert taiga[3] == 2 and desert[3] == 5 and other[3] == 0 and ice[3] == 0                  # a conifer, sand, no sign, none on ice
    assert other[:3] == [round(0.62 * 255 + 0.38 * 236), round(0.38 * 228), round(0.38 * 209)]  # the engine's red, paled toward the paper
    assert taiga[:3] != [0, 0, 0] and got["p"] == [3, 7, 0] and got["names"] == 7


@needs_node
def test_the_shaders_are_whole_texts_with_the_viewers_colours_in_them():
    got = draw_js("({ data: dataShader([217, 26, 191], [115, 115, 115], [70, 86, 108], [176, 166, 148]), map: FS_MAP, river: [VS_RIVER, FS_RIVER], width: DATA_W })")
    for text in (got["data"], got["map"], *got["river"]):
        assert text.startswith("#version 300 es\n") and "void main()" in text and "undefined" not in text and "NaN" not in text
    assert "vec3(0.851, 0.102, 0.749)" in got["data"] and f"const int DW = {got['width']};" in got["map"]
    # a word GLSL keeps for itself, used as a name, stops the shader from compiling in every browser (found here: "cast")
    kept = {"cast", "flat", "smooth", "input", "output", "filter", "sample", "common", "partition", "active", "half", "fixed", "namespace", "using",
            "class", "union", "enum", "template", "this", "goto", "inline", "public", "static", "extern", "interface", "long", "short", "double"}
    for text in (got["data"], got["map"], *got["river"]):
        code = re.sub(r"//[^\n]*", "", text)
        named = set(re.findall(r"\b(?:float|int|bool|vec[234]|ivec[234]|uvec[234]|mat3)\s+([A-Za-z_]\w*)", code))
        named |= {n.strip() for group in re.findall(r"\b(?:float|int|vec[234])\s+([^;()]*);", code) for n in re.split(r",", re.sub(r"=[^,]*", "", group))}
        assert not (named & kept), named & kept


def test_the_page_holds_everything_its_scripts_reach_for():
    page = (VIEWER / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', page))
    used = set(re.findall(r'\$\("([^"]+)"\)', (VIEWER / "viewer.js").read_text(encoding="utf-8")))
    assert used and not (used - ids), used - ids
    assert page.index('src="draw.js"') < page.index('src="viewer.js"')                         # viewer.js uses what draw.js defines
    css = (VIEWER / "style.css").read_text(encoding="utf-8")
    assert not (set(re.findall(r"#([a-z]+)\b(?=[^{}]*\{)", css)) - ids - {"fff"})               # no rule for a part that is gone
