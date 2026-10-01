# -*- coding: utf-8 -*-
"""REC-9 3회차 화면 쪽(지시서 2026-10-01-20) — 2회차 교차검수(app-design-expert 고칠 것 1·3 · design-critic 고칠 것 1~3 · qa §9)가
남긴 표시 문제. 판정 기준은 바꾸지 않는다 — 이미 정해진 판정(service.bid_state · estimate_withheld = `no_estimate`)을 화면이 같은 말로 하게 한다.

A. 상세 — 시세 없는 침수차(라이브 2025타경12085_1: 등급 flood · 시세 없음 · 매각기일 10-06)에 '입찰하지 마세요'가 한 번도 없었다.
   A1 산정 근거 보류 상자가 '분석 전'·nomarket·'시세 없음' 갈래보다 먼저 · '입찰하지 마세요' 한 덩어리
   A2 상단 배너 '아직 계산되지 않았습니다' → Steward 문구 · '수입·상용/특수차' 안내 없음
   A3 물건 정보 '다음 기일 예상 최저가' 행 없음
B. 리포트 — B1 01 셋째 요점 · B2 '입찰 중단 기준' 상자 색(`stop_active or _noest`)·'(01)' · B3 09 '사고·침수' 칩 · B4 10 ＝줄 작은 설명 ·
   B5 `.stop` 좁은 폭에서 태그·문장 위아래로(CSS 규칙만 여기서 — 폭·줄 수는 브라우저 측정, screenshots/rec9-r3/HEAD.txt)
C. 목록 lg 표 — C1 시세 칸 신뢰도 점 중립 · C2 최저매각가 칸 강조·title 없음(관심 lg 표 같은 패턴 포함)
D. /privacy — `<style>` 안 내부 메모를 Jinja 주석으로(공개 소스에 안 실린다)
E. 테스트 공백 — E1(qa §9-1 · N35·N36) 빌드된 app.css 에 템플릿이 쓰는 유틸리티 · E2(qa §9-2 · N14) 목록 lg 상한가 칸 매각 종료 '—'

각 테스트는 **전제를 먼저 단언**한다(그 갈래가 실제로 렌더되는 물건인지) — 아니면 공허 통과다. 이름에 '대조군'이 붙은 테스트는
바뀌면 안 되는 물건의 렌더를 예전 바이트 그대로 단언한다(지시서 E4 집계에서 뺀다).
외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`(autouse, 시도 기록).
"""
import json
import re
from pathlib import Path

import pytest

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec9_frontend import KW_BD, _flood, cars, get  # noqa: F401 — 1회차 픽스처(FLOOD·KWFLOOD·FLDR2·BLK)
from tests.test_rec9_r2_frontend import NEG_BD, POS_BD, _s01, _stop, _upper, more  # noqa: F401 — 2회차 픽스처(ACC·NEG·POS·FLLOW·LOW)
from web import service
from web.app import _won

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates"

# Steward 확정 문구(지시서 2026-10-01-20) — 글자 그대로.
# 3.5회차(지시서 2026-10-01-24)가 고친 것: 보류 상자 본문·배너 문장은 하우스 낱말(F4), 상자 머리 로즈 한 단계 진하게(F3),
# 배너 굵은 낱말은 로즈 상자 본문색을 물려받는다(F2 — 클래스 없음). 나머지 3.5회차 단언은 tests/test_rec9_r35_frontend.py.
HOLD_A1 = ('<div class="text-sm text-mut px-4">감정평가서 등 법원 자료에서 침수·전손 기재가 감지되었습니다. 예상낙찰가·입찰 상한선을 내지 않습니다 —\n'
           '          <span class="whitespace-nowrap">입찰하지 마세요</span>.</div>')
HOLD_TITLE = '<div class="text-xs text-rose-700 mb-1 font-semibold">⛔ 입찰 보류 — 침수·전손 의심</div>'
BANNER_A2 = ('<b>침수·전손 의심</b> 물건이라 예상낙찰가·입찰 상한선을 내지 않습니다 — '
             '<b class="whitespace-nowrap">입찰하지 마세요</b>.')
