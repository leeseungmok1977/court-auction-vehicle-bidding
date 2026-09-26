"""UX-2 탭 복귀형 · UX-5 조건 표면 · UX-1 칩 ✕ 교정 · UX-3 구분 줄 — 화면 회귀 (지시서 2026-09-26-23, 오너 승인 2026-09-26).

배경(검색 UX 점검 2026-09-26): 하단 탭·사이드바 `차량목록`이 필터·페이지·스크롤을 전부 버렸다(12회 전부 초기화, 상세 ←·뒤로가기는
복원) → 탭을 **마지막 목록으로 복귀**(30분 TTL, 재탭 = 맨 위). 활성 조건을 말하는 표면이 반쪽(검색어 칩 없음·제조사/정렬 칩 안 됨·
큰글씨 접힌 머리 무표시) → `총 N건` 위 **조건 요약 한 줄** + 큰글씨 접힌 머리 재사용 + 검색어 칩 + [적용] 변경 표시.
날짜·결과·법원 칩 ✕ 가 필터 전부를 초기화(`/vehicles`)·이탈(`/courts`) → 그 조건만 해제(qs_no_*). `매각기일순` 경계에 구분 줄.

두 층:
  A. 템플릿(TestClient, 렌더 HTML 의 **앵커 문자열**만 — 줄 번호·오프셋 창 금지). TestClient 의 host 는 `testserver`(loopback 아님)라
     공개 뷰로 렌더된다.
  B. 동작(Playwright Chromium, 같은 프로세스의 스레드 uvicorn — 임시 DB). playwright/브라우저가 없으면 skip.
     포트는 OS 가 비운 것(8765·8000·8811·8797·8841·8877 금지 — 운영·다른 담당의 로컬 서버).
"""
import html as html_mod
import re
import socket
import threading
import time
from datetime import date, timedelta
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from web import db

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
BASE_TPL = (ROOT / "web/templates/base.html").read_text(encoding="utf-8")
FRAME = (ROOT / "web/static/frame.html").read_text(encoding="utf-8")
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877}

TODAY = date.today()


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·낙찰 아님) — FEAT-1·UX-1 테스트와 같은 관례.
# min_sale_price 12,000,000 = 가격대 '1,000~2,000만'(1000-2000) 안.
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(rows):
    """rows: (id, model, maker, sale_date, court). DB_PATH 는 conftest autouse 픽스처가 이미 tmp 로 바꿔 놓았다."""
    db.init_db()
    for i, (vid, model, maker, sd, court) in enumerate(rows):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경4{i:04d}", model=model, maker=maker, sale_date=sd, court=court))


# 현대 14대(미래 기일) → 12/페이지라 2페이지. 기아 1·과거 기일 1 은 다른 필터의 대조군.
HYUNDAI_14 = [(f"H{i:02d}", "쏘나타(SONATA)", "현대", _d(3 + i), "수원지방법원") for i in range(14)]
OTHERS = [("K1", "K5", "기아", _d(5), "인천지방법원"), ("P1", "그랜저(GRANDEUR)", "현대", "2026-09-01", "대구지방법원")]
# 구분 줄 픽스처: 미래 3 · 과거 3 (12/페이지 → 1페이지 안 idx 3)
SPLIT_3_3 = [("F1", "쏘나타", "현대", _d(1), "수원지방법원"), ("F2", "쏘나타", "현대", _d(2), "수원지방법원"),
             ("F3", "쏘나타", "현대", _d(3), "수원지방법원"), ("Q1", "쏘나타", "현대", _d(-1), "수원지방법원"),
             ("Q2", "쏘나타", "현대", _d(-2), "수원지방법원"), ("Q3", "쏘나타", "현대", _d(-3), "수원지방법원")]
# 경계가 2페이지 첫 행: 미래 12 · 과거 3
SPLIT_12_3 = [(f"F{i:02d}", "쏘나타", "현대", _d(1 + i), "수원지방법원") for i in range(12)] + \
             [(f"Q{i}", "쏘나타", "현대", _d(-1 - i), "수원지방법원") for i in range(3)]
