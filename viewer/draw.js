// What the viewer draws with: its shaders, and the arithmetic that prepares a world for them. No third-party code.
//
// Two looks share one way of finding the cell under a point of the canvas (a grid of nearest cells, then the nearest
// of that cell and its neighbours, so that a cell's borders are exact at any zoom):
//   * the data look paints each cell with the colour of one stored field, exactly as stored;
//   * the illustrated look is a drawing of the world, made from several of its fields at once: sea and land, heights,
//     biomes, ice, lakes and rivers.
// The illustrated look is a drawing, not a result. Everything in it that is smaller than a cell is the viewer's hand:
// the bends of the coasts and of the rivers between the centres of the cells, the ridges on the mountains, the lines
// in the shadows. The cells' stored values stay one click away, and the data look shows them untouched.
"use strict";

const DATA_W = 1024;                      // a value for each cell lies in a texture this wide
const DRAWING = {
  kernel: 1.0,                            // a cell's weight reaches this many of its own spacings, and is nothing beyond
  warp: 0.42,                             // how far the coasts are bent, in spacings of the cells, at the largest bend
  warpStep: 1.6,                          // the largest bend is this many spacings long; each next one half as long
  reliefM: 950.0,                         // a rise of this many metres from one cell to the next is drawn as a 45 degree slope
  ruggedM: 1100.0,                        // where the heights change this much from cell to cell, the drawn ridges are at their strongest
  riverParts: 16,                         // a river's way from one cell to the next is drawn in this many straight parts
  riverFloor: 0.004,                      // rivers below this share of the largest flows are not drawn at any zoom
};
const INK = [0.168, 0.137, 0.2];

// ---------------------------------------------------------------- shaders
const GLSL_HEAD = `#version 300 es
precision highp float; precision highp int; precision highp sampler2D; precision highp usampler2D;
uniform usampler2D uIds; uniform sampler2D uPos; uniform sampler2D uNbr;
uniform ivec2 uIdSize; uniform int uFlat, uReady, uSel, uMesh; uniform mat3 uRot;
uniform float uZoom, uAspect, uPxPerRad, uCell; uniform vec2 uPan; uniform vec3 uSpace;
// the finer cells that the engine worked out for one region (the detail), where there are any: their own grid of
// nearest cells on the flat sheet that touches the sphere at the region's middle, their places and their neighbours
uniform usampler2D uFIds; uniform sampler2D uFPos; uniform sampler2D uFNbr;
uniform int uFine, uFSize; uniform vec3 uFCentre, uFEast, uFNorth; uniform float uFHalf, uFCell, uFIn, uFOut;
const float PI = 3.141592653589793;
const int DW = ${DATA_W};
const float KERNEL = ${DRAWING.kernel.toFixed(3)};
ivec2 at(int id) { return ivec2(id % DW, id / DW); }
// The place on the sphere under a point of the canvas (p runs from -1 to 1 both ways). w is always a place: beyond
// the map's edge it is the nearest place on the edge, and "beyond" says how many pixels outside the point lies.
void place(vec2 p, out vec3 w, out float shade, out float beyond) {
  if (uFlat == 1) {
    float fit = min(1.0, uAspect / 2.0);                 // the whole map fits the canvas at zoom 1
    float lon = (p.x * uAspect / 2.0 / fit / uZoom + uPan.x) * PI, lat = (p.y / fit / uZoom + uPan.y) * PI / 2.0;
    beyond = (abs(lat) - PI / 2.0) * uPxPerRad; lat = clamp(lat, -PI / 2.0, PI / 2.0);
    w = vec3(cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)); shade = 1.0;
  } else {
    vec2 q = vec2(p.x * uAspect, p.y) / uZoom; float r = length(q);
    beyond = (r - 1.0) * uPxPerRad; if (r > 1.0) q /= r;
    float z = sqrt(max(0.0, 1.0 - dot(q, q))); w = uRot * vec3(q, z); shade = 0.72 + 0.28 * z;
  }
}
int gridCell(vec3 w) {
  float lat = asin(clamp(w.z, -1.0, 1.0)), lon = atan(w.y, w.x);
  int ix = clamp(int(floor((lon + PI) / (2.0 * PI) * float(uIdSize.x))), 0, uIdSize.x - 1);
  int iy = clamp(int(floor((PI / 2.0 - lat) / PI * float(uIdSize.y))), 0, uIdSize.y - 1);
  return int(texelFetch(uIds, ivec2(ix, iy), 0).r);
}
void nbrsOf(sampler2D nb, int c, out int n[6]) {         // the neighbours of a cell; -1 where it has only five
  ivec2 t = ivec2((c % DW) * 2, c / DW);
  vec4 a = texelFetch(nb, t, 0), b = texelFetch(nb, t + ivec2(1, 0), 0);
  n[0] = int(a.x); n[1] = int(a.y); n[2] = int(a.z); n[3] = int(a.w); n[4] = int(b.x); n[5] = int(b.y);
}
void nbrs(int c, out int n[6]) { nbrsOf(uNbr, c, n); }
int settle(sampler2D pos, sampler2D nb, vec3 w, int c) {  // from a cell near w to the cell whose centre is nearest, exactly
  int n[6]; nbrsOf(nb, c, n);
  float best = dot(w, texelFetch(pos, at(c), 0).xyz); int bc = c;
  for (int k = 0; k < 6; k++) if (n[k] >= 0) { float d = dot(w, texelFetch(pos, at(n[k]), 0).xyz); if (d > best) { best = d; bc = n[k]; } }
  return bc;
}
int nearest(vec3 w) { int c = gridCell(w); return uMesh == 0 ? c : settle(uPos, uNbr, w, c); }
int nearestFine(vec3 w) {                                 // the same among the detail's cells
  vec2 q = vec2(dot(w, uFEast), dot(w, uFNorth)) / uFHalf * 0.5 + 0.5;
  ivec2 t = clamp(ivec2(floor(q * float(uFSize))), ivec2(0), ivec2(uFSize - 1));
  return settle(uFPos, uFNbr, w, int(texelFetch(uFIds, t, 0).r));
}
float fineShare(vec3 w) {                                 // 1 well inside the detail's region, 0 outside it, and between near its edge
  return uFine == 1 ? 1.0 - smoothstep(uFIn, uFOut, acos(clamp(dot(w, uFCentre), -1.0, 1.0))) : 0.0;
}
float border(vec3 w, int c) {                             // how far w lies inside its cell c: radians to the nearest border
  int n[6]; nbrs(c, n); vec3 pc = texelFetch(uPos, at(c), 0).xyz; float dc = dot(w, pc), e = 1.0;
  for (int k = 0; k < 6; k++) if (n[k] >= 0) { vec3 pk = texelFetch(uPos, at(n[k]), 0).xyz; e = min(e, (dc - dot(w, pk)) / length(pc - pk)); }
  return e;
}
`;

