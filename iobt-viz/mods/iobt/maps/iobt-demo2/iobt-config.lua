--[[
   IoBT Configuration - Small Scale Demo

   30 units: 20 infantry + 10 vehicles
   Map bounds: X from 49-79, Y from 45-81
]]

IoBTConfig = {
    ticksPerSecond = 25,

    export = {
        enabled = true,
        sampleInterval = 125,  -- Every 5 seconds
        stopAfterTicks = 1500, -- 60 seconds
    },

    units = {},

    buildings = {
        { id = "power1", type = "powr", owner = "Blue", x = 66, y = 78 },
        { id = "hq1", type = "dome", owner = "Blue", x = 64, y = 74 },
        { id = "base1", type = "fact", owner = "Blue", x = 60, y = 74 },
    },

    networkLinks = {}
}

-- Helper to add infantry squad
local function addInfantrySquad(squadId, squadSize, waypoints)
    for i = 1, squadSize do
        local offsetX = (i % 4) - 2
        local offsetY = math.floor(i / 4)
        local unit = {
            id = "inf_" .. squadId .. "_" .. i,
            type = "e1",
            owner = "Blue",
            waypoints = {}
        }
        for _, wp in ipairs(waypoints) do
            table.insert(unit.waypoints, {
                time = wp.time + (i * 3),
                x = math.max(49, math.min(79, wp.x + offsetX)),
                y = math.max(45, math.min(81, wp.y + offsetY))
            })
        end
        table.insert(IoBTConfig.units, unit)
    end
end

-- Helper to add vehicle group
local function addVehicleGroup(groupId, groupSize, unitType, waypoints)
    for i = 1, groupSize do
        local offsetX = (i % 3) - 1
        local offsetY = math.floor(i / 3)
        local unit = {
            id = "veh_" .. groupId .. "_" .. i,
            type = unitType,
            owner = "Blue",
            waypoints = {}
        }
        for _, wp in ipairs(waypoints) do
            table.insert(unit.waypoints, {
                time = wp.time + (i * 5),
                x = math.max(49, math.min(79, wp.x + offsetX)),
                y = math.max(45, math.min(81, wp.y + offsetY))
            })
        end
        table.insert(IoBTConfig.units, unit)
    end
end

-- 2 Infantry Squads (10 each = 20 total)
addInfantrySquad(1, 10, {
    { time = 0,   x = 52, y = 48 },
    { time = 300, x = 58, y = 54 },
    { time = 600, x = 64, y = 62 },
    { time = 900, x = 64, y = 70 },
})

addInfantrySquad(2, 10, {
    { time = 100, x = 76, y = 50 },
    { time = 400, x = 70, y = 56 },
    { time = 700, x = 64, y = 64 },
    { time = 1000, x = 60, y = 72 },
})

-- 2 Vehicle Groups (5 each = 10 total)
addVehicleGroup(1, 5, "jeep", {
    { time = 0,   x = 50, y = 60 },
    { time = 250, x = 56, y = 64 },
    { time = 500, x = 62, y = 68 },
    { time = 750, x = 66, y = 74 },
})

addVehicleGroup(2, 5, "apc", {
    { time = 150, x = 78, y = 62 },
    { time = 400, x = 72, y = 66 },
    { time = 650, x = 66, y = 70 },
    { time = 900, x = 62, y = 74 },
})
