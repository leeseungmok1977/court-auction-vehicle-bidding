# -*- coding: utf-8 -*-
"""REC-1 4회차(지시서 2026-09-30-06) — qa 3회차 N7: 임박 매각기일 알림·헤더 벨 배지의 판정 게이트.

N7  홈 '임박 매각기일 — 3일 이내 · 검토가능 물건'(`service.alert_items`)과 모든 화면의 헤더 벨 배지
    (`service.alert_count`)가 저장 문자열 judgment=='입찰 검토 가능' **만으로** 물건을 골랐다.
    09-29 백업의 E300(2026타경50522_1, 기일 10-12)은 최저가가 이번 회차 값으로 확인되지 않아(floor_unconfirmed)
    예상낙찰가가 없고 판정은 '다음 기일 최저가 공고 대기'인데, 반사실 10-09 09:00 에 D-3 으로 홈 알림
    '예상낙찰가 —'와 벨 1 로 떴다(재등급 전 사본은 520d 까지 2). 캐러셀과 같은 계열 누수의 **세 번째 길**이다
    (09-22 시동 불가 카니발 → 09-29 캐러셀 캐시 경로 N1 → 알림·벨).
    처방: 두 함수가 **한 함수**(`service._alert_rows`)로 고르고, 그 함수는 홈 '지금 입찰 추천' 칸의 판정
    (`lifecycle_bucket_of(v) == "review"` — bid_state state ∈ resale·usepick)을 그대로 쓴다. 모수도 그 칸을 센
    목록과 같다(hide_incomplete).

시각은 반사실 **2026-10-09 09:00 으로 고정**한다(service.date/datetime · datetime 모듈 · SQL date('now')).
E300·520d·G90 은 09-29 백업 값 그대로다(G90 대조군만 기일을 10-12 로 옮기면서 그 기일내역 행도 같이 옮겼다).
외부 요청 0 — 루프백 밖 connect·connect_ex·DNS 와 법원 요청 함수를 막고 시도를 기록한다(TEST-1).
"""
import datetime as _dtmod
import inspect
import re
import socket

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from web import db, service

NOW_D = _dtmod.date(2026, 10, 9)        # 반사실: E300 기일(10-12) D-3
NOW_T = (9, 0)
SALE = "2026-10-12"
_REAL_DATE, _REAL_DT = _dtmod.date, _dtmod.datetime
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}   # XFF 가 없으면 이 앱은 요청을 관리자(SSH 터널)로 본다


# ── 외부 요청 0(시도 기록) ─────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts: list = []
    real, real_ex, real_gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def _lo(h) -> bool:
        return h is None or str(h) in ("127.0.0.1", "::1", "localhost", "testserver")

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


# ── 반사실 시각 고정 ────────────────────────────────────────────────────
class _FD(_REAL_DATE):
    @classmethod
    def today(cls):
        return cls(NOW_D.year, NOW_D.month, NOW_D.day)


class _FDT(_REAL_DT):
    @classmethod
    def now(cls, tz=None):
        return cls(NOW_D.year, NOW_D.month, NOW_D.day, *NOW_T)

    @classmethod
    def today(cls):
        return cls.now()


def _sql_time(args):
    """SQLite date()/datetime() 의 'now' 를 고정 시각으로. 이 앱이 쓰는 수식('localtime', '±N day')만 받는다."""
    if not args or args[0] is None:
        return None
    s = str(args[0])
    if s == "now":
        t = _REAL_DT(NOW_D.year, NOW_D.month, NOW_D.day, *NOW_T)
    else:
        try:
            t = _REAL_DT.fromisoformat(s[:19])
        except ValueError:
            return None
    for m in args[1:]:
        m = str(m).strip()
        if m == "localtime":
            continue
        mm = re.match(r"^([+-]?\d+) days?$", m)
        if not mm:
            raise ValueError(f"고정 시각 하네스가 모르는 SQL 날짜 수식 {m!r}")
        t = t + _dtmod.timedelta(days=int(mm.group(1)))
    return t


