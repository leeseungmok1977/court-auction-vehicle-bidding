"""입찰가 산정 로직 (설계서 A.6).

기준시세     = 시세요약.중앙값 × 플랫폼 가중 (엔카 1.0 / 케이카 0.95)
입찰 상한가  = 기준시세
              − 예상 수리비(사용자 입력)
              − 사고 감가(단순수리 5% / 사고 10~20%)
              − 리스크 프리미엄(기준시세의 5~10%)
              − 취득 부대비용(취득세 7% + 이전·탁송 고정비)
              − 목표 절감/마진(10~15%)
권장 범위    = [현재 최저매각가, 입찰 상한가]

자동 판정:
  침수·전손 키워드 → "입찰 보류"
  표본 < 5건        → "시세 신뢰도 낮음, 수동 검토"
  상한가 < 최저매각가 → "유찰 대기"

모든 파라미터는 config.yaml에서 읽어 코드 수정 없이 조정한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

# config.yaml 위치: 프로젝트 루트 (src/bidcalc/calculator.py -> parents[2])
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class Judgment(str, Enum):
    """자동 판정 결과 (설계서 A.6)."""

    OK = "입찰 검토 가능"
    HOLD_FLOOD = "입찰 보류"          # 침수·전손
    LOW_CONFIDENCE = "시세 신뢰도 낮음, 수동 검토"  # 표본 부족
    WAIT_FAIL = "유찰 대기"            # 상한가 < 최저매각가


class AccidentGrade(str, Enum):
    """사고 판정 등급 (config.accident_depreciation_rate 키와 대응)."""

    NONE = "none"        # 무사고
    MINOR = "minor"      # 단순수리
    ACCIDENT = "accident"  # 사고
    FLOOD = "flood"      # 침수의심


@dataclass
class BidInput:
    """산정 입력값."""

    median_price: float          # 시세요약 중앙값 (원)
    min_sale_price: float        # 현재 최저매각가 (원)
    sample_count: int            # 시세 표본수
    platform: str = "encar"      # encar | kcar
    accident_grade: str = "none"  # none | minor | accident | flood
    repair_cost: float = 0.0     # 예상 수리비 (사용자 입력, 원)
    appraisal_text: str = ""     # 감정평가서 텍스트 (침수 키워드 판정용)
    photo_count: Optional[int] = None  # 차량 사진 수(None=미상 → 감가 안 함, 0=사진없음 → 감가)


@dataclass
class BidResult:
    """산정 결과. breakdown 은 입찰검토.산정근거(JSON) 열에 그대로 저장 가능."""

    base_price: float            # 기준시세
    upper_bid: float             # 입찰 상한가
    lower_bound: float           # 권장 범위 하한 (= 현재 최저매각가)
    upper_bound: float           # 권장 범위 상한 (= 입찰 상한가)
    judgment: str                # Judgment 값
    breakdown: dict = field(default_factory=dict)  # 항목별 차감 내역

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def load_config(path: Optional[str | Path] = None) -> dict:
    """config.yaml 로드. path 미지정 시 프로젝트 루트의 config.yaml 사용."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _is_flood(inp: BidInput, config: dict) -> bool:
    """침수·전손 판정: 등급이 flood 이거나 감정평가서 자유서술에 키워드 존재.

    보험사고이력 정형구('전손 보험사고 : 0건' 등)는 제거 후 스캔한다 — '0건'을
    침수로 오판해 무사고 차량이 '입찰 보류'로 표기되는 모순을 막는다."""
    if inp.accident_grade == AccidentGrade.FLOOD.value:
        return True
    keywords = config.get("flood_keywords", [])
    from ..parse.detail_parser import _strip_report
    text = _strip_report(inp.appraisal_text or "")
    return any(kw in text for kw in keywords)


def calculate(inp: BidInput, config: dict) -> BidResult:
    """A.6 산식으로 입찰 상한가와 권장 범위, 자동 판정을 산출한다."""
    weight = config["platform_weight"].get(inp.platform, 1.0)
    base_price = inp.median_price * weight

    flood = _is_flood(inp, config)

    # 사고 감가율: 침수면 flood 율, 아니면 등급별 율
    rate_table = config["accident_depreciation_rate"]
    acc_rate = rate_table.get("flood", 1.0) if flood else rate_table.get(inp.accident_grade, 0.0)

    accident_dep = base_price * acc_rate
    risk_premium = base_price * config["risk_premium_rate"]
    acquisition_tax = base_price * config["acquisition_tax_rate"]
    fixed = config["fixed_costs"]["transfer_fee"] + config["fixed_costs"]["delivery_fee"]
    margin = base_price * config["margin_rate"]

    # 감정 요항 기반 상태·검사 추가 정비/비용(외관 손상·관리불량·검사경과·시동불가).
    # 요항 텍스트가 없거나 config.condition_costs 미설정이면 0(기존 동작 유지).
    from ..parse.appraisal import condition_adjustment
    cond = condition_adjustment(inp.appraisal_text or "", config)
    condition_cost = cond.get("add", 0)
    cond_flags = list(cond.get("flags", []))

    # 차량 사진 없음 → 실물 확인 불가 리스크 감가(사진수 0으로 명시된 경우만; None=미상은 제외)
    no_photo_cost = 0
    if inp.photo_count == 0:
        no_photo_cost = int((config.get("condition_costs", {}) or {}).get("no_photos", 0))
        if no_photo_cost:
            cond_flags.append("차량 사진 없음")

    upper_bid = (
        base_price
        - inp.repair_cost
        - accident_dep
        - risk_premium
        - acquisition_tax
        - fixed
        - margin
        - condition_cost
        - no_photo_cost
    )

    # 자동 판정 (우선순위: 침수 > 표본부족 > 유찰대기 > 가능)
    if flood:
        judgment = Judgment.HOLD_FLOOD
    elif inp.sample_count < config["min_sample_count"]:
        judgment = Judgment.LOW_CONFIDENCE
    elif upper_bid < inp.min_sale_price:
        judgment = Judgment.WAIT_FAIL
    else:
        judgment = Judgment.OK

    breakdown = {
        "기준시세": round(base_price),
        "플랫폼": inp.platform,
        "플랫폼가중": weight,
        "예상수리비": round(inp.repair_cost),
        "사고등급": AccidentGrade.FLOOD.value if flood else inp.accident_grade,
        "사고감가율": acc_rate,
        "사고감가": round(accident_dep),
        "리스크프리미엄": round(risk_premium),
        "취득세": round(acquisition_tax),
        "고정부대비": fixed,
        "마진": round(margin),
        "상태정비추가": round(condition_cost + no_photo_cost),
        "상태사유": cond_flags,
        "표본수": inp.sample_count,
        "현재최저매각가": round(inp.min_sale_price),
    }

    return BidResult(
        base_price=round(base_price),
        upper_bid=round(upper_bid),
        lower_bound=round(inp.min_sale_price),
        upper_bound=round(upper_bid),
        judgment=judgment.value,
        breakdown=breakdown,
    )


def _demo() -> None:
    """단독 실행 예시: python -m src.bidcalc.calculator"""
    config = load_config()
    inp = BidInput(
        median_price=20_000_000,
        min_sale_price=10_000_000,
        sample_count=8,
        platform="encar",
        accident_grade="minor",
        repair_cost=500_000,
        appraisal_text="외관 양호, 단순 판금 이력 있음",
    )
    result = calculate(inp, config)
    print("=== 입찰가 산정 예시 ===")
    print(result.to_json())


if __name__ == "__main__":
    _demo()
