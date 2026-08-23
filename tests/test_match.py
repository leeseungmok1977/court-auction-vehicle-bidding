"""동급 매물 매칭·통계 테스트 (설계서 TASK-05 DoD: ±1년 경계, 표본 0건)."""

from src.parse.market_match import filter_comparable, compute_stats, summarize


def _mk(year, mileage, price_won):
    return {"platform": "encar", "form_year": year, "mileage_km": mileage,
            "price_won": price_won}


def test_year_boundary_pm1():
    """연식 ±1년 경계: 2020·2022 포함, 2019·2023 제외 (기준 2021)."""
    listings = [_mk(2019, 50000, 1000), _mk(2020, 50000, 2000),
                _mk(2021, 50000, 3000), _mk(2022, 50000, 4000),
                _mk(2023, 50000, 5000)]
    comps = filter_comparable(listings, form_year=2021, mileage_km=50000,
                              year_tol=1, mileage_tol=0.30)
    years = sorted(c["form_year"] for c in comps)
    assert years == [2020, 2021, 2022]


def test_mileage_boundary_pm30():
    """주행거리 ±30% 경계 (기준 100,000km → 70,000~130,000)."""
    listings = [_mk(2021, 69000, 1), _mk(2021, 70000, 2), _mk(2021, 100000, 3),
                _mk(2021, 130000, 4), _mk(2021, 131000, 5)]
    comps = filter_comparable(listings, form_year=2021, mileage_km=100000,
                              year_tol=1, mileage_tol=0.30)
    miles = sorted(c["mileage_km"] for c in comps)
    assert miles == [70000, 100000, 130000]


def test_stats_values():
    comps = [_mk(2021, 50000, 10_000_000), _mk(2021, 50000, 20_000_000),
             _mk(2021, 50000, 30_000_000)]
    st = compute_stats(comps, platform="encar", form_year=2021, mileage_km=50000)
    assert st.sample_count == 3
    assert st.median_price == 20_000_000
    assert st.mean_price == 20_000_000
    assert st.min_price == 10_000_000


def test_zero_sample():
    """표본 0건 → sample_count 0, 가격 None (bidcalc가 '신뢰도 낮음' 처리)."""
    st = summarize([], form_year=2021, mileage_km=50000)
    assert st.sample_count == 0
    assert st.median_price is None
    assert st.min_price is None


def test_tiered_exact_match():
    listings = [_mk(2021, 50000, 10_000_000), _mk(2021, 52000, 11_000_000)]
    st = summarize(listings, form_year=2021, mileage_km=50000)
    assert st.sample_count == 2 and "동급" in st.match_label


def test_tiered_expand_when_no_exact():
    """연식±1엔 없고 ±2엔 있으면 '확장' 기준으로 매칭."""
    listings = [_mk(2019, 50000, 10_000_000), _mk(2019, 55000, 12_000_000)]
    st = summarize(listings, form_year=2021, mileage_km=50000)
    assert st.sample_count == 2 and "확장" in st.match_label


def test_tiered_no_match_beyond_3yr():
    """연식±3을 벗어난 매물만 있으면 표본 없음(오해 방지 — 엉뚱한 연식 미사용)."""
    listings = [_mk(2010, 50000, 5_000_000)]
    st = summarize(listings, form_year=2021, mileage_km=50000)
    assert st.sample_count == 0 and st.median_price is None


def _mkm(year, mileage, price, model, fuel):
    return {"platform": "encar", "form_year": year, "mileage_km": mileage,
            "price_won": price, "model": model, "fuel": fuel}


def test_summarize_generation_filter():
    """물건 연식의 지배적 Model(세대)만 매칭 — 신세대·타연료 혼입 배제."""
    L = [
        _mkm(2020, 150000, 13_000_000, "더 뉴 카니발", "디젤"),
        _mkm(2019, 160000, 12_000_000, "더 뉴 카니발", "디젤"),
        _mkm(2020, 140000, 14_000_000, "더 뉴 카니발", "디젤"),
        _mkm(2021, 150000, 25_000_000, "카니발 4세대", "디젤"),   # 신세대 → 제외
        _mkm(2021, 155000, 26_000_000, "카니발 4세대", "디젤"),
        _mkm(2020, 150000, 22_000_000, "더 뉴 카니발", "가솔린"),  # 타연료 → 제외
    ]
    st = summarize(L, form_year=2020, mileage_km=150000, fuel="디젤")
    assert st.median_price == 13_000_000       # 3세대 디젤 3건의 중앙값
    assert "동세대" in st.match_label and "디젤" in st.match_label


def test_summarize_fuel_guard_keeps_when_sparse():
    """연료 일치 표본이 3건 미만이면 연료로 좁히지 않는다(과도 축소 방지)."""
    L = [
        _mkm(2020, 150000, 13_000_000, "쏘렌토", "디젤"),
        _mkm(2020, 150000, 14_000_000, "쏘렌토", "가솔린"),
    ]
    st = summarize(L, form_year=2020, mileage_km=150000, fuel="디젤")
    assert st.sample_count == 2                 # 연료 축소 안 함(디젤 1건뿐)


def test_skip_none_price():
    listings = [_mk(2021, 50000, None), _mk(2021, 50000, 15_000_000)]
    comps = filter_comparable(listings, form_year=2021, mileage_km=50000)
    assert len(comps) == 1
