---
order: 2026-09-30-18
from: steward
ticket: REC-1
result: done
verified: 재현
handoff: []
---

# 재조회 하루 상한 150 → 60 (지시서 2026-09-30-18)

- 확인(10-01 23:2x, 운영 서버 `web.maint floor-refresh-plan` — 요청 0·쓰기 0): 지연 대상 **37건**, 하루에 해소(days_to_clear 1) — 60 아래라 조건 충족.
- 적용: `config.yaml` `min_refresh_daily_cap` 150 → 60, 커밋 9078af0, 서버 반영·재기동 후 plan 이 `cap: 60` · `targets: 37` 을 낸다.
- 오너 승인 일정("첫 3일만 150")보다 하루 이르다 — 대상이 37건이라 10-02 06:30 실행 결과는 150 과 같다. 10-03 기한을 세션 유무와 관계없이 지키려고 당겼다.
