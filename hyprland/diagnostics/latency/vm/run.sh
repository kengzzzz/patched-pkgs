#!/usr/bin/env bash
# run.sh [rounds] [variant...]: boots the guest, runs interleaved stock and patched rounds, summarizes them and shuts down.
# Variants: partial (redraws a small strip), full (redraws every frame), sub (full, from a subsurface).
# Each run takes about 100 s.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
work=$here/work
rounds=${1:-4}
shift || true
variants=("$@")
[[ ${#variants[@]} -gt 0 ]] || variants=(partial full sub)
[[ -f $work/root.img ]] || { printf 'Run setup.sh first.\n' >&2; exit 1; }
name=results-$(date +%Y%m%d-%H%M%S)

rm -rf "$work/share/guest" "$work/share/client"
cp -r "$here/guest" "$work/share/guest"
mkdir -p "$work/share/client"
cp "$here/../client/abclient.c" "$here/../client/build.sh" "$here/../client/wlr-layer-shell-unstable-v1.xml" "$work/share/client/"

"$here/boot.sh" > "$work/qemu.log" 2>&1 &
qemu=$!
shutdown() {
    "$here/ssh.sh" systemctl poweroff 2>/dev/null || true
    for _ in $(seq 30); do kill -0 "$qemu" 2>/dev/null || return 0; sleep 1; done
    kill "$qemu" 2>/dev/null || true
}
trap shutdown EXIT

for _ in $(seq 60); do "$here/ssh.sh" true 2>/dev/null && break; sleep 2; done
"$here/ssh.sh" 'rm -rf /opt/stock /opt/patched && cp -a /mnt/share/opt/stock /mnt/share/opt/patched /opt/ && /mnt/share/client/build.sh'
"$here/ssh.sh" "/mnt/share/guest/run-all.sh $rounds $name ${variants[*]}"

cp -r "$work/share/results/$name" "$here/$name"
python3 -I "$here/analyze.py" "$here/$name" | tee "$here/$name/summary.txt"
