"""UX-1(앞부분)·UX-4 — 검색 폼 파라미터 보존 + 활성 칩 줄바꿈 (지시서 2026-09-26-22, 오너 승인 2026-09-26).

배경(검색 UX 워크스루 2026-09-26 §3 U2·U3): 차종 카드 SUV(88건)에서 제조사만 바꿔 [적용] → `segment` 가 빠져
128건·차종 `전체`(S11-54→55). 달력 9/1(28건)에서 정렬만 바꿔 [적용] → `date` 가 빠져 1,316건(S11-56→57).
폼 hidden 이 `upcoming/result/status/cond/bucket/usepick/picks` 7종만이라 `segment/date/court/promising` 이 조용히 버려졌다.
같은 줄의 활성 칩 5종(upcoming·date·result·cond 2종·court)에는 `whitespace-nowrap shrink-0` 이 없어 390px 에서
`입찰예정 30일 ✕` 2줄·`2026-09-01 매각 ✕` 3줄(S6-30·S11-56).

이 파일은 **렌더된 HTML** 만 본다(서버 필터 의미는 다른 테스트가 지킨다):
  ① 진입 파라미터(segment·date·court·promising)가 있으면 폼 안에 같은 값의 hidden 이 있다(court 는 콤마 다중값 그대로)
  ② 그 파라미터가 없으면 그 hidden 도 없다(빈값 hidden 은 서버가 오염값으로 볼 수 있다)
  ③ 폼 안 `name="…"` 은 이름별로 **정확히 1회** — 같은 이름이 두 번이면 서버가 중복으로 보고 필터를 푼다(FEAT-1 price 사고)
  ④ 활성 칩 5종의 `<a …>` 태그에 `whitespace-nowrap` 과 `shrink-0` 이 있다(비활성 칩·가격대 칩과 같은 관례)
  ⑤ **폼 제출 재현**(U2 회귀): 화면의 폼을 파싱해(셀렉트 기본값 + hidden 전부) GET 제출 → `segment` 가 남고 총수 불변.
     제조사만 바꿔 제출해도 segment 가 남는다(S11-54→55). 날짜 화면도 정렬만 바꿔 제출하면 date 가 남는다(S11-56→57).
검사는 전부 **앵커 문자열**로 한다 — 줄 번호·매직 오프셋 창을 쓰지 않는다.
"""
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from starlette.testclient import TestClient

from web import db

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
LIST_TOTAL = re.compile(r"window\.NC_LIST_TOTAL=(\d+);")
FORM_NAMES = ("segment", "date", "court", "promising", "price", "judgment", "maker", "sort", "q")

# hide_incomplete=True 를 통과하는 최소 형태(시세 있음·사건번호 형식·낙찰 아님) — FEAT-1 테스트와 같은 관례
BASE = {"court": "수원지방법원", "item_no": "1", "year": 2020, "status": "완료", "fail_count": 1,
        "median_price": 15_000_000, "appraisal_value": 20_000_000, "min_sale_price": 12_000_000,
        "market_confidence_label": "보통", "judgment": "유찰 대기"}
_TODAY = date.today()
SOON = (_TODAY + timedelta(days=10)).isoformat()      # upcoming=30 안
FAR = (_TODAY + timedelta(days=200)).isoformat()      # upcoming=30 밖
PAST_DATE = "2026-09-01"                              # 달력 진입 날짜(과거 기일도 date= 로는 조회된다)

# (id, model, maker, sale_date, court). SUV 는 현대 2 + 기아 1 이 30일 안, 기아 1 이 밖. 세단은 30일 안 1.
ROWS = [
    ("S1", "싼타페(SANTAFE)", "현대", SOON, "수원지방법원"),
    ("S2", "투싼(TUCSON)", "현대", SOON, "인천지방법원"),
    ("S3", "쏘렌토(SORENTO)", "기아", SOON, "수원지방법원"),
    ("S4", "스포티지", "기아", FAR, "의정부지방법원"),
    ("D1", "쏘나타(SONATA)", "현대", SOON, "수원지방법원"),
    ("P1", "그랜저(GRANDEUR)", "현대", PAST_DATE, "대구지방법원"),
    ("P2", "K5", "기아", PAST_DATE, "대구지방법원"),
]


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ux14.db")
    db.init_db()
    for i, (vid, model, maker, sd, court) in enumerate(ROWS):
        db.upsert_vehicle(dict(BASE, id=vid, case_no=f"2026타경3{i:04d}", model=model, maker=maker,
                               sale_date=sd, court=court))
    return ROWS


@pytest.fixture
def client(seeded):
    import web.app as A
    return TestClient(A.app)


def _get(client, url: str) -> str:
    r = client.get(url, headers=_PUBLIC)
    assert r.status_code == 200, f"{url} → {r.status_code}"
    return r.text


def _form(html: str) -> str:
    """검색 폼(`<form method="get" action="/vehicles"`) 안쪽 HTML."""
    i = html.index('<form method="get" action="/vehicles"')
    return html[i:html.index("</form>", i)]