const VS_QUAD = `#version 300 es
in vec2 aPos; out vec2 vPos; void main() { vPos = aPos; gl_Position = vec4(aPos, 0.0, 1.0); }`;

// The data look: one stored field, a colour for each cell.
function dataShader(noClass, noValue, nothingAtSea, nothingOnLand) {
  const v3 = (c) => `vec3(${c.map((x) => (x / 255).toFixed(3)).join(", ")})`;
  return GLSL_HEAD + `
uniform sampler2D uData; uniform sampler2D uLut; uniform sampler2D uPal; uniform sampler2D uSea;
uniform int uCategorical, uClasses, uSplit, uLog, uZeroNone, uHasSea, uSmooth; uniform float uLo, uHi;
in vec2 vPos; out vec4 frag;
float blended(vec3 w, int c, float own) {                 // the field between the centres of the cells, for the eye only
  int n[6]; nbrs(c, n); float sw = 0.0, sv = 0.0;
  for (int k = 0; k < 7; k++) {
    int j = k == 0 ? c : n[k - 1]; if (j < 0) continue;
    vec4 P = texelFetch(uPos, at(j), 0); float t = length(w - P.xyz) / (KERNEL * P.w); if (t >= 1.0) continue;
    float val = texelFetch(uData, at(j), 0).r; if (isnan(val)) continue;
    float q = 1.0 - t * t; q *= q; sw += q; sv += q * val;
  }
  return sw > 0.0 ? sv / sw : own;
}
void main() {
  vec3 w; float shade, beyond; place(vPos, w, shade, beyond);
  if (beyond > 0.0) { frag = vec4(uSpace, 1.0); return; }
  if (uReady == 0) { frag = vec4(vec3(0.25) * shade, 1.0); return; }
  int id = nearest(w);
  float v = texelFetch(uData, at(id), 0).r;
  bool smoothed = uSmooth == 1 && uMesh == 1 && uCategorical == 0;
  if (smoothed && !isnan(v)) v = blended(w, id, v);
  vec3 c;
  if (isnan(v)) c = ${v3(noValue)};
  else if (uCategorical == 1) {                           // a code outside the list of classes has a colour of its own
    int k = int(floor(v + 0.5));
    c = (k < 0 || k >= uClasses) ? ${v3(noClass)} : texelFetch(uPal, ivec2(k, 0), 0).rgb;
  }
  else if (uCategorical == 2) {                           // a number that names a thing (a plate, a basin): one colour each
    float k = floor(v + 0.5);
    if (k < 0.0 || (uZeroNone == 1 && k == 0.0)) c = ${v3(noValue)};
    else {
      float h = fract(k * 0.61803398875) * 6.0, l = 0.40 + 0.22 * fract(k * 0.36787944117), s = 0.55;
      float a = s * min(l, 1.0 - l);
      vec3 n = mod(vec3(0.0, 4.0, 2.0) + h, 6.0);
      c = l - a * clamp(min(n - 1.0, 3.0 - n), -1.0, 1.0);
    }
  }
  else {
    float t = 0.0; bool nothing = false;
    if (uSplit == 1) t = v <= 0.0 ? 0.498 - 0.498 * clamp(v / min(uLo, -1e-30), 0.0, 1.0) : 0.502 + 0.498 * clamp(v / max(uHi, 1e-30), 0.0, 1.0);
    else if (uLog == 1) { if (v > 0.0) t = clamp(log(v / uLo) / log(uHi / uLo), 0.0, 1.0); else nothing = true; }
    else t = clamp((v - uLo) / max(uHi - uLo, 1e-30), 0.0, 1.0);
    if (nothing) {                                        // exactly zero has no place on a log scale
      bool sea = uHasSea == 1 && texelFetch(uSea, at(id), 0).r > 0.5;
      c = sea ? ${v3(nothingAtSea)} : ${v3(nothingOnLand)};
    } else c = textureLod(uLut, vec2(t, 0.5), 0.0).rgb;
  }
  if (uMesh == 1) {                                       // the cells' borders, once a cell is large on the screen
    float e = border(w, id) * uPxPerRad, large = smoothstep(26.0, 70.0, uCell * uPxPerRad);
    float line = (1.0 - smoothstep(0.4, 1.4, e)) * large * (smoothed ? 0.0 : 0.2);
    if (id == uSel) { c = mix(c, vec3(1.0), 0.65); c = mix(c, vec3(0.06), 1.0 - smoothstep(1.0, 2.2, e)); }
    else c = mix(c, dot(c, vec3(0.299, 0.587, 0.114)) > 0.45 ? vec3(0.0) : vec3(1.0), line);
  } else if (id == uSel) c = mix(c, vec3(1.0), 0.65);
  frag = vec4(c * shade, 1.0);
}`;
}

