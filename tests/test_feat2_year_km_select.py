"""FEAT-2 연식 하한·주행거리 상한 필터 — 화면(vehicles.html) 계약 (지시서 2026-09-27-28, frontend-engineer).

서버 계약(경계·NULL·누적 COUNT·패리티)은 tests/test_feat2_year_km_filter.py 가 지킨다. 이 파일은 **렌더된 HTML** 만 본다
(tests/test_feat1_price_select.py 를 본떴다):
  ① `<select name="year_min">`·`<select name="km_max">` 가 검색 폼 안, 가격대 다음·정렬 앞. 옵션 5개(전체 + 4) · `라벨 (건수)` · aria-label.
     optgroup 없음 — 라벨 자체가 축(년 이후·km 이하)을 말한다. ⚠ 건수는 **누적**(앞 옵션 ⊇ 뒤 옵션)이라 합이 총수가 아니다.
  ② `?year_min=<key>`·`?km_max=<key>` 면 그 옵션만 selected · 해제 칩(`라벨 ✕`, 축 접두 없음, 가격대 칩과 같은 primary 소프트 톤·nowrap·shrink-0,
     href 는 **그 축만** 뺀 qs) · `(필터 적용)` · 필터 초기화 칩(has_filter)
  ③ 없음·오염값·중복이면 칩 없음 · 어느 옵션도 selected 아님
  ④ `name="year_min"`·`name="km_max"` 는 HTML 에 **정확히 1번** — hidden 으로 또 넣으면 서버가 중복으로 보고 필터를 푼다
  ⑤ `ncSaveSearch` 의 key→라벨 사전(YM·KM)은 서버(year_options·km_options)에서 주입되고 템플릿 소스에는 라벨·key 리터럴이 없다(단일 원천).
     라벨이 축을 말하므로 저장 라벨에 접두를 붙이지 않는다(가격대 '최저가 ' 와 다른 점).
  ⑥ 페이지네이션 · '입찰예정 30일만' 링크가 두 키를 유지한다
  ⑦ 좁은 폭 그리드: 셀렉트 6개, 연식·주행거리는 전폭(col-span-2) — 2026-09-27 실측: 반 칸(320px 글자 영역 80px·360px 100px)에
     선택 라벨(108~110px)이 안 들어가 320 에서 '(74' 로 잘렸다(screenshots/feat2/mid-320-year2018.png). [적용]은 정렬 옆.
  ⑧ 주행거리 미상 제외 표기: km_max 가 있고 미상>0 이면 요약 줄의 **주행거리 부품 바로 뒤** `(주행거리 미상 N건 제외)` 가 mut 톤·부품 밖,
     주행거리 셀렉트 title 에도 같은 문장. 뒤에 정렬·페이지 부품이 와도 자리는 주행거리 뒤다(디자인 검수 2026-09-27 조건 1 — 맨 뒤에 두면
     `매각기일순 (주행거리 미상 N건 제외)` 처럼 정렬이 손실 원인으로 읽힌다).
     km_max 없으면(값은 컨텍스트에 있어도) 그리지 않는다 — 빠진 게 없는데 '제외' 라고 쓰면 거짓(서버 계약 §2.3). 미상 0건이어도 같은 이유로 안 그린다.
  ⑨ 0건 옵션도 `(0)` 으로 표기 · 빈 결과 화면은 초기화 안내(운영 도구 문구 없음)
  ⑩ 요약 줄 부품(UX-5)에 두 라벨이 들어가고 큰글씨 접힌 머리 `외 N` 은 부품 수만 센다(미상 문구는 부품이 아니다)
검사는 전부 **앵커 문자열**로 한다 — 줄 번호·매직 오프셋 창을 쓰지 않는다.
"""
import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import db, service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = _ROOT / "web" / "templates" / "vehicles.html"
APP_CSS = _ROOT / "web" / "static" / "app.css"

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님) — median_price 가 있으면 주행거리 NULL 이어도 보인다
BASE = {"court": "수원지방법원", "item_no": "1", "sale_date": "2999-01-01", "model": "쏘나타", "status": "완료", "fail_count": 1,
        "min_sale_price": 15_000_000, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, 연식, 주행거리, 제조사). 2018·100,000 을 **13행**(페이지 크기 12 초과)으로 채워 페이지네이션이 실제로 그려진다(공허 통과 방지).
