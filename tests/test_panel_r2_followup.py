"""2회차 패널 미처리 지적 조치 회귀 테스트 (2026-09-12).

1·2회차에서 연속으로 지적됐는데 남아 있던 것들:
  · 입찰 상한선('얼마까지 써도 되는가')이 없고 재판매 마진 상한가만 있었다
  · 소프트캡이 걸린 물건의 §10 산식이 검산되지 않았다(42,000,000×1.129 ≠ 17,500,000)
  · §07이 최저매각가 미만 입찰가를 후보로 내고 '우량'까지 판정했다
  · 인수권리 경고가 부동산 템플릿(임차권·지상권·등기부)이었다 — 차량엔 성립하지 않는 권리
"""
import pytest
from starlette.testclient import TestClient

from web import service

# min_premium_pool이 없으면 win_probability가 None → 템플릿이 else 분기만 탄다.
# 4회차에 이것 때문에 "낙찰 확률" 분기의 UndefinedError(프로덕션 500)를 못 잡았다 —
# 품질 전문가가 경고한 "픽스처가 그 분기를 렌더한 적이 없다"에 그대로 빠진 것이다.
BT = {"min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      # accuracy_for()가 층별 오차를 내려면 pred_pool이 필요하다. 없으면 추천 게이트가
      # "오차를 모르면 추천하지 않는다"로 막아 픽스처가 전부 빠진다(의도된 동작).
      "pred_pool": [{"err_pct": 8.0 + (i % 5), "maker": "현대", "model": "쏘나타",
                     "fail_count": 1, "median_price": 20_000_000, "actual": 20_000_000}
                    for i in range(40)],}


def v(**kw):
    base = {"median_price": 40_000_000, "min_sale_price": 28_000_000, "fail_count": 1,
            "market_confidence_label": "높음", "accident_grade": "none", "judgment": "유찰 대기"}
    base.update(kw)
    return base


# ── 입찰 상한선 ──────────────────────────────────────────────────
def test_max_bid_is_the_breakeven_of_the_saving_formula():
    """상한선은 절감액이 0이 되는 지점이어야 한다 — 두 식이 따로 놀면 안 된다."""
    car = v()
    mb = service.personal_use_max_bid(car, BT)
    assert mb and mb > 0
    # 상한선보다 확실히 싸게 낙찰되는 시나리오는 이득, 확실히 비싸면 손해
    cheap = dict(car, min_sale_price=int(mb * 0.6 / 1.13))
    dear = dict(car, min_sale_price=int(mb * 1.6 / 1.13))
    assert service.personal_use_saving(cheap, BT) is not None
    assert service.personal_use_saving(dear, BT) is None


def test_max_bid_reflects_condition_and_accident_assumption():
    """상태가 나쁘거나 사고 이력이 확인되면 상한선은 내려가야 한다."""
    good = service.personal_use_max_bid(v(insurance_history={"내차피해": 0}), BT)
    unknown = service.personal_use_max_bid(v(), BT)                    # 이력 미확인 → 사고 가정
    poor = service.personal_use_max_bid(v(condition_level="poor"), BT)
    assert unknown < good, "이력 미확인이 무사고 확인보다 상한선이 높으면 안 된다"
    assert poor < unknown, "상태 불량은 정비 충당만큼 상한선이 내려가야 한다"


def test_max_bid_absent_when_we_cannot_claim_it():
    assert service.personal_use_max_bid(v(market_confidence_label="낮음"), BT) is None
    assert service.personal_use_max_bid(v(runnable="no"), BT) is None
    assert service.personal_use_max_bid(v(median_price=None), BT) is None


# ── 소프트캡 검산 ────────────────────────────────────────────────
def test_soft_cap_is_shown_as_its_own_step():
    """캡이 걸리면 basis가 캡 전후 값을 함께 내야 화면 검산이 닫힌다."""
    capped = v(min_sale_price=42_000_000, median_price=15_900_000, fail_count=1)
    b = service.expected_band(capped, BT)
    assert b["basis"]["capped"] is True
    assert b["basis"]["raw"] > b["basis"]["cap"]
    # 5회차: 캡을 최저매각가 아래로 내리면 **법적으로 써낼 수 없는 금액**이 인쇄된다
    # (실측 61장 중 6장, 덤프트럭은 최저가의 27%). 최저가 하한이 캡보다 우선한다.
    assert b["price"] == max(b["basis"]["cap"], capped["min_sale_price"])
    assert b["price"] >= capped["min_sale_price"]
    # 캡이 안 걸리는 평범한 물건은 단계를 늘리지 않는다
    plain = service.expected_band(v(), BT)
    assert plain["basis"]["capped"] is False


