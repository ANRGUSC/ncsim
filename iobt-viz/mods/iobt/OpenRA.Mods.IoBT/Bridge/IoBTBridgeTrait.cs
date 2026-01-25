#region Copyright & License Information
/*
 * IoBT Bridge Trait
 * Attaches the bridge server to the World actor
 * Handles message routing between external simulators and iobt-viz
 */
#endregion

using System;
using System.Collections.Generic;
using System.Linq;
using OpenRA.Graphics;
using OpenRA.Mods.Common.Traits;
using OpenRA.Traits;

namespace OpenRA.Mods.IoBT.Bridge
{
	[TraitLocation(SystemActors.World)]
	[Desc("Provides bridge server for external simulator communication (SAGA scheduler, ncsim, etc.).")]
	public class IoBTBridgeInfo : TraitInfo
	{
		[Desc("TCP port for the bridge server.")]
		public readonly int Port = 9999;

		[Desc("Whether to auto-start the bridge when the world loads.")]
		public readonly bool AutoStart = true;

		public override object Create(ActorInitializer init) { return new IoBTBridge(init.Self, this); }
	}

	public class IoBTBridge : IWorldLoaded, INotifyActorDisposing, ITick
	{
		readonly IoBTBridgeInfo info;
		readonly World world;
		IoBTBridgeServer server;
		IoBTNetworkOverlay overlay;

		// Pending messages to process on game thread
		readonly Queue<(int connectionId, BridgeMessage message)> pendingMessages = new();
		readonly object messageLock = new();

		// SAGA schedule response tracking (for Lua polling)
		bool scheduleResponsePending;
		readonly Dictionary<string, int> pendingAssignments = new();
		readonly object scheduleLock = new();

		public bool IsRunning => server?.IsRunning ?? false;
		public int ConnectionCount => server?.ConnectionCount ?? 0;

		/// <summary>Check if a SAGA schedule response is pending (for Lua polling).</summary>
		public bool HasPendingSchedule
		{
			get
			{
				lock (scheduleLock)
					return scheduleResponsePending;
			}
		}

		/// <summary>Get and clear pending assignments (returns copy).</summary>
		public Dictionary<string, int> GetAndClearPendingAssignments()
		{
			lock (scheduleLock)
			{
				var copy = new Dictionary<string, int>(pendingAssignments);
				pendingAssignments.Clear();
				scheduleResponsePending = false;
				return copy;
			}
		}

		/// <summary>Clear the pending schedule flag without getting assignments.</summary>
		public void ClearPendingSchedule()
		{
			lock (scheduleLock)
			{
				scheduleResponsePending = false;
				pendingAssignments.Clear();
			}
		}

		public IoBTBridge(Actor self, IoBTBridgeInfo info)
		{
			this.info = info;
			world = self.World;
		}

		void IWorldLoaded.WorldLoaded(World w, WorldRenderer wr)
		{
			// Get reference to the network overlay
			overlay = w.WorldActor.TraitOrDefault<IoBTNetworkOverlay>();

			if (info.AutoStart)
				StartServer();

			Log.Write("debug", "IoBT Bridge trait loaded");
		}

		public void StartServer()
		{
			if (server != null)
				return;

			server = new IoBTBridgeServer(info.Port);
			server.MessageReceived += OnMessageReceived;
			server.ClientConnected += OnClientConnected;
			server.ClientDisconnected += OnClientDisconnected;

			try
			{
				server.Start();
			}
			catch (Exception ex)
			{
				Log.Write("debug", $"Failed to start bridge server: {ex.Message}");
				server.Dispose();
				server = null;
			}
		}

		public void StopServer()
		{
			if (server == null)
				return;

			server.MessageReceived -= OnMessageReceived;
			server.ClientConnected -= OnClientConnected;
			server.ClientDisconnected -= OnClientDisconnected;
			server.Stop();
			server.Dispose();
			server = null;
		}

		void OnClientConnected(int connectionId)
		{
			Log.Write("debug", $"Bridge client {connectionId} connected");

			// Send welcome message with current state
			var welcome = new BridgeMessage
			{
				Type = "welcome",
				Data = new Dictionary<string, object>
				{
					["server"] = "iobt-viz",
					["version"] = "1.0",
					["protocol"] = "newline-json",
					["compute_nodes"] = overlay?.GetComputeNodeCount() ?? 0
				}
			};
			server.SendMessage(connectionId, welcome);
		}

		void OnClientDisconnected(int connectionId)
		{
			Log.Write("debug", $"Bridge client {connectionId} disconnected");
		}

		void OnMessageReceived(int connectionId, BridgeMessage message)
		{
			// Queue message for processing on game thread
			lock (messageLock)
			{
				pendingMessages.Enqueue((connectionId, message));
			}
		}

