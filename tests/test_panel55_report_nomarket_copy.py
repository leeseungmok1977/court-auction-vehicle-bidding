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

# 두 변형에 공통인 앞머리 — 분기 자체가 렌더됐는지 확인하는 앵커
_ANCHOR = "시세가 아직 산정되지 않아"
# 관리자 변형에만 있어야 하는 것: 존재하는 버튼의 이름
_ADMIN_ONLY = "다시 분석"
# 공개 변형에 있어야 하는 것
_PUBLIC_LINE = "종합 리포트를 만들 수 없습니다"
# 공개 문구가 **하면 안 되는 약속** — 코드로 보장되지 않는 시점 (지시서 ⚠)
_TIMING_WORDS = ("곧", "매일", "잠시 후", "자동으로 다시", "다시 시도")


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
    import web.app as A
    return TestClient(A.app)


def _note(html: str) -> str:
    """앵커가 든 `<p>` 하나만 잘라 낸다 — 페이지 다른 곳의 낱말이 검사를 오염시키지 않게."""
    i = html.index(_ANCHOR)
    return html[i:html.index("</p>", i)]


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


def test_admin_copy_keeps_the_button_it_actually_has(client):
    """관리자(터널)는 버튼이 실제로 있으니 기존 문구를 유지한다."""
    r = client.get("/vehicle/nomed_1/report", headers=_TUNNEL)
    assert r.status_code == 200
    note = _note(r.text)
    assert "[" + _ADMIN_ONLY + "]" in note
    assert _PUBLIC_LINE not in note


def test_forged_loopback_host_with_xff_gets_public_copy(client):
    """Host 를 127.0.0.1 로 위조해도 nginx 가 붙인 XFF 가 있으면 공개 문구(test_exposure 와 같은 규약)."""
    r = client.get("/vehicle/nomed_1/report", headers={"host": "127.0.0.1", "x-forwarded-for": "203.0.113.7"})
    assert _ADMIN_ONLY not in _note(r.text)


# ── 템플릿 원문 검사 — 렌더 검사가 못 보는 '구조'를 본다 ──────────────────

def test_report_template_gates_the_button_mention():
    """report.html 에서 `[다시 분석]` 은 `{% if is_admin(request) %}` 안에서만 나와야 한다.
    줄 번호가 아니라 앵커 문자열로 그 `<p>` 를 찾는다(CLAUDE.md 규칙 8)."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    i = src.index(_ANCHOR)
    p_start = src.rindex("<p", 0, i)
    block = src[p_start:src.index("</p>", i)]
    assert "{% if is_admin(request) %}" in block, "게이트가 없다 — 누구에게나 관리자 문구가 나간다"
    assert block.index("{% if is_admin(request) %}") < block.index(_ADMIN_ONLY), "버튼 언급이 게이트 앞에 있다"
    assert "{% else %}" in block and _PUBLIC_LINE in block.split("{% else %}", 1)[1]


def test_premise_detail_button_is_still_admin_only():
    """이 분기 문구를 가른 **전제**: detail.html 의 [다시 분석] 이 관리자 전용이라는 것.
    누군가 그 버튼을 공개로 열면 이 테스트가 먼저 울린다 — 그때는 리포트 문구도 같이 다시 봐야 한다."""
    src = (_TPL / "detail.html").read_text(encoding="utf-8")
    gate = "{% if can_analyze and v.status == '완료' and is_admin(request) %}"
    assert gate in src, "detail.html 의 [다시 분석] 게이트가 바뀌었다 — report.html 의 갈라 쓴 문구를 재검토하라"
    after = src[src.index(gate):]
    assert re.search(r"다시 분석</button>", after[:1200]), "게이트 바로 아래에 [다시 분석] 버튼이 없다"
