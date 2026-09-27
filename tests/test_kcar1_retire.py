# -*- coding: utf-8 -*-
"""KCAR-1 — 케이카 중지 · 낡은 값 퇴역 (2026-09-27, 지시 2026-09-27-33).

왜 이 파일이 있나 (qa 재현 reports/2026-09-27-kcar-qa.md):
  · 공개 입찰예정 383건 중 **23건**이 09-05(22일 전)에 받은 케이카 값 — 표본 2~3건 — 을 25~33% 비중으로
    가격에 섞고 있었다. 그 때문에 공개 '입찰 상한' 21건 · 판정 3건(초록 '지금 사면 이득' 1건 포함)이 움직였다.
  · 23쌍 중 19쌍은 앱 자신의 교차검증(tol 10%)으로 보면 '불일치' — 표본이 5건 이상이었다면 경고했을 값이다.
  · `kcar_cross_enabled: false` 만으로는 공개 숫자에서 빠지지 않았다 — `_blend_ok` 가 설정을 안 읽었다.
  · 매일 06:32 에 브라우저 기동을 시도해 실패했고, 실패할 때마다 드라이버가 남았다.

그래서 여기서 재는 것:
  ① 게이트 세 조건(꺼짐·나이·표본) 각각과 경계(정확히 7일 · 표본 5건)
  ② 게이트에 걸리면 effective_median = 엔카 단독, 공개 '2차 소스' 문구·관리자 '산정 반영 시세' 행이 사라짐
  ③ 저장값 재적용(_reapply_stored)이 낡은 값으로 신뢰도 상한 88→96 을 열지 못함
  ④ 꺼져 있으면 브라우저를 띄우지 않고(KcarSession 미생성) 엔카 헛요청도 없음 · 'disabled' 기록
  ⑤ launch 실패 시 드라이버 stop
  ⑥ 감시 신호 ④ '중지(의도)' 문구·판정 · 일일 리포트
  ⑦ 반증 — 게이트 한 줄을 지운 변이체에서 위 단언들이 **빨간불**이 되는가
각 단언은 **반대쪽**(게이트를 통과하는 조건에서는 섞인다)도 함께 민다 — 한쪽만 있으면 공허하다.
외부 요청은 0 이다 — 엔카·케이카·Playwright 는 전부 가짜로 바꾼다.
"""
from datetime import date, datetime, timedelta
import importlib.util
import inspect
import textwrap
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import ops_health as oh
from web import service
from src.collect import kcar
from src.parse.market_match import summarize

_ROOT = Path(__file__).resolve().parents[1]
ON = {"enabled": True, "max_age_days": 7, "min_sample": 5}
OFF = {"enabled": False, "max_age_days": 7, "min_sample": 5}
STOP_PHRASE = "2026-09-27 오너 결정으로 중지 · 낡은 값은 가격에 섞지 않음(나이 7일·표본 5건 게이트)"


