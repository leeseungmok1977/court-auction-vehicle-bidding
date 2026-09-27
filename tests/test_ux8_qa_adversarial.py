"""UX-8 적대적 반증(qa, 지시서 2026-09-27-07) — 필터 카드 접기의 상태 기계·첫 페인트·손실 검증.

보고서: reports/2026-09-27-ux8-qa.md. 앵커 문자열만 쓴다(오프셋 창 없음).

xfail(strict=True) 는 **재현된 결함**이다 — 고치면 XPASS 로 빨간불이 켜지니 그때 표식을 뗀다.
  → r2(지시서 2026-09-27-09, frontend)에서 B-1·B-2 를 고쳐 네 건 모두 XPASS(strict) 로 빨간불이 켜진 것을 확인하고 표식을 뗐다.
    B-1 = 기억 키에서 sort=recent 제외, B-2 = 결정 스크립트를 details 앞 MutationObserver 로(자리 이동만으로는 CPU 4x 에서 닫힌 프레임이 남았다).
  · B-1 기억 키가 기본 정렬(`sort=recent`)을 조합의 일부로 센다 → 정렬 없는 진입 링크(홈 차종 카드
    `?segment=…&upcoming=30`·대시보드 버킷 `?bucket=…`)에서 펼친 뒤 2페이지·[적용](무변경)이면 다시 접힌다(원칙 ④ 위반).
  · B-2 넓은 폭(≥ 640)은 서버가 닫힌 채 그리고 뒤 인라인 스크립트가 연다 → 파서가 둘 사이에서 양보하면
    빈 띠(닫힌 카드) 프레임이 그려진다(원칙 ② "첫 페인트 전" 위반). 분할 전송으로 결정적으로 재현한다.
"""
from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, quote, urlsplit

import pytest
from starlette.testclient import TestClient

from web import db

TODAY = date.today()
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964, 8996, 8917, 8723, 8724, 8725, 8726}
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1, "mileage_km": 50_000,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}
HY = quote("현대")
COND = "/vehicles?maker=" + HY + "&price=1000-2000&year_min=2018&sort=sale_date"
# 홈 차종 카드 링크 원문과 같은 꼴 — sort 가 없다(web/templates 의 `?segment=…&upcoming=30`)
SEG = "/vehicles?segment=sedan&upcoming=30"
XSS = '<img src=x onerror=alert(1)>"\''


def _d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def _seed(n=30):
    db.init_db()
    for i in range(n):
        db.upsert_vehicle(dict(BASE, id=f"Q{i:02d}", case_no=f"2026타경5{i:04d}", model="쏘나타(SONATA)", maker="현대",
                               sale_date=_d(3 + i % 25), court="수원지방법원"))


def _key(url: str) -> str:
    """인라인 스크립트 key() 와 같은 규칙(page·빈 값·기본 정렬 sort=recent 제외, 키 정렬) — 파이썬 재현. r2 에서 기본 정렬 제외가 더해졌다(B-1)."""
    return "&".join(sorted(f"{k}={v}" for k, v in parse_qsl(urlsplit(url).query)
                           if v != "" and k != "page" and not (k == "sort" and v == "recent")))


def _key_r1(url: str) -> str:
    """r1 규칙(page·빈 값만 제외) — B-1 의 전제를 사실로 남기려고 둔다."""
    return "&".join(sorted(f"{k}={v}" for k, v in parse_qsl(urlsplit(url).query) if v != "" and k != "page"))


# ═════════════════════════════ 1. 템플릿(HTTP) ═════════════════════════════

@pytest.fixture
def client():
    import web.app as A
    return TestClient(A.app)


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.text


