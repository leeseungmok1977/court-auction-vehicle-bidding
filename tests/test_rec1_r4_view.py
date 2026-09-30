# -*- coding: utf-8 -*-
"""REC-1 4회차(지시서 2026-09-30-07) — 세 가지 **화면** 결함.

  1  홈 '임박 매각기일'(#alerts) 카드 — 예상낙찰가가 없으면 맨 '—' 대신 목록·캐러셀과 같은 '미산출'(회색 · 한 단계 작게),
     가드 물건이면 그 아래 '최저가 확인 필요'. '검토가능' 게이트는 service(backend, qa N7)가 건다 — 여기서 보는 것은
     게이트가 새었을 때의 **템플릿 한 겹**이라, alert_items 를 게이트 이전 동작(저장 판정 문자열만)으로 바꿔 넣고 본다.
  2  리포트 07 — 예상낙찰가가 없을 때의 문장이 가장 좋은 경우를 '최악의 경우'라고 불렀다(2회째 지적: 2회차 노트 7 ·
     3회차 고칠 것 1). 가드면 '표시된 최저매각가에 낙찰된다고 가정 — 실제 이번 회차 최저가는 확인 전', 비가드면 '가장 좋은
     경우'. 행 수·이름은 아래 표와 같게(E300: 두 줄인데 '재판매 상한가 … 한 가지 경우'라 했다).
  3  리포트 §01 — 재판매 상한가가 0원 이하인데 `not upper` 만으로 걸러 음수를 기준선으로 인쇄했다(1470 '마진 확보선
     -342,000원 이하가 기준'). 상세와 같은 '산정 불가 — 상한가 0원 이하'. 같은 §01 의 가격 스펙트럼 핀(음수 left)과
     §10 결론 줄의 '이 값 이하로 낙찰 시 목표마진 확보' 지시도 같은 뿌리라 함께 본다.

가리킬 때는 줄 번호가 아니라 **앵커 문자열**로 가리킨다(CLAUDE.md 규칙 8).
외부 요청 0 — 루프백 밖 소켓 연결을 막는다(TEST-1).
공허 통과 방지 — 각 분기는 픽스처가 **실제로 그 분기를 그리는지** 먼저 단언한다.

바이트 불변 기준값(`*_MD5`)은 이 파일의 `seed()` 를 HEAD 7513b71 판 app.py·템플릿 트리(scratch)에서 그대로 돌려 잰 값이다.
날짜·D-day 는 날마다 바뀌므로 지우고 잰다(`_norm`).
"""
import hashlib
import re
import socket
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from web import db, service
from tests.test_render_smoke import BT

_PUB = {"x-forwarded-for": "203.0.113.7"}
FAR = "2999-01-01"
D2 = (date.today() + timedelta(days=2)).isoformat()
D3 = (date.today() + timedelta(days=3)).isoformat()

_BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020, "item_no": "1",
         "sale_date": FAR, "sale_time": "10:00", "status": "완료", "market_confidence": 78,
         "market_confidence_label": "높음", "sample_count": 12, "photo_count": 3, "judgment": "유찰 대기"}

def _bd(base, repair, cond, acc_rate, acc, risk, tax, fixed, margin, why=()):
    """calculator.calculate 의 breakdown 모양(§10 산식 '재판매 상한가 (마진 기준)'이 이것으로 그려진다)."""
    return {"기준시세": base, "예상수리비": repair, "상태정비추가": cond, "상태사유": list(why), "사고감가율": acc_rate,
            "사고감가": acc, "리스크프리미엄": risk, "취득세": tax, "고정부대비": fixed, "마진": margin}


