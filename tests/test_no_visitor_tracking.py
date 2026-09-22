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


# ── 더 조용한 구멍: 사람이 시키는 경로 ─────────────────────────────────────
# cron 을 막아도 분석가에게 "이탈률 원인을 보라"고 시키면 같은 표가 다시 나온다. 실제로
# 2026-09-22 그날, 집계를 없애기로 결정한 시점에 `insight` 에이전트가 바로 그 지시로 돌고
# 있었다. 그래서 세 에이전트 정의에 "직접 집계하지 마라"를 적었고, 여기서 그 문단이
# 살아 있는지 본다. 토큰 금지 방식은 못 쓴다 — 금지 문구 자체에 '방문자·IP' 가 들어 있다.
SENTINEL = "IP 로 묶어 방문자를 세는 것은"
GUARDED_AGENTS = ("insight.md", "growth.md", "voice.md")


@pytest.mark.parametrize("agent", GUARDED_AGENTS)
def test_에이전트_정의가_로그_직접_집계를_금지하고_있다(agent):
    """★ 코드가 아니라 **지시**로 되돌아오는 길을 막는다.

    `voice` 는 특히 축이 바뀌었다. 예전 정의는 "리뷰가 0건이어도 행동 데이터는 있다"를
    판단의 근거로 삼았는데, 이제 0건이면 **정말로 모른다.** 그 문장을 조용히 빼지 않고
    "더는 사실이 아니다"라고 적어 둔 이유다 — 없어진 근거를 모르는 채 쓰는 것이 제일 나쁘다.
    """
    body = (ROOT / ".claude" / "agents" / agent).read_text(encoding="utf-8")
    assert SENTINEL in body, (
        f".claude/agents/{agent} 에서 접속 로그 직접 집계 금지 문단이 사라졌다. "
        "에이전트가 ssh 로 /var/log/nginx 를 집계하면 tools/ 에서 뺀 것이 그대로 돌아온다 — "
        "Play '수집된 데이터 없음' 신고가 다시 거짓이 된다(docs/ORG.md §4).")