LI_B1 = '<li><b>이 결론은 시세가 아니라</b> 감정평가서 등 법원 자료의 <b>침수·전손 기재</b>에 근거합니다.</li>'
STOP_B2 = "<b>침수·전손 의심</b>으로 이미 입찰 중단 기준에 해당합니다 — 이 리포트는 예상낙찰가·입찰 상한선을 내지 않습니다."
SMALL_B4 = "0원 이하 — 되팔이로 목표마진을 남길 낙찰가가 없습니다"
# 예전 문장(대조군이 그대로여야 한다)
NOMED_BOX = ('<div class="text-center bg-sky-50 border border-sky-200 rounded-lg py-4 mb-4">\n'
             '        <div class="text-xs text-sky-700 mb-1 font-semibold">시세 정보 없음 — 수동 확인 필요</div>\n'
             '        <div class="text-sm text-mut px-4">수입·상용/특수차 등 자동 동급 매칭이 되지 않아 시세를 계산하지 못했습니다.\n'
             '          상세(주행거리·사진·사고이력)는 확보되었으니, 중고차 시세를 직접 확인하세요.</div>\n'
             '      </div>')
IMPORT_NOTE = '<span class="text-xs text-mut">수입·상용/특수차는 국산 승용 자동 시세 대상이 아닙니다.</span>'
NEXT = {"price": 8_750_000, "ratio": 0.7, "basis": "global", "n": 0, "court_n": None, "share": None, "alt_price": None}


@pytest.fixture
def r3(mk):
    """3회차에 더하는 물건들 — 값은 사본 실데이터의 모양(이름 옆 주석)."""
    return {
        # 침수 등급 · 분석 전(status 미분석) · 시세 없음 — '분석 전' 갈래가 먼저 잡던 모양
        "FLPRE": mk("FLPRE", model="봉고III", appraisal_value=9_000_000, min_sale_price=9_000_000, fail_count=0, status="미분석",
                    judgment=None, accident_grade="flood", market_confidence_label=None, market_confidence=None),
        # 키워드로만 보류 · 상한가 양수가 최저가 아래(09-29 2026타경20278_1 값: 최저 12,740,000 · 상한 9,920,000 · 시세 19,500,000).
        # 감정가는 유찰 2회 = 저감 2회분(0.7²)이 되게 — 최저가가 이번 회차 값으로 확인되는 물건(관심 표 floor_check 갈래가 아니다)
        "KWOVER": mk("KWOVER", model="토레스", appraisal_value=26_000_000, min_sale_price=12_740_000, fail_count=2, judgment="입찰 보류",
                     accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0}, median_price=19_500_000,
                     upper_bid=9_920_000),
        # 침수 등급 · 최저가가 시세보다 높다(목록 lg 최저매각가 칸이 로즈 + '경매 최저가가 소매 시세보다 높음' 이던 모양)
        "FLMKT": mk("FLMKT", model="스포티지", appraisal_value=20_000_000, min_sale_price=14_000_000, judgment="유찰 대기",
                    accident_grade="flood", median_price=12_000_000, upper_bid=5_000_000, market_confidence_label="보통",
                    market_confidence=55),
        # 대조군 — 비침수 · 최저가가 시세보다 높다(로즈 + title 그대로)
        "MKTCTL": mk("MKTCTL", model="스포티지", appraisal_value=20_000_000, min_sale_price=14_000_000, judgment="유찰 대기",
                     accident_grade="none", median_price=12_000_000, upper_bid=5_000_000, market_confidence_label="보통",
                     market_confidence=55),
        # 대조군 — 비침수 · 보험이력 있음 · 사고 등급 아님(09 칩 초록 '이력상 양호' 그대로)
        "OKINS": mk("OKINS", model="아반떼 CN7", appraisal_value=20_000_000, min_sale_price=10_000_000, judgment="유찰 대기",
                    accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0}, median_price=20_000_000,
                    upper_bid=12_000_000),
        # 매각 종료 · 상한가 0원 이하(qa N14 — 목록 lg 상한가 칸은 '—')
        "CLNEG": mk("CLNEG", model="아반떼 AD", appraisal_value=6_000_000, min_sale_price=4_000_000, fail_count=1, judgment="종결",
                    auction_result="낙찰", winning_price=5_100_000, accident_grade="none", median_price=8_000_000, upper_bid=-500_000,
                    sale_date=_d(-3)),
        # 대조군 — 진행 중 · 같은 0원 이하(목록 lg '산정 불가')
        "OPNEG": mk("OPNEG", model="아반떼 AD", appraisal_value=6_000_000, min_sale_price=4_000_000, fail_count=1, judgment="유찰 대기",
                    accident_grade="none", median_price=8_000_000, upper_bid=-500_000),
    }


