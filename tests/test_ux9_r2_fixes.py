"""UX-9 r2 — 수정 회차 (지시서 2026-09-27-62 r2: qa·디자인 반증 결과 반영).

대상 앵커(줄 번호 금지): web/templates/vehicles.html
  · 스켈레톤 IIFE — "var res=document.getElementById('listResults')" ~ 그 뒤 줄 첫머리의 "})();"
  · [적용] 변경 표시 IIFE — "function mark(on)" ~ 그 뒤 줄 첫머리의 "})();"
  · 페이지 이동 줄 — "{% if total_pages > 1 %}" 뒤 첫 "<nav"

무엇을 지키나(전부 HEAD 도 같던 기존 결함 — qa 반증 2026-09-27):
  R1   커밋 전 이동 중단(브라우저 X·ESC = CDP Page.stopLoading)은 문서를 떠나지 않아 pagehide 가 없다 → 스켈레톤 고착.
       Navigation API(navigate 이벤트의 signal abort)로 되돌린다. 다른 이동이 이어받은 abort(연타)는 되돌리지 않는다.
       기본 경로는 tests/test_ux9_qa_adversarial.py::test_stop_loading_before_commit_restores_list(strict xfail → 뗌).
  N3   [적용](제조사 기아) → 뒤로 = 셀렉트 '기아' · 목록 '현대' · 변경 표시 꺼짐. bfcache 켬·끔 둘 다.
       → 기준을 서버 값(복제 폼 reset)으로, [적용]으로 떠나면 pagehide 에서 폼을 서버 값으로 되돌린다.
       [적용] 없이 바꾼 값은 남기고 변경 표시를 켠다.
  QA-2 페이지 이동 줄이 nowrap 이라 overflow-hidden 카드에 '다음 ›' 가 잘렸다 — 큰글씨 320·360 1페이지만이 아니라
       일반 모드 5페이지 이후 390·430 도(운영 DB 사본 6폭×일반/큰글씨×4페이지 = 48 조합 중 22 조합). → flex-wrap + 낱말 nowrap.
  C1   주석이 디스크에 없는 보고서를 근거로 대지 않는다(CLAUDE.md 규칙 8) — vehicles.html 이 인용하는 reports/*.md 는 전부 있어야 한다.

⚠ 하네스 함정(구현·qa 파일 docstring 과 같다): Playwright 는 `--disable-back-forward-cache` 로 띄운다 → ignore_default_args 로 뺀다.
  기본 headless shell 은 그래도 bfcache 를 안 쓴다 → channel="chrome" 우선, 없으면 "chromium". 복귀마다 pageshow persisted 를 단언한다.
"""
import asyncio
import re
import socket
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from web import db

ROOT = Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964, 8996, 8917, 8853, 8854, 8871, 8872}
TODAY = date.today()
H = {320: 568, 360: 780, 390: 844}
HYUNDAI = "%ED%98%84%EB%8C%80"     # 현대
KIA_Q = b"maker=%EA%B8%B0%EC%95%84"  # 기아(폼 제출 쿼리)

BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1, "mileage_km": 50_000,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}


def _seed(n=30):
    """30건 = 3페이지(VEHICLES_PAGE_SIZE 12). 기아 = 5건마다 1건(현대 24건 = 조건 목록 2페이지)."""
    db.init_db()
    for i in range(n):
        maker, model = ("기아", "쏘렌토(SORENTO)") if i % 5 == 0 else ("현대", "쏘나타(SONATA)")
        db.upsert_vehicle(dict(BASE, id=f"R{i:03d}", case_no=f"2026타경7{i:04d}", model=model, maker=maker,
                               sale_date=(TODAY + timedelta(days=3 + i % 20)).isoformat()))


# ═══════════════════════════════════ A. 템플릿(소스 앵커) ═══════════════════════════════════

def _block(start, end="\n})();"):
    """IIFE 의 끝 = 줄 첫머리의 '})();' — 안쪽 즉시 실행 함수(기준 계산)의 '})();' 에서 끊기지 않게."""
    i = LIST_TPL.index(start)
    return LIST_TPL[i:LIST_TPL.index(end, i)]


