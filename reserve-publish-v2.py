#!/usr/bin/env python3
"""발행 예약(원자적 잠금 + 소유자 토큰). 같은 해시에 대한 동시 실행을 차단한다.
사용법: reserve-publish <SHA-256> <슬러그>
동작:
  1. 같은 해시의 published/unknown 기록이 있으면 거부 (종료코드 3) — 예약 시점 재확인.
  2. 같은 해시의 publishing 기록이 있으면 거부 (종료코드 1).
  3. O_EXCL로 예약 파일 원자적 생성. owner token(uuid4)을 파일에 기록하고 stdout으로 출력.
성공 시 종료코드 0. 해제는 반드시 이 토큰으로 release-publish <SHA-256> <토큰>.
"""
import os, re, sys, uuid
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))
KST = timezone(timedelta(hours=9))

def records():
    recs = []
    pubdir = os.path.join(BASE, "queue", "published")
    if not os.path.isdir(pubdir):
        return recs
    for fn in os.listdir(pubdir):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(pubdir, fn), encoding="utf-8").read()
        h = re.search(r"SHA-256:\s*([0-9a-f]{64})", text)
        st = re.search(r"상태:\s*(\w+)", text)
        recs.append({"sha256": h.group(1) if h else None,
                     "status": st.group(1) if st else "published"})
    return recs

def main():
    if len(sys.argv) < 3:
        print("usage: reserve-publish <SHA-256> <슬러그>", file=sys.stderr)
        sys.exit(2)
    digest, slug = sys.argv[1], sys.argv[2]
    recs = records()
    same = [r for r in recs if r["sha256"] == digest]
    if any(r["status"] in ("published", "unknown") for r in same):
        print("이미 발행됐거나 결과가 불명한 기록이 있음 — 예약 거부", file=sys.stderr)
        sys.exit(3)
    if any(r["status"] == "publishing" for r in same):
        print("이미 발행 진행 중 — 예약 거부", file=sys.stderr)
        sys.exit(1)
    pubdir = os.path.join(BASE, "queue", "published")
    os.makedirs(pubdir, exist_ok=True)
    token = uuid.uuid4().hex
    stamp = datetime.now(KST).strftime("%Y%m%d")
    path = os.path.join(pubdir, f"{stamp}-{slug}.publishing.md")
    content = (f"# 발행 진행 기록\n- SHA-256: {digest}\n- 상태: publishing\n"
               f"- 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST\n"
               f"- PID: {os.getpid()}\n- owner: {token}\n")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        print(f"예약 파일 충돌: {path}", file=sys.stderr)
        sys.exit(1)
    # 토큰을 stdout으로 전달 (크론이 보관했다가 해제에 사용)
    print(token)
    sys.exit(0)

if __name__ == "__main__":
    main()
