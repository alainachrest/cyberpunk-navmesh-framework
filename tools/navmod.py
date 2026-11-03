"""Builds navmesh mods for Cyberpunk 2077.

  new sector (ArchiveXL streaming block)   build_sector(), build_block()
  merge into the game's own tiles          merge_into_sector()

Everything is written in the game's own formats (see docs/navmesh-format.md).
"""
import math
import random
import struct

import cr2w
from cr2w import Obj, Prop, p_u8, p_u16, p_u32, p_i32, p_u64, p_f32, p_vlq
import detour

TILE = detour.TILE_SIZE
BUFFER_FLAGS = 0x720000          # what the game's sector buffers use
SECTOR_VERSION = 68
STREAMING_DISTANCE = 274.9231262207031


def _struct(f, props):
    """Bytes of a nested struct value: [(name, type, raw)]."""
    return f.struct_bytes(Obj(None, [Prop(n, t, r) for n, t, r in props]))


def _vec4(f, x, y, z, w):
    return _struct(f, [("X", "Float", p_f32(x)), ("Y", "Float", p_f32(y)), ("Z", "Float", p_f32(z)), ("W", "Float", p_f32(w))])


def _box(f, mn, mx):
    return _struct(f, [("Min", "Vector4", _vec4(f, *mn, 0.0)), ("Max", "Vector4", _vec4(f, *mx, 0.0))])


def _node_record(pos, index, node_id):
    """One worldCompiledNodeInstanceSetupInfo (144 bytes, patch 2.5 layout)."""
    x, y, z = pos
    b = struct.pack("<4f4f3f3f3f3f", x, y, z, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0,
                    0.0, 0.0, 0.0, x, y, z, x, y, z)
    bits = 0x10380100000 | (index & 0x7FFFF)   # flags and priority as the game's navigation nodes
    b += struct.pack("<QQQQQ", 0, node_id, 0, 0, bits)
    b += struct.pack("<ffIB", 3.4028234663852886e38, STREAMING_DISTANCE, 0xFFFFFFFF, 0)
    b += b"\0" * 11
    assert len(b) == 144
    return b


def _res_pos(r, centre, i):
    """A resource's node position: given, or the centre of its tiles."""
    if r.get("pos"):
        return tuple(r["pos"])
    ts = list(r["tiles"].values())
    return (round((min(t.bmin[0] for t in ts) + max(t.bmax[0] for t in ts)) / 2, 1),
            round((min(t.bmin[2] for t in ts) + max(t.bmax[2] for t in ts)) / 2, 1),
            round((min(t.bmin[1] for t in ts) + max(t.bmax[1] for t in ts)) / 2, 1))