def test_skeleton_reverts_on_aborted_navigation_only_if_last():
    s = _block("var res=document.getElementById('listResults')")
    assert "window.navigation" in s and "addEventListener('navigate'" in s, "R1: Navigation API navigate 이벤트를 듣는다"
    assert re.search(r"e\.signal\.addEventListener\('abort'", s), "R1: 중단 = navigate 이벤트 signal 의 abort"
    assert re.search(r"setTimeout\(function\(\)\{\s*if\(last===me\)\s*undo\(\);", s), \
        "R1: 다른 이동이 이어받은 abort(연타)는 되돌리지 않는다 — 한 틱 미뤄 마지막 이동인지 본다"
    assert re.search(r"addEventListener\('pagehide',\s*undo,\s*true\)", s), "UX-9 r1 처방 유지"


def test_apply_indicator_baseline_is_server_values_and_resets_on_leave():
    s = _block("function mark(on)")
    assert "f.cloneNode(true)" in s and "c.reset()" in s, "N3 ⑴: 기준 = 복제 폼 reset(HTML 기본값 = 서버 값)"
    assert "var base=ser();" not in s, "N3: 로드 때 폼 값(뒤로 오면 되살린 값)을 기준으로 잡지 않는다"
    assert "addEventListener('pageshow', function(){ mark(false); })" not in s, "N3: pageshow 에서 무조건 떼지 않는다"
    assert "addEventListener('pageshow', sync)" in s, "N3 ⑶: pageshow 에서 기준과 다시 비교"
    assert re.search(r"addEventListener\('pagehide',\s*function\(\)\{\s*if\(!sent\)\s*return;\s*sent=false;\s*f\.reset\(\);", s), \
        "N3 ⑵: [적용]으로 떠날 때만 폼을 서버 값으로 되돌린다"


def test_pager_row_wraps_and_labels_stay_on_one_line():
    i = LIST_TPL.index("{% if total_pages > 1 %}")
    nav = LIST_TPL[LIST_TPL.index("<nav", i):LIST_TPL.index("</nav>", i)]
    head = nav[:nav.index(">")]
    assert "flex-wrap" in head, "QA-2: 항목 단위로 다음 줄로 넘긴다(nowrap 이면 카드에 잘린다)"
    for lbl in ("‹ 이전", "다음 ›"):
        tags = re.findall(r'<(?:a|span)[^>]*class="([^"]*)"[^>]*>' + re.escape(lbl) + "<", nav)
        assert len(tags) == 2 and all("whitespace-nowrap" in c for c in tags), f"QA-2: '{lbl}' 링크·비활성 둘 다 한 줄: {tags}"


def test_cited_reports_exist_on_disk():
    """C1(CLAUDE.md 규칙 8): 주석이 가리키는 보고서가 없으면 근거가 아니라 거짓 포인터다(r1 은 없는 파일을 인용했다)."""
    cited = sorted(set(re.findall(r"reports/[A-Za-z0-9_./-]+\.md", LIST_TPL)))
    missing = [c for c in cited if not (ROOT / c).is_file()]
    assert not missing, f"vehicles.html 이 인용하는데 디스크에 없는 보고서: {missing}"


# ═══════════════════════════════════ B. 동작(Playwright) ═══════════════════════════════════

def _free_port() -> int:
    for _ in range(20):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


SLOW = {"match": b"", "sec": 0.0}   # 쿼리에 match 가 들어간 /vehicles 응답을 sec 초 늦춘다(서버 쪽 느린 망)


def _with_delay(app):
    async def wrapped(scope, receive, send):
        if SLOW["sec"] and scope["type"] == "http" and scope["path"] == "/vehicles" and SLOW["match"] in scope.get("query_string", b""):
            await asyncio.sleep(SLOW["sec"])
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
    opened = []
    yield opened
    SLOW.update(match=b"", sec=0.0)
    for c in opened:
        try:
            c.close()
        except Exception:
            pass


