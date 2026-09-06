"""엔카/케이카 원자료 격리 회귀 테스트 (MONETIZATION_SPEC TASK-M01/M02).

비관리자 응답에는 개별 동급 매물·케이카·표본수 등 원자료가 절대 나오지 않아야 하고,
관리자에게는 보여야 한다. 소매 시세(median)·신뢰도·재판매 손익분기는 유지.
"""
import pytest
from starlette.testclient import TestClient


def test_public_view_strips_private_keeps_public():
    from web import service
    v = {"id": "x", "median_price": 13000000, "market_confidence": 72,
         "min_sale_price": 10000000, "judgment": "입찰 검토 가능",
         "comps": [{"badge": "z"}], "kcar_median": 8, "encar_total": 9,
         "sample_count": 42, "mean_price": 6, "min_price": 5, "market_cv": 0.1,
         "market_vs_appraisal": 0.9, "match_label": "연식±1", "cross_source_status": "agree",
         "breakdown": {"기준시세": 13000000, "마진": 900000, "플랫폼": "encar", "표본수": 42}}
    u = service.public_view(v, is_admin=False)
    for k in ("comps", "kcar_median", "encar_total", "sample_count", "mean_price",
              "min_price", "market_cv", "market_vs_appraisal", "match_label",
              "cross_source_status"):
        assert u.get(k) is None, f"PRIVATE 누출: {k}"   # 키는 있되 값은 None(finalize가 ''로 렌더)
    # 유지돼야 하는 '반영된 결과'
    assert u["median_price"] == 13000000 and u["market_confidence"] == 72
    assert u["judgment"] == "입찰 검토 가능"
    # breakdown은 유지하되 엔카 메타(플랫폼·표본수)만 제거, 원가항목은 유지
    assert "플랫폼" not in u["breakdown"] and "표본수" not in u["breakdown"]
    assert u["breakdown"]["마진"] == 900000 and u["breakdown"]["기준시세"] == 13000000
    # 관리자는 원본 그대로
    assert service.public_view(v, is_admin=True) is v


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
        # 엔카 원자료 — 개별 매물 badge에 verbatim 감시 문자열
        "encar_total": 99999, "sample_count": 42, "mean_price": 66660000, "min_price": 55550000,
        "market_cv": 0.19, "market_vs_appraisal": 0.87,
        "comps": [{"year": 2020, "mileage_km": 50000, "price_won": 7770000, "badge": "ZZLEAKZZ"}],
        "kcar_median": 8880000, "kcar_sample": 7,
        "cross_source_status": "agree", "cross_source_rel": 0.03,
    })
    import web.app as A
    monkeypatch.setattr(A, "_ADMIN_KEY", "testkey")
    return A, TestClient(A.app)


def _paths():
    return ["/vehicle/T1_1", "/vehicles", "/vehicle/T1_1/report"]


def test_user_responses_have_no_encar_raw(app_client):
    _, c = app_client
    for p in _paths():
        r = c.get(p)
        assert r.status_code == 200, p
        assert "ZZLEAKZZ" not in r.text, f"엔카 개별매물 누출(user): {p}"
        assert "동급 매물" not in r.text, f"동급 매물 섹션 누출(user): {p}"


def test_admin_responses_show_encar_raw(app_client):
    A, c = app_client
    ck = {"nq_admin": A._admin_token()}
    r = c.get("/vehicle/T1_1", cookies=ck)
    assert r.status_code == 200
    assert "ZZLEAKZZ" in r.text, "관리자에게 개별 동급 매물이 보여야 함"
