"""엔드투엔드 산정 리포트 생성 (설계서 TASK-05 DoD: 샘플리포트).

법원경매 물건(상세) + 엔카 동급 시세 → 입찰가 산정 → 마크다운 리포트.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .bidcalc.calculator import BidInput, BidResult, calculate
from .parse.detail_parser import DetailInfo
from .parse.market_match import MarketStats


def build_report(case_no: str, court: str, model: str, detail: DetailInfo,
                 stats: MarketStats, bid: BidResult, repair_cost: int,
                 encar_total: Optional[int] = None) -> str:
    def won(v):
        return f"{v:,}원" if isinstance(v, (int, float)) else "—"

    lines = [
        f"# 입찰가 산정 샘플 리포트 — {case_no}",
        "",
        f"- 생성일: {date.today().isoformat()}",
        f"- 법원: {court} · 물건: {model}",
        "- 데이터 출처: 대법원 법원경매정보(물건 상세) + SK엔카(동급 시세)",
        "",
        "## 1. 물건 정보 (법원경매 상세)",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 사건번호 | {case_no} |",
        f"| 차량 | {detail.maker} {model} ({detail.year}년식) |",
        f"| 주행거리 | {detail.mileage_km:,} km |" if detail.mileage_km else "| 주행거리 | — |",
        f"| 배기량 | {detail.displacement_cc} cc |" if detail.displacement_cc else "| 배기량 | — |",
        f"| 감정가 | {won(detail.appraisal_value)} |",
        f"| 최저매각가 | {won(bid.lower_bound)} |",
        f"| 유찰횟수 | {detail.fail_count} 회 |",
        f"| 매각기일 | {detail.sale_date} |",
        f"| 사고판정 | **{detail.accident_grade}** (근거: {', '.join(detail.accident_hits) or '없음'}) |",
        f"| 보험사고이력 | {detail.insurance_history} |",
        "",
        "## 2. 동급 시세 (SK엔카)",
        "",
        f"- 매칭 기준: 모델={model}, 연식 {stats.year_range[0]}~{stats.year_range[1]}, "
        f"주행거리 {stats.mileage_range[0]:,}~{stats.mileage_range[1]:,} km"
        if stats.mileage_range[0] else f"- 매칭 기준: 모델={model}, 연식 {stats.year_range}",
        f"- 엔카 전체 동모델 매물: {encar_total:,} 대" if encar_total else "",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 표본수(동급) | {stats.sample_count} 건 |",
        f"| 평균가 | {won(stats.mean_price)} |",
        f"| 중앙값 | {won(stats.median_price)} |",
        f"| 최저가 | {won(stats.min_price)} |",
        "",
        "## 3. 입찰가 산정 (설계서 A.6)",
        "",
        f"- 예상 수리비(입력 예시): {won(repair_cost)}",
        "",
        "| 항목 | 값 |",
        "|---|---|",
    ]
    for k, v in bid.breakdown.items():
        vv = won(v) if isinstance(v, int) and abs(v) >= 1000 else v
        lines.append(f"| {k} | {vv} |")
    lines += [
        "",
        "## 4. 결론",
        "",
        f"- **자동 판정: {bid.judgment}**",
        f"- 권장 입찰 범위: **{won(bid.lower_bound)} ~ {won(bid.upper_bound)}**",
        f"  (하한=현재 최저매각가, 상한=산정 상한가)",
        "",
        "> 파라미터(마진·감가·리스크 등)는 config.yaml에서 조정 가능. "
        "수리비는 실제 점검 후 입력 권장.",
    ]
    return "\n".join(l for l in lines if l is not None)
