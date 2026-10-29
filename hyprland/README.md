# hyprland

Hyprland 0.57.0 with twelve patches. The numbers carry over from earlier
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
A surface with an SDR image description that is scanned out directly still
gets SDR metadata. Auto HDR also no longer changes the CM type of a monitor
configured for HDR, so `hdr` and `hdredid` stay as set. Monitors configured for SDR behave as before. It
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

## 0011: keep top layers over a floating fullscreen window on scrolling

0009 only works while a top layer keeps the flag that allows it above the
fullscreen window. On the scrolling layout, every layout recalculation with a
floating fullscreen window clears that flag on all layers of the monitor.
Mapping a layer schedules a recalculation, so a notification or an OSD lost
the flag right after it mapped and stayed hidden behind the window.

The default fullscreen handler already hides top layers when a window goes
fullscreen. The patch stops the scrolling layout from hiding them again in
that branch, so layers mapped later keep the flag. Windows are handled as
before. It changes only
`src/layout/algorithm/tiled/scrolling/ScrollingFullscreenHandler.cpp`.

Drop this patch when upstream stops clearing layer flags on every
recalculation with a floating fullscreen window.

## 0012: keep a fullscreen window's format while it is composited

Direct scanout puts the output in the format of the window's buffers. When a
notification or an OSD covers the window, Hyprland composites again. It went
back to its own format for that, and to the window's format again when the
OSD faded. Each switch reallocated Hyprland's swapchain. For a window whose
buffers use another format than Hyprland's, like a game in XB24 or a browser
in AB24 against XR24, the screen went black for 2 to 3 refreshes when scanout
resumed.

The patch keeps the window's format for composited frames while the window
stays fullscreen on the monitor, so an OSD changes neither the format nor the
swapchain. Only 8 bit, 10 bit and half float RGB formats are kept, half float
only when the GPU can render into it. In HDR, the window's own HDR metadata is
kept along with its format, and Hyprland only sends metadata again when it
changes, since every metadata change is a modeset. Hyprland goes back to its
own format and metadata when the window leaves fullscreen or closes, when
another window becomes fullscreen, when a composited commit fails and when a
monitor rule is applied.

It also fixes three problems on the same path:

- The first composited frame after a format change was drawn into a buffer in
  the old format, which the commit replaced with an empty buffer. Leaving
  direct scanout showed one blank frame. Hyprland now matches the swapchain to
  the output format before it draws.
- A screenshot or screen share that started while the output used a window's
  AB24 format failed. It now gets Hyprland's own format.
- A monitor rule applied during direct scanout, like switching to 10 bit, was
  undone when scanout ended.

It changes `src/output/Monitor.cpp`, `src/output/Monitor.hpp`,
`src/output/OutputCommitCoordinator.cpp` and `src/render/Renderer.cpp`.

Drop this patch when upstream keeps the scanout format while a fullscreen
window is briefly composited.

## 0013: keep the configured HDR metadata for HDR fullscreen windows

With a monitor set to `cm = "hdr"`, Hyprland sent the HDR metadata of a
fullscreen window's surface while it scanned the window out directly, and the
monitor's own metadata otherwise. Some displays blank for about a second on
every metadata change, so entering or leaving fullscreen and switching
workspaces blanked the screen. A browser in HDR sent fixed default values
there, not data from the video, so the switch gained nothing.

The patch keeps the monitor's metadata for surfaces with the PQ transfer
function, in direct scanout too, while the monitor is configured for HDR. A
client that sends real mastering data loses that hint, and the display
handles highlights above its own peak without it. Surfaces with an SDR image
description still get SDR metadata in direct scanout, and auto HDR still
passes the surface's metadata through. The metadata part of 0012 then only
matters for auto HDR. It changes only `src/render/Renderer.cpp`.

Drop this patch when upstream can keep the monitor's HDR metadata for
fullscreen windows.

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
- 0009 and 0011 on the scrolling layout: a native Wayland game in floating
  fullscreen with direct scanout and tearing. Each volume OSD showed above it,
  blocked solitary for 2 to 4 seconds, and scanout and tearing resumed after
  it faded.
- 0012 with the aquamarine patches: about 14 OSD cycles over a fullscreen
  browser video in AB24 and 5 over the same game in XB24. The output kept the
  window's format under every OSD, the swapchain was never reallocated, and
  the black frames on scanout resume were gone. In HDR the format and the HDR
  metadata stayed under every OSD and screenshot, with no modeset.
- 0013 in HDR with `cm_auto_hdr = 0`: a browser video entered and left
  fullscreen, and its workspace was switched away and back. The connector's
  HDR metadata stayed at the monitor's values the whole time, and the monitor
  never blanked. Composited frames, like those under an OSD, looked a bit
  darker than direct scanout because Hyprland tone-maps the video. A window
  rule with `tonemap = "off"` removed the difference.
- An SDR game in HDR: with the default `render.non_shader_cm`, Hyprland
  scanned it out with SDR metadata, so the monitor left HDR while the game was
  scanned out. With `non_shader_cm = "ondemand"`, the game stayed composited
  and the monitor stayed in HDR, at a lower frame rate.

## References and diagnostics

- `references/scanout-feedback-upstream.patch` is the original export of
  0001, with its full commit message.
- `diagnostics/record-scanout.py <class>` records a 180 second scanout
  timeline from `hyprctl` for the windows with that class.
- `diagnostics/record-overlay.py <monitor> [seconds]` logs the solitary,
  scanout, tearing and format state and the above fullscreen flag of each
  layer whenever one of them changes.
- `diagnostics/capture-only.sh` takes a grim screenshot and saves the monitor
  state before and after it.
- `diagnostics/collect-game-threads.sh <class>` dumps the threads of the
  window with that class with gdb, for example when it freezes. It needs sudo.
- `diagnostics/capture-stalls.py <process> [game log]` samples Hyprland and
  game thread states and `hyprctl` latency until Ctrl-C. When the game stops
  using CPU, it saves the last 3 seconds. It shows whether Hyprland was
  blocked in a commit, idle, or still rendering. The game log is copied on
  every game exit.
- `diagnostics/latency/live/run.sh scanout|composited` measures the time
  from a test client's commit to the page flip on the focused monitor, with
  vsync, uncapped and with tearing. `composited` turns direct scanout off.
  It runs on workspace 9, hides the cursor after 1 second and restores the
  settings it changed. Keep the mouse still while it runs.
- `diagnostics/latency/vm/setup.sh` builds stock and patched Hyprland and
  aquamarine and a KVM guest with a virtual display. `vm/run.sh` compares
  them on direct scanout, OSDs and fullscreen changes, with a checksum of
  every displayed frame and the CPU instructions per frame. The guest has
  no async page flips or HDR metadata, so tearing and HDR need the live
  test. The results are in `diagnostics/latency/RESULTS.md`.

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
