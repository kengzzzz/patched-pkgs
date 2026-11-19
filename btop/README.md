# btop

btop 1.4.8 built like Arch's `1.4.8-1`, with two patches for the process box.

Since 1.4.8, every process box key also redraws the CPU box, so that the
`- +` update buttons turn gray in tree view. Both patches change that redraw.

## 0001: no crash or blank screen when the CPU box is hidden

The redraw also runs when the CPU box is hidden and has no size. Keys like `f`
or Down in the process box then abort btop with a libstdc++ assertion, or
clear the screen and show "No boxes shown!".

The patch redraws the CPU box only when it is shown. Upstream merged the same
fix in PR #1967. Drop this patch once a release includes it.

## 0002: no extra CPU sample on process box keys

Keys that reload the process list, like `e` or sorting in tree view, make the
CPU box redraw take a new sample too. Each press adds a point to the CPU graph,
measured over a much shorter interval than the update time.

The patch redraws the CPU box from the last sample. Drop it once upstream does
the same.

## Rollback

Run `sudo pacman -S btop`, then restart btop.
