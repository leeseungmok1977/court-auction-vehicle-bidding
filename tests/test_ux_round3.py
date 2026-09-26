"""UX 묶음 3차 — 디자인 지적 3 + qa 회귀 1 + 기존 틈 3 (지시서 2026-09-26-26 / frontend-engineer).

2차(UX-2·5·1·3) 결과가 디자인 검수(reports/2026-09-26-ux-batch-design.md)와 qa 반증(reports/2026-09-26-ux-batch-qa.md)을 거쳐 나온
지적을 고정한다. 검사는 전부 **앵커 문자열** — 줄 번호·오프셋 창 없음.
  ① 요약 줄 날짜 = `{{ date }} 매각`(칩과 같은 ISO — 예전 `9/1 매각` 은 한 화면의 세 번째 날짜 문법)
  ② 구분 줄 문구 `지난 기일 N건 — 낙찰은 결과 참고 · 유찰은 다음 기일 대기`(카드·표가 `split_note` 한 원천)
  ③ 큰글씨 접힌 머리 = 첫 부품 + `외 N`(부품 단위 — 글자 단위 truncate 가 `1,000~2,…` 로 숫자 가운데를 잘랐다)
  ④ [적용] is-dirty 되돌림(Playwright: 셀렉트를 바꿨다 원래 값 → 채움 해제, 검색어도)
  ⑤ 상세 헤더 제목 열 sm:min-w-[12rem](Playwright 공개 뷰 640·700·768: h1 1줄, 액션 줄 넘침 0; 관리자 뷰도) — qa D-1 회귀 기준표 재현
  ⑥ `all` hidden(`request.query_params` — 라우트 컨텍스트에 all 이 없다), 값은 원값, 폼 제출 재현으로 모수 유지
  ⑦ 검색 저장 라벨 date·court(칩 규칙)·result·bucket(주입 사전)·usepick(주입 사전)·picks·promising
  ⑧ frame.html `\\` 거부 + 출처 대조(초기 로드·load 갱신), Playwright 로 `#/\\evil.example/x` → iframe `/`, 외부 요청 0
Playwright 층은 같은 프로세스의 스레드 uvicorn(임시 DB), 브라우저 없으면 skip. 포트는 OS 가 비운 것(운영·다른 담당 로컬 서버 9개 금지).
"""
import ast
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

from web import db, service

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
LIST_TPL = (ROOT / "web/templates/vehicles.html").read_text(encoding="utf-8")
DETAIL_TPL = (ROOT / "web/templates/detail.html").read_text(encoding="utf-8")
FRAME = (ROOT / "web/static/frame.html").read_text(encoding="utf-8")
APP_CSS = (ROOT / "web/static/app.css").read_text(encoding="utf-8")
_PUBLIC = {"x-forwarded-for": "203.0.113.9"}
FORBIDDEN_PORTS = {8765, 8000, 8811, 8797, 8841, 8877, 8931, 8963, 8964}
TODAY = date.today()
SPLIT_NOTE = "낙찰은 결과 참고 · 유찰은 다음 기일 대기"
OLD_SPLIT_NOTE = "낙찰 결과·다음 기일 대기 참고"
EXPECTED_SUMMARY = "현대 · 1,000~2,000만 · 매각기일순 · 2/2페이지"
COMBO = "/vehicles?maker=현대&price=1000-2000&sort=sale_date&page=2"


def _d(n):
    return (TODAY + timedelta(days=n)).isoformat()


# hide_incomplete 를 통과하는 최소 형태(시세 있음·사건번호 형식·낙찰 아님). min_sale_price 12,000,000 = 가격대 1000-2000 안.
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기", "maker": "현대", "model": "쏘나타(SONATA)"}
HYUNDAI_14 = [{"id": f"H{i:02d}", "sale_date": _d(3 + i)} for i in range(14)]
KIA_1 = [{"id": "K1", "maker": "기아", "model": "K5", "sale_date": _d(5), "court": "인천지방법원"}]
SPLIT_3_3 = [{"id": f"F{i}", "sale_date": _d(1 + i)} for i in range(3)] + [{"id": f"Q{i}", "sale_date": _d(-1 - i)} for i in range(3)]


def _seed(rows):
    db.init_db()
    for i, r in enumerate(rows):
        db.upsert_vehicle(dict(BASE, case_no=f"2026타경6{i:04d}", **r))


