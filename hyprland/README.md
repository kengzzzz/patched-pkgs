# hyprland

Hyprland 0.57.0 with nine patches. The numbers carry over from earlier
releases. 0002, a backport of the tearing fix in upstream PR
[#16572](https://github.com/hyprwm/Hyprland/pull/16572), was dropped because
0.57.0 includes it.

## 0001: keep scanout dmabuf feedback for subsurfaces

Taken from Rick Littel's commit
[8edefed](https://github.com/Kuret/Hyprland/commit/8edefed837199c53f8652b991415d331ac571a04).

When a window goes fullscreen, Hyprland sends the scanout tranche to only one
dmabuf feedback object. That misses two cases:

- Wine renders into a subsurface, not the fullscreen surface.
- NVIDIA's Vulkan driver creates a new feedback object every time it
  recreates a swapchain.

These clients then allocate buffers that can't be used for direct scanout.

The patch tracks the surface tree of each scanout window and sends the tranche
to every feedback object in it. New feedback objects get the scanout tranche
first. It changes only `src/protocols/LinuxDMABUF.cpp` and
`src/protocols/LinuxDMABUF.hpp`, and it does nothing unless
`render.direct_scanout` is enabled.

## 0003: skip direct scanout for buffers KMS can't take

A game on Wine Wayland presented 10-bit (XB30) buffers in a compressed layout
that KMS can't import. To try direct scanout, Hyprland switches the output
from XR24 to XB30. The test commit fails and the rollback switches it back.
Each switch is a modeset, so this repeated on every frame and the screen
stayed black.

The patch blocks direct scanout for buffers that aquamarine has already
marked as unimportable, and the rollback only resets the format when the
attempt changed it. The commit coordinator also restores the format after a
failed direct scanout commit, so the patch passes it the previous format only
when the attempt changed it. A bad buffer now costs one modeset, and Hyprland
composites the window instead. It changes only `src/output/Monitor.cpp`.

Drop this patch when upstream checks the buffer before changing the output
format in `CMonitor::attemptDirectScanout`.

## 0004: send the scanout tranche to windows that map fullscreen

Hyprland sends the scanout tranche to the window's solitary surface when the
window goes fullscreen. A window that is already fullscreen when it maps, as
some games on Wine Wayland are, can have no solitary surface at that moment.
Hyprland then skips the tranche and never sends it later. Without it,
NVIDIA's Vulkan driver picks a compressed layout that the display plane can't
scan out, and the window stays composited.

The patch passes the window's toplevel surface instead. 0001 already sends
the tranche to every feedback object under the toplevel, so windows that had
a solitary surface behave as before. Leaving fullscreen resets the feedback
the same way. It changes only
`src/managers/fullscreen/handler/FullscreenHandler.cpp` and
`src/layout/algorithm/tiled/scrolling/ScrollingFullscreenHandler.cpp`.

Drop this patch when upstream stops requiring the solitary surface before
sending the scanout tranche.

## 0005: start tearing from subsurface commits

Wine's Wayland driver presents into a subsurface. Hyprland only starts a torn
frame in `CWindow::commitWindow`, which runs when the window's own surface
commits. Wine's frames commit only the subsurface, so Wine Wayland windows
never tear. This is upstream issue
[#16035](https://github.com/hyprwm/Hyprland/issues/16035).

The patch moves the tearing check into `CWindow::checkTearing` and calls it
from `CSubsurface::onCommit` too. That call only happens when the committed
subsurface is the window's solitary resource, which is also the surface
direct scanout uses. Windows without such a subsurface go through the same
check as before. `damageSurface()` consumes the surface damage, so both
callers check for damage before calling it. It changes
`src/desktop/view/window/Window.cpp`, `src/desktop/view/window/Window.hpp`
and `src/desktop/view/Subsurface.cpp`.

Drop this patch when upstream fixes #16035.

## 0006: keep HDR signaling for SDR fullscreen windows

With a monitor set to `cm = "hdr"`, a fullscreen window whose surface has an
SDR image description, such as a browser playing video, made auto HDR send
SDR metadata to the display. Hyprland kept compositing for the PQ image
description, so the panel showed PQ pixels as SDR and colors were wrong.

The patch keeps the configured HDR metadata whenever the frame is composited.
An SDR buffer that is scanned out directly still gets SDR metadata. Auto HDR
also no longer changes the CM type of a monitor configured for HDR, so `hdr`
and `hdredid` stay as set. Monitors configured for SDR behave as before. It
changes only `src/render/Renderer.cpp`.

Drop this patch when upstream stops sending SDR metadata for composited
frames on a monitor configured for HDR.

## 0007: wait for the flip after a torn direct scanout commit

A composited torn frame marks the monitor busy until its page flip completes.
A frame that arrives in the meantime waits and is drawn on the next flip.
Direct scanout skipped this. While a game was tearing, its next frame often
came before the previous flip finished. aquamarine refused that commit, and
Hyprland went back to compositing and changed the output format, which is a
modeset. The next frame entered direct scanout again with another modeset.
The screen flickered and stayed at the refresh rate.

The patch marks the monitor busy after a torn direct scanout commit, the same
way composited tearing does. It also holds any torn frame while a page flip
is pending and draws it when the flip completes. That covers a vsync flip
from before tearing started, for example while the cursor was still visible.
It only matters when a window gets direct scanout and tearing at the same
time, which also needs the aquamarine patch in this repo. Without both, the
output switched between XB24 (the window's buffer) and XR24 (the compositor's
swapchain) on almost every frame. It changes `src/output/Monitor.cpp` and
`src/render/Renderer.cpp`.

Drop this patch when upstream holds torn commits until the previous flip
completes.

## 0008: tag presentation feedback with its commit

Hyprland tags queued presentation feedback with the commit that presents it,
and with whether that commit tore or used VRR. The check in
`CPresentationProtocol::tagQueued` is inverted. It skips the untagged entries
it should tag, so no feedback is ever tagged. Clients are told that every
frame waited for vblank, torn frames included, and a failed commit doesn't
discard its feedback. The patch inverts the check. It changes only
`src/protocols/PresentationTime.cpp`.

Drop this patch when upstream fixes the check in `tagQueued`.

## 0009: show top layers mapped over a fullscreen window

A fullscreen window hides the top layers under it. A top layer that maps
while the window is already fullscreen, like a notification or an OSD, is
still drawn above it by default
(`layers:allow_new_top_layers_over_existing_fullscreen`). 0.57.0 stopped
letting top layers block the solitary state. While a window is solitary,
Hyprland scans it out or draws only that window, so these layers were not
shown.

The patch lets a top layer that is allowed above the fullscreen window and
not faded out block solitary again, the same way overlay layers do. Top
layers hidden under the window, such as a bar, still don't. It changes only
`src/output/Monitor.cpp`.

Drop this patch when upstream checks top layers above a fullscreen window in
`CMonitor::isSolitaryBlocked`.

## 0010: accept tearing hints from subsurfaces

A game asks for tearing with the tearing control protocol when its vsync is
off. Hyprland only applies the hint when it is set on a window's own surface.
Wine's Wayland driver presents into a subsurface, so its games could only
tear through an `immediate` window rule, which also ignores the game's vsync
setting.

The patch applies a hint set on a subsurface to the window at the root of the
surface tree. Each game then tears or waits for vblank according to its own
vsync setting. It changes only `src/protocols/TearingControl.cpp`.

Drop this patch when upstream applies tearing hints from subsurfaces.

## Validation

Tested on 0.56.2 with an RTX 5080 and a 3440x1440 240 Hz QD-OLED, in SDR with
VRR off.

- 0001 with `direct_scanout = 1`: a Vulkan game on Wine Wayland, in windowed
  fullscreen with the Steam overlay off, scanned out in 72 of 180 timeline
  samples and resumed scanout after workspace switches. Stock Hyprland with
  scanout on turned the same game black 1 to 2 s after its workspace was
  shown. Unrelated fullscreen and focus hangs also happened with scanout off.
- 0003 and 0004 with `direct_scanout = 2`: a game on Wine Wayland that
  presents XB30 buffers scans out from a cold launch with no import failures.
  Leaving fullscreen resets the feedback, and each switch between the game and
  another workspace costs one modeset.
- 0005: a D3D11 game on Wine Wayland with an `immediate` window rule tears
  during gameplay. It never tore without the patch. Tearing stops in menus
  with a cursor, on workspace switches and when the window leaves fullscreen,
  and it comes back each time. A game on Wine Wayland set up for direct
  scanout still scans out and doesn't tear. Known issue: once, a layer
  surface stopped getting frame callbacks while a game was tearing, and it
  stayed frozen until its client restarted. It could not be reproduced.
- 0007 with the aquamarine patch: a native Wayland game with `content =
  "game"` and `immediate = true` scanned out and tore in 229 of 261 samples
  without flicker, at about 800 fps instead of 240. Entering fullscreen cost a
  few modesets, and gameplay cost none. With the aquamarine patch alone, the
  same game flickered and modeset about 160 times a second.

Tested on 0.57.0 with the same setup:

- A bar and a per-window keyboard layout daemon kept working over the event
  and command sockets.
- 0007 with the aquamarine patch: the same game scanned out and tore in 271
  of 318 samples without flicker. Entering fullscreen no longer committed over
  a pending flip. When the game quit, Hyprland retried direct scanout with its
  destroyed buffer for under a second, at one modeset per try.
- 0010: a game on Wine Wayland, with no window rule, set the tearing hint
  with its vsync off and cleared it when vsync was turned on. It stayed at
  240 fps either way because its visible hardware cursor blocks tearing.

## References and diagnostics

- `references/scanout-feedback-upstream.patch` is the original export of
  0001, with its full commit message.
- `diagnostics/record-scanout.py <class>` records a 180 second scanout
  timeline from `hyprctl` for the windows with that class.
- `diagnostics/capture-only.sh` takes a grim screenshot and saves the monitor
  state before and after it.
- `diagnostics/collect-game-threads.sh <class>` dumps the threads of the
  window with that class with gdb, for example when it freezes. It needs sudo.

The scripts write their output next to themselves, and git ignores it.

## Build notes

- The build clones submodules too.
- `hyprctl version` shows the upstream commit and marks the tree as dirty.
- `ABI_PACKAGES` lists the hypr* libraries. Rebuild when any of them is
  updated.
- Before moving to a newer release, check whether upstream already has an
  equivalent fix.

## Rollback

To drop a patch, remove it from `patches/`, bump `PKGREL` and build again.
Install the new package, then log out and back in. For the unpatched package,
run `sudo pacman -S hyprland` and log out and back in.
