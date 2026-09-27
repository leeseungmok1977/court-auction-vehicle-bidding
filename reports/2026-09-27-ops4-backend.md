---
order: 2026-09-27-65
from: backend-engineer
ticket: OPS-4
result: done
verified: 재현
workflow: ops4-followups
handoff: []
---

# OPS-4 ①②③: 조용히 안 도는 예약 작업 · `workflow: 없음` · 월간 운영 절 (backend-engineer, 2026-09-27)

> 입력: 지시서 `2026-09-27-65`, `reports/2026-09-27-ops3-qa.md`(QA-OPS3-4 · §2 ④ 관찰), `reports/2026-09-27-ops3-backend-r2.md` §6, `reports/2026-09-27-ops3-qa-r2.md` §4.
> `workflow: ops4-followups` 는 지시서가 적으라고 한 워크플로 이름이다. `result: done`·`handoff: []` 이므로 새 지시서는 생기지 않는다.
> 이 보고서는 **파일로 쓰지 못했다.** 하네스가 이 자리의 보고서 파일 쓰기를 막았다. 지시서의 대체 규칙에 따라 전문을 그대로 돌려준다. Steward 가 `reports/2026-09-27-ops4-backend.md` 로 옮기면 머리말의 `order:` 로 `-65` 가 닫힌다.
> 순환계는 파일 이름이 아니라 `order:` 로 지시서를 닫는다(`scan` 의 `parent = orders.get(str(meta.get("order") …))`). 그래서 지시서 파일의 `output` 칸(`reports/2026-09-27-backend-engineer-OPS-4.md`)과 경로가 달라도 닫힌다.

## [요약]

세 가지를 모두 구현했고 테스트로 고정했다. 전체 스위트는 **2,204 passed · 4 xfailed · 0 failed** 다.

- **①** 예약 작업의 주기를 **트리거에서 읽는다**(`Export-ScheduledTask` XML).
  - 가장 짧은 주기가 하루 이하면 매일(한도 36시간), 7일 이하면 매주(8일), 31일 이하면 매월(35일)로 나눈다.
  - 마지막 성공이 한도를 넘으면 다음 실행이 잡혀 있어도 '조용히 안 돎'이다.
  - 한 번도 안 돈 작업은 등록 후 한도가 지나기 전에는 보지 않는다.
  - 한도 값은 계약 §1 에 새로 둔 3줄에서 읽는다.
  - QA-OPS3-4 strict xfail 은 XPASS 를 확인한 뒤 표식을 지웠다.
- **②** `workflow:` 값이 비었거나 `없음`·`none`·`-`·`no` 면 워크플로로 보지 않는다.
  - 새로 찾은 것: 따옴표 없는 `workflow: -` 는 YAML 문법 오류다. 그래서 머리말 **전체**가 깨져 인계가 통째로 사라지고 있었다. 이제 그 한 줄만 비우고 다시 읽는다.
- **③** 운영·공급 절의 구현을 `tools/ops_digest.py` 하나로 옮겼고, 주간과 월간이 같이 쓴다.
  - 주간 출력은 **글자까지 같다**(W38·W39 대조).
  - 월간 9월 렌더의 수치는 원문 표를 따로 센 값과 전부 일치했다.
- **이 PC 실제 상태 dry-run**: 새 지시서 0건 · 경고 0건 · 쓴 파일 없음. 지금 잡히는 조용한 작업은 **없다.** db-backup-pull 과 monthly-report 는 첫 실행 전이고 한도 전이다.
- **라이브**: 16:05:02 매시 스캔이 새 코드로 오류 없이 돌았다. 결과는 `task_seen` 9개 기록, 새 지시서 0건이다.
- **Steward 가 볼 것 2건**(§2-4):
  - ⑴ 이 규칙을 만든 이유인 `naechaget-db-backup-pull` 은 §3.1 티켓이 `AUD-08`(열림)이다. 그래서 조용히 빠져도 **지시서가 생기지 않는다.**
  - ⑵ 월간 작업은 `StartWhenAvailable=False` 다. 10-01 13:30 에 PC 가 꺼져 있으면 첫 실행이 빠지고, 이 규칙이 그것을 잡는 것은 10-27 20:47 이다.
