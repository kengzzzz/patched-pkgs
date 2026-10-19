# quickshell

Quickshell 0.3.2 with two patches.

## 0001: reconnect the Hyprland event socket

Hyprland disconnects an event socket client when 64 events are waiting for
it, for example while the client is busy. Quickshell 0.3.2 logs
`Hyprland event socket error: PeerClosedError` and never reconnects.
Workspaces, monitors and windows then stay out of date until restart.

The patch:

- reconnects after 100 ms, doubling the delay up to 5 s
- reloads monitors, workspaces, windows and the active window after
  reconnecting
- removes windows that closed while it was disconnected, and keeps windows
  that opened during the reload

## 0002: render every window through one shared VkDevice

With the threaded render loop, every QQuickWindow creates its own VkDevice. On
NVIDIA 615.78.08 each device uses about 67 MB of memory and 5 driver threads.
Destroying one when a window hides can block the GUI thread for 10 to 15 s.

The patch:

- creates one VkDevice with up to 16 queues on the first window, with the same
  extensions and features Qt would enable
- gives every window that device and a queue of its own through
  `QQuickGraphicsDevice::fromDeviceObjects`. Qt never destroys a device it did
  not create, and each window only waits on its own queue.
- frees a window's queue after the window and its renderer are destroyed
- falls back to a separate device when all queues are in use, and logs
  `All 16 shared Vulkan queues are in use`

It applies only with `QSG_RHI_BACKEND=vulkan`. Set `QS_NO_SHARED_VK_DEVICE=1`
to turn it off.

## Build notes

- Quickshell uses private Qt APIs. `ABI_PACKAGES` makes the build fail unless
  qt6-base, qt6-declarative and qt6-wayland match the host's versions.
- The build also produces `quickshell-debug` with full debug symbols.

## Rollback

Run `sudo pacman -S quickshell`, then `systemctl --user restart quickshell`.