@pytest.fixture
def client():
    import web.app as A
    return TestClient(A.app, headers=_PUBLIC)


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _text(frag):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", frag)).strip()


def _total(h):
    m = re.search(r"window\.NC_LIST_TOTAL=(\d+);", h)
    assert m, "NC_LIST_TOTAL 없음"
    return int(m.group(1))


def _cond_summary(h):
    m = re.search(r'<p id="condSummary"[^>]*>(.*?)</p>', h, re.S)
    return _text(m.group(1)) if m else None


def _collapsed_head(h):
    return re.search(r'<details id="listFilter"[^>]*>\s*<summary[^>]*>(.*?)</summary>', h, re.S).group(1)


def _filter_form(h):
    i = h.index('<details id="listFilter"')
    i = h.index("<form", i)
    return h[i:h.index("</form>", i)]


def _form_params(form):
    """브라우저가 GET 제출할 때 싣는 (name, value) — hidden·search 는 value, select 는 selected 옵션(없으면 첫 옵션)."""
    out = []
    for m in re.finditer(r'<(input|select)\b([^>]*)>', form):
        attrs = m.group(2)
        name = re.search(r'name="([^"]+)"', attrs)
        if not name:
            continue
        if m.group(1) == "input":
            v = re.search(r'value="([^"]*)"', attrs)
            out.append((name.group(1), html_mod.unescape(v.group(1) if v else "")))
        else:
            body = form[m.end():form.index("</select>", m.end())]
            sel = re.search(r'<option value="([^"]*)"[^>]*\bselected\b', body) or re.search(r'<option value="([^"]*)"', body)
            out.append((name.group(1), html_mod.unescape(sel.group(1) if sel else "")))
    return out


# ── ① 요약 줄 날짜 ─────────────────────────────────────────────────────────────

def test_summary_date_part_is_iso_same_as_chip(client):
    _seed([{"id": "P1", "sale_date": "2026-09-01"}])
    h = _get(client, "/vehicles?date=2026-09-01&sort=sale_date")
    summ = _cond_summary(h)
    assert summ is not None and summ.startswith("2026-09-01 매각 · 매각기일순"), summ
    chip = re.search(r'title="날짜 필터 해제">(.*?)</a>', h, re.S)
    assert chip and _text(chip.group(1)) == "2026-09-01 매각 ✕", "칩과 요약이 같은 문자열"
    assert "9/1 매각" not in h
    assert "date[5:7]" not in LIST_TPL, "월/일 축약 식은 템플릿에서 사라진다"


# ── ② 구분 줄 문구 — 한 원천 ─────────────────────────────────────────────────────

def test_split_note_wording_and_single_source(client):
    assert LIST_TPL.count("{% set split_note = '" + SPLIT_NOTE + "' %}") == 1
    assert LIST_TPL.count("건 — {{ split_note }}") == 2, "표(lg+)·카드 두 자리가 같은 변수를 쓴다"
    _seed(SPLIT_3_3)
    r = client.get("/vehicles?sort=sale_date")
    assert r.status_code == 200 and r.context["sale_split"]["page_first_past_idx"] == 3, "픽스처 전제(공허 통과 방지)"
    assert r.text.count('건 — ' + SPLIT_NOTE) == 2, "카드 1 + 표 1"
    assert OLD_SPLIT_NOTE not in r.text, "예전 문구(참고 가 유찰까지 받음)는 렌더에 없다"
    assert re.search(r'<tr data-sale-split class="bg-background"><td colspan="9"[^>]*>지난 기일 <b class="text-txt tnum">3</b>건 — ' + SPLIT_NOTE, r.text)


# ── ③ 큰글씨 접힌 머리 — 부품 단위 ───────────────────────────────────────────────

def test_collapsed_header_first_part_plus_count(client):
    _seed(HYUNDAI_14 + KIA_1)
    head = _collapsed_head(_get(client, COMBO))
    assert _text(head).endswith("검색 · 필터 — 현대 외 3 expand_more") or "— 현대 외 3" in _text(head), _text(head)
    assert EXPECTED_SUMMARY not in _text(head), "전문은 머리에 안 넣는다(부품 단위)"
    assert 'title="' + EXPECTED_SUMMARY + '"' in head, "전문은 title"
    one = _text(_collapsed_head(_get(client, "/vehicles?maker=기아")))
    assert "— 기아" in one and " 외 " not in one, one
    two = _text(_collapsed_head(_get(client, "/vehicles?maker=기아&sort=mileage")))
    assert "— 기아 외 1" in two, two
    assert "—" not in _text(_collapsed_head(_get(client, "/vehicles"))), "기본 상태엔 요약 없음"
    assert "{{ _cs.parts[0] }}" in LIST_TPL and "외 {{ _cs.parts|length - 1 }}" in LIST_TPL, "요약 줄 부품(_cs.parts) 재사용"


