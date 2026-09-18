"""상태 분해(라이프사이클) — 겹치지 않게 나눠 합이 총대수와 정확히 일치."""
import pytest


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _v(db, id, **kw):
    # case_no는 실제 형식(YYYY타경N)이어야 한다 — 공개 목록이 '(중복)' 같은 비정형
    # 사건번호를 거르기 때문에, id를 그대로 쓰면 픽스처가 통째로 숨겨진다.
    base = {"id": id, "folder_key": id, "case_no": f"2026타경{abs(hash(id)) % 90000 + 1000}",
            "item_no": "1",
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
    # 칸을 하나라도 빠뜨리면 합계가 조용히 어긋난다 — 전 칸을 명시적으로 더한다.
    assert (p["review"] + p["usepick"] + p["wait"] + p["nomarket"]
            + p["lowconf"] + p["won"] + p["other"]) == p["total"]
    assert p["total"] == 6
    assert p["won"] == 1 and p["wait"] == 2 and p["lowconf"] == 1 and p["other"] == 1


def test_끝난_물건은_시세비교대상아님_칸에_들어가지_않는다(dbmod):
    """이 칸은 **앞으로 입찰할 수 있는** 물건만 담아야 한다.

    2026-09-19 실측: 칸을 넣고 운영 데이터에 대입하니 109건 중 53건이 '종결'이었다.
    won 버킷이 auction_result='낙찰'만 보기 때문에, 판정만 '종결'인 물건이 이 분기에
    가로채인 것이다. 사용자가 칸을 눌렀을 때 끝난 경매가 절반이면 칸이 거짓말을 한다.
    단위 테스트로는 못 잡혔다 — 판별 함수 자체는 종결 여부를 모르기 때문이다.
    """
    from web import service
    _v(dbmod, "H1", model="굴착기", judgment="시세 신뢰도 낮음, 수동 검토",
       mileage_km=100, photo_count=3)
    _v(dbmod, "H2", model="굴착기", judgment="종결", mileage_km=100, photo_count=3)
    _v(dbmod, "H3", model="굴착기", judgment="유찰 대기", auction_result="낙찰",
       winning_price=1200, min_sale_price=800, sale_date="2020-01-01",
       mileage_km=100, photo_count=3)
    p = service.lifecycle_partition()
    assert p["nomarket"] == 1, "끝난 물건(종결·낙찰)이 새 칸에 섞였다"
    assert p["total"] == 3


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
