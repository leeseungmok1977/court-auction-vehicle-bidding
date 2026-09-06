"""FastAPI 운영 웹도구 — 진행경과 확인 · 선택 · 재산정.

실행: python run_web.py   (또는  uvicorn web.app:app --port 8000)
브라우저: http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (src.* 사용)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from web import db, service  # noqa: E402
from src.collect import kcar  # noqa: E402

app = FastAPI(title="법원경매 차량 입찰가 산정")

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# CSS 캐시 버스팅 — app.css 변경(재빌드) 시 쿼리버전이 바뀌어 브라우저가 새 CSS를 받는다.
def _css_version() -> str:
    try:
        return str(int(os.path.getmtime(BASE / "static" / "app.css")))
    except OSError:
        return "1"


templates.env.globals["css_v"] = _css_version()  # 시작 시점 CSS 버전(재빌드 반영은 재기동 시)
templates.env.globals["alert_count"] = lambda: service.alert_count(3)


# PWA 서비스워커 — 루트 스코프(/)로 서빙해야 앱 전체를 제어(정적경로 서빙 시 스코프가 /static/로 제한됨)
@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


# Android TWA Digital Asset Links — 앱 서명 지문 등록 시 URL 바 없는 신뢰 앱으로 검증됨
@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks():
    return FileResponse(BASE / "static" / ".well-known" / "assetlinks.json",
                        media_type="application/json")

from src.paths import DATA_DIR  # noqa: E402  (배포 시 DATA_DIR 환경변수로 영속 볼륨 지정)

JUDGMENTS = ["입찰 검토 가능", "유찰 대기", "시세 신뢰도 낮음, 수동 검토", "입찰 보류", "종결"]


def _display_judgment(v: dict, today: str):
    """표시용 판정 보정(신뢰): 이미 낙찰이면 '종결', 지난 기일인데 '입찰 검토 가능'으로
    남은 물건(다음 기일 미정)은 '유찰 대기'로 표기. 가짜 '검토 가능' 배지 방지.
    DB 값은 그대로 두고 화면 배지·강조만 실제 상태로 맞춘다."""
    j = v.get("judgment")
    if v.get("auction_result") == "낙찰":
        return "종결"
    if (j == "입찰 검토 가능" and v.get("sale_date") and v.get("sale_date") < today
            and v.get("auction_result") not in ("낙찰", "종결")):
        return "유찰 대기"
    return j


def _won(v):
    return f"{int(v):,}" if isinstance(v, (int, float)) else "—"


def _bcls(j):
    # Stripe 라이트: 연한 배경(-50) + 진한 텍스트(-700) + 연한 보더(-200)
    return {
        "입찰 검토 가능": "bg-emerald-50 text-emerald-700 border border-emerald-200",
        "유찰 대기": "bg-amber-50 text-amber-700 border border-amber-200",
        "시세 신뢰도 낮음, 수동 검토": "bg-sky-50 text-sky-700 border border-sky-200",
        "입찰 보류": "bg-rose-50 text-rose-700 border border-rose-200",
        "종결": "bg-slate-100 text-slate-500 border border-slate-200",
    }.get(j, "bg-slate-100 text-slate-500 border border-slate-200")


def _jshort(j):
    return {"시세 신뢰도 낮음, 수동 검토": "신뢰도 낮음"}.get(j, j or "")


def _acc(g):
    """사고판정 내부 enum → 한글 표시."""
    return {"none": "무사고", "minor": "단순수리", "accident": "사고", "flood": "침수의심"}.get(
        g, g or "—")


import re as _re

# 원문 차명 오염 화이트리스트(정상 트림 'TFSI quattro' 등은 건드리지 않음)
_MDL_FIXES = {"Mer cedes": "Mercedes"}


def _mdl(s):
    """차명 표시 정규화 — 공백 압축 + 알려진 원문 오염만 교정."""
    s = _re.sub(r"\s+", " ", (s or "").strip())
    for bad, good in _MDL_FIXES.items():
        s = s.replace(bad, good)
    return s or "—"


def _sstat(s):
    """상태 표시 정규화 — 내부 예외 원문을 사용자 친화 라벨로. (원문은 title 툴팁용으로 보존)"""
    s = s or ""
    if s.startswith("오류") or "not defined" in s or "Error" in s:
        return "분석 실패 — 재시도"
    if s.startswith("차단"):
        return "차단 감지 — 잠시 후"
    return s or "—"


templates.env.filters["won"] = _won
templates.env.filters["bcls"] = _bcls
templates.env.filters["jshort"] = _jshort
templates.env.filters["acc"] = _acc
templates.env.filters["mdl"] = _mdl
templates.env.filters["sstat"] = _sstat


def _cur_url(request: Request) -> str:
    """현재 경로+쿼리 (뒤로가기 대상 저장용)."""
    q = request.url.query
    return request.url.path + (("?" + q) if q else "")


@app.on_event("startup")
def _startup():
    import threading
    db.init_db()
    db.clear_orphaned_runs()   # 재시작으로 미완결된 좀비 'running' 런 정리
    service.start_scheduler()
    # 기존 물건의 빈 주행거리를 저장된 요항에서 백필(무네트워크)
    threading.Thread(target=service.backfill_mileage_from_files, daemon=True).start()
    # 확정 낙찰을 영구 히스토리에 백필(무네트워크) — 학습 데이터 누적 시작
    threading.Thread(target=service.backfill_sale_results, daemon=True).start()
    # 감정요항 검사만료일·상태등급 백필(무네트워크, 최초 1회) — 목록 필터·정렬용
    threading.Thread(target=service.backfill_appraisal_signals, daemon=True).start()
    # 디스크엔 사진 있는데 photo_count=0으로 어긋난 물건 정정(목록 표시·감가 정합)
    threading.Thread(target=service.backfill_photo_count, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    counts = db.counts_by_judgment()
    run = db.latest_run()
    total = db.total_vehicles()
    starred = len(db.list_vehicles(starred=True))
    # 유망 물건: '높음' 신뢰도 + 오매칭 아님만(median/min 과대 배제) → 예상낙찰가 여유 순.
    # (신뢰 낮은/오매칭 의심 물건이 큰 여유로 상단을 독점하지 않도록 — 실측 신뢰 최우선)
    _bt = service.backtest_stats()
    _disc = _bt.get("discount_median")

    def _promising(v):
        if v.get("market_confidence_label") != "높음":
            return False
        m, mn = v.get("median_price"), v.get("min_sale_price")
        if m and mn and mn > 0 and m / mn > 3.5:   # 시세가 최저가의 3.5배 초과 → 오매칭/이상 의심
            return False
        return True

    def _exp_margin(v):
        exp = service.expected_for(v, _bt)
        return (exp or v.get("upper_bid") or 0) - (v.get("min_sale_price") or 0)
    _cand = [v for v in db.list_vehicles(judgment="입찰 검토 가능") if _promising(v)]
    candidates = sorted(_cand, key=_exp_margin, reverse=True)[:8]
    for v in candidates:      # 유찰횟수 반영 예상낙찰가(대시보드 표시용)
        v["expected_win"] = service.expected_for(v, _bt)
    # 상단 대표 밴드(정보 위계) — 검토 가능 물건의 예상낙찰가 범위·평균 신뢰도 한눈 요약
    _exps = [e for e in (service.expected_for(v, _bt) for v in _cand) if e]
    _confs = [v.get("market_confidence") for v in _cand if v.get("market_confidence")]
    review_summary = None
    if _exps:
        import statistics
        review_summary = {
            "count": len(_cand),
            "exp_lo": min(_exps), "exp_hi": max(_exps),
            "exp_med": int(statistics.median(_exps)),
            "conf_avg": round(sum(_confs) / len(_confs)) if _confs else None,
            "mae": _bt.get("mae_pct"),
        }
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "counts": counts, "run": run, "total": total,
        "starred": starred, "candidates": candidates, "running": service.is_running(),
        "judgments": JUDGMENTS, "settings": db.get_all_settings(),
        "upcoming": db.upcoming_count(30), "pending": db.pending_count(),
        "won": db.won_count(), "backtest": _bt, "review_summary": review_summary,
        "alerts": service.alert_items(3),
    })


@app.get("/landing", response_class=HTMLResponse)
def landing(request: Request):
    """가치제안 랜딩(무료 유입) — 검증된 정확도로 세일즈, 결제는 보류(설계상 건당 리포트)."""
    bt = service.backtest_stats()
    ctx = {
        "request": request,
        "total": len(db.list_vehicles()),
        "won": db.won_count(),
        "upcoming": db.upcoming_count(30),
        "sample": bt.get("sample") or 0,
        "mae": round(bt.get("mae_pct")) if bt.get("mae_pct") else None,
        "discount": round(bt.get("discount_median") * 100) if bt.get("discount_median") else None,
    }
    return templates.TemplateResponse("landing.html", ctx)


@app.post("/daily/settings")
def daily_settings(enabled: str = Form(""), daily_time: str = Form("06:00"),
                   daily_within: int = Form(30), analyze: str = Form(""),
                   analyze_limit: int = Form(0)):
    db.set_setting("daily_enabled", "1" if enabled else "0")
    db.set_setting("daily_time", daily_time or "06:00")
    db.set_setting("daily_within", str(daily_within or 30))
    db.set_setting("daily_analyze", "1" if analyze else "0")
    db.set_setting("daily_analyze_limit", str(analyze_limit or 0))
    return RedirectResponse("/", status_code=303)


@app.post("/daily/run-now")
def daily_run_now(within: int = Form(30), analyze: str = Form("1"),
                  analyze_limit: int = Form(0)):
    service.start_daily(within_days=within, analyze=bool(analyze),
                        analyze_limit=analyze_limit)
    return RedirectResponse("/", status_code=303)


VEHICLES_PAGE_SIZE = 12


@app.get("/vehicles", response_class=HTMLResponse)
def vehicles(request: Request, judgment: str = "", maker: str = "", q: str = "",
             sort: str = "sale_date", upcoming: str = "", result: str = "", status: str = "",
             cond: str = "", page: int = 1):
    # upcoming은 str로 받아 빈값/오염값에 견고하게 파싱(폼 hidden 빈값·손편집 URL 대비)
    up = int(upcoming) if upcoming.strip().lstrip("-").isdigit() else 0
    if up < 0:
        up = 0
    rows = db.list_vehicles(judgment=judgment or None, maker=maker or None,
                            q=q or None, sort=sort, result=result or None,
                            status=status or None, cond=cond or None,
                            upcoming_days=up or None, hide_incomplete=True)
    _bt = service.backtest_stats()
    disc = _bt.get("discount_median")
    mae = _bt.get("mae_pct")
    # 예상낙찰가 계산은 비용이 있으므로 '예상낙찰가순' 정렬처럼 전체가 필요할 때만 전 행 계산,
    # 그 외에는 아래에서 현재 페이지 12행에만 계산(성능 — 목록 렌더 8~26s → 1~2s).
    if sort == "expected":
        for r in rows:
            r["expected_win"] = service.expected_for(r, _bt)
        rows.sort(key=lambda r: (r.get("expected_win") or 0), reverse=True)
    # 페이지네이션 (필터·정렬 후 슬라이스)
    total = len(rows)
    total_pages = max(1, (total + VEHICLES_PAGE_SIZE - 1) // VEHICLES_PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * VEHICLES_PAGE_SIZE
    page_rows = rows[start:start + VEHICLES_PAGE_SIZE]
    if sort != "expected":      # 정렬용 전체계산이 아니면 현재 페이지만
        for r in page_rows:
            r["expected_win"] = service.expected_for(r, _bt)
    mlot = service.multi_lot_ids()
    for r in page_rows:      # 목록 썸네일용 사진 URL(현재 페이지만 폴더 스캔)
        fk = r.get("folder_key") or r["id"]
        pdir = DATA_DIR / fk / "photos"
        if pdir.exists():   # photo_count 대신 실제 디스크 사진 유무로 표시(정합성 어긋나도 안전)
            avail = {p.name for p in pdir.iterdir() if p.is_file()}
            order = [n for n in (r.get("photo_order") or []) if n in avail]  # 비전 분류 순서 우선
            names = (order + sorted(n for n in avail if n not in order))[:12]
            r["photo_urls"] = [f"/photo/{fk}/{n}" for n in names]
        else:
            r["photo_urls"] = []
        r["photo_lot_mixed"] = r["id"] in mlot   # 동일사건 다물건 → 사진 혼재 가능
    from urllib.parse import urlencode
    qs = urlencode({k: v for k, v in {
        "judgment": judgment, "maker": maker, "q": q, "sort": sort,
        "upcoming": up or "", "result": result, "status": status, "cond": cond}.items() if v})
    qs_no_upcoming = urlencode({k: v for k, v in {   # 30일 해제 링크용(upcoming만 제거, 나머지 유지)
        "judgment": judgment, "maker": maker, "q": q, "sort": sort,
        "result": result, "status": status, "cond": cond}.items() if v})
    qs_no_cond = urlencode({k: v for k, v in {        # 상태 필터 토글용(cond만 제거, 나머지 유지)
        "judgment": judgment, "maker": maker, "q": q, "sort": sort,
        "upcoming": up or "", "result": result, "status": status}.items() if v})
    from datetime import date as _date
    _tdy = _date.today().isoformat()
    _tdy_d = _date.today()
    for r in page_rows:      # 표시용 판정 보정(지난기일 검토가능→유찰대기, 낙찰→종결) — 신뢰
        r["judgment"] = _display_judgment(r, _tdy)
        sd = r.get("sale_date")           # D-day(남은 일수) — 법차식 카운트다운 배지
        try:
            r["dday"] = (_date.fromisoformat(sd) - _tdy_d).days if sd else None
        except (ValueError, TypeError):
            r["dday"] = None
        av, mn = r.get("appraisal_value"), r.get("min_sale_price")   # 감정가 대비 %
        r["appr_pct"] = round(100 * mn / av) if (av and mn) else None
    resp = templates.TemplateResponse("vehicles.html", {
        "request": request, "rows": page_rows, "judgment": judgment, "maker": maker,
        "q": q, "sort": sort, "upcoming": up, "result": result, "status": status,
        "cond": cond,
        "judgments": JUDGMENTS, "makers": db.distinct_makers(),
        "today": _date.today().isoformat(), "mae": mae,
        "total": total, "page": page, "total_pages": total_pages,
        "page_size": VEHICLES_PAGE_SIZE, "qs": qs, "qs_no_upcoming": qs_no_upcoming,
        "qs_no_cond": qs_no_cond,
        "range_start": start + 1 if total else 0,
        "range_end": start + len(page_rows),
    })
    resp.set_cookie("last_list", _cur_url(request), max_age=86400)
    return resp


@app.get("/vehicle/{vid}", response_class=HTMLResponse)
def vehicle_detail(request: Request, vid: str, cc: str = "", an: str = ""):
    v = db.get_vehicle(vid)
    if not v:
        return RedirectResponse("/vehicles", status_code=303)
    photos = []
    pdir = DATA_DIR / (v.get("folder_key") or vid) / "photos"
    if pdir.exists():
        avail = {p.name for p in pdir.iterdir() if p.is_file()}
        order = [n for n in (v.get("photo_order") or []) if n in avail]  # 비전 분류 순서 우선
        photos = order + sorted(n for n in avail if n not in order)
    appraisal = ""
    afile = DATA_DIR / (v.get("folder_key") or vid) / "appraisal.txt"
    if afile.exists():
        appraisal = afile.read_text(encoding="utf-8")
    # 상한가 < 최저매각가(유찰 대기)일 때: 목표가 도달까지 예상 유찰 횟수
    wait = None
    ub, floor = v.get("upper_bid"), v.get("min_sale_price")
    if ub is not None and ub > 0 and floor and ub < floor:   # ub>0: math.log 도메인 오류 방지
        import math

        def _rounds(drop):
            return max(1, math.ceil(math.log(ub / floor) / math.log(1 - drop)))

        wait = {"target": ub, "rounds_fast": _rounds(0.30), "rounds_slow": _rounds(0.20)}

    _bk = request.cookies.get("last_list") or ""
    # 쿠키값을 href에 그대로 넣지 않도록 내부 상대경로만 허용(javascript:·data:·//host 등 스킴 차단)
    back_url = _bk if (_bk.startswith("/") and not _bk.startswith("//")) else "/vehicles"
    bt = service.backtest_stats()
    disc = bt.get("discount_median")
    _cd = service.comparable_discount(v, bt)     # 유사 낙찰(같은차종·유사연식·주행) 기반 보정
    comps = service.comparable_sales(v, bt)
    lo = service.expected_winning(v.get("median_price"), bt.get("discount_p25"))
    _hi = service.expected_winning(v.get("median_price"), bt.get("discount_p75"))
    source = None
    if _cd:                                       # 유사 낙찰 기반이면 밴드도 유사사례 분포로
        import statistics as _st
        rr = sorted(c["ratio"] for c in _cd[2] if c.get("ratio"))
        if len(rr) >= 4:
            q = _st.quantiles(rr, n=4)
            lo = service.expected_winning(v.get("median_price"), round(q[0], 3))
            _hi = service.expected_winning(v.get("median_price"), round(q[2], 3))
        source = f"유사 낙찰 {_cd[1]}건 기반"
    # 예상낙찰가 범위 상단은 시세중앙값 미만으로 캡(낙찰가가 시세와 같아지는 건 비현실적)
    if _hi and v.get("median_price"):
        _hi = min(_hi, int(v["median_price"] * 0.97))
    expected = {"price": service.expected_for(v, bt), "lo": lo,
                "hi": _hi, "discount": disc, "sample": bt.get("sample"),
                "mae": bt.get("mae_pct"), "source": source,
                "comp_n": _cd[1] if _cd else 0} if disc else None
    dist = service.price_distribution(
        v, expected["price"] if expected else None, bt.get("mae_pct"))
    # 감정 요항 구조화(색상·연료·검사유효기간·옵션·상태) + 상태 반영 비용
    from src.parse.appraisal import condition_adjustment
    cond = condition_adjustment(appraisal, service.load_config()) if appraisal else None
    asum = cond.get("parsed") if cond else None
    from datetime import date as _date
    v["judgment"] = _display_judgment(v, _date.today().isoformat())   # 표시용 판정 보정(신뢰)
    return templates.TemplateResponse("detail.html", {
        "request": request, "v": v, "photos": photos, "appraisal": appraisal,
        "asum": asum, "cond": cond, "today": _date.today().isoformat(),
        "can_analyze": service.can_analyze(v), "running": service.is_running(),
        "wait": wait, "back_url": back_url, "expected": expected, "dist": dist,
        "verdict": service.plain_verdict(v, expected), "comps_won": comps[:6],
        "eff_median": service.effective_median(v),
        "kcar_enabled": kcar.ENABLED, "cc_msg": cc, "an_msg": an,
    })


@app.get("/vehicle/{vid}/report", response_class=HTMLResponse)
def vehicle_report(request: Request, vid: str):
    """물건별 종합 분석 리포트(인쇄·PDF용 단일 페이지)."""
    from datetime import datetime
    v = db.get_vehicle(vid)
    if not v:
        return RedirectResponse("/vehicles", status_code=303)
    config = service.load_config()
    bt = service.backtest_stats()
    disc = bt.get("discount_median")
    _hi = service.expected_winning(v.get("median_price"), bt.get("discount_p75"))
    if _hi and v.get("median_price"):
        _hi = min(_hi, int(v["median_price"] * 0.97))
    expected = {"price": service.expected_for(v, bt),
                "lo": service.expected_winning(v.get("median_price"), bt.get("discount_p25")),
                "hi": _hi, "discount": disc, "sample": bt.get("sample"),
                "mae": bt.get("mae_pct")} if disc else None
    appraisal = ""
    afile = DATA_DIR / (v.get("folder_key") or vid) / "appraisal.txt"
    if afile.exists():
        appraisal = afile.read_text(encoding="utf-8")
    dist = service.price_distribution(
        v, expected["price"] if expected else None, bt.get("mae_pct"))
    return templates.TemplateResponse("report.html", {
        "request": request, "v": v, "expected": expected, "appraisal": appraisal,
        "report": service.report_data(v, config, bt), "backtest": bt, "dist": dist,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


@app.get("/vehicle/{vid}/appraisal", response_class=HTMLResponse)
def vehicle_appraisal(vid: str):
    """감정평가서 원본(KAPA 공식 문서)을 인앱 뷰어로 연결(저장·재배포하지 않음)."""
    v = db.get_vehicle(vid)
    if not v:
        return RedirectResponse("/vehicles", status_code=303)
    cs_no = service._sa_no_from_docid(v.get("doc_id") or "")
    dxdy = (v.get("sale_date") or "").replace("-", "")
    if not cs_no or not v.get("court_code"):
        return HTMLResponse("<p style='font-family:sans-serif;padding:2rem'>감정평가서 식별정보가 없습니다. 물건을 다시 분석해 주세요.</p>")
    from src.collect import courtdoc
    from src.collect.courtauction_list import new_session, warmup
    try:
        s = new_session(); warmup(s)
        url = courtdoc.resolve_appraisal_url(s, v["court_code"], cs_no, dxdy)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<p style='font-family:sans-serif;padding:2rem'>감정평가서 조회 실패/차단: {e}</p>")
    if not url:
        return HTMLResponse("<p style='font-family:sans-serif;padding:2rem'>이 물건은 감정평가서 전자문서가 없습니다.</p>")
    html = (
        "<!doctype html><html lang=ko><head><meta charset=utf-8>"
        f"<title>감정평가서 · {v.get('model','')}</title>"
        "<style>body{margin:0;font-family:Pretendard,'Malgun Gothic',sans-serif}"
        ".bar{display:flex;gap:1rem;align-items:center;padding:.6rem 1rem;background:#0d253d;color:#fff;font-size:14px}"
        ".bar a{color:#b9b9f9;text-decoration:none}</style></head><body>"
        f"<div class=bar><b>감정평가서 원본</b><span>{v.get('court','')} · {v.get('case_no','')}</span>"
        f"<a href='{url}' target=_blank rel=noopener>↗ 새 탭에서 열기</a>"
        "<span style='margin-left:auto;opacity:.7'>출처: 한국감정평가사협회(KAPA) 공식 문서 — 원본 연결</span></div>"
        f"<iframe src='{url}' style='width:100%;height:calc(100vh - 44px);border:0'></iframe></body></html>")
    return HTMLResponse(html)


@app.get("/photo/{vid}/{filename}")
def photo(vid: str, filename: str):
    # 경로 탈출 방지 — vid·filename 모두 basename으로 정제
    # NUL바이트(%00) 등 비정상 경로는 ValueError를 내므로 잡아서 404로(500 방지)
    try:
        safe_vid = os.path.basename(vid)
        safe = os.path.basename(filename)
        if "\x00" in safe_vid or "\x00" in safe:
            raise ValueError("null byte")
        fp = (DATA_DIR / safe_vid / "photos" / safe).resolve()
        photos_root = (DATA_DIR / safe_vid / "photos").resolve()
        if photos_root in fp.parents and fp.exists() and fp.is_file():
            return FileResponse(str(fp))
    except (ValueError, OSError):
        pass
    return JSONResponse({"error": "not found"}, status_code=404)


@app.post("/vehicle/{vid}/analyze")
def analyze_one(vid: str):
    r = service.analyze_single(vid)
    an = ""
    if r is None:
        an = "분석 실패 — 사건번호 복원 불가(doc_id 없음)."
    elif r.get("status") == "미매핑":
        an = "국산 승용 자동 시세 매핑 대상이 아닙니다(수입·상용·특수차)."
    elif r.get("median_price") is None and r.get("status") not in ("완료",) \
            and r.get("auction_result") != "낙찰" and r.get("judgment") != "종결":
        an = ("법원 상세정보가 비어 있어 분석할 수 없습니다(종결·취하·조회불가 가능). "
              "목록의 사진은 이전 수집분입니다.")
    if an:
        from urllib.parse import quote
        return RedirectResponse(f"/vehicle/{vid}?an={quote(an)}", status_code=303)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/recompute")
def recompute(vid: str, repair_cost: int = Form(0)):
    service.recompute(vid, repair_cost)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/crosscheck")
def crosscheck(vid: str):
    """케이카 2차 소스로 시세 교차검증(온디맨드). 결과 메시지를 배너로 전달."""
    from urllib.parse import quote
    try:
        r = service.kcar_crosscheck(vid)
        if r.get("ok"):
            st = {"agree": "일치", "diverge": "불일치", "single": "단일"}.get(r.get("status"), r.get("status"))
            msg = (f"교차검증 {st} · 엔카 {(r.get('encar_median') or 0)//10000}만 vs "
                   f"케이카 {(r.get('kcar_median') or 0)//10000}만"
                   f"(표본 {r.get('kcar_sample')}건) · 신뢰도 {r.get('confidence_label')} {r.get('confidence')}점")
        else:
            msg = r.get("msg") or "교차검증 실패"
    except Exception as e:  # noqa: BLE001 — 차단 등
        msg = f"교차검증 중단: {e}"
    return RedirectResponse(f"/vehicle/{vid}?cc={quote(msg)}", status_code=303)


@app.post("/vehicle/{vid}/actual")
def actual_price(vid: str, actual_price: str = Form("")):
    """사용자가 확인한 실측 시세 기록(캘리브레이션용)."""
    from datetime import datetime
    try:
        val = int(actual_price) if actual_price.strip() else None
    except ValueError:
        val = None
    db.update_fields(vid, actual_price=val,
                     actual_price_at=None if val is None else datetime.now().strftime("%Y-%m-%d %H:%M"))
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/star")
def star(vid: str):
    v = db.get_vehicle(vid)
    if v:
        db.update_fields(vid, starred=0 if v.get("starred") else 1)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/memo")
def memo(vid: str, memo: str = Form(""), final_bid: str = Form("")):
    fb = int(final_bid) if str(final_bid).strip().isdigit() else None
    db.update_fields(vid, memo=memo, final_bid=fb)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, sort: str = "sale_date"):
    """관심 물건 비교·정렬(PS-06) — 예상낙찰가·여유(예상−최저)·D-day로 후보 비교."""
    from datetime import date as _date
    rows = db.list_vehicles(starred=True, sort="sale_date")
    bt = service.backtest_stats()
    today = _date.today()
    for v in rows:                       # 비교 지표 파생
        exp = service.expected_for(v, bt)
        v["expected_win"] = exp
        v["margin_room"] = (exp - v["min_sale_price"]) if (exp and v.get("min_sale_price")) else None
        try:
            v["dday"] = (_date.fromisoformat(v.get("sale_date")) - today).days
        except (TypeError, ValueError):
            v["dday"] = None
    keys = {
        "sale_date": lambda v: (v.get("sale_date") or "9999"),
        "dday": lambda v: (v["dday"] if v.get("dday") is not None and v["dday"] >= 0 else 9999),
        "expected": lambda v: -(v.get("expected_win") or 0),
        "margin": lambda v: -(v.get("margin_room") or -1e12),
        "min_sale_price": lambda v: (v.get("min_sale_price") or 0),
    }
    rows.sort(key=keys.get(sort, keys["sale_date"]))
    resp = templates.TemplateResponse("watchlist.html", {
        "request": request, "rows": rows, "sort": sort, "today": today.isoformat(),
        "mae": bt.get("mae_pct")})
    resp.set_cookie("last_list", _cur_url(request), max_age=86400)
    return resp


def _manwon_to_won(v: str):
    s = str(v).strip()
    return str(int(s) * 10000) if s.isdigit() else ""


@app.post("/run")
def run(max_items: int = Form(5), scan_limit: int = Form(40), repair_cost: int = Form(500000),
        car_nm: str = Form(""), maker: str = Form(""),
        year_min: str = Form(""), year_max: str = Form(""),
        price_min: str = Form(""), price_max: str = Form(""),
        fail_min: str = Form(""), car_type: str = Form("Y")):
    search = None
    if car_nm.strip() or maker.strip():
        search = {
            "court": {
                "carMdlNm": car_nm.strip(),
                "gdsVendNm": maker.strip(),
                "carMdyrMin": year_min.strip(),
                "carMdyrMax": year_max.strip(),
                "rletLwsDspslPrcMin": _manwon_to_won(price_min),
                "rletLwsDspslPrcMax": _manwon_to_won(price_max),
                "flbdNcntMin": fail_min.strip(),
            },
            "encar_model_group": car_nm.strip(),
            "encar_car_type": car_type or "Y",
        }
    service.start_collection(max_items=max_items, scan_limit=scan_limit,
                             repair_cost=repair_cost, search=search)
    return RedirectResponse("/", status_code=303)


@app.post("/reanalyze")
def reanalyze(max_items: int = Form(20)):
    service.start_reanalyze(max_items=max_items)
    return RedirectResponse("/", status_code=303)


@app.post("/results/run-now")
def results_run_now(max_items: int = Form(300)):
    service.start_results(max_items=max_items)
    return RedirectResponse("/", status_code=303)


@app.post("/recompute-all")
def recompute_all():
    service.start_recompute_all()
    return RedirectResponse("/", status_code=303)


def _db_running(run: dict | None) -> bool:
    """다른 프로세스(CLI/스케줄러)의 실행도 감지 — status=running + 하트비트 최신(120초 이내)."""
    if not run or run.get("status") != "running":
        return False
    hb = db.get_setting("run_heartbeat")
    if not hb:
        return False
    try:
        from datetime import datetime
        return (datetime.now() - datetime.strptime(hb, "%Y-%m-%d %H:%M:%S")).total_seconds() < 120
    except (ValueError, TypeError):
        return False


@app.get("/run/status")
def run_status():
    counts = db.counts_by_judgment()
    run = db.latest_run()
    return {
        "running": service.is_running() or _db_running(run),
        "run": run,
        "total": db.total_vehicles(),
        "upcoming": db.upcoming_count(30),
        "pending": db.pending_count(),
        "ok": counts.get("입찰 검토 가능", 0),
        "wait": counts.get("유찰 대기", 0),
        "hold": counts.get("입찰 보류", 0),
    }
