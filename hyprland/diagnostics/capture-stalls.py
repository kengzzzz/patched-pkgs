#!/usr/bin/env python3
"""Sample Hyprland and game thread states to classify present stalls."""

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

if len(sys.argv) not in (2, 3):
    sys.exit(f"Usage: {sys.argv[0]} <process name> [game log file]")
GAME_COMM = sys.argv[1]
GAME_LOG = Path(sys.argv[2]) if len(sys.argv) == 3 else None
PERIOD = 0.05
RING_SECONDS = 3.0
STALL_WINDOW = 0.25
STALL_RATIO = 0.25
MIN_BASELINE_CORES = 0.5

out_dir = Path(__file__).resolve().parent / ("stall-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
out_dir.mkdir()
timeline = (out_dir / "timeline.log").open("w", buffering=1)
lock = threading.Lock()
stop = threading.Event()


def stamp():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def emit(kind, text):
    with lock:
        timeline.write(f"{stamp()} {time.monotonic():.3f} {kind} {text}\n")


def find_pid(comm):
    for entry in os.scandir("/proc"):
        if entry.name.isdigit():
            try:
                with open(f"/proc/{entry.name}/comm") as f:
                    if f.read().strip() == comm:
                        return int(entry.name)
            except OSError:
                pass
    return None


def read_threads(pid):
    threads = {}
    try:
        tids = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return None
    for tid in tids:
        base = f"/proc/{pid}/task/{tid}"
        try:
            with open(base + "/stat") as f:
                stat = f.read()
            with open(base + "/schedstat") as f:
                runtime = int(f.read().split()[0])
            with open(base + "/wchan") as f:
                wchan = f.read().strip() or "0"
        except (OSError, ValueError):
            continue
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        state = stat[stat.rindex(")") + 2]
        threads[int(tid)] = (comm, state, wchan, runtime)
    return threads


def describe(prev, cur, dt, limit=None, only=None):
    rows = []
    for tid, (comm, state, wchan, runtime) in cur.items():
        if only is not None and tid not in only:
            continue
        delta = runtime - prev[tid][3] if prev and tid in prev else 0
        rows.append((delta, tid, comm, state, wchan))
    rows.sort(reverse=True)
    if limit:
        rows = rows[:limit]
    return " | ".join(
        f"{tid}:{comm}:{state}:{wchan}:{delta / dt / 1e7:.0f}%" for delta, tid, comm, state, wchan in rows
    )


def hottest(ring, count):
    snaps = [s for s in list(ring)[:-6] if s["game"]]
    if len(snaps) < 2:
        return None
    first, last = snaps[0]["game"], snaps[-1]["game"]
    deltas = sorted(((v[3] - first[tid][3], tid) for tid, v in last.items() if tid in first), reverse=True)
    return {tid for _, tid in deltas[:count]}


def sampler():
    hypr = find_pid("Hyprland")
    game = None
    ring = deque(maxlen=int(RING_SECONDS / PERIOD))
    game_rates = deque(maxlen=int(10 / PERIOD))
    prev_hypr = prev_game = None
    prev_time = time.monotonic()
    main_wchan = None
    main_since = prev_time
    in_stall = False
    stall_start = 0.0
    last_summary = prev_time
    dumps = 0
    hot = None
    emit("START", f"hyprland={hypr} game_comm={GAME_COMM}")
    while not stop.is_set():
        tick = time.monotonic()
        if game is None or not os.path.exists(f"/proc/{game}"):
            new_game = find_pid(GAME_COMM)
            if new_game != game:
                emit("GAME", f"pid={new_game}")
                if game is not None and GAME_LOG and GAME_LOG.exists():
                    shutil.copy(GAME_LOG, out_dir / f"{GAME_LOG.stem}-{game}{GAME_LOG.suffix}")
                game, prev_game = new_game, None
                game_rates.clear()
                in_stall = False
        hypr_threads = read_threads(hypr) or {}
        game_threads = read_threads(game) if game else None
        now = time.monotonic()
        dt = now - prev_time

        main = hypr_threads.get(hypr)
        if main:
            wchan = main[2] if main[1] != "R" else "running"
            if wchan != main_wchan:
                held = now - main_since
                if main_wchan not in (None, "running", "do_epoll_wait", "__x64_sys_epoll_wait", "ep_poll") and held >= 0.1:
                    emit("HYPR_MAIN", f"left {main_wchan} after {held * 1000:.0f} ms, now {wchan}")
                main_wchan, main_since = wchan, now
            elif main_wchan not in ("running", "do_epoll_wait", "__x64_sys_epoll_wait", "ep_poll") and now - main_since >= 0.1 and int((now - main_since) / 0.5) != int((now - main_since - dt) / 0.5):
                emit("HYPR_MAIN", f"in {main_wchan} state {main[1]} for {(now - main_since) * 1000:.0f} ms")

        snapshot = {"t": stamp(), "dt": dt, "hypr": hypr_threads, "game": game_threads,
                    "prev_hypr": prev_hypr, "prev_game": prev_game}
        ring.append(snapshot)

        if game_threads is not None and prev_game is not None and dt > 0:
            game_runtime = sum(v[3] for v in game_threads.values())
            prev_runtime = sum(v[3] for tid, v in prev_game.items() if tid in game_threads)
            game_rates.append((now, (game_runtime - prev_runtime) / dt / 1e9))
            window = [r for t, r in game_rates if now - t <= STALL_WINDOW]
            history = sorted(r for t, r in game_rates if now - t > STALL_WINDOW)
            if len(history) > 40 and window:
                baseline = history[len(history) // 2]
                rate = sum(window) / len(window)
                stalled = baseline >= MIN_BASELINE_CORES and rate < baseline * STALL_RATIO
                if stalled and not in_stall:
                    in_stall, stall_start = True, now
                    emit("STALL_BEGIN", f"game {rate:.2f} cores vs baseline {baseline:.2f}")
                    hot = hottest(ring, 12)
                    if dumps < 60:
                        dumps += 1
                        dump_ring(ring, f"stall-{dumps:02d}-begin")
                elif in_stall and rate >= baseline * 0.5:
                    in_stall = False
                    emit("STALL_END", f"after {(now - stall_start) * 1000:.0f} ms, game {rate:.2f} cores")
                    if dumps <= 60:
                        dump_ring(ring, f"stall-{dumps:02d}-end")
                if in_stall and dumps <= 60 and int((now - stall_start) / 0.5) != int((now - stall_start - dt) / 0.5):
                    emit("STALL_GAME", describe(prev_game, game_threads, dt, 12, hot))
                    emit("STALL_HYPR", describe(prev_hypr, hypr_threads, dt))

        if now - last_summary >= 1.0:
            parts = []
            if prev_hypr:
                parts.append("hypr " + describe(prev_hypr, hypr_threads, dt, 3))
            if game_threads and prev_game:
                parts.append("game " + describe(prev_game, game_threads, dt, 4))
            emit("SUMMARY", " || ".join(parts))
            last_summary = now

        prev_hypr, prev_game, prev_time = hypr_threads, game_threads, now
        time.sleep(max(0, PERIOD - (time.monotonic() - tick)))


def dump_ring(ring, name):
    with (out_dir / f"{name}.log").open("w") as f:
        for snap in list(ring):
            f.write(f"=== {snap['t']} dt={snap['dt'] * 1000:.0f}ms\n")
            f.write("hypr " + describe(snap["prev_hypr"], snap["hypr"], snap["dt"]) + "\n")
            if snap["game"]:
                f.write("game " + describe(snap["prev_game"], snap["game"], snap["dt"], 25) + "\n")


def probe():
    last = None
    while not stop.is_set():
        started = time.monotonic()
        try:
            result = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, timeout=60)
            latency = (time.monotonic() - started) * 1000
            state = [
                {k: m.get(k) for k in ("name", "solitary", "directScanoutTo", "directScanoutBlockedBy",
                                        "activelyTearing", "tearingBlockedBy", "currentFormat")}
                for m in json.loads(result.stdout)
            ]
        except (subprocess.SubprocessError, ValueError) as error:
            latency = (time.monotonic() - started) * 1000
            state = f"error {error}"
        if latency > 100:
            emit("IPC_SLOW", f"hyprctl monitors took {latency:.0f} ms")
        if state != last:
            emit("MONITORS", json.dumps(state, separators=(",", ":")))
            last = state
        time.sleep(max(0, 0.2 - (time.monotonic() - started)))


threads = [threading.Thread(target=sampler, daemon=True), threading.Thread(target=probe, daemon=True)]
for t in threads:
    t.start()
print(f"Recording to {out_dir}. Press Ctrl-C to stop.", flush=True)
try:
    while all(t.is_alive() for t in threads):
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
stop.set()
for t in threads:
    t.join(timeout=2)
emit("STOP", "")
for src in [GAME_LOG, *Path(os.environ["XDG_RUNTIME_DIR"], "hypr").glob("*/hyprland.log")]:
    if src and src.exists():
        shutil.copy(src, out_dir / src.name)
print(f"Saved {out_dir}", flush=True)
