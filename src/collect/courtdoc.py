"""법원 전자문서(감정평가서) 해석 — 원본 뷰어 URL 구성.

실측(WebSquare PGJ15BP03 + selectAeeWevlInfo.on 응답) 기반, 추측 없음(C.4-3):
  POST /pgj/pgj15B/selectAeeWevlInfo.on
    body dma_srchAeeWevl = {cortOfcCd, cortSptNm, csNo, auctnInfOriginDvsCd:'4', dspslDxdyYmd, pgmId}
  resp data.dma_ordTsIndvdAeeWevlInf = {cortOfcCd, csNo, ordTsCnt, aeeWevlNo, wrtYmd, ...}
  → 감정평가서 원본 뷰어: https://ca.kapanet.or.kr/view/{cortOfcCd}/{csNo}/{ordTsCnt}/{aeeWevlNo}/{wrtYmd}
    (한국감정평가사협회 KAPA 호스팅 — 저장·재배포하지 않고 공식 원본을 그대로 연결)
"""
from __future__ import annotations

import json
import time
from typing import Optional

from .courtauction_list import BASE, INDEX, REQUEST_DELAY_SEC, _check_block

AEE_ENDPOINT = f"{BASE}/pgj/pgj15B/selectAeeWevlInfo.on"
KAPA_VIEW = "https://ca.kapanet.or.kr/view"


def resolve_appraisal_url(session, cort_ofc_cd: str, cs_no: str,
                          dxdy_ymd: str = "") -> Optional[str]:
    """감정평가서 원본 뷰어 URL 반환(없으면 None). session은 법원 warmup된 requests.Session."""
    if not cort_ofc_cd or not cs_no:
        return None
    body = {"dma_srchAeeWevl": {
        "cortOfcCd": cort_ofc_cd, "cortSptNm": "", "csNo": cs_no,
        "auctnInfOriginDvsCd": "4", "dspslDxdyYmd": str(dxdy_ymd or ""),
        "pgmId": "PGJ154M03"}}
    headers = {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json",
               "Referer": INDEX, "Origin": BASE, "X-Requested-With": "XMLHttpRequest"}
    time.sleep(REQUEST_DELAY_SEC)   # C.4-2
    r = session.post(AEE_ENDPOINT, data=json.dumps(body), headers=headers, timeout=30)
    _check_block(r)                 # C.4-5
    info = (r.json().get("data", {}) or {}).get("dma_ordTsIndvdAeeWevlInf", {}) or {}
    cort = info.get("cortOfcCd"); cs = info.get("csNo"); ots = info.get("ordTsCnt")
    aee = info.get("aeeWevlNo"); wrt = info.get("wrtYmd")
    if not (cort and cs and ots is not None and aee and wrt):
        return None
    return f"{KAPA_VIEW}/{cort}/{cs}/{ots}/{aee}/{wrt}"
