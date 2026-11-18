# patched-pkgs

Patched Arch Linux packages, built in Docker. Each package pins an upstream
commit and applies the patches in its `patches/` directory. Nothing here
installs a package or changes the running system.

| Package | Patches |
| --- | --- |
| [hyprland](hyprland/README.md) | Direct scanout and tearing for Wine and fullscreen games, HDR metadata, OSDs over fullscreen windows, SDR screenshots of HDR frames, commit queue crash, session lock replacement, layer fade blur |
| [aquamarine](aquamarine/README.md) | Tearing with direct scanout, format and HDR changes without a modeset, buffer age, outputs left on at exit, no HDR infoframe in SDR |
| [quickshell](quickshell/README.md) | Event socket reconnect, one shared VkDevice, thread-safe theme icons |
| [egl-wayland2](egl-wayland2/README.md) | `wl_buffer.release` leak with explicit sync |
| [qt6-declarative](qt6-declarative/README.md) | Out-of-date swapchain in the threaded render loop, Arch's backports |
| [freerdp](freerdp/README.md) | No blocking security key box in SDL3, no FIDO2 PIN when UV is not required |

## Layout

```
<package>/
  package.env    upstream pin, version, base image, ABI check
  Dockerfile     install deps, clone, apply patches, makepkg
  PKGBUILD       builds the cloned tree
  patches/       applied in name order with `git apply --index`
  README.md      what each patch fixes and how to roll back
  references/    hyprland only, original patch export
  diagnostics/   hyprland only, test scripts
  dist/          build output, one directory per version, untracked
```

`package.env` fields:

| Field | Meaning |
| --- | --- |
| `BASE_IMAGE` | Arch `base-devel` image, pinned by digest |
| `UPSTREAM_URL` | Git repository to clone |
| `UPSTREAM_REF` | Tag to build |
| `UPSTREAM_COMMIT` | Commit the tag must point to, or the build fails |
| `PKGVER`, `PKGREL` | Package version |
| `ABI_PACKAGES` | Optional. Packages that must match the host's upstream version. |

## Build

Docker must work without sudo.

```sh
./build.sh quickshell
BUILD_JOBS=16 ./build.sh hyprland
./build.sh --refresh hyprland   # also update the build image's packages
```

Output goes to `<package>/dist/<PKGVER>-<PKGREL>/`: the packages,
`SHA256SUMS`, `source.txt`, `build-packages.txt`, `.SRCINFO` and `build.log`.

`build.sh` never overwrites a version directory. Bump `PKGREL` to build again.

After the build, `build.sh` fails if the host lacks a runtime dependency or an
`ABI_PACKAGES` entry differs from the host. Update the host or rebuild with
`--refresh`. `--no-host-check` skips this for builds that go to another
system.

## Compiler flags

The Dockerfiles build with `-march=znver5 -mtune=znver5 -O3` and LTO. The
packages run only on Zen 5. On another CPU, makepkg skips `check()`.

## Releases

`.github/workflows/release.yml` builds aquamarine, egl-wayland2, hyprland and
freerdp after a push to main or by hand. It builds a package only when no
release `<package>-<PKGVER>-<PKGREL>` exists, and never replaces a release.
Each release has a `.tar` with `package.env` and `dist/<PKGVER>-<PKGREL>/`,
and its `.sha256`. Check `ABI_PACKAGES` and dependencies on the system that
installs it.

`.github/workflows/drift.yml` runs daily. It fails when a release no longer
fits the CachyOS znver4 and Arch repositories. Update `package.env`, bump
`PKGREL` and push. When CachyOS only lags behind Arch, wait for it. GitHub
turns the schedule off after 60 days without a commit.

## Install

```sh
sudo pacman -U <package>/dist/<PKGVER>-<PKGREL>/<name>-<PKGVER>-<PKGREL>-x86_64.pkg.tar.zst
```

Set `PKGREL` to the repository pkgrel plus 0.1. When the repository releases a
higher version, `pacman -Syu` replaces the local package without a warning.
Compare `pacman -Qm` with `pacman -Si <name>` before updating, or add the
package to `IgnorePkg`.

`dist/` keeps only the installed build. To roll back a patch, remove it or
restore the older version from git, bump `PKGREL` and build again.
`sudo pacman -S <name>` goes back to the repository package.

## Updating a package

1. Check whether upstream fixed the problem. `./overlap.py <package> <tag>`
   lists patches that no longer apply or sit near upstream changes.
2. Set `UPSTREAM_REF`, `UPSTREAM_COMMIT`, `PKGVER` and `PKGREL`. Get the
   commit with `git ls-remote <url> 'refs/tags/<tag>*'`. For an annotated tag,
   use the line ending in `^{}`.
3. Compare the PKGBUILD with Arch's at
   `https://gitlab.archlinux.org/archlinux/packaging/packages/<name>`.
4. Build. Rebase any patch that fails to apply.
5. Test the fix at runtime before installing.

## License

The build script, Dockerfiles and docs are under [0BSD](LICENSE). Each patch
follows its upstream license: Hyprland and aquamarine BSD-3-Clause, quickshell
LGPL-3.0-only, egl-wayland2 and FreeRDP Apache-2.0, Qt Declarative
LGPL-3.0-only, GPL-2.0-only or GPL-3.0-only. The PKGBUILDs are adapted from
Arch Linux packaging, 0BSD.
