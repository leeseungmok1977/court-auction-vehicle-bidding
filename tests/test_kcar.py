"""케이카 2차 소스 · 교차검증 단위 테스트 (네트워크 없이 정규화·신뢰도 로직만)."""
from src.collect import kcar
from src.parse.market_match import summarize, cross_source_check
from web import service


# --- kcar.normalize: 실응답(확정 필드 + 패턴매칭 대상) → 공통 스키마 -----------------
def _kcar_row(price, year="202106", km=30000, fuel="디젤", cd="EC1"):
    # 실측 확정 키(run_kcar_discover 응답 기준): carCd/mnuftrNm/modelGrpNm/grdNm/mfgDt/prc/milg/fuelNm.
    # grdNm에 연료어('디젤')가 섞여 있어도 연료 전용 키(fuelNm)가 우선돼야 한다.
    return {"carCd": cd, "mnuftrNm": "기아", "modelGrpNm": "쏘렌토", "modelNm": "쏘렌토 4세대",
            "carWhlNm": "기아 쏘렌토 2.2 디젤 시그니처", "grdNm": "2.2 디젤 시그니처",
            "grdDtlNm": "시그니처", "mfgDt": year, "prc": price, "milg": km,
            "fuelNm": fuel, "extrColorNm": "흰색"}


def test_kcar_normalize_maps_confirmed_fields():
    rows = [_kcar_row(2450, cd="A"), _kcar_row(2600, cd="B")]  # prc 만원 단위
    norm = kcar.normalize(rows)
    assert len(norm) == 2
    a = norm[0]
    assert a["platform"] == "kcar"
    assert a["id"] == "A"
    assert a["form_year"] == 2021           # 202106 → 2021
    assert a["price_won"] == 2450 * 10000   # 만원 → 원 환산
    assert a["mileage_km"] == 30000         # mlgKm 패턴 매칭
    assert a["fuel"] == "디젤"              # fuelNm 전용 키 우선(트림명 '디젤 시그니처'에 오염 안 됨)
    assert a["model"] == "쏘렌토"


def test_kcar_normalize_price_in_won_passthrough():
    # 이미 원 단위(>=10만)면 그대로
    norm = kcar.normalize([_kcar_row(24500000)])
    assert norm[0]["price_won"] == 24500000


def test_kcar_normalize_skips_priceless():
    rows = [{"carCd": "X", "carNm": "쏘렌토", "mfgDt": "202106"}]  # 가격 없음
    assert kcar.normalize(rows) == []


def test_kcar_extract_rows_from_wrapper():
    body = {"data": {"rows": [_kcar_row(2500)]}, "success": True}
    assert len(kcar._extract_rows(body)) == 1


def test_kcar_model_is_group_not_trim():
    # 회귀 방지: 모델은 그룹명(쏘렌토)이어야지 트림(grdNm '2.2 디젤 시그니처')이면 안 됨
    m = kcar.normalize([_kcar_row(2500)])[0]["model"]
    assert m == "쏘렌토" and "디젤" not in m


def test_kcar_priced_count_excludes_prepare():
    # 판매목록(가격 有) vs 준비중(prc="") 구분
    rows = [_kcar_row(2500), _kcar_row(2600), {"carCd": "P", "prc": ""}]
    assert kcar._priced_count(rows) == 2


def test_kcar_fuel_prefers_name_over_code():
    # 회귀 방지: fuelCd(코드 '001')가 아닌 fuelNm(이름 '가솔린')을 써야 함
    row = _kcar_row(2500, fuel="가솔린")
    row["fuelCd"] = "001"
    assert kcar.normalize([row])[0]["fuel"] == "가솔린"


def test_gen_year_range_parses():
    assert kcar._gen_year_range("쏘렌토 4세대 20년~23년") == (2020, 2023)
    assert kcar._gen_year_range("더 뉴 쏘렌토 4세대 23년~") == (2023, 9999)
    assert kcar._gen_year_range("쏘렌토 02년~06년") == (2002, 2006)