def _banner(html):
    """상단 배너(시세 없음) — 상태 갈래는 흰 상자, 침수·전손 판정 갈래는 로즈 상자(3.5회차 F2)."""
    i = html.index('rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">')
    i = html.rindex("<div", 0, i)
    return html[i:html.index("\n</div>", i)]


def _basis(html):
    i = html.index('<h3 class="text-lg font-semibold mb-3">입찰가 산정 근거</h3>')
    return html[i:i + 4000]


def _nm(monkeypatch):
    monkeypatch.setattr(service, "next_min_sale", lambda v, *a, **k: dict(NEXT))


# ── A1 — 상세 '입찰가 산정 근거' 보류 상자가 맨 앞 갈래 ───────────────────────────────
@pytest.mark.parametrize("vid", ["FLLOW", "FLPRE", "FLOOD", "KWFLOOD", "FLDR2"])
def test_A1_침수_전손_보류_상자가_맨_먼저_선다(more, r3, cars, get, vid):
    v = {**more, **r3, **cars}[vid]
    ctx, html = get(f"/vehicle/{vid}")
    assert ctx["bidst"]["no_estimate"] is True and ctx["bidst"]["state"] == "blocked", "전제 — 침수·전손 판정 물건"
    if vid == "FLLOW":
        assert v["median_price"] is None and v["status"] == "완료", "전제 — 시세 없음 · 분석 완료('시세 정보 없음' 갈래가 잡던 모양)"
    if vid == "FLPRE":
        assert v["status"] != "완료", "전제 — 분석 전 갈래가 잡던 모양"
    b = _basis(html)
    assert HOLD_TITLE in b and HOLD_A1 in b, "로즈 보류 상자 · '입찰하지 마세요' 한 덩어리"
    assert re.match(r'<h3 class="text-lg font-semibold mb-3">입찰가 산정 근거</h3>\s*'
                    r'<div class="text-center bg-rose-50 border border-rose-200 rounded-lg py-4 mb-4">\s*' + re.escape(HOLD_TITLE), b), \
        "카드 제목 바로 아래 첫 상자 — 다른 갈래보다 먼저"
    for gone in ("중고차 시세를 직접 확인하세요", "시세 정보 없음 — 수동 확인 필요", "분석 전 — 상단", "입찰하지 마세요.</div>"):
        assert gone not in b, gone
    assert html.count("입찰하지 마세요") >= 1


def test_A1_대조군_시세_없는_비침수는_예전_상자(more, get):
    v = more["LOW"]
    ctx, html = get("/vehicle/LOW")
    assert v["median_price"] is None and not ctx["bidst"]["no_estimate"] and ctx["bidst"]["state"] != "nomarket", "전제"
    b = _basis(html)
    assert NOMED_BOX in b and "⛔ 입찰 보류" not in b


def test_A1_대조군_분석_전_비침수는_예전_상자(mk, get):
    mk("PRECTL", model="봉고III", appraisal_value=9_000_000, min_sale_price=9_000_000, fail_count=0, status="미분석", judgment=None,
       accident_grade="none", market_confidence_label=None, market_confidence=None)
    ctx, html = get("/vehicle/PRECTL")
    assert not ctx["bidst"]["no_estimate"]
    b = _basis(html)
    assert ('<div class="text-center bg-background border border-line rounded-lg py-4 mb-4">\n'
            '        <div class="text-sm text-mut">분석 전 — 상단 [이 물건 분석]으로 산정하세요</div>') in b


