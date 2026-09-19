#!/usr/bin/env python3
"""Convert binary PPM (P6) to PNG. Stdlib only."""
import struct, sys, zlib

def read_ppm(path):
    with open(path, 'rb') as f:
        assert f.readline().strip() == b'P6'
        line = f.readline()
        while line.startswith(b'#'):
            line = f.readline()
        w, h = map(int, line.split())
        assert int(f.readline()) == 255
        return w, h, f.read(w * h * 3)

def chunk(tag, payload):
    return (struct.pack('>I', len(payload)) + tag + payload +
            struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

def write_png(path, w, h, rgb):
    raw = b''.join(b'\x00' + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    png  = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)

if __name__ == '__main__':
    w, h, rgb = read_ppm(sys.argv[1])
    write_png(sys.argv[2], w, h, rgb)
    print(f'{sys.argv[1]} -> {sys.argv[2]} ({w}x{h})')