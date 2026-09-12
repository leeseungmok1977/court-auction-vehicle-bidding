"""차량 보관장소 추출·백필 — 실측에서 나온 실제 문장 형태로 고정한다.

보관장소는 **차량이 실제로 있는 곳**이고 `location`(채무자 주소)과 다르다.
섞이면 사용자를 엉뚱한 도시로 보낸다.

실측 배경(1,320건 전수):
  · DB 0건 / 수집 JSON 163건 — 기능이 2026-09-06에 들어왔는데 상세 분석은
    그 전(8-23)에 끝나 백필이 한 번도 돌지 않았다.
  · 감정서 본문의 '보관장소' 언급 91건 중 기존 패턴으로는 56건만 잡혔다.
    놓친 것은 전부 조사가 붙고 구두점이 없는 실제 문장체였다.
"""
import json

import pytest

from src.parse.detail_parser import _storage_from_text
from web import db, service

# 실제 감정서에서 관찰된 형태 → 기대 추출값(부분 일치로 검사)
REAL_FORMS = [
    ("2) 본 차량의 보관장소는 경기도 안양시 동안구 엘에스로 99 소재 '중부모터스' 구내이며"
     "    동소에서 실사하였음.", "경기도 안양시 동안구 엘에스로 99"),
    ("1) 본건 자동차의 보관장소는 경상남도 창원시 성산구 남면로 319임.",
     "경상남도 창원시 성산구 남면로 319"),
    ("보관장소 ㆍ경상남도 창원시 마산합포구 가포동 619번지.",
     "경상남도 창원시 마산합포구 가포동 619번지"),
    ('- 보관장소는 "서울특별시 강서구 마곡동 1045번지 (금화주차장)"임.',
     "서울특별시 강서구 마곡동 1045번지"),
    ("- 본건 자동차 보관장소는 경기도 안산시 상록구 수암동 458-3번지임.",
     "경기도 안산시 상록구 수암동 458-3번지"),
    ("현장조사일 현재 보관장소는 원주시 소초면 섬배로 14-16에 보관되어 있음.",
     "원주시 소초면 섬배로 14-16"),
    ("본건 자동차는 지정 보관장소(경기도 광주시 도척면 진우리 844-14, 강남물류)에 주차되어 있는",
     "경기도 광주시 도척면 진우리 844-14"),
]

# 주소가 없는 언급 — 잡으면 안 된다 (잡으면 화면에 엉뚱한 문구가 주소로 나간다)
NON_ADDRESS = [
    "시동은 정상적으로 작동되나, 보관장소 여건상 차량의 정상작동 여부는 확인이 불가능한 바",
    "외관 스크래치 등 자세한 사항은 보관장소 내에서 재확인하시기 바랍니다.",
    "본건 2014년식으로서, 보관장소 입고일 현재 계기판상 주행거리는 206,308km임.",
    "자동차 키가 부재하여 별도로 제작하여 자동차 보관장소에 보관시켰음.",
    "전면 유리창등이 파손된 상태로 보관장소에 입고된 것으로 탐문되었습니다.",
]


@pytest.mark.parametrize("text,expect", REAL_FORMS)
def test_real_sentence_forms_are_extracted(text, expect):
    got = _storage_from_text(text)
    assert expect in got, f"기대 {expect!r} 가 추출값 {got!r} 에 없다"


@pytest.mark.parametrize("text", NON_ADDRESS)
def test_non_address_mentions_are_rejected(text):
    assert _storage_from_text(text) == "", "주소가 없는 언급을 보관장소로 채택했다"


def test_business_name_alone_is_not_an_address():
    """'아줌마주차장'처럼 상호만 있으면 주소가 아니다 — 실제 오탐이었다."""
    assert _storage_from_text("보관장소는 아줌마주차장임.") == ""


def test_unbalanced_quote_is_removed():
    """따옴표가 한쪽만 남으면 화면에 깨진 값으로 보인다."""
    got = _storage_from_text("보관장소는 울산광역시 울주군 언양읍 언양로 605 '복산주차장'임.")
    assert got and got.count("'") % 2 == 0, f"짝 안 맞는 따옴표가 남았다: {got!r}"


def test_duplicated_sido_is_collapsed():
    got = _storage_from_text("보관장소는 경기도 경기도 용인시 기흥구 흥덕4로30번길 28-25임.")
    assert got.startswith("경기도 용인시"), got


