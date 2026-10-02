"""자동차 물건 상세 응답 파싱 (설계서 L3/FLOW-02, TASK-03).

입력: /pgj/pgj15B/selectAuctnCsSrchRslt.on 응답의 data.dma_result
출력: DetailInfo (차량 상세 + 회차별 최저가 + 감정 요항 텍스트 + 사고 1차 판정 + 사진 메타)

핵심 필드(실측, PGJ154M03.xml / 실제 응답 확인):
  gdsDspslObjctLst[i].drvnDistIndctCtt  주행거리(km)   ← 목록에 없던 값
  gdsDspslObjctLst[i].carDsplcCtt       배기량(cc)
  gdsDspslObjctLst[i].carVidCtt         차대번호(VIN)
  dspslGdsDxdyInfo.*PbancLwsDspslPrc    회차별 최저매각가(기일이력)
  dspslGdsDxdyInfo.dspslGdsSpcfcEcdocId 감정평가서/명세서 전자문서 ID
  aeeWevlMnpntLst[].aeeWevlMnpntCtt     감정평가 요항 텍스트(사고 판정 근거)
  csPicLst[].picFile                    사진(base64) — 별도 다운로드 불필요

두 번호(AUD-18, Steward 라이브 검증 2026-10-02 — 법원 요청 4회):
  요청 dspslGdsSeq = 목록 maemulSer = **매각물건 번호**. 응답 gdsDspslObjctLst[].dspslObjctSeq = 목록 mokmulSer
  = **목적물 번호** = 우리 item_no. doc_id 끝 두 자리가 (매각물건, 목적물)이다. 일괄매각이면 매각물건 하나에
  목적물이 여럿이다 — [0] 은 남의 차일 수 있어 **목적물 번호로 고른다**(pick_vehicle_object).
  감정요항의 '기호N' 도 목적물 번호다(53697 사건: 기호4 = 벤츠, 기호3 = 기아 — 매각물건 3 의 목적물은 4).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

# 기본 사고/침수 키워드 (config 미제공 시 fallback; 실제로는 config.yaml 사용)
_DEFAULT_ACCIDENT = ["사고", "판금", "교환", "부식", "훼손", "파손", "손상"]
_DEFAULT_FLOOD = ["침수", "전손"]


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    s = re.sub(r"[,\s㎞km]", "", str(v))
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def _fmt_date(v) -> Optional[str]:
    s = str(v or "").strip()
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"\d{8}", s) else None


def _hhmm(v) -> Optional[str]:
    """매각 시각 코드('1000'/'1030') → 'HH:MM'. 유효 시각(00~23시,00~59분)만."""
    s = str(v or "").strip()
    if re.fullmatch(r"\d{4}", s) and int(s[0:2]) < 24 and int(s[2:4]) < 60:
        return f"{s[0:2]}:{s[2:4]}"
    return None


def _sale_time(dx: dict, fail_count: Optional[int]) -> Optional[str]:
    """다음 매각기일의 입찰 시각 — 회차별 시각(fst/scnd/thrd/foth DspslHm) 중 현재 회차값.

    유찰 횟수가 곧 진행한 매각기일 수이므로 그 인덱스(범위초과 시 마지막 유효값)를 쓴다.
    법원 입찰 시각은 회차 간 대개 동일하나, 응답의 실제 값만 사용(추측 금지)."""
    raw = [dx.get("fstDspslHm"), dx.get("scndDspslHm"),
           dx.get("thrdDspslHm"), dx.get("fothDspslHm")]
    times = [t for t in raw if _hhmm(t)]
    if not times:
        return None
    idx = min(fail_count or 0, len(times) - 1)
    return _hhmm(times[idx])


def _clean(v) -> str:
    # &amp;quot; 같은 이중 이스케이프 정리
    return html.unescape(html.unescape(str(v or ""))).strip()


def _fuel_from_text(text: str) -> Optional[str]:
    """감정 요항 텍스트에서 연료 추출 (엔카 FuelType 표기와 맞춤). 코드보다 신뢰 가능."""
    if not text:
        return None
    if "하이브리드" in text:
        return "하이브리드"
    if "전기차" in text or "전기자동차" in text:
        return "전기"
    if "디젤" in text or "경유" in text:
        return "디젤"
    if "가솔린" in text or "휘발유" in text:
        return "가솔린"
    if "LPG" in text or "엘피지" in text or "lpg" in text:
        return "LPG"
    return None


def _mileage_from_text(text: str, item_no=None) -> Optional[int]:
    """감정 요항 텍스트에서 주행거리 추출 (구조화 필드가 빈 경우 보조).

    예: '계기판상 주행거리는 52,902㎞임.' / '주행거리 123,456km'

    ⚠ 다물건 감정서는 기호1~N의 주행거리를 한 줄에 나열한다. 첫 매치를 잡으면
    **남의 차 주행거리가 이 차에 붙는다** — 2025타경101362에서 기호3 그랜저(70,842km)가
    148,589km(기호1 값)로 표시됐고, 그 값이 시세 매칭·상한선까지 전파됐다
    (5회차 중고차 P0). item_no가 있으면 그 기호 구간에서만 찾는다.
    """
    if not text:
        return None
    from .appraisal import is_multi_symbol, slice_for_symbol
    if is_multi_symbol(text):
        sub, ok = slice_for_symbol(text, item_no)
        if not ok:
            return None          # 어느 차 것인지 모르면 값을 만들지 않는다
        text = sub
    m = re.search(r"주행거리[^0-9]{0,15}([0-9][0-9,]{1,})\s*(?:㎞|km|키로|킬로)", text)
    if not m:
        m = re.search(r"([0-9][0-9,]{2,})\s*(?:㎞|km)", text)
    return _to_int(m.group(1)) if m else None


# 주소로 인정할 최소 조건 — **행정구역/도로명 토큰이 반드시 있어야 한다.**
# '물류·창고·주차장'만 있으면 상호일 뿐 주소가 아니다(실측: "아줌마주차장"이
# 보관장소로 채택되던 오탐). 상호는 주소를 보조할 뿐 대체하지 못한다.
_STORAGE_HINT = re.compile(
    r"[가-힣]{2,}(?:특별자치시|특별자치도|특별시|광역시)"
    r"|[가-힣]{2,}(?:시|군|구|읍|면|동|리)(?:\s|$|[0-9])"
    r"|[가-힣0-9]{2,}(?:로|길)\s*[0-9]"
    r"|[0-9]+\s*(?:-\s*[0-9]+)?\s*번지")

# 주소 뒤에 붙어 오는 서술 꼬리 — 잘라낸다.
# 예: "…번영로 1130-12번지, 시전 내에보관중입니다" / "…224-1'여대주차장'에 주차중이며, 동소에서 실사하였음"
_STORAGE_TAIL = re.compile(
    r"\s*(?:에\s*(?:주차|보관|소재)\s*(?:중|되어)?.*$"
    r"|내에\s*보관.*$|보관\s*중.*$|동소에서.*$|,?\s*실사.*$|이며.*$|입니다.*$|임\s*\.?$)")


def _storage_from_text(*texts) -> str:
    """감정평가 요항·매각물건명세에서 '차량 보관장소'를 추출한다(구조화 필드가 빈 경우 보조).

    법원 자동차 감정서는 보관장소를 텍스트로만 기재하는 경우가 많다. 예:
      '본건 자동차는 지정 보관장소(경기도 광주시 도척면 진우리 844-14, 강남물류)에 주차되어 있는…'
      '보관장소 : 서울 강서구 …'
    → 괄호 안 주소 → 콜론 뒤 주소 → '…에 주차/보관/소재' 앞 주소 순으로 시도. 주소 힌트가 있어야 채택.
    """
    text = "\n".join(_clean(t) for t in texts if t)
    if not text:
        return ""
    # ⚠ 1,318건 전수 실측: '보관장소' 언급 91건 중 아래 3개 패턴으로 56건(62%)만 잡혔다.
    #   놓친 형태는 모두 조사가 붙고 구두점이 없는 실제 문장체였다:
    #     "보관장소는 경기도 안양시 동안구 엘에스로 99 소재 '중부모터스' 구내이며"
    #     "본건 자동차의 보관장소는 경상남도 창원시 성산구 남면로 319임."
    #     "보관장소 ㆍ경상남도 창원시 마산합포구 가포동 619번지."
    #     '보관장소는 "서울특별시 강서구 마곡동 1045번지 (금화주차장)"임.'
    #   반대로 주소가 아예 없는 언급("보관장소 여건상", "보관장소 내에서 재확인",
    #   "보관장소 입고일 현재 주행거리")은 잡으면 안 된다 — 그래서 종결형을 못박는다.
    pats = (
        r"보관\s*장소[^\n(]{0,10}\(\s*([^)\n]{4,90}?)\s*\)",              # 지정 보관장소(주소)
        r"보관\s*장소\s*(?:은|는|이|가)?\s*[:：]\s*([가-힣0-9][^\n.]{3,80})",  # 보관장소 : 주소
        # 보관장소는 "<주소>"임 / 보관장소 ㆍ<주소>. — 인용부호·불릿 형태
        r"보관\s*장소\s*(?:은|는|이|가)?\s*[ㆍ·]?\s*[\"'“”]([^\"'“”\n]{4,90}?)[\"'“”]",
        # 보관장소는 <주소> 소재/구내/임/이며   ← 실제로 가장 많은 형태
        # 후보 안에 따옴표가 들어올 수 있다("…언양로 605 '복산주차장'임"). 막으면
        # 그 형태를 통째로 놓치므로 허용하고, 짝 안 맞는 따옴표는 뒤에서 지운다.
        r"보관\s*장소\s*(?:은|는|이|가)\s*([가-힣][^\n]{4,80}?)"
        r"\s*(?:소재|구내|일원|일대|임\s*[.,]|이며|에\s*보관|에\s*주차|에\s*소재)",
        # 보관장소 ㆍ<주소>.  (불릿 뒤 바로 주소)
        r"보관\s*장소\s*[ㆍ·]\s*([가-힣][^\n]{4,80}?)\s*[.。]",
        r"([가-힣]{2,}(?:특별자치시|특별자치도|특별시|광역시|도|시)[^\n]{4,70}?)\s*에\s*(?:주차|보관|소재)",  # …에 주차/보관/소재
    )
    for p in pats:
        m = re.search(p, text)
        if not m:
            continue
        cand = re.sub(r"\s+", " ", m.group(1)).strip(" .,·:")
        cand = _STORAGE_TAIL.sub("", cand).strip(" .,·:'\"“”")
        # 짝이 안 맞는 따옴표는 통째로 뺀다 — "…언양로 605 '복산주차장" 처럼 남으면
        # 화면에 깨진 것처럼 보인다(신뢰가 1순위인 화면에서 값 자체를 의심하게 만든다).
        for qch in ("'", '"', "“", "”"):
            if cand.count(qch) % 2:
                cand = cand.replace(qch, "")
        # 원문 오기로 시·도명이 두 번 적히는 경우가 있다("경기도 경기도 용인시").
        cand = re.sub(r"^([가-힣]{2,}(?:특별자치[시도]|특별시|광역시|도))\s+\1\b", r"\1", cand)
        cand = re.sub(r"\s+", " ", cand).strip(" .,·:")
        if _STORAGE_HINT.search(cand) and 4 <= len(cand) <= 90:
            return cand
    return ""


# 보험개발원 사고이력 리포트 정형 카운트 (요항에 포함됨). 값이 '0건'이어도
# 단어('침수','전손','사고')가 나타나므로 단순 키워드 매칭은 오탐한다 → 카운트로 판정.
# 콜론(:) 유무·단위(건/회) 모두 허용 — 법원/감정인마다 표기가 다르다.
# 예: '내차 피해 : 6건'(정형) / '내차 피해 6회(19,150,135원)'(매각물건명세 서술형).
# 값은 카운트(>0)로만 사고 판정하므로 '0회/0건'은 안전하게 무사고 처리된다.
# ★ '피해' 없이 쓰는 서술형도 읽는다(REC-1, 2026-09-29): "중고차 사고 이력정보보고서는 내차 8회 및
#   상대차 2회의 사고 기록이 있습니다." 예전 패턴은 `내차\s*피해` 를 요구해 이 꼴을 통째로 놓쳤다 —
#   서버 appraisal.txt 1,543개 중 4건, 그중 BMW 520d(2026타경30118_1)는 '내차 8회'인데 건수를 못 읽어
#   건수별 감가표(7회 이상 30%) 대신 단일 15%를 받고 '지금 입찰 추천'에 들어가 있었다.
#   숫자가 '내차'(·'피해')·콜론 바로 뒤에 와야 한다 — "내차 수리비 … 3회" 같은 다른 문장은 잡지 않는다.
#   ⚠ "1회 258,930원의 내차피해"(숫자가 앞에 오는 꼴)는 아직 못 읽는다 — 이 경우는 건수 미상이라
#   단일 15%(표로는 10%)로 보수적인 쪽에 머문다.
_HIST_PATTERNS = {
    "total_loss": r"전손\s*보험사고\s*:?\s*(\d+)\s*[건회]",   # 전손
    "theft": r"도난\s*보험사고\s*:?\s*(\d+)\s*[건회]",         # 도난
    "flood": r"침수\s*보험사고\s*:?\s*(\d+)\s*[건회]",         # 침수
    "special_use": r"특수용도이력\s*:?\s*(\d+)\s*[건회]",
    "owner_changes": r"소유자\s*변경\s*:?\s*(\d+)\s*[건회]",
    "plate_changes": r"차량번호\s*변경\s*:?\s*(\d+)\s*[건회]",
    "own_damage": r"내차\s*(?:피해\s*)?:?\s*(\d+)\s*[건회]",
    "opp_damage": r"상대차\s*(?:피해\s*)?:?\s*(\d+)\s*[건회]",
}

# 직전 파서(REC-1 수정 전, 커밋 8073a3d)의 보험이력 패턴 — **파싱에 쓰지 않는다.**
# `python -m web.maint regrade-accidents` 가 "파서 수정으로 결과가 달라진 행"만 고르는 기준선이다
# (qa 2026-09-29 F4: 범위 없는 재등급은 요항 파일이 없는 행을 매각물건명세만으로 다시 매겨, 요항에만 있던
#  사고·침수 근거를 지우고 무사고로 내렸다 — 로컬 사본에서 HEAD 파서로도 23행이 바뀌었다).
# 다음에 _HIST_PATTERNS 를 고치면 이 자리를 **그 직전 패턴**으로 바꾸고 _BASELINE_REF 도 함께 바꾼다.
HIST_PATTERNS_BASELINE = {
    "total_loss": r"전손\s*보험사고\s*:?\s*(\d+)\s*[건회]",
    "theft": r"도난\s*보험사고\s*:?\s*(\d+)\s*[건회]",
    "flood": r"침수\s*보험사고\s*:?\s*(\d+)\s*[건회]",
    "special_use": r"특수용도이력\s*:?\s*(\d+)\s*[건회]",
    "owner_changes": r"소유자\s*변경\s*:?\s*(\d+)\s*[건회]",
    "plate_changes": r"차량번호\s*변경\s*:?\s*(\d+)\s*[건회]",
    "own_damage": r"내차\s*피해\s*:?\s*(\d+)\s*[건회]",
    "opp_damage": r"상대차\s*피해\s*:?\s*(\d+)\s*[건회]",
}
HIST_PATTERNS_BASELINE_REF = "8073a3d"

# 관리상태 등 자유 서술에서만 찾는 손상 표현(리포트 정형구에는 없음)
_DAMAGE_TEXT_KW = ["훼손", "판금", "교환", "부식", "파손", "손상"]


def parse_insurance_history(text: str, patterns: Optional[dict] = None) -> dict:
    """요항 텍스트의 보험사고이력 카운트를 구조화.

    patterns 는 재등급 범위를 정할 때 기준선(`HIST_PATTERNS_BASELINE`)과 대조하려고만 넘긴다.
    생략하면 현재 패턴이다."""
    out: dict[str, int] = {}
    for key, pat in (patterns if patterns is not None else _HIST_PATTERNS).items():
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1))
    return out


# ── 침수 오탐을 만드는 두 가지 서술 ──────────────────────────────────────
# 2026-09-21 사용자 지적("진짜 침수인가?")으로 운영 20대를 원문 대조한 결과,
# **14대가 부정문 오독**이었다. 아래 정형구 제거는 "침수 보험사고 : 0건" 같은 **숫자형**만
# 지우는데, 실제 원문은 숫자가 없는 서술형이라 그대로 남고 '침수' 낱말만 걸렸다.
#   · "중고차 사고이력 보고서상 전손 및 침수 **없음**"
#   · "전손 : 없음. 도난 : 없음. 침수 : **없음**."
#   · "자동차보험 특수사고이력(전손, 도난, 침수 등)은 **없으나** 내차 피해는 2회…"
#   · "전손, 도난, 침수 이력은 **없는 것으로 조회되었음**"
# 어제 고친 "시동이 **불**가능"을 긍정으로 읽던 것과 같은 구조다.
# 거리 90자: 실측(2024타경51422)에서 "전손 … 차량번호변경 없음"이 **64자**였다.
# 60자로 끊으면 나열이 긴 서술을 놓친다. 문장 경계([^.])는 유지해 다른 문장의 '없음'을
# 끌어오지 않는다.
_NEG_FLOOD = re.compile(
    r"(전손|도난|침수)[^.]{0,90}?"
    r"(없음|없고|없으나|없으며|없는|이력없|해당\s*없|무사고)")
# "침수차량 **여부도 재확인** 하시기 바랍니다" — 감정인이 확인을 요청한 것이지
# 침수라고 적은 것이 아니다(운영 4대). 이것을 의심으로 세면 정상차가 감가 100%를 맞는다.
_ASK_FLOOD = re.compile(r"침수[^.\n]{0,20}?(여부|확인)[^.\n]{0,30}?(재확인|바랍|요함|요망)")


def _strip_report(text: str) -> str:
    """보험사고이력 정형 카운트 구간을 제거해 키워드 오탐을 막는다(콜론 유무 무관).

    ⚠ 숫자형 정형구만으로는 부족하다 — 부정 서술(위 _NEG_FLOOD)과 확인 요청(_ASK_FLOOD)도
      함께 지운다. 지우지 않으면 '침수 없음'이 '침수'로 읽혀 감가 100%가 붙는다.
    ⚠ 원문은 줄 폭에 맞춰 **문장 중간에서 접힌다**("…전손 보험사고,도난 보험사고,침수⏎
      보험사고, … 차량번호변경 없음"). 줄바꿈을 그대로 두면 부정문이 끊겨 '침수'만 남는다
      (2024타경51422 실측: '전손'→'없음' 64자 사이에 줄바꿈 1개). 어제 시동 판정에서 겪은
      것과 같은 함정이라, 지우기 전에 **먼저 이어 붙인다.**"""
    t = re.sub(r"(?<![.!?])\n\s*", " ", text)
    t = _NEG_FLOOD.sub(" ", t)
    t = _ASK_FLOOD.sub(" ", t)
    # ⚠ "0건"은 **이력이 없다**는 뜻이다. 아래 기존 패턴은 '보험사고'라는 낱말을 요구해
    #   "전손 0건, 도난 0건, 침수 0건"(레인지로버 이보크)이나 "전손 : 0, 도난 : 0, 침수 : 0"
    #   (그랜저) 형태를 못 잡았다. 부정문 패턴도 '없음' 류만 보므로 숫자 0 은 안 걸린다.
    #   그 결과 _is_flood 가 '침수'를 찾아 **감가율 1.0(시세 전액)** 을 덮어썼다
    #   — grade_accident 는 보험 카운트가 있어 accident 로 맞게 판정했는데 값만 틀렸다.
    #   1건 이상은 진짜 이력이므로 **0 일 때만** 지운다.
    t = re.sub(r"(전손|도난|침수)\s*(보험사고|피해)?\s*[:：]?\s*0\s*[건회]?", " ", t)
    t = re.sub(r"(전손|도난|침수)\s*보험사고\s*:?\s*\d+\s*[건회]", " ", t)
    t = re.sub(r"(특수용도이력|소유자\s*변경|차량번호\s*변경|내차\s*피해|상대차\s*피해)"
               r"\s*:?\s*\d+\s*[건회][^-\n]*", " ", t)
    return t.replace("사고이력정보", " ").replace("보험사고", " ")


def grade_accident(appraisal_text: str, spec_remark: str = "",
                   config: Optional[dict] = None):
    """사고/침수 판정 — 감정평가서(요항) + 매각물건명세(비고) **모두**를 근거로.

    - 사고이력 카운트(내차피해·상대차피해·전손·침수 등)는 두 소스에서 추출(콜론 유무 무관).
      '중고차 사고이력정보보고서상 내차 피해 6회…'처럼 매각물건명세에만 있는 이력도 놓치지 않는다.
    - 자유서술 손상 키워드(판금·교환·부식·사고 등)는 **감정 요항 본문에서만** 스캔한다
      (매각물건명세의 '사고이력 없음' 정형구를 '사고' 키워드로 오탐하지 않도록 — 정상차 오판 방지).
    - 명시적 '사고이력 있음' 문구는 안전망으로 추가 반영('없음'은 매칭 안 함).
    반환: (grade, accident_hits, flood_hits, insurance_history). grade: none|accident|flood.
    """
    at = appraisal_text or ""
    sr = spec_remark or ""
    both = f"{at}\n{sr}"
    hist = parse_insurance_history(both)             # 카운트: 두 소스 모두
    cleaned = _strip_report(at)                       # 손상 키워드: 감정 요항 본문만(명세 정형구 오탐 방지)
    acc_kw = (config or {}).get("accident_keywords", _DEFAULT_ACCIDENT)
    fld_kw = (config or {}).get("flood_keywords", _DEFAULT_FLOOD)
    flood_hits: list[str] = []
    accident_hits: list[str] = []
    if hist.get("flood", 0) > 0:
        flood_hits.append("침수이력")
    if hist.get("total_loss", 0) > 0:
        flood_hits.append("전손이력")
    # 자유서술의 침수·전손 낱말은 **보험이력 카운트가 있어도** 본다(PANEL-60).
    # 예전엔 카운트가 있으면 자유서술을 건너뛰었다(초기 커밋) — 그때는 정형구("침수 보험사고 : 0건")를
    # 못 지워 카운트 문장 자체가 오탐원이었기 때문이다. 지금은 _strip_report 가 정형구·0건·부정문·
    # 확인요청을 먼저 지우므로 그 이유가 사라졌고, 게이트만 남아 **진짜 전손을 놓쳤다**:
    #   2026타경10406_1 "전손 사고 이력 : 보험사고 이력(2019-03-19, 수리비 39,080,000원) 존재함"
    #   → '차량번호 변경 1회' 카운트가 있어 자유서술을 건너뛰고 accident 로 내렸다. 같은 텍스트를
    #   calculator._is_flood 는 게이트 없이 읽어 '입찰 보류'로 판정 — 등급과 판정이 갈렸다.
    # 로컬 1,340건 실측: 게이트를 풀어 바뀌는 행은 이 한 건뿐(부정문 11건은 그대로 none/accident).
    flood_hits += [k for k in fld_kw if k in cleaned]
    if hist.get("own_damage", 0) > 0:
        accident_hits.append(f"내차피해{hist['own_damage']}회")
    if hist.get("opp_damage", 0) > 0:
        accident_hits.append(f"상대차피해{hist['opp_damage']}회")
    if hist.get("special_use", 0) > 0:
        accident_hits.append("특수용도이력")
    accident_hits += [k for k in acc_kw if k in cleaned]
    if re.search(r"사고\s*이력\s*[가이은는]?\s*있", both):   # 명시 '사고이력 있음' 안전망('없음' 제외)
        accident_hits.append("사고이력있음")
    flood_hits = sorted(set(flood_hits))
    accident_hits = sorted(set(accident_hits))
    grade = "flood" if flood_hits else "accident" if accident_hits else "none"
    return grade, accident_hits, flood_hits, hist


@dataclass
class DetailInfo:
    case_no: str
    court_code: str
    item_seq: str
    # 차량 상세
    maker: str
    model: str
    year: Optional[int]
    displacement_cc: Optional[int]
    mileage_km: Optional[int]
    fuel_code: str
    fuel_name: Optional[str]      # 요항 텍스트에서 추출한 연료(디젤/가솔린/LPG) — 코드보다 신뢰
    transmission_code: str
    reg_no: str
    vin: str
    storage_addr: str
    # 감정/기일
    appraisal_value: Optional[int]
    fail_count: Optional[int]
    sale_date: Optional[str]
    sale_time: Optional[str] = None   # 다음 매각기일 입찰 시각(HH:MM)
    sale_place: str = ""              # 매각(입찰) 장소 — 경매법정
    round_prices: list[int] = field(default_factory=list)  # 회차별 최저매각가
    appraisal_ecdoc_id: str = ""     # 감정평가서/명세서 전자문서 ID
    spec_remark: str = ""            # 매각물건명세 요약(gdsSpcfcRmk: 연식·주행·연료·유효검사·보험사고이력)
    # 감정 요항 / 사고 판정
    appraisal_text: str = ""
    insurance_history: dict = field(default_factory=dict)  # 구조화된 사고이력 카운트
    accident_hits: list[str] = field(default_factory=list)
    flood_hits: list[str] = field(default_factory=list)
    accident_grade: str = "none"     # none | accident | flood (bidcalc 입력)
    # 사진
    photo_count: int = 0
    # 기일내역 / 낙찰결과
    dxdy_history: list = field(default_factory=list)   # 회차별 기일·결과·낙찰가
    winning_price: Optional[int] = None                # 낙찰가 (매각된 경우)
    # 고른 목적물의 번호(dspslObjctSeq = 목록 mokmulSer = item_no). 응답에 번호가 없으면 ''(AUD-18).
    object_seq: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 이 물건의 목적물 고르기 · 응답 신원 확인 (AUD-18) ──────────────────────────────
# 예전 `_vehicle_obj` 는 gdsDspslObjctLst[0] 을 무조건 집었다. 일괄매각처럼 매각물건 하나에 목적물이 여럿이면
# [0] 은 남의 차다(예: 2026타경30359_2 '_1 과 일괄매각', doc 끝 '12'). 그리고 상세를 엉뚱한 매각물건 번호로
# 물으면 법원은 **옆 물건의 상세**를 그대로 준다 — 2025타경53697_4(벤츠 CLS350)에 매각물건 4(그랜드 스타렉스)의
# 2,497cc·디젤·'뒤바퀴 부식' 비고가 저장돼 있었다(운영 DB 10-02). 그래서 저장 전에 두 가지를 본다:
#   ① 응답의 사건(csNo)·법원(cortOfcCd)·매각물건(dspslGdsSeq)이 **보낸 값**과 같은가
#   ② 목적물 목록에 **dspslObjctSeq == item_no** 인 원소가 정확히 하나 있는가
_SEQ_RE = re.compile(r"[0-9]+")


def _seq(v) -> str:
    """순번 정규화 — 4 · '4' · ' 04 ' → '4'. 비었으면 ''. 숫자가 아니면 공백만 뗀 원문."""
    s = str(v if v is not None else "").strip()
    return str(int(s)) if _SEQ_RE.fullmatch(s) else s


def _objects(result: dict) -> list:
    return [o for o in (result.get("gdsDspslObjctLst") or []) if isinstance(o, dict)]


def _pick_object_index(result: dict, item_no=None) -> tuple:
    """(목적물 위치 또는 None, 사유). 사유가 matched·legacy·only 면 고른 것, 그 밖은 못 고른 것.

    - item_no(목적물 번호)를 주면: dspslObjctSeq 가 같은 원소 **하나**(matched). 없으면 not_found, 둘 이상 duplicate.
    - 응답에 dspslObjctSeq 가 아예 없는 옛 모양(축소 픽스처·합성 응답)이면 **목적물이 하나이고 매각물건 번호
      (dspslGdsSeq)가 item_no 와 같을 때만** 그것(legacy). 두 번호가 같으면 '어느 목적물인가'가 갈릴 여지가 없다 —
      운영 DB 1,621행 중 1,599행이 그 꼴이다. 그 밖은 고르지 않는다(unnumbered) — 모르면 남의 차를 집지 않는다.
    - item_no 를 모르는 호출(데모·검증 CLI·단위 테스트)은 목적물이 하나일 때만(only), 여럿이면 고르지 않는다(ambiguous).
    - 목적물이 없으면 (None, 'none') — 빈 응답(종결·취하·조회불가)은 호출부의 기존 규칙(상세없음)이 정한다."""
    lst = _objects(result)
    if not lst:
        return None, "none"
    want = _seq(item_no)
    if not want:
        return (0, "only") if len(lst) == 1 else (None, "ambiguous")
    if any(_seq(o.get("dspslObjctSeq")) for o in lst):
        hit = [i for i, o in enumerate(lst) if _seq(o.get("dspslObjctSeq")) == want]
        if len(hit) == 1:
            return hit[0], "matched"
        return None, ("duplicate" if hit else "not_found")
    dx = result.get("dspslGdsDxdyInfo") or {}
    gds = _seq(dx.get("dspslGdsSeq")) or _seq(lst[0].get("dspslGdsSeq"))
    if len(lst) == 1 and gds == want:
        return 0, "legacy"
    return None, "unnumbered"


def pick_vehicle_object(result: dict, item_no=None) -> tuple:
    """상세 응답(dma_result)에서 이 물건의 목적물 → (목적물 dict, 사유). 못 고르면 ({}, 사유). 규칙은 _pick_object_index."""
    idx, how = _pick_object_index(result, item_no)
    return (_objects(result)[idx] if idx is not None else {}), how


def _vehicle_obj(result: dict, item_no=None) -> dict:
    return pick_vehicle_object(result, item_no)[0]


_PICK_WHY = {"not_found": "목적물 {want} 없음", "duplicate": "목적물 {want} 중복",
             "unnumbered": "목적물 번호 없음 — 고를 수 없음", "ambiguous": "목적물 번호 미상 — 고를 수 없음"}


def detail_identity(resp_json: dict, sa_no, court_code, gds_seq, item_no) -> dict:
    """상세 응답이 **보낸 키의 물건**인가 — 저장(행 갱신·사진 폴더·분석) 전에 부른다(AUD-18). 외부 요청 0.

    sa_no·court_code·gds_seq = 보낸 csNo·cortOfcCd·dspslGdsSeq, item_no = 이 행의 목적물 번호.
    반환 {"ok", "reasons": [불일치 사유], "obj_index": 고른 목적물 위치(없으면 None), "pick": 사유, "got": 받은 값 요약}.

    규칙 — 값이 **있는데 다르면** 불일치다(없는 키는 비교하지 않는다):
      · 사건·법원: 기일정보(dspslGdsDxdyInfo — 요청 키를 그대로 되돌려 준다)의 csNo·cortOfcCd 가 보낸 값과 다르면
        다른 사건이다. 사건 단위 블록(csBaseInfo·사진·감정요항)은 보지 않는다 — 중복·병합 사건에서 그 값이 무엇인지
        원문을 본 적이 없다(C.4-3). 모르는 값으로 정상 상세를 막지 않는다.
      · 매각물건: 기일정보·목적물의 dspslGdsSeq 가 보낸 값과 다르면 다른 매각물건.
      · 목적물: `_pick_object_index` 가 못 고르면(not_found·duplicate·unnumbered·ambiguous) 불일치.
        목적물이 아예 없으면(none) 불일치로 보지 않는다 — 빈 응답은 호출부의 기존 규칙(상세없음)이 처리한다.
    실측(라이브 2건·픽스처): 실제 응답에는 위 키가 모두 있다. 키가 빠진 응답은 축소 픽스처·합성 응답뿐이다."""
    result = ((resp_json or {}).get("data") or {}).get("dma_result") if isinstance(resp_json, dict) else None
    result = result if isinstance(result, dict) else {}
    dx = result.get("dspslGdsDxdyInfo") or {}
    dx = dx if isinstance(dx, dict) else {}
    lst = _objects(result)
    want_cs, want_cc = str(sa_no or "").strip(), str(court_code or "").strip()
    want_gds, want_obj = _seq(gds_seq), _seq(item_no)
    reasons: list = []
    for key, want, label in (("csNo", want_cs, "사건"), ("cortOfcCd", want_cc, "법원")):
        got = str(dx.get(key) or "").strip()
        if got and want and got != want:
            reasons.append(f"{label} {got}≠{want}")
    gds_got = sorted({_seq(d.get("dspslGdsSeq")) for d in (dx, *lst)} - {""})
    bad = [g for g in gds_got if want_gds and g != want_gds]
    if bad:
        reasons.append(f"매각물건 {'·'.join(bad)}≠{want_gds}")
    idx, how = _pick_object_index(result, item_no)
    if how in _PICK_WHY:
        reasons.append(_PICK_WHY[how].format(want=want_obj or "?"))
    got = {"csNo": dx.get("csNo"), "cortOfcCd": dx.get("cortOfcCd"), "dspslGdsSeq": dx.get("dspslGdsSeq"),
           "objects": [[_seq(o.get("dspslObjctSeq")),
                        " ".join(str(o.get(k) or "").strip() for k in ("gdsVendNm", "carMdlNm", "carDelvYr")).strip()]
                       for o in lst]}
    return {"ok": not reasons, "reasons": reasons, "obj_index": idx if not reasons else None,
            "pick": how, "got": got}


def narrow_to_object(resp_json: dict, index) -> dict:
    """목적물 목록을 고른 하나로 줄인 **얕은 사본**(원본은 그대로). index 가 None 이면 원본을 그대로 돌려준다.

    저장·파싱(`parse_detail`·`save_item_folder` 의 detail.json)이 [0] 이 아니라 **확인한 목적물**을 읽게 한다.
    사진(csPicLst)·감정요항은 사건 단위라 그대로 둔다(사진 혼재는 DATA-03 계열 — 이번 범위 밖)."""
    if index is None or not isinstance(resp_json, dict):
        return resp_json
    data = dict(resp_json.get("data") or {})
    result = dict(data.get("dma_result") or {})
    result["gdsDspslObjctLst"] = [_objects(result)[index]]
    data["dma_result"] = result
    return {**resp_json, "data": data}


# 기일 결과 코드 (확인분). 매각(낙찰)은 낙찰가 + '비매각이 아닌' 코드로 판정.
DXDY_RESULT = {"002": "유찰", "003": "변경", "004": "취하", "005": "정지"}
_NON_SALE_CODES = {"002", "003", "004", "005"}  # 유찰·변경·취하·정지 = 매각 아님


def _parse_dxdy(result: dict):
    """기일내역(gdsDspslDxdyLst) → 회차별 목록(기일순) + 낙찰가. 매각기일(kndCd 01)만.

    낙찰은 낙찰가(dspslAmt>0)가 있고 결과코드가 유찰/변경/취하/정지가 **아닐** 때만
    인정한다(불허·재매각 잔액을 낙찰로 오인하지 않도록). 기일순 정렬로 최신 확정
    낙찰가를 채택한다.
    """
    rows = [r for r in (result.get("gdsDspslDxdyLst") or [])
            if str(r.get("auctnDxdyKndCd") or "") == "01"]
    rows.sort(key=lambda r: str(r.get("dxdyYmd") or ""))
    hist = []
    winning = None
    for r in rows:
        amt = _to_int(r.get("dspslAmt"))
        code = str(r.get("auctnDxdyRsltCd") or "")
        is_sale = bool(amt and amt > 0 and code not in _NON_SALE_CODES)
        # 기일순 진행: 매각이면 낙찰가 설정, 이후 비매각(재매각·유찰) 회차가 오면 무효화
        winning = amt if is_sale else None
        hist.append({
            "ymd": _fmt_date(r.get("dxdyYmd")),
            "result_code": code,
            "result": ("낙찰" if is_sale else DXDY_RESULT.get(code, "")),
            "lws_price": _to_int(r.get("tsLwsDspslPrc")),
            "dspsl_amt": amt,
        })
    return hist, winning


def parse_detail(resp_json: dict, config: Optional[dict] = None, item_no=None) -> DetailInfo:
    """상세 응답 → DetailInfo. `item_no`(목적물 번호)를 주면 그 목적물을 읽는다(AUD-18 — 규칙은
    `_pick_object_index`). 운영 경로(`web/service.py::_analyze_item`)는 `detail_identity` 로 확인한 뒤
    `narrow_to_object` 로 목적물을 하나로 줄인 응답을 넘긴다. 못 고르면 차량 필드는 비운다(남의 차를 집지 않는다)."""
    result = (resp_json.get("data", {}) or {}).get("dma_result", {}) or {}
    obj = _vehicle_obj(result, item_no)
    dx = result.get("dspslGdsDxdyInfo", {}) or {}

    # 감정 요항 텍스트
    texts = [_clean(r.get("aeeWevlMnpntCtt")) for r in (result.get("aeeWevlMnpntLst") or [])]
    appraisal_text = "\n".join(t for t in texts if t)

    # 주행거리: 구조화 필드 우선, 없으면 요항 텍스트에서 보조 추출
    mileage = _to_int(obj.get("drvnDistIndctCtt"))
    if mileage is None:
        # 다물건 감정서의 '기호N' 은 **목적물 번호**다(AUD-18). 예전엔 매각물건 번호(dspslGdsSeq)를 넘겨
        # 53697 사건 매각물건 3(목적물 4 벤츠)이 기호3(기아 237,768km)을 집을 수 있었다. 목적물 번호를 모르면
        # 넘기지 않는다 — 다물건 글이면 값을 만들지 않는다(_mileage_from_text 의 기존 규칙).
        _sym = _seq(item_no) or _seq(obj.get("dspslObjctSeq"))
        mileage = _mileage_from_text(appraisal_text, item_no=_sym or None)

    dxdy_history, winning_price = _parse_dxdy(result)

    # 사고 판정: 감정 요항 + 매각물건명세(비고) 모두를 근거로(카운트·손상키워드·명시문구).
    # 사고이력이 매각물건명세에만 기재된 경우(예: '내차 피해 6회…')도 무사고로 오판하지 않는다.
    grade, accident_hits, flood_hits, hist = grade_accident(
        appraisal_text, dx.get("gdsSpcfcRmk"), config)

    # 회차별 최저매각가
    rounds = []
    for k in ("fstPbancLwsDspslPrc", "scndPbancLwsDspslPrc",
              "thrdPbancLwsDspslPrc", "fothPbancLwsDspslPrc"):
        v = _to_int(dx.get(k))
        if v is not None:
            rounds.append(v)

    _fc = _to_int(dx.get("flbdNcnt"))
    return DetailInfo(
        case_no=str(dx.get("csNo") or obj.get("csNo") or "").strip(),
        court_code=str(dx.get("cortOfcCd") or obj.get("cortOfcCd") or "").strip(),
        item_seq=str(dx.get("dspslGdsSeq") or obj.get("dspslGdsSeq") or "").strip(),
        maker=_clean(obj.get("gdsVendNm")),
        model=_clean(obj.get("carMdlNm")),
        year=_to_int(obj.get("carDelvYr")),
        displacement_cc=_to_int(obj.get("carDsplcCtt")),
        mileage_km=mileage,
        fuel_code=str(obj.get("fuelKndCd") or "").strip(),
        fuel_name=_fuel_from_text(appraisal_text),
        transmission_code=str(obj.get("grbxTypCd") or "").strip(),
        reg_no=_clean(obj.get("objctRegNo")),
        vin=str(obj.get("carVidCtt") or "").strip(),
        storage_addr=(_clean(obj.get("storgPlcRdnmAddr") or obj.get("storgPlcAllLtnoAddr"))
                      or _storage_from_text(appraisal_text, dx.get("gdsSpcfcRmk"))),
        appraisal_value=_to_int(dx.get("aeeEvlAmt")),
        fail_count=_fc,
        sale_date=_fmt_date(dx.get("dspslDxdyYmd")),
        sale_time=_sale_time(dx, _fc),
        sale_place=_clean(dx.get("dspslPlcNm")),
        round_prices=rounds,
        appraisal_ecdoc_id=str(dx.get("dspslGdsSpcfcEcdocId") or "").strip(),
        spec_remark=_clean(dx.get("gdsSpcfcRmk")),
        appraisal_text=appraisal_text,
        insurance_history=hist,
        accident_hits=accident_hits,
        flood_hits=flood_hits,
        accident_grade=grade,
        photo_count=len(result.get("csPicLst") or []),
        dxdy_history=dxdy_history,
        winning_price=winning_price,
        object_seq=_seq(obj.get("dspslObjctSeq")),
    )
