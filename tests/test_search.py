"""차량 검색 수집 관련 순수 로직 테스트 (제조사 정규화·모델그룹·필터 조립)."""

from src.collect.encar import normalize_maker, clean_model_group, auto_map


def test_normalize_maker_domestic():
    assert normalize_maker("현대자동차") == "현대"
    assert normalize_maker("현대자동차(주)") == "현대"
    assert normalize_maker("기아자동차") == "기아"
    assert normalize_maker("기아") == "기아"
    assert normalize_maker("제네시스") == "제네시스"


def test_normalize_maker_aliases():
    assert normalize_maker("르노삼성") == "르노코리아(삼성)"
    assert normalize_maker("쌍용자동차") == "KG모빌리티(쌍용)"
    assert normalize_maker("한국지엠") == "쉐보레(GM대우)"
    assert normalize_maker("쉐보레") == "쉐보레(GM대우)"


def test_normalize_maker_unknown():
    assert normalize_maker("벤츠") is None
    assert normalize_maker("") is None
    assert normalize_maker(None) is None


def test_court_filters_strips_empty():
    from web.service import _court_filters
    search = {"court": {"carMdlNm": "그랜저", "gdsVendNm": "", "carMdyrMin": "2018",
                        "rletLwsDspslPrcMax": ""}}
    out = _court_filters(search)
    assert out == {"carMdlNm": "그랜저", "carMdyrMin": "2018"}
    assert _court_filters(None) == {}


def test_manwon_conversion():
    from web.app import _manwon_to_won
    assert _manwon_to_won("1000") == "10000000"
    assert _manwon_to_won("") == ""
    assert _manwon_to_won("abc") == ""


def test_result_helpers():
    from src.collect.courtauction_result import result_key, winning_amt, result_status, final_fields
    row = {"saNo": "20260130003534", "mokmulSer": "1", "maeAmt": "26280000"}
    assert result_key(row) == ("20260130003534", "1")
    assert winning_amt(row) == 26280000          # 낙찰가
    assert winning_amt({"maeAmt": None}) == 0     # 유찰
    assert winning_amt({"maeAmt": "0"}) == 0
    # 결과 분류: 확정 매각(04)만 낙찰. 유찰=03. 그 외는 기타(금액 있어도 미확정)
    assert result_status({"maeAmt": "8110000", "mulStatcd": "04"}) == ("낙찰", 8110000)
    assert result_status({"maeAmt": "0", "mulStatcd": "03"}) == ("유찰", None)
    assert result_status({"maeAmt": "0", "mulStatcd": "07"}) == ("기타", None)
    # 금액이 있어도 상태가 04가 아니면 낙찰로 단정하지 않음 (낙찰가<최저가 방지)
    assert result_status({"maeAmt": "15205000", "mulStatcd": "02"}) == ("기타", None)
    # 최종 최저매각가·유찰·기일 동기화 (낙찰가<최저가 오해 방지)
    ff = final_fields({"minmaePrice": "7350000", "yuchalCnt": "2", "maeGiil": "20260819"})
    assert ff == {"min_sale_price": 7350000, "fail_count": 2, "sale_date": "2026-08-19"}


def test_clean_model_group():
    assert clean_model_group("그랜저(GRANDEUR)") == "그랜저"
    assert clean_model_group("쏘나타 뉴 라이즈") == "쏘나타"
    assert clean_model_group("K8") == "K8"
    # 별칭: 첫 토큰이 틀리는 경우 보정
    assert clean_model_group("그랜드 스타렉스(GRAND STAREX)") == "스타렉스"
    assert clean_model_group("코란도스포츠") == "코란도"
    assert clean_model_group("") is None


def test_auto_map_genesis_and_domestic():
    assert auto_map("현대자동차", "EQ900")["manufacturer"] == "제네시스"
    assert auto_map("현대자동차", "G80")["manufacturer"] == "제네시스"
    assert auto_map("(주)현대자동차", "그랜드 스타렉스(GRAND STAREX)") == {
        "car_type": "Y", "manufacturer": "현대", "model_group": "스타렉스"}


def test_auto_map_import():
    m = auto_map("벤츠", "E220 d Cabriolet")
    assert m["car_type"] == "N" and m["manufacturer"] == "벤츠"
    assert m["model_group"] == "E-클래스" and m["premium"]
    assert auto_map("벤츠", "S350 d 4Matic L")["model_group"] == "S-클래스"
    assert auto_map("BMW", "520d xDrive")["model_group"] == "5시리즈"
    assert auto_map("BMW", "X5 xDrive30d")["model_group"] == "X5"
    assert auto_map("아우디", "A6 40 TDI")["model_group"] == "A6"
    assert auto_map(None, "카이엔")["manufacturer"] == "포르쉐"
    # 국산 상용(미니버스)은 국산으로 확정 — 수입 '미니' 오탐 방지
    assert auto_map("현대자동차", "미니버스")["manufacturer"] == "현대"
    # 상용/특수차(제조사 매핑 불가)는 None
    assert auto_map("", "덤프트럭 TGS 37.500") is None
