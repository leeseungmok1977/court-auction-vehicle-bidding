"""UX-8 결과 화면 필터 카드 접기 — 화면 회귀 (지시서 2026-09-27-06, 오너 승인 2026-09-27).

배경: FEAT-2 로 셀렉트가 여섯이 되어 폰 필터 카드 하단이 329→417(+88px) — 조건을 건 결과 화면에서 첫 매물 카드가 더 내려갔다.
디자인 검수(reports/2026-09-27-feat2-design.md 고칠 것 2·Q1) 처방: has_filter 인 결과 화면에서는 `#listFilter` 를 접어
`검색 · 필터 — {첫 부품} 외 N` 머리만 보이고, 첫 진입(조건 없음)은 편다.

Steward 원칙(지시서): ① 서버가 기본 상태를 정한다(has_filter → open 없이) ② 좁은 폭(< 640)만 접는다 — 넓은 폭은 인라인 스크립트가
첫 페인트 전에 연다(렌더 무변경) ③ summary 는 has_filter 일 때 일반 모드에서도 보인다 ④ 펼친 선택은 같은 필터 조합(page 제외) 안에서
기억 ⑤ 칩 ✕ 손실 — (a) 칩은 카드 안 / (b) 접혔을 때만 해제 칩 한 줄을 카드 밖에(매크로 하나) → 측정으로 (b) 채택(보고서 비교표)
⑥ UX-5 요약 줄·FEAT-1/2 셀렉트·UX-1 hidden·UX-3 구분 줄·검색 저장 동작 무변경.

r2(지시서 2026-09-27-09 — qa reports/2026-09-27-ux8-qa.md · 디자인 검수 UX-8):
  B-1 기억 키에서 기본 정렬(sort=recent)을 뺀다 — 정렬 없는 홈 진입 링크에서 펼친 뒤 2페이지·무변경 [적용]이 다시 접히던 것.
  B-2 여닫기 결정을 details **앞** 스크립트의 MutationObserver 로 — 자리(`</details>` 뒤·`</summary>` 뒤·details 첫 자식)로는 파서가 그 스크립트
      직전에 양보할 때 닫힌 카드가 그려졌다(CPU 4x 측정 — r2 보고서). 관찰 콜백은 마이크로태스크라 렌더링 전에 돈다.
  디자인 고칠 것 1: 펼치면 셰브런이 뒤집히고(group-open:rotate-180, motion-safe) 펼친 머리의 부제는 숨는다. #listLegend 셰브런도 같은 규칙.
  qa 접근성(낮음): 머리의 두 아이콘(리거처 글자)은 aria-hidden — 접근 이름이 `filter_list 검색 · 필터 … expand_more` 로 읽혔다.

두 층:
  A. 템플릿(TestClient, 렌더 HTML·소스의 **앵커 문자열**만 — 줄 번호·오프셋 창 금지). TestClient 의 host 는 `testserver` → 공개 뷰.
  B. 동작(Playwright Chromium, 같은 프로세스의 스레드 uvicorn — 임시 DB). 폰 폭은 is_mobile·has_touch. 서버는 127.0.0.1 이라
     관리자 뷰 = PC 폰 프레임 리다이렉트 없음(1440 은 전체 폭). playwright/브라우저가 없으면 skip.
"""
import re
import socket
import threading
import time
from datetime import date, timedelta
from urllib.parse import quote, urlsplit, parse_qs

import pytest
from starlette.testclient import TestClient

from web import db

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
BASE_TPL = (ROOT / "web/templates/base.html").read_text(encoding="utf-8")
APP_CSS = (ROOT / "web/static/app.css").read_text(encoding="utf-8")
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964, 8996, 8917}

TODAY = date.today()


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# hide_incomplete 를 통과하는 최소 형태(UX-2·FEAT 테스트와 같은 관례). min_sale_price 12,000,000 = 가격대 1000-2000, 연식 2020 ≥ 2018.
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1, "mileage_km": 50_000,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(n=30, extra=()):
    db.init_db()
    rows = [(f"H{i:02d}", "쏘나타(SONATA)", "현대", _d(3 + i), "수원지방법원") for i in range(n)] + list(extra)
    for i, (vid, model, maker, sd, court) in enumerate(rows):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경4{i:04d}", model=model, maker=maker, sale_date=sd, court=court))


COND = "/vehicles?maker=" + quote("현대") + "&price=1000-2000&year_min=2018&sort=sale_date"
DATE = "/vehicles?date=2026-09-01&sort=sale_date"


@pytest.fixture
def client():
    import web.app as A
    return TestClient(A.app)


def _get(client, url: str) -> str:
    r = client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", fragment)).strip()


def _details_tag(h):
    return re.search(r'<details id="listFilter"[^>]*>', h).group(0)


def _summary(h):
    m = re.search(r'<details id="listFilter"[^>]*>\s*<summary class="([^"]*)">(.*?)</summary>', h, re.S)
    return m.group(1), m.group(2)


def _card_row(h):
    """카드 안 칩 행 — 첫 nc-chiprow 부터 폼 끝까지(앵커)."""
    i = h.index('<div class="nc-chiprow')
    return h[i:h.index("</form>", i)]


