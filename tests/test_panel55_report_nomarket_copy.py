"""PANEL-55 — 시세 미산정 리포트의 안내는 **보는 사람에게 실제로 있는 버튼**만 말해야 한다.

2026-09-24 라이브 재현(공개 헤더 `X-Forwarded-For`): `/vehicle/2025타경56677_1/report` 가
"물건 상세에서 [다시 분석] 후 다시 시도하세요" 를 냈다. 그런데 그 버튼은 detail.html 이
`{% if can_analyze and v.status == '완료' and is_admin(request) %}` 로 **관리자에게만** 그린다.
공개 사용자는 시키는 대로 상세로 가도 버튼이 없다 — 막다른 길이다.

고친 뒤: 관리자(SSH 터널 = loopback Host, XFF 없음)는 기존 문구 그대로(버튼이 실제로 있다),
공개 사용자(nginx 경유 = XFF 존재)는 없는 버튼을 언급하지 않는 문구. 판정 기준은 새로 만들지
않고 기존 `is_admin(request)` 하나를 쓴다 — `tests/test_exposure.py` 와 같은 헤더 규약.

반증 기록(2026-09-24): report.html 의 `{% if is_admin(request) %}` 게이트를 지우고 이 파일을
돌리면 `test_public_copy_never_names_the_admin_button` 과
`test_report_template_gates_the_button_mention` 이 실패한다.

2회차(검수 지적 2·3, 지시서 2026-09-24-09): 공개 문구에서 `아직`(한 낱말짜리 시점 약속 — 이 분기
공개 431건 중 391건은 기일이 지났다)을 빼고, 그릇을 각주(`.note`)에서 `.sec-empty` 로 바꾸고,
'물건 상세' 를 sticky 바의 `상세로` 와 같은 핸들러(`_reportBack`)로 링크했다. 관리자 문구의 `아직` 은
유지한다(행동할 수 있는 사람이다). 앵커는 두 변형이 모두 품는 `산정되지 않아 종합 리포트를` 로 옮겼다.
반증(2회차): 공개 문구에 `아직` 을 되돌리면 `test_public_copy_promises_no_timing` 이 실패한다.

3회차(PANEL-56 교차검수 처방, 지시서 2026-09-24-13): stop 톤(`침수·전손 의심 — 입찰 보류` 6건 · `시동·운행 불가 — 판정 보류`
13건)은 이 분기에서 본문이 없어 마스트헤드 알약이 유일한 위험 신호였는데 그 알약은 wait 와 같은 흰 외곽선(남색 위 의미색
중화가 설계 의도). 두 검수자가 같이 잡았다 — 침수차에 대해 페이지가 "시세만 없다"고 말한다. 처방(design-critic 안 채택):
마스트헤드에 빨강을 넣지 않고 **본문 첫 문장이 판정**이 된다 — `<b>{bidst.label}입니다.</b> 시세가 산정되지 않아 종합
리포트**도** 만들 수 없습니다.` 그릇에는 `is-stop` 클래스 → 왼쪽 레일만 로즈(`.verdict.is-stop` 과 같은 꼴). wait 톤은 그대로.
자잘한 셋(design-critic 3): `감정가·최저매각가` nowrap · 관리자 동사 `생성할`→`만들` 통일 · 관리자 '물건 상세' 도 같은 링크.
⚠ 동사 통일로 `종합 리포트를 만들 수 없습니다` 는 더는 공개 전용 조각이 아니다 — 관리자/공개를 가르는 것은 `아직`·`[다시 분석]`
(관리자) 과 `감정가·최저매각가 … 그대로 확인하실 수 있습니다`(공개) 다.
반증(3회차): stop 분기(`{% if _stop0 %}…`)를 지우면 `test_stop_tone_copy_leads_with_the_verdict` 가 실패한다.
"""
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

_PUB = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}
_TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"

