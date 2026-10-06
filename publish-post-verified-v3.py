#!/usr/bin/env python3
"""검증 발행 래퍼 v3. 발행 전 소유권 검사 + 해시 재확인 + 상태 전이를 래퍼가 책임진다.

사용법: publish-post-verified <SHA-256> <본문파일> <account-id>
        --slug <슬러그> --token <owner-token> [--log <로그파일>] [--timeout <초>] [--dry-run]
        (--dry-run에서는 --slug/--token 생략 가능, CLI를 호출하지 않는다)

종료코드:
  0 = 발행 성공 + published 기록 + 예약 해제 완료
  1 = 발행 실패/불명 (unknown 기록 + 해제 시도) 또는 요청 미시작 (not_started)
  2 = 사전 차단 (인자 누락, 해시 불일치, 소유권 불일치) — CLI 호출 0회
  3 = 발행은 성공했으나 예약 해제 실패 (published 기록은 있음, 장애로 보고할 것)
  그 외 = CLI 종료코드 전파 (unknown 기록됨)

상태 전이:
- 해시 불일치/소유권 불일치 → publish_aborted 기록만. 타 소유자의 예약은 건드리지 않는다.
- 본문 파일 없음 → not_started (요청 미시작). 토큰으로 자기 예약만 해제.
- CLI 성공 + post_id 확인 → published. post_id를 못 읽으면 unknown (성공 단정 금지).
- CLI 실패/타임아웃/디코딩 오류 → unknown. 타임아웃 부분 출력은 진단 파일에 원본 그대로 보존.
- CLI 실행 자체 실패(OSError) → not_started.
환경변수: THREADS_BASE(기본 ~/workspace/threads), THREADS_CLI(기본 threads-cli).
"""
import hashlib, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE = os.environ.get("THREADS_BASE", os.path.expanduser("~/workspace/threads"))
CLI = os.environ.get("THREADS_CLI", "threads-cli")
BIN = os.path.dirname(os.path.abspath(__file__))

def now():
    return datetime.now(KST)

def log_line(path, msg):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{now().strftime('%H:%M:%S')} {msg}\n")

def as_text(x):
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="replace")
    return x

def write_diag(slug, content):
    d = os.path.join(BASE, "logs")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"diag-{slug}-{now().strftime('%Y%m%d-%H%M%S')}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

def write_record(slug, status, digest, extra=""):
    pubdir = os.path.join(BASE, "queue", "published")
    os.makedirs(pubdir, exist_ok=True)
    stamp = now().strftime("%Y%m%d")
    name = f"{stamp}-{slug}.md" if status == "published" else f"{stamp}-{slug}.{status}.md"
    path = os.path.join(pubdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 발행 기록\n- SHA-256: {digest}\n- 상태: {status}\n"
                f"- 시각: {now().strftime('%Y-%m-%d %H:%M')} KST\n{extra}")
    return path

def release(digest, token):
    if not token:
        return None
    p = subprocess.run([sys.executable, os.path.join(BIN, "release-publish"), digest, token],
                       capture_output=True, text=True)
    return p.returncode

