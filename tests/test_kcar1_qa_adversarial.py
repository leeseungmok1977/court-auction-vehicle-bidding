# -*- coding: utf-8 -*-
"""KCAR-1 qa 적대적 반증 (2026-09-27, 지시 2026-09-27-34).

backend 의 `test_kcar1_retire.py`(46개)가 **함수 단위**로 게이트를 민다. 이 파일은 그 바깥을 민다 —
게이트가 옳아도 **다른 길로** 케이카 값이 공개 숫자에 들어가거나, 꺼 둔 수집이 **다른 입구로** 다시
브라우저를 띄우면 KCAR-1 은 실패다. 그래서 재는 것:

  A. 우회 경로 — 케이카 컬럼을 읽는 함수가 허용 목록 밖에 새로 생기면 빨간불(AST 전수).
     템플릿에서 케이카 컬럼은 관리자 시세 카드 안에서만 읽힌다.
     공개 목록 카드의 '입찰 상한'과 홈 캐러셀 저장분(하루를 버틴다)도 게이트를 따른다.
  B. 입구 — 매일 경로를 **처음부터**(daily_update → requery_missing_market → recompute_all_market)
     돌려 브라우저(Playwright)·KcarSession 0회를 잰다. 관리자 [분석]·[전체 재교정] 라우트도.
  C. 감시 — 사내 대시보드 표시층(supply_display)이 '중지(의도)'를 초록 그대로 두고 경보로 올리지 않는다.
  D. 되돌리기 — 설정을 켜고 **새로 받은** 값(오늘·표본 ≥5)이면 매일 경로·관리자 교차검증 모두 다시 섞인다.
     재개 경로가 죽지 않았는지.

각 단언은 반대쪽(켜짐·신선·표본 충분이면 실제로 섞인다·시도한다)을 함께 민다 — 한쪽만 있으면 공허하다.
외부 요청 0 — 루프백 밖 소켓 연결·DNS 조회를 막는다(backend 사고 §6 재발 방지). Playwright 는 가짜다.
"""
import ast
import json
import re
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import db, service
from src.collect import kcar

_ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
ON = {"enabled": True, "max_age_days": 7, "min_sample": 5}
STOP_PHRASE = "2026-09-27 오너 결정으로 중지 · 낡은 값은 가격에 섞지 않음(나이 7일·표본 5건 게이트)"
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


