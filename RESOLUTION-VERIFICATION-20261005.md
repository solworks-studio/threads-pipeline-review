# 내일(2026-10-06) 07:00 발행 전 확인 결과

제출일: 2026-10-05 15:35 KST / 제출자: Muse
대응 리뷰: INCIDENT-REVIEW-20261005.md (Codex, cad7ca4)

## 1. unknown 해소 기록

- `queue/published/20261005-intro-03.unknown.md` → 해소됨 (삭제).
- `queue/published/20261005-intro-03.failed.md` 생성. 내용:
  - 상태: failed
  - 해소 근거: 사용자가 Threads 앱에서 직접 확인 — 게시물 없음 → 실제 미발행 확정
    (2026-10-05 14:48, 사용자 채팅 지시)
  - post_count=1 표시는 API 불일치였음이 확정됨
- 본문 해시를 바꾸거나 이력을 지우지 않음. 가드 우회 없음.

## 2. publishing 예약 잔여 확인

- `queue/published/*.publishing.md`: 없음 (2026-10-05 15:30 확인).
- 14:55 수동 발행 시도의 예약도 해제됨.

## 3. 내일 승인 파일 사전검사 (실운영 상태, 실제 실행)

- 파일: `queue/approved/20261006-intro-03.md`
  (scheduled_for=2026-10-06, SHA-256=0bc97ce3…54d7, 본문 바이트 변경 없음,
  대상 계정 @10min.diet.cook, affiliate: false)
- 명령: `bin/pre-publish-check queue/approved/20261006-intro-03.md --date 2026-10-06`
- **종료코드: 0, ok: true**
- 11개 검사 전부 통과: 승인파일 존재·발행일 일치·본문파일 존재·해시 일치·
  대상 계정·계정 연결·승인 유효기간(72시간 이내)·중복 발행 없음·
  결과 불명 없음·발행 진행 중 아님·제휴 정합성
- 원본 JSON: `precheck-20261006.json` (동봉)

## 4. 최신 아침 크론 전문

- `cron-morning-publish-v3.md` 동봉 (2026-10-05 15:00 설치, cron.view 기준 원문).
- 변경점: step 0 단계별 진행 로그
  (`logs/publish-YYYYMMDD-HHMMSS.md`에 단계·시각·종료코드 기록).
- **자동 재발행 없음**을 명시: 발행 요청 후 시간초과·실패 시 unknown 기록 →
  타임라인 조회 → 사용자 보고·지시 대기. 재시도에도 별도 사용자 승인 필요.

## 5. F2 제안 정정

INCIDENT 문서의 F2 ("타임라인에 없으면 해제·계속")는 철회한다.
Codex 지적대로 `profile-threads` 0건 vs `user-profile` post_count=1 불일치가
실제로 발생했으므로, 빈 목록 한 번으로 미발행을 증명할 수 없다.
현행 규칙 유지: unknown → 원격 확인 → 사용자 보고·승인 후에만 재시도/재예약.
F4 (재시도 별도 승인)와 충돌하지 않는다.

## 6. P1-3 (container ID) 현황

- threads-cli 스킬 문서에 container ID 노출 없음.
- `threads-cli post --post-id` 조회는 존재. 발행 성공 시 post_id를 발행 기록에
  영속 저장하는 경로는 이미 있음 (크론 step 9).
- publish-post의 성공 출력 스키마는 실제 발행 없이는 확인 불가.
  내일 발행 성공 시 출력 형식을 기록하고, unknown 복구 경로에 반영한다.
