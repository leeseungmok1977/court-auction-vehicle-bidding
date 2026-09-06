"""서비스 계층: 수집 파이프라인 ↔ DB 연결, 백그라운드 수집, 재산정.

기존 src 모듈(collect/parse/bidcalc)을 재사용한다. 소량·저속 원칙 유지.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

import yaml

from src.collect.courtauction_list import new_session, warmup, fetch_list_page
from src.collect.courtauction_detail import fetch_detail, save_item_folder
from src.collect import encar
from src.collect import kcar
from src.parse.list_parser import parse_list_response
from src.parse.detail_parser import parse_detail
from src.parse.market_match import summarize, _confidence_label, cross_source_check
from src.bidcalc.calculator import BidInput, calculate
from src.pipeline import resolve_mapping

from . import db

# 동시 수집 방지용 상태
_lock = threading.Lock()
_active = {"running": False, "run_id": None}


_config_cache = {"mtime": None, "data": None}


def load_config(path: str = "config.yaml") -> dict:
    """config.yaml 로드(mtime 캐시). 예상낙찰가 등 행마다 호출되는 경로의 파일I/O·YAML파싱
    반복을 제거해 목록 렌더 성능을 크게 개선. 파일이 바뀌면 자동 재로딩. (읽기전용 사용 전제)"""
    import os as _os
    try:
        m = _os.path.getmtime(path)
    except OSError:
        m = None
    if _config_cache["data"] is None or _config_cache["mtime"] != m:
        _config_cache["data"] = yaml.safe_load(open(path, encoding="utf-8"))
        _config_cache["mtime"] = m
    return _config_cache["data"]


def is_running() -> bool:
    return _active["running"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _resolve_encar(item, config: dict, search: Optional[dict]):
    """엔카 매핑 결정: ① config.model_mapping ② 검색 차명 ③ 국산 자동매핑."""
    key, mp = resolve_mapping(item.model, config)
    if mp:
        return mp
    # 사용자가 검색한 차명(정확한 의도) 우선
    if search and search.get("encar_model_group"):
        man = encar.normalize_maker(item.maker)
        if man:
            return {"car_type": search.get("encar_car_type", "Y"),
                    "manufacturer": man, "model_group": search["encar_model_group"]}
    # 국산 자동매핑 (전체 스캔 포함)
    return encar.auto_map(item.maker, item.model)


def _analyze_item(cs, es, raw: dict, item, config: dict, repair_cost: int,
                  search: Optional[dict] = None) -> dict:
    """물건 1건: 매핑→상세→엔카→산정. DB 레코드 dict 반환."""
    base = {
        "id": item.folder_key, "case_no": item.case_no, "item_no": item.item_no,
        "court": item.court, "court_code": item.court_code, "location": item.location,
        "maker": item.maker, "model": item.model, "year": item.year,
        "min_sale_price": item.min_sale_price, "doc_id": item.doc_id,
        "folder_key": item.folder_key, "collected_at": _now(),
    }

    # 1) 상세는 항상 수집 (수입·상용/특수차 포함) — 주행거리·사진·사고이력·요항
    dresp = fetch_detail(cs, raw["saNo"], raw["boCd"], raw.get("maemulSer", "1")).json()
    detail = parse_detail(dresp, config)
    # 법원 상세가 완전히 비어 있으면(종결·취하·조회불가) 기존에 확보한 사진·주행거리·요항을
    # 빈 값(0/None)으로 덮지 않고 보존한다. 저장(save_item_folder)도 건너뛴다.
    # 단, 낙찰/기일 결과(dxdy·낙찰가)가 있으면 아래 정상 흐름에서 처리하도록 제외한다.
    if (detail.mileage_km is None and not detail.photo_count
            and not (detail.appraisal_text or "").strip()
            and not detail.dxdy_history and detail.winning_price is None):
        prev = db.get_vehicle(item.folder_key) or {}
        for k in ("photo_count", "mileage_km", "displacement_cc", "fuel_code",
                  "appraisal_value", "accident_grade", "spec_remark",
                  "inspection_to", "condition_level"):
            if prev.get(k) not in (None, 0, "", []):
                base[k] = prev[k]
        # 법원 상세가 비어 분석 불가 → '상세없음'(목록에서 숨김). 매각기일 지났으면 '종결'.
        base["status"] = ("종결" if item.sale_date and item.sale_date <= date.today().isoformat()
                          else "상세없음")
        base["analyzed_at"] = _now()
        return base
    save_item_folder(dresp, item.folder_key, config)
    # 차량 보관장소(=실제 차량 위치)는 별도 필드로 보존. location(목록의 채무자 주소)을
    # 덮어쓰지 않는다 — 두 주소의 의미가 달라 섞으면 신뢰 저하(차량위치 vs 채무자주소).
    _storg = (getattr(detail, "storage_addr", "") or "").strip()
    base.update({
        "mileage_km": detail.mileage_km, "displacement_cc": detail.displacement_cc,
        "fuel_code": detail.fuel_code, "appraisal_value": detail.appraisal_value,
        "fail_count": detail.fail_count, "sale_date": detail.sale_date,
        "sale_time": detail.sale_time, "sale_place": detail.sale_place,
        "storage_addr": _storg or None,
        "accident_grade": detail.accident_grade, "accident_hits": detail.accident_hits,
        "insurance_history": detail.insurance_history,
        "appraisal_ecdoc_id": detail.appraisal_ecdoc_id, "spec_remark": detail.spec_remark,
        "photo_count": detail.photo_count,
        "repair_cost": repair_cost, "analyzed_at": _now(),
    })
    base.update(_appraisal_signals(detail.appraisal_text, config))   # 검사만료일·상태등급 저장
    # 낙찰결과는 데이터가 있을 때만 기록(빈 종결 물건이 기존 확정결과를 NULL로 덮지 않도록)
    if detail.dxdy_history or detail.winning_price is not None:
        base.update({
            "dxdy_history": detail.dxdy_history, "winning_price": detail.winning_price,
            "auction_result": _resolve_auction_result(detail.dxdy_history, detail.winning_price),
            "result_checked_at": _now(), "result_source": "detail",  # 잠정 — 권위 소스가 재검증
        })
    # 이미 낙찰(매각완료)이면 시세·산정 없이 종결 처리(검토가능/유찰대기 오분류 방지)
    if base.get("auction_result") == "낙찰":
        # 최저매각가는 '낙찰 회차'의 최저가로 동기화 (낙찰가<최저매각가 표시 오류 방지)
        won = [h for h in (detail.dxdy_history or [])
               if h.get("result") == "낙찰" and h.get("lws_price")]
        if won:
            base["min_sale_price"] = max(won, key=lambda h: h.get("ymd") or "")["lws_price"]
        base["status"] = "종결"
        base["judgment"] = "종결"
        return base
    # 비낙찰: 현재 최저매각가를 기일내역의 다음 예정 회차 값으로 보정(목록 스냅샷 낡음 보정)
    base["min_sale_price"] = _current_min_sale(detail.dxdy_history, item.min_sale_price)
    item.min_sale_price = base["min_sale_price"]   # 이후 산정에도 동일 값 사용

    # 물건상세가 비어 있으면(매각기일 지나 종결·조회불가) 시세를 만들지 않는다(데이터 일관성)
    if (detail.mileage_km is None and not detail.photo_count
            and not (detail.appraisal_text or "").strip()):
        base["status"] = ("종결" if item.sale_date and item.sale_date <= date.today().isoformat()
                          else "미분석")
        return base

    # 2) 엔카 시세 (매핑 가능하면). 국산=general, 수입=premium
    mp = _resolve_encar(item, config, search)
    if mp:
        try:
            # 연식 범위로 쿼리해 같은 연식대 표본을 안정적으로 확보 (첫등록 YYYYMM)
            yf = (item.year - 1) * 100 if item.year else None
            yt = ((item.year + 1) * 100 + 99) if item.year else None
            res = encar.search(es, manufacturer=mp["manufacturer"], model_group=mp["model_group"],
                               car_type=mp.get("car_type", "Y"), premium=mp.get("premium", False),
                               year_from=yf, year_to=yt, limit=100)
            # 감정가는 상세(aeeEvlAmt, 권위값)를 가드 소스로 전달 — 신뢰도 가드는 summarize 내부에서 통합
            stats = summarize(encar.normalize(res["results"]), form_year=item.year,
                              mileage_km=detail.mileage_km, platform="encar",
                              year_tol=config.get("year_tol", 1),
                              mileage_tol=config.get("mileage_tol", 0.30),
                              fuel=detail.fuel_name,   # 요항 텍스트 기반(신뢰) 연료로 매칭
                              min_sample=config.get("min_sample_count", 5),
                              trim=encar.trim_hint(item.model),
                              appraisal_value=detail.appraisal_value or item.appraisal_value,
                              config=config)
            base.update({"market_platform": "encar", "encar_total": res["count"]})
            base.update(_guarded_market_fields(stats))
            if stats.median_price is not None:  # 표본 있으면 산정
                bi = BidInput(photo_count=detail.photo_count, median_price=stats.median_price, min_sale_price=item.min_sale_price or 0,
                              sample_count=stats.sample_count, platform="encar",
                              accident_grade=detail.accident_grade, repair_cost=repair_cost,
                              appraisal_text=detail.appraisal_text)
                bid = calculate(bi, config)
                base.update({
                    "upper_bid": bid.upper_bid, "lower_bound": bid.lower_bound,
                    "judgment": _final_judgment(bid.judgment, stats.confidence_label),
                    "breakdown": bid.breakdown, "status": "완료",
                })
                return base
        except Exception as e:  # noqa: BLE001
            if _is_block(e):    # 엔카 차단 → 상위로 전파해 즉시 중단 (C.4-5)
                raise

    # 3) 시세 없음/실패 → 상세만 확보 (수동 시세 확인 대상)
    base.update({
        "sample_count": base.get("sample_count") or 0, "upper_bid": None,
        "lower_bound": item.min_sale_price, "judgment": "시세 신뢰도 낮음, 수동 검토",
        "status": "완료",
    })
    return base


def _court_filters(search: Optional[dict]) -> dict:
    """검색 dict → fetch_list_page 로 넘길 법원경매 필터(빈 값 제외)."""
    if not search:
        return {}
    court = search.get("court") or {}
    return {k: v for k, v in court.items() if str(v).strip()}


def _run_collection(max_items: int, scan_limit: int, repair_cost: int, run_id: int,
                    search: Optional[dict] = None) -> None:
    config = load_config()
    try:
        cs = new_session(); warmup(cs)
        list_resp = fetch_list_page(cs, page_no=1, page_size=40, **_court_filters(search)).json()
        raws = list_resp["data"]["dlt_srchResult"]
        items = parse_list_response(list_resp)
        es = encar.new_session()

        processed = 0
        consecutive_fail = 0
        for idx, (raw, item) in enumerate(zip(raws, items)):
            if processed >= max_items or idx >= scan_limit:
                break
            db.update_run(run_id, scanned=idx + 1,
                          message=f"{item.case_no} {item.model} 분석 중…")
            try:
                rec = _analyze_item(cs, es, raw, item, config, repair_cost, search)
                consecutive_fail = 0
            except Exception as e:  # noqa: BLE001
                if _is_block(e):     # 차단 → 외부에서 즉시 중단 (C.4-5)
                    raise
                consecutive_fail += 1
                if consecutive_fail >= 3:      # 비정상 3연속 → 중단 (C.4-5)
                    raise RuntimeError("비정상 응답 3회 연속 — 중단")
                rec = {"id": item.folder_key, "case_no": item.case_no,
                       "item_no": item.item_no, "model": item.model,
                       "status": f"오류: {e}", "collected_at": _now()}
            db.upsert_vehicle(rec)
            if rec.get("status") == "완료":
                processed += 1
                db.update_run(run_id, processed=processed)
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"완료 {processed}건 / 스캔 {idx + 1}건")
    except Exception as e:  # noqa: BLE001
        db.update_run(run_id, status="error", finished_at=_now(),
                      message=f"수집 오류: {e}\n{traceback.format_exc()[-300:]}")
    finally:
        with _lock:
            _active["running"] = False
            _active["run_id"] = None


def start_collection(max_items: int = 5, scan_limit: int = 40,
                     repair_cost: int = 500000, search: Optional[dict] = None) -> Optional[int]:
    """백그라운드 수집 시작. 이미 실행 중이면 None."""
    with _lock:
        if _active["running"]:
            return None
        run_id = db.create_run(target=max_items)
        _active["running"] = True
        _active["run_id"] = run_id
    t = threading.Thread(target=_run_collection,
                         args=(max_items, scan_limit, repair_cost, run_id, search), daemon=True)
    t.start()
    return run_id


def _is_block(err) -> bool:
    """403/429 차단 오류인지 (C.4-5 즉시 중단 판정용)."""
    return "차단" in str(err)


def _final_judgment(bid_judgment: str, conf_label) -> str:
    """시세 신뢰도가 '낮음'이면 '입찰 검토 가능'을 '수동 검토'로 하향(과입찰 방지).

    감정가 괴리·표본부족으로 시세를 못 믿는데 '검토 가능'으로 보이면
    산정 상한가를 신뢰해 과입찰할 위험이 있다(재정 리스크)."""
    if conf_label == "낮음" and bid_judgment == "입찰 검토 가능":
        return "시세 신뢰도 낮음, 수동 검토"
    return bid_judgment


def _guarded_market_fields(stats) -> dict:
    """MarketStats(가드가 이미 summarize 내부에서 통합 적용됨) → DB 저장용 시세/신뢰도 필드.

    신뢰도 단일 진실원천: summarize가 반환한 stats.confidence를 그대로 저장한다."""
    # 주의: 케이카 교차검증 컬럼(kcar_median/kcar_sample/cross_source_status/cross_source_rel)은
    # 여기서 기록하지 않는다 — 엔카 단독 재분석/재교정이 사용자의 교차검증 결과를 덮어쓰지 않게
    # 하기 위함(단일 진실원천은 kcar_crosscheck). 미포함 → upsert/update가 기존 값 보존.
    return {
        "sample_count": stats.sample_count, "mean_price": stats.mean_price,
        "median_price": stats.median_price, "min_price": stats.min_price,
        "match_label": stats.match_label, "market_confidence": stats.confidence,
        "market_confidence_label": stats.confidence_label, "market_cv": stats.cv,
        "market_vs_appraisal": stats.market_vs_appraisal, "comps": stats.comps,
    }


def _resolve_auction_result(history, winning_price) -> Optional[str]:
    """기일내역 + 낙찰가로 현재 낙찰결과 판정. 매각기일 전이면 None."""
    if winning_price:
        return "낙찰"
    today = date.today().isoformat()
    past = [r for r in (history or []) if r.get("ymd") and r["ymd"] <= today]
    if not past:
        return None
    last = max(past, key=lambda r: r["ymd"])
    return last.get("result") or "미확정"


def _current_min_sale(history, fallback):
    """기일내역에서 '현재(다음 예정) 최저매각가'를 도출.

    회차가 진행될수록 최저가가 저감되므로, **낙찰이 아닌 가장 최근 기일**의 최저가를
    쓴다. 목록 스냅샷의 최저매각가가 이전(유찰된) 회차라 낡은 문제를 상세 시점 값으로
    보정한다(권장 하한·유찰회차 계산의 기준)."""
    cand = [h for h in (history or [])
            if h.get("result") != "낙찰" and h.get("lws_price")]
    if not cand:
        return fallback
    latest = max(cand, key=lambda h: h.get("ymd") or "")
    return latest.get("lws_price") or fallback


def _sa_no_from_docid(doc_id: str) -> Optional[str]:
    """docid = boCd(7) + saNo(14) + seq. 저장된 docid에서 saNo 복원."""
    d = doc_id or ""
    return d[7:21] if len(d) >= 21 else None


def _rebuild_item(v: dict):
    """DB 레코드 → VehicleItem 재구성 (재분석용)."""
    from src.parse.list_parser import VehicleItem
    return VehicleItem(
        case_no=v.get("case_no") or "", item_no=v.get("item_no") or "1",
        court=v.get("court") or "", court_code=v.get("court_code") or "",
        maker=v.get("maker") or "", model=v.get("model") or "", year=v.get("year"),
        fuel_code="", fuel_name=None, transmission_code="",
        appraisal_value=v.get("appraisal_value"), min_sale_price=v.get("min_sale_price"),
        fail_count=v.get("fail_count"), sale_date=v.get("sale_date"),
        sale_time=v.get("sale_time"), sale_place=v.get("sale_place") or "",
        usage_name="", location=v.get("location") or "", status_code="",
        doc_id=v.get("doc_id") or "")


def _reanalyze(max_items: int, repair_cost: int, run_id: int) -> None:
    """기존 '미매핑' 국산 물건에 상세·시세를 소급 적용."""
    config = load_config()
    try:
        # 대상: 미분석·미매핑·상세없음(재시도) + docid로 saNo 복원 가능
        # '상세없음'도 재시도해 법원에 상세가 다시 생기면 목록에 복귀시킨다.
        targets = []
        for v in db.list_vehicles():
            if v.get("status") not in ("미매핑", "미분석", "상세없음"):
                continue
            if not _sa_no_from_docid(v.get("doc_id") or ""):
                continue
            targets.append(v)
        # 아직 분석 안 한 물건 우선(상세없음 재조회는 남는 예산으로) → 죽은 물건 반복조회 낭비 완화
        targets.sort(key=lambda v: (v.get("analyzed_at") is not None, v.get("analyzed_at") or ""))
        db.update_run(run_id, target=min(max_items, len(targets)) or 0,
                      message=f"재분석 대상 {len(targets)}건")

        cs = new_session(); warmup(cs)
        es = encar.new_session()
        processed = 0
        consecutive_fail = 0
        for i, v in enumerate(targets):
            if processed >= max_items:
                break
            db.update_run(run_id, scanned=i + 1,
                          message=f"{v['case_no']} {v['model']} 재분석 중…")
            item = _rebuild_item(v)
            raw = {"saNo": _sa_no_from_docid(v["doc_id"]), "boCd": v.get("court_code"),
                   "maemulSer": v.get("item_no") or "1"}
            try:
                rec = _analyze_item(cs, es, raw, item, config,
                                    v.get("repair_cost") or repair_cost)
                consecutive_fail = 0
            except Exception as e:  # noqa: BLE001
                if _is_block(e):
                    raise
                consecutive_fail += 1
                if consecutive_fail >= 3:      # 비정상 3연속 → 중단 (C.4-5)
                    raise RuntimeError("비정상 응답 3회 연속 — 중단")
                rec = None
            if rec and rec.get("status") == "완료":
                db.upsert_vehicle(rec)
                processed += 1
                db.update_run(run_id, processed=processed)
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"재분석 완료 {processed}건 / 대상 {len(targets)}건")
    except Exception as e:  # noqa: BLE001
        db.update_run(run_id, status="error", finished_at=_now(), message=f"재분석 오류: {e}")
    finally:
        with _lock:
            _active["running"] = False
            _active["run_id"] = None


def start_reanalyze(max_items: int = 20, repair_cost: int = 500000) -> Optional[int]:
    with _lock:
        if _active["running"]:
            return None
        run_id = db.create_run(target=max_items)
        _active["running"] = True
        _active["run_id"] = run_id
    threading.Thread(target=_reanalyze, args=(max_items, repair_cost, run_id),
                     daemon=True).start()
    return run_id


# =========================================================================
# 일일 목록 갱신 (1개월 이내 입찰예정 전체) — 차종 미지정
# =========================================================================

def _listing_rec(item) -> dict:
    return {
        "id": item.folder_key, "case_no": item.case_no, "item_no": item.item_no,
        "court": item.court, "court_code": item.court_code, "location": item.location,
        "maker": item.maker, "model": item.model, "year": item.year,
        "appraisal_value": item.appraisal_value, "min_sale_price": item.min_sale_price,
        "fail_count": item.fail_count, "sale_date": item.sale_date,
        "sale_time": item.sale_time, "sale_place": item.sale_place,
        "doc_id": item.doc_id, "folder_key": item.folder_key, "collected_at": _now(),
    }


def collect_upcoming(within_days: int = 30, run_id: Optional[int] = None,
                     max_pages: int = 25, finalize: bool = True) -> int:
    """전국 자동차 경매 목록을 순회해 매각기일이 within_days 이내인 물건만 갱신."""
    today = date.today()
    end = today + timedelta(days=within_days)
    cs = new_session(); warmup(cs)
    stored = 0
    page = 1
    total = None
    seen_ids: set[str] = set()   # 이번 스캔에서 관측한 모든 물건 id(목록이탈 감지용)
    complete = False             # 리스트 끝까지 봤는지(부분 스캔이면 이탈 sweep 미실행)
    while page <= max_pages:
        resp = fetch_list_page(cs, page_no=page, page_size=40).json()
        rows = resp["data"]["dlt_srchResult"]
        total = resp["data"]["dma_pageInfo"].get("groupTotalCount") or 0
        if not rows:
            complete = True
            break
        for item in parse_list_response(resp):
            seen_ids.add(item.folder_key)      # 날짜 무관 — 목록에 '존재'하는 모든 물건
            if not item.sale_date:
                continue
            try:
                d = date.fromisoformat(item.sale_date)
            except ValueError:
                continue
            if today <= d <= end:
                db.upsert_listing(_listing_rec(item))
                stored += 1
        if run_id:
            db.update_run(run_id, scanned=page * 40, processed=stored,
                          message=f"목록 {page}페이지 순회 · 입찰예정 {stored}건")
        if page * 40 >= total:
            complete = True
            break
        page += 1
    db.set_setting("last_upcoming_count", str(stored))
    db.set_setting("last_upcoming_at", _now())
    # 목록이탈(변경·취하·연기) 정리 — 완전 스캔 + 전체의 80%↑ 관측 시에만(부분 스캔 오탐 방지)
    if complete and total and len(seen_ids) >= int(total * 0.8):
        sweep = db.mark_disappeared(seen_ids, today.isoformat(), end.isoformat())
        db.set_setting("last_disappear_sweep", f"{_now()} {sweep}")
    if finalize and run_id:
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"입찰예정 {stored}건 갱신 (≤{within_days}일)")
    return stored


def _reconcile_min_from_dxdy(within_days: int = 30) -> None:
    """목록 갱신이 덮은 최저매각가를 기일내역(다음 예정 회차)로 재정합(무네트워크·멱등).

    이미 분석된 입찰예정 물건은 목록 스냅샷보다 상세 기일내역이 더 정확하므로,
    낙찰이 아닌 다음 예정 회차 최저가로 min_sale_price/lower_bound를 맞춘다."""
    for v in db.list_vehicles(upcoming_days=within_days):
        h = v.get("dxdy_history")
        if not h or v.get("auction_result") == "낙찰":
            continue
        cur = _current_min_sale(h, v.get("min_sale_price"))
        if cur and cur != v.get("min_sale_price"):
            f = {"min_sale_price": cur}
            if v.get("upper_bid") is not None:
                f["lower_bound"] = cur
            db.update_fields(v["id"], **f)


def daily_update(within_days: int = 30, analyze: bool = True,
                 analyze_limit: int = 0, run_id: Optional[int] = None,
                 repair_cost: int = 500000) -> dict:
    """일일 갱신: ① 입찰예정 목록 수집 → ② 국산차 시세 분석까지 연속 진행."""
    config = load_config()
    stored = collect_upcoming(within_days=within_days, run_id=run_id, finalize=False)
    _reconcile_min_from_dxdy(within_days)   # 목록이 덮은 dxdy 보정 최저매각가 복원
    analyzed = 0
    if analyze:
        # 분석 대상: 입찰예정 창의 미분석/미매핑 국산차
        targets = [v for v in db.list_vehicles(upcoming_days=within_days)
                   if v.get("status") in ("미분석", "미매핑")
                   and _sa_no_from_docid(v.get("doc_id") or "") and can_analyze(v)]
        # 런당 분석 상한: 0(전체)이어도 하드 상한(C.4-1)으로 무제한 외부요청 방지
        DAILY_ANALYZE_CAP = 80
        cap = analyze_limit if (analyze_limit and analyze_limit > 0) else DAILY_ANALYZE_CAP
        targets = targets[:cap]
        if run_id:
            db.update_run(run_id, target=len(targets), processed=0, scanned=0)

        cs = new_session(); warmup(cs)
        es = encar.new_session()
        consecutive_fail = 0
        for i, v in enumerate(targets):
            if run_id:
                db.update_run(run_id, scanned=i + 1,
                              message=f"시세 분석 {i + 1}/{len(targets)} · {v.get('model')}")
            item = _rebuild_item(v)
            raw = {"saNo": _sa_no_from_docid(v["doc_id"]), "boCd": v.get("court_code"),
                   "maemulSer": v.get("item_no") or "1"}
            try:
                rec = _analyze_item(cs, es, raw, item, config,
                                    v.get("repair_cost") or repair_cost)
                db.upsert_vehicle(rec)
                consecutive_fail = 0
                if rec.get("status") == "완료":
                    analyzed += 1
            except Exception as e:  # noqa: BLE001
                if _is_block(e):
                    raise
                consecutive_fail += 1
                if consecutive_fail >= 3:      # 비정상 3연속 → 중단 (C.4-5)
                    raise RuntimeError("비정상 응답 3회 연속 — 중단")

            if run_id:
                db.update_run(run_id, processed=analyzed)
    # ③ 낙찰결과 반영 (매각기일 지난 물건)
    results = update_results(run_id=run_id, finalize=False)
    # ④ 오늘의 추천 물건 갱신(대시보드 캐러셀) — 매일 아침 리스트업
    try:
        refresh_daily_picks(5)
    except Exception:  # noqa: BLE001 — 추천 갱신 실패가 갱신 전체를 막지 않도록
        pass
    if run_id:
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"입찰예정 {stored} · 분석 {analyzed} · 낙찰결과 {results}건")
    return {"stored": stored, "analyzed": analyzed, "results": results}


def _run_daily(within_days: int, analyze: bool, analyze_limit: int, run_id: int) -> None:
    try:
        daily_update(within_days=within_days, analyze=analyze,
                     analyze_limit=analyze_limit, run_id=run_id)
    except Exception as e:  # noqa: BLE001
        db.update_run(run_id, status="error", finished_at=_now(), message=f"일일 갱신 오류: {e}")
    finally:
        with _lock:
            _active["running"] = False
            _active["run_id"] = None


def start_daily(within_days: int = 30, analyze: bool = True,
                analyze_limit: int = 0) -> Optional[int]:
    with _lock:
        if _active["running"]:
            return None
        run_id = db.create_run(target=0)
        _active["running"] = True
        _active["run_id"] = run_id
    threading.Thread(target=_run_daily,
                     args=(within_days, analyze, analyze_limit, run_id), daemon=True).start()
    return run_id


# --- 내장 스케줄러 (앱 실행 중 매일 지정 시각 1회) ---
_scheduler_started = False


def _scheduler_loop() -> None:
    while True:
        try:
            s = db.get_all_settings()
            if s.get("daily_enabled") == "1" and not is_running():
                now = datetime.now()
                hhmm = now.strftime("%H:%M")
                today = now.strftime("%Y-%m-%d")
                if hhmm >= s.get("daily_time", "06:00") and s.get("last_run_date") != today:
                    db.set_setting("last_run_date", today)
                    start_daily(int(s.get("daily_within", "30")),
                                analyze=s.get("daily_analyze", "1") == "1",
                                analyze_limit=int(s.get("daily_analyze_limit", "0")))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(60)


def start_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, daemon=True).start()


# =========================================================================
# 낙찰결과 반영 (매각기일 지난 물건 재조회) — 기존 데이터는 유지, 결과만 추가
# =========================================================================

def update_results(max_courts: int = 100, run_id: Optional[int] = None,
                   finalize: bool = True, max_requests: int = 300) -> int:
    """매각기일이 지난 물건의 낙찰결과(낙찰가/유찰)를 매각결과검색으로 반영.

    법원(cortOfcCd)별로 자동차 매각결과를 순회해 (사건번호, 물건순번)으로 매칭한다.
    물건상세와 달리 종결된 물건의 낙찰가도 보존되므로 실제 낙찰가를 얻을 수 있다.
    max_requests: 런당 총 외부요청 하드캡(C.4-1 소량 원칙). 초과 시 조기 종료·보고.
    """
    from src.collect import courtauction_result as cr
    config = load_config()   # 유찰 반영 시 판정·상한가 재산정용
    today = date.today().isoformat()
    recency_days = 45   # 매각결과검색이 보존하는 대략적 기간

    # 재조정(미래기일)된 유찰/기타 결과 정리 + 만료 물건 종결 처리(무네트워크)
    db.clear_rescheduled_results()
    db.mark_aged_out(days=recency_days)

    # 대상: 최근 recency_days 이내 매각기일 지남 + 낙찰/종결 아님 + saNo 복원 가능
    def _in_window(sd):
        return sd and sd <= today and sd >= (date.today() - timedelta(days=recency_days)).isoformat()
    # 권위 소스(매각결과검색)로 확정된 낙찰만 제외. 상세-유래 '잠정' 낙찰은 재검증 대상에 포함
    targets = [v for v in db.list_vehicles()
               if _in_window(v.get("sale_date"))
               and not (v.get("auction_result") == "낙찰" and v.get("result_source") == "result_search")
               and _sa_no_from_docid(v.get("doc_id") or "")]
    courts: dict = {}
    for v in targets:
        bo = v.get("court_code")
        if bo:
            courts.setdefault(bo, []).append(v)
    court_list = list(courts.keys())[:max_courts]
    if run_id:
        db.update_run(run_id, target=len(court_list), processed=0, scanned=0)

    s = new_session(); warmup(s)
    updated = 0
    consecutive_fail = 0
    blocked = False
    req_used = 0                              # 런당 총 외부요청 카운트 (C.4-1)
    budget_stop = False
    for i, bo in enumerate(court_list):
        if req_used >= max_requests:         # 요청 예산 소진 → 조기 종료 (C.4-1)
            budget_stop = True
            break
        if run_id:
            db.update_run(run_id, scanned=i + 1,
                          message=f"낙찰결과 조회 {i + 1}/{len(court_list)} 법원 (요청 {req_used}/{max_requests})")
        pages_this = min(15, max_requests - req_used)
        try:
            rows = cr.fetch_all_results(s, bo, max_pages=pages_this)
            consecutive_fail = 0
        except RuntimeError as e:            # 403/429 차단 → 즉시 중단 (C.4-5)
            if "차단" in str(e):
                blocked = True
                break
            consecutive_fail += 1
            rows = []
        except Exception:  # noqa: BLE001
            consecutive_fail += 1
            rows = []
        req_used += min(pages_this, max(1, -(-len(rows) // 40)))  # 실사용 페이지 추정
        if consecutive_fail >= 3:            # 비정상 응답 3연속 → 중단 (C.4-5)
            blocked = True
            break
        rmap = {cr.result_key(x): x for x in rows}
        for v in courts[bo]:
            row = rmap.get((_sa_no_from_docid(v["doc_id"]), str(v.get("item_no"))))
            if not row:
                continue
            label, win = cr.result_status(row)
            fields = {"auction_result": label, "winning_price": win,
                      "result_checked_at": _now(), "result_source": "result_search"}
            # 낙찰(매각완료)이면 판정을 '종결'로 이관 → 검토가능/유찰대기 KPI 이중집계 방지
            if label == "낙찰":
                fields["judgment"] = "종결"
                fields["status"] = "종결"
            elif v.get("status") == "종결":
                # 잠정 낙찰이 권위 소스에서 유찰/불허로 뒤집힘 → '종결' 고착 해제, 재분석 대상 복귀
                fields["status"] = "미분석"
                fields["judgment"] = None
            # 최저매각가·유찰·기일을 최종값으로 동기화 (낙찰가<최저가 오해 방지)
            for k, val in cr.final_fields(row).items():
                if val is not None:
                    fields[k] = val
            new_min = fields.get("min_sale_price")
            if new_min is not None:
                fields["lower_bound"] = new_min
                # 비낙찰: 최저가가 내려가면 판정·상한가 재산정(낡은 '유찰 대기' 고착 방지)
                if label != "낙찰" and v.get("median_price"):
                    bi = BidInput(median_price=v["median_price"] or 0, min_sale_price=new_min,
                                  sample_count=v.get("sample_count") or 0, platform="encar",
                                  accident_grade=v.get("accident_grade") or "none",
                                  repair_cost=v.get("repair_cost") or 500000)
                    bid = calculate(bi, config)
                    fields["upper_bid"] = bid.upper_bid
                    fields["judgment"] = _final_judgment(bid.judgment, v.get("market_confidence_label"))
                    fields["breakdown"] = json.dumps(bid.breakdown, ensure_ascii=False)
                    fields["status"] = "완료"
            db.update_fields(v["id"], **fields)
            if label == "낙찰" and win and v.get("median_price"):
                db.record_sale_result(_sale_snapshot({**v, **fields}, win))   # 영구 축적
            updated += 1
        if run_id:
            db.update_run(run_id, processed=updated)

    if blocked:
        if finalize and run_id:
            db.update_run(run_id, status="error", finished_at=_now(),
                          message=f"차단/비정상 응답 감지 — 중단 (낙찰결과 {updated}건 반영)")
        # finalize=False(daily_update 내부 호출)에서도 차단을 상위로 전파 (C.4-5)
        raise RuntimeError(f"낙찰결과 차단/비정상 응답 감지 — 중단 (반영 {updated}건)")
    return updated
    if finalize and run_id:
        tail = f" · 요청상한 {max_requests} 도달로 일부만 처리(다음 실행에서 이어짐)" if budget_stop else ""
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"낙찰결과 {updated}건 반영{tail}")
    return updated


def _run_results(max_items: int, run_id: int) -> None:
    try:
        update_results(run_id=run_id, finalize=True)
    except Exception as e:  # noqa: BLE001
        db.update_run(run_id, status="error", finished_at=_now(), message=f"낙찰결과 오류: {e}")
    finally:
        with _lock:
            _active["running"] = False
            _active["run_id"] = None


def start_results(max_items: int = 300) -> Optional[int]:
    with _lock:
        if _active["running"]:
            return None
        run_id = db.create_run(target=0)
        _active["running"] = True
        _active["run_id"] = run_id
    threading.Thread(target=_run_results, args=(max_items, run_id), daemon=True).start()
    return run_id


def backfill_mileage_from_files() -> int:
    """기존 분석 물건 중 주행거리가 빈 것을, 저장된 감정요항(appraisal.txt)에서 채운다(무네트워크)."""
    from src.paths import DATA_DIR
    from src.parse.detail_parser import _mileage_from_text
    updated = 0
    for v in db.list_vehicles():
        if v.get("mileage_km") is not None:
            continue
        fk = v.get("folder_key") or v.get("id")
        fp = DATA_DIR / fk / "appraisal.txt"
        if not fp.exists():
            continue
        try:
            km = _mileage_from_text(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            km = None
        if km:
            db.update_fields(v["id"], mileage_km=km)
            updated += 1
    return updated


def backfill_photo_count() -> int:
    """디스크엔 사진이 있는데 DB photo_count가 0/NULL인 물건을 실제 파일 수로 정정(무네트워크).

    목록 재수집 등으로 photo_count가 어긋나면 ⑴ 목록에서 사진이 안 뜨고 ⑵ '사진없음 감가'가
    잘못 적용되므로, 폴더의 실제 사진 수로 맞춘다.
    """
    from src.paths import DATA_DIR
    updated = 0
    for v in db.list_vehicles():
        if v.get("photo_count"):
            continue
        fk = v.get("folder_key") or v.get("id")
        pdir = DATA_DIR / fk / "photos"
        if not pdir.exists():
            continue
        n = sum(1 for p in pdir.iterdir() if p.is_file())
        if n > 0:
            db.update_fields(v["id"], photo_count=n)
            updated += 1
    return updated


def _appraisal_signals(text: str, config: Optional[dict] = None) -> dict:
    """감정요항 텍스트 → 저장용 신호(검사만료일·상태등급·손상표현). 텍스트 없으면 {}.
    inspection_to는 만료일(안정적)만 저장 — '경과' 여부는 조회 시점에 판정(시간이 지나도 정확)."""
    from src.parse.appraisal import parse_appraisal
    p = parse_appraisal(text or "")
    if not p:
        return {}
    insp = p.get("inspection")
    return {
        "inspection_to": insp["valid_to"] if insp else None,
        "condition_level": p["condition"]["level"],
        "condition_flags": p["condition"]["damage"] or None,
    }


def backfill_appraisal_signals() -> int:
    """저장된 감정요항(appraisal.txt)에서 검사만료일·상태등급을 채운다(무네트워크, 최초 1회).
    condition_level이 아직 없는(NULL) 물건만 처리 → 이후 시작 시엔 빠르게 통과."""
    import os
    updated = 0
    for v in db.list_vehicles():
        if v.get("condition_level"):
            continue
        fk = v.get("folder_key") or v.get("id")
        fp = os.path.join("data", fk, "appraisal.txt")
        if not os.path.exists(fp):
            continue
        try:
            sig = _appraisal_signals(open(fp, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            sig = {}
        db.update_fields(v["id"],
                         condition_level=sig.get("condition_level") or "unknown",
                         inspection_to=sig.get("inspection_to"),
                         condition_flags=sig.get("condition_flags"))
        updated += 1
    return updated


def can_analyze(v: dict) -> bool:
    """상세를 수집할 수 있는지 (docid로 saNo 복원 가능). 수입·상용 포함 모든 물건 대상."""
    return bool(_sa_no_from_docid(v.get("doc_id") or ""))


def backtest_stats() -> dict:
    """이미 낙찰된 물건으로 시스템 시세·상한가의 실측 정확도를 백테스트(무네트워크).

    - 낙찰가/시세중앙값 분포 = 경매 낙찰률(시세 대비 실거래 할인)
    - 낙찰가 ≤ 산정 상한가 비율 = 상한가가 실제 낙찰가를 안전히 상회했는지
    - 시세 기반 예상 낙찰가(=시세×할인중앙값)의 실측 대비 오차(MAE%)
    사용자 최우선 가치 '실측 신뢰'를 데이터로 검증하고, 산정 보정 근거를 제공한다.
    """
    import statistics as st
    rows = db.list_vehicles()
    # 학습 데이터셋: 영구 히스토리(sale_results) ∪ 라이브 낙찰 (id 중복 제거, 히스토리 우선).
    # 라이브 테이블이 갱신·만료돼도 히스토리에 누적된 표본은 유지 → 시간이 지날수록 신뢰성↑.
    data: dict = {}
    for r in db.list_sale_results():
        if r.get("median_price") and r.get("winning_price"):
            data[r["id"]] = r
    for r in rows:
        if (r.get("auction_result") == "낙찰" and r.get("winning_price")
                and r.get("median_price") and r["id"] not in data):
            data[r["id"]] = r
    med_rows = list(data.values())
    live_won = [r for r in rows if r.get("auction_result") == "낙찰" and r.get("winning_price")]
    ratios = sorted(r["winning_price"] / r["median_price"] for r in med_rows)
    out = {"won_total": len(med_rows), "sample": len(med_rows),
           "discount_median": None, "discount_p25": None, "discount_p75": None,
           "upper_hit_rate": None, "upper_n": 0, "mae_pct": None,
           "actual_sample": 0, "actual_mae_pct": None,
           "discount_by_fail": {}, "discount_by_model": {}, "model_learned": 0,
           "history_n": db.count_sale_results()}
    if ratios:
        out["discount_median"] = round(st.median(ratios), 3)
        if len(ratios) >= 4:
            q = st.quantiles(ratios, n=4)
            out["discount_p25"], out["discount_p75"] = round(q[0], 3), round(q[2], 3)
        # (참고) baseline 오차: 전역 단일 할인율×시세 — 아래 LOO(실제 예측) 대비 상한
        dm = out["discount_median"]
        errs = [abs(r["median_price"] * dm - r["winning_price"]) / r["winning_price"]
                for r in med_rows]
        out["mae_baseline_pct"] = round(st.mean(errs) * 100, 1)
        out["mae_pct"] = out["mae_baseline_pct"]   # LOO 계산 실패 시 폴백
        # 유찰횟수(수요 신호)별 할인율 — 선호 차량은 일찍·높게 낙찰(유찰1회 ≈ 0.90, 2회+ ≈ 0.77).
        # 표본이 적으므로 전역 중앙값으로 수축(shrinkage)해 과적합 방지.
        from collections import defaultdict
        bg = defaultdict(list)
        for r in med_rows:
            b = "1" if (r.get("fail_count") or 0) <= 1 else "2plus"
            bg[b].append(r["winning_price"] / r["median_price"])
        by = {}
        for b, vs in bg.items():
            if len(vs) >= 5:
                w = len(vs) / (len(vs) + 8)         # 표본 많을수록 버킷값 신뢰
                by[b] = round(w * st.median(vs) + (1 - w) * dm, 3)
            else:
                by[b] = dm
        out["discount_by_fail"] = by
        # 모델별 할인율 — 데이터가 쌓여 특정 모델 표본이 임계치(MODEL_MIN)를 넘으면 자동 활성.
        # (인기·선호가 낙찰률에 반영됨. 표본 적을 땐 비활성 → 유찰버킷/전역으로 폴백)
        MODEL_MIN = 8
        bgm = defaultdict(list)
        for r in med_rows:
            mk = _model_key(r)      # 항상 재계산(정규화 규칙 변경 즉시 반영, 파편화 방지)
            if mk:
                bgm[mk].append(r["winning_price"] / r["median_price"])
        bym = {}
        for mk, vs in bgm.items():
            if len(vs) >= MODEL_MIN:
                w = len(vs) / (len(vs) + 10)        # 모델별은 더 보수적으로 수축
                bym[mk] = round(w * st.median(vs) + (1 - w) * dm, 3)
        out["discount_by_model"] = bym
        out["model_learned"] = len(bym)
        # ── 최저매각가 기반 예측(핵심 개선): 낙찰가/최저가 프리미엄은 낙찰가/시세보다 훨씬 안정적 ──
        # 유찰로 내려간 최저가가 '시장이 드러낸 할인'을 이미 반영 → 예측 오차 대폭↓(26%→~10%).
        # 유찰 횟수가 많을수록 프리미엄↑(경쟁·저가 매력). 표본 적은 버킷은 전역으로 수축.
        prem_all = [r["winning_price"] / r["min_sale_price"]
                    for r in med_rows if r.get("min_sale_price") and r.get("winning_price")]
        if prem_all:
            gpm = st.median(prem_all)
            out["min_premium_median"] = round(gpm, 3)
            if len(prem_all) >= 4:
                pq = st.quantiles(prem_all, n=4)
                out["min_premium_p25"], out["min_premium_p75"] = round(pq[0], 3), round(pq[2], 3)
            pbf = defaultdict(list)
            for r in med_rows:
                if r.get("min_sale_price"):
                    pbf[_fail_bucket(r.get("fail_count"))].append(r["winning_price"] / r["min_sale_price"])
            mpf = {}
            for b, vs in pbf.items():
                if len(vs) >= 5:
                    w = len(vs) / (len(vs) + 8)
                    mpf[b] = round(w * st.median(vs) + (1 - w) * gpm, 3)
                else:
                    mpf[b] = round(gpm, 3)
            out["min_premium_by_fail"] = mpf
            # LOO MAE(자기 제외 유찰버킷 프리미엄 × 최저가) — 실제 예측의 정직 정확도
            idx = [(_fail_bucket(r.get("fail_count")), r) for r in med_rows if r.get("min_sale_price")]
            loo = []
            for i, (bi, r) in enumerate(idx):
                peers = [(o["winning_price"] / o["min_sale_price"])
                         for j, (bj, o) in enumerate(idx) if j != i and bj == bi]
                if len(peers) >= 5:
                    w = len(peers) / (len(peers) + 8)
                    prem = w * st.median(peers) + (1 - w) * gpm
                else:
                    prem = gpm
                pred = r["min_sale_price"] * prem
                if r.get("median_price"):
                    pred = min(pred, r["median_price"] * 1.10)   # expected_for와 동일 소프트캡
                loo.append(abs(pred - r["winning_price"]) / r["winning_price"])
            if loo:
                out["mae_pct"] = round(st.mean(loo) * 100, 1)
    # 유사 낙찰(comparable) 매칭용 풀 — 같은 차종·유사 연식·주행거리 낙찰 사례로
    # 예상낙찰가를 개별 보정하기 위한 경량 스냅샷(모델키·연식·주행·할인율·낙찰가).
    out["comp_pool"] = [
        {"model_key": _model_key(r), "year": r.get("year"), "mileage_km": r.get("mileage_km"),
         "ratio": r["winning_price"] / r["median_price"], "winning_price": r["winning_price"],
         "median_price": r["median_price"], "sale_date": r.get("sale_date"),
         "case_no": r.get("case_no")}
        for r in med_rows]
    ub_rows = [r for r in live_won if r.get("upper_bid")]
    if ub_rows:
        out["upper_n"] = len(ub_rows)
        out["upper_hit_rate"] = round(
            sum(1 for r in ub_rows if r["winning_price"] <= r["upper_bid"]) / len(ub_rows), 3)
    # 사용자 실측 캘리브레이션 오차(시세 vs 실측)
    act = [r for r in rows if r.get("actual_price") and r.get("median_price")]
    if act:
        out["actual_sample"] = len(act)
        aerrs = [abs(r["median_price"] - r["actual_price"]) / r["actual_price"] for r in act]
        out["actual_mae_pct"] = round(st.mean(aerrs) * 100, 1)
    return out


def expected_winning(median_price: Optional[int], discount: Optional[float]) -> Optional[int]:
    """시세중앙값 × 경매 할인율 = 실측 기반 예상 낙찰가 (10만원 단위 반올림 — 거짓 정밀 제거)."""
    if not median_price or not discount:
        return None
    return int(round(median_price * discount / 100_000) * 100_000)


def _model_key(v: dict) -> str:
    """모델별 할인율 집계용 정규화 키. 제조사 표기 변형('현대'/'현대자동차'/'(주)현대자동차')과
    모델 괄호영문·공백을 정규화해 같은 모델이 파편화되지 않게 한다. 기록·조회 동일 사용."""
    import re as _re
    mk = (v.get("maker") or "").replace("(주)", "").replace("자동차", "").strip()
    md = _re.sub(r"\s+", " ", (v.get("model") or "").split("(")[0]).strip()
    return f"{mk}|{md}" if md else ""


def _fail_bucket(fc) -> int:
    """유찰 횟수 버킷(0=신건, 1, 2, 3+) — 낙찰가/최저가 프리미엄 집계용."""
    fc = fc or 0
    return 0 if fc == 0 else 1 if fc == 1 else 2 if fc == 2 else 3


def min_premium_for(bt: dict, fail_count) -> Optional[float]:
    """최저매각가 대비 예상 낙찰 프리미엄(낙찰가/최저가) — 유찰버킷별(없으면 전역 중앙값)."""
    bt = bt or {}
    mpf = bt.get("min_premium_by_fail") or {}
    return mpf.get(_fail_bucket(fail_count)) or bt.get("min_premium_median")


def discount_for(bt: dict, fail_count=None, model_key: str = "") -> Optional[float]:
    """할인율 선택 — 자동 승급: ① 모델별(표본 충분 시) → ② 유찰버킷 → ③ 전역 중앙값.
    데이터가 쌓여 특정 모델 표본이 임계치를 넘으면 그 모델 할인율이 자동으로 쓰인다."""
    bt = bt or {}
    by_model = bt.get("discount_by_model") or {}
    if model_key and model_key in by_model:
        return by_model[model_key]
    by_fail = bt.get("discount_by_fail") or {}
    b = "1" if (fail_count or 0) <= 1 else "2plus"
    return by_fail.get(b) or bt.get("discount_median")


COMP_MIN_N = 3   # 유사 낙찰이 이 이상이면 개별 보정에 사용


def comparable_sales(v: dict, bt: dict, year_tol: Optional[int] = None,
                     mileage_tol: Optional[float] = None, limit: int = 8) -> list:
    """이 물건과 같은 차종·유사 연식·유사 주행거리의 과거 낙찰 사례를 유사도순으로 반환.

    - 같은 model_key(정규화 제조사|모델)
    - 연식 |Δ| ≤ year_tol (기본 config year_tol=1)
    - 둘 다 주행거리가 있으면 |Δ|/대상 ≤ mileage_tol (기본 0.30). 없으면 주행 조건 생략.
    유사도(연식차→주행차)순 정렬. 예상낙찰가 보정과 상세 '유사 낙찰 사례' 표시에 사용.
    """
    pool = (bt or {}).get("comp_pool") or []
    mk = _model_key(v)
    if not mk:
        return []
    cfg = load_config()
    ytol = year_tol if year_tol is not None else int(cfg.get("year_tol", 1))
    mtol = mileage_tol if mileage_tol is not None else float(cfg.get("mileage_tol", 0.30))
    yr, ml = v.get("year"), v.get("mileage_km")
    out = []
    for r in pool:
        if r.get("model_key") != mk:
            continue
        yd = 0
        if yr and r.get("year") is not None:
            yd = abs(r["year"] - yr)
            if yd > ytol:
                continue
        md = None
        if ml and r.get("mileage_km"):
            md = abs(r["mileage_km"] - ml) / ml
            if md > mtol:           # 둘 다 주행거리가 있고 차이가 크면 제외
                continue
        out.append({**r, "_yd": yd, "_md": md if md is not None else 1.0})
    out.sort(key=lambda r: (r["_yd"], r["_md"]))
    return out[:limit]


def comparable_discount(v: dict, bt: dict) -> Optional[tuple]:
    """유사 낙찰 사례(≥COMP_MIN_N)로 할인율을 산출. (할인율, 표본수, 사례목록) 또는 None.
    표본이 적을 땐 모델/전역 할인율로 수축(shrinkage)해 과적합을 막는다."""
    comps = comparable_sales(v, bt)
    ratios = [r["ratio"] for r in comps if r.get("ratio")]
    if len(ratios) < COMP_MIN_N:
        return None
    import statistics as st
    med = st.median(ratios)
    fb = discount_for(bt, v.get("fail_count"), _model_key(v)) or med
    n = len(ratios)
    w = n / (n + 3)                 # 표본 많을수록 유사사례값 신뢰
    return round(w * med + (1 - w) * fb, 3), n, comps


# ── 엔카/케이카 원자료 격리 (MONETIZATION_SPEC TASK-M01) ─────────────────────
# 일반 사용자 응답에서 제거할 필드 — '화면 숨김'이 아니라 데이터 계층에서 삭제(뷰소스·
# 향후 JSON API로도 안 샘). 소매 시세(median_price)·신뢰도·재판매 손익분기는 '반영된
# 결과'라 유지, 개별 동급 매물(comps)·케이카·표본수·매칭메타 등 원자료만 제거.
PRIVATE_FIELDS = frozenset({
    "market_platform", "encar_total", "sample_count", "mean_price", "min_price",
    "market_cv", "market_vs_appraisal", "comps", "match_label",
    "kcar_median", "kcar_sample", "cross_source_status", "cross_source_rel", "kcar_checked_at",
    "actual_price", "actual_price_at", "repair_cost",
})
# breakdown(재판매 손익분기 폭포, 사용자 노출)에 섞인 엔카 메타만 골라 제거
_BREAKDOWN_PRIVATE = frozenset({"플랫폼", "플랫폼가중", "표본수"})


def public_view(v: Optional[dict], is_admin: bool) -> Optional[dict]:
    """물건 dict에서 비관리자에게 나가면 안 되는 엔카/케이카 원자료를 비운 사본 반환.
    관리자면 원본 그대로. 파생 결과(예상낙찰가·신뢰도·소매 시세·재판매 손익분기)는 유지.

    서버 렌더 안전을 위해 키를 '삭제'하지 않고 **None**으로 치환한다(미가드 템플릿 참조가
    UndefinedError로 500 되는 것을 방지 — app.py의 finalize가 None→""로 렌더).
    ※ 향후 별도 JSON API(M05+)에서는 이 키들을 응답에서 아예 '제외'할 것."""
    if is_admin or not v:
        return v
    out = dict(v)
    for k in PRIVATE_FIELDS:
        if k in out:
            out[k] = None
    bd = out.get("breakdown")
    if isinstance(bd, dict):
        out["breakdown"] = {k: val for k, val in bd.items() if k not in _BREAKDOWN_PRIVATE}
    return out


def effective_median(v: dict) -> Optional[int]:
    """산정에 반영할 시세 = 엔카(기준) + 케이카(2차 소스) 표본가중 블렌드.

    케이카 표본이 충분(≥2)하고 두 소스가 극단으로 벌어지지 않을 때만 블렌드한다.
    가중치는 케이카 표본이 많을수록 커지되 상한 35%(엔카가 여전히 기준). 표본 부족·
    극단 괴리(오매칭 의심)면 엔카만 사용 — 노이즈로 산정을 흔들지 않기 위함(신뢰 최우선).
    """
    enc = v.get("median_price")
    if not enc:
        return enc
    kc, kn = v.get("kcar_median"), (v.get("kcar_sample") or 0)
    if not kc or kn < 2:
        return enc
    if not (0.5 <= kc / enc <= 2.0):     # 2배 이상 벌어지면 오매칭 의심 → 엔카만
        return enc
    w = min(0.35, kn / (kn + 6))          # 케이카 표본 가중(상한 35%)
    return int(round(((1 - w) * enc + w * kc) / 10000) * 10000)


def expected_for(v: dict, bt: dict) -> Optional[int]:
    """물건 dict + 백테스트 통계 → 예상 낙찰가(중심 추정치).

    핵심: **최저매각가 × 유찰버킷 프리미엄**(낙찰가/최저가). 유찰로 내려간 최저가가
    시장 할인을 이미 반영해 낙찰가/시세보다 훨씬 안정적 → 실측 오차 최소(~10%).
    최저매각가가 없으면 시세×할인율(유사낙찰→모델→유찰→전역)로 폴백."""
    mn = v.get("min_sale_price")
    prem = min_premium_for(bt, v.get("fail_count"))
    med = effective_median(v)
    if mn and prem:
        est = int(round(mn * prem / 100_000) * 100_000)
        if med:                     # 소프트 캡: 낙찰가가 시세를 크게 상회하는 비현실 방어(신건·고감정가)
            est = min(est, int(round(med * 1.10 / 100_000) * 100_000))
        return est
    # 폴백(최저가 없음): 시세 기반 — 유사낙찰 → 모델/유찰/전역 할인율
    cd = comparable_discount(v, bt)
    if cd:
        return expected_winning(med, cd[0])
    return expected_winning(med, discount_for(bt, v.get("fail_count"), _model_key(v)))


def expected_band(v: dict, bt: dict) -> Optional[dict]:
    """예상 낙찰가 중심값 + 밴드(보수/균형/공격)를 **하나의 기준**으로 산출.

    상단 'AI 예상낙찰가'·추천 입찰 전략·한줄 코멘트가 모두 이 함수 하나를 공유해
    계산식이 일치한다(별도 산정 금지). 중심값(=균형)은 `expected_for`(목록·대시보드와
    동일 소스)이고, 밴드는 **같은 프리미엄 기준**에 전역 분위수의 상대폭(p25/median,
    p75/median)을 곱해 만든다 → 캡/반올림 후에도 항상 보수 ≤ 균형 ≤ 공격.

    반환: {price(균형), lo(보수), hi(공격), premium, basis} 또는 None.
    basis.kind: 'min_premium'(최저매각가×유찰프리미엄) | 'median_discount'(시세×할인율 폴백).
    """
    center = expected_for(v, bt)          # 중심값 — 목록·대시보드와 동일한 단일 소스
    if not center:
        return None
    bt = bt or {}
    mn = v.get("min_sale_price")
    prem = min_premium_for(bt, v.get("fail_count"))
    med = effective_median(v)
    cap = int(med * 1.10) if med else None

    def _round(x):
        return int(round(x / 100_000) * 100_000)

    def _cap(x):
        return min(x, cap) if cap else x

    if mn and prem:
        gpm = bt.get("min_premium_median") or prem
        p25, p75 = bt.get("min_premium_p25"), bt.get("min_premium_p75")
        rel_lo = (p25 / gpm) if (p25 and gpm) else 0.93     # 전역 분포의 상대 폭
        rel_hi = (p75 / gpm) if (p75 and gpm) else 1.07
        lo, hi = _round(_cap(center * rel_lo)), _round(_cap(center * rel_hi))
        basis = {"kind": "min_premium", "min_sale_price": mn,
                 "premium": round(prem, 3), "fail_count": v.get("fail_count") or 0}
    else:                                 # 폴백: 시세×할인율 분위수
        lo = expected_winning(med, bt.get("discount_p25"))
        hi = expected_winning(med, bt.get("discount_p75"))
        basis = {"kind": "median_discount", "median": med,
                 "discount": bt.get("discount_median")}
    # 캡·반올림으로 인한 역전 방지 — 균형(center)은 항상 밴드 안에
    if lo and lo > center:
        lo = center
    if hi and hi < center:
        hi = center
    return {"price": center, "lo": lo, "hi": hi,
            "premium": round(prem, 3) if prem else None, "basis": basis}


def _sale_snapshot(v: dict, win: int) -> dict:
    """확정 낙찰 → 히스토리 스냅샷(학습 데이터). 시세·유찰·인기프록시를 낙찰 시점 값으로 고정."""
    med = v.get("median_price")
    return {
        "id": v.get("id"), "court_code": v.get("court_code"), "case_no": v.get("case_no"),
        "item_no": v.get("item_no"), "maker": v.get("maker"), "model": v.get("model"),
        "model_key": _model_key(v), "year": v.get("year"), "mileage_km": v.get("mileage_km"),
        "fuel_code": v.get("fuel_code"), "median_price": med,
        "min_sale_price": v.get("min_sale_price"), "fail_count": v.get("fail_count"),
        "encar_total": v.get("encar_total"),
        "market_confidence_label": v.get("market_confidence_label"),
        "winning_price": win, "ratio": round(win / med, 4) if (med and win) else None,
        "sale_date": v.get("sale_date"), "recorded_at": _now(),
    }


def backfill_sale_results() -> int:
    """라이브 vehicles의 확정 낙찰을 히스토리에 소급 기록(멱등). 최초·정기 동기화용."""
    n = 0
    for v in db.list_vehicles(result="낙찰"):
        if v.get("winning_price") and v.get("median_price"):
            db.record_sale_result(_sale_snapshot(v, v["winning_price"]))
            n += 1
    return n


def plain_verdict(v: dict, expected: Optional[dict]) -> Optional[dict]:
    """비전문가용 한줄 판정 — 30초 안에 '얼마·지금 가능?' 이해(PS-03).

    코멘트는 화면의 수치와 **모순되지 않아야** 한다(신뢰 최우선):
    - 시세 비교는 상세 '소매 차익'과 **동일한 값**(effective_median)을 써서 할인율(%)이 일치.
    - 되팔이(재판매) 가능 여부는 재판매 손익분기(수리·이전·명도·마진 반영 상한가 upper_bid)로 판단.
      → '시세에 가깝게'처럼 데이터와 어긋나는 표현을 쓰지 않는다.
    """
    if not expected or not expected.get("price"):
        return None
    exp = expected["price"]
    med = effective_median(v) or v.get("median_price")
    if not med:
        return None
    floor = v.get("min_sale_price") or 0
    upper = v.get("upper_bid") or 0

    def won(n):
        return f"{int(round(n / 10000)):,}만원" if n else "—"

    if v.get("auction_result") == "낙찰" or v.get("judgment") == "종결":
        return {"tone": "closed", "text": "이미 매각이 끝난 물건입니다 (참고용)."}
    if v.get("market_confidence_label") == "낮음":
        return {"tone": "caution",
                "text": f"시세 신뢰도가 낮아 참고용입니다. 예상 낙찰가 {won(exp)}은 현장 확인 후 판단하세요."}
    if not (floor and floor <= exp):
        return {"tone": "wait",
                "text": f"지금 최저가 {won(floor)}은 예상 낙찰가 {won(exp)}보다 높습니다. 아직 비싸니 추가 유찰을 기다리는 게 좋습니다."}
    # 여기부터 floor ≤ exp — '지금 입찰 검토 가능' 구간
    gap = round((med - exp) / med * 100) if med > exp else 0   # 소매 시세 대비 예상낙찰가 할인율(=소매 차익 %와 동일)
    gap_txt = f"소매 시세보다 약 {gap}% 낮지만" if gap >= 3 else "소매 시세와 큰 차이가 없어"
    head = f"지금 {won(floor)}에 입찰할 수 있고 예상 낙찰가는 {won(exp)}입니다."
    if upper and exp <= upper:            # 재판매 손익분기 이내 → 되팔이 차익 여지
        return {"tone": "ok",
                "text": f"{head} 재판매 손익분기({won(upper)}) 이내라 되팔이 차익도 노려볼 만합니다."}
    if upper and exp > upper:             # 손익분기 초과 → 되팔이 어렵고 실사용 목적
        return {"tone": "ok",
                "text": f"{head} {gap_txt}, 이전·수리·명도비를 빼면 재판매 손익분기({won(upper)})를 초과해 되팔이 차익은 어렵습니다. 직접 타실 목적이면 검토할 만합니다."}
    # upper_bid 미산정(시세 신뢰 보통 등) — 소매 차익만으로 안내
    if gap >= 25:
        return {"tone": "ok",
                "text": f"{head} {gap_txt} 이전·수리·명도비를 감안해 되팔이 실익을 따져보세요. 직접 타실 목적이면 검토할 만합니다."}
    return {"tone": "ok",
            "text": f"{head} {gap_txt} 되팔이 차익은 크지 않고, 직접 타실 목적이면 검토할 만합니다."}


def alert_items(days: int = 3) -> list:
    """임박 매각기일(오늘~D+days) 알림 대상 — 관심 물건 또는 검토가능. dday·예상낙찰가 포함(PS-05)."""
    import datetime
    today = datetime.date.today()
    bt = backtest_stats()
    seen, out = set(), []
    rows = (db.list_vehicles(starred=True, upcoming_days=days)
            + db.list_vehicles(judgment="입찰 검토 가능", upcoming_days=days))
    for v in rows:
        if v["id"] in seen:
            continue
        seen.add(v["id"])
        try:
            dd = (datetime.date.fromisoformat(v.get("sale_date")) - today).days
        except (TypeError, ValueError):
            continue
        if dd < 0:
            continue
        out.append({**v, "dday": dd, "expected_win": expected_for(v, bt)})
    out.sort(key=lambda x: (x["dday"], -(x.get("expected_win") or 0)))
    return out


def _promising(v: dict) -> bool:
    """대표 후보 자격 — 시세 신뢰도 높음 + 오매칭(시세≫최저가) 의심 제외."""
    if v.get("market_confidence_label") != "높음":
        return False
    m, mn = v.get("median_price"), v.get("min_sale_price")
    if m and mn and mn > 0 and m / mn > 3.5:
        return False
    return True


def review_summary(bt: Optional[dict] = None) -> Optional[dict]:
    """검토 가능 물건의 예상낙찰가 집계(중심값·IQR·평균 신뢰도·MAE·시세대비 할인율).
    대시보드/달력 공용. bt를 넘기면 재계산 생략."""
    import statistics
    bt = bt or backtest_stats()
    disc = bt.get("discount_median")
    cand = [v for v in db.list_vehicles(judgment="입찰 검토 가능") if _promising(v)]
    exps = [e for e in (expected_for(v, bt) for v in cand) if e]
    if not exps:
        return None
    confs = [v.get("market_confidence") for v in cand if v.get("market_confidence")]
    if len(exps) >= 4:
        q = statistics.quantiles(exps, n=4)
        p25, p75 = int(q[0]), int(q[2])
    else:
        p25, p75 = min(exps), max(exps)
    return {
        "count": len(cand),
        "exp_lo": min(exps), "exp_hi": max(exps), "exp_p25": p25, "exp_p75": p75,
        "exp_med": int(statistics.median(exps)),
        "conf_avg": round(sum(confs) / len(confs)) if confs else None,
        "mae": bt.get("mae_pct"),
        "disc_pct": round((1 - disc) * 100) if disc else None,
    }


def _pick_photo_url(v: dict) -> Optional[str]:
    from src.paths import DATA_DIR
    fk = v.get("folder_key") or v.get("id")
    pdir = DATA_DIR / fk / "photos"
    if not pdir.exists():
        return None
    avail = {p.name for p in pdir.iterdir() if p.is_file()}
    order = [n for n in (v.get("photo_order") or []) if n in avail]
    names = order + sorted(n for n in avail if n not in order)
    return f"/photo/{fk}/{names[0]}" if names else None


def _pick_dict(v: dict, bt: dict) -> dict:
    """추천 캐러셀 표시용 dict — 엔카 원자료 제거 + 사진·D-day·예상낙찰가·시세대비 할인."""
    import datetime
    exp = expected_for(v, bt)
    med = effective_median(v)
    d = public_view(dict(v), False)
    d["expected_win"] = exp
    d["disc_pct"] = int(round((med - exp) / med * 100)) if (med and exp and med > exp) else None
    d["photo_url"] = _pick_photo_url(v)
    try:
        d["dday"] = (datetime.date.fromisoformat(v["sale_date"]) - datetime.date.today()).days
    except (TypeError, ValueError, KeyError):
        d["dday"] = None
    return d


def compute_daily_picks(n: int = 5) -> list:
    """오늘의 추천 물건 id 선정(매일 아침 갱신용) — 검토가능·사진·예측 있는 물건 중
    시세 대비 차익(할인) 큰 순, 제조사 다양성 확보해 상위 n건 id."""
    bt = backtest_stats()
    cand = []
    for v in db.list_vehicles(judgment="입찰 검토 가능"):
        if not (v.get("photo_count") and v.get("median_price") and v.get("min_sale_price")):
            continue
        if not _promising(v):
            continue
        exp, med = expected_for(v, bt), effective_median(v)
        if not exp or not med:
            continue
        cand.append((med - exp, v))       # 시세 대비 차익(할인액) 큰 순
    cand.sort(key=lambda x: -x[0])
    ids, makers = [], set()
    for _, v in cand:                     # 제조사 다양성 우선
        mk = v.get("maker") or ""
        if mk in makers:
            continue
        makers.add(mk); ids.append(v["id"])
        if len(ids) >= n:
            break
    if len(ids) < n:                      # 부족하면 다양성 무시하고 채움
        for _, v in cand:
            if v["id"] not in ids:
                ids.append(v["id"])
            if len(ids) >= n:
                break
    return ids


def refresh_daily_picks(n: int = 5) -> list:
    """추천 id를 계산·저장(날짜 스탬프). 매일 갱신 작업에서 호출."""
    import datetime, json
    ids = compute_daily_picks(n)
    db.set_setting("daily_picks_ids", json.dumps(ids))
    db.set_setting("daily_picks_date", datetime.date.today().isoformat())
    return ids


def get_daily_picks(n: int = 5) -> list:
    """오늘의 추천 물건(표시용 dict). 하루 고정(날짜 캐시), 없으면 계산·저장.
    저장된 id를 매 로드 시 현재 상태로 재구성하되, 여전히 유효(검토가능·미래기일)한 것만."""
    import datetime, json
    today = datetime.date.today().isoformat()
    ids = None
    if db.get_setting("daily_picks_date") == today:
        try:
            ids = json.loads(db.get_setting("daily_picks_ids") or "[]")
        except Exception:  # noqa: BLE001
            ids = None
    if not ids:
        ids = refresh_daily_picks(n)
    bt = backtest_stats()
    out = []
    for vid in ids:
        v = db.get_vehicle(vid)
        if not v or v.get("judgment") != "입찰 검토 가능" or v.get("status") == "상세없음":
            continue
        if v.get("auction_result") in ("낙찰", "종결"):
            continue
        if not v.get("sale_date") or v["sale_date"] < today:
            continue
        out.append(_pick_dict(v, bt))
    return out


_multi_lot_cache = {"ids": None}


def multi_lot_ids(refresh: bool = False) -> set:
    """동일 사건(사건번호)에 물건이 2개 이상이라 사진 폴더가 섞여 있을 수 있는
    물건 id 집합. 대법원 경매는 한 사건에 여러 물건이 있으면 각 물건 폴더에 사건
    전체 사진이 들어오는 경우가 있어(형제 물건 파일셋 동일), 해당 물건의 정면·측면·
    실내 분류가 다른 물건 차량일 수 있다 → 목록·상세에 '사진 혼재 가능' 캐비엇 표기용.
    """
    if _multi_lot_cache["ids"] is not None and not refresh:
        return _multi_lot_cache["ids"]
    conn = db.connect()
    rows = conn.execute("SELECT id FROM vehicles WHERE COALESCE(photo_count,0) > 0").fetchall()
    from collections import defaultdict
    by_case = defaultdict(list)
    for r in rows:
        vid = r["id"]
        by_case[vid.rsplit("_", 1)[0]].append(vid)   # 사건번호 = id에서 _물건 제거
    ids = {vid for grp in by_case.values() if len(grp) > 1 for vid in grp}
    _multi_lot_cache["ids"] = ids
    return ids


def alert_count(days: int = 3) -> int:
    """헤더 벨 배지용 경량 카운트(백테스트 미호출)."""
    import datetime
    today = datetime.date.today()
    seen = set()
    for v in (db.list_vehicles(starred=True, upcoming_days=days)
              + db.list_vehicles(judgment="입찰 검토 가능", upcoming_days=days)):
        try:
            if (datetime.date.fromisoformat(v.get("sale_date")) - today).days >= 0:
                seen.add(v["id"])
        except (TypeError, ValueError):
            pass
    return len(seen)


def price_distribution(v: dict, exp: Optional[int], mae: Optional[float],
                       nbins: int = 12) -> Optional[dict]:
    """동급 매물(comps) 실제 가격 분포 히스토그램 데이터 + 마커(최저·예상·시세) 위치.

    표(숫자)가 아닌 시각 요소로 '어느 가격대에 베팅하는가'를 보여주기 위한 것.
    """
    comps = v.get("comps") or []
    prices = sorted(c.get("price_won") for c in comps if c.get("price_won"))
    prices = [p for p in prices if p]
    if len(prices) < 5:
        return None
    floor = v.get("min_sale_price") or 0
    median = v.get("median_price") or 0
    marks = [m for m in (floor, exp, median) if m]
    lo = min(prices + marks)
    hi = max(prices + marks)
    if hi <= lo:
        return None
    span = hi - lo
    counts = [0] * nbins
    for p in prices:
        idx = min(nbins - 1, max(0, int((p - lo) / span * nbins)))
        counts[idx] += 1
    maxc = max(counts) or 1

    def pct(x):
        return round((x - lo) / span * 100, 1)

    bins = [{"x": round(i * 100 / nbins, 2), "w": round(100 / nbins, 2),
             "h": round(counts[i] / maxc * 100), "c": counts[i]} for i in range(nbins)]
    band = None
    if exp and mae:
        band = {"lo": max(0.0, pct(exp * (1 - mae / 100))),
                "hi": min(100.0, pct(exp * (1 + mae / 100)))}
    return {
        "bins": bins, "maxc": maxc, "n": len(prices), "lo": lo, "hi": hi,
        "floor": floor, "exp": exp, "median": median, "band": band,
        "floor_pct": pct(floor) if floor else None,
        "exp_pct": pct(exp) if exp else None,
        "median_pct": pct(median) if median else None,
    }


def report_data(v: dict, config: dict, bt: dict) -> Optional[dict]:
    """종합 분석 리포트용 파생 데이터 — 실데이터·산정로직 기반(취득원가·수익 시뮬·민감도·신뢰도).

    지어내지 않는다: 있는 값으로 계산하고, 추정 항목은 화면에서 태그(추정)로 정직 표기.
    """
    med = v.get("median_price")
    if not med:
        return None
    floor = v.get("min_sale_price") or 0
    tax_rate = config.get("acquisition_tax_rate", 0.07)
    fc = config.get("fixed_costs", {})
    transfer, delivery = fc.get("transfer_fee", 300000), fc.get("delivery_fee", 200000)
    fixed = transfer + delivery
    repair = v.get("repair_cost") or 500000
    reserve = 500000                          # 리스크 충당(현금) — 추정
    # 상세와 동일한 단일 소스(expected_band): 중심(exp)=균형, 밴드(lo/hi)가 항상 중심을 감싼다.
    # (구: exp=최저가×프리미엄, lo/hi=시세×할인율 → 서로 다른 모델이라 밴드가 중심을 벗어나는 모순)
    _band = expected_band(v, bt) or {}
    exp = _band.get("price") or expected_for(v, bt) or 0
    upper = v.get("upper_bid") or 0
    lo = _band.get("lo")
    hi = _band.get("hi")
    resale = med                              # 보수적 재판매가 = 시세중앙값
    target_margin = round(med * config.get("margin_rate", 0.15))

    def _allin(bid):
        tax = round(bid * tax_rate)
        return {"bid": bid, "tax": tax, "fixed": fixed, "repair": repair,
                "reserve": reserve, "total": bid + tax + fixed + repair + reserve}

    # 수익 시뮬레이션 — 낙찰가 레벨(최저가·예상·상한가·중간값)
    levels = {floor, exp, upper}
    if exp and upper:
        levels.add(int(round((exp + upper) / 2 / 100000) * 100000))
    if exp:
        levels.add(int(round(exp * 1.08 / 100000) * 100000))
    sim = []
    for b in sorted(x for x in levels if x and x > 0):
        ai = _allin(b)
        margin = resale - ai["total"]
        grade = ("우량" if margin >= target_margin else "적정" if margin >= target_margin * 0.5
                 else "주의" if margin > 0 else "부적정")
        sim.append({**ai, "margin": margin, "grade": grade,
                    "is_exp": b == exp, "is_upper": b == upper})

    # 민감도 — 정비비(수리비) 추가 × 재판매가 변동 (기준 낙찰가 = 예상낙찰가)
    base_bid = exp or upper or floor
    base_fixed = round(base_bid * tax_rate) + fixed + reserve
    sens = []
    for dr in (0, 500000, 1000000):
        cells = [(resale + dp) - (base_bid + base_fixed + repair + dr)
                 for dp in (-1000000, 0, 1000000)]
        sens.append({"repair_delta": dr, "cells": cells})

    # 데이터 신뢰도 카테고리(있는 데이터로 도출 — 없으면 추정/낮춤)
    conf = v.get("market_confidence") or 0
    cats = [
        {"name": "경매 가격정보", "score": 100, "tag": "confirmed"},
        {"name": "차량 기본정보", "score": 100 if v.get("mileage_km") else 60,
         "tag": "confirmed" if v.get("mileage_km") else "estimated"},
        {"name": "사고·이력", "score": 90 if v.get("insurance_history") else 60,
         "tag": "verified" if v.get("insurance_history") else "estimated"},
        {"name": "시장 가격", "score": conf, "tag": "verified"},
        {"name": "상태·정비비", "score": 60, "tag": "estimated"},
    ]
    stop_active = v.get("accident_grade") in ("accident", "flood")
    return {
        "exp": exp, "lo": lo, "hi": hi, "upper": upper, "floor": floor, "resale": resale,
        "tax_rate": tax_rate, "transfer": transfer, "delivery": delivery, "fixed": fixed,
        "repair": repair, "reserve": reserve, "target_margin": target_margin,
        "allin_ref": _allin(exp or upper or floor), "sim": sim, "sens": sens, "cats": cats,
        "stop_active": stop_active, "discount": discount_for(bt, v.get("fail_count"), _model_key(v)),
        "mae": bt.get("mae_pct"),
    }


def analyze_single(vid: str, repair_cost: Optional[int] = None) -> Optional[dict]:
    """단건 즉시 분석 (상세 + 엔카 시세 + 산정). 동기 실행(약 10초)."""
    config = load_config()
    v = db.get_vehicle(vid)
    if not v:
        return None
    sa = _sa_no_from_docid(v.get("doc_id") or "")
    if not sa:
        return None
    cs = new_session(); warmup(cs)
    es = encar.new_session()
    item = _rebuild_item(v)
    raw = {"saNo": sa, "boCd": v.get("court_code"), "maemulSer": v.get("item_no") or "1"}
    try:
        rec = _analyze_item(cs, es, raw, item, config,
                            repair_cost or v.get("repair_cost") or 500000)
    except Exception as e:  # noqa: BLE001 — 차단/네트워크 오류 시 500 대신 상태 기록
        db.update_fields(vid, status="차단 감지 — 잠시 후 재시도" if _is_block(e)
                         else f"오류: {str(e)[:40]}")
        return db.get_vehicle(vid)
    db.upsert_vehicle(rec)
    # 케이카 2소스 자동 교차검증(활성 시) — 개별 분석은 처음부터 두 소스를 함께 반영
    if (kcar.ENABLED and config.get("kcar_cross_enabled", False)
            and rec.get("median_price") is not None):
        try:
            kcar_crosscheck(vid, config)
        except Exception:  # noqa: BLE001 — 차단·오류는 조용히(단건이라 이후 재시도 가능)
            pass
    return db.get_vehicle(vid)


def recompute_all_market(run_id: Optional[int] = None, finalize: bool = True) -> int:
    """기존 물건 전체의 시세를 개선 로직(연식범위·연료·동세대)으로 일괄 재교정.

    물건상세는 재조회하지 않고(주행거리·사진·사고이력·낙찰결과 보존), 저장된
    연식·주행거리 + 저장된 감정요항(appraisal.txt)의 연료로 **엔카만 재조회**한다.
    같은 (제조사·모델·연식)끼리 묶어 엔카 요청을 캐시해 요청 수를 줄인다.
    """
    import os
    from src.parse.detail_parser import _fuel_from_text
    config = load_config()
    year_tol = config.get("year_tol", 1)
    mileage_tol = config.get("mileage_tol", 0.30)

    # 시세 매핑 가능 + 연식 있는 물건만
    groups: dict = {}
    for v in db.list_vehicles():
        if v.get("year") is None:
            continue
        # 이미 매각(낙찰)·종결된 물건은 재교정 대상 제외(판정을 '검토가능'으로 되살리지 않음)
        if v.get("auction_result") == "낙찰" or v.get("status") == "종결":
            continue
        # 상세가 없는(종결·조회불가) 물건엔 시세를 만들지 않음 (주행거리 없이 연식만 매칭=부정확)
        if v.get("mileage_km") is None and not v.get("photo_count"):
            continue
        mp = _resolve_encar(_rebuild_item(v), config, None)
        if not mp:
            continue
        key = (mp["manufacturer"], mp["model_group"], mp.get("car_type", "Y"),
               bool(mp.get("premium", False)), int(v["year"]))
        groups.setdefault(key, []).append(v)

    keys = list(groups.keys())
    total_items = sum(len(g) for g in groups.values())   # 진행바 분모(물건 수)와 단위 통일
    if run_id:
        db.update_run(run_id, target=total_items, processed=0, scanned=0)

    es = encar.new_session()
    # 케이카 2소스: (모델·연식·연료) 캐시 + 요청 상한(C.4-1)으로 그룹당 최소 조회
    kcar_on = kcar.ENABLED and config.get("kcar_cross_enabled", False)
    ks = None
    kcache: dict = {}
    kreq = {"n": 0, "cap": config.get("kcar_max_requests", 200)}
    if kcar_on:
        try:
            ks = kcar.new_session()
        except Exception:  # noqa: BLE001 — 케이카 세션 실패 시 엔카 단독 진행
            ks = None
    updated = 0
    consecutive_fail = 0
    kcar_blocked = False
    for i, key in enumerate(keys):
        man, mg, ct, prem, year = key
        if run_id:
            _kmsg = f" · 케이카 {kreq['n']}회" if ks else ""
            db.update_run(run_id, scanned=i + 1,
                          message=f"시세 재교정 {i + 1}/{len(keys)} · {mg} {year}{_kmsg}")
        yf, yt = (year - 1) * 100, (year + 1) * 100 + 99
        query_ok = True
        try:
            res = encar.search(es, manufacturer=man, model_group=mg, car_type=ct,
                               premium=prem, year_from=yf, year_to=yt, limit=100)
            listings = encar.normalize(res["results"])
            consecutive_fail = 0
        except RuntimeError as e:
            if "차단" in str(e):
                break
            consecutive_fail += 1; query_ok = False; listings = []; res = {"count": None}
            if consecutive_fail >= 3:
                break
        except Exception:  # noqa: BLE001
            consecutive_fail += 1; query_ok = False; listings = []; res = {"count": None}
            if consecutive_fail >= 3:
                break
        if not query_ok:
            continue   # 조회 실패 시 기존 시세 보존(덮어쓰지 않음)

        for v in groups[key]:
            fuel = None
            atext = ""
            fp = os.path.join("data", v.get("folder_key") or v["id"], "appraisal.txt")
            if os.path.exists(fp):
                try:
                    atext = open(fp, encoding="utf-8").read()
                    fuel = _fuel_from_text(atext)
                except Exception:  # noqa: BLE001
                    pass
            _msc = config.get("min_sample_count", 5)
            stats = summarize(listings, form_year=v["year"], mileage_km=v.get("mileage_km"),
                              platform="encar", year_tol=year_tol, mileage_tol=mileage_tol,
                              fuel=fuel, min_sample=_msc,
                              trim=encar.trim_hint(v.get("model")),
                              appraisal_value=v.get("appraisal_value"), config=config)
            fields = {"market_platform": "encar", "encar_total": res.get("count"),
                      "analyzed_at": _now()}
            fields.update(_appraisal_signals(atext, config))   # 검사만료일·상태등급 갱신
            # 케이카 2소스 교차검증: 라이브(캐시+상한) 또는 저장값 재적용 → fresh 엔카 median에 반영
            stats, _kf, _blk = _kcar_cross_live(ks, kcache, kreq, v, fuel, listings,
                                                stats, year, config)
            fields.update(_kf)
            if _blk:                       # 케이카 차단 → 이후 케이카 중단(엔카는 계속)
                kcar_blocked = True
                try:
                    ks.close()
                except Exception:  # noqa: BLE001
                    pass
                ks = None
            fields.update(_guarded_market_fields(stats))
            if stats.median_price is not None:
                # 산정 시세 = 엔카 + 케이카(2차) 블렌드
                eff = effective_median({"median_price": stats.median_price,
                                        "kcar_median": fields.get("kcar_median"),
                                        "kcar_sample": fields.get("kcar_sample")})
                bi = BidInput(median_price=eff,
                              min_sale_price=v.get("min_sale_price") or 0,
                              sample_count=stats.sample_count, platform="encar",
                              accident_grade=v.get("accident_grade") or "none",
                              repair_cost=v.get("repair_cost") or 500000,
                              appraisal_text=atext, photo_count=v.get("photo_count"))
                bid = calculate(bi, config)
                fields.update({"upper_bid": bid.upper_bid, "lower_bound": bid.lower_bound,
                               "judgment": _final_judgment(bid.judgment, fields.get("market_confidence_label")),
                               "breakdown": json.dumps(bid.breakdown, ensure_ascii=False)})
            else:
                # 시세가 사라지면 낡은 상한가·산정을 무효화(고아 상한가 방지)
                fields.update({"upper_bid": None, "lower_bound": None, "breakdown": None,
                               "judgment": "시세 신뢰도 낮음, 수동 검토"})
            db.update_fields(v["id"], **fields)
            updated += 1
        if run_id:
            db.update_run(run_id, processed=updated)

    if ks is not None:
        try:
            ks.close()
        except Exception:  # noqa: BLE001
            pass
    if finalize and run_id:
        _km = (f" · 케이카 {kreq['n']}회 조회" + ("(차단중단)" if kcar_blocked else "")) if kcar_on else ""
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"시세 재교정 {updated}건{_km}")
    return updated


def _run_recompute_all(run_id: int) -> None:
    try:
        recompute_all_market(run_id=run_id, finalize=True)
    except Exception as e:  # noqa: BLE001
        db.update_run(run_id, status="error", finished_at=_now(), message=f"시세 재교정 오류: {e}")
    finally:
        with _lock:
            _active["running"] = False
            _active["run_id"] = None


def start_recompute_all() -> Optional[int]:
    with _lock:
        if _active["running"]:
            return None
        run_id = db.create_run(target=0)
        _active["running"] = True
        _active["run_id"] = run_id
    threading.Thread(target=_run_recompute_all, args=(run_id,), daemon=True).start()
    return run_id


def recompute(vid: str, repair_cost: int, config: dict | None = None) -> Optional[dict]:
    """저장된 시세로 수리비만 바꿔 재산정."""
    config = config or load_config()
    v = db.get_vehicle(vid)
    if not v or v.get("median_price") is None:
        return None
    bi = BidInput(median_price=v["median_price"] or 0, min_sale_price=v["min_sale_price"] or 0,
                  sample_count=v.get("sample_count") or 0, platform="encar",
                  accident_grade=v.get("accident_grade") or "none", repair_cost=repair_cost)
    bid = calculate(bi, config)
    db.update_fields(vid, repair_cost=repair_cost, upper_bid=bid.upper_bid,
                     lower_bound=bid.lower_bound,
                     judgment=_final_judgment(bid.judgment, v.get("market_confidence_label")),
                     breakdown=json.dumps(bid.breakdown, ensure_ascii=False),
                     analyzed_at=_now())
    return db.get_vehicle(vid)


def _kcar_keyword(model: Optional[str]) -> str:
    """법원 물건 모델명 → 케이카 자유검색 키워드(괄호·특수문자·순수숫자 토큰 제거, 앞 3토큰)."""
    import re
    if not model:
        return ""
    s = re.sub(r"\(.*?\)", " ", model)            # 괄호 내용 제거(세대코드 등)
    s = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", s)     # 특수문자 제거
    toks = [t for t in s.split() if t and t[0].isalpha()]  # 배기량(3.5T·2000 등) 토큰 제외
    return " ".join(toks[:3])                       # 브랜드+모델 수준


def _kcar_cross_live(ks, kcache: dict, kreq: dict, v: dict, fuel, listings: list,
                     stats, group_year: int, config: dict):
    """재교정용 케이카 교차검증. (모델·연식·연료) 캐시로 그룹당 최소 조회 → fresh 대조.

    ks=None(케이카 off/미가동)이면 저장된 교차검증을 fresh 엔카 median에 재적용(보존).
    반환: (stats, kcar_fields, blocked). blocked=True면 상위에서 중단(C.4-5).
    """
    _msc = config.get("min_sample_count", 5)
    ytol = config.get("year_tol", 1)
    mtol = config.get("mileage_tol", 0.30)
    tol = config.get("cross_source_tol", 0.10)
    trim = encar.trim_hint(v.get("model"))

    def _resum(xs, xr, kcm, kcs):
        st = summarize(listings, form_year=v["year"], mileage_km=v.get("mileage_km"),
                       platform="encar", year_tol=ytol, mileage_tol=mtol, fuel=fuel,
                       min_sample=_msc, trim=trim, appraisal_value=v.get("appraisal_value"),
                       config=config, cross_status=xs, cross_rel=xr,
                       kcar_median=kcm, kcar_sample=kcs)
        return st, {"kcar_median": kcm, "kcar_sample": kcs,
                    "cross_source_status": xs, "cross_source_rel": xr}

    if stats.median_price is None:
        return stats, {}, False

    def _reapply_stored():
        kcm, kcs = v.get("kcar_median"), v.get("kcar_sample") or 0
        if kcm and kcs >= _msc:
            xs, xr, _ = cross_source_check(stats.median_price, kcm, tol=tol)
            st, kf = _resum(xs, xr, kcm, kcs)
            return st, kf, False
        return stats, {}, False

    if ks is None:                       # 라이브 off → 저장된 교차검증 재적용(있으면)
        return _reapply_stored()

    kw = _kcar_keyword(v.get("model"))
    hyb = bool(fuel and "하이브리드" in fuel)
    ckey = (kw, group_year, hyb)
    if kw and ckey not in kcache:        # (모델·연식·연료)당 1회만 케이카 조회
        if kreq["n"] >= kreq["cap"]:
            kcache[ckey] = []            # 요청 상한 도달(C.4-1)
        else:
            try:
                kres = ks.search(kw, year=group_year, hybrid=hyb)
                kreq["n"] += 1
                kw_toks = set(kw.split())
                kcache[ckey] = [l for l in kcar.normalize(kres["results"])
                                if kw_toks & set(str(l.get("model") or "").split())]
            except Exception as e:  # noqa: BLE001
                if _is_block(e):
                    return stats, {}, True    # 차단 → 중단(C.4-5)
                kcache[ckey] = []
    klist = kcache.get(ckey, [])
    if not klist:                        # 라이브 빈 결과 → 저장값이라도 보존
        return _reapply_stored()
    kstats = summarize(klist, form_year=v["year"], mileage_km=v.get("mileage_km"),
                       platform="kcar", year_tol=ytol, mileage_tol=mtol, fuel=fuel,
                       min_sample=_msc, trim=trim, config=config)
    tier_ok = (kstats.tier_level is not None and stats.tier_level is not None
               and kstats.tier_level <= stats.tier_level)
    if kstats.median_price and kstats.sample_count >= _msc and tier_ok:
        xs, xr, _ = cross_source_check(stats.median_price, kstats.median_price, tol=tol)
    else:
        xs, xr = "single", None
    st, kf = _resum(xs, xr, kstats.median_price, kstats.sample_count)
    return st, kf, False


def kcar_crosscheck(vid: str, config: dict | None = None) -> dict:
    """[온디맨드] 케이카 2차 소스로 엔카 시세를 교차검증하고 신뢰도를 갱신.

    엔카를 재조회해 원표본으로 신뢰도를 재계산하고(교차검증 상한 반영), 케이카를 조회해
    동급 중앙값을 구한 뒤 두 소스를 대조한다. 일치(±tol)면 단일소스 상한(88)을 풀어
    신뢰도 상향, 크게 벌어지면 상한/경고. 결과를 DB에 저장하고 요약 dict 반환.
    """
    import os
    from src.parse.detail_parser import _fuel_from_text
    config = config or load_config()
    v = db.get_vehicle(vid)
    if not v or v.get("year") is None:
        return {"ok": False, "msg": "물건/연식 정보가 없어 교차검증할 수 없습니다"}
    if v.get("median_price") is None:
        return {"ok": False, "msg": "엔카 시세가 없어 교차검증 불가 — 먼저 시세 분석을 실행하세요"}
    if not kcar.ENABLED:
        return {"ok": False, "msg": "케이카 수집이 비활성 상태입니다(kcar.ENABLED=False)"}

    year_tol = config.get("year_tol", 1)
    mileage_tol = config.get("mileage_tol", 0.30)
    min_sample = config.get("min_sample_count", 5)
    tol = config.get("cross_source_tol", 0.10)
    trim = encar.trim_hint(v.get("model"))

    # 저장된 감정요항의 연료(신뢰 소스) + 상태 반영용 원문
    from src.paths import DATA_DIR
    fuel, atext = None, ""
    fp = DATA_DIR / (v.get("folder_key") or v["id"]) / "appraisal.txt"
    if fp.exists():
        try:
            atext = fp.read_text(encoding="utf-8")
            fuel = _fuel_from_text(atext)
        except Exception:  # noqa: BLE001
            pass

    # 1) 엔카 재조회(신뢰도 재계산용 원표본) — 매핑 → 연식범위 쿼리
    mp = _resolve_encar(_rebuild_item(v), config, None)
    if not mp:
        return {"ok": False, "msg": "엔카 매핑 불가 — 교차검증 대상 아님"}
    es = encar.new_session()
    yf, yt = (v["year"] - 1) * 100, (v["year"] + 1) * 100 + 99
    try:
        eres = encar.search(es, manufacturer=mp["manufacturer"], model_group=mp["model_group"],
                            car_type=mp.get("car_type", "Y"), premium=mp.get("premium", False),
                            year_from=yf, year_to=yt, limit=100)
    except Exception as e:  # noqa: BLE001
        if _is_block(e):
            raise
        return {"ok": False, "msg": f"엔카 조회 실패: {e}"}
    elist = encar.normalize(eres["results"])

    # 2) 케이카 조회(자유검색=모델 키워드) → 동급 중앙값
    kw = _kcar_keyword(v.get("model"))
    if not kw:
        return {"ok": False, "msg": "케이카 검색 키워드 생성 실패(모델명 없음)"}
    ks = kcar.new_session()
    try:
        kres = kcar.search(ks, kw, limit=60, year=v.get("year"),
                           hybrid=bool(fuel and "하이브리드" in fuel))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"케이카 조회 실패: {e}"}
    finally:
        try:
            ks.close()
        except Exception:  # noqa: BLE001
            pass
    # 케이카 결과를 모델명 토큰으로 필터 — 검색이 키워드 필터에 실패해(타임딜 등 혼합 목록)
    # 엉뚱한 모델이 섞여도 같은 모델만 남겨 사과-사과 비교를 보장(오판정 방지)
    reached = kres.get("reached")   # 가격 있는 판매목록에 실제 도달했는가(검색실패 구분)
    kw_toks = set(kw.split())
    klist_all = kcar.normalize(kres["results"])
    klist = [l for l in klist_all
             if kw_toks & set(str(l.get("model") or "").split())]
    kstats = summarize(klist, form_year=v["year"], mileage_km=v.get("mileage_km"),
                       platform="kcar", year_tol=year_tol, mileage_tol=mileage_tol,
                       fuel=fuel, min_sample=min_sample, trim=trim, config=config)
    kcar_median, kcar_sample = kstats.median_price, kstats.sample_count
    kcar_matched = len(klist)   # 모델 일치 매물 수(진단)

    # 3) 두 소스 대조 → 엔카 원표본으로 신뢰도 재계산(교차검증 상한 반영)
    base = summarize(elist, form_year=v["year"], mileage_km=v.get("mileage_km"),
                     platform="encar", year_tol=year_tol, mileage_tol=mileage_tol,
                     fuel=fuel, min_sample=min_sample, trim=trim,
                     appraisal_value=v.get("appraisal_value"), config=config)
    # 교차검증 적용 조건(오판정 방지):
    #  ① 케이카 동급표본 ≥ 최소치, ② 두 소스가 동일하거나 더 좁은 tier(사과-오렌지 비교 차단)
    tier_ok = (kstats.tier_level is not None and base.tier_level is not None
               and kstats.tier_level <= base.tier_level)
    if not reached:
        status, rel = "single", None
        note = "케이카 판매목록 미도달(검색 흐름 실패) — 교차검증 미적용"
    elif kcar_median is None or kcar_sample < min_sample:
        status, rel = "single", None
        note = (f"케이카 동급 표본 부족({kcar_sample}건, 최소 {min_sample}) — 교차검증 미적용"
                if kcar_sample else "케이카 동급 매물 없음(검색은 도달) — 교차검증 미적용")
    elif not tier_ok:
        status, rel = "single", None
        note = "두 소스의 매칭 범위(tier)가 달라 비교 보류 — 교차검증 미적용"
    else:
        status, rel, note = cross_source_check(base.median_price, kcar_median, tol=tol)
    stats = summarize(elist, form_year=v["year"], mileage_km=v.get("mileage_km"),
                      platform="encar", year_tol=year_tol, mileage_tol=mileage_tol,
                      fuel=fuel, min_sample=min_sample, trim=trim,
                      appraisal_value=v.get("appraisal_value"), config=config,
                      cross_status=status, cross_rel=rel,
                      kcar_median=kcar_median, kcar_sample=kcar_sample)

    fields = {"market_platform": "encar", "encar_total": eres.get("count"),
              "kcar_checked_at": _now(), "analyzed_at": _now(),
              # 교차검증 컬럼은 여기서만 기록(단일 진실원천)
              "kcar_median": stats.kcar_median, "kcar_sample": stats.kcar_sample,
              "cross_source_status": stats.cross_source_status,
              "cross_source_rel": stats.cross_source_rel}
    fields.update(_guarded_market_fields(stats))
    if stats.median_price is not None:
        # 산정 시세 = 엔카 + 케이카(2차) 블렌드. 상한가·판정을 블렌드 시세로 재산정
        # (상태·사진 감가 포함 — 요항 원문·photo_count 전달).
        eff = effective_median({"median_price": stats.median_price,
                                "kcar_median": stats.kcar_median,
                                "kcar_sample": stats.kcar_sample})
        bi = BidInput(median_price=eff, min_sale_price=v.get("min_sale_price") or 0,
                      sample_count=stats.sample_count, platform="encar",
                      accident_grade=v.get("accident_grade") or "none",
                      repair_cost=v.get("repair_cost") or 500000,
                      appraisal_text=atext, photo_count=v.get("photo_count"))
        bid = calculate(bi, config)
        fields.update({"upper_bid": bid.upper_bid, "lower_bound": bid.lower_bound,
                       "judgment": _final_judgment(bid.judgment, stats.confidence_label),
                       "breakdown": json.dumps(bid.breakdown, ensure_ascii=False)})
    db.update_fields(vid, **fields)
    return {"ok": True, "status": status, "rel": rel, "note": note,
            "keyword": kw, "encar_median": base.median_price, "kcar_median": kcar_median,
            "kcar_sample": kcar_sample, "kcar_matched": kcar_matched,
            "kcar_found": len(klist_all), "confidence": stats.confidence,
            "confidence_label": stats.confidence_label}
