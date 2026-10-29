#!/usr/bin/env python3
"""Log solitary, direct scanout, tearing and layer flags whenever they change."""

from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

if len(sys.argv) not in (2, 3):
    sys.exit(f"Usage: {sys.argv[0]} <monitor> [seconds]")
monitor_name = sys.argv[1]
duration = float(sys.argv[2]) if len(sys.argv) == 3 else 300

here = Path(__file__).resolve().parent
layers_file = here / "overlay-layers-now.txt"
path = here / ("overlay-timeline-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt")

# hyprctl eval only prints "ok", so the layer list goes through a file
layers_eval = (
    f"local f = io.open('{layers_file}', 'w') "
    "for _, l in ipairs(hl.get_layers()) do "
    "f:write(string.format('%s/L%d/mapped=%s/above_fs=%s ', l.namespace, l.layer, "
    "tostring(l.mapped), tostring(l.above_fullscreen))) "
    "end f:close()"
)


def hyprctl(*arguments):
    return subprocess.run(["hyprctl", *arguments], capture_output=True, text=True, timeout=2).stdout


def snapshot():
    monitor = next(m for m in json.loads(hyprctl("monitors", "-j")) if m["name"] == monitor_name)
    hyprctl("eval", layers_eval)
    layers = layers_file.read_text().strip()
    fullscreen = [
        f"{c['class']}:{c['fullscreen']}:floating={c['floating']}:xwayland={c['xwayland']}"
        for c in json.loads(hyprctl("clients", "-j"))
        if c.get("fullscreen")
    ]
    return (
        f"solitary={monitor['solitary']} blocked={monitor['solitaryBlockedBy']} "
        f"scanout={monitor['directScanoutTo']} scanoutBlocked={monitor['directScanoutBlockedBy']} "
        f"tearing={monitor['activelyTearing']} format={monitor['currentFormat']} "
        f"fullscreen={fullscreen} layers: {layers}"
    )


print(f"Recording for {duration:.0f} seconds: {path}", flush=True)
last = None
end = time.monotonic() + duration
with path.open("w") as output:
    while time.monotonic() < end:
        try:
            state = snapshot()
        except (subprocess.SubprocessError, ValueError, StopIteration, OSError) as error:
            state = f"error {error}"
        if state != last:
            output.write(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {state}\n")
            output.flush()
            last = state
        time.sleep(0.05)
print(f"Finished: {path}", flush=True)
