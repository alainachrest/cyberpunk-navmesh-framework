# Cyberpunk navmesh framework: test 1

Can NPCs walk where there's no navmesh? If they can, a navigation framework for
modded and generated areas can be a graph of waypoints instead of real navmesh,
which modders can't make.

The game's own move command, `AIMoveToCommand`, has an `ignoreNavigation`
switch. This test sends an NPC along a route you lay down, twice: once the
normal way (asking the navmesh for a path) and once with `ignoreNavigation` on,
and records what happens on every leg.

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
| fails | reaches, walking | No navmesh needed: a waypoint framework works |
| fails | reaches, sliding | It can be moved but looks wrong: needs more work |
| fails | fails | `ignoreNavigation` isn't enough: next test is splines |
