#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
build=$here/build
wp=$(pkg-config --variable=pkgdatadir wayland-protocols)
mkdir -p "$build"
for xml in "$wp/stable/xdg-shell/xdg-shell.xml" "$wp/stable/linux-dmabuf/linux-dmabuf-v1.xml" \
           "$wp/stable/presentation-time/presentation-time.xml" "$wp/staging/tearing-control/tearing-control-v1.xml" \
           "$here/wlr-layer-shell-unstable-v1.xml"; do
    name=$(basename "$xml" .xml)
    wayland-scanner client-header "$xml" "$build/$name-client-protocol.h"
    wayland-scanner private-code "$xml" "$build/$name-protocol.c"
done
# shellcheck disable=SC2046
gcc -O2 -Wall -I"$build" -o "$build/abclient" "$here/abclient.c" "$build"/*-protocol.c \
    $(pkg-config --cflags --libs wayland-client libdrm gbm)
