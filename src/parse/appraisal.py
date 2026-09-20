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
# ⚠ 감정인은 감정평가사이지 국어교사가 아니다. 자유서술 원문에 오탈자·구어체가 정상으로 섞이고,
# 문자열 whitelist는 구조적으로 계속 샌다. 게다가 **새는 방향이 항상 같다** — 미탐이면 충당 과소
# → 상한선 과대 → 사용자가 더 많이 쓰게 된다. 로컬 감정서 1,305건 실측(2026-09-12 3회차):
#   스크레치류 32건 · 양호치 못함 6건 · 회손 1건. 표기 변형을 함께 잡는다.
_DAMAGE_MINOR = ["긁", "벗겨", "찍", "스크래치", "스크레치", "스크렛치", "스크레취",
                 "변색", "마모", "손상", "훼손", "회손", "기스"]
_DAMAGE_MAJOR = ["파손", "깨", "찌그러", "찌그럼", "찌그름", "우그러", "부식", "누수", "누유",
                 "탈거", "찢", "침수"]
# 전반적 관리불량 표현 — "양호치 못함"·"양호하지 않음"처럼 부정 어미가 붙는 형태 포함
_POOR_KW = ["좋지 못", "좋지못", "양호치 못", "양호치못", "양호하지 못", "양호하지 않",
            "불량", "노후", "심한 편", "열악", "관리가 안"]
# 상태·손상을 서술한 문장을 추리기 위한 신호어(읽기용 발췌)
_COND_SENT_KW = ["외관", "상태", "시동", "운행", "관리", "결함", "긁", "찍", "벗겨", "도장",
                 "파손", "손상", "부식", "훼손", "깨", "찌그", "변색", "마모", "누유", "누수",
                 "정비", "교체", "수리", "이상"]


# ── 다물건 감정서: 기호 단위 분리 ─────────────────────────────────
# 한 사건에 물건이 여러 개면 감정서 1부가 기호1~N을 함께 서술한다. 문서 전체를
# 스캔하면 **남의 차 정보가 이 차에 붙는다** — 5회차 실측(2025타경101362):
#   기호3 그랜저(실제 70,842km)가 화면에 148,589km(기호1 값)로 표시되고,
#   "기호2, 4는 시동이 안되는 상태" 문장에 걸려 **시동 멀쩡한 기호3에 STOP**이 붙었다.
#   매각기일이 남은, 지금 입찰 가능한 물건이었다.
#
# 기호는 "기호1", "기호(2)", "기호1, 3, 5는"처럼 나열로도 쓰인다. 그래서 문장이 아니라
# **기호 마커 위치로 텍스트를 쪼개** 각 구간을 그 기호 그룹에 귀속시킨다.
_SYM_GROUP = re.compile(r"기호\s*\(?\s*(\d{1,2}(?:\s*[,·]\s*\d{1,2})*)\s*\)?")


def _symbols(chunk: str) -> set:
    return {int(x) for x in re.findall(r"\d{1,2}", chunk or "")}


def is_multi_symbol(text: str) -> bool:
    """감정서가 여러 기호를 함께 서술하는가."""
    seen = set()
    for m in _SYM_GROUP.finditer(text or ""):
        seen |= _symbols(m.group(1))
    return len(seen) >= 2


def slice_for_symbol(text: str, item_no) -> tuple:
    """이 물건(기호 N)에 귀속되는 구간만 남긴다.

    반환: (해당 텍스트, 신뢰 가능 여부). 분리에 실패하면 (원문, False) —
    호출부는 False면 상태·시동·검사기간을 **미상으로 두어야 한다**. 남의 차 서술로
    판정하는 것보다 모른다고 하는 편이 낫다(이 제품의 기존 규칙).
    """
    if not text or not is_multi_symbol(text):
        return text, True
    try:
        want = int(str(item_no).strip())
    except (TypeError, ValueError):
        return text, False
    marks = list(_SYM_GROUP.finditer(text))
    if not marks:
        return text, False
    kept = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        if want in _symbols(m.group(1)):
            kept.append(text[m.start():end])
    if not kept:
        return text, False
    return " ".join(kept), True


