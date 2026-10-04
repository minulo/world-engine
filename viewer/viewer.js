// World viewer. It reads one world through the engine's local server and draws any stored field
// on a globe or a flat map. No third-party code: one WebGL2 fragment shader does the drawing.
"use strict";

const $ = (id) => document.getElementById(id);
const DATA_W = 1024;
const state = {
  world: null, field: null, part: "", month: 1, flat: false, lon0: 0, lat0: 20, zoom: 0.92, panX: 0, panY: 0,
  idmap: null, idW: 0, idH: 0, data: null, stats: null, selected: -1, playing: null, cache: new Map(),
};

// ---------------------------------------------------------------- colour
const MAPS = {
  viridis: ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725"],
  thermal: ["#1b2a6b", "#2b5fb0", "#5aa5d6", "#b5dbe8", "#f5f1d8", "#f7c56b", "#ec7f3b", "#c8321f", "#7a0f17"],
  rain: ["#f4efe1", "#d9e7c5", "#a3d3a8", "#5cb6a4", "#2f8fb0", "#2b63a8", "#3a3a8f", "#4a1d6e"],
  diverging: ["#2b3f8f", "#5c86c9", "#a9c8e8", "#f2f2f2", "#f0b8a0", "#d6694d", "#9b1c1c"],
  terrain: ["#0a1f4d", "#1b4a8a", "#3f86c2", "#9fd0e6", "#5f9d58", "#b8b56a", "#b08a57", "#8a6a55", "#f4f4f4"],
};
const SPLIT_AT = { terrain: 4 };          // where a map breaks at zero: water colours below, land colours above
const FIELD_MAP = {
  elevation: ["terrain", true], height_above_sea: ["terrain", true], surface_temperature: ["thermal", false],
  precipitation: ["rain", false], snowfall: ["rain", false], column_water: ["rain", false], ocean_evaporation: ["rain", false],
  subsidence: ["diverging", true], convergence_rate: ["diverging", true], coriolis_parameter: ["diverging", true],
  latitude: ["diverging", true], longitude: ["diverging", true],
};
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
const VS = `#version 300 es
in vec2 aPos; out vec2 vPos; void main() { vPos = aPos; gl_Position = vec4(aPos, 0.0, 1.0); }`;
const FS = `#version 300 es
precision highp float; precision highp int; precision highp usampler2D;
uniform usampler2D uIds; uniform sampler2D uData; uniform sampler2D uLut; uniform sampler2D uPal;
uniform int uFlat, uCategorical, uSplit, uSel, uReady; uniform ivec2 uIdSize; uniform mat3 uRot;
uniform float uZoom, uLo, uHi, uAspect; uniform vec2 uPan; uniform vec3 uSpace;
in vec2 vPos; out vec4 frag;
const float PI = 3.141592653589793;
void main() {
  vec2 p = vec2(vPos.x * uAspect, vPos.y);
  float lat, lon, shade = 1.0;
  if (uFlat == 1) {
    float fit = min(1.0, uAspect / 2.0);                 // the whole map fits the canvas at zoom 1
    lon = (vPos.x * uAspect / 2.0 / fit / uZoom + uPan.x) * PI; lat = (vPos.y / fit / uZoom + uPan.y) * PI / 2.0;
    if (abs(lat) > PI / 2.0) { frag = vec4(uSpace, 1.0); return; }
    lon = mod(lon + PI, 2.0 * PI) - PI;
  } else {
    vec2 q = p / uZoom; float r2 = dot(q, q);
    if (r2 > 1.0) { frag = vec4(uSpace, 1.0); return; }
    float z = sqrt(1.0 - r2); vec3 w = uRot * vec3(q, z);
    lat = asin(clamp(w.z, -1.0, 1.0)); lon = atan(w.y, w.x); shade = 0.72 + 0.28 * z;
  }
  if (uReady == 0) { frag = vec4(vec3(0.25) * shade, 1.0); return; }
  int ix = clamp(int(floor((lon + PI) / (2.0 * PI) * float(uIdSize.x))), 0, uIdSize.x - 1);
  int iy = clamp(int(floor((PI / 2.0 - lat) / PI * float(uIdSize.y))), 0, uIdSize.y - 1);
  int id = int(texelFetch(uIds, ivec2(ix, iy), 0).r);
  float v = texelFetch(uData, ivec2(id % ${DATA_W}, id / ${DATA_W}), 0).r;
  vec3 c;
  if (isnan(v)) c = vec3(0.45);
  else if (uCategorical == 1) c = texelFetch(uPal, ivec2(int(v + 0.5), 0), 0).rgb;
  else {
    float t;
    if (uSplit == 1) t = v <= 0.0 ? 0.498 - 0.498 * clamp(v / min(uLo, -1e-30), 0.0, 1.0) : 0.502 + 0.498 * clamp(v / max(uHi, 1e-30), 0.0, 1.0);
    else t = clamp((v - uLo) / max(uHi - uLo, 1e-30), 0.0, 1.0);
    c = texture(uLut, vec2(t, 0.5)).rgb;
  }
  if (id == uSel) c = mix(c, vec3(1.0), 0.65);
  frag = vec4(c * shade, 1.0);
}`;
let prog, uni = {}, tex = {};
function initGL() {
  if (!gl) { $("status").textContent = "This browser has no WebGL2, which the viewer needs."; return false; }
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  gl.useProgram(prog);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "aPos"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  for (const n of ["uIds", "uData", "uLut", "uPal", "uFlat", "uCategorical", "uSplit", "uSel", "uReady", "uIdSize", "uRot", "uZoom",
    "uLo", "uHi", "uAspect", "uPan", "uSpace"]) uni[n] = gl.getUniformLocation(prog, n);
  ["ids", "data", "lut", "pal"].forEach((n, i) => { tex[n] = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + i);
    gl.bindTexture(gl.TEXTURE_2D, tex[n]);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, n === "lut" ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, n === "lut" ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); });
  gl.uniform1i(uni.uIds, 0); gl.uniform1i(uni.uData, 1); gl.uniform1i(uni.uLut, 2); gl.uniform1i(uni.uPal, 3);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  return true;
}
function rotation() {
  const la = state.lat0 * Math.PI / 180, lo = state.lon0 * Math.PI / 180;
  const f = [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
  const r = [-Math.sin(lo), Math.cos(lo), 0];
  const u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]];
  return { r, u, f };
}
function draw() {
  if (!prog) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2), w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  const { r, u, f } = rotation();
  gl.uniformMatrix3fv(uni.uRot, false, new Float32Array([...r, ...u, ...f]));
  gl.uniform1i(uni.uFlat, state.flat ? 1 : 0); gl.uniform1f(uni.uZoom, state.zoom); gl.uniform1f(uni.uAspect, w / h);
  gl.uniform2f(uni.uPan, state.panX, state.panY); gl.uniform1i(uni.uSel, state.selected);
  gl.uniform1i(uni.uReady, state.idmap && state.data ? 1 : 0); gl.uniform2i(uni.uIdSize, state.idW, state.idH);
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  gl.uniform3f(uni.uSpace, dark ? 0.02 : 0.043, dark ? 0.027 : 0.059, dark ? 0.043 : 0.09);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
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
function cellAt(lat, lon) {
  if (!state.idmap) return -1;
  const ix = Math.min(state.idW - 1, Math.max(0, Math.floor((lon + 180) / 360 * state.idW)));
  const iy = Math.min(state.idH - 1, Math.max(0, Math.floor((90 - lat) / 180 * state.idH)));
  return state.idmap[iy * state.idW + ix];
}

