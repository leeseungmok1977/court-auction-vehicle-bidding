# -*- coding: utf-8 -*-
"""REC-13 화면 쪽(지시서 2026-10-01-28) — 상세 '사고판정' 칩 색을 칩 글자와 같은 근거로.

칩 글자는 `v|accv`(= service.accident_label)라서 근거가 없으면(service.accident_evidence 거짓 — 보험이력 카운트도 사고 낱말도
없음) '이력 미확인'이라고 쓴다. 그런데 색 술어는 등급(`accident_grade == 'none'`)만 봐서 그 글자를 **초록**으로 칠했다 —
10-01 백업 사본 상세 1,587쪽 중 1,060쪽(예: 2026타경10300_1). 리포트 09 '사고·침수' 칩은 5회차 패널 지적으로 이미
"미확인은 앰버"로 고쳤다(tests/test_exposure.py::test_unverified_history_is_never_green). 상세에도 같은 규칙:
  · '무사고'(근거 있는 none) → 초록 그대로 · '이력 미확인' → 앰버(단순수리 갈래와 같은 클래스) · '단순수리' → 앰버 그대로
  · '사고'·'침수의심' → 로즈, 글자는 한 단계 진하게(로즈 바탕 위 4.28 → 5.72:1, 하우스 정지 칩 `_TONE_CLS['stop']` 과 같은 단계)
  · 그 밖('—') → 회색 그대로
같은 토큰 대비 2곳(design-critic 3.5회차 §7): 산정 근거 카드 '산정 불가 — 상한가 0원 이하' 상자 머리 · 관리자 시세 카드의
"⛔ 현재 최저매각가 … 높습니다" 경고문 — 로즈 글자 한 단계 진하게.

2단계(같은 지시서 이어서): 같은 상세 아래 산정 근거 카드의 '사고등급' 글자가 등급 이름(`bd.사고등급|acc`)이라 근거 없는 none 을
'무사고'로 찍었다(바로 옆 감가는 사고차 가정 15% · 10-01 사본 공개 상세 668쪽). 저장 산정표에 계산기가 남긴 표기('사고표기')가 있으면
그것을, 없으면 예전 글자 그대로. 상태 카드 로즈 칩 2종('외관·상태 손상 언급' · '시동·운행 불가 언급')도 같은 토큰이라 한 단계 진하게.

REC-15(지시서 2026-10-01-35): 근거의 정의(service.accident_evidence)가 좁아져 소유자·번호 변경·특수사고만 있는 보험이력은
'이력 미확인'이다. 상세 칩은 글자를 따르므로 그대로 맞고, 리포트 09 칩도 같은 글자를 따르게 했다 — 두 화면 패리티에 그 꼴을 더한다.

판정 기준은 바꾸지 않는다(service.py 무수정) — 이미 정해진 글자(accident_label)를 색이 같은 뜻으로 따라가게 할 뿐이다.
각 테스트는 **전제를 먼저 단언**한다(그 갈래가 실제로 렌더되는 물건인지) — 아니면 공허 통과다. 이름에 '대조군'이 붙은 테스트는
바뀌면 안 되는 렌더를 예전(a89a4a9) 바이트 그대로 단언한다(지시서 빨강 집계에서 뺀다).
외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`(autouse, 시도 기록).
"""
import json
import re
from pathlib import Path

import pytest

from tests.test_rec1_r3_picks_gate_block import _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec9_frontend import KW_BD, get  # noqa: F401 — 산정표 모양 · 렌더 + 템플릿 문맥 캡처
from web import service
from web.app import _TONE_CLS

ROOT = Path(__file__).resolve().parents[1]

OK = "bg-emerald-50 text-emerald-700 border border-emerald-200"
CAUTION = "bg-amber-50 text-amber-700 border border-amber-200"
STOP = "bg-rose-50 text-rose-700 border border-rose-200"
NEUTRAL = "bg-slate-100 text-mut border border-line"
OLD_STOP = "bg-rose-50 text-rose-600 border border-rose-200"     # 예전 로즈 갈래(4.28:1)
CHIP_HEAD = '<dd><span class="inline-flex px-2 py-0.5 rounded text-xs font-medium '
# 칩 글자 → 색(지시서 2026-10-01-28 항목 1). 초록은 '무사고' 하나뿐이다.
WANT = {"무사고": OK, "이력 미확인": CAUTION, "단순수리": CAUTION, "사고": STOP, "침수의심": STOP}

