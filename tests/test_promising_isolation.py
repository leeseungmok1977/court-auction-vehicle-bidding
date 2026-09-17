"""promising_rows 가 넘겨받은 행을 오염시키지 않는다 + 재사용 경로가 자체 조회와 같은 결과를 낸다.

배경(2026-09-18): 홈 한 요청에서 list_vehicles 가 6회 돌았고, 그중 lifecycle_partition 의
첫 적재와 promising_rows 가 **완전히 같은 질의**였다(hide_incomplete=True, 각각 누적 0.53·0.58초).
한 번만 읽어 둘에 넘기되, promising_rows 는 행에 직접 쓰므로(v["use_tier"], v.update(...))
공유하면 라이프사이클 집계가 보는 행이 오염된다 → 얕은 복사로 격리했다.

이 테스트가 고정하는 것:
  ① 공유 행의 최상위 6개 필드가 호출 뒤에도 생기지 않는다(오염 없음)
  ② 중첩 객체(JSON 컬럼)도 제자리에서 바뀌지 않는다 — 얕은 복사의 유일한 빈틈이라 명시적으로 검사
  ③ rows 를 넘긴 결과 == 넘기지 않은 결과(같은 물건, 같은 순서)
  ④ within_days 를 함께 주면 모수가 다르므로 재사용하지 않는다

②가 깨지면 얕은 복사로는 부족하다는 뜻이다 — 그때는 복사 범위를 다시 설계해야 한다.
"""
import copy

import pytest

MUTATED = ("use_tier", "expected_win", "pick_kind", "pick_label", "pick_disc", "pick_score")

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 유망 물건으로 뽑힐 만한 물건 + 그렇지 않은 물건을 섞는다.
    for i, (mid, med, floor, judg) in enumerate([
        ("A_1", 12000000, 6000000, "입찰 검토 가능"),
        ("B_1", 9000000, 5000000, "유찰 대기"),
        ("C_1", 8000000, 7600000, "유찰 대기"),
    ]):
        db.upsert_vehicle({
            "id": mid, "folder_key": mid, "case_no": f"2026타경{100+i}", "item_no": "1",
            "court": "수원지방법원", "maker": "기아", "model": "쏘렌토", "year": 2019,
            "min_sale_price": floor, "appraisal_value": int(med * 1.05), "fail_count": 1,
            "sale_date": "2999-01-01", "status": "완료", "judgment": judg,
            "median_price": med, "market_confidence": 85, "market_confidence_label": "높음",
            "sample_count": 12, "mileage_km": 90000, "photo_count": 5,
            "comps": [{"price": med, "src": "x"}],          # 중첩 가변 객체(얕은 복사의 빈틈)
            "photo_order": ["a.jpg", "b.jpg"],
        })
    return service


def test_shared_rows_are_not_polluted(svc):
    """공유 행에 promising_rows 의 계산 결과가 남으면 안 된다 — 라이프사이클 집계가 같은 행을 본다."""
    from web import db
    rows = db.list_vehicles(hide_incomplete=True)
    assert rows, "픽스처가 비었다 — 테스트가 공허해진다"
    snapshot = copy.deepcopy(rows)
    svc.promising_rows(BT, rows=rows)
    for before, after in zip(snapshot, rows):
        for k in MUTATED:
            assert k not in after or after.get(k) == before.get(k), (
                f"공유 행이 오염됐다: {after.get('id')} 의 {k}")


def test_nested_objects_are_not_mutated_in_place(svc):
    """얕은 복사의 유일한 빈틈 — 중첩 리스트·dict 가 제자리에서 바뀌면 격리가 깨진다."""
    from web import db
    rows = db.list_vehicles(hide_incomplete=True)
    snapshot = copy.deepcopy(rows)
    svc.promising_rows(BT, rows=rows)
    for before, after in zip(snapshot, rows):
        assert before.get("comps") == after.get("comps"), "comps 가 제자리에서 바뀌었다"
        assert before.get("photo_order") == after.get("photo_order"), "photo_order 가 바뀌었다"


def test_reused_rows_give_the_same_result(svc):
    """재사용 경로와 자체 조회 경로가 같은 물건을 같은 순서로 내야 한다."""
    from web import db
    rows = db.list_vehicles(hide_incomplete=True)
    a = svc.promising_rows(BT, rows=rows)
    b = svc.promising_rows(BT)
    assert [x["id"] for x in a] == [x["id"] for x in b]
    for x, y in zip(a, b):
        for k in MUTATED:
            assert x.get(k) == y.get(k), f"{x['id']} 의 {k} 가 경로에 따라 다르다"


def test_within_days_does_not_reuse_rows(svc):
    """within_days 가 오면 모수가 달라지므로 넘겨받은 행을 쓰면 안 된다."""
    from web import db
    rows = db.list_vehicles(hide_incomplete=True)
    called = {"n": 0}
    real = db.list_vehicles

    def spy(*a, **k):
        called["n"] += 1
        return real(*a, **k)

    import web.service as S
    orig = S.db.list_vehicles
    S.db.list_vehicles = spy
    try:
        svc.promising_rows(BT, rows=rows, within_days=30)
    finally:
        S.db.list_vehicles = orig
    assert called["n"] == 1, "within_days 가 있는데 넘겨받은 행을 그대로 썼다"
