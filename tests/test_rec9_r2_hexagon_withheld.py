# -*- coding: utf-8 -*-
"""REC-9 2회차(지시서 2026-10-01-15) — 침수·전손 판정 물건의 리포트 01 육각형은 정상 차량 시세에 기댄 축을 내지 않는다.

2026-10-01 교차검수(design-critic 고칠 것 2 · app-design-expert 고칠 것 2a, 34408 — 2025타경34408_1 CLS300 d):
빨간 판정 "잔존 가치를 산정할 수 없어 예상낙찰가·입찰 상한선을 제공하지 않습니다"가 선 같은 01 에
'가격 메리트 100(할인 69%)'·'시세 신뢰도 53'·'잔존가치 38'·'유동성 84' — 머리 "6/6축 산출"이 그려졌다.
네 축 모두 정상 차량 시세·시장이 기준이다. 판정의 이유가 바로 그 시세를 이 차에 쓸 수 없다는 것이다.

Steward 결정 (나) 서버: `service.hexagon_scores` 가 `estimate_withheld(v)` 참이면 네 축(HEXA_MARKET_AXES)을 score None + 사유.
남는 축은 사고·상태·주행 적정성 둘이라 리포트의 기존 게이트(`hexa.n_avail >= 3`)가 육각형을 접는다(템플릿 변경 없음).
판정 기준은 그대로다 — 표시를 조이는 쪽이다. estimate_withheld 가 거짓인 물건(끝난 침수차·비침수 부적합·되팔이)의
육각형과 리포트는 바이트 그대로다.

'옛 동작'은 HEXA_MARKET_AXES 를 빈 튜플로 두어 재현한다 — 육각형만 옛 모습이 되고 판정·문장·나머지 리포트는 그대로다.
그 재현이 공허하지 않도록 34408 장면(100·53·0·86·38·84, 6/6)과 대조군의 시세 축 점수(수정 전 코드로 계산한 값)를 못 박는다.

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`. 리포트 라우트가 감정서·사진을 찾는 DATA_DIR 은
임시 폴더로 돌린다(data/ 무접촉).
"""
import difflib
import inspect
import json
import re
from datetime import date

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from web import service

TODAY = date(2026, 10, 1)            # 육각형 경과연수 기준 고정(점수 값을 단언하므로)
_PUB = {"x-forwarded-for": "203.0.113.7"}
MARKET = ("price", "conf", "value", "liq")
SAYS = "잔존 가치를 산정할 수 없어"     # 판정 문장(plain_verdict) — 숫자 '잔존가치'와 한 렌더에 함께 서면 안 된다
# 34408 이 육각형에 쓰던 재료 — 같은 차종 매물 363건(유동성 84) · 출시가 8,700~13,380만원(중간 11,040만원 → 잔존가치 38)
_FULL = {"encar_total": 363, "newcar_min": 8_700, "newcar_max": 13_380}
# 리포트 01 육각형 표의 한 줄: 축 이름 → 점수 칸
_ROW = re.compile(r'<span class="nm">([^<]+)</span>\s*<div class="tk">.*?</div>\s*<span class="sc num">([^<]*)</span>', re.S)


@pytest.fixture
def cars(mk):
    """침수 두 갈래(등급 flood · 키워드로만 '입찰 보류') + 대조군 셋. 다섯 대 모두 육각형 재료를 갖춘다 —
    대조군이 육각형을 그리지 않으면 '바이트 그대로'가 공허 통과다."""
    return {
        # 34408 값 그대로(09-29 백업) — 날짜만 오늘 기준으로 옮겼다. 저장 판정 '입찰 보류' · 예상가 밴드 있음
        "FLOOD": mk("FLOOD", maker="Mercedes-Benz", model="Mercedes-Benz CLS300 d", year=2020, court="광주지방법원",
                    appraisal_value=30_000_000, min_sale_price=10_752_000, fail_count=4, sale_date=_d(6),
                    sale_time="09:55", judgment="입찰 보류", accident_grade="flood", condition_level="poor",
                    runnable="no", median_price=34_900_000, sample_count=5, market_confidence=53,
                    market_confidence_label="보통", upper_bid=-13_321_000, lower_bound=10_752_000, photo_count=8,
                    mileage_km=65_683, **_FULL),
        # 감정서 침수·전손 키워드로만 '입찰 보류'(등급은 무사고 확인) — test_rec9_no_estimate 의 KWFLOOD 에 육각형 재료를 더했다
        "KWFLOOD": mk("KWFLOOD", appraisal_value=30_000_000, min_sale_price=10_000_000, fail_count=2,
                      judgment="입찰 보류", accident_grade="none",
                      insurance_history={"own_damage": 0, "opp_damage": 0},
                      median_price=30_000_000, upper_bid=19_000_000, **_FULL),
        # 대조군 ① 비침수 부적합(최저가 > 손익분기 — 같은 blocked·stop 이지만 침수가 아니다)
        "BLK": mk("BLK", appraisal_value=20_000_000, min_sale_price=16_000_000, median_price=16_600_000,
                  judgment="유찰 대기", **_FULL),
        # 대조군 ② 끝난 침수차 — 참고 기록(판정 '매각 종료'). 34408 도 매각이 끝나면 이 갈래다
        "FLOOD_WON": mk("FLOOD_WON", appraisal_value=12_000_000, min_sale_price=9_000_000, sale_date=_d(-10),
                        judgment="종결", accident_grade="flood", median_price=13_000_000, auction_result="낙찰",
                        winning_price=9_500_000, **_FULL),
        # 대조군 ③ 되팔이 — 판정이 초록인 물건
        "RSL": mk("RSL", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="입찰 검토 가능",
                  median_price=30_000_000, upper_bid=19_000_000, **_FULL),
    }