def _ts(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat() + " 23:10:39"


def _car(**kw) -> dict:
    """블렌드 조건을 전부 만족하는 물건(엔카 1,290만 · 케이카 1,500만 · 표본 5 · 오늘 조회)."""
    v = {"median_price": 12_900_000, "kcar_median": 15_000_000, "kcar_sample": 5,
         "kcar_checked_at": _ts(0), "sample_count": 12, "analyzed_at": _ts(0)}
    v.update(kw)
    return v


def _policy(monkeypatch, pol):
    monkeypatch.setattr(service, "kcar_blend_policy", lambda config=None: dict(pol))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """이 파일은 외부 요청 0 이어야 한다(C.4) — 코드가 퇴행해도 **연결 자체를 막는다.**

    2026-09-27 작업 중 실측: 변이체(crosscheck 조기 반환 삭제)에서 라우트 테스트가 엔카 스텁 없이
    `kcar_crosscheck` 를 타서 실제 `encar.search` 까지 내려갔다. 테스트가 빨간불이 되는 것과
    별개로 **요청이 나가면 안 된다.** 그래서 루프백이 아닌 소켓 연결을 여기서 끊는다
    (Windows 의 이벤트 루프는 TestClient 를 띄울 때 127.0.0.1 로 socketpair 를 만든다 — 그건 허용)."""
    import socket
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _is_loopback(addr) -> bool:
        host = addr[0] if isinstance(addr, tuple) and addr else addr
        return str(host) in ("127.0.0.1", "::1", "localhost")

    def _deny(self, addr, *a, **k):
        if _is_loopback(addr):
            return real_connect(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 이 파일은 외부 요청 0 이어야 한다(C.4)")

    def _deny_ex(self, addr, *a, **k):
        if _is_loopback(addr):
            return real_connect_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 이 파일은 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_ex)


# ── ① 설정: config.yaml 이 단일 진실원천 ────────────────────────────────
def test_설정값은_config_에_있고_표본게이트는_교차검증_최소표본보다_작지_않다():
    cfg = service.load_config()
    assert cfg["kcar_cross_enabled"] is False, "KCAR-1: 케이카 중지"
    assert cfg["kcar_blend_max_age_days"] == 7
    assert cfg["kcar_blend_min_sample"] == 5
    # 표본 2~3건을 섞던 문제의 처방 — 교차검증이 판정조차 안 하는 표본으로 가격을 움직이지 않는다
    assert cfg["kcar_blend_min_sample"] >= cfg["min_sample_count"]
    assert service.kcar_blend_policy(cfg) == {"enabled": False, "max_age_days": 7, "min_sample": 5}


def test_정책은_설정을_읽고_못_읽으면_섞지_않는_쪽으로_넘어진다(monkeypatch):
    got = service.kcar_blend_policy({"kcar_cross_enabled": True, "kcar_blend_max_age_days": 3,
                                     "kcar_blend_min_sample": 9})
    assert got == {"enabled": True, "max_age_days": 3, "min_sample": 9}

    def _broken():
        raise OSError("config.yaml 없음")
    monkeypatch.setattr(service, "load_config", _broken)
    assert service.kcar_blend_policy()["enabled"] is False


# ── ② 게이트 세 조건 각각 + 경계 ─────────────────────────────────────
def test_게이트를_모두_통과하면_섞인다(monkeypatch):
    """반대쪽 — 이게 없으면 아래 '안 섞인다' 단언이 전부 공허하다."""
    _policy(monkeypatch, ON)
    v = _car()
    assert service._blend_ok(v) is True
    assert service.effective_median(v) != v["median_price"]
    assert service.market_provenance(v)["cross_n"] == 5


def test_설정이_꺼지면_신선한_값도_섞지_않는다(monkeypatch):
    _policy(monkeypatch, OFF)
    v = _car(kcar_sample=9)
    assert service._blend_ok(v) is False
    assert service.effective_median(v) == v["median_price"]
    assert service.market_provenance(v)["cross_n"] == 0


def test_실제_설정으로도_섞지_않는다():
    """정책을 바꿔치기하지 않고 저장소 config.yaml 그대로 — 배포되면 이 상태다."""
    v = _car(kcar_sample=9)
    assert service.effective_median(v) == v["median_price"]
    assert service.market_provenance(v)["cross_n"] == 0


@pytest.mark.parametrize("age, ok", [(0, True), (6, True), (7, True), (8, False), (22, False)])
def test_나이_게이트_경계는_정확히_7일까지_통과(monkeypatch, age, ok):
    _policy(monkeypatch, ON)
    v = _car(kcar_checked_at=_ts(age))
    assert service._blend_ok(v) is ok, f"{age}일 된 값 → {ok} 여야 한다"
    assert (service.effective_median(v) != v["median_price"]) is ok


@pytest.mark.parametrize("stamp", [None, "", "모름", "2026-13-45 00:00:00"])
def test_조회_시각이_없거나_못_읽으면_섞지_않는다(monkeypatch, stamp):
    _policy(monkeypatch, ON)
    v = _car(kcar_checked_at=stamp)
    assert service._blend_ok(v) is False
    assert service.effective_median(v) == v["median_price"]


@pytest.mark.parametrize("n, ok", [(2, False), (3, False), (4, False), (5, True), (9, True)])
def test_표본_게이트_경계는_5건부터_통과(monkeypatch, n, ok):
    """지금 DB 의 케이카 표본은 최대 3건 — 전부 여기서 걸린다(qa 재현 111행: 1건 47·2건 40·3건 24)."""
    _policy(monkeypatch, ON)
    v = _car(kcar_sample=n)
    assert service._blend_ok(v) is ok
    assert (service.market_provenance(v)["cross_n"] == n) is ok


def test_극단_괴리_게이트는_그대로다(monkeypatch):
    """새 게이트가 기존 조건(0.5~2.0배)을 대신하지 않는다 — 통과해도 2배 넘게 벌어지면 엔카만."""
    _policy(monkeypatch, ON)
    v = _car(kcar_median=40_000_000, kcar_sample=9)
    assert service._blend_ok(v) is False


def test_qa_가_잡은_09_05_값은_설정을_켜도_걸린다(monkeypatch):
    """2026타경10111_1 카니발 모양(엔카 1,290만 · 케이카 1,890만 · 표본 3 · 09-05 조회)을 그대로 넣는다.

    설정을 **켜도** 나이·표본 게이트가 막는다 — '설정만 다시 켜면 22일 된 값이 돌아온다'가 아니다."""
    _policy(monkeypatch, ON)
    v = _car(median_price=12_900_000, kcar_median=18_900_000, kcar_sample=3,
             kcar_checked_at="2026-09-05 23:10:39")
    assert service.effective_median(v) == 12_900_000


# ── ③ 공개 문구 · 관리자 행 ─────────────────────────────────────────
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


def _client(tmp_path, monkeypatch, **kcar_fields):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "k1.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({
        "id": "K1_1", "folder_key": "K1_1", "case_no": "2026타경9", "item_no": "1",
        "court": "수원지방법원", "maker": "기아", "model": "쏘렌토", "year": 2019,
        "min_sale_price": 9000000, "appraisal_value": 11000000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 9670000, "market_confidence": 72, "market_confidence_label": "높음",
        "sample_count": 12, "analyzed_at": _ts(0), **kcar_fields,
    })
    import web.app as A
    return TestClient(A.app)


