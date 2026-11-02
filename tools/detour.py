"""Cyberpunk 2077 navmesh tiles: Recast/Detour dtMeshTile data, read and write.

The game's tiles are stock Detour tile data (DetourNavMeshBuilder's
dtCreateNavMeshData output) with:
  - version 8 (stock Detour is 7)
  - 3 vertices per polygon (DT_VERTS_PER_POLYGON = 3)
  - off-mesh connection records of 40 bytes (stock: 36)
  - bvNodeCount = 2 * ground polygons (older Detour)
Coordinates are Detour's Y-up: (x, height, y) in game terms.
See docs/navmesh-format.md.
"""
import math
import struct

NVP = 3
VERSION = 8
EXT_LINK = 0x8000
TILE_SIZE = 32.4
HUMAN = (1.8, 0.3, 0.6)      # walkable height, radius, climb
VEHICLE = (2.2, 1.5, 0.5)
CELL = 0.1                    # bvQuantFactor = 1 / CELL


def align4(n):
    return (n + 3) & ~3


class Tile:
    def __init__(self):
        self.x = self.y = self.layer = self.user_id = 0
        self.version = VERSION
        self.agent = HUMAN
        self.bmin = [0.0, 0.0, 0.0]
        self.bmax = [0.0, 0.0, 0.0]
        self.quant = 1.0 / CELL
        self.verts = []        # [(x, h, y)]
        self.polys = []        # dict(verts=[3], neis=[3], flags, area, type, first_link)
        self.max_links = 0
        self.links = b""       # raw, normally all zero
        self.detail_meshes = []  # (vertBase, triBase, vertCount, triCount)
        self.detail_verts = []
        self.detail_tris = []    # (a, b, c, flags)
        self.bv = []             # (bmin3, bmax3, i)
        self.bv_count = 0
        self.offmesh = []        # raw 40-byte records
        self.offmesh_base = 0


def read_tile(b):
    t = Tile()
    h = struct.unpack_from("<4s14I", b, 0)
    if h[0] != b"VAND":
        raise ValueError("not a navmesh tile")
    (_, t.version, x, y, t.layer, t.user_id, npoly, nvert, nlink, ndm, ndv, ndt, nbv, noff, t.offmesh_base) = h
    t.x = x - (1 << 32) if x >= 1 << 31 else x
    t.y = y - (1 << 32) if y >= 1 << 31 else y
    f = struct.unpack_from("<10f", b, 60)
    t.agent = f[0:3]
    t.bmin, t.bmax, t.quant = list(f[3:6]), list(f[6:9]), f[9]
    p = 100
    for i in range(nvert):
        t.verts.append(struct.unpack_from("<3f", b, p)); p += 12
    for i in range(npoly):
        fl, = struct.unpack_from("<I", b, p)
        v = struct.unpack_from("<3H", b, p + 4)
        n = struct.unpack_from("<3H", b, p + 10)
        flags, vc, at = struct.unpack_from("<HBB", b, p + 16)
        t.polys.append(dict(first_link=fl, verts=list(v[:vc]), neis=list(n[:vc]), flags=flags,
                            area=at & 0x3F, type=at >> 6, vcount=vc))
        p += 20
    t.max_links = nlink
    t.links = b[p:p + 16 * nlink]; p += 16 * nlink
    for i in range(ndm):
        vb, tb, vc, tc = struct.unpack_from("<IIBB", b, p)
        t.detail_meshes.append((vb, tb, vc, tc)); p += 12
    for i in range(ndv):
        t.detail_verts.append(struct.unpack_from("<3f", b, p)); p += 12
    for i in range(ndt):
        t.detail_tris.append(struct.unpack_from("<4B", b, p)); p += 4
    for i in range(nbv):
        v = struct.unpack_from("<6Hi", b, p)
        t.bv.append((v[0:3], v[3:6], v[6])); p += 16
    t.bv_count = nbv
    for i in range(noff):
        t.offmesh.append(b[p:p + 40]); p += 40
    if p != len(b):
        raise ValueError(f"tile size mismatch: read {p} of {len(b)}")
    return t


