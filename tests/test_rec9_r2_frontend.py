# -*- coding: utf-8 -*-
"""REC-9 2회차 화면 쪽(지시서 2026-10-01-16) — 1회차 검수(design-critic 고칠 것 1·3 · app-design-expert 고칠 것 1·2·3 · qa §7)가
남긴 자리. 판정 기준은 바꾸지 않는다 — 이미 정해진 판정(service.bid_state · estimate_withheld)을 화면이 같은 말로 하게 한다.

배포 조건(design-critic 필수)
  1. 리포트 01 '입찰 중단 기준'(`.stop` on·off): 침수·전손 판정 물건(`_noest`)은 없는 '권장가'를 무효로 선언하지 않고 한줄 판정과 같은
     무조건 보류를 말한다(Steward 문구). 키워드로만 보류된 물건은 off 갈래(회색 상자)로 오는데 같은 문장이다.
     (REC-9 3회차: 상자 색 술어가 `stop_active or _noest` 로 바뀌어 키워드 보류 물건도 로즈 on — tests/test_rec9_r3_frontend.py B2.)
  2. 문서 끝 면책 `.disc` 의 빨강 굵기 술어 `report and not _noest`(PANEL-56 4회차 오너 결정 원칙) · `_noest` 면 '(±N%)' 생략.
같은 배포(권고 → Steward 채택)
  3. 상세 '입찰가 산정 근거' 보류 상자 — "자동 산정을 제공하지 않습니다 — 입찰하지 마세요."
     (REC-9 3.5회차 F4: 본문은 하우스 낱말 "…예상낙찰가·입찰 상한선을 내지 않습니다 — 입찰하지 마세요."로 바뀌었다 — 아래 HOLD_NEW.)
  4. 상세 히어로 '시세 신뢰도' 배지 — no_estimate 면 중립색(초록·앰버·로즈 금지).
  5. 0원 이하·가린 재판매 상한가 — 상세 산정표 끝줄(음수 width·초록 금지) · 목록 lg 표 · 관심 표 · 홈 '유망 물건' 표.
  6. 관심 화면 칩 — 저장 판정 '시세 신뢰도 낮음'인 침수차는 로즈 '입찰 보류'(기존 저장 문자열).
  7. `_noest` 물건의 next_min 줄 · 숨긴 값을 가리키는 유사 낙찰 주석을 그리지 않는다.
테스트 공백(qa §7 생존 변이): M24(가드 + 키워드 보류의 상세 '입찰 상한선' 행) · M32(히어로 expected.source) · M44(리포트 10 '오차를
고르는 규칙'). M60(/privacy §9 화면 ⊂ 문서)은 tests/test_privacy_play1.py.

각 테스트는 **전제를 먼저 단언**한다(그 갈래가 실제로 렌더되는 물건인지) — 아니면 공허 통과다.
외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`(autouse, 시도 기록).
"""
import json
import re

import pytest

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec9_frontend import KW_BD, _body, _flood, _url, cars, get  # noqa: F401 — 1회차 픽스처(FLOOD·KWFLOOD·FLDR2·BLK) 재사용
from web import service
from web.app import _won

# REC-9 3회차(Steward B2): 문장 끝 '(01)'을 뺐다 — 상자가 01 안에 있어 자기 절을 가리켰다(design-critic 2회차 판단 3).
STOP_SENTENCE = ("<b>침수·전손 의심</b>으로 이미 입찰 중단 기준에 해당합니다 — "
                 "이 리포트는 예상낙찰가·입찰 상한선을 내지 않습니다.")
# 대조군 문장 — 예전과 바이트 그대로여야 한다(침수·전손 판정이 아닌 물건)
STOP_ON_ORIG = ("<b>사고/침수 이력이 감지</b>되었습니다. 현장에서 골격(프레임) 손상·침수 확정 시 본 리포트의 권장가는 "
                "<b>즉시 무효</b>이며 입찰 보류를 권장합니다.")
DISC_RED_ORIG = '<b style="color:var(--red)">입찰 중단 기준에 해당하는 사실을 미리 발견하면 권장가는 무효입니다.</b>'
# REC-9 3회차(Steward A1): '입찰하지 마세요'를 한 덩어리로 묶는다(큰글씨 320 에서 "입찰하지 / 마세요."로 갈렸다)
# REC-9 3.5회차(Steward F4): 하우스 낱말 '예상낙찰가·입찰 상한선 … 내지 않습니다', 출처는 '감정평가서 등 법원 자료'(리포트 01 셋째 요점과 같은 범위)
HOLD_NEW = ("감정평가서 등 법원 자료에서 침수·전손 기재가 감지되었습니다. 예상낙찰가·입찰 상한선을 내지 않습니다 —\n"
            '          <span class="whitespace-nowrap">입찰하지 마세요</span>.')
