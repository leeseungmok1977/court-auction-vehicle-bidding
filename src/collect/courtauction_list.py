"""법원경매정보 자동차·중기 물건목록 수집 (설계서 L1/FLOW-01, TASK-02).

엔드포인트/파라미터는 사이트의 WebSquare 화면 정의(PGJ154M01/M02.xml)에서
실측으로 확인한 값이다(추측 아님, C.4-3 준수).

  POST /pgj/pgjsearch/searchControllerMain.on   (application/json)
  body = { "dma_pageInfo": {...}, "dma_srchGdsDtlSrchInfo": {...} }
  resp = { "data": { "dlt_srchResult": [...], "dma_pageInfo": {...} }, ... }

세션 쿠키는 접속 시 서버가 발급한다(하드코딩 금지, C.4-4). 자동차 고정 코드:
  cortAuctnSrchCondCd = "0004603" (물건검색 구분: 자동차·중기)
  lclDspslGdsLstUsgCd = "30000"   (용도 대분류: 자동차)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import requests

BASE = "https://www.courtauction.go.kr"
LIST_ENDPOINT = f"{BASE}/pgj/pgjsearch/searchControllerMain.on"
INDEX = f"{BASE}/pgj/index.on"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 자동차·중기 검색 고정 코드 (PGJ154M01.xml btn_srchCarTmid_onclick)
VEHICLE_FIXED = {
    "cortAuctnSrchCondCd": "0004603",
    "lclDspslGdsLstUsgCd": "30000",
    "cortStDvs": "1",
    "statNum": 1,
}

# dma_srchGdsDtlSrchInfo 전체 키 (PGJ154M02.xml). 미지정은 빈 문자열.
SRCH_KEYS = [
    "cortAuctnSrchCondCd", "cortStDvs", "rprsAdongSdCd", "rprsAdongSggCd",
    "rprsAdongEmdCd", "rdnmSdCd", "rdnmSggCd", "rdnmNo", "cortOfcCd", "jdbnCd",
    "aeeEvlAmtMin", "aeeEvlAmtMax", "rletLwsDspslPrcMin", "rletLwsDspslPrcMax",
    "lclDspslGdsLstUsgCd", "mclDspslGdsLstUsgCd", "sclDspslGdsLstUsgCd",
    "execrOfcDvsCd", "flbdNcntMin", "flbdNcntMax", "lafjOrderBy", "pgmId",
    "cortAuctnMbrsId", "csNo", "statNum", "gdsVendNm", "grbxTypCd", "carMdlNm",
    "carMdyrMin", "carMdyrMax", "fuelKndCd", "dspslDxdyYmd", "sideDvsCd",
]

REQUEST_DELAY_SEC = 5  # C.4-2: 외부 요청 전 대기


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    return s


def warmup(session: requests.Session) -> None:
    """메인/index 진입으로 세션 쿠키(JSESSIONID 등) 획득."""
    session.get(f"{BASE}/", timeout=20)
    time.sleep(2)
    session.get(INDEX, timeout=20)


def build_search_info(pgm_id: str = "PGJ154M02", **overrides) -> dict:
    info = {k: "" for k in SRCH_KEYS}
    info.update(VEHICLE_FIXED)
    info["pgmId"] = pgm_id
    info["lafjOrderBy"] = ""
    info.update(overrides)  # 예: aeeEvlAmtMin, gdsVendNm, carMdlNm ...
    return info


def build_page_info(page_no: int = 1, page_size: int = 40) -> dict:
    return {
        "pageNo": page_no,
        "pageSize": page_size,
        "bfPageNo": "",
        "startRowNo": "",
        "totalCnt": "",
        "totalYn": "",
        "groupTotalCount": "",
    }


def fetch_list_page(session: requests.Session, page_no: int = 1,
                    page_size: int = 40, **search_overrides) -> requests.Response:
    """자동차 물건목록 1페이지 조회 (1회 호출)."""
    body = {
        "dma_pageInfo": build_page_info(page_no, page_size),
        "dma_srchGdsDtlSrchInfo": build_search_info(**search_overrides),
    }
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json",
        "Referer": INDEX,
        "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
    }
    time.sleep(REQUEST_DELAY_SEC)  # C.4-2
    return session.post(LIST_ENDPOINT, data=json.dumps(body),
                        headers=headers, timeout=30)


def _summarize(resp: requests.Response) -> dict:
    out = {"status": resp.status_code,
           "content_type": resp.headers.get("Content-Type"),
           "len": len(resp.content)}
    try:
        j = resp.json()
        out["top_keys"] = list(j.keys())
        data = j.get("data", {})
        if isinstance(data, dict):
            out["data_keys"] = list(data.keys())
            rows = data.get("dlt_srchResult")
            if isinstance(rows, list):
                out["row_count"] = len(rows)
                if rows:
                    out["first_row_keys"] = list(rows[0].keys())
            pi = data.get("dma_pageInfo")
            if isinstance(pi, dict):
                out["page_info"] = pi
    except Exception as e:  # noqa: BLE001
        out["json_error"] = f"{type(e).__name__}: {e}"
        out["text_head"] = resp.text[:300]
    return out


def main() -> None:
    Path("data").mkdir(exist_ok=True)
    s = new_session()
    warmup(s)
    print("cookies:", list(s.cookies.get_dict().keys()))
    resp = fetch_list_page(s, page_no=1, page_size=40)

    # C.4-5 중단 조건
    if resp.status_code in (403, 429):
        print(f"[중단] 차단 상태코드 {resp.status_code} — 즉시 보고 필요")

    summary = _summarize(resp)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out_path = Path("data") / "응답_L1.json"
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype:
        out_path.write_text(
            json.dumps(resp.json(), ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out_path.write_text(resp.text, encoding="utf-8")
    print("saved:", out_path)


if __name__ == "__main__":
    main()
