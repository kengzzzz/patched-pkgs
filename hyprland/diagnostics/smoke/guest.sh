#!/usr/bin/env bash
# guest.sh <build> <outdir>: smoke scenarios against /opt/<build>. vm.sh runs it inside the guest.
set -uo pipefail
build=$1 out=$2
share=/mnt/share
client=$share/client/build/abclient
export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1
export PATH=/opt/$build/usr/bin:$PATH LD_LIBRARY_PATH=/opt/$build/usr/lib

mono() { python3 -c 'import time; print(time.monotonic_ns())'; }
mark() {
    echo "$1 $(mono)" >> "$out/phases.txt"
    hyprctl eval "print('SMOKEMARK $1')" > /dev/null
}
fullscreen() {
    mark "$1"
    hyprctl dispatch 'hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" })' > /dev/null
}

rm -rf "$out"
mkdir -p "$out"
pkill -x Hyprland && sleep 1
"$share/guest/start-hypr.sh" "$build" "$out" || exit 1
pid=$(cat "$out/hyprland.pid")
HYPRLAND_INSTANCE_SIGNATURE=$(cat "$out/signature")
export HYPRLAND_INSTANCE_SIGNATURE
log=$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/hyprland.log

python3 -I "$share/smoke/sample.py" "$out/state.txt" &
sampler=$!
python3 "$share/guest/crc.py" /sys/kernel/debug/dri/0/crtc-0/crc "$out/crc.txt" &
crc=$!
sleep 1

# NVIDIA's Vulkan driver creates a new feedback object for every swapchain
mark root
"$client" game --fullscreen --format xb24 --full-damage --refeedback 1500 --seconds 7 --log "$out/root.txt"
sleep 1

mark sub
"$client" game --fullscreen --subsurface --format xb24 --full-damage --refeedback 1500 --seconds 12 --log "$out/sub.txt" &
game=$!
sleep 4
mark headless-add
hyprctl output create headless SMOKE > /dev/null
sleep 3
mark headless-remove
hyprctl output remove SMOKE > /dev/null
wait "$game"
sleep 1

mark osd
"$client" game --fullscreen --format ab24 --full-damage --feedback --seconds 22 --log "$out/osd-game.txt" &
game=$!
sleep 3
"$client" osd --layer overlay --on 1500 --off 1500 --cycles 3 --log "$out/osd.txt"
sleep 1
for _ in 1 2; do
    fullscreen fs-off
    sleep 1.5
    fullscreen fs-on
    sleep 1.5
done
wait "$game"
mark end

kill -0 "$pid" 2>/dev/null && touch "$out/alive"
kill "$sampler" "$crc" 2>/dev/null
kill "$pid"
for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
pkill -9 -x Hyprland
cp "$log" "$out/hyprland.log"
