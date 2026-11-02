"""Builds the navmesh loading tests: a flat square of navmesh at a spot.

  python make_test.py layer X Y Z [--size 16] [--out DIR]
      New navigation sector added through an ArchiveXL streaming block, tiles
      on Detour layer 1 (so they don't clash with the game's layer-0 tiles).

  python make_test.py merge X Y Z --sector SEGS [--size 16] [--out DIR]
      Overrides the game's navigation sector that holds the tile under the
      spot, with our square merged into the existing tile.
      SEGS: the sector's segments as dumped from the game archive, each
      decompressed (see kark): a directory of seg_000.bin, seg_001.bin...

X Y Z are game world coordinates (z up), e.g. from NavTest's navtest_spots.txt.
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cr2w      # noqa: E402
import detour    # noqa: E402
import navmod    # noqa: E402
import rdar      # noqa: E402

MOD_DIR = "mod\\navmesh_framework_test"


def square(x, y, z, size, layer, agent=detour.HUMAN):
    h = size / 2
    return detour.flat_tiles(x - h, y - h, x + h, y + h, z, agent=agent, layer=layer)


def make_layer(x, y, z, size, out):
    sector_path = MOD_DIR + "\\navmesh_test.streamingsector"
    block_path = MOD_DIR + "\\navmesh_test.streamingblock"
    res_path = MOD_DIR + "\\navmesh_test_0.navmesh"
    tiles = square(x, y, z, size, layer=1)
    sec, centre, half = navmod.build_sector("navmesh_test", [dict(path=res_path, agent="Human", tiles=tiles)])
    blk = navmod.build_block([(sector_path, centre)])
    files = []
    for path, f in ((sector_path, sec), (block_path, blk)):
        data, bufs = f.segments()
        files.append((path, data, bufs))
    os.makedirs(out, exist_ok=True)
    name = "NavmeshFrameworkTest_Layer"
    rdar.write(os.path.join(out, name + ".archive"), files)
    with open(os.path.join(out, name + ".archive.xl"), "w", newline="\r\n") as fh:
        fh.write("streaming:\n  blocks:\n    - " + block_path + "\n")
    # loose copies for inspecting in WolvenKit
    for path, f in ((sector_path, sec), (block_path, blk)):
        p = os.path.join(out, "raw", *path.split("\\"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(f.write())
    return sorted(tiles), centre


def load_sector(segdir):
    segs = sorted(glob.glob(os.path.join(segdir, "seg_*.bin")))
    data = open(segs[0], "rb").read()
    return cr2w.File.read(data, [open(s, "rb").read() for s in segs[1:]])


def make_merge(x, y, z, size, segdir, sector_path, out):
    f = load_sector(segdir)
    adds = square(x, y, z, size, layer=0)
    done = []
    for o_i, o in enumerate(f.exports):
        if o.cls != "worldNavigationTileResource":
            continue
        agent = o.get("agentSize")
        if agent and f.names[cr2w.u16(agent.raw)] != "Human":
            continue
        rows_raw = o.get("tilesData").raw
        n = cr2w.u32(rows_raw[:4])
        p = 4
        rows = []
        for _ in range(n):
            s, p = f.parse_struct(rows_raw, p)
            rows.append({q.name: cr2w.i32(q.raw) for q in s.props})
        refs_raw = o.get("tileBuffers").raw
        refs = [cr2w.u32(refs_raw[4 + 4 * i:8 + 4 * i]) for i in range(cr2w.u32(refs_raw[:4]))]
        for row in rows:
            key = (row.get("tileX", 0), row.get("tileY", 0))
            if key in adds:
                bi = (refs[row.get("bufferIndex", 0)] & 0x7FFFFFFF) - 1
                base = detour.read_tile(f.buffer_data(bi))
                merged = navmod.merge_tile(base, adds[key])
                f.set_buffer(bi, detour.write_tile(merged))
                done.append(key)
    missing = [k for k in adds if k not in done]
    if missing:
        raise SystemExit("tiles not in this sector: %s" % missing)
    data, bufs = f.segments()
    os.makedirs(out, exist_ok=True)
    rdar.write(os.path.join(out, "NavmeshFrameworkTest_Merge.archive"), [(sector_path, data, bufs)])
    p = os.path.join(out, "raw", *sector_path.split("\\"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(f.write())
    return sorted(done)


def resource_for(x, y):
    """The game's resource (5x5 tiles) holding the tile under (x, y)."""
    tx, ty = int(x // detour.TILE_SIZE), int(y // detour.TILE_SIZE)
    return tx // 5, ty // 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["layer", "merge"])
    ap.add_argument("x", type=float)
    ap.add_argument("y", type=float)
    ap.add_argument("z", type=float)
    ap.add_argument("--size", type=float, default=16.0)
    ap.add_argument("--sector", help="merge: directory of the sector's decompressed segments")
    ap.add_argument("--sector-path", help="merge: the sector's depot path")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if a.mode == "layer":
        tiles, centre = make_layer(a.x, a.y, a.z, a.size, a.out)
        print("layer test: tiles", tiles, "node at", centre)
    else:
        print("merged tiles", make_merge(a.x, a.y, a.z, a.size, a.sector, a.sector_path, a.out))


if __name__ == "__main__":
    main()
