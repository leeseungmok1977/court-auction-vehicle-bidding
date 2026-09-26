"""FEAT-2 연식 하한·주행거리 상한 필터 — 서버 쪽 계약 (오너 승인 2026-09-26 UX-6 순서 1, 지시서 2026-09-27-27).

FEAT-1(tests/test_price_band_filter.py)의 항목을 그대로 본떴다. 옵션 정의는 `service.YEAR_MIN_OPTIONS`·
`KM_MAX_OPTIONS` 둘뿐이고 라우트·COUNT·템플릿·이 파일이 전부 그것을 본다. 가격대와 달리 **누적 옵션**이다 —
'2018년 이후'는 '2020년 이후'를 포함하므로 옵션별 건수는 SUM(CASE WHEN …) 으로 한 쿼리에 센다.

이 파일이 지키는 것:
  ① 상수 형태(키는 URL 문자열·값·라벨)   ② 화이트리스트(정확 문자열 일치 — '2018.0'·'abc'·중복·빈값 → 필터 없음, 200)
  ③ 경계: 정확히 2018 포함(>=) · 정확히 100,000 포함(<=) · year NULL·0 제외 · km NULL·0 이하 제외
  ④ SQL 조각 == 파이썬 술어(segment·bucket·usepick·picks 경로)   ⑤ 옵션별 COUNT 는 한 쿼리(execute 1회)
  ⑥ `/vehicles` 총수 == `/api/vehicles/count`(SQL 경로·파이썬 경로·usepick·bucket·picks)
  ⑦ 패싯 일관성: 선택 옵션 count == total, 다른 옵션 count == "그 옵션으로 바꾸면 나올 총수", 축 3종이 서로를 반영
  ⑧ km_unknown_excluded == 주행거리 축만 뺀 모수의 미상(NULL·0 이하) 건수   ⑨ 템플릿 컨텍스트 계약·qs/_filters
  ⑩ 반증 — WHERE 조각을 지운 변이체는 NULL·범위 밖 행을 돌려준다(조각이 실제로 일을 한다)
"""
import inspect
import re
import textwrap

import pytest
from starlette.testclient import TestClient

from web import db, service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님)
BASE = {"court": "수원지방법원", "item_no": "1", "sale_date": "2999-01-01",
        "status": "완료", "fail_count": 1, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, 연식, 주행거리, 최저매각가, 제조사, 모델) — 옵션 경계마다 양쪽에 한 행씩. 모델 '포터'는 segment=commercial(파이썬 필터) 검증용.
ROWS = [
    ("R01", 2014, 49_999,   4_000_000, "현대", "쏘나타"),   # 2015 미만 · 5만 미만
    ("R02", 2015, 50_000,   8_000_000, "현대", "쏘나타"),   # ★ 경계: 정확히 2015 는 '2015년 이후', 정확히 50,000 은 '5만km 이하'
    ("R03", 2017, 50_001,  12_000_000, "기아", "쏘나타"),
    ("R04", 2018, 100_000, 15_400_000, "기아", "포터"),     # ★ 경계: 정확히 2018 · 정확히 100,000
    ("R05", 2019, 100_001, 18_000_000, "현대", "쏘나타"),
    ("R06", 2020, 150_000, 22_000_000, "현대", "포터"),     # ★ 경계: 정확히 2020 · 정확히 150,000
    ("R07", 2021, 150_001, 25_000_000, "기아", "쏘나타"),
    ("R08", 2022, 200_000, 35_000_000, "현대", "쏘나타"),   # ★ 경계: 정확히 2022 · 정확히 200,000
    ("R09", 2024, 200_001, 50_000_000, "기아", "포터"),     # 20만 초과 — 어느 상한에도 안 든다(미상은 아님)
    ("R10", 2023, 30_000,  None,       "현대", "쏘나타"),   # 최저가 미상(가격대 축 NULL)
    ("N01", None, 20_000,  9_000_000,  "현대", "포터"),     # 연식 미상 — 하한을 고르면 빠져야 한다
    ("N02", 0,    20_000,  9_000_000,  "기아", "쏘나타"),   # 연식 0 — 하한을 고르면 빠져야 한다
    ("M01", 2020, None,    9_000_000,  "현대", "쏘나타"),   # 주행거리 미상(NULL)
    ("M02", 2020, 0,       9_000_000,  "기아", "포터"),     # 주행거리 0(선박류) — 상한을 고르면 빠져야 한다
    ("M03", 2019, -5,      9_000_000,  "현대", "쏘나타"),   # 주행거리 음수(방어) — 미상과 같은 판정
]
ALL_IDS = {r[0] for r in ROWS}
YEAR_UNKNOWN = {"N01", "N02"}
KM_UNKNOWN = {"M01", "M02", "M03"}
EXPECTED_YEAR = {                          # 누적 — 큰 하한은 작은 하한의 부분집합
    "2015": {"R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "M01", "M02", "M03"},
    "2018": {"R04", "R05", "R06", "R07", "R08", "R09", "R10", "M01", "M02", "M03"},
    "2020": {"R06", "R07", "R08", "R09", "R10", "M01", "M02"},
    "2022": {"R08", "R09", "R10"},
}
EXPECTED_KM = {
    "50000":  {"R01", "R02", "R10", "N01", "N02"},
    "100000": {"R01", "R02", "R10", "N01", "N02", "R03", "R04"},
    "150000": {"R01", "R02", "R10", "N01", "N02", "R03", "R04", "R05", "R06"},
    "200000": {"R01", "R02", "R10", "N01", "N02", "R03", "R04", "R05", "R06", "R07", "R08"},
}
YEAR_COUNTS_ALL = {"2015": 12, "2018": 10, "2020": 7, "2022": 3, None: 2}
KM_COUNTS_ALL = {"50000": 5, "100000": 7, "150000": 9, "200000": 11, None: 3}
KIA = "maker=%EA%B8%B0%EC%95%84"
HYUNDAI = "maker=%ED%98%84%EB%8C%80"


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "yk.db")
    db.init_db()
    for i, (vid, year, km, price, maker, model) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경2{i:04d}", year=year, mileage_km=km,
                               min_sale_price=price, maker=maker, model=model))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app)