VEH = {
    # ── 리포트 ──
    # 520d 꼴 가드: 감정 2,000만 · 최저 980만(0.7²) · 유찰 3 → 한 단계 지연. 재판매 상한 7,525,950 < 최저 → 07 표 한 줄.
    "lag_1": dict(case_no="2026타경92101", appraisal_value=20_000_000, min_sale_price=9_800_000, fail_count=3,
                  median_price=20_795_000, upper_bid=7_525_950, accident_grade="accident",
                  insurance_history={"own_damage": 8, "opp_damage": 2},
                  breakdown=_bd(20_795_000, 500_000, 0, 0.30, 6_238_500, 1_455_650, 1_455_650, 500_000, 3_119_250)),
    # E300 꼴 가드: 재판매 상한 9,413,200 > 최저 9,310,000 → 07 표 두 줄(표시된 최저가 · 재판매 상한).
    "e300_1": dict(case_no="2026타경92102", maker="벤츠", model="E300", appraisal_value=19_000_000,
                   min_sale_price=9_310_000, fail_count=3, median_price=18_595_000, upper_bid=9_413_200,
                   judgment="입찰 검토 가능"),
    # 1470 꼴: 1회 지연 가드(최저가 = 감정가 · 유찰 1) + 시동·운행 불가 + 재판매 상한 -342,000.
    "neg_g": dict(case_no="2025타경92103", appraisal_value=5_000_000, min_sale_price=5_000_000, fail_count=1,
                  median_price=4_300_000, upper_bid=-342_000, runnable="no",
                  breakdown=_bd(4_300_000, 500_000, 1_750_000, 0.15, 645_000, 301_000, 301_000, 500_000, 645_000,
                                ("자동차검사 유효기간 경과", "시동·운행 불가 언급"))),
    # 50483 꼴: 가드 아님 · 예상낙찰가 있음 · 재판매 상한 -662,000 — 예전엔 '마진 확보선(-662,000원)을 초과'로 갔다.
    "neg_p": dict(case_no="2026타경92104", appraisal_value=2_700_000, min_sale_price=2_700_000, fail_count=0,
                  median_price=2_300_000, upper_bid=-662_000,
                  breakdown=_bd(2_300_000, 500_000, 950_000, 0.15, 345_000, 161_000, 161_000, 500_000, 345_000,
                                ("관리·외관 불량", "자동차검사 유효기간 경과"))),
    # 가드 아님 · 예상낙찰가 있음 · 재판매 상한 양수 — 07·§01 이 예전과 같은 바이트여야 한다.
    "g90_1": dict(case_no="2026타경92105", model="G90", appraisal_value=29_000_000, min_sale_price=16_240_000,
                  fail_count=2, median_price=34_050_000, upper_bid=17_818_000, judgment="입찰 검토 가능",
                  dxdy_history=[{"ymd": FAR, "lws_price": 16_240_000}]),
    # 가드 아님 · 예상낙찰가를 강제로 비운 물건(현 산식으로는 도달하지 않는 분기 — 07 문장만 본다, 아래 픽스처).
    "noexp_p": dict(case_no="2026타경92106", appraisal_value=12_000_000, min_sale_price=8_400_000, fail_count=1,
                    median_price=13_000_000, upper_bid=9_000_000),
    # ── 홈 임박 알림(기일 3일 안) ──
    # E300 꼴 가드 · 저장 판정 '입찰 검토 가능' · D-3 — qa N7 의 반사실 10-09 그 모습.
    "e300_a": dict(case_no="2026타경92111", maker="벤츠", model="E300", appraisal_value=19_000_000,
                   min_sale_price=9_310_000, fail_count=3, median_price=18_595_000, upper_bid=9_413_200,
                   judgment="입찰 검토 가능", sale_date=D3),
    # 가드 아님 · 예상낙찰가 있음 · D-2 — 카드가 예전과 같은 바이트여야 한다.
    "g90_a": dict(case_no="2026타경92112", model="G90", appraisal_value=29_000_000, min_sale_price=16_240_000,
                  fail_count=2, median_price=34_050_000, upper_bid=17_818_000, judgment="입찰 검토 가능",
                  sale_date=D2, dxdy_history=[{"ymd": D2, "lws_price": 16_240_000}]),
    # 가드 아님 · 예상낙찰가가 비어 들어온 카드(게이트가 샌 다른 경우) — '미산출'만, 이유 줄은 없다.
    "plain_a": dict(case_no="2026타경92113", model="아반떼", appraisal_value=12_000_000, min_sale_price=8_400_000,
                    fail_count=1, median_price=13_000_000, upper_bid=9_000_000, judgment="입찰 검토 가능",
                    sale_date=D2),
}
RATES = {"by_court": {"수원지방법원": {"ratio": 0.7, "n": 18, "share": 1.0}}, "global": 0.7, "n": 100,
         "observed": {0.7: 100}}
# 게이트가 새어 들어온 알림 목록(게이트 이전 alert_items 와 같은 모양) — dday·예상낙찰가 포함, 예상가 없음은 강제
_LEAKED = (("g90_a", 2, None), ("e300_a", 3, None), ("plain_a", 2, "none"))

