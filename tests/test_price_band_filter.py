"""FEAT-1 가격대 필터(최저매각가 5구간) — 서버 쪽 계약 (오너 승인 2026-09-26, 지시서 2026-09-26-12).

축은 **최저매각가**(min_sale_price)다. 감정가·시세가 아니다. 구간은 반열림 [lo, hi) — 정확히 5,000,000 은
'500~1,000만'. 구간 정의는 `service.PRICE_BANDS` 하나이고 라우트·COUNT·템플릿·이 파일이 전부 그것을 본다.

이 파일이 지키는 것:
  ① 경계값·NULL 제외(SQL 조각과 파이썬 술어가 같은 답)   ② 잘못된 key(abc·주입 문자열·빈값·중복) → 200·필터 무시
  ③ `/vehicles` 총수 == `/api/vehicles/count`(SQL 경로·파이썬 경로 모두)   ④ 구간 COUNT 합 + NULL == 필터 총수(한 쿼리)
  ⑤ 기존 필터 회귀(제조사+가격대)   ⑥ 템플릿 컨텍스트 계약(price·price_bands·qs_no_price·qs)
  ⑦ 반증 — WHERE 조각을 지운 변이체는 NULL·다른 구간 행을 돌려준다(조각이 실제로 일을 한다)
"""
import inspect
import re
import textwrap

import pytest
from starlette.testclient import TestClient

from web import db, service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님)
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "sale_date": "2999-01-01",
        "status": "완료", "fail_count": 1, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, 최저매각가, 제조사, 모델) — 경계마다 양쪽에 한 행씩. 모델 '포터'는 segment=commercial(파이썬 필터) 검증용.
ROWS = [
    ("A0", 0,           "현대", "쏘나타"),   # 0 도 값이다 → '~500만'
    ("A1", 4_999_999,   "현대", "쏘나타"),
    ("B1", 5_000_000,   "기아", "쏘나타"),   # ★ 경계: 정확히 500만은 '500~1,000만'
    ("B2", 9_999_999,   "기아", "쏘나타"),
    ("C1", 10_000_000,  "현대", "쏘나타"),
    ("C2", 15_400_000,  "현대", "포터"),     # 라이브 중앙값 1,540만
    ("C3", 19_999_999,  "현대", "쏘나타"),
    ("D1", 20_000_000,  "기아", "쏘나타"),
    ("D2", 29_999_999,  "기아", "포터"),
    ("E1", 30_000_000,  "현대", "쏘나타"),   # ★ 경계: 정확히 3,000만은 '3,000만~'
    ("E2", 100_000_000, "현대", "포터"),
    ("N1", None,        "현대", "쏘나타"),   # 최저가 미상 — 구간을 고르면 빠져야 한다
    ("N2", None,        "기아", "포터"),
]
EXPECTED = {"0-500": {"A0", "A1"}, "500-1000": {"B1", "B2"}, "1000-2000": {"C1", "C2", "C3"},
            "2000-3000": {"D1", "D2"}, "3000-": {"E1", "E2"}}
NULL_IDS = {"N1", "N2"}
ALL_IDS = {r[0] for r in ROWS}


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pb.db")
    db.init_db()
    for i, (vid, price, maker, model) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경1{i:04d}",
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


# ── 단일 원천 상수 ────────────────────────────────────────────────────

def test_price_bands_single_source_shape():
    """지시서 스펙 그대로: 5구간·순서·경계·라벨. 이 표가 바뀌면 프론트 명세(reports/…feat1-backend)도 바뀐다."""
    assert service.PRICE_BANDS == (
        ("0-500", 0, 5_000_000, "~500만"),
        ("500-1000", 5_000_000, 10_000_000, "500~1,000만"),
        ("1000-2000", 10_000_000, 20_000_000, "1,000~2,000만"),
        ("2000-3000", 20_000_000, 30_000_000, "2,000~3,000만"),
        ("3000-", 30_000_000, None, "3,000만~"),
    )
    assert isinstance(service.PRICE_BANDS, tuple), "순서 있는 불변 튜플"
    # 빈틈·겹침 없이 이어진다(앞 구간 hi == 다음 구간 lo), 마지막만 상한 없음
    for (k1, lo1, hi1, _), (k2, lo2, hi2, _) in zip(service.PRICE_BANDS, service.PRICE_BANDS[1:]):
        assert hi1 == lo2, (k1, k2)
    assert service.PRICE_BANDS[0][1] == 0 and service.PRICE_BANDS[-1][2] is None
    assert service.PRICE_BAND_KEYS == tuple(b[0] for b in service.PRICE_BANDS)
    assert service.PRICE_BAND_LABELS["500-1000"] == "500~1,000만"


