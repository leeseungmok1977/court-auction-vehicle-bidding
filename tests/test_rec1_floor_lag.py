# -*- coding: utf-8 -*-
"""REC-1 수정(지시서 2026-09-29-20) — 최저매각가 지연 감지·가드·재판정·재조회·사고이력·추세 기록.

2026-09-29 재현(backend·qa 독립): 입찰예정 417대 중 239대(57%)의 최저매각가가 **한 회차 전 값**이다.
법원 목록의 minmaePrice 는 직전(유찰된) 회차 값인데, 분석 뒤 유찰된 물건은 상세를 다시 받지 않아
기일내역에 새 회차가 없다. `stale_floor` 는 '유찰≥1 + 최저가=감정가'(1회 지연)만 잡아 2회차 이상
지연은 예상낙찰가가 1/0.7≈1.43배 부풀고 '이번 회차 입찰 부적합'을 받았다.

이 파일의 테스트는 외부 요청 0 이다 — 루프백 밖 소켓 연결을 막고(TEST-1: 전역 가드 없음),
법원 요청 함수(new_session·warmup·fetch_detail)는 가짜로 바꾼다. 09-27 에 변이 실험이 엔카를 실제로
부른 사고가 있었다.
"""
import json
import socket
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.bidcalc.calculator import BidInput, calculate, judge
from src.parse.detail_parser import grade_accident, parse_insurance_history
from web import db, service

ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
SD = (TODAY + timedelta(days=10)).isoformat()          # 기일이 남은 물건
PAST = (TODAY - timedelta(days=3)).isoformat()


# ── 외부 요청 0 ────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real, real_ex = socket.socket.connect, socket.socket.connect_ex

    def _lo(addr):
        h = addr[0] if isinstance(addr, tuple) and addr else addr
        return str(h) in ("127.0.0.1", "::1", "localhost")

    def deny(self, addr, *a, **k):
        if _lo(addr):
            return real(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — REC-1 테스트는 외부 요청 0 이어야 한다(C.4)")

    def deny_ex(self, addr, *a, **k):
        if _lo(addr):
            return real_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — REC-1 테스트는 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)

    def _no_court(*a, **k):
        raise AssertionError("법원 세션을 열었다 — 모킹 없이 법원에 요청하려 했다")
    monkeypatch.setattr(service, "new_session", _no_court)
    monkeypatch.setattr(service, "warmup", _no_court)
    monkeypatch.setattr(service, "fetch_detail", _no_court)