- **스키마**: 웹 API·템플릿 dict 키·DB 는 바뀌지 않았다. 사내 형식만 바뀌었다(§6).

## 1. 바꾼 파일

| 파일 | 무엇 |
|---|---|
| `tools/agent_dashboard.py` | `read_schedule` 의 PowerShell 이 트리거 XML(`Export-ScheduledTask`)과 등록 날짜(`$t.Date`)를 함께 읽는다. 순수 함수 `trigger_period`·`_iso_duration`·`local_minutes`·`_max_gap` 를 새로 두었다. 행에 `period_s`·`first_start`·`registered`·`trigger_error` 가 붙는다. 읽기만 한다 |
| `tools/org_runtime.py` | `silence_verdict`(Steward 결정 규칙)와 `SILENCE_CLASSES` 를 새로 두었다. `task_eval` 이 고장이 아닌 작업에 이 판정을 더하고, 처음 본 시각을 상태 파일 `task_seen` 에 적는다. `workflow_of`·`NO_WORKFLOW` 도 새로 두었다. `split_front` 는 YAML 오류가 나면 `workflow: -` 한 줄만 비우고 다시 읽는다 |
| `tools/ops_digest.py` (신규) | 운영·공급 절의 **유일한 구현**이다: `collect_ops`·`ops_stats`·`ops_section(period=, scrub=, compact=)`·`panel_line`·`days_text`·`ticket_md` |
| `tools/weekly_report.py` | 운영 절 구현 119줄을 지웠다. `ops_digest` 를 부르는 얇은 함수만 남았고, 이름과 서명은 그대로다 |
| `tools/monthly_report.py` | `## 운영·공급` 절을 맨 앞에 두고 `collect_ops`·`build_markdown(…, ops=None)` 을 더했다. 품질 절에는 패널 정기 실행 줄을 넣었다(A-05 처방). 콘솔 교체(`_wrap_console`)는 진입점으로 옮겼다 |
| `docs/org-contracts.md` | §1 에 설정 3줄을 더했다: `성공 없음 한도 · 매일(시간)` 36 · `성공 없음 한도 · 매주(일)` 8 · `성공 없음 한도 · 매월(일)` 35. §3 표에서는 예약 작업 행(판정 이름 2개 추가)·키 설명·handoff 행 괄호를 고쳤다. §3 규칙 문단의 '결정 대기'를 결정 내용으로 바꿨다 |
| `.claude/agents/_handoff-protocol.md` | `workflow:` 절에 한 줄을 더했다 |
| `tests/test_ops3_qa_adversarial.py` | QA-OPS3-4 strict xfail 표식을 지웠다(단언은 그대로). 도우미 `_task` 는 새 행 모양을 따른다. `REAL_0927` 에는 오늘 읽은 트리거 값을 채웠다(§5) |
| `tests/test_ops4_followups.py` (신규) | 78건(§5) |

- `web/`·`src/`·DB 는 건드리지 않았다.
- 같은 작업 트리에 다른 담당의 변경이 있다. 나는 손대지 않았다:
  - OPS-4 ④ 프런트: `tools/agent_dashboard.html`·`tests/test_ops4_dashboard_labels.py`·`reports/2026-09-27-ops4-frontend.md`
  - UX-9: `web/templates/vehicles.html`·`tests/test_ux9_*`
- 작업 중 HEAD 가 `c202dfe` → `e772962`(Steward 의 백로그 docs 커밋)로 움직였다. 내 파일과 겹치지 않는다.

## 2. ① 조용히 안 도는 예약 작업

### 2-1. 규칙: Steward 결정을 코드로

- `silence_verdict(t, now, settings, seen)` 은 `schedule_verdict` 가 고장이 아니라고 본 작업에만 적용된다. 고장 판정(대시보드와 같은 규칙 + 대시보드에 없는 규칙 둘)과 24시간 대기는 그대로다.
- **주기**: 행의 `period_s` 를 쓴다(트리거에서 읽은 값).
  - 경계인 하루·7일·31일은 '매일·매주·매월'이라는 말의 뜻이라 코드(`SILENCE_CLASSES`)에 둔다. 한도 **값**은 계약 §1 에서 읽는다.
  - 작업 이름별 주기는 코드에도 문서에도 없다. 테스트 `test_no_task_name_carries_a_hardcoded_period` 가 이것을 고정한다.