def test_b1_precondition_pagination_links_add_default_sort_to_sortless_entry(client):
    """B-1 의 전제(사실 고정): 정렬 없는 진입 URL 의 페이지 링크는 `sort=recent` 를 싣는다 → 인라인 스크립트의 기억 키가 달라진다.
    서버 qs 를 바꾸거나 key() 가 기본 정렬을 빼거나, 어느 쪽으로 고쳐도 이 테스트가 아니라 아래 xfail 이 풀려야 한다."""
    _seed(30)
    h = _get(client, SEG)
    m = re.search(r'href="(/vehicles\?[^"]*page=2)"', h)
    assert m, "2페이지 링크"
    href = m.group(1).replace("&amp;", "&")
    assert "sort=recent" in href and "sort=" not in SEG
    assert _key_r1(SEG) != _key_r1(href), (_key_r1(SEG), _key_r1(href))     # r1 규칙이면 다른 조합이 된다(B-1 원인)
    assert _key(SEG) == _key(href), (_key(SEG), _key(href))                 # r2 규칙(기본 정렬 제외) — 같은 조합


def test_fold_row_escapes_exactly_once(client):
    """접힌 칩 줄은 같은 매크로의 두 번째 렌더다 — `|trim` 을 거친 뒤에도 Markup 이라 이중·미이스케이프가 없어야 한다."""
    _seed(3)
    h = _get(client, "/vehicles?q=" + quote(XSS))
    i = h.index('<div id="listFilterChips"')
    row = h[i:h.index("</div>", i)]
    assert "<img src=x" not in h, "미이스케이프"
    assert "&lt;img src=x onerror=alert(1)&gt;" in row, row
    assert "&amp;lt;" not in row and "&amp;#34;" not in row, "이중 이스케이프"


@pytest.mark.parametrize("url", [
    COND, "/vehicles?q=" + quote("쏘나타") + "&date=2026-09-01&court=" + quote("수원지방법원")
    + "&upcoming=30&cond=damaged&price=1000-2000&year_min=2018&km_max=100000",
])
def test_no_duplicate_ids_with_two_chip_renders(client, url):
    """매크로를 두 번 렌더해도 id 가 겹치지 않는다(칩에 id 를 달면 접힌 줄과 카드 안에서 중복된다)."""
    _seed(3)
    ids = re.findall(r'\bid="([^"]+)"', _get(client, url))
    assert not sorted({i for i in ids if ids.count(i) > 1})


# ═════════════════════════════ 2. 브라우저 ═════════════════════════════

def _free_port() -> int:
    for _ in range(30):
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


def _split_at(body: bytes) -> int:
    """끊는 자리 = 목록 필터 카드의 `</details>` 바로 뒤(카드 내용은 전부 파싱됐고 그 뒤 인라인 스크립트는 아직). 고치는 방식
    (스크립트를 카드 첫 자식으로 옮기기 · 넓은 폭은 CSS 로 내용 보이기 · 서버가 열고 좁은 폭만 CSS 로 접기)과 무관하게 같은 자리다."""
    i = body.find(b'<details id="listFilter"')
    j = body.find(b"</details>", i) if i >= 0 else -1
    return j + len(b"</details>") if j >= 0 else -1


@pytest.fixture(scope="module")
def split_server(server):
    """분할 전송 프록시 — /vehicles HTML 을 목록 필터 카드 `</details>` **바로 뒤**에서 끊고 0.8초 쉰 뒤 나머지를 보낸다.
    네트워크 세그먼트 경계(또는 CPU 가 느린 폰에서 파서 양보)가 카드와 그 뒤 인라인 스크립트 사이에 떨어진 경우의 결정적 재현."""
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        def do_GET(self):
            try:
                r = urllib.request.urlopen(server + self.path)
                status, hdrs, body = r.status, r.getheaders(), r.read()
            except urllib.error.HTTPError as e:
                status, hdrs, body = e.code, list(e.headers.items()), e.read()
            self.send_response(status)
            for k, v in hdrs:
                if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            i = _split_at(body) if self.path.startswith("/vehicles") else -1
            if i > 0:
                self.wfile.write(body[:i]); self.wfile.flush(); time.sleep(0.8)
                self.wfile.write(body[i:])
            else:
                self.wfile.write(body)
            self.wfile.flush()

    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


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
# 매 rAF(= 그 프레임의 렌더 직전) 카드 **내용이 보였는가**(open 이거나, 닫혀도 CSS 로 폼이 그려지는가 — checkVisibility: 닫힌 details 내용은
# content-visibility 로 건너뛰어 false. getBoundingClientRect 는 닫혀도 높이를 돌려줘 못 쓴다). 카드 없음 = -1.
FRAME_LOG = """
window.__f = [];
(function tick(){ var d = document.getElementById('listFilter'), f = d && d.querySelector('form');
  window.__f.push(!d ? -1 : ((d.open || (f && f.checkVisibility())) ? 1 : 0));
  if (window.__f.length < 600) requestAnimationFrame(tick); })();
"""


