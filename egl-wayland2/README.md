# egl-wayland2

egl-wayland2 1.0.2 with one patch.

## 0001: drain wl_buffer.release events with explicit sync

With explicit sync, each `wl_buffer` is attached to a private event queue
that has no release listener and is never read. Every presented frame leaves
one 216-byte `wl_buffer.release` event in that queue. At 240 fps on NVIDIA,
this leaks 3 to 4 MiB per minute in every EGL Wayland app.

The patch adds an empty release listener and reads the queue once per
`eglSwapBuffers`.

Upstream tracks the leak in NVIDIA/egl-wayland2 issue #51. PR #56 fixes it
differently. Drop this patch once a tagged release includes a fix.

Restart EGL apps after installing so they load the new library.

## Rollback

Run `sudo pacman -S egl-wayland2`, then restart EGL apps.
