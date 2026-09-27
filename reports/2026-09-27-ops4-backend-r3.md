---
order: 2026-09-27-74
from: backend-engineer
ticket: OPS-4
result: done
verified: 재현
handoff: []
workflow: ops4-r3
---

# OPS-4 r3 — 대시보드 행에 고장 판정(`verdict`) · 결재함 예약 작업 경보 목적 줄 · 140자 경계 자르기 (backend-engineer, 지시서 2026-09-27-74)

[요약] 지시서의 1~4를 모두 했다. 전체 스위트는 **2,358 passed · 4 xfailed · 0 failed**다(11분 08초).

- **① `verdict` 싣기(QA-OPS4-4 ⓐ)**
  - 대시보드 예약 작업 행마다 `verdict` = {"broken", "label"} 를 싣는다.
  - 값은 순환계 `schedule_verdict` 결과 그대로다(`agent_dashboard.attach_verdict`). 못 붙이면 None 이다.
- **필드 동일성(먼저 확인한 것)**
  - 두 읽기는 **같은 함수**(`read_schedule`)다. 그래서 칸도 뜻도 같다(확인).
  - 달랐던 것은 **판정 순서** 하나였다. `silence_rows` 가 고장 행에도 조용한 누락 판정을 돌려서, 스탠드업은 내지 않는 트리거 경고를 대시보드만 냈다.
  - `judge_task` 한 곳으로 모아 같게 했다.
- **KPI**
  - 새 키 `sched_stopped`(꺼짐·다음 실행 없음)를 더하고 `sched_alarm` 에 합쳤다.
  - 기존 키의 뜻은 그대로다.
