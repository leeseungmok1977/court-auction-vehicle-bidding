"""SEC-1: 상세 화면의 단건 분석 안내(?an=)는 관리자에게만 그린다.

2026-10-03 design-critic 관찰 → Steward 라이브 재현: 공개 사용자가 `/vehicle/{id}?an=<아무 문장>` 으로
접속하면 그 문장이 공식 안내 상자(앰버·info 아이콘) 안에 그려졌다. HTML 은 이스케이프되지만, 우리 도메인
링크로 거짓 안내를 퍼뜨릴 수 있다. 안내를 만드는 `analyze_one` 은 관리자 전용이므로 공개 화면엔 필요 없다.
"""
import pytest
from starlette.testclient import TestClient

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_vehicle({
        "id": "T1_1", "folder_key": "T1_1", "case_no": "2026타경1", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
        "min_sale_price": 10000000, "appraisal_value": 15000000, "fail_count": 1,
        "sale_date": "2999-01-01", "median_price": 13000000, "status": "완료",
    })
    import web.app as A
    return TestClient(A.app)


def test_public_page_does_not_render_an_query_text(client):
    r = client.get("/vehicle/T1_1", params={"an": "SPOOF이 차는 침수차입니다 010-0000-0000"}, headers=_PUBLIC)
    assert r.status_code == 200
    assert "SPOOF" not in r.text and "010-0000-0000" not in r.text


def test_admin_still_sees_analysis_notice(client):
    r = client.get("/vehicle/T1_1", params={"an": "ADMINNOTE 법원 상세가 이 물건과 달라 저장하지 않았습니다"}, headers=_TUNNEL)
    assert r.status_code == 200
    assert "ADMINNOTE" in r.text
