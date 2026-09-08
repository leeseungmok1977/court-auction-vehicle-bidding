"""낙찰 결과 무결성 검증 — 물리적으로 불가능한 낙찰(오염 데이터)을 걸러낸다(신뢰 최우선)."""
from web.service import _result_anomaly


def test_normal_sale_is_ok():
    v = {"auction_result": "낙찰", "winning_price": 26280000,
         "min_sale_price": 22400000, "sale_date": "2020-01-01"}
    assert _result_anomaly(v, today="2026-09-08") == []


def test_winning_below_min_flagged():
    v = {"auction_result": "낙찰", "winning_price": 6177700,
         "min_sale_price": 45500000, "sale_date": "2020-01-01"}
    assert "낙찰가<최저매각가" in _result_anomaly(v, today="2026-09-08")


def test_sold_before_sale_date_flagged():
    v = {"auction_result": "낙찰", "winning_price": 50000000,
         "min_sale_price": 45000000, "sale_date": "2026-09-21"}
    assert "매각기일 미도래" in _result_anomaly(v, today="2026-09-08")


def test_non_sale_not_flagged():
    # 낙찰이 아니면 매각기일이 미래여도 이상 아님(예정 물건은 정상)
    assert _result_anomaly({"auction_result": "유찰", "sale_date": "2026-09-21"},
                           today="2026-09-08") == []


def test_snapshot_without_label_win_below_min():
    # 낙찰결과 스냅샷(auction_result 필드 없음)도 낙찰가<최저가는 잡는다(학습 오염 방지)
    v = {"winning_price": 9000000, "min_sale_price": 128798000}
    assert "낙찰가<최저매각가" in _result_anomaly(v)
