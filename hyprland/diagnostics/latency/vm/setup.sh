#!/usr/bin/env bash
# Builds stock and patched Hyprland and aquamarine with this repo's Dockerfiles, then a KVM guest with vkms.
# Both aquamarine builds carry aquamarine-skip-mgpu-retry.patch. Without a render node, aquamarine retries its
# blit renderer on every commit, which only happens in the guest. Delete work/ to rebuild after patches change.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "$here/../../../.." && pwd)
work=$here/work
deps_image=patched-pkgs-latency-deps
vm_image=patched-pkgs-latency-vm
mkdir -p "$work/ab" "$work/ctx" "$work/share/opt"

cp "$repo/build.sh" "$work/ab/"
for pkg in aquamarine hyprland; do
    for variant in stock patched; do
        dir=$work/ab/$pkg-$variant
        [[ -n $(compgen -G "$dir/dist/*/$pkg-0*.pkg.tar.zst") ]] && continue
        rm -rf "$dir"
        mkdir -p "$dir/patches"
        cp "$repo/$pkg/Dockerfile" "$repo/$pkg/PKGBUILD" "$repo/$pkg/package.env" "$dir/"
        [[ $variant == patched ]] && cp "$repo/$pkg/patches/"*.patch "$dir/patches/"
        [[ $pkg == aquamarine ]] && cp "$here/aquamarine-skip-mgpu-retry.patch" "$dir/patches/9000-skip-mgpu-retry.patch"
        # the host check at the end of build.sh doesn't matter for the guest
        BUILD_JOBS=${BUILD_JOBS:-8} "$work/ab/build.sh" "$pkg-$variant" > "$work/ab/$pkg-$variant.log" 2>&1 || true
        [[ -n $(compgen -G "$dir/dist/*/$pkg-0*.pkg.tar.zst") ]] || { printf 'Build failed, see %s\n' "$work/ab/$pkg-$variant.log" >&2; exit 1; }
    done
done

base_image=$(. "$work/ab/hyprland-stock/package.env" && echo "$BASE_IMAGE")
docker build -q --target dependencies --build-arg "BASE_IMAGE=$base_image" -t "$deps_image" "$work/ab/hyprland-stock"
[[ -f $work/key ]] || ssh-keygen -q -t ed25519 -N '' -C latency-vm -f "$work/key"
cp "$here/Dockerfile" "$work/key.pub" "$work/ctx/"
docker build -q --build-arg "DEPS_IMAGE=$deps_image" -t "$vm_image" "$work/ctx"

cid=$(docker create "$vm_image")
trap 'docker rm -f "$cid" > /dev/null' EXIT
docker cp "$cid:/boot/vmlinuz-linux" "$work/vmlinuz"
docker cp "$cid:/boot/initramfs-test.img" "$work/initramfs.img"
docker export "$cid" | docker run --rm -i -v "$work:/out" "$vm_image" bash -euo pipefail -c '
    mkdir /r
    tar -xpf - -C /r
    rm -f /r/.dockerenv /out/root.img
    : > /r/etc/machine-id
    printf "nameserver 10.0.2.3\n" > /r/etc/resolv.conf
    mkfs.ext4 -q -L root -d /r /out/root.img 12G
    chown '"$(id -u):$(id -g)"' /out/root.img'

for variant in stock patched; do
    opt=$work/share/opt/$variant
    rm -rf "$opt"
    mkdir -p "$opt"
    for pkg in aquamarine hyprland; do
        bsdtar -xf "$(compgen -G "$work/ab/$pkg-$variant/dist/*/$pkg-0*.pkg.tar.zst" | head -1)" -C "$opt" --exclude '.*'
    done
done
printf 'Guest ready in %s\n' "$work"