# ── 백필 ────────────────────────────────────────────────────────
@pytest.fixture
def one(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "s.db")
    db.init_db()
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data" / "V1"
    folder.mkdir(parents=True)
    db.upsert_vehicle({"id": "V1", "folder_key": "V1", "case_no": "2026타경1",
                       "item_no": "1", "court": "수원지방법원", "maker": "현대",
                       "model": "그랜저", "status": "완료"})
    return folder


def test_backfill_prefers_court_json_over_text(one):
    (one / "d.json").write_text(json.dumps(
        {"storage_addr": "경기도 수원시 팔달구 매산로 1"}, ensure_ascii=False), encoding="utf-8")
    (one / "appraisal.txt").write_text(
        "보관장소는 부산광역시 강서구 경전철로 202임.", encoding="utf-8")
    out = service.backfill_storage_addr()
    v = db.get_vehicle("V1")
    assert out["from_court"] == 1 and out["from_text"] == 0
    assert v["storage_addr"] == "경기도 수원시 팔달구 매산로 1"
    assert v["storage_src"] == "court", "출처를 기록해야 화면에 함께 낼 수 있다"


def test_backfill_falls_back_to_appraisal_text(one):
    (one / "appraisal.txt").write_text(
        "본건 자동차의 보관장소는 경상남도 창원시 성산구 남면로 319임.", encoding="utf-8")
    out = service.backfill_storage_addr()
    v = db.get_vehicle("V1")
    assert out["from_text"] == 1
    assert "창원시 성산구 남면로 319" in v["storage_addr"]
    assert v["storage_src"] == "text"


def test_backfill_never_overwrites_an_existing_value(one):
    db.update_fields("V1", storage_addr="이미 있는 주소 서울 강남구 테헤란로 1",
                     storage_src="court")
    (one / "appraisal.txt").write_text(
        "보관장소는 부산광역시 강서구 경전철로 202임.", encoding="utf-8")
    out = service.backfill_storage_addr()
    assert out["already"] == 1 and out["from_text"] == 0
    assert db.get_vehicle("V1")["storage_addr"].endswith("테헤란로 1")


def test_backfill_makes_no_network_call(one, monkeypatch):
    """C.4 — 백필은 외부 요청을 하지 않는다. 저장된 파일만 읽는다."""
    import urllib.request
    def boom(*a, **k):
        raise AssertionError("백필이 외부 요청을 시도했다")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    for name in ("get", "post", "request"):
        try:
            import requests
            monkeypatch.setattr(requests, name, boom)
        except ImportError:
            pass
    (one / "appraisal.txt").write_text(
        "보관장소는 경상남도 창원시 성산구 남면로 319임.", encoding="utf-8")
    service.backfill_storage_addr()


def test_listing_refresh_cannot_wipe_storage_fields():
    """목록 갱신이 보관장소를 덮으면 안 된다 — 파생값이라 목록에는 없다."""
    for col in ("storage_addr", "storage_src", "storage_conf"):
        assert col in db._LISTING_KEEP, f"{col} 이 목록 갱신 보호 목록에 없다"


# ── 화면 표기 — 출처를 반드시 함께 낸다 ──────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    db.init_db()
    db.upsert_vehicle({
        "id": "S1", "folder_key": "S1", "case_no": "2026타경7", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "그랜저", "year": 2020,
        "min_sale_price": 10_000_000, "appraisal_value": 14_000_000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 12_000_000, "market_confidence": 78,
        "market_confidence_label": "높음", "location": "서울 강남구 테헤란로 1",
        "storage_addr": "경기도 안양시 동안구 엘에스로 99", "storage_src": "court",
    })
    import web.app as A
    return TestClient(A.app)


@pytest.mark.parametrize("path", ["/vehicle/S1", "/vehicle/S1/report"])
def test_storage_address_is_shown_with_its_source(client, path):
    """주소만 내고 출처를 감추면, 소스끼리 어긋날 때 사용자가 무엇을 믿을지 모른다."""
    html = client.get(path).text
    assert "경기도 안양시 동안구 엘에스로 99" in html
    assert "법원 상세" in html, f"{path}: 출처 표기가 없다"


def test_missing_storage_does_not_claim_the_court_omitted_it(client):
    """'법원 미표시'는 사실이 아니었다 — 우리가 안 채운 경우가 대부분이었다."""
    db.update_fields("S1", storage_addr=None, storage_src=None)
    html = client.get("/vehicle/S1").text
    assert "법원 미표시" not in html
    assert "확인되지 않음" in html
