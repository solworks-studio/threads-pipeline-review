---
id: threads-morning-publish
title: 쓰레드 승인글 아침 7시 발행
enabled: true
owner: goal:threads-automation-pipeline-diet-10-minute-recipes
mode: task
schedule:
  kind: daily
  timezone: Asia/Seoul
  time: 07:00:00
delivery:
  - chat_id: 2d04738b-be29-43ca-9d27-b3ef7f349e22
metadata:
  originating_chat_context_json: '{"chat_id":"2d04738b-be29-43ca-9d27-b3ef7f349e22","origin_provider":"main","chat_kind":"direct","event_kind":"message","require_mention":false,"device_id":"312bdddb-a230-4398-8166-916e2b17c48b"}'
  presentation_locale: en-US
---
쓰레드 파이프라인의 아침 발행 작업이다. 전체 설계는 ~/workspace/threads/PIPELINE.md v2를 따르라. 시간대는 Asia/Seoul.

이 작업의 발행 권한은 사용자의 명시적 지시("전날 승인한 글을 다음날 오전 7시에 승인본 그대로 발행")에 근거한다. 승인된 바이트와 한 글자라도 다르면 발행하지 마라.

0. **진행 로그**: 실행 시작 시 `~/workspace/threads/logs/publish-YYYYMMDD-HHMMSS.md` 파일을 생성하라 (YYYYMMDD-HHMMSS=실행 시작 시각). 이후 각 단계가 끝날 때마다 `HH:MM:SS step=<번호> <단계명> 결과=<ok|차단|실패> (종료코드=<N>)` 형식으로 한 줄씩 추가하라. 실행 환경이 중간에 재시작돼도 사망 지점을 특정할 수 있게 하는 것이 목적이다.
1. 오늘 날짜(YYYYMMDD) 기준으로 ~/workspace/threads/queue/approved/ 에서 scheduled_for=오늘인 승인 파일을 찾으라. 파일 형식: YYYYMMDD-<slug>.md, 안에 본문 파일 경로 + SHA-256 해시 + 승인 기록이 있다.
2. 승인 파일이 없으면: 발행하지 마라. ~/workspace/threads/logs/YYYYMMDD.md에 "발행 건 없음"을 기록하고 종료하라. 사용자에게 별도 보고는 하지 마라.
3. 승인 파일에서 SHA-256 해시와 본문 파일 경로, 슬러그를 읽으라.
4. **발행 전 상태 확인**: `~/workspace/threads/bin/pre-publish-check <승인파일>` 을 실행하라. **종료코드를 반드시 확인**하라 (0=통과, 2=차단). JSON의 ok만 보지 마라. 종료코드가 0이 아니면 발행하지 말고, reasons를 사용자에게 보고하라. 이 단계에서 탈락하면 예약을 잡지 않았으므로 해제 호출을 하지 마라.
5. **원자적 예약**: `~/workspace/threads/bin/reserve-publish <SHA-256> <슬러그>` 를 실행하라. stdout으로 출력된 owner token을 보관하라. 종료코드가 0이 아니면 (다른 실행 진행 중이거나 이미 발행/불명 기록이 있으면) 발행하지 말고 보고하라. 예약을 잡지 못했으므로 해제 호출을 하지 마라.
6. **최종본 재검수**: `~/workspace/threads/bin/final-audit <본문파일>` 을 실행하라. 종료코드 0(판정 통과)이 아니면 보관한 owner token으로 `~/workspace/threads/bin/release-publish <SHA-256> <토큰>` 을 실행해 예약을 해제한 뒤, 발행하지 말며 사용자에게 보고하라. 승인본을 고쳐서 발행하지 마라.
7. threads-cli accounts로 계정 id를 확인한 뒤, 검증 래퍼로 발행하라:
   `~/workspace/threads/bin/publish-post-verified <SHA-256> <본문파일> <account-id> --log <진행로그>`
   래퍼가 발행 직전에 본문 해시를 재확인하고 publish_begin/publish_result를 로그에 남긴다. 해시 불일치(종료코드 2)면 발행되지 않는다.
   대상 계정은 @10min.diet.cook (id 17841427109584787)이다. 다른 계정이면 owner token으로 예약을 해제한 뒤 중단하고 보고하라.
8. 발행 요청 후 시간초과·실패 시: queue/published/에 SHA-256·상태: unknown·시각을 기록하고 owner token으로 예약을 해제한 뒤, 실제 게시 여부를 먼저 조회하라 (profile-threads로 목록 확인). 무조건 재발행하지 마라. 사용자에게 보고하고 지시를 기다려라.
9. 발행 성공 시: queue/published/ 에 발행 기록(SHA-256·상태: published·시각·post_id)을 남기고 owner token으로 예약을 해제하라.
10. 사용자에게 간결하게 보고하라: 발행된 글 전문 + post id. 한국어로.

주의: 재시도 호출에도 별도 사용자 승인이 필요하다. 이 크론은 승인된 1건을 1회만 발행한다. **예약을 잡지 못한 실행은 절대 release-publish를 호출하지 마라.** 토큰 없이 해제하지 마라.