# ── A2 — 상단 배너 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLLOW", "FLPRE"])
def test_A2_배너는_아직이라고_말하지_않는다(more, r3, get, vid):
    v = {**more, **r3}[vid]
    ctx, html = get(f"/vehicle/{vid}")
    assert v["median_price"] is None and ctx["bidst"]["no_estimate"], "전제 — 배너가 서는 침수·전손 판정 물건"
    assert not ctx["can_analyze"], "전제 — 예전엔 '수입·상용/특수차' 안내가 같은 배너에 섰다(doc_id 없음)"
    bn = _banner(html)
    assert BANNER_A2 in bn
    for gone in ("아직", "현재 <b", "상태입니다", "수입·상용/특수차"):
        assert gone not in bn, gone


def test_A2_대조군_비침수_배너는_예전_문장(more, get):
    v = more["LOW"]
    ctx, html = get("/vehicle/LOW")
    assert v["median_price"] is None and not ctx["bidst"]["no_estimate"] and not ctx["can_analyze"], "전제"
    bn = _banner(html)
    assert ('<div class="text-sm text-mut" title="완료">\n'
            '    현재 <b class="text-txt">' in bn and '</b> 상태입니다 — 시세·입찰가가 아직 계산되지 않았습니다.\n  </div>\n' in bn)
    assert bn.rstrip().endswith(IMPORT_NOTE), "수입·상용 안내 그대로"


def test_A2_대조군_매각_종료는_예전_문장(mk, get):
    """매각 종료(침수 등급이어도 no_estimate 거짓 — bid_state 가 closed 를 먼저 본다) — 배너 그대로."""
    mk("CLFL", model="포터 II", appraisal_value=12_000_000, min_sale_price=8_400_000, judgment="종결", auction_result="낙찰",
       winning_price=9_000_000, accident_grade="flood", market_confidence_label=None, market_confidence=None, sale_date=_d(-5))
    ctx, html = get("/vehicle/CLFL")
    assert ctx["bidst"]["state"] == "closed" and not ctx["bidst"]["no_estimate"]
    assert ('<b class="text-txt">매각 종료</b>된 물건입니다 — 시세·입찰가는 계산하지 않습니다.\n    \n  </div>') in _banner(html)


# ── A3 — 물건 정보 '다음 기일 예상 최저가' ─────────────────────────────────────────
def test_A3_다음_기일_예상_최저가_행이_없다(more, get, monkeypatch):
    _nm(monkeypatch)
    ctx, html = get("/vehicle/FLLOW")
    assert ctx["bidst"]["no_estimate"] and ctx["next_min"] and not ctx["floor_guard"], "전제 — 예전엔 이 행이 섰다"
    assert "다음 기일 예상 최저가" not in html and _won(NEXT["price"]) not in html
    assert f'<span class="nc-unit">{_won(more["FLLOW"]["min_sale_price"])} 원</span>' in html, "최저매각가(법원 사실)는 그대로"


def test_A3_대조군_비침수는_행이_그대로(more, get, monkeypatch):
    _nm(monkeypatch)
    ctx, html = get("/vehicle/LOW")
    assert not ctx["bidst"]["no_estimate"] and ctx["next_min"] and not ctx["floor_guard"]
    assert ('<dd class="font-mono text-txt tnum"><span class="nc-unit">8,750,000 원</span>\n'
            '      <span class="block text-mut text-xs font-sans not-italic mt-0.5">30% 저감 · 전국 기준(이 법원 표본 부족)</span>') in html
    assert html.count("다음 기일 예상 최저가") == 3, "gloss 매크로가 용어를 세 번 쓴다(aria-label · 본문 · 말풍선)"


def test_A_시세_없는_침수차_화면_전체(more, get, monkeypatch):
    """지시서 확인 항목 — '입찰하지 마세요' ≥ 2 · '직접 확인하세요' 0 · '아직 계산되지' 0 · '다음 기일 예상 최저가' 0."""
    _nm(monkeypatch)
    ctx, html = get("/vehicle/FLLOW")
    assert ctx["bidst"]["no_estimate"] and ctx["next_min"], "전제"
    assert html.count("입찰하지 마세요") >= 2
    for gone in ("중고차 시세를 직접 확인하세요", "아직 계산되지", "다음 기일 예상 최저가"):
        assert gone not in html, gone


