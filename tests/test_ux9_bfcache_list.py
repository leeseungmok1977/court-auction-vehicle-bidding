"""UX-9 뒤로가기 캐시(bfcache) 복원 시 목록 고착·스크롤 손실 — 회귀 (지시서 2026-09-27-62).

배경(qa reports/2026-09-27-ux8-live-check.md — 라이브 재현 2/2, UX-8 회귀 아님):
  N1   vehicles.html 스켈레톤 IIFE(앵커 'listSkeleton' · 'function show(')가 페이지 링크 click 에서 #listResults 를 숨기고
       #listSkeleton 을 보인다. 폰 Chrome 기본값인 bfcache 는 떠나기 직전 DOM 을 얼렸다 되살리므로 '2' → 뒤로 = 회색 줄 8개로 고착.
  지적2 숨김으로 #appscroll 높이가 줄어 base.html 'nc:scroll' 저장(click·pagehide·visibilitychange)이 줄어든 scrollTop 을
       적는다(360: 4196→154). 리스너 순서만 바꾸면 pagehide·visibilitychange 가 다시 덮는다.
  N2   제출 스켈레톤의 `form[action="/vehicles"]` 는 헤더 검색 폼(base.html, hidden lg:block)을 잡는다 → '#listFilter form'.
       ⚠ N1 없이 셀렉터만 고치면 고착이 [적용]→뒤로 로 번진다 — 같은 회차에서 고친다(③이 그 경로를 지킨다).
처방: 숨기기 직전 scrollTop 을 잡아 두고 pagehide(capture)에서 목록·scrollTop 을 되돌린다 → bfcache 에 스켈레톤 상태가 안 남고,
      base.html 의 pagehide·visibilitychange 저장은 되돌린 값을 적는다. pageshow(persisted) 되돌림은 보험.

⚠ 하네스 함정 두 개 — 이걸 모르면 이 파일은 공허 통과한다(2026-09-27 실측):
  ① Playwright 는 Chromium 을 `--disable-back-forward-cache` 로 띄운다 → ignore_default_args 로 뺀다.
  ② 기본 headless(chromium-headless-shell)는 ①을 해도 bfcache 를 안 쓴다 — CDP Page.backForwardCacheNotUsed 이유
     `BackForwardCacheDisabledForDelegate`. → channel="chromium"(새 headless, 전체 Chromium)으로 띄운다.
  그래서 매 복귀마다 pageshow 의 event.persisted 를 단언한다(새 로드로 돌아왔으면 bfcache 경로를 밟지 않은 것).
  대조로 bfcache 를 끈 기본 브라우저(= 새 로드 back_forward)의 스크롤 복원도 따로 본다 — qa 의 4196→154 는 그 경로였다.

두 층: A. 템플릿 소스 앵커(줄 번호 금지)  B. 동작(Playwright, 같은 프로세스 스레드 uvicorn — conftest 임시 DB).
서버는 127.0.0.1 → 관리자 뷰(PC 폰 프레임 리다이렉트 없음). 폰 폭은 is_mobile·has_touch. 서비스워커는 새 컨텍스트라 허용(영속 프로필 함정 없음).
"""
import asyncio
import re
import socket
import threading
import time
from datetime import date, timedelta

import pytest

from web import db

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964, 8996, 8917}
TODAY = date.today()

BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1, "mileage_km": 50_000,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(n=30):
    """30건 = 3페이지(VEHICLES_PAGE_SIZE 12). 기아 몇 건은 [적용] 경로에서 조건을 바꾸기 위해."""
    db.init_db()
    for i in range(n):
        maker, model = ("기아", "쏘렌토(SORENTO)") if i % 5 == 0 else ("현대", "쏘나타(SONATA)")
        db.upsert_vehicle(dict(BASE, id=f"U{i:02d}", case_no=f"2026타경9{i:04d}", model=model, maker=maker,
                               sale_date=(TODAY + timedelta(days=3 + i)).isoformat()))


# ═══════════════════════════════════ A. 템플릿(소스 앵커) ═══════════════════════════════════

