"""FEAT-2 연식 하한·주행거리 상한 필터 — QA 적대적 반증 테스트 (지시서 2026-09-27-29 / qa-engineer).

서버 계약은 tests/test_feat2_year_km_filter.py, 화면 계약은 tests/test_feat2_year_km_select.py 가 지킨다.
이 파일은 그 둘이 **보지 않은 틈**만 본다(운영 DB 사본 1,418행·550셀 스위프에서 통과한 항목을 tmp DB 로 고정):
  ① 0건 화면(빈 결과 분기)에서도 두 축의 selected · 해제 칩이 남고 각 칩 ✕ 는 자기 키만 뺀다.
  ② 파라미터 오염(raw 쿼리스트링 26종 × 2키: 빈값 · 중복 · %00 · ;DROP · [] · 10KB · 대소문자 · 공백 · '2018.0' · '2018년' · 음수 · score …)
     → 200 · selected 없음 · 칩 없음 · 미상 문구 없음 · 총수 == 필터 없음 · count API 동일.
     한 축만 중복이면 **그 축만** 필터 없음이고 다른 축은 걸린다(대조군).
  ③ 경계 행(정확히 2015/2018/2020/2022 · 정확히 50,000/100,000/150,000/200,000 · year NULL·0 · km NULL·0·음수 · 20만 초과)이
     **렌더된 HTML** 의 `href="/vehicle/<id>"` 로 포함·제외된다 — 서버 테스트는 list_vehicles 의 id 집합까지만 봤다.
  ④ 패싯 예측을 **이 파일의 평문 술어**(service 함수를 쓰지 않는다)로 재계산해 SQL 경로·파이썬 경로(segment) 모두에서 대조:
     선택 옵션 count == total == API · 다른 옵션 count == 그 옵션으로 바꾼 총수 · 가격대 옵션이 두 축을 반영 · km_unknown_excluded.
  ⑤ 미상 문구는 km_max 가 있고 미상 > 0 일 때만(요약 줄 + 셀렉트 title, 같은 수) — 안 골랐거나 0건이면 없다.
  ⑥ 매각기일순 구분 줄이 두 축을 걸어도 카드 자리에 **경계 페이지 1회**(표 자리까지 합쳐 HTML 에 2회) — 경계는 평문 술어로 계산.
  ⑦ 요청당 쿼리: SQL 경로 축별 COUNT(`SUM(CASE WHEN`) 정확히 2 + 가격대 `GROUP BY band` 1, 축 유무로 execute 수 불변 · 파이썬 경로 0 · count API 1.
  ⑧ 기존 비용(FEAT-2 무관, xfail strict): `_maker_variants` 가 `_vehicles_where` 호출마다 `SELECT DISTINCT maker` 를 실행해 maker 페이지는
     목록 1 + 축 COUNT 3 = 4회 — FEAT-1 때 2회에서 FEAT-2 로 4회가 됐다(사본 실측 execute 8→12). 캐시하면 이 표식이 빨간불로 알린다.
  ⑨ 페이지네이션·'입찰예정 30일만' 링크가 두 키를 **각각 한 번** 싣는다.
검사는 전부 앵커 문자열 — 줄 번호·오프셋 창 없음.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import db, service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님) — 이웃 테스트와 같은 관례
BASE = {"court": "수원지방법원", "item_no": "1", "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, year, mileage_km, min_sale_price, maker, model, sale_date). 모델 '포터' 는 segment=commercial(파이썬 경로).
ROWS = [
    ("Y15",   2015, 30_000,  8_000_000,  "현대", "쏘나타", "2999-01-01"),   # ★ 정확히 2015
    ("Y18",   2018, 100_000, 12_000_000, "현대", "쏘나타", "2999-01-02"),   # ★ 정확히 2018 · 정확히 100,000
    ("Y20",   2020, 150_000, 22_000_000, "기아", "쏘나타", "2999-01-03"),   # ★ 정확히 2020 · 정확히 150,000
    ("Y22",   2022, 200_000, 35_000_000, "현대", "쏘나타", "2999-01-04"),   # ★ 정확히 2022 · 정확히 200,000
    ("K50",   2019, 50_000,  15_000_000, "기아", "쏘나타", "2999-01-05"),   # ★ 정확히 50,000
    ("YN",    None, 20_000,  9_000_000,  "현대", "쏘나타", "2999-01-06"),   # 연식 NULL
    ("Y0",    0,    20_000,  9_000_000,  "기아", "쏘나타", "2999-01-07"),   # 연식 0
    ("KN",    2021, None,    9_000_000,  "현대", "쏘나타", "2999-01-08"),   # 주행 NULL
    ("K0",    2021, 0,       9_000_000,  "현대", "쏘나타", "2999-01-09"),   # 주행 0(선박류 판정)
    ("KNEG",  2021, -5,      9_000_000,  "기아", "쏘나타", "2999-01-10"),   # 주행 음수(방어)
    ("KOVER", 2023, 200_001, 50_000_000, "현대", "쏘나타", "2999-01-11"),   # 20만 초과 — 어느 상한에도 없고 미상도 아니다
    ("PN",    2023, 30_000,  None,       "현대", "쏘나타", "2999-01-12"),   # 최저가 NULL(가격대 축 NULL)
    ("F1",    2019, 70_000,  9_000_000,  "현대", "쏘나타", "2999-01-13"),
    ("F2",    2019, 80_000,  9_000_000,  "현대", "쏘나타", "2999-01-14"),
    ("F3",    2019, 90_000,  9_000_000,  "현대", "쏘나타", "2999-01-15"),
    ("F4",    2019, 95_000,  9_000_000,  "현대", "쏘나타", "2999-01-16"),
    ("C1",    2018, 100_000, 15_400_000, "기아", "포터",   "2999-01-17"),   # segment=commercial
    ("C2",    2020, None,    9_000_000,  "현대", "포터",   "2999-01-18"),
    ("C3",    2014, 40_000,  9_000_000,  "현대", "포터",   "2999-01-19"),
    ("C4",    2022, 250_000, 9_000_000,  "기아", "포터",   "2999-01-20"),
    ("P1",    2019, 60_000,  9_000_000,  "현대", "쏘나타", "2020-01-05"),   # 지난 기일(구분 줄용)
    ("P2",    2016, 90_000,  9_000_000,  "현대", "쏘나타", "2020-01-03"),
    ("P3",    2021, 110_000, 9_000_000,  "기아", "쏘나타", "2020-01-01"),
]
ROW = {r[0]: dict(zip(("id", "year", "km", "price", "maker", "model", "sale_date"), r)) for r in ROWS}
TOTAL = len(ROWS)                                                  # 23
YK = {"2015": 2015, "2018": 2018, "2020": 2020, "2022": 2022}
KK = {"50000": 50_000, "100000": 100_000, "150000": 150_000, "200000": 200_000}
PBR = {"0-500": (0, 5_000_000), "500-1000": (5_000_000, 10_000_000), "1000-2000": (10_000_000, 20_000_000),
       "2000-3000": (20_000_000, 30_000_000), "3000-": (30_000_000, None)}
CASE = {vid: f"2026타경8{i:04d}" for i, (vid, *_r) in enumerate(ROWS)}     # 서로 접두가 아닌 사건번호(q=LIKE 로 1행만 잡힌다)


# ── 평문 술어(service 를 쓰지 않는다 — 구현과 독립인 기대값) ─────────────────────────

def _year_ok(r, y):
    return not y or (r["year"] is not None and r["year"] >= YK[y])


def _km_ok(r, k):
    return not k or (r["km"] is not None and 0 < r["km"] <= KK[k])


def _price_ok(r, b):
    if not b:
        return True
    lo, hi = PBR[b]
    return r["price"] is not None and r["price"] >= lo and (hi is None or r["price"] < hi)


def _base(maker="", segment=""):
    rows = list(ROW.values())
    if maker:
        rows = [r for r in rows if r["maker"] == maker]
    if segment == "commercial":
        rows = [r for r in rows if r["model"] == "포터"]
    return rows


def _expect(maker="", segment="", y="", k="", b=""):
    return {r["id"] for r in _base(maker, segment) if _year_ok(r, y) and _km_ok(r, k) and _price_ok(r, b)}


def _expect_unknown(maker="", segment="", y="", b=""):
    """km_unknown_excluded 기대값 — 주행거리 축만 뺀 모수의 NULL·0 이하 수."""
    return sum(1 for r in _base(maker, segment) if _year_ok(r, y) and _price_ok(r, b) and (r["km"] is None or r["km"] <= 0))


# ── HTML 앵커 ───────────────────────────────────────────────────────────

OPT = re.compile(r'<option value="([^"]*)"\s*(selected)?\s*>([^<]*)</option>')
CHIP = re.compile(r'<a href="([^"]*)" class="[^"]*" title="(가격대|연식|주행거리) 필터 해제">([^<]*)</a>')
NOTE = re.compile(r'<span class="text-mut whitespace-nowrap">\(주행거리 미상 (\d+)건 제외\)</span>')
TITLE_NOTE = re.compile(r'<select name="km_max"[^>]*title="[^"]*주행거리 미상 (\d+)건 제외"')
LIST_TOTAL = re.compile(r"window\.NC_LIST_TOTAL=(\d+);")


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _total(html):
    m = LIST_TOTAL.search(html)
    assert m, "window.NC_LIST_TOTAL 이 없다"
    return int(m.group(1))


def _options(html, name):
    m = re.search(r'<select name="%s"[^>]*>(.*?)</select>' % name, html, re.S)
    assert m, f"{name} 셀렉트가 없다"
    return OPT.findall(m.group(1))


def _selected(html, name):
    return [v for v, s, _ in _options(html, name) if s]


def _counts(html, name):
    out = {}
    for v, _s, txt in _options(html, name):
        if v:
            mm = re.search(r"\((\d+)\)\s*$", txt)
            assert mm, txt
            out[v] = int(mm.group(1))
    return out


def _chips(html, axis=None):
    return [c for c in CHIP.findall(html) if axis is None or c[1] == axis]


def _note(html):
    m = NOTE.search(html); t = TITLE_NOTE.search(html)
    return (int(m.group(1)) if m else None, int(t.group(1)) if t else None)


def _ids(html):
    return set(re.findall(r'href="/vehicle/([A-Za-z0-9_]+)"', html))


def _api(client, qs):
    r = client.get("/api/vehicles/count" + ("?" + qs if qs else ""))
    assert r.status_code == 200, qs
    return r.json()["total"]


def _card_section(html):
    sec = html[html.index('<div id="listResults">'):]
    return sec[sec.index("lg:hidden"):] if "lg:hidden" in sec else sec


# ── 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "feat2_qa.db")
    db.init_db()
    for vid, year, km, price, maker, model, sd in ROWS:
        db.upsert_vehicle(dict(BASE, id=vid, case_no=CASE[vid], year=year, mileage_km=km, min_sale_price=price,
                               maker=maker, model=model, sale_date=sd))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app, headers=_PUBLIC)


def test_fixture_is_not_void(client):
    """공허 통과 방지 — 전 행이 공개 목록에 보이고, 각 경계·미상 부류가 실제로 있다."""
    assert _total(_get(client, "/vehicles")) == TOTAL
    assert _total(_get(client, "/vehicles?segment=commercial")) == 4
    assert _expect_unknown() == 4 and {r["id"] for r in ROW.values() if r["year"] is None or r["year"] <= 0} == {"YN", "Y0"}
    assert _expect(y="2015", k="200000") == {"Y15", "Y18", "Y20", "Y22", "K50", "PN", "F1", "F2", "F3", "F4", "C1", "P1", "P2", "P3"}   # 14 → 2페이지
    assert _expect(y="2022", k="50000", maker="기아") == set(), "0건 조합(①)이 실제로 0건이어야 한다"


# ── ① 0건 화면 ─────────────────────────────────────────────────────────

def test_zero_result_keeps_both_axes_selected_and_chips_drop_only_own_key(client):
    html = _get(client, "/vehicles?maker=기아&year_min=2022&km_max=50000&price=500-1000")
    assert _total(html) == 0 and _api(client, "maker=기아&year_min=2022&km_max=50000&price=500-1000") == 0
    assert "조건에 맞는 물건이 없습니다" in html and "필터 초기화" in html
    assert "/ 총 <b" not in html and "(필터 적용)" not in html     # 결과 푸터는 이 분기에 없다(FEAT-1 QA 와 같은 구조)
    assert _selected(html, "year_min") == ["2022"] and _selected(html, "km_max") == ["50000"] and _selected(html, "price") == ["500-1000"]
    y, k = _chips(html, "연식"), _chips(html, "주행거리")
    assert len(y) == 1 and y[0][2].strip() == "2022년 이후 ✕" and "year_min=" not in y[0][0] and "km_max=50000" in y[0][0] and "price=500-1000" in y[0][0] and "maker=" in y[0][0]
    assert len(k) == 1 and k[0][2].strip() == "5만km 이하 ✕" and "km_max=" not in k[0][0] and "year_min=2022" in k[0][0] and "price=500-1000" in k[0][0]
    # 0건이어도 셀렉트의 다른 옵션은 '그 옵션으로 바꾸면 나올 총수' — 기아 × ≤5만 × 500~1,000만: Y0(연식 0 → 연식 축은 미상) 뿐
    assert _counts(html, "year_min") == {"2015": 0, "2018": 0, "2020": 0, "2022": 0}
    assert _counts(html, "km_max") == {kk: len(_expect(maker="기아", y="2022", k=kk, b="500-1000")) for kk in KK}
    assert _note(html) == (None, None), "미상 0건(C4 는 250,000)이면 '제외' 문구를 그리지 않는다"


# ── ② 파라미터 오염 ──────────────────────────────────────────────────────

def _variants(key, good, other):
    return [f"{key}=", f"{key}={good}&{key}={other}", f"{key}={good}&{key}={good}", f"{key}=%00", f"{key}={good};DROP",
            f"{key}[]={good}", f"{key}=" + "A" * 10240, f"{key}={good}&{key}=", f"{key}=&{key}={good}", f"{key.upper()}={good}",
            f"{key}={good}%20", f"{key}=%20{good}", f"{key}={good}%00", f"{key}={good}.0", f"{key}={good}%EB%85%84", f"{key}=-{good}",
            f"{key}={good}&{key}={good}&{key}={good}", f"{key}=abc", f"{key}={good}'", f"{key}=None", f"{key}=%2F{good}",
            f"{key}={int(good) + 1}", f"{key}=0{good}", f"{key}=%2B{good}", f"{key}=1e5", f"{key}=score", f"{key}=2018,2020"]


POLLUTED = _variants("year_min", "2018", "2020") + _variants("km_max", "100000", "50000")


@pytest.mark.parametrize("raw", POLLUTED, ids=[p[:28] for p in POLLUTED])
def test_polluted_param_means_no_filter_on_page_and_api(client, raw):
    html = _get(client, "/vehicles?" + raw)
    assert _total(html) == TOTAL
    assert _selected(html, "year_min") == [] and _selected(html, "km_max") == [] and _selected(html, "price") == []
    assert _chips(html) == [] and "(필터 적용)" not in html and "주행거리 미상" not in html
    assert _api(client, raw) == TOTAL


def test_duplicate_on_one_axis_only_drops_that_axis(client):
    """한 축만 중복이면 그 축만 필터 없음 — 다른 축은 걸린다(대조군: 오염 검사가 공허하지 않음)."""
    html = _get(client, "/vehicles?year_min=2018&year_min=2020&km_max=100000")
    assert _selected(html, "year_min") == [] and _selected(html, "km_max") == ["100000"]
    assert _total(html) == len(_expect(k="100000")) == _api(client, "year_min=2018&year_min=2020&km_max=100000")
    assert len(_chips(html)) == 1 and _chips(html)[0][1] == "주행거리"
    # 인코딩된 정확 키는 걸린다
    assert _selected(_get(client, "/vehicles?year_min=%32%30%31%38"), "year_min") == ["2018"]


# ── ③ 경계 — 렌더된 HTML ───────────────────────────────────────────────

BOUNDARY = [
    ("Y15", "year_min=2015", "year_min=2018"), ("Y18", "year_min=2018", "year_min=2020"), ("Y20", "year_min=2020", "year_min=2022"),
    ("Y22", "year_min=2022", "km_max=150000"),
    ("K50", "km_max=50000", "year_min=2020"), ("Y18", "km_max=100000", "km_max=50000"), ("Y20", "km_max=150000", "km_max=100000"),
    ("Y22", "km_max=200000", "km_max=150000"),
    ("YN", "km_max=200000", "year_min=2015"), ("Y0", "km_max=200000", "year_min=2015"),
    ("KN", "year_min=2015", "km_max=200000"), ("K0", "year_min=2015", "km_max=200000"), ("KNEG", "year_min=2015", "km_max=200000"),
    ("KOVER", "year_min=2022", "km_max=200000"),
]


@pytest.mark.parametrize("vid,inc,exc", BOUNDARY, ids=[f"{v}:{i}:{e}" for v, i, e in BOUNDARY])
def test_boundary_row_rendered_in_including_option_and_absent_in_excluding(client, vid, inc, exc):
    q = f"all=1&q={CASE[vid]}"
    assert vid in _ids(_get(client, f"/vehicles?{q}")), "검색만으로는 보인다(전제)"
    assert vid in _ids(_get(client, f"/vehicles?{q}&{inc}")), f"{vid} 는 {inc} 에 포함돼야 한다"
    assert vid not in _ids(_get(client, f"/vehicles?{q}&{exc}")), f"{vid} 는 {exc} 에서 빠져야 한다"


# ── ④ 패싯 예측 — 평문 술어로 재계산, SQL 경로·파이썬 경로 ────────────────────────

CELLS = [("", ""), ("2015", ""), ("", "100000"), ("2018", "100000"), ("2020", "200000"), ("2022", "50000")]


@pytest.mark.parametrize("path", ["", "segment=commercial", "maker=현대", "maker=기아&price=500-1000"], ids=["sql", "python", "maker", "maker+price"])
@pytest.mark.parametrize("y,k", CELLS, ids=[f"y{y or '-'}k{k or '-'}" for y, k in CELLS])
def test_facet_counts_match_plain_predicates_and_switch_totals(client, path, y, k):
    seg = "commercial" if "segment" in path else ""
    maker = "현대" if "현대" in path else ("기아" if "기아" in path else "")
    b = "500-1000" if "price=" in path else ""
    qs = "&".join(x for x in [path, f"year_min={y}" if y else "", f"km_max={k}" if k else ""] if x)
    html = _get(client, "/vehicles?" + qs)
    exp_ids = _expect(maker, seg, y, k, b)
    assert _total(html) == len(exp_ids) == _api(client, qs)
    if len(exp_ids) <= 12:
        assert _ids(html) == exp_ids, "첫 페이지 카드 = 기대 id 집합"
    if y:
        assert _counts(html, "year_min")[y] == len(exp_ids)
    if k:
        assert _counts(html, "km_max")[k] == len(exp_ids)
    if b:
        assert _counts(html, "price")[b] == len(exp_ids)
    # 다른 옵션 = 그 옵션으로 바꾸면 나올 총수(누적) — 자기 축만 빼고 나머지(가격대·다른 축) 적용
    assert _counts(html, "year_min") == {yy: len(_expect(maker, seg, yy, k, b)) for yy in YK}
    assert _counts(html, "km_max") == {kk: len(_expect(maker, seg, y, kk, b)) for kk in KK}
    assert _counts(html, "price") == {bb: len(_expect(maker, seg, y, k, bb)) for bb in PBR}, "가격대 옵션이 두 축을 반영"
    # 미상 문구 — km_max 가 있고 미상 > 0 일 때만, 요약 줄 == title == 평문 기대값
    exp_unk = _expect_unknown(maker, seg, y, b)
    got = _note(html)
    if k and exp_unk:
        assert got == (exp_unk, exp_unk), f"unknown {got} != {exp_unk}"
    else:
        assert got == (None, None) and "주행거리 미상" not in html


def test_axis_option_vector_is_independent_of_own_axis_value(client):
    for path in ("", "segment=commercial"):
        sep = "&" if path else ""
        ref_y = _counts(_get(client, f"/vehicles?{path}"), "year_min")
        ref_k = _counts(_get(client, f"/vehicles?{path}"), "km_max")
        for y in YK:
            assert _counts(_get(client, f"/vehicles?{path}{sep}year_min={y}"), "year_min") == ref_y
        for k in KK:
            assert _counts(_get(client, f"/vehicles?{path}{sep}km_max={k}"), "km_max") == ref_k
            assert _note(_get(client, f"/vehicles?{path}{sep}km_max={k}"))[0] == _expect_unknown(segment="commercial" if path else "")


# ── ⑤ 미상 문구의 조건 ──────────────────────────────────────────────────

def test_unknown_note_requires_km_max_and_nonzero(client):
    assert _note(_get(client, "/vehicles?year_min=2015")) == (None, None)                       # 안 골랐으면 없음(값은 서버가 준다)
    assert _note(_get(client, "/vehicles?km_max=200000")) == (4, 4)                              # KN·K0·KNEG·C2
    assert _note(_get(client, "/vehicles?km_max=200000&maker=기아")) == (1, 1)                   # KNEG
    assert _note(_get(client, "/vehicles?km_max=200000&maker=기아&year_min=2022")) == (None, None)   # 기아 × 2022+ = C4 뿐 → 미상 0 → 문구 없음
    html = _get(client, "/vehicles?km_max=100000&segment=commercial")
    assert _note(html) == (1, 1) and _total(html) == 2                                          # C2 만 미상, C1(100,000)·C3(40,000) 통과
    assert "(주행거리 미상 1건 제외)" in html and html.count("주행거리 미상") == 2, "요약 줄 1 + 셀렉트 title 1 — 다른 곳에 새지 않는다"


# ── ⑥ 매각기일순 구분 줄 ──────────────────────────────────────────────────

@pytest.mark.parametrize("qs", ["year_min=2015&km_max=200000", "year_min=2020", "km_max=100000&maker=현대", "segment=commercial&year_min=2015&km_max=200000"])
def test_split_line_once_on_boundary_page_with_axes(client, qs):
    d = dict(x.split("=") for x in qs.split("&"))
    rows = _expect(d.get("maker", ""), d.get("segment", ""), d.get("year_min", ""), d.get("km_max", ""))
    up = sum(1 for v in rows if ROW[v]["sale_date"] >= "2999"); past = len(rows) - up
    pages = max(1, -(-len(rows) // 12))
    found = []
    for p in range(1, pages + 1):
        html = _get(client, f"/vehicles?sort=sale_date&{qs}&page={p}")
        sec = _card_section(html)
        if "data-sale-split" in sec:
            found.append((p, sec.count("data-sale-split"), sec[:sec.index("data-sale-split")].count('<a href="/vehicle/')))
        assert html.count("data-sale-split") in (0, 2), "표(lg+)·카드 두 자리가 같은 줄을 그린다"
    if past == 0:
        assert found == []
    else:
        assert found == [(up // 12 + 1, 1, up % 12)], f"{qs}: {found} (upcoming {up}, past {past})"
        assert f'지난 기일 <b class="text-txt tnum">{past}</b>건' in _get(client, f"/vehicles?sort=sale_date&{qs}&page={up // 12 + 1}")


# ── ⑦ 요청당 쿼리 ──────────────────────────────────────────────────────

class _Spy:
    def __init__(self):
        self.sql = []
        self._orig = db.connect

    def __enter__(self):
        spy = self

        class P:
            def __init__(self, c): self._c = c
            def execute(self, s, *a, **k): spy.sql.append(s); return self._c.execute(s, *a, **k)
            def __getattr__(self, n): return getattr(self._c, n)
        db.connect = lambda *a, **k: P(spy._orig(*a, **k))
        return self

    def __exit__(self, *a):
        db.connect = self._orig


def _count(client, url):
    client.get(url)                                   # 워밍업(backtest 캐시 등)
    with _Spy() as s:
        assert client.get(url).status_code == 200
        return (len(s.sql), sum(1 for q in s.sql if "SUM(CASE WHEN" in q), sum(1 for q in s.sql if "GROUP BY band" in q),
                sum(1 for q in s.sql if "SELECT DISTINCT maker" in q))


def test_query_budget_sql_path_two_cumulative_counts_python_path_none(client):
    n0, cum0, band0, _ = _count(client, "/vehicles")
    n1, cum1, band1, _ = _count(client, "/vehicles?year_min=2018&km_max=100000&price=1000-2000")
    assert (cum0, band0) == (2, 1) and (cum1, band1) == (2, 1), "축별 COUNT 는 연식·주행 각 1(SUM(CASE)) + 가격대 1(GROUP BY band)"
    assert n0 == n1, "축을 골라도 execute 수는 그대로(WHERE 조각만 늘어난다)"
    for url in ("/vehicles?segment=commercial&year_min=2018&km_max=100000", "/vehicles?picks=1&km_max=100000"):
        _n, cum, band, _ = _count(client, url)
        assert (cum, band) == (0, 0), url
    for url in ("/api/vehicles/count", "/api/vehicles/count?year_min=2018&km_max=100000", "/api/vehicles/count?segment=commercial&km_max=50000"):
        assert _count(client, url)[0] == 1, url


@pytest.mark.xfail(strict=True, reason="기존 비용(FEAT-2 무관): _maker_variants 가 _vehicles_where 호출마다 SELECT DISTINCT maker 를 실행 — "
                                       "maker 페이지는 목록 1 + 축 COUNT 3 = 4회(FEAT-1 때 2회). 캐시/1회 조회로 고치면 이 표식을 지운다")
def test_known_cost_maker_variants_lookup_at_most_twice_per_request(client):
    _n, _c, _b, distinct = _count(client, "/vehicles?maker=현대&year_min=2018")
    assert distinct <= 2, f"SELECT DISTINCT maker {distinct}회"


def test_maker_variants_lookup_count_is_exactly_list_plus_three_facets(client):
    """⑧ 의 현재 값을 고정 — 4회. 축 COUNT 가 하나 늘거나 줄면 여기서 드러난다."""
    assert _count(client, "/vehicles?maker=현대&year_min=2018")[3] == 4
    assert _count(client, "/vehicles?maker=현대&segment=commercial")[3] == 1, "파이썬 경로는 목록 1회뿐"


# ── ⑨ 링크가 두 키를 각각 한 번 싣는다 ──────────────────────────────────────

def test_pagination_and_upcoming_links_carry_both_keys_once(client):
    html = _get(client, "/vehicles?year_min=2015&km_max=200000")
    assert _total(html) == 14
    m = re.search(r'<a href="(/vehicles\?[^"]*page=2)"', html)
    assert m, "2페이지 링크가 없다"
    assert m.group(1).count("year_min=2015") == 1 and m.group(1).count("km_max=200000") == 1
    m2 = re.search(r'<a href="(/vehicles\?[^"]*upcoming=30)"', html)
    assert m2 and m2.group(1).count("year_min=2015") == 1 and m2.group(1).count("km_max=200000") == 1
    assert re.findall(r'<input type="hidden" name="(year_min|km_max|price)"', html) == [], "셀렉트가 있는 키는 hidden 으로 또 싣지 않는다"
    assert html.count('name="year_min"') == 1 and html.count('name="km_max"') == 1
