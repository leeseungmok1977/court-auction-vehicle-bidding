"""자동차 물건 상세 응답 파싱 (설계서 L3/FLOW-02, TASK-03).

입력: /pgj/pgj15B/selectAuctnCsSrchRslt.on 응답의 data.dma_result
출력: DetailInfo (차량 상세 + 회차별 최저가 + 감정 요항 텍스트 + 사고 1차 판정 + 사진 메타)

핵심 필드(실측, PGJ154M03.xml / 실제 응답 확인):
  gdsDspslObjctLst[0].drvnDistIndctCtt  주행거리(km)   ← 목록에 없던 값
  gdsDspslObjctLst[0].carDsplcCtt       배기량(cc)
  gdsDspslObjctLst[0].carVidCtt         차대번호(VIN)
  dspslGdsDxdyInfo.*PbancLwsDspslPrc    회차별 최저매각가(기일이력)
  dspslGdsDxdyInfo.dspslGdsSpcfcEcdocId 감정평가서/명세서 전자문서 ID
  aeeWevlMnpntLst[].aeeWevlMnpntCtt     감정평가 요항 텍스트(사고 판정 근거)
  csPicLst[].picFile                    사진(base64) — 별도 다운로드 불필요
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


def _mileage_from_text(text: str) -> Optional[int]:
    """감정 요항 텍스트에서 주행거리 추출 (구조화 필드가 빈 경우 보조).

    예: '계기판상 주행거리는 52,902㎞임.' / '주행거리 123,456km'
    """
    if not text:
        return None
    m = re.search(r"주행거리[^0-9]{0,15}([0-9][0-9,]{1,})\s*(?:㎞|km|키로|킬로)", text)
    if not m:
        m = re.search(r"([0-9][0-9,]{2,})\s*(?:㎞|km)", text)
    return _to_int(m.group(1)) if m else None


_STORAGE_HINT = re.compile(r"(시|도|군|구|읍|면|동|리|로|길|번지|물류|창고|야적|주차장)")


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
    pats = (
        r"보관\s*장소[^\n(]{0,10}\(\s*([^)\n]{4,90}?)\s*\)",              # 지정 보관장소(주소)
        r"보관\s*장소\s*(?:은|는|이|가)?\s*[:：]\s*([가-힣0-9][^\n.]{3,80})",  # 보관장소 : 주소
        r"([가-힣]{2,}(?:특별자치시|특별자치도|특별시|광역시|도|시)[^\n]{4,70}?)\s*에\s*(?:주차|보관|소재)",  # …에 주차/보관/소재
    )
    for p in pats:
        m = re.search(p, text)
        if m:
            cand = re.sub(r"\s+", " ", m.group(1)).strip(" .,·:")
            if _STORAGE_HINT.search(cand) and 4 <= len(cand) <= 90:
                return cand
    return ""


# 보험개발원 사고이력 리포트 정형 카운트 (요항에 포함됨). 값이 '0건'이어도
# 단어('침수','전손','사고')가 나타나므로 단순 키워드 매칭은 오탐한다 → 카운트로 판정.
_HIST_PATTERNS = {
    "total_loss": r"전손\s*보험사고\s*:\s*(\d+)\s*건",   # 전손
    "theft": r"도난\s*보험사고\s*:\s*(\d+)\s*건",         # 도난
    "flood": r"침수\s*보험사고\s*:\s*(\d+)\s*건",         # 침수
    "special_use": r"특수용도이력\s*:\s*(\d+)\s*건",
    "owner_changes": r"소유자\s*변경\s*:\s*(\d+)\s*회",
    "plate_changes": r"차량번호\s*변경\s*:\s*(\d+)\s*회",
    "own_damage": r"내차\s*피해\s*:\s*(\d+)\s*회",
    "opp_damage": r"상대차\s*피해\s*:\s*(\d+)\s*회",
}

# 관리상태 등 자유 서술에서만 찾는 손상 표현(리포트 정형구에는 없음)
_DAMAGE_TEXT_KW = ["훼손", "판금", "교환", "부식", "파손", "손상"]


def parse_insurance_history(text: str) -> dict:
    """요항 텍스트의 보험사고이력 카운트를 구조화."""
    out: dict[str, int] = {}
    for key, pat in _HIST_PATTERNS.items():
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1))
    return out


def _strip_report(text: str) -> str:
    """보험사고이력 정형 카운트 구간을 제거해 키워드 오탐을 막는다."""
    t = re.sub(r"(전손|도난|침수)\s*보험사고\s*:\s*\d+\s*건", " ", text)
    t = re.sub(r"(특수용도이력|소유자\s*변경|차량번호\s*변경|내차\s*피해|상대차\s*피해)"
               r"\s*:\s*\d+\s*[건회][^-\n]*", " ", t)
    return t.replace("사고이력정보", " ").replace("보험사고", " ")


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

    def to_dict(self) -> dict:
        return asdict(self)


def _vehicle_obj(result: dict) -> dict:
    lst = result.get("gdsDspslObjctLst") or []
    return lst[0] if lst else {}


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


def parse_detail(resp_json: dict, config: Optional[dict] = None) -> DetailInfo:
    result = (resp_json.get("data", {}) or {}).get("dma_result", {}) or {}
    obj = _vehicle_obj(result)
    dx = result.get("dspslGdsDxdyInfo", {}) or {}

    # 감정 요항 텍스트
    texts = [_clean(r.get("aeeWevlMnpntCtt")) for r in (result.get("aeeWevlMnpntLst") or [])]
    appraisal_text = "\n".join(t for t in texts if t)

    # 사고 판정: ① 보험사고이력 카운트(구조적) ② 관리상태 자유서술 손상표현
    hist = parse_insurance_history(appraisal_text)
    report_present = bool(hist)
    cleaned = _strip_report(appraisal_text)

    # 주행거리: 구조화 필드 우선, 없으면 요항 텍스트에서 보조 추출
    mileage = _to_int(obj.get("drvnDistIndctCtt"))
    if mileage is None:
        mileage = _mileage_from_text(appraisal_text)

    dxdy_history, winning_price = _parse_dxdy(result)

    acc_kw = (config or {}).get("accident_keywords", _DEFAULT_ACCIDENT)
    fld_kw = (config or {}).get("flood_keywords", _DEFAULT_FLOOD)

    flood_hits: list[str] = []
    accident_hits: list[str] = []

    # 침수/전손: 리포트가 있으면 카운트로만 판정(‘0건’ 오탐 방지)
    if hist.get("flood", 0) > 0:
        flood_hits.append("침수이력")
    if hist.get("total_loss", 0) > 0:
        flood_hits.append("전손이력")
    if not report_present:  # 리포트 없으면 자유서술 키워드로 보조 판정
        flood_hits += [k for k in fld_kw if k in cleaned]

    # 사고: 이력 카운트 + 정형구 제거한 텍스트의 손상 키워드
    if hist.get("own_damage", 0) > 0:
        accident_hits.append(f"내차피해{hist['own_damage']}회")
    if hist.get("opp_damage", 0) > 0:
        accident_hits.append(f"상대차피해{hist['opp_damage']}회")
    if hist.get("special_use", 0) > 0:
        accident_hits.append("특수용도이력")
    accident_hits += [k for k in acc_kw if k in cleaned]

    flood_hits = sorted(set(flood_hits))
    accident_hits = sorted(set(accident_hits))

    if flood_hits:
        grade = "flood"
    elif accident_hits:
        grade = "accident"
    else:
        grade = "none"

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
    )