- **결재함 목적 줄(design r2 #1)**
  - 라벨을 그대로 앞에 두고, 라벨에 없는 것만 붙인다.
  - 1999 날짜·괄호·'N시간째'·'다음 실행 없음' 되풀이가 모두 없어졌다.
  - 이 PC 작업 이름 9개로 계산하면 가장 긴 줄이 123자다. 자를 일이 없다.
- **140자 자르기**
  - 한도는 그대로 두고 ` · ` 경계(없으면 공백 경계)에서 자르고 `…` 을 붙인다. 시각·숫자 중간은 자르지 않는다.
  - 지금 열린 지시서 21장 중 한도를 넘는 것은 4장(모두 인계)이다. 넷 다 낱말 경계에서 `…` 로 끝난다.
- **스키마**: 웹 API(`web/`)·템플릿 dict 키·DB 는 바뀌지 않았다. 사내 대시보드 JSON 에 행 `verdict` 와 KPI `sched_stopped` 가 더해졌다(§7 명세 — frontend `-75` 가 읽는다).
- **테스트**: 신규 26건. 옛 동작 13종을 메모리에서 되살리면 **13/13** 빨간불이다.
- **Steward 가 볼 것**(§8):
  - 매분 스냅샷이 작업 트리 코드로 새 필드를 이미 서버에 올리고 있다(로그 근거).
  - 스탠드업 '경보 → 티켓' 줄에는 'N시간째'가 남아 있다(범위 밖).
  - 꺼짐 + 실패 행을 표에 어떤 글자로 칠할지는 frontend 가 정한다.

## 0. 조건

- **기준**
  - HEAD `5625ed4` + 작업 트리(OPS-4 1·2회차 미커밋)다. 작업 중 HEAD 는 움직이지 않았다.
  - 시작 md5 는 qa r2 기록과 같았다: `org_runtime.py` `7db51ab3` · `agent_dashboard.py` `ec0e3ed7` · `agent_dashboard.html` `8c9e4d8f` · `org-contracts.md` `8fb967b1`.
  - 작업 트리에는 내가 오기 전 변경이 두 개 더 있었다: `.claude/commands/daily-check.md`·`docs/backlog.md`(19:07:24 — r3 발행 때로 보인다, 내 것 아님). 둘 다 손대지 않았다. daily-check 의 '대시보드 예약 작업 표' 어휘는 이미 고쳐져 있다(qa·design r2 지적 해소 — 확인).
- **끝 md5**: `org_runtime.py` `d113bf59` · `agent_dashboard.py` `70bea076` · `agent_dashboard.html` `8c9e4d8f`(그대로) · `org-contracts.md` `d753beb5` · `tests/test_ops4_r3_backend.py` `11a4ed34`. 전체 스위트 시작(19:32:48)과 끝(19:43:59)에 이 입력 7개의 md5 가 같았다.
- **설치 방식**
  - 매시 스캔(:05)과 매분 스냅샷이 작업 트리의 이 두 파일을 import 한다.
  - 그래서 scratch 사본에서 편집 → `compile` 통과 → 같은 디렉터리 임시 파일 → `os.replace` 순으로 바꿨다(19:21:29, `org_runtime` 먼저). 깨진 상태로 저장된 순간은 없다.
  - CRLF 줄끝을 유지했다(편집한 6개 파일 모두 줄 수 = CRLF 수).
- **운영 무쓰기**
  - `data/org-state.json`(`73479388`)·`data/org-bus.jsonl`(`78adc339`)의 md5 가 19:13 과 19:44 에 같다.
  - `orders/` 는 78 → 78 이다.
  - 실험은 모두 tmp_path·scratch 에서 했다. 결재함 실데이터 점검(§4)은 `Org.board()`(읽기만)로 했다.
- **하지 않은 것**: 커밋, 배포, 서버 접속, 외부 요청, `tools/agent_dashboard.html` 수정, 8765·8799 기동, 작업 스케줄러 조회. 실제 9행은 운영 스냅샷 작업이 만든 JSON 을 읽었다(§2).
- **pytest**: `NC_NO_SCHEDULER=1 NC_NO_BACKGROUND=1`, `-p no:cacheprovider`.

## 1. 필드 동일성 — 먼저 확인한 것

### 1-1. 같은 것(확인된 사실)

- **같은 함수**: 순환계 `Org.schedule_states` 는 `agent_dashboard.read_schedule()` 을 그대로 부른다. 대시보드 `build_state` 도 같은 함수를 부른다.
  - 테스트 `test_runtime_reads_the_same_function_as_the_dashboard` 가 같은 **객체**가 돌아오는지 본다.
- **칸의 뜻**(`read_schedule` 한 곳에서 만든다):
  - `enabled` = State ≠ Disabled
  - `next_run` = NextRunTime(없으면 '')
  - `never_ran` = LastRunTime 이 1999-11-30
  - `running` = State Running
  - `ok` = 결과 0 이거나 실행 중
  - `last_result` = 결과 문자열
- **읽는 칸이 정확히 여섯**: `schedule_verdict` 가 읽는 칸은 이 여섯뿐이다. 새 상수 `org_runtime.SCHEDULE_FIELDS` 로 적었다.
  - 기록용 dict 로 64경우를 돌려 **읽은 칸 = 목록**인지 테스트로 고정했다. 함수가 새 칸을 읽게 되면 목록에 더해야 통과한다.
- **끝까지 같은 판정**: 가짜 PowerShell 출력 6행(꺼짐·다음 실행 없음·실패·실행 중·안 돎·정상)을 두 경로로 읽혔다.
  - 경로 ⑴ `read_schedule` → `attach_verdict`
  - 경로 ⑵ `read_schedule` → `scan`(`task_eval`, 가로채지 않음)
  - 두 경로의 라벨이 같았다. 꺼진 작업은 `enabled False`(`ok True`)로, 다음 실행이 없으면 `next_run ''` 로 온다.

### 1-2. 달랐던 것 → 맞춤

- **ⓐ 판정 순서**
  - `task_eval` 은 고장이 **아닐 때만** `silence_verdict` 를 불렀다. `silence_rows` 는 **모든 행에** 불렀다.
  - `bad` 는 결과가 같았다. `silence_verdict` 가 그 경우를 스스로 거르기 때문이다.
  - 그러나 고장 행의 트리거 경고(`warn`)·`cls`·`limit_h` 는 대시보드에만 실렸다. 예: 실패 + 트리거를 못 읽은 작업은 대시보드 '못 읽은 것'에는 경고가 있고 스탠드업에는 없었다.
  - 새 함수 `org_runtime.judge_task` 를 두어 `task_eval`·`silence_rows` 가 **둘 다** 이 함수를 거친다. 고장 행의 silence 는 `SILENCE_NONE`(bad False · warn '' · cls '' · limit_h 0)이다.
  - 테스트 `test_trigger_warning_comes_from_the_same_rows_on_both_sides`: 스탠드업 경고 목록과 대시보드 경고 목록이 글자까지 같다.
- **ⓑ 칸이 빠진 행**
  - 실제 행에는 늘 여섯 칸이 있다.
  - 그래도 대시보드는 칸이 빠진 행을 판정하지 않고 `verdict` None(모름) + '못 읽은 것' 경고로 둔다. `enabled` 가 빠진 행을 판정하면 꺼진 작업이 '정상'이 되기 때문이다.
  - 순환계 `task_eval` 에는 이 가드를 넣지 않았다. 입력이 같은 함수라 실제로는 차이가 나지 않고, 기존 테스트 픽스처가 부분 행을 쓴다.

### 1-3. 남은 차이(설계대로 — 고치지 않았다)

- **'미등록'**(§3.1 에 있는데 목록에 없는 작업)은 순환계에만 있다. 대시보드 표는 목록에 있는 작업만 행으로 그린다. 그래서 결재함의 '미등록' 지시서에 대응하는 표 행은 없다.
- **읽는 시각**: 순환계는 매시 :05 에, 대시보드는 요청마다·매분 읽는다. 그 사이에 스케줄러 상태가 바뀌면 둘이 다를 수 있다. 뜻의 차이가 아니라 시점의 차이다(추정 — 재현하지 않았다).

## 2. `verdict` 싣기(QA-OPS4-4 ⓐ)

- **`agent_dashboard.attach_verdict(sched)`**
  - `attach_silence` 와 같은 방식이다. `org_runtime` 을 import 해 `schedule_verdict` 를 그대로 부른다.
  - 판정 순서와 글자는 대시보드에 다시 짜지 않았다. 테스트가 AST 로 본문의 문자열 상수에 판정 글자('꺼짐'·'다음 실행 없음'·'실패 · 결과'…)와 `enabled` 가 없는지 본다.
- **None(모름)이 되는 때**
  - `org_runtime` import 실패 → 모든 행 None, `problems` 에 오류
  - 칸 빠짐 → 그 행 None, 행 경고
  - 판정 함수 예외 → 그 행 None, 행 경고
  - 어느 경우에도 '정상'으로 채우지 않는다.
- **`build_state` 순서**: `read_schedule` → `attach_verdict` → `attach_silence`.
- **지금 실제 9행**(19:30:48 스냅샷 JSON — 운영 스냅샷 작업이 19:21 설치 뒤 만든 것, 내가 실행하지 않음):
  - 터널: `{broken: true, label: '실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음'}`
  - db-backup-pull·monthly: '아직 때가 안 됨'
  - ops-snapshot: '실행 중'
  - 나머지 5개: '정상'
  - KPI: `sched_stopped 0` · `sched_alarm 1`. `problems` 에 새 경고는 없다(원래 있던 '판정표에 없는 자리' 한 줄뿐).

## 3. 결재함 예약 작업 경보 목적 줄(design r2 #1)

`org_runtime.task_purpose(t, now)` 가 만들고, `Org.scan` ⑦ 이 부른다. 아래 예는 테스트 기대값 그대로다(`NOW` 2026-10-28 10:05).

| 경우 | 목적 첫 줄 |
|---|---|
| 조용히 안 돎 | 예약 작업 `x-quiet` — 조용히 안 돎 · 마지막 성공 10-26 08:05 · 매일 작업 한도 36시간 넘김 · 다음 실행 2026-10-29 00:05 |
| 첫 실행 없음 | 예약 작업 `x-first` — 첫 실행 없음 · 등록 09-18 10:05 뒤 매월 작업 한도 35일 넘김 · 다음 실행 2026-11-01 10:05 |
| 실패(라벨에 '다음 실행 없음') | 예약 작업 `x-dead` — 실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음 · 마지막 실행 2026-10-16 05:24 뒤 292시간 |
| 실패(다음 실행 있음) | 예약 작업 `x-hourly` — 실패 · 결과 1(0x00000001) · 마지막 실행 2026-10-28 09:05 뒤 1시간 · 다음 실행 2026-10-28 11:05 |
| 꺼짐 | 예약 작업 `x-disabled` — 꺼짐(Disabled) · 마지막 실행 2026-10-25 10:05 뒤 72시간 |
| 다음 실행 없음 | 예약 작업 `x-no-next` — 다음 실행 없음 · 마지막 실행 2026-10-27 04:05 뒤 30시간 |
| 실행된 적 없음(등록 날짜 있음) | 예약 작업 `x-never-reg` — 실행된 적 없음 · 예정도 없음 · 등록 2026-10-23 10:05 뒤 120시간 |
| 실행된 적 없음(등록 날짜 없음) | 예약 작업 `x-never-noreg` — 실행된 적 없음 · 예정도 없음 · 순환계가 처음 본 2026-10-27 04:05 뒤 30시간 |
| 미등록 | 예약 작업 `naechaget-org-standup` — 미등록 · 순환계가 처음 본 2026-10-27 04:05 뒤 30시간 |

- **라벨**은 `silence.label`·`verdict.label` 과 글자가 같다(테스트 `test_verdict_label_is_the_inbox_label`). 결재함 표의 `tx()` 가 백틱을 지우므로, 화면에는 '예약 작업 x-quiet — …'로 보인다.
- **'N시간'의 기준을 다시 잰다.** 수는 `task_eval` 의 `since`(고장 시작)가 아니라 **그 문장이 말하는 기준**으로 계산한다.
  - 꺼짐은 `since` 가 '처음 본 때'다. 그래서 옛 `hours` 를 '마지막 실행 … 뒤'에 붙이면 거짓 문장이 된다.
  - 기준을 고르는 순서: 마지막 실행 → 한 번도 안 돌았으면 등록 → 등록 날짜도 없으면 순환계가 처음 본 때.
- **다음 실행**은 잡혀 있고 라벨이 '다음 실행'을 말하지 않을 때만 붙인다(매시 실패 작업 등).
- **1999**는 두 겹으로 막았다. `never_ran` 이면 마지막 실행 칸을 쓰지 않는다. 그 칸이 빠져도 2000년 전 시각은 실행으로 치지 않는다.
- **시각 표기**
  - 라벨 안은 순환계 라벨 그대로다(`MM-DD HH:MM`).
  - 덧붙이는 시각은 `YYYY-MM-DD HH:MM` 이다. 기존 테스트가 `다음 실행 2026-09-28 12:00` 을 단언하고 있고, 표의 날짜 칸과도 같은 모양이다.
- **이미 열린 지시서 파일은 다시 쓰지 않는다**(테스트 — 스캔 전후 md5 가 같다). 새 모양은 새로 서는 지시서부터 적용된다. 이미 열린 옛 모양 줄은 목록에서 경계 자르기만 받는다.
- **길이**: 이 PC 작업 이름 9개 × 가장 긴 라벨 7종으로 계산하면 최장 123자다. 결재함 목록 한도 안이다(계산).
  - r2 의 weekly 줄은 옛 모양이 142자(`[:140]` → `… 17:5`)였다. 새 모양은 104자다.

## 4. 140자 경계 자르기(`org_runtime.clip_line`)

`Org.board` 의 `open`·`inbox` 목록(대시보드 결재함 표·스탠드업 결재함 절)에 쓴다. 한도 `PURPOSE_CLIP = 140` 은 그대로다.

- **자르는 순서**
  - ① ` · ` 경계: 남는 앞부분이 한도의 절반(70자) 이상일 때만 쓴다. 결과는 `… · …` 꼴이다.
  - ② 공백 경계: 시각(`YYYY-MM-DD HH:MM`·`MM-DD HH:MM`) 안의 공백은 경계로 치지 않는다. 결과는 `… …` 꼴이다.
  - ③ 한 덩어리일 때만 글자 경계다. 숫자와 숫자 사이는 피한다.
- 잘린 앞부분에 짝이 안 맞는 `**`·백틱이 남으면 닫는다. 스탠드업 마크다운이 뒤 줄까지 굵게·코드로 번지지 않게 하려는 것이다.
- 결과는 늘 140자 이하다. 한도 안의 줄은 손대지 않는다.
- ①에 '절반' 조건을 둔 이유: ` · ` 가 앞쪽에 하나뿐인 긴 문장을 거기서 자르면 읽을 것이 거의 남지 않는다. 지시서의 글자에 없는 판단이라 여기 적는다.
- **옛 r2 줄**: `[:140]` 은 `… 다음 실행 2026-10-02 17:5` 였다. 새 결과는 `… · **226시간째**(마지막 실행 2026-09-25 15:53 · …`(120자)다.
- **지금 운영 결재함**(`Org.board()` 를 운영 루트에서 **읽기만** — 상태·버스 md5 전후 같음):
  - 열린 21장 중 한도를 넘는 것은 인계(handoff) 4장이다(`-15`·`-38`·`-56`·`-57`).
  - 넷 다 ` · ` 가 없는 문장이라 공백 경계에서 `…` 로 끝난다.
  - `-15` 는 114자에서 끝난다. `app-design-expert·design-critic` 이 공백 없는 한 덩어리라 그 앞에서 잘렸다.
- **다른 사유(alert·routine·owner·manual)**: 지금 열린 것 가운데 한도를 넘는 것이 없다. 테스트 픽스처(경보 줄 모양·긴 정기 점검 문장·백틱 안에서 잘리는 인계)로 확인했다. 실데이터로는 **미검증**이다.
- **적용하지 않은 곳**(범위 밖, §8): 스탠드업 디스패치 목록의 `[:90]`, 피드 `note` 의 `[:80]`.

## 5. 문서

- **`docs/org-contracts.md` §3 예약 작업 규칙 문단**
  - 괄호 "(대시보드는 결과가 0 이면 정상으로 칠한다)"를 지웠다.
  - 대신 적은 것: '대시보드의 옛 칩 규칙(결과 `ok` 만 봤다)에 없던 규칙은 **둘**', r2 까지의 엇갈림(QA-OPS4-4), 이제 행 `verdict`·KPI `sched_stopped`·`sched_alarm` 으로 같은 판정을 싣는다는 것, 칠하는 일은 frontend(`-75`), 판정 순서(`judge_task`).
  - '규칙은 **둘**' 문구는 남겼다(`test_ops3_r2_fixes` 가 본다).
- **`schedule_verdict` docstring**: '대시보드에 **없는** 규칙 둘' 문단을 같은 내용으로 바꿨다.
- **`silence_verdict` docstring**: `judge_task` 순서 한 줄을 더했다.
- **`agent_dashboard` 모듈 docstring 출처표**: 예약 작업 칸에 `verdict` 를 더했다.
- 줄 번호는 쓰지 않았다. `tools/check_md_tables.py`(계약·프로토콜): 이상 없음.

## 6. 테스트

### 6-1. 신규 `tests/test_ops4_r3_backend.py` — 26건

| 묶음 | 내용 |
|---|---|
| ① verdict | 공허 방지(네 모양 지시서·분기 전부) · 행마다 순환계 결과 그대로(꺼짐·다음 실행 없음·실패 2종·안 돎 2종·정상·실행 중·대기) · 라벨 = 결재함 라벨 · 가짜 결과가 그대로 나옴 · **판정 불가 None**(import 실패·칸 빠짐·행 예외·빈 목록, `sched_stopped` None) · 대시보드 본문에 판정 글자 없음(AST) · `build_state` 통합 |
| ② 필드 동일성 | 같은 함수(같은 객체) · 읽는 칸 = `SCHEDULE_FIELDS`(64경우) · 가짜 PowerShell → 두 경로 같은 라벨 |
| ③ 순서·겹침 | 128경우 격자에서 고장이면 silence = `SILENCE_NONE`, 둘 다 경보인 행 없음, `silence_rows` = `judge_task` · 트리거 경고가 양쪽에서 같은 행·같은 글자 |
| ④ KPI | `sched_stopped`·`sched_alarm` · 기존 키 뜻(r2 정의 재계산과 같음) · `sched_alarm` = 결재함 task 지시서 수 − 미등록 · 꺼짐 + 실패 행은 bad 로 한 번만 |
| ⑤ 목적 줄 | 아홉 모양 글자까지(§3 표) · 목록에 온전히 섬 · `clip_line` 7경우(r2 실제 줄·긴 이름·경보·인계·앞쪽 ` · `·시각 걸침·백틱) · 사유 6종 목록 자르기 + 열린 지시서 파일 무변경 · 계약·docstring 문구 |
| ⑥ 변이(파일 안) | 옛 목적 줄 9장 · 1999 · '다음 실행 없음' 되풀이 · `[:140]` · verdict 없음 / 전부 정상 / 옛 `ok` 칩 규칙 · r2 counts · r2 `silence_rows` 순서 — 각 검사 함수가 빨개진다 |

### 6-2. 기존 파일 수정 2곳(이유)

- **`tests/test_ops4_qa_r2.py`**(qa 파일)
  - 목적 줄 모양을 단언한 두 줄의 끝 `· **` 를 `· 다음 실행 ` 으로 바꿨다(지시서가 바꾸라고 한 모양이다).
  - strict xfail 표식과 reason 은 **그대로**다(diff 로 확인).
  - `test_known_gap_is_what_it_is_today` 도 그대로 두었다. 그 픽스처는 `attach_verdict` 를 부르지 않아 `sched_stopped` 가 None 이고, `sched_alarm` 식이 r2 와 같아서 여전히 통과한다. qa `-76` 이 표식을 뗄 때 이 테스트도 함께 볼 일이다.
- **`tests/test_ops4_r2_fixes.py`**(내 r2 파일): counts 전체 dict 비교에 `sched_stopped: 0` 을 더하고, `attach_verdict` 호출 한 줄을 더했다.

### 6-3. 공허 통과 점검 — 메모리 변이 13종, 13/13 빨간불

- 방식: 원본은 건드리지 않았다. scratch `-p` 플러그인으로 모듈 속성만 바꿨다. 원본 md5 는 전후가 같다.
- 대상: 신규 파일에서 `-k "not mutation"`, 즉 **본 테스트만** 돌렸다(파일 안 변이 테스트는 뺐다).
- 대조(변이 없음): 20 passed.

| 변이 | 빨개진 본 테스트 수 |
|---|---|
| 옛 목적 줄 모양 · 1999 붙임 · '다음 실행 없음' 되풀이 | 2 · 1 · 2 |
| `[:140]` 그대로 · 시각 보호 끔 | 2 · 1 |
| verdict 안 실음 · 전부 정상 · 옛 `ok` 칩 규칙 | 9 · 9 · 9 |
| 칸 검사 없음 | 1 |
| r2 counts · alarm 에 stopped 뺌 | 4 · 1 |
| `judge_task` 옛 순서 · r2 `silence_rows` | 2 · 2 |

### 6-4. 스위트

- **OPS 묶음**(ops3 3편 · ops4 7편 · org_runtime · ops_health): **371 passed · 1 xfailed**(40.9초). xfailed 는 QA-OPS4-4 strict xfail 이다 — 표 칩은 html 몫이라 아직 초록이다(§8-6).
- **전체**: 19:32:48~19:43:59, HEAD `5625ed4` 고정. **2,358 passed · 4 xfailed · 0 failed**(668.6초).
  - xfailed 목록: `test_feat1_qa_adversarial` 2 · `test_feat2_qa_adversarial` 1 · `test_ops4_qa_r2::test_known_gap_disabled_and_no_next_run…` 1 — qa r2 와 같다.
  - UX-9 Playwright 타이밍 테스트는 이번에 통과했다(재실행 필요 없었음).
  - **수 맞추기**: qa r2 최종은 2,332 + 4 = 2,336 이다. 신규 26 을 더하면 2,362 = 2,358 + 4 다. 줄어든 테스트는 없다.

## 7. 명세 — frontend(`-75`)·qa(`-76`)가 읽는다

**웹 API(`web/`)·템플릿 dict 키·DB 스키마는 바뀌지 않았다.** 바뀐 것은 사내 대시보드 JSON(`/api/state`, 그리고 같은 `build_state` 를 굽는 ops 스냅샷 JSON의 `state`)이다.

### 7-1. `schedule[]` 행 + `verdict`(새 키)

```jsonc
// 판정을 못 붙임(모름) — '정상'으로 그리지 말 것. 사유는 problems[] 에 있다
"verdict": null

// 순환계 schedule_verdict 결과 그대로 — 결재함 '예약 작업 경보'와 같은 함수·같은 글자
"verdict": {"broken": true,  "label": "꺼짐(Disabled)"}
"verdict": {"broken": true,  "label": "다음 실행 없음"}
"verdict": {"broken": true,  "label": "실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음"}
"verdict": {"broken": true,  "label": "실패 · 결과 1(0x00000001)"}
"verdict": {"broken": true,  "label": "실행된 적 없음 · 예정도 없음"}
"verdict": {"broken": false, "label": "아직 때가 안 됨"}   // 한 번도 안 돌았고 다음 실행 있음
"verdict": {"broken": false, "label": "실행 중"}
"verdict": {"broken": false, "label": "정상"}
```

행 전체 예(꺼진 작업):

```json
{"name": "x-disabled", "status": "Disabled", "running": false, "last_run": "2026-10-25 10:05",
 "last_result": "0", "next_run": "", "enabled": false, "never_ran": false, "ok": true,
 "period_s": 86400, "first_start": "", "registered": "", "trigger_error": "",
 "verdict": {"broken": true, "label": "꺼짐(Disabled)"},
 "silence": {"bad": false, "label": "", "since": "", "limit_h": 0, "cls": "", "warn": ""}}
```

- **`verdict.broken` 과 `silence.bad` 는 한 행에서 함께 참일 수 없다.** 고장 행의 `silence` 는 늘 `SILENCE_NONE` 이다(위 예의 값 — r3 에서 바뀐 점. r2 에서는 고장 행에도 `cls`·`limit_h`·`warn` 이 실릴 수 있었다).
- **라벨 글자의 원천**: `verdict.label` 은 결재함 목적 줄 ` — ` 뒤 라벨과 같은 글자다(조용한 누락 행에서는 `silence.label`).
- **`verdict` 키 이름이 겹친다**: 에이전트 행(`departments[].members[].verdict` — 문자열, 활용 판정)과 이름이 같지만 **다른 객체**다.
- **칩 판정 순서 권고**(결정은 frontend):
  - ① `never_ran && !next_run` → 빨강 — `verdict.label` 이 '실행된 적 없음 · 예정도 없음'
  - ② `!never_ran && !ok` → 빨강 실패
  - ③ `verdict.broken` → 빨강 — 여기에 남는 것은 **꺼짐·다음 실행 없음뿐**이다. 이 행이 KPI `sched_stopped` 다.
  - ④ `silence.bad` → 주황
  - ⑤ 나머지 기존 분기
  - `verdict === null` 이면 이 행이 고장인지 모른다. 초록 '정상'으로 그리지 않는다('확인 불가'와 같은 원칙).
- **꺼짐 + 실패 행**(State Disabled, 결과 ≠ 0 — 예: 오너가 죽은 터널을 끈 경우):
  - `verdict.label` 은 '꺼짐(Disabled)'이다(결재함도 이 글자다). KPI 는 기존 뜻대로 `sched_bad` 에 센다(두 번 세지 않는다).
  - 칩을 ② '실패 · 결과 N' 으로 그리면 타일('1개 실패')과 맞지만 결재함 글자와 다르다. `verdict.label` 로 그리면 결재함과 맞지만 타일과 다르다.
  - 드문 경우다. 어느 쪽을 택할지 frontend 가 정해 적어 달라.
- **칩 머리/사유 나누기**: 조용한 누락처럼 ` · ` 로 머리·사유를 나누면 칩 + 사유가 결재함 라벨과 글자까지 같아진다(예: 머리 '실패', 사유 '결과 3221225477(0xC0000005) · 다음 실행 없음'). 선택이다.

### 7-2. `kpi` — 새 키 `sched_stopped`

```jsonc
"kpi": {
  "sched_total": 9,
  "sched_never": 0,      // 실행된 적 없음 · 예정도 없음 — 뜻 그대로
  "sched_pending": 2,    // 첫 실행 대기(첫 실행 없음 판정은 뺀다) — 뜻 그대로
  "sched_bad": 1,        // 실패(결과 ≠ 0, 한 번이라도 돈 작업) — 뜻 그대로. 꺼짐 + 실패 행도 여기
  "sched_silent": 0,     // 조용히 안 돎 + 첫 실행 없음 — 뜻 그대로. 판정 못 함 → null
  "sched_stopped": 0,    // ★ 새 키 — 꺼짐(Disabled)·다음 실행 없음. 결과는 0 인데 다시 돌지 않는다.
                         //   = verdict.broken 인데 never·bad·silent 어디에도 들지 않는 행. 한 행이라도 verdict 가 null 이면 null(0 이 아니다)
  "sched_alarm": 1       // 볼 것 = never + bad + silent + stopped(r3 에서 stopped 를 더함). 넷은 서로 겹치지 않는다.
                         //   = 순환계가 '예약 작업 경보'로 보는 작업(고장 또는 조용한 누락) 가운데 목록에 있는 것의 수
}
```

- **타일 권고**: `sched_stopped > 0` 이면 빨강(고장)이다. 부제는 행의 `verdict.label` 별로 세면 표 글자와 맞는다(예: '1개 꺼짐(Disabled)'·'1개 다음 실행 없음'). `sched_stopped == null` 이면서 볼 것이 달리 없으면 '확인 불가'(mute)다.
- **`problems[]` 에 새로 들어갈 수 있는 문장**:
  - `예약 작업 고장 판정을 싣지 못했다: …`
  - `` 예약 작업 `…` 행에 판정 칸(…)이 없다 — 고장 판정을 싣지 않음 ``
  - `` 예약 작업 `…` 의 고장 판정이 실패했다(…) — 싣지 않음 ``
- **줄어드는 문장**: 고장 행의 트리거 경고는 더 나오지 않는다(§1-2 ⓐ — 스탠드업과 같아짐).

### 7-3. 순환계·도구 함수(qa 참고)

| 어디 | 전 | 후 |
|---|---|---|
| `org_runtime.SCHEDULE_FIELDS` | — | 새 상수(판정이 읽는 칸 6개) |
| `org_runtime.SILENCE_NONE` | `silence_verdict` 안의 지역 값 | 모듈 상수 |
| `org_runtime.judge_task` | — | 새 함수 → (verdict, silence). `task_eval`·`silence_rows` 가 거친다 |
| `Org.silence_rows` 결과 | 고장 행에도 조용한 누락 판정 | 고장 행은 `SILENCE_NONE` |
| `Org.task_eval` 한 줄 | … | + `quiet`·`never_ran`·`registered`(목적 줄용) |
| `org_runtime.task_purpose` · `clip_line` · `PURPOSE_CLIP` | — | 새 이름 |
| `Org.board` 의 `purpose` | `[:140]` | `clip_line` |
| task 지시서 목적 첫 줄 | `… — {라벨} · **N시간째**(마지막 실행 … · 다음 실행 …)` | §3 표 |
| `agent_dashboard.attach_verdict` | — | 새 함수 |
| `agent_dashboard.schedule_counts` | … | + `sched_stopped`, `sched_alarm` 에 합침 |

## 8. Steward 가 볼 것 · 남은 것

1. **작업 트리 변경이 매분 서버로 나간다**(확인된 사실 — 로컬 근거. 내가 실행한 것은 아니다).
   - 19:30:48 로컬 스냅샷 JSON 에 `verdict`·`sched_stopped` 가 이미 들어 있다.
   - `%LOCALAPPDATA%\naechaget\snapshot.log` 에 19:27~19:31 매분 `published` 가 있다.
   - 새 필드는 작업 이름·판정 라벨뿐이다. 개인정보는 없다.
   - r2(§9-1)·qa r2(§4)가 짚은 경로와 같다. "배포 금지" 회차에도 대시보드 코드가 사실상 1분 안에 비밀 주소에 반영된다. 운영 판단 거리다.
2. **스탠드업 '경보 → 티켓' 줄**(`alert_lines`)에는 여전히 `· {hours}시간째 ·` 가 있다. 결재함 목적 줄과 같은 '주어 없는 수'다. 이번 지시서 범위(결재함 목적 줄) 밖이라 두었다. 같은 방식으로 고칠지 정해 달라.
3. **다른 글자 수 자르기 두 곳**도 같은 결함 유형이다(범위 밖이라 두었다):
   - 스탠드업 디스패치 목록 `o['purpose'][:90]`
   - 피드 `order.created` 의 `note=…[:80]`(버스에 기록돼 대시보드 피드에 보인다)
   - `clip_line(…, 90/80)` 한 줄씩이면 된다.
4. **피드 문구 조사**(design r2 메모 5): `workflow {workflow} 가 {result} 를 받는다` 의 '를'. 범위 밖이라 두었다.
5. **큰 시간 수**: 목적 줄은 지시서 규격대로 '시간'이다. 오래된 고장은 '292시간'·'1012시간'처럼 커진다. 일 단위로 바꿀지는 design 판단이다.
6. **QA-OPS4-4 strict xfail 은 아직 XFAIL 이다.**
   - 표 칩은 `agent_dashboard.html` 의 `schedState` 가 그리고, 이번 회차에서는 손대지 않았다.
   - frontend `-75` 가 `verdict` 를 따르면 XPASS(strict) 빨간불이 되고, qa `-76` 이 표식을 뗀다.
   - 백엔드 쪽 틈(수·판정 싣기)은 닫혔다. '표 초록 · 결재함 경보'는 화면을 바꿔야 사라진다 — OPS-4 를 '완료'로 닫는 조건은 `-75`·`-76` 뒤다.
7. **보고서 경로**: 지시서 `output` 칸은 `reports/2026-09-27-backend-engineer-OPS-4-r3.md` 인데, 워크플로 지시(`ops4-<자리>-r3`)대로 이 파일에 썼다. 순환계는 머리말 `order:` 로 지시서를 닫으므로 동작에는 차이가 없다(코드 근거).

## 9. 확인된 사실 · 추정 · 미검증

- **확인된 사실**(코드·테스트·실측으로 재현):
  - 두 읽기가 같은 함수·같은 칸·같은 뜻이라는 것(§1-1), 판정 순서 차이와 그 맞춤(§1-2)
  - verdict 싣기·None 경로·KPI 수(테스트 26 · 변이 13/13)
  - 목적 줄 아홉 모양(글자까지), 열린 지시서 파일 무변경
  - 운영 결재함 21장 중 4장 자르기 결과(읽기만)
  - 운영 스냅샷 JSON 의 실제 9행 verdict, 로컬 snapshot.log 의 `published`
  - 스위트 수·xfail 목록, 입력 md5 시작 = 끝, 운영 `data/`·`orders/` 무쓰기
- **추정**:
  - 스냅샷이 실제로 서버에 올라갔다는 것 — 근거는 로컬 로그뿐이다.
  - 두 읽기의 시점 차이로 판정이 다를 수 있다는 것(§1-3) — 재현하지 않았다.
  - 대시보드 결재함 화면에서 새 목적 줄이 한 줄로 온전히 보인다는 것 — 글자 수 계산만 했고 화면은 찍지 않았다.
- **미검증**:
  - 결재함·표 화면 캡처(이 자리는 html 을 바꾸지 않았다 — qa `-76`·design `-77` 몫)
  - alert·routine 사유의 실데이터 자르기(지금 열린 것 중 한도를 넘는 것이 없다 — 픽스처로만)
  - 20:05 매시 스캔이 새 코드로 도는 것. 설치는 19:21 이고, 그 뒤 매시 스캔은 아직 없었다. 같은 코드 경로를 tmp 루트 `scan()` 으로 테스트했고, 운영 스냅샷은 새 코드로 돌았다.
