"""The panel's icons, drawn in code: a small rasteriser (shapes covered by sub-pixel samples, so edges are smoothed)
and a PNG writer, both standard library only. The buttons' icons are drawn when the window opens, at the size the
screen needs; the app's icon (a planet) is drawn by make_icons.py into the files of assets/.

PNG as written here: the 8-byte signature, then IHDR (width, height, bit depth 8, colour type 6 = RGBA), one IDAT of
zlib-compressed rows each led by filter byte 0, and IEND; each chunk is length, type, data and the CRC-32 of type and
data [DOCUMENTED: the PNG specification, W3C, sections 5.2 to 5.6 and 11.2]."""
from __future__ import annotations

import base64
import math
import struct
import zlib


# ---------------------------------------------------------------------------------------------- PNG
def png_bytes(width, height, rgba: bytes) -> bytes:
    """An RGBA image (rows from the top, 4 bytes a pixel) as a PNG file."""
    assert len(rgba) == width * height * 4
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def png_size(data: bytes):
    """The width and height in a PNG's header."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


# ---------------------------------------------------------------------------------------------- the rasteriser
def hex_rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Raster:
    """An image of size x size pixels on which shapes are painted in a design grid of `grid` units (a 16-unit grid
    for the buttons), each covered by n x n samples a pixel."""

    def __init__(self, size, grid=16.0, samples=3):
        self.size, self.k, self.n = size, size / grid, samples
        self.px = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]      # premultiplied RGBA

    def paint(self, inside, bbox, colour, alpha=1.0):
        """Paint `colour` where inside(x, y) holds (x, y in grid units); bbox (x0, y0, x1, y1) bounds the shape."""
        r, g, b = hex_rgb(colour) if isinstance(colour, str) else colour
        k, n, size = self.k, self.n, self.size
        x0, y0 = max(0, int(bbox[0] * k) - 1), max(0, int(bbox[1] * k) - 1)
        x1, y1 = min(size, int(math.ceil(bbox[2] * k)) + 1), min(size, int(math.ceil(bbox[3] * k)) + 1)
        offs = [(i + 0.5) / n for i in range(n)]
        for py in range(y0, y1):
            for px in range(x0, x1):
                hit = 0
                for oy in offs:
                    y = (py + oy) / k
                    for ox in offs:
                        if inside((px + ox) / k, y):
                            hit += 1
                if hit:
                    a = alpha * hit / (n * n)
                    p = self.px[py * size + px]
                    p[0] = r * a + p[0] * (1 - a)
                    p[1] = g * a + p[1] * (1 - a)
                    p[2] = b * a + p[2] * (1 - a)
                    p[3] = a + p[3] * (1 - a)

    # shapes, in grid units
    def circle(self, cx, cy, r, colour, alpha=1.0):
        self.paint(lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r, (cx - r, cy - r, cx + r, cy + r), colour, alpha)

    def ring(self, cx, cy, r, width, colour, start=0.0, end=360.0):
        """A circle's outline from angle start to end (degrees, 0 at the right, counted clockwise on the screen)."""
        lo, hi = (r - width / 2) ** 2, (r + width / 2) ** 2
        full = end - start >= 360

        def inside(x, y):
            d = (x - cx) ** 2 + (y - cy) ** 2
            if not lo <= d <= hi:
                return False
            if full:
                return True
            a = math.degrees(math.atan2(y - cy, x - cx)) % 360
            return (a - start) % 360 <= (end - start)
        e = r + width
        self.paint(inside, (cx - e, cy - e, cx + e, cy + e), colour)

    def polygon(self, points, colour, alpha=1.0):
        xs, ys = [p[0] for p in points], [p[1] for p in points]

        def inside(x, y):
            c, j = False, len(points) - 1
            for i in range(len(points)):
                (xi, yi), (xj, yj) = points[i], points[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    c = not c
                j = i
            return c
        self.paint(inside, (min(xs), min(ys), max(xs), max(ys)), colour, alpha)

    def rect(self, x0, y0, x1, y1, colour, radius=0.0, alpha=1.0):
        def inside(x, y):
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                return False
            dx = max(x0 + radius - x, 0, x - (x1 - radius))
            dy = max(y0 + radius - y, 0, y - (y1 - radius))
            return dx * dx + dy * dy <= radius * radius
        self.paint(inside, (x0, y0, x1, y1), colour, alpha)

    def line(self, x0, y0, x1, y1, width, colour):
        """A stroke with round ends."""
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy or 1e-9
        h = width / 2

        def inside(x, y):
            t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / ll))
            return (x - x0 - t * dx) ** 2 + (y - y0 - t * dy) ** 2 <= h * h
        self.paint(inside, (min(x0, x1) - h, min(y0, y1) - h, max(x0, x1) + h, max(y0, y1) + h), colour)

    def rgba(self) -> bytes:
        out = bytearray()
        for r, g, b, a in self.px:
            if a > 0:
                out += bytes((round(min(1, r / a) * 255), round(min(1, g / a) * 255), round(min(1, b / a) * 255), round(a * 255)))
            else:
                out += b"\x00\x00\x00\x00"
        return bytes(out)

    def png(self) -> bytes:
        return png_bytes(self.size, self.size, self.rgba())


