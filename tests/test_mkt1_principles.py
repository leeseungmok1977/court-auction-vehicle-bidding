# -*- coding: utf-8 -*-
"""MKT-1 — 판정 원칙을 사용자가 알 수 있게 (오너 결정 2026-10-02: 용어 '안전한 쪽으로', 랜딩·앱 소개에 넣는다).

지시서 2026-10-02-03 의 확정 문구를 **글자 그대로** 고정한다. 지키는 것:
  ① 랜딩 '핵심 가치' 섹션(제목 '감으로 입찰하지 않습니다')의 3카드 — 셋째가 '안전한 산정 로직' — **바로 뒤, 그 섹션 안**에
     '판정 원칙' 블록: 제목 · 보조줄 · 항목 넷. 상자를 치지 않는다 — 바로 아래 '정직 배너'가 이미 테두리 상자라서
     상자 두 개가 연달아 나오지 않게(지시서).
  ② base.html 두 자리에 같은 한 문장 — 데스크톱 사이드바('참고용 분석 도구(투자 권유 아님)' 바로 뒤),
     모바일 푸터('법원경매 분석 도구입니다 — 이 앱에서는 입찰할 수 없습니다.' 바로 뒤).
  ③ 과장 낱말 0 — 결과를 약속하는 말('걸러'·'안전합니다'·'보장' …). 이 문구는 **계산 방식**만 말한다(표시광고 실증 부담).
     랜딩 **전체**에도 0 이다 — 2회차(Steward 확정 10-02)에 셋째 카드의 '…로 손실을 막습니다.'를
     '…자동 경고합니다.'로 고쳤다(하는 일만 말한다).
  ④ 2회차: 넷째 항목은 따옴표 낱말 없이 '판정을 보류하고' — 화면 낱말 '판정 보류'는 신뢰도 낮음(lowconf)에만 붙고
     동급 시세 없음(nomarket)에는 붙지 않는데, 둘 다 추천 칸 밖이다. 모바일 푸터 두 줄과 사이드바 문장은
     줄 끝 외톨이를 막는 줄바꿈 규칙(text-wrap:pretty)을 쓴다(큰글씨 390 '없습니다.' · 1440 '계산합니다.' 실측).
  ⑤ 3회차(app-design 검수 · Steward 판정 10-02 10:25): 글자는 그대로, 묶음과 색만 —
     제목의 '안전한 쪽으로'(큰글씨 320 '모르는 건 안전한 / 쪽으로' → 첫 줄이 '안전하다'로 읽힘) · 셋째 카드 굵은 '자동 경고' ·
     푸터 기존 줄 '입찰할 수 없습니다.'(큰글씨 390 '입찰할 / 수 없습니다')를 한 덩어리로, 체크 아이콘은 인디고 대신 보조 글자색.
     그래서 제목·푸터 줄은 원문 HTML 이 아니라 **사람이 읽는 글자**로 찾는다(안에 묶음 태그가 있다).

문장마다 지키는 코드가 있다(근거 대조: reports/2026-10-02-growth-MKT-1.md 끝 'Steward 검토' 절):
  사고 가정 service.use_accident_rate·accident_evidence · 침수·전손 estimate_withheld ·
  최저가 미반영 floor_unconfirmed·refresh_lagged_floors · 판정 보류 bid_state 의 lowconf·nomarket(lifecycle 칸도 review 밖).
그 동작이 바뀌면 화면 문장과 이 파일을 **함께** 고친다 — 화면만 남으면 지키지 않는 약속이 된다.

자리는 줄 번호가 아니라 **앵커 문자열**로 찾는다(CLAUDE.md 규칙 8).
"""
import html as _html
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

PUB = {"x-forwarded-for": "203.0.113.7"}
ADMIN = {"host": "127.0.0.1"}

