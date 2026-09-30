# -*- coding: utf-8 -*-
"""REC-1 3회차(지시서 2026-09-30-01) — qa 2회차 N1·N2.

N1  홈 '오늘의 추천' **캐시 경로**(아침에 저장한 목록을 하루 동안 다시 쓰는 길)가 재판매 축에서 저장 문자열
    judgment=='입찰 검토 가능'만 다시 봤다. 09-29 백업에는 옛 코드가 그날 저장한 추천(520d·E300 resale)이 있고,
    새 코드로 같은 날 홈을 그리면 최저가가 이번 회차 값으로 확인되지 않은(floor_unconfirmed) 두 차가
    '✓ 되팔아도 남음' · AI 예상낙찰가 '—' 로 떴다(상세는 '이번 회차 최저가 확인 필요'). 계산 경로 `_add` 는
    예상낙찰가가 없어 이미 거르던 물건이다 — 캐시 경로 누수는 2026-09-22(시동 불가 카니발)에 이어 **두 번째**다.
    처방: 두 경로가 **같은 자격 함수**(`service._daily_pick_gate`)를 부른다.
N2  `refresh_lagged_floors` 의 finally 에서 `last_min_refresh` 기록이 실패하면(DB 잠김 등) 올라가던 차단 예외
    (fetch 403 → RuntimeError, warmup HTTPError(403))가 그 OperationalError 로 **바뀌었다.** daily_update 는 그것을
    비차단 오류로 격리해 낙찰결과·최종 검토(법원 요청)로 계속 갔다 — C.4-5 즉시 중단이 기록 한 줄에 풀린 것이다.
    qa 의 scratch 적대 테스트 2개(tests_adv/test_qa_r2_f3.py)를 이름 그대로 옮기고, 올라온 예외의 **종류**까지 본다.

외부 요청 0 — 루프백 밖 connect·connect_ex·DNS 와 법원 요청 함수(new_session·warmup·fetch_detail)를 막고
**시도를 기록**한다(TEST-1). 매일 갱신이 예외를 격리해도 시도 자체는 테스트 끝에서 빨갛게 잡힌다.
"""
import inspect
import json
import logging
import socket
import sqlite3
from datetime import date, timedelta

import pytest
import requests

from src.collect import courtauction_detail as cad, courtauction_list as cal
from tests.test_daily_picks_two_axes import BT
from web import db, service

TODAY = date.today()


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# ── 외부 요청 0(시도 기록) ─────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts: list = []
    real, real_ex, real_gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def _lo(h) -> bool:
        return h is None or str(h) in ("127.0.0.1", "::1", "localhost")

    def _host(addr):
        return addr[0] if isinstance(addr, tuple) and addr else addr

    def deny(self, addr, *a, **k):
        if _lo(_host(addr)):
            return real(self, addr, *a, **k)
        attempts.append(("connect", addr))
        raise AssertionError(f"외부 연결 시도 {addr!r}")

    def deny_ex(self, addr, *a, **k):
        if _lo(_host(addr)):
            return real_ex(self, addr, *a, **k)
        attempts.append(("connect_ex", addr))
        raise AssertionError(f"외부 연결 시도 {addr!r}")

    def deny_dns(host, *a, **k):
        if _lo(host):
            return real_gai(host, *a, **k)
        attempts.append(("dns", host))
        raise AssertionError(f"DNS 조회 시도 {host!r}")

    def no_court(*a, **k):
        attempts.append(("court", a[:1]))
        raise AssertionError("모킹 없이 법원 요청 함수를 불렀다")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)
    monkeypatch.setattr(socket, "getaddrinfo", deny_dns)
    for name in ("new_session", "warmup", "fetch_detail"):
        monkeypatch.setattr(service, name, no_court)
    yield attempts
    assert not attempts, f"외부 요청 시도 {attempts} — 이 파일은 외부 요청 0 이어야 한다(C.4)"


