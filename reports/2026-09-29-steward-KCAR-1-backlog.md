---
order: 2026-09-29-03
from: steward
ticket: KCAR-1
result: done
verified: 재현
handoff: []
---

# KCAR-1 후속 백로그 반영 (Steward, 2026-09-29)

헤드리스 당직이 `docs/backlog.md` 쓰기를 거부당해 남긴 pm 문안(`reports/2026-09-27-pm-orchestrator-KCAR-1.md` §2)을 옮겼다.

- (가) KCAR-3 행 끝 — 즐겨찾기·입찰 메모가 판정 변화를 반영하지 않는 문제(F1) 흡수와 DoD 보강
- (나) KCAR-4 행 끝 — 차익 카드 색 처방(F2)과 DoD 보강
- (다) KCAR-5 신규 — 부적합 판정 문단의 사고이력 단서를 별도 중립 한 줄로
- (라) DES-6 신규 — '소매 평균 시세' 라벨이 실제로는 중앙값
- (마) AUD-03 행 끝 — 시세 나이와 '높음' 초록 알약 충돌, 범위 셋으로 나눔

옮기기 전 코드 주장 5건을 재현했다(확인된 사실):
`app.py` `watchlist` 에 `bid_state` 없음 · `detail.html` 차익 블록 `text-emerald-600` · `service.py` `plain_verdict` 가 `alt` 사용 ·
템플릿 전체 '소매 평균 시세' 1곳 · `detail.html` `cbadge` 가 '높음'에 `bg-emerald-400`. 카니발 10111 수치와 즐겨찾기 렌더는 pm 보고대로 미검증이다.
