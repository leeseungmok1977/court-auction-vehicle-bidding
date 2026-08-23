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

app = FastAPI(title="법원경매 차량 입찰가 산정")

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

DATA_DIR = ROOT / "data"

JUDGMENTS = ["입찰 검토 가능", "유찰 대기", "시세 신뢰도 낮음, 수동 검토", "입찰 보류"]


def _won(v):
    return f"{int(v):,}" if isinstance(v, (int, float)) else "—"


def _bcls(j):
    return {
        "입찰 검토 가능": "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
        "유찰 대기": "bg-amber-500/15 text-amber-400 border border-amber-500/30",
        "시세 신뢰도 낮음, 수동 검토": "bg-sky-500/15 text-sky-300 border border-sky-500/30",
        "입찰 보류": "bg-red-500/15 text-red-400 border border-red-500/30",
    }.get(j, "bg-[#1E293B] text-[#94A3B8] border border-[#334155]")


def _jshort(j):
    return {"시세 신뢰도 낮음, 수동 검토": "신뢰도 낮음"}.get(j, j or "")


templates.env.filters["won"] = _won
templates.env.filters["bcls"] = _bcls
templates.env.filters["jshort"] = _jshort


def _cur_url(request: Request) -> str:
    """현재 경로+쿼리 (뒤로가기 대상 저장용)."""
    q = request.url.query
    return request.url.path + (("?" + q) if q else "")


@app.on_event("startup")
def _startup():
    import threading
    db.init_db()
    service.start_scheduler()
    # 기존 물건의 빈 주행거리를 저장된 요항에서 백필(무네트워크)
    threading.Thread(target=service.backfill_mileage_from_files, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    counts = db.counts_by_judgment()
    run = db.latest_run()
    total = db.total_vehicles()
    starred = len(db.list_vehicles(starred=True))
    candidates = [v for v in db.list_vehicles(judgment="입찰 검토 가능", sort="upper_bid")][:8]
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "counts": counts, "run": run, "total": total,
        "starred": starred, "candidates": candidates, "running": service.is_running(),
        "judgments": JUDGMENTS, "settings": db.get_all_settings(),
        "upcoming": db.upcoming_count(30), "pending": db.pending_count(),
        "won": db.won_count(),
    })


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


@app.get("/vehicles", response_class=HTMLResponse)
def vehicles(request: Request, judgment: str = "", maker: str = "", q: str = "",
             sort: str = "sale_date", upcoming: int = 0, result: str = ""):
    rows = db.list_vehicles(judgment=judgment or None, maker=maker or None,
                            q=q or None, sort=sort, result=result or None,
                            upcoming_days=upcoming if upcoming else None)
    resp = templates.TemplateResponse("vehicles.html", {
        "request": request, "rows": rows, "judgment": judgment, "maker": maker,
        "q": q, "sort": sort, "upcoming": upcoming, "result": result,
        "judgments": JUDGMENTS, "makers": db.distinct_makers(),
    })
    resp.set_cookie("last_list", _cur_url(request), max_age=86400)
    return resp


@app.get("/vehicle/{vid}", response_class=HTMLResponse)
def vehicle_detail(request: Request, vid: str):
    v = db.get_vehicle(vid)
    if not v:
        return RedirectResponse("/vehicles", status_code=303)
    photos = []
    pdir = DATA_DIR / (v.get("folder_key") or vid) / "photos"
    if pdir.exists():
        photos = sorted(p.name for p in pdir.iterdir() if p.is_file())
    appraisal = ""
    afile = DATA_DIR / (v.get("folder_key") or vid) / "appraisal.txt"
    if afile.exists():
        appraisal = afile.read_text(encoding="utf-8")
    # 상한가 < 최저매각가(유찰 대기)일 때: 목표가 도달까지 예상 유찰 횟수
    wait = None
    ub, floor = v.get("upper_bid"), v.get("min_sale_price")
    if ub is not None and floor and ub < floor:
        import math

        def _rounds(drop):
            return max(1, math.ceil(math.log(ub / floor) / math.log(1 - drop)))

        wait = {"target": ub, "rounds_fast": _rounds(0.30), "rounds_slow": _rounds(0.20)}

    back_url = request.cookies.get("last_list") or "/vehicles"
    return templates.TemplateResponse("detail.html", {
        "request": request, "v": v, "photos": photos, "appraisal": appraisal,
        "can_analyze": service.can_analyze(v), "running": service.is_running(),
        "wait": wait, "back_url": back_url,
    })


@app.get("/photo/{vid}/{filename}")
def photo(vid: str, filename: str):
    # 경로 탈출 방지
    safe = os.path.basename(filename)
    fp = DATA_DIR / vid / "photos" / safe
    if fp.exists() and fp.is_file():
        return FileResponse(str(fp))
    return JSONResponse({"error": "not found"}, status_code=404)


@app.post("/vehicle/{vid}/analyze")
def analyze_one(vid: str):
    service.analyze_single(vid)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/recompute")
def recompute(vid: str, repair_cost: int = Form(0)):
    service.recompute(vid, repair_cost)
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
def watchlist(request: Request):
    rows = db.list_vehicles(starred=True, sort="sale_date")
    resp = templates.TemplateResponse("watchlist.html", {"request": request, "rows": rows})
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