# 두 변형에 공통인 조각 — 분기 자체가 렌더됐는지 확인하는 앵커
# (앞머리는 더는 공통이 아니다: 관리자 '시세가 아직 산정되지 않아 …' / 공개 '시세가 산정되지 않아 …';
#  3회차부터 조사도 갈린다: wait '종합 리포트를' / stop '종합 리포트도' — 그래서 조사 앞에서 끊는다)
_ANCHOR = "산정되지 않아 종합 리포트"
# 문구를 담는 그릇 — 각주(.note)가 아니라 빈 섹션 블록(.sec-empty). wait 톤의 여는 태그 원문.
_BOX_OPEN = '<div class="sec-empty">'
# stop 톤은 `is-stop` 이 붙는다 — 두 꼴을 모두 품는 접두
_BOX_OPEN_ANY = '<div class="sec-empty'
# 템플릿 원문의 여는 태그(렌더 전) — 원문 검사는 이걸로 그릇을 찾는다
_BOX_OPEN_SRC = "<div class=\"sec-empty{{ ' is-stop' if _stop0 }}\">"
_BOX_OPEN_STOP = '<div class="sec-empty is-stop">'
# 관리자 변형에만 있어야 하는 것: 존재하는 버튼의 이름
_ADMIN_ONLY = "다시 분석"
# 공개 변형에 있어야 하는 것 (3회차부터 관리자도 같은 동사를 쓴다 — 공개 **전용** 조각은 아래 _PUBLIC_TAIL)
_PUBLIC_LINE = "종합 리포트를 만들 수 없습니다"
# 공개 변형에만 있는 꼬리 — 관리자는 [다시 분석] 을 시키지 법원 자료를 안내하지 않는다
_PUBLIC_TAIL = "그대로 확인하실 수 있습니다"
# 390 에서 `감정가·` 가 줄끝 고아가 됐다(design-critic 3) — 한 덩어리로 묶는다
_NOWRAP_PAIR = '<span style="white-space:nowrap">감정가·최저매각가</span>'
# 3회차에 버린 동사 — 관리자 '생성할' / 공개 '만들' 이 갈려 있었다
_OLD_VERB = "생성할"
# 공개 문구가 **하면 안 되는 약속** — 코드로 보장되지 않는 시점 (지시서 ⚠)
# `아직` 도 시점 약속이다(2회차 검수 지적 3): 열에 아홉에게는 '영영'이다.
_TIMING_WORDS = ("곧", "매일", "잠시 후", "자동으로 다시", "다시 시도", "아직")
# 공개 문구의 '물건 상세' 링크 — sticky 바의 `상세로` 와 같은 핸들러여야 한다(히스토리 설계 우회 금지)
_BACK_HANDLER = 'onclick="return _reportBack(event)"'


@pytest.fixture
def client(tmp_path, monkeypatch):
    """시세 미산정(median_price=None) 물건 하나 — `{% if report %}` 의 else 분기를 실제로 탄다."""
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p55.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "nomed_1", "folder_key": "nomed_1", "case_no": "2026타경5501",
                       "judgment": "시세 정보 없음", "min_sale_price": 9_000_000,
                       "appraisal_value": 12_000_000, "median_price": None})
    # stop 톤 둘 — 운영 실측(2026-09-24) 침수 6건(`2025타경53062_1`) · 시동 불가 13건(`2025타경6000_1`) 과 같은 상태.
    # bid_state 는 accident_grade=='flood' → blocked/stop, runnable=='no' → lowconf/stop (service.bid_state 원문).
    db.upsert_vehicle({**_BASE, "id": "nomed_flood", "folder_key": "nomed_flood", "case_no": "2026타경5502",
                       "judgment": "시세 신뢰도 낮음, 수동 검토", "accident_grade": "flood",
                       "market_confidence": 0, "market_confidence_label": "낮음",
                       "min_sale_price": 9_000_000, "appraisal_value": 12_000_000, "median_price": None})
    db.upsert_vehicle({**_BASE, "id": "nomed_nostart", "folder_key": "nomed_nostart", "case_no": "2026타경5503",
                       "judgment": "시세 신뢰도 낮음, 수동 검토", "runnable": "no",
                       "market_confidence": 0, "market_confidence_label": "낮음",
                       "min_sale_price": 9_000_000, "appraisal_value": 12_000_000, "median_price": None})
    import web.app as A
    return TestClient(A.app)


