"""Offline review probes for 9a6fdbc; no Threads/GPT API or real publishing.

Run with Python 3. All operational files are isolated in TemporaryDirectory.
Only account connectivity and GPT/publisher effects are mocked.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ["PYTHONUTF8"] = "1"

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).with_name("v5-probe-results.json")
KST = timezone(timedelta(hours=9))
results = {"reviewed_commit": "9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1",
           "real_publish_calls": 0, "real_gpt_calls": 0, "probes": []}

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

guard = load("guard_v5", "pre-publish-check-v2.py")
reserve = load("reserve_v5", "reserve-publish.py")
release = load("release_v5", "release-publish.py")
parser = load("parser_v5", "parse-verdict.py")
audit = load("audit_v5", "final-audit.py")

def invoke(module, args):
    stdout, stderr, code = io.StringIO(), io.StringIO(), 0
    with patch.object(sys, "argv", [module.__name__, *map(str, args)]), \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            module.main()
        except SystemExit as e:
            code = e.code
    return {"exit_code": code, "stdout": stdout.getvalue().strip(),
            "stderr": stderr.getvalue().strip()}

def record(name, observed, expected):
    results["probes"].append({"name": name, "observed": observed,
                              "expected_safe_behavior": expected})

with tempfile.TemporaryDirectory(prefix="threads-review-v5-") as temp:
    base = Path(temp)
    pub = base / "queue" / "published"
    pub.mkdir(parents=True)
    for m in (guard, reserve, release):
        m.BASE = temp
    guard.check_connectivity = lambda *a, **k: True
    now = datetime.now(KST)
    date, stamp = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M")
    approval, body = base / "approval.md", base / "body.txt"

    def fixture(text="normal body", affiliate="false", age=0):
        body.write_bytes(text.encode("utf-8"))
        digest = hashlib.sha256(body.read_bytes()).hexdigest()
        at = (now - timedelta(hours=age)).strftime("%Y-%m-%d %H:%M")
        approval.write_text(f"승인자: test\n승인 시각: {at} KST\n"
                            f"scheduled_for: {date}\n대상 계정: @10min.diet.cook\n"
                            f"affiliate: {affiliate}\nSHA-256: {digest}\n"
                            "본문 파일: body.txt\n", encoding="utf-8")
        return digest

    def check():
        r = invoke(guard, [approval, "--date", date])
        return {"exit_code": r["exit_code"], **json.loads(r["stdout"])}

    digest = fixture()
    record("normal approval", check()["exit_code"], 0)
    record("missing approval", invoke(guard, [base / "missing.md"])["exit_code"], 2)
    body.write_bytes(b"tampered")
    record("body tamper", check()["exit_code"], 2)
    fixture(age=73)
    record("expired approval", check()["exit_code"], 2)
    digest = fixture()
    for status in ("published", "unknown", "publishing"):
        p = pub / "control.md"
        p.write_text(f"SHA-256: {digest}\n상태: {status}\n시각: {stamp}\n", encoding="utf-8")
        record(f"existing {status}", check()["exit_code"], 2)
        p.unlink()
    disclosure = "이 포스팅은 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받습니다."
    fixture(disclosure + "\n상품 추천", "true")
    record("affiliate URL absent", check()["exit_code"], 2)
    fixture(disclosure + "\nhttps://example.com/coupang", "true")
    record("non-Coupang URL", check()["exit_code"], 2)
    fixture(disclosure + "\nhttps://link.coupang.com/a/test", "true")
    record("affiliate URL control", check()["exit_code"], 0)

    record("old verdict false-positive", parser.parse("판정: 수정필요\n지적: 수정하면 통과 가능")["pass"], False)
    record("two valid verdicts", parser.parse("판정: 통과\n판정: 반려")["pass"], False)
    record("valid plus malformed verdict", parser.parse("판정: 통과\n판정: maybe")["pass"], False)
    record("verdict not first line", parser.parse("임의 설명\n판정: 통과")["pass"], False)

    # Deterministic two-worker interleaving on ONE machine, ONE slug.
    # Both workers pass precheck; B pauses before reservation. A finishes.
    digest = fixture("race body")
    a_check, b_check = check(), check()
    fake_publisher_calls = []
    def fake_publish(payload):
        fake_publisher_calls.append(payload)
        return f"fake{len(fake_publisher_calls)}"
    a_reserve = invoke(reserve, [digest, "same-slug"])
    if a_reserve["exit_code"] == 0 and a_check["ok"] and parser.parse("판정: 통과")["pass"]:
        fake_publish(body.read_bytes())
    completed = pub / "completed.md"
    completed.write_text(f"SHA-256: {digest}\n상태: published\n시각: {stamp}\npost_id: fake1\n", encoding="utf-8")
    invoke(release, [digest])
    b_reserve = invoke(reserve, [digest, "same-slug"])
    if b_reserve["exit_code"] == 0 and b_check["ok"] and parser.parse("판정: 통과")["pass"]:
        fake_publish(body.read_bytes())
    record("delayed second worker after first release",
           {"prechecks": [a_check["exit_code"], b_check["exit_code"]],
            "reservations": [a_reserve["exit_code"], b_reserve["exit_code"]],
            "fake_publish_calls": len(fake_publisher_calls)}, {"fake_publish_calls": 1})
    invoke(release, [digest])
    completed.unlink()

    # A owns a reservation; a losing/non-owning caller can delete it.
    invoke(reserve, [digest, "owner-A"])
    loser = invoke(reserve, [digest, "owner-B"])
    nonowner_release = invoke(release, [digest])
    record("non-owner releases active reservation",
           {"loser_exit": loser["exit_code"], "release_stdout": nonowner_release["stdout"],
            "remaining_reservations": len(list(pub.glob("*.publishing.md")))},
           {"remaining_reservations": 1})

    # The checked bytes are not retained for the later audit/publish steps.
    digest = fixture("approved immutable payload")
    accepted = check()
    invoke(reserve, [digest, "mutation"])
    body.write_bytes(b"changed after the precheck")
    record("body changes between precheck and later file read",
           {"precheck_exit": accepted["exit_code"],
            "later_payload_matches_approval": hashlib.sha256(body.read_bytes()).hexdigest() == digest},
           {"later_payload_matches_approval": True})
    invoke(release, [digest])

    # GPT command fails but emits a plausible JSON response on stdout.
    real_run = subprocess.run
    def fake_run(args, **kwargs):
        if args[0] == audit.GCHAT:
            return subprocess.CompletedProcess(args, 1, json.dumps({"text": "판정: 통과"}), "simulated failure")
        kwargs["encoding"] = "utf-8"
        return real_run([sys.executable, str(ROOT / "parse-verdict.py")], **kwargs)
    with patch.object(audit.subprocess, "run", side_effect=fake_run):
        observed = invoke(audit, [body])
    record("failed GPT process with parseable stdout", observed, {"exit_code": 1, "pass": False})

    # Replay Muse's B/C/D test scripts with only path and account I/O adapters.
    staged_bin = base / "bin"
    staged_bin.mkdir()
    names = {"parse-verdict": "parse-verdict.py", "pre-publish-check": "pre-publish-check-v2.py",
             "reserve-publish": "reserve-publish.py", "release-publish": "release-publish.py"}
    for name, src in names.items():
        code = (ROOT / src).read_text(encoding="utf-8")
        if name == "pre-publish-check":
            code = code.replace('if __name__ == "__main__":',
                                'check_connectivity = lambda *a, **k: True\nif __name__ == "__main__":')
        (staged_bin / name).write_text(code, encoding="utf-8")
    results["muse_test_replays"] = []
    for test in ("test-verdict-parser.py", "test-guard.py", "test-publish-path.py"):
        code = (ROOT / test).read_text(encoding="utf-8")
        code = code.replace('os.path.expanduser("~/workspace/threads/bin")', repr(str(staged_bin)))
        for name in names:
            code = code.replace(f'os.path.expanduser("~/workspace/threads/bin/{name}")', repr(str(staged_bin / name)))
        staged = base / test
        staged.write_text(code, encoding="utf-8")
        p = real_run([sys.executable, str(staged)], capture_output=True, text=True, encoding="utf-8",
                     env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
        results["muse_test_replays"].append({"test": test, "exit_code": p.returncode,
                                              "stdout": p.stdout, "stderr": p.stderr})

OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
