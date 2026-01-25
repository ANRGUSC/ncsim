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
				// Check for 'n' key press (lowercase)
				if (e.Event == KeyInputEvent.Down && e.Key == Keycode.N && !e.IsRepeat)
				{
					// Don't trigger if any modifiers are held
					if (e.Modifiers != Modifiers.None)
						return false;

					// Find the network overlay and toggle it
					var overlay = world.WorldActor.TraitOrDefault<IoBTNetworkOverlay>();
					if (overlay != null)
					{
						overlay.Toggle();
						var status = overlay.OverlayEnabled ? "ON" : "OFF";
						TextNotificationsManager.Debug($"IoBT Network Overlay: {status}");
						return true;
					}
				}

				return false;
			});
		}
	}
}
