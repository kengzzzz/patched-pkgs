#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || { printf 'Usage: %s <window class>\n' "${0##*/}" >&2; exit 1; }
diagnostic_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
game_pid=$(hyprctl -i 0 clients -j | python -c '
import json, sys
games = [c for c in json.load(sys.stdin) if c.get("mapped") and c.get("class") == sys.argv[1]]
if len(games) != 1:
    sys.exit(f"Expected exactly one mapped window with class {sys.argv[1]}.")
print(games[0]["pid"])
' "$1")
[[ $game_pid =~ ^[1-9][0-9]*$ ]] || exit 1
snapshot="$diagnostic_dir/game-threads-$(date +%Y%m%d-%H%M%S).txt"

printf 'Collecting PID %s. Linux ptrace policy requires sudo.\n' "$game_pid"
snapshot_status=0
sudo timeout -s INT 20s gdb -nx -nh -batch \
    -iex 'set auto-load off' \
    -iex 'set debuginfod enabled off' \
    -ex 'set pagination off' \
    -ex 'thread apply all bt 8' \
    -ex detach -p "$game_pid" > "$snapshot" 2>&1 || snapshot_status=$?
printf 'Debugger exit status: %s\nSnapshot: %s\n' "$snapshot_status" "$snapshot"
exit "$snapshot_status"
