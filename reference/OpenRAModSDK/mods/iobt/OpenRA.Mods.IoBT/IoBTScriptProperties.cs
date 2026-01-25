#region Copyright & License Information
/*
 * IoBT Lua Script Properties
 * Exposes IoBT overlay controls and DAG scheduling to Lua scripts
 */
#endregion

using OpenRA.Mods.Common.Scripting;
using OpenRA.Scripting;
using OpenRA.Traits;

namespace OpenRA.Mods.IoBT
{
	[ScriptPropertyGroup("IoBT")]
	public class IoBTGlobalScriptProperties : ScriptPlayerProperties
	{
		readonly World world;

		public IoBTGlobalScriptProperties(ScriptContext context, Player player)
			: base(context, player)
		{
			world = context.World;
		}

		IoBTNetworkOverlay GetOverlay()
		{
			return world.WorldActor.TraitOrDefault<IoBTNetworkOverlay>();
		}

		// === Toggle Controls ===

		[Desc("Toggle the entire network overlay on/off.")]
		public void ToggleNetworkOverlay()
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.Toggle();
		}

		[Desc("Enable or disable the entire overlay.")]
		public void SetOverlayEnabled(bool enabled)
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.OverlayEnabled = enabled;
		}

		[Desc("Set the network link radius in cells.")]
		public void SetNetworkRadius(int radius)
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.NetworkRadius = radius;
		}

		[Desc("Enable or disable network link rendering.")]
		public void SetNetworkLinksEnabled(bool enabled)
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.EnableLinks = enabled;
		}

		[Desc("Enable or disable compute marker rendering.")]
		public void SetComputeMarkersEnabled(bool enabled)
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.EnableComputeMarkers = enabled;
		}

		[Desc("Enable or disable DAG status panel.")]
		public void SetDagStatusEnabled(bool enabled)
		{
			var overlay = GetOverlay();
			if (overlay != null)
				overlay.ShowDagStatus = enabled;
		}

		// === DAG Task Management ===

		[Desc("Get the number of available compute nodes.")]
		public int GetComputeNodeCount()
		{
			var overlay = GetOverlay();
			return overlay?.GetComputeNodeCount() ?? 0;
		}

		[Desc("Add a task to the DAG. Dependencies is a comma-separated list of task IDs.")]
		public void AddDagTask(string taskId, string name, string dependencies)
		{
			var overlay = GetOverlay();
			if (overlay == null) return;

			var deps = string.IsNullOrEmpty(dependencies)
				? new string[0]
				: dependencies.Split(',');

			overlay.AddTask(taskId, name, deps);
		}

		[Desc("Assign a task to run on a compute node (by index 0 to N-1).")]
		public void AssignTask(string taskId, int computeNodeIndex)
		{
			var overlay = GetOverlay();
			overlay?.AssignTask(taskId, computeNodeIndex);
		}

		[Desc("Mark a task as completed.")]
		public void CompleteTask(string taskId)
		{
			var overlay = GetOverlay();
			overlay?.CompleteTask(taskId);
		}

		[Desc("Add an active data transfer link between two compute nodes.")]
		public void AddActiveLink(int fromNodeIndex, int toNodeIndex, string label)
		{
			var overlay = GetOverlay();
			overlay?.AddActiveLink(fromNodeIndex, toNodeIndex, label);
		}

		[Desc("Clear all active data transfer links.")]
		public void ClearActiveLinks()
		{
			var overlay = GetOverlay();
			overlay?.ClearActiveLinks();
		}

		[Desc("Clear all DAG tasks and reset.")]
		public void ClearDag()
		{
			var overlay = GetOverlay();
			overlay?.ClearDag();
		}

		// === Network-Aware Scheduling ===

		[Desc("Check if two compute nodes are within communication range.")]
		public bool AreNodesConnected(int nodeIndex1, int nodeIndex2)
		{
			var overlay = GetOverlay();
			return overlay?.AreNodesConnected(nodeIndex1, nodeIndex2) ?? false;
		}

		[Desc("Mark a task as stalled (waiting for network connectivity).")]
		public void StallTask(string taskId)
		{
			var overlay = GetOverlay();
			overlay?.StallTask(taskId);
		}

		[Desc("Move a stalled task back to pending status.")]
		public void UnstallTask(string taskId)
		{
			var overlay = GetOverlay();
			overlay?.UnstallTask(taskId);
		}

		[Desc("Get the node index a task was assigned to (-1 if not assigned).")]
		public int GetTaskNodeIndex(string taskId)
		{
			var overlay = GetOverlay();
			return overlay?.GetTaskNodeIndex(taskId) ?? -1;
		}

		[Desc("Get the dependencies of a task as comma-separated string.")]
		public string GetTaskDependencies(string taskId)
		{
			var overlay = GetOverlay();
			return overlay?.GetTaskDependencies(taskId) ?? "";
		}
	}
}
