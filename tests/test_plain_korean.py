"""60·70대 축 — 사용자에게 보이는 글에 영문 전문용어를 쓰지 않는다.

18인 패널 재평가에서 60·70대 세그먼트만 **±0.00**으로 전혀 안 움직였다. 지적은
두 갈래였다.

  (1) 읽을 수 없는 말: STOP RULE · All-in Cost · CONFIDENCE · LOO MAE ·
      Leave-One-Out · AUTOBID REPORT · MAE · D-day · IQR
  (2) 같은 뜻으로 읽히는 숫자가 여러 개: 신뢰도 76 / 적중 25% / 표본 38

(2)의 뿌리는 더 나빴다. 리포트에서 **같은 값 하나가 네 이름으로** 불렸다 —
머리말 `CONFIDENCE 72/100`, §01 `본 결론의 신뢰도 72/100`, §02 헤드라인 `72/100`,
그리고 그 바로 아래 막대 `시장 가격 72`. 게다가 다섯 축 평균(71.4)이 우연히 72와
비슷해 헤드라인이 **종합점수처럼** 읽혔다. 실제로는 시세 하나의 점수다.

축 점수를 합산해 종합점수를 만들지 않는다는 원칙(육각형 각주)이 이미 있으므로,
새 합성 점수를 만드는 대신 **이름을 하나로** 고정하고 중복 막대를 지웠다.
"""
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

# 화면에 그대로 나가면 안 되는 말. 값은 대체 표현(에러 메시지에 실어 보낸다).
BANNED = {
    "STOP RULE": "입찰 중단 기준",
    "All-in Cost": "총 취득원가",
    "CONFIDENCE": "시세 신뢰도",
    "LOO MAE": "예측 오차",
    "Leave-One-Out": "그 차를 빼고 예측",
    "AUTOBID REPORT": "차량경매 분석 리포트",
    "(MAE": "평균 오차",
    "D-day": "매각기일 가까운 순",
}
# 관리자 화면에만 남겨둔 말 — 원자료를 직접 대조하는 사람에게는 IQR 이 오히려 정확하다.
# 소스 스캔은 관리자/공개를 구분하지 못하므로, 이런 항목은 **렌더된 공개 응답**으로만 잡는다.
BANNED_PUBLIC_ONLY = {"IQR": "값이 유난히 튀는 매물을 걸러낸 뒤"}