def _ids(rows) -> set:
    return {r["id"] for r in rows}


def _list_total(client, url: str) -> int:
    r = client.get(url, headers=_PUBLIC)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    m = re.search(r"window\.NC_LIST_TOTAL=(\d+);", r.text)
    assert m, f"{url}: 목록 총수를 못 찾음"
    return int(m.group(1))


def _api_total(client, qs: str) -> int:
    r = client.get("/api/vehicles/count" + (f"?{qs}" if qs else ""), headers=_PUBLIC)
    assert r.status_code == 200
    return r.json()["total"]


# ── ① 단일 원천 상수 ────────────────────────────────────────────────

def test_options_single_source_shape():
    """지시서 스펙 그대로: 옵션 4개씩·순서·값·라벨. 이 표가 바뀌면 프론트 명세(reports/…feat2-backend)도 바뀐다."""
    assert service.YEAR_MIN_OPTIONS == (
        ("2015", 2015, "2015년 이후"), ("2018", 2018, "2018년 이후"),
        ("2020", 2020, "2020년 이후"), ("2022", 2022, "2022년 이후"),
    )
    assert service.KM_MAX_OPTIONS == (
        ("50000", 50_000, "5만km 이하"), ("100000", 100_000, "10만km 이하"),
        ("150000", 150_000, "15만km 이하"), ("200000", 200_000, "20만km 이하"),
    )
    for opts in (service.YEAR_MIN_OPTIONS, service.KM_MAX_OPTIONS):
        assert isinstance(opts, tuple), "순서 있는 불변 튜플"
        assert [k for k, _v, _l in opts] == [str(v) for _k, v, _l in opts], "key 는 값의 문자열(URL 파라미터 그대로)"
        assert [v for _k, v, _l in opts] == sorted(v for _k, v, _l in opts), "오름차순(누적 옵션)"
    assert service.YEAR_MIN_KEYS == ("2015", "2018", "2020", "2022")
    assert service.KM_MAX_KEYS == ("50000", "100000", "150000", "200000")
    assert service.YEAR_MIN_LABELS["2018"] == "2018년 이후"
    assert service.KM_MAX_LABELS["100000"] == "10만km 이하"


# ── ② 화이트리스트 ──────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["abc", "2018.0", "", " 2018", "2018 ", "02018", "+2018", "2019", "2018;DROP TABLE vehicles",
                                 None, 2018, 2018.0, ["2018"], True])
def test_year_min_value_whitelist_rejects(bad):
    assert service.year_min_value(bad) is None, repr(bad)


@pytest.mark.parametrize("bad", ["abc", "100000.0", "1e5", "", " 100000", "100000 ", "100,000", "10만", "99999",
                                 "100000;DROP TABLE vehicles", None, 100_000, ["100000"], True])
def test_km_max_value_whitelist_rejects(bad):
    assert service.km_max_value(bad) is None, repr(bad)


def test_option_value_accepts_exact_keys():
    for k, v, _l in service.YEAR_MIN_OPTIONS:
        assert service.year_min_value(k) == v
    for k, v, _l in service.KM_MAX_OPTIONS:
        assert service.km_max_value(k) == v


# ── ③ 경계(파이썬 술어) ───────────────────────────────────────────────

@pytest.mark.parametrize("year,ymin,ok", [
    (2018, 2018, True), (2017, 2018, False), (2019, 2018, True), (2015, 2015, True), (2014, 2015, False),
    (2022, 2022, True), (2100, 2015, True), (1, 2015, False),
    (None, 2015, False), (0, 2015, False), (-1, 2015, False),
    ("2020", 2018, True), ("abc", 2018, False), ("", 2018, False), (True, 2015, False),
])
def test_year_min_match_boundaries(year, ymin, ok):
    assert service.year_min_match(year, ymin) is ok


@pytest.mark.parametrize("km,kmax,ok", [
    (100_000, 100_000, True), (100_001, 100_000, False), (99_999, 100_000, True),
    (50_000, 50_000, True), (200_000, 200_000, True), (200_001, 200_000, False), (1, 50_000, True),
    (0, 50_000, False), (None, 50_000, False), (-5, 200_000, False),
    ("90000", 100_000, True), ("abc", 100_000, False), (True, 50_000, False),
])
def test_km_max_match_boundaries(km, kmax, ok):
    assert service.km_max_match(km, kmax) is ok


