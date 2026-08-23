"""법원경매정보 자동차 물건 상세·첨부 수집 (설계서 L3~L5/FLOW-02, TASK-03).

  POST /pgj/pgj15B/selectAuctnCsSrchRslt.on   (application/json)
  body = { "dma_srchGdsDtlSrch": {csNo, cortOfcCd, dspslGdsSeq, pgmId, srchInfo} }
  resp = { "data": { "dma_result": {... 상세, csPicLst(base64 사진), aeeWevlMnpntLst(요항) } } }

사진은 응답 내 base64(csPicLst[].picFile)로 내장되어 별도 다운로드가 필요 없다.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Optional

import requests

from .courtauction_list import BASE, INDEX, new_session, warmup, REQUEST_DELAY_SEC, _check_block
from ..paths import DATA_DIR
from ..parse.detail_parser import parse_detail

DETAIL_ENDPOINT = f"{BASE}/pgj/pgj15B/selectAuctnCsSrchRslt.on"


def fetch_detail(session: requests.Session, cs_no: str, cort_ofc_cd: str,
                 dspsl_gds_seq: str = "1", pgm_id: str = "PGJ154M03") -> requests.Response:
    """물건 상세 1건 조회 (1회 호출)."""
    body = {"dma_srchGdsDtlSrch": {
        "csNo": cs_no,
        "cortOfcCd": cort_ofc_cd,
        "dspslGdsSeq": dspsl_gds_seq,
        "pgmId": pgm_id,
        "srchInfo": {},
    }}
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json",
        "Referer": INDEX,
        "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
    }
    time.sleep(REQUEST_DELAY_SEC)  # C.4-2
    r = session.post(DETAIL_ENDPOINT, data=json.dumps(body), headers=headers, timeout=30)
    _check_block(r)                   # C.4-5 차단(상태코드+소프트) 즉시 중단
    return r


def _photo_bytes(pic: dict) -> Optional[bytes]:
    b64 = pic.get("picFile")
    if not b64 or not isinstance(b64, str):
        return None
    try:
        return base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None


def save_item_folder(resp_json: dict, folder_key: str, config: Optional[dict] = None,
                     base_dir: Optional[str] = None) -> Path:
    """물건 폴더 생성: detail.json + appraisal.txt + photos/ (설계서 TASK-03 산출물)."""
    result = (resp_json.get("data", {}) or {}).get("dma_result", {}) or {}
    folder = (Path(base_dir) if base_dir else DATA_DIR) / folder_key
    (folder / "photos").mkdir(parents=True, exist_ok=True)
    (folder / "appraisal").mkdir(parents=True, exist_ok=True)

    info = parse_detail(resp_json, config)

    # 파싱 요약
    (folder / "detail.json").write_text(
        json.dumps(info.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 감정 요항 텍스트(사고 판정 근거)
    (folder / "appraisal.txt").write_text(info.appraisal_text, encoding="utf-8")

    # 사진 저장 (base64 디코딩)
    saved = 0
    for i, pic in enumerate(result.get("csPicLst") or []):
        raw = _photo_bytes(pic)
        if raw is None:
            continue
        # 실제 바이트로 확장자 판별(사이트는 GIF를 .jpg로 명명하기도 함)
        if raw[:6] in (b"GIF89a", b"GIF87a"):
            ext = "gif"
        elif raw[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif raw[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        else:
            ext = "bin"
        stem = Path(pic.get("picTitlNm") or f"photo_{i+1}").stem
        (folder / "photos" / f"{stem}.{ext}").write_bytes(raw)
        saved += 1

    return folder


def main() -> None:
    """L1 최상단 물건 1건의 상세를 수집·저장(데모)."""
    from .courtauction_list import fetch_list_page
    from ..parse.list_parser import parse_list_response, VehicleItem  # noqa: F401

    s = new_session()
    warmup(s)
    list_resp = fetch_list_page(s, page_no=1, page_size=40).json()
    items = parse_list_response(list_resp)
    # 상세 필드가 채워진 물건 우선(연식 존재)
    target = next((it for it in items if it.year), items[0])
    raw = list_resp["data"]["dlt_srchResult"][items.index(target)]

    print("target:", target.case_no, target.model, target.court)
    resp = fetch_detail(s, cs_no=raw["saNo"], cort_ofc_cd=raw["boCd"],
                        dspsl_gds_seq=raw.get("maemulSer", "1")).json()
    folder = save_item_folder(resp, target.folder_key)
    info = parse_detail(resp)
    print("saved folder:", folder)
    print("주행거리:", info.mileage_km, "km | 배기량:", info.displacement_cc,
          "cc | 사진:", info.photo_count, "장")
    print("사고판정:", info.accident_grade, "| hits:", info.accident_hits, info.flood_hits)


if __name__ == "__main__":
    main()
