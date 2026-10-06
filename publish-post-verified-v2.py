#!/usr/bin/env python3
"""검증 발행 래퍼 v2. 발행 직전 해시 재확인 + 상태 전이(기록·예약 해제)를 래퍼가 책임진다.

사용법: publish-post-verified <SHA-256> <본문파일> <account-id>
        --slug <슬러그> --token <owner-token> [--log <로그파일>] [--timeout <초>] [--dry-run]

동작:
- 해시 불일치 → publish_aborted 기록, 토큰으로 예약 해제, 종료코드 2. 게시 없음.
- CLI 성공(rc 0) → published 기록 작성, 토큰으로 예약 해제, 종료코드 0. stdout 그대로 출력.
- CLI 실패(rc!=0) → unknown 기록 작성, 토큰으로 예약 해제, 종료코드=rc.
- CLI 타임아웃 → 부분 stdout/stderr 보존, unknown 기록, 토큰으로 예약 해제, 종료코드 1.
- CLI 실행 자체 실패(OSError) → not_started로 기록 (요청 미시작이라 unknown 아님), 해제, 종료코드 1.
- --dry-run: CLI를 호출하지 않고 검증·로그만 수행.
환경변수: THREADS_BASE(기본 ~/workspace/threads), THREADS_CLI(기본 threads-cli).
"""
import hashlib, json, os, subprocess, sys, time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))
CLI = os.environ.get("THREADS_CLI", "threads-cli")
BIN = os.path.dirname(os.path.abspath(__file__))

def log_line(path, msg):
    if not path:
        return
    ts = datetime.now(KST).strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def as_text(x):
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="replace")
    return x

def write_record(slug, status, digest, extra=""):
    pubdir = os.path.join(BASE, "queue", "published")
    os.makedirs(pubdir, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    path = os.path.join(pubdir, f"{stamp}-{slug}.{status}.md" if status != "published"
                        else f"{stamp}-{slug}.md")
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 발행 기록\n- SHA-256: {digest}\n- 상태: {status}\n- 시각: {now} KST\n{extra}")
    return path

def release(digest, token):
    if not token:
        return None
    p = subprocess.run([sys.executable, os.path.join(BIN, "release-publish"), digest, token],
                       capture_output=True, text=True)
    return p.returncode

def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print("usage: publish-post-verified <SHA-256> <본문파일> <account-id> "
              "--slug <s> --token <t> [--log <f>] [--timeout <s>] [--dry-run]", file=sys.stderr)
        sys.exit(2)
    digest, body_path, account_id = args[0], args[1], args[2]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    slug = opt("--slug", "post")
    token = opt("--token")
    log_path = opt("--log")
    timeout = int(opt("--timeout", "300"))
    dry = "--dry-run" in args

    body = open(body_path, "rb").read()
    actual = hashlib.sha256(body).hexdigest()
    if actual != digest:
        log_line(log_path, f"publish_aborted reason=hash_mismatch expected={digest[:12]} actual={actual[:12]}")
        release(digest, token)
        print("해시 불일치 — 발행 중단", file=sys.stderr)
        sys.exit(2)

    text = body.decode("utf-8")
    log_line(log_path, f"publish_begin sha={digest[:12]} account={account_id} bytes={len(body)}")
    if dry:
        log_line(log_path, "publish_result dry_run ok")
        print("dry-run ok")
        sys.exit(0)

    t0 = time.monotonic()
    try:
        p = subprocess.run([CLI, "publish-post", "--account-id", account_id,
                            "--text", text], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        elapsed = round(time.monotonic() - t0, 1)
        out, err = as_text(e.stdout).strip(), as_text(e.stderr).strip()
        rec = write_record(slug, "unknown", digest,
                           f"- 사유: publish-post {timeout}초 타임아웃 (서버 반영 여부 불확실). 재발행 금지.\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result outcome=unknown reason=timeout elapsed={elapsed} "
                           f"record={os.path.basename(rec)} release_rc={rc_rel} "
                           f"partial_stdout={out[:200]!r} partial_stderr={err[:200]!r}")
        print(f"타임아웃 — unknown 기록 완료 ({rec})", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        log_line(log_path, f"publish_result outcome=not_started reason=oserror error={e}")
        release(digest, token)
        print(f"CLI 실행 실패: {e}", file=sys.stderr)
        sys.exit(1)

    if p.returncode == 0:
        post_id = ""
        try:
            post_id = json.loads(p.stdout).get("post_id", "")
        except Exception:
            pass
        rec = write_record(slug, "published", digest,
                           f"- post_id: {post_id}\n- 방식: publish-post-verified\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result ok post_id={post_id} record={os.path.basename(rec)} release_rc={rc_rel}")
        sys.stdout.write(p.stdout)
        sys.exit(0)
    else:
        rec = write_record(slug, "unknown", digest,
                           f"- 사유: publish-post 종료코드 {p.returncode} (서버 반영 여부 불확실). 재발행 금지.\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result outcome=unknown reason=cli_error rc={p.returncode} "
                           f"record={os.path.basename(rec)} release_rc={rc_rel} stderr={p.stderr.strip()[:200]!r}")
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        sys.exit(p.returncode)

if __name__ == "__main__":
    main()
