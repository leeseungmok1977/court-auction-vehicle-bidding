# -*- coding: utf-8 -*-
"""`accuracy_for` 가 **가격대 층**을 후보에 넣는다 (PANEL-30).

`accuracy_strata` 는 `price_band` 를 계산해 두는데 `accuracy_for` 의 후보는
`[제조사, 유찰횟수]` 둘뿐이라 **죽은 계산**이었다. 넣으면 '더 나쁜 쪽' 규칙상 표시 오차는
커지거나 그대로다 — 더 낙관적으로 바뀌는 경우가 없어, `accuracy_for` 독스트링이 금지한
과대주장과 방향이 같다(실측 근거: reports/panel08-softcap-accuracy-strata.md —
734건 중 396건이 평균 +0.77%p·최대 +1.0%p, 회복 건수는 0건).

★ 같은 커밋에 넣은 가드: `price_band` 는 `median_price or actual or 0` 이라 **가격을 모르는
  물건을 `500만 이하` 에 밀어 넣는다.** 지금은 그 층이 n=2(<8)라 자동 제외돼 무해하지만,
  표본이 8을 넘는 순간 가격 미상 물건이 엉뚱한 오차율을 배정받는다. 무해한 지금 고정해 둔다.
"""
import pytest

from web import service


@pytest.fixture(autouse=True)
def _clear_strata_memo(monkeypatch):
    """`_ACC_STRATA` 는 conftest 의 캐시 초기화 목록에 **없다** — 앞 테스트의 층이 넘어온다."""
    monkeypatch.setattr(service, "_ACC_STRATA", {"key": None, "data": None}, raising=False)


def _pool(n, err, median, **kw):
    row = {"err_pct": err, "median_price": median, "actual": median,
           "maker": "현대", "model": "쏘나타", "fail_count": 0}
    row.update(kw)
    return [dict(row) for _ in range(n)]


def _bt(pool):
    return {"sample": len(pool), "mae_pct": 9.9, "pred_pool": pool}


def v(**kw):
    base = {"maker": "현대", "model": "쏘나타", "fail_count": 0, "median_price": 30_000_000}
    base.update(kw)
    return base


# 층이 8건(ACCURACY_STRATUM_MIN_N)씩이라 둘 다 숫자를 낸다.
# 비싼 쪽 오차 12.0 · 싼 쪽 4.0 → 제조사·유찰 층은 섞여서 8.0 이 된다.
_MIXED = _pool(8, 12.0, 30_000_000) + _pool(8, 4.0, 3_000_000)


def test_전제_가격대_층과_다른_층의_값이_다르다():
    """전제가 깨지면 아래 테스트는 배선이 끊겨도 통과한다(공허 통과 방지)."""
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(_bt(_MIXED))}
    assert rows[("제조사", "국산")]["mae"] == 8.0
    assert rows[("유찰횟수", "유찰 0~1회")]["mae"] == 8.0
    assert rows[("가격대", "2,000만 초과")]["mae"] == 12.0
    assert rows[("가격대", "500만 이하")]["mae"] == 4.0


def test_가격대_층이_후보에_들어간다():
    """★ PANEL-30 본체. 고치기 전에는 제조사·유찰 층(8.0)만 보고 12.0 을 놓쳤다."""
    got = service.accuracy_for(v(median_price=30_000_000), _bt(_MIXED))
    assert got["mae"] == 12.0, (
        f"가격대 층(12.0)을 빼고 {got['mae']} 를 썼다 — accuracy_strata 가 계산해 둔 층을 "
        "accuracy_for 가 안 보는 죽은 계산이다(PANEL-30)")


def test_가격대_층이_더_낙관적이면_그쪽을_고르지_않는다():
    """'더 나쁜 쪽' 규칙은 층이 늘어도 그대로다 — 유리한 4.0 을 고르면 과대주장이 된다."""
    got = service.accuracy_for(v(median_price=3_000_000), _bt(_MIXED))
    assert got["mae"] == 8.0, f"낙관적인 가격대 층(4.0)을 골랐다: {got}"