def _total(html: str) -> int:
    m = LIST_TOTAL.search(html)
    assert m, "window.NC_LIST_TOTAL 이 없다"
    return int(m.group(1))


def _hidden(form: str, name: str):
    """폼 안 hidden 의 value(없으면 None). 같은 이름이 둘이면 실패."""
    found = re.findall(r'<input type="hidden" name="%s" value="([^"]*)">' % re.escape(name), form)
    assert len(found) <= 1, f"hidden {name} 가 {len(found)}개"
    return found[0] if found else None


class _FormFields(HTMLParser):
    """브라우저가 GET 제출할 때 싣는 (name, value) — input(hidden·text) 은 value, select 는 selected 옵션
    (없으면 첫 옵션). 버튼(name 없음)은 싣지 않는다."""

    def __init__(self):
        super().__init__()
        self.fields = []           # [(name, value)]
        self._sel = None           # (name, [(value, selected)])

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name"):
            self.fields.append((a["name"], a.get("value", "")))
        elif tag == "select" and a.get("name"):
            self._sel = (a["name"], [])
        elif tag == "option" and self._sel is not None:
            self._sel[1].append((a.get("value", ""), "selected" in a))

    def handle_endtag(self, tag):
        if tag == "select" and self._sel is not None:
            name, opts = self._sel
            chosen = next((v for v, s in opts if s), opts[0][0] if opts else "")
            self.fields.append((name, chosen))
            self._sel = None


def _submit(client, html: str, **override) -> tuple[str, str]:
    """화면의 폼을 그대로(또는 셀렉트 하나를 바꿔) GET 제출한다. 반환: (제출 URL, 응답 HTML)."""
    p = _FormFields(); p.feed(_form(html))
    fields = [(k, override.get(k, v)) for k, v in p.fields]
    url = "/vehicles?" + urlencode(fields)
    return url, _get(client, url)


# ── ① 진입 파라미터 → hidden ──────────────────────────────────────────────────

def test_segment_hidden_when_entered_from_segment_card(client):
    form = _form(_get(client, "/vehicles?segment=suv&upcoming=30"))
    assert _hidden(form, "segment") == "suv"
    assert _hidden(form, "upcoming") == "30", "기존 hidden 관례는 그대로"


def test_date_hidden_when_entered_from_calendar(client):
    form = _form(_get(client, f"/vehicles?date={PAST_DATE}&sort=sale_date"))
    assert _hidden(form, "date") == PAST_DATE


def test_court_hidden_keeps_comma_multi_value_as_is(client):
    court = "수원지방법원,인천지방법원"
    form = _form(_get(client, "/vehicles?court=" + court))
    assert _hidden(form, "court") == court, "콤마 다중값을 쪼개거나 바꾸지 않는다(서버가 콤마로 나눈다)"


def test_promising_hidden_when_entered_from_review_card(client):
    form = _form(_get(client, "/vehicles?promising=1"))
    assert _hidden(form, "promising") == "1"


# ── ② 파라미터 없음 → hidden 없음 ─────────────────────────────────────────────

@pytest.mark.parametrize("url", ["/vehicles", "/vehicles?maker=현대&sort=recent", "/vehicles?upcoming=30"])
def test_no_hidden_without_parameter(client, url):
    form = _form(_get(client, url))
    for name in ("segment", "date", "court", "promising"):
        assert _hidden(form, name) is None, f"{url}: {name} hidden 이 빈값으로라도 있으면 안 된다"


# ── ③ 폼 안 name 은 이름별 정확히 1회 ─────────────────────────────────────────

ALWAYS_IN_FORM = ("price", "judgment", "maker", "sort", "q")          # 셀렉트·검색창 — 항상 1회
HIDDEN_WHEN_SET = ("segment", "date", "court", "promising")           # 값이 있을 때만 hidden 1회, 없으면 0회


@pytest.mark.parametrize("url", [
    "/vehicles",
    "/vehicles?segment=suv&upcoming=30",
    f"/vehicles?date={PAST_DATE}&sort=sale_date",
    "/vehicles?court=수원지방법원,인천지방법원&promising=1&price=1000-2000&maker=현대&judgment=유찰 대기&q=싼타페",
])
def test_each_form_name_appears_exactly_once(client, url):
    form = _form(_get(client, url))
    present = parse_qs(urlsplit(url).query)
    for name in FORM_NAMES:
        n = len(re.findall(r'\bname="%s"' % re.escape(name), form))
        want = 1 if (name in ALWAYS_IN_FORM or name in present) else 0
        assert n == want, (f"{url}: name=\"{name}\" 가 폼 안에 {n}회(기대 {want} — 둘이면 서버가 중복으로 보고 "
                           f"필터를 푼다, 값 없는 hidden 은 빈값을 실어 보낸다)")
    assert set(HIDDEN_WHEN_SET) | set(ALWAYS_IN_FORM) == set(FORM_NAMES)


# ── ④ 활성 칩 5종 nowrap ──────────────────────────────────────────────────────

