# v5 재검토 — 개선 확인, 중복 발행 방지는 아직 미완료

- 검토일: 2026-10-05 (Asia/Seoul)
- 검토 대상: `9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1`
- 이전 검토: [TEST-REVIEW-20261004.md](TEST-REVIEW-20261004.md)
- 독립 재현: [review-tests/recheck_v5.py](review-tests/recheck_v5.py)
- 실행 결과: [review-tests/v5-probe-results.json](review-tests/v5-probe-results.json)
- 실제 Threads 게시·조회 및 GPT API 호출: 이번 검토에서 모두 0회. 운영 크론·승인 파일은 변경하지 않았다.

## 판단

지난 지적을 실제로 반영했다. 차단 종료코드, publishing 상태 검사, 제휴 필수 필드,
별도 판정 파서, 최종 검수 래퍼, 현행 크론 전문과 결과 JSON이 추가됐다.
기존 테스트도 경로·계정 연결을 격리 환경에 맞춰 실행했을 때 **B 10/10, C 13/13, D 11/11** 통과했다.

그러나 이것으로 중복 발행이 방지됐다고 결론 내릴 수 없다. **같은 머신·같은 해시·같은 슬러그에서
두 실행이 모두 사전검사를 통과하고, 첫 실행의 완료 후 두 번째가 예약하는 순서에서는 가짜 게시가 2회 가능했다.**
분산 환경의 문제가 아니라 현재 검사·예약 순서의 문제다.
아래 P1 세 항목을 해결한 뒤 자동 발행 경로를 다시 검증해야 한다.

## 확인된 개선

| 항목 | 독립 확인 |
|---|---|
| 승인 없음·본문 변조·72시간 초과 | 모두 종료코드 2로 차단 |
| 기존 published / unknown / publishing 기록 | 모두 종료코드 2로 차단 |
| 제휴 URL 누락 | 종료코드 2로 차단 |
| `판정: 수정필요`와 설명의 `통과 가능` 혼동 | 수정필요로 차단, 이전 오판 해결 |
| 두 개의 정상 형식 판정 줄 | 차단 |
| 현행 아침 크론 | 검사→예약→최종 검수→발행 순서와 종료코드 확인 명시 |
| 크레딧 부족 처리 | PIPELINE-v5는 검수 보류·승인 단계 차단으로 개선. 일일 크론에는 옛 문구가 남음 |

## 1. [P1] 예약 획득 안에서 완료 상태를 다시 확인해야 한다

