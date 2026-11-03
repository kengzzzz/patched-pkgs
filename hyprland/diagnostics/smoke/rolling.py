#!/usr/bin/env python3
"""rolling.py <out>: write Hyprland's log lines from now on to <out> until killed.

hyprland.log is written through a buffer, so recent lines can be missing from the file for minutes. The rolling log
in memory has them but keeps only the last 4 KB, so this polls it and appends what is new since the last poll."""

import subprocess
import sys
import time


def snapshot():
    try:
        return subprocess.run(["hyprctl", "rollinglog"], capture_output=True, text=True, timeout=2).stdout.splitlines()
    except subprocess.SubprocessError:
        return None


def overlap(prev, cur):
    for k in range(min(len(prev), len(cur)), 0, -1):
        if prev[-k:] == cur[:k]:
            return k
    return 0


prev = snapshot() or []
with open(sys.argv[1], "w", buffering=1) as out:
    while True:
        time.sleep(0.2)
        cur = snapshot()
        if cur is None:
            continue
        for line in cur[overlap(prev, cur):]:
            out.write(line + "\n")
        prev = cur