def test_낡은_값이면_공개_2차소스_문구와_관리자_산정반영_행이_없다(tmp_path, monkeypatch):
    """qa 가 센 23건의 모양(22일 · 표본 3) — 저장소 설정 그대로(꺼짐)."""
    c = _client(tmp_path, monkeypatch, kcar_median=13_000_000, kcar_sample=3,
                kcar_checked_at="2026-09-05 23:10:39")
    for path in ("/vehicle/K1_1", "/vehicle/K1_1/report"):
        r = c.get(path, headers=_PUBLIC)
        assert r.status_code == 200
        assert "2차 소스" not in r.text, f"{path}: 쓰지 않은 표본을 '반영'했다고 적었다"
    admin = c.get("/vehicle/K1_1", headers=_TUNNEL).text
    assert "산정 반영 시세" not in admin, "블렌드가 없는데 관리자 카드가 '예상낙찰가·상한가에 반영'이라 적었다"
    assert "케이카 참고 중앙값" in admin, "저장값은 지우지 않는다 — 관리자에게는 참고로 남는다"


def test_게이트를_통과하면_두_문구가_실제로_나온다(tmp_path, monkeypatch):
    """반대쪽 — 위 테스트가 템플릿 분기를 못 타서 통과한 것이 아님을 확인한다."""
    _policy(monkeypatch, ON)
    c = _client(tmp_path, monkeypatch, kcar_median=13_000_000, kcar_sample=9,
                kcar_checked_at=_ts(1))
    assert "2차 소스 9건" in c.get("/vehicle/K1_1", headers=_PUBLIC).text
    assert "2차 소스 9건" in c.get("/vehicle/K1_1/report", headers=_PUBLIC).text
    assert "산정 반영 시세" in c.get("/vehicle/K1_1", headers=_TUNNEL).text


