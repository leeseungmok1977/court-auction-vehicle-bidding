"""자동차 물건 상세 파싱 테스트 (설계서 TASK-03 DoD).

실제 상세 응답(축소 픽스처 tests/fixtures/detail_sample.json)으로 검증:
주행거리, 배기량, VIN, 회차별 최저가, 감정 요항 텍스트, 사고 1차 판정.
"""

import json
from pathlib import Path

import pytest

from src.parse.detail_parser import parse_detail

FIXTURE = Path(__file__).parent / "fixtures" / "detail_sample.json"


@pytest.fixture
def resp():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def cfg():
    return {
        "accident_keywords": ["사고", "판금", "교환", "부식", "훼손", "파손", "손상"],
        "flood_keywords": ["침수", "전손"],
    }


def test_vehicle_fields(resp, cfg):
    info = parse_detail(resp, cfg)
    assert info.mileage_km == 52902        # 주행거리 (계기판 52,902km)
    assert info.displacement_cc == 1950    # 배기량
    assert info.year == 2018               # 연식(출고)
    assert info.vin == "WDD1K1EB2JF043189"  # 차대번호
    assert info.model == "E220 d Cabriolet"


def test_insurance_history_counts(resp, cfg):
    """보험사고이력 카운트를 구조적으로 파싱한다."""
    info = parse_detail(resp, cfg)
    h = info.insurance_history
    assert h.get("flood") == 0        # 침수 0건
    assert h.get("total_loss") == 0   # 전손 0건
    assert h.get("own_damage") == 1   # 내차 피해 1회
    assert h.get("owner_changes") == 2


def test_accident_not_flood_false_positive(resp, cfg):
    """'침수 보험사고 : 0건'을 침수로 오탐하지 않는다(회귀 방지)."""
    info = parse_detail(resp, cfg)
    assert info.appraisal_text
    assert "훼손" in info.appraisal_text
    assert info.flood_hits == []                     # 0건 → 침수/전손 아님
    assert info.accident_grade == "accident"         # 내차피해 1회 + 훼손 → 사고
    assert "훼손" in info.accident_hits
    assert any("내차피해" in h for h in info.accident_hits)


def test_round_prices_and_docid(resp):
    info = parse_detail(resp)
    assert info.appraisal_value == 35000000
    assert info.fail_count == 2
    assert isinstance(info.round_prices, list) and len(info.round_prices) >= 1
    assert info.appraisal_ecdoc_id                   # 감정평가서 전자문서 ID 존재


def test_photo_count(resp):
    info = parse_detail(resp)
    assert info.photo_count == 7


def test_mileage_fallback_from_text():
    """구조화 필드가 비어도 감정 요항 텍스트에서 주행거리 추출."""
    resp = {"data": {"dma_result": {
        "gdsDspslObjctLst": [{"drvnDistIndctCtt": None, "carMdlNm": "아반떼"}],
        "aeeWevlMnpntLst": [{"aeeWevlMnpntCtt": "계기판상 주행거리는 123,456㎞임."}],
    }}}
    assert parse_detail(resp).mileage_km == 123456


def test_mileage_structured_priority():
    """구조화 필드가 있으면 그 값을 우선."""
    resp = {"data": {"dma_result": {
        "gdsDspslObjctLst": [{"drvnDistIndctCtt": "80000"}],
        "aeeWevlMnpntLst": [{"aeeWevlMnpntCtt": "주행거리 123,456km"}],
    }}}
    assert parse_detail(resp).mileage_km == 80000


def test_no_config_fallback(resp):
    # config 미제공 시 기본 키워드로도 사고 판정 동작
    info = parse_detail(resp)
    assert info.accident_grade == "accident"
    assert "훼손" in info.accident_hits


def test_flood_true_positive():
    """실제 침수 이력(건수>0)은 flood로 판정."""
    resp = {"data": {"dma_result": {
        "aeeWevlMnpntLst": [
            {"aeeWevlMnpntCtt": "사고이력정보 보고서 - 전손 보험사고 : 0건 "
                                "- 침수 보험사고 : 1건 - 내차 피해 : 0회"}
        ]}}}
    info = parse_detail(resp)
    assert info.insurance_history.get("flood") == 1
    assert info.accident_grade == "flood"
    assert "침수이력" in info.flood_hits


def _dxdy_resp(rows):
    return {"data": {"dma_result": {"gdsDspslDxdyLst": rows}}}


def test_dxdy_conservative_nakchal():
    """낙찰가가 있어도 결과코드가 변경(003)이면 낙찰로 인정하지 않는다."""
    info = parse_detail(_dxdy_resp([
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260721", "auctnDxdyRsltCd": "002",
         "tsLwsDspslPrc": "31000000", "dspslAmt": "0"},
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260825", "auctnDxdyRsltCd": "003",
         "tsLwsDspslPrc": "21700000", "dspslAmt": "25000000"},  # 변경 → 낙찰 아님
    ]))
    assert info.winning_price is None
    assert [h["result"] for h in info.dxdy_history] == ["유찰", "변경"]


def test_dxdy_true_nakchal_and_sort():
    """매각 결과코드(비-비매각)+낙찰가면 낙찰, 기일순 정렬로 최신 낙찰가 채택."""
    info = parse_detail(_dxdy_resp([
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260825", "auctnDxdyRsltCd": "001",
         "tsLwsDspslPrc": "21700000", "dspslAmt": "23000000"},
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260721", "auctnDxdyRsltCd": "002",
         "tsLwsDspslPrc": "31000000", "dspslAmt": "0"},
    ]))
    assert info.winning_price == 23000000
    assert info.dxdy_history[0]["ymd"] <= info.dxdy_history[1]["ymd"]  # 기일순


def test_dxdy_sale_then_reauction_resets_winning():
    """낙찰 후 후속 재매각/유찰 회차가 오면 이전 낙찰가를 무효화한다."""
    info = parse_detail(_dxdy_resp([
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260601", "auctnDxdyRsltCd": "001",
         "tsLwsDspslPrc": "20000000", "dspslAmt": "22000000"},   # 낙찰(뒤에 재매각)
        {"auctnDxdyKndCd": "01", "dxdyYmd": "20260710", "auctnDxdyRsltCd": "002",
         "tsLwsDspslPrc": "20000000", "dspslAmt": "0"},          # 이후 유찰 → 무효
    ]))
    assert info.winning_price is None
