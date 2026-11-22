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
    scripts = re.findall(r'<script src="([^"]+)"', page)
    assert scripts[0] == "draw.js" and scripts[-1] == "viewer.js"                               # viewer.js starts the page: all it uses is defined before it
    assert sorted(scripts) == sorted(p.name for p in VIEWER.glob("*.js"))                       # every script of the folder, and none that is not there
    used = set().union(*(re.findall(r'\$\("([^"]+)"\)', (VIEWER / name).read_text(encoding="utf-8")) for name in scripts))
    assert used and not (used - ids), used - ids
    css = (VIEWER / "style.css").read_text(encoding="utf-8")
    assert not (set(re.findall(r"#([a-z]+)\b(?=[^{}]*\{)", css)) - ids - {"fff"})               # no rule for a part that is gone


# ---------------------------------------------------------------------------------------------- the atlas (viewer/atlas.js)
def atlas_js(expression, **given):
    """The value of a JavaScript expression that may use everything draw.js and atlas.js define, and `given`."""
    run = ("const fs = require('fs'), vm = require('vm'), ctx = vm.createContext({});"
           "for (const f of process.argv.slice(2, -1)) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx);"
           "ctx.given = JSON.parse(fs.readFileSync(0, 'utf8'));"
           "process.stdout.write(JSON.stringify(vm.runInContext(process.argv[process.argv.length - 1], ctx)));")
    r = subprocess.run([NODE, "-e", run, str(VIEWER / "draw.js"), str(VIEWER / "atlas.js"), expression], input=json.dumps(given),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def toy_world(m):
    """On a mesh of 642 cells: a land of the cells within 50 degrees of one place, with a ring of highland in it and a
    lake, a speck of land of one cell off its coast, and a river from the highland down to the sea; sea everywhere else."""
    centre = np.array([1.0, 0.0, 0.0])
    off = np.degrees(np.arccos(np.clip(m.xyz @ centre, -1, 1)))
    island = int(np.argmin(np.abs(off - 70) + 50 * (m.xyz[:, 1] > -0.3)))
    sea = (off > 50).astype(int)
    sea[island] = 0
    height = np.where(sea == 1, -4000.0, 300.0)
    height[(off > 10) & (off < 18)] = 1800.0
    lake = np.zeros(m.n, int)
    lake[int(np.argmin(off))] = 1
    recv, flow = np.full(m.n, -1), np.zeros(m.n)
    path = [int(np.argmin(np.abs(off - a) + 50 * (np.abs(m.xyz[:, 2]) > 0.2) + 50 * (m.xyz[:, 1] < 0))) for a in (14, 24, 34, 44, 49, 56)]
    for k, (a, b) in enumerate(zip(path, path[1:])):
        recv[a] = b
        flow[a] = 1000.0 * (k + 1)
    return {"n": m.n, "xyz": m.xyz.ravel().tolist(), "nbr": m.nbr.ravel().tolist(), "sea": sea.tolist(), "height": height.tolist(),
            "recv": recv.tolist(), "flow": flow.tolist(), "lake": lake.tolist()}, path, island


@needs_node
def test_the_atlas_finds_the_worlds_own_features():
    m = get_mesh(3)
    world, path, island = toy_world(m)
    feats = atlas_js("Atlas.features({...given, xyz: Float32Array.from(given.xyz), nbr: Int32Array.from(given.nbr)})"
                     ".map((f) => ({kind: f.kind, size: f.size, cells: f.cells, anchor: f.anchor, rank: f.rank, path: f.path, along: f.along}))", **world)
    kinds = [f["kind"] for f in feats]
    land = next(f for f in feats if f["kind"] == "continent")
    sea = np.array(world["sea"])
    assert land["size"] == int((sea == 0).sum()) - 1 and all(sea[c] == 0 for c in land["cells"])        # the land without the speck far off
    assert "island" not in kinds                                                                          # one cell is no island (fewer than 3)
    assert kinds.count("range") == 1 and kinds.count("lake") == 1 and kinds.count("ocean") + kinds.count("sea") == 1   # (an ocean from 300 cells)
    high = next(f for f in feats if f["kind"] == "range")
    assert all(world["height"][c] >= 1500 for c in high["cells"]) and high["along"] > 0
    river = next(f for f in feats if f["kind"] == "river")
    mouth = next(c for c, after in zip(path, path[1:]) if sea[c] == 0 and sea[after] == 1)
    up = path[:path.index(mouth) + 1][::-1]                                                              # from the mouth up the toy river,
    up = [c for k, c in enumerate(up) if all(world["flow"][q] >= 0.25 * world["flow"][mouth] for q in up[:k + 1])]   # while the flow holds
    assert river["path"] == up and len(up) >= 4
    ocean = next(f for f in feats if f["kind"] in ("ocean", "sea"))
    assert all(sea[c] == 1 for c in ocean["cells"]) and land["anchor"] in land["cells"]
    assert [f["rank"] for f in feats if f["kind"] == "continent"] == [0]


@needs_node
def test_the_invented_names_are_the_same_for_the_same_seed_and_none_is_used_twice():
    m = get_mesh(3)
    world, _, _ = toy_world(m)
    expr = ("(() => { const f = Atlas.features({...given, xyz: Float32Array.from(given.xyz), nbr: Int32Array.from(given.nbr)});"
            " const a = Atlas.names(given.seed, f), b = Atlas.names(given.seed, f), c = Atlas.names(given.seed + 1, f);"
            " return { a: [a.world, ...a.of.values()], b: [b.world, ...b.of.values()], c: [c.world, ...c.of.values()], kinds: f.map((x) => x.kind) }; })()")
    got = atlas_js(expr, **world, seed=20261004)
    assert got["a"] == got["b"] and got["a"] != got["c"]
    words = [n.split()[-1] if n.split()[0] in ("the", "Lake", "River", "Isle", "Sea") else n.split()[0] for n in got["a"][1:]]
    assert len(set(words)) == len(words) and all(re.fullmatch(r"[A-Z][a-z]{2,12}", w) for w in [got["a"][0], *words])
    for kind, name in zip(got["kinds"], got["a"][1:]):
        assert {"ocean": "Ocean", "range": ("Mountains", "Range", "Heights"), "lake": ("Lake", "Water", "Mere"),
                "river": ("River", "the ")}[kind] if kind in ("ocean",) else True
        if kind == "ocean":
            assert "Ocean" in name
        if kind == "lake":
            assert any(w in name for w in ("Lake", "Water", "Mere"))
        if kind == "range":
            assert any(w in name for w in ("Mountains", "Range", "Heights"))


@needs_node
def test_the_magic_layers_marks_are_lines_not_nets():
    """Plate lines as a tree through their cells (each cell joined once), river lines along the water's way, the
    nexus cells, and the wellsprings with their mana among the wellsprings'."""
    m = get_mesh(3)
    a = int(np.argmax(m.xyz[:, 0]))
    band = sorted({a, *[int(j) for j in m.nbr[a] if j >= 0]})                          # seven cells: a dense blob
    river = [int(np.argmax(m.xyz[:, 1]))]
    river.append(int(next(j for j in m.nbr[river[0]] if j >= 0)))
    recv = [-1] * m.n
    recv[river[0]] = river[1]
    ley = [0] * m.n
    for c in band:
        ley[c] = 1
    for c in river:
        ley[c] = 2
    nexus = int(next(j for c in band for j in m.nbr[c] if j >= 0 and j not in band and j not in river))
    ley[nexus] = 3
    aura = [0] * m.n
    aura[band[0]], aura[river[0]] = 1, 1
    density = [0.0] * m.n
    density[band[0]], density[river[0]] = 2.0, 8.0
    got = atlas_js("Atlas.magicMarks(given.n, Int32Array.from(given.nbr), given.recv, given.ley, ['none', 'plate_line', 'river_line', 'nexus'],"
                   " given.aura, ['faint', 'wellspring'], given.density)", n=m.n, nbr=m.nbr.ravel().tolist(), recv=recv, ley=ley, aura=aura, density=density)
    tree = got["plate"]
    joined = {c for e in tree for c in e}
    assert len(tree) == len(joined) - 1 == len(band)                                   # a tree over the band and the nexus: no triangle
    assert got["river"] == [[river[0], river[1]]] and got["nexus"] == [nexus]
    assert sorted(got["springs"]) == sorted([[band[0], 0.25], [river[0], 1.0]])


@needs_node
def test_a_river_is_not_drawn_across_a_lake_and_only_the_main_stem_swells():
    m = get_mesh(3)
    a = 100
    b = int(m.nbr[a][0])
    side = int(next(j for j in m.nbr[b] if j >= 0 and j != a))
    c = int(next(j for j in m.nbr[b] if j >= 0 and j not in (a, side)))
    recv, flow, sea, lake = [-1] * m.n, [0.0] * m.n, [0] * m.n, [0] * m.n
    recv[a], recv[side], recv[b] = b, b, c
    flow[a], flow[side], flow[b] = 30.0, 10.0, 50.0
    xyz = m.xyz.astype(np.float32).ravel().tolist()
    parts = np.array(draw_js("Array.from(riverParts(Float32Array.from(given.xyz), Int32Array.from(given.recv), Float32Array.from(given.flow), given.sea, 50, given.lake))",
                             xyz=xyz, recv=recv, flow=flow, sea=sea, lake=lake)).reshape(-1, 8)
    each = draw_js("DRAWING.riverParts")

    def way(parts, frm):                                       # the parts of the way from a cell: they start at its centre
        k = next(k for k in range(0, len(parts), each) if np.allclose(parts[k][0:3], m.xyz[frm], atol=1e-5))
        return parts[k:k + each]
    assert np.allclose(way(parts, a)[-1][3:6], m.xyz[b], atol=1e-5) and np.allclose(way(parts, side)[-1][3:6], m.xyz[b], atol=1e-5)
    assert np.isclose(way(parts, a)[-1][7], 1.0) and np.isclose(way(parts, side)[-1][7], 10 / 50)   # the main stem swells to the join's flow; a side river does not
    lake[b] = lake[c] = 1
    across = np.array(draw_js("Array.from(riverParts(Float32Array.from(given.xyz), Int32Array.from(given.recv), Float32Array.from(given.flow), given.sea, 50, given.lake))",
                              xyz=xyz, recv=recv, flow=flow, sea=sea, lake=lake)).reshape(-1, 8)
    assert not any(np.allclose(p[3:6], m.xyz[c], atol=1e-5) for p in across)          # nothing drawn from b to c: both are lake