# ── §07 시뮬레이션 하한 ──────────────────────────────────────────
def test_simulation_never_offers_a_bid_below_the_legal_floor():
    """최저매각가 미만은 써낼 수 없는 금액이다 — 후보로 내면 무효 입찰을 유도한다."""
    cfg = service.load_config()
    capped = v(min_sale_price=42_000_000, median_price=15_900_000,
               upper_bid=10_000_000, fail_count=1)
    rep = service.report_data(capped, cfg, BT)
    assert rep, "리포트 데이터가 나와야 이 테스트가 의미 있다"
    assert rep["sim"], "시뮬레이션 행이 비면 테스트가 공허하다"
    for row in rep["sim"]:
        assert row["bid"] >= capped["min_sale_price"], (
            f"최저매각가 {capped['min_sale_price']:,} 미만 입찰가 {row['bid']:,}가 후보로 나왔다")


# ── 차량 전용 권리 문구 ──────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({
        "id": "R1_1", "folder_key": "R1_1", "case_no": "2026타경5", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
        "min_sale_price": 28000000, "appraisal_value": 32000000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 40000000, "market_confidence": 78,
        "market_confidence_label": "높음", "sample_count": 12,
    })
    import web.app as A
    return TestClient(A.app)


_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


def test_rights_warning_is_about_cars_not_real_estate(client):
    html = client.get("/vehicle/R1_1/report", headers=_PUBLIC).text
    for w in ("임차권", "지상권"):
        assert w not in html, f"차량에 성립하지 않는 부동산 권리 '{w}'가 남아 있다"
    assert "등기부" not in html, "차량은 등기부가 아니라 자동차등록원부로 확인한다"
    for w in ("유치권", "자동차등록원부", "과태료"):
        assert w in html, f"차량 경매에서 실제로 돈이 새는 항목 '{w}'가 없다"


def test_report_shows_the_max_bid(client):
    html = client.get("/vehicle/R1_1/report", headers=_PUBLIC).text
    assert "입찰 상한선" in html


# ── 법원별 저감률 · 다음 기일 최저가 ─────────────────────────────
# 경매 전문가 1·2회차 연속 지적: "유찰 대기 물건 사용자에게 필요한 유일한 숫자는
# '다음 기일에는 얼마부터 시작하나'인데 그게 없다."
# 외부 자료를 쓰지 않고 **우리 기일내역**에서 실측한다 — 622건 관측, 0.70(83%)/0.80(16%).

def test_reduction_rates_are_measured_not_invented(tmp_path, monkeypatch):
    """저감률은 기일내역에서 실측한다 — 표본이 부족한 법원은 값을 주장하지 않는다.

    ⚠ 예전엔 운영 DB를 그대로 읽었다. 그러면 결과가 그날 데이터에 달려 있고,
    빈 DB(CI·새 클론)에서는 통째로 깨진다(4회차 품질 지적 3). 데이터를 직접 만든다."""
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "red.db")
    monkeypatch.setattr(service, "_reduction_cache", {"key": None, "data": None})
    db.init_db()
    base = {"maker": "현대", "model": "쏘나타", "item_no": "1", "sale_date": "2999-01-01"}

    def hist(*prices):
        return [{"ymd": f"2026-0{i+1}-01", "lws_price": p} for i, p in enumerate(prices)]

    for i in range(6):        # 수원 = 0.7 로 일정
        db.upsert_vehicle(dict(base, id=f"S{i}_1", folder_key=f"S{i}_1",
                               case_no=f"2026타경1{i:03d}", court="수원지방법원",
                               dxdy_history=hist(10_000_000, 7_000_000, 4_900_000)))
    for i in range(6):        # 서울남부 = 0.8 로 일정
        db.upsert_vehicle(dict(base, id=f"N{i}_1", folder_key=f"N{i}_1",
                               case_no=f"2026타경2{i:03d}", court="서울남부지방법원",
                               dxdy_history=hist(10_000_000, 8_000_000)))
    for i in range(3):        # 표본 부족 법원 — by_court에 들어가면 안 된다
        db.upsert_vehicle(dict(base, id=f"X{i}_1", folder_key=f"X{i}_1",
                               case_no=f"2026타경3{i:03d}", court="표본부족지원",
                               dxdy_history=hist(10_000_000, 7_000_000)))
    r = service.court_reduction_rates()
    assert r["global"] == 0.7 and r["n"] >= 15
    assert r["by_court"]["수원지방법원"]["ratio"] == 0.7
    assert r["by_court"]["서울남부지방법원"]["ratio"] == 0.8
    assert "표본부족지원" not in r["by_court"], "표본 3건으로 법원값을 주장하면 안 된다"
    for court, info in r["by_court"].items():
        assert info["n"] >= service._REDUCTION_MIN_N
        assert 0.5 <= info["ratio"] <= 0.95


