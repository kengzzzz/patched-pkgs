# egl-wayland2

egl-wayland2 1.0.2 with one patch.

## 0001: drain wl_buffer.release events with explicit sync

With explicit sync, each `wl_buffer` sits on a private queue that is never
read. Every frame leaves one release event there. At 240 fps this leaks 3 to
4 MiB per minute in every EGL Wayland app.

The patch adds an empty release listener and reads the queue once per
`eglSwapBuffers`.

Upstream tracks this in NVIDIA/egl-wayland2 issue #51. Drop the patch once a
tagged release fixes it.

Restart EGL apps after installing.

## Rollback

Run `sudo pacman -S egl-wayland2`, then restart EGL apps.
