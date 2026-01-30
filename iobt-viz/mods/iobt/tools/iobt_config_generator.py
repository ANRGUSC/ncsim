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
            "comm_range": 4,  # Small range to ensure partitions form
            "max_data_rate": 100,
            "min_data_rate": 10,
            "dag_depth": 3,
            "branching_factor": 2,
            "task_duration": 75,
            "transfer_duration": 50,  # Ticks to show transfer visualization (2 seconds at 25 ticks/sec)
            "simulation_duration": 60,
            "num_squads": 5,
            "partition_mode": True,  # Enable guaranteed partition-inducing mobility
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
        """Generate start and end positions for squads.

        Mobility pattern depends on partition_mode:
        - partition_mode=True: Guaranteed partition pattern (left/right split)
        - partition_mode=False: Radial dispersal pattern
        """
        positions = []
        center_x = (self.MAP_MIN_X + self.MAP_MAX_X) // 2
        center_y = (self.MAP_MIN_Y + self.MAP_MAX_Y) // 2
        partition_mode = self.config.get("partition_mode", True)

        if partition_mode:
            # PARTITION MODE: Create guaranteed left/right split
            # Half the squads go left, half go right
            # This ensures a partition forms when comm_range is small
            comm_range = self.config.get("comm_range", 8)

            # End positions must be > 2*comm_range apart to guarantee partition
            # Left group: x = center - separation, Right group: x = center + separation
            separation = max(comm_range + 4, 10)  # At least comm_range + 4 cells apart

            left_x = center_x - separation
            right_x = center_x + separation

            for i in range(num_squads):
                # Start clustered at center
                start_offset = (i % 3) - 1  # -1, 0, or 1
                start_x = center_x + start_offset
                start_y = center_y + ((i // 3) - 1)

                # Alternate between left and right groups
                if i % 2 == 0:
                    # Left group
                    end_x = left_x + (i % 3) - 1
                    end_y = center_y + ((i // 2) % 3) - 1
                else:
                    # Right group
                    end_x = right_x + (i % 3) - 1
                    end_y = center_y + ((i // 2) % 3) - 1

                positions.append((
                    self._clamp_x(start_x),
                    self._clamp_y(start_y),
                    self._clamp_x(end_x),
                    self._clamp_y(end_y)
                ))
        else:
            # RADIAL MODE: Original radial dispersal pattern
            cluster_radius = 3  # Very tight cluster
            disperse_radius = 12  # How far out they spread

            for i in range(num_squads):
                # Start angle - slight variation to avoid exact overlap
                start_angle = (2 * math.pi * i) / num_squads
                start_x = int(center_x + cluster_radius * math.cos(start_angle))
                start_y = int(center_y + cluster_radius * math.sin(start_angle))

                # End position - spread out to edges in different directions
                end_angle = (2 * math.pi * i) / num_squads
                end_x = int(center_x + disperse_radius * math.cos(end_angle))
                end_y = int(center_y + disperse_radius * math.sin(end_angle))

                positions.append((
                    self._clamp_x(start_x),
                    self._clamp_y(start_y),
                    self._clamp_x(end_x),
                    self._clamp_y(end_y)
                ))

        return positions

    def generate_infantry_squads_lua(self) -> str:
        """Generate Lua code for infantry squads.

        Mobility pattern: Rapid dispersal from center cluster.
        - All squads start clustered together
        - Quick movement outward (dispersal completes before first tasks finish)
        - Then hold positions (with slight drift) for remaining time

        In partition_mode, dispersal is VERY fast to ensure partition forms
        before early tasks (T0, T1) complete and need to transfer data.
        """
        total_nodes = self.config["total_nodes"]
        infantry_pct = self.config["infantry_pct"]
        num_squads = self.config["num_squads"]
        duration_ticks = self.config["simulation_duration"] * 25  # 25 ticks per second
        partition_mode = self.config.get("partition_mode", True)

        infantry_count = int(total_nodes * infantry_pct / 100)
        per_squad = infantry_count // num_squads
        remainder = infantry_count % num_squads

        positions = self._generate_squad_start_positions(num_squads)

        if partition_mode:
            lines = ["-- INFANTRY SQUADS (PARTITION MODE: fast dispersal to create left/right split)"]
            # Timing: DAG starts at tick ~200 (see iobt-main.lua AfterDelay(200,...))
            # T0 starts at ~250 (after SAGA response), completes at ~325
            # We want partition to form DURING T0 execution so that when T0 completes,
            # transfers to T1/T8 are blocked.
            #
            # Dispersal should:
            # - Start around tick 250-270 (when T0 is running)
            # - Complete around tick 310-320 (before T0 finishes at ~325)
            #
            # WP0 will be at start_time (cluster), WP1 will be at dispersal_time (dispersed)
            # For fast split, dispersal_time = 60 ticks of movement from start
            dispersal_time = 60  # 60 ticks of movement to reach dispersed position
        else:
            lines = ["-- INFANTRY SQUADS (clustered start -> gradual dispersal)"]
            # Standard: dispersal in first 20% of simulation
            dispersal_time = int(duration_ticks * 0.20)

        for squad_id in range(1, num_squads + 1):
            squad_size = per_squad + (1 if squad_id <= remainder else 0)
            if squad_size == 0:
                continue

            start_x, start_y, end_x, end_y = positions[squad_id - 1]

            if partition_mode:
                # PARTITION MODE: Units spawn and stay clustered until DAG starts running
                # DAG starts at tick ~200, T0 starts at ~250, completes at ~325
                # We want dispersal to start DURING T0 execution and complete before T0 finishes
                # So: cluster until tick ~260, then disperse by tick ~320
                cluster_time = 260 + (squad_id - 1) * 5  # Small stagger
                dispersal_complete_time = cluster_time + dispersal_time
            else:
                cluster_time = (squad_id - 1) * 10  # Original behavior
                dispersal_complete_time = cluster_time + dispersal_time

            # Generate 5 waypoints: clustered start, rapid dispersal, then hold
            waypoints = []

            # WP 0: Spawn and stay clustered (units appear at game start but at cluster position)
            waypoints.append(f"{{ time = 0, x = {start_x}, y = {start_y} }}")

            # WP 1: Stay clustered until dispersal begins
            waypoints.append(f"{{ time = {cluster_time}, x = {start_x}, y = {start_y} }}")

            # WP 2: Quick move to dispersed position
            waypoints.append(f"{{ time = {dispersal_complete_time}, x = {end_x}, y = {end_y} }}")

            # WP 3-4: Hold dispersed position with slight drift
            for wp_idx in range(3, 5):
                # Slight random-ish drift based on squad_id to keep things interesting
                drift_x = ((squad_id + wp_idx) % 3) - 1  # -1, 0, or 1
                drift_y = ((squad_id * wp_idx) % 3) - 1
                # Hold positions throughout rest of simulation
                t = 0.4 + (wp_idx - 3) * 0.3  # 0.4, 0.7 of simulation
                wp_time = int(t * duration_ticks)
                wp_x = self._clamp_x(end_x + drift_x * wp_idx)
                wp_y = self._clamp_y(end_y + drift_y * wp_idx)
                waypoints.append(f"{{ time = {wp_time}, x = {wp_x}, y = {wp_y} }}")

            lines.append(f"\n-- Squad {squad_id}: {squad_size} infantry")
            lines.append(f"addInfantrySquad({squad_id}, {squad_size}, {start_x}, {start_y}, {{")
            lines.append("    " + ",\n    ".join(waypoints))
            lines.append("})")

        return "\n".join(lines)

    def generate_vehicle_groups_lua(self) -> str:
        """Generate Lua code for vehicle groups.

        Mobility pattern: Rapid dispersal from center cluster (same as infantry).
        Vehicles start slightly offset from infantry but follow same dispersal pattern.

        In partition_mode, vehicles follow same fast dispersal as infantry.
        """
        total_nodes = self.config["total_nodes"]
        infantry_pct = self.config["infantry_pct"]
        num_squads = self.config["num_squads"]
        duration_ticks = self.config["simulation_duration"] * 25
        partition_mode = self.config.get("partition_mode", True)

        vehicle_count = int(total_nodes * (100 - infantry_pct) / 100)
        if vehicle_count == 0:
            return "-- No vehicles configured"

        vehicles_per_group = max(1, vehicle_count // num_squads)
        remainder = vehicle_count % num_squads

        positions = self._generate_squad_start_positions(num_squads)
        # Offset vehicle positions slightly from infantry (but keep in bounds)
        positions = [
            (self._clamp_x(p[0] + 1), self._clamp_y(p[1] + 1),
             self._clamp_x(p[2] + 2), self._clamp_y(p[3] + 2))
            for p in positions
        ]

        if partition_mode:
            lines = ["\n-- VEHICLE GROUPS (PARTITION MODE: fast dispersal with infantry)"]
            # Same fast dispersal as infantry - complete before T0 finishes
            dispersal_time = 45  # Slightly faster than infantry
        else:
            lines = ["\n-- VEHICLE GROUPS (clustered start -> gradual dispersal)"]
            # Standard: dispersal in first 18% of simulation
            dispersal_time = int(duration_ticks * 0.18)

        for group_id in range(1, num_squads + 1):
            group_size = vehicles_per_group + (1 if group_id <= remainder else 0)
            if group_size == 0:
                continue

            start_x, start_y, end_x, end_y = positions[group_id - 1]
            vehicle_type = self.VEHICLE_TYPES[(group_id - 1) % len(self.VEHICLE_TYPES)]

            if partition_mode:
                # PARTITION MODE: Same timing as infantry - cluster then disperse during DAG
                cluster_time = 258 + (group_id - 1) * 5  # Slightly before infantry
                dispersal_complete_time = cluster_time + dispersal_time
            else:
                cluster_time = (group_id - 1) * 10 + 5  # Original behavior
                dispersal_complete_time = cluster_time + dispersal_time

            # Generate 5 waypoints: clustered start, rapid dispersal, then hold
            waypoints = []

            # WP 0: Spawn and stay clustered
            waypoints.append(f"{{ time = 0, x = {start_x}, y = {start_y} }}")

            # WP 1: Stay clustered until dispersal begins
            waypoints.append(f"{{ time = {cluster_time}, x = {start_x}, y = {start_y} }}")

            # WP 2: Quick move to dispersed position
            waypoints.append(f"{{ time = {dispersal_complete_time}, x = {end_x}, y = {end_y} }}")

            # WP 3-4: Hold dispersed position with slight drift
            for wp_idx in range(3, 5):
                drift_x = ((group_id + wp_idx) % 3) - 1
                drift_y = ((group_id * wp_idx) % 3) - 1
                t = 0.4 + (wp_idx - 3) * 0.3
                wp_time = int(t * duration_ticks)
                wp_x = self._clamp_x(end_x + drift_x * wp_idx)
                wp_y = self._clamp_y(end_y + drift_y * wp_idx)
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
        transfer_duration = self.config["transfer_duration"]  # Configurable transfer visualization duration

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
    taskNodeAssignment = {{}}, -- taskId -> nodeIndex that ran/is running the task
    pendingTransfers = {{}},  -- taskId -> list of pending incoming transfers
    transferDuration = {transfer_duration}  -- ticks for data transfer visualization
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
    ConfiguredDagState.pendingTransfers = {{}}
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

-- Pre-assign nodes to tasks (for transfer visualization) without starting them
function PreAssignTaskNodes()
    local nodeCount = Blue.GetComputeNodeCount()
    local nodeIndex = 0

    for _, task in ipairs(IoBTConfig.dagTasks) do
        local taskId = task.id
        -- Only pre-assign if not already assigned
        if ConfiguredDagState.taskNodeAssignment[taskId] == nil then
            local assignedNode = nodeIndex % nodeCount
            nodeIndex = nodeIndex + 1
            ConfiguredDagState.taskNodeAssignment[taskId] = assignedNode
        end
    end
end

-- Find and execute tasks that are ready (dependencies satisfied + connectivity OK)
function ExecuteNextDagTasks()
    local nodeCount = Blue.GetComputeNodeCount()

    -- First, pre-assign all tasks so we know where they'll run
    PreAssignTaskNodes()

    for _, task in ipairs(IoBTConfig.dagTasks) do
        local taskId = task.id

        -- Skip completed, running, or stalled tasks (Lua 5.1 compatible - no goto)
        local shouldSkip = ConfiguredDagState.completedTasks[taskId] or
                          ConfiguredDagState.runningTasks[taskId] or
                          ConfiguredDagState.stalledTasks[taskId]

        if not shouldSkip then
            -- Check if dependencies are satisfied
            if AreDependenciesSatisfied(taskId) then
                -- Get pre-assigned node
                local assignedNode = ConfiguredDagState.taskNodeAssignment[taskId]

                -- Check connectivity to parent task nodes
                local canAssign, blockedBy, blockedNode = CanAssignToNode(taskId, assignedNode)

                if canAssign then
                    -- Assign and run the task
                    print("IoBT DAG: Assigning " .. taskId .. " to node C" .. assignedNode)
                    Blue.AssignTask(taskId, assignedNode)
                    ConfiguredDagState.runningTasks[taskId] = true

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

-- Find all tasks that depend on the given task
function FindDependentTasks(completedTaskId)
    local dependents = {{}}
    for _, task in ipairs(IoBTConfig.dagTasks) do
        for _, dep in ipairs(task.deps) do
            if dep == completedTaskId then
                table.insert(dependents, task.id)
                break
            end
        end
    end
    return dependents
end

-- Start data transfers from completed task to its dependent tasks
function StartDataTransfers(completedTaskId)
    local sourceNode = ConfiguredDagState.taskNodeAssignment[completedTaskId]
    if sourceNode == nil then return end

    local dependents = FindDependentTasks(completedTaskId)
    local transfersStarted = 0

    for _, depTaskId in ipairs(dependents) do
        -- Only transfer if dependent task hasn't completed yet
        if not ConfiguredDagState.completedTasks[depTaskId] then
            -- Get the target node - assign if not yet assigned
            local targetNode = ConfiguredDagState.taskNodeAssignment[depTaskId]

            -- Only show transfer if tasks are on different nodes
            if targetNode ~= nil and targetNode ~= sourceNode then
                print("IoBT DAG: Transferring data " .. completedTaskId .. " -> " .. depTaskId ..
                      " (C" .. sourceNode .. " -> C" .. targetNode .. ")")
                -- Use AddTaskTransferWithNodes to pass explicit node indices
                -- (dest task may not be "assigned" in C# yet, only pre-assigned in Lua)
                Blue.AddTaskTransferWithNodes(completedTaskId, depTaskId, sourceNode, targetNode, "data")
                transfersStarted = transfersStarted + 1

                -- Track pending transfer for the dependent task
                if not ConfiguredDagState.pendingTransfers[depTaskId] then
                    ConfiguredDagState.pendingTransfers[depTaskId] = {{}}
                end
                table.insert(ConfiguredDagState.pendingTransfers[depTaskId], completedTaskId)
            end
        end
    end

    -- Schedule transfer completion and link cleanup
    if transfersStarted > 0 then
        Trigger.AfterDelay(ConfiguredDagState.transferDuration, function()
            Blue.ClearActiveLinks()
            -- Now execute any newly unblocked tasks
            ExecuteNextDagTasks()
        end)
    else
        -- No transfers needed, execute immediately
        ExecuteNextDagTasks()
    end
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
        Blue.ClearActiveLinks()
        Trigger.AfterDelay(75, function()
            RestartDag()
        end)
    else
        -- Start data transfers to dependent tasks
        StartDataTransfers(taskId)
    end
end

-- Restart the DAG execution
function RestartDag()
    print("IoBT DAG: Restarting DAG...")
    Blue.ClearDag()
    Blue.ClearActiveLinks()
    ConfiguredDagState.started = false
    ConfiguredDagState.completedTasks = {{}}
    ConfiguredDagState.runningTasks = {{}}
    ConfiguredDagState.stalledTasks = {{}}
    ConfiguredDagState.taskNodeAssignment = {{}}
    ConfiguredDagState.pendingTransfers = {{}}

    Trigger.AfterDelay(25, function()
        InitConfiguredDag()
    end)
end

-- Flag to use configured DAG instead of hardcoded demo
UseConfiguredDag = true
'''

        return lua_code

    def generate_full_config(self) -> str:
        """Generate the complete Lua configuration file.

        NOTE: This generates DATA ONLY - no execution logic.
        All DAG execution logic with SAGA integration is in iobt-main.lua.
        This separation allows runconfig to regenerate iobt-config.lua without
        overwriting the SAGA scheduler integration code.
        """
        cfg = self.config
        duration_ticks = cfg["simulation_duration"] * 25
        tasks = self.generate_dag_tree()
        total_tasks = len(tasks)
        partition_mode = cfg.get("partition_mode", True)

        # Header comment - varies based on partition mode
        if partition_mode:
            mobility_desc = """Mobility Pattern: PARTITION MODE (guaranteed stall demo)
   - All units start clustered at map center
   - FAST dispersal (~2 seconds) creates left/right split BEFORE T0 completes
   - Left half and right half end up > comm_range apart (guaranteed partition)
   - Baseline mode (B) will stall waiting for reconnection
   - Smart-Resilient mode (S) will reassign tasks to parent's partition
   - Press S to fix stalls, B to see baseline behavior"""
        else:
            mobility_desc = """Mobility Pattern: Clustered start -> gradual dispersal
   - All units start near map center (clustered together)
   - Gradual dispersal to spread positions over time
   - Groups hold dispersed positions with slight drift"""

        header = f'''--[[
   IoBT Configuration (DATA ONLY)
   Generated by IoBT-Viz Config GUI
   Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

   Nodes: {cfg["total_nodes"]} ({cfg["infantry_pct"]}% infantry, {100-cfg["infantry_pct"]}% vehicles)
   Communication Range: {cfg["comm_range"]} cells
   DAG: {cfg["dag_depth"]} levels, {cfg["branching_factor"]} branches ({total_tasks} tasks)
   Task Duration: {cfg["task_duration"]} ticks per task
   Transfer Duration: {cfg["transfer_duration"]} ticks (cyan link highlight)
   Simulation: {cfg["simulation_duration"]} seconds
   Partition Mode: {partition_mode}

   {mobility_desc}

   NOTE: Execution logic is in iobt-main.lua (not here).
   This file defines data only: units, buildings, dagTasks, network settings.
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

    dagSettings = {{
        taskDuration = {cfg["task_duration"]},  -- ticks per task
        transferDuration = {cfg["transfer_duration"]},  -- ticks for transfer visualization
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

        # NOTE: We intentionally do NOT include generate_dag_execution_lua() here.
        # All execution logic with SAGA integration is in iobt-main.lua.
        # This separation allows runconfig to be re-run without breaking SAGA.

        return header + main_config + helpers + "\n" + infantry + "\n" + vehicles + "\n"


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
