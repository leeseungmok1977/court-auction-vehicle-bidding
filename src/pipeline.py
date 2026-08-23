"""배치 산정 파이프라인 (검증용, 소량·저속).

경매 자동차 목록 → 모델매핑 → 상세 → 엔카 동급 시세 → 입찰가 산정 → 결과표.

설계서 C.4-1(소량 원칙) 준수: 매핑된 max_items 건만 처리, 전체 스캔은 scan_limit 상한.
실행: python -m src.pipeline
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from .collect.courtauction_list import new_session, warmup, fetch_list_page
from .collect.courtauction_detail import fetch_detail, save_item_folder
from .collect import encar
from .parse.list_parser import parse_list_response
from .parse.detail_parser import parse_detail
from .parse.market_match import summarize
from .bidcalc.calculator import BidInput, calculate


def load_config(path: str = "config.yaml") -> dict:
    return yaml.safe_load(open(path, encoding="utf-8"))


def resolve_mapping(car_nm: str, config: dict):
    """경매 차명 → 엔카 (car_type, manufacturer, model_group). 미매핑 시 (key, None)."""
    for key, val in (config.get("model_mapping") or {}).items():
        if key in (car_nm or ""):
            return key, val
    return None, None


def run(max_items: int = 3, scan_limit: int = 15, repair_cost: int = 500_000,
        config: Optional[dict] = None) -> list[dict]:
    config = config or load_config()
    year_tol = config.get("year_tol", 1)
    mileage_tol = config.get("mileage_tol", 0.30)

    cs = new_session()
    warmup(cs)
    list_resp = fetch_list_page(cs, page_no=1, page_size=40).json()
    raw_rows = list_resp["data"]["dlt_srchResult"]
    items = parse_list_response(list_resp)

    es = encar.new_session()
    results: list[dict] = []
    processed = 0

    for idx, (raw, item) in enumerate(zip(raw_rows, items)):
        if processed >= max_items or idx >= scan_limit:
            break
        key, mp = resolve_mapping(item.model, config)
        if not mp:
            results.append({"case_no": item.case_no, "model": item.model,
                            "status": "미매핑(모델매핑 필요)"})
            continue

        # 상세
        dresp = fetch_detail(cs, raw["saNo"], raw["boCd"], raw.get("maemulSer", "1")).json()
        detail = parse_detail(dresp, config)
        save_item_folder(dresp, item.folder_key, config)

        # 엔카 동급 시세
        try:
            res = encar.search(es, manufacturer=mp["manufacturer"],
                               model_group=mp["model_group"], car_type=mp.get("car_type", "Y"),
                               limit=100)
            listings = encar.normalize(res["results"])
            stats = summarize(listings, form_year=item.year, mileage_km=detail.mileage_km,
                              platform="encar", year_tol=year_tol, mileage_tol=mileage_tol)
        except Exception as e:  # noqa: BLE001
            results.append({"case_no": item.case_no, "model": item.model,
                            "status": f"엔카 오류: {e}"})
            processed += 1
            continue

        # 산정
        bi = BidInput(median_price=stats.median_price or 0,
                      min_sale_price=item.min_sale_price or 0,
                      sample_count=stats.sample_count, platform="encar",
                      accident_grade=detail.accident_grade, repair_cost=repair_cost,
                      appraisal_text=detail.appraisal_text)
        bid = calculate(bi, config)

        results.append({
            "case_no": item.case_no, "court": item.court, "model": item.model,
            "year": item.year, "mileage_km": detail.mileage_km,
            "min_sale_price": item.min_sale_price, "appraisal_value": detail.appraisal_value,
            "fail_count": detail.fail_count, "accident_grade": detail.accident_grade,
            "encar_total": res["count"], "sample_count": stats.sample_count,
            "median_price": stats.median_price, "upper_bid": bid.upper_bid,
            "judgment": bid.judgment, "status": "완료",
        })
        processed += 1

    return results


def write_report(results: list[dict], path: str = "docs/산정결과표.md") -> None:
    def won(v):
        return f"{v:,}" if isinstance(v, (int, float)) else "—"

    lines = [
        "# 배치 산정 결과표",
        "",
        f"- 생성일: {date.today().isoformat()}",
        f"- 처리 건수: {sum(1 for r in results if r.get('status') == '완료')} 완료 / {len(results)} 스캔",
        "- 출처: 대법원 법원경매정보 + SK엔카",
        "",
        "| 사건번호 | 차량 | 연식 | 주행(km) | 최저매각가 | 엔카중앙값 | 표본 | 상한가 | 판정 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.get("status") != "완료":
            lines.append(f"| {r['case_no']} | {r['model']} | — | — | — | — | — | — | {r['status']} |")
            continue
        lines.append(
            f"| {r['case_no']} | {r['model']} | {r['year']} | {won(r['mileage_km'])} | "
            f"{won(r['min_sale_price'])} | {won(r['median_price'])} | {r['sample_count']} | "
            f"{won(r['upper_bid'])} | **{r['judgment']}** |")
    lines += ["", "> 금액 단위 원. 상한가<최저매각가면 '유찰 대기'. 파라미터는 config.yaml."]
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = run(max_items=3, scan_limit=40)
    write_report(results)
    done = [r for r in results if r.get("status") == "완료"]
    print(f"완료 {len(done)}건 / 스캔 {len(results)}건 → docs/산정결과표.md")
    for r in done:
        print(f"  {r['case_no']} {r['model']}: {r['judgment']} (상한 {r['upper_bid']:,})")


if __name__ == "__main__":
    main()
