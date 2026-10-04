#!/usr/bin/env python3
"""최종본 재검수 래퍼. GPT 호출 → parse-verdict로 판정. 운영 발행 경로와 테스트가 같은 파서를 쓴다.
사용법: final-audit <본문파일> [--evidence <근거파일>]
종료코드: 0 = 판정 통과, 1 = 그 외 전부 차단.
"""
import json, os, subprocess, sys

BASE = os.path.expanduser("~/workspace/threads")
GCHAT = os.path.expanduser("~/workspace/skills/openai/bin/gpt-chat")
AUD = os.path.join(BASE, "prompts", "auditor.md")
PARSER = os.path.join(BASE, "bin", "parse-verdict")

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"verdict": None, "pass": False, "reason": "본문 파일 미지정"}, ensure_ascii=False))
        sys.exit(1)
    body = open(sys.argv[1], encoding="utf-8").read()
    evidence = ""
    if "--evidence" in sys.argv:
        epath = sys.argv[sys.argv.index("--evidence") + 1]
        if os.path.isfile(epath):
            evidence = "\n\n[근거 데이터]\n" + open(epath, encoding="utf-8").read()
    user_text = body + evidence
    try:
        p = subprocess.run([GCHAT, "--system-file", AUD, "--user", user_text],
                           capture_output=True, text=True, timeout=180)
        resp = json.loads(p.stdout).get("text", "")
    except Exception as e:
        print(json.dumps({"verdict": None, "pass": False,
                          "reason": f"GPT 호출 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)
    q = subprocess.run([sys.executable, PARSER], input=resp,
                       capture_output=True, text=True)
    print(q.stdout.strip())
    sys.exit(q.returncode)

if __name__ == "__main__":
    main()
