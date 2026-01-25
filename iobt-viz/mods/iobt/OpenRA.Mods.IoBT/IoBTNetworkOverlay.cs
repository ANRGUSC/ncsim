#region Copyright & License Information
/*
 * IoBT Network Overlay
 * Renders network links between units with distance-based data rates
 * Links color-coded: green (high rate) -> yellow -> red (low rate)
 * Compute nodes shown as small filled circles: blue (high CPU) or yellow (low CPU)
 * Supports DAG task scheduling visualization
 */
#endregion

using System;
using System.Collections.Generic;
using System.Linq;
using OpenRA.Graphics;
using OpenRA.Mods.Common.Commands;
using OpenRA.Mods.Common.Traits;
using OpenRA.Mods.Common.Widgets;
using OpenRA.Primitives;
using OpenRA.Traits;

namespace OpenRA.Mods.IoBT
{
	[TraitLocation(SystemActors.World)]
	[Desc("Renders network links between nearby units and compute point markers.")]
	public class IoBTNetworkOverlayInfo : TraitInfo, Requires<ChatCommandsInfo>
	{
		[Desc("Maximum distance (in cells) for automatic network links.")]
		public readonly int NetworkRadius = 8;

		[Desc("Width of network link lines.")]
		public readonly float LinkWidth = 1f;

		[Desc("Width of active (data transfer) link lines.")]
		public readonly float ActiveLinkWidth = 3f;

		[Desc("Maximum data rate at zero distance (Mbps).")]
		public readonly int MaxDataRate = 100;

		[Desc("Minimum data rate to show link (below this, no link drawn).")]
		public readonly int MinDataRate = 10;

		[Desc("Radius of compute point circles (in world units).")]
		public readonly int ComputeCircleRadius = 150;

		[Desc("Percentage of infantry that are compute nodes (0-100).")]
		public readonly int InfantryComputePercent = 15;

		[Desc("Percentage of vehicles that are compute nodes (0-100).")]
		public readonly int VehicleComputePercent = 50;

		public override object Create(ActorInitializer init) { return new IoBTNetworkOverlay(init.Self, this); }
	}

	public class IoBTNetworkOverlay : IRenderAnnotations, IWorldLoaded, ITick, IChatCommand
	{
		readonly IoBTNetworkOverlayInfo info;
		readonly World world;
		readonly Random random = new Random();

		// Global toggle (can be controlled via Lua or 'n' command)
		public bool OverlayEnabled { get; set; } = true;
		public bool EnableLinks { get; set; } = true;
		public bool EnableComputeMarkers { get; set; } = true;
		public bool ShowDagStatus { get; set; } = true;

		// Lua-controlled settings
		public int NetworkRadius { get; set; }

		// Tracked actors with their compute status
		readonly Dictionary<Actor, ComputeNodeInfo> computeNodes = new();

		// Cached actor lists for performance
		readonly List<Actor> trackedActors = new();
		int lastUpdateTick = -10;

		// DAG Task Scheduling
		readonly Dictionary<string, DagTask> dagTasks = new();
		readonly List<ActiveLink> activeLinks = new();
		readonly List<Actor> computeNodeList = new(); // Ordered list of compute nodes for assignment

		public IoBTNetworkOverlay(Actor self, IoBTNetworkOverlayInfo info)
		{
			this.info = info;
			world = self.World;
			NetworkRadius = info.NetworkRadius;
		}

		void IWorldLoaded.WorldLoaded(World w, WorldRenderer wr)
		{
			// Register chat commands for toggling the overlay
			var console = w.WorldActor.Trait<ChatCommands>();
			console.RegisterCommand("n", this);
			console.RegisterCommand("network", this);

			Log.Write("debug", "IoBT: Network overlay loaded. Type 'n' or 'network' in chat to toggle.");
		}

		void IChatCommand.InvokeCommand(string name, string arg)
		{
			if (name == "n" || name == "network")
			{
				Toggle();
				var status = OverlayEnabled ? "ON" : "OFF";
				TextNotificationsManager.Debug($"IoBT Network Overlay: {status}");
			}
		}

