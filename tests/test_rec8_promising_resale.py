# -*- coding: utf-8 -*-
"""REC-8 추가(지시서 2026-10-01-03 범위 확장) — 홈 '유망 물건'의 '✓ 되팔아도 남음'은 판정(bid_state)이 되팔이일 때만.

2026-10-01 07:30 라이브(Steward 확인): 520d(2026타경30118_1)·봉고(3142_1)는 bid_state state 가 usepick('지금 사면 이득')
인데 유망 물건 표·카드에 '✓ 되팔아도 남음'이 붙었다(E300 50522_1 도). service.promising_rows 가 칸(kind)을
`judgment == '입찰 검토 가능' and _review_biddable(v)` 만으로 'resale' 로 정했기 때문이다 — 캐러셀은 eefc578(REC-7 ⑺)에서
`_daily_pick_gate` 의 재판매 칸을 bid_state == 'resale' 일 때만으로 이미 막았다. 같은 누수의 여섯 번째 자리다.

처방: 두 곳이 **같은 함수**(service.resale_pick_ok)로 재판매 칸을 정한다. 떨어진 물건은 두 곳 모두 실사용 갈래
(personal_use_tier)로 다시 심사받는데, 그 함수는 저장 판정이 '입찰 검토 가능'이면 '그쪽 칸이 가져간다'며 None 이라
지금 규칙에서는 두 곳 모두에서 **빠진다**(배지를 '지금 사면 이득'으로 바꿔 다는 것이 아니다 — 판정 기준은 그대로).

520d 값은 REC-1 재조회 뒤 라이브 값: 최저 6,860,000 · 유찰 3 · 감정가 20,000,000 · 시세 20,795,000 · upper_bid 7,525,950 ·
사고(내차) 8회 → bid_state usepick(tests/test_rec7_carousel_resale_state.py 의 픽스처와 같은 값).
외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import inspect

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _ge300, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec7_carousel_resale_state import _b520_after_refresh
from web import service

_PUB = {"x-forwarded-for": "203.0.113.7"}


def _rsl(mk, vid="RSL", **kw):
    """대조군 — 판정이 되팔이(resale)인 물건(REC-7 ⑺ 대조군과 같은 값)."""
    base = dict(maker="기아", model="K5", appraisal_value=30_000_000, min_sale_price=10_000_000, fail_count=1,
                judgment="입찰 검토 가능", median_price=30_000_000, upper_bid=19_000_000)
    base.update(kw)
    return mk(vid, **base)


def _kinds():
    return {r["id"]: r["pick_kind"] for r in service.promising_rows(BT)}


def test_전제_520d_는_판정이_지금_사면_이득이고_유망_물건의_다른_자격은_갖췄다(mk):
    v = _b520_after_refresh(mk)
    st = service.bid_state(v, BT)
    assert st["state"] == "usepick" and st["label"] == "지금 사면 이득" and st["tone"] == "ok", st
    assert service._promising(v), "시세 신뢰도 '높음' + 오매칭 아님 — 칸 판단만 남아야 재현이다"
    exp = service.expected_for(v, BT)
    assert exp and exp < v["median_price"], "시세보다 싸다 — 유망 물건의 나머지 문턱을 넘는다"
    assert exp > v["upper_bid"], "예상 경쟁가가 되팔이 손익분기를 넘는다 — '되팔아도 남음'은 거짓"
    assert service.personal_use_tier(v, BT) is None, "저장 판정 '입찰 검토 가능'이면 실사용 갈래는 None(그쪽 칸이 가져간다)"


def test_520d_는_유망_물건에서_되팔아도_남음으로_서지_않는다(mk):
    _b520_after_refresh(mk)
    _rsl(mk)
    kinds = _kinds()
    assert kinds.get("RSL") == "resale", f"대조군은 선다(공허 통과 방지): {kinds}"
    assert kinds.get("B520R") != "resale", kinds
    assert "B520R" not in kinds, "지금 규칙(personal_use_tier 제외 줄)에서는 배지를 바꿔 다는 것이 아니라 빠진다"


def test_유망_물건과_캐러셀이_같은_판단을_쓴다(mk):
    """두 자리의 재판매 칸 판단이 물건마다 같다 — 되팔이(RSL) · 지금 사면 이득(520d) · 상한선 초과(OVR) · 가드(GE300) ·
    침수 등급이 뒤에 붙은 물건(FLDR)."""
    cars = {
        "RSL": _rsl(mk),
        "B520R": _b520_after_refresh(mk),
        "OVR": _rsl(mk, "OVR", upper_bid=None, appraisal_value=12_000_000, median_price=13_000_000),
        "GE300": _ge300(mk),
        "FLDR": _rsl(mk, "FLDR", accident_grade="flood"),
    }
    assert service.bid_state(cars["OVR"], BT)["state"] == "over_market", "전제: 되팔이 손익분기 없는 물건은 상한선 초과"
    kinds = _kinds()
    picks = {p["id"]: p["kind"] for p in service.compute_daily_picks(10)}
    for vid, v in cars.items():
        gate = service._daily_pick_gate(v, "resale", BT) is not None
        prom = kinds.get(vid) == "resale"
        pick = picks.get(vid) == "resale"
        ok = service.resale_pick_ok(v, service.bid_state(v, BT))
        assert gate == pick == ok, (vid, gate, pick, ok)
        # 유망 물건은 시세보다 싸야(exp < 시세) 선다 — 그 문턱을 넘는 물건에서는 캐러셀과 판단이 같아야 한다
        exp = service.expected_for(v, BT)
        if exp and exp < v["median_price"]:
            assert prom == ok, (vid, prom, ok)
    assert {k for k, x in kinds.items() if x == "resale"} == {"RSL"} and picks.get("RSL") == "resale"


def test_전체_목록과_홈_섹션도_같은_함수다(mk):
    """`/vehicles?picks=1`(유망 물건 전체)·홈 표는 promising_rows 를 그대로 쓴다 — 520d 가 '되팔아도 남음'으로 그려지지 않는다."""
    _b520_after_refresh(mk)
    _rsl(mk)
    import web.app as A
    c = TestClient(A.app)
    html = c.get("/vehicles?picks=1", headers=_PUB).text
    assert "/vehicle/RSL" in html and "/vehicle/B520R" not in html
    home = c.get("/", headers=_PUB).text
    i = home.index("유망 물건")
    sec = home[i:home.index("</section>", i)] if "</section>" in home[i:] else home[i:i + 20000]
    assert "B520R" not in sec, "홈 유망 물건 표에 520d 가 섰다"


def test_구조_두_자리가_같은_함수를_부른다():
    assert "resale_pick_ok(" in inspect.getsource(service.promising_rows)
    assert "resale_pick_ok(" in inspect.getsource(service._daily_pick_gate)
    src = inspect.getsource(service.resale_pick_ok)
    assert '"입찰 검토 가능"' in src and '"resale"' in src
    # 저장 문자열만으로 재판매 칸을 정하던 옛 줄이 돌아오지 않게
    body = inspect.getsource(service.promising_rows)
    assert 'if v.get("judgment") == "입찰 검토 가능" and _review_biddable(v):\n            kind = "resale"' not in body