- **판정**:
  - **돈 적이 있고, 결과가 0 이고, 다음 실행이 잡혀 있는 작업**: 마지막 실행이 곧 마지막 성공이다. 한도를 넘으면 라벨은 `조용히 안 돎 · 마지막 성공 MM-DD HH:MM · 매일 작업 한도 36시간 넘김` 이다. **다음 실행이 잡혀 있어도** 그렇다.
  - **한 번도 안 돈 작업(267011)이고 다음 실행이 잡혀 있을 때**:
    - 기준 시각은 등록 날짜와 첫 트리거 시작 중 늦은 쪽이다.
    - 등록 날짜가 비어 있으면(이 PC 9개 중 7개) 순환계가 처음 본 시각을 쓴다(`task_seen`).
    - 한도를 넘으면 라벨은 `첫 실행 없음 · 등록 MM-DD HH:MM 뒤 … 넘김` 이다.
  - **이 판정이 보지 않는 것**: 실행 중·꺼짐·실패·다음 실행 없음.
    - 실행 중은 정상이고, 꺼짐은 이미 고장으로 판정된다.
    - 실패와 다음 실행 없음은 `schedule_verdict` 가 본다. 두 번 세지 않는다.
  - **규칙 밖**: 주기가 없는 작업(부팅 트리거 — 터널)과 주기가 31일을 넘는 작업.
  - **판정하지 않고 경고만 하는 경우**(스탠드업 '읽지 못한 것'):
    - 트리거를 못 읽은 작업.
    - §1 에 한도 줄이 없을 때 — 코드가 한도를 지어내지 않는다.
- **스캔**:
  - 고장 시작은 마지막 성공 시각(첫 실행 전이면 기준 시각)이다. 키는 `task:<작업>:<그 시각>` 이다.
  - 이 판정은 한도를 이미 품고 있다. 그래서 `예약 작업 실패 지속(시간)` 24시간을 **더 기다리지 않는다**(`need_hours` = 한도).
  - 열린 티켓이 있으면 `ticket-open` 이다(기존 규칙 유지).
  - 지시서를 닫아도 같은 구간에서는 다시 만들지 않는다(`done-before`). 작업이 다시 돌았다가 또 빠지면 새 구간이다.

### 2-2. 트리거 읽기(`agent_dashboard.read_schedule`)

- PowerShell 에 `Export-ScheduledTask`(XML)와 `$t.Date` 를 더했다.
  - XML 요소 이름은 언어와 무관하다. 09-23 에 CSV 헤더가 UI 언어로 나온 함정을 피한다.
  - 트리거를 못 읽어도 작업 목록은 그대로 내고, `TriggerError` 에 사유만 싣는다.
- 비용(확인된 사실, 이 PC 작업 9개): 3.22초 → 4.70초. 타임아웃은 90초다.
- 이 PC 실측(09-27 15:2x, 읽기만):

| 작업 | 트리거 | `period_s` | 첫 트리거 시작 | 등록 날짜 | 분류 |
|---|---|---|---|---|---|
| NaechaGet-PhotoClassify | 매주 일요일 | 604800 | 09-06 08:17 | 없음 | 매주 8일 |
| naechaget-daily-report | 매일 | 86400 | 09-16 12:00 | 없음 | 매일 36시간 |
| naechaget-db-backup-pull | 매일 | 86400 | 09-27 09:10 | 없음 | 매일 36시간 |
| naechaget-home-tunnel | 부팅 | 없음 | — | 없음 | 규칙 밖 |
| naechaget-monthly-report | 매월 1일(12달) | 2678400 | 09-22 13:30 | 09-22 20:47 | 매월 35일 |
| naechaget-ops-snapshot | 1분 반복 | 60 | 09-23 08:36 | 없음 | 매일 36시간 |
| naechaget-org-heartbeat | 1시간 반복 | 3600 | 09-27 00:05 | 없음 | 매일 36시간 |
| naechaget-org-standup | 매일 | 86400 | 09-27 08:45 | 없음 | 매일 36시간 |
| naechaget-weekly-report | 매주 토요일 | 604800 | 09-22 13:00 | 09-22 20:47 | 매주 8일 |

