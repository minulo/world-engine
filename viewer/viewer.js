// World viewer. It reads one world through the engine's local server and shows it on a globe or a flat map, in one of
// two looks: any stored field, a colour for each cell (the data look), or a drawing of the world made from several
// fields at once (the illustrated look). No third-party code: the shaders and the arithmetic they need are in draw.js.
"use strict";

const $ = (id) => document.getElementById(id);
const ZOOM_MIN = 0.5, ZOOM_MAX = 60;
// The detail: finer cells that the engine works out for the region in view, on request, once a cell of the world is
// `from` points wide on the screen (and lets go of below `drop`). The region asked for reaches from `least` to `most`
// spacings of the world's cells; over the last `band` of them the finer drawing gives way to the world's own.
const DETAIL = { from: 110, drop: 85, least: 5, most: 10, band: 1.6 };
const NO_CLASS = [217, 26, 191];           // the colour of a class code that the field's list does not hold
const NO_VALUE = [115, 115, 115];          // a cell without a value
const NOTHING_ON_LAND = [176, 166, 148];   // on a log scale, a cell that holds exactly zero: no colour of the scale is its own,
const NOTHING_AT_SEA = [70, 86, 108];      // so land and sea each get a plain one, and a dry valley does not look like the sea
const state = {
  world: null, field: null, part: "", month: 1, flat: false, lon0: 0, lat0: 20, zoom: 0.92, panX: 0, panY: 0,
  idmap: null, idW: 0, idH: 0, data: null, stats: null, selected: -1, playing: null, cache: new Map(), sea: null,
  frame: -1, filming: null,                // frame: a picture of the geological history, or -1 for the world as it ends
  day: 0, stepping: null, dayRanges: {},   // day: the date of the weather shown; a day's colour scale is kept from the first day shown
  whyAsked: "",                            // the "why" answer last asked for: an answer that comes back after a later one is dropped
  look: "data",                            // "data": one field as stored; "map": the illustrated look
  mesh: null,                              // where the cells are and which lie next to which (for exact borders and for drawing)
  map: null,                               // what the illustrated look is drawn from, once it has been asked for
  season: false, smooth: false,            // the illustrated look follows the month; the data look blends between cells
  finer: true, detail: null,               // the illustrated look asks for finer cells close in; and those it holds now
};

// ---------------------------------------------------------------- colour
const MAPS = {
  viridis: ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725"],
  thermal: ["#1b2a6b", "#2b5fb0", "#5aa5d6", "#b5dbe8", "#f5f1d8", "#f7c56b", "#ec7f3b", "#c8321f", "#7a0f17"],
  rain: ["#f4efe1", "#d9e7c5", "#a3d3a8", "#5cb6a4", "#2f8fb0", "#2b63a8", "#3a3a8f", "#4a1d6e"],
  diverging: ["#2b3f8f", "#5c86c9", "#a9c8e8", "#f2f2f2", "#f0b8a0", "#d6694d", "#9b1c1c"],
  terrain: ["#0a1f4d", "#1b4a8a", "#3f86c2", "#9fd0e6", "#5f9d58", "#b8b56a", "#b08a57", "#8a6a55", "#f4f4f4"],
  water: ["#ece6d6", "#d3e3df", "#a6d0e2", "#6aaede", "#3b82c9", "#1f58a6", "#123a7a", "#0a2352"],
  // the fantasy layer magic (data/fantasy/magic.yaml names them in its fields' display)
  aether: ["#0d0b1e", "#2a1b5c", "#4b2a8f", "#7a35b8", "#b23fb5", "#e0609a", "#f59a6b", "#ffd166", "#fff6d5"],
  wild: ["#10161c", "#1f3b4d", "#24676b", "#3e9a6a", "#9bc53d", "#f2c14e", "#f2784b", "#ef476f"],
};
const SPLIT_AT = { terrain: 4 };          // where a map breaks at zero: water colours below, land colours above
const FIELD_MAP = {
  elevation: ["terrain", true], height_above_sea: ["terrain", true], surface_temperature: ["thermal", false],
  precipitation: ["rain", false], snowfall: ["rain", false], column_water: ["rain", false], ocean_evaporation: ["rain", false],
  subsidence: ["diverging", true], convergence_rate: ["diverging", true], coriolis_parameter: ["diverging", true],
  latitude: ["diverging", true], longitude: ["diverging", true],
  // third entry "log": a few cells hold most of the range (a river), so equal steps of colour are equal ratios
  river_discharge: ["water", false, "log"], drainage_area: ["water", false, "log"], lake_fraction: ["water", false],
  runoff: ["rain", false], runoff_annual: ["rain", false], evapotranspiration: ["rain", false],
  potential_evapotranspiration: ["rain", false], soil_moisture: ["rain", false], snow_water: ["water", false, "log"],
  snow_cover: ["water", false],
  slope: ["viridis", false, "log"],
  weather_temperature: ["thermal", false], weather_precipitation: ["rain", false, "log"], storm_influence: ["water", false],
  daily_temperature_spread: ["thermal", false], wet_day_fraction: ["rain", false],
};
const LOG_DECADES = 4;                    // a log scale spans this many powers of ten below its top
const ZERO_IS_NONE = { depression_id: true };     // index fields in which 0 means "none", drawn in the neutral colour
function hex(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
function ramp(stops, out, from, count) {
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1) * (stops.length - 1), k = Math.min(Math.floor(t), stops.length - 2), f = t - k;
    for (let c = 0; c < 3; c++) out[(from + i) * 4 + c] = Math.round(stops[k][c] + f * (stops[k + 1][c] - stops[k][c]));
    out[(from + i) * 4 + 3] = 255;
  }
}
function lut(name, split) {
  const stops = MAPS[name].map(hex), out = new Uint8Array(256 * 4);
  if (split && SPLIT_AT[name]) { ramp(stops.slice(0, SPLIT_AT[name]), out, 0, 128); ramp(stops.slice(SPLIT_AT[name]), out, 128, 128); }
  else ramp(stops, out, 0, 256);
  return out;
}
function palette(n, given) {
  const out = new Uint8Array(Math.max(n, 1) * 4);
  for (let i = 0; i < n; i++) {
    let rgb;
    if (given && given[i]) rgb = hex(given[i]);
    else {
      const h = (i * 137.508) % 360, s = 0.55, l = 0.42 + 0.18 * ((i * 7) % 3) / 2;
      const a = s * Math.min(l, 1 - l), f = (k) => { const m = (k + h / 30) % 12; return l - a * Math.max(-1, Math.min(m - 3, 9 - m, 1)); };
      rgb = [f(0), f(8), f(4)].map((v) => Math.round(v * 255));
    }
    out.set([rgb[0], rgb[1], rgb[2], 255], i * 4);
  }
  return out;
}

// ---------------------------------------------------------------- WebGL
const canvas = $("gl");
const gl = canvas.getContext("webgl2", { antialias: false });
let prog, uni = {}, tex = {}, looks = {}, quad, rivers, fineRivers;
// each texture keeps a unit of its own, so that no drawing has to bind one again
const UNITS = { ids: 0, data: 1, lut: 2, pal: 3, sea: 4, pos: 5, nbr: 6, a: 7, b: 8, biome: 9, fids: 10, fpos: 11, fnbr: 12, fa: 13, fb: 14 };
const SAMPLERS = { uIds: 0, uData: 1, uLut: 2, uPal: 3, uSea: 4, uPos: 5, uNbr: 6, uA: 7, uB: 8, uBiome: 9,
                   uFIds: 10, uFPos: 11, uFNbr: 12, uFA: 13, uFB: 14 };
