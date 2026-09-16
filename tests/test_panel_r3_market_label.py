"""'(시세 초과)'는 예상낙찰가가 실제로 시세를 넘을 때만 붙어야 한다.

3회차 패널(2026-09-17) 지적 — 예상낙찰가 780만원이 시세중앙값 990만원의 **79%** 인데
리포트가 "약 79% (시세 초과)"라고 적고, 같은 화면 가격 스펙트럼에서는 780이 990보다
왼쪽에 찍혔다. 그림과 문장이 서로 반박했다.

원인은 리포트 템플릿이 `over_market = _st in ('over_market','blocked')` 로 묶은 것이다.
service.bid_state 는 **서로 다른 세 이유**로 그 상태를 돌려준다.
  · exp > med                    → 진짜 시세 초과
  · 예상 경쟁가가 상한선 초과      → 시세 이하인데도 over_market
  · blocked(최저가 > 손익분기)     → 시세와 무관
뒤의 둘에도 '(시세 초과)'가 붙었다. 숫자가 화면에 그대로 있는데 문장이 반대로 말하면,
사용자는 앱 전체를 검산하게 된다 — 이 앱에서 가장 비싼 종류의 오류다.
"""
import re

import pytest
from starlette.testclient import TestClient

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 최저매각가가 손익분기를 넘어 blocked/over_market 이 되지만,
    # 예상낙찰가(최저가 × 유찰 프리미엄)는 시세중앙값(1,000만) **아래**로 남는 창을 쓴다.
    # ⚠ 프리미엄은 fail_count 버킷이 아니라 실제 산정식이 정하므로(900만으로 잡았더니 1,020만이
    #    나와 전제가 깨졌다), 아래 test_fixture_really_is_a_warning_state 가 매번 전제를 검사한다.
    db.upsert_vehicle({
        "id": "M1_1", "folder_key": "M1_1", "case_no": "2026타경11", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "그랜저", "year": 2017,
        "min_sale_price": 8300000, "appraisal_value": 12000000, "fail_count": 2,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 10000000, "market_confidence": 78, "market_confidence_label": "높음",
        "sample_count": 14,
    })
    import web.app as A
    return TestClient(A.app)


def _ratio(html: str):
    """리포트 01 이 표시한 '약 N%' (예상낙찰가 ÷ 시세중앙값)."""
    m = re.search(r"예상낙찰가는\s*<b[^>]*>약\s*(\d+)%", html)
    return int(m.group(1)) if m else None


def test_fixture_really_is_a_warning_state(client):
    """픽스처가 실제로 경고 상태여야 이 테스트가 공허하지 않다."""
    from web import db, service
    v = db.get_vehicle("M1_1")
    st = service.bid_state(v, BT)
    assert st["state"] in ("blocked", "over_market"), f"경고 상태가 아니다: {st}"
    exp = service.expected_for(v, BT)
    med = service.effective_median(v)
    assert exp and med and exp <= med, f"예상낙찰가가 시세를 넘어버렸다: exp={exp}, med={med}"


def test_ceiling_exceeded_is_not_labelled_market_exceeded(client):
    """상한선·부적합 때문에 경고인 물건에 '시세 초과'라고 쓰지 않는다."""
    html = client.get("/vehicle/M1_1/report", headers=_PUBLIC).text
    assert _ratio(html) is not None, "01 에 예상낙찰가 비율이 없다 — 픽스처가 렌더되지 않았다"
    assert _ratio(html) < 100, "픽스처 전제가 깨졌다(비율이 100% 이상)"
    assert "(시세 초과)" not in html, "시세의 100% 미만인데 '(시세 초과)'가 붙었다"
    assert "소매 시세를 넘어" not in html, "시세를 넘지 않았는데 '소매 시세를 넘어'라고 적었다"


def test_tag_and_number_cannot_contradict(client):
    """어떤 물건이든 '(시세 초과)' 꼬리표와 표시된 비율은 같은 말을 해야 한다."""
    html = client.get("/vehicle/M1_1/report", headers=_PUBLIC).text
    r = _ratio(html)
    if r is not None:
        assert ("(시세 초과)" in html) == (r >= 100), (
            f"비율 {r}% 와 꼬리표가 어긋난다")