def _note(html: str) -> str:
    """앵커가 든 `.sec-empty` 블록 하나만 잘라 낸다 — 페이지 다른 곳의 낱말이 검사를 오염시키지 않게."""
    i = html.index(_ANCHOR)
    return html[html.rindex(_BOX_OPEN_ANY, 0, i):html.index("</div>", i)]


def _bidst(vid: str) -> dict:
    """판정 단일 소스 — 화면의 첫 문장이 이 라벨을 원문 그대로 말해야 한다."""
    from web import db
    return service.bid_state(db.get_vehicle(vid), BT, service.load_config())


def test_fixture_actually_hits_the_unpriced_branch(client):
    """픽스처가 else 분기를 못 타면 아래 검사는 전부 공허하다(CLAUDE.md '공허 통과')."""
    html = client.get("/vehicle/nomed_1/report", headers=_PUB).text
    assert _ANCHOR in html
    assert '<span class="sec-no">' not in html, "본문 01~12 가 렌더됐다 — 시세 미산정 분기가 아니다"


def test_public_copy_never_names_the_admin_button(client):
    """공개 사용자에게는 존재하지 않는 `[다시 분석]` 을 시키지 않는다."""
    r = client.get("/vehicle/nomed_1/report", headers=_PUB)
    assert r.status_code == 200
    note = _note(r.text)
    assert _PUBLIC_LINE in note
    assert _ADMIN_ONLY not in note, f"공개 문구가 관리자 전용 버튼을 말한다: {note}"
    assert _ADMIN_ONLY not in r.text, "페이지 어딘가에 '다시 분석' 이 남아 있다"


def test_public_copy_promises_no_timing(client):
    """'시세가 잡히면 …' 같은 시점·재시도 약속은 코드가 보장하지 않는다 — 넣지 않는다.
    requery_missing_market 은 기일 30일 창 안의 물건만 다시 묻고, 기일이 지난 물건은 영영 안 묻는다."""
    note = _note(client.get("/vehicle/nomed_1/report", headers=_PUB).text)
    hit = [w for w in _TIMING_WORDS if w in note]
    assert not hit, f"공개 문구에 시점·재시도 약속이 있다: {hit} — {note}"


def test_public_copy_links_detail_with_the_same_back_handler(client):
    """'물건 상세' 는 링크다 — 그리고 sticky 바 `상세로` 가 쓰는 바로 그 `_reportBack` 을 쓴다.
    일반 링크면 [목록, 상세, 리포트, 상세]로 히스토리가 쌓여 상세의 '뒤로'가 리포트로 간다."""
    html = client.get("/vehicle/nomed_1/report", headers=_PUB).text
    note = _note(html)
    m = re.search(r'<a href="/vehicle/nomed_1"([^>]*)>물건 상세</a>', note)
    assert m, f"공개 문구에 '물건 상세' 링크가 없다: {note}"
    assert _BACK_HANDLER in m.group(0), "링크가 sticky 바와 다른 핸들러를 쓴다"
    assert "function _reportBack(" in html, "핸들러 정의가 페이지에 없다"
    # 같은 핸들러를 sticky 바 버튼도 쓴다 — 둘이 갈리면 여기서 울린다
    assert html.count(_BACK_HANDLER) == 2, "핸들러 사용처가 2(버튼+링크)가 아니다"


