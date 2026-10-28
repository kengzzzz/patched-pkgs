# aquamarine

aquamarine 0.15.1 with one patch.

## 0001: no async page flip on a modeset commit

Direct scanout and tearing could not run together. Entering direct scanout
changes the output format from Hyprland's swapchain format to the game's
buffer format, which needs a modeset. With tearing, the same commit also
asked for an async page flip. The kernel rejects a commit with both, so it
failed with EINVAL. Hyprland then went back to compositing and tried again on
the next frame, which caused a modeset on almost every frame.

The patch drops the async flag from any commit that modesets. The format
change flips on vblank once, and the frames after it flip async. Leaving
direct scanout costs one modeset, as it did before. It changes only
`src/backend/drm/DRM.cpp`.

Hyprland also needs patch 0007 from this repo. Without it, the next torn
frame is committed before the vblank flip completes, and the loop continues.

Drop this patch when upstream stops adding `DRM_MODE_PAGE_FLIP_ASYNC` to
commits that modeset in `CDRMOutput::commitState`.

## Rollback

To drop the patch, remove it from `patches/`, bump `PKGREL` and build again.
For the unpatched package, run `sudo pacman -S aquamarine`. Either way, log
out and back in.
