#!/usr/bin/env bash
set -euo pipefail

# Usage: drift.sh <root> <package>...
# <root> holds released packages laid out like this repository. The sync
# databases must already list the repositories of the target system.

root=$1
shift
status=0

problem() {
    printf '%s: %s\n' "$pkg" "$1"
    bad=1
    status=1
}

repo_version() {
    local found
    found=$(pacman -Sddp --print-format '%n %v' "$1" 2>/dev/null) || return 1
    [[ ${found%% *} == "$1" ]] && printf '%s\n' "${found#* }"
}

for pkg in "$@"; do
    bad=0
    env=$root/$pkg/package.env
    [[ -f $env ]] || { problem "no release, see the release workflow"; continue; }
    ABI_PACKAGES=
    # shellcheck source=/dev/null
    source "$env"
    out=$root/$pkg/dist/$PKGVER-$PKGREL
    [[ -f $out/build-packages.txt ]] || { problem "no build-packages.txt in $out"; continue; }

    for abi in $ABI_PACKAGES; do
        built=$(awk -v p="$abi" '$1 == p { print $2 }' "$out/build-packages.txt")
        repo=$(repo_version "$abi") || repo=
        [[ ${built%-*} == "${repo%-*}" ]] \
            || problem "built against $abi ${built:-none}, the repositories have ${repo:-none}"
    done

    for file in "$out"/*.pkg.tar.zst; do
        info=$(bsdtar -xOf "$file" .PKGINFO)
        name=$(sed -n 's/^pkgname = //p' <<<"$info")
        version=$(sed -n 's/^pkgver = //p' <<<"$info")
        if repo=$(repo_version "$name"); then
            [[ ${version%-*} == "${repo%-*}" ]] \
                || problem "$name is $version, the repositories have $repo"
            (($(vercmp "$repo" "$version") <= 0)) \
                || problem "the repositories have $name $repo, which replaces $version on update"
        fi
        mapfile -t deps < <(sed -n 's/^depend = //p' <<<"$info")
        for dep in "${deps[@]}"; do
            pacman -Sddp --print-format %n "$dep" &>/dev/null \
                || problem "$name needs $dep, which the repositories do not provide"
        done
    done
    ((bad)) || printf '%s %s-%s matches the repositories\n' "$pkg" "$PKGVER" "$PKGREL"
done

if ((status)); then
    printf '\nBump PKGREL and push to build again.\n'
fi
exit "$status"