# ── 시동·운행 판정 ──────────────────────────────────────────────────────
# 2026-09-20 사용자 지적("문구를 제대로 읽고 기재해야 되는데 그렇지 않은 게 있어 보여")으로
# 재작성. 예전에는 **문서 전체**에 정규식을 돌리고 `elif` 로 '불가'가 '가능'을 무조건 덮어,
# 원문이 "걸었다"고 적은 물건까지 '시동·운행 불가'로 표시했다. 운영 43건을 원문과 대조한
# 결과 5건이 명백한 오판이었다(반대 방향 미탐은 0건 — 한 방향으로만 틀리고 있었다).
#   · G70        "시동이 켜지지 않아 점프선을 연결하여 정상시동을 확인하였고"
#   · 한성윙바디  "시동이 걸리지 않아 출장업체의 도움으로 시동을 걸었습니다"
#   · 투싼        "자체 시동 불가함 … 용역 의뢰하여 시동 실험 결과 시동가능함"
#   · 디스커버리  "시동이 걸리지 않아 긴급충전을 통해 주행거리를 확인하였으며"
#   · 고소작업차  "현재 시동상태 또한 양호하나, 향후 … 불량일 수도 있음"(미래 가정을 현재로 읽음)
# '가동·작동'도 걸린다는 뜻이다 — "시동은 정상 가동됨"(50911 기호1·2 원문)이 미상으로
# 빠지고 있었다. 아래 판정 순서가 '불가 → 가능'이라 "시동 작동 불량"은 여전히 불가로 잡힌다.
_RUN_POS = re.compile(r"(시동|운행)[^.]{0,14}(가능|양호|보통|가동|작동)")
# ⚠ '확인 불가'는 **못 봤다**는 뜻이지 못 움직인다는 뜻이 아니다(2026-09-12 코퍼스 실측 27건).
#    범위를 넓히지 않는다 — "시동이 걸리지 않아 …확인할 수 없었습니다"까지 미상으로 만들면
#    실제로 안 걸린 차를 놓친다(짚그랜드체로키가 그 형태다).
_RUN_UNK = re.compile(r"(시동|운행)[^.]{0,16}(확인\s*(이|은)?\s*불가|확인\s*되지\s*않|미확인)")
_RUN_NEG = re.compile(r"(시동|운행)[^.]{0,16}(불가|불능|불량|안\s?됨|안\s?되|(?:되|걸리|켜지)지\s*않)")
# 가정법("불량일 수도 있음")은 현재 사실이 아니다 — 지금 양호한 차를 불가로 만들었다.
_RUN_MAYBE = re.compile(r"\s*(일|할|될|이|하|되)?\s*수\s?도?\s*있|\s*가능성")
# ⚠ 되살린 **수단**만 보고 회복으로 읽으면 안 된다. "배터리 점프를 시도하여도 시동이
#    걸리지 않았으며"(코란도)가 정확히 그 함정이다. 수단 + **실제로 걸렸다는 완료 서술**이
#    같은 문장에 함께 있을 때만 '점프 시동'으로 본다.
_RUN_AGENT = re.compile(r"점프|충전|보조\s?배터리|배터리\s?교체|배터리로\s?교체|용역|출장")
# ⚠ '확인하였다'와 '확인 대상이다'는 다른 말이다. 완료 어미를 요구하지 않으면
#    "확인이 어려운 상태로 **정상시동 확인**, 기관, 본체, …"(천공기) 같은 **점검 항목 나열**을
#    완료로 읽는다. 실제로 초안이 그렇게 읽었다(2026-09-20 로컬 전건 재파싱에서 적발).
# ⚠⚠ `시동[^.]{0,6}가능` 은 **"시동이 불가능"의 '가능'에 걸린다.** 초안이 실제로 그랬고,
#     "배터리가 방전되어 시동이 불가능하며 배터리교체를 요합니다"(인터내셔널프로스타)를
#     '점프로 시동됨'이라 적을 뻔했다. 부정을 긍정으로 뒤집는 것이라 가장 나쁜 오류다.
#     → '가능' 바로 앞이 '불'이면 매치하지 않는다.
_RUN_DONE = re.compile(r"정상\s?시동을?\s?확인(하|했|함|됨)|시동[^.]{0,6}(?<!불)가능"
                       r"|시동을?\s?걸었|확인한\s?주행거리|주행거리를?\s?확인")