# ---------------------------------------------------------------------------------------------- the buttons' icons
GREEN, RED, BLUE, AMBER, PURPLE, GREY, ORANGE = "#2e9d4f", "#cf3f35", "#2f6fc0", "#d9961a", "#7a55c2", "#5f6b76", "#d86a1c"


def _play(r):
    r.polygon([(4.5, 2.5), (13.5, 8), (4.5, 13.5)], GREEN)


def _stop(r):
    r.rect(3, 3, 13, 13, RED, radius=1.6)


def _globe(r):
    r.ring(8, 8, 5.9, 1.4, BLUE)
    r.line(2.6, 8, 13.4, 8, 1.2, BLUE)
    r.line(8, 2.3, 8, 13.7, 1.2, BLUE)

    def meridian(x, y):                                          # an ellipse's outline: the lines of longitude
        d = ((x - 8) / 2.8) ** 2 + ((y - 8) / 5.9) ** 2
        return 0.72 <= d <= 1.0
    r.paint(meridian, (5, 2, 11, 14), BLUE)


def _upgrade(r):
    r.polygon([(8, 1.8), (14, 8), (10.3, 8), (10.3, 14), (5.7, 14), (5.7, 8), (2, 8)], PURPLE)


def _refresh(r):
    r.ring(8, 8, 5.2, 1.9, ORANGE, start=320, end=250 + 360)
    r.polygon([(9.6, 0.9), (14.4, 3.2), (10.3, 6.8)], ORANGE)


def _reset(r):                                                    # a box: the environment of packages
    r.polygon([(8, 1.8), (14, 4.6), (8, 7.4), (2, 4.6)], "#9aa6b2")
    r.polygon([(2, 5.4), (7.5, 8.0), (7.5, 14.6), (2, 12)], GREY)
    r.polygon([(8.5, 8.0), (14, 5.4), (14, 12), (8.5, 14.6)], "#46515b")


def _trash(r):
    r.rect(2.5, 3.2, 13.5, 4.8, RED, radius=0.6)
    r.rect(6.2, 1.6, 9.8, 3.6, RED, radius=0.6)
    r.polygon([(3.8, 5.6), (12.2, 5.6), (11.3, 14.4), (4.7, 14.4)], RED)
    for x in (6.4, 8.0, 9.6):
        r.line(x, 7.3, x, 12.6, 0.8, "#ffffff")


def _folder(r):
    r.rect(1.5, 3, 7.5, 6, "#b8800f", radius=0.8)
    r.rect(1.5, 4.5, 14.5, 13.5, AMBER, radius=1.0)


def _install(r):                                                  # an arrow down into a tray
    r.line(8, 1.8, 8, 9.5, 2.0, BLUE)
    r.polygon([(4.2, 7.0), (11.8, 7.0), (8, 11.2)], BLUE)
    r.rect(2, 10.5, 14, 14.2, BLUE, radius=1.0, alpha=0.35)
    r.rect(2, 12.6, 14, 14.2, BLUE, radius=0.8)


def _copy(r):
    r.rect(2, 2, 10, 11, "#9aa6b2", radius=1.0)
    r.rect(6, 5, 14, 14, GREY, radius=1.0)


ICONS = {"start": _play, "stop": _stop, "browser": _globe, "upgrade": _upgrade, "rebuild": _refresh, "reset": _reset,
         "delete": _trash, "folder": _folder, "install": _install, "copy": _copy}


def icon_png(name, size=20, disabled=False) -> bytes:
    """The PNG of one button's icon, `size` pixels square; disabled: grey and faint."""
    r = Raster(size, 16.0, 3 if size <= 24 else 2)
    ICONS[name](r)
    if disabled:
        for p in r.px:
            if p[3] > 0:
                grey = (0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2]) / p[3]
                v = (0.55 + 0.35 * grey) * p[3] * 0.55
                p[0] = p[1] = p[2] = v
                p[3] *= 0.55
    return r.png()


def light_png(colour, size=18) -> bytes:
    """The status light: a coloured disc with a soft highlight."""
    r = Raster(size, 16.0, 3)
    r.circle(8, 8, 7.4, "#000000", alpha=0.18)
    r.circle(8, 8, 6.6, colour)
    r.circle(6.3, 5.9, 2.6, "#ffffff", alpha=0.35)
    return r.png()


def photo(tk_module, png: bytes, master=None):
    """A tk.PhotoImage of a PNG (Tk reads PNG itself from 8.6 on)."""
    return tk_module.PhotoImage(master=master, data=base64.b64encode(png).decode("ascii"), format="png")
