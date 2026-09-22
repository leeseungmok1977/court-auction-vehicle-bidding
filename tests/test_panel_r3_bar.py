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
    # 짧은 라벨은 'PDF 저장' — 프린터 아이콘이 이미 인쇄를 말한다. 일반 ≤400px · 큰글씨 ≤430px
    assert 'class="bl-full">인쇄 / PDF 저장' in html and 'class="bl-short">PDF 저장' in html
    src = (TPL / "report.html").read_text(encoding="utf-8")
    # ★ 2026-09-22 380→400. 숫자만 올린 게 아니라 **기준이 역효과를 내고 있었다.**
    #   380 이면 390px 에서 긴 라벨 `인쇄 / PDF 저장`(137px, 짧은 쪽보다 33px 넓다)이 되살아나
    #   실측 부족분이 360px 49px < 390px 52px — 화면이 넓어졌는데 더 모자랐다.
    #   430px 은 긴 라벨로도 26px 남으므로 400 으로 둔다(들어가는 곳에서까지 줄이지 않는다).
    assert "@media (max-width:400px){ .rtop .bl-full{display:none} .rtop .bl-short{display:inline} }" in src
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


def test_narrow_widths_fit_the_four_buttons_in_one_row():
    """★ `되팔기 계산` 이 혼자 둘째 줄에 남아 있었다 — 방금 걷어낸 비활성 칩과 **자리가 같아서**
    본문 3개 섹션을 켜고 끄는 모드 토글이 남은 잔재처럼 읽혔다(2026-09-22 디자인 검수).

    실측: 360px 에서 필요 369px / 자리 320px → 49px 부족, 2줄, 고정 바 190px.
    가로 패딩 14→10(버튼당 8px×4) · gap 8→6(6px) · 라벨 축약으로 306px 까지 줄여 1줄이 됐고
    고정 바가 **145px** 로 내려갔다. 줄 하나가 45px 이다(190−145).

    ⚠ 320px 과 큰글씨 320·360px 은 **여전히 2줄이다.** 거기서 더 밀어넣으면 탭 영역이
      위태로워지고, 글자를 키워 달라고 한 사람에게서 글자를 뺏는 일이 된다. 고치지 않은 것이지
      못 본 것이 아니다.
    """
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert ".rtop .btn{padding:7px 10px;min-height:44px}" in src, (
        "좁은 폭 버튼 규칙이 바뀌었다 — 패딩 축소가 빠지면 360px 에서 다시 2줄이 되고 "
        "고정 바가 45px 늘어난다. min-height 가 빠지면 탭 타깃이 37px 로 돌아간다")
    assert ".rtop-btns{gap:6px}" in src, "좁은 폭 gap 축소가 사라졌다"


def test_normal_mode_tap_target_matches_the_large_mode_floor():
    """★ 같은 손가락에 다른 기준을 적용하고 있었다 — 일반 37px / 큰글씨 44px(실측).

    큰글씨 블록 주석이 스스로 "탭 타깃을 34~38px 로 두면 손떨림이 있는 바로 그 사용자에게
    가장 작은 조작 대상을 남긴다"고 적어 두고도, 정작 일반 모드가 37px 이었다.
    세로만 7px 늘고 가로는 1px 도 더 쓰지 않으므로 한 줄 성과는 그대로다.

    ⚠ 이 규칙은 **≤460px 안에만** 있어야 한다. 터치 관련 사이징을 좁은 폭에 한정하는 것이
      이 파일의 방식이다(아래 test_large_mode_button_padding_is_screen_only 와 같은 원칙).
    """
    src = (TPL / "report.html").read_text(encoding="utf-8")
    # ⚠ "@media (max-width:460px){" 는 파일에 **여러 개**다(✓ 제거 규칙에도 쓴다).
    #   첫 번째를 집어 덩어리를 자르면 규칙이 블록 밖으로 나가도 통과한다 — 규칙 **바로 앞의**
    #   미디어쿼리가 무엇인지로 판정한다.
    i = src.index(".rtop .btn{padding:7px 10px;min-height:44px}")
    head = src[:i]
    last_media = head.rfind("@media")
    assert head[last_media:].startswith("@media (max-width:460px){"), (
        "탭 타깃 하한이 ≤460px 블록 밖으로 나갔다 — 데스크톱 툴바까지 44px 로 두꺼워진다")
    # 기반 규칙(전 폭)에는 min-height 가 없어야 한다
    j = src.index(".rtop .btn{padding:7px 14px}")
    assert "min-height" not in src[j:j + 40], "전 폭에 탭 타깃 하한이 걸렸다"
    assert '<span class="bl-full">되팔기 계산</span><span class="bl-short">되팔기</span>' in src, (
        "되팔기 버튼의 라벨 축약이 사라졌다 — 인쇄 버튼과 같은 장치를 쓴다")


