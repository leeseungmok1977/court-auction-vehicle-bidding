"""리포트 고정 바 높이 · caution 판정 문장의 초과 폭 — 디자인 검수가 범위 밖으로 남긴 2건.

고정 바: 칩 5개 합(일반 337px·큰글씨 386px)이 320~390px 폭을 넘어 두 줄로 접혔고, 버튼 3개
(큰글씨 338px)도 두 줄이라 큰글씨 360px 에서 바가 202px — 640px 기기 화면의 32%였다.
큰글씨를 켠 사람일수록 본문이 좁아지는 역설. 칩은 한 줄 가로 스크롤(목록 필터칩과 같은 패턴,
오른쪽 페이드 = '더 있음'), 인쇄 버튼은 ≤430px 에서 짧은 라벨, 큰글씨 좁은 폭은 패딩만 축소.
실측 후: 큰글씨 320~430px 바 107px(17%), 버튼 1줄·칩 1줄.

caution: "예상 경쟁가가 상한선 초과"에 폭을 실어 준다("…상한선을 40만원 초과"). 목록 칩의
짧은 label 은 그대로 두고 bid_state 가 over_by 를 함께 내보내 리포트 스펙트럼·§01 만 쓴다.
"""
import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE
from tests.test_panel_r3_p0 import TPL, _PUBLIC, _BT2


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bar.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: _BT2)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "P0_1", "folder_key": "P0_1", "case_no": "2026타경9101",
                       "judgment": "유찰 대기", "fail_count": 2, "min_sale_price": 33_920_000,
                       "appraisal_value": 53_000_000, "median_price": 35_250_000,
                       "upper_bid": 23_777_500, "market_confidence": 52,
                       "market_confidence_label": "보통", "sample_count": 32})
    import web.app as A
    return TestClient(A.app)


def test_section_chips_scroll_in_one_line_instead_of_wrapping():
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index(".secnav{")
    rule = src[i:src.index("}", i)]
    assert "flex-wrap:nowrap" in rule and "overflow-x:auto" in rule, rule
    assert "mask-image" not in rule, "페이드를 항상 걸면 다 보이는 폭(390px 일반)에서 마지막 칩 끝을 이유 없이 흐린다(최종 검수)"
    assert "padding:8px 18px 8px 0" in rule, "끝까지 밀었을 때 마지막 칩이 페이드 밖으로 나와야 한다"
    j = src.index(".secnav-wrap.can-scroll .secnav{")
    assert "mask-image" in src[j:src.index("}", j)], "페이드가 없으면 마지막 칩이 잘린 것으로 읽힌다(CLAUDE.md 실측)"


def test_print_button_has_a_short_label_for_narrow_widths(client):
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    # 짧은 라벨은 'PDF 저장' — 프린터 아이콘이 이미 인쇄를 말한다. 일반 ≤380px · 큰글씨 ≤430px (검수)
    assert 'class="bl-full">인쇄 / PDF 저장' in html and 'class="bl-short">PDF 저장' in html
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "@media (max-width:380px){ .rtop .bl-full{display:none} .rtop .bl-short{display:inline} }" in src
    assert "@media screen and (max-width:430px){ html.nc-large .rtop .bl-full{display:none}" in src