# ── 확정 문구(지시서 2026-10-02-03, 글자 그대로) ─────────────────────────
TITLE = "모르는 건 안전한 쪽으로 계산합니다"
SUB = "확인되지 않은 사실은 유리하게 보지 않습니다 — 경매는 낙찰 뒤 되돌릴 수 없기 때문입니다."
ITEMS = (
    "사고 이력을 확인하지 못한 차는 무사고로 보지 않고, 사고차로 가정해 계산합니다.",
    '침수·전손이 의심되는 차는 예상낙찰가 대신 "입찰하지 마세요"라고 알려 드립니다.',
    "유찰 뒤 최저가가 아직 반영되지 않은 물건은, 법원 기일내역으로 확인하기 전까지 예상값을 보여 드리지 않습니다.",
    "비교할 시세가 부족하거나 믿기 어려우면 판정을 보류하고 추천에 넣지 않습니다.",
)
SENT = "사고 이력을 확인하지 못한 차는 사고차로 가정해 계산합니다."
# 셋째 카드 본문(2회차 Steward 확정) — 앞부분은 그대로, 굵은 부분과 끝이 바뀌었다
CARD3_BODY = "취득세·이전등록·마진까지 반영한 상한가를 계산하고, 사고·침수 이력이 있으면 입찰 중단 기준으로 자동 경고합니다."
CARD3_BOLD = "사고·침수 이력이 있으면 입찰 중단 기준으로 자동 경고"
CARD3_HEAD = "취득세·이전등록·마진까지 반영한 상한가를 계산하고,"     # 1·2회차 모두 같은 앞부분(대조군 앵커)
# 3회차 — 줄 끝에서 갈라지면 안 되는 덩어리(글자는 그대로, 한 덩어리로 묶는 태그만)
NOWRAP = '<span class="whitespace-nowrap">'
TITLE_UNIT = "안전한 쪽으로"
CARD3_UNIT = "자동 경고"
FOOTER_UNIT = "입찰할 수 없습니다."

# ── 앵커 ─────────────────────────────────────────────────────────────
CORE = "감으로 입찰하지 않습니다"                 # '핵심 가치' 섹션 제목
CARDS = ("검증된 예상낙찰가", "종합 분석 리포트", "안전한 산정 로직")
HONEST = "정확도를 부풀리지 않습니다"              # 바로 다음 섹션(정직 배너) 제목
SIDEBAR_ANCHOR = "참고용 분석 도구(투자 권유 아님)"
FOOTER_ANCHOR = "법원경매 분석 도구입니다 — 이 앱에서는 입찰할 수 없습니다."

# 결과를 약속하는 말. 앞의 셋은 지시서가 든 예, 나머지는 같은 계열.
# ⚠ '안전한'(쪽으로)은 오너가 고른 용어라 금지어가 아니다 — '안전합니다'(결과 단정)만 막는다.
EXAGGERATION = ("걸러", "안전합니다", "보장", "완벽", "확실", "무조건", "100%", "절대", "손실을 막")


def _promises(text: str) -> list:
    """결과를 약속하는 말. '확실'은 정직 배너의 '불확실성'(약속의 반대말)을 빼고 센다."""
    return [w for w in EXAGGERATION if (re.search(r"(?<!불)확실", text) if w == "확실" else w in text)]

_TAG = re.compile(r"<[^>]+>")
_ICON = re.compile(r'<span class="material-symbols-outlined[^"]*"[^>]*>[^<]*</span>')


def _text(s: str) -> str:
    """사람이 읽는 글자 — 태그를 지우고 공백을 하나로, 엔티티를 푼다."""
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub("", s))).strip()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mkt1.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "M1_1", "folder_key": "M1_1", "case_no": "2026타경7101",
                       "judgment": "유찰 대기", "min_sale_price": 10_000_000,
                       "appraisal_value": 12_000_000, "median_price": 15_000_000})
    db.upsert_vehicle({**_BASE, "id": "M2_1", "folder_key": "M2_1", "case_no": "2026타경7102",
                       "min_sale_price": 10_000_000, "median_price": 14_000_000,
                       "auction_result": "낙찰", "winning_price": 12_000_000, "sale_date": "2026-08-01"})
    import web.app as A
    # with(lifespan) 를 쓰지 않는다 — 켜면 백필 데몬이 monkeypatch 해제 뒤 운영 DB 에 쓴다(test_landing_parity 와 같은 이유).
    return TestClient(A.app)


def _core_section(html: str) -> str:
    """'핵심 가치' 섹션 — 제목 앞의 <section 부터 그 뒤 첫 </section> 앞까지."""
    i = html.index(CORE)
    return html[html.rindex("<section", 0, i):html.index("</section>", i)]


def _title_hits(html: str) -> list:
    """사람이 읽는 글자가 TITLE 인 h3 — 안에 묶음 태그가 있어도 찾는다(3회차)."""
    return [m for m in re.finditer(r"<h3\b[^>]*>(.*?)</h3>", html, re.S) if _text(m.group(1)) == TITLE]


def _title_h3(html: str):
    hits = _title_hits(html)
    assert len(hits) == 1, f"랜딩에 판정 원칙 제목 h3 가 {len(hits)}개다(1개여야 한다)"
    return hits[0]