# 경계: 정확히 2018 은 '2018 이후'에 포함, 정확히 100,000 은 '10만 이하'에 포함, 200,001 은 어느 상한에도 없음. 미상: 연식 NULL 1 · 주행 NULL 1 · 주행 0 1.
ROWS = (
    [("Y17", 2017, 30_000, "현대")]
    + [(f"Y18-{i:02d}", 2018, 100_000, "현대") for i in range(13)]
    + [("Y20", 2020, 150_000, "현대"), ("Y22", 2022, 200_001, "기아")]
    + [("YN", None, 50_000, "현대"), ("KN", 2020, None, "현대"), ("K0", 2020, 0, "현대")]
)
TOTAL = len(ROWS)                                                           # 19
YEAR_COUNTS = {"2015": 18, "2018": 17, "2020": 4, "2022": 1}               # 누적(필터 없음)
KM_COUNTS = {"50000": 2, "100000": 15, "150000": 16, "200000": 16}         # 누적(필터 없음) — 200,001 은 어디에도 없음
KM_UNKNOWN = 2                                                              # KN(NULL) + K0(0)
YEAR_CHIP_RE = re.compile(r'<a href="([^"]*)" class="([^"]*)" title="연식 필터 해제">([^<]*)</a>')
KM_CHIP_RE = re.compile(r'<a href="([^"]*)" class="([^"]*)" title="주행거리 필터 해제">([^<]*)</a>')


def _card_chip_row(html: str) -> str:
    """UX-8(2026-09-27): 해제 칩은 카드 안 칩 행과, 카드가 접혔을 때 보이는 카드 밖 한 줄(#listFilterChips) 두 곳에 같은 매크로로
    그려진다 — 칩 수는 **카드 안 칩 행**에서 센다(두 줄의 동일성은 tests/test_ux8_filter_fold.py). 앵커: 첫 nc-chiprow ~ 폼 끝."""
    i = html.index('<div class="nc-chiprow')
    return html[i:html.index("</form>", i)]

NOTE_RE = re.compile(r"\(주행거리 미상 (\d+)건 제외\)")


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "feat2.db")
    db.init_db()
    for i, (vid, year, km, maker) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경4{i:04d}", year=year, mileage_km=km, maker=maker))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app)


def _get(client, url: str) -> str:
    r = client.get(url, headers=_PUBLIC)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _select_block(html: str, name: str) -> str:
    """`<select name="…"` 부터 그 `</select>` 까지."""
    i = html.index(f'<select name="{name}"')
    return html[i:html.index("</select>", i)]


def _options(block: str) -> list:
    """[(value, 나머지 속성, 표시 텍스트)]"""
    return re.findall(r'<option value="([^"]*)"([^>]*)>([^<]*)</option>', block)


def _grid_block(html: str) -> str:
    """좁은 폭 2열 그리드 래퍼 — 안에 div 가 없으므로 첫 `</div>` 가 그 끝이다."""
    i = html.index('<div class="grid grid-cols-2')
    return html[i:html.index("</div>", i)]


