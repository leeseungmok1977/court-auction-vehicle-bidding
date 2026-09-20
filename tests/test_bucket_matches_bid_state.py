"""같은 사실을 두 곳에서 따로 판정하지 않는다 — 버킷과 bid_state 의 일치.

2026-09-20 운영 실측에서 잡힌 결함. `bucket=nomarket` 목록에 든 물건을 눌러 상세로 가면
**다른 말**이 나왔다. 55건 중 34건이 그랬다.

원인은 문구가 아니라 **기준이 두 개**였다는 것이다.
  · 버킷(`_bucket_and_tier`) : `no_market_reason(v)` 를 직접 봄
  · 화면(`bid_state`)        : 그 위에 '지난 기일·침수·시동 불가' 같은 더 앞선 사실이 먼저 옴

그래서 버킷이 판정보다 느슨했고, 시세와 무관한 이유로 이미 판정이 끝난 물건까지
'건설기계·선박 등' 칸에 담겼다. 34건의 내역은 이랬다:
  지난 기일 28 · 시동 불가 2 · 침수·전손 2 · **시세가 실제로 나온 물건 2**
앞의 32건은 판정 쪽이 옳았고(시세와 무관한 더 중한 사실), 뒤의 2건은 시세가 있는데
"동급 시세 없음"이라 부를 뻔했다 — 거짓말이 될 뻔한 쪽이다.

이 앱은 "판정은 bid_state 한 곳에서만 내리고 화면은 그 결과를 그린다"를 규칙으로 삼는다
(service.py 의 BID_STATES 주석). 버킷도 화면이다. 그래서 여기서 **두 기준의 일치를 고정**한다.
문구를 맞추는 테스트가 아니라 **기준이 갈라지는 것 자체를 막는** 테스트다.
"""
import pytest

from web import db, service
from tests.test_personal_use import BT


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    return db


def _v(dbmod, vid, **kw):
    base = {"id": vid, "folder_key": vid, "case_no": f"2026타경{abs(hash(vid)) % 90000 + 1000}",
            "item_no": "1", "maker": "현대", "model": "굴착기", "sale_date": "2999-01-01",
            "mileage_km": 50000, "photo_count": 3, "status": "완료",
            "min_sale_price": 10_000_000, "appraisal_value": 12_000_000}
    base.update(kw)
    dbmod.upsert_vehicle(base)
    return dbmod.get_vehicle(vid)


def test_버킷과_판정이_같은_말을_한다(dbmod):
    """두 기준이 갈라지면 목록과 상세가 다른 말을 한다 — 그것 자체를 막는다."""
    rows = [
        _v(dbmod, "NM1"),                                                   # 순수 비교 대상 없음
        _v(dbmod, "PAST", sale_date="2020-01-01"),                          # 지난 기일이 더 앞선 사실
        _v(dbmod, "FLOOD", accident_grade="flood"),                         # 침수가 더 앞선 사실
        _v(dbmod, "DEAD", runnable="no"),                                   # 시동 불가가 더 앞선 사실
        _v(dbmod, "HASMKT", median_price=13_000_000,                        # 시세가 실제로 있다
           market_confidence_label="높음"),
        _v(dbmod, "CAR", model="쏘나타", median_price=13_000_000,            # 평범한 승용차
           market_confidence_label="높음"),
    ]
    for r in rows:
        bucket = service.lifecycle_bucket_of(r, BT)
        state = service.bid_state(r, BT)["state"]
        assert (bucket == "nomarket") == (state == "nomarket"), (
            f"{r['model']}({r['id']}): 버킷={bucket} 인데 판정={state} — "
            f"목록과 상세가 다른 말을 하게 된다")


def test_시세가_있으면_비교대상_없음_칸에_넣지_않는다(dbmod):
    """실측 2건: median 1,010만·789만인 물건이 '동급 시세 없음' 칸에 있었다 — 거짓말이다."""
    r = _v(dbmod, "HAS", model="덤프트럭", median_price=7_890_000,
           market_confidence_label="높음")
    assert service.lifecycle_bucket_of(r, BT) != "nomarket"


def test_지난_기일은_비교대상_없음보다_앞선_사실이다(dbmod):
    """입찰할 수 없는 물건에 '동급 시세가 없다'고 말하는 건 초점이 어긋난다."""
    r = _v(dbmod, "OLD", sale_date="2020-01-01")
    assert service.bid_state(r, BT)["state"] == "wait"
    assert service.lifecycle_bucket_of(r, BT) != "nomarket"


def test_라이프사이클_합계가_여전히_총대수와_같다(dbmod):
    """버킷 판정을 bid_state 로 바꿨다 — 배타·망라가 깨지면 KPI 합계가 어긋난다."""
    for i, kw in enumerate(({}, {"sale_date": "2020-01-01"}, {"accident_grade": "flood"},
                            {"model": "쏘나타", "median_price": 13_000_000,
                             "market_confidence_label": "높음"})):
        _v(dbmod, f"S{i}", **kw)
    p = service.lifecycle_partition()
    assert (p["review"] + p["usepick"] + p["wait"] + p["nomarket"]
            + p["lowconf"] + p["won"] + p["other"]) == p["total"]
