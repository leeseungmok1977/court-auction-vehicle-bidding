"""리포트 섹션 번호는 01~12가 끊기지 않아야 한다.

2026-09-13 18인 패널: 3명이 "04 다음에 바로 06 — 05가 통째로 없음"을 **버그로**
읽었다. p39(디자이너): "넘버링을 신뢰 장치로 쓰기로 했으면 번호가 비면 안 돼요."

원인은 두 섹션이 자료 없을 때 통째로 사라지는 구조였다는 것:
    04  {% if v.spec_remark or appraisal %}
    05  {% if comps_won or (v.comps and is_admin(request)) %}
05는 상단 탭에 `#sec05 시세비교` 링크가 **남아 있는데** 대상이 없어서 더 나빴다.
표본 400건을 세어 보니 comps_won 이 없는 물건이 248건(62%) — 예외가 아니라 다수다.

이제 두 섹션 모두 항상 렌더하고, 비었을 때는 **왜 비었는지**를 본문에 적는다.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

_PUB = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}

_SEC_NO = re.compile(r'<span class="sec-no">(\d\d)</span>')
_TAB = re.compile(r'href="#(sec\d\d)"')


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "sections.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 가장 헐벗은 물건 — 명세요약도, 감정요항도, 유사낙찰도 없다.
    db.upsert_vehicle({**_BASE, "id": "bare_1", "folder_key": "bare_1",
                       "case_no": "2026타경90001", "judgment": "유찰 대기",
                       "min_sale_price": 10_000_000, "appraisal_value": 12_000_000,
                       "median_price": 13_000_000})
    # 시세조차 없는 경우 — 빈 상태 문구의 {% if med %} 분기
    db.upsert_vehicle({**_BASE, "id": "bare_nomed", "folder_key": "bare_nomed",
                       "case_no": "2026타경90002", "judgment": "유찰 대기",
                       "min_sale_price": 10_000_000, "appraisal_value": 12_000_000,
                       "median_price": None})
    import web.app as A
    return TestClient(A.app)


@pytest.mark.parametrize("hdr", [_PUB, _TUNNEL], ids=["public", "admin"])
def test_section_numbers_have_no_gap(client, hdr):
    html = client.get("/vehicle/bare_1/report", headers=hdr).text
    nums = _SEC_NO.findall(html)
    assert nums, "섹션 번호를 하나도 못 찾았다 — 셀렉터가 바뀌었는지 확인"
    got = [int(n) for n in nums]
    assert got == list(range(1, len(got) + 1)), f"번호가 끊겼다: {nums}"
    assert got[-1] == 12, f"마지막 섹션이 12가 아니다: {nums}"


@pytest.mark.parametrize("vid", ["bare_1", "bare_nomed"])
def test_every_tab_anchor_exists(client, vid):
    """탭이 가리키는 앵커가 실제로 문서에 있어야 한다 — 05가 이걸로 깨졌다."""
    html = client.get(f"/vehicle/{vid}/report", headers=_PUB).text
    for anchor in set(_TAB.findall(html)):
        assert f'id="{anchor}"' in html, f"탭 {anchor} 의 대상이 문서에 없다"


def test_unpriced_report_drops_the_tabs_instead_of_dangling_them(client):
    """시세 미산정이면 본문 01~12가 통째로 없다. 그때 탭 5개가 남아 있으면
    눌러도 아무 일이 없다 — 없는 목차를 보여주느니 목차를 내린다."""
    html = client.get("/vehicle/bare_nomed/report", headers=_PUB).text
    assert "종합 리포트를 생성할 수 없습니다" in html
    assert not _SEC_NO.findall(html), "본문이 없는데 섹션 번호가 있다"
    assert not _TAB.findall(html), "대상 없는 탭 앵커가 남았다"


def test_empty_sections_say_why(client):
    """번호만 채우고 내용을 비워 두면 그건 그냥 다른 종류의 버그다."""
    html = client.get("/vehicle/bare_1/report", headers=_PUB).text
    assert "법원 실낙찰 기록이 아직 확보되지 않았습니다" in html
    assert "매각물건명세 요약·감정 요항 본문이 없습니다" in html


def test_empty_state_does_not_leak_sample_counts(client):
    """M01 — 공개 응답에 동급 매물·표본 수를 흘리지 않는다."""
    html = client.get("/vehicle/bare_1/report", headers=_PUB).text
    body = html[html.index('id="sec05"'):html.index('id="sec06"')]
    for banned in ("동급 매물", "표본", "엔카", "encar"):
        assert banned not in body, f"05 빈 상태에 '{banned}' 노출"


# ── 예상낙찰가 미산출 물건(713건 중 171건 = 24%)의 표기 ──────────────
# 발견 경위: 05 빈 섹션을 눈으로 보다가 바로 아래 06 제목이 "예상낙찰가 0원 기준"인데
# 표는 48,392,900원인 것을 봤다. 측정으로는 안 잡혔다(넘침 0건이었다).
#   ① 06·08 제목이 exp 를 그대로 찍어 "0원 기준" — 표와 다른 말
#   ② allin_ref 가 **최저매각가 미만**인 상한가로 계산 — 법적으로 못 쓰는 금액
#      (같은 함수의 sim 표는 이미 그 후보를 걸러내고 있었다)
#   ③ 10 산출 로직이 폴백 산식을 그려 "69,990,000 × 82% ＝ 0" — 검산이 안 닫힌다
# stale_floor(유찰 있는데 최저가=감정가)는 **일부러** 미산출로 두는 정직한 동작이다.
# 고칠 것은 산출이 아니라 표기다.

_STALE = dict(min_sale_price=66_000_000, appraisal_value=66_000_000,
              median_price=69_990_000, upper_bid=48_392_900, fail_count=1)


@pytest.fixture
def stale(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "stale.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "stale_1", "folder_key": "stale_1",
                       "case_no": "2026타경90003", "judgment": "유찰 대기", **_STALE})
    import web.app as A
    return TestClient(A.app)


def test_unpriced_vehicle_is_actually_unpriced(stale):
    """픽스처가 exp=0 상태를 실제로 만드는지 — 아니면 아래 테스트가 공허하다."""
    from web import db
    v = db.get_vehicle("stale_1")
    assert service.stale_floor(v) is True
    r = service.report_data(v, service.load_config(), BT)
    assert r and not r["exp"], "exp 가 0이 아니면 이 파일이 검사할 게 없다"


def test_allin_basis_never_below_the_legal_floor(stale):
    """최저매각가 미만은 써낼 수 없는 금액이다 — 취득원가 기준으로 쓰면 안 된다."""
    from web import db
    v = db.get_vehicle("stale_1")
    r = service.report_data(v, service.load_config(), BT)
    assert r["allin_bid"] >= v["min_sale_price"], (
        f"기준 낙찰가 {r['allin_bid']:,} < 최저매각가 {v['min_sale_price']:,}")
    assert r["allin_ref"]["bid"] == r["allin_bid"], "표와 라벨이 다른 값을 쓴다"
    assert r["allin_basis"] == "floor"


def test_no_zero_won_labels_anywhere(stale):
    """'0원 기준' 같은 거짓 라벨이 한 곳도 없어야 한다."""
    html = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    bad = [m.group(0).strip() for m in re.finditer(r".{40}(?<![\d,])0\s*(?:만원|원)", text)]
    assert not bad, "0원/0만원 표기: " + " || ".join(bad[:4])


def test_section_titles_name_the_number_they_used(stale):
    """06·08 제목이 실제로 계산에 쓴 값을 말해야 한다."""
    html = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    assert "현 최저매각가 66,000,000원 기준" in html, "06 제목이 기준값과 다르다"
    assert "낙찰가 66,000,000원(현 최저매각가) 고정" in html, "08 제목이 기준값과 다르다"


def test_logic_section_explains_instead_of_printing_a_broken_equation(stale):
    """10은 닫히지 않는 검산(× 82% ＝ 0)을 그리는 대신 이유를 적는다."""
    html = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    body = html[html.index("<h2>산출 로직</h2>"):]
    assert "예상낙찰가를 산출하지 않았습니다" in body
    assert "저감된 가격을" in body and "아직 공고하지 않은" in body
    assert "실측 낙찰률(유찰횟수 반영)" not in body, "쓰지 않은 폴백 산식이 인쇄된다"


def test_unpriced_report_never_claims_an_expected_price(stale):
    """없는 값에 적중률을 달거나, 없는 값을 초과했다고 말하지 않는다."""
    html = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    head = html[html.index('id="sec01"'):html.index('id="sec02"')]
    assert "미산출" in head
    assert "실측 ±10% 적중" not in head, "미산출인데 정확도 꼬리표가 붙었다"
    assert "예상낙찰가 초과 — 추가 유찰" not in head, "없는 값을 초과했다고 말한다"


def test_scenario_bid_is_not_tagged_as_a_verified_fact(stale):
    """초록 confirmed 는 '검증된 사실'에만. 최저매각가를 낙찰가 자리에 넣은 것은
    하한 시나리오이지 확정 낙찰가가 아니다(디자인 검수 지적 1)."""
    html = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    row = html[html.index(">낙찰가</td>"):]
    row = row[:row.index("</tr>")]
    assert "tag confirmed" not in row, "가정치에 '검증됨' 색이 붙었다"
    assert "하한 시나리오" in row


def test_unbiddable_ceiling_is_flagged(stale):
    """상한선(5,710만)이 최저매각가(6,600만)보다 낮으면 그 큰 숫자는 써낼 수 없다.
    화면에서 가장 큰 숫자가 못 쓰는 금액인데 아무 표시가 없었다(디자인 검수 지적 2)."""
    from web import db
    v = db.get_vehicle("stale_1")
    mb = service.bid_state(v, BT)["max_bid"]
    assert mb and mb < v["min_sale_price"], f"픽스처 전제가 깨졌다: max_bid={mb}"
    head = stale.get("/vehicle/stale_1/report", headers=_PUB).text
    head = head[head.index('id="sec01"'):head.index('id="sec02"')]
    assert "써낼 수 없는 금액" in head
    assert "어떤 금액을 써도 손해" in head


def test_empty_sections_are_not_double_framed(stale, client):
    """흰 카드 안의 빈 박스는 '렌더 실패'로 보인다 — 자료가 없으면 카드를 씌우지 않는다."""
    html = client.get("/vehicle/bare_1/report", headers=_PUB).text
    body = html[html.index('id="sec05"'):html.index('id="sec06"')]
    assert 'class="card"' not in body, "빈 05가 카드 껍데기 안에 들어 있다"
    assert 'class="sec-empty"' in body


def test_priced_vehicle_still_shows_the_normal_formula(client):
    """미산출 분기를 넣다가 정상 물건의 산식을 덮지 않았는지."""
    html = client.get("/vehicle/bare_1/report", headers=_PUB).text
    assert "예상낙찰가를 산출하지 않았습니다" not in html
    assert "예상낙찰가 " in html


def test_section_05_still_shows_real_data_when_present(client, monkeypatch):
    """빈 상태를 넣다가 실데이터 경로를 덮지 않았는지."""
    monkeypatch.setattr(service, "comparable_sales", lambda *a, **k: [
        {"case_no": "2025타경1", "year": 2020, "mileage_km": 90000,
         "winning_price": 9_000_000, "median_price": 12_000_000, "ratio": 0.75,
         "court": "수원지방법원", "sale_date": "2025-05-01"}])
    html = client.get("/vehicle/bare_1/report", headers=_PUB).text
    assert "유사 낙찰 실적" in html
    assert "법원 실낙찰 기록이 아직 확보되지 않았습니다" not in html