BT = {"min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


def V(**kw) -> dict:
    """기일 남은 유찰 3회 물건 — 감정가 2,000만, 기본은 기일내역 없음(목록 값 그대로)."""
    base = {"id": "T_1", "case_no": "2026타경30118", "item_no": "1", "court": "전주지방법원",
            "court_code": "B000520", "doc_id": "B000520" + "20260130030118" + "11",   # 운영 형식(boCd 7 + saNo 14 + seq)
            "appraisal_value": 20_000_000, "min_sale_price": 9_800_000, "fail_count": 3,
            "sale_date": SD, "status": "완료", "judgment": "입찰 검토 가능",
            "median_price": 20_795_000, "sample_count": 14, "market_confidence_label": "높음",
            "accident_grade": "none", "upper_bid": 10_645_200, "lower_bound": 9_800_000,
            "breakdown": {"현재최저매각가": 9_800_000, "상태정비추가": 0}}
    base.update(kw)
    return base


def H(*rows):
    """기일내역 행: (날짜, 결과, 최저가)."""
    return [{"ymd": d, "result_code": "002" if r == "유찰" else "", "result": r,
             "lws_price": p, "dspsl_amt": None} for d, r, p in rows]


# ═════════════════════════════════════════════════════════════════════
# 1. 지연 감지 — floor_lag · 신호별
# ═════════════════════════════════════════════════════════════════════
def test_저감_횟수는_표준_비율에서만_읽는다():
    f = service.implied_reductions
    assert f(20_000_000, 20_000_000) == 0
    assert f(20_000_000, 14_000_000) == 1
    assert f(20_000_000, 16_000_000) == 1           # 0.8 법원
    assert f(20_000_000, 9_800_000) == 2            # 0.7²
    assert f(1_855_000, 1_187_000) == 2             # 0.8² — 법원 원 단위 절사(1,187,200 → 1,187,000)
    assert f(20_000_000, 11_200_000) is None        # 0.56 = 0.8×0.7 — 비표준은 '모른다'
    assert f(20_000_000, 0) is None and f(None, 9_800_000) is None
    assert f(20_000_000, 25_000_000) is None        # 최저가 > 감정가(재감정 등)는 읽지 않는다


def test_신호_price_behind_기일내역_없이_가격이_유찰보다_한_단계_늦다():
    """09-29 백업의 대다수(목록 값 그대로인 행 249개)가 이 꼴이다 — 2026타경30118_1 BMW 520d."""
    v = V()
    assert service.floor_lag(v) == ["price_behind"]
    assert service.floor_lagging(v) is True
    # 반대쪽: 유찰 2회에 0.7² 면 맞는 값이다
    assert service.floor_lag(V(fail_count=2)) == []


def test_신호_dxdy_old_만으로는_가격을_막지_않는다():
    """기일 변경(연기)은 저감 없이 날짜만 옮긴다 — 유찰 수·가격이 맞으면 숨기지 않고 재조회 대상에만."""
    v = V(fail_count=2, dxdy_history=H(("2026-06-01", "유찰", 20_000_000), ("2026-07-01", "유찰", 14_000_000),
                                        ("2026-08-01", "", 9_800_000)))
    assert service.floor_lag(v) == ["dxdy_old"]
    assert service.floor_lagging(v) is False


def test_신호_dxdy_fails_behind_기일내역의_유찰이_목록보다_적다():
    """이번 기일 행이 있어도 최저가가 비어 있으면 권위값이 아니다 — 날짜는 맞고 유찰 수만 모자란 경우.
    가격은 비표준(0.56)이라 price_behind 는 서지 않는다 → 이 신호 하나만 남는다."""
    v = V(fail_count=3, min_sale_price=11_200_000,
          dxdy_history=H(("2026-06-01", "유찰", 20_000_000), ("2026-07-01", "유찰", 16_000_000),
                         (SD, "", None)))
    assert service.floor_lag(v) == ["dxdy_fails_behind"]
    assert service.floor_lagging(v) is True


def test_세_신호가_함께_서는_전형():
    """분석 때 받은 기일내역이 옛 회차에서 멈춘 물건(09-29 백업 26개) — 2025타경59564_1 꼴."""
    v = V(fail_count=2, min_sale_price=14_000_000,
          dxdy_history=H(("2026-07-13", "유찰", 20_000_000), ("2026-08-25", "", 14_000_000)))
    assert service.floor_lag(v) == ["dxdy_old", "dxdy_fails_behind", "price_behind"]


def test_이번_기일_권위값이_있으면_지연이_아니다():
    """2025타경73487_1 꼴: 저감 없는 회차가 끼어 가격이 유찰보다 한 단계 적어 보여도 법원 값이 우선이다."""
    v = V(fail_count=4, min_sale_price=6_860_000,
          dxdy_history=H(("2026-02-26", "유찰", 20_000_000), ("2026-04-02", "유찰", 20_000_000),
                         ("2026-05-07", "유찰", 14_000_000), ("2026-06-11", "유찰", 9_800_000),
                         (SD, "", 6_860_000)))
    assert service.implied_reductions(20_000_000, 6_860_000) == 3 < 4, "전제: 가격만 보면 지연처럼 보인다"
    assert service.floor_lag(v) == []


def test_기일_지남_낙찰_종결은_대상이_아니다():
    assert service.floor_lag(V(sale_date=PAST)) == []
    assert service.floor_lag(V(auction_result="낙찰")) == []
    assert service.floor_lag(V(auction_result="종결")) == []
    assert service.floor_lag(V(judgment="종결")) == []
    assert service.floor_lag(V(sale_date=None)) == []
    assert service.floor_lag(V(sale_date=TODAY.isoformat())) == ["price_behind"], "오늘 기일은 남은 것"


def test_기일내역이_문자열로_와도_읽는다():
    v = V(fail_count=2, min_sale_price=14_000_000,
          dxdy_history=json.dumps(H(("2026-07-13", "유찰", 20_000_000), ("2026-08-25", "", 14_000_000))))
    assert "dxdy_fails_behind" in service.floor_lag(v)


# ═════════════════════════════════════════════════════════════════════
# 4. 중간 가드 — stale_floor 와 같은 상태·같은 문구
# ═════════════════════════════════════════════════════════════════════
def test_지연이면_예상낙찰가를_내지_않고_stale_floor_와_같은_상태_문구다():
    lag = V()
    assert service.expected_for(lag, BT) is None
    st = service.bid_state(lag, BT)
    stale = V(fail_count=1, min_sale_price=20_000_000)          # 기존 stale_floor(1회 지연)
    assert service.stale_floor(stale) is True
    st0 = service.bid_state(stale, BT)
    assert (st["state"], st["label"], st["tone"]) == (st0["state"], st0["label"], st0["tone"]) == (
        "wait", "다음 기일 최저가 공고 대기", "wait")
    # 반대쪽: 지연이 풀리면(유찰 2회 = 0.7² 가 맞는 값) 예측이 다시 나온다 — 가드가 공허하지 않다
    assert service.expected_for(V(fail_count=2), BT) is not None


def test_가드는_틀린_이번_회차_부적합을_막는다(monkeypatch):
    """예전 판정: 부푼 최저가로 blocked('이번 회차 입찰 부적합'). 가드 뒤: 공고 대기(wait)."""
    v = V(median_price=10_000_000, upper_bid=5_000_000, judgment="유찰 대기")
    mb = service.personal_use_max_bid(v, BT)
    assert mb and v["min_sale_price"] > mb, "전제: 부푼 최저가가 실사용 손익분기를 넘는다"
    st = service.bid_state(v, BT)
    assert (st["state"], st["label"]) == ("wait", "다음 기일 최저가 공고 대기")
    # 반대쪽: 가드를 떼면(= HEAD 8073a3d 동작) blocked 가 나온다 — 이 테스트가 무엇을 막는지 보여 준다
    monkeypatch.setattr(service, "floor_lagging", lambda *_a, **_k: False)
    assert service.bid_state(v, BT)["state"] == "blocked"


def test_stale_floor_자체는_바뀌지_않았다():
    """상세 화면의 설명 문장('감정가와 같음')이 stale_floor 에 묶여 있다 — 다회차 지연에 그 문장을 쓰면 거짓이다."""
    assert service.stale_floor(V()) is False                  # 다회차 지연은 stale_floor 가 아니다
    assert service.floor_unconfirmed(V()) is True             # 가드는 둘을 합친다
    assert service.stale_floor(V(fail_count=1, min_sale_price=20_000_000)) is True


def test_dxdy_old_만인_물건은_예측을_숨기지_않는다():
    v = V(fail_count=2, dxdy_history=H(("2026-06-01", "유찰", 20_000_000), ("2026-07-01", "유찰", 14_000_000),
                                        ("2026-08-01", "", 9_800_000)))
    assert service.expected_for(v, BT) is not None


# ═════════════════════════════════════════════════════════════════════
# 3. 재판정 — 저장된 시세로(외부 요청 0), 판정 규칙은 calculator.judge 한 곳
# ═════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("upper,mn,n,flood", [
    (10_000_000, 9_000_000, 14, False), (10_000_000, 11_000_000, 14, False),
    (10_000_000, 10_000_000, 14, False), (10_000_000, 9_000_000, 3, False),
    (10_000_000, 9_000_000, 14, True), (-5_000_000, 9_000_000, 14, False)])
