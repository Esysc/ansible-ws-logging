#!/usr/bin/env python3
"""Background log writer used for local testing.
Writes appended lines to all *.log files in a directory every INTERVAL seconds.
"""
import glob
import os
import signal
import sys
import time
from typing import Any, Dict

LOG_DIR: str = os.environ.get("LOG_DIR") or os.getcwd()
INTERVAL: int = int(os.environ.get("LOG_WRITER_INTERVAL", "2"))

counters: Dict[str, int] = {}


def _handle(signum: int, frame: Any) -> None:
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle)
signal.signal(signal.SIGINT, _handle)


while True:
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        files = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
        if not files:
            files = [os.path.join(LOG_DIR, "ansible.log")]

        for p in files:
            c = counters.setdefault(p, 0)
            line = f"{ts} - {os.path.basename(p)} - appended line {c}\n"
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
            counters[p] = c + 1

        time.sleep(INTERVAL)
    except Exception as e:
        with open(
            os.path.join(os.path.dirname(__file__), "log_writer.err"), "a"
        ) as errf:
            errf.write(str(e) + "\n")
        time.sleep(1)