function program(vs, fs, attributes) {
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
  attributes.forEach((name, i) => gl.bindAttribLocation(p, i, name));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  for (let i = 0; i < gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i++) { const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
  gl.useProgram(p);
  for (const [name, unit] of Object.entries(SAMPLERS)) if (u[name]) gl.uniform1i(u[name], unit);
  return { prog: p, uni: u };
}
function initGL() {
  if (!gl) { $("status").textContent = "This browser has no WebGL2, which the viewer needs."; return false; }
  looks.data = program(VS_QUAD, dataShader(NO_CLASS, NO_VALUE, NOTHING_AT_SEA, NOTHING_ON_LAND), ["aPos"]);
  looks.map = program(VS_QUAD, FS_MAP, ["aPos"]);
  looks.river = program(VS_RIVER, FS_RIVER, ["aCorner", "aA", "aB", "aQ"]);
  prog = looks.data.prog; uni = looks.data.uni;         // the data look's program is the one in use between two drawings
  quad = gl.createVertexArray(); gl.bindVertexArray(quad);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  const strips = () => {                   // one strip of four corners, drawn once for each part of a river
    const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, -1, 0, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const parts = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, parts);
    [[1, 3, 0], [2, 3, 12], [3, 2, 24]].forEach(([loc, size, at]) => { gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 32, at); gl.vertexAttribDivisor(loc, 1); });
    return { vao, parts, count: 0 };
  };
  rivers = strips(); fineRivers = strips();                // the rivers of the world's cells, and of the detail's
  gl.bindVertexArray(quad);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  for (const [n, unit] of Object.entries(UNITS)) { tex[n] = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex[n]);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, n === "lut" ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, n === "lut" ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    // one empty point each, of the kind the shaders read, until the world's own arrive
    if (n === "ids" || n === "fids") gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32UI, 1, 1, 0, gl.RED_INTEGER, gl.UNSIGNED_INT, new Uint32Array(1));
    else if (n === "data" || n === "sea") gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, 1, 1, 0, gl.RED, gl.FLOAT, new Float32Array(1));
    else if (n === "lut" || n === "pal" || n === "biome") gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
    else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, 1, 1, 0, gl.RGBA, gl.FLOAT, new Float32Array(4)); }
  gl.useProgram(prog); gl.uniform1i(uni.uHasSea, 0);
  return true;
}
function rotation() {
  const la = state.lat0 * Math.PI / 180, lo = state.lon0 * Math.PI / 180;
  const f = [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
  const r = [-Math.sin(lo), Math.cos(lo), 0];
  const u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]];
  return { r, u, f };
}
function pxPerRad(height, aspect) {       // pixels to one radian at the middle of the view (on the flat map: of latitude)
  return state.flat ? height / 2 * Math.min(1, aspect / 2) * state.zoom / (Math.PI / 2) : height / 2 * state.zoom;
}
function shared(u, w, h, ready) {         // what every program is told before it draws
  const { r, u: up, f } = rotation();
  gl.uniformMatrix3fv(u.uRot, false, new Float32Array([...r, ...up, ...f]));
  gl.uniform1i(u.uFlat, state.flat ? 1 : 0); gl.uniform1f(u.uZoom, state.zoom); gl.uniform1f(u.uAspect, w / h);
  gl.uniform2f(u.uPan, state.panX, state.panY); gl.uniform1i(u.uSel, state.selected);
  gl.uniform1i(u.uReady, ready ? 1 : 0); gl.uniform2i(u.uIdSize, state.idW, state.idH);
  gl.uniform1i(u.uMesh, state.mesh ? 1 : 0); gl.uniform1f(u.uCell, state.mesh ? state.mesh.cell : 0.03);
  gl.uniform1f(u.uPxPerRad, pxPerRad(h, w / h));
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  gl.uniform3f(u.uSpace, dark ? 0.02 : 0.043, dark ? 0.027 : 0.059, dark ? 0.043 : 0.09);
  gl.uniform1i(u.uDark, dark ? 1 : 0);
  const d = state.look === "map" ? state.detail : null;
  gl.uniform1i(u.uFine, d ? 1 : 0);
  if (d) { gl.uniform1i(u.uFSize, d.size); gl.uniform3fv(u.uFCentre, d.centre); gl.uniform3fv(u.uFEast, d.east); gl.uniform3fv(u.uFNorth, d.north);
    gl.uniform1f(u.uFHalf, d.half); gl.uniform1f(u.uFCell, d.cell); gl.uniform1f(u.uFIn, d.inner); gl.uniform1f(u.uFOut, d.outer); }
}
function draw() {
  if (!prog) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2), w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  gl.bindVertexArray(quad); gl.disable(gl.BLEND);
  if (state.look !== "map") {
    gl.useProgram(prog); shared(uni, w, h, state.idmap && state.data);
    gl.uniform1i(uni.uSmooth, state.smooth ? 1 : 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  } else {
    const m = state.map, ready = !!(m && state.idmap), ppr = pxPerRad(h, w / h), d = state.detail;
    // as many sizes of bend as the screen can show, the smallest a few pixels long; and as many sizes of ridge
    const bends = (cell) => Math.max(2, Math.min(9, Math.floor(Math.log2(Math.max(1, cell * ppr * DRAWING.warpStep / 3))) + 1));
    const ridges = (cell) => Math.max(1, Math.min(4, Math.floor(Math.log2(Math.max(1, cell * ppr * 0.9 / (12 * dpr)))) + 1));
    const cell = state.mesh ? state.mesh.cell : 0.03, fine = d ? d.cell : cell;
    const M = looks.map; gl.useProgram(M.prog); shared(M.uni, w, h, ready);
    gl.uniform1i(M.uni.uOct, bends(cell)); gl.uniform1i(M.uni.uFOct, bends(fine)); gl.uniform1f(M.uni.uDpr, dpr);
    gl.uniform1i(M.uni.uRidge, ridges(cell)); gl.uniform1i(M.uni.uFRidge, ridges(fine));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (ready && (rivers.count || (d && fineRivers.count))) {
      const R = looks.river; gl.useProgram(R.prog); shared(R.uni, w, h, ready);
      gl.uniform1i(R.uni.uOct, bends(cell)); gl.uniform1i(R.uni.uFOct, bends(fine)); gl.uniform1f(R.uni.uDpr, dpr); gl.uniform2f(R.uni.uView, w, h);
      const turns = state.zoom / (state.flat ? 1 : 0.92);   // how far in the view is, 1 for the whole world
      gl.uniform1f(R.uni.uWide, Math.max(0.6, Math.min(2.4, 0.72 * Math.pow(turns, 0.4))));
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      for (const [level, strip, least] of [[0, rivers, Math.max(DRAWING.riverFloor, 0.11 / Math.pow(turns, 1.2))],   // closer in, smaller rivers are drawn too
                                           [1, fineRivers, DRAWING.riverFloor]]) {
        if (!strip.count || (level === 1 && !d)) continue;
        gl.uniform1i(R.uni.uLevel, level); gl.uniform1f(R.uni.uQMin, least); gl.bindVertexArray(strip.vao);
        for (const shift of state.flat ? [-2, 0, 2] : [0]) { gl.uniform1f(R.uni.uShift, shift); gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, strip.count); }
      }
      gl.disable(gl.BLEND); gl.bindVertexArray(quad);
    }
    gl.useProgram(prog);
  }
  showScale();
  clearTimeout(draw.then); draw.then = setTimeout(considerDetail, 220);     // once the view rests: does it want finer cells?
}
function screenToLatLon(cx, cy) {
  const rect = canvas.getBoundingClientRect(), x = ((cx - rect.left) / rect.width * 2 - 1) * (rect.width / rect.height), y = 1 - (cy - rect.top) / rect.height * 2;
  if (state.flat) {
    const fit = Math.min(1, rect.width / rect.height / 2);
    const lat = (y / fit / state.zoom + state.panY) * 90; let lon = (x / 2 / fit / state.zoom + state.panX) * 180;
    if (Math.abs(lat) > 90) return null;
    lon = ((lon + 180) % 360 + 360) % 360 - 180; return [lat, lon];
  }
  const qx = x / state.zoom, qy = y / state.zoom, r2 = qx * qx + qy * qy;
  if (r2 > 1) return null;
  const z = Math.sqrt(1 - r2), { r, u, f } = rotation();
  const w = [0, 1, 2].map((k) => r[k] * qx + u[k] * qy + f[k] * z);
  return [Math.asin(Math.max(-1, Math.min(1, w[2]))) * 180 / Math.PI, Math.atan2(w[1], w[0]) * 180 / Math.PI];
}
function cellAt(lat, lon) {                // as the shaders: the grid's cell, then the nearest of it and its neighbours
  if (!state.idmap) return -1;
  const ix = Math.min(state.idW - 1, Math.max(0, Math.floor((lon + 180) / 360 * state.idW)));
  const iy = Math.min(state.idH - 1, Math.max(0, Math.floor((90 - lat) / 180 * state.idH)));
  const c = state.idmap[iy * state.idW + ix], m = state.mesh;
  if (!m) return c;
  const la = lat * Math.PI / 180, lo = lon * Math.PI / 180, w = [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
  const near = (j) => w[0] * m.xyz[j * 3] + w[1] * m.xyz[j * 3 + 1] + w[2] * m.xyz[j * 3 + 2];
  let best = near(c), bc = c;
  for (let k = 0; k < 6; k++) { const j = m.nbr[c * 6 + k]; if (j >= 0 && near(j) > best) { best = near(j); bc = j; } }
  return bc;
}

// ---------------------------------------------------------------- data
async function getJSON(url) { const r = await fetch(url); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j; }
async function getBuffer(url) { const r = await fetch(url); if (!r.ok) throw new Error((await r.json()).error || r.statusText); return r.arrayBuffer(); }
function spec() { return state.world.fields[state.field]; }
function isMonthly() { return spec().shape === "month_cell"; }
function isDaily() { return spec().shape === "day_cell"; }
function inHistory() { const h = state.world.history; return !!h && h.fields.includes(state.field); }
function framed() { return inHistory() && state.frame >= 0 && state.frame < state.world.history.rounds.length; }
async function loadField() {
  const s = spec(), key = `${state.field}|${isMonthly() ? state.month : 0}|${state.part}|${framed() ? state.frame : -1}|${isDaily() ? state.day : -1}`;
  let arr = state.cache.get(key);
  if (!arr && isDaily()) {
    const q = new URLSearchParams({ name: state.field, day: state.day });
    if (s.kind === "direction" && state.part) q.set("part", state.part);
    $("status").textContent = `working out day ${state.day}…`;
    arr = new Float32Array(await getBuffer("/api/weather?" + q));
    $("status").textContent = "";
    if (state.cache.size > 80) state.cache.clear();
    state.cache.set(key, arr);
  }
  if (!arr && framed()) {
    arr = new Float32Array(await getBuffer("/api/history?" + new URLSearchParams({ name: state.field, index: state.frame })));
    if (state.cache.size > 80) state.cache.clear();
    state.cache.set(key, arr);
  }
  if (!arr) {
    const q = new URLSearchParams({ name: state.field });
    if (isMonthly()) q.set("month", state.month);
    if (s.kind === "direction" && state.part) q.set("part", state.part);
    arr = new Float32Array(await getBuffer("/api/field?" + q));
    if (state.cache.size > 80) state.cache.clear();
    state.cache.set(key, arr);
  }
  state.data = arr;
  const [filled, h] = padded(arr);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, tex.data);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, DATA_W, h, 0, gl.RED, gl.FLOAT, filled);
  draw();
}