UB0_NEW = '<div class="text-xs text-rose-700 mb-1 font-semibold">산정 불가 — 상한가 0원 이하</div>'
UB0_OLD = '<div class="text-xs text-rose-600 mb-1 font-semibold">산정 불가 — 상한가 0원 이하</div>'
OVER_NEW = '<div class="mt-3 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded-md px-3 py-2">\n        ⛔ 현재 최저매각가('
OVER_OLD = '<div class="mt-3 text-xs bg-rose-50 border border-rose-200 text-rose-600 rounded-md px-3 py-2">\n        ⛔ 현재 최저매각가('

BASE = dict(appraisal_value=20_000_000, min_sale_price=10_000_000, judgment="유찰 대기", median_price=16_600_000,
            upper_bid=9_000_000)


@pytest.fixture
def c13(mk):
    """사고판정 갈래별 물건 — 등급·근거만 다르고 나머지는 같다(값은 10-01 사본 실데이터의 모양)."""
    return {
        # 근거 없는 등급 none — 2026타경10300_1 류(보험이력·사고 낱말 없음). 사본 상세 1,060쪽이 이 모양
        "NOEV": mk("NOEV", accident_grade="none", **BASE),
        # 빈 보험이력({})도 근거가 아니다(service.accident_evidence — 'bool({})' 거짓)
        "NOEV0": mk("NOEV0", accident_grade="none", insurance_history={}, **BASE),
        # 대조군 — 근거 있는 none(보험이력에 내차·상대차 피해 0건 카운트가 있다 = 조회했다) — 2026타경100009_1 류
        "EV0": mk("EV0", accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0}, **BASE),
        # REC-15 — 보험이력이 있어도 일반 사고 항목이 없으면 근거가 아니다(service.accident_evidence):
        # 소유자·번호 변경만(2026타경50904_1 꼴) · 특수사고(전손·도난·침수) 카운트만(2026타경503268_1 꼴)
        "OWN13": mk("OWN13", accident_grade="none", insurance_history={"owner_changes": 3, "plate_changes": 1}, **BASE),
        "SPC13": mk("SPC13", accident_grade="none", insurance_history={"total_loss": 0, "theft": 0, "flood": 0}, **BASE),
        # 대조군 — 단순수리(사본 0대 — 합성)
        "MINOR": mk("MINOR", accident_grade="minor", **BASE),
        # 사고 — 2025타경104467_1 류(사고 낱말이 칩 옆에 선다)
        "ACC13": mk("ACC13", accident_grade="accident", insurance_history={"own_damage": 2, "opp_damage": 0},
                    accident_hits=["판금"], **BASE),
        # 침수의심 — 2025타경12085_1 류
        "FLD13": mk("FLD13", accident_grade="flood", **BASE),
        # 대조군 — 등급 없음('—') — 2026타경101080_2 류
        "NOG": mk("NOG", accident_grade=None, **BASE),
    }


def _chip(html):
    """상세 물건 정보의 '사고판정' 칸 값(<dd> … </dd>) — 앞 공백 포함."""
    i = html.index("</dt>", html.index('aria-label="사고판정')) + len("</dt>")
    return html[i:html.index("</dd>", i) + len("</dd>")]


def _cls_text(frag):
    m = re.match(r'\s*' + re.escape(CHIP_HEAD) + r'([^"]+)">([^<]*)</span>', frag)
    assert m, "사고판정 칩 마크업이 아니다 — " + frag[:200]
    return m.group(1), m.group(2)


# ── 1. 상세 '사고판정' 칩 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["NOEV", "NOEV0"])
def test_근거_없는_none_은_앰버_이력_미확인(c13, get, vid):
    v = c13[vid]
    assert v["accident_grade"] == "none" and not service.accident_evidence(v), "전제 — 등급 none · 근거 없음"
    ctx, html = get(f"/vehicle/{vid}")
    cls, text = _cls_text(_chip(html))
    assert text == "이력 미확인" == service.accident_label(v)
    assert cls == CAUTION, f"확인하지 못한 것을 괜찮은 색으로 칠했다: {cls}"
    assert "emerald" not in _chip(html)


def test_대조군_근거_있는_none_은_초록_무사고_바이트_그대로(c13, get):
    v = c13["EV0"]
    assert v["accident_grade"] == "none" and service.accident_evidence(v), "전제 — 보험이력 0건 카운트가 있다(조회함)"
    _, html = get("/vehicle/EV0")
    assert _chip(html) == "\n    " + CHIP_HEAD + OK + '">무사고</span>\n      </dd>'


def test_대조군_단순수리는_앰버_그대로(c13, get):
    _, html = get("/vehicle/MINOR")
    assert _chip(html) == "\n    " + CHIP_HEAD + CAUTION + '">단순수리</span>\n      </dd>'


