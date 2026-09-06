"""즐겨찾기 = 기기 로컬(localStorage) 전환 회귀 테스트.

서버는 즐겨찾기 상태를 저장하지 않는다(다중 사용자 안전). /watchlist는
클라이언트가 넘긴 물건 ID 목록(ids)만 렌더하고, ids가 아예 없으면
하이드레이트 모드(로컬 ID 읽어 재요청)로 응답한다. 전역 star POST는 제거됨.
"""
import pytest
from starlette.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_vehicle({
        "id": "T1_1", "folder_key": "T1_1", "case_no": "2026타경1", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
        "min_sale_price": 10000000, "appraisal_value": 15000000, "fail_count": 1,
        "sale_date": "2999-01-01", "median_price": 13000000,
        "market_confidence": 72, "market_confidence_label": "높음",
        "judgment": "입찰 검토 가능", "status": "완료",
    })
    import web.app as A
    return TestClient(A.app)


def test_watchlist_hydrate_when_no_ids(app_client):
    """ids 파라미터가 없으면 하이드레이트 모드 — 로딩 안내 + 로컬 ID로 재요청 스크립트."""
    r = app_client.get("/watchlist")
    assert r.status_code == 200
    assert "불러오는 중" in r.text
    assert "location.replace" in r.text          # 클라이언트가 ids 붙여 재요청
    assert "2026타경1" not in r.text              # 아직 물건 렌더 안 함
    assert "아직 즐겨찾기" not in r.text          # 빈 상태로 오인 렌더 금지


def test_fav_defined_before_hydrate_uses_it(app_client):
    """회귀(blocker): window.Fav는 하이드레이트 스크립트가 Fav.csv()를 쓰기 전에,
    그리고 <head> 안에서 정의돼야 한다. (content 블록 뒤에 두면 파싱 시점에 undefined →
    항상 빈 ids로 리다이렉트 → 즐겨찾기가 절대 표시되지 않던 버그를 잡는다.)"""
    html = app_client.get("/watchlist").text
    assert "window.Fav" in html and "Fav.csv()" in html
    assert html.index("window.Fav") < html.index("Fav.csv()"), "Fav 정의가 하이드레이트 사용보다 앞서야 함"
    assert html.index("window.Fav") < html.index("</head>"), "Fav는 <head>에서 정의돼야 함"


def test_watchlist_renders_given_ids(app_client):
    """ids로 넘긴 물건만 비교 테이블에 렌더."""
    r = app_client.get("/watchlist?ids=T1_1")
    assert r.status_code == 200
    assert "2026타경1" in r.text
    assert "불러오는 중" not in r.text


def test_watchlist_empty_ids_shows_empty_state(app_client):
    """ids=""(즐겨찾기 없음) → 빈 상태 안내(하이드레이트로 되돌아가지 않음)."""
    r = app_client.get("/watchlist?ids=")
    assert r.status_code == 200
    assert "아직 즐겨찾기" in r.text
    assert "불러오는 중" not in r.text


def test_watchlist_ignores_unknown_ids(app_client):
    """존재하지 않는 ID는 조용히 제외 → 결과 없으면 빈 상태."""
    r = app_client.get("/watchlist?ids=NOPE,ALSO_NOPE")
    assert r.status_code == 200
    assert "2026타경1" not in r.text
    assert "아직 즐겨찾기" in r.text


def test_star_post_route_removed(app_client):
    """전역 star 토글 POST는 제거(다중 사용자 안전) → 라우트 없음."""
    r = app_client.post("/vehicle/T1_1/star")
    assert r.status_code in (404, 405)


def test_detail_has_client_fav_button(app_client):
    """상세 페이지 즐겨찾기 버튼은 클라이언트 토글(data-fav-btn) — 서버 POST 폼 아님."""
    r = app_client.get("/vehicle/T1_1", headers={"x-forwarded-for": "203.0.113.7"})
    assert r.status_code == 200
    assert "data-fav-btn" in r.text
    assert 'action="/vehicle/T1_1/star"' not in r.text
