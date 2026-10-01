# -*- coding: utf-8 -*-
"""REC-8 ⑵(지시서 2026-10-01-03) — 수집 실행 중 `/run/status` 가 저장 판정 문자열 수로 홈 KPI 를 덮지 않는다.

예전 응답의 ok·wait·hold 는 db.counts_by_judgment(저장 judgment 문자열 수)였고, base.html 폴링이 실행 중 2초마다
홈 KPI '지금 입찰 추천'(#kpi-ok)·'유찰 대기'(#kpi-wait)를 그 값으로 덮었다 — 09-29 백업 사본 09:00 기준 3 → 4 · 725 → 576.
'곧 열리는 경매 30일'(#kpi-upcoming)도 숨김 물건까지 센 다른 정의(upcoming_count)로 417 → 491 이 됐다.
실행 중에는 공개 사용자에게도 응답한다(running 이면 공개 응답 제한이 풀린다).

처방: 응답에서 ok·wait·hold 를 뺀다(관리자 화면도 읽지 않는다). 실행이 끝나면 base.html 이 홈을 새로고침해 바른 수를
그린다. upcoming 은 홈과 같은 정의(lifecycle_partition 의 upcoming30 = hide_incomplete 목록 건수)의 COUNT 로 센다.
폴링마다 칸 판정(lifecycle_partition·bid_state)을 돌리지 않는다 — 부하가 늘면 안 된다.

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.test_rec1_r3_picks_gate_block import _d, _ge300, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from web import db, service

ROOT = Path(__file__).resolve().parents[1]
_PUB = {"x-forwarded-for": "203.0.113.7"}   # XFF 가 없으면 관리자(SSH 터널)로 본다
PUBLIC_KEYS = {"running", "run", "upcoming", "pending"}


@pytest.fixture
def cars(mk):
    """저장 판정 문자열 수와 칸 수가 **다르게** 나오는 모수 — 덮어쓰기가 틀린 수를 내던 모양 그대로."""
    base = dict(appraisal_value=30_000_000, min_sale_price=10_000_000, median_price=30_000_000, fail_count=1)
    mk("RSL", judgment="입찰 검토 가능", upper_bid=19_000_000, sale_date=_d(5), **base)       # 칸 review
    _ge300(mk)                                                                                  # 저장 '입찰 검토 가능' · 칸 wait
    mk("STOP", judgment="입찰 검토 가능", upper_bid=19_000_000, runnable="no", sale_date=_d(6), **base)
    mk("W1", judgment="유찰 대기", sale_date=_d(10), **dict(base, min_sale_price=29_000_000))
    mk("W2", judgment="유찰 대기", sale_date=_d(-20), **dict(base, min_sale_price=29_000_000))   # 지난 기일 — 저장 '유찰 대기'
    mk("HOLD", judgment="입찰 보류", accident_grade="flood", sale_date=_d(12), **base)
    # 숨김 물건(시세 없음 + 사진 없음) — upcoming_count 는 세고 홈(hide_incomplete)은 안 센다
    mk("HID1", judgment="유찰 대기", sale_date=_d(3), median_price=None, photo_count=0)
    mk("HID2", judgment="유찰 대기", sale_date=_d(20), median_price=None, photo_count=0)
    mk("DUPX", judgment="유찰 대기", sale_date=_d(4), case_no="(중복)2026타경DUPX", **base)     # 사건번호 형식 밖 — 숨김
    mk("FAR", judgment="유찰 대기", sale_date=_d(45), **base)                                  # 30일 창 밖
    db.create_run(5)          # 진행 표시(d.run)가 읽을 실행 기록 — 하트비트가 없어 '실행 중'은 is_running 으로만 켠다


@pytest.fixture
def client(monkeypatch):
    import web.app as A
    return TestClient(A.app)


def _running(monkeypatch):
    monkeypatch.setattr(service, "is_running", lambda: True)


def test_전제_저장_문자열_수와_홈_칸_수가_다르다(cars):
    counts = db.counts_by_judgment()
    lc = service.lifecycle_partition()
    assert counts["입찰 검토 가능"] == 3 and lc["review"] == 1, (counts, lc)   # 옛 #kpi-ok 는 3, 홈은 1
    assert counts["유찰 대기"] != lc["wait"], (counts, lc)
    assert db.upcoming_count(30) != lc["upcoming30"], "숨김 물건 때문에 옛 upcoming 정의가 홈과 달라야 재현이다"


def test_실행_중_공개_응답에_저장_문자열_수가_없다(cars, client, monkeypatch):
    _running(monkeypatch)
    d = client.get("/run/status", headers=_PUB).json()
    assert d["running"] is True
    assert set(d) == PUBLIC_KEYS, f"공개 응답은 화면이 쓰는 것만 — {sorted(d)}"
    for leaked in ("ok", "wait", "hold", "total"):
        assert leaked not in d, leaked


def test_관리자에게도_판정_문자열_수를_주지_않는다(cars, client, monkeypatch):
    _running(monkeypatch)
    d = client.get("http://localhost/run/status").json()     # XFF 없음 + 루프백 = 관리자(SSH 터널 직결)
    assert set(d) == PUBLIC_KEYS | {"total"}, sorted(d)
    assert d["total"] == db.total_vehicles()
    monkeypatch.setattr(service, "is_running", lambda: False)
    idle = client.get("http://localhost/run/status").json()
    assert idle["running"] is False and not {"ok", "wait", "hold"} & set(idle), sorted(idle)


def test_곧_열리는_경매는_홈과_같은_정의다(cars, client, monkeypatch):
    _running(monkeypatch)
    d = client.get("/run/status", headers=_PUB).json()
    lc = service.lifecycle_partition()
    assert d["upcoming"] == lc["upcoming30"] == len(db.list_vehicles(upcoming_days=30, hide_incomplete=True))
    assert d["pending"] == db.pending_count(), "홈 '분석 대기'(dashboard 의 pending)와 같은 함수"


def test_유휴_공개_응답은_그대로_최소다(cars, client):
    assert client.get("/run/status", headers=_PUB).json() == {"running": False}


def test_폴링은_판정을_계산하지_않는다(cars, client, monkeypatch):
    """폴링은 실행 중 2초마다 온다 — 칸 판정(전 행)·저장 문자열 집계를 부르면 부하가 는다."""
    _running(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("/run/status 가 판정·전 행 적재를 불렀다")
    for mod, name in ((service, "lifecycle_partition"), (service, "bid_state"), (service, "_bucket_and_tier"),
                      (service, "backtest_stats"), (db, "counts_by_judgment"), (db, "list_vehicles")):
        monkeypatch.setattr(mod, name, boom)
    for url, h in (("/run/status", _PUB), ("http://localhost/run/status", {})):
        r = client.get(url, headers=h)
        assert r.status_code == 200 and "upcoming" in r.json()
    monkeypatch.setattr(service, "is_running", lambda: False)
    assert client.get("/run/status", headers=_PUB).json() == {"running": False}


def test_count_vehicles_는_list_vehicles_와_같은_필터다(cars):
    for kw in ({}, {"upcoming_days": 30, "hide_incomplete": True}, {"hide_incomplete": True},
               {"judgment": "유찰 대기"}, {"judgment": "입찰 검토 가능", "hide_incomplete": True},
               {"upcoming_days": 7}, {"maker": "현대", "hide_incomplete": True}):
        assert db.count_vehicles(**kw) == len(db.list_vehicles(**kw)), kw


def test_옛_폴링_코드가_빈_키를_받아도_KPI_를_덮지_않는다():
    """frontend 가 base.html 의 덮어쓰기 줄을 지우기 전에 이 응답이 배포돼도 홈 KPI 는 그대로여야 한다 —
    base.html 의 setTxt 는 값이 null·undefined 면 쓰지 않는다(fmt(undefined) 는 undefined). 이 가드가 사라지면
    빈 키가 'undefined' 글자로 KPI 를 덮는다."""
    html = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    m = re.search(r"const setTxt = \(id,v\) => \{([^}]*)\};", html)
    assert m, "base.html 폴링의 setTxt 정의를 찾지 못했다"
    assert re.search(r"v\s*!=\s*null", m.group(1)), f"setTxt 에 null 가드가 없다: {m.group(1)}"
    assert re.search(r"const fmt = n => \(typeof n==='number'\) \? n\.toLocaleString\('ko-KR'\) : n;", html)


def _calls(fn) -> set:
    """함수 본문이 **실제로 부르는** 이름(주석·문자열 속 낱말은 세지 않는다)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return out


