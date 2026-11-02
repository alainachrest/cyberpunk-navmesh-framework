# Cyberpunk 2077's navmesh format (patch 2.5)

Findings from inspecting `navigation_3_-28_1_3.streamingsector` in WolvenKit 9.1.0,
checked against WolvenKit's own reader (`WolvenKit.RED4/Archive/IO/TilesReader.cs`,
`Archive/Buffer/TilesStruct.cs`).

**Summary: each navmesh tile is a Recast/Detour `dtMeshTile` blob**, built with
triangles only (`DT_VERTS_PER_POLYGON = 3`) and 64-bit poly refs. The only
difference from stock Detour found so far is the off-mesh connection record (40
bytes instead of 36).

## How the pieces fit

```
navigation_<x>_<y>_<z>_<lvl>.streamingsector       (sector, streamed with the world)
  nodes[] worldNavigationNode
    navigationTileResource -> base\worlds\03_night_city\sectors\_generated\navigation\resources\navigation_<x>_<y>_<n>.navmesh

<name>.navmesh  (worldNavigationTileResource)
  agentSize          Human (one resource per agent size)
  localBoundingBox   -81..81 x -81..81 x about -22..22   (162 m square)
  tilesData[25]      worldNavigationTileData: tileX, tileY, tileIndex, bufferIndex,
                     agentSize, tileRef (int64 max = unset), offMeshConnections,
                     activeVariantIDs, allVariantIDs
  tileBuffers[25]    DataBuffer, one Detour tile each
```

- Tiles are 32.4 m on a fixed world grid: tile min x = tileX * 32.4, min y = tileY * 32.4.
- A resource is a 5x5 block of tiles: node `navNode_5_-44` -> world 810, -7128 (5 * 162, -44 * 162).
- Detour is Y-up, so vectors in the buffer are (x, height, y) in game terms.

## Tile buffer layout (little-endian)

| Order | WolvenKit name | Detour | Size each |
|---|---|---|---|
| header | `TilesBufferHeader` (60 bytes) | `dtMeshHeader` part 1 | |
| | `vand` | `magic` 'DNAV' | u32 |
| | `uk1` | `version` | u32 |
| | `tileX`, `tileY` | `x`, `y` | u32 each |
| | `uk2` | `layer` | u32 |
| | `uk3` | `userId` | u32 |
| | `count1` | `polyCount` | u32 |
| | `count2` | `vertCount` | u32 |
| | `count3` | `maxLinkCount` | u32 |
| | `count4` | `detailMeshCount` | u32 |
| | `count5` | `detailVertCount` | u32 |
| | `count6` | `detailTriCount` | u32 |
| | `count7` | `bvNodeCount` | u32 |
| | `count8` | `offMeshConCount` | u32 |
| | `uk4` | `offMeshBase` | u32 |
| | `Uk1` (1.8, 0.3, 0.6) | `walkableHeight`, `walkableRadius`, `walkableClimb` | 3 x f32 |
| | `Min`, `Max` | `bmin`, `bmax` | 3 x f32 each |
| | `Uk2` (10) | `bvQuantFactor` = 1 / cell size, so cell size 0.1 m | f32 |
| 1 | `Vertices` | `verts` | 12 |
| 2 | `FaceInfo` | `dtPoly`: `firstLink` u32 (`Zero`), `verts[3]` u16 (`Indices`), `neis[3]` u16 (`ConnectedFaces`), `flags` u16 (`Three`), `vertCount` u8 (`NumIndices`), `areaAndtype` u8 (`Bits`) | 20 |
| 3 | `Zeros` | `dtLink` (empty in the file, filled at load) | 16 |
| 4 | `Indices` | `dtPolyDetail`: `vertBase` u32, `triBase` u32 (`Index`), `vertCount` u8 + `triCount` u8 + pad (`Uk2`, 256 = 0 verts, 1 tri) | 12 |
| 5 | `Uk3` | `detailVerts` | 12 |
| 6 | `Flags` | `detailTris`: v0, v1, v2, edge flags as 4 bytes (352452864 = 00 01 02 15) | 4 |
| 7 | `Info` | `dtBVNode`: `bmin[3]`, `bmax[3]` u16 (WolvenKit splits each into two signed bytes), `i` i32 (negative = escape) | 16 |
| 8 | `Uk4` | `dtOffMeshConnection`: `pos[6]` f32, `rad` f32, then 3 x u32 (stock Detour has poly u16, flags u8, side u8, userId u32: **4 bytes fewer**) | 40 |

### Neighbours (`neis`)

As in Detour: 0 = wall; n = internal neighbour face n-1; with bit 0x8000 set
(WolvenKit's `Bit`) the edge is a portal to the next tile and the low bits are
the side (0 = +x, 2 = +y, 4 = -x, 6 = -y). Example, tile 0 face 0:
edges `2/True` (portal, +y side), `0/True` (portal, +x side), `2/False` (face 1).

### Worked example: resource `navigation_5_-44_0`, tile 0

- 4 verts: (810, 293.6, -7095.6), (842.4, 296.9, -7095.6), (842.4, 284.6, -7128), (810, 284, -7128),
  one sloped square over the whole tile, split into 2 triangles.
- BV nodes `i`: -3 (root, escape 3), 1, 0; 4 slots reserved (2 per face, Detour's default).
- BV root bounds dequantised: bmin (0, 150, 0), bmax (324, 279, 324) in 0.1 m cells.

## What this means for custom navmesh

- Recast (Detour's builder) can generate these tiles from geometry with the game's
  settings: agent 1.8 / 0.3 / 0.6, cell size 0.1, 32.4 m tiles, 3 verts per poly,
  64-bit refs. Then patch the off-mesh record to 40 bytes.
- WolvenKit 9.1.0 has a **reader** for these buffers but no writer registered, so a
  tool would write the tile bytes itself and wrap them in a `.navmesh` resource.

## Open questions

1. The extra 4 bytes in off-mesh connections, and what `tilesData.offMeshConnections` holds.
2. What `version` (`uk1`) and `userId` (`uk3`) are in shipped tiles.
3. `flags` (3) and `areaAndtype` (1) meanings: area ids and walk flags CDPR uses.
4. Whether the game loads an extra navigation sector + resource added by ArchiveXL,
   and whether tiles must line up with neighbours (portals) or can stand alone.
5. The second agent size resource (`_1`) per node.