PAST_ONLY = [(f"Q{i}", "쏘나타", "현대", _d(-1 - i), "수원지방법원") for i in range(3)]


@pytest.fixture
def client():
    import web.app as A
    return TestClient(A.app)


def _get(client, url: str) -> str:
    r = client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _ctx(client, url: str) -> dict:
    r = client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.context


def _text(html_fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html_fragment)).strip()


def _cond_summary(html: str):
    m = re.search(r'<p id="condSummary"[^>]*>(.*?)</p>', html, re.S)
    return _text(m.group(1)) if m else None


def _chip_row(html: str) -> str:
    i = html.index('<div class="nc-chiprow')
    return html[i:html.index('<span class="hidden sm:inline text-sm text-mut ml-auto', i)]


def _card_section(html: str) -> str:
    """모바일 카드 컨테이너(`lg:hidden divide-y`) — 표(lg+)는 따로 같은 규칙으로 그린다."""
    i = html.index('<div class="lg:hidden divide-y divide-line">')
    return html[i:html.index('<div class="bg-surface border-t border-line px-4 py-3', i)]


# ── A-1. 탭 매크로 data-nav ─────────────────────────────────────────────────────────

def test_data_nav_vehicles_on_sidebar_and_tab_only(client):
    _seed(HYUNDAI_14)
    html = _get(client, "/calendar")
    tagged = re.findall(r'<a href="([^"]+)" data-nav="vehicles"', html)
    assert tagged == ["/vehicles", "/vehicles"], f"사이드바·하단 탭 두 곳, href 는 /vehicles 그대로: {tagged}"
    assert len(re.findall(r"<a [^>]*data-nav=", html)) == 2, "다른 항목(홈·달력·즐겨찾기)엔 붙지 않는다(스크립트·주석의 문자열은 제외)"
    for other in ("/calendar", "/watchlist"):
        assert not re.search(rf'<a href="{other}" data-nav', html)


def test_tab_return_script_and_ttl_constant_present(client):
    _seed(HYUNDAI_14)
    html = _get(client, "/vehicles")
    for anchor in ("nc:lastList", "nc:restoreScroll", "NC_LASTLIST_TTL_MS = 30 * 60 * 1000", "data-nav=\"vehicles\"]"):
        assert anchor in html, anchor
    # 스크롤 복원은 back_forward **또는** 탭 복귀 플래그로 — 예전 조건은 그대로 남아 있다
    assert "isBackForward() || viaTab" in html


def test_active_state_on_detail_kept(client):
    """상세(/vehicle/…)에서 `차량목록` 탭이 활성인 것은 **유지** — 탭이 실제로 '내 목록'으로 가므로 약속이 지켜진다(usedcar 지적 2 의 2안 불필요)."""
    _seed(HYUNDAI_14)
    html = _get(client, "/vehicle/H00")
    tab = re.search(r'<a href="/vehicles" data-nav="vehicles" class="flex-1[^"]*"', html)
    assert tab and "text-primary" in tab.group(0), "하단 탭 차량목록 활성(text-primary) 유지"


# ── A-2. 필터 초기화 칩·조건 요약 줄·큰글씨 접힌 머리 ─────────────────────────────────

EXPECTED_SUMMARY = "현대 · 1,000~2,000만 · 매각기일순 · 2/2페이지"
COMBO = "/vehicles?maker=현대&price=1000-2000&sort=sale_date&page=2"


def test_reset_chip_present_only_with_filters(client):
    _seed(HYUNDAI_14 + OTHERS)
    with_f = _chip_row(_get(client, COMBO))
    assert re.search(r'<a href="/vehicles" class="hidden sm:inline-flex[^"]*"[^>]*>필터 초기화</a>', with_f), \
        "검색 저장 뒤 필터 초기화 칩(sm 이상 노출)"
    assert with_f.index("검색 저장") < with_f.index("필터 초기화") < with_f.index("1,000~2,000만 ✕")
    assert "bg-rose" not in with_f.split("필터 초기화")[0].rsplit("<a", 1)[-1], "경고색 금지(비활성 톤)"
    # base.html 스크립트 주석에도 같은 낱말이 있으므로 **링크 마크업**(>필터 초기화</a>)으로 본다
    plain = _get(client, "/vehicles")
    assert ">필터 초기화</a>" not in plain, "필터 없으면(정렬·페이지만) 칩·링크 둘 다 없다"
    sort_only = _get(client, "/vehicles?sort=sale_date&page=2")
    assert ">필터 초기화</a>" not in sort_only, "정렬·페이지만 바뀐 것은 활성 조건이 아니다"