# 결과를 말하지 않는 서술 — 이게 붙으면 '가능'도 '완료'도 아니다.
#   · "시동가능 여부는 확인하였으나"(A7)      → 확인 행위만, 결과 없음
#   · "시동 및 운전가능성 여부를 확인"(K7)     → 같은 구조
#   · "정상 운행이 가능했던 것으로 조사되나"(G70) → 과거·전문(傳聞)이지 현재 상태가 아니다
_RUN_PAST = re.compile(r"\s*(했던|하였던|였던|던\s*것)")


def _affirmed(s: str, m) -> bool:
    """이 매치가 **현재 상태에 대한 단정**인가. '여부'·과거형·부정이면 아니다."""
    tail = s[m.end():m.end() + 10]
    if _RUN_PAST.match(tail):
        return False
    # "정상시동을 확인하지 못하였음" · "주행거리를 확인하지 못함" — 완료형 뒤의 부정.
    if re.match(r"\s*지\s*(못|않)", tail):
        return False
    return "여부" not in s[m.start():m.end() + 8]


def _runnable_of(clean: str):
    """시동·운행 상태 — True(가능) / False(불가) / 'jump'(점프 시동) / None(미상).

    문서 전체가 아니라 **문장 단위**로 본다. 감정요항은 한 문장 안에서 상태가 뒤집힌다
    ("~걸리지 않아 ~점프하여 정상시동을 확인하였고"). 앞부분만 읽으면 정반대로 적게 된다.
    """
    # ⚠ 감정요항 원문은 줄 폭에 맞춰 **문장 중간에서 줄바꿈**된다(사이에 빈 줄이 끼기도 한다).
    #   줄바꿈에서 그대로 자르면 "…시동이 걸리지 않아 긴급충전을 통해" 까지만 읽고 끝나
    #   뒤에 오는 "주행거리를 확인하였으며"(=걸렸다)를 못 본다 — 이 함수가 고치려던
    #   "끝까지 안 읽는" 문제가 줄바꿈 때문에 되살아난다. 2026-09-21 운영 실측
    #   (2025타경10002 디스커버리): 같은 코드가 로컬은 jump, 운영은 불가였고 원인이 이것이었다.
    #   마침표로 끝나지 않는 줄바꿈은 **이어 붙인 뒤에** 문장을 가른다(사람이 읽는 방식).
    clean = re.sub(r"(?<![.!?])\n\s*", " ", clean)
    pos = neg = jump = False
    for s in re.split(r"(?<=\.)\s*|\n", clean):
        if "시동" not in s and "운행" not in s:
            continue
        if _RUN_AGENT.search(s) and any(_affirmed(s, m) for m in _RUN_DONE.finditer(s)):
            jump = True
            continue                      # 되살아난 문장은 '불가'로 세지 않는다
        if _RUN_UNK.search(s):
            continue                      # 확인 불가 — 어느 쪽으로도 세지 않는다
        # 한 문장에 가정법 '불량'과 실제 '불가'가 같이 올 수 있어 전부 훑는다.
        if any(not _RUN_MAYBE.match(s[m.end():m.end() + 12]) for m in _RUN_NEG.finditer(s)):
            neg = True
        elif any(_affirmed(s, m) for m in _RUN_POS.finditer(s)):
            pos = True
    if jump:
        return "jump"
    if neg:
        return False                      # 보수적: 불가가 가능을 이긴다(다물건 서술 대비)
    if pos:
        return True
    return None


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
    # "시동상태 보통"도 시동이 걸린다는 뜻이다(다물건 감정서에서 흔한 표현).
    # 판정은 _runnable_of 한 곳에서 — 문장 단위로 보고 회복·가정법까지 가른다(위 주석).
    runnable = _runnable_of(clean)

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