# HEAD 7513b71 판(app.py 31f4cf6b · dashboard 8448dff4 · report 78fdea1a)에서 이 seed() 로 잰 값 — 모듈 끝 설명 참조
G90_ALERT_CARD_MD5 = "9ee8c32d7fddf139106b5f87b1e541b3"
G90_REPORT_07_MD5 = "6c10e2b57919ec627e4b1cba9ca2a4d3"
G90_REPORT_01_MD5 = "58a82c9cda6f5d921fd45ebd3a7efca2"
LIMIT_07 = (" <b>이 마진에는 사고 감가와 리스크 프리미엄이 빠져 있습니다</b> — 되팔기 판단은 10의 "
            "<b>재판매 상한가</b>를 기준으로 하세요.")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real, real_ex = socket.socket.connect, socket.socket.connect_ex

    def _lo(addr):
        h = addr[0] if isinstance(addr, tuple) and addr else addr
        return str(h) in ("127.0.0.1", "::1", "localhost")

    def deny(self, addr, *a, **k):
        if _lo(addr):
            return real(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 화면 테스트는 외부 요청 0 이어야 한다(C.4)")

    def deny_ex(self, addr, *a, **k):
        if _lo(addr):
            return real_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 화면 테스트는 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)


def seed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r4_view.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    monkeypatch.setattr(service, "court_reduction_rates", lambda: RATES)
    monkeypatch.setattr(service, "sale_time_passed", lambda v, now=None: False)
    monkeypatch.setattr(service, "get_daily_picks", lambda n=5: [])
    # noexp_p: 가드가 아닌데 예상낙찰가가 없는 리포트(07 의 비가드 분기). 현 산식은 시세가 있으면 값을 내므로 여기서만 비운다.
    real_band, real_for = service.expected_band, service.expected_for
    monkeypatch.setattr(service, "expected_band",
                        lambda v, bt, *a, **k: None if v.get("id") == "noexp_p" else real_band(v, bt, *a, **k))
    monkeypatch.setattr(service, "expected_for",
                        lambda v, bt, *a, **k: None if v.get("id") == "noexp_p" else real_for(v, bt, *a, **k))
    db.init_db()
    for vid, kw in VEH.items():
        db.upsert_vehicle({**_BASE, "id": vid, "folder_key": vid, **kw})

    # 알림 게이트를 **끈** 상태 — 게이트 이전 alert_items 처럼 저장 판정만 보고 실어 보낸 목록을 그대로 넣는다.
    def _leaked(days=3):
        out = []
        for vid, dd, force in _LEAKED:
            v = db.get_vehicle(vid)
            exp = None if force == "none" else service.expected_for(v, BT)
            out.append({**v, "dday": dd, "expected_win": exp, "photo_url": None})
        return out
    monkeypatch.setattr(service, "alert_items", _leaked)
    monkeypatch.setattr(service, "alert_count", lambda days=3: len(_LEAKED))
    import web.app as A
    return TestClient(A.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return seed(tmp_path, monkeypatch)


# ── 도우미 ──────────────────────────────────────────────────────────────────────
def _sec(h, a, b):
    i = h.find(a)
    assert i >= 0, f"앵커 {a!r} 가 없다 — 템플릿 구조가 바뀌었는지 확인"
    j = h.find(b, i + len(a))
    assert j > i, f"앵커 {b!r} 가 {a!r} 뒤에 없다"
    return h[i:j]


def _text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).replace("&amp;", "&")


def _norm(h):
    """날마다 바뀌는 것(날짜 · D-day · CSS 캐시버스팅)을 지운다."""
    h = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", h)
    h = re.sub(r"D-(?:DAY|\d+)", "D-N", h)
    return re.sub(r"\?v=[0-9a-zA-Z._-]+", "?v=X", h)


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _alert_card(home, vid):
    seg = _sec(home, 'id="alerts"', "<!-- 유망 물건")
    m = re.search(r'<a href="/vehicle/' + re.escape(vid) + r'" class="flex gap-3 min-w-0 border.*?</a>', seg, flags=re.S)
    assert m, f"알림 카드 {vid} 가 없다 — 픽스처가 알림 목록에 실리지 않았다(공허 통과 방지)"
    return m.group(0)


def _value_html(card):
    m = re.search(r'예상낙찰가</span>\s*(.*?)\s*</div>', card, flags=re.S)
    assert m, "알림 카드의 예상낙찰가 자리를 못 찾았다"
    return m.group(1)


S07 = ("<!-- 07 수익 시뮬레이션 -->", "<!-- 08 민감도 -->")
S01 = ('id="sec01"', 'id="sec02"')
S10 = ('id="sec10"', 'id="sec11"')
NEG_AMOUNT = re.compile(r"[-−]\s?\d{1,3}(?:,\d{3})+")