def _summary(html: str):
    m = re.search(r'<p id="condSummary"[^>]*>(.*?)</p>', html, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else None


def _total(html: str) -> int:
    return int(re.search(r"window\.NC_LIST_TOTAL=(\d+);", html).group(1))


def _save_body(html: str) -> str:
    i = html.index("function ncSaveSearch(")
    return html[i:html.index("(function(){", i)]      # 함수의 실제 끝(바로 다음 IIFE) — 고정 오프셋 창이 아니다


# ── ① 셀렉트 ────────────────────────────────────────────────────────────────

def test_fixture_is_not_void(client):
    html = _get(client, "/vehicles")
    assert _total(html) == TOTAL == 19, "픽스처 전제: 19행 전부 공개 목록에 보인다(미상 행 포함)"


@pytest.mark.parametrize("name,first,keys,labels,counts", [
    ("year_min", "전체 연식", service.YEAR_MIN_KEYS, service.YEAR_MIN_LABELS, YEAR_COUNTS),
    ("km_max", "전체 주행거리", service.KM_MAX_KEYS, service.KM_MAX_LABELS, KM_COUNTS),
])
def test_select_in_form_with_five_options_label_and_count(client, name, first, keys, labels, counts):
    html = _get(client, "/vehicles")
    form_i = html.index('<form method="get" action="/vehicles"')
    form_j = html.index("</form>", form_i)
    sel_i = html.index(f'<select name="{name}"')
    assert form_i < sel_i < form_j, "셀렉트는 검색 폼 안(제출 시 키가 실린다)"
    blk = _select_block(html, name)
    m = re.search(r'aria-label="([^"]+)"', blk)
    assert m and m.group(1).strip(), "기존 셀렉트 관례대로 aria-label 필수"
    assert "<optgroup" not in blk, "라벨이 축을 말하므로 optgroup 없음(가격대와 다른 점)"
    opts = _options(blk)
    assert len(opts) == 5, f"옵션은 '{first}' + 4 = 5개, 실제 {len(opts)}"
    assert opts[0][0] == "" and opts[0][2].strip() == first, "이웃 '전체 판정'·'전체 가격대' 와 같은 어순"
    assert [o[0] for o in opts[1:]] == list(keys), "옵션 순서는 service 상수 그대로"
    for key, attrs, text in opts[1:]:
        assert text.strip() == f"{labels[key]} ({counts[key]})", (key, text)
        assert "selected" not in attrs
    # 누적 표기 — 앞 옵션 ⊇ 뒤 옵션(연식 하한은 내림, 주행 상한은 오름). 합 ≠ 총수임을 여기서 고정한다(디자인 검수에 물을 것).
    shown = [counts[k] for k in keys]
    assert shown == sorted(shown, reverse=(name == "year_min")) and sum(shown) != TOTAL


def test_selects_sit_between_price_and_sort(client):
    html = _get(client, "/vehicles")
    order = [html.index(f'<select name="{n}"') for n in ("price", "year_min", "km_max", "sort")]
    assert order == sorted(order), "가격대 → 연식 → 주행거리 → 정렬"


@pytest.mark.parametrize("url,name,key,expected_total", [
    ("/vehicles?year_min=2018", "year_min", "2018", 17),
    ("/vehicles?km_max=100000", "km_max", "100000", 15),
])
def test_selected_option_count_equals_list_total(client, url, name, key, expected_total):
    """패싯 규칙: 선택된 옵션의 (건수) == 목록 '총 N건'."""
    html = _get(client, url)
    assert _total(html) == expected_total
    text = next(t for k, _, t in _options(_select_block(html, name)) if k == key)
    labels = service.YEAR_MIN_LABELS if name == "year_min" else service.KM_MAX_LABELS
    assert text.strip() == f"{labels[key]} ({expected_total})"


def test_other_axis_counts_reflect_selection(client):
    """축 3종 상호 반영: 연식을 고르면 주행거리 셀렉트 숫자가 바뀌고, 연식 셀렉트 숫자는 그대로(자기 축은 모수에서 빠진다)."""
    html = _get(client, "/vehicles?year_min=2018")
    year = {k: t.strip() for k, _, t in _options(_select_block(html, "year_min")) if k}
    km = {k: t.strip() for k, _, t in _options(_select_block(html, "km_max")) if k}
    assert year == {k: f"{service.YEAR_MIN_LABELS[k]} ({YEAR_COUNTS[k]})" for k in service.YEAR_MIN_KEYS}, "자기 축 불변"
    # 연식 ≥2018 모수: Y18×13(10만)·Y20(15만)·Y22(20만 초과)·KN·K0 → ≤5만 0 · ≤10만 13 · ≤15만 14 · ≤20만 14
    assert km == {"50000": f"{service.KM_MAX_LABELS['50000']} (0)", "100000": f"{service.KM_MAX_LABELS['100000']} (13)",
                  "150000": f"{service.KM_MAX_LABELS['150000']} (14)", "200000": f"{service.KM_MAX_LABELS['200000']} (14)"}


# ── ② 선택 상태 · 해제 칩 · (필터 적용) ───────────────────────────────────────

@pytest.mark.parametrize("url,name,key,chip_re,labels", [
    ("/vehicles?year_min=2018", "year_min", "2018", YEAR_CHIP_RE, service.YEAR_MIN_LABELS),
    ("/vehicles?km_max=100000", "km_max", "100000", KM_CHIP_RE, service.KM_MAX_LABELS),
])
def test_selected_option_chip_and_filter_applied_marker(client, url, name, key, chip_re, labels):
    html = _get(client, url)
    attrs = {k: a for k, a, _ in _options(_select_block(html, name))}
    assert "selected" in attrs[key]
    assert all("selected" not in a for k, a in attrs.items() if k != key)
    chips = chip_re.findall(_card_chip_row(html))
    assert len(chips) == 1, f"해제 칩은 정확히 하나, 실제 {len(chips)}"
    href, cls, text = chips[0]
    assert text.strip() == f"{labels[key]} ✕", text          # 라벨 + ✕ 그대로(접두 없음 — 320px 페이드 규칙)
    assert href.startswith("/vehicles") and f"{name}=" not in href, href
    assert href == "/vehicles" or (href.startswith("/vehicles?") and len(href) > len("/vehicles?")), href
    # 톤: 가격대·입찰예정 칩과 같은 primary 소프트. 범위 선택은 경고가 아니다 — 빨강·앰버 금지. 스크롤 줄이라 한 줄 유지.
    assert "bg-primary/10" in cls and "text-primary" in cls and "rounded-full" in cls
    assert not re.search(r"rose|amber|red-|orange", cls), cls
    assert "whitespace-nowrap" in cls and "shrink-0" in cls
    assert "(필터 적용)" in html
    assert ">필터 초기화</a>" in html, "has_filter 에 두 키가 들어가야 초기화 칩·링크가 뜬다"


def test_chip_links_drop_only_their_own_axis_and_keep_the_rest(client):
    html = _get(client, "/vehicles?year_min=2018&km_max=100000&maker=%ED%98%84%EB%8C%80&upcoming=30&price=1000-2000")
    y_href, _, y_text = YEAR_CHIP_RE.findall(html)[0]
    k_href, _, k_text = KM_CHIP_RE.findall(html)[0]
    assert "year_min=" not in y_href and "km_max=100000" in y_href and "maker=" in y_href and "upcoming=30" in y_href and "price=1000-2000" in y_href
    assert "km_max=" not in k_href and "year_min=2018" in k_href and "maker=" in k_href and "upcoming=30" in k_href and "price=1000-2000" in k_href
    assert y_text.strip() == f"{service.YEAR_MIN_LABELS['2018']} ✕" and k_text.strip() == f"{service.KM_MAX_LABELS['100000']} ✕"
    # 칩 순서: 가격대 → 연식 → 주행거리 → 입찰예정(가격대 칩 뒤에 붙였다)
    assert html.index('title="가격대 필터 해제"') < html.index('title="연식 필터 해제"') < html.index('title="주행거리 필터 해제"') < html.index("입찰예정 30일 ✕")
    # 가격대 해제 칩도 두 키를 보존한다(qs_no_price 계약)
    p_href = re.search(r'<a href="([^"]*)" class="[^"]*" title="가격대 필터 해제">', html).group(1)
    assert "year_min=2018" in p_href and "km_max=100000" in p_href and "price=" not in p_href


# ── ③ 없음·오염·중복 → 칩 없음 ───────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "/vehicles",
    "/vehicles?year_min=&km_max=",
    "/vehicles?year_min=abc&km_max=abc",
    "/vehicles?year_min=2018.0&km_max=1e5",
    "/vehicles?year_min=2019&km_max=99999",                    # 화이트리스트 밖
    "/vehicles?year_min=2018&year_min=2020&km_max=50000&km_max=50000",   # 중복 → 서버가 필터 없음으로 정규화 → 칩도 없어야 한다
])
def test_no_effective_axis_means_no_chip_and_nothing_selected(client, url):
    html = _get(client, url)
    assert 'title="연식 필터 해제"' not in html and 'title="주행거리 필터 해제"' not in html
    for label in list(service.YEAR_MIN_LABELS.values()) + list(service.KM_MAX_LABELS.values()):
        assert f"{label} ✕" not in html
    for name in ("year_min", "km_max"):
        assert all("selected" not in a for k, a, _ in _options(_select_block(html, name)) if k)
    assert "(필터 적용)" not in html and ">필터 초기화</a>" not in html
    assert _total(html) == TOTAL


