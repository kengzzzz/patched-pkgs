#!/usr/bin/env bash
# start-hypr.sh <build> <outdir>: start Hyprland from /opt/<build> and wait for its socket
set -euo pipefail
build=$1 out=$2
mkdir -p "$out"
export XDG_RUNTIME_DIR=/run/user/0
rm -rf "$XDG_RUNTIME_DIR/hypr"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export LIBSEAT_BACKEND=${LIBSEAT_BACKEND:-noop}
export LD_LIBRARY_PATH=/opt/$build/usr/lib
setsid /opt/$build/usr/bin/Hyprland --i-am-really-stupid -c /mnt/share/guest/hypr.lua > "$out/hyprland.stdout" 2>&1 < /dev/null &
echo $! > "$out/hyprland.pid"
for _ in $(seq 100); do
    sig=$(ls "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -1 || true)
    if [[ -n $sig && -S $XDG_RUNTIME_DIR/hypr/$sig/.socket.sock && -S $XDG_RUNTIME_DIR/wayland-1 ]]; then
        echo "$sig" > "$out/signature"
        sleep 0.5
        HYPRLAND_INSTANCE_SIGNATURE=$sig /opt/$build/usr/bin/hyprctl dismissnotify > /dev/null
        exit 0
    fi
    sleep 0.1
done
echo "Hyprland did not start" >&2
tail -30 "$out/hyprland.stdout" >&2
exit 1