def test_judge_는_calculate_의_판정과_같다(upper, mn, n, flood):
    cfg = service.load_config()
    # calculate 로 같은 상한가를 만들려면 역산이 필요하다 — 대신 calculate 결과의 상한가로 judge 를 불러 대조한다
    bi = BidInput(median_price=upper + 8_000_000, min_sale_price=mn, sample_count=n,
                  accident_grade="flood" if flood else "none")
    bid = calculate(bi, cfg)
    assert judge(bid.upper_bid, mn, n, flood, cfg) == bid.judgment


def _put(**kw) -> dict:
    row = V(**kw)
    db.upsert_vehicle(row)
    return db.get_vehicle(row["id"])


def test_최저가가_내려가면_유찰대기가_검토가능으로_재판정된다():
    _put(min_sale_price=6_860_000, lower_bound=9_800_000, judgment="유찰 대기", upper_bid=8_000_000,
         breakdown={"현재최저매각가": 9_800_000, "상태정비추가": 700_000}, analyzed_at="2026-09-05 22:01:50",
         starred=1, memo="메모")
    r = service.rejudge_floor_changes()
    v = db.get_vehicle("T_1")
    assert r["judgment_changed"] == 1 and r["to_review"] == 1
    assert v["judgment"] == "입찰 검토 가능"
    assert v["lower_bound"] == 6_860_000
    assert v["breakdown"]["현재최저매각가"] == 6_860_000
    assert v["breakdown"]["상태정비추가"] == 700_000, "상한가 근거(상태 정비)는 그대로여야 한다"
    assert v["upper_bid"] == 8_000_000, "상한가는 최저가와 무관하다 — 다시 계산하지 않는다"
    assert v["analyzed_at"] == "2026-09-05 22:01:50", "시세 나이(analyzed_at)를 새로 고치면 안 된다"
    assert (v["starred"], v["memo"]) == (1, "메모"), "사용자 선택을 덮었다"
    # 멱등 — 두 번째는 바꿀 것이 없다
    assert service.rejudge_floor_changes()["updated"] == 0


def test_최저가가_올라가면_검토가능이_유찰대기로_내려간다():
    _put(min_sale_price=12_000_000, judgment="입찰 검토 가능", upper_bid=10_000_000,
         breakdown={"현재최저매각가": 9_800_000})
    r = service.rejudge_floor_changes()
    assert r["to_wait"] == 1 and db.get_vehicle("T_1")["judgment"] == "유찰 대기"


def test_신뢰도_낮음이면_수동_검토로_내린다():
    _put(min_sale_price=6_860_000, judgment="유찰 대기", upper_bid=8_000_000,
         market_confidence_label="낮음", breakdown={"현재최저매각가": 9_800_000})
    service.rejudge_floor_changes()
    assert db.get_vehicle("T_1")["judgment"] == "시세 신뢰도 낮음, 수동 검토"


