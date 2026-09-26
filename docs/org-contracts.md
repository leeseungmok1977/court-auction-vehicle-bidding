# 인계 계약 — 누가 무엇을 받아 누구에게 넘기는가

> 2026-09-26 오너 지시로 제정. *"회사라면 각각의 조직원들이 유기적으로 움직여야 하는데,
> 그렇지 않다."*
>
> **이 문서는 조직도가 아니라 배선도다.** 부서 편성은 [`ORG.md`](ORG.md) §1이 정하고,
> 여기에는 **일이 흐르는 길**만 둔다. `tools/org_runtime.py`가 §1·§2 표를 읽어 움직이고
> `tools/agent_dashboard.py`가 같은 표를 읽어 화면에 띄운다 — **표를 고치면 둘 다 따라온다.**
> 표에 없는 경로로 넘기려 하면 순환계는 그 인계를 **실행하지 않고 Steward 결재함으로 올린다.**

## 0. 왜 이 문서가 필요했나 — 2026-09-26 실측

대시보드 조직도에서 읽힌 것:

| 증상 | 실측 | 뜻 |
|---|---|---|
| PM 이 뛰지 않는다 | `pm-orchestrator` 2회·3일 전 / `frontend-engineer` 18회·`app-design-expert` 50회 | 배분을 PM 이 아니라 오너·Steward 가 직접 하고 있다 |
| 경보가 반응을 부르지 않는다 | `리듬중단` 3자리가 13일째 | 화면은 알고 있는데 아무도 깨우지 않는다 |
| 인계가 기록되지 않는다 | `reports/` 38건 중 다음 담당을 **기계가 읽을 형식으로** 적은 곳 0건. 산문으로 적은 곳 1건(`bidder-insight-2026-09-26.md` — "`growth`가 검토할 … 문제로 넘긴다") — 그 인계가 실행됐는지 추적할 방법이 없다 | 다음 담당 연결이 Steward 기억 속에만 있다 |
| 종료 조건 없는 왕복 | 디자인 검수 50회 `과부하` | 같은 티켓에서 몇 번째 왕복인지 아무도 세지 않는다 |

원인은 한 줄이다: **Steward 는 오너가 세션을 열 때만 존재한다.** 서브에이전트는 서로 부르지
못하므로(ORG §1) Steward 가 없으면 조직 전체가 정지한다. 그래서 세 가지를 붙였다.

1. **지시서를 파일로 둔다**(`orders/`) — 기억이 아니라 대기열에 일이 쌓인다.
2. **보고서가 다음 담당을 적는다**(`_handoff-protocol.md` 머리말) — 순환계가 그것을 읽어 다음 지시서를 만든다.
3. **당직 Steward 가 정해진 시각에 깨어난다**(작업 스케줄러) — 오너가 없어도 자동 실행 가능한 지시서를 처리한다.

## 1. 운영 설정

| 설정 | 값 | 뜻 |
|---|---|---|
| `자동 디스패치` | `켜짐` | `꺼짐`으로 바꾸면 당직 Steward 가 지시서를 **읽고 브리핑만** 쓰고 아무도 부르지 않는다 |
| `하루 디스패치 상한` | `3` | 당직이 하루에 부르는 최대 건수. 비용 상한이다 — 올리는 것은 오너 승인 사항 |
| `정체 기준(일)` | `3` | 열린 지시서가 이 일수를 넘기면 `pm-orchestrator`에게 정체 점검을 건다 |
| `기본 왕복 상한` | `3` | 같은 티켓에서 같은 담당이 받는 지시서 수. 넘으면 인계 대신 Steward 결재함 |

## 2. 부서별 계약

- **받는 일**: 이 자리가 깨어나는 조건. 여기에 없는 일로 부르지 않는다.
- **넘길 수 있는 곳**: 보고서 머리말 `handoff:` 에 적을 수 있는 담당. `steward`(결재함)는 누구나 쓸 수 있다.
- **자동**: `예`면 당직 Steward 가 오너 없이 부른다. `아니오`면 지시서가 쌓이기만 하고 **오너가 연 세션**에서 처리한다.
  코드를 고치는 자리·외부에 요청을 보내는 자리·오너 입력이 필요한 자리는 전부 `아니오`다.