def test_copy_is_body_text_not_a_footnote(client):
    """이 분기에서 이 문장은 페이지의 **유일한 본문**이다 — 각주(.note) 그릇이면 면책보다 연해진다(검수 지적 2).
    `.sec-empty`(기존 규칙) 에 담고, 첫 문장(사실)만 굵게. 카드로 감싸지 않는다(프레임 두 겹)."""
    for hdr in (_PUB, _TUNNEL):
        html = client.get("/vehicle/nomed_1/report", headers=hdr).text
        note = _note(html)
        assert note.startswith(_BOX_OPEN)
        assert re.match(r'<div class="sec-empty"><b[^>]*>[^<]*산정되지 않아 종합 리포트를 [^<]*니다\.</b> ', note), \
            f"첫 문장(사실)이 굵게 시작하지 않는다: {note[:120]}"
        # 그릇 바로 바깥이 카드가 아니다
        i = html.index(note)
        assert html[html.rindex("<section", 0, i):i].count('class="card"') == 0, "빈 상태가 카드 껍데기 안에 있다"
        assert 'class="note"' not in note
        for banned in ("var(--red)", "var(--amber)"):
            assert banned not in note, f"'해당 없음'에 경고색이 붙었다: {banned}"


def test_admin_copy_keeps_the_button_it_actually_has(client):
    """관리자(터널)는 버튼이 실제로 있으니 기존 문구를 유지한다."""
    r = client.get("/vehicle/nomed_1/report", headers=_TUNNEL)
    assert r.status_code == 200
    note = _note(r.text)
    assert "[" + _ADMIN_ONLY + "]" in note
    assert _PUBLIC_TAIL not in note and _NOWRAP_PAIR not in note, "관리자에게 공개 꼬리(법원 자료 안내)가 나갔다"
    assert "아직" in note, "관리자 문구의 '아직' 은 유지한다 — 다시 분석을 누를 수 있는 사람이다"
    # 3회차: 동사는 공개와 같다 — '생성할' 은 버렸다
    assert "만들 수 없습니다" in note and _OLD_VERB not in note


def test_forged_loopback_host_with_xff_gets_public_copy(client):
    """Host 를 127.0.0.1 로 위조해도 nginx 가 붙인 XFF 가 있으면 공개 문구(test_exposure 와 같은 규약)."""
    r = client.get("/vehicle/nomed_1/report", headers={"host": "127.0.0.1", "x-forwarded-for": "203.0.113.7"})
    assert _ADMIN_ONLY not in _note(r.text)


# ── 3회차: stop 톤이면 본문 첫 문장이 판정이다 (PANEL-56 교차검수 처방) ─────────

def test_stop_fixtures_actually_hit_stop_tone(client):
    """공허 통과 방지: 두 픽스처가 실제로 stop 톤 · 시세 없는 분기를 탄다."""
    for vid, state in (("nomed_flood", "blocked"), ("nomed_nostart", "lowconf")):
        st = _bidst(vid)
        assert st["tone"] == "stop" and st["state"] == state, f"{vid}: {st['state']}/{st['tone']}"
        assert " — " in st["label"]
        html = client.get(f"/vehicle/{vid}/report", headers=_PUB).text
        assert _ANCHOR in html and '<span class="sec-no">' not in html


@pytest.mark.parametrize("vid", ["nomed_flood", "nomed_nostart"])
@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_stop_tone_copy_leads_with_the_verdict(client, vid, hdr):
    """stop 이면 첫 문장 = `{bidst.label}입니다.`(라벨 원문 그대로, 굵게), 다음 문장은 '종합 리포트**도**'.
    그릇에 `is-stop` — 왼쪽 레일이 로즈가 되는 훅(규칙은 템플릿 <style>, 인라인 빨강은 없다)."""
    html = client.get(f"/vehicle/{vid}/report", headers=hdr).text
    note = _note(html)
    label = _bidst(vid)["label"]
    lead = f'{_BOX_OPEN_STOP}<b style="color:var(--ink)">{label}입니다.</b> 시세가 '
    assert note.startswith(lead), f"첫 문장이 판정이 아니다: {note[:160]}"
    rest = note[len(lead):]
    if hdr is _TUNNEL:
        assert rest.startswith("아직 산정되지 않아 종합 리포트도 만들 수 없습니다. ")
        assert "[" + _ADMIN_ONLY + "]" in rest and _PUBLIC_TAIL not in rest
    else:
        assert rest.startswith("산정되지 않아 종합 리포트도 만들 수 없습니다. ")
        assert _NOWRAP_PAIR in rest and _PUBLIC_TAIL in rest and _ADMIN_ONLY not in rest
    # 판정 문장은 하나뿐, 라벨은 접지 않는다(judge_label 의 nowrap span 이 본문에 오지 않는다)
    assert note.count("입니다.</b>") == 1
    assert "whitespace-nowrap" not in note
    for banned in ("var(--red)", "var(--amber)", 'class="note"'):
        assert banned not in note, f"{banned} 가 본문에 인라인으로 들어왔다"
    # 마스트헤드 알약에는 여전히 의미색이 없다(처방: 빨강은 본문 레일에만)
    mh = html[html.index("<!-- 마스트헤드 -->"):html.index("</header>")]
    assert 'class="masthead is-stop"' in mh
    badges = mh[mh.index('<div class="badges">'):mh.index('<div class="mh-eyebrow">')]
    assert '<div class="badge judge">' in badges, "판정 알약이 없다 — 픽스처가 점수 배지 쪽으로 갔다"
    assert "var(--red)" not in badges and "style=" not in badges and "rgba(225,29,72" not in badges


