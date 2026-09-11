"""리포트 종합 프로필 육각형(hexagon_scores) — 신뢰성 불변식.

자료가 없는 축은 0으로 꾸미지 않고 None(미산출). 각 축은 실제 입력값으로 근거(note)를 남긴다.
공식은 service.hexagon_scores docstring·리포트 각주와 동일하다.
"""
from datetime import date

from web import service

TODAY = date(2026, 9, 11)


def _v(**kw):
    base = {"min_sale_price": 8_000_000, "median_price": 12_000_000, "appraisal_value": 15_000_000,
            "market_confidence": 78, "market_confidence_label": "높음", "market_platform": "encar",
            "accident_grade": "none", "condition_level": "unknown", "inspection_to": "2027-03-01",
            "year": 2020, "mileage_km": 90_000, "encar_total": 1_000}
    base.update(kw)
    return base


def _score(h, key):
    return next(a for a in h["axes"] if a["key"] == key)


def test_full_data_yields_six_axes_and_polygon():
    h = service.hexagon_scores(_v(), TODAY)
    assert [a["key"] for a in h["axes"]] == ["price", "conf", "cond", "km", "age", "liq"]
    assert h["n_avail"] == 6 and h["poly"].count(",") == 6
    for a in h["axes"]:
        assert 0 <= a["score"] <= 100 and a["note"]
        assert "px" in a and "lx" in a          # SVG 좌표 존재
    assert len(h["rings"]) == 4


def test_price_merit_uses_market_then_appraisal():
    h = service.hexagon_scores(_v(), TODAY)
    p = _score(h, "price")
    assert p["score"] == 74 and "시세" in p["note"] and "33%" in p["note"]   # 1-8/12=33% → 70+20×(3.3/15)=74
    h2 = service.hexagon_scores(_v(median_price=None, market_confidence=None), TODAY)
    p2 = _score(h2, "price")
    assert "감정가 기준" in p2["note"] and p2["score"] == 92   # 1-8/15=47% → 90+10×(1.7/10)=92
    assert _score(h2, "conf")["score"] is None                 # 시세 없으면 신뢰도 축 미산출


def test_missing_axes_are_none_not_zero():
    h = service.hexagon_scores(_v(mileage_km=None, encar_total=None), TODAY)
    assert _score(h, "km")["score"] is None
    assert _score(h, "liq")["score"] is None
    assert h["n_avail"] == 4
    assert "px" not in _score(h, "km")                          # 미산출 축은 꼭짓점 좌표가 없다


def test_condition_axis_penalties():
    assert _score(service.hexagon_scores(_v(accident_grade="flood"), TODAY), "cond")["score"] == 0
    assert _score(service.hexagon_scores(_v(accident_grade="accident"), TODAY), "cond")["score"] == 45
    c = _score(service.hexagon_scores(_v(condition_level="poor", inspection_to="2026-01-01"), TODAY), "cond")
    assert c["score"] == 65 and "검사 만료" in c["note"] and "상태 미흡" in c["note"]
    assert _score(service.hexagon_scores(_v(accident_grade=None), TODAY), "cond")["score"] is None


def test_mileage_and_age_scales():
    h = service.hexagon_scores(_v(year=2020, mileage_km=90_000), TODAY)   # 6년·연 15,000km → ratio 1.0
    assert _score(h, "km")["score"] == 70
    assert _score(h, "age")["score"] == round(70 - (6 - 5) * (70 - 50) / 3)  # 5→70, 8→50 사이
    assert _score(service.hexagon_scores(_v(year=2026, mileage_km=1_000), TODAY), "km")["score"] == 100


def test_liquidity_log_scale_and_zero():
    assert _score(service.hexagon_scores(_v(encar_total=0), TODAY), "liq")["score"] == 5
    assert _score(service.hexagon_scores(_v(encar_total=100), TODAY), "liq")["score"] == 70
    assert _score(service.hexagon_scores(_v(encar_total=5_000), TODAY), "liq")["score"] == 100


def test_reference_price_is_disclosed():
    h = service.hexagon_scores(_v(market_platform="동급참조", market_confidence=63,
                                  market_confidence_label="보통"), TODAY)
    assert "동급 참조" in _score(h, "conf")["note"]