def _phone(browser, w=390, extra=()):
    ctx = browser.new_context(viewport={"width": w, "height": 844}, device_scale_factor=1, locale="ko-KR", is_mobile=True, has_touch=True)
    ctx.add_init_script(NO_SPLASH)
    for s in extra:
        ctx.add_init_script(s)
    return ctx


def _desk(browser, w, extra=()):
    ctx = browser.new_context(viewport={"width": w, "height": 900}, device_scale_factor=1, locale="ko-KR")
    ctx.add_init_script(NO_SPLASH)
    for s in extra:
        ctx.add_init_script(s)
    return ctx


def _open(pg):
    return pg.evaluate("document.getElementById('listFilter').open")


def _tap_summary(pg):
    pg.locator("#listFilter > summary").tap()
    pg.wait_for_timeout(150)


def _nav(pg, loc):
    with pg.expect_navigation(wait_until="load"):
        loc.tap()
    pg.wait_for_timeout(250)


def test_b1_sortless_entry_expanded_stays_expanded_on_page_2(server, browser):
    _seed(30)
    ctx = _phone(browser); pg = ctx.new_page()
    try:
        pg.goto(server + SEG, wait_until="load")
        assert _open(pg) is False
        _tap_summary(pg)
        assert _open(pg) is True
        _nav(pg, pg.locator('#listResults a[href*="page=2"]').first)
        assert "page=2" in pg.url
        assert _open(pg) is True, f"같은 조합의 다음 페이지는 펼친 채여야 한다(④) — url={pg.url}"
    finally:
        ctx.close()


def test_b1_sortless_entry_apply_without_change_stays_expanded(server, browser):
    _seed(30)
    ctx = _phone(browser); pg = ctx.new_page()
    try:
        pg.goto(server + SEG, wait_until="load")
        _tap_summary(pg)
        _nav(pg, pg.locator("#listFilter form span.sm\\:hidden button"))
        assert _open(pg) is True, f"무변경 [적용] = 같은 조합 — url={pg.url}"
    finally:
        ctx.close()


def test_sorted_entry_expanded_survives_page_2_back_forward(server, browser):
    """대조군: 정렬이 있는 진입(COND)은 ④ 대로 동작한다 — B-1 이 '기억 전체'가 아니라 키 정규화 문제임을 가른다."""
    _seed(30)
    ctx = _phone(browser); pg = ctx.new_page()
    try:
        pg.goto(server + COND, wait_until="load")
        _tap_summary(pg)
        _nav(pg, pg.locator('#listResults a[href*="page=2"]').first)
        assert _open(pg) is True
        pg.go_back(wait_until="load"); pg.wait_for_timeout(250)
        assert _open(pg) is True
        pg.go_forward(wait_until="load"); pg.wait_for_timeout(250)
        assert _open(pg) is True
    finally:
        ctx.close()


@pytest.mark.parametrize("raw", ["{bad json", '"str"', "1", "true", "[]", "null", '{"maker=기아":1}',
                                 "__KEY_STR__", "__KEY_TRUE__", "__KEY_2__"])
def test_polluted_memory_falls_back_to_rule_1_folded(server, browser, raw):
    """sessionStorage 오염값 → 기본 규칙 ①(접힘). 같은 키라도 값이 정확히 1 이 아니면 접힘. 페이지 오류 0."""
    _seed(3)
    k = _key(COND)
    raw = {"__KEY_STR__": json.dumps({k: "1"}), "__KEY_TRUE__": json.dumps({k: True}), "__KEY_2__": json.dumps({k: 2})}.get(raw, raw)
    ctx = _phone(browser); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    try:
        pg.goto(server + "/vehicles", wait_until="load")
        pg.evaluate("v => sessionStorage.setItem('nc:listFilterOpen', v)", raw)
        pg.goto(server + COND, wait_until="load")
        assert _open(pg) is False, raw
        assert not errs, errs
    finally:
        ctx.close()


