// The sheet over the map: a second canvas laid exactly over the drawing, for what a shader draws badly: lettering
// and vector ornaments. Each layer draws itself with the 2D canvas, in the points of the page, and places things by
// asking where a place on the sphere falls on the sheet (the same arithmetic as the shaders' in draw.js, so that the
// sheet and the map never part). A layer changes nothing of the map under it. Whatever a layer writes that the world
// does not hold (a made-up name, an ornament) is that layer's to mark as invented on the page.
//
// A layer is { name, on(), draw(ctx, view) }: on() says whether it is shown now; draw() is called with the canvas
// already scaled to the page's points and clipped to nothing (a layer that must stay inside the map calls
// Overlay.clipToMap first). Layers are drawn in the order they were added.
"use strict";

const Overlay = (() => {
  const layers = [];
  let sheet = null, ctx = null;
  const clamp1 = (x) => Math.max(-1, Math.min(1, x));
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

  // The view of this moment, as the shaders see it. W and H are the map's size in points; ppr the points to one
  // radian at the middle of the view (on the flat map: of latitude); cell the spacing of the world's cells in
  // radians; worldPx the width of one copy of the world on the flat map; copies the sideways shifts, in points, of
  // the copies of the world that can be seen (the flat map repeats; on the globe there is one).
  function view() {
    const W = canvas.clientWidth, H = canvas.clientHeight, aspect = W / Math.max(1, H), fit = Math.min(1, aspect / 2);
    const worldPx = 2 * fit * state.zoom * H, copies = [0];
    if (state.flat) for (let k = 1; k * worldPx - worldPx / 2 < W && k < 6; k++) copies.push(k * worldPx, -k * worldPx);
    return { W, H, aspect, fit, flat: state.flat, zoom: state.zoom, panX: state.panX, panY: state.panY, rot: rotation(),
             ppr: pxPerRad(H, aspect), cell: state.mesh ? state.mesh.cell : 0.03, worldPx, copies,
             dark: window.matchMedia("(prefers-color-scheme: dark)").matches, look: state.look };
  }
  function unit(lat, lon) {                  // a place given in degrees, as a unit vector
    const la = lat * Math.PI / 180, lo = lon * Math.PI / 180;
    return [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
  }
  // Where a place (a unit vector) falls on the sheet: [x, y, facing]. On the globe, facing is the cosine of the
  // angle between the place and the middle of the view: above 0 the place is on the near side, near 0 it is at the
  // rim. On the flat map it is 1, and x is that of the copy of the world nearest the middle of the view.
  function project(v, w) {
    if (v.flat) {
      let dx = Math.atan2(w[1], w[0]) / Math.PI - v.panX; dx -= 2 * Math.floor((dx + 1) / 2);
      const px = dx * 2 * v.fit * v.zoom / v.aspect, py = (Math.asin(clamp1(w[2])) / (Math.PI / 2) - v.panY) * v.fit * v.zoom;
      return [(px + 1) / 2 * v.W, (1 - py) / 2 * v.H, 1];
    }
    const { r, u, f } = v.rot;
    return [(dot(w, r) * v.zoom / v.aspect + 1) / 2 * v.W, (1 - dot(w, u) * v.zoom) / 2 * v.H, dot(w, f)];
  }
  // A line of places as lines on the sheet: a list of runs, each a list of [x, y]. On the flat map each point follows
  // the one before it across the edge where the map wraps, so a line that crosses that edge stays whole (one run).
  // On the globe the parts on the far side are left out, which can cut the line into several runs.
  function trace(v, places, least = 0.03) {
    const runs = []; let run = null;
    if (v.flat) {
      let dx = 0, before = 0;
      places.forEach((w, i) => {
        const lon = Math.atan2(w[1], w[0]) / Math.PI;
        if (i === 0) { dx = lon - v.panX; dx -= 2 * Math.floor((dx + 1) / 2); }
        else { let step = lon - before; step -= 2 * Math.floor((step + 1) / 2); dx += step; }
        before = lon;
        const px = dx * 2 * v.fit * v.zoom / v.aspect, py = (Math.asin(clamp1(w[2])) / (Math.PI / 2) - v.panY) * v.fit * v.zoom;
        (run = run || (runs[runs.push([]) - 1])).push([(px + 1) / 2 * v.W, (1 - py) / 2 * v.H]);
      });
      return runs;
    }
    for (const w of places) {
      const p = project(v, w);
      if (p[2] > least) (run = run || (runs[runs.push([]) - 1])).push([p[0], p[1]]); else run = null;
    }
    return runs.filter((r) => r.length > 1);
  }
  // A run measured: its length in points, and at(s), the point and direction a distance s along it.
  function measured(run) {
    const upTo = [0];
    for (let i = 1; i < run.length; i++) upTo.push(upTo[i - 1] + Math.hypot(run[i][0] - run[i - 1][0], run[i][1] - run[i - 1][1]));
    const length = upTo[upTo.length - 1];
    const at = (s) => {
      s = Math.max(0, Math.min(length, s));
      let i = 1; while (i < run.length - 1 && upTo[i] < s) i++;
      const a = run[i - 1], b = run[i], span = Math.max(1e-9, upTo[i] - upTo[i - 1]), t = (s - upTo[i - 1]) / span;
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, Math.atan2(b[1] - a[1], b[0] - a[0])];
    };
    return { length, at };
  }
  // The map's own area as the canvas' clip: the disc of the globe, or the band of the flat map between the poles.
  function clipToMap(c, v) {
    c.beginPath();
    if (v.flat) { const e = DRAWING.flatEdge / 90, top = (1 - (e - v.panY) * v.fit * v.zoom) / 2 * v.H, bottom = (1 - (-e - v.panY) * v.fit * v.zoom) / 2 * v.H;
      c.rect(0, top, v.W, bottom - top); }
    else c.arc(v.W / 2, v.H / 2, v.zoom * v.H / 2, 0, 2 * Math.PI);
    c.clip();
  }
  function redraw() {
    if (!sheet) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2), W = canvas.clientWidth, H = canvas.clientHeight;
    const w = Math.round(W * dpr), h = Math.round(H * dpr);
    if (sheet.width !== w || sheet.height !== h) { sheet.width = w; sheet.height = h; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
    const v = view();
    for (const layer of layers) {
      if (!layer.on(v)) continue;
      ctx.save();
      try { layer.draw(ctx, v); } catch (e) { console.error(`the layer ${layer.name} of the sheet over the map could not be drawn`, e); }
      ctx.restore();
    }
  }
  return {
    init(element) { sheet = element; ctx = element.getContext("2d"); },
    add(layer) { layers.push(layer); },          // { name, on(view), draw(ctx, view) }
    layers, view, unit, project, trace, measured, clipToMap, redraw,
    get sheet() { return sheet; },
  };
})();
