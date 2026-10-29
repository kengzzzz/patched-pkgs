#!/usr/bin/env bash
# Boots the guest. VM_CPUS pins it, for example to one CCD.
set -euo pipefail
work=$(cd -- "$(dirname -- "$0")" && pwd)/work
pin=()
[[ -n ${VM_CPUS:-} ]] && pin=(taskset -c "$VM_CPUS")
exec "${pin[@]}" qemu-system-x86_64 \
    -name latency-vm -enable-kvm -cpu host -smp 8 -m 8G \
    -kernel "$work/vmlinuz" -initrd "$work/initramfs.img" \
    -append "root=/dev/vda rw console=ttyS0 loglevel=4" \
    -drive file="$work/root.img",if=virtio,format=raw,cache=unsafe \
    -virtfs local,path="$work/share",mount_tag=share,security_model=none,id=share \
    -netdev user,id=n0,hostfwd=tcp:127.0.0.1:"${VM_SSH_PORT:-2222}"-:22 -device virtio-net-pci,netdev=n0 \
    -display none -vga none -monitor none \
    -serial file:"$work/serial.log"
