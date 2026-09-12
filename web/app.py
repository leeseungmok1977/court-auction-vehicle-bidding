"""FastAPI 운영 웹도구 — 진행경과 확인 · 선택 · 재산정.

실행: python run_web.py   (또는  uvicorn web.app:app --port 8000)
브라우저: http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 import 경로에 추가 (src.* 사용)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, PlainTextResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from web import db, service, brands, auth  # noqa: E402
from src.collect import kcar  # noqa: E402

# docs/redoc/openapi는 기본 경로에서 끈다 — 공개 도메인에 관리자 쓰기 엔드포인트 목록
# (/run·/reanalyze·/daily/run-now 등)과 파라미터 스키마를 통째로 노출할 이유가 없다.
# 관리자(SSH 터널)용으로는 아래에서 _require_admin을 건 동일 경로를 다시 연다.
app = FastAPI(title="법원경매 차량 입찰가 산정",
              docs_url=None, redoc_url=None, openapi_url=None)

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
# None을 빈 문자열로 렌더(격리로 비운 필드가 'None' 텍스트로 새거나 미가드 참조가 깨지지 않게)
templates.env.finalize = lambda x: "" if x is None else x
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# CSS 캐시 버스팅 — app.css 변경(재빌드) 시 쿼리버전이 바뀌어 브라우저가 새 CSS를 받는다.
def _css_version() -> str:
    try:
        return str(int(os.path.getmtime(BASE / "static" / "app.css")))
    except OSError:
        return "1"


templates.env.globals["css_v"] = _css_version()  # 시작 시점 CSS 버전(재빌드 반영은 재기동 시)
templates.env.globals["alert_count"] = lambda: service.alert_count(3)


# ── 관리자 모드 (MONETIZATION_SPEC TASK-M03 — SSH 터널 전용) ──────────────────
# 관리자 화면·운영 도구·엔카 원자료는 '앱/공개 도메인'에 두지 않는다(APK 디컴파일·심사
# 리스크·데이터 노출 방지). 운영자는 SSH 로컬 터널로만 접근한다:
#   ssh -i naechaget.pem -L 9000:127.0.0.1:8000 ubuntu@43.202.126.180
#   → 브라우저 http://127.0.0.1:9000  (엔카 원자료 + 운영 도구 표시)
# 판정 근거(보안): uvicorn은 127.0.0.1:8000(loopback) 전용 바인딩 + 8000 외부 차단.
#   도달 경로는 (a) nginx 프록시(공개 도메인 — X-Forwarded-For 부가) 또는 (b) SSH 터널
#   (직결 — XFF 없음)뿐. 따라서 'XFF 없음 + Host가 loopback' = 터널 = 운영자 = 관리자.
#   공개 사용자는 반드시 nginx를 거치므로(XFF 존재) 절대 관리자가 될 수 없다.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_admin(request: Request) -> bool:
    if request.headers.get("x-forwarded-for"):     # nginx 경유(공개) → 관리자 아님
        return False
    return (request.url.hostname or "").lower() in _LOOPBACK_HOSTS   # 터널 직결(loopback)


templates.env.globals["is_admin"] = is_admin
# 사용자·등급(M04 뼈대) — 지금은 전원 tier=1. M11+에서 require_tier로 게이팅.
templates.env.globals["current_user"] = auth.current_user
templates.env.globals["user_tier"] = auth.user_tier
# 광고(AdSense) — pub-ID를 설정에 넣기 전까진 완전 비활성. TWA엔 AdMob 불가 → 웹 AdSense.
templates.env.globals["adsense_client"] = lambda: db.get_setting("adsense_client", "")


def _require_admin(request: Request) -> None:
    """운영 엔드포인트 보호 — 공개 도메인엔 존재 자체를 숨긴다(404). 터널에서만 동작."""
    from fastapi import HTTPException
    if not is_admin(request):
        raise HTTPException(status_code=404)


@app.get("/openapi.json", include_in_schema=False)
def _admin_openapi(request: Request):
    """관리자 전용 OpenAPI 스키마. 공개 도메인에서는 404."""
    _require_admin(request)
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False)
def _admin_docs(request: Request):
    """관리자 전용 Swagger UI. 공개 도메인에서는 404."""
    _require_admin(request)
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/openapi.json", title="내차GET API")


@app.get("/admin", include_in_schema=False)
def admin_status(request: Request):
    if is_admin(request):
        body = ("관리자 모드 <b>ON</b> (SSH 터널) · "
                "<a href='/admin/anomalies'>무결성 검토 기록</a> · <a href='/'>홈</a>")
    else:
        body = ("관리자 화면은 SSH 터널로만 접근합니다: "
                "<code>ssh -L 9000:127.0.0.1:8000 …</code> 후 <code>http://127.0.0.1:9000</code>"
                " · <a href='/'>홈</a>")
    return HTMLResponse(f"<p style='font-family:sans-serif;padding:2rem'>{body}</p>")


@app.get("/admin/anomalies", include_in_schema=False)
def admin_anomalies(request: Request):
    """무결성 검토 감사기록(최종 검토 단계에서 남긴 이상·재확인 결과) — 관리자 전용."""
    import html as _html
    _require_admin(request)
    rows = db.list_anomalies(200)
    trs = "".join(
        "<tr><td>{ts}</td><td>{cn}</td><td>{ac}</td><td>{rs}</td><td>{nt}</td></tr>".format(
            ts=_html.escape(a.get("ts") or ""), cn=_html.escape(a.get("case_no") or ""),
            ac=_html.escape(a.get("action") or ""), rs=_html.escape(a.get("reasons") or ""),
            nt=_html.escape(a.get("note") or "")) for a in rows)
    doc = (
        "<html><head><meta charset='utf-8'><title>무결성 검토 기록</title>"
        "<style>body{font-family:sans-serif;padding:1.5rem;font-size:13px}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}"
        "th{background:#f4f6f9}td:nth-child(3){font-weight:600}</style></head><body>"
        f"<h2>무결성 검토 기록 <span style='color:#888;font-weight:400'>· {len(rows)}건</span></h2>"
        "<p><a href='/admin'>← 관리자</a> · resolved=재확인 후 복원, quarantined=등록 보류(숨김), error=재조회 오류</p>"
        "<table><thead><tr><th>시각</th><th>사건번호</th><th>조치</th><th>사유</th><th>메모</th></tr></thead>"
        f"<tbody>{trs or '<tr><td colspan=5>기록 없음</td></tr>'}</tbody></table></body></html>")
    return HTMLResponse(doc)


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
    if v.get("status") == "상세없음":     # 법원 목록·상세에서 사라짐(변경·취하·연기) → 검토가능 아님
        return "확인 필요"
    if (j == "입찰 검토 가능" and v.get("sale_date") and v.get("sale_date") < today
            and v.get("auction_result") not in ("낙찰", "종결")):
        return "유찰 대기"
    return j


def _won(v):
    return f"{int(v):,}" if isinstance(v, (int, float)) else "—"


_TONE_CLS = {
    "ok": "bg-emerald-50 text-emerald-700 border border-emerald-200",
    "caution": "bg-amber-50 text-amber-700 border border-amber-200",
    "stop": "bg-rose-50 text-rose-700 border border-rose-200",
    "wait": "bg-slate-100 text-slate-600 border border-slate-200",
}


def _tcls(tone):
    """판정 톤 → 칩 색. 레거시 judgment 문자열 대신 bid_state의 톤을 쓴다."""
    return _TONE_CLS.get(tone, _TONE_CLS["wait"])


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


def _car_name(maker, model):
    """제조사+차명 결합 표시 — 차명이 이미 제조사로 시작하면 중복 제거.
    예: maker='BMW', model='BMW 530i xDrive' → 'BMW 530i xDrive'(‘BMW BMW …’ 방지).
    차명에 제조사가 없으면(예: '쏘나타') 정상적으로 '현대 쏘나타'로 결합."""
    m = _mdl(model)
    mk = _re.sub(r"\s+", " ", (maker or "").strip())
    if m == "—":
        return mk or "차량"
    if mk and m.lower().startswith(mk.lower()):
        return m
    return (mk + " " + m).strip() if mk else m


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
templates.env.filters["tcls"] = _tcls
templates.env.filters["jshort"] = _jshort
templates.env.filters["acc"] = _acc
# 물건 단위 사고판정 — 근거 없는 'none'을 '무사고'로 단정하지 않는다(service.accident_label).
templates.env.filters["accv"] = service.accident_label
templates.env.filters["mdl"] = _mdl
templates.env.filters["sstat"] = _sstat
templates.env.globals["car_name"] = _car_name   # 제조사+차명 중복 제거 결합(‘BMW BMW …’ 방지)


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
    # 헤더 "총 N대 모니터링" — 목록과 같은 모수여야 한다. COUNT(*)를 쓰면 1320이라 띄우고
    # 눌러 들어가면 1167이 나온다(2026-09-12 2회차 패널 앱품질 지적 3).
    total = service.lifecycle_partition()["total"]
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

    def _exp_margin(v):                       # 유망도 = 시세 대비 예상낙찰가 절감액(클수록 저가 매수)
        exp = service.expected_for(v, _bt)
        return (v.get("median_price") or 0) - (exp or v.get("upper_bid") or 0)
    _cand = [v for v in db.list_vehicles(judgment="입찰 검토 가능") if _promising(v)]
    candidates = sorted(_cand, key=_exp_margin, reverse=True)[:8]
    for v in candidates:      # 유찰횟수 반영 예상낙찰가(대시보드 표시용)
        v["expected_win"] = service.expected_for(v, _bt)
    # 상단 대표 밴드(달력 하단으로 이동) + 오늘의 추천 캐러셀(첫화면 상단, 매일 아침 갱신)
    review_summary = service.review_summary(_bt)
    daily_picks = service.get_daily_picks(5)
    _adm = is_admin(request)
    _pv = lambda rows: rows if _adm else [service.public_view(r, False) for r in rows]  # noqa: E731
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "counts": counts, "run": run, "total": total,
        "encar_health": service.encar_health_status(),   # 시세 수집 차단·지연 정직 고지
        "candidates": _pv(candidates), "running": service.is_running(),
        "judgments": JUDGMENTS, "settings": db.get_all_settings(),
        "upcoming": db.upcoming_count(30), "pending": db.pending_count(),
        "won": db.won_count(), "backtest": _bt, "review_summary": review_summary,
        "lifecycle": service.lifecycle_partition(),   # 겹치지 않는 상태 분해(합=총대수)
        "alerts": _pv(service.alert_items(3)),
        "top_makers": [dict(name=m, n=n, **brands.brand_asset(m)) for m, n in db.top_makers(8)],
        "daily_picks": daily_picks,
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


@app.get("/ads.txt", response_class=PlainTextResponse, include_in_schema=False)
def ads_txt():
    """AdSense 승인용 ads.txt — pub-ID(설정 adsense_client) 넣으면 자동 게시, 없으면 404.
    TWA는 웹이라 app-ads.txt(AdMob용)가 아니라 ads.txt를 쓴다."""
    ac = db.get_setting("adsense_client", "")
    pub = ac.replace("ca-", "").strip() if ac else ""
    if not pub.startswith("pub-"):
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    """개인정보처리방침(공개 독립 페이지) — Play·AdMob 심사 필수. 문의 이메일은 설정으로 교체 가능."""
    return templates.TemplateResponse("privacy.html", {
        "request": request, "updated": "2026-09-11", "site": "naechaget.co.kr",
        "contact": db.get_setting("privacy_contact", "koreanplus@gmail.com"),
    })


@app.post("/daily/settings")
def daily_settings(request: Request, enabled: str = Form(""), daily_time: str = Form("06:00"),
                   daily_within: int = Form(30), analyze: str = Form(""),
                   analyze_limit: int = Form(0)):
    _require_admin(request)
    db.set_setting("daily_enabled", "1" if enabled else "0")
    db.set_setting("daily_time", daily_time or "06:00")
    db.set_setting("daily_within", str(daily_within or 30))
    db.set_setting("daily_analyze", "1" if analyze else "0")
    db.set_setting("daily_analyze_limit", str(analyze_limit or 0))
    return RedirectResponse("/", status_code=303)


@app.post("/daily/run-now")
def daily_run_now(request: Request, within: int = Form(30), analyze: str = Form("1"),
                  analyze_limit: int = Form(0)):
    _require_admin(request)
    service.start_daily(within_days=within, analyze=bool(analyze),
                        analyze_limit=analyze_limit)
    return RedirectResponse("/", status_code=303)


VEHICLES_PAGE_SIZE = 12


@app.get("/vehicles", response_class=HTMLResponse)
def vehicles(request: Request, judgment: str = "", maker: str = "", q: str = "",
             sort: str = "recent", upcoming: str = "", result: str = "", status: str = "",
             cond: str = "", page: int = 1, date: str = "", court: str = "", promising: str = "",
             segment: str = "", all: str = "", usepick: str = "", bucket: str = ""):
    # upcoming은 str로 받아 빈값/오염값에 견고하게 파싱(폼 hidden 빈값·손편집 URL 대비)
    up = int(upcoming) if upcoming.strip().lstrip("-").isdigit() else 0
    if up < 0:
        up = 0
    # all=1: 상태 분해 KPI 링크용 — 불완전 물건 숨김을 해제해 카드 수와 목록 수가 정확히 일치.
    _hide_incomplete = all != "1"
    rows = db.list_vehicles(judgment=judgment or None, maker=maker or None,
                            q=q or None, sort=sort, result=result or None,
                            status=status or None, cond=cond or None,
                            upcoming_days=up or None, hide_incomplete=_hide_incomplete,
                            date=date or None, court=court or None,
                            promising=bool(promising))
    if segment:      # 차종 프리셋(상용·패밀리·SUV·세단·경차) — 모델명 근사 분류로 필터
        rows = [r for r in rows if service.vehicle_segment(r) == segment]
    _bt = service.backtest_stats()
    if bucket:       # 대시보드 카드 링크 — 카드 수와 목록 수가 정확히 같아야 한다
        rows = [r for r in rows if service.in_lifecycle_bucket(r, bucket, _bt)]
    if usepick == "1":   # 실사용 추천 — 되팔이 마진이 아니라 '소매보다 싼가'로 거른다
        rows = [r for r in rows if service.is_personal_use_pick(r, _bt)]
        for r in rows:   # 추천 근거(소매 대비 절감액)를 화면에 보여주기 위해 행에 싣는다
            r["use_saving"] = service.personal_use_saving(r, _bt)
        rows.sort(key=lambda r: -(r.get("use_saving") or 0))
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
    # 필터 4종을 손으로 나열하다 보니 새 파라미터를 넣을 때마다 빠뜨린다 — bucket·usepick이
    # 페이지네이션·칩 링크에서 전부 누락돼, 실사용 추천 22건에서 "2"를 누르면 전체 1167건이
    # 나왔다(2026-09-12 디자인 검수 블로커). 한 곳에서 만들고 필요한 키만 뺀다.
    _filters = {"judgment": judgment, "maker": maker, "q": q, "sort": sort,
                "upcoming": up or "", "result": result, "status": status, "cond": cond,
                "date": date, "court": court, "promising": promising, "segment": segment,
                "bucket": bucket, "usepick": usepick, "all": all}

    def _qs(*drop: str) -> str:
        return urlencode({k: v for k, v in _filters.items() if v and k not in drop})

    qs = _qs()
    qs_no_upcoming = _qs("upcoming")    # 30일 해제 링크용(upcoming만 제거, 나머지 유지)
    qs_no_cond = _qs("cond")            # 상태 필터 토글용
    qs_no_segment = _qs("segment")      # 차종 프리셋 칩용
    qs_no_bucket = _qs("bucket")        # 버킷 해제 칩용
    from datetime import date as _date
    _tdy = _date.today().isoformat()
    _tdy_d = _date.today()
    for r in page_rows:      # 표시용 판정 보정(지난기일 검토가능→유찰대기, 낙찰→종결) — 신뢰
        r["judgment"] = _display_judgment(r, _tdy)
        # 목록 카드 칩도 상세·리포트와 **같은 판정**을 말해야 한다. 예전엔 레거시
        # judgment 문자열이라, 상세에서 "이번 회차 입찰 부적합"인 차가 목록에서는
        # 앰버 "유찰 대기"로 보였다(4회차 디자인·경매 P0).
        r["bidst"] = service.bid_state(r, _bt)
        sd = r.get("sale_date")           # D-day(남은 일수) — 법차식 카운트다운 배지
        try:
            r["dday"] = (_date.fromisoformat(sd) - _tdy_d).days if sd else None
        except (ValueError, TypeError):
            r["dday"] = None
        av, mn = r.get("appraisal_value"), r.get("min_sale_price")   # 감정가 대비 %
        r["appr_pct"] = round(100 * mn / av) if (av and mn) else None
    if not is_admin(request):     # 엔카 원자료 격리(M01) — 목록 각 행에서 제거
        page_rows = [service.public_view(r, False) for r in page_rows]
    resp = templates.TemplateResponse("vehicles.html", {
        "request": request, "rows": page_rows, "judgment": judgment, "maker": maker,
        "q": q, "sort": sort, "upcoming": up, "result": result, "status": status,
        "cond": cond, "date": date, "court": court, "promising": promising,
        "segment": segment, "segment_presets": [(k, lbl) for k, lbl, _ in service.VEHICLE_SEGMENTS],
        "usepick": usepick == "1",
        "judgments": JUDGMENTS, "makers": db.distinct_makers(),
        "today": _date.today().isoformat(), "mae": mae,
        "total": total, "page": page, "total_pages": total_pages,
        "page_size": VEHICLES_PAGE_SIZE, "qs": qs, "qs_no_upcoming": qs_no_upcoming,
        "qs_no_cond": qs_no_cond, "qs_no_segment": qs_no_segment,
        "qs_no_bucket": qs_no_bucket, "bucket": bucket,
        "range_start": start + 1 if total else 0,
        "range_end": start + len(page_rows),
    })
    resp.set_cookie("last_list", _cur_url(request), max_age=86400, secure=True, samesite="lax")
    return resp


@app.get("/api/vehicles/count")
def vehicles_count(judgment: str = "", maker: str = "", q: str = "", result: str = "",
                   status: str = "", cond: str = "", upcoming: str = "", date: str = "",
                   court: str = "", segment: str = "", all: str = "", bucket: str = "",
                   usepick: str = ""):
    """저장한 검색의 '새 매물' 감지용 — 동일 필터의 현재 건수만 반환(JSON). 외부 데이터 없음.

    ⚠️ `/vehicles`와 **같은 모수**를 써야 한다. 예전엔 hide_incomplete를 넘기지 않아
    "현재 1,320건"이라고 알린 뒤 눌러 들어가면 1,167건이 나왔다(2026-09-12 패널 지적).
    """
    up = int(upcoming) if upcoming.strip().lstrip("-").isdigit() else 0
    rows = db.list_vehicles(judgment=judgment or None, maker=maker or None, q=q or None,
                            result=result or None, status=status or None, cond=cond or None,
                            upcoming_days=(up or None), date=date or None, court=court or None,
                            hide_incomplete=(all != "1"))
    if segment:
        rows = [r for r in rows if service.vehicle_segment(r) == segment]
    if bucket or usepick == "1":     # /vehicles와 같은 필터를 타야 건수가 일치한다
        _bt = service.backtest_stats()
        if bucket:
            rows = [r for r in rows if service.in_lifecycle_bucket(r, bucket, _bt)]
        if usepick == "1":
            rows = [r for r in rows if service.is_personal_use_pick(r, _bt)]
    return {"total": len(rows)}


@app.get("/accuracy", response_class=HTMLResponse)
def accuracy(request: Request):
    """예측 적중률 사후검증 — 과거 낙찰 물건으로 예상낙찰가 vs 실제 낙찰가를 정직 측정(LOO).
    median/winning은 공개 데이터라 공개 노출 가능(엔카 표본수 등 원자료 없음)."""
    bt = service.backtest_stats()
    pool = bt.get("pred_pool") or []
    scatter, axis_max, omitted = [], 0, 0
    if pool:
        # 축 상한을 95퍼센타일로 — 소수 고가 이상치가 저가 밀집 구간을 뭉개지 않게(가독성).
        # 상한 초과분은 그래프에서만 생략(통계·MAE엔 그대로 포함)하고 건수를 노출(무음 절단 금지).
        vals = sorted(max(p["pred"], p["actual"]) for p in pool)
        axis_max = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
        for p in pool:
            if max(p["pred"], p["actual"]) > axis_max:
                omitted += 1
                continue
            scatter.append({"x": round(p["actual"] / axis_max * 100, 2),
                            "y": round(p["pred"] / axis_max * 100, 2),
                            "within": p["err_pct"] <= 20})
    return templates.TemplateResponse("accuracy.html", {
        "request": request, "bt": bt, "scatter": scatter,
        "axis_max": axis_max, "scatter_omitted": omitted, "recent": pool[:24],
        # 층화 — "어디서 잘 맞고 어디서 안 맞는가". 전체 MAE 하나만 내면
        # 표본에 없는 유형에도 정확도를 전이시키는 과대주장이 된다(3회차 경매·중고차 지적).
        "strata": service.accuracy_strata(bt), "strata_min_n": service.ACCURACY_STRATUM_MIN_N,
    })


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request, ym: str = ""):
    """경매 달력 — 월별 그리드에 날짜별 매각기일 물건 수 표시(법차 벤치마킹)."""
    import calendar as _cal
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    try:
        if ym and len(ym) == 7:
            y, m = int(ym[:4]), int(ym[5:7])
            _date(y, m, 1)   # 유효성
        else:
            y, m = today.year, today.month
    except (ValueError, TypeError):
        y, m = today.year, today.month
    first = _date(y, m, 1)
    last = _date(y, m, _cal.monthrange(y, m)[1])
    counts = db.sale_date_counts(first.isoformat(), last.isoformat())
    cal = _cal.Calendar(firstweekday=6)   # 일요일 시작
    grid = [[{
        "iso": d.isoformat(), "day": d.day, "in_month": d.month == m,
        "count": counts.get(d.isoformat(), 0),
        "is_today": d == today, "is_past": d < today,
    } for d in wk] for wk in cal.monthdatescalendar(y, m)]
    return templates.TemplateResponse("calendar.html", {
        "request": request, "y": y, "m": m, "grid": grid,
        "total": sum(counts.values()),
        "upcoming_total": sum(c for iso, c in counts.items() if iso >= today.isoformat()),
        "prev_ym": (first - _td(days=1)).strftime("%Y-%m"),
        "next_ym": (last + _td(days=1)).strftime("%Y-%m"),
        "today_iso": today.isoformat(),
        "sale_stats": service.last_month_sale_stats(),   # 지난달 낙찰 실적 카드(달력 하단)
    })


@app.get("/courts", response_class=HTMLResponse)
def courts_view(request: Request):
    """법원별 물건 수 — 지역(법원) 선택 탐색(법차 '근처 법원' 벤치마킹)."""
    rows = db.court_counts()   # [(court, n)] 내림차순
    total = sum(n for _, n in rows)
    return templates.TemplateResponse("courts.html", {
        "request": request, "courts": rows, "total": total,
    })


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
    # 예상낙찰가 + 밴드(보수/균형/공격)를 **단일 소스**로 산출 → 상단 카드·추천 전략·코멘트 계산식 일치
    _band = service.expected_band(v, bt)
    # ⚠ comps는 **최저매각가가 없을 때만** 산정에 쓰인다(service.expected_for 폴백 경로).
    # 예전엔 comparable_discount가 값을 내기만 하면 "산정에 반영" 라벨이 붙어, 최저가가 있는
    # 대부분의 물건에서 **검증 가능한 거짓**을 화면에 찍고 있었다(3회차 경매 지적 2).
    _used_comps = bool(_cd) and not (_band and (_band.get("basis") or {}).get("kind") == "min_premium")
    source = (f"유사 낙찰 {_cd[1]}건 참고" if _used_comps else None) if _cd else None
    expected = None
    if _band:
        expected = {"price": _band["price"], "lo": _band["lo"], "hi": _band["hi"],
                    "premium": _band.get("premium"), "basis": _band.get("basis") or {},
                    "discount": disc, "sample": bt.get("sample"),
                    # 전체 MAE가 아니라 **이 유형**의 실측 오차. 없으면 None(배지 안 찍음).
                    "mae": (service.accuracy_for(v, bt) or {}).get("mae"),
                    "acc": service.accuracy_for(v, bt), "source": source,
                    "comp_n": _cd[1] if _cd else 0,
                    # 낙찰 확률 — 실측 (낙찰가÷최저가) 분포에서 계산. 표본 부족이면 None이고
                    # 화면은 확률을 표시하지 않는다(하드코딩 ~25/50/75% 폐기, 4회차 품질 P0).
                    "p_lo": service.win_probability(v, _band.get("lo"), bt) if _band else None,
                    "p_mid": service.win_probability(v, _band.get("price"), bt) if _band else None,
                    "p_hi": service.win_probability(v, _band.get("hi"), bt) if _band else None,
                    "comp_used": _used_comps,          # 실제로 산정에 쓰였는가
                    "comp_ratio": _cd[0] if _cd else None}
    dist = service.price_distribution(
        v, expected["price"] if expected else None, bt.get("mae_pct"))
    # 감정 요항 구조화(색상·연료·검사유효기간·옵션·상태) + 상태 반영 비용
    from src.parse.appraisal import condition_adjustment
    _cfg = service.load_config()
    cond = condition_adjustment(appraisal, _cfg) if appraisal else None
    asum = cond.get("parsed") if cond else None
    from datetime import date as _date
    v["judgment"] = _display_judgment(v, _date.today().isoformat())   # 표시용 판정 보정(신뢰)
    # ── 엔카 원자료 격리(M01): 파생값은 원본 v로 먼저 계산, 컨텍스트엔 비관리자용 사본 ──
    _adm = is_admin(request)
    eff_med = service.effective_median(v)                 # 소매 시세(유지) — 원본으로 계산
    # 판정 단일 소스 — 상세와 리포트가 같은 결론을 말하게 한다(3회차 패널 4인 합의 지적).
    _bidst = service.bid_state(v, bt, _cfg)
    verdict = service.plain_verdict(v, expected, _bidst)
    can_an = service.can_analyze(v)
    return templates.TemplateResponse("detail.html", {
        "request": request, "v": service.public_view(v, _adm), "photos": photos, "appraisal": appraisal,
        "asum": asum, "cond": cond, "today": _date.today().isoformat(),
        "can_analyze": can_an, "running": service.is_running(),
        "wait": wait, "back_url": back_url, "expected": expected,
        "dist": dist if _adm else None,                   # 동급 매물 분포(엔카 viz)는 관리자만
        "verdict": verdict, "comps_won": comps[:6],
        "eff_median": eff_med,
        "kcar_enabled": kcar.ENABLED, "cc_msg": cc, "an_msg": an,
        "newcar_public": bool(_cfg.get("newcar_public", False)),   # 당시 출시가 공개 여부(config 전환)
        # 낙찰 시 간이 총비용(낙찰가+취득세+이전·탁송) — 초보용 '그래서 총 얼마' 답변. 전체는 리포트 06.
        "allin": service.allin_estimate(expected["price"] if expected else None, _cfg),
        # 다음 기일 예상 최저가 — '이번 회차를 건너뛸까'를 판단할 유일한 숫자
        "next_min": service.next_min_sale(v),
        # 표시된 최저매각가가 직전(유찰된) 기일 값으로 보이면 그렇게 밝힌다
        "stale_floor": service.stale_floor(v),
        # 판정 단일 소스 — 상세·리포트가 서로 다른 말을 하지 않도록 같은 값을 쓴다
        "bidst": _bidst,
        "use": service.personal_use_detail(v, bt, _cfg),
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
    _band = service.expected_band(v, bt)   # 상세와 동일한 단일 소스(중심=균형, 밴드 일치)
    expected = None
    if _band:
        expected = {"price": _band["price"], "lo": _band["lo"], "hi": _band["hi"],
                    "premium": _band.get("premium"), "basis": _band.get("basis") or {},
                    "discount": disc, "sample": bt.get("sample"), "mae": bt.get("mae_pct")}
    appraisal = ""
    afile = DATA_DIR / (v.get("folder_key") or vid) / "appraisal.txt"
    if afile.exists():
        appraisal = afile.read_text(encoding="utf-8")
    # 사진(비전 분류 순서 우선) — 로컬 /photo 서빙(렌더 시 외부호출 없음)
    photos = []
    pdir = DATA_DIR / (v.get("folder_key") or vid) / "photos"
    if pdir.exists():
        avail = {p.name for p in pdir.iterdir() if p.is_file()}
        order = [n for n in (v.get("photo_order") or []) if n in avail]
        photos = order + sorted(n for n in avail if n not in order)
    # 유사 낙찰 실적(같은 차종 과거 법원 실낙찰 — 엔카 원자료 아님, 공개 가능).
    # 표시용은 같은 차종을 넓게(연식±3·주행±50%) 유사도순으로 — 실낙찰 근거를 풍부히 보이기 위함.
    # (예상낙찰가 개별 보정에 쓰는 comparable_discount의 엄격 매칭[연식±1·주행±30%]은 그대로 유지)
    comps_won = service.comparable_sales(v, bt, year_tol=3, mileage_tol=0.5, limit=8)
    import statistics as _st
    _cr = [c["ratio"] for c in comps_won if c.get("ratio")]
    comp_ratio_med = round(_st.median(_cr), 3) if _cr else None
    # 감정 요항 구조화(검사유효기간·상태등급·연료·색상) — 상세와 동일
    from src.parse.appraisal import condition_adjustment
    cond = condition_adjustment(appraisal, config) if appraisal else None
    asum = cond.get("parsed") if cond else None
    _bidst = service.bid_state(v, bt, config)             # 판정 단일 소스(상세·리포트 공용)
    verdict = service.plain_verdict(v, expected, _bidst)  # 판정은 하지 않고 문장만 만든다
    dist = service.price_distribution(
        v, expected["price"] if expected else None, bt.get("mae_pct"))
    _adm = is_admin(request)
    _report = service.report_data(v, config, bt)          # 원본 v로 계산
    return templates.TemplateResponse("report.html", {
        "request": request, "v": service.public_view(v, _adm), "expected": expected, "appraisal": appraisal,
        "report": _report, "backtest": bt, "dist": dist if _adm else None,
        "photos": photos, "comps_won": comps_won, "asum": asum, "verdict": verdict,
        # 리포트의 판정·비율은 상세·산정과 **같은 시세**를 써야 한다. plain_verdict/report_data는
        # 이미 effective_median(엔카+케이카 블렌드)을 쓰는데 템플릿만 원본 median_price를 써서
        # 같은 물건에 "11% 싸다"(상세)와 "시세 초과·비권장"(리포트)이 동시에 나왔다
        # (2026-09-12 2회차 패널 앱품질 지적 1).
        "eff_median": service.effective_median(v),
        # 실사용 손익분기 상한선 — "얼마까지 써도 되는가". 경매 전문가가 1·2회차 연속
        # 지적한 항목으로, 예상낙찰가(예측)보다 실제로 더 중요한 값이다.
        "max_bid": _bidst.get("max_bid"),
        "next_min": service.next_min_sale(v),
        # 표시된 최저매각가가 직전(유찰된) 기일 값으로 보이면 그렇게 밝힌다
        "stale_floor": service.stale_floor(v),
        "bidst": _bidst,          # 판정 단일 소스 — 상세와 같은 값
        "use": service.personal_use_detail(v, bt, config),
        "comp_min_n": service.COMP_MIN_N, "comp_ratio_med": comp_ratio_med,
        # 01 종합 프로필(6축, 미산출=None; 매물건수는 관리자만, 잔존가치는 출시가 공개 규칙과 동일 게이트)
        "hexa": service.hexagon_scores(v, include_private=_adm,
                                       newcar_ok=_adm or bool(config.get("newcar_public", False)),
                                       asum=asum),
        "mile_mismatch": service.mileage_mismatch(v, asum),
        "newcar_public": bool(config.get("newcar_public", False)),   # 당시 출시가 공개 여부(compliance §6 조건 충족 시 config로 전환)
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


@app.get("/vehicle/{vid}/appraisal", response_class=HTMLResponse)
def vehicle_appraisal(vid: str):
    """감정평가서 원본 안내(딥링크). 원본 PDF는 KAPA(ca.kapanet.or.kr)가 법원 세션 토큰 경로로만
    서빙하며, 우리 서버(EC2)는 KAPA에 네트워크 차단되어 프록시·저장이 불가하다. 따라서 감정 요항(핵심
    내용)은 상세 화면에 그대로 제공하고, 원본 전체는 법원경매정보로 정직하게 안내한다(외부 요청 없음)."""
    import html as _html
    v = db.get_vehicle(vid)
    if not v:
        return RedirectResponse("/vehicles", status_code=303)
    court = _html.escape(v.get("court") or "—")
    case = _html.escape(v.get("case_no") or "—")
    # 법원경매정보 '자동차·중기검색' 페이지(실측 URL) — 딥링크가 물건 단위로는 안 되어 검색 진입점으로 안내
    court_url = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
    page = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>감정평가서 원본 안내</title>
<style>
  :root{color-scheme:light}
  body{margin:0;font-family:'Pretendard','Malgun Gothic',system-ui,sans-serif;background:#f6f9fc;color:#0d253d;
       min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
  .card{max-width:460px;width:100%;background:#fff;border:1px solid #e3e8ee;border-radius:20px;
       padding:28px 24px;box-shadow:0 10px 30px rgba(13,37,61,.08)}
  .ic{width:52px;height:52px;border-radius:14px;background:#eef0ff;display:flex;align-items:center;
       justify-content:center;font-size:26px;margin-bottom:14px}
  h1{font-size:19px;margin:0 0 10px;font-weight:800;letter-spacing:-.01em}
  p{font-size:14px;line-height:1.65;color:#4b5a73;margin:0 0 12px}
  .meta{background:#f6f9fc;border:1px solid #e3e8ee;border-radius:12px;padding:12px 14px;margin:16px 0;font-size:13px;line-height:1.7}
  .meta b{color:#0d253d}
  .note{font-size:12.5px;color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:11px 12px;margin:16px 0;line-height:1.6}
  .btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;box-sizing:border-box;
       padding:13px;border-radius:12px;background:#533afd;color:#fff;font-weight:700;font-size:15px;text-decoration:none;border:0;cursor:pointer}
  .btn.sec{background:#fff;color:#4b5a73;border:1px solid #cdd7e3;margin-top:10px}
  .warn{font-size:12px;color:#5e6c85;margin-top:16px;text-align:center;line-height:1.6}
</style></head><body>
<div class="card">
  <div class="ic">&#128196;</div>
  <h1>감정평가서 원본</h1>
  <p>원본 감정평가서(PDF)는 <b>대한민국 법원경매정보</b>의 한국감정평가사협회(KAPA) 전자문서로 제공되며, <b>법원 열람 세션을 통해서만</b> 접근됩니다. 보안 정책상 외부 앱에서 직접 표시할 수 없습니다.</p>
  <div class="meta">법원 &nbsp;<b>__COURT__</b><br>사건번호 &nbsp;<b>__CASE__</b></div>
  <div class="note">&#9989; 이 앱은 감정평가서의 <b>핵심 내용(감정 요항 &mdash; 차량 상태&middot;사고&middot;주행거리&middot;감정 근거)</b>을 물건 상세 화면에 이미 정리해 제공합니다. 아래는 <b>원본 전체 문서</b>가 필요할 때만 이용하세요.</div>
  <a class="btn" href="__COURT_URL__" target="_blank" rel="noopener">법원경매정보에서 열람 &#8599;</a>
  <button class="btn sec" onclick="window.close()">닫기</button>
  <div class="warn">법원경매정보 &rarr; <b>자동차&middot;중기검색</b>에서 위 <b>법원&middot;사건번호</b>로 조회하시면 원본 감정평가서&middot;현황조사서를 열람할 수 있습니다.</div>
</div></body></html>""".replace("__COURT__", court).replace("__CASE__", case).replace("__COURT_URL__", court_url)
    return HTMLResponse(page)


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
def analyze_one(request: Request, vid: str):
    _require_admin(request)
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
def recompute(request: Request, vid: str, repair_cost: int = Form(0)):
    _require_admin(request)
    service.recompute(vid, repair_cost)
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