def _fold_row(h):
    m = re.search(r'<div id="listFilterChips"[^>]*>(.*?)\n</div>', h, re.S)
    return m.group(1) if m else None


def _anchors(fragment):
    return [re.sub(r"\s+", " ", a) for a in re.findall(r"<a\b.*?</a>", fragment, re.S)]


# ═══════════════════════════════════ A. 템플릿 ═══════════════════════════════════

def test_has_filter_renders_closed_with_visible_narrow_summary(client):
    _seed(3)
    h = _get(client, COND)
    tag = _details_tag(h)
    assert not re.search(r"\sopen[\s>]", tag), f"has_filter → open 없이(서버가 기본 상태를 정한다): {tag}"
    assert 'class="group peer ' in tag, "group(히트영역 ::before)·peer(접힌 칩 줄) 표식"
    cls, body = _summary(h)
    assert cls.startswith("hidden max-sm:flex "), f"좁은 폭에서만 보인다(넓은 폭은 전처럼 숨김): {cls}"
    for c in ("before:absolute", "before:-inset-x-3", "before:-top-4", "before:-bottom-3", "group-open:before:bottom-0", "relative"):
        assert c in cls.split(), f"히트영역 클래스 {c}"
    assert "— 현대 외 3" in _text(body), _text(body)                   # 부품 단위(DES-3 처방 그대로) — 현대·가격대·연식·정렬 = 4부품
    assert _text(re.search(r'<span class="min-w-0 truncate[^"]*" title="([^"]*)"', body).group(1)) == "현대 · 1,000~2,000만 · 2018년 이후 · 매각기일순"


def test_no_filter_renders_open_with_hidden_summary_as_before(client):
    _seed(3)
    for url in ("/vehicles", "/vehicles?sort=sale_date", "/vehicles?page=2"):
        h = _get(client, url)
        assert _details_tag(h).startswith('<details id="listFilter" open class='), url
        cls, body = _summary(h)
        assert cls.startswith("hidden cursor-pointer") and "max-sm:flex" not in cls, (url, cls)
        assert _fold_row(h) is None and 'id="listFilterChips"' not in h, url


def test_collapsed_head_parts_for_date_url(client):
    _seed(3)
    cls, body = _summary(_get(client, DATE))
    assert "max-sm:flex" in cls and "— 2026-09-01 매각 외 1" in _text(body)


@pytest.mark.parametrize("url", [
    COND, DATE,
    "/vehicles?upcoming=30&cond=damaged",
    "/vehicles?cond=insp_expired&q=" + quote("쏘나타"),
    "/vehicles?bucket=wait", "/vehicles?usepick=now", "/vehicles?picks=1", "/vehicles?promising=1",
    "/vehicles?result=" + quote("낙찰"), "/vehicles?court=" + quote("수원지방법원,인천지방법원"),
    "/vehicles?maker=" + quote("현대") + "&price=1000-2000&year_min=2018&km_max=100000&page=2",
])
def test_fold_row_is_exactly_the_active_chips_of_the_card_row(client, url):
    """⑤ (b): 접힌 칩 줄 = 카드 안 칩 행의 **해제 ✕ 칩만**(같은 매크로의 두 번째 렌더 — 문자열까지 같다). 검색 저장·비활성 퀵 칩·초기화 칩 없음."""
    _seed(14)
    h = _get(client, url)
    card = _anchors(_card_row(h))
    active = [a for a in card if _text(a).endswith("✕")]
    fold = _fold_row(h)
    assert fold is not None, url
    got = _anchors(fold)
    assert got and got == active, (url, got, active)
    assert "검색 저장" not in fold and "필터 초기화" not in fold and "ncSaveSearch" not in fold
    for quick in ("입찰예정 30일만</a>", ">검사 경과</a>", ">외관 손상</a>"):
        assert quick not in fold, (url, quick)


def test_fold_row_absent_when_no_removable_chip(client):
    """제조사·판정만 건 결과 — 둘은 해제 칩이 없다(요약 줄 '필터 초기화'가 맡는다). 빈 줄을 그리지 않는다."""
    _seed(3)
    for url in ("/vehicles?maker=" + quote("현대"), "/vehicles?judgment=" + quote("유찰 대기"), "/vehicles?segment=sedan"):
        h = _get(client, url)
        assert not re.search(r"\sopen[\s>]", _details_tag(h)), url
        assert 'id="listFilterChips"' not in h, url


def test_fold_row_classes_and_position(client):
    _seed(3)
    h = _get(client, COND)
    row = re.search(r'<div id="listFilterChips" class="([^"]*)"', h).group(1).split()
    for c in ("sm:hidden", "peer-open:hidden", "[.nc-large_&]:hidden", "overflow-x-auto", "flex"):
        assert c in row, c
    # 래퍼 안 순서(r2): 결정 스크립트 → <details …peer> … </details> → 접힌 칩 줄
    # (결정 스크립트는 details **앞** — MutationObserver 로 details 가 DOM 에 들어온 순간 정한다(qa B-2). peer 는 뒤 형제만 본다.
    #  칩 줄은 details 뒤라 파싱될 때 최종 open 이 이미 정해져 있다.)
    k = h.index("nc:listFilterOpen")
    i = h.index('<details id="listFilter"')
    j = h.index("</details>", i)
    m = h.index('<div id="listFilterChips"', j)
    assert k < i < j < m
    w = h.rfind("<div>", 0, k)
    assert w > h.rfind("</div>", 0, k) and h[w:k].count("<script>") == 1 and "</script>" not in h[w:h.index("<script>", w)], \
        "결정 스크립트는 래퍼 div 의 첫 자식(space-y-6 이 칩 줄에 붙지 않게 — 래퍼 유지)"
    assert h[h.index("})();</script>", k) + len("})();</script>"):i].strip() == "", "스크립트와 details 사이에 다른 요소 없음"