@pytest.mark.parametrize("kw", [
    {"judgment": "입찰 보류"}, {"judgment": "시세 신뢰도 낮음, 수동 검토"}, {"judgment": "종결"},
    {"upper_bid": None}, {"auction_result": "낙찰"}, {"status": "상세없음"}])
def test_최저가와_무관한_판정은_건드리지_않는다(kw):
    base = dict(min_sale_price=6_860_000, breakdown={"현재최저매각가": 9_800_000})
    base.update(kw)
    before = _put(**base)
    assert service.rejudge_floor(before) == {}


def test_목록_갱신이_최저가를_바꾸면_다음_재판정이_따라간다():
    """upsert_listing 은 판정을 보존한다(_LISTING_KEEP) — 그래서 재판정 단계가 따로 있어야 한다."""
    _put(min_sale_price=9_800_000, judgment="유찰 대기", upper_bid=8_000_000)
    db.upsert_listing({"id": "T_1", "case_no": "2026타경30118", "item_no": "1", "court_code": "B000520",
                       "min_sale_price": 6_860_000, "fail_count": 3, "sale_date": SD,
                       "appraisal_value": 20_000_000})
    v = db.get_vehicle("T_1")
    assert (v["min_sale_price"], v["judgment"]) == (6_860_000, "유찰 대기"), "전제: 목록은 판정을 보존한다"
    service.rejudge_floor_changes()
    assert db.get_vehicle("T_1")["judgment"] == "입찰 검토 가능"


def test_breakdown_에_최저가_칸이_없는_옛_행도_판정은_맞춘다():
    _put(min_sale_price=6_860_000, lower_bound=6_860_000, judgment="유찰 대기", upper_bid=8_000_000,
         breakdown={"기준시세": 20_000_000})
    service.rejudge_floor_changes()
    v = db.get_vehicle("T_1")
    assert v["judgment"] == "입찰 검토 가능"
    assert "현재최저매각가" not in v["breakdown"], "근거표 모양을 바꾸지 않는다(칸을 새로 만들지 않는다)"


# ═════════════════════════════════════════════════════════════════════
# 2. 상세 재조회 — 기본 꺼짐 · 드라이런 · 상한 · 지연 · 차단 중단
# ═════════════════════════════════════════════════════════════════════
def test_설정_재조회는_오너_승인으로_켜졌고_상한이_있다():
    """오너 승인 2026-09-30(C.4-6 첫 실행): 저장소 config 에서 켰다. 켜짐은 정확히 bool True 여야 하고,
    하루 상한은 코드 하드캡 안이어야 한다(첫 3일 150 → 10-03 부터 60, Steward 지시서).
    꺼진 경로의 '요청 0' 검사는 아래 테스트들이 config 를 메모리에서 꺼서 따로 지킨다."""
    cfg = service.load_config()
    assert cfg["min_refresh_enabled"] is True, "켜짐은 정확히 true(bool) — 문자열·1 은 꺼짐으로 읽힌다"
    assert 0 < cfg["min_refresh_daily_cap"] <= service.MIN_REFRESH_HARD_CAP
    assert cfg["min_refresh_backoff_days"] >= 1


@pytest.mark.parametrize("val", ["true", "True", 1, "yes", None])
def test_켜짐은_정확히_True_일_때만이다(val):
    assert service._min_refresh_settings({"min_refresh_enabled": val})["enabled"] is False


def test_설정이_하드캡을_넘어도_하드캡에서_멈춘다():
    s = service._min_refresh_settings({"min_refresh_enabled": True, "min_refresh_daily_cap": 10_000})
    assert s["cap"] == service.MIN_REFRESH_HARD_CAP == 150
    assert service._min_refresh_settings({"min_refresh_daily_cap": "x"})["cap"] == 0
    assert service._min_refresh_settings({"min_refresh_daily_cap": -5})["cap"] == 0


def test_요청_간_대기는_5초에서_10초다():
    from src.collect.courtauction_list import REQUEST_DELAY_SEC
    lo, hi = service.MIN_REFRESH_JITTER_SEC
    assert REQUEST_DELAY_SEC + lo >= 5 and REQUEST_DELAY_SEC + hi <= 10


def _seed_lagging(n=3):
    ids = []
    for i in range(n):
        vid = f"L_{i}"
        db.upsert_vehicle(V(id=vid, case_no=f"2026타경{30118 + i}", doc_id="B000520" + f"{20260130030118 + i}" + "11",
                            sale_date=(TODAY + timedelta(days=5 + i)).isoformat(),
                            judgment="유찰 대기", upper_bid=8_000_000))
        ids.append(vid)
    return ids


