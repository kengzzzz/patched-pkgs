# aquamarine

aquamarine 0.15.1 with three patches.

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

## 0002: change the output format or HDR metadata without a modeset

Every switch between direct scanout and compositing changes the output format
when the client's buffers use a different format than Hyprland's swapchain,
and in HDR it can change the HDR metadata too. aquamarine treats both as a
reconfiguration and modesets, so the screen blinked each time a notification
or OSD appeared over a game and again when it left.

When a commit changes only the format or the HDR metadata and carries a
buffer, the patch first commits it as a plain page flip. If the driver rejects
that, the existing retry modesets as before. On a connector with a `max_bpc`
property, a change of bit depth, like 8 to 10 bits, still modesets, because
`max_bpc` follows the bit depth. NVIDIA connectors have no `max_bpc`, and
NVIDIA's driver applies HDR metadata without a modeset, so there both are
tried as a page flip. Mode, enable and wide color changes still modeset. The
change still flips on vblank, since async flips can't change the format. It
changes only `src/backend/drm/DRM.cpp`.

Drop this patch when upstream stops modesetting for format and HDR metadata
changes in `CDRMOutput::commitState`.

## 0003: report an unknown age for new swapchain buffers

`CSwapchain::next` always reports the swapchain length as the buffer age, even
for buffers that were just allocated and hold nothing yet. Hyprland uses the
age to redraw only what changed since that buffer was last shown. Every switch
between direct scanout and compositing reallocates the swapchain in a new
format, so the frames after the switch were drawn onto empty buffers with only
the latest damage. A fullscreen window that redraws little, like a video,
stayed black around a notification or OSD for over a second.

The patch marks new buffers as fresh and reports age 0 for each until it has
been handed out once, so the consumer redraws the whole frame. A rolled back
acquire marks the buffer fresh again. It changes `src/allocator/Swapchain.cpp`
and adds two private members to `CSwapchain` in
`include/aquamarine/allocator/Swapchain.hpp`. The class is only created inside
the library, so consumers don't need a rebuild.

Drop this patch when upstream reports an unknown age for buffers that were
never acquired.

## Validation

Tested with Hyprland 0.57.0 and the patches in this repo, on an RTX 5080 and
a 3440x1440 240 Hz QD-OLED.

- 0001: see the 0007 entries in the Hyprland README.
- 0002: a native game switched between XB24 and XR24 16 times around OSDs,
  each time without a modeset and with no fallback. In HDR, entering and
  leaving fullscreen changed the format and the HDR metadata without a
  modeset. The driver accepted every one of these commits.
- 0003: an OSD over a fullscreen browser video no longer blanked the video
  for over a second.

## Rollback

To drop a patch, remove it from `patches/`, bump `PKGREL` and build again.
For the unpatched package, run `sudo pacman -S aquamarine`. Either way, log
out and back in.
