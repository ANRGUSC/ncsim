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
