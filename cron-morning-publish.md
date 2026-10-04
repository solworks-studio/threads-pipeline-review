# 아침 발행 크론: threads-morning-publish (스케줄러 설정, 신설 2026-10-04)

- 스케줄: 매일 07:00, Asia/Seoul
- 실행 종류: agent (승인글 발행)
- 발행 권한의 근거: 사용자의 명시적 지시 ("전날 승인한 글을 다음날 오전 7시에 승인본 그대로 발행"). 승인된 바이트와 한 글자라도 다르면 발행하지 마라.

## 지시문 전문

1. 오늘 날짜 기준 `~/workspace/threads/queue/approved/`에서 scheduled_for=오늘인 승인 파일을 찾으라 (형식: YYYYMMDD-<slug>.md, 본문 + SHA-256 해시 + 승인 기록).
2. 승인 파일이 없으면 발행하지 마라. 로그에 "발행 건 없음" 기록 후 종료. 별도 보고 불필요.
3. 승인 파일이 있으면 본문의 SHA-256을 계산해 기록된 해시와 대조. 불일치 시 중단하고 사용자에게 보고.
4. `threads-cli accounts`로 계정 id 확인 후 발행: `threads-cli publish-post --account-id <id> --text "<승인 본문>"`. 대상 계정은 @10min.diet.cook (id 17841427109584787). 다르면 중단하고 보고.
5. 발행 타임아웃·실패 시 unknown 기록 후 실제 게시 여부 조회. 무조건 재발행 금지. 사용자에게 보고하고 지시 대기.
6. 성공 시 post id를 `queue/published/`에 기록 (발행 ID, 해시 대조 결과, 시각).
7. 사용자에게 보고: 발행된 글 전문 + post id.