def test_condition_summary_line_exact_and_absent_by_default(client):
    _seed(HYUNDAI_14 + OTHERS)
    html = _get(client, COMBO)
    ctx = _ctx(client, COMBO)
    assert ctx["total"] == 15 and ctx["total_pages"] == 2, "픽스처 전제(공허 통과 방지) — 현대 14 + 그랜저(과거 기일, 현대) 1"
    assert _cond_summary(html) == EXPECTED_SUMMARY + " · 필터 초기화", "요약 + (sm 미만용) 필터 초기화 링크"
    # 링크는 sm 미만 전용이고 정렬까지 초기화(/vehicles) — UX-7 판정
    assert re.search(r'<a href="/vehicles" class="sm:hidden[^"]*"[^>]*>필터 초기화</a>', html)
    assert _cond_summary(_get(client, "/vehicles")) is None, "기본 상태(필터 없음·recent·1페이지)는 줄을 그리지 않는다 — 16행 2페이지여도 1페이지면 없다"
    assert _cond_summary(_get(client, "/vehicles?page=2")) == "2/2페이지", "페이지 위치는 2페이지부터"
    # 요약은 '판정 표시 설명' 줄 **위**에 있다
    assert html.index('id="condSummary"') < html.index("판정 표시 설명")


@pytest.mark.parametrize("url,expected", [
    ("/vehicles?q=쏘나타&segment=sedan", "“쏘나타” · 세단"),                    # 쏘나타 14(세단) → 2페이지지만 1페이지는 위치를 안 적는다
    ("/vehicles?q=쏘나타&segment=sedan&page=2", "“쏘나타” · 세단 · 2/2페이지"),
    ("/vehicles?date=2026-09-01&sort=sale_date", "2026-09-01 매각 · 매각기일순"),   # 3차(디자인 지적 1): 칩과 같은 ISO — 예전 `9/1 매각`
    ("/vehicles?court=수원지방법원,인천지방법원&upcoming=30", "입찰예정 30일 · 법원 2곳"),   # 수원 14 + 인천 1 = 15
    ("/vehicles?judgment=유찰 대기&cond=insp_expired", "유찰 대기 · 검사 경과"),
    ("/vehicles?maker=기아", "기아"),
    ("/vehicles?sort=mileage", "짧은 주행거리순"),
])
def test_condition_summary_parts_use_existing_labels(client, url, expected):
    _seed(HYUNDAI_14 + OTHERS)
    got = _cond_summary(_get(client, url))
    assert got is not None
    assert got.replace(" · 필터 초기화", "") == expected, got


def test_large_text_collapsed_header_reuses_same_summary(client):
    _seed(HYUNDAI_14 + OTHERS)
    html = _get(client, COMBO)
    summ = re.search(r'<details id="listFilter"[^>]*>\s*<summary[^>]*>(.*?)</summary>', html, re.S).group(1)
    # 3차(디자인 지적 3): 글자 단위 truncate 가 숫자 가운데를 잘라 **부품 단위**(첫 부품 + 외 N)로 — 전문은 title·요약 줄이 맡는다
    assert "— 현대 외 3" in _text(summ) and EXPECTED_SUMMARY not in _text(summ), _text(summ)
    assert 'title="' + EXPECTED_SUMMARY + '"' in summ, "전문은 title"
    # 기본 상태에서는 접힌 머리에 '—' 요약이 없다
    plain = re.search(r'<details id="listFilter"[^>]*>\s*<summary[^>]*>(.*?)</summary>', _get(client, "/vehicles"), re.S).group(1)
    assert "—" not in _text(plain)


