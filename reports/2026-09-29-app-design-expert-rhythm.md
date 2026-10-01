---
order: 2026-09-29-11
from: app-design-expert
ticket: 2026-09-29-11
result: needs-owner
verified: 재현
handoff: []
---

# 18인 페르소나 패널 리듬 `늦음` — 나흘째 재확인 (2026-09-30 당직, 지시서 2026-09-29-11)

> 조사는 `app-design-expert` 가 했다. 이 자리는 reports/ 에 쓰지 말라는 지시를 받았으므로 당직 Steward 가 결과를 받아 적었다.
> 이 지시서는 `2026-09-28-02` 가 닫히자 같은 key(`rhythm:docs/reviews/persona/*.md`)로 세 번째로 다시 생긴 것이다.
> `verified: 재현` 은 아래 **확인된 사실**에만 해당한다. 당직이 앵커 문자열로 파일을 직접 다시 찾아 확인했다. **추정** 절은 미검증이다.

## 요약

패널은 여전히 9/17 이후 멈춰 있다. 원인 ①~⑦도, 사람이 할 조치 ①~③도 바뀌지 않았다. 본문은 [09-27 보고](2026-09-27-app-design-expert-rhythm.md) 부록에 있다.
새로 확인된 사실은 세 가지다.
- 결재함에 같은 결정이 **두 건** 열려 있다.
- 09-29 오너 세션이 열렸지만 이 결정은 처리되지 않았다.
- 권고안 A안이 실제로 작동하는 사례가 다른 리듬 행에서 관측됐다.

## 확인된 사실 (당직 재현)

1. **결재함 중복 2건, 1건은 기한 초과.**
   - `orders/2026-09-27-19.md`: `status: open` · `due: '2026-09-29'` → 기한을 하루 넘겼다.
   - `orders/2026-09-29-10.md`: `status: open` · `key: owner:reports/2026-09-28-app-design-expert-rhythm.md` · `due: '2026-10-01'`. 내용은 위와 같은 결정이다.
   - 09-29 보고가 추정으로 적은 "결재함에 같은 건이 날마다 는다"는 이로써 두 번 실측됐다.
2. **오너 세션에서 처리되지 않았다.** `docs/standups/2026-09-30.md` 흐름에 Steward 가 만든 지시서가 이어진다. `17:58 … steward → insight 2026-09-29-12 REC-1` 부터 `04:12 … steward → design-critic 2026-09-30-10` 까지다. 그러나 1의 두 건은 여전히 열려 있다.
3. **A안이 작동한다는 실측 사례가 있다.**
   - `docs/agent-utilization.md` 에서 `docs/weekly-reports/*.md` 행의 담당 칸은 `(자동 토 13:00)` 이다. 이 칸에서는 자동 자리가 잡히지 않는다.
   - `tools/org_runtime.py` 리듬 분기는 `owners = [n for n in _TICK.findall(r.get("owner", "")) if seats.get(n, {}).get("auto")]` → `to = owners[0] if owners else STEWARD` 순서로 받는 자리를 정한다. 그래서 이 행의 리듬 경보는 Steward 로 갔다.
   - 스탠드업에 `18:02 order.created org-runtime → steward 2026-09-29-18 리듬 늦음 — docs/weekly-reports/*.md` 가 남아 있다.
   - 페르소나 행 담당을 `steward` 로 바꾸면 이 확인 지시서도 `app-design-expert` 가 아니라 Steward 에게 간다.
4. **그대로인 것.**
   - `docs/reviews/persona/` 에는 여전히 `2026-09-11-r1.md` · `2026-09-14-r2.md` · `2026-09-17-r3.md` 세 개뿐이다.
   - `docs/agent-utilization.md` 행 `` | `docs/reviews/persona/*.md` | 7 | 2026-09-11 | `app-design-expert` (겸임) | `` 가 바뀌지 않았다.
   - `docs/backlog.md` `AUD-09` 행: 상태 `todo · 확인(qa)`, 담당 `Steward · **오너(패널 비용·배선)**`.
5. **원인 ①~⑦ 중 틀려진 것 없음.**
   - 당직이 직접 확인한 것: ⑤ `_TICK.findall`, ⑦ `has_key(key, open_only=True)`, 결재 key 분기 `has_key(f"owner:{rel}")`.
   - 나머지는 서브에이전트가 앵커로 다시 확인했다: ③ `DISPATCH_ALLOWED`, ④ skills 0건, ⑥ `def pick_vehicle`, README 앵커 4개.

## 추정 (미검증)

- 이 보고서를 `needs-owner` 로 닫으면 다음 scan 에서 두 가지가 생길 것이다.
  - 결재함에 **세 번째** 중복 건(`owner:reports/2026-09-29-app-design-expert-rhythm.md`).
  - 같은 확인 지시서의 **네 번째** 발행.
  - 앞의 두 번과 같은 패턴이지만 이번 회차는 아직 실측하지 않았다.
  - **scan 실측(2026-09-30 당직)**: 둘 다 생겼다. `2026-09-30-16`(to `steward`, key `owner:reports/2026-09-29-app-design-expert-rhythm.md`)과 `2026-09-30-17`(to `app-design-expert`, key `rhythm:docs/reviews/persona/*.md`)이다. 이 줄은 확인된 사실로 바뀌었다.
- 이 확인은 매일 하루 디스패치 상한 3건 중 1건을 쓴다. 사흘째 나온 것이 "변동 없음"뿐이라 그 슬롯이 낭비되고 있다.

## 사람이 할 조치

변동 없음(09-27 보고 부록 ② 표 ①~③).

**Steward 권고(변동 없음)**: 조치 ② A안부터 한다. `docs/agent-utilization.md` §3 리듬 표에서 이 행의 담당을 `steward` 로 바꾸는 한 칸 수정이다.
- 비용이 들지 않는다.
- 위 사실 3처럼 같은 분기가 이미 다른 행에서 그렇게 돌고 있다.
- 매일 생기는 헛지시서와 결재함 중복을 함께 멈춘다.

결정하면 `AUD-09` 상태 칸과 결재함 `2026-09-27-19` · `2026-09-29-10` · 이번 scan 이 만들 결재 건을 **함께** 닫는다.

## 다음 담당

없음(서브에이전트 판단). 막힌 곳은 오너 결정 하나이고, 그 결정은 이미 결재함에 올라가 있다.
- `frontend-engineer`: 넘길 화면 작업이 없다.
- `pm-orchestrator`: 에이전트를 기동할 수 없어서 넘겨도 풀리지 않는다.