@pytest.mark.parametrize("km,unknown", [(None, True), (0, True), (-5, True), (1, False), (100_000, False), ("abc", True)])
def test_km_unknown_rule(km, unknown):
    assert service.km_unknown(km) is unknown


# ── ③ DB 층: WHERE 조각(경계·NULL 제외) ─────────────────────────────

def test_list_vehicles_year_min_boundary_and_null_excluded(seeded):
    for key, val, _lbl in service.YEAR_MIN_OPTIONS:
        got = _ids(db.list_vehicles(hide_incomplete=True, year_min=val))
        assert got == EXPECTED_YEAR[key], key
        assert not (got & YEAR_UNKNOWN), f"{key}: 연식 NULL·0 행이 들어왔다"
    # 필터 없음 → NULL·0 포함 전부(기존 호출부 무영향)
    assert _ids(db.list_vehicles(hide_incomplete=True)) == ALL_IDS
    # 누적: 큰 하한 ⊂ 작은 하한
    assert EXPECTED_YEAR["2022"] < EXPECTED_YEAR["2020"] < EXPECTED_YEAR["2018"] < EXPECTED_YEAR["2015"]


def test_list_vehicles_km_max_boundary_and_unknown_excluded(seeded):
    for key, val, _lbl in service.KM_MAX_OPTIONS:
        got = _ids(db.list_vehicles(hide_incomplete=True, km_max=val))
        assert got == EXPECTED_KM[key], key
        assert not (got & KM_UNKNOWN), f"{key}: 주행거리 NULL·0 이하 행이 들어왔다"
    assert "R09" not in EXPECTED_KM["200000"], "20만 초과는 미상이 아니라 '범위 밖'"
    assert EXPECTED_KM["50000"] < EXPECTED_KM["100000"] < EXPECTED_KM["150000"] < EXPECTED_KM["200000"]


def test_list_vehicles_both_axes_and_price(seeded):
    assert _ids(db.list_vehicles(hide_incomplete=True, year_min=2018, km_max=100_000)) == {"R04", "R10"}
    assert _ids(db.list_vehicles(hide_incomplete=True, year_min=2020, km_max=50_000)) == {"R10"}
    assert _ids(db.list_vehicles(hide_incomplete=True, price_min=5_000_000, price_max=10_000_000, year_min=2015)) == \
        {"R02", "M01", "M02", "M03"}
    assert _ids(db.list_vehicles(hide_incomplete=True, price_min=5_000_000, price_max=10_000_000,
                                 year_min=2015, km_max=50_000)) == {"R02"}


# ── ④ SQL 조각 == 파이썬 술어 ──────────────────────────────────────────

def test_python_predicate_agrees_with_sql_fragment(seeded):
    """segment·bucket·usepick·picks 경로는 파이썬으로 거른다 — SQL 과 같은 답이어야 두 경로의 총수가 같다."""
    all_rows = db.list_vehicles(hide_incomplete=True)
    for key, val, _lbl in service.YEAR_MIN_OPTIONS:
        assert _ids(service.filter_year_min(all_rows, key)) == _ids(db.list_vehicles(hide_incomplete=True, year_min=val)), key
    for key, val, _lbl in service.KM_MAX_OPTIONS:
        assert _ids(service.filter_km_max(all_rows, key)) == _ids(db.list_vehicles(hide_incomplete=True, km_max=val)), key
    for yk, yv, _ in service.YEAR_MIN_OPTIONS:
        for kk, kv, _ in service.KM_MAX_OPTIONS:
            assert _ids(service.filter_km_max(service.filter_year_min(all_rows, yk), kk)) == \
                _ids(db.list_vehicles(hide_incomplete=True, year_min=yv, km_max=kv)), (yk, kk)
    assert service.filter_year_min(all_rows, "abc") is all_rows      # 잘못된 key → 그대로
    assert service.filter_year_min(all_rows, "") is all_rows
    assert service.filter_km_max(all_rows, "2018.0") is all_rows
    assert service.filter_km_max(all_rows, "") is all_rows
    assert service.year_min_counts(all_rows) == YEAR_COUNTS_ALL
    assert service.km_max_counts(all_rows) == KM_COUNTS_ALL


# ── ⑤ COUNT 는 한 쿼리 ────────────────────────────────────────────────

class _CountingConn:
    """execute 호출을 세는 커넥션 프록시(PRAGMA 는 connect() 안에서 실행돼 여기 안 잡힌다)."""

    def __init__(self, conn, box):
        self._c, self._box = conn, box

    def execute(self, sql, *a, **k):
        self._box.append(sql)
        return self._c.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._c, name)

    def __enter__(self):
        return self._c.__enter__()

    def __exit__(self, *a):
        return self._c.__exit__(*a)