def _skeleton_iife() -> str:
    i = LIST_TPL.index("var res=document.getElementById('listResults')")
    return LIST_TPL[i:LIST_TPL.index("})();", i)]


def test_skeleton_iife_hooks_filter_form_not_header_search():
    s = _skeleton_iife()
    assert "document.querySelector('#listFilter form')" in s, "N2: 제출 스켈레톤은 필터 폼(#listFilter 안)에 건다"
    assert 'form[action="/vehicles"]' not in s, "N2: 헤더 검색 폼(hidden lg:block)이 먼저 잡히는 셀렉터"


def test_skeleton_iife_reverts_on_pagehide_and_pageshow():
    s = _skeleton_iife()
    assert re.search(r"addEventListener\('pagehide',\s*undo,\s*true\)", s), "N1·지적2: pagehide(capture)에서 되돌린다 — base.html 저장보다 먼저"
    assert re.search(r"addEventListener\('pageshow',\s*function\(e\)\{\s*if\(e\.persisted\)\s*undo\(\);", s), "보험: bfcache 복원 시 되돌림"
    assert "scrollTop=y0" in s.replace(" ", ""), "지적2: 숨기기 전 scrollTop 으로 되돌린다"


# ═══════════════════════════════════ B. 동작(Playwright) ═══════════════════════════════════

def _free_port() -> int:
    for _ in range(20):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


SLOW = {"page2": 0.0}      # >0 이면 /vehicles?…page=2 응답을 그만큼 늦춘다(느린 망 흉내 — 서버 쪽이라 누를 때의 미리 받기 요청도 같이 늦는다)


def _with_delay(app):
    async def wrapped(scope, receive, send):
        if SLOW["page2"] and scope["type"] == "http" and scope["path"] == "/vehicles" and b"page=2" in scope.get("query_string", b""):
            await asyncio.sleep(SLOW["page2"])
        await app(scope, receive, send)
    return wrapped


