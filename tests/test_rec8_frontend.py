# -*- coding: utf-8 -*-
"""REC-8 화면 쪽(지시서 2026-10-01-04) — 서버 쪽(2026-10-01-03, test_rec8_judgment_filter·test_rec8_run_status)의 짝.

⑴ 진입점 6곳(홈 '더보기 →'·'✅ 검토 가능' · 랜딩 '지금 검토 가능한 물건 →'·'유망 물건 보기' · 목록 '🎯 검토 추천 ✕'·'되팔이 기준 보기')이
   저장 판정 문자열(`?judgment=입찰 검토 가능`)이 아니라 '지금 입찰 추천' 칸(`?bucket=review&sort=expected`)으로 간다. 글자는 그대로다
   (이름 통일은 REC-2 오너 결정). 서버는 옛 링크도 같은 목록을 보여 주지만, 칸 링크가 더 빠른 길을 탄다(backend §1~3 요점).
⑵ base.html 폴링이 실행 중 홈 '지금 입찰 추천'(#kpi-ok)·'유찰 대기'(#kpi-wait)를 덮지 않는다(그 키는 서버가 뺐다).
⑶ 홈 임박 알림 머리의 '전체 N건 →'이 알림과 **같은 집합**을 연다 — 알림 = review 칸 ∩ 3일 이내(service._alert_rows).

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`.
"""
import re
from pathlib import Path
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _ge300, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec8_judgment_filter import _resale
from web import service

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates"
_PUB = {"x-forwarded-for": "203.0.113.9"}
REVIEW = "/vehicles?bucket=review&sort=expected"
# (템플릿, 링크 글자의 앞부분) — 진입점 6곳(backend 명세 §4.3)
ENTRY = [("dashboard.html", "더보기 →"), ("dashboard.html", "✅ 검토 가능"),
         ("landing.html", "지금 검토 가능한 물건 →"), ("landing.html", "유망 물건 보기"),
         ("vehicles.html", "🎯 검토 추천 ✕"), ("vehicles.html", "되팔이 기준 보기")]


@pytest.fixture
def get(monkeypatch):
    import web.app as A
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append(ctx)
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    c = TestClient(A.app)

    def _get(url):
        cap.clear()
        r = c.get(url, headers=_PUB)
        assert r.status_code == 200, (url, r.status_code)
        return cap[-1], r.text
    return _get


def _href_of(src: str, text: str):
    """`<a href="…" …>text…` 의 href(여는 태그 바로 뒤 글자가 text 로 시작하는 첫 a)."""
    m = re.search(r'<a href="([^"]+)"[^>]*>\s*' + re.escape(text), src)
    return m.group(1) if m else None


# ── ⑴ 진입점 ────────────────────────────────────────────────────────────
def test_템플릿에_저장_판정_문자열_링크가_없다():
    for f in sorted(TPL.glob("*.html")):
        s = f.read_text(encoding="utf-8")
        for bad in ("judgment=입찰 검토 가능", "judgment=" + quote("입찰 검토 가능"), "judgment=입찰+검토+가능"):
            assert bad not in s, f"{f.name}: {bad}"


@pytest.mark.parametrize("tpl,text", ENTRY)
def test_진입점_6곳은_칸으로_간다(tpl, text):
    src = (TPL / tpl).read_text(encoding="utf-8")
    assert src.count(text) == 1, f"{tpl}: '{text}' 앵커가 하나여야 한다 — 글자가 바뀌었는지 본다(이름 통일은 REC-2)"
    assert _href_of(src, text) == REVIEW, (tpl, text, _href_of(src, text))


def test_렌더된_화면의_진입점도_칸이다(mk, get):
    _resale(mk, "RV1", sale_date=_d(5))
    _, home = get("/")
    _, landing = get("/landing")
    _, prom = get("/vehicles?promising=1")
    _, use = get("/vehicles?usepick=1")
    for html, text in ((home, "✅ 검토 가능"), (landing, "지금 검토 가능한 물건 →"), (landing, "유망 물건 보기"),
                       (prom, "🎯 검토 추천 ✕"), (use, "되팔이 기준 보기")):
        assert _href_of(html, text) == REVIEW.replace("&", "&amp;") or _href_of(html, text) == REVIEW, (text, _href_of(html, text))


