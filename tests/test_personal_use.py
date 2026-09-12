"""'실사용 추천' 분류 회귀 테스트 (2026-09-12 사용자 요청).

배경: 기존 '입찰 검토 가능'은 **재판매 마진**(upper_bid ≥ 최저매각가)을 요구한다.
실측하니 그 손익분기가 소매 시세의 중앙값 60%인데, 자사 적중률 페이지가 공개한
실제 낙찰가율 중앙값은 74%다. 시장이 거의 도달하지 못하는 선이라 1,320대 중 17대만 남았고,
직접 탈 사람에게 합리적인 물건 100여 대가 '유찰 대기'에 묻혀 있었다.

'실사용 추천'은 마진을 요구하지 않고 **소매로 사는 총비용보다 싼가**만 본다.
기준은 최저매각가가 아니라 **예상 낙찰가** — 최저가 기준은 '그 값에 낙찰될 때만' 성립하는
낙관치이고, 무엇보다 예상낙찰가가 시세를 넘으면 '비권장' 경고를 띄우면서 같은 물건을
추천하는 모순이 생긴다(P0-3과 정합).
"""
import pytest

from web import service

# 실제 산식은 **최저매각가 × 유찰버킷 프리미엄**(소프트캡 = 시세×1.10)이다.
# 이 필드를 빼면 '시세×할인율' 폴백으로 새 경로를 타 테스트가 의도를 못 지킨다.
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


def v(**kw):
    base = {"median_price": 40_000_000, "min_sale_price": 28_000_000, "fail_count": 1,
            "market_confidence_label": "높음", "accident_grade": "none", "judgment": "유찰 대기"}
    base.update(kw)
    return base


def test_saving_is_positive_when_auction_beats_retail():
    s = service.personal_use_saving(v(), BT)
    assert s and s > 0


def test_no_saving_when_expected_close_to_retail():
    """예상 낙찰가가 시세에 근접하면 취득세·이전·정비를 더해 소매가 유리해진다.

    최저 2,900만 × 프리미엄 1.13 = 3,277만 → 소프트캡(3,000만×1.10=3,300만) 아래라 그대로.
    경매 총비용이 소매 총비용을 넘으므로 추천 대상이 아니다.
    """
    assert service.personal_use_saving(v(median_price=30_000_000, min_sale_price=29_000_000), BT) is None


@pytest.mark.parametrize("kw,why", [
    ({"median_price": None}, "시세가 없으면 비교 자체가 불가"),
    ({"market_confidence_label": "낮음"}, "시세를 못 믿으면 추천하면 안 된다"),
    ({"accident_grade": "flood"}, "침수·전손은 추천 대상이 아니다"),
    ({"judgment": "종결"}, "이미 끝난 물건"),
    ({"judgment": "입찰 보류"}, "위험 신호가 있는 물건"),
])
def test_excluded_cases(kw, why):
    assert service.personal_use_saving(v(**kw), BT) is None, why


def test_resale_pick_does_not_double_count():
    """재판매 기준을 통과한 물건은 그쪽 칸이 가져간다 — 대시보드 합계가 총대수와 맞아야 한다."""
    assert service.is_personal_use_pick(v(judgment="입찰 검토 가능"), BT) is False


def test_uses_expected_price_not_floor():
    """최저매각가가 아무리 낮아도 예상 낙찰가가 시세를 넘으면 추천하지 않는다.

    P0-3에서 '예상낙찰가 > 시세면 입찰 비권장'을 띄우기로 했으므로 같은 물건을
    추천 칸에 올리면 한 화면에서 모순된다.
    """
    # 최저가가 시세보다 높은 신건 → 예상낙찰가는 소프트캡(시세×1.10)에 걸려도 여전히 시세 초과
    over = v(median_price=10_000_000, min_sale_price=12_000_000, fail_count=0)
    exp = service.expected_for(over, BT)
    assert exp and exp >= over["median_price"], "전제 확인: 예상가가 시세 이상이어야 하는 사례"
    assert service.personal_use_saving(over, BT) is None


def test_cost_model_constants_present():
    """비용 모델이 조용히 사라지면 '소매보다 싸다'는 주장이 근거를 잃는다."""
    assert service.USE_TAX_RATE == 0.07
    assert service.USE_AUCTION_FEE > 0 and service.USE_RETAIL_FEE > 0
    assert service.USE_REPAIR_RESERVE > 0, "경매차는 성능점검·보증이 없어 정비 충당이 필요하다"
    # 경매 쪽 부대비가 소매보다 커야 정직하다(탁송·정비가 추가로 든다)
    assert service.USE_AUCTION_FEE + service.USE_REPAIR_RESERVE > service.USE_RETAIL_FEE


def test_past_sale_date_is_never_recommended():
    """매각기일이 지난 물건은 입찰할 수 없다.

    낙찰결과가 아직 안 붙어 '유찰 대기'로 남아 있는 지난 물건이 섞이면
    입찰 불가한 차를 권하게 된다(2026-09-12 실측: 140대 중 58대가 8월 기일이었다).
    """
    import datetime
    today = datetime.date(2026, 9, 12)
    assert service.is_personal_use_pick(v(sale_date="2026-08-20"), BT, today=today) is False
    assert service.is_personal_use_pick(v(sale_date="2026-09-30"), BT, today=today) is True
    assert service.is_personal_use_pick(v(sale_date=None), BT, today=today) is False