@pytest.fixture(scope="module")
def server():
    uvicorn = pytest.importorskip("uvicorn")
    import web.app as A
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(_with_delay(A.app), host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
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
def pw():
    m = pytest.importorskip("playwright.sync_api")
    with m.sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def bf_browser(pw):
    """bfcache 를 켠 Chromium — 함정 ①②(모듈 docstring)."""
    try:
        b = pw.chromium.launch(channel="chromium", ignore_default_args=["--disable-back-forward-cache"])
    except Exception as e:      # 전체 Chromium 미설치
        pytest.skip(f"chromium(channel) 없음: {e}")
    yield b
    b.close()


@pytest.fixture(scope="module")
def plain_browser(pw):
    """Playwright 기본(bfcache 끔) — 뒤로가기가 새 로드(back_forward)가 되는 경로."""
    try:
        b = pw.chromium.launch()
    except Exception as e:
        pytest.skip(f"chromium 없음: {e}")
    yield b
    b.close()


@pytest.fixture
def ctxs():
    """이 테스트가 연 컨텍스트를 **단언이 실패해도** 닫는다 — 열린 채 남은 미리 받기·미리 렌더 요청이 다음 테스트(또는
    conftest 가 DB_PATH 를 되돌린 뒤)의 서버로 새지 않게. autouse 임시 DB 픽스처보다 먼저 정리된다(나중에 세워지므로)."""
    opened = []
    yield opened
    SLOW["page2"] = 0.0
    for c in opened:
        try:
            c.close()
        except Exception:
            pass


# 문서 스크립트보다 먼저 도는 기록기. bfcache 로 돌아오면 같은 window 라 기록이 이어진다(새 로드면 새로 시작).
PROBE = """
try{sessionStorage.setItem('nc_splash','1')}catch(e){}
window.__ps = [];
window.addEventListener('pageshow', function(e){ window.__ps.push(e.persisted); });
window.__sk = [];
document.addEventListener('DOMContentLoaded', function(){
  var s = document.getElementById('listSkeleton'); if(!s) return;
  new MutationObserver(function(){ window.__sk.push(s.classList.contains('hidden') ? 'hidden' : 'shown'); })
    .observe(s, {attributes:true, attributeFilter:['class']});
});
"""
STATE = """() => {
  const r = document.getElementById('listResults'), s = document.getElementById('listSkeleton'), a = document.getElementById('appscroll');
  const vis = e => !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0;
  let store = {}; try { store = JSON.parse(sessionStorage.getItem('nc:scroll') || '{}'); } catch (e) {}
  const nav = performance.getEntriesByType('navigation')[0];
  return {results: vis(r), skeleton: vis(s), top: a.scrollTop, ch: a.clientHeight, sh: a.scrollHeight,
          stored: store[location.pathname + location.search], ps: window.__ps.slice(), sk: window.__sk.slice(),
          navtype: nav ? nav.type : null, url: location.pathname + location.search};
}"""
TAB_LIST = 'nav[class~="lg:hidden"] a[data-nav="vehicles"]'
TAB_CAL = 'nav[class~="lg:hidden"] a[href="/calendar"]'
HEIGHT = {390: 844, 360: 780}


def _phone(browser, w, ctxs):
    ctx = browser.new_context(viewport={"width": w, "height": HEIGHT[w]}, device_scale_factor=1, locale="ko-KR",
                              is_mobile=True, has_touch=True)
    ctx.add_init_script(PROBE)
    ctxs.append(ctx)
    return ctx


def _st(pg):
    return pg.evaluate(STATE)


def _page_link(pg, which):
    loc = pg.locator('#listResults a[href*="page=2"]')
    loc = loc.filter(has_text=re.compile(r"^\s*2\s*$")) if which == "2" else loc.filter(has_text="다음")
    return loc.locator("visible=true").first


def _back_bf(pg):
    """뒤로 → bfcache 복원(pageshow persisted=true)까지 기다린다. 새 로드였으면 여기서 실패(공허 통과 방지)."""
    pg.go_back(wait_until="commit")
    try:
        pg.wait_for_function("() => window.__ps && window.__ps.indexOf(true) >= 0", timeout=5000)
    except Exception:
        raise AssertionError(f"bfcache 복원이 아니다(pageshow persisted 없음) — 하네스 함정 ①②: {_st(pg)}")
    pg.wait_for_timeout(300)      # 복원 뒤 rAF(base.html restore 의 두 번째 대입)까지
    return _st(pg)


def _assert_restored(st, y_click, where):
    assert st["results"], f"{where}: 목록이 보여야 한다(N1 — 스켈레톤 고착): {st}"
    assert not st["skeleton"], f"{where}: 스켈레톤은 숨어야 한다: {st}"
    assert abs(st["top"] - y_click) <= st["ch"], f"{where}: 누른 자리 ±1화면({y_click}±{st['ch']}) — 지적2: {st}"
    assert st["stored"] is not None and abs(st["stored"] - y_click) <= st["ch"], \
        f"{where}: nc:scroll 저장값도 누른 자리(새 로드 복귀가 이 값을 쓴다): {st}"


@pytest.mark.parametrize("w", [390, 360])
@pytest.mark.parametrize("which", ["2", "다음"])
def test_page_link_then_back_restores_list_and_scroll(server, bf_browser, ctxs, w, which):
    """①② · ⑥ — 페이지 '2' / '다음 ›' → 뒤로(bfcache)."""
    _seed()
    ctx = _phone(bf_browser, w, ctxs); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    link = _page_link(pg, which)
    link.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
    y = _st(pg)["top"]
    assert y > HEIGHT[w], f"픽스처 전제: 페이지 링크가 첫 화면 밖(스크롤 {y})"
    link.click(); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("load")
    st = _back_bf(pg)
    assert st["sk"][:1] == ["shown"], f"스켈레톤 가치 유지 — 링크를 누르면 보였어야 한다: {st['sk']}"
    _assert_restored(st, y, f"{w} '{which}' → 뒤로")


@pytest.mark.parametrize("w", [390, 360])
def test_apply_then_back_restores_list(server, bf_browser, ctxs, w):
    """③ — 필터 [적용] → 뒤로. N2 로 제출 스켈레톤이 이제 필터 폼에 걸린다 → N1 처방 없이면 여기서 고착."""
    _seed()
    ctx = _phone(bf_browser, w, ctxs); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    assert pg.eval_on_selector("#listFilter", "d => d.open"), "조건 없는 첫 진입은 펼침(UX-8)"
    pg.select_option("#listFilter select[name=maker]", "기아")
    btn = pg.locator("#listFilter form button.btn-ghost:not([type])").locator("visible=true").first
    btn.scroll_into_view_if_needed()
    y = _st(pg)["top"]
    btn.click(); pg.wait_for_url(lambda u: "maker=" in u); pg.wait_for_load_state("load")
    st = _back_bf(pg)
    assert st["sk"][:1] == ["shown"], f"N2: [적용] 제출에 스켈레톤이 걸려야 한다(헤더 검색 폼이 아니라): {st['sk']}"
    _assert_restored(st, y, f"{w} [적용] → 뒤로")


@pytest.mark.parametrize("w", [390, 360])
def test_detail_then_back_keeps_list_and_scroll(server, bf_browser, ctxs, w):
    """④ 회귀 — 상세 카드 → 뒤로(스켈레톤을 안 거치는 경로. qa D: 3421 그대로)."""
    _seed()
    ctx = _phone(bf_browser, w, ctxs); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    card = pg.locator('#listResults a[href^="/vehicle/"]').locator("visible=true").nth(6)
    card.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
    y = _st(pg)["top"]
    assert y > 0
    card.click(); pg.wait_for_url(lambda u: "/vehicle/" in u); pg.wait_for_load_state("load")
    st = _back_bf(pg)
    assert st["sk"] == [], f"상세 경로는 스켈레톤을 건드리지 않는다: {st['sk']}"
    _assert_restored(st, y, f"{w} 상세 → 뒤로")


def test_tab_return_after_page_back_restores_scroll(server, bf_browser, ctxs):
    """⑤ UX-2 회귀 — '2' → 뒤로(bfcache) → 달력 탭 → 차량목록 탭 = 1페이지 누른 자리."""
    _seed()
    ctx = _phone(bf_browser, 390, ctxs); pg = ctx.new_page()
    pg.goto(server + "/vehicles?sort=sale_date", wait_until="networkidle")
    link = _page_link(pg, "2"); link.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
    y = _st(pg)["top"]
    link.click(); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("load")
    _assert_restored(_back_bf(pg), y, "'2' → 뒤로")
    pg.click(TAB_CAL); pg.wait_for_url(lambda u: "/calendar" in u); pg.wait_for_load_state("load")
    pg.click(TAB_LIST); pg.wait_for_url(lambda u: "/vehicles" in u); pg.wait_for_load_state("load")
    pg.wait_for_timeout(300)
    st = _st(pg)
    assert st["url"] == "/vehicles?sort=sale_date", f"탭 복귀 = 마지막 목록(1페이지): {st['url']}"
    assert st["results"] and not st["skeleton"], st
    assert abs(st["top"] - y) <= st["ch"], f"탭 복귀도 누른 자리(±1화면, {y}): {st}"
    assert pg.evaluate("() => sessionStorage.getItem('nc:restoreScroll')") is None, "플래그는 한 번 쓰고 지운다(UX-2)"


@pytest.mark.parametrize("w", [390, 360])
def test_page_link_then_back_without_bfcache_restores_scroll(server, plain_browser, ctxs, w):
    """지적2 대조 — bfcache 가 없을 때(새 로드 back_forward) nc:scroll 복원이 누른 자리를 쓴다(qa A: 4196→154 였다)."""
    _seed()
    ctx = _phone(plain_browser, w, ctxs); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    link = _page_link(pg, "2"); link.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
    y = _st(pg)["top"]
    link.click(); pg.wait_for_url(lambda u: "page=2" in u); pg.wait_for_load_state("load")
    pg.go_back(wait_until="load"); pg.wait_for_timeout(400)
    st = _st(pg)
    assert st["ps"] == [False] and st["navtype"] == "back_forward", f"대조군은 새 로드여야 한다: {st}"
    _assert_restored(st, y, f"{w} bfcache 없음 '2' → 뒤로")


def test_modified_click_opens_tab_without_hiding_list(server, bf_browser, ctxs):
    """새 탭으로 여는 클릭(Ctrl)은 이 문서를 떠나지 않는다 — 스켈레톤을 걸면 pagehide 가 안 와서 그대로 고착된다."""
    _seed()
    ctx = bf_browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1, locale="ko-KR")
    ctx.add_init_script(PROBE); ctxs.append(ctx)
    pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    link = _page_link(pg, "2"); link.scroll_into_view_if_needed()
    with ctx.expect_page() as newp:
        link.click(modifiers=["Control"])
    newp.value.close()
    pg.wait_for_timeout(200)
    st = _st(pg)
    assert st["results"] and not st["skeleton"] and st["sk"] == [], f"원래 탭 목록 그대로: {st}"