def _report(client, vid):
    r = client.get(f"/vehicle/{vid}/report", headers=_PUB)
    assert r.status_code == 200
    return r.text


def _rd(vid):
    v = db.get_vehicle(vid)
    return v, service.report_data(v, service.load_config(), BT)


def test_픽스처_검산_breakdown_합이_재판매_상한과_같다():
    for vid in ("lag_1", "neg_g", "neg_p"):
        b, up = VEH[vid]["breakdown"], VEH[vid]["upper_bid"]
        ded = sum(b[k] for k in ("예상수리비", "상태정비추가", "사고감가", "리스크프리미엄", "취득세", "고정부대비", "마진"))
        assert b["기준시세"] - ded == up, (vid, b["기준시세"] - ded, up)


# ════════════════════════════════════════════════════════════════════════════════
# 1. 홈 #alerts — 게이트가 샜을 때의 템플릿 한 겹
# ════════════════════════════════════════════════════════════════════════════════
def test_알림_전제_가드_물건이_실제로_새어_들어와_카드로_그려진다(client):
    e = db.get_vehicle("e300_a")
    assert service.floor_unconfirmed(e), "e300_a 가 가드가 아니면 이 파일의 알림 검사는 공허하다"
    assert e["judgment"] == "입찰 검토 가능", "저장 판정 문자열 경로(qa N7)의 모습이어야 한다"
    assert service.expected_for(e, BT) is None, "가드 물건은 예상낙찰가가 없어야 한다(REC-1)"
    assert not service.floor_unconfirmed(db.get_vehicle("g90_a"))
    assert not service.floor_unconfirmed(db.get_vehicle("plain_a"))
    assert service.expected_for(db.get_vehicle("g90_a"), BT), "g90_a 는 예상가가 있는 대조군이어야 한다"
    home = client.get("/", headers=_PUB).text
    for vid in ("e300_a", "g90_a", "plain_a"):
        _alert_card(home, vid)


def test_알림_가드_카드는_맨_대시가_아니라_미산출과_최저가_확인_필요(client):
    card = _alert_card(client.get("/", headers=_PUB).text, "e300_a")
    val = _value_html(card)
    assert ">—<" not in val and "—" not in _text(val), f"맨 '—'가 남았다: {val}"
    assert "미산출" in _text(val) and "최저가 확인 필요" in _text(val), val
    # 회색 · 한 단계 작게(숫자 text-sm → text-xs) · sans(mono 스택엔 한글이 없다)
    m = re.search(r'<span class="([^"]*)">미산출</span>', val)
    assert m, val
    cls = m.group(1).split()
    assert "text-mut" in cls and "text-xs" in cls and "font-mono" not in cls and "text-sm" not in cls, cls
    assert "text-primary" not in val and "text-txt" not in val, "미산출을 잉크·보라로 칠하면 값이 있는 것처럼 읽힌다"


def test_알림_예상가_없는_비가드_카드는_미산출만_이유_줄은_없다(client):
    val = _value_html(_alert_card(client.get("/", headers=_PUB).text, "plain_a"))
    assert "미산출" in _text(val) and "—" not in _text(val), val
    assert "최저가 확인 필요" not in val, "가드가 아닌 물건에 최저가 확인 이유를 달면 거짓이다"


def test_알림_예상가_있는_카드는_예전과_같은_바이트(client):
    home = client.get("/", headers=_PUB).text
    card = _alert_card(home, "g90_a")
    exp = service.expected_for(db.get_vehicle("g90_a"), BT)
    assert f'<span class="font-mono font-bold text-sm text-txt">{exp:,}</span>' in card
    assert "미산출" not in card and "최저가 확인 필요" not in card
    assert _md5(_norm(card)) == G90_ALERT_CARD_MD5, "예상가가 있는 알림 카드의 바이트가 바뀌었다"


def test_알림_섹션_어디에도_값_자리의_맨_대시가_없다(client):
    seg = _sec(client.get("/", headers=_PUB).text, 'id="alerts"', "<!-- 유망 물건")
    vals = re.findall(r'예상낙찰가</span>\s*(.*?)\s*</div>', seg, flags=re.S)
    assert len(vals) == len(_LEAKED), vals
    assert not [v for v in vals if "—" in _text(v)], vals


