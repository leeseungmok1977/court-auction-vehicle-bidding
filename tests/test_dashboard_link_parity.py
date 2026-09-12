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

# 대시보드 템플릿이 참조하는 키까지 채운다(실제 backtest_stats() 반환 키 기준).
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "discount_p25": 0.62, "discount_p75": 0.86, "discount_by_fail": {}, "discount_by_model": {},
      "upper_hit_rate": None, "upper_n": 0, "within10_pct": 62, "within20_pct": 96,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "history_n": 0, "model_learned": False, "pred_n": 40, "comp_pool": [],
      # accuracy_for()가 층별 오차를 내려면 실제 표본이 필요하다 — 빈 리스트면
      # 추천 게이트가 "오차를 모르면 추천하지 않는다"로 막아 픽스처가 전부 빠진다.
      "pred_pool": [{"err_pct": 8.0 + (i % 5), "maker": "현대", "model": "쏘나타",
                     "fail_count": 1, "median_price": 40_000_000, "actual": 30_000_000}
                    for i in range(40)],
      "won_total": 0}


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
        dict(base, id="U1_1", case_no="2026타경11", min_sale_price=16000000,
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
    # 페이지네이션이 실제로 생기도록 '유찰 대기'를 페이지 크기 이상으로 채운다
    # (물건이 적으면 페이지 링크가 없어 아래 테스트가 조용히 공허해진다)
    for i in range(20):
        rows.append(dict(base, id=f"WB{i}_1", case_no=f"2026타경9{i:03d}",
                         min_sale_price=39000000, appraisal_value=40000000,
                         median_price=40000000, market_confidence_label="높음",
                         judgment="유찰 대기"))
        rows.append(dict(base, id=f"LB{i}_1", case_no=f"2026타경8{i:03d}",
                         min_sale_price=10000000, appraisal_value=12000000,
                         median_price=13000000, market_confidence_label="낮음",
                         judgment="시세 신뢰도 낮음, 수동 검토"))
        # 절감액이 층 오차를 넘어야 '실사용 추천'에 든다(5회차 유의성 게이트)
        rows.append(dict(base, id=f"UB{i}_1", case_no=f"2026타경7{i:03d}",
                         min_sale_price=16000000, appraisal_value=30000000,
                         median_price=40000000, market_confidence_label="높음",
                         judgment="유찰 대기"))
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


def test_dashboard_header_number_matches_the_list(client):
    """대시보드 헤더에 렌더된 숫자 자체를 읽어 목록과 대조한다.

    lifecycle_partition()만 고치고 대시보드 라우트의 별도 total 변수를 안 고쳐
    화면에는 그대로 1320이 남아 있었다 — 측정이 아니라 **스크린샷을 눈으로 보고** 발견했다.
    그래서 이 테스트는 함수 반환값이 아니라 렌더된 HTML을 본다."""
    import re
    html = client.get("/", headers=_PUBLIC).text
    m = re.search(r"총\s*<b[^>]*>([\d,]+)</b>\s*대\s*모니터링", html)
    assert m, "헤더 총계를 못 찾음"
    assert int(m.group(1).replace(",", "")) == _list_count(client, "/vehicles")


@pytest.mark.parametrize("href", [
    "/vehicles?bucket=wait", "/vehicles?bucket=lowconf", "/vehicles?usepick=1",
])
def test_filters_survive_pagination(client, href):
    """2페이지로 넘어가도 필터가 유지돼야 한다.

    2026-09-12 디자인 검수 블로커: 실사용 추천 22건 목록에서 '2'를 누르면
    `/vehicles?sort=recent&page=2` — 필터가 통째로 빠져 전체 1167건이 나왔다.
    카드 숫자 = 목록 건수 규칙이 1페이지에서만 지켜지고 있었다."""
    import re
    html = client.get(href, headers=_PUBLIC).text
    links = re.findall(r'href="(/vehicles\?[^"]*page=\d+[^"]*)"', html)
    key = href.split("?", 1)[1].split("=")[0]
    assert links, f"{href}: 페이지 링크가 없어 이 테스트가 공허하다 — 픽스처를 늘려야 한다"
    for ln in links:
        assert key in ln, f"페이지 링크에서 {key}가 사라짐: {ln}"


def test_filter_form_keeps_bucket_and_usepick(client):
    """'적용' 버튼(폼 제출)으로도 필터가 풀리면 안 된다."""
    for href, name in (("/vehicles?bucket=wait", "bucket"), ("/vehicles?usepick=1", "usepick")):
        html = client.get(href, headers=_PUBLIC).text
        assert f'name="{name}"' in html, f"{href}: 폼에 {name} hidden input이 없다"