def _ts(days_ago: int, hm: str = "23:10:39") -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat() + " " + hm


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """루프백 밖 연결·DNS 를 막는다 — 코드가 퇴행해도 요청은 나가지 않는다(C.4)."""
    import socket
    real_connect, real_connect_ex, real_gai = (socket.socket.connect, socket.socket.connect_ex,
                                               socket.getaddrinfo)
    loop = {"127.0.0.1", "::1", "localhost", "testserver"}

    def _host(addr):
        return str(addr[0] if isinstance(addr, tuple) and addr else addr)

    def _deny(self, addr, *a, **k):
        if _host(addr) in loop:
            return real_connect(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 이 파일은 외부 요청 0 이어야 한다(C.4)")

    def _deny_ex(self, addr, *a, **k):
        if _host(addr) in loop:
            return real_connect_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 이 파일은 외부 요청 0 이어야 한다(C.4)")

    def _gai(host, *a, **k):
        if host is None or str(host) in loop:
            return real_gai(host, *a, **k)
        raise AssertionError(f"외부 DNS 조회 {host!r} — 이 파일은 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _gai)


def _policy(monkeypatch, pol):
    monkeypatch.setattr(service, "kcar_blend_policy", lambda config=None: dict(pol))


def _config_on(monkeypatch):
    """설정 파일을 켠 것처럼 — kcar_blend_policy(config) 도 이 값을 읽는다(가짜 정책이 아니다)."""
    real = service.load_config()
    on = dict(real, kcar_cross_enabled=True)
    monkeypatch.setattr(service, "load_config", lambda *a, **k: on)
    return on


def _browser_meter(monkeypatch) -> dict:
    """브라우저를 띄우는 **모든** 입구에 계수기를 단다 — kcar.new_session · KcarSession · sync_playwright.

    가장 아래(sync_playwright)까지 막는 이유: 누군가 new_session 을 거치지 않고 KcarSession 을
    직접 만들거나, 다른 모듈이 Playwright 를 부르면 위 두 개만으로는 못 잡는다."""
    import playwright.sync_api as psa
    n = {"new_session": 0, "KcarSession": 0, "sync_playwright": 0}

    def _mk(key):
        def _boom(*a, **k):
            n[key] += 1
            raise RuntimeError(f"[qa] {key} 호출됨 — 브라우저 기동 시도")
        return _boom
    monkeypatch.setattr(kcar, "new_session", _mk("new_session"))
    monkeypatch.setattr(kcar, "KcarSession", _mk("KcarSession"))
    monkeypatch.setattr(psa, "sync_playwright", _mk("sync_playwright"))
    return n


def _encar_listings(n=20, price=30_000_000, year=2021, model="쏘렌토", platform="encar"):
    return [{"platform": platform, "form_year": year, "mileage_km": 28000 + i * 100,
             "price_won": price + i * 50_000, "model": model,
             "badge": None, "fuel": None, "id": f"{platform[0]}{i}"} for i in range(n)]


def _encar_meter(monkeypatch, listings) -> dict:
    e = {"new_session": 0, "search": 0}

    def _sess():
        e["new_session"] += 1
        return object()

    def _search(*a, **k):
        e["search"] += 1
        return {"count": len(listings), "results": list(listings)}
    monkeypatch.setattr(service.encar, "new_session", _sess)
    monkeypatch.setattr(service.encar, "search", _search)
    monkeypatch.setattr(service.encar, "normalize", lambda rows: list(rows))
    return e


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "k1qa.db")
    db.init_db()
    return tmp_path


# ═════════════════════════════════════════════════════════════════════════
# A. 우회 경로
# ═════════════════════════════════════════════════════════════════════════
_KCAR_KEYS = ("kcar_median", "kcar_sample", "kcar_checked_at", "cross_source_status", "cross_source_rel")
# 2026-09-27 qa 가 전수로 확인한 허용 목록. 여기에 **새 함수가 늘면** 그 함수가 게이트를 거치는지 사람이
# 보고 목록에 올려야 한다 — 조용히 늘면 `effective_median` 을 우회하는 두 번째 블렌드가 생길 수 있다.
_ALLOWED_READERS = {
    "<module>",              # PRIVATE_FIELDS(공개 차단 목록)
    "_blend_ok", "effective_median", "kcar_value_usable", "kcar_age_days",   # 게이트 자체
    "market_provenance",     # cross_n = _blend_ok(v) 일 때만
    "_kcar_cross_live", "kcar_crosscheck", "recompute_all_market",          # 수집·재적용(게이트 적용 확인됨)
    "supply_snapshot",       # 감시용 max(kcar_checked_at)
}


def test_A1_케이카_컬럼을_읽는_함수는_허용_목록_안에만_있다():
    tree = ast.parse((_ROOT / "web" / "service.py").read_text(encoding="utf-8"))
    readers: dict = {}

    class _V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.value in _KCAR_KEYS:
                readers.setdefault(self.stack[0] if self.stack else "<module>", set()).add(node.value)
    _V().visit(tree)
    assert readers, "전제: 케이카 컬럼을 읽는 곳이 하나도 안 잡혔다 — 파서가 틀렸다"
    extra = set(readers) - _ALLOWED_READERS
    assert not extra, (f"케이카 컬럼을 읽는 새 함수 {sorted(extra)} — effective_median/_blend_ok 게이트를 "
                       "거치는지 확인하고 허용 목록에 올릴 것(KCAR-1)")
    # 반대쪽: 허용 목록의 핵심 셋은 실제로 읽는다(목록이 비어서 통과하는 게 아니다)
    assert {"_blend_ok", "effective_median", "market_provenance"} <= set(readers)


def test_A2_템플릿의_케이카_컬럼은_관리자_시세_카드_안에서만_읽힌다():
    tpl = _ROOT / "web" / "templates"
    pat = re.compile(r"\bv\.(kcar_\w+|cross_source_\w+)")
    outside = {p.name: len(pat.findall(p.read_text(encoding="utf-8")))
               for p in tpl.glob("*.html") if p.name != "detail.html"}
    assert not {k: n for k, n in outside.items() if n}, f"공개 템플릿이 케이카 컬럼을 읽는다: {outside}"
    d = (tpl / "detail.html").read_text(encoding="utf-8")
    hits = [m.start() for m in pat.finditer(d)]
    assert hits, "전제: detail.html 관리자 카드가 케이카 컬럼을 읽고 있어야 이 검사가 의미가 있다"
    end = d.index("{# /관리자 전용 시세 카드 #}")
    start = d.rindex("{% if is_admin(request) %}", 0, hits[0])
    assert all(start < h < end for h in hits), "관리자 시세 카드 밖에서 케이카 컬럼을 읽는다"


def _g80(**kw) -> dict:
    """실사용 갈래가 **블렌드 때만** '지금 사면 이득'이 되는 모양(라이브 2026타경50102_1 G80 을 본뜸).
    엔카 1,530만 · 케이카 1,700만(표본 5·어제) · 최저가 960만. 전제는 테스트 안에서 다시 확인한다."""
    v = {"id": "QG_1", "folder_key": "QG_1", "case_no": "2026타경9101", "item_no": "1",
         "court": "강릉지원", "maker": "현대", "model": "G80", "year": 2017, "mileage_km": 123622,
         "min_sale_price": 9_600_000, "appraisal_value": 18_000_000, "fail_count": 3,
         "sale_date": (TODAY + timedelta(days=20)).isoformat(), "sale_time": "10:00",
         "status": "완료", "judgment": "유찰 대기", "median_price": 15_300_000, "sample_count": 31,
         "market_confidence": 87, "market_confidence_label": "높음", "market_cv": 0.182,
         "accident_grade": "accident", "runnable": "unknown", "condition_level": "poor",
         "photo_count": 2, "analyzed_at": _ts(0, "06:40:00"), "repair_cost": 500_000,
         "kcar_median": 17_000_000, "kcar_sample": 5, "kcar_checked_at": _ts(1)}
    v.update(kw)
    return v


@pytest.fixture
def g80_env(tmpdb, monkeypatch):
    """G80 모양 1대 + 이 유형 오차 10%(층 통계 대신 고정 — 여기서 재는 것은 층이 아니라 게이트)."""
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    monkeypatch.setattr(service, "accuracy_for",
                        lambda v, bt=None: {"mae": 10.0, "n": 100, "label": "테스트층",
                                            "group": "제조사", "within10": 60})
    db.upsert_vehicle(_g80())
    return db.get_vehicle("QG_1")


def test_A3_전제_이_물건은_블렌드_때만_지금_사면_이득이다(g80_env, monkeypatch):
    v = g80_env
    enc_only = dict(v, kcar_median=None, kcar_sample=None)
    assert service.personal_use_tier(enc_only, BT)["tier"] == "cheap"
    assert service.personal_use_tier(v, BT)["tier"] == "cheap", "저장소 설정(꺼짐)이면 엔카 단독과 같아야 한다"
    _policy(monkeypatch, ON)
    assert service.personal_use_tier(v, BT)["tier"] == "now", "전제 붕괴 — 켜면 '지금 사면 이득'이어야 한다"


def test_A4_홈_캐러셀_저장분은_하루를_버텨도_꺼진_블렌드의_지금_사면_이득을_다시_띄우지_않는다(g80_env, monkeypatch):
    """라이브 사본 실측: 09-27 06:30 에 저장된 오늘의 추천 5장 중 4번째가 2026타경50102_1 kind='now' 다.
    배포 뒤 같은 날 홈은 저장분을 다시 읽는다 — 저장분이 게이트를 우회하면 초록 카드가 하루 더 남는다."""
    db.set_setting("daily_picks_date", TODAY.isoformat())
    db.set_setting("daily_picks_ids", json.dumps([{"id": "QG_1", "kind": "now"}]))
    got = service.get_daily_picks(5)
    assert all(not (p["id"] == "QG_1" and p.get("pick_kind") == "now") for p in got), \
        "꺼진 블렌드로만 성립하는 '지금 사면 이득' 카드가 저장분 경로로 살아남았다"
    # 반대쪽: 게이트가 열려 있으면 같은 저장분이 그대로 뜬다(재검증 경로가 카드를 다 지우는 게 아니다)
    _policy(monkeypatch, ON)
    got_on = service.get_daily_picks(5)
    assert [(p["id"], p.get("pick_kind")) for p in got_on] == [("QG_1", "now")]


def test_A5_공개_목록_카드의_입찰_상한은_엔카_단독_값이다(g80_env, monkeypatch):
    """backend 테스트는 상세·리포트만 렌더했다. 목록 카드 '입찰 상한'도 같은 게이트를 따르는지(렌더 기준)."""
    import web.app as A
    v = g80_env
    real_policy = service.kcar_blend_policy
    enc = service.bid_state(dict(v, kcar_median=None, kcar_sample=None), BT)["max_bid"]
    _policy(monkeypatch, ON)
    blended = service.bid_state(v, BT)["max_bid"]
    monkeypatch.setattr(service, "kcar_blend_policy", real_policy)     # 저장소 설정(꺼짐)으로 되돌림
    assert enc and blended and enc != blended, "전제: 블렌드 여부로 입찰 상한이 달라져야 한다"
    c = TestClient(A.app)
    html = c.get("/vehicles", params={"q": "2026타경9101"}, headers=_PUBLIC).text
    assert "2026타경9101" in html, "전제: 목록에 이 물건 카드가 떠야 한다"
    assert f"{enc:,}" in html, "목록 카드에 엔카 단독 입찰 상한이 없다"
    assert f"{blended:,}" not in html, "목록 카드가 꺼진 블렌드의 입찰 상한을 찍었다"
    # 반대쪽: 게이트가 열리면 같은 카드가 블렌드 값을 찍는다(분기가 실제로 카드에 닿는다)
    _policy(monkeypatch, ON)
    html_on = c.get("/vehicles", params={"q": "2026타경9101"}, headers=_PUBLIC).text
    assert f"{blended:,}" in html_on


# ═════════════════════════════════════════════════════════════════════════
# B. 입구 — 매일 경로를 처음부터, 관리자 라우트
# ═════════════════════════════════════════════════════════════════════════
def _daily_vehicle(**kw) -> dict:
    """0표본 재조회 대상(시세 없음·30일 안 기일·14일 전 조회) + **신선한** 케이카 저장값(어제·표본 5).
    설정만 켜져 있으면 나이·표본 게이트는 통과한다 — 막는 것은 설정 하나뿐인 모양."""
    v = {"id": "QD_1", "folder_key": "QD_1", "case_no": "2026타경9201", "item_no": "1",
         "court": "수원지방법원", "maker": "기아", "model": "쏘렌토", "year": 2021, "mileage_km": 30000,
         "appraisal_value": 31_000_000, "min_sale_price": 25_000_000, "fail_count": 1,
         "sale_date": (TODAY + timedelta(days=10)).isoformat(), "status": "완료", "judgment": "유찰 대기",
         "sample_count": 0, "analyzed_at": _ts(14), "collected_at": _ts(14),
         "kcar_median": 36_000_000, "kcar_sample": 5, "kcar_checked_at": _ts(1)}
    v.update(kw)
    return v


def _stub_daily(monkeypatch) -> dict:
    """daily_update 의 외부 단계(법원 수집·법원 세션·엔카 헬스·사진·낙찰결과·검토·출시가)를 가짜로.
    케이카·엔카 재조회 경로(requery_missing_market → recompute_all_market)는 **진짜**로 둔다."""
    c = {"court_session": 0}

    def _court_session():
        c["court_session"] += 1
        return object()
    monkeypatch.setattr(service, "collect_upcoming", lambda **k: 0)
    monkeypatch.setattr(service, "_reconcile_min_from_dxdy", lambda *a, **k: None)
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "ok", "code": 200})
    monkeypatch.setattr(service, "new_session", _court_session)
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect", lambda **k: {"matched": 0, "remaining": 0})
    return c


