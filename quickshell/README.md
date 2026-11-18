# quickshell

Quickshell 0.3.2 with three patches.

## 0001: reconnect the Hyprland event socket

Hyprland drops an event socket client that falls 64 events behind. Quickshell
logs `PeerClosedError` and never reconnects, so workspaces, monitors and
windows go stale until restart.

The patch reconnects with a backoff from 100 ms to 5 s, then reloads monitors,
workspaces and windows.

## 0002: render every window through one shared VkDevice

With the threaded render loop, each window creates its own VkDevice. On NVIDIA
each one uses about 67 MB and 5 driver threads. Destroying one when a window
hides can block the GUI thread for 10 to 15 s.

The patch creates one VkDevice with up to 16 queues and gives each window a
queue of its own. When all queues are in use, a window gets its own device and
Quickshell logs `All 16 shared Vulkan queues are in use`.

It applies only with `QSG_RHI_BACKEND=vulkan`. Set `QS_NO_SHARED_VK_DEVICE=1`
to turn it off.

## 0003: serialize theme icon access

`QIcon` is not thread safe. Async images load icons on the pixmap reader
thread while other code uses `QIcon` on the GUI thread. When both reach the
same icon, Quickshell can crash in `QPlatformPixmap::fromFile` or fail to
load the icon.

The patch guards theme icon access with one mutex, in the `image://icon`
provider, `Quickshell.iconPath(name, true)`, `Quickshell.hasThemeIcon` and
tray icon rendering. The provider returns a deep copy.

It does not cover:

- `qsimage` and `qspixmap` URLs. Load them synchronously.
- Qt's own theme change handling on the GUI thread.

Drop it when upstream serializes theme icon access or keeps it on the GUI
thread.

## Build notes

- `ABI_PACKAGES` makes the build fail unless qt6-base, qt6-declarative and
  qt6-wayland match the host. Quickshell uses private Qt APIs.
- The build also produces `quickshell-debug`.

## Rollback

Run `sudo pacman -S quickshell`, then `systemctl --user restart quickshell`.
