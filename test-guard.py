#!/usr/bin/env python3
"""가드 검사 단위 테스트. 격리된 임시 BASE + 실행 시점 타임스탬프 사용 (나중에 재현 가능).
실제 Threads/GPT 호출 없음. publish-post 호출 없음.
각 케이스는 해당 검사 항목의 pass 값을 직접 확인한다.
"""
import hashlib, importlib.util, os, sys, tempfile
from importlib.machinery import SourceFileLoader
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE_BIN = os.path.expanduser("~/workspace/threads/bin/pre-publish-check")
guard = SourceFileLoader("guard", BASE_BIN).load_module()

tmp = tempfile.mkdtemp(prefix="guard-test-")
guard.BASE = tmp
guard.check_connectivity = lambda *a, **k: True
os.makedirs(os.path.join(tmp, "queue", "published"), exist_ok=True)

NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y-%m-%d")
STAMP = NOW.strftime("%Y-%m-%d %H:%M")
OLD = (NOW - timedelta(days=4)).strftime("%Y-%m-%d %H:%M")

fails = 0
def check(name, approval_text, body_text, item_name, expect_pass):
    global fails
    bpath = os.path.join(tmp, "body.txt")
    open(bpath, "w", encoding="utf-8").write(body_text)
    digest = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    apath = os.path.join(tmp, "approval.md")
    open(apath, "w", encoding="utf-8").write(
        approval_text.replace("{DIGEST}", digest))
    ap = guard.parse_approval(apath)
    # parse_approval 대신 전체 검사를 돌리기 위해 main 로직을 흉내내지 않고,
    # published_records와 개별 판정을 직접 검증한다.
    # 간단히: rec() 수집용 가짜 main을 실행한다.
    import io, contextlib
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            sys.argv = ["pre-publish-check", apath, "--date", TODAY]
            guard.main()
        except SystemExit as e:
            code = e.code
    import json
    d = json.loads(buf.getvalue())
    item = next((c for c in d["checks"] if c["name"] == item_name), None)
    got = item["pass"] if item else None
    ok = (got is expect_pass)
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {item_name}={got} (기대 {expect_pass})")

def mk_aff(aff): return f"affiliate: {aff}\n" if aff else ""
def base_approval(body="정상 본문", aff="false", stamp=STAMP, sched=TODAY,
                  extra=""):
    return (f"승인자: 테스트\n승인 시각: {stamp} KST\nscheduled_for: {sched}\n"
            f"대상 계정: @10min.diet.cook\n{mk_aff(aff)}"
            f"SHA-256: {{DIGEST}}\n본문 파일: body.txt\n{extra}")

def add_record(digest, status, at=STAMP):
    fn = os.path.join(tmp, "queue", "published", f"test-{status}.md")
    open(fn, "w", encoding="utf-8").write(
        f"SHA-256: {digest}\n상태: {status}\n시각: {at} KST\n")
    return fn

# 1. 정상
check("정상 승인", base_approval(), "정상 본문", "제휴 정합성", True)
# 2. 승인 후 변조
b = os.path.join(tmp, "body.txt"); open(b, "w", encoding="utf-8").write("원본")
d0 = hashlib.sha256("원본".encode()).hexdigest()
open(os.path.join(tmp, "approval.md"), "w", encoding="utf-8").write(
    base_approval().replace("{DIGEST}", d0))
open(b, "w", encoding="utf-8").write("변조됨")
import io, contextlib, json
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        sys.argv = ["pre-publish-check", os.path.join(tmp, "approval.md"), "--date", TODAY]
        guard.main()
    except SystemExit:
        pass
d = json.loads(buf.getvalue())
item = next(c for c in d["checks"] if c["name"] == "해시 일치")
ok = item["pass"] is False
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 승인 후 변조 차단: 해시 일치={item['pass']} (기대 False)")
# 3. 중복
open(b, "w", encoding="utf-8").write("중복 본문")
d1 = hashlib.sha256("중복 본문".encode()).hexdigest()
fn1 = add_record(d1, "published")
open(os.path.join(tmp, "approval.md"), "w", encoding="utf-8").write(
    base_approval().replace("{DIGEST}", d1))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        sys.argv = ["pre-publish-check", os.path.join(tmp, "approval.md"), "--date", TODAY]
        guard.main()
    except SystemExit:
        pass
