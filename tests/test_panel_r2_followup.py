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