PROBE = """
try{sessionStorage.setItem('nc_splash','1')}catch(e){}
window.__ps = [];
window.addEventListener('pageshow', function(e){ window.__ps.push(e.persisted); });
"""
STATE = """() => {
  const r = document.getElementById('listResults'), s = document.getElementById('listSkeleton'), a = document.getElementById('appscroll'),
        f = document.querySelector('#listFilter form');
  const vis = e => !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0;
  const nav = performance.getEntriesByType('navigation')[0];
  return {results: vis(r), skeleton: vis(s), top: a.scrollTop, maker: f ? f.maker.value : null, q: f ? f.q.value : null,
          dirty: f ? [...f.querySelectorAll('button.btn-ghost:not([type])')].map(b => b.classList.contains('is-dirty')) : null,
          ps: (window.__ps || []).slice(), navtype: nav ? nav.type : null, url: decodeURIComponent(location.pathname + location.search)};
}"""


def _phone(browser, w, ctxs, large=False, sw="allow"):
    ctx = browser.new_context(viewport={"width": w, "height": H[w]}, device_scale_factor=1, locale="ko-KR",
                              is_mobile=True, has_touch=True, service_workers=sw)
    if large:
        ctx.add_init_script("try{localStorage.setItem('naechaget:large','1')}catch(e){}")
    ctx.add_init_script(PROBE)
    ctxs.append(ctx)
    return ctx


def _st(pg):
    for _ in range(50):
        try:
            return pg.evaluate(STATE)
        except Exception:        # 복원 직후 실행 컨텍스트 교체
            time.sleep(0.1)
    return pg.evaluate(STATE)


def _back(pg, bfcache):
    pg.go_back(wait_until="commit")
    t0 = time.time()
    while time.time() - t0 < 6:
        try:
            ps = pg.evaluate("() => window.__ps || null")
            if ps and (ps[-1] is True or (not bfcache and time.time() - t0 > 1.0)):
                break
        except Exception:
            pass
        time.sleep(0.05)
    pg.wait_for_timeout(400)
    s = _st(pg)
    if bfcache:
        assert s["ps"] and s["ps"][-1] is True, f"bfcache 복원이 아니다(공허 통과 방지): {s}"
    else:
        assert s["ps"] == [False] and s["navtype"] == "back_forward", f"새 로드(back_forward)여야 한다: {s}"
    return s


def _open_filter(pg):
    if not pg.evaluate("() => document.getElementById('listFilter').open"):
        pg.locator("#listFilter > summary").tap(); pg.wait_for_timeout(250)


def _apply_btn(pg):
    return pg.locator("#listFilter form button.btn-ghost:not([type])").locator("visible=true").first


def _link(pg, which):
    loc = pg.locator('#listResults a[href*="page="]')
    loc = loc.filter(has_text=which) if which in ("다음", "이전") else loc.filter(has_text=re.compile(r"^\s*%s\s*$" % which))
    return loc.locator("visible=true").first


# ── N3 ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bfcache", [True, False], ids=["bfcache", "newload"])
@pytest.mark.parametrize("start,server_maker", [("/vehicles", ""), (f"/vehicles?maker={HYUNDAI}", "현대")], ids=["all", "hyundai"])
def test_apply_then_back_select_matches_list(server, bf, nobf, ctxs, bfcache, start, server_maker):
    """N3 — [적용](기아) → 뒤로 = 셀렉트가 목록의 조건(서버 값)과 같고 변경 표시는 꺼짐. HEAD 는 셀렉트 '기아'로 남았다."""
    _seed()
    pg = _phone(bf if bfcache else nobf, 390, ctxs).new_page()
    pg.goto(server + start, wait_until="load")
    _open_filter(pg)
    pg.select_option("#listFilter select[name=maker]", "기아")
    assert _st(pg)["dirty"] == [True, True], "전제: 바꾸면 변경 표시"
    _apply_btn(pg).tap()
    pg.wait_for_url(re.compile("maker=%EA%B8%B0"), wait_until="commit"); pg.wait_for_load_state("load"); pg.wait_for_timeout(200)
    s = _back(pg, bfcache)
    assert s["maker"] == server_maker, f"N3: 셀렉트 = 이 목록에 걸린 조건({server_maker!r}): {s}"
    assert s["dirty"] == [False, False], f"N3: 폼 = 서버 값이면 변경 표시 꺼짐: {s}"
    assert s["results"] and not s["skeleton"], s