def test_구조_판정_문자열_집계는_화면_경로에서_쓰지_않는다():
    import web.app as A
    for fn in (A.run_status, A.dashboard):
        assert "counts_by_judgment" not in _calls(fn), fn.__name__
    # web/ 전체에서 부르는 곳이 없다 — db 독스트링('어떤 화면·응답도 쓰지 않는다')이 거짓이 되지 않게
    for f in ("app.py", "service.py"):
        tree = ast.parse((ROOT / "web" / f).read_text(encoding="utf-8"))
        called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert "counts_by_judgment" not in called, f
    assert "count_vehicles(upcoming_days=30, hide_incomplete=True)" in inspect.getsource(A.run_status)
    # 홈과 같은 정의 — lifecycle_partition 의 upcoming30 필터가 바뀌면 이 줄도 같이 바뀌어야 한다
    assert "db.list_vehicles(upcoming_days=30, hide_incomplete=True)" in inspect.getsource(service.lifecycle_partition)


def test_홈_컨텍스트에_저장_문자열_집계를_넘기지_않는다(cars, monkeypatch):
    import web.app as A
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append((name, ctx))
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    r = TestClient(A.app).get("/", headers=_PUB)
    assert r.status_code == 200
    name, ctx = cap[-1]
    assert name == "dashboard.html" and "counts" not in ctx, "어느 템플릿도 읽지 않던 저장 문자열 집계는 넘기지 않는다"
    assert ctx["lifecycle"]["review"] == 1
