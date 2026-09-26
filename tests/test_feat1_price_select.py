"""FEAT-1 가격대 필터 — 화면(vehicles.html) 계약 (오너 승인 2026-09-26, 지시서 2026-09-26-13).

서버 계약(경계·NULL·COUNT·패리티)은 tests/test_price_band_filter.py 가 지킨다. 이 파일은 **렌더된 HTML** 만 본다:
  ① `<select name="price">` 가 검색 폼 안에 있고 옵션 6개(전체 가격대 + 5구간) · 표기 `라벨 (건수)` · aria-label
     축 표시(디자인 검수 2026-09-26, 지시서 -16): 5구간은 `<optgroup label="최저매각가 기준">` 안, 첫 옵션은 밖.
     ⚠ 옵션 텍스트에는 축 낱말을 넣지 않는다 — 좁은 폭에서 '(41' 로 잘리는 회귀. 첫 옵션 어순은 이웃(`전체 판정`)과 같게.
  ② `?price=<key>` 면 그 옵션만 selected · 해제 칩(`라벨 ✕` — 축 접두 없음) · `(필터 적용)`
     ⚠ 칩에 '최저가 ' 접두를 붙이지 않는다 — 2026-09-26 실측: 320px 에서 접두 칩 우변 299 > 줄 페이드 시작 275
     (줄 우변 291 − 16) → ✕ 가 페이드에 들고 pill 오른쪽이 잘렸다. 접두 없는 우변 265 는 앞이다(지시서 -16: 결정은 측정이 한다).
  ③ price 없음·오염값·중복이면 칩 없음 · 어느 구간도 selected 아님
  ④ `name="price"` 는 HTML 에 **정확히 1번** — hidden 으로 또 넣으면 서버가 중복으로 보고 필터를 푼다
  ⑤ `ncSaveSearch` 의 key→라벨 사전은 서버(price_bands)에서 주입되고, 템플릿 소스에는 라벨·key 리터럴이 없다(단일 원천).
     저장 검색 라벨에는 축 접두 `최저가 ` 가 붙는다(`현대 · 최저가 3,000만~`) — 폭 제약이 없는 즐겨찾기 카드라 칩과 달리 붙인다.
     사전 값(PB)은 서버 라벨 그대로
  ⑥ 페이지네이션 · '입찰예정 30일만' 링크가 `price=` 를 유지한다
  ⑦ 좁은 폭 그리드: 셀렉트 4개 중 가격대만 전폭(col-span-2) + [적용]은 정렬 옆 — 2+1+2 세 줄, 빈 셀 없음·건수 안 잘림
     (빌드된 app.css 에 유틸리티 존재)
검사는 전부 **앵커 문자열**로 한다 — 줄 번호·매직 오프셋 창(`d[i:i+4200]` 류)을 쓰지 않는다.
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

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·미래 기일·낙찰 아님) — 서버 테스트와 같은 관례
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "sale_date": "2999-01-01", "model": "쏘나타",
        "status": "완료", "fail_count": 1, "median_price": 15_000_000, "appraisal_value": 20_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}

# (id, 최저매각가, 제조사). 1,000~2,000만 구간을 **13행**(페이지 크기 12 초과)으로 채워 페이지네이션이 실제로 그려진다 —
# 링크가 price= 를 유지하는지 공허 통과 없이 검사하기 위해서다. 2,000~3,000만 은 0건으로 비워 빈 결과 화면도 본다.
ROWS = (
    [("A1", 3_000_000, "현대"), ("A2", 4_999_999, "기아")]                            # ~500만 2
    + [("B1", 5_000_000, "기아")]                                                       # 500~1,000만 1 (★ 경계: 정확히 500만)
    + [(f"C{i:02d}", 15_000_000, "현대" if i % 2 else "기아") for i in range(13)]        # 1,000~2,000만 13
    + [("E1", 30_000_000, "현대")]                                                      # 3,000만~ 1 (★ 경계: 정확히 3,000만)
    + [("N1", None, "현대")]                                                            # 최저가 미상 — 구간을 고르면 빠진다
)
COUNTS = {"0-500": 2, "500-1000": 1, "1000-2000": 13, "2000-3000": 0, "3000-": 1}
CHIP_RE = re.compile(r'<a href="([^"]*)" class="([^"]*)" title="가격대 필터 해제">([^<]*)</a>')


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "feat1.db")
    db.init_db()
    for i, (vid, price, maker) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경2{i:04d}", min_sale_price=price, maker=maker))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app)


def _get(client, url: str) -> str:
    r = client.get(url, headers=_PUBLIC)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _select_block(html: str) -> str:
    """`<select name="price"` 부터 그 `</select>` 까지 — 셀렉트 안에는 option 만 있다."""
    i = html.index('<select name="price"')
    return html[i:html.index("</select>", i)]


def _options(block: str) -> list:
    """[(value, 나머지 속성, 표시 텍스트)]"""
    return re.findall(r'<option value="([^"]*)"([^>]*)>([^<]*)</option>', block)


def _optgroup_block(block: str) -> str:
    """셀렉트 블록 안의 `<optgroup …>` 부터 `</optgroup>` 까지(안쪽만)."""
    i = block.index("<optgroup ")
    return block[i:block.index("</optgroup>", i)]


def _grid_block(html: str) -> str:
    """좁은 폭 2열 그리드 래퍼(`<div class="grid grid-cols-2`) — 안에 div 가 없으므로 첫 `</div>` 가 그 끝이다."""
    i = html.index('<div class="grid grid-cols-2')
    return html[i:html.index("</div>", i)]


# ── ① 셀렉트 ────────────────────────────────────────────────────────────────

def test_select_in_form_with_six_options_label_and_count(client):
    html = _get(client, "/vehicles")
    form_i = html.index('<form method="get" action="/vehicles"')
    form_j = html.index("</form>", form_i)
    sel_i = html.index('<select name="price"')
    assert form_i < sel_i < form_j, "가격대 셀렉트는 검색 폼 안에 있어야 한다(제출 시 price 가 실린다)"
    blk = _select_block(html)
    m = re.search(r'aria-label="([^"]+)"', blk)
    assert m and m.group(1).strip(), "기존 셀렉트 관례대로 aria-label 필수"
    opts = _options(blk)
    assert len(opts) == 6, f"옵션은 '전체 가격대' + 5구간 = 6개, 실제 {len(opts)}"
    assert opts[0][0] == "" and opts[0][2].strip() == "전체 가격대",         "이웃 '전체 판정'·'전체 제조사' 와 같은 어순(디자인 검수 2026-09-26 ②-1-③)"
    assert [o[0] for o in opts[1:]] == list(service.PRICE_BAND_KEYS), "구간 순서는 PRICE_BANDS 그대로"
    for key, attrs, text in opts[1:]:
        assert text.strip() == f"{service.PRICE_BAND_LABELS[key]} ({COUNTS[key]})", (key, text)
        assert "selected" not in attrs


def test_bands_grouped_under_axis_optgroup_and_option_text_has_no_axis_word(client):
    """축 낱말은 optgroup 라벨(고르는 순간에만 보임, 닫힌 셀렉트 폭 0 증가)에만 — 옵션 텍스트에 넣으면
    좁은 폭 반 칸에서 '(41' 로 잘리던 회귀(2026-09-26 실측)로 돌아간다."""
    blk = _select_block(_get(client, "/vehicles"))
    assert blk.count("<optgroup ") == 1 and blk.count("</optgroup>") == 1
    m = re.search(r'<optgroup label="([^"]+)">', blk)
    assert m and m.group(1) == "최저매각가 기준", m and m.group(1)
    grp = _optgroup_block(blk)
    assert [o[0] for o in _options(grp)] == list(service.PRICE_BAND_KEYS), "5구간 전부 optgroup 안"
    assert blk.index('<option value="">') < blk.index("<optgroup "), "'전체 가격대' 는 optgroup 밖(앞)"
    assert '<option value="">' not in grp
    for _key, _attrs, text in _options(blk):
        for word in ("최저매각가", "최저가", "시세", "감정가"):
            assert word not in text, f"옵션 텍스트에 축 낱말 {word!r}: {text!r} — optgroup 라벨에만 둔다"


def test_selected_band_count_equals_list_total(client):
    """패싯 규칙: 선택된 구간의 (건수) == 목록 '총 N건'. 라벨의 숫자가 목록과 다르면 사용자가 계산을 의심한다."""
    html = _get(client, "/vehicles?price=1000-2000")
    total = int(re.search(r"window\.NC_LIST_TOTAL=(\d+);", html).group(1))
    text = next(t for k, _, t in _options(_select_block(html)) if k == "1000-2000")
    assert total == 13 and text.strip() == f"{service.PRICE_BAND_LABELS['1000-2000']} (13)"


# ── ② 선택 상태 · 해제 칩 · (필터 적용) ───────────────────────────────────────

def test_selected_option_chip_and_filter_applied_marker(client):
    html = _get(client, "/vehicles?price=1000-2000")
    attrs = {k: a for k, a, _ in _options(_select_block(html))}
    assert "selected" in attrs["1000-2000"]
    assert all("selected" not in a for k, a in attrs.items() if k != "1000-2000")
    chips = CHIP_RE.findall(html)
    assert len(chips) == 1, f"해제 칩은 정확히 하나, 실제 {len(chips)}"
    href, cls, text = chips[0]
    # 칩 텍스트는 라벨 + ✕ 그대로 — 접두를 붙이면 320px 에서 ✕ 가 페이드 마스크에 든다(모듈 docstring ②, 실측).
    assert text.strip() == f"{service.PRICE_BAND_LABELS['1000-2000']} ✕", text
    assert not text.strip().startswith("최저가"), "칩 접두 금지(320px 실측 회귀)"
    # 서버의 _filters 에는 sort 기본값(recent)이 항상 실리므로 qs_no_price 는 보통 'sort=recent' 다(실측) —
    # 칩 링크는 price 만 빠진 /vehicles?… 여야 하고, '?' 만 남는 빈 꼬리는 없어야 한다.
    assert href.startswith("/vehicles") and "price=" not in href, href
    assert href == "/vehicles" or (href.startswith("/vehicles?") and len(href) > len("/vehicles?")), href
    # 톤: '입찰예정' 칩과 같은 primary 소프트. 가격대는 경고가 아니다 — 빨강·앰버 금지. 스크롤 줄이라 한 줄 유지.
    assert "bg-primary/10" in cls and "text-primary" in cls and "rounded-full" in cls
    assert not re.search(r"rose|amber|red-|orange", cls), cls
    assert "whitespace-nowrap" in cls and "shrink-0" in cls
    assert "(필터 적용)" in html


def test_chip_link_drops_only_price_and_keeps_other_filters(client):
    html = _get(client, "/vehicles?price=1000-2000&maker=%ED%98%84%EB%8C%80&upcoming=30")
    href, _, text = CHIP_RE.findall(html)[0]
    assert "price=" not in href
    assert "maker=" in href and "upcoming=30" in href
    assert text.strip() == f"{service.PRICE_BAND_LABELS['1000-2000']} ✕", text


# ── ③ price 없음·오염·중복 → 칩 없음 ─────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "/vehicles",
    "/vehicles?price=",
    "/vehicles?price=abc",
    "/vehicles?price=0-500&price=3000-",      # 중복 → 서버가 필터 없음으로 정규화 → 칩도 없어야 한다
    "/vehicles?price=1000-2000&price=1000-2000",
])
def test_no_effective_price_means_no_chip_and_nothing_selected(client, url):
    html = _get(client, url)
    assert 'title="가격대 필터 해제"' not in html
    for label in service.PRICE_BAND_LABELS.values():
        assert f"{label} ✕" not in html
    assert all("selected" not in a for k, a, _ in _options(_select_block(html)) if k)
    assert "(필터 적용)" not in html


# ── ④ name="price" 정확히 1번 ────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "/vehicles",
    "/vehicles?price=1000-2000",
    "/vehicles?price=1000-2000&maker=%ED%98%84%EB%8C%80&upcoming=30&cond=damaged&sort=sale_date",
    "/vehicles?price=0-500&bucket=wait",
    "/vehicles?price=3000-&segment=sedan",
    "/vehicles?price=2000-3000",              # 0건 화면에도 폼은 그려진다
])
def test_price_name_appears_exactly_once(client, url):
    html = _get(client, url)
    assert html.count('name="price"') == 1, "hidden 으로 price 를 또 넣으면 중복 → 필터 해제(서버 규칙)"
    assert 'type="hidden" name="price"' not in html


# ── ⑤ 검색 저장 라벨 사전 — 서버 주입 · 단일 원천 ─────────────────────────────

def test_save_search_script_gets_label_map_from_server(client):
    html = _get(client, "/vehicles")
    i = html.index("function ncSaveSearch(")
    body = html[i:html.index("(function(){", i)]      # 함수의 실제 끝(바로 다음 IIFE) — 고정 오프셋 창이 아니다
    assert "p.get('price')" in body, "저장 라벨 parts 에 가격대가 들어가야 한다"
    m = re.search(r"var PB=(\{.*?\});", body, re.S)
    assert m, "key→라벨 사전 `var PB={...}` 이 주입돼야 한다"
    assert json.loads(m.group(1)) == service.PRICE_BAND_LABELS, "사전 값은 서버 라벨 그대로(접두는 여기 넣지 않는다)"
    assert "parts.push('최저가 '+PB[pb])" in body, "저장 검색 라벨은 해제 칩과 같은 접두 → '현대 · 최저가 3,000만~'"


def test_template_source_has_no_hardcoded_band_labels_or_keys():
    """라벨·경계는 service.PRICE_BANDS 한 곳 — 템플릿·JS 에 다시 적으면 한쪽만 바뀌는 사고가 난다."""
    src = TEMPLATE.read_text(encoding="utf-8")
    for label in service.PRICE_BAND_LABELS.values():
        assert label not in src, f"템플릿에 라벨 리터럴 {label!r}"
    for key in service.PRICE_BAND_KEYS:
        assert f'"{key}"' not in src and f"'{key}'" not in src, f"템플릿에 key 리터럴 {key!r}"


# ── ⑥ 페이지네이션 · 입찰예정 30일만 링크가 price 유지 ──────────────────────────

def test_pagination_and_upcoming_links_keep_price(client):
    html = _get(client, "/vehicles?price=1000-2000")
    assert int(re.search(r"window\.NC_LIST_TOTAL=(\d+);", html).group(1)) == 13
    page_links = re.findall(r'href="(/vehicles\?[^"]*page=\d+)"', html)
    assert page_links, "13행(페이지 크기 12) → 페이지네이션 링크가 실제로 그려져야 한다(공허 통과 방지)"
    assert all("price=1000-2000" in h for h in page_links), page_links
    m = re.search(r'href="([^"]*upcoming=30)"[^>]*>입찰예정 30일만<', html)
    assert m and "price=1000-2000" in m.group(1), m and m.group(1)


# ── ⑦ 좁은 폭 그리드 — 빈 셀 없음 · 빈 결과 안내 ──────────────────────────────

def test_narrow_grid_has_four_selects_and_full_width_apply(client):
    html = _get(client, "/vehicles")
    grid = _grid_block(html)
    assert grid.count("<select ") == 4, "판정·제조사·가격대·정렬"
    m_sel = re.search(r'<select name="price"[^>]*class="([^"]*)"', grid)
    assert m_sel and "col-span-2" in m_sel.group(1), \
        "가격대 셀렉트는 좁은 폭에서 전폭 — 반 칸(360px 147px)에는 '라벨 (건수)' 가 '(41' 로 잘린다(2026-09-26 실측)"
    m = re.search(r'<button class="([^"]*)">\s*<span class="material-symbols-outlined text-base">filter_list</span> 적용</button>', grid)
    assert m and "w-full" in m.group(1) and "col-span" not in m.group(1), \
        "2 + 1 + 2 = 세 줄: [적용]은 정렬 옆 여섯째 칸 — 전폭으로 두면 일곱째 칸이 빈다"
    css = APP_CSS.read_text(encoding="utf-8", errors="ignore")
    assert ".col-span-2{" in css, "npm run build:css 가 col-span-2 를 내보내야 한다"


def test_empty_result_under_price_filter_offers_reset_not_ops_hint(client):
    html = _get(client, "/vehicles?price=2000-3000")   # 0건 구간 — 셀렉트 표기도 (0)
    assert "조건에 맞는 물건이 없습니다" in html
    assert "필터를 바꾸거나 초기화해 보세요" in html
    assert "을 실행하면 물건이 채워집니다" not in html, "필터 탓인데 운영 도구 안내가 나오면 오도"
    assert f"{service.PRICE_BAND_LABELS['2000-3000']} (0)" in html