def write_tile(t):
    out = bytearray()
    ground = t.offmesh_base
    out += struct.pack("<4s14I", b"VAND", t.version, t.x & 0xFFFFFFFF, t.y & 0xFFFFFFFF, t.layer, t.user_id,
                       len(t.polys), len(t.verts), t.max_links, len(t.detail_meshes), len(t.detail_verts),
                       len(t.detail_tris), t.bv_count, len(t.offmesh), ground)
    out += struct.pack("<10f", *t.agent, *t.bmin, *t.bmax, t.quant)
    for v in t.verts:
        out += struct.pack("<3f", *v)
    for p in t.polys:
        vs = list(p["verts"]) + [0] * (NVP - len(p["verts"]))
        ns = list(p["neis"]) + [0] * (NVP - len(p["neis"]))
        out += struct.pack("<I3H3HHBB", p.get("first_link", 0), *vs, *ns, p["flags"], len(p["verts"]),
                           (p["area"] & 0x3F) | (p["type"] << 6))
    out += t.links if len(t.links) == 16 * t.max_links else b"\0" * (16 * t.max_links)
    for d in t.detail_meshes:
        out += struct.pack("<IIBBxx", *d)
    for v in t.detail_verts:
        out += struct.pack("<3f", *v)
    for tri in t.detail_tris:
        out += struct.pack("<4B", *tri)
    bv = list(t.bv) + [((0, 0, 0), (0, 0, 0), 0)] * (t.bv_count - len(t.bv))
    for bmin, bmax, i in bv:
        out += struct.pack("<6Hi", *bmin, *bmax, i)
    for o in t.offmesh:
        out += o
    return bytes(out)


# --- building ------------------------------------------------------------------

def link_count(polys, noffmesh=0):
    """Detour's maxLinkCount: every edge, plus 2 per portal edge, plus 2 per off-mesh link end."""
    edges = portals = 0
    for p in polys:
        for n in p["neis"]:
            edges += 1
            if n & EXT_LINK and (n & 0xF) != 0xF:
                portals += 1
    return edges + portals * 2 + noffmesh * 4  # both ends of each off-mesh link (game tiles match this)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def msvc_qsort(a, start, end, comp):
    """Sorts a[start:end] in place exactly like the MSVC C runtime's qsort (which
    the game's navmesh baker used), so ties land in the same order."""
    def shortsort(lo, hi):
        while hi > lo:
            mx = lo
            for p in range(lo + 1, hi + 1):
                if comp(a[p], a[mx]) > 0:
                    mx = p
            a[mx], a[hi] = a[hi], a[mx]
            hi -= 1

    if end - start < 2:
        return
    stack = []
    lo, hi = start, end - 1
    while True:
        size = hi - lo + 1
        if size <= 8:
            shortsort(lo, hi)
        else:
            mid = lo + size // 2
            if comp(a[lo], a[mid]) > 0: a[lo], a[mid] = a[mid], a[lo]
            if comp(a[lo], a[hi]) > 0: a[lo], a[hi] = a[hi], a[lo]
            if comp(a[mid], a[hi]) > 0: a[mid], a[hi] = a[hi], a[mid]
            loguy, higuy = lo, hi
            while True:
                if mid > loguy:
                    loguy += 1
                    while loguy < mid and comp(a[loguy], a[mid]) <= 0:
                        loguy += 1
                if mid <= loguy:
                    loguy += 1
                    while loguy <= hi and comp(a[loguy], a[mid]) <= 0:
                        loguy += 1
                higuy -= 1
                while higuy > mid and comp(a[higuy], a[mid]) > 0:
                    higuy -= 1
                if higuy < loguy:
                    break
                a[loguy], a[higuy] = a[higuy], a[loguy]
                if mid == higuy:
                    mid = loguy
            higuy += 1
            if mid < higuy:
                higuy -= 1
                while higuy > mid and comp(a[higuy], a[mid]) == 0:
                    higuy -= 1
            if mid >= higuy:
                higuy -= 1
                while higuy > lo and comp(a[higuy], a[mid]) == 0:
                    higuy -= 1
            if higuy - lo >= hi - loguy:
                if lo < higuy: stack.append((lo, higuy))
                if loguy < hi:
                    lo = loguy
                    continue
            else:
                if loguy < hi: stack.append((loguy, hi))
                if lo < higuy:
                    hi = higuy
                    continue
        if not stack:
            return
        lo, hi = stack.pop()


