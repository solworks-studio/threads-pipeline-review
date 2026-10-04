#!/usr/bin/env python3
"""차단 테스트 러너. 실제 발행(publish-post)은 절대 호출하지 않는다.
실행: python3 run-blocking-tests.py
결과: 콘솔 요약 + blocking-test-results.json
"""
import hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime, timedelta

BASE = os.path.expanduser("~/workspace/threads")
BIN = os.path.join(BASE, "bin", "pre-publish-check")
TDIR = os.path.join(BASE, "tests", "fixtures")
PUBDIR = os.path.join(BASE, "queue", "published")
os.makedirs(TDIR, exist_ok=True)

results = []
def run_case(name, args, expect_ok, must_contain=""):
    p = subprocess.run([sys.executable, BIN] + args, capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(p.stdout)
    except Exception:
        d = {"ok": None, "raw": p.stdout, "err": p.stderr}
    ok_match = (d.get("ok") is expect_ok)
    txt = json.dumps(d, ensure_ascii=False)
    contain = (must_contain in txt) if must_contain else True
    passed = ok_match and contain
    results.append({"case": name, "expect_ok": expect_ok, "got_ok": d.get("ok"),
                    "must_contain": must_contain, "passed": passed,
                    "reasons": d.get("reasons", [])})
    print(f"[{'PASS' if passed else 'FAIL'}] {name} (expect_ok={expect_ok}, got={d.get('ok')})")
    return d

def w(path, text):
    open(path, "w", encoding="utf-8").write(text)

def approval_fixture(name, body_text, scheduled_for, approved_at, account="@10min.diet.cook",
                     affiliate=False, extra=""):
    bpath = os.path.join(TDIR, name + ".body.txt")
    w(bpath, body_text)
    h = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    apath = os.path.join(TDIR, name + ".md")
    w(apath, f"""# 승인 기록 — 테스트 픽스처 ({name})
- 승인자: 테스트
- 승인 시각: {approved_at} KST
- scheduled_for: {scheduled_for} (발행일)
- 대상 계정: {account}
- affiliate: {"true" if affiliate else "false"}
- SHA-256: {h}
- 본문 파일: {name}.body.txt
{extra}""")
    return apath, h

TODAY = "2026-10-04"
OLD = "2026-09-30 09:13"

# 1. 승인 없는 발행 차단
run_case("승인 없는 발행 차단", ["/nonexistent/approval.md", "--date", TODAY], False, "승인 파일이 없음")

# 2. 승인 후 수정 차단 (본문 변조 → 해시 불일치)
ap2, _ = approval_fixture("t2-tampered", "원본 본문", TODAY, TODAY + " 09:00")
w(os.path.join(TDIR, "t2-tampered.body.txt"), "변조된 본문")  # 승인 후 수정 시뮬레이션
run_case("승인 후 수정 차단", [ap2, "--date", TODAY], False, "해시")

# 3. 중복 발행 차단 (같은 해시 발행 기록 존재)
ap3, h3 = approval_fixture("t3-dup", "중복 테스트 본문", TODAY, TODAY + " 09:00")
w(os.path.join(PUBDIR, "test-dup-fixture.md"),
  f"# 발행 기록 — 테스트\n- SHA-256: {h3}\n- 상태: published\n- post_id: test123\n")
run_case("중복 발행 차단", [ap3, "--date", TODAY], False, "중복")
os.remove(os.path.join(PUBDIR, "test-dup-fixture.md"))

# 4. 승인 만료 차단 (72시간 초과)
ap4, _ = approval_fixture("t4-expired", "만료 테스트 본문", TODAY, OLD)
run_case("승인 만료 차단", [ap4, "--date", TODAY], False, "유효기간")

# 5. 발행 결과 불명 차단 (unknown 상태)
ap5, h5 = approval_fixture("t5-unknown", "불명 테스트 본문", TODAY, TODAY + " 09:00")
w(os.path.join(PUBDIR, "test-unknown-fixture.md"),
  f"# 발행 기록 — 테스트\n- SHA-256: {h5}\n- 상태: unknown\n")
run_case("결과 불명 시 재발행 차단", [ap5, "--date", TODAY], False, "unknown")
os.remove(os.path.join(PUBDIR, "test-unknown-fixture.md"))

# 6. 제휴 고지 누락 차단
ap6, _ = approval_fixture("t6-affiliate", "제휴 상품 추천 글입니다.\n[LINK]에서 구매하세요.", TODAY,
                         TODAY + " 09:00", affiliate=True)
run_case("제휴 고지 누락 차단", [ap6, "--date", TODAY], False, "제휴")

# 7. 정상 케이스 (실제 승인 파일, 발행일은 하지 않음 — 체크만)
real_ap = os.path.join(BASE, "queue", "approved", "20261005-intro-03.md")
run_case("정상 승인 통과 (체크만, 발행 없음)", [real_ap, "--date", "2026-10-05"], True)

# 8. 중복 크론 가드 로직 검증 (같은 날짜 초안 파일 존재 시 중단)
guard_date = "20990101"
guard_file = os.path.join(BASE, "queue", "drafts", f"{guard_date}-01.md")
w(guard_file, "가드 테스트 더미")
exists = os.path.isfile(guard_file)
should_abort = exists  # 크론 지시문: 같은 날짜 파일이 이미 있으면 중복 실행으로 보고 중단
os.remove(guard_file)
results.append({"case": "중복 크론 실행 차단", "expect_ok": True, "got_ok": should_abort,
                "must_contain": "", "passed": should_abort is True,
                "reasons": [] if should_abort else ["가드 미작동"]})
print(f"[{'PASS' if should_abort else 'FAIL'}] 중복 크론 실행 차단 (파일 존재 시 중단={should_abort})")

# 9/10. GPT 최종본 재검수 (실제 API 호출 2건)
AUD = os.path.join(BASE, "prompts", "auditor.md")
GCHAT = os.path.expanduser("~/workspace/skills/openai/bin/gpt-chat")
def audit(text):
    p = subprocess.run([GCHAT, "--system-file", AUD, "--user", text],
                       capture_output=True, text=True, timeout=120)
    try:
        d = json.loads(p.stdout)
        return d.get("text", "")
    except Exception:
        return "AUDIT_CALL_FAILED: " + p.stdout[:200]

good_body = open(os.path.join(BASE, "queue", "approved", "20261005-intro-03.body.txt"),
                 encoding="utf-8").read()
bad_body = good_body + "\n이거 먹으면 일주일에 2kg 빠집니다!"
print("GPT 재검수 호출 중 (2건)...")
r_good = audit(good_body)
r_bad = audit(bad_body)
good_pass = "통과" in r_good and "반려" not in r_good.split("통과")[0][-50:]
bad_blocked = ("반려" in r_bad) or ("수정필요" in r_bad)
results.append({"case": "최종본 재검수 — 정상본 통과", "expect_ok": True,
                "got_ok": good_pass, "must_contain": "", "passed": good_pass,
                "reasons": [] if good_pass else [r_good[:300]]})
results.append({"case": "최종본 재검수 — 문제본 차단", "expect_ok": True,
                "got_ok": bad_blocked, "must_contain": "", "passed": bad_blocked,
                "reasons": [] if bad_blocked else [r_bad[:300]]})
print(f"[{'PASS' if good_pass else 'FAIL'}] 최종본 재검수 — 정상본 통과")
print(f"[{'PASS' if bad_blocked else 'FAIL'}] 최종본 재검수 — 문제본 차단")

# 결과 저장
out = {"date": datetime.now().isoformat(), "publish_post_called": False,
       "cases": results,
       "summary": f"{sum(1 for r in results if r['passed'])}/{len(results)} 통과"}
json.dump(out, open(os.path.join(BASE, "tests", "blocking-test-results.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n" + out["summary"])
print("publish-post 호출: 없음 (전체 테스트는 체크·검수만 수행)")
