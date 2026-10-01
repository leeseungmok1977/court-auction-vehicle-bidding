# -*- coding: utf-8 -*-
"""PLAY-1(지시서 2026-10-01-04) — `/privacy` 출시 전 최종 문안을 화면에 고정한다.

문안의 원본은 `docs/compliance-review.md` §13.2 ①~⑧(준법 담당 확정, 2026-10-01)이다. 이 파일은
⑴ 그 절의 '교체 후' 인용문(`> ` 줄)이 렌더된 화면에 **한 글자도 다르지 않게** 있는지 문서에서 직접 읽어 대조하고,
⑵ 지시서가 정한 앵커(보호책임자 줄 · 표 안 '(예정)' 행 0 · '향후 도입 예정 기능' 블록 2곳 · 기관 4곳 전화·https URL ·
   개정 이력 마지막 줄 날짜 = app.py 시행일 · 자동 수집 행 불변)를 각각 단언한다.

② §1 ※ 문장은 **정정안(A)** 이다(오너 결정 2026-10-01: 정정안(A) — §13.6 N1). 원안(B)로 정해지면 `N1_SENTENCE`·`N1_OTHER` 두 상수와
privacy.html 의 그 한 구절만 바꾼다(문서 §13.2-② 인용문도 함께).

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`(autouse).
"""
import html as _html
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.test_rec1_r3_picks_gate_block import _no_network  # noqa: F401 — 외부 요청 0(시도 기록)
from web import db

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates" / "privacy.html"
DOC = ROOT / "docs" / "compliance-review.md"
_PUB = {"x-forwarded-for": "203.0.113.9"}

# ② N1 — 정정안(A). 원안(B)로 바뀌면 이 두 줄만 서로 바꾼다.
N1_SENTENCE = "서비스는 이를 특정 개인을 식별할 목적으로 수집·이용하지 않고 차주 등에 관한 정보를 따로 조회해 결합하지 않습니다."
N1_OTHER = "차주 등 개인 정보와 결합하지 않습니다"

# 자동 수집 행 — '수집 없음' 신고의 근거 문장이 든 행. 한 글자도 바꾸지 않는다(§13.2-① · test_no_visitor_tracking).
AUTO_ROW = ("<tr><td>자동 수집</td><td>접속 로그(IP·시각·요청), 기기·브라우저 정보, 쿠키·로컬 저장소(세션·설정 유지)"
            "<div class=\"text-mut text-xs mt-1\">웹서버 인프라 로그로만 사용합니다 — 분석·프로필 연결·외부 제공이 없고 14일 후 자동 삭제되므로, "
            "Google Play '데이터 안전'의 <b>수집</b>에는 해당하지 않아 스토어에 '수집 없음'으로 신고했습니다.</div></td><td>서비스 이용 시</td></tr>")
USER_ROW = ("<tr><td>이용자 입력</td><td>즐겨찾기·메모·최종입찰가 등 이용자가 직접 입력한 값 — <b>기기 내 로컬 저장소(localStorage)에만 "
            "보관되며 서버로 전송·수집하지 않음</b></td><td>기능 사용 시</td></tr>")

AGENCIES = [   # (이름, 전화 표기, https URL) — §13.4 에서 공식 사이트로 확인한 값
    ("개인정보분쟁조정위원회", "1833-6972", "https://www.kopico.go.kr"),
    ("개인정보침해신고센터(한국인터넷진흥원)", "국번 없이 118", "https://privacy.kisa.or.kr"),
    ("대검찰청", "국번 없이 1301", "https://www.spo.go.kr"),
    ("경찰청 사이버범죄 신고시스템", "국번 없이 182", "https://ecrm.police.go.kr"),
]
SECTIONS = ["1. 수집하는 항목과 방법", "2. 이용 목적", "3. 보유 및 파기", "4. 제3자 제공 및 처리위탁", "5. 이용자의 권리",
            "6. 아동의 개인정보", "7. 면책 및 데이터 성격", "8. 개인정보 보호책임자 및 문의처",
            "9. 개인정보의 안전성 확보 조치", "10. 권익침해 구제 방법", "11. 방침의 변경"]


@pytest.fixture
def page(monkeypatch):
    """공개 헤더로 /privacy 를 그려 (html, 컨텍스트) 를 돌려준다."""
    import web.app as A
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append(ctx)
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    r = TestClient(A.app).get("/privacy", headers=_PUB)
    assert r.status_code == 200
    return r.text, cap[-1]


