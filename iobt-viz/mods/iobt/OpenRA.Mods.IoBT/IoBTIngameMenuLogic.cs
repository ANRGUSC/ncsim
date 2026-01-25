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

using System;
using System.Collections.Generic;
using System.Linq;
using OpenRA.Graphics;
using OpenRA.Mods.Common.Traits;
using OpenRA.Mods.Common.Widgets;
using OpenRA.Mods.Common.Widgets.Logic;
using OpenRA.Widgets;

namespace OpenRA.Mods.IoBT
{
	/// <summary>
	/// Simplified ingame menu for IoBT visualization.
	/// Provides Resume, Settings, and Quit buttons.
	/// </summary>
	public class IoBTIngameMenuLogic : ChromeLogic
	{
		readonly Widget menu;
		readonly Widget buttonContainer;
		readonly ButtonWidget buttonTemplate;
		readonly int2 buttonStride;
		readonly List<ButtonWidget> buttons = new();

		readonly ModData modData;
		readonly Action onExit;
		readonly World world;
		readonly WorldRenderer worldRenderer;
		readonly MenuPostProcessEffect mpe;

		[ObjectCreator.UseCtor]
		public IoBTIngameMenuLogic(Widget widget, ModData modData, World world, Action onExit, WorldRenderer worldRenderer,
			IngameInfoPanel initialPanel, Dictionary<string, MiniYaml> logicArgs)
		{
			this.modData = modData;
			this.world = world;
			this.worldRenderer = worldRenderer;
			this.onExit = onExit;

			var buttonHandlers = new Dictionary<string, Action>
			{
				{ "RESUME", CreateResumeButton },
				{ "SETTINGS", CreateSettingsButton },
				{ "QUIT", CreateQuitButton },
			};

			menu = widget.Get("INGAME_MENU");
			mpe = world.WorldActor.TraitOrDefault<MenuPostProcessEffect>();
			mpe?.Fade(mpe.Info.MenuEffect);

			buttonContainer = menu.Get("MENU_BUTTONS");
			buttonTemplate = buttonContainer.Get<ButtonWidget>("BUTTON_TEMPLATE");
			buttonContainer.RemoveChild(buttonTemplate);

			if (logicArgs.TryGetValue("ButtonStride", out var buttonStrideNode))
				buttonStride = FieldLoader.GetValue<int2>("ButtonStride", buttonStrideNode.Value);

			if (logicArgs.TryGetValue("Buttons", out var buttonsNode))
			{
				var buttonIds = FieldLoader.GetValue<string[]>("Buttons", buttonsNode.Value);
				foreach (var button in buttonIds)
					if (buttonHandlers.TryGetValue(button, out var createHandler))
						createHandler();
			}

			// Recenter the button container
			if (buttons.Count > 0)
			{
				var expand = (buttons.Count - 1) * buttonStride;
				buttonContainer.Bounds.X -= expand.X / 2;
				buttonContainer.Bounds.Y -= expand.Y / 2;
				buttonContainer.Bounds.Width += expand.X;
				buttonContainer.Bounds.Height += expand.Y;
			}
		}

		void CloseMenu()
		{
			Ui.CloseWindow();
			mpe?.Fade(MenuPostProcessEffect.EffectType.None);
			onExit();
			Ui.ResetTooltips();
		}

		ButtonWidget AddButton(string id, string label)
		{
			var button = buttonTemplate.Clone() as ButtonWidget;
			var lastButton = buttons.LastOrDefault();
			if (lastButton != null)
			{
				button.Bounds.X = lastButton.Bounds.X + buttonStride.X;
				button.Bounds.Y = lastButton.Bounds.Y + buttonStride.Y;
			}

			button.Id = id;
			button.GetText = () => label;
			buttonContainer.AddChild(button);
			buttons.Add(button);

			return button;
		}

		void CreateResumeButton()
		{
			var button = AddButton("RESUME", "Resume");
			button.Key = modData.Hotkeys["escape"];
			button.OnClick = CloseMenu;
		}

		void CreateSettingsButton()
		{
			var button = AddButton("SETTINGS", "Settings");
			button.OnClick = () =>
			{
				Ui.OpenWindow("SETTINGS_PANEL", new WidgetArgs()
				{
					{ "world", world },
					{ "worldRenderer", worldRenderer },
					{ "onExit", () => { } },
				});
			};
		}

		void CreateQuitButton()
		{
			var button = AddButton("QUIT", "Quit");
			button.OnClick = () =>
			{
				// Exit the application directly
				Game.Exit();
			};
		}
	}
}
