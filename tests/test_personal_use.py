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


def _pred_block(n, err, fail_count, median):
    """pred_pool 한 덩어리 — 한 블록 안에서는 오차가 일정하다(층 평균을 손으로 검산하려고)."""
    return [{"err_pct": err, "maker": "현대", "model": "쏘나타",
             "fail_count": fail_count, "median_price": median, "actual": median}
            for _ in range(n)]


# ★ pred_pool 은 **층마다 다른 값**을 내야 한다 (PANEL-39).
#   예전 픽스처는 40행 전부 `median_price=20,000,000` · `fail_count=1` · 현대 쏘나타라
#   가격대·유찰횟수·제조사 **세 층이 전부 10.0** 이었다. 층값이 같으면 accuracy_for 가
#   어느 층을 고르든 결과가 같아서 **가격대 층 배선을 끊어도 테스트가 안 울린다.**
#   (그 함정은 test_mae_stratum_parity.py:18-22 가 이미 문서화해 둔 것이다.)
#   그래서 2×2 블록(유찰 0~1회/3회 이상 × 시세 1,500만/3,000만)으로 축을 갈라 둔다:
#
#     가격대 2,000만 이상   n=24  mae 10.0   ← 이 파일 픽스처(시세 4,000만)가 고르는 층
#     가격대 1,000~2,000만  n=16  mae  4.0
#     유찰 0~1회            n=20  mae  2.0
#     유찰 3회 이상         n=20  mae 13.2
#     제조사 국산           n=40  mae  7.6
#
#   ⚠ `2,000만 이상` 을 **10.0 에 맞춘 것은 의도**다. 고치기 전 accuracy_for 가 이 파일
#   물건들에 내주던 값이 10.0 이라, 그대로 둬야 이 BT 를 빌려 쓰는 5개 모듈
#   (test_terms · test_usepick_tiers · test_bid_state_nomarket · test_bucket_matches_bid_state ·
#   test_panel_r2_fixes)의 오차 게이트 경계가 움직이지 않는다. 가격대 배선을 끊으면
#   유찰 0~1회(2.0)로 떨어지고 "이득 83만 < 오차 316만" 이 뒤집힌다 — 그게 반증 장치다.
PRED_POOL = (_pred_block(12, 2.0, 1, 30_000_000) + _pred_block(12, 18.0, 3, 30_000_000)
             + _pred_block(8, 2.0, 1, 15_000_000) + _pred_block(8, 6.0, 3, 15_000_000))

# 층 → 기대 mae. 아래 자기 유효성 검사가 이 표와 대조한다(픽스처가 평평해지면 빨간불).
STRATA_EXPECTED = {("가격대", "2,000만 이상"): 10.0, ("가격대", "1,000~2,000만"): 4.0,
                   ("유찰횟수", "유찰 0~1회"): 2.0, ("유찰횟수", "유찰 3회 이상"): 13.2,
                   ("제조사", "국산"): 7.6}

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      # accuracy_for()가 층별 오차를 내려면 pred_pool이 필요하다. 없으면 추천 게이트가
      # "오차를 모르면 추천하지 않는다"로 막아 픽스처가 전부 빠진다(의도된 동작).
      "pred_pool": PRED_POOL,}


def v(**kw):
    # 절감액이 층 오차(≈10%)를 넘는 물건이어야 '실사용 추천'에 든다.
    # 최저가 2,800만이면 절감 87만 < 오차 316만이라 유의하지 않다(5회차 게이트).
    base = {"median_price": 40_000_000, "min_sale_price": 22_000_000, "fail_count": 1,
            "market_confidence_label": "높음", "accident_grade": "none", "judgment": "유찰 대기"}
    base.update(kw)
    return base


# ── ★ 픽스처 자기 유효성 검사 (PANEL-39) ────────────────────────────────
# 모범: tests/test_panel35_hero_tone_parity.py — 픽스처에 그 갈래가 **실재하는지**를
# 테스트가 스스로 검사한다. 픽스처를 고쳐 놓아도 다음 사람이 조용히 평평하게 만들면
# 아래 검사가 먼저 빨간불이 된다. 고친 뒤가 아니라 **고쳐진 상태를 지키는** 장치다.

def test_픽스처의_세_축이_서로_다른_오차를_낸다():
    """세 축이 같은 값이면 accuracy_for 가 어느 층을 골라도 결과가 같다 — 공허 통과."""
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(BT)}
    got = {k: rows[k]["mae"] for k in STRATA_EXPECTED if k in rows}
    assert got == STRATA_EXPECTED, f"층값이 표와 다르다 — 픽스처나 층 경계가 바뀌었다: {got}"
    # 이 파일 물건(국산·유찰 1회·시세 4,000만)이 닿는 세 축이 모두 달라야 한다
    axes = {g: rows[(g, lab)]["mae"] for g, lab in
            [("가격대", "2,000만 이상"), ("유찰횟수", "유찰 0~1회"), ("제조사", "국산")]}
    assert len(set(axes.values())) == 3, (
        f"두 축 이상이 같은 값이다 — 배선을 끊어도 테스트가 안 울린다(PANEL-39): {axes}")


