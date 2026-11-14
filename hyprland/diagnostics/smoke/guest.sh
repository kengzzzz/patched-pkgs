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

lockc=$share/client/build/lockclient
locks=$out/lock
mkdir -p "$locks"
result() { echo "$1 $2" >> "$out/lock.txt"; }
locked() { hyprctl locked 2>&1 | tr -d '[:space:]'; }
events() { awk '{print $1}' "$locks/$1.txt" 2>/dev/null | paste -sd, -; }
# start_holder <name> [args]: start a lock client in the background and wait for its first event
start_holder() {
    local name=$1 want=LOCKED
    shift
    [[ " $* " == *" --no-draw "* ]] && want=REQUEST
    "$lockc" --log "$locks/$name.txt" --seconds 60 "$@" &
    holder=$!
    for _ in $(seq 80); do grep -q "^$want " "$locks/$name.txt" 2>/dev/null && return 0; sleep 0.1; done
    return 1
}
unlock_holder() {
    kill -USR1 "$holder"
    wait "$holder"
    sleep 0.3
}
crash_holder() {
    kill -9 "$holder"
    wait "$holder" 2>/dev/null
    sleep 0.5
}

mark lock-replace
start_holder holder1
"$lockc" --log "$locks/second1.txt" --unlock-after 1000 --seconds 5
sleep 0.5
result replace_locked "$(locked)"
unlock_holder
result replace_unlocked "$(locked)"
result holder1 "$(events holder1)"
result second1 "$(events second1)"

mark lock-limbo
start_holder holder2 --no-draw
sleep 0.5
"$lockc" --log "$locks/second2.txt" --unlock-after 1000 --seconds 5
sleep 0.5
result limbo_locked "$(locked)"
for _ in $(seq 80); do grep -q '^LOCKED ' "$locks/holder2.txt" && break; sleep 0.1; done
unlock_holder
result limbo_unlocked "$(locked)"
result holder2 "$(events holder2)"
result second2 "$(events second2)"

mark lock-crash
start_holder holder3
hyprctl eval 'hl.clear_crashed_lockscreen()' > "$locks/clear-live.txt" 2>&1
result clear_live "$(locked)"
crash_holder
result crash_locked "$(locked)"
start_holder holder4
result takeover_locked "$(locked)"
unlock_holder
result takeover_unlocked "$(locked)"
result holder4 "$(events holder4)"

mark lock-crash-early
start_holder holder5 --no-draw
sleep 0.5
crash_holder
result early_crash_locked "$(locked)"
start_holder holder6
unlock_holder
result early_takeover_unlocked "$(locked)"
result holder6 "$(events holder6)"

mark lock-clear
start_holder holder7
crash_holder
hyprctl eval 'hl.clear_crashed_lockscreen()' > "$locks/clear-dead.txt" 2>&1
sleep 0.3
result clear_dead "$(locked)"

mark lock-finished-once
start_holder holder8
"$lockc" --log "$locks/second3.txt" --seconds 4 &
second=$!
sleep 1
crash_holder
hyprctl eval 'hl.clear_crashed_lockscreen()' > "$locks/clear-denied.txt" 2>&1
sleep 0.3
result denied_clear "$(locked)"
wait "$second"
hyprctl eval 'hl.clear_crashed_lockscreen()' > /dev/null 2>&1
result second3 "$(events second3)"
mark lock-end

kill -0 "$pid" 2>/dev/null && touch "$out/alive"
kill "$sampler" "$crc" 2>/dev/null
kill "$pid"
for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
pkill -9 -x Hyprland
cp "$log" "$out/hyprland.log"