def test_price_band_range_whitelist():
    assert service.price_band_range("0-500") == (0, 5_000_000)
    assert service.price_band_range("500-1000") == (5_000_000, 10_000_000)
    assert service.price_band_range("3000-") == (30_000_000, None)
    for bad in ("abc", "0-500;DROP TABLE vehicles", "", " 0-500", "0-500 ", "500-1000x",
                None, 0, 5_000_000, ["0-500"]):
        assert service.price_band_range(bad) is None, repr(bad)


@pytest.mark.parametrize("price,key", [
    (0, "0-500"), (4_999_999, "0-500"),
    (5_000_000, "500-1000"), (9_999_999, "500-1000"),
    (10_000_000, "1000-2000"), (19_999_999, "1000-2000"),
    (20_000_000, "2000-3000"), (29_999_999, "2000-3000"),
    (30_000_000, "3000-"), (10 ** 9, "3000-"),
    (None, None), ("", None), ("abc", None), (True, None),
])
def test_price_band_key_boundaries(price, key):
    assert service.price_band_key(price) == key


# ── DB 층: WHERE 조각 ────────────────────────────────────────────────

def test_list_vehicles_band_filter_boundary_and_null_excluded(seeded):
    seen = set()
    for key, lo, hi, _lbl in service.PRICE_BANDS:
        got = _ids(db.list_vehicles(hide_incomplete=True, price_min=lo, price_max=hi))
        assert got == EXPECTED[key], key
        assert not (got & NULL_IDS), f"{key}: 최저가 NULL 행이 구간에 들어왔다"
        seen |= got
    assert seen == ALL_IDS - NULL_IDS
    # 필터 없음(둘 다 None) → NULL 포함 전부 — 기존 호출부에 영향 없음
    assert _ids(db.list_vehicles(hide_incomplete=True)) == ALL_IDS
    # 0 은 값이다(truthiness 로 무시되면 안 됨): price_min=0 만 줘도 NULL 은 빠진다
    assert _ids(db.list_vehicles(hide_incomplete=True, price_min=0)) == ALL_IDS - NULL_IDS


def test_python_predicate_agrees_with_sql_fragment(seeded):
    """segment·bucket·usepick·picks 경로는 파이썬으로 거른다 — SQL 과 같은 답이어야 두 경로의 총수가 같다."""
    all_rows = db.list_vehicles(hide_incomplete=True)
    for key, lo, hi, _lbl in service.PRICE_BANDS:
        assert _ids(service.filter_price_band(all_rows, key)) == \
            _ids(db.list_vehicles(hide_incomplete=True, price_min=lo, price_max=hi)), key
    assert service.filter_price_band(all_rows, "abc") is all_rows      # 잘못된 key → 그대로
    assert service.filter_price_band(all_rows, "") is all_rows
    counts = service.price_band_counts(all_rows)
    assert counts == {"0-500": 2, "500-1000": 2, "1000-2000": 3, "2000-3000": 2, "3000-": 2, None: 2}


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


def test_count_by_price_band_is_one_query_and_sums_to_total(seeded, monkeypatch):
    real = db.connect
    box = []
    monkeypatch.setattr(db, "connect", lambda: _CountingConn(real(), box))
    counts = db.count_by_price_band(service.PRICE_BANDS, hide_incomplete=True)
    assert len(box) == 1, box
    assert "CASE" in box[0] and "GROUP BY" in box[0]
    assert counts == {"0-500": 2, "500-1000": 2, "1000-2000": 3, "2000-3000": 2, "3000-": 2, None: 2}
    assert sum(v for k, v in counts.items() if k is not None) + counts[None] == \
        len(db.list_vehicles(hide_incomplete=True))
    # 구간마다 COUNT == 같은 필터 + 그 구간 WHERE 조각의 목록 건수
    for key, lo, hi, _lbl in service.PRICE_BANDS:
        assert counts[key] == len(db.list_vehicles(hide_incomplete=True, price_min=lo, price_max=hi)), key


def test_count_by_price_band_keeps_zero_bands_and_other_filters(seeded):
    """기아만: ~500만·1,000~2,000만·3,000만~ 은 0 건이어도 key 가 있어야 셀렉트가 5칸을 그린다."""
    counts = db.count_by_price_band(service.PRICE_BANDS, hide_incomplete=True, maker="기아")
    assert counts == {"0-500": 0, "500-1000": 2, "1000-2000": 0, "2000-3000": 2, "3000-": 0, None: 1}
    assert set(counts) == set(service.PRICE_BAND_KEYS) | {None}
    assert sum(counts.values()) == len(db.list_vehicles(hide_incomplete=True, maker="기아")) == 5


