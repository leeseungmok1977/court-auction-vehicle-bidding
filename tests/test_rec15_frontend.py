# -*- coding: utf-8 -*-
"""REC-15 화면 짝(지시서 2026-10-01-35) — 리포트 09 '사고·침수' 칩 · 상세 '사고판정' 말풍선.

REC-15(backend, 오너 승인)로 사고 근거(service.accident_evidence)가 좁아졌다 — 보험이력에 일반 사고 항목(내차·상대차 피해)
키가 있거나 사고 낱말(accident_hits)이 있을 때만 근거다. 소유자·차량번호 변경이나 특수사고(전손·도난·침수) 카운트만 있는
보험이력은 '이력 미확인'(2026타경50904_1 · 503268_1 등 8대).
  1. 리포트 09 칩은 `v.insurance_history`(dict 가 비지 않음)로 초록을 골라, 그 8대에서 칸 글자는 '이력 미확인'인데 칩은 초록
     '이력상 양호'였다. 이제 초록은 칸 글자(`_accl = v|accv`)가 '무사고'일 때만 — 상세 사고판정 칩(REC-13)과 같은 술어.
     STOP 갈래(`report.stop_active or _noest`)는 그대로 먼저.
  2. 상세 '사고판정' 말풍선에 '이력 미확인'의 뜻 한 문장(Steward 문구 그대로).
판정·근거의 정의는 바꾸지 않는다(service.py 무수정) — 화면이 이미 정해진 글자를 같은 색·같은 말로 따라가게 할 뿐이다.

각 테스트는 **전제를 먼저 단언**한다(그 갈래가 실제로 렌더되는 물건인지). 이름에 '대조군'이 붙은 테스트는 바뀌면 안 되는 렌더를
예전 그대로 단언한다(지시서 빨강 집계에서 뺀다). 외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import re

import pytest

from tests.test_rec13_frontend import BASE, CAUTION, OK, _chip, _cls_text
from tests.test_rec1_r3_picks_gate_block import _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec9_frontend import get  # noqa: F401 — 렌더 + 템플릿 문맥 캡처
from web import service

CHIP09 = re.compile(r'<td class="k">사고·침수</td>.*?<td class="c tagcell"><span class="chip ([a-z]+)">([^<]+)</span></td></tr>', re.S)
# 칸 글자 = v|accv — 뒤에 사고 낱말(' — …')과 고정 문구(' · 골격 손상 여부 현장 확인')가 붙는다
SUB09 = re.compile(r'<td class="k">사고·침수</td><td class="sub">([^<]*?)(?: — [^<]*)? · 골격 손상 여부 현장 확인</td>')
# Steward 문구(지시서 2026-10-01-35) — 글자 그대로. 템플릿이 홑따옴표를 &#39; 로 내보낸다(자동 이스케이프).
OLD_DESC = "감정평가서·이력을 근거로 한 사고 여부 표시예요. 골격(프레임) 사고·침수는 아무리 싸도 입찰 보류 대상입니다."
# 첫 문안(159자)은 큰글씨 320 에서 말풍선이 스크롤 영역 아래로 36px 넘어 Steward 가 줄였고, 둘째 문안('사고차라는 뜻은 아니고, 가격만 …')은
# 한쪽만 부정해 '실제로는 괜찮은 차'로 읽힐 여지가 있어 양쪽을 다 모른다고 고쳤다(design-critic 고칠 것 1 · Steward 확정 — 같은 지시서 이어서).
NEW_SENT = "'이력 미확인'은 사고 기록을 확인하지 못했다는 뜻이에요. 사고차인지 아닌지 모르니, 가격은 사고차로 가정해 계산합니다."


def _esc(t):
    return t.replace("'", "&#39;")


@pytest.fixture
def c15(mk):
    """값은 10-01 백업 사본의 모양 그대로(이름 옆 주석). 시세·상한가가 있어 리포트 본문(09 표)이 선다."""
    return {
        # REC-15 꼴 — 소유자·번호 변경만(2026타경50904_1 · 52708_1 · 50311_1 · 60319_1)
        "OWNPL": mk("OWNPL", accident_grade="none", insurance_history={"owner_changes": 3, "plate_changes": 1}, **BASE),
        # REC-15 꼴 — 특수사고 카운트만(2026타경503268_1: 전손 0 · 도난 0 · 침수 0)
        "SPCL": mk("SPCL", accident_grade="none", insurance_history={"total_loss": 0, "theft": 0, "flood": 0}, **BASE),
        # REC-15 꼴 — 둘이 섞임(일반 사고 키는 여전히 없음)
        "MIXD": mk("MIXD", accident_grade="none",
                   insurance_history={"owner_changes": 1, "plate_changes": 0, "total_loss": 0, "flood": 0}, **BASE),
        # 대조군 — 근거 있는 '무사고'(2026타경100009_1: 내차 0 · 상대차 0) · 내차 키 하나만 있어도 근거
        "EVK": mk("EVK", accident_grade="none", insurance_history={"own_damage": 0, "opp_damage": 0}, **BASE),
        "EVK1": mk("EVK1", accident_grade="none", insurance_history={"own_damage": 0, "owner_changes": 2}, **BASE),
        # 대조군 — 보험이력 없음(이미 앰버) · 사고(STOP) · 침수의심(STOP — 침수·전손 판정)
        "NOINS": mk("NOINS", accident_grade="none", **BASE),
        "ACCS": mk("ACCS", accident_grade="accident", insurance_history={"own_damage": 2, "opp_damage": 0},
                   accident_hits=["내차피해2회"], **BASE),
        "FLDS": mk("FLDS", accident_grade="flood", insurance_history={"owner_changes": 2}, **BASE),
        # 색 규칙만 보는 합성 — 단순수리(STOP 갈래 아님)·근거 있음(사본 0대). 칸 글자가 '무사고'가 아니니 초록이 아니다
        "MINORI": mk("MINORI", accident_grade="minor", insurance_history={"own_damage": 1, "opp_damage": 0}, **BASE),
    }


def _chip09(html):
    m = CHIP09.search(html)
    assert m, "전제 — 리포트 09 '사고·침수' 행이 렌더된다(본문 있는 리포트)"
    return m.groups()


# ── 1. 리포트 09 칩 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["OWNPL", "SPCL", "MIXD"])
def test_REC15_꼴은_리포트_09_칩도_앰버_이력_미확인(c15, get, vid):
    v = c15[vid]
    assert v["insurance_history"] and v["accident_grade"] == "none", "전제 — 보험이력 dict 가 비지 않은 등급 none(예전엔 초록)"
    assert not service.accident_evidence(v) and service.accident_label(v) == "이력 미확인", \
        "전제 — REC-15 근거 술어(일반 사고 항목 없음 → 근거 아님)"
    ctx, rep = get(f"/vehicle/{vid}/report")
    assert not ctx["report"]["stop_active"] and not (ctx["bidst"] or {}).get("no_estimate"), "전제 — STOP 갈래 아님"
    assert SUB09.search(rep).group(1) == "이력 미확인", "전제 — 같은 행 칸 글자"
    assert _chip09(rep) == ("warn", "이력 미확인"), "칸 글자는 '이력 미확인'인데 칩이 초록이면 안 된다"
    assert "이력상 양호" not in rep


@pytest.mark.parametrize("vid", ["EVK", "EVK1"])
def test_대조군_근거_있는_무사고는_리포트_09_초록_그대로(c15, get, vid):
    v = c15[vid]
    assert service.accident_evidence(v) and service.accident_label(v) == "무사고", "전제 — 일반 사고 항목 키가 있다(0건이어도 조회함)"
    _, rep = get(f"/vehicle/{vid}/report")
    assert _chip09(rep) == ("ok", "이력상 양호")


@pytest.mark.parametrize("vid,want", [("NOINS", ("warn", "이력 미확인")), ("ACCS", ("risk", "STOP 대상")),
                                      ("FLDS", ("risk", "STOP 대상"))], ids=["NOINS", "ACCS", "FLDS"])
def test_대조군_보험이력_없음_앰버_사고_침수_STOP_그대로(c15, get, vid, want):
    ctx, rep = get(f"/vehicle/{vid}/report")
    if vid != "NOINS":
        assert ctx["report"]["stop_active"] or (ctx["bidst"] or {}).get("no_estimate"), "전제 — STOP 갈래(먼저 잡는다)"
    assert _chip09(rep) == want


def test_리포트_09_칩_색과_칸_글자는_한_값에서(c15, get):
    """같은 행의 칸 글자(v|accv)와 칩이 갈라지지 않는다 — 초록 ⇔ 칸 글자 '무사고' (STOP 갈래 밖 전부)."""
    bad = []
    for vid in ("OWNPL", "SPCL", "MIXD", "EVK", "EVK1", "NOINS", "MINORI"):
        _, rep = get(f"/vehicle/{vid}/report")
        word = SUB09.search(rep).group(1)
        cls, txt = _chip09(rep)
        if (cls == "ok") != (word == "무사고") or (txt == "이력상 양호") != (word == "무사고"):
            bad.append((vid, word, cls, txt))
    assert not bad, bad


# ── 2. 상세 '사고판정' 말풍선 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("vid", ["OWNPL", "EVK"])
def test_사고판정_말풍선에_이력_미확인_뜻_한_문장(c15, get, vid):
    _, html = get(f"/vehicle/{vid}")
    pop = f'<span class="pop" role="tooltip"><b>사고판정</b> — {OLD_DESC} {_esc(NEW_SENT)}</span>'
    assert pop in html, "기존 두 문장 뒤에 Steward 문구 그대로"
    assert f'aria-label="사고판정 — {OLD_DESC} {_esc(NEW_SENT)}"' in html, "스크린리더 글자도 같은 문장"
    assert html.count("사고차인지 아닌지 모르니") == 2, "말풍선·aria-label 두 곳뿐"
    assert "근거 자료(보험이력의 사고 기록 등)" not in html, "첫 문안은 남지 않는다"
    assert "사고차라는 뜻은 아니고" not in html, "둘째 문안(한쪽만 부정)은 남지 않는다"
    # 칩은 1단계 그대로 — 말풍선 옆 칩이 글자와 같은 색
    assert _cls_text(_chip(html)) == ((CAUTION, "이력 미확인") if vid == "OWNPL" else (OK, "무사고"))
