"""FEAT-1 가격대 필터 — QA 적대적 반증 테스트 (지시서 2026-09-26-14 / qa-engineer).

서버 계약은 tests/test_price_band_filter.py, 화면 계약은 tests/test_feat1_price_select.py 가 지킨다.
이 파일은 그 둘이 **보지 않은 틈**만 본다(운영 DB 사본 1,418행 실측에서 통과한 항목을 tmp DB 로 고정):
  ① 0건 화면(빈 결과 분기)에서도 선택 구간 selected · 해제 칩이 남는다 — 사용자가 "왜 0건인지" 볼 수 있어야 한다.
     이 분기에는 결과 푸터('총 N건 (필터 적용)')가 아예 없다 — 실측 스위프에서 '(필터 적용) 없음' 24건이 전부 이 경우였다.
  ② 파라미터 오염 20종(raw 쿼리스트링: 빈값 · 중복 2·3회 · %00 · ;DROP · price[] · 10KB · 대소문자 · 후행 공백 · 개행 …)
     → 200 · 구간 selected 없음 · 칩 없음 · 총수 == 필터 없음 · count API 도 같다.
     ⚠ '가격대 전체' 옵션에는 selected 속성이 **없다**(첫 옵션 기본값) — "selected 가 [''] 다" 로 검사하면 전부 거짓 양성이다.
  ③ 경계 4곳(정확히 5,000,000 · 10,000,000 · 20,000,000 · 30,000,000)이 **렌더된 HTML** 에서 위 구간에만 나온다 —
     서버 테스트는 list_vehicles 의 id 집합까지만 봤다.
  ④ 패싯 항등식 sum(옵션 건수) + 최저가 NULL 행 == 가격 없는 총수 — 운영 사본에는 NULL 이 0 행이라 항등식의 NULL 항이
     공허했다. 여기서는 NULL 행을 넣어 SQL 경로·파이썬 경로(segment) 모두에서 검사한다.
  ⑤ 요청당 구간 COUNT 쿼리는 SQL 경로 정확히 1 · 파이썬 경로 0 이고, price 유무로 execute 수가 달라지지 않는다.
  ⑥ 기존 틈 2건(FEAT-1 무관, backend 보고 §5-3): count API 가 promising 을 받지 않음 · upcoming 음수 클램프 없음.
     xfail(strict) 표식 — 고치면 이 표식이 빨간불로 알리므로 그때 표식을 지운다.
검사는 전부 앵커 문자열 — 줄 번호·오프셋 창 없음.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import db, service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님) — 이웃 테스트와 같은 관례
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "sale_date": "2999-01-01", "model": "쏘나타",
        "status": "완료", "fail_count": 1, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, 최저매각가, 제조사, 모델, 신뢰도). 경계마다 양쪽 한 행 + 파이썬 경로용 '포터'(commercial) + NULL 2행.
ROWS = [
    ("P0",  4_999_999,  "현대", "쏘나타", "보통"),
    ("P5",  5_000_000,  "현대", "쏘나타", "높음"),   # ★ 정확히 500만 → '500~1,000만'. 신뢰도 높음 = promising 대상
    ("P9",  9_999_999,  "기아", "쏘나타", "보통"),
    ("P10", 10_000_000, "현대", "쏘나타", "보통"),   # ★ 정확히 1,000만 → '1,000~2,000만'
    ("P19", 19_999_999, "기아", "쏘나타", "보통"),
    ("P20", 20_000_000, "기아", "쏘나타", "보통"),   # ★ 정확히 2,000만 → '2,000~3,000만'
    ("P29", 29_999_999, "기아", "쏘나타", "보통"),
    ("P30", 30_000_000, "현대", "쏘나타", "보통"),   # ★ 정확히 3,000만 → '3,000만~'
    ("S1",  15_000_000, "현대", "포터",   "보통"),   # segment=commercial (파이썬 경로)
    ("N1",  None,       "현대", "쏘나타", "보통"),   # 최저가 미상 — 어느 구간에도 없다
    ("N2",  None,       "기아", "쏘나타", "보통"),
]
TOTAL = len(ROWS)                                                  # 11
COUNTS_ALL = {"0-500": 1, "500-1000": 2, "1000-2000": 3, "2000-3000": 2, "3000-": 1}   # 합 9 + NULL 2 = 11
BOUNDARY = [("P5", "0-500", "500-1000"), ("P10", "500-1000", "1000-2000"),
            ("P20", "1000-2000", "2000-3000"), ("P30", "2000-3000", "3000-")]

SEL = re.compile(r'<select name="price"[^>]*>(.*?)</select>', re.S)
OPT = re.compile(r'<option value="([^"]*)"\s*(selected)?\s*>([^<]*)</option>')
CHIP = re.compile(r'<a href="([^"]*)" class="[^"]*" title="가격대 필터 해제">([^<]*)</a>')
LIST_TOTAL = re.compile(r"window\.NC_LIST_TOTAL=(\d+);")


def _options(html):
    m = SEL.search(html)
    assert m, "가격대 셀렉트가 없다"
    return OPT.findall(m.group(1))


def _selected(html):
    return [v for v, sel, _ in _options(html) if sel]


def _counts(html):
    out = {}
    for v, _sel, txt in _options(html):
        if v:
            mm = re.search(r"\((\d+)\)\s*$", txt)
            assert mm, txt
            out[v] = int(mm.group(1))
    return out


def _total(html):
    m = LIST_TOTAL.search(html)
    assert m, "window.NC_LIST_TOTAL 이 없다"
    return int(m.group(1))


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "feat1_qa.db")
    db.init_db()
    for i, (vid, price, maker, model, conf) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경3{i:04d}", min_sale_price=price,
                               maker=maker, model=model, market_confidence_label=conf))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app, headers=_PUBLIC)


def _api(client, qs):
    r = client.get("/api/vehicles/count" + ("?" + qs if qs else ""))
    assert r.status_code == 200, qs
    return r.json()["total"]


# ── ① 0건 화면에서도 선택 상태가 남는다 ─────────────────────────────────────────

def test_zero_result_page_keeps_selected_band_and_chip(client):
    """기아 × '3,000만~' 는 0건. 빈 결과 분기에서 셀렉트 selected · 해제 칩(제조사 유지, price 만 제거)이 남고,
    결과 푸터가 없으므로 '(필터 적용)' 도 없다 — 이 부재는 결함이 아니라 분기 구조다(실측 24건 전부 이 경우)."""
    r = client.get("/vehicles?maker=기아&price=3000-")
    assert r.status_code == 200
    html = r.text
    assert _total(html) == 0
    assert "조건에 맞는 물건이 없습니다" in html and "필터 초기화" in html
    assert "운영 도구" not in html                        # 필터 탓을 데이터 없음으로 오도하지 않는다
    assert _selected(html) == ["3000-"]
    chips = CHIP.findall(html)
    assert len(chips) == 1 and chips[0][1].strip() == "3,000만~ ✕", chips
    assert "maker=" in chips[0][0] and "price=" not in chips[0][0]
    # 결과 푸터('1–12 / 총 N건 (필터 적용)')는 이 분기에 없다. 필터 카드 머리의 '총 0건'(앵커 '>총 <b') 은 남는다 —
    # 처음 이 검사를 '총 <b' 로 적었다가 그 머리글에 걸려 빨간불이 났다(2026-09-26 QA). 푸터 앵커는 '/ 총 <b' 다.
    assert "/ 총 <b" not in html and "(필터 적용)" not in html
    assert '>총 <b class="text-txt">0</b>건' in html          # 필터 카드 머리에는 0건이 보인다
    assert _counts(html) == {"0-500": 0, "500-1000": 1, "1000-2000": 1, "2000-3000": 2, "3000-": 0}
    assert _api(client, "maker=기아&price=3000-") == 0


# ── ② 파라미터 오염 20종 ─────────────────────────────────────────────────────────

POLLUTED = [
    "price=", "price=0-500&price=1000-2000", "price=1000-2000&price=1000-2000", "price=%00", "price=0-500;DROP",
    "price[]=0-500", "price=" + "A" * 10240, "price=0-500&price=", "price=&price=0-500", "PRICE=0-500",
    "price=0-500%20", "price=0-500%00", "price=1000-2000;price=0-500", "price=%EA%B0%80", "price=3000-%0A",
    "price=0-500&price=0-500&price=0-500", "price=abc", "price=0-500'", "price=None", "price=%2F0-500",
]


@pytest.mark.parametrize("raw", POLLUTED, ids=[p[:24] for p in POLLUTED])
def test_polluted_price_param_means_no_filter_on_page_and_api(client, raw):
    r = client.get("/vehicles?" + raw)
    assert r.status_code == 200, raw
    html = r.text
    assert _total(html) == TOTAL, raw
    assert _selected(html) == [], raw                   # ⚠ [''] 가 아니다 — '가격대 전체' 에는 selected 속성이 없다
    assert not CHIP.findall(html), raw
    assert "(필터 적용)" not in html, raw
    assert _api(client, raw) == TOTAL, raw


def test_pollution_predicate_is_not_vacuous(client):
    """대조군: 퍼센트 인코딩된 정상 key(`0%2D500` == `0-500`) 는 필터가 걸린다 — 위 술어가 항상 참인 게 아니다."""
    html = client.get("/vehicles?price=0%2D500").text
    assert _total(html) == COUNTS_ALL["0-500"] == 1
    assert _selected(html) == ["0-500"]
    assert [c[1].strip() for c in CHIP.findall(html)] == ["~500만 ✕"]
    assert "(필터 적용)" in html
    assert _api(client, "price=0%2D500") == 1
    # 같은 이름이 아닌 다른 키(price[])는 무시되고 price 는 그대로 걸린다
    assert _total(client.get("/vehicles?price=0-500&price%5B%5D=x").text) == 1


# ── ③ 경계 — 렌더된 카드가 위 구간에만 있다 ─────────────────────────────────────

@pytest.mark.parametrize("vid,lower,upper", BOUNDARY, ids=[b[0] for b in BOUNDARY])
def test_boundary_row_renders_in_upper_band_only(client, vid, lower, upper):
    href = f'href="/vehicle/{vid}"'
    lo = client.get(f"/vehicles?price={lower}").text
    up = client.get(f"/vehicles?price={upper}").text
    none = client.get("/vehicles").text
    assert href not in lo, (vid, lower)
    assert href in up, (vid, upper)
    assert href in none, vid
    assert _selected(up) == [upper] and _counts(up)[upper] == _total(up)


# ── ④ 패싯 항등식 — NULL 행이 있는 상태에서, SQL 경로·파이썬 경로 모두 ────────────

@pytest.mark.parametrize("combo,null_rows", [
    ("", 2), ("maker=기아", 1), ("maker=현대", 1), ("q=쏘나타", 2),
    ("segment=commercial", 0),        # 파이썬 경로: S1 만 (NULL 행은 쏘나타라 빠진다)
], ids=["none", "kia", "hyundai", "q", "segment"])
def test_facet_identity_with_null_rows(client, combo, null_rows):
    base = client.get("/vehicles" + ("?" + combo if combo else "")).text
    counts, total = _counts(base), _total(base)
    assert set(counts) == set(service.PRICE_BAND_KEYS)
    assert sum(counts.values()) + null_rows == total == _api(client, combo), (combo, counts, total)
    for key in service.PRICE_BAND_KEYS:              # "그 구간으로 바꾸면 나올 총수" + 옵션 벡터는 price 와 무관
        qs = (combo + "&" if combo else "") + f"price={key}"
        page = client.get("/vehicles?" + qs).text
        assert counts[key] == _total(page) == _api(client, qs) == _counts(page)[key], (combo, key)
        assert _counts(page) == counts, (combo, key)
        assert _selected(page) == [key]


def test_facet_identity_matches_db_null_bucket(seeded):
    """count_by_price_band 의 None 키가 실제 NULL 행 수(2)다 — 위 항등식의 NULL 항이 공허하지 않다."""
    c = db.count_by_price_band(service.PRICE_BANDS, hide_incomplete=True)
    assert c[None] == 2 and {k: v for k, v in c.items() if k} == COUNTS_ALL


# ── ⑤ 요청당 구간 COUNT 쿼리 수 ────────────────────────────────────────────────

class _CountingConn:
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


def _is_band_count(sql):
    return "CASE" in sql and "GROUP BY band" in sql


def test_band_count_query_once_on_sql_path_zero_on_python_path(client, monkeypatch):
    real = db.connect
    box = []
    monkeypatch.setattr(db, "connect", lambda: _CountingConn(real(), box))
    urls = ["/vehicles", "/vehicles?price=1000-2000", "/vehicles?segment=commercial",
            "/vehicles?segment=commercial&price=1000-2000", "/api/vehicles/count?price=1000-2000"]
    for u in urls:                                    # 워밍업(백테스트·다물건 캐시) — 2회째를 잰다
        assert client.get(u).status_code == 200
    n = {}
    for u in urls:
        box.clear()
        assert client.get(u).status_code == 200
        n[u] = (len(box), sum(1 for s in box if _is_band_count(s)))
    assert n["/vehicles"][1] == 1 and n["/vehicles?price=1000-2000"][1] == 1
    assert n["/vehicles?segment=commercial"][1] == 0 and n["/vehicles?segment=commercial&price=1000-2000"][1] == 0
    assert n["/api/vehicles/count?price=1000-2000"] == (1, 0)
    # price 를 거는 것 자체는 쿼리를 더하지 않는다(COUNT 는 price 유무와 무관하게 1회)
    assert n["/vehicles"][0] == n["/vehicles?price=1000-2000"][0]
    assert n["/vehicles?segment=commercial"][0] == n["/vehicles?segment=commercial&price=1000-2000"][0]


# ── ⑥ 기존 틈(FEAT-1 무관) — xfail(strict) 표식 ──────────────────────────────────

@pytest.mark.xfail(strict=True, reason="기존 틈(FEAT-1 무관): /api/vehicles/count 가 promising 을 받지 않는다 — "
                                       "고치면 이 xfail 이 빨간불이 되니 그때 표식을 지운다")
def test_known_gap_count_api_ignores_promising(client):
    assert _total(client.get("/vehicles?promising=1").text) == _api(client, "promising=1")


@pytest.mark.xfail(strict=True, reason="기존 틈(FEAT-1 무관): /vehicles 는 upcoming 음수를 0 으로 클램프하지만 "
                                       "/api/vehicles/count 는 그대로 써서 0 건이 된다")
def test_known_gap_count_api_negative_upcoming(client):
    assert _total(client.get("/vehicles?upcoming=-5").text) == _api(client, "upcoming=-5")
