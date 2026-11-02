// -----------------------------------------------------------------------------
// NavTest - can NPCs walk where there's no navmesh?
// -----------------------------------------------------------------------------
//
// The game's own move command, AIMoveToCommand, has an `ignoreNavigation`
// switch. If an NPC told to walk with it on gets there on foot (with its walking
// animation) across ground that has no navmesh, a navigation framework for
// modded areas can be a graph of waypoints: no navmesh needed.
//
// The CET side (bin/x64/plugins/cyber_engine_tweaks/mods/navtest) runs the
// tests and asks this system to send the commands and report their state.

module NavTest

public class NavTestSystem extends ScriptableSystem {
    private let m_command: ref<AIMoveToCommand>;
    private let m_npc: wref<ScriptedPuppet>;

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
        AIPositionSpec.SetWorldPosition(cmd.movementTarget, target);
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

    public func Cancel() {
        if IsDefined(this.m_command) && IsDefined(this.m_npc) {
            this.m_npc.GetAIControllerComponent().CancelCommand(this.m_command);
        }
        this.m_command = null;
    }
}