// What the illustrated look and its rivers share: the bends, and where the land is, at either level of cells.
const GLSL_DRAWN = `
uniform sampler2D uA; uniform sampler2D uB; uniform sampler2D uFA; uniform sampler2D uFB; uniform int uOct, uFOct;
uvec3 pcg3(uvec3 v) {                                     // whole-number arithmetic: the same bends on every machine
  v = v * 1664525u + 1013904223u; v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  v ^= v >> 16u; v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y; return v;
}
vec3 hash3(vec3 c) { return vec3(pcg3(uvec3(ivec3(c) + 1000000)) >> 8u) * (2.0 / 16777215.0) - 1.0; }
vec3 noise3(vec3 p) {                                     // three smooth random numbers from -1 to 1 for a place
  vec3 i = floor(p), f = p - i, u = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), u.x), mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), u.x), u.y),
             mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), u.x), mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), u.x), u.y), u.z);
}
vec3 warp(vec3 w, int oct, float cell) {                  // the bends: large ones, and on them ever smaller ones; all by the cells' spacing
  vec3 s = vec3(0.0); float a = 1.0, f = 1.0 / (${DRAWING.warpStep.toFixed(3)} * cell);
  for (int o = 0; o < 10; o++) { if (o >= oct) break; s += a * noise3(w * f + 19.7 * float(o)); a *= 0.5; f *= 2.0; }
  return s * (${DRAWING.warp.toFixed(3)} * cell);
}
// x: 1 on land and 0 at sea; y: 1 under ice; each smoothly from cell to cell (the cells: their places, neighbours and values)
vec2 landAt(sampler2D pos, sampler2D nb, sampler2D A, vec3 wp, int c) {
  int n[6]; nbrsOf(nb, c, n); float sw = 0.0; vec2 s = vec2(0.0);
  for (int k = 0; k < 7; k++) {
    int j = k == 0 ? c : n[k - 1]; if (j < 0) continue;
    vec4 P = texelFetch(pos, at(j), 0); float t = length(wp - P.xyz) / (KERNEL * P.w); if (t >= 1.0) continue;
    float q = 1.0 - t * t; q *= q; sw += q; s += q * texelFetch(A, at(j), 0).xw;
  }
  return sw > 0.0 ? s / sw : texelFetch(A, at(c), 0).xw;
}
`;