def _stored_basis(vid):
    v = db.get_vehicle(vid)
    bd = v.get("breakdown")
    bd = json.loads(bd) if isinstance(bd, str) else (bd or {})
    return v, bd.get("기준시세")


def test_B1_매일_경로_전체에서_꺼져_있으면_브라우저_0회_엔카는_그룹수만큼만(tmpdb, monkeypatch):
    n = _browser_meter(monkeypatch)
    e = _encar_meter(monkeypatch, _encar_listings())
    _stub_daily(monkeypatch)
    db.upsert_vehicle(_daily_vehicle())
    out = service.daily_update(within_days=30, analyze=True)
    assert out["requery"] == {"targets": 1, "updated": 1}, f"전제: 재조회 경로를 실제로 탔어야 한다 {out['requery']}"
    assert n == {"new_session": 0, "KcarSession": 0, "sync_playwright": 0}, f"꺼져 있는데 브라우저 입구가 열렸다 {n}"
    assert e["search"] == 1, f"엔카 요청은 재조회 그룹 1개만이어야 한다(케이카 헛요청 없음) — {e}"
    s = db.get_all_settings()
    assert s["kcar_health_state"] == "disabled" and s["kcar_health_msg"] == STOP_PHRASE
    v, basis = _stored_basis("QD_1")
    assert v["median_price"] and basis == v["median_price"], \
        f"저장 산정의 기준시세가 엔카 단독이 아니다({basis} vs {v['median_price']}) — 꺼진 케이카가 섞였다"
    assert (v["kcar_median"], v["kcar_sample"]) == (36_000_000, 5), "저장값은 지우지 않는다(보존)"


