import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def load_crc(run):
    out = []
    for line in open(run / "crc.txt"):
        parts = line.replace("\x00", "").split()
        if len(parts) == 3:
            out.append((int(parts[0]), int(parts[1], 16), parts[2]))
    return out


def load_perf(path):
    vals = {}
    if not path.exists():
        return vals
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        f = line.strip().split(",")
        try:
            vals[f[2]] = float(f[0])
        except (ValueError, IndexError):
            pass
    return vals


def analyze(run):
    phases = {}
    loglines = {}
    for line in open(run / "phases.txt"):
        f = line.split()
        phases[f[1]] = (int(f[2]), int(f[3]))
        if len(f) >= 6:
            loglines[f[1]] = (int(f[4]), int(f[5]))
    crc = load_crc(run)

    def in_phase(name, t):
        a, b = phases[name]
        return a <= t < b

    s_ds = Counter(c for t, _, c in crc if in_phase("ds", t)).most_common(1)[0][0]
    s_osd = Counter(c for t, _, c in crc if in_phase("comp", t)).most_common(1)[0][0]

    res = {"run": run.name, "build": "-".join(run.name.split("-")[:-1])}
    for name in phases:
        frames = [c for t, _, c in crc if in_phase(name, t)]
        cnt = Counter(frames)
        res[f"{name}_vblanks"] = len(frames)
        res[f"{name}_other_frames"] = sum(v for k, v in cnt.items() if k not in (s_ds, s_osd))
        res[f"{name}_distinct"] = len(cnt)
        res[f"{name}_transient_frames"] = sum(v for v in cnt.values() if v < 10)

    # each OSD transition: time from the client's map/unmap commit until the first vblank showing the target
    # image, and the frames in between that show neither the old nor the new image
    events = []
    for line in open(run / "osd.txt"):
        p = line.split()
        if p[0] in ("MAP", "UNMAP"):
            events.append((p[0], int(p[2])))
    trans = []
    for kind, t in events:
        target = s_osd if kind == "MAP" else s_ds
        after = [(tt, c) for tt, _, c in crc if tt >= t]
        glitches = 0
        hit = None
        vblanks = None
        for i, (tt, c) in enumerate(after[:240]):
            if c == target:
                hit = tt
                vblanks = i + 1
                break
            if c not in (s_ds, s_osd):
                glitches += 1
        # frames that show neither image within 1 s after the transition, even after the target appeared
        window = [c for tt, c in after if tt < t + 1_000_000_000]
        trans.append({"kind": kind, "latency_ms": (hit - t) / 1e6 if hit else None, "vblanks": vblanks, "glitches_before": glitches,
                      "glitches_1s": sum(1 for c in window if c not in (s_ds, s_osd))})
    for kind in ("MAP", "UNMAP"):
        lat = [x["latency_ms"] for x in trans if x["kind"] == kind and x["latency_ms"] is not None]
        res[f"{kind.lower()}_latency_ms_med"] = st.median(lat) if lat else None
        res[f"{kind.lower()}_latency_ms_max"] = max(lat) if lat else None
        vb = [x["vblanks"] for x in trans if x["kind"] == kind and x["vblanks"] is not None]
        res[f"{kind.lower()}_vblanks_list"] = vb
        res[f"{kind.lower()}_missing"] = sum(1 for x in trans if x["kind"] == kind and x["latency_ms"] is None)
        res[f"{kind.lower()}_glitches_1s"] = sum(x["glitches_1s"] for x in trans if x["kind"] == kind)

    # client side: commit to presentation, per phase
    pres = []
    discarded = []
    for line in open(run / "game.txt"):
        p = line.split()
        if p[0] == "P":
            pres.append((int(p[2]), int(p[3]), int(p[6])))
        elif p[0] == "D":
            discarded.append(int(p[2]))
    for name in phases:
        lat = [(pr - c) / 1e6 for c, pr, _ in pres if in_phase(name, c)]
        res[f"{name}_present_ms_med"] = st.median(lat) if lat else None
        res[f"{name}_present_ms_p95"] = pct(lat, 95)
        res[f"{name}_presented"] = len(lat)
        res[f"{name}_discarded"] = sum(1 for c in discarded if in_phase(name, c))
        res[f"{name}_zero_copy_frac"] = (sum(1 for c, _, f in pres if in_phase(name, c) and f & 8) / len(lat)) if lat else None

    for name in phases:
        vb = res[f"{name}_vblanks"] or 1
        for scope in ("main", "proc"):
            perf = load_perf(run / f"perf-{name}-{scope}.csv")
            if perf:
                res[f"{name}_{scope}_cpu_us_per_vblank"] = perf.get("task-clock", 0) * 1000 / vb
                res[f"{name}_{scope}_kinstr_per_vblank"] = perf.get("instructions:u", 0) / 1000 / vb
                res[f"{name}_{scope}_kinstr_k_per_vblank"] = perf.get("instructions:k", 0) / 1000 / vb

    loglist = (run / "hyprland.log").read_text(errors="replace").splitlines()
    log = "\n".join(loglist)
    marks = [i for i, l in enumerate(loglist) if "ABMARK" in l]
    bounds = {}
    start = None
    for i in marks:
        if "ABMARK start" in loglist[i]:
            start = i
        elif "ABMARK end" in loglist[i] and start is not None:
            bounds[loglist[i].split("ABMARK end")[1].strip()] = (start, i)
            start = None
    for name, (la, lb) in bounds.items():
        part = "\n".join(loglist[la:lb])
        res[f"{name}_modesets"] = len(re.findall(r"drm: Modesetting", part))
        res[f"{name}_no_modeset_reconfigs"] = len(re.findall(r"without a modeset, format", part))
        res[f"{name}_swapchain_reallocs"] = len(re.findall(r"Swapchain: Reconfigured", part))
        res[f"{name}_ds_enter"] = len(re.findall(r"Entered a direct scanout", part))
    res["modesets"] = len(re.findall(r"drm: Modesetting", log))
    res["no_modeset_reconfigs"] = len(re.findall(r"without a modeset, format", log))
    res["no_modeset_fallbacks"] = len(re.findall(r"without a modeset failed", log))
    res["swapchain_reallocs"] = len(re.findall(r"Swapchain: Reconfigured", log))
    res["ds_enter"] = len(re.findall(r"Entered a direct scanout", log))
    res["ds_leave"] = len(re.findall(r"Left a direct scanout", log))
    res["commit_failures"] = len(re.findall(r"(?i)commit failed|failed to commit", log))
    return res