@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_wait_tone_copy_is_unchanged(client, hdr):
    """wait 톤(nomed_1)은 3회차 전과 같은 첫 문장 — 판정 문장도, is-stop 도 붙지 않는다."""
    note = _note(client.get("/vehicle/nomed_1/report", headers=hdr).text)
    assert _bidst("nomed_1")["tone"] != "stop"
    first = ('<div class="sec-empty"><b style="color:var(--ink)">시세가 아직 산정되지 않아 종합 리포트를 만들 수 없습니다.</b> '
             if hdr is _TUNNEL else
             '<div class="sec-empty"><b style="color:var(--ink)">시세가 산정되지 않아 종합 리포트를 만들 수 없습니다.</b> ')
    assert note.startswith(first), note[:160]
    assert "입니다.</b>" not in note and "is-stop" not in note and "리포트도" not in note


@pytest.mark.parametrize("vid", ["nomed_1", "nomed_flood"])
@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_copy_never_says_generate(client, vid, hdr):
    """동사 통일 — 관리자 '생성할 수 없습니다' 는 버렸다. 공개·관리자·wait·stop 전부 '만들 수 없습니다'."""
    note = _note(client.get(f"/vehicle/{vid}/report", headers=hdr).text)
    assert _OLD_VERB not in note and "만들 수 없습니다" in note


@pytest.mark.parametrize("vid", ["nomed_1", "nomed_flood"])
def test_appraisal_pair_never_leaves_an_orphan(client, vid):
    """`감정가·최저매각가` 는 한 덩어리(nowrap) — 390 에서 `감정가·` 만 줄끝에 남았다."""
    note = _note(client.get(f"/vehicle/{vid}/report", headers=_PUB).text)
    assert _NOWRAP_PAIR in note
    assert note.count("감정가") == 1, "묶이지 않은 '감정가' 가 따로 있다"


def test_admin_detail_link_uses_the_same_back_handler(client):
    """관리자 문구의 '물건 상세' 도 링크다 — 거기 가서 [다시 분석] 을 누르라는 사람이 관리자다. 핸들러는 공개와 같은 _reportBack."""
    html = client.get("/vehicle/nomed_1/report", headers=_TUNNEL).text
    note = _note(html)
    m = re.search(r'<a href="/vehicle/nomed_1"([^>]*)>물건 상세</a>에서 <b>\[다시 분석\]</b>', note)
    assert m, f"관리자 문구에 '물건 상세' 링크가 없다: {note}"
    assert _BACK_HANDLER in m.group(0)
    assert html.count(_BACK_HANDLER) == 2, "핸들러 사용처가 2(버튼+링크)가 아니다"


# ── 템플릿 원문 검사 — 렌더 검사가 못 보는 '구조'를 본다 ──────────────────