def test_B2_반대쪽_켜져_있으면_매일_경로가_브라우저를_1회_시도하고_신선한_저장값을_섞는다(tmpdb, monkeypatch):
    """B1 의 계수기·기준시세 단언이 공허하지 않음을 보인다 — 같은 픽스처가 켜지면 둘 다 뒤집힌다."""
    _config_on(monkeypatch)
    n = _browser_meter(monkeypatch)
    _encar_meter(monkeypatch, _encar_listings())
    _stub_daily(monkeypatch)
    db.upsert_vehicle(_daily_vehicle())
    service.daily_update(within_days=30, analyze=True)
    assert n["new_session"] == 1, f"켜져 있으면 실행당 1회 시도해야 한다 {n}"
    assert db.get_all_settings()["kcar_health_state"] == "error"
    v, basis = _stored_basis("QD_1")
    eff = service.effective_median(v)
    assert eff != v["median_price"] and basis == eff, "켜짐·어제·표본 5 인데 섞이지 않았다 — 재개 경로가 죽었다"


def test_B3_켜도_22일_된_저장값은_매일_경로에서_섞이지_않는다(tmpdb, monkeypatch):
    _config_on(monkeypatch)
    _browser_meter(monkeypatch)
    _encar_meter(monkeypatch, _encar_listings())
    _stub_daily(monkeypatch)
    db.upsert_vehicle(_daily_vehicle(kcar_checked_at=_ts(22)))
    service.daily_update(within_days=30, analyze=True)
    v, basis = _stored_basis("QD_1")
    assert basis == v["median_price"], "나이 게이트가 매일 경로에서 빠졌다"