# ══ N1 — 오늘의 추천: 계산·캐시 두 경로가 같은 자격 ══════════════════════════
@pytest.fixture
def mk(monkeypatch):
    """사진·시세 신뢰도 '높음'을 갖춘 물건 — 캐러셀 자격에서 **예상낙찰가만** 갈리게 만든다."""
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)

    def _mk(vid, **kw):
        row = {"id": vid, "folder_key": vid, "case_no": f"2026타경{vid}", "item_no": "1",
               "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
               "sale_date": _d(13), "sale_time": "10:00", "status": "완료", "photo_count": 3,
               "mileage_km": 50_000, "fail_count": 1,
               "market_confidence_label": "높음", "market_confidence": 81}
        row.update(kw)
        db.upsert_vehicle(row)
        return db.get_vehicle(vid)
    return _mk


# 09-29 백업에 옛 코드가 저장한 그날의 추천 두 대와 같은 모양 — 값은 백업 그대로, 날짜만 오늘 기준으로 옮겼다.
def _g520(mk):
    """2026타경30118_1 BMW 520d — 유찰 3회인데 최저가 980만 = 감정가 2,000만 × 0.7²(저감 2회분) → price_behind."""
    return mk("G520", maker="BMW", model="BMW 520d", year=2017, court="전주지방법원",
              appraisal_value=20_000_000, min_sale_price=9_800_000, fail_count=3,
              judgment="입찰 검토 가능", median_price=20_795_000, sample_count=14,
              market_confidence=85, accident_grade="accident", upper_bid=10_645_200,
              lower_bound=9_800_000, photo_count=15)


def _ge300(mk):
    """2026타경50522_1 벤츠 E300 4Matic — 기일내역 유찰 2회(목록 3회) · 마지막 회차가 이번 기일보다 앞 · 0.7²."""
    hist = [{"ymd": _d(-92), "result_code": "002", "result": "유찰", "lws_price": 19_000_000, "dspsl_amt": None},
            {"ymd": _d(-57), "result_code": "002", "result": "유찰", "lws_price": 13_300_000, "dspsl_amt": None},
            {"ymd": _d(-22), "result_code": "", "result": "", "lws_price": 9_310_000, "dspsl_amt": 0}]
    return mk("GE300", maker="벤츠", model="벤츠 E300 4Matic", year=2017, court="성남지원",
              appraisal_value=19_000_000, min_sale_price=9_310_000, fail_count=3,
              judgment="입찰 검토 가능", median_price=18_595_000, sample_count=42,
              market_confidence=80, accident_grade="none", upper_bid=9_413_200,
              lower_bound=9_310_000, photo_count=8, dxdy_history=hist)


def _rok(mk):
    """대조군 — 최저가가 확인된(가드 아님) 재판매 후보. 예상낙찰가가 있다."""
    return mk("ROK", maker="기아", model="K5", appraisal_value=30_000_000, min_sale_price=10_000_000,
              fail_count=1, judgment="입찰 검토 가능", median_price=30_000_000,
              upper_bid=19_000_000)   # REC-7 ⑺: 재판매 칸은 bid_state 가 되팔이여야 선다 — 되팔이 손익분기를 채운 진짜 후보


def _store(items):
    db.set_setting("daily_picks_ids", json.dumps(items, ensure_ascii=False))
    db.set_setting("daily_picks_date", TODAY.isoformat())