def _active_chip_tag(html: str, text_anchor: str) -> str:
    """`text_anchor`(칩의 표시 문구, ✕ 포함) 가 들어 있는 `<a …>` 시작 태그 전체."""
    j = html.index(text_anchor)
    i = html.rindex("<a ", 0, j)
    return html[i:html.index(">", i) + 1]


@pytest.mark.parametrize("url,anchor", [
    ("/vehicles?upcoming=30", "입찰예정 30일 ✕"),
    (f"/vehicles?date={PAST_DATE}", f"{PAST_DATE} 매각 ✕"),
    ("/vehicles?result=낙찰", "결과=낙찰 ✕"),
    ("/vehicles?cond=insp_expired", "검사 경과 ✕"),
    ("/vehicles?cond=damaged", "외관 손상 ✕"),
    ("/vehicles?court=수원지방법원", "수원지법 ✕"),
    ("/vehicles?court=수원지방법원,인천지방법원", "법원 2곳 ✕"),
])
def test_active_chip_has_nowrap_and_shrink0(client, url, anchor):
    tag = _active_chip_tag(_form(_get(client, url)), anchor)
    cls = re.search(r'class="([^"]*)"', tag).group(1).split()
    assert "whitespace-nowrap" in cls and "shrink-0" in cls, (anchor, tag)
    assert "flex" not in cls or "inline-flex" in cls, f"{anchor}: 블록 flex 가 아니라 가격대 칩과 같은 inline-flex"


# ── ⑤ 폼 제출 재현(U2 회귀) ─────────────────────────────────────────────────────

def test_submit_unchanged_form_keeps_segment_and_total(client):
    """S11-54→55: SUV 화면에서 [적용]만 눌러도 segment 가 남고 총수가 같다."""
    html = _get(client, "/vehicles?segment=suv&upcoming=30")
    before = _total(html)
    assert before == 3, "픽스처: 30일 안 SUV 3건(공허 통과 방지)"
    url, after_html = _submit(client, html)
    q = parse_qs(urlsplit(url).query)
    assert q.get("segment") == ["suv"] and q.get("upcoming") == ["30"], url
    assert _total(after_html) == before
    assert 'name="segment" value="suv"' in _form(after_html), "제출 뒤 화면에도 hidden 이 남아 다음 [적용]도 지킨다"


def test_submit_with_maker_changed_keeps_segment_and_narrows(client):
    """S11-54→55 재현: 제조사만 바꿔 제출 → segment 유지, 총수는 부분집합(≤)이어야 하며 늘면 안 된다."""
    html = _get(client, "/vehicles?segment=suv&upcoming=30")
    before = _total(html)
    url, after_html = _submit(client, html, maker="현대")
    q = parse_qs(urlsplit(url).query)
    assert q.get("segment") == ["suv"] and q.get("maker") == ["현대"], url
    assert _total(after_html) == 2 <= before, "SUV·현대·30일 안 = 2 (segment 가 빠졌으면 세단 쏘나타가 섞여 3)"
    # 활성 SUV 칩(차종 프리셋 줄)이 그대로 켜져 있다
    assert 'bg-primary text-white border-primary">SUV</a>' in after_html


def test_submit_with_sort_changed_keeps_date(client):
    """S11-56→57 재현: 달력 날짜 화면에서 정렬만 바꿔 제출 → date 유지, 총수 불변, 날짜 칩 유지."""
    html = _get(client, f"/vehicles?date={PAST_DATE}&sort=sale_date")
    before = _total(html)
    assert before == 2, "픽스처: 9/1 기일 2건"
    url, after_html = _submit(client, html, sort="mileage")
    q = parse_qs(urlsplit(url).query)
    assert q.get("date") == [PAST_DATE] and q.get("sort") == ["mileage"], url
    assert _total(after_html) == before
    assert f"{PAST_DATE} 매각 ✕" in after_html


def test_submit_keeps_court_and_promising(client):
    """법원 다중 선택·검토 추천 진입에서도 [적용] 이 모수를 지킨다."""
    court = "수원지방법원,인천지방법원"
    html = _get(client, f"/vehicles?court={court}")
    before = _total(html)
    assert before == 4, "픽스처: 수원 3 + 인천 1"
    url, after_html = _submit(client, html)
    assert parse_qs(urlsplit(url).query).get("court") == [court], url
    assert _total(after_html) == before

    html = _get(client, "/vehicles?promising=1")
    url, after_html = _submit(client, html)
    assert parse_qs(urlsplit(url).query).get("promising") == ["1"], url
    assert _total(after_html) == _total(html)


def test_submitted_url_has_no_duplicate_keys(client):
    """제출 URL 에 같은 키가 두 번 실리지 않는다(③ 의 제출 쪽 거울)."""
    html = _get(client, "/vehicles?segment=suv&upcoming=30&court=수원지방법원&promising=1&price=1000-2000")
    url, _ = _submit(client, html)
    q = parse_qs(urlsplit(url).query, keep_blank_values=True)
    dup = {k: v for k, v in q.items() if len(v) > 1}
    assert not dup, dup
    assert q["price"] == ["1000-2000"], "price 는 셀렉트 한 곳에서만 실린다(hidden 금지)"
