"""Independent offline probes; no Threads or GPT calls and no real queue writes."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
TARGET = ROOT.parent / 'pre-publish-check.py'
spec = importlib.util.spec_from_file_location('guard', TARGET)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

results = []
with tempfile.TemporaryDirectory(prefix='isolated-guard-', dir=ROOT) as temp:
    base = Path(temp)
    guard.BASE = str(base)
    guard.check_connectivity = lambda *args, **kwargs: True
    published = base / 'queue' / 'published'
    published.mkdir(parents=True)
    now = guard.datetime.now(guard.KST)
    today = now.strftime('%Y-%m-%d')
    stamp = now.strftime('%Y-%m-%d %H:%M')
    body = base / 'body.txt'
    approval = base / 'approval.md'

    def write_approval(text='정상 테스트 본문', affiliate=False, approved_by=True):
        body.write_bytes(text.encode('utf-8'))
        digest = hashlib.sha256(body.read_bytes()).hexdigest()
        fields = [f'scheduled_for: {today}', f'SHA-256: {digest}',
                  f'본문 파일: {body.name}', '대상 계정: @10min.diet.cook',
                  f'승인 시각: {stamp}', f'affiliate: {str(affiliate).lower()}']
        if approved_by:
            fields.append('승인자: 테스트 사용자')
        approval.write_text('\n'.join(fields), encoding='utf-8')
        return digest

    def probe(name, approval_path=approval):
        original_argv = sys.argv
        sys.argv = ['pre-publish-check', str(approval_path), '--date', today]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                guard.main()
        finally:
            sys.argv = original_argv
        data = json.loads(out.getvalue())
        results.append({'case': name, 'ok': data['ok'], 'reasons': data.get('reasons', [])})
        return data

    write_approval()
    probe('baseline valid fixture')
    probe('missing approval', base / 'missing.md')
    body.write_text('변경된 본문', encoding='utf-8')
    probe('tampered body')

    digest = write_approval()
    record = published / 'record.md'
    for state in ['published', 'unknown', 'publishing']:
        record.write_text(f'SHA-256: {digest}\n상태: {state}', encoding='utf-8')
        probe(f'existing {state} record')
    record.unlink()

    write_approval('이 게시물은 쿠팡 파트너스 활동의 일환으로 수수료를 제공받습니다.\n추천 상품입니다.', affiliate=True)
    probe('affiliate true but NO URL')
    write_approval(approved_by=False)
    probe('missing approver')
    write_approval()
    probe('same approval attempt one')
    probe('same approval attempt two without any reservation')

# Probe the command-line failure contract; missing approval returns before any API call.
command = subprocess.run([sys.executable, str(TARGET), str(ROOT / 'missing-review-approval.md')], capture_output=True)
results.append({'case': 'missing approval process exit status', 'returncode': command.returncode,
                'json_ok': json.loads(command.stdout)['ok']})

# Reproduce the exact result-classification expression from the submitted runner.
for response in ['판정: 수정필요\n지적: 수정하면 통과 가능', '판정: 반려\n지적: 위험한 표현입니다.\n수정안: 고친 뒤 통과 가능']:
    accepted = '통과' in response and '반려' not in response.split('통과')[0][-50:]
    results.append({'case': 'submitted GPT normal-case parser', 'response': response, 'classified_as_pass': accepted})

artifact = {'tested_commit': '7a79858860f9358e3074dff143b48dbd4c559a58',
            'threads_calls': 0, 'gpt_calls': 0,
            'method': 'Original guard module; isolated temporary BASE; account connectivity mocked true; timestamps use current KST. Does not execute actual publishing path.',
            'results': results}
(ROOT / 'independent-probe-results.json').write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(artifact, ensure_ascii=False, indent=2))
