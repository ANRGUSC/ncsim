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

using System.Linq;
using OpenRA.Widgets;

namespace OpenRA.Mods.IoBT
{
	public class IoBTMainMenuLogic : ChromeLogic
	{
		readonly Widget rootMenu;
		readonly ModData modData;

		[ObjectCreator.UseCtor]
		public IoBTMainMenuLogic(Widget widget, World world, ModData modData)
		{
			this.modData = modData;
			rootMenu = widget;

			// Auto-start directly into the map
			Game.RunAfterTick(AutoStartGame);
		}

		void AutoStartGame()
		{
			// Find the iobt-sim map (200 units demo that's known to work)
			var mapPreview = modData.MapCache
				.Where(m => m.Status == MapStatus.Available &&
					m.Title != null &&
					(m.Title.Contains("200 Units") || m.Uid.Contains("iobt-sim")))
				.FirstOrDefault();

			// Fallback to iobt-demo2
			mapPreview ??= modData.MapCache
				.Where(m => m.Status == MapStatus.Available &&
					m.Title != null &&
					(m.Title.Contains("Small Scale") || m.Uid.Contains("iobt-demo2")))
				.FirstOrDefault();

			// Fallback: try to find any map with "IoBT" in the title
			mapPreview ??= modData.MapCache
				.Where(m => m.Status == MapStatus.Available &&
					m.Title != null &&
					m.Title.IndexOf("iobt", System.StringComparison.OrdinalIgnoreCase) >= 0)
				.FirstOrDefault();

			// Final fallback: just use the first available lobby map
			mapPreview ??= modData.MapCache
				.Where(m => m.Status == MapStatus.Available && m.Visibility.HasFlag(MapVisibility.Lobby))
				.FirstOrDefault();

			if (mapPreview == null)
			{
				Log.Write("debug", "IoBT: No suitable map found for auto-start");
				return;
			}

			var mapUid = mapPreview.Uid;
			Log.Write("debug", $"IoBT: Auto-starting game with map: {mapPreview.Title} ({mapUid})");

			// Remove the menu UI
			rootMenu.Parent?.RemoveChild(rootMenu);

			// Start the game using Game.LoadMap which handles all the setup
			Game.LoadMap(mapUid);
		}
	}
}