def test_sort_labels_single_source_for_select_and_summary(client):
    _seed(HYUNDAI_14)
    assert "{% set sort_labels = {" in LIST_TPL and LIST_TPL.count("sort_labels") >= 3, "셀렉트·요약 줄이 한 dict 를 쓴다"
    assert "<option value=\"sale_date\" {% if sort=='sale_date' %}" not in LIST_TPL, "옵션 문구를 손으로 다시 적지 않는다"
    html = _get(client, "/vehicles?sort=fail_count&maker=현대")
    opt = re.search(r'<option value="fail_count" selected>([^<]+)</option>', html).group(1)
    assert opt == "유찰 많은순" and _cond_summary(html).startswith("현대 · 유찰 많은순")


# ── A-3. 검색어 칩·type=search·칩 ✕ 링크·아이콘·nowrap·셀렉트 title ─────────────────────

def test_search_chip_and_search_input(client):
    _seed(HYUNDAI_14 + OTHERS)
    url = "/vehicles?q=쏘나타&maker=현대&sort=sale_date"
    html, ctx = _get(client, url), _ctx(client, url)
    row = _chip_row(html)
    m = re.search(r'<a href="([^"]+)" class="[^"]*whitespace-nowrap shrink-0" title="검색어 해제">(.*?)</a>', row, re.S)
    assert m, "검색어 활성 칩"
    href = html_mod.unescape(m.group(1))          # 속성값의 & 는 &amp; 로 이스케이프된다(정상)
    assert href == "/vehicles?" + ctx["qs_no_q"] and "q=" not in href
    assert "maker=" in href and "sort=sale_date" in href, "그 조건만 푼다"
    assert _text(m.group(2)) == "“쏘나타” ✕"
    assert re.search(r'<input type="search" name="q" value="쏘나타"', html)
    assert "검색어 해제" not in _get(client, "/vehicles?maker=현대"), "q 없으면 칩 없음"


@pytest.mark.parametrize("url,key,title", [
    ("/vehicles?date=2026-09-01&maker=현대&sort=sale_date", "date", "날짜 필터 해제"),
    ("/vehicles?result=낙찰&maker=현대&sort=sale_date", "result", "결과 필터 해제"),
    ("/vehicles?court=수원지방법원&maker=현대&sort=sale_date", "court", "법원 필터 해제"),
    ("/vehicles?court=수원지방법원,인천지방법원&maker=현대", "court", "법원 필터 해제"),
])
def test_date_result_court_chip_x_drops_only_that_key(client, url, key, title):
    _seed(HYUNDAI_14 + OTHERS)
    html, ctx = _get(client, url), _ctx(client, url)
    m = re.search(rf'<a href="([^"]+)" class="[^"]*"(?: title="{title}")?[^>]*title="{title}"', html) or \
        re.search(rf'<a href="([^"]+)"[^>]*title="{title}"', html)
    assert m, f"{key} 칩"
    href = html_mod.unescape(m.group(1))
    assert href == "/vehicles?" + ctx[f"qs_no_{key}"], (href, ctx[f"qs_no_{key}"])
    assert f"{key}=" not in href and "maker=" in href, "그 키만 빠지고 나머지는 유지"
    assert not href.startswith("/courts"), "법원 칩 ✕ 는 /courts 로 이탈하지 않는다"


def test_court_usepick_picks_chips_have_no_icon_and_promising_nowrap(client):
    _seed(HYUNDAI_14 + OTHERS)
    court = re.search(r'<a href="[^"]+"[^>]*title="법원 필터 해제">(.*?)</a>', _get(client, "/vehicles?court=수원지방법원"), re.S).group(1)
    assert "gavel" not in court and "material-symbols" not in court
    assert "법원 선택으로" not in LIST_TPL and "/courts" not in _chip_row(_get(client, "/vehicles?court=수원지방법원"))
    for u, ttl in (("/vehicles?usepick=1", "실사용 추천 해제"), ("/vehicles?picks=1", "유망 물건 해제")):
        html = _get(client, u)
        m = re.search(rf'<a href="/vehicles"[^>]*title="{ttl}">(.*?)</a>', html, re.S)
        if m:   # 픽스처에서 추천 0건이면 칩이 없을 수 있다(total 0 이어도 칩은 그려지므로 보통 있다)
            assert "material-symbols" not in m.group(1), f"{ttl} 칩 아이콘 제거(높이 34→26)"
    pm = re.search(r'<a href="/vehicles\?judgment=입찰 검토 가능&sort=expected" class="([^"]*)"', _get(client, "/vehicles?promising=1"))
    assert pm and "whitespace-nowrap" in pm.group(1) and "shrink-0" in pm.group(1) and "inline-flex" in pm.group(1)


