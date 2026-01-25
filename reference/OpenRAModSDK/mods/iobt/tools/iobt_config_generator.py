"""
IoBT Configuration Generator

Core logic for generating Lua configuration files for IoBT-Viz simulations.
Separated from GUI for testability and reuse.
"""

import math
from datetime import datetime
from typing import List, Dict, Any, Tuple


class IoBTConfigGenerator:
    """Generates Lua configuration for IoBT-Viz simulations."""

    # Tighter map bounds to avoid water at edges
    # Safe land area is roughly X: 50-78, Y: 48-79
    MAP_MIN_X = 51
    MAP_MAX_X = 77
    MAP_MIN_Y = 49
    MAP_MAX_Y = 78

    # Unit types
    INFANTRY_TYPE = "e1"
    VEHICLE_TYPES = ["jeep", "apc", "1tnk", "2tnk", "3tnk", "arty"]

    def __init__(self):
        self.config = {
            "total_nodes": 50,
            "infantry_pct": 70,
            "compute_node_pct": 30,
            "comm_range": 8,
            "max_data_rate": 100,
            "min_data_rate": 10,
            "dag_depth": 3,
            "branching_factor": 2,
            "task_duration": 75,
            "simulation_duration": 60,
            "num_squads": 5,
        }

    def set_config(self, **kwargs):
        """Update configuration parameters."""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value

    def generate_dag_tree(self) -> List[Dict[str, Any]]:
        """Generate a tree-structured DAG with given depth and branching."""
        depth = self.config["dag_depth"]
        branching = self.config["branching_factor"]
        tasks = []
        task_id = [0]  # Use list for closure

        def add_node(parent_id: str, current_depth: int):
            node_id = f"T{task_id[0]}"
            task_id[0] += 1
            tasks.append({
                "id": node_id,
                "name": f"Task {node_id[1:]}",
                "deps": [parent_id] if parent_id else []
            })

            if current_depth < depth:
                for _ in range(branching):
                    add_node(node_id, current_depth + 1)

        add_node(None, 0)
        return tasks

    def generate_dag_preview(self) -> str:
        """Generate ASCII art preview of DAG tree."""
        depth = self.config["dag_depth"]
        branching = self.config["branching_factor"]

        lines = []
        task_id = [0]

        def draw_node(prefix: str, is_last: bool, current_depth: int):
            node_name = f"T{task_id[0]}"
            task_id[0] += 1

            if current_depth == 0:
                lines.append(node_name)
            else:
                connector = "+-- " if is_last else "+-- "
                lines.append(prefix + connector + node_name)

            if current_depth < depth:
                new_prefix = prefix + ("    " if is_last else "|   ")
                for i in range(branching):
                    is_last_child = (i == branching - 1)
                    draw_node(new_prefix, is_last_child, current_depth + 1)

        draw_node("", True, 0)
        return "\n".join(lines)

    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation."""
        return a + (b - a) * t

    def _clamp_x(self, x: float) -> int:
        """Clamp X coordinate to map bounds."""
        return max(self.MAP_MIN_X, min(self.MAP_MAX_X, int(x)))

    def _clamp_y(self, y: float) -> int:
        """Clamp Y coordinate to map bounds."""
        return max(self.MAP_MIN_Y, min(self.MAP_MAX_Y, int(y)))

    def _generate_squad_start_positions(self, num_squads: int) -> List[Tuple[int, int, int, int]]:
        """Generate start and end positions for squads around the map edges."""
        positions = []
        center_x = (self.MAP_MIN_X + self.MAP_MAX_X) // 2
        center_y = (self.MAP_MIN_Y + self.MAP_MAX_Y) // 2

        # Distribute squads around the perimeter (but staying in safe bounds)
        for i in range(num_squads):
            angle = (2 * math.pi * i) / num_squads
            # Start from edges (reduced radius to stay in safe area)
            start_x = int(center_x + 12 * math.cos(angle))
            start_y = int(center_y + 13 * math.sin(angle))
            # Move toward center with some offset
            end_angle = angle + math.pi + (math.pi / 6) * (i % 2 - 0.5)
            end_x = int(center_x + 6 * math.cos(end_angle))
            end_y = int(center_y + 7 * math.sin(end_angle))

            positions.append((
                self._clamp_x(start_x),
                self._clamp_y(start_y),
                self._clamp_x(end_x),
                self._clamp_y(end_y)
            ))

        return positions

    def generate_infantry_squads_lua(self) -> str:
        """Generate Lua code for infantry squads."""
        total_nodes = self.config["total_nodes"]
        infantry_pct = self.config["infantry_pct"]
        num_squads = self.config["num_squads"]
        duration_ticks = self.config["simulation_duration"] * 25  # 25 ticks per second

        infantry_count = int(total_nodes * infantry_pct / 100)
        per_squad = infantry_count // num_squads
        remainder = infantry_count % num_squads

        positions = self._generate_squad_start_positions(num_squads)
        lines = ["-- INFANTRY SQUADS"]

        for squad_id in range(1, num_squads + 1):
            squad_size = per_squad + (1 if squad_id <= remainder else 0)
            if squad_size == 0:
                continue

            start_x, start_y, end_x, end_y = positions[squad_id - 1]
            start_time = (squad_id - 1) * 50  # Stagger squad spawns

            # Generate 5 waypoints per squad
            waypoints = []
            for wp_idx in range(5):
                t = wp_idx / 4
                wp_time = start_time + int(t * duration_ticks * 0.9)
                wp_x = self._clamp_x(self._lerp(start_x, end_x, t))
                wp_y = self._clamp_y(self._lerp(start_y, end_y, t))
                waypoints.append(f"{{ time = {wp_time}, x = {wp_x}, y = {wp_y} }}")

            lines.append(f"\n-- Squad {squad_id}: {squad_size} infantry")
            lines.append(f"addInfantrySquad({squad_id}, {squad_size}, {start_x}, {start_y}, {{")
            lines.append("    " + ",\n    ".join(waypoints))
            lines.append("})")

        return "\n".join(lines)

    def generate_vehicle_groups_lua(self) -> str:
        """Generate Lua code for vehicle groups."""
        total_nodes = self.config["total_nodes"]
        infantry_pct = self.config["infantry_pct"]
        num_squads = self.config["num_squads"]
        duration_ticks = self.config["simulation_duration"] * 25

        vehicle_count = int(total_nodes * (100 - infantry_pct) / 100)
        if vehicle_count == 0:
            return "-- No vehicles configured"

        vehicles_per_group = max(1, vehicle_count // num_squads)
        remainder = vehicle_count % num_squads

        positions = self._generate_squad_start_positions(num_squads)
        # Offset vehicle positions from infantry (but keep in bounds)
        positions = [
            (self._clamp_x(p[0] + 2), self._clamp_y(p[1] + 2),
             self._clamp_x(p[2] - 1), self._clamp_y(p[3] - 1))
            for p in positions
        ]

        lines = ["\n-- VEHICLE GROUPS"]

        for group_id in range(1, num_squads + 1):
            group_size = vehicles_per_group + (1 if group_id <= remainder else 0)
            if group_size == 0:
                continue

            start_x, start_y, end_x, end_y = positions[group_id - 1]
            start_time = (group_id - 1) * 50 + 25  # Offset from infantry
            vehicle_type = self.VEHICLE_TYPES[(group_id - 1) % len(self.VEHICLE_TYPES)]

            # Generate 5 waypoints per group
            waypoints = []
            for wp_idx in range(5):
                t = wp_idx / 4
                wp_time = start_time + int(t * duration_ticks * 0.85)
                wp_x = self._clamp_x(self._lerp(start_x, end_x, t))
                wp_y = self._clamp_y(self._lerp(start_y, end_y, t))
                waypoints.append(f"{{ time = {wp_time}, x = {wp_x}, y = {wp_y} }}")

            lines.append(f"\n-- Group {group_id}: {group_size} {vehicle_type}")
            lines.append(f'addVehicleGroup({group_id}, {group_size}, "{vehicle_type}", {{')
            lines.append("    " + ",\n    ".join(waypoints))
            lines.append("})")

        return "\n".join(lines)

    def generate_dag_tasks_lua(self) -> str:
        """Generate Lua code for DAG tasks table."""
        tasks = self.generate_dag_tree()
        lines = ["    dagTasks = {"]

        for task in tasks:
            deps_str = ", ".join(f'"{d}"' for d in task["deps"])
            lines.append(f'        {{ id = "{task["id"]}", name = "{task["name"]}", deps = {{{deps_str}}} }},')

        lines.append("    }")
        return "\n".join(lines)

    def generate_dag_execution_lua(self) -> str:
        """Generate Lua code that executes the DAG with network-aware scheduling."""
        tasks = self.generate_dag_tree()
        task_duration = self.config["task_duration"]

        # Build the Lua code with network-aware scheduling
        lua_code = f'''
-- ============================================
-- DAG Execution Logic (Generated)
-- Network-Aware Scheduling with Connectivity Checks
-- ============================================

-- Track DAG execution state
ConfiguredDagState = {{
    started = false,
    taskIndex = 1,
    tasks = {{}},
    completedTasks = {{}},
    runningTasks = {{}},      -- taskId -> true for currently running
    stalledTasks = {{}},      -- taskId -> true for connectivity-blocked
    taskNodeAssignment = {{}} -- taskId -> nodeIndex that ran/is running the task
}}

-- Initialize the configured DAG
function InitConfiguredDag()
    if ConfiguredDagState.started then return end

    local nodeCount = Blue.GetComputeNodeCount()
    print("IoBT DAG: Found " .. nodeCount .. " compute nodes")

    if nodeCount < 1 then
        print("IoBT DAG: Need at least 1 compute node")
        return
    end

    ConfiguredDagState.started = true
    ConfiguredDagState.completedTasks = {{}}
    ConfiguredDagState.runningTasks = {{}}
    ConfiguredDagState.stalledTasks = {{}}
    ConfiguredDagState.taskNodeAssignment = {{}}
    print("IoBT DAG: Starting configured DAG execution...")

    -- Register all tasks with the DAG system
'''

        # Generate task registration with all dependencies
        for task in tasks:
            deps_str = ",".join(task["deps"]) if task["deps"] else ""
            lua_code += f'    Blue.AddDagTask("{task["id"]}", "{task["name"]}", "{deps_str}")\n'

        lua_code += f'''
    -- Start executing tasks
    ExecuteNextDagTasks()

    -- Start periodic connectivity check for stalled tasks
    StartConnectivityMonitor()
end

-- Check if a task's dependencies are satisfied (all completed)
function AreDependenciesSatisfied(taskId)
    for _, task in ipairs(IoBTConfig.dagTasks) do
        if task.id == taskId then
            for _, dep in ipairs(task.deps) do
                if not ConfiguredDagState.completedTasks[dep] then
                    return false
                end
            end
            return true
        end
    end
    return true
end

-- Check if all parent task nodes are connected to the target node
-- Returns true if task can be assigned to targetNode, false if blocked by connectivity
function CanAssignToNode(taskId, targetNode)
    for _, task in ipairs(IoBTConfig.dagTasks) do
        if task.id == taskId then
            for _, dep in ipairs(task.deps) do
                local parentNode = ConfiguredDagState.taskNodeAssignment[dep]
                if parentNode ~= nil then
                    -- Check if parent node is connected to target node
                    if not Blue.AreNodesConnected(parentNode, targetNode) then
                        return false, dep, parentNode
                    end
                end
            end
            return true, nil, nil
        end
    end
    return true, nil, nil
end

-- Find and execute tasks that are ready (dependencies satisfied + connectivity OK)
function ExecuteNextDagTasks()
    local nodeCount = Blue.GetComputeNodeCount()
    local nodeIndex = 0

    for _, task in ipairs(IoBTConfig.dagTasks) do
        local taskId = task.id

        -- Skip completed, running, or stalled tasks (Lua 5.1 compatible - no goto)
        local shouldSkip = ConfiguredDagState.completedTasks[taskId] or
                          ConfiguredDagState.runningTasks[taskId] or
                          ConfiguredDagState.stalledTasks[taskId]

        if not shouldSkip then
            -- Check if dependencies are satisfied
            if AreDependenciesSatisfied(taskId) then
                -- Compute target node (round-robin)
                local assignedNode = nodeIndex % nodeCount
                nodeIndex = nodeIndex + 1

                -- Check connectivity to parent task nodes
                local canAssign, blockedBy, blockedNode = CanAssignToNode(taskId, assignedNode)

                if canAssign then
                    -- Assign and run the task
                    print("IoBT DAG: Assigning " .. taskId .. " to node C" .. assignedNode)
                    Blue.AssignTask(taskId, assignedNode)
                    ConfiguredDagState.runningTasks[taskId] = true
                    ConfiguredDagState.taskNodeAssignment[taskId] = assignedNode

                    -- Schedule completion after task duration
                    local taskDuration = {task_duration}  -- ticks per task
                    Trigger.AfterDelay(taskDuration, function()
                        CompleteTask(taskId)
                    end)
                else
                    -- Stall the task - waiting for connectivity
                    print("IoBT DAG: Task " .. taskId .. " stalled - C" .. assignedNode ..
                          " disconnected from parent " .. blockedBy .. " (C" .. blockedNode .. ")")
                    Blue.StallTask(taskId)
                    ConfiguredDagState.stalledTasks[taskId] = true
                    -- Store intended node assignment for retry
                    ConfiguredDagState.taskNodeAssignment[taskId] = assignedNode
                end
            end
        end
    end
end

-- Periodically check if stalled tasks can resume
function StartConnectivityMonitor()
    Trigger.AfterDelay(25, function()
        if not ConfiguredDagState.started then return end

        local anyUnstalled = false

        for taskId, _ in pairs(ConfiguredDagState.stalledTasks) do
            local targetNode = ConfiguredDagState.taskNodeAssignment[taskId]
            if targetNode then
                local canAssign, _, _ = CanAssignToNode(taskId, targetNode)
                if canAssign then
                    -- Connectivity restored - unstall and run
                    print("IoBT DAG: Task " .. taskId .. " connectivity restored, resuming on C" .. targetNode)
                    Blue.UnstallTask(taskId)
                    ConfiguredDagState.stalledTasks[taskId] = nil

                    Blue.AssignTask(taskId, targetNode)
                    ConfiguredDagState.runningTasks[taskId] = true

                    local taskDuration = {task_duration}
                    Trigger.AfterDelay(taskDuration, function()
                        CompleteTask(taskId)
                    end)

                    anyUnstalled = true
                end
            end
        end

        -- Continue monitoring
        StartConnectivityMonitor()
    end)
end

-- Mark a task as complete and trigger dependent tasks
function CompleteTask(taskId)
    if ConfiguredDagState.completedTasks[taskId] then
        return  -- Already completed
    end

    print("IoBT DAG: " .. taskId .. " complete")
    Blue.CompleteTask(taskId)
    ConfiguredDagState.completedTasks[taskId] = true
    ConfiguredDagState.runningTasks[taskId] = nil

    -- Check if all tasks are done
    local allDone = true
    for _, task in ipairs(IoBTConfig.dagTasks) do
        if not ConfiguredDagState.completedTasks[task.id] then
            allDone = false
            break
        end
    end

    if allDone then
        print("IoBT DAG: All tasks complete! Restarting in 3 seconds...")
        Trigger.AfterDelay(75, function()
            RestartDag()
        end)
    else
        -- Execute any newly unblocked tasks
        ExecuteNextDagTasks()
    end
end

-- Restart the DAG execution
function RestartDag()
    print("IoBT DAG: Restarting DAG...")
    Blue.ClearDag()
    ConfiguredDagState.started = false
    ConfiguredDagState.completedTasks = {{}}
    ConfiguredDagState.runningTasks = {{}}
    ConfiguredDagState.stalledTasks = {{}}
    ConfiguredDagState.taskNodeAssignment = {{}}

    Trigger.AfterDelay(25, function()
        InitConfiguredDag()
    end)
end

-- Flag to use configured DAG instead of hardcoded demo
UseConfiguredDag = true
'''

        return lua_code

    def generate_full_config(self) -> str:
        """Generate the complete Lua configuration file."""
        cfg = self.config
        duration_ticks = cfg["simulation_duration"] * 25
        tasks = self.generate_dag_tree()
        total_tasks = len(tasks)

        # Header comment
        header = f'''--[[
   IoBT Configuration
   Generated by IoBT-Viz Config GUI
   Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

   Nodes: {cfg["total_nodes"]} ({cfg["infantry_pct"]}% infantry, {100-cfg["infantry_pct"]}% vehicles)
   Communication Range: {cfg["comm_range"]} cells
   DAG: {cfg["dag_depth"]} levels, {cfg["branching_factor"]} branches ({total_tasks} tasks)
   Task Duration: {cfg["task_duration"]} ticks per task
   Simulation: {cfg["simulation_duration"]} seconds
]]'''

        # Main config structure
        main_config = f'''
IoBTConfig = {{
    ticksPerSecond = 25,

    export = {{
        enabled = true,
        sampleInterval = 125,  -- Every 5 seconds
        stopAfterTicks = {duration_ticks},  -- {cfg["simulation_duration"]} seconds
    }},

    networkSettings = {{
        range = {cfg["comm_range"]},
        maxDataRate = {cfg["max_data_rate"]},
        minDataRate = {cfg["min_data_rate"]},
    }},

    units = {{}},

    buildings = {{
        -- Power plants to avoid low power warning
        {{ id = "power1", type = "powr", owner = "Blue", x = 74, y = 76 }},
        {{ id = "power2", type = "powr", owner = "Blue", x = 54, y = 76 }},
        -- Command bases
        {{ id = "hq1", type = "dome", owner = "Blue", x = 74, y = 74 }},
        {{ id = "hq2", type = "dome", owner = "Blue", x = 54, y = 74 }},
        {{ id = "base1", type = "fact", owner = "Blue", x = 74, y = 70 }},
        {{ id = "base2", type = "fact", owner = "Blue", x = 54, y = 70 }},
    }},

    networkLinks = {{}},

{self.generate_dag_tasks_lua()}
}}'''

        # Helper functions with tighter bounds
        helpers = f'''
-- Helper to add infantry squad (rifle soldiers only - e1)
local function addInfantrySquad(squadId, squadSize, startX, startY, waypoints)
    for i = 1, squadSize do
        local offsetX = (i % 5) - 2  -- Spread in a 5-wide formation
        local offsetY = math.floor(i / 5)
        local unit = {{
            id = "inf_" .. squadId .. "_" .. i,
            type = "e1",  -- Rifle infantry only
            owner = "Blue",
            waypoints = {{}}
        }}
        for _, wp in ipairs(waypoints) do
            table.insert(unit.waypoints, {{
                time = wp.time + (i * 2),  -- Slight time offset per soldier
                x = math.max({self.MAP_MIN_X}, math.min({self.MAP_MAX_X}, wp.x + offsetX)),
                y = math.max({self.MAP_MIN_Y}, math.min({self.MAP_MAX_Y}, wp.y + offsetY))
            }})
        end
        table.insert(IoBTConfig.units, unit)
    end
end

-- Helper to add vehicle group
local function addVehicleGroup(groupId, groupSize, unitType, waypoints)
    for i = 1, groupSize do
        local offsetX = (i % 3) - 1  -- Spread in a 3-wide formation
        local offsetY = math.floor(i / 3) * 2
        local unit = {{
            id = "veh_" .. groupId .. "_" .. i,
            type = unitType,
            owner = "Blue",
            waypoints = {{}}
        }}
        for _, wp in ipairs(waypoints) do
            table.insert(unit.waypoints, {{
                time = wp.time + (i * 5),  -- Slight time offset per vehicle
                x = math.max({self.MAP_MIN_X}, math.min({self.MAP_MAX_X}, wp.x + offsetX)),
                y = math.max({self.MAP_MIN_Y}, math.min({self.MAP_MAX_Y}, wp.y + offsetY))
            }})
        end
        table.insert(IoBTConfig.units, unit)
    end
end
'''

        # Generated unit definitions
        infantry = self.generate_infantry_squads_lua()
        vehicles = self.generate_vehicle_groups_lua()

        # DAG execution logic
        dag_execution = self.generate_dag_execution_lua()

        return header + main_config + helpers + "\n" + infantry + "\n" + vehicles + "\n" + dag_execution


def main():
    """Test the generator."""
    gen = IoBTConfigGenerator()
    gen.set_config(
        total_nodes=100,
        infantry_pct=75,
        num_squads=8,
        dag_depth=3,
        branching_factor=2,
    )

    print("DAG Preview:")
    print(gen.generate_dag_preview())
    print("\n" + "=" * 50 + "\n")
    print(gen.generate_full_config())


if __name__ == "__main__":
    main()