def build_bv(t):
    """Detour's createBVTree over the ground polygons, using the detail mesh
    (poly verts + extra detail verts) for bounds, quantised by bvQuantFactor."""
    q = t.quant
    items = []
    for i in range(t.offmesh_base):
        p = t.polys[i]
        pts = [t.verts[v] for v in p["verts"]]
        if i < len(t.detail_meshes):
            vb, tb, vc, tc = t.detail_meshes[i]
            pts += t.detail_verts[vb:vb + vc]
        mn = [min(v[k] for v in pts) for k in range(3)]
        mx = [max(v[k] for v in pts) for k in range(3)]
        # Recast vertices sit on the voxel grid; the game's trees are built from
        # those voxel coordinates, so snap instead of trusting float error.
        bmin = tuple(_clamp(int(math.floor((mn[k] - t.bmin[k]) * q + 1e-3)), 0, 0xFFFF) for k in range(3))
        bmax = tuple(_clamp(int(math.ceil((mx[k] - t.bmin[k]) * q - 1e-3)), 0, 0xFFFF) for k in range(3))
        items.append([bmin, bmax, i])
    nodes = []

    def subdivide(imin, imax):
        icur = len(nodes)
        nodes.append(None)
        if imax - imin == 1:
            nodes[icur] = (items[imin][0], items[imin][1], items[imin][2])
            return
        sub = items[imin:imax]
        bmin = tuple(min(it[0][k] for it in sub) for k in range(3))
        bmax = tuple(max(it[1][k] for it in sub) for k in range(3))
        ext = [bmax[k] - bmin[k] for k in range(3)]
        axis = 0
        if ext[1] > ext[axis]:
            axis = 1
        if ext[2] > ext[axis]:
            axis = 2
        msvc_qsort(items, imin, imax, lambda a, b: (a[0][axis] > b[0][axis]) - (a[0][axis] < b[0][axis]))
        isplit = imin + (imax - imin) // 2
        subdivide(imin, isplit)
        subdivide(isplit, imax)
        nodes[icur] = (bmin, bmax, -(len(nodes) - icur))

    if items:
        subdivide(0, len(items))
    t.bv = nodes
    t.bv_count = 2 * t.offmesh_base


def finish(t):
    """Fills in the derived parts: link count, BV tree."""
    t.max_links = link_count(t.polys[:t.offmesh_base] if t.offmesh else t.polys, len(t.offmesh))
    t.links = b""
    build_bv(t)


def _edge_on_boundary(a, b):
    return 1


def flat_tiles(x0, y0, x1, y1, z, agent=HUMAN, layer=0, area=3, flags=3):
    """Navmesh for a flat rectangle (world x0..x1, y0..y1 at height z), split on
    the game's 32.4 m tile grid. Returns {(tx, ty): Tile}. Each tile piece is
    one square of two triangles; edges shared with the neighbouring piece are
    portals, the rectangle's outline is wall."""
    tiles = {}
    tx0, tx1 = math.floor(x0 / TILE_SIZE), math.floor((x1 - 1e-4) / TILE_SIZE)
    ty0, ty1 = math.floor(y0 / TILE_SIZE), math.floor((y1 - 1e-4) / TILE_SIZE)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            ax, bx = max(x0, tx * TILE_SIZE), min(x1, (tx + 1) * TILE_SIZE)
            ay, by = max(y0, ty * TILE_SIZE), min(y1, (ty + 1) * TILE_SIZE)
            t = Tile()
            t.x, t.y, t.layer, t.agent = tx, ty, layer, agent
            t.bmin = [tx * TILE_SIZE, z - 1.0, ty * TILE_SIZE]
            t.bmax = [(tx + 1) * TILE_SIZE, z + 1.0, (ty + 1) * TILE_SIZE]
            # same corner order as the game's single-square tiles:
            # 0 (min x, max y), 1 (max x, max y), 2 (max x, min y), 3 (min x, min y)
            t.verts = [(ax, z, by), (bx, z, by), (bx, z, ay), (ax, z, ay)]
            east = EXT_LINK | 0 if bx < x1 - 1e-4 else 0
            north = EXT_LINK | 2 if by < y1 - 1e-4 else 0
            west = EXT_LINK | 4 if ax > x0 + 1e-4 else 0
            south = EXT_LINK | 6 if ay > y0 + 1e-4 else 0
            # triangle 0: 0-1-2 (north edge, east edge, diagonal -> poly 1)
            # triangle 1: 0-2-3 (diagonal -> poly 0, south edge, west edge)
            t.polys = [
                dict(verts=[0, 1, 2], neis=[north, east, 2], flags=flags, area=area, type=0),
                dict(verts=[0, 2, 3], neis=[1, south, west], flags=flags, area=area, type=0),
            ]
            t.detail_meshes = [(0, 0, 0, 1), (0, 1, 0, 1)]
            t.detail_tris = [(0, 1, 2, 0x15), (0, 1, 2, 0x15)]
            t.offmesh_base = 2
            finish(t)
            tiles[(tx, ty)] = t
    return tiles
