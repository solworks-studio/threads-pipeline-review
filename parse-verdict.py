#!/usr/bin/env python3
"""GPT 검수 응답의 판정을 엄격히 파싱한다.
사용법: parse-verdict [응답파일]   (없으면 stdin)
규칙:
  - `판정: 통과|수정필요|반려` 형식의 줄이 정확히 1개 있어야 한다.
  - 설명문에 '통과 가능' 같은 단어가 있어도 판정 줄이 아니면 무시한다.
  - 통과가 아니면 전부 차단. 빈 응답·판정 없음·복수 판정·형식 불일치도 차단.
출력: JSON {"verdict": ..., "pass": bool, "reason": ...}
종료코드: 0 = 통과, 1 = 차단.
"""
import json, re, sys

PAT = re.compile(r"^판정:\s*(통과|수정필요|반려)\s*$", re.M)

def parse(text):
    if not text or not text.strip():
        return {"verdict": None, "pass": False, "reason": "빈 응답"}
    hits = PAT.findall(text)
    if len(hits) == 0:
        return {"verdict": None, "pass": False, "reason": "판정 줄 없음"}
    if len(hits) > 1:
        return {"verdict": None, "pass": False, "reason": f"복수 판정 ({len(hits)}개)"}
    v = hits[0]
    if v == "통과":
        return {"verdict": v, "pass": True, "reason": ""}
    return {"verdict": v, "pass": False, "reason": f"판정={v}"}

def main():
    if len(sys.argv) > 1:
        text = open(sys.argv[1], encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    r = parse(text)
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r["pass"] else 1)

if __name__ == "__main__":
    main()
