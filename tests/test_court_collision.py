"""사건번호 충돌 — 다른 법원의 같은 사건번호가 한 행·한 폴더로 섞이는 문제.

18인 페르소나 패널이 발견했다. 대표 물건이 '벤츠 S350 BlueTEC L' 제목에
현대 그랜저 사진 11장·연료 LPG였고, 여러 명이 심각도 5로 지적했다.

근본 원인은 `id`/`folder_key` 가 `사건번호_물건번호` 뿐이고 **법원 코드가 없다**는 것.
사건번호는 법원마다 따로 매기므로 충돌한다. 목록(가격·기일)은 A법원 것이 남고
폴더(사진·감정서)는 B법원 것이 덮어써진다.

영향: 사진·감정서가 남의 차 → 시세 매칭·예상낙찰가·상한가·사고판정이 전부 남의 차 값.
실측 2026-09-13: 1,301건 중 29건(2.2%), 진행 중 16건.
"""
import json

import pytest

from web import db, service


@pytest.fixture
def two(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "c.db")
    db.init_db()
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data" / "2026타경1_1"
    folder.mkdir(parents=True)
    # DB 행은 A법원 물건(목록에서 온 가격·기일)
    db.upsert_vehicle({
        "id": "2026타경1_1", "folder_key": "2026타경1_1", "case_no": "2026타경1",
        "item_no": "1", "court": "성남지원", "court_code": "B000251",
        "maker": "벤츠", "model": "S350 BlueTEC L", "year": 2015,
        "min_sale_price": 25_000_000, "sale_date": "2999-01-01", "status": "완료",
        "median_price": 11_300_000, "upper_bid": 7_023_000, "judgment": "입찰 검토 가능",
        "market_confidence": 52, "accident_grade": "none", "mileage_km": 161_544,
    })
    # 그런데 저장된 상세는 B법원의 다른 차
    (folder / "d.json").write_text(json.dumps({
        "court_code": "B250826", "case_no": "20260130000001", "item_seq": "1",
        "maker": "현대", "model": "그랜저(GRANDEUR)", "year": 2019,
    }, ensure_ascii=False), encoding="utf-8")
    return folder


def test_detects_a_court_code_mismatch(two):
    rows = service.find_court_mismatch()
    assert len(rows) == 1
    r = rows[0]
    assert r["db_court"] == "B000251" and r["file_court"] == "B250826"
    assert "벤츠" in r["db_model"] and "그랜저" in r["file_model"]


def test_matching_court_is_not_flagged(two):
    (two / "d.json").write_text(json.dumps(
        {"court_code": "B000251", "maker": "벤츠", "model": "S350 BlueTEC L"},
        ensure_ascii=False), encoding="utf-8")
    assert service.find_court_mismatch() == []


def test_quarantine_hides_it_and_wipes_the_other_cars_numbers(two):
    out = service.quarantine_court_mismatch(apply=True)
    assert out["found"] == 1 and out["quarantined"] == 1
    v = db.get_vehicle("2026타경1_1")
    assert v["status"] == "상세없음", "목록에서 숨겨지지 않는다"
    # ⚠ 숨기기만 하고 파생값을 남기면 백테스트·추천·통계로 남의 차 값이 흘러든다
    for col in ("median_price", "upper_bid", "judgment", "accident_grade",
                "market_confidence", "mileage_km"):
        assert not v[col], f"{col} 에 남의 차 값이 남았다: {v[col]}"


def test_quarantine_keeps_the_case_itself(two):
    """삭제하지 않는다 — 사건은 실재하고, id에 법원을 넣어 다시 수집하면 복구된다."""
    service.quarantine_court_mismatch(apply=True)
    v = db.get_vehicle("2026타경1_1")
    assert v is not None
    assert v["case_no"] == "2026타경1" and v["court_code"] == "B000251"
    assert v["min_sale_price"] == 25_000_000, "목록에서 온 값까지 지우면 안 된다"


def test_quarantine_is_dry_run_by_default(two):
    out = service.quarantine_court_mismatch()
    assert out["found"] == 1 and out["quarantined"] == 0
    assert db.get_vehicle("2026타경1_1")["status"] == "완료"


def test_quarantine_writes_an_audit_row(two):
    service.quarantine_court_mismatch(apply=True)
    conn = db.connect()
    rows = conn.execute("SELECT * FROM anomaly_log").fetchall()
    conn.close()
    assert len(rows) == 1 and rows[0]["action"] == "quarantined"
    assert "법원코드 불일치" in rows[0]["reasons"]


# ── 쓰기 시점 차단 (재발 방지) ───────────────────────────────────
def _listing(vid, court_code, maker, model):
    return {"id": vid, "folder_key": vid, "case_no": vid.rsplit("_", 1)[0], "item_no": "1",
            "court": "법원", "court_code": court_code, "maker": maker, "model": model,
            "year": 2020, "min_sale_price": 1_000_000, "sale_date": "2999-01-01",
            "collected_at": "2026-09-13 00:00:00"}


def test_listing_upsert_refuses_to_merge_a_different_court(tmp_path, monkeypatch):
    """같은 사건번호라도 법원이 다르면 병합하지 않는다.

    병합하면 목록(가격·기일)은 A법원, 상세(사진·감정서·시세)는 B법원이 되어
    **한 행이 두 대의 차**가 된다. 조용히 덮는 대신 예외로 올려 기록하게 한다.
    """
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "u.db")
    db.init_db()
    db.upsert_listing(_listing("2026타경7_1", "B000251", "벤츠", "S350"))

    with pytest.raises(db.CaseCollision) as e:
        db.upsert_listing(_listing("2026타경7_1", "B250826", "현대", "그랜저"))
    assert e.value.old_court == "B000251" and e.value.new_court == "B250826"

    v = db.get_vehicle("2026타경7_1")
    assert v["court_code"] == "B000251" and v["model"] == "S350", "기존 행이 덮였다"


def test_same_court_still_updates_normally(tmp_path, monkeypatch):
    """같은 법원이면 평소대로 갱신돼야 한다 — 가드가 정상 수집을 막으면 안 된다."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "u2.db")
    db.init_db()
    db.upsert_listing(_listing("2026타경8_1", "B000251", "현대", "그랜저"))
    rec = _listing("2026타경8_1", "B000251", "현대", "그랜저")
    rec["min_sale_price"] = 800_000
    db.upsert_listing(rec)
    assert db.get_vehicle("2026타경8_1")["min_sale_price"] == 800_000


def test_new_row_without_existing_court_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "u3.db")
    db.init_db()
    db.upsert_listing(_listing("2026타경9_1", "B000251", "현대", "그랜저"))
    assert db.get_vehicle("2026타경9_1") is not None