def test_count_by_year_min_is_one_query_and_matches_lists(seeded, monkeypatch):
    real = db.connect
    box = []
    monkeypatch.setattr(db, "connect", lambda: _CountingConn(real(), box))
    counts = db.count_by_year_min(service.YEAR_MIN_OPTIONS, hide_incomplete=True)
    assert len(box) == 1, box
    assert box[0].count("SUM(CASE WHEN") == len(service.YEAR_MIN_OPTIONS) + 1, "옵션 4개 + 미상 1 을 한 SELECT 로"
    assert "GROUP BY" not in box[0]
    assert counts == YEAR_COUNTS_ALL
    for key, val, _lbl in service.YEAR_MIN_OPTIONS:
        assert counts[key] == len(db.list_vehicles(hide_incomplete=True, year_min=val)), key
    # 항등식(누적이라 합이 아니다): 가장 작은 하한 + 미상 + 그보다 오래된 행(R01) == 총수
    assert counts["2015"] + counts[None] + 1 == len(db.list_vehicles(hide_incomplete=True)) == len(ROWS)


def test_count_by_km_max_is_one_query_and_matches_lists(seeded, monkeypatch):
    real = db.connect
    box = []
    monkeypatch.setattr(db, "connect", lambda: _CountingConn(real(), box))
    counts = db.count_by_km_max(service.KM_MAX_OPTIONS, hide_incomplete=True)
    assert len(box) == 1, box
    assert box[0].count("SUM(CASE WHEN") == len(service.KM_MAX_OPTIONS) + 1
    assert counts == KM_COUNTS_ALL
    for key, val, _lbl in service.KM_MAX_OPTIONS:
        assert counts[key] == len(db.list_vehicles(hide_incomplete=True, km_max=val)), key
    # None 항 = 실제 미상 행 수(M01 NULL · M02 0 · M03 음수) — 공허하지 않다
    assert counts[None] == len(KM_UNKNOWN) == 3
    # 가장 큰 상한 + 미상 + 범위 밖(R09) == 총수
    assert counts["200000"] + counts[None] + 1 == len(ROWS)


def test_count_keeps_zero_options_and_other_filters(seeded):
    """기아 + 5만km 이하 → N02(연식 0) 하나뿐: 옵션 4개가 전부 0 이어도 key 가 있어야 셀렉트가 4칸을 그린다."""
    counts = db.count_by_year_min(service.YEAR_MIN_OPTIONS, hide_incomplete=True, maker="기아", km_max=50_000)
    assert counts == {"2015": 0, "2018": 0, "2020": 0, "2022": 0, None: 1}
    assert set(counts) == set(service.YEAR_MIN_KEYS) | {None}
    # 현대 + 2020년 이후(R06·R08·R10·M01·M03 아님(2019)) → 주행: ≤5만 R10 · ≤15만 +R06 · ≤20만 +R08 · 미상 M01
    counts = db.count_by_km_max(service.KM_MAX_OPTIONS, hide_incomplete=True, maker="현대", year_min=2020)
    assert counts == {"50000": 1, "100000": 1, "150000": 2, "200000": 3, None: 1}


def test_count_rejects_own_axis_but_accepts_the_other_two(seeded):
    with pytest.raises(TypeError):
        db.count_by_year_min(service.YEAR_MIN_OPTIONS, hide_incomplete=True, year_min=2018)
    with pytest.raises(TypeError):
        db.count_by_km_max(service.KM_MAX_OPTIONS, hide_incomplete=True, km_max=100_000)
    # 다른 두 축은 필터로 받는다(패싯 규칙) — 가격대 COUNT 도 새 두 축을 받는다
    assert db.count_by_year_min(service.YEAR_MIN_OPTIONS, hide_incomplete=True, km_max=100_000,
                                price_min=0, price_max=5_000_000) == {"2015": 0, "2018": 0, "2020": 0, "2022": 0, None: 0}
    pb = db.count_by_price_band(service.PRICE_BANDS, hide_incomplete=True, year_min=2018, km_max=100_000)
    assert pb == {"0-500": 0, "500-1000": 0, "1000-2000": 1, "2000-3000": 0, "3000-": 0, None: 1}


# ── ② 라우트: 잘못된 값 → 200·필터 무시 ────────────────────────────────

@pytest.mark.parametrize("qs", [
    "year_min=abc", "year_min=2018.0", "year_min=", "year_min=2019", "year_min=%202018", "year_min=02018",
    "year_min=2018&year_min=2020", "year_min=2018&year_min=2018", "year_min=2018;DROP%20TABLE%20vehicles",
    "km_max=abc", "km_max=100000.0", "km_max=1e5", "km_max=", "km_max=100,000", "km_max=99999",
    "km_max=100000&km_max=50000", "km_max=100000&km_max=100000", "km_max=%20100000",
    "year_min=abc&km_max=abc",
])
def test_invalid_params_are_ignored_not_500(client, qs):
    assert _list_total(client, f"/vehicles?{qs}") == len(ROWS), qs
    assert _api_total(client, qs) == len(ROWS), qs
    assert len(db.list_vehicles()) == len(ROWS), "테이블이 그대로다(바인딩 파라미터 — 주입 불가)"


# ── ⑥ 총수 일치: /vehicles == /api/vehicles/count ──────────────────────