### 2-3. 이 PC 실제 상태 dry-run

- `python tools/org_runtime.py scan --dry-run` 을 두 번 돌렸다(15:31, 15:39).
  - 결과: `would_create []` · `would_close []` · `warnings []`.
  - tasks 는 터널 한 줄뿐이다: 실패 0xC0000005 · 다음 실행 없음 · 274시간 · `ticket-open`(AUD-05). 전과 같다.
- 아무것도 쓰지 않았다: `data/org-state.json` md5 `a6ff9386…` 와 `data/org-bus.jsonl` md5 `8c616463…` 가 전후 같았고, `orders/` 도 69개로 같았다.
- **지금 잡히는 조용한 작업은 0건이다.** db-backup-pull(첫 실행 09-28 09:10)과 monthly-report(첫 실행 10-01 13:30)는 첫 실행 전이고 등록 후 한도도 지나지 않았다.
- **라이브(확인된 사실)**: 16:05:02 매시 스캔이 새 코드로 돌았다.
  - 상태 파일에 `task_seen` 9개가 16:05:02 로 적혔다.
  - `task_bad` 는 터널 하나로 그대로다.
  - 버스에는 `scan · new 0 · closed 1` 이 남았다(프런트 보고서가 `-66` 을 닫았다).
  - `orders/` 는 69개로 그대로다.

**시간을 옮긴 시뮬레이션**(일회성 스크립트이고 테스트가 아니다):

- 15:3x 에 읽은 목록을 고정하고, 그 뒤로 아무 작업도 돌지 않았다고 가정했다.
- 처음 본 시각은 16:05 로 두었다. 실제 라이브 값과 같다.
- 결과:

| 시각 | 새로 잡히는 것 | 행동 |
|---|---|---|
| 09-28 12:00 | 없음 | — |
| 09-29 04:04 | daily-report(40시간) · org-standup(43시간) · org-heartbeat(36시간) | steward 에게 지시서(티켓 없음) |
| 09-29 04:05 | + db-backup-pull `첫 실행 없음 · 등록 09-27 16:05 뒤` | **ticket-open(AUD-08) — 지시서 없음** |
| 09-29 05:00(목록을 다시 읽음) | + ops-snapshot(37시간) | 지시서 |
| 10-04 13:00 | + weekly-report(마지막 성공 09-26 13:00 · 8일) | ticket-open(AUD-15) |
| 10-05 08:17 이후 | + PhotoClassify(8일) | ticket-open(AUD-15) |
| 10-27 20:47 | + monthly-report `첫 실행 없음 · 등록 09-22 20:47 뒤 · 35일` | ticket-open(AUD-15) |

- 실제로는 heartbeat 가 자기 스캔을 도는 동안 '실행 중'이다. 그래서 heartbeat 는 자기 자신을 잡지 않는다. heartbeat 가 멈추면 08:45 standup 의 스캔이 잡는다. 시뮬레이션에서 잡힌 것처럼 나온 것은 목록을 고정했기 때문이다.
- 첫 시뮬레이션에서는 ops-snapshot 이 빠졌다. 목록을 읽은 순간 실행 중이었기 때문이다(1분마다 도는 작업). Ready 상태로 다시 읽은 목록에서는 잡혔다. 테스트도 60초 주기를 따로 고정했다.

### 2-4. Steward 가 볼 것

1. **이 규칙을 만든 이유인 작업이 지금 티켓 뒤에 숨는다**(확인된 사실).
   - §3.1 `naechaget-db-backup-pull` 의 티켓 칸은 `AUD-08` 이다.
   - 백로그 상태 '백업 완료(2026-09-27) · 헬스체크 남음' 을 `ticket_is_open` 은 **열림**으로 읽는다.
   - 그래서 내려받기가 조용히 빠져도 `ticket-open` 이 된다. 스탠드업 줄에만 나오고 지시서는 생기지 않는다.
   - 판단: AUD-08 에 남은 일은 헬스체크로, 다른 주제다. §3.1 스스로의 규칙('다른 주제의 티켓을 적지 않는다 — 진짜 고장이 그 티켓 뒤에 숨는다')에 비추면 칸을 `-` 로 비우는 것이 맞다고 본다.
   - 주간·월간·사진 분류는 `AUD-15`(열림, todo(낮음))가 바로 그 따라잡기 문제다. 그래서 기존 규칙대로 두는 것이 맞다.
   - **§3.1 은 고치지 않았다.** 표의 티켓은 Steward 가 정한다.
