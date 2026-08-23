"""동급 매물 매칭·통계 테스트 (설계서 TASK-05 DoD: ±1년 경계, 표본 0건)."""

from src.parse.market_match import (
    filter_comparable, compute_stats, summarize, trim_outliers,
    appraisal_guard, appraisal_penalty, cross_source_check, _fuel_match)


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


def _mkid(_id, mileage, price):
    return {"platform": "encar", "form_year": 2021, "mileage_km": mileage,
            "price_won": price, "model": "쏘렌토", "fuel": "디젤", "id": _id}


def test_summarize_dedupes_by_id():
    """같은 id(또는 동일 스펙 재등록)는 표본수를 부풀리지 않는다. 서로 다른 차는 유지."""
    listings = [
        _mkid("A", 50000, 15_000_000), _mkid("A", 50000, 15_000_000),  # id 중복(재등록)
        _mkid("B", 52000, 15_200_000), _mkid("C", 48000, 14_800_000),
        _mkid("D", 55000, 15_500_000), _mkid("E", 46000, 14_600_000),
    ]
    st = summarize(listings, form_year=2021, mileage_km=50000)
    assert st.sample_count == 5          # A중복 1건 제외 → 5건


def test_summarize_min_sample_gates_confidence():
    """표본이 min_sample 미만이면 신뢰도가 '낮음'으로 게이팅된다."""
    listings = [_mk(2021, 50000, 15_000_000), _mk(2021, 51000, 15_200_000)]
    st = summarize(listings, form_year=2021, mileage_km=50000, min_sample=5)
    assert st.sample_count == 2
    assert st.confidence <= 40 and st.confidence_label == "낮음"


def _mkb(year, price, badge, _id):
    return {"platform": "encar", "form_year": year, "mileage_km": 50000,
            "price_won": price, "model": "S클래스", "badge": badge, "id": _id}


def test_summarize_trim_filters_to_maybach():
    """트림 힌트가 있으면 Badge로 해당 트림만 매칭(마이바흐 ≠ 일반 S클래스). 스펙은 매물마다 상이."""
    L = [{"platform": "encar", "form_year": 2023, "mileage_km": 40000 + i * 5000,
          "price_won": 148_000_000 + i * 2_000_000, "model": "S클래스",
          "badge": "마이바흐 S 580 4MATIC", "id": i} for i in range(4)] + \
        [{"platform": "encar", "form_year": 2023, "mileage_km": 30000 + i * 5000,
          "price_won": 86_000_000 + i * 2_000_000, "model": "S클래스",
          "badge": "S 400 d 4MATIC", "id": 100 + i} for i in range(4)]
    st = summarize(L, form_year=2023, mileage_km=50000, min_sample=3, trim="마이바흐")
    assert st.median_price == 151_000_000      # 마이바흐 4건(148~154M)의 중앙값
    assert "마이바흐" in st.match_label


def test_summarize_trim_unconfirmed_caps_confidence():
    """트림 힌트가 있으나 Badge 표본이 부족하면 신뢰도를 낮춘다(오매칭 위험)."""
    L = [_mkb(2023, 88_000_000, "S 400 d 4MATIC", 100 + i) for i in range(8)]
    st = summarize(L, form_year=2023, mileage_km=50000, min_sample=3, trim="마이바흐")
    assert st.confidence <= 40 and st.confidence_label == "낮음"
    assert "미확인" in st.match_label


def test_trim_outliers_removes_extremes():
    """허위 저가 미끼·특장 고가 매물이 평균을 왜곡하지 않도록 IQR로 제거."""
    prices = [12_000_000, 12_500_000, 13_000_000, 13_500_000,
              14_000_000, 1_000_000, 99_000_000]  # 저가·고가 이상치 2건
    kept, n_out = trim_outliers(prices)
    assert n_out == 2
    assert 1_000_000 not in kept and 99_000_000 not in kept


def test_trim_outliers_small_sample_noop():
    """표본 5건 미만이면 트리밍하지 않는다(표본 보호)."""
    prices = [10_000_000, 50_000_000, 90_000_000]
    kept, n_out = trim_outliers(prices)
    assert n_out == 0 and kept == prices