# ════════════════════════════════════════════════════════════════════════════════
# 2. 리포트 07 — 예상낙찰가가 없을 때의 문장
# ════════════════════════════════════════════════════════════════════════════════
def test_07_가드_한_줄_최악이_아니라_표시된_최저가_가정과_확인_전(client):
    v, rd = _rd("lag_1")
    assert service.floor_unconfirmed(v) and not rd["exp"], "lag_1 은 예상가 없는 가드여야 한다(공허 통과 방지)"
    assert len(rd["sim"]) == 1 and rd["sim"][0]["bid"] == v["min_sale_price"], rd["sim"]
    s = _sec(_report(client, "lag_1"), *S07)
    assert "sec-empty inset" in s, "07 의 예상가 없음 문장이 그려지지 않았다"
    t = _text(s)
    assert "최악" not in t, "가장 좋은 쪽의 가정을 '최악의 경우'라고 부른다(2회째 지적)"
    assert "표시된 최저매각가에 낙찰된다고 가정 한 한 가지 경우만" in t, t[:400]
    assert "실제 이번 회차 최저가는 확인 전" in t
    assert "가장 좋은 경우" not in t, "가드 물건은 그 최저가부터 확인 전이라 최선이라 부를 수도 없다"
    assert '<span class="tag basis">표시된 최저가</span>' in s


def test_07_가드_두_줄이면_두_가지_경우라고_말한다(client):
    v, rd = _rd("e300_1")
    assert service.floor_unconfirmed(v) and not rd["exp"]
    assert len(rd["sim"]) == 2 and v["upper_bid"] > v["min_sale_price"], rd["sim"]
    s = _sec(_report(client, "e300_1"), *S07)
    t = _text(s)
    assert "최악" not in t
    assert "표시된 최저매각가와 재판매 상한가에 낙찰된다고 가정 한 두 가지 경우만" in t, t[:400]
    assert "한 가지 경우" not in t, "표가 두 줄인데 '한 가지 경우'라고 하면 안 된다"
    assert '<span class="tag basis">표시된 최저가</span>' in s and '<span class="tag estimated">재판매 상한</span>' in s


def test_07_비가드_예상가_없음은_가장_좋은_경우(client):
    v, rd = _rd("noexp_p")
    assert not service.floor_unconfirmed(v) and not rd["exp"], "noexp_p 는 예상가 없는 비가드여야 한다"
    assert len(rd["sim"]) == 2, rd["sim"]    # 최저 8,400,000 < 재판매 상한 9,000,000
    s = _sec(_report(client, "noexp_p"), *S07)
    assert "sec-empty inset" in s
    t = _text(s)
    assert "최악" not in t
    assert "현 최저매각가와 재판매 상한가에 낙찰됐다고 가정 한 두 가지 경우만" in t, t[:400]
    assert "최저매각가 줄의 마진이 가장 좋은 경우" in t and "경쟁으로 더 높게 낙찰되면 줄어듭니다" in t
    assert "확인 전" not in t, "확인된 최저가에 '확인 전'을 붙이면 거짓이다"


@pytest.mark.parametrize("vid", ["lag_1", "e300_1", "neg_g", "noexp_p"])
def test_07_금지_문구_최악의_경우는_리포트_어디에도_없다(client, vid):
    """app-design-expert 3회차 고칠 것 1 '금지 목록에 최악의 경우로 읽으십시오를 더한다' — 07 구간만이 아니라 리포트 전체."""
    v, rd = _rd(vid)
    assert not rd["exp"], f"{vid}: 예상가 없는 리포트여야 07 문장이 그려진다(공허 통과 방지)"
    h = _report(client, vid)
    assert "sec-empty inset" in _sec(h, *S07)
    t = _text(h)
    assert "최악의 경우로 읽으십시오" not in t and "최악의 경우" not in t


def test_07_예상가_있는_비가드는_예전과_같은_바이트(client):
    v, rd = _rd("g90_1")
    assert not service.floor_unconfirmed(v) and rd["exp"], "g90_1 은 예상가 있는 비가드여야 한다"
    h = _report(client, "g90_1")
    s = _sec(h, *S07)
    assert "sec-empty inset" not in s and "가정" not in _text(s)
    # Steward(REC-1 4회차 교차검수 반영): 07 각주에 마진 한계 고지 한 줄을 **모든 리포트**에 더했다(REC-5 ⑴ 전까지).
    # 그 한 줄만 달라졌는지 본다 — 문장을 빼면 이전 바이트와 같아야 한다(다른 곳이 바뀌면 빨간불).
    assert LIMIT_07 in s, "07 각주에 마진 한계 고지가 없다"
    assert _md5(_norm(s.replace(LIMIT_07, ""))) == G90_REPORT_07_MD5, "예상가가 있는 리포트의 07 바이트가 고지 한 줄 밖에서 바뀌었다"