		void ITick.Tick(Actor self)
		{
			// Process pending messages on game thread
			while (true)
			{
				(int connectionId, BridgeMessage message) item;
				lock (messageLock)
				{
					if (pendingMessages.Count == 0)
						break;
					item = pendingMessages.Dequeue();
				}

				ProcessMessage(item.connectionId, item.message);
			}
		}

		void ProcessMessage(int connectionId, BridgeMessage message)
		{
			try
			{
				System.Console.WriteLine($"[BRIDGE] Processing message: {message.Type}");
				switch (message.Type?.ToLowerInvariant())
				{
					case "ping":
						HandlePing(connectionId, message);
						break;

					case "hello":
						HandleHello(connectionId, message);
						break;

					case "get_state":
						HandleGetState(connectionId, message);
						break;

					case "schedule_request":
						HandleScheduleRequest(connectionId, message);
						break;

					case "schedule_response":
						HandleScheduleResponse(connectionId, message);
						break;

					case "apply_schedule":
						HandleApplySchedule(connectionId, message);
						break;

					default:
						Log.Write("debug", $"Unknown message type: {message.Type}");
						SendError(connectionId, $"Unknown message type: {message.Type}");
						break;
				}
			}
			catch (Exception ex)
			{
				Log.Write("debug", $"Error processing message: {ex.Message}");
				SendError(connectionId, ex.Message);
			}
		}

		void HandlePing(int connectionId, BridgeMessage message)
		{
			server.SendMessage(connectionId, BridgeMessage.CreatePong());
		}

		void HandleHello(int connectionId, BridgeMessage message)
		{
			// Acknowledge client identification
			var client = message.Data?.ContainsKey("client") == true ? message.Data["client"]?.ToString() : "unknown";
			var algorithm = message.Data?.ContainsKey("algorithm") == true ? message.Data["algorithm"]?.ToString() : "unknown";
			Log.Write("debug", $"Client {connectionId} identified: {client} (algorithm: {algorithm})");

			// Send acknowledgment
			var ack = new BridgeMessage();
			ack.Type = "hello_ack";
			ack.Data["status"] = "ok";
			ack.Data["message"] = $"Welcome {client}";
			server.SendMessage(connectionId, ack);
		}

		void HandleGetState(int connectionId, BridgeMessage message)
		{
			// Return current network and DAG state for SAGA scheduler
			var state = new Dictionary<string, object>
			{
				["compute_nodes"] = overlay?.GetComputeNodeCount() ?? 0,
				["overlay_enabled"] = overlay?.OverlayEnabled ?? false,
				["network_radius"] = overlay?.NetworkRadius ?? 0,
				["world_tick"] = world.WorldTick
			};

			// Build connectivity matrix for compute nodes
			var nodeCount = overlay?.GetComputeNodeCount() ?? 0;
			var connectivity = new List<List<bool>>();
			for (var i = 0; i < nodeCount; i++)
			{
				var row = new List<bool>();
				for (var j = 0; j < nodeCount; j++)
				{
					row.Add(overlay?.AreNodesConnected(i, j) ?? false);
				}
				connectivity.Add(row);
			}
			state["connectivity"] = connectivity;

			server.SendMessage(connectionId, new BridgeMessage
			{
				Type = "state",
				Data = state
			});
		}

		void HandleScheduleRequest(int connectionId, BridgeMessage message)
		{
			// This is sent FROM iobt-viz TO the SAGA scheduler service
			// Build network topology and DAG info for external scheduler
			var nodeCount = overlay?.GetComputeNodeCount() ?? 0;

			// Build adjacency/connectivity info
			var connectivity = new List<List<bool>>();
			for (var i = 0; i < nodeCount; i++)
			{
				var row = new List<bool>();
				for (var j = 0; j < nodeCount; j++)
					row.Add(overlay?.AreNodesConnected(i, j) ?? false);
				connectivity.Add(row);
			}

			// Forward the request with added state
			var request = new BridgeMessage
			{
				Type = "schedule_request",
				Data = new Dictionary<string, object>(message.Data)
				{
					["compute_nodes"] = nodeCount,
					["connectivity"] = connectivity
				}
			};

			// Broadcast to all scheduler clients (or could target specific one)
			server.BroadcastMessage(request);
		}

		void HandleScheduleResponse(int connectionId, BridgeMessage message)
		{
			// Received FROM SAGA scheduler service
			// Contains task→node assignments
			Log.Write("debug", "Received schedule response from SAGA scheduler");
			System.Console.WriteLine("[BRIDGE] Received schedule_response from SAGA");

			if (!message.Data.TryGetValue("assignments", out var assignmentsObj))
			{
				Log.Write("debug", "Schedule response missing 'assignments' field");
				System.Console.WriteLine("[BRIDGE] ERROR: schedule_response missing 'assignments' field");
				return;
			}

			// Store assignments for Lua polling (one-shot scheduling mode)
			StoreScheduleResponse(assignmentsObj);
			System.Console.WriteLine($"[BRIDGE] Stored {pendingAssignments.Count} assignments, pending={scheduleResponsePending}");

			// Also apply immediately to overlay for visual update
			ApplySchedule(assignmentsObj);
		}

