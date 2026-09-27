---
order: 2026-09-27-04
from: qa-engineer
ticket: 2026-09-27-04
result: done
verified: 재현
handoff: []
---
이상 없음 — 주간 테스트 게이트 통과. 기준: HEAD `c7d38d0` + 미커밋 작업 트리(UX8 필터 접기, 7파일 +103/−17, 신규 `tests/test_ux8_filter_fold.py` 포함).

- **전체 스위트(qa-engineer 실행)**: `python -m pytest -q -p no:cacheprovider` → `1880 passed, 3 xfailed, 1083 warnings`, 480s. 실패·에러·스킵 0.
  지시한 `NC_NO_SCHEDULER=1` 앞붙임은 권한 대기로 막혀 빼고 돌렸다(시간만 늘어남).
- **Steward 재현(부분)**: `tests/test_ux8_filter_fold.py` + `test_feat1_qa_adversarial.py` + `test_feat2_qa_adversarial.py`
  → `176 passed, 3 xfailed` (141s). xfail 3건 수·위치가 qa 보고와 일치. 전체 1880건 수치는 Steward 가 다시 세지 않았다.
- **xfail 3건** = 테스트 파일에 "기존 틈"으로 적힌 strict 표식(count API 가 `promising` 미반영 · count API 음수 upcoming 미클램프 · 제조사 페이지 `SELECT DISTINCT maker` 4회). 신규 회귀 아님. 경고는 전부 deprecation(FastAPI `on_event`·`TemplateResponse` 인자 순서·websockets legacy).

범위 밖 메모(추정·인계 아님): 미커밋 UX8 작업은 테스트만 통과했을 뿐 6개 폭 측정·디자인 검수는 이 지시서에서 하지 않았다 — 그 작업의 지시서에서 확인할 것.
