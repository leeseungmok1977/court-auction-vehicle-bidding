# orders/ — 작업 지시서 대기열

> 2026-09-26 제정. 전에는 [작업 지시서]가 Steward 의 대화 속에만 있었다. 세션이 닫히면
> 지시도 사라졌고, 대시보드는 "누가 무엇을 기다리는가"를 볼 수 없었다.
> 이제 지시서는 **파일**이다. 대기열이 곧 조직의 할 일 목록이다.

## 누가 만드나

- **Steward** — `python tools/org_runtime.py order --to <담당> --purpose "…"`
- **순환계** — 보고서 머리말의 `handoff:`, 리듬 중단, 미배분 티켓, 정체, 왕복 상한 초과
  (규칙은 [`docs/org-contracts.md`](../docs/org-contracts.md) §3)

손으로 파일을 만들어도 된다. 형식만 지키면 순환계가 읽는다.

## 형식 — `orders/YYYY-MM-DD-NN.md`

CLAUDE.md 의 작업 지시서 형식(번호/담당/목적/범위/입력/기한/산출물)을 그대로 파일로 옮겼다.

```yaml
---
id: 2026-09-26-04
to: backend-engineer          # 받는 자리. steward = 오너·Steward 결재함
from: qa-engineer             # 누가 넘겼나 (steward · org-runtime · 에이전트 이름)
ticket: FEAT-1                # 백로그 티켓. 없으면 최초 지시서 번호로 묶인다
status: open                  # open | doing | done | blocked | escalated | cancelled
round: 2                      # 같은 티켓에서 이 자리가 받은 몇 번째 지시서인가
reason: handoff               # handoff | rhythm | unassigned | stale | cap | owner | routine | manual
key: handoff:reports/2026-09-26-feat1-qa.md>backend-engineer   # 중복 방지 열쇠
due: 2026-09-27
created: 2026-09-26T20:40:00
inputs:
  - reports/2026-09-26-feat1-qa.md
output: reports/2026-09-26-backend-engineer-FEAT-1-r2.md
---
## 목적
## 범위
## 완료 기준
```

## 상태가 바뀌는 때

| 상태 | 언제 |
|---|---|
| `open` | 만들어졌다 |
| `doing` | 당직 또는 Steward 가 담당을 불렀다 |
| `done`·`blocked` | 그 지시서 번호(`order:`)를 단 보고서가 `reports/`에 들어왔다 |
| `blocked` | 당직이 불렀는데 **보고서가 안 나왔다** — 끝났다고 치지 않는다 |
| `escalated` | 왕복 상한을 넘겨 Steward 결재함으로 올라갔다 |
| `cancelled` | Steward 가 취소했다(`order-close --status cancelled`) |

★ **보고서 없이 `done` 으로 바꾸지 않는다.** CLAUDE.md 운영 규칙 7 — 티켓은 DoD 원문과
대조한 뒤에만 닫는다 — 이 대기열에도 똑같이 적용된다.
