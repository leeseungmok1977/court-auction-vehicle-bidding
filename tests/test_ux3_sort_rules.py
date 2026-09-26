"""UX-3 정렬 규칙(오너 승인 2026-09-26, 지시서 2026-09-26-21) + UX-1 화면이 쓸 컨텍스트.

검색 UX 점검(reports/2026-09-26-search-ux-synthesis.md)에서 정렬 두 종이 **이름과 반대로** 동작했다:
  · `매각기일순`(sort=sale_date)  — 방향 없는 ASC 라 끝난 경매부터(1·2페이지 24건 전부 '매각 종료')
  · `짧은 주행거리순`(sort=mileage) — NULL 만 뒤로 보내 mileage_km=0 인 선박('동력선 진솔호')이 첫 카드

새 규칙(서버 계약):
  ① sale_date: [오늘 이후(오늘 포함) 가까운 순] → [지난 기일, 최근 종료 먼저] → [sale_date NULL]. 모수(WHERE) 무변경.
     "오늘"은 SQL date('now','localtime') — upcoming_days 조각과 같은 식 — 이고 파이썬 쪽은 date.today().
  ② mileage: NULL 과 0 이하를 함께 뒤로, 양수는 오름차순.
  ③ vehicles() 컨텍스트 sale_split = {upcoming, past, undated, page_first_past_idx} — sale_date 정렬(SQL 경로)일 때만.
     page_first_past_idx: 전체 정렬 결과에서 첫 '지난 기일' 행의 전역 인덱스가 **현재 페이지 범위 안에 있을 때만**
     그 페이지 내 0-based 인덱스, 그 밖(경계가 앞 페이지·지난 기일 없음)이면 None → 구분 줄은 경계 페이지에 한 번.
  ④ 다른 정렬·usepick·picks 경로·sort=expected 에서는 sale_split None 이고 200. segment·bucket(순서 보존)은 dict(지시서 -23).
  ⑤ qs_no_date / qs_no_result / qs_no_court / qs_no_q — 그 키만 뺀 쿼리스트링(UX-1 칩 ✕ 링크).
  ⑥ 회귀: /api/vehicles/count 는 목록 총수와 같고(정렬은 모수를 바꾸지 않는다), 기존 정렬 전부 200.
  반증: 정렬식을 예전 것으로 되돌린 **메모리 변이체**(db.SALE_DATE_SORT / db.MILEAGE_SORT monkeypatch)에서 ①·② 검사가
     빨간불인지 — 검사가 공허하지 않음을 증명한다.
검사는 전부 컨텍스트 dict·앵커 문자열로 한다 — 줄 번호·오프셋 창 금지.
"""
from datetime import date, timedelta
from urllib.parse import parse_qs

import pytest
from starlette.testclient import TestClient

from web import db

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
TODAY = date.today()


def _d(offset: int) -> str:
    """오늘 기준 offset 일(양수=미래, 음수=과거)의 ISO 날짜."""
    return (TODAY + timedelta(days=offset)).isoformat()


# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·낙찰 아님) — FEAT-1 테스트와 같은 관례.
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "model": "쏘나타", "maker": "현대",
        "status": "완료", "fail_count": 1, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "min_sale_price": 12_000_000, "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(tmp_path, monkeypatch, rows):
    """rows: (id, sale_date | None, mileage_km | None) 순서열. 삽입 순서는 기대 순서와 **다르게** 섞어 넣는다
    (rowid 순서가 우연히 기대 순서와 같으면 정렬을 검사하지 않은 채 통과한다)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ux3.db")
    db.init_db()
    for i, (vid, sd, km) in enumerate(rows):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경3{i:04d}", sale_date=sd, mileage_km=km))


def _client() -> TestClient:
    import web.app as A
    return TestClient(A.app)


def _ctx(client, url: str) -> dict:
    r = client.get(url, headers=_PUBLIC)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.context


def _ids(rows) -> list:
    return [r["id"] for r in rows]


# ── 정렬 규칙 검사기(①·②) — 실제 결과와 변이체 결과에 같은 검사기를 쓴다 ─────────────────────────

# 미래 3(+1·+10·+30) · 오늘 1(경계) · 과거 3(−1·−10·−30) · NULL 2. 삽입 순서는 의도적으로 뒤섞음.
SALE_ROWS = [("P30", _d(-30), 1), ("N1", None, 1), ("F30", _d(30), 1), ("P1", _d(-1), 1),
             ("T0", _d(0), 1), ("F1", _d(1), 1), ("N2", None, 1), ("P10", _d(-10), 1), ("F10", _d(10), 1)]
SALE_EXPECT_HEAD = ["T0", "F1", "F10", "F30", "P1", "P10", "P30"]   # 그 뒤 {N1, N2}(NULL 끼리 순서는 규정 없음)


def _check_sale_date_order(ids: list) -> None:
    assert ids[:7] == SALE_EXPECT_HEAD, f"[오늘·미래 가까운 순][과거 최근 먼저] 이어야 한다: {ids}"
    assert set(ids[7:]) == {"N1", "N2"}, f"sale_date NULL 은 맨 뒤: {ids}"


# 양수 3(1,000·50,000·250,000) · 0 · NULL. 0 이 삽입 첫 줄(예전 규칙이면 첫 카드가 되는 자리).
MILE_ROWS = [("Z0", _d(5), 0), ("M250", _d(5), 250_000), ("MN", _d(5), None), ("M1", _d(5), 1_000), ("M50", _d(5), 50_000)]


def _check_mileage_order(ids: list) -> None:
    assert ids[:3] == ["M1", "M50", "M250"], f"양수는 오름차순이어야 한다: {ids}"
    assert set(ids[3:]) == {"Z0", "MN"}, f"0 과 NULL 은 함께 맨 뒤: {ids}"


# ── ① 매각기일순 ─────────────────────────────────────────────────────────────────

def test_sale_date_sort_upcoming_asc_then_past_desc_then_null(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    _check_sale_date_order(_ids(db.list_vehicles(sort="sale_date", hide_incomplete=True)))     # DB 층
    ctx = _ctx(_client(), "/vehicles?sort=sale_date")                                            # 라우트 층(1페이지=전부)
    _check_sale_date_order(_ids(ctx["rows"]))


def test_today_is_in_upcoming_block_boundary(tmp_path, monkeypatch):
    """경계: 오늘 기일은 '오늘 이후' 블록이고 그 블록의 첫 행이다(입찰 시각 전이면 아직 입찰할 수 있다)."""
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ids = _ids(db.list_vehicles(sort="sale_date", hide_incomplete=True))
    assert ids[0] == "T0"
    ctx = _ctx(_client(), "/vehicles?sort=sale_date")
    assert ctx["sale_split"]["upcoming"] == 4, "오늘 1 + 미래 3"


def test_sql_today_and_python_today_agree():
    """SQL 분류(date('now','localtime'))와 파이썬 분류(date.today())가 같은 날을 가리켜야 sale_split 이 정렬과 맞는다."""
    conn = db.connect()
    try:
        sql_today = conn.execute("SELECT date('now','localtime')").fetchone()[0]
    finally:
        conn.close()
    assert sql_today == date.today().isoformat()


def test_sale_date_sort_uses_same_today_expression_as_upcoming_days():
    """PANEL-16: 날짜 계산 자리를 늘리되 식은 통일 — upcoming_days 조각과 같은 `date('now','localtime')`."""
    assert "date('now','localtime')" in db.SALE_DATE_SORT
    assert "date('now')" not in db.SALE_DATE_SORT.replace("date('now','localtime')", "")


def test_internal_default_sort_is_unchanged_plain_asc(tmp_path, monkeypatch):
    """내부 호출(sort 미지정)은 예전 그대로 방향 없는 ASC — 수집기 순회 순서를 UI 규칙 변경과 분리한다."""
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    got = _ids(db.list_vehicles(hide_incomplete=True))
    conn = db.connect()
    try:
        raw = [r[0] for r in conn.execute("SELECT id FROM vehicles ORDER BY sale_date").fetchall()]
    finally:
        conn.close()
    assert got == raw


# ── ② 짧은 주행거리순 ───────────────────────────────────────────────────────────

def test_mileage_sort_zero_and_null_last_positive_ascending(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, MILE_ROWS)
    _check_mileage_order(_ids(db.list_vehicles(sort="mileage", hide_incomplete=True)))
    ctx = _ctx(_client(), "/vehicles?sort=mileage")
    _check_mileage_order(_ids(ctx["rows"]))
    assert ctx["sale_split"] is None


# ── 반증(메모리 변이): 예전 정렬식으로 되돌리면 ①·② 검사가 빨간불이어야 한다 ─────────────────

def test_mutant_old_sale_date_asc_fails_check(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    monkeypatch.setattr(db, "SALE_DATE_SORT", "sale_date")          # 예전 식: 방향 없는 ASC
    ids = _ids(db.list_vehicles(sort="sale_date", hide_incomplete=True))
    assert ids[0] != "T0", "변이가 적용되지 않았다(list_vehicles 가 상수를 안 쓴다?)"
    with pytest.raises(AssertionError):
        _check_sale_date_order(ids)


def test_mutant_old_mileage_null_only_fails_check(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, MILE_ROWS)
    monkeypatch.setattr(db, "MILEAGE_SORT", "mileage_km IS NULL, mileage_km")   # 예전 식: NULL 만 뒤로
    ids = _ids(db.list_vehicles(sort="mileage", hide_incomplete=True))
    assert ids[0] == "Z0", "변이가 적용되지 않았다 — 예전 식이면 0 이 첫 카드다(동력선 진솔호 재현)"
    with pytest.raises(AssertionError):
        _check_mileage_order(ids)


# ── ③ sale_split 계약 ──────────────────────────────────────────────────────────

def _rows_up_past_null(n_up: int, n_past: int, n_null: int):
    rows = [(f"U{i:02d}", _d(i + 1), 1) for i in range(n_up)]
    rows += [(f"P{i:02d}", _d(-(i + 1)), 1) for i in range(n_past)]
    rows += [(f"N{i:02d}", None, 1) for i in range(n_null)]
    rows.reverse()                                       # 삽입 순서 ≠ 기대 순서
    return rows


def test_sale_split_counts_and_boundary_on_second_page(tmp_path, monkeypatch):
    """미래 15 · 과거 5 · NULL 2(페이지 12): 1페이지는 미래만 → None, 2페이지에서 경계(전역 15 → 페이지 내 3)."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(15, 5, 2))
    c = _client()
    p1 = _ctx(c, "/vehicles?sort=sale_date")["sale_split"]
    assert p1 == {"upcoming": 15, "past": 5, "undated": 2, "page_first_past_idx": None}
    p2 = _ctx(c, "/vehicles?sort=sale_date&page=2")
    assert p2["sale_split"] == {"upcoming": 15, "past": 5, "undated": 2, "page_first_past_idx": 3}
    assert _ids(p2["rows"])[3] == "P00" and _ids(p2["rows"])[2] == "U14", "경계 앞은 가장 먼 미래, 경계는 가장 최근 과거"
    assert set(_ids(p2["rows"])[8:]) == {"N00", "N01"}, "NULL 은 맨 뒤"