NA_TITLE = "0원 이하 — 되팔이로 목표마진을 남길 낙찰가가 없습니다"
NA_CELL = f'<span class="font-sans text-xs font-medium text-mut" title="{NA_TITLE}">산정 불가</span>'
HELD_CELL = '<span class="font-sans text-xs font-medium text-mut">내지 않음</span>'

# 1470 류(비침수·0원 이하) 산정표 — 백업 값 그대로(기준 430만 − 차감 464.2만 = −34.2만)
NEG_BD = {"기준시세": 4_300_000, "플랫폼": "encar", "플랫폼가중": 1.0, "예상수리비": 500_000, "사고등급": "none",
          "사고감가율": 0.15, "사고감가": 645_000, "리스크프리미엄": 301_000, "취득세": 301_000, "고정부대비": 500_000,
          "마진": 645_000, "상태정비추가": 1_750_000, "상태사유": ["자동차검사 유효기간 경과", "시동·운행 불가 언급"], "표본수": 9}
POS_BD = {"기준시세": 34_700_000, "플랫폼": "encar", "플랫폼가중": 1.0, "예상수리비": 500_000, "사고등급": "accident",
          "사고감가율": 0.15, "사고감가": 5_205_000, "리스크프리미엄": 2_429_000, "취득세": 2_429_000, "고정부대비": 500_000,
          "마진": 5_205_000, "상태정비추가": 0, "표본수": 21}
_STEPS = ("예상수리비", "상태정비추가", "사고감가", "리스크프리미엄", "취득세", "고정부대비", "마진")


def _upper(bd):
    return bd["기준시세"] - sum(bd[k] for k in _STEPS)


@pytest.fixture
def more(mk):
    """1회차 cars 에 더하는 2회차 물건들."""
    return {
        # 대조군 — 사고 등급(stop_active)이고 침수·전손 판정이 아니다 · 밴드 있음 · 상한가 양수
        "ACC": mk("ACC", model="아반떼 CN7", appraisal_value=20_000_000, min_sale_price=10_000_000, median_price=16_600_000,
                  judgment="유찰 대기", accident_grade="accident", insurance_history={"own_damage": 2, "opp_damage": 0},
                  upper_bid=9_000_000),
        # 1470 류 — 비침수 · 재판매 상한가 0원 이하 · 산정표 있음
        "NEG": mk("NEG", model="아반떼 MD", year=2013, appraisal_value=5_000_000, min_sale_price=3_500_000, fail_count=1,
                  judgment="유찰 대기", accident_grade="none", median_price=4_300_000, upper_bid=_upper(NEG_BD),
                  breakdown=json.dumps(NEG_BD, ensure_ascii=False)),
        # 대조군 — 상한가 양수 · 산정표 있음(끝줄 초록 막대가 그대로여야 한다)
        "POS": mk("POS", model="그랜저 IG", year=2019, appraisal_value=40_000_000, min_sale_price=32_000_000, fail_count=1,
                  judgment="유찰 대기", accident_grade="accident", median_price=34_700_000, upper_bid=_upper(POS_BD),
                  breakdown=json.dumps(POS_BD, ensure_ascii=False)),
        # 침수 등급 · 저장 판정 '시세 신뢰도 낮음'(09-29 사본 5대 — 2025타경12085_1 류: 시세 없음)
        "FLLOW": mk("FLLOW", model="포터 II", appraisal_value=15_000_000, min_sale_price=12_500_000, fail_count=0,
                    judgment="시세 신뢰도 낮음, 수동 검토", accident_grade="flood", market_confidence_label=None,
                    market_confidence=None),
        # 대조군 — 같은 저장 판정의 비침수 물건(하늘색 '신뢰도 낮음' 칩이 그대로)
        "LOW": mk("LOW", model="스타렉스", appraisal_value=15_000_000, min_sale_price=12_500_000, fail_count=0,
                  judgment="시세 신뢰도 낮음, 수동 검토", accident_grade="none", market_confidence_label=None,
                  market_confidence=None),
    }


def _stop(html):
    m = re.search(r'<div class="stop (on|off)">\s*<span class="tg">입찰 중단 기준</span>\s*<p class="gloss-row">(.*?)</p>', html, re.S)
    assert m, "01 '입찰 중단 기준' 상자가 없다 — 리포트 본문 갈래가 아니다(공허 통과 방지)"
    return m.group(1), m.group(2)


def _disc(html):
    m = re.search(r'<div class="disc">(.*?)</div>', html, re.S)
    assert m, "문서 끝 면책이 없다"
    return m.group(1)


def _endline(html):
    """상세 '재판매 손익분기 산정' 끝줄(= 손익분기 상한) 한 줄의 HTML."""
    i = html.index("= 손익분기 상한</span>")
    j = html.index('<div class="text-xs text-mut mb-4 leading-relaxed border-t border-line pt-2">', i)
    return html[i:j]