// ---------------------------------------------------------------- the mesh, and the illustrated look
function cellTexture(name, width, rows, rgba) {            // four numbers for each cell (or for each half of a cell's neighbours)
  gl.activeTexture(gl.TEXTURE0 + UNITS[name]); gl.bindTexture(gl.TEXTURE_2D, tex[name]);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, width, rows, 0, gl.RGBA, gl.FLOAT, rgba);
}
async function loadMesh() {
  const n = state.world.meta.cells, rows = Math.ceil(n / DATA_W);
  const xyz = new Float32Array(await getBuffer("/api/mesh?part=xyz")), nbr = new Int32Array(await getBuffer("/api/mesh?part=nbr"));
  const h = cellSpacing(xyz, nbr), pos = new Float32Array(DATA_W * rows * 4), around = new Float32Array(DATA_W * rows * 8).fill(-1);
  let sum = 0;
  for (let i = 0; i < n; i++) { pos.set([xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2], h[i]], i * 4); sum += h[i];
    for (let k = 0; k < 6; k++) around[i * 8 + k] = nbr[i * 6 + k]; }
  cellTexture("pos", DATA_W, rows, pos); cellTexture("nbr", DATA_W * 2, rows, around);
  state.mesh = { xyz, nbr, h, cell: sum / n };
}
function canDraw() { return !!(state.mesh && state.world && state.world.fields.ocean_mask); }
async function loadMap() {                 // everything the illustrated look is drawn from, asked for once
  if (state.map) return state.map;
  const f = state.world.fields, n = state.world.meta.cells;
  const plane = async (name, month) => new Float32Array(await getBuffer("/api/field?" + new URLSearchParams(month ? { name, month } : { name })));
  const one = (name) => f[name] ? plane(name) : null;
  const year = (name) => !f[name] ? null : f[name].shape === "month_cell" ? Promise.all(MONTHS(state.world.meta.months).map((mo) => plane(name, mo))) : plane(name).then((a) => [a]);
  const [sea, up, depth, elevation, biome, lake, recv, flow, snow] = await Promise.all([one("ocean_mask"), one("height_above_sea"), one("sea_depth"),
    one("elevation"), one("biome"), one("lake_fraction"), one("flow_receiver"), year("river_discharge"), year("snow_ice_cover")]);
  const height = new Float32Array(n), ground = new Float32Array(n);     // metres above the sea, below it as less than nothing; and the land's own
  for (let i = 0; i < n; i++) { height[i] = sea[i] ? -(depth ? depth[i] : 3000) : Math.max(0, up ? up[i] : elevation ? elevation[i] : 0); ground[i] = Math.max(0, height[i]); }
  const mean = (planes) => { const out = new Float32Array(n); for (const a of planes) for (let i = 0; i < n; i++) out[i] += a[i] / planes.length; return out; };
  const least = (planes) => { const out = new Float32Array(n).fill(Infinity); for (const a of planes) for (let i = 0; i < n; i++) out[i] = Math.min(out[i], a[i]); return out; };
  const names = biome ? f.biome.categories : [], colours = drawnBiomeColours(names, state.world.colors.biome);
  const pal = new Uint8Array(Math.max(1, colours.length) * 4); colours.forEach((c, i) => pal.set([c[0], c[1], c[2], c[3] * 30], i * 4));   // the fourth: the biome's sign
  gl.activeTexture(gl.TEXTURE0 + UNITS.biome); gl.bindTexture(gl.TEXTURE_2D, tex.biome);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, Math.max(1, colours.length), 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, pal);
  const flowYear = flow ? mean(flow) : null;
  state.map = { sea, height, biome, lake, recv, flow, snow, names, colours, ice: names.indexOf("ice"),
                slope: cellGradients(state.mesh.xyz, state.mesh.nbr, ground), flowYear, snowLeast: snow ? least(snow) : null,
                top: flowYear ? percentile(Array.from(flowYear).filter((v, i) => !sea[i]), 99.5) : 0, riverCount: 0 };
  redrawMap();
  return state.map;
}
function redrawMap() {                     // the parts of the drawing that follow the month when the seasons are shown
  const m = state.map, n = state.world.meta.cells, rows = Math.ceil(n / DATA_W), mo = state.season ? state.month - 1 : -1;
  const A = new Float32Array(DATA_W * rows * 4), B = new Float32Array(DATA_W * rows * 4);
  const snow = m.snow ? (mo >= 0 && m.snow.length > 1 ? m.snow[mo] : m.snowLeast) : null;
  for (let i = 0; i < n; i++) {
    const ice = (m.biome && m.biome[i] === m.ice) || (snow && snow[i] >= 0.5);
    A.set([m.sea[i] ? 0 : 1, m.height[i], m.biome ? m.biome[i] : -1, ice ? 1 : 0], i * 4);
    B.set([m.slope[i * 3], m.slope[i * 3 + 1], m.slope[i * 3 + 2], m.lake && m.lake[i] >= 0.5 ? 1 : 0], i * 4);
  }
  cellTexture("a", DATA_W, rows, A); cellTexture("b", DATA_W, rows, B);
  if (m.recv && m.flow && m.top > 0) {
    const parts = riverParts(state.mesh.xyz, m.recv, mo >= 0 && m.flow.length > 1 ? m.flow[mo] : m.flowYear, m.sea, m.top);
    gl.bindBuffer(gl.ARRAY_BUFFER, rivers.parts); gl.bufferData(gl.ARRAY_BUFFER, parts, gl.DYNAMIC_DRAW);
    m.riverCount = rivers.count = parts.length / 8;
  }
}
// ---------------------------------------------------------------- the detail: finer cells for the region in view
function unitAt(lat, lon) { const la = lat * Math.PI / 180, lo = lon * Math.PI / 180; return [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)]; }
function angle(a, b) { return Math.acos(Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))); }
function viewOnSphere() {                 // the middle of the view, how far it reaches (radians), and how wide a cell of the world is on the screen
  const rect = canvas.getBoundingClientRect(), ll = screenToLatLon(rect.left + rect.width / 2, rect.top + rect.height / 2);
  if (!ll || !rect.height) return null;
  const ppr = pxPerRad(rect.height, rect.width / rect.height);
  return { lat: ll[0], lon: ll[1], at: unitAt(ll[0], ll[1]), reach: Math.hypot(rect.width, rect.height) / 2 / ppr, cellPx: state.mesh.cell * ppr };
}
function dropDetail() { if (state.detail) { state.detail = null; fineRivers.count = 0; detailNote(); draw(); } else detailNote(); }
function considerDetail() {
  if (state.look !== "map" || !state.map || !state.mesh || !state.finer) return dropDetail();
  const v = viewOnSphere(); if (!v) return;
  if (v.cellPx < DETAIL.drop || (v.cellPx < DETAIL.from && !state.detail)) return dropDetail();
  const d = state.detail, cell = state.mesh.cell;
  // the detail held is enough while the view lies inside its full part (or, for a view wider than any detail, near its middle)
  if (d && angle(v.at, d.centre) + Math.min(v.reach, 0.7 * d.inner) <= d.inner) return;
  if (considerDetail.asking) return;
  const want = Math.max(DETAIL.least * cell, Math.min(DETAIL.most * cell, v.reach * 1.15 + (DETAIL.band + 1.6) * cell));
  const asked = new URLSearchParams({ lat: v.lat.toFixed(2), lon: v.lon.toFixed(2), radius_km: (want * state.world.planet.radius_m / 1000).toFixed(0) }).toString();
  if (asked === considerDetail.last) return;                // what this would ask for is what it holds, or what was refused
  considerDetail.asking = true; considerDetail.last = asked;
  $("status").textContent = "working out finer cells for this region…";
  getJSON("/api/detail?" + asked).then((j) => { $("status").textContent = ""; useDetail(j); })
    .catch((e) => { $("status").textContent = ""; state.finer = false; $("finer").checked = false; state.detail = null; detailNote(`No finer cells: ${e.message}.`); draw(); })
    .finally(() => { considerDetail.asking = false; });
}
function useDetail(j) {                    // the finer cells as the shaders read them: places, neighbours, the grid of nearest cells, values, rivers
  const M = state.map, mesh = state.mesh, m = j.cells, rows = Math.ceil(m / DATA_W);
  const xyz = Float32Array.from(j.xyz), nbr = Int32Array.from(j.nbr), h = cellSpacing(xyz, nbr), ground = Float32Array.from(j.height, (v) => Math.max(0, v));
  const pos = new Float32Array(DATA_W * rows * 4), around = new Float32Array(DATA_W * rows * 8).fill(-1);
  const A = new Float32Array(DATA_W * rows * 4), B = new Float32Array(DATA_W * rows * 4), slope = cellGradients(xyz, nbr, ground);
  const landBiome = (o) => {                // the biome of the world's cell a fine cell lies in; for a fine cell of land in a cell of sea, of land next to it
    if (!M.biome) return -1;
    if (!M.sea[o]) return M.biome[o];
    const next = (c) => Array.from(mesh.nbr.slice(c * 6, c * 6 + 6)).filter((q) => q >= 0);
    for (const ring of [next(o), next(o).flatMap(next)]) { const q = ring.find((c) => !M.sea[c]); if (q !== undefined) return M.biome[q]; }
    return -1;
  };
  let sum = 0;
  for (let i = 0; i < m; i++) { pos.set([xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2], h[i]], i * 4); sum += h[i];
    for (let k = 0; k < 6; k++) around[i * 8 + k] = nbr[i * 6 + k];
    A.set([j.sea[i] ? 0 : 1, j.height[i], landBiome(j.owner[i]), 0], i * 4);
    B.set([slope[i * 3], slope[i * 3 + 1], slope[i * 3 + 2], j.lake[i] ? 1 : 0], i * 4); }
  cellTexture("fpos", DATA_W, rows, pos); cellTexture("fnbr", DATA_W * 2, rows, around); cellTexture("fa", DATA_W, rows, A); cellTexture("fb", DATA_W, rows, B);
  const ids = Uint32Array.from(j.grid.ids);
  gl.activeTexture(gl.TEXTURE0 + UNITS.fids); gl.bindTexture(gl.TEXTURE_2D, tex.fids);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32UI, j.grid.size, j.grid.size, 0, gl.RED_INTEGER, gl.UNSIGNED_INT, ids);
  const parts = M.top > 0 ? riverParts(xyz, Int32Array.from(j.recv), Float32Array.from(j.flow), j.sea, M.top) : new Float32Array(0);
  gl.bindBuffer(gl.ARRAY_BUFFER, fineRivers.parts); gl.bufferData(gl.ARRAY_BUFFER, parts, gl.DYNAMIC_DRAW); fineRivers.count = parts.length / 8;
  const outer = Math.max(0.5 * j.reach, j.reach - 0.6 * mesh.cell), inner = Math.max(0.3 * j.reach, j.reach - DETAIL.band * mesh.cell);
  state.detail = { centre: j.centre, east: j.east, north: j.north, half: j.grid.half, size: j.grid.size, ids, cell: sum / m, reach: j.reach, inner, outer,
                   cells: m, level: j.level, worldCells: j.of_world_cells, xyz, nbr, sea: j.sea, lake: j.lake, height: j.height, flow: j.flow, riverCount: fineRivers.count };
  detailNote(); draw();
}
function fineAt(ll) {                      // the detail's cell at a place, where the finer drawing is whole; else -1
  const d = state.detail; if (!d || state.look !== "map") return -1;
  const w = unitAt(ll[0], ll[1]); if (angle(w, d.centre) > d.inner) return -1;
  const q = [d.east, d.north].map((e) => (w[0] * e[0] + w[1] * e[1] + w[2] * e[2]) / d.half * 0.5 + 0.5);
  const at = q.map((v) => Math.max(0, Math.min(d.size - 1, Math.floor(v * d.size)))), c = d.ids[at[1] * d.size + at[0]];
  const near = (k) => w[0] * d.xyz[k * 3] + w[1] * d.xyz[k * 3 + 1] + w[2] * d.xyz[k * 3 + 2];
  let best = near(c), bc = c;
  for (let k = 0; k < 6; k++) { const n = d.nbr[c * 6 + k]; if (n >= 0 && near(n) > best) { best = near(n); bc = n; } }
  return bc;
}
function detailNote(said) {
  const d = state.detail, km = (x) => fmt(x * state.world.planet.radius_m / 1000, "km");
  $("detailnote").textContent = said || (d ? `Finer cells are shown here: ${d.cells.toLocaleString()} cells about ${km(d.cell)} apart, which the engine worked out for this ` +
    `region just now from ${d.worldCells} cells of the world (heights, coast, lakes and rivers; nothing of it is stored). The biomes and the ice are still the world's own cells'.`
    : state.finer ? `Close in (a cell of the world ${DETAIL.from} points wide), the engine works out finer cells for the region in view.` : "");
}
function mapLegend() {                     // what the colours and lines of the drawing stand for
  const m = state.map, legend = $("legend"); legend.textContent = "";
  const ul = document.createElement("ul"), here = new Set();
  if (m.biome) for (let i = 0; i < m.biome.length; i++) if (!m.sea[i]) here.add(m.biome[i]);
  m.names.forEach((name, i) => { if (here.has(i) && name !== "ocean") ul.append(swatch(m.colours[i], name.replace(/_/g, " "))); });
  ul.append(swatch([174, 222, 218], "sea near the coast (a drawn band)"), swatch([139, 202, 208], "open sea"), swatch([110, 178, 196], "sea deeper than 3,800 m"));
  if (m.lake && m.lake.some((v) => v >= 0.5)) ul.append(swatch([153, 212, 214], "lake"));
  ul.append(swatch([190, 172, 167], "above 1,500 m"), swatch([237, 232, 230], "above 2,700 m"), swatch([39, 100, 133], "river, wider with its flow"));
  legend.append(ul);
  const note = document.createElement("p"); note.className = "muted small";
  note.textContent = "The small signs say what kind of country a place is: trees for forest, a flat-topped tree among tufts for open woodland, " +
    "tufts for grass, dots for sand, short strokes for tundra, peaks where the heights change fast. None of them marks a thing that stands at that spot.";
  legend.append(note);
}
async function setLook(look) {
  if (look === "map" && !canDraw()) look = "data";
  state.look = look; document.body.dataset.look = look;
  $("lookmap").setAttribute("aria-pressed", String(look === "map")); $("lookdata").setAttribute("aria-pressed", String(look !== "map"));
  if (look === "map") {
    if (state.playing && !state.season) togglePlay();
    $("status").textContent = "drawing the map…"; draw();
    await loadMap();
    $("status").textContent = ""; mapLegend(); monthRow(); draw();
  } else await selectField();
}
function monthRow() {                      // the month matters to a monthly field, and to the drawing when it shows the seasons
  const on = state.look === "map" ? state.season : isMonthly();
  $("monthrow").style.opacity = on ? 1 : 0.4; $("month").disabled = $("play").disabled = !on;
  if (!on && state.playing) togglePlay();
}
async function showMonth() {               // the month has changed
  if (state.look === "map") { if (state.map && state.season) { redrawMap(); draw(); } }
  else await loadField();
}
function rangeOf(arr, positive) {       // as the server's stats: the 2nd and 98th percentiles, and the 99.9th for a log scale
  const f = Array.from(arr).filter(Number.isFinite).sort((a, b) => a - b);
  if (!f.length) return { min: null, max: null, low: null, high: null, top: null };
  const at = (p) => f[Math.min(f.length - 1, Math.floor(p / 100 * f.length))];
  return { min: f[0], max: f[f.length - 1], low: positive ? 0 : at(2), high: at(98), top: at(99.9) };
}
function padded(arr) { const h = Math.ceil(arr.length / DATA_W), out = new Float32Array(DATA_W * h); out.set(arr); return [out, h]; }
function named(field, v) {                // a number that names a thing is a whole number, and one of them means "none"
  if (v === null || v === undefined || Number.isNaN(v)) return "no value";
  const k = Math.round(v);
  return k < 0 || (ZERO_IS_NONE[field] && k === 0) ? `none (${k})` : String(k);
}
function swatch(rgb, text) {
  const li = document.createElement("li"), sw = document.createElement("span");
  sw.className = "sw"; sw.style.background = `rgb(${rgb.join(",")})`; li.append(sw, text); return li;
}
function fmt(v, unit) {
  if (v === null || v === undefined || Number.isNaN(v)) return "no value";
  const a = Math.abs(v); let t;
  if (a !== 0 && (a < 0.01 || a >= 1e6)) t = v.toExponential(2); else t = a >= 1000 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
  return unit && !/^(category|index|true or false|0 to 1)$/.test(unit) ? `${t} ${unit}` : t;
}
async function selectField() {
  const s = spec(), cat = s.kind === "category" || s.kind === "boolean", names_a_thing = s.kind === "index";
  $("fielddesc").textContent = s.description || "";
  $("partrow").hidden = s.kind !== "direction";
  $("historyrow").hidden = !inHistory();
  $("dayrow").hidden = !isDaily();
  if (!isDaily() && state.stepping) toggleDays();
  if (!inHistory() && state.filming) toggleFilm();
  monthRow();
  const shown = s.display && MAPS[s.display.map] ? [s.display.map, false, s.display.scale] : null;   // a map that fields.yaml names
  const [mapName, split0, scale] = FIELD_MAP[state.field] || shown || ["viridis", false];
  let lo = 0, hi = 1, split = false, log = false;
  const legend = $("legend"); legend.textContent = "";
  if (cat) {
    const names = s.kind === "boolean" ? ["false", "true"] : s.categories;
    const pal = palette(names.length, s.kind === "boolean" ? ["#c9b38a", "#2f6fa8"] : state.world.colors[state.field]);
    gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, tex.pal);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, names.length, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, pal);
    await loadField();
    const present = new Set(state.data);
    const ul = document.createElement("ul");
    names.forEach((n, i) => { if (!present.has(i)) return; const li = document.createElement("li"), sw = document.createElement("span");
      sw.className = "sw"; sw.style.background = `rgb(${pal[i * 4]},${pal[i * 4 + 1]},${pal[i * 4 + 2]})`; li.append(sw, n.replace(/_/g, " ")); ul.append(li); });
    if ([...present].some((v) => !Number.isNaN(v) && (v < 0 || v >= names.length))) {
      const li = document.createElement("li"), sw = document.createElement("span");
      sw.className = "sw"; sw.style.background = `rgb(${NO_CLASS.join(",")})`; li.append(sw, "no class (a code outside the list)"); ul.append(li);
    }
    legend.append(ul);
    gl.uniform1i(uni.uClasses, names.length);
  } else if (names_a_thing) {
    await loadField();
    const note = document.createElement("p"); note.className = "muted small";
    note.textContent = "The colours tell one number from the next and have no order; two numbers far apart can look alike. " +
      "Click a cell for its number. Grey means none" + (ZERO_IS_NONE[state.field] ? " (0)." : " (-1).");
    legend.append(note);
  } else {
    if (isDaily()) {                       // no stored values to scale by: the first day shown sets the scale
      await loadField();
      const rk = `${state.field}|${state.part}`;
      state.dayRanges[rk] = state.dayRanges[rk] || rangeOf(state.data, s.kind === "direction" && !state.part);
      state.stats = state.dayRanges[rk];
    } else state.stats = await getJSON("/api/stats?name=" + encodeURIComponent(state.field));
    lo = state.stats.low ?? 0; hi = state.stats.high ?? 1;
    log = scale === "log" && state.stats.top > 0;
    if (log) { hi = state.stats.top; lo = hi / 10 ** LOG_DECADES; }
    split = split0 && state.stats.min < 0 && state.stats.max > 0 && !(s.kind === "direction" && !state.part);
    if (s.kind === "direction" && state.part) { const m = Math.max(Math.abs(lo), Math.abs(hi)); lo = -m; hi = m; split = true; }
    if (split) { lo = Math.min(lo, -1e-30); hi = Math.max(hi, 1e-30); }
    if (hi <= lo) hi = lo + 1;
    const table = lut(split && mapName === "viridis" ? "diverging" : (s.kind === "direction" && state.part ? "diverging" : mapName), split);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, tex.lut);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, table);
    const bar = document.createElement("canvas"); bar.width = 256; bar.height = 1;
    const img = bar.getContext("2d").createImageData(256, 1); img.data.set(table); bar.getContext("2d").putImageData(img, 0, 0);
    const ends = document.createElement("div"); ends.className = "ends";
    const mid = split ? `<span>0</span>` : "";
    ends.innerHTML = `<span>${log ? "≤ " : ""}${fmt(lo, "")}</span>${mid}<span>${fmt(hi, s.unit)}</span>`;
    legend.append(bar, ends);
    await loadField();
    const extra = document.createElement("ul");
    if (log) {
      const note = document.createElement("p"); note.className = "muted small";
      note.textContent = "Equal steps of colour are equal ratios.";
      legend.append(note);
      if (state.data.some((v) => v === 0)) {
        extra.append(swatch(NOTHING_ON_LAND, state.sea ? "exactly zero, on land" : "exactly zero"));
        if (state.sea) extra.append(swatch(NOTHING_AT_SEA, "exactly zero, at sea"));
      }
    }
    if (state.data.some(Number.isNaN)) extra.append(swatch(NO_VALUE, "no value"));
    if (extra.children.length) legend.append(extra);
  }
  gl.uniform1i(uni.uCategorical, cat ? 1 : names_a_thing ? 2 : 0); gl.uniform1i(uni.uSplit, split ? 1 : 0);
  gl.uniform1i(uni.uLog, log ? 1 : 0); gl.uniform1i(uni.uZeroNone, ZERO_IS_NONE[state.field] ? 1 : 0);
  gl.uniform1f(uni.uLo, lo); gl.uniform1f(uni.uHi, hi);
  const writer = state.world.weather && state.world.weather.writers ? state.world.weather.writers[state.field] : null;
  const line = state.world.lineage[state.field] || (writer ? { writer, pushes: [] } : null), m = line && state.world.models[line.writer];
  $("model").innerHTML = line ? `<p><b>Written by</b> ${line.writer}${line.pushes.length ? ", then pushed by " + line.pushes.join(", ") : ""}.</p>` +
    (m && m.model ? `<p><b>Model.</b> ${m.model}</p><p><b>What it ignores.</b> ${m.ignores || ""}</p><p><b>Where it will be wrong.</b> ${m.wrong_where || ""}</p>` : "") : "";
  draw();
  if (state.selected >= 0) showCell(state.selected);
}

