# aquamarine

aquamarine 0.16.0 with five patches.

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
that, the existing retry modesets as before. A change of bit depth, like 8 to
10 bits, is tried as a page flip too, since `max_bpc` no longer follows the
buffer format. Mode, enable, wide color and `max_bpc` changes still modeset.
The change still flips on vblank, since async flips can't change the format.
It changes only `src/backend/drm/DRM.cpp`.

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

## 0004: leave outputs on at exit

When the compositor exits cleanly, aquamarine turns every output off. The
monitor loses its signal and can take several seconds to show the next
picture, even when the console or the next compositor uses the same mode.
With a greeter that runs its own compositor, every login stayed black that
long.

The patch skips this only when the DRM backend is destroyed. It closes the
framebuffers on screen with CloseFB, so closing the DRM device can't remove
them, and leaves the output on. The last frame, cursor included, stays until
the console or the next compositor draws over it. Unplugged monitors and
outputs disabled at runtime still turn off. It changes only
`src/backend/drm/DRM.cpp`.

The handoff is seamless only when the next DRM client uses the same mode on
the same CRTC. A different mode still needs a modeset. After a crash, or on
kernels without CloseFB, the kernel removes the framebuffer on screen, so the
screen goes blank until the next client draws. NVIDIA without
`nvidia-drm.fbdev=1` turns outputs off whenever the compositor releases the
display, so the patch has no effect there. The next DRM client can read the
last frame until it draws over it.

If the kernel defers the console takeover and nothing has printed to the
console yet, the console's framebuffer was never drawn. The kernel still puts
it on screen when the compositor exits, so leftover video memory shows until
the next compositor starts. Boot with `fbcon=nodefer` to avoid this.

Drop this patch when upstream stops turning outputs off in the
`CDRMBackend` destructor.

## 0005: no HDR infoframe in SDR

In SDR, Hyprland still hands aquamarine HDR metadata, all zeros. aquamarine
turned it into a blob, so the driver sent an HDR infoframe that only says
SDR. The console sends no HDR infoframe at all. Some monitors resync for a
few seconds whenever that infoframe starts or stops, so starting a compositor
from the console went black that long, even at the same mode.

When the metadata is all zeros, the patch clears `HDR_OUTPUT_METADATA`
instead of creating a blob, the same as the console. Any other metadata still
gets a blob. Turning HDR off in a session now stops the infoframe too,
instead of sending one that says SDR. It changes only
`src/backend/drm/impl/Atomic.cpp`.

Drop this patch when upstream clears the property for empty metadata, or
Hyprland stops sending empty metadata in SDR.

## Validation

Tested on aquamarine 0.15.1 and 0.16.0 with Hyprland 0.57.0 and the patches
in this repo, on an RTX 5080 and a 3440x1440 240 Hz QD-OLED. HDR metadata
changes were tested on 0.15.1 only.

- 0001: see the 0007 entries in the Hyprland README. On 0.16.0, a native game
  scanned out and tore at well over the refresh rate.
- 0002: a native game switched between XB24 and XR24 16 times around OSDs,
  each time without a modeset and with no fallback. In HDR, entering and
  leaving fullscreen changed the format and the HDR metadata without a
  modeset. The driver accepted every one of these commits. On 0.16.0,
  workspace switches during a game, OSDs over a browser video and a 10-bit
  video player going in and out of fullscreen on an 8-bit desktop changed the
  format the same way, including 8 to 10 bits and back.
- 0003: an OSD over a fullscreen browser video no longer blanked the video
  for over a second.
- 0004: tested with Hyprland 0.57.1 on kernel 7.3.3 and NVIDIA 620.70.06
  with `nvidia-drm.fbdev=1`. A compositor running the greeter's config, started
  from a text console and closed with its exit bind, left the screen black for
  about five seconds without the patch. With it, the console showed in under a
  second. A real login went from the greeter to the desktop without the long
  black screen.
- 0005: tested with the same setup. A compositor running the greeter's config,
  started from a text console at the same mode, changed the HDR infoframe and
  left the screen black for a few seconds without the patch. With it, the
  kernel saw no infoframe change and the picture came up in about a second. A
  boot through the greeter and a login changed the infoframe zero times. HDR
  on and off still switched the monitor in and out of HDR.

## Rollback

To drop a patch, remove it from `patches/`, bump `PKGREL` and build again.
For the unpatched package, run `sudo pacman -S aquamarine`. Either way, log
out and back in.
