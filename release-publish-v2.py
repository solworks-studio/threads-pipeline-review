#!/usr/bin/env python3
"""발행 예약 해제. 소유자 토큰이 일치할 때만 해제한다.
사용법: release-publish <SHA-256> <owner-token>
토큰이 없거나 불일치하면 아무 것도 삭제하지 않고 종료코드 1.
예약을 잡지 못한 실행은 이 명령을 호출하지 마라.
"""
import os, re, sys

BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))

def main():
    if len(sys.argv) < 3:
        print("usage: release-publish <SHA-256> <owner-token>", file=sys.stderr)
        sys.exit(2)
    digest, token = sys.argv[1], sys.argv[2]
    pubdir = os.path.join(BASE, "queue", "published")
    removed = 0
    if os.path.isdir(pubdir):
        for fn in os.listdir(pubdir):
            if not fn.endswith(".publishing.md"):
                continue
            p = os.path.join(pubdir, fn)
            text = open(p, encoding="utf-8").read()
            if digest not in text:
                continue
            m = re.search(r"owner:\s*([0-9a-f]{32})", text)
            if m and m.group(1) == token:
                os.remove(p)
                removed += 1
            else:
                print(f"소유자 불일치 — 해제 거부: {fn}", file=sys.stderr)
    if removed:
        print(f"해제 {removed}건")
        sys.exit(0)
    print("해제할 예약 없음 (토큰 불일치 또는 예약 없음)", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()
