# -*- coding: utf-8 -*-
"""REC-9 3.5회차 화면 쪽(지시서 2026-10-01-24) — 3회차 교차검수(design-critic 고칠 것 1~3 · app-design-expert 고칠 것 1·2 · qa 비차단 1·2)가
남긴 자리. 판정 기준은 바꾸지 않는다 — 이미 정해진 판정(service.bid_state · estimate_withheld = `no_estimate`)을 화면이 같은 말로 하게 한다.

F1 최저가 미확인(floor_guard) 침수·전손 판정 물건(라이브 2025타경51723_1·2026타경93_1 은 공고 전 갈래)
   · 상세 '가격 확인 필요' 칸 — 추정 최저가 문장 셋을 그리지 않고, 뒤 줄은 "최저가를 확인해도 … 입찰 보류입니다."로 끝난다
     ('입찰 전 … 확인하세요'·'다음 기일이 잡히면 … 확인하세요' 없음). 첫 사실 줄은 남는다.
   · 상세 '이번 기일 예상 최저가 (공고 확인 전)' 행 없음
   · 리포트 01 첫 요점 — 정지 문장 먼저(Steward 문구)
F2 상단 배너(시세 없음)의 no_estimate 갈래 — 같은 페이지 추천 전략 보류 상자와 같은 로즈 면·본문색, title 없음
F3 산정 근거 보류 상자 머리 — 로즈 한 단계 진하게(대비 AA)
F4 하우스 낱말 — 배너 · 보류 상자 본문(Steward 문구)
F7 관심 모바일 카드 최저매각가 로즈 · 목록 lg 표 시세 숫자 — no_estimate 행은 중립
대조군 — 다른 사유의 가드 물건(사유 없음·시동 불가·신뢰도 낮음·시세 없음·동급 시세 없음·기일 지남)과 정상 행: 3회차 작업 트리
(지시서 2026-10-01-20 산출, detail 6ba93665 · report 4d52fc52 · vehicles 03b004dc · watchlist 5226ba81)에서 잰 조각 md5 그대로.
날짜는 고정값(2999-01-01 · 2020-01-01)이라 md5 가 날마다 바뀌지 않는다.

각 테스트는 **전제를 먼저 단언**한다(그 갈래가 실제로 렌더되는 물건인지) — 아니면 공허 통과다. 이름에 '대조군'이 붙은 테스트는
바뀌면 안 되는 렌더를 단언한다(지시서 집계에서 뺀다). 외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import hashlib
import re

import pytest

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec9_frontend import _flood, cars, get  # noqa: F401 — 1회차 픽스처(FLOOD 34408형 등)
from tests.test_rec9_r2_frontend import more  # noqa: F401 — 2회차 픽스처(FLLOW 시세 없는 침수 · LOW 시세 없는 비침수 · POS)
from tests.test_rec9_r3_frontend import r3  # noqa: F401 — 3회차 픽스처(FLMKT · MKTCTL)
from web import service
from web.app import _won

FAR, PAST = "2999-01-01", "2020-01-01"
RATES = {"by_court": {"수원지방법원": {"ratio": 0.7, "n": 18, "share": 1.0}}, "global": 0.7, "n": 100, "observed": {0.7: 100}}
HOLD_FLOOD = "최저가를 확인해도 침수·전손 의심이라 입찰 보류입니다."
# Steward 확정 문구(지시서 2026-10-01-24) — 글자 그대로
LI_F1 = ('<li>표시된 최저매각가 <b class="num">7,000,000원</b>(이번 회차 확인 전) — '
         '<b style="color:var(--red)">침수·전손 의심이라 입찰 보류입니다</b></li>')
BANNER_F4 = ('<b>침수·전손 의심</b> 물건이라 예상낙찰가·입찰 상한선을 내지 않습니다 — '
             '<b class="whitespace-nowrap">입찰하지 마세요</b>.')
HOLD_F4 = ('<div class="text-sm text-mut px-4">감정평가서 등 법원 자료에서 침수·전손 기재가 감지되었습니다. 예상낙찰가·입찰 상한선을 내지 않습니다 —\n'
           '          <span class="whitespace-nowrap">입찰하지 마세요</span>.</div>')
HOLD_F3 = '<div class="text-xs text-rose-700 mb-1 font-semibold">⛔ 입찰 보류 — 침수·전손 의심</div>'
BOX_ROSE = '<div class="bg-rose-50 border border-rose-200 rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">'
BOX_PLAIN = '<div class="bg-surface border border-line rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">'


@pytest.fixture
def g(mk, monkeypatch):
    """가드(유찰 2회인데 최저가가 감정가의 70% = 저감 1회분 → 한 단계 지연) 물건들. 저감률은 고정(이 법원 0.7) — 추정값 7,000,000×0.7."""
    monkeypatch.setattr(service, "court_reduction_rates", lambda: RATES)
    base = dict(appraisal_value=10_000_000, min_sale_price=7_000_000, fail_count=2, sale_date=FAR, judgment="유찰 대기")
    # 기일이 지난 가드는 1회 지연(최저가 = 감정가 · 유찰 ≥1, service.stale_floor)뿐이다 — 다회차 지연 신호는 기일이 남은 물건만 본다
    past = dict(appraisal_value=10_000_000, min_sale_price=10_000_000, fail_count=1, sale_date=PAST, auction_result="유찰",
                judgment="유찰 대기")
    nom = dict(median_price=None, market_confidence=None, market_confidence_label=None)
    return {
        # 침수 · 가드 · 공고 후(이번 기일 남음 — 추정 최저가·'입찰 전 … 확인하세요'가 서던 모양) · 시세 없음
        "GFLP": mk("GFLP", accident_grade="flood", **nom, **base),
        # 같은 모양 · 시세 있음(리포트 본문이 선다)
        "GFLM": mk("GFLM", accident_grade="flood", median_price=9_000_000, upper_bid=3_000_000, **base),
        # 침수 · 가드 · 공고 전(기일 지남 · 새 기일 미정 — 라이브 51723·93 모양: 최저가 = 감정가 · 유찰 1)
        "GFLN": mk("GFLN", accident_grade="flood", **nom, **past),
        # 대조군 — 가드인데 사유가 없거나 다르다(바이트 그대로여야 한다)
        "GLAG": mk("GLAG", accident_grade="accident", median_price=20_795_000, upper_bid=7_525_950, **base),
        "GSTOP": mk("GSTOP", runnable="no", median_price=4_300_000, upper_bid=1_000_000, **base),
        "GLOWC": mk("GLOWC", median_price=18_000_000, upper_bid=9_000_000, market_confidence=30, market_confidence_label="낮음",
                    **base),
        "GNOMED": mk("GNOMED", **nom, **base),
        "GNOMKT": mk("GNOMKT", model="굴착기", **nom, **base),
        "GPAST": mk("GPAST", median_price=20_795_000, upper_bid=7_525_950, **past),
    }


def _guard_block(html):
    """상세 물건 정보의 '가격 확인 필요' 칸부터 '매각 일시' 행 앞까지(추정 행 · 입찰 상한선 행 포함)."""
    i = html.index('<dt class="text-amber-800">가격 확인 필요</dt>')
    return html[i:html.index('<dt class="text-mut"><span class="gloss " tabindex="0" role="button" aria-label="매각 일시', i)]


def _amber(html):
    b = _guard_block(html)
    return b[:b.index("</dd>") + 5]


def _text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


def _first_li(html):
    s = html[html.index('id="sec01"'):html.index('id="sec02"')]
    i = s.index('<ul class="vpts">')
    return s[i:s.index("</li>", i) + 5]


def _banner(html):
    i = html.index('rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">')
    i = html.rindex("<div", 0, i)
    return html[i:html.index("\n</div>", i)]


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ── F1 — 상세 '가격 확인 필요' 칸 · '이번 기일 예상 최저가' 행 ──────────────────────────────
@pytest.mark.parametrize("vid,pending", [("GFLP", True), ("GFLM", True), ("GFLN", False)])
def test_F1_가드_침수차_가격_확인_칸은_정지_문장으로_끝난다(g, get, vid, pending):
    ctx, html = get(f"/vehicle/{vid}")
    fg = ctx["floor_guard"]
    assert ctx["bidst"]["no_estimate"] and fg and fg["hold"] == "flood", "전제 — 최저가 미확인 · 침수·전손 판정"
    assert fg["pending"] is pending, "전제 — 공고 후(이번 기일 남음) / 공고 전(기일 지남) 갈래"
    if pending:
        assert fg["est"] and fg["est"]["price"] == 4_900_000, "전제 — 예전엔 '약 4,900,000원(추정)'·'이번 기일 예상 최저가' 행이 섰다"
    a = _amber(html)
    t = _text(a)
    first = ("유찰 2회인데 최저가가 감정가의 70%(저감 1회분)라 직전 회차 값으로 보입니다." if pending
             else "유찰 1회인데 최저가가 감정가의 100%(저감 0회분)라 직전 회차 값으로 보입니다.")
    assert t.startswith("가격 확인 필요 " + first), "첫 사실 줄은 남는다 — " + t
    assert t.endswith(HOLD_FLOOD), t
    assert a.endswith(f'<span class="block mt-1">{HOLD_FLOOD}</span></dd>'), "뒤 줄은 정지 문장 하나로 끝난다(뒤 공백 없이)"
    for gone in ("(추정)", "추정하지 않습니다", "입찰 전", "다음 기일이 잡히면", "판정 보류가 풀린 뒤에", "확인 전까지"):
        assert gone not in t, gone
    assert "이번 기일 예상 최저가" not in html and "4,900,000" not in html


def test_F1_리포트_01_첫_요점은_정지_문장이_먼저(g, get):
    ctx, html = get("/vehicle/GFLM/report")
    assert ctx["report"] and ctx["bidst"]["no_estimate"] and ctx["floor_guard"] and ctx["floor_guard"]["est"], \
        "전제 — 본문 있는 리포트 · 가드 · 추정값 재료 있음(예전엔 가드 갈래가 첫 요점을 가져갔다)"
    li = _first_li(html)
    assert li == '<ul class="vpts">\n          ' + LI_F1
    s = _text(html[html.index('id="sec01"'):html.index('id="sec02"')])
    for gone in ("(추정)", "입찰 전 법원경매정보", "다음 기일이 잡히면", "이번 회차 최저가 확인 필요"):
        assert gone not in s, gone


@pytest.mark.parametrize("vid", ["GLAG", "GSTOP", "GLOWC", "GNOMED", "GNOMKT", "GPAST"])
def test_F1_대조군_다른_사유의_가드_물건은_3회차_바이트_그대로(g, get, vid):
    ctx, html = get(f"/vehicle/{vid}")
    assert ctx["floor_guard"] and not ctx["bidst"]["no_estimate"], "전제 — 가드 · 침수·전손 판정 아님"
    assert ctx["floor_guard"]["hold"] == {"GLAG": None, "GSTOP": "stop", "GLOWC": "lowconf", "GNOMED": "nomed", "GNOMKT": "nomarket",
                                          "GPAST": None}[vid]
    assert _md5(_guard_block(html)) == SNAP_DETAIL[vid], f"{vid}: 3회차와 다른 렌더 — {_text(_guard_block(html))[:200]}"


@pytest.mark.parametrize("vid", ["GLAG", "GSTOP", "GLOWC", "GPAST"])
def test_F1_대조군_다른_사유의_가드_리포트_첫_요점은_3회차_바이트_그대로(g, get, vid):
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["report"] and ctx["floor_guard"] and not ctx["bidst"]["no_estimate"], "전제 — 본문 있는 가드 리포트"
    assert _md5(_first_li(html)) == SNAP_LI[vid], f"{vid}: {_text(_first_li(html))[:200]}"


def test_F1_대조군_가드_아닌_침수차_리포트_첫_요점은_예전_문장(cars, get):
    ctx, html = get("/vehicle/FLOOD/report")
    assert ctx["bidst"]["no_estimate"] and not ctx["floor_guard"], "전제 — 가드 아닌 침수·전손 판정"
    assert _first_li(html) == ('<ul class="vpts">\n          <li>현 최저매각가 <b class="num">10,752,000원</b> — '
                               '<b style="color:var(--red)">침수·전손 의심이라 입찰 보류입니다</b></li>')


# ── F2·F4 — 상단 배너 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLLOW", "GFLP", "GFLN"])
def test_F2_F4_배너는_로즈_면에_하우스_낱말(more, g, get, vid):
    ctx, html = get(f"/vehicle/{vid}")
    v = {**more, **g}[vid]
    assert v["median_price"] is None and ctx["bidst"]["no_estimate"], "전제 — 배너가 서는 침수·전손 판정 물건"
    bn = _banner(html)
    assert bn.startswith(BOX_ROSE + '\n  <div class="text-sm text-rose-800">\n    ' + BANNER_F4), \
        "로즈 면 · 본문 로즈 · 상태값 툴팁(title) 없음 · 하우스 낱말 — " + bn[:300]
    for gone in ("시세·입찰가", "아직", "현재 <b", "상태입니다", "수입·상용/특수차", "text-mut", "bg-surface"):
        assert gone not in bn, gone


def test_F2_관리자_분석_버튼은_로즈_상자_안에_그대로(mk, get):
    mk("FLADM", model="포터 II", appraisal_value=15_000_000, min_sale_price=12_500_000, fail_count=0, judgment="시세 신뢰도 낮음, 수동 검토",
       accident_grade="flood", market_confidence_label=None, market_confidence=None, doc_id="B000210" + "20250130012085" + "1")
    ctx, html = get("/vehicle/FLADM", admin=True)
    assert ctx["can_analyze"] and ctx["bidst"]["no_estimate"], "전제 — 관리자 · 분석 가능 · 침수·전손 판정"
    bn = _banner(html)
    assert bn.startswith(BOX_ROSE)
    assert '<form method="post" action="/vehicle/FLADM/analyze"' in bn and "이 물건 분석 (약 10초)</button>" in bn, "버튼 조건은 그대로"


def test_F2_대조군_시세_없는_비침수_배너는_바이트_그대로(more, get):
    ctx, html = get("/vehicle/LOW")
    assert more["LOW"]["median_price"] is None and not ctx["bidst"]["no_estimate"], "전제"
    bn = _banner(html)
    assert bn.startswith(BOX_PLAIN + '\n  <div class="text-sm text-mut" title="완료">\n    현재 <b class="text-txt">')
    assert _md5(bn) == SNAP_BANNER["LOW"], bn


# ── F3·F4 — 산정 근거 보류 상자 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLLOW", "GFLP", "GFLN"])
def test_F3_F4_보류_상자_머리는_진한_로즈_본문은_하우스_낱말(more, g, cars, get, vid):
    ctx, html = get(f"/vehicle/{vid}")
    assert ctx["bidst"]["no_estimate"], "전제"
    i = html.index('<h3 class="text-lg font-semibold mb-3">입찰가 산정 근거</h3>')
    b = html[i:i + 3000]
    assert HOLD_F3 in b and HOLD_F4 in b
    for gone in ("text-rose-600", "자동 산정을 제공하지", "감정평가서에 침수·전손 이력이"):
        assert gone not in b, gone


def test_F3_F4_34408형도_같은_상자(cars, get):
    ctx, html = get("/vehicle/FLOOD")
    assert ctx["bidst"]["no_estimate"] and cars["FLOOD"]["median_price"], "전제 — 시세 있는 침수차(배너 없음)"
    assert BOX_ROSE not in html and BOX_PLAIN not in html, "시세가 있으면 상단 배너는 서지 않는다"
    assert HOLD_F3 in html and HOLD_F4 in html and "자동 산정을 제공하지" not in html


# ── F7 — 관심 모바일 카드 · 목록 lg 시세 숫자 ─────────────────────────────────────────────
def _card_min(html, vid):
    cards = html[html.index('<div class="lg:hidden divide-y divide-line">'):]
    card = re.search(r'<a href="/vehicle/' + vid + r'".*?</a>', cards, re.S).group(0)
    m = re.search(r'<div class="text-\[10px\] text-mut">최저매각가</div><div class="nc-price font-mono whitespace-nowrap ([^"]+)"', card)
    assert m, f"관심 카드 {vid} 최저매각가"
    return m.group(1)


def test_F7_관심_모바일_카드_침수차는_로즈가_없다(cars, get):
    v = cars["FLOOD"]
    ctx, html = get("/watchlist?ids=FLOOD")
    row = ctx["rows"][0]
    assert row["no_estimate"] and not row["floor_check"] and v["upper_bid"] and v["min_sale_price"] > v["upper_bid"], \
        "전제 — 예전엔 '최저가 > 상한가'로 로즈였다(09-29 사본 34408 과 같은 모양)"
    assert _card_min(html, "FLOOD") == "text-mut"


def test_F7_대조군_관심_모바일_카드_비침수는_로즈_그대로(more, get):
    pos = more["POS"]
    ctx, html = get("/watchlist?ids=POS")
    assert not ctx["rows"][0]["no_estimate"] and not ctx["rows"][0]["floor_check"] and pos["min_sale_price"] > pos["upper_bid"], "전제"
    assert _card_min(html, "POS") == "text-rose-600"


def _row(html, vid):
    m = re.search(r'<tr[^>]*>(?:(?!</tr>).)*?href="/vehicle/' + vid + r'"(?:(?!</tr>).)*</tr>', html, re.S)
    assert m, f"lg 표에 {vid} 행이 없다"
    return m.group(0)


_MED = re.compile(r'<td class="py-2\.5 px-3 text-right whitespace-nowrap">\s*<div class="font-mono ([^"]+)">([\d,]+)')


@pytest.mark.parametrize("vid,q,was", [("FLOOD", "CLS300", "text-txt"), ("FLMKT", "FLMKT", "text-rose-600")])
def test_F7_목록_lg_침수_행의_시세_숫자는_중립(cars, r3, get, vid, q, was):
    v = {**cars, **r3}[vid]
    assert service.bid_state(v, BT)["no_estimate"], "전제"
    assert (v["min_sale_price"] > v["median_price"]) is (was == "text-rose-600"), "전제 — 예전 색(시세 초과면 로즈)"
    _, lst = get(f"/vehicles?q={q}&sort=expected")
    m = _MED.search(_row(lst, vid))
    assert m and m.groups() == ("text-mut", _won(v["median_price"]))


def test_F7_대조군_목록_lg_정상_행의_시세_숫자는_그대로(more, r3, get):
    _, l1 = get("/vehicles?q=POS&sort=expected")
    assert _MED.search(_row(l1, "POS")).groups() == ("text-txt", _won(more["POS"]["median_price"]))
    _, l2 = get("/vehicles?q=MKTCTL&sort=expected")
    assert _MED.search(_row(l2, "MKTCTL")).groups() == ("text-rose-600", "12,000,000")


# ── 대조군 조각 md5 — 3회차 작업 트리(지시서 2026-10-01-20 산출, detail 6ba93665 · report 4d52fc52)에서 이 파일의 픽스처로 잰 값 ──
# 상세 '가격 확인 필요' 칸 ~ '매각 일시' 앞(추정 행 · 입찰 상한선 행 포함). 예: GLAG 는 '…약 4,900,000원(추정)입니다. 입찰 전 … 확인하세요.
# 확인 전까지 예상낙찰가·추천 전략은 내지 않습니다 …' + '이번 기일 예상 최저가 (공고 확인 전) 4,900,000 원' + '입찰 상한선 16,900,000 원'.
SNAP_DETAIL = {
    "GLAG": "24abdc1a1e43d207dcebf6af14d62727",
    "GSTOP": "ad718a5c56c1641a0c9b89c5514fb7f0",
    "GLOWC": "1d7facaf3de68bc1103104c5c1c35e78",
    "GNOMED": "6b4006f2717f305b0737eb86c67469f2",
    "GNOMKT": "2bd66143974bc1c61fa5b5972d1dddbd",
    "GPAST": "3ee586737b3961f6040eabe3ca969ec9",
}
SNAP_LI = {   # 리포트 01 `<ul class="vpts">` ~ 첫 `</li>`
    "GLAG": "c7df1003e1b699bd1a5ad98d17cde655",
    "GSTOP": "c9e430eaa7b3d33642bd8c2e9b603238",
    "GLOWC": "0f5139f8a20cb0cd3a9eeb31797bc90c",
    "GPAST": "b87236f9ca35eb5ebd8c18ad08f10128",
}
SNAP_BANNER = {"LOW": "d79f95471af98ad3f7e9595a88290867"}   # 상단 배너(상태 갈래 — '현재 완료 상태입니다 …' + 수입·상용 안내)
