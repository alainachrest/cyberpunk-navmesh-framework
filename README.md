# Cyberpunk navmesh framework

A framework that lets modders add real navmesh to custom areas, so NPCs can
path around them like they do in the rest of Night City.

The game's navmesh is Recast/Detour tiles (see [docs/navmesh-format.md](docs/navmesh-format.md)),
so the plan is: build tiles for a custom area with Recast, using the game's
settings, package them as `.navmesh` resources with navigation sectors, and have
the game load them.

## Test 1: the checking tool

NavTest is the in-game check for all of that. It records, at points you choose,
whether the game finds navmesh there, and sends an NPC along a route the normal
way (asking the navmesh for a path). Run it on a custom area before and after
adding navmesh: before, the points say "NO navmesh" and the normal walk fails;
once our navmesh loads, both should change.

It also does a second run with `AIMoveToCommand`'s `ignoreNavigation` switch on,
for comparison: what NPCs do in an area that has no navmesh yet.

## Install

Copy `bin` and `r6` into the game folder, or install the zip with Vortex.
Needs Cyber Engine Tweaks and redscript.

## Running it

Do it twice: once on a street (there is navmesh there, so this is the control)
and once somewhere with **no** navmesh. Real Netrunning's cyberspace is ideal
(jack in from your home computer, where nothing attacks you); a rooftop V can
reach also works.

1. Open the CET overlay. The **NavTest** window is there.
2. Walk the route, pressing **Add waypoint** at each corner (at least 2, 4 or 5
   is better). Keep the route on solid ground with no walls in the way.
3. **Spawn test NPC**. It appears at the first waypoint.
4. **Run both tests**, close the overlay, and watch.

Hotkeys can be bound in CET for adding waypoints, spawning, running and stopping.

## What to report

Each waypoint you add says whether the game finds navmesh under it, so you
can tell the no-navmesh run really had none. The window shows each leg, then a summary, and the same text is written to
`bin/x64/plugins/cyber_engine_tweaks/mods/navtest/navtest_results.txt`. Send
that file for each place you tested, plus what you saw:

- Did the NPC **walk with its legs**, or slide / glide?
- Did it go **straight** between waypoints, or wander off?
- Did it **fall** or sink into the floor?
- Did it stop at walls, or walk through them?

## What the results mean

| Normal | Ignore navigation | Meaning |
| --- | --- | --- |
| reaches | reaches | Both work there (expected on a street) |
| fails | either | No navmesh there yet (expected before we add ours) |

After adding our own navmesh to an area, the waypoints there should say
"navmesh here" and the normal run should reach every one.

## Results

**2 Nov 2026, loading test (new sector, layer 1) in Real Netrunning's cyberspace: works.**
Our own navigation sector, added through an ArchiveXL streaming block with
tiles on Detour layer 1, loaded. NavTest found navmesh at every point on floor 1
(z 9000), and a spawned NPC walked a 6-point route the normal way (pathing on
the navmesh, walking animation), reaching 5 of 5 legs with every command
reporting Success.

So mods can add navmesh without overriding the game's own sectors: their own
sector, their own tiles, on a layer above 0.

**3 Nov 2026, switching navmesh while playing: works through world variants.**
- Navigation obstacles (`NavigationSystem.AddObstacle`) don't change NPC paths,
  on our navmesh or the game's (tested on a street: the NPC walked straight
  through).
- Codeware's `WorldStateSystem.ToggleNode` on our navigation nodes didn't
  unload their navmesh.
- **World variants do.** The game stores some tiles in several versions keyed
  by world variant IDs (`activeVariantIDs` / `allVariantIDs` in `tilesData`;
  47 of its 3,846 navigation sectors do this, for quest states). We gave every
  test tile a second version 10 m lower, registered a variant on our streaming
  block, and switched it with `WorldStateSystem.ToggleVariant`: navmesh here ->
  variant on -> NO navmesh here -> variant off -> navmesh here.

So navmesh can change at runtime, as long as every state it can be in is built
in advance as a tile version.
