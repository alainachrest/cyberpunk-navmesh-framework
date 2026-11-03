# Detour harness

Loads navmesh tiles into stock Detour (recastnavigation) set up like the game
(`DT_POLYREF64`, `DT_VERTS_PER_POLYGON = 3`, `DT_NAVMESH_VERSION = 8`) and runs a
path query, to check tiles before they go in game.

    git clone https://github.com/recastnavigation/recastnavigation
    # in Detour/Include/DetourNavMesh.h: define DT_POLYREF64, set the two constants above
    g++ -O1 -o harness harness.cpp recastnavigation/Detour/Source/*.cpp -Irecastnavigation/Detour/Include
    ./harness tiles.bin SX SY SZ EX EY EZ      # tiles.bin: repeated (u32 size, tile bytes)

It paths across the game's own tiles (navigation_3_-28_1_3), and across Real
Netrunning cyberspace mazes built by rn_cyberspace.py: through open doorways,
and not through closed ones.