def test_count_by_price_band_rejects_price_filter(seeded):
    with pytest.raises(TypeError):
        db.count_by_price_band(service.PRICE_BANDS, hide_incomplete=True, price_min=0)


# ── 라우트: 화이트리스트·총수 일치 ──────────────────────────────────────

@pytest.mark.parametrize("qs", [
    "price=abc", "price=0-500;DROP%20TABLE%20vehicles", "price=", "price=0-500&price=500-1000",
    "price=0-500&price=0-500", "price=%200-500", "price=3000-x",
])
def test_invalid_price_param_is_ignored_not_500(client, qs):
    assert _list_total(client, f"/vehicles?{qs}") == len(ROWS), qs
    assert _api_total(client, qs) == len(ROWS), qs
    assert len(db.list_vehicles()) == len(ROWS), "테이블이 그대로다(바인딩 파라미터 — 주입 불가)"


@pytest.mark.parametrize("qs,expect", [
    ("price=1000-2000", 3),                          # SQL 경로
    ("price=3000-&maker=%ED%98%84%EB%8C%80", 2),     # SQL 경로 + 제조사(현대)
    ("price=500-1000&maker=%EA%B8%B0%EC%95%84", 2),  # SQL 경로 + 제조사(기아)
    ("price=1000-2000&segment=commercial", 1),       # 파이썬 경로(차종) — 포터 C2 만
    ("price=0-500&segment=commercial", 0),           # 파이썬 경로 0건도 200
    ("price=2000-3000&sort=min_sale_price", 2),      # 정렬과 무관
    ("price=3000-&picks=1", 0),                      # picks 경로(백테스트 표본 없음 → 유망 0) — 500 금지
])
def test_list_total_equals_count_api(client, qs, expect):
    assert _list_total(client, f"/vehicles?{qs}") == expect, qs
    assert _api_total(client, qs) == expect, qs


def test_maker_filter_regression_with_and_without_price(client):
    """기존 필터가 그대로 동작하고(가격대 없으면 이전과 같은 수), 가격대는 그 위에 AND 로 얹힌다."""
    kia = "maker=%EA%B8%B0%EC%95%84"
    assert _list_total(client, f"/vehicles?{kia}") == 5 == _api_total(client, kia)
    assert _list_total(client, f"/vehicles?{kia}&price=2000-3000") == 2
    assert _list_total(client, f"/vehicles?{kia}&price=0-500") == 0
    assert _list_total(client, "/vehicles") == len(ROWS) == _api_total(client, "")


# ── 템플릿 컨텍스트 계약(프론트가 쓰는 변수) ───────────────────────────

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


def test_template_context_contract_sql_path(client, monkeypatch):
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?price=1000-2000&maker=%ED%98%84%EB%8C%80&page=1", headers=_PUBLIC).status_code == 200
    assert ctx["price"] == "1000-2000"
    assert [b["key"] for b in ctx["price_bands"]] == list(service.PRICE_BAND_KEYS)
    assert [b["label"] for b in ctx["price_bands"]] == [b[3] for b in service.PRICE_BANDS]
    # 현대 8행: ~500만 2 · 500~1,000만 0 · 1,000~2,000만 3 · 2,000~3,000만 0 · 3,000만~ 2 (+NULL 1)
    assert [b["count"] for b in ctx["price_bands"]] == [2, 0, 3, 0, 2]
    # 선택 구간의 count == 목록 총수(패싯 규칙: 가격만 뺀 나머지 필터로 센다)
    assert ctx["total"] == 3 == next(b["count"] for b in ctx["price_bands"] if b["key"] == ctx["price"])
    # qs(페이지네이션·정렬 링크)는 price 를 **유지**, qs_no_price 는 price 만 뺀다
    assert "price=1000-2000" in ctx["qs"] and "maker=" in ctx["qs"]
    assert "price=" not in ctx["qs_no_price"] and "maker=" in ctx["qs_no_price"]


def test_template_context_contract_python_path(client, monkeypatch):
    """segment(파이썬 필터)와 함께면 구간별 건수도 그 필터를 반영해야 라벨 숫자가 목록과 맞는다."""
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?price=1000-2000&segment=commercial", headers=_PUBLIC).status_code == 200
    # 상용(포터) C2·D2·E2·N2 → 1,000~2,000만 1 · 2,000~3,000만 1 · 3,000만~ 1
    assert [b["count"] for b in ctx["price_bands"]] == [0, 0, 1, 1, 1]
    assert ctx["total"] == 1 and ctx["price"] == "1000-2000"