# ── B1 — 리포트 01 셋째 요점 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD", "FLDR2"])
def test_B1_요점은_시세가_아니라_침수_전손_기재에_근거한다(cars, get, vid):
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["report"] and ctx["bidst"]["no_estimate"], "전제 — 본문이 있는 침수·전손 판정 리포트"
    s = _s01(html)
    assert LI_B1 in s
    for gone in ("이 결론이 딛고 선", "미확정 요소", f"시세 신뢰도 {cars[vid].get('market_confidence')}/100</b>"):
        assert gone not in s, gone


def test_B1_대조군_예상가_있는_물건은_예전_요점(more, get):
    ctx, html = get("/vehicle/ACC/report")
    assert not ctx["bidst"]["no_estimate"] and ctx["report"]["exp"] and not ctx["floor_guard"], "전제 — `elif exp` 갈래"
    li = (f'<li><b>시세 신뢰도 {more["ACC"]["market_confidence"]}/100</b> — 이 결론이 딛고 선 <b>소매 시세</b>를 얼마나 믿을 수 있는지의 점수입니다'
          '(차량 상태·사고 이력의 확실성은 별개 · 02 참조). 미확정 요소는 현장확인(상태·정비비)뿐이며 결과에 따라 밴드가 조정될 수 있음(09)</li>\n'
          '        </ul>')
    assert li in _s01(html) and LI_B1 not in html


# ── B2 — '입찰 중단 기준' 상자 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLOOD", "FLDR2", "KWFLOOD", "KWOVER"])
def test_B2_침수_전손_판정이면_상자는_로즈_문장_끝에_01_없음(cars, r3, get, vid):
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["report"] and ctx["bidst"]["no_estimate"], "전제"
    if vid in ("KWFLOOD", "KWOVER"):
        assert ctx["report"]["stop_active"] is False, "전제 — 키워드로만 보류(등급 none): 예전엔 회색 off 상자였다"
    cls, txt = _stop(html)
    assert cls == "on"
    assert txt.strip() == STOP_B2 and "(01)" not in txt


# ── B3 — 09 '사고·침수' 칩 ─────────────────────────────────────────────────────────
_CHIP = re.compile(r'<td class="k">사고·침수</td>.*?<td class="c tagcell"><span class="chip ([a-z]+)">([^<]+)</span></td></tr>', re.S)


@pytest.mark.parametrize("vid", ["KWFLOOD", "KWOVER"])
def test_B3_키워드_보류_09_칩은_STOP_대상(cars, r3, get, vid):
    v = {**cars, **r3}[vid]
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["bidst"]["no_estimate"] and not ctx["report"]["stop_active"] and v["insurance_history"], \
        "전제 — 키워드로만 보류 · 보험이력 있음(예전엔 초록 '이력상 양호')"
    m = _CHIP.search(html)
    assert m and m.groups() == ("risk", "STOP 대상")
    assert "이력상 양호" not in html


def test_B3_대조군_보험이력_있는_정상차는_초록_그대로(r3, more, get):
    ctx, html = get("/vehicle/OKINS/report")
    assert not ctx["bidst"]["no_estimate"] and not ctx["report"]["stop_active"]
    assert _CHIP.search(html).groups() == ("ok", "이력상 양호")
    ctx2, h2 = get("/vehicle/ACC/report")
    assert ctx2["report"]["stop_active"] and not ctx2["bidst"]["no_estimate"]
    assert _CHIP.search(h2).groups() == ("risk", "STOP 대상")


# ── B4 — 10 ＝줄 작은 설명 ────────────────────────────────────────────────────────
_EQ = re.compile(r'<div class="logic"><span class="ln">＝</span><div class="ld"><b>재판매 상한가</b><small>([^<]*)</small></div>'
                 r'(<span class="lv[^"]*"[^>]*>[^<]*</span>)</div>')


def test_B4_비침수_0원_이하는_숫자를_두고_설명에_산정_불가가_없다(more, get):
    v = more["NEG"]
    ctx, html = get("/vehicle/NEG/report")
    assert v["upper_bid"] < 0 and not ctx["bidst"]["no_estimate"] and v["breakdown"], "전제 — 비침수 · 0원 이하 · 10 산정표"
    m = _EQ.search(html)
    assert m and m.group(1) == SMALL_B4
    assert m.group(2) == f'<span class="lv num">{_won(v["upper_bid"])}</span>', "값 칸은 숫자 그대로(검산 원칙 — Steward '통일하지 않음')"


