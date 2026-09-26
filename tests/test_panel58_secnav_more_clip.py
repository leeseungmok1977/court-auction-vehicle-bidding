"""PANEL-58 — 시세 있는 리포트가 320·360px 에서 가로 스크롤 +91px.

원인은 섹션 칩이 아니라 칩 줄 오른쪽의 '더 있음' 표식 `<i class="secnav-more material-symbols-outlined">chevron_right</i>` 다.
Material Symbols 아이콘 폰트가 적용되기 전(첫 방문 수백 ms) 또는 못 받았을 때 리거처 이름 `chevron_right` 가
13글자 낱말(18px 에서 약 111px)로 그려져 `width:20px` 상자를 뚫고 나가고, 그 상자가 바 오른쪽 여백 끝
(`right:-20px` = 뷰포트 끝)에 걸려 있어 문서가 정확히 그만큼 넓어졌다 — 320 에서 411, 360 에서 451(+91 동일).
woff2 를 차단하면 결정적으로 재현되고, 정상 로드에서도 fonts=loading 인 t≈560~690ms 창에서 같은 값이 찍혔다.
넘친 것은 요소가 아니라 **글자 줄**이라, 요소 rect 만 세는 측정에는 (스크롤 컨테이너 안이라 무해한) 섹션 칩만 잡혔다.
시세 없는 물건이 6폭 전부 0 이었던 이유는 고쳐서가 아니라 `{% if report %}` 가 바 자체를 안 그리기 때문이다.

`html.ms-pending` 의 visibility:hidden 과 @font-face 의 font-display:block 은 글자를 **안 보이게** 할 뿐
자리는 그대로 차지한다. 상자 안에서 잘라야(overflow:hidden) 문서 폭이 늘지 않는다.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE
from tests.test_panel_r3_p0 import TPL, _PUBLIC, _BT2


def _rule(src: str, head: str) -> str:
    """``head`` 로 시작하는 CSS 규칙 한 덩어리(여는 { 부터 닫는 } 까지)."""
    i = src.index(head)
    return src[i:src.index("}", i) + 1]


def _more_rule_clips(src: str) -> bool:
    """`.secnav-more{…}` 규칙이 상자 밖 글자 줄을 자르는가 — 판정 술어(테스트와 반증이 같은 술어를 쓴다)."""
    rule = _rule(src, ".secnav-more{")
    decls = {d.split(":", 1)[0].strip(): d.split(":", 1)[1].strip()
             for d in rule[rule.index("{") + 1:-1].split(";") if ":" in d}
    return decls.get("overflow") == "hidden" and decls.get("width") == "20px" and decls.get("right") == "-20px"


def test_more_marker_clips_the_unligatured_icon_name():
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert _more_rule_clips(src), _rule(src, ".secnav-more{")
    # 이유가 규칙 옆에 남아 있어야 다음 사람이 '왜 overflow:hidden 이지' 하고 지우지 않는다
    i = src.index(".secnav-more{")
    assert "PANEL-58" in src[src.rfind('/* PANEL-58', 0, i):i]  # 앵커 기반 — 매직 창은 주석이 늘면 낡는다(CLAUDE.md 규칙 8) and "chevron_right" in src[src.rfind('/* PANEL-58', 0, i):i]  # 앵커 기반 — 매직 창은 주석이 늘면 낡는다(CLAUDE.md 규칙 8)


def test_counterproof_the_predicate_fails_without_the_clip():
    """반증: overflow:hidden 만 빼면 같은 술어가 거짓이 된다 — 술어가 실제로 그 선언을 보고 있다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    rule = _rule(src, ".secnav-more{")
    stripped = src.replace(rule, rule.replace(";overflow:hidden", ""))
    assert stripped != src and not _more_rule_clips(stripped)
    # overflow 를 visible/clip 으로 바꿔도 거짓 — 'hidden' 만 통과한다(clip 은 iOS 15 이전 미지원)
    assert not _more_rule_clips(src.replace(rule, rule.replace("overflow:hidden", "overflow:visible")))


def test_scroll_container_and_gutter_marker_are_still_wired_as_before():
    """칩 줄은 여전히 overflow-x:auto 한 줄 스크롤이고, 표식은 바의 여백에 있으며 can-scroll 때만 보인다.
    (PANEL-58 은 여기에 잘라내기 한 줄만 더했다 — 기존 불변식이 그대로인지 같이 못 박는다.)"""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    nav = _rule(src, ".secnav{")
    assert "overflow-x:auto" in nav and "flex-wrap:nowrap" in nav
    more = _rule(src, ".secnav-more{")
    assert "display:none" in more and "background" not in more
    assert ".secnav-wrap.can-scroll .secnav-more{display:block}" in src


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p58.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: _BT2)
    db.init_db()
    common = {**_BASE, "judgment": "유찰 대기", "fail_count": 2, "min_sale_price": 4_500_000,
              "appraisal_value": 7_000_000, "upper_bid": 4_200_000}
    # 시세 있는 물건 — report_data 가 dict 를 돌려주고 바(칩 + 표식)가 그려진다
    db.upsert_vehicle({**common, "id": "P58_M", "folder_key": "P58_M", "case_no": "2026타경50403",
                       "median_price": 4_995_000, "market_confidence": 60,
                       "market_confidence_label": "보통", "sample_count": 26})
    # 시세 없는 물건 — report_data 가 None 이라 바 자체가 없다(반증: 0 이었던 이유는 고쳐서가 아니다)
    db.upsert_vehicle({**common, "id": "P58_N", "folder_key": "P58_N", "case_no": "2025타경73637",
                       "median_price": None, "sample_count": 0,
                       "judgment": "시세 신뢰도 낮음, 수동 검토"})
    import web.app as A
    return TestClient(A.app)


def test_rendered_report_with_market_carries_marker_and_clip_rule(client):
    html = client.get("/vehicle/P58_M/report", headers=_PUBLIC).text
    assert 'class="secnav-more material-symbols-outlined"' in html and ">chevron_right<" in html
    assert 'class="secnav"' in html
    assert _more_rule_clips(html), "렌더된 HTML 의 인라인 <style> 에 잘라내기 규칙이 없다"
    # 리거처 이름은 아이콘 폰트 클래스 안에서만 나와야 한다(폰트 없이 글자로 보일 자리를 더 만들지 않는다)
    assert len(re.findall(r">chevron_right<", html)) == 1


def test_counterproof_report_without_market_has_no_marker_at_all(client):
    html = client.get("/vehicle/P58_N/report", headers=_PUBLIC).text
    assert "secnav-more" not in html.split("<div class=\"page\"", 1)[1].split("<!-- 마스트헤드 -->", 1)[0]
    assert 'class="secnav"' not in html
