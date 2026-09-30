# -*- coding: utf-8 -*-
"""REC-7 ⑺ — 홈 캐러셀 '되팔아도 남음'은 판정(bid_state)이 되팔이(resale)일 때만.

2026-10-01 라이브: REC-1 최저가 재조회로 최저가가 법원 값으로 바로잡히자, 저장 판정이 '입찰 검토 가능'(최저가 기준)이지만
예상 경쟁가로는 되팔이 손익분기를 넘는 물건이 캐러셀 재판매 칸에 올랐다. BMW 520d(2026타경30118_1)는
최저 686만 · 예상 840만 · 되팔이 손익분기 752.6만 — 캐러셀은 '✓ 되팔아도 남음', 상세는 '되팔이 차익은 어렵습니다'.
"""
from __future__ import annotations

from datetime import date, timedelta

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from web import service

TODAY = date.today()


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def _b520_after_refresh(mk):
    """재조회 뒤 520d — 최저가 686만 = 감정가 2,000만 × 0.7³(유찰 3회와 일치, 가드 아님) · 사고 8회 감가 30% 반영 상한가."""
    hist = [{"ymd": _d(-85), "result_code": "002", "result": "유찰", "lws_price": 20_000_000, "dspsl_amt": None},
            {"ymd": _d(-50), "result_code": "002", "result": "유찰", "lws_price": 14_000_000, "dspsl_amt": None},
            {"ymd": _d(-15), "result_code": "002", "result": "유찰", "lws_price": 9_800_000, "dspsl_amt": None},
            {"ymd": _d(11), "result_code": "", "result": "", "lws_price": 6_860_000, "dspsl_amt": 0}]
    return mk("B520R", maker="BMW", model="BMW 520d", year=2017, court="전주지방법원", sale_date=_d(11),
              appraisal_value=20_000_000, min_sale_price=6_860_000, fail_count=3, dxdy_history=hist,
              judgment="입찰 검토 가능", median_price=20_795_000, sample_count=14, market_confidence=85,
              accident_grade="accident", insurance_history={"own_damage": 8, "opp_damage": 2},
              upper_bid=7_525_950, lower_bound=6_860_000, photo_count=15)


def test_전제_520d_는_가드가_아니고_판정은_지금_사면_이득이며_예상가가_손익분기를_넘는다(mk):
    v = _b520_after_refresh(mk)
    assert not service.floor_unconfirmed(v), "최저가가 확인된 물건이어야 한다(가드면 다른 경로로 빠진다)"
    exp = service.expected_for(v, BT)
    st = service.bid_state(v, BT)
    assert exp and exp > v["upper_bid"], f"예상가 {exp} 가 되팔이 손익분기 {v['upper_bid']} 를 넘어야 재현이다"
    assert st["state"] == "usepick", st


def test_재판매_칸은_판정이_되팔이가_아니면_받지_않는다(mk):
    v = _b520_after_refresh(mk)
    assert service._daily_pick_gate(v, "resale", BT) is None


def test_대조군_판정이_되팔이인_물건은_재판매_칸에_선다(mk):
    r = mk("RSL", maker="기아", model="K5", appraisal_value=30_000_000, min_sale_price=10_000_000,
           fail_count=1, judgment="입찰 검토 가능", median_price=30_000_000, upper_bid=19_000_000)
    assert service.bid_state(r, BT)["state"] == "resale", "대조군 전제: 판정이 되팔이여야 한다"
    assert service._daily_pick_gate(r, "resale", BT) is not None


def test_오늘의_추천에서_520d_는_되팔아도_남음_칸으로_서지_않는다(mk):
    _b520_after_refresh(mk)
    picks = service.compute_daily_picks(5)
    assert not [p for p in picks if p["id"] == "B520R" and p["kind"] == "resale"], picks
