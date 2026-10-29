# qt6-declarative

Qt Declarative 6.12.0 built like Arch's `6.12.0-3`, with one extra patch.

## 0001 and 0002: Arch's backports

These are the two upstream commits Arch cherry-picks:

- 0001 is 8c23f65ec4, "QML engine: Correctly compare composites when multiple
  engines are used"
- 0002 is 7214a32024, "Fix teardown hang with QuickPixmapReader"

Drop them once the pinned tag contains them.

## 0003: recreate an out-of-date swapchain in the threaded render loop

A Vulkan swapchain can go out of date while its size stays the same. With
NVIDIA on Wayland, this has happened to a long-running window, and from then
on `QRhi::beginFrame()` returned `FrameOpSwapChainOutOfDate` on every frame.
The threaded render loop recreates the swapchain only when the size changes, so
it keeps retrying. The GUI and render threads spin at full speed and the window
never draws again.

With the patch, the loop remembers an out-of-date result from `beginFrame()` or
`endFrame()` and recreates the swapchain on the next frame, the same way it
does after a resize. If that fails, it skips the frame and tries again on the
next one. Only the threaded render loop is patched.

Drop it once upstream recreates out-of-date swapchains itself.

## Build notes

- `ABI_PACKAGES` makes the build fail unless qt6-base matches the host. Qt
  modules use each other's private APIs.
- Quickshell uses private qt6-declarative APIs, so build both against the same
  Qt version.
- The build also produces `qt6-declarative-debug` with full debug symbols.

## Rollback

Run `sudo pacman -S qt6-declarative`, then restart running Qt applications.
