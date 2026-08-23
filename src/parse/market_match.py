"""동급 매물 매칭·시세 통계 (설계서 TASK-05, A.4-5 / A.5 시세요약).

동급 기준: 모델 동일, 연식 ±1년, 주행거리 ±30%.
통계: 표본수, 평균가, 중앙값, 최저가 (원 단위).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MarketStats:
    platform: str
    sample_count: int
    mean_price: Optional[int]
    median_price: Optional[int]
    min_price: Optional[int]
    year_range: tuple
    mileage_range: tuple
    match_label: str = ""   # 어떤 기준으로 표본을 잡았는지 (동급/확장/연식±3)

    def to_dict(self) -> dict:
        return asdict(self)


def filter_comparable(listings: list[dict], form_year: Optional[int],
                      mileage_km: Optional[int], year_tol: int = 1,
                      mileage_tol: float = 0.30) -> list[dict]:
    """연식 ±year_tol, 주행거리 ±mileage_tol 범위의 매물만 남긴다."""
    out = []
    for it in listings:
        if it.get("price_won") is None:
            continue
        # 연식 필터
        if form_year is not None and it.get("form_year") is not None:
            if abs(it["form_year"] - form_year) > year_tol:
                continue
        # 주행거리 필터
        if mileage_km and it.get("mileage_km") is not None:
            lo, hi = mileage_km * (1 - mileage_tol), mileage_km * (1 + mileage_tol)
            if not (lo <= it["mileage_km"] <= hi):
                continue
        out.append(it)
    return out


def compute_stats(comparables: list[dict], platform: str = "encar",
                  form_year: Optional[int] = None,
                  mileage_km: Optional[int] = None,
                  year_tol: int = 1, mileage_tol: float = 0.30) -> MarketStats:
    prices = [c["price_won"] for c in comparables if c.get("price_won") is not None]
    yr = (None, None)
    if form_year is not None:
        yr = (form_year - year_tol, form_year + year_tol)
    ml = (None, None)
    if mileage_km:
        ml = (int(mileage_km * (1 - mileage_tol)), int(mileage_km * (1 + mileage_tol)))
    if not prices:
        return MarketStats(platform, 0, None, None, None, yr, ml)
    return MarketStats(
        platform=platform,
        sample_count=len(prices),
        mean_price=int(statistics.mean(prices)),
        median_price=int(statistics.median(prices)),
        min_price=min(prices),
        year_range=yr,
        mileage_range=ml,
    )


def summarize(listings: list[dict], form_year: Optional[int],
              mileage_km: Optional[int], platform: str = "encar",
              year_tol: int = 1, mileage_tol: float = 0.30,
              fuel: Optional[str] = None) -> MarketStats:
    """매칭 + 통계 (정교화판).

    ① **연료 일치**(디젤/가솔린 등) ② **동일 세대**(물건 연식의 지배적 엔카 Model만
    — 예: 카니발 3세대 '더 뉴 카니발'과 2021 '카니발 4세대'가 섞여 중앙값이 부풀지 않게)
    ③ 동급(연식±1·주행±30%) → 확장 → 연식±3 단계 완화.
    """
    from collections import Counter

    pool = [l for l in listings if l.get("price_won") is not None]
    note = ""
    # ① 연료 일치
    if fuel:
        fp = [l for l in pool if l.get("fuel") == fuel]
        if len(fp) >= 3:          # 표본이 충분할 때만 연료로 좁힘
            pool = fp
            note += f"·{fuel}"
    # ② 동일 세대 (물건 연식과 정확히 같은 연식 매물의 지배적 Model)
    if form_year is not None:
        exact = [l.get("model") for l in pool if l.get("form_year") == form_year and l.get("model")]
        if exact:
            dominant = Counter(exact).most_common(1)[0][0]
            same_gen = [l for l in pool if l.get("model") == dominant]
            if len(same_gen) >= 3:
                pool = same_gen
                note += "·동세대"

    tiers = [
        (f"동급 (연식±{year_tol}·주행±{int(mileage_tol * 100)}%)", year_tol, mileage_tol),
        ("확장 (연식±2·주행±50%)", 2, 0.50),
        ("연식±3 (주행 무관)", 3, None),
    ]
    for label, ytol, mtol in tiers:
        comps = filter_comparable(
            pool, form_year,
            mileage_km if mtol is not None else None,
            year_tol=ytol, mileage_tol=mtol if mtol is not None else 9.99)
        if comps:
            st = compute_stats(comps, platform, form_year, mileage_km,
                               ytol, mtol if mtol is not None else 9.99)
            st.match_label = label + note
            return st
    st = compute_stats([], platform, form_year, mileage_km, year_tol, mileage_tol)
    st.match_label = "동급 표본 없음"
    return st