def _sql_date(*a):
    t = _sql_time(a)
    return t.date().isoformat() if t else None


def _sql_datetime(*a):
    t = _sql_time(a)
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else None


@pytest.fixture
def clock(monkeypatch):
    """2026-10-09 09:00 — 판정(bid_state·floor_lag·sale_time_passed)·알림(datetime 모듈)·SQL 이 같은 '지금'을 본다."""
    monkeypatch.setattr(service, "date", _FD)
    monkeypatch.setattr(service, "datetime", _FDT)
    monkeypatch.setattr(_dtmod, "date", _FD)
    monkeypatch.setattr(_dtmod, "datetime", _FDT)
    real_connect = db.connect

    def _connect():
        c = real_connect()
        c.create_function("date", -1, _sql_date)
        c.create_function("datetime", -1, _sql_datetime)
        return c
    monkeypatch.setattr(db, "connect", _connect)
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    assert service.date.today() == NOW_D and _dtmod.date.today() == NOW_D
    return NOW_D


def _mk(vid, **kw):
    row = {"id": vid, "folder_key": vid, "case_no": f"2026타경{vid}", "item_no": "1",
           "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
           "sale_date": SALE, "sale_time": "10:00", "status": "완료", "photo_count": 3,
           "mileage_km": 50_000, "fail_count": 1, "judgment": "입찰 검토 가능",
           "market_confidence_label": "높음", "market_confidence": 81}
    row.update(kw)
    db.upsert_vehicle(row)
    return db.get_vehicle(vid)


# 09-29 백업 값 그대로(기일·기일내역 날짜 포함).
def _e300():
    """2026타경50522_1 벤츠 E300 4Matic — 기일내역 유찰 2회(목록 3회) · 마지막 회차 09-07 < 기일 10-12 · 0.7²."""
    hist = [{"ymd": "2026-06-29", "result_code": "002", "result": "유찰", "lws_price": 19_000_000, "dspsl_amt": None},
            {"ymd": "2026-08-03", "result_code": "002", "result": "유찰", "lws_price": 13_300_000, "dspsl_amt": None},
            {"ymd": "2026-09-07", "result_code": "", "result": "", "lws_price": 9_310_000, "dspsl_amt": 0}]
    return _mk("GE300", case_no="2026타경50522", maker="벤츠", model="벤츠 E300 4Matic", year=2017,
               court="성남지원", appraisal_value=19_000_000, min_sale_price=9_310_000, fail_count=3,
               median_price=18_595_000, sample_count=42, market_confidence=80, accident_grade="none",
               upper_bid=9_413_200, lower_bound=9_310_000, photo_count=8, mileage_km=None, dxdy_history=hist)


def _520d():
    """2026타경30118_1 BMW 520d(재등급 전 사본) — 유찰 3회인데 최저가 980만 = 감정가 2,000만 × 0.7² → price_behind."""
    return _mk("G520", case_no="2026타경30118", maker="BMW", model="BMW 520d", year=2017, court="전주지방법원",
               appraisal_value=20_000_000, min_sale_price=9_800_000, fail_count=3,
               median_price=20_795_000, sample_count=14, market_confidence=85, accident_grade="accident",
               upper_bid=10_645_200, lower_bound=9_800_000, photo_count=15)