def test_게이트_후에는_입찰상한이_엔카_단독과_같다(monkeypatch):
    """공개 '입찰 상한'은 저장값 upper_bid 가 아니라 bid_state().max_bid 다(qa §요약 1)."""
    base = _car(median_price=9_670_000, kcar_median=13_000_000, kcar_sample=3,
                kcar_checked_at="2026-09-05 23:10:39", min_sale_price=9_000_000,
                appraisal_value=11_000_000, fail_count=1, sale_date="2999-01-01",
                maker="기아", model="쏘렌토", year=2019, market_confidence=72,
                market_confidence_label="높음")
    enc_only = dict(base, kcar_median=None, kcar_sample=None)
    assert service.bid_state(base, BT)["max_bid"] == service.bid_state(enc_only, BT)["max_bid"]
    # 반대쪽: 신선·표본 충분·켜짐이면 입찰 상한이 실제로 달라진다(같은 픽스처가 분기를 탄다)
    _policy(monkeypatch, ON)
    fresh = dict(base, kcar_sample=9, kcar_checked_at=_ts(0))
    assert service.bid_state(fresh, BT)["max_bid"] != service.bid_state(enc_only, BT)["max_bid"]


# ── ④ 저장값 재적용이 낡은 값으로 신뢰도 상한을 열지 않는다 ───────────────
def _encar_listings(n=20, price=30_000_000):
    return [{"platform": "encar", "form_year": 2021, "mileage_km": 28000 + i * 100,
             "price_won": price + i * 50_000, "model": "쏘렌토",
             "badge": None, "fuel": None, "id": f"e{i}"} for i in range(n)]


def _reapply(cfg, checked_at, sample=12):
    listings = _encar_listings()
    stats = summarize(listings, form_year=2021, mileage_km=30000, platform="encar",
                      appraisal_value=31_000_000, config=cfg)
    assert stats.confidence == 88, "전제: 단일소스 상한 88 에 닿아 있어야 '상한이 열렸나'를 잴 수 있다"
    v = {"model": "기아 쏘렌토", "year": 2021, "mileage_km": 30000, "appraisal_value": 31_000_000,
         "kcar_median": 30_400_000, "kcar_sample": sample, "kcar_checked_at": checked_at}
    return service._kcar_cross_live(None, {}, {"n": 0, "cap": 200}, v, None, listings,
                                    stats, 2021, cfg)


_CFG_ON = {"min_sample_count": 5, "cross_source_tol": 0.10, "kcar_cross_enabled": True,
           "kcar_blend_max_age_days": 7, "kcar_blend_min_sample": 5}


def test_낡은_agree_는_신뢰도_상한을_열지_못한다():
    st, kf, blk = _reapply(_CFG_ON, "2026-09-05 23:10:39")
    assert blk is False and kf == {}, "낡은 값은 돌려주지 않는다(= DB 저장값은 보존, 덮지 않음)"
    assert st.confidence <= 88


def test_설정이_꺼지면_신선한_agree_도_상한을_열지_못한다():
    st, kf, _ = _reapply(dict(_CFG_ON, kcar_cross_enabled=False), _ts(0))
    assert kf == {} and st.confidence <= 88