def test_B4_34408형은_산정_불가가_한_번(cars, get):
    ctx, html = get("/vehicle/FLOOD/report")
    assert cars["FLOOD"]["upper_bid"] < 0 and ctx["bidst"]["no_estimate"], "전제"
    m = _EQ.search(html)
    assert m and m.group(1) == SMALL_B4
    assert (m.group(1) + m.group(2)).count("산정 불가") == 1


# ── B5 — `.stop` CSS ─────────────────────────────────────────────────────────────
def test_B5_stop_상자는_좁으면_태그_아래로_쌓인다(cars, get):
    _, html = get("/vehicle/FLOOD/report")
    i = html.index(".stop{")
    st = html[html.rindex("<style>", 0, i):html.index("</style>", i)]
    assert ".stop{margin-top:20px;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:flex-start;border-radius:10px;padding:13px 16px}" in st
    assert ".stop p{flex:1 1 12em;min-width:0;font-size:12.5px;line-height:1.55}" in st
    # 큰글씨 320 대만 좌우 안쪽 여백 12px — 대체 서체(웹폰트 지연·실패)에서도 off 갈래 ≤6줄(브라우저 실측은 HEAD.txt)
    assert "@media screen and (max-width:359px){html.nc-large .stop{padding-left:12px;padding-right:12px}}" in st
    assert "html.nc-large .stop .tg{font-size:16px}" in st, "태그 글꼴은 그대로"
    assert "REC-9 3회차" not in html, "내부 메모는 Jinja 주석 — 공개 HTML 에 실리지 않는다"


# ── C1·C2 — 목록 lg 표 ──────────────────────────────────────────────────────────────
def _row(html, vid):
    m = re.search(r'<tr[^>]*>(?:(?!</tr>).)*?href="/vehicle/' + vid + r'"(?:(?!</tr>).)*</tr>', html, re.S)
    assert m, f"lg 표에 {vid} 행이 없다"
    return m.group(0)


_MIN = re.compile(r'<td class="py-2\.5 px-3 text-right whitespace-nowrap ([^"]+)"\s*((?:title="[^"]*")?)><span class="font-mono text-sm">([\d,]+)</span>')
_DOT = re.compile(r'<span class="w-1\.5 h-1\.5 rounded-full ([^"]+)"></span>([^<\s]+)')


@pytest.mark.parametrize("label,conf", [("높음", 81), ("보통", 53), ("낮음", 30)])
def test_C1_침수_전손_행의_신뢰도_점은_중립(mk, get, label, conf):
    _flood(mk, "FLC", market_confidence_label=label, market_confidence=conf)
    ctl = mk("OKC", model="아반떼 CN7", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="유찰 대기",
             median_price=30_000_000, upper_bid=19_000_000, market_confidence_label=label, market_confidence=conf)
    assert not service.bid_state(ctl, BT)["no_estimate"]
    _, lst = get("/vehicles?q=FLC&sort=expected")
    _, lc = get("/vehicles?q=OKC&sort=expected")
    d_fl, d_ctl = _DOT.search(_row(lst, "FLC")), _DOT.search(_row(lc, "OKC"))
    assert d_fl and d_ctl, "전제 — 두 행 모두 시세 칸에 신뢰도 점이 선다"
    assert d_fl.groups() == ("bg-slate-400", label), "등급과 무관한 중립 하나 · 글자 그대로"
    sig = {"높음": "bg-emerald-500", "보통": "bg-amber-500", "낮음": "bg-rose-500"}[label]
    assert d_ctl.groups() == (sig, label), "대조군은 신호등 색 그대로"


