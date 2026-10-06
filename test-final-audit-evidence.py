#!/usr/bin/env python3
"""final-audit v2 근거 연결 테스트 (Codex POLICY-RECHECK-V2 P1).
차단 경로는 GPT를 호출하지 않으므로 실제 API 호출 없이 검증한다.
- --require-evidence인데 근거 미지정 → exit 1, pass=false
- --evidence 파일 없음 → exit 1, pass=false
- --evidence 빈 파일 → exit 1, pass=false
- --approval 파일 없음 → exit 1, pass=false
"""
import json, os, subprocess, sys, tempfile

FA = os.path.expanduser("~/workspace/threads/bin/final-audit")
tmp = tempfile.mkdtemp(prefix="fa-test-")
body = os.path.join(tmp, "body.txt")
open(body, "w", encoding="utf-8").write("테스트 본문")
empty = os.path.join(tmp, "empty.md")
open(empty, "w").write("")

fails = 0
def check(name, cond):
    global fails
    fails += not cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")

def run(args):
    p = subprocess.run([sys.executable, FA, body] + args, capture_output=True, text=True)
    try:
        out = json.loads(p.stdout)
    except Exception:
        out = {}
    return p, out

p, out = run(["--require-evidence"])
check("근거 미지정 + require: exit 1 + pass=false", p.returncode == 1 and out.get("pass") is False)

p, out = run(["--evidence", os.path.join(tmp, "nope.md"), "--require-evidence"])
check("근거 파일 없음: exit 1 + pass=false", p.returncode == 1 and out.get("pass") is False)

p, out = run(["--evidence", empty, "--require-evidence"])
check("근거 빈 파일: exit 1 + pass=false", p.returncode == 1 and out.get("pass") is False)

p, out = run(["--approval", os.path.join(tmp, "nope.md")])
check("승인 기록 없음: exit 1 + pass=false", p.returncode == 1 and out.get("pass") is False)

print(f"\n{fails}건 실패")
sys.exit(1 if fails else 0)
