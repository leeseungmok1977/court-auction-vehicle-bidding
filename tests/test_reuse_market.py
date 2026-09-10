"""동급 시세 참조(reuse_market_prices) — 엔카를 못 쓸 때 DB의 실측 시세로 공백을 메우되 정직하게.

신뢰성 불변식:
1) 외부요청 0.  2) 실측 시세만 공여(참조끼리 연쇄 금지).  3) 신뢰도 한 단계 하향(높음→보통, 보통→낮음).
4) 출처 표기(market_platform/ref_date/ref_id).  5) 이미 시세가 있는 물건은 건드리지 않는다.
"""
from datetime import date, timedelta

import pytest


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _soon(days=5):
    return (date.today() + timedelta(days=days)).isoformat()


def _v(db, id, **kw):
    base = {"id": id, "folder_key": id, "case_no": id, "item_no": "1",
            "maker": "현대", "model": "그랜저", "year": 2020, "mileage_km": 80000,
            "min_sale_price": 7_000_000, "sale_date": _soon(), "status": "완료"}
    base.update(kw)
    db.upsert_vehicle(base)


def _donor(db, id, label="높음", conf=85, median=12_000_000, **kw):
    _v(db, id, median_price=median, sample_count=20, market_confidence=conf,
       market_confidence_label=label, market_platform="encar", analyzed_at="2026-09-05 06:40:00",
       sale_date="2026-08-20", **kw)


def test_no_external_request(dbmod, monkeypatch):
    from web import service
    from src.collect import encar

    def _boom(*a, **k):
        raise AssertionError("reuse_market_prices가 외부요청을 했다")

    monkeypatch.setattr(encar, "new_session", _boom)
    monkeypatch.setattr(encar, "search", _boom)
    _donor(dbmod, "D1"); _v(dbmod, "T1")
    service.reuse_market_prices()


def test_applies_donor_median_with_downgraded_confidence(dbmod):
    from web import service
    _donor(dbmod, "D1", label="높음", conf=85, median=12_000_000)
    _donor(dbmod, "D2", label="높음", conf=80, median=13_000_000, year=2021)
    _v(dbmod, "T1")                         # 시세 없음, 2020
    out = service.reuse_market_prices()
    assert out["applied"] == 1
    t = dbmod.get_vehicle("T1")
    assert t["median_price"] in (12_000_000, 12_500_000)      # 상위 후보 중앙값(연식 일치 우선)
    assert t["market_platform"] == "동급참조"
    assert t["market_ref_id"] == "D1"                           # 연식 완전 일치 공여자가 대표
    assert t["market_ref_date"] == "2026-09-05"
    assert t["market_confidence_label"] == "보통"              # 높음 → 보통 (한 단계 하향)
    assert t["market_confidence"] == 70                          # 85 - 15
    assert t["upper_bid"] is not None                            # 판정·상한가 산정됨
    assert t["judgment"] != "시세 신뢰도 낮음, 수동 검토"


def test_medium_donor_stays_manual_review(dbmod):
    """공여자가 '보통'이면 참조 시세는 '낮음' → 판정은 수동 검토로 남는다(과입찰 방지)."""
    from web import service
    _donor(dbmod, "D1", label="보통", conf=60)
    _v(dbmod, "T1")
    service.reuse_market_prices()
    t = dbmod.get_vehicle("T1")
    assert t["median_price"] == 12_000_000                      # 시세는 보여주되
    assert t["market_confidence_label"] == "낮음"
    assert t["judgment"] == "시세 신뢰도 낮음, 수동 검토"        # 판정은 상향하지 않는다


def test_reference_prices_do_not_chain(dbmod):
    from web import service
    _v(dbmod, "R1", median_price=9_000_000, market_platform="동급참조",
       market_confidence_label="보통", sale_date="2026-08-20")   # 참조 시세(공여 불가)
    _v(dbmod, "T1")
    out = service.reuse_market_prices()
    assert out["applied"] == 0 and out["no_donor"] == 1
    assert dbmod.get_vehicle("T1")["median_price"] is None


def test_year_tolerance_and_untouched_priced(dbmod):
    from web import service
    _donor(dbmod, "D1", year=2016)                               # 연식 4년 차이 → 공여 불가
    _v(dbmod, "T1")
    _v(dbmod, "P1", model="쏘나타", median_price=5_000_000, market_platform="encar",
       market_confidence_label="높음")   # 이미 시세 있음(다른 차종) → 대상도 공여자도 아님
    out = service.reuse_market_prices()
    assert out["applied"] == 0 and out["no_donor"] == 1
    assert dbmod.get_vehicle("T1")["median_price"] is None
    p = dbmod.get_vehicle("P1")
    assert p["median_price"] == 5_000_000 and p["market_platform"] == "encar"


def test_priced_vehicle_is_a_valid_donor(dbmod):
    """시세가 있는 같은 차종·연식 물건은(실측이면) 공여자로 쓰인다 — 앞 테스트의 반례 고정."""
    from web import service
    _v(dbmod, "P1", median_price=5_000_000, market_platform="encar", sample_count=8,
       market_confidence=80, market_confidence_label="높음", analyzed_at="2026-09-04 07:00:00")
    _v(dbmod, "T1")
    assert service.reuse_market_prices()["applied"] == 1
    assert dbmod.get_vehicle("T1")["market_ref_id"] == "P1"


def test_excludes_closed_and_past(dbmod):
    from web import service
    _donor(dbmod, "D1")
    _v(dbmod, "T_past", sale_date="2020-01-01")                  # 기일 지남
    _v(dbmod, "T_won", auction_result="낙찰", winning_price=8_000_000)
    out = service.reuse_market_prices()
    assert out["applied"] == 0
