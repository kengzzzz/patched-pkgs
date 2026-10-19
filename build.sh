#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s [--refresh] <package>\n' "${0##*/}" >&2
    printf '  --refresh  re-run pacman -Syu in the dependency layer\n' >&2
    exit 1
}

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
refresh=()
[[ ${1:-} == --refresh ]] && { refresh=(--no-cache-filter dependencies); shift; }
[[ $# -eq 1 ]] || usage
pkg=${1%/}
dir=$root/$pkg
[[ -f $dir/package.env ]] || { printf 'No package.env in %s\n' "$dir" >&2; exit 1; }

ABI_PACKAGES=
set -a
source "$dir/package.env"
set +a

build_jobs=${BUILD_JOBS:-8}
[[ $build_jobs =~ ^[1-9][0-9]*$ ]] || { printf 'BUILD_JOBS must be a positive integer.\n' >&2; exit 1; }

out=$dir/dist/$PKGVER-$PKGREL
if [[ -e $out ]]; then
    printf '%s already exists. Bump PKGREL or remove it to rebuild.\n' "$out" >&2
    exit 1
fi

args=(--build-arg "BUILD_JOBS=$build_jobs")
for var in BASE_IMAGE UPSTREAM_URL UPSTREAM_REF UPSTREAM_COMMIT PKGVER PKGREL; do
    [[ -n ${!var:-} ]] || { printf '%s is not set in package.env\n' "$var" >&2; exit 1; }
    args+=(--build-arg "$var=${!var}")
done

mkdir -p "$dir/dist"
log=$dir/dist/$PKGVER-$PKGREL.log
docker build --progress=plain "${refresh[@]}" "${args[@]}" \
    --output "type=local,dest=$out" "$dir" 2>&1 | tee "$log"
mv -- "$log" "$out/build.log"
(cd "$out" && sha256sum -- *.pkg.tar.zst > SHA256SUMS)

status=0
for package in "$out"/*.pkg.tar.zst; do
    name=$(bsdtar -xOf "$package" .PKGINFO | sed -n 's/^pkgname = //p')
    if ! pacman -Q "$name" &>/dev/null; then
        printf 'Skipping host check for %s: not installed on this host.\n' "$name"
        continue
    fi
    mapfile -t deps < <(bsdtar -xOf "$package" .PKGINFO | sed -n 's/^depend = //p')
    if ! missing=$(pacman -T "${deps[@]}"); then
        printf '%s: dependencies missing on this host:\n%s\n' "${package##*/}" "$missing" >&2
        status=1
    fi
done

for abi in $ABI_PACKAGES; do
    built=$(awk -v p="$abi" '$1 == p { print $2 }' "$out/build-packages.txt")
    host=$(pacman -Q "$abi" 2>/dev/null | cut -d' ' -f2) || host=
    if [[ ${built%-*} != "${host%-*}" ]]; then
        printf 'ABI mismatch: %s built against %s, host has %s\n' "$abi" "${built:-none}" "${host:-none}" >&2
        status=1
    fi
done

if ((status)); then
    printf '\nPackages are in %s but do not match this host; do not install them.\n' "$out" >&2
    printf 'Update the host or rebuild with --refresh after removing that directory.\n' >&2
    exit 1
fi
printf '\nBuilt and matched against the host:\n'
ls -1 "$out"/*.pkg.tar.zst