def test_pick_generation_matches_year_and_hybrid():
    cands = [(2, "쏘렌토 4세대 20년~23년"), (0, "더 뉴 쏘렌토 4세대 23년~"),
             (6, "쏘렌토 4세대 하이브리드 20년~23년")]
    assert kcar._pick_generation(cands, 2021, False) == 2   # 연식 포함·비하이브리드
    assert kcar._pick_generation(cands, 2021, True) == 6    # 하이브리드 변형
    assert kcar._pick_generation(cands, 2024, False) == 0   # 23년~ 세대
    assert kcar._pick_generation([], 2021, False) is None


def test_kw_match_detects_filtered_list():
    # 키워드 필터 목록 판별: 쏘렌토 목록 vs 타임딜 혼합 목록
    sorento = [_kcar_row(2500, cd=f"S{i}") for i in range(3)]        # modelGrpNm=쏘렌토
    mixed = [{"modelGrpNm": "토레스", "prc": "1900", "carCd": "T"},
             {"modelGrpNm": "이쿼녹스", "prc": "2100", "carCd": "E"}]
    assert kcar._kw_match(sorento, "기아 쏘렌토") == 3
    assert kcar._kw_match(mixed, "기아 쏘렌토") == 0


# --- cross_source_check ---------------------------------------------------------------
def test_cross_source_agree_and_diverge():
    assert cross_source_check(3000, 3100)[0] == "agree"     # ~3% 차이
    assert cross_source_check(3000, 4000)[0] == "diverge"   # 33% 차이
    assert cross_source_check(3000, None)[0] == "single"


# --- summarize: 교차검증 상태에 따른 신뢰도 상한 -------------------------------------
def _encar_listings(n=20, price=30_000_000):
    return [{"platform": "encar", "form_year": 2021, "mileage_km": 30000,
             "price_won": price + (i % 5) * 100_000, "model": "쏘렌토",
             "badge": None, "fuel": None, "id": f"e{i}"} for i in range(n)]


def _conf(cross_status, kcar_median=None):
    return summarize(_encar_listings(), form_year=2021, mileage_km=30000,
                     platform="encar", appraisal_value=31_000_000,
                     config={"min_sample_count": 5},
                     cross_status=cross_status, cross_rel=0.03,
                     kcar_median=kcar_median, kcar_sample=12)


def test_single_source_capped_at_88():
    st = _conf(None)
    assert st.confidence <= 88
    assert st.cross_source_status == "single"


def test_agree_releases_single_source_cap():
    single = _conf(None).confidence
    agree = _conf("agree", kcar_median=30_500_000)
    assert agree.confidence > single           # 단일소스 상한(88) 해제
    assert agree.confidence <= 96              # cross_source_cap
    assert agree.kcar_median == 30_500_000
    assert "2소스일치" in agree.match_label


def test_diverge_caps_confidence():
    st = _conf("diverge", kcar_median=45_000_000)
    assert st.confidence <= 55
    assert "2소스불일치" in st.match_label


# --- tier 레벨(소스간 tier 정합 비교용) ------------------------------------------------
def test_tier_level_donggeup_is_zero():
    st = summarize(_encar_listings(), form_year=2021, mileage_km=30000, platform="encar",
                   config={"min_sample_count": 5})
    assert st.tier_level == 0          # 동급(연식±1·주행±30%)


def test_tier_level_relaxes_when_mileage_off():
    # 주행 4만(피물건 3만 대비 +33% → 동급 ±30% 밖, 확장 ±50% 안) → tier 1
    listings = [{"platform": "encar", "form_year": 2021, "mileage_km": 40000,
                 "price_won": 28_000_000 + (i % 4) * 100_000, "model": "쏘렌토",
                 "badge": None, "fuel": None, "id": f"e{i}"} for i in range(8)]
    st = summarize(listings, form_year=2021, mileage_km=30000, platform="encar",
                   config={"min_sample_count": 5})
    assert st.tier_level == 1          # 확장 tier


