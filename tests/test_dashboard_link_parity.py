"""대시보드에 적힌 숫자 = 그 숫자를 누르면 나오는 목록 건수.

2026-09-12 2회차 패널(앱품질 지적 3) 실측 — 세 곳이 어긋나 있었다:
  헤더 "총 1320대 모니터링"  → 목록 1167건   (total_vehicles()가 COUNT(*)라 숨김 물건 포함)
  카드 "유찰 대기 387대"     → 목록 469건    (카드는 usepick을 뺐는데 링크는 안 뺌)
  링크 "기타·미분석 181대"   → 목록 1320건   (?all=1이 전체 목록이었음)

1회차에 count API만 고치고 대시보드 헤더를 안 고쳐 같은 거짓말이 남았다. 그래서 이번엔
**링크를 실제로 따라가 세는** 테스트를 만든다 — 숫자만 맞추는 수정으로는 통과하지 않는다.
"""
import re

import pytest
from starlette.testclient import TestClient

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1}
    rows = [
        # 소매보다 싼 실사용 추천(유찰 대기지만 usepick으로 빠져야 함)
        dict(base, id="U1_1", case_no="2026타경11", min_sale_price=20000000,
             appraisal_value=30000000, median_price=40000000,
             market_confidence_label="높음", judgment="유찰 대기"),
        # 순수 유찰 대기(비싸서 추천 아님)
        dict(base, id="W1_1", case_no="2026타경12", min_sale_price=39000000,
             appraisal_value=40000000, median_price=40000000,
             market_confidence_label="높음", judgment="유찰 대기"),
        dict(base, id="R1_1", case_no="2026타경13", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="높음", judgment="입찰 검토 가능"),
        dict(base, id="L1_1", case_no="2026타경14", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="낮음", judgment="시세 신뢰도 낮음, 수동 검토"),
        # 기일이 지난 '입찰 검토 가능' — 목록 필터는 빼는데 버킷이 안 빼면
        # 카드 34 / 링크 17처럼 갈린다(실제로 그렇게 갈렸다).
        dict(base, id="P1_1", case_no="2026타경18", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000, sale_date="2020-01-01",
             market_confidence_label="높음", judgment="입찰 검토 가능"),
        dict(base, id="O1_1", case_no="2026타경15", min_sale_price=10000000,
             appraisal_value=12000000, judgment="입찰 보류", accident_grade="flood"),
        dict(base, id="O2_1", case_no="2026타경16", min_sale_price=10000000,
             appraisal_value=12000000, judgment="미분석", status="미분석"),
        dict(base, id="N1_1", case_no="2026타경17", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="높음", judgment="종결", auction_result="낙찰",
             winning_price=11000000),
    ]
    for r in rows:
        db.upsert_vehicle(r)
    import web.app as A
    return TestClient(A.app)


_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


def _list_count(client, href: str) -> int:
    """목록 페이지가 스스로 보고하는 총건수를 읽는다."""
    r = client.get(href, headers=_PUBLIC)
    assert r.status_code == 200, f"{href} → {r.status_code}"
    m = re.search(r'id="listCount"[^>]*>\s*([\d,]+)', r.text)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"총\s*<b[^>]*>([\d,]+)</b>\s*건", r.text)
    assert m, f"{href}: 목록 건수를 못 찾음"
    return int(m.group(1).replace(",", ""))


def test_partition_sums_to_total(client):
    from web import service
    lc = service.lifecycle_partition()
    assert (lc["won"] + lc["review"] + lc["usepick"] + lc["wait"]
            + lc["lowconf"] + lc["other"]) == lc["total"]


@pytest.mark.parametrize("key,href", [
    ("usepick", "/vehicles?usepick=1"),
    ("wait", "/vehicles?bucket=wait"),
    ("lowconf", "/vehicles?bucket=lowconf"),
    ("other", "/vehicles?bucket=other"),
    ("review", "/vehicles?judgment=입찰 검토 가능&sort=expected"),
])
def test_card_number_equals_what_the_link_opens(client, key, href):
    from web import service
    assert service.lifecycle_partition()[key] == _list_count(client, href), (
        f"카드 '{key}' 값과 링크 {href} 결과가 다르다")


def test_header_total_equals_default_list(client):
    from web import service
    assert service.lifecycle_partition()["total"] == _list_count(client, "/vehicles")


def test_count_api_agrees_with_the_list(client):
    """저장한 검색 알림이 쓰는 count API도 같은 모수를 써야 한다."""
    for href, api in (("/vehicles?bucket=wait", "/api/vehicles/count?bucket=wait"),
                      ("/vehicles?usepick=1", "/api/vehicles/count?usepick=1"),
                      ("/vehicles", "/api/vehicles/count")):
        assert client.get(api, headers=_PUBLIC).json()["total"] == _list_count(client, href), api