def test_stop_rail_rule_sits_beside_the_verdict_rule():
    """`.sec-empty.is-stop{border-left-color:var(--red)}` 는 `.verdict.is-stop` 바로 옆에 — 같은 관례, 같은 자리.
    app.css(Tailwind)가 아니라 템플릿 <style> 안이다."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    v = ".verdict.is-stop{border-top-color:var(--red)}"
    r = ".sec-empty.is-stop{border-left-color:var(--red)}"
    assert src.count(r) == 1
    assert 0 < src.index(r) - src.index(v) < 400, "레일 규칙이 verdict 규칙 옆에 있지 않다"
    assert ".masthead.is-stop .badge.judge" not in src, "버린 처방(알약에 rose)이 들어왔다"
    assert ".sec-empty.is-stop" not in (_TPL.parent / "static" / "app.css").read_text(encoding="utf-8")


def test_stop_lead_uses_the_label_verbatim_from_the_same_source():
    """첫 문장은 `{{ bidst.label }}입니다.` — 새 낱말·접기 없이 원문. 톤은 마스트헤드가 쓰는 `_tone0` 에서 —
    판정을 새로 계산하지 않는다(bid_state 호출 없음)."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    p_start = src.index(_BOX_OPEN_SRC)
    block = src[p_start:src.index("</div>", src.index(_ANCHOR, p_start))]
    assert src.count(_BOX_OPEN_SRC) == 1
    assert "{% if _stop0 %}<b style=\"color:var(--ink)\">{{ bidst.label }}입니다.</b> " in block
    assert "judge_label" not in block and "bid_state(" not in block
    assert "{% set _stop0 = (_tone0 == 'stop') %}" in src
    # _tone0 는 마스트헤드 주석과 <header> 사이에서 한 번만 정의되고, 이 그릇은 그 뒤에 온다
    assert src.count("{% set _tone0 = ") == 1
    assert src.index("<!-- 마스트헤드 -->") < src.index("{% set _tone0 = ") < src.index('<header class="masthead') < src.index(_BOX_OPEN_SRC)
    assert _OLD_VERB not in block



def test_report_template_gates_the_button_mention():
    """report.html 에서 `[다시 분석]` 은 `{% if is_admin(request) %}` 안에서만 나와야 한다.
    줄 번호가 아니라 앵커 문자열로 그 `<p>` 를 찾는다(CLAUDE.md 규칙 8)."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    # 그릇을 먼저 찾는다 — 바로 위 주석에도 같은 문장이 있어 앵커부터 찾으면 주석에 걸린다
    p_start = src.index(_BOX_OPEN_SRC)
    i = src.index(_ANCHOR, p_start)
    block = src[p_start:src.index("</div>", i)]
    assert "{% if is_admin(request) %}" in block, "게이트가 없다 — 누구에게나 관리자 문구가 나간다"
    g = block.index("{% if is_admin(request) %}")
    assert g < block.index(_ADMIN_ONLY), "버튼 언급이 게이트 앞에 있다"
    # 그 게이트의 else(= 공개 가지)는 게이트 뒤 첫 {% else %} — 공개 꼬리는 그 뒤에만, 버튼은 그 앞에만
    e = block.index("{% else %}", g)
    assert _PUBLIC_TAIL in block[e:] and _ADMIN_ONLY not in block[e:]
    assert _PUBLIC_LINE in block, "wait 톤 공개 문장이 원문에 없다"


def test_premise_detail_button_is_still_admin_only():
    """이 분기 문구를 가른 **전제**: detail.html 의 [다시 분석] 이 관리자 전용이라는 것.
    누군가 그 버튼을 공개로 열면 이 테스트가 먼저 울린다 — 그때는 리포트 문구도 같이 다시 봐야 한다."""
    src = (_TPL / "detail.html").read_text(encoding="utf-8")
    gate = "{% if can_analyze and v.status == '완료' and is_admin(request) %}"
    assert gate in src, "detail.html 의 [다시 분석] 게이트가 바뀌었다 — report.html 의 갈라 쓴 문구를 재검토하라"
    after = src[src.index(gate):]
    assert re.search(r"다시 분석</button>", after[:1200]), "게이트 바로 아래에 [다시 분석] 버튼이 없다"
