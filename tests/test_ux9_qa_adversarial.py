"""UX-9 적대적 반증 — 구현(tests/test_ux9_bfcache_list.py)이 밟지 않은 경로 (qa-engineer, 지시서 2026-09-27-63).

대상: web/templates/vehicles.html 스켈레톤 IIFE(앵커 'listSkeleton' · 'function undo(') 와 base.html 스크롤 복원(앵커 "var KEY = 'nc:scroll'").
처방(작업 트리): 숨기기 직전 scrollTop(y0) 을 잡고 pagehide(capture)에서 목록·scrollTop 을 되돌린다 + pageshow(persisted) 보험 +
                제출 셀렉터 '#listFilter form'(N2) + 새 탭 클릭 제외.

이 파일이 더 밟는 것(2026-09-27 qa 실측, 운영 DB 사본에서도 같은 결과 — reports/2026-09-27-ux9-qa.md):
  앞으로/뒤로 왕복 · 3페이지 연쇄 · '‹ 이전' · 더블클릭(y0 는 첫 값) · 조건 목록 접힘/펼침(UX-8) 유지 · 접힌 칩 ✕ · 큰글씨 ·
  필터 검색칸 Enter 제출 · 데스크톱 헤더 검색(N2 — 스켈레톤이 걸리면 안 된다) · 데스크톱 표 '2' · 키보드 Enter ·
  커밋 전 뒤로(이동 취소) → 앞으로 · 오프라인 오류 페이지 → 뒤로 · PC 공개 뷰 폰 프레임(iframe — bfcache 대상 아님) ·
  bfcache 없는 연쇄(새 로드 복원값).
  ⚠ 잔여(기존 결함, HEAD 도 같다): 커밋 전 **이동 중단**(브라우저 X·ESC = Page.stopLoading)은 문서를 떠나지 않아 pagehide 가 없다 →
    스켈레톤 고착. strict xfail 로 적어 두었다 — UX-9 r2(frontend)가 고쳐 표시를 뗐다(test_stop_loading_before_commit_restores_list).

⚠ 하네스 함정(구현 파일 docstring 과 같다): Playwright 는 `--disable-back-forward-cache` 로 띄운다 → ignore_default_args 로 뺀다.
  기본 headless shell 은 그래도 bfcache 를 안 쓴다 → channel="chrome"(설치된 Chrome) 우선, 없으면 channel="chromium".
  복귀마다 pageshow 의 event.persisted 를 단언한다(새 로드면 bfcache 경로를 안 밟은 것 = 공허 통과).
  bfcache 복원에는 load 이벤트가 없다 → 복귀 대기는 wait_until="commit" + persisted 폴링(`wait_for_url` 기본값 load 로 기다리면 30초 타임아웃).
"""
import asyncio
import re
import socket
import threading
import time
from datetime import date, timedelta

import pytest

from web import db

FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964, 8996, 8917, 8853, 8854}
TODAY = date.today()
H = {390: 844, 360: 780}
HYUNDAI = "%ED%98%84%EB%8C%80"     # 현대

BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1, "mileage_km": 50_000,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(n=30):
    """30건 = 3페이지(VEHICLES_PAGE_SIZE 12). 현대 24건 = 조건 목록 2페이지. 매각기일 전부 30일 안 → upcoming=30 해제 칩이 생긴다."""
    db.init_db()
    for i in range(n):
        maker, model = ("기아", "쏘렌토(SORENTO)") if i % 5 == 0 else ("현대", "쏘나타(SONATA)")
        db.upsert_vehicle(dict(BASE, id=f"Q{i:02d}", case_no=f"2026타경8{i:04d}", model=model, maker=maker,
                               sale_date=(TODAY + timedelta(days=3 + i % 20)).isoformat()))


def _free_port() -> int:
    for _ in range(20):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


SLOW = {"page2": 0.0}


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


def _launch(pw, bfcache=True):
    kw = {"ignore_default_args": ["--disable-back-forward-cache"]} if bfcache else {}
    last = None
    for ch in ("chrome", "chromium"):
        try:
            return pw.chromium.launch(channel=ch, **kw)
        except Exception as e:       # 채널 미설치
            last = e
    pytest.skip(f"chrome/chromium 채널 없음: {last}")


@pytest.fixture(scope="module")
def bf(pw):
    b = _launch(pw, True)
    yield b
    b.close()


