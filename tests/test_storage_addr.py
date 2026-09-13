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


def test_backfill_fills_missing_source_for_existing_values(one):
    """값은 있는데 출처가 없는 행 — 운영에 309건 있었다.

    출처를 함께 내기로 한 이상, 출처 없는 값은 표기 규칙의 구멍이다.
    """
    (one / "d.json").write_text(json.dumps(
        {"storage_addr": "경기도 수원시 팔달구 매산로 1"}, ensure_ascii=False), encoding="utf-8")
    db.update_fields("V1", storage_addr="경기도 수원시 팔달구 매산로 1", storage_src=None)
    out = service.backfill_storage_addr()
    assert out["already"] == 1 and out["src_filled"] == 1
    assert db.get_vehicle("V1")["storage_src"] == "court"


def test_source_lookup_does_not_guess_when_files_disagree(one):
    """저장된 값과 파일의 값이 다르면 출처를 지어내지 않는다."""
    (one / "d.json").write_text(json.dumps(
        {"storage_addr": "부산광역시 강서구 경전철로 202"}, ensure_ascii=False), encoding="utf-8")
    db.update_fields("V1", storage_addr="경기도 수원시 팔달구 매산로 1", storage_src=None)
    out = service.backfill_storage_addr()
    assert out["src_filled"] == 0
    assert not (db.get_vehicle("V1")["storage_src"] or "")


