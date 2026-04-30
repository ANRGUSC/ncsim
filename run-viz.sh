#!/bin/sh
# Launch iobt-viz on macOS
# Requires .NET 6.0 runtime in ~/.dotnet

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VIZ_DIR="$SCRIPT_DIR/iobt-viz"
ENGINE_DIR="$VIZ_DIR/engine"

export DOTNET_ROOT="$HOME/.dotnet"
DOTNET="$DOTNET_ROOT/dotnet"

if [ ! -f "$DOTNET" ]; then
    echo "Error: dotnet not found at $DOTNET"
    echo "Install .NET 6.0 runtime: https://dot.net/v1/dotnet-install.sh --channel 6.0 --runtime dotnet --install-dir ~/.dotnet"
    exit 1
fi

cd "$ENGINE_DIR"
exec "$DOTNET" bin/OpenRA.dll \
    Game.Mod=iobt \
    Engine.EngineDir=".." \
    Engine.LaunchPath="$VIZ_DIR/launch-game.sh" \
    Engine.ModSearchPaths="$VIZ_DIR/mods,./mods" \
    "$@"
