"""Generate assets/muscles/placeholder.png.

Four muscle groups arriving with the exercise import have no artwork yet
(Forearms, Abductors, Adductors, Neck). They share this placeholder until real
images exist.

Written as a script rather than committed as an opaque binary so the shape and
the colours can be re-derived, and so it stays honest about being generated.

No Pillow in this project's virtualenv and no intention of adding one for a
single 256px square, so the PNG is encoded directly: raw RGBA scanlines, zlib
deflate, CRC32 per chunk. That is the whole format for an image this simple.

Run:  python make_placeholder.py
"""

import struct
import zlib
from pathlib import Path

SIZE = 256
OUT = (Path(__file__).resolve().parents[2]
       / "Frontend" / "assets" / "muscles" / "placeholder.png")

# Matches the design tokens the rest of the app uses.
GROUND = (0x1A, 0x1A, 0x1A, 255)   # --surface
GOLD = (0xC9, 0xA8, 0x4C, 255)     # --gold

canvas = [[GROUND for _ in range(SIZE)] for _ in range(SIZE)]


def put(x, y, colour):
    if 0 <= x < SIZE and 0 <= y < SIZE:
        canvas[y][x] = colour


def stroke_round_rect(left, top, right, bottom, radius, width, colour):
    """Outline only: fill the outer rounded rect, then cut the inner one."""
    def inside(x, y, l, t, r, b, rad):
        if x < l or x > r or y < t or y > b:
            return False
        for cx, cy in ((l + rad, t + rad), (r - rad, t + rad),
                       (l + rad, b - rad), (r - rad, b - rad)):
            near_x = x < l + rad if cx == l + rad else x > r - rad
            near_y = y < t + rad if cy == t + rad else y > b - rad
            if near_x and near_y:
                return (x - cx) ** 2 + (y - cy) ** 2 <= rad ** 2
        return True

    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            outer = inside(x, y, left, top, right, bottom, radius)
            inner = inside(x, y, left + width, top + width,
                           right - width, bottom - width, max(radius - width, 0))
            if outer and not inner:
                put(x, y, colour)


def stroke_circle(cx, cy, radius, width, colour):
    for y in range(cy - radius - 1, cy + radius + 2):
        for x in range(cx - radius - 1, cx + radius + 2):
            distance_sq = (x - cx) ** 2 + (y - cy) ** 2
            if (radius - width) ** 2 <= distance_sq <= radius ** 2:
                put(x, y, colour)


def fill_rect(left, top, right, bottom, colour):
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            put(x, y, colour)


# Frame, echoing the --radius-sm corners used on the real muscle tiles.
stroke_round_rect(10, 10, SIZE - 11, SIZE - 11, 22, 3, GOLD)

# A dumbbell: generic enough to stand in for any body part, and unmistakably
# a placeholder rather than a real anatomical illustration.
MID = SIZE // 2
stroke_circle(MID - 52, MID, 30, 4, GOLD)
stroke_circle(MID + 52, MID, 30, 4, GOLD)
fill_rect(MID - 26, MID - 5, MID + 26, MID + 4, GOLD)
fill_rect(MID - 70, MID - 14, MID - 62, MID + 13, GOLD)
fill_rect(MID + 62, MID - 14, MID + 70, MID + 13, GOLD)


def chunk(tag, payload):
    body = tag + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


raw = bytearray()
for row in canvas:
    raw.append(0)                      # filter type 0 (None) per scanline
    for pixel in row:
        raw.extend(pixel)

png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
       + chunk(b"IEND", b""))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_bytes(png)
print(f"wrote {OUT}  ({len(png) / 1024:.1f} KB, {SIZE}x{SIZE} RGBA)")
