"""일일 갱신 최종 검토 — 이상 낙찰 재확인 후 복원(resolved) / 등록 보류(quarantined) + 감사기록."""
import pytest


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _anom_vehicle(db):
    # 이상 낙찰: 낙찰가(100) < 최저매각가(1000) + 매각기일 미래
    db.upsert_vehicle({
        "id": "A_1", "folder_key": "A_1", "case_no": "2026타경1", "item_no": "1",
        "doc_id": "docid-x", "court_code": "X", "maker": "현대", "model": "쏘나타",
        "auction_result": "낙찰", "winning_price": 100, "min_sale_price": 1000,
        "sale_date": "2999-01-01", "status": "종결", "judgment": "종결",
    })


def test_review_resolves_when_recheck_clears(dbmod, monkeypatch):
    from web import service
    _anom_vehicle(dbmod)
    # 재확인이 '낙찰 아님(진행중)'으로 정정된 rec 반환 → 정상화 → 복원
    fixed = {"id": "A_1", "folder_key": "A_1", "case_no": "2026타경1", "item_no": "1",
             "auction_result": None, "winning_price": None, "min_sale_price": 1000,
             "sale_date": "2999-01-01", "status": "미분석"}
    monkeypatch.setattr(service, "_sa_no_from_docid", lambda d: "SA")
    monkeypatch.setattr(service, "_rebuild_item", lambda v: None)
    monkeypatch.setattr(service, "_analyze_item", lambda *a, **k: fixed)
    out = service.review_daily_anomalies(None, None, {})
    assert out["found"] == 1 and out["resolved"] == 1 and out["quarantined"] == 0
    assert dbmod.get_vehicle("A_1").get("auction_result") is None      # 오염 낙찰 제거(복원)
    logs = dbmod.list_anomalies()
    assert logs and logs[0]["action"] == "resolved"


def test_review_quarantines_when_still_anomalous(dbmod, monkeypatch):
    from web import service
    _anom_vehicle(dbmod)
    # 재확인해도 여전히 이상(낙찰가<최저가) → 등록 보류(저장 안 함) + 기록
    still_bad = {"id": "A_1", "auction_result": "낙찰", "winning_price": 100,
                 "min_sale_price": 1000, "sale_date": "2999-01-01"}
    monkeypatch.setattr(service, "_sa_no_from_docid", lambda d: "SA")
    monkeypatch.setattr(service, "_rebuild_item", lambda v: None)
    monkeypatch.setattr(service, "_analyze_item", lambda *a, **k: still_bad)
    out = service.review_daily_anomalies(None, None, {})
    assert out["quarantined"] == 1 and out["resolved"] == 0
    # 기존 오염 낙찰이 그대로 남아(등록 보류) → 목록 가드가 계속 숨김
    assert dbmod.get_vehicle("A_1").get("auction_result") == "낙찰"
    logs = dbmod.list_anomalies()
    assert logs and logs[0]["action"] == "quarantined"


def test_review_no_anomaly_no_action(dbmod, monkeypatch):
    from web import service
    dbmod.upsert_vehicle({"id": "OK_1", "folder_key": "OK_1", "case_no": "2026타경2",
                          "auction_result": "낙찰", "winning_price": 2000,
                          "min_sale_price": 1000, "sale_date": "2020-01-01"})
    out = service.review_daily_anomalies(None, None, {})
    assert out["found"] == 0 and out["reviewed"] == 0
