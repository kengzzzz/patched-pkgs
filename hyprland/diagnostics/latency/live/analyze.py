#!/usr/bin/env python3
"""Summarize a run of run.sh: commit to flip latency per phase and the compositor state during it."""

import json
import sys
from collections import Counter
from pathlib import Path

VSYNC, ZERO_COPY = 0x1, 0x8
SKIP_NS = 2_000_000_000


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def stats(xs):
    if not xs:
        return "n=0"
    return (f"n={len(xs):5d} avg={sum(xs) / len(xs):6.3f} med={pct(xs, 50):6.3f} p95={pct(xs, 95):6.3f} "
            f"p99={pct(xs, 99):6.3f} max={max(xs):7.3f}")


def load(path):
    pres, disc, end = [], [], ""
    for line in open(path):
        f = line.split()
        if f[0] == "P":
            pres.append({"commit": int(f[2]), "flip": int(f[3]), "flags": int(f[6]), "recv": int(f[7])})
        elif f[0] == "D":
            disc.append(int(f[2]))
        elif f[0] == "END":
            end = line.strip()
    if not pres:
        return [], [], end
    start = min(x["commit"] for x in pres) + SKIP_NS
    return [x for x in pres if x["commit"] >= start], [t for t in disc if t >= start], end


def report(out, name):
    pres, disc, end = load(out / f"{name}.txt")
    print(f"== {name}  ({end})")
    if not pres:
        print("   no presented frames")
        return
    span = (max(x["commit"] for x in pres) - min(x["commit"] for x in pres)) / 1e9 or 1
    torn = [x for x in pres if not x["flags"] & VSYNC]
    print(f"   presented {len(pres)} ({len(pres) / span:.0f}/s), discarded {len(disc)}, torn {len(torn) / len(pres):.1%}, "
          f"zero copy {sum(1 for x in pres if x['flags'] & ZERO_COPY) / len(pres):.1%}")
    print(f"   commit -> flip ms             {stats([(x['flip'] - x['commit']) / 1e6 for x in pres])}")
    print(f"   commit -> feedback ms         {stats([(x['recv'] - x['commit']) / 1e6 for x in pres])}")
    if torn and len(torn) != len(pres):
        print(f"   torn frames, -> feedback ms   {stats([(x['recv'] - x['commit']) / 1e6 for x in torn])}")

    osd = out / "osd.txt"
    if name == "tear-osd" and osd.exists():
        events = [(f[0], int(f[2])) for f in (line.split() for line in open(osd)) if f[0] in ("MAP", "UNMAP")]
        for kind, t in events:
            if kind != "UNMAP":
                continue
            after = sorted((x for x in pres if x["commit"] >= t), key=lambda x: x["commit"])
            first = [x for x in after if not x["flags"] & VSYNC][:3]
            if first:
                print(f"   OSD gone: tearing again after {(first[0]['commit'] - t) / 1e6:.0f} ms, "
                      f"first torn frames {[round((x['recv'] - x['commit']) / 1e6, 3) for x in first]} ms")


def main():
    out = Path(sys.argv[1])
    phases = [(f[0], int(f[1])) for f in (line.split() for line in open(out / "phases.txt"))]
    for name, _ in phases:
        if (out / f"{name}.txt").exists():
            report(out, name)

    state_file = out / "state.txt"
    state = [json.loads(line) for line in open(state_file)] if state_file.exists() else []
    for (name, a), (_, b) in zip(phases, phases[1:]):
        s = [x for x in state if a <= x["t"] < b]
        if not s:
            continue
        print(f"-- {name}: tearing {sum(1 for x in s if x['activelyTearing']) / len(s):.0%}, "
              f"scanout {sum(1 for x in s if x['directScanoutTo'] not in ('0', None)) / len(s):.0%}, "
              f"formats {dict(Counter(x['currentFormat'] for x in s))}, "
              f"solitary blocked by {dict(Counter(r for x in s for r in (x.get('solitaryBlockedBy') or [])))}")


main()