위치: [reserve-publish.py L22–34](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/reserve-publish.py#L22),
[cron-morning-publish-v2.md L24–25](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/cron-morning-publish-v2.md#L24).

현재 사전검사와 예약은 별도 명령이다. 예약은 `.publishing.md`만 검색하고 published/unknown을 검사하지 않는다.
O_EXCL은 해당 파일 생성 시점의 충돌만 막으며, 발행 완료 뒤 파일을 삭제하면 다음 실행이 생성할 수 있다.

독립 재현 순서:

1. A와 B가 같은 승인본의 사전검사를 각각 통과한다. 둘 다 종료코드 0.
2. B를 예약 직전에 멈춘다.
3. A가 예약→가짜 게시→published 기록→예약 해제를 완료한다.
4. B가 이전 검사 결과를 가지고 예약한다. **종료코드 0으로 성공**한다.
5. B도 통과 판정을 받는다면 같은 본문을 다시 게시할 수 있다. 재현의 가짜 게시 카운터는 **2회**.

해결: 계정+승인 ID/해시를 기준으로 공통 잠금을 획득한 뒤,
그 잠금 안에서 published/unknown/publishing 상태와 승인 유효성을 다시 검사하고 상태를 전이해야 한다.
검사만 잠금 밖에서 수행하고 예약 파일만 원자적으로 만드는 것으로는 부족하다.
동일 해시를 다른 슬러그가 사용해도 동일한 잠금 키를 사용해야 한다.
성공/불명 결과 기록을 확정할 때까지 잠금을 유지하고, 그 뒤 잠금을 획득하는 실행도 완료 상태 때문에 차단돼야 한다.

회귀 테스트: B를 예약 전에 정확히 멈추고 A가 기록·해제를 완료한 뒤 B를 재개한다.
가짜 게시 **정확히 1회**, B 차단을 요구한다. 기존 D 테스트는 시작 지점 barrier와 실행 1회만 사용하여 이 순서를 강제하지 않는다.

## 2. [P1] 잠금을 얻지 못한 실행이 다른 실행의 잠금을 지울 수 있다

위치: [release-publish.py L17–21](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/release-publish.py#L17),
[아침 크론 L35](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/cron-morning-publish-v2.md#L35).

해제 명령은 해시가 포함된 예약 파일을 모두 삭제한다. 해제 호출자가 예약을 얻었는지 확인하지 않는다.
크론 끝의 “어떤 단계에서 차단되면 예약을 해제”는 사전검사나 예약 충돌로 탈락한 실행에도 적용될 수 있다.

재현: A 예약 성공 → B 예약 실패(종료코드 1) → B가 같은 해시로 해제 호출 → **A의 예약 1건 삭제**.
활성 예약이 0건으로 바뀌었다.

해결: 예약 성공 시 임의 owner token/run ID를 반환하고, 해제·완료 전이는 동일 소유자만 허용한다.
예약 실패 시 해제를 호출하지 않는 흐름을 명시한다.
발행 요청 이후 published/unknown 기록 확정에 실패하면 잠금을 유지하고 원격 확인을 요구한다.
회귀 테스트는 예약에 실패한 B가 해제를 시도해도 A의 잠금이 남아 있는지 검사한다.

## 3. [P1] 검증한 본문과 실제 전달할 본문을 한 번만 읽어 고정해야 한다

위치: [아침 크론 L24–28](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/cron-morning-publish-v2.md#L24),
[test-publish-path.py L59–77](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/test-publish-path.py#L59).

검사·최종 GPT 검수·게시가 각각 본문 경로를 사용한다. 게시 경로 테스트도 검사 이후 파일을 다시 읽어 가짜 게시 함수에 넘긴다.
검사 후 최종 검수/게시 전에 파일을 수정하면 처음 승인된 해시와 다른 내용이 사용될 수 있다.
지금 테스트의 “변조”는 검사 전에 수정하는 경우만 다룬다.

독립 프로브에서 정상 본문 검사와 예약이 통과한 뒤 파일을 수정했을 때, 이후 읽은 본문의 해시는 승인 해시와 달랐다.
이는 실제 발행을 재현한 결과가 아니라, 현재 경로의 서로 다른 파일 읽기 사이에 발생하는 동일성 누락을 확인한 것이다.

해결: 발행 래퍼가 본문 바이트를 한 번 읽고 승인 해시와 대조한 뒤,
동일한 불변 payload를 최종 검수와 게시 함수에 전달한다. 게시 직전에 원본 경로를 다시 읽지 않는다.
검수 결과에는 payload 해시를 묶고, 실제 게시 인자도 같은 해시인지 검사한다.
회귀 테스트: 사전검사 뒤/검수 뒤 원본 파일을 바꿔도 미승인 내용의 게시 호출은 0회여야 한다.

## 4. [P2] GPT 호출 실패의 종료코드를 확인하지 않는다

위치: [final-audit.py L25–27](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/final-audit.py#L25).

`gpt-chat`의 returncode를 확인하지 않고 stdout JSON의 text만 파싱한다.
실패 프로세스(returncode=1)가 파싱 가능한 `{"text":"판정: 통과"}`를 남기도록 주입하자,
래퍼는 **종료코드 0, pass=true**를 출력했다.
예외/타임아웃을 차단하는 것과 정상 반환한 프로세스의 실패 코드를 차단하는 것은 별도다.

해결: GPT returncode가 0인지 먼저 확인하고, 오류 필드·응답 타입·빈 text·판정 형식을 검사한다.
실패 코드+통과 text, 실패 JSON, 빈 응답, 타임아웃 모두 게시 호출 0회로 검증한다.

## 5. [P2] 파트너스 URL 검사는 URL의 도메인을 검사해야 한다

위치: [pre-publish-check-v2.py L27](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/pre-publish-check-v2.py#L27).

정규식은 URL 어디든 `coupang` 문자열만 있으면 통과시킨다.
제휴 고지와 **`https://example.com/coupang`**만 포함한 제휴글이 전체 검사 종료코드 0으로 통과했다.
이 URL은 쿠팡 도메인이 아니다. 제휴 링크 누락은 해결했지만 링크 정합성 확인은 아직 부족하다.

해결: URL parser로 HTTPS와 hostname을 정확히 검사하고, 실제 사용하는 파트너스 링크 형식의 허용 목록을 둔다.
경로/쿼리의 `coupang`, 유사 도메인, userinfo로 꾸민 URL은 허용하지 않는다.
허용 도메인만으로 추천 상품과 제휴 attribution이 맞는 것까지 증명되는 것은 아니므로 링크 생성 근거도 연결한다.

## 6. [P2] 파서가 비정상 판정 줄을 세지 않아 모순된 응답을 허용한다

위치: [parse-verdict.py L13–18](https://github.com/solworks-studio/threads-pipeline-review/blob/9a6fdbce83c32c47e8a511dd7cbd0c4cb2460fd1/parse-verdict.py#L13).

`판정: 통과\n판정: maybe`를 입력하면 pass=true다.
허용값과 일치하는 줄만 세기 때문에, 두 번째 비정상 판정은 없는 것으로 취급한다.
판정이 첫 줄이 아닌 응답도 통과하며 auditor-v3의 첫 줄 계약과 다르다.

해결: 첫 줄의 형식을 검증하고 모든 `판정:` 필드를 세어 정확히 하나인지 검사한다.
가능하면 판정은 구조화 JSON의 단일 필드로 받는다.
기존 “수정하면 통과 가능” 오판은 해결됐다는 점과 이 추가 형식 검사는 구분해야 한다.

## 운영 지침·증거에서 남은 항목

- **일일 크론의 429 처리**: PIPELINE-v5와 달리 cron-daily-drafts-v3 L34는 아직 “검수를 생략”이라고 지시하고,
  L40은 최종본 2개와 승인 요청을 지시한다. 검수 실패한 슬롯은 승인 요청 목록에서 제외한다고 명확히 고친다.
- **최종 재검수의 근거**: 아침 크론은 `final-audit <본문파일>`만 호출하고 `--evidence`를 전달하지 않는다.
  레시피의 근거 파일·제휴 메타데이터를 승인 해시와 함께 묶고 최종 검수에 전달하는 계약이 필요하다.
  명시한 evidence 경로가 없으면 조용히 생략하지 않고 차단한다.
- **측정**: 주간 크론은 여전히 최근 7일 게시물의 현시점 값을 수집한다. 발행 후 24시간/7일 스냅샷과
  2/24/72시간 댓글 수집을 예약하는 실행물은 이번 제출에도 없다. 수익화 실험의 비교 기준을 위해 보완한다.
- **테스트 증거**: 이번 JSON은 A 10건의 결과다. B/C/D 원본 출력과 GPT 원문·판정·본문 해시를 함께 남기면
  검수 모델이 제대로 반려했는지, 호출 오류 때문에 차단됐는지를 구분할 수 있다.
  run-blocking-tests-v2의 고정 날짜·실운영 디렉토리 fixture·파일 존재만 확인하는 크론 중복 테스트는 여전히 남아 있다.
- **공통 실행 경로**: D는 운영 코드의 미러다. 상태 확인·예약·검수·게시·기록을 수행하는 공통 래퍼에
  가짜 게시/GPT 어댑터를 주입해 검사해야 운영과 테스트가 달라지는 문제를 줄일 수 있다.

## 다음 검토에 제출할 최소 증거

1. 공통 발행 래퍼와 소유자 검증이 있는 잠금/상태 전이 코드.
2. 차단 케이스별 가짜 게시 0회, 정상 1회.
3. 두 검사 동시 통과→A 완료→B 예약 재개 순서에서도 게시 정확히 1회.
4. 예약 실패한 실행이 타 실행의 잠금을 삭제하지 못함.
5. 검사/검수 사이 파일 변조 시 미승인 payload 게시 0회.
6. GPT 비정상 종료·비정상/복수 판정·비제휴 도메인 URL 모두 차단.
7. 위 테스트 원본 출력과 payload 해시, 현행 크론 전문.

실환경 스모크 A는 이 PC에 Muse의 실행 환경·승인 파일이 없고 GPT 실호출을 포함하므로 재실행하지 않았다.
B/C/D 재실행은 경로만 임시 디렉토리로 변경하고 계정 연결 확인을 True로 대체했다.
이것은 실제 계정 토큰·상품 링크·외부 게시 성공·현재 설치된 크론 동작에 대한 검증이 아니다.

독립 재현 실행: UTF-8 모드로 `python -X utf8 review-tests/recheck_v5.py`.
결과 JSON에 성공 대조군과 각 빈틈의 관찰값을 함께 저장했다.