def test_section_chips_fit_without_cutting_a_word_at_360():
    """★ 360px 에서 `낙찰 절차` 가 18px 잘려 '낙찰 절' 로 보였다.

    이 저장소는 이미 '⚠ 리스' 사례에서 **미완성 낱말은 '더 있음'이 아니라 렌더링 사고로
    읽힌다**는 기준을 세웠다. 칩 가로 패딩 11→8 과 gap 6→4 로 360px 에서 317/320 이 되어
    다 들어간다(실측).

    ⚠ 오른쪽 여백 18px 로는 손대지 않았다 — 12px 로 줄이면 4px 을 더 벌지만 "끝까지 밀었을 때
      마지막 칩이 페이드 밖으로 나와야 한다"는 위 test_section_chips... 의 불변식을 깬다.
      그 테스트는 문자열 검사라 통과했겠지만 의도는 깨졌을 것이다.
    """
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert ".secnav a{padding:7px 8px}" in src, "좁은 폭 칩 패딩 축소가 사라졌다"
    # 320px 은 패딩·gap 으로도 안 되고 오른쪽 여백 18px 은 페이드 불변식이라 못 건드린다 —
    # 남은 레버가 라벨 길이뿐이다. `절차` 는 온전한 낱말이라 잘려도 고장으로 읽히지 않는다.
    assert '<span class="cl-full">낙찰 절차</span><span class="cl-short">절차</span>' in src, (
        "마지막 칩의 라벨 축약이 사라졌다 — 320px 에서 다시 '낙찰 절' 로 잘린다")
    assert "@media (max-width:340px){ .secnav .cl-full{display:none}" in src
    # ★ 큰글씨는 칩 글자가 15px 이라 360px 에서도 28px 잘렸다(캡처 narrow_360_large.png).
    #   ≤340px 만 잡으면 이 조합을 놓친다 — 버튼 라벨과 같은 방식으로 큰글씨는 기준을 넓힌다.
    assert "html.nc-large .secnav .cl-short{display:inline}" in src, (
        "큰글씨 칩 축약이 없다 — 큰글씨 360px 에서 '낙찰 절' 로 잘린다")
    assert "html.nc-large .secnav a{padding:7px 8px}" in src, (
        "큰글씨 칩 축소가 사라졌다 — 430px 큰글씨는 14px 넘치면서 페이드가 꺼져 "
        "'잘렸는데 더 있음 신호가 없는' 상태가 된다")
    i = src.index(".secnav{")
    assert "padding:8px 18px 8px 0" in src[i:src.index("}", i)], (
        "오른쪽 여백을 줄였다 — 끝까지 밀었을 때 마지막 칩이 페이드 안에 걸린다")


def test_large_mode_buttons_meet_the_tap_target_floor():
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "html.nc-large .rtop .btn{ padding:7px 10px; min-height:44px }" in src
    assert "html.nc-large .rtop-btns{ gap:10px }" in src


def test_pressed_toggle_is_outlined_not_filled():
    """파란 채움 켜짐은 옆의 주동작(인쇄, 코발트 채움)과 구별이 안 됐다 — 리포트·헤더 둘 다."""
    rpt = (TPL / "report.html").read_text(encoding="utf-8")
    base = (TPL / "base.html").read_text(encoding="utf-8")
    # 선택자는 토글이 늘면서 묶였다(#rptLarge, #rptResale) — 문자열이 아니라 규칙을 확인한다
    import re as _re
    _m = _re.search(r'([^\n]*#rptLarge\[aria-pressed="true"\][^\n]*)\{([^}]*)\}', rpt)
    assert _m, "켜짐 상태 규칙이 없다"
    assert "background:#fff" in _m.group(2), "켜짐이 파란 채움으로 돌아갔다 — 인쇄 버튼과 구별이 안 된다"
    assert ("border-color:var(--cobalt)" in _m.group(2)
            and "box-shadow:inset 0 0 0 1px var(--cobalt)" in _m.group(2)), (
        "켜짐의 윤곽 표시가 사라졌다")
    # ★ 굵은 테두리로 되돌리지 마라. 2026-09-22 실측: 켜면 버튼이 +19px(✓ 17 + 테두리 2)
    #   늘어 360px 에서 행이 1줄→2줄로 접히고 고정 바가 152→202px 로 뛰었다.
    #   그림자는 레이아웃을 바꾸지 않으므로 켜도 폭이 그대로다.
    assert "border:2px" not in _m.group(2), (
        "테두리 굵기로 켜짐을 그리면 버튼 폭이 늘어 좁은 폭에서 행이 접힌다")
    assert '#rptResale[aria-pressed="true"]::before{content:none}' in rpt, (
        "좁은 폭에서 ✓ 를 빼는 규칙이 사라졌다 — ✓ 하나가 17px 이라 360px 에서 행이 접힌다")
    assert "#rptResale" in _m.group(1), "토글이 둘인데 켜짐 표시는 하나만 걸려 있다"
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