def test_chip_markup_single_source_macro(client):
    """두 벌을 손으로 적지 않는다 — 매크로 하나, 호출 둘. 칩 title 은 소스에 한 번씩."""
    assert LIST_TPL.count("{% macro filter_chips(with_quick) %}") == 1
    assert LIST_TPL.count("{{ filter_chips(true) }}") == 1, "카드 안 칩 행(비활성 퀵 칩 포함)"
    assert LIST_TPL.count("{% set _fold_chips = filter_chips(false)|trim %}") == 1, "접힌 칩 줄(해제 ✕ 만)"
    for t in ("가격대 필터 해제", "연식 필터 해제", "주행거리 필터 해제", "날짜 필터 해제", "법원 필터 해제", "검색어 해제", "결과 필터 해제"):
        assert LIST_TPL.count(f'title="{t}"') == 1, t
    assert LIST_TPL.count("{% elif with_quick %}") == 3, "비활성 퀵 칩 셋(입찰예정 30일만·검사 경과·외관 손상)만 with_quick"


def test_inline_script_rules_and_order_before_scroll_restore(client):
    _seed(3)
    h = _get(client, COND)
    s = h[h.index("getElementById('listFilter')"):h.index("})();</script>", h.index("getElementById('listFilter')"))]
    assert "matchMedia('(min-width:640px)')" in s, "넓은 폭(sm 이상)은 연다"
    assert "k!=='page'" in s and "v!==''" in s and ".sort()" in s, "기억 키 = page·빈 값 뺀 쿼리, 키 정렬"
    assert "!(k==='sort' && v==='recent')" in s, "기억 키에서 기본 정렬을 뺀다(qa B-1 — 서버 링크·폼은 sort=recent 를 싣고 홈 진입 링크는 안 싣는다)"
    assert "d.addEventListener('click'" in s and "closest('summary')" in s and "s.parentNode===d" in s and "if(!user) return" in s, \
        "사용자가 (이 카드의) summary 를 눌렀을 때만 기억 — 결정 시점엔 summary 가 아직 없어 details 에 위임"
    assert "addEventListener('change'" in s, "폭 변화(회전) 시 넓어지면 연다"
    assert "new MutationObserver(" in s and "mo.disconnect()" in s and "addEventListener('DOMContentLoaded', run)" in s, \
        "details 가 DOM 에 들어온 순간 정한다(qa B-2) · MutationObserver 없으면 DOMContentLoaded"
    assert h.index("nc:listFilterOpen") < h.index('<details id="listFilter"'), "결정 스크립트는 details 앞"
    assert h.index("nc:listFilterOpen") < h.index("function restore()"), "스크롤 복원보다 먼저 최종 open 을 정한다"


def test_chevron_flips_and_expanded_head_drops_subtitle(client):
    """디자인 검수 UX-8 고칠 것 1: 펼친 상태가 모양으로 읽히게 — 셰브런 180° (detail·dashboard 의 group-open:rotate-90 과 같은 규칙,
    모션 줄이기면 전환 없이). 펼친 머리의 부제는 숨긴다(바로 아래 셀렉트가 같은 값). 아이콘 리거처 글자는 접근 이름에서 뺀다(qa)."""
    _seed(3)
    cls, body = _summary(_get(client, COND))
    icons = re.findall(r'<span class="material-symbols-outlined([^"]*)"([^>]*)>(\w+)</span>', body)
    assert [i[2] for i in icons] == ["filter_list", "expand_more"], icons
    assert all('aria-hidden="true"' in i[1] for i in icons), icons
    chev = icons[1][0].split()
    for c in ("group-open:rotate-180", "motion-safe:transition-transform", "motion-safe:ease-[var(--ease-out)]"):
        assert c in chev, c
    assert "transition-transform" not in chev and "transition" not in chev, "전환은 motion-safe 에서만"
    sub = re.search(r'<span class="(min-w-0 truncate[^"]*)" title=', body).group(1).split()
    assert "group-open:hidden" in sub, sub
    leg = re.search(r'<details id="listLegend" class="([^"]*)">\s*<summary[^>]*>\s*<span class="material-symbols-outlined([^"]*)">expand_more</span>',
                    _get(client, COND))
    assert leg and "group" in leg.group(1).split(), "범례 details 가 group"
    for c in ("group-open:rotate-180", "motion-safe:transition-transform", "motion-safe:ease-[var(--ease-out)]"):
        assert c in leg.group(2).split(), c