def test_memory_positive_control_exact_key_opens(server, browser):
    _seed(3)
    ctx = _phone(browser); pg = ctx.new_page()
    try:
        pg.goto(server + "/vehicles", wait_until="load")
        pg.evaluate("v => sessionStorage.setItem('nc:listFilterOpen', v)", json.dumps({_key(COND): 1}))
        pg.goto(server + COND, wait_until="load")
        assert _open(pg) is True
    finally:
        ctx.close()


def test_keyboard_enter_on_summary_expands_and_is_remembered(server, browser):
    """키보드 사용자: summary 에 포커스 → Enter 로 펼침(click 이벤트가 나므로 기억도 쓴다)."""
    _seed(3)
    ctx = _phone(browser); pg = ctx.new_page()
    try:
        pg.goto(server + COND, wait_until="load")
        pg.focus("#listFilter > summary"); pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
        assert _open(pg) is True
        assert json.loads(pg.evaluate("sessionStorage.getItem('nc:listFilterOpen')")).get(_key(COND)) == 1
    finally:
        ctx.close()


@pytest.mark.parametrize("w,expect", [(639, False), (640, True)])
def test_boundary_639_640_desktop_context(server, browser, w, expect):
    """경계: 터치 아닌 창에서도 639 는 접힘·640 은 펼침(CSS max-sm 과 JS matchMedia 가 같은 경계)."""
    _seed(3)
    ctx = _desk(browser, w); pg = ctx.new_page()
    try:
        pg.goto(server + COND, wait_until="load")
        assert _open(pg) is expect
        vis = pg.evaluate("getComputedStyle(document.querySelector('#listFilter > summary')).display !== 'none'")
        assert vis is (not expect), "summary 는 좁은 폭에서만 보인다"
    finally:
        ctx.close()


@pytest.mark.parametrize("w", [320, 390])
def test_no_visible_duplicate_remove_link_folded_or_expanded(server, browser, w):
    """접힌 줄과 카드 안 칩 행이 같은 ✕ 링크를 **화면에 동시에** 보이지 않는다 — 접힘·펼침 둘 다. 320 첫 ✕ 는 페이드 앞(UX-4)."""
    _seed(3)
    url = "/vehicles?q=" + quote("쏘나타") + "&upcoming=30&cond=damaged&price=1000-2000&year_min=2018&km_max=100000"
    js = """() => {
      const d = document.getElementById('listFilter');
      const vis = e => { const r = e.getBoundingClientRect(); if (!r.width || !r.height) return false;
        for (let n = e; n; n = n.parentElement) { if (getComputedStyle(n).display === 'none') return false; }
        return !(d && !d.open && d.contains(e) && !e.closest('summary')); };
      const k = [...document.querySelectorAll('a')].filter(a => a.textContent.includes('✕') && vis(a)).map(a => a.getAttribute('href') + '|' + a.textContent.trim());
      const row = document.getElementById('listFilterChips'); let first = null, fade = null;
      if (row && vis(row)) { fade = row.getBoundingClientRect().right - 16; first = row.querySelector('a').getBoundingClientRect().right; }
      return {n: k.length, dup: k.filter((x, i) => k.indexOf(x) !== i), first, fade}; }"""
    ctx = _phone(browser, w); pg = ctx.new_page()
    try:
        pg.goto(server + url, wait_until="load")
        a = pg.evaluate(js)
        assert a["n"] == 6 and not a["dup"], a
        assert a["first"] is not None and a["first"] <= a["fade"], a
        _tap_summary(pg)
        b = pg.evaluate(js)
        assert b["n"] == 6 and not b["dup"] and b["first"] is None, b
    finally:
        ctx.close()