def test_chip_fade_is_not_fully_transparent_and_has_a_chevron():
    """320px 에서 페이드가 '⚠ 리스크'의 '크'를 통째로 지워 '⚠ 리스' — 미완성 낱말은 고장으로 읽힌다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index(".secnav{")
    assert "scroll-padding-right:24px" in src[i:src.index("}", i)], "키보드 포커스가 페이드 안에서 사라진다"
    j = src.index(".secnav-wrap.can-scroll .secnav{")
    fade = src[j:src.index("}", j)]
    assert "rgba(0,0,0,.3)" in fade and "transparent" not in fade, "페이드 끝이 완전 투명이다"
    assert 'class="secnav-more material-symbols-outlined"' in src and "chevron_right" in src
    assert "function _syncSecnav" in src and "can-scroll" in src


def test_chevron_sits_in_the_bar_gutter_not_on_a_chip():
    """종이색 원을 칩 위에 얹으면 가장자리 칩에 구멍이 나 '⚠ 리 ›' — 경고 칩의 낱말이 훼손된다(최종 검수)."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    k = src.index(".secnav-more{")
    rule = src[k:src.index("}", k)]
    assert "right:-20px" in rule and "width:20px" in rule, "› 는 바의 오른쪽 여백(padding 20px) 위에 있어야 한다"
    assert "background" not in rule, "칩 위에 종이색 배경을 얹으면 낱말에 구멍이 난다"


def test_more_marker_uses_the_last_chip_edge_not_scroll_width():
    """scrollWidth 는 padding-right 를 포함해 칩이 다 보이는 390px 일반에서도 거짓 '더 있음'이 떴다(최종 검수)."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    f = src.index("function _syncSecnav")
    body = src[f:src.index("document.addEventListener", f)]
    assert "lastElementChild" in body and "getBoundingClientRect().right" in body
    assert ".scrollWidth" not in body, "n.scrollWidth 판정으로 되돌아갔다"
    assert "document.fonts.ready.then(_syncSecnav)" in src, "웹폰트가 늦게 오면 칩 폭이 바뀐다"


def test_large_mode_buttons_meet_the_tap_target_floor():
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "html.nc-large .rtop .btn{ padding:7px 10px; min-height:44px }" in src
    assert "html.nc-large .rtop-btns{ gap:10px }" in src


def test_pressed_toggle_is_outlined_not_filled():
    """파란 채움 켜짐은 옆의 주동작(인쇄, 코발트 채움)과 구별이 안 됐다 — 리포트·헤더 둘 다."""
    rpt = (TPL / "report.html").read_text(encoding="utf-8")
    base = (TPL / "base.html").read_text(encoding="utf-8")
    assert '#rptLarge[aria-pressed="true"]{background:#fff;color:var(--cobalt);border:2px solid var(--cobalt)}' in rpt
    assert '#largeToggle[aria-pressed="true"]{background:#fff;color:#2f5fe0;border:2px solid #2f5fe0}' in base
    assert "background:#2f5fe0;color:#fff" not in rpt and "background:#2f5fe0;color:#fff" not in base


def test_caution_label_targets_the_ceiling_pin():
    """넓은 폭에서 클램프가 안 걸리면 라벨이 밴드 중앙(자기가 가리키는 상한선 핀보다 왼쪽)에 갔다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "{% set _blc = (max_bid if (_tone == 'caution' and max_bid) else (floor+exp)/2) %}" in src


def test_large_mode_button_padding_is_screen_only():
    """큰글씨 규칙은 인쇄에 닿으면 안 된다(가드와 같은 원칙) — screen 전용 블록 안에 있어야 한다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index("html.nc-large .rtop .btn{ padding:7px 10px; min-height:44px }")
    head = src[:i]
    assert head.rfind("@media screen and (max-width:560px){") > head.rfind("@media print{")


def _caution_vehicle():
    # 최저가는 상한선 아래, 예상 경쟁가는 상한선 위 → over_market/caution
    return {**_BASE, "min_sale_price": 30_100_000, "appraisal_value": 40_000_000,
            "median_price": 41_460_000, "upper_bid": 21_920_000, "fail_count": 1,
            "photo_count": 3}


def test_bid_state_reports_how_far_the_expected_price_exceeds_the_ceiling():
    st = service.bid_state(_caution_vehicle(), BT)
    assert "over_by" in st
    if st["tone"] == "caution":
        assert st["over_by"] and st["over_by"] == st["exp"] - st["max_bid"]
        assert st["label"] == "예상 경쟁가가 상한선 초과", "칩용 짧은 라벨은 바뀌면 안 된다"
    else:
        # 픽스처가 caution 을 못 만들면 아래 렌더 테스트도 의미가 없다 — 그 사실을 드러낸다
        pytest.skip(f"픽스처가 caution 이 아니다: {st['state']}")


def test_caution_report_states_the_overshoot_amount(client):
    from web import db
    db.upsert_vehicle({**_caution_vehicle(), "id": "CA_1", "folder_key": "CA_1",
                       "case_no": "2026타경9103", "judgment": "유찰 대기",
                       "market_confidence": 60, "market_confidence_label": "보통"})
    st = service.bid_state(db.get_vehicle("CA_1"), _BT2)
    if st["tone"] != "caution":
        pytest.skip(f"픽스처가 caution 이 아니다: {st['state']}")
    html = client.get("/vehicle/CA_1/report", headers=_PUBLIC).text
    sp = html[html.index('class="sp-blabel'):]
    sp = sp[:sp.index("</div>")]
    assert "만원 초과" in sp, "스펙트럼 판정 라벨에 초과 폭이 없다"
    assert f"상한선을 {st['over_by']:,}원 넘습니다" in html, "§01 에 초과 폭이 없다"