def test_css_rules_built():
    for rule in (r".max-sm\:flex{display:flex}", r".peer[open]~.peer-open\:hidden{display:none}",
                 r".nc-large .\[\.nc-large_\&\]\:hidden{display:none}", r".group[open] .group-open\:before\:bottom-0:before",
                 r".before\:-top-4:before", r".before\:-bottom-3:before", r".before\:-inset-x-3:before"):
        assert rule in APP_CSS, f"app.css 재빌드 누락: {rule}"
    assert "@media not all and (min-width:640px){.max-sm\\:flex{display:flex}}" in APP_CSS, "max-sm = sm(640) 미만"
    # r2 — 셰브런 회전·펼친 머리 부제 숨김·모션(ease-out 토큰, 모션 줄이기 존중)
    for rule in (r".group[open] .group-open\:rotate-180{--tw-rotate:180deg}", r".group[open] .group-open\:hidden{display:none}",
                 r".motion-safe\:ease-\[var\(--ease-out\)\]{transition-timing-function:var(--ease-out)}"):
        assert rule in APP_CSS, f"app.css 재빌드 누락: {rule}"
    mq = APP_CSS[APP_CSS.index("@media (prefers-reduced-motion:no-preference){"):]
    mq = mq[:mq.index("}}") + 2]
    assert r".motion-safe\:transition-transform{transition-property:transform" in mq and r".motion-safe\:ease-\[var\(--ease-out\)\]" in mq, mq


# ═══════════════════════════════════ B. 동작(Playwright) ═══════════════════════════════════

def _free_port() -> int:
    for _ in range(20):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


