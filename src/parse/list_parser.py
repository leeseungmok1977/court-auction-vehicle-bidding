"""자동차 물건목록 응답 파싱·필드 매핑 (설계서 TASK-03, A.5 물건 목록).

입력: /pgj/pgjsearch/searchControllerMain.on 응답의 data.dlt_srchResult 행
출력: A.5 '물건' 목록 열에 대응하는 VehicleItem

주행거리·변속기명·연료명·사고판정은 상세(L3)·감정평가서(L4)에서 확정한다.
연료/변속기 코드값의 한글명은 사이트 공통코드로 별도 확인 필요(추측 금지, C.4-3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional

# 관측된 연료 코드(값만 확보). 한글명은 공통코드 확인 전까지 비워 둔다(추측 금지).
FUEL_CODE: dict[str, str] = {
    # "0001001": "?", "0001002": "?"  ← 공통코드 서비스로 확정 후 채움
}


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s == "" or not re.fullmatch(r"-?\d+", s):
        return None
    return int(s)


def _fmt_date(v) -> Optional[str]:
    """YYYYMMDD -> YYYY-MM-DD. 유효하지 않으면 None."""
    s = str(v or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _hhmm(v) -> Optional[str]:
    """매각 시각 코드('1000'/'1030') → 'HH:MM'. 유효 시각만."""
    s = str(v or "").strip()
    if re.fullmatch(r"\d{4}", s) and int(s[0:2]) < 24 and int(s[2:4]) < 60:
        return f"{s[0:2]}:{s[2:4]}"
    return None


def _sale_time(row: dict, fail_count: Optional[int]) -> Optional[str]:
    """다음 매각기일 입찰 시각 — 회차별 시각(maeHh1~4) 중 현재 회차값(범위초과 시 마지막)."""
    times = [t for t in (_hhmm(row.get(k)) for k in ("maeHh1", "maeHh2", "maeHh3", "maeHh4")) if t]
    if not times:
        return None
    return times[min(fail_count or 0, len(times) - 1)]


# 표시용 사건번호 형식 'YYYY타경N' — `web/db.py` `_vehicles_where` 의 목록 GLOB 가드와 같은 뜻.
_CASE_RE = re.compile(r"\d{4}타경\d+")
# saNo(14자리) = 연도 4 + 사건구분 '0130'(타경) + 일련번호 6(0 채움). 상세 조회 키(csNo)와 같은 값이다.
_SANO_CASE_RE = re.compile(r"(\d{4})0130(\d{6})")


def case_no_from_sano(sa_no) -> Optional[str]:
    """saNo('20260130030526') → 표시용 사건번호('2026타경30526'). 규칙에 맞지 않으면 None(추측하지 않는다).

    근거(AUD-04, 2026-10-02): 운영 DB 백업(2026-10-01) 정상 행 **1,571/1,571** 에서 printCsNo 끝부분과
    이 규칙의 결과가 같다(불일치 0 · 전 1,587행의 사건구분이 '0130'). 감사 검증 B(09-27)도 1,476/1,476."""
    m = _SANO_CASE_RE.fullmatch(str(sa_no or "").strip())
    return f"{m.group(1)}타경{int(m.group(2))}" if m else None


_CASE_PARTS_RE = re.compile(r"(\d{4})타경(\d{1,6})")


def sano_from_case_no(case_no) -> Optional[str]:
    """표시용 사건번호('2025타경53697') → saNo('20250130053697'). `case_no_from_sano` 의 역. 형식 밖이면 None.

    AUD-18: 저장된 doc_id 의 가운데 14자리가 **이 행의 사건**인지 맞춰 보는 데만 쓴다(상세 조회 키 해석).
    '(중복)'·'(병합)' 처럼 사건번호 형식이 아닌 행은 None — 그 행은 doc_id 해석을 쓰지 않는다."""
    m = _CASE_PARTS_RE.fullmatch(str(case_no or "").strip())
    return f"{m.group(1)}0130{int(m.group(2)):06d}" if m else None


def _case_no(row: dict) -> str:
    """표시용 사건번호(예: '2025타경103470'). printCsNo 끝부분 우선, 형식 밖이면 saNo 에서 복원.

    ⚠ AUD-04(2026-10-02): 중복·병합 사건은 printCsNo 마지막 `<br/>` 조각이 '(중복)'·'(병합)' 이라
      그 문자열이 사건번호가 됐다. 그래서 여러 법원의 물건이 `(중복)_1` 같은 **한 id** 를 두고 다퉜고
      (09-30 하루 14건 버려짐 — 백업 anomaly_log), 저장된 행도 목록 GLOB 가드에 숨겨졌다. 끝 조각이 사건번호 형식이 아니면
      saNo(상세 조회에 쓰는 바로 그 사건) 로 되돌린다. 정상 행은 바뀌지 않는다(끝 조각 == saNo 규칙, 위 근거).
      saNo 도 규칙 밖이면 예전 그대로 돌려준다 — 모르는 형식을 지어내지 않는다(C.4-3)."""
    printed = str(row.get("printCsNo", "") or "")
    cand = ""
    if "<br/>" in printed:
        cand = printed.split("<br/>")[-1].strip()
    if not cand and printed and "타경" in printed:
        cand = printed.strip()
    if cand and _CASE_RE.fullmatch(cand):
        return cand
    restored = case_no_from_sano(row.get("saNo"))
    if restored:
        return restored
    return cand or str(row.get("saNo", "") or "").strip()


# ── 저장 id(=폴더명) ────────────────────────────────────────────────────────────────
# 예전 규칙 id 는 `사건번호_물건번호` 뿐이라 **법원 코드가 없다.** 사건번호는 법원마다 따로 매기므로
# 다른 법원의 같은 번호가 한 id 를 두고 충돌한다(AUD-02: 09-30 하루 27쌍 + '(중복)' 14건이 버려짐 — 백업 anomaly_log).
# 기존 행의 id 는 바꾸지 않는다(URL·기기 즐겨찾기/메모 키·사진 폴더·낙찰 이력이 id 에 묶여 있다).
# **충돌한 새 물건만** 법원 구분 id `사건번호_물건번호@법원코드` 로 저장한다(web/db.py resolve_listing_id).
#   - '@' 는 URL 경로 조각에 그대로 쓸 수 있고(RFC 3986 pchar) Windows·Linux 파일 이름에도 안전하다.
#   - 예전 규칙 id 에는 '@' 가 없다(아래 _id_part 가 지운다 · 백업 1,587행 실측 0) → 두 형식은 절대 겹치지 않는다.
#   - 법원코드(boCd, 예 B000250)는 영숫자만 남긴다.
COURT_SEP = "@"
_ID_UNSAFE = re.compile(r'[\s/\\:?#%@*"<>|\x00-\x1f]')


def _id_part(s) -> str:
    """id 조각 정리 — 공백·경로·URL 예약 문자·'@' 제거. 지금까지 저장된 id(영숫자·한글·괄호·'_')는 그대로다."""
    return _ID_UNSAFE.sub("", str(s or ""))


def court_qualified_key(base_key: str, court_code) -> Optional[str]:
    """법원 구분 id: `{예전 규칙 id}@{법원코드}`. 법원코드가 비면 None(구분할 수 없다)."""
    cc = re.sub(r"[^0-9A-Za-z]", "", str(court_code or ""))
    return f"{base_key}{COURT_SEP}{cc}" if cc and base_key else None


def is_court_qualified(key) -> bool:
    """법원 구분 id 인가(충돌로 따로 저장된 물건)."""
    return COURT_SEP in str(key or "")


def _clean_location(v) -> str:
    return str(v or "").strip().strip("[]").strip()


def _clean_addr(v) -> str:
    """printSt('채무자주소 : 서울 강남구 …') → 주소 부분만."""
    s = str(v or "").strip()
    s = re.sub(r"^[^:：]{1,12}[:：]\s*", "", s)  # 'OO주소 : ' 접두 제거
    return s.strip()


@dataclass
class VehicleItem:
    # A.5 '물건' 열 대응
    case_no: str               # 사건번호
    item_no: str               # 물건번호
    court: str                 # 법원
    court_code: str            # 법원사무소코드(boCd)
    maker: str                 # 제조사
    model: str                 # 모델(차명)
    year: Optional[int]        # 연식
    fuel_code: str             # 연료(코드)
    fuel_name: Optional[str]   # 연료(한글, 공통코드 확정 후)
    transmission_code: str     # 변속기(코드)
    appraisal_value: Optional[int]  # 감정가
    min_sale_price: Optional[int]   # 최저매각가
    fail_count: Optional[int]       # 유찰횟수
    sale_date: Optional[str]        # 매각기일(YYYY-MM-DD)
    sale_time: Optional[str]        # 입찰(매각) 시각 HH:MM
    sale_place: str                 # 매각(입찰) 장소 — 경매법정
    usage_name: str            # 매각용도명
    location: str              # 목록 표시주소(대개 채무자 주소) — 차량 위치 아님
    status_code: str           # 물건상태코드
    doc_id: str                # 상세조회 키(docid)
    mileage: Optional[int] = None   # 주행거리(상세에서 확정)
    # 저장 id(=폴더명)를 정해 줄 때만 채운다 — 이미 저장된 행의 id(재분석 경로)나 법원 구분 id(AUD-02).
    # 비어 있으면 예전 규칙(base_key)이다. 법원 목록 파서는 이 값을 채우지 않는다.
    key: Optional[str] = None
    # 매각물건 번호(목록 maemulSer) — 상세 조회 요청의 dspslGdsSeq(수집URL정의서 L3). AUD-18(2026-10-02).
    # ⚠ item_no(물건번호)는 **목적물 번호**(mokmulSer = 상세 응답 dspslObjctSeq)다. 두 번호가 다른 물건이 있다
    #   (일괄매각·다물건 사건 — 운영 DB 10-02 사본 1,621행 중 22행). item_no 로 상세를 물으면 법원은
    #   그 번호의 **다른 매각물건**(옆 차)을 주거나 빈 응답을 준다. 비어 있으면 모른다는 뜻이다(재분석 경로 등).
    maemul_ser: str = ""

    @property
    def base_key(self) -> str:
        """예전 규칙 id: `{사건번호}_{물건번호}`(법원 코드 없음)."""
        return f"{_id_part(self.case_no)}_{_id_part(self.item_no)}"

    @property
    def folder_key(self) -> str:
        """저장 id 이자 data/<폴더명>. `key` 가 있으면 그것, 없으면 예전 규칙."""
        return self.key or self.base_key

    def to_dict(self) -> dict:
        d = asdict(self)
        d["folder_key"] = self.folder_key
        return d


def parse_row(row: dict) -> VehicleItem:
    fuel_code = str(row.get("fuelKindcd", "") or "")
    year = _to_int(row.get("carYrtype"))
    if year in (0, None):
        year = None
    _fc = _to_int(row.get("yuchalCnt"))
    return VehicleItem(
        case_no=_case_no(row),
        item_no=str(row.get("mokmulSer", "") or row.get("maemulSer", "") or "").strip(),
        court=str(row.get("jiwonNm", "") or "").strip(),
        court_code=str(row.get("boCd", "") or "").strip(),
        maker=str(row.get("jejosaNm", "") or "").strip(),
        model=str(row.get("carNm", "") or "").strip(),
        year=year,
        fuel_code=fuel_code,
        fuel_name=FUEL_CODE.get(fuel_code),
        transmission_code=str(row.get("bsgFormCd", "") or "").strip(),
        appraisal_value=_to_int(row.get("gamevalAmt")),
        min_sale_price=_to_int(row.get("minmaePrice")),
        fail_count=_fc,
        sale_date=_fmt_date(row.get("maeGiil")),
        sale_time=_sale_time(row, _fc),
        sale_place=str(row.get("maePlace", "") or "").strip(),
        usage_name=str(row.get("dspslUsgNm", "") or "").strip(),
        location=_clean_addr(row.get("printSt")) or _clean_location(row.get("convAddr")),
        status_code=str(row.get("mulStatcd", "") or "").strip(),
        doc_id=str(row.get("docid", "") or "").strip(),
        maemul_ser=str(row.get("maemulSer", "") or "").strip(),
    )


def parse_list_response(resp_json: dict) -> list[VehicleItem]:
    """전체 응답 JSON에서 물건 목록을 파싱."""
    rows = (resp_json.get("data", {}) or {}).get("dlt_srchResult", []) or []
    return [parse_row(r) for r in rows]


def total_count(resp_json: dict) -> Optional[int]:
    """검색 조건 전체 건수(groupTotalCount)."""
    pi = (resp_json.get("data", {}) or {}).get("dma_pageInfo", {}) or {}
    return _to_int(pi.get("groupTotalCount"))