def test_전제_가드_물건은_예상낙찰가_하나만_모자란다(mk):
    """공허 통과 방지 — 두 차가 stop·신뢰도·사진 게이트가 아니라 **예상낙찰가 게이트 하나로만** 갈려야
    N1 을 재현한다(09-29 실측: 둘 다 bid_state wait '다음 기일 최저가 공고 대기', 저장 판정 '입찰 검토 가능')."""
    for v in (_g520(mk), _ge300(mk)):
        assert service.floor_unconfirmed(v) and service.floor_lagging(v), f"{v['id']}: 가드가 아니다"
        assert not service.stale_floor(v), f"{v['id']}: 1회 지연이 아니라 REC-1 다회차 신호로 걸려야 한다"
        assert service.expected_for(v, BT) is None, f"{v['id']}: 예상낙찰가가 나온다"
        assert v["judgment"] == "입찰 검토 가능", "저장 문자열은 재판매 축을 말해야 한다(N1 의 조건)"
        assert v["photo_count"] and v["median_price"] and v["min_sale_price"] and service._promising(v)
        st = service.bid_state(v, BT)
        assert st["state"] == "wait" and st["tone"] != "stop", f"{v['id']}: stop 게이트로 걸린다 {st}"
    r = _rok(mk)
    assert not service.floor_unconfirmed(r) and service.expected_for(r, BT), "대조군은 예상낙찰가가 있어야 한다"
    assert (service.bid_state(r, BT) or {}).get("tone") != "stop"


def test_계산_경로는_가드_물건을_이미_거른다(mk):
    _g520(mk), _ge300(mk), _rok(mk)
    ids = [p["id"] for p in service.compute_daily_picks(5)]
    assert "ROK" in ids, f"대조군이 빠졌다 — 계산 경로가 아무것도 안 올린다: {ids}"
    assert not {"G520", "GE300"} & set(ids), f"계산 경로가 가드 물건을 올렸다: {ids}"


def test_N1_아침_저장분의_가드_물건이_캐시_경로로_되팔아도_남음이_되지_않는다(mk):
    """★ qa N1 재현 — 저장분(재판매 축)을 새 코드로 같은 날 다시 읽는다. 대조군은 그대로 남아야 한다."""
    _g520(mk), _ge300(mk), _rok(mk)
    stored = [{"id": "G520", "kind": "resale"}, {"id": "GE300", "kind": "resale"},
              {"id": "ROK", "kind": "resale"}]
    _store(stored)
    out = service.get_daily_picks(5)
    got = [(d["id"], d["pick_kind"]) for d in out]
    assert got == [("ROK", "resale")], f"가드 물건이 저장분 경로로 '되팔아도 남음' 카드가 됐다: {got}"
    assert all(d.get("expected_win") for d in out), "AI 예상낙찰가 '—' 인 추천 카드가 있다"
    assert json.loads(db.get_setting("daily_picks_ids")) == stored, "캐시 경로가 저장분을 다시 썼다(하루 고정)"


def test_옛_저장형식_문자열_id도_같은_게이트를_지난다(mk):
    """형식 변경 전 저장분(id 문자열 = 재판매 축)도 같은 자격으로 거른다."""
    _g520(mk), _rok(mk)
    _store(["G520", "ROK"])
    assert [d["id"] for d in service.get_daily_picks(5)] == ["ROK"]


