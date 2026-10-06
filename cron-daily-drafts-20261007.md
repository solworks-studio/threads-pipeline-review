---
id: threads-daily-drafts
title: 쓰레드 다이어트·레시피 일일 초안 생성+검수
enabled: true
owner: goal:threads-automation-pipeline-diet-10-minute-recipes
mode: task
schedule:
  kind: daily
  timezone: Asia/Seoul
  time: 19:00:00
delivery:
  - chat_id: 2d04738b-be29-43ca-9d27-b3ef7f349e22
metadata:
  originating_chat_context_json: '{"chat_id":"2d04738b-be29-43ca-9d27-b3ef7f349e22","origin_provider":"main","chat_kind":"direct","event_kind":"message","require_mention":false,"device_id":"3f643d2e-980d-4101-9024-bf35ff47b900"}'
  presentation_locale: ko-KR
---
쓰레드 자동화 파이프라인의 일일 초안 생성 작업이다. 전체 설계는 ~/workspace/threads/PIPELINE.md v2를 따르라. 시간대는 Asia/Seoul.

**이 크론에는 발행 권한이 없다.** 초안 생성·검수·승인 요청까지만 수행하고, threads-cli publish-post는 절대 실행하지 마라.

**레시피 출처 원칙 (2026-10-07 신설, 필수):** 레시피는 반드시 실제로 존재하는 레시피를 참고해서만 작성하라. AI가 재료 구성·조리법을 창작하는 것은 금지다. 초안 작성 전에 웹 검색으로 실제 레시피를 1개 이상 확보하라. 저작권 배려로 원본을 그대로 복사하지 말고, 맛에 큰 영향을 주지 않는 범위(양념 분량 미세 조정, 부재료 교체·생략·추가, 표현 변경, 분량 환산)에서만 변형하라. 주재료 교체·핵심 조리법 변경·없는 단계 추가는 금지다. 근거 파일에 원본 출처(매체·제목, URL, 확인일, 적용한 변형 내용)를 반드시 기록하라. 출처가 없으면 초안을 제출하지 마라.

1. ~/workspace/threads/prompts/writer.md를 읽고, 다이어트·10분 레시피 niche로 쓰레드 초안 2개를 작성하라. 레시피형은 위 출처 원칙에 따라 실제 레시피를 먼저 확보한 뒤 작성하라. frontmatter(affiliate/product)를 포함하고, 어제(queue/drafts, queue/review) 소재와 겹치지 않게 하라. 오늘 날짜(YYYYMMDD) 기준 `~/workspace/threads/queue/drafts/YYYYMMDD-01.md`, `YYYYMMDD-02.md`에 저장하라. 같은 날짜 파일이 이미 있으면 중복 실행으로 보고 중단하라.

2. 레시피형 초안은 `~/workspace/threads/evidence/TEMPLATE.md` 형식으로 근거 파일을 `~/workspace/threads/queue/evidence/YYYYMMDD-NN.md`에 작성하라. 근거에는 원본 레시피 출처(매체·제목, URL, 확인일, 적용한 변형 내용)를 반드시 포함하라. 각 재료는 `~/workspace/threads/bin/mfds-lookup "식품명"` 으로 식약처 DB를 실제 조회하고, 원재료 항목(가공·조리품 제외 우선)의 kcal·단백질·지방·탄수화물을 기록하라. 식약처 DB에 적합한 원재료 항목이 없으면 `~/workspace/threads/bin/usda-lookup "영문 식품명"` 으로 USDA FoodData Central에서 교차검증하라 (Energy 단위가 KJ면 kcal로 환산: ÷4.184, 한국 식품과 가장 유사한 항목 선택). 두 곳 모두 적합한 항목이 없을 때만 해당 수치는 "AI 계산 (외부 교차검증 미실시)"로 표기하라. 근거 없는 수치는 본문에서 빼라. 출처는 실제 조회한 경우만 기재하라 (허위 기재는 검수 반려).

3. frontmatter `affiliate: true`인 초안은 검수 전에 제휴링크와 고지 문구를 삽입하라. 고지는 본문 첫 줄 ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."), 링크는 `[LINK]` 자리에 치환하라. 유효한 링크가 없거나 미치환 토큰이 남으면 해당 초안은 `failed`로 기록하고 제외하라.

4. 각 초안+근거를 GPT 검수자에게 보내라:
   `~/workspace/skills/openai/bin/gpt-chat --system-file ~/workspace/threads/prompts/auditor.md --user-file <draft>`
   (근거 파일 내용을 --user 입력에 함께 포함하라. 인트로·소통형 초안은 auditor.md의 콘텐츠 유형별 검수 강도를 적용하라.)
   결과를 `~/workspace/threads/queue/review/YYYYMMDD-NN.md`에 저장하라 (원본 초안 + GPT 판정 전문).
   - 판정이 `수정필요`면 초안을 1회 수정하고 재검수하라 (최대 1회).
   - 판정이 `반려`면 해당 초안을 폐기하고 새 초안 1개를 작성해 검수하라 (최대 1회).
   - 검수 실패·시간초과·이상 응답은 통과로 처리하지 마라. `failed`로 기록하고 최종 보고에 명시하라.
   - API가 429/insufficient_quota로 실패하면 해당 초안의 검수를 **보류**하고, 최종 보고에 "OpenAI 크레딧 부족 — platform.openai.com Billing에서 충전 필요"라고 명시하라. 검수 성공 없이 승인 요청 단계로 넘어가지 마라.

5. ~/workspace/threads/prompts/tone.md로 톤 검수를 직접 수행하라.

6. 실행 로그를 ~/workspace/threads/logs/YYYYMMDD.md에 한 줄씩 기록하라 (상태: draft/reviewed/failed).

7. 최종 메시지로 사용자에게 보고하라: 최종본 2개 전문 + 근거 요약 + 각각의 GPT 판정 요약 + "발행 승인 요청". 보고에 다음 문구를 포함하라: "승인된 글은 다음날 오전 7시에 승인본과 바이트 단위로 동일하게 자동 발행됩니다." 승인이 떨어지기 전에는 절대 발행하지 마라.

보고는 한국어로, 간결하게. 초안 전문은 반드시 포함하라.
