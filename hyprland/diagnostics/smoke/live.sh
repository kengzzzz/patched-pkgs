#!/usr/bin/env bash
# live.sh: smoke checks on the running session, about a minute on workspace 9. Keep the mouse still.
# Exits non-zero when a check fails.
set -uo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
client=$here/../latency/client/build/abclient
"$here/../latency/client/build.sh" || exit 1
out=$here/live-$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"

mono() { python3 -c 'import time; print(time.monotonic_ns())'; }
mark() { echo "$1 $(mono)" >> "$out/phases.txt"; }
float_rule() {
    hyprctl eval "hl.window_rule({ name = \"smoke-float\", enabled = $1, match = { class = \"^(abgame)$\" }, float = true })" > /dev/null
}

orig_ws=$(hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
orig_timeout=$(hyprctl getoption cursor:inactive_timeout | awk '/float/ {print $2}')
hyprctl monitors -j | python3 -c 'import json,sys; print(next(m["name"] for m in json.load(sys.stdin) if m["focused"]))' > "$out/monitor"
cleanup() {
    kill "$sampler" "$logger" 2>/dev/null
    pkill -f "$client" 2>/dev/null
    [[ -n ${vk:-} ]] && kill "$vk" 2>/dev/null
    float_rule false
    hyprctl eval "hl.config({ cursor = { inactive_timeout = ${orig_timeout:-0} } })" > /dev/null
    hyprctl dispatch "hl.dsp.focus({ workspace = $orig_ws })" > /dev/null
}
trap cleanup EXIT

python3 -I "$here/../latency/live/sample.py" "$out/state.txt" &
sampler=$!
python3 -I "$here/rolling.py" "$out/hyprland.log" &
logger=$!

# a visible hardware cursor blocks tearing
hyprctl eval "hl.config({ cursor = { inactive_timeout = 1 } })" > /dev/null
hyprctl dispatch "hl.dsp.focus({ workspace = ${SMOKE_WORKSPACE:-9} })" > /dev/null
sleep 2

gpu=(--gbm "${RENDER_NODE:-/dev/dri/renderD128}" --fullscreen --full-damage)

mark tear
"$client" game "${gpu[@]}" --format xb24 --tear --fps 500 --feedback --seconds 8 --log "$out/tear.txt"
sleep 1

# 0011 needs a floating fullscreen window
float_rule true
mark osd
"$client" game "${gpu[@]}" --format xb24 --tear --fps 500 --seconds 15 --log "$out/osd-game.txt" &
game=$!
sleep 1.5
hyprctl clients -j | python3 -c 'import json,sys; print(json.dumps([c for c in json.load(sys.stdin) if c["class"] == "abgame"]))' > "$out/clients-osd.json"
sleep 1
"$client" osd --layer top --on 1500 --off 2500 --cycles 3 --log "$out/osd.txt"
wait "$game"
float_rule false
sleep 1

mark sub
"$client" game "${gpu[@]}" --subsurface --format xb24 --tear --fps 500 --seconds 8 --log "$out/sub.txt"
sleep 1

mark ab30
"$client" game "${gpu[@]}" --format ab30 --seconds 8 --log "$out/ab30.txt"
sleep 1

# unlike abclient, the driver picks its buffers from the scanout tranche
if command -v vkcube > /dev/null; then
    mark vkcube
    vkcube --wsi wayland > /dev/null 2>&1 &
    vk=$!
    sleep 1.5
    hyprctl dispatch 'hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" })' > /dev/null
    sleep 7
    kill "$vk"
    wait "$vk" 2>/dev/null
    vk=
    sleep 1
fi
mark end

sleep 0.5
kill "$sampler" "$logger" 2>/dev/null
python3 -I "$here/live-check.py" "$out" | tee "$out/verdict.txt"
exit "${PIPESTATUS[0]}"