@pytest.fixture(scope="module")
def server():
    uvicorn = pytest.importorskip("uvicorn")
    import web.app as A
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(A.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
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


NO_SPLASH = "try{sessionStorage.setItem('nc_splash','1')}catch(e){}"
# 첫 페인트 기록: 문서 스크립트보다 먼저 도는 init script 가 매 프레임(rAF = 페인트 직전) #listFilter.open 을 적는다.
FRAME_LOG = """
window.__ncFrames = []; window.__ncDCL = null;
(function tick(){ var d = document.getElementById('listFilter'); if (d) window.__ncFrames.push(d.open);
  if (window.__ncFrames.length < 240) requestAnimationFrame(tick); })();
document.addEventListener('DOMContentLoaded', function(){ var d = document.getElementById('listFilter'); window.__ncDCL = d ? d.open : null; });
"""
STATE = """() => {
  const d = document.getElementById('listFilter'), s = d.querySelector('summary'), row = document.getElementById('listFilterChips');
  const vis = e => !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0;
  const card = [...document.querySelectorAll('#listResults a[href^="/vehicle/"]')].find(a => a.getBoundingClientRect().height > 0);
  const sb = s.getBoundingClientRect();
  return {open: d.open, summary: vis(s), row: vis(row), sumTop: sb.top, sumBottom: sb.bottom, sumH: sb.height,
          cardTop: card ? card.getBoundingClientRect().top : null, hscroll: document.documentElement.scrollWidth > innerWidth,
          mem: sessionStorage.getItem('nc:listFilterOpen'), large: document.documentElement.classList.contains('nc-large'),
          head: (s.querySelector('span.truncate') || {}).textContent || null};
}"""
PHONES = [320, 360, 390, 430]
TAB_LIST = 'nav[class~="lg:hidden"] a[data-nav="vehicles"]'
TAB_CAL = 'nav[class~="lg:hidden"] a[href="/calendar"]'


def _phone(browser, w=390, h=844, large=False, frames=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ko-KR", is_mobile=True, has_touch=True)
    ctx.add_init_script(NO_SPLASH)
    if large:
        ctx.add_init_script("try{localStorage.setItem('naechaget:large','1')}catch(e){}")
    if frames:
        ctx.add_init_script(FRAME_LOG)
    return ctx


def _desk(browser, w, h=900, frames=False):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ko-KR")
    ctx.add_init_script(NO_SPLASH)
    if frames:
        ctx.add_init_script(FRAME_LOG)
    return ctx


def _st(pg):
    return pg.evaluate(STATE)


def _path_qs(url: str) -> str:
    u = urlsplit(url)
    return u.path + ("?" + u.query if u.query else "")


def _qs(url):
    return {k: v for k, v in parse_qs(urlsplit(url).query).items()}


@pytest.mark.parametrize("w", PHONES)
def test_p1_phone_folds_gain_toggle_and_hit_area(server, browser, w):
    """⑴ 첫 카드가 얼마나 올라왔나(펼친 상태 대비) ⑵ 탭 → 펼침 → 탭 → 접힘 · 접힌 칩 줄은 접혔을 때만 · 히트영역 ≥ 40 · 가로 스크롤 없음."""
    _seed(30)
    ctx = _phone(browser, w); pg = ctx.new_page()
    pg.goto(server + COND, wait_until="networkidle")
    a = _st(pg)
    assert a["open"] is False and a["summary"] and a["row"] and not a["hscroll"], a
    assert a["head"] and "— 현대 외 3" in a["head"], a["head"]
    # 320 에서도 접힌 칩 줄의 첫 해제 ✕ 가 페이드(줄 우변 − 16) 앞(UX-4 규칙)
    fx = pg.evaluate("""() => { const r = document.getElementById('listFilterChips'), rr = r.getBoundingClientRect();
        const c = [...r.querySelectorAll('a')].find(x => x.textContent.trim().endsWith('✕')); const cr = c.getBoundingClientRect();
        return {right: cr.right, fade: rr.right - 16, h: cr.height}; }""")
    assert fx["right"] <= fx["fade"] and fx["h"] <= 28, fx
    # 히트영역: 접힘 — 글자 줄 위 12px·아래 10px 도 summary
    hit = lambda y: pg.evaluate("(y) => { const s = document.querySelector('#listFilter > summary'); const e = document.elementFromPoint(innerWidth / 2, y); return !!e && s.contains(e); }", y)  # noqa: E731
    assert hit(a["sumTop"] - 12) and hit(a["sumBottom"] + 10), "접힌 카드 여백까지 summary"
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    b = _st(pg)
    assert b["open"] is True and b["summary"] and not b["row"], b
    assert hit(b["sumTop"] - 12) and not hit(b["sumBottom"] + 4), "펼침: 위로는 넓고 아래 셀렉트는 뺏지 않는다"
    hit_h = lambda: pg.evaluate("""() => { const s = document.querySelector('#listFilter > summary'), b = s.getBoundingClientRect(), p = getComputedStyle(s, '::before');
        return (b.bottom - parseFloat(p.bottom)) - (b.top + parseFloat(p.top)); }""")  # noqa: E731
    assert hit_h() >= 40, f"펼침 히트영역 {hit_h()}px(위 16 + 글자 줄)"
    gain = b["cardTop"] - a["cardTop"]
    before_head = b["cardTop"] - b["sumH"]           # HEAD(요약 머리 없이 펼친 카드) 기준 첫 카드 top
    assert gain >= 200, f"{w}px 첫 카드 top 접힘 {a['cardTop']} / 펼침 {b['cardTop']} (이득 {gain}, HEAD 대비 {before_head - a['cardTop']})"
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    c = _st(pg)
    assert c["open"] is False and c["row"] and c["cardTop"] == a["cardTop"], c
    ctx.close()


def test_p3_memory_same_combo_pages_back_and_new_combo_folds(server, browser):
    """④ 펼친 선택은 같은 조합(page 제외) 안에서 — 다음 페이지·뒤로가기는 펼친 채, [적용](조합 변경)·칩 ✕ 뒤에는 다시 접힘."""
    _seed(30)
    ctx = _phone(browser, 390); pg = ctx.new_page()
    pg.goto(server + COND, wait_until="networkidle")
    assert _st(pg)["open"] is False
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    assert _st(pg)["open"] is True and _st(pg)["mem"]
    pg.click('#listResults a[href*="page=2"]:visible'); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("networkidle")
    s2 = _st(pg)
    assert s2["open"] is True and not s2["row"], "같은 조합 2페이지 → 펼친 채"
    pg.go_back(); pg.wait_for_url(lambda u: "page=2" not in u); pg.wait_for_load_state("networkidle")
    assert _st(pg)["open"] is True, "뒤로가기 → 펼친 채"
    # [적용] — 정렬을 바꾸면 새 조합(새 결과 화면) → 접힘
    pg.select_option("#listFilter select[name=sort]", "mileage")
    pg.locator("#listFilter form button.btn-ghost:not([type]):visible").click()
    pg.wait_for_url(lambda u: "sort=mileage" in u); pg.wait_for_load_state("networkidle")
    s3 = _st(pg)
    assert s3["open"] is False and s3["row"], "[적용]으로 조합이 바뀌면 다시 접힘"
    # 같은 조합의 [적용](값 그대로) — 폼 제출 URL(빈 값 포함)과 링크 URL 이 같은 키 → 펼친 채 기억 유지
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    pg.locator("#listFilter form button.btn-ghost:not([type]):visible").click(); pg.wait_for_load_state("networkidle")
    assert "judgment=" in pg.url and _st(pg)["open"] is True, ("빈 값이 실린 제출 URL 도 같은 조합", pg.url)
    # 칩 ✕(카드 안, 펼친 상태) → 조합이 바뀌어 접힘
    pg.click('#listFilter a[title="연식 필터 해제"]'); pg.wait_for_url(lambda u: "year_min" not in u); pg.wait_for_load_state("networkidle")
    s4 = _st(pg)
    assert s4["open"] is False and "maker" in _qs(pg.url) and "price" in _qs(pg.url), s4
    ctx.close()


def test_p3b_folded_row_chip_is_one_tap_and_drops_only_its_key(server, browser):
    """⑤ (b) 의 목적 — 접힌 채로 조건 하나만 빼기가 한 번 탭(UX-1)."""
    _seed(30)
    ctx = _phone(browser, 320); pg = ctx.new_page()
    pg.goto(server + COND, wait_until="networkidle")
    assert _st(pg)["open"] is False
    pg.locator('#listFilterChips a[title="가격대 필터 해제"]').tap()
    pg.wait_for_url(lambda u: "price=" not in u); pg.wait_for_load_state("networkidle")
    q = _qs(pg.url)
    assert "price" not in q and q.get("maker") == ["현대"] and q.get("year_min") == ["2018"] and q.get("sort") == ["sale_date"], q
    s = _st(pg)
    assert s["open"] is False and s["row"], "아직 조건이 있는 결과 화면 → 접힌 채"
    ctx.close()


@pytest.mark.parametrize("expand", [False, True])
def test_p4_tab_return_keeps_url_scroll_and_fold_state(server, browser, expand):
    """⑷ UX-2 탭 복귀: 필터 + 2페이지 + 스크롤 → 달력 → 차량목록 탭 → URL·scrollTop 동일(접힌 채/펼친 채)."""
    _seed(30)
    url = COND + "&page=2"
    ctx = _phone(browser, 390, 640); pg = ctx.new_page()
    pg.goto(server + url, wait_until="networkidle")
    if expand:
        pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    assert _st(pg)["open"] is expand
    assert pg.evaluate("() => { const e=document.getElementById('appscroll'); return e.scrollHeight - e.clientHeight; }") > 400, "스크롤 여지(픽스처 전제)"
    pg.evaluate("() => document.getElementById('appscroll').scrollTop = 400")
    y0 = pg.evaluate("() => document.getElementById('appscroll').scrollTop")
    pg.click(TAB_CAL); pg.wait_for_url(lambda u: "/calendar" in u)
    pg.click(TAB_LIST); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("networkidle")
    assert _path_qs(pg.url) == url
    pg.wait_for_function(f"() => Math.abs(document.getElementById('appscroll').scrollTop - {y0}) <= 1", timeout=3000)
    assert _st(pg)["open"] is expand, "복귀 후 접힘/펼침 상태 그대로"
    ctx.close()


@pytest.mark.parametrize("case", ["phone-default", "phone-remembered", "phone-plain", "phone-large", "wide-768", "wide-1440"])
def test_p5_first_paint_equals_final_state(server, browser, case):
    """⑸ 번쩍임 없음 — 매 프레임(rAF) 기록한 open 이 전부 최종 상태와 같고, DOMContentLoaded 시점도 같다."""
    _seed(30)
    url = "/vehicles" if case == "phone-plain" else COND
    if case.startswith("wide"):
        ctx = _desk(browser, int(case.split("-")[1]), frames=True)
    else:
        ctx = _phone(browser, 390, large=(case == "phone-large"), frames=True)
    pg = ctx.new_page()
    if case == "phone-remembered":
        pg.goto(server + COND, wait_until="networkidle")
        pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
        pg.click('#listResults a[href*="page=2"]:visible'); pg.wait_for_url(lambda u: "page=2" in u)
    else:
        pg.goto(server + url, wait_until="networkidle")
    pg.wait_for_timeout(400)
    final = _st(pg)["open"]
    frames, dcl = pg.evaluate("() => [window.__ncFrames, window.__ncDCL]")
    expect = {"phone-default": False, "phone-remembered": True, "phone-plain": True, "phone-large": False, "wide-768": True, "wide-1440": True}[case]
    assert final is expect, (case, final)
    assert frames and all(f is final for f in frames), (case, frames[:10])
    assert dcl is final, (case, dcl)
    ctx.close()


def test_p6_large_mode_unchanged_and_toggle_off_leaves_handle(server, browser):
    """⑹ 큰글씨: 항상 접힘·summary 보임·접힌 칩 줄 없음(동작 무변경). 큰글씨를 끄면(ncToggleLarge) 펼치고, 좁은 폭 결과 화면이라 손잡이가 남는다."""
    _seed(30)
    ctx = _phone(browser, 360, large=True); pg = ctx.new_page()
    for url in (COND, "/vehicles"):
        pg.goto(server + url, wait_until="networkidle")
        s = _st(pg)
        assert s["large"] and s["open"] is False and s["summary"] and not s["row"], (url, s)
    pg.goto(server + COND, wait_until="networkidle")
    box = pg.locator("#listFilter > summary").bounding_box()
    assert box and box["height"] < 48, "한 줄 머리(test_b6 와 같은 기준 — ::before 는 bounding box 를 늘리지 않는다)"
    pg.evaluate("() => ncToggleLarge()"); pg.wait_for_timeout(250)
    s = _st(pg)
    assert not s["large"] and s["open"] is True and s["summary"] and not s["row"], s
    assert s["mem"] is None, "큰글씨 토글이 여는 것은 기억이 아니다"
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    s = _st(pg)
    assert s["open"] is False and s["row"], s
    ctx.close()


@pytest.mark.parametrize("w", [640, 768, 1440])
def test_p7_wide_stays_open_and_unchanged(server, browser, w):
    """② 넓은 폭(≥ 640)은 조건 결과 화면에서도 open · summary 숨김 · 접힌 칩 줄 숨김(렌더 무변경 — md5 증명은 보고서 캡처)."""
    _seed(30)
    ctx = _desk(browser, w); pg = ctx.new_page()
    for url in (COND, DATE, "/vehicles"):
        pg.goto(server + url, wait_until="networkidle")
        s = _st(pg)
        assert s["open"] is True and not s["summary"] and not s["row"] and not s["hscroll"], (w, url, s)
    ctx.close()


def test_p8_boundary_639_folds_and_rotation_to_wide_opens(server, browser):
    _seed(30)
    ctx = _desk(browser, 639); pg = ctx.new_page()
    pg.goto(server + COND, wait_until="networkidle")
    s = _st(pg)
    assert s["open"] is False and s["summary"] and s["row"], ("639 = sm 미만", s)
    # 폰 가로 회전처럼 폭이 640 이상이 되면 summary 가 숨으므로 연다 — 닫힌 채 손잡이 없는 카드를 남기지 않는다
    pg.set_viewport_size({"width": 844, "height": 390}); pg.wait_for_timeout(300)
    s = _st(pg)
    assert s["open"] is True and not s["summary"] and not s["row"] and s["mem"] is None, s
    ctx.close()


def test_p9_save_search_still_works_after_expanding(server, browser):
    """⑥ 검색 저장 동작 무변경 — 결과 화면 폰 폭에서는 카드를 펼친 뒤 누른다(버튼은 접힌 칩 줄에 넣지 않는다 — 지시서 (b) 정의)."""
    _seed(30)
    ctx = _phone(browser, 390); pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept())
    pg.goto(server + COND, wait_until="networkidle")
    assert pg.locator('#listFilterChips button[onclick="ncSaveSearch()"]').count() == 0
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    pg.click('#listFilter button[onclick="ncSaveSearch()"]')
    lst = pg.evaluate("() => JSON.parse(localStorage.getItem('naechaget:searches') || '[]')")
    assert lst and lst[0]["label"] == "현대 · 최저가 1,000~2,000만 · 2018년 이후", lst
    ctx.close()


CHEV = """() => { const d = document.getElementById('listFilter'), s = d.querySelector('summary');
  const ic = s.querySelectorAll('.material-symbols-outlined'), c = ic[ic.length - 1], sub = s.querySelector('span.truncate');
  const cs = getComputedStyle(c);
  return {open: d.open, t: cs.transform, dur: cs.transitionDuration, ease: cs.transitionTimingFunction,
          sub: sub ? getComputedStyle(sub).display : null, h: s.getBoundingClientRect().height}; }"""


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_p10_chevron_flips_when_expanded_and_respects_reduced_motion(server, browser, motion):
    """디자인 고칠 것 1 — 접힘: 셰브런 그대로(none)·부제 보임 / 펼침: 180°(matrix(-1,0,0,-1,0,0))·부제 숨김·머리 높이 그대로.
    전환은 transform 만, ease-out 토큰(0.23,1,0.32,1)·150ms. 모션 줄이기면 전환 0s(바로 뒤집힌다). 접근 이름에 리거처 글자가 없다."""
    _seed(30)
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, locale="ko-KR", is_mobile=True, has_touch=True,
                              reduced_motion=motion)
    ctx.add_init_script(NO_SPLASH); pg = ctx.new_page()
    pg.goto(server + COND, wait_until="networkidle")
    a = pg.evaluate(CHEV)
    assert a["open"] is False and a["t"] == "none" and a["sub"] != "none", a
    if motion == "reduce":
        assert a["dur"] == "0s", a
    else:
        assert a["dur"] == "0.15s" and a["ease"] == "cubic-bezier(0.23, 1, 0.32, 1)", a
    name = [n.get("name", {}).get("value", "") for n in ctx.new_cdp_session(pg).send("Accessibility.getFullAXTree")["nodes"]
            if n.get("role", {}).get("value") == "DisclosureTriangle"]
    assert name and name[0].startswith("검색 · 필터") and "expand_more" not in name[0] and "filter_list" not in name[0], name
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(400)
    b = pg.evaluate(CHEV)
    assert b["open"] is True and b["t"] == "matrix(-1, 0, 0, -1, 0, 0)" and b["sub"] == "none" and b["h"] == a["h"], b
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(400)
    c = pg.evaluate(CHEV)
    assert c["open"] is False and c["t"] == "none" and c["sub"] != "none", c
    # 판정 표시 설명(#listLegend) — 같은 규칙
    pg.evaluate("() => document.getElementById('listLegend').open = true"); pg.wait_for_timeout(400)
    lt = pg.evaluate("() => getComputedStyle(document.querySelector('#listLegend > summary .material-symbols-outlined')).transform")
    assert lt == "matrix(-1, 0, 0, -1, 0, 0)", lt
    ctx.close()