2. **10-01 첫 월간 보고가 빠질 위험.**
   - 월간 작업의 설정은 `StartWhenAvailable=False` 다(확인된 사실, 읽기만). 10-01 13:30 에 PC 가 꺼져 있으면 따라잡지 않는다(AUD-15).
   - 이 규칙이 그것을 잡는 것은 등록(09-22 20:47) + 35일 = **10-27 20:47** 이다. 그때도 AUD-15 가 열려 있으면 스탠드업 줄뿐이다.
   - 코드(③)는 준비됐다. Steward 가 정해 둘 일은 둘 중 하나다:
     - 10-01 13:30 에 PC 가 켜져 있게 한다.
     - 빠지면 오너 세션에서 `python tools/monthly_report.py` 를 한 번 돌린다(서버 접속이 필요하다).
3. **대가**(판단):
   - PC 를 36시간 넘게 껐다 켜면, 스캔이 매일 작업의 따라잡기(`StartWhenAvailable=True`)보다 먼저 돌 수 있다. 그러면 지시서가 한 장 생긴다.
   - 따라잡은 뒤에는 판정이 풀린다. Steward 가 지시서를 '의도된 상태'로 닫으면 된다.
   - 계약 §3 에 적었다.

## 3. ② `workflow:` 값이 '없음'이면 워크플로가 아니다

- `workflow_of(meta)`:
  - 값이 None·False·빈 값이거나 `없음`·`none`·`-`·`—`·`no`·`null`·`n/a`·`false`(대소문자 무시)면 `''` 를 돌려준다.
  - 스캔의 워크플로 판정이 이 함수를 쓴다. 인계와 반려(`result: fail` → pm)가 정상 처리된다.
- **새로 찾은 것**(확인된 사실): 따옴표 없는 `workflow: -` 를 PyYAML 이 `sequence entries are not allowed here` 로 거부한다.
  - 전에는 이 때문에 머리말 **전체**가 깨진 것(`__broken__`)으로 읽혔다. `handoff`·`result` 가 통째로 무시되고 경고 한 줄만 남았다.
  - 이제 `split_front` 는 YAML 오류가 나면 **`workflow: -` 한 줄만** `workflow: ''` 로 바꿔 한 번 더 읽는다.
  - 다른 줄의 오류(예: `ticket: -`)는 그대로 '깨짐'이다. 테스트로 고정했다.
- 전에도 괜찮았던 값: PyYAML 은 따옴표 없는 `no`·`false`·`~`·`null` 을 원래 거짓·없음으로 읽는다.
- 이번에 새로 막은 것: 문자열로 남는 값(`없음`·`none`·`None`·`'-'`·`'no'`)과 따옴표 없는 `-`.
- 문서: `_handoff-protocol.md` `workflow:` 절에 한 줄, 계약 §3 handoff 행에 괄호 한 줄을 더했다.

## 4. ③ 월간 보고 운영 절

- **공용 모듈**: `tools/ops_digest.py` 가 유일한 구현이다.
  - `weekly_report.py` 에는 같은 이름·서명의 얇은 함수만 남았다.
  - 복붙은 없다. 테스트가 두 파일에 `def ops_stats` 와 표 머리가 없는지 본다.
- **주간 출력은 바뀌지 않았다**(확인된 사실).
  - 옮기기 전 모듈(백업 사본)과 새 모듈로 W38·W39 `build_markdown` 을 각각 만들어 비교했다. 생성 시각 줄을 빼면 글자까지 같다.
  - 빈 입력·오류·None 세 경우의 `ops_section`·`panel_line` 출력도 같다.
