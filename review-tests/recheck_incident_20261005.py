"""Offline reproduction: rescheduling does not clear a same-hash unknown.

Original guard is imported unchanged. Clock and account connectivity are mocked;
all fixtures are temporary. No API requests, paid calls, or publishing.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("incident_guard", ROOT / "pre-publish-check-v2.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
KST = timezone(timedelta(hours=9))
fixed = datetime(2026, 10, 6, 7, 0, tzinfo=KST)

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

guard.datetime = FixedDateTime
guard.check_connectivity = lambda *a, **k: True
results = {"reviewed_commit": "a15334f978633fecf70081717fbb131a64ab4357",
           "simulated_time": fixed.isoformat(), "real_api_calls": 0,
           "real_publish_calls": 0, "cases": []}

with tempfile.TemporaryDirectory(prefix="threads-incident-review-") as temp:
    base = Path(temp)
    guard.BASE = str(base)
    published = base / "queue" / "published"
    published.mkdir(parents=True)
    body = base / "body.txt"
    body.write_bytes(b"unchanged approved intro")
    digest = hashlib.sha256(body.read_bytes()).hexdigest()
    approval = base / "20261006-intro-03.md"
    approval.write_text("승인자: test\n승인 시각: 2026-10-04 09:13 KST\n"
                        "scheduled_for: 2026-10-06\n대상 계정: @10min.diet.cook\n"
                        f"affiliate: false\nSHA-256: {digest}\n본문 파일: body.txt\n", encoding="utf-8")
    old_unknown = published / "20261005-intro-03.unknown.md"

    def run(name):
        out, code = io.StringIO(), 0
        with patch.object(sys, "argv", ["pre-publish-check", str(approval)]), contextlib.redirect_stdout(out):
            try:
                guard.main()
            except SystemExit as e:
                code = e.code
        d = json.loads(out.getvalue())
        chosen = [c for c in d["checks"] if c["name"] in
                  ("발행일 일치", "승인 유효기간", "결과 불명 없음")]
        results["cases"].append({"name": name, "exit_code": code, "ok": d["ok"],
                                  "selected_checks": chosen, "reasons": d["reasons"]})
        return code

    assert run("next-day approval without previous unknown") == 0
    old_unknown.write_text(f"SHA-256: {digest}\n상태: unknown\n시각: 2026-10-05 14:45 KST\n", encoding="utf-8")
    assert run("next-day approval with previous-day same-hash unknown") == 2
    with old_unknown.open("a", encoding="utf-8") as f:
        f.write("resolved: true\n해소 사유: 테스트용 사용자 미게시 확인\n")
    assert run("only appending resolution metadata does not change guard state") == 2
    old_unknown.write_text(f"SHA-256: {digest}\n상태: failed\n해소 사유: 테스트용 미게시 확인 및 재예약\n", encoding="utf-8")
    assert run("control: explicit status transition after documented resolution") == 0

target = Path(__file__).with_name("incident-20261005-probe-results.json")
target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