def test_next_min_uses_the_courts_own_rate_when_we_have_one():
    r = {"by_court": {"수원지방법원": {"ratio": 0.7, "n": 86, "share": 1.0},
                      "서울남부지방법원": {"ratio": 0.8, "n": 14, "share": 1.0}},
         "global": 0.7, "n": 609, "observed": {}}
    a = service.next_min_sale({"min_sale_price": 10_000_000, "court": "수원지방법원"}, r)
    b = service.next_min_sale({"min_sale_price": 10_000_000, "court": "서울남부지방법원"}, r)
    assert a["price"] == 7_000_000 and a["basis"] == "court" and a["court_n"] == 86
    assert b["price"] == 8_000_000 and b["basis"] == "court"


def test_next_min_says_so_when_it_falls_back_to_the_global_rate():
    """법원 표본이 없으면 전국값을 쓰되 **법원값인 척하지 않는다**."""
    r = {"by_court": {}, "global": 0.7, "n": 609, "observed": {}}
    out = service.next_min_sale({"min_sale_price": 10_000_000, "court": "표본없는지원"}, r)
    assert out["basis"] == "global" and out["court_n"] is None


def test_next_min_absent_for_finished_items():
    r = {"by_court": {}, "global": 0.7, "n": 9, "observed": {}}
    assert service.next_min_sale({"min_sale_price": 10_000_000, "auction_result": "낙찰"}, r) is None
    assert service.next_min_sale({"min_sale_price": 10_000_000, "judgment": "종결"}, r) is None
    assert service.next_min_sale({"min_sale_price": None}, r) is None


def test_detail_shows_next_min(client):
    html = client.get("/vehicle/R1_1", headers=_PUBLIC).text
    assert "다음 기일 예상 최저가" in html


# ── 사건번호 형식 ────────────────────────────────────────────────
def test_malformed_case_numbers_are_hidden_from_public_list(tmp_path, monkeypatch):
    """'(중복)'·'(병합)'은 사건번호가 아니라 법원 목록의 표기다.

    2026-09-12 2회차 품질 지적 5: `/vehicle/(중복)_1`이 공개 목록·URL에 노출됐다.
    사건번호는 사용자가 법원에서 물건을 특정하는 유일한 키라, 이걸로는 찾을 수 없다.
    """
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "cn.db")
    db.init_db()
    base = {"court": "수원지방법원", "maker": "BMW", "model": "X3", "year": 2021,
            "min_sale_price": 42000000, "appraisal_value": 42000000, "item_no": "1",
            "sale_date": "2999-01-01", "status": "완료", "median_price": 15900000,
            "market_confidence_label": "낮음", "judgment": "시세 신뢰도 낮음, 수동 검토"}
    db.upsert_vehicle(dict(base, id="OK_1", folder_key="OK_1", case_no="2026타경1234"))
    db.upsert_vehicle(dict(base, id="DUP_1", folder_key="DUP_1", case_no="(중복)"))
    db.upsert_vehicle(dict(base, id="MRG_1", folder_key="MRG_1", case_no="(병합)"))
    ids = {v["id"] for v in db.list_vehicles(hide_incomplete=True)}
    assert "OK_1" in ids
    assert "DUP_1" not in ids and "MRG_1" not in ids
    # 관리자용 전체 조회(hide_incomplete=False)에서는 여전히 보여야 한다 — 데이터가 사라지면 못 고친다
    all_ids = {v["id"] for v in db.list_vehicles(hide_incomplete=False)}
    assert {"DUP_1", "MRG_1"} <= all_ids