@pytest.mark.parametrize("qs,expect", [
    ("year_min=2015", 12), ("year_min=2018", 10), ("year_min=2020", 7), ("year_min=2022", 3),   # SQL 경로
    ("km_max=50000", 5), ("km_max=100000", 7), ("km_max=150000", 9), ("km_max=200000", 11),
    ("year_min=2018&km_max=100000", 2),                       # R04·R10
    ("year_min=2020&km_max=50000", 1),                        # R10
    ("price=500-1000&year_min=2015", 4),                      # 가격대 + 연식: R02·M01·M02·M03
    ("price=500-1000&year_min=2015&km_max=50000", 1),         # 축 3종 AND: R02
    (f"{KIA}&year_min=2020", 3),                              # 기아: R07·R09·M02
    (f"{HYUNDAI}&km_max=50000", 4),                           # 현대: R01·R02·R10·N01
    ("year_min=2018&sort=mileage", 10),                       # 정렬과 무관
    ("year_min=2018&segment=commercial", 4),                  # 파이썬 경로(차종): R04·R06·R09·M02
    ("km_max=150000&segment=commercial", 3),                  # R04·R06·N01
    ("year_min=2018&km_max=150000&segment=commercial", 2),    # R04·R06
    ("km_max=50000&segment=commercial&price=1000-2000", 0),   # 파이썬 경로 0건도 200
    ("year_min=2022&picks=1", 0),                             # picks 경로(백테스트 표본 없음 → 유망 0) — 500 금지
])
def test_list_total_equals_count_api(client, qs, expect):
    assert _list_total(client, f"/vehicles?{qs}") == expect, qs
    assert _api_total(client, qs) == expect, qs


def test_existing_filters_regression_with_and_without_axes(client):
    """기존 필터가 그대로(축을 안 고르면 이전과 같은 수), 축은 그 위에 AND 로 얹힌다."""
    assert _list_total(client, f"/vehicles?{KIA}") == 6 == _api_total(client, KIA)
    assert _list_total(client, f"/vehicles?{KIA}&year_min=2022") == 1                   # R09
    assert _list_total(client, f"/vehicles?{KIA}&km_max=50000") == 1                    # N02
    assert _list_total(client, f"/vehicles?{KIA}&year_min=2015&km_max=50000") == 0
    assert _list_total(client, "/vehicles") == len(ROWS) == _api_total(client, "")
    assert _list_total(client, "/vehicles?price=1000-2000") == 3 == _api_total(client, "price=1000-2000")  # FEAT-1 그대로


# ── ⑦⑧⑨ 템플릿 컨텍스트 계약(프론트가 쓰는 변수) ───────────────────────

