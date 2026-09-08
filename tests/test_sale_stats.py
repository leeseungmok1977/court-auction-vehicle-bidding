"""달력 하단 '지난달 낙찰 실적'(last_month_sale_stats) — 신뢰성 불변식.

데이터 신뢰성 최우선: (1) 낙찰가<최저매각가 무결성 위반 행은 반드시 제외,
(2) 대표값은 중앙값이라 시세오매칭 이상치에 견고, (3) 유찰 분모가 없으므로
'낙찰율' 류 지표를 절대 만들어내지 않는다(구성 합이 표본 수와 일치).
"""
import pytest
from datetime import date


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _prev_month_day(day=15):
    """지난달(전월)의 특정 일 — 함수의 '전월' 브랜치(표본>=8)를 타게 한다."""
    t = date.today()
    py, pm = (t.year - 1, 12) if t.month == 1 else (t.year, t.month - 1)
    return date(py, pm, min(day, 28))


def _rec(db, id, winning, median, mn, d=None):
    db.record_sale_result({
        "id": id, "winning_price": winning, "median_price": median,
        "min_sale_price": mn, "sale_date": (d or _prev_month_day()).isoformat(),
    })


def test_none_when_no_data(dbmod):
    from web import service
    assert service.last_month_sale_stats() is None


def test_excludes_winning_below_min_and_invariants(dbmod):
    from web import service
    # 유효 8건(가격대 4구간에 2건씩) — winning>=min
    rows = [
        ("A0", 3_000_000, 6_000_000, 2_000_000),   # 0.50, 300만 → 500만 이하
        ("A1", 4_000_000, 6_000_000, 2_000_000),   # 0.67, 400만 → 500만 이하
        ("B0", 7_000_000, 10_000_000, 5_000_000),  # 0.70, 700만 → 500~1000만
        ("B1", 8_000_000, 10_000_000, 5_000_000),  # 0.80, 800만 → 500~1000만
        ("C0", 15_000_000, 18_000_000, 10_000_000),# 0.83, 1500만 → 1000~2000만
        ("C1", 16_000_000, 18_000_000, 10_000_000),# 0.89, 1600만 → 1000~2000만
        ("D0", 25_000_000, 27_000_000, 20_000_000),# 0.93, 2500만 → 2000만 이상
        ("D1", 24_000_000, 27_000_000, 20_000_000),# 0.89, 2400만 → 2000만 이상
    ]
    for id, w, m, mn in rows:
        _rec(dbmod, id, w, m, mn)
    # 무결성 위반: 낙찰가 < 최저매각가 (불가능한 값) → 제외돼야 한다
    _rec(dbmod, "BAD", 1_000_000, 5_000_000, 2_000_000)

    s = service.last_month_sale_stats()
    assert s is not None
    assert s["n"] == 8                      # BAD 제외
    assert s["window"] == "month"
    # 가격대·요일 구성 합이 표본 수와 정확히 일치(허수 없음)
    assert sum(b["n"] for b in s["price_bands"]) == 8
    assert sum(w["n"] for w in s["weekdays"]) == 8
    # 4개 가격대에 2건씩
    assert [b["n"] for b in s["price_bands"]] == [2, 2, 2, 2]
    # 중앙값·IQR 정합
    assert 0 < s["ratio_p25"] <= s["ratio_med"] <= s["ratio_p75"] <= 130
    assert s["over_min_med"] > 0            # 최저가 대비 프리미엄(+)
    # 낙찰율(유찰 분모 필요) 류 지표를 만들어내지 않는다
    assert not any("낙찰율" in k or k in ("sold_rate", "win_rate") for k in s)


def test_median_robust_to_market_mismatch_outlier(dbmod):
    from web import service
    # 정상 7건(시세의 ~80%) + 시세오매칭 의심 1건(시세의 14%, 그러나 winning>=min이라 유효)
    for i in range(7):
        _rec(dbmod, f"N{i}", 8_000_000, 10_000_000, 6_000_000)   # 0.80
    _rec(dbmod, "OUT", 1_400_000, 10_000_000, 1_000_000)         # 0.14 (극단 저비율)
    s = service.last_month_sale_stats()
    assert s is not None and s["n"] == 8
    # 평균이면 이상치에 끌려 내려가지만, 중앙값은 80% 부근을 유지
    assert s["ratio_med"] >= 75