_TAGSTRIP = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->|\{#.*?#\}", re.S)


def _visible(path: pathlib.Path) -> str:
    """주석·스크립트·스타일을 뺀, 사람이 읽는 자리의 텍스트."""
    return _COMMENT.sub(" ", _TAGSTRIP.sub(" ", path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("tpl", sorted(p.name for p in TPL.glob("*.html")))
def test_no_english_jargon_in_templates(tpl):
    src = _visible(TPL / tpl)
    hit = [f"{t} → '{ko}'" for t, ko in BANNED.items() if t in src]
    assert not hit, f"{tpl}: 영문 전문용어가 남았다 — " + " / ".join(hit)


@pytest.mark.parametrize("path", ["/", "/vehicles", "/vehicle/K1_1",
                                  "/vehicle/K1_1/report", "/accuracy", "/watchlist",
                                  "/calendar", "/landing"])
def test_no_english_jargon_on_public_screens(client, path):
    """실제로 공개 사용자에게 나가는 HTML 기준 — 관리자 전용 문구는 여기 안 나온다."""
    # 주석·스타일은 화면이 아니다 — 사람이 읽는 자리만 본다
    html = _COMMENT.sub(" ", _TAGSTRIP.sub(" ", client.get(path, headers=_PUBLIC).text))
    hit = [f"{t} → '{ko}'" for t, ko in {**BANNED, **BANNED_PUBLIC_ONLY}.items()
           if t in html]
    assert not hit, f"{path}: " + " / ".join(hit)


def test_admin_keeps_the_precise_term(client):
    """평이화가 관리자용 정확한 표현까지 지우지 않았는지 — IQR 은 대조하는 사람에겐 정확하다."""
    html = client.get("/vehicle/K1_1", headers={"host": "127.0.0.1"}).text
    assert "IQR" in html


def test_the_scanner_would_actually_catch_something():
    """가드 — 주석 제거가 과해서 본문까지 날리면 이 파일이 아무것도 안 지킨다."""
    src = _visible(TPL / "report.html")
    assert "총 취득원가" in src and "입찰 중단 기준" in src
    assert len(src) > 20000, "본문이 통째로 사라졌다 — 스캐너가 고장났다"


# ── 신뢰도 척도: 같은 숫자에 이름 하나 ────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ko.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "K1_1", "folder_key": "K1_1",
                       "case_no": "2026타경8001", "judgment": "유찰 대기",
                       "min_sale_price": 10_000_000, "appraisal_value": 12_000_000,
                       "median_price": 13_000_000, "market_confidence": 72,
                       "market_confidence_label": "높음", "sample_count": 21,
                       "market_cv": 0.14, "analyzed_at": "2026-09-05 10:00:00",
                       "match_label": "동급 (연식±1·주행±30%)·가솔린·동세대",
                       "comps": [{"year": 2020, "mileage_km": 50000,
                                  "price_won": 12_800_000, "badge": "x"}]})
    import web.app as A
    return TestClient(A.app)


def test_the_same_score_is_not_shown_twice_in_one_card():
    """§02 헤드라인 숫자와 그 아래 막대에 같은 72가 두 번 찍혔다."""
    from web import db
    v = dict(db.get_vehicle("x") or {}, market_confidence=72, median_price=13_000_000,
             min_sale_price=10_000_000, photo_count=3)
    cats = service.report_data(v, service.load_config(), BT)["cats"]
    names = [c["name"] for c in cats]
    assert "시장 가격" not in names, "헤드라인과 같은 값의 막대가 남아 있다"
    assert all(c["score"] != 72 or c["name"] != "시장 가격" for c in cats)
    assert len(cats) >= 4, f"막대를 너무 많이 지웠다: {names}"


def test_headline_score_is_named(client):
    """이름 없는 큰 숫자는 다섯 축 평균(종합점수)으로 오독된다."""
    html = client.get("/vehicle/K1_1/report", headers=_PUBLIC).text
    head = html[html.index('id="sec02"'):]
    head = head[:head.index("모델 검증 실적")] if "모델 검증 실적" in head else head[:4000]
    assert "시세 신뢰도" in head, "§02 헤드라인 숫자에 이름이 없다"


def test_one_name_for_one_number_across_the_report(client):
    """머리말·§01·§02·꼬리말이 같은 값을 같은 이름으로 불러야 한다."""
    html = client.get("/vehicle/K1_1/report", headers=_PUBLIC).text
    assert html.count("시세 신뢰도") >= 3, "이름이 일부에만 붙었다"
    assert "본 결론의 신뢰도" not in html, "같은 값에 다른 이름이 남았다"
    assert "CONFIDENCE" not in html


def test_large_font_button_says_what_it_does(client):
    """'가+' 는 60·70대에게 읽히지 않는다. 헤더 여유가 40px 뿐이라 4글자는 못 넣는다."""
    html = client.get("/vehicles", headers=_PUBLIC).text
    btn = html[html.index('id="largeToggle"'):]
    btn = btn[:btn.index("</button>")]
    assert "큰글씨" in btn and "가+" not in btn


# ── 큰글씨 모드가 리포트에도 걸리는가 ──────────────────────────────
# 리포트는 base.html 을 쓰지 않는 **독립 문서**라 헤더 토글이 여기엔 안 걸렸다.
# 60·70대에게 글이 가장 많고 판단이 가장 무거운 화면만 접근성 옵션에서 빠져 있었다
# (2026-09-13 디자인 검수). 목록에서 켜고 넘어오면 그대로 유지돼야 한다.

def test_report_participates_in_large_font_mode(client):
    html = client.get("/vehicle/K1_1/report", headers=_PUBLIC).text
    assert 'localStorage.getItem("naechaget:large")' in html,         "선적용 스크립트가 없다 — 목록에서 켜고 와도 리포트만 작게 나온다"
    assert "nc-large" in html and html.count("html.nc-large") > 30,         "px 고정 본문을 재선언하지 않으면 루트 확대로는 한 글자도 안 커진다"
    assert 'id="rptLarge"' in html, "리포트로 바로 들어온 사람이 켤 방법이 없다"


def test_large_mode_uses_the_same_storage_key_as_the_header():
    """다른 키를 쓰면 화면을 옮길 때마다 상태가 끊긴다."""
    rpt = (TPL / "report.html").read_text(encoding="utf-8")
    base = (TPL / "base.html").read_text(encoding="utf-8")
    assert "naechaget:large" in rpt and "naechaget:large" in base
    assert "nc_large" not in rpt, "다른 저장 키를 쓴다"


def test_large_mode_does_not_touch_printing():
    """종이 크기는 고정이라 확대하면 넘쳐 잘린다 — 화면에서만 확대한다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index("html.nc-large")
    head = src[:i]
    assert head.rstrip().endswith("@media screen{"),         "큰글씨 규칙이 @media screen 밖에 있어 인쇄까지 확대된다"
    # 주석에는 이 낱말이 '왜 안 쓰는지'로 남아 있다 — 실제 선언만 본다
    import re as _re
    code = _re.sub(r"/\*.*?\*/", " ", src, flags=_re.S)
    assert "font-size:revert" not in code, \
        "revert 는 작성자 스타일이 아니라 브라우저 기본값으로 되돌린다 — 인쇄가 깨진다"


def test_large_mode_scales_the_body_text():
    """생성된 재선언이 실제로 더 큰 값인지 — 같은 값을 다시 쓰면 아무 일도 안 일어난다."""
    import re as _re
    src = (TPL / "report.html").read_text(encoding="utf-8")
    base = float(_re.search(r"^body\{[^}]*font-size:([0-9.]+)px", src, _re.M).group(1))
    big = float(_re.search(r"html\.nc-large body\{font-size:([0-9.]+)px\}", src).group(1))
    assert big > base * 1.2, f"본문이 안 커졌다: {base}px → {big}px"


def test_narrow_large_header_keeps_the_search_icon():
    """320px + 큰글씨에서 헤더가 넘쳐 검색 아이콘이 잘린 적이 두 번 있다.

    1차(3회차 검수): 루트 폰트를 125%로 올렸을 때.
    2차(2026-09-13): '가+'를 '큰글씨' 알약으로 키웠을 때 — 우측 합 328px > 320px.
    둘 다 워드마크·로고를 줄여 아이콘을 지키는 방식으로 풀었다. 그 규칙이 사라지면
    다음 사람이 같은 함정에 다시 빠진다.

    실측(Playwright, 320·360·390·430·768 × ON/OFF)은 넘침 0건·여유 40px 이상.
    여기서는 그 완충을 만든 **규칙이 살아 있는지**만 지킨다.
    """
    src = (TPL / "base.html").read_text(encoding="utf-8")
    i = src.find("@media (max-width:359px)")
    assert i > 0, "320px 큰글씨 완충 규칙이 없다 — 검색 아이콘이 잘린다"
    block = src[i:src.index("}", src.index("}", i) + 1) + 1]
    assert "nc-large" in block and "nc-brand-name" in block, block
