"""I8S1: 8-bit pixel indices with a big-endian RGB565 palette.

Header: magic[4], width:u16, height:u16, palette_count:u16 (big-endian).
Then palette_count RGB565 entries and width*height one-byte indices.
Decoding happens during preload, before the animation clock starts.
"""
import struct

MAGIC = b"I8S1"


def decode(data):
    if len(data) < 10:
        raise ValueError("Truncated indexed sprite header")
    magic, width, height, count = struct.unpack(">4sHHH", data[:10])
    if magic != MAGIC or not (1 <= width <= 240 and 1 <= height <= 240):
        raise ValueError("Invalid indexed sprite header")
    if not 1 <= count <= 256:
        raise ValueError("Invalid indexed sprite palette")
    offset = 10 + count * 2
    pixels = width * height
    if len(data) != offset + pixels:
        raise ValueError("Invalid indexed sprite length")
    output = bytearray(pixels * 2)
    for i in range(pixels):
        index = data[offset + i]
        if index >= count:
            raise ValueError("Indexed sprite pixel outside palette")
        color = 10 + index * 2
        output[i * 2] = data[color]
        output[i * 2 + 1] = data[color + 1]
    return output