# ── ④ name= 정확히 1번 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "/vehicles",
    "/vehicles?year_min=2018&km_max=100000",
    "/vehicles?year_min=2020&km_max=100000&price=1000-2000&sort=sale_date&maker=%ED%98%84%EB%8C%80&upcoming=30&cond=damaged",
    "/vehicles?year_min=2015&bucket=wait",
    "/vehicles?km_max=200000&segment=sedan",
    "/vehicles?year_min=2022&km_max=50000",     # 0건 화면에도 폼은 그려진다
])
def test_axis_names_appear_exactly_once(client, url):
    html = _get(client, url)
    for name in ("year_min", "km_max"):
        assert html.count(f'name="{name}"') == 1, f"hidden 으로 {name} 을 또 넣으면 중복 → 필터 해제(서버 규칙)"
        assert f'type="hidden" name="{name}"' not in html


# ── ⑤ 검색 저장 라벨 사전 — 서버 주입 · 단일 원천 ─────────────────────────────

def test_save_search_script_gets_label_maps_from_server(client):
    body = _save_body(_get(client, "/vehicles"))
    ym = re.search(r"var YM=(\{.*?\});", body, re.S)
    km = re.search(r"var KM=(\{.*?\});", body, re.S)
    assert ym and km, "key→라벨 사전 `var YM={...}`·`var KM={...}` 이 주입돼야 한다"
    assert json.loads(ym.group(1)) == service.YEAR_MIN_LABELS
    assert json.loads(km.group(1)) == service.KM_MAX_LABELS
    assert "p.get('year_min')" in body and "parts.push(YM[ym])" in body
    assert "p.get('km_max')" in body and "parts.push(KM[km])" in body
    assert "'+YM[" not in body and "'+KM[" not in body, "라벨이 축을 말하므로 접두 없음(가격대 '최저가 ' 와 다르다)"
    # 기존 부품(FEAT-1 ⑤·UX 3차 ⑦ 가 고정)은 그대로
    assert "p.get('price')" in body and "parts.push('최저가 '+PB[pb])" in body


