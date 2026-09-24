"""PANEL-56 — 리포트 마스트헤드의 라벨 배지는 **점수 배지와 같은 게이트** 안에 있어야 한다.

발견(app-design-expert 검수 2026-09-24, Steward 재현): 마스트헤드의 점수 배지
`시세 신뢰도 NN/100` 은 `{% if conf %}` 로 숨는데, 바로 옆 라벨 배지
`{{ v.market_confidence_label or '—' }}` 는 게이트가 없었다. 시세 없는 물건은
`market_match._confidence_label(0)` 이 '낮음' 을 돌려줘 명사 없는 `낮음` 이 홀로 찍혔다 —
공개 431건 전건. 같은 물건을 상세 h1 칩은 `bidst.label`(예: '매각 종료')로 말했다.
**같은 물건, 두 화면, 두 말** — 판정 표시 문제다.

고친 뒤: 라벨 배지는 `conf` 게이트 안. 시세 없는 분기(`conf` 가 0)는 판정 단일 소스
`bidst.label` 을 같은 `.badge` 로 찍고, `bidst` 마저 없으면 배지를 그리지 않는다.
긴 라벨은 detail.html 과 같은 `ui.judge_label` 로 ' — ' 뒤에서만 접는다.

★ 시세 **있는** 물건의 마스트헤드 렌더는 한 글자도 바뀌면 안 된다 —
`_PRICED_MASTHEAD_MD5` 는 변경 **전**(커밋 b6990a1, report.html md5 59dba2e6…) 렌더에서 잰 값이다.
발행 시각(`now`)만 `<NOW>` 로 치환해 잰다.

반증 기록(2026-09-24): 라벨 배지를 게이트 밖(원래 자리)으로 되돌리면
`test_unpriced_masthead_never_shows_a_bare_low_badge` · `test_unpriced_masthead_says_what_detail_says` ·
`test_closed_vehicle_masthead_reads_closed_not_low` · `test_template_gates_label_badge_with_score_badge` 가 실패한다.

3회차(교차검수 처방, 지시서 2026-09-24-13): 이 분기의 알약은 `.badge` 가 원래 숫자용(mono 10.5px .06em)이라
한글 판정문이 타자기 태그처럼 읽혔다(app-design-expert 1). 그 분기에만 `class="badge judge"` — sans 12px/600,
자간 0, 6×12 padding, 큰글씨 14px. 색·외곽선은 `.badge` 그대로(의미색 없음 — stop 톤 경고는 본문 첫 문장이 맡는다,
`test_panel55_report_nomarket_copy.py`). 시세 있는 물건은 이 분기를 안 타므로 `_PRICED_MASTHEAD_MD5` 는 그대로다.
"""
import hashlib
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

_PUB = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}
_TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"

# 마스트헤드를 자르는 앵커(줄 번호 금지 — CLAUDE.md 규칙 8)
_MH_START = "<!-- 마스트헤드 -->"
_MH_END = "</header>"
_BADGES_START = '<div class="badges">'
_BADGES_END = '<div class="mh-eyebrow">'
_NOW = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
# 변경 전 렌더(시세 있는 픽스처 priced_1, 공개·관리자 동일)의 마스트헤드 md5 — 발행 시각만 <NOW>
_PRICED_MASTHEAD_MD5 = "e87fa43a022c6aa8db63d822988fda14"

# 시세 없는 물건의 실제 상태(운영 DB 실측 2026-09-24: median NULL 이면 confidence 0 · label '낮음' 이 296건)
_NOMED = dict(min_sale_price=9_000_000, appraisal_value=12_000_000, median_price=None,
              market_confidence=0, market_confidence_label="낮음")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p56.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 시세 있는 물건 — 렌더가 한 글자도 바뀌면 안 되는 쪽
    db.upsert_vehicle({**_BASE, "id": "priced_1", "folder_key": "priced_1", "case_no": "2026타경90001",
                       "judgment": "유찰 대기", "min_sale_price": 10_000_000, "appraisal_value": 12_000_000,
                       "median_price": 13_000_000})
    # 시세 없음 + 매각 종료 — 라이브 재현 물건(2025타경56677_1)과 같은 상태 → bid_state 'closed'
    db.upsert_vehicle({**_BASE, "id": "nomed_closed", "folder_key": "nomed_closed", "case_no": "2026타경90011",
                       "judgment": "종결", "auction_result": "낙찰", "sale_date": "2026-08-18", **_NOMED})
    # 시세 없음 + 기일 미도래 — 목록에 지금 뜨는 물건(2026타경51876_1)과 같은 상태 → 'lowconf'(' — ' 있는 긴 라벨)
    db.upsert_vehicle({**_BASE, "id": "nomed_up", "folder_key": "nomed_up", "case_no": "2026타경90012",
                       "judgment": "시세 신뢰도 낮음, 판정 보류", **_NOMED})
    # 시세 없음 + 침수 — stop 톤(운영 6건, `2025타경53062_1` 과 같은 상태). 알약에 의미색이 붙지 않아야 한다.
    db.upsert_vehicle({**_BASE, "id": "nomed_flood", "folder_key": "nomed_flood", "case_no": "2026타경90013",
                       "judgment": "시세 신뢰도 낮음, 수동 검토", "accident_grade": "flood", **_NOMED})
    import web.app as A
    return TestClient(A.app)