def main():
    root = Path(sys.argv[1])
    runs = sorted(p for p in root.iterdir() if p.is_dir() and (p / "phases.txt").exists())
    results = [analyze(r) for r in runs]
    (root / "summary.json").write_text(json.dumps(results, indent=1))
    builds = sorted({r["build"] for r in results})
    keys = [k for k in results[0] if k not in ("run", "build") and not k.endswith("_list")]
    print(f"{'metric':38}" + "".join(f"{b:>22}" for b in builds))
    for k in keys:
        row = f"{k:38}"
        for b in builds:
            vals = [r[k] for r in results if r["build"] == b and r.get(k) is not None]
            if not vals:
                row += f"{'-':>22}"
                continue
            med = st.median(vals)
            spread = f"{min(vals):.3g}..{max(vals):.3g}" if len(vals) > 1 else ""
            row += f"{med:>10.4g} {spread:>11}"
        print(row)
    pooled(results)


def pooled(results):
    for kind in ("map", "unmap"):
        for b in sorted({r["build"] for r in results}):
            vals = [v for r in results if r["build"] == b for v in r.get(f"{kind}_vblanks_list", [])]
            if vals:
                print(f"{kind} vblanks {b:>8}: n={len(vals)} median={st.median(vals)} mean={st.mean(vals):.2f} dist={dict(sorted(Counter(vals).items()))}")


main()
