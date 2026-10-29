#!/usr/bin/env bash
# Measures commit to flip latency of a fullscreen test client on the focused monitor.
# scanout: direct scanout with vsync, uncapped, tearing and tearing under OSDs, about 80 s.
# composited: the same client with direct scanout turned off, about 50 s.
set -uo pipefail
suite=${1:-}
[[ $suite == scanout || $suite == composited ]] || { printf 'Usage: %s scanout|composited\n' "${0##*/}" >&2; exit 1; }

here=$(cd -- "$(dirname -- "$0")" && pwd)
client=$here/../client/build/abclient
[[ -x $client ]] || "$here/../client/build.sh" || exit 1
out=$here/$suite-$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"

mono() { python3 -c 'import time; print(time.monotonic_ns())'; }
mark() { echo "$1 $(mono)" >> "$out/phases.txt"; }
phase() {
    local name=$1
    shift
    mark "$name"
    "$client" game "$@" --log "$out/$name.txt"
    sleep 1
}

orig_ws=$(hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
orig_timeout=$(hyprctl getoption cursor:inactive_timeout | awk '/float/ {print $2}')
orig_ds=$(hyprctl getoption render:direct_scanout | awk '/int/ {print $2}')
cleanup() {
    kill "$sampler" 2>/dev/null
    pkill -f "$client" 2>/dev/null
    hyprctl eval "hl.config({ cursor = { inactive_timeout = ${orig_timeout:-0} }, render = { direct_scanout = ${orig_ds:-1} } })" > /dev/null
    hyprctl dispatch "hl.dsp.focus({ workspace = $orig_ws })" > /dev/null
}
trap cleanup EXIT

python3 -I "$here/sample.py" "$out/state.txt" &
sampler=$!

# a visible hardware cursor blocks tearing
hyprctl eval "hl.config({ cursor = { inactive_timeout = 1 } })" > /dev/null
[[ $suite == composited ]] && hyprctl eval "hl.config({ render = { direct_scanout = 0 } })" > /dev/null
hyprctl dispatch "hl.dsp.focus({ workspace = ${LATENCY_WORKSPACE:-9} })" > /dev/null
sleep 2

gpu=(--gbm "${RENDER_NODE:-/dev/dri/renderD128}" --fullscreen --format xb24 --full-damage)
phase vsync "${gpu[@]}" --seconds 15
phase uncapped "${gpu[@]}" --fps 500 --seconds 15
phase tear "${gpu[@]}" --tear --fps 500 --seconds 15

if [[ $suite == scanout ]]; then
    mark tear-osd
    "$client" game "${gpu[@]}" --tear --fps 500 --seconds 18 --log "$out/tear-osd.txt" &
    game=$!
    sleep 2.5
    "$client" osd --layer overlay --on 1500 --off 3500 --cycles 3 --log "$out/osd.txt"
    wait "$game"
    sleep 1
fi
mark end

python3 -I "$here/analyze.py" "$out" | tee "$out/summary.txt"