def _capture_ctx(monkeypatch):
    import web.app as A
    box = {}
    real = A.templates.TemplateResponse

    def spy(name, ctx, *a, **k):
        if name == "vehicles.html":
            box.update(ctx)
        return real(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", spy)
    return box


def _counts(opts) -> list:
    return [o["count"] for o in opts]


def test_template_context_contract_sql_path(client, monkeypatch):
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?year_min=2018&km_max=100000&page=1", headers=_PUBLIC).status_code == 200
    assert ctx["year_min"] == "2018" and ctx["km_max"] == "100000"
    assert [o["key"] for o in ctx["year_options"]] == list(service.YEAR_MIN_KEYS)
    assert [o["label"] for o in ctx["year_options"]] == [o[2] for o in service.YEAR_MIN_OPTIONS]
    assert [o["key"] for o in ctx["km_options"]] == list(service.KM_MAX_KEYS)
    assert [o["label"] for o in ctx["km_options"]] == [o[2] for o in service.KM_MAX_OPTIONS]
    assert ctx["total"] == 2                                                  # R04·R10
    # 패싯 규칙: 연식 건수는 주행거리(≤10만) 모수에서, 주행거리 건수는 연식(2018+) 모수에서 — 선택 옵션 count == total
    assert _counts(ctx["year_options"]) == [4, 2, 1, 1]                       # ≤10만: R01·R02·R03·R04·R10·N01·N02
    assert _counts(ctx["km_options"]) == [1, 2, 4, 6]                         # 2018+: R04~R10·M01~M03
    assert next(o["count"] for o in ctx["year_options"] if o["key"] == ctx["year_min"]) == ctx["total"]
    assert next(o["count"] for o in ctx["km_options"] if o["key"] == ctx["km_max"]) == ctx["total"]
    # 가격대 셀렉트도 두 축을 반영(R04 1,540만 → 1,000~2,000만 · R10 최저가 NULL)
    assert _counts(ctx["price_bands"]) == [0, 0, 1, 0, 0]
    # 주행거리 미상 = 주행거리 축만 뺀 모수(2018+)의 NULL·0 이하 = M01·M02·M03
    assert ctx["km_unknown_excluded"] == 3
    # qs(페이지네이션·정렬 링크·UX-5 요약·검색 저장)는 두 키를 **유지**, qs_no_* 는 자기 키만 뺀다
    assert "year_min=2018" in ctx["qs"] and "km_max=100000" in ctx["qs"]
    assert "year_min=" not in ctx["qs_no_year_min"] and "km_max=100000" in ctx["qs_no_year_min"]
    assert "km_max=" not in ctx["qs_no_km_max"] and "year_min=2018" in ctx["qs_no_km_max"]
    assert "year_min=2018" in ctx["qs_no_price"] and "km_max=100000" in ctx["qs_no_price"]
    assert "year_min=2018" in ctx["qs_no_q"] and "km_max=100000" in ctx["qs_no_date"]   # UX-1 칩 ✕ 링크도 두 키를 보존


def test_template_context_contract_python_path(client, monkeypatch):
    """segment(파이썬 필터)와 함께면 축별 건수도 그 필터를 반영해야 라벨 숫자가 목록과 맞는다."""
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?segment=commercial&year_min=2018&km_max=150000", headers=_PUBLIC).status_code == 200
    # 상용(포터): R04(2018·10만) R06(2020·15만) R09(2024·20만+) N01(연식 NULL·2만) M02(2020·0)
    assert ctx["total"] == 2 and ctx["year_min"] == "2018" and ctx["km_max"] == "150000"
    assert _counts(ctx["year_options"]) == [2, 2, 1, 0]        # ≤15만 모수 R04·R06·N01
    assert _counts(ctx["km_options"]) == [0, 1, 2, 2]          # 2018+ 모수 R04·R06·R09·M02
    assert ctx["km_unknown_excluded"] == 1                     # M02
    assert _counts(ctx["price_bands"]) == [0, 0, 1, 1, 0]      # 두 축 적용 R04·R06


def test_template_context_when_no_selection(client, monkeypatch):
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?year_min=abc&km_max=2018", headers=_PUBLIC).status_code == 200
    assert ctx["year_min"] == "" and ctx["km_max"] == ""
    assert "year_min=" not in ctx["qs"] and "km_max=" not in ctx["qs"]
    assert ctx["qs_no_year_min"] == ctx["qs"] == ctx["qs_no_km_max"]
    assert _counts(ctx["year_options"]) == [12, 10, 7, 3]
    assert _counts(ctx["km_options"]) == [5, 7, 9, 11]
    assert ctx["km_unknown_excluded"] == 3, "안 골라도 '고르면 빠질 건수'를 준다(툴팁용) — 같은 모수"
    assert ctx["total"] == len(ROWS)
    assert len(ctx["year_options"]) == 4 and len(ctx["km_options"]) == 4


def test_facet_counts_predict_switch_totals(client, monkeypatch):
    """다른 옵션의 count 는 '그 옵션으로 바꾸면 나올 총수'다 — 축 둘 다, 다른 축·제조사가 걸린 채로."""
    ctx = _capture_ctx(monkeypatch)
    base = f"{HYUNDAI}&km_max=150000"
    assert client.get(f"/vehicles?{base}&year_min=2020", headers=_PUBLIC).status_code == 200
    year_counts = {o["key"]: o["count"] for o in ctx["year_options"]}
    assert sum(year_counts.values()) > 0, "전제: 공허하지 않다"
    for key, n in year_counts.items():
        assert _list_total(client, f"/vehicles?{base}&year_min={key}") == n == _api_total(client, f"{base}&year_min={key}"), key
    base = f"{HYUNDAI}&year_min=2015"
    ctx.clear()
    assert client.get(f"/vehicles?{base}&km_max=50000", headers=_PUBLIC).status_code == 200
    km_counts = {o["key"]: o["count"] for o in ctx["km_options"]}
    assert sum(km_counts.values()) > 0
    for key, n in km_counts.items():
        assert _list_total(client, f"/vehicles?{base}&km_max={key}") == n == _api_total(client, f"{base}&km_max={key}"), key
    # 축을 바꿔도 다른 축의 셀렉트 숫자는 그대로(자기 축은 모수에서 빠지므로)
    ctx.clear()
    assert client.get(f"/vehicles?{base}&km_max=200000", headers=_PUBLIC).status_code == 200
    assert {o["key"]: o["count"] for o in ctx["km_options"]} == km_counts


def test_km_unknown_excluded_is_exactly_what_the_filter_drops(client, monkeypatch):
    """km_max 를 고르면 목록에서 빠지는 행 = 상한 초과 + 미상. 미상 수가 km_unknown_excluded 다(제조사·연식이 걸린 채로도)."""
    ctx = _capture_ctx(monkeypatch)
    for base, kw in ((f"{HYUNDAI}&year_min=2018&", dict(maker="현대", year_min=2018)), ("", {})):
        ctx.clear()
        assert client.get(f"/vehicles?{base}km_max=200000", headers=_PUBLIC).status_code == 200
        basis = db.list_vehicles(hide_incomplete=True, **kw)
        unknown = [r for r in basis if service.km_unknown(r.get("mileage_km"))]
        over = [r for r in basis if not service.km_unknown(r.get("mileage_km")) and r["mileage_km"] > 200_000]
        assert ctx["km_unknown_excluded"] == len(unknown), base
        assert ctx["total"] == len(basis) - len(unknown) - len(over), base
        assert all(not service.km_unknown(r.get("mileage_km")) for r in ctx["rows"]), "페이지 행에 미상이 없다"


def test_sql_path_adds_exactly_two_facet_queries_and_python_path_none(client, monkeypatch):
    """요청당 DB 쿼리: SQL 경로는 축별 COUNT 3개(가격대 GROUP BY 1 + SUM(CASE) 2) / 파이썬 경로는 0."""
    real = db.connect
    box = []
    monkeypatch.setattr(db, "connect", lambda: _CountingConn(real(), box))
    client.get("/vehicles?year_min=2018", headers=_PUBLIC)          # 워밍업(캐시 채움)
    box.clear()
    assert client.get("/vehicles?year_min=2018&km_max=100000", headers=_PUBLIC).status_code == 200
    assert sum("SUM(CASE WHEN" in s for s in box) == 2, [s[:60] for s in box]
    assert sum("GROUP BY band" in s for s in box) == 1
    box.clear()
    assert client.get("/vehicles?segment=commercial&year_min=2018", headers=_PUBLIC).status_code == 200
    assert sum("SUM(CASE WHEN" in s for s in box) == 0 and sum("GROUP BY band" in s for s in box) == 0
    box.clear()
    assert client.get("/api/vehicles/count?year_min=2018&km_max=100000", headers=_PUBLIC).status_code == 200
    assert sum("SUM(CASE WHEN" in s for s in box) == 0 and len(box) == 1


# ── ⑥⑦ 파이썬 경로(usepick·bucket): 갈래 판정은 축 3종 적용 전 모수에서 한 번만 ──────────
# 백테스트 표본이 있어야 갈래가 생기므로 대시보드 패리티 픽스처의 BT 를 빌려 쓰되, 행은 연식·주행거리를 달리 심는다
# (패리티 픽스처는 전부 year=2020·mileage NULL 이라 그대로 쓰면 연식은 전부 통과·주행거리는 전부 0건 — 공허 통과).
from tests.test_dashboard_link_parity import BT as _PARITY_BT  # noqa: E402

USE_ROWS = [
    # (id, 연식, 주행거리) — U*: '지금 사면 이득' 후보(min 1,600만 · 시세 4,000만) / C*: '싸게 낙찰되면 이득' 후보 / W*: 유찰 대기(비추천)
    ("U01", 2014, 40_000), ("U02", 2019, 90_000), ("U03", 2021, 140_000), ("U04", 2023, None), ("U05", 2018, 100_000),
    ("C01", 2017, 120_000), ("C02", 2020, 0), ("C03", 2022, 30_000),
    ("W01", 2015, 50_000), ("W02", None, 200_000), ("W03", 2024, 10_000),
]


@pytest.fixture
def use_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "use.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: _PARITY_BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1", "sale_date": "2999-01-01",
            "status": "완료", "fail_count": 1, "market_confidence_label": "높음", "judgment": "유찰 대기"}
    money = {"U": dict(min_sale_price=16_000_000, appraisal_value=30_000_000, median_price=40_000_000),
             "C": dict(min_sale_price=28_000_000, appraisal_value=38_000_000, median_price=40_000_000),
             "W": dict(min_sale_price=39_000_000, appraisal_value=40_000_000, median_price=40_000_000)}
    for i, (vid, year, km) in enumerate(USE_ROWS):
        db.upsert_vehicle(dict(base, **money[vid[0]], id=vid, case_no=f"2026타경3{i:04d}", year=year, mileage_km=km))
    import web.app as A
    return TestClient(A.app)


