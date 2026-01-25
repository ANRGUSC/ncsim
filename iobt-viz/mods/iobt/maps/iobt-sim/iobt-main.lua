--[[
   IoBT Main Visualization Script

   This script implements:
   - Time-waypoint interpolation for unit movement
   - Building placement
   - Position recording and export
   - (Future) Network link visualization

   The script uses pathfinding for natural movement between waypoints.
]]

-- State tracking
IoBTState = {
    units = {},
    buildings = {},
    initialized = false
}

-- Position log for export
PositionLog = {}

-- Linear interpolation helper
function Lerp(a, b, t)
    return a + (b - a) * t
end

-- Get interpolated target position for a unit at current game time
-- Returns nil if the unit shouldn't exist yet (before first waypoint)
function GetInterpolatedPosition(waypoints, currentTime)
    -- Not yet at first waypoint
    if currentTime < waypoints[1].time then
        return nil
    end

    -- Find the waypoint segment we're in
    for i = 1, #waypoints - 1 do
        local wp1 = waypoints[i]
        local wp2 = waypoints[i + 1]

        if currentTime >= wp1.time and currentTime < wp2.time then
            -- Interpolate between waypoints
            local duration = wp2.time - wp1.time
            local elapsed = currentTime - wp1.time
            local t = elapsed / duration

            local x = math.floor(Lerp(wp1.x, wp2.x, t) + 0.5)
            local y = math.floor(Lerp(wp1.y, wp2.y, t) + 0.5)

            return CPos.New(x, y)
        end
    end

    -- Past the last waypoint - stay at final position
    local lastWp = waypoints[#waypoints]
    return CPos.New(lastWp.x, lastWp.y)
end

-- Record current positions of all tracked units
function RecordPositions(currentTime)
    for id, state in pairs(IoBTState.units) do
        if state.actor and not state.actor.IsDead then
            local pos = state.actor.Location
            table.insert(PositionLog, {
                time = currentTime,
                unit = id,
                x = pos.X,
                y = pos.Y
            })
        end
    end
end

-- Export recorded positions as CSV to console
function ExportLog()
    print("=== IOBT POSITION LOG START ===")
    print("time,unit,x,y")
    for _, entry in ipairs(PositionLog) do
        print(entry.time .. "," .. entry.unit .. "," .. entry.x .. "," .. entry.y)
    end
    print("=== IOBT POSITION LOG END ===")
    print("Total entries: " .. #PositionLog)
end

-- DAG Demo state
DagDemo = {
    enabled = true,  -- Set to false to disable DAG demo
    started = false
}

-- Simple 3-task DAG demo
-- DAG structure: T0 (Load) -> T1 (Process) -> T2 (Output)
function StartDagDemo()
    if not DagDemo.enabled or DagDemo.started then return end

    local nodeCount = Blue.GetComputeNodeCount()
    print("IoBT DAG: Found " .. nodeCount .. " compute nodes")

    if nodeCount < 3 then
        print("IoBT DAG: Need at least 3 compute nodes for demo, have " .. nodeCount)
        return
    end

    DagDemo.started = true
    print("IoBT DAG: Starting 3-task DAG demo...")

    -- Define the DAG tasks
    Blue.AddDagTask("T0", "Load Data", "")
    Blue.AddDagTask("T1", "Process", "T0")
    Blue.AddDagTask("T2", "Output", "T1")

    -- Phase 1: Start T0 on node C0
    Trigger.AfterDelay(25, function()
        print("IoBT DAG: Assigning T0 to C0")
        Blue.AssignTask("T0", 0)
    end)

    -- Phase 2: T0 completes, data transfer to T1 on C1
    Trigger.AfterDelay(100, function()
        print("IoBT DAG: T0 complete, transferring data to T1")
        Blue.CompleteTask("T0")
        Blue.AssignTask("T1", 1)  -- Assign T1 first so transfer knows the destination
        Blue.AddTaskTransfer("T0", "T1", "data")  -- Shows "T0→T1" in status panel
    end)

    Trigger.AfterDelay(125, function()
        print("IoBT DAG: Transfer complete, T1 running on C1")
        Blue.ClearActiveLinks()
    end)

    -- Phase 3: T1 completes, data transfer to T2 on C2
    Trigger.AfterDelay(200, function()
        print("IoBT DAG: T1 complete, transferring data to T2")
        Blue.CompleteTask("T1")
        Blue.AssignTask("T2", 2)  -- Assign T2 first so transfer knows the destination
        Blue.AddTaskTransfer("T1", "T2", "result")  -- Shows "T1→T2" in status panel
    end)

    Trigger.AfterDelay(225, function()
        print("IoBT DAG: Transfer complete, T2 running on C2")
        Blue.ClearActiveLinks()
    end)

    -- Phase 4: T2 completes, DAG done
    Trigger.AfterDelay(300, function()
        print("IoBT DAG: T2 complete - DAG execution finished!")
        Blue.CompleteTask("T2")
    end)

    -- Restart the demo after a pause
    Trigger.AfterDelay(400, function()
        print("IoBT DAG: Restarting demo...")
        Blue.ClearDag()
        DagDemo.started = false
    end)
end

-- Called once when the map loads
function WorldLoaded()
    -- Get the Blue player
    Blue = Player.GetPlayer("Blue")

    if not Blue then
        print("ERROR: Blue player not found!")
        return
    end

    print("IoBT: Initializing simulation...")
    print("IoBT: Export enabled = " .. tostring(IoBTConfig.export.enabled))
    print("IoBT: Sample interval = " .. IoBTConfig.export.sampleInterval .. " ticks")
    print("IoBT: Stop after = " .. IoBTConfig.export.stopAfterTicks .. " ticks")
    print("IoBT: Press 'N' in chat to toggle network overlay (type: n)")

    -- Spawn buildings
    for _, bldg in ipairs(IoBTConfig.buildings) do
        local owner = Player.GetPlayer(bldg.owner)
        if owner then
            local actor = Actor.Create(bldg.type, true, {
                Owner = owner,
                Location = CPos.New(bldg.x, bldg.y)
            })
            IoBTState.buildings[bldg.id] = {
                actor = actor,
                config = bldg
            }
            print("IoBT: Spawned building " .. bldg.id .. " (" .. bldg.type .. ") at " .. bldg.x .. "," .. bldg.y)
        else
            print("ERROR: Owner not found for building " .. bldg.id)
        end
    end

    IoBTState.initialized = true
    print("IoBT: Initialization complete. " .. #IoBTConfig.units .. " units, " .. #IoBTConfig.buildings .. " buildings configured.")

    -- Start DAG after units have spawned (wait for compute nodes to be assigned)
    Trigger.AfterDelay(50, function()
        -- Check if config defines a custom DAG execution (UseConfiguredDag flag)
        if UseConfiguredDag and InitConfiguredDag then
            print("IoBT: Using configured DAG from iobt-config.lua")
            InitConfiguredDag()
        else
            print("IoBT: Using default DAG demo")
            StartDagDemo()
        end
    end)
end

-- Called every game tick (~25 times/second at default speed)
function Tick()
    if not IoBTState.initialized then
        return
    end

    local currentTime = DateTime.GameTime

    -- Process each configured unit
    for _, unitDef in ipairs(IoBTConfig.units) do
        local targetPos = GetInterpolatedPosition(unitDef.waypoints, currentTime)
        local state = IoBTState.units[unitDef.id]

        if targetPos then
            if not state or not state.actor or state.actor.IsDead then
                -- Unit needs to be spawned
                local owner = Player.GetPlayer(unitDef.owner)
                if owner then
                    local actor = Actor.Create(unitDef.type, true, {
                        Owner = owner,
                        Location = targetPos
                    })
                    state = {
                        actor = actor,
                        lastTargetPos = targetPos,
                        config = unitDef
                    }
                    IoBTState.units[unitDef.id] = state
                    print("IoBT: Spawned unit " .. unitDef.id .. " (" .. unitDef.type .. ") at tick " .. currentTime)
                end
            elseif state.lastTargetPos.X ~= targetPos.X or state.lastTargetPos.Y ~= targetPos.Y then
                -- Target position has changed - issue new move command
                -- Only issue command if target is different from last command
                state.actor.Stop()
                state.actor.Move(targetPos)
                state.lastTargetPos = targetPos
            end
        end
    end

    -- Position recording at configured interval
    if IoBTConfig.export.enabled then
        if currentTime % IoBTConfig.export.sampleInterval == 0 then
            RecordPositions(currentTime)
        end

        -- Auto-stop and export
        if IoBTConfig.export.stopAfterTicks > 0 and currentTime >= IoBTConfig.export.stopAfterTicks then
            ExportLog()
            IoBTConfig.export.enabled = false  -- Stop further recording
            print("IoBT: Simulation recording complete.")
        end
    end
end
