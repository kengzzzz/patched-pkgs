#!/usr/bin/env bash
set -euo pipefail

diagnostic_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
capture_name="capture-only-$(date +%Y%m%d-%H%M%S)"

printf 'Return to PoE2; capture starts in 5 seconds.\n'
sleep 5
hyprctl -i 0 getoption render:direct_scanout > "$diagnostic_dir/$capture_name-scanout.txt"
hyprctl -i 0 monitors -j > "$diagnostic_dir/$capture_name-before.json"
capture_status=0
timeout 10s grim "$diagnostic_dir/$capture_name.png" || capture_status=$?
hyprctl -i 0 monitors -j > "$diagnostic_dir/$capture_name-after.json"
printf 'Capture exit status: %s\nEvidence prefix: %s/%s\n' "$capture_status" "$diagnostic_dir" "$capture_name"
exit "$capture_status"