def _g90(vid="CTRL", **kw):
    """대조군 — 2025타경34553_1 G90(비가드, 저장 '입찰 검토 가능', 실데이터 판정 usepick). 기일을 10-12 로 옮기며
    기일내역의 '이번 기일' 행도 같이 옮겼다 — 그래야 백업에서처럼 최저가가 이번 회차 값으로 확인된 물건이다."""
    sd = kw.pop("sale_date", SALE)
    hist = [{"ymd": "2026-04-22", "result_code": "002", "result": "유찰", "lws_price": 29_000_000, "dspsl_amt": None},
            {"ymd": "2026-06-10", "result_code": "002", "result": "유찰", "lws_price": 20_300_000, "dspsl_amt": None},
            {"ymd": "2026-07-15", "result_code": "001", "result": "", "lws_price": 16_240_000, "dspsl_amt": None},
            {"ymd": sd, "result_code": "", "result": "", "lws_price": 16_240_000, "dspsl_amt": 0}]
    row = dict(case_no="2025타경34553", maker="현대자동차", model="G90", year=2020, court="광주지방법원",
               appraisal_value=29_000_000, min_sale_price=16_240_000, fail_count=2, median_price=34_050_000,
               sample_count=12, market_confidence=65, market_confidence_label="보통", accident_grade="accident",
               upper_bid=17_818_000, lower_bound=16_240_000, photo_count=11, mileage_km=74_496,
               auction_result="미확정", sale_date=sd, dxdy_history=hist)
    row.update(kw)
    return _mk(vid, **row)


def _mixed():
    """알림 후보(저장 '입찰 검토 가능')가 갈리는 길을 한 벌로. 반환: {id: 3일 창 알림에 드는가}."""
    _e300()
    _520d()
    _g90("CTRL")                                                           # 비가드 · review · D-3 → 든다
    _g90("STOP", runnable="no")                                            # 시동 불가 → bid_state stop → 칸 lowconf
    _g90("LOWC", market_confidence_label="낮음", market_confidence=30)     # 시세 신뢰도 낮음 → 칸 lowconf
    _g90("TODAY_LIVE", sale_date=NOW_D.isoformat(), sale_time="23:59")     # 오늘 · 입찰 시각 전 → 든다(D-DAY)
    _g90("TODAY_ENDED", sale_date=NOW_D.isoformat(), sale_time="08:00")    # 오늘 · 시각 경과 → 빠진다
    _g90("FAR", sale_date="2026-10-20")                                    # D-11 → 3일 창 밖(14일 창엔 든다)
    _g90("DUP", case_no="(중복)")                                          # 목록이 숨기는 사건번호 → 칸 목록에 없다
    return {"GE300": False, "G520": False, "CTRL": True, "STOP": False, "LOWC": False,
            "TODAY_LIVE": True, "TODAY_ENDED": False, "FAR": False, "DUP": False}


def _review_window(days: int) -> set:
    """기대값을 **알림 함수를 거치지 않고** 센다 — 홈 '지금 입찰 추천' 칸을 센 목록(hide_incomplete)에서
    칸 판정 ∩ 오늘~D+days ∩ 입찰 시각 전."""
    out = set()
    for v in db.list_vehicles(hide_incomplete=True):
        if service.lifecycle_bucket_of(v, BT) != "review":
            continue
        dd = (_REAL_DATE.fromisoformat(v["sale_date"]) - NOW_D).days
        if 0 <= dd <= days and not (dd == 0 and service.sale_time_passed(v)):
            out.add(v["id"])
    return out