def test_price_select_title_and_apply_dirty_script(client):
    _seed(HYUNDAI_14)
    html = _get(client, "/vehicles")
    assert 'name="price" aria-label="가격대 필터 (최저매각가 기준)" class="inp py-1.5 min-w-0 col-span-2" title="괄호 건수는 현재 적용된 조건 기준"' in html
    assert "#listFilter form" in html and "is-dirty" in html, "[적용] 변경 표시 스크립트"
    css = (ROOT / "web/static/tailwind_input.css").read_text(encoding="utf-8")
    assert ".btn-ghost.is-dirty { background: #533afd; color: #fff;" in css, "primary 채움(토큰 색)"
    # [적용] 버튼 마크업은 그대로(다른 테스트가 `<button class="…">` 를 정규식으로 잡는다)
    assert html.count('<span class="material-symbols-outlined text-base">filter_list</span> 적용</button>') == 2


# ── A-4. UX-3 구분 줄 ────────────────────────────────────────────────────────────────

def _cards_before_split(section: str):
    if "data-sale-split" not in section:
        return None
    return section[:section.index("data-sale-split")].count('<a href="/vehicle/')


def test_split_line_before_first_past_card_on_boundary_page(client):
    _seed(SPLIT_3_3)
    html = _get(client, "/vehicles?sort=sale_date")
    assert _ctx(client, "/vehicles?sort=sale_date")["sale_split"]["page_first_past_idx"] == 3
    sec = _card_section(html)
    assert _cards_before_split(sec) == 3, "미래 3장 뒤·첫 지난 기일 카드 앞"
    assert sec.count("data-sale-split") == 1, "한 페이지에 한 번만"
    assert "지난 기일 <b class=\"text-txt tnum\">3</b>건 — 낙찰은 결과 참고 · 유찰은 다음 기일 대기" in sec   # 3차(디자인 지적 2): '참고'는 낙찰에만
    # 표(lg+)에도 같은 줄 — <tr colspan=9>
    assert re.search(r'<tr data-sale-split class="bg-background"><td colspan="9"[^>]*>지난 기일 <b class="text-txt tnum">3</b>건', html)


def test_split_line_only_on_boundary_page(client):
    _seed(SPLIT_12_3)
    p1 = _get(client, "/vehicles?sort=sale_date")
    assert "data-sale-split" not in p1, "경계가 2페이지면 1페이지엔 없다"
    p2 = _get(client, "/vehicles?sort=sale_date&page=2")
    assert _cards_before_split(_card_section(p2)) == 0, "2페이지 첫 카드 위"


def test_split_line_top_when_only_past(client):
    _seed(PAST_ONLY)
    html = _get(client, "/vehicles?sort=sale_date")
    assert _cards_before_split(_card_section(html)) == 0, "예정 기일 없음 → 목록 맨 위"
    assert "data-sale-split" not in _get(client, "/vehicles?sort=recent"), "다른 정렬엔 없다"


def test_split_line_on_segment_path_too(client):
    """지시서 D-8: segment·bucket(순서 보존)도 계산 — app.py 조건 한 줄."""
    _seed(SPLIT_3_3)
    assert _cards_before_split(_card_section(_get(client, "/vehicles?sort=sale_date&segment=sedan"))) == 3
    assert "data-sale-split" not in _get(client, "/vehicles?sort=sale_date&picks=1")


# ── A-5. 상세 ← · frame.html ─────────────────────────────────────────────────────────

