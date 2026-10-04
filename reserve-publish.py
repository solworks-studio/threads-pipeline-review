#!/usr/bin/env python3
"""발행 예약(원자적 잠금). 같은 해시에 대한 동시 실행을 차단한다.
사용법: reserve-publish <SHA-256> <슬러그>
동작: queue/published/<날짜>-<슬러그>.publishing.md 를 O_EXCL로 생성.
     이미 있으면(같은 해시의 publishing 기록) 종료코드 1로 실패.
성공 시 종료코드 0. release-publish로 해제한다.
"""
import os, sys
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))
KST = timezone(timedelta(hours=9))

def main():
    if len(sys.argv) < 3:
        print("usage: reserve-publish <SHA-256> <슬러그>", file=sys.stderr)
        sys.exit(2)
    digest, slug = sys.argv[1], sys.argv[2]
    pubdir = os.path.join(BASE, "queue", "published")
    os.makedirs(pubdir, exist_ok=True)
    # 같은 해시의 publishing 기록이 이미 있으면 실패
    for fn in os.listdir(pubdir):
        if fn.endswith(".publishing.md"):
            t = open(os.path.join(pubdir, fn), encoding="utf-8").read()
            if digest in t and "상태: publishing" in t:
                print(f"이미 발행 진행 중: {fn}", file=sys.stderr)
                sys.exit(1)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    path = os.path.join(pubdir, f"{stamp}-{slug}.publishing.md")
    content = (f"# 발행 진행 기록\n- SHA-256: {digest}\n- 상태: publishing\n"
               f"- 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST\n"
               f"- PID: {os.getpid()}\n")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        print(f"예약 파일 충돌: {path}", file=sys.stderr)
        sys.exit(1)
    print(path)
    sys.exit(0)

if __name__ == "__main__":
    main()
