"""Offline review of wrapper v2. All subprocess calls are mocked; no real CLI/API.

Run with Python from the repository or any directory. Observations include
intentional adverse inputs; reproducing a defect does not mean it is safe.
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_wrapper_v2", ROOT / "publish-post-verified-v2.py")
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
observations = []


def probe(name, mode="success", token="owner", mismatch=False, dry=False, missing_body=False):
    with tempfile.TemporaryDirectory(prefix="threads-offline-review-") as temp:
        base = Path(temp)
        pub = base / "queue" / "published"
        pub.mkdir(parents=True)
        body = base / "body.txt"
        payload = "오프라인 테스트 본문".encode("utf-8")
        body.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        marker = pub / "case.publishing.md"
        marker.write_text("owner=owner", encoding="utf-8")
        args = ["publish-post-verified", "0" * 64 if mismatch else digest,
                str(body), "mock-account", "--slug", "case", "--log", str(base / "run.log")]
        if token is not None:
            args.extend(["--token", token])
        if dry:
            args.append("--dry-run")
        if missing_body:
            body.unlink()
        calls = {"publish": 0, "release": 0}

        def fake_run(argv, **kwargs):
            if argv[0] == "MOCK_THREADS_ONLY":
                calls["publish"] += 1
                if mode == "timeout":
                    raise subprocess.TimeoutExpired(argv, 300, output=b"partial-out", stderr=b"partial-err")
                if mode == "long_timeout":
                    raise subprocess.TimeoutExpired(argv, 300, output=b"A" * 200 + b"request-id=tail", stderr=b"")
                if mode == "oserror":
                    raise FileNotFoundError("mock executable missing")
                if mode == "decode_error":
                    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "mock output decoding error")
                output = {"empty": "", "invalid_json": "not-json", "cli_fail": ""}.get(
                    mode, '{"post_id":"mock-id"}')
                return subprocess.CompletedProcess(argv, 3 if mode == "cli_fail" else 0,
                                                   stdout=output, stderr="mock failure" if mode == "cli_fail" else "")
            if argv[0] == sys.executable and Path(argv[1]).name == "release-publish":
                calls["release"] += 1
                rc = 0 if token == "owner" and mode != "release_failure" else 1
                if rc == 0:
                    marker.unlink()
                return subprocess.CompletedProcess(argv, rc, stdout="", stderr="")
            raise AssertionError("Unmocked command forbidden: " + repr(argv))

        wrapper.BASE = temp
        wrapper.CLI = "MOCK_THREADS_ONLY"
        out, err = io.StringIO(), io.StringIO()
        exit_code, exception = None, None
        with patch.object(sys, "argv", args), patch.object(wrapper.subprocess, "run", fake_run), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                wrapper.main()
            except SystemExit as exc:
                exit_code = exc.code
            except Exception as exc:
                exception = type(exc).__name__
        records = {p.name: p.read_text(encoding="utf-8") for p in pub.glob("*.md")
                   if not p.name.endswith(".publishing.md")}
        log = (base / "run.log").read_text(encoding="utf-8") if (base / "run.log").exists() else ""
        observations.append({"case": name, "exit_code": exit_code, "exception": exception,
                             "mock_calls": calls, "reservation_remains": marker.exists(),
                             "records": records, "log": log})


probe("success")
probe("cli_failure", "cli_fail")
probe("timeout", "timeout")
probe("not_started", "oserror")
probe("hash_mismatch", mismatch=True)
probe("dry_run", dry=True)
probe("missing_owner_token", token=None)
probe("wrong_owner_token", token="wrong-owner")
probe("empty_success_output", "empty")
probe("invalid_success_output", "invalid_json")
probe("release_failure", "release_failure")
probe("missing_body", missing_body=True)
probe("timeout_diagnostic_tail", "long_timeout")
probe("output_decode_failure", "decode_error")

by_name = {row["case"]: row for row in observations}
assert by_name["success"]["exit_code"] == 0 and not by_name["success"]["reservation_remains"]
assert by_name["cli_failure"]["exit_code"] == 3 and ".unknown.md" in " ".join(by_name["cli_failure"]["records"])
assert by_name["timeout"]["exit_code"] == 1 and "partial-out" in by_name["timeout"]["log"]
assert "partial-err" in by_name["timeout"]["log"] and not by_name["timeout"]["reservation_remains"]
assert by_name["not_started"]["mock_calls"]["release"] == 1 and not by_name["not_started"]["records"]
assert by_name["hash_mismatch"]["mock_calls"]["publish"] == 0
assert by_name["dry_run"]["mock_calls"]["publish"] == 0

# Defect reproduction assertions: these confirm the observed problem only.
assert by_name["missing_owner_token"]["mock_calls"]["publish"] == 1
assert by_name["wrong_owner_token"]["mock_calls"]["publish"] == 1
assert by_name["empty_success_output"]["exit_code"] == 0 and by_name["empty_success_output"]["records"]
assert by_name["invalid_success_output"]["exit_code"] == 0 and by_name["invalid_success_output"]["records"]
assert by_name["release_failure"]["exit_code"] == 0 and by_name["release_failure"]["reservation_remains"]
assert by_name["missing_body"]["exception"] == "FileNotFoundError" and by_name["missing_body"]["reservation_remains"]
assert "request-id=tail" not in by_name["timeout_diagnostic_tail"]["log"]
assert by_name["output_decode_failure"]["exception"] == "UnicodeDecodeError" and not by_name["output_decode_failure"]["records"]

result = {"source_commit": "9efe13e", "actual_publish_calls": 0, "actual_api_calls": 0,
          "submitted_linux_test_suite_rerun": False, "probes": observations}
target = ROOT / "review-tests" / "policy-20261007-probe-results.json"
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"observations": len(observations), "actual_publish_calls": 0,
                  "result_file": target.name}, ensure_ascii=False))