d = json.loads(buf.getvalue())
item = next(c for c in d["checks"] if c["name"] == "중복 발행 없음")
ok = item["pass"] is False
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 중복 발행 차단: {item['pass']} (기대 False)")
os.remove(fn1)
# 4. unknown
fn2 = add_record(d1, "unknown")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        sys.argv = ["pre-publish-check", os.path.join(tmp, "approval.md"), "--date", TODAY]
        guard.main()
    except SystemExit:
        pass
d = json.loads(buf.getvalue())
item = next(c for c in d["checks"] if c["name"] == "결과 불명 없음")
ok = item["pass"] is False
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] unknown 차단: {item['pass']} (기대 False)")
os.remove(fn2)
# 5. publishing (신규)
fn3 = add_record(d1, "publishing")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        sys.argv = ["pre-publish-check", os.path.join(tmp, "approval.md"), "--date", TODAY]
        guard.main()
    except SystemExit:
        pass
d = json.loads(buf.getvalue())
item = next(c for c in d["checks"] if c["name"] == "발행 진행 중 아님")
ok = item["pass"] is False and "동시 실행" in item["detail"]
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] publishing 차단: {item['pass']} (기대 False)")
os.remove(fn3)
# 6. publishing stale (2시간 전)
stale_at = (NOW - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
fn4 = add_record(d1, "publishing", stale_at)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try:
        sys.argv = ["pre-publish-check", os.path.join(tmp, "approval.md"), "--date", TODAY]
        guard.main()
    except SystemExit:
        pass
d = json.loads(buf.getvalue())
item = next(c for c in d["checks"] if c["name"] == "발행 진행 중 아님")
ok = item["pass"] is False and "원격" in item["detail"]
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] stale publishing 원격확인 요구: {item['pass']} (기대 False)")
os.remove(fn4)
# 7. 만료
check("승인 만료", base_approval(stamp=OLD), "정상 본문", "승인 유효기간", False)
# 8. affiliate 필드 누락 → 차단
check("affiliate 누락", base_approval(aff=None), "정상 본문", "제휴 정합성", False)
# 9. affiliate=true + 고지 있음 + URL 없음 → 차단
check("제휴 URL 없음", base_approval(aff="true"),
      "이 포스팅은 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받습니다.\n추천 상품", "제휴 정합성", False)
# 10. affiliate=true + 고지 없음 → 차단
check("제휴 고지 없음", base_approval(aff="true"),
      "추천 상품 https://link.coupang.com/a/xyz", "제휴 정합성", False)
# 11. affiliate=true + 고지 + URL → 통과
check("제휴 정상", base_approval(aff="true"),
      "이 포스팅은 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받습니다.\nhttps://link.coupang.com/a/xyz", "제휴 정합성", True)

# 종료코드 검증 (실제 서브프로세스 + 격리 BASE)
import subprocess
env = {**os.environ, "THREADS_BASE": tmp}
# threads-cli 호출을 피하기 위해 격리 BASE에 가짜 published만 두고,
# 계정 연결 검사는 실제 호출되므로 여기서는 해시 불일치 케이스로 종료코드만 본다.
open(os.path.join(tmp, "approval.md"), "w", encoding="utf-8").write(
    base_approval().replace("{DIGEST}", "0" * 64))  # 해시 불일치 → 차단
open(b, "w", encoding="utf-8").write("중복 본문")
p = subprocess.run([sys.executable, BASE_BIN, os.path.join(tmp, "approval.md"),
                    "--date", TODAY], capture_output=True, text=True, env=env)
ok = p.returncode == 2
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 차단 시 종료코드 2 (실제 {p.returncode})")
d = json.loads(p.stdout)
ok = d["ok"] is False
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 차단 시 JSON ok=false")

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
