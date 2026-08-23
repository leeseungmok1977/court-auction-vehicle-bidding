"""동급 매물 매칭·시세 통계 (설계서 TASK-05, A.4-5 / A.5 시세요약).

동급 기준: 모델 동일, 연식 ±1년, 주행거리 ±30%.
통계: 표본수, 평균가, 중앙값, 최저가 (원 단위).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, asdict, field
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
    outlier_count: int = 0  # IQR로 제거한 이상치 표본 수
    cv: Optional[float] = None       # 변동계수(표준편차/평균) — 가격 흩어짐 정도
    confidence: int = 0              # 시세 신뢰도 점수 0~100 (모든 가드 적용된 최종값)
    confidence_label: str = ""       # 높음 / 보통 / 낮음
    market_vs_appraisal: Optional[float] = None  # 시세중앙값/감정가 (가드 소스)
    comps: list = field(default_factory=list)  # 중앙값 산출에 쓴 개별 동급 매물(감사용)
    cross_source_status: str = "single"          # single / agree / diverge (케이카 교차검증)
    cross_source_rel: Optional[float] = None     # 두 소스 상대편차 (0.05 = 5%)
    kcar_median: Optional[int] = None            # 케이카 동급 중앙값(교차검증 소스)
    kcar_sample: int = 0                          # 케이카 표본수
    tier_level: Optional[int] = None             # 채택 tier(0=동급·1=확장·2=연식±3) — 소스간 tier 정합 비교용

    def to_dict(self) -> dict:
        return asdict(self)


def _confidence_label(score: int) -> str:
    if score >= 70:
        return "높음"
    if score >= 45:
        return "보통"
    return "낮음"


def appraisal_guard(median_price: Optional[int],
                    appraisal_value: Optional[int],
                    config: Optional[dict] = None) -> tuple:
    """감정가(독립적 전문가 추정) 대비 시세 괴리로 신뢰도 상한을 건다.

    표본이 많고 촘촘해도(=내부 일관성 높음) 엔카가 **다른 트림·세대**를 매칭하면
    시세가 감정가와 크게 어긋난다(예: 마이바흐 S580을 일반 S클래스로 매칭).
    정상 대역은 시세/감정가 ≈ 0.7~1.4(실측 중앙값 0.93). 벗어나면 신뢰도를 낮춘다.
    임계값은 config.appraisal_guard로 외부화(기본값은 실측 기반).

    반환: (신뢰도 상한 or None, 사유 note, 비율 ratio or None)
    """
    if not median_price or not appraisal_value:
        return None, "", None
    g = (config or {}).get("appraisal_guard", {}) if config else {}
    strong_low = g.get("strong_low", 0.50); strong_high = g.get("strong_high", 1.80)
    mild_low = g.get("mild_low", 0.65); mild_high = g.get("mild_high", 1.28)
    cap_strong = g.get("cap_strong", 38); cap_mild = g.get("cap_mild", 60)
    ratio = round(median_price / appraisal_value, 2)
    if ratio < strong_low or ratio > strong_high:
        return cap_strong, "감정가 대비 괴리 큼 — 트림·사고 확인", ratio
    if ratio < mild_low or ratio > mild_high:
        return cap_mild, "감정가 대비 편차 있음", ratio
    return None, "", ratio


def cross_source_check(median_a: Optional[int], median_b: Optional[int],
                       tol: float = 0.10) -> tuple:
    """두 독립 시세 소스(엔카·케이카)의 중앙값 교차검증.

    ±tol 이내면 일치(신뢰 가점), 크게 벌어지면 불일치(상한/경고). 한쪽이 없으면
    ('single', None, '단일 소스')를 반환해 교차검증 미수행을 정직하게 표기.
    반환: (상태 'agree'|'diverge'|'single', 상대편차 or None, note)
    """
    if not median_a or not median_b:
        return "single", None, "단일 소스(교차검증 미수행)"
    rel = abs(median_a - median_b) / min(median_a, median_b)
    if rel <= tol:
        return "agree", round(rel, 3), f"2소스 일치(±{int(rel*100)}%)"
    return "diverge", round(rel, 3), f"2소스 불일치(±{int(rel*100)}%) — 확인 필요"


def appraisal_penalty(median_price: Optional[int], appraisal_value: Optional[int],
                      config: Optional[dict] = None) -> int:
    """정상 대역 안이라도 감정가와 벌어질수록 신뢰도를 연속 감점(정확도 반영).

    신뢰도가 '정밀도(표본·분산)'만 보고 '정확도(감정가 정합)'를 놓치는 문제를 보정한다.
    |ln(시세/감정가)|에 비례 — 감정가와 같으면 0, 벌어질수록 증가(상한 soft_max)."""
    if not median_price or not appraisal_value:
        return 0
    g = (config or {}).get("appraisal_guard", {}) or {}
    soft_max = g.get("soft_max", 30)
    low_factor = g.get("soft_low_factor", 0.35)
    ratio = median_price / appraisal_value
    dev = abs(math.log(ratio))
    pen = dev * 55
    if ratio < 1:              # 시세<감정가 = 흔함(감정가 고평가) → 감점 완화
        pen *= low_factor
    return min(soft_max, round(pen))


def trim_outliers(prices: list[int]) -> tuple[list[int], int]:
    """IQR(사분위 범위) 기반 이상치 제거.

    사고·침수차, 허위 저가 미끼, 특장/개조 고가 매물이 평균·중앙값을 왜곡한다.
    표본 5건 이상일 때 [Q1-1.5·IQR, Q3+1.5·IQR] 밖 매물을 버린다.
    반환: (남은 가격, 제거 건수).
    """
    if len(prices) < 5:
        return prices, 0
    s = sorted(prices)
    try:
        # inclusive: 소표본(n=5)에서도 단일 극단치를 잡아냄(기본 exclusive는 펜스가 과도하게 넓음)
        qs = statistics.quantiles(s, n=4, method="inclusive")
        q1, q3 = qs[0], qs[2]
    except statistics.StatisticsError:
        return prices, 0
    iqr = q3 - q1
    if iqr <= 0:
        return prices, 0
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [p for p in prices if lo <= p <= hi]
    if len(kept) < 3:            # 너무 많이 잘리면 원본 유지 (표본 보호)
        return prices, 0
    return kept, len(prices) - len(kept)


def filter_comparable(listings: list[dict], form_year: Optional[int],
                      mileage_km: Optional[int], year_tol: int = 1,
                      mileage_tol: float = 0.30) -> list[dict]:
    """연식 ±year_tol, 주행거리 ±mileage_tol 범위의 매물만 남긴다."""
    out = []
    for it in listings:
        if it.get("price_won") is None:
            continue
        # 연식 필터 — 결측 매물은 동급에서 제외(범위 밖 매물 편입 방지)
        if form_year is not None:
            if it.get("form_year") is None:
                continue
            if abs(it["form_year"] - form_year) > year_tol:
                continue
        # 주행거리 필터 — 결측 매물은 제외 (mileage_km이 지정된 tier에 한함)
        if mileage_km:
            if it.get("mileage_km") is None:
                continue
            lo, hi = mileage_km * (1 - mileage_tol), mileage_km * (1 + mileage_tol)
            if not (lo <= it["mileage_km"] <= hi):
                continue
        out.append(it)
    return out


def compute_stats(comparables: list[dict], platform: str = "encar",
                  form_year: Optional[int] = None,
                  mileage_km: Optional[int] = None,
                  year_tol: int = 1, mileage_tol: float = 0.30) -> MarketStats:
    raw_prices = [c["price_won"] for c in comparables if c.get("price_won") is not None]
    yr = (None, None)
    if form_year is not None:
        yr = (form_year - year_tol, form_year + year_tol)
    ml = (None, None)
    if mileage_km:
        ml = (int(mileage_km * (1 - mileage_tol)), int(mileage_km * (1 + mileage_tol)))
    if not raw_prices:
        return MarketStats(platform, 0, None, None, None, yr, ml)
    prices, n_out = trim_outliers(raw_prices)
    # 중앙값 산출에 실제 쓰인(이상치 제외) 매물을 감사용으로 보관 — 가격 오름차순 최대 40건
    # (연식·주행·가격 동일 매물은 표시상 중복 제거 — 감사 테이블 신뢰성)
    lo_p, hi_p = min(prices), max(prices)
    comps, _seen = [], set()
    for c in sorted((c for c in comparables
                     if c.get("price_won") is not None and lo_p <= c["price_won"] <= hi_p),
                    key=lambda c: c["price_won"]):
        key = (c.get("form_year"), c.get("mileage_km"), c.get("price_won"))
        if key in _seen:
            continue
        _seen.add(key)
        comps.append({"id": c.get("id"), "year": c.get("form_year"),
                      "mileage_km": c.get("mileage_km"), "price_won": c.get("price_won"),
                      "badge": c.get("badge"), "model": c.get("model")})
        if len(comps) >= 40:
            break
    n = len(prices)
    mean_p = statistics.mean(prices)
    cv = None
    if n >= 2 and mean_p:
        # 소표본 분산 과소평가 방지: 표본표준편차(stdev) 사용
        cv = round(statistics.stdev(prices) / mean_p, 3)
    # 신뢰도(표본·분산 기준, 최대 80점 — 매칭단계 보너스는 summarize에서 +20)
    # 표본 점수: 로그 곡선(≈n5:26·n10:36·n20:48·n30:55) — n10 조기 포화 제거, 대표성 반영
    conf = max(0, min(55, round(12 * math.log2(n + 1) - 5))) if n else 0
    if cv is not None:                        # 분산 가점(과가중 완화, 밴드 강화)
        conf += 25 if cv <= 0.10 else 15 if cv <= 0.20 else 5 if cv <= 0.30 else 0
    return MarketStats(
        platform=platform,
        sample_count=len(prices),
        mean_price=int(mean_p),
        median_price=int(statistics.median(prices)),
        min_price=min(prices),
        year_range=yr,
        mileage_range=ml,
        outlier_count=n_out,
        cv=cv,
        confidence=min(80, conf),
        comps=comps,
    )


def _fuel_match(item_fuel: Optional[str], listing_fuel: Optional[str]) -> bool:
    """연료 일치 — 하이브리드·전기 등 엔카 표기 변형(가솔린(하이브리드) 등)까지 부분일치."""
    if not item_fuel or not listing_fuel:
        return False
    a, b = item_fuel.strip(), listing_fuel.strip()
    if a == b:
        return True
    for key in ("하이브리드", "전기"):     # 표기 변형이 많은 파워트레인
        if key in a and key in b:
            return True
    return a in b or b in a


def _dedupe_by_id(listings: list[dict]) -> list[dict]:
    """중복 매물 제거 — ① 엔카 id, ② (연식·주행·가격) 동일(재등록)까지 제거.
    재등록/페이지중첩이 표본수·중앙값·신뢰도를 부풀리지 않게 하고, 감사 테이블과 표본수를 일치시킨다."""
    seen_id, seen_spec, out = set(), set(), []
    for l in listings:
        _id = l.get("id")
        if _id is not None and _id in seen_id:
            continue
        spec = (l.get("form_year"), l.get("mileage_km"), l.get("price_won"))
        if spec in seen_spec:
            continue
        if _id is not None:
            seen_id.add(_id)
        seen_spec.add(spec)
        out.append(l)
    return out


def _apply_appraisal_confidence(st: "MarketStats", appraisal_value, config,
                                cross_status: Optional[str] = None,
                                cross_rel: Optional[float] = None) -> None:
    """감정가 괴리 가드 + 소스 상한을 st.confidence에 통합 적용(단일 진실원천).

    summarize 내부에서 호출 — MarketStats.confidence가 모든 소비 경로에서 최종값이 되게 한다.
    cross_status(케이카 교차검증)에 따라 마지막 상한이 달라진다:
      single → single_source_cap(기본 88, 단일소스 위험 할인)
      agree  → cross_source_cap(기본 96) + 소폭 가점(독립 2소스 일치로 위험 완화)
      diverge→ cross_diverge_cap(기본 55) + 경고(두 소스가 크게 다름 = 매칭/시세 불확실)
    """
    if st.median_price is None:
        st.confidence_label = _confidence_label(st.confidence)
        return
    g = (config or {}).get("appraisal_guard", {}) if config else {}
    conf = st.confidence
    # ① 소프트 감점(정확도, 저측 완화)
    conf = max(0, conf - appraisal_penalty(st.median_price, appraisal_value, config))
    # ② 하드 상한(대역 이탈). strong 대역은 cv 무관 유지. mild는 '저측(시세<감정가, 흔함)'에서만
    #    양질 실측(저cv·충분표본)으로 완화 — 고측(시세>감정가, 오매칭·인플레 의심)은 저분산이어도 유지
    #    (오매칭은 같은 오답끼리 뭉쳐 cv가 낮아지므로 '저분산=신뢰'가 함정).
    cap, note, ratio = appraisal_guard(st.median_price, appraisal_value, config)
    st.market_vs_appraisal = ratio
    cap_mild = g.get("cap_mild", 60)
    min_sample = (config or {}).get("min_sample_count", 5)
    well = (st.sample_count >= min_sample and st.cv is not None
            and st.cv <= g.get("wellmatched_cv", 0.15))
    if cap is not None:
        relax = well and cap == cap_mild and ratio is not None and ratio < 1.0
        if not relax and conf > cap:
            conf = cap
        if note:
            st.match_label += f"·{note}"
    # ③ 소스 상한 — 케이카 교차검증 결과에 따라 상한을 선택(2소스 일치 시에만 88 상회 허용)
    status = cross_status or st.cross_source_status or "single"
    st.cross_source_status = status
    if cross_rel is not None:
        st.cross_source_rel = cross_rel
    if status == "agree":
        cross_cap = g.get("cross_source_cap", 96)
        bonus = g.get("cross_agree_bonus", 6)
        conf = min(cross_cap, conf + bonus)
        st.match_label += "·2소스일치"
    elif status == "diverge":
        conf = min(conf, g.get("cross_diverge_cap", 55))
        st.match_label += "·2소스불일치"
    else:
        conf = min(conf, g.get("single_source_cap", 88))
    st.confidence = conf
    st.confidence_label = _confidence_label(conf)


def summarize(listings: list[dict], form_year: Optional[int],
              mileage_km: Optional[int], platform: str = "encar",
              year_tol: int = 1, mileage_tol: float = 0.30,
              fuel: Optional[str] = None, min_sample: int = 5,
              trim: Optional[str] = None,
              appraisal_value: Optional[int] = None, config: Optional[dict] = None,
              cross_status: Optional[str] = None, cross_rel: Optional[float] = None,
              kcar_median: Optional[int] = None, kcar_sample: int = 0) -> MarketStats:
    """매칭 + 통계 (정교화판).

    ① **트림**(마이바흐·AMG 등 Badge) ② **연료 일치** ③ **동일 세대**(물건 연식의 지배적
    엔카 Model만) ④ 동급(연식±1·주행±30%) → 확장 → 연식±3 단계 완화.
    표본 id 중복을 제거하고, 표본이 min_sample 미만이면 신뢰도를 '낮음'으로 게이팅한다.
    trim이 있으나 Badge로 확인되는 표본이 부족하면(상위 트림 오매칭 위험) 신뢰도를 낮춘다.
    """
    from collections import Counter

    pool = _dedupe_by_id([l for l in listings if l.get("price_won") is not None])
    note = ""
    trim_unconfirmed = False
    fuel_unconfirmed = False
    gen_unconfirmed = False
    # ① 트림(Badge) 일치 — 상위 트림이 기본 트림 시세에 섞이지 않게
    if trim:
        tp = [l for l in pool if trim.upper() in (l.get("badge") or "").upper()]
        if len(tp) >= 3:
            pool = tp
            note += f"·{trim}"
        else:
            trim_unconfirmed = True   # 트림 확인 불가 → 아래에서 신뢰도 상한
    # ② 연료 일치 (하이브리드·전기 표기 변형까지 부분일치)
    if fuel:
        fp = [l for l in pool if _fuel_match(fuel, l.get("fuel"))]
        if len(fp) >= 3:          # 표본이 충분할 때만 연료로 좁힘
            pool = fp
            note += f"·{fuel}"
        elif any(l.get("fuel") for l in pool):
            fuel_unconfirmed = True   # 연료 지정됐으나 표본 부족으로 미적용 → 정직 표기
    # ② 동일 세대 (물건 연식과 정확히 같은 연식 매물의 지배적 Model)
    if form_year is not None:
        exact = [l.get("model") for l in pool if l.get("form_year") == form_year and l.get("model")]
        distinct_models = {l.get("model") for l in pool if l.get("model")}
        if exact:
            dominant = Counter(exact).most_common(1)[0][0]
            same_gen = [l for l in pool if l.get("model") == dominant]
            if len(same_gen) >= 3:
                pool = same_gen
                note += "·동세대"
            elif len(distinct_models) >= 2:
                gen_unconfirmed = True   # 세대 확정 못했는데 이종 세대 혼입
        elif len(distinct_models) >= 2:
            gen_unconfirmed = True

    tiers = [
        (f"동급 (연식±{year_tol}·주행±{int(mileage_tol * 100)}%)", year_tol, mileage_tol, 20),
        ("확장 (연식±2·주행±50%)", 2, 0.50, 10),
        ("연식±3·주행±80%", 3, 0.80, 0),   # 주행을 완전히 끄지 않음(저주행 comp 상방편향 억제)
    ]
    # 표본이 충분(≥min_sample)한 가장 좁은 tier를 우선 채택. 없으면 가장 좁은 비어있지 않은 tier.
    # (동급 3건보다 확장 12건이 대표성이 높음 — 빈약한 동급을 성급히 '낮음'으로 처리하지 않도록)
    first_nonempty = None
    chosen = None
    for idx, (label, ytol, mtol, tier_bonus) in enumerate(tiers):
        comps = filter_comparable(
            pool, form_year,
            mileage_km if mtol is not None else None,
            year_tol=ytol, mileage_tol=mtol if mtol is not None else 9.99)
        if not comps:
            continue
        if first_nonempty is None:
            first_nonempty = (idx, label, ytol, mtol, tier_bonus, comps)
        if len(comps) >= min_sample:
            chosen = (idx, label, ytol, mtol, tier_bonus, comps)
            break
    chosen = chosen or first_nonempty
    if chosen is None:
        st = compute_stats([], platform, form_year, mileage_km, year_tol, mileage_tol)
        st.match_label = "동급 표본 없음"
        st.confidence_label = _confidence_label(0)
        st.market_vs_appraisal = appraisal_guard(None, appraisal_value, config)[2]
        return st
    tier_idx, label, ytol, mtol, tier_bonus, comps = chosen
    st = compute_stats(comps, platform, form_year, mileage_km,
                       ytol, mtol if mtol is not None else 9.99)
    extra = f"·이상치{st.outlier_count}건제외" if st.outlier_count else ""
    st.match_label = label + note + extra
    st.confidence = min(100, st.confidence + tier_bonus)
    if st.sample_count < min_sample:      # 표본 부족 → 신뢰도 '낮음' 상한
        st.confidence = min(st.confidence, 40)
        st.match_label += f"·표본{st.sample_count}건(부족)"
    if trim_unconfirmed:                  # 상위 트림 Badge 미확인 → 신뢰도 상한
        st.confidence = min(st.confidence, 40)
        st.match_label += f"·{trim}트림 미확인"
    if gen_unconfirmed:                    # 이종 세대 혼입 가능 → '보통' 상한
        st.confidence = min(st.confidence, 60)
        st.match_label += "·세대미확인"
    if fuel_unconfirmed:                   # 연료 지정됐으나 미적용(파워트레인 혼입 가능) → '보통' 상한
        st.confidence = min(st.confidence, 60)
        st.match_label += "·연료미필터"
    st.tier_level = tier_idx   # 0=동급·1=확장·2=연식±3 (소스간 tier 정합 비교용)
    # 케이카 교차검증 소스 기록(있으면) — 상한 선택에 사용
    st.kcar_median = kcar_median
    st.kcar_sample = kcar_sample or 0
    # 감정가 괴리 가드 + 소스 상한을 여기서 통합 적용 → MarketStats.confidence가 최종 진실원천
    _apply_appraisal_confidence(st, appraisal_value, config,
                               cross_status=cross_status, cross_rel=cross_rel)
    return st