# ── 지도 사진 검출 (3단계) ──────────────────────────────────────
def _synth(path, kind):
    """지도/차량/명판을 흉내 낸 합성 이미지. 실제 판정 특징을 재현한다."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(0)
    if kind == "map":
        # 밝은 파스텔 **유채색**을 넓게 깔고 얇은 선만 긋는다
        a = np.full((200, 200, 3), 236, dtype=np.uint8)
        a[0:100, :] = (214, 232, 205)      # 필지 초록
        a[100:200, :] = (240, 226, 208)    # 필지 베이지
        a[:, 98:101] = (150, 150, 150)
        a[95:98, :] = (150, 150, 150)
    elif kind == "plate":
        # 차대번호 명판 — 밝고 평평하고 선이 적지만 **무채색**이다.
        # pastel 조건이 없으면 이게 지도로 잡힌다(실제 오탐이었다).
        a = np.full((200, 200, 3), 250, dtype=np.uint8)
        a[60:150, 20:180] = (35, 35, 35)
        a[70:80, 30:170] = (230, 230, 230)
        a[100:110, 30:170] = (230, 230, 230)
    else:
        # 사진: 질감·그림자로 색이 넓게 퍼지고 엣지가 강하다
        a = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(a).save(path)


def test_map_detector_separates_maps_from_photos(tmp_path):
    from src.vision.map_photo import is_map_photo
    m, c = tmp_path / "m.png", tmp_path / "c.png"
    _synth(m, "map")
    _synth(c, "car")
    assert is_map_photo(str(m)) is True, "지도를 못 잡는다"
    assert is_map_photo(str(c)) is False, "사진을 지도로 잡는다"


def test_vin_plate_is_not_mistaken_for_a_map(tmp_path):
    """차대번호 명판을 지도로 잡으면 안 된다 — 실제 오탐이었다.

    명판도 밝고 평평하고 선이 적어 pale/top/edge 만으로는 지도와 구분되지 않는다.
    사용자가 '위치도'를 눌렀는데 명판이 나오면 앱이 거짓말을 한 것이다.
    지도만 가진 성질은 **파스텔 유채색이 넓게 깔린다**는 것이다(실측: 지도 0.68~0.96,
    명판 0.07, 차량 사진 0.30~0.52).
    """
    from src.vision.map_photo import is_map_photo, map_features
    p = tmp_path / "plate.png"
    _synth(p, "plate")
    ft = map_features(str(p))
    assert ft["pale"] >= 0.40 and ft["edge"] <= 10, "명판은 지도와 pale/edge가 겹쳐야 의미 있는 시험"
    assert is_map_photo(str(p)) is False, f"명판을 지도로 잡았다: {ft}"


def test_map_detector_survives_a_broken_file(tmp_path):
    """깨진 파일 한 장이 수집·백필을 멈추면 안 된다."""
    from src.vision.map_photo import is_map_photo
    bad = tmp_path / "x.gif"
    bad.write_bytes(b"not an image")
    assert is_map_photo(str(bad)) is False


def test_detail_points_to_the_map_photo_when_address_is_missing(client):
    """주소가 없어도 지도가 붙어 있으면 몇 번 사진인지 알려준다.

    실측: 주소 없는 물건 중 655건에 지도 사진이 있다. '확인되지 않음'만 띄우면
    화면에 이미 있는 위치를 사용자가 못 찾는다.
    """
    import web.app as A
    db.update_fields("S1", storage_addr=None, storage_src=None)
    pdir = A.DATA_DIR / "S1" / "photos"
    pdir.mkdir(parents=True, exist_ok=True)
    for name in ("a.png", "b.png"):
        _synth(pdir / name, "car")
    _synth(pdir / "c.png", "map")
    db.update_fields("S1", map_photos=["c.png"])

    html = client.get("/vehicle/S1").text
    assert "위치도" in html and "3번" in html, "지도 사진 안내가 없다"
    assert "확인되지 않음" not in html


# ── 지도 OCR (4단계) — 파싱·채택 규칙 ────────────────────────────
from src.vision.map_ocr import parse_label  # noqa: E402

# 검증 대상은 주소의 **첫 시·군·구**(도시)다 — 그것이 동명이동을 가르는 축이다.
# known_gu_names() 는 앱이 가진 주소에서 모든 시·군·구 토큰을 뽑으므로
# 실제로는 '전주시'와 '덕진구'가 모두 들어 있다.
GU = {"전주시", "덕진구", "안양시", "동안구", "창원시", "성산구", "서울특별시", "강서구"}


def test_ocr_accepts_a_full_address_next_to_the_label():
    """서버 실측에서 실제로 나온 OCR 결과."""
    got = parse_label("보관장소 55 uel 1456, ae 2 전주시 덕진구 덕진동1가 1420 호 시", GU)
    assert got["addr"] == "전주시 덕진구 덕진동1가 1420"


def test_ocr_rejects_a_partial_address_without_a_city():
    """'호계동 1101번지'는 안양·포항·양산에 다 있다 — 도시가 없으면 채택 못 한다."""
    got = parse_label("보관장소(호계동 1101번지) eee a ee", GU)
    assert got["label"] is True and got["addr"] == ""


def test_ocr_rejects_an_invented_district_name():
    """OCR이 지명을 지어내면 걸러야 한다 — 없는 구는 채택하지 않는다."""
    got = parse_label("보관장소 서울특별시 없는구 어딘가동 1", GU)
    assert got["addr"] == "" and "아는 시·군·구가 아님" in got["why"]


def test_ocr_ignores_maps_without_the_storage_label():
    """'본건'만 있는 지도는 채무자 주소일 수 있다 — 보관장소로 쓰지 않는다.

    실측 2024타경51422: '본건' 지도는 동문동을 가리키는데 법원이 준 보관장소는
    율지8로 52였다. 라벨을 안 가리면 틀린 주소를 낸다.
    """
    got = parse_label("본건 서울특별시 강서구 마곡동 1045", GU)
    assert got["label"] is False and got["addr"] == ""


def test_ocr_backfill_never_overwrites_a_court_value(one, monkeypatch):
    db.update_fields("V1", storage_addr="경기도 수원시 팔달구 매산로 1",
                     storage_src="court", map_photos=["m.png"])
    called = []
    monkeypatch.setattr("src.vision.map_ocr.read_storage_label",
                        lambda *a, **k: called.append(1) or {"label": True, "addr": "다른 주소"})
    out = service.backfill_map_ocr()
    assert not called, "이미 값이 있는데 OCR을 돌렸다"
    assert out["skipped"] >= 1
    assert db.get_vehicle("V1")["storage_addr"].endswith("매산로 1")


def test_ocr_result_is_marked_as_an_estimate(one, monkeypatch):
    """OCR은 숫자를 틀린다 — 확정으로 표기하면 안 된다."""
    (one / "photos").mkdir()
    (one / "photos" / "m.png").write_bytes(b"x")
    db.update_fields("V1", map_photos=["m.png"])
    monkeypatch.setattr(service, "known_gu_names", lambda: {"덕진구"})
    monkeypatch.setattr("src.vision.map_ocr.read_storage_label",
                        lambda *a, **k: {"label": True, "level": "full",
                                         "addr": "전주시 덕진구 덕진동1가 1420"})
    out = service.backfill_map_ocr()
    v = db.get_vehicle("V1")
    assert out["found"] == 1
    assert v["storage_src"] == "map_ocr" and v["storage_conf"] == "추정"


def test_coarse_result_says_it_is_only_district_level(one, monkeypatch):
    """동 이름이 깨져 구까지만 읽은 값은 그렇게 적어야 한다.

    실측: "보관장소 | & Mk 광주광역시 남구 SUS 124-3 송원주차장" — 시·도와 구는
    멀쩡한데 동이 'SUS'로 깨졌다. 번지까지 있는 값과 같은 표기를 쓰면 정밀도를
    오해한다.
    """
    (one / "photos").mkdir()
    (one / "photos" / "m.png").write_bytes(b"x")
    db.update_fields("V1", map_photos=["m.png"])
    monkeypatch.setattr(service, "known_gu_names", lambda: {"남구"})
    monkeypatch.setattr("src.vision.map_ocr.read_storage_label",
                        lambda *a, **k: {"label": True, "level": "coarse",
                                         "addr": "광주광역시 남구"})
    out = service.backfill_map_ocr()
    v = db.get_vehicle("V1")
    assert out["found"] == 1 and out["coarse"] == 1
    assert v["storage_conf"] == "구 단위 추정"


def test_parse_falls_back_to_district_when_dong_is_garbled():
    got = parse_label("보관장소 | & Mk 광주광역시 남구 SUS 124-3 송원주차장", {"남구"})
    assert got["addr"] == "광주광역시 남구" and got["level"] == "coarse"


def test_two_character_district_names_are_matched():
    """남구·북구·동구·서구·중구는 2글자다.

    `[가-힣]{2,6}(?:시|군|구)` 로 쓰면 접미사와 합쳐 최소 3글자를 요구해 이들을
    통째로 놓친다. 실측에서 광주광역시 남구가 이 이유로 버려졌다.
    """
    for text, gu, expect in [
        ("보관장소 광주광역시 남구 SUS 124-3", {"남구"}, "광주광역시 남구"),
        ("보관장소 부산광역시 북구 화명동 12-3", {"북구"}, "부산광역시 북구 화명동 12-3"),
        ("보관장소 대구광역시 중구 동산동 5", {"중구"}, "대구광역시 중구 동산동 5"),
    ]:
        assert parse_label(text, gu)["addr"] == expect, text


def test_known_gu_vocabulary_includes_two_character_districts():
    """대조표에도 2글자 구가 들어가야 한다 — 아니면 제대로 읽고도 버린다."""
    import re
    pat = re.compile(r"[가-힣]{1,5}(?:시|군|구)")
    assert "남구" in pat.findall("광주광역시 남구 봉선동")


def test_ocr_does_not_retry_a_vehicle_it_already_attempted(one, monkeypatch):
    """OCR은 장당 12초다 — 실패분을 재실행마다 다시 읽으면 3시간이 낭비된다.

    결과가 아니라 **시도했다는 사실**을 남겨야 증분 실행이 싸진다.
    """
    (one / "photos").mkdir()
    (one / "photos" / "m.png").write_bytes(b"x")
    db.update_fields("V1", map_photos=["m.png"])
    monkeypatch.setattr(service, "known_gu_names", lambda: {"남구"})
    calls = []
    monkeypatch.setattr("src.vision.map_ocr.read_storage_label",
                        lambda *a, **k: calls.append(1) or
                        {"label": False, "addr": "", "level": "", "why": "x"})
    service.backfill_map_ocr()
    assert len(calls) == 1 and db.get_vehicle("V1")["map_ocr_at"]
    service.backfill_map_ocr()                    # 두 번째 실행
    assert len(calls) == 1, "이미 시도한 물건을 또 읽었다"
    service.backfill_map_ocr(redo=True)           # 강제 재시도는 다시 읽는다
    assert len(calls) == 2


# ── 비전 LLM 폴백 (OCR 실패분 한정) ──────────────────────────────
from src.vision.map_vision import accept as v_accept  # noqa: E402

GU2 = {"전주시", "덕진구", "서산시", "서대문구", "안양시"}


def test_vision_accepts_a_printed_address():
    """큰 글씨로 인쇄된 주소를 옮기는 것은 정확하다 — 실측 전주 건."""
    got = v_accept({"printed_address": "전주시 덕진구 덕진동1가 1420",
                    "nearby_labels": ["덕진구", "전주역"], "label_kind": "보관장소"}, GU2)
    assert got["addr"] == "전주시 덕진구 덕진동1가 1420" and got["level"] == "full"


def test_vision_never_uses_labels_the_model_claims_to_have_read():
    """⚠ 이 테스트가 이 기능의 핵심 안전장치다.

    실측: 충남 **서산시** 지도를 주고 물었더니 모델이 `서대문구`·`영천동`·`서대문역`
    (서울 지명)을 "읽었다"고 답했다. 근거(evidence)를 요구해도 소용없다 —
    **근거 자체가 지어내진다.** 그래서 주변 지명은 채택 경로에서 통째로 뺀다.
    """
    got = v_accept({"printed_address": None,
                    "nearby_labels": ["서대문구", "영천동", "서대문역"],
                    "label_kind": "보관장소"}, GU2)
    assert got["addr"] == "", f"지어낸 지명을 주소로 채택했다: {got}"
    assert "인쇄돼 있지 않" in got["why"]


def test_vision_uses_bongeon_maps_too():
    """'본건' 지도도 쓴다 — **자동차는 부동산과 다르다.**

    부동산은 물건 소재지가 그 부동산 위치로 고정되지만, 자동차는 그렇지 않다.
    차량의 물건 소재지가 곧 보관장소다.

    실측도 이를 뒷받침한다: 2024타경51422의 '본건' 지도는 감정서 본문의
    보관장소(동문동)와 일치했고, 오히려 법원 API 값(율지8로 52)이 달랐다.
    대신 다른 가드(지명 어휘·법원 시·도·번지 모순)는 그대로 태운다.
    """
    got = v_accept({"printed_address": "서산시 동문동 195-4",
                    "nearby_labels": [], "label_kind": "본건"}, {"서산시"})
    assert got["addr"] == "서산시 동문동 195-4"

    # 라벨이 무엇이든 다른 가드는 여전히 막는다
    blocked = v_accept({"printed_address": "경기도 안양시 백석동 방성리 492-3",
                        "nearby_labels": [], "label_kind": "본건"},
                       {"안양시"}, {"경기"}, DONG_VOCAB, None)
    assert blocked["addr"] == ""


def test_city_is_completed_only_when_unique_in_the_court_region():
    """'호계동 1101번지'처럼 시가 빠진 주소는 법원 관할에서 **유일할 때만** 채운다.

    실측: 우리 어휘의 동/리 892개 중 77%가 시·도를 알면 시·군·구가 유일해진다.
    둘 이상이면 지어내지 않고 포기한다 — 엉뚱한 도시로 보내는 것이 더 나쁘다.
    """
    dbg = {"안양시": {"호계동", "관양동"}, "포항시": {"호계동"}}
    gsido = {"안양시": "경기", "포항시": "경북"}
    ok = v_accept({"printed_address": "호계동 1101번지", "nearby_labels": [],
                   "label_kind": "보관장소"},
                  {"안양시", "포항시"}, {"경기"}, dbg, None, gsido)
    assert ok["addr"] == "안양시 호계동 1101번지", ok

    # 같은 시·도에 후보가 둘이면 포기한다
    dbg2 = {"안양시": {"호계동"}, "성남시": {"호계동"}}
    gsido2 = {"안양시": "경기", "성남시": "경기"}
    amb = v_accept({"printed_address": "호계동 1101번지", "nearby_labels": [],
                    "label_kind": "보관장소"},
                   {"안양시", "성남시"}, {"경기"}, dbg2, None, gsido2)
    assert amb["addr"] == "" and "특정 불가" in amb["why"]


def test_vision_rejects_an_address_contradicting_the_court_region():
    """법원 관할 시·도와 어긋나면 버린다 — 추정이 아니라 반증에만 쓴다."""
    got = v_accept({"printed_address": "서울특별시 서대문구 영천동 1",
                    "nearby_labels": [], "label_kind": "보관장소"},
                   GU2, court_sido={"충남"})
    assert got["addr"] == "" and "어긋남" in got["why"]
    # 같은 시·도면 통과한다(정읍지원 물건의 전주시 주소처럼)
    ok = v_accept({"printed_address": "전주시 덕진구 덕진동1가 1420",
                   "nearby_labels": [], "label_kind": "보관장소"},
                  GU2, court_sido={"전북"})
    assert ok["addr"].startswith("전주시")


def test_vision_rejects_label_text_mistaken_for_an_address():
    """모델이 라벨 자체나 파편을 주소로 내는 경우가 있다 — 실측 '보관장소', '1393-3 강변북로'."""
    for junk in ("보관장소", "1393-3 강변북로", "null"):
        got = v_accept({"printed_address": junk, "nearby_labels": [],
                        "label_kind": "보관장소"}, GU2)
        assert got["addr"] == "", f"쓰레기 문자열을 주소로 채택했다: {junk}"


def test_vision_backfill_skips_vehicles_that_already_have_an_address(one, monkeypatch):
    db.update_fields("V1", storage_addr="경기도 수원시 팔달구 매산로 1",
                     storage_src="court", map_photos=["m.png"])
    called = []
    monkeypatch.setattr("src.vision.map_vision.read_map",
                        lambda *a, **k: called.append(1) or {})
    out = service.backfill_map_vision(limit=5, delay=0)
    assert not called and out["tried"] == 0


def test_vision_backfill_aborts_after_three_consecutive_failures(one, monkeypatch):
    """C.4 중단 조건 — 429/403 이 3연속이면 즉시 멈춘다."""
    from src.vision.map_vision import VisionError
    (one / "photos").mkdir()
    for i in range(6):
        db.upsert_vehicle({"id": f"W{i}", "folder_key": "V1", "case_no": "2026타경9",
                           "item_no": "1", "court": "수원지방법원", "status": "완료"})
        db.update_fields(f"W{i}", map_photos=["m.png"])
        (one / "photos" / "m.png").write_bytes(b"x")
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise VisionError("HTTP 429")
    monkeypatch.setattr("src.vision.map_vision.read_map", boom)
    out = service.backfill_map_vision(limit=50, delay=0)
    assert out["aborted"] and "429" in out["aborted"]
    assert len(calls) == 3, f"3연속에서 멈춰야 하는데 {len(calls)}회 호출했다"


def test_vision_api_key_is_never_hardcoded():
    """C.4 — 키는 gitignore된 docs/.env 에서만 읽는다."""
    import pathlib
    src = pathlib.Path("src/vision/map_vision.py").read_text(encoding="utf-8")
    assert "sk-" not in src, "소스에 키가 박혀 있다"
    assert "docs" in src and ".env" in src


@pytest.mark.parametrize("path", ["/vehicle/S1", "/vehicle/S1/report"])
def test_vision_sourced_address_is_marked_as_an_estimate(client, path):
    """지도 판독 값은 확정이 아니다 — 출처와 추정 표기가 함께 나와야 한다."""
    db.update_fields("S1", storage_addr="전주시 덕진구 덕진동1가 1420",
                     storage_src="map_vision", storage_conf="추정")
    html = client.get(path).text
    assert "전주시 덕진구 덕진동1가 1420" in html
    assert "지도 판독" in html, f"{path}: 출처 표기가 없다"


def test_storage_patch_round_trip_never_overwrites_source_values(one, tmp_path):
    """지도 판독 결과를 운영에 옮길 때 원문 값(법원·감정서)을 덮으면 안 된다.

    비전 LLM은 로컬에서 돌리고 결과만 옮긴다 — API 키를 운영 서버에 두지 않기
    위해서다. 옮기는 과정에서 추정값이 확정값을 밀어내면 안 된다.
    """
    db.update_fields("V1", storage_addr="전주시 덕진구 덕진동1가 1420",
                     storage_src="map_vision", storage_conf="추정")
    p = tmp_path / "patch.json"
    assert service.export_storage_patch(str(p)) == 1

    # 옮겨받는 쪽: 하나는 이미 법원값이 있고, 하나는 비어 있다
    db.upsert_vehicle({"id": "V2", "folder_key": "V2", "case_no": "2026타경2",
                       "item_no": "1", "court": "수원지방법원", "status": "완료"})
    db.update_fields("V1", storage_addr="충청남도 서산시 율지8로 52",
                     storage_src="court", storage_conf=None)
    out = service.apply_storage_patch(str(p))
    assert out["kept"] == 1 and out["applied"] == 0
    assert db.get_vehicle("V1")["storage_src"] == "court", "추정값이 법원값을 덮었다"

    db.update_fields("V1", storage_addr=None, storage_src=None)
    out2 = service.apply_storage_patch(str(p))
    assert out2["applied"] == 1
    assert db.get_vehicle("V1")["storage_src"] == "map_vision"


def test_storage_patch_skips_unknown_vehicle_ids(one, tmp_path):
    import json as _json
    p = tmp_path / "p.json"
    p.write_text(_json.dumps([{"id": "NOPE", "addr": "서울특별시 강서구",
                               "src": "map_vision", "conf": "추정"}]), encoding="utf-8")
    out = service.apply_storage_patch(str(p))
    assert out["unknown"] == 1 and out["applied"] == 0


# ── 비전 판독 2차 가드 — 실측 오류에서 나온 것들 ──────────────────
DONG_VOCAB = {"양주시": {"백석읍", "방성리", "고읍동", "남방동"},
              "남양주시": {"오남읍", "오남리", "화도읍"},
              "안양시": {"동안구", "관양동", "호계동"},
              "미추홀구": {"학익동", "용현동", "주안동"}}
PLACE_IDX = {"bunji": {"492-3": {"양주시"}}, "facil": {"정석주차장": {"양주시"}}}


def test_vision_rejects_a_dong_that_does_not_belong_to_that_district():
    """시·군·구가 실재하고 법원 시·도와 맞아도 틀릴 수 있다.

    실측: '경기도 안양시 백석동 방성리 492-3(정석주차장)' — 안양시도 실재하고
    경기도 맞지만, 실제는 **양주시 백석읍 방성리**였다. 그 시·군·구에 그런 동이
    있는지까지 봐야 걸린다.
    """
    got = v_accept({"printed_address": "경기도 안양시 백석동 방성리 492-3(정석주차장)",
                    "nearby_labels": [], "label_kind": "보관장소"},
                   {"안양시"}, {"경기"}, DONG_VOCAB, None)
    assert got["addr"] == "" and "확인되지 않는 지명" in got["why"]

    ok = v_accept({"printed_address": "경기도 양주시 백석읍 방성리 492-3",
                   "nearby_labels": [], "label_kind": "보관장소"},
                  {"양주시"}, {"경기"}, DONG_VOCAB, None)
    assert ok["addr"].startswith("경기도 양주시")


def test_vision_rejects_a_place_that_trusted_data_puts_elsewhere():
    """같은 시설명·번지가 신뢰 소스에선 다른 시·군·구면 하나는 틀렸다."""
    got = v_accept({"printed_address": "경기도 안양시 관양동 492-3 정석주차장",
                    "nearby_labels": [], "label_kind": "보관장소"},
                   {"안양시"}, None, DONG_VOCAB, PLACE_IDX)
    assert got["addr"] == "" and "신뢰 소스에서" in got["why"]


def test_short_lot_numbers_do_not_trigger_a_contradiction():
    """'22-11' 같은 짧은 번호는 다른 동네와 우연히 겹친다 — 정상 주소를 떨어뜨렸다."""
    idx = {"bunji": {"22-11": {"평택시"}}, "facil": {}}
    got = v_accept({"printed_address": "경기도 양주시 고읍동 285 (청담로 39번길 22-11)",
                    "nearby_labels": [], "label_kind": "보관장소"},
                   {"양주시"}, None, DONG_VOCAB, idx)
    assert got["addr"], f"짧은 번호 우연 충돌로 정상 주소를 버렸다: {got['why']}"


def test_label_prefix_is_stripped_from_the_address():
    """모델이 라벨 문구를 주소 앞에 붙여 온다 — '보관장소 - …', '어선 보관장소 …'."""
    from src.vision.map_vision import clean_address
    assert clean_address("보관장소 - 경상북도 안동시 강남14길 65") == "경상북도 안동시 강남14길 65"
    assert clean_address("어선 보관장소 여수시 국동항") == "여수시 국동항"
    assert clean_address("대상물건 보관장소 부산광역시 강서구") == "부산광역시 강서구"


def test_validation_vocabulary_excludes_vision_output(one):
    """⚠ 검증 어휘를 비전 결과로 만들면 순환이 된다 — 실제로 그랬다.

    비전이 만들어 낸 '병설리'·'화이트동'이 어휘에 들어가 자기 자신을 통과시켰다.
    """
    db.upsert_vehicle({"id": "T1", "folder_key": "T1", "case_no": "2026타경3",
                       "item_no": "1", "court": "의정부지방법원", "status": "완료",
                       "location": "경기도 양주시 백석읍 방성리 1"})
    db.update_fields("T1", storage_addr="경기도 양주시 백석읍 병설리 490-2",
                     storage_src="map_vision")
    vocab = service.known_dong_by_gu()
    assert "방성리" in vocab.get("양주시", set()), "location 은 어휘에 들어가야 한다"
    assert "병설리" not in vocab.get("양주시", set()), "비전 결과가 어휘를 오염시켰다"