@pytest.mark.parametrize("entry", ["/vehicles?segment=sedan&upcoming=30", "/vehicles?bucket=lowconf"])   # 대시보드 링크 원문과 같은 꼴(sort 없음) — 픽스처 30건은 전부 lowconf 칸
def test_p11_sortless_entry_expanded_survives_page_2_and_unchanged_apply(server, browser, entry):
    """qa B-1 — 홈의 진입 링크는 sort 가 없고 서버 링크·폼은 sort=recent 를 싣는다. 기억 키가 기본 정렬을 빼므로 같은 조합이다:
    펼침 → 2페이지(링크에 sort=recent) 펼친 채 → 뒤로 펼친 채 → 앞으로 펼친 채 · 무변경 [적용] 펼친 채. 정렬을 바꾸면 여전히 새 조합(접힘)."""
    _seed(30)
    ctx = _phone(browser, 390); pg = ctx.new_page()
    pg.goto(server + entry, wait_until="networkidle")
    assert _st(pg)["open"] is False
    link = pg.locator('#listResults a[href*="page=2"]:visible').first
    assert link.count() == 1 and "sort=recent" in link.get_attribute("href"), "픽스처 전제: 2페이지가 있고 링크가 기본 정렬을 싣는다"
    pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)
    link.click(); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("networkidle")
    assert "sort=recent" in pg.url and _st(pg)["open"] is True, ("같은 조합 2페이지 → 펼친 채", pg.url)
    pg.go_back(); pg.wait_for_url(lambda u: "page=2" not in u); pg.wait_for_load_state("networkidle")
    assert _st(pg)["open"] is True, "뒤로 → 펼친 채"
    pg.go_forward(); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("networkidle")
    assert _st(pg)["open"] is True, "앞으로 → 펼친 채"
    pg.goto(server + entry, wait_until="networkidle")
    assert _st(pg)["open"] is True, "같은 조합 재진입 → 펼친 채"
    pg.locator("#listFilter form button.btn-ghost:not([type]):visible").click(); pg.wait_for_load_state("networkidle")
    assert "sort=recent" in pg.url and _st(pg)["open"] is True, ("무변경 [적용](폼이 sort=recent 를 싣는다) → 펼친 채", pg.url)
    pg.select_option("#listFilter select[name=sort]", "mileage")
    pg.locator("#listFilter form button.btn-ghost:not([type]):visible").click()
    pg.wait_for_url(lambda u: "sort=mileage" in u); pg.wait_for_load_state("networkidle")
    assert _st(pg)["open"] is False, "정렬을 바꾸면 새 조합 → 접힘"
    ctx.close()