def test_신선한_agree_는_상한을_연다():
    """반대쪽 — 재적용 경로 자체가 살아 있어야 위 두 테스트가 의미가 있다."""
    st, kf, _ = _reapply(_CFG_ON, _ts(2))
    assert kf.get("cross_source_status") == "agree"
    assert st.confidence > 88
    assert "kcar_checked_at" not in kf, "재적용은 조회가 아니다 — 시각을 새로 쓰면 나이 게이트가 속는다"


class _FakeKS:
    def __init__(self):
        self.calls = 0

    def search(self, kw, year=None, hybrid=False):
        self.calls += 1
        return {"results": [], "reached": True}


def test_설정이_꺼지면_세션이_넘어와도_라이브_조회를_하지_않는다():
    cfg = {"min_sample_count": 5, "cross_source_tol": 0.10, "kcar_cross_enabled": False}
    ks = _FakeKS()
    listings = _encar_listings()
    stats = summarize(listings, form_year=2021, mileage_km=30000, platform="encar", config=cfg)
    v = {"model": "기아 쏘렌토", "year": 2021, "mileage_km": 30000}
    service._kcar_cross_live(ks, {}, {"n": 0, "cap": 200}, v, None, listings, stats, 2021, cfg)
    assert ks.calls == 0
    # 반대쪽: 켜면 조회한다
    service._kcar_cross_live(ks, {}, {"n": 0, "cap": 200}, v, None, listings, stats, 2021,
                             dict(cfg, kcar_cross_enabled=True))
    assert ks.calls == 1


# ── ⑤ 꺼져 있으면 브라우저도 엔카 헛요청도 없다 ─────────────────────────
@pytest.fixture
def svc(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "k1svc.db")
    db.init_db()
    return service


def _no_browser(monkeypatch) -> dict:
    """KcarSession 이 만들어지면 즉시 실패 + 횟수 기록(호출자가 예외를 삼켜도 횟수로 잡힌다)."""
    n = {"session": 0}

    def _boom(*a, **k):
        n["session"] += 1
        raise AssertionError("KcarSession 이 생성됐다 — 꺼져 있으면 브라우저를 띄우면 안 된다")
    monkeypatch.setattr(kcar, "new_session", _boom)
    monkeypatch.setattr(kcar, "KcarSession", _boom)
    return n


def test_매일_경로는_꺼져_있으면_브라우저를_띄우지_않고_disabled_를_남긴다(svc, monkeypatch):
    from web import db
    n = _no_browser(monkeypatch)
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1", "maker": "현대",
                       "model": "그랜저", "year": 2020, "mileage_km": 50000})
    monkeypatch.setattr(svc.encar, "new_session", lambda: object())
    monkeypatch.setattr(svc.encar, "search", lambda *a, **k: {"count": 0, "results": []})
    svc.recompute_all_market(finalize=False)            # 저장소 config.yaml(꺼짐) 그대로
    assert n["session"] == 0
    s = db.get_all_settings()
    assert s["kcar_health_state"] == "disabled"
    assert s["kcar_health_msg"] == STOP_PHRASE


def test_매일_경로는_켜져_있으면_세션을_시도한다(svc, monkeypatch):
    """반대쪽 — 위 테스트의 가짜가 실제로 호출될 수 있는 자리에 있는지."""
    from web import db
    n = _no_browser(monkeypatch)
    real = service.load_config()
    monkeypatch.setattr(svc, "load_config", lambda *a, **k: dict(real, kcar_cross_enabled=True))
    monkeypatch.setattr(svc.encar, "new_session", lambda: object())
    monkeypatch.setattr(svc.encar, "search", lambda *a, **k: {"count": 0, "results": []})
    svc.recompute_all_market(finalize=False)
    assert n["session"] == 1
    assert db.get_all_settings()["kcar_health_state"] == "error"