def _block(html: str) -> str:
    """판정 원칙 블록 — 제목 h3 를 감싼 div 의 여는 태그부터 목록 </ul> 까지."""
    m = _title_h3(html)
    return html[html.rindex("<div", 0, m.start()):html.index("</ul>", m.end()) + len("</ul>")]


def _footer_lines(html: str) -> list:
    """모바일 푸터의 줄(바깥 span) — [(여는 태그, 안쪽 HTML)]. 줄마다 한 행이라 안쪽 묶음 span 이 있어도 행 끝 </span> 까지 잡는다."""
    i = html.index("이 앱은 무엇인가요?")
    seg = html[i:html.index("</div>", i)]
    return re.findall(r'^[ \t]*(<span class="w-full[^"]*"[^>]*>)(.*)</span>[ \t]*$', seg, re.M)


def _items(block: str) -> list:
    return [_text(_ICON.sub("", li)) for li in re.findall(r"<li\b[^>]*>(.*?)</li>", block, re.S)]


# ── ① 랜딩 블록 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("who", ["pub", "admin"])
def test_landing_block_says_the_confirmed_words_verbatim(client, who):
    """제목·보조줄·항목 넷이 확정 문구와 **한 글자도** 다르지 않다(순서 포함)."""
    html = client.get("/landing", headers=PUB if who == "pub" else ADMIN).text
    blk = _block(html)
    h3 = re.search(r"<h3[^>]*>(.*?)</h3>", blk, re.S).group(1)
    assert _text(h3) == TITLE
    p = re.search(r"<p\b[^>]*>(.*?)</p>", blk, re.S)
    assert p and _text(p.group(1)) == SUB, p and _text(p.group(1))
    assert _items(blk) == list(ITEMS), _items(blk)


def test_block_is_inside_core_values_right_after_the_third_card(client):
    """자리: '핵심 가치' 섹션 **안**, 셋째 카드('안전한 산정 로직')가 든 그리드 **바로 뒤**, 그 섹션의 마지막.
    다음 섹션(정직 배너)으로 밀려나거나 카드 위로 올라가면 빨강."""
    html = client.get("/landing", headers=PUB).text
    sec = _core_section(html)
    hits = _title_hits(sec)
    assert len(hits) == 1, "판정 원칙 블록이 '핵심 가치' 섹션 밖에 있다"
    c3, t = sec.index(CARDS[2]), hits[0].start()
    assert c3 < t, "판정 원칙 블록이 셋째 카드보다 앞에 있다"
    # 셋째 카드 문단 끝 ~ 블록 여는 태그: 카드·그리드를 닫는 태그만(사이에 다른 내용이 끼지 않는다)
    between = sec[sec.index("</p>", c3) + len("</p>"):sec.rindex("<div", 0, t)]
    assert re.fullmatch(r"\s*</div>\s*</div>\s*", between), repr(between[:200])
    # 블록 뒤 ~ 섹션 끝: 블록을 닫는 태그만(섹션의 마지막)
    after = sec[sec.index("</ul>", t) + len("</ul>"):]
    assert re.fullmatch(r"\s*</div>\s*", after), repr(after[:200])
    # 정직 배너는 그대로 다음에 온다
    assert _title_h3(html).start() < html.index(HONEST)


def test_block_is_a_light_checklist_not_another_box(client):
    """바로 아래 정직 배너가 테두리 상자다 — 이 블록은 상자(테두리·면·모서리·그림자)를 치지 않는다(지시서).
    항목마다 체크 아이콘: 장식이라 화면 읽기 프로그램이 'check_circle'을 읽지 않게, 초록이 아니게
    (이 앱에서 초록 체크는 홈 '지금 입찰 추천'의 표시라 '입찰하지 마세요' 옆에 두면 뜻이 섞인다).
    3회차: 인디고도 아니다 — 보조 글자색(text-mut). 인디고는 누르는 곳(버튼·링크)에만, 장식 글머리표가 글자보다 먼저 눈을 끌지 않게."""
    html = client.get("/landing", headers=PUB).text
    h = _title_h3(html)
    d = html.rindex("<div", 0, h.start())
    m = re.match(r'<div class="([^"]*)">\s*$', html[d:h.start()])
    assert m, "제목 h3 를 바로 감싼 div 가 없다"
    boxy = [c for c in m.group(1).split() if c.startswith(("border", "bg-", "rounded", "shadow", "ring"))]
    assert not boxy, f"판정 원칙 블록에 상자 클래스: {boxy}"
    assert not {"hidden", "sr-only", "invisible"} & set(m.group(1).split()), m.group(1)
    lis = re.findall(r"<li\b[^>]*>(.*?)</li>", _block(html), re.S)
    assert len(lis) == len(ITEMS)
    for li in lis:
        icon = re.search(r'<span class="material-symbols-outlined([^"]*)"([^>]*)>([^<]*)</span>', li)
        assert icon and icon.group(3) == "check_circle", li[:200]
        assert 'aria-hidden="true"' in icon.group(2), "장식 아이콘을 화면 읽기 프로그램이 읽는다"
        assert not re.search(r"\b(?:text|bg)-(?:emerald|green)-", icon.group(1)), icon.group(1)
        cls = icon.group(1).split()
        assert "text-mut" in cls and "text-primary" not in cls, f"체크 아이콘 색은 보조 글자색이어야 한다: {cls}"