def test_꺼져_있으면_요청_0_대상_수만_센다(monkeypatch):
    real = service.load_config
    monkeypatch.setattr(service, "load_config",      # 저장소 config 는 09-30 에 켜졌다 — 꺼진 경로는 메모리에서 끄고 본다
                        lambda *a, **k: {**real(*a, **k), "min_refresh_enabled": False})
    _seed_lagging(3)
    res = service.refresh_lagged_floors()           # 꺼짐. 법원 함수는 부르면 실패(픽스처)
    assert res["enabled"] is False and res["requests"] == 0 and res["fetched"] == 0
    assert res["targets"] == 3 and res["targets_guard"] == 3
    assert service.floor_refresh_label(res) == "최저가 지연 3대(재조회 꺼짐)"
    assert json.loads(db.get_setting("last_min_refresh"))["targets"] == 3


def test_드라이런은_켜져_있어도_요청_0이고_계획을_낸다():
    _seed_lagging(3)
    cfg = {**service.load_config(), "min_refresh_enabled": True, "min_refresh_daily_cap": 2}
    res = service.refresh_lagged_floors(dry_run=True, config=cfg)
    assert res["requests"] == 0 and res["fetched"] == 0
    assert (res["targets"], res["per_item_requests"], res["planned_items"]) == (3, 1, 2)
    assert res["planned_requests"] == 2 + service.MIN_REFRESH_SESSION_REQUESTS
    assert res["delay_sec"] == [5, 10] and res["est_seconds"] > 0 and res["days_to_clear"] == 2
    assert db.get_setting("last_min_refresh") is None, "드라이런은 아무것도 쓰지 않는다"


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _detail_payload(court="B000520", dxdy=()):
    return {"data": {"dma_result": {
        "dspslGdsDxdyInfo": {"cortOfcCd": court},
        "gdsDspslDxdyLst": [{"auctnDxdyKndCd": "01", "dxdyYmd": d.replace("-", ""),
                             "auctnDxdyRsltCd": c, "tsLwsDspslPrc": str(p), "dspslAmt": "0"}
                            for d, c, p in dxdy]}}}


def _court_stub(monkeypatch, responder):
    calls = {"session": 0, "warmup": 0, "detail": [], "sleep": []}

    def ns():
        calls["session"] += 1
        return object()

    def wu(_s):
        calls["warmup"] += 1

    def fd(_s, sa, bo, seq="1"):
        calls["detail"].append((sa, bo, seq))
        return responder(len(calls["detail"]), sa)
    monkeypatch.setattr(service, "new_session", ns)
    monkeypatch.setattr(service, "warmup", wu)
    monkeypatch.setattr(service, "fetch_detail", fd)
    monkeypatch.setattr(service.time, "sleep", lambda s: calls["sleep"].append(s))
    return calls


def _on(cap=60):
    return {**service.load_config(), "min_refresh_enabled": True, "min_refresh_daily_cap": cap}


def test_켜면_법원_기일내역으로_최저가를_바꾸고_같은_자리에서_재판정한다(monkeypatch):
    ids = _seed_lagging(1)
    sd = db.get_vehicle(ids[0])["sale_date"]
    calls = _court_stub(monkeypatch, lambda n, sa: _Resp(_detail_payload(dxdy=[
        ("2026-06-01", "002", 20_000_000), ("2026-07-06", "002", 14_000_000),
        ("2026-08-10", "002", 9_800_000), (sd, "", 6_860_000)])))
    res = service.refresh_lagged_floors(config=_on())
    v = db.get_vehicle(ids[0])
    assert (calls["session"], calls["warmup"], len(calls["detail"])) == (1, 1, 1)
    assert calls["detail"][0] == ("20260130030118", "B000520", "1"), "docid 로 복원한 키로 물어야 한다"
    assert all(0 <= s <= 5 for s in calls["sleep"]) and len(calls["sleep"]) == 1
    assert res["requests"] == 1 + service.MIN_REFRESH_SESSION_REQUESTS and res["changed"] == 1
    assert v["min_sale_price"] == 6_860_000 and v["lower_bound"] == 6_860_000
    assert v["judgment"] == "입찰 검토 가능", "최저가가 바뀐 자리에서 재판정해야 한다"
    assert v["floor_checked_at"], "재조회 시각(백오프 기준)이 남아야 한다"
    assert service.floor_lag(v) == [], "권위값이 들어오면 가드가 풀린다"
    assert service.floor_refresh_label(res) == "최저가 재조회 1/1(갱신 1)"
    # 백오프 — 같은 날 다시 돌려도 이 물건은 대상이 아니다(이미 지연도 아니다)
    assert service.min_refresh_targets(config=_on()) == []


def test_하루_상한을_넘지_않는다(monkeypatch):
    _seed_lagging(5)
    calls = _court_stub(monkeypatch, lambda n, sa: _Resp(_detail_payload(dxdy=[("2026-07-01", "002", 14_000_000)])))
    res = service.refresh_lagged_floors(config=_on(cap=2))
    assert len(calls["detail"]) == 2 and res["requests"] == 2 + service.MIN_REFRESH_SESSION_REQUESTS
    assert res["not_posted"] == 2, "법원 상세에도 이번 회차가 없으면 가드는 그대로"


