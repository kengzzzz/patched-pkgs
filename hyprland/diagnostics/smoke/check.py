#!/usr/bin/env python3
"""Verdicts for vm.sh results: one line per check for the stock and patched builds."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

S = 1_000_000_000

# key, description, expected to fail on stock
CHECKS = [
    ("ds_root", "direct scanout of a fullscreen client", False),
    ("fb_root", "its feedback gets the scanout tranche", False),
    ("fb_root_new", "feedback created during scanout starts with it (0001)", True),
    ("fb_sub", "a subsurface's feedback gets the scanout tranche", False),
    ("fb_sub_new", "subsurface feedback created during scanout starts with it (0001)", True),
    ("fb_headless", "the tranche stays when an output is added or removed (0001)", True),
    ("ds_headless", "direct scanout stays when an output is added or removed", False),
    ("osd_blocks", "an OSD stops direct scanout", False),
    ("osd_resumes", "direct scanout resumes after each OSD", False),
    ("osd_format", "the client's format stays under the OSD (0012)", True),
    ("osd_clean", "no transient frames around the OSDs (0012, aquamarine 0003)", True),
    ("fs_ds", "direct scanout after each fullscreen toggle", False),
    ("fs_feedback", "feedback follows fullscreen toggles", False),
    ("no_fallbacks", "no failed format change without a modeset", False),
    ("alive", "Hyprland still runs at the end", False),
]


def load_phases(run):
    return [(name, int(t)) for name, t in (line.split() for line in open(run / "phases.txt"))]


def times(ph, name):
    return [t for p, t in ph if p == name]


def load_feedback(path):
    out = []
    for line in open(path):
        p = line.split()
        if p[0] == "FB":
            out.append({"t": int(p[1]), "id": int(p[2]), "first": p[3] == "first=1", "scanout": p[4] == "scanout=1"})
    return out


def load_states(run):
    return [d for d in map(json.loads, open(run / "state.txt")) if d["name"] != "SMOKE"]


def window(states, a, b):
    return [s for s in states if a <= s["t"] < b]


def scanning(s):
    return s["directScanoutTo"] not in ("0", "", None)


def mostly_scanning(w):
    return bool(w) and sum(map(scanning, w)) >= 0.8 * len(w)


def new_feedback_starts_scanout(fbs):
    start = next((f["id"] for f in fbs if f["scanout"]), None)
    if start is None:
        return False
    firsts = [f for f in fbs if f["first"] and f["id"] > start]
    return len(firsts) >= 2 and all(f["scanout"] for f in firsts)


def kept_across(fbs, marks):
    for m in marks:
        w = [f for f in fbs if m <= f["t"] < m + 2 * S]
        # a table rebuild resends the feedback to existing objects, so it shows up as a batch that isn't an object's first
        if not any(not f["first"] for f in w) or not all(f["scanout"] for f in w):
            return False
    return True


def analyze(run):
    ph = load_phases(run)
    st = load_states(run)
    r, info = {}, {}
    root, sub = times(ph, "root")[0], times(ph, "sub")[0]
    added, removed = times(ph, "headless-add")[0], times(ph, "headless-remove")[0]
    fb_root, fb_sub, fb_osd = (load_feedback(run / f) for f in ("root.txt", "sub.txt", "osd-game.txt"))

    r["ds_root"] = mostly_scanning(window(st, root + 2 * S, root + 7 * S))
    r["fb_root"] = any(f["scanout"] for f in fb_root)
    r["fb_root_new"] = new_feedback_starts_scanout(fb_root)
    r["fb_sub"] = any(f["scanout"] for f in fb_sub)
    r["fb_sub_new"] = new_feedback_starts_scanout(fb_sub)
    r["fb_headless"] = kept_across(fb_sub, [added, removed])
    r["ds_headless"] = mostly_scanning(window(st, removed + 1.5 * S, sub + 11.5 * S))

    maps, unmaps = {}, {}
    for line in open(run / "osd.txt"):
        p = line.split()
        if p[0] == "MAP":
            maps[p[1]] = int(p[2])
        elif p[0] == "UNMAP":
            unmaps[p[1]] = int(p[2])
    cycles = [(maps[c], unmaps[c]) for c in sorted(maps) if c in unmaps]
    shown = [window(st, m + S // 3, u) for m, u in cycles]
    r["osd_blocks"] = len(cycles) == 3 and all(w and not any(map(scanning, w)) for w in shown)
    r["osd_resumes"] = len(cycles) == 3 and all(any(map(scanning, window(st, u + S // 2, u + 1.4 * S))) for _, u in cycles)
    # hyprctl may not name the client's format, so compare with what it shows during direct scanout
    before = [s["currentFormat"] for s in window(st, times(ph, "osd")[0] + S, cycles[0][0]) if scanning(s)] if cycles else []
    ds_format = Counter(before).most_common(1)[0][0] if before else None
    r["osd_format"] = (len(cycles) == 3 and ds_format not in (None, "XRGB8888")
                       and all(w and all(s["currentFormat"] == ds_format for s in w) for w in shown))

    crc = []
    for line in open(run / "crc.txt"):
        p = line.replace("\x00", "").split()
        if len(p) == 3:
            crc.append((int(p[0]), p[2]))
    if cycles:
        counts = Counter(c for t, c in crc if cycles[0][0] - S <= t < cycles[-1][1] + S)
        # an image that shows for fewer than 10 vblanks is a glitch, every real state lasts longer
        info["transient frames around the OSDs"] = sum(v for v in counts.values() if v < 10)
        r["osd_clean"] = info["transient frames around the OSDs"] == 0
    else:
        r["osd_clean"] = False

    ons, offs = times(ph, "fs-on"), times(ph, "fs-off")
    r["fs_ds"] = len(ons) == 2 and all(any(map(scanning, window(st, t + 0.8 * S, t + 1.5 * S))) for t in ons)
    r["fs_feedback"] = (len(ons) == 2 and all(any(f["scanout"] for f in fb_osd if t <= f["t"] < t + S) for t in ons)
                        and all(any(not f["scanout"] for f in fb_osd if t <= f["t"] < t + S) for t in offs))

    log = (run / "hyprland.log").read_text(errors="replace")
    a, b = log.find("SMOKEMARK root"), log.find("SMOKEMARK end")
    played = log[a:b] if a >= 0 and b > a else log
    info["modesets during the scenarios"] = len(re.findall(r"drm: Modesetting", played))
    info["format changes without a modeset"] = len(re.findall(r"without a modeset, format", played))
    r["no_fallbacks"] = "without a modeset failed" not in log
    r["alive"] = (run / "alive").exists()
    return r, info


def main():
    root = Path(sys.argv[1])
    builds = [b for b in ("stock", "patched") if (root / b / "phases.txt").exists()]
    if not builds:
        sys.exit(f"no results in {root}")
    results = {b: analyze(root / b) for b in builds}
    width = max(len(d) for _, d, _ in CHECKS) + 2
    print(f"{'check':{width}}" + "".join(f"{b:>10}" for b in builds))
    failed, fixed = False, []
    for key, desc, stock_fails in CHECKS:
        row = f"{desc:{width}}"
        for b in builds:
            ok = results[b][0].get(key, False)
            if b == "stock" and stock_fails:
                cell = "PASS!" if ok else "fail*"
                if ok:
                    fixed.append(desc)
            else:
                cell = "pass" if ok else "FAIL"
                failed |= b == "patched" and not ok
            row += f"{cell:>10}"
        print(row)
    for name in results[builds[0]][1]:
        print(f"{name:{width}}" + "".join(f"{results[b][1][name]:>10}" for b in builds))
    print("\n* expected to fail on stock")
    for desc in fixed:
        print(f"! stock passes '{desc}', upstream may have fixed it")
    sys.exit(1 if failed else 0)


main()