// ---------------------------------------------------------------- data
async function getJSON(url) { const r = await fetch(url); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j; }
async function getBuffer(url) { const r = await fetch(url); if (!r.ok) throw new Error((await r.json()).error || r.statusText); return r.arrayBuffer(); }
function spec() { return state.world.fields[state.field]; }
function isMonthly() { return spec().shape === "month_cell"; }
async function loadField() {
  const s = spec(), key = `${state.field}|${isMonthly() ? state.month : 0}|${state.part}`;
  let arr = state.cache.get(key);
  if (!arr) {
    const q = new URLSearchParams({ name: state.field });
    if (isMonthly()) q.set("month", state.month);
    if (s.kind === "direction" && state.part) q.set("part", state.part);
    arr = new Float32Array(await getBuffer("/api/field?" + q));
    if (state.cache.size > 80) state.cache.clear();
    state.cache.set(key, arr);
  }
  state.data = arr;
  const h = Math.ceil(arr.length / DATA_W), padded = new Float32Array(DATA_W * h); padded.set(arr);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, tex.data);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, DATA_W, h, 0, gl.RED, gl.FLOAT, padded);
  draw();
}
function fmt(v, unit) {
  if (v === null || v === undefined || Number.isNaN(v)) return "undefined";
  const a = Math.abs(v); let t;
  if (a !== 0 && (a < 0.01 || a >= 1e6)) t = v.toExponential(2); else t = a >= 1000 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2);
  return unit && !/^(category|index|true or false|0 to 1)$/.test(unit) ? `${t} ${unit}` : t;
}
async function selectField() {
  const s = spec(), cat = s.kind === "category" || s.kind === "boolean";
  $("fielddesc").textContent = s.description || "";
  $("partrow").hidden = s.kind !== "direction";
  $("monthrow").style.opacity = isMonthly() ? 1 : 0.4; $("month").disabled = $("play").disabled = !isMonthly();
  if (!isMonthly() && state.playing) togglePlay();
  const [mapName, split0] = FIELD_MAP[state.field] || ["viridis", false];
  let lo = 0, hi = 1, split = false;
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
    legend.append(ul);
  } else {
    state.stats = await getJSON("/api/stats?name=" + encodeURIComponent(state.field));
    lo = state.stats.low ?? 0; hi = state.stats.high ?? 1;
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
    ends.innerHTML = `<span>${fmt(lo, "")}</span>${mid}<span>${fmt(hi, s.unit)}</span>`;
    legend.append(bar, ends);
    await loadField();
  }
  gl.uniform1i(uni.uCategorical, cat ? 1 : 0); gl.uniform1i(uni.uSplit, split ? 1 : 0);
  gl.uniform1f(uni.uLo, lo); gl.uniform1f(uni.uHi, hi);
  const line = state.world.lineage[state.field], m = line && state.world.models[line.writer];
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
    else if (Array.isArray(v)) { const ok = v.filter((x) => x !== null); const mean = ok.reduce((a, b) => a + b, 0) / Math.max(ok.length, 1);
      shown = `${fmt(v[state.month - 1], s.unit)} <span class="muted">(year ${fmt(mean, "")})</span>`; }
    else shown = fmt(v, s.unit);
    rows.push(`<tr class="${name === state.field ? "current" : ""}"><td>${name.replace(/_/g, " ")}</td><td class="num">${shown}</td></tr>`);
  }
  $("cellvalues").innerHTML = `<table><thead><tr><th>Field</th><th>Value (month ${state.month})</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  const why = $("why"); why.innerHTML = `<p class="muted small">asking why…</p>`;
  try {
    const a = await getJSON(`/api/explain?cell=${id}&field=${encodeURIComponent(state.field)}`);
    const items = a.chain.map((st) => `<li class="${st.push ? "push" : ""}">${st.text.replace(/</g, "&lt;")}</li>`).join("");
    why.innerHTML = `<h2>Why is ${state.field.replace(/_/g, " ")} like this here?</h2>` +
      a.notices.map((n) => `<div class="notice">${n}</div>`).join("") + `<ol>${items}</ol>`;
  } catch (e) { why.innerHTML = `<p class="muted small">No "why" answer: ${e.message}</p>`; }
}

// ---------------------------------------------------------------- controls
function togglePlay() {
  const b = $("play");
  if (state.playing) { clearInterval(state.playing); state.playing = null; b.textContent = "Play"; b.setAttribute("aria-pressed", "false"); return; }
  b.textContent = "Pause"; b.setAttribute("aria-pressed", "true");
  state.playing = setInterval(async () => { state.month = state.month % state.world.meta.months + 1; $("month").value = state.month;
    $("monthlabel").textContent = state.month; await loadField(); }, 700);
}
function setView(flat) {
  state.flat = flat; state.zoom = flat ? 1 : 0.92; state.panX = state.panY = 0;
  $("viewflat").setAttribute("aria-pressed", String(flat)); $("viewglobe").setAttribute("aria-pressed", String(!flat)); draw();
}
function wire() {
  $("field").addEventListener("change", (e) => { state.field = e.target.value; state.part = ""; $("part").value = ""; selectField(); });
  $("part").addEventListener("change", (e) => { state.part = e.target.value; selectField(); });
  $("month").addEventListener("input", async (e) => { state.month = +e.target.value; $("monthlabel").textContent = state.month; await loadField();
    if (state.selected >= 0) showCell(state.selected); });
  $("play").addEventListener("click", togglePlay);
  $("viewglobe").addEventListener("click", () => setView(false)); $("viewflat").addEventListener("click", () => setView(true));
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, moved: false }; canvas.setPointerCapture(e.pointerId); canvas.classList.add("dragging"); });
  canvas.addEventListener("pointermove", (e) => {
    const ll = screenToLatLon(e.clientX, e.clientY);
    if (ll && state.data) { const id = cellAt(ll[0], ll[1]), v = state.data[id], s = spec();
      const shown = s.kind === "category" ? s.categories[v].replace(/_/g, " ") : s.kind === "boolean" ? (v ? "true" : "false") : fmt(v, s.unit);
      $("status").textContent = `${Math.abs(ll[0]).toFixed(1)}° ${ll[0] >= 0 ? "N" : "S"}, ${Math.abs(ll[1]).toFixed(1)}° ${ll[1] >= 0 ? "E" : "W"} · ${shown}`; }
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    const k = 2 / canvas.clientHeight / state.zoom;
    if (state.flat) { const fit = Math.min(1, canvas.clientWidth / canvas.clientHeight / 2);
      state.panX -= dx * k / fit; state.panY = Math.max(-1, Math.min(1, state.panY + dy * k / fit)); }
    else { state.lon0 -= dx * k * 60; state.lat0 = Math.max(-90, Math.min(90, state.lat0 + dy * k * 60)); }
    drag.x = e.clientX; drag.y = e.clientY; draw();
  });
  canvas.addEventListener("pointerup", (e) => { canvas.classList.remove("dragging");
    if (drag && !drag.moved) { const ll = screenToLatLon(e.clientX, e.clientY); if (ll) showCell(cellAt(ll[0], ll[1])); } drag = null; });
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); state.zoom = Math.max(0.5, Math.min(40, state.zoom * Math.exp(-e.deltaY * 0.0015))); draw(); }, { passive: false });
  window.addEventListener("resize", draw);
}
async function start() {
  if (!initGL()) return;
  wire(); draw();
  const w = state.world = await getJSON("/api/world");
  const m = w.meta;
  $("worldinfo").textContent = `${m.cells.toLocaleString()} cells · profile ${m.profile} · seed ${w.seed} · engine ${w.engine_version}`;
  const msgs = [...w.notices, ...w.warnings];
  if (msgs.length) { $("banner").hidden = false; $("banner").innerHTML = msgs.map((t) => `<p>${t}</p>`).join(""); }
  $("month").max = m.months;
  const groups = {};
  for (const [name, s] of Object.entries(w.fields)) (groups[s.family] = groups[s.family] || []).push(name);
  const sel = $("field");
  for (const [fam, names] of Object.entries(groups)) { const og = document.createElement("optgroup"); og.label = fam;
    for (const n of names) { const o = document.createElement("option"); o.value = n; o.textContent = n.replace(/_/g, " "); og.append(o); } sel.append(og); }
  const want = new URLSearchParams(location.search).get("field");
  state.field = want && w.fields[want] ? want : ["biome", "elevation", "latitude"].find((n) => w.fields[n]) || Object.keys(w.fields)[0];
  sel.value = state.field;
  $("status").textContent = "preparing the map of cells…";
  const width = m.cells > 100000 ? 4096 : m.cells > 20000 ? 2048 : 1024;
  state.idmap = new Uint32Array(await getBuffer("/api/idmap?width=" + width)); state.idW = width; state.idH = width / 2;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex.ids);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32UI, state.idW, state.idH, 0, gl.RED_INTEGER, gl.UNSIGNED_INT, state.idmap);
  await selectField();
  $("status").textContent = "";
  window.viewerReady = true;
}
start().catch((e) => { $("status").textContent = "The viewer stopped: " + e.message; console.error(e); });