def test_sale_split_boundary_exactly_at_second_page_first_row(tmp_path, monkeypatch):
    """미래 12 · 과거 3: 경계가 정확히 2페이지 첫 행 → 1페이지 None, 2페이지 0."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(12, 3, 0))
    c = _client()
    assert _ctx(c, "/vehicles?sort=sale_date")["sale_split"]["page_first_past_idx"] is None
    assert _ctx(c, "/vehicles?sort=sale_date&page=2")["sale_split"]["page_first_past_idx"] == 0


def test_sale_split_boundary_only_once_when_first_page_already_past(tmp_path, monkeypatch):
    """미래 10 · 과거 5: 경계는 1페이지(인덱스 10)에서 한 번. 2페이지는 이미 과거로 이어지므로 None(구분 줄 재출력 금지)."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(10, 5, 0))
    c = _client()
    assert _ctx(c, "/vehicles?sort=sale_date")["sale_split"]["page_first_past_idx"] == 10
    assert _ctx(c, "/vehicles?sort=sale_date&page=2")["sale_split"] == \
        {"upcoming": 10, "past": 5, "undated": 0, "page_first_past_idx": None}


def test_sale_split_no_past_rows(tmp_path, monkeypatch):
    """지난 기일이 없으면 past=0·인덱스 None(NULL 만 뒤에 있어도 '지난 기일' 구분 줄은 그리지 않는다)."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(3, 0, 2))
    assert _ctx(_client(), "/vehicles?sort=sale_date")["sale_split"] == \
        {"upcoming": 3, "past": 0, "undated": 2, "page_first_past_idx": None}


def test_sale_split_all_past_boundary_is_first_row(tmp_path, monkeypatch):
    """전부 지난 기일이면 경계는 1페이지 0 — 화면이 첫 카드 위에 구분 줄을 그릴 수 있어야 한다."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(0, 4, 0))
    assert _ctx(_client(), "/vehicles?sort=sale_date")["sale_split"] == \
        {"upcoming": 0, "past": 4, "undated": 0, "page_first_past_idx": 0}