def test_template_source_has_no_hardcoded_labels_or_keys():
    """라벨·경계는 service.YEAR_MIN_OPTIONS·KM_MAX_OPTIONS 한 곳 — 템플릿·JS(주석 포함)에 다시 적으면 한쪽만 바뀌는 사고가 난다."""
    src = TEMPLATE.read_text(encoding="utf-8")
    for label in list(service.YEAR_MIN_LABELS.values()) + list(service.KM_MAX_LABELS.values()):
        assert label not in src, f"템플릿에 라벨 리터럴 {label!r}"
    for key in service.YEAR_MIN_KEYS + service.KM_MAX_KEYS:
        assert f'"{key}"' not in src and f"'{key}'" not in src, f"템플릿에 key 리터럴 {key!r}"


# ── ⑥ 페이지네이션 · 입찰예정 30일만 링크가 두 키 유지 ───────────────────────────

def test_pagination_and_upcoming_links_keep_both_keys(client):
    html = _get(client, "/vehicles?year_min=2018&km_max=200000")
    assert _total(html) == 14, "Y18×13 + Y20 = 14행(페이지 크기 12) → 페이지네이션이 실제로 그려진다(공허 통과 방지)"
    page_links = re.findall(r'href="(/vehicles\?[^"]*page=\d+)"', html)
    assert page_links
    assert all("year_min=2018" in h and "km_max=200000" in h for h in page_links), page_links
    m = re.search(r'href="([^"]*upcoming=30)"[^>]*>입찰예정 30일만<', html)
    assert m and "year_min=2018" in m.group(1) and "km_max=200000" in m.group(1), m and m.group(1)


