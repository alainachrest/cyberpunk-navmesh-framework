"""Cyberpunk 2077 .archive (RDAR) reading and writing.

Writing stores everything uncompressed (zSize == size), which the game reads
as-is. CR2W files go in as their CR2W part plus one segment per buffer, the
same way WolvenKit packs them. See WolvenKit.RED4/Archive/IO/ArchiveWriter.cs.
"""
import hashlib
import struct
import time

MAGIC = 0x52414452  # "RDAR"
VERSION = 12

_CRC64_POLY = 0xC96C5795D7870F42
_crc64_table = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ _CRC64_POLY if _c & 1 else _c >> 1
    _crc64_table.append(_c)


def crc64(data):
    crc = 0xFFFFFFFFFFFFFFFF
    for b in data:
        crc = (crc >> 8) ^ _crc64_table[(crc ^ b) & 0xFF]
    return crc ^ 0xFFFFFFFFFFFFFFFF


def path_hash(path):
    h = 0xCBF29CE484222325
    for b in path.lower().replace("/", "\\").encode():
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


class Reader:
    def __init__(self, path):
        self.f = open(path, "rb")
        magic, ver, ipos, isize = struct.unpack("<IIQI", self.f.read(20))
        if magic != MAGIC:
            raise ValueError("not an archive")
        self.f.seek(ipos)
        _fto, _fts, _crc, nf, ns, nd = struct.unpack("<IIQIII", self.f.read(28))
        self.entries = {}
        for _ in range(nf):
            h, _ts, ninl, ss, se, _ds, _de = struct.unpack("<QqIIIII", self.f.read(36))
            self.f.read(20)
            self.entries[h] = (ninl, ss, se)
        self.segments = [struct.unpack("<QII", self.f.read(16)) for _ in range(ns)]

    def has(self, path):
        return path_hash(path) in self.entries

    def raw_segments(self, path):
        """[(zsize, size, bytes)] as stored (first is the file, the rest buffers)."""
        ninl, ss, se = self.entries[path_hash(path)]
        out = []
        for i in range(ss, se):
            off, z, s = self.segments[i]
            self.f.seek(off)
            out.append((z, s, self.f.read(z)))
        return out


def write(out_path, files):
    """files: [(depot path, first segment bytes, [(disk bytes, mem size), ...] buffers)].
    Segments are stored uncompressed."""
    entries = []
    segs = []
    body = bytearray()
    base = 0xAC  # header (40) + 132 bytes padding
    for path, data, buffers in sorted(files, key=lambda f: path_hash(f[0])):
        first = len(segs)
        segs.append((base + len(body), len(data), len(data)))
        body += data
        for disk, mem in buffers:
            segs.append((base + len(body), len(disk), mem))
            body += disk
        sha = hashlib.sha1(data).digest()
        entries.append((path_hash(path), len(buffers), first, len(segs), sha))
    # index starts on a 4096 boundary
    end = base + len(body)
    pad = (-end) % 4096
    body += b"\0" * pad
    index_pos = base + len(body)

    ts = int((time.time() + 11644473600) * 10_000_000)  # Windows FILETIME
    table = bytearray(struct.pack("<III", len(entries), len(segs), 0))
    for h, ninl, ss, se, sha in entries:
        table += struct.pack("<QqIIIII", h, ts, ninl, ss, se, 0, 0) + sha
    for off, z, s in segs:
        table += struct.pack("<QII", off, z, s)
    index = struct.pack("<IIQ", 8, len(table) + 8, crc64(bytes(table))) + table
    tail_pad = (-(index_pos + len(index))) % 4096
    filesize = index_pos + len(index) + tail_pad

    header = struct.pack("<IIQIQIQ", MAGIC, VERSION, index_pos, len(index), 0, 0, filesize)
    header += struct.pack("<Q", 0)  # custom data length
    out = bytearray(header)
    out += b"\0" * (base - len(out))
    out += body
    out += index
    out += b"\0" * tail_pad
    with open(out_path, "wb") as fh:
        fh.write(out)
    return len(out)
