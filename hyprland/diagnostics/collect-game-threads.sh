#!/usr/bin/env bash
set -euo pipefail

diagnostic_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
game_pid=$(hyprctl -i 0 clients -j | python -c '
import json, sys
games = [c for c in json.load(sys.stdin) if c.get("mapped") and c.get("class") == "steam_app_2694490"]
if len(games) != 1:
    sys.exit("Expected exactly one running PoE2 window.")
print(games[0]["pid"])
')
[[ $game_pid =~ ^[1-9][0-9]*$ ]] || exit 1
snapshot="$diagnostic_dir/poe2-native-threads-$(date +%Y%m%d-%H%M%S).txt"

printf 'Collecting PoE2 PID %s; sudo is required by Linux ptrace policy.\n' "$game_pid"
snapshot_status=0
sudo timeout -s INT 20s gdb -nx -nh -batch \
    -iex 'set auto-load off' \
    -iex 'set debuginfod enabled off' \
    -ex 'set pagination off' \
    -ex 'thread apply all bt 8' \
    -ex detach -p "$game_pid" > "$snapshot" 2>&1 || snapshot_status=$?
printf 'Debugger exit status: %s\nSnapshot: %s\n' "$snapshot_status" "$snapshot"
exit "$snapshot_status"