def test_use_fixture_is_not_void(use_client):
    """전제: 픽스처가 두 갈래를 실제로 만든다(PANEL-46 자기 유효성)."""
    assert _api_total(use_client, "usepick=now") >= 4
    assert _api_total(use_client, "usepick=cheap") >= 2
    assert _api_total(use_client, "bucket=wait") >= 2


@pytest.mark.parametrize("qs", [
    "usepick=1&year_min=2018", "usepick=1&km_max=100000", "usepick=1&year_min=2020&km_max=150000",
    "usepick=now&year_min=2018&km_max=100000", "usepick=cheap&km_max=150000", "usepick=cheap&year_min=2022",
    "bucket=wait&year_min=2015", "bucket=wait&km_max=50000", "bucket=usepick&year_min=2018&km_max=150000",
    "usepick=1&price=1000-2000&year_min=2018&km_max=100000",
])
def test_usepick_and_bucket_paths_agree_with_count_api(use_client, qs):
    assert _list_total(use_client, f"/vehicles?{qs}") == _api_total(use_client, qs), qs


def test_usepick_facets_are_consistent_with_year_and_km(use_client, monkeypatch):
    """usepick 페이지에서 연식·주행거리를 고르면 ① 갈래 칩 수(use_counts)가 두 축을 반영하고 ② 축별 건수는 갈래를
    반영한다(패싯 규칙) ③ 선택 옵션 count == total ④ 페이지 행 전부 조건을 만족."""
    ctx = _capture_ctx(monkeypatch)
    base_total = _list_total(use_client, "/vehicles?usepick=1")
    assert base_total > 0
    assert use_client.get("/vehicles?usepick=1", headers=_PUBLIC).status_code == 200
    year_no_sel = {o["key"]: o["count"] for o in ctx["year_options"]}
    km_no_sel = {o["key"]: o["count"] for o in ctx["km_options"]}
    unknown_no_sel = ctx["km_unknown_excluded"]
    assert 0 < year_no_sel["2015"] < base_total, "픽스처: 최소 한 추천 행은 2015 미만(U01 2014) — 가장 작은 하한도 진부분집합"
    assert 0 < km_no_sel["50000"] < km_no_sel["200000"], "누적 옵션이 실제로 층을 이룬다"
    assert unknown_no_sel >= 1, "U04(NULL)·C02(0) 중 최소 하나는 추천에 든다"
    for key, n in year_no_sel.items():
        ctx.clear()
        assert use_client.get(f"/vehicles?usepick=1&year_min={key}", headers=_PUBLIC).status_code == 200
        assert ctx["total"] == n == ctx["use_counts"]["all"], key
        assert ctx["use_counts"]["now"] + ctx["use_counts"]["cheap"] == n, key
        assert {o["key"]: o["count"] for o in ctx["year_options"]} == year_no_sel, key   # 자기 축은 모수에서 빠진다
        assert all(service.year_min_match(r["year"], int(key)) for r in ctx["rows"]), key
    for key, n in km_no_sel.items():
        ctx.clear()
        assert use_client.get(f"/vehicles?usepick=1&km_max={key}", headers=_PUBLIC).status_code == 200
        assert ctx["total"] == n == ctx["use_counts"]["all"], key
        assert {o["key"]: o["count"] for o in ctx["km_options"]} == km_no_sel, key
        assert ctx["km_unknown_excluded"] == unknown_no_sel, key
        assert all(service.km_max_match(r["mileage_km"], int(key)) for r in ctx["rows"]), key
    # 두 축 동시: 연식 셀렉트 숫자는 주행거리를, 주행거리 셀렉트 숫자는 연식을 반영한다
    ctx.clear()
    assert use_client.get("/vehicles?usepick=1&year_min=2018&km_max=150000", headers=_PUBLIC).status_code == 200
    assert ctx["total"] == ctx["use_counts"]["all"]
    assert next(o["count"] for o in ctx["year_options"] if o["key"] == "2018") == ctx["total"]
    assert next(o["count"] for o in ctx["km_options"] if o["key"] == "150000") == ctx["total"]
    assert {o["key"]: o["count"] for o in ctx["year_options"]} != year_no_sel, "주행거리 상한이 연식 셀렉트 숫자를 바꿨다"


