"""UX-1~5 묶음 — QA 적대적 반증 테스트 (지시서 2026-09-26-24 / qa-engineer).

frontend·backend 테스트(tests/test_ux1_ux4_form_and_chips.py · test_ux2_ux5_nav_state.py · test_ux3_sort_rules.py)가 **보지 않은 틈**만
본다. 운영 DB 사본(1,418행) 실측에서 통과한 것을 tmp DB 로 고정하고, 실측에서 드러난 기존 틈 3건은 strict xfail 로 표식한다
(고치면 빨간불로 알리므로 그때 표식을 지운다 — FEAT-1 qa ⑥ 과 같은 방식).
  ① 오늘 경계(운영 사본에는 sale_date = 오늘 행이 0 이라 공허했다): 오늘 기일은 미래 블록 **첫 행**이고 구분 줄은 그 뒤 첫 과거 행 앞.
  ② 칩 ✕ 를 **실제로 따라가** 그 키 하나만 빠지고 나머지 12키가 남으며 총수가 줄지 않는다(날짜·결과·법원(다중)·검색어·가격대·입찰예정·검사경과).
  ③ 탭 복귀 저장값(nc:lastList) 적대 주입 7종 → 항상 /vehicles (Playwright, 브라우저 없으면 skip). 접두 검사의 약점(`/vehicles/../admin` 이
     같은 출처 /admin 으로 감)은 같은 출처 스크립트만 쓸 수 있는 저장소라 차단 항목이 아니다 — 여기서는 외부 이탈·스킴 주입만 단정한다.
  ④ 기존 틈(이 묶음 무관, HEAD 도 동일): `all=1` 진입 뒤 [적용]이 all 을 버림 · 검색 저장 라벨이 date 를 안 읽음 ·
     frame.html 해시 가드가 `/\\evil.com` 을 못 거름(브라우저가 `\\`→`/` 로 정규화해 `//evil.com`).
     → 3차(지시서 2026-09-26-26)에서 셋 다 고쳐 strict xfail 표식을 뗐다(단정 원문 그대로). 동작 단정은 tests/test_ux_round3.py.
검사는 전부 앵커 문자열 — 줄 번호·오프셋 창 없음.
"""
import html as html_mod
import json
import re
import socket
import threading
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from starlette.testclient import TestClient

from web import db

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
FRAME = (ROOT / "web/static/frame.html").read_text(encoding="utf-8")
_PUBLIC = {"x-forwarded-for": "203.0.113.9"}
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931}
TODAY = date.today()


def _d(n):
    return (TODAY + timedelta(days=n)).isoformat()


BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기", "maker": "현대", "model": "쏘나타(SONATA)"}


def _seed(rows):
    db.init_db()
    for i, r in enumerate(rows):
        db.upsert_vehicle(dict(BASE, case_no=f"2026타경5{i:04d}", **r))


@pytest.fixture
def client():
    import web.app as A
    return TestClient(A.app, headers=_PUBLIC)


def _total(h):
    m = re.search(r"window\.NC_LIST_TOTAL=(\d+);", h)
    assert m, "NC_LIST_TOTAL 없음"
    return int(m.group(1))


def _card_seq(h):
    sec = h[h.index('<div class="lg:hidden divide-y divide-line">'):]
    j = sec.find('<div id="listSkeleton"')
    sec = sec[:j] if j > 0 else sec
    return ["SPLIT" if m.group(1) else m.group(2) for m in re.finditer(r'(data-sale-split)|<a href="/vehicle/([^"]+)" class="block', sec)]


# ── ① 오늘 경계 ───────────────────────────────────────────────────────────────

def test_today_is_first_of_upcoming_block_and_split_sits_before_first_past(client):
    """오늘·+1·+3 / −1·−2 → 카드 순서 [오늘, +1, +3, −1, −2], 구분 줄은 인덱스 3 앞, sale_split 3분류 수가 맞는다."""
    _seed([{"id": "T0", "sale_date": _d(0)}, {"id": "T1", "sale_date": _d(1)}, {"id": "T3", "sale_date": _d(3)},
           {"id": "P1", "sale_date": _d(-1)}, {"id": "P2", "sale_date": _d(-2)}])
    r = client.get("/vehicles?sort=sale_date")
    assert r.status_code == 200
    seq = _card_seq(r.text)
    assert seq == ["T0", "T1", "T3", "SPLIT", "P1", "P2"], seq
    ss = r.context["sale_split"]
    assert ss == {"upcoming": 3, "past": 2, "undated": 0, "page_first_past_idx": 3}
    assert r.text.count("<tr data-sale-split") == 1 and r.text.count("<div data-sale-split") == 1


def test_today_only_rows_have_no_split_line(client):
    _seed([{"id": "T0", "sale_date": _d(0)}, {"id": "T0b", "sale_date": _d(0)}])
    r = client.get("/vehicles?sort=sale_date")
    assert _card_seq(r.text) == ["T0", "T0b"]
    assert r.context["sale_split"]["page_first_past_idx"] is None and r.context["sale_split"]["upcoming"] == 2


# ── ② 칩 ✕ 를 따라가 그 조건만 빠진다 ──────────────────────────────────────────

FULL = {"judgment": "유찰 대기", "maker": "현대", "q": "쏘나타", "sort": "sale_date", "upcoming": "30", "result": "유찰",
        "status": "완료", "cond": "insp_expired", "date": _d(2), "court": "수원지방법원,인천지방법원", "segment": "sedan",
        "price": "1000-2000"}
CHIP_TITLES = {"날짜 필터 해제": "date", "결과 필터 해제": "result", "법원 필터 해제": "court", "검색어 해제": "q", "가격대 필터 해제": "price"}


