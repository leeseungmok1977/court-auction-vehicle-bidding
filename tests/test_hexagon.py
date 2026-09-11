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
            "year": 2020, "mileage_km": 90_000, "encar_total": 1_000,
            "newcar_min": 3_000, "newcar_max": 4_000}          # 출시가 범위(만원) → 중간 3,500만원
    base.update(kw)
    return base


def _score(h, key):
    return next(a for a in h["axes"] if a["key"] == key)


def _hx(v, **kw):
    kw.setdefault("newcar_ok", True)     # 단위 테스트는 config 의존 없이 공개 허용 상태로 고정
    return service.hexagon_scores(v, TODAY, **kw)


def test_full_data_yields_six_axes_and_polygon():
    h = _hx(_v())
    assert [a["key"] for a in h["axes"]] == ["price", "conf", "cond", "km", "value", "liq"]
    assert h["n_avail"] == 6 and h["poly"].count(",") == 6
    for a in h["axes"]:
        assert 0 <= a["score"] <= 100 and a["note"]
        assert "px" in a and "lx" in a          # SVG 좌표 존재
    assert len(h["rings"]) == 4


def test_price_merit_uses_market_then_appraisal():
    h = _hx(_v())
    p = _score(h, "price")
    assert p["score"] == 74 and "시세" in p["note"] and "33%" in p["note"]   # 1-8/12=33% → 70+20×(3.3/15)=74
    h2 = _hx(_v(median_price=None, market_confidence=None))
    p2 = _score(h2, "price")
    assert "감정가 기준" in p2["note"] and p2["score"] == 92   # 1-8/15=47% → 90+10×(1.7/10)=92
    assert _score(h2, "conf")["score"] is None                 # 시세 없으면 신뢰도 축 미산출


def test_missing_axes_are_none_not_zero():
    h = _hx(_v(mileage_km=None, encar_total=None))
    assert _score(h, "km")["score"] is None
    assert _score(h, "liq")["score"] is None
    assert h["n_avail"] == 4
    assert "px" not in _score(h, "km")                          # 미산출 축은 꼭짓점 좌표가 없다


def test_condition_axis_penalties():
    assert _score(_hx(_v(accident_grade="flood")), "cond")["score"] == 0
    assert _score(_hx(_v(accident_grade="accident")), "cond")["score"] == 45
    c = _score(_hx(_v(condition_level="poor", inspection_to="2026-01-01")), "cond")
    assert c["score"] == 65 and "검사 만료" in c["note"] and "상태 미흡" in c["note"]
    assert _score(_hx(_v(accident_grade=None)), "cond")["score"] is None


def test_mileage_scale():
    h = _hx(_v(year=2020, mileage_km=90_000))   # 6년·연 15,000km → ratio 1.0
    assert _score(h, "km")["score"] == 70
    assert _score(_hx(_v(year=2026, mileage_km=1_000)), "km")["score"] == 100


def test_residual_value_axis():
    """잔존가치 = 시세 중앙값 ÷ 출시가 범위 중간값. 근거에 중간값·등급 범위·경과연수를 실제 숫자로 적는다."""
    a = _score(_hx(_v()), "value")           # 1,200만 ÷ 3,500만 = 34.3% → 35 + 25×(4.3/15) = 42
    assert a["score"] == 42
    assert "3,500만원" in a["note"] and "34%" in a["note"] and "30~40%" in a["note"] and "6년 경과" in a["note"]
    assert "보배드림" not in a["note"] and "당시 출시가" not in a["note"]
    assert _score(_hx(_v(median_price=32_000_000)), "value")["score"] == 100   # 91% → 상한
    assert _score(_hx(_v(median_price=3_000_000)), "value")["score"] == 5      # 8.6% → 하한
    single = _score(_hx(_v(newcar_min=3_500, newcar_max=3_500)), "value")     # 등급 1개면 범위 표기 생략
    assert single["score"] == 42 and "등급 범위" not in single["note"]


def test_residual_value_missing_or_gated_is_none():
    assert _score(_hx(_v(newcar_min=None, newcar_max=None)), "value")["score"] is None
    assert _score(_hx(_v(median_price=None, market_confidence=None)), "value")["score"] is None
    g = _score(_hx(_v(), newcar_ok=False), "value")     # 공개 플래그 꺼짐: 값·숫자·'당시 출시가' 토큰 모두 없음
    assert g["score"] is None and not any(ch.isdigit() for ch in g["note"]) and "당시 출시가" not in g["note"]
    assert "px" not in g
    # newcar_ok 미지정 시 config.newcar_public을 따른다(관리자는 항상 허용)
    from unittest import mock
    with mock.patch.object(service, "load_config", lambda: {"newcar_public": False}):
        assert _score(service.hexagon_scores(_v(), TODAY), "value")["score"] is None
        assert _score(service.hexagon_scores(_v(), TODAY, include_private=True), "value")["score"] == 42


def test_liquidity_log_scale_and_zero():
    assert _score(_hx(_v(encar_total=0)), "liq")["score"] == 5
    assert _score(_hx(_v(encar_total=100)), "liq")["score"] == 70
    assert _score(_hx(_v(encar_total=5_000)), "liq")["score"] == 100


def test_public_payload_has_no_raw_listing_count():
    """유동성 축의 매물 건수(엔카 원자료)는 관리자에게만 실린다 — 공개 JSON에 count가 없어야 한다."""
    pub = _score(_hx(_v(encar_total=1_000)), "liq")
    assert "count" not in pub and "동급 매물" not in pub["note"]
    adm = _score(_hx(_v(encar_total=1_000), include_private=True), "liq")
    assert adm["count"] == 1_000


def test_reference_price_is_disclosed():
    h = service.hexagon_scores(_v(market_platform="동급참조", market_confidence=63,
                                  market_confidence_label="보통"), TODAY)
    assert "동급 참조" in _score(h, "conf")["note"]
