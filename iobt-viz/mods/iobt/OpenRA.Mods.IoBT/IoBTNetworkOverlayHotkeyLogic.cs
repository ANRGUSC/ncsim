#region Copyright & License Information
/*
 * Copyright (c) The OpenRA Developers and Contributors
 * This file is part of OpenRA, which is free software. It is made
 * available to you under the terms of the GNU General Public License
 * as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version. For more
 * information, see COPYING.
 */
#endregion

using OpenRA.Mods.Common.Widgets;
using OpenRA.Widgets;

namespace OpenRA.Mods.IoBT
{
	public class IoBTNetworkOverlayHotkeyLogic : ChromeLogic
	{
		[ObjectCreator.UseCtor]
		public IoBTNetworkOverlayHotkeyLogic(Widget widget, World world)
		{
			var keyHandler = widget.Get<LogicKeyListenerWidget>("IOBT_KEYHANDLER");
			keyHandler.AddHandler(e =>
			{
				if (e.Event != KeyInputEvent.Down || e.IsRepeat || e.Modifiers != Modifiers.None)
					return false;

				var overlay = world.WorldActor.TraitOrDefault<IoBTNetworkOverlay>();
				if (overlay == null)
					return false;

				// 'N' key: toggle network overlay
				if (e.Key == Keycode.N)
				{
					overlay.Toggle();
					var status = overlay.OverlayEnabled ? "ON" : "OFF";
					TextNotificationsManager.Debug($"IoBT Network Overlay: {status}");
					return true;
				}

				// 'B' key: Baseline mode (stall on partition)
				if (e.Key == Keycode.B)
				{
					overlay.ResilienceMode = "B";
					TextNotificationsManager.Debug("Mode: Baseline (tasks stall on partition)");
					return true;
				}

				// 'S' key: Smart mode (reassign stalled tasks in partition)
				if (e.Key == Keycode.S)
				{
					overlay.ResilienceMode = "S";
					TextNotificationsManager.Debug("Mode: Smart (reassign stalled tasks in partition)");
					return true;
				}

				// 'H' key: HEFT restart mode (restart HEFT on largest partition)
				if (e.Key == Keycode.H)
				{
					overlay.ResilienceMode = "H";
					TextNotificationsManager.Debug("Mode: HEFT-Restart (restart DAG on largest partition)");
					return true;
				}

				// 'R' key: Restart simulation (reset map)
				if (e.Key == Keycode.R)
				{
					TextNotificationsManager.Debug("Restarting simulation...");
					// Delay slightly to allow message to display
					Game.RunAfterTick(() =>
					{
						var map = world.Map.Uid;
						Game.RestartGame();
					});
					return true;
				}

				// 'Q' key: Quit application
				if (e.Key == Keycode.Q)
				{
					TextNotificationsManager.Debug("Quitting...");
					Game.Exit();
					return true;
				}

				return false;
			});
		}
	}
}