- **리듬(일)**: 이 일수 동안 이 자리에 지시서가 한 건도 없으면 순환계가 정기 지시서를 만든다. `-`는 부를 때만 일한다.
  ★ 정기 지시서는 **일을 지어내라는 뜻이 아니다.** 볼 것이 없으면 `result: done` 한 줄로 닫는다(프로토콜 §3).
- **왕복 상한**: 비우면 §1 기본값.

| 담당 | 받는 일 | 넘길 수 있는 곳 | 자동 | 리듬(일) | 왕복 상한 |
|---|---|---|---|---|---|
| `pm-orchestrator` | 스탠드업 배분 · 미배분 티켓 · 정체 지시서 · 반려 판정 | `backend-engineer` `frontend-engineer` `qa-engineer` `insight` `growth` `compliance-officer` `design-critic` `app-design-expert` `auction-expert` `usedcar-expert` `app-qa-auditor` `voice` `bidder-insight` `monetization-engineer` `photo-classifier` | `예` | `1` | `5` |
| `backend-engineer` | 라우트·스키마·산정 로직 티켓 · qa 반증 | `qa-engineer` `frontend-engineer` `pm-orchestrator` | `아니오` | `-` | |
| `frontend-engineer` | 화면 티켓 · 디자인 검수 수정지시 | `qa-engineer` `design-critic` `app-design-expert` `backend-engineer` `pm-orchestrator` | `아니오` | `-` | |
| `qa-engineer` | 구현 완료 보고 · 주간 테스트 게이트 | `backend-engineer` `frontend-engineer` `design-critic` `app-design-expert` `pm-orchestrator` | `예` | `7` | |
| `insight` | 지표 이상 · 실험 판정 · 성장 제안 반대 심문 · 주간 수치 검증 | `pm-orchestrator` `growth` `backend-engineer` `usedcar-expert` `auction-expert` | `예` | `7` | |
| `auction-expert` | 주간 전문가 패널 | `pm-orchestrator` `insight` | `아니오` | `-` | |
| `usedcar-expert` | 주간 전문가 패널 · 시세 매칭 의심 | `pm-orchestrator` `insight` | `아니오` | `-` | |
| `app-qa-auditor` | 주간 전문가 패널 · 운영 수치 반증 | `pm-orchestrator` `insight` `backend-engineer` | `아니오` | `-` | |
| `photo-classifier` | `/classify-photos` 결과 검수 · 썸네일 이의 | `backend-engineer` `pm-orchestrator` | `아니오` | `-` | |
| `growth` | 유입·리텐션·포지셔닝 개선안 요청 | `insight` `compliance-officer` `pm-orchestrator` | `예` | `-` | |
| `voice` | 오너가 넘긴 리뷰·문의 | `pm-orchestrator` `growth` `insight` | `아니오` | `-` | |
| `bidder-insight` | 기능 우선순위·무료/유료 경계 결정 전 조사 | `pm-orchestrator` `growth` `compliance-officer` | `아니오` | `-` | |
| `compliance-officer` | 공개 범위·신고 정합성·성장 제안 반대 심문 | `pm-orchestrator` | `예` | `-` | |
| `monetization-engineer` | 오너가 유료화를 결정한 뒤 | `compliance-officer` `pm-orchestrator` | `아니오` | `-` | |
| `app-design-expert` | 공개 제품 화면 변경 검수 | `frontend-engineer` `pm-orchestrator` | `예` | `-` | `3` |
| `design-critic` | 사내 도구·문서·산출물 화면 변경 검수 | `frontend-engineer` `pm-orchestrator` | `예` | `-` | `3` |