# ════════════════════════════════════════════════════════════════════════════════
# 3. 리포트 §01 — 0원 이하 재판매 상한가
# ════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("vid,guard,has_exp", [("neg_g", True, False), ("neg_p", False, True)])
def test_음수_상한_전제(client, vid, guard, has_exp):
    v, rd = _rd(vid)
    assert v["upper_bid"] < 0, "음수 상한 픽스처가 아니면 이 검사는 공허하다"
    assert bool(service.floor_unconfirmed(v)) is guard
    assert bool(rd["exp"]) is has_exp
    if has_exp:   # 예전 코드가 '재판매 부적합 신호 — … 마진 확보선(-N원)을 초과'로 가던 조건
        assert rd["exp"] > v["upper_bid"]
    h = _report(client, vid)
    assert "01 핵심 결론" in _text(h)


@pytest.mark.parametrize("vid", ["neg_g", "neg_p"])
def test_음수_상한_01에_마이너스_금액_기준선이_없다(client, vid):
    h = _report(client, vid)
    s01 = _sec(h, *S01)
    t = _text(s01)
    assert not NEG_AMOUNT.findall(t), f"§01 에 음수 금액이 남았다: {NEG_AMOUNT.findall(t)}"
    for ph in ("재판매 상한가 -", "마진 확보선 -", "마진 확보선(-", "마진 확보선( -"):
        assert ph not in t, ph
    assert "재판매 상한가 산정 불가" in t, "머리의 '재판매 상한가'가 상세와 같은 '산정 불가'여야 한다"
    assert "재판매 목적이면 산정 불가 — 상한가 0원 이하" in t, "요점이 상세와 같은 말이어야 한다"
    assert "재판매 부적합 신호" not in t, "음수 상한을 '마진 확보선'으로 삼는 문장이 남았다"
    # 가격 스펙트럼: 0원 이하 상한가 핀을 그리지 않는다(예전엔 left 가 음수라 차트 밖에 '재판매 상한가'가 찍혔다)
    assert '<span class="lf">재판매 상한가</span>' not in s01
    assert not [x for x in re.findall(r'class="sp-pin[^"]*" style="left:(-?[\d.]+)%', s01) if float(x) < 0]


@pytest.mark.parametrize("vid", ["neg_g", "neg_p"])
def test_음수_상한_10_결론_줄은_숫자는_두고_지시는_산정_불가(client, vid):
    v = db.get_vehicle(vid)
    t = _text(_sec(_report(client, vid), *S10))
    assert "재판매 상한가" in t, "§10 산식이 그려지지 않았다(breakdown 없음 — 공허 통과)"
    assert "이 값 이하로 낙찰 시 목표마진 확보" not in t, "음수를 '이 값 이하로 낙찰' 기준선으로 쓴다"
    assert "0원 이하 — 산정 불가" in t
    assert f"{v['upper_bid']:,}" in t, "검산이 닫히도록 산식 결과 숫자는 그대로 둔다(상세 산정표와 같다)"


def test_양수_상한은_예전_기준선_문장_그대로(client):
    h = _report(client, "lag_1")
    t01 = _text(_sec(h, *S01))
    assert "재판매 목적이면 마진 확보선 7,525,950원 이하가 기준" in t01
    assert "산정 불가" not in t01
    assert "이 값 이하로 낙찰 시 목표마진 확보" in _text(_sec(h, *S10))


def test_양수_상한_비가드_01은_예전과_같은_바이트(client):
    v, rd = _rd("g90_1")
    assert v["upper_bid"] > 0 and not service.floor_unconfirmed(v)
    s = _sec(_report(client, "g90_1"), *S01)
    assert '<span class="lf">재판매 상한가</span>' in s or "재판매 상한가" in _text(s)
    assert _md5(_norm(s)) == G90_REPORT_01_MD5, "양수 상한 비가드 리포트 §01 의 바이트가 바뀌었다"


# 기준값 재는 법(scratch — 저장소 밖):
#   HEAD 7513b71 판 app.py·템플릿 + service.py(d8a5866f) 트리에 이 파일을 복사해 두고, 같은 seed() 로
#   '/' 의 g90_a 알림 카드 · '/vehicle/g90_1/report' 의 07 구간(S07) · §01 구간(S01)을 잘라 _norm 뒤 md5.
