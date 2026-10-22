#!/usr/bin/env python3
"""Record a three-minute, read-only timeline around game/workspace changes."""

from datetime import datetime
import json
from pathlib import Path
import subprocess
import time


def query(*arguments):
    result = subprocess.run(
        ["hyprctl", "-i", "0", *arguments],
        capture_output=True, text=True, timeout=3, check=True,
    )
    return result.stdout


path = Path(__file__).resolve().parent / (
    "scanout-timeline-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".jsonl"
)
print(f"Recording for 180 seconds: {path}", flush=True)
with path.open("w") as output:
    for _ in range(180):
        started = time.monotonic()
        record = {"time": datetime.now().astimezone().isoformat()}
        try:
            record["scanout_setting"] = query("getoption", "render:direct_scanout").strip()
            record["game"] = [
                {key: client.get(key) for key in (
                    "pid", "address", "fullscreen", "fullscreenClient",
                    "xwayland", "workspace", "size",
                )}
                for client in json.loads(query("clients", "-j"))
                if client.get("class") == "steam_app_2694490"
            ]
            record["monitors"] = [
                {key: monitor.get(key) for key in (
                    "name", "activeWorkspace", "solitary", "solitaryBlockedBy",
                    "directScanoutTo", "directScanoutBlockedBy", "currentFormat",
                )}
                for monitor in json.loads(query("monitors", "-j"))
            ]
        except (subprocess.SubprocessError, ValueError) as error:
            record["error"] = str(error)
        output.write(json.dumps(record) + "\n")
        output.flush()
        time.sleep(max(0, 1 - (time.monotonic() - started)))
print(f"Finished: {path}", flush=True)
