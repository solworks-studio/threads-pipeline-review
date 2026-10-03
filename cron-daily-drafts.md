# 일일 크론: threads-daily-drafts (스케줄러 설정)

- 스케줄: 매일 07:00, Asia/Seoul
- 실행 종류: agent (초안 생성·검수·승인 요청)
- **발행 권한 없음.** publish-post는 절대 실행하지 않는다.

## 지시문 전문

쓰레드 자동화 파이프라인의 일일 초안 생성 작업이다. 전체 설계는 ~/workspace/threads/PIPELINE.md v2를 따르라. 시간대는 Asia/Seoul.

**이 크론에는 발행 권한이 없다.** 초안 생성·검수·승인 요청까지만 수행하고, threads-cli publish-post는 절대 실행하지 마라.

1. ~/workspace/threads/prompts/writer.md를 읽고, 다이어트·10분 레시피 niche로 쓰레드 초안 2개를 작성하라. frontmatter(affiliate/product)를 포함하고, 어제(queue/drafts, queue/review) 소재와 겹치지 않게 하라. 오늘 날짜(YYYYMMDD) 기준 `~/workspace/threads/queue/drafts/YYYYMMDD-01.md`, `YYYYMMDD-02.md`에 저장하라. 같은 날짜 파일이 이미 있으면 중복 실행으로 보고 중단하라.

2. 레시피형 초안은 `~/workspace/threads/evidence/TEMPLATE.md` 형식으로 근거 파일을 `~/workspace/threads/queue/evidence/YYYYMMDD-NN.md`에 작성하라. 근거 없는 수치는 본문에서 빼라.

3. frontmatter `affiliate: true`인 초안은 검수 전에 제휴링크와 고지 문구를 삽입하라. 고지는 본문 첫 줄 ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."), 링크는 `[LINK]` 자리에 치환하라. 유효한 링크가 없거나 미치환 토큰이 남으면 해당 초안은 `failed`로 기록하고 제외하라.

4. 각 초안+근거를 GPT 검수자에게 보내라:
   `~/workspace/skills/openai/bin/gpt-chat --system-file ~/workspace/threads/prompts/auditor.md --user-file <draft>`
   (근거 파일 내용을 --user 입력에 함께 포함하라.)
   결과를 `~/workspace/threads/queue/review/YYYYMMDD-NN.md`에 저장하라 (원본 초안 + GPT 판정 전문).
   - 판정이 `수정필요`면 초안을 1회 수정하고 재검수하라 (최대 1회).
   - 판정이 `반려`면 해당 초안을 폐기하고 새 초안 1개를 작성해 검수하라 (최대 1회).
   - 검수 실패·시간초과·이상 응답은 통과로 처리하지 마라. `failed`로 기록하고 최종 보고에 명시하라.
   - API가 429/insufficient_quota로 실패하면 검수를 생략하고, 최종 보고에 "OpenAI 크레딧 부족 — platform.openai.com Billing에서 충전 필요"라고 명시하라.

5. ~/workspace/threads/prompts/tone.md로 톤 검수를 직접 수행하라.

6. 실행 로그를 ~/workspace/threads/logs/YYYYMMDD.md에 한 줄씩 기록하라 (상태: draft/reviewed/failed).

7. 최종 메시지로 사용자에게 보고하라: 최종본 2개 전문 + 근거 요약 + 각각의 GPT 판정 요약 + "발행 승인 요청". 승인이 떨어지기 전에는 절대 발행하지 마라.

보고는 한국어로, 간결하게. 초안 전문은 반드시 포함하라.