# ── ⑥ all hidden ──────────────────────────────────────────────────────────────

def test_all_hidden_only_when_entered_raw_value_and_submit_keeps_population(client):
    _seed([{"id": "C1", "sale_date": _d(3)},
           {"id": "I1", "sale_date": _d(3), "median_price": None, "mileage_km": None, "photo_count": 0}])   # 불완전 → 기본 숨김
    t_def, t_all = _total(_get(client, "/vehicles")), _total(_get(client, "/vehicles?all=1"))
    assert (t_def, t_all) == (1, 2), "픽스처 전제: all=1 이 불완전 물건을 드러낸다(공허 통과 방지)"
    form = _filter_form(_get(client, "/vehicles?all=1&maker=현대"))
    assert form.count('name="all"') == 1 and '<input type="hidden" name="all" value="1">' in form
    params = _form_params(form)
    assert [k for k, _ in params].count("all") == 1
    r = client.get("/vehicles?" + urlencode([(k, v) for k, v in params if v != ""]))
    assert r.status_code == 200 and _total(r.text) == 2, "[적용] 뒤에도 all=1 이 살아 모수가 같다"
    assert 'name="all"' not in _filter_form(_get(client, "/vehicles?maker=현대")), "진입 파라미터가 없으면 hidden 도 없다"
    assert '<input type="hidden" name="all" value="0">' in _filter_form(_get(client, "/vehicles?all=0")), "원값 그대로(무효값을 1 로 승격하지 않는다)"
    assert "{% set all = request.query_params.get('all', '') %}" in LIST_TPL, "all 은 라우트 컨텍스트에 없어 request 에서 읽는다(app.py 무접촉)"


# ── ⑦ 검색 저장 라벨 ──────────────────────────────────────────────────────────────

def test_saved_search_label_reads_missing_keys_with_chip_words(client):
    _seed(HYUNDAI_14)
    h = _get(client, "/vehicles?date=2026-09-01")
    i = h.index("function ncSaveSearch(")
    body = h[i:h.index("(function(){", i)]
    for anchor in ("p.get('date')+' 매각'", "'결과='+p.get('result')", "BL[p.get('bucket')]", "p.get('usepick')", "'실사용 추천'",
                   "p.get('picks')==='1'", "'유망 물건'", "p.get('promising')", "'검토 추천'",
                   "'법원 '+ct.split(',').length+'곳'", "ct.replace('지방법원','지법')"):
        assert anchor in body, anchor
    assert "parts.push('법원 지정')" not in body, "법원은 칩과 같은 규칙(N곳 / 지법 축약) — 예전 호출은 없다(주석의 낱말은 무관)"
    m = re.search(r"var BL=(\{.*?\}), UT=(\{.*?\});", body, re.S)
    assert m, "버킷·실사용 사전은 Jinja 주입"
    tpl_bl = ast.literal_eval(LIST_TPL[LIST_TPL.index("{% set bucket_labels = ") + len("{% set bucket_labels = "):LIST_TPL.index(" %}", LIST_TPL.index("{% set bucket_labels = "))])
    assert json.loads(m.group(1)) == tpl_bl and tpl_bl["wait"] == "유찰 대기"
    assert json.loads(m.group(2)) == service.USE_TIER_LABELS
    # 기존 부품(FEAT-1 ⑤ 가 고정)은 그대로
    assert "p.get('price')" in body and "parts.push('최저가 '+PB[pb])" in body


# ── ⑧ frame.html 가드(소스) · ⑤ 상세 템플릿(소스) ──────────────────────────────────