def test_칸_링크는_홈_지금_입찰_추천_수와_같은_목록을_연다(mk, get):
    """링크를 바꾼 이유가 '카드 수 = 목록 수'다 — 템플릿의 그 href 그대로 열어 홈 칸 수와 대조한다(공허 통과 방지: 칸 밖 물건을 섞는다)."""
    _resale(mk, "RV1", sale_date=_d(5))
    _resale(mk, "RV2", sale_date=_d(8), min_sale_price=11_000_000)
    _ge300(mk)                                              # 저장 '입찰 검토 가능' · 칸 밖(이번 회차 최저가 미확인)
    _resale(mk, "STOP", runnable="no")                      # 저장 '입찰 검토 가능' · 칸 밖(시동 불가)
    href = _href_of((TPL / "dashboard.html").read_text(encoding="utf-8"), "✅ 검토 가능")
    ctx, _ = get(href)
    lc = service.lifecycle_partition()
    assert ctx["total"] == lc["review"] == 2 and {r["id"] for r in ctx["rows"]} == {"RV1", "RV2"}


# ── ⑵ 폴링 ──────────────────────────────────────────────────────────────
def test_폴링은_지금_입찰_추천_유찰_대기_KPI를_덮지_않는다():
    base = (TPL / "base.html").read_text(encoding="utf-8")
    assert not re.search(r"setTxt\(\s*['\"]kpi-(ok|wait)['\"]", base), "실행 중 저장 판정 문자열 수로 홈 칸 수를 덮던 줄"
    assert re.search(r"setTxt\(\s*'kpi-upcoming'\s*,\s*fmt\(d\.upcoming\)\)", base), "같은 정의(홈 upcoming30)인 수는 그대로 갱신"
    assert re.search(r"setTxt\(\s*'kpi-pending'\s*,\s*fmt\(d\.pending\)\)", base)
    for f in sorted(TPL.glob("*.html")):         # 다른 스크립트가 같은 칸을 덮지 않는다
        s = f.read_text(encoding="utf-8")
        assert not re.search(r"getElementById\(\s*['\"]kpi-(ok|wait)['\"]", s), f.name
    # 홈 칸 숫자 자리는 그대로 있다 — 서버가 lifecycle 로 그린다
    dash = (TPL / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="kpi-ok">{{ lifecycle.review }}</span>' in dash and 'id="kpi-wait">{{ lifecycle.wait }}</span>' in dash


# ── ⑶ 알림 '전체 N건 →' ──────────────────────────────────────────────────
@pytest.fixture
def alerts(mk):
    """review 칸 3일 이내 7대(알림 6장 + '전체 7건') + 3일 이내지만 칸 밖 2대 + 칸 안이지만 3일 밖 1대."""
    for i in range(7):
        _resale(mk, f"AL{i}", sale_date=_d(1 + i % 3), min_sale_price=9_000_000 + i * 100_000)
    _resale(mk, "ALSTOP", runnable="no", sale_date=_d(2))                     # 3일 이내 · 시동 불가(칸 밖)
    mk("ALWAIT", judgment="유찰 대기", appraisal_value=30_000_000, min_sale_price=29_000_000,
       median_price=30_000_000, sale_date=_d(1))                               # 3일 이내 · 유찰 대기(칸 밖)
    _resale(mk, "ALFAR", sale_date=_d(9))                                       # 칸 안 · 3일 밖


def _ids(get, url):
    ctx, _ = get(url)
    ids = [r["id"] for r in ctx["rows"]]
    for p in range(2, ctx["total_pages"] + 1):
        ids += [r["id"] for r in get(f"{url}&page={p}")[0]["rows"]]
    return ctx, set(ids)


def test_알림_전체_링크는_알림과_같은_집합을_연다(alerts, get):
    al = {a["id"] for a in service.alert_items(3)}
    assert al == {f"AL{i}" for i in range(7)}, "전제 — 알림은 칸 안 · 3일 이내 7대"
    _, home = get("/")
    m = re.search(r'<a href="([^"]+)"[^>]*>전체 (\d+)건 →</a>', home)
    assert m, "알림이 6장을 넘으면 '전체 N건 →' 이 그려진다"
    href = m.group(1).replace("&amp;", "&")
    assert href == "/vehicles?bucket=review&upcoming=3&sort=sale_date"
    ctx, ids = _ids(get, href)
    assert ids == al and ctx["total"] == len(al) == int(m.group(2)), (ids ^ al, ctx["total"], m.group(2))
    # 대조 — 옛 링크(?upcoming=3)는 칸 밖 물건까지 열었다(이 픽스처가 둘을 가르는지 확인 · 공허 통과 방지)
    _, old = _ids(get, "/vehicles?upcoming=3&sort=sale_date")
    assert {"ALSTOP", "ALWAIT"} <= old and old != al
