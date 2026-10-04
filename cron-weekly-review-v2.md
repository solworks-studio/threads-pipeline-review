---
id: threads-weekly-review
title: 쓰레드 파이프라인 주간 성과 리뷰
enabled: true
owner: goal:threads-automation-pipeline-diet-10-minute-recipes
mode: task
schedule:
  kind: weekly
  timezone: Asia/Seoul
  time: 09:00:00
  dow: [Mon]
delivery:
  - chat_id: 2d04738b-be29-43ca-9d27-b3ef7f349e22
metadata:
  originating_chat_context_json: '{"chat_id":"2d04738b-be29-43ca-9d27-b3ef7f349e22","origin_provider":"main","chat_kind":"direct","event_kind":"message","require_mention":false,"device_id":"3f643d2e-980d-4101-9024-bf35ff47b900"}'
  presentation_locale: ko-KR
---
쓰레드 파이프라인 주간 성과 리뷰. 전체 설계는 ~/workspace/threads/PIPELINE.md v2의 "성과 측정" 절을 따르라. 시간대는 Asia/Seoul.

1. ~/workspace/threads/queue/published/ 에서 지난 7일간 발행된 게시물 목록을 읽어라 (post id, 주제, 형식, 시간, 제휴 여부).
2. threads 스킬(~/opt/hatch/skills/threads/SKILL.md 또는 ~/workspace/skills 내)을 읽고 사용 가능한 insights/조회 명령을 확인하라. 각 게시물의 조회·좋아요·댓글·재게시·공유를 수집하라. API에 없는 값은 0이 아니라 `미수집`으로 기록하라.
3. 결과를 `~/workspace/threads/queue/metrics/YYYYMMDD-weekly.md`에 기록하라 (게시물별: 발행 ID, 주제, 형식, 시간, 제휴 여부 + 지표).
4. 지표를 계산하라: 조회 대비 댓글·공유율, 제휴글의 링크 클릭(수집 가능 시). 쿠팡파트너스 클릭·주문·수수료는 API 미연동이므로 사용자가 제공하기 전까지는 제외하고, 그旨을 명시하라.
5. 최종 메시지로 사용자에게 보고하라: 주간 지표 요약 + 가장 잘된 게시물 1개 + 다음 주에 바꿀 1가지 제안 (주제·제품·빈도 중 하나). 한국어로 간결하게.

이 크론에는 발행 권한이 없다. 측정·보고만 수행하라.