# ══ 전제 — 공허 통과 방지 ══════════════════════════════════════════════════
def test_전제_픽스처가_각_갈래에_실제로_떨어진다(clock):
    _mixed()
    for vid in ("GE300", "G520"):
        v = db.get_vehicle(vid)
        st = service.bid_state(v, BT)
        assert service.floor_unconfirmed(v) and service.floor_lagging(v), f"{vid}: 가드가 아니다"
        assert service.expected_for(v, BT) is None, f"{vid}: 예상낙찰가가 나온다"
        assert v["judgment"] == "입찰 검토 가능", f"{vid}: 저장 문자열이 N7 의 조건이 아니다"
        assert (st["state"], st["label"]) == ("wait", "다음 기일 최저가 공고 대기"), (vid, st["state"], st["label"])
        assert service.lifecycle_bucket_of(v, BT) == "wait", vid
    c = db.get_vehicle("CTRL")
    assert not service.floor_unconfirmed(c) and service.expected_for(c, BT), "대조군이 가드이거나 예상낙찰가가 없다"
    assert service.lifecycle_bucket_of(c, BT) == "review", "대조군이 '지금 입찰 추천' 칸이 아니다"
    assert service.bid_state(db.get_vehicle("STOP"), BT)["tone"] == "stop"
    assert service.lifecycle_bucket_of(db.get_vehicle("STOP"), BT) == "lowconf"
    assert service.lifecycle_bucket_of(db.get_vehicle("LOWC"), BT) == "lowconf"
    for vid in ("STOP", "LOWC"):
        assert not service.floor_unconfirmed(db.get_vehicle(vid)), f"{vid}: 가드면 '가드는 아닌데 칸도 아님'을 못 본다"
    assert service.sale_time_passed(db.get_vehicle("TODAY_ENDED"))
    assert not service.sale_time_passed(db.get_vehicle("TODAY_LIVE"))
    assert service.lifecycle_bucket_of(db.get_vehicle("DUP"), BT) == "review", "DUP 은 판정으로는 칸이어야 모수 차이를 본다"
    assert "DUP" not in {v["id"] for v in db.list_vehicles(hide_incomplete=True)}, "목록이 DUP 을 숨기지 않는다"
    # 옛 규칙(저장 문자열 · 3일 창)이라면 무엇이 들어갔는가 — 이 파일이 막는 대상이 실제로 후보에 있다
    old = {v["id"] for v in db.list_vehicles(judgment="입찰 검토 가능", upcoming_days=3)}
    assert {"GE300", "G520", "STOP", "LOWC", "DUP"} <= old, sorted(old)


# ══ N7 재현 — 가드 + 저장 '입찰 검토 가능' + D-3 ══════════════════════════════
def test_N7_가드_D3_는_알림0_벨0(clock):
    _e300()
    v = db.get_vehicle("GE300")
    assert (_REAL_DATE.fromisoformat(v["sale_date"]) - NOW_D).days == 3 and service.floor_unconfirmed(v)
    items = service.alert_items(3)
    assert items == [], f"가드 물건이 임박 알림에 들어왔다: {[(r['id'], r.get('expected_win')) for r in items]}"
    assert service.alert_count(3) == 0, "가드 물건이 헤더 벨 배지에 세어졌다"


def test_N7_재등급_전_사본처럼_520d_까지_있어도_0(clock):
    _e300()
    _520d()
    assert service.alert_items(3) == [] and service.alert_count(3) == 0


def test_비가드_정상_물건은_그대로_1(clock):
    _e300()
    _g90("CTRL")
    items = service.alert_items(3)
    assert [r["id"] for r in items] == ["CTRL"], [r["id"] for r in items]
    assert items[0]["dday"] == 3 and items[0]["expected_win"], items[0].get("expected_win")
    assert service.alert_count(3) == 1


# ══ 불변식 — 알림 = '지금 입찰 추천' 칸 ∩ 기일 창 ∩ 입찰 시각 전, 벨 = 알림 수 ═════════════
@pytest.mark.parametrize("days", [0, 1, 3, 7, 10, 14])   # 10: FAR(D-11)이 창 바로 밖 — 창 경계 한 칸 어긋남을 잡는다
def test_알림은_지금입찰추천_칸의_기일창_교집합이고_벨은_그_수다(clock, days):
    _mixed()
    items = service.alert_items(days)
    got = [r["id"] for r in items]
    assert len(got) == len(set(got)), f"같은 물건이 두 번: {got}"
    want = _review_window(days)
    assert set(got) == want, f"창 {days}일: 알림 {sorted(got)} ≠ 칸 {sorted(want)}"
    assert service.alert_count(days) == len(items), f"창 {days}일: 벨 {service.alert_count(days)} ≠ 알림 {len(items)}"


def test_3일창_기대값을_갈래별로_고정한다(clock):
    want = _mixed()
    got = {r["id"] for r in service.alert_items(3)}
    assert got == {k for k, v in want.items() if v}, sorted(got)
    assert {r["id"] for r in service.alert_items(14)} == {"CTRL", "TODAY_LIVE", "FAR"}


