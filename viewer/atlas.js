// The atlas: what the sheet over the map (overlay.js) letters and adorns in the illustrated look.
//
//   * Names. The world stores none, so the names are made up here from the world's seed, in a language that is also
//     made up from it: the same world always gets the same names, and another world other ones. The THINGS named are
//     the world's own: its lands (connected land cells), its open seas (sea cells eight or more cells from any land),
//     its highlands (connected land above 1,500 m), its largest rivers (traced up from their mouths along the
//     largest flow) and its lakes. The page says that the names are invented.
//   * The magic layer, on a world that carries the invented fantasy layer "magic": its ley lines, the places where
//     they cross (nexus) and its wellsprings, from the layer's own fields. Invented, as the layer is.
//   * A compass rose and a cartouche with the world's name.
//
// The first half of this file is plain arithmetic on the world's arrays, with no page in it (tests/test_viewer_draw.py
// runs it with node); the second half draws, and needs the page, its state and the sheet.
"use strict";

const Atlas = (() => {
  // ---------------------------------------------------------------- the world's features
  const RULES = {
    landLeast: 3,           // a land of fewer cells gets no name
    continentLeast: 100,    // a land of this many cells or more is lettered as a continent
    openSea: 8,             // a sea cell this many cells from any land or more belongs to an open sea
    oceanLeast: 100,        // an open sea of fewer cells gets no name
    oceanBig: 300,          // an open sea of this many cells or more is an ocean, else a sea
    highM: 1500,            // highlands: connected land at least this high (metres above the sea)
    highLeast: 4,           // highlands of fewer cells get no name
    riverShare: 0.05,       // a river is named if the flow at its mouth is at least this share of the largest mouth's
    riverUp: 0.25,          // its name runs up the main stem while the flow is at least this share of the mouth's
    riverLeast: 4,          // a river whose named stretch has fewer cells gets no name
  };

  // The connected groups of cells for which inside(i) holds (through the mesh's neighbours), the largest first.
  function components(n, nbr, inside) {
    const label = new Int32Array(n).fill(-1), out = [];
    for (let s = 0; s < n; s++) {
      if (label[s] >= 0 || !inside(s)) continue;
      const cells = [s]; label[s] = out.length;
      for (let k = 0; k < cells.length; k++) {
        const c = cells[k];
        for (let e = 0; e < 6; e++) { const j = nbr[c * 6 + e]; if (j >= 0 && label[j] < 0 && inside(j)) { label[j] = out.length; cells.push(j); } }
      }
      out.push(cells.sort((a, b) => a - b));
    }
    return out.sort((a, b) => b.length - a.length || a[0] - b[0]);
  }
  // How many steps from cell to neighbouring cell each cell lies from the nearest cell for which from(i) holds.
  function steps(n, nbr, from) {
    const d = new Int32Array(n).fill(-1), queue = [];
    for (let i = 0; i < n; i++) if (from(i)) { d[i] = 0; queue.push(i); }
    for (let k = 0; k < queue.length; k++) {
      const c = queue[k];
      for (let e = 0; e < 6; e++) { const j = nbr[c * 6 + e]; if (j >= 0 && d[j] < 0) { d[j] = d[c] + 1; queue.push(j); } }
    }
    return d;
  }
  const unit = (v) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const at = (xyz, i) => [xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2]];
  // The shape of a group of cells seen from its anchor cell: the direction along the ground in which it is longest
  // (axis) and how far it reaches along it and across (radians, two standard deviations).
  function shape(cells, xyz, anchor) {
    const c = at(xyz, anchor), up = Math.abs(c[2]) < 0.95 ? [0, 0, 1] : [1, 0, 0];
    const e1 = unit(cross(up, c)), e2 = cross(c, e1);
    let sxx = 0, sxy = 0, syy = 0, mx = 0, my = 0;
    for (const i of cells) { const p = at(xyz, i), x = dot(p, e1), y = dot(p, e2); mx += x; my += y; sxx += x * x; sxy += x * y; syy += y * y; }
    const k = cells.length; mx /= k; my /= k; sxx = sxx / k - mx * mx; sxy = sxy / k - mx * my; syy = syy / k - my * my;
    const t = 0.5 * Math.atan2(2 * sxy, sxx - syy), tr = (sxx + syy) / 2, det = Math.sqrt(((sxx - syy) / 2) ** 2 + sxy * sxy);
    const axis = [0, 1, 2].map((q) => Math.cos(t) * e1[q] + Math.sin(t) * e2[q]);
    return { centre: c, axis, along: 2 * Math.sqrt(Math.max(tr + det, 0)), across: 2 * Math.sqrt(Math.max(tr - det, 0)) };
  }
  // The cell of a group that lies furthest inside it (most steps from any cell outside it); of two, the lower number.
  function innermost(n, nbr, cells) {
    const mine = new Uint8Array(n); for (const i of cells) mine[i] = 1;
    const d = steps(n, nbr, (i) => !mine[i]);
    let best = cells[0]; for (const i of cells) if (d[i] > d[best]) best = i;
    return best;
  }

  // The features of a world worth a name. world: { n, xyz, nbr, sea, height, recv, flow, lake } (arrays, one value a
  // cell: sea and lake 1 or 0; height in metres above the sea, below it as less than nothing; recv the cell a cell's
  // water runs to, -1 for none; flow the year's mean river flow, m3/s). Each feature: { kind, key, cells, anchor,
  // size, rank, ... } where key is stable for the same world, and the larger the size the sooner it is shown.
  function features(world) {
    const { n, xyz, nbr, sea, height, recv, flow, lake } = world, out = [];
    const isSea = (i) => sea[i] > 0.5;
    for (const cells of components(n, nbr, (i) => !isSea(i))) {
      if (cells.length < RULES.landLeast) continue;
      const anchor = innermost(n, nbr, cells);
      out.push({ kind: cells.length >= RULES.continentLeast ? "continent" : "island", key: `land:${cells[0]}`, cells, anchor, size: cells.length, ...shape(cells, xyz, anchor) });
    }
    const fromLand = steps(n, nbr, (i) => !isSea(i));
    for (const cells of components(n, nbr, (i) => isSea(i) && fromLand[i] >= RULES.openSea)) {
      if (cells.length < RULES.oceanLeast) continue;
      let anchor = cells[0]; for (const i of cells) if (fromLand[i] > fromLand[anchor]) anchor = i;
      out.push({ kind: cells.length >= RULES.oceanBig ? "ocean" : "sea", key: `sea:${cells[0]}`, cells, anchor, size: cells.length, ...shape(cells, xyz, anchor) });
    }
    for (const cells of components(n, nbr, (i) => !isSea(i) && height[i] >= RULES.highM)) {
      if (cells.length < RULES.highLeast) continue;
      const anchor = innermost(n, nbr, cells);
      out.push({ kind: "range", key: `high:${cells[0]}`, cells, anchor, size: cells.length, ...shape(cells, xyz, anchor) });
    }
    if (lake) for (const cells of components(n, nbr, (i) => lake[i] > 0.5 && !isSea(i))) {
      const anchor = innermost(n, nbr, cells);
      out.push({ kind: "lake", key: `lake:${cells[0]}`, cells, anchor, size: cells.length, ...shape(cells, xyz, anchor) });
    }
    if (recv && flow) out.push(...rivers(world));
    const order = ["continent", "ocean", "sea", "range", "island", "river", "lake"];
    out.sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || b.size - a.size || (a.key < b.key ? -1 : 1));
    const seen = {}; for (const f of out) f.rank = seen[f.kind] = (seen[f.kind] ?? -1) + 1;
    return out;
  }
  // The largest rivers: from each mouth (a cell of land whose water runs into the sea), up the main stem (the donor
  // with the most flow) while the flow is at least a share of the mouth's. Each with its path, from mouth to source.
  function rivers(world) {
    const { n, sea, recv, flow, lake } = world, donors = Array.from({ length: n }, () => []);
    for (let i = 0; i < n; i++) if (!(sea[i] > 0.5) && recv[i] >= 0) donors[recv[i]].push(i);
    const mouths = [];
    for (let i = 0; i < n; i++) if (!(sea[i] > 0.5) && recv[i] >= 0 && sea[recv[i]] > 0.5) mouths.push(i);
    const top = mouths.reduce((m, i) => Math.max(m, flow[i]), 0), out = [];
    for (const mouth of mouths) {
      if (!(flow[mouth] >= RULES.riverShare * top) || top <= 0) continue;
      const path = [mouth];
      for (let c = mouth; path.length < n;) {
        let next = -1; for (const d of donors[c]) if (next < 0 || flow[d] > flow[next] || (flow[d] === flow[next] && d < next)) next = d;
        if (next < 0 || flow[next] < RULES.riverUp * flow[mouth]) break;
        path.push(next); c = next;
      }
      const dry = path.filter((i) => !(lake && lake[i] > 0.5));
      if (dry.length < RULES.riverLeast) continue;
      out.push({ kind: "river", key: `river:${mouth}`, cells: path, anchor: path[Math.floor(path.length / 2)], size: flow[mouth], path });
    }
    return out;
  }

  // ---------------------------------------------------------------- names, made up from the seed
  function hashText(text) { let h = 2166136261; for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function random(seed) {                    // a stream of numbers from 0 to 1, the same for the same seed (mulberry32)
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  // A language: which sounds it has, chosen from the seed; and a way to make words of them.
  function language(seed) {
    const r = random(hashText(`language:${seed}`));
    const some = (from, k) => { const pool = from.slice(), got = []; while (got.length < k && pool.length) got.push(pool.splice(Math.floor(r() * pool.length), 1)[0]); return got; };
    const onsets = some(["b", "c", "d", "f", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "z", "th", "sh", "br", "dr", "kr", "tr", "gr", "st", "vr", "sk", "gl", "fr"], 13);
    const vowels = some(["a", "e", "i", "o", "u", "a", "e", "ae", "ai", "ei", "ou", "ia", "y"], 6);
    const codas = ["", "", "", ...some(["n", "r", "l", "s", "th", "nd", "rn", "sk", "m", "ld", "x"], 5)];
    return (rr) => {
      const parts = 2 + (rr() < 0.3 ? 1 : 0);
      let w = "";
      for (let k = 0; k < parts; k++) {
        const pick = (list) => list[Math.floor(rr() * list.length)];
        w += (k === 0 || rr() < 0.75 ? pick(onsets) : "") + pick(vowels) + (k === parts - 1 || rr() < 0.25 ? pick(codas) : "");
      }
      w = w.replace(/(.)\1\1+/g, "$1$1").slice(0, 11);
      return w.charAt(0).toUpperCase() + w.slice(1);
    };
  }
  // A name for each feature, and one for the world; the same seed gives the same names, and no two features share one.
  function names(seed, feats) {
    const word = language(seed), used = new Set(), out = new Map();
    const fresh = (key) => { const r = random(hashText(`${seed}:${key}`)); for (let k = 0; k < 20; k++) { const w = word(r); if (!used.has(w)) { used.add(w); return [w, r]; } } return [word(r) + "a", r]; };
    const [worldName] = fresh("world");
    for (const f of feats) {
      const [w, r] = fresh(f.key), pick = (list) => list[Math.floor(r() * list.length)];
      out.set(f.key, {
        continent: w, island: pick([`${w} Island`, `Isle of ${w}`, `${w} Isle`]),
        ocean: pick([`${w} Ocean`, `the ${w} Ocean`]), sea: pick([`${w} Sea`, `Sea of ${w}`]),
        range: pick([`the ${w} Mountains`, `${w} Range`, `the ${w} Heights`]), river: pick([`${w} River`, `River ${w}`, `the ${w}`]),
        lake: pick([`Lake ${w}`, `${w} Water`, `${w} Mere`]),
      }[f.kind]);
    }
    return { world: worldName, of: out };
  }

  // ---------------------------------------------------------------- drawing
  const SERIF = `"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif`;
  const STYLE = {          // each kind's lettering: size from the smallest to the largest of its kind, spacing in ems
    continent: { size: [15, 25], weight: 600, upper: true, spacing: 0.32, colour: "#3a2d24" },
    island: { size: [10, 13], weight: 600, upper: true, spacing: 0.16, colour: "#3a2d24" },
    ocean: { size: [15, 21], italic: true, upper: true, spacing: 0.38, colour: "#2b5d76" },
    sea: { size: [12, 15], italic: true, upper: true, spacing: 0.28, colour: "#2b5d76" },
    range: { size: [9, 12], weight: 600, upper: true, spacing: 0.3, colour: "#5a4433" },
    river: { size: [10, 12], italic: true, spacing: 0.04, colour: "#1f5a78" },
    lake: { size: [9, 11], italic: true, spacing: 0.04, colour: "#1f5a78" },
  };
  const HALO = "rgba(244, 238, 222, 0.88)";
  const placed = [];                        // the names lettered in the last drawing (for tools/viewer_check.py)
  let prepared = null;                       // { key, feats, names }: for the world and map that are shown
  const show = { names: true, magic: false };
  let magic = null;                          // the magic layer's marks, once asked for: { lines, nexus, springs }

  function prepare(state) {
    const m = state.map, key = state.world.seed + ":" + state.world.meta.cells;
    if (prepared && prepared.key === key) return prepared;
    const n = state.world.meta.cells, mesh = state.mesh;
    const feats = features({ n, xyz: mesh.xyz, nbr: mesh.nbr, sea: m.sea, height: m.height, recv: m.recv, flow: m.flowYear, lake: m.lake });
    const sizes = {};
    for (const f of feats) (sizes[f.kind] = sizes[f.kind] || []).push(f.size);
    for (const f of feats) {                 // the place of each among its kind, 0 the smallest to 1 the largest, on a log scale
      const s = sizes[f.kind], lo = Math.log(Math.min(...s)), hi = Math.log(Math.max(...s));
      f.weight = hi > lo ? (Math.log(f.size) - lo) / (hi - lo) : 1;
    }
    prepared = { key, feats, names: names(state.world.seed, feats) };
    return prepared;
  }
  function fontOf(st, size) { return `${st.italic ? "italic " : ""}${st.weight || 400} ${size}px ${SERIF}`; }
  // The places of each letter of a text laid along a run of the sheet, centred on the run's middle, or null where the
  // run is too short. Glyphs: [{ ch, x, y, angle, r }].
  function along(c, text, size, spacing, run) {
    const m = Overlay.measured(run), widths = [...text].map((ch) => c.measureText(ch).width + spacing * size);
    const total = widths.reduce((a, b) => a + b, 0) - spacing * size;
    if (total > m.length) return null;
    let s = (m.length - total) / 2; const out = [];
    for (const [k, ch] of [...text].entries()) { const p = m.at(s + widths[k] / 2 - spacing * size / 2); out.push({ ch, x: p[0], y: p[1], angle: p[2], r: size * 0.55 }); s += widths[k]; }
    return out;
  }
  function straight(c, text, size, spacing, x, y, angle) {
    const widths = [...text].map((ch) => c.measureText(ch).width + spacing * size), total = widths.reduce((a, b) => a + b, 0) - spacing * size;
    let s = -total / 2; const out = [], ca = Math.cos(angle), sa = Math.sin(angle);
    for (const [k, ch] of [...text].entries()) { const d = s + widths[k] / 2 - spacing * size / 2; out.push({ ch, x: x + ca * d, y: y + sa * d, angle, r: size * 0.55 }); s += widths[k]; }
    return { glyphs: out, width: total };
  }
  function free(glyphs, taken, v) {
    let off = 0;
    for (const g of glyphs) {
      if (g.x < 4 || g.y < 4 || g.x > v.W - 4 || g.y > v.H - 4) off++;
      for (const t of taken) if ((g.x - t.x) ** 2 + (g.y - t.y) ** 2 < (g.r + t.r) ** 2) return false;
    }
    return off === 0;
  }
  function letter(c, glyphs, st, size) {
    c.font = fontOf(st, size); c.textAlign = "center"; c.textBaseline = "middle"; c.lineJoin = "round";
    for (const pass of [0, 1]) for (const g of glyphs) {
      c.save(); c.translate(g.x, g.y); c.rotate(g.angle);
      if (pass === 0) { c.strokeStyle = HALO; c.lineWidth = Math.max(2.5, size * 0.22); c.strokeText(g.ch, 0, 0); }
      else { c.fillStyle = st.colour; c.fillText(g.ch, 0, 0); }
      c.restore();
    }
  }
  // The screen angle of a direction along the ground at a place, and whether the place is in view.
  function onSheet(v, p, dir) {
    const a = Overlay.project(v, p), b = Overlay.project(v, unit(p.map((x, q) => x + 0.01 * dir[q])));
    return { x: a[0], y: a[1], facing: a[2], angle: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }
  const upright = (a) => { while (a > Math.PI / 2) a -= Math.PI; while (a < -Math.PI / 2) a += Math.PI; return a; };

  function drawNames(c, v) {
    const st = state, P = prepare(st), taken = [...furnitureZones(v)];
    placed.length = 0;
    const turns = v.zoom / (v.flat ? 1 : 0.92);
    for (const f of P.feats) {
      const text0 = P.names.of.get(f.key); if (!text0) continue;
      const S = STYLE[f.kind], text = S.upper ? text0.toUpperCase() : text0;
      let size = S.size[0] + (S.size[1] - S.size[0]) * f.weight;
      if (f.kind === "river") {
        if (f.rank > 3 + 9 * Math.log2(1 + turns)) continue;          // closer in, more rivers are named
        const pts = f.path.map((i) => at(st.mesh.xyz, i)).reverse();  // from the source to the mouth
        const smooth = pts.map((p, k) => unit([0, 1, 2].map((q) => (pts[Math.max(0, k - 1)][q] + 2 * p[q] + pts[Math.min(pts.length - 1, k + 1)][q]) / 4)));
        let best = null;
        for (let run of Overlay.trace(v, smooth, 0.2)) {
          if (run[run.length - 1][0] < run[0][0]) run = run.slice().reverse();   // read from left to right
          const lifted = run.map((p, k) => { const q = run[Math.min(run.length - 1, k + 1)], o = run[Math.max(0, k - 1)], dx = q[0] - o[0], dy = q[1] - o[1], l = Math.hypot(dx, dy) || 1;
            return [p[0] + dy / l * size * 0.75, p[1] - dx / l * size * 0.75]; });   // a little beside the river, not on it
          c.font = fontOf(S, size);
          const g = along(c, text, size, S.spacing, lifted);
          if (g && free(g, taken, v) && (!best || g.length)) { best = g; break; }
        }
        if (!best) continue;
        letter(c, best, S, size); taken.push(...best); placed.push(text);
        continue;
      }
      const p = at(st.mesh.xyz, f.anchor), o = onSheet(v, p, f.axis);
      if (o.facing < 0.25) continue;
      const reach = f.along * v.ppr * (v.flat ? 1 : Math.max(0.3, o.facing));     // how long the feature is on the sheet
      c.font = fontOf(S, size);
      let spacing = S.spacing, laid = straight(c, text, size, spacing, o.x, o.y, Math.max(-0.5, Math.min(0.5, upright(o.angle))));
      if (laid.width > 2 * reach) {                                   // too long for the feature: tighter, then smaller, then none
        if (f.kind === "lake" || f.kind === "island") { if (laid.width > 2 * reach + 60) continue; }
        else {
          spacing = S.spacing * 0.3; laid = straight(c, text, size, spacing, o.x, o.y, laid.glyphs[0].angle);
          if (laid.width > 2 * reach) { size = Math.max(S.size[0] * 0.85, size * 2 * reach / laid.width); c.font = fontOf(S, size);
            laid = straight(c, text, size, spacing, o.x, o.y, laid.glyphs[0].angle); if (laid.width > 2.2 * reach) continue; }
        }
      }
      if (laid.width < 0.06 * reach && (f.kind === "continent" || f.kind === "ocean")) continue;   // far too close in: the name has left the sheet
      if (!free(laid.glyphs, taken, v)) continue;
      letter(c, laid.glyphs, { ...S }, size); taken.push(...laid.glyphs); placed.push(text);
    }
  }
  function furnitureZones(v) {               // where the cartouche, the compass and the buttons are: no name goes there
    const z = [];
    for (let x = 10; x < 260; x += 16) for (let y = 10; y < 62; y += 16) z.push({ x, y, r: 9 });
    for (let y = 10; y < 130; y += 16) z.push({ x: v.W - 26, y, r: 18 });
    z.push({ x: 46, y: v.H - 72, r: 34 }, { x: v.W - 70, y: v.H - 16, r: 22 });
    return z;
  }

  function drawMagic(c, v) {
    if (!magic) return;
    Overlay.clipToMap(c, v);
    const xyz = state.mesh.xyz;
    c.lineCap = "round"; c.lineJoin = "round";
    for (const [colour, glow, edges] of [["#7b3fb3", "rgba(155, 89, 211, 0.22)", magic.plate], ["#3f6fb8", "rgba(80, 140, 220, 0.22)", magic.river]]) {
      for (const [w, style] of [[7, glow], [1.6, colour]]) {
        c.strokeStyle = style; c.lineWidth = w; c.beginPath();
        for (const [i, j] of edges) {
          const a = at(xyz, i), b = at(xyz, j), mid = unit([a[0] + b[0], a[1] + b[1], a[2] + b[2]]);
          for (const run of Overlay.trace(v, [a, mid, b], 0.05)) { c.moveTo(run[0][0], run[0][1]); for (const q of run.slice(1)) c.lineTo(q[0], q[1]); }
        }
        c.stroke();
      }
    }
    const star = (x, y, r, points, fill) => {
      c.beginPath();
      for (let k = 0; k < points * 2; k++) { const a = -Math.PI / 2 + k * Math.PI / points, rr = k % 2 ? r * 0.42 : r; c.lineTo(x + rr * Math.cos(a), y + rr * Math.sin(a)); }
      c.closePath(); c.fillStyle = fill; c.fill(); c.strokeStyle = "#2b2333"; c.lineWidth = 1; c.stroke();
    };
    for (const i of magic.nexus) { const p = Overlay.project(v, at(xyz, i)); if (p[2] > 0.1) star(p[0], p[1], 5, 4, "#c9a227"); }
    for (const [i, w] of magic.springs) { const p = Overlay.project(v, at(xyz, i)); if (p[2] > 0.1) star(p[0], p[1], 5 + 5 * w, 8, "#f2c14e"); }
  }
  // The magic layer's marks from its fields. A ley line along a river runs as the river does: from each of its cells to
  // the cell its water runs to (recv). A ley line along a plate boundary is a band of cells; it is drawn as a tree
  // through them (each cell joined to the one it was first reached from), so that it reads as a line and not as a
  // net of triangles. Nexus: the cells where the two meet. Wellsprings: the cells whose aura is "wellspring", each
  // with its mana among the wellsprings' (0 to 1).
  function magicMarks(n, nbr, recv, ley, leyNames, aura, auraNames, density) {
    const kind = (i) => leyNames[Math.round(ley[i])] || "none";
    const riverish = (i) => kind(i) === "river_line" || kind(i) === "nexus", platish = (i) => kind(i) === "plate_line" || kind(i) === "nexus";
    const river = [], plate = [], nexus = [], springs = [];
    for (let i = 0; i < n; i++) {
      if (kind(i) === "nexus") nexus.push(i);
      if (riverish(i) && recv && recv[i] >= 0 && riverish(recv[i])) river.push([i, recv[i]]);
    }
    const reached = new Uint8Array(n);
    for (let s0 = 0; s0 < n; s0++) {
      if (reached[s0] || !platish(s0)) continue;
      const queue = [s0]; reached[s0] = 1;
      for (let k = 0; k < queue.length; k++) {
        const c = queue[k];
        for (let e = 0; e < 6; e++) { const j = nbr[c * 6 + e]; if (j >= 0 && !reached[j] && platish(j)) { reached[j] = 1; queue.push(j); plate.push([c, j]); } }
      }
    }
    const wells = []; for (let i = 0; i < n; i++) if (auraNames[Math.round(aura[i])] === "wellspring") wells.push(i);
    const most = wells.reduce((m, i) => Math.max(m, density[i]), 0) || 1;
    for (const i of wells) springs.push([i, density[i] / most]);
    return { plate, river, nexus, springs };
  }
  async function loadMagic(state, getBuffer) {
    if (magic) return magic;
    const f = state.world.fields, plane = async (name) => new Float32Array(await getBuffer("/api/field?name=" + name));
    const [ley, aura, density] = await Promise.all([plane("ley_line"), plane("aura"), plane("mana_density")]);
    magic = magicMarks(state.world.meta.cells, state.mesh.nbr, state.map ? state.map.recv : null, ley, f.ley_line.categories, aura, f.aura.categories, density);
    return magic;
  }
  const hasMagic = (world) => !!(world.fields.ley_line && world.fields.aura && world.fields.mana_density && world.fields.ley_line.categories && world.fields.aura.categories);

  function drawCompass(c, v) {
    const x = 46, y = v.H - 72, r = 26;
    let north = -Math.PI / 2;                                        // straight up on the flat map
    if (!v.flat) { const ll = screenToLatLon(canvas.getBoundingClientRect().left + v.W / 2, canvas.getBoundingClientRect().top + v.H / 2);
      if (ll && Math.abs(ll[0]) < 89) { const p = Overlay.unit(ll[0], ll[1]), o = onSheet(v, p, [-p[0] * p[2], -p[1] * p[2], 1 - p[2] * p[2]]); north = o.angle; } }
    c.save(); c.translate(x, y);
    c.fillStyle = "rgba(244, 238, 222, 0.85)"; c.beginPath(); c.arc(0, 0, r + 6, 0, 2 * Math.PI); c.fill();
    c.strokeStyle = "#2b2333"; c.lineWidth = 1; c.beginPath(); c.arc(0, 0, r + 6, 0, 2 * Math.PI); c.stroke();
    c.beginPath(); c.arc(0, 0, r - 7, 0, 2 * Math.PI); c.stroke();
    c.rotate(north + Math.PI / 2);
    for (let k = 0; k < 8; k++) {                                     // eight points: the four main ones long, half dark
      const a = k * Math.PI / 4, len = k % 2 ? r * 0.55 : r, w = k % 2 ? 3 : 5;
      for (const side of [-1, 1]) {
        c.beginPath(); c.moveTo(0, 0); c.lineTo(Math.sin(a) * len, -Math.cos(a) * len);
        c.lineTo(Math.sin(a + side * Math.PI / 2) * w, -Math.cos(a + side * Math.PI / 2) * w); c.closePath();
        c.fillStyle = side < 0 ? "#2b2333" : "#f4eede"; c.fill(); c.strokeStyle = "#2b2333"; c.lineWidth = 0.8; c.stroke();
      }
    }
    c.fillStyle = "#2b2333"; c.font = `600 11px ${SERIF}`; c.textAlign = "center"; c.textBaseline = "bottom"; c.fillText("N", 0, -r - 1);
    c.restore();
  }
  function drawCartouche(c, v) {
    const st = state, P = prepare(st), m = st.world.meta;
    const title = P.names.world.toUpperCase(), line2 = `seed ${st.world.seed} · ${m.cells.toLocaleString()} cells`, line3 = "names and ornaments invented by the viewer";
    c.save(); c.font = `600 15px ${SERIF}`;
    const w = Math.max(c.measureText(title).width + title.length * 3, 120, (c.font = `italic 11px ${SERIF}`, c.measureText(line3).width)) + 28;
    const x = 12, y = 12, h = 60;
    c.fillStyle = "rgba(244, 238, 222, 0.92)"; c.fillRect(x, y, w, h);
    c.strokeStyle = "#2b2333"; c.lineWidth = 1.4; c.strokeRect(x + 0.5, y + 0.5, w, h); c.lineWidth = 0.6; c.strokeRect(x + 4, y + 4, w - 7, h - 7);
    c.fillStyle = "#2b2333"; c.textAlign = "center"; c.textBaseline = "alphabetic";
    c.font = `600 15px ${SERIF}`; c.textAlign = "left";                // the title in spaced capitals, centred
    const gap = 3, tw = [...title].reduce((t, ch) => t + c.measureText(ch).width + gap, -gap);
    let s = x + w / 2 - tw / 2;
    for (const ch of title) { c.fillText(ch, s, y + 24); s += c.measureText(ch).width + gap; }
    c.textAlign = "center";
    c.font = `11px ${SERIF}`; c.fillText(line2, x + w / 2, y + 39);
    c.font = `italic 11px ${SERIF}`; c.fillStyle = "#5a4c40"; c.fillText(line3, x + w / 2, y + 53);
    c.restore();
  }
  function install(getBuffer) {
    const mapOnly = (v) => v.look === "map" && state.map && state.mesh;
    Overlay.add({ name: "magic", on: (v) => mapOnly(v) && show.magic && !!magic, draw: drawMagic });
    Overlay.add({ name: "names", on: (v) => mapOnly(v) && show.names, draw: drawNames });
    Overlay.add({ name: "compass", on: mapOnly, draw: drawCompass });
    Overlay.add({ name: "cartouche", on: (v) => mapOnly(v) && show.names, draw: drawCartouche });
    Atlas.getBuffer = getBuffer;
  }
  async function setMagic(on, state) {
    show.magic = on;
    if (on && !magic) await loadMagic(state, Atlas.getBuffer);
  }
  return { RULES, components, steps, shape, innermost, features, rivers, language, names, magicMarks, hasMagic,
           prepare, install, setMagic, show, placed, get magic() { return magic; } };
})();