def _split_anchor(body: bytes, where: str) -> int:
    i = body.find(b'<details id="listFilter"')
    if i < 0:
        return -1
    if where == "details-open":
        return body.index(b">", i) + 1
    if where == "summary-end":
        return body.index(b"</summary>", i) + len(b"</summary>")
    return body.index(b"</details>", i) + len(b"</details>")


@pytest.fixture(scope="module")
def split_proxy(server):
    """분할 전송 프록시 — 헤더 X-Split-At(details-open · summary-end · details-end) 자리에서 /vehicles HTML 을 끊고 0.8초 쉰다.
    파서가 그 자리에서 반드시 양보한다(데이터가 없다) — 결정이 '자리'에 기대면 닫힌 카드가 그려지고, 마이크로태스크(관찰 콜백)면 안 그려진다."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.request

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        def do_GET(self):
            r = urllib.request.urlopen(server + self.path)
            body = r.read()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Connection", "close"); self.end_headers()
            where = self.headers.get("X-Split-At")
            i = _split_anchor(body, where) if (where and self.path.startswith("/vehicles")) else -1
            if i > 0:
                self.wfile.write(body[:i]); self.wfile.flush(); time.sleep(0.8)
            self.wfile.write(body[max(i, 0):]); self.wfile.flush()

    httpd = ThreadingHTTPServer(("127.0.0.1", _free_port()), H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.mark.parametrize("where", ["details-open", "summary-end", "details-end"])
@pytest.mark.parametrize("view", ["wide-640", "wide-1440", "phone-remembered", "phone-default"])
def test_p12_split_delivery_never_paints_non_final_open_state(split_proxy, browser, where, view):
    """qa B-2 — 파서가 details 여는 태그 뒤·summary 뒤·details 뒤 어디서 멈춰도, 매 프레임(rAF)의 open 이 최종값과 같다.
    r1(`</details>` 뒤 스크립트)·`</summary>` 뒤·details 첫 자식 시안은 이 중 한 곳 이상에서 닫힌 프레임이 나왔다(r2 보고서)."""
    _seed(30)
    hdr = {"X-Split-At": where}
    if view.startswith("wide"):
        ctx = browser.new_context(viewport={"width": int(view.split("-")[1]), "height": 900}, device_scale_factor=1, locale="ko-KR",
                                  extra_http_headers=hdr)
        ctx.add_init_script(NO_SPLASH)
    else:
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, locale="ko-KR", is_mobile=True,
                                  has_touch=True, extra_http_headers=hdr)
        ctx.add_init_script(NO_SPLASH)
        if view == "phone-remembered":
            key = "maker=현대&price=1000-2000&sort=sale_date&year_min=2018"
            ctx.add_init_script("try{sessionStorage.setItem('nc:listFilterOpen', JSON.stringify({%s: 1}))}catch(e){}" % __import__("json").dumps(key, ensure_ascii=False))
    ctx.add_init_script(FRAME_LOG)
    pg = ctx.new_page()
    pg.goto(split_proxy + COND, wait_until="load"); pg.wait_for_timeout(300)
    final = _st(pg)["open"]
    frames = pg.evaluate("() => window.__ncFrames")
    expect = {"wide-640": True, "wide-1440": True, "phone-remembered": True, "phone-default": False}[view]
    assert final is expect, (view, final)
    assert frames and all(f is final for f in frames), (view, where, [f for f in frames if f is not final][:5], len(frames))
    ctx.close()