def split_resources(tiles, path_fmt, agent="Human"):
    """Groups tiles into the game's 5 x 5 tile resources (162 m squares)."""
    groups = {}
    for key, t in tiles.items():
        groups.setdefault((key[0] // 5, key[1] // 5), {})[key] = t
    out = []
    for (rx, ry), g in sorted(groups.items()):
        out.append(dict(path=path_fmt.format(rx=rx, ry=ry), agent=agent, tiles=g))
    return out


def node_ref_hash(ref):
    """A NodeRef's hash, as the game stores it in node data: FNV-1a 64 of the
    path without its '#' marks (e.g. "$/my_mod/#my_node")."""
    return cr2w.fnv1a64(ref.replace("#", ""))


def _node_ref_bytes(ref):
    b = ref.encode()
    return p_vlq(-len(b)) + b          # length-prefixed, negative = UTF-8


def build_sector(name, resources):
    """A navigation streaming sector holding our own tile resources.

    resources: [dict(path, agent ('Human'/'Vehicle'), tiles {(tx,ty): detour.Tile},
                     ref (optional NodeRef, e.g. "$/my_mod/#node_0", so scripts can
                     switch the node on and off))]
    Returns (cr2w.File, node position, half-extent)."""
    f = cr2w.File()
    for s in ("worldStreamingSector", "cookingPlatform", "ECookingPlatform", "PLATFORM_PC",
              "localInplaceResource", "array:rRef:CResource", "level", "Uint8", "category",
              "worldStreamingSectorCategory", "Navigation"):
        f.nid(s)
    sector = Obj("worldStreamingSector")
    f.exports.append(sector)
    rng = random.Random(name)

    # node position: centre of all tiles
    allt = [t for r in resources for t in r["tiles"].values()]
    mn = [min(t.bmin[0] for t in allt), min(t.bmin[2] for t in allt), min(t.bmin[1] for t in allt)]
    mx = [max(t.bmax[0] for t in allt), max(t.bmax[2] for t in allt), max(t.bmax[1] for t in allt)]
    centre = [round((mn[k] + mx[k]) / 2, 1) for k in range(3)]
    half = [max(mx[k] - centre[k], centre[k] - mn[k]) for k in range(3)]

    nodes_data = b""
    node_idx = []
    res_idx = []
    for i, r in enumerate(resources):
        f.imports.append((r["path"], 0, 8))           # embedded
        node = Obj("worldNavigationNode")
        node.props = [
            Prop("debugName", "CName", p_u16(f.nid("navNode_%s_%d" % (name, i)))),
            Prop("sourcePrefabHash", "Uint64", p_u64(rng.getrandbits(64))),
            Prop("navigationTileResource", "raRef:worldNavigationTileResource", p_u16(i + 1)),
        ]
        f.exports.append(node)
        node_idx.append(len(f.exports) - 1)
        node_id = node_ref_hash(r["ref"]) if r.get("ref") else rng.getrandbits(40)
        nodes_data += _node_record(_res_pos(r, centre, i), i, node_id)

    for i, r in enumerate(resources):
        res = Obj("worldNavigationTileResource")
        keys = sorted(r["tiles"])                     # x-major, as the game orders them
        rows = []
        refs = []
        pos = _res_pos(r, centre, i)
        for k, key in enumerate(keys):
            t = r["tiles"][key]
            bi = f.add_buffer(detour.write_tile(t), BUFFER_FLAGS)
            refs.append(0x80000000 | (bi + 2))       # +1 for 1-based, +1 for the node data buffer before
            rows.append(_struct(f, [("tileX", "Int32", p_i32(t.x)), ("tileY", "Int32", p_i32(t.y)),
                                    ("tileIndex", "Uint32", p_u32(k)), ("bufferIndex", "Uint32", p_u32(k))]))
        ts = list(r["tiles"].values())
        rmn = (min(t.bmin[0] for t in ts), min(t.bmin[2] for t in ts), min(t.bmin[1] for t in ts))
        rmx = (max(t.bmax[0] for t in ts), max(t.bmax[2] for t in ts), max(t.bmax[1] for t in ts))
        lo = (rmn[0] - pos[0], rmn[1] - pos[1], rmn[2] - pos[2])
        hi = (rmx[0] - pos[0], rmx[1] - pos[1], rmx[2] - pos[2])
        res.props = [
            Prop("cookingPlatform", "ECookingPlatform", p_u16(f.nid("PLATFORM_PC"))),
            Prop("localBoundingBox", "Box", _box(f, lo, hi)),
            Prop("tilesData", "array:worldNavigationTileData", p_u32(len(rows)) + b"".join(rows)),
            Prop("tileBuffers", "array:DataBuffer", p_u32(len(refs)) + b"".join(p_u32(x) for x in refs)),
            Prop("agentSize", "NavGenAgentSize", p_u16(f.nid(r.get("agent", "Human")))),
        ]
        f.exports.append(res)
        res_idx.append(len(f.exports) - 1)
        f.embedded.append((i + 1, len(f.exports) - 1, 0))

    # node data goes first among the buffers (the game's sectors do the same)
    f.buffers.insert(0, [BUFFER_FLAGS, nodes_data, len(nodes_data)])

    sector.props = [
        Prop("cookingPlatform", "ECookingPlatform", p_u16(f.nid("PLATFORM_PC"))),
        Prop("localInplaceResource", "array:rRef:CResource",
             p_u32(len(resources)) + b"".join(p_u16(i + 1) for i in range(len(resources)))),
        Prop("level", "Uint8", p_u8(3)),
        Prop("category", "worldStreamingSectorCategory", p_u16(f.nid("Navigation"))),
    ]
    inner = p_u32(0x80000001)                         # node data buffer
    inner += p_vlq(len(node_idx)) + b"".join(p_i32(i + 1) for i in node_idx)
    refs = [r["ref"] for r in resources if r.get("ref")]
    inner += p_vlq(len(refs)) + b"".join(_node_ref_bytes(x) for x in refs)   # node refs
    inner += p_vlq(1) + p_i32(0)                      # variant indices
    inner += p_i32(0)                                 # persistent node index
    sector.appendix = p_i32(SECTOR_VERSION) + p_i32(len(inner) + 4) + inner
    return f, centre, half


def build_block(sector_paths):
    """A worldStreamingBlock listing navigation sectors: [(path, centre)]."""
    f = cr2w.File()
    f.nid("worldStreamingBlock")
    blk = Obj("worldStreamingBlock")
    descs = []
    for i, (path, centre) in enumerate(sector_paths):
        f.imports.append((path, 0, 4))                # soft async reference
        r = STREAMING_DISTANCE
        mn = (centre[0] - r, centre[1] - r, centre[2] - r)
        mx = (centre[0] + r, centre[1] + r, centre[2] + r)
        box = _struct(f, [("Min", "Vector4", _vec4(f, *mn, 1.0)), ("Max", "Vector4", _vec4(f, *mx, 1.0))])
        descs.append(_struct(f, [
            ("data", "raRef:worldStreamingSector", p_u16(i + 1)),
            ("streamingBox", "Box", box),
            ("numNodeRanges", "Uint32", p_u32(1)),
            ("level", "Uint8", p_u8(3)),
            ("category", "worldStreamingSectorCategory", p_u16(f.nid("Navigation"))),
        ]))
    blk.props = [
        Prop("cookingPlatform", "ECookingPlatform", p_u16(f.nid("PLATFORM_PC"))),
        Prop("descriptors", "array:worldStreamingSectorDescriptor", p_u32(len(descs)) + b"".join(descs)),
    ]
    f.exports.append(blk)
    return f


# --- merging into the game's tiles ----------------------------------------------

def merge_tile(base, add):
    """Adds the ground polygons of tile `add` to tile `base` (same x, y), keeping
    base's off-mesh connections. New polygons don't link to old ones (an island)."""
    nb = base.offmesh_base
    nv = len(base.verts)
    shift = len(add.polys[:add.offmesh_base])
    # off-mesh polys move up by `shift`; their verts stay at the end of the vert list
    new_polys = base.polys[:nb]
    for p in add.polys[:add.offmesh_base]:
        q = dict(p)
        q["verts"] = [v + nv for v in p["verts"]]          # our verts go after all of base's
        # internal neighbours are 1-based poly indices: shift past base's ground polys;
        # tile-edge portals become walls (they'd need matching neighbours to link)
        q["neis"] = [(n + nb) if (n and not n & detour.EXT_LINK) else 0 for n in p["neis"]]
        q["first_link"] = 0
        new_polys.append(q)
    off_polys = [dict(p) for p in base.polys[nb:]]           # off-mesh polys keep their verts
    base.verts = list(base.verts) + list(add.verts)
    base.polys = new_polys + off_polys
    # detail meshes: ours have no extra verts; tris appended
    tri_base = len(base.detail_tris)
    for vb, tb, vc, tc in add.detail_meshes:
        base.detail_meshes.append((len(base.detail_verts), tri_base + tb, vc, tc))
    base.detail_tris = list(base.detail_tris) + list(add.detail_tris)
    base.offmesh_base = nb + shift
    # off-mesh connection records point at their polygon index (u16 at byte 28)
    recs = []
    for o in base.offmesh:
        poly = struct.unpack_from("<H", o, 28)[0]
        if poly >= nb:
            poly += shift
        recs.append(o[:28] + struct.pack("<H", poly) + o[30:])
    base.offmesh = recs
    base.bmin = [min(base.bmin[k], add.bmin[k]) for k in range(3)]
    base.bmax = [max(base.bmax[k], add.bmax[k]) for k in range(3)]
    links = detour.link_count(base.polys[:base.offmesh_base], len(base.offmesh))
    base.max_links = links
    base.links = b""
    detour.build_bv(base)
    return base
