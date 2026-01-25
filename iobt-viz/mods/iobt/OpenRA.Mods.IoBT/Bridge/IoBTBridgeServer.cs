#region Copyright & License Information
/*
 * IoBT Bridge Server
 * TCP server for external simulator communication (ncsim, SAGA scheduler, etc.)
 * Uses newline-delimited JSON protocol for simplicity
 * Port: 9999 (configurable)
 */
#endregion

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace OpenRA.Mods.IoBT.Bridge
{
	/// <summary>
	/// TCP server that listens for external simulator connections.
	/// Protocol: Newline-delimited JSON (\n terminated).
	/// Default port: 9999
	/// </summary>
	public class IoBTBridgeServer : IDisposable
	{
		public const int DefaultPort = 9999;

		readonly int port;
		readonly ConcurrentDictionary<int, BridgeConnection> connections = new();
		TcpListener listener;
		CancellationTokenSource cts;
		Task acceptTask;
		int nextConnectionId;
		bool disposed;

		/// <summary>Event fired when a message is received from any client.</summary>
		public event Action<int, BridgeMessage> MessageReceived;

		/// <summary>Event fired when a client connects.</summary>
		public event Action<int> ClientConnected;

		/// <summary>Event fired when a client disconnects.</summary>
		public event Action<int> ClientDisconnected;

		public bool IsRunning => listener != null && !disposed;
		public int ConnectionCount => connections.Count;

		public IoBTBridgeServer(int port = DefaultPort)
		{
			this.port = port;
		}

		/// <summary>Start the bridge server.</summary>
		public void Start()
		{
			if (disposed)
				throw new ObjectDisposedException(nameof(IoBTBridgeServer));

			if (listener != null)
				return; // Already started

			try
			{
				listener = new TcpListener(IPAddress.Any, port);
				listener.Start();
				cts = new CancellationTokenSource();

				Log.Write("debug", $"IoBT Bridge Server started on port {port}");

				// Start accepting connections in background
				acceptTask = AcceptConnectionsAsync(cts.Token);
			}
			catch (Exception ex)
			{
				Log.Write("debug", $"Failed to start bridge server: {ex.Message}");
				throw;
			}
		}

		/// <summary>Stop the bridge server.</summary>
		public void Stop()
		{
			if (disposed || listener == null)
				return;

			Log.Write("debug", "IoBT Bridge Server stopping...");

			cts?.Cancel();

			// Close all client connections
			foreach (var conn in connections.Values)
				conn.Dispose();
			connections.Clear();

			// Stop listener
			try
			{
				listener.Stop();
			}
			catch (Exception ex)
			{
				Log.Write("debug", $"Error stopping listener: {ex.Message}");
			}

			listener = null;
			Log.Write("debug", "IoBT Bridge Server stopped");
		}

		async Task AcceptConnectionsAsync(CancellationToken token)
		{
			while (!token.IsCancellationRequested)
			{
				try
				{
					var client = await listener.AcceptTcpClientAsync();
					var connId = Interlocked.Increment(ref nextConnectionId);

					var connection = new BridgeConnection(connId, client, this);
					connections[connId] = connection;

					Log.Write("debug", $"Client {connId} connected from {client.Client.RemoteEndPoint}");
					ClientConnected?.Invoke(connId);

					// Start reading from this connection
					_ = connection.StartReadingAsync(token);
				}
				catch (ObjectDisposedException)
				{
					// Listener was stopped
					break;
				}
				catch (SocketException) when (token.IsCancellationRequested)
				{
					// Expected during shutdown
					break;
				}
				catch (Exception ex)
				{
					if (!token.IsCancellationRequested)
						Log.Write("debug", $"Error accepting connection: {ex.Message}");
				}
			}
		}

		/// <summary>Send a message to a specific client.</summary>
		public void SendMessage(int connectionId, BridgeMessage message)
		{
			if (connections.TryGetValue(connectionId, out var conn))
				conn.SendMessage(message);
		}

		/// <summary>Send a message to all connected clients.</summary>
		public void BroadcastMessage(BridgeMessage message)
		{
			foreach (var conn in connections.Values)
				conn.SendMessage(message);
		}

		internal void OnMessageReceived(int connectionId, BridgeMessage message)
		{
			Log.Write("debug", $"Received from client {connectionId}: type={message.Type}");
			MessageReceived?.Invoke(connectionId, message);
		}

		internal void OnConnectionClosed(int connectionId)
		{
			if (connections.TryRemove(connectionId, out _))
			{
				Log.Write("debug", $"Client {connectionId} disconnected");
				ClientDisconnected?.Invoke(connectionId);
			}
		}

		public void Dispose()
		{
			if (disposed)
				return;

			disposed = true;
			Stop();
			cts?.Dispose();
		}
	}

	/// <summary>
	/// Represents a single client connection to the bridge.
	/// </summary>
	public class BridgeConnection : IDisposable
	{
		readonly int id;
		readonly TcpClient client;
		readonly IoBTBridgeServer server;
		readonly NetworkStream stream;
		readonly StreamReader reader;
		readonly StreamWriter writer;
		readonly object writeLock = new();
		bool disposed;

		public int Id => id;
		public bool IsConnected => client?.Connected ?? false;

		public BridgeConnection(int id, TcpClient client, IoBTBridgeServer server)
		{
			this.id = id;
			this.client = client;
			this.server = server;
			stream = client.GetStream();
			reader = new StreamReader(stream, Encoding.UTF8);
			writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };
		}

		public async Task StartReadingAsync(CancellationToken token)
		{
			try
			{
				while (!token.IsCancellationRequested && client.Connected)
				{
					var line = await reader.ReadLineAsync();
					if (line == null)
						break; // Connection closed

					try
					{
						var message = BridgeMessage.Parse(line);
						if (message != null)
							server.OnMessageReceived(id, message);
					}
					catch (JsonException ex)
					{
						Log.Write("debug", $"Invalid JSON from client {id}: {ex.Message}");
						// Send error response
						SendMessage(new BridgeMessage
						{
							Type = "error",
							Data = new Dictionary<string, object>
							{
								["message"] = "Invalid JSON format",
								["details"] = ex.Message
							}
						});
					}
				}
			}
			catch (IOException)
			{
				// Connection closed
			}
			catch (Exception ex)
			{
				if (!token.IsCancellationRequested)
					Log.Write("debug", $"Error reading from client {id}: {ex.Message}");
			}
			finally
			{
				server.OnConnectionClosed(id);
				Dispose();
			}
		}

		public void SendMessage(BridgeMessage message)
		{
			if (disposed || !client.Connected)
				return;

			try
			{
				var json = message.ToJson();
				lock (writeLock)
				{
					writer.WriteLine(json);
				}
			}
			catch (Exception ex)
			{
				Log.Write("debug", $"Error sending to client {id}: {ex.Message}");
			}
		}

		public void Dispose()
		{
			if (disposed)
				return;

			disposed = true;
			reader?.Dispose();
			writer?.Dispose();
			stream?.Dispose();
			client?.Dispose();
		}
	}

	/// <summary>
	/// Bridge protocol message (newline-delimited JSON).
	/// </summary>
	public class BridgeMessage
	{
		public string Type { get; set; }
		public Dictionary<string, object> Data { get; set; }

		public BridgeMessage()
		{
			Data = new Dictionary<string, object>();
		}

		public static BridgeMessage Parse(string json)
		{
			using var doc = JsonDocument.Parse(json);
			var root = doc.RootElement;

			var message = new BridgeMessage();

			if (root.TryGetProperty("type", out var typeElement))
				message.Type = typeElement.GetString();

			// Parse other properties into Data dictionary
			foreach (var prop in root.EnumerateObject())
			{
				if (prop.Name == "type")
					continue;

				message.Data[prop.Name] = ParseJsonElement(prop.Value);
			}

			return message;
		}

		static object ParseJsonElement(JsonElement element)
		{
			return element.ValueKind switch
			{
				JsonValueKind.String => element.GetString(),
				JsonValueKind.Number => element.TryGetInt64(out var l) ? l : element.GetDouble(),
				JsonValueKind.True => true,
				JsonValueKind.False => false,
				JsonValueKind.Null => null,
				JsonValueKind.Array => ParseJsonArray(element),
				JsonValueKind.Object => ParseJsonObject(element),
				_ => element.GetRawText()
			};
		}

		static List<object> ParseJsonArray(JsonElement element)
		{
			var list = new List<object>();
			foreach (var item in element.EnumerateArray())
				list.Add(ParseJsonElement(item));
			return list;
		}

		static Dictionary<string, object> ParseJsonObject(JsonElement element)
		{
			var dict = new Dictionary<string, object>();
			foreach (var prop in element.EnumerateObject())
				dict[prop.Name] = ParseJsonElement(prop.Value);
			return dict;
		}

		public string ToJson()
		{
			var options = new JsonSerializerOptions
			{
				WriteIndented = false
			};

			var dict = new Dictionary<string, object>(Data)
			{
				["type"] = Type
			};

			return JsonSerializer.Serialize(dict, options);
		}

		/// <summary>Create a simple response message.</summary>
		public static BridgeMessage CreateResponse(string type, string status, object data = null)
		{
			var msg = new BridgeMessage { Type = type };
			msg.Data["status"] = status;
			if (data != null)
				msg.Data["data"] = data;
			return msg;
		}

		/// <summary>Create a pong response to a ping.</summary>
		public static BridgeMessage CreatePong()
		{
			return new BridgeMessage
			{
				Type = "pong",
				Data = new Dictionary<string, object>
				{
					["timestamp"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
				}
			};
		}
	}
}