@pytest.mark.parametrize("bfcache", [True, False], ids=["bfcache", "newload"])
def test_unapplied_edit_survives_leave_and_marks_dirty(server, bf, nobf, ctxs, bfcache):
    """N3 ⑶ — [적용] 없이 바꾼 채 '2' → 뒤로 = 바꾼 값은 남고 변경 표시가 켜진다(HEAD 는 셀렉트 '기아' + 표시 꺼짐)."""
    _seed()
    pg = _phone(bf if bfcache else nobf, 390, ctxs).new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    pg.select_option("#listFilter select[name=maker]", "기아")
    L = _link(pg, "2"); L.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
    L.tap(); pg.wait_for_url(re.compile("page=2"), wait_until="commit"); pg.wait_for_load_state("load"); pg.wait_for_timeout(200)
    s = _back(pg, bfcache)
    assert s["maker"] == "기아" and s["dirty"] == [True, True], f"N3 ⑶: 바꾼 값 + 변경 표시: {s}"


def test_fresh_load_indicator_off_across_conditions(server, bf, ctxs):
    """N3 ⑴ 회귀 — 기준을 복제 폼 reset 으로 바꿔도 새로 연 목록(숨은 칸·usepick·검색어 포함)은 변경 표시가 꺼져 있다."""
    _seed()
    pg = _phone(bf, 390, ctxs).new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    for q in ("", f"?maker={HYUNDAI}", "?q=%EC%8F%98%EB%82%98%ED%83%80", "?usepick=now", "?picks=1", "?sort=sale_date&upcoming=30",
              "?segment=suv", "?court=%EC%88%98%EC%9B%90%EC%A7%80%EB%B0%A9%EB%B2%95%EC%9B%90", "?sort=recent&page=2"):
        pg.goto(server + "/vehicles" + q, wait_until="load")
        assert _st(pg)["dirty"] == [False, False], f"새로 연 목록 {q!r}: 변경 표시 꺼짐"
    assert not errs, errs


# ── R1 ──────────────────────────────────────────────────────────────────────────────────

def test_stop_loading_after_apply_restores_list_and_keeps_edit(server, bf, ctxs):
    """R1 — [적용] 제출 뒤 커밋 전 중단 = 목록이 보이고, 폼은 바꾼 값 + 변경 표시(아직 적용 안 됨)."""
    _seed()
    ctx = _phone(bf, 390, ctxs, sw="block"); pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg); cdp.send("Page.enable")
    pg.goto(server + "/vehicles", wait_until="load")
    pg.select_option("#listFilter select[name=maker]", "기아")
    SLOW.update(match=KIA_Q, sec=4.0)
    _apply_btn(pg).tap(no_wait_after=True)
    pg.wait_for_timeout(700)
    cdp.send("Page.stopLoading")
    pg.wait_for_timeout(1200)
    s = _st(pg)
    assert "maker=" not in s["url"], f"전제: 중단돼 원래 목록에 남아 있다: {s}"
    assert s["results"] and not s["skeleton"], f"R1: 중단 뒤 목록: {s}"
    assert s["maker"] == "기아" and s["dirty"] == [True, True], f"R1: 적용 안 된 값은 남고 표시가 켜져 있다: {s}"


SAMPLER = """
if (location.search.indexOf('page=') < 0) setInterval(function(){ try {
  var s = document.getElementById('listSkeleton'), r = document.getElementById('listResults'); if (!s || !r) return;
  var l = JSON.parse(sessionStorage.getItem('r2:samples') || '[]');
  l.push({t: Date.now(), sk: getComputedStyle(s).display !== 'none', res: getComputedStyle(r).display !== 'none'});
  sessionStorage.setItem('r2:samples', JSON.stringify(l.slice(-80)));
} catch (e) {} }, 50);
"""


