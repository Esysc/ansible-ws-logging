#!/usr/bin/env python3
"""Populate a directory with realistic sample log files.
Usage: populate_sample_logs.py <target_dir>
"""
import gzip
import os
import sys
import time


def write_logs(target_dir: str) -> None:
    os.makedirs(target_dir, exist_ok=True)
    now = int(time.time())

    def write(name: str, lines: int) -> None:
        p = os.path.join(target_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            for i in range(lines):
                fmt = "%Y-%m-%d %H:%M:%S"
                ts = time.strftime(fmt, time.localtime(now + i))
                f.write(f"{ts} - {name} - log line {i}\n")

    # Main logs
    write("ansible.log", 200)
    write("access.log", 500)
    write("errors.log", 100)

    # gzipped older log
    gzpath = os.path.join(target_dir, "old.log.gz")
    with gzip.open(gzpath, "wb") as f:
        fmt = "%Y-%m-%d %H:%M:%S"
        for i in range(300):
            ts = time.strftime(fmt, time.localtime(now + i))
            line = f"{ts} - old.log - entry {i}\n"
            f.write(line.encode())

    # rotated / archived logs
    for i in range(6):
        write(f"app.{i}.log", 50)


if __name__ == "__main__":
    default = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "sample_logs")
    )
    target = sys.argv[1] if len(sys.argv) > 1 else default
    write_logs(os.path.abspath(target))
    print("created")
