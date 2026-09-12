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

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


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
    assert b["price"] <= b["basis"]["cap"]
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

def test_reduction_rates_are_measured_not_invented():
    r = service.court_reduction_rates()
    assert r["n"] > 100, "표본이 이 정도는 돼야 법원별로 나눌 수 있다"
    assert r["global"] in (0.7, 0.8), f"실측 저감배율이 예상 밖: {r['global']}"
    for court, info in r["by_court"].items():
        assert info["n"] >= 5, f"{court}: 표본 {info['n']}건으로 법원값을 주장하면 안 된다"
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


def test_accident_count_uses_both_own_and_opposite_damage():
    assert service.accident_hit_count(v(insurance_history=_ins(own=2, opp=3))) == 5
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


def test_accuracy_for_picks_the_worse_stratum():
    """낙관적인 층을 고르면 안 된다 — 불리한 쪽을 택한다."""
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata()}
    car = v(fail_count=5, maker="BMW", model="520d")           # 수입 + 유찰 3회 이상
    got = service.accuracy_for(car)
    cands = [rows.get(("제조사", "수입")), rows.get(("유찰횟수", "유찰 3회 이상"))]
    cands = [c for c in cands if c and c["mae"] is not None]
    if cands and got:
        assert got["mae"] == max(c["mae"] for c in cands)


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
