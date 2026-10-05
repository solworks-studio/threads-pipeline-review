#!/usr/bin/env python3
"""발행 경로 호출 횟수 검증. 실제 publish-post는 절대 호출하지 않는다.
운영 경로 미러: pre-publish-check(종료코드) → reserve-publish(원자적) →
parse-verdict(엄격) → 가짜 게시 → published 기록.
- 정상 경로: 가짜 게시 1회
- 차단 경로(승인 없음·변조·중복·unknown·publishing·제휴URL없음·판정실패): 0회
- 동시 실행 2스레드: 최대 1회
"""
import hashlib, importlib.util, json, os, subprocess, sys, tempfile, threading
from importlib.machinery import SourceFileLoader
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
TBIN = os.path.expanduser("~/workspace/threads/bin")
tmp = tempfile.mkdtemp(prefix="pubpath-test-")
ENV = {**os.environ, "THREADS_BASE": tmp}
os.makedirs(os.path.join(tmp, "queue", "published"), exist_ok=True)
os.makedirs(os.path.join(tmp, "queue", "approved"), exist_ok=True)

NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y-%m-%d")
STAMP = NOW.strftime("%Y-%m-%d %H:%M")

class FakePublisher:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0
    def publish(self, text):
        with self.lock:
            self.calls += 1
        return "fake_post_id_123"

def load(name):
    return SourceFileLoader(name, os.path.join(TBIN, name)).load_module()

pv = load("parse-verdict")

def write_approval(slug, body_text, aff="false", stamp=STAMP, sched=TODAY, extra=""):
    bpath = os.path.join(tmp, "queue", "approved", slug + ".body.txt")
    open(bpath, "w", encoding="utf-8").write(body_text)
    digest = hashlib.sha256(body_text.encode()).hexdigest()
    apath = os.path.join(tmp, "queue", "approved", slug + ".md")
    aff_line = f"affiliate: {aff}\n" if aff else ""
    open(apath, "w", encoding="utf-8").write(
        f"승인자: 테스트\n승인 시각: {stamp} KST\nscheduled_for: {sched}\n"
        f"대상 계정: @10min.diet.cook\n{aff_line}"
        f"SHA-256: {digest}\n본문 파일: {slug}.body.txt\n{extra}")
    return apath, digest

def add_record(digest, status, at=STAMP):
    fn = os.path.join(tmp, "queue", "published", f"test-{status}-{digest[:8]}.md")
    open(fn, "w", encoding="utf-8").write(
        f"SHA-256: {digest}\n상태: {status}\n시각: {at} KST\n")
    return fn

def publish_attempt(approval_path, slug, digest, verdict_text, publisher):
    """운영 경로 미러. 반환: 게시 호출 여부(bool)."""
    # 1. 상태 확인 (종료코드로 판단)
    p = subprocess.run([sys.executable, os.path.join(TBIN, "pre-publish-check"),
                        approval_path, "--date", TODAY],
                       capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        return False
    # 2. 원자적 예약 (토큰 보관)
    p = subprocess.run([sys.executable, os.path.join(TBIN, "reserve-publish"),
                        digest, slug], capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        return False
    token = p.stdout.strip()
    try:
        # 3. 엄격 판정 파서 (final-audit과 동일)
        r = pv.parse(verdict_text)
        if not r["pass"]:
            return False
        # 4. 게시 (가짜) — 래퍼의 해시 검증을 흉내: 본문 해시 재확인
        body_bytes = open(
            os.path.join(tmp, "queue", "approved", slug + ".body.txt"),
            "rb").read()
        if hashlib.sha256(body_bytes).hexdigest() != digest:
            return False
        post_id = publisher.publish(body_bytes.decode("utf-8"))
        # 5. 기록
        open(os.path.join(tmp, "queue", "published", f"{TODAY}-{slug}.md"),
             "w", encoding="utf-8").write(
            f"# 발행 기록\n- SHA-256: {digest}\n- 상태: published\n"
            f"- 시각: {STAMP} KST\n- post_id: {post_id}\n")
        return True
    finally:
        # 토큰 보유자만 해제. 토큰이 없으면 호출하지 않는다 (설계상 항상 있음).
        subprocess.run([sys.executable, os.path.join(TBIN, "release-publish"),
                        digest, token], capture_output=True, env=ENV)

GOOD_VERDICT = "판정: 통과\n지적:\n- 없음"
BAD_VERDICT = "판정: 수정필요\n지적:\n- 수정하면 통과 가능"

fails = 0
def expect(name, got_calls, expect_calls):
    global fails
    ok = got_calls == expect_calls
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: 게시 호출 {got_calls}회 (기대 {expect_calls}회)")

# 1. 정상 경로 → 1회
pub = FakePublisher()
ap, dg = write_approval("t-normal", "정상 본문")
publish_attempt(ap, "t-normal", dg, GOOD_VERDICT, pub)
expect("정상 경로", pub.calls, 1)

# 2. 차단 경로 → 0회
cases = []
ap2, dg2 = write_approval("t-tamper", "원본")
open(os.path.join(tmp, "queue", "approved", "t-tamper.body.txt"), "w",
     encoding="utf-8").write("변조됨")
cases.append(("승인 후 변조", ap2, "t-tamper", dg2, GOOD_VERDICT))
cases.append(("승인 파일 없음", "/nonexistent.md", "t-none", "0" * 64, GOOD_VERDICT))
ap4, dg4 = write_approval("t-exp", "본문", stamp=(NOW - timedelta(days=4)).strftime("%Y-%m-%d %H:%M"))
cases.append(("승인 만료", ap4, "t-exp", dg4, GOOD_VERDICT))
ap5, dg5 = write_approval("t-dup", "중복 본문")
add_record(dg5, "published")
cases.append(("중복 발행", ap5, "t-dup", dg5, GOOD_VERDICT))
ap6, dg6 = write_approval("t-unk", "불명 본문")
add_record(dg6, "unknown")
cases.append(("결과 불명", ap6, "t-unk", dg6, GOOD_VERDICT))
ap7, dg7 = write_approval("t-ping", "진행중 본문")
add_record(dg7, "publishing")
cases.append(("발행 진행 중", ap7, "t-ping", dg7, GOOD_VERDICT))
ap8, dg8 = write_approval("t-aff", "이 포스팅은 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받습니다.\n상품 추천",
                          aff="true")
cases.append(("제휴 URL 없음", ap8, "t-aff", dg8, GOOD_VERDICT))
ap9, dg9 = write_approval("t-verdict", "본문")
cases.append(("판정 수정필요", ap9, "t-verdict", dg9, BAD_VERDICT))
cases.append(("판정 없음", ap9, "t-verdict2", dg9, "지적: 문제 있음"))

for name, ap_, slug_, dg_, verdict_ in cases:
    pub = FakePublisher()
    # 각 케이스마다 독립 해시가 필요하므로 승인 파일을 복제한다
    publish_attempt(ap_, slug_, dg_, verdict_, pub)
    expect(f"차단: {name}", pub.calls, 0)

# 3. 동시 실행 → 최대 1회
pub = FakePublisher()
apc, dgc = write_approval("t-race", "동시 본문")
barrier = threading.Barrier(2)
results = []
def racer():
    barrier.wait()
    results.append(publish_attempt(apc, "t-race", dgc, GOOD_VERDICT, pub))
ts = [threading.Thread(target=racer) for _ in range(2)]
[t.start() for t in ts]
[t.join() for t in ts]
ok = pub.calls <= 1
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 동시 실행: 게시 호출 {pub.calls}회 (기대 최대 1회)")

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
