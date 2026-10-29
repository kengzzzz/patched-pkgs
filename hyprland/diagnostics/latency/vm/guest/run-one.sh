#!/usr/bin/env bash
# run-one.sh <build> <outdir> [client options...]: one scenario run against /opt/<build>
set -uo pipefail
build=$1 out=$2
shift 2
game_opts=("$@")
[[ ${#game_opts[@]} -eq 0 ]] && game_opts=(--fullscreen --format xb24)
share=/mnt/share
client=$share/client/build/abclient
export XDG_RUNTIME_DIR=/run/user/0 WAYLAND_DISPLAY=wayland-1

mono() { python3 -c 'import time; print(time.monotonic_ns())'; }
mark() { LD_LIBRARY_PATH=/opt/$build/usr/lib /opt/$build/usr/bin/hyprctl eval "print('ABMARK $1')" > /dev/null; }
phase() { mark "end $1"; echo "PHASE $1 $2 $3" >> "$out/phases.txt"; }
perf_phase() {
    local name=$1 secs=$2
    perf stat -x, -e task-clock,instructions:u,instructions:k,cycles:u -p "$pid" -o "$out/perf-$name-proc.csv" -- sleep "$secs" &
    perf stat -x, -e task-clock,instructions:u,instructions:k,cycles:u -t "$pid" -o "$out/perf-$name-main.csv" -- sleep "$secs" &
}

rm -rf "$out"
mkdir -p "$out"
pkill -x Hyprland && sleep 1
"$share/guest/start-hypr.sh" "$build" "$out" || exit 1
pid=$(cat "$out/hyprland.pid")
export HYPRLAND_INSTANCE_SIGNATURE=$(cat "$out/signature")
log=$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/hyprland.log
sleep 1

python3 "$share/guest/crc.py" /sys/kernel/debug/dri/0/crtc-0/crc "$out/crc.txt" &
crc_pid=$!
"$client" game "${game_opts[@]}" --log "$out/game.txt" &
game_pid=$!
sleep 4

t0=$(mono)
mark start
perf_phase ds 15
sleep 15.2
phase ds "$t0" "$(mono)"

t0=$(mono)
mark start
perf_phase osd 41
"$client" osd --layer overlay --on 1500 --off 3500 --cycles 8 --delay 500 --log "$out/osd.txt"
sleep 0.5
phase osd "$t0" "$(mono)"

t0=$(mono)
mark start
perf_phase comp 15
"$client" osd --layer overlay --on 15500 --off 0 --cycles 1 --log "$out/osd-steady.txt"
phase comp "$t0" "$(mono)"
sleep 1

fs_toggle() {
    LD_LIBRARY_PATH=/opt/$build/usr/lib /opt/$build/usr/bin/hyprctl dispatch 'hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" })' > /dev/null
    echo "$1 $(mono)" >> "$out/fs.txt"
}
t0=$(mono)
mark start
perf_phase fs 23
for _ in 1 2 3; do
    fs_toggle FSOFF
    sleep 2
    fs_toggle FSON
    sleep 2
done
for i in 1 2; do
    "$client" osd --layer overlay --on 3000 --cycles 1 --log "$out/osd-fs-$i.txt" &
    sleep 1
    fs_toggle FSOFF_OSD
    sleep 1.5
    fs_toggle FSON_OSD
    wait $!
    sleep 1.5
done
sleep 0.5
phase fs "$t0" "$(mono)"

kill "$game_pid" 2>/dev/null
wait "$game_pid" 2>/dev/null
kill "$crc_pid" 2>/dev/null
kill "$pid"
for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
pkill -9 -x Hyprland
cp "$log" "$out/hyprland.log"
echo "done $build $out"