def test_second_link_during_slow_navigation_keeps_skeleton(server, bf, ctxs):
    """R1 오탐 방지 — 느린 '2' 가 걸린 채 '3' 을 누르면 '2' 가 abort 되지만 새 이동이 이어받았다 → 목록이 번쩍 다시 나오면 안 된다.
    측정: 페이지 안 기록기(50ms)를 다음 화면에서 읽는다(이동 중 evaluate 는 커밋까지 막힌다 — test_ux9_bfcache_list 의 함정 설명)."""
    _seed()
    ctx = _phone(bf, 390, ctxs); ctx.add_init_script(SAMPLER); pg = ctx.new_page()
    pg.goto(server + "/vehicles", wait_until="load")
    _link(pg, "2").scroll_into_view_if_needed(); pg.wait_for_timeout(250)
    SLOW.update(match=b"page=", sec=2.0)
    t0 = pg.evaluate("() => Date.now()")
    pg.evaluate("""() => { const f = n => [...document.querySelectorAll('#listResults a[href*="page=' + n + '"]')]
                                         .find(x => x.offsetParent && x.textContent.trim() === String(n));
                           const a = f(2), b = f(3); setTimeout(() => a.click(), 0); setTimeout(() => b.click(), 600); }""")
    pg.wait_for_url(re.compile(r"page=3"), wait_until="commit", timeout=20000)
    samples = [x for x in pg.evaluate("() => JSON.parse(sessionStorage.getItem('r2:samples') || '[]')") if x["t"] > t0]
    assert len(samples) >= 20, f"느린 망 전제(1초 이상 1페이지에 머묾): {len(samples)}개"
    shown_list = [x for x in samples[1:] if x["res"]]
    assert not shown_list, f"다른 이동이 이어받은 abort 에 목록을 되살리면 안 된다: {len(shown_list)}/{len(samples)}"


# ── QA-2 ────────────────────────────────────────────────────────────────────────────────

PAGER = """() => {
  const nav = [...document.querySelectorAll('#listResults nav')].find(n => n.offsetParent);
  const card = nav.closest('.overflow-hidden').getBoundingClientRect();
  const it = [...nav.children].map(x => { const q = x.getBoundingClientRect();
    return {t: x.textContent.trim(), r: q.right, h: Math.round(q.height), cy: Math.round((q.top + q.bottom) / 2)}; });
  const nums = it.filter(x => /^[0-9]+$/.test(x.t)).map(x => x.h);
  return {vw: innerWidth, cardR: card.right, items: it, numH: Math.max(...nums), rows: new Set(it.map(x => Math.round(x.cy / 8))).size};
}"""


@pytest.mark.parametrize("large", [True, False], ids=["large", "normal"])
@pytest.mark.parametrize("w", [320, 360, 390])
@pytest.mark.parametrize("page", [1, 5])
def test_pager_next_is_inside_card(server, bf, ctxs, large, w, page):
    """QA-2 — '다음 ›' 우변 ≤ 카드 우변 ≤ 뷰포트, 이전/다음 낱말은 한 줄(숫자 칸과 같은 높이).
    HEAD: 큰글씨 320·360 1페이지(백로그 QA-2)와 5페이지 전 폭에서 잘렸다(120건 픽스처 10페이지 — 5페이지 = ‹ 1 … 3–7 … 10 ›)."""
    _seed(120)
    pg = _phone(bf, w, ctxs, large=large).new_page()
    pg.goto(server + f"/vehicles?sort=recent&page={page}", wait_until="load")
    m = pg.evaluate(PAGER)
    nxt = next(x for x in m["items"] if "다음" in x["t"])
    assert nxt["r"] <= m["cardR"] + 0.5 <= m["vw"] + 0.5, f"QA-2: '다음 ›' 가 카드 안({w} {'큰글씨' if large else '일반'} {page}p): {m}"
    labels = [x["h"] for x in m["items"] if "이전" in x["t"] or "다음" in x["t"]]
    assert labels and all(h <= m["numH"] for h in labels), f"QA-2: '‹ 이전'·'다음 ›' 가 두 줄로 찌그러지면 안 된다: {m}"
    if large and w == 320 and page == 5:
        assert m["rows"] >= 2, f"공허 통과 방지: 이 조합은 한 줄에 안 들어가 줄바꿈을 밟아야 한다: {m}"


def test_pager_stays_single_row_on_desktop(server, bf, ctxs):
    """QA-2 회귀 — 넓은 폭(1440 관리자 뷰)은 전처럼 한 줄."""
    _seed(120)
    ctx = bf.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ko-KR")
    ctx.add_init_script(PROBE); ctxs.append(ctx)
    pg = ctx.new_page()
    for page in (1, 5):
        pg.goto(server + f"/vehicles?sort=recent&page={page}", wait_until="load")
        m = pg.evaluate(PAGER)
        assert m["rows"] == 1, f"1440 {page}p 한 줄: {m}"
