# -*- coding: utf-8 -*-
"""REC-9 화면 쪽(지시서 2026-10-01-04) — 침수·전손 판정 물건에 예상낙찰가·밴드·입찰 상한선을 그리지 않는다.

2026-09-30 교차검수(34408 — 2025타경34408_1 CLS300 d, 비가드): 빨간 판정 상자가 "잔존 가치를 산정할 수 없어 예상낙찰가·입찰
상한선을 제공하지 않습니다"라고 말한 바로 아래, 리포트 01 이 가장 큰 글자로 예상가 밴드 1,230~1,460만원·중심값을 그렸고
"이미 입찰 상한선을 넘습니다"(침수에는 상한선이 없다)라고 썼다. 상세 히어로·목록 카드·관심 화면도 같은 숫자를 그렸다.

신호는 서버의 `no_estimate` 하나다(service.estimate_withheld — bidst · 관심 화면 행). 값은 그대로 오고 **가리는 것은 템플릿**이다
(backend 명세 §4.4). 이 파일은 네 화면(상세·리포트·목록·관심)의 렌더 HTML 을 본다:
  · 34408 형(저장 '입찰 보류' · 등급 flood · 예상가 있음) — 예상가(원·만 단위 모두)·'입찰 상한선' 금액·'이미 입찰 상한선을 넘습니다' 0,
    대신 판정 문장과 같은 뜻의 자리 표시(ui.withheld · '내지 않음').
  · 키워드로만 보류된 물건(상한선 계산이 된다) — 상한선 금액도 0.
  · 대조군(침수 아닌 blocked) — 그대로(숫자·문장이 남는다). 비침수 물건의 렌더 바이트 불변은 기존 md5 테스트
    (test_rec1_floor_view · test_rec1_r3_view · test_rec1_r4_view · test_panel56)가 지킨다.
판정 기준은 바꾸지 않는다 — 표시만.

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import json
import re

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from web import service

_PUB = {"x-forwarded-for": "203.0.113.9"}
COMPS = [{"price_won": p, "year": 2020, "mileage_km": 60_000, "badge": "-"}
         for p in (30_000_000, 32_000_000, 33_500_000, 34_900_000, 36_000_000, 38_000_000)]


# 재판매 손익분기 산정표(breakdown) — 2회차: 끝줄(= 손익분기 상한)·리포트 10 끝줄이 그려지는 물건이어야 v.upper_bid 대조가 공허하지 않다.
# 34408 은 09-29 백업 값 그대로(34,900,000 − 48,221,000 = −13,321,000). 키워드 보류 물건은 상한가 19,000,000 이 되도록 맞춘 값.
FLOOD_BD = {"기준시세": 34_900_000, "플랫폼": "encar", "플랫폼가중": 1.0, "예상수리비": 500_000, "사고등급": "flood",
            "사고감가율": 1.0, "사고감가": 34_900_000, "리스크프리미엄": 2_443_000, "취득세": 2_443_000, "고정부대비": 500_000,
            "마진": 5_235_000, "상태정비추가": 2_200_000, "상태사유": ["관리·외관 불량", "시동·운행 불가 언급"], "표본수": 5}
KW_BD = {"기준시세": 30_000_000, "플랫폼": "encar", "플랫폼가중": 1.0, "예상수리비": 1_800_000, "사고등급": "none",
         "사고감가율": 0.0, "사고감가": 0, "리스크프리미엄": 2_100_000, "취득세": 2_100_000, "고정부대비": 500_000,
         "마진": 4_500_000, "상태정비추가": 0, "표본수": 12}


def _flood(mk, vid="FLOOD", **kw):
    """34408 값 그대로(09-29 백업 — backend test_rec9_no_estimate 의 FLOOD) — 날짜만 오늘 기준."""
    row = dict(maker="Mercedes-Benz", model="Mercedes-Benz CLS300 d", year=2020, court="광주지방법원",
               appraisal_value=30_000_000, min_sale_price=10_752_000, fail_count=4, sale_date=_d(6),
               sale_time="09:55", judgment="입찰 보류", accident_grade="flood", runnable="no",
               median_price=34_900_000, sample_count=5, market_confidence=53, market_confidence_label="보통",
               upper_bid=-13_321_000, lower_bound=10_752_000, photo_count=8, mileage_km=65_683,
               breakdown=json.dumps(FLOOD_BD, ensure_ascii=False))
    row.update(kw)
    return mk(vid, **row)


@pytest.fixture
def cars(mk):
    return {
        "FLOOD": _flood(mk),
        # 감정서 키워드로만 '입찰 보류'(등급 무사고) — 상한선 계산이 된다(bidst.max_bid 있음)
        "KWFLOOD": mk("KWFLOOD", model="그랜저 IG", appraisal_value=30_000_000, min_sale_price=10_000_000, fail_count=2,
                      judgment="입찰 보류", accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0},
                      median_price=30_000_000, upper_bid=19_000_000, breakdown=json.dumps(KW_BD, ensure_ascii=False)),
        # 등급 flood 인데 저장 판정이 다른 물건(09-29 사본 침수 9대 중 5대가 그렇다) — 산정 근거 갈래도 신호로 간다
        "FLDR2": mk("FLDR2", model="싼타페 TM", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="유찰 대기",
                    accident_grade="flood", median_price=30_000_000, upper_bid=19_000_000,
                    breakdown=json.dumps(KW_BD, ensure_ascii=False)),
        # 대조군 — 침수 아닌 '이번 회차 입찰 부적합'(blocked)
        "BLK": mk("BLK", model="아반떼 CN7", appraisal_value=20_000_000, min_sale_price=16_000_000, median_price=16_600_000,
                  judgment="유찰 대기"),
    }


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

    def _get(url, admin=False):
        cap.clear()
        r = c.get("http://localhost" + url) if admin else c.get(url, headers=_PUB)   # XFF 없음 + 루프백 = 관리자
        assert r.status_code == 200, (url, r.status_code)
        return cap[-1], r.text
    return _get


SCREENS = {   # 화면 → 그 물건 하나만 그리는 URL
    "detail": "/vehicle/{id}",
    "report": "/vehicle/{id}/report",
    "list": "/vehicles?q={q}&sort=expected",
    "watch": "/watchlist?ids={id}",
}
QUERY = {"FLOOD": "CLS300", "KWFLOOD": "KWFLOOD", "FLDR2": "FLDR2", "BLK": "BLK"}


def _url(screen, vid):
    return SCREENS[screen].format(id=vid, q=QUERY[vid])


def _body(html: str) -> str:
    """스타일·스크립트를 뺀 HTML(속성·title 툴팁 포함 — 툴팁의 숫자도 숫자다)."""
    return re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)


def _forms(x, token=True):
    """한 금액이 화면에 나오는 모양: 원(13,100,000) · 만(1,310만) · 만 단위 정수 토큰(1310 — 리포트 01 밴드·스펙트럼 핀).
    정수 토큰은 그 모양으로 찍히는 금액(예상가·상한선)에만 건다 — 작은 금액의 토큰(130)은 SVG 좌표 등과 겹쳐 오탐이 된다."""
    from web.app import _man, _won
    out = [_won(x), _man(x)]
    if token:
        out.append(re.compile(r"(?<![\d,.])" + str(int(round(x / 10000))) + r"(?![\d,])"))
    return out


def _hits(html, amounts):
    body = _body(html)
    out = []
    for x, token in amounts:
        for f in _forms(x, token):
            if (f.search(body) if hasattr(f, "search") else f in body):
                out.append((x, getattr(f, "pattern", f)))
    return out


def _withheld_amounts(v):
    """그 물건 화면에 나오면 안 되는 금액 [(금액, 만 단위 토큰도 보나)] — 예상가(중심·밴드)·상한선 + 그 값에 기댄 계산(총비용·여유).

    REC-9 2회차(qa §7 · app-design-expert 고칠 것 1): **재판매 상한가(v.upper_bid)** 도 센다. 1회차 헬퍼가 세지 않아
    키워드로만 보류된 물건(양수 상한가 19,000,000)이 상세 산정표 끝줄·목록 lg 표·관심 표에 그대로 서도 빨간불이 안 켜졌다.
    0원 이하(34408 -13,321,000)는 '산정 불가', 양수는 '내지 않음'으로 가린다 — 어느 쪽이든 숫자는 0 이어야 한다."""
    cfg = service.load_config()
    band = service.expected_band(v, BT) or {}
    st = service.bid_state(v, BT)
    exp = band.get("price") or service.expected_for(v, BT)
    out = {(a, True) for a in (band.get("price"), band.get("lo"), band.get("hi"), service.expected_for(v, BT), st.get("max_bid"),
                               v.get("upper_bid")) if a}
    if exp:
        allin = service.allin_estimate(exp, cfg, v) or {}
        rep = service.report_data(v, cfg, BT) or {}
        out |= {(a, False) for a in (allin.get("total"), (rep.get("allin_ref") or {}).get("total"), exp - v["min_sale_price"]) if a}
    return sorted(out)


# ── 전제 — 공허 통과 방지 ─────────────────────────────────────────────────
def test_전제_신호와_가릴_숫자가_실제로_있다(cars):
    for vid in ("FLOOD", "KWFLOOD", "FLDR2"):
        st = service.bid_state(cars[vid], BT)
        assert st["no_estimate"] is True and st["state"] == "blocked", (vid, st["state"], st["label"])
        assert service.expected_band(cars[vid], BT), f"{vid}: 예상가 밴드 값은 서버가 그대로 보낸다 — 가릴 숫자가 있어야 재현이다"
    band = service.expected_band(cars["FLOOD"], BT)
    assert band["lo"] < band["price"] < band["hi"]
    assert service.bid_state(cars["FLOOD"], BT)["max_bid"] is None, "등급 flood 는 상한선이 없다(34408)"
    assert service.bid_state(cars["KWFLOOD"], BT)["max_bid"], "키워드로만 보류된 물건은 상한선 값이 온다 — 그래서 상한선도 가린다"
    blk = service.bid_state(cars["BLK"], BT)
    assert blk["state"] == "blocked" and blk["no_estimate"] is False and blk["max_bid"] and service.expected_band(cars["BLK"], BT)
    assert len(_withheld_amounts(cars["FLOOD"])) >= 5
    for vid in ("FLOOD", "KWFLOOD", "FLDR2"):   # 2회차 — 재판매 상한가가 실제로 세는 금액에 들어 있고, 그 값이 서는 산정표가 있다(공허 통과 방지)
        assert (cars[vid]["upper_bid"], True) in _withheld_amounts(cars[vid]), vid
        bd = cars[vid]["breakdown"]
        bd = json.loads(bd) if isinstance(bd, str) else bd
        steps = ("예상수리비", "상태정비추가", "사고감가", "리스크프리미엄", "취득세", "고정부대비", "마진")
        assert bd["기준시세"] - sum(bd[k] for k in steps) == cars[vid]["upper_bid"], f"{vid}: 산정표가 상한가로 닫힌다"


# ── 34408 형 · 키워드 보류 — 네 화면에 숫자 0 ──────────────────────────────
@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD", "FLDR2"])
@pytest.mark.parametrize("screen", list(SCREENS))
def test_침수전손_판정_물건은_예상가와_상한선을_그리지_않는다(cars, get, screen, vid):
    ctx, html = get(_url(screen, vid))
    rows = ctx.get("rows")
    if rows is not None:
        assert [r["id"] for r in rows] == [vid], "그 물건 하나만 그린 화면이어야 대조가 선다"
    hits = _hits(html, _withheld_amounts(cars[vid]))
    assert not hits, f"{screen}/{vid}: 가린 금액이 화면에 있다 {hits}"
    assert "이미 입찰 상한선을 넘습니다" not in html
    if screen in ("list", "watch"):
        assert "내지 않음" in html and "침수·전손 의심" in html, "숫자 대신 같은 뜻의 짧은 자리 표시"
        assert not re.search(r"입찰 상한 <b", html), "목록 카드의 '입찰 상한' 줄"


def test_상세_히어로와_추천_입찰_전략(cars, get):
    _, html = get("/vehicle/FLOOD")
    assert "AI 예상낙찰가 · 입찰 상한선" in html
    assert '<span class="whitespace-nowrap">침수·전손 의심 —</span> <span class="whitespace-nowrap">내지 않습니다</span>' in html
    assert "예상낙찰가·입찰 상한선을 제공하지 않습니다" in html, "판정 상자 문장은 그대로"
    for gone in ("소매 시장 대비 차익", "예상낙찰가(균형) 산정식", "낙찰 시 최소 예상비용", "산정 기준</span>", "nc-gauge-judge"):
        assert gone not in html, gone
    assert "이 물건에는 입찰가를 제시하지 않습니다." in html and "침수·전손 의심 물건이라 잔존 가치를 산정할 수 없습니다." in html
    assert "⛔ 입찰 보류 — 침수·전손 의심" in html, "입찰가 산정 근거 칸은 산정식 대신 보류 상자"


def test_키워드로만_보류된_물건도_같은_사유를_말한다(cars, get):
    """예전 '추천 입찰 전략' 사유 조건은 등급(flood)이라 이 물건엔 '최저매각가가 손익분기를 넘어'라는 다른 이유가 나왔다
    — 최저가 1,000만 ≤ 상한선이라 그 이유는 거짓이었다."""
    _, html = get("/vehicle/KWFLOOD")
    assert "침수·전손 의심 물건이라 잔존 가치를 산정할 수 없습니다." in html
    assert "써낼 수 있는 모든 금액이 손해입니다" not in html


def test_저장_판정이_다른_침수_물건도_보류_상자로_간다(cars, get):
    _, html = get("/vehicle/FLDR2")
    assert "⛔ 입찰 보류 — 침수·전손 의심" in html
    assert "재판매 손익분기 <span class=\"text-mut\">(참고 — 되팔이 목적)</span>" not in html and "실제 입찰가는 위" not in html


def test_리포트_01과_06_07_08_10(cars, get):
    _, html = get("/vehicle/FLOOD/report")
    s01 = html[html.index('id="sec01"'):html.index('id="sec02"')]
    assert '<div class="v-label">예상낙찰가 · 입찰 상한선</div>' in s01 and '<div class="v-held">' in s01
    assert "v-band" not in s01, "01 의 가장 큰 글자(밴드·상한선) 자리"
    assert "침수·전손 의심이라 입찰 보류입니다" in s01 and "이미 입찰 상한선을 넘습니다" not in s01
    for gone in ("대비 이 물건의 예상낙찰가는", "준비할 현금은 총", "밴드가 조정될 수 있음", 'class="spectrum"'):
        assert gone not in s01, gone
    for gone in ('class="rowcard cost"', 'class="rowcard sim"', 'class="matrix"', "예상낙찰가</b><small>분위수 밴드"):
        assert gone not in html, gone
    for keep in ("낙찰가를 가정한 총 취득원가도 계산하지 않습니다(01).", "낙찰가별 수익 시뮬레이션도 싣지 않습니다(01).",
                 "낙찰가를 고정한 민감도 분석도 싣지 않습니다(01).", "예상낙찰가와 그 산정식을 싣지 않습니다(01)."):
        assert keep in html, keep
    for no in ("06", "07", "08", "10"):
        assert f'id="sec{no}"' in html, "섹션 번호는 건너뛰지 않는다 — 왜 비었는지를 본문에 적는다(sec-empty 규칙)"
    # 05 안내문이 가리키던 것(이 물건의 예상낙찰가 산출 · 01 의 시세중앙값)은 이제 없다 — 없는 것을 가리키지 않는다
    assert "이 물건의 예상낙찰가는 이 표 대신" not in html and "소매 시세중앙값은 <b>01 핵심 결론</b>에 있습니다" not in html


def test_리포트_재판매_기준선_문장도_예상가에_기대면_그리지_않는다(cars, get):
    """키워드 보류 물건(상한가 19,000,000 — 픽스처 값)은 '마진 확보선 … 이하가 기준'·'예상낙찰가가 마진 확보선을 초과' 갈래로
    갈 수 있다. 잔존 가치를 못 매기는 물건에 되팔이 기준선을 주지 않는다. 0원 이하(산정 불가) 문장은 사실이라 남는다(34408)."""
    _, kw = get("/vehicle/KWFLOOD/report")
    s01 = kw[kw.index('id="sec01"'):kw.index('id="sec02"')]
    assert "마진 확보선" not in s01 and "재판매 부적합 신호" not in s01
    _, fl = get("/vehicle/FLOOD/report")
    assert "재판매 목적이면 <b>산정 불가 — 상한가 0원 이하</b>" in fl


# ── 대조군 — 침수 아닌 blocked 는 그대로 ─────────────────────────────────────
@pytest.mark.parametrize("screen", list(SCREENS))
def test_대조군_비침수_부적합은_숫자를_그대로_그린다(cars, get, screen):
    _, html = get(_url(screen, "BLK"))
    v = cars["BLK"]
    exp = service.expected_for(v, BT)
    st = service.bid_state(v, BT)
    from web.app import _won
    if screen != "report":
        assert _won(exp) in html, f"{screen}: 예상낙찰가 숫자"
    if screen in ("detail", "list"):
        assert _won(st["max_bid"]) in html, f"{screen}: 입찰 상한선 금액"
    if screen == "report":
        assert "이미 입찰 상한선을 넘습니다" in html and 'class="v-band num"' in html and 'class="rowcard cost"' in html
        assert '<div class="v-held">' not in html
        assert "이 물건의 예상낙찰가는 이 표 대신" in html and "소매 시세중앙값은 <b>01 핵심 결론</b>에 있습니다" in html
    assert "내지 않음" not in html and "내지 않습니다</span>" not in html


# ── (관리자 전용) 동급 매물 분포 — 예상낙찰가 표식·±오차 음영이 이 차트의 주제다 ─────────
def test_관리자_분포_차트도_침수는_그리지_않는다(mk, get):
    fl = _flood(mk, "FLOODC", comps=COMPS)
    ok = mk("RSLC", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="입찰 검토 가능",
            median_price=30_000_000, upper_bid=19_000_000, comps=COMPS)
    for v in (fl, ok):   # 전제 — 둘 다 분포 재료가 있다(가리지 않으면 그려진다)
        assert service.price_distribution(v, service.expected_for(v, BT), 10.0), v["id"]
    _, d_fl = get("/vehicle/FLOODC", admin=True)
    _, r_fl = get("/vehicle/FLOODC/report", admin=True)
    _, d_ok = get("/vehicle/RSLC", admin=True)
    _, r_ok = get("/vehicle/RSLC/report", admin=True)
    assert "동급 매물 시세 분포" in d_ok and "실매물 시세 분포" in r_ok, "대조군(관리자)에는 그려진다"
    assert "동급 매물 시세 분포" not in d_fl and "실매물 시세 분포" not in r_fl
