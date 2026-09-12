"""전문가 패널 1회차 P0 수정 회귀 테스트 (2026-09-12).

세 건 모두 '데이터가 없거나 불리한 사실을 화면이 유리하게 왜곡하던' 문제였다.
이 앱의 1순위 가치가 데이터 신뢰성이므로, 되돌아가면 즉시 실패하도록 고정한다.

P0-1 리포트 §01의 "시세 대비 예상낙찰가 %"가 이 물건이 아니라 **모집단 중앙값**을 렌더링.
      73% 표시 vs 실제 105% (3/3 재현). 원인 `report.html`의 `report.discount`.
P0-2 사고 이력 **자료가 없으면** 등급 'none' → 화면 '무사고' → 육각형 사고축 **100점**.
      같은 리포트 신뢰도 패널은 같은 항목을 '60점·추정'이라 표기해 한 화면에서 모순.
P0-3 예상낙찰가가 소매 시세를 넘는데 "직접 타실 목적이면 검토할 만합니다"로 안내.
      335건이 해당(전문가 3인 합의 지적).
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service

# ── 백테스트 통계 고정 ────────────────────────────────────────────
# 주입하지 않으면 plain_verdict → bid_state → backtest_stats() 가 **운영 DB**를 읽는다.
# 4회차 품질 감사: 그 상태에서 이 파일의 회귀 가드 7건이 데이터에 따라 깨지거나
# 조용히 통과했다. 회귀 가드의 실행 여부가 그날 PC의 데이터에 달려 있으면 가드가 아니다.
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "within20_pct": 96, "pred_n": 135,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)]}


@pytest.fixture(autouse=True)
def _fixed_backtest(monkeypatch):
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)



# ── P0-2 사고 이력 근거 ──────────────────────────────────────
@pytest.mark.parametrize("v,expected", [
    ({"accident_grade": "none"}, "이력 미확인"),                                  # 자료 없음
    ({"accident_grade": "none", "insurance_history": {}}, "이력 미확인"),          # 빈 dict도 자료 없음
    ({"accident_grade": "none", "insurance_history": {"내차피해": 0}}, "무사고"),   # 0건이라도 '조회함'
    ({"accident_grade": "none", "insurance_history": {"내차피해": 2}}, "무사고"),
    ({"accident_grade": "accident", "accident_hits": ["판금"]}, "사고"),
    ({"accident_grade": "flood"}, "침수의심"),
    ({"accident_grade": None}, "—"),
])
def test_accident_label_never_asserts_no_accident_without_evidence(v, expected):
    assert service.accident_label(v) == expected


def test_hexagon_accident_axis_unscored_without_evidence():
    """근거 없는 'none'에 만점을 주지 않는다 — 잔존가치 축과 같은 미산출 원칙."""
    v = {"accident_grade": "none", "year": 2020, "mileage_km": 50000}
    ax = {a["key"]: a for a in service.hexagon_scores(v)["axes"]}
    assert ax["cond"]["score"] is None, "자료가 없는데 사고·상태 점수가 매겨졌다"
    assert "미확인" in ax["cond"]["note"]


def test_hexagon_accident_axis_scored_with_evidence():
    v = {"accident_grade": "none", "insurance_history": {"내차피해": 0},
         "year": 2020, "mileage_km": 50000}
    ax = {a["key"]: a for a in service.hexagon_scores(v)["axes"]}
    assert ax["cond"]["score"] == 100
    assert ax["cond"]["note"].startswith("사고 이력 없음")


def test_confidence_panel_and_hexagon_agree():
    """신뢰도 패널이 '추정 60'이라고 말하면 육각형도 만점을 주면 안 된다(한 화면 모순 방지)."""
    v = {"accident_grade": "none", "year": 2020, "mileage_km": 50000,
         "median_price": 10_000_000, "min_sale_price": 8_000_000}
    cats = {c["name"]: c for c in service.report_bundle(v)["confidence_cats"]} \
        if hasattr(service, "report_bundle") else None
    ax = {a["key"]: a for a in service.hexagon_scores(v)["axes"]}
    if cats:                                  # 번들 구조가 바뀌어도 육각형 불변식은 지킨다
        assert cats["사고·이력"]["tag"] == "estimated"
    assert ax["cond"]["score"] is None


# ── P0-3 시세 초과 물건 ──────────────────────────────────────
def _v(med, floor=None, upper=11_283_000):
    return {"median_price": med, "min_sale_price": floor if floor is not None else med - 1_000_000,
            "upper_bid": upper, "market_confidence_label": "높음", "fail_count": 1}


# 문구가 아니라 **불변식**을 검사한다. 3회차에 판정이 bid_state 단일 소스로 바뀌면서
# 같은 물건이 더 강한 'blocked'(최저가조차 손익분기 초과 → "입찰하지 마세요")를 받게 됐다.
# 문구를 박아두면 판정이 강해질 때마다 테스트가 깨지고, 약해질 때는 안 깨진다 — 방향이 반대다.
_REFUSALS = ("권하지 않습니다", "입찰하지 마세요", "까지만 유효", "기다리는 게 좋습니다")


def _assert_refuses(r):
    assert r["tone"] in ("caution", "stop"), f"경고 톤이 아님: {r['tone']}"
    assert any(k in r["text"] for k in _REFUSALS), f"거절 문구가 없음: {r['text']}"
    for bad in ("검토할 만합니다", "노려볼 만합니다", "검토 가능"):
        assert bad not in r["text"], f"거절해야 하는데 권유 문구가 있음: {bad}"


def test_verdict_refuses_when_expected_above_retail():
    _assert_refuses(service.plain_verdict(_v(17_300_000, 16_000_000), {"price": 18_100_000}))


@pytest.mark.parametrize("exp,med", [(17_300_001, 17_300_000), (34_200_000, 32_500_000),
                                     (12_000_000, 10_895_000), (8_700_000, 8_300_000)])
def test_verdict_over_market_variants(exp, med):
    _assert_refuses(service.plain_verdict(_v(med, min(exp, med) - 100_000), {"price": exp}))


def test_verdict_blocks_when_floor_already_exceeds_breakeven():
    """최저매각가조차 실사용 손익분기를 넘으면 **써낼 수 있는 모든 금액이 손해**다.

    3회차 경매 지적: "낙찰 가능성이 낮다"고만 쓰면 초보자는 '더 쓰면 되겠네'로 읽는다.
    실제 사실은 정반대 — 어떤 금액을 써도 진다."""
    v = _v(17_300_000, 16_000_000)
    st = service.bid_state(v)
    assert st["state"] == "blocked" and st["tone"] == "stop"
    r = service.plain_verdict(v, {"price": 18_100_000}, st)
    assert "입찰하지 마세요" in r["text"]


def test_never_recommends_and_refuses_at_the_same_time():
    """같은 판정문에 거절과 권유가 함께 나오면 안 된다(3회차 품질 지적: 46건 중 28건)."""
    for med, floor, exp in [(17_300_000, 16_000_000, 18_100_000),
                            (16_600_000, 14_000_000, 16_600_000),
                            (40_000_000, 28_000_000, 31_600_000)]:
        r = service.plain_verdict(_v(med, floor), {"price": exp})
        refuses = any(k in r["text"] for k in _REFUSALS)
        recommends = any(k in r["text"] for k in ("검토할 만합니다", "노려볼 만합니다"))
        assert not (refuses and recommends), f"거절+권유 동시 출현: {r['text']}"


def test_verdict_still_recommends_when_below_retail():
    """시세보다 싼 물건까지 막으면 제품이 죽는다 — 정상 경로는 그대로여야 한다."""
    r = service.plain_verdict(_v(17_300_000, 11_000_000), {"price": 12_110_000})
    assert r["tone"] == "ok" and "입찰할 수 있고" in r["text"]


# ── P0-1 리포트 비율 ────────────────────────────────────────
@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_vehicle({
        "id": "P1_1", "folder_key": "P1_1", "case_no": "2026타경777", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "그랜저", "year": 2018,
        "min_sale_price": 16_000_000, "appraisal_value": 20_000_000, "fail_count": 1,
        "sale_date": "2999-01-01", "median_price": 17_300_000, "upper_bid": 11_283_000,
        "market_confidence": 77, "market_confidence_label": "높음",
        "judgment": "유찰 대기", "status": "완료", "accident_grade": "none",
        "mileage_km": 134_000,
    })
    # 예상낙찰가는 과거 낙찰 데이터에서 나오므로, 빈 DB에서는 산출되지 않는다.
    # 여기서 검증하려는 건 '템플릿이 어떤 값을 쓰는가'이므로 산출 결과를 고정 주입한다.
    monkeypatch.setattr(service, "backtest_stats",
                        lambda *a, **k: {"discount_median": 0.74, "sample": 172, "mae_pct": 9.2,
                                         "upper_hit_rate": None, "upper_n": 0,
                                         "within10_pct": 62, "within20_pct": 96, "pred_n": 172,
                                         "pred_pool": [], "n": 172})
    monkeypatch.setattr(service, "expected_band",
                        lambda *a, **k: {"price": 18_100_000, "lo": 16_800_000, "hi": 19_000_000,
                                         "premium": 1.129, "basis": {}})
    import web.app as A
    return TestClient(A.app)


def test_report_ratio_is_this_vehicle_not_population(app_client):
    """§01의 비율은 이 물건의 예상낙찰가÷시세여야 한다(모집단 중앙값이 아니라)."""
    html = app_client.get("/vehicle/P1_1/report").text
    assert "이 물건의 예상낙찰가는" in html, "비율 문장이 사라졌거나 문구가 바뀌었다"
    m = re.search(r"이 물건의 예상낙찰가는 <b[^>]*>약 (\d+)%", html)
    assert m, "비율 숫자를 찾지 못했다"
    pct = int(m.group(1))
    # 시세 17,300,000 기준 — 모집단 낙찰가율(보통 70%대)이 그대로 찍히면 이 검사가 잡는다
    assert 90 <= pct <= 130, f"이 물건 비율이 아니라 모집단 통계로 보인다: {pct}%"


def test_report_marks_over_market_and_hides_recommendation(app_client):
    html = app_client.get("/vehicle/P1_1/report").text
    assert "시세 초과" in html
    assert "지금 입찰 검토 가능" not in html, "시세를 넘는데 '검토 가능'이라고 표시했다"


def test_report_shows_unverified_accident(app_client):
    """보험이력이 없는 물건의 리포트에 '무사고'가 단정으로 찍히면 안 된다."""
    html = app_client.get("/vehicle/P1_1/report").text
    assert "이력 미확인" in html
