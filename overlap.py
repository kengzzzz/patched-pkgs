#!/usr/bin/env python3
"""overlap.py <package> <new-ref> [old-ref]: for each patch, whether it still applies on <new-ref> and whether
upstream changed code near its hunks since [old-ref], which defaults to the pinned commit. A hint for what to
retest, not proof that nothing broke: a patch can also depend on code it doesn't touch."""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

NEAR = 20


def git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env).stdout


def old_ranges(diff):
    out, cur = {}, None
    for line in diff.splitlines():
        if line.startswith("--- "):
            cur = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("@@") and cur:
            m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
            start, n = int(m[1]), int(m[2] if m[2] is not None else 1)
            out.setdefault(cur, []).append((start, start + max(n, 1) - 1))
    return out


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__.splitlines()[0])
    root = Path(__file__).resolve().parent
    pkg, new = sys.argv[1], sys.argv[2]
    env = dict(re.match(r"(\w+)=(.*)", line).groups() for line in open(root / pkg / "package.env") if "=" in line)
    url = env["UPSTREAM_URL"].strip("\"'")
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "patched-pkgs" / f"{pkg}.git"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", url, str(cache)], check=True)
    git(cache, "fetch", "-q", "--filter=blob:none", "--tags", "--force", "origin", "+refs/heads/*:refs/heads/*")
    old = git(cache, "rev-parse", (sys.argv[3] if len(sys.argv) == 4 else env["UPSTREAM_COMMIT"]) + "^{commit}").strip()
    new = git(cache, "rev-parse", new + "^{commit}").strip()

    patches = sorted((root / pkg / "patches").glob("*.patch"))
    with tempfile.TemporaryDirectory() as tmp:
        index_env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(cache, "read-tree", new, env=index_env)
        width = max(len(p.name) for p in patches) + 2
        print(f"{'patch':{width}}{'applies':9}upstream changes near its hunks")
        for patch in patches:
            applies = subprocess.run(["git", "-C", str(cache), "apply", "--cached", str(patch)], env=index_env,
                                     capture_output=True).returncode == 0
            mine = old_ranges(patch.read_text())
            theirs = old_ranges(git(cache, "diff", "-U0", old, new, "--", *mine)) if mine else {}
            near = []
            for f, rs in theirs.items():
                merged = []
                for a, b in sorted(r for r in rs if any(r[0] <= pb + NEAR and r[1] >= pa - NEAR for pa, pb in mine.get(f, []))):
                    if merged and a <= merged[-1][1] + NEAR:
                        merged[-1][1] = max(merged[-1][1], b)
                    else:
                        merged.append([a, b])
                if merged:
                    near.append(f + ":" + ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in merged))
            if near:
                status = ", ".join(near)
            elif theirs:
                status = "none, other changes in " + ", ".join(sorted(theirs))
            else:
                status = "none, files unchanged"
            print(f"{patch.name:{width}}{'yes' if applies else 'NO':9}{status}")


main()
