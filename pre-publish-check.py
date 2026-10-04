#!/usr/bin/env python3
"""발행 전 상태 확인. 실제 발행은 하지 않는다.
사용법: pre-publish-check <승인파일경로> [--date YYYYMMDD] [--threads-bin <경로>]
출력 JSON: {"ok": bool, "checks": [{"name","pass","detail"}], "reasons": [...]}
검증 항목:
  1. 승인 파일 존재
  2. scheduled_for == 기준일
  3. 본문 파일 존재
  4. SHA-256 해시 일치 (승인 후 수정 차단)
  5. 대상 계정 일치 (@10min.diet.cook)
  6. threads-cli accounts로 계정 연결 확인
  7. 승인 만료 (승인 후 72시간 이내)
  8. 중복 발행 방지 (같은 해시의 published 기록 없음)
  9. 발행 결과 불명 차단 (같은 해시의 unknown 상태 없음)
  10. 제휴 정합성 (affiliate=true면 첫 줄 고지 + 미치환 토큰 없음)
"""
import hashlib, json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

BASE = os.path.expanduser("~/workspace/threads")
EXPECTED_ACCOUNT = "10min.diet.cook"
EXPECTED_ACCOUNT_ID = "17841427109584787"
APPROVAL_TTL_HOURS = 72
DISCLOSURE_PHRASE = "쿠팡 파트너스 활동의 일환으로"
KST = timezone(timedelta(hours=9))

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def parse_approval(path):
    text = open(path, encoding="utf-8").read()
    def grab(pat):
        m = re.search(pat, text, re.M)
        return m.group(1).strip() if m else None
    return {
        "scheduled_for": grab(r"scheduled_for:\s*(\d{4}-\d{2}-\d{2})"),
        "sha256": grab(r"SHA-256:\s*([0-9a-f]{64})"),
        "body_file": grab(r"본문 파일:\s*(\S+)"),
        "account": grab(r"대상 계정:\s*(\S+)"),
        "approved_at": grab(r"승인 시각:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"),
        "affiliate": (grab(r"affiliate:\s*(true|false)") or "false") == "true",
        "raw": text,
    }

def check_connectivity(threads_bin="threads-cli"):
    try:
        out = subprocess.run([threads_bin, "accounts"], capture_output=True,
                             text=True, timeout=30)
        data = json.loads(out.stdout or "{}")
        accts = data.get("accounts", [])
        return any(a.get("username") == EXPECTED_ACCOUNT for a in accts)
    except Exception:
        return False

def published_records():
    recs = []
    pubdir = os.path.join(BASE, "queue", "published")
    if not os.path.isdir(pubdir):
        return recs
    for fn in os.listdir(pubdir):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(pubdir, fn), encoding="utf-8").read()
        h = re.search(r"SHA-256:\s*([0-9a-f]{64})", text)
        st = re.search(r"상태:\s*(\w+)", text)
        recs.append({"file": fn,
                     "sha256": h.group(1) if h else None,
                     "status": st.group(1) if st else "published"})
    return recs

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "reasons": ["usage: pre-publish-check <승인파일> [--date YYYYMMDD]"]},
                         ensure_ascii=False))
        sys.exit(1)
    approval_path = sys.argv[1]
    if "--date" in sys.argv:
        today = sys.argv[sys.argv.index("--date") + 1]
    else:
        today = datetime.now(KST).strftime("%Y-%m-%d")

    checks, reasons = [], []

    def rec(name, passed, detail=""):
        checks.append({"name": name, "pass": passed, "detail": detail})
        if not passed:
            reasons.append(f"{name}: {detail}")

    # 1. 승인 파일 존재 (승인 없는 발행 차단)
    if not os.path.isfile(approval_path):
        rec("승인파일 존재", False, "승인 파일이 없음 — 발행 차단")
        print(json.dumps({"ok": False, "checks": checks, "reasons": reasons}, ensure_ascii=False))
        return
    rec("승인파일 존재", True, os.path.basename(approval_path))
    ap = parse_approval(approval_path)

    # 2. scheduled_for == 기준일
    rec("발행일 일치", ap["scheduled_for"] == today,
        f"scheduled_for={ap['scheduled_for']}, 기준일={today}")

    # 3. 본문 파일 존재
    body_path = None
    if ap["body_file"]:
        cand = ap["body_file"]
        body_path = cand if os.path.isabs(cand) else os.path.join(os.path.dirname(approval_path), cand)
    rec("본문파일 존재", bool(body_path and os.path.isfile(body_path or "")),
        body_path or "본문 파일 경로 없음")
    body_text = open(body_path, encoding="utf-8").read() if body_path and os.path.isfile(body_path) else ""

    # 4. 해시 일치 (승인 후 수정 차단)
    if ap["sha256"] and body_path and os.path.isfile(body_path):
        actual = sha256_file(body_path)
        rec("해시 일치", actual == ap["sha256"],
            "일치" if actual == ap["sha256"] else "불일치 — 승인 후 수정됨, 발행 차단")
    else:
        rec("해시 일치", False, "해시 또는 본문 없음")

    # 5. 대상 계정 일치 (@ 접두사 정규화)
    acct = (ap["account"] or "").lstrip("@")
    rec("대상 계정", acct == EXPECTED_ACCOUNT,
        f"기록={ap['account']}, 기대={EXPECTED_ACCOUNT}")

    # 6. 계정 연결 확인
    rec("계정 연결", check_connectivity(), "threads-cli accounts")

    # 7. 승인 만료 (72시간)
    try:
        approved_at = datetime.strptime(ap["approved_at"], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        age_h = (datetime.now(KST) - approved_at).total_seconds() / 3600
        rec("승인 유효기간", 0 <= age_h <= APPROVAL_TTL_HOURS, f"{age_h:.1f}시간 경과")
    except Exception:
        rec("승인 유효기간", False, f"승인 시각 파싱 실패: {ap['approved_at']}")

    # 8/9. 중복·불명 차단
    recs = published_records()
    dup = [r for r in recs if r["sha256"] == ap["sha256"] and r["status"] == "published"]
    unk = [r for r in recs if r["sha256"] == ap["sha256"] and r["status"] == "unknown"]
    rec("중복 발행 없음", not dup, f"동일 해시 발행 기록 {len(dup)}건" if dup else "없음")
    rec("결과 불명 없음", not unk, "unknown 상태 존재 — 실게시 확인 필요" if unk else "없음")

    # 10. 제휴 정합성
    if ap["affiliate"]:
        first_line = body_text.split("\n")[0] if body_text else ""
        has_disc = DISCLOSURE_PHRASE in first_line
        no_token = "[LINK]" not in body_text and "[AFFILIATE]" not in body_text
        rec("제휴 고지", has_disc and no_token,
            f"첫줄고지={has_disc}, 미치환토큰없음={no_token}")
    else:
        rec("제휴 고지", True, "제휴글 아님 — 검사 생략")

    ok = all(c["pass"] for c in checks)
    print(json.dumps({"ok": ok, "checks": checks, "reasons": reasons}, ensure_ascii=False))

if __name__ == "__main__":
    main()