def test_title_keeps_the_safe_side_phrase_together(client):
    """제목의 '안전한 쪽으로'는 한 덩어리(3회차 app-design 검수) — 큰글씨 320 에서 '모르는 건 안전한 / 쪽으로'로 갈리면
    첫 줄이 '모르는 건 안전한'으로 끝나 '안전하다고 가정'으로 읽힌다. 글자는 그대로, 묶음 태그만."""
    h3 = _title_h3(client.get("/landing", headers=PUB).text).group(1)
    assert NOWRAP + TITLE_UNIT + "</span>" in h3, h3
    assert _text(h3) == TITLE


# ── ② base.html 두 자리 ───────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/", "/vehicles", "/calendar", "/accuracy", "/watchlist", "/vehicle/M1_1"])
@pytest.mark.parametrize("who", ["pub", "admin"])
def test_base_sentence_in_sidebar_and_mobile_footer(client, path, who):
    """base.html 을 쓰는 화면마다 두 번 — 사이드바(데스크톱)에 한 번, 모바일 푸터에 한 번, 각각 앵커 **바로 뒤**."""
    r = client.get(path, headers=PUB if who == "pub" else ADMIN)
    assert r.status_code == 200, (path, r.status_code)
    html = r.text
    assert html.count(SENT) == 2, f"{path}: 한 문장이 {html.count(SENT)}번(2번이어야 한다)"
    aside = html[html.index("<aside"):html.index("</aside>")]
    # 문장을 감싼 span 은 허용한다 — 줄 끝 외톨이('계산합니다.' 한 낱말)를 막는 줄바꿈 규칙이 그 span 에 있다
    side = re.search(re.escape(SIDEBAR_ANCHOR) + r"\s*<br>\s*(<span\b[^>]*>)?" + re.escape(SENT), aside)
    assert side, "사이드바: '참고용 분석 도구(투자 권유 아님)' 바로 뒤가 아니다"
    # 모바일 푸터는 줄(바깥 span)을 사람이 읽는 글자로 찾는다 — 기존 줄 안에 묶음 태그가 있다(3회차)
    lines = _footer_lines(html)
    texts = [_text(inner) for _, inner in lines]
    assert FOOTER_ANCHOR in texts, texts
    k = texts.index(FOOTER_ANCHOR)
    assert texts[k + 1:k + 2] == [SENT], f"모바일 푸터: '…입찰할 수 없습니다.' 바로 뒤 줄이 아니다 — {texts}"
    # 문장을 감싼 태그가 숨기지 않는다(푸터 줄 묶음이 데스크톱에서 lg:hidden 인 것은 부모의 몫 — 그 자리는 사이드바가 맡는다)
    for tag in (side.group(1) or "", lines[k + 1][0]):
        assert not re.search(r'class="[^"]*\b(?:hidden|sr-only|invisible)\b', tag) and "display:none" not in tag, tag


# ── ③ 과장 낱말 ───────────────────────────────────────────────────────
def test_no_exaggeration_words(client):
    """새 문구(블록 전체 + base 한 문장)에 결과를 약속하는 말이 없다. 랜딩 **전체**(사람이 읽는 글자)에도 없다 —
    2회차에 셋째 카드의 '손실을 막습니다'를 고쳐 이제 성립한다('확실'은 '불확실성'을 빼고 센다)."""
    land = client.get("/landing", headers=PUB).text
    new_text = _text(_block(land)) + " " + SENT
    assert not _promises(new_text), f"과장 낱말: {_promises(new_text)}"
    visible = _text(re.sub(r"<(script|style)\b.*?</\1>", " ", land, flags=re.S | re.I))
    assert CORE in visible and TITLE in visible, "보이는 글자 추출이 고장났다 — 이 검사가 공허해진다"
    assert not _promises(visible), f"랜딩에 결과 약속: {_promises(visible)}"
    home = client.get("/", headers=PUB).text
    aside = home[home.index("<aside"):home.index("</aside>")]
    assert SENT in aside and not _promises(SENT)


