#!/usr/bin/env python3
"""Find first responsive port by attempting TCP connect.
Usage: find_responsive_port.py [start] [end]
"""
import socket
import sys


def find_responsive(start: int = 5500, end: int = 5570) -> int:
    for p in range(start, end):
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("127.0.0.1", p))
            s.close()
            return p
        except Exception:
            continue
    raise SystemExit(1)


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 5570
    p = find_responsive(start, end)
    print(p)
    sys.exit(0)
