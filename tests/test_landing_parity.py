# -*- coding: utf-8 -*-
"""소개 페이지와 홈이 **같은 수**를 말하는가 — 첫인상에서 갈리면 안 된다.

2026-09-22 실측. 같은 앱 안에서 같은 뜻의 숫자가 화면마다 달랐다:

    소개(/landing)  1,455건 분석 중 · 낙찰 423건 · 예상 오차 ±9%
    홈(/)           총 1,278대 · 낙찰·종결 413
    적중률(/accuracy)                    검증 249건 · ±9.3%

원인은 소개 페이지만 `len(db.list_vehicles())`로 **따로 센 것**이다(홈은
`hide_incomplete=True` 후 `lifecycle_partition`). 오차도 소개만 `round()`해서
±9 와 ±9.3 으로 갈렸다.

이게 왜 최우선이었나: 마케팅 진단에서 나온 개선안 대부분이 **이 숫자들을 첫 화면·공유
카드·검색결과로 더 크게, 더 멀리 실어 나르는 일**이었다. 바닥이 어긋난 채 확성기를 물리면
늘어나는 건 신뢰가 아니라 "어느 게 맞나"다. 이 앱이 파는 것은 차가 아니라 정직이다.

`tests/test_dashboard_link_parity.py`가 '대시보드 숫자 = 링크를 눌러 센 수'를 고정하듯,
이 파일은 '소개 숫자 = 홈 숫자'를 고정한다.
"""
import re

import pytest
from starlette.testclient import TestClient

BT = {"discount_median": 0.74, "mae_pct": 9.3, "sample": 172, "pred_n": 249,
      "within10_pct": 61, "within20_pct": 95, "history_n": 244,
      "min_premium_median": 1.13, "min_premium_by_fail": {}, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "model_learned": False, "comp_pool": [], "pred_pool": [], "won_total": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
            "photo_count": 3, "mileage_km": 50_000}
    rows = [
        dict(base, id="A1", case_no="2026타경1", min_sale_price=16_000_000,
             median_price=40_000_000, market_confidence_label="높음", judgment="유찰 대기"),
        dict(base, id="A2", case_no="2026타경2", min_sale_price=20_000_000,
             median_price=30_000_000, market_confidence_label="높음",
             judgment="입찰 검토 가능"),
        dict(base, id="W1", case_no="2026타경3", min_sale_price=10_000_000,
             median_price=14_000_000, market_confidence_label="높음",
             auction_result="낙찰", winning_price=12_000_000, sale_date="2026-08-01"),
        # ★ 숨김 대상(상세없음) — 소개가 이걸 세면 홈보다 큰 수가 나온다. 갈림의 원인이었다.
        {"id": "H1", "case_no": "(중복)_9", "item_no": "1", "status": "상세없음",
         "court": "수원지방법원", "sale_date": "2999-01-01"},
    ]
    for r in rows:
        db.upsert_vehicle(r)
    from web.app import app
    with TestClient(app) as c:
        yield c


def _num(html: str, pattern: str):
    m = re.search(pattern, html)
    return m.group(1).replace(",", "") if m else None


def test_소개와_홈이_같은_총대수를_말한다(client):
    """★ 랜딩 1455 · 홈 1278 이 동시에 떠 있던 것을 막는다."""
    home = client.get("/").text
    land = client.get("/landing").text
    h = _num(home, r"총 <b[^>]*>([\d,]+)")
    l = _num(land, r'text-3xl font-bold font-mono">([\d,]+)</div><div[^>]*>전국 물건 분석')
    assert h and l, f"총 대수를 찾지 못했다 (홈={h}, 소개={l})"
    assert h == l, f"홈은 {h}건, 소개는 {l}건이라고 말한다 — 첫인상에서 갈린다"


def test_숨긴_물건을_소개가_몰래_세지_않는다(client):
    """'상세없음'은 목록에 안 나오는데 소개만 세면 눌러 들어갔을 때 수가 줄어든다."""
    land = client.get("/landing").text
    l = _num(land, r'text-3xl font-bold font-mono">([\d,]+)</div><div[^>]*>전국 물건 분석')
    assert l == "3", f"숨김 1건을 포함해 {l}건으로 셌다 — 목록과 모수가 다르다"


def test_오차_표기가_적중률_페이지와_같다(client):
    """소개만 반올림해 ±9%, 적중률은 ±9.3% 였다 — 같은 값을 두 번 말하지 않는다."""
    land = client.get("/landing").text
    acc = client.get("/accuracy").text
    lm = re.search(r"±([\d.]+)%", land)
    assert lm, "소개 페이지에서 오차 표기를 찾지 못했다"
    assert lm.group(1) == str(BT["mae_pct"]), (
        f"소개는 ±{lm.group(1)}% 인데 실제 오차는 ±{BT['mae_pct']}% 다 — 반올림하지 않는다")
    # ⚠ 아무 ± 나 집으면 안 된다 — 적중률 페이지에는 저감률 등 다른 ± 수치도 있어서
    #   처음엔 '±30%'를 오차로 잘못 집었다(2026-09-22). '평균 오차' 라벨 뒤를 본다.
    am = re.search(r"평균 오차.{0,200}?±([\d.]+)", acc, re.S)
    assert am, "적중률 페이지에서 '평균 오차' 타일을 찾지 못했다"
    assert am.group(1) == lm.group(1), (
        f"소개 ±{lm.group(1)}% vs 적중률 ±{am.group(1)}% — 같은 값이어야 한다")


def test_검증_건수는_누적_낙찰이_아니라_대조한_건수다(client):
    """'낙찰 이력 423건'과 '실제로 대조한 249건'은 다른 수다. 뭉치면 무엇이 검증인지 모른다."""
    land = client.get("/landing").text
    assert str(BT["pred_n"]) in land, "실제 대조 건수가 소개 페이지에 없다"
    assert "낙찰 이력" in land, "누적 낙찰을 '검증'이라 부르면 과대주장이 된다"


def test_about_주소로도_소개가_열린다(client):
    """소개를 /about 으로 찾는 사람이 많았고 404였다(2026-09-22 실측)."""
    r = client.get("/about")
    assert r.status_code == 200, f"/about 이 {r.status_code}"
    assert "얼마에 낙찰될지" in r.text, "/about 이 소개 페이지가 아니다"


def test_홈_첫_화면이_이_앱이_무엇인지_말한다(client):
    """방문자의 67%가 1페이지만 보고 나갔는데, 첫 화면에 설명이 한 줄도 없었다."""
    home = client.get("/").text
    assert "얼마 쓰면 되는지" in home, "홈 첫 화면의 가치제안 한 줄이 사라졌다"
    assert "/landing" in home, "소개로 가는 길이 첫 화면에서 사라졌다"