# --- 교차검증 컬럼은 단일소스 재분석 경로에서 기록되지 않아야 함([C] 덮어쓰기 방지) --------
def test_guarded_fields_excludes_cross_columns():
    st = summarize(_encar_listings(), form_year=2021, mileage_km=30000, platform="encar",
                   config={"min_sample_count": 5})
    f = service._guarded_market_fields(st)
    for col in ("kcar_median", "kcar_sample", "cross_source_status", "cross_source_rel"):
        assert col not in f            # kcar_crosscheck만 기록(기존 값 보존)


# --- 재교정 케이카 라이브 교차검증(_kcar_cross_live): 캐시·상한·상한해제 -----------------
class _FakeKS:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def search(self, kw, year=None, hybrid=False):
        self.calls += 1
        return {"results": self.rows, "reached": True}


def test_kcar_cross_live_releases_cap_and_caches():
    cfg = {"min_sample_count": 5, "cross_source_tol": 0.10}
    # 고유 스펙 20건(주행·가격 상이) → dedup 후에도 20건, 저cv → 단일소스 상한 88에 도달
    listings = [{"platform": "encar", "form_year": 2021, "mileage_km": 28000 + i * 100,
                 "price_won": 30_000_000 + i * 50_000, "model": "쏘렌토",
                 "badge": None, "fuel": None, "id": f"e{i}"} for i in range(20)]
    stats = summarize(listings, form_year=2021, mileage_km=30000, platform="encar",
                      appraisal_value=31_000_000, config=cfg)
    assert stats.confidence == 88                        # 단일소스 상한에 도달
    kraw = [_kcar_row(3000 + i * 10, year="202106", km=30000, cd=f"k{i}") for i in range(12)]
    ks = _FakeKS(kraw)
    kcache, kreq = {}, {"n": 0, "cap": 200}
    v = {"model": "기아 쏘렌토", "year": 2021, "mileage_km": 30000, "appraisal_value": 31_000_000}
    st, kf, blk = service._kcar_cross_live(ks, kcache, kreq, v, None, listings, stats, 2021, cfg)
    assert blk is False
    assert kf["cross_source_status"] == "agree"          # 케이카 30M ≈ 엔카 30M
    assert st.confidence > 88                             # 단일소스 상한 해제
    assert ks.calls == 1
    # 같은 (모델·연식·연료) 2번째 물건 → 캐시 히트(추가 조회 없음)
    service._kcar_cross_live(ks, kcache, kreq, v, None, listings, stats, 2021, cfg)
    assert ks.calls == 1


def test_kcar_cross_live_respects_request_cap():
    cfg = {"min_sample_count": 5, "cross_source_tol": 0.10}
    listings = _encar_listings(20)
    stats = summarize(listings, form_year=2021, mileage_km=30000, platform="encar", config=cfg)
    ks = _FakeKS([_kcar_row(3000, cd=f"k{i}") for i in range(12)])
    kcache, kreq = {}, {"n": 5, "cap": 5}                 # 이미 상한 도달
    v = {"model": "기아 쏘렌토", "year": 2021, "mileage_km": 30000}
    st, kf, blk = service._kcar_cross_live(ks, kcache, kreq, v, None, listings, stats, 2021, cfg)
    assert ks.calls == 0                                  # 상한 도달 → 케이카 미조회
    assert kf == {} or kf.get("cross_source_status") == "single"


# --- service._kcar_keyword ------------------------------------------------------------
def test_kcar_keyword_strips_noise():
    assert service._kcar_keyword("제네시스 G80 (RG3) 3.5T") == "제네시스 G80"
    assert service._kcar_keyword("기아 쏘렌토") == "기아 쏘렌토"
    assert service._kcar_keyword(None) == ""
