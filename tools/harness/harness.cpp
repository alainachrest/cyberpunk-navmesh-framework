// Loads tiles (file: repeated u32 size + tile bytes) and finds a path.
// harness tiles.bin sx sy sz ex ey ez   (game coords: x, y, z up)
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "DetourCommon.h"
#include "DetourAlloc.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
int main(int argc, char** argv) {
    FILE* f = fopen(argv[1], "rb");
    dtNavMesh* nav = dtAllocNavMesh();
    dtNavMeshParams p; memset(&p, 0, sizeof p);
    p.tileWidth = p.tileHeight = 32.4f; p.maxTiles = 1 << 16; p.maxPolys = 1 << 16;
    if (dtStatusFailed(nav->init(&p))) { printf("init failed\n"); return 1; }
    unsigned int size; int n = 0;
    while (fread(&size, 4, 1, f) == 1) {
        unsigned char* d = (unsigned char*)dtAlloc(size, DT_ALLOC_PERM);
        fread(d, 1, size, f);
        dtStatus s = nav->addTile(d, size, DT_TILE_FREE_DATA, 0, 0);
        if (dtStatusFailed(s)) { printf("addTile %d failed %x\n", n, s); return 1; }
        n++;
    }
    printf("tiles %d\n", n);
    dtNavMeshQuery* q = dtAllocNavMeshQuery(); q->init(nav, 4096);
    dtQueryFilter filter;
    float s[3] = { (float)atof(argv[2]), (float)atof(argv[4]), (float)atof(argv[3]) };
    float e[3] = { (float)atof(argv[5]), (float)atof(argv[7]), (float)atof(argv[6]) };
    float ext[3] = { 1, 2, 1 };
    dtPolyRef sr, er; float sp[3], ep[3];
    q->findNearestPoly(s, ext, &filter, &sr, sp); q->findNearestPoly(e, ext, &filter, &er, ep);
    printf("start poly %s end poly %s\n", sr ? "found" : "NONE", er ? "found" : "NONE");
    if (!sr || !er) return 0;
    dtPolyRef path[512]; int np = 0;
    dtStatus st = q->findPath(sr, er, sp, ep, &filter, path, &np, 512);
    float straight[512 * 3]; int ns = 0;
    q->findStraightPath(sp, ep, path, np, straight, 0, 0, &ns, 512);
    float last[3]; dtVcopy(last, &straight[(ns - 1) * 3]);
    bool reached = dtVdist(last, ep) < 0.1f;
    printf("path polys %d, %s, corners:", np, reached ? "REACHES the end" : (dtStatusDetail(st, DT_PARTIAL_RESULT) ? "PARTIAL (can't reach)" : "does not reach"));
    for (int i = 0; i < ns; i++) printf(" (%.1f,%.1f)", straight[i * 3], straight[i * 3 + 2]);
    printf("\n");
}