# ── 감정서 표기 변형 (3회차 중고차 지적 3) ──────────────────────
# 실측(로컬 1,305건): 스크레치류 32건 · "양호치 못함" 6건 · 회손 1건.
# 미탐은 언제나 충당 과소 → 상한선 과대 → 사용자가 더 많이 쓰게 된다.
@pytest.mark.parametrize("text,level", [
    ("전면 범퍼, 펜더 회손된 상태 및 외부에 다소의 흠집이 있는 상태로서 관리상태는 양호치 못함.", "poor"),
    ("일부 부분적인 스크레치 등이 관찰되나 전반적으로 양호함.", "fair"),
    ("좌측 전면에 일부 스크레치가 목측되었으나.", "fair"),
    ("차량 외부에 스크래치 등이 있으니 참고바람.", "fair"),
    ("관리상태 양호하지 못함.", "poor"),
    ("외관 상태 보통임.", "unknown"),
])
def test_appraisal_parser_handles_real_world_spellings(text, level):
    from src.parse.appraisal import parse_appraisal
    assert parse_appraisal(text)["condition"]["level"] == level, text


def test_condition_costs_actually_change_the_reserve():
    """표기를 잡아도 비용에 안 붙으면 의미가 없다 — 끝까지 연결되는지 본다."""
    from src.parse.appraisal import condition_adjustment
    cfg = service.load_config()
    poor = condition_adjustment("범퍼 회손, 관리상태 양호치 못함.", cfg)
    assert poor["add"] >= cfg["condition_costs"]["poor"]
    assert "관리·외관 불량" in poor["flags"]


# ── 사고 건수별 감가 · 정비 충당 비례 하한 (3회차 중고차 지적 2) ──
# "사고 11회 A6와 사고 1회 차의 감가가 같다", "포르쉐 718과 카니발의 정비 충당이 같다".
# ⚠ 감가 표는 실측이 아니라 가정이다 — 자사 낙찰 표본은 층당 n=1~7이라 보정 근거가 못 됐다.
#    테스트는 '값이 얼마인가'가 아니라 **순서와 방향**을 지킨다(표를 바꿔도 안 깨진다).

def _ins(own=0, opp=0):
    return {"own_damage": own, "opp_damage": opp, "owner_changes": 1}


def test_accident_rate_increases_with_hit_count():
    cfg = service.load_config()
    rates = [service.use_accident_rate(
        v(accident_grade="accident", insurance_history=_ins(own=n)), cfg)[0]
        for n in (1, 3, 5, 12)]
    assert rates == sorted(rates), f"건수가 늘수록 감가가 커져야 한다: {rates}"
    assert rates[0] < rates[-1], "1회와 12회의 감가가 같으면 안 된다"


def test_accident_count_uses_own_damage_only():
    # 4회차엔 own+opp를 더했다. 5회차 중고차 지적: 상대차피해는 이 차가 남의 차에
    # 입힌 손상이라 이 차의 가치와 무관하다. 더하면 감가가 계통적으로 과대해진다.
    assert service.accident_hit_count(v(insurance_history=_ins(own=2, opp=3))) == 2
    # 이력을 확보하지 못하면 0이 아니라 '모른다' — 0으로 치면 근거 없는 무사고가 된다
    assert service.accident_hit_count(v()) is None
    assert service.accident_hit_count(v(insurance_history={"owner_changes": 2})) is None


def test_unknown_history_still_assumes_accident():
    """건수별 표를 넣어도 '이력 미확인 → 사고 가정' 규칙은 유지돼야 한다."""
    rate, assumed = service.use_accident_rate(v(accident_grade="none"))
    assert assumed is True and rate > 0


def test_repair_reserve_scales_with_vehicle_value():
    """정액만 쓰면 고가차의 충당이 낙찰가의 1%대가 된다."""
    cheap = service.use_repair_reserve(v(median_price=5_000_000, photo_count=3))
    dear = service.use_repair_reserve(v(median_price=90_000_000, photo_count=3))
    assert dear > cheap * 3, f"고가차 충당이 비례해 오르지 않는다: {cheap} vs {dear}"
    # 저가차에서는 정액 하한이 유지된다(비례만 쓰면 충당이 거의 사라진다)
    assert cheap >= service.USE_REPAIR_BASE


