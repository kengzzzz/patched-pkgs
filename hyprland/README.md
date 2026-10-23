# hyprland

Hyprland 0.56.2 with four patches.

## 0001: keep scanout dmabuf feedback for subsurfaces

Taken from Rick Littel's commit
[8edefed](https://github.com/Kuret/Hyprland/commit/8edefed837199c53f8652b991415d331ac571a04).

When a window goes fullscreen, Hyprland sends the scanout tranche to only one
dmabuf feedback object. Two cases miss it:

- Wine renders into a subsurface, not the fullscreen surface.
- NVIDIA's Vulkan driver creates a new feedback object every time it
  recreates a swapchain.

These clients then allocate buffers that can't be used for direct scanout.

The patch tracks the surface tree of each scanout window, sends the tranche to
every feedback object in that tree, and gives new feedback objects the scanout
tranche first. It changes only `src/protocols/LinuxDMABUF.cpp` and
`src/protocols/LinuxDMABUF.hpp`.

The patch has no effect unless `render.direct_scanout` is enabled.

## 0002: fix tearing

Backport of upstream PR
[#16572](https://github.com/hyprwm/Hyprland/pull/16572), merged after 0.56.2.
PR #15500 added an `isTearingBlocked()` check to the tearing branch in
`CWindow::commitWindow`. That check always fails because `nextRenderTorn` is
only set inside the same branch, so tearing never starts on 0.56.x. The patch
removes the check. Upstream later moved the file to
`src/desktop/view/window/Window.cpp`. The backport uses the 0.56.2 path.

On NVIDIA, a window must not get tearing and direct scanout together. With
both active, the output switched between XB24 (game buffer) and XR24
(compositor swapchain) almost every frame. Each switch was a modeset, and the
async commits failed with EINVAL. Window rules (`content` and `immediate`)
give each game one or the other.

Drop this patch when moving to a release that contains PR #16572.

## 0003: skip direct scanout for buffers KMS can't take

Monster Hunter Wilds presented 10-bit (XB30) buffers with a compressed
layout that KMS can't import. To try direct scanout, Hyprland switches the
output from XR24 to XB30, the test commit fails, and the rollback switches it
back. Each switch is a modeset, so this happened on every frame and the screen
stayed black.

The patch blocks direct scanout for buffers that aquamarine has already
marked as unimportable. The rollback also only resets the format when the
attempt changed it. Each bad buffer now costs one modeset, and Hyprland
composites the window instead. It changes only `src/output/Monitor.cpp`.

Drop this patch when upstream checks the buffer before changing the output
format in `CMonitor::attemptDirectScanout`.

## 0004: send the scanout tranche to windows that map fullscreen

Hyprland sends the scanout tranche to the window's solitary surface when it
goes fullscreen. A window that is already fullscreen when it maps, like
Monster Hunter Wilds, can have no solitary surface at that moment. Hyprland
then skips the tranche and never sends it later. Without the tranche,
NVIDIA's Vulkan driver picks a compressed layout that the display plane can't
scan out, and the game stays composited.

The patch passes the window's toplevel surface instead. 0001 already sends
the tranche to every feedback object under the toplevel, so windows that had
a solitary surface behave as before. Leaving fullscreen resets the feedback
the same way. It changes only
`src/managers/fullscreen/handler/FullscreenHandler.cpp` and
`src/layout/algorithm/tiled/scrolling/ScrollingFullscreenHandler.cpp`.

Drop this patch when upstream stops requiring the solitary surface before
sending the scanout tranche.

## Validation

Tested on an RTX 5080 with a 3440x1440 240 Hz QD-OLED (DP-3), SDR, VRR off.

- 2026-10-14, 0001 with `direct_scanout = 1`: PoE2 on native Wayland
  (Vulkan, Windowed Fullscreen, Steam Overlay off) showed active scanout in 72
  of 180 timeline samples and resumed it after workspace switches. Stock
  Hyprland with scanout on had turned PoE2 black 1 to 2 s after its workspace
  was shown. Unrelated fullscreen and focus hangs also happened with scanout
  off.
- 2026-10-22, 0002: before the patch, native CS2 never tore
  (`activelyTearing` false in 20 of 20 samples). After it, CS2 tore in every
  in-match sample and ran above 240 fps.
- 2026-10-22, tearing plus direct scanout on one window: 49227 modesets and
  as many rejected async commits in one session. See the 0002 section.
- 2026-10-23, 0003 and 0004 with `direct_scanout = 2`: Monster Hunter Wilds
  (Proton, Wine Wayland, XB30) scans out from a cold launch with no import
  failures. Leaving fullscreen resets the feedback. Each switch between the
  game and another workspace costs one modeset.

The raw data (thread dumps, scanout timelines), the earlier README log and
build logs from the old `~/Data/hyprland-scanout` project are in
`dist/hyprland-scanout-archive.tar.zst`. It also holds the 4.3 package (0001
and 0002 with stock Arch flags).

## References and diagnostics

- `references/scanout-feedback-upstream.patch` is the original export of
  0001, with its full commit message.
- `diagnostics/record-scanout.py` records a 180 second scanout timeline from
  `hyprctl`. `capture-only.sh` takes a grim screenshot with monitor state
  before and after it. `collect-game-threads.sh` dumps the PoE2 threads with
  gdb when the game freezes and needs sudo. All three write their output next
  to themselves, and git ignores it.

## Build notes

- The build clones submodules too.
- `hyprctl version` shows the upstream commit and marks the tree as dirty.
- `ABI_PACKAGES` lists the hypr* libraries. Rebuild when any of them is
  updated.
- Before moving to a newer release, check whether upstream already has an
  equivalent fix.

## Rollback

Run `sudo pacman -S hyprland`, then log out and back in. To go back to 0001
to 0003, install the 4.6 package from `dist/0.56.2-4.6/` instead. For only
0001 and 0002, use `dist/0.56.2-4.4/`.