@pytest.mark.parametrize("vid,word,hits", [("ACC13", "사고", "판금"), ("FLD13", "침수의심", None)], ids=["ACC13", "FLD13"])
def test_사고_침수의심은_로즈_글자_한_단계_진하게(c13, get, vid, word, hits):
    v = c13[vid]
    assert v["accident_grade"] in ("accident", "flood"), "전제 — 로즈 갈래"
    _, html = get(f"/vehicle/{vid}")
    frag = _chip(html)
    cls, text = _cls_text(frag)
    assert text == word and cls == STOP, cls
    assert OLD_STOP not in frag and "text-rose-600" not in frag
    if hits:
        assert f'<span class="text-mut text-xs ml-1">{hits}</span></dd>' in frag, "사고 낱말은 칩 옆에 그대로"


def test_대조군_등급_없음은_회색_그대로(c13, get):
    assert service.accident_label(c13["NOG"]) == "—", "전제 — 등급 없음"
    _, html = get("/vehicle/NOG")
    assert _chip(html) == "\n    " + CHIP_HEAD + NEUTRAL + '">—</span>\n      </dd>'


def test_로즈_갈래는_하우스_정지_칩과_같은_단계다():
    """판정 칩(app._TONE_CLS)과 같은 클래스 — 같은 뜻의 로즈·앰버·초록이 화면마다 다른 단계면 안 된다."""
    assert (_TONE_CLS["ok"], _TONE_CLS["caution"], _TONE_CLS["stop"]) == (OK, CAUTION, STOP)


def test_초록은_글자가_무사고일_때만(mk, get):
    """등급 × 근거 전 조합 — 칩 글자는 accident_label 그대로, 색은 글자를 따른다(초록 ⇔ '무사고').
    근거를 템플릿이 다시 계산하지 않는다: 같은 물건의 글자와 색이 한 함수(accident_label)에서 나온다."""
    evid = {"noev": {}, "empty": {"insurance_history": {}}, "ins0": {"insurance_history": {"own_damage": 0}},
            "hits": {"accident_hits": ["판금"]}}
    bad = []
    for g in ("none", "minor", "accident", "flood", None):
        for ek, ekw in evid.items():
            vid = f"INV_{g}_{ek}"
            v = mk(vid, accident_grade=g, **ekw, **BASE)
            _, html = get(f"/vehicle/{vid}")
            cls, text = _cls_text(_chip(html))
            label = service.accident_label(v)
            want = WANT.get(label, NEUTRAL)
            if text != label or cls != want or (cls == OK) != (text == "무사고"):
                bad.append((vid, text, label, cls))
    assert not bad, bad


@pytest.mark.parametrize("vid,detail_cls,word,chip09,word09", [
    ("NOEV", CAUTION, "이력 미확인", "warn", "이력 미확인"),
    ("EV0", OK, "무사고", "ok", "이력상 양호"),          # 대조군 — 두 화면 모두 초록 그대로
    ("OWN13", CAUTION, "이력 미확인", "warn", "이력 미확인"),   # REC-15 — 소유자·번호 변경만
    ("SPC13", CAUTION, "이력 미확인", "warn", "이력 미확인"),   # REC-15 — 특수사고 카운트만
], ids=["NOEV", "대조군_EV0", "REC15_OWN", "REC15_SPC"])
def test_상세_칩과_리포트_09_칩은_같은_색_계열(c13, get, vid, detail_cls, word, chip09, word09):
    """'이력 미확인'은 두 화면 모두 앰버(리포트 chip warn), 근거 있는 '무사고'는 두 화면 모두 초록(chip ok).
    REC-13 때는 리포트 09 를 바꾸지 않고 상세가 리포트의 규칙을 따라왔다. REC-15(지시서 2026-10-01-35)부터는 리포트 09 도
    칸 글자(v|accv)를 따른다 — 보험이력 dict 가 비지 않다는 것만으로 초록이던 꼴(소유자·번호 변경만 · 특수사고만)이 두 화면 모두 앰버다."""
    _, rep = get(f"/vehicle/{vid}/report")
    m = re.search(r'<td class="k">사고·침수</td>.*?<span class="chip (\w+)">([^<]*)</span>', rep, re.S)
    assert m, "전제 — 리포트 09 '사고·침수' 행이 렌더된다"
    assert (m.group(1), m.group(2)) == (chip09, word09)
    _, html = get(f"/vehicle/{vid}")
    assert _cls_text(_chip(html)) == (detail_cls, word)