def test_계산과_캐시가_같은_자격을_쓴다(mk):
    """두 경로의 자격이 같으면 — 모든 (물건, 칸) 조합을 저장해 캐시 경로로 읽은 결과가 새로 계산한 결과와 같다.

    어느 한쪽 게이트만 고치면(09-22·09-29 두 번 그랬다) 이 등식이 깨진다."""
    _g520(mk), _ge300(mk), _rok(mk)
    u = mk("UNOW", maker="현대", model="쏘나타", min_sale_price=16_000_000, median_price=40_000_000,
           appraisal_value=30_000_000, judgment="유찰 대기")
    t = service.personal_use_tier(u, BT)
    assert t, "전제: 실사용 추천 물건이 아니다"
    mk("STOP", maker="쌍용", model="렉스턴", min_sale_price=10_000_000, median_price=30_000_000,
       appraisal_value=30_000_000, judgment="입찰 검토 가능", runnable="no")
    mk("LOWC", maker="르노", model="SM6", min_sale_price=10_000_000, median_price=30_000_000,
       appraisal_value=30_000_000, judgment="입찰 검토 가능",
       market_confidence_label="보통", market_confidence=52)
    mk("NOPH", maker="쉐보레", model="말리부", min_sale_price=10_000_000, median_price=30_000_000,
       appraisal_value=30_000_000, judgment="입찰 검토 가능", photo_count=0)
    # 실사용 축의 가드 물건(09-29 스포티지 70425_1 꼴): 유찰 1회인데 최저가 = 감정가(1회 지연)
    g = mk("GUSE", maker="기아", model="스포티지", min_sale_price=16_000_000, median_price=40_000_000,
           appraisal_value=16_000_000, judgment="유찰 대기")
    assert service.stale_floor(g) and service.expected_for(g, BT) is None, "전제: 1회 지연 가드"
    ids = ["G520", "GE300", "ROK", "UNOW", "STOP", "LOWC", "NOPH", "GUSE"]
    fresh = {(p["id"], p["kind"]) for p in service.compute_daily_picks(len(ids))}
    assert fresh == {("ROK", "resale"), ("UNOW", t["tier"])}, f"계산 경로 결과가 전제와 다르다: {fresh}"
    _store([{"id": i, "kind": k} for i in ids for k in ("resale", "now", "cheap")])
    cached = {(d["id"], d["pick_kind"]) for d in service.get_daily_picks(len(ids))}
    assert cached == fresh, f"두 경로의 자격이 갈렸다 — 캐시만 {cached - fresh} · 계산만 {fresh - cached}"


def test_두_경로가_같은_자격_함수를_부르고_캐시는_저장_문자열로_판정하지_않는다():
    """게이트를 한쪽에만 고치면 세 번째 누수가 난다 — 두 경로 본문에 같은 함수 호출이 있어야 한다."""
    comp = inspect.getsource(service.compute_daily_picks)
    cache = inspect.getsource(service.get_daily_picks)
    assert "_daily_pick_gate(" in comp, "계산 경로가 공용 자격 함수를 안 부른다"
    assert "_daily_pick_gate(" in cache, "캐시 경로가 공용 자격 함수를 안 부른다"
    assert '!= "입찰 검토 가능"' not in cache, "캐시 경로가 저장 문자열(judgment)로 카드 판정을 다시 정한다"


# ══ N2 — 차단 뒤 last_min_refresh 기록 실패가 차단을 가리지 않는다 ══════════════
# (아래 도우미와 첫 두 테스트는 qa 2회차 scratch `tests_adv/test_qa_r2_f3.py` 에서 옮겼다 — 이름 그대로.)
def V(i=0, **kw):
    base = {"id": f"L_{i}", "case_no": f"2026타경{30118 + i}", "item_no": "1", "court": "전주지방법원",
            "court_code": "B000520", "doc_id": "B000520" + f"{20260130030118 + i}" + "11",
            "appraisal_value": 20_000_000, "min_sale_price": 9_800_000, "fail_count": 3,
            "sale_date": _d(5 + i), "status": "완료", "judgment": "유찰 대기",
            "median_price": 20_795_000, "sample_count": 14, "market_confidence_label": "높음",
            "accident_grade": "none", "upper_bid": 8_000_000, "lower_bound": 9_800_000,
            "breakdown": {"현재최저매각가": 9_800_000}}
    base.update(kw)
    return base


class R:
    def __init__(self, status=200, payload=None, ctype="application/json;charset=UTF-8", text=None):
        self.status_code, self.headers = status, {"Content-Type": ctype}
        self.text = text if text is not None else json.dumps(payload or {}, ensure_ascii=False)

    def json(self):
        return json.loads(self.text)


class S:
    """requests.Session 대역 — 실제 warmup()·fetch_detail() 코드가 이 객체를 부른다(요청 0)."""
    def __init__(self, responder):
        self.gets, self.posts, self.responder, self.headers = [], [], responder, {}

    def get(self, url, **k):
        self.gets.append(url)
        return R(200, {}, "text/html", "<html></html>")

    def post(self, url, data=None, **k):
        body = json.loads(data)
        self.posts.append(body["dma_srchGdsDtlSrch"]["csNo"])
        return self.responder(len(self.posts), body)