# ── ⑩ 반증: WHERE 조각이 실제로 일을 한다 ─────────────────────────────

_ANCHORS = ('where.append("year >= ?"); params.append(int(year_min))',
            'where.append("mileage_km > 0 AND mileage_km <= ?"); params.append(int(km_max))')


def test_where_fragments_are_load_bearing(seeded):
    """`db._vehicles_where` 원문에서 두 조각을 지운 변이체를 메모리에서 만들어 실행한다(파일은 안 건드린다).
    변이체는 같은 인자로 15행 전부(NULL·0·범위 밖 포함)를 돌려주고, 원본은 R04·R10 만 돌려준다 —
    즉 위의 경계·NULL 테스트는 이 두 줄이 없으면 반드시 빨간불이다."""
    src = textwrap.dedent(inspect.getsource(db._vehicles_where))
    for a in _ANCHORS:
        assert a in src, f"앵커가 사라졌다 — 조각 문장을 바꿨으면 이 테스트의 _ANCHORS 도 함께 바꿔라: {a}"
    mutant_src = src
    for a in _ANCHORS:
        mutant_src = mutant_src.replace(a, "pass")
    ns = dict(vars(db))
    exec(compile(mutant_src, "<mutant _vehicles_where>", "exec"), ns)
    mutant = ns["_vehicles_where"]

    def _run(fn):
        where, params = fn(hide_incomplete=True, year_min=2018, km_max=100_000)
        conn = db.connect()
        try:
            return {r["id"] for r in conn.execute(
                "SELECT id FROM vehicles WHERE " + " AND ".join(where), params)}
        finally:
            conn.close()

    real_where, real_params = db._vehicles_where(year_min=2018, km_max=100_000)
    mut_where, _ = mutant(year_min=2018, km_max=100_000)
    assert real_where == ["year >= ?", "mileage_km > 0 AND mileage_km <= ?"] and real_params == [2018, 100_000]
    assert mut_where == []
    assert _run(db._vehicles_where) == {"R04", "R10"}
    assert _run(mutant) == ALL_IDS, "조각이 없으면 NULL·0·범위 밖이 전부 새어 나온다"
    # 조각 하나만 지운 변이체도 각각 잡힌다(둘이 서로를 가리지 않는다)
    for a, leak in zip(_ANCHORS, ({"R04", "R10", "N01", "N02", "R01", "R02", "R03"},        # 연식 조각 없음 → ≤10만 전부
                                  {"R04", "R05", "R06", "R07", "R08", "R09", "R10", "M01", "M02", "M03"})):  # 주행 조각 없음 → 2018+ 전부
        ns = dict(vars(db))
        exec(compile(src.replace(a, "pass"), "<mutant one>", "exec"), ns)
        assert _run(ns["_vehicles_where"]) == leak, a
