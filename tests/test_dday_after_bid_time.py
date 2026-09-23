"""끝난 경매에 빨강 'D-DAY 입찰'을 붙이지 않는다 (2026-09-23 출시 블로커).

운영 실측(공개 사용자, `/vehicles?date=2026-09-23`, 15:11 KST):
'D-DAY 입찰' 12회 · '기일 경과 — 결과 확인 전' 24회 · bg-rose-500 14회가 한 화면에
같이 나왔고, **배지가 붙은 카드 12장 전부**가 같은 카드 안에서 두 말을 동시에 했다.
그 물건들의 입찰 시각은 09:55~10:30 으로 조회 시점보다 5시간 전에 끝나 있었다.

원인은 판정 엔진이 아니다 — `service.bid_state()` 는 `sale_time_passed()` 로 시각을
올바르게 본다. **그 값을 안 쓰는 표시 계층**(app.py 의 D-day 계산과 `_display_judgment`)이
날짜만 비교했다.

빨강은 이 앱에서 가장 센 신호다. '오늘 입찰'이라고 빨강으로 적힌 차를 보고 법원에 가면
이미 끝난 경매다. 한 카드가 반대되는 두 말을 하면 사용자는 어느 쪽도 못 믿는다.

⚠ 시각을 **모르는** 물건은 '지나지 않음'으로 남겨야 한다(보수적). 끝나지 않은 경매를
  끝났다고 말하는 쪽이 더 비싼 실수다.
"""
from datetime import date

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_dashboard_link_parity import BT

# 공개 사용자로 본다 — XFF 가 없으면 이 앱은 요청을 관리자(SSH 터널)로 판정한다.
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

_TODAY = date.today().isoformat()
_BASE = {
    "case_no": "2026타경9001", "item_no": "1", "court": "수원지방법원",
    "maker": "현대", "model": "쏘나타", "year": 2020,
    "min_sale_price": 28_000_000, "appraisal_value": 32_000_000, "fail_count": 1,
    "status": "완료", "judgment": "유찰 대기", "median_price": 40_000_000,
    "market_confidence": 78, "market_confidence_label": "높음", "sample_count": 12,
    "photo_count": 3, "sale_date": _TODAY,
}


@pytest.fixture
def one_car(tmp_path, monkeypatch):
    """물건 **한 대만** 있는 목록을 렌더한다 — 배지·칩이 어느 카드 것인지 섞이지 않게."""
    def _make(**over):
        from web import db
        monkeypatch.setattr(db, "DB_PATH", tmp_path / (over.get("id", "X") + ".db"))
        monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
        db.init_db()
        db.upsert_vehicle(dict(_BASE, **over))
        import web.app as A
        # all=1 — 목록의 '미완성 숨김'에 걸려 0건이 나오면 이 테스트는 공허해진다.
        return TestClient(A.app).get("/vehicles?all=1", headers=_PUBLIC).text
    return _make


def _badges(html: str) -> str:
    """배지·칩이 있는 사진 위 영역만(대조용 원문). 실패 메시지에 그대로 싣는다."""
    i = html.find("D-DAY")
    j = html.find("기일 경과")
    k = max(i, j)
    return html[max(0, k - 300):k + 300] if k >= 0 else "(D-DAY·기일 경과 둘 다 없음)"


# ── 1. 끝난 경매 ────────────────────────────────────────────────
def test_시각이_지나면_빨강_DDAY_배지를_끈다(one_car):
    """00:00 기일은 하루 중 어느 시각에 돌려도 이미 지났다."""
    html = one_car(id="ENDED_1", sale_time="00:00")
    assert "D-DAY" not in html, (
        "입찰 시각이 지났는데 'D-DAY' 배지가 남았다 — 끝난 경매를 오늘 입찰이라 말한다:\n"
        + _badges(html))
    assert "기일 경과 — 결과 확인 전" in html, (
        "판정 칩이 기일 경과를 말하지 않으면 이 테스트는 배지만 지운 것을 통과시킨다:\n"
        + _badges(html))


def test_한_카드가_두_말을_동시에_하지_않는다(one_car):
    """운영 실측의 핵심 증상 — 같은 카드에 'D-DAY 입찰'과 '기일 경과'가 공존했다."""
    html = one_car(id="ENDED_2", sale_time="00:00")
    assert not ("D-DAY 입찰" in html and "기일 경과" in html), _badges(html)


# ── 2. 아직 안 끝난 경매(대조군) ─────────────────────────────────
def test_시각_전에는_DDAY_배지가_그대로_있다(one_car):
    """대조군이 없으면 위 두 테스트는 '배지가 원래 안 나온다'로도 통과한다."""
    html = one_car(id="LIVE_1", sale_time="23:59")
    assert "D-DAY" in html, (
        "아직 입찰 전인 오늘 기일 물건인데 카운트다운 배지가 사라졌다:\n" + _badges(html))


def test_시각을_모르면_보수적으로_지나지_않은_것으로_둔다(one_car):
    """sale_time 이 비면 sale_time_passed 가 False — 배지를 유지한다.

    끝난 경매를 살아 있다고 말하는 것도 나쁘지만, **아직 입찰할 수 있는 차를 끝났다고
    말해 기회를 뺏는 것**이 이 화면에서는 더 비싼 실수다. 아는 것만 고친다.
    """
    for t in (None, "", "오전 10시", "99:99"):
        html = one_car(id="UNK_1", sale_time=t)
        assert "D-DAY" in html, f"시각 '{t}' 를 지난 것으로 단정했다:\n{_badges(html)}"


# ── 3. 상단 배지(_display_judgment) ──────────────────────────────
def test_상단_배지가_히어로_칩과_같은_말을_한다():
    from web.app import ELAPSED_LABEL, _display_judgment

    car = dict(_BASE, id="D_1", sale_time="00:00")
    assert _display_judgment(car, _TODAY) == ELAPSED_LABEL, (
        "상세 상단 배지가 '유찰 대기'로 남으면 바로 아래 히어로 칩('기일 경과')과 충돌한다")
    # 시각 전 · 시각 미상은 그대로
    assert _display_judgment(dict(car, sale_time="23:59"), _TODAY) == "유찰 대기"
    assert _display_judgment(dict(car, sale_time=None), _TODAY) == "유찰 대기"


def test_문구가_판정_엔진과_한_글자도_다르지_않다():
    """두 곳에 같은 문장을 적어 두면 한쪽만 고쳐져 화면이 다시 갈라진다."""
    from web.app import ELAPSED_LABEL

    car = dict(_BASE, id="D_2", sale_time="00:00")
    assert service.bid_state(car, BT)["label"] == ELAPSED_LABEL


def test_입찰_보류는_건드리지_않는다():
    """_display_judgment 의 결과는 bid_state 가 **다시 읽는 입력**이다(blocked 분기).

    여기서 '입찰 보류'를 다른 문자열로 바꾸면 침수·전손 차단이 조용히 풀린다.
    """
    from web.app import _display_judgment

    car = dict(_BASE, id="D_3", sale_time="00:00", judgment="입찰 보류")
    car["judgment"] = _display_judgment(car, _TODAY)
    assert car["judgment"] == "입찰 보류"
    assert service.bid_state(car, BT)["state"] == "blocked", "침수·전손 차단이 풀렸다"


def test_낙찰_종결은_기일_경과로_덮이지_않는다():
    from web.app import _display_judgment

    won = dict(_BASE, id="D_4", sale_time="00:00", auction_result="낙찰")
    assert _display_judgment(won, _TODAY) == "종결"