- **월간**(`monthly_report.py`):
  - `## 운영·공급` 절을 **맨 앞**(고객 유입 앞)에 둔다. 주간과 같은 순서이고 이유도 같다: 공급이 멈춘 달의 제품 수치는 낡은 수치다.
  - 기간 이름은 '이 달'이다. 한 달이면 날짜 줄이 길어지므로 사흘 넘게 이어진 날은 `09-01~09-14` 로 접는다. 주간은 접지 않는다(전과 같다).
  - **품질 절**: 월간도 '전문가 패널 리포트 **N건**'으로 파일 수만 적어, W39 와 같은 구멍(A-05, 파일 수로 실패를 가림)이 있었다. 그래서 주간과 같은 `panel_line` 을 파일 목록 **앞**에 넣었다. 지시서 ③ 문언 밖이지만 같은 절의 같은 결함이라 함께 고쳤다.
  - **콘솔 교체**(`_wrap_console`)를 진입점으로 옮겼다. 모듈 맨 위에 있어서 import 만으로 호출자의 `sys.stdout` 을 갈아치우고 있었다. weekly 가 OPS-3 에서 받은 처방과 같다.
- **9월 렌더**(확인된 사실, 서버는 읽지 않음): 일일 리포트 13편(09-15~09-27)을 셌고, 리포트 없는 날은 09-01~09-14 다.
  - **공급**:
    - 케이카 교차검증 3일(09-24~09-26, KCAR-1 닫힘)
    - 물건 수집 1일(09-25)
    - 실행 기록 1일(09-25)
    - 시세 분석 1일(09-27, AUD-06 열림)
    - 신호마다 '확인 불가' 9일 — 공급 절이 생기기 전 리포트다.
  - **정기 작업**:
    - 매일 시세·낙찰 갱신: 실패 3회(09-15·09-17·09-25)
    - 집 회선 터널: 실패 5회(09-15·09-19~09-21·09-27)
    - 주간 전문가 패널: 실패 1회(09-26)
  - **품질**: `정기 실행(토 09:20, 일일 리포트 기준): 예정 2회 · 성공 0회 · 실패 1회(09-26) · 확인 불가 1회` 다음에 파일 7건이 온다.
  - **대조**: 공용 파서를 쓰지 않고 원문 표를 문자열로 잘라 따로 셌다. 신호·작업·날짜가 **전부 일치**했다. 테스트로도 고정했다(리포트가 7편 미만이면 skip).
