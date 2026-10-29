#!/usr/bin/env bash
work=$(cd -- "$(dirname -- "$0")" && pwd)/work
exec ssh -q -i "$work/key" -p "${VM_SSH_PORT:-2222}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=5 -o ServerAliveInterval=30 root@127.0.0.1 "$@"