@pytest.mark.parametrize("vid,was", [("FLOOD", "amber"), ("KWOVER", "amber"), ("FLMKT", "rose")])
def test_C2_침수_전손_행의_최저매각가_칸은_강조도_title도_없다(cars, r3, get, vid, was):
    v = {**cars, **r3}[vid]
    assert service.bid_state(v, BT)["no_estimate"], "전제"
    if was == "amber":
        assert v["upper_bid"] and v["min_sale_price"] > v["upper_bid"], "전제 — 예전엔 앰버 + '최저가가 산정 상한가(재판매 기준)보다 높음'"
    else:
        assert v["min_sale_price"] > v["median_price"], "전제 — 예전엔 로즈 + '경매 최저가가 소매 시세보다 높음'"
    _, lst = get(f"/vehicles?q={vid if vid != 'FLOOD' else 'CLS300'}&sort=expected")
    m = _MIN.search(_row(lst, vid))
    assert m and m.groups() == ("text-mut", "", _won(v["min_sale_price"]))


def test_C2_대조군_비침수_행은_강조와_title_그대로(more, r3, get):
    pos = more["POS"]
    assert pos["min_sale_price"] > pos["upper_bid"] and not service.bid_state(pos, BT)["no_estimate"]
    _, l1 = get("/vehicles?q=POS&sort=expected")
    assert _MIN.search(_row(l1, "POS")).groups() == ("text-amber-700", 'title="최저가가 산정 상한가(재판매 기준)보다 높음"',
                                                     _won(pos["min_sale_price"]))
    _, l2 = get("/vehicles?q=MKTCTL&sort=expected")
    assert _MIN.search(_row(l2, "MKTCTL")).groups() == ("text-rose-600", 'title="경매 최저가가 소매 시세보다 높음 — 시세보다 비싼 입찰"', "14,000,000")
    _, l3 = get("/vehicles?q=OKINS&sort=expected")
    assert _MIN.search(_row(l3, "OKINS")).groups() == ("text-mut", "", "10,000,000")


def _watch_min(html, vid):
    tb = html[html.index("<tbody"):html.index("</tbody>")]
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", tb, re.S):
        if f'href="/vehicle/{vid}"' in tr:
            return re.findall(r"(<td[^>]*>)(.*?)</td>", tr, re.S)[3]
    raise AssertionError(f"관심 표에 {vid} 행이 없다")


@pytest.mark.parametrize("vid", ["FLOOD", "KWOVER"])
def test_C2_관심_lg_표도_같은_규칙(cars, r3, get, vid):
    v = {**cars, **r3}[vid]
    ctx, wl = get(f"/watchlist?ids={vid}")
    row = ctx["rows"][0]
    assert row["no_estimate"] and not row["floor_check"] and v["min_sale_price"] > v["upper_bid"], "전제 — 예전엔 로즈 + title"
    td, val = _watch_min(wl, vid)
    assert td == '<td class="py-2.5 px-4 font-mono text-right whitespace-nowrap text-mut"\n              >' and val == _won(v["min_sale_price"])


def test_C2_대조군_관심_lg_표_비침수는_로즈_title_그대로(more, get):
    pos = more["POS"]
    _, wl = get("/watchlist?ids=POS")
    td, val = _watch_min(wl, "POS")
    assert td == ('<td class="py-2.5 px-4 font-mono text-right whitespace-nowrap text-rose-600"\n'
                  '              title="최저매각가가 산정 상한가보다 높음">') and val == _won(pos["min_sale_price"])


# ── D — /privacy 내부 메모 ─────────────────────────────────────────────────────────
def test_D_privacy_공개_소스에_내부_메모가_없다(get):
    _, html = get("/privacy")
    st = html[html.index("<style>"):html.index("</style>")]
    for gone in ("PLAY-1", "app-design-expert", "고칠 것", "실측", "/*"):
        assert gone not in st, gone
    assert ".tel{white-space:nowrap}" in st and "ul.hist{list-style:none;padding-left:0}" in st, "스타일 규칙은 그대로"
    assert "2026-10-01" in html, "시행일은 건드리지 않는다"
    src = (TPL / "privacy.html").read_text(encoding="utf-8")
    assert "{#- PLAY-1 2회차(app-design-expert 고칠 것 3)" in src, "메모는 템플릿 안 Jinja 주석으로 남는다"