def test_sale_split_empty_result(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [])
    assert _ctx(_client(), "/vehicles?sort=sale_date")["sale_split"] == \
        {"upcoming": 0, "past": 0, "undated": 0, "page_first_past_idx": None}


def test_sale_split_respects_filters_population(tmp_path, monkeypatch):
    """sale_split 은 **필터 적용 후 모수**를 센다(총 N건과 같은 모수) — upcoming 필터면 past·undated 가 0."""
    _seed(tmp_path, monkeypatch, _rows_up_past_null(4, 3, 1))
    ctx = _ctx(_client(), "/vehicles?sort=sale_date&upcoming=30")
    assert ctx["total"] == 4
    assert ctx["sale_split"] == {"upcoming": 4, "past": 0, "undated": 0, "page_first_past_idx": None}


# ── ④ 다른 정렬·파이썬 경로·expected → sale_split None, 200 ─────────────────────────

@pytest.mark.parametrize("sort", ["", "recent", "min_sale_price", "upper_bid", "median_price", "fail_count",
                                  "mileage", "inspection", "expected", "nonexistent"])
def test_other_sorts_have_no_sale_split_and_render(tmp_path, monkeypatch, sort):
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ctx = _ctx(_client(), f"/vehicles?sort={sort}")
    assert ctx["sale_split"] is None


@pytest.mark.parametrize("extra", ["usepick=1", "usepick=now", "usepick=cheap", "picks=1"])
def test_python_paths_with_sale_date_sort_render_and_have_no_sale_split(tmp_path, monkeypatch, extra):
    """usepick·picks 는 순서를 다시 매기므로 sale_split None(정렬 순서를 보증할 수 없는 곳에 구분 줄을 그리지 않는다)."""
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ctx = _ctx(_client(), f"/vehicles?sort=sale_date&{extra}")
    assert ctx["sale_split"] is None


@pytest.mark.parametrize("extra", ["segment=sedan", "segment=suv", "bucket=wait", "bucket=review"])
def test_order_preserving_python_paths_keep_sale_split(tmp_path, monkeypatch, extra):
    """segment·bucket 은 SQL 순서를 **보존**하므로 구분 줄을 그린다(지시서 2026-09-26-23 D-8 — 1차의 '일괄 None' 을 좁힘).
    픽스처(BASE.model='쏘나타' = sedan) 로 segment=sedan 은 SALE_ROWS 전부, suv·bucket 은 0행 이상 — 어느 쪽이든 dict 이고
    upcoming+past+undated == 총수, 경계 인덱스는 1페이지 안(모수가 12 이하)이라 past 가 있으면 upcoming 과 같다."""
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ctx = _ctx(_client(), f"/vehicles?sort=sale_date&{extra}")
    sp = ctx["sale_split"]
    assert isinstance(sp, dict) and set(sp) == {"upcoming", "past", "undated", "page_first_past_idx"}
    assert sp["upcoming"] + sp["past"] + sp["undated"] == ctx["total"]
    if sp["past"]:
        assert sp["page_first_past_idx"] == sp["upcoming"], "1페이지 안 경계 = 미래 블록 길이"
    else:
        assert sp["page_first_past_idx"] is None
    if extra == "segment=sedan":
        assert sp == {"upcoming": 4, "past": 3, "undated": 2, "page_first_past_idx": 4}, "픽스처 전부 세단 — 오늘1+미래3 / 과거3 / NULL2"


