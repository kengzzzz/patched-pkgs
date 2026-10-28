# patched-pkgs

Patched Arch Linux packages, built in Docker. Each package directory pins an
upstream commit and applies the patches in its `patches/` directory. Nothing
here installs a package or changes the running system.

| Package | Patches |
| --- | --- |
| [hyprland](hyprland/README.md) | Tearing and direct scanout feedback for Wine subsurfaces, scanout feedback for windows that map fullscreen, guard against a scanout modeset loop, HDR signaling for SDR fullscreen windows, flow control for torn direct scanout, presentation feedback tagging, top layers over fullscreen windows, tearing hints from subsurfaces |
| [quickshell](quickshell/README.md) | Shared VkDevice for all windows, event socket reconnect |
| [egl-wayland2](egl-wayland2/README.md) | `wl_buffer.release` leak with explicit sync |
| [aquamarine](aquamarine/README.md) | Direct scanout with tearing |

## Layout

```
<package>/
  package.env    upstream pin, package version, base image, ABI check
  Dockerfile     install deps, clone and verify, apply patches, makepkg
  PKGBUILD       builds the cloned tree
  patches/       applied in name order with `git apply --index`
  README.md      what each patch fixes and how to roll back
  references/    hyprland only: original patch export
  diagnostics/   hyprland only: scanout and freeze capture scripts
  dist/          build output, one directory per version (not tracked)
```

`package.env` fields:

| Field | Meaning |
| --- | --- |
| `BASE_IMAGE` | Arch `base-devel` image, pinned by digest |
| `UPSTREAM_URL` | Git repository to clone |
| `UPSTREAM_REF` | Tag to build |
| `UPSTREAM_COMMIT` | Commit the tag must point to. The build fails otherwise. |
| `PKGVER`, `PKGREL` | Package version |
| `ABI_PACKAGES` | Optional. Packages that must have the same upstream version as the host. |

## Build

Docker must be usable without sudo.

```sh
./build.sh quickshell
BUILD_JOBS=16 ./build.sh hyprland
./build.sh --refresh hyprland   # also update packages in the build image
```

The output goes to `<package>/dist/<PKGVER>-<PKGREL>/`:

- the packages and `SHA256SUMS`
- `source.txt` with the upstream commit and the patch checksums
- `build-packages.txt` with the package versions used in the build
- `.SRCINFO` and `build.log`

## Compiler flags

Each Dockerfile changes the image's `/etc/makepkg.conf` from
`-march=x86-64 -mtune=generic -O2` to `-march=native -O3`, like CachyOS's
makepkg.conf. LTO stays on through makepkg's default `lto` option. Docker
does not hide the CPU, so `native` resolves to the host CPU (`znver5` here).
The build log shows the resolved `-march` and `-mtune`. The packages only run
on the CPU family they were built on.

`build.sh` never overwrites an existing version directory. Bump `PKGREL` to
build again.

After the build, `build.sh` fails if the host is missing a runtime dependency
or if an `ABI_PACKAGES` entry has a different upstream version on the host.
Update the host or rebuild with `--refresh`.

## Install

```sh
sudo pacman -U <package>/dist/<PKGVER>-<PKGREL>/<name>-<PKGVER>-<PKGREL>-x86_64.pkg.tar.zst
```

Set `PKGREL` to the repository pkgrel plus 0.1, so the local package is newer
than the repository one. When the repository releases a higher version,
`pacman -Syu` replaces the local package without a warning. Compare
`pacman -Qm` with `pacman -Si <name>` before updating, or add the package to
`IgnorePkg`.

`dist/` keeps only the installed build. To roll back a patch, remove it from
`patches/` or restore the older version from git, bump `PKGREL` and build
again. `sudo pacman -S <name>` goes back to the unpatched repository package.

## Updating a package

1. Check whether upstream already fixed the problem.
2. Set `UPSTREAM_REF`, `UPSTREAM_COMMIT`, `PKGVER` and `PKGREL`. Get the commit
   with `git ls-remote <url> 'refs/tags/<tag>*'`. For an annotated tag, use the
   line ending in `^{}`.
3. Compare the PKGBUILD with Arch's at
   `https://gitlab.archlinux.org/archlinux/packaging/packages/<name>`.
4. Build. Patches must apply exactly. Rebase any patch that fails.
5. Test the fix at runtime before installing.

## License

The build script, Dockerfiles and documentation are under [0BSD](LICENSE).
Each patch follows the license of its upstream project: Hyprland
(BSD-3-Clause), aquamarine (BSD-3-Clause), quickshell (LGPL-3.0-only) and
egl-wayland2 (Apache-2.0). The PKGBUILDs are adapted from Arch Linux packaging
(0BSD).