# ── ⑦ 좁은 폭 그리드 ─────────────────────────────────────────────────────────

def test_narrow_grid_has_six_selects_and_full_width_axes(client):
    html = _get(client, "/vehicles")
    grid = _grid_block(html)
    assert grid.count("<select ") == 6, "판정·제조사·가격대·연식·주행거리·정렬"
    for name in ("year_min", "km_max"):
        m_sel = re.search(rf'<select name="{name}"[^>]*class="([^"]*)"', grid)
        assert m_sel and "col-span-2" in m_sel.group(1), \
            f"{name} 은 좁은 폭에서 전폭 — 반 칸(320px 글자 영역 80px)에는 선택 라벨(108~110px)이 '(74' 로 잘린다(2026-09-27 실측)"
    m = re.search(r'<button class="([^"]*)">\s*<span class="material-symbols-outlined text-base">filter_list</span> 적용</button>', grid)
    assert m and "w-full" in m.group(1) and "col-span" not in m.group(1), "[적용]은 정렬 옆 마지막 칸(2+1+1+1+2 다섯 줄, 빈 셀 없음)"
    assert ".col-span-2{" in APP_CSS.read_text(encoding="utf-8", errors="ignore")


# ── ⑧ 주행거리 미상 제외 표기 ─────────────────────────────────────────────────

def test_unknown_km_note_only_when_km_max_selected_and_nonzero(client):
    with_km = _get(client, "/vehicles?km_max=100000")
    s = _summary(with_km)
    assert s is not None and NOTE_RE.search(s) and int(NOTE_RE.search(s).group(1)) == KM_UNKNOWN, s
    assert s.startswith(f"{service.KM_MAX_LABELS['100000']} (주행거리 미상 {KM_UNKNOWN}건 제외)"), s
    # mut 톤·부품 밖: 문구 span 은 text-txt 가 아니고 조건 구분점(·) 앞이 아니라 부품 뒤에 붙는다
    note_tag = re.search(r'<span class="([^"]*)">\(주행거리 미상 \d+건 제외\)</span>', with_km)
    assert note_tag and "text-mut" in note_tag.group(1) and "text-txt" not in note_tag.group(1)
    # 주행거리 셀렉트 title 에도 같은 문장, 연식 셀렉트에는 없음
    km_title = re.search(r'<select name="km_max"[^>]*title="([^"]*)"', with_km).group(1)
    assert f"주행거리 미상 {KM_UNKNOWN}건 제외" in km_title and "괄호 건수는 현재 적용된 조건 기준" in km_title
    assert "미상" not in re.search(r'<select name="year_min"[^>]*title="([^"]*)"', with_km).group(1)
    # km_max 없음 → 컨텍스트에 값이 있어도 '제외' 를 쓰지 않는다
    for url in ("/vehicles", "/vehicles?year_min=2018", "/vehicles?maker=%ED%98%84%EB%8C%80&sort=mileage"):
        html = _get(client, url)
        assert "주행거리 미상" not in html, url
    # km_max 있음 + 미상 0건(연식 ≥2022 모수 = Y22 뿐) → 빠진 게 없으니 안 그린다
    zero_unknown = _get(client, "/vehicles?year_min=2022&km_max=50000")
    assert "주행거리 미상" not in zero_unknown