def _chips(h):
    out = []
    for m in re.finditer(r'<a href="([^"]*)"([^>]*)>(.*?)</a>', h, re.S):
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(3))).strip()
        if txt.endswith("✕"):
            t = re.search(r'title="([^"]*)"', m.group(2))
            out.append((txt, html_mod.unescape(m.group(1)), t.group(1) if t else ""))
    return out


def test_each_new_chip_x_drops_exactly_its_key_and_total_does_not_shrink(client):
    """12키를 전부 실은 URL(모수 1건: 수원·검사경과·유찰·1,000~2,000만·세단·기일 +2). 칩 7종(날짜·결과·법원 2곳·검색어·가격대·입찰예정·검사 경과)
    각각의 href 를 **실제로 열어** 그 키만 빠지고 나머지 11키가 그대로이며 총수 ≥ 1 인지 본다. FULL 이 0건이면 공허하므로 먼저 단언."""
    _seed([{"id": "M1", "sale_date": _d(2), "auction_result": "유찰", "inspection_to": _d(-10), "model": "쏘나타(SONATA)"},
           {"id": "M2", "sale_date": _d(2), "auction_result": "유찰", "inspection_to": _d(-10), "court": "인천지방법원", "model": "쏘나타(SONATA)"},
           {"id": "O1", "sale_date": _d(2), "court": "대구지방법원", "model": "그랜저(GRANDEUR)"}])
    r = client.get("/vehicles?" + urlencode(FULL))
    assert r.status_code == 200
    t0 = _total(r.text)
    assert t0 >= 1, "픽스처가 FULL 조건을 통과해야 한다(공허 통과 방지)"
    chips = _chips(r.text)
    seen = set()
    for txt, href, title in chips:
        key = CHIP_TITLES.get(title) or ("upcoming" if txt.startswith("입찰예정") else "cond" if txt.startswith("검사 경과") else None)
        if key is None:
            continue
        seen.add(key)
        qs = parse_qs(urlsplit(href).query, keep_blank_values=True)
        assert key not in qs, (txt, href)
        for k, v in FULL.items():
            if k != key:
                assert qs.get(k) == [v], (txt, k, qs.get(k))
        r2 = client.get(href)
        assert r2.status_code == 200 and _total(r2.text) >= t0, (txt, _total(r2.text), t0)
    assert seen == {"date", "result", "court", "q", "price", "upcoming", "cond"}, seen


# ── ③ 탭 복귀 저장값 적대 주입 (Playwright) ─────────────────────────────────────

def _free_port():
    for _ in range(50):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


@pytest.fixture
def server():
    uvicorn = pytest.importorskip("uvicorn")
    import web.app as A
    port = _free_port()
    cfg = uvicorn.Config(A.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True; th.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium 없음: {e}")
        yield b
        b.close()


HOSTILE = [json.dumps({"url": "javascript:alert(1)", "ts": 0}), json.dumps({"url": "//evil.example/x", "ts": 0}),
           json.dumps({"url": "http://evil.example/vehicles", "ts": 0}), json.dumps({"url": "/vehicle/2025타경1_1", "ts": 0}),
           "not json {", json.dumps({"url": "/vehicles?maker=a", "ts": "0"}), json.dumps({"url": "/vehicles?maker=a", "ts": 1})]


def test_hostile_last_list_values_always_land_on_plain_vehicles(server, browser):
    """ts 는 브라우저에서 Date.now() 로 덮어 '30분 안'으로 만든다(만료 때문에 통과하는 공허 통과 방지). 마지막 항목만 31분 전 만료 케이스."""
    _seed([{"id": "V1", "sale_date": _d(2)}])
    ctx = browser.new_context(viewport={"width": 390, "height": 640}, device_scale_factor=1, locale="ko-KR", has_touch=True)
    pg = ctx.new_page(); alerts = []
    pg.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
    for i, raw in enumerate(HOSTILE):
        pg.goto(server + "/calendar", wait_until="networkidle")
        expired = i == len(HOSTILE) - 1
        pg.evaluate("""([raw, expired]) => { let v = raw; try { const o = JSON.parse(raw); if (typeof o.ts === 'number') o.ts = Date.now() - (expired ? 31*60*1000 : 0); v = JSON.stringify(o); } catch (e) {}
                       sessionStorage.setItem('nc:lastList', v); }""", [raw, expired])
        pg.click('nav[class~="lg:hidden"] a[data-nav="vehicles"]'); pg.wait_for_load_state("networkidle")
        u = urlsplit(pg.url)
        assert u.path == "/vehicles" and u.query == "" and u.netloc.startswith("127.0.0.1"), (raw, pg.url)
    assert alerts == []
    ctx.close()


# ── ④ 기존 틈 — strict xfail (이 묶음 무관, HEAD 도 동일) ────────────────────────

def test_form_keeps_all_param_on_apply():
    """3차에서 고침 — hidden 은 request.query_params 에서 읽는다(all 은 라우트 컨텍스트에 없다)."""
    assert re.search(r'{% if all %}<input type="hidden" name="all"', LIST_TPL)


def test_saved_search_label_reads_date():
    """3차에서 고침 — date 부품 `YYYY-MM-DD 매각`(칩과 같은 낱말)."""
    fn = LIST_TPL[LIST_TPL.index("function ncSaveSearch"):]
    fn = fn[:fn.index("var label=")]
    assert "p.get('date')" in fn


def test_frame_hash_guard_rejects_backslash_or_checks_origin():
    """3차에서 고침 — `\\` 포함 거부 + new URL(...).origin 대조(둘 다)."""
    guard = FRAME[FRAME.index('if (!p.startsWith("/")'):FRAME.index('document.getElementById("f").src = p;')]
    assert ("\\\\" in guard) or ("new URL(" in guard and "origin" in guard)
