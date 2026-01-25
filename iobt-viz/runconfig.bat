@echo off
REM IoBT-Viz Configuration Generator Launcher
REM Run this script to open the GUI for configuring IoBT simulations

start "IoBT Config" pythonw "%~dp0mods\iobt\tools\iobt_config_gui.py"
echo IoBT-Viz Config GUI launched.
echo You can now run: .\launch-game.cmd Mod=iobt