def test_관리자_교차검증은_설정을_엔카보다_먼저_본다(svc, monkeypatch):
    from web import db
    n = _no_browser(monkeypatch)
    e = {"session": 0, "search": 0}

    def _enc_session():
        e["session"] += 1
        return object()

    def _enc_search(*a, **k):
        e["search"] += 1
        return {"count": 0, "results": []}
    monkeypatch.setattr(svc.encar, "new_session", _enc_session)
    monkeypatch.setattr(svc.encar, "search", _enc_search)
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1", "maker": "기아", "model": "쏘렌토",
                       "year": 2019, "mileage_km": 50000, "median_price": 12_000_000})
    r = svc.kcar_crosscheck("v1")
    assert r["ok"] is False and r.get("disabled") is True
    assert STOP_PHRASE in r["msg"]
    assert e == {"session": 0, "search": 0}, "꺼져 있는데 엔카를 헛조회했다"
    assert n["session"] == 0
    assert db.get_all_settings()["kcar_health_state"] == "disabled"
    # 반대쪽: 켜져 있으면 예전 순서(엔카 → 케이카)로 간다 — 가짜 세션이 거기서 터진다
    real = service.load_config()
    with pytest.raises(AssertionError, match="KcarSession"):
        svc.kcar_crosscheck("v1", dict(real, kcar_cross_enabled=True))
    assert e["search"] == 1 and n["session"] == 1


def test_관리자_교차검증_라우트는_중지_사유를_배너로_돌려준다(tmp_path, monkeypatch):
    from urllib.parse import unquote
    n = _no_browser(monkeypatch)
    e = {"search": 0}

    def _enc_search(*a, **k):
        e["search"] += 1
        return {"count": 0, "results": []}
    monkeypatch.setattr(service.encar, "new_session", lambda: object())
    monkeypatch.setattr(service.encar, "search", _enc_search)
    c = _client(tmp_path, monkeypatch)
    r = c.post("/vehicle/K1_1/crosscheck", headers=_TUNNEL, follow_redirects=False)
    assert r.status_code == 303
    assert STOP_PHRASE in unquote(r.headers["location"])
    assert n["session"] == 0 and e["search"] == 0


# ── ⑥ launch 가 실패해도 드라이버를 남기지 않는다 ───────────────────────
class _FakePW:
    def __init__(self, fail_at):
        self.fail_at, self.stopped, self.browser_closed = fail_at, 0, 0
        pw = self

        class _Browser:
            def new_page(self, **k):
                if pw.fail_at == "new_page":
                    raise RuntimeError("new_page 실패")
                return object()

            def close(self):
                pw.browser_closed += 1

        class _Chromium:
            def launch(self, **k):
                if pw.fail_at == "launch":
                    raise RuntimeError("Chromium distribution 'chrome' is not found")
                return _Browser()
        self.chromium = _Chromium()

    def stop(self):
        self.stopped += 1


def _fake_playwright(monkeypatch, fail_at):
    pw = _FakePW(fail_at)

    class _Starter:
        def start(self):
            return pw
    import playwright.sync_api as psa
    monkeypatch.setattr(psa, "sync_playwright", lambda: _Starter())
    return pw


@pytest.mark.parametrize("fail_at, closed", [("launch", 0), ("new_page", 1)])
def test_기동_실패면_드라이버를_멈추고_원래_예외를_올린다(monkeypatch, fail_at, closed):
    pw = _fake_playwright(monkeypatch, fail_at)
    with pytest.raises(RuntimeError, match="chrome|new_page"):
        kcar.KcarSession()
    assert pw.stopped == 1, "launch 실패 뒤 _pw.stop() 이 불리지 않았다(드라이버 누수)"
    assert pw.browser_closed == closed


def test_정상_기동이면_드라이버를_멈추지_않는다(monkeypatch):
    pw = _fake_playwright(monkeypatch, None)
    s = kcar.KcarSession()
    assert pw.stopped == 0
    s.close()
    assert pw.stopped == 1 and pw.browser_closed == 1


