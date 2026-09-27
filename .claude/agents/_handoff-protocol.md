# 보고서 머리말 규약 — 다음 담당을 적는다

> `_` 로 시작하므로 에이전트 정의가 아니다(`_panel-context.md` 와 같다).
> 2026-09-26 제정. 배선도는 [`docs/org-contracts.md`](../../docs/org-contracts.md).

## 1. 왜

서브에이전트는 서로 부르지 못한다. 전에는 "다음은 누구에게"가 Steward 의 기억 속에만 있어서,
Steward 세션이 닫히면 조직이 멈췄다. 이제 **보고서가 다음 담당을 적고**, 순환계
(`tools/org_runtime.py`)가 그 줄을 읽어 다음 지시서(`orders/`)를 만든다.

## 2. 형식 — `reports/` 에 쓰는 모든 보고서의 **맨 첫 줄부터**

```yaml
---
order: 2026-09-26-03          # 이 보고가 답하는 지시서 번호. 지시서 없이 한 일이면 줄을 지운다
from: qa-engineer             # 이 보고를 낸 자리
ticket: FEAT-1                # 백로그 티켓 ID. 없으면 줄을 지운다
result: fail                  # done | fail | blocked | needs-owner
verified: 재현                # 재현 | 미검증 — 주장을 코드·DB·라이브로 다시 확인했는가
handoff:                      # 다음 담당. 없으면 handoff: []
  - to: backend-engineer
    why: 가격대 필터 반증 2건 — 재현 절차는 §3
---
```

- `to` 는 [`docs/org-contracts.md`](../../docs/org-contracts.md) §2 의 **넘길 수 있는 곳**에 있어야 한다.
  없는 곳을 적으면 인계는 실행되지 않고 `steward` 결재함으로 올라간다.

### 워크플로가 부른 단계면 `workflow:` 를 단다 (2026-09-27, OPS-3)

```yaml
workflow: audit-1-run-3        # 이 보고를 부른 워크플로 실행 id. 워크플로 밖이면 줄을 지운다
```

- 이 줄이 있으면 순환계는 `handoff:` 로 **새 지시서를 만들지 않는다** — 다음 단계는 워크플로가 부른다.
  `result: fail`·`blocked` 인데 `handoff:` 가 없어도 `pm-orchestrator` 반려 지시서를 만들지 않는다.
  대신 `data/org-bus.jsonl` 에 `handoff.skipped`·`result.skipped` 한 줄을 남긴다(무엇을 건너뛰었는지 추적된다).
- `result: needs-owner` 는 **그래도 결재함에 올라간다.** 오너 결정은 워크플로가 삼키지 않는다.
- `handoff:` 는 그대로 적는다 — 워크플로 **밖**에서 이 보고를 읽는 사람에게 다음 담당을 알려 준다.
- 왜: 2026-09-27 워크플로 보고서의 `handoff:` 가 **이미 돌고 있는 단계**에 지시서 11건을 또 만들었다(Steward 취소).
  `workflow:` 가 없어도, Steward 가 발행한 지시서에 답한 보고서이고 같은 티켓·같은 담당으로 열린(`open`·`doing`)
  지시서가 이미 있으면 순환계는 새로 만들지 않는다(org-contracts §3).
- 오너 결정이 필요하면 `result: needs-owner` 로 닫는다. `handoff` 로 돌려 막지 않는다.
- `why` 는 **다음 담당이 무엇을 해야 하는지** 한 줄이다. 느낌이 아니라 산출물을 가리킨다(ORG §2.1).

## 3. 할 일이 없을 때

정기 지시서(리듬)를 받았는데 볼 것이 없으면 **부풀리지 않는다.**

```yaml
---
order: 2026-10-03-01
from: insight
result: done
verified: 재현
handoff: []
---
이상 없음 — 확인한 것 세 줄.
```

리듬을 만족시키려고 분량을 채우지 않는다(agent-utilization §3).

## 4. 쓰기 권한이 없는 자리

`insight`·`photo-classifier` 처럼 `Write` 가 없는 자리는 Steward 가 결과를 받아 대신 쓴다.
그때 `from` 은 **일을 한 자리**를 적고, Steward 는 머리말을 지어내지 않는다 —
그 자리가 말한 다음 담당만 옮긴다.
