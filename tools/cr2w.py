"""Minimal CR2W (REDengine 4 resource) reader and writer.

Enough for Cyberpunk 2077 streaming sectors, navigation tile resources and
streaming blocks: property values are kept as raw bytes (with helpers to read
and build nested structs), so a file can be read, edited and written back.

Layout follows WolvenKit's CR2WReader/CR2WWriter (WolvenKit.RED4/Archive/IO).
Buffers are written uncompressed (diskSize == memSize).
"""
import struct
import zlib

MAGIC = b"CR2W"
DEADBEEF = 0xDEADBEEF


def fnv1a32(s):
    h = 0x811C9DC5
    for b in s.encode():
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def fnv1a64(s):
    h = 0xCBF29CE484222325
    for b in s.encode():
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def short_hash(s):
    """CName short hash: FNV-1a 64 folded to 32 bits ("" is 0)."""
    if s == "":
        return 0
    h = fnv1a64(s)
    return ((h >> 32) ^ h) & 0xFFFFFFFF


def crc32(b, start=0):
    return zlib.crc32(b, start) & 0xFFFFFFFF


class Prop:
    __slots__ = ("name", "type", "raw")

    def __init__(self, name, type_, raw):
        self.name, self.type, self.raw = name, type_, raw

    def __repr__(self):
        return f"Prop({self.name}:{self.type}={self.raw[:24].hex()}{'...' if len(self.raw) > 24 else ''})"


class Obj:
    """A class instance: properties in order, plus any trailing (appendix) bytes."""

    def __init__(self, cls, props=None, appendix=b"", parent=0, flags=0, template=0):
        self.cls = cls
        self.props = props or []
        self.appendix = appendix
        self.parent, self.flags, self.template = parent, flags, template

    def get(self, name):
        for p in self.props:
            if p.name == name:
                return p
        return None

    def set(self, name, type_, raw, after=None):
        p = self.get(name)
        if p:
            p.type, p.raw = type_, raw
            return p
        p = Prop(name, type_, raw)
        if after is None:
            self.props.append(p)
        else:
            i = [q.name for q in self.props].index(after)
            self.props.insert(i + 1, p)
        return p

    def remove(self, name):
        self.props = [p for p in self.props if p.name != name]