// The illustrated look. No branch here holds a derivative (fwidth, dFdx): every pixel runs the same lines, and the
// choices are made with weights, so that the lines stay whole on every graphics card.
const FS_MAP = GLSL_HEAD + GLSL_DRAWN + `
uniform sampler2D uBiome; uniform int uRidge, uFRidge, uDark; uniform float uDpr;
in vec2 vPos; out vec4 frag;
const vec3 INK = vec3(${INK.join(", ")});
const vec3 LIGHT = vec3(-0.5488, 0.5488, 0.6306);         // the light of maps: from the upper left
float aastep(float th, float x) { float f = max(fwidth(x), 1e-7) * 0.75; return smoothstep(th - f, th + f, x); }
float stroke(float d, float halfw) { return 1.0 - smoothstep(halfw - 0.5, halfw + 0.5, d); }   // d: pixels from the line's middle
float hatch(float coord, float spacing, float halfw) {    // parallel strokes that keep their spacing on the screen at any zoom
  float l = log2(uPxPerRad / spacing), l0 = floor(l), fr = l - l0;
  float u = coord * exp2(l0 + 1.0), i = floor(u + 0.5), d = abs(u - i) / max(fwidth(u), 1e-7);
  return stroke(d, halfw) * (mod(i, 2.0) > 0.5 ? fr : 1.0);
}
float ridges(vec3 p, int oct, float cell) {               // the drawn ridges: sharp crests, smaller ones on the larger
  float s = 0.0, a = 0.5, f = 1.0 / (0.9 * cell);
  for (int o = 0; o < 6; o++) { if (o >= oct) break; float v = 1.0 - abs(noise3(p * f + 31.0 * float(o)).x); s += a * v * v; a *= 0.5; f *= 2.1; }
  return s;
}
float seg(vec2 p, vec2 a, vec2 b) { vec2 pa = p - a, ba = b - a; return length(pa - ba * clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0)); }
float pen(float d, float halfw, float aa) { return 1.0 - smoothstep(halfw - 0.5 * aa, halfw + 0.5 * aa, d); }
// One of the map's small signs, at p (in the sign's own units from the middle of its foot; up is up): how much ink
// (x) and how much filling (y). aa is the width of a pixel in those units. A sign stands for the kind of country it
// lies in (a tree for forest, a peak for mountains): it is not a thing that the world holds at that place.
vec2 sign_(vec2 p, int kind, float pick, float aa) {
  float ink = 0.0, fill = 0.0;
  if (kind == 3 && pick > 0.4) kind = 4;                  // open woodland: a tree here and there among the grass
  if (kind == 1) {                                        // a broad-leaved tree
    float d = length(p - vec2(0.0, 2.4)) - 3.3;
    fill = 1.0 - smoothstep(-aa, aa, d); ink = max(pen(abs(d), 0.42, aa), pen(seg(p, vec2(0.0, -3.4), vec2(0.0, -0.9)), 0.48, aa));
  } else if (kind == 2) {                                 // a conifer
    float d = max(-1.6 - p.y, (abs(p.x) - 3.0 * (5.6 - p.y) / 7.2) * 0.923);
    fill = 1.0 - smoothstep(-aa, aa, d); ink = max(pen(abs(d), 0.42, aa), pen(seg(p, vec2(0.0, -3.4), vec2(0.0, -1.6)), 0.48, aa));
  } else if (kind == 3) {                                 // a flat-topped tree of the savanna
    float d = (length((p - vec2(0.0, 2.7)) / vec2(4.4, 1.8)) - 1.0) * 1.8;
    fill = 1.0 - smoothstep(-aa, aa, d); ink = max(pen(abs(d), 0.42, aa), pen(seg(p, vec2(0.0, -3.4), vec2(0.0, 0.9)), 0.48, aa));
  } else if (kind == 4) {                                 // a tuft of grass
    ink = 0.62 * max(pen(seg(p, vec2(0.0, -2.2), vec2(-2.3, 1.5)), 0.36, aa), max(pen(seg(p, vec2(0.0, -2.2), vec2(0.0, 2.7)), 0.36, aa), pen(seg(p, vec2(0.0, -2.2), vec2(2.3, 1.5)), 0.36, aa)));
  } else if (kind == 5) {                                 // sand: three dots
    ink = 0.5 * max(pen(length(p - vec2(-2.7, -0.7)), 0.62, aa), max(pen(length(p - vec2(0.3, 1.3)), 0.62, aa), pen(length(p - vec2(2.9, -1.1)), 0.62, aa)));
  } else if (kind == 6) {                                 // tundra: two short strokes
    ink = 0.48 * max(pen(seg(p, vec2(-3.2, 0.3), vec2(-0.7, 0.3)), 0.36, aa), pen(seg(p, vec2(0.7, -1.4), vec2(3.2, -1.4)), 0.36, aa));
  } else if (kind == 7) {                                 // a peak, its right flank in shadow
    float l = seg(p, vec2(-6.2, -3.6), vec2(0.0, 4.6)), r = seg(p, vec2(0.0, 4.6), vec2(6.2, -3.6));
    float inside = max(-3.6 - p.y, (abs(p.x) - 6.2 * (4.6 - p.y) / 8.2) * 0.798);
    fill = (1.0 - smoothstep(-aa, aa, inside)) * smoothstep(-0.6, 0.6, p.x + 0.35 * (p.y - 4.6));
    ink = max(max(pen(l, 0.5, aa), pen(r, 0.5, aa)), 0.7 * pen(seg(p, vec2(0.0, 4.6), vec2(1.3, -0.4)), 0.36, aa));
  }
  return vec2(ink, fill);
}
// The signs of one size: one may stand in each mesh of a net of latitude and longitude with meshes "pitch" radians
// wide (fewer meshes around the world toward the poles), a little off its middle. dens: how many of the meshes hold one.
vec2 signs(vec3 w, vec3 ex, vec3 ny, float lat, float lon, float pitch, float seed, int kind, float dens, float size) {
  vec2 got = vec2(0.0); float row = floor(lat / pitch), east = uFlat == 1 ? 1.0 / max(cos(lat), 0.05) : 1.0;
  for (int dj = -1; dj <= 1; dj++) {
    float j = row + float(dj), latc = (j + 0.5) * pitch;
    if (abs(latc) > 1.45) continue;
    float around = max(3.0, floor(2.0 * PI * cos(latc) / pitch + 0.5)), wide = 2.0 * PI / around, i0 = floor((lon + PI) / wide);
    for (int di = -1; di <= 1; di++) {
      float i = mod(i0 + float(di), around);
      vec3 h = hash3(vec3(i, j, seed)) * 0.5 + 0.5;
      float show = 1.0 - smoothstep(dens - 0.06, dens + 0.06, h.z); if (show <= 0.0) continue;
      float alat = latc + (h.y - 0.5) * 0.66 * pitch, alon = (i + 0.5 + (h.x - 0.5) * 0.66) * wide - PI;
      vec3 d = w - vec3(cos(alat) * cos(alon), cos(alat) * sin(alon), sin(alat));
      vec2 p = vec2(dot(d, ex) * east, dot(d, ny)) * uPxPerRad / size;
      if (dot(p, p) > 90.0) continue;
      got = max(got, show * sign_(p, kind, fract(h.z * 17.31 + h.x), 1.0 / size));
    }
  }
  return got;
}
// The signs at this zoom: they grow as the view comes closer, and when they have doubled, a finer net of small
// ones takes their place.
vec2 signsNow(vec3 w, vec3 ex, vec3 ny, float lat, float lon, float pitchPx, float seed, int kind, float dens) {
  float l = log2(uPxPerRad * 0.02 / pitchPx), l0 = floor(l), fr = l - l0, pitch = 0.02 * exp2(-l0), size = uDpr * exp2(fr);
  vec2 a = signs(w, ex, ny, lat, lon, pitch, seed + 31.0 * l0, kind, dens, size);
  if (fr < 0.8) return a;
  return mix(a, signs(w, ex, ny, lat, lon, 0.5 * pitch, seed + 31.0 * (l0 + 1.0), kind, dens, uDpr), smoothstep(0.8, 1.0, fr));
}
// What the cells around a place say of it, blended (each cell's weight falls to nothing one spacing from its centre).
struct Ground {
  float land, up, deep, ice, lake;                        // 1 on land; metres above the sea, and below it; 1 under ice; 1 in a lake
  vec3 grad;                                              // the slope of the land's heights (metres to the radian, along the ground)
  float bio, margin;                                      // the biome that holds the most of the weight of the land around, and its lead
};
Ground around(sampler2D pos, sampler2D nb, sampler2D A, sampler2D B, vec3 wp, int c) {
  int n[6]; nbrsOf(nb, c, n);
  float wt[7]; float bio[7]; float lnd[7];
  float sw = 0.0; Ground g = Ground(0.0, 0.0, 0.0, 0.0, 0.0, vec3(0.0), -1.0, 0.0);
  for (int k = 0; k < 7; k++) {
    wt[k] = 0.0; bio[k] = -1.0; lnd[k] = 0.0;
    int j = k == 0 ? c : n[k - 1]; if (j < 0) continue;
    vec4 P = texelFetch(pos, at(j), 0); float t = length(wp - P.xyz) / (KERNEL * P.w); if (t >= 1.0) continue;
    float q = 1.0 - t * t; q *= q;
    vec4 a = texelFetch(A, at(j), 0), b = texelFetch(B, at(j), 0);
    wt[k] = q; bio[k] = a.z; lnd[k] = a.x;
    sw += q; g.land += q * a.x; g.up += q * max(a.y, 0.0); g.deep += q * max(-a.y, 0.0); g.ice += q * a.w; g.grad += q * b.xyz; g.lake += q * b.w;
  }
  if (sw <= 0.0) { vec4 a = texelFetch(A, at(c), 0), b = texelFetch(B, at(c), 0);
    sw = 1.0; wt[0] = 1.0; bio[0] = a.z; lnd[0] = a.x; g.land = a.x; g.up = max(a.y, 0.0); g.deep = max(-a.y, 0.0); g.ice = a.w; g.grad = b.xyz; g.lake = b.w; }
  g.land /= sw; g.up /= sw; g.deep /= sw; g.ice /= sw; g.lake /= sw; g.grad /= sw;
  float best = -1.0, second = 0.0;
  for (int k = 0; k < 7; k++) if (wt[k] > 0.0 && lnd[k] > 0.5 && bio[k] >= 0.0) {
    float s = 0.0; for (int m = 0; m < 7; m++) if (lnd[m] > 0.5 && bio[m] == bio[k]) s += wt[m];
    if (s > best) { best = s; g.bio = bio[k]; }
  }
  for (int k = 0; k < 7; k++) if (wt[k] > 0.0 && lnd[k] > 0.5 && bio[k] >= 0.0 && bio[k] != g.bio) {
    float s = 0.0; for (int m = 0; m < 7; m++) if (lnd[m] > 0.5 && bio[m] == bio[k]) s += wt[m];
    second = max(second, s);
  }
  g.margin = (best - second) / sw;
  return g;
}
// The country at a place, drawn from its ground: w is the place, wp the place the bends moved it to, cell the
// spacing of the cells the ground came from, and relief the distance over which a rise counts as a slope.
vec3 country(Ground g, vec3 w, vec3 wp, float cell, float relief, int ridgeOct, vec3 ex, vec3 ny, float lat, float lon, float px) {
  float pxCell = cell * uPxPerRad;
  // the light on the heights: the slope the cells hold, and the drawn ridges on it
  vec2 slope = vec2(dot(g.grad, ex), dot(g.grad, ny)) * (relief / ${DRAWING.reliefM.toFixed(1)});
  float rug = clamp(length(g.grad) * relief / ${DRAWING.ruggedM.toFixed(1)}, 0.0, 1.0);
  float reach = 2.5 * px / uPxPerRad, b0 = ridges(wp, ridgeOct, cell);  // the ridges' slope, taken over a few pixels
  vec2 db = rug * vec2(ridges(normalize(wp + ex * reach), ridgeOct, cell) - b0, ridges(normalize(wp + ny * reach), ridgeOct, cell) - b0) * (cell / reach) * 0.5;
  float lit = dot(normalize(vec3(-(slope + db), 1.0)), LIGHT);
  float sh1 = 1.0 - aastep(LIGHT.z - 0.20, lit), sh2 = 1.0 - aastep(LIGHT.z - 0.40, lit), hl = aastep(LIGHT.z + 0.18, lit);
  // every line's distance, in pixels, before any choice is made
  float isLand = aastep(0.5, g.land), coast = abs(g.land - 0.5) / max(fwidth(g.land), 1e-7);
  float isIce = aastep(0.5, g.ice), iceEdge = abs(g.ice - 0.5) / max(fwidth(g.ice), 1e-7);
  float isLake = aastep(0.5, g.lake) * isLand, lakeEdge = abs(g.lake - 0.5) / max(fwidth(g.lake), 1e-7);
  float biomeEdge = g.margin / max(fwidth(g.margin), 1e-7);
  float crest = g.up + (b0 - 0.35) * rug * 900.0;         // the heights' bands follow the drawn ridges
  float high1 = aastep(1500.0, crest), high2 = aastep(2700.0, crest);
  float far1 = 1.0 - aastep(0.30, g.land), far2 = aastep(3800.0, g.deep) * (1.0 - aastep(0.04, g.land));
  float h1 = hatch(asin(clamp(dot(w, vec3(0.2873, 0.1642, 0.9437)), -1.0, 1.0)), 6.5 * px, 0.4 * px);
  // the land: flat colours by biome, rock on the heights, ice; then light and shadow in three steps
  vec4 biome = g.bio >= 0.0 ? texelFetch(uBiome, ivec2(int(g.bio), 0), 0) : vec4(0.82, 0.80, 0.64, 0.0);
  vec3 base = biome.rgb; int kind = int(biome.a * 255.0 / 30.0 + 0.5);
  base = mix(base, vec3(0.745, 0.685, 0.625), 0.38 * high1); base = mix(base, vec3(0.93, 0.91, 0.90), 0.65 * high2);
  base = mix(base, vec3(0.972, 0.980, 0.984), isIce);
  vec3 landc = mix(base, base * vec3(1.06, 1.045, 0.97) + 0.018, hl);
  landc = mix(landc, landc * vec3(0.82, 0.795, 0.90), sh1); landc = mix(landc, landc * vec3(0.80, 0.77, 0.90), sh2);
  landc = mix(landc, INK, 0.30 * h1 * sh2);
  // the small signs: peaks where the land is rugged, and elsewhere what grows there; none on ice, in lakes or at a biome's very edge
  float peaks = smoothstep(0.30, 0.46, rug), inside = smoothstep(0.03, 0.14, g.margin) * smoothstep(0.52, 0.64, g.land) * (1.0 - isIce) * (1.0 - step(0.5, g.lake));
  float dens = kind == 1 || kind == 2 ? 0.86 : kind == 3 ? 0.62 : kind == 4 ? 0.5 : kind == 5 ? 0.42 : kind == 6 ? 0.36 : 0.0;
  vec2 grows = kind > 0 ? signsNow(w, ex, ny, lat, lon, 23.0, 7.0, kind, dens) * (1.0 - peaks) : vec2(0.0);
  vec2 peak = peaks > 0.0 ? signsNow(w, ex, ny, lat, lon, 31.0, 211.0, 7, 0.82) * peaks : vec2(0.0);
  landc = mix(landc, mix(base * 0.66, vec3(0.13, 0.33, 0.29), 0.3), grows.y * inside);
  landc = mix(landc, landc * vec3(0.72, 0.69, 0.84), peak.y * inside);
  landc = mix(landc, INK, 0.82 * max(grows.x, peak.x) * inside);
  landc = mix(landc, INK, 0.2 * stroke(biomeEdge, 0.3 * px) * (1.0 - isIce) * smoothstep(14.0, 30.0, pxCell / px));
  // the sea: a pale band along the coasts, the open sea, the deep; and the old charts' lines along the shore
  vec3 seac = mix(vec3(0.682, 0.871, 0.855), vec3(0.545, 0.792, 0.816), far1); seac = mix(seac, vec3(0.506, 0.765, 0.800), far2);
  seac = mix(seac, vec3(0.925, 0.955, 0.962), isIce);
  float shore = (stroke(abs(coast - 5.0 * px), 0.4 * px) * 0.42 + stroke(abs(coast - 10.5 * px), 0.4 * px) * 0.27 + stroke(abs(coast - 17.0 * px), 0.4 * px) * 0.15);
  seac = mix(seac, vec3(0.22, 0.42, 0.52), shore * (1.0 - isIce) * smoothstep(7.0, 16.0, pxCell / px));
  vec3 lakec = mix(vec3(0.60, 0.83, 0.84), vec3(0.93, 0.955, 0.962), isIce);
  landc = mix(landc, lakec, isLake);
  landc = mix(landc, INK, 0.8 * stroke(lakeEdge, 0.7 * px) * isLand);
  vec3 col = mix(seac, landc, isLand);
  col = mix(col, vec3(0.42, 0.55, 0.66), 0.55 * stroke(iceEdge, 0.55 * px));
  return mix(col, INK, 0.92 * stroke(coast, 1.0 * px));
}
void main() {
  vec3 w; float limb, beyond; place(vPos, w, limb, beyond);
  float px = uDpr, lat = asin(clamp(w.z, -1.0, 1.0)), lon = atan(w.y, w.x);
  vec3 ex = uFlat == 1 ? normalize(vec3(-w.y, w.x, 1e-9)) : uRot[0];
  vec3 ny = uFlat == 1 ? cross(w, ex) : uRot[1];
  // the world's own cells
  vec3 wp = normalize(w + warp(w, uOct, uCell));
  Ground g = around(uPos, uNbr, uA, uB, wp, nearest(wp));
  vec3 col = country(g, w, wp, uCell, uCell, uRidge, ex, ny, lat, lon, px);
  if (uFine == 1) {                                       // (the same for every pixel of a picture, so no line is lost)
    // the finer cells of the detail, where they are: their own heights, coast, lakes; the biome and the ice are the world's
    vec3 wf = normalize(w + warp(w, uFOct, uFCell));
    Ground f = around(uFPos, uFNbr, uFA, uFB, wf, nearestFine(wf));
    if (g.bio >= 0.0) { f.bio = g.bio; f.margin = g.margin; } else f.margin = 1.0;
    f.ice = g.ice;
    col = mix(col, country(f, w, wf, uFCell, 1.5 * uFCell, uFRidge, ex, ny, lat, lon, px), fineShare(w));
  }
  float every = uCell * uPxPerRad > 180.0 * px ? 10.0 : 30.0;        // the lines of latitude and longitude, in degrees
  float glat = lat * 180.0 / PI / every, glon = lon * 180.0 / PI / every;
  float grat = max(stroke(abs(glat - floor(glat + 0.5)) / max(fwidth(glat), 1e-7), 0.4 * px),
                   stroke(abs(glon - floor(glon + 0.5)) / max(fwidth(glon), 1e-7), 0.4 * px) * (1.0 - smoothstep(1.35, 1.5, abs(lat))));
  int cu = uSel >= 0 ? nearest(w) : -1;                   // the cell that is selected is shown where it truly lies
  float sel = cu == uSel && uSel >= 0 ? 1.0 : 0.0, selEdge = uSel >= 0 ? border(w, cu) * uPxPerRad : 99.0;
  col = mix(col, INK, 0.06 * grat);
  col = mix(col, vec3(1.0), 0.28 * sel); col = mix(col, vec3(0.75, 0.16, 0.2), sel * (1.0 - smoothstep(1.2 * px, 2.4 * px, selEdge)));
  col *= uFlat == 1 ? 1.0 : 0.86 + 0.14 * limb;
  // the paper around the map: the globe's shadow on it, and the map's inked edge
  vec3 paper = uDark == 1 ? vec3(0.150, 0.140, 0.180) : vec3(0.925, 0.893, 0.820);
  vec2 q = vec2(vPos.x * uAspect, vPos.y) / uZoom;
  float thrown = uFlat == 1 ? 0.0 : 1.0 - smoothstep(0.0, 0.075, length(q - vec2(0.02, -0.027)) - 1.0);
  vec3 outc = paper * (1.0 - 0.3 * thrown);
  col = mix(col, outc, smoothstep(-0.5, 0.5, beyond));
  col = mix(col, INK, stroke(abs(beyond), 1.2 * px) * 0.95);
  col = uReady == 1 ? col : paper * 0.94;
  vec2 fc = gl_FragCoord.xy;
  float grain = hash3(vec3(floor(fc), 3.0)).x * 0.016 + noise3(vec3(fc * 0.011 / px, 5.0)).x * 0.028;
  frag = vec4(col * (1.0 + grain), 1.0);
}`;

