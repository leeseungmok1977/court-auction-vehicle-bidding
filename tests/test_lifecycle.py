"""상태 분해(라이프사이클) — 겹치지 않게 나눠 합이 총대수와 정확히 일치."""
import pytest


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _v(db, id, **kw):
    base = {"id": id, "folder_key": id, "case_no": id, "item_no": "1",
            "maker": "현대", "model": "쏘나타", "sale_date": "2999-01-01"}
    base.update(kw)
    db.upsert_vehicle(base)


def test_partition_sums_to_total(dbmod):
    from web import service
    _v(dbmod, "R1", judgment="입찰 검토 가능", median_price=1000, min_sale_price=800, mileage_km=100)
    _v(dbmod, "W1", judgment="유찰 대기", median_price=1000, min_sale_price=800, mileage_km=100)
    _v(dbmod, "W2", judgment="유찰 대기", median_price=1000, min_sale_price=800, mileage_km=100)
    _v(dbmod, "L1", judgment="시세 신뢰도 낮음, 수동 검토", median_price=500, mileage_km=100)
    _v(dbmod, "N1", judgment="낙찰", auction_result="낙찰", winning_price=1200,
       min_sale_price=800, sale_date="2020-01-01", median_price=1000)
    _v(dbmod, "O1", judgment="입찰 보류", median_price=500, mileage_km=100)   # 기타
    p = service.lifecycle_partition()
    assert p["review"] + p["wait"] + p["lowconf"] + p["won"] + p["other"] == p["total"]
    assert p["total"] == 6
    assert p["won"] == 1 and p["wait"] == 2 and p["lowconf"] == 1 and p["other"] == 1


def test_reconcile_won_judgment(dbmod):
    from web import service
    # 낙찰인데 판정이 '유찰 대기'로 잘못 남음 → 정합화로 '종결'
    _v(dbmod, "N1", auction_result="낙찰", winning_price=1200, min_sale_price=800,
       sale_date="2020-01-01", median_price=1000, judgment="유찰 대기")
    n = service.reconcile_won_judgment()
    assert n == 1
    assert dbmod.get_vehicle("N1")["judgment"] == "종결"
    # 정합화 후: 유찰 대기에 안 잡히고 낙찰로만 잡힘(겹침 해소)
    p = service.lifecycle_partition()
    assert p["wait"] == 0 and p["won"] == 1
