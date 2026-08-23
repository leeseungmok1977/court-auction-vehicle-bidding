"""법원경매 매각결과검색 (기일별검색 → 매각결과) — 낙찰가(maeAmt) 확보.

물건상세(selectAuctnCsSrchRslt.on)는 매각기일이 지나 종결되면 빈값을 반환하지만,
매각결과검색은 종결된 물건의 **낙찰가·매각/유찰 결과**를 보존한다.

  POST /pgj/pgjsearch/selectDspslSchdRsltSrch.on   (application/json)
  body = { "dma_pageInfo": {...}, "dma_srchGdsDtlSrchInfo": {statNum:3, cortOfcCd, lclDspslGdsLstUsgCd:30000, ...} }
  resp = data.dlt_srchResult[] — 각 행에 saNo, mokmulSer, maeAmt(낙찰가), maeGiil, mulStatcd(03유찰/04매각)

법원(cortOfcCd)별로 자동차(30000) 매각결과를 순회해, 우리 물건과 (saNo, mokmulSer)로 매칭한다.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import requests

from .courtauction_list import BASE, INDEX, new_session, warmup, REQUEST_DELAY_SEC, _check_block
from ..parse.list_parser import _to_int, _fmt_date

RESULT_ENDPOINT = f"{BASE}/pgj/pgjsearch/selectDspslSchdRsltSrch.on"


def _body(bo_cd: str, page_no: int, page_size: int = 40, **over) -> dict:
    info = {
        "statNum": "3", "pgmId": "PGJ158M02", "cortStDvs": "1",
        "cortOfcCd": bo_cd, "jdbnCd": "", "csNo": "",
        "rprsAdongSdCd": "", "rprsAdongSggCd": "", "rprsAdongEmdCd": "",
        "rdnmSdCd": "", "rdnmSggCd": "", "rdnmNo": "",
        "auctnGdsStatCd": "", "lclDspslGdsLstUsgCd": "30000",
        "mclDspslGdsLstUsgCd": "", "sclDspslGdsLstUsgCd": "",
        "dspslAmtMin": "", "dspslAmtMax": "", "aeeEvlAmtMin": "", "aeeEvlAmtMax": "",
        "flbdNcntMin": "", "flbdNcntMax": "", "lafjOrderBy": "",
    }
    info.update(over)
    return {
        "dma_pageInfo": {"pageNo": page_no, "pageSize": page_size, "bfPageNo": "",
                         "startRowNo": "", "totalCnt": "", "totalYn": "", "groupTotalCount": ""},
        "dma_srchGdsDtlSrchInfo": info,
    }


def fetch_results(session: requests.Session, bo_cd: str, page_no: int = 1,
                  page_size: int = 40):
    """한 법원의 자동차 매각결과 1페이지. 반환: (rows, groupTotalCount)."""
    headers = {
        "Content-Type": "application/json;charset=UTF-8", "Accept": "application/json",
        "Referer": INDEX, "Origin": BASE, "X-Requested-With": "XMLHttpRequest",
    }
    time.sleep(REQUEST_DELAY_SEC)
    r = session.post(RESULT_ENDPOINT, data=json.dumps(_body(bo_cd, page_no, page_size)),
                     headers=headers, timeout=30)
    _check_block(r)                   # C.4-5 차단(상태코드+소프트) 즉시 중단
    j = r.json()
    data = j.get("data", {}) or {}
    return (data.get("dlt_srchResult") or [],
            _to_int((data.get("dma_pageInfo") or {}).get("groupTotalCount")))


def fetch_all_results(session: requests.Session, bo_cd: str, max_pages: int = 15) -> list[dict]:
    """한 법원의 자동차 매각결과 전체(페이지 순회).

    groupTotalCount가 빈값이어도 조기 중단하지 않는다 — 총계가 없으면 '가득 찬 페이지'가
    올 때까지 계속 순회하고, 부분 페이지(40건 미만)에서 종료한다(누락 방지)."""
    out: list[dict] = []
    page = 1
    while page <= max_pages:
        rows, total = fetch_results(session, bo_cd, page, page_size=40)
        if not rows:
            break
        out.extend(rows)
        if total and page * 40 >= total:   # 총계 알 때만 총계 기준 종료
            break
        if len(rows) < 40:                 # 총계 미상: 부분 페이지면 마지막
            break
        page += 1
    return out


def result_key(row: dict) -> tuple:
    """매칭 키: (사건번호 saNo, 물건순번 mokmulSer)."""
    return (str(row.get("saNo") or ""), str(row.get("mokmulSer") or ""))


def winning_amt(row: dict) -> int:
    """낙찰가(매각금액). 유찰이면 0."""
    return _to_int(row.get("maeAmt")) or 0


def result_status(row: dict):
    """매각결과 분류. 반환: (label, winning_price).

    mulStatcd 04=매각(낙찰 확정), 03=유찰. **확정 매각(04)만 낙찰**로 인정하고
    낙찰가(maeAmt)를 채운다. 금액이 있어도 상태가 04가 아니면(매각결정 전·불허·재매각
    ·변경·취하 등) '기타'로 두어, 낙찰가가 최저가보다 낮게 보이는 오류를 방지한다.
    """
    st = str(row.get("mulStatcd") or "")
    if st == "04":
        mae = winning_amt(row)
        return "낙찰", (mae if mae > 0 else None)
    if st == "03":
        return "유찰", None
    return "기타", None      # 변경/취하/정지/매각결정 전 등 (금액 있어도 미확정)


def final_fields(row: dict) -> dict:
    """매각결과의 최종 최저매각가·유찰횟수·매각기일 (표시 일관성용).

    수집 시점 이후 유찰이 더 진행돼 최저가가 내려간 뒤 낙찰되면, 저장된 최저가가
    낙찰가보다 높아 보이는 오해가 생긴다. 이를 최종값으로 동기화한다.
    """
    return {
        "min_sale_price": _to_int(row.get("minmaePrice")),
        "fail_count": _to_int(row.get("yuchalCnt")),
        "sale_date": _fmt_date(row.get("maeGiil")),
    }
