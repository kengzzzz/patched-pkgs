#!/usr/bin/env python3
"""Verdicts for live.sh results."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

S = 1_000_000_000

run = Path(sys.argv[1])
monitor = (run / "monitor").read_text().strip()
phases = {name: int(t) for name, t in (line.split() for line in open(run / "phases.txt"))}
states = [d for d in map(json.loads, open(run / "state.txt")) if d["name"] == monitor]
log = (run / "hyprland.log").read_text(errors="replace")


def window(a, b):
    return [s for s in states if a <= s["t"] < b]


def scanning(s):
    return s["directScanoutTo"] not in ("0", "", None)


def mostly(w, pred):
    return bool(w) and sum(map(pred, w)) >= 0.8 * len(w)


def tearing_scanout(s):
    return scanning(s) and s["activelyTearing"]


def feedback(name):
    return [line.split() for line in open(run / name) if line.startswith("FB ")]


checks = []


def check(desc, ok):
    checks.append((desc, bool(ok)))


t = phases["tear"]
check("direct scanout with tearing (0007)", mostly(window(t + 2 * S, t + 8 * S), tearing_scanout))
check("the client's feedback gets the scanout tranche (0001)", any(f[4] == "scanout=1" for f in feedback("tear.txt")))

clients = [c for c in json.loads((run / "clients-osd.json").read_text()) if c["class"] == "abgame"]
check("the OSD test ran on a floating fullscreen window", clients and clients[0]["floating"] and clients[0]["fullscreen"])
maps, unmaps = {}, {}
for line in open(run / "osd.txt"):
    p = line.split()
    if p[0] in ("MAP", "UNMAP"):
        (maps if p[0] == "MAP" else unmaps)[p[1]] = int(p[2])
cycles = [(maps[c], unmaps[c]) for c in sorted(maps) if c in unmaps]
shown = [window(m + S // 3, u) for m, u in cycles]
check("each OSD stops direct scanout, so it is visible (0009, 0011)", len(cycles) == 3 and all(w and not any(map(scanning, w)) for w in shown))
# hyprctl may not name the client's format, so compare with what it shows during direct scanout
before = [s["currentFormat"] for s in window(phases["osd"] + S, cycles[0][0]) if scanning(s)] if cycles else []
ds_format = Counter(before).most_common(1)[0][0] if before else None
check("the window's format stays under the OSD (0012)", len(cycles) == 3 and ds_format not in (None, "XRGB8888")
      and all(w and all(s["currentFormat"] == ds_format for s in w) for w in shown))
check("direct scanout and tearing resume after each OSD", len(cycles) == 3 and all(any(map(tearing_scanout, window(u + S, u + 2 * S))) for _, u in cycles))

t = phases["sub"]
check("tearing from a subsurface (0005, 0010)", mostly(window(t + 2 * S, t + 8 * S), tearing_scanout))

t = phases["ab30"]
check("direct scanout of a 10-bit client without a modeset", mostly(window(t + 2 * S, t + 8 * S), lambda s: scanning(s) and s["currentFormat"] != "XRGB8888")
      and "without a modeset, format AB30" in log)

if "vkcube" in phases:
    t = phases["vkcube"]
    check("direct scanout of a fullscreen Vulkan client (0001, 0004)", mostly(window(t + 4 * S, t + 8.5 * S), scanning))

check("no commit over a pending flip (0007)", "page-flip is awaiting" not in log)
check("no failed format change without a modeset (aquamarine 0002)", "without a modeset failed" not in log)
check("no max_bpc retry (aquamarine 0002)", "retrying without max_bpc" not in log)
check("no modeset (aquamarine 0002)", "drm: Modesetting" not in log)

width = max(len(d) for d, _ in checks) + 2
for desc, ok in checks:
    print(f"{desc:{width}}{'pass' if ok else 'FAIL':>6}")
print(f"{'format changes without a modeset':{width}}{len(re.findall(r'without a modeset, format', log)):>6}")
sys.exit(0 if all(ok for _, ok in checks) else 1)
