#!/usr/bin/env python3
"""검증 발행 래퍼. 발행 직전에 본문 바이트의 해시를 재확인하고,
publish_begin / publish_result를 영속 로그에 기록한다.
사용법: publish-post-verified <SHA-256> <본문파일> <account-id> [--log <로그파일>] [--dry-run]
- 해시 불일치 → 발행하지 않고 종료코드 2.
- --dry-run: threads-cli를 호출하지 않고 검증·로그만 수행 (테스트용).
- 성공 시 threads-cli publish-post의 stdout을 그대로 출력한다.
"""
import hashlib, os, subprocess, sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

def log_line(path, msg):
    if not path:
        return
    ts = datetime.now(KST).strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def main():
    if len(sys.argv) < 4:
        print("usage: publish-post-verified <SHA-256> <본문파일> <account-id> [--log <f>] [--dry-run]",
              file=sys.stderr)
        sys.exit(2)
    digest, body_path, account_id = sys.argv[1], sys.argv[2], sys.argv[3]
    log_path = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None
    dry = "--dry-run" in sys.argv

    body = open(body_path, "rb").read()
    actual = hashlib.sha256(body).hexdigest()
    if actual != digest:
        log_line(log_path, f"publish_aborted reason=hash_mismatch expected={digest[:12]} actual={actual[:12]}")
        print("해시 불일치 — 발행 중단", file=sys.stderr)
        sys.exit(2)

    text = body.decode("utf-8")
    log_line(log_path, f"publish_begin sha={digest[:12]} account={account_id} bytes={len(body)}")
    if dry:
        log_line(log_path, "publish_result dry_run ok")
        print("dry-run ok")
        sys.exit(0)
    p = subprocess.run(["threads-cli", "publish-post", "--account-id", account_id,
                        "--text", text], capture_output=True, text=True, timeout=300)
    if p.returncode == 0:
        log_line(log_path, f"publish_result ok stdout={p.stdout.strip()[:200]}")
    else:
        log_line(log_path, f"publish_result fail rc={p.returncode} stderr={p.stderr.strip()[:200]}")
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    sys.exit(p.returncode)

if __name__ == "__main__":
    main()
