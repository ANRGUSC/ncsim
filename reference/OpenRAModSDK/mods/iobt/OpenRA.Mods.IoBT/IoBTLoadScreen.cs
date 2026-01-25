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

using OpenRA.Graphics;
using OpenRA.Mods.Common.LoadScreens;
using OpenRA.Mods.Common.Widgets;
using OpenRA.Primitives;

namespace OpenRA.Mods.IoBT
{
	public sealed class IoBTLoadScreen : SheetLoadScreen
	{
		Rectangle stripeRect;
		Sprite stripe;

		Sheet lastSheet;
		int lastDensity;
		Size lastResolution;

		public override void DisplayInner(Renderer r, Sheet s, int density)
		{
			if (s != lastSheet || density != lastDensity)
			{
				lastSheet = s;
				lastDensity = density;
				// Only load the stripe, skip the logo (hammer/sickle)
				stripe = CreateSprite(s, density, new Rectangle(258, 0, 253, 256));
			}

			if (r.Resolution != lastResolution)
			{
				lastResolution = r.Resolution;
				stripeRect = new Rectangle(0, lastResolution.Height / 2 - 128, lastResolution.Width, 256);
			}

			// Draw only the stripe background (no logo)
			if (stripe != null)
				WidgetUtils.FillRectWithSprite(stripeRect, stripe);

			if (r.Fonts != null)
			{
				// Draw "Loading IoBT-Viz..." centered
				var loadingText = "Loading IoBT-Viz...";
				var loadingSize = r.Fonts["Bold"].Measure(loadingText);
				var loadingPos = new float2(
					(r.Resolution.Width - loadingSize.X) / 2,
					(r.Resolution.Height - loadingSize.Y) / 2);
				r.Fonts["Bold"].DrawText(loadingText, loadingPos, Color.White);

				// Draw "ANRG, USC, 2026" at bottom center
				var creditText = "ANRG, USC, 2026";
				var creditSize = r.Fonts["Bold"].Measure(creditText);
				var creditPos = new float2(
					(r.Resolution.Width - creditSize.X) / 2,
					r.Resolution.Height - creditSize.Y - 20);
				r.Fonts["Bold"].DrawText(creditText, creditPos, Color.White);
			}
		}
	}
}