# ── 3. 같은 토큰 대비 2곳 ──────────────────────────────────────────────────────────────
def test_산정_근거_0원_이하_상자_머리는_로즈_한_단계_진하게(mk, get):
    v = mk("UB0", model="아반떼 AD", appraisal_value=6_000_000, min_sale_price=4_000_000, fail_count=1, judgment="유찰 대기",
           accident_grade="none", median_price=8_000_000, upper_bid=-500_000)
    ctx, html = get("/vehicle/UB0")
    assert v["upper_bid"] <= 0 and not (ctx["bidst"] or {}).get("no_estimate") and not ctx["wait"], \
        "전제 — 0원 이하 · 침수·전손 판정 아님 · 유찰 대기 계산 없음(산정 근거 카드가 이 상자를 그리는 갈래)"
    assert UB0_NEW in html and UB0_OLD not in html


def test_관리자_시세_카드_최저가_시세_초과_경고문은_로즈_한_단계_진하게(mk, get):
    v = mk("OVER", model="스포티지", appraisal_value=20_000_000, min_sale_price=14_000_000, judgment="유찰 대기",
           accident_grade="none", median_price=12_000_000, upper_bid=5_000_000, market_confidence_label="보통",
           market_confidence=55)
    ctx, html = get("/vehicle/OVER", admin=True)
    assert v["min_sale_price"] > v["median_price"] and not ctx["floor_guard"], "전제 — 최저가 > 시세 · 최저가 확인됨"
    assert OVER_NEW in html and OVER_OLD not in html
    _, pub = get("/vehicle/OVER")
    assert "⛔ 현재 최저매각가" not in pub, "전제 — 시세 카드는 관리자 화면에만 있다(공개 쪽은 바뀌지 않는다)"


def test_쓴_클래스는_이미_빌드된_app_css_에_있다():
    """새 유틸리티 없음 — 재빌드가 지금 app.css 와 같아야 한다(지시서 항목 4). 쓰는 클래스가 빌드에 있는지만 본다."""
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    for cls in ("text-rose-700", "bg-rose-50", "border-rose-200", "bg-amber-50", "text-amber-700", "border-amber-200",
                "bg-emerald-50", "text-emerald-700", "border-emerald-200"):
        assert re.search(r"\." + re.escape(cls) + r"\{", css), cls


# ══ 2단계 — 산정 근거 '사고등급' 글자 · 상태 카드 로즈 칩 2종 ══════════════════════════════════
LINE = '사고등급 <b class="text-txt">{}</b>(감가 {}%)'
NOLABEL = object()
P2 = dict(appraisal_value=30_000_000, min_sale_price=10_000_000, judgment="유찰 대기", median_price=30_000_000,
          upper_bid=19_000_000)


def _bd(grade, rate, label=NOLABEL):
    """저장 산정표(KW_BD 모양) — 등급·감가율·계산기 표기('사고표기')만 바꾼다. label 을 주지 않으면 표기 없는 옛 산정표."""
    d = {**KW_BD, "사고등급": grade, "사고감가율": rate, "사고감가": round(KW_BD["기준시세"] * rate)}
    if label is not NOLABEL:
        d["사고표기"] = label
    return json.dumps(d, ensure_ascii=False)


@pytest.fixture
def p2(mk):
    """값은 10-01 사본 산정표의 모양 그대로(이름 옆 주석)."""
    return {
        # 근거 없는 none — 2026타경3534_1 류(사고표기 '이력 미확인 — 사고차 가정' · 감가 15%). 사본 665행
        "BDNOEV": mk("BDNOEV", accident_grade="none", breakdown=_bd("none", 0.15, "이력 미확인 — 사고차 가정"), **P2),
        # 사고 — 2026타경81_1 류(사고표기 '사고 2회')
        "BDACC": mk("BDACC", accident_grade="accident", insurance_history={"own_damage": 2, "opp_damage": 0},
                    accident_hits=["내차피해2회"], breakdown=_bd("accident", 0.15, "사고 2회"), **P2),
        # 근거 있는 none — 2026타경100009_1 류(내차·상대차 0건 · 사고표기 '무사고(이력 확인됨)' · 감가 0%)
        "BDEV": mk("BDEV", accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0},
                   breakdown=_bd("none", 0.0, "무사고(이력 확인됨)"), **P2),
        # 대조군 — 사고표기가 없는 옛 산정표(2026타경70774_1 류 · 감가 0%) · 빈 표기 · 침수의심(표기 = 등급 이름)
        "BDOLD": mk("BDOLD", accident_grade="none", breakdown=_bd("none", 0.0), **P2),
        "BDEMPTY": mk("BDEMPTY", accident_grade="none", breakdown=_bd("none", 0.15, ""), **P2),
        "BDFLD": mk("BDFLD", accident_grade="flood", breakdown=_bd("flood", 1.0, "침수의심"), **P2),
    }


