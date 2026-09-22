# -*- coding: utf-8 -*-
"""공유 미리보기 카드에 **박제되면 거짓이 되는 값**을 싣지 않는다.

2026-09-22. 링크를 카톡에 붙여도 제목·썸네일이 안 떴고(og 0건) 공유 버튼조차 없었다.
그래서 og 를 넣었는데, 논쟁에서 전문가 넷이 **전원 같은 경고**를 했다:

    "미리보기 카드는 캐시되어 박제되는데 가격은 바뀐다. 게다가 화면의 예상낙찰가 중 24%는
     예측이 아니라 법원 최저가를 그대로 복사한 값이고, 그 사정을 알리는 11px 회색 글씨는
     카드로 따라가지 않는다. 맥락이 잘린 숫자가 곧 과장이다."

그래서 카드에는 **법원 공시 사실만** 싣는다. 최저매각가만 예외인 이유는 틀리는 방향이
하나뿐이기 때문이다 — 회차 안에서 불변이고 유찰되면 내려가기만 해서, 낡은 카드는
'실제보다 비싸게' 적힌 쪽으로만 틀리고 들어온 사람은 화면에서 더 싼 값을 본다.

이 파일이 지키는 것:
  (1) 판단값(예상낙찰가·입찰 상한·시세·적중률)이 카드에 없다
  (2) 상대 날짜(D-6)가 없다 — 캐시된 순간 거짓이 된다
  (3) 끝난 경매는 제목이 그렇게 말한다
  (4) 주소·이미지가 절대 주소다(상대 주소는 무시된다)
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
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "og.db")
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타(SONATA)", "item_no": "1",
            "year": 2020, "status": "완료", "photo_count": 3, "mileage_km": 50_000,
            "median_price": 14_000_000, "min_sale_price": 9_000_000, "fail_count": 2}
    db.upsert_vehicle(dict(base, id="LIVE1", case_no="2026타경7", sale_date="2999-01-01"))
    db.upsert_vehicle(dict(base, id="DONE1", case_no="2026타경8", sale_date="2020-05-01",
                           auction_result="낙찰", winning_price=10_000_000))
    from web.app import app
    with TestClient(app) as c:
        yield c


def _og(html: str, prop: str):
    m = re.search(rf'<meta property="og:{prop}" content="([^"]*)"', html)
    return m.group(1) if m else None


def test_카드에_법원_공시_사실이_담긴다(client):
    h = client.get("/vehicle/LIVE1").text
    t, d = _og(h, "title"), _og(h, "description")
    assert t and d, f"og 가 없다 (title={t}, desc={d})"
    assert "2026타경7" in t and "수원지방법원" in t, f"사건 식별이 없다: {t}"
    assert "9,000,000" in d or "900만" in d, f"최저매각가가 없다: {d}"
    assert "2999-01-01" in d, f"매각기일(절대 날짜)이 없다: {d}"
    assert "유찰 2회" in d, f"유찰 횟수가 없다: {d}"


def test_박제되면_거짓이_되는_값은_싣지_않는다(client):
    """★ 전문가 4인이 전원 같은 이유로 막은 것이다."""
    h = client.get("/vehicle/LIVE1").text
    card = " ".join(filter(None, [_og(h, "title"), _og(h, "description")]))
    for bad in ("예상낙찰가", "입찰 상한", "적중", "오차", "시세"):
        assert bad not in card, f"카드에 '{bad}' 가 실렸다 — 캡션 없이 박제된다: {card}"
    assert not re.search(r"\bD-\d", card), f"상대 날짜가 실렸다 — 캐시되면 거짓이 된다: {card}"


def test_끝난_경매는_제목이_그렇게_말한다(client):
    """검색·공유로 들어온 사람이 입찰할 수 있다고 오해하면 안 된다."""
    h = client.get("/vehicle/DONE1").text
    t = _og(h, "title")
    assert t and t.startswith("[매각 종료]"), f"종료 표시가 없다: {t}"


def test_주소와_이미지가_절대주소다(client):
    h = client.get("/vehicle/LIVE1").text
    for prop in ("url", "image"):
        u = _og(h, prop)
        assert u and u.startswith("http"), f"og:{prop} 가 절대 주소가 아니다: {u}"
    m = re.search(r'<link rel="canonical" href="([^"]*)"', h)
    assert m and m.group(1).startswith("http"), f"canonical 이 절대 주소가 아니다: {m}"


def test_리포트도_같은_규칙을_따른다(client):
    """리포트는 base.html 을 상속하지 않는 독립 문서라 og 를 따로 쓴다 — 규칙이 갈리면
    같은 물건이 두 경로로 공유될 때 서로 다른 말을 하게 된다."""
    h = client.get("/vehicle/LIVE1/report").text
    t, d = _og(h, "title"), _og(h, "description")
    assert t and d, f"리포트에 og 가 없다 (title={t}, desc={d})"
    assert "2026타경7" in t, f"사건 식별이 없다: {t}"
    card = t + " " + d
    for bad in ("예상낙찰가", "입찰 상한", "적중", "오차"):
        assert bad not in card, f"리포트 카드에 '{bad}' 가 실렸다: {card}"
    assert not re.search(r"\bD-\d", card), f"상대 날짜가 실렸다: {card}"
    u = _og(h, "url")
    assert u and u.startswith("http"), f"리포트 og:url 이 절대 주소가 아니다: {u}"


def test_리포트도_끝난_경매를_밝힌다(client):
    h = client.get("/vehicle/DONE1/report").text
    t = _og(h, "title")
    assert t and t.startswith("[매각 종료]"), f"리포트에 종료 표시가 없다: {t}"


def test_공유_버튼이_있고_뒤로가_살아_있다(client):
    """'뒤로'는 필터를 걸고 들어온 목록으로 되돌리는 일을 겸한다 — 없애지 않는다."""
    h = client.get("/vehicle/LIVE1").text
    assert "navigator.share" in h, "공유 수단이 없다"
    assert "_goBack" in h and "뒤로" in h, "'뒤로'가 사라졌다"