def test_unknown_km_count_tracks_current_population(client):
    """미상 건수는 주행거리 축만 뺀 현재 모수 기준 — 제조사 기아(Y22 뿐, 미상 0) vs 현대(KN·K0 = 2)."""
    kia = _get(client, "/vehicles?km_max=200000&maker=%EA%B8%B0%EC%95%84")
    assert "주행거리 미상" not in kia and _total(kia) == 0
    hy = _get(client, "/vehicles?km_max=200000&maker=%ED%98%84%EB%8C%80")
    assert f"(주행거리 미상 {KM_UNKNOWN}건 제외)" in _summary(hy)


# ── ⑨ 0건 옵션 · 빈 결과 ─────────────────────────────────────────────────────

def test_zero_count_options_and_empty_result_offer_reset(client):
    html = _get(client, "/vehicles?year_min=2022&km_max=50000")   # Y22 는 200,001km → 0건
    assert _total(html) == 0
    assert "조건에 맞는 물건이 없습니다" in html and "필터를 바꾸거나 초기화해 보세요" in html
    assert "을 실행하면 물건이 채워집니다" not in html, "필터 탓인데 운영 도구 안내가 나오면 오도"
    # 연식 셀렉트(주행 ≤5만 모수 = Y17·YN): 2015 이후 1 · 나머지 0 — 0건도 '(0)' 으로 그린다
    year = {k: t.strip() for k, _, t in _options(_select_block(html, "year_min")) if k}
    assert year["2022"] == f"{service.YEAR_MIN_LABELS['2022']} (0)" and year["2015"] == f"{service.YEAR_MIN_LABELS['2015']} (1)"
    km = {k: t.strip() for k, _, t in _options(_select_block(html, "km_max")) if k}
    assert all(t.endswith(" (0)") for t in km.values()), km


# ── ⑩ 요약 줄 부품 · 큰글씨 접힌 머리 ────────────────────────────────────────

def test_summary_line_parts_and_collapsed_head(client):
    url = "/vehicles?maker=%ED%98%84%EB%8C%80&year_min=2018&km_max=100000&sort=sale_date"
    html = _get(client, url)
    assert _total(html) == 13
    s = _summary(html)
    y, k = service.YEAR_MIN_LABELS["2018"], service.KM_MAX_LABELS["100000"]
    # 미상 문구는 주행거리 부품 **바로 뒤**(정렬 앞) — 디자인 검수 2026-09-27 조건 1. 부품 순서·수는 그대로.
    assert s == f"현대 · {y} · {k} (주행거리 미상 {KM_UNKNOWN}건 제외) · 매각기일순 · 필터 초기화", s
    # 뒤에 부품이 둘(정렬·페이지) 와도 자리는 주행거리 뒤 — 13행이라 2페이지가 실제로 있다(공허 통과 방지: 총수 13 > 페이지 12)
    s2 = _summary(_get(client, url + "&page=2"))
    assert s2 == f"현대 · {y} · {k} (주행거리 미상 {KM_UNKNOWN}건 제외) · 매각기일순 · 2/2페이지 · 필터 초기화", s2
    # 주행거리가 마지막 부품이면(정렬 recent) 문구가 그 뒤·초기화 앞 — 자리 규칙은 같다
    s3 = _summary(_get(client, "/vehicles?maker=%ED%98%84%EB%8C%80&year_min=2018&km_max=100000"))
    assert s3 == f"현대 · {y} · {k} (주행거리 미상 {KM_UNKNOWN}건 제외) · 필터 초기화", s3
    # 부품 span 은 text-txt·nowrap(UX-5 규칙) — 두 라벨 모두
    for label in (y, k):
        assert f'<span class="text-txt whitespace-nowrap">{label}</span>' in html
    # 큰글씨 접힌 머리: 첫 부품 + '외 N' — N 은 부품 수(4−1=3), 미상 문구는 세지 않는다. title 은 부품 전문(미상 문구 없음)
    head = html[html.index("<summary"):html.index("</summary>")]
    assert "— 현대 외 3" in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", head))
    assert f'title="현대 · {y} · {k} · 매각기일순"' in head
    assert "미상" not in head
