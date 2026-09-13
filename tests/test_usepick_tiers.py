"""실사용 추천 두 갈래 — '지금 사면 이득' / '싸게 낙찰되면 이득' (사용자 결정 2026-09-13).

배경: 실사용 추천이 3~9대뿐이었다. 원인 조사 결과 신건은 최저가=감정가(시세의 1.07배)라 구조적으로
못 들어오고, "최저가는 손익분기 아래인데 예상 경쟁가가 그 위"라서 빠진 물건이 46대(유의 25대)나
'유찰 대기'에 묻혀 있었다. 이 물건들은 **손익분기 이하로만 쓰면 이득**이다 — 낙찰 가능성이 낮을 뿐.
'유찰되면 후보'(다음 회차 저감 후 이득)는 사용자 결정으로 넣지 않는다 — 유찰되면 그때 올라온다.

정직성: 갈래마다 5회차 패널의 유의성 게이트(이득 > 예상낙찰가×MAE)를 똑같이 건다. cheap 은
최저가 근처 낙찰 시 이득이 오차보다 커야 한다. 세 화면(홈·목록·상세)의 문구는 USE_TIER_LABELS 하나다.
"""
import datetime
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_personal_use import BT, v

TODAY = datetime.date(2026, 9, 13)
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


def test_labels_are_plain_korean_and_single_sourced():
    assert service.USE_TIER_LABELS == {"now": "지금 사면 이득", "cheap": "싸게 낙찰되면 이득"}
    for bad in ("지금 이득", "상한선 안", "유찰 시"):
        assert bad not in service.USE_TIER_LABELS.values(), "처음 보는 사람이 못 읽는 내부 용어"


def test_now_tier_is_exactly_the_old_recommendation():
    car = v(sale_date="2026-09-30")
    t = service.personal_use_tier(car, BT, today=TODAY)
    assert t and t["tier"] == "now" and t["label"] == "지금 사면 이득" and t["saving"] > 0
    assert service.is_personal_use_pick(car, BT, today=TODAY) is True


def test_cheap_tier_when_expected_gain_is_within_error_but_floor_gain_is_not():
    """최저 2,800만: 예상 3,164만은 손익분기 안이지만 이득 83만 < 오차 316만 → now 아님(bid_state '실사용이면 이득').
    최저가 근처면 이득 472만 > 오차 → '싸게 낙찰되면 이득'."""
    car = v(min_sale_price=28_000_000, sale_date="2026-09-30")
    assert service.is_personal_use_pick(car, BT, today=TODAY) is False
    t = service.personal_use_tier(car, BT, today=TODAY)
    assert t and t["tier"] == "cheap" and t["label"] == "싸게 낙찰되면 이득"
    assert t["floor"] == 28_000_000 and t["floor"] <= t["max_bid"] and t["saving_floor"] > 0
    assert t["room"] == t["max_bid"] - t["floor"]


def test_cheap_tier_covers_the_caution_state_too():
    """최저 2,900만: 예상 3,277만이 손익분기(≈3,230만)를 넘어 bid_state 는 caution — 그래도 최저가 근처면 이득이 유의."""
    car = v(min_sale_price=29_000_000, sale_date="2026-09-30")
    st = service.bid_state(car, BT)
    assert st["state"] == "over_market" and st["tone"] == "caution", "전제: 예상 경쟁가가 상한선 초과"
    t = service.personal_use_tier(car, BT, today=TODAY)
    assert t and t["tier"] == "cheap" and t["max_bid"] == st["max_bid"]


def test_no_tier_when_even_the_floor_gain_is_within_error():
    """최저 3,000만: 최저가로 낙찰돼도 이득 258만 < 오차 339만 → 이득이라 부르지 않는다(5회차 게이트)."""
    car = v(min_sale_price=30_000_000, sale_date="2026-09-30")
    assert service.bid_state(car, BT)["tone"] == "caution"
    assert service.personal_use_tier(car, BT, today=TODAY) is None


@pytest.mark.parametrize("kw,why", [
    ({"min_sale_price": 33_000_000}, "최저가부터 손익분기 초과(blocked) — 어떤 금액도 손해"),
    ({"min_sale_price": 38_000_000, "fail_count": 0}, "예상 경쟁가가 시세 초과(비권장) — 갈래 없음"),
    ({"judgment": "입찰 검토 가능"}, "재판매 칸이 가져간다(칸 겹침 금지)"),
    ({"sale_date": "2026-08-20"}, "지난 기일은 입찰할 수 없다"),
    ({"market_confidence_label": "낮음"}, "시세를 못 믿으면 어느 갈래도 아니다"),
    ({"accident_grade": "flood"}, "침수·전손"),
    ({"runnable": "no", "min_sale_price": 28_000_000}, "시동 불가는 수리비가 열려 있다"),
    ({"appraisal_value": 8_500_000, "min_sale_price": 8_000_000}, "시세/감정가 괴리(오매칭 의심)"),
])
def test_no_tier_cases(kw, why):
    car = v(sale_date="2026-09-30")
    car.update(kw)
    assert service.personal_use_tier(car, BT, today=TODAY) is None, why


