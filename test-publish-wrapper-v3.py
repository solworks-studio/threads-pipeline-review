#!/usr/bin/env python3
"""publish-post-verified v4 회귀 테스트 (Codex POLICY-RECHECK-V2 지적 반영).
- CLI 종료코드 3 → 래퍼 종료코드 1 + unknown (성공 코드 3과 충돌 해소), cli_rc는 로그에만
- 유효 토큰 + 다른 슬러그 → exit 2, CLI 호출 0회, 예약 유지 (소유권에 슬러그 포함)
- post_id가 객체/불리언 → unknown (invalid_post_id), 정수 → published 허용
- 비UTF-8 본문 → not_started + 예약 해제, CLI 호출 0회 (예약 잔류 해소)
"""
import hashlib, os, stat, subprocess, sys, tempfile

TBIN = os.path.expanduser("~/workspace/threads/bin")
tmp = tempfile.mkdtemp(prefix="wrapper4-test-")
os.makedirs(os.path.join(tmp, "queue", "published"), exist_ok=True)
os.makedirs(os.path.join(tmp, "bin"), exist_ok=True)
CALLS = os.path.join(tmp, "calls.txt")

fails = 0
def check(name, cond):
    global fails
    fails += not cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")

def fake_cli(name, script):
    p = os.path.join(tmp, "bin", name)
    open(p, "w").write("#!/bin/sh\n" + f'echo call >> {CALLS}\n' + script)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p

def calls():
    return open(CALLS).read().count("call") if os.path.exists(CALLS) else 0

RC3 = fake_cli("cli-rc3", 'echo "boom" >&2\nexit 3\n')
OBJID = fake_cli("cli-objid", 'echo "{\\"post_id\\": {\\"error\\": \\"pending\\"}}"\nexit 0\n')
INTID = fake_cli("cli-intid", 'echo "{\\"post_id\\": 777}"\nexit 0\n')
BOOLID = fake_cli("cli-boolid", 'echo "{\\"post_id\\": true}"\nexit 0\n')
OK = fake_cli("cli-ok", 'echo "{\\"post_id\\": \\"555\\"}"\nexit 0\n')

_seq = [0]
def make_case(body_bytes=None):
    _seq[0] += 1
    slug = f"w{_seq[0]}"
    body = os.path.join(tmp, f"body-{slug}.txt")
    data = body_bytes if body_bytes is not None else f"본문 {slug}".encode()
    open(body, "wb").write(data)
    return slug, body, hashlib.sha256(data).hexdigest()

def reserve(digest, slug):
    env = {**os.environ, "THREADS_BASE": tmp}
    p = subprocess.run([sys.executable, f"{TBIN}/reserve-publish", digest, slug],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()

def release(digest, token):
    env = {**os.environ, "THREADS_BASE": tmp}
    subprocess.run([sys.executable, f"{TBIN}/release-publish", digest, token],
                   capture_output=True, env=env)

def run(cli, digest, body, slug, token):
    env = {**os.environ, "THREADS_BASE": tmp, "THREADS_CLI": cli}
    log = os.path.join(tmp, f"{slug}.log")
    p = subprocess.run([sys.executable, f"{TBIN}/publish-post-verified", digest, body,
                        "17841427109584787", "--slug", slug, "--token", token, "--log", log],
                       capture_output=True, text=True, env=env)
    logtxt = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    return p, logtxt

def pub_files():
    d = os.path.join(tmp, "queue", "published")
    return os.listdir(d) if os.path.isdir(d) else []

def has_publishing():
    return any(f.endswith(".publishing.md") for f in pub_files())

# 1. CLI rc=3 → 래퍼 exit 1 (3 아님) + unknown + cli_rc 로그
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(RC3, dg, body, slug, tok)
check("CLI rc=3: 래퍼 exit 1 (성공 코드 3과 충돌 없음)", p.returncode == 1)
check("CLI rc=3: unknown 기록 + cli_rc=3 로그 + 해제",
      any(f"{slug}.unknown" in f for f in pub_files())
      and "cli_rc=3" in log and "outcome=unknown" in log and not has_publishing())

# 2. 슬러그 불일치 (토큰·해시는 유효) → exit 2, 호출 0회, 예약 유지
slug, body, dg = make_case(); tok = reserve(dg, slug)
before = calls()
p, log = run(OK, dg, body, "different-slot", tok)
check("슬러그 불일치: exit 2 + 호출 0회 + 예약 유지",
      p.returncode == 2 and calls() == before and has_publishing())
check("슬러그 불일치: 기록 파일 없음",
      not any("different-slot" in f for f in pub_files()))
release(dg, tok)

# 3. post_id 객체 → unknown (invalid_post_id)
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(OBJID, dg, body, slug, tok)
check("post_id 객체: exit 1 + unknown + invalid_post_id",
      p.returncode == 1 and any(f"{slug}.unknown" in f for f in pub_files())
      and "reason=invalid_post_id" in log and not has_publishing())

# 4. post_id 정수 → published
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(INTID, dg, body, slug, tok)
check("post_id 정수: exit 0 + published + post_id=777",
      p.returncode == 0 and any(slug in f and "unknown" not in f for f in pub_files())
      and "post_id=777" in log)

# 5. post_id 불리언 → unknown
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(BOOLID, dg, body, slug, tok)
check("post_id 불리언: exit 1 + unknown",
      p.returncode == 1 and any(f"{slug}.unknown" in f for f in pub_files()))

# 6. 비UTF-8 본문 → not_started + 해제 + 호출 0회
slug, body, dg = make_case(body_bytes=b"\xff\xfe\x00broken")
tok = reserve(dg, slug)
before = calls()
p, log = run(OK, dg, body, slug, tok)
check("비UTF-8 본문: exit 1 + not_started + unknown 없음 + 해제 + 호출 0회",
      p.returncode == 1 and "outcome=not_started" in log and "reason=body_not_utf8" in log
      and not any(f"{slug}.unknown" in f for f in pub_files())
      and not has_publishing() and calls() == before)

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