def test_가격대_층이_이_픽스처의_오차를_실제로_좌우한다():
    """★ 반증 장치. `accuracy_for` 후보에서 가격대를 빼면 10.0 → 2.0 으로 떨어지고,
    그 순간 이 BT 를 쓰는 오차 게이트(test_terms·test_usepick_tiers)가 함께 깨진다."""
    got = service.accuracy_for(v(), BT)
    assert got and got["group"] == "가격대" and got["mae"] == 10.0, (
        f"가격대 층이 판정을 좌우하지 않는다 — 이 픽스처로는 PANEL-30 배선을 감시 못 한다: {got}")
    dom = service.accuracy_for(v(maker="현대", model="쏘나타"), BT)
    assert dom["group"] == "가격대" and dom["mae"] == 10.0, dom


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
    assert service.USE_REPAIR_BASE > 0, "경매차는 성능점검·보증이 없어 정비 충당이 필요하다"
    # 경매 쪽 부대비가 소매보다 커야 정직하다(탁송·정비가 추가로 든다)
    assert service.USE_AUCTION_FEE + service.USE_REPAIR_BASE > service.USE_RETAIL_FEE


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


# ── 2회차 패널(2026-09-12) P0 회귀 ─────────────────────────────────────
# 중고차 전문가: "감정 당시 시동 불능"인 마세라티가 '−34%·760만원 절감'으로 1위 추천됐다.
# 경매 전문가: 시세/감정가 3.24배인 그랜저가 '소매보다 −1845만'으로 1위 추천됐다.
# 둘 다 절감액 정렬 때문에 **오차가 클수록 맨 위로** 올라온 결과였다.

def test_not_runnable_is_never_recommended():
    """시동·운행 불가 물건은 수리비가 열려 있어 '소매보다 싸다'고 말할 수 없다."""
    assert service.personal_use_saving(v(runnable="no"), BT) is None
    assert service.is_personal_use_pick(v(runnable="no"), BT) is False
    # 확인되지 않은 경우(unknown)까지 배제하면 대부분이 사라진다 — 배제는 'no'일 때만.
    assert service.personal_use_saving(v(runnable="unknown"), BT) is not None


def test_appraisal_mismatch_is_never_recommended():
    """시세가 감정가와 크게 어긋나면 오매칭 의심 — 절감액 자체를 신뢰할 수 없다."""
    # 시세/감정가 = 3.24 (실측 사례: 2016 그랜저 13만km, 감정 850만 / 시세 2,750만)
    assert service.personal_use_saving(v(median_price=27_500_000, appraisal_value=8_500_000,
                                         min_sale_price=8_500_000), BT) is None
    # 정합 대역 안이면 정상 추천된다
    assert service.personal_use_saving(v(appraisal_value=38_000_000), BT) is not None


def test_repair_reserve_reflects_condition_not_a_flat_constant():
    """정비 충당이 상수면 상태가 나쁜 차일수록 절감액이 과대평가된다."""
    good = service.use_repair_reserve(v(condition_level="unknown", photo_count=5))
    poor = service.use_repair_reserve(v(condition_level="poor", photo_count=5))
    expired = service.use_repair_reserve(v(condition_level="unknown", photo_count=5,
                                           inspection_to="2023-08-28"))
    assert poor > good and expired > good, "상태·검사 만료가 충당금에 반영돼야 한다"
    # config.yaml의 condition_costs를 그대로 쓴다(코드에 숫자를 다시 박지 않는다)
    costs = service.load_config()["condition_costs"]
    assert poor - good == costs["poor"]
    assert expired - good == costs["inspection_expired"]


def test_unverified_accident_history_is_assumed_accident():
    """근거 없는 '무사고'로 절감액을 부풀리지 않는다.

    실측(2026-09-12): 추천 82건 중 **근거 있는 무사고는 0건**이었는데도 계산은 사고감가 0을
    적용하고 있었다. 화면은 '이력 미확인'이라 적으면서 계산만 무사고로 치는 모순이었다."""
    rate_unknown, assumed = service.use_accident_rate(v(accident_grade="none"))
    assert assumed is True and rate_unknown > 0
    # 보험이력 등 근거가 있으면 가정하지 않는다
    rate_known, assumed2 = service.use_accident_rate(
        v(accident_grade="none", insurance_history={"내차피해": 0}))
    assert assumed2 is False and rate_known == 0
    # 가정을 적용하면 절감액은 반드시 더 보수적(작거나 없음)이다
    assumed_saving = service.personal_use_saving(v(), BT)
    known_saving = service.personal_use_saving(v(insurance_history={"내차피해": 0}), BT)
    assert known_saving > assumed_saving


def test_detail_exposes_the_assumption_used():
    """화면이 '어떤 가정으로 나온 숫자인지' 말할 수 있어야 한다."""
    d = service.personal_use_detail(v(), BT)
    assert d and d["accident_assumed"] is True and d["saving"] > 0
    assert d["comp"] < v()["median_price"], "비교 대상 소매가에 사고감가가 반영돼야 한다"
