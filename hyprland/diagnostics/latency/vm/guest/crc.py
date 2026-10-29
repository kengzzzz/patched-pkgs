import os
import sys
import time

crc_dir, out_path = sys.argv[1], sys.argv[2]
with open(os.path.join(crc_dir, "control"), "w") as f:
    f.write("auto")
fd = os.open(os.path.join(crc_dir, "data"), os.O_RDONLY)
with open(out_path, "w", buffering=1) as out:
    pending = b""
    while True:
        chunk = os.read(fd, 4096)
        t = time.monotonic_ns()
        if not chunk:
            break
        pending += chunk
        *lines, pending = pending.split(b"\n")
        for line in lines:
            out.write(f"{t} {line.decode().replace("\x00", "").strip()}\n")