- **10-01 13:30 첫 실행**: 09-01~09-30 을 센다. 09-28~09-30 리포트는 그때까지 생긴다.
- **진입점 확인**:
  - 두 스크립트가 다른 작업 폴더(`C:\`)에서도 `--help` 까지 import 되는 것을 확인했다. 스케줄러가 부르는 방식과 같다.
  - `main` 은 서버 ssh 가 있어 직접 돌리지 않았다. 대신 테스트가 서버·git 을 바꿔 끼운 채 `main(["2026-09", "--dry-run"])` 이 운영 절을 채우는지 본다.

## 5. 테스트

### 신규 `tests/test_ops4_followups.py` — 78건(파라미터 포함)

| 영역 | 내용 |
|---|---|
| 트리거 파싱 | 이 PC 실제 XML 6종 · 여러 요일 · 격주 · 분기 · 반복 겹침 · 꺼진 트리거 · 깨진 XML · 반복 간격 문자열 |
| `read_schedule` 행 모양 | 가짜 PowerShell 출력으로 확인 |
| 한도 경계 | 매일·매시·매분·매주·매월 각각 한도 정각이면 조용함, 1분 전이면 정상 |
| 규칙 밖 | 부팅 · 31일 초과 · 실행 중 · 옛 행 모양 · 실패 · 다음 실행 없음 |
| 경고 | 트리거를 못 읽음 · §1 한도 줄 없음 |
| 첫 실행 전 | 기준 시각이 등록 날짜 · 처음 본 시각 · 첫 트리거 시작 인 경우 |
| 스캔 | 지시서 1건 · 키 · 멱등 · 닫아도 다시 안 만듦 · 다시 돌았다 빠지면 새 구간 · 열린 티켓 · dry-run 은 안 씀 · 지워진 작업 정리 · 고장 규칙 우선 |
| 문서 ↔ 코드 | §1 키 글자 · §3 결정 문언 · 라벨 머리 |
| ② | 값 15종 · 실제 머리말 9종 · fail → pm · 진짜 id 는 여전히 건너뜀 · 따옴표 없는 `-` 는 그 줄만 비움 |
| ③ | import 부작용 없음 · 구현 하나 · 월간 수치·접기·순서 · 모름은 조용하지 않음 · 주간 문구 불변 · `days_text` · `main` 배선 · 9월 원문 대조 |

### `tests/test_ops3_qa_adversarial.py`

- QA-OPS3-4 strict xfail 을 먼저 돌려 **XPASS(strict) 빨간불을 확인**한 뒤 표식을 지웠다. **테스트 본문(단언)은 그대로다.**
- 바뀐 것은 도우미 `_task` 의 기본 행 모양이다. `read_schedule` 행이 이제 트리거 값을 싣기 때문이다(기본은 매일 작업). `REAL_0927` 에는 오늘 트리거 XML 에서 읽은 실측값을 채웠다.
- 숨기지 않고 적는다: 이 도우미 변경 없이는 XPASS 가 날 수 없다.
  - 결정은 '주기를 트리거에서 읽는다'이다.
  - 그래서 주기 정보가 없는 행은 **판정하지 않게** 만들었다. 옛 모양 행에서 헛경보를 내지 않기 위해서다.

### 공허 통과 점검 — 변이 17종 중 17종 빨간불

- 원본 파일은 건드리지 않았다. 사본 모듈을 `pytest -p` 로 먼저 올리는 방식이다. 원본 md5 는 전후가 같았다.
- 대상 파일: `test_ops4_followups.py` + `test_ops3_qa_adversarial.py`(113건).

| 변이 | 결과 |
|---|---|
| R1 조용함 판정 끔 | 5 failed |
| R2 등록 날짜 무시 | 2 failed |
| R3 마지막 성공을 고장 시작으로 안 씀 | 5 failed |
| R4 workflow 옛 해석 | 7 failed |
| R5 `workflow: -` 복구 없음 | 2 failed |
| R6 매주를 매일 한도로 | 2 failed |
| R7 트리거 오류 경고 없음 | 2 failed |
| R8 처음 본 시각 안 적음 | 2 failed |
| R9 첫 트리거 시작 무시 | 1 failed |
| R10 실행 중도 판정 | 1 failed |
| A1 반복 간격 무시 | 3 failed |
| A2 가장 긴 간격 대신 짧은 간격 | 1 failed |
| A3 꺼진 트리거도 셈 | 1 failed |
| O1 날짜 접기 안 함 | 5 failed |
| M1 월간 main 이 ops 를 안 넘김 | 1 failed |
| M2 월간 운영 절 없음 | 4 failed |
| M3 월간 품질이 패널 실패를 안 적음 | 1 failed |

### 전체 스위트

- 조건: `python -m pytest -q`, `NC_NO_SCHEDULER=1` `NC_NO_BACKGROUND=1`, HEAD `e772962` + 작업 트리, 15:40~15:54.
- 결과: **2,204 passed · 4 xfailed · 0 failed**(784.67초).
- **수 맞추기**(확인된 사실): qa-r2 기준은 2,104 passed + 4 xfailed = 2,108 이다.

| 변화 | passed | xfailed |
|---|---|---|
| qa-r2 기준 | 2,104 | 4 |
| `test_ops4_followups.py`(내 것) +78 | +78 | |
| 다른 담당 `test_ops4_dashboard_labels.py` +5 | +5 | |
| 다른 담당 `test_ux9_qa_adversarial.py` +17 | +16 | +1 |
| QA-OPS3-4 xfail → 통과 | +1 | −1 |
| **합계** | **2,204** | **4** |

  - 총 2,208건이다. 줄어든 테스트는 없다.
  - 남은 xfailed 4 = `test_feat1_qa_adversarial` 2 · `test_feat2_qa_adversarial` 1 · UX-9 QA 1.
- OPS 관련 묶음(ops4 두 파일 · ops3 세 파일 · org_runtime · no_visitor_tracking · ops_health): 252 passed.
- `tools/check_md_tables.py`: 바꾼 문서 2편에 이상 없음.

## 6. 형식 변경 명세 — 다른 자리가 반영할 것

**웹 API·템플릿 dict 키 변경 없음. DB 스키마 변경 없음.** `web/`·`src/` 는 바뀌지 않았다.

| 어디 | 전 | 후 | 읽는 쪽 |
|---|---|---|---|
| `agent_dashboard.read_schedule` 행(대시보드 JSON `schedule`) | name·status·running·last_run·last_result·next_run·enabled·never_ran·ok | + `period_s`(초, 주기 없으면 null) · `first_start`('YYYY-MM-DD HH:MM' 또는 '') · `registered`(같은 형식 또는 '') · `trigger_error`('' 또는 사유) | 순환계. 프런트는 아래 권고 참고 |
| `data/org-state.json` | … `task_bad` | + `task_seen` {작업: 처음 본 시각 ISO} | 순환계만. 없으면 빈 것으로 시작한다(하위호환). 지워진 작업은 정리한다 |
| `org_runtime.task_eval` 항목 | 라벨 5종 · `need_hours`=24 | + 라벨 `조용히 안 돎 · …`·`첫 실행 없음 · …`. 이 둘의 `need_hours` 는 한도(36·192·840) | 스탠드업 · `scan --dry-run` |
| `org_runtime` 공개 이름 | — | `silence_verdict` · `SILENCE_CLASSES` · `workflow_of` · `NO_WORKFLOW` | 테스트 |
| `split_front` | YAML 오류면 깨짐 | `workflow: -` 한 줄만 비우고 다시 읽는다(다른 오류는 깨짐) | 순환계 |
| 계약 §1 | — | `성공 없음 한도 · 매일(시간)` 36 · `성공 없음 한도 · 매주(일)` 8 · `성공 없음 한도 · 매월(일)` 35 | 순환계(`contracts()`) |
| 계약 §3 | 예약 작업 행 · 규칙 '결정 대기' | 행에 판정 이름 2종·키 설명을 더했다. 규칙 문단은 결정 내용(주기 출처·한도·첫 실행·열린 티켓·대가)으로 바꿨다. handoff 행에 괄호 한 줄 | 사람 |
| `weekly_report` | 운영 절 구현 | 같은 이름·서명으로 `ops_digest` 를 부른다 | 주간 작업·테스트 |
| `monthly_report` | 운영 절 없음 | `## 운영·공급`(맨 앞) · 품질 절 패널 정기 실행 줄 · `build_markdown(…, ops=None)` · `collect_ops` | 월간 작업(10-01 13:30) |

**frontend 권고**(OPS-4 ④ 후속): 대시보드 정기 작업 표는 아직 '조용히 안 돎'을 그리지 않는다.

- 이 판정은 §1 한도와 `task_seen` 이 필요하다. JS 로 다시 짜면 규칙이 두 벌이 된다.
- 하려면 backend 가 대시보드 JSON 에 `silence_verdict` 결과를 실어 주는 쪽을 권한다. 아직 구현하지 않았다.

## 7. 확인된 사실 · 추정 · 미검증

- **확인된 사실**:
  - dry-run, 16:05 라이브 스캔, 트리거 실측, 9월 렌더와 원문 대조, 주간 동일성, 스위트 수, 변이 점검. 조건은 각 절에 적었다.
  - 작업 스케줄러는 **읽기만** 했다(Get-ScheduledTask · Get-ScheduledTaskInfo · Export-ScheduledTask).
  - 서버 접속·외부 요청·커밋·배포·운영 DB 쓰기는 하지 않았다.
- **추정·판단**:
  - PC 를 36시간 넘게 껐다 켤 때 따라잡기와 스캔 중 어느 쪽이 먼저 도는지는 재 보지 않았다(§2-4 ③).
  - AUD-08 칸을 비우자는 것은 판단이다(§2-4 ①).
- **미검증**:
  - 등록 날짜가 비어 있고, 오래전에 등록됐는데 한 번도 안 돈 작업은 늦게 잡힌다. 처음 본 시각이 배포 시각이 되어 한도만큼 늦는다. 이 PC 에는 그런 작업이 없다(db-backup-pull 은 오늘 등록됐다).
  - 트리거 XML 을 못 읽는 권한 환경(다른 계정)은 재현하지 않았다. 가짜 출력으로만 경고 경로를 고정했다.
  - 새 형식 일일 리포트 전체 생성(ssh 필요)은 이번 범위 밖이다.