		void ITick.Tick(Actor self)
		{
			// Update tracked actors every 10 ticks for performance
			if (world.WorldTick - lastUpdateTick >= 10)
			{
				lastUpdateTick = world.WorldTick;
				UpdateTrackedActors();
			}
		}

		// Toggle the entire overlay on/off
		public void Toggle()
		{
			OverlayEnabled = !OverlayEnabled;
		}

		// === DAG Task Management API ===

		// Define a new task in the DAG
		public void AddTask(string taskId, string name, string[] dependencies)
		{
			dagTasks[taskId] = new DagTask
			{
				Id = taskId,
				Name = name,
				Dependencies = dependencies ?? Array.Empty<string>(),
				Status = TaskStatus.Pending,
				AssignedNode = null
			};
		}

		// Assign a task to a compute node (by index in compute node list)
		public void AssignTask(string taskId, int computeNodeIndex)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return;

			if (computeNodeIndex >= 0 && computeNodeIndex < computeNodeList.Count)
			{
				var node = computeNodeList[computeNodeIndex];
				task.AssignedNode = node;
				task.AssignedNodeIndex = computeNodeIndex;
				task.Status = TaskStatus.Running;

				// Update the compute node info with the task
				if (computeNodes.TryGetValue(node, out var nodeInfo))
				{
					nodeInfo.RunningTaskId = taskId;
				}
			}
		}

		// Mark a task as completed
		public void CompleteTask(string taskId)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return;

			task.Status = TaskStatus.Completed;