def _line(html):
    m = re.search(r'사고등급 <b class="text-txt">[^<]*</b>\(감가 [0-9.]+%\)', html)
    assert m, "전제 — 산정 근거 카드의 '사고등급' 줄이 렌더된다(산정표·시세·상한가가 있는 물건)"
    return m.group(0)


@pytest.mark.parametrize("vid,want", [
    ("BDNOEV", LINE.format("이력 미확인 — 사고차 가정", "15.0")),
    ("BDACC", LINE.format("사고 2회", "15.0")),
], ids=["BDNOEV", "BDACC"])
def test_2단계_사고등급_글자는_계산기_표기를_쓴다(p2, get, vid, want):
    _, html = get(f"/vehicle/{vid}")
    assert _line(html) == want
    if vid == "BDNOEV":
        assert _cls_text(_chip(html)) == (CAUTION, "이력 미확인"), "전제 — 위 칩과 같은 말(1단계)"
        assert '사고등급 <b class="text-txt">무사고</b>' not in html


def test_2단계_근거_있는_무사고_산정표는_무사고_뜻_그대로(p2, get):
    """계산기 표기가 '무사고(이력 확인됨)'이라 글자에 근거가 붙는다 — 뜻('무사고')·감가(0.0%)·굵기·색은 그대로.
    ⚠ 1단계 바이트와는 다르다(예전 '무사고' → '무사고(이력 확인됨)') — 지시서 대조군 '그대로'와의 차이는 보고서에 적었다."""
    _, html = get("/vehicle/BDEV")
    assert _cls_text(_chip(html)) == (OK, "무사고"), "전제 — 근거 있는 none"
    assert _line(html) == LINE.format("무사고(이력 확인됨)", "0.0")


@pytest.mark.parametrize("vid,want", [
    ("BDOLD", LINE.format("무사고", "0.0")),       # 표기 없는 옛 산정표 — 예전 글자(등급 이름) 그대로
    ("BDEMPTY", LINE.format("무사고", "15.0")),    # 빈 표기도 예전 글자로 떨어진다
    ("BDFLD", LINE.format("침수의심", "100.0")),   # 표기 = 등급 이름 — 바이트 같음
], ids=["BDOLD", "BDEMPTY", "BDFLD"])
def test_대조군_2단계_표기_없는_산정표는_예전_글자_바이트_그대로(p2, get, vid, want):
    _, html = get(f"/vehicle/{vid}")
    assert _line(html) == want


COND_ROSE = ('<span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full {} border border-rose-200">'
             '<span class="material-symbols-outlined text-sm">{}</span> {}</span>')
COND_MINOR = ('<span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 '
              'border border-amber-200"><span class="material-symbols-outlined text-sm">build</span> 외관 손상 언급</span>')


@pytest.fixture
def cond(mk, monkeypatch, tmp_path):
    """감정 요항 글(appraisal.txt)이 있는 물건 — 상세 라우트가 읽는 DATA_DIR 만 임시 폴더로 돌린다(저장소 data/ 무접촉)."""
    import web.app as A
    monkeypatch.setattr(A, "DATA_DIR", tmp_path)

    def _mk(vid, text):
        (tmp_path / vid).mkdir()
        (tmp_path / vid / "appraisal.txt").write_text(text, encoding="utf-8")
        return mk(vid, accident_grade="none", **P2)
    return _mk


def test_2단계_상태_카드_로즈_칩_2종은_글자_한_단계_진하게(cond, get):
    cond("COND2", "외관은 앞범퍼 일부 파손되어 있음. 시동이 걸리지 않아 운행 불가함.")
    ctx, html = get("/vehicle/COND2")
    c = ctx["asum"]["condition"]
    assert c["major"] and c["runnable"] is False, "전제 — 중대 손상 낱말 · 시동 불가(두 로즈 칩이 서는 물건)"
    assert COND_ROSE.format("bg-rose-50 text-rose-700", "warning", "외관·상태 손상 언급") in html
    assert COND_ROSE.format("bg-rose-50 text-rose-700", "do_not_disturb_on", "시동·운행 불가 언급") in html
    assert "bg-rose-50 text-rose-600 border border-rose-200" not in html


def test_대조군_2단계_경미_손상_앰버_칩_그대로(cond, get):
    cond("COND1", "앞범퍼에 긁힌 흔적이 있음.")
    ctx, html = get("/vehicle/COND1")
    c = ctx["asum"]["condition"]
    assert c["minor"] and not c["major"] and not c["poor"], "전제 — 경미 손상만(앰버 칩 갈래)"
    assert COND_MINOR in html
