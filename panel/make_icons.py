"""Draw the app's icon, a planet, into panel/assets/: world-engine.png (256 px, for the window), world-engine-64.png
(for the panel's heading), world-engine.ico (Windows) and world-engine.icns (macOS). Standard library only; run it
again after changing the drawing:

    python panel/make_icons.py

What the file formats are taken to be:
  .ico   a 6-byte ICONDIR (reserved 0, type 1, the number of images), one 16-byte ICONDIRENTRY per image (width and
         height as a byte, 0 meaning 256; colour count 0; reserved 0; planes 1; bits per pixel 32; the image's length
         and offset), then the images. An image may be a whole PNG file, which Windows reads from Vista on
         [DOCUMENTED: Microsoft Learn, "Icons" (the ICO format), and the ICONDIR layout in "Icons in Win32"].
  .icns  'icns' and the file's length (big-endian 32 bits), then entries of a 4-byte type, a length that counts the
         8-byte entry header, and the data. The types used here hold PNG data: icp4 16 px, icp5 32 px, ic07 128 px,
         ic08 256 px, ic09 512 px, ic11 32 px (16 at 2x), ic12 64 px (32 at 2x), ic13 256 px (128 at 2x) and
         ic14 512 px (256 at 2x) [DOCUMENTED: the table of types in "Apple Icon Image format", Wikipedia, which
         gives macOS 10.7 or later for icp4 and icp5 and 10.8 for ic11 to ic14; Apple publishes no specification].
The files written here were read back with Pillow [MEASURED].
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icons import hex_rgb, png_bytes  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
R = 0.84                                  # the planet's radius in the square of half-width 1; the rest is atmosphere


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


# The centres of the continents on the unit sphere, each with its size and weight.
CONTINENTS = [(_norm(c), s, w) for c, s, w in (
    ((-0.50, 0.40, 0.77), 22.0, 0.9), ((-0.30, 0.05, 0.95), 26.0, 0.8), ((-0.40, -0.38, 0.83), 20.0, 0.85),
    ((0.45, 0.42, 0.78), 18.0, 0.85), ((0.60, -0.15, 0.78), 24.0, 0.75), ((0.15, 0.62, 0.77), 30.0, 0.6),
    ((0.20, -0.60, 0.78), 26.0, 0.7), ((-0.05, -0.15, 0.99), 45.0, 0.55))]
LIGHT = _norm((-0.55, 0.62, 0.62))        # from the upper left, in front
OCEAN_DEEP, OCEAN_SHALLOW = hex_rgb("#1b4f99"), hex_rgb("#3f93d6")
GREEN, DRY, ICE = hex_rgb("#3f9a4a"), hex_rgb("#c9a865"), hex_rgb("#f4f8fb")
GLOW = hex_rgb("#86c8ff")


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _surface(x, y):
    """The colour and opacity of the planet at (x, y), x to the right and y up, in units of the icon's half-width."""
    d2 = x * x + y * y
    if d2 > R * R:                                           # the atmosphere's glow outside the disc
        d = math.sqrt(d2)
        t = (d - R) / (1.0 - R)
        return GLOW, max(0.0, 1.0 - t) ** 2.2 * 0.55
    nx, ny = x / R, y / R
    nz = math.sqrt(max(0.0, 1.0 - nx * nx - ny * ny))
    # the globe tilted by 20 degrees
    c, s = math.cos(math.radians(20)), math.sin(math.radians(20))
    px, py, pz = c * nx - s * ny, s * nx + c * ny, nz
    land = sum(w * math.exp(-(1.0 - (px * cx + py * cy + pz * cz)) * k) for (cx, cy, cz), k, w in CONTINENTS)
    land += 0.09 * math.sin(9 * px + 1.3) * math.sin(8 * py + 0.4) * math.sin(10 * pz + 2.1)   # ragged coasts
    land += 0.05 * math.sin(23 * px + 0.7) * math.sin(19 * py + 2.2) * math.sin(21 * pz + 1.1)
    if abs(py) > 0.9 + 0.035 * math.sin(17 * px + 1.0) * math.sin(11 * pz):
        base = ICE
    elif land > 0.5:
        dryness = max(0.0, 1.0 - abs(abs(py) - 0.36) / 0.12) * min(1.0, (land - 0.5) * 5)
        base = _mix(GREEN, DRY, 0.6 * dryness)
    else:
        base = _mix(OCEAN_DEEP, OCEAN_SHALLOW, max(0.0, min(1.0, (land - 0.25) / 0.25)) ** 1.5)
    diffuse = max(0.0, nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2])
    shade = 0.28 + 0.82 * diffuse
    col = tuple(min(1.0, ch * shade) for ch in base)
    if land <= 0.5 and base is not ICE:                      # the sun's glint on the sea
        hz = _norm((LIGHT[0], LIGHT[1], LIGHT[2] + 1.0))
        spec = max(0.0, nx * hz[0] + ny * hz[1] + nz * hz[2]) ** 40 * 0.55
        col = tuple(min(1.0, ch + spec) for ch in col)
    rim = (1.0 - nz) ** 3 * 0.65                             # the air seen edge on
    return _mix(col, GLOW, rim), 1.0


def planet_png(size) -> bytes:
    n = 4 if size <= 64 else 3 if size <= 128 else 2
    out = bytearray()
    for py in range(size):
        for px in range(size):
            r = g = b = a = 0.0
            for j in range(n):
                y = 1.0 - 2.0 * (py + (j + 0.5) / n) / size
                for i in range(n):
                    x = 2.0 * (px + (i + 0.5) / n) / size - 1.0
                    (cr, cg, cb), ca = _surface(x, y)
                    r, g, b, a = r + cr * ca, g + cg * ca, b + cb * ca, a + ca
            if a > 0:
                out += bytes((round(min(1, r / a) * 255), round(min(1, g / a) * 255), round(min(1, b / a) * 255),
                              round(a / (n * n) * 255)))
            else:
                out += b"\0\0\0\0"
    return png_bytes(size, size, bytes(out))


def ico(pngs: dict) -> bytes:
    sizes = sorted(pngs)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(head) + 16 * len(sizes)
    entries, data = b"", b""
    for s in sizes:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(pngs[s]), offset + len(data))
        data += pngs[s]
    return head + entries + data


ICNS_TYPES = (("icp4", 16), ("icp5", 32), ("ic11", 32), ("ic12", 64), ("ic07", 128), ("ic08", 256), ("ic13", 256),
              ("ic09", 512), ("ic14", 512))


def icns(pngs: dict) -> bytes:
    body = b"".join(kind.encode("ascii") + struct.pack(">I", 8 + len(pngs[s])) + pngs[s] for kind, s in ICNS_TYPES)
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main():
    ASSETS.mkdir(exist_ok=True)
    pngs = {}
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        print(f"drawing {s} px", flush=True)
        pngs[s] = planet_png(s)
    (ASSETS / "world-engine.png").write_bytes(pngs[256])
    (ASSETS / "world-engine-64.png").write_bytes(pngs[64])
    (ASSETS / "world-engine.ico").write_bytes(ico({s: pngs[s] for s in (16, 24, 32, 48, 64, 256)}))
    (ASSETS / "world-engine.icns").write_bytes(icns(pngs))
    for name in ("world-engine.png", "world-engine-64.png", "world-engine.ico", "world-engine.icns"):
        print(f"wrote {ASSETS / name} ({(ASSETS / name).stat().st_size} bytes)")


if __name__ == "__main__":
    main()