			// Clear the task from the compute node
			if (task.AssignedNode != null && computeNodes.TryGetValue(task.AssignedNode, out var nodeInfo))
			{
				nodeInfo.RunningTaskId = null;
			}
		}

		// Add an active data transfer link between two compute nodes
		public void AddActiveLink(int fromNodeIndex, int toNodeIndex, string label)
		{
			if (fromNodeIndex >= 0 && fromNodeIndex < computeNodeList.Count &&
			    toNodeIndex >= 0 && toNodeIndex < computeNodeList.Count)
			{
				activeLinks.Add(new ActiveLink
				{
					From = computeNodeList[fromNodeIndex],
					To = computeNodeList[toNodeIndex],
					Label = label,
					FromNodeIndex = fromNodeIndex,
					ToNodeIndex = toNodeIndex
				});
			}
		}

		// Add a task-to-task transfer (shows as "T1→T4" in the status panel)
		// This version looks up node indices from task assignments
		public void AddTaskTransfer(string sourceTaskId, string destTaskId, string label = "data")
		{
			if (!dagTasks.TryGetValue(sourceTaskId, out var sourceTask) ||
			    !dagTasks.TryGetValue(destTaskId, out var destTask))
				return;

			var fromNodeIndex = sourceTask.AssignedNodeIndex;
			var toNodeIndex = destTask.AssignedNodeIndex;

			if (fromNodeIndex >= 0 && fromNodeIndex < computeNodeList.Count &&
			    toNodeIndex >= 0 && toNodeIndex < computeNodeList.Count &&
			    fromNodeIndex != toNodeIndex)  // Only show if on different nodes
			{
				activeLinks.Add(new ActiveLink
				{
					From = computeNodeList[fromNodeIndex],
					To = computeNodeList[toNodeIndex],
					Label = label,
					SourceTaskId = sourceTaskId,
					DestTaskId = destTaskId,
					FromNodeIndex = fromNodeIndex,
					ToNodeIndex = toNodeIndex
				});
			}
		}

		// Add a task-to-task transfer with explicit node indices (for when dest task isn't assigned yet)
		public void AddTaskTransferWithNodes(string sourceTaskId, string destTaskId, int fromNodeIndex, int toNodeIndex, string label = "data")
		{
			Log.Write("debug", $"IoBT: AddTaskTransferWithNodes called: {sourceTaskId}->{destTaskId}, nodes {fromNodeIndex}->{toNodeIndex}, computeNodeList.Count={computeNodeList.Count}");

			if (fromNodeIndex >= 0 && fromNodeIndex < computeNodeList.Count &&
			    toNodeIndex >= 0 && toNodeIndex < computeNodeList.Count &&
			    fromNodeIndex != toNodeIndex)  // Only show if on different nodes
			{
				activeLinks.Add(new ActiveLink
				{
					From = computeNodeList[fromNodeIndex],
					To = computeNodeList[toNodeIndex],
					Label = label,
					SourceTaskId = sourceTaskId,
					DestTaskId = destTaskId,
					FromNodeIndex = fromNodeIndex,
					ToNodeIndex = toNodeIndex
				});
				Log.Write("debug", $"IoBT: Added active link, activeLinks.Count={activeLinks.Count}");
			}
			else
			{
				Log.Write("debug", $"IoBT: Skipped - indices out of range or same node");
			}
		}

		// Clear all active links
		public void ClearActiveLinks()
		{
			activeLinks.Clear();
		}

		// Clear all DAG tasks
		public void ClearDag()
		{
			dagTasks.Clear();
			activeLinks.Clear();
			foreach (var nodeInfo in computeNodes.Values)
				nodeInfo.RunningTaskId = null;
		}

		// Get number of compute nodes (for Lua to know how many are available)
		public int GetComputeNodeCount()
		{
			return computeNodeList.Count;
		}

		// Check if two compute nodes are within communication range
		public bool AreNodesConnected(int nodeIndex1, int nodeIndex2)
		{
			if (nodeIndex1 < 0 || nodeIndex1 >= computeNodeList.Count ||
			    nodeIndex2 < 0 || nodeIndex2 >= computeNodeList.Count)
				return false;

			if (nodeIndex1 == nodeIndex2)
				return true;

			var node1 = computeNodeList[nodeIndex1];
			var node2 = computeNodeList[nodeIndex2];

			if (node1.IsDead || !node1.IsInWorld || node2.IsDead || !node2.IsInWorld)
				return false;

			var diff = node1.CenterPosition - node2.CenterPosition;
			var distSquared = (long)diff.X * diff.X + (long)diff.Y * diff.Y;
			var distance = Math.Sqrt(distSquared);

			var radiusInWorld = NetworkRadius * 1024;
			return distance <= radiusInWorld;
		}

		// Stall a task (waiting for network connectivity)
		public void StallTask(string taskId)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return;

			task.Status = TaskStatus.Stalled;
		}

		// Unstall a task (move from stalled back to pending)
		public void UnstallTask(string taskId)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return;

			if (task.Status == TaskStatus.Stalled)
				task.Status = TaskStatus.Pending;
		}

		// Get the node index a task was assigned to (for checking connectivity with parent tasks)
		public int GetTaskNodeIndex(string taskId)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return -1;

			return task.AssignedNodeIndex;
		}

		// Get task dependencies as comma-separated string
		public string GetTaskDependencies(string taskId)
		{
			if (!dagTasks.TryGetValue(taskId, out var task))
				return "";

			return string.Join(",", task.Dependencies);
		}

		// Build adjacency list (parent → children) for visualization
		Dictionary<string, List<string>> BuildAdjacencyList()
		{
			var adjacency = new Dictionary<string, List<string>>();

			foreach (var task in dagTasks.Values)
			{
				// Initialize each task as potential parent
				if (!adjacency.ContainsKey(task.Id))
					adjacency[task.Id] = new List<string>();

				// Add this task as child to each of its dependencies (parents)
				foreach (var dep in task.Dependencies)
				{
					if (!adjacency.ContainsKey(dep))
						adjacency[dep] = new List<string>();
					adjacency[dep].Add(task.Id);
				}
			}

			return adjacency;
		}

		void UpdateTrackedActors()
		{
			trackedActors.Clear();
			computeNodeList.Clear();

			foreach (var actor in world.Actors)
			{
				if (actor.IsDead || !actor.IsInWorld)
					continue;

				// Track mobile units (infantry and vehicles)
				if (actor.Info.HasTraitInfo<MobileInfo>())
				{
					trackedActors.Add(actor);

					// Assign compute status if not already done
					if (!computeNodes.ContainsKey(actor))
					{
						var isInfantry = actor.Info.Name.ToLowerInvariant().StartsWith("e");
						var computeChance = isInfantry ? info.InfantryComputePercent : info.VehicleComputePercent;

						if (random.Next(100) < computeChance)
						{
							// Randomly assign high or low CPU (50/50)
							computeNodes[actor] = new ComputeNodeInfo
							{
								IsCompute = true,
								IsHighCpu = random.Next(2) == 0,
								NodeIndex = -1 // Will be assigned below
							};
						}
						else
						{
							computeNodes[actor] = new ComputeNodeInfo { IsCompute = false };
						}
					}

					// Build ordered compute node list
					if (computeNodes.TryGetValue(actor, out var nodeInfo) && nodeInfo.IsCompute)
					{
						nodeInfo.NodeIndex = computeNodeList.Count;
						computeNodeList.Add(actor);
					}
				}
			}

			// Clean up dead actors
			var deadActors = computeNodes.Keys.Where(a => a.IsDead || !a.IsInWorld).ToList();
			foreach (var dead in deadActors)
				computeNodes.Remove(dead);

			// Clean up active links with dead actors
			activeLinks.RemoveAll(l => l.From.IsDead || !l.From.IsInWorld || l.To.IsDead || !l.To.IsInWorld);
		}

		// Calculate data rate based on distance using square root curve for gradual dropoff
		double CalculateDataRate(double distance, double range)
		{
			if (distance >= range)
				return 0;

			var ratio = distance / range;
			var rate = info.MaxDataRate * (1.0 - Math.Sqrt(ratio));
			return Math.Max(0, rate);
		}

		// Get color for data rate: green (100) -> yellow (60) -> red (20)
		Color GetLinkColor(double rate, bool isActive)
		{
			if (isActive)
				return Color.FromArgb(255, 0, 255, 255); // Cyan for active links

			// Normalize rate to 0-1 range between MinDataRate and MaxDataRate
			var normalized = (rate - info.MinDataRate) / (info.MaxDataRate - info.MinDataRate);
			normalized = Math.Max(0, Math.Min(1, normalized));

			int r, g, b;
			if (normalized > 0.5)
			{
				var t = (normalized - 0.5) * 2;
				r = (int)(255 * (1 - t));
				g = 255;
				b = 0;
			}
			else
			{
				var t = normalized * 2;
				r = 255;
				g = (int)(255 * t);
				b = 0;
			}

			return Color.FromArgb(120, r, g, b); // More transparent for background links
		}

		bool IsActiveLink(Actor a, Actor b)
		{
			return activeLinks.Any(l =>
				(l.From == a && l.To == b) || (l.From == b && l.To == a));
		}

		IEnumerable<IRenderable> IRenderAnnotations.RenderAnnotations(Actor self, WorldRenderer wr)
		{
			if (!OverlayEnabled)
				yield break;

			if (!EnableLinks && !EnableComputeMarkers)
				yield break;

			var radiusInWorld = NetworkRadius * 1024;

			// Draw network links between nearby units
			if (EnableLinks)
			{
				for (var i = 0; i < trackedActors.Count; i++)
				{
					var actorA = trackedActors[i];
					if (actorA.IsDead || !actorA.IsInWorld)
						continue;

					for (var j = i + 1; j < trackedActors.Count; j++)
					{
						var actorB = trackedActors[j];
						if (actorB.IsDead || !actorB.IsInWorld)
							continue;

						var diff = actorA.CenterPosition - actorB.CenterPosition;
						var distSquared = (long)diff.X * diff.X + (long)diff.Y * diff.Y;
						var distance = Math.Sqrt(distSquared);

						var dataRate = CalculateDataRate(distance, radiusInWorld);

						if (dataRate >= info.MinDataRate)
						{
							var isActive = IsActiveLink(actorA, actorB);
							var linkColor = GetLinkColor(dataRate, isActive);
							var linkWidth = isActive ? info.ActiveLinkWidth : info.LinkWidth;

							yield return new IoBTLineRenderable(
								actorA.CenterPosition,
								actorB.CenterPosition,
								linkColor,
								linkWidth);
						}
					}
				}
			}

			// Draw compute point markers
			if (EnableComputeMarkers)
			{
				foreach (var actor in trackedActors)
				{
					if (actor.IsDead || !actor.IsInWorld)
						continue;

					if (computeNodes.TryGetValue(actor, out var nodeInfo) && nodeInfo.IsCompute)
					{
						// Blue for high CPU, Yellow for low CPU
						var cpuColor = nodeInfo.IsHighCpu
							? Color.FromArgb(220, 60, 120, 255)
							: Color.FromArgb(220, 255, 220, 60);

						yield return new IoBTFilledCircleRenderable(
							actor.CenterPosition,
							info.ComputeCircleRadius,
							cpuColor);

						// Show task ID if running a task
						if (!string.IsNullOrEmpty(nodeInfo.RunningTaskId))
						{
							yield return new IoBTTextRenderable(
								actor.CenterPosition + new WVec(0, -300, 0),
								nodeInfo.RunningTaskId,
								Color.White);
						}
						// Otherwise show node index
						else
						{
							yield return new IoBTTextRenderable(
								actor.CenterPosition + new WVec(0, -300, 0),
								$"C{nodeInfo.NodeIndex}",
								Color.FromArgb(180, 200, 200, 200));
						}
					}
				}
			}

			// Draw DAG status panel in top-left corner
			if (ShowDagStatus && dagTasks.Count > 0)
			{
				var yOffset = 50;

				// Section 1: DAG Structure (Adjacency List)
				yield return new IoBTScreenTextRenderable(
					new int2(10, yOffset),
					"DAG Structure:",
					Color.White);
				yOffset += 18;

				var adjacency = BuildAdjacencyList();
				foreach (var kvp in adjacency.OrderBy(k => k.Key))
				{
					if (kvp.Value.Count > 0)
					{
						var childrenStr = string.Join(", ", kvp.Value);
						yield return new IoBTScreenTextRenderable(
							new int2(20, yOffset),
							$"{kvp.Key}: {childrenStr}",
							Color.FromArgb(200, 180, 180, 180));
						yOffset += 14;
					}
				}

				yOffset += 8;

				// Section 2: Task Status
				yield return new IoBTScreenTextRenderable(
					new int2(10, yOffset),
					"Status:",
					Color.White);
				yOffset += 18;

				foreach (var task in dagTasks.Values.OrderBy(t => t.Id))
				{
					var statusColor = task.Status switch
					{
						TaskStatus.Pending => Color.Gray,
						TaskStatus.Running => Color.Cyan,
						TaskStatus.Completed => Color.Green,
						TaskStatus.Stalled => Color.Yellow,
						_ => Color.White
					};

					var statusLabel = task.Status switch
					{
						TaskStatus.Pending => "Wait",
						TaskStatus.Running => "Run",
						TaskStatus.Completed => "Done",
						TaskStatus.Stalled => "Stall",
						_ => "?"
					};

					var nodeLabel = task.AssignedNodeIndex >= 0 ? $"C{task.AssignedNodeIndex}" : "-";
					var activeMarker = task.Status == TaskStatus.Running ? " <--" : "";

					yield return new IoBTScreenTextRenderable(
						new int2(20, yOffset),
						$"{task.Id} [{statusLabel}] {nodeLabel}{activeMarker}",
						statusColor);
					yOffset += 14;
				}

				// Section 3: Active Transfers
				if (activeLinks.Count > 0)
				{
					yOffset += 8;
					yield return new IoBTScreenTextRenderable(
						new int2(10, yOffset),
						"Transfers:",
						Color.White);
					yOffset += 18;

					foreach (var link in activeLinks)
					{
						string transferLabel;
						if (!string.IsNullOrEmpty(link.SourceTaskId) && !string.IsNullOrEmpty(link.DestTaskId))
						{
							// Show as "T1→T4 (C0→C2)"
							transferLabel = $"{link.SourceTaskId}\u2192{link.DestTaskId} (C{link.FromNodeIndex}\u2192C{link.ToNodeIndex})";
						}
						else
						{
							// Fallback: just show node indices
							transferLabel = $"C{link.FromNodeIndex}\u2192C{link.ToNodeIndex}: {link.Label}";
						}

						yield return new IoBTScreenTextRenderable(
							new int2(20, yOffset),
							transferLabel,
							Color.Cyan);
						yOffset += 14;
					}
				}
			}
		}

		bool IRenderAnnotations.SpatiallyPartitionable => false;
	}

	public enum TaskStatus { Pending, Running, Completed, Stalled }

	public class DagTask
	{
		public string Id;
		public string Name;
		public string[] Dependencies;
		public TaskStatus Status;
		public Actor AssignedNode;
		public int AssignedNodeIndex = -1; // Store the node index for connectivity checks
	}

	public class ActiveLink
	{
		public Actor From;
		public Actor To;
		public string Label;
		public string SourceTaskId;  // Task sending data (e.g., "T1")
		public string DestTaskId;    // Task receiving data (e.g., "T4")
		public int FromNodeIndex;
		public int ToNodeIndex;
	}

	public class ComputeNodeInfo
	{
		public bool IsCompute;
		public bool IsHighCpu;
		public int NodeIndex;
		public string RunningTaskId;
	}

	// Line renderable for network links
	public class IoBTLineRenderable : IRenderable, IFinalizedRenderable
	{
		readonly WPos start;
		readonly WPos end;
		readonly Color color;
		readonly float width;

		public IoBTLineRenderable(WPos start, WPos end, Color color, float width)
		{
			this.start = start;
			this.end = end;
			this.color = color;
			this.width = width;
		}

		public WPos Pos => start;
		public int ZOffset => 0;
		public bool IsDecoration => true;

		public IRenderable WithZOffset(int newOffset) => this;
		public IRenderable OffsetBy(in WVec vec) => new IoBTLineRenderable(start + vec, end + vec, color, width);
		public IRenderable AsDecoration() => this;
		public IFinalizedRenderable PrepareRender(WorldRenderer wr) => this;

		public void Render(WorldRenderer wr)
		{
			var startScreen = wr.Viewport.WorldToViewPx(wr.Screen3DPosition(start));
			var endScreen = wr.Viewport.WorldToViewPx(wr.Screen3DPosition(end));
			Game.Renderer.RgbaColorRenderer.DrawLine(startScreen, endScreen, width, color);
		}

		public void RenderDebugGeometry(WorldRenderer wr) { }
		public Rectangle ScreenBounds(WorldRenderer wr) => Rectangle.Empty;
	}

	// Filled circle renderable
	public class IoBTFilledCircleRenderable : IRenderable, IFinalizedRenderable
	{
		readonly WPos pos;
		readonly int radius;
		readonly Color color;

		public IoBTFilledCircleRenderable(WPos pos, int radius, Color color)
		{
			this.pos = pos;
			this.radius = radius;
			this.color = color;
		}

		public WPos Pos => pos;
		public int ZOffset => 0;
		public bool IsDecoration => true;

		public IRenderable WithZOffset(int newOffset) => this;
		public IRenderable OffsetBy(in WVec vec) => new IoBTFilledCircleRenderable(pos + vec, radius, color);
		public IRenderable AsDecoration() => this;
		public IFinalizedRenderable PrepareRender(WorldRenderer wr) => this;

		public void Render(WorldRenderer wr)
		{
			var screenPos = wr.Viewport.WorldToViewPx(wr.Screen3DPosition(pos));
			var edgePos = pos + new WVec(radius, 0, 0);
			var screenEdge = wr.Viewport.WorldToViewPx(wr.Screen3DPosition(edgePos));
			var screenRadius = Math.Max(3, (int)Math.Sqrt(
				Math.Pow(screenEdge.X - screenPos.X, 2) +
				Math.Pow(screenEdge.Y - screenPos.Y, 2)));

			for (var r = screenRadius; r >= 0; r--)
				DrawCircle(screenPos, r, color);
		}

		void DrawCircle(int2 center, int r, Color c)
		{
			if (r <= 0)
			{
				Game.Renderer.RgbaColorRenderer.DrawLine(
					new float3(center.X, center.Y, 0),
					new float3(center.X + 1, center.Y, 0), 1, c);
				return;
			}

			const int segments = 12;
			var angleStep = 2 * Math.PI / segments;
			for (var i = 0; i < segments; i++)
			{
				var a1 = i * angleStep;
				var a2 = (i + 1) * angleStep;
				var p1 = new float3(center.X + (float)(r * Math.Cos(a1)), center.Y + (float)(r * Math.Sin(a1)), 0);
				var p2 = new float3(center.X + (float)(r * Math.Cos(a2)), center.Y + (float)(r * Math.Sin(a2)), 0);
				Game.Renderer.RgbaColorRenderer.DrawLine(p1, p2, 1, c);
			}
		}

		public void RenderDebugGeometry(WorldRenderer wr) { }
		public Rectangle ScreenBounds(WorldRenderer wr) => Rectangle.Empty;
	}

	// Text renderable for world-space labels
	public class IoBTTextRenderable : IRenderable, IFinalizedRenderable
	{
		readonly WPos pos;
		readonly string text;
		readonly Color color;

		public IoBTTextRenderable(WPos pos, string text, Color color)
		{
			this.pos = pos;
			this.text = text;
			this.color = color;
		}

		public WPos Pos => pos;
		public int ZOffset => 0;
		public bool IsDecoration => true;

		public IRenderable WithZOffset(int newOffset) => this;
		public IRenderable OffsetBy(in WVec vec) => new IoBTTextRenderable(pos + vec, text, color);
		public IRenderable AsDecoration() => this;
		public IFinalizedRenderable PrepareRender(WorldRenderer wr) => this;

		public void Render(WorldRenderer wr)
		{
			var screenPos = wr.Viewport.WorldToViewPx(wr.Screen3DPosition(pos));
			var font = Game.Renderer.Fonts["TinyBold"];
			var textSize = font.Measure(text);
			font.DrawText(text, new float2(screenPos.X - textSize.X / 2, screenPos.Y - textSize.Y / 2), color);
		}

		public void RenderDebugGeometry(WorldRenderer wr) { }
		public Rectangle ScreenBounds(WorldRenderer wr) => Rectangle.Empty;
	}

	// Screen-space text renderable for UI panels
	public class IoBTScreenTextRenderable : IRenderable, IFinalizedRenderable
	{
		readonly int2 screenPos;
		readonly string text;
		readonly Color color;

		public IoBTScreenTextRenderable(int2 screenPos, string text, Color color)
		{
			this.screenPos = screenPos;
			this.text = text;
			this.color = color;
		}

		public WPos Pos => WPos.Zero;
		public int ZOffset => 0;
		public bool IsDecoration => true;

		public IRenderable WithZOffset(int newOffset) => this;
		public IRenderable OffsetBy(in WVec vec) => this;
		public IRenderable AsDecoration() => this;
		public IFinalizedRenderable PrepareRender(WorldRenderer wr) => this;

		public void Render(WorldRenderer wr)
		{
			var font = Game.Renderer.Fonts["TinyBold"];
			font.DrawText(text, new float2(screenPos.X, screenPos.Y), color);
		}

		public void RenderDebugGeometry(WorldRenderer wr) { }
		public Rectangle ScreenBounds(WorldRenderer wr) => Rectangle.Empty;
	}
}
