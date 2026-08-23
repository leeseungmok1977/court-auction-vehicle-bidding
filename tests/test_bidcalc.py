"""입찰가 산정 로직 단위 테스트 (설계서 TASK-01 DoD).

케이스:
  ① 정상 산정
  ② 상한가 < 최저가 → 유찰 대기
  ③ 표본 < 5 → 시세 신뢰도 낮음
  ④ 침수 키워드 → 입찰 보류
  ⑤ 경계값 (감가 0%, 유찰 0회, 표본 정확히 5건)
"""

import pytest

from src.bidcalc.calculator import (
    BidInput,
    Judgment,
    calculate,
    load_config,
)


@pytest.fixture
def cfg():
    """테스트 고정 파라미터 (config.yaml 편집과 무관하게 로직 검증)."""
    return {
        "platform_weight": {"encar": 1.00, "kcar": 0.95},
        "accident_depreciation_rate": {
            "none": 0.00,
            "minor": 0.05,
            "accident": 0.15,
            "flood": 1.00,
        },
        "risk_premium_rate": 0.07,
        "acquisition_tax_rate": 0.07,
        "margin_rate": 0.12,
        "fixed_costs": {"transfer_fee": 300_000, "delivery_fee": 200_000},
        "min_sample_count": 5,
        "flood_keywords": ["침수", "전손"],
        "accident_keywords": ["사고", "판금", "교환", "부식"],
    }


# ① 정상 산정 --------------------------------------------------------------
def test_normal_calculation(cfg):
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=10_000_000,
        sample_count=8,
        platform="encar",
        accident_grade="none",
        repair_cost=500_000,
    )
    r = calculate(inp, cfg)

    # base=20,000,000
    # 차감: 수리 500,000 + 사고 0 + 리스크 1,400,000 + 취득세 1,400,000
    #       + 고정 500,000 + 마진 2,400,000 = 6,200,000
    # 상한가 = 13,800,000
    assert r.base_price == 20_000_000
    assert r.upper_bid == 13_800_000
    assert r.lower_bound == 10_000_000
    assert r.upper_bound == 13_800_000
    assert r.judgment == Judgment.OK.value


def test_platform_weight_kcar(cfg):
    """케이카 가중 0.95 적용 확인."""
    inp = BidInput(median_price=20_000_000, min_sale_price=5_000_000,
                   sample_count=6, platform="kcar")
    r = calculate(inp, cfg)
    assert r.base_price == 19_000_000  # 20,000,000 × 0.95


# ② 상한가 < 최저가 → 유찰 대기 --------------------------------------------
def test_upper_below_min_waits(cfg):
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=15_000_000,  # 상한가(13,800,000)보다 높음
        sample_count=8,
        platform="encar",
        accident_grade="none",
        repair_cost=500_000,
    )
    r = calculate(inp, cfg)
    assert r.upper_bid < inp.min_sale_price
    assert r.judgment == Judgment.WAIT_FAIL.value


# ③ 표본 < 5 → 시세 신뢰도 낮음 --------------------------------------------
def test_low_sample_low_confidence(cfg):
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=10_000_000,
        sample_count=3,  # 5건 미만
        platform="encar",
    )
    r = calculate(inp, cfg)
    assert r.judgment == Judgment.LOW_CONFIDENCE.value


# ④ 침수 키워드 → 입찰 보류 ------------------------------------------------
def test_flood_keyword_holds(cfg):
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=10_000_000,
        sample_count=8,  # 표본 충분해도 침수가 우선
        platform="encar",
        appraisal_text="차량 하부 침수 흔적 및 부식 확인됨",
    )
    r = calculate(inp, cfg)
    assert r.judgment == Judgment.HOLD_FLOOD.value


def test_flood_grade_holds(cfg):
    """등급이 flood 로 지정된 경우도 보류."""
    inp = BidInput(median_price=20_000_000, min_sale_price=5_000_000,
                   sample_count=10, accident_grade="flood")
    r = calculate(inp, cfg)
    assert r.judgment == Judgment.HOLD_FLOOD.value


# ⑤ 경계값 (감가 0%, 유찰 0회, 표본 정확히 5건) ----------------------------
def test_boundary_values(cfg):
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=20_000_000,  # 유찰 0회 → 최저가 = 감정가 수준
        sample_count=5,             # 정확히 5건 → 신뢰도 낮음 아님
        platform="encar",
        accident_grade="none",      # 감가 0%
        repair_cost=0,
    )
    r = calculate(inp, cfg)
    # 감가 0 확인
    assert r.breakdown["사고감가"] == 0
    # 표본 5건은 min_sample_count(5) 미만이 아님 → 신뢰도 낮음 아님
    assert r.judgment != Judgment.LOW_CONFIDENCE.value
    # 상한가 13,800,000 < 최저가 20,000,000 → 유찰 대기
    assert r.judgment == Judgment.WAIT_FAIL.value


# config.yaml 실제 파일 로드 및 필수 키 검증 --------------------------------
def test_config_file_loads_with_required_keys():
    config = load_config()
    required = [
        "platform_weight",
        "accident_depreciation_rate",
        "risk_premium_rate",
        "acquisition_tax_rate",
        "margin_rate",
        "fixed_costs",
        "min_sample_count",
        "flood_keywords",
    ]
    for key in required:
        assert key in config, f"config.yaml 에 '{key}' 누락"
    # 실제 config 로도 정상 산정되는지 스모크 테스트
    inp = BidInput(median_price=15_000_000, min_sale_price=8_000_000, sample_count=7)
    r = calculate(inp, config)
    assert r.upper_bid < r.base_price
