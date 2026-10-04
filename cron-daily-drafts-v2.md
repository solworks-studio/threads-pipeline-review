# 일일 크론: threads-daily-drafts (스케줄러 설정, v2)

- 스케줄: 매일 19:00, Asia/Seoul (2026-10-04 변경, 기존 07:00)
- 실행 종류: agent (초안 생성·검수·승인 요청)
- **발행 권한 없음.** publish-post는 절대 실행하지 마라.

## 지시문 전문

쓰레드 자동화 파이프라인의 일일 초안 생성 작업이다. 전체 설계는 ~/workspace/threads/PIPELINE.md v2를 따르라. 시간대는 Asia/Seoul.

**이 크론에는 발행 권한이 없다.** 초안 생성·검수·승인 요청까지만 수행하고, threads-cli publish-post는 절대 실행하지 마라.

1. writer.md를 읽고 초안 2개를 작성하라 (frontmatter 포함, 어제 소재와 겹치지 않게). `~/workspace/threads/queue/drafts/YYYYMMDD-NN.md`에 저장. 같은 날짜 파일이 이미 있으면 중복 실행으로 보고 중단.
2. 레시피형은 근거 파일 작성 (`queue/evidence/`). 근거 없는 수치는 본문에서 제외.
3. `affiliate: true`인 초안은 검수 전에 제휴링크·고지 삽입 (고지는 본문 첫 줄, 링크는 `[LINK]` 치환). 유효 링크가 없으면 `failed`로 기록하고 제외.
4. GPT 검수 (`gpt-chat --system-file prompts/auditor.md --user-file <draft>`, 근거 포함). 인트로·소통형은 콘텐츠 유형별 검수 강도 적용. `수정필요`→1회 수정 후 재검수, `반려`→폐기 후 새로 1개 (최대 1회). 검수 실패·타임아웃은 통과 처리 금지.
5. tone.md 톤 검수.
6. 로그 기록 (`logs/YYYYMMDD.md`).
7. 사용자에게 보고: 최종본 전문 + 근거 요약 + GPT 판정 요약 + "발행 승인 요청". 문구 포함: "승인된 글은 다음날 오전 7시에 승인본과 바이트 단위로 동일하게 자동 발행됩니다."
