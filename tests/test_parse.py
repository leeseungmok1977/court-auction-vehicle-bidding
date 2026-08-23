"""자동차 물건목록 파싱 테스트 (설계서 TASK-03 DoD).

실제 응답(축소 픽스처 tests/fixtures/list_sample.json)으로 필드 추출을 검증한다:
사건번호, 차명, 연식, 감정가, 최저가, 매각기일, 유찰횟수 (+ 주행거리는 상세에서).
"""

import json
from pathlib import Path

import pytest

from src.parse.list_parser import parse_list_response, parse_row, total_count

FIXTURE = Path(__file__).parent / "fixtures" / "list_sample.json"


@pytest.fixture
def resp():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_loads(resp):
    rows = resp["data"]["dlt_srchResult"]
    assert len(rows) >= 2


def test_parse_all_rows(resp):
    items = parse_list_response(resp)
    assert len(items) == len(resp["data"]["dlt_srchResult"])
    # 필수 필드 존재
    for it in items:
        assert it.case_no          # 사건번호
        assert it.doc_id           # 상세조회 키
        assert it.court            # 법원
        assert it.item_no          # 물건번호


def test_field_extraction_types(resp):
    it = parse_list_response(resp)[0]
    # 금액·건수는 정수 또는 None
    assert it.appraisal_value is None or isinstance(it.appraisal_value, int)
    assert it.min_sale_price is None or isinstance(it.min_sale_price, int)
    assert it.fail_count is None or isinstance(it.fail_count, int)
    # 매각기일은 YYYY-MM-DD 또는 None
    if it.sale_date is not None:
        assert len(it.sale_date) == 10 and it.sale_date[4] == "-"
    # 주행거리는 목록 단계에서 미확정(None)
    assert it.mileage is None


def test_case_no_from_printcsno():
    """printCsNo의 <br/> 뒤 사건번호를 추출한다."""
    row = {"printCsNo": "서울중앙지방법원<br/>2025타경103470", "saNo": "20250130103470",
           "mokmulSer": "1", "jiwonNm": "서울중앙지방법원", "docid": "X", "boCd": "B000210"}
    it = parse_row(row)
    assert it.case_no == "2025타경103470"


def test_date_format():
    row = {"maeGiil": "20260820", "printCsNo": "법원<br/>2025타경1", "mokmulSer": "1",
           "jiwonNm": "법원", "docid": "X", "boCd": "B"}
    it = parse_row(row)
    assert it.sale_date == "2026-08-20"


def test_year_zero_becomes_none():
    row = {"carYrtype": "0", "printCsNo": "법원<br/>2025타경1", "mokmulSer": "1",
           "jiwonNm": "법원", "docid": "X", "boCd": "B"}
    it = parse_row(row)
    assert it.year is None


def test_folder_key():
    row = {"printCsNo": "법원<br/>2025타경103470", "mokmulSer": "2",
           "jiwonNm": "법원", "docid": "X", "boCd": "B"}
    it = parse_row(row)
    assert it.folder_key == "2025타경103470_2"


def test_total_count(resp):
    tc = total_count(resp)
    assert tc is None or isinstance(tc, int)
