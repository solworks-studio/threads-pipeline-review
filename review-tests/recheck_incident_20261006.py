"""Offline review of October 6 incident; no real publishing or API calls.

Probe partial timeout diagnostics, repeat-release semantics, and October 7
approval TTL/unknown behavior using the unchanged submitted implementations.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
results = {"reviewed_commit": "2b6520a4fac7e342aa001e93e32b901c4d3ad3f3",
           "real_api_calls": 0, "real_publish_calls": 0, "probes": []}

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def invoke(m, args):
    out, err, code, exception = io.StringIO(), io.StringIO(), 0, None
    with patch.object(sys, "argv", [m.__name__, *map(str, args)]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            m.main()
        except SystemExit as e:
            code = e.code
        except Exception as e:
            code, exception = None, type(e).__name__
    return {"exit_code": code, "stdout": out.getvalue().strip(),
            "stderr": err.getvalue().strip(), "exception": exception}

with tempfile.TemporaryDirectory(prefix="threads-incident-oct6-") as temp:
    base = Path(temp)
    reserve = load("reserve_oct6", "reserve-publish-v2.py")
    release = load("release_oct6", "release-publish-v2.py")
    guard = load("guard_oct6", "pre-publish-check-v2.py")
    publisher = load("publisher_oct6", "publish-post-verified.py")
    for m in (reserve, release, guard):
        m.BASE = temp
    guard.check_connectivity = lambda *a, **k: True
    pubdir = base / "queue" / "published"
    pubdir.mkdir(parents=True)
    body, log = base / "body.txt", base / "run.log"
    body.write_bytes(b"unchanged approved intro")
    digest = hashlib.sha256(body.read_bytes()).hexdigest()

    # Timeout includes useful partial output, but original wrapper does not save it.
    error = subprocess.TimeoutExpired("fake-cli", 300,
                                      output=b"phase=remote_request_started\n",
                                      stderr=b"partial_diagnostic_for_test\n")
    with patch.object(publisher.subprocess, "run", side_effect=error):
        outcome = invoke(publisher, [digest, body, "fake-account", "--log", log])
    text = log.read_text(encoding="utf-8")
    results["probes"].append({"name": "timeout loses partial diagnostics",
                              "observed": outcome,
                              "publish_begin_saved": "publish_begin" in text,
                              "publish_result_saved": "publish_result" in text,
                              "partial_output_saved": "remote_request_started" in text,
                              "partial_stderr_saved": "partial_diagnostic_for_test" in text})

    token = invoke(reserve, [digest, "test"])["stdout"]
    first = invoke(release, [digest, token])
    second = invoke(release, [digest, token])
    assert first["exit_code"] == 0 and second["exit_code"] == 1
    results["probes"].append({"name": "same reservation released twice",
                              "exit_codes": [first["exit_code"], second["exit_code"]]})

    approval = base / "20261007-intro-03.md"
    approval.write_text("승인자: test\n승인 시각: 2026-10-04 09:13 KST\n"
                        "scheduled_for: 2026-10-07\n대상 계정: @10min.diet.cook\n"
                        f"affiliate: false\nSHA-256: {digest}\n본문 파일: body.txt\n", encoding="utf-8")
    fixed = datetime(2026, 10, 7, 7, 0, tzinfo=KST)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    guard.datetime = FixedDateTime

    def check(name):
        r = invoke(guard, [approval])
        d = json.loads(r["stdout"])
        results["probes"].append({"name": name, "simulated_time": fixed.isoformat(),
                                  "exit_code": r["exit_code"], "ok": d["ok"],
                                  "reasons": d["reasons"],
                                  "approval_age": next(c["detail"] for c in d["checks"] if c["name"] == "승인 유효기간")})
        return r["exit_code"]

    assert check("October 7 at 07:00 without old unknown") == 0
    unresolved = pubdir / "20261006-intro-03.unknown.md"
    unresolved.write_text(f"SHA-256: {digest}\n상태: unknown\n", encoding="utf-8")
    assert check("October 7 at 07:00 with October 6 same-hash unknown") == 2
    unresolved.unlink()
    fixed = datetime(2026, 10, 7, 9, 14, tzinfo=KST)
    assert check("October 7 after original approval TTL") == 2

    json_before = json.loads((ROOT / "precheck-20261006.json").read_text(encoding="utf-8"))
    saved_age = next(c["detail"] for c in json_before["checks"] if c["name"] == "승인 유효기간")
    age_today = (datetime(2026, 10, 6, 6, 59, 36, tzinfo=KST) -
                 datetime(2026, 10, 4, 9, 13, tzinfo=KST)).total_seconds() / 3600
    results["probes"].append({"name": "submitted precheck freshness",
                              "saved_approval_age": saved_age,
                              "expected_age_at_today_run": f"{age_today:.1f}시간 경과"})

target = Path(__file__).with_name("incident-20261006-probe-results.json")
target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
