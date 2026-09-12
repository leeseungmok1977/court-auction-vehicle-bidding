"""service.py 순수 헬퍼 테스트 (최저매각가 도출·판정 하향)."""

from web import service


def test_current_min_sale_uses_next_scheduled_round():
    """낙찰 아닌 가장 최근(다음 예정) 기일의 최저가를 현재 최저매각가로 쓴다."""
    hist = [
        {"ymd": "2026-07-21", "result": "유찰", "lws_price": 31_000_000},
        {"ymd": "2026-08-25", "result": "",     "lws_price": 21_700_000},  # 다음 예정
    ]
    assert service._current_min_sale(hist, 31_000_000) == 21_700_000


def test_current_min_sale_ignores_nakchal_round():
    hist = [
        {"ymd": "2026-07-21", "result": "유찰", "lws_price": 31_000_000},
        {"ymd": "2026-08-25", "result": "낙찰", "lws_price": 21_700_000},
    ]
    assert service._current_min_sale(hist, 31_000_000) == 31_000_000


def test_current_min_sale_fallback_when_empty():
    assert service._current_min_sale([], 9_000_000) == 9_000_000
    assert service._current_min_sale(None, 9_000_000) == 9_000_000


def test_final_judgment_downgrades_low_confidence():
    assert service._final_judgment("입찰 검토 가능", "낮음") == "시세 신뢰도 낮음, 수동 검토"
    assert service._final_judgment("입찰 검토 가능", "높음") == "입찰 검토 가능"
    # 4회차: '유찰 대기'도 하향한다. 사고 감가를 정직하게 반영하자 같은 물건이
    # '검토 가능' → '유찰 대기'로 떨어지면서 하향을 피해 갔고, 시세를 못 믿는다는
    # 사실이 화면에서 사라졌다. 확정 상태(종결·보류)만 남긴다.
    assert service._final_judgment("유찰 대기", "낮음") == "시세 신뢰도 낮음, 수동 검토"
    assert service._final_judgment("유찰 대기", "높음") == "유찰 대기"
    assert service._final_judgment("종결", "낮음") == "종결"
    assert service._final_judgment("입찰 보류", "낮음") == "입찰 보류"


def test_is_block():
    assert service._is_block(RuntimeError("법원경매 차단 상태코드 403")) is True
    assert service._is_block(ValueError("timeout")) is False


def test_expected_winning():
    assert service.expected_winning(20_000_000, 0.8) == 16_000_000
    assert service.expected_winning(None, 0.8) is None
    assert service.expected_winning(20_000_000, None) is None