// The rivers: each part of a river's way is one strip of four corners, as wide as its flow asks, bent with the land.
// uLevel says whose rivers these are: 0 the world's own cells', 1 those of the detail's finer cells; near the edge
// of the detail the one gives way to the other.
const VS_RIVER = GLSL_HEAD + GLSL_DRAWN + `
in vec2 aCorner; in vec3 aA; in vec3 aB; in vec2 aQ;
uniform vec2 uView; uniform float uShift, uWide, uDpr; uniform int uLevel;
out float vSide, vHalf, vFront, vQ; out vec2 vP;
vec3 bent(vec3 x) {                                       // where the drawing shows the place x: against the bends
  int oct = min(uLevel == 1 ? uFOct : uOct, 3); float cell = uLevel == 1 ? uFCell : uCell;
  vec3 w = normalize(x - warp(x, oct, cell)); w = normalize(x - warp(w, oct, cell)); return normalize(x - warp(w, oct, cell));
}
float lonOf(vec3 w) { return atan(w.y, w.x) / PI; }
void main() {
  vec3 a = bent(aA), b = bent(aB); vec2 sa, sb; float fa = 1.0, fb = 1.0;
  if (uFlat == 1) {
    float fit = min(1.0, uAspect / 2.0), la = lonOf(a) - uPan.x; la -= 2.0 * floor((la + 1.0) / 2.0);
    float d = lonOf(b) - lonOf(a); d -= 2.0 * floor((d + 1.0) / 2.0); float lb = la + d;
    sa = vec2((la + uShift) * 2.0 * fit * uZoom / uAspect, (asin(clamp(a.z, -1.0, 1.0)) / (PI / 2.0) - uPan.y) * fit * uZoom);
    sb = vec2((lb + uShift) * 2.0 * fit * uZoom / uAspect, (asin(clamp(b.z, -1.0, 1.0)) / (PI / 2.0) - uPan.y) * fit * uZoom);
  } else {
    vec3 ca = a * uRot, cb = b * uRot;                    // (a vector times the matrix: the matrix turned back)
    sa = vec2(ca.x * uZoom / uAspect, ca.y * uZoom); sb = vec2(cb.x * uZoom / uAspect, cb.y * uZoom); fa = ca.z; fb = cb.z;
  }
  vec2 pa = sa * uView * 0.5, pb = sb * uView * 0.5, dir = pb - pa; float len = length(dir);
  dir = len > 1e-5 ? dir / len : vec2(1.0, 0.0);
  float q = mix(aQ.x, aQ.y, aCorner.x), halfw = 0.5 * uDpr * uWide * (0.55 + 4.2 * pow(clamp(q, 0.0, 1.0), 0.45));
  vec2 p = mix(pa, pb, aCorner.x) + vec2(-dir.y, dir.x) * aCorner.y * (halfw + 1.0) + dir * (aCorner.x * 2.0 - 1.0) * min(0.5 * halfw, 0.4 * len);
  gl_Position = vec4(p / (uView * 0.5), 0.0, 1.0);
  vSide = aCorner.y * (halfw + 1.0); vHalf = halfw; vFront = mix(fa, fb, aCorner.x); vQ = q; vP = gl_Position.xy;
}`;
const FS_RIVER = GLSL_HEAD + GLSL_DRAWN + `
in float vSide, vHalf, vFront, vQ; in vec2 vP; out vec4 frag; uniform float uQMin; uniform int uLevel;
void main() {
  if (vFront < 0.0) discard;                              // on the far side of the globe
  vec3 w; float shade, beyond; place(vP, w, shade, beyond);
  float fine = fineShare(w), mine = uLevel == 1 ? fine : 1.0 - fine;
  if (beyond > 0.0 || mine <= 0.0) discard;
  vec3 wp = normalize(w + warp(w, uOct, uCell));
  vec2 ground = landAt(uPos, uNbr, uA, wp, nearest(wp));  // the world's own land and ice
  if (uLevel == 1) { vec3 wf = normalize(w + warp(w, uFOct, uFCell)); ground.x = landAt(uFPos, uFNbr, uFA, wf, nearestFine(wf)).x; }
  if (ground.x < 0.5 || ground.y > 0.5) discard;          // a river ends where the drawn sea begins, and is not drawn under ice
  float a = (1.0 - smoothstep(vHalf - 0.5, vHalf + 0.5, abs(vSide))) * smoothstep(uQMin * 0.55, uQMin, vQ);
  frag = vec4(0.153, 0.392, 0.522, 0.94 * a * mine);
}`;