# ── E1 — 빌드된 app.css 에 템플릿이 쓰는 유틸리티(qa §9-1 · N35·N36) ────────────────────
CSS_RULES = {   # 템플릿이 쓰는 클래스 → app.css 에 있어야 하는 규칙(npm run build:css 산출)
    "ring-inset": r".ring-inset{--tw-ring-inset:inset}",
    "ring-white/30": r".ring-white\/30{--tw-ring-color:hsla(0,0%,100%,.3)}",
    "bg-white/[0.12]": r".bg-white\/\[0\.12\]{background-color:hsla(0,0%,100%,.12)}",
    "sm:ml-auto": r".sm\:ml-auto{margin-left:auto}",
    "whitespace-nowrap": r".whitespace-nowrap{white-space:nowrap}",          # 3회차 A1·A2 '입찰하지 마세요' 한 덩어리
    "bg-slate-400": r".bg-slate-400{",                                       # 3회차 C1 신뢰도 점 중립
    # 3.5회차 F2·F3 — 배너 로즈 면·본문, 보류 상자 머리(모두 이미 빌드된 규칙 — 재빌드 결과 app.css 그대로)
    "bg-rose-50": r".bg-rose-50{",
    "border-rose-200": r".border-rose-200{",
    "text-rose-800": r".text-rose-800{",
    "text-rose-700": r".text-rose-700{",
}
USES = {   # 그 클래스를 쓰는 자리(템플릿 원문) — 템플릿만 나가고 app.css 가 안 나가면 화면에서 빠지는 것들
    "detail.html": ["'bg-white/[0.12] text-white/90 ring-1 ring-inset ring-white/30'", '<span class="sm:ml-auto min-w-0 text-right font-semibold text-mut">',
                    '<span class="whitespace-nowrap">입찰하지 마세요</span>', '<b class="whitespace-nowrap">입찰하지 마세요</b>',
                    "{{ 'bg-rose-50 border border-rose-200' if _bne else 'bg-surface border border-line' }}",
                    "{{ 'text-rose-800' if _bne else 'text-mut' }}",
                    '<div class="text-xs text-rose-700 mb-1 font-semibold">⛔ 입찰 보류 — 침수·전손 의심</div>'],
    "vehicles.html": ["{% set dot = 'bg-slate-400' if _ne else", "{{ 'text-mut' if _ne else 'text-rose-600' if over_mkt else 'text-txt' }}"],
}


def test_E1_빌드된_app_css_에_템플릿이_쓰는_유틸리티가_있다():
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    for cls, rule in CSS_RULES.items():
        assert rule in css, f"빌드된 app.css 에 {cls} 가 없다 — npm run build:css 후 템플릿과 같은 배포로"
    i = css.index(r".sm\:ml-auto{")
    media = css.rfind("@media", 0, i)
    assert css[media:media + 25] == "@media (min-width:640px){" and css.count("{", media, i) - css.count("}", media, i) == 1, \
        "sm:ml-auto 는 640px 이상에서만"
    for name, needles in USES.items():
        src = (TPL / name).read_text(encoding="utf-8")
        for n in needles:
            assert n in src, (name, n)


# ── E2 — 목록 lg 상한가 칸: 매각 종료는 0원 이하여도 '—'(qa §9-2 · N14) ──────────────────
def _upper_cell(row):
    m = re.search(r'title="재판매 손익분기가\(마진·부대비 차감\) — 이 값 이하 낙찰 시 차익">(.*?)</td>', row, re.S)
    assert m, "lg 표 '상한가 재판매' 칸"
    return m.group(1)


def test_E2_매각_종료_0원_이하는_대시(r3, get):
    v = r3["CLNEG"]
    st = service.bid_state(v, BT)
    assert st["state"] == "closed" and v["upper_bid"] < 0, "전제 — 매각 종료 · 0원 이하(`and not closed` 를 지우면 '산정 불가'가 선다)"
    _, lst = get("/vehicles?q=CLNEG&sort=expected")
    assert _upper_cell(_row(lst, "CLNEG")) == "—"


def test_E2_대조군_진행_중_0원_이하는_산정_불가(r3, get):
    _, lst = get("/vehicles?q=OPNEG&sort=expected")
    assert _upper_cell(_row(lst, "OPNEG")) == ('<span class="font-sans text-xs font-medium text-mut" '
                                               'title="0원 이하 — 되팔이로 목표마진을 남길 낙찰가가 없습니다">산정 불가</span>')