# ── ④ 2회차 손질(Steward 확정 10-02) ─────────────────────────────────────
def test_third_card_says_what_it_does_not_a_promise(client):
    """셋째 카드 '안전한 산정 로직' 본문 — 결과 약속('…로 손실을 막습니다.') 대신 하는 일('…자동 경고합니다.').
    앞부분은 그대로, 굵은 부분은 정확히 '사고·침수 이력이 있으면 입찰 중단 기준으로 자동 경고'."""
    sec = _core_section(client.get("/landing", headers=PUB).text)
    i = sec.index(CARDS[2])
    p = re.search(r"<p\b[^>]*>(.*?)</p>", sec[i:], re.S).group(1)
    assert _text(p) == CARD3_BODY, _text(p)
    bolds = re.findall(r"<b\b[^>]*>(.*?)</b>", p, re.S)
    assert [_text(b) for b in bolds] == [CARD3_BOLD]
    assert "손실을 막" not in _text(p)
    # 3회차: 굵은 '자동 경고'는 한 덩어리(768·큰글씨 320 에서 '자동 / 경고'로 갈렸다 — 문단은 이미 외톨이 규칙을 받고 있었다)
    assert bolds[0].rstrip().endswith(NOWRAP + CARD3_UNIT + "</span>"), bolds[0]


def test_footer_and_sidebar_lines_do_not_strand_the_last_word(client):
    """모바일 푸터 두 줄(기존 줄 + 새 문장)과 사이드바 문장은 줄 끝 외톨이를 막는 줄바꿈 규칙을 쓴다.
    실측: 큰글씨 390 에서 '…입찰할 수 / 없습니다.', 1024·1440 사이드바에서 '…가정해 / 계산합니다.' 가 한 낱말만 떨어졌다.
    3회차: 그 규칙만으로는 기존 줄이 '…입찰할 / 수 없습니다.'로 '할 수'를 갈랐다 — '입찰할 수 없습니다.'를 한 덩어리로."""
    html = client.get("/", headers=PUB).text
    lines = {_text(inner): (tag, inner) for tag, inner in _footer_lines(html)}
    assert FOOTER_ANCHOR in lines and SENT in lines, f"모바일 푸터 두 줄을 찾지 못했다 — {list(lines)}"
    aside = html[html.index("<aside"):html.index("</aside>")]
    side = re.search(re.escape(SIDEBAR_ANCHOR) + r"\s*<br>\s*(<span\b[^>]*>)" + re.escape(SENT), aside)
    assert side, "사이드바 문장을 감싼 태그가 없다"
    for tag in (lines[FOOTER_ANCHOR][0], lines[SENT][0], side.group(1)):
        assert re.search(r"text-wrap\s*:\s*pretty", tag), tag
    assert NOWRAP + FOOTER_UNIT + "</span>" in lines[FOOTER_ANCHOR][1], lines[FOOTER_ANCHOR][1]


# ── 대조군 — 지금(HEAD) 코드에서도 초록이어야 한다 ─────────────────────────
def test_control_anchors_still_where_the_block_expects_them(client):
    """앵커가 사라지거나 옮겨지면 위 테스트들이 엉뚱한 자리를 본다 — 앵커 자체를 따로 지킨다.
    셋째 카드는 1·2회차 모두 같은 앞부분으로 가리킨다(본문 뒷부분은 2회차에 바뀌었다 — 위 전용 테스트가 지킨다)."""
    land = client.get("/landing", headers=PUB).text
    sec = _core_section(land)
    assert re.findall(r"<h3[^>]*>([^<]*)</h3>", sec)[:3] == list(CARDS)
    assert CARD3_HEAD in sec[sec.index(CARDS[2]):], "셋째 카드 본문의 앞부분"
    assert land.index(CORE) < land.index(HONEST)
    home = client.get("/", headers=PUB).text
    # 푸터 기존 줄은 3회차에 안쪽 묶음 태그가 생겨 원문 HTML 로는 이어지지 않는다 — 사람이 읽는 글자로 센다(HEAD 에서도 1)
    assert home.count(SIDEBAR_ANCHOR) == 1 and _text(home).count(FOOTER_ANCHOR) == 1
