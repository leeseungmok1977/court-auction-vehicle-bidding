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
    # 2026-09-20 2차: 칸 배정 기준이 **judgment 컬럼 → bid_state** 로 바뀌었다.
    # 예전 기대값(wait 2·lowconf 1·other 1)은 저장된 옛 분석 결과를 그대로 믿은 숫자다.
    # 운영 교차표에서 그 기준이 카드 배지와 어긋나 있었다 — '신뢰도 낮음' 257건 중 진짜
    # lowconf 는 67건뿐이었다. 그래서 숫자를 다시 박지 않고 **어느 물건이 왜 그 칸인지**를
    # 적는다(숫자만 고치면 다음에 또 무슨 뜻이었는지 알 수 없다).
    #   R1 판정=검토 가능(큐레이션 칸이 먼저 가져감) · N1 낙찰 · O1 '입찰 보류'→blocked
    #   W1·W2 는 judgment 가 '유찰 대기'지만 판정은 예상낙찰가를 못 내 lowconf 다.
    b = lambda i: service.lifecycle_bucket_of(dbmod.get_vehicle(i))  # noqa: E731
    assert b("R1") == "review" and b("N1") == "won"
    assert b("O1") == "wait", "'이번 회차는 아니다'(blocked)는 유찰 대기 칸"
    assert {b("W1"), b("W2"), b("L1")} == {"lowconf"}
    assert p["other"] == 0, "뺄셈 칸이 비었다 — 모든 물건이 판정으로 설명된다"


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