class _SyncThread:
    """start_* 가 띄우는 데몬 스레드를 **그 자리에서** 돌린다 — 끝난 뒤 계수기를 읽기 위해서."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._t, self._a, self._k = target, args, kwargs or {}

    def start(self):
        self._t(*self._a, **self._k)


def _admin_client():
    import web.app as A
    return TestClient(A.app)


def test_B4_전체_재교정_라우트는_꺼져_있으면_브라우저_0회_실행기록에_케이카가_없다(tmpdb, monkeypatch):
    n = _browser_meter(monkeypatch)
    e = _encar_meter(monkeypatch, _encar_listings())
    import types
    monkeypatch.setattr(service, "threading", types.SimpleNamespace(Thread=_SyncThread, Lock=threading.Lock))
    db.upsert_vehicle(_daily_vehicle(median_price=30_000_000, sample_count=12, photo_count=3))
    r = _admin_client().post("/recompute-all", headers=_TUNNEL, follow_redirects=False)
    assert r.status_code == 303
    assert n == {"new_session": 0, "KcarSession": 0, "sync_playwright": 0}, n
    assert e["search"] == 1, "전제: 재교정이 실제로 엔카 1그룹을 돌았어야 한다"
    run = db.latest_run()
    assert run["status"] == "done" and "케이카" not in (run["message"] or ""), run["message"]
    assert db.get_all_settings()["kcar_health_state"] == "disabled"
    # 반대쪽: 켜면 같은 라우트가 1회 시도하고 실행 기록에 케이카 조회 수를 적는다
    _config_on(monkeypatch)
    _admin_client().post("/recompute-all", headers=_TUNNEL, follow_redirects=False)
    assert n["new_session"] == 1 and "케이카 0회 조회" in (db.latest_run()["message"] or "")


def test_B5_관리자_다시분석_라우트는_꺼져_있으면_케이카_교차검증을_부르지_않는다(tmpdb, monkeypatch):
    n = _browser_meter(monkeypatch)
    _encar_meter(monkeypatch, _encar_listings())
    calls = {"crosscheck": 0}

    def _cc(vid, config=None):
        calls["crosscheck"] += 1
        return {"ok": False, "msg": "[qa] 가짜"}
    monkeypatch.setattr(service, "kcar_crosscheck", _cc)
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    v = _daily_vehicle(median_price=30_000_000, sample_count=12, doc_id="B000210" + "20260130009201" + "1")

    def _analyze_item(cs, es, raw, item, config, repair_cost):
        return dict(v, status="완료", analyzed_at=_ts(0))
    monkeypatch.setattr(service, "_analyze_item", _analyze_item)
    db.upsert_vehicle(v)
    r = _admin_client().post("/vehicle/QD_1/analyze", headers=_TUNNEL, follow_redirects=False)
    assert r.status_code == 303
    assert calls["crosscheck"] == 0 and n["sync_playwright"] == 0 and n["new_session"] == 0
    # 반대쪽: 켜면 분석 직후 교차검증을 1회 부른다
    _config_on(monkeypatch)
    _admin_client().post("/vehicle/QD_1/analyze", headers=_TUNNEL, follow_redirects=False)
    assert calls["crosscheck"] == 1


# ═════════════════════════════════════════════════════════════════════════
# C. 감시 — 사내 대시보드 표시층
# ═════════════════════════════════════════════════════════════════════════
def _load_dashboard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("agent_dashboard_k1qa", _ROOT / "tools" / "agent_dashboard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_C1_사내_대시보드는_중지_의도를_초록으로_두고_경보로_올리지_않는다():
    from datetime import datetime
    from web import ops_health as oh
    D = _load_dashboard()
    now = datetime.combine(TODAY, datetime.min.time()).replace(hour=12)
    snap = {"kcar_checked_at": "2026-09-05 23:10:39", "kcar_state": "disabled",
            "kcar_enabled": False, "kcar_blend_max_age_days": 7, "kcar_blend_min_sample": 5}
    verdict = oh.evaluate(snap, oh.load_thresholds(), now=now)
    verdict.update(stale=False, age_hours=0.1)
    state, why, shown = D.supply_display(verdict, None)
    k = next(s for s in shown["signals"] if s["key"] == "kcar")
    assert k["state"] == "ok" and k["head"] == "중지(의도)" and k["detail"].startswith(STOP_PHRASE)
    assert "케이카" not in why, f"중지(의도)가 공급 머리줄에 이상으로 올라왔다: {why}"
    # 반대쪽: 설정이 켜진 채 22일 멈춰 있으면 같은 표시층이 경보로 올린다(표시층이 kcar 를 통째로 빼는 게 아니다)
    bad = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39", "kcar_state": "error",
                       "kcar_msg": "chrome", "kcar_enabled": True}, oh.load_thresholds(), now=now)
    bad.update(stale=False, age_hours=0.1)
    _, why_bad, shown_bad = D.supply_display(bad, None)
    assert next(s for s in shown_bad["signals"] if s["key"] == "kcar")["state"] == "warn"
    assert "케이카" in why_bad


# ═════════════════════════════════════════════════════════════════════════
# D. 되돌리기 — 재개 경로가 살아 있는가
# ═════════════════════════════════════════════════════════════════════════
class _FakeKcarSession:
    def __init__(self, listings):
        self.listings, self.calls = listings, 0

    def search(self, kw, year=None, hybrid=False, limit=None):
        self.calls += 1
        return {"results": list(self.listings), "reached": True}

    def close(self):
        pass


def test_D1_켜고_새로_받은_값이면_관리자_교차검증이_시각을_쓰고_공개_숫자에_다시_섞인다(tmpdb, monkeypatch):
    """설정 true + 오늘 조회 + 표본 ≥5 → 저장 → 공개 상세의 '2차 소스'와 입찰 상한이 되살아난다."""
    import web.app as A
    _config_on(monkeypatch)
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    _encar_meter(monkeypatch, _encar_listings())
    ks = _FakeKcarSession(_encar_listings(n=8, price=33_000_000, platform="kcar"))
    monkeypatch.setattr(kcar, "new_session", lambda: ks)
    monkeypatch.setattr(kcar, "search", lambda s, kw, **k: s.search(kw, **k))
    monkeypatch.setattr(kcar, "normalize", lambda rows: list(rows))
    db.upsert_vehicle(_daily_vehicle(median_price=30_000_000, sample_count=12,
                                     kcar_median=None, kcar_sample=None, kcar_checked_at=None))
    r = service.kcar_crosscheck("QD_1")
    assert r.get("ok") is True and ks.calls == 1, r
    v = db.get_vehicle("QD_1")
    assert str(v["kcar_checked_at"])[:10] == TODAY.isoformat() and v["kcar_sample"] >= 5
    eff = service.effective_median(v)
    assert eff != v["median_price"], "켜짐·오늘·표본 ≥5 인데 다시 섞이지 않는다 — 재개 경로가 죽었다"
    page = TestClient(A.app).get("/vehicle/QD_1", headers=_PUBLIC).text
    assert f"2차 소스 {v['kcar_sample']}건" in page
    # 그리고 8일이 지나면 같은 값이 저절로 빠진다(재개해도 낡은 값은 다시 퇴역)
    db.update_fields("QD_1", kcar_checked_at=_ts(8))
    assert service.effective_median(db.get_vehicle("QD_1")) == v["median_price"]


def test_D2_켜고_라이브로_받으면_재교정이_시각을_쓰고_산정에_섞는다(tmpdb, monkeypatch):
    """매일·재교정 경로의 재개: `_kcar_cross_live` 가 새 값과 함께 kcar_checked_at 을 돌려줘야
    나이 게이트가 새 값을 낡은 값으로 오판하지 않는다(backend 수정 #4)."""
    _config_on(monkeypatch)
    _encar_meter(monkeypatch, _encar_listings())
    ks = _FakeKcarSession(_encar_listings(n=8, price=33_000_000, platform="kcar"))
    monkeypatch.setattr(kcar, "new_session", lambda: ks)
    monkeypatch.setattr(kcar, "normalize", lambda rows: list(rows))
    db.upsert_vehicle(_daily_vehicle(median_price=30_000_000, sample_count=12, photo_count=3,
                                     kcar_median=None, kcar_sample=None, kcar_checked_at=None))
    service.recompute_all_market(finalize=False)
    assert ks.calls == 1
    v, basis = _stored_basis("QD_1")
    assert str(v["kcar_checked_at"] or "")[:10] == TODAY.isoformat(), "라이브로 받은 값에 조회 시각이 없다"
    assert v["kcar_sample"] >= 5 and basis == service.effective_median(v) != v["median_price"]
