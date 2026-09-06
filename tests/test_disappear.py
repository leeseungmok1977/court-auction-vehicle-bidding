"""목록이탈(변경·취하·연기) 자동 감지 — db.mark_disappeared 안전성 테스트.

핵심은 '오탐 방지': 부분/비정상 스캔이 대량의 정상 물건을 '상세없음'으로
잘못 표시하지 않아야 한다. 되돌리기(재등장→미분석)는 항상 수행돼야 한다.
"""
import pytest


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _add(db, vid, sale_date, judgment="입찰 검토 가능", status="완료", auction_result=None):
    db.upsert_vehicle({"id": vid, "folder_key": vid, "sale_date": sale_date,
                       "judgment": judgment, "status": status,
                       "auction_result": auction_result})


WIN = ("2026-09-06", "2026-10-06")   # 입찰예정 창(30일)


def test_flags_disappeared_biddable(tdb):
    _add(tdb, "A", "2026-09-10")     # 창 내 · 이번 스캔에서 관측됨 → 유지
    _add(tdb, "B", "2026-09-10")     # 창 내 · 안 보임 → 목록이탈 표시
    r = tdb.mark_disappeared({"A"}, *WIN)
    assert r["flagged"] == 1 and not r["skipped"]
    assert tdb.get_vehicle("B")["status"] == "상세없음"
    assert tdb.get_vehicle("A")["status"] == "완료"


def test_restores_reappeared(tdb):
    _add(tdb, "C", "2026-09-10", status="상세없음")   # 이탈 표시됐던 물건
    r = tdb.mark_disappeared({"C"}, *WIN)             # 이번 스캔에서 다시 보임
    assert r["restored"] == 1
    assert tdb.get_vehicle("C")["status"] == "미분석"


def test_safety_cap_skips_mass_flag(tdb):
    # 후보 30건 전부 안 보임 → guard(max(20, 20%)=20) 초과 → 표시 보류(오탐 방지)
    for i in range(30):
        _add(tdb, f"V{i}", "2026-09-10")
    r = tdb.mark_disappeared({"X"}, *WIN)             # 후보 중 아무도 관측 안 됨
    assert r["skipped"] and r["flagged"] == 0
    assert tdb.get_vehicle("V0")["status"] == "완료"   # 정상 물건 보존


def test_cap_still_restores(tdb):
    # 표시가 보류돼도 재등장 복구는 항상 수행
    for i in range(30):
        _add(tdb, f"V{i}", "2026-09-10")
    _add(tdb, "C", "2026-09-10", status="상세없음")
    r = tdb.mark_disappeared({"C"}, *WIN)
    assert r["skipped"] and r["restored"] == 1
    assert tdb.get_vehicle("C")["status"] == "미분석"


def test_empty_scan_noop(tdb):
    _add(tdb, "A", "2026-09-10")
    r = tdb.mark_disappeared(set(), *WIN)             # 빈 스캔 → 전체 미실행
    assert r["skipped"] and r["flagged"] == 0 and r["restored"] == 0
    assert tdb.get_vehicle("A")["status"] == "완료"


def test_out_of_window_not_flagged(tdb):
    _add(tdb, "F", "2026-12-01")     # 창 밖(먼 미래) · 안 보임 → 후보 아님
    r = tdb.mark_disappeared({"other"}, *WIN)
    assert r["candidates"] == 0 and r["flagged"] == 0
    assert tdb.get_vehicle("F")["status"] == "완료"


def test_sold_item_not_flagged(tdb):
    _add(tdb, "S", "2026-09-10", auction_result="낙찰")  # 낙찰 물건은 후보 제외
    r = tdb.mark_disappeared({"other"}, *WIN)
    assert r["candidates"] == 0
    assert tdb.get_vehicle("S")["status"] == "완료"