def test_bucket_takes_both_tiers_and_stays_exclusive():
    now_car = v(sale_date="2999-01-01")
    cheap_car = v(min_sale_price=28_000_000, sale_date="2999-01-01")
    wait_car = v(min_sale_price=39_000_000, sale_date="2999-01-01")
    assert service._bucket_and_tier(now_car, BT)[0] == "usepick"
    b, t = service._bucket_and_tier(cheap_car, BT)
    assert b == "usepick" and t["tier"] == "cheap"
    assert service._bucket_and_tier(wait_car, BT) == ("wait", None)
    assert service.lifecycle_bucket_of(cheap_car, BT) == "usepick"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    from tests.test_dashboard_link_parity import BT as BT2
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT2)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1", "year": 2020,
            "sale_date": "2999-01-01", "status": "완료", "fail_count": 1, "market_confidence_label": "높음",
            "judgment": "유찰 대기", "median_price": 40_000_000}
    db.upsert_vehicle(dict(base, id="NOW_1", case_no="2026타경21", min_sale_price=16_000_000, appraisal_value=30_000_000))
    db.upsert_vehicle(dict(base, id="CHEAP_1", case_no="2026타경22", min_sale_price=28_000_000, appraisal_value=38_000_000))
    db.upsert_vehicle(dict(base, id="WAIT_1", case_no="2026타경23", min_sale_price=39_000_000, appraisal_value=40_000_000))
    import web.app as A
    return TestClient(A.app)


def test_home_card_shows_both_tiers_with_matching_numbers(client):
    html = client.get("/", headers=_PUBLIC).text
    lc = service.lifecycle_partition()
    assert lc["usepick"] == 2 and lc["usepick_now"] == 1 and lc["usepick_cheap"] == 1 and lc["wait"] == 1
    card = html[html.index('href="/vehicles?usepick=1"'):]
    card = card[:card.index("</a>")]
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", card))
    # 문구와 숫자가 한 구절("… 이득 1대")로 — 숫자를 명사에서 떼지 않는다(검수)
    assert "지금 사면 이득 1대" in txt and "싸게 낙찰되면 이득 1대" in txt, txt
    for bad in ("지금 이득", "상한선 안", "유찰 시", "직접 탈 목적"):
        assert bad not in card


def test_list_filters_and_tags_follow_the_tiers(client):
    both = client.get("/vehicles?usepick=1", headers=_PUBLIC).text
    assert "NOW_1" in both and "CHEAP_1" in both and "WAIT_1" not in both
    assert "지금 사면 이득" in both and "싸게 낙찰되면 이득" in both and "만원까지" in both
    assert both.index("NOW_1") < both.index("CHEAP_1"), "지금 사면 이득이 먼저"
    now = client.get("/vehicles?usepick=now", headers=_PUBLIC).text
    assert "NOW_1" in now and "CHEAP_1" not in now and 'name="usepick" value="now"' in now
    cheap = client.get("/vehicles?usepick=cheap", headers=_PUBLIC).text
    assert "CHEAP_1" in cheap and "NOW_1" not in cheap and 'name="usepick" value="cheap"' in cheap
    assert "실사용 추천 · 싸게 낙찰되면 이득 ✕" in cheap
    # 갈래 칩의 수 = 홈 카드의 수
    assert re.search(r"지금 사면 이득 <span[^>]*>1대</span>", both) and re.search(r"싸게 낙찰되면 이득 <span[^>]*>1대</span>", both)
    for href, n in (("/api/vehicles/count?usepick=1", 2), ("/api/vehicles/count?usepick=now", 1),
                    ("/api/vehicles/count?usepick=cheap", 1)):
        assert client.get(href, headers=_PUBLIC).json()["total"] == n, href


def _text(html: str) -> str:
    """태그를 걷고 공백을 접는다 — 배지는 '싸게 낙찰되면 <span>이득 · …</span>' 처럼 나뉘어 있다(숫자를 명사에서 안 뗀다)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_detail_badge_uses_the_same_words(client):
    cheap = _text(client.get("/vehicle/CHEAP_1", headers=_PUBLIC).text)
    assert "싸게 낙찰되면 이득 · " in cheap and "만원까지" in cheap
    now = _text(client.get("/vehicle/NOW_1", headers=_PUBLIC).text)
    assert "지금 사면 이득" in now
    wait = _text(client.get("/vehicle/WAIT_1", headers=_PUBLIC).text)
    assert "지금 사면 이득" not in wait and "싸게 낙찰되면 이득" not in wait
