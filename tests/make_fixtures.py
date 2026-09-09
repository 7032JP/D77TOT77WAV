#!/usr/bin/env python3
"""Generate the small, self-made D77 fixtures used by the tests.

No external dependencies. Everything is deterministic, so the fixtures are
not checked in: `test_convert.py` regenerates them into `tests/out/` on every
run, and this file can also be run by hand:

    python3 tests/make_fixtures.py OUTDIR

Each fixture is a 2D (80 cyl x 2 heads, 16 x 256 B sectors per track) image
that only carries as many tracks as the case needs:

    C0 H0 R1        IPL sector (skipped by the converter's default --skip 256)
    data tracks     pseudo-random bytes from a tiny xorshift generator, with
                    one all-$E5 sector inside the data area (must be kept:
                    fill sectors inside a data-bearing track are payload)
    3 fill tracks   $E5 / $FF / $00 (must be dropped by the auto-trim)
    remaining       absent (track offset 0)

The number of data tracks selects the chunk count N of the converter:
    3 tracks -> 12 KiB - 256 B ->  N = 1
    5 tracks -> 20 KiB - 256 B ->  N = 2
    9 tracks -> 36 KiB - 256 B ->  N = 3
"""

import os
import struct
import sys

SECTOR_SIZE = 256
SECTORS_PER_TRACK = 16
TRACK_TABLE_ENTRIES = 164
HEADER_SIZE = 0x20 + TRACK_TABLE_ENTRIES * 4      # 0x2B0

# (case name, fixture file, data tracks, entry address, expected N,
#  expected trampoline variants in tape order)
CASES = [
    ('n1',         'n1.d77', 3, 0x4000, 1, ['rev_last']),
    ('n2_simple',  'n2.d77', 5, 0x3000, 2, ['rev_int', 'rev_last']),
    ('n2_article', 'n2.d77', 5, 0x0200, 2, ['rev_int (stash)', 'relocate2']),
    ('n3',         'n3.d77', 9, 0x2000, 3, ['rev_int', 'rev_int', 'fwd_last']),
]

FIXTURES = {
    'n1.d77': 3,
    'n2.d77': 5,
    'n3.d77': 9,
}


def _xorshift_bytes(seed, count):
    """Deterministic pseudo-random bytes (32-bit xorshift)."""
    x = seed & 0xFFFFFFFF or 0x2545F491
    out = bytearray()
    while len(out) < count:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out += struct.pack('<I', x)
    return bytes(out[:count])


def _ipl_sector(name):
    """A recognisable, non-fill boot sector. Its contents never reach the
    output because the converter skips it by default (--skip 256)."""
    body = ('D77TOT77WAV TEST FIXTURE ' + name).encode('ascii')
    body = body.ljust(SECTOR_SIZE, b'\x00')
    return body


def _sector_record(c, h, r, data):
    hdr = struct.pack('<BBBBHBBB5xH',
                      c, h, r, 1,                 # C H R N (N=1 -> 256 B)
                      SECTORS_PER_TRACK,          # sectors in this track
                      0x00,                       # density: double
                      0x00,                       # deleted-data mark: no
                      0x00,                       # status: OK
                      len(data))                  # data size
    return hdr + data


def build_d77(name, data_tracks):
    """Return the bytes of one fixture image."""
    seed = sum(ord(ch) * (i + 1) for i, ch in enumerate(name)) * 2654435761
    stream = _xorshift_bytes(seed, data_tracks * SECTORS_PER_TRACK * SECTOR_SIZE)

    tracks = []                                      # list of track byte blobs
    pos = 0
    for t in range(data_tracks):
        c, h = divmod(t, 2)
        secs = []
        for r in range(1, SECTORS_PER_TRACK + 1):
            if t == 0 and r == 1:
                data = _ipl_sector(name)
            elif t == 1 and r == 9:
                data = b'\xE5' * SECTOR_SIZE         # inner fill sector: kept
            else:
                data = stream[pos:pos + SECTOR_SIZE]
            pos += SECTOR_SIZE
            secs.append(_sector_record(c, h, r, data))
        tracks.append(b''.join(secs))

    for fill in (0xE5, 0xFF, 0x00):                  # trailing fill tracks
        t = len(tracks)
        c, h = divmod(t, 2)
        tracks.append(b''.join(
            _sector_record(c, h, r, bytes([fill]) * SECTOR_SIZE)
            for r in range(1, SECTORS_PER_TRACK + 1)))

    offsets = []
    off = HEADER_SIZE
    for blob in tracks:
        offsets.append(off)
        off += len(blob)
    offsets += [0] * (TRACK_TABLE_ENTRIES - len(offsets))
    total = off

    header = bytearray(HEADER_SIZE)
    header[0:16] = name.encode('ascii')[:16].ljust(16, b'\x00')
    header[0x1A] = 0x00                              # not write-protected
    header[0x1B] = 0x00                              # media type: 2D
    header[0x1C:0x20] = struct.pack('<I', total)
    header[0x20:HEADER_SIZE] = struct.pack('<%dI' % TRACK_TABLE_ENTRIES, *offsets)
    return bytes(header) + b''.join(tracks)


def write_fixtures(out_dir):
    """Write every fixture into `out_dir`; return {file name: path}."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for fname, data_tracks in FIXTURES.items():
        path = os.path.join(out_dir, fname)
        with open(path, 'wb') as f:
            f.write(build_d77(os.path.splitext(fname)[0], data_tracks))
        paths[fname] = path
    return paths


def main(argv):
    if len(argv) != 2:
        print('usage: make_fixtures.py OUTDIR', file=sys.stderr)
        return 2
    for fname, path in sorted(write_fixtures(argv[1]).items()):
        print(f'{path}  ({os.path.getsize(path)} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
