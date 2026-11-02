--[[
NavTest: checks for the navmesh framework (is there navmesh here, can an NPC path here)

Lay down a route by walking it and pressing "Add waypoint" at each corner,
spawn a test NPC, then run the tests. The NPC walks the route twice:
  normal      the game's usual movement (asks the navmesh for a path)
  ignore nav  the same command with ignoreNavigation on (walks straight)
Each leg records whether it got there, how far it moved, whether it fell,
and what the command reported. Results go to the overlay window and to
navtest_results.txt in this folder.

Run it once on a street (navmesh: the control) and once somewhere without
navmesh (Real Netrunning's cyberspace, a rooftop). Watch the NPC too: does it
walk with its legs, or slide?
]]

local NavTest = {
	waypoints = {},
	npc = nil,
	record = "Character.CorpoMan",
	records = { "Character.CorpoMan", "Character.CorpoWoman", "Character.VendorMale", "Character.YoungsterFemale" },
	recordIndex = 1,
	run = false,          -- walk or run
	legTimeout = 20,      -- seconds a leg may take
	reachedWithin = 1.5,  -- metres from a waypoint that counts as arrived
	test = nil,           -- the running test
	results = {},         -- lines shown in the window
	overlay = false,
}

local STATES = { [-1] = "none", [0] = "NotExecuting", [1] = "Enqueued", [2] = "Executing", [3] = "Cancelled",
	[4] = "Interrupted", [5] = "Success", [6] = "Failure" }

local function log(text)
	print("[NavTest] " .. text)
	table.insert(NavTest.results, text)
	while #NavTest.results > 200 do table.remove(NavTest.results, 1) end
end

local function try(fn)
	local ok, a = pcall(fn)
	if not ok then log("call failed: " .. tostring(a)) return nil end
	return a
end

local function system()
	return try(function() return Game.GetScriptableSystemsContainer():Get("NavTest.NavTestSystem") end)
end

local function player()
	return try(function()
		local p = Game.GetPlayer()
		local pos = p:GetWorldPosition()
		return { x = pos.x, y = pos.y, z = pos.z, yaw = p:GetWorldYaw() }
	end)
end

local function npcPos()
	if NavTest.npc == nil then return nil end
	return try(function()
		local e = Game.FindEntityByID(NavTest.npc)
		if e == nil then return nil end
		local p = e:GetWorldPosition()
		return { x = p.x, y = p.y, z = p.z }
	end)
end

local function dist(a, b)
	local dx, dy, dz = a.x - b.x, a.y - b.y, (a.z or 0) - (b.z or 0)
	return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function flat(a, b)
	local dx, dy = a.x - b.x, a.y - b.y
	return math.sqrt(dx * dx + dy * dy)
end

local function teleportNPC(pos)
	return try(function()
		local e = Game.FindEntityByID(NavTest.npc)
		if e == nil then return false end
		Game.GetTeleportationFacility():Teleport(e, Vector4.new(pos.x, pos.y, pos.z, 1.0), EulerAngles.new(0, 0, 0))
		return true
	end)
end

---------------------------------------------------------------------------
-- Actions
---------------------------------------------------------------------------

function NavTest.addWaypoint()
	local p = player()
	if p == nil then return end
	local s = system()
	p.navmesh = s and try(function() return s:OnNavmesh(p.x, p.y, p.z, 1.0) end)
	table.insert(NavTest.waypoints, p)
	log(string.format("waypoint %d at %.1f, %.1f, %.1f: %s", #NavTest.waypoints, p.x, p.y, p.z,
		p.navmesh == true and "navmesh here" or (p.navmesh == false and "NO navmesh here" or "navmesh unknown")))
end

-- Marks where V stands as a spot to build test navmesh at. Appends to
-- navtest_spots.txt: x y z yaw navmesh(1/0/?)
function NavTest.markSpot()
	local p = player()
	if p == nil then return end
	local s = system()
	local nav = s and try(function() return s:OnNavmesh(p.x, p.y, p.z, 1.0) end)
	local f = io.open("navtest_spots.txt", "a")
	if f then
		f:write(string.format("%.3f %.3f %.3f %.1f %s\n", p.x, p.y, p.z, p.yaw or 0,
			nav == true and "1" or (nav == false and "0" or "?")))
		f:close()
	end
	log(string.format("spot marked at %.1f, %.1f, %.1f: %s", p.x, p.y, p.z,
		nav == true and "navmesh here" or (nav == false and "NO navmesh here" or "navmesh unknown")))
end

-- Is there navmesh where V stands right now?
function NavTest.checkHere()
	local p = player()
	if p == nil then return end
	local s = system()
	local nav = s and try(function() return s:OnNavmesh(p.x, p.y, p.z, 1.0) end)
	log(string.format("at %.1f, %.1f, %.1f: %s", p.x, p.y, p.z,
		nav == true and "navmesh here" or (nav == false and "NO navmesh here" or "navmesh unknown")))
end

function NavTest.clearWaypoints()
	NavTest.waypoints = {}
	log("waypoints cleared")
end

function NavTest.spawn()
	NavTest.despawn()
	local p = player()
	if p == nil then return end
	-- a couple of metres in front of V
	local yaw = math.rad(p.yaw or 0)
	local x, y = p.x - math.sin(yaw) * 2.5, p.y + math.cos(yaw) * 2.5
	if #NavTest.waypoints > 0 then x, y = NavTest.waypoints[1].x, NavTest.waypoints[1].y end
	local z = (#NavTest.waypoints > 0 and NavTest.waypoints[1].z or p.z) + 0.1
	NavTest.npc = try(function()
		local spec = DynamicEntitySpec.new()
		spec.recordID = NavTest.record
		spec.position = Vector4.new(x, y, z, 1.0)
		spec.orientation = EulerAngles.new(0, 0, 0):ToQuat()
		spec.alwaysSpawned = true
		spec.persistState = false
		spec.persistSpawn = false
		return Game.GetDynamicEntitySystem():CreateEntity(spec)
	end)
	log("spawned " .. NavTest.record .. (NavTest.npc and "" or " (FAILED)"))
end

function NavTest.despawn()
	NavTest.stop("despawned")
	if NavTest.npc then
		try(function() Game.GetDynamicEntitySystem():DeleteEntity(NavTest.npc) end)
		NavTest.npc = nil
	end
end

function NavTest.stop(why)
	if NavTest.test then
		local s = system()
		if s then try(function() s:Cancel() end) end
		log("test stopped" .. (why and (": " .. why) or ""))
		NavTest.test = nil
	end
end

-- mode: "normal" or "ignore"; both = normal then ignore
function NavTest.start(modes)
	if NavTest.npc == nil then log("spawn the NPC first") return end
	if #NavTest.waypoints < 2 then log("add at least two waypoints (walk the route, pressing Add waypoint)") return end
	if system() == nil then log("redscript part not found: is r6/scripts/NavTest installed?") return end
	NavTest.test = { modes = modes, mode = 1, leg = 2, phase = "reset", wait = 0, summary = {} }
	log("---- test started: " .. table.concat(modes, " then ") .. ", " .. #NavTest.waypoints .. " waypoints, " ..
		(NavTest.run and "running" or "walking"))
end

---------------------------------------------------------------------------
-- The test runner
---------------------------------------------------------------------------

local function writeFile()
	local f = io.open("navtest_results.txt", "w")
	if f == nil then return end
	for _, line in ipairs(NavTest.results) do f:write(line, "\n") end
	f:close()
end

local function finishLeg(t, reason)
	local leg = t.current
	local here = npcPos() or leg.last
	local target = NavTest.waypoints[t.leg]
	local reached = here and flat(here, target) <= NavTest.reachedWithin
	local line = string.format("  [%s] leg %d->%d: %s in %.1fs, moved %.1fm, %.1fm from target, lowest drop %.1fm, command %s%s",
		t.modes[t.mode], t.leg - 1, t.leg, reached and "REACHED" or "did not reach", leg.time, leg.moved,
		here and flat(here, target) or -1, leg.drop, STATES[leg.state] or tostring(leg.state), reason and (" (" .. reason .. ")") or "")
	log(line)
	table.insert(t.summary, { mode = t.modes[t.mode], reached = reached, moved = leg.moved, drop = leg.drop, state = leg.state })
	t.current = nil
	t.leg = t.leg + 1
	if t.leg > #NavTest.waypoints then
		t.mode = t.mode + 1
		t.leg = 2
		t.phase = "reset"
	else
		t.phase = "send"
	end
end

local function summarise(t)
	log("---- summary")
	local on, off = 0, 0
	for _, w in ipairs(NavTest.waypoints) do
		if w.navmesh == true then on = on + 1 elseif w.navmesh == false then off = off + 1 end
	end
	log(string.format("  route: %d waypoints on navmesh, %d with none", on, off))
	for _, mode in ipairs(t.modes) do
		local legs, reached, moved, fell = 0, 0, 0, false
		for _, s in ipairs(t.summary) do
			if s.mode == mode then
				legs = legs + 1
				if s.reached then reached = reached + 1 end
				moved = moved + s.moved
				if s.drop > 2 then fell = true end
			end
		end
		log(string.format("  %s: reached %d of %d legs, walked %.1fm in total%s", mode, reached, legs, moved,
			fell and ", FELL more than 2m at some point" or ""))
	end
	log("  Did it walk with its legs, or slide? Write that down too.")
	writeFile()
end

local function update(dt)
	local t = NavTest.test
	if t == nil then return end
	if t.mode > #t.modes then
		summarise(t)
		NavTest.test = nil
		return
	end
	if t.wait > 0 then t.wait = t.wait - dt return end

	if t.phase == "reset" then
		-- back to the first waypoint before each mode
		teleportNPC(NavTest.waypoints[1])
		log("[" .. t.modes[t.mode] .. "] starting from waypoint 1")
		t.phase, t.wait = "send", 2.0
		return
	end

	if t.phase == "send" then
		local target = NavTest.waypoints[t.leg]
		local s = system()
		local ok = s and try(function()
			return s:MoveTo(NavTest.npc, target.x, target.y, target.z, t.modes[t.mode] == "ignore", NavTest.run)
		end)
		local here = npcPos()
		t.current = { time = 0, moved = 0, drop = 0, state = -1, last = here, startZ = here and here.z or target.z, sample = 0 }
		if not ok then
			finishLeg(t, "the NPC wouldn't take the command")
			return
		end
		t.phase = "moving"
		return
	end

	if t.phase == "moving" then
		local leg = t.current
		leg.time = leg.time + dt
		leg.sample = leg.sample + dt
		if leg.sample < 0.25 then return end
		leg.sample = 0
		local here = npcPos()
		if here == nil then finishLeg(t, "the NPC is gone") return end
		if leg.last then leg.moved = leg.moved + dist(here, leg.last) end
		leg.last = here
		leg.drop = math.max(leg.drop, (leg.startZ or here.z) - here.z)
		local s = system()
		leg.state = s and try(function() return s:LastState() end) or -1
		local target = NavTest.waypoints[t.leg]
		if flat(here, target) <= NavTest.reachedWithin and leg.state ~= 2 then finishLeg(t) return end
		if leg.state == 5 or leg.state == 6 or leg.state == 3 or leg.state == 4 then finishLeg(t) return end
		if leg.drop > 10 then finishLeg(t, "fell through") return end
		if leg.time >= NavTest.legTimeout then
			if s then try(function() s:Cancel() end) end
			finishLeg(t, "timed out")
		end
	end
end

---------------------------------------------------------------------------
-- CET
---------------------------------------------------------------------------

registerForEvent("onInit", function() log("ready. Open the CET overlay for the NavTest window.") end)
registerForEvent("onUpdate", function(dt) update(dt) end)
registerForEvent("onOverlayOpen", function() NavTest.overlay = true end)
registerForEvent("onOverlayClose", function() NavTest.overlay = false end)

registerHotkey("navtest_spot", "Mark navmesh test spot", function() NavTest.markSpot() end)
registerHotkey("navtest_check", "Check for navmesh here", function() NavTest.checkHere() end)
registerHotkey("navtest_waypoint", "Add waypoint (your position)", function() NavTest.addWaypoint() end)
registerHotkey("navtest_spawn", "Spawn test NPC", function() NavTest.spawn() end)
registerHotkey("navtest_both", "Run both tests", function() NavTest.start({ "normal", "ignore" }) end)
registerHotkey("navtest_stop", "Stop test", function() NavTest.stop("by hand") end)

registerForEvent("onDraw", function()
	if not NavTest.overlay then return end
	if ImGui.Begin("NavTest") then
		ImGui.Text("Waypoints: " .. #NavTest.waypoints .. "    NPC: " .. (NavTest.npc and "spawned" or "none") ..
			"    Test: " .. (NavTest.test and "running" or "idle"))
		if ImGui.Button("Check for navmesh here") then NavTest.checkHere() end
		ImGui.SameLine()
		if ImGui.Button("Mark navmesh test spot") then NavTest.markSpot() end
		ImGui.Separator()
		if ImGui.Button("Add waypoint (where V stands)") then NavTest.addWaypoint() end
		ImGui.SameLine()
		if ImGui.Button("Clear waypoints") then NavTest.clearWaypoints() end
		if ImGui.Button("NPC: " .. NavTest.record) then
			NavTest.recordIndex = NavTest.recordIndex % #NavTest.records + 1
			NavTest.record = NavTest.records[NavTest.recordIndex]
		end
		ImGui.SameLine()
		if ImGui.Button("Spawn test NPC") then NavTest.spawn() end
		ImGui.SameLine()
		if ImGui.Button("Despawn") then NavTest.despawn() end
		NavTest.run = ImGui.Checkbox("Run instead of walk", NavTest.run)
		if ImGui.Button("Run both tests") then NavTest.start({ "normal", "ignore" }) end
		ImGui.SameLine()
		if ImGui.Button("Normal only") then NavTest.start({ "normal" }) end
		ImGui.SameLine()
		if ImGui.Button("Ignore navigation only") then NavTest.start({ "ignore" }) end
		ImGui.SameLine()
		if ImGui.Button("Stop") then NavTest.stop("by hand") end
		ImGui.Separator()
		ImGui.BeginChild("results", 0, 260, true)
		for _, line in ipairs(NavTest.results) do ImGui.TextWrapped(line) end
		ImGui.EndChild()
	end
	ImGui.End()
end)

return NavTest
