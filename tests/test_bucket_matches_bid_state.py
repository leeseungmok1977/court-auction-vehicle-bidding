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


# ── 2026-09-20 2차: nomarket 하나만 맞춰 놓았더니 나머지가 그대로 어긋나 있었다 ──────
#
# 운영 교차표(목록 1,244건)를 떠 보고 알았다. '신뢰도 낮음' 칸 257건 중 판정이 실제로
# lowconf 인 것은 67건뿐이고, 184건은 '유찰 대기', 6건은 '이번 회차 부적합'이었다.
# 거꾸로 '유찰 대기' 505건 안에는 lowconf 93건이 섞여 있었다. 칸 이름과 카드 배지가
# 같은 물건에 대해 다른 말을 한 것이다 — 9/20 오전에 nomarket 에서 고친 바로 그 결함이
# 다른 칸에 남아 있었다. 그래서 대응표를 **전 상태에 대해** 고정한다.
BUCKET_OF_STATE = {
    "nomarket": "nomarket",
    "lowconf": "lowconf",
    "wait": "wait",
    "blocked": "wait",        # '이번 회차 입찰 부적합' — 뜻이 "이번 회차는 아니다"로 같다
    "over_market": "wait",    # '시세 초과' — 마찬가지
}
# 앞선 분기(낙찰·큐레이션·실사용 갈래)가 먼저 가져가는 칸. 이 칸에 들어간 물건은
# 판정과 무관하게 배정되므로 대응표의 적용 대상이 아니다.
_CLAIMED_FIRST = ("won", "review", "usepick")


def test_모든_상태에서_칸과_판정이_같은_말을_한다(dbmod):
    rows = [
        _v(dbmod, "NM", model="굴착기"),                                    # nomarket
        _v(dbmod, "PAST", model="쏘나타", sale_date="2020-01-01"),           # wait(지난 기일)
        _v(dbmod, "FLOOD", model="쏘나타", accident_grade="flood"),          # blocked
        _v(dbmod, "DEAD", model="쏘나타", runnable="no"),                    # lowconf
        _v(dbmod, "NOMED", model="쏘나타", median_price=None),               # lowconf(시세 없음)
        _v(dbmod, "LOWC", model="쏘나타", median_price=13_000_000,           # lowconf(진짜)
           market_confidence_label="낮음"),
        _v(dbmod, "STALE", model="쏘나타", median_price=18_000_000,          # 저감가 미공고
           market_confidence_label="높음", appraisal_value=20_000_000,
           min_sale_price=20_000_000, fail_count=1),
        _v(dbmod, "OK", model="쏘나타", median_price=13_000_000,             # 평범한 승용차
           market_confidence_label="높음"),
    ]
    for r in rows:
        bucket = service.lifecycle_bucket_of(r, BT)
        if bucket in _CLAIMED_FIRST:
            continue
        state = service.bid_state(r, BT)["state"]
        assert bucket == BUCKET_OF_STATE.get(state, "other"), (
            f"{r['id']}({r['model']}): 판정={state} 인데 칸={bucket} — "
            f"칸 이름과 카드 배지가 다른 말을 하게 된다")


def test_저감가_미공고를_신뢰도_탓으로_돌리지_않는다(dbmod):
    """실측 74건. 신뢰도 높음 49·보통 25, 표본 수 중앙값 19 — 시세는 멀쩡했다.

    유찰됐는데 법원이 저감가를 아직 공고하지 않으면 예상낙찰가를 **일부러** 내지 않는다
    (낡은 출발선으로 만든 예측은 지어낸 값이라서다). 그건 시세를 못 믿겠다는 뜻이 아니다.
    상세 화면은 이미 "다음 기일 최저가가 공고되면 자동 반영됩니다"라고 정확히 말하고
    있었는데 목록 카드만 "시세 신뢰도 낮음"이라고 했다 — 74건 전부 기일이 남은,
    사용자가 지금 실제로 검토하는 물건이었다."""
    r = _v(dbmod, "SF", model="쏘나타", median_price=18_000_000,
           market_confidence_label="높음", sample_count=19,
           appraisal_value=20_000_000, min_sale_price=20_000_000, fail_count=1)
    st = service.bid_state(r, BT)
    assert st["exp"] is None, "저감가 미공고면 예상낙찰가는 내지 않는다(기존 설계)"
    assert st["state"] == "wait"
    assert "신뢰도" not in st["label"], f"신뢰도 탓을 하고 있다: {st['label']}"
    assert service.lifecycle_bucket_of(r, BT) == "wait"


def test_신뢰도가_실제로_낮으면_그대로_신뢰도_낮음이다(dbmod):
    """고치면서 반대쪽을 지우면 안 된다 — 진짜 신뢰도 낮음 36건은 그대로 남아야 한다."""
    r = _v(dbmod, "LC", model="쏘나타", median_price=13_000_000,
           market_confidence_label="낮음")
    st = service.bid_state(r, BT)
    assert st["state"] == "lowconf" and "신뢰도" in st["label"]
    assert service.lifecycle_bucket_of(r, BT) == "lowconf"