// ---------------------------------------------------------------- preparing a world for the shaders
// The spacing of each cell: the mean distance to its neighbours (a chord of the unit sphere: for a cell, as good as radians).
function cellSpacing(xyz, nbr) {
  const n = xyz.length / 3, h = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0, m = 0;
    for (let k = 0; k < 6; k++) { const j = nbr[i * 6 + k]; if (j < 0) continue;
      s += Math.hypot(xyz[j * 3] - xyz[i * 3], xyz[j * 3 + 1] - xyz[i * 3 + 1], xyz[j * 3 + 2] - xyz[i * 3 + 2]); m++; }
    h[i] = m ? s / m : 1; }
  return h;
}
// The slope of a field at each cell, as a vector on the sphere (the field's units for one radian): the slope along the
// ground that fits the rises to the cell's neighbours best (least squares, each neighbour at its own place around).
function cellGradients(xyz, nbr, value) {
  const n = value.length, g = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const p = [xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2]];
    // two directions along the ground at the cell: e1 toward the first neighbour, e2 square to it
    let e1 = null, e2 = null, sxx = 0, sxy = 0, syy = 0, sxv = 0, syv = 0;
    for (let k = 0; k < 6; k++) { const j = nbr[i * 6 + k]; if (j < 0) continue;
      const q = [xyz[j * 3], xyz[j * 3 + 1], xyz[j * 3 + 2]], dot = p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
      const t = [q[0] - p[0] * dot, q[1] - p[1] * dot, q[2] - p[2] * dot], len = Math.hypot(t[0], t[1], t[2]), ang = Math.acos(Math.max(-1, Math.min(1, dot)));
      if (len < 1e-12 || ang < 1e-12) continue;
      for (let c = 0; c < 3; c++) t[c] /= len;
      if (!e1) { e1 = t.slice(); e2 = [p[1] * e1[2] - p[2] * e1[1], p[2] * e1[0] - p[0] * e1[2], p[0] * e1[1] - p[1] * e1[0]]; }
      const x = ang * (t[0] * e1[0] + t[1] * e1[1] + t[2] * e1[2]), y = ang * (t[0] * e2[0] + t[1] * e2[1] + t[2] * e2[2]), rise = value[j] - value[i];
      sxx += x * x; sxy += x * y; syy += y * y; sxv += x * rise; syv += y * rise; }
    const det = sxx * syy - sxy * sxy;
    if (!e1 || Math.abs(det) < 1e-30) continue;
    const a = (sxv * syy - syv * sxy) / det, b = (syv * sxx - sxv * sxy) / det;
    for (let c = 0; c < 3; c++) g[i * 3 + c] = a * e1[c] + b * e2[c];
  }
  return g;
}
// The rivers as parts to draw: for each cell of land that hands a flow on, its way to the cell that receives it, as a
// curve through the cell above it and the cell below (so that a river has no corners at the centres of the cells),
// cut into straight parts. Each part: where it starts, where it ends, and the flow at each end as a share (0 to 1) of
// `top`, the flow of the largest rivers. The flow is that of the cell at the start and of the receiver at the end, so
// a river widens along its way; a river that starts in the cell starts as a thread.
function riverParts(xyz, recv, flow, sea, top) {
  const n = recv.length, floor = DRAWING.riverFloor * top, donor = new Int32Array(n).fill(-1), out = [];
  const drawn = (i) => !sea[i] && recv[i] >= 0 && flow[i] >= floor;
  for (let i = 0; i < n; i++) if (drawn(i)) { const r = recv[i]; if (donor[r] < 0 || flow[i] > flow[donor[r]]) donor[r] = i; }
  const P = (i) => [xyz[i * 3], xyz[i * 3 + 1], xyz[i * 3 + 2]], S = DRAWING.riverParts;
  const share = (v) => Math.max(0, Math.min(1, v / top));
  for (let i = 0; i < n; i++) {
    if (!drawn(i)) continue;
    const r = recv[i], p1 = P(i), p2 = P(r), d = donor[i], r2 = recv[r];
    const p0 = d >= 0 ? P(d) : p1.map((v, k) => 2 * v - p2[k]), p3 = r2 >= 0 ? P(r2) : p2.map((v, k) => 2 * v - p1[k]);
    const qa = share(flow[i]) * (d >= 0 ? 1 : 0.12), qb = share(sea[r] ? flow[i] : Math.max(flow[r], flow[i]));
    let prev = p1;
    for (let s = 1; s <= S; s++) {
      const t = s / S, t2 = t * t, t3 = t2 * t, pt = [0, 0, 0];
      for (let k = 0; k < 3; k++) pt[k] = 0.5 * (2 * p1[k] + (p2[k] - p0[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * t3);
      const len = Math.hypot(pt[0], pt[1], pt[2]); for (let k = 0; k < 3; k++) pt[k] /= len;
      out.push(prev[0], prev[1], prev[2], pt[0], pt[1], pt[2], qa + (qb - qa) * (s - 1) / S, qa + (qb - qa) * t);
      prev = pt;
    }
  }
  return new Float32Array(out);
}
function percentile(values, p) {
  const f = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
  return f.length ? f[Math.min(f.length - 1, Math.floor(p / 100 * f.length))] : 0;
}

// The illustrated look's own colours, by the name of the biome. A biome it does not know keeps the engine's colour,
// paled toward the paper.
const DRAWN_BIOMES = {
  ocean: "#8bcad0", ice: "#f8fafb",
  tropical_rain_forest: "#3f9c74", tropical_seasonal_forest: "#5fae72", tropical_dry_forest_savanna: "#d6bd62", tropical_seasonal_forest_savanna: "#d6bd62",
  warm_mixed_forest: "#6fb383", temperate_deciduous_forest: "#8cc481", cool_mixed_forest: "#70ae8e", cool_conifer_forest: "#4c9a84",
  taiga: "#93bda3", cold_mixed_forest: "#86b6a2", cold_deciduous_forest: "#aacba6",
  xerophytic_woods_scrub: "#d3b674", warm_grass_shrub: "#e6cf88", cool_grass_shrub: "#d3d792",
  tundra: "#cddccb", hot_desert: "#f4d3a1", semi_desert: "#eec592", polar_desert: "#e4e9e4",
};
// The small sign that stands for each biome: 0 none, 1 a broad-leaved tree, 2 a conifer, 3 open woodland (a
// flat-topped tree among grass), 4 grass, 5 sand, 6 tundra. (7, a peak, is drawn where the land is rugged.)
const DRAWN_SIGNS = {
  tropical_rain_forest: 1, tropical_seasonal_forest: 1, warm_mixed_forest: 1, temperate_deciduous_forest: 1, cool_mixed_forest: 1, cold_deciduous_forest: 1,
  cool_conifer_forest: 2, taiga: 2, cold_mixed_forest: 2,
  tropical_dry_forest_savanna: 3, tropical_seasonal_forest_savanna: 3, xerophytic_woods_scrub: 3,
  warm_grass_shrub: 4, cool_grass_shrub: 4, hot_desert: 5, semi_desert: 5, tundra: 6,
};
const SIGN_NAMES = ["", "trees", "conifers", "scattered trees and grass", "grass", "sand", "tundra"];
function hexRGB(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
function drawnBiomeColours(names, engineColours) {       // for each biome: red, green, blue, and its sign
  return names.map((name, i) => {
    const sign = DRAWN_SIGNS[name] || 0;
    if (DRAWN_BIOMES[name]) return [...hexRGB(DRAWN_BIOMES[name]), sign];
    const c = engineColours && engineColours[i] ? hexRGB(engineColours[i]) : [205, 200, 160];
    return [...c.map((v, k) => Math.round(0.62 * v + 0.38 * [236, 228, 209][k])), sign];
  });
}