def payload(sd, price, court="B000520"):
    rows = [{"auctnDxdyKndCd": "01", "dxdyYmd": "20260801", "auctnDxdyRsltCd": "002",
             "tsLwsDspslPrc": "9800000", "dspslAmt": "0"},
            {"auctnDxdyKndCd": "01", "dxdyYmd": sd.replace("-", ""), "auctnDxdyRsltCd": "",
             "tsLwsDspslPrc": str(price), "dspslAmt": "0"}]
    return {"data": {"dma_result": {"dspslGdsDxdyInfo": {"cortOfcCd": court}, "gdsDspslDxdyLst": rows}}}


def _enable(monkeypatch):
    real = service.load_config
    monkeypatch.setattr(service, "load_config",
                        lambda *a, **k: {**real(*a, **k), "min_refresh_enabled": True})


def _stub_rest(monkeypatch, seen):
    """재조회 뒤 단계들을 가짜로 — 어디까지 도달했는지 seen 에 남긴다."""
    monkeypatch.setattr(service, "collect_upcoming", lambda **k: 0)
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "blocked", "code": 407})
    monkeypatch.setattr(service, "reuse_market_prices", lambda **k: {})
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: seen.append("update_results") or 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: seen.append("review") or
                        {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect",
                        lambda **k: seen.append("newcar") or {"matched": 0, "remaining": 0})
    monkeypatch.setattr(service.encar, "new_session", lambda: object())


def _wire(monkeypatch, responder):
    sess = S(responder)
    monkeypatch.setattr(service, "new_session", lambda: sess)
    monkeypatch.setattr(service, "warmup", cal.warmup)
    monkeypatch.setattr(service, "fetch_detail", cad.fetch_detail)
    for m in (cal.time, cad.time, service.time):
        monkeypatch.setattr(m, "sleep", lambda s: None)
    return sess


def _fail_setting(monkeypatch, key="last_min_refresh"):
    real = db.set_setting

    def f(k, v):
        if k == key:
            raise sqlite3.OperationalError("database is locked")
        return real(k, v)
    monkeypatch.setattr(db, "set_setting", f)


def _run():
    rid = db.create_run(target=0)
    try:
        out = service.daily_update(run_id=rid)
        return "continued", out
    except Exception as e:  # noqa: BLE001
        return f"raised {type(e).__name__}: {e}", None


class _Rs:
    def __init__(self, code):
        self.status_code = code


def _warmup_raising(monkeypatch, exc_factory, first_only=False):
    calls = []

    def wu(_s):
        calls.append(1)
        if not first_only or len(calls) == 1:
            raise exc_factory()
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", wu)
    return calls


# ── qa 원본 ① 차단(403) 뒤 finally 의 설정 저장이 실패하면 — 차단 신호가 가려지는가 ─────────────
def test_차단_뒤_설정저장_실패가_차단을_가리지_않는다(monkeypatch, caplog):
    for i in range(3):
        db.upsert_vehicle(V(i))
    seen = []
    _stub_rest(monkeypatch, seen)
    sess = _wire(monkeypatch, lambda n, b: R(403))
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    caplog.set_level(logging.WARNING, logger="naechaget.floor_refresh")
    outcome, _ = _run()
    assert outcome.startswith("raised") and seen == [], f"차단 뒤에도 갱신이 계속됐다: {outcome} · {seen}"
    # (옮기며 강화) 올라온 것은 **차단 예외**다 — 설정 저장의 OperationalError 가 아니다. 요청은 1회에서 멈췄다.
    assert outcome.startswith("raised RuntimeError") and "차단" in outcome, outcome
    assert len(sess.posts) == 1, f"차단 뒤 요청을 더 보냈다: {len(sess.posts)}"
    assert "last_min_refresh 기록 실패" in caplog.text, "기록 실패가 어디에도 남지 않았다"