def test_우선순위는_가격_지연이면서_시세_있는_물건_먼저_기일_가까운_순(monkeypatch):
    db.upsert_vehicle(V(id="OLD_ONLY", fail_count=2, sale_date=(TODAY + timedelta(days=1)).isoformat(),
                        dxdy_history=H(("2026-06-01", "유찰", 20_000_000), ("2026-07-01", "유찰", 14_000_000),
                                       ("2026-08-01", "", 9_800_000))))
    db.upsert_vehicle(V(id="NOMKT", median_price=None, sale_date=(TODAY + timedelta(days=2)).isoformat()))
    db.upsert_vehicle(V(id="FAR", sale_date=(TODAY + timedelta(days=20)).isoformat()))
    db.upsert_vehicle(V(id="NEAR", sale_date=(TODAY + timedelta(days=3)).isoformat()))
    assert [v["id"] for v in service.min_refresh_targets(config=_on())] == ["NEAR", "FAR", "NOMKT", "OLD_ONLY"]
    plan = service.min_refresh_plan(config=_on())
    assert (plan["targets"], plan["targets_guard"], plan["targets_guard_with_market"],
            plan["targets_dxdy_old_only"]) == (4, 3, 2, 1)


def test_분석_단계가_받을_물건과_받을_키가_없는_물건은_빼고_백오프를_지킨다():
    db.upsert_vehicle(V(id="A", status="미분석"))
    db.upsert_vehicle(V(id="A2", status="상세없음"))
    db.upsert_vehicle(V(id="C", doc_id=""))
    db.upsert_vehicle(V(id="D", floor_checked_at=f"{TODAY.isoformat()} 06:31:00"))
    db.upsert_vehicle(V(id="E", floor_checked_at=f"{(TODAY - timedelta(days=4)).isoformat()} 06:31:00"))
    # 동급참조는 넣는다 — 분석 단계는 엔카가 막히면 건너뛰고, 엔카 0건이면 받은 상세까지 버린다
    db.upsert_vehicle(V(id="F", market_platform=service.REUSE_PLATFORM))
    assert sorted(v["id"] for v in service.min_refresh_targets(config=_on())) == ["E", "F"]


def test_차단이면_즉시_중단하고_예외를_올린다(monkeypatch):
    _seed_lagging(3)

    def responder(n, sa):
        raise RuntimeError("법원경매 차단 상태코드 429")
    calls = _court_stub(monkeypatch, responder)
    with pytest.raises(RuntimeError, match="차단"):
        service.refresh_lagged_floors(config=_on())
    assert len(calls["detail"]) == 1, "차단 뒤에 요청을 더 보냈다(C.4-5)"
    rec = json.loads(db.get_setting("last_min_refresh"))
    assert "차단" in rec["stopped"] and rec["requests"] == 1 + service.MIN_REFRESH_SESSION_REQUESTS


def test_캡차_소프트_차단도_차단이다(monkeypatch):
    _seed_lagging(2)
    calls = _court_stub(monkeypatch, lambda n, sa: (_ for _ in ()).throw(
        RuntimeError("법원경매 차단 감지 — 비정상 응답(캡차/비JSON)")))
    with pytest.raises(RuntimeError):
        service.refresh_lagged_floors(config=_on())
    assert len(calls["detail"]) == 1


def test_비정상_응답_3회_연속이면_중단한다(monkeypatch):
    _seed_lagging(5)
    calls = _court_stub(monkeypatch, lambda n, sa: (_ for _ in ()).throw(ValueError("JSON 깨짐")))
    with pytest.raises(RuntimeError, match="3회 연속"):
        service.refresh_lagged_floors(config=_on())
    assert len(calls["detail"]) == 3


def test_빈_상세는_기존_기일내역을_덮지_않는다(monkeypatch):
    old = H(("2026-07-13", "유찰", 20_000_000), ("2026-08-25", "", 14_000_000))
    db.upsert_vehicle(V(id="E1", fail_count=2, min_sale_price=14_000_000, dxdy_history=old))
    _court_stub(monkeypatch, lambda n, sa: _Resp({"data": {"dma_result": {}}}))
    res = service.refresh_lagged_floors(config=_on())
    v = db.get_vehicle("E1")
    assert res["empty"] == 1 and v["dxdy_history"] == old and v["min_sale_price"] == 14_000_000
    assert v["floor_checked_at"], "헛걸음도 백오프 기준이 된다"


def test_다른_법원_응답은_섞지_않는다(monkeypatch):
    _seed_lagging(1)
    _court_stub(monkeypatch, lambda n, sa: _Resp(_detail_payload(court="999999", dxdy=[(SD, "", 1)])))
    res = service.refresh_lagged_floors(config=_on())
    v = db.get_vehicle("L_0")
    assert res["mismatch"] == 1 and v["min_sale_price"] == 9_800_000 and not v.get("dxdy_history")


