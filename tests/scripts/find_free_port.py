#!/usr/bin/env python3
"""
Find a free port in a range and print it.

Usage: find_free_port.py [start] [end]
"""
import socket
import sys


def find_free(start: int = 5500, end: int = 5520) -> int:
    for p in range(start, end):
        s = socket.socket()
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            continue
    raise SystemExit(1)


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 5520
    p = find_free(start, end)
    print(p)
    sys.exit(0)
