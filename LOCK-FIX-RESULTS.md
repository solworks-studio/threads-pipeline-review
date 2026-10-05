# P1 잠금 소유권 수정 결과 (RESOLUTION-REVIEW-20261005.md §1 대응)

- 실행일: 2026-10-05 / 실제 publish-post 호출: 0회

## 수정 내용

| 지적 | 수정 |
|---|---|
| A 완료·해제 후 B가 재예약 → 중복 발행 가능 | `reserve-publish`가 예약 시점에 published/unknown을 재확인 (있으면 exit 3 거부). A의 published 기록이 B를 막는다 |
| `release-publish` 소유자 검증 없음 | owner token 도입. 예약 성공 시 uuid4 토큰 발급·파일 기록·stdout 출력. 해제는 토큰 일치 시에만 |
| 탈락한 실행이 타 실행의 잠금을 해제 | 크론 지시 변경: 예약을 잡지 못한 실행은 절대 release 호출 금지. 토큰 없이 해제 불가 (exit 2) |
| 검증·검수·게시가 본문을 따로 읽음 (불변 payload 아님) | `publish-post-verified` 래퍼: 발행 직전 SHA-256 재확인, 불일치 시 미발행. publish_begin(요청 직전)/publish_result(응답 직후) 영속 로그 |

## 테스트 결과

### test-lock-ownership.py — 12/12 통과
- A 예약→토큰 발급, B 예약 거부, 타인 토큰 해제 거부(예약 유지),
  소유자 해제 성공, 토큰 없는 해제 거부
- published/unknown 존재 시 예약 거부 (exit 3)
- publish-post-verified: 해시 불일치 차단 + publish_aborted 로그,
  dry-run에서 publish_begin/result 로그 (sha·account·bytes 포함)
- 2스레드 동시 예약: 승자 1명, 패자의 해제 시도 거부

### test-publish-path.py (토큰 플로우 반영) — 11/11 통과
- 정상 1회, 차단 9종 0회, 동시 최대 1회 (가짜 게시)

### 기존 스위트 회귀
- test-verdict-parser.py 10/10, test-guard.py 13/13 통과

## 크론 반영

`cron-morning-publish-v4.md`: step 5에서 토큰 보관, step 6·8·9에서 토큰으로만 해제,
step 7에서 `publish-post-verified` 사용. "예약을 잡지 못한 실행은 절대 해제 호출 금지" 명시.

## 미반영 (후속)

- 07:10 읽기 전용 감시 크론: 신규 스케줄이라 사용자 승인 후 생성
- container ID: 스킬 미노출. publish-post 성공 출력 스키마는 실제 발행 시 기록 예정