def test_알림_카드엔_예상낙찰가가_비지_않고_가드가_없다(clock):
    _mixed()
    for days in (3, 14):
        for r in service.alert_items(days):
            assert r.get("expected_win"), f"{r['id']}: 예상낙찰가 없이 알림에 실렸다(카드에 '—')"
            assert not service.floor_unconfirmed(r), f"{r['id']}: 최저가 미확인 물건이 알림에 실렸다"
            assert isinstance(r["dday"], int) and r["dday"] >= 0, (r["id"], r["dday"])


# ══ 화면 — 홈 알림 카드 수 = 벨(홈) = 벨(다른 화면) ══════════════════════════════
def test_화면_홈과_다른_화면의_벨이_알림_카드_수와_같다(clock):
    _mixed()
    import web.app as A
    c = TestClient(A.app)
    r = c.get("/", headers=_PUBLIC)
    assert r.status_code == 200
    ids = [a["id"] for a in r.context["alerts"]]
    assert sorted(ids) == ["CTRL", "TODAY_LIVE"], ids
    assert r.context["alert_badge"] == len(ids)
    assert A.templates.env.globals["alert_count"]() == len(ids), "다른 화면의 벨(alert_count)이 홈 카드 수와 다르다"
    for path in ("/vehicles", "/calendar"):      # /calendar 는 라우트가 백테스트를 부르지 않는 화면
        page = c.get(path, headers=_PUBLIC)
        assert page.status_code == 200, path
        bell = re.findall(r"임박 매각기일 알림 (\d+)건", page.text)
        assert bell == [str(len(ids))], f"{path} 벨 {bell} ≠ 홈 알림 {len(ids)}"


def test_화면_가드뿐이면_벨0_알림_섹션없음(clock):
    _e300()
    _520d()
    import web.app as A
    c = TestClient(A.app)
    r = c.get("/", headers=_PUBLIC)
    assert r.status_code == 200 and r.context["alerts"] == [] and r.context["alert_badge"] == 0
    assert 'id="alerts"' not in r.text, "알림이 0건인데 홈에 '임박 매각기일' 섹션이 그려졌다"
    assert re.findall(r"임박 매각기일 알림 (\d+)건", c.get("/vehicles", headers=_PUBLIC).text) == ["0"]


# ══ 구조 — 판정은 한 곳, 저장 문자열로 말하지 않는다 ══════════════════════════════
def test_구조_두_함수가_한_함수로_고르고_그_함수는_칸_판정을_부른다():
    items_src = inspect.getsource(service.alert_items)
    count_src = inspect.getsource(service.alert_count)
    rows_src = inspect.getsource(service._alert_rows)
    assert "_alert_rows(" in items_src and "_alert_rows(" in count_src, "알림·벨이 한 함수를 부르지 않는다"
    for name, s in (("alert_items", items_src), ("alert_count", count_src)):
        body = s.split('"""')[-1]
        assert "list_vehicles" not in body, f"{name} 가 따로 질의한다 — 벨·카드가 다시 두 벌이 된다"
        assert "judgment" not in body, f"{name} 본문이 judgment 를 본다"
    body = rows_src.split('"""')[-1]
    assert "lifecycle_bucket_of(" in body, "_alert_rows 가 '지금 입찰 추천' 칸 판정을 부르지 않는다"
    assert not re.search(r"""\.get\(\s*["']judgment["']\s*\)|\[\s*["']judgment["']\s*\]""", body), (
        "_alert_rows 가 저장 판정 문자열을 직접 비교한다 — 후보 질의(필요조건) 밖에서 쓰지 않는다")
    assert "hide_incomplete=True" in body, "모수가 '지금 입찰 추천' 목록과 다르다"


def test_후보가_없으면_백테스트를_부르지_않는다(monkeypatch):
    """벨은 모든 화면이 부른다 — 후보 0 인 날 백테스트(캐시가 식었으면 수백 ms)를 깨우지 않는다."""
    calls = []
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: calls.append(1) or BT)
    assert service.alert_count(3) == 0 and service.alert_items(3) == []
    assert calls == [], f"후보가 없는데 백테스트를 {len(calls)}회 불렀다"