def test_warmup_403_뒤_설정저장_실패가_차단을_가리지_않는다(monkeypatch, caplog):
    db.upsert_vehicle(V(0))
    seen = []
    _stub_rest(monkeypatch, seen)
    _warmup_raising(monkeypatch, lambda: requests.exceptions.HTTPError("403 Forbidden", response=_Rs(403)))
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    caplog.set_level(logging.WARNING, logger="naechaget.floor_refresh")
    outcome, _ = _run()
    assert outcome.startswith("raised") and seen == [], f"차단 뒤에도 갱신이 계속됐다: {outcome} · {seen}"
    assert outcome.startswith("raised HTTPError") and "403" in outcome, outcome
    assert "last_min_refresh 기록 실패" in caplog.text, "기록 실패가 어디에도 남지 않았다"


# ── 같은 가장자리의 나머지 갈래 ──────────────────────────────────────────
def test_비정상_3연속_뒤_설정저장_실패도_중단을_가리지_않는다(monkeypatch):
    for i in range(4):
        db.upsert_vehicle(V(i))
    seen = []
    _stub_rest(monkeypatch, seen)

    def boom(n, b):
        raise requests.exceptions.ConnectionError("끊김")
    sess = _wire(monkeypatch, boom)
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    outcome, _ = _run()
    assert outcome.startswith("raised RuntimeError") and "3회 연속" in outcome, outcome
    assert seen == [] and len(sess.posts) == 3, (seen, len(sess.posts))


def test_직접_호출도_429_차단_예외가_그대로_올라온다(monkeypatch):
    """관리 명령(`python -m web.maint floor-refresh`)이 부르는 자리 — 예외 종류가 바뀌지 않아야 한다."""
    for i in range(2):
        db.upsert_vehicle(V(i))
    sess = _wire(monkeypatch, lambda n, b: R(429))
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    with pytest.raises(RuntimeError, match="차단"):
        service.refresh_lagged_floors()
    assert len(sess.posts) == 1


def test_비차단_오류_뒤_설정저장_실패는_원래_오류로_격리된다(monkeypatch):
    """warmup 연결 끊김(비차단) + 기록 실패 → 격리되는 것은 **원래 오류**다(실행 메시지가 거짓 원인을 말하지 않게)."""
    db.upsert_vehicle(V(0))
    seen = []
    _stub_rest(monkeypatch, seen)
    _warmup_raising(monkeypatch, lambda: requests.exceptions.ConnectionError("끊김"), first_only=True)
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    outcome, out = _run()
    assert outcome == "continued" and "update_results" in seen, (outcome, seen)
    assert out["floor"]["error_type"] == "ConnectionError", out["floor"]
    assert "⚠최저가 재조회 오류 ConnectionError" in db.latest_run()["message"]


def test_정상_완료_뒤_설정저장_실패는_예전처럼_올라가_격리된다(monkeypatch):
    """올라갈 예외가 없으면 기록 실패를 **삼키지 않는다** — 호출자가 비차단 오류로 격리하고 메시지에 남는다."""
    db.upsert_vehicle(V(0))
    sds = {V(0)["doc_id"][7:21]: V(0)["sale_date"]}
    seen = []
    _stub_rest(monkeypatch, seen)
    sess = _wire(monkeypatch, lambda n, b: R(200, payload(sds[b["dma_srchGdsDtlSrch"]["csNo"]], 6_860_000)))
    _enable(monkeypatch)
    _fail_setting(monkeypatch)
    outcome, out = _run()
    assert outcome == "continued" and "update_results" in seen, (outcome, seen)
    assert out["floor"]["error_type"] == "OperationalError", out["floor"]
    assert len(sess.posts) == 1
    assert db.get_vehicle("L_0")["min_sale_price"] == 6_860_000, "기록 전에 반영한 값은 남아야 한다"
    assert "⚠최저가 재조회 오류 OperationalError" in db.latest_run()["message"]