# ── ⑤ qs_no_* — 그 키만 뺀다 ─────────────────────────────────────────────────────

FULL_QS = ("judgment=%EC%9C%A0%EC%B0%B0+%EB%8C%80%EA%B8%B0&maker=%ED%98%84%EB%8C%80&q=%EC%8F%98%EB%82%98%ED%83%80"
           "&sort=sale_date&result=%EB%82%99%EC%B0%B0&date=2026-10-01&court=%EC%88%98%EC%9B%90%EC%A7%80%EB%B0%A9%EB%B2%95%EC%9B%90"
           "&upcoming=30&cond=damaged&price=1000-2000")


@pytest.mark.parametrize("key,ctx_key", [("date", "qs_no_date"), ("result", "qs_no_result"),
                                         ("court", "qs_no_court"), ("q", "qs_no_q")])
def test_qs_no_key_drops_only_that_key(tmp_path, monkeypatch, key, ctx_key):
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ctx = _ctx(_client(), "/vehicles?" + FULL_QS)
    full = parse_qs(ctx["qs"])
    assert set(full) == {"judgment", "maker", "q", "sort", "result", "date", "court", "upcoming", "cond", "price"}, \
        "전제: 진입 파라미터가 전부 qs 에 실려 있어야 '그 키만 뺀다'를 검사할 수 있다"
    part = parse_qs(ctx[ctx_key])
    assert key not in part
    assert part == {k: v for k, v in full.items() if k != key}, f"{ctx_key} 는 {key} 만 빼고 나머지를 그대로 둬야 한다"


def test_qs_no_key_when_key_absent_equals_qs(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, SALE_ROWS)
    ctx = _ctx(_client(), "/vehicles?maker=%ED%98%84%EB%8C%80&sort=sale_date")
    for k in ("qs_no_date", "qs_no_result", "qs_no_court", "qs_no_q"):
        assert ctx[k] == ctx["qs"]


# ── ⑥ 회귀 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("qs", ["", "sort=sale_date", "sort=mileage", "sort=sale_date&upcoming=30",
                                "sort=sale_date&result=%EB%82%99%EC%B0%B0", "sort=mileage&maker=%ED%98%84%EB%8C%80"])
def test_count_api_matches_list_total_regardless_of_sort(tmp_path, monkeypatch, qs):
    """정렬은 모수를 바꾸지 않는다 — /api/vehicles/count 의 total == 목록 총수(sort 는 count 가 무시하는 키)."""
    _seed(tmp_path, monkeypatch, SALE_ROWS + [("M0", _d(3), 0)])
    c = _client()
    total = _ctx(c, "/vehicles" + (f"?{qs}" if qs else ""))["total"]
    r = c.get("/api/vehicles/count" + (f"?{qs}" if qs else ""), headers=_PUBLIC)
    assert r.status_code == 200
    assert r.json()["total"] == total


def test_count_api_unchanged_population_with_zero_mileage_and_null_dates(tmp_path, monkeypatch):
    """mileage 0·sale_date NULL 행도 모수에 그대로 남는다(정렬만 뒤로 보낸다) — 9 + 1 = 10."""
    _seed(tmp_path, monkeypatch, SALE_ROWS + [("M0", _d(3), 0)])
    r = _client().get("/api/vehicles/count", headers=_PUBLIC)
    assert r.json()["total"] == 10
    ids = _ids(db.list_vehicles(sort="mileage", hide_incomplete=True))
    assert len(ids) == 10 and ids[-1] == "M0", "mileage 0 행은 모수에 남되 맨 뒤(SALE_ROWS 는 전부 1 km)"


@pytest.mark.parametrize("sort", ["recent", "sale_date", "expected", "upper_bid", "min_sale_price",
                                  "mileage", "fail_count", "inspection"])
def test_all_select_sorts_render_200(tmp_path, monkeypatch, sort):
    _seed(tmp_path, monkeypatch, SALE_ROWS + MILE_ROWS)
    r = _client().get(f"/vehicles?sort={sort}", headers=_PUBLIC)
    assert r.status_code == 200