def test_detail_back_button_labelled(client):
    _seed(HYUNDAI_14)
    html = _get(client, "/vehicle/H00")
    m = re.search(r'<a href="[^"]*" onclick="return _goBack\(event\)" aria-label="목록으로" title="목록으로"\s+class="([^"]*)"[^>]*>(.*?)</a>', html, re.S)
    assert m, "← 버튼"
    assert _text(m.group(2)) == "arrow_back 목록으로"
    assert "width:2.75rem" not in m.group(0), "고정 폭 해제 — 내용 폭"
    assert 'aria-label="뒤로"' not in html


def test_frame_updates_outer_hash_on_iframe_load():
    assert 'addEventListener("load"' in FRAME and "history.replaceState(null, \"\", \"#\" + np)" in FRAME
    assert 'np.startsWith("//")' in FRAME, "내부 경로만"
    assert 'document.getElementById("f").src = p;' in FRAME, "초기 로드 로직 무변경"


# ═══════════════════════════════════ B. 동작(Playwright) ═══════════════════════════════════

def _free_port() -> int:
    for _ in range(20):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


@pytest.fixture(scope="module")
def server():
    """같은 프로세스의 스레드 uvicorn — db.DB_PATH 는 요청 시점에 읽으므로 테스트별 tmp DB(conftest) 를 그대로 본다."""
    uvicorn = pytest.importorskip("uvicorn")
    import web.app as A
    port = _free_port()
    cfg = uvicorn.Config(A.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    srv = uvicorn.Server(cfg)
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "uvicorn 기동 실패"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:      # 브라우저 미설치
            pytest.skip(f"chromium 없음: {e}")
        yield b
        b.close()


def _phone(browser, **kw):
    return browser.new_context(viewport={"width": 390, "height": 640}, device_scale_factor=1, locale="ko-KR", has_touch=True, **kw)


LIST_URL = "/vehicles?maker=" + quote("현대") + "&price=1000-2000&sort=sale_date&page=2"
# 하단 탭 바(모바일, `nav.lg:hidden`). 사이드바의 같은 항목은 폰 폭에서 화면 밖(off-canvas)에 렌더돼 있어 `:visible` 로도 잡힌다 —
# 그걸 누르면 "element is outside of the viewport" 로 실패한다(실측). 탭 바를 지목한다.
TAB_LIST = 'nav[class~="lg:hidden"] a[data-nav="vehicles"]'
TAB_CAL = 'nav[class~="lg:hidden"] a[href="/calendar"]'


def _path_qs(url: str) -> str:
    from urllib.parse import urlsplit
    u = urlsplit(url)
    return u.path + ("?" + u.query if u.query else "")


def test_b1_tab_returns_to_last_list_with_filters_page_and_scroll(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    ctx = _phone(browser); pg = ctx.new_page()
    pg.goto(server + LIST_URL, wait_until="networkidle")
    assert pg.eval_on_selector("select[name=maker]", "e => e.value") == "현대"
    assert pg.evaluate("() => { const e=document.getElementById('appscroll'); return e.scrollHeight > e.clientHeight; }"), "스크롤 여지(픽스처 전제)"
    pg.evaluate("() => document.getElementById('appscroll').scrollTop = 300")
    assert pg.evaluate("() => document.getElementById('appscroll').scrollTop") >= 250
    pg.click(TAB_CAL); pg.wait_for_url(lambda u: "/calendar" in u)
    pg.click(TAB_LIST); pg.wait_for_url(lambda u: "page=2" in u)
    assert _path_qs(pg.url) == LIST_URL
    assert pg.eval_on_selector("select[name=maker]", "e => e.value") == "현대"
    assert pg.eval_on_selector("select[name=price]", "e => e.value") == "1000-2000"
    assert pg.eval_on_selector("select[name=sort]", "e => e.value") == "sale_date"
    assert re.search(r"13[–-]15", pg.inner_text("#listResults")), "2페이지(13–15 / 총 15건)"
    pg.wait_for_function("() => document.getElementById('appscroll').scrollTop >= 250", timeout=3000)
    assert pg.evaluate("() => sessionStorage.getItem('nc:restoreScroll')") is None, "플래그는 한 번 쓰고 지운다"
    ctx.close()


def test_b2_retap_on_list_scrolls_to_top_and_keeps_url(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    ctx = _phone(browser, reduced_motion="reduce"); pg = ctx.new_page()
    pg.goto(server + LIST_URL, wait_until="networkidle")
    pg.evaluate("() => document.getElementById('appscroll').scrollTop = 300")
    pg.click(TAB_LIST); pg.wait_for_timeout(400)
    assert _path_qs(pg.url) == LIST_URL, "URL 불변(이동 없음)"
    pg.wait_for_function("() => document.getElementById('appscroll').scrollTop === 0", timeout=3000)
    ctx.close()


def test_b3_detail_then_tab_returns_to_last_list(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    ctx = _phone(browser); pg = ctx.new_page()
    pg.goto(server + LIST_URL, wait_until="networkidle")
    pg.click('#listResults a[href^="/vehicle/"]:visible'); pg.wait_for_url(lambda u: "/vehicle/" in u)
    pg.click(TAB_LIST); pg.wait_for_url(lambda u: "page=2" in u)
    assert _path_qs(pg.url) == LIST_URL
    ctx.close()


def test_b4_ttl_expired_falls_back_to_plain_list(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    ctx = _phone(browser); pg = ctx.new_page()
    pg.goto(server + LIST_URL, wait_until="networkidle")
    pg.click(TAB_CAL); pg.wait_for_url(lambda u: "/calendar" in u)
    # 목록을 떠난 뒤(pagehide 갱신 뒤)에 31분 전으로 조작해야 한다 — 목록 페이지에서 고치면 떠날 때 다시 덧쓴다
    pg.evaluate("() => { const o = JSON.parse(sessionStorage.getItem('nc:lastList')); o.ts = Date.now() - 31*60*1000; sessionStorage.setItem('nc:lastList', JSON.stringify(o)); }")
    pg.click(TAB_LIST); pg.wait_for_url(lambda u: u.endswith("/vehicles"))
    assert _path_qs(pg.url) == "/vehicles", "만료 → 기본 href"
    ctx.close()


def test_b5_pc_frame_hash_follows_iframe_and_survives_reload(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    # loopback 은 관리자라 자동 프레임 리다이렉트가 꺼진다 → 프레임 페이지를 직접 연다(해시 = 내부 경로)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ko-KR"); pg = ctx.new_page()
    pg.goto(server + "/static/frame.html#/vehicles?maker=" + quote("현대") + "&price=1000-2000", wait_until="networkidle")
    fr = next(f for f in pg.frames if f != pg.main_frame)
    fr.wait_for_selector('a[href*="page=2"]')
    fr.click('a[href*="page=2"]')
    pg.wait_for_function("() => location.hash.includes('page=2')", timeout=5000)
    assert "page=2" in pg.evaluate("location.hash") and pg.evaluate("location.hash").startswith("#/vehicles")
    pg.reload(wait_until="networkidle")
    fr2 = next(f for f in pg.frames if f != pg.main_frame)
    fr2.wait_for_selector("#listResults")
    assert "page=2" in fr2.url and "price=1000-2000" in fr2.url, "F5 후 마지막 경로로 다시 열린다"
    ctx.close()


def test_b6_large_text_collapsed_header_shows_summary(server, browser):
    _seed(HYUNDAI_14 + OTHERS)
    ctx = _phone(browser); ctx.add_init_script("try{localStorage.setItem('naechaget:large','1')}catch(e){}")
    pg = ctx.new_page(); pg.goto(server + LIST_URL, wait_until="networkidle")
    assert pg.evaluate("() => document.documentElement.classList.contains('nc-large')")
    assert pg.evaluate("() => document.getElementById('listFilter').open") is False
    s = pg.locator("#listFilter > summary")
    assert s.is_visible()
    assert "— 현대 외 3" in re.sub(r"\s+", " ", s.inner_text())          # 3차: 부품 단위(첫 부품 + 외 N)
    assert s.locator("span[title]").get_attribute("title") == EXPECTED_SUMMARY, "전문은 title"
    box = s.bounding_box()
    assert box and box["height"] < 48, f"한 줄(말줄임)이어야 한다: {box}"
    ctx.close()