def check_ownership(digest, token):
    """활성 예약 중 같은 해시의 파일이 있고 owner가 토큰과 일치하면 True."""
    pubdir = os.path.join(BASE, "queue", "published")
    if not os.path.isdir(pubdir):
        return False
    for fn in os.listdir(pubdir):
        if not fn.endswith(".publishing.md"):
            continue
        text = open(os.path.join(pubdir, fn), encoding="utf-8").read()
        if digest not in text:
            continue
        m = re.search(r"owner:\s*([0-9a-f]{32})", text)
        return bool(m and m.group(1) == token)
    return False

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    if len(args) < 3:
        print("usage: publish-post-verified <SHA-256> <본문파일> <account-id> "
              "--slug <s> --token <t> [--log <f>] [--timeout <s>] [--dry-run]", file=sys.stderr)
        sys.exit(2)
    digest, body_path, account_id = args[0], args[1], args[2]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    slug = opt("--slug")
    token = opt("--token")
    log_path = opt("--log")
    timeout = int(opt("--timeout", "300"))

    if not dry and (not slug or not token):
        log_line(log_path, "publish_aborted reason=missing_args (slug/token 필수)")
        print("--slug와 --token은 필수다", file=sys.stderr)
        sys.exit(2)
    slug = slug or "post"

    # 본문 읽기 (실패 = 요청 미시작)
    try:
        body = open(body_path, "rb").read()
    except OSError as e:
        log_line(log_path, f"publish_result outcome=not_started reason=body_missing error={e}")
        rc_rel = release(digest, token) if token else None
        log_line(log_path, f"cleanup release_rc={rc_rel}")
        print(f"본문 파일 없음: {e}", file=sys.stderr)
        sys.exit(1)

    # 해시 재확인 (불일치 시 토큰으로 자기 예약만 해제 — 해제는 토큰 일치 시에만 실행됨)
    actual = hashlib.sha256(body).hexdigest()
    if actual != digest:
        rc_rel = release(digest, token) if token else None
        log_line(log_path, f"publish_aborted reason=hash_mismatch expected={digest[:12]} "
                           f"actual={actual[:12]} release_rc={rc_rel}")
        print("해시 불일치 — 발행 중단", file=sys.stderr)
        sys.exit(2)

    # 소유권 사전 검사 (dry-run 제외)
    if not dry and not check_ownership(digest, token):
        log_line(log_path, "publish_aborted reason=ownership (활성 예약 없음 또는 토큰 불일치)")
        print("예약 소유권 불일치 — 발행 중단", file=sys.stderr)
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
        diag = write_diag(slug, f"reason=timeout elapsed={elapsed}\n"
                                f"--- stdout ---\n{as_text(e.stdout)}\n--- stderr ---\n{as_text(e.stderr)}\n")
        rec = write_record(slug, "unknown", digest,
                           f"- 사유: publish-post {timeout}초 타임아웃 (서버 반영 여부 불확실). 재발행 금지.\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result outcome=unknown reason=timeout elapsed={elapsed} "
                           f"record={os.path.basename(rec)} release_rc={rc_rel} diag={os.path.basename(diag)}")
        print(f"타임아웃 — unknown 기록 완료 ({rec})", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        diag = write_diag(slug, f"reason=decode_error\n{e!r}\n")
        rec = write_record(slug, "unknown", digest,
                           "- 사유: CLI 출력 디코딩 오류 (요청 시작됨, 반영 여부 불확실). 재발행 금지.\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result outcome=unknown reason=decode_error "
                           f"record={os.path.basename(rec)} release_rc={rc_rel} diag={os.path.basename(diag)}")
        sys.exit(1)
    except OSError as e:
        log_line(log_path, f"publish_result outcome=not_started reason=oserror error={e}")
        rc_rel = release(digest, token)
        log_line(log_path, f"cleanup release_rc={rc_rel}")
        print(f"CLI 실행 실패: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # 그 외 예외도 unknown으로 남긴다 (요청 시작 후로 간주)
        diag = write_diag(slug, f"reason=unexpected {type(e).__name__}\n{e!r}\n")
        rec = write_record(slug, "unknown", digest,
                           f"- 사유: 래퍼 예외 {type(e).__name__} (반영 여부 불확실). 재발행 금지.\n")
        rc_rel = release(digest, token)
        log_line(log_path, f"publish_result outcome=unknown reason=unexpected "
                           f"record={os.path.basename(rec)} release_rc={rc_rel} diag={os.path.basename(diag)}")
        sys.exit(1)

    if p.returncode == 0:
        post_id = ""
        try:
            post_id = str(json.loads(p.stdout).get("post_id", "") or "")
        except Exception:
            post_id = ""
        if not post_id:
            # 종료코드 0이어도 식별자가 없으면 성공으로 단정하지 않는다
            diag = write_diag(slug, f"reason=no_post_id rc=0\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}\n")
            rec = write_record(slug, "unknown", digest,
                               "- 사유: CLI 종료코드 0이나 post_id를 확인하지 못함 (반영 여부 불확실). 재발행 금지.\n")
            rc_rel = release(digest, token)
            log_line(log_path, f"publish_result outcome=unknown reason=no_post_id "
                               f"record={os.path.basename(rec)} release_rc={rc_rel} diag={os.path.basename(diag)}")
            sys.stdout.write(p.stdout)
            sys.exit(1)
        rec = write_record(slug, "published", digest,
                           f"- post_id: {post_id}\n- 방식: publish-post-verified\n")
        rc_rel = release(digest, token)
        if rc_rel != 0:
            log_line(log_path, f"publish_result ok post_id={post_id} record={os.path.basename(rec)} "
                               f"release_rc={rc_rel} release=failed")
            sys.stdout.write(p.stdout)
            print("발행은 성공했으나 예약 해제에 실패했다 — 장애로 보고할 것", file=sys.stderr)
            sys.exit(3)
        log_line(log_path, f"publish_result ok post_id={post_id} record={os.path.basename(rec)} release_rc=0")
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