def _hx(v, **kw):
    kw.setdefault("newcar_ok", True)      # config 의존 없이 출시가 공개 상태로 고정(test_hexagon 과 같은 규칙)
    return service.hexagon_scores(v, TODAY, **kw)


def _ax(h):
    return {a["key"]: a for a in h["axes"]}


def _scores(h):
    return {a["key"]: a["score"] for a in h["axes"]}


def _old(monkeypatch, fn):
    """옛 동작 — 육각형이 침수·전손 판정으로 가릴 축이 없던 때. 판정·문장은 그대로 두고 육각형만 되돌린다."""
    with monkeypatch.context() as m:
        m.setattr(service, "HEXA_MARKET_AXES", ())
        return fn()


def _dump(h):
    return json.dumps(h, ensure_ascii=False, sort_keys=True)


# ── 전제 — 픽스처가 그 갈래를 만들고, 옛 동작이 그 장면을 그린다 ─────────────────────────
def test_전제_픽스처가_그_갈래를_만든다(cars, monkeypatch):
    for vid in ("FLOOD", "KWFLOOD"):
        v = cars[vid]
        st = service.bid_state(v, BT)
        assert service.estimate_withheld(v) is True, f"{vid}: 침수·전손 판정이 아니다 — 이 파일 전체가 공허 통과다"
        assert st["state"] == "blocked" and st["no_estimate"] is True and st["label"] == "침수·전손 의심 — 입찰 보류", st
        assert service.expected_band(v, BT), f"{vid}: 예상가 밴드가 없다(34408 은 있었다)"
    assert cars["KWFLOOD"]["accident_grade"] != "flood", "키워드 보류형은 등급이 flood 가 아니어야 한다"
    blk, won = service.bid_state(cars["BLK"], BT), service.bid_state(cars["FLOOD_WON"], BT)
    assert blk["state"] == "blocked" and "침수" not in blk["label"] and not service.estimate_withheld(cars["BLK"])
    assert won["state"] == "closed" and cars["FLOOD_WON"]["accident_grade"] == "flood"
    assert not service.estimate_withheld(cars["FLOOD_WON"]), "끝난 침수차는 참고 기록 — 가리지 않는다"
    assert service.bid_state(cars["RSL"], BT)["state"] == "resale"
    # 옛 동작은 34408 장면을 그대로 그린다 — 교차검수가 본 값(100·53·0·86·38·84, 6/6축)
    old = _old(monkeypatch, lambda: _hx(cars["FLOOD"]))
    assert _scores(old) == {"price": 100, "conf": 53, "cond": 0, "km": 86, "value": 38, "liq": 84}, _scores(old)
    assert old["n_avail"] == 6 and "할인 69%" in _ax(old)["price"]["note"]
    for vid in ("KWFLOOD", "BLK", "FLOOD_WON", "RSL"):
        o = _old(monkeypatch, lambda: _hx(cars[vid]))
        assert all(isinstance(_ax(o)[k]["score"], int) for k in MARKET), (vid, _scores(o))


