#!/usr/bin/env bash
# vm.sh: runs guest.sh against stock and patched Hyprland in the latency VM and prints one verdict per check.
# The VM is set up or rebuilt first when a package changed. Exits non-zero when a patched check fails.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
vm=$here/../latency/vm
work=$vm/work
client=$here/../latency/client
name=results-$(date +%Y%m%d-%H%M%S)

BUILD_JOBS=${BUILD_JOBS:-8} "$vm/setup.sh"

rm -rf "$work/share/guest" "$work/share/client" "$work/share/smoke" "$work/share/smoke-results"
cp -r "$vm/guest" "$work/share/guest"
mkdir -p "$work/share/client" "$work/share/smoke"
cp "$client/abclient.c" "$client/lockclient.c" "$client/build.sh" "$client/wlr-layer-shell-unstable-v1.xml" "$work/share/client/"
cp "$here/guest.sh" "$here/../latency/live/sample.py" "$work/share/smoke/"

"$vm/boot.sh" > "$work/qemu.log" 2>&1 &
qemu=$!
shutdown() {
    "$vm/ssh.sh" systemctl poweroff 2>/dev/null || true
    for _ in $(seq 30); do kill -0 "$qemu" 2>/dev/null || return 0; sleep 1; done
    kill "$qemu" 2>/dev/null || true
}
trap shutdown EXIT

for _ in $(seq 60); do "$vm/ssh.sh" true 2>/dev/null && break; sleep 2; done
"$vm/ssh.sh" 'rm -rf /opt/stock /opt/patched && cp -a /mnt/share/opt/stock /mnt/share/opt/patched /opt/ && /mnt/share/client/build.sh'
for build in stock patched; do
    "$vm/ssh.sh" "/mnt/share/smoke/guest.sh $build /root/smoke/$build && mkdir -p /mnt/share/smoke-results && cp -r /root/smoke/$build /mnt/share/smoke-results/"
done

mkdir -p "$here/$name"
cp -r "$work/share/smoke-results/"* "$here/$name/"
set +e
python3 -I "$here/check.py" "$here/$name" | tee "$here/$name/verdict.txt"
exit "${PIPESTATUS[0]}"