def test_appraisal_guard_normal_band():
    """시세/감정가가 정상 대역(0.7~1.4)이면 상한 없음."""
    cap, note, ratio = appraisal_guard(9_300_000, 10_000_000)
    assert cap is None and ratio == 0.93 and note == ""


def test_appraisal_guard_strong_deviation():
    """시세가 감정가의 절반 미만 → 신뢰도 낮음으로 강제(엉뚱한 트림 매칭 의심)."""
    cap, note, ratio = appraisal_guard(4_785_000, 12_000_000)  # BMW 740i 사례 0.40
    assert cap == 38 and "괴리" in note and ratio == 0.4


def test_appraisal_guard_mild_deviation():
    """시세가 감정가의 0.59배(마이바흐 사례) → 보통으로 하향."""
    cap, note, ratio = appraisal_guard(88_500_000, 150_000_000)
    assert cap == 60 and ratio == 0.59


def test_appraisal_guard_high_deviation():
    """시세가 감정가의 2.3배(이보크 사례) → 낮음(사고차 저평가·오매칭 확인)."""
    cap, note, ratio = appraisal_guard(34_945_000, 15_000_000)
    assert cap == 38 and ratio > 2.0


def test_appraisal_guard_missing_inputs():
    assert appraisal_guard(None, 10_000_000) == (None, "", None)
    assert appraisal_guard(10_000_000, None) == (None, "", None)


def test_fuel_match_hybrid_variants():
    """하이브리드·전기 표기 변형까지 부분일치, 이종 연료는 불일치."""
    assert _fuel_match("하이브리드", "가솔린(하이브리드)") is True
    assert _fuel_match("하이브리드", "하이브리드") is True
    assert _fuel_match("전기", "전기(EV)") is True
    assert _fuel_match("디젤", "디젤") is True
    assert _fuel_match("디젤", "가솔린") is False
    assert _fuel_match("가솔린", "하이브리드") is False
    assert _fuel_match(None, "디젤") is False


def test_summarize_fuel_unconfirmed_caps():
    """연료 지정됐으나 표본 부족으로 못 좁히면 '연료미필터' + 신뢰도 상한."""
    # 디젤 1건 + 가솔린 다수 → 디젤 필터 미적용(표본<3), 표본은 충분
    L = [{"platform": "encar", "form_year": 2021, "mileage_km": 50000,
          "price_won": 20_000_000 + i, "model": "쏘렌토", "fuel": "가솔린", "id": "g%d" % i}
         for i in range(6)]
    L.append({"platform": "encar", "form_year": 2021, "mileage_km": 50000,
              "price_won": 20_000_000, "model": "쏘렌토", "fuel": "디젤", "id": "d1"})
    st = summarize(L, form_year=2021, mileage_km=50000, fuel="디젤", min_sample=5)
    assert "연료미필터" in st.match_label
    assert st.confidence <= 60


def test_cross_source_check():
    """엔카·케이카 교차검증: 근접→일치, 괴리→불일치, 결측→단일소스."""
    assert cross_source_check(22_000_000, 22_800_000)[0] == "agree"      # ±3.6%
    assert cross_source_check(22_000_000, 30_000_000)[0] == "diverge"    # ±36%
    assert cross_source_check(22_000_000, None)[0] == "single"
    assert cross_source_check(None, None)[0] == "single"


def test_appraisal_penalty_scales_with_deviation():
    """감정가와 같으면 0, 벌어질수록 증가(상한 30)."""
    assert appraisal_penalty(10_000_000, 10_000_000) == 0        # ratio 1.0
    p_near = appraisal_penalty(9_000_000, 10_000_000)            # ratio 0.9
    p_far = appraisal_penalty(7_200_000, 10_000_000)             # ratio 0.72
    assert 0 < p_near < p_far <= 30
    assert appraisal_penalty(None, 10_000_000) == 0


def test_compute_stats_trims_and_reports():
    comps = [_mk(2021, 50000, p) for p in
             (12_000_000, 12_500_000, 13_000_000, 13_500_000, 14_000_000, 90_000_000)]
    st = compute_stats(comps, platform="encar", form_year=2021, mileage_km=50000)
    assert st.outlier_count == 1
    assert st.sample_count == 5
    assert st.median_price == 13_000_000       # 이상치 제외 중앙값
