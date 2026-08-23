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
from src.parse.list_parser import parse_list_response
from src.parse.detail_parser import parse_detail
from src.parse.market_match import summarize
from src.bidcalc.calculator import BidInput, calculate
from src.pipeline import resolve_mapping

from . import db

# 동시 수집 방지용 상태
_lock = threading.Lock()
_active = {"running": False, "run_id": None}


def load_config(path: str = "config.yaml") -> dict:
    return yaml.safe_load(open(path, encoding="utf-8"))


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
    save_item_folder(dresp, item.folder_key, config)
    if getattr(detail, "storage_addr", "") and detail.storage_addr.strip():
        base["location"] = detail.storage_addr
    base.update({
        "mileage_km": detail.mileage_km, "displacement_cc": detail.displacement_cc,
        "fuel_code": detail.fuel_code, "appraisal_value": detail.appraisal_value,
        "fail_count": detail.fail_count, "sale_date": detail.sale_date,
        "accident_grade": detail.accident_grade, "accident_hits": detail.accident_hits,
        "insurance_history": detail.insurance_history,
        "appraisal_ecdoc_id": detail.appraisal_ecdoc_id, "photo_count": detail.photo_count,
        "repair_cost": repair_cost, "analyzed_at": _now(),
        "dxdy_history": detail.dxdy_history, "winning_price": detail.winning_price,
        "auction_result": _resolve_auction_result(detail.dxdy_history, detail.winning_price),
        "result_checked_at": _now(),
    })

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
            stats = summarize(encar.normalize(res["results"]), form_year=item.year,
                              mileage_km=detail.mileage_km, platform="encar",
                              year_tol=config.get("year_tol", 1),
                              mileage_tol=config.get("mileage_tol", 0.30),
                              fuel=detail.fuel_name)   # 요항 텍스트 기반(신뢰) 연료로 매칭
            base.update({
                "market_platform": "encar", "encar_total": res["count"],
                "sample_count": stats.sample_count, "mean_price": stats.mean_price,
                "median_price": stats.median_price, "min_price": stats.min_price,
                "match_label": stats.match_label,
            })
            if stats.median_price is not None:  # 표본 있으면 산정
                bi = BidInput(median_price=stats.median_price, min_sale_price=item.min_sale_price or 0,
                              sample_count=stats.sample_count, platform="encar",
                              accident_grade=detail.accident_grade, repair_cost=repair_cost,
                              appraisal_text=detail.appraisal_text)
                bid = calculate(bi, config)
                base.update({
                    "upper_bid": bid.upper_bid, "lower_bound": bid.lower_bound,
                    "judgment": bid.judgment, "breakdown": bid.breakdown, "status": "완료",
                })
                return base
        except Exception:  # noqa: BLE001
            pass

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
        for idx, (raw, item) in enumerate(zip(raws, items)):
            if processed >= max_items or idx >= scan_limit:
                break
            db.update_run(run_id, scanned=idx + 1,
                          message=f"{item.case_no} {item.model} 분석 중…")
            try:
                rec = _analyze_item(cs, es, raw, item, config, repair_cost, search)
            except Exception as e:  # noqa: BLE001
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
        usage_name="", location=v.get("location") or "", status_code="",
        doc_id=v.get("doc_id") or "")


def _reanalyze(max_items: int, repair_cost: int, run_id: int) -> None:
    """기존 '미매핑' 국산 물건에 상세·시세를 소급 적용."""
    config = load_config()
    try:
        # 대상: 미매핑 + 자동매핑 가능 + docid로 saNo 복원 가능
        targets = []
        for v in db.list_vehicles():
            if v.get("status") not in ("미매핑", "미분석"):
                continue
            if not _sa_no_from_docid(v.get("doc_id") or ""):
                continue
            targets.append(v)
        db.update_run(run_id, target=min(max_items, len(targets)) or 0,
                      message=f"재분석 대상 {len(targets)}건")

        cs = new_session(); warmup(cs)
        es = encar.new_session()
        processed = 0
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
            except Exception:  # noqa: BLE001
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
    while page <= max_pages:
        resp = fetch_list_page(cs, page_no=page, page_size=40).json()
        rows = resp["data"]["dlt_srchResult"]
        total = resp["data"]["dma_pageInfo"].get("groupTotalCount") or 0
        if not rows:
            break
        for item in parse_list_response(resp):
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
            break
        page += 1
    db.set_setting("last_upcoming_count", str(stored))
    db.set_setting("last_upcoming_at", _now())
    if finalize and run_id:
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"입찰예정 {stored}건 갱신 (≤{within_days}일)")
    return stored


