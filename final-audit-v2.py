#!/usr/bin/env python3
"""최종본 재검수 래퍼 v2. GPT 호출 → parse-verdict로 판정. 운영 발행 경로와 테스트가 같은 파서를 쓴다.
사용법: final-audit <본문파일> [--evidence <근거파일>] [--approval <승인기록파일>] [--require-evidence]
종료코드: 0 = 판정 통과, 1 = 그 외 전부 차단.

근거 연결 규칙 (2026-10-07, Codex POLICY-RECHECK-V2 P1 반영):
- --evidence/--approval을 명시했는데 파일이 없거나 비어 있으면 GPT를 호출하지 않고 차단한다.
- --require-evidence인데 --evidence가 없으면 차단한다 (아침 재검수용 — 근거 없는 검수 금지).
- 승인 기록을 주면 판정·예정 발행일시까지 검수 입력에 포함된다.
"""
import json, os, subprocess, sys

BASE = os.path.expanduser("~/workspace/threads")
GCHAT = os.path.expanduser("~/workspace/skills/openai/bin/gpt-chat")
AUD = os.path.join(BASE, "prompts", "auditor.md")
PARSER = os.path.join(BASE, "bin", "parse-verdict")

def fail(reason):
    print(json.dumps({"verdict": None, "pass": False, "reason": reason}, ensure_ascii=False))
    sys.exit(1)

def read_required(path, label):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        fail(f"{label} 파일이 없거나 비어 있음 — 검수 차단: {path}")
    return open(path, encoding="utf-8").read()

def opt(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None

def main():
    if len(sys.argv) < 2:
        fail("본문 파일 미지정")
    body = open(sys.argv[1], encoding="utf-8").read()
    evidence_path = opt("--evidence")
    approval_path = opt("--approval")
    if "--require-evidence" in sys.argv and not evidence_path:
        fail("--require-evidence인데 근거가 지정되지 않음 — 검수 차단")
    user_text = body
    if evidence_path:
        user_text += "\n\n[근거 데이터]\n" + read_required(evidence_path, "근거")
    if approval_path:
        user_text += "\n\n[승인 기록]\n" + read_required(approval_path, "승인 기록")
    try:
        p = subprocess.run([GCHAT, "--system-file", AUD, "--user", user_text],
                           capture_output=True, text=True, timeout=180)
        resp = json.loads(p.stdout).get("text", "")
    except Exception as e:
        fail(f"GPT 호출 실패: {e}")
    q = subprocess.run([sys.executable, PARSER], input=resp,
                       capture_output=True, text=True)
    print(q.stdout.strip())
    sys.exit(q.returncode)

if __name__ == "__main__":
    main()