# ── ⑦ 감시 신호 ④ '중지(의도)' ─────────────────────────────────────
TH = oh.load_thresholds()
NOON = datetime(2026, 9, 27, 12, 0, 0)


def _k(res):
    return next(s for s in res["signals"] if s["key"] == "kcar")


def test_문구는_서비스와_감시가_같은_문장을_쓴다():
    assert oh.kcar_stop_note(7, 5) == STOP_PHRASE
    assert service.kcar_disabled_msg() == STOP_PHRASE          # 게이트 숫자는 config 에서 읽는다
    assert "게이트" in oh.kcar_stop_note() and "7일" not in oh.kcar_stop_note()   # 모르면 숫자 생략


def test_disabled_상태는_이상이_아니라_중지_의도다():
    res = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39", "kcar_state": "disabled",
                       "kcar_blend_max_age_days": 7, "kcar_blend_min_sample": 5}, TH, now=NOON)
    k = _k(res)
    assert k["state"] == "ok" and k["head"] == "중지(의도)" and k.get("paused") is True
    assert k["detail"].startswith(STOP_PHRASE)
    assert "마지막 교차검증 2026-09-05" in k["detail"]
    assert all(a["key"] != "kcar" for a in res["alerts"]), "끈 것을 경보로 올렸다"


def test_설정이_꺼졌는데_마지막_기록이_error_면_사실로_덧붙이되_울리지_않는다():
    res = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39", "kcar_state": "error",
                       "kcar_msg": "Chromium distribution 'chrome' is not found",
                       "kcar_state_at": "2026-09-27 06:32:54", "kcar_enabled": False},
                      TH, now=NOON)
    k = _k(res)
    assert k["state"] == "ok" and k["head"] == "중지(의도)"
    assert "설정 반영 전 기록" in k["detail"] and "마지막 시도 error" in k["detail"]


def test_설정을_모르면_예전_판정_그대로다():
    """반대쪽 — kcar_enabled 가 없는 스냅샷(구버전 서버)은 22일 정지를 여전히 '이상'으로 잡는다."""
    res = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39", "kcar_state": "error",
                       "kcar_msg": "chrome"}, TH, now=NOON)
    assert _k(res)["state"] == "warn"
    res2 = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39", "kcar_enabled": True},
                       TH, now=NOON)
    assert _k(res2)["state"] == "warn"


def test_앱의_공급판정도_중지_의도로_읽는다(svc, monkeypatch):
    """스냅샷 → 판정 끝까지. 앱은 자기 config 를 싣는다(꺼짐)."""
    from web import db
    _no_browser(monkeypatch)
    monkeypatch.setattr(svc.encar, "new_session", lambda: object())
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1",
                       "kcar_checked_at": "2026-09-05 23:10:39"})
    svc.recompute_all_market(finalize=False)
    snap = svc.supply_snapshot()
    assert snap["kcar_enabled"] is False
    k = _k(svc.supply_health(now=NOON))
    assert k["state"] == "ok" and k["detail"].startswith(STOP_PHRASE)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_일일_리포트는_운영_서버_설정을_읽어_같은_문구를_쓴다():
    R = _load(_ROOT / "tools" / "daily_ops_report.py", "daily_ops_report_k1")
    since, until = R.report_window(date(2026, 9, 27))
    script = R.remote_script(since, until)
    compile(script, "remote", "exec")                 # 서버에서 돌 스크립트가 문법상 깨지지 않는다
    assert "kcar_cross_enabled" in script and 'out["kcar_config"]' in script
    data = {"since": since, "until": until, "generated": NOON,
            "server": {"runs": [], "settings": {"kcar_health_state": "error",
                                                "kcar_health_msg": "chrome",
                                                "kcar_health_at": "2026-09-27 06:32:54"},
                       "supply": {"kcar_checked_at": "2026-09-05 23:10:39"},
                       "kcar_config": {"kcar_enabled": False, "kcar_blend_max_age_days": 7,
                                       "kcar_blend_min_sample": 5}}}
    k = _k(R.supply_verdict(data, NOON))
    assert k["state"] == "ok" and k["detail"].startswith(STOP_PHRASE)
    md = "\n".join(R.supply_block(R.supply_verdict(data, NOON), True))
    assert "중지(의도)" in md and STOP_PHRASE in md
    # 반대쪽: 서버 설정을 못 읽었으면(빈 값) 예전처럼 이상으로 남는다
    data["server"]["kcar_config"] = {}
    assert _k(R.supply_verdict(data, NOON))["state"] == "warn"


