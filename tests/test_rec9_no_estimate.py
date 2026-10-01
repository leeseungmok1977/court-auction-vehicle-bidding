# -*- coding: utf-8 -*-
"""REC-9(지시서 2026-10-01-03) — 침수·전손 판정 물건: 판정 문장과 화면이 같은 말을 하게 하는 **신호 하나**.

2026-09-30 교차검수(34408 — 2025타경34408_1 CLS300 d, 비가드): 빨간 판정 상자가
"잔존 가치를 산정할 수 없어 예상낙찰가·입찰 상한선을 제공하지 않습니다. 입찰하지 마세요."라고 말한 바로 아래,
리포트 §01 이 가장 큰 글자로 예상가 밴드 1,230~1,460만원·중심값 13,100,000원을 그렸다(09-29 백업 사본에서 재현).

신호: `service.estimate_withheld(v, st)` 한 곳 — bid_state 의 침수·전손 분기(blocked)를 탄 물건이면 참.
  · bid_state 결과의 `no_estimate`(목록 카드·상세·리포트의 `bidst`)
  · plain_verdict 결과의 `no_estimate`(판정 상자 `verdict`)
  · 관심 화면 행의 `no_estimate`
모두 이 값이다. 판정 문장("…제공하지 않습니다")의 조건도 이 함수라, 신호는 그 문장과 같은 조건에서만 참이다.
판정 기준(bid_state state·tone)은 바꾸지 않는다 — 화면 표시용 스위치다.

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import inspect

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _ge300, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from web import db, service

_PUB = {"x-forwarded-for": "203.0.113.7"}
MSG = "예상낙찰가·입찰 상한선을 제공하지 않습니다"


@pytest.fixture
def cars(mk):
    """침수 두 갈래(등급·저장 판정) + 끝난 침수차 + 판정별 대조군."""
    return {
        # 34408 값 그대로(09-29 백업) — 날짜만 오늘 기준으로 옮겼다
        "FLOOD": mk("FLOOD", maker="Mercedes-Benz", model="Mercedes-Benz CLS300 d", year=2020, court="광주지방법원",
                    appraisal_value=30_000_000, min_sale_price=10_752_000, fail_count=4, sale_date=_d(6),
                    sale_time="09:55", judgment="입찰 보류", accident_grade="flood", runnable="no",
                    median_price=34_900_000, sample_count=5, market_confidence=53, market_confidence_label="보통",
                    upper_bid=-13_321_000, lower_bound=10_752_000, photo_count=8, mileage_km=65_683),
        # 감정서 침수·전손 키워드로만 '입찰 보류'(등급은 무사고 확인) — 상한선 계산은 된다(personal_use_max_bid)
        "KWFLOOD": mk("KWFLOOD", appraisal_value=30_000_000, min_sale_price=10_000_000, fail_count=2,
                      judgment="입찰 보류", accident_grade="none",
                      insurance_history={"own_damage": 0, "opp_damage": 0},
                      median_price=30_000_000, upper_bid=19_000_000),
        # 끝난 침수차 — 참고 기록이라 가리지 않는다(판정 '매각 종료')
        "FLOOD_WON": mk("FLOOD_WON", appraisal_value=12_000_000, min_sale_price=9_000_000, sale_date=_d(-10),
                        judgment="종결", accident_grade="flood", median_price=13_000_000, auction_result="낙찰",
                        winning_price=9_500_000),
        # 판정별 대조군
        "RSL": mk("RSL", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="입찰 검토 가능",
                  median_price=30_000_000, upper_bid=19_000_000),
        "BLK": mk("BLK", appraisal_value=20_000_000, min_sale_price=16_000_000, median_price=16_600_000,
                  judgment="유찰 대기"),                                        # 최저가 > 손익분기 — 비침수 부적합
        "USE": mk("USE", appraisal_value=30_000_000, min_sale_price=16_000_000, median_price=40_000_000,
                  judgment="유찰 대기"),
        "LOWC": mk("LOWC", appraisal_value=30_000_000, min_sale_price=10_000_000, median_price=30_000_000,
                   judgment="시세 신뢰도 낮음, 수동 검토", market_confidence_label="낮음", market_confidence=30),
        "STOP": mk("STOP", appraisal_value=30_000_000, min_sale_price=10_000_000, median_price=30_000_000,
                   judgment="입찰 검토 가능", upper_bid=19_000_000, runnable="no"),
        "PAST": mk("PAST", appraisal_value=30_000_000, min_sale_price=10_000_000, median_price=30_000_000,
                   judgment="유찰 대기", sale_date=_d(-3)),
        "GE300": _ge300(mk),
    }


def _exp(v):
    band = service.expected_band(v, BT)
    return {"price": band["price"], "lo": band["lo"], "hi": band["hi"]} if band else None


# ── 전제 — 픽스처가 그 갈래를 만든다 ──────────────────────────────────────
def test_전제_침수차에도_예상가_밴드와_상한선_재료가_있다(cars):
    """가릴 숫자가 실제로 있어야 재현이다 — 34408 은 밴드가 있고, 키워드 보류 물건은 상한선까지 있다."""
    band = service.expected_band(cars["FLOOD"], BT)
    assert band and band["price"] and band["lo"] < band["price"] < band["hi"], band
    st = service.bid_state(cars["KWFLOOD"], BT)
    assert st["state"] == "blocked" and st["max_bid"], st
    assert service.bid_state(cars["BLK"], BT)["state"] == "blocked", "비침수 부적합 대조군"
    assert service.bid_state(cars["FLOOD_WON"], BT)["state"] == "closed"
    states = {service.bid_state(v, BT)["state"] for v in cars.values()}
    assert states >= {"blocked", "closed", "resale", "usepick", "lowconf", "wait"}, states


# ── 신호의 값 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid,want", [("FLOOD", True), ("KWFLOOD", True), ("FLOOD_WON", False), ("RSL", False),
                                      ("BLK", False), ("USE", False), ("LOWC", False), ("STOP", False),
                                      ("PAST", False), ("GE300", False)])
def test_신호는_침수전손_판정에서만_참이다(cars, vid, want):
    v = cars[vid]
    st = service.bid_state(v, BT)
    assert st["no_estimate"] is want, (vid, st["state"], st["label"])
    assert service.estimate_withheld(v, st) is want
    assert service.estimate_withheld(v) is want, "st 없이 불러도 같은 값"


@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD", "FLOOD_WON", "RSL", "BLK", "USE", "LOWC", "STOP", "PAST"])
def test_판정_문장과_신호가_같은_조건이다(cars, vid):
    """'제공하지 않습니다' 문장 ⇔ verdict.no_estimate ⇔ bidst.no_estimate — 한 곳(estimate_withheld)에서 정한다."""
    v = cars[vid]
    st = service.bid_state(v, BT)
    exp = _exp(v) or ({"price": st["exp"]} if st.get("exp") else None)
    if not exp:
        pytest.skip(f"{vid}: 예상가가 없어 판정 문장이 없다")
    pv = service.plain_verdict(v, exp, st)
    assert pv, vid
    says = MSG in pv["text"]
    assert says == bool(pv.get("no_estimate")) == st["no_estimate"], (vid, pv)


def test_키워드로만_보류된_물건도_칩과_같은_말을_한다(cars):
    """예전 문장 조건은 등급 flood 뿐이라, 칩이 '침수·전손 의심 — 입찰 보류'인 물건에 '최저매각가가 손익분기를 넘어'라는
    다른 이유를 댔다(이 물건은 최저가 1,000만 ≤ 상한선이라 그 이유 자체가 거짓)."""
    v = cars["KWFLOOD"]
    st = service.bid_state(v, BT)
    assert st["label"] == "침수·전손 의심 — 입찰 보류" and v["min_sale_price"] <= st["max_bid"]
    pv = service.plain_verdict(v, _exp(v), st)
    assert MSG in pv["text"] and pv["no_estimate"] is True and pv["tone"] == "stop"
    assert "손익분기" not in pv["text"], pv["text"]


def test_끝난_침수차는_참고_기록으로_남는다(cars):
    v = cars["FLOOD_WON"]
    pv = service.plain_verdict(v, _exp(v) or {"price": 9_500_000}, service.bid_state(v, BT))
    assert pv["text"].startswith("이미 매각이 끝난") and not pv.get("no_estimate")


# ── 화면 컨텍스트 — 템플릿이 읽는 자리 ───────────────────────────────────────
@pytest.fixture
def get(monkeypatch):
    import web.app as A
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append(ctx)
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    c = TestClient(A.app)

    def _get(url):
        cap.clear()
        r = c.get(url, headers=_PUB)
        assert r.status_code == 200, (url, r.status_code)
        return cap[-1]
    return _get


@pytest.mark.parametrize("path", ["/vehicle/{}", "/vehicle/{}/report"])
def test_상세와_리포트는_bidst_와_verdict_로_신호를_받는다(cars, get, path):
    ctx = get(path.format("FLOOD"))
    assert ctx["bidst"]["no_estimate"] is True and ctx["verdict"]["no_estimate"] is True
    assert ctx["expected"] and ctx["expected"]["price"], "예상가 값은 그대로 온다 — 가리는 것은 템플릿(명세)"
    ok = get(path.format("RSL"))
    assert ok["bidst"]["no_estimate"] is False and not (ok["verdict"] or {}).get("no_estimate")


def test_목록_카드는_행의_bidst_로_신호를_받는다(cars, get):
    ctx = get("/vehicles?all=1&sort=expected")
    rows = {r["id"]: r for r in ctx["rows"]}
    assert rows["FLOOD"]["bidst"]["no_estimate"] is True and rows["FLOOD"]["expected_win"], "예상가 값은 온다"
    assert rows["RSL"]["bidst"]["no_estimate"] is False


def test_관심_화면은_행의_no_estimate_로_신호를_받는다(cars, get):
    ctx = get("/watchlist?ids=FLOOD,KWFLOOD,RSL,GE300,FLOOD_WON")
    rows = {r["id"]: r for r in ctx["rows"]}
    assert rows["FLOOD"]["no_estimate"] is True and rows["KWFLOOD"]["no_estimate"] is True
    assert rows["RSL"]["no_estimate"] is False and rows["GE300"]["no_estimate"] is False
    assert rows["FLOOD_WON"]["no_estimate"] is False
    # 가드가 아닌 행에는 여전히 bidst 를 달지 않는다(칩 체계·렌더 바이트 불변 규칙 — REC-1 3회차)
    assert rows["FLOOD"]["bidst"] is None and rows["GE300"]["bidst"] is not None


# ── 홈 세 자리(캐러셀·유망 물건·알림)에는 침수차가 구조적으로 서지 않는다 ─────────────
def test_침수차는_추천_자리에_서지_않는다(mk):
    """저장 판정이 '입찰 검토 가능'이고 사진·시세·되팔이 손익분기까지 갖춘 침수차도 — bid_state 가 stop 으로 막는다."""
    v = mk("FLDR", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="입찰 검토 가능",
           median_price=30_000_000, upper_bid=19_000_000, accident_grade="flood", sale_date=_d(2))
    ctrl = mk("RSL", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="입찰 검토 가능",
              median_price=30_000_000, upper_bid=19_000_000, sale_date=_d(2))
    assert service.estimate_withheld(v) and not service.estimate_withheld(ctrl)
    assert "RSL" in {r["id"] for r in service.promising_rows(BT)}, "대조군은 선다(공허 통과 방지)"
    assert "FLDR" not in {r["id"] for r in service.promising_rows(BT)}
    assert "FLDR" not in {p["id"] for p in service.compute_daily_picks(5)}
    assert service._daily_pick_gate(v, "resale", BT) is None
    assert "FLDR" not in {a["id"] for a in service.alert_items(3)}
    assert "RSL" in {a["id"] for a in service.alert_items(3)}
    assert service.lifecycle_bucket_of(v, BT) != "review"


# ── 구조 — 한 곳에서 정한다 ─────────────────────────────────────────────────
def test_구조_침수_술어와_신호는_한_곳이다():
    import web.app as A
    assert "flood_hold(v)" in inspect.getsource(service.bid_state)
    assert '"no_estimate": True' in inspect.getsource(service.bid_state)
    assert "estimate_withheld(v, st)" in inspect.getsource(service.plain_verdict)
    assert 'accident_grade") == "flood"' not in inspect.getsource(service.plain_verdict), "문장 조건을 따로 적지 않는다"
    assert "service.flood_hold(v)" in inspect.getsource(A._floor_hold)
    assert "service.estimate_withheld(" in inspect.getsource(A.watchlist)