@pytest.fixture(scope="module")
def nobf(pw):
    b = _launch(pw, False)
    yield b
    b.close()


@pytest.fixture
def ctxs():
    """단언이 실패해도 컨텍스트를 닫는다(열린 미리 받기 요청이 다음 테스트 DB 로 새지 않게)."""
    opened = []
    yield opened
    SLOW["page2"] = 0.0
    for c in opened:
        try:
            c.close()
        except Exception:
            pass


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
  const r = document.getElementById('listResults'), s = document.getElementById('listSkeleton'), a = document.getElementById('appscroll'),
        d = document.getElementById('listFilter'), c = document.getElementById('listFilterChips');
  const vis = e => !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0;
  let store = {}; try { store = JSON.parse(sessionStorage.getItem('nc:scroll') || '{}'); } catch (e) {}
  const nav = performance.getEntriesByType('navigation')[0];
  return {results: vis(r), skeleton: vis(s), top: a.scrollTop, ch: a.clientHeight, stored: store[location.pathname + location.search],
          open: d ? d.open : null, chips: vis(c), ps: (window.__ps || []).slice(), sk: (window.__sk || []).slice(),
          navtype: nav ? nav.type : null, url: location.pathname + location.search};
}"""


def _phone(browser, w, ctxs, large=False, sw="allow"):
    ctx = browser.new_context(viewport={"width": w, "height": H[w]}, device_scale_factor=1, locale="ko-KR",
                              is_mobile=True, has_touch=True, service_workers=sw)
    if large:
        ctx.add_init_script("try{localStorage.setItem('naechaget:large','1')}catch(e){}")
    ctx.add_init_script(PROBE)
    ctxs.append(ctx)
    return ctx


def _desk(browser, ctxs, headers=None):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ko-KR",
                              extra_http_headers=headers or {})
    ctx.add_init_script(PROBE)
    ctxs.append(ctx)
    return ctx


def _st(target):
    for _ in range(50):
        try:
            return target.evaluate(STATE)
        except Exception:        # 복원 직후 실행 컨텍스트 교체
            time.sleep(0.1)
    return target.evaluate(STATE)


def _link(pg, which):
    loc = pg.locator('#listResults a[href*="page="]')
    loc = loc.filter(has_text=which) if which in ("다음", "이전") else loc.filter(has_text=re.compile(r"^\s*%s\s*$" % which))
    return loc.locator("visible=true").first


def _at(pg, link):
    link.scroll_into_view_if_needed(); pg.wait_for_timeout(200)
    return _st(pg)["top"]


def _wait_url(pg, pat):
    pg.wait_for_url(re.compile(pat), timeout=15000, wait_until="commit")
    pg.wait_for_load_state("load"); pg.wait_for_timeout(300)


def _restored(pg, bfcache=True, t=6.0):
    """복귀 뒤 상태. bfcache=True 면 persisted 복원이어야 하고, False 면 새 로드(back_forward)여야 한다."""
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            ps = pg.evaluate("() => window.__ps || null")
            if ps and (ps[-1] is True or (not bfcache and time.time() - t0 > 1.0)):
                break
        except Exception:
            pass
        time.sleep(0.05)
    pg.wait_for_timeout(400)      # base.html restore 의 rAF 두 번째 대입까지
    s = _st(pg)
    if bfcache:
        assert s["ps"] and s["ps"][-1] is True, f"bfcache 복원이 아니다(pageshow persisted 없음) — 공허 통과 방지: {s}"
    else:
        assert s["ps"] == [False] and s["navtype"] == "back_forward", f"새 로드(back_forward)여야 한다: {s}"
    return s


def _back(pg, bfcache=True):
    pg.go_back(wait_until="commit")
    return _restored(pg, bfcache)


def _ok(s, y, where, open0=None, tol=4):
    assert s["results"], f"{where}: 목록이 보여야 한다(N1 고착): {s}"
    assert not s["skeleton"], f"{where}: 스켈레톤은 숨어야 한다: {s}"
    assert abs(s["top"] - y) <= tol, f"{where}: 누른 자리 {y} 그대로(지적 2): {s}"
    assert s["stored"] is not None and abs(s["stored"] - y) <= tol, f"{where}: nc:scroll 저장값도 {y}(새 로드 복귀가 이 값을 쓴다): {s}"
    if open0 is not None:
        assert s["open"] is open0, f"{where}: 필터 카드 여닫이(UX-8)가 떠나기 전과 같아야 한다({open0}): {s}"


# ═══════════════════════════════ bfcache 켬 ═══════════════════════════════

def test_forward_back_cycles_keep_list_on_both_pages(server, bf, ctxs):
    """'2' → (뒤로 → 앞으로) × 3 — 1·2페이지 모두 매번 목록이 보이고 1페이지는 누른 자리."""
    _seed()
    pg = _phone(bf, 360, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    L.tap(); _wait_url(pg, r"page=2")
    for i in range(3):
        _ok(_back(pg), y, f"#{i} 뒤로=1페이지")
        pg.go_forward(wait_until="commit")
        s2 = _restored(pg)
        assert "page=2" in s2["url"] and s2["results"] and not s2["skeleton"], f"#{i} 앞으로=2페이지 목록: {s2}"


def test_chain_page3_then_back_twice(server, bf, ctxs):
    """1 → '2' → '3' → 뒤로(2페이지, 그 페이지에서 누른 자리) → 뒤로(1페이지, 누른 자리)."""
    _seed()
    pg = _phone(bf, 390, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y1 = _at(pg, L); L.tap(); _wait_url(pg, r"page=2")
    L3 = _link(pg, "3"); y2 = _at(pg, L3); L3.tap(); _wait_url(pg, r"page=3")
    _ok(_back(pg), y2, "3 → 뒤로 = 2페이지")
    _ok(_back(pg), y1, "→ 뒤로 = 1페이지")


def test_prev_link_from_page3_then_back(server, bf, ctxs):
    """3페이지에서 '‹ 이전'(= 새 이동) → 뒤로 = 3페이지 누른 자리."""
    _seed()
    pg = _phone(bf, 360, ctxs).new_page()
    pg.goto(server + "/vehicles?sort=recent&page=3", wait_until="load")
    L = _link(pg, "이전"); y = _at(pg, L)
    L.tap(); _wait_url(pg, r"page=2")
    _ok(_back(pg), y, "'‹ 이전' → 뒤로")


def test_double_click_keeps_first_scroll(server, bf, ctxs):
    """같은 링크 두 번(빠른 연타) — 두 번째 show() 가 줄어든 scrollTop 으로 y0 를 덮으면 안 된다."""
    _seed()
    pg = _phone(bf, 360, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    pg.evaluate("""() => { const a = [...document.querySelectorAll('#listResults a[href*="page=2"]')].find(x => x.offsetParent);
                           setTimeout(() => { a.click(); a.click(); }, 0); }""")
    for _ in range(100):
        if "page=2" in pg.url:
            break
        time.sleep(0.1)
    pg.wait_for_load_state("load"); pg.wait_for_timeout(300)
    _ok(_back(pg), y, "연타 → 뒤로")


@pytest.mark.parametrize("expand", [False, True], ids=["folded", "expanded"])
def test_condition_list_fold_state_survives_bfcache(server, bf, ctxs, expand):
    """조건 목록(UX-8: 좁은 폭 결과 화면은 접힘) — 접힌 채/펼친 채 '2' → 뒤로 = 같은 여닫이 + 목록 + 누른 자리."""
    _seed()
    pg = _phone(bf, 360, ctxs).new_page()
    pg.goto(server + f"/vehicles?maker={HYUNDAI}", wait_until="load")
    assert pg.evaluate("() => document.getElementById('listFilter').open") is False, "전제: 결과 화면 좁은 폭은 접힘"
    if expand:
        pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(300)
    open0 = pg.evaluate("() => document.getElementById('listFilter').open")
    assert open0 is expand
    L = _link(pg, "2"); y = _at(pg, L)
    L.tap(); _wait_url(pg, r"page=2")
    _ok(_back(pg), y, f"조건 목록 {'펼침' if expand else '접힘'} '2' → 뒤로", open0=open0)


def test_fold_chip_x_then_back_does_not_touch_skeleton(server, bf, ctxs):
    """접힌 칩 줄(#listFilterChips)의 해제 ✕ — 스켈레톤을 거치지 않는 경로. 뒤로 = 접힘·칩 줄·목록 그대로."""
    _seed()
    pg = _phone(bf, 360, ctxs).new_page()
    pg.goto(server + f"/vehicles?maker={HYUNDAI}&upcoming=30", wait_until="load")
    s0 = _st(pg)
    assert s0["open"] is False and s0["chips"], f"전제: 접힘 + 해제 칩 줄: {s0}"
    pg.locator("#listFilterChips a").locator("visible=true").first.tap()
    pg.wait_for_url(lambda u: "upcoming=" not in u, wait_until="commit"); pg.wait_for_load_state("load"); pg.wait_for_timeout(300)
    s = _back(pg)
    assert s["sk"] == [], f"칩 ✕ 는 스켈레톤을 건드리지 않는다: {s['sk']}"
    _ok(s, s0["top"], "칩 ✕ → 뒤로", open0=False)
    assert s["chips"], f"접힌 칩 줄이 다시 보여야 한다: {s}"


def test_large_font_page_link_then_back(server, bf, ctxs):
    """큰글씨(nc-large — 필터 카드 항상 접힘) '다음 ›' → 뒤로."""
    _seed()
    pg = _phone(bf, 360, ctxs, large=True).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    assert pg.evaluate("() => document.documentElement.classList.contains('nc-large')"), "전제: 큰글씨"
    L = _link(pg, "다음"); y = _at(pg, L)
    L.tap(); _wait_url(pg, r"page=2")
    _ok(_back(pg), y, "큰글씨 '다음' → 뒤로", open0=False)


def test_filter_search_enter_submits_skeleton_then_back(server, bf, ctxs):
    """필터 카드 검색칸 Enter(= #listFilter form submit) — N2 로 스켈레톤이 걸린다 → 뒤로 = 목록."""
    _seed()
    pg = _phone(bf, 390, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    inp = pg.locator("#listFilter input[name=q]").locator("visible=true").first
    y = _at(pg, inp)
    inp.fill("쏘나타"); inp.press("Enter")
    _wait_url(pg, r"q=")
    s = _back(pg)
    assert s["sk"][:1] == ["shown"], f"필터 폼 제출에 스켈레톤(N2): {s['sk']}"
    _ok(s, y, "검색칸 Enter → 뒤로", open0=True)


def test_desktop_header_search_does_not_trigger_skeleton(server, bf, ctxs):
    """N2 회귀 — 1440 헤더 검색 폼(base.html hidden lg:block)은 목록 스켈레톤과 무관. HEAD 는 여기서 스켈레톤을 걸고 뒤로 = 고착."""
    _seed()
    pg = _desk(bf, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    inp = pg.locator('form[action="/vehicles"].lg\\:block input[name=q]')
    inp.fill("쏘나타"); inp.press("Enter")
    _wait_url(pg, r"q=")
    s = _back(pg)
    assert s["sk"] == [], f"헤더 검색은 스켈레톤을 걸지 않는다(N2): {s['sk']}"
    _ok(s, 0, "헤더 검색 → 뒤로")


def test_desktop_table_page_link_then_back(server, bf, ctxs):
    """1440 관리자 뷰(최상위 문서·표 레이아웃) '2' → 뒤로."""
    _seed()
    pg = _desk(bf, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    L.click(); _wait_url(pg, r"page=2")
    _ok(_back(pg), y, "1440 '2' → 뒤로")


def test_keyboard_enter_on_page_link_then_back(server, bf, ctxs):
    """키보드 Enter 로 연 페이지 링크(click, button 0) → 뒤로."""
    _seed()
    pg = _phone(bf, 390, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    L.focus(); pg.keyboard.press("Enter"); _wait_url(pg, r"page=2")
    _ok(_back(pg), y, "키보드 Enter → 뒤로")


def test_back_before_commit_cancels_then_forward_restores_list(server, bf, ctxs):
    """느린 망에서 '2' → 커밋 전 뒤로(이동 취소, 직전 화면=달력) → 앞으로 = 1페이지 목록·누른 자리. HEAD 는 스켈레톤 고착."""
    _seed()
    pg = _phone(bf, 390, ctxs, sw="block").new_page()
    pg.goto(server + "/calendar", wait_until="load")
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    SLOW["page2"] = 4.0
    L.tap(no_wait_after=True)
    pg.wait_for_timeout(700)
    try:
        pg.go_back(wait_until="commit")        # 대기 중인 이동이 취소되며 ERR_ABORTED 를 던질 수 있다
    except Exception:
        pass
    pg.wait_for_url(re.compile(r"/calendar"), wait_until="commit", timeout=10000)
    pg.wait_for_timeout(500)
    SLOW["page2"] = 0.0
    pg.go_forward(wait_until="commit")
    _ok(_restored(pg), y, "커밋 전 뒤로 → 앞으로")


def test_offline_error_page_then_back(server, bf, ctxs):
    """오프라인에서 '2'(서비스워커 없음 → 크롬 오류 페이지로 커밋) → 온라인 → 뒤로 = 목록·누른 자리."""
    _seed()
    ctx = _phone(bf, 390, ctxs, sw="block"); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    ctx.set_offline(True)
    L.tap(no_wait_after=True)
    pg.wait_for_timeout(2000)
    ctx.set_offline(False)
    pg.go_back(wait_until="commit")
    _ok(_restored(pg), y, "오프라인 '2' → 뒤로")


def test_stop_loading_before_commit_restores_list(server, bf, ctxs):
    """커밋 전 이동 중단(X·ESC = Page.stopLoading) — 문서를 떠나지 않아 pagehide 가 없다. qa 가 strict xfail 로 적어 둔 잔여(HEAD 동일)를
    UX-9 r2 가 Navigation API(navigate signal abort)로 고쳐 표시를 뗐다(변형은 tests/test_ux9_r2_fixes.py)."""
    _seed()
    ctx = _phone(bf, 390, ctxs, sw="block"); pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg); cdp.send("Page.enable")
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y = _at(pg, L)
    SLOW["page2"] = 4.0
    L.tap(no_wait_after=True)
    pg.wait_for_timeout(700)
    cdp.send("Page.stopLoading")
    pg.wait_for_timeout(1500)
    s = _st(pg)
    assert "page=2" not in s["url"], f"전제: 이동이 중단돼 1페이지에 남아 있다: {s}"
    assert s["results"] and not s["skeleton"], f"중단 뒤에도 목록이 보여야 한다: {s}"
    assert abs(s["top"] - y) <= 4, s


# ═══════════════════════════════ bfcache 없음(새 로드) ═══════════════════════════════

def test_chain_without_bfcache_restores_saved_scroll(server, nobf, ctxs):
    """bfcache 없음 — 1 → '2' → '3' → 뒤로 → 뒤로. 각 복귀는 새 로드라 nc:scroll 저장값만으로 자리를 찾는다(HEAD: 줄어든 값)."""
    _seed()
    pg = _phone(nobf, 360, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    L = _link(pg, "2"); y1 = _at(pg, L); L.tap(); _wait_url(pg, r"page=2")
    L3 = _link(pg, "3"); y2 = _at(pg, L3); L3.tap(); _wait_url(pg, r"page=3")
    pg.go_back(wait_until="load"); _ok(_restored(pg, bfcache=False), y2, "새 로드 3 → 뒤로 = 2페이지")
    pg.go_back(wait_until="load"); _ok(_restored(pg, bfcache=False), y1, "새 로드 → 뒤로 = 1페이지")


def test_public_phone_frame_iframe_page_link_then_back(server, bf, ctxs):
    """PC 공개 뷰(X-Forwarded-For → /static/frame.html 폰 프레임 iframe). iframe 은 bfcache 대상이 아니라 뒤로 = 새 로드.
    HEAD 는 저장값이 줄어 있어 297 근처로 떨어졌다(운영 DB 사본 실측 4224 → 297)."""
    _seed()
    pg = _desk(bf, ctxs, headers={"X-Forwarded-For": "203.0.113.9"}).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    pg.wait_for_url(re.compile(r"frame\.html"), timeout=10000)
    fr = None
    for _ in range(50):
        fr = next((f for f in pg.frames if f != pg.main_frame and "/vehicles" in f.url), None)
        if fr:
            break
        time.sleep(0.1)
    assert fr, "폰 프레임 iframe 없음"
    fr.wait_for_load_state("load")
    L = fr.locator('#listResults a[href*="page="]').filter(has_text=re.compile(r"^\s*2\s*$")).locator("visible=true").first
    L.scroll_into_view_if_needed(); pg.wait_for_timeout(200)
    y = _st(fr)["top"]
    L.click()
    for _ in range(100):
        if "page=2" in fr.url:
            break
        time.sleep(0.1)
    pg.wait_for_timeout(800)
    pg.go_back(wait_until="commit")
    pg.wait_for_timeout(1500)
    fr = next(f for f in pg.frames if f != pg.main_frame)
    s = _st(fr)
    assert s["navtype"] == "back_forward" and s["ps"] == [False], f"iframe 뒤로 = 새 로드: {s}"
    _ok(s, y, "PC 프레임 '2' → 뒤로")
