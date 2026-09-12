# 주간 전문가 패널 리포트

중고차·앱디자인·경매·앱품질 전문가 4인(에이전트)이 매주 라이브 앱을 직접 써보고
100점 루브릭으로 채점한 기록이다. 파일명은 평가일(`YYYY-MM-DD.md`).

- 실행: `/weekly-expert-review` (정의: `.claude/skills/weekly-expert-review/SKILL.md`)
- 에이전트 정의: `.claude/agents/{usedcar-expert,app-design-expert,auction-expert,app-qa-auditor}.md`
- 공통 제약·제품 범위: `.claude/agents/_panel-context.md`
- 스크린샷: `screenshots/weekly/YYYY-MM-DD/`

## 읽는 법
점수 자체보다 **합의 지적**(둘 이상이 같은 문제를 지적한 것)과 **회차 간 증감**을 본다.
한 명만 지적한 것은 관점 차이일 수 있지만, 둘 이상이 겹치면 실제 결함일 가능성이 높다.

## 회차
| 날짜 | 중고차 | 디자인 | 경매 | 품질 | 한 줄 결론 |
|---|---|---|---|---|---|
| [2026-09-12](2026-09-12.md) | 66 | 65 | 68 | 73 | 시세 초과 물건을 '검토 가능'으로 권하고, 리포트 첫 줄 비율이 틀림 |
