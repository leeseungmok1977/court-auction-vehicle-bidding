# -*- coding: utf-8 -*-
"""접속 로그로 방문자를 세지 않는다 — Play '수집된 데이터 없음' 신고를 지키는 벽.

2026-09-22 오너 결정. 사정은 이렇다.

일일·주간 리포트가 nginx 접속 로그를 **IP 로 묶어** 방문자수·1페이지 이탈률을 냈다.
Google Play 데이터 안전의 '앱 상호작용'은 원문이 *"the number of times they visit a page"*
이고, 일시적 사용 면제는 *"only stored in memory and retained for no longer than necessary
to service the specific request in real-time"* 이다 — 하루치 집계를 리포트로 만들어
저장소에 커밋하는 것은 그 면제에 해당하지 않는다.

더 결정적인 건 **우리 방침이 스스로 내건 근거**였다. `privacy.html` 은
"분석·프로필 연결·외부 제공이 없고 … 그러므로 '수집 없음'으로 신고했습니다"라고 적어 두었다.
집계를 하는 순간 그 문장이 거짓이 된다 — 해석의 여지가 아니라 자기모순이다.

그래서 지표를 포기하고 **코드를 뺐다.** 잃은 것도 적어 둔다: 1페이지 이탈률(67%)과
외부 유입 건수(하루 2.8건)를 더는 못 잰다. 출시 후에는 Play Console·Search Console 이
우리 서버에서 아무것도 모으지 않고 같은 질문에 답한다.

이 테스트는 그 코드가 **조용히 돌아오는 것**을 막는다. 되살리려면 신고 변경과 방침 수정이
먼저다 — 코드만 되살리면 스토어 신고가 허위가 된다.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("daily_ops_report.py", "weekly_report.py", "monthly_report.py")

# 설명문에는 '방문자'·'IP' 가 남아 있어야 한다(왜 뺐는지를 적어 둔 주석이다).
# 그래서 낱말이 아니라 **집계 코드에만 나오는 토큰**을 막는다.
FORBIDDEN = {
    "bounce_pct": "1페이지 이탈률 — 방문자별 페이지뷰를 세야만 나온다",
    "deep_pct": "심층 열람률 — 같은 계산의 다른 얼굴",
    '"visitors"': "방문자 수 집계 키",
    "access.log": "nginx 접속 로그 읽기",
    "/var/log/nginx": "nginx 로그 경로",
}


@pytest.mark.parametrize("name", TOOLS)
def test_보고서_도구가_접속_로그로_방문자를_세지_않는다(name):
    """★ 이 셋이 한 줄로 이어져 있었다 — 일일이 표를 만들고 월간이 그 표를 파싱했다.

    하나만 빼면 나머지가 같은 신고 모순을 그대로 안고 돈다. 그래서 셋을 함께 막는다.
    """
    body = (ROOT / "tools" / name).read_text(encoding="utf-8")
    hit = [f"{tok} ({why})" for tok, why in FORBIDDEN.items() if tok in body]
    assert not hit, (
        f"tools/{name} 에 방문자 집계가 돌아왔다: {', '.join(hit)}\n"
        "Play '수집된 데이터 없음' 신고와 개인정보처리방침이 함께 거짓이 된다. "
        "되살리려면 신고·방침을 먼저 고쳐야 한다(docs/ORG.md §4).")


def test_방침이_내건_근거_문장이_그대로_있다():
    """★ 이 문장이 '수집 없음' 신고의 근거다 — 사라지거나 바뀌면 위 테스트의 전제도 바뀐다.

    문구를 고치는 사람이 이 파일을 보게 만드는 것이 목적이다. 방침을 바꾸는 것 자체는
    오너 승인 사항이며(docs/ORG.md §3 개인정보 수집 범위 변경), 코드만 되살리는 길을 막는다.
    """
    body = (ROOT / "web" / "templates" / "privacy.html").read_text(encoding="utf-8")
    assert "분석·프로필 연결·외부 제공이 없고" in body, (
        "개인정보처리방침에서 '수집 없음' 신고의 근거 문장이 사라졌다. "
        "방침을 바꾼 것이라면 tools/ 의 집계 금지도 함께 재검토해야 한다.")


def test_월간이_일일_리포트에서_방문자_표를_파싱하지_않는다():
    """원천이 사라졌는데 파서가 남아 있으면 '기록 없음'을 매달 사실처럼 출력한다."""
    body = (ROOT / "tools" / "monthly_report.py").read_text(encoding="utf-8")
    assert "read_daily_visitors" not in body, (
        "월간 보고서가 아직 일일 리포트의 방문자 표를 읽으려 한다 — 죽은 경로다")
    assert "## 방문자" not in body, "방문자 표 파싱 문자열이 남아 있다"