# ── 침수·전손 판정: 시세 기반 네 축을 내지 않는다 ──────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD"])
@pytest.mark.parametrize("private", [False, True])
def test_침수전손_판정이면_시세_기반_네_축은_미산출이고_사유가_있다(cars, monkeypatch, vid, private):
    v = cars[vid]
    new, old = _hx(v, include_private=private), _old(monkeypatch, lambda: _hx(v, include_private=private))
    for k in MARKET:
        a = _ax(new)[k]
        assert a["score"] is None, (vid, k, a)
        assert a["note"] == service.HEXA_WITHHELD_NOTE and "침수·전손" in a["note"], (vid, k, a["note"])
        assert not any(ch.isdigit() for ch in a["note"]), "점수를 내지 않는 축에 숫자 근거를 남기지 않는다"
        assert "px" not in a and "count" not in a, (vid, k, a)
        assert isinstance(_ax(old)[k]["score"], int), "옛 동작은 숫자를 냈다(공허 통과 방지)"
    if private:
        assert "count" in _ax(old)["liq"], "옛 동작은 관리자에게 매물 건수를 실었다"
    # 시세에 기대지 않는 두 축은 그대로다
    for k in ("cond", "km"):
        assert _ax(new)[k] == _ax(old)[k], (vid, k)
    assert new["n_avail"] == 2 < 3, "리포트 게이트(n_avail >= 3)가 육각형을 접는 조건"
    assert new["poly"] == "" and new["edges"] == []


# ── 리포트 01 렌더 ──────────────────────────────────────────────────────────────
@pytest.fixture
def get(monkeypatch, tmp_path):
    """리포트 렌더 — 공개(nginx 경유)·관리자(루프백) 두 갈래. 컨텍스트도 함께 돌려준다."""
    import web.app as A
    monkeypatch.setattr(A, "DATA_DIR", tmp_path)          # 감정서·사진 경로 — data/ 를 보지 않는다
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append(ctx)
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    pub, adm = TestClient(A.app), TestClient(A.app, base_url="http://127.0.0.1")

    def _get(vid, admin=False):
        cap.clear()
        r = adm.get(f"/vehicle/{vid}/report") if admin else pub.get(f"/vehicle/{vid}/report", headers=_PUB)
        assert r.status_code == 200, (vid, r.status_code)
        return r.text, cap[-1]
    return _get


def _sec01(html):
    i = html.index('id="sec01"')
    return html[i:html.index('id="sec02"', i)]


def _numeric(html, name):
    """한 렌더에 축 `name` 의 숫자 점수가 서는 자리 — 표 줄 · SVG 라벨(aria) · 툴팁 데이터(hxData)."""
    hits = [s for n, s in _ROW.findall(html) if n == name and s.strip().isdigit()]
    hits += re.findall(re.escape(name) + r"\s*\d+", html)
    m = re.search(r'<script type="application/json" id="hxData">(.*?)</script>', html, re.S)
    if m:
        hits += [a["score"] for a in json.loads(m.group(1)) if a.get("name") == name and a.get("score") is not None]
    return hits


@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD"])
@pytest.mark.parametrize("admin", [False, True])
def test_리포트_01_은_판정과_어긋나는_시세_점수를_그리지_않는다(cars, get, monkeypatch, vid, admin):
    html, ctx = get(vid, admin)
    s1 = _sec01(html)
    assert SAYS in html, "판정 문장이 서야 '함께 0'이 의미가 있다"
    assert ctx["hexa"]["n_avail"] == 2 and ctx["bidst"]["no_estimate"] is True
    assert _numeric(html, "가격 메리트") == [], "가격 메리트 숫자 점수"
    assert _numeric(html, "잔존가치") == [], f"'{SAYS}'와 숫자 잔존가치가 한 렌더에 함께 섰다"
    for name in ("시세 신뢰도", "유동성"):
        assert not [s for n, s in _ROW.findall(html) if n == name], name
    assert 'class="hexa"' not in s1 and "축 산출" not in s1, "남는 축이 둘이면 기존 게이트가 육각형을 접는다"
    # 공허 통과 방지 — 옛 동작이면 같은 렌더에 육각형·숫자 점수가 판정 문장과 함께 선다(이 검출기가 그 장면을 잡는다)
    old_html, old_ctx = _old(monkeypatch, lambda: get(vid, admin))
    assert 'class="hexa"' in _sec01(old_html) and old_ctx["hexa"]["n_avail"] == 6
    assert _numeric(old_html, "가격 메리트") and _numeric(old_html, "잔존가치") and SAYS in old_html
    if vid == "FLOOD":
        assert "6/6축 산출" in old_html and "100" in _numeric(old_html, "가격 메리트")
        assert "38" in [s for n, s in _ROW.findall(old_html) if n == "잔존가치"], "34408 장면: 잔존가치 38"