@app.post("/vehicle/{vid}/crosscheck")
def crosscheck(request: Request, vid: str):
    _require_admin(request)
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
def actual_price(request: Request, vid: str, actual_price: str = Form("")):
    """사용자가 확인한 실측 시세 기록(캘리브레이션용) — 운영자 전용."""
    _require_admin(request)
    from datetime import datetime
    try:
        val = int(actual_price) if actual_price.strip() else None
    except ValueError:
        val = None
    db.update_fields(vid, actual_price=val,
                     actual_price_at=None if val is None else datetime.now().strftime("%Y-%m-%d %H:%M"))
    return RedirectResponse(f"/vehicle/{vid}", status_code=303)


# 메모·최종입찰가는 기기 로컬(localStorage) 저장으로 이관 — 서버 저장 라우트 없음(다중 사용자 안전).


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request, sort: str = "sale_date", ids: Optional[str] = None):
    """즐겨찾기 비교·정렬(PS-06) — 예상낙찰가·여유(예상−최저)·D-day로 후보 비교.

    즐겨찾기는 기기 로컬(localStorage)에 저장되므로 클라이언트가 물건 ID 목록(ids,
    콤마구분)을 넘겨준다. ids 파라미터가 아예 없으면(첫 진입) 하이드레이트 모드로
    응답해 클라이언트가 로컬 ID를 읽어 재요청하게 한다. ids=""(빈값)은 즐겨찾기 없음."""
    from datetime import date as _date
    if ids is None:                       # 아직 클라이언트가 ID 미전달 → 하이드레이트
        resp = templates.TemplateResponse("watchlist.html", {
            "request": request, "hydrate": True, "sort": sort, "rows": [], "ids_csv": ""})
        resp.set_cookie("last_list", _cur_url(request), max_age=86400, secure=True, samesite="lax")
        return resp
    id_list, _seen = [], set()             # 순서 보존 + 중복 제거 + 남용 방지 상한
    for s in ids.split(","):
        s = s.strip()
        if s and s not in _seen:
            _seen.add(s); id_list.append(s)
        if len(id_list) >= 200:
            break
    rows = [v for v in (db.get_vehicle(i) for i in id_list) if v]
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
        # 여유 큰 순(내림차순). margin_room=0(여유 없음)은 실제 값으로, None(데이터 없음)만 최하단.
        "margin": lambda v: -(v["margin_room"]) if v.get("margin_room") is not None else 1e12,
        "min_sale_price": lambda v: (v.get("min_sale_price") or 0),
    }
    rows.sort(key=keys.get(sort, keys["sale_date"]))
    if not is_admin(request):     # 엔카 원자료 격리(M01)
        rows = [service.public_view(r, False) for r in rows]
    resp = templates.TemplateResponse("watchlist.html", {
        "request": request, "rows": rows, "sort": sort, "today": today.isoformat(),
        "mae": bt.get("mae_pct"), "hydrate": False, "ids_csv": ",".join(id_list)})
    resp.set_cookie("last_list", _cur_url(request), max_age=86400, secure=True, samesite="lax")
    return resp


