"""상세 화면 간이 총비용(allin_estimate) — 낙찰가 + 취득세 + 이전·탁송."""
from web import service


def _cfg():
    return {"acquisition_tax_rate": 0.07,
            "fixed_costs": {"transfer_fee": 300000, "delivery_fee": 200000}}


def test_allin_sums_bid_tax_fixed():
    a = service.allin_estimate(10_000_000, _cfg())
    assert a["bid"] == 10_000_000
    assert a["tax"] == 700_000            # 7%
    assert a["fixed"] == 500_000          # 이전 30만 + 탁송 20만
    assert a["total"] == 11_200_000       # 낙찰가+세금+고정비
    assert a["tax_rate"] == 0.07


def test_allin_none_when_no_bid():
    assert service.allin_estimate(None, _cfg()) is None
    assert service.allin_estimate(0, _cfg()) is None


def test_allin_uses_config_defaults_when_missing():
    a = service.allin_estimate(20_000_000, {})   # 기본값 7% · 30만 · 20만
    assert a["tax"] == 1_400_000 and a["fixed"] == 500_000 and a["total"] == 21_900_000
