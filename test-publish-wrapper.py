#!/usr/bin/env python3
"""publish-post-verified v2 테스트. 가짜 CLI로 성공/실패/타임아웃/미실행을 주입한다.
- 성공: published 기록 + post_id + 예약 해제
- 실패(rc!=0): unknown 기록 + 예약 해제
- 타임아웃: 부분 출력 보존 + unknown 기록 + 예약 해제
- CLI 없음(OSError): unknown 기록 없음(not_started) + 예약 해제
- 해시 불일치: 기록 없음 + 예약 해제 + exit 2
"""
import hashlib, os, stat, subprocess, sys, tempfile

TBIN = os.path.expanduser("~/workspace/threads/bin")
tmp = tempfile.mkdtemp(prefix="wrapper-test-")
os.makedirs(os.path.join(tmp, "queue", "published"), exist_ok=True)
os.makedirs(os.path.join(tmp, "bin"), exist_ok=True)

fails = 0
def check(name, cond):
    global fails
    fails += not cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")

def fake_cli(name, script):
    p = os.path.join(tmp, "bin", name)
    open(p, "w").write("#!/bin/sh\n" + script)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p

OK = fake_cli("cli-ok", 'echo "{\\"post_id\\": \\"999\\"}"\nexit 0\n')
FAIL = fake_cli("cli-fail", 'echo "some error" >&2\nexit 3\n')
SLOW = fake_cli("cli-slow", 'echo "partial-out"\necho "partial-err" >&2\nsleep 10\n')

def make_case(slug):
    body = os.path.join(tmp, f"body-{slug}.txt")
    text = f"테스트 본문 {slug}"
    open(body, "w", encoding="utf-8").write(text)
    return body, hashlib.sha256(text.encode()).hexdigest()

def reserve(slug, digest):
    env = {**os.environ, "THREADS_BASE": tmp}
    p = subprocess.run([sys.executable, f"{TBIN}/reserve-publish", digest, slug],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()

def run(cli, slug, token, extra=None):
    body, digest = make_case(slug)
    env = {**os.environ, "THREADS_BASE": tmp, "THREADS_CLI": cli}
    log = os.path.join(tmp, f"{slug}.log")
    cmd = [sys.executable, f"{TBIN}/publish-post-verified", digest, body,
           "17841427109584787", "--slug", slug, "--token", token, "--log", log]
    if extra:
        cmd += extra
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    logtxt = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    return p, logtxt

def pub_files():
    return os.listdir(os.path.join(tmp, "queue", "published"))

def has_publishing():
    return any(f.endswith(".publishing.md") for f in pub_files())

# 1. 성공
tok = reserve("ok1", make_case("ok1")[1])
p, log = run(OK, "ok1", tok)
check("성공: exit 0 + post_id 출력", p.returncode == 0 and "999" in p.stdout)
check("성공: published 기록", any("ok1" in f and f.endswith(".md") and "unknown" not in f for f in pub_files()))
check("성공: 예약 해제됨", not has_publishing())
check("성공: publish_result ok 로그", "publish_result ok" in log and "release_rc=0" in log)

# 2. CLI 실패
tok = reserve("fail1", make_case("fail1")[1])
p, log = run(FAIL, "fail1", tok)
check("실패: exit 3 전파", p.returncode == 3)
check("실패: unknown 기록", any("fail1.unknown" in f for f in pub_files()))
check("실패: 예약 해제됨", not has_publishing())
check("실패: outcome=unknown 로그", "outcome=unknown" in log and "reason=cli_error" in log)

# 3. 타임아웃 (2초)
tok = reserve("slow1", make_case("slow1")[1])
p, log = run(SLOW, "slow1", tok, extra=["--timeout", "2"])
check("타임아웃: exit 1", p.returncode == 1)
check("타임아웃: unknown 기록", any("slow1.unknown" in f for f in pub_files()))
check("타임아웃: 예약 해제됨", not has_publishing())
diagdir = os.path.join(tmp, "logs")
diagtxt = ""
if os.path.isdir(diagdir):
    for d in os.listdir(diagdir):
        if "slow1" in d:
            diagtxt = open(os.path.join(diagdir, d), encoding="utf-8").read()
check("타임아웃: reason=timeout + 부분 출력 보존",
      "reason=timeout" in log and "diag=" in log
      and "partial-out" in diagtxt and "partial-err" in diagtxt)

# 4. CLI 없음 (OSError)
tok = reserve("noexe", make_case("noexe")[1])
p, log = run("/nonexistent/cli", "noexe", tok)
check("미실행: exit 1", p.returncode == 1)
check("미실행: unknown 기록 없음", not any("noexe.unknown" in f for f in pub_files()))
check("미실행: 예약 해제됨", not has_publishing())
check("미실행: not_started 로그", "outcome=not_started" in log)

# 5. 해시 불일치
BODY5, DIGEST5 = make_case("badhash")
tok = reserve("badhash", "0" * 64)
env = {**os.environ, "THREADS_BASE": tmp, "THREADS_CLI": OK}
log = os.path.join(tmp, "badhash.log")
p = subprocess.run([sys.executable, f"{TBIN}/publish-post-verified", "0" * 64, BODY5,
                    "17841427109584787", "--slug", "badhash", "--token", tok, "--log", log],
                   capture_output=True, text=True, env=env)
check("해시 불일치: exit 2", p.returncode == 2)
check("해시 불일치: unknown/published 기록 없음",
      not any("badhash" in f and not f.endswith(".publishing.md") for f in pub_files()))
check("해시 불일치: 예약 해제됨", not has_publishing())

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
