"""메모·최종입찰가 = 기기 로컬(localStorage) 전환 회귀 테스트.

서버는 memo/final_bid를 저장하지 않고 렌더하지도 않는다(다중 사용자 안전).
DB에 전역 값이 남아 있어도 어떤 응답(상세·즐겨찾기)에도 새어 나오면 안 된다.
"""
import pytest
from starlette.testclient import TestClient

LEAK_MEMO = "ZZMEMOLEAKZZ"
LEAK_BID = 98765432          # 다른 곳과 겹치지 않는 distinctive 값


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
        # 전역 DB에 남아 있는(레거시) 사용자 입력값 — 절대 렌더되면 안 됨
        "memo": LEAK_MEMO, "final_bid": LEAK_BID,
    })
    import web.app as A
    return TestClient(A.app)


_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


def test_memo_post_route_removed(app_client):
    """전역 memo 저장 POST는 제거 → 라우트 없음(익명 크로스유저 쓰기 차단)."""
    r = app_client.post("/vehicle/T1_1/memo", data={"memo": "x", "final_bid": "1"})
    assert r.status_code in (404, 405)


def test_detail_uses_client_note_form(app_client):
    """상세 입찰 메모는 클라이언트 폼(data-note-form) — 서버 POST 폼·서버 value 없음."""
    r = app_client.get("/vehicle/T1_1", headers=_PUBLIC)
    assert r.status_code == 200
    assert "data-note-form" in r.text
    assert 'action="/vehicle/T1_1/memo"' not in r.text


def test_global_memo_never_leaks(app_client):
    """DB에 전역 memo/final_bid가 있어도 어떤 화면에도 렌더되지 않는다(공개·관리자 모두).
    통화는 _won 필터로 콤마 포맷되므로 raw '98765432'와 콤마형 '98,765,432' 둘 다 검사."""
    bid_raw, bid_won = str(LEAK_BID), f"{LEAK_BID:,}"
    for headers in (_PUBLIC, _TUNNEL):
        for path in ("/vehicle/T1_1", "/watchlist?ids=T1_1", "/vehicle/T1_1/report", "/"):
            r = app_client.get(path, headers=headers)
            assert r.status_code == 200, (path, headers)
            assert LEAK_MEMO not in r.text, f"memo 누출: {path} {headers}"
            assert bid_raw not in r.text and bid_won not in r.text, f"final_bid 누출: {path} {headers}"


def test_watchlist_has_client_note_placeholders(app_client):
    """즐겨찾기 표는 memo/최종입찰가를 클라이언트 렌더용 placeholder로 둔다."""
    r = app_client.get("/watchlist?ids=T1_1")
    assert r.status_code == 200
    assert "data-note-bid" in r.text and "data-note-memo" in r.text


def test_notes_defined_in_head(app_client):
    """회귀: window.Notes는 <head>에서 정의(인라인 스크립트가 파싱 시점에 안전 참조)."""
    html = app_client.get("/vehicle/T1_1").text
    assert "window.Notes" in html
    assert html.index("window.Notes") < html.index("</head>")