def test_재조회는_사진_요항_시세_결과_열을_건드리지_않는다(monkeypatch):
    ids = _seed_lagging(1)
    db.update_fields(ids[0], photo_count=15, median_price=20_795_000, auction_result=None,
                     accident_grade="accident", insurance_history={"own_damage": 8})
    sd = db.get_vehicle(ids[0])["sale_date"]
    _court_stub(monkeypatch, lambda n, sa: _Resp(_detail_payload(dxdy=[(sd, "", 6_860_000)])))
    before = db.get_vehicle(ids[0])
    service.refresh_lagged_floors(config=_on())
    after = db.get_vehicle(ids[0])
    changed = {k for k in after if after[k] != before.get(k)}
    assert changed <= {"dxdy_history", "min_sale_price", "lower_bound", "judgment", "breakdown",
                       "floor_checked_at"}, changed


# ═════════════════════════════════════════════════════════════════════
# 매일 갱신 배선 — 목록 수집 직후 · 재판정 · 실행 기록 · 추세 기록
# ═════════════════════════════════════════════════════════════════════
def _daily_body() -> str:
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    i = src.index("def daily_update(")
    return src[i:src.index("def photo_autosort_run", i)]


def test_재조회는_목록_수집_직후_재판정은_그다음_분석보다_먼저():
    b = _daily_body()
    order = [b.index(x) for x in ("collect_upcoming(", "_reconcile_min_from_dxdy(",
                                  "refresh_lagged_floors(", "rejudge_floor_changes(", "encar_health()")]
    assert order == sorted(order), order


def _stub_daily(monkeypatch):
    monkeypatch.setattr(service, "collect_upcoming", lambda **k: 0)
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "blocked", "code": 407})
    monkeypatch.setattr(service, "reuse_market_prices", lambda **k: {})
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect", lambda **k: {"matched": 0, "remaining": 0})
    # ⑤ 최종 검토 앞에서 법원 세션을 연다 — 가짜 세션(요청 0)
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *_a, **_k: None)
    monkeypatch.setattr(service.encar, "new_session", lambda: object())


def test_매일_갱신은_꺼진_재조회를_세고_재판정하고_추천_수를_남긴다(monkeypatch):
    real = service.load_config
    monkeypatch.setattr(service, "load_config",      # 저장소 config 는 09-30 에 켜졌다 — 꺼진 경로는 메모리에서 끄고 본다
                        lambda *a, **k: {**real(*a, **k), "min_refresh_enabled": False})
    _stub_daily(monkeypatch)
    _seed_lagging(2)
    _put(id="R1", min_sale_price=6_860_000, fail_count=2, judgment="유찰 대기", upper_bid=8_000_000,
         breakdown={"현재최저매각가": 9_800_000})
    rid = db.create_run(target=0)
    out = service.daily_update(run_id=rid)
    assert out["floor"]["enabled"] is False and out["floor"]["requests"] == 0
    assert out["floor"]["targets"] == 2
    assert out["rejudge"]["to_review"] == 1 and db.get_vehicle("R1")["judgment"] == "입찰 검토 가능"
    msg = db.latest_run()["message"]
    assert msg.startswith("입찰예정 0 · 분석 0"), "일일 리포트 파서가 요약으로 인식하는 머리가 깨졌다"
    assert " · 최저가 지연 2대(재조회 꺼짐)" in msg and " · 최저가 재판정 1" in msg
    row = json.loads(db.get_setting(service.SUPPLY_HISTORY_KEY))[-1]
    for k in ("review", "usepick", "usepick_now", "upcoming30", "floor_lag", "at"):
        assert k in row, f"추세 기록에 {k} 가 없다"
    assert row["floor_lag"] == 2 and isinstance(row["review"], int)


def test_추세_기록은_추천_수_없이_불러도_예전_모양이다():
    rows = service.record_supply_history(today="2026-09-29")
    assert set(rows[-1]) == {"date", "zero", "total"}
    rows = service.record_supply_history(today="2026-09-29", picks={"review": 5, "usepick": 30, "zzz": 1})
    assert rows[-1]["review"] == 5 and rows[-1]["usepick"] == 30 and "zzz" not in rows[-1]
    assert len(rows) == 1, "같은 날은 덮어쓴다"


def test_supply_picks_는_홈_카드와_같은_함수로_센다(monkeypatch):
    monkeypatch.setattr(service, "lifecycle_partition", lambda rows=None: {
        "review": 7, "usepick": 31, "usepick_now": 17, "upcoming30": 497})
    p = service.supply_picks()
    assert (p["review"], p["usepick"], p["usepick_now"], p["upcoming30"]) == (7, 31, 17, 497)


# ═════════════════════════════════════════════════════════════════════
# 5. 사고이력 '내차 N회' — 운영 appraisal.txt 네 예문
# ═════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("text,own,opp", [
    ("중고차이력정보보고서는 내차 1회 사고 기록이 있습니다.", 1, None),
    ("…내차 1회 및 상대차 4회의 사고 기록이 있습니다.", 1, 4),
    ("중고차 사고 이력정보보고서는 내차 8회 및 상대차 2회의 사고 기록이 있습니다.", 8, 2),
    ("- 중고차이력정보보고서는 내차 1회 및 상대차 2회의 사고 기록이 있습니다.", 1, 2),
])
def test_내차_N회_상대차_N회를_읽는다(text, own, opp):
    h = parse_insurance_history(text)
    assert h.get("own_damage") == own
    assert h.get("opp_damage") == opp