def _masthead(html: str) -> str:
    i = html.index(_MH_START)
    return _NOW.sub("<NOW>", html[i:html.index(_MH_END, i)])


def _badges(html: str) -> str:
    i = html.index(_BADGES_START)
    return html[i:html.index(_BADGES_END, i)]


def _label_of(vid: str) -> str:
    """판정 단일 소스가 실제로 내는 라벨 — 화면이 이것과 같은 말을 해야 한다."""
    from web import db
    return service.bid_state(db.get_vehicle(vid), BT, service.load_config())["label"]


def test_fixtures_actually_hit_their_branches(client):
    """공허 통과 방지: priced_1 은 점수 배지가 있고, nomed_* 는 없어야(conf 0) 아래 검사가 의미 있다."""
    assert '<div class="badge fill">' in client.get("/vehicle/priced_1/report", headers=_PUB).text
    for vid in ("nomed_closed", "nomed_up"):
        html = client.get(f"/vehicle/{vid}/report", headers=_PUB).text
        assert '<div class="badge fill">' not in html, f"{vid}: 점수 배지가 있다 — 시세 없는 분기가 아니다"
        assert '<span class="sec-no">' not in html
    # 두 픽스처가 서로 다른 판정 상태를 실제로 만든다(닫힘 / 판정 보류)
    assert _label_of("nomed_closed") == "매각 종료"
    assert " — " in _label_of("nomed_up"), "긴 라벨(접힘 검사)이 아니다"


@pytest.mark.parametrize("vid", ["nomed_closed", "nomed_up"])
@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_unpriced_masthead_never_shows_a_bare_low_badge(client, vid, hdr):
    """명사 없는 `낮음` 은 절대 안 나온다. '—' 자리표시도 안 나온다."""
    badges = _badges(client.get(f"/vehicle/{vid}/report", headers=hdr).text)
    assert '<div class="badge">낮음</div>' not in badges, f"{vid}: 홀로 찍힌 '낮음'"
    assert '<div class="badge judge">낮음</div>' not in badges, f"{vid}: 홀로 찍힌 '낮음'"
    assert ">—<" not in badges
    assert "시세 신뢰도 <b>" not in badges


@pytest.mark.parametrize("vid", ["nomed_closed", "nomed_up"])
def test_unpriced_masthead_says_what_detail_says(client, vid):
    """마스트헤드 배지 = bidst.label — 상세 h1 칩과 한 글자로 같은 말."""
    badges = _badges(client.get(f"/vehicle/{vid}/report", headers=_PUB).text)
    label = _label_of(vid)
    for part in label.split(" — "):
        assert part in badges, f"{vid}: 배지에 '{part}' 가 없다 — {badges}"
    assert badges.count('<div class="badge judge">') == 1, "배지는 하나(판정 라벨)만"
    assert '<div class="badge">' not in badges and "badge fill" not in badges
    if " — " not in label:
        assert "낮음" not in badges, f"{vid}: '낮음' 이 남아 있다"


def test_closed_vehicle_masthead_reads_closed_not_low(client):
    """라이브 재현 물건(낙찰·종결)의 마스트헤드가 상세와 같은 '매각 종료' 를 말한다."""
    badges = _badges(client.get("/vehicle/nomed_closed/report", headers=_PUB).text)
    assert '<div class="badge judge">매각 종료</div>' in badges
    assert "낮음" not in badges


def test_long_label_folds_only_after_the_dash(client):
    """' — ' 가 든 긴 라벨은 detail.html 과 같은 ui.judge_label 규칙 — 앞뒤 절만 nowrap, 그 사이에서만 접힌다."""
    badges = _badges(client.get("/vehicle/nomed_up/report", headers=_PUB).text)
    a, b = _label_of("nomed_up").split(" — ", 1)
    assert f'<span class="whitespace-nowrap">{a} —</span> <span class="whitespace-nowrap">{b}</span>' in badges, badges


def test_no_semantic_color_on_the_badge(client):
    """'해당 없음' 은 경고가 아니다 — .badge 그대로, 빨강·앰버·초록 금지."""
    for vid in ("nomed_closed", "nomed_up", "nomed_flood"):
        badges = _badges(client.get(f"/vehicle/{vid}/report", headers=_PUB).text)
        assert 'class="badge judge"' in badges
        for banned in ("var(--red)", "var(--amber)", "var(--green)", "style=", "rgba(225,29,72"):
            assert banned not in badges, f"{vid}: 배지에 {banned}"