		void StoreScheduleResponse(object assignmentsObj)
		{
			lock (scheduleLock)
			{
				pendingAssignments.Clear();

				System.Console.WriteLine($"[BRIDGE] StoreScheduleResponse: assignmentsObj type = {assignmentsObj?.GetType()?.FullName ?? "null"}");

				// Parse assignments (task_id → node_index)
				if (assignmentsObj is Dictionary<string, object> assignments)
				{
					System.Console.WriteLine($"[BRIDGE] Parsing {assignments.Count} assignments from Dictionary<string,object>");
					foreach (var kvp in assignments)
					{
						var taskId = kvp.Key;
						System.Console.WriteLine($"[BRIDGE] Assignment {taskId}: value type = {kvp.Value?.GetType()?.FullName ?? "null"}, value = {kvp.Value}");
						if (kvp.Value is long nodeIndex)
						{
							pendingAssignments[taskId] = (int)nodeIndex;
							Log.Write("debug", $"Stored assignment: {taskId} -> node {nodeIndex}");
							System.Console.WriteLine($"[BRIDGE] Stored (long): {taskId} -> {nodeIndex}");
						}
						else if (kvp.Value is int nodeIndexInt)
						{
							pendingAssignments[taskId] = nodeIndexInt;
							Log.Write("debug", $"Stored assignment: {taskId} -> node {nodeIndexInt}");
							System.Console.WriteLine($"[BRIDGE] Stored (int): {taskId} -> {nodeIndexInt}");
						}
						else if (kvp.Value is double nodeIndexDouble)
						{
							pendingAssignments[taskId] = (int)nodeIndexDouble;
							Log.Write("debug", $"Stored assignment: {taskId} -> node {(int)nodeIndexDouble}");
							System.Console.WriteLine($"[BRIDGE] Stored (double): {taskId} -> {(int)nodeIndexDouble}");
						}
						else
						{
							System.Console.WriteLine($"[BRIDGE] SKIPPED: {taskId} - value type not recognized");
						}
					}
				}
				else
				{
					System.Console.WriteLine($"[BRIDGE] assignmentsObj is NOT Dictionary<string,object>");
				}

				scheduleResponsePending = true;
				Log.Write("debug", $"Schedule response stored: {pendingAssignments.Count} assignments pending");
			}
		}

		void HandleApplySchedule(int connectionId, BridgeMessage message)
		{
			// Direct command to apply a schedule
			if (message.Data.TryGetValue("assignments", out var assignmentsObj))
				ApplySchedule(assignmentsObj);
		}

		void ApplySchedule(object assignmentsObj)
		{
			if (overlay == null)
			{
				Log.Write("debug", "Cannot apply schedule: overlay not available");
				return;
			}

			// Parse assignments (task_id → node_index)
			if (assignmentsObj is Dictionary<string, object> assignments)
			{
				foreach (var kvp in assignments)
				{
					var taskId = kvp.Key;
					if (kvp.Value is long nodeIndex)
					{
						Log.Write("debug", $"Assigning task {taskId} to node {nodeIndex}");
						overlay.AssignTask(taskId, (int)nodeIndex);
					}
					else if (kvp.Value is int nodeIndexInt)
					{
						Log.Write("debug", $"Assigning task {taskId} to node {nodeIndexInt}");
						overlay.AssignTask(taskId, nodeIndexInt);
					}
					else if (kvp.Value is double nodeIndexDouble)
					{
						Log.Write("debug", $"Assigning task {taskId} to node {(int)nodeIndexDouble}");
						overlay.AssignTask(taskId, (int)nodeIndexDouble);
					}
				}
			}
		}

		void SendError(int connectionId, string errorMessage)
		{
			server?.SendMessage(connectionId, new BridgeMessage
			{
				Type = "error",
				Data = new Dictionary<string, object>
				{
					["message"] = errorMessage
				}
			});
		}

		/// <summary>Send a schedule request to connected SAGA scheduler.</summary>
		public void RequestSchedule(Dictionary<string, object> dagInfo)
		{
			if (server == null || !server.IsRunning)
			{
				Log.Write("debug", "Cannot request schedule: bridge not running");
				return;
			}

			var request = new BridgeMessage
			{
				Type = "schedule_request",
				Data = dagInfo
			};

			server.BroadcastMessage(request);
		}

		void INotifyActorDisposing.Disposing(Actor self)
		{
			StopServer();
		}
	}
}
