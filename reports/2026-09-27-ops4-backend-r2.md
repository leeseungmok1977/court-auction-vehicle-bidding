---
order: 2026-09-27-69
from: backend-engineer
ticket: OPS-4
result: done
verified: 재현
workflow: ops4-r2
handoff: []
---

# OPS-4 수정 회차(r2) — workflow 주석 · 트리거 Duration/만료 · 대시보드에 조용한 누락 판정 · §3.1 티켓 칸 (backend-engineer, 2026-09-27)

> 입력: 지시서 `2026-09-27-69`, `reports/2026-09-27-ops4-qa.md`(QA-OPS4-1·2·3, §5), `reports/2026-09-27-ops4-design.md`(#1·#2), 1회차 `reports/2026-09-27-ops4-backend.md`.
> 기준: HEAD `e772962` + 작업 트리(1회차 미커밋 변경 위). 커밋·배포·서버 접속·외부 요청은 하지 않았다. 작업 스케줄러는 **읽기만** 했다.
> `workflow: ops4-r2` 이므로 순환계는 인계 지시서를 만들지 않는다. 다음 단계(frontend `-70`, qa `-71`, design `-72`)는 이미 발행돼 있다.

## [요약]

지시서의 ①~⑥을 모두 했다. 전체 스위트는 **2,306 passed · 3 xfailed · 1 failed**다. 실패 1건은 UX-9 Playwright 타이밍 테스트이고 이번 변경과 무관하다. 단독으로 3회 돌리면 3/3 통과한다(§7).

- **①** `workflow: -   # 주석` 이 이제 '워크플로 없음'이다(QA-OPS4-3).
- **②** 반복에 끝나는 `Duration` 이 있으면 반복 간격 대신 바깥 트리거 주기를 쓴다(QA-OPS4-1).
- **③** `EndBoundary` 가 지난 트리거는 주기와 첫 시작에서 뺀다(QA-OPS4-2).
  - ①②③의 strict xfail 3건은 **XPASS(strict) 빨간불을 확인한 뒤** 표식만 뗐다.
- **④** 대시보드 JSON 의 `schedule` 행마다 `silence` 를 싣는다. 값은 순환계 `silence_verdict` 결과 그대로다.
  - KPI 에 `sched_silent`·`sched_alarm` 을 더했다.
  - 판정 규칙은 `org_runtime` 한 곳에만 있다. 대시보드 소스에는 한도 이름도 분류표도 없다(테스트로 고정).
- **⑤** §3.1 네 행(db-backup-pull·weekly·monthly·PhotoClassify)의 티켓 칸을 `-` 로 바꾸고 Steward 문구를 적었다.
  - 따라잡기 적용 사실을 계약 §3·§3.1 과 `silence_verdict` docstring 에 반영했다.
  - 적용 사실은 이 PC 에서 **다시 읽어 확인했다**(16:51:17): 9개 모두 `StartWhenAvailable=True`·`DisallowStartIfOnBatteries=False`.
- **⑥** 스케줄러 목록을 '정기 작업'이라 부르던 곳을 '예약 작업'으로 고쳤다. 계약 2곳, `org_runtime` 3곳, `agent_dashboard.py` 3곳이다.
  - 스탠드업 문구는 '예약 작업 경보(고장·조용히 안 돎)'가 됐다.
- **§3.1 변경 뒤 이 PC 9개 작업**(시뮬레이션, §6):
  - 조용히 빠지면 지시서가 **4장 → 8장**이 된다.
  - 새로 지시서가 되는 넷: db-backup-pull(09-29 05:05) · weekly(10-04 13:05) · PhotoClassify(10-05 09:05) · monthly(10-27 21:05).
  - 지금 실제 dry-run 결과는 0건이다.
- **스키마**: 웹 API·템플릿 dict 키·DB 는 바뀌지 않았다. 바뀐 것은 사내 대시보드 JSON 과 순환계 반환 모양뿐이다(§8 명세 — frontend 가 반영).
- **Steward 가 볼 것 4건**(§9): 매분 스냅샷 파이프라인이 작업 트리 변경을 서버로 올린다 · 10-01 첫 월간 보고의 안전망 · 남은 어휘 두 곳 · 백로그 AUD-15 제목.

## 1. 바꾼 파일

| 파일 | 무엇 |
|---|---|
| `tools/org_runtime.py` | `_BARE_DASH_WORKFLOW` 정규식(①). `silence_verdict` 가 `cls` 를 더 내고, 규칙 안 작업이면 정상이어도 `cls`·`limit_h` 를 싣는다. docstring 에 따라잡기 적용 사실을 적었다. **새 메서드 `Org.silence_rows`**(읽기만). 주석·docstring·스탠드업 어휘(⑥) |
| `tools/agent_dashboard.py` | `trigger_period(xml, now=None)` — Duration(②)·EndBoundary(③). 새 함수 `_local_naive`·`attach_silence`·`schedule_counts`. `build_state` 가 `attach_silence` 를 부르고 KPI 는 `schedule_counts` 에서 나온다. 모듈 docstring 출처표(옛 `schtasks CSV` → 실제 PowerShell)와 절 머리·CLI 출력 어휘 |
| `docs/org-contracts.md` | §3.1 네 행(티켓 `-` · 비고). §3 규칙 문단: 어휘 정의 한 줄, 따라잡기 적용 사실, 조용한 누락은 그 일을 맡은 티켓만 적는다는 문장, 대시보드 포인터(`OPS-4 ④` → `silence_rows`·지시서 `-70`) |
| `.claude/agents/_handoff-protocol.md` | `workflow:` 절에 "값 뒤에 주석을 달아도 같다" 한 구절 |
| `tests/test_ops4_qa_adversarial.py`(qa 파일) | strict xfail 표식 3개만 뗐다. 단언은 그대로다 |
| `tests/test_ops4_followups.py`(1회차 내 파일) | `test_open_ticket_keeps_the_existing_rule` 이 실제 §3.1 의 weekly `AUD-15` 에 기대고 있었다. 임시 계약표의 그 한 칸만 `AUD-15` 로 되돌려 **규칙 자체**를 보게 했다 |
| `tests/test_ops4_r2_fixes.py`(신규) | 37건(§7) |

- 건드리지 않은 것:
  - `tools/agent_dashboard.html`(frontend `-70` 몫)
  - `web/templates/vehicles.html`·`tests/test_ux9_*`(다른 워크플로)
  - `web/`·`src/`·DB
- 매시 스캔 대비: 편집마다 메모리에서 `compile()` 을 통과한 뒤 임시 파일로 쓰고 교체했다(깨진 상태로 저장하지 않음). 이 방식을 쓰기 전 첫 편집 한 번은 `py_compile` 으로 확인했다. 그때 생긴 부산물 `__pycache__/org_runtime.py.cpython-312.pyc` 는 지웠다.

## 2. ① `workflow: -` 뒤 주석 (QA-OPS4-3)

- 정규식은 qa 제안 그대로다: `^workflow:[ \t]*-[ \t]*(#.*)?$`.
- 받는 형태(테스트 고정):
  - `workflow: -   # 워크플로 밖`
  - `workflow: -⇥# …`(탭 뒤 주석)
  - `workflow: - #`
  - `workflow:-  # …`
- 받지 않는 형태:
  - `- x`·`- x  # 주석`·`-- # 주석` 처럼 주석이 아닌 값이 붙은 경우.
  - 다른 줄의 `ticket: -  # 없음`. 여전히 머리말 **깨짐**이다. 고치는 것은 workflow 줄 하나뿐이다.
- **한계(확인된 사실)**: `workflow: -#x` 처럼 `#` 앞에 공백이 없으면 YAML 문법 오류가 아니라 **값 `-#x`** 다.
  - 그래서 정규식까지 오지 않고 워크플로로 취급된다.
  - 조용히 사라지지는 않는다 — 버스에 `handoff.skipped` 가 남는다(테스트 `test_dash_glued_to_hash_is_a_yaml_value_and_leaves_a_skip_record`).
  - 규약 예시는 `#` 앞에 공백을 둔다. 목록을 넓히지는 않았다.

## 3. ②③ 트리거 주기 (QA-OPS4-1 · QA-OPS4-2)

`agent_dashboard.trigger_period(xml, now=None)` 는 **살아 있는 트리거**만 센다. `now` 를 주지 않으면 읽는 순간이다(`read_schedule` 이 그렇게 부른다).

| 경우 | 전 | 후 |
|---|---|---|
| 매주 + 반복 PT1H · Duration PT3H | 3600(매일 36h → 월요일 헛경보) | **7일**(매주 8일) |
| 매주 + 반복 PT1H · Duration P6D | 3600 | 7일(하루 넘게 비는 날이 있다) |
| 매주 + 반복 PT1H · Duration P7D 이상 | 3600 | 3600(창이 다음 회차까지 이어진다) |
| 매일 + 반복 PT1H · Duration P1D(흔한 GUI 설정) | 3600 | 3600 |
| 반복 · Duration 없음 · 빈 요소 · `P0D` | 반복 간격 | 반복 간격(무기한) |
| 바깥 주기가 있는데 Duration 글자를 못 읽음(`P1W`) | 반복 간격 | 바깥 주기(짧게 잡으면 헛경보 쪽으로 틀린다) |
| 한 번 트리거 + 유한 반복(시작+기간이 지남) | 반복 간격 | **죽은 트리거**(주기 없음·첫 시작에서도 뺌) |
| 끝난 매일(EndBoundary 지남) + 살아 있는 매주 | 1일 | **7일**, 첫 시작도 매주 트리거 것 |
| EndBoundary(+09:00) 정각 | 셈 | 그 순간부터 뺀다(현지 시각으로 비교) |
| 트리거 전부 끝남 | — | 주기 None · 오류 아님(규칙 밖) |

- 이 PC 9개 실측 트리거의 결과는 전과 같다. qa `test_real_0927_triggers_all_nine` 9건이 통과했고, 17:09 에 실제로 다시 읽은 값도 같다(§6).
- 설계 판단: 끝난 트리거의 시작을 첫 시작에서 뺀 이유는 헛경보 방향 때문이다. 옛 트리거는 끝나고 새 트리거가 미래에 시작하는 작업을, 옛 시작 기준으로 '첫 실행 없음'이라 부르면 헛경보다.

## 4. ④ 대시보드 JSON 에 판정 싣기 — 규칙은 org_runtime 한 곳

- **`org_runtime.Org.silence_rows(sched, now=None, settings=None)`** → `{작업: silence_verdict 결과}`.
  - 읽기만 한다. 테스트로 상태 파일 md5 불변과 버스 미생성을 확인한다.
  - 처음 본 시각은 `task_seen` 에서 가져오고, 없으면 **지금**을 쓴다. `task_eval` 이 다음 스캔에서 그렇게 적으므로 같은 기준이다.
- **`agent_dashboard.attach_silence(sched, now=None)`**: 행마다 `silence` 에 위 결과를 **그대로** 넣는다.
  - 실패하면 `silence` 는 `None`(모름)이고, 사유는 `problems` 에 올라간다. '정상'으로 채우지 않는다.
  - 판정 경고(트리거를 못 읽음·§1 한도 없음)도 한 번씩 `problems` 로 올린다. 순환계 스탠드업 '읽지 못한 것'과 같은 문장이다.
- **`agent_dashboard.schedule_counts(sched)`**: KPI 의 예약 작업 수를 표와 같은 행에서 센다. 필드 뜻은 §8.
- **같은 판정인지**(테스트 `test_dashboard_and_runtime_give_the_same_verdict_on_the_same_rows`): 같은 행·같은 시각에서 비교했다.
  - 순환계 스캔이 '조용히 안 돎/첫 실행 없음'으로 본 작업과 라벨이 대시보드 `silence.bad` 행과 **글자까지 같다**.
- **단일 원천**(테스트 `test_the_rule_lives_only_in_org_runtime`):
  - `agent_dashboard.py` 에 `성공 없음 한도`·`SILENCE_CLASSES` 가 없다.
  - `attach_silence` 본문은 `silence_rows(` 를 부르고 시간 계산을 하지 않는다.
- **이 PC 실제 상태**(17:1x, `build_state()` 를 프로세스 안에서 한 번 부름):
  - 조건: 세션 캐시는 scratch 로 돌렸다. 운영 `data/` 3개 파일의 md5 는 전후가 같았다.
  - 결과: `sched_total 9 · never 0 · pending 2 · bad 1 · silent 0 · alarm 1`. 9행 모두 `silence` 가 있다(매일 5 · 매주 2 · 매월 1 · 규칙 밖 1). `problems` 에 판정 경고는 없다.

## 5. ⑤ Steward 결정 반영 · 문서가 옛 상태를 말하지 않게

- **§3.1 네 행**:
  - 티켓 칸은 `-`, 받는 자리는 `steward` 그대로다.
  - 비고에 `2026-09-27 Steward: 조용한 누락은 지시서로(열린 티켓이 다른 주제)` 를 적었다.
  - 순환계 해석(`alert_routes`)은 네 행 모두 `ticket ''` · `watch True` 다(확인).
- **따라잡기 적용 사실 — 재현**(읽기만, 16:51:17 `Get-ScheduledTask`):
  - 9개 모두 `StartWhenAvailable=True` · `DisallowStartIfOnBatteries=False` · `StopIfGoingOnBatteries=False` 다.
  - 로그온 방식은 **Interactive 7개, S4U 2개**(daily-report·home-tunnel)다.
  - 이 사실을 문서에 넣었다: Interactive 작업은 오너가 로그온해 있어야 돈다. 그래서 따라잡기는 "PC 가 켜지고 **오너가 로그온한 뒤**"다.
- **옛 상태를 말하던 문장 교체**:
  - 계약 §3 '따라잡기가 없어(AUD-15)' → 적용 사실 + 그래도 이 규칙이 필요한 이유(PC 가 켜져야 돈다 · Interactive).
  - §3.1 weekly 비고 '노트북 조건에서 건너뛰고 따라잡지 않는다' → '따라잡기 켬(…)'.
  - `silence_verdict` docstring 의 같은 서술.
  - 테스트 `test_documents_state_the_catch_up_as_applied` 가 옛 문장이 계약·코드에 없는지 본다.
- **계약 포인터**: "대시보드 정기 작업 표에는 이 판정이 아직 없다(OPS-4 ④)" 를 바꿨다.
  - 새 문장은 "대시보드는 이 판정을 다시 짜지 않고 `silence`·`sched_silent`·`sched_alarm` 으로 받는다 — 그리는 일은 frontend(지시서 `2026-09-27-70`)" 다.
  - qa §5-3 과 design #1 의 '맡은 곳 없음'은 backend 쪽이 끝났고, 화면 쪽은 `-70` 이다.

## 6. dry-run · 이 PC 실제 작업 9개

### 6-1. 지금(확인된 사실)

- **라이브 매시 스캔 17:05:02**: 새 코드와 새 §3.1 로 돌았다.
  - `scan exit=0` · `warnings []` · new 0 · closed 3(`-65`·`-67`·`-68`).
  - tasks 는 터널 한 줄(ticket-open AUD-05)이다. `task_bad` 는 전과 같다.
- **dry-run 17:08:23**: `org_runtime.py --root <scratch 사본> scan --dry-run`. 예약 작업 목록은 실제 스케줄러에서 읽었다.
  - 결과: `would_create []` · `would_close []` · `warnings []`. tasks 는 터널 한 줄이다.
  - 운영 `data/org-state.json`·`org-bus.jsonl` md5 가 전후 같았고, `orders/` 는 73 → 73 이다.

### 6-2. §3.1 변경 뒤 무엇이 지시서가 되나 — 시간 이동 시뮬레이션(일회성 스크립트, 테스트 아님)

- 조건:
  - 17:09:07 에 실제로 읽은 9행을 고정했다(읽는 순간 ops-snapshot 도 실행 중이 아니었다).
  - 그 뒤 **아무 작업도 다시 안 돈다**고 가정했다.
  - `task_seen` 은 운영 값 그대로다(16:05:02).
  - 09-27 18:05 부터 11-10 까지 **매시** 스캔했다.
  - scratch 임시 루트 두 개에서 돌렸다: 지금 계약(후) / 네 칸만 옛 티켓으로 되돌린 계약(전).
  - 일일 리포트·리듬 입력은 껐다(예약 작업만 본다).

| 처음 울리는 때 | 작업 | 라벨 | 전 | **후** |
|---|---|---|---|---|
| 즉시 | naechaget-home-tunnel | 실패 · 0xC0000005 · 다음 실행 없음 | ticket-open(AUD-05) | ticket-open(AUD-05) |
| 09-28 21:05 | naechaget-org-standup | 조용히 안 돎 · 마지막 성공 09-27 08:45 · 매일 36시간 | 지시서 | 지시서 |
| 09-29 00:05 | naechaget-daily-report | 조용히 안 돎 · 09-27 12:00 · 매일 36시간 | 지시서 | 지시서 |
| 09-29 05:05 | naechaget-org-heartbeat | 조용히 안 돎 · 09-27 17:05 · 매일 36시간 | 지시서 | 지시서 |
| 09-29 05:05 | naechaget-db-backup-pull | 첫 실행 없음 · 등록 09-27 16:05 뒤 · 매일 36시간 | **ticket-open(AUD-08) → 0장** | **지시서** |
| 09-29 06:05 | naechaget-ops-snapshot | 조용히 안 돎 · 09-27 17:08 · 매일 36시간 | 지시서 | 지시서 |
| 10-04 13:05 | naechaget-weekly-report | 조용히 안 돎 · 09-26 13:00 · 매주 8일 | **ticket-open(AUD-15) → 0장** | **지시서** |
| 10-05 09:05 | NaechaGet-PhotoClassify | 조용히 안 돎 · 09-27 08:17 · 매주 8일 | **ticket-open(AUD-15) → 0장** | **지시서** |
| 10-27 21:05 | naechaget-monthly-report | 첫 실행 없음 · 등록 09-22 20:47 뒤 · 매월 35일 | **ticket-open(AUD-15) → 0장** | **지시서** |

- 44일 매시 스캔이 끝난 뒤 task 지시서는 **후 8장 / 전 4장**이다. 작업당 한 장이고 멱등이다(키 목록은 실행 출력에 있다).
- 결과는 qa 1회차 표(§1.1)와 시각까지 같다. 바뀐 것은 네 작업의 동작뿐이다.
- 실제로는 heartbeat 가 자기 스캔을 도는 동안 '실행 중'이라 자기를 잡지 않는다. heartbeat 가 멈추면 08:45 스탠드업 스캔이 잡는다(1회차와 같음 — 추정, 코드 근거만 있다).

## 7. 테스트

### 신규 `tests/test_ops4_r2_fixes.py` — 37건

| 영역 | 내용 |
|---|---|
| ① | 주석 달린 `-` 4형태 인계 정상 · 값 붙은 `-` 3형태는 구하지 않음 · 다른 줄은 안 고침 · `-#x` 한계(YAML 값, skipped 기록) |
| ② | Duration 9경우 표(§3) · 한 번 트리거의 유한 반복이 끝남 · 유한 Duration 주간 작업이 매주 한도로 판정 |
| ③ | 끝난 트리거가 주기·첫 시작에서 빠짐 · 끝나기 전엔 셈 · 오프셋 붙은 EndBoundary 정각 경계 · 전부 끝남 = 규칙 밖 · 기본 `now` |
| ④ | `cls`·`limit_h` 모양 · `silence_rows` 읽기만·task_seen·처음 보면 지금 · **순환계와 대시보드 판정 글자까지 같음** · 결과를 그대로 싣는다(가짜 결과가 그대로 나옴) · 실패는 None · 경고는 한 번씩 · KPI 수 · `build_state` 통합 · 대시보드에 규칙 없음 |
| ⑤⑥ | §3.1 네 행 티켓 `-`·문구 · 실제 §3.1 로 네 작업이 지시서가 됨 · 따라잡기 적용 사실 · 옛 문장 없음 · '대시보드 정기 작업 표' 없음 · '정기 작업'은 일일 리포트 뜻으로 남음 |

### 공허 통과 점검 — 변이 16종 중 16종 빨간불

- 방식: 원본은 건드리지 않았다. 변이는 **메모리에서만** 적용해 `sys.modules` 에 먼저 올렸다(pytest `-p` 플러그인, scratch).
- 원본 md5 는 전후가 같았다. 대조 실행(항등 변이)은 154 passed 였다.
- 대상: r2 · qa · followups 세 파일.

| 변이 | 결과 |
|---|---|
| 정규식 옛 모양 · Duration 무시 · 유한이면 항상 바깥 주기 · 못 읽는 Duration 을 무기한으로 · 한 번 트리거 유한 반복이 안 죽음 | 각각 1+ failed |
| EndBoundary 무시 · 끝난 순간을 살아 있다고 봄 · 끝난 트리거 시작도 셈 | 각각 1+ failed |
| attach 가 silence 를 안 실음 · attach 가 bad 를 False 로 · build_state 가 attach 안 부름 | 각각 1+ failed |
| pending 이 첫 실행 없음도 셈 · 판정 못해도 silent 0 · alarm 에 silent 빠짐 | 각각 1+ failed |
| silence_rows 가 처음 본 작업을 '' 로 · 정상 행에 cls 안 실음 | 각각 1+ failed |

### qa strict xfail 3건

먼저 돌려 **XPASS(strict) 3 failed** 를 확인했다. 그 뒤 표식만 떼고 이유를 주석 한 줄로 남겼다(`QA-OPS4-n(고침 — backend r2 …)`). 단언은 그대로다.

### 전체 스위트

- 조건: `python -m pytest -q -p no:cacheprovider`, `NC_NO_SCHEDULER=1` `NC_NO_BACKGROUND=1`, HEAD `e772962` + 작업 트리, 17:14:38~17:28:59.
- 결과: **2,306 passed · 3 xfailed · 1 failed**(857초).
  - 실패: `tests/test_ux9_r2_fixes.py::test_second_link_during_slow_navigation_keeps_skeleton`.
    - 브라우저 표본 55개 중 1개가 목록을 보였다는 타이밍 단언이다.
    - 이 파일과 `vehicles.html` 은 16:30:56 이후 바뀌지 않았다(내 작업 전). 내 모듈을 import 하지 않는다.
    - **단독 3회 3/3 통과**. 부하 때의 타이밍 흔들림으로 본다(추정). 다른 워크플로 영역이라 건드리지 않았다.
- **수 맞추기**:
  - qa 1회차 기준은 2,267 passed + 6 xfailed = 2,273 이다.
  - 신규 +37 과 xfail→통과 3 을 더하면 총 2,310 = 2,306 + 3 + 1 이다. 줄어든 테스트는 없다.
  - 남은 xfailed 3 은 `test_feat1_qa_adversarial` 2 · `test_feat2_qa_adversarial` 1 이다. UX-9 QA 의 xfail 1 은 이번 실행에서 없었다 — 그쪽 워크플로 변경(추정).
- OPS 묶음(ops4 네 파일 · ops3 세 파일 · org_runtime · ops_health · no_visitor_tracking): **328 passed**.
- `tools/check_md_tables.py`: 계약·프로토콜 2편 이상 없음.

## 8. 형식 변경 명세 — frontend(`-70`)·qa(`-71`)가 반영할 것

**웹 API(`web/`)·템플릿 dict 키·DB 스키마 변경 없음.** 바뀐 것은 사내 도구의 JSON 과 순환계 반환 모양이다.

### 8-1. 대시보드 JSON(`/api/state`, 그리고 같은 `build_state` 를 굽는 ops 스냅샷 JSON)

**`schedule[]` 행 + `silence`** (새 키):

```
silence: null                      # 판정을 못 붙임(모름) — '정상'으로 그리지 말 것. problems 에 사유가 있다
silence: {
  "bad":     bool,                 # 조용히 안 돎 또는 첫 실행 없음 — 경보
  "label":   str,                  # bad 일 때만. 순환계 결재함·스탠드업과 같은 글자
                                   #  '조용히 안 돎 · 마지막 성공 MM-DD HH:MM · 매일 작업 한도 36시간 넘김'
                                   #  '첫 실행 없음 · 등록 MM-DD HH:MM 뒤 매월 작업 한도 35일 넘김'
  "since":   str,                  # bad 일 때 ISO(마지막 성공 또는 등록 시각), 아니면 ''
  "limit_h": int,                  # 규칙 안 작업이면 한도(시간: 36·192·840), 규칙 밖이면 0
  "cls":     "매일"|"매주"|"매월"|"",   # 트리거 주기 분류. ''= 규칙 밖(부팅 트리거 터널 등)·실행 중·꺼짐
  "warn":    str                   # 트리거를 못 읽음·§1 한도 없음이면 사유(그때 bad 는 False)
}
```

- `silence.bad` 가 참일 수 있는 행은 둘뿐이다. 서로 겹치지 않는다.
  - ⓐ `ok` 참 · `next_run` 있음 · 실행 중 아님
  - ⓑ `never_ran` 참 · `next_run` 있음
- **렌더 권고**(design #1 과 같음 — 결정은 frontend):
  - 칩 판정 순서: ① 실행된 적 없음·예정 없음(빨강) → ② **`silence.bad` 면 `pill warn` + `silence.label`, 행 `late`** → ③ 기존 규칙('아직 때가 안 됨'·실행 중·정상·실패).
  - ⓑ('첫 실행 없음')는 지금 '아직 때가 안 됨'으로 그려지는 행이다. **② 를 그보다 먼저** 봐야 한다.
- **`kpi`**:
  - `sched_silent`: `silence.bad` 행 수. 판정을 못 붙였으면 `null`(0 이 아니다 — `running_now` 와 같은 원칙).
  - `sched_alarm` = `sched_never + sched_bad + (sched_silent or 0)` — 볼 것이 있는 작업 수.
  - `sched_pending`: **뜻이 좁아졌다.** '첫 실행 없음'으로 판정된 작업은 빠진다(대기이면서 경보일 수 없다).
  - `sched_total`·`sched_never`·`sched_bad`: 뜻이 전과 같다.
  - 타일 권고: `sched_never`/`sched_bad` 는 빨강 그대로 두고, `sched_silent > 0` 이면 주황으로 'N개 조용히 안 돎'.
- `problems[]` 에 새 문장이 들어갈 수 있다:
  - "조용히 안 도는 예약 작업을 판정하지 못했다: …"
  - "예약 작업 `…` 의 트리거를 읽지 못했다 — …"
  - "org-contracts §1 에 `…` 가 없다 — …"

### 8-2. 순환계·도구 함수

| 어디 | 전 | 후 |
|---|---|---|
| `org_runtime.silence_verdict` 반환 | {bad, label, since, limit_h, warn} · 정상이면 limit_h 0 | + `cls`. 규칙 안 작업이면 정상이어도 `cls`·`limit_h` 를 싣는다. `bad` 일 때의 값은 같다 |
| `org_runtime.Org.silence_rows` | — | 새 메서드(읽기만) |
| `agent_dashboard.trigger_period` | `(xml)` | `(xml, now=None)` — 끝난 트리거·유한 반복 반영 |
| `agent_dashboard` 새 이름 | — | `attach_silence` · `schedule_counts` · `_local_naive` |
| `_BARE_DASH_WORKFLOW` | 줄 끝 공백만 | 줄 끝 주석 허용 |
| 스탠드업 '경보 → 티켓' 머리 | "예약 작업 고장이" | "예약 작업 경보(고장·조용히 안 돎)가" |
| 계약 §3.1 네 행 | 티켓 AUD-08·AUD-15 | `-` + Steward 문구 |

- **qa `-71` 이 알아 둘 것**: `test_ops4_qa_adversarial._dashboard_pill` 은 1회차 html 칩 규칙을 옮긴 도우미다. `-70` 이 칩 규칙을 바꾸면 이 도우미가 옛 규칙을 말하게 된다.
  - 지금은 캡처 시각 9행이 모두 조용하지 않아 결과가 같다(통과).
  - 도우미를 `silence` 를 보는 규칙으로 맞추는 것을 권한다.

## 9. Steward 가 볼 것

1. **작업 트리 변경이 매분 서버로 나간다**(확인된 사실 — 내가 실행한 것은 아니다).
   - `naechaget-ops-snapshot` 은 1분마다 `tools/export_dashboard_snapshot.py` 로 **작업 트리의** `build_state()` 를 굽는다. 그 결과를 `publish_dashboard_snapshot.ps1` 이 운영 서버 `web/static/ops/<열쇠>.json·html` 로 scp 한다.
   - 17:13:47 로컬 사본에 `silence`·`sched_silent` 가 이미 들어 있고, 로그에 `17:13:47 published` 가 있다.
   - 새 필드는 작업 이름·판정 라벨·한도뿐이다. 개인정보는 없고, 전에도 나가던 schedule 행에 붙은 것이다.
   - 다만 "배포 금지"인 회차에도 대시보드 코드 변경은 이 경로로 **사실상 1분 안에 비밀 주소에 반영된다.** 1회차(`period_s` 등)도 같았다.
   - 원하면 스냅샷 굽기를 커밋된 코드로 제한하는 방안을 따로 정할 일이다(판단).
2. **10-01 첫 월간 보고의 안전망은 이제 따라잡기다.**
   - monthly 는 `StartWhenAvailable=True` 이지만 Interactive 다.
   - 그래서 10-01 13:30 에 PC 가 꺼져 있으면, 켜고 **오너가 로그온한 뒤** 돈다. 따라잡기가 Interactive 작업에서 로그온 뒤에 도는지는 이 PC 에서 재 보지 않았다(추정).
   - 이 규칙이 첫 실행 누락을 잡는 것은 여전히 등록 + 35일 = **10-27 21:05** 다. 이제는 지시서가 된다.
   - 10-01 당일에 잡으려면 '첫 실행 없음'의 기준을 '첫 예정 시각 + 여유'로 바꾸는 방안이 있다. 판정 규칙 변경이라 제안만 한다.
3. **남은 어휘 두 곳**(내 범위 밖이라 고치지 않았다):
   - `.claude/commands/daily-check.md` 의 "예약 작업 고장(대시보드 정기 작업 표, …)"
   - `tools/agent_dashboard.html` 의 절 제목·KPI 이름·주석 두 곳("정기 작업 표와 **같은 목록**") — frontend `-70` 이 할 일이다.
   - 참고: `web/static/ops/*.html` 사본은 스냅샷이 매분 다시 굽는다.
4. **백로그 AUD-15 제목**이 아직 "예약 작업 따라잡기 없음(10-01 첫 월간 보고 누락 위험)"이다. 따라잡기 건은 적용됐으니 상태 칸이나 제목을 갱신할 일이다(Steward 문서).

## 10. 확인된 사실 · 추정 · 미검증

- **확인된 사실**:
  - 따라잡기 설정·로그온 방식(읽기만)
  - 라이브 17:05 스캔 exit 0
  - 임시 루트 dry-run 0건과 운영 파일 md5 불변
  - 17:09 실측 9행의 주기·분류·판정
  - 시뮬레이션 표
  - 순환계·대시보드 판정 일치
  - 스냅샷 파일에 새 필드
  - XPASS 확인
  - 변이 16/16
  - 전체 스위트 수와 UX-9 단독 3/3
- **추정**:
  - UX-9 실패는 부하 때의 타이밍 흔들림이다.
  - heartbeat 가 멈추면 스탠드업 스캔이 잡는다(1회차와 같음).
  - Interactive 작업의 따라잡기는 로그온 뒤에 돈다.
- **미검증**:
  - 네임스페이스가 다른 트리거 XML(qa 관찰 — 경고 없이 주기 None)과 `<Enabled>0</Enabled>` 는 이번 지시서 범위 밖이라 그대로 두었다.
  - `해당 없음`·en dash `–` 같은 목록 밖 표기도 그대로다(qa §5-4 낮음).