// ---------------------------------------------------------------- cell panel
const MONTHS = (n) => Array.from({ length: n }, (_, i) => i + 1);
async function showCell(id) {
  state.selected = id; draw();
  const c = await getJSON("/api/cell?id=" + id);
  $("celltitle").textContent = `Cell ${id} at ${Math.abs(c.lat).toFixed(1)}° ${c.lat >= 0 ? "N" : "S"}, ${Math.abs(c.lon).toFixed(1)}° ${c.lon >= 0 ? "E" : "W"}`;
  const rows = [];
  for (const [name, v] of Object.entries(c.values)) {
    const s = state.world.fields[name]; let shown;
    if (s.kind === "direction") {
      const pair = s.shape === "month_cell" ? [v[(state.month - 1) * 2], v[(state.month - 1) * 2 + 1]] : v;
      const sp = Math.hypot(pair[0], pair[1]);
      shown = `${fmt(sp, s.unit)}, toward ${((Math.atan2(pair[0], pair[1]) * 180 / Math.PI + 360) % 360).toFixed(0)}° from north`;
    } else if (s.kind === "category") shown = (Array.isArray(v) ? v[state.month - 1] : v).replace(/_/g, " ");
    else if (s.kind === "boolean") shown = v ? "true" : "false";
    else if (s.kind === "index") shown = named(name, v);
    else if (Array.isArray(v)) { const ok = v.filter((x) => x !== null); const mean = ok.reduce((a, b) => a + b, 0) / Math.max(ok.length, 1);
      shown = `${fmt(v[state.month - 1], s.unit)} <span class="muted">(year ${fmt(mean, "")})</span>`; }
    else shown = fmt(v, s.unit);
    rows.push(`<tr class="${name === state.field ? "current" : ""}"><td>${name.replace(/_/g, " ")}</td><td class="num">${shown}</td></tr>`);
  }
  if (isDaily() && state.data) { const s = spec(), v = state.data[id];
    rows.unshift(`<tr class="current"><td>${state.field.replace(/_/g, " ")} (day ${state.day})</td><td class="num">${fmt(v, s.unit)}</td></tr>`); }
  $("cellvalues").innerHTML = `<table><thead><tr><th>Field</th><th>Value (month ${state.month})</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  const why = $("why"), q = new URLSearchParams({ cell: id, field: state.field });
  if (isDaily()) q.set("day", state.day);  // a day's field: the server works the day out with its cause records
  const asked = q.toString(); state.whyAsked = asked;
  why.innerHTML = `<p class="muted small">asking why…</p>`;
  try {
    const a = await getJSON("/api/explain?" + asked);
    if (state.whyAsked !== asked) return;  // another cell, field or day was asked for meanwhile: its answer is the one to show
    const items = a.chain.map((st) => `<li class="${st.push ? "push" : ""}">${st.text.replace(/</g, "&lt;")}</li>`).join("");
    why.innerHTML = `<h2>Why is ${state.field.replace(/_/g, " ")} like this here${a.day !== undefined ? ` on day ${a.day}` : ""}?</h2>` +
      a.notices.map((n) => `<div class="notice">${n}</div>`).join("") + `<ol>${items}</ol>`;
  } catch (e) { if (state.whyAsked === asked) why.innerHTML = `<p class="muted small">No "why" answer: ${e.message}</p>`; }
}

// ---------------------------------------------------------------- controls
function togglePlay() {
  const b = $("play");
  if (state.playing) { clearInterval(state.playing); state.playing = null; b.textContent = "Play"; b.setAttribute("aria-pressed", "false"); return; }
  b.textContent = "Pause"; b.setAttribute("aria-pressed", "true");
  state.playing = setInterval(async () => { state.month = state.month % state.world.meta.months + 1; $("month").value = state.month;
    $("monthlabel").textContent = state.month; await showMonth(); }, 700);
}
function frameLabel() {
  const h = state.world.history, n = h.rounds.length;
  $("framelabel").textContent = state.frame < 0 || state.frame >= n ? "the end of the history"
    : `${h.times_my[state.frame].toFixed(0)} My into the history`;
}
async function showFrame(i) {
  const n = state.world.history.rounds.length;
  state.frame = i >= n ? -1 : i; $("frame").value = i >= n || i < 0 ? n : i; frameLabel(); await loadField();
}
function toggleFilm() {
  const b = $("playhist");
  if (state.filming) { clearInterval(state.filming); state.filming = null; b.textContent = "Play"; b.setAttribute("aria-pressed", "false"); return; }
  b.textContent = "Pause"; b.setAttribute("aria-pressed", "true");
  const n = state.world.history.rounds.length;
  if (state.frame < 0) state.frame = n;
  state.filming = setInterval(async () => { await showFrame(state.frame < 0 ? 0 : (state.frame + 1) % (n + 1)); }, 450);
}
function dayLabel() {
  const per = state.world.weather.days_per_year, year = Math.floor(state.day / per);
  $("daylabel").textContent = `${state.day} (year ${year}, day ${Math.floor(state.day - year * per) + 1} of the year)`;
}
async function showDay(d) {
  state.day = Math.max(0, d); $("day").value = state.day; dayLabel(); await loadField();
  if (state.selected >= 0) showCell(state.selected);
}
function toggleDays() {
  const b = $("playdays");
  if (state.stepping) { clearInterval(state.stepping); state.stepping = null; b.textContent = "Play"; b.setAttribute("aria-pressed", "false"); return; }
  b.textContent = "Pause"; b.setAttribute("aria-pressed", "true");
  let busy = false;                        // a day takes the server a moment: the next is asked for when this one is drawn
  state.stepping = setInterval(async () => { if (busy) return; busy = true;
    try { await showDay((state.day + 1) % (+$("day").max + 1)); } finally { busy = false; } }, 250);
}
function setView(flat) {
  state.flat = flat; state.zoom = flat ? 1 : 0.92; state.panX = state.panY = 0;
  $("viewflat").setAttribute("aria-pressed", String(flat)); $("viewglobe").setAttribute("aria-pressed", String(!flat)); draw();
}
function showScale() {                     // a bar of a round number of kilometres, for the middle of the view
  if (!state.world || !canvas.clientHeight) return;
  const kmPerPx = state.world.planet.radius_m / 1000 / pxPerRad(canvas.clientHeight, canvas.clientWidth / canvas.clientHeight);
  const most = 120 * kmPerPx, ten = 10 ** Math.floor(Math.log10(most)), km = [5, 2, 1].map((k) => k * ten).find((k) => k <= most);
  $("scalebar").style.width = `${km / kmPerPx}px`;
  $("scaletext").textContent = `${km.toLocaleString()} km` + (state.flat ? " north to south" : "");
}
// Zoom to `zoom`, keeping the place under a point of the window (cx, cy) under it; without a point, about the middle.
function zoomTo(zoom, cx, cy) {
  const z0 = state.zoom, z1 = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom));
  if (z1 === z0) return;
  const rect = canvas.getBoundingClientRect(), pointed = cx !== undefined;
  if (state.flat && pointed) {
    const x = ((cx - rect.left) / rect.width * 2 - 1) * (rect.width / rect.height), y = 1 - (cy - rect.top) / rect.height * 2;
    const fit = Math.min(1, rect.width / rect.height / 2), k = 1 / z0 - 1 / z1;
    state.panX += x / 2 / fit * k; state.panY = Math.max(-1, Math.min(1, state.panY + y / fit * k)); state.zoom = z1;
  } else if (!state.flat && pointed) {
    const before = screenToLatLon(cx, cy); state.zoom = z1;
    for (let pass = 0; before && pass < 3; pass++) {       // turn the globe until that place is under the point again
      const now = screenToLatLon(cx, cy); if (!now) break;
      state.lon0 += ((before[1] - now[1] + 540) % 360) - 180; state.lat0 = Math.max(-90, Math.min(90, state.lat0 + before[0] - now[0]));
    }
  } else state.zoom = z1;
  draw();
}
function wire() {
  $("field").addEventListener("change", (e) => { state.field = e.target.value; state.part = ""; $("part").value = ""; setLook("data"); });
  $("part").addEventListener("change", (e) => { state.part = e.target.value; selectField(); });
  $("month").addEventListener("input", async (e) => { state.month = +e.target.value; $("monthlabel").textContent = state.month; await showMonth();
    if (state.selected >= 0) showCell(state.selected); });
  $("play").addEventListener("click", togglePlay);
  $("frame").addEventListener("input", (e) => showFrame(+e.target.value));
  $("playhist").addEventListener("click", toggleFilm);
  $("day").addEventListener("input", (e) => showDay(+e.target.value));
  $("playdays").addEventListener("click", toggleDays);
  $("viewglobe").addEventListener("click", () => setView(false)); $("viewflat").addEventListener("click", () => setView(true));
  $("lookmap").addEventListener("click", () => setLook("map")); $("lookdata").addEventListener("click", () => setLook("data"));
  $("smooth").addEventListener("change", (e) => { state.smooth = e.target.checked; draw(); });
  $("season").addEventListener("change", (e) => { state.season = e.target.checked; monthRow(); if (state.map) { redrawMap(); draw(); } });
  $("finer").addEventListener("change", (e) => { state.finer = e.target.checked; considerDetail.last = null; considerDetail(); });
  $("zoomin").addEventListener("click", () => zoomTo(state.zoom * 1.6)); $("zoomout").addEventListener("click", () => zoomTo(state.zoom / 1.6));
  $("zoomreset").addEventListener("click", () => setView(state.flat));
  const touching = new Map(); let drag = null, pinch = null;          // one finger or the mouse drags; two fingers pinch
  const spread = () => { const [a, b] = [...touching.values()]; return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
  canvas.addEventListener("pointerdown", (e) => { touching.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* a pointer the browser no longer holds */ }
    canvas.classList.add("dragging");
    if (touching.size === 2) { pinch = { ...spread(), zoom: state.zoom }; if (drag) drag.moved = true; }
    else drag = { x: e.clientX, y: e.clientY, moved: false }; });
  canvas.addEventListener("pointermove", (e) => {
    if (touching.has(e.pointerId)) touching.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && touching.size === 2) { const now = spread(); zoomTo(pinch.zoom * now.d / pinch.d, now.x, now.y); return; }
    const ll = screenToLatLon(e.clientX, e.clientY);
    if (ll && state.look === "map" && state.map) { const f = fineAt(ll), d = state.detail;
      $("status").textContent = `${place(ll)} · ` + (f < 0 ? drawnAt(cellAt(ll[0], ll[1])) :
        `finer cell: ${d.sea[f] ? `sea, ${fmt(-d.height[f], "m")} deep` : `${d.lake[f] ? "lake" : "land"}, ${fmt(d.height[f], "m")} above the sea`}` +
        (d.flow[f] > 0 ? `, a river of ${fmt(d.flow[f], "m³/s")}` : "")); }
    else if (ll && state.data) { const id = cellAt(ll[0], ll[1]), v = state.data[id], s = spec();
      const shown = s.kind === "category" ? (s.categories[v] || `no class (code ${v})`).replace(/_/g, " ") : s.kind === "boolean" ? (v ? "true" : "false")
        : s.kind === "index" ? named(state.field, v) : fmt(v, s.unit);
      $("status").textContent = `${place(ll)} · ${shown}`; }
    if (!drag || pinch) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    const k = 2 / canvas.clientHeight / state.zoom;
    if (state.flat) { const fit = Math.min(1, canvas.clientWidth / canvas.clientHeight / 2);
      state.panX -= dx * k / fit / 2; state.panY = Math.max(-1, Math.min(1, state.panY + dy * k / fit)); }   // the map spans two units of pan across, one up
    else { state.lon0 -= dx * k * 60; state.lat0 = Math.max(-90, Math.min(90, state.lat0 + dy * k * 60)); }
    drag.x = e.clientX; drag.y = e.clientY; draw();
  });
  const lift = (e) => { touching.delete(e.pointerId); if (!touching.size) { canvas.classList.remove("dragging"); pinch = null; } };
  canvas.addEventListener("pointerup", (e) => { const was = drag, pinched = pinch; lift(e);
    if (was && !was.moved && !pinched) { const ll = screenToLatLon(e.clientX, e.clientY); if (ll) showCell(cellAt(ll[0], ll[1])); }
    if (!touching.size) drag = null; });
  canvas.addEventListener("pointercancel", (e) => { lift(e); drag = null; });
  // the wheel, and a pinch on a trackpad, which most browsers send as the wheel with the control key down
  canvas.addEventListener("wheel", (e) => { e.preventDefault();
    zoomTo(state.zoom * Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0015)), e.clientX, e.clientY); }, { passive: false });
  let gesture = 1;                         // Safari sends a pinch on a trackpad as a gesture of its own
  canvas.addEventListener("gesturestart", (e) => { e.preventDefault(); gesture = state.zoom; });
  canvas.addEventListener("gesturechange", (e) => { e.preventDefault(); zoomTo(gesture * e.scale, e.clientX, e.clientY); });
  canvas.addEventListener("dblclick", (e) => { e.preventDefault(); zoomTo(state.zoom * (e.shiftKey ? 0.5 : 2), e.clientX, e.clientY); });
  canvas.addEventListener("keydown", (e) => {
    const step = 60 * 2 / canvas.clientHeight / state.zoom, move = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[e.key];
    if (e.key === "+" || e.key === "=") zoomTo(state.zoom * 1.6);
    else if (e.key === "-" || e.key === "_") zoomTo(state.zoom / 1.6);
    else if (e.key === "0") setView(state.flat);
    else if (move && state.flat) { const fit = Math.min(1, canvas.clientWidth / canvas.clientHeight / 2);
      state.panX += move[0] * step / fit / 2; state.panY = Math.max(-1, Math.min(1, state.panY + move[1] * step / fit)); draw(); }
    else if (move) { state.lon0 += move[0] * step * 60; state.lat0 = Math.max(-90, Math.min(90, state.lat0 + move[1] * step * 60)); draw(); }
    else return;
    e.preventDefault();
  });
  window.addEventListener("resize", draw);
}
function place(ll) { return `${Math.abs(ll[0]).toFixed(1)}° ${ll[0] >= 0 ? "N" : "S"}, ${Math.abs(ll[1]).toFixed(1)}° ${ll[1] >= 0 ? "E" : "W"}`; }
function drawnAt(id) {                     // in the illustrated look: what the cell under the pointer holds of what is drawn
  const m = state.map, h = m.height[id];
  if (m.sea[id]) return `sea, ${fmt(-h, "m")} deep`;
  const name = m.biome && m.names[m.biome[id]] ? m.names[m.biome[id]].replace(/_/g, " ") : "land";
  return `${m.lake && m.lake[id] >= 0.5 ? "lake" : name}, ${fmt(h, "m")} above the sea`;
}
function asked0() { return new URLSearchParams(location.search); }
async function start() {
  if (!initGL()) return;
  wire(); draw();
  const w = state.world = await getJSON("/api/world");
  const m = w.meta;
  $("worldinfo").textContent = `${m.cells.toLocaleString()} cells · profile ${m.profile} · seed ${w.seed} · engine ${w.engine_version}`;
  const msgs = [...w.notices, ...w.warnings];
  if (m.fantasy && m.fantasy.length)                        // an invented layer laid over the physics (data/fantasy/)
    msgs.unshift(`This world carries the invented fantasy layer ${m.fantasy.join(", ")}: the fields it adds follow made-up rules ` +
                 "and claim nothing about any real world.");
  $("month").max = m.months;
  if (w.weather && w.weather.why_not) msgs.push(w.weather.why_not);
  if (w.weather && Object.keys(w.weather.fields).length) {        // the fields of a day join the list: worked out on request
    for (const [name, s] of Object.entries(w.weather.fields)) w.fields[name] = { ...s, family: s.family + " (one day)" };
    $("day").max = Math.ceil(w.weather.days_per_year) * 10 - 1;
    if (asked0().has("day")) state.day = Math.max(0, +asked0().get("day"));
    $("day").value = state.day; dayLabel();
  }
  if (msgs.length) { $("banner").hidden = false; $("banner").innerHTML = msgs.map((t) => `<p>${t}</p>`).join(""); }
  const groups = {};
  for (const [name, s] of Object.entries(w.fields)) (groups[s.family] = groups[s.family] || []).push(name);
  const sel = $("field");
  for (const [fam, names] of Object.entries(groups)) { const og = document.createElement("optgroup"); og.label = fam;
    for (const n of names) { const o = document.createElement("option"); o.value = n; o.textContent = n.replace(/_/g, " "); og.append(o); } sel.append(og); }
  const asked = new URLSearchParams(location.search);       // ?field=biome&lat=48&lon=-20&month=7&view=flat
  if (asked.has("lat")) state.lat0 = Math.max(-90, Math.min(90, +asked.get("lat")));
  if (asked.has("lon")) state.lon0 = +asked.get("lon");
  if (asked.has("month")) { state.month = Math.max(1, Math.min(m.months, +asked.get("month"))); $("month").value = state.month; $("monthlabel").textContent = state.month; }
  if (asked.get("view") === "flat") setView(true);
  if (asked.has("zoom")) state.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, +asked.get("zoom") || state.zoom));
  if (asked.has("smooth")) { state.smooth = true; $("smooth").checked = true; }
  if (asked.has("season")) { state.season = true; $("season").checked = true; }
  if (asked.get("finer") === "0") { state.finer = false; $("finer").checked = false; }
  const hist = w.history || { rounds: [], times_my: [], fields: [] };
  w.history = hist;
  $("frame").max = hist.rounds.length; $("frame").value = hist.rounds.length;
  if (asked.has("frame")) { const f = +asked.get("frame"); state.frame = f >= 0 && f < hist.rounds.length ? f : -1; $("frame").value = state.frame < 0 ? hist.rounds.length : state.frame; }
  if (hist.rounds.length) frameLabel();
  const want = asked.get("field");
  state.field = want && w.fields[want] ? want : ["biome", "elevation", "latitude"].find((n) => w.fields[n]) || Object.keys(w.fields)[0];
  sel.value = state.field;
  $("status").textContent = "preparing the map of cells…";
  const width = m.cells > 100000 ? 4096 : m.cells > 20000 ? 2048 : 1024;
  state.idmap = new Uint32Array(await getBuffer("/api/idmap?width=" + width)); state.idW = width; state.idH = width / 2;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex.ids);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32UI, state.idW, state.idH, 0, gl.RED_INTEGER, gl.UNSIGNED_INT, state.idmap);
  if (w.fields.ocean_mask) {                                // where the sea lies, for the cells a log scale has no colour for
    state.sea = new Float32Array(await getBuffer("/api/field?name=ocean_mask"));
    const [filled, h] = padded(state.sea);
    gl.activeTexture(gl.TEXTURE4); gl.bindTexture(gl.TEXTURE_2D, tex.sea);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, DATA_W, h, 0, gl.RED, gl.FLOAT, filled);
    gl.uniform1i(uni.uHasSea, 1);
  }
  try { await loadMesh(); } catch (e) { console.warn("no mesh from the server: the cells' borders follow the grid", e); }
  $("lookrow").hidden = !canDraw();
  // the drawing is what a world opens with; a request that names a field (?field=) asks for the data look
  document.body.dataset.look = "data";
  await selectField();
  if ((asked.get("look") || (asked.has("field") ? "data" : "map")) === "map" && canDraw()) await setLook("map");
  $("status").textContent = "";
  window.viewerReady = true;
}
start().catch((e) => { $("status").textContent = "The viewer stopped: " + e.message; console.error(e); });