@pytest.mark.parametrize("text,own", [
    ("내차 피해 : 6건", 6), ("내차 피해 6회(19,150,135원)", 6), ("내차피해 1회", 1),
    ("보험사고이력 내차 3회(8,038,135원), 상대차 1회(6,162,733원)", 3),   # 운영 spec_remark 원문
])
def test_기존_표기도_그대로_읽는다(text, own):
    assert parse_insurance_history(text).get("own_damage") == own


@pytest.mark.parametrize("text", ["내차 수리비 1,234,000원 3회", "내차피해, 상대차 피해 없음",
                                  "내차 2대 보관", "1회 258,930원의 내차피해"])
def test_다른_문장의_숫자는_사고_건수로_읽지_않는다(text):
    assert "own_damage" not in parse_insurance_history(text)


def test_내차_8회면_건수별_감가표의_30퍼센트를_받는다():
    """2026타경30118_1 BMW 520d — 예전엔 건수를 못 읽어 단일 15%."""
    text = "중고차 사고 이력정보보고서는 내차 8회 및 상대차 2회의 사고 기록이 있습니다."
    grade, hits, _f, hist = grade_accident(text)
    assert grade == "accident" and "내차피해8회" in hits
    v = {"accident_grade": grade, "insurance_history": hist}
    assert service.accident_hit_count(v) == 8
    rate, assumed = service.use_accident_rate(v, service.load_config())
    assert (rate, assumed) == (0.30, False)


def test_재등급_경로는_저장된_요항으로_외부_요청_없이_감가를_다시_매긴다(tmp_path, monkeypatch):
    """배포 때 도는 경로: `python -m web.maint regrade-accidents` = backfill_accident_grades()(비강제).
    보험이력이 달라진 행만 다시 산정한다 — 요항 파일은 DATA_DIR/<id>/appraisal.txt."""
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    (tmp_path / "BMW_1").mkdir()
    (tmp_path / "BMW_1" / "appraisal.txt").write_text(
        "중고차 사고 이력정보보고서는 내차 8회 및 상대차 2회의 사고 기록이 있습니다.", encoding="utf-8")
    db.upsert_vehicle(V(id="BMW_1", folder_key="BMW_1", accident_grade="accident", accident_hits=["사고"],
                        insurance_history={}, photo_count=15, repair_cost=500_000))
    n = service.backfill_accident_grades()
    v = db.get_vehicle("BMW_1")
    assert n == 1
    assert v["insurance_history"] == {"own_damage": 8, "opp_damage": 2}
    assert v["breakdown"]["사고감가율"] == 0.30 and v["breakdown"]["사고표기"] == "사고 8회"
    assert v["upper_bid"] < 10_645_200, "감가가 커지면 재판매 손익분기도 내려가야 한다"
    assert service.backfill_accident_grades() == 0, "멱등 — 두 번째는 바꿀 것이 없다"


def test_재등급_미리보기는_쓰지_않고_바뀔_행을_보여_준다(tmp_path, monkeypatch, capsys):
    """파서 수정은 금전 안내를 바꾼다(PANEL-60 선례) — 배포 전에 바뀔 행을 먼저 본다."""
    from web import maint
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    (tmp_path / "BMW_1").mkdir()
    (tmp_path / "BMW_1" / "appraisal.txt").write_text(
        "중고차 사고 이력정보보고서는 내차 8회 및 상대차 2회의 사고 기록이 있습니다.", encoding="utf-8")
    db.upsert_vehicle(V(id="BMW_1", folder_key="BMW_1", accident_grade="accident", accident_hits=["사고"],
                        insurance_history={}, breakdown={"사고감가율": 0.15, "현재최저매각가": 9_800_000}))
    before = db.get_vehicle("BMW_1")
    assert maint.main(["maint", "regrade-accidents", "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    # REC-1 r2(qa F4): 출력은 service.regrade_accidents 모양 — targets·rows(행별 [전, 후]). 기본도 미리보기다.
    assert out["targets"] == 1 and out["apply"] is False and out["rows"][0]["id"] == "BMW_1"
    assert out["rows"][0]["rate"] == [0.15, 0.30]
    assert out["rows"][0]["upper_bid"][1] < out["rows"][0]["upper_bid"][0]
    assert db.get_vehicle("BMW_1") == before, "미리보기가 DB 를 썼다"


def test_관리_명령_드라이런은_요청도_쓰기도_없다(capsys):
    from web import maint
    _seed_lagging(2)
    assert maint.main(["maint", "floor-refresh-plan"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and out["requests"] == 0 and out["targets"] == 2
    assert db.get_setting("last_min_refresh") is None
