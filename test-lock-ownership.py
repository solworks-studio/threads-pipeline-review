#!/usr/bin/env python3
"""잠금 소유권 테스트. 실제 publish-post 호출 없음.
- A 예약 → B 예약 실패 → B의 잘못된 토큰 해제는 거부 → A의 올바른 토큰 해제 성공
- published/unknown 기록이 있으면 예약 거부 (종료코드 3)
- publish-post-verified: 해시 불일치 시 threads-cli 미호출, begin/result 로그 기록
- 동시 예약 경쟁: 승자 1명, 패자는 승자의 예약을 해제할 수 없음
"""
import hashlib, os, subprocess, sys, tempfile, threading

TBIN = os.path.expanduser("~/workspace/threads/bin")
tmp = tempfile.mkdtemp(prefix="lock-test-")
ENV = {**os.environ, "THREADS_BASE": tmp}
os.makedirs(os.path.join(tmp, "queue", "published"), exist_ok=True)

fails = 0
def check(name, cond):
    global fails
    fails += not cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, env=ENV)

DIGEST = "a" * 64

# 1. A 예약 성공 → 토큰 발급
p = run([sys.executable, f"{TBIN}/reserve-publish", DIGEST, "t1"])
token_a = p.stdout.strip()
check("A 예약 성공 + 토큰 발급", p.returncode == 0 and len(token_a) == 32)

# 2. B 예약 실패 (같은 해시)
p = run([sys.executable, f"{TBIN}/reserve-publish", DIGEST, "t1"])
check("B 예약 거부", p.returncode == 1)

# 3. B가 잘못된 토큰으로 해제 시도 → 거부, A 예약 유지
p = run([sys.executable, f"{TBIN}/release-publish", DIGEST, "0" * 32])
still = any(f.endswith(".publishing.md") for f in os.listdir(os.path.join(tmp, "queue", "published")))
check("타인 토큰 해제 거부 + 예약 유지", p.returncode == 1 and still)

# 4. A가 올바른 토큰으로 해제 → 성공
p = run([sys.executable, f"{TBIN}/release-publish", DIGEST, token_a])
gone = not any(f.endswith(".publishing.md") for f in os.listdir(os.path.join(tmp, "queue", "published")))
check("소유자 해제 성공", p.returncode == 0 and gone)

# 5. 토큰 없이 해제 호출 → 거부 (사용법 오류)
p = run([sys.executable, f"{TBIN}/release-publish", DIGEST])
check("토큰 없는 해제 거부", p.returncode == 2)

# 6. published 기록이 있으면 예약 거부 (exit 3)
open(os.path.join(tmp, "queue", "published", "test-pub.md"), "w").write(
    f"SHA-256: {DIGEST}\n상태: published\n")
p = run([sys.executable, f"{TBIN}/reserve-publish", DIGEST, "t1"])
check("published 존재 시 예약 거부(exit 3)", p.returncode == 3)
os.remove(os.path.join(tmp, "queue", "published", "test-pub.md"))

# 7. unknown 기록이 있으면 예약 거부 (exit 3)
open(os.path.join(tmp, "queue", "published", "test-unk.md"), "w").write(
    f"SHA-256: {DIGEST}\n상태: unknown\n")
p = run([sys.executable, f"{TBIN}/reserve-publish", DIGEST, "t1"])
check("unknown 존재 시 예약 거부(exit 3)", p.returncode == 3)
os.remove(os.path.join(tmp, "queue", "published", "test-unk.md"))

# 8. publish-post-verified: 해시 불일치 → threads-cli 미호출
body = os.path.join(tmp, "body.txt")
open(body, "w", encoding="utf-8").write("원본 본문")
logf = os.path.join(tmp, "run.log")
p = run([sys.executable, f"{TBIN}/publish-post-verified", "b" * 64, body,
         "17841427109584787", "--log", logf])
logtxt = open(logf, encoding="utf-8").read() if os.path.exists(logf) else ""
check("해시 불일치 시 발행 차단", p.returncode == 2 and "publish_aborted" in logtxt)

# 9. publish-post-verified: dry-run → begin/result 로그, threads-cli 미호출
real_digest = hashlib.sha256("원본 본문".encode()).hexdigest()
os.remove(logf)
p = run([sys.executable, f"{TBIN}/publish-post-verified", real_digest, body,
         "17841427109584787", "--log", logf, "--dry-run"])
logtxt = open(logf, encoding="utf-8").read()
check("dry-run begin/result 로그", p.returncode == 0
      and "publish_begin" in logtxt and "publish_result" in logtxt
      and f"sha={real_digest[:12]}" in logtxt)

# 10. 동시 예약 경쟁: 승자 1명, 패자는 해제 불가
DIGEST2 = "c" * 64
barrier = threading.Barrier(2)
tokens = {}
def racer(name):
    barrier.wait()
    r = run([sys.executable, f"{TBIN}/reserve-publish", DIGEST2, "race"])
    tokens[name] = (r.returncode, r.stdout.strip())
ts = [threading.Thread(target=racer, args=(f"r{i}",)) for i in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
winners = [n for n, (rc, _) in tokens.items() if rc == 0]
check("동시 예약 승자 1명", len(winners) == 1)
loser = [n for n in tokens if n not in winners][0]
p = run([sys.executable, f"{TBIN}/release-publish", DIGEST2, "f" * 32])
still2 = any(f.endswith(".publishing.md") for f in os.listdir(os.path.join(tmp, "queue", "published")))
check("패자의 해제 시도 거부", p.returncode == 1 and still2)
# 승자가 정리
wtok = tokens[winners[0]][1]
p = run([sys.executable, f"{TBIN}/release-publish", DIGEST2, wtok])
check("승자 해제 성공", p.returncode == 0)

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
