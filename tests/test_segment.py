"""차종 프리셋 분류(vehicle_segment) — 모델명 키워드 근사."""
from web import service


def seg(model):
    return service.vehicle_segment({"model": model})


def test_commercial():
    assert seg("포터Ⅱ") == "commercial"
    assert seg("봉고3 냉동탑차") == "commercial"
    assert seg("마이티 카고크레인") == "commercial"
    assert seg("렉스턴스포츠") == "commercial"      # 픽업은 상용으로


def test_minivan_before_suv():
    assert seg("카니발") == "minivan"
    assert seg("스타렉스") == "minivan"
    assert seg("코란도투리스모") == "minivan"        # '코란도' SUV보다 투리스모 승합 우선


def test_suv_and_sedan():
    assert seg("싼타페(SANTAFE)") == "suv"
    assert seg("팰리세이드") == "suv"
    assert seg("GV80") == "suv"
    assert seg("BMW X5") == "suv"
    assert seg("쏘나타(SONATA)") == "sedan"
    assert seg("그랜저(GRANDEUR)") == "sedan"
    assert seg("K5") == "sedan"
    assert seg("벤츠 E클래스") == "sedan"


def test_compact():
    assert seg("모닝") == "compact"
    assert seg("레이") == "compact"


def test_unknown_is_none():
    assert seg("") is None
    assert seg("굴착기 06W") is None
    assert seg(None) is None


def test_presets_exposed():
    keys = [k for k, _lbl, _kw in service.VEHICLE_SEGMENTS]
    assert keys == ["commercial", "minivan", "compact", "suv", "sedan"]
    assert service.SEGMENT_LABELS["suv"] == "SUV"