def test_graded_rate_makes_max_bid_more_conservative_for_multi_accident():
    """감가가 커지면 상한선은 반드시 내려간다 — 방향이 뒤집히면 안 된다."""
    one = service.personal_use_max_bid(
        v(accident_grade="accident", insurance_history=_ins(own=1)), BT)
    many = service.personal_use_max_bid(
        v(accident_grade="accident", insurance_history=_ins(own=12)), BT)
    assert one and many and many < one


# ── 적중률 층화 (3회차 경매·중고차 공통 지적) ────────────────────
# "검증 사례가 전부 국산인데 수입차에도 ±9% 배지를 똑같이 찍는다 —
#  표본에 없는 모집단에 정확도를 전이시키는 과대주장."

def test_strata_never_reports_a_number_without_enough_samples():
    for r in service.accuracy_strata():
        if r["n"] < service.ACCURACY_STRATUM_MIN_N:
            assert r["mae"] is None and r["within10"] is None, (
                f"{r['group']}/{r['label']}: 표본 {r['n']}건인데 숫자를 냈다")
        else:
            assert r["mae"] is not None


def test_accuracy_for_picks_the_worse_stratum(monkeypatch):
    """낙관적인 층을 고르면 안 된다 — 불리한 쪽을 택한다.

    ⚠ 예전엔 `if cands and got:` 안에서만 단언해, 운영 DB의 수입차 표본이 8건 밑으로
    떨어지면 **어서션을 하나도 실행하지 않고 통과**했다. 그 상태에서 max()를 min()으로
    바꿔도 초록불이었다 — 이 테스트가 막으라고 만들어진 결함이 정확히 그것이다
    (4회차 품질 지적 3). 층 데이터를 테스트가 직접 만든다."""
    strata = [
        {"group": "제조사", "label": "수입", "n": 40, "mae": 10.4, "within10": 54},
        {"group": "제조사", "label": "국산", "n": 98, "mae": 8.7, "within10": 64},
        {"group": "유찰횟수", "label": "유찰 3회 이상", "n": 17, "mae": 12.8, "within10": 41},
        {"group": "유찰횟수", "label": "유찰 0~1회", "n": 59, "mae": 8.0, "within10": 71},
    ]
    monkeypatch.setattr(service, "accuracy_strata", lambda *a, **k: strata)
    got = service.accuracy_for(v(fail_count=5, maker="BMW", model="520d"))
    assert got is not None, "층이 둘 다 있는데 값을 못 냈다"
    assert got["mae"] == 12.8, f"불리한 층(12.8)이 아니라 {got['mae']}를 골랐다"
    # 유리한 층만 있는 경우에도 그 값을 쓴다
    got2 = service.accuracy_for(v(fail_count=0, maker="현대", model="그랜저"))
    assert got2["mae"] == 8.7


def test_domestic_detection_handles_real_maker_strings():
    for maker, model, dom in [("현대자동차(주)", "그랜저", True), ("기아자동차", "쏘렌토", True),
                              ("제네시스", "G80", True), ("르노삼성자동차", "QM6", True),
                              ("BMW", "520d", False), ("메르세데스벤츠코리아", "E220 d", False),
                              ("마세라티", "르반떼", False)]:
        assert service.is_domestic_maker({"maker": maker, "model": model}) is dom, maker


# ── 4회차 P0: 판정과 출력 숫자가 어긋나지 않는다 ─────────────────
# 3인이 각각 지적: 빨간 "입찰하지 마세요" 바로 아래에 초록 금액 3개 +"낙찰 확률 ~75%".

@pytest.fixture
def bidclient(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "b4.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
            "item_no": "1", "sale_date": "2999-01-01", "status": "완료",
            "fail_count": 1, "market_confidence_label": "높음", "market_confidence": 78}
    # blocked: 최저매각가가 손익분기를 넘는다
    db.upsert_vehicle(dict(base, id="BLK_1", folder_key="BLK_1", case_no="2026타경701",
                           min_sale_price=16_000_000, appraisal_value=20_000_000,
                           median_price=16_600_000, judgment="유찰 대기"))
    # flood: 침수의심
    db.upsert_vehicle(dict(base, id="FLD_1", folder_key="FLD_1", case_no="2026타경702",
                           min_sale_price=9_000_000, appraisal_value=12_000_000,
                           median_price=13_000_000, accident_grade="flood",
                           judgment="입찰 보류"))
    # 정상 usepick
    db.upsert_vehicle(dict(base, id="OK_1", folder_key="OK_1", case_no="2026타경703",
                           min_sale_price=28_000_000, appraisal_value=30_000_000,
                           median_price=40_000_000, judgment="유찰 대기"))
    import web.app as A
    return TestClient(A.app)