def daily_update(within_days: int = 30, analyze: bool = True,
                 analyze_limit: int = 0, run_id: Optional[int] = None,
                 repair_cost: int = 500000) -> dict:
    """일일 갱신: ① 입찰예정 목록 수집 → ② 국산차 시세 분석까지 연속 진행."""
    config = load_config()
    stored = collect_upcoming(within_days=within_days, run_id=run_id, finalize=False)
    analyzed = 0
    if analyze:
        # 분석 대상: 입찰예정 창의 미분석/미매핑 국산차
        targets = [v for v in db.list_vehicles(upcoming_days=within_days)
                   if v.get("status") in ("미분석", "미매핑")
                   and _sa_no_from_docid(v.get("doc_id") or "") and can_analyze(v)]
        if analyze_limit and analyze_limit > 0:
            targets = targets[:analyze_limit]
        if run_id:
            db.update_run(run_id, target=len(targets), processed=0, scanned=0)

        cs = new_session(); warmup(cs)
        es = encar.new_session()
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
                if rec.get("status") == "완료":
                    analyzed += 1
            except Exception:  # noqa: BLE001
                pass
            if run_id:
                db.update_run(run_id, processed=analyzed)
    # ③ 낙찰결과 반영 (매각기일 지난 물건)
    results = update_results(run_id=run_id, finalize=False)
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
                   finalize: bool = True) -> int:
    """매각기일이 지난 물건의 낙찰결과(낙찰가/유찰)를 매각결과검색으로 반영.

    법원(cortOfcCd)별로 자동차 매각결과를 순회해 (사건번호, 물건순번)으로 매칭한다.
    물건상세와 달리 종결된 물건의 낙찰가도 보존되므로 실제 낙찰가를 얻을 수 있다.
    """
    from src.collect import courtauction_result as cr
    today = date.today().isoformat()
    recency_days = 45   # 매각결과검색이 보존하는 대략적 기간

    # 재조정(미래기일)된 유찰/기타 결과 정리 + 만료 물건 종결 처리(무네트워크)
    db.clear_rescheduled_results()
    db.mark_aged_out(days=recency_days)

    # 대상: 최근 recency_days 이내 매각기일 지남 + 낙찰/종결 아님 + saNo 복원 가능
    def _in_window(sd):
        return sd and sd <= today and sd >= (date.today() - timedelta(days=recency_days)).isoformat()
    targets = [v for v in db.list_vehicles()
               if _in_window(v.get("sale_date"))
               and v.get("auction_result") != "낙찰"   # 낙찰만 최종. 창 밖 만료건은 위 mark_aged_out가 종결 처리
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
    for i, bo in enumerate(court_list):
        if run_id:
            db.update_run(run_id, scanned=i + 1,
                          message=f"낙찰결과 조회 {i + 1}/{len(court_list)} 법원")
        try:
            rows = cr.fetch_all_results(s, bo)
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
                      "result_checked_at": _now()}
            # 최저매각가·유찰·기일을 최종값으로 동기화 (낙찰가<최저가 오해 방지)
            for k, val in cr.final_fields(row).items():
                if val is not None:
                    fields[k] = val
            if fields.get("min_sale_price") is not None:
                fields["lower_bound"] = fields["min_sale_price"]
            db.update_fields(v["id"], **fields)
            updated += 1
        if run_id:
            db.update_run(run_id, processed=updated)

    if blocked:
        if finalize and run_id:
            db.update_run(run_id, status="error", finished_at=_now(),
                          message=f"차단/비정상 응답 감지 — 중단 (낙찰결과 {updated}건 반영)")
        return updated
    if finalize and run_id:
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"낙찰결과 {updated}건 반영")
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
    import os
    from src.parse.detail_parser import _mileage_from_text
    updated = 0
    for v in db.list_vehicles():
        if v.get("mileage_km") is not None:
            continue
        fk = v.get("folder_key") or v.get("id")
        fp = os.path.join("data", fk, "appraisal.txt")
        if not os.path.exists(fp):
            continue
        try:
            km = _mileage_from_text(open(fp, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            km = None
        if km:
            db.update_fields(v["id"], mileage_km=km)
            updated += 1
    return updated


def can_analyze(v: dict) -> bool:
    """상세를 수집할 수 있는지 (docid로 saNo 복원 가능). 수입·상용 포함 모든 물건 대상."""
    return bool(_sa_no_from_docid(v.get("doc_id") or ""))


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
    rec = _analyze_item(cs, es, raw, item, config,
                        repair_cost or v.get("repair_cost") or 500000)
    db.upsert_vehicle(rec)
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
    if run_id:
        db.update_run(run_id, target=len(keys), processed=0, scanned=0)

    es = encar.new_session()
    updated = 0
    consecutive_fail = 0
    for i, key in enumerate(keys):
        man, mg, ct, prem, year = key
        if run_id:
            db.update_run(run_id, scanned=i + 1,
                          message=f"시세 재교정 {i + 1}/{len(keys)} · {mg} {year}")
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
            fp = os.path.join("data", v.get("folder_key") or v["id"], "appraisal.txt")
            if os.path.exists(fp):
                try:
                    fuel = _fuel_from_text(open(fp, encoding="utf-8").read())
                except Exception:  # noqa: BLE001
                    pass
            stats = summarize(listings, form_year=v["year"], mileage_km=v.get("mileage_km"),
                              platform="encar", year_tol=year_tol, mileage_tol=mileage_tol,
                              fuel=fuel)
            fields = {"market_platform": "encar", "encar_total": res.get("count"),
                      "sample_count": stats.sample_count, "mean_price": stats.mean_price,
                      "median_price": stats.median_price, "min_price": stats.min_price,
                      "match_label": stats.match_label, "analyzed_at": _now()}
            if stats.median_price is not None:
                bi = BidInput(median_price=stats.median_price,
                              min_sale_price=v.get("min_sale_price") or 0,
                              sample_count=stats.sample_count, platform="encar",
                              accident_grade=v.get("accident_grade") or "none",
                              repair_cost=v.get("repair_cost") or 500000)
                bid = calculate(bi, config)
                fields.update({"upper_bid": bid.upper_bid, "lower_bound": bid.lower_bound,
                               "judgment": bid.judgment,
                               "breakdown": json.dumps(bid.breakdown, ensure_ascii=False)})
            db.update_fields(v["id"], **fields)
            updated += 1
        if run_id:
            db.update_run(run_id, processed=updated)

    if finalize and run_id:
        db.update_run(run_id, status="done", finished_at=_now(),
                      message=f"시세 재교정 {updated}건")
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
                     lower_bound=bid.lower_bound, judgment=bid.judgment,
                     breakdown=json.dumps(bid.breakdown, ensure_ascii=False),
                     analyzed_at=_now())
    return db.get_vehicle(vid)