class File:
    def __init__(self):
        self.version = 195
        self.flags = 0
        self.timestamp = 0
        self.build = 0
        self.names = [""]          # name table, index 0 is ""
        self.imports = []          # (path, className, flags)
        self.exports = []          # Obj
        self.buffers = []          # [flags, disk bytes, memSize] (memSize != len: Kraken-compressed)
        self.embedded = []         # (importIndex 1-based, chunkIndex 0-based, pathHash)

    # names --------------------------------------------------------------
    def name(self, i):
        return self.names[i]

    def nid(self, s):
        if s not in self.names:
            self.names.append(s)
        return self.names.index(s)

    # reading --------------------------------------------------------------
    @classmethod
    def read(cls, data, buffer_data=None):
        """data: the CR2W bytes. buffer_data: optional list of decompressed buffer
        bytes (as found in archive segments). Without it, buffers are read from
        the file and must be stored uncompressed."""
        f = cls()
        if data[:4] != MAGIC:
            raise ValueError("not a CR2W file")
        (f.version, f.flags, f.timestamp, f.build, objectsEnd, buffersEnd, _crc, _n) = struct.unpack_from("<IIQIIIII", data, 4)
        tabs = [struct.unpack_from("<III", data, 40 + 12 * i) for i in range(10)]
        so, sl, _ = tabs[0]
        strbuf = data[so:so + sl]

        def s(o):
            return strbuf[o:strbuf.index(b"\0", o)].decode()

        f.names = [s(struct.unpack_from("<II", data, tabs[1][0] + 8 * i)[0]) for i in range(tabs[1][1])]
        for i in range(tabs[2][1]):
            o, c, fl = struct.unpack_from("<IHH", data, tabs[2][0] + 8 * i)
            f.imports.append((s(o), c, fl))
        exp = [struct.unpack_from("<HHIIIiI", data, tabs[4][0] + 24 * i) for i in range(tabs[4][1])]
        for (ci, fl, parent, size, off, tmpl, _c) in exp:
            obj, end = f._read_class(data, off, f.names[ci])
            obj.flags, obj.parent, obj.template = fl, parent, tmpl
            obj.appendix = data[end:off + size]
            f.exports.append(obj)
        for i in range(tabs[5][1]):
            fl, idx, off, disk, mem, _c = struct.unpack_from("<IIIIII", data, tabs[5][0] + 24 * i)
            if buffer_data is not None:
                b = buffer_data[i]
                if isinstance(b, tuple):
                    f.buffers.append([fl, b[0], b[1]])
                else:
                    f.buffers.append([fl, b, len(b)])
            else:
                f.buffers.append([fl, data[off:off + disk], mem])
        for i in range(tabs[6][1]):
            f.embedded.append(struct.unpack_from("<IIQ", data, tabs[6][0] + 16 * i))
        return f

    def _read_class(self, data, off, cls_name):
        """Reads a class blob at off: 0x00, then {name u16, type u16, size u32, value}
        until name 0. Returns (Obj, end offset)."""
        obj = Obj(cls_name)
        if data[off] != 0:
            raise ValueError(f"unexpected class prefix {data[off]} at {off}")
        p = off + 1
        while True:
            n = struct.unpack_from("<H", data, p)[0]
            p += 2
            if n == 0:
                break
            t, size = struct.unpack_from("<HI", data, p)
            p += 6
            obj.props.append(Prop(self.names[n], self.names[t], data[p:p + size - 4]))
            p += size - 4
        return obj, p

    def parse_struct(self, raw, offset=0):
        """A nested struct value (same layout as a class). Returns (Obj, end)."""
        return self._read_class(raw, offset, None)

    # writing --------------------------------------------------------------
    def class_bytes(self, obj):
        out = bytearray(b"\0")
        for p in obj.props:
            out += struct.pack("<HHI", self.nid(p.name), self.nid(p.type), len(p.raw) + 4)
            out += p.raw
        out += b"\0\0"
        return bytes(out)

    def struct_bytes(self, obj):
        return self.class_bytes(obj)

    def write(self):
        # serialise chunks first (may add names)
        chunks = [self.class_bytes(o) + o.appendix for o in self.exports]
        for o in self.exports:
            self.nid(o.cls)
        for path, c, fl in self.imports:
            pass
        # string buffer: names, then import paths
        strbuf = bytearray(b"")
        offs = {}
        for s in self.names:
            if s not in offs:
                offs[s] = len(strbuf)
                strbuf += s.encode() + b"\0"
        imp_offs = {}
        for path, _c, _fl in self.imports:
            if path not in imp_offs:
                imp_offs[path] = len(strbuf)
                strbuf += path.encode() + b"\0"
        strbuf = bytes(strbuf)

        nexp, nbuf, nemb = len(self.exports), len(self.buffers), len(self.embedded)
        pos = 160
        t_str = (pos, len(strbuf), crc32(strbuf)); pos += len(strbuf)
        names_b = b"".join(struct.pack("<II", offs[s], short_hash(s)) for s in self.names)
        t_names = (pos, len(self.names), crc32(names_b)); pos += len(names_b)
        imp_b = b"".join(struct.pack("<IHH", imp_offs[p], c, fl) for p, c, fl in self.imports)
        t_imp = (pos if self.imports else 0, len(self.imports), crc32(imp_b) if self.imports else 0); pos += len(imp_b)
        prop_b = b"\0" * 16
        t_prop = (pos, 1, crc32(prop_b)); pos += 16
        exp_pos = pos; pos += 24 * nexp
        buf_pos = pos; pos += 24 * nbuf
        emb_pos = pos; pos += 16 * nemb
        data_start = pos
        exp_b = bytearray()
        o = data_start
        for obj, ch in zip(self.exports, chunks):
            exp_b += struct.pack("<HHIIIiI", self.nid(obj.cls), obj.flags, obj.parent, len(ch), o, obj.template, 0)  # the game ships 0 here
            o += len(ch)
        objects_end = o
        buf_b = bytearray()
        bufdata = bytearray()
        for fl, b, mem in self.buffers:
            buf_b += struct.pack("<IIIIII", fl, 0, objects_end + len(bufdata), len(b), mem, crc32(b))
            bufdata += b
        emb_b = b"".join(struct.pack("<IIQ", *e) for e in self.embedded)
        t_exp = (exp_pos if nexp else 0, nexp, crc32(exp_b) if nexp else 0)
        t_buf = (buf_pos if nbuf else 0, nbuf, crc32(buf_b) if nbuf else 0)
        t_emb = (emb_pos if nemb else 0, nemb, crc32(emb_b) if nemb else 0)
        tables = [t_str, t_names, t_imp, t_prop, t_exp, t_buf, t_emb, (0, 0, 0), (0, 0, 0), (0, 0, 0)]
        buffers_end = objects_end + len(bufdata)
        num_chunks = 6
        h = crc32(MAGIC)
        h = crc32(struct.pack("<IIQIIIII", self.version, self.flags, self.timestamp, self.build,
                              objects_end, buffers_end, DEADBEEF, num_chunks), h)
        for t in tables:
            h = crc32(struct.pack("<III", *t), h)
        out = bytearray(MAGIC)
        out += struct.pack("<IIQIIIII", self.version, self.flags, self.timestamp, self.build,
                           objects_end, buffers_end, h, num_chunks)
        for t in tables:
            out += struct.pack("<III", *t)
        assert len(out) == 160
        out += strbuf + names_b + imp_b + prop_b + exp_b + buf_b + emb_b
        assert len(out) == data_start
        for ch in chunks:
            out += ch
        self._objects_end = objects_end
        out += bufdata
        return bytes(out)

    def segments(self):
        """For packing into an archive: the CR2W part, then each buffer as
        (disk bytes, memSize)."""
        full = self.write()
        return full[:self._objects_end], [(b, mem) for _fl, b, mem in self.buffers]

    def buffer_data(self, i):
        """Uncompressed bytes of buffer i (raises if it is still compressed)."""
        fl, b, mem = self.buffers[i]
        if len(b) != mem:
            raise ValueError("buffer %d is compressed" % i)
        return b

    def set_buffer(self, i, data):
        self.buffers[i][1] = data
        self.buffers[i][2] = len(data)

    def add_buffer(self, data, flags=0x720000):
        self.buffers.append([flags, data, len(data)])
        return len(self.buffers) - 1


