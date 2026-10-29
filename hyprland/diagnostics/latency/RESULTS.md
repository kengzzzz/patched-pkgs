# Latency results

Hyprland 0.57.0-1.11 and aquamarine 0.15.1-1.7 from this repo, on an RTX 5080
with driver 615.78.08 and a 3440x1440 240 Hz QD-OLED over DisplayPort, in
SDR with VRR off.

(current) is the setup in use: `direct_scanout = 1` and
`allow_tearing = true`. (upstream) is upstream's default: `direct_scanout = 0`
and `allow_tearing = false`. The upstream rows use the same build with those
settings. The patches only add a few checks on that path, and the VM
comparison below shows the same steady latency for stock and patched builds.

## Commit to flip

`live/run.sh` measures the time from the client's commit to the page flip
timestamp the kernel reports. It doesn't include the game's own rendering or
the display's processing. The client is fullscreen with XB24 buffers from the
GPU. With vsync it draws a frame each time Hyprland asks for one. With vsync
off it commits every 2 ms, which is 500 fps, and asks for tearing through the
tearing control protocol. Each row covers 13 to 18 seconds, 3,100 to 9,000
frames. Times are in ms.

Game with vsync on:

| Setup | avg | median | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| Direct scanout (current) | 8.228 | 8.247 | 8.686 | 8.711 |
| Composited (upstream) | 8.097 | 8.139 | 8.189 | 8.226 |

Game with vsync off:

| Setup | avg | median | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| Direct scanout, tearing (current) | 0.066 | 0.055 | 0.125 | 0.147 |
| Composited, tearing | 0.176 | 0.154 | 0.304 | 0.360 |
| Direct scanout, no tearing | 5.187 | 5.218 | 6.133 | 6.614 |
| Composited, no tearing (upstream) | 5.167 | 5.167 | 6.074 | 6.152 |

- With vsync, a frame is shown 2 refreshes after the client commits it,
  8.33 ms at 240 Hz. Hyprland asks for the next frame while the current one
  waits for its flip.
- Direct scanout looks 0.13 ms slower with vsync, but both setups show every
  frame 2 refreshes after the one in which the client committed. Hyprland
  wakes the client about 0.1 ms after each flip with direct scanout and about
  0.2 ms after when it composites first, so the client only starts earlier.
  The wider p95 and p99 come from the flip completion times reported for
  direct scanout. They are spread about 0.5 ms around the fixed refresh.
- Without tearing, direct scanout and compositing take the same time. The
  flip waits for the next refresh either way.
- With tearing, direct scanout skips the composite pass and saves about
  0.1 ms.
- "Direct scanout, no tearing" is what the current setup gives a game that
  doesn't ask for tearing.
- The client barely uses the GPU. A game that keeps the GPU busy can delay
  the composite pass, so the composited rows may be higher in real games.
  That is not measured here.

After an OSD or a notification, tearing starts again once the layer has
faded out, about 500 ms with a 500 ms fade. The first 1 or 2 torn frames
then take 0.3 to 2 ms, because 0007 holds them until the last vsync flip
completes.

## Stock and patched in a VM

`vm/run.sh` runs both builds in a KVM guest with vkms at 1280x720 and 60 Hz,
4 rounds of 3 clients each. The guest has no async page flips or HDR
metadata, so tearing and HDR are not covered. Modesets cost almost nothing in
vkms, so the stock penalty on a real display is larger than these numbers
show. Each run shows 11 OSDs and leaves and reenters fullscreen 5 times.

| | stock | patched |
| --- | ---: | ---: |
| Modesets per run | 30 | 1 |
| Swapchain reallocations per run | 30 | 12 |
| OSD visible after, median | 3 frames | 2 frames |
| OSD gone after, median | 2 frames | 2 frames |
| Bad frames, client that redraws every frame | 1 per OSD | 0 |
| Bad frames, client that redraws little | 240 per 8 OSDs, 310 in 15 s under an OSD | 0 |
| Commit to present, steady | 2 frames | 2 frames |

The bad frames are the first composited frame drawn in the old format, which
0012 fixes, and buffers drawn with a wrong age, which aquamarine 0003 fixes.
With a client in XR24, the same format as Hyprland's, neither build modesets
after startup or shows bad frames.

The patched build runs a few more instructions per frame on Hyprland's main
thread: about 0.5k with direct scanout, 4k to 6k when composited, and 2.8k for
each commit from a subsurface, which comes from 0005. That is a few µs at
most, under 0.2% of a frame at 240 Hz.
