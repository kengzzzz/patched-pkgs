# aquamarine

aquamarine 0.16.0 with five patches.

## 0001: no async page flip on a modeset commit

Entering direct scanout with tearing asked for a modeset and an async flip in
the same commit. The kernel rejects that with EINVAL, so Hyprland fell back
to compositing and tried again, which modeset on almost every frame.

The patch drops the async flag from any commit that modesets. The format
change flips on vblank once, and later frames flip async.

Hyprland needs its patch 0007 too, or the next torn frame is committed before
the vblank flip completes.

Drop it when upstream stops adding `DRM_MODE_PAGE_FLIP_ASYNC` to modeset
commits in `CDRMOutput::commitState`.

## 0002: change the output format or HDR metadata without a modeset

Each switch between direct scanout and compositing can change the output
format and HDR metadata. aquamarine modeset for both, so the screen blinked
when an OSD appeared over a game and again when it left.

The patch first tries such a commit as a plain page flip, bit depth changes
included. If the driver rejects it, the existing retry modesets. Mode, enable,
wide color and `max_bpc` changes still modeset.

HDR metadata changes were tested on aquamarine 0.15.1 only.

Drop it when upstream stops modesetting for format and HDR metadata changes.

## 0003: report an unknown age for new swapchain buffers

`CSwapchain::next` reports the swapchain length as the age of buffers that
were just allocated and are empty. Hyprland then redraws only the damage. A
format switch reallocates the swapchain, so a video stayed black around an OSD
for over a second.

The patch reports age 0 for a new buffer until it has been handed out once.
It adds private members to `CSwapchain`, but consumers don't need a rebuild.

Drop it when upstream reports an unknown age for buffers that were never
acquired.

## 0004: leave outputs on at exit

aquamarine turns every output off when the compositor exits. Some monitors
then take several seconds to show the next picture, so a login from a greeter
stayed black that long.

The patch leaves outputs on when the DRM backend is destroyed, and closes the
framebuffers with CloseFB so the last frame stays on screen. Unplugged and
disabled outputs still turn off.

Limits:

- The handoff is seamless only when the next client uses the same mode on the
  same CRTC.
- After a crash or on kernels without CloseFB, the screen goes blank until the
  next client draws.
- NVIDIA needs `nvidia-drm.fbdev=1`, or the patch has no effect.
- The next DRM client can read the last frame.
- With a deferred console takeover, old video memory can show until the next
  compositor starts. Boot with `fbcon=nodefer` to avoid it.

Drop it when upstream stops turning outputs off in the `CDRMBackend`
destructor.

## 0005: no HDR infoframe in SDR

In SDR, Hyprland passes all-zero HDR metadata. aquamarine sent it as an HDR
infoframe that says SDR. The console sends none. Some monitors resync for a
few seconds when the infoframe starts or stops, so starting a compositor from
the console went black.

The patch clears `HDR_OUTPUT_METADATA` when the metadata is all zeros. Turning
HDR off in a session now stops the infoframe too.

Drop it when upstream clears the property for empty metadata, or Hyprland
stops sending empty metadata in SDR.

## Rollback

Remove the patch from `patches/`, bump `PKGREL` and build again. For the
unpatched package, run `sudo pacman -S aquamarine`. Log out and back in
either way.
