"""Offline independent wrapper v3 review; every subprocess call is mocked."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_wrapper_v3", ROOT / "publish-post-verified-v3.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
OWNER = "a" * 32
rows = []


def probe(name, mode="success", token=OWNER, slug="case", reservation=True,
          mismatch=False, dry=False, missing_body=False, bad_body=False):
    with tempfile.TemporaryDirectory(prefix="threads-wrapper3-offline-") as temp:
        base = Path(temp)
        pub = base / "queue" / "published"
        pub.mkdir(parents=True)
        body = base / "body.txt"
        payload = b"\xff" if bad_body else "오프라인 테스트 본문".encode("utf-8")
        body.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        marker = pub / "20261007-case.publishing.md"
        if reservation:
            marker.write_text(f"- SHA-256: {digest}\n- 상태: publishing\n- owner: {OWNER}\n", encoding="utf-8")
        log_path = base / "run.log"
        args = ["publish-post-verified", "0" * 64 if mismatch else digest,
                str(body), "mock-account", "--log", str(log_path)]
        if token is not None:
            args.extend(["--token", token])
        if slug is not None:
            args.extend(["--slug", slug])
        if dry:
            args.append("--dry-run")
        if missing_body:
            body.unlink()
        calls = {"publish": 0, "release": 0}

        def fake_run(argv, **kwargs):
            if argv[0] == "MOCK_THREADS_ONLY":
                calls["publish"] += 1
                if mode == "timeout":
                    raise subprocess.TimeoutExpired(argv, 300, output=b"A" * 500 + b"request-id=tail", stderr=b"partial-err")
                if mode == "oserror":
                    raise FileNotFoundError("mock executable missing")
                if mode == "decode_error":
                    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "mock CLI output decoding error")
                if mode == "unexpected":
                    raise RuntimeError("mock unexpected exception")
                output = {"empty": "", "invalid_json": "not-json", "cli_fail": "",
                          "cli_fail3": "", "bad_id": '{"post_id":{"error":"pending"}}'}.get(
                    mode, '{"post_id":"18186871165408948"}')
                rc = 3 if mode == "cli_fail3" else 7 if mode == "cli_fail" else 0
                return subprocess.CompletedProcess(argv, rc, stdout=output, stderr="mock error" if rc else "")
            if argv[0] == sys.executable and Path(argv[1]).name == "release-publish":
                calls["release"] += 1
                rc = 0 if argv[2] == digest and argv[3] == OWNER and marker.exists() and mode != "release_failure" else 1
                if rc == 0:
                    marker.unlink()
                return subprocess.CompletedProcess(argv, rc, stdout="", stderr="")
            raise AssertionError("Unmocked command forbidden: " + repr(argv))

        wrapper.BASE = temp
        wrapper.CLI = "MOCK_THREADS_ONLY"
        exit_code, exception = None, None
        with patch.object(sys, "argv", args), patch.object(wrapper.subprocess, "run", fake_run), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                wrapper.main()
            except SystemExit as exc:
                exit_code = exc.code
            except Exception as exc:
                exception = type(exc).__name__
        records = {p.name: p.read_text(encoding="utf-8") for p in pub.glob("*.md")
                   if not p.name.endswith(".publishing.md")}
        diagnostics = {p.name: p.read_text(encoding="utf-8") for p in (base / "logs").glob("diag-*.txt")}
        rows.append({"case": name, "exit_code": exit_code, "exception": exception,
                     "mock_calls": calls, "reservation_remains": marker.exists(),
                     "records": records, "log": log_path.read_text(encoding="utf-8") if log_path.exists() else "",
                     "diagnostics": diagnostics})


probe("success")
probe("cli_failure", "cli_fail")
probe("timeout", "timeout")
probe("not_started", "oserror")
probe("hash_mismatch", mismatch=True)
probe("dry_run", dry=True, token=None, slug=None)
probe("missing_owner_token", token=None)
probe("missing_slug", slug=None)
probe("wrong_owner_token", token="b" * 32)
probe("missing_reservation", reservation=False)
probe("empty_success_output", "empty")
probe("invalid_success_output", "invalid_json")
probe("release_failure", "release_failure")
probe("missing_body", missing_body=True)
probe("output_decode_failure", "decode_error")
probe("unexpected_cli_exception", "unexpected")
probe("cli_failure_code3", "cli_fail3")
probe("slug_mismatch", slug="different-slot")
probe("malformed_post_id", "bad_id")
probe("invalid_utf8_body", bad_body=True)

by = {row["case"]: row for row in rows}
checks = {
    "normal_success": by["success"]["exit_code"] == 0 and not by["success"]["reservation_remains"],
    "cli_failure_unknown": by["cli_failure"]["exit_code"] == 7 and "outcome=unknown" in by["cli_failure"]["log"],
    "timeout_unknown_and_full_diag": by["timeout"]["exit_code"] == 1 and "outcome=unknown" in by["timeout"]["log"]
        and "request-id=tail" in "".join(by["timeout"]["diagnostics"].values()) and not by["timeout"]["reservation_remains"],
    "not_started_cleanup": "outcome=not_started" in by["not_started"]["log"] and not by["not_started"]["reservation_remains"],
    "hash_mismatch_no_publish": by["hash_mismatch"]["mock_calls"]["publish"] == 0,
    "dry_run_no_publish": by["dry_run"]["mock_calls"]["publish"] == 0,
    "missing_token_blocked": by["missing_owner_token"]["exit_code"] == 2 and by["missing_owner_token"]["mock_calls"]["publish"] == 0,
    "missing_slug_blocked": by["missing_slug"]["exit_code"] == 2 and by["missing_slug"]["mock_calls"]["publish"] == 0,
    "wrong_token_blocked_preserved": by["wrong_owner_token"]["exit_code"] == 2 and by["wrong_owner_token"]["mock_calls"]["publish"] == 0
        and by["wrong_owner_token"]["reservation_remains"],
    "missing_reservation_blocked": by["missing_reservation"]["exit_code"] == 2 and by["missing_reservation"]["mock_calls"]["publish"] == 0,
    "empty_response_unknown": by["empty_success_output"]["exit_code"] == 1 and "reason=no_post_id" in by["empty_success_output"]["log"],
    "invalid_json_unknown": by["invalid_success_output"]["exit_code"] == 1 and "reason=no_post_id" in by["invalid_success_output"]["log"],
    "release_failure_reported": by["release_failure"]["exit_code"] == 3 and by["release_failure"]["reservation_remains"]
        and "release=failed" in by["release_failure"]["log"],
    "missing_body_cleanup": by["missing_body"]["mock_calls"]["publish"] == 0 and not by["missing_body"]["reservation_remains"]
        and "outcome=not_started" in by["missing_body"]["log"],
    "decode_error_unknown": by["output_decode_failure"]["exit_code"] == 1 and "outcome=unknown" in by["output_decode_failure"]["log"],
    "unexpected_exception_unknown": by["unexpected_cli_exception"]["exit_code"] == 1 and "outcome=unknown" in by["unexpected_cli_exception"]["log"],
}
assert all(checks.values()), checks
assert by["cli_failure_code3"]["exit_code"] == 3 and "outcome=unknown" in by["cli_failure_code3"]["log"]
assert by["slug_mismatch"]["mock_calls"]["publish"] == 1 and any("different-slot" in p for p in by["slug_mismatch"]["records"])
assert by["malformed_post_id"]["exit_code"] == 0 and by["malformed_post_id"]["records"]
assert by["invalid_utf8_body"]["exception"] == "UnicodeDecodeError" and by["invalid_utf8_body"]["reservation_remains"]

audit_spec = importlib.util.spec_from_file_location("review_final_audit", ROOT / "final-audit.py")
audit = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit)
audit.GCHAT = "MOCK_GPT_ONLY"
audit_inputs = []
with tempfile.TemporaryDirectory(prefix="threads-audit-input-offline-") as temp:
    body = Path(temp) / "body.txt"
    evidence = Path(temp) / "evidence.md"
    body.write_text("최종 게시 본문", encoding="utf-8")
    evidence.write_text("원본 요약 + 변경표 + 계산 근거", encoding="utf-8")
    def fake_audit_run(argv, **kwargs):
        if argv[0] == "MOCK_GPT_ONLY":
            supplied = argv[argv.index("--user") + 1]
            audit_inputs.append({"evidence_supplied": "원본 요약 + 변경표 + 계산 근거" in supplied})
            # No model verdict is being tested here: capture actual supplied text only.
            return subprocess.CompletedProcess(argv, 0, stdout='{"text":"mock"}', stderr="")
        if argv[0] == sys.executable and argv[1] == audit.PARSER:
            return subprocess.CompletedProcess(argv, 0, stdout='{"mock_parser":true}', stderr="")
        raise AssertionError("Unmocked audit command forbidden")
    for args in (["final-audit", str(body)], ["final-audit", str(body), "--evidence", str(evidence)]):
        with patch.object(sys, "argv", args), patch.object(audit.subprocess, "run", fake_audit_run), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                audit.main()
            except SystemExit:
                pass
assert audit_inputs == [{"evidence_supplied": False}, {"evidence_supplied": True}]

result = {"source_commit": "fa95a76", "actual_publish_calls": 0, "actual_api_calls": 0,
          "submitted_linux_tests_rerun": False, "confirmed_checks": checks, "observations": rows,
          "final_audit_input_checks": audit_inputs}
target = ROOT / "review-tests" / "wrapper-v3-20261007-probe-results.json"
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"observations": len(rows), "confirmed_checks": sum(checks.values()), "actual_publish_calls": 0,
                  "result_file": target.name}, ensure_ascii=False))