def test_frame_guard_rejects_backslash_and_checks_origin_in_both_places():
    guard = FRAME[FRAME.index('if (!p.startsWith("/")'):FRAME.index('document.getElementById("f").src = p;')]
    assert 'p.indexOf("\\\\") !== -1' in guard and "new URL(p, location.origin).origin !== location.origin" in guard
    load = FRAME[FRAME.index('addEventListener("load"'):]
    assert "l.origin !== location.origin" in load and 'np.indexOf("\\\\") !== -1' in load and 'np.startsWith("//")' in load
    assert 'history.replaceState(null, "", "#" + np)' in load, "해시 갱신 로직은 그대로"


def test_detail_title_column_min_width_class_and_css(client):
    _seed(HYUNDAI_14)
    assert '<div class="min-w-0 flex-1 sm:min-w-[12rem]">' in _get(client, "/vehicle/H00")
    assert DETAIL_TPL.count('class="min-w-0 flex-1 sm:min-w-[12rem]"') == 1
    assert "sm\\:min-w-\\[12rem\\]{min-width:12rem}" in APP_CSS, "빌드된 app.css 에 유틸리티가 있어야 화면에 먹는다"


# ═══════════════════════════════════ Playwright ═══════════════════════════════════

def _free_port():
    for _ in range(50):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        if port not in FORBIDDEN_PORTS:
            return port
    raise RuntimeError("free port")


@pytest.fixture(scope="module")
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


DIRTY_BTNS = '#listFilter form button.btn-ghost:not([type])'


def test_apply_dirty_reverts_when_form_returns_to_loaded_values(server, browser):
    """④ 디자인 Q6: 셀렉트를 바꿨다 원래 값으로 돌리면 [적용] 채움이 풀린다(로드 시 직렬화와 비교). 검색어도 같은 규칙."""
    _seed(HYUNDAI_14 + KIA_1)
    ctx = browser.new_context(viewport={"width": 390, "height": 640}, device_scale_factor=1, locale="ko-KR", has_touch=True)
    pg = ctx.new_page(); pg.goto(server + "/vehicles?maker=현대", wait_until="networkidle")
    dirty = lambda: pg.eval_on_selector_all(DIRTY_BTNS, 'els => els.map(e => e.classList.contains("is-dirty"))')  # noqa: E731
    assert dirty() == [False, False], "로드 직후 깨끗"
    pg.select_option("#listFilter select[name=maker]", "기아")
    assert dirty() == [True, True], "바꾸면 채움"
    pg.select_option("#listFilter select[name=maker]", "현대")
    assert dirty() == [False, False], "원래 값으로 돌리면 풀림(예전엔 채워진 채 남았다)"
    pg.fill("#listFilter input[name=q]", "쏘")
    assert dirty() == [True, True]
    pg.fill("#listFilter input[name=q]", "")
    assert dirty() == [False, False]
    pg.select_option("#listFilter select[name=sort]", "mileage")
    assert dirty() == [True, True], "정렬도 폼 값"
    ctx.close()


@pytest.mark.parametrize("width", [640, 700, 768])
@pytest.mark.parametrize("view", ["public", "admin"])
def test_detail_header_title_column_keeps_width_and_actions_fold(server, browser, width, view):
    """⑤ qa D-1 회귀 기준표(공개 뷰 640·700·768: 제목 열 0·28·96 → h1 두 줄) 재현 → 제목 열 ≥ 190, h1 1줄, 액션 줄·문서 넘침 0."""
    # 감정평가서·시세 있음 → 공개 뷰 5버튼. 이름은 qa 회귀 기준 물건과 같은 `기아 카니발`(text-2xl 굵게 ≈130px < 192) — 긴 이름은 192px 안에서도
    # 접히므로 "한 줄" 단정이 이름 길이를 재는 꼴이 된다(첫 실행에서 `현대 쏘나타(SONATA)` 가 64px 로 잡혔다).
    _seed([{"id": "D1", "sale_date": _d(3), "appraisal_ecdoc_id": "ecdoc-1", "maker": "기아", "model": "카니발"}])
    kw = {"extra_http_headers": {"X-Forwarded-For": "203.0.113.9"}} if view == "public" else {}
    ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1, locale="ko-KR", has_touch=True, **kw)
    pg = ctx.new_page(); pg.goto(server + "/vehicle/D1", wait_until="networkidle")
    if view == "public":
        assert pg.locator("text=다시 분석").count() == 0, "공개 뷰 확정(관리자 버튼 없음)"
    m = pg.evaluate("""() => {
        const col = document.querySelector('[class*="sm:min-w-[12rem]"]'); const h1 = col.querySelector('h1'); const row = col.nextElementSibling;
        const r = (e) => e.getBoundingClientRect();
        const sc = document.getElementById('appscroll');
        return {title: r(col).width, h1: r(h1).height, court: r(col.querySelector('p')).height,
                row_w: r(row).width, row_h: r(row).height, row_right: r(row).right, row_over: row.scrollWidth > row.clientWidth + 1,
                doc_over: document.documentElement.scrollWidth > window.innerWidth,
                app_over: sc ? sc.scrollWidth > sc.clientWidth : false, vw: window.innerWidth,
                back: !!Array.from(row.querySelectorAll('a')).find(a => a.textContent.includes('목록으로'))};
    }""")
    assert m["back"], "액션 줄에 목록으로 가 있다(픽스처 전제)"
    assert "카니발" in pg.locator('[class*="sm:min-w-[12rem]"] h1').inner_text(), "픽스처 전제(짧은 이름)"
    assert m["title"] >= 190, m
    assert m["h1"] <= 34, f"제목 한 줄(text-2xl 32px): {m}"
    assert m["court"] <= 42, f"법원·사건 줄 두 줄 이내: {m}"
    assert not m["row_over"] and not m["doc_over"] and not m["app_over"] and m["row_right"] <= m["vw"], m
    ctx.close()