# ── ⑧ 반증 — 게이트 한 줄을 지운 변이체에서 빨간불이 켜지는가 ─────────────
def _scenarios() -> dict:
    """위 단언들의 핵심 셋 — 셋 다 '섞지 않는다(False)'가 정답이다."""
    return {
        "꺼짐": service._blend_ok(_car(kcar_sample=9)),
        "나이": service._blend_ok(_car(kcar_checked_at=_ts(8))),
        "표본": service._blend_ok(_car(kcar_sample=3)),
    }


def _mutant(fn, old: str, new: str):
    """원본 소스에서 한 줄을 지운 함수. 전역은 **살아 있는 모듈 dict** 를 쓴다 — 사본을 쓰면
    monkeypatch 로 바꾼 정책을 못 보고 원본 정책을 읽어, 변이가 아니라 픽스처가 결과를 정한다."""
    import types
    src = textwrap.dedent(inspect.getsource(fn))
    assert src.count(old) == 1, f"변이 대상 줄을 못 찾았다: {old!r}"
    ns = dict(vars(service))
    exec(compile(src.replace(old, new), f"<mutant {fn.__name__}>", "exec"), ns)
    tmp = ns[fn.__name__]
    return types.FunctionType(tmp.__code__, vars(service), fn.__name__, tmp.__defaults__)


_MUTANTS = {
    "꺼짐": (service.kcar_value_usable, '    if not pol.get("enabled"):\n        return False\n', ""),
    "나이": (service.kcar_value_usable,
             '    if age is None or age > int(pol["max_age_days"]):\n        return False\n', ""),
    "표본": (service.kcar_value_usable,
             'return int((v or {}).get("kcar_sample") or 0) >= int(pol["min_sample"])', "return True"),
}


def test_원본은_세_시나리오_모두_섞지_않는다(monkeypatch):
    _policy(monkeypatch, OFF)
    assert _scenarios()["꺼짐"] is False
    _policy(monkeypatch, ON)
    got = _scenarios()
    assert got["나이"] is False and got["표본"] is False


@pytest.mark.parametrize("name", list(_MUTANTS))
def test_게이트_한_줄을_지우면_그_시나리오가_빨간불이_된다(monkeypatch, name):
    fn, old, new = _MUTANTS[name]
    monkeypatch.setattr(service, fn.__name__, _mutant(fn, old, new))
    _policy(monkeypatch, OFF if name == "꺼짐" else ON)
    got = _scenarios()[name]
    assert got is True, f"'{name}' 게이트를 지웠는데도 결과가 같다 — 이 파일의 단언이 그 줄을 지키지 못한다"


def test_blend_ok_에서_게이트_호출을_지우면_22일_된_값이_다시_섞인다(monkeypatch):
    """가장 쉬운 퇴행 — `_blend_ok` 가 게이트를 부르는 한 줄을 누가 지우는 경우."""
    v = _car(kcar_sample=3, kcar_checked_at="2026-09-05 23:10:39")
    assert service.effective_median(v) == v["median_price"]
    mut = _mutant(service._blend_ok, "    if not kcar_value_usable(v):\n        return False\n", "")
    monkeypatch.setattr(service, "_blend_ok", mut)
    assert service.effective_median(v) != v["median_price"], "변이체가 22일 된 값을 섞어야 반증이 선다"
