#!/usr/bin/env python3
"""publish-post-verified v3 회귀 테스트 (Codex POLICY-RECHECK 지적 반영).
가짜 CLI가 호출될 때마다 마커 파일에 기록해 '호출 0회'를 검증한다.
- 토큰/슬러그 누락 → exit 2, 호출 0회
- 예약 없음/타인 토큰 → exit 2, 호출 0회, 예약 유지
- 빈 응답/not-json 성공 → unknown, exit 1 (성공 단정 금지)
- 정상 성공 → published + exit 0 / 해제 실패 → exit 3
- 본문 파일 누락 → not_started, unknown 없음, 예약 해제
- 디코딩 오류 → unknown + 진단 파일
- 타임아웃 → 진단 파일에 부분 출력 전체 보존 (끝부분 request-id 포함)
"""
import hashlib, os, stat, subprocess, sys, tempfile

TBIN = os.path.expanduser("~/workspace/threads/bin")
tmp = tempfile.mkdtemp(prefix="wrapper3-test-")
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

OK = fake_cli("cli-ok", 'echo "{\\"post_id\\": \\"777\\"}"\nexit 0\n')
EMPTY = fake_cli("cli-empty", 'exit 0\n')
NOTJSON = fake_cli("cli-notjson", 'echo "hello"\nexit 0\n')
BADUTF = fake_cli("cli-badutf", "printf '\\377\\376 invalid'\nexit 0\n")
LONG = os.path.join(tmp, "longid.txt")
open(LONG, "w").write("x" * 500 + " REQ-ID-AT-END-12345")
SLOW = fake_cli("cli-slow", f'cat {LONG}\nsleep 10\n')

def calls():
    return open(CALLS).read().count("call") if os.path.exists(CALLS) else 0

_seq = [0]
def make_case():
    _seq[0] += 1
    slug = f"c{_seq[0]}"
    body = os.path.join(tmp, f"body-{slug}.txt")
    text = f"본문 {slug}"
    open(body, "w", encoding="utf-8").write(text)
    return slug, body, hashlib.sha256(text.encode()).hexdigest()

def reserve(digest, slug):
    env = {**os.environ, "THREADS_BASE": tmp}
    p = subprocess.run([sys.executable, f"{TBIN}/reserve-publish", digest, slug],
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()

def run(cli, digest, body, slug, token="SKIP", wrapper=None, extra=None):
    env = {**os.environ, "THREADS_BASE": tmp, "THREADS_CLI": cli}
    log = os.path.join(tmp, f"{slug}.log")
    cmd = [sys.executable, wrapper or f"{TBIN}/publish-post-verified", digest, body,
           "17841427109584787", "--log", log]
    if slug is not None:
        cmd += ["--slug", slug]
    if token != "SKIP":
        cmd += ["--token", token]
    if extra:
        cmd += extra
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    logtxt = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    return p, logtxt

def pub_files():
    d = os.path.join(tmp, "queue", "published")
    return os.listdir(d) if os.path.isdir(d) else []

def has_publishing():
    return any(f.endswith(".publishing.md") for f in pub_files())

# 1. 토큰 누락
slug, body, dg = make_case(); reserve(dg, slug)
before = calls()
p, log = run(OK, dg, body, slug)
check("토큰 누락: exit 2 + 호출 0회", p.returncode == 2 and calls() == before)
check("토큰 누락: 예약 유지", has_publishing())

# 2. 슬러그 누락
before = calls()
p, log = run(OK, dg, body, None, token="x" * 32)
check("슬러그 누락: exit 2 + 호출 0회", p.returncode == 2 and calls() == before)

# 3. 타인 토큰
before = calls()
p, log = run(OK, dg, body, slug, token="f" * 32)
check("타인 토큰: exit 2 + 호출 0회 + 예약 유지",
      p.returncode == 2 and calls() == before and has_publishing())
# 정리: 실제 소유자 토큰으로 해제
env = {**os.environ, "THREADS_BASE": tmp}
subprocess.run([sys.executable, f"{TBIN}/release-publish", dg,
                open(os.path.join(tmp, "queue", "published",
                     [f for f in pub_files() if f.endswith(".publishing.md")][0]),
                     encoding="utf-8").read().split("owner: ")[1].strip()],
               capture_output=True, env=env)

# 4. 예약 없음
slug, body, dg = make_case()
before = calls()
p, log = run(OK, dg, body, slug, token="a" * 32)
check("예약 없음: exit 2 + 호출 0회", p.returncode == 2 and calls() == before)

# 5. 빈 성공 응답 → unknown
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(EMPTY, dg, body, slug, token=tok)
check("빈 응답: exit 1 + unknown 기록 + 해제",
      p.returncode == 1 and any(f"{slug}.unknown" in f for f in pub_files()) and not has_publishing())
check("빈 응답: reason=no_post_id 로그", "reason=no_post_id" in log)

# 6. not-json 성공 응답 → unknown
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(NOTJSON, dg, body, slug, token=tok)
check("not-json: exit 1 + unknown 기록", p.returncode == 1
      and any(f"{slug}.unknown" in f for f in pub_files()))

# 7. 정상 성공
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(OK, dg, body, slug, token=tok)
check("정상: exit 0 + published + post_id + 해제",
      p.returncode == 0 and "777" in p.stdout
      and any(slug in f and "unknown" not in f and f.endswith(".md") for f in pub_files())
      and not has_publishing())

# 8. 해제 실패 → exit 3 (래퍼 사본 + 실패하는 release 스텁)
wbin = os.path.join(tmp, "wbin"); os.makedirs(wbin, exist_ok=True)
import shutil
shutil.copy(f"{TBIN}/publish-post-verified", os.path.join(wbin, "publish-post-verified"))
stub = os.path.join(wbin, "release-publish")
open(stub, "w").write("#!/bin/sh\nexit 1\n")
os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(OK, dg, body, slug, token=tok, wrapper=os.path.join(wbin, "publish-post-verified"))
check("해제 실패: exit 3 + published 기록 + release=failed 로그",
      p.returncode == 3 and any(slug in f and "unknown" not in f for f in pub_files())
      and "release=failed" in log)

# 9. 본문 파일 누락 → not_started
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(OK, dg, os.path.join(tmp, "no-such-body.txt"), slug, token=tok)
check("본문 누락: exit 1 + not_started + unknown 없음 + 해제",
      p.returncode == 1 and "not_started" in log
      and not any(f"{slug}.unknown" in f for f in pub_files())
      and not any(slug in f and f.endswith(".publishing.md") for f in pub_files()))

# 10. 디코딩 오류 → unknown + 진단 파일
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(BADUTF, dg, body, slug, token=tok)
diagdir = os.path.join(tmp, "logs")
diags = os.listdir(diagdir) if os.path.isdir(diagdir) else []
check("디코딩 오류: exit 1 + unknown + diag 파일",
      p.returncode == 1 and any(f"{slug}.unknown" in f for f in pub_files())
      and "reason=decode_error" in log and any(slug in d for d in diags))

# 11. 타임아웃 → 진단 파일에 전체 부분 출력 보존
slug, body, dg = make_case(); tok = reserve(dg, slug)
p, log = run(SLOW, dg, body, slug, token=tok, extra=["--timeout", "2"])
diagtxt = ""
for d in os.listdir(diagdir):
    if slug in d:
        diagtxt = open(os.path.join(diagdir, d), encoding="utf-8").read()
check("타임아웃: exit 1 + unknown + 진단에 끝부분 ID 보존",
      p.returncode == 1 and any(f"{slug}.unknown" in f for f in pub_files())
      and "REQ-ID-AT-END-12345" in diagtxt)

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
