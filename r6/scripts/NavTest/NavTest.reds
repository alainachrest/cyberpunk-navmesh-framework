// -----------------------------------------------------------------------------
// NavTest - checks for the navmesh framework
// -----------------------------------------------------------------------------
//
// The framework adds real navmesh to custom areas. This checks, in game,
// whether the game finds navmesh at a point and whether an NPC can path there
// (AIMoveToCommand the normal way), so an area can be tested before and after
// our navmesh is added. A second mode with `ignoreNavigation` on is kept for
// comparison.
//
// The CET side (bin/x64/plugins/cyber_engine_tweaks/mods/navtest) runs the
// tests and asks this system to send the commands and report their state.

module NavTest

public class NavTestSystem extends ScriptableSystem {
    private let m_command: ref<AIMoveToCommand>;
    private let m_npc: wref<ScriptedPuppet>;
    private let m_obstacles: array<ref<NavigationObstacle>>;

    public static func Get() -> ref<NavTestSystem> {
        return GameInstance.GetScriptableSystemsContainer(GetGameInstance())
            .Get(n"NavTest.NavTestSystem") as NavTestSystem;
    }

    // Tells the NPC to walk (or run) to a point. ignoreNav: walk straight there
    // without asking the navmesh for a path. Returns false if the NPC can't take commands.
    public func MoveTo(id: EntityID, x: Float, y: Float, z: Float, ignoreNav: Bool, run: Bool) -> Bool {
        let puppet = GameInstance.FindEntityByID(GetGameInstance(), id) as ScriptedPuppet;
        if !IsDefined(puppet) {
            return false;
        }
        let ai = puppet.GetAIControllerComponent();
        if !IsDefined(ai) {
            return false;
        }
        if IsDefined(this.m_command) && IsDefined(this.m_npc) {
            this.m_npc.GetAIControllerComponent().CancelCommand(this.m_command);
        }

        let cmd = new AIMoveToCommand();
        let target: WorldPosition;
        WorldPosition.SetVector4(target, Vector4(x, y, z, 1.0));
        let spec: AIPositionSpec;
        AIPositionSpec.SetWorldPosition(spec, target);
        cmd.movementTarget = spec;
        cmd.movementType = run ? moveMovementType.Run : moveMovementType.Walk;
        cmd.ignoreNavigation = ignoreNav;
        cmd.useStart = true;
        cmd.useStop = true;
        cmd.desiredDistanceFromTarget = 0.5;
        cmd.finishWhenDestinationReached = true;
        cmd.ignoreInCombat = true;

        this.m_command = cmd;
        this.m_npc = puppet;
        return ai.SendCommand(cmd);
    }

    // The last command's state: 0 NotExecuting, 1 Enqueued, 2 Executing,
    // 3 Cancelled, 4 Interrupted, 5 Success, 6 Failure; -1 if there's no command.
    public func LastState() -> Int32 {
        if !IsDefined(this.m_command) || !IsDefined(this.m_npc) {
            return -1;
        }
        let ai = this.m_npc.GetAIControllerComponent();
        if !IsDefined(ai) {
            return -1;
        }
        return EnumInt(ai.GetCommandState(this.m_command));
    }

    // Is there navmesh at this point (within `tolerance` metres)? Asked of the
    // game's own navigation system, for V's size.
    public func OnNavmesh(x: Float, y: Float, z: Float, tolerance: Float) -> Bool {
        let player = GameInstance.GetPlayerSystem(GetGameInstance()).GetLocalPlayerControlledGameObject();
        let nav = GameInstance.GetAINavigationSystem(GetGameInstance());
        if !IsDefined(nav) || !IsDefined(player) {
            return false;
        }
        return nav.IsPointOnNavmesh(player, Vector4(x, y, z, 1.0), tolerance);
    }

    // Puts a navigation obstacle (an upright cylinder) at a point, for human-sized
    // NPCs. Returns how many obstacles there are now, or -1 if it failed.
    public func AddObstacle(x: Float, y: Float, z: Float, radius: Float, height: Float) -> Int32 {
        let nav = GameInstance.GetAINavigationSystem(GetGameInstance());
        if !IsDefined(nav) {
            return -1;
        }
        let o = nav.AddObstacle(Vector4(x, y, z, 1.0), radius, height, NavGenAgentSize.Human);
        if !IsDefined(o) {
            return -1;
        }
        ArrayPush(this.m_obstacles, o);
        return ArraySize(this.m_obstacles);
    }

    public func ClearObstacles() -> Int32 {
        let nav = GameInstance.GetAINavigationSystem(GetGameInstance());
        let n = ArraySize(this.m_obstacles);
        if IsDefined(nav) {
            for o in this.m_obstacles {
                nav.RemoveObstacle(o);
            }
        }
        ArrayClear(this.m_obstacles);
        return n;
    }

    public func Cancel() {
        if IsDefined(this.m_command) && IsDefined(this.m_npc) {
            this.m_npc.GetAIControllerComponent().CancelCommand(this.m_command);
        }
        this.m_command = null;
    }
}
