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

**레시피 출처 원칙 (2026-10-07 신설, Codex 리뷰 반영, 필수):** 실제로 열람한 기존 레시피를 기반으로 변형·재구성하는 것은 허용한다. 금지 대상은 (1) 참고 근거 없이 조합한 레시피를 검증된 조리법처럼 제시하는 것, (2) 타인 콘텐츠 복제(원본 문장·특징적 표현·사진 그대로 사용)다. 순서는 반드시 **원본 레시피 실제 열람 → 근거 파일 작성 → 초안 작성 → 검수**다. 근거가 없거나 검수에 실패한 레시피는 승인 요청에서 제외하라.

1. 레시피형 소재를 정하면 먼저 웹 검색으로 실제 레시피를 1개 이상 **실제로 열람**하라. 열람한 원본의 핵심 정보(주재료·분량·조리 구조)를 확보하라. 존재하는 URL을 붙이는 것만으로는 열람이 아니다.

2. 근거 파일을 먼저 작성하라: `~/workspace/threads/evidence/TEMPLATE.md` 형식으로 `~/workspace/threads/queue/evidence/YYYYMMDD-NN.md`. 원본 제목, 작성자/사이트, URL, 확인일, 실제로 확인한 핵심 정보, 변경 전후·이유·근거, 미검증 항목, 실제 조리 여부, 그리고 **승인 패키지 자료(원본 요약 + 변경표)**를 기록하라. 변경표 형식: `변경 항목 | 원본 | 최종본 | 변경 이유 | 영향·근거/미확인 사항`. 분량 확정(범위에서 특정 값 선택, "약간"의 수치화, 재료 전제 변경)도 전부 변경 항목으로 기록하라. 영양 수치는 각 재료를 `~/workspace/threads/bin/mfds-lookup "식품명"` 으로 식약처 DB에서 실제 조회하고, 원재료 항목이 없으면 `~/workspace/threads/bin/usda-lookup "영문 식품명"` 으로 USDA에서 교차검증하라 (Energy가 KJ면 kcal로 환산: ÷4.184). 두 곳 모두 없을 때만 "AI 계산 (외부 교차검증 미실시)"로 표기하라. 본문에 등장하는 모든 재료가 재료 표와 칼로리 계산에 포함돼야 한다. 근거 없는 수치는 본문에서 빼라. 출처는 실제 조회한 경우만 기재하라 (허위 기재는 검수 반려). 변형한 분량 기준으로 칼로리를 재계산하라.

3. ~/workspace/threads/prompts/writer.md를 읽고 초안 2개를 작성하라. 최종 글의 설명·도입·팁은 네 문장으로 새로 쓰고, 원본 문장의 단어 치환으로 때우지 마라. 본문 말미에 참고 출처를 짧게 표기하라 (예: "레시피 참고: ○○"). 주재료 교체·핵심 조리법 변경은 추가 레시피 근거나 실제 조리 검증이 있을 때만 하고, 없으면 완성된 레시피처럼 제시하지 마라. frontmatter(affiliate/product)를 포함하고, 어제(queue/drafts, queue/review) 소재와 겹치지 않게 하라. `~/workspace/threads/queue/drafts/YYYYMMDD-01.md`, `YYYYMMDD-02.md`에 저장하라. 같은 날짜 파일이 이미 있으면 중복 실행으로 보고 중단하라.

4. frontmatter `affiliate: true`인 초안은 검수 전에 제휴링크와 고지 문구를 삽입하라. 고지는 본문 첫 줄 ("이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."), 링크는 `[LINK]` 자리에 치환하라. 유효한 링크가 없거나 미치환 토큰이 남으면 해당 초안은 `failed`로 기록하고 제외하라.

5. 각 초안+근거+**열람한 원본의 요약(핵심 정보와 원본-최종본 비교 포함)**을 GPT 검수자에게 보내라:
   `~/workspace/skills/openai/bin/gpt-chat --system-file ~/workspace/threads/prompts/auditor.md --user-file <draft>`
   (근거 파일 내용과 원본 요약을 --user 입력에 함께 포함하라. 검수자는 링크를 직접 열 수 없으므로 URL만으로 검증했다고 간주하지 마라. 인트로·소통형 초안은 auditor.md의 콘텐츠 유형별 검수 강도를 적용하라.)
   결과를 `~/workspace/threads/queue/review/YYYYMMDD-NN.md`에 저장하라 (원본 초안 + GPT 판정 전문).
   - 판정이 `수정필요`면 초안을 1회 수정하고 재검수하라 (최대 1회).
   - 판정이 `반려`면 해당 초안을 폐기하고 새 초안 1개를 작성해 검수하라 (최대 1회). 새 초안도 원본 열람→근거→작성 순서를 지켜라.
   - 검수 실패·시간초과·이상 응답은 통과로 처리하지 마라. `failed`로 기록하고 최종 보고에 명시하라.
   - API가 429/insufficient_quota로 실패하면 해당 초안의 검수를 **보류**하고, 최종 보고에 "OpenAI 크레딧 부족 — platform.openai.com Billing에서 충전 필요"라고 명시하라. 검수 성공 없이 승인 요청 단계로 넘어가지 마라.

6. ~/workspace/threads/prompts/tone.md로 톤 검수를 직접 수행하라. **톤 검수로 본문이 바뀌면, 바뀐 최종본으로 GPT 재검수를 다시 수행하고 승인 비교 자료(변경표)를 갱신하라.** 톤만 맞고 재검수를 통과하지 않은 본문은 승인 요청에 넣지 마라.

7. 실행 로그를 ~/workspace/threads/logs/YYYYMMDD.md에 한 줄씩 기록하라 (상태: draft/reviewed/failed).

8. 최종 메시지로 사용자에게 **승인 패키지**를 보고하고 "발행 승인 요청"을 하라. 레시피마다 아래 4가지를 이 순서로 전부 포함하라. 하나라도 빠지면 그 레시피의 승인 요청을 보류하고 누락을 명시하라. 원본 링크만 보내거나 근거 파일에만 저장한 것으로는 충족되지 않는다.
   1. 원본 제목·작성자/사이트·URL·확인일 + 직접 확인한 요약 (인분, 재료/분량, 조리 순서, 원본 표기 시간)
   2. 최종 변형 레시피 (재료·분량·순서)
   3. 변경표 (변경 항목 | 원본 | 최종본 | 변경 이유 | 영향·근거/미확인 사항)
   4. 실제 게시할 최종 본문 전문 + 버전 + GPT 판정 + 예정 발행일시
   보고에 다음 문구를 포함하라: "승인된 글은 다음날 오전 7시에 승인본과 바이트 단위로 동일하게 자동 발행됩니다." 승인이 떨어지기 전에는 절대 발행하지 마라.

보고는 한국어로. 최종 본문 전문은 반드시 포함하라.