# value helpers ----------------------------------------------------------------
def u8(b): return struct.unpack("<B", b)[0]
def u16(b): return struct.unpack("<H", b)[0]
def i32(b): return struct.unpack("<i", b)[0]
def u32(b): return struct.unpack("<I", b)[0]
def u64(b): return struct.unpack("<Q", b)[0]
def f32(b): return struct.unpack("<f", b)[0]
def p_u8(v): return struct.pack("<B", v)
def p_u16(v): return struct.pack("<H", v)
def p_i32(v): return struct.pack("<i", v)
def p_u32(v): return struct.pack("<I", v)
def p_u64(v): return struct.pack("<Q", v)
def p_f32(v): return struct.pack("<f", v)


def vlq(b, p):
    """CR2W variable-length int (WolvenKit ReadVLQInt32). Returns (value, new p)."""
    c = b[p]; p += 1
    neg = c & 0x80
    val = c & 0x3F
    shift = 6
    more = c & 0x40
    while more:
        c = b[p]; p += 1
        val |= (c & 0x7F) << shift
        shift += 7
        more = c & 0x80
    return (-val if neg else val), p


def p_vlq(v):
    neg = v < 0
    v = abs(v)
    first = (v & 0x3F) | (0x80 if neg else 0)
    v >>= 6
    out = bytearray()
    if v:
        first |= 0x40
    out.append(first)
    while v:
        c = v & 0x7F
        v >>= 7
        if v:
            c |= 0x80
        out.append(c)
    return bytes(out)