_PUB = {"x-forwarded-for": "203.0.113.7"}


@pytest.mark.parametrize("vid", ["BLK_1", "FLD_1"])
def test_no_bid_amounts_offered_when_we_say_do_not_bid(bidclient, vid):
    html = bidclient.get(f"/vehicle/{vid}", headers=_PUB).text
    assert "입찰가를 제시하지 않습니다" in html, "차단 문구가 없다"
    assert "낙찰 확률" not in html, "입찰하지 말라면서 낙찰 확률을 제시하고 있다"


def test_normal_vehicle_still_gets_strategy(bidclient):
    """정상 물건까지 막으면 제품이 죽는다."""
    html = bidclient.get("/vehicle/OK_1", headers=_PUB).text
    assert "낙찰 확률" in html and "입찰가를 제시하지 않습니다" not in html


def test_flood_never_says_wait_for_cheaper(bidclient):
    """침수차에 '아직 비싸니 기다리세요'는 '싸지면 사라'로 읽힌다."""
    from web import db
    st = service.bid_state(db.get_vehicle("FLD_1"), BT)
    assert st["state"] == "blocked" and st["tone"] == "stop"
    r = service.plain_verdict(db.get_vehicle("FLD_1"), {"price": 9_000_000}, st)
    assert "기다리는 게 좋습니다" not in r["text"] and "입찰하지 마세요" in r["text"]


def test_state_never_green_without_a_breakeven():
    """상한선을 못 구했으면 초록불을 켜지 않는다."""
    st = service.bid_state(v(market_confidence_label="높음", runnable="no",
                             sale_date="2999-01-01"), BT)
    assert st["tone"] != "ok"


def test_past_sale_date_is_not_a_recommendation():
    st = service.bid_state(v(sale_date="2020-01-01"), BT)
    assert st["state"] == "wait" and st["tone"] != "ok"


def test_list_chip_uses_the_same_verdict_as_detail(bidclient):
    """목록 칩과 상세 판정이 같은 말을 해야 한다."""
    import re
    from web import db
    lst = bidclient.get("/vehicles", headers=_PUB).text
    for vid in ("BLK_1", "OK_1"):
        label = service.bid_state(db.get_vehicle(vid), BT)["label"]
        assert label in lst, f"{vid}: 목록에 판정 '{label}'이 없다"


def test_resale_breakeven_uses_the_same_accident_rate(bidclient):
    """재판매 손익분기와 실사용 상한선이 서로 다른 사고 감가를 쓰면 안 된다."""
    from src.bidcalc.calculator import BidInput
    car = v(accident_grade="none")            # 이력 미확인 → 사고 가정
    bi = BidInput(median_price=car["median_price"], min_sale_price=car["min_sale_price"],
                  sample_count=10, accident_grade="none")
    service.apply_accident_rate(bi, car)
    assert bi.accident_rate == service.use_accident_rate(car)[0]
    assert "무사고" not in bi.accident_label, "근거 없이 무사고라고 쓰면 안 된다"


# ── 낡은 최저가 (4회차 경매 P0) ──────────────────────────────────
# 유찰 1회 이상인데 최저가 == 감정가 = 저감 후 가격이 아직 공고되지 않은 것.
# 산식이 `최저매각가 × 프리미엄`이라 오차가 100% 전파되고, 방향은 항상 '부풀림'이다.
# 그리고 이 오류는 /accuracy에 절대 안 잡힌다 — 낙찰이 안 나므로 검증 표본에 없다.

def test_stale_floor_detected():
    assert service.stale_floor(v(appraisal_value=20_000_000,
                                 min_sale_price=20_000_000, fail_count=1)) is True
    assert service.stale_floor(v(appraisal_value=20_000_000,
                                 min_sale_price=14_000_000, fail_count=1)) is False
    assert service.stale_floor(v(appraisal_value=20_000_000,
                                 min_sale_price=20_000_000, fail_count=0)) is False