def _manwon_to_won(v: str):
    s = str(v).strip()
    return str(int(s) * 10000) if s.isdigit() else ""


@app.post("/run")
def run(request: Request, max_items: int = Form(5), scan_limit: int = Form(40),
        repair_cost: int = Form(500000),
        car_nm: str = Form(""), maker: str = Form(""),
        year_min: str = Form(""), year_max: str = Form(""),
        price_min: str = Form(""), price_max: str = Form(""),
        fail_min: str = Form(""), car_type: str = Form("Y")):
    _require_admin(request)
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
def reanalyze(request: Request, max_items: int = Form(20)):
    _require_admin(request)
    service.start_reanalyze(max_items=max_items)
    return RedirectResponse("/", status_code=303)


@app.post("/results/run-now")
def results_run_now(request: Request, max_items: int = Form(300)):
    _require_admin(request)
    service.start_results(max_items=max_items)
    return RedirectResponse("/", status_code=303)


@app.post("/recompute-all")
def recompute_all(request: Request):
    _require_admin(request)
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
def run_status(request: Request):
    counts = db.counts_by_judgment()
    run = db.latest_run()
    running = service.is_running() or _db_running(run)
    # 공개 응답은 화면이 실제로 쓰는 것만 준다. 유휴 상태의 지난 런 기록(실행 시각·소요·건수)은
    # 운영 지표라 공개할 이유가 없고, 수집 주기를 그대로 알려주는 셈이 된다.
    # UI(base.html poll)는 running이 false면 run/카운트를 읽지 않으므로 동작에 지장이 없다.
    if not is_admin(request) and not running:
        return {"running": False}
    return {
        "running": running,
        "run": run,
        "total": db.total_vehicles(),
        "upcoming": db.upcoming_count(30),
        "pending": db.pending_count(),
        "ok": counts.get("입찰 검토 가능", 0),
        "wait": counts.get("유찰 대기", 0),
        "hold": counts.get("입찰 보류", 0),
    }