def _text(h: str) -> str:
    """태그를 걷고 공백을 하나로 — 사람이 읽는 글자."""
    h = re.sub(r"<(style|script)\b.*?</\1>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _flat(h: str) -> str:
    """태그를 **공백 없이** 걷는다 — '<b>연락처</b>: x' 가 '연락처: x' 로 읽히게(인용문 대조용)."""
    h = re.sub(r"<(style|script)\b.*?</\1>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


def _section(h: str, title: str) -> str:
    i = h.index(f"<h2>{title}</h2>")
    j = h.find("<h2>", i + 4)
    return h[i:j if j > 0 else len(h)]


def _doc_quotes() -> list:
    """compliance-review §13.2 의 '교체 후' 인용문(`> ` 줄)을 화면 글자로 바꾼 목록."""
    src = DOC.read_text(encoding="utf-8")
    i = src.index("### 13.2 절별 교체 문안")
    blk = src[i:src.index("### 13.3", i)]
    out = []
    for line in blk.splitlines():
        if not line.startswith(">"):
            continue
        t = line[1:].strip()
        if not t:
            continue
        t = re.sub(r"^- ", "", t).replace("**", "")
        if t.startswith("… "):                       # ④ — 마지막 문장만 바꾼다는 표시
            t = t[2:]
        if t.startswith("연락처: "):                  # ⑤ — 괄호 안은 반영 지시(메일 링크·{{ contact }})이지 문언이 아니다
            t = t.split(" (메일 링크")[0]
        out.append(t)
    return out


# ── ⑴ 문서 §13.2 인용문 그대로 ───────────────────────────────────────────────
def test_문서_13_2_인용문이_화면에_그대로_있다(page):
    quotes = _doc_quotes()
    assert len(quotes) >= 30, f"§13.2 인용문을 못 읽었다({len(quotes)}줄) — 문서 구조가 바뀌었는지 본다"
    flat = _flat(page[0])
    missing = [q for q in quotes if q not in flat]
    assert not missing, "§13.2 '교체 후' 문안과 화면이 다르다:\n  " + "\n  ".join(missing)


# ── ⑵ 지시서 앵커 ─────────────────────────────────────────────────────────────
def test_절_번호와_제목(page):
    assert re.findall(r"<h2>([^<]+)</h2>", page[0]) == SECTIONS


def test_보호책임자_줄과_연락처는_설정값으로_그린다(page, monkeypatch):
    h, ctx = page
    sec8 = _section(h, "8. 개인정보 보호책임자 및 문의처")
    assert "<b>개인정보 보호책임자</b>: 경매로 내차GET 개인정보보호 담당(대표)" in sec8
    assert f'<b>연락처</b>: <a href="mailto:{ctx["contact"]}">{ctx["contact"]}</a>' in sec8
    assert ctx["contact"] == "koreanplus@gmail.com", "빈 DB 기본값(D2) — 라이브 설정값은 배포 뒤 확인(§13.9-2)"
    # 하드코딩이 아니라 {{ contact }} 다 — 설정을 바꾸면 따라 바뀐다
    src = TPL.read_text(encoding="utf-8")
    assert src.count('<a href="mailto:{{ contact }}">{{ contact }}</a>') == 1 and "koreanplus@gmail.com" not in src
    db.set_setting("privacy_contact", "privacy-test@example.com")
    import web.app as A
    h2 = TestClient(A.app).get("/privacy", headers=_PUB).text
    assert 'href="mailto:privacy-test@example.com"' in h2 and "koreanplus@gmail.com" not in h2


def test_표에는_예정_행이_없다(page):
    h = page[0]
    tables = re.findall(r"<table>.*?</table>", h, flags=re.S)
    assert len(tables) == 2, "§1 수집 항목 · §4 수탁 표"
    for t in tables:
        assert "(예정)" not in t, t[:200]
    rows1 = re.findall(r"<tr><td>", tables[0])
    rows4 = re.findall(r"<tr><td>", tables[1])
    assert len(rows1) == 2 and len(rows4) == 1, (len(rows1), len(rows4))
    assert AUTO_ROW in tables[0] and USER_ROW in tables[0]
    assert "<tr><td>Amazon Web Services (AWS, 서울 리전)</td><td>서버·데이터 호스팅</td></tr>" in tables[1]


def test_자동_수집_행은_한_글자도_바뀌지_않았다():
    src = TPL.read_text(encoding="utf-8")
    assert src.count(AUTO_ROW) == 1, "자동 수집 행 — 데이터 안전 '수집 없음' 신고의 근거 문장(바꾸지 않는다)"
    assert "분석·프로필 연결·외부 제공이 없고" in src


def test_향후_도입_예정_블록은_두_곳이다(page):
    h = page[0]
    assert h.count("<b>향후 도입 예정 기능 (현재 적용되지 않음)</b>") == 2
    s1, s4 = _section(h, "1. 수집하는 항목과 방법"), _section(h, "4. 제3자 제공 및 처리위탁")
    for sec, items in ((s1, ("계정(Google 로그인 도입 시)", "결제·구독(구독 결제 도입 시)", "광고(광고 도입 시)")),
                       (s4, ("Google Firebase Authentication — Google 로그인·본인 식별",
                             "Google Play Billing / Developer API — 구독 결제·검증·해지 반영", "Google AdMob — 광고 노출·측정"))):
        blk = sec[sec.index('<div class="plan">'):]
        blk = blk[:blk.index("</div>")]
        assert "향후 도입 예정 기능 (현재 적용되지 않음)" in blk
        for it in items:
            assert it in blk, it
    # 국외 이전 문장은 '(예정)' Google 기능에 딸린 말 — 블록 안으로만 옮겼다(지금 이전이 일어나는 것처럼 읽히지 않게)
    assert "Google 서비스 이용에 따라 정보가 국외" not in h
    assert "이 기능들을 도입하면 정보가 국외(Google 데이터센터)로 이전·처리될 수 있으며" in s4


def test_N1_정정안과_5절_계정정보(page):
    t = _text(page[0])
    assert N1_SENTENCE in t and N1_OTHER not in t
    assert "특정 개인을 식별하는 개인정보가 아닙니다" not in t, "교체 전 문장"
    assert "서버에 보관하는 계정 정보가 없습니다" in t and "서버에 보관되는 개인정보가 없습니다" not in t


def test_권익침해_구제_기관_4곳_전화와_https(page):
    sec = _section(page[0], "10. 권익침해 구제 방법")
    lis = re.findall(r"<li>(.*?)</li>", sec, flags=re.S)
    assert len(lis) == 4
    for (name, tel, url), li in zip(AGENCIES, lis):
        host = url.split("://", 1)[1]
        # 2회차: '국번 없이 NNN' 은 한 덩어리(320px 에서 번호가 다음 줄에 홀로 떨어졌다) — 글자는 그대로, 감싸는 태그만
        shown = f'<span class="tel">{tel}</span>' if tel.startswith("국번 없이") else tel
        assert li == f'{name}: {shown} (<a href="{url}">{host}</a>)', li
    assert "http://" not in sec and "ecrm.cyber.go.kr" not in sec


def test_개정_이력_마지막_줄_날짜는_시행일이다(page):
    h, ctx = page
    sec = _section(h, "11. 방침의 변경")
    ul = sec[sec.index('<ul class="hist">'):]
    ul = ul[:ul.index("</ul>")]
    # 2회차: 날짜가 `<span class="hd">` 열로 감싸였다(hanging indent) — 사람이 읽는 글자로 대조한다
    lines = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<li>(.*?)</li>", ul, flags=re.S)]
    dates = [x.split(" ", 1)[0] for x in lines]
    assert len(lines) == 5 and lines[0] == "2026-09-06 제정"
    assert dates == sorted(dates) and len(set(dates)) == 5, dates
    assert dates[-1] == ctx["updated"], "개정 이력 마지막 줄 = app.py privacy() 의 updated — 같은 커밋에서 함께 바꾼다(§13.2-⑨)"
    assert f"시행일 {ctx['updated']}" in h


# ── 2회차(지시서 2026-10-01-16) ───────────────────────────────────────────────
def _doc_item6() -> tuple:
    """compliance-review §13.2-⑥(새 §9 안전성 확보 조치) 인용문 — (도입 문장, 조치 목록)."""
    src = DOC.read_text(encoding="utf-8")
    blk = src[src.index("### 13.2 절별 교체 문안"):src.index("### 13.3")]
    blk = blk[blk.index("**⑥ "):]
    blk = blk[:blk.index("\n**⑦")] if "\n**⑦" in blk else blk
    quoted = [ln[1:].strip() for ln in blk.splitlines() if ln.startswith(">") and ln[1:].strip()]
    items = [re.sub(r"^- ", "", q).replace("**", "") for q in quoted if q.startswith("- ")]
    intro = [q.replace("**", "") for q in quoted if not q.startswith("- ") and not q.startswith("**9.")]
    return intro, items


def test_M60_안전성_조치_목록은_문서_6과_정확히_같다(page):
    """1회차 테스트는 '문서 ⊂ 화면'만 봤다 — 화면에 확인되지 않은 조치('최신 보안 패치' 등)를 더해도 빨간불이 안 켜졌다(qa M60).
    §9 는 **실제로 하고 있는 조치만** 적는 절이다(§13.2-⑥ D5). 목록이 문서와 같은 개수·같은 순서·같은 글자여야 한다."""
    intro, items = _doc_item6()
    assert len(items) == 4 and intro, f"§13.2-⑥ 을 못 읽었다({len(items)}개) — 문서 구조가 바뀌었는지 본다"
    sec = _section(page[0], "9. 개인정보의 안전성 확보 조치")
    shown = [_flat(li) for li in re.findall(r"<li>(.*?)</li>", sec, flags=re.S)]
    assert shown == items, f"화면 §9 목록과 문서 §13.2-⑥ 이 다르다:\n  화면 {shown}\n  문서 {items}"
    paras = [_flat(p) for p in re.findall(r"<p>(.*?)</p>", sec, flags=re.S)]
    assert paras == intro, (paras, intro)


def test_회색_글자는_앱과_같은_토큰이다():
    """자체 `--mut:#64748d` 는 #f6f9fc 위 4.49:1(AA 미달) — 페이지 바탕의 ※ 문단 두 곳과 바닥글이 그 위에 있다.
    앱은 이미 `mut: #5e6c85`(tailwind.config.js — 주석 '구 #64748d=4.49'). 같은 값이면 5.02:1(흰 위 5.30:1)."""
    src = TPL.read_text(encoding="utf-8")
    assert "--mut:#5e6c85" in src and "#64748d" not in src
    cfg = (ROOT / "tailwind.config.js").read_text(encoding="utf-8")
    assert 'mut: "#5e6c85"' in cfg, "앱 토큰이 바뀌면 이 문서도 함께 본다"

    def _lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    ratio = (_lum("#f6f9fc") + 0.05) / (_lum("#5e6c85") + 0.05)
    assert ratio >= 4.5, ratio


def test_국번_없이_번호는_한_덩어리이고_글자는_그대로(page):
    h = page[0]
    assert ".tel{white-space:nowrap}" in TPL.read_text(encoding="utf-8")
    tels = re.findall(r'<span class="tel">([^<]*)</span>', h)
    assert tels == ["국번 없이 118", "국번 없이 1301", "국번 없이 182"]
    assert "국번 없이 118" in _flat(h) and "국번 없이 1301" in _flat(h) and "국번 없이 182" in _flat(h)


def test_개정_이력은_날짜_열과_설명_열로_선다(page):
    """둘째 줄이 날짜 아래로 파고들지 않게(hanging indent) — 날짜를 한 열로 세운다. 글자는 그대로(위 날짜 테스트·인용문 대조)."""
    src = TPL.read_text(encoding="utf-8")
    assert "ul.hist{list-style:none;padding-left:0}" in src
    # 날짜 칸은 고정 폭 — 서체 숫자 폭이 글자마다 달라 max-content 만으로는 줄마다 설명 시작점이 어긋났다(실측 80~85px)
    assert ".hist li{display:grid;grid-template-columns:minmax(max-content,5.75em) minmax(0,1fr);column-gap:.6em}" in src
    sec = _section(page[0], "11. 방침의 변경")
    ul = sec[sec.index('<ul class="hist">'):]
    ul = ul[:ul.index("</ul>")]
    lis = re.findall(r"<li>(.*?)</li>", ul, flags=re.S)
    assert len(lis) == 5 and all(re.match(r'<span class="hd">\d{4}-\d{2}-\d{2}</span> \S', li) for li in lis), lis