> 성장 제안은 반대 심문을 거친다(ORG §2.2) — 그래서 `growth`는 `insight`·`compliance-officer`로만
> 넘기고, 둘이 판정한 뒤에 `pm-orchestrator`로 간다.
>
> `auction-expert`·`usedcar-expert`·`app-qa-auditor`가 `자동: 아니오`인 이유: 이 셋은 **클라우드 패널
> 루틴**이 부른다. 이 자리의 리듬이 끊기면 사람을 부를 게 아니라 루틴 인프라를 봐야 한다
> (agent-utilization §4) — 그래서 순환계는 이 경우 에이전트가 아니라 **Steward 결재함**으로 올린다.

## 3. 순환계가 스스로 만드는 지시서

| 계기 | 받는 자리 | 중복 방지 |
|---|---|---|
| 보고서 머리말 `handoff:` | 적힌 담당(계약에 있는 경로만) | 같은 보고서 → 같은 담당은 한 번 |
| 보고서 `result: fail`·`blocked` 인데 `handoff:` 없음 | `pm-orchestrator` | 보고서당 한 번 |
| 보고서 `result: needs-owner` | `steward` | 보고서당 한 번 |
| 왕복 상한 초과 | `steward` | 티켓·담당당 열린 것 한 건 |
| 리듬 감시(agent-utilization §3) `늦음`·`끊김`·`없음` | 담당 칸의 에이전트가 계약상 `자동: 예`면 그 자리, 아니면 `steward` | 산출물당 열린 것 한 건 |
| 백로그 `todo` 인데 지시서가 없는 티켓 | `pm-orchestrator` (묶어서 한 건) | 열린 것 한 건 |
| 정체 기준을 넘긴 열린 지시서 | `pm-orchestrator` (묶어서 한 건) | 열린 것 한 건 |
| §2 리듬(일) 동안 지시서가 없던 자리 | 그 자리 | 리듬 주기당 한 건 |

## 4. 당직 Steward 가 하지 않는 것

오너 승인 항목(ORG §3)은 **도구 권한으로 막는다** — 헤드리스 실행에는 허용 목록 밖 도구가 전부
거부된다. 커밋·푸시·ssh·배포·설정 변경·코드 편집은 허용 목록에 없다.
당직은 오너 승인이 필요한 결론에 닿으면 보고서를 `result: needs-owner`로 닫고 멈춘다.

### 실측 — 이 막음이 서브에이전트까지 닿는가 (2026-09-26)

첫 당직 실행(`compliance-officer`, 저장소 복사본)이 스스로 이 절의 빈틈을 짚었다: *"허용·금지 목록은
최상위 `claude -p`에만 넘어가는데, 당직이 `Agent`로 위임한 서브에이전트에도 적용되는지는 미검증이다."*
맞는 지적이라 **도구 계층에서 직접 쟀다.** 조건: Claude Code 2.1.283 · Linux · 저장소 복사본 ·
`tools/org_runtime.py` 의 `_claude_cmd()` 그대로 · 당직이 `general-purpose` 서브에이전트에게 쓰기 두 건을 시킴.

| 서브에이전트의 쓰기 | 도구가 돌려준 결과(원문) |
|---|---|
| `src/_probe_sub.txt` | `File is in a directory that is denied by your permission settings.` — 파일 없음 확인 |
| `reports/_probe_sub.txt` | `File created successfully` — 파일 있음 확인 |

→ **최상위의 허용·금지 목록이 위임된 서브에이전트의 도구 호출에도 적용된다.** 에이전트 정의의 `tools:`
(예: `design-critic` 의 경로 없는 `Write`)는 이 목록을 넓히지 못한다.
⚠ 같은 날 `design-critic` 으로 먼저 쟀을 때는 서브에이전트가 **역할 밖 지시라며 스스로 거부**해서
도구 계층을 관찰하지 못했다. 그 결과를 "도구가 막았다"로 적지 않았다 — 막은 것은 도구가 아니라 판단이었다.
Claude Code 버전이 오르면 이 표를 다시 잰다.
