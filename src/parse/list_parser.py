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


def _case_no(row: dict) -> str:
    """표시용 사건번호(예: '2025타경103470'). printCsNo 끝부분 우선, 없으면 saNo."""
    printed = str(row.get("printCsNo", "") or "")
    if "<br/>" in printed:
        tail = printed.split("<br/>")[-1].strip()
        if tail:
            return tail
    if printed and "타경" in printed:
        return printed.strip()
    return str(row.get("saNo", "") or "").strip()


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
    usage_name: str            # 매각용도명
    location: str              # 소재지
    status_code: str           # 물건상태코드
    doc_id: str                # 상세조회 키(docid)
    mileage: Optional[int] = None   # 주행거리(상세에서 확정)

    @property
    def folder_key(self) -> str:
        """data/{사건번호}_{물건번호} 폴더명."""
        safe = self.case_no.replace(" ", "").replace("/", "")
        return f"{safe}_{self.item_no}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["folder_key"] = self.folder_key
        return d


def parse_row(row: dict) -> VehicleItem:
    fuel_code = str(row.get("fuelKindcd", "") or "")
    year = _to_int(row.get("carYrtype"))
    if year in (0, None):
        year = None
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
        fail_count=_to_int(row.get("yuchalCnt")),
        sale_date=_fmt_date(row.get("maeGiil")),
        usage_name=str(row.get("dspslUsgNm", "") or "").strip(),
        location=_clean_addr(row.get("printSt")) or _clean_location(row.get("convAddr")),
        status_code=str(row.get("mulStatcd", "") or "").strip(),
        doc_id=str(row.get("docid", "") or "").strip(),
    )


def parse_list_response(resp_json: dict) -> list[VehicleItem]:
    """전체 응답 JSON에서 물건 목록을 파싱."""
    rows = (resp_json.get("data", {}) or {}).get("dlt_srchResult", []) or []
    return [parse_row(r) for r in rows]


def total_count(resp_json: dict) -> Optional[int]:
    """검색 조건 전체 건수(groupTotalCount)."""
    pi = (resp_json.get("data", {}) or {}).get("dma_pageInfo", {}) or {}
    return _to_int(pi.get("groupTotalCount"))
