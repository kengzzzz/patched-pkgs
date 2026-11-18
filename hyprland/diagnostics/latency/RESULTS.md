# Latency results

Hyprland 0.57.0-1.11 and aquamarine 0.15.1-1.7 from this repo, on an RTX 5080
with driver 615.78.08 and a 3440x1440 240 Hz QD-OLED, in SDR with VRR off.

"Current" is `direct_scanout = 1` with `allow_tearing = true`. "Upstream" is
the default, `direct_scanout = 0` with `allow_tearing = false`, on the same
build.

## Commit to flip

`live/run.sh` measures from the client's commit to the kernel's page flip
timestamp. It excludes game rendering and display processing. The client is
fullscreen with XB24 buffers. With vsync off it commits every 2 ms and asks
for tearing. Each row is 3,100 to 9,000 frames. Times are in ms.

Vsync on:

| Setup | avg | median | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| Direct scanout, current | 8.228 | 8.247 | 8.686 | 8.711 |
| Composited, upstream | 8.097 | 8.139 | 8.189 | 8.226 |

Vsync off:

| Setup | avg | median | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| Direct scanout, tearing, current | 0.066 | 0.055 | 0.125 | 0.147 |
| Composited, tearing | 0.176 | 0.154 | 0.304 | 0.360 |
| Direct scanout, no tearing | 5.187 | 5.218 | 6.133 | 6.614 |
| Composited, no tearing, upstream | 5.167 | 5.167 | 6.074 | 6.152 |

- With vsync, both setups show each frame 2 refreshes after the commit.
  Direct scanout wakes the client earlier, so it only looks 0.13 ms slower.
- Without tearing, direct scanout and compositing take the same time.
- With tearing, direct scanout saves about 0.1 ms.
- The client barely uses the GPU. A busy game may make the composited rows
  slower.

After an OSD fades, about 500 ms, tearing resumes. The first 1 or 2 torn
frames take 0.3 to 2 ms, because 0007 holds them until the last vsync flip.

## Stock and patched in a VM

`vm/run.sh` runs both builds in a KVM guest with vkms at 1280x720 60 Hz. It
can't test tearing or HDR. Modesets cost almost nothing in vkms, so stock
does worse on real hardware. Each run shows 11 OSDs and toggles fullscreen 5
times.

| | stock | patched |
| --- | ---: | ---: |
| Modesets per run | 30 | 1 |
| Swapchain reallocations per run | 30 | 12 |
| OSD visible after, median | 3 frames | 2 frames |
| OSD gone after, median | 2 frames | 2 frames |
| Bad frames, client that redraws every frame | 1 per OSD | 0 |
| Bad frames, client that redraws little | 240 per 8 OSDs | 0 |
| Commit to present, steady | 2 frames | 2 frames |

Hyprland 0012 and aquamarine 0003 fix the bad frames. A client in XR24 shows
no modesets or bad frames on either build.

The patched build adds a few µs per frame at most, under 0.2% of a frame at
240 Hz.
