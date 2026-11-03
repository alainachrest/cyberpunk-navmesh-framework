"""Navmesh for Real Netrunning's cyberspace.

Every floor of a network is a maze of square rooms, one room per navmesh tile
(32.4 m), up to 8 x 8. Each room's navmesh is the same: the floor inside its
walls, plus a short corridor through each wall that has a doorway. Which
doorways exist is only known when the mod generates the maze, so every tile is
built in all 16 versions (one per combination of its 4 doorways), each doorway
is a world variant, and the mod switches the variants on for the doorways the
maze has (Codeware's WorldStateSystem.ToggleVariant).

Floors sit in fixed slots (each its own spot, so their doorways never share a
tile). Keep the constants below in step with real_netrunning/modules/cyberkit.lua.

  python rn_cyberspace.py OUT_DIR
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detour    # noqa: E402
import navmod    # noqa: E402
import rdar      # noqa: E402

T = detour.TILE_SIZE            # room size = tile size
GRID = 8                         # rooms per side, at most
SLOTS = 12                       # floor slots
SLOT_STEP = 10                   # tiles between slot corners (along x)
CORNER = (-34, 27)               # tile of slot 1's room (0, 0)
TOP_Z = 9000.0                   # floor surface of slot 1
FLOOR_GAP = 18.0                 # each slot 18 m lower than the one before
DOOR = 4.0                       # doorway width
WALL = 0.5                       # wall thickness
RADIUS = detour.HUMAN[1]         # keep NPCs this far from walls

MOD = "mod\\real_netrunning\\cyberspace"
VARIANT_REF = "$/real_netrunning/cyberspace/#floor_%d"


def slot_corner(slot):
    """Tile (tx, ty) of room (0, 0) on floor slot `slot` (1-based)."""
    return CORNER[0] + (slot - 1) * SLOT_STEP, CORNER[1]


def slot_z(slot):
    return TOP_Z - (slot - 1) * FLOOR_GAP


def door_name(axis, x, y):
    """'e': between room (x, y) and (x+1, y); 'n': between (x, y) and (x, y+1)."""
    return "door_%s_%d_%d" % (axis, x, y)


def room_tris(x0, y0, z, open_sides):
    """Triangles for one room tile at world corner (x0, y0). open_sides: set of
    'e', 'w', 'n', 's' with a doorway."""
    b = WALL / 2 + RADIUS                 # inside the walls
    h = DOOR / 2 - RADIUS                 # half of the walkable doorway
    c = T / 2
    xs = [b, c - h, c + h, T - b]
    tris = []
    for i in range(3):
        for j in range(3):
            tris += detour.rect_tris(x0 + xs[i], y0 + xs[j], x0 + xs[i + 1], y0 + xs[j + 1], z)
    if "e" in open_sides:
        tris += detour.rect_tris(x0 + T - b, y0 + c - h, x0 + T, y0 + c + h, z)
    if "w" in open_sides:
        tris += detour.rect_tris(x0, y0 + c - h, x0 + b, y0 + c + h, z)
    if "n" in open_sides:
        tris += detour.rect_tris(x0 + c - h, y0 + T - b, x0 + c + h, y0 + T, z)
    if "s" in open_sides:
        tris += detour.rect_tris(x0 + c - h, y0, x0 + c + h, y0 + b, z)
    return tris


def slot_resources(slot):
    """The tile resources for one floor slot, with every tile in all versions."""
    ref = VARIANT_REF % slot
    cx, cy = slot_corner(slot)
    z = slot_z(slot)
    variants = []
    ids = {}
    for x in range(GRID):
        for y in range(GRID):
            if x + 1 < GRID:
                ids[("e", x, y)] = None
            if y + 1 < GRID:
                ids[("n", x, y)] = None
    for k in sorted(ids, key=lambda k: (k[0], k[1], k[2])):
        name = door_name(*k)
        vid = navmod.variant_id(ref, name)
        ids[k] = vid
        variants.append(dict(ref=ref, name=name, id=vid, range=len(variants) + 1))

    tiles, versions = {}, {}
    for x in range(GRID):
        for y in range(GRID):
            tx, ty = cx + x, cy + y
            sides = {}                    # side -> variant id of its doorway
            if x + 1 < GRID: sides["e"] = ids[("e", x, y)]
            if x > 0: sides["w"] = ids[("e", x - 1, y)]
            if y + 1 < GRID: sides["n"] = ids[("n", x, y)]
            if y > 0: sides["s"] = ids[("n", x, y - 1)]
            every = sorted(sides.values())
            vs = []
            names = sorted(sides)
            for n in range(len(names) + 1):
                for open_ in itertools.combinations(names, n):
                    t = detour.tile_from_triangles(tx, ty, room_tris(tx * T, ty * T, z, set(open_)), layer=1)
                    vs.append((t, sorted(sides[s] for s in open_), every))
            tiles[(tx, ty)] = vs[0][0]
            versions[(tx, ty)] = vs
    res = navmod.split_resources(tiles, MOD + "\\floor_%d_{rx}_{ry}.navmesh" % slot)
    for r in res:
        r["versions"] = {k: versions[k] for k in r["tiles"]}
    return res, variants


def build(out):
    files = []
    block_items = []
    for slot in range(1, SLOTS + 1):
        res, variants = slot_resources(slot)
        path = MOD + "\\floor_%d.streamingsector" % slot
        sec, centre, _half = navmod.build_sector("rn_cyberspace_%d" % slot, res, variant_ranges=len(variants))
        data, bufs = sec.segments()
        files.append((path, data, bufs))
        block_items.append((path, centre, variants))
    blk = navmod.build_block(block_items)
    block_path = MOD + "\\cyberspace.streamingblock"
    data, bufs = blk.segments()
    files.append((block_path, data, bufs))
    os.makedirs(out, exist_ok=True)
    name = "RealNetrunning_CyberspaceNavmesh"
    size = rdar.write(os.path.join(out, name + ".archive"), files)
    with open(os.path.join(out, name + ".archive.xl"), "w", newline="\r\n") as fh:
        fh.write("streaming:\n  blocks:\n    - " + block_path + "\n")
    return size


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "out"), "bytes")
