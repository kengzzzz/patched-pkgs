# hyprland

Hyprland 0.56.2 with one patch.

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

## Build notes

- The build clones submodules too.
- `hyprctl version` shows the upstream commit and marks the tree as dirty.
- `ABI_PACKAGES` lists the hypr* libraries. Rebuild when any of them is
  updated.
- Before moving to a newer release, check whether upstream already has an
  equivalent fix.

## Rollback

Run `sudo pacman -S hyprland`, then log out and back in.
