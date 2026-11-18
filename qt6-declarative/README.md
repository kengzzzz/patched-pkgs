# qt6-declarative

Qt Declarative 6.12.0 built like Arch's `6.12.0-3`, with one extra patch.

## 0001 and 0002: Arch's backports

The two upstream commits Arch cherry-picks:

- 0001 is 8c23f65ec4, "QML engine: Correctly compare composites when multiple
  engines are used"
- 0002 is 7214a32024, "Fix teardown hang with QuickPixmapReader"

Drop them once the pinned tag contains them.

## 0003: recreate an out-of-date swapchain in the threaded render loop

A Vulkan swapchain can go out of date without a size change. The threaded
render loop recreates it only on resize, so it retried forever. Both threads
spun at full speed and the window never drew again.

The patch recreates the swapchain on the next frame after an out-of-date
result, as it does after a resize.

Drop it once upstream recreates out-of-date swapchains itself.

## Build notes

- `ABI_PACKAGES` makes the build fail unless qt6-base matches the host.
- Build Quickshell against the same Qt version. It uses private
  qt6-declarative APIs.
- The build also produces `qt6-declarative-debug`.

## Rollback

Run `sudo pacman -S qt6-declarative`, then restart running Qt applications.