def test_template_context_when_no_price(client, monkeypatch):
    ctx = _capture_ctx(monkeypatch)
    assert client.get("/vehicles?price=abc", headers=_PUBLIC).status_code == 200
    assert ctx["price"] == "" and "price=" not in ctx["qs"]
    assert [b["count"] for b in ctx["price_bands"]] == [2, 2, 3, 2, 2]
    assert sum(b["count"] for b in ctx["price_bands"]) + len(NULL_IDS) == ctx["total"] == len(ROWS)


# ── 파이썬 경로(usepick·bucket): 갈래 판정을 가격대 적용 전 모수에서 한 번만 하도록 재배선했다 ──
# 백테스트 표본이 있어야 갈래가 생기므로 대시보드 패리티 테스트의 픽스처(BT + 66행)를 빌려 쓴다.
from tests.test_dashboard_link_parity import client as parity_client  # noqa: E402,F401  (픽스처 등록)


@pytest.mark.parametrize("qs", [
    "usepick=1&price=1000-2000", "usepick=1&price=2000-3000", "usepick=cheap&price=2000-3000",
    "usepick=now&price=1000-2000", "usepick=1&price=0-500", "bucket=wait&price=3000-",
    "bucket=wait&price=0-500", "bucket=usepick&price=1000-2000",
])
def test_usepick_and_bucket_paths_agree_with_count_api(parity_client, qs):
    assert _list_total(parity_client, f"/vehicles?{qs}") == _api_total(parity_client, qs), qs


def test_usepick_facets_are_consistent_with_price(parity_client, monkeypatch):
    """usepick 페이지에서 가격대를 고르면 ① 갈래 칩 수(use_counts)는 가격대를 반영하고
    ② 구간별 건수는 갈래를 반영한다(패싯 규칙) ③ 구간 합 + NULL == 가격대 없는 같은 목록의 총수."""
    ctx = _capture_ctx(monkeypatch)
    base_total = _list_total(parity_client, "/vehicles?usepick=1")
    assert base_total > 0, "전제: 픽스처에 실사용 추천이 있어야 공허하지 않다"
    assert parity_client.get("/vehicles?usepick=1", headers=_PUBLIC).status_code == 200
    counts_no_price = {b["key"]: b["count"] for b in ctx["price_bands"]}
    assert sum(counts_no_price.values()) == base_total, "픽스처 실사용 추천은 전부 최저가가 있다"
    assert ctx["use_counts"]["all"] == base_total
    # 가격대 하나를 고르면: 목록 총수 == 그 구간의 count(가격 없는 상태와 같은 값) == 칩 '전체' 수
    for key, n in counts_no_price.items():
        if n == 0:
            continue
        ctx.clear()
        assert parity_client.get(f"/vehicles?usepick=1&price={key}", headers=_PUBLIC).status_code == 200
        assert ctx["total"] == n, key
        assert ctx["use_counts"]["all"] == n, key
        assert ctx["use_counts"]["now"] + ctx["use_counts"]["cheap"] == n, key
        assert {b["key"]: b["count"] for b in ctx["price_bands"]} == counts_no_price, key
        assert all(service.price_band_key(r["min_sale_price"]) == key for r in ctx["rows"]), key


# ── 반증: WHERE 조각이 실제로 일을 한다 ─────────────────────────────────

_ANCHORS = ('where.append("min_sale_price >= ?"); params.append(int(price_min))',
            'where.append("min_sale_price < ?"); params.append(int(price_max))')


def test_where_fragments_are_load_bearing(seeded):
    """`db._vehicles_where` 원문에서 두 조각을 지운 변이체를 메모리에서 만들어 실행한다(파일은 안 건드린다).
    변이체는 같은 인자로 13행 전부(NULL 포함)를 돌려주고, 원본은 경계 2행만 돌려준다 —
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
        where, params = fn(hide_incomplete=True, price_min=5_000_000, price_max=10_000_000)
        conn = db.connect()
        try:
            return {r["id"] for r in conn.execute(
                "SELECT id FROM vehicles WHERE " + " AND ".join(where), params)}
        finally:
            conn.close()

    real_where, _ = db._vehicles_where(price_min=5_000_000, price_max=10_000_000)
    mut_where, _ = mutant(price_min=5_000_000, price_max=10_000_000)
    assert real_where == ["min_sale_price >= ?", "min_sale_price < ?"]
    assert mut_where == []
    assert _run(db._vehicles_where) == {"B1", "B2"}
    assert _run(mutant) == ALL_IDS, "조각이 없으면 NULL·다른 구간이 전부 새어 나온다"