@pytest.mark.parametrize("admin", [False, True])
def test_리포트에서_빠지는_것은_육각형_블록뿐이다(cars, get, monkeypatch, admin):
    """34408 형: 옛 렌더와 새 렌더의 차이는 한 덩어리 삭제 — 육각형 블록(여섯 축 줄 포함)뿐이고 나머지는 바이트 그대로다."""
    new = get("FLOOD", admin)[0].splitlines()
    old = _old(monkeypatch, lambda: get("FLOOD", admin))[0].splitlines()
    ops = [o for o in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if o[0] != "equal"]
    assert len(ops) == 1 and ops[0][0] == "delete", ops
    gone = "\n".join(old[ops[0][1]:ops[0][2]])
    assert gone.lstrip().startswith('<div class="hexa">') and gone.count('<span class="nm">') == 6, gone[:200]
    assert "입찰 중단 기준" not in gone and SAYS not in gone, "육각형 밖이 함께 빠졌다"


# ── 대조군: 육각형·리포트 바이트 그대로 ──────────────────────────────────────────
# 이번 변경 전 코드(web/service.py md5 74de9b9b)로 같은 픽스처를 계산한 시세 축 점수 — '옛 동작' 재현에 기대지 않는 닻
_CTRL_MARKET = {
    "BLK": {"price": 17, "conf": 81, "value": 10, "liq": 84},
    "FLOOD_WON": {"price": 71, "conf": 81, "value": 7, "liq": 84},
    "RSL": {"price": 100, "conf": 81, "value": 30, "liq": 84},
}


@pytest.mark.parametrize("vid", ["BLK", "FLOOD_WON", "RSL"])
@pytest.mark.parametrize("private", [False, True])
def test_대조군_육각형은_바이트_그대로다(cars, monkeypatch, vid, private):
    v = cars[vid]
    new, old = _hx(v, include_private=private), _old(monkeypatch, lambda: _hx(v, include_private=private))
    assert _dump(new) == _dump(old), vid
    assert {k: _ax(new)[k]["score"] for k in MARKET} == _CTRL_MARKET[vid], _scores(new)
    assert all(a["note"] != service.HEXA_WITHHELD_NOTE for a in new["axes"])
    if private:
        assert _ax(new)["liq"]["count"] == 363


@pytest.mark.parametrize("vid", ["BLK", "FLOOD_WON", "RSL"])
@pytest.mark.parametrize("admin", [False, True])
def test_대조군_리포트는_바이트_그대로다(cars, get, monkeypatch, vid, admin):
    new, ctx = get(vid, admin)
    old, _ = _old(monkeypatch, lambda: get(vid, admin))
    assert new == old, f"{vid}: 리포트가 바뀌었다"
    assert 'class="hexa"' in _sec01(new) and ctx["hexa"]["n_avail"] >= 5, "대조군이 육각형을 그려야 비교가 의미 있다"
    assert _numeric(new, "가격 메리트"), "대조군의 가격 메리트 점수는 그대로 선다"


# ── 신호의 출처 — 판정 문장과 같은 한 곳 ───────────────────────────────────────────
def test_st_를_넘기면_그_판정을_쓰고_다시_계산하지_않는다(cars, monkeypatch):
    v = cars["FLOOD"]
    st = service.bid_state(v, BT)
    with monkeypatch.context() as m:
        m.setattr(service, "bid_state", lambda *a, **k: pytest.fail("bid_state 를 다시 계산했다"))
        assert _hx(v, st=st)["n_avail"] == 2
        closed = {**st, "state": "closed", "no_estimate": False}
        assert all(_ax(_hx(v, st=closed))[k]["score"] is not None for k in MARKET), "넘긴 판정을 따르지 않았다"
        # 비침수 물건은 st 가 없어도 bid_state 를 계산하지 않는다 — 육각형이 모든 리포트에서 부르는 자리(추가 비용 0)
        assert _hx(cars["RSL"])["n_avail"] == 5
        assert service.estimate_withheld(cars["BLK"]) is False


def test_구조_육각형은_판정_문장과_같은_한_곳을_본다():
    src = inspect.getsource(service.hexagon_scores)
    assert "    if estimate_withheld(v, st):" in src, "육각형의 조건은 판정 문장(plain_verdict)과 같은 estimate_withheld 다"
    assert "flood_hold(" not in src and '"blocked"' not in src, "조건을 따로 적지 않는다"
    assert service.HEXA_MARKET_AXES == ("price", "conf", "value", "liq")