@pytest.mark.parametrize("hash_", ["#/\\evil.example/x", "#/\\\\evil.example", "#//evil.example/x", "#http://evil.example/", "#/vehicles\\@evil.example"])
def test_frame_hostile_hash_lands_on_root_without_external_request(server, browser, hash_):
    _seed(HYUNDAI_14)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ko-KR")
    pg = ctx.new_page(); ext = []
    pg.on("request", lambda r: ext.append(r.url) if urlsplit(r.url).hostname not in ("127.0.0.1", "localhost") else None)
    pg.goto(server + "/static/frame.html" + hash_, wait_until="networkidle")
    fr = next(f for f in pg.frames if f != pg.main_frame)
    u = urlsplit(fr.url)
    assert u.netloc.startswith("127.0.0.1") and u.path == "/", (hash_, fr.url)
    assert ext == [], (hash_, ext)
    ctx.close()


@pytest.mark.parametrize("qs,expected", [
    ("date=2026-09-01&sort=sale_date", "2026-09-01 매각"),                                  # qa G 표의 `전체 물건` 케이스
    ("court=수원지방법원", "수원지법"),
    ("court=수원지방법원,인천지방법원&result=유찰&bucket=wait&usepick=now&picks=1&promising=1",
     "법원 2곳 · 결과=유찰 · 유찰 대기 · 실사용 추천 · 지금 사면 이득 · 유망 물건 · 검토 추천"),
])
def test_saved_search_label_runtime_reads_new_keys(server, browser, qs, expected):
    """⑦ 소스 앵커만이 아니라 실제 [검색 저장] 클릭 → localStorage 라벨. 낱말은 칩·요약 줄과 같다(주입 사전 포함)."""
    _seed(HYUNDAI_14)
    ctx = browser.new_context(viewport={"width": 390, "height": 640}, device_scale_factor=1, locale="ko-KR", has_touch=True)
    pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept())
    pg.goto(server + "/vehicles?" + qs, wait_until="networkidle")
    pg.click('button[onclick="ncSaveSearch()"]')
    lst = pg.evaluate("() => JSON.parse(localStorage.getItem('naechaget:searches') || '[]')")
    assert lst and lst[0]["label"] == expected, lst
    assert "page=" not in lst[0]["qs"] and "all=" not in lst[0]["qs"]
    ctx.close()


def test_frame_normal_internal_path_still_loads(server, browser):
    _seed(HYUNDAI_14)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, locale="ko-KR")
    pg = ctx.new_page(); pg.goto(server + "/static/frame.html#/vehicles?maker=%ED%98%84%EB%8C%80&sort=sale_date", wait_until="networkidle")
    fr = next(f for f in pg.frames if f != pg.main_frame)
    fr.wait_for_selector("#listResults")
    assert urlsplit(fr.url).path == "/vehicles" and "sort=sale_date" in fr.url
    assert pg.evaluate("location.hash").startswith("#/vehicles"), "load 갱신(같은 출처)은 그대로 동작"
    ctx.close()
