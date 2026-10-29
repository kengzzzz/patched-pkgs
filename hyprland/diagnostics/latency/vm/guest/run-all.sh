#!/usr/bin/env bash
# run-all.sh <rounds> <name> <variant...>: interleaved stock and patched runs, results in /mnt/share/results/<name>
set -uo pipefail
rounds=$1 name=$2
shift 2
out=/mnt/share/results/$name
rm -rf "$out" /root/runs
mkdir -p "$out" /root/runs
declare -A opts=(
    [partial]="--fullscreen --format xb24"
    [full]="--fullscreen --format xb24 --full-damage"
    [sub]="--fullscreen --format xb24 --full-damage --subsurface"
)
for r in $(seq "$rounds"); do
    if ((r % 2)); then order=(stock patched); else order=(patched stock); fi
    for v in "$@"; do
        for b in "${order[@]}"; do
            run=$b-$v-$r
            # shellcheck disable=SC2086
            /mnt/share/guest/run-one.sh "$b" "/root/runs/$run" ${opts[$v]} > "/root/runs/$run.out" 2>&1
            cp -r "/root/runs/$run" "$out/"
            echo "$(date +%T) $run" | tee -a "$out/progress.txt"
        done
    done
done