def test_블렌드된_시세로_층을_고른다():
    """화면에 쓰는 시세(effective_median = 엔카+케이카 블렌드)와 같은 기준으로 층을 잡는다."""
    car = v(median_price=3_000_000, kcar_median=4_000_000, kcar_sample=9)
    assert service.effective_median(car) < 5_000_000, "전제: 블렌드해도 500만 이하"
    assert service.accuracy_for(car, _bt(_MIXED))["mae"] == 8.0


# ── 가드 ① 가격을 모르면 가격대 층을 배정받지 않는다 ──────────────────────
def test_가격을_모르면_가격대_층을_배정받지_않는다(monkeypatch):
    """`500만 이하` 층이 표본을 채운 미래 상태를 가정한다 — 그때 터지는 것이 이 함정이다."""
    strata = [
        {"group": "제조사", "label": "국산", "n": 100, "mae": 8.6, "within10": 65},
        {"group": "유찰횟수", "label": "유찰 0~1회", "n": 59, "mae": 8.0, "within10": 71},
        {"group": "가격대", "label": "500만 이하", "n": 40, "mae": 20.0, "within10": 20},
    ]
    monkeypatch.setattr(service, "accuracy_strata", lambda *a, **k: strata)
    got = service.accuracy_for(v(median_price=None))
    assert got["mae"] == 8.6 and got["label"] != "500만 이하", (
        f"가격을 모르는 물건이 '500만 이하' 층의 오차(±20.0%)를 배정받았다: {got}")


def test_가격_미상_표본은_가격대_층을_살찌우지_않는다():
    """층을 만드는 쪽(strata)에서도 막는다 — 후보에서만 빼면 층 값 자체가 이미 오염된다."""
    pool = _pool(8, 30.0, None, actual=None) + _pool(8, 5.0, 3_000_000)
    strata = service.accuracy_strata(_bt(pool))
    rows = {(r["group"], r["label"]): r for r in strata}
    band = rows.get(("가격대", "500만 이하"))
    assert band and band["n"] == 8 and band["mae"] == 5.0, (
        f"가격 미상 8건이 '500만 이하' 층에 섞였다(n={band and band['n']}, mae={band and band['mae']}) "
        "— median_price or actual or 0 의 함정")
    assert sum(r["n"] for r in strata if r["group"] == "가격대") == 8
    # 제조사·유찰 층은 가격과 무관하므로 16건 모두 센다(가드가 과하게 걷어내지 않았는지)
    assert rows[("제조사", "국산")]["n"] == 16


# ── 가드 ② 표본 부족 층은 여전히 후보에서 빠진다 ───────────────────────────
def test_표본_부족_가격대_층은_후보에서_빠진다(monkeypatch):
    strata = [
        {"group": "제조사", "label": "국산", "n": 100, "mae": 8.6, "within10": 65},
        {"group": "유찰횟수", "label": "유찰 0~1회", "n": 59, "mae": 8.0, "within10": 71},
        {"group": "가격대", "label": "500만 이하", "n": 2, "mae": None, "within10": None},
    ]
    monkeypatch.setattr(service, "accuracy_strata", lambda *a, **k: strata)
    got = service.accuracy_for(v(median_price=3_000_000))
    assert got["mae"] == 8.6, f"표본 2건짜리 층을 후보로 썼다: {got}"


def test_표본이_부족하면_가격대_층도_숫자를_내지_않는다():
    """층을 만드는 쪽의 규칙 — n<8 이면 mae/within10 은 None 이다(지어내지 않는다)."""
    pool = _pool(2, 4.0, 3_000_000) + _pool(8, 12.0, 30_000_000)
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(_bt(pool))}
    thin = rows[("가격대", "500만 이하")]
    assert thin["n"] == 2 and thin["mae"] is None and thin["within10"] is None


def test_층_경계는_기존_값_그대로다():
    """구간을 새로 만들지 않는다 — `accuracy_strata` 가 쓰던 경계를 그대로 쓴다."""
    for med, label in [(4_999_999, "500만 이하"), (5_000_000, "500~1,000만"),
                       (9_999_999, "500~1,000만"), (10_000_000, "1,000~2,000만"),
                       (19_999_999, "1,000~2,000만"), (20_000_000, "2,000만 초과")]:
        assert service._price_band(med) == label, med
    assert service._price_band(None) is None and service._price_band(0) is None
