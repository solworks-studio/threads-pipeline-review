#!/usr/bin/env python3
"""parse-verdict 단위 테스트."""
import importlib.util, subprocess, sys, tempfile, os
from importlib.machinery import SourceFileLoader

pv = SourceFileLoader("pv", os.path.expanduser("~/workspace/threads/bin/parse-verdict")).load_module()

CASES = [
    ("정상 통과", "판정: 통과\n지적:\n- 없음", True),
    ("수정필요 + '통과 가능' 설명", "판정: 수정필요\n지적:\n- 수정하면 통과 가능", False),
    ("반려", "판정: 반려\n지적:\n- 위험한 표현", False),
    ("빈 응답", "", False),
    ("판정 줄 없음", "지적:\n- 문제 있음", False),
    ("복수 판정", "판정: 통과\n판정: 반려", False),
    ("잘못된 값", "판정: maybe", False),
    ("형식 불일치", "판정은 통과입니다", False),
]

fails = 0
for name, text, expect_pass in CASES:
    r = pv.parse(text)
    ok = (r["pass"] is expect_pass)
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: pass={r['pass']} (기대 {expect_pass})")

# 종료코드 검증
p = subprocess.run([sys.executable, os.path.expanduser("~/workspace/threads/bin/parse-verdict")],
                   input="판정: 통과\n", capture_output=True, text=True)
ok = p.returncode == 0
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 종료코드 0 (통과)")
p = subprocess.run([sys.executable, os.path.expanduser("~/workspace/threads/bin/parse-verdict")],
                   input="판정: 수정필요\n", capture_output=True, text=True)
ok = p.returncode == 1
fails += not ok
print(f"[{'PASS' if ok else 'FAIL'}] 종료코드 1 (차단)")

print(f"\n{len(CASES)+2-fails}/{len(CASES)+2} 통과")
sys.exit(1 if fails else 0)
