#!/usr/bin/env python3
"""발행 예약 해제. reserve-publish가 만든 .publishing.md를 삭제한다.
사용법: release-publish <SHA-256>
"""
import os, sys

BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))

def main():
    if len(sys.argv) < 2:
        print("usage: release-publish <SHA-256>", file=sys.stderr)
        sys.exit(2)
    digest = sys.argv[1]
    pubdir = os.path.join(BASE, "queue", "published")
    removed = 0
    if os.path.isdir(pubdir):
        for fn in os.listdir(pubdir):
            if fn.endswith(".publishing.md"):
                p = os.path.join(pubdir, fn)
                if digest in open(p, encoding="utf-8").read():
                    os.remove(p)
                    removed += 1
    print(f"해제 {removed}건")
    sys.exit(0)

if __name__ == "__main__":
    main()
