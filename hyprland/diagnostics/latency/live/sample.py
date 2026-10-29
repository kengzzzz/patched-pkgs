#!/usr/bin/env python3
"""Sample the tearing, direct scanout and solitary state of every monitor four times a second."""

import json
import subprocess
import sys
import time

KEYS = ("name", "activelyTearing", "directScanoutTo", "solitary", "currentFormat", "tearingBlockedBy", "directScanoutBlockedBy", "solitaryBlockedBy")

with open(sys.argv[1], "w", buffering=1) as out:
    while True:
        t = time.monotonic_ns()
        try:
            monitors = json.loads(subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=2).stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError):
            monitors = []
        for m in monitors:
            out.write(json.dumps({"t": t, **{k: m.get(k) for k in KEYS}}) + "\n")
        time.sleep(0.25)
