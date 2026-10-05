"""Offline probes for fbd149e. No real Threads/GPT calls.

For reproducibility, pause B after its records snapshot, not merely before
entering reserve. Only timing, account I/O, and publisher I/O are adapted.
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

os.environ["PYTHONUTF8"] = "1"
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
results = {"reviewed_commit": "fbd149e2f0d896782ea0719e0416705b1bcdf625",
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

def add(name, observed, expected):
    results["probes"].append({"name": name, "observed": observed,
                              "expected_safe_behavior": expected})

with tempfile.TemporaryDirectory(prefix="threads-lock-review-") as temp:
    base = Path(temp)
    a = load("reserve_A", "reserve-publish-v2.py")
    b = load("reserve_B", "reserve-publish-v2.py")
    release = load("release_v2", "release-publish-v2.py")
    publisher = load("publisher_verified", "publish-post-verified.py")
    for m in (a, b, release):
        m.BASE = temp
    pubdir = base / "queue" / "published"
    pubdir.mkdir(parents=True)
    digest = hashlib.sha256(b"approved race payload").hexdigest()
    calls = []

    def fake_publish(payload):
        calls.append(payload)
        return f"fake-{len(calls)}"

    # Passing control: B reads records only after A completes.
    ar = invoke(a, [digest, "same"])
    token = ar["stdout"]
    bad = invoke(release, [digest, "0" * 32])
    add("wrong owner cannot release", {"exit_code": bad["exit_code"],
                                       "reservations": len(list(pubdir.glob("*.publishing.md")))},
        {"exit_code": 1, "reservations": 1})
    record = pubdir / "complete.md"
    record.write_text(f"SHA-256: {digest}\n상태: published\npost_id: fake\n", encoding="utf-8")
    invoke(release, [digest, token])
    add("B reads after A completed", invoke(b, [digest, "same"])["exit_code"], 3)
    record.unlink()

    # B reads an empty state and pauses. A then publishes and releases.
    original_b_records = b.records
    def pause_after_snapshot():
        snapshot = original_b_records()
        ar = invoke(a, [digest, "same"])
        assert ar["exit_code"] == 0
        post_id = fake_publish(b"approved race payload")
        record.write_text(f"SHA-256: {digest}\n상태: published\npost_id: {post_id}\n", encoding="utf-8")
        assert invoke(release, [digest, ar["stdout"]])["exit_code"] == 0
        return snapshot
    with patch.object(b, "records", side_effect=pause_after_snapshot):
        br = invoke(b, [digest, "same"])
    if br["exit_code"] == 0:
        fake_publish(b"approved race payload")
    add("B snapshot before A publishes, B creates after A releases",
        {"B_reservation_exit": br["exit_code"], "fake_publish_calls": len(calls)},
        {"B_reservation_denied": True, "fake_publish_calls": 1})
    if br["exit_code"] == 0:
        invoke(release, [digest, br["stdout"]])
    record.unlink()

    # Both same-hash workers use different slugs and read before either locks.
    def pause_while_a_active():
        snapshot = original_b_records()
        ar = invoke(a, [digest, "slug-A"])
        assert ar["exit_code"] == 0
        return snapshot
    with patch.object(b, "records", side_effect=pause_while_a_active):
        br = invoke(b, [digest, "slug-B"])
    add("same hash different slugs with simultaneous snapshots",
        {"B_reservation_exit": br["exit_code"],
         "active_reservations": len(list(pubdir.glob("*.publishing.md")))},
        {"B_reservation_denied": True, "active_reservations": 1})

    # Exercise the REAL verified publisher main with a CLI spy, not a mirror.
    body, log = base / "body.txt", base / "publisher.log"
    approved = "approved original body"
    body.write_bytes(approved.encode("utf-8"))
    expected = hashlib.sha256(body.read_bytes()).hexdigest()
    cli_calls = []
    def cli_spy(args, **kwargs):
        cli_calls.append(args)
        body.write_bytes(b"changed after publisher read")
        return subprocess.CompletedProcess(args, 0, '{"id":"fake-post"}', "")
    with patch.object(publisher.subprocess, "run", side_effect=cli_spy):
        good = invoke(publisher, [expected, body, "fake-account", "--log", log])
    add("real publisher uses captured verified bytes", {"exit_code": good["exit_code"],
                                                         "cli_calls": len(cli_calls),
                                                         "text_matches_approval": cli_calls[0][-1] == approved},
        {"exit_code": 0, "cli_calls": 1, "text_matches_approval": True})
    with patch.object(publisher.subprocess, "run", side_effect=cli_spy):
        bad = invoke(publisher, [expected, body, "fake-account", "--log", log])
    add("mutation before publisher read blocked", {"exit_code": bad["exit_code"],
                                                    "additional_cli_calls": len(cli_calls) - 1},
        {"exit_code": 2, "additional_cli_calls": 0})
    body.write_bytes(approved.encode("utf-8"))
    log.write_text("", encoding="utf-8")
    with patch.object(publisher.subprocess, "run", side_effect=subprocess.TimeoutExpired("fake-cli", 300)):
        timed = invoke(publisher, [expected, body, "fake-account", "--log", log])
    log_text = log.read_text(encoding="utf-8")
    add("CLI timeout log", {"exception": timed["exception"],
                            "publish_begin": "publish_begin" in log_text,
                            "publish_result": "publish_result" in log_text},
        {"controlled_failure": True, "publish_begin": True, "publish_result": True})

    # Replay submitted changed tests. Adapt only path and account connectivity.
    bindir = base / "bin"
    bindir.mkdir()
    mapping = {"reserve-publish": "reserve-publish-v2.py", "release-publish": "release-publish-v2.py",
               "publish-post-verified": "publish-post-verified.py", "parse-verdict": "parse-verdict.py",
               "pre-publish-check": "pre-publish-check-v2.py"}
    for name, src in mapping.items():
        code = (ROOT / src).read_text(encoding="utf-8")
        if name == "pre-publish-check":
            code = code.replace('if __name__ == "__main__":',
                                'check_connectivity = lambda *a, **k: True\nif __name__ == "__main__":')
        (bindir / name).write_text(code, encoding="utf-8")
    results["muse_test_replays"] = []
    for test in ("test-lock-ownership.py", "test-publish-path-v2.py"):
        code = (ROOT / test).read_text(encoding="utf-8")
        code = code.replace('os.path.expanduser("~/workspace/threads/bin")', repr(str(bindir)))
        staged = base / test
        staged.write_text(code, encoding="utf-8")
        p = subprocess.run([sys.executable, str(staged)], capture_output=True, text=True,
                           encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60)
        results["muse_test_replays"].append({"test": test, "exit_code": p.returncode,
                                              "stdout": p.stdout, "stderr": p.stderr})

target = Path(__file__).with_name("lock-v2-probe-results.json")
target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