def test_stale_floor_blocks_expected_price():
    """낡은 출발선으로 만든 예측은 지어낸 값이다."""
    stale = v(appraisal_value=120_000_000, min_sale_price=120_000_000,
              fail_count=1, median_price=100_000_000)
    assert service.expected_for(stale, BT) is None
    # 상한선은 **시세**에서 나오므로 낡은 최저가와 무관하게 유효하다 — 지우지 않는다.
    assert service.personal_use_max_bid(stale, BT) is not None
    st = service.bid_state(stale, BT)
    assert st["tone"] != "ok", "가격을 못 믿는데 초록불이면 안 된다"
    assert st["state"] == "lowconf"
    # 정상 물건은 그대로 산출된다
    ok = v(appraisal_value=120_000_000, min_sale_price=84_000_000,
           fail_count=1, median_price=100_000_000)
    assert service.expected_for(ok, BT) is not None


# ── 상대차피해는 이 차의 감가가 아니다 (5회차 중고차 지적 3) ─────
def test_opposite_damage_is_not_counted_as_own_accident():
    """상대차피해는 이 차가 남의 차에 입힌 손상이다 — 이 차 가치와 무관하다."""
    only_opp = v(accident_grade="accident",
                 insurance_history={"own_damage": 0, "opp_damage": 1})
    assert service.accident_hit_count(only_opp) == 0
    assert service.opposite_damage_count(only_opp) == 1
    # 내차 4 + 상대차 4를 8건으로 세면 30%가 되지만, 내차 기준이면 22%다
    mixed = v(accident_grade="accident",
              insurance_history={"own_damage": 4, "opp_damage": 4})
    own_only = v(accident_grade="accident",
                 insurance_history={"own_damage": 4, "opp_damage": 0})
    assert service.use_accident_rate(mixed)[0] == service.use_accident_rate(own_only)[0]


# ── 다물건 감정서: 남의 차 정보가 붙지 않는다 (5회차 중고차 P0) ──
# 실측(2025타경101362): 기호3 그랜저(실제 70,842km)가 화면에 148,589km(기호1 값)로
# 표시되고, "기호2, 4는 시동이 안되는 상태" 문장에 걸려 시동 멀쩡한 기호3에 STOP이 붙었다.
_MULTI = """기호1 싼타페:2016년식, 주행거리-148,589km  기호3 그랜져:2020년식, 주행거리-70,842km
2) 기호1, 3, 5는 시동상태 보통이며 기호2, 4는 시동이 안되는 상태로 추정.
기호3 : 내차 피해(1회 - 3,995,341원)"""


def test_multi_symbol_appraisal_is_detected():
    from src.parse.appraisal import is_multi_symbol
    assert is_multi_symbol(_MULTI) is True
    assert is_multi_symbol("본건 차량은 시동이 걸리지 않는바.") is False


@pytest.mark.parametrize("sym,runnable", [(1, True), (2, False), (3, True), (4, False)])
def test_symbol_slice_keeps_only_this_vehicle(sym, runnable):
    from src.parse.appraisal import slice_for_symbol, parse_appraisal
    sub, ok = slice_for_symbol(_MULTI, sym)
    assert ok, "분리 실패"
    assert parse_appraisal(sub)["condition"]["runnable"] is runnable
    # 남의 차 주행거리가 섞이면 안 된다
    if sym == 3:
        assert "148,589" not in sub and "70,842" in sub


def test_unsplittable_multi_symbol_claims_nothing():
    """분리에 실패하면 상태를 주장하지 않는다 — 남의 차 서술로 판정하는 것보다 낫다."""
    from web import service
    sig = service._appraisal_signals(_MULTI, item_no=None)
    assert sig["condition_level"] == "unknown" and sig["runnable"] == "unknown"


def test_single_symbol_appraisal_is_unaffected():
    """단일 물건 감정서는 예전과 똑같이 동작해야 한다(과잉 차단 방지)."""
    from web import service
    sig = service._appraisal_signals(
        "본건 차량은 차량키가 있으나 시동이 걸리지 않는바 참고바람.", item_no="1")
    assert sig["runnable"] == "no"