@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_priced_masthead_unchanged_byte_for_byte(client, hdr):
    """★ 시세 있는 물건의 마스트헤드는 변경 전과 md5 가 같다(발행 시각만 치환).
    상수는 변경 전 커밋(b6990a1)의 템플릿으로 같은 픽스처를 렌더해 잰 값이다."""
    mh = _masthead(client.get("/vehicle/priced_1/report", headers=hdr).text)
    assert "<NOW>" in mh, "발행 시각 치환이 안 됐다 — 비교가 날짜에 흔들린다"
    assert hashlib.md5(mh.encode("utf-8")).hexdigest() == _PRICED_MASTHEAD_MD5, \
        "시세 있는 물건의 마스트헤드 렌더가 변경 전과 다르다"
    assert '<div class="badge">높음</div>' in mh and "시세 신뢰도 <b>78</b>/100" in mh


# ── 템플릿 원문 검사 — 렌더가 못 보는 '구조' ──────────────────────────────

def test_template_gates_label_badge_with_score_badge():
    """report.html 마스트헤드에서 라벨 배지는 점수 배지와 **같은** `{% if conf %}` 안에만 있어야 하고,
    시세 없는 분기는 `{% elif bidst %}` 로 bidst.label 을 judge_label 로 찍어야 한다."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    mh = src[src.index(_MH_START):src.index(_MH_END, src.index(_MH_START))]
    gate = "{% if conf %}<div class=\"badge fill\">"
    g = mh.index(gate)
    seg = mh[g:mh.index("{% endif %}", g)]
    assert "market_confidence_label" in seg, "라벨 배지가 conf 게이트 밖에 있다"
    assert mh.count("market_confidence_label") == 1, "마스트헤드에 라벨 배지가 둘 이상"
    assert "{% elif bidst %}" in seg and "ui.judge_label(bidst.label)" in seg.split("{% elif bidst %}", 1)[1]
    assert '<div class="badge judge">' in seg.split("{% elif bidst %}", 1)[1], "판정 알약에 judge 클래스가 없다"
    assert "{% else %}" not in seg, "bidst 가 없을 때도 무언가를 그린다 — 측정하지 않은 것을 말하지 않는다"
    # 본문 02 근거 점검의 같은 표기는 그대로다({% if report %} 안이라 시세 있을 때만 렌더)
    assert src.count("{{ v.market_confidence_label or '—' }}") == 2


# ── 3회차: 판정 알약 서체 `.badge.judge` — 시세 없는 분기에만 ──────────────────

def test_judge_class_only_in_the_unpriced_branch(client):
    """`badge judge` 는 시세 없는 물건에 정확히 하나, 시세 있는 물건에는 0 — 렌더와 원문 둘 다."""
    assert "badge judge" not in client.get("/vehicle/priced_1/report", headers=_PUB).text
    for vid in ("nomed_closed", "nomed_up", "nomed_flood"):
        html = client.get(f"/vehicle/{vid}/report", headers=_PUB).text
        assert html.count('class="badge judge"') == 1, vid
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    assert src.count('class="badge judge"') == 1
    mh = src[src.index(_MH_START):src.index(_MH_END, src.index(_MH_START))]
    assert 'class="badge judge"' in mh.split("{% elif bidst %}", 1)[1].split("{% endif %}", 1)[0]


def test_judge_badge_rules_and_base_badge_untouched():
    """`.badge.judge` 는 sans 12/600·자간 0·6×12, 큰글씨 14px. 공용 `.badge` 규칙은 한 글자도 안 바뀐다.
    버린 처방(`.masthead.is-stop .badge.judge` rose)은 없다. app.css 에는 아무것도 없다(템플릿 <style> 안)."""
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    assert src.count(".badge.judge{font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:0;padding:6px 12px}") == 1
    assert src.count("html.nc-large .badge.judge{font-size:14px}") == 1
    assert src.count(".badge{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;padding:5px 12px;border-radius:99px;"
                     "border:1px solid rgba(255,255,255,.3);color:rgba(255,255,255,.9)}") == 1, "공용 .badge 규칙이 바뀌었다"
    assert src.count("html.nc-large .badge{font-size:13px}") == 1
    assert ".masthead.is-stop .badge.judge" not in src
    assert "--sans:" in src, "리포트 sans 스택 변수가 없다 — .badge.judge 가 빈 폰트를 가리킨다"
    assert ".badge.judge" not in (_TPL.parent / "static" / "app.css").read_text(encoding="utf-8")


def test_stop_tone_badge_stays_neutral_but_header_is_marked(client):
    """stop 톤(침수)도 알약은 흰 외곽선 그대로 — 경고는 본문이 맡는다. 헤더의 is-stop 훅은 그대로 붙는다."""
    html = client.get("/vehicle/nomed_flood/report", headers=_PUB).text
    mh = _masthead(html)
    assert 'class="masthead is-stop"' in mh
    badges = _badges(html)
    label = _label_of("nomed_flood")
    assert label == "침수·전손 의심 — 입찰 보류"
    for part in label.split(" — "):
        assert part in badges
    assert 'class="badge judge"' in badges and "style=" not in badges