# 1페이지에서만 100ms 마다 스켈레톤 상태를 sessionStorage 에 적는다(같은 탭이라 다음 화면에서 읽힌다).
SAMPLER = """
if (location.search.indexOf('page=2') < 0) setInterval(function(){ try {
  var s = document.getElementById('listSkeleton'), r = document.getElementById('listResults'); if (!s || !r) return;
  var l = JSON.parse(sessionStorage.getItem('ux9:samples') || '[]');
  l.push({t: Date.now(), sk: getComputedStyle(s).display !== 'none', res: getComputedStyle(r).display !== 'none',
          top: Math.round(s.getBoundingClientRect().top)});
  sessionStorage.setItem('ux9:samples', JSON.stringify(l.slice(-60)));
} catch (e) {} }, 100);
"""


def test_skeleton_still_shows_on_slow_network(server, bf_browser, ctxs):
    """가치 유지 — 느린 망에서 '2' 를 누르면 다음 화면이 오기 전까지 스켈레톤이 화면 안에 보인다.
    ⚠ 측정 함정(2026-09-27 실측, channel=chromium): 이동이 걸려 있는 동안 page.evaluate·page.screenshot·CDP Runtime.evaluate 는
      **커밋될 때까지 돌아오지 않는다**(3.5~4.4초 막힌 뒤 evaluate 는 '컨텍스트 파괴' 오류 또는 다음 화면의 값). 그 사이 페이지 JS 는
      100ms 마다 돈다. → 페이지 안 기록기(SAMPLER)가 sessionStorage 에 적은 것을 다음 화면에서 읽는다.
      늦추기는 서버 쪽(SLOW) — CDP 망 흉내(latency 2500ms)로도 커밋이 2.8초로 늦어지지만, CDP 에 기대지 않는 쪽이 결정적이다."""
    _seed()
    ctx = _phone(bf_browser, 390, ctxs); ctx.add_init_script(SAMPLER); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="networkidle")
    link = _page_link(pg, "2"); link.scroll_into_view_if_needed(); pg.wait_for_timeout(250)
    SLOW["page2"] = 2.0
    t_click = pg.evaluate("() => Date.now()")
    link.click(no_wait_after=True)
    pg.wait_for_url(lambda u: "page=2" in u, timeout=15000)
    samples = [x for x in pg.evaluate("() => JSON.parse(sessionStorage.getItem('ux9:samples') || '[]')") if x["t"] > t_click]
    assert len(samples) >= 10, f"느린 망 전제(1초 이상 1페이지에 머묾): {len(samples)}개"
    shown = [x for x in samples if x["sk"] and not x["res"]]
    assert len(shown) >= len(samples) - 1, f"넘어가는 중 내내 스켈레톤(첫 표본은 누르기 직전일 수 있다): {samples}"
    assert all(0 <= x["top"] < HEIGHT[390] for x in shown), f"스켈레톤이 화면 안에 있어야 보인다: {shown}"
