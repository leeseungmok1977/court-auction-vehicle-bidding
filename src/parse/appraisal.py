"""감정평가 요항(자유서술) 구조화 — 표시·밸류에이션 보조.

대법원 경매의 감정 요항은 감정인마다 형태가 제각각인 자유서술이라, 색상·연료·주행·
검사유효기간·옵션·상태(손상/관리/시동)를 **보수적으로** 추출한다. 확신이 없으면 비우고
원문을 함께 노출한다(신뢰도 최우선 — 추정으로 원문을 대체하지 않음).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .detail_parser import _strip_report, _fuel_from_text, _mileage_from_text

# 옵션 표준명 → 표기 변형
_OPTION_KW = {
    "네비게이션": ["네비게이션", "네비"],
    "후방카메라": ["후방카메라", "후방 카메라", "후방모니터"],
    "블랙박스": ["블랙박스"],
    "선루프": ["선루프", "썬루프", "파노라마"],
    "가죽시트": ["가죽시트", "가죽 시트", "레자시트"],
    "열선시트": ["열선시트", "열선 시트", "열선시트"],
    "통풍시트": ["통풍시트", "통풍 시트"],
    "하이패스": ["하이패스"],
    "스마트키": ["스마트키"],
    "크루즈컨트롤": ["크루즈"],
    "자동변속": ["오토", "자동변속"],
}
# 자유서술의 외관/기계 손상 표현(보험이력 정형구는 _strip_report로 제거 후 스캔).
# 경미(외관 도장/긁힘류)와 중대(구조/기계/부식류)를 구분.
_DAMAGE_MINOR = ["긁", "벗겨", "찍", "스크래치", "변색", "마모", "손상", "훼손", "기스"]
_DAMAGE_MAJOR = ["파손", "깨", "찌그러", "우그러", "부식", "누수", "누유", "탈거", "찢", "침수"]
# 전반적 관리불량 표현
_POOR_KW = ["좋지 못", "좋지못", "불량", "노후", "심한 편", "열악", "관리가 안"]
# 상태·손상을 서술한 문장을 추리기 위한 신호어(읽기용 발췌)
_COND_SENT_KW = ["외관", "상태", "시동", "운행", "관리", "결함", "긁", "찍", "벗겨", "도장",
                 "파손", "손상", "부식", "훼손", "깨", "찌그", "변색", "마모", "누유", "누수",
                 "정비", "교체", "수리", "이상"]


def parse_appraisal(text: str, today: Optional[date] = None) -> Optional[dict]:
    """요항 텍스트 → 구조화 dict. 추출 불가 항목은 None/빈값(원문은 raw로 보존)."""
    if not text or not text.strip():
        return None
    today = today or date.today()
    clean = _strip_report(text)   # 보험사고이력 정형 카운트 제거(‘0건’ 손상 오탐 방지)

    # 색상: 'OO색' + (임/이며/계열/문장끝/구두점) — '검정색.' 같은 단독 표기도 포착
    m = re.search(r"([가-힣]{1,4})색\s*(?:임|이며|계열|입니다|이고|\.|,|\n|$)", text)
    color = (m.group(1) + "색") if m else None

    # 검사/등록 유효기간: 'YYYY.MM.DD ~ YYYY.MM.DD' (구분자 사이 '.'·공백 허용: '18.~ 2026')
    inspection = None
    dm = re.search(r"(\d{4})[.\-/]\s?(\d{1,2})[.\-/]\s?(\d{1,2})\.?\s*~\s*"
                   r"(\d{4})[.\-/]\s?(\d{1,2})[.\-/]\s?(\d{1,2})", text)
    if dm:
        try:
            vf = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            vt = date(int(dm.group(4)), int(dm.group(5)), int(dm.group(6)))
            inspection = {"valid_from": vf.isoformat(), "valid_to": vt.isoformat(),
                          "expired": vt < today, "days_left": (vt - today).days}
        except ValueError:
            inspection = None

    options = [name for name, kws in _OPTION_KW.items() if any(k in text for k in kws)]

    # 손상 키워드 — 부정어(없음/아님)가 바로 뒤에 오는 출현은 제외(‘파손 없음’ 오탐 방지)
    def _kw_present(t: str, kw: str) -> bool:
        for m in re.finditer(re.escape(kw), t):
            if not re.search(r"없|아니|아님", t[m.end():m.end() + 7]):
                return True
        return False

    minor = sorted({k for k in _DAMAGE_MINOR if _kw_present(clean, k)})
    major = sorted({k for k in _DAMAGE_MAJOR if _kw_present(clean, k)})
    damage = minor + major
    poor = any(k in clean for k in _POOR_KW)
    runnable = None
    if re.search(r"(시동|운행)[^.]{0,12}(가능|양호)", clean):
        runnable = True
    if re.search(r"(시동|운행)[^.]{0,12}(불가|불능|안 ?됨|되지\s*않)", clean):
        runnable = False

    # 등급(밸류에이션용, 보수적): 관리불량·중대손상 → poor / 경미손상 → fair / 그 외 → unknown
    # ★ 키워드 부재를 '양호(good)'로 단정하지 않는다 — 요항은 자유서술이라 놓칠 수 있음.
    if poor or major:
        level = "poor"
    elif minor:
        level = "fair"
    else:
        level = "unknown"

    # 상태·손상 서술 문장 발췌(읽기용) — 옵션·연료·색상·기간만 있는 줄은 제외
    lines = re.split(r"(?<=음\.)\s*|(?<=임\.)\s*|\n", text)
    note_lines = []
    for ln in lines:
        s = ln.strip()
        if not s or not any(w in s for w in _COND_SENT_KW):
            continue
        # 옵션 나열 문장은 상태서술이 아님(설치되어 있음 등) → 제외
        if ("설치" in s or "장착" in s) and not any(w in s for w in
                ("외관", "긁", "찍", "벗겨", "파손", "손상", "부식", "결함", "이상")):
            continue
        note_lines.append(s)

    return {
        "color": color,
        "fuel": _fuel_from_text(text),
        "mileage": _mileage_from_text(text),
        "inspection": inspection,
        "options": options,
        "condition": {
            "level": level,            # unknown | fair | poor  (good은 쓰지 않음)
            "damage": damage,          # 발견된 손상 표현
            "minor": minor,
            "major": major,
            "poor": poor,
            "runnable": runnable,      # True/False/None
            "has_note": bool(note_lines),
        },
        "note_lines": note_lines,      # 상태 서술 문장(읽기용)
        "raw": text.strip(),
    }


def condition_adjustment(text: str, config: dict, today: Optional[date] = None) -> dict:
    """상태·검사 기반 추가 정비/비용(밸류에이션용). config.condition_costs 사용.

    반환: {add: 추가 차감액(원), flags: [사유], parsed: parse_appraisal 결과}
    확신 없거나 텍스트 없으면 add=0.
    """
    parsed = parse_appraisal(text, today)
    if not parsed:
        return {"add": 0, "flags": [], "parsed": None}
    costs = (config or {}).get("condition_costs", {}) or {}
    add, flags = 0, []
    lvl = parsed["condition"]["level"]
    if lvl == "poor":
        add += int(costs.get("poor", 0)); flags.append("관리·외관 불량")
    elif lvl == "fair":
        add += int(costs.get("fair", 0)); flags.append("외관 경미 손상")
    insp = parsed.get("inspection")
    if insp and insp.get("expired"):
        add += int(costs.get("inspection_expired", 0)); flags.append("자동차검사 유효기간 경과")
    if parsed["condition"]["runnable"] is False:
        add += int(costs.get("not_runnable", 0)); flags.append("시동·운행 불가 언급")
    return {"add": add, "flags": flags, "parsed": parsed}