def test_a11y_tree_folded_exposes_disclosure_and_fold_chips_once(server, browser):
    """스크린리더: 접힘 = summary 가 DisclosureTriangle(expanded=false), 해제 ✕ 링크는 접힌 줄에서 한 번씩, 셀렉트는 트리 밖(표준 disclosure).
    펼침 = expanded=true, 셀렉트 6, ✕ 링크 중복 없음."""
    _seed(3)
    ctx = _phone(browser); pg = ctx.new_page()

    def ax():
        nodes = ctx.new_cdp_session(pg).send("Accessibility.getFullAXTree")["nodes"]
        role = lambda n: n.get("role", {}).get("value")
        name = lambda n: n.get("name", {}).get("value", "")
        xs = [name(n) for n in nodes if role(n) == "link" and not n.get("ignored") and "✕" in name(n)]
        dis = [n for n in nodes if role(n) == "DisclosureTriangle" and "검색 · 필터" in name(n)]
        exp = [p["value"].get("value") for p in (dis[0].get("properties", []) if dis else []) if p["name"] == "expanded"]
        combos = [n for n in nodes if role(n) == "combobox" and not n.get("ignored")]
        return xs, len(dis), exp, len(combos)

    try:
        pg.goto(server + COND, wait_until="load")
        xs, ndis, exp, nc = ax()
        assert ndis == 1 and exp == [False] and nc == 0, (ndis, exp, nc)
        assert len(xs) == 2 and len(set(xs)) == 2, xs
        _tap_summary(pg)
        xs, ndis, exp, nc = ax()
        assert ndis == 1 and exp == [True] and nc == 6, (ndis, exp, nc)
        assert len(xs) == len(set(xs)) == 2, xs
    finally:
        ctx.close()


def test_scroll_restore_happens_after_open_is_final(server, browser):
    """뒤로가기: base.html restore() 가 scrollTop 을 쓰는 순간 details.open 이 이미 최종값(펼침 기억)이다."""
    _seed(30)
    hook = """
    window.__rs = [];
    (function(){ var desc = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop');
      Object.defineProperty(Element.prototype, 'scrollTop', { configurable: true, get: desc.get,
        set: function(v){ if (this.id === 'appscroll') { var d = document.getElementById('listFilter'); window.__rs.push(d ? d.open : null); }
          return desc.set.call(this, v); } }); })();"""
    ctx = _phone(browser, extra=(hook,)); pg = ctx.new_page()
    try:
        pg.goto(server + COND, wait_until="load")
        _tap_summary(pg)
        card = pg.locator('#listResults a[href^="/vehicle/"] >> visible=true').nth(2)
        card.scroll_into_view_if_needed(); pg.wait_for_timeout(150)
        y = pg.evaluate("document.getElementById('appscroll').scrollTop")
        assert y > 0
        _nav(pg, card)
        pg.go_back(wait_until="load"); pg.wait_for_timeout(400)
        rs = pg.evaluate("window.__rs")
        assert rs and all(o is True for o in rs), rs
        assert pg.evaluate("document.getElementById('appscroll').scrollTop") == y
    finally:
        ctx.close()


@pytest.mark.parametrize("w", [640, 1440])
def test_b2_wide_first_paint_never_shows_closed_card_under_split_delivery(split_server, browser, w):
    _seed(3)
    ctx = _desk(browser, w, extra=(FRAME_LOG,)); pg = ctx.new_page()
    try:
        pg.goto(split_server + COND, wait_until="load"); pg.wait_for_timeout(200)
        frames = [x for x in pg.evaluate("window.__f") if x != -1]
        assert frames and _open(pg) is True
        assert 0 not in frames, f"내용 없는 빈 띠 프레임 {frames.count(0)}개 / 전체 {len(frames)}"
    finally:
        ctx.close()


def test_split_delivery_phone_default_never_shows_open_card(split_server, browser):
    """대조군: 폰 기본(접힘)은 서버 렌더 = 최종이라 분할 전송에서도 번쩍임 0(원칙 ① 이 지키는 경로)."""
    _seed(3)
    ctx = _phone(browser, extra=(FRAME_LOG,)); pg = ctx.new_page()
    try:
        pg.goto(split_server + COND, wait_until="load"); pg.wait_for_timeout(200)
        frames = [x for x in pg.evaluate("window.__f") if x != -1]
        assert frames and _open(pg) is False and 1 not in frames, frames[:20]
    finally:
        ctx.close()