def _text(h):
    """태그를 걷고 공백을 하나로 — 사람이 읽는 글자(끝줄 말은 ' — ' 앞뒤를 두 덩어리로 감싼다: ui.judge_label)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()


_JL = ('<span class="sm:ml-auto min-w-0 text-right font-semibold text-mut"><span class="whitespace-nowrap">{} —</span> '
       '<span class="whitespace-nowrap">{}</span></span>')


# ── 1 · 2 — 리포트 '입찰 중단 기준' · 면책 (배포 조건) ─────────────────────────────
@pytest.mark.parametrize("vid,cls", [("FLOOD", "on"), ("FLDR2", "on"), ("KWFLOOD", "on")])
def test_리포트_입찰_중단_기준은_무조건_보류를_말한다(cars, get, vid, cls):
    st = service.bid_state(cars[vid], BT)
    assert st["no_estimate"] is True, (vid, st["state"])                       # 전제 — 침수·전손 판정 물건
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["report"], "리포트 본문 갈래(시세 있음)여야 '입찰 중단 기준' 상자가 선다"
    got_cls, txt = _stop(html)
    # REC-9 3회차(Steward B2): 상자 색 술어 `report.stop_active or _noest` — 키워드로만 보류된 물건(KWFLOOD, stop_active 거짓)도 로즈 on.
    # 2회차엔 회색 off 상자 안에서 "이미 해당합니다"였다(두 검수 공통 지적).
    assert got_cls == cls, "침수·전손 판정 물건은 상자도 로즈(on) — 문장과 같은 세기"
    assert txt.strip() == STOP_SENTENCE
    assert "권장가" not in txt and "확정 시" not in txt


def test_리포트_입찰_중단_기준_대조군은_예전_문장(more, cars, get):
    """stop_active 이고 침수·전손 판정이 아닌 물건(사고 등급) · stop_active 가 아닌 물건 — 문장 바이트 그대로."""
    assert not service.bid_state(more["ACC"], BT)["no_estimate"]
    ctx, html = get("/vehicle/ACC/report")
    assert ctx["report"]["stop_active"] is True and ctx["expected"] and ctx["expected"]["acc"], "전제 — on 갈래 · 오차 꼬리표 있음"
    cls, txt = _stop(html)
    assert cls == "on" and txt == STOP_ON_ORIG + "\n        "
    disc = _disc(html)
    assert DISC_RED_ORIG in disc and disc.count("color:var(--red)") == 1, "본문이 있는 대조군은 빨간 굵기 그대로"
    assert f"오차(±{ctx['expected']['acc']['mae']}%)가 있고" in disc
    _, blk = get("/vehicle/BLK/report")
    cls, txt = _stop(blk)
    assert cls == "off" and txt.startswith("현장/서류에서 <b>골격(프레임) 사고 · 침수 · 미기재 중대 결함 · ")
    assert txt.rstrip().endswith("중 하나라도 확인되면 본 리포트의 권장가는 무효로 간주하고 입찰을 보류하십시오.")


@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD", "FLDR2"])
def test_면책_끝_문장은_권장가_없는_물건에서_빨갛지_않다(cars, get, vid):
    ctx, html = get(f"/vehicle/{vid}/report")
    assert ctx["report"] and ctx["bidst"]["no_estimate"], "전제 — 본문이 있는 침수·전손 판정 물건(예전 술어 `report` 가 참)"
    disc = _disc(html)
    assert "color:var(--red)" not in disc and "<b style" not in disc
    assert "입찰 중단 기준에 해당하는 사실을 미리 발견하면 권장가는 무효입니다." in disc, "문장은 그대로 — 색·굵기만"
    if vid == "FLOOD":
        assert ctx["expected"] and ctx["expected"]["acc"], "전제 — 오차 꼬리표 재료가 있다(가리지 않으면 '(±11.7%)'가 선다)"
    assert "오차(±" not in disc and "추정치로 오차가 있고" in disc


# ── 3 — 상세 '입찰가 산정 근거' 보류 상자 ────────────────────────────────────────
@pytest.mark.parametrize("vid", ["FLOOD", "KWFLOOD", "FLDR2"])
def test_상세_보류_상자는_판정_상자와_같은_지시(cars, get, vid):
    _, html = get(f"/vehicle/{vid}")
    assert "⛔ 입찰 보류 — 침수·전손 의심" in html, "전제 — 보류 상자가 선다"
    assert HOLD_NEW in html
    assert "현장 점검 후 판단하세요" not in html and "제공하지 않으니" not in html
    assert "입찰하지 마세요." in html


# ── 4 — 상세 히어로 '시세 신뢰도' 배지 ─────────────────────────────────────────
_BADGE = re.compile(r'<span class="text-xs font-bold px-2\.5 py-1 rounded-full ([^"]*)" title="[^"]*">([^<]*)</span>')


@pytest.mark.parametrize("label,conf", [("높음", 81), ("보통", 53), ("낮음", 30)])
def test_히어로_신뢰도_배지는_침수_전손이면_중립색(mk, get, label, conf):
    _flood(mk, "FLB", market_confidence_label=label, market_confidence=conf)
    ok = mk("OKB", appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="유찰 대기", median_price=30_000_000,
            upper_bid=19_000_000, market_confidence_label=label, market_confidence=conf)
    assert not service.bid_state(ok, BT)["no_estimate"]
    _, fl = get("/vehicle/FLB")
    _, ctl = get("/vehicle/OKB")
    m_fl, m_ctl = _BADGE.search(fl), _BADGE.search(ctl)
    assert m_fl and m_ctl, "전제 — 히어로 신뢰도 배지가 두 물건 모두에 선다"
    assert m_fl.group(2) == m_ctl.group(2) == f"{label} · {conf}/100", "글자는 그대로 — 색만"
    neutral = "bg-white/[0.12] text-white/90 ring-1 ring-inset ring-white/30"
    assert m_fl.group(1) == neutral
    assert not re.search(r"emerald|amber|rose", m_fl.group(1))
    sig = {"높음": "bg-emerald-400 text-[#0b142b]", "보통": "bg-amber-400 text-[#0b142b]", "낮음": "bg-rose-400 text-white"}[label]
    assert m_ctl.group(1) == sig, "대조군은 신호등 색 그대로"


# ── 5 — 0원 이하·가린 재판매 상한가 ─────────────────────────────────────────────
def test_상세_산정표_끝줄_0원_이하는_막대도_초록도_없다(more, get):
    v = more["NEG"]
    assert v["upper_bid"] == -342_000 and not service.bid_state(v, BT)["no_estimate"], "전제 — 비침수 · 0원 이하"
    _, html = get("/vehicle/NEG")
    assert "재판매 손익분기 산정" in html, "전제 — 산정표가 그려진다"
    assert "width:-" not in html, "음수 width 는 CSS 가 버려 트랙 전폭이 된다(값 −8% · 그림 +100%)"
    end = _endline(html)
    assert _JL.format("산정 불가", "0원 이하") in end, "대시 뒤에서만 접힌다(큰글씨 320px)"
    assert "emerald" not in end and _won(v["upper_bid"]) not in end and "style=\"width:" not in end
    assert "font-mono" not in end and "whitespace-nowrap\">산정 불가 — 0원 이하" not in end, "말이라 mono 를 걸지 않고, 한 덩어리로 묶지 않는다"
    # 차감 행은 그대로 남는다
    for k in ("예상수리비", "상태정비추가", "사고감가", "마진"):
        assert f"−{_won(NEG_BD[k])}" in html, k


@pytest.mark.parametrize("vid", ["KWFLOOD", "FLDR2"])
def test_상세_산정표_끝줄_가린_상한가는_내지_않음(cars, get, vid):
    v = cars[vid]
    st = service.bid_state(v, BT)
    assert st["no_estimate"] and v["upper_bid"] > 0, "전제 — 가린 값 · 상한가 양수(지금 숫자가 선다)"
    _, html = get(f"/vehicle/{vid}")
    assert "재판매 손익분기 산정" in html, "전제 — 산정표가 그려진다"
    end = _endline(html)
    assert _JL.format("내지 않음", "침수·전손 의심") in end and _won(v["upper_bid"]) not in html
    assert "emerald" not in end and "style=\"width:" not in end
    for k in ("예상수리비", "리스크프리미엄", "마진"):
        assert f"−{_won(KW_BD[k])}" in html, f"차감 행은 남는다 — {k}"


def test_상세_산정표_끝줄_34408은_0원_이하가_먼저(cars, get):
    """34408 은 0원 이하이면서 가린 값이다 — 리포트 01 요점('산정 불가 — 상한가 0원 이하')과 같은 말을 한다."""
    assert cars["FLOOD"]["upper_bid"] < 0 and cars["FLOOD"]["breakdown"], "전제 — 0원 이하 · 산정표 있음"
    _, html = get("/vehicle/FLOOD")
    end = _endline(html)
    assert "산정 불가 — 0원 이하" in _text(end) and "내지 않음" not in end
    assert "width:-" not in html


def test_상세_산정표_끝줄_대조군은_바이트_그대로(more, get):
    v = more["POS"]
    assert v["upper_bid"] > 0 and not service.bid_state(v, BT)["no_estimate"]
    _, html = get("/vehicle/POS")
    end = _endline(html)
    w = round(v["upper_bid"] / POS_BD["기준시세"] * 100, 1)
    assert end == ('= 손익분기 상한</span>\n'
                   f'            <span class="sm:w-28 sm:text-right font-mono font-semibold text-emerald-700 tnum sm:shrink-0 sm:order-last">{_won(v["upper_bid"])}</span>\n'
                   '          </div>\n'
                   f'          <div class="flex-1 h-2.5 sm:h-6 rounded bg-emerald-100 mt-1 sm:mt-0"><div class="bg-emerald-500 h-2.5 sm:h-6 rounded" style="width:{w}%"></div></div>\n'
                   '        </div>\n      </div>\n      ')


def _list_upper_cell(html, vid):
    row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*?href="/vehicle/' + vid + r'"(?:(?!</tr>).)*</tr>', html, re.S)
    assert row, f"lg 표에 {vid} 행이 없다"
    m = re.search(r'title="재판매 손익분기가\(마진·부대비 차감\) — 이 값 이하 낙찰 시 차익">(.*?)</td>', row.group(0), re.S)
    assert m, "lg 표 '상한가 재판매' 칸"
    return m.group(1)


def _watch_upper_cell(html, vid):
    tb = html[html.index("<tbody"):html.index("</tbody>")]
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", tb, re.S):
        if f'href="/vehicle/{vid}"' in tr:
            return re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)[4]
    raise AssertionError(f"관심 표에 {vid} 행이 없다")


@pytest.mark.parametrize("vid,q", [("NEG", "NEG"), ("FLOOD", "CLS300")])
def test_목록_관심_표_0원_이하는_산정_불가(more, cars, get, vid, q):
    v = (more.get(vid) or cars[vid])
    assert v["upper_bid"] < 0, "전제 — 0원 이하"
    _, lst = get(f"/vehicles?q={q}&sort=expected")
    _, wl = get(f"/watchlist?ids={vid}")
    assert _list_upper_cell(lst, vid) == NA_CELL
    assert _watch_upper_cell(wl, vid) == NA_CELL
    for h in (lst, wl):
        assert _won(v["upper_bid"]) not in _body(h)


@pytest.mark.parametrize("vid,q", [("KWFLOOD", "KWFLOOD"), ("FLDR2", "FLDR2")])
def test_목록_관심_표_가린_상한가는_내지_않음(cars, get, vid, q):
    v = cars[vid]
    assert service.bid_state(v, BT)["no_estimate"] and v["upper_bid"] > 0, "전제 — 가린 값이 양수로 있다"
    _, lst = get(f"/vehicles?q={q}&sort=expected")
    _, wl = get(f"/watchlist?ids={vid}")
    assert _list_upper_cell(lst, vid) == HELD_CELL
    assert _watch_upper_cell(wl, vid) == HELD_CELL


def test_목록_관심_표_가릴_값이_없으면_예전처럼_대시(more, get):
    """침수·전손 판정이어도 상한가가 없는 물건(시세 없음 — 09-29 사본 5대)은 '—' 그대로 — 가릴 값이 없는 칸까지 바꾸지 않는다."""
    v = more["FLLOW"]
    assert service.bid_state(v, BT)["no_estimate"] and v.get("upper_bid") is None
    _, lst = get("/vehicles?q=FLLOW&sort=expected")
    _, wl = get("/watchlist?ids=FLLOW")
    assert _list_upper_cell(lst, "FLLOW") == "—" and _watch_upper_cell(wl, "FLLOW") == "—"


@pytest.mark.parametrize("vid", ["POS", "ACC"])
def test_목록_관심_표_대조군은_숫자_그대로(more, get, vid):
    v = more[vid]
    assert v["upper_bid"] > 0 and not service.bid_state(v, BT)["no_estimate"]
    _, lst = get(f"/vehicles?q={vid}&sort=expected")
    _, wl = get(f"/watchlist?ids={vid}")
    assert _list_upper_cell(lst, vid) == _won(v["upper_bid"])
    assert _watch_upper_cell(wl, vid) == _won(v["upper_bid"])


def test_홈_유망_물건_표_0원_이하는_산정_불가(more, get, monkeypatch):
    """홈 '유망 물건' 표에도 같은 칸이 있다 — 실사용 '지금 사면 이득' 물건은 재판매 상한가가 0원 이하일 수 있다."""
    neg = dict(more["NEG"], expected_win=3_955_000, pick_kind="now", pick_label=service.PICK_LABELS["now"], pick_disc=8,
               pick_score=0.1)
    pos = dict(more["POS"], expected_win=33_000_000, pick_kind="resale", pick_label=service.PICK_LABELS["resale"], pick_disc=5,
               pick_score=0.05)
    monkeypatch.setattr(service, "promising_rows", lambda *a, **k: [neg, pos])
    _, html = get("/")
    tb = html[html.index("<!-- 유망 물건"):]
    tb = tb[:tb.index("<!-- 모바일 카드 -->")]
    assert 'href="/vehicle/NEG"' in tb and 'href="/vehicle/POS"' in tb, "전제 — 두 물건이 표에 선다"
    cell = ('<td class="py-2.5 text-right font-mono text-mut"><span class="font-sans text-xs font-medium text-mut whitespace-nowrap" '
            f'title="{NA_TITLE}">산정 불가</span></td>')
    assert cell in tb and _won(neg["upper_bid"]) not in tb
    assert f'<td class="py-2.5 text-right font-mono text-mut">{_won(pos["upper_bid"])}</td>' in tb, "대조군 숫자 그대로"


# ── 6 — 관심 화면 칩 ────────────────────────────────────────────────────────────
def _chips(html, vid):
    tb = html[html.index("<tbody"):html.index("</tbody>")]
    tr = next(t for t in re.findall(r"<tr[^>]*>.*?</tr>", tb, re.S) if f'href="/vehicle/{vid}"' in t)
    table_chip = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)[1]
    cards = html[html.index('<div class="lg:hidden divide-y divide-line">'):]
    card = re.search(r'<a href="/vehicle/' + vid + r'".*?</a>', cards, re.S).group(0)
    card_chip = re.search(r'<div class="flex items-center gap-1\.5 shrink-0">(.*?)</div>', card, re.S).group(1)
    return table_chip, card_chip


def test_관심_칩_침수차는_입찰_보류(more, cars, get):
    v = more["FLLOW"]
    st = service.bid_state(v, BT)
    assert st["no_estimate"] and v["judgment"] == "시세 신뢰도 낮음, 수동 검토", "전제 — 침수 판정 · 저장 판정 '신뢰도 낮음'"
    ctx, html = get("/watchlist?ids=FLLOW")
    assert not ctx["rows"][0]["floor_check"], "전제 — 가드 갈래(bidst.label 칩)가 아니다"
    t, c = _chips(html, "FLLOW")
    rose = "bg-rose-50 text-rose-700 border border-rose-200"
    assert t == f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium {rose}" style="word-break:keep-all">입찰 보류</span>'
    assert c.endswith(f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap {rose}">입찰 보류</span>')
    assert "신뢰도 낮음" not in t + c and "sky" not in t + c
    # 저장 판정이 이미 '입찰 보류'인 침수차(34408)는 같은 칩 — 바이트 그대로
    _, h2 = get("/watchlist?ids=FLOOD")
    t2, _ = _chips(h2, "FLOOD")
    assert t2 == t


def test_관심_칩_대조군_비침수_신뢰도_낮음은_하늘색_그대로(more, get):
    assert not service.bid_state(more["LOW"], BT)["no_estimate"]
    _, html = get("/watchlist?ids=LOW")
    t, c = _chips(html, "LOW")
    sky = "bg-sky-50 text-sky-700 border border-sky-200"
    assert t == f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium {sky}" style="word-break:keep-all">신뢰도 낮음</span>'
    assert c.endswith(f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap {sky}">신뢰도 낮음</span>')


# ── 7 — next_min · 유사 낙찰 주석 ────────────────────────────────────────────────
NEXT = {"price": 7_000_000, "ratio": 0.7, "basis": "global", "n": 0, "court_n": None, "share": None, "alt_price": None}


def _strategy(html):
    """상세 '추천 입찰 전략' 보류 상자(로즈) 한 개 — 첫 문장부터 그 상자의 닫는 태그까지."""
    i = html.index("<b>이 물건에는 입찰가를 제시하지 않습니다.</b>", html.index("<!-- 추천 입찰 전략 밴드"))
    return html[i:html.index("</div>", i)]


def _s01(html):
    return html[html.index('id="sec01"'):html.index('id="sec02"')]


def test_next_min_줄은_침수_전손이면_그리지_않는다(cars, get, monkeypatch):
    """'다음 기일 예상 최저가는 …'은 '기다리면 된다'로 읽힌다 — 침수·전손은 기다려도 풀리지 않는다."""
    monkeypatch.setattr(service, "next_min_sale", lambda v, *a, **k: dict(NEXT))
    for vid in ("FLOOD", "BLK"):
        ctx, _ = get(f"/vehicle/{vid}/report")
        assert ctx["next_min"] and not ctx["floor_guard"], f"전제 — {vid} 는 비가드 · next_min 있음(리포트 요점 갈래가 열린다)"
    _, d_fl = get("/vehicle/FLOOD")
    _, d_blk = get("/vehicle/BLK")
    s_fl, s_blk = _strategy(d_fl), _strategy(d_blk)
    assert "이 물건에는 입찰가를 제시하지 않습니다." in s_fl and "이 물건에는 입찰가를 제시하지 않습니다." in s_blk, "전제 — 둘 다 보류 상자"
    assert "다음 기일 예상 최저가는" not in s_fl
    assert "다음 기일 예상 최저가는 <b>7,000,000원</b>입니다." in s_blk, "대조군(비침수 부적합)은 그대로"
    _, r_fl = get("/vehicle/FLOOD/report")
    _, r_blk = get("/vehicle/BLK/report")
    assert "다음 기일 예상 최저가는" not in _s01(r_fl)
    assert "다음 기일 예상 최저가는 <span class=\"num\">7,000,000원</span>" in _s01(r_blk)


COMPS = [{"case_no": "2025타경1111", "year": 2020, "mileage_km": 60_000, "median_price": 34_000_000, "winning_price": 12_000_000,
          "ratio": 0.35, "sale_date": "2026-08-01"},
         {"case_no": "2025타경2222", "year": 2019, "mileage_km": 70_000, "median_price": 33_000_000, "winning_price": 13_000_000,
          "ratio": 0.39, "sale_date": "2026-07-01"}]


def test_유사_낙찰_주석은_숨긴_값을_가리키지_않는다(cars, get, monkeypatch):
    monkeypatch.setattr(service, "comparable_sales", lambda *a, **k: [dict(c) for c in COMPS])
    monkeypatch.setattr(service, "comparable_discount", lambda *a, **k: (0.37, 2))
    ctx, d_fl = get("/vehicle/FLOOD")
    assert ctx["comps_won"] and ctx["expected"]["comp_n"] == 2 and not ctx["expected"]["comp_used"], \
        "전제 — 유사 낙찰 표가 서고 '(산정에는 미반영 …)' 갈래가 열린다"
    seg = d_fl[d_fl.index("유사 낙찰 사례 <span"):]
    seg = seg[:seg.index("</span></div>")]
    for gone in ("(예상낙찰가 산정에 반영)", "산정에는 미반영", "산정엔 모델·전역 할인율 사용"):
        assert gone not in seg, gone
    _, d_blk = get("/vehicle/BLK")
    assert "(<b class=\"text-txt\">산정에는 미반영</b> — 최저매각가×유찰 프리미엄으로 계산했습니다)" in d_blk, "대조군 그대로"
    ctx_r, r_fl = get("/vehicle/FLOOD/report")
    assert len(ctx_r["comps_won"]) == 2 < ctx_r["comp_min_n"], "전제 — 05 '축적 중' 갈래"
    sec05 = r_fl[r_fl.index('id="sec05"'):r_fl.index('id="sec06"')]
    assert "유사 낙찰 사례 <b>축적 중 (2건)</b>. 아래는 현재까지 확보된 사례입니다." in sec05
    assert "개별 보정에 직접 반영" not in sec05 and "예상낙찰가 산정의 핵심 근거" not in sec05
    assert "같은 차종이 소매 시세 대비 실제 몇 %에 낙찰됐는지 보여줍니다.</p>" in sec05
    _, r_blk = get("/vehicle/BLK/report")
    s5 = r_blk[r_blk.index('id="sec05"'):r_blk.index('id="sec06"')]
    assert ("유사 낙찰 사례 <b>축적 중 (2건)</b> — 3건 이상 쌓이면 이 차량 예상낙찰가의 개별 보정에 직접 반영됩니다. "
            "아래는 현재까지 확보된 사례입니다.") in s5
    assert "보여주며, 예상낙찰가 산정의 핵심 근거입니다.</p>" in s5


# ── 테스트 공백(qa §7 생존 변이) ────────────────────────────────────────────────
def test_M24_가드_키워드_보류는_상세_입찰_상한선_행이_없다(mk, get):
    """가드(이번 회차 최저가 미확인) + 키워드로만 '입찰 보류' + 상한선 값 있음 — 상세 '물건 정보'의 '입찰 상한선 (직접 탈 목적)' 행.
    조건의 `not bidst.no_estimate` 를 지우면(M24) 판정 상자 '제공하지 않습니다' 아래에 상한선 금액이 선다."""
    row = dict(maker="BMW", model="BMW 520d", year=2017, court="전주지방법원", appraisal_value=20_000_000, min_sale_price=9_800_000,
               fail_count=3, median_price=20_795_000, sample_count=14, market_confidence=85, accident_grade="none",
               insurance_history={"own_damage": 0, "opp_damage": 0}, upper_bid=10_645_200, lower_bound=9_800_000, photo_count=15)
    gkw = mk("GKW", judgment="입찰 보류", **row)
    ctl = mk("GCTL", judgment="유찰 대기", **row)
    st = service.bid_state(gkw, BT)
    assert st["no_estimate"] and st["max_bid"], "전제 — 키워드 보류 · 상한선 값이 온다"
    ctx, html = get("/vehicle/GKW")
    assert ctx["floor_guard"] and ctx["floor_guard"]["pending"], "전제 — 가드 · 기일 남음(상한선 행 갈래가 열린다)"
    ctx2, h2 = get("/vehicle/GCTL")
    assert ctx2["floor_guard"] and ctx2["floor_guard"]["pending"] and ctx2["bidst"]["max_bid"]
    dd = '<dd class="font-mono text-lg font-semibold text-txt tnum"><span class="nc-unit">{} 원</span>'
    assert "(직접 탈 목적)</span></dt>" in h2 and dd.format(_won(ctx2["bidst"]["max_bid"])) in h2, "대조군(비침수 가드)은 행이 선다"
    assert "(직접 탈 목적)</span></dt>" not in html
    assert dd.format(_won(st["max_bid"])) not in html, "상한선 금액 칸(감정가와 같은 숫자일 수 있어 칸 모양으로 본다)"


def test_M32_히어로_산정_출처_꼬리표는_침수_전손이면_없다(cars, get, monkeypatch):
    """`expected.source`('유사 낙찰 N건 참고')는 숨긴 예상가를 어떻게 냈는지 말한다. 조건의 no_estimate 를 지우면(M32) 선다."""
    orig = service.expected_band

    def band(v, bt=None, *a, **k):   # 최저가 경로가 아닌 산정(유사 낙찰을 실제로 쓴다) — source 가 서는 갈래
        b = orig(v, bt, *a, **k)
        return {**b, "basis": {"kind": "discount", "median": v.get("median_price"), "discount": 0.4}} if b else b
    monkeypatch.setattr(service, "expected_band", band)
    monkeypatch.setattr(service, "comparable_discount", lambda *a, **k: (0.4, 4))
    ctx, html = get("/vehicle/FLOOD")
    assert ctx["expected"]["source"] == "유사 낙찰 4건 참고" and ctx["bidst"]["no_estimate"], "전제 — 꼬리표 값이 있다"
    assert "유사 낙찰 4건 참고" not in html
    ctx2, h2 = get("/vehicle/BLK")
    assert ctx2["expected"]["source"] == "유사 낙찰 4건 참고"
    assert 'AI 낙찰 예측 분석 <span class="text-white/50 font-normal">· 유사 낙찰 4건 참고</span>' in h2, "대조군은 선다"


def test_M44_리포트_10_오차를_고르는_규칙은_침수_전손이면_없다(cars, get):
    ctx, html = get("/vehicle/FLOOD/report")
    assert ctx["report"]["exp"] and ctx["expected"] and ctx["expected"]["acc"], "전제 — exp·오차 꼬리표 재료가 있다(가리지 않으면 선다)"
    assert "오차를 고르는 규칙" not in html
    _, h2 = get("/vehicle/BLK/report")
    assert "<b style=\"color:var(--ink)\">오차를 고르는 규칙</b>" in h2, "대조군은 선다"


def test_리포트_10_재판매_상한가_끝줄도_가린다(cars, more, get):
    """리포트 10 '재판매 상한가 (마진 기준)' 끝줄 — 상세 산정표와 같은 규칙(차감 행은 남기고 끝줄만)."""
    assert cars["FLOOD"]["breakdown"] and cars["KWFLOOD"]["breakdown"], "전제 — 10 재판매 상한가 표 재료"
    _, fl = get("/vehicle/FLOOD/report")
    _, kw = get("/vehicle/KWFLOOD/report")
    pat = re.compile(r'<div class="logic"><span class="ln">＝</span><div class="ld"><b>재판매 상한가</b><small>[^<]*</small></div>'
                     r'<span class="lv[^"]*"[^>]*>[^<]*</span></div>')
    end_fl, end_kw = pat.search(fl), pat.search(kw)
    assert end_fl and end_kw, "전제 — 10 재판매 상한가 표가 선다"
    # REC-9 3회차(Steward B4): 작은 설명에서 '산정 불가: '를 뺐다 — 값 칸이 이미 '산정 불가'라 한 줄에 두 번이었다.
    assert ">산정 불가</span>" in end_fl.group(0) and "0원 이하 — 되팔이로 목표마진을 남길 낙찰가가 없습니다" in end_fl.group(0)
    assert end_fl.group(0).count("산정 불가") == 1
    assert ">내지 않음</span>" in end_kw.group(0) and "침수·전손 의심 — 내지 않습니다(01)" in end_kw.group(0)
    for e in (end_fl.group(0), end_kw.group(0)):
        assert 'class="lv num"' not in e and not re.search(r"\d{1,3}(,\d{3})+", e)
    assert f"−{_won(KW_BD['마진'] + KW_BD['취득세'] + KW_BD['고정부대비'])}" in kw, "차감 행은 남는다"
    _, pos = get("/vehicle/POS/report")   # 대조군 — 비침수 · 상한가 양수: 끝줄 숫자 그대로(바이트)
    assert ('<b>재판매 상한가</b><small>이 값 이하로 낙찰 시 목표마진 확보</small></div>'
            f'<span class="lv num">{_won(_upper(POS_BD))}</span></div>') in pos
