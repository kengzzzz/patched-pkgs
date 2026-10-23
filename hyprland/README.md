# hyprland

Hyprland 0.56.2 with five patches.

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

## 0002: fix tearing

Backport of upstream PR
[#16572](https://github.com/hyprwm/Hyprland/pull/16572), merged after 0.56.2.
PR #15500 added an `isTearingBlocked()` check to the tearing branch in
`CWindow::commitWindow`. The check always fails because `nextRenderTorn` is
only set inside that branch, so tearing never starts on 0.56.x. The patch
removes the check. Upstream has since moved the file to
`src/desktop/view/window/Window.cpp`, and the backport uses the 0.56.2 path.

On NVIDIA, a window must not get tearing and direct scanout at the same time.
With both active, the output switched between XB24 (the window's buffer) and
XR24 (the compositor's swapchain) on almost every frame. Each switch was a
modeset, and the async commits failed with EINVAL. Use window rules
(`content` and `immediate`) to give each window one or the other.

Drop this patch when moving to a release that contains PR #16572.

## 0003: skip direct scanout for buffers KMS can't take

A game on Wine Wayland presented 10-bit (XB30) buffers in a compressed layout
that KMS can't import. To try direct scanout, Hyprland switches the output
from XR24 to XB30. The test commit fails and the rollback switches it back.
Each switch is a modeset, so this repeated on every frame and the screen
stayed black.

The patch blocks direct scanout for buffers that aquamarine has already
marked as unimportable, and the rollback only resets the format when the
attempt changed it. A bad buffer now costs one modeset, and Hyprland
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
check as before. It changes `src/desktop/view/Window.cpp`,
`src/desktop/view/Window.hpp` and `src/desktop/view/Subsurface.cpp`.

Drop this patch when upstream fixes #16035.

## Validation

Tested on an RTX 5080 with a 3440x1440 240 Hz QD-OLED, in SDR with VRR off.

- 0001 with `direct_scanout = 1`: a Vulkan game on Wine Wayland, in windowed
  fullscreen with the Steam overlay off, scanned out in 72 of 180 timeline
  samples and resumed scanout after workspace switches. Stock Hyprland with
  scanout on turned the same game black 1 to 2 s after its workspace was
  shown. Unrelated fullscreen and focus hangs also happened with scanout off.
- 0002: a native Wayland game never tore before the patch. With it, the game
  tore in every sample taken during gameplay and ran above 240 fps.
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
