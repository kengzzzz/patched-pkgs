# hyprland

Hyprland 0.57.2 with seventeen patches. Numbers carry over from earlier
releases. 0002 was dropped because 0.57.0 includes upstream PR
[#16572](https://github.com/hyprwm/Hyprland/pull/16572). 0015 was dropped
because 0.57.2 includes upstream PR
[#16740](https://github.com/hyprwm/Hyprland/pull/16740).

## 0001: keep scanout dmabuf feedback for subsurfaces

Based on Rick Littel's commit
[8edefed](https://github.com/Kuret/Hyprland/commit/8edefed837199c53f8652b991415d331ac571a04).

Hyprland sends the scanout tranche only to feedback objects of the fullscreen
surface. Wine renders into a subsurface. NVIDIA's Vulkan driver creates a new
feedback object on each swapchain rebuild. An output change sends the default
tranche to subsurfaces. In all three cases the client allocates buffers that
can't be scanned out.

The patch sends the tranche to every feedback object under the scanout window,
including new ones, and keeps it across table rebuilds. It does nothing unless
`render.direct_scanout` is on.

Drop it when upstream sends the scanout tranche to subsurfaces and to feedback
objects created during scanout.

## 0003: skip direct scanout for buffers KMS can't take

Some games on Wine Wayland present XB30 buffers in a layout KMS can't import.
Hyprland switched the output format to try scanout, failed, and switched back.
That was two modesets per frame and a black screen.

The patch skips scanout for buffers aquamarine has marked as unimportable, and
resets the format only when the attempt changed it.

Drop it when upstream checks the buffer before changing the output format in
`CMonitor::attemptDirectScanout`.

## 0004: send the scanout tranche to windows that map fullscreen

A window that is already fullscreen when it maps can have no solitary surface
yet. Hyprland then never sends it the scanout tranche, and the window stays
composited.

The patch uses the toplevel surface instead. With 0001, that reaches every
feedback object under it.

Drop it when upstream stops requiring the solitary surface before sending the
scanout tranche.

## 0005: start tearing from subsurface commits

Hyprland starts a torn frame only when a window's own surface commits. Wine
commits only its subsurface, so Wine Wayland windows never tear. This is
upstream issue [#16035](https://github.com/hyprwm/Hyprland/issues/16035).

The patch runs the same tearing check when the window's solitary subsurface
commits.

Once, a layer surface stopped getting frame callbacks while a game was
tearing. It could not be reproduced.

Drop it when upstream fixes #16035.

## 0006: keep HDR signaling for SDR fullscreen windows

On a monitor with `cm = "hdr"`, an SDR fullscreen window such as a browser
video made auto HDR send SDR metadata. Hyprland still composited in PQ, so
colors were wrong.

The patch keeps the configured HDR metadata for composited frames. Auto HDR
no longer changes the CM type of a monitor set to `hdr` or `hdredid`. An SDR
surface in direct scanout still turns HDR metadata off, and aquamarine 0005
then clears the property.

Drop it when upstream stops sending SDR metadata for composited frames on an
HDR monitor.

## 0007: wait for the flip after a torn direct scanout commit

Composited tearing waits for the page flip before the next commit. Direct
scanout did not. The next torn frame failed, Hyprland fell back to
compositing, and each switch was a modeset. The screen flickered and stayed at
the refresh rate.

The patch marks the monitor busy after a torn scanout commit and holds a torn
frame until a pending flip completes. It needs aquamarine 0001.

Drop it when upstream holds torn commits until the previous flip completes.

## 0008: tag presentation feedback with its commit

The check in `CPresentationProtocol::tagQueued` is inverted, so no feedback is
tagged. Clients are told every frame waited for vblank, and a failed commit
keeps its feedback. The patch inverts the check.

Drop it when upstream fixes the check.

## 0009: show top layers mapped over a fullscreen window

A notification or OSD that maps over a fullscreen window should show above it.
Since 0.57.0 top layers no longer block the solitary state, so Hyprland
scanned out the window and hid the layer.

The patch lets a mapped top layer that is allowed above the window block
solitary again. It stops blocking as soon as it unmaps. Hidden top layers such
as a bar still don't block.

Drop it when upstream checks top layers in `CMonitor::isSolitaryBlocked`.

## 0010: accept tearing hints from subsurfaces

Hyprland applies a tearing hint only from a window's own surface. Wine sets it
on a subsurface, so its games could only tear through an `immediate` window
rule.

The patch applies a subsurface's hint to its root window, so each game follows
its own vsync setting.

Drop it when upstream applies tearing hints from subsurfaces.

## 0011: keep top layers over a floating fullscreen window on scrolling

On the scrolling layout, each recalculation with a floating fullscreen window
clears the flag 0009 needs on every layer. Mapping a layer triggers a
recalculation, so the OSD stayed hidden.

The patch stops the scrolling layout from hiding top layers again.

Drop it when upstream stops clearing layer flags on every recalculation.

## 0012: keep a fullscreen window's format while it is composited

When an OSD covered a scanned out window, Hyprland went back to its own format
and reallocated its swapchain. It switched again when the OSD faded. For
buffers in XB24 or AB24, the screen went black for 2 to 3 refreshes.

The patch keeps the window's format, and in HDR its metadata, while the window
stays fullscreen. It keeps only 8 bit, 10 bit and half float RGB. Hyprland
goes back to its own format when the window leaves fullscreen or closes,
another window goes fullscreen, a composited commit fails or a monitor rule is
applied.

It also fixes three bugs on the same path:

- The first composited frame after a format change was blank.
- A screenshot taken while the output used AB24 failed.
- A monitor rule applied during scanout was undone when scanout ended.

Drop it when upstream keeps the scanout format while a fullscreen window is
briefly composited.

## 0013: keep the configured HDR metadata for HDR fullscreen windows

On a monitor with `cm = "hdr"`, Hyprland sent a scanned out window's HDR
metadata and the monitor's metadata otherwise. Some displays blank for about a
second on each change. Browsers send fixed default values here anyway.

The patch keeps the monitor's metadata for PQ surfaces, in scanout too. A
client with real mastering data loses it. Auto HDR still passes surface
metadata through. Turning HDR off during scanout now turns metadata off at
once.

Drop it when upstream can keep the monitor's HDR metadata for fullscreen
windows.

## 0014: keep screenshots of HDR frames in SDR colors

In HDR, screenshots and screen shares read an SDR copy of each frame. Blurred
backgrounds and close animation snapshots went into it unconverted and came
out too dark. HDR surfaces used 80 nits as SDR white and came out too bright.

The patch converts FP16 textures back to SDR for the copy and maps an HDR
surface's reference white to SDR white. On HDR monitors without SDR changes,
the copy is drawn only while a capture or mirror runs.

It also fixes two upstream shader errors in the copy path. The inner glow
shader failed to compile. With `use_shader_blur_blend` and
`blur:proportional`, blurred windows weren't drawn.

Known limits:

- HDR content in a blurred background or snapshot comes out too bright.
- SDR saturation isn't undone for blur and snapshots.
- Borders in snapshots are a bit dark with `sdrbrightness` above 1.
- With `render:use_fp16 = 0`, only the HDR surface fix applies.

Drop it when upstream converts blurred backgrounds and HDR surfaces for the
SDR copy.

## 0016: process a surface's commit queue in one pass at a time

A commit listener can call `CSurfaceStateQueue::tryProcess` again while it is
running. The nested call applies and removes the same commit. Hyprland then
aborts, or drops a commit. A tearing game in direct scanout with a visible
cursor hit this.

The patch makes a nested call return at once. The outer pass still applies
whatever the nested call unlocked.

Drop it when upstream guards `tryProcess` against nested calls.

## 0017: no new session lock while the lock program runs

With `misc:allow_session_lock_restore` on, any Wayland client could replace a
running lock and then unlock the session without a password.

The patch refuses a new lock while the current one exists. A lock program
restarted after a crash still takes over. A hung lock program must be killed
first.

This only matters with `allow_session_lock_restore` on. After the lock program
dies, any program can still take the lock, and a program running as the user
can kill the lock program.

Drop it when upstream refuses a new session lock while the current lock's
program runs.

## 0018: blur a layer's fadeout the way the layer was blurred

A layer's fadeout snapshot followed the global `decoration:blur:xray`. The
mapped layer used live blur unless it had the `xray` rule. With global xray
on, a frosted panel turned into blurred wallpaper when it started to fade.

The patch gives the snapshot the layer's own blur choice. Live blur costs more
GPU time during the fade.

Drop it when upstream keeps a layer's blur choice for its fadeout.

## 0019: a fading layer shows its blur before its content

A blurred layer faded its blur and its pixels together, so its text overlapped
the sharp windows behind it.

The patch fades in the blur during the first half and the pixels during the
second. Closing runs backwards. Layers without blur and windows fade as
before. Layer popups that close on their own still fade the old way.

Drop it when upstream fades a blurred layer's blur ahead of its pixels.

## Diagnostics

Scripts in `diagnostics/` write their output next to themselves. Git ignores
it.

- `smoke/vm.sh` checks scanout, feedback, OSDs, outputs and session lock on
  stock and patched builds in a VM. Run it before installing. Never run it on
  the live session, because it takes the session lock.
- `smoke/live.sh` checks tearing, OSDs and GPU buffers on the running session.
  Run it after installing. The HDR patches 0006, 0013 and 0014 still need a
  manual check.
- `latency/` measures commit to flip time. Results are in
  `diagnostics/latency/RESULTS.md`.
- `record-scanout.py`, `record-overlay.py`, `capture-only.sh`,
  `capture-stalls.py` and `collect-game-threads.sh` log scanout state, layer
  state, screenshots, stalls and game threads.

`references/scanout-feedback-upstream.patch` is the original export of 0001.

## Build notes

- The build clones submodules.
- `hyprctl version` marks the tree as dirty.
- `ABI_PACKAGES` lists the hypr* libraries. Rebuild when one is updated.

## Rollback

Remove the patch from `patches/`, bump `PKGREL` and build again. For the
unpatched package, run `sudo pacman -S hyprland`. Log out and back in either
way.
