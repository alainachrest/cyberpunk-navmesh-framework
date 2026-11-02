# Tools

Python 3, no dependencies. Everything is written in the game's own formats.

| File | What it does |
|---|---|
| `cr2w.py` | Reads and writes CR2W resources (sectors, streaming blocks). Round-trips the game's navigation sectors byte for byte, apart from buffer compression. |
| `detour.py` | Reads and writes navmesh tiles (Detour `dtMeshTile` data); builds BV trees and link counts the way the game's baker did, and makes flat tiles. |
| `navmod.py` | Builds a new navigation sector + streaming block, or merges polygons into one of the game's tiles. |
| `rdar.py` | Reads and writes `.archive` files (stored uncompressed). |
| `make_test.py` | Builds the two loading tests for a spot. |
| `kark/` | Small Rust tool that decompresses the game's Kraken-compressed archive segments (uses the `oozextract` crate). |

## Loading tests

Both put a flat square of navmesh (16 m by default) at a spot where there is none:

- `python make_test.py layer X Y Z` - a **new** navigation sector, added with an
  ArchiveXL streaming block. Its tiles are on Detour layer 1, because the game
  already has a layer-0 tile at nearly every spot. If this works, mods can add
  navmesh without touching the game's own.
- `python make_test.py merge X Y Z --sector DIR --sector-path PATH` - overrides
  the game's navigation sector that holds the tile there, with the square merged
  into the existing tile. Works whatever the game thinks of layers, but only one
  mod can own a tile this way.

Check with NavTest's **Check for navmesh here** standing on the square.

Real Netrunning's cyberspace (8 floors, 18 m apart, around its origin):

    python make_test.py layer -1085 880 9000 --size 192 --floors 8 --gap 18

Tiles are grouped into the game's 5 x 5 tile resources, one node each, and
stacked floors share tiles (as the game's multi-level areas do).
